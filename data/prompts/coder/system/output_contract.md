OUTPUT
- The scene holds raw JavaScript only: no Markdown fences, no prose. The module starts with `export default function generate(THREE) {` and ends with that function's closing `}`.
- This function is the only top-level statement: every constant, helper and class lives inside it. It is synchronous and returns a THREE.Group.
- Include this helper unchanged and end with `return fitToUnitCube(root);`; nothing touches root after that call:
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

VALIDATOR RULES
- No import, require, import(), other exports, async, await or Promise. Strict mode: declare every variable with const or let.
- Write THREE only as `THREE.Name`. Never alias, destructure, spread, store, return or pass it (`helper(THREE)`, `[THREE]`, `{ lib: THREE }`); nested helpers use it from the closure. No computed access on THREE, Math, Object, Array or Symbol (`THREE[name]`, `Math[fn]`). No `.constructor` or `.__proto__`.
- Allowed globals only: Math Number String Array Object Symbol JSON Map Set Boolean Error TypeError RangeError Infinity NaN undefined parseInt parseFloat isFinite isNaN BigInt ArrayBuffer DataView Int8Array Uint8Array Uint8ClampedArray Int16Array Uint16Array Int32Array Uint32Array Float32Array Float64Array BigInt64Array BigUint64Array. No console, arguments, RegExp, WeakMap, Intl.
- Forbidden names, also as your own variable names: eval Function setTimeout setInterval setImmediate queueMicrotask fetch XMLHttpRequest WebSocket document window navigator localStorage sessionStorage indexedDB OffscreenCanvas HTMLCanvasElement crypto Date performance Proxy Reflect WeakRef FinalizationRegistry SharedArrayBuffer Atomics Worker process module global globalThis self require (name a part `seatModule`, not `module`).
- Deterministic: no Math.random, Date, THREE.MathUtils.seededRandom or generateUUID. Derive variation from indices or this hash (0..1): `function hash2(i, j) { let h = (i * 374761393 + j * 668265263) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; }`
- THREE.Name must be one of: BufferGeometry BufferAttribute InterleavedBuffer InterleavedBufferAttribute Float32BufferAttribute Uint8BufferAttribute Uint16BufferAttribute Uint32BufferAttribute Int8BufferAttribute Int16BufferAttribute Int32BufferAttribute BoxGeometry SphereGeometry CylinderGeometry CapsuleGeometry ConeGeometry TorusGeometry TorusKnotGeometry PlaneGeometry CircleGeometry RingGeometry TetrahedronGeometry OctahedronGeometry DodecahedronGeometry IcosahedronGeometry PolyhedronGeometry ExtrudeGeometry LatheGeometry ShapeGeometry TubeGeometry EdgesGeometry WireframeGeometry MeshStandardMaterial MeshPhysicalMaterial MeshBasicMaterial PointsMaterial LineBasicMaterial LineDashedMaterial DataTexture Vector2 Vector3 Vector4 Matrix3 Matrix4 Quaternion Euler Box2 Box3 Sphere Plane Ray Line3 Triangle Spherical Cylindrical Color MathUtils Curve CurvePath Shape Path CatmullRomCurve3 CubicBezierCurve3 LineCurve3 QuadraticBezierCurve3 EllipseCurve ArcCurve LineCurve SplineCurve QuadraticBezierCurve CubicBezierCurve Object3D Group Mesh InstancedMesh Line LineSegments Points SRGBColorSpace LinearSRGBColorSpace NoColorSpace FrontSide BackSide DoubleSide NormalBlending AdditiveBlending SubtractiveBlending MultiplyBlending NoBlending NearestFilter LinearFilter NearestMipmapNearestFilter LinearMipmapNearestFilter NearestMipmapLinearFilter LinearMipmapLinearFilter RepeatWrapping ClampToEdgeWrapping MirroredRepeatWrapping RGBAFormat RGBFormat RGFormat RedFormat LuminanceFormat UnsignedByteType HalfFloatType FloatType StaticDrawUsage DynamicDrawUsage StreamDrawUsage.
  Everything else is rejected, including Scene, cameras, lights, loaders, Texture, CanvasTexture, ShaderMaterial, MeshPhongMaterial, MeshLambertMaterial, Sprite, SkinnedMesh, helpers, legacy THREE.Geometry / THREE.Math / BoxBufferGeometry, and add-ons (RoundedBoxGeometry, TextGeometry, mergeGeometries, CSG). No envMap, no morph targets.
- Budgets: vertices <= 250k (aim <= 150k); draw calls <= 200, each Mesh, Line, Points and InstancedMesh counts 1 (aim <= 120); depth <= 32; instances <= 50k; DataTexture data <= 4 MiB; literals <= 50 KB (never embed vertex tables, images or base64); <= 5 s and 256 MB.
- No NaN or Infinity and no throw: no division by a possible zero, clamp Math.acos / Math.asin arguments, no arithmetic on possibly undefined values, no zero or negative sizes, no direction between identical points.
- InstancedMesh: after the last setMatrixAt set `instanceMatrix.needsUpdate = true` and call `computeBoundingBox()` and `computeBoundingSphere()`.
