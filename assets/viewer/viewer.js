import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const host = document.querySelector('#viewer');
const status = document.querySelector('#viewer-status');
const buttons = [...document.querySelectorAll('[data-action]')];
buttons.forEach(button => { button.disabled = true; });

async function start() {
  if (!host.dataset.model) {
    status.textContent = 'No GLB has been delivered yet. Current renders and files are available below.';
    return;
  }
  if (location.protocol === 'file:') {
    status.textContent = 'Serve this unpacked folder locally to view the model. Expand “Open this report offline” below for the command.';
    return;
  }
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setClearColor(0xe9e9e2);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1;
  const canvas = renderer.domElement;
  canvas.tabIndex = 0;
  canvas.setAttribute('aria-label', 'Interactive building model. Drag to orbit, scroll to zoom, arrow keys to pan.');
  host.append(canvas);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 10000);
  const controls = new OrbitControls(camera, canvas);
  controls.listenToKeyEvents(canvas);
  controls.addEventListener('change', () => renderer.render(scene, camera));
  scene.add(new THREE.HemisphereLight(0xf9f7ee, 0x8a9584, 1.5));
  const sun = new THREE.DirectionalLight(0xfff5dd, 2.5);
  sun.position.set(5, 8, 4);
  scene.add(sun);
  const fill = new THREE.DirectionalLight(0xd8e8ff, 0.8);
  fill.position.set(-5, 2, -4);
  scene.add(fill);
  new ResizeObserver(() => {
    const width = host.clientWidth;
    const height = host.clientHeight;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
    renderer.render(scene, camera);
  }).observe(host);

  const gltf = await new GLTFLoader().loadAsync(host.dataset.model);
  scene.add(gltf.scene);
  const bounds = new THREE.Box3().setFromObject(gltf.scene);
  if (bounds.isEmpty()) throw new Error('The exported model contains no visible geometry.');
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  const radius = Math.max(size.length() / 2, 0.01);
  camera.near = Math.max(radius / 10000, 0.0001);
  camera.far = radius * 100;
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.minDistance = radius * 0.05;
  controls.maxDistance = radius * 30;
  const fitAngle = Math.min(camera.fov * Math.PI / 180, 2 * Math.atan(Math.tan(camera.fov * Math.PI / 360) * camera.aspect));
  camera.position.copy(center).add(new THREE.Vector3(1, 0.65, 1).normalize().multiplyScalar(radius / Math.sin(fitAngle / 2) * 1.1));
  controls.update();
  controls.saveState();
  buttons.forEach(button => {
    button.disabled = false;
    button.addEventListener('click', () => {
      const offset = camera.position.clone().sub(controls.target);
      switch (button.dataset.action) {
        case 'left': offset.applyAxisAngle(new THREE.Vector3(0, 1, 0), -Math.PI / 12); break;
        case 'right': offset.applyAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI / 12); break;
        case 'in': offset.multiplyScalar(0.8); break;
        case 'out': offset.multiplyScalar(1.25); break;
        case 'reset': controls.reset(); return;
      }
      offset.clampLength(controls.minDistance, controls.maxDistance);
      camera.position.copy(controls.target).add(offset);
      controls.update();
    });
  });
  status.textContent = 'Model loaded. Drag to explore, or use the controls below.';
  host.dataset.loaded = 'true';
  renderer.render(scene, camera);
}

start().catch(error => {
  status.textContent = 'The 3D viewer could not open this model. Serve the unpacked folder locally and use a WebGL-capable browser. The render galleries and downloads remain available.';
  host.dataset.error = error.message;
  console.error('Model viewer:', error);
});
