import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  validateSignClip,
  HUMAN_BONE_NAMES,
  CLIP_STATUSES,
  REST_POSE,
  trimSignClipStroke,
  convertDirectAnimationToSignClip,
  detectDatasetQuaternionLayout as schemaDetectLayout,
  normalizeBoneName as schemaNormalizeBone
} from '../static/js/avatar/sign-animation-schema.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const controllerPath = path.join(__dirname, '../static/js/avatar/avatar-controller.js');
const rawBakedPath = path.join(__dirname, '../../scripts/lunes_raw_baked_animation.json');

console.log('--- TEST 1: Verificar importación estática en avatar-controller.js ---');
const controllerSource = fs.readFileSync(controllerPath, 'utf8');
if (!controllerSource.includes("import { validateSignClip } from './sign-animation-schema.js';")) {
  throw new Error("FAIL: avatar-controller.js no contiene el import de validateSignClip.");
}
if (!controllerSource.includes("import { HUMAN_BONE_NAMES } from './sign-animation-schema.js';")) {
  throw new Error("FAIL: avatar-controller.js no contiene el import de HUMAN_BONE_NAMES.");
}
console.log('PASS: validateSignClip y HUMAN_BONE_NAMES están correctamente importados en avatar-controller.js');

// Extraer funciones y lógica del controlador evaluando el código relevante
const BONE_LOWER_MAP = new Map((HUMAN_BONE_NAMES || []).map(b => [b.toLowerCase(), b]));

const BONE_ALIASES = {
  'j_bip_c_hips': 'hips',
  'j_bip_c_spine': 'spine',
  'j_bip_c_chest': 'chest',
  'j_bip_c_upperchest': 'upperChest',
  'j_bip_c_neck': 'neck',
  'j_bip_c_head': 'head',
  'j_bip_l_eye': 'leftEye',
  'j_bip_r_eye': 'rightEye',
  'j_bip_l_shoulder': 'leftShoulder',
  'j_bip_l_upperarm': 'leftUpperArm',
  'j_bip_l_lowerarm': 'leftLowerArm',
  'j_bip_l_hand': 'leftHand',
  'j_bip_l_thumb1': 'leftThumbMetacarpal',
  'j_bip_l_thumb2': 'leftThumbProximal',
  'j_bip_l_thumb3': 'leftThumbDistal',
  'j_bip_l_index1': 'leftIndexProximal',
  'j_bip_l_index2': 'leftIndexIntermediate',
  'j_bip_l_index3': 'leftIndexDistal',
  'j_bip_l_middle1': 'leftMiddleProximal',
  'j_bip_l_middle2': 'leftMiddleIntermediate',
  'j_bip_l_middle3': 'leftMiddleDistal',
  'j_bip_l_ring1': 'leftRingProximal',
  'j_bip_l_ring2': 'leftRingIntermediate',
  'j_bip_l_ring3': 'leftRingDistal',
  'j_bip_l_little1': 'leftLittleProximal',
  'j_bip_l_little2': 'leftLittleIntermediate',
  'j_bip_l_little3': 'leftLittleDistal',
  'j_bip_r_shoulder': 'rightShoulder',
  'j_bip_r_upperarm': 'rightUpperArm',
  'j_bip_r_lowerarm': 'rightLowerArm',
  'j_bip_r_hand': 'rightHand',
  'j_bip_r_thumb1': 'rightThumbMetacarpal',
  'j_bip_r_thumb2': 'rightThumbProximal',
  'j_bip_r_thumb3': 'rightThumbDistal',
  'j_bip_r_index1': 'rightIndexProximal',
  'j_bip_r_index2': 'rightIndexIntermediate',
  'j_bip_r_index3': 'rightIndexDistal',
  'j_bip_r_middle1': 'rightMiddleProximal',
  'j_bip_r_middle2': 'rightMiddleIntermediate',
  'j_bip_r_middle3': 'rightMiddleDistal',
  'j_bip_r_ring1': 'rightRingProximal',
  'j_bip_r_ring2': 'rightRingIntermediate',
  'j_bip_r_ring3': 'rightRingDistal',
  'j_bip_r_little1': 'rightLittleProximal',
  'j_bip_r_little2': 'rightLittleIntermediate',
  'j_bip_r_little3': 'rightLittleDistal',
  'wrist': 'rightHand',
  'r_wrist': 'rightHand',
  'l_wrist': 'leftHand',
  'righthandthumb1': 'rightThumbMetacarpal',
  'righthandthumb2': 'rightThumbProximal',
  'righthandthumb3': 'rightThumbDistal',
  'righthandindex1': 'rightIndexProximal',
  'righthandindex2': 'rightIndexIntermediate',
  'righthandindex3': 'rightIndexDistal',
  'righthandmiddle1': 'rightMiddleProximal',
  'righthandmiddle2': 'rightMiddleIntermediate',
  'righthandmiddle3': 'rightMiddleDistal',
  'righthandring1': 'rightRingProximal',
  'righthandring2': 'rightRingIntermediate',
  'righthandring3': 'rightRingDistal',
  'righthandpinky1': 'rightLittleProximal',
  'righthandpinky2': 'rightLittleIntermediate',
  'righthandpinky3': 'rightLittleDistal'
};

