import * as THREE from 'three';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { buildMachine, LAYOUT, type PartId } from '../scenes/machine';
import { INK } from '../scenes/machine';
import { PARTS } from '../data/parts';

/**
 * Сцена разборки. Прогресс пина (0…1) ведёт камеру, узлы и подписи.
 * Без WebGL и при prefers-reduced-motion остаётся статичный кадр: пин снят,
 * подписи выведены списком (см. разметку Anatomy.astro).
 */

gsap.registerPlugin(ScrollTrigger);

const smoothstep = (t: number) => {
  const x = Math.min(1, Math.max(0, t));
  return x * x * (3 - 2 * x);
};

/** Порог вылета узла: волны по две, как в parts.ts. */
function partProgress(p: number, wave: number) {
  const up = smoothstep((p - 0.14 - (wave - 1) * 0.045) / 0.3);
  const down = smoothstep((p - 0.72 - (wave - 1) * 0.03) / 0.22);
  return up * (1 - down);
}

const GAP = 46;
const TOP = 118;

export function initAnatomy() {
  const pin = document.querySelector<HTMLElement>('[data-anatomy-pin]');
  const stage = document.querySelector<HTMLElement>('[data-anatomy-stage]');
  const canvas = document.querySelector<HTMLCanvasElement>('[data-anatomy-canvas]');
  const labelHost = document.querySelector<HTMLElement>('[data-anatomy-labels]');
  const hint = document.querySelector<HTMLElement>('[data-anatomy-hint]');
  if (!pin || !stage || !canvas || !labelHost) return;

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  let renderer: THREE.WebGLRenderer;
  try {
    renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
    });
  } catch {
    pin.classList.add('is-static');
    return;
  }

  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearAlpha(0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;

  const scene = new THREE.Scene();

  const key = new THREE.DirectionalLight(0xffe6c4, 2.1);
  key.position.set(-46, 62, 54);
  const rim = new THREE.DirectionalLight(0xa9bcd6, 0.75);
  rim.position.set(38, 6, -46);
  scene.add(key, rim);

  const camera = new THREE.PerspectiveCamera(26, 1, 1, 400);
  const basePos = new THREE.Vector3(-23, 3.5, 97);
  const lookAt = new THREE.Vector3(0, 0.5, 0);
  camera.position.copy(basePos);
  camera.lookAt(lookAt);

  const machine = buildMachine();
  scene.add(machine.root);
  (window as unknown as Record<string, unknown>).__crema = { renderer, scene, camera, machine, INK };

  // Гаснет только корпус: внутренности должны читаться при разборке.
  const shellMat = INK.shellFill;
  const shellEdge = INK.shellEdge;
  shellMat.transparent = true;

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'anatomy__leaders');
  labelHost.appendChild(svg);

  interface LabelRef {
    id: PartId;
    part: (typeof PARTS)[number];
    el: HTMLDivElement;
    line: SVGLineElement;
    ly: number;
  }

  const labels: LabelRef[] = PARTS.map((part, i) => {
    const el = document.createElement('div');
    el.className = 'anatomy__label';
    el.dataset.side = part.side;
    el.innerHTML = `<span class="anatomy__label-idx">${String(i + 1).padStart(2, '0')}</span><span class="anatomy__label-name">${part.name}</span>`;
    labelHost.appendChild(el);

    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('class', 'anatomy__leader');
    svg.appendChild(line);

    return { id: part.id as PartId, part, el, line, ly: 0 };
  });

  const v = new THREE.Vector3();
  const size = { w: 1, h: 1 };

  const resize = () => {
    const r = stage.getBoundingClientRect();
    size.w = Math.max(1, r.width);
    size.h = Math.max(1, r.height);
    renderer.setSize(size.w, size.h, false);
    camera.aspect = size.w / size.h;
    camera.fov = size.w < 720 ? 34 : 26;
    camera.updateProjectionMatrix();
    svg.setAttribute('viewBox', `0 0 ${size.w} ${size.h}`);
  };

  let progress = 0;
  let targetProgress = 0;
  let visible = true;

  const frame = (p: number) => {
    // Камера отъезжает и поднимается, когда узлы расходятся.
    const e = smoothstep((p - 0.12) / 0.4) * (1 - smoothstep((p - 0.74) / 0.24));
    camera.position.set(basePos.x - 6 * e, basePos.y + 5 * e, basePos.z + 16 * e);
    camera.lookAt(lookAt);

    const anchors: { x: number; y: number; ref: LabelRef; pe: number }[] = [];

    for (const ref of labels) {
      const group = machine.parts[ref.id];
      const pe = partProgress(p, ref.part.wave);
      const s = machine.start[ref.id];

      const off = LAYOUT[ref.id];
      group.position.set(s.x + off[0] * pe, s.y + off[1] * pe, s.z + off[2] * pe);

      group.getWorldPosition(v);
      v.project(camera);
      anchors.push({
        x: (v.x * 0.5 + 0.5) * size.w,
        y: (-v.y * 0.5 + 0.5) * size.h,
        ref,
        pe,
      });
    }

    // Подписи в два столбца по краям: разводим по вертикали, чтобы не липли.
    const mid = size.w * 0.5;
    for (const side of ['l', 'r'] as const) {
      const col = anchors
        .filter((a) => (a.x < mid ? 'l' : 'r') === side)
        .sort((a, b) => a.y - b.y);
      const top = TOP;
      const bottom = size.h - 72;
      let y = top;
      for (const a of col) {
        y = Math.max(y, Math.min(a.y, bottom));
        a.ref.ly = y;
        y += GAP;
      }
      const over = (col[col.length - 1]?.ref.ly ?? 0) - bottom;
      if (over > 0) for (const a of col) a.ref.ly -= over;
    }

    for (const a of anchors) {
      const { ref, pe } = a;
      const left = a.x < mid;
      const side = left ? 'l' : 'r';
      if (ref.el.dataset.side !== side) ref.el.dataset.side = side;
      const lx = left ? 24 : size.w - 24;

      const opacity = smoothstep((pe - 0.18) / 0.3);

      ref.el.style.left = `${lx}px`;
      ref.el.style.top = `${ref.ly}px`;
      ref.el.style.opacity = String(opacity);
      ref.el.style.transform = left ? 'translateY(-50%) translateX(0)' : 'translateY(-50%) translateX(-100%)';

      ref.line.setAttribute('x1', String(left ? lx + 6 : lx - 6));
      ref.line.setAttribute('y1', String(ref.ly));
      ref.line.setAttribute('x2', String(a.x));
      ref.line.setAttribute('y2', String(a.y));
      ref.line.style.opacity = String(opacity);
    }

    shellMat.opacity = 1 - 0.9 * e;
    shellEdge.opacity = 0.9 * (1 - 0.6 * e);
    shellMat.depthWrite = shellMat.opacity > 0.92;

    if (hint) hint.style.opacity = String(1 - smoothstep(p / 0.04));

    if (visible) renderer.render(scene, camera);
  };

  resize();

  if (reduced) {
    pin.classList.add('is-static');
    frame(0);
    new ResizeObserver(() => {
      resize();
      frame(0);
    }).observe(stage);
    return;
  }

  ScrollTrigger.create({
    trigger: pin,
    start: 'top top',
    end: 'bottom bottom',
    scrub: true,
    onUpdate: (self) => {
      targetProgress = self.progress;
    },
  });

  new IntersectionObserver((entries) => {
    visible = entries[0]?.isIntersecting ?? true;
  }).observe(stage);

  new ResizeObserver(() => {
    resize();
    frame(progress);
  }).observe(stage);

  const tick = () => {
    progress += (targetProgress - progress) * 0.14;
    frame(Math.min(1, Math.max(0, progress)));
  };

  gsap.ticker.add(tick);
}
