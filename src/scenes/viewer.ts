import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { gsap } from 'gsap';

/**
 * Просмотрщик машины: GLB из Blender, орбита, разборка по кнопке,
 * подсветка узла под курсором и подписи.
 *
 * Контракт с моделью: узлы верхнего уровня названы Panel_Front, Group_Head,
 * Water_Tank и т.д.; вектор разборки приходит в userData.explode
 * (массив трёх чисел в метрах, в системе координат модели).
 */

type Node = {
  obj: THREE.Object3D;
  rest: THREE.Vector3;
  vector: THREE.Vector3;
  name: string;
  label: string;
  el: HTMLElement;
  h: number;
};

/** Имя узла в GLB → подпись на сайте. */
const LABELS: Record<string, string> = {
  Control_Panel: 'Панель управления',
  Group_Head: 'Варочная группа',
  Portafilter: 'Держатель фильтра',
  Brewing_Unit: 'Заварочный блок',
  Boiler: 'Бойлер',
  Pump: 'Помпа',
  Steam_Wand: 'Паровой кран',
  Water_Tank: 'Бак для воды',
  Bean_Hopper: 'Контейнер для зёрен',
  Drip_Tray: 'Каплесборник',
  Panel_Top: 'Площадка подогрева',
  Shell: 'Корпус',
};

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
  renderer.toneMappingExposure = 1.35;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 20);
  camera.position.set(0.66, 0.5, 0.82);

  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 1.15;

  const key = new THREE.DirectionalLight(0xfff1e0, 3.4);
  key.position.set(0.8, 1.1, 1.0);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xffe0b4, 2.6);
  rim.position.set(-0.9, 0.6, -1.0);
  scene.add(rim);
  const fill = new THREE.DirectionalLight(0xd9c7ae, 1.4);
  fill.position.set(-0.6, 0.2, 1.2);
  scene.add(fill);

  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.075;
  controls.enablePan = false;
  controls.minDistance = 0.5;
  controls.maxDistance = 1.8;
  controls.minPolarAngle = Math.PI * 0.16;
  controls.maxPolarAngle = Math.PI * 0.6;
  controls.target.set(0, 0.21, 0);
  controls.autoRotate = !reduce;
  controls.autoRotateSpeed = 0.45;
  controls.addEventListener('start', () => {
    controls.autoRotate = false;
  });

  const machine = new THREE.Group();
  scene.add(machine);

  const nodes: Node[] = [];
  const pickables: THREE.Mesh[] = [];
  let hovered: THREE.Mesh | null = null;
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
  };
  resize();
  new ResizeObserver(resize).observe(stage);

  const loader = new GLTFLoader();
  loader.load(
    new URL('model/machine.glb', document.baseURI).href,
    (gltf) => {
      const model = gltf.scene;
      box.setFromObject(model);
      const s = 0.46 / Math.max(box.max.x - box.min.x, box.max.y - box.min.y, box.max.z - box.min.z);
      model.scale.setScalar(s);
      box.setFromObject(model);
      center.set((box.min.x + box.max.x) / 2, 0, (box.min.z + box.max.z) / 2);
      model.position.sub(new THREE.Vector3(center.x, box.min.y, center.z));
      machine.add(model);

      model.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (!mesh.isMesh) return;
        const src = mesh.material as THREE.MeshStandardMaterial;
        mesh.material = src.clone();
        pickables.push(mesh);
      });

      model.traverse((child) => {
        const vec = child.userData?.explode as number[] | undefined;
        const label = LABELS[child.name];
        if (!vec || !label) return;
        const el = document.createElement('span');
        el.className = 'viewer__label';
        el.textContent = label;
        el.style.opacity = '0';
        labelHost.appendChild(el);
        nodes.push({
          obj: child,
          rest: child.position.clone(),
          // Вектор в метрах: делим на масштаб, чтобы в локальных координатах он давал ту же длину.
          vector: new THREE.Vector3(vec[0], vec[1], vec[2]).multiplyScalar(1 / s),
          name: child.name,
          label,
          el,
          h: 0,
        });
      });

      // Высоту подписи запоминаем один раз, чтобы не мерить каждый кадр.
      nodes.forEach((n) => {
        n.h = n.el.getBoundingClientRect().height || 22;
      });

      btn.disabled = false;
      root.classList.add('is-ready');
      ready = true;
      apply();
    },
    undefined,
    () => {
      root.classList.add('is-static');
    },
  );

  const apply = () => {
    for (const n of nodes) {
      n.obj.position.set(
        n.rest.x + n.vector.x * progress,
        n.rest.y + n.vector.y * progress,
        n.rest.z + n.vector.z * progress,
      );
    }
  };

  const setExploded = (next: boolean) => {
    exploded = next;
    btn.textContent = next ? 'Собрать' : 'Разобрать';
    btn.setAttribute('aria-pressed', String(next));
    const state = { v: progress };
    gsap.killTweensOf(state);
    gsap.to(state, {
      v: next ? 1 : 0,
      duration: reduce ? 0 : 1.15,
      ease: 'power3.inOut',
      onUpdate: () => {
        progress = state.v;
        apply();
      },
    });

    // Отъезжаем вместе с разборкой, но не отбираем управление у мыши.
    const dir = camera.position.clone().sub(controls.target).normalize();
    const dist = {
      d: camera.position.distanceTo(controls.target),
      y: controls.target.y,
    };
    gsap.to(dist, {
      d: (size.w / size.h < 1 ? (next ? 1.95 : 1.18) : next ? 1.5 : 0.86),
      y: next ? 0.06 : 0.21,
      duration: reduce ? 0 : 1.15,
      ease: 'power3.inOut',
      onUpdate: () => {
        controls.target.y = dist.y;
        camera.position.copy(controls.target).addScaledVector(dir, dist.d);
      },
    });
  };

  btn.addEventListener('click', () => setExploded(!exploded));

  // Стартовый кадр: отъезжаем на дистанцию, зависящую от аспекта сцены.
  {
    const dir0 = camera.position.clone().sub(controls.target).normalize();
    const d0 = size.w / size.h < 1 ? 1.22 : 1.0;
    camera.position.copy(controls.target).addScaledVector(dir0, d0);
  }

  // ?explode в адресе — сразу открыть разобранную машину (для показа и проверок).
  if (new URLSearchParams(location.search).has('explode')) setExploded(true);

  // --- подсветка ------------------------------------------------------------

  const ray = new THREE.Raycaster();
  const pointer = new THREE.Vector2();

  const hoverOff = () => {
    if (!hovered) return;
    const m = hovered.material as THREE.MeshStandardMaterial;
    m.emissive.setHex(0x000000);
    m.emissiveIntensity = 0;
    hovered = null;
    canvas.style.cursor = 'grab';
  };

  canvas.addEventListener('pointermove', (ev) => {
    if (!ready) return;
    const r = canvas.getBoundingClientRect();
    pointer.x = ((ev.clientX - r.left) / r.width) * 2 - 1;
    pointer.y = -((ev.clientY - r.top) / r.height) * 2 + 1;
    ray.setFromCamera(pointer, camera);
    const hit = ray.intersectObjects(pickables, false)[0];
    const mesh = (hit?.object as THREE.Mesh) ?? null;
    if (mesh === hovered) return;
    hoverOff();
    if (mesh) {
      hovered = mesh;
      const m = mesh.material as THREE.MeshStandardMaterial;
      m.emissive.setHex(0x8a5a1d);
      m.emissiveIntensity = 0.35;
      canvas.style.cursor = 'pointer';
    }
  });
  canvas.addEventListener('pointerleave', hoverOff);

  // --- кадр -----------------------------------------------------------------

  const placed: { n: Node; x: number; y: number }[] = [];

  const placeLabels = () => {
    placed.length = 0;
    for (const n of nodes) {
      box.setFromObject(n.obj);
      box.getCenter(center);
      tmp.copy(center).project(camera);
      if (tmp.z > 1) continue;
      placed.push({
        n,
        x: (tmp.x * 0.5 + 0.5) * size.w,
        y: (-tmp.y * 0.5 + 0.5) * size.h,
      });
    }

    // Разводим подписи по вертикали, чтобы не слипались.
    placed.sort((a, b) => a.y - b.y);
    const gap = 26;
    for (let i = 1; i < placed.length; i++) {
      const prev = placed[i - 1];
      const cur = placed[i];
      const min = prev.y + Math.max(prev.n.h, gap);
      if (cur.y < min) cur.y = min;
    }

    const alpha = Math.min(1, Math.max(0, (progress - 0.35) / 0.4));
    for (const p of placed) {
      const el = p.n.el;
      el.style.opacity = alpha.toFixed(3);
      const w = el.offsetWidth || 140;
      // У правого края разворачиваем подпись влево.
      const flip = p.x + w + 64 > size.w;
      el.dataset.flip = flip ? '1' : '0';
      const dx = flip ? -34 : 34;
      el.style.transform = `translate(${Math.round(p.x)}px, ${Math.round(p.y - p.n.h / 2)}px) translateX(${flip ? 'calc(-100% - 34px)' : '34px'})`;
      void dx;
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