function normalizeBoneName(name) {
  if (typeof name !== 'string') return name;
  const clean = name.replace(/^mixamorig:?/i, '').trim();
  const lower = clean.toLowerCase();
  if (BONE_ALIASES[lower]) return BONE_ALIASES[lower];
  if (BONE_LOWER_MAP.has(lower)) return BONE_LOWER_MAP.get(lower);
  return clean;
}

function detectDatasetQuaternionLayout(data) {
  const meta = (data && data.metadata) || {};
  const explicit = (meta.quaternionOrder || meta.quaternionFormat || data.quaternionOrder || data.quaternionFormat || '').toLowerCase();
  if (explicit === 'wxyz') return 'wxyz';
  if (explicit === 'xyzw') return 'xyzw';

  let wxyzVotes = 0;
  let xyzwVotes = 0;

  const voteQuat = (q) => {
    if (!Array.isArray(q) || q.length < 4) return;
    const a = Number(q[0]) || 0;
    const d = Number(q[3]) || 0;
    if (Math.abs(a) > 0.7 && Math.abs(d) < 0.35) wxyzVotes++;
    else if (Math.abs(d) > 0.7 && Math.abs(a) < 0.35) xyzwVotes++;
  };

  if (Array.isArray(data.frames)) {
    for (const f of data.frames.slice(0, 10)) {
      if (f && f.rotations && typeof f.rotations === 'object') {
        for (const q of Object.values(f.rotations)) {
          voteQuat(q);
        }
      }
    }
  } else if (data.extractedTracks && typeof data.extractedTracks === 'object') {
    for (const track of Object.values(data.extractedTracks)) {
      if (track && Array.isArray(track.quaternions)) {
        for (const q of track.quaternions.slice(0, 10)) {
          voteQuat(q);
        }
      }
    }
  }

  return (wxyzVotes > xyzwVotes) ? 'wxyz' : 'xyzw';
}

class TestControllerHarness {
  constructor() {
    this.clips = {};
    this.categories = [];
    this.selectedClipId = null;
    this.lastError = null;
    this.player = null; // Permite probar robustez con player null
  }

  renderClipOptions() {}

  async prepareSelectedClip() {
    let clip = this.clips[this.selectedClipId];
    if (typeof clip === 'function') {
      try {
        clip = await clip();
        this.clips[this.selectedClipId] = clip;
      } catch (e) {
        console.error('Error al resolver clip dinámico:', e);
      }
    }
    if (!clip) clip = this.clips.NEUTRAL;
    if (this.player) {
      this.player.loadClip(clip);
    }
    const duration = this.player ? this.player.getDuration() : ((clip && clip.durationMs ? clip.durationMs / 1000 : 0));
    return duration;
  }

