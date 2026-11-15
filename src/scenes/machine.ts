import * as THREE from 'three';

/**
 * Машина как техническая схема: плоская заливка + контурные линии.
 * Источник пропорций — ref/hero.png (21.5 × 36 × 17.5 см, серый кожух,
 * золотая лицевая панель, варочная группа, паровой кран, каплесборник).
 *
 * Почему схема, а не фотореализм: один кадр не даёт геометрии для 1:1, а
 * линия честно показывает устройство и не врёт светом. Узлы — отдельные
 * группы, их двигает разборка (src/scripts/anatomy.ts).
 */

export type PartId =
  | 'control'
  | 'group'
  | 'boiler'
  | 'pump'
  | 'steam'
  | 'portafilter'
  | 'tray'
  | 'tank';

export const MACHINE = { w: 21.5, h: 36, d: 17.5 };
const FACE = MACHINE.d / 2;

/** Заливки и линии: по одному материалу каждого тона на всю сцену. */
export const INK = {
  fillDark: new THREE.MeshBasicMaterial({ color: 0x14110d }),
  fillGold: new THREE.MeshBasicMaterial({ color: 0x8a5a1d }),
  fillSteel: new THREE.MeshBasicMaterial({ color: 0x4b463c }),
  edgeGold: new THREE.LineBasicMaterial({ color: 0xf0c98a, transparent: true, opacity: 0.95 }),
  edgeSteel: new THREE.LineBasicMaterial({ color: 0xb9ae9a, transparent: true, opacity: 0.65 }),
  /** Кожух гаснет при разборке — отдельные прозрачные материалы. */
  shellFill: new THREE.MeshBasicMaterial({ color: 0x4b463c, transparent: true, opacity: 1 }),
  shellEdge: new THREE.LineBasicMaterial({ color: 0xd8cdb8, transparent: true, opacity: 0.9 }),
};

function roundedRect(w: number, h: number, r: number) {
  const s = new THREE.Shape();
  const x = -w / 2;
  const y = -h / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y);
  s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r);
  s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h);
  s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r);
  s.quadraticCurveTo(x, y, x + r, y);
  return s;
}

function plate(w: number, h: number, d: number, r: number, bevel = 0.25) {
  const geo = new THREE.ExtrudeGeometry(
    roundedRect(w - bevel * 2, h - bevel * 2, Math.max(0.12, r - bevel)),
    {
      depth: Math.max(0.02, d - bevel * 2),
      bevelEnabled: true,
      bevelSize: bevel,
      bevelThickness: bevel,
      bevelSegments: 2,
      curveSegments: 14,
    },
  );
  geo.center();
  return geo;
}

type Tone = 'gold' | 'steel' | 'dark' | 'shell';

const FILL: Record<Tone, THREE.Material> = {
  gold: INK.fillGold,
  steel: INK.fillSteel,
  dark: INK.fillDark,
  shell: INK.shellFill,
};
const EDGE: Record<Tone, THREE.LineBasicMaterial> = {
  gold: INK.edgeGold,
  steel: INK.edgeSteel,
  dark: INK.edgeGold,
  shell: INK.shellEdge,
};

function part(
  parent: THREE.Object3D,
  geo: THREE.BufferGeometry,
  tone: Tone,
  pos: [number, number, number] = [0, 0, 0],
  rot: [number, number, number] = [0, 0, 0],
) {
  const m = new THREE.Mesh(geo, FILL[tone]);
  m.position.set(...pos);
  m.rotation.set(...rot);
  parent.add(m);

  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 32), EDGE[tone]);
  edges.position.copy(m.position);
  edges.rotation.copy(m.rotation);
  parent.add(edges);
  return m;
}

