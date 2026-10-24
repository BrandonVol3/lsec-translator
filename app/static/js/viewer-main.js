/**
 * viewer-main.js
 * Controlador principal de la vista /viewer (Modelo Paramétrico MANO M(β, θ) + Avatar VRM 1.0).
 */

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';
import { ensureARKitAndVRMExpressionBindings } from '/static/js/avatar/vrm-loader.js';
import {
  FINGER_COLORS_CSS,
  MANO_JOINT_DEFS,
  FINGER_CHAINS,
  applyLSECDefaultRestPose,
  createCompleteManoHandAssembly,
  updateDeformableManoMeshGeometry,
  quatToMat3String,
  quatToEulerDegStr,
  fmtQuat,
  quatAngleDeg,
} from './viewer-mano-rig.js';

const $ = id => document.getElementById(id);
const stage = $('stage');
const refVideo = $('refVideo');
const macroWrap = $('macroManoWrap');

let telemetryHand = 'right';
window.setTelemetryHand = (side) => {
  telemetryHand = side;
  $('tab-right').classList.toggle('active', side === 'right');
  $('tab-left').classList.toggle('active', side === 'left');
  $('macro-side-label').textContent = side === 'right' ? 'Mano Derecha (R)' : 'Mano Izquierda (L)';
  if (anim) applyFrameAtTime(currentTime);
};

function initTelemetryTable() {
  const tbody = $('manoJointsBody');
  tbody.innerHTML = '';
  for (const def of MANO_JOINT_DEFS) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="j-idx"><strong>${def.id}</strong><br><span>${def.kp}</span></td>
      <td>
        <div class="j-name">
          <span class="leg-dot" style="background:${FINGER_COLORS_CSS[def.finger]}"></span>
          <span>${def.label}</span>
        </div>
      </td>
      <td class="j-quat" id="jq-${def.suffix}">[0.00, 0.00, 0.00, 1.00]</td>
      <td class="j-euler" id="je-${def.suffix}">(0°, 0°, 0°)</td>
      <td class="j-deg" id="jd-${def.suffix}">0.0°</td>
      <td>
        <div class="j-bar-bg">
          <div class="j-bar-fill" id="jb-${def.suffix}" style="width:0%; background:${FINGER_COLORS_CSS[def.finger]}"></div>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  }
}
initTelemetryTable();

// ---------------------------------------------------------------------------
// Escena Principal Three.js (Avatar VRM + Malla Paramétrica MANO Superpuesta)
// ---------------------------------------------------------------------------
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.domElement.classList.add('webgl');
stage.appendChild(renderer.domElement);

const scene = new THREE.Scene();

const hemiLight = new THREE.HemisphereLight(0xffffff, 0x334155, 1.45);
scene.add(hemiLight);

const dirLight = new THREE.DirectionalLight(0xffffff, 1.9);
dirLight.position.set(1.5, 3, 2.5);
dirLight.castShadow = true;
scene.add(dirLight);

const fillLight = new THREE.DirectionalLight(0x38bdf8, 0.9);
fillLight.position.set(-2, 1.3, 1.6);
scene.add(fillLight);

const grid = new THREE.GridHelper(4, 24, 0x0284c7, 0x1e293b);
grid.position.y = 0;
scene.add(grid);

const camera = new THREE.PerspectiveCamera(24, 1, 0.04, 20);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;

// ---------------------------------------------------------------------------
// Sub-Escena 3D Macro (Inspector Aislado de la Malla Paramétrica MANO)
// ---------------------------------------------------------------------------
const macroRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
macroRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
macroWrap.appendChild(macroRenderer.domElement);

const macroScene = new THREE.Scene();
macroScene.add(new THREE.HemisphereLight(0xffffff, 0x1e293b, 1.6));
const macroDir = new THREE.DirectionalLight(0x38bdf8, 2.0);
macroDir.position.set(0.5, 1.0, 1.2);
macroScene.add(macroDir);

const macroGrid = new THREE.GridHelper(0.36, 12, 0x0284c7, 0x1e293b);
macroGrid.rotation.x = Math.PI / 2;
macroGrid.position.z = -0.09;
macroScene.add(macroGrid);