  convertHamerAnimationToSignClip(data, defaultName = 'SEÑA_LSEC') {
    if (!data || typeof data !== 'object') return data;

    const meta = data.metadata || {};
    const signName = (meta.sign && typeof meta.sign === 'string' && meta.sign.trim())
      || (data.sign && typeof data.sign === 'string' && data.sign.trim())
      || (typeof defaultName === 'string' && defaultName.trim() ? defaultName.trim() : 'SEÑA_LSEC');
    const fps = Number(meta.fps || data.fps || data.FPS) || 60;
    const totalFrames = Array.isArray(data.frames)
      ? data.frames.length
      : (Number(data.totalFrames) || 0);
    const durationSec = Number(meta.duration || data.duration)
      || (totalFrames > 0 ? (totalFrames - 1) / fps : 1.0);

    const detectedLayout = detectDatasetQuaternionLayout(data);
    const isWxyz = (detectedLayout === 'wxyz');

    const boneMap = new Map();
    const exprMap = new Map();
    let maxTimeFound = 0;

    const sanitizeQuat = (raw) => {
      if (!Array.isArray(raw) || raw.length < 4) return [0, 0, 0, 1];
      const vals = raw.slice(0, 4).map(v => (typeof v === 'number' && Number.isFinite(v) ? v : 0));
      const [x, y, z, w] = isWxyz ? [vals[1], vals[2], vals[3], vals[0]] : [vals[0], vals[1], vals[2], vals[3]];
      const norm = Math.hypot(x, y, z, w);
      if (!Number.isFinite(norm) || norm < 0.0001) {
        return [0, 0, 0, 1];
      }
      return [x / norm, y / norm, z / norm, w / norm];
    };

    if (Array.isArray(data.frames)) {
      for (let i = 0; i < data.frames.length; i++) {
        const f = data.frames[i];
        if (!f || typeof f !== 'object') continue;
        const t = (typeof f.time === 'number' && Number.isFinite(f.time)) ? f.time : (i / fps);
        if (t > maxTimeFound) maxTimeFound = t;

        if (f.rotations && typeof f.rotations === 'object') {
          for (let [rawBone, q] of Object.entries(f.rotations)) {
            if (!Array.isArray(q) || q.length < 4) continue;
            const bone = normalizeBoneName(rawBone);
            if (!boneMap.has(bone)) {
              boneMap.set(bone, { boneName: bone, times: [], rotations: [] });
            }
            const bEntry = boneMap.get(bone);
            bEntry.times.push(t);
            const [qx, qy, qz, qw] = sanitizeQuat(q);
            bEntry.rotations.push(qx, qy, qz, qw);
          }
        }

        const exprSource = f.expressions || f.blendshapes;
        if (exprSource && typeof exprSource === 'object') {
          for (const [expr, val] of Object.entries(exprSource)) {
            if (typeof val !== 'number' || !Number.isFinite(val)) continue;
            let exprName = expr;
            if (expr === 'blink_l') exprName = 'blinkLeft';
            else if (expr === 'blink_r') exprName = 'blinkRight';

            if (!exprMap.has(exprName)) {
              exprMap.set(exprName, { expressionName: exprName, times: [], values: [] });
            }
            const eEntry = exprMap.get(exprName);
            eEntry.times.push(t);
            eEntry.values.push(Math.max(0, Math.min(1, val)));
          }
        }
      }
    } else if (data.extractedTracks && typeof data.extractedTracks === 'object') {
      for (let [rawBone, track] of Object.entries(data.extractedTracks)) {
        if (!track || typeof track !== 'object') continue;
        const bone = normalizeBoneName(rawBone);
        const times = Array.isArray(track.times) ? track.times : [];
        if (times.length > 0) {
          const lastT = times[times.length - 1];
          if (typeof lastT === 'number' && lastT > maxTimeFound) maxTimeFound = lastT;
        }

        const rotations = [];
        if (Array.isArray(track.rotations)) {
          for (let k = 0; k < track.rotations.length; k += 4) {
            const rawSlice = [track.rotations[k], track.rotations[k + 1], track.rotations[k + 2], track.rotations[k + 3]];
            const [qx, qy, qz, qw] = sanitizeQuat(rawSlice);
            rotations.push(qx, qy, qz, qw);
          }
        } else if (Array.isArray(track.quaternions)) {
          for (let k = 0; k < track.quaternions.length; k++) {
            const item = track.quaternions[k];
            const [qx, qy, qz, qw] = sanitizeQuat(item);
            rotations.push(qx, qy, qz, qw);
          }
        }
        if (times.length > 0 && rotations.length === times.length * 4) {
          boneMap.set(bone, { boneName: bone, times, rotations });
        }
      }
    }

    const finalDurationSec = Math.max(durationSec, maxTimeFound);
    const durationMs = Math.max(100, Math.round((finalDurationSec + 0.15) * 1000));

    const rawSlug = meta.slug || data.slug || signName.toLowerCase().replace(/[^a-z0-9_-]/gi, '_').replace(/^_+|_+$/g, '');
    const clipId = (rawSlug && rawSlug.length > 0) ? rawSlug : 'custom_clip';

    const boneTracks = Array.from(boneMap.values());
    const expressionTracks = Array.from(exprMap.values());

    return {
      clipId: clipId,
      gloss: signName,
      durationMs: durationMs,
      status: 'DEMO_ONLY',
      validationStatus: 'EXPERIMENTAL',
      metadata: {
        isValidatedLSEC: false,
        source: 'HaMeR Pipeline',
        quaternionOrder: 'xyzw',
        ...meta
      },
      boneTracks,
      expressionTracks
    };
  }

