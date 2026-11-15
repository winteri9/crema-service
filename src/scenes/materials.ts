import * as THREE from 'three';

/**
 * Материалы машины. Источник: фото ref/hero.png — матовая сталь корпуса,
 * золотая лицевая панель, чёрное основание. Пересветов нет, всё PBR.
 * Один env-мап на всю сцену: отражения дают форму, не текстуры.
 */

const steel = new THREE.MeshStandardMaterial({
  color: 0xc4bdb3,
  metalness: 1,
  roughness: 0.28,
  envMapIntensity: 1.3,
});

export const MAT = {
  steel,
  /** Корпус: отдельный инстанс, потому что гаснет при разборке. */
  shell: steel.clone(),
  gold: new THREE.MeshStandardMaterial({
    color: 0xd3a869,
    metalness: 1,
    roughness: 0.22,
    envMapIntensity: 1.25,
  }),
  goldSoft: new THREE.MeshStandardMaterial({
    color: 0xc39a61,
    metalness: 1,
    roughness: 0.36,
    envMapIntensity: 1.1,
  }),
  dark: new THREE.MeshStandardMaterial({
    color: 0x16130f,
    metalness: 0.55,
    roughness: 0.52,
  }),
  glass: new THREE.MeshStandardMaterial({
    color: 0x0a0908,
    metalness: 0.25,
    roughness: 0.18,
    envMapIntensity: 0.9,
  }),
  copper: new THREE.MeshStandardMaterial({
    color: 0xa56a40,
    metalness: 1,
    roughness: 0.42,
  }),
};

export function disposeMaterials() {
  for (const m of Object.values(MAT)) m.dispose();
}
