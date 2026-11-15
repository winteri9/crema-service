import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { gsap } from 'gsap';

/**
 * Просмотрщик машины: GLB из Blender, орбита, послойная разборка по кнопке,
 * подсветка узла под курсором и подписи с выносками к самим деталям.
 *
 * Контракт с моделью:
 *  - 16 узлов верхнего уровня названы по-русски («Корпус», «Бойлер»…);
 *    подпись на сайте — это obj.name, отдельного словаря нет;
 *  - вектор разборки лежит в userData.explode (три числа в метрах);
 *  - волна разборки — в userData.wave, если экспорт её донёс.
 */

type Part = {
  obj: THREE.Object3D;
  rest: THREE.Vector3;
  vector: THREE.Vector3;
  wave: number;
  label: string;
  el: HTMLElement;
  line: SVGLineElement;
  dot: SVGCircleElement;
  h: number;
  w: number;
  x: number;
  y: number;
  side: number;
};

/** Порядок разборки, если userData.wave не дошёл: панели → лицо → узлы → нутро. */
const WAVES: string[][] = [
  ['Левая панель', 'Правая панель', 'Верхняя площадка'],
  ['Лицевая панель', 'Панель управления'],
  ['Варочная группа', 'Держатель фильтра', 'Паровой кран', 'Каплесборник'],
  ['Бак для воды', 'Контейнер для зёрен'],
  ['Заварочный блок', 'Бойлер', 'Помпа', 'Кофемолка'],
];

const waveOf = (name: string): number => {
  const i = WAVES.findIndex((w) => w.includes(name));
  return i < 0 ? 0 : i;
};

/** Окружение из трёх зон: ключевая, заполняющая и контровая — металлу есть что отражать. */
function buildEnv(renderer: THREE.WebGLRenderer) {
  const env = new THREE.Scene();
  const box = new THREE.Mesh(
    new THREE.BoxGeometry(12, 12, 12),
    new THREE.MeshBasicMaterial({ color: new THREE.Color(0.075, 0.066, 0.056), side: THREE.BackSide }),
  );
  env.add(box);

  // горизонтальная полоса-горизонт: именно она даёт вертикальным панелям градиентный блик
  const bandMat = new THREE.MeshBasicMaterial({ side: THREE.DoubleSide });
  bandMat.color.setRGB(0.62, 0.54, 0.42);
  const band = new THREE.Mesh(new THREE.CylinderGeometry(5.4, 5.4, 1.15, 40, 1, true), bandMat);
  band.position.y = 0.25;
  env.add(band);

  const zone = (
    color: [number, number, number],
    size: [number, number],
    pos: [number, number, number],
  ) => {
    const m = new THREE.MeshBasicMaterial();
    m.color.setRGB(color[0], color[1], color[2]);
    const p = new THREE.Mesh(new THREE.PlaneGeometry(size[0], size[1]), m);
    p.position.set(pos[0], pos[1], pos[2]);
    p.lookAt(0, 0, 0);
    env.add(p);
    return p;
  };

  // ключ — большой тёплый софтбокс сверху-слева-спереди
  zone([2.6, 2.35, 2.05], [5.2, 3.4], [-2.4, 3.0, 2.6]);
  // заполнение — холоднее и слабее, справа
  zone([0.55, 0.50, 0.46], [3.6, 2.4], [3.4, 0.6, 1.8]);
  // контровый — узкая полоса сзади, чтобы по силуэту бежал блик
  zone([1.25, 1.05, 0.80], [4.0, 0.9], [0.4, 1.6, -4.0]);
  // нижняя подсветка — совсем немного, чтобы низ корпуса не был чёрным
  zone([0.26, 0.22, 0.18], [6.0, 6.0], [0.0, -4.2, 0.0]);

  const pmrem = new THREE.PMREMGenerator(renderer);
  const tex = pmrem.fromScene(env, 0.02).texture;
  pmrem.dispose();
  env.traverse((o) => {
    const m = o as THREE.Mesh;
    if (m.isMesh) {
      m.geometry.dispose();
      (m.material as THREE.Material).dispose();
    }
  });
  box.geometry.dispose();
  (box.material as THREE.Material).dispose();
  return tex;
}