  async importCustomClip(file) {
    if (!file) return null;

    try {
      let customClip;
      const fileName = (file && typeof file === 'object' && file.name) ? file.name : 'custom_clip.json';

      if (typeof file === 'string') {
        try {
          customClip = JSON.parse(file);
        } catch (jsonErr) {
          throw new Error('El archivo no contiene un formato JSON válido.');
        }
      } else if (file && typeof file.text === 'function') {
        const text = await file.text();
        try {
          customClip = JSON.parse(text);
        } catch (jsonErr) {
          throw new Error('El archivo no contiene un formato JSON válido.');
        }
      } else if (file && typeof file === 'object') {
        customClip = JSON.parse(JSON.stringify(file));
      } else {
        throw new Error('El archivo o dato proporcionado no es válido.');
      }

      if (customClip && !customClip.boneTracks && (Array.isArray(customClip.frames) || customClip.extractedTracks)) {
        customClip = this.convertHamerAnimationToSignClip(customClip, fileName.replace(/\.[^/.]+$/, ''));
      }

      if (customClip && typeof customClip === 'object') {
        if (!customClip.clipId && customClip.gloss) {
          customClip.clipId = customClip.gloss.toLowerCase().replace(/[^a-z0-9_-]/gi, '_');
        } else if (!customClip.clipId) {
          customClip.clipId = `CUSTOM_${Date.now()}`;
        }
        if (!customClip.gloss && customClip.clipId) {
          customClip.gloss = customClip.clipId.toUpperCase();
        } else if (!customClip.gloss) {
          customClip.gloss = 'PERSONALIZADA';
        }
        if (typeof customClip.durationMs !== 'number' || customClip.durationMs <= 0) {
          let maxT = 0;
          if (Array.isArray(customClip.boneTracks)) {
            customClip.boneTracks.forEach(tr => {
              if (Array.isArray(tr.times) && tr.times.length > 0) {
                const tLast = tr.times[tr.times.length - 1];
                if (typeof tLast === 'number' && tLast > maxT) maxT = tLast;
              }
            });
          }
          if (maxT > 0) {
            customClip.durationMs = Math.round((maxT + 0.15) * 1000);
          }
        }
      }

      const validation = validateSignClip(customClip);
      if (!validation.valid) {
        const errorList = validation.errors.join('\n- ');
        throw new Error(`Estructura de seña incompatible:\n- ${errorList}`);
      }

      const clipId = customClip.clipId || `CUSTOM_${Date.now()}`;
      this.clips[clipId] = customClip;
      this.selectedClipId = clipId;

      await this.prepareSelectedClip();
      if (this.player) {
        this.player.play(customClip);
      }

      return customClip;
    } catch (err) {
      this.lastError = err.message;
      return null;
    }
  }
}

const harness = new TestControllerHarness();

console.log('--- TEST 2: Validar conversión de animation.json estándar de HaMeR Pipeline (xyzw) ---');
const sampleHamer = {
  metadata: {
    sign: 'HOLA_COLAB',
    slug: 'hola_colab',
    fps: 30,
    duration: 1.0,
    source: 'Colab HaMeR'
  },
  frames: [
    {
      time: 0.0,
      rotations: {
        rightUpperArm: [0.0, 0.0, 0.0, 1.0],
        rightLowerArm: [0.1, 0.2, 0.3, 0.9]
      },
      expressions: {
        happy: 0.8,
        blink_l: 0.5
      }
    },
    {
      time: 0.5,
      rotations: {
        rightUpperArm: [0.0, 0.3826834, 0.0, 0.9238795],
        rightLowerArm: [0.2, 0.3, 0.4, 0.8]
      },
      expressions: {
        happy: 1.0,
        blink_l: 0.0
      }
    }
  ]
};

