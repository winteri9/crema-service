import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { HDRLoader } from 'three/examples/jsm/loaders/HDRLoader.js';
import { RectAreaLightUniformsLib } from 'three/examples/jsm/lights/RectAreaLightUniformsLib.js';
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
  ['Левая панель', 'Правая панель', 'Верхняя площадка', 'Контейнер для зёрен'],
  ['Лицевая панель', 'Панель управления'],
  ['Варочная группа', 'Держатель фильтра', 'Паровой кран', 'Каплесборник'],
  ['Бак для воды'],
  ['Заварочный блок', 'Бойлер', 'Помпа', 'Кофемолка'],
];

/** Узлы, подписи которых видны всегда. Остальные — только под курсором. */
const ALWAYS = new Set([
  'Варочная группа',
  'Держатель фильтра',
  'Бойлер',
  'Заварочный блок',
  'Помпа',
  'Бак для воды',
]);
const waveOf = (name: string): number => {
  const i = WAVES.findIndex((w) => w.includes(name));
  return i < 0 ? 0 : i;
};

/**
 * GLTFLoader прогоняет имена через sanitizeNodeName и меняет пробелы на «_».
 * Внешний код (FAULTS, список-оглавление) присылает имена с пробелами,
 * поэтому сравниваем всегда в нормализованном виде — с любой стороны.
 */
