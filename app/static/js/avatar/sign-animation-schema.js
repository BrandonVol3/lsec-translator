/**
 * LSEC Studio — Esquema y Validador de Clips de Animación de Señas
 * 
 * Define la estructura de datos estandarizada para clips de animación de
 * Lengua de Señas Ecuatoriana (LSEC) y realiza validación estricta de:
 * - Identificadores y metadatos lingüísticos/técnicos.
 * - Duración y orden cronológico de marcas de tiempo.
 * - Pistas esqueléticas con cuaterniones normalizados [x, y, z, w].
 * - Pistas de expresiones faciales en rango [0, 1].
 * - Nombres normalizados de huesos humanoides compatibles con VRM 1.0.
 * 
 * Un clip inválido produce advertencias claras y se omite de forma controlada
 * sin interrumpir la ejecución de la aplicación.
 */

import {
  REST_POSE,
  UPPER_LIMB_REST_BONES,
  computeSignClipStrokeWindow,
  trimSignClipStroke
} from './sign-stroke-window.js';

export {
  REST_POSE,
  UPPER_LIMB_REST_BONES,
  computeSignClipStrokeWindow,
  trimSignClipStroke
};

export const HUMAN_BONE_NAMES = Object.freeze([
  // Torso y columna
  'hips',
  'spine',
  'chest',
  'upperChest',
  'neck',
  'head',
  'leftEye',
  'rightEye',
  // Extremidad superior izquierda
  'leftShoulder',
  'leftUpperArm',
  'leftLowerArm',
  'leftHand',
  'leftThumbMetacarpal',
  'leftThumbProximal',
  'leftThumbDistal',
  'leftIndexProximal',
  'leftIndexIntermediate',
  'leftIndexDistal',
  'leftMiddleProximal',
  'leftMiddleIntermediate',
  'leftMiddleDistal',
  'leftRingProximal',
  'leftRingIntermediate',
  'leftRingDistal',
  'leftLittleProximal',
  'leftLittleIntermediate',
  'leftLittleDistal',
  // Extremidad superior derecha
  'rightShoulder',
  'rightUpperArm',
  'rightLowerArm',
  'rightHand',
  'rightThumbMetacarpal',
  'rightThumbProximal',
  'rightThumbDistal',
  'rightIndexProximal',
  'rightIndexIntermediate',
  'rightIndexDistal',
  'rightMiddleProximal',
  'rightMiddleIntermediate',
  'rightMiddleDistal',
  'rightRingProximal',
  'rightRingIntermediate',
  'rightRingDistal',
  'rightLittleProximal',
  'rightLittleIntermediate',
  'rightLittleDistal',
  // Extremidades inferiores (base y estabilidad)
  'leftUpperLeg',
  'leftLowerLeg',
  'leftFoot',
  'leftToes',
  'rightUpperLeg',
  'rightLowerLeg',
  'rightFoot',
  'rightToes'
]);

export const VRM_EXPRESSION_NAMES = Object.freeze([
  'neutral',
  'happy',
  'angry',
  'sad',
  'relaxed',
  'surprised',
  'aa',
  'ih',
  'ou',
  'ee',
  'oh',
  'blink',
  'blinkLeft',
  'blinkRight',
  'lookUp',
  'lookDown',
  'lookLeft',
  'lookRight'
]);