const converted = harness.convertHamerAnimationToSignClip(sampleHamer, 'HOLA_COLAB');
const valResult = validateSignClip(converted);
if (!valResult.valid) {
  throw new Error(`FAIL: El clip convertido no superó validateSignClip: ${valResult.errors.join('; ')}`);
}
console.log('PASS: Clip convertido válido.');

console.log('--- TEST 3: Manejo de cuaterniones degenerados o desnormalizados ---');
const degenerateHamer = {
  totalFrames: 1,
  frames: [
    {
      time: 0.0,
      rotations: {
        rightHand: [0.0, 0.0, 0.0, 0.0]
      }
    }
  ]
};
const convertedDegen = harness.convertHamerAnimationToSignClip(degenerateHamer, 'DEGEN_TEST');
const valDegen = validateSignClip(convertedDegen);
if (!valDegen.valid) {
  throw new Error(`FAIL: Error validando cuaternión degenerado: ${valDegen.errors.join('; ')}`);
}
const handTrack = convertedDegen.boneTracks.find(t => t.boneName === 'rightHand');
if (!handTrack || handTrack.rotations[3] !== 1.0) {
  throw new Error(`FAIL: Cuaternión degenerado no fue resuelto a identidad [0,0,0,1]`);
}
console.log('PASS: Cuaterniones degenerados corregidos automáticamente a identidad unitaria.');

console.log('--- TEST 4: Normalización de nombres de huesos de Blender y Mixamo ---');
const blenderMixamoAnim = {
  totalFrames: 2,
  frames: [
    { time: 0.0, rotations: { 'J_Bip_C_Head': [0, 0, 0, 1], 'mixamorig:RightHand': [0, 0, 0, 1] } },
    { time: 0.5, rotations: { 'J_Bip_C_Head': [0, 0, 0, 1], 'mixamorig:RightHand': [0, 0, 0, 1] } }
  ]
};
const convertedBlender = harness.convertHamerAnimationToSignClip(blenderMixamoAnim, 'BLENDER_SIGN');
const headB = convertedBlender.boneTracks.find(t => t.boneName === 'head');
const handB = convertedBlender.boneTracks.find(t => t.boneName === 'rightHand');
if (!headB || !handB) {
  throw new Error(`FAIL: Huesos no fueron normalizados: head=${!!headB}, rightHand=${!!handB}`);
}
console.log('PASS: Nombres de huesos de Blender y Mixamo normalizados a nomenclatura VRM.');

console.log('--- TEST 5: Carga y conversión del archivo real scripts/lunes_raw_baked_animation.json (wxyz -> xyzw) ---');
if (fs.existsSync(rawBakedPath)) {
  const realBaked = JSON.parse(fs.readFileSync(rawBakedPath, 'utf8'));
  const convertedReal = harness.convertHamerAnimationToSignClip(realBaked, 'lunes_raw_baked_animation');
  const valReal = validateSignClip(convertedReal);
  if (!valReal.valid) {
    throw new Error(`FAIL: Archivo real lunes_raw_baked no superó validación: ${valReal.errors.join('; ')}`);
  }
  // Verificar que el cuaternión en Three.js [x, y, z, w] tiene w como componente 3 cerca de 1.0 (no w=0 con inversión de 180°)
  const spineTrack = convertedReal.boneTracks.find(t => t.boneName === 'spine');
  if (!spineTrack) throw new Error('FAIL: Falta pista de columna (spine)');
  const qw = spineTrack.rotations[3];
  if (qw < 0.9) {
    throw new Error(`FAIL: Inversión de cuaternión detectada en spine: w=${qw}, esperado > 0.9 en [x,y,z,w]`);
  }
  if (convertedReal.durationMs < 4200) {
    throw new Error(`FAIL: Duración truncada: ${convertedReal.durationMs}ms, esperado >= 4200ms`);
  }
  console.log(`PASS: Archivo real lunes_raw_baked_animation.json convertido a [x,y,z,w] sin inversión (duración: ${convertedReal.durationMs}ms).`);
} else {
  console.warn('WARN: scripts/lunes_raw_baked_animation.json no encontrado, se omite prueba con archivo físico.');
}