const macroCamera = new THREE.PerspectiveCamera(28, 1, 0.01, 5);
macroCamera.position.set(0, 0, 0.42);
macroCamera.lookAt(0, 0, 0);

const avatarHandVis = {
  right: createCompleteManoHandAssembly(scene),
  left: createCompleteManoHandAssembly(scene),
};
const macroHandVis = createCompleteManoHandAssembly(macroScene);

function syncManoAssembliesFromVrm() {
  if (!vrm || !vrm.humanoid) return;
  vrm.scene.updateMatrixWorld(true);
  const humanoid = vrm.humanoid;

  for (const side of ['right', 'left']) {
    const vis = avatarHandVis[side];
    const kps = vis.kpPositions;
    const quats = vis.kpQuats;
    const handNode = humanoid.getNormalizedBoneNode(`${side}Hand`);
    if (!handNode) continue;

    handNode.getWorldPosition(kps[0]);
    handNode.getWorldQuaternion(quats[0]);

    for (const chain of FINGER_CHAINS) {
      const [b0Name, b1Name, b2Name] = chain.bones.map(b => `${side}${b}`);
      const [id0, id1, id2, idTip] = chain.kpIds;

      const n0 = humanoid.getNormalizedBoneNode(b0Name);
      const n1 = humanoid.getNormalizedBoneNode(b1Name);
      const n2 = humanoid.getNormalizedBoneNode(b2Name);

      if (n0) { n0.getWorldPosition(kps[id0]); n0.getWorldQuaternion(quats[id0]); }
      if (n1) { n1.getWorldPosition(kps[id1]); n1.getWorldQuaternion(quats[id1]); }
      if (n2) { n2.getWorldPosition(kps[id2]); n2.getWorldQuaternion(quats[id2]); }

      if (n1 && n2) {
        const dir = new THREE.Vector3().subVectors(kps[id2], kps[id1]);
        const len = dir.length();
        const relQ = quats[id1].clone().invert().multiply(quats[id2]);
        dir.applyQuaternion(relQ).normalize().multiplyScalar(Math.max(0.017, len * 0.86));
        kps[idTip].copy(kps[id2]).add(dir);
        quats[idTip].copy(quats[id2]);
      }
    }

    updateDeformableManoMeshGeometry(vis);
  }

  const srcVis = avatarHandVis[telemetryHand];
  if (srcVis) {
    const center = new THREE.Vector3();
    for (let i = 0; i < 21; i++) center.add(srcVis.kpPositions[i]);
    center.multiplyScalar(1 / 21);

    for (let i = 0; i < 21; i++) {
      macroHandVis.kpPositions[i].copy(srcVis.kpPositions[i]).sub(center);
      macroHandVis.kpQuats[i].copy(srcVis.kpQuats[i]);
    }
    updateDeformableManoMeshGeometry(macroHandVis);
  }

  updateDynamicCalloutLines();
}

function projectToScreen(vec3, w, h) {
  const v = vec3.clone().project(camera);
  return [(v.x * 0.5 + 0.5) * w, (-(v.y * 0.5) + 0.5) * h];
}

function setPolylinePoints(id, x0, y0, x1, y1) {
  const el = $(id);
  if (!el) return;
  const midX = x0 + (x1 - x0) * 0.55;
  el.setAttribute('points', `${x0.toFixed(1)},${y0.toFixed(1)} ${midX.toFixed(1)},${y0.toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}`);
}

function updateDynamicCalloutLines() {
  if (!$('chkCallouts').checked || !vrm) return;
  const w = stage.clientWidth;
  const h = stage.clientHeight;
  if (w === 0 || h === 0) return;

  const rhKps = avatarHandVis.right.kpPositions;
  const lhKps = avatarHandVis.left.kpPositions;

  const [rx0, ry0] = projectToScreen(rhKps[0], w, h);
  setPolylinePoints('line-rh-wrist', 255, 86, rx0, ry0);

  const [rx8, ry8] = projectToScreen(rhKps[8], w, h);
  setPolylinePoints('line-rh-fingers', 255, h - 92, rx8, ry8);

  const lhPalm = new THREE.Vector3().lerpVectors(lhKps[0], lhKps[9], 0.45);
  const [lxP, lyP] = projectToScreen(lhPalm, w, h);
  setPolylinePoints('line-lh-palm', w - 255, 86, lxP, lyP);

  const [lx12, ly12] = projectToScreen(lhKps[12], w, h);
  setPolylinePoints('line-lh-mesh', w - 255, h - 92, lx12, ly12);
}

