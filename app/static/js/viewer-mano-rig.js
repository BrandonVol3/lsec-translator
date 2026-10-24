/**
 * viewer-mano-rig.js
 * Topología paramétrica MANO M(β, θ), ensamblaje 3D de 21 keypoints + 16 gimbals SO(3)
 * y utilidades matemáticas de telemetría para el visor 1:1 (/viewer).
 */

import * as THREE from 'three';

export const FINGER_COLORS_HEX = {
  wrist: 0x38bdf8,
  Thumb: 0xf59e0b,
  Index: 0x6366f1,
  Middle: 0x10b981,
  Ring: 0xa855f7,
  Little: 0xec4899,
};

export const FINGER_COLORS_CSS = {
  wrist: '#38bdf8',
  Thumb: '#f59e0b',
  Index: '#6366f1',
  Middle: '#10b981',
  Ring: '#a855f7',
  Little: '#ec4899',
};

export const MANO_JOINT_DEFS = [
  { id: 'R_glob', kp: 'J0', suffix: 'Hand', label: 'Hand (Muñeca)', finger: 'wrist' },
  { id: 'θ_01', kp: 'J5', suffix: 'IndexProximal', label: 'IndexProximal (MCP)', finger: 'Index' },
  { id: 'θ_02', kp: 'J6', suffix: 'IndexIntermediate', label: 'IndexInterm. (PIP)', finger: 'Index' },
  { id: 'θ_03', kp: 'J7', suffix: 'IndexDistal', label: 'IndexDistal (DIP)', finger: 'Index' },
  { id: 'θ_04', kp: 'J9', suffix: 'MiddleProximal', label: 'MiddleProximal (MCP)', finger: 'Middle' },
  { id: 'θ_05', kp: 'J10', suffix: 'MiddleIntermediate', label: 'MiddleInterm. (PIP)', finger: 'Middle' },
  { id: 'θ_06', kp: 'J11', suffix: 'MiddleDistal', label: 'MiddleDistal (DIP)', finger: 'Middle' },
  { id: 'θ_07', kp: 'J17', suffix: 'LittleProximal', label: 'LittleProximal (MCP)', finger: 'Little' },
  { id: 'θ_08', kp: 'J18', suffix: 'LittleIntermediate', label: 'LittleInterm. (PIP)', finger: 'Little' },
  { id: 'θ_09', kp: 'J19', suffix: 'LittleDistal', label: 'LittleDistal (DIP)', finger: 'Little' },
  { id: 'θ_10', kp: 'J13', suffix: 'RingProximal', label: 'RingProximal (MCP)', finger: 'Ring' },
  { id: 'θ_11', kp: 'J14', suffix: 'RingIntermediate', label: 'RingInterm. (PIP)', finger: 'Ring' },
  { id: 'θ_12', kp: 'J15', suffix: 'RingDistal', label: 'RingDistal (DIP)', finger: 'Ring' },
  { id: 'θ_13', kp: 'J1', suffix: 'ThumbMetacarpal', label: 'ThumbMetacarp. (CMC)', finger: 'Thumb' },
  { id: 'θ_14', kp: 'J2', suffix: 'ThumbProximal', label: 'ThumbProximal (MCP)', finger: 'Thumb' },
  { id: 'θ_15', kp: 'J3', suffix: 'ThumbDistal', label: 'ThumbDistal (IP)', finger: 'Thumb' },
];

export const FINGER_CHAINS = [
  { name: 'Thumb', bones: ['ThumbMetacarpal', 'ThumbProximal', 'ThumbDistal'], kpIds: [1, 2, 3, 4], radii: [0.0115, 0.0098, 0.0082, 0.0062] },
  { name: 'Index', bones: ['IndexProximal', 'IndexIntermediate', 'IndexDistal'], kpIds: [5, 6, 7, 8], radii: [0.0102, 0.0086, 0.0072, 0.0055] },
  { name: 'Middle', bones: ['MiddleProximal', 'MiddleIntermediate', 'MiddleDistal'], kpIds: [9, 10, 11, 12], radii: [0.0106, 0.0088, 0.0074, 0.0056] },
  { name: 'Ring', bones: ['RingProximal', 'RingIntermediate', 'RingDistal'], kpIds: [13, 14, 15, 16], radii: [0.0098, 0.0082, 0.0068, 0.0052] },
  { name: 'Little', bones: ['LittleProximal', 'LittleIntermediate', 'LittleDistal'], kpIds: [17, 18, 19, 20], radii: [0.0088, 0.0074, 0.0062, 0.0048] },
];