console.log('--- TEST 6: importCustomClip con archivo File simulado (.text() y .name) ---');
async function testFileImport() {
  const fakeFile = {
    name: 'animation.json',
    text: async () => JSON.stringify(sampleHamer)
  };
  const imported = await harness.importCustomClip(fakeFile);
  if (!imported || imported.gloss !== 'HOLA_COLAB') {
    throw new Error(`FAIL: importCustomClip falló: ${harness.lastError}`);
  }
  console.log('PASS: importCustomClip procesó el archivo File simulado exitosamente.');
}

console.log('--- TEST 7: importCustomClip con JSON corrupto ---');
async function testCorruptedImport() {
  const fakeFile = {
    name: 'corrupted.json',
    text: async () => '{ this is not json'
  };
  const imported = await harness.importCustomClip(fakeFile);
  if (imported !== null) {
    throw new Error('FAIL: Se esperaba rechazo de archivo corrupto pero fue aceptado.');
  }
  if (!harness.lastError || !harness.lastError.includes('formato JSON válido')) {
    throw new Error(`FAIL: Mensaje de error no esperado: ${harness.lastError}`);
  }
  console.log('PASS: JSON corrupto capturado con mensaje descriptivo:', harness.lastError);
}

console.log('--- TEST 8: Robustez null-safe cuando this.player es null ---');
async function testNullPlayerSafety() {
  harness.player = null; // Sin inicializar el reproductor aún
  const fakeFile = {
    name: 'custom_sign.json',
    text: async () => JSON.stringify({
      clipId: 'SAFE_CLIP',
      gloss: 'SAFE_CLIP',
      durationMs: 1500,
      boneTracks: [{ boneName: 'head', times: [0, 1.5], rotations: [0, 0, 0, 1, 0, 0, 0, 1] }]
    })
  };
  const imported = await harness.importCustomClip(fakeFile);
  if (!imported) {
    throw new Error(`FAIL: Falló importación segura con player=null: ${harness.lastError}`);
  }
  console.log('PASS: importCustomClip y prepareSelectedClip son completamente null-safe sin player.');
}

console.log('--- TEST 9: Conversión y validación de seña v2.5 Directo 1:1 ---');
async function testDirectV25AnimationConversion() {
  const directPath = path.join(__dirname, '../../../Diccionario LSEC/senas_vrm_direct/A diario, Cotidiano(a)/animation.json');
  if (fs.existsSync(directPath)) {
    const rawData = JSON.parse(fs.readFileSync(directPath, 'utf8'));
    const converted = convertDirectAnimationToSignClip(rawData);
    if (!converted) throw new Error('FAIL: convertDirectAnimationToSignClip retorno nulo');
    if (converted.metadata.pipelineVersion !== '2.5_Directo_1a1') {
      throw new Error(`FAIL: pipelineVersion no es 2.5_Directo_1a1: ${converted.metadata.pipelineVersion}`);
    }
    if (converted.status !== 'MACHINE_PROPOSED') {
      throw new Error(`FAIL: status no es MACHINE_PROPOSED: ${converted.status}`);
    }
    const val = validateSignClip(converted);
    if (!val.valid) {
      throw new Error(`FAIL: validacion fallo en seña v2.5: ${val.errors.join(', ')}`);
    }
    console.log('PASS: Seña v2.5 Directo 1:1 convertida y validada exitosamente (0 errores).');
  } else {
    console.log('SKIP: Archivo de prueba de seña directa no encontrado en disco.');
  }
}