// ---------------------------------------------------------------------------
// Cámara, Resize y Modo Rayos-X del Avatar
// ---------------------------------------------------------------------------
function setCameraMode(mode) {
  ['cam-mano', 'cam-macro-rh', 'cam-macro-lh', 'cam-full'].forEach(id => $(id).classList.remove('active'));
  if (mode === 'mano') {
    $('cam-mano').classList.add('active');
    camera.position.set(0, 1.31, 0.96);
    controls.target.set(0, 1.24, 0.14);
  } else if (mode === 'macro-rh') {
    $('cam-macro-rh').classList.add('active');
    const p = avatarHandVis.right.kpPositions[9];
    if (p && p.lengthSq() > 0) {
      camera.position.set(p.x - 0.08, p.y + 0.04, p.z + 0.34);
      controls.target.copy(p);
    }
  } else if (mode === 'macro-lh') {
    $('cam-macro-lh').classList.add('active');
    const p = avatarHandVis.left.kpPositions[9];
    if (p && p.lengthSq() > 0) {
      camera.position.set(p.x + 0.08, p.y + 0.04, p.z + 0.34);
      controls.target.copy(p);
    }
  } else if (mode === 'full') {
    $('cam-full').classList.add('active');
    camera.position.set(0, 1.35, 1.85);
    controls.target.set(0, 1.22, 0);
  }
  controls.update();
}
$('cam-mano').onclick = () => setCameraMode('mano');
$('cam-macro-rh').onclick = () => setCameraMode('macro-rh');
$('cam-macro-lh').onclick = () => setCameraMode('macro-lh');
$('cam-full').onclick = () => setCameraMode('full');
setCameraMode('mano');

function applyAvatarXrayState() {
  if (!vrm) return;
  const xray = $('chkXray').checked;
  vrm.scene.traverse(obj => {
    if (obj.isMesh && obj.material) {
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
      for (const m of mats) {
        m.transparent = true;
        m.opacity = xray ? 0.48 : 1.0;
        m.needsUpdate = true;
      }
    }
  });
}

