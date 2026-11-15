import * as THREE from 'three';

/**
 * Студийное окружение для отражений. Источник света — фото ref/hero.png:
 * тёплый ключевой свет слева-сверху, холодная подсветка справа, глухая стена
 * сзади. Собирается один раз и живёт как scene.environment.
 */

function panel(
  scene: THREE.Scene,
  color: number,
  w: number,
  h: number,
  pos: [number, number, number],
  rot: [number, number, number] = [0, 0, 0],
  intensity = 1,
) {
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(w, h),
    new THREE.MeshBasicMaterial({
      color: new THREE.Color(color).multiplyScalar(intensity),
      side: THREE.DoubleSide,
    }),
  );
  mesh.position.set(...pos);
  mesh.rotation.set(...rot);
  scene.add(mesh);
  return mesh;
}

export function makeEnvironment(renderer: THREE.WebGLRenderer): THREE.Texture {
  const envScene = new THREE.Scene();

  // Комната: тёмная тёплая коробка.
  const room = new THREE.Mesh(
    new THREE.BoxGeometry(90, 64, 90),
    new THREE.MeshBasicMaterial({ color: 0x241c15, side: THREE.BackSide }),
  );
  envScene.add(room);

  // Ключ слева-сверху, тёплый.
  panel(envScene, 0xffd9a6, 30, 22, [-30, 16, 24], [0, Math.PI / 2.6, 0], 7.5);
  // Мягкий заполняющий спереди.
  panel(envScene, 0xc08a52, 26, 12, [0, 4, 40], [0, 0, 0], 1.8);
  // Узкая яркая полоса справа — даёт длинный блик по золоту.
  panel(envScene, 0xfff0d8, 5, 36, [30, 8, 4], [0, -Math.PI / 2, 0], 5.5);
  // Холодный рим сзади.
  panel(envScene, 0x38404c, 24, 26, [0, 10, -34], [0, Math.PI, 0], 1.6);
  // Потолок-софтбокс.
  panel(envScene, 0xffe4bd, 34, 34, [0, 29, 0], [-Math.PI / 2, 0, 0], 3.6);
  // Тёплый отсвет от столешницы.
  panel(envScene, 0x5a3a1e, 40, 20, [0, -18, 10], [Math.PI / 2, 0, 0], 1.6);

  const pmrem = new THREE.PMREMGenerator(renderer);
  pmrem.compileEquirectangularShader();
  const target = pmrem.fromScene(envScene, 0.02);
  pmrem.dispose();
  envScene.traverse((o) => {
    if (o instanceof THREE.Mesh) {
      o.geometry.dispose();
      (o.material as THREE.Material).dispose();
    }
  });

  return target.texture;
}