/** Куда узел уезжает при разборке (см, мировые оси). */
export const LAYOUT: Record<PartId, [number, number, number]> = {
  control: [2.4, 0, 5.2],
  group: [9.4, 3.4, 3.6],
  portafilter: [10.2, -3.2, 6.0],
  steam: [13.4, 2.2, 1.2],
  boiler: [-10.2, 2.8, -1.0],
  pump: [-11.4, -7.4, 1.0],
  tank: [-12.2, -1.0, -5.6],
  tray: [0.6, -13.2, 4.2],
};

export interface Machine {
  root: THREE.Group;
  parts: Record<PartId, THREE.Group>;
  shell: THREE.Group;
  start: Record<PartId, THREE.Vector3>;
}

export function buildMachine(): Machine {
  const root = new THREE.Group();
  const parts = {} as Record<PartId, THREE.Group>;
  const start = {} as Record<PartId, THREE.Vector3>;

  const shell = new THREE.Group();
  shell.name = 'shell';
  root.add(shell);

  const bodyH = 32;

  // Кожух: серый корпус со скруглениями по фото.
  part(shell, plate(MACHINE.w, bodyH, MACHINE.d, 2.8, 1.2), 'shell', [0, -0.4, 0]);

  // Плинтус.
  part(shell, plate(MACHINE.w - 0.6, MACHINE.d - 0.8, 1.1, 1.0, 0.3), 'gold', [0, -17.0, 0], [
    Math.PI / 2,
    0,
    0,
  ]);

  // Площадка подогрева чашек и прутья.
  part(shell, plate(MACHINE.w - 1.6, MACHINE.d - 2.4, 0.7, 0.9, 0.24), 'steel', [0, 15.0, -0.4], [
    Math.PI / 2,
    0,
    0,
  ]);
  for (let i = 0; i < 3; i++) {
    part(shell, plate(MACHINE.w - 5.2, 0.24, 0.24, 0.12, 0.07), 'gold', [0, 15.7, -4.6 + i * 4.2]);
  }

  // --- 01 панель управления: золотая плита в кожухе ---
  const control = new THREE.Group();
  control.name = 'control';
  root.add(control);
  parts.control = control;

  const fz = FACE + 0.2;

  part(control, plate(17.6, bodyH - 4.6, 0.5, 2.0, 0.18), 'gold', [0, -0.8, fz]);

  // Дисплей.
  part(control, plate(1.0, 5.6, 0.16, 0.3, 0.05), 'dark', [-5.4, 2.6, fz + 0.3]);

  // Кнопки.
  for (const x of [-5.4, -3.3]) {
    part(control, new THREE.CylinderGeometry(0.66, 0.66, 0.3, 22), 'gold', [x, 10.2, fz + 0.26], [
      Math.PI / 2,
      0,
      0,
    ]);
  }

  // Клавиши снизу.
  for (let i = 0; i < 3; i++) {
    part(control, plate(1.7, 0.6, 0.14, 0.18, 0.05), 'gold', [-4.9 + i * 2.1, -8.4, fz + 0.3]);
  }

  // --- 02 варочная группа ---
  const group = new THREE.Group();
  group.name = 'group';
  root.add(group);
  parts.group = group;

  part(group, new THREE.CylinderGeometry(3.0, 3.0, 1.6, 48), 'gold', [1.6, 4.4, fz + 0.8], [
    Math.PI / 2,
    0,
    0,
  ]);
  part(group, new THREE.CylinderGeometry(3.4, 3.4, 0.34, 48), 'gold', [1.6, 4.4, fz + 1.7], [
    Math.PI / 2,
    0,
    0,
  ]);
  part(group, new THREE.CylinderGeometry(2.35, 2.35, 0.3, 40), 'dark', [1.6, 4.4, fz + 1.9], [
    Math.PI / 2,
    0,
    0,
  ]);
  // Рычаг группы.
  part(group, new THREE.CylinderGeometry(0.34, 0.34, 3.0, 14), 'gold', [1.6, 7.7, fz + 1.0], [
    0,
    0,
    Math.PI / 2.15,
  ]);

  // --- 03 держатель фильтра ---
  const portafilter = new THREE.Group();
  portafilter.name = 'portafilter';
  root.add(portafilter);
  parts.portafilter = portafilter;

  part(portafilter, new THREE.CylinderGeometry(2.75, 2.75, 1.3, 48), 'gold', [1.6, -1.5, fz + 1.2], [
    Math.PI / 2,
    0,
    0,
  ]);
  part(portafilter, new THREE.CylinderGeometry(2.4, 2.4, 0.34, 40), 'dark', [1.6, -1.5, fz + 1.9], [
    Math.PI / 2,
    0,
    0,
  ]);

  const handle = new THREE.Group();
  handle.position.set(1.6, -1.8, fz + 2.1);
  handle.rotation.set(0.92, 0, 0.16);
  portafilter.add(handle);
  part(handle, new THREE.CylinderGeometry(0.52, 0.74, 6.2, 18), 'dark', [0, 0, 3.0], [
    Math.PI / 2,
    0,
    0,
  ]);

  // --- 04 бойлер ---
  const boiler = new THREE.Group();
  boiler.name = 'boiler';
  root.add(boiler);
  parts.boiler = boiler;
  part(boiler, new THREE.CylinderGeometry(4.2, 4.2, 10.5, 36), 'gold', [0, 2.6, -2.2], [
    Math.PI / 2,
    0,
    0,
  ]);
  part(boiler, new THREE.CylinderGeometry(0.95, 0.95, 3.2, 16), 'steel', [5.2, 2.6, -2.2], [
    0,
    0,
    Math.PI / 2,
  ]);

  // --- 05 помпа ---
  const pump = new THREE.Group();
  pump.name = 'pump';
  root.add(pump);
  parts.pump = pump;
  part(pump, new THREE.CylinderGeometry(1.9, 1.9, 4.4, 26), 'steel', [-4.6, -8.8, -3.2], [
    0,
    0,
    Math.PI / 2,
  ]);
  part(pump, new THREE.CylinderGeometry(1.0, 1.0, 1.8, 16), 'gold', [-7.4, -8.8, -3.2], [
    0,
    0,
    Math.PI / 2,
  ]);

  // --- 06 паровой кран ---
  const steam = new THREE.Group();
  steam.name = 'steam';
  root.add(steam);
  parts.steam = steam;
  const curve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(8.4, 5.4, fz - 0.6),
    new THREE.Vector3(9.9, 2.6, fz + 1.4),
    new THREE.Vector3(10.2, -2.0, fz + 1.9),
    new THREE.Vector3(10.0, -6.6, fz + 1.5),
  ]);
  part(steam, new THREE.TubeGeometry(curve, 56, 0.34, 10, false), 'gold');
  part(steam, new THREE.SphereGeometry(0.78, 18, 12), 'gold', [8.4, 5.6, fz - 0.6]);
  part(steam, new THREE.CylinderGeometry(0.46, 0.62, 1.1, 14), 'gold', [10.0, -7.2, fz + 1.5]);

  // --- 07 каплесборник ---
  const tray = new THREE.Group();
  tray.name = 'tray';
  root.add(tray);
  parts.tray = tray;
  part(tray, plate(16.2, 4.6, 0.5, 0.7, 0.16), 'gold', [0, -15.0, fz + 0.55], [Math.PI / 2, 0, 0]);
  for (let i = 0; i < 5; i++) {
    part(tray, plate(13.2, 0.26, 0.26, 0.1, 0.05), 'dark', [0, -14.95, fz + 0.32 + i * 0.72]);
  }

  // --- 08 бак для воды ---
  const tank = new THREE.Group();
  tank.name = 'tank';
  root.add(tank);
  parts.tank = tank;
  part(tank, plate(8.6, bodyH - 7, 6.6, 1.0, 0.28), 'steel', [-3.4, -0.8, -FACE + 1.6]);

  for (const id of Object.keys(parts) as PartId[]) {
    start[id] = parts[id].position.clone();
  }

  return { root, parts, shell, start };
}
