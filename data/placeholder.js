export default function generate(THREE) {
  function fitToUnitCube(object) {
    const wrapper = new THREE.Group();
    wrapper.add(object);
    wrapper.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(wrapper);
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    if (!Number.isFinite(maxDim) || maxDim <= 0) throw new Error('Invalid bounds');
    const scale = 0.95 / maxDim;
    wrapper.scale.setScalar(scale);
    wrapper.position.copy(box.getCenter(new THREE.Vector3())).multiplyScalar(-scale);
    wrapper.updateMatrixWorld(true);
    return wrapper;
  }
  const root = new THREE.Group();
  const material = new THREE.MeshStandardMaterial({ color: __COLOR__, roughness: 0.6, metalness: 0.1 });
  root.add(new THREE.Mesh(new THREE.SphereGeometry(0.5, 48, 32), material));
  return fitToUnitCube(root);
}