/** Мягкая контактная тень: радиальный градиент в canvas-текстуре. */
function shadowTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const g = c.getContext('2d');
  if (g) {
    const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    grad.addColorStop(0, 'rgba(0,0,0,0.62)');
    grad.addColorStop(0.45, 'rgba(0,0,0,0.34)');
    grad.addColorStop(0.75, 'rgba(0,0,0,0.09)');
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grad;
    g.fillRect(0, 0, 256, 256);
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export function initViewer(root: HTMLElement) {
  const canvas = root.querySelector<HTMLCanvasElement>('[data-viewer-canvas]');
  const labelHost = root.querySelector<HTMLElement>('[data-viewer-labels]');
  const btn = root.querySelector<HTMLButtonElement>('[data-viewer-toggle]');
  const stage = root.querySelector<HTMLElement>('[data-viewer-stage]');
  if (!canvas || !labelHost || !btn || !stage) return;

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let renderer: THREE.WebGLRenderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  } catch {
    root.classList.add('is-static');
    return;
  }

  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearAlpha(0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.12;
  renderer.shadowMap.enabled = false;

  const scene = new THREE.Scene();
  scene.environment = buildEnv(renderer);
  scene.environmentIntensity = 1.45;

  const camera = new THREE.PerspectiveCamera(30, 1, 0.03, 20);
  camera.position.set(0.52, 0.40, 0.76);

  // Точечные источники только подчёркивают форму, основную работу делает env.
  const key = new THREE.DirectionalLight(0xfff0dc, 1.35);
  key.position.set(0.9, 1.2, 0.9);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xffd9a8, 1.25);
  rim.position.set(-0.8, 0.7, -1.0);
  scene.add(rim);
  const fill = new THREE.DirectionalLight(0xcfc0ad, 0.45);
  fill.position.set(-0.7, 0.15, 1.1);
  scene.add(fill);

  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.075;
  controls.enablePan = false;
  controls.minDistance = 0.5;
  controls.maxDistance = 2.0;
  controls.minPolarAngle = Math.PI * 0.18;
  controls.maxPolarAngle = Math.PI * 0.56;
  controls.target.set(0, 0.2, 0);
  controls.autoRotate = !reduce;
  controls.autoRotateSpeed = 0.4;
  controls.addEventListener('start', () => {
    controls.autoRotate = false;
  });

  const machine = new THREE.Group();
  scene.add(machine);

  // контактная тень
  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.MeshBasicMaterial({
      map: shadowTexture(),
      transparent: true,
      depthWrite: false,
      opacity: 0.55,
    }),
  );
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = 0.0015;
  shadow.scale.setScalar(0.72);
  shadow.renderOrder = -1;
  scene.add(shadow);

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'viewer__leaders');
  svg.setAttribute('aria-hidden', 'true');
  labelHost.appendChild(svg);

  const parts: Part[] = [];
  const pickables: THREE.Mesh[] = [];
  let hovered: THREE.Object3D | null = null;
  let ready = false;
  let progress = 0;
  let exploded = false;

  const size = { w: 1, h: 1 };
  const tmp = new THREE.Vector3();
  const box = new THREE.Box3();
  const center = new THREE.Vector3();

  const resize = () => {
    const r = stage.getBoundingClientRect();
    size.w = Math.max(1, Math.round(r.width));
    size.h = Math.max(1, Math.round(r.height));
    renderer.setSize(size.w, size.h, false);
    camera.aspect = size.w / size.h;
    camera.updateProjectionMatrix();
    svg.setAttribute('viewBox', `0 0 ${size.w} ${size.h}`);
  };
  resize();
  new ResizeObserver(resize).observe(stage);

  const loader = new GLTFLoader();
  loader.load(
    new URL('model/machine.glb', document.baseURI).href,
    (gltf) => {
      const model = gltf.scene;
      box.setFromObject(model);
      const s =
        0.46 /
        Math.max(box.max.x - box.min.x, box.max.y - box.min.y, box.max.z - box.min.z);
      model.scale.setScalar(s);
      box.setFromObject(model);
      center.set((box.min.x + box.max.x) / 2, 0, (box.min.z + box.max.z) / 2);
      model.position.sub(new THREE.Vector3(center.x, box.min.y, center.z));
      machine.add(model);

      model.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (!mesh.isMesh) return;
        const src = mesh.material as THREE.MeshStandardMaterial;
        const clone = src.clone();
        clone.envMapIntensity = 1.15;
        mesh.material = clone;
        pickables.push(mesh);
      });

      model.traverse((child) => {
        const vec = child.userData?.explode as number[] | undefined;
        if (!vec) return;
        // GLTFLoader прогоняет имена через sanitizeNodeName и меняет пробелы на «_».
        // В модели пробелов кроме разделителя слов нет — возвращаем их обратно.
        const label = child.name.replace(/_/g, ' ');
        if (!label) return;

        const el = document.createElement('span');
        el.className = 'viewer__label';
        el.textContent = label;
        el.style.opacity = '0';
        labelHost.appendChild(el);

        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('class', 'viewer__leader');
        svg.appendChild(line);
        const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        dot.setAttribute('class', 'viewer__leader-dot');
        dot.setAttribute('r', '2.6');
        svg.appendChild(dot);

        const wave = typeof child.userData?.wave === 'number'
          ? (child.userData.wave as number)
          : waveOf(child.name.replace(/_/g, ' '));

        parts.push({
          obj: child,
          rest: child.position.clone(),
          // Вектор в метрах: делим на масштаб модели, чтобы в локальных координатах он дал ту же длину.
          vector: new THREE.Vector3(vec[0], vec[1], vec[2]).multiplyScalar(1 / s),
          wave,
          label,
          el,
          line,
          dot,
          h: 22,
          w: 120,
          x: 0,
          y: 0,
          side: 1,
        });
      });

      parts.forEach((p) => {
        const r = p.el.getBoundingClientRect();
        p.h = r.height || 22;
        p.w = r.width || 120;
      });

      btn.disabled = false;
      root.classList.add('is-ready');
      ready = true;
      apply(progress);
    },
    undefined,
    () => {
      root.classList.add('is-static');
    },
  );

  const apply = (p: number) => {
    for (const part of parts) {
      // Волны: панели уходят первыми, нутро — последним.
      const at = part.wave * 0.16;
      const local = Math.min(1, Math.max(0, (p - at) / 0.62));
      const e = local * local * (3 - 2 * local);
      part.obj.position.set(
        part.rest.x + part.vector.x * e,
        part.rest.y + part.vector.y * e,
        part.rest.z + part.vector.z * e,
      );
    }
    shadow.material.opacity = 0.55 - 0.3 * p;
    shadow.scale.setScalar(0.72 + 0.5 * p);
  };

  const setExploded = (next: boolean) => {
    exploded = next;
    btn.textContent = next ? 'Собрать' : 'Разобрать';
    btn.setAttribute('aria-pressed', String(next));
    // в разобранном виде машина должна стоять неподвижно — иначе подписи уезжают
    if (next) controls.autoRotate = false;

    const state = { v: progress };
    gsap.killTweensOf(state);
    gsap.to(state, {
      v: next ? 1 : 0,
      duration: reduce ? 0 : 2.4,
      ease: 'none',
      onUpdate: () => {
        progress = state.v;
        apply(progress);
      },
    });

    // Отъезжаем вместе с разборкой, но не отбираем управление у мыши.
    const dir = camera.position.clone().sub(controls.target).normalize();
    const cam = {
      d: camera.position.distanceTo(controls.target),
      y: controls.target.y,
    };
    const portrait = size.w / size.h < 1;
    gsap.to(cam, {
      d: next ? (portrait ? 1.5 : 1.12) : portrait ? 1.15 : 0.95,
      y: next ? 0.14 : 0.2,
      duration: reduce ? 0 : 1.4,
      ease: 'power3.inOut',
      onUpdate: () => {
        controls.target.y = cam.y;
        camera.position.copy(controls.target).addScaledVector(dir, cam.d);
      },
    });
  };

  btn.addEventListener('click', () => setExploded(!exploded));

  // Стартовый кадр: отъезжаем на дистанцию, зависящую от аспекта сцены.
  {
    const dir0 = camera.position.clone().sub(controls.target).normalize();
    const d0 = size.w / size.h < 1 ? 1.15 : 0.95;
    camera.position.copy(controls.target).addScaledVector(dir0, d0);
  }

  // ?explode в адресе — сразу открыть разобранную машину (для показа и проверок).
  if (new URLSearchParams(location.search).has('explode')) setExploded(true);

  // --- подсветка ------------------------------------------------------------

  const ray = new THREE.Raycaster();
  const pointer = new THREE.Vector2();

  const paint = (obj: THREE.Object3D, on: boolean) => {
    obj.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      const m = mesh.material as THREE.MeshStandardMaterial;
      if (!m || !m.emissive) return;
      m.emissive.setHex(on ? 0xd8a24a : 0x000000);
      m.emissiveIntensity = on ? 0.22 : 0;
    });
  };

  const hoverOff = () => {
    if (!hovered) return;
    paint(hovered, false);
    hovered = null;
    canvas.style.cursor = 'grab';
    root.classList.remove('is-hover');
  };

  canvas.addEventListener('pointermove', (ev) => {
    if (!ready) return;
    const r = canvas.getBoundingClientRect();
    pointer.x = ((ev.clientX - r.left) / r.width) * 2 - 1;
    pointer.y = -((ev.clientY - r.top) / r.height) * 2 + 1;
    ray.setFromCamera(pointer, camera);
    const hit = ray.intersectObjects(pickables, false)[0];
    if (!hit) {
      hoverOff();
      return;
    }
    // поднимаемся до корневого узла детали (у него есть explode)
    let node: THREE.Object3D | null = hit.object;
    while (node && typeof node.userData?.explode === 'undefined') node = node.parent;
    if (!node || node === hovered) return;
    hoverOff();
    hovered = node;
    paint(node, true);
    canvas.style.cursor = 'pointer';
    root.classList.add('is-hover');
  });
  canvas.addEventListener('pointerleave', hoverOff);

  // --- подписи ---------------------------------------------------------------

  const placeLabels = () => {
    const cx = size.w / 2;
    const alpha = Math.min(1, Math.max(0, (progress - 0.3) / 0.45));

    const pts: Part[] = [];
    for (const part of parts) {
      box.setFromObject(part.obj);
      if (box.isEmpty()) continue;
      box.getCenter(center);
      tmp.copy(center).project(camera);
      part.x = (tmp.x * 0.5 + 0.5) * size.w;
      part.y = (-tmp.y * 0.5 + 0.5) * size.h;
      part.side = part.x < cx ? -1 : 1;
      pts.push(part);
    }

    // разводим по вертикали отдельно в каждой колонке
    for (const side of [-1, 1]) {
      const col = pts.filter((p) => p.side === side).sort((a, b) => a.y - b.y);
      const gap = 24;
      for (let i = 1; i < col.length; i++) {
        const min = col[i - 1].y + Math.max(gap, col[i - 1].h + 4);
        if (col[i].y < min) col[i].y = min;
      }
      // если колонка вылезла за низ — подтягиваем вверх
      let over = 0;
      const last = col[col.length - 1];
      if (last) over = Math.max(0, last.y + last.h / 2 - (size.h - 20));
      if (over > 0) for (const p of col) p.y -= over;
    }

    for (const p of pts) {
      const off = 52;
      const tipX = p.x + p.side * off;
      const tipY = p.y;
      const edgeX = tipX + p.side * 12;
      p.el.style.opacity = alpha.toFixed(3);
      p.el.style.transform = `translate(${Math.round(edgeX)}px, ${Math.round(tipY - p.h / 2)}px) translateX(${p.side < 0 ? '-100%' : '0'})`;

      p.line.setAttribute('x1', String(Math.round(edgeX)));
      p.line.setAttribute('y1', String(Math.round(tipY)));
      p.line.setAttribute('x2', String(Math.round(p.x + p.side * 8)));
      p.line.setAttribute('y2', String(Math.round(p.y)));
      p.line.style.opacity = String(alpha * 0.55);
      p.dot.setAttribute('cx', String(Math.round(p.x)));
      p.dot.setAttribute('cy', String(Math.round(p.y)));
      p.dot.style.opacity = String(alpha);
    }
  };

  let visible = true;
  new IntersectionObserver(
    (entries) => {
      visible = entries[0]?.isIntersecting ?? true;
    },
    { threshold: 0 },
  ).observe(stage);

  const frame = () => {
    if (visible && ready) placeLabels();
    controls.update();
    if (visible) renderer.render(scene, camera);
    requestAnimationFrame(frame);
  };
  frame();
}