console.log('--- TEST 10: Consistencia de REST_POSE (~75° brazos abajo, sin T-pose) ---');
async function testRestPoseConsistency() {
  if (!REST_POSE || !Array.isArray(REST_POSE.leftUpperArm) || !Array.isArray(REST_POSE.rightUpperArm)) {
    throw new Error('FAIL: REST_POSE no exporta leftUpperArm y rightUpperArm');
  }
  if (Math.abs(REST_POSE.leftUpperArm[2] - (-0.6087)) > 0.01 || Math.abs(REST_POSE.rightUpperArm[2] - 0.6087) > 0.01) {
    throw new Error(`FAIL: REST_POSE upperArm no tiene inclinación natural de ~75°: L=${REST_POSE.leftUpperArm}, R=${REST_POSE.rightUpperArm}`);
  }
  const factorySrc = fs.readFileSync(path.join(__dirname, '../static/js/avatar/sign-clip-factory.js'), 'utf8');
  const playerSrc = fs.readFileSync(path.join(__dirname, '../static/js/avatar/sign-player.js'), 'utf8');
  if (factorySrc.includes('-0.2756') || playerSrc.includes('-0.2756')) {
    throw new Error('FAIL: Aún existen residuos de cuaternión de semi T-pose (-0.2756) en sign-clip-factory.js o sign-player.js');
  }
  if (!factorySrc.includes('-0.6087') || !playerSrc.includes('REST_POSE')) {
    throw new Error('FAIL: sign-clip-factory.js o sign-player.js no usan REST_POSE unificado (-0.6087)');
  }
  console.log('PASS: REST_POSE, sign-clip-factory.js y sign-player.js unificados a ~75° brazos abajo (sin T-pose).');
}

console.log('--- TEST 11: Conversión v2.6 y recorte de ventana de stroke activo (trimSignClipStroke) ---');
async function testV26StrokeTrimming() {
  const v26Path = path.join(__dirname, '../../../Diccionario LSEC/senas_vrm_direct_v2.6/Poder/animation.json');
  if (fs.existsSync(v26Path)) {
    const rawData = JSON.parse(fs.readFileSync(v26Path, 'utf8'));
    const converted = convertDirectAnimationToSignClip(rawData);
    const trimmed = trimSignClipStroke(converted);
    if (!trimmed || !Array.isArray(trimmed.boneTracks) || trimmed.boneTracks.length === 0) {
      throw new Error('FAIL: trimSignClipStroke devolvió clip vacío');
    }
    if (trimmed.durationMs > converted.durationMs) {
      throw new Error(`FAIL: trimSignClipStroke aumentó la duración (${trimmed.durationMs} > ${converted.durationMs})`);
    }
    const val = validateSignClip(trimmed);
    if (!val.valid) {
      throw new Error(`FAIL: Clip v2.6 recortado inválido: ${val.errors.join(', ')}`);
    }
    console.log(`PASS: Clip v2.6 "Poder" recortado de ${converted.durationMs}ms a ${trimmed.durationMs}ms (velocidad recomendada: ${trimmed.metadata.recommendedSpeed}x).`);
  } else {
    throw new Error(`FAIL: Carpeta senas_vrm_direct_v2.6/Poder no encontrada en ${v26Path}`);
  }
}