const norm = (name: string) => name.replace(/_/g, ' ').replace(/\s+/g, ' ').trim();

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
  // AgX и экспозиция 1.0 — ровно как постер в Blender (build.py:843).
  renderer.toneMapping = THREE.AgXToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.shadowMap.enabled = false;
  RectAreaLightUniformsLib.init();

  const scene = new THREE.Scene();
  // Окружение — настоящая HDR-студия из Blender (tools/blender/env.py).
  scene.environment = buildEnv(renderer);
  // HDR-студия из tools/blender/env.py — теперь основное окружение (карта ярче коробки
  // в 4,4 раза по средней яркости). ?box — сравнить со старым процедурным окружением.
  const USE_HDR = !new URLSearchParams(location.search).has('box');
  const HDR_INTENSITY = 0.06;
  scene.environmentIntensity = USE_HDR ? HDR_INTENSITY : 1.45;

  if (USE_HDR) {
    new HDRLoader().load(
      new URL('hdr/studio.hdr', document.baseURI).href,
      (hdr) => {
        hdr.mapping = THREE.EquirectangularReflectionMapping;
        const pmrem = new THREE.PMREMGenerator(renderer);
        const env = pmrem.fromEquirectangular(hdr).texture;
        pmrem.dispose();
        hdr.dispose();
        scene.environment = env;
        scene.environmentIntensity = HDR_INTENSITY;
      },
      undefined,
      () => {},
    );
  }

  const camera = new THREE.PerspectiveCamera(30, 1, 0.03, 20);
  camera.position.set(0.52, 0.40, 0.76);

  // Точечных ламп нет намеренно: в постере свет дают только четыре area-лампы
  // и мир. Любая добавка direction-света ломает совпадение с эталоном.

  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.075;
  controls.enablePan = false;
  controls.minDistance = 0.5;
  controls.maxDistance = 2.0;
  // Колесо не перехватываем: страница должна листаться. Зум — Ctrl+колесо, пинч и кнопки.
  controls.enableZoom = false;
  canvas.addEventListener(
    'wheel',
    (ev) => {
      if (!ev.ctrlKey && !ev.metaKey) return;
      ev.preventDefault();
      const dir = camera.position.clone().sub(controls.target).normalize();
      const d = camera.position.distanceTo(controls.target);
      const next = THREE.MathUtils.clamp(d + Math.sign(ev.deltaY) * 0.08, 0.5, 2.0);
      camera.position.copy(controls.target).addScaledVector(dir, next);
    },
    { passive: false },
  );
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
  let DIST_CLOSED = 0.9;
  let DIST_OPEN = 1.1;
  let progress = 0;
  let exploded = false;
  let anim: gsap.core.Tween | null = null;

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

  // Студия постера: те же четыре area-лампы, что в build.py:995-998.
  // Без них IBL заливает корпус ровным светом, и металл перестаёт читаться.
  // Позиции Blender (X, Y, Z) → three (X, Z, -Y); размеры и мощность как в постере.
  // three без физических единиц: мощность Blender переводится в яркость
  // с этим множителем — им же и подбирается экспозиция студии.
  const STUDIO_GAIN = 0.25;
  const addStudioLights = (s: number) => {
    const studio = [
      { pos: [-1.05, 1.28, 1.25], target: [0.0, 0.24, 0.02], w: 2.2, h: 1.6, power: 110, color: 0xfff0dc },
      { pos: [1.25, 0.52, 0.95], target: [0.0, 0.18, 0.0], w: 1.4, h: 1.05, power: 45, color: 0xf2ebe5 },
      { pos: [0.3, 1.0, -1.3], target: [0.0, 0.22, 0.0], w: 1.0, h: 0.7, power: 70, color: 0xffe0bc },
      { pos: [0.16, 0.122, 0.13], target: [0.0, 0.05, 0.15], w: 0.16, h: 0.09, power: 3.5, color: 0xffe0b8 },
    ];
    for (const l of studio) {
      // Интенсивность RectAreaLight в three — это яркость; из мощности Blender
      // она получается как power / (площадь * pi).
      const light = new THREE.RectAreaLight(l.color, (l.power / (l.w * l.h * Math.PI)) * STUDIO_GAIN, l.w * s, l.h * s);
      light.position.set(l.pos[0] * s, l.pos[1] * s, l.pos[2] * s);
      light.lookAt(l.target[0] * s, l.target[1] * s, l.target[2] * s);
      scene.add(light);
    }
  };

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
      addStudioLights(s);

      model.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (!mesh.isMesh) return;
        const src = mesh.material as THREE.MeshStandardMaterial;
        const clone = src.clone();
        const nm = (src.name || '').toLowerCase();
        // Чистый PBR из GLB: металл получает отражения окружения, без шума в шейдере.
        // Золото читается мягче, хром — жёстче; раздельные значения дают
        // каждому металлу свой уровень отражения в одном и том же HDR.
        clone.envMapIntensity = /gold|brass|copper/.test(nm)
          ? 1.35
          : /chrome/.test(nm)
            ? 1.45
            : /steel|alu/.test(nm)
              ? 1.2
              : 1.1;

        mesh.material = clone;
        pickables.push(mesh);
      });

      model.traverse((child) => {
        const vec = child.userData?.explode as number[] | undefined;
        if (!vec) return;
        // GLTFLoader прогоняет имена через sanitizeNodeName и меняет пробелы на «_».
        // В модели пробелов кроме разделителя слов нет — возвращаем их обратно.
        const label = norm(child.name);
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

      // Габарит сборки: спокойная и раскрытая. Камера подбирает дистанцию так,
      // чтобы проекция всех деталей укладывалась в кадр целиком.
      const fitDir = camera.position.clone().sub(controls.target).normalize();

      const cornersAt = (state: number) => {
        apply(state);
        const pts: THREE.Vector3[] = [];
        for (const part of parts) {
          box.setFromObject(part.obj);
          if (box.isEmpty()) continue;
          for (let i = 0; i < 8; i++) {
            pts.push(
              new THREE.Vector3(
                i & 1 ? box.max.x : box.min.x,
                i & 2 ? box.max.y : box.min.y,
                i & 4 ? box.max.z : box.min.z,
              ),
            );
          }
        }
        return pts;
      };

      const fitDist = (pts: THREE.Vector3[]) => {
        const probe = camera.clone();
        probe.aspect = camera.aspect;
        probe.updateProjectionMatrix();
        let lo = 0.4;
        let hi = 3.2;
        for (let i = 0; i < 26; i++) {
          const mid = (lo + hi) / 2;
          probe.position.copy(controls.target).addScaledVector(fitDir, mid);
          probe.lookAt(controls.target);
          probe.updateMatrixWorld(true);
          let ok = true;
          for (const p of pts) {
            tmp.copy(p).project(probe);
            if (Math.abs(tmp.x) > 0.93 || Math.abs(tmp.y) > 0.93) {
              ok = false;
              break;
            }
          }
          if (ok) hi = mid;
          else lo = mid;
        }
        return THREE.MathUtils.clamp(hi, 0.5, 2.4);
      };

      DIST_CLOSED = fitDist(cornersAt(0)) * 0.84;
      DIST_OPEN = fitDist(cornersAt(1)) * 0.88;
      progress = 0;
      apply(0);
      progress = 0;

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

  // snap — выставить состояние сразу, без анимации: для ?explode из адреса и
  // для prefers-reduced-motion. Тяжёлая загрузка глушит тикер GSAP (lagSmoothing),
  // и твин, запущенный до неё, отстаёт на секунды.
  const setExploded = (next: boolean, snap = false) => {
    exploded = next;
    btn.textContent = next ? 'Собрать' : 'Разобрать';
    btn.setAttribute('aria-pressed', String(next));
    // в разобранном виде машина должна стоять неподвижно — иначе подписи уезжают
    if (next) controls.autoRotate = false;

    anim?.kill();
    if (snap || reduce) {
      progress = next ? 1 : 0;
      apply(progress);
    } else {
      const state = { v: progress };
      anim = gsap.to(state, {
        v: next ? 1 : 0,
        duration: 2.4,
        ease: 'none',
        onUpdate: () => {
          progress = state.v;
          apply(progress);
        },
      });
    }

    // Отъезжаем вместе с разборкой, но не отбираем управление у мыши.
    const dir = camera.position.clone().sub(controls.target).normalize();
    const cam = {
      d: camera.position.distanceTo(controls.target),
      y: controls.target.y,
    };
    gsap.to(cam, {
      d: next ? DIST_OPEN : DIST_CLOSED,
      y: next ? 0.2 : 0.2,
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
    const d0 = DIST_CLOSED;
    camera.position.copy(controls.target).addScaledVector(dir0, d0);
  }

  // ?explode в адресе — сразу открыть разобранную машину (для показа и проверок).
  if (new URLSearchParams(location.search).has('explode')) setExploded(true, true);

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
    // Постоянно показываем только смысловые узлы; остальные — по наведению.
    const base = Math.min(1, Math.max(0, (progress - 0.3) / 0.45));

    const pts: Part[] = [];
    const alpha = new Map<Part, number>();
    for (const part of parts) {
      const a = part.obj === hovered ? 1 : ALWAYS.has(part.label) ? base : 0;
      alpha.set(part, a);
      if (a <= 0.02) {
        part.el.style.opacity = '0';
        part.line.style.opacity = '0';
        part.dot.style.opacity = '0';
        continue;
      }
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
      const gap = 26;
      for (let i = 1; i < col.length; i++) {
        const min = col[i - 1].y + Math.max(gap, col[i - 1].h + 6);
        if (col[i].y < min) col[i].y = min;
      }
      let over = 0;
      const last = col[col.length - 1];
      if (last) over = Math.max(0, last.y + last.h / 2 - (size.h - 20));
      if (over > 0) for (const p of col) p.y -= over;
    }

    for (const p of pts) {
      const a = alpha.get(p) ?? 0;
      // Выноска пропорциональна ширине сцены: на узкой модели фиксированные 46 px
      // упирались подписью в корпус. У края сцены выноска укорачивается.
      const off = Math.round(THREE.MathUtils.clamp(size.w * 0.032, 28, 56));
      const pad = 10;
      let tipX = p.x + p.side * off;
      if (p.side > 0) tipX = Math.min(tipX, size.w - pad - p.w - 12);
      else tipX = Math.max(tipX, pad + p.w + 12);
      const tipY = p.y;
      const edgeX = tipX + p.side * 10;
      p.el.style.opacity = a.toFixed(3);
      p.el.style.transform = `translate(${Math.round(edgeX)}px, ${Math.round(tipY - p.h / 2)}px) translateX(${p.side < 0 ? '-100%' : '0'})`;

      p.line.setAttribute('x1', String(Math.round(edgeX)));
      p.line.setAttribute('y1', String(Math.round(tipY)));
      p.line.setAttribute('x2', String(Math.round(p.x + p.side * 7)));
      p.line.setAttribute('y2', String(Math.round(p.y)));
      p.line.style.opacity = String(a * 0.5);
      p.dot.setAttribute('cx', String(Math.round(p.x)));
      p.dot.setAttribute('cy', String(Math.round(p.y)));
      p.dot.style.opacity = String(a);
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

  // --- публичный интерфейс для сценария самодиагностики ---
  const pulse = (name: string, dur = 1500) => {
    const part = parts.find((p) => p.label === norm(name));
    if (!part) return;
    const t0 = performance.now();
    const step = (now: number) => {
      const k = Math.min(1, (now - t0) / dur);
      const w = Math.sin(Math.PI * k);
      part.obj.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (!mesh.isMesh) return;
        const m = mesh.material as THREE.MeshStandardMaterial;
        if (!m || !m.emissive) return;
        m.emissive.setHex(0xd8a24a);
        m.emissiveIntensity = 0.32 * w;
      });
      if (k < 1) requestAnimationFrame(step);
      else paint(part.obj, false);
    };
    requestAnimationFrame(step);
  };

  /** Навести камеру на деталь: список-оглавление в секции зовёт это. */
  const focus = (name: string) => {
    const part = parts.find((p) => p.label === norm(name));
    if (!part) return;
    box.setFromObject(part.obj);
    if (box.isEmpty()) return;
    box.getCenter(center);
    const dir = camera.position.clone().sub(controls.target).normalize();
    const span = Math.max(box.max.x - box.min.x, box.max.y - box.min.y, box.max.z - box.min.z);
    const d = THREE.MathUtils.clamp(
      (span * 2.6) / Math.sin((camera.fov * Math.PI) / 360),
      0.45,
      1.9,
    );
    gsap.to(controls.target, { x: center.x, y: center.y, z: center.z, duration: 0.7, ease: 'power2.out' });
    gsap.to(camera.position, {
      x: center.x + dir.x * d,
      y: center.y + dir.y * d,
      z: center.z + dir.z * d,
      duration: 0.7,
      ease: 'power2.out',
    });
    controls.autoRotate = false;
    pulse(name, 1400);
  };

  (root as HTMLElement & { __viewer?: unknown }).__viewer = {
    explode: (on: boolean) => setExploded(on),
    isExploded: () => exploded,
    pulse,
    focus,
  };
}