export const LSEC_REST_ROTATIONS = {
  hips: [0.0, 0.0, 0.0, 1.0],
  spine: [0.0, 0.0, 0.0, 1.0],
  chest: [0.0, 0.0, 0.0, 1.0],
  neck: [0.0, 0.0, 0.0, 1.0],
  head: [0.0, 0.0, 0.0, 1.0],
  leftShoulder: [0.0, 0.0, 0.0, 1.0],
  leftUpperArm: [0.004336, -0.049058, -0.641077, 0.765895],
  leftLowerArm: [0.065695, -0.087499, -0.029961, 0.993544],
  leftHand: [0.0, 0.0, 0.0, 1.0],
  rightShoulder: [0.0, 0.0, 0.0, 1.0],
  rightUpperArm: [0.004336, 0.049058, 0.641077, 0.765895],
  rightLowerArm: [0.065695, 0.087499, 0.029961, 0.993544],
  rightHand: [0.0, 0.0, 0.0, 1.0],
  leftThumbMetacarpal: [-0.00911, -0.086678, -0.104131, 0.990737],
  leftThumbProximal: [0.0, 0.0, -0.121869, 0.992546],
  leftThumbDistal: [0.0, 0.0, -0.104528, 0.994522],
  leftIndexProximal: [0.0, 0.0, -0.173648, 0.984808],
  leftIndexIntermediate: [0.0, 0.0, -0.241922, 0.970296],
  leftIndexDistal: [0.0, 0.0, -0.121869, 0.992546],
  leftMiddleProximal: [0.0, 0.0, -0.207912, 0.978148],
  leftMiddleIntermediate: [0.0, 0.0, -0.275637, 0.961262],
  leftMiddleDistal: [0.0, 0.0, -0.139173, 0.990268],
  leftRingProximal: [0.0, 0.0, -0.241922, 0.970296],
  leftRingIntermediate: [0.0, 0.0, -0.309017, 0.951057],
  leftRingDistal: [0.0, 0.0, -0.156434, 0.987688],
  leftLittleProximal: [0.0, 0.0, -0.275637, 0.961262],
  leftLittleIntermediate: [0.0, 0.0, -0.34202, 0.939693],
  leftLittleDistal: [0.0, 0.0, -0.173648, 0.984808],
  rightThumbMetacarpal: [-0.00911, 0.086678, 0.104131, 0.990737],
  rightThumbProximal: [0.0, 0.0, 0.121869, 0.992546],
  rightThumbDistal: [0.0, 0.0, 0.104528, 0.994522],
  rightIndexProximal: [0.0, 0.0, 0.173648, 0.984808],
  rightIndexIntermediate: [0.0, 0.0, 0.241922, 0.970296],
  rightIndexDistal: [0.0, 0.0, 0.121869, 0.992546],
  rightMiddleProximal: [0.0, 0.0, 0.207912, 0.978148],
  rightMiddleIntermediate: [0.0, 0.0, 0.275637, 0.961262],
  rightMiddleDistal: [0.0, 0.0, 0.139173, 0.990268],
  rightRingProximal: [0.0, 0.0, 0.241922, 0.970296],
  rightRingIntermediate: [0.0, 0.0, 0.309017, 0.951057],
  rightRingDistal: [0.0, 0.0, 0.156434, 0.987688],
  rightLittleProximal: [0.0, 0.0, 0.275637, 0.961262],
  rightLittleIntermediate: [0.0, 0.0, 0.34202, 0.939693],
  rightLittleDistal: [0.0, 0.0, 0.173648, 0.984808],
};

export function applyLSECDefaultRestPose(targetVrm) {
  if (!targetVrm?.humanoid) return;
  const humanoid = targetVrm.humanoid;
  for (const [boneName, q] of Object.entries(LSEC_REST_ROTATIONS)) {
    const boneNode = humanoid.getNormalizedBoneNode(boneName);
    if (boneNode) boneNode.quaternion.set(q[0], q[1], q[2], q[3]);
  }
}

export const RING_SIDES = 8;