const resize = () => {
  const w = stage.clientWidth, h = stage.clientHeight;
  if (w > 0 && h > 0) {
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  const mw = macroWrap.clientWidth, mh = macroWrap.clientHeight;
  if (mw > 0 && mh > 0) {
    macroRenderer.setSize(mw, mh, false);
    macroCamera.aspect = mw / mh;
    macroCamera.updateProjectionMatrix();
  }
};
window.addEventListener('resize', resize);
setTimeout(resize, 50);

// ---------------------------------------------------------------------------
// Carga de Avatar VRM, Señas y Telemetría Matemática SO(3)
// ---------------------------------------------------------------------------
let vrm = null;
let anim = null;
let isPlaying = true;
let currentTime = 0;
let duration = 0;
let fps = 60;
let totalFrames = 0;
let currentSignName = 'Hola';
let currentVersion = '2.7';

async function loadVrmBuffer(buffer, name = 'Avatar') {
  $('status-banner').textContent = `Cargando ${name}...`;
  const loader = new GLTFLoader();
  loader.register(parser => new VRMLoaderPlugin(parser));
  try {
    const gltf = await loader.parseAsync(buffer, '');
    if (vrm) scene.remove(vrm.scene);
    vrm = gltf.userData.vrm;
    VRMUtils.rotateVRM0(vrm);
    ensureARKitAndVRMExpressionBindings(vrm, gltf);
    scene.add(vrm.scene);
    applyLSECDefaultRestPose(vrm);
    applyAvatarXrayState();
    setCameraMode('mano');
    updateStatus();
  } catch (err) {
    console.error('Error cargando VRM:', err);
    $('status-banner').textContent = 'Error cargando avatar VRM: ' + err.message;
  }
}

function resetViewerFacialExpressionsToNeutral() {
  if (!vrm || !vrm.expressionManager) return;
  try {
    if (typeof vrm.expressionManager.resetValues === 'function') {
      vrm.expressionManager.resetValues();
    }
    const vrmPresets = [
      'happy', 'angry', 'sad', 'relaxed', 'surprised',
      'aa', 'ih', 'ou', 'ee', 'oh',
      'blink', 'blinkLeft', 'blinkRight',
      'lookUp', 'lookDown', 'lookLeft', 'lookRight'
    ];
    for (const preset of vrmPresets) {
      vrm.expressionManager.setValue(preset, 0.0);
    }
    vrm.expressionManager.setValue('neutral', 1.0);
  } catch (_) {}
}

function loadAnimationJson(jsonText, signTitle = '', qaData = null) {
  try {
    anim = typeof jsonText === 'string' ? JSON.parse(jsonText) : jsonText;
    fps = anim.metadata?.fps || 60;
    totalFrames = anim.frames.length;
    duration = anim.metadata?.duration || (totalFrames / fps);
    currentTime = 0;
    isPlaying = true;
    $('play').textContent = '⏸ Pausar';
    $('play').classList.add('active');

    resetViewerFacialExpressionsToNeutral();

    const sName = signTitle || anim.metadata?.sign || 'LSEC';
    const cnmArch = anim.metadata?.facialArchetype || 'neutral';
    const cnmExplicit = anim.metadata?.hasExplicitFacialExpression === true;
    const handStd = anim.metadata?.handStandardization;
    const verLabel = (handStd && handStd.version === 'v2.7')
      ? `v2.7 Estandarizado (${handStd.status === 'STANDARDIZED' ? (handStd.template_id || 'OK') : handStd.status})`
      : (anim.metadata?.pipelineVersion || `v${currentVersion}`);
    $('badge-version').textContent = `${verLabel} · CNM: ${cnmExplicit ? cnmArch : 'neutral'}`;

    const fid = anim.metadata?.fidelity || {};
    if (qaData && qaData.distance_after_deg !== undefined && qaData.distance_after_deg !== null) {
      $('qa-delta-deg').textContent = `${Number(qaData.distance_after_deg).toFixed(2)}°`;
    } else if (fid.avg_bone_delta_deg !== undefined) {
      $('qa-delta-deg').textContent = `${Number(fid.avg_bone_delta_deg).toFixed(2)}°`;
    }
    if (fid.avg_wrist_displacement_cm !== undefined) {
      $('qa-wrist-cm').textContent = `${Number(fid.avg_wrist_displacement_cm).toFixed(2)} cm`;
    }
    if (qaData && qaData.right_hand_coverage !== undefined) {
      $('m-cov-rl').textContent = `${(qaData.right_hand_coverage * 100).toFixed(0)}% / ${(qaData.left_hand_coverage * 100).toFixed(0)}%`;
    }

    updateStatus(sName);
    applyFrameAtTime(0);
  } catch (err) {
    console.error('Error leyendo animation.json:', err);
    $('status-banner').textContent = 'Error en archivo de animación: ' + err.message;
  }
}

async function loadSignByName(signName, versionOverride = null) {
  if (!signName || !signName.trim()) return;
  const name = signName.trim();
  currentSignName = name;
  const ver = versionOverride || ($('selectVersion') ? $('selectVersion').value : currentVersion) || '2.7';
  currentVersion = ver;
  if ($('selectVersion') && $('selectVersion').value !== ver) {
    $('selectVersion').value = ver;
  }
  $('signSearch').value = name;
  $('status-banner').textContent = `Cargando seña (${ver === '2.7' ? 'v2.7 Estandarizado' : 'v' + ver}) y modelo paramétrico MANO: ${name}...`;
  try {
    const [resAnim, resQa] = await Promise.all([
      fetch(`/api/v1/animations/${encodeURIComponent(name)}?version=${encodeURIComponent(ver)}`),
      fetch(`/api/v1/animations/${encodeURIComponent(name)}/qa?version=${encodeURIComponent(ver)}`).catch(() => null),
    ]);
    if (!resAnim.ok) throw new Error(`HTTP ${resAnim.status}: Seña no encontrada`);
    const data = await resAnim.json();
    const qaData = (resQa && resQa.ok) ? await resQa.json() : null;

    refVideo.src = `/api/v1/animations/${encodeURIComponent(name)}/video`;
    refVideo.play().catch(() => {});

    loadAnimationJson(data, name, qaData);
  } catch (err) {
    console.error(err);
    $('status-banner').textContent = `⚠️ No se pudo cargar '${name}': ${err.message}`;
  }
}
window.loadSignByName = loadSignByName;

if ($('selectVersion')) {
  $('selectVersion').onchange = e => {
    currentVersion = e.target.value || '2.7';
    const val = $('signSearch').value || currentSignName;
    if (val) loadSignByName(val, currentVersion);
  };
}

$('btnLoadSign').onclick = () => {
  const val = $('signSearch').value;
  if (val) loadSignByName(val, currentVersion);
};
$('signSearch').onkeydown = e => {
  if (e.key === 'Enter') {
    const val = $('signSearch').value;
    if (val) loadSignByName(val, currentVersion);
  }
};

function updateStatus(title = '') {
  if (vrm && anim) {
    const sName = title || anim.metadata?.sign || 'LSEC';
    const handStd = anim.metadata?.handStandardization;
    const stdTag = (handStd && handStd.version === 'v2.7')
      ? `v2.7 ${handStd.status || 'ESTANDARIZADO'}`
      : `v${currentVersion}`;
    const cnmLabel = anim.metadata?.hasExplicitFacialExpression
      ? `CNM Explícito (${anim.metadata?.facialArchetypeLabel || anim.metadata?.facialArchetype})`
      : 'CNM Neutral';
    $('status-banner').textContent = `Seña: ${sName} [${stdTag}] · ${cnmLabel} · 16 Rots SO(3) / Mano → Avatar VRM 1.0 (${totalFrames}F @ ${fps} FPS)`;
  }
}

function applyFrameAtTime(timeSec) {
  if (!vrm || !anim || anim.frames.length === 0) return;

  const frameIdx = Math.max(0, Math.min(anim.frames.length - 1, Math.round(timeSec * fps)));
  const frame = anim.frames[frameIdx];
  if (!frame) return;

  const humanoid = vrm.humanoid;
  if (frame.hipsPosition) {
    const hipsNode = humanoid.getNormalizedBoneNode('hips');
    if (hipsNode) hipsNode.position.fromArray(frame.hipsPosition);
  }

  if (frame.rotations) {
    for (const [boneName, q] of Object.entries(frame.rotations)) {
      const boneNode = humanoid.getNormalizedBoneNode(boneName);
      if (boneNode) boneNode.quaternion.set(q[0], q[1], q[2], q[3]);
    }
  }

  if (vrm.expressionManager) {
    const hasExplicitFacial = anim.metadata?.hasExplicitFacialExpression === true ||
      anim.metadata?.nonManualStandard?.hasExplicitFacialExpression === true;

    if (!hasExplicitFacial) {
      resetViewerFacialExpressionsToNeutral();
    } else {
      let maxNonNeutral = 0;
      if (frame.blendshapes) {
        for (const [bsName, weight] of Object.entries(frame.blendshapes)) {
          const w = Number(weight) || 0;
          if (w > maxNonNeutral) maxNonNeutral = w;
          vrm.expressionManager.setValue(bsName, w);
        }
      }
      if (frame.expressions) {
        for (const [expr, weight] of Object.entries(frame.expressions)) {
          const w = Number(weight) || 0;
          if (expr !== 'neutral' && w > maxNonNeutral) maxNonNeutral = w;
          vrm.expressionManager.setValue(expr, w);
        }
      }
      if (maxNonNeutral > 0.02) {
        vrm.expressionManager.setValue('neutral', Math.max(0, 1.0 - maxNonNeutral));
      } else {
        vrm.expressionManager.setValue('neutral', 1.0);
      }
    }
  }

  if (refVideo && refVideo.readyState >= 2 && Math.abs(refVideo.currentTime - timeSec) > 0.12) {
    try { refVideo.currentTime = timeSec; } catch (_) {}
  }

  const qRH = frame.rotations?.rightHand;
  const qLH = frame.rotations?.leftHand;
  $('mat-rh').textContent = quatToMat3String(qRH);
  $('mat-lh').textContent = quatToMat3String(qLH);
  $('axis-rh').textContent = `||ω||=${quatAngleDeg(qRH).toFixed(1)}°`;
  $('axis-lh').textContent = `||ω||=${quatAngleDeg(qLH).toFixed(1)}°`;

  $('co-q-rh').textContent = `q_RH = ${fmtQuat(qRH)}`;
  $('co-q-lh').textContent = `q_LH = ${fmtQuat(qLH)}`;
  $('active-frame-badge').textContent = `Cuadro ${frameIdx} / ${totalFrames - 1}`;

  const side = telemetryHand;
  let sumFlex = 0;
  let countFlex = 0;
  for (const def of MANO_JOINT_DEFS) {
    const boneKey = `${side}${def.suffix}`;
    const q = frame.rotations?.[boneKey];
    const qEl = $(`jq-${def.suffix}`);
    const eEl = $(`je-${def.suffix}`);
    const dEl = $(`jd-${def.suffix}`);
    const bEl = $(`jb-${def.suffix}`);
    if (q && qEl && eEl && dEl && bEl) {
      qEl.textContent = fmtQuat(q);
      eEl.textContent = quatToEulerDegStr(q);
      const deg = quatAngleDeg(q);
      dEl.textContent = `${deg.toFixed(1)}°`;
      const pct = Math.min(100, (deg / 95) * 100);
      bEl.style.width = `${pct.toFixed(0)}%`;
      if (def.suffix !== 'Hand') {
        sumFlex += deg;
        countFlex++;
      }
    }
  }
  if (countFlex > 0) {
    $('co-flex-rh').textContent = `Flexión Media 15 Falanges: ${(sumFlex / countFlex).toFixed(1)}°`;
  }

  $('scrub').value = duration > 0 ? Math.round((timeSec / duration) * 1000) : 0;
  const currentStr = timeSec.toFixed(2).padStart(5, '0');
  const totalStr = duration.toFixed(2).padStart(5, '0');
  $('info').textContent = `${currentStr}s / ${totalStr}s (F: ${frameIdx}/${totalFrames - 1})`;
}

$('btnCapturePose').onclick = () => {
  if (!anim || !anim.frames.length) return;
  isPlaying = false;
  $('play').textContent = '▶ Reproducir';
  $('play').classList.remove('active');
  refVideo.pause();
  const targetIdx = Math.floor(anim.frames.length * 0.42);
  currentTime = targetIdx / fps;
  applyFrameAtTime(currentTime);
};

$('play').onclick = () => {
  if (!anim) return;
  isPlaying = !isPlaying;
  $('play').textContent = isPlaying ? '⏸ Pausar' : '▶ Reproducir';
  $('play').classList.toggle('active', isPlaying);
  if (isPlaying) refVideo.play().catch(() => {});
  else refVideo.pause();
};

$('stop').onclick = () => {
  isPlaying = false;
  $('play').textContent = '▶ Reproducir';
  $('play').classList.remove('active');
  currentTime = 0;
  refVideo.pause();
  if (anim) applyFrameAtTime(0);
};

$('prev').onclick = () => {
  isPlaying = false;
  $('play').textContent = '▶ Reproducir';
  $('play').classList.remove('active');
  refVideo.pause();
  currentTime = Math.max(0, currentTime - (1 / fps));
  applyFrameAtTime(currentTime);
};

$('next').onclick = () => {
  isPlaying = false;
  $('play').textContent = '▶ Reproducir';
  $('play').classList.remove('active');
  refVideo.pause();
  currentTime = Math.min(duration, currentTime + (1 / fps));
  applyFrameAtTime(currentTime);
};

$('scrub').oninput = e => {
  if (!duration) return;
  currentTime = (parseFloat(e.target.value) / 1000) * duration;
  applyFrameAtTime(currentTime);
};

$('chkManoMesh').onchange = e => {
  const v = e.target.checked;
  avatarHandVis.right.meshGroup.visible = v;
  avatarHandVis.left.meshGroup.visible = v;
  macroHandVis.meshGroup.visible = v;
};
$('chkManoRig').onchange = e => {
  const v = e.target.checked;
  avatarHandVis.right.rigGroup.visible = v;
  avatarHandVis.left.rigGroup.visible = v;
  macroHandVis.rigGroup.visible = v;
};
$('chkBasis').onchange = e => {
  const v = e.target.checked;
  avatarHandVis.right.basisGroup.visible = v;
  avatarHandVis.left.basisGroup.visible = v;
  macroHandVis.basisGroup.visible = v;
};
$('chkCallouts').onchange = e => {
  const v = e.target.checked;
  $('callout-svg').style.display = v ? 'block' : 'none';
  $('callouts-container').style.display = v ? 'block' : 'none';
};
$('chkXray').onchange = applyAvatarXrayState;

$('btnTogglePanels').onclick = () => {
  $('workspace').classList.toggle('clean-mode');
  setTimeout(resize, 30);
};

async function initCatalog() {
  try {
    const res = await fetch('/api/v1/animations/list?limit=6000');
    if (res.ok) {
      const data = await res.json();
      const list = $('signsList');
      list.innerHTML = '';
      const seenNfc = new Set();
      (data.signs || []).forEach(s => {
        if (!s) return;
        const nfcSign = String(s).normalize('NFC').trim();
        if (!nfcSign || seenNfc.has(nfcSign)) return;
        seenNfc.add(nfcSign);
        const opt = document.createElement('option');
        opt.value = nfcSign;
        list.appendChild(opt);
      });
    }
  } catch (_) {}
}

async function initDefaultAvatar() {
  const candidates = [
    '/avatar/LSEC-Interpreter-Female.vrm',
    '/avatar/LSEC-Interpreter-Female-2.vrm',
    'Avatar/LSEC-Interpreter-Female.vrm'
  ];
  for (const path of candidates) {
    try {
      const res = await fetch(path);
      if (res.ok) {
        const buf = await res.arrayBuffer();
        await loadVrmBuffer(buf, 'LSEC-Interpreter-Female.vrm');
        return true;
      }
    } catch (_) {}
  }
  return false;
}

$('fVrm').onchange = async e => {
  const file = e.target.files[0];
  if (file) await loadVrmBuffer(await file.arrayBuffer(), file.name);
};
$('fAnim').onchange = async e => {
  const file = e.target.files[0];
  if (file) loadAnimationJson(await file.text(), file.name);
};

let lastTimestamp = performance.now();

function animate(now) {
  const deltaSec = (now - lastTimestamp) / 1000;
  lastTimestamp = now;

  if (isPlaying && anim && duration > 0) {
    const rate = parseFloat($('rate').value) || 1.0;
    currentTime += deltaSec * rate;

    if (currentTime >= duration) {
      if ($('loop').checked) {
        currentTime = currentTime % duration;
      } else {
        currentTime = duration;
        isPlaying = false;
        $('play').textContent = '▶ Reproducir';
        $('play').classList.remove('active');
      }
    }
    applyFrameAtTime(currentTime);
  }

  controls.update();
  if (vrm) {
    vrm.update(deltaSec);
    syncManoAssembliesFromVrm();
  }
  renderer.render(scene, camera);
  macroRenderer.render(macroScene, macroCamera);
  requestAnimationFrame(animate);
}

requestAnimationFrame(animate);

(async () => {
  await initCatalog();
  const avatarLoaded = await initDefaultAvatar();
  if (avatarLoaded) {
    await loadSignByName('Hola');
  }
})();