export const ARKIT_BLENDSHAPE_NAMES = Object.freeze([
  'browDownLeft',
  'browDownRight',
  'browInnerUp',
  'browOuterUpLeft',
  'browOuterUpRight',
  'cheekPuff',
  'cheekSquintLeft',
  'cheekSquintRight',
  'eyeBlinkLeft',
  'eyeBlinkRight',
  'eyeLookDownLeft',
  'eyeLookDownRight',
  'eyeLookInLeft',
  'eyeLookInRight',
  'eyeLookOutLeft',
  'eyeLookOutRight',
  'eyeLookUpLeft',
  'eyeLookUpRight',
  'eyeSquintLeft',
  'eyeSquintRight',
  'eyeWideLeft',
  'eyeWideRight',
  'jawForward',
  'jawLeft',
  'jawOpen',
  'jawRight',
  'mouthClose',
  'mouthDimpleLeft',
  'mouthDimpleRight',
  'mouthFrownLeft',
  'mouthFrownRight',
  'mouthFunnel',
  'mouthLeft',
  'mouthLowerDownLeft',
  'mouthLowerDownRight',
  'mouthPressLeft',
  'mouthPressRight',
  'mouthPucker',
  'mouthRight',
  'mouthRollLower',
  'mouthRollUpper',
  'mouthShrugLower',
  'mouthShrugUpper',
  'mouthSmileLeft',
  'mouthSmileRight',
  'mouthStretchLeft',
  'mouthStretchRight',
  'mouthUpperUpLeft',
  'mouthUpperUpRight',
  'noseSneerLeft',
  'noseSneerRight',
  'tongueOut'
]);

export const ALL_EXPRESSION_TRACK_NAMES = Object.freeze([
  ...VRM_EXPRESSION_NAMES,
  ...ARKIT_BLENDSHAPE_NAMES
]);

export const CLIP_STATUSES = Object.freeze([
  'DEMO_ONLY',
  'MACHINE_PROPOSED',
  'EXPERIMENTAL',
  'REQUIRES_LSEC_VALIDATION',
  'HUMAN_REVIEWED',
  'VALIDATED_LSEC'
]);

/**
 * Valida un objeto clip contra el esquema de animación LSEC.
 * @param {Object} clip - Objeto que representa el clip de animación.
 * @returns {{ valid: boolean, errors: string[], warnings: string[] }}
 */