export function buildParametricManoSkinTopology() {
  const totalVerts = 23 * RING_SIDES + 5;
  const positions = new Float32Array(totalVerts * 3);
  const indices = [];

  const addTubeIndices = (ringA, ringB) => {
    const baseA = ringA * RING_SIDES;
    const baseB = ringB * RING_SIDES;
    for (let s = 0; s < RING_SIDES; s++) {
      const sNext = (s + 1) % RING_SIDES;
      const a0 = baseA + s, a1 = baseA + sNext;
      const b0 = baseB + s, b1 = baseB + sNext;
      indices.push(a0, b0, a1);
      indices.push(a1, b0, b1);
    }
  };

  addTubeIndices(0, 1);
  addTubeIndices(1, 2);

  for (let f = 0; f < 5; f++) {
    const rStart = 3 + f * 4;
    addTubeIndices(rStart, rStart + 1);
    addTubeIndices(rStart + 1, rStart + 2);
    addTubeIndices(rStart + 2, rStart + 3);
    const tipIdx = 23 * RING_SIDES + f;
    const lastRingBase = (rStart + 3) * RING_SIDES;
    for (let s = 0; s < RING_SIDES; s++) {
      const sNext = (s + 1) % RING_SIDES;
      indices.push(lastRingBase + s, tipIdx, lastRingBase + sNext);
    }
  }

  for (let f = 1; f < 4; f++) {
    const rA = (3 + f * 4) * RING_SIDES;
    const rB = (3 + (f + 1) * 4) * RING_SIDES;
    for (let s = 0; s < RING_SIDES; s++) {
      const sNext = (s + 1) % RING_SIDES;
      indices.push(rA + s, rB + s, rA + sNext);
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setIndex(indices);
  geo.computeVertexNormals();
  return geo;
}

export function createGimbalRing(radius, colorHex) {
  const group = new THREE.Group();
  const makeCircle = (axis, col) => {
    const pts = [];
    const segs = 28;
    for (let i = 0; i <= segs; i++) {
      const a = (i / segs) * Math.PI * 2;
      if (axis === 'x') pts.push(new THREE.Vector3(0, Math.cos(a) * radius, Math.sin(a) * radius));
      if (axis === 'y') pts.push(new THREE.Vector3(Math.cos(a) * radius, 0, Math.sin(a) * radius));
      if (axis === 'z') pts.push(new THREE.Vector3(Math.cos(a) * radius, Math.sin(a) * radius, 0));
    }
    const g = new THREE.BufferGeometry().setFromPoints(pts);
    const m = new THREE.LineBasicMaterial({ color: col, depthTest: false, transparent: true, opacity: 0.78 });
    return new THREE.Line(g, m);
  };
  group.add(makeCircle('x', 0xef4444));
  group.add(makeCircle('y', 0x22c55e));
  group.add(makeCircle('z', colorHex || 0x38bdf8));
  group.renderOrder = 1002;
  return group;
}

export function createCompleteManoHandAssembly(targetScene) {
  const root = new THREE.Group();
  const meshGroup = new THREE.Group();
  const rigGroup = new THREE.Group();
  const basisGroup = new THREE.Group();
  root.add(meshGroup, rigGroup, basisGroup);
  targetScene.add(root);

  const skinGeo = buildParametricManoSkinTopology();
  const skinSurfaceMat = new THREE.MeshPhongMaterial({
    color: 0x0284c7,
    emissive: 0x0c4a6e,
    specular: 0x38bdf8,
    shininess: 80,
    transparent: true,
    opacity: 0.28,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const skinWireMat = new THREE.MeshBasicMaterial({
    color: 0x38bdf8,
    wireframe: true,
    transparent: true,
    opacity: 0.62,
    depthTest: false,
  });
  const skinSurfaceMesh = new THREE.Mesh(skinGeo, skinSurfaceMat);
  const skinWireMesh = new THREE.Mesh(skinGeo, skinWireMat);
  skinSurfaceMesh.renderOrder = 990;
  skinWireMesh.renderOrder = 991;
  meshGroup.add(skinSurfaceMesh, skinWireMesh);

  const spheres = [];
  const sphereGeo = new THREE.SphereGeometry(0.0052, 14, 14);
  const wristGeo = new THREE.SphereGeometry(0.0082, 16, 16);

  for (let i = 0; i < 21; i++) {
    let color = FINGER_COLORS_HEX.wrist;
    if (i >= 1 && i <= 4) color = FINGER_COLORS_HEX.Thumb;
    else if (i >= 5 && i <= 8) color = FINGER_COLORS_HEX.Index;
    else if (i >= 9 && i <= 12) color = FINGER_COLORS_HEX.Middle;
    else if (i >= 13 && i <= 16) color = FINGER_COLORS_HEX.Ring;
    else if (i >= 17 && i <= 20) color = FINGER_COLORS_HEX.Little;

    const mat = new THREE.MeshBasicMaterial({ color, depthTest: false, transparent: true, opacity: 0.96 });
    const mesh = new THREE.Mesh(i === 0 ? wristGeo : sphereGeo, mat);
    mesh.renderOrder = 999;
    rigGroup.add(mesh);
    spheres.push(mesh);
  }

  const gimbalIndices = [0, 1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15, 17, 18, 19];
  const gimbals = {};
  for (const kpIdx of gimbalIndices) {
    const r = kpIdx === 0 ? 0.022 : (kpIdx % 4 === 1 ? 0.011 : 0.008);
    const g = createGimbalRing(r, 0x38bdf8);
    rigGroup.add(g);
    gimbals[kpIdx] = g;
  }

  const segments = [
    [0, 1, 'Thumb'], [1, 2, 'Thumb'], [2, 3, 'Thumb'], [3, 4, 'Thumb'],
    [0, 5, 'Index'], [5, 6, 'Index'], [6, 7, 'Index'], [7, 8, 'Index'],
    [0, 9, 'Middle'], [9, 10, 'Middle'], [10, 11, 'Middle'], [11, 12, 'Middle'],
    [0, 13, 'Ring'], [13, 14, 'Ring'], [14, 15, 'Ring'], [15, 16, 'Ring'],
    [0, 17, 'Little'], [17, 18, 'Little'], [18, 19, 'Little'], [19, 20, 'Little'],
    [1, 5, 'wrist'], [5, 9, 'wrist'], [9, 13, 'wrist'], [13, 17, 'wrist'],
  ];

  const cylinders = [];
  const cylGeo = new THREE.CylinderGeometry(0.0022, 0.0022, 1, 8);
  cylGeo.translate(0, 0.5, 0);
  cylGeo.rotateX(Math.PI / 2);

  for (const [a, b, fname] of segments) {
    const mat = new THREE.MeshBasicMaterial({
      color: FINGER_COLORS_HEX[fname],
      depthTest: false,
      transparent: true,
      opacity: fname === 'wrist' ? 0.55 : 0.92,
    });
    const cyl = new THREE.Mesh(cylGeo, mat);
    cyl.renderOrder = 998;
    rigGroup.add(cyl);
    cylinders.push({ mesh: cyl, a, b });
  }

  const arrowFm = new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(), 0.095, 0x10b981, 0.018, 0.010);
  const arrowTm = new THREE.ArrowHelper(new THREE.Vector3(0, 1, 0), new THREE.Vector3(), 0.085, 0xf59e0b, 0.018, 0.010);
  const arrowNm = new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1), new THREE.Vector3(), 0.085, 0x38bdf8, 0.018, 0.010);
  [arrowFm, arrowTm, arrowNm].forEach(arr => {
    arr.line.material.depthTest = false;
    arr.cone.material.depthTest = false;
    arr.renderOrder = 1005;
    basisGroup.add(arr);
  });

  return {
    root,
    meshGroup,
    rigGroup,
    basisGroup,
    skinGeo,
    spheres,
    gimbals,
    cylinders,
    arrowFm,
    arrowTm,
    arrowNm,
    kpPositions: Array.from({ length: 21 }, () => new THREE.Vector3()),
    kpQuats: Array.from({ length: 21 }, () => new THREE.Quaternion()),
  };
}

export function updateDeformableManoMeshGeometry(vis) {
  const kps = vis.kpPositions;
  const posAttr = vis.skinGeo.attributes.position;
  const arr = posAttr.array;

  const fm = new THREE.Vector3().subVectors(kps[9], kps[0]).normalize();
  const tm = new THREE.Vector3().subVectors(kps[5], kps[17]).normalize();
  const nm = new THREE.Vector3().crossVectors(fm, tm).normalize();
  const orthoTm = new THREE.Vector3().crossVectors(nm, fm).normalize();

  const writeRing = (ringIdx, center, axisDir, rWide, rThick) => {
    let u = new THREE.Vector3().crossVectors(axisDir, nm);
    if (u.lengthSq() < 1e-5) u.copy(orthoTm);
    else u.normalize();
    const v = new THREE.Vector3().crossVectors(axisDir, u).normalize();

    const base = ringIdx * RING_SIDES * 3;
    for (let s = 0; s < RING_SIDES; s++) {
      const ang = (s / RING_SIDES) * Math.PI * 2;
      const cosA = Math.cos(ang) * rWide;
      const sinA = Math.sin(ang) * rThick;
      arr[base + s * 3 + 0] = center.x + u.x * cosA + v.x * sinA;
      arr[base + s * 3 + 1] = center.y + u.y * cosA + v.y * sinA;
      arr[base + s * 3 + 2] = center.z + u.z * cosA + v.z * sinA;
    }
  };

  writeRing(0, kps[0], fm, 0.028, 0.015);

  const mcpCenter = new THREE.Vector3()
    .add(kps[5]).add(kps[9]).add(kps[13]).add(kps[17]).multiplyScalar(0.25);
  const midPalm = new THREE.Vector3().lerpVectors(kps[0], mcpCenter, 0.52);
  writeRing(1, midPalm, fm, 0.038, 0.016);

  writeRing(2, mcpCenter, fm, 0.041, 0.014);

  for (let f = 0; f < 5; f++) {
    const chain = FINGER_CHAINS[f];
    const [id0, id1, id2, idTip] = chain.kpIds;
    const [rad0, rad1, rad2, rad3] = chain.radii;
    const rStart = 3 + f * 4;

    const dir0 = new THREE.Vector3().subVectors(kps[id1], kps[id0]).normalize();
    const dir1 = new THREE.Vector3().subVectors(kps[id2], kps[id1]).normalize();
    const dir2 = new THREE.Vector3().subVectors(kps[idTip], kps[id2]).normalize();

    writeRing(rStart + 0, kps[id0], dir0, rad0, rad0 * 0.82);
    writeRing(rStart + 1, kps[id1], dir1, rad1, rad1 * 0.82);
    writeRing(rStart + 2, kps[id2], dir2, rad2, rad2 * 0.82);

    const subTip = new THREE.Vector3().lerpVectors(kps[id2], kps[idTip], 0.72);
    writeRing(rStart + 3, subTip, dir2, rad3, rad3 * 0.78);

    const tipBase = (23 * RING_SIDES + f) * 3;
    arr[tipBase + 0] = kps[idTip].x;
    arr[tipBase + 1] = kps[idTip].y;
    arr[tipBase + 2] = kps[idTip].z;
  }

  posAttr.needsUpdate = true;
  vis.skinGeo.computeVertexNormals();

  for (let i = 0; i < 21; i++) {
    vis.spheres[i].position.copy(kps[i]);
    if (vis.gimbals[i]) {
      vis.gimbals[i].position.copy(kps[i]);
      vis.gimbals[i].quaternion.copy(vis.kpQuats[i]);
    }
  }
  for (const seg of vis.cylinders) {
    const pa = kps[seg.a];
    const pb = kps[seg.b];
    const dist = pa.distanceTo(pb);
    seg.mesh.position.copy(pa);
    seg.mesh.lookAt(pb);
    seg.mesh.scale.set(1, 1, Math.max(0.0001, dist));
  }

  const palmOrigin = new THREE.Vector3().lerpVectors(kps[0], kps[9], 0.35);
  vis.arrowFm.position.copy(palmOrigin);
  vis.arrowFm.setDirection(fm);
  vis.arrowTm.position.copy(palmOrigin);
  vis.arrowTm.setDirection(tm);
  vis.arrowNm.position.copy(palmOrigin);
  vis.arrowNm.setDirection(nm);
}

export function quatToMat3String(q) {
  if (!q) return ' 1.000  0.000  0.000\n 0.000  1.000  0.000\n 0.000  0.000  1.000';
  const [x, y, z, w] = q;
  const r00 = 1 - 2 * (y * y + z * z), r01 = 2 * (x * y - z * w), r02 = 2 * (x * z + y * w);
  const r10 = 2 * (x * y + z * w), r11 = 1 - 2 * (x * x + z * z), r12 = 2 * (y * z - x * w);
  const r20 = 2 * (x * z - y * w), r21 = 2 * (y * z + x * w), r22 = 1 - 2 * (x * x + y * y);
  const f = n => (n >= 0 ? ' ' : '') + n.toFixed(3);
  return `${f(r00)} ${f(r01)} ${f(r02)}\n${f(r10)} ${f(r11)} ${f(r12)}\n${f(r20)} ${f(r21)} ${f(r22)}`;
}

export function quatToEulerDegStr(q) {
  if (!q) return '(0°, 0°, 0°)';
  const e = new THREE.Euler().setFromQuaternion(new THREE.Quaternion(q[0], q[1], q[2], q[3]), 'XYZ');
  const d = r => Math.round((r * 180) / Math.PI);
  return `(${d(e.x)}°,${d(e.y)}°,${d(e.z)}°)`;
}

export function fmtQuat(q) {
  if (!q) return '[0.00, 0.00, 0.00, 1.00]';
  return `[${q[0].toFixed(2)}, ${q[1].toFixed(2)}, ${q[2].toFixed(2)}, ${q[3].toFixed(2)}]`;
}

export function quatAngleDeg(q) {
  if (!q) return 0;
  const w = Math.min(1.0, Math.max(-1.0, Math.abs(q[3])));
  return (2 * Math.acos(w) * 180) / Math.PI;
}