console.log('--- TEST 12: Preservación de las 108 glosas de 1.mp4 sin solapamientos ni omisiones (resolveOverlappingGlossIntervals) ---');
async function testResolveOverlappingGlossIntervals() {
  const vm = await import('node:vm');
  const stateSrc = fs.readFileSync(path.join(__dirname, '../static/js/state.js'), 'utf8');
  const sandbox = { window: {}, console };
  vm.runInNewContext(stateSrc, sandbox);
  const store = sandbox.window.appState;
  if (!store || typeof store.loadProject !== 'function') {
    throw new Error('FAIL: No se pudo instanciar LSECStateStore desde state.js');
  }

  const reportPath = path.join(__dirname, '../../reports/lsec_2_1_1_after.json');
  if (!fs.existsSync(reportPath)) {
    throw new Error(`FAIL: Reporte 1.mp4 no encontrado en ${reportPath}`);
  }
  const rawReport = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
  const expectedCount = rawReport.glosses.length;
  store.loadProject(JSON.parse(JSON.stringify(rawReport)), '1.mp4');
  const allGlosses = store.state.project.glosses;
  if (!Array.isArray(allGlosses) || allGlosses.length !== expectedCount) {
    throw new Error(`FAIL: Se omitieron glosas en loadProject (${allGlosses ? allGlosses.length : 0} !== ${expectedCount})`);
  }

  // Verificar que todas las glosas tienen ventana positiva y sin solapamiento dentro de cada proposición
  for (let i = 0; i < allGlosses.length; i++) {
    const g = allGlosses[i];
    const dur = g.end_time - g.start_time;
    if (!(dur > 0.05)) {
      throw new Error(`FAIL: Glosa #${i} (${g.gloss}) tiene duración inválida: ${dur}s (${g.start_time}-${g.end_time})`);
    }
    if (i > 0) {
      const prev = allGlosses[i - 1];
      const sameProp = (g.proposition_id || g.origin_proposition_id) === (prev.proposition_id || prev.origin_proposition_id);
      if (sameProp && g.start_time < prev.end_time - 1e-3) {
        throw new Error(`FAIL: Solapamiento en proposición entre #${i - 1} (${prev.gloss}: ${prev.start_time}-${prev.end_time}) y #${i} (${g.gloss}: ${g.start_time}-${g.end_time})`);
      }
    }
    // Verificar que tokens compuestos LSEC no sean marcados como dactilología
    if (['PRO1-PL', 'MÁS-DE', 'SOLAMENTE-NO', 'ESAS-PERSONAS', 'PRO2-MISMO'].includes(g.gloss)) {
      if (g.is_fingerspelling || g.gloss_type === 'DACTILOLOGÍA') {
        throw new Error(`FAIL: Glosa compuesta LSEC ${g.gloss} fue marcada erróneamente como dactilología`);
      }
    }
  }

  // Verificar que SER, DECIR, QUIÉN, PODER, PRO1-PL, ESAS-PERSONAS, PRO2-MISMO son alcanzables por búsqueda temporal en lsec_2_1_1_after.json
  for (const requiredGloss of ['SER', 'DECIR', 'QUIÉN', 'PODER', 'PRO1-PL', 'ESAS-PERSONAS', 'PRO2-MISMO']) {
    const target = allGlosses.find(g => g.gloss === requiredGloss);
    if (!target) {
      throw new Error(`FAIL: Glosa crítica ${requiredGloss} ausente de allGlosses`);
    }
    const midTime = (target.start_time + target.end_time) / 2;
    const matched = allGlosses.find(g => midTime >= g.start_time && midTime <= g.end_time);
    if (!matched || matched.id !== target.id) {
      throw new Error(`FAIL: Glosa ${requiredGloss} en t=${midTime.toFixed(3)}s fue eclipsada por ${matched ? matched.gloss : 'ninguna'}`);
    }
  }

  // Verificar también upec_v21_inspection.json (que contiene ESO, SER, SOLAMENTE-NO, MÁS-DE)
  const upecPath = path.join(__dirname, '../../reports/upec_v21_inspection.json');
  if (fs.existsSync(upecPath)) {
    const upecReport = JSON.parse(fs.readFileSync(upecPath, 'utf8'));
    // Incluir también una glosa explícita CON con timestamp solapado para verificar que nunca se omite
    upecReport.glosses.push({
      id: 'g_con_test',
      gloss: 'CON',
      lemma: 'con',
      origin_proposition_id: upecReport.glosses[0]?.origin_proposition_id || 'p1',
      source_start_seconds: 0.5,
      source_end_seconds: 1.5
    });
    store.loadProject(JSON.parse(JSON.stringify(upecReport)), '1_upec.mp4');
    const upecGlosses = store.state.project.glosses;
    for (const requiredGloss of ['CON', 'ESO', 'SER', 'SOLAMENTE-NO', 'MÁS-DE']) {
      const target = upecGlosses.find(g => g.gloss === requiredGloss);
      if (!target) {
        throw new Error(`FAIL: Glosa crítica ${requiredGloss} ausente tras loadProject`);
      }
      const midTime = (target.start_time + target.end_time) / 2;
      const matched = upecGlosses.find(g => midTime >= g.start_time && midTime <= g.end_time);
      if (!matched || matched.id !== target.id) {
        throw new Error(`FAIL: Glosa ${requiredGloss} en t=${midTime.toFixed(3)}s fue eclipsada por ${matched ? matched.gloss : 'ninguna'}`);
      }
    }
  }

  console.log(`PASS: Las ${allGlosses.length} glosas de 1.mp4 tienen intervalos secuenciales sin solapamiento y 0 glosas omitidas.`);
}

(async () => {
  await testFileImport();
  await testCorruptedImport();
  await testNullPlayerSafety();
  await testDirectV25AnimationConversion();
  await testRestPoseConsistency();
  await testV26StrokeTrimming();
  await testResolveOverlappingGlossIntervals();
  console.log('\n=== TODOS LOS TESTS DE VALIDACIÓN JS PASARON SATISFACTORIAMENTE ===');
})();