export function validateSignClip(clip) {
  const errors = [];
  const warnings = [];

  if (!clip || typeof clip !== 'object') {
    return {
      valid: false,
      errors: ['El clip debe ser un objeto JSON válido y no nulo.'],
      warnings: []
    };
  }

  // 1. Identificadores y glosa
  if (!clip.clipId || typeof clip.clipId !== 'string' || clip.clipId.trim() === '') {
    errors.push('El campo "clipId" es obligatorio y debe ser una cadena no vacía.');
  }

  if (!clip.gloss || typeof clip.gloss !== 'string' || clip.gloss.trim() === '') {
    errors.push('El campo "gloss" es obligatorio y debe ser una cadena no vacía.');
  }

  // 2. Duración
  if (typeof clip.durationMs !== 'number' || clip.durationMs <= 0 || !Number.isFinite(clip.durationMs)) {
    errors.push(`El campo "durationMs" debe ser un número finito mayor a 0. Valor recibido: ${clip.durationMs}`);
  }

  const durationSec = (clip.durationMs || 0) / 1000.0;

  // 3. Estado y trazabilidad
  if (clip.status && !CLIP_STATUSES.includes(clip.status)) {
    warnings.push(`Estado "${clip.status}" no reconocido en el catálogo estándar de estados.`);
  }

  if (clip.validationStatus !== 'VALIDATED_LSEC') {
    if (!clip.metadata || clip.metadata.isValidatedLSEC !== false) {
      warnings.push('El clip no está validado como LSEC nativa. Debe registrarse explícitamente en metadata.isValidatedLSEC = false.');
    }
  }

  // 4. Pistas de huesos (Bone Tracks)
  if (!Array.isArray(clip.boneTracks)) {
    errors.push('El campo "boneTracks" debe ser un arreglo.');
  } else {
    clip.boneTracks.forEach((track, index) => {
      const trackId = `boneTrack[${index}](${track.boneName || 'sin_nombre'})`;

      if (!track.boneName || typeof track.boneName !== 'string') {
        errors.push(`${trackId}: "boneName" es obligatorio.`);
      } else if (!HUMAN_BONE_NAMES.includes(track.boneName)) {
        warnings.push(`${trackId}: El hueso "${track.boneName}" no pertenece a la nomenclatura estándar VRM.`);
      }

      if (!Array.isArray(track.times) || track.times.length === 0) {
        errors.push(`${trackId}: "times" debe ser un arreglo no vacío.`);
      } else {
        // Verificar orden ascendente y límites temporales
        let prevTime = -Infinity;
        for (let i = 0; i < track.times.length; i++) {
          const t = track.times[i];
          if (typeof t !== 'number' || !Number.isFinite(t) || t < 0) {
            errors.push(`${trackId}: El tiempo en índice ${i} (${t}) no es un número finito positivo.`);
            break;
          }
          if (t < prevTime) {
            errors.push(`${trackId}: Los tiempos deben ser estrictamente no decrecientes. ${t} < ${prevTime}`);
            break;
          }
          if (t > durationSec + 0.05) {
            warnings.push(`${trackId}: El tiempo ${t}s excede la duración declarada del clip (${durationSec}s).`);
          }
          prevTime = t;
        }
      }

      // Validar cuaterniones de rotación (4 componentes x, y, z, w por keyframe)
      if (!Array.isArray(track.rotations)) {
        errors.push(`${trackId}: "rotations" debe ser un arreglo de cuaterniones.`);
      } else {
        const expectedRotCount = (track.times ? track.times.length : 0) * 4;
        if (track.rotations.length !== expectedRotCount) {
          errors.push(`${trackId}: Longitud de "rotations" (${track.rotations.length}) debe ser exactamente 4 veces la de "times" (${expectedRotCount}).`);
        } else {
          // Validar longitud unitaria de cada cuaternión
          for (let k = 0; k < track.rotations.length; k += 4) {
            const x = track.rotations[k];
            const y = track.rotations[k + 1];
            const z = track.rotations[k + 2];
            const w = track.rotations[k + 3];

            if ([x, y, z, w].some(v => typeof v !== 'number' || !Number.isFinite(v))) {
              errors.push(`${trackId}: Cuaternión en fotograma ${k / 4} contiene componentes no numéricas.`);
              break;
            }

            const normSq = x * x + y * y + z * z + w * w;
            if (Math.abs(normSq - 1.0) > 0.15 && normSq > 0.0001) {
              warnings.push(`${trackId}: Cuaternión en fotograma ${k / 4} no está estrictamente normalizado (norma^2 = ${normSq.toFixed(3)}). Se normalizará automáticamente.`);
            } else if (normSq <= 0.0001) {
              errors.push(`${trackId}: Cuaternión degenerado con magnitud cercana a 0 en fotograma ${k / 4}.`);
              break;
            }
          }
        }
      }

      // Validar posiciones opcionales (3 componentes x, y, z por keyframe)
      if (track.positions) {
        if (!Array.isArray(track.positions)) {
          errors.push(`${trackId}: "positions" debe ser un arreglo si está presente.`);
        } else {
          const expectedPosCount = (track.times ? track.times.length : 0) * 3;
          if (track.positions.length !== expectedPosCount) {
            errors.push(`${trackId}: Longitud de "positions" (${track.positions.length}) debe ser exactamente 3 veces la de "times" (${expectedPosCount}).`);
          }
        }
      }
    });
  }

  // 5. Pistas de expresiones faciales (Expression Tracks)
  if (clip.expressionTracks && !Array.isArray(clip.expressionTracks)) {
    errors.push('El campo "expressionTracks" debe ser un arreglo si está presente.');
  } else if (Array.isArray(clip.expressionTracks)) {
    clip.expressionTracks.forEach((track, index) => {
      const trackId = `expressionTrack[${index}](${track.expressionName || 'sin_nombre'})`;

      if (!track.expressionName || typeof track.expressionName !== 'string') {
        errors.push(`${trackId}: "expressionName" es obligatorio.`);
      }

      if (!Array.isArray(track.times) || track.times.length === 0) {
        errors.push(`${trackId}: "times" debe ser un arreglo no vacío.`);
      }

      if (!Array.isArray(track.values) || (track.times && track.values.length !== track.times.length)) {
        errors.push(`${trackId}: Longitud de "values" debe coincidir exactamente con "times".`);
      } else {
        track.values.forEach((val, vIdx) => {
          if (typeof val !== 'number' || val < 0 || val > 1) {
            errors.push(`${trackId}: El valor en índice ${vIdx} (${val}) debe estar en el rango [0.0, 1.0].`);
          }
        });
      }
    });
  }

  const valid = errors.length === 0;
  if (!valid) {
    console.warn(`[SignAnimationSchema] Clip "${clip.clipId || 'desconocido'}" rechazado por validación:`, errors);
  } else if (warnings.length > 0) {
    console.info(`[SignAnimationSchema] Clip "${clip.clipId}" válido con advertencias:`, warnings);
  }

  return { valid, errors, warnings };
}

export const BONE_LOWER_MAP = new Map((HUMAN_BONE_NAMES || []).map(b => [b.toLowerCase(), b]));

export const BONE_ALIASES = Object.freeze({
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
});

export function normalizeBoneName(name) {
  if (typeof name !== 'string') return name;
  const clean = name.replace(/^mixamorig:?/i, '').trim();
  const lower = clean.toLowerCase();
  if (BONE_ALIASES[lower]) return BONE_ALIASES[lower];
  if (BONE_LOWER_MAP.has(lower)) return BONE_LOWER_MAP.get(lower);
  return clean;
}

export function detectDatasetQuaternionLayout(data) {
  const meta = (data && data.metadata) || {};
  const explicit = (meta.quaternionOrder || meta.quaternionFormat || data.quaternionOrder || data.quaternionFormat || '').toLowerCase();
  if (explicit.includes('wxyz') || explicit.includes('[w, x, y, z]') || explicit.includes('[w,x,y,z]')) return 'wxyz';
  if (explicit.includes('xyzw') || explicit.includes('[x, y, z, w]') || explicit.includes('[x,y,z,w]')) return 'xyzw';

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

export const EXPLICIT_FACIAL_LEXICAL_SET = new Set([
  'soplar', 'silbar', 'silbido', 'inflar',
  'chupar', 'succionar', 'besar', 'beso', 'sorber',
  'escupir', 'lengua', 'lamer',
  'broma pesada', 'broma-pesado', 'burla', 'burlarse', 'ladron',
  'por favor', 'por-favor', 'por-favor-3',
  'alegre', 'alegria', 'feliz', 'felicidad', 'sonreir', 'sonrisa',
  'reir', 'risa', 'carcajada', 'contento', 'contenta', 'divertido',
  'divertirse', 'chiste', 'gracioso', 'broma', 'entusiasmo',
  'entusiasmado', 'optimista', 'buen humor', 'buen-humor',
  'triste', 'tristeza', 'llorar', 'llanto', 'lagrima', 'lagrimas',
  'sufrir', 'sufrimiento', 'deprimido', 'depresion', 'melancolia',
  'desanimado', 'desanimo', 'luto', 'duelo', 'lamento', 'lamentar',
  'infeliz', 'angustia', 'adolorido', 'dolor',
  'enojado', 'enojo', 'enojarse', 'bravo', 'rabia', 'ira', 'furioso',
  'furia', 'molesto', 'disgusto', 'disgustado', 'odio', 'odiar',
  'rencor', 'coraje', 'malgenio', 'mal humor', 'mal-humor',
  'furor', 'colera', 'indignado', 'celos', 'celoso',
  'sorpresa', 'sorprendido', 'sorprender', 'asombro', 'asombrado',
  'asombrar', 'susto', 'asustado', 'asustar', 'miedo', 'temor',
  'terror', 'panico', 'espanto', 'impactado', 'admiracion', 'impresionado',
  'gritar', 'grito', 'bostezar', 'bostezo', 'vomitar', 'vomito',
  'morder', 'mordida', 'masticar',
  'dormir', 'dormitar', 'dormilon', 'parpadear', 'guinar',
  'duda', 'dudar', 'pregunta', 'preguntar'
]);

/**
 * Determina si una seña requiere explícitamente activar una expresión facial
 * según sus metadatos (categoría ROSTRO / nonManualStandard) o padrón léxico auditado.
 * Por defecto retorna `false` (modo neutral estricto).
 * @param {string} signName
 * @param {Object} [meta]
 * @returns {boolean}
 */
export function hasExplicitFacialExpressionForSign(signName = '', meta = {}) {
  if (meta && typeof meta === 'object') {
    if (typeof meta.hasExplicitFacialExpression === 'boolean') {
      return meta.hasExplicitFacialExpression;
    }
    if (meta.nonManualStandard && typeof meta.nonManualStandard.hasExplicitFacialExpression === 'boolean') {
      return meta.nonManualStandard.hasExplicitFacialExpression;
    }
    if (
      meta.faceOnly === true ||
      meta.solo_rostro === true ||
      meta.handshape === 'configuracion_manual_rostro' ||
      (typeof meta.handshapeVariant === 'string' && meta.handshapeVariant.includes('rostro'))
    ) {
      return true;
    }
  }

  const rawText = String(signName || (meta && (meta.sign || meta.gloss || meta.slug)) || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/\([a-z]{1,3}\)/g, '')
    .trim();

  if (!rawText) return false;
  if (EXPLICIT_FACIAL_LEXICAL_SET.has(rawText)) return true;

  const parts = rawText.split(/[,;/|]+/).map(s => s.trim()).filter(Boolean);
  for (const part of parts) {
    if (EXPLICIT_FACIAL_LEXICAL_SET.has(part)) return true;
  }
  return false;
}

/**
 * Convierte un objeto de animación v2.5 / HaMeR / Colab (frames o extractedTracks)
 * en un clip estándar compatible con el esquema SignClip de LSEC Studio y SignPlayer.
 * @param {Object} data - Datos JSON con frames y metadata
 * @param {string} defaultName - Nombre base para la seña
 * @returns {Object} Clip estándar SignClip
 */
export function convertDirectAnimationToSignClip(data, defaultName = 'SEÑA_LSEC') {
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

  const isFaceOnlyRestArms = Boolean(
    meta.faceOnly === true ||
    meta.armsInRestPose === true ||
    meta.handshape === 'configuracion_manual_rostro'
  );

  const hasExplicitFacialExpression = hasExplicitFacialExpressionForSign(signName, meta);

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
          if (isFaceOnlyRestArms && UPPER_LIMB_REST_BONES.has(bone)) {
            const restQ = REST_POSE[bone] || [0, 0, 0, 1];
            bEntry.rotations.push(restQ[0], restQ[1], restQ[2], restQ[3]);
          } else {
            const [qx, qy, qz, qw] = sanitizeQuat(q);
            bEntry.rotations.push(qx, qy, qz, qw);
          }
        }
      }

      if (hasExplicitFacialExpression) {
        const exprSources = [f.expressions, f.blendshapes];
        for (const exprSource of exprSources) {
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
      if (isFaceOnlyRestArms && UPPER_LIMB_REST_BONES.has(bone)) {
        const restQ = REST_POSE[bone] || [0, 0, 0, 1];
        for (let k = 0; k < times.length; k++) {
          rotations.push(restQ[0], restQ[1], restQ[2], restQ[3]);
        }
      } else if (Array.isArray(track.rotations)) {
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
  // Garantizar continuidad antipodal (<q_k, q_{k-1}> >= 0) en todas las pistas óseas
  // para prevenir giros espurios de 360° en interpoladores SLERP/lineales.
  for (const track of boneTracks) {
    const rots = track && track.rotations;
    if (!Array.isArray(rots) || rots.length < 8) continue;
    for (let k = 4; k < rots.length; k += 4) {
      const dot = (
        rots[k - 4] * rots[k] +
        rots[k - 3] * rots[k + 1] +
        rots[k - 2] * rots[k + 2] +
        rots[k - 1] * rots[k + 3]
      );
      if (dot < 0) {
        rots[k] = -rots[k];
        rots[k + 1] = -rots[k + 1];
        rots[k + 2] = -rots[k + 2];
        rots[k + 3] = -rots[k + 3];
      }
    }
  }
  let expressionTracks = [];
  if (hasExplicitFacialExpression) {
    expressionTracks = Array.from(exprMap.values()).filter(et => {
      if (!et || !Array.isArray(et.values) || et.values.length === 0) return false;
      if (et.expressionName === 'neutral') return true;
      return et.values.some(v => v > 0.005);
    });
  }
  if (expressionTracks.length === 0) {
    expressionTracks = [
      {
        expressionName: 'neutral',
        times: [0.0, Math.max(0.1, finalDurationSec)],
        values: [1.0, 1.0]
      }
    ];
  }

  const handStd = (meta.handStandardization && typeof meta.handStandardization === 'object') ? meta.handStandardization : null;
  const isV27 = Boolean(
    (handStd && handStd.version === 'v2.7') ||
    String(meta.version_served || '') === '2.7' ||
    String(meta.pipelineVersion || '').startsWith('2.7')
  );
  const rawPipelineVer = meta.pipelineVersion || meta.pipeline_version || '';
  const pipelineVer = isV27
    ? (String(rawPipelineVer).startsWith('2.7') ? rawPipelineVer : '2.7_Estandarizado')
    : (rawPipelineVer || '2.6_Directo_1a1_corregido');
  const isDirectPipeline = isV27 || String(pipelineVer).startsWith('2.7') || String(pipelineVer).startsWith('2.6') || String(pipelineVer).startsWith('2.5');
  const isV26 = !isV27 && String(pipelineVer).startsWith('2.6');

  const rawClip = {
    clipId: clipId,
    gloss: signName,
    durationMs: durationMs,
    status: isDirectPipeline ? 'MACHINE_PROPOSED' : 'DEMO_ONLY',
    validationStatus: 'REQUIRES_LSEC_VALIDATION',
    metadata: {
      ...meta,
      isValidatedLSEC: false,
      source: isDirectPipeline
        ? (isV27
          ? 'Pipeline LSEC v2.7 Estandarizado (Configuración Manual)'
          : (isV26 ? 'Pipeline LSEC v2.6 Directo 1:1 Corregido' : 'Pipeline LSEC v2.5 Directo 1:1'))
        : 'HaMeR Pipeline',
      quaternionOrder: 'xyzw',
      pipelineVersion: pipelineVer,
      standardizedVersion: isV27 ? '2.7' : (isV26 ? '2.6' : '2.5'),
      version_served: meta.version_served || (isV27 ? '2.7' : (isV26 ? '2.6' : '2.5')),
      pure1to1Copy: meta.pure1to1Copy !== undefined ? meta.pure1to1Copy : true,
      hasExplicitFacialExpression,
      defaultNeutralFacialMode: !hasExplicitFacialExpression,
      facialArchetype: meta.facialArchetype || (hasExplicitFacialExpression ? 'explicit' : 'neutral')
    },
    boneTracks,
    expressionTracks
  };

  try {
    if (meta.stroke && typeof meta.stroke === 'object' && typeof meta.stroke.strokeStart === 'number' && typeof meta.stroke.strokeEnd === 'number') {
      rawClip.metadata.stroke = meta.stroke;
    }
    rawClip.metadata.strokeWindow = computeSignClipStrokeWindow(rawClip);
    if (!rawClip.metadata.stroke && rawClip.metadata.strokeWindow && rawClip.metadata.strokeWindow.strokeMeta) {
      rawClip.metadata.stroke = rawClip.metadata.strokeWindow.strokeMeta;
    }
  } catch (_) {}

  return rawClip;
}
