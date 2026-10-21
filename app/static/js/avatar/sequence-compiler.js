/**
 * sequence-compiler.js
 * Compilador determinista de secuencias de glosas y motor de coarticulación C¹ para LSEC Studio.
 *
 * Responsabilidades:
 * 1. Recibir la lista de glosas del proyecto (con sus marcas de tiempo y proposiciones/segmentos)
 *    y los clips resueltos (con metadatos de trazo activo `stroke` de v2.7 o heurística de cadena completa).
 * 2. Compilar un plan temporal continuo y determinista:
 *    - Tope estricto de velocidad máxima en 1.6x (y mínima 0.70x).
 *    - Retropropagación (backpropagation) de holgura en secuencias densas y recuperación en pausas.
 *    - Límite de desfase acumulado (lag <= 1.0 s) con extensión controlada de cola PiP al final del video.
 *    - Cero caídas a reposo intra-oración (pausas <= 1.5 s mantienen la postura final con micro-movimiento
 *      respiratorio determinista <= 1°, ~0.2 Hz; solo pausas > 1.5 s o inicio/fin van a REST_POSE).
 * 3. Exponer la función pura `sample(t)` (y alias `pose(t)`) que evalúa directamente:
 *    `t (segundos) -> { bones, expressions, activeGloss, activeEntry, phase, lagSec, speed, isExtendedTail }`
 *    garantizando determinismo cuadro a cuadro (scrub aleatorio == reproducción secuencial == exportación 30 FPS).
 */

import {
  HUMAN_BONE_NAMES,
  ALL_EXPRESSION_TRACK_NAMES as FACIAL_EXPRESSION_NAMES,
  REST_POSE,
  computeSignClipStrokeWindow
} from './sign-animation-schema.js';

export const LEFT_ARM_BONES = Object.freeze([
  'leftShoulder', 'leftUpperArm', 'leftLowerArm', 'leftHand'
]);

export const RIGHT_ARM_BONES = Object.freeze([
  'rightShoulder', 'rightUpperArm', 'rightLowerArm', 'rightHand'
]);

const FINGER_SUFFIXES = [
  'ThumbMetacarpal', 'ThumbProximal', 'ThumbDistal',
  'IndexProximal', 'IndexIntermediate', 'IndexDistal',
  'MiddleProximal', 'MiddleIntermediate', 'MiddleDistal',
  'RingProximal', 'RingIntermediate', 'RingDistal',
  'LittleProximal', 'LittleIntermediate', 'LittleDistal'
];

export const LEFT_FINGER_BONES = Object.freeze(FINGER_SUFFIXES.map(s => `left${s}`));
export const RIGHT_FINGER_BONES = Object.freeze(FINGER_SUFFIXES.map(s => `right${s}`));
export const TORSO_HEAD_BONES = Object.freeze(['hips', 'spine', 'chest', 'upperChest', 'neck', 'head']);

export const ALL_COMPILER_BONES = Object.freeze([
  ...TORSO_HEAD_BONES,
  ...LEFT_ARM_BONES,
  ...LEFT_FINGER_BONES,
  ...RIGHT_ARM_BONES,
  ...RIGHT_FINGER_BONES
]);

const FINGER_BONE_SET = new Set([...LEFT_FINGER_BONES, ...RIGHT_FINGER_BONES]);
const LEFT_CHAIN_SET = new Set([...LEFT_ARM_BONES, ...LEFT_FINGER_BONES]);
const RIGHT_CHAIN_SET = new Set([...RIGHT_ARM_BONES, ...RIGHT_FINGER_BONES]);
const ARM_BONE_SET = new Set([...LEFT_ARM_BONES, ...RIGHT_ARM_BONES]);

export const CANONICAL_REST_BONES = Object.freeze((() => {
  const map = {};
  for (const b of HUMAN_BONE_NAMES) {
    const raw = REST_POSE[b] ? [...REST_POSE[b]] : [0, 0, 0, 1];
    const n = Math.hypot(raw[0], raw[1], raw[2], raw[3]) || 1;
    map[b] = Object.freeze([raw[0] / n, raw[1] / n, raw[2] / n, raw[3] / n]);
  }
  return map;
})());

// ---------------------------------------------------------------------------
// Álgebra de Cuaterniones y Espacio Tangente so(3)
// ---------------------------------------------------------------------------

export function quatNormalize(q) {
  if (!Array.isArray(q) || q.length < 4) return [0, 0, 0, 1];
  const x = Number(q[0]) || 0;
  const y = Number(q[1]) || 0;
  const z = Number(q[2]) || 0;
  const w = Number(q[3]) || 0;
  const norm = Math.hypot(x, y, z, w);
  if (norm < 1e-9) return [0, 0, 0, 1];
  return [x / norm, y / norm, z / norm, w / norm];
}

export function quatDot(q1, q2) {
  return q1[0] * q2[0] + q1[1] * q2[1] + q1[2] * q2[2] + q1[3] * q2[3];
}

export function quatEnsureSameHemisphere(qRef, qTarget) {
  const d = quatDot(qRef, qTarget);
  if (d < 0) {
    return [-qTarget[0], -qTarget[1], -qTarget[2], -qTarget[3]];
  }
  return [qTarget[0], qTarget[1], qTarget[2], qTarget[3]];
}

export function quatConjugate(q) {
  return [-q[0], -q[1], -q[2], q[3]];
}

export function quatMultiply(q1, q2) {
  const x1 = q1[0], y1 = q1[1], z1 = q1[2], w1 = q1[3];
  const x2 = q2[0], y2 = q2[1], z2 = q2[2], w2 = q2[3];
  return [
    w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
    w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
    w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2
  ];
}

export function quatAngleDeg(q1, q2) {
  if (!q1 || !q2) return 0;
  const qa = quatNormalize(q1);
  const qb = quatEnsureSameHemisphere(qa, quatNormalize(q2));
  const diffNorm = Math.hypot(qa[0] - qb[0], qa[1] - qb[1], qa[2] - qb[2], qa[3] - qb[3]);
  const sumNorm = Math.hypot(qa[0] + qb[0], qa[1] + qb[1], qa[2] + qb[2], qa[3] + qb[3]);
  return (2.0 * Math.atan2(diffNorm, sumNorm) * 180.0) / Math.PI;
}

/**
 * Mapa logarítmico en SO(3): q unitario -> vector rotación en radianes [rx, ry, rz].
 */
export function quatLogRad(q) {
  let qn = quatNormalize(q);
  if (qn[3] < 0) {
    qn = [-qn[0], -qn[1], -qn[2], -qn[3]];
  }
  const w = Math.min(1.0, Math.max(-1.0, qn[3]));
  const angle = 2.0 * Math.acos(w);
  const sinH = Math.sqrt(Math.max(0.0, 1.0 - w * w));
  if (sinH < 1e-7 || angle < 1e-7) {
    return [0, 0, 0];
  }
  const s = angle / sinH;
  return [qn[0] * s, qn[1] * s, qn[2] * s];
}

/**
 * Mapa exponencial en SO(3): vector rotación en radianes [rx, ry, rz] -> cuaternión unitario [x, y, z, w].
 */
export function quatExpRad(r) {
  const rx = Number(r[0]) || 0;
  const ry = Number(r[1]) || 0;
  const rz = Number(r[2]) || 0;
  const angle = Math.hypot(rx, ry, rz);
  if (angle < 1e-7) {
    return quatNormalize([0.5 * rx, 0.5 * ry, 0.5 * rz, 1.0]);
  }
  const half = 0.5 * angle;
  const s = Math.sin(half) / angle;
  return [rx * s, ry * s, rz * s, Math.cos(half)];
}

export function quatSlerp(q0, q1, u) {
  const t = Math.min(1.0, Math.max(0.0, u));
  const qa = quatNormalize(q0);
  const qb = quatEnsureSameHemisphere(qa, quatNormalize(q1));
  let dot = quatDot(qa, qb);
  if (dot > 0.9995) {
    return quatNormalize([
      qa[0] + t * (qb[0] - qa[0]),
      qa[1] + t * (qb[1] - qa[1]),
      qa[2] + t * (qb[2] - qa[2]),
      qa[3] + t * (qb[3] - qa[3])
    ]);
  }
  dot = Math.min(1.0, Math.max(-1.0, dot));
  const theta0 = Math.acos(dot);
  const theta = theta0 * t;
  const sinTheta = Math.sin(theta);
  const sinTheta0 = Math.sin(theta0);
  const s0 = Math.cos(theta) - dot * (sinTheta / sinTheta0);
  const s1 = sinTheta / sinTheta0;
  return [
    s0 * qa[0] + s1 * qb[0],
    s0 * qa[1] + s1 * qb[1],
    s0 * qa[2] + s1 * qb[2],
    s0 * qa[3] + s1 * qb[3]
  ];
}

/**
 * Polinomio de quinto orden de mínimo tirón (minimum-jerk):
 * s(0)=0, s(1)=1, s'(0)=s'(1)=0, s''(0)=s''(1)=0.
 */
export function minimumJerk(u) {
  const x = Math.min(1.0, Math.max(0.0, u));
  const x3 = x * x * x;
  return x3 * (10.0 + x * (-15.0 + 6.0 * x));
}

/**
 * Interpolación C¹ en SO(3) combinando minimum-jerk con spline cúbico de Hermite en el espacio tangente so(3).
 * Garantiza continuidad exacta de posición y velocidad angular sin sobreimpulso (overshoot).
 *
 * @param {number[]} q0 - Cuaternión inicial [x, y, z, w]
 * @param {number[]} q1 - Cuaternión final [x, y, z, w]
 * @param {number[]} [w0] - Velocidad angular inicial en so(3) [wx, wy, wz] (rad/s)
 * @param {number[]} [w1] - Velocidad angular final en so(3) [wx, wy, wz] (rad/s)
 * @param {number} durationSec - Duración T de la transición en segundos
 * @param {number} u - Parámetro normalizado [0, 1]
 */
export function interpolateSO3HermiteC1(q0, q1, w0, w1, durationSec, u) {
  const tau = Math.min(1.0, Math.max(0.0, u));
  const qa = quatNormalize(q0);
  const qb = quatEnsureSameHemisphere(qa, quatNormalize(q1));
  if (tau <= 0.0) return qa;
  if (tau >= 1.0) return qb;

  const dq = quatMultiply(quatConjugate(qa), qb);
  const deltaR = quatLogRad(dq);
  const deltaNorm = Math.hypot(deltaR[0], deltaR[1], deltaR[2]);
  const T = Math.max(0.05, Number(durationSec) || 0.20);

  const sMj = minimumJerk(tau);
  const hasW0 = Array.isArray(w0) && w0.length === 3 && (Math.abs(w0[0]) + Math.abs(w0[1]) + Math.abs(w0[2])) > 1e-4;
  const hasW1 = Array.isArray(w1) && w1.length === 3 && (Math.abs(w1[0]) + Math.abs(w1[1]) + Math.abs(w1[2])) > 1e-4;

  if (!hasW0 && !hasW1) {
    const rVec = [deltaR[0] * sMj, deltaR[1] * sMj, deltaR[2] * sMj];
    return quatNormalize(quatMultiply(qa, quatExpRad(rVec)));
  }

  // Acotar tangentes escaladas T*w solo ante valores físicamente extremos
  const maxTangentNorm = Math.max(4.0, 3.5 * deltaNorm + 2.5);
  const clampTangent = (w) => {
    if (!Array.isArray(w) || w.length < 3) return [0, 0, 0];
    const tx = (Number(w[0]) || 0) * T;
    const ty = (Number(w[1]) || 0) * T;
    const tz = (Number(w[2]) || 0) * T;
    const mag = Math.hypot(tx, ty, tz);
    if (mag <= maxTangentNorm || mag < 1e-7) return [tx, ty, tz];
    const scale = maxTangentNorm / mag;
    return [tx * scale, ty * scale, tz * scale];
  };

  // Inversa del Jacobiano derecho de SO(3): J_r^{-1}(u) v = d exp_{-u}^{-1}(v)
  // Necesaria en tau=1 donde r(1) = deltaR != 0 para que 2*(q(1)^{-1} q'(1)) = w1 exacto.
  const dExpInvNegSO3 = (uVec, vVec) => {
    const ux = uVec[0], uy = uVec[1], uz = uVec[2];
    const vx = vVec[0], vy = vVec[1], vz = vVec[2];
    const theta = Math.hypot(ux, uy, uz);
    if (theta < 1e-7) return [vx, vy, vz];
    // u x v
    const cx = uy * vz - uz * vy;
    const cy = uz * vx - ux * vz;
    const cz = ux * vy - uy * vx;
    // u x (u x v)
    const ccx = uy * cz - uz * cy;
    const ccy = uz * cx - ux * cz;
    const ccz = ux * cy - uy * cx;
    let eta;
    if (theta < 1e-3) {
      const t2 = theta * theta;
      eta = (1.0 / 12.0) + t2 / 720.0;
    } else {
      const half = 0.5 * theta;
      const sinHalf = Math.sin(half);
      const cosHalf = Math.cos(half);
      eta = (1.0 / (theta * theta)) - (cosHalf / (2.0 * theta * sinHalf));
    }
    return [
      vx + 0.5 * cx + eta * ccx,
      vy + 0.5 * cy + eta * ccy,
      vz + 0.5 * cz + eta * ccz
    ];
  };

  const m0 = clampTangent(w0);
  const m1 = dExpInvNegSO3(deltaR, clampTangent(w1));

  const t2 = tau * tau;
  const t3 = t2 * tau;
  const h10 = t3 - 2.0 * t2 + tau;
  const h01 = -2.0 * t3 + 3.0 * t2;
  const h11 = t3 - t2;

  // Polinomio cúbico de Hermite en so(3):
  // h10'(0)=1, h01'(0)=0, h11'(0)=0 => dr/dt(0) = m0 / T = w0 exactamente (continuidad C^1 en t0)
  // h10'(1)=0, h01'(1)=0, h11'(1)=1 => J_r(deltaR)*dr/dt(1) = w1 exactamente (continuidad C^1 en t1)
  const rVec = [
    h01 * deltaR[0] + h10 * m0[0] + h11 * m1[0],
    h01 * deltaR[1] + h10 * m0[1] + h11 * m1[1],
    h01 * deltaR[2] + h10 * m0[2] + h11 * m1[2]
  ];

  return quatNormalize(quatMultiply(qa, quatExpRad(rVec)));
}

// ---------------------------------------------------------------------------
// Evaluación de Pistas de un SignClip en un Tiempo Local
// ---------------------------------------------------------------------------

function sampleBoneTrackAt(track, localSec) {
  if (!track || !Array.isArray(track.times) || !Array.isArray(track.rotations) || track.times.length === 0) {
    return null;
  }
  const times = track.times;
  const rots = track.rotations;
  const n = times.length;
  if (n === 1 || localSec <= times[0]) {
    return quatNormalize([rots[0] ?? 0, rots[1] ?? 0, rots[2] ?? 0, rots[3] ?? 1]);
  }
  if (localSec >= times[n - 1]) {
    const b = (n - 1) * 4;
    return quatNormalize([rots[b] ?? 0, rots[b + 1] ?? 0, rots[b + 2] ?? 0, rots[b + 3] ?? 1]);
  }

  // Búsqueda binaria O(log N)
  let lo = 0;
  let hi = n - 1;
  while (lo + 1 < hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= localSec) lo = mid;
    else hi = mid;
  }

  const t0 = times[lo];
  const t1 = times[hi];
  const alpha = (t1 > t0 + 1e-6) ? (localSec - t0) / (t1 - t0) : 0.0;
  const b0 = lo * 4;
  const b1 = hi * 4;
  const q0 = [rots[b0] ?? 0, rots[b0 + 1] ?? 0, rots[b0 + 2] ?? 0, rots[b0 + 3] ?? 1];
  const q1 = [rots[b1] ?? 0, rots[b1 + 1] ?? 0, rots[b1 + 2] ?? 0, rots[b1 + 3] ?? 1];
  return quatSlerp(q0, q1, alpha);
}

function sampleExpressionTrackAt(track, localSec) {
  if (!track || !Array.isArray(track.times) || !Array.isArray(track.values) || track.times.length === 0) {
    return 0.0;
  }
  const times = track.times;
  const vals = track.values;
  const n = times.length;
  if (n === 1 || localSec <= times[0]) return Math.max(0, Math.min(1, Number(vals[0]) || 0));
  if (localSec >= times[n - 1]) return Math.max(0, Math.min(1, Number(vals[n - 1]) || 0));

  let lo = 0;
  let hi = n - 1;
  while (lo + 1 < hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= localSec) lo = mid;
    else hi = mid;
  }
  const t0 = times[lo];
  const t1 = times[hi];
  const alpha = (t1 > t0 + 1e-6) ? (localSec - t0) / (t1 - t0) : 0.0;
  const v = (Number(vals[lo]) || 0) + alpha * ((Number(vals[hi]) || 0) - (Number(vals[lo]) || 0));
  return Math.max(0, Math.min(1, v));
}

function buildPreparedClipDescriptor(clip) {
  if (!clip || typeof clip !== 'object' || !Array.isArray(clip.boneTracks)) return null;

  const isTrimmed = Boolean(clip.metadata && clip.metadata.isStrokeTrimmed);
  const rawTracks = (isTrimmed && Array.isArray(clip._untrimmedBoneTracks))
    ? clip._untrimmedBoneTracks
    : clip.boneTracks;
  const rawExprs = (isTrimmed && Array.isArray(clip._untrimmedExpressionTracks))
    ? clip._untrimmedExpressionTracks
    : (clip.expressionTracks || []);
  const usingUntrimmed = Boolean(isTrimmed && Array.isArray(clip._untrimmedBoneTracks));

  const trackMap = new Map();
  let maxTrackSec = 0;
  for (const tr of rawTracks) {
    if (tr && tr.boneName && Array.isArray(tr.times) && tr.times.length > 0) {
      trackMap.set(tr.boneName, tr);
      const lastT = tr.times[tr.times.length - 1];
      if (lastT > maxTrackSec) maxTrackSec = lastT;
    }
  }

  const exprMap = new Map();
  for (const et of rawExprs) {
    if (et && et.expressionName && Array.isArray(et.times) && et.times.length > 0) {
      exprMap.set(et.expressionName, et);
    }
  }

  let strokeMeta = (clip.metadata && clip.metadata.stroke) || null;
  if (!strokeMeta) {
    const win = computeSignClipStrokeWindow(clip);
    strokeMeta = win.strokeMeta || null;
  }

  const totalClipSec = Math.max(0.1, maxTrackSec || ((clip.durationMs || 1000) / 1000.0));
  let strokeStart = 0.0;
  let strokeEnd = totalClipSec;

  if (usingUntrimmed) {
    if (strokeMeta && typeof strokeMeta.strokeStart === 'number' && typeof strokeMeta.strokeEnd === 'number') {
      strokeStart = Math.max(0, Math.min(totalClipSec, strokeMeta.strokeStart));
      strokeEnd = Math.max(strokeStart + 0.05, Math.min(totalClipSec, strokeMeta.strokeEnd));
    } else if (clip.metadata && typeof clip.metadata.strokeStartSec === 'number' && typeof clip.metadata.strokeEndSec === 'number') {
      strokeStart = Math.max(0, clip.metadata.strokeStartSec);
      strokeEnd = Math.max(strokeStart + 0.05, clip.metadata.strokeEndSec);
    }
  } else if (!isTrimmed && strokeMeta && typeof strokeMeta.strokeStart === 'number' && typeof strokeMeta.strokeEnd === 'number') {
    strokeStart = Math.max(0, Math.min(totalClipSec, strokeMeta.strokeStart));
    strokeEnd = Math.max(strokeStart + 0.05, Math.min(totalClipSec, strokeMeta.strokeEnd));
  } else {
    strokeStart = 0.0;
    strokeEnd = totalClipSec;
  }

  const strokeDuration = Math.max(0.08, strokeEnd - strokeStart);
  const activeHands = (strokeMeta && strokeMeta.activeHands) || { left: true, right: true, dominant: 'right' };
  const flags = (strokeMeta && strokeMeta.flags) || {
    repeatedStroke: false,
    oneHanded: activeHands.left !== activeHands.right,
    tooShort: strokeDuration < 0.38,
    faceOnly: Boolean(clip.metadata && (clip.metadata.faceOnly || clip.metadata.armsInRestPose))
  };

  const sampleClipPoseAt = (clipTimeSec) => {
    const bones = {};
    for (const bName of ALL_COMPILER_BONES) {
      if (LEFT_CHAIN_SET.has(bName) && !activeHands.left) {
        bones[bName] = [...(CANONICAL_REST_BONES[bName] || [0, 0, 0, 1])];
        continue;
      }
      if (RIGHT_CHAIN_SET.has(bName) && !activeHands.right) {
        bones[bName] = [...(CANONICAL_REST_BONES[bName] || [0, 0, 0, 1])];
        continue;
      }
      const tr = trackMap.get(bName);
      const q = tr ? sampleBoneTrackAt(tr, clipTimeSec) : null;
      bones[bName] = q || [...(CANONICAL_REST_BONES[bName] || [0, 0, 0, 1])];
    }
    const expressions = {};
    for (const eName of FACIAL_EXPRESSION_NAMES) {
      const et = exprMap.get(eName);
      expressions[eName] = et ? sampleExpressionTrackAt(et, clipTimeSec) : 0.0;
    }
    if (exprMap.size === 0) {
      expressions.neutral = 1.0;
    }
    return { bones, expressions };
  };

  // Extraer velocidad tangente (rad/s) en cualquier instante del clip por diferencias finitas en so(3)
  const sampleClipVelocityAt = (clipTimeSec, dir = 'central') => {
    const eps = 2e-3;
    const tA = dir === 'forward' ? clipTimeSec : Math.max(0, clipTimeSec - eps);
    const tB = dir === 'backward' ? clipTimeSec : Math.min(totalClipSec, clipTimeSec + eps);
    const dt = tB - tA;
    const velMap = {};
    if (dt < 1e-5) {
      for (const bName of [...LEFT_ARM_BONES, ...RIGHT_ARM_BONES]) velMap[bName] = [0, 0, 0];
      return velMap;
    }
    const pA = sampleClipPoseAt(tA).bones;
    const pB = sampleClipPoseAt(tB).bones;
    for (const bName of [...LEFT_ARM_BONES, ...RIGHT_ARM_BONES]) {
      if ((LEFT_CHAIN_SET.has(bName) && !activeHands.left) || (RIGHT_CHAIN_SET.has(bName) && !activeHands.right)) {
        velMap[bName] = [0, 0, 0];
      } else {
        const dq = quatMultiply(quatConjugate(pA[bName]), quatEnsureSameHemisphere(pA[bName], pB[bName]));
        const r = quatLogRad(dq);
        velMap[bName] = [r[0] / dt, r[1] / dt, r[2] / dt];
      }
    }
    return velMap;
  };

  const startSnapshot = sampleClipPoseAt(strokeStart);
  const endSnapshot = sampleClipPoseAt(strokeEnd);
  const startVel = sampleClipVelocityAt(strokeStart, 'forward');
  const endVel = sampleClipVelocityAt(strokeEnd, 'backward');

  return {
    clip,
    trackMap,
    exprMap,
    strokeStart,
    strokeEnd,
    strokeDuration,
    originalDuration: (strokeMeta && strokeMeta.originalDuration) || totalClipSec,
    activeHands,
    flags,
    startSnapshot,
    endSnapshot,
    startVel,
    endVel,
    sampleClipPoseAt,
    sampleClipVelocityAt
  };
}

// ---------------------------------------------------------------------------
// Micro-movimiento Respiratorio Determinista C¹ en Mantenimiento / Reposo
// ---------------------------------------------------------------------------

function applyBreathingMicroMotion(baseBones, tSec, windowStartSec, windowEndSec, amplitudeDeg = 0.85, freqHz = 0.20) {
  const out = {};
  for (const [k, v] of Object.entries(baseBones)) {
    out[k] = [v[0], v[1], v[2], v[3]];
  }
  const dur = windowEndSec - windowStartSec;
  if (dur <= 0.08 || amplitudeDeg <= 0) return out;

  // Envolvente C¹ sin² en los bordes de la ventana para derivada nula en t=windowStart y t=windowEnd
  const localT = Math.max(0, Math.min(dur, tSec - windowStartSec));
  const rampSec = Math.min(0.18, 0.45 * dur);
  let env = 1.0;
  if (localT < rampSec) {
    const s = Math.sin((0.5 * Math.PI * localT) / rampSec);
    env = s * s;
  } else if (dur - localT < rampSec) {
    const s = Math.sin((0.5 * Math.PI * (dur - localT)) / rampSec);
    env = s * s;
  }

  const phase = 2.0 * Math.PI * freqHz * tSec;
  // Usar (1 - cos) / 2 o sin modulada por env para que en los extremos el desplazamiento y velocidad sean 0
  const breathRad = ((amplitudeDeg * Math.PI) / 180.0) * env * Math.sin(phase);
  if (Math.abs(breathRad) < 1e-6) return out;

  const applyDelta = (boneName, rx, ry, rz) => {
    if (!out[boneName]) return;
    const dq = quatExpRad([rx, ry, rz]);
    out[boneName] = quatNormalize(quatMultiply(out[boneName], dq));
  };

  applyDelta('spine', breathRad * 0.35, 0, 0);
  applyDelta('chest', breathRad * 0.55, 0, 0);
  applyDelta('leftUpperArm', breathRad * 0.25, 0, -breathRad * 0.20);
  applyDelta('rightUpperArm', breathRad * 0.25, 0, breathRad * 0.20);
  return out;
}

function computeMaxArmAngleDeg(bonesA, bonesB) {
  let maxDeg = 0;
  for (const bName of [...LEFT_ARM_BONES, ...RIGHT_ARM_BONES]) {
    const qa = (bonesA && bonesA[bName]) || CANONICAL_REST_BONES[bName];
    const qb = (bonesB && bonesB[bName]) || CANONICAL_REST_BONES[bName];
    const deg = quatAngleDeg(qa, qb);
    if (deg > maxDeg) maxDeg = deg;
  }
  return maxDeg;
}

function makeNeutralExpressions() {
  const expr = {};
  for (const eName of FACIAL_EXPRESSION_NAMES) {
    expr[eName] = eName === 'neutral' ? 1.0 : 0.0;
  }
  return expr;
}

function interpolateExpressions(exprA, exprB, u) {
  const s = minimumJerk(u);
  const out = {};
  for (const eName of FACIAL_EXPRESSION_NAMES) {
    const va = (exprA && typeof exprA[eName] === 'number') ? exprA[eName] : (eName === 'neutral' ? 1.0 : 0.0);
    const vb = (exprB && typeof exprB[eName] === 'number') ? exprB[eName] : (eName === 'neutral' ? 1.0 : 0.0);
    out[eName] = Math.max(0, Math.min(1, va + s * (vb - va)));
  }
  return out;
}

// ---------------------------------------------------------------------------
// Clase Principal: SequenceCompiler
// ---------------------------------------------------------------------------

export class SequenceCompiler {
  constructor(options = {}) {
    this.options = {
      maxSpeed: 1.6,
      minSpeed: 0.70,
      maxLagSec: 1.0,
      restGapThresholdSec: 1.5,
      extendEndForLag: true,
      minTransitionSec: 0.10,
      maxTransitionSec: 0.35,
      transitionAngleRate: 0.0022,
      restTransitionSec: 0.30,
      fingerAnticipationSec: 0.08,
      breathingAmplitudeDeg: 0.85,
      breathingFreqHz: 0.20,
      ...options
    };
    this.plan = null;
  }

  /**
   * Extrae y ordena las entradas de glosas desde un proyecto de LSEC Studio o un arreglo.
   */
  _extractRawEntries(project) {
    const rawList = [];
    if (Array.isArray(project)) {
      rawList.push(...project);
    } else if (project && typeof project === 'object') {
      if (Array.isArray(project.glosses) && project.glosses.length > 0) {
        rawList.push(...project.glosses);
      } else if (Array.isArray(project.segments)) {
        for (const seg of project.segments) {
          if (seg && Array.isArray(seg.glosses)) {
            for (const g of seg.glosses) {
              rawList.push({
                ...g,
                proposition_id: g.proposition_id || g.origin_proposition_id || seg.id
              });
            }
          }
        }
      }
    }

    const parsed = [];
    for (let i = 0; i < rawList.length; i++) {
      const item = rawList[i];
      if (!item) continue;
      const gloss = String(item.gloss || item.lemma || item.text || '').trim();
      if (!gloss) continue;
      const st = typeof item.start_seconds === 'number'
        ? item.start_seconds
        : (typeof item.start_time === 'number'
          ? item.start_time
          : (typeof item.startMs === 'number' ? item.startMs / 1000.0 : (typeof item.start === 'number' ? item.start : 0)));
      const et = typeof item.end_seconds === 'number'
        ? item.end_seconds
        : (typeof item.end_time === 'number'
          ? item.end_time
          : (typeof item.endMs === 'number' ? item.endMs / 1000.0 : (typeof item.end === 'number' ? item.end : st + 0.8)));
      if (!Number.isFinite(st) || !Number.isFinite(et) || et <= st) continue;

      const cleanUpper = gloss.toUpperCase();
      const isSingleLetterHyphenated = cleanUpper.includes('-')
        && cleanUpper.split('-').filter(Boolean).every(p => p.trim().length === 1);

      parsed.push({
        index: i,
        id: item.id || `g_${i}`,
        gloss,
        glossKey: cleanUpper,
        slotStart: st,
        slotEnd: et,
        slotDuration: Math.max(0.05, et - st),
        propositionId: item.proposition_id || item.origin_proposition_id || item.prop_id || item.segment_id || null,
        isFingerspelling: Boolean(item.is_fingerspelling || item.gloss_type === 'DACTILOLOGÍA' || isSingleLetterHyphenated),
        raw: item,
        rawItem: item
      });
    }

    parsed.sort((a, b) => (a.slotStart - b.slotStart) || (a.slotEnd - b.slotEnd) || (a.index - b.index));
    return parsed;
  }

  _resolveClipFromMap(entry, clipMap) {
    if (!clipMap) return null;
    if (typeof clipMap === 'function') {
      return clipMap(entry);
    }
    if (clipMap instanceof Map) {
      return (
        clipMap.get(entry.glossKey) ||
        clipMap.get(entry.gloss) ||
        clipMap.get(entry.id) ||
        null
      );
    }
    if (typeof clipMap === 'object') {
      return (
        clipMap[entry.glossKey] ||
        clipMap[entry.gloss] ||
        clipMap[entry.id] ||
        null
      );
    }
    return null;
  }

  /**
   * Compila el plan maestro de ejecución continua y coarticulación C¹.
   * @param {Object|Array} project - Proyecto LSEC Studio o lista de glosas
   * @param {Map|Object|Function} clipMap - Mapa de glosa -> SignClip
   * @param {Object} [overrideOptions]
   * @returns {Object} Plan compilado
   */
  compile(project, clipMap, overrideOptions = {}) {
    const opts = { ...this.options, ...overrideOptions };
    const maxSpeed = Math.max(1.0, Number(opts.maxSpeed) || 1.6);
    const minSpeed = Math.max(0.4, Math.min(1.0, Number(opts.minSpeed) || 0.70));
    const maxLagSec = Math.max(0.1, Number(opts.maxLagSec) || 1.0);
    const restGapThresholdSec = Math.max(0.25, Number(opts.restGapThresholdSec) || 1.5);
    const minTrans = Math.max(0.06, Number(opts.minTransitionSec) || 0.10);
    const maxTrans = Math.max(minTrans, Number(opts.maxTransitionSec) || 0.35);
    const angleRate = Number(opts.transitionAngleRate) || 0.0022;
    const restTransSec = Math.max(0.15, Number(opts.restTransitionSec) || 0.30);

    const rawEntries = this._extractRawEntries(project);
    const baseVideoDuration = Number(
      opts.videoDurationSec ||
      opts.videoDuration ||
      (project && (project.media_info?.duration_seconds || project.video_duration || project.duration || project.videoDuration)) ||
      (rawEntries.length > 0 ? rawEntries[rawEntries.length - 1].slotEnd : 0)
    ) || 0;

    // 1. Preparar descriptores de trazo para cada glosa
    const entries = rawEntries.map((item, idx) => {
      const clip = item.isFingerspelling ? null : this._resolveClipFromMap(item, clipMap);
      const prepared = clip ? buildPreparedClipDescriptor(clip) : null;
      return {
        ...item,
        orderIndex: idx,
        clip: clip || null,
        prepared,
        status: prepared ? 'PLAYABLE' : (item.isFingerspelling ? 'FINGERSPELLING' : 'MISSING')
      };
    });

    // Filtrar las glosas reproducibles para planificación cinemática, manteniendo referencia a todas
    const playableIndices = [];
    for (let i = 0; i < entries.length; i++) {
      if (entries[i].prepared) playableIndices.push(i);
    }

    if (playableIndices.length === 0) {
      this.plan = {
        options: opts,
        entries,
        playableEntries: [],
        segments: [],
        videoDurationSec: baseVideoDuration,
        avatarEndTimeSec: 0,
        sequenceEndTime: baseVideoDuration,
        extendedTailSec: 0,
        stats: {
          totalGlosses: entries.length,
          playableGlosses: 0,
          adjustedGlosses: 0,
          intraSentenceRestDrops: 0,
          interSentenceRestDrops: 0,
          maxLagSec: 0,
          maxSpeedUsed: 1.0
        }
      };
      this.compiled = this.plan;
      return this.plan;
    }

    // 2. Agrupar glosas reproducibles en corridas contiguas (separadas únicamente cuando hay pausa > restGapThresholdSec)
    const runs = [];
    let currentRun = [playableIndices[0]];

    for (let k = 1; k < playableIndices.length; k++) {
      const prevIdx = playableIndices[k - 1];
      const currIdx = playableIndices[k];
      const prevE = entries[prevIdx];
      const currE = entries[currIdx];
      const slotGap = currE.slotStart - prevE.slotEnd;
      const sameProp = Boolean(
        prevE.propositionId &&
        currE.propositionId &&
        prevE.propositionId === currE.propositionId
      );

      // Si pertenecen a la misma oración/proposición, medir el mayor hueco de silencio real entre entradas consecutivas
      let effectiveSilenceGap = slotGap;
      if (sameProp && currIdx > prevIdx + 1) {
        effectiveSilenceGap = 0.0;
        for (let m = prevIdx; m < currIdx; m++) {
          const gBetween = entries[m + 1].slotStart - entries[m].slotEnd;
          if (gBetween > effectiveSilenceGap) effectiveSilenceGap = gBetween;
        }
      }

      // Nunca caer a reposo si la pausa efectiva es <= restGapThresholdSec (1.5s por defecto)
      if (effectiveSilenceGap > restGapThresholdSec) {
        runs.push(currentRun);
        currentRun = [currIdx];
      } else {
        currentRun.push(currIdx);
      }
    }
    if (currentRun.length > 0) runs.push(currentRun);

    // 3. Planificar cada corrida con:
    //    - Duración de transición adaptativa T = clamp(0.10 + k * maxAngleDeg, 0.10, 0.35)
    //    - Backpropagation de holgura en secuencias densas
    //    - Tope de velocidad 1.6x y presupuesto estricto de desfase lag <= maxLagSec (1.0 s)
    let prevRunFinishSec = 0.0;
    for (let rIdx = 0; rIdx < runs.length; rIdx++) {
      const run = runs[rIdx];
      const m = run.length;
      const runItems = run.map(idx => entries[idx]);

      // 3a. Calcular duraciones de transición y longitudes de trazo efectivas
      const transDur = new Float64Array(m);
      const effStrokeLen = new Float64Array(m);
      const effStrokeStart = new Float64Array(m);
      const effStrokeEnd = new Float64Array(m);

      for (let j = 0; j < m; j++) {
        const it = runItems[j];
        const prep = it.prepared;
        let sStart = prep.strokeStart;
        let sEnd = prep.strokeEnd;
        let sLen = prep.strokeDuration;

        // Si la seña tiene repetición de diccionario y excede holgadamente el slot a 1.35x, usar 1 repetición
        if (prep.flags && prep.flags.repeatedStroke && sLen > 1.35 * it.slotDuration && sLen > 1.20) {
          const singleLen = Math.max(0.60, sLen * 0.56);
          sEnd = sStart + singleLen;
          sLen = singleLen;
        }

        effStrokeStart[j] = sStart;
        effStrokeEnd[j] = sEnd;
        effStrokeLen[j] = sLen;

        if (j === 0) {
          transDur[j] = Math.min(restTransSec, Math.max(minTrans, it.slotStart > 0.05 ? Math.min(restTransSec, it.slotStart) : minTrans));
        } else {
          const prevPrep = runItems[j - 1].prepared;
          const prevEndPose = prevPrep.sampleClipPoseAt(effStrokeEnd[j - 1]).bones;
          const currStartPose = prep.sampleClipPoseAt(sStart).bones;
          const maxAng = computeMaxArmAngleDeg(prevEndPose, currStartPose);
          transDur[j] = Math.min(maxTrans, Math.max(minTrans, minTrans + angleRate * maxAng));
        }
      }

      // 3b. Backpropagation: identificar demanda acumulada aguas abajo para que señas holgadas
      //     cedan tiempo terminando antes (hasta maxSpeed = 1.6x) cuando vienen señas densas detrás.
      const downstreamDeficit = new Float64Array(m);
      let accDeficit = 0;
      for (let j = m - 1; j >= 0; j--) {
        const it = runItems[j];
        const minPossibleDur = effStrokeLen[j] / maxSpeed + (j > 0 ? transDur[j] : 0);
        const slotBudget = it.slotEnd - it.slotStart;
        const localDeficit = minPossibleDur - slotBudget;
        downstreamDeficit[j] = accDeficit;
        accDeficit = Math.max(0, accDeficit + localDeficit);
      }

      // 3c. Pasada hacia adelante (Forward pass) con límite de velocidad 1.6x
      const startArr = new Float64Array(m);
      const endArr = new Float64Array(m);
      const speedArr = new Float64Array(m);
      const minSpeedFloor = new Float64Array(m);
      minSpeedFloor.fill(minSpeed);
      const adjArr = new Uint8Array(m);

      const minRunStartAllowed = rIdx === 0 ? 0.0 : (prevRunFinishSec + minTrans);

      const runForwardSchedule = () => {
        let prevStrokeEndSec = -Infinity;
        for (let j = 0; j < m; j++) {
          const it = runItems[j];
          const T_tr = j > 0 ? transDur[j] : 0;
          const maxEarlyLead = downstreamDeficit[j] > 0.02 ? Math.min(0.35, downstreamDeficit[j]) : 0.0;
          const earliestAllowed = Math.max(minRunStartAllowed, it.slotStart - maxEarlyLead);
          const minAfterPrev = j > 0 ? (prevStrokeEndSec + T_tr) : earliestAllowed;
          const startSec = Math.max(0.0, Math.max(earliestAllowed, minAfterPrev));

          const targetEnd = Math.max(startSec + 0.12, it.slotEnd - Math.min(maxLagSec, downstreamDeficit[j]));
          const availForTarget = Math.max(0.10, targetEnd - startSec);
          const availForSlotEnd = Math.max(0.10, it.slotEnd - startSec);

          let speed = 1.0;
          const strokeLen = effStrokeLen[j];
          if (strokeLen > availForTarget) {
            const neededSpeed = strokeLen / availForTarget;
            if (neededSpeed <= maxSpeed) {
              speed = Math.max(1.0, neededSpeed);
            } else {
              speed = maxSpeed;
            }
          }
          speed = Math.min(maxSpeed, Math.max(minSpeedFloor[j], speed));
          const playDur = strokeLen / speed;
          const endSec = startSec + playDur;

          startArr[j] = startSec;
          endArr[j] = endSec;
          speedArr[j] = speed;
          if ((strokeLen / availForSlotEnd) > maxSpeed + 0.05) {
            adjArr[j] = 1;
          }
          prevStrokeEndSec = endSec;
        }
      };

      runForwardSchedule();

      // 3d. Garantía estricta de presupuesto de lag (startLag <= maxLagSec y endLag <= maxLagSec):
      //     Si una ráfaga densa acumula lag > maxLagSec, comprimir primero el primer punto de violación
      //     en la cadena contigua [j0..j] (manteniendo speed <= 1.6x).
      const maxCompressIters = Math.max(16, m * 2);
      for (let iter = 0; iter < maxCompressIters; iter++) {
        let violIdx = -1;
        let violExcess = 0;
        let isStartViol = false;

        for (let j = 0; j < m; j++) {
          const sExcess = (startArr[j] - runItems[j].slotStart) - maxLagSec;
          const eExcess = (endArr[j] - runItems[j].slotEnd) - maxLagSec;
          if (sExcess > 1e-4 || eExcess > 1e-4) {
            violIdx = j;
            if (sExcess >= eExcess && j > 0) {
              violExcess = sExcess;
              isStartViol = true;
            } else {
              violExcess = Math.max(sExcess, eExcess);
              isStartViol = false;
            }
            break;
          }
        }
        if (violIdx < 0) break;

        // Identificar el inicio j0 de la cadena contigua sin holgura que alimenta a violIdx
        let j0 = violIdx;
        while (j0 > 0 && startArr[j0] <= endArr[j0 - 1] + transDur[j0] + 1e-3) {
          j0--;
        }

        const strokeRangeEnd = (isStartViol && violIdx > j0) ? (violIdx - 1) : violIdx;
        let neededReduction = violExcess + 0.002;

        // Paso A: Acelerar a maxSpeed cualquier seña de la cadena [j0..strokeRangeEnd] que aún vaya < maxSpeed
        for (let k = j0; k <= strokeRangeEnd; k++) {
          if (speedArr[k] < maxSpeed - 1e-4) {
            const curDur = effStrokeLen[k] / speedArr[k];
            const minDurAtMax = effStrokeLen[k] / maxSpeed;
            const saved = Math.max(0, curDur - minDurAtMax);
            minSpeedFloor[k] = maxSpeed;
            speedArr[k] = maxSpeed;
            neededReduction = Math.max(0, neededReduction - saved);
          } else {
            minSpeedFloor[k] = maxSpeed;
          }
        }

        // Paso B: Reducir duraciones de transición en (j0..violIdx] hacia minTrans (0.10s)
        for (let k = j0 + 1; k <= violIdx && neededReduction > 1e-5; k++) {
          const reducibleTrans = Math.max(0, transDur[k] - minTrans);
          if (reducibleTrans > 0) {
            const cut = Math.min(reducibleTrans, neededReduction);
            transDur[k] -= cut;
            neededReduction -= cut;
          }
        }

        // Paso C: Recortar proporcionalmente los bordes de effStrokeLen en [j0..strokeRangeEnd] a velocidad maxSpeed
        if (neededReduction > 1e-4) {
          const minPlayDur = 0.16;
          let totalReduciblePlay = 0;
          for (let k = j0; k <= strokeRangeEnd; k++) {
            minSpeedFloor[k] = maxSpeed;
            const playAtMax = effStrokeLen[k] / maxSpeed;
            totalReduciblePlay += Math.max(0, playAtMax - minPlayDur);
          }

          if (totalReduciblePlay > 1e-5) {
            for (let k = j0; k <= strokeRangeEnd; k++) {
              const playAtMax = effStrokeLen[k] / maxSpeed;
              const redPlay = Math.max(0, playAtMax - minPlayDur);
              if (redPlay <= 0) continue;
              const share = Math.min(redPlay, neededReduction * (redPlay / totalReduciblePlay));
              const newPlayDur = playAtMax - share;
              const newStrokeLen = newPlayDur * maxSpeed;
              const deltaLen = effStrokeLen[k] - newStrokeLen;
              if (deltaLen > 1e-5) {
                effStrokeStart[k] += deltaLen * 0.35;
                effStrokeEnd[k] = effStrokeStart[k] + newStrokeLen;
                effStrokeLen[k] = newStrokeLen;
                adjArr[k] = 1;
              }
            }
          }
        }

        // Recalcular déficit aguas abajo y horario hacia adelante
        accDeficit = 0;
        for (let j = m - 1; j >= 0; j--) {
          const it = runItems[j];
          const minPossibleDur = effStrokeLen[j] / maxSpeed + (j > 0 ? transDur[j] : 0);
          const slotBudget = it.slotEnd - it.slotStart;
          downstreamDeficit[j] = accDeficit;
          accDeficit = Math.max(0, accDeficit + (minPossibleDur - slotBudget));
        }
        runForwardSchedule();
      }

      // 3e. Materializar snapshots y velocidades reales escaladas por `speed` (regla de la cadena d/dt = speed * d/d_tau)
      const scaleVelMap = (rawVel, spd) => {
        const out = {};
        for (const [k, v] of Object.entries(rawVel || {})) {
          out[k] = [v[0] * spd, v[1] * spd, v[2] * spd];
        }
        return out;
      };

      for (let j = 0; j < m; j++) {
        const it = runItems[j];
        const sStart = effStrokeStart[j];
        const sEnd = effStrokeEnd[j];
        const strokeLen = effStrokeLen[j];
        const startSec = startArr[j];
        const endSec = endArr[j];
        const speed = speedArr[j];
        const playDur = endSec - startSec;
        const startLagSec = Math.max(0.0, startSec - it.slotStart);
        const endLagSec = Math.max(0.0, endSec - it.slotEnd);
        const lagSec = Math.max(startLagSec, endLagSec);

        const startSnap = it.prepared.sampleClipPoseAt(sStart);
        const endSnap = it.prepared.sampleClipPoseAt(sEnd);
        const rawStartVel = it.prepared.sampleClipVelocityAt(sStart, 'forward');
        const rawEndVel = it.prepared.sampleClipVelocityAt(sEnd, 'backward');
        const exactSpeed = playDur > 1e-6 ? (sEnd - sStart) / playDur : speed;

        it.strokeStart = sStart;
        it.strokeEnd = sEnd;
        it.strokeDuration = strokeLen;
        it.startSec = startSec;
        it.endSec = endSec;
        it.playDurationSec = playDur;
        it.speed = exactSpeed;
        it.startLagSec = Number(startLagSec.toFixed(4));
        it.endLagSec = Number(endLagSec.toFixed(4));
        it.lagSec = Number(lagSec.toFixed(4));
        it.transitionDuration = transDur[j];
        it.adjusted = Boolean(adjArr[j]);
        it.startSnapshot = startSnap;
        it.endSnapshot = endSnap;
        it.startVel = scaleVelMap(rawStartVel, exactSpeed);
        it.endVel = scaleVelMap(rawEndVel, exactSpeed);
        it.runIndex = rIdx;
        it.indexInRun = j;
      }

      prevRunFinishSec = endArr[m - 1] + restTransSec;
    }

    // 4. Construir la lista continua y sin huecos de segmentos cinemáticos:
    //    Cada segmento es de tipo: 'rest' | 'transition' | 'stroke' | 'hold'
    const segments = [];
    const neutralSnapshot = {
      bones: CANONICAL_REST_BONES,
      expressions: makeNeutralExpressions()
    };
    const zeroVel = {};
    for (const bName of [...LEFT_ARM_BONES, ...RIGHT_ARM_BONES]) zeroVel[bName] = [0, 0, 0];

    let cursorSec = 0.0;
    let intraSentenceRestDrops = 0;
    let interSentenceRestDrops = 0;

    for (let rIdx = 0; rIdx < runs.length; rIdx++) {
      const run = runs[rIdx];
      const firstEntry = entries[run[0]];

      // Transición desde reposo hacia la primera seña de la corrida
      const prepDur = Math.min(restTransSec, Math.max(minTrans, firstEntry.startSec - cursorSec));
      const transStart = Math.max(cursorSec, firstEntry.startSec - prepDur);

      if (transStart > cursorSec + 1e-4) {
        segments.push({
          type: 'rest',
          startSec: cursorSec,
          endSec: transStart,
          fromSnapshot: neutralSnapshot,
          toSnapshot: neutralSnapshot,
          activeEntry: null
        });
      }

      if (firstEntry.startSec > transStart + 1e-4) {
        segments.push({
          type: 'transition',
          subtype: 'from_rest',
          startSec: transStart,
          endSec: firstEntry.startSec,
          fromSnapshot: neutralSnapshot,
          toSnapshot: firstEntry.startSnapshot,
          fromVel: zeroVel,
          toVel: firstEntry.startVel,
          activeEntry: firstEntry
        });
      }

      // Recorrer cada seña de la corrida
      for (let j = 0; j < run.length; j++) {
        const currEntry = entries[run[j]];

        // Segmento de trazo activo (stroke)
        segments.push({
          type: 'stroke',
          startSec: currEntry.startSec,
          endSec: currEntry.endSec,
          activeEntry: currEntry
        });

        cursorSec = currEntry.endSec;

        if (j + 1 < run.length) {
          const nextEntry = entries[run[j + 1]];
          const gapTotal = Math.max(0.0, nextEntry.startSec - currEntry.endSec);
          const desiredTrans = Math.min(maxTrans, Math.max(nextEntry.transitionDuration, minTrans));
          // Solo insertar mantenimiento (hold) si la pausa supera la transición por al menos 80ms;
          // de lo contrario, usar todo el intervalo como transición fluida continua C^1 sin detener el brazo
          const hasHold = gapTotal > desiredTrans + 0.08;
          const tDur = hasHold ? desiredTrans : gapTotal;
          const holdEnd = hasHold ? (nextEntry.startSec - tDur) : currEntry.endSec;

          if (hasHold && holdEnd > currEntry.endSec + 1e-4) {
            segments.push({
              type: 'hold',
              startSec: currEntry.endSec,
              endSec: holdEnd,
              holdSnapshot: currEntry.endSnapshot,
              activeEntry: currEntry,
              nextEntry
            });
          }

          if (nextEntry.startSec > holdEnd + 1e-4) {
            segments.push({
              type: 'transition',
              subtype: 'coarticulation',
              startSec: holdEnd,
              endSec: nextEntry.startSec,
              fromSnapshot: currEntry.endSnapshot,
              toSnapshot: nextEntry.startSnapshot,
              fromVel: hasHold ? zeroVel : currEntry.endVel,
              toVel: nextEntry.startVel,
              fromEntry: currEntry,
              activeEntry: nextEntry
            });
          }
          cursorSec = nextEntry.startSec;
        }
      }

      // Al finalizar la corrida, retornar suavemente a REST_POSE
      const lastEntry = entries[run[run.length - 1]];
      const returnEndSec = lastEntry.endSec + restTransSec;
      segments.push({
        type: 'transition',
        subtype: 'to_rest',
        startSec: lastEntry.endSec,
        endSec: returnEndSec,
        fromSnapshot: lastEntry.endSnapshot,
        toSnapshot: neutralSnapshot,
        fromVel: lastEntry.endVel,
        toVel: zeroVel,
        fromEntry: lastEntry,
        activeEntry: null
      });
      cursorSec = returnEndSec;

      if (rIdx + 1 < runs.length) {
        const nextFirst = entries[runs[rIdx + 1][0]];
        const sameProp = Boolean(
          lastEntry.propositionId &&
          nextFirst.propositionId &&
          lastEntry.propositionId === nextFirst.propositionId
        );
        if (sameProp) intraSentenceRestDrops++;
        else interSentenceRestDrops++;
      }
    }

    const avatarEndTimeSec = cursorSec;
    const sequenceEndTime = opts.extendEndForLag !== false
      ? Math.max(baseVideoDuration, avatarEndTimeSec)
      : baseVideoDuration;

    if (sequenceEndTime > cursorSec + 1e-4) {
      segments.push({
        type: 'rest',
        startSec: cursorSec,
        endSec: sequenceEndTime,
        fromSnapshot: neutralSnapshot,
        toSnapshot: neutralSnapshot,
        activeEntry: null
      });
    }

    const playableEntries = playableIndices.map(idx => entries[idx]);
    let maxLagFound = 0;
    let maxSpeedFound = 1.0;
    let adjustedCount = 0;
    for (const pe of playableEntries) {
      if (pe.lagSec > maxLagFound) maxLagFound = pe.lagSec;
      if (pe.speed > maxSpeedFound) maxSpeedFound = pe.speed;
      if (pe.adjusted) adjustedCount++;
    }

    this.plan = {
      options: opts,
      entries,
      playableEntries,
      segments,
      videoDurationSec: Number(baseVideoDuration.toFixed(4)),
      avatarEndTimeSec: Number(avatarEndTimeSec.toFixed(4)),
      sequenceEndTime: Number(sequenceEndTime.toFixed(4)),
      extendedTailSec: Number(Math.max(0, sequenceEndTime - baseVideoDuration).toFixed(4)),
      stats: {
        totalGlosses: entries.length,
        playableGlosses: playableEntries.length,
        adjustedGlosses: adjustedCount,
        intraSentenceRestDrops,
        interSentenceRestDrops,
        maxLagSec: Number(maxLagFound.toFixed(4)),
        maxSpeedUsed: Number(maxSpeedFound.toFixed(4))
      }
    };
    this.compiled = this.plan;

    return this.plan;
  }

  /**
   * Resuelve qué entrada de glosa debe mostrarse como activa (HUD / PiP badge / exportación)
   * en el instante `t`, preservando glosas no ejecutables (FINGERSPELLING / MISSING) durante su
   * ventana nominal `[slotStart, slotEnd]` y evitando dejar pegada la glosa anterior durante
   * pausas silenciosas o retornos a reposo (`to_rest`).
   */
  resolveActiveEntryAt(t, seg) {
    const allEntries = (this.plan && Array.isArray(this.plan.entries)) ? this.plan.entries : [];
    // 1. Si existe una glosa no ejecutable (DACTILOLOGÍA / MISSING) cuya ventana nominal contiene t, priorizarla
    for (let i = 0; i < allEntries.length; i++) {
      const e = allEntries[i];
      if (!e.playable && t >= e.slotStart - 1e-4 && t <= e.slotEnd + 1e-4) {
        return e;
      }
    }

    if (!seg) return null;

    // 2. Durante el trazo activo de una seña (incluyendo desfase o cola extendida del PiP), mostrar esa seña
    if (seg.type === 'stroke') {
      return seg.activeEntry || null;
    }

    // 3. Durante mantenimiento ('hold') o transición ('from_rest', 'coarticulation', 'to_rest'):
    if (seg.type === 'hold' || seg.type === 'transition') {
      const prevE = seg.type === 'hold' ? seg.activeEntry : seg.fromEntry;
      const nextE = seg.type === 'hold' ? seg.nextEntry : seg.activeEntry;

      if (nextE && t >= nextE.slotStart - 1e-4 && t <= Math.max(nextE.slotEnd, nextE.endSec) + 1e-4) {
        return nextE;
      }
      if (prevE && t >= prevE.slotStart - 1e-4 && t <= prevE.slotEnd + 1e-4) {
        return prevE;
      }
      for (let i = 0; i < allEntries.length; i++) {
        const e = allEntries[i];
        if (t >= e.slotStart - 1e-4 && t <= e.slotEnd + 1e-4 && (!e.playable || t <= e.endSec + 1e-4)) {
          return e;
        }
      }
      return null;
    }

    return null;
  }

  /**
   * Evalúa de forma pura y determinista la pose completa del avatar en el instante `tSec`.
   * Idéntico resultado para reproducción en vivo, scrub aleatorio en el timeline o exportación a 30 FPS.
   *
   * @param {number} tSec - Tiempo en segundos
   * @returns {{
   *   timeSec: number,
   *   phase: 'rest'|'transition'|'stroke'|'hold',
   *   subtype: string|null,
   *   activeGloss: string|null,
   *   activeEntry: Object|null,
   *   bones: Object<string, number[]>,
   *   expressions: Object<string, number>,
   *   speed: number,
   *   lagSec: number,
   *   adjusted: boolean,
   *   isExtendedTail: boolean
   * }}
   */
  sample(tSec) {
    const t = Math.max(0.0, Number(tSec) || 0.0);
    const opts = (this.plan && this.plan.options) || this.options;
    const videoDur = (this.plan && this.plan.videoDurationSec) || 0;
    const isExtendedTail = videoDur > 0 && t > videoDur + 1e-4;

    if (!this.plan || !Array.isArray(this.plan.segments) || this.plan.segments.length === 0) {
      return {
        timeSec: t,
        phase: 'rest',
        subtype: 'empty_plan',
        activeGloss: null,
        activeEntry: null,
        bones: applyBreathingMicroMotion(CANONICAL_REST_BONES, t, 0, Math.max(10, t + 1), opts.breathingAmplitudeDeg, opts.breathingFreqHz),
        expressions: makeNeutralExpressions(),
        speed: 1.0,
        lagSec: 0.0,
        adjusted: false,
        isExtendedTail
      };
    }

    const segs = this.plan.segments;
    // Búsqueda binaria del segmento que contiene `t`
    let seg = null;
    if (t <= segs[0].startSec) {
      seg = segs[0];
    } else if (t >= segs[segs.length - 1].endSec) {
      seg = segs[segs.length - 1];
    } else {
      let lo = 0;
      let hi = segs.length - 1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        const cand = segs[mid];
        if (t < cand.startSec - 1e-7) {
          hi = mid - 1;
        } else if (t > cand.endSec + 1e-7) {
          lo = mid + 1;
        } else {
          seg = cand;
          break;
        }
      }
      if (!seg) seg = segs[Math.max(0, Math.min(segs.length - 1, lo))];
    }

    if (!seg || seg.type === 'rest' || t >= segs[segs.length - 1].endSec) {
      const wStart = seg ? seg.startSec : 0;
      const wEnd = seg ? Math.max(seg.endSec, t + 1.0) : t + 1.0;
      const restEntry = this.resolveActiveEntryAt(t, seg);
      return {
        timeSec: t,
        phase: 'rest',
        subtype: 'canonical_rest',
        activeGloss: restEntry ? restEntry.gloss : null,
        activeEntry: restEntry,
        bones: applyBreathingMicroMotion(CANONICAL_REST_BONES, t, wStart, wEnd, opts.breathingAmplitudeDeg, opts.breathingFreqHz),
        expressions: makeNeutralExpressions(),
        speed: 1.0,
        lagSec: 0.0,
        adjusted: false,
        isExtendedTail
      };
    }

    if (seg.type === 'stroke') {
      const entry = seg.activeEntry;
      const prep = entry.prepared;
      const localClipSec = Math.min(
        entry.strokeEnd,
        Math.max(entry.strokeStart, entry.strokeStart + (t - entry.startSec) * entry.speed)
      );
      const snap = prep.sampleClipPoseAt(localClipSec);
      const resolvedEntry = this.resolveActiveEntryAt(t, seg) || entry;
      return {
        timeSec: t,
        phase: 'stroke',
        subtype: 'active_stroke',
        activeGloss: resolvedEntry.gloss,
        activeEntry: resolvedEntry,
        bones: snap.bones,
        expressions: snap.expressions,
        speed: entry.speed,
        lagSec: entry.lagSec,
        adjusted: entry.adjusted,
        isExtendedTail
      };
    }

    if (seg.type === 'hold') {
      const entry = this.resolveActiveEntryAt(t, seg);
      const kinEntry = seg.activeEntry;
      const baseBones = seg.holdSnapshot.bones;
      const bones = applyBreathingMicroMotion(
        baseBones,
        t,
        seg.startSec,
        seg.endSec,
        opts.breathingAmplitudeDeg,
        opts.breathingFreqHz
      );
      // Relajar suavemente expresiones un 25% durante el mantenimiento sin caer a cero
      const dur = Math.max(0.05, seg.endSec - seg.startSec);
      const uHold = Math.min(1.0, Math.max(0.0, (t - seg.startSec) / dur));
      const holdEnv = 0.25 * Math.sin(Math.PI * uHold);
      const expressions = interpolateExpressions(seg.holdSnapshot.expressions, makeNeutralExpressions(), holdEnv);

      return {
        timeSec: t,
        phase: 'hold',
        subtype: 'pose_hold',
        activeGloss: entry ? entry.gloss : null,
        activeEntry: entry || null,
        bones,
        expressions,
        speed: kinEntry ? kinEntry.speed : 1.0,
        lagSec: kinEntry ? kinEntry.lagSec : 0.0,
        adjusted: kinEntry ? kinEntry.adjusted : false,
        isExtendedTail
      };
    }

    // seg.type === 'transition'
    const T = Math.max(1e-4, seg.endSec - seg.startSec);
    const u = Math.min(1.0, Math.max(0.0, (t - seg.startSec) / T));

    // Anticipación de dedos: completan su configuración manual entre 60ms y 100ms antes que el brazo
    const antSec = Math.min(Number(opts.fingerAnticipationSec) || 0.08, 0.32 * T);
    const alphaAnt = Math.min(0.35, Math.max(0.0, antSec / T));
    const uFingers = seg.subtype === 'to_rest'
      ? u
      : Math.min(1.0, Math.max(0.0, u / Math.max(0.5, 1.0 - alphaAnt)));

    const fromBones = seg.fromSnapshot.bones;
    const toBones = seg.toSnapshot.bones;
    const fromVel = seg.fromVel || {};
    const toVel = seg.toVel || {};
    const bones = {};

    for (const bName of ALL_COMPILER_BONES) {
      const q0 = fromBones[bName] || CANONICAL_REST_BONES[bName];
      const q1 = toBones[bName] || CANONICAL_REST_BONES[bName];
      if (FINGER_BONE_SET.has(bName)) {
        bones[bName] = interpolateSO3HermiteC1(q0, q1, null, null, T * (1.0 - alphaAnt), uFingers);
      } else if (ARM_BONE_SET.has(bName)) {
        bones[bName] = interpolateSO3HermiteC1(q0, q1, fromVel[bName], toVel[bName], T, u);
      } else {
        bones[bName] = interpolateSO3HermiteC1(q0, q1, null, null, T, u);
      }
    }

    const expressions = interpolateExpressions(seg.fromSnapshot.expressions, seg.toSnapshot.expressions, u);
    const activeEntry = this.resolveActiveEntryAt(t, seg);
    const kinEntry = seg.activeEntry || seg.fromEntry || null;

    return {
      timeSec: t,
      phase: 'transition',
      subtype: seg.subtype || 'coarticulation',
      activeGloss: activeEntry ? activeEntry.gloss : null,
      activeEntry,
      bones,
      expressions,
      speed: kinEntry ? kinEntry.speed : 1.0,
      lagSec: kinEntry ? kinEntry.lagSec : 0.0,
      adjusted: kinEntry ? Boolean(kinEntry.adjusted) : false,
      isExtendedTail
    };
  }

  /**
   * Alias de `sample(tSec)` conforme al contrato funcional `pose(t)` del plan.
   */
  pose(tSec) {
    return this.sample(tSec);
  }

  getSequenceEndTime(fallbackDuration = 0) {
    if (!this.plan) return fallbackDuration;
    return Math.max(fallbackDuration, this.plan.sequenceEndTime || 0);
  }
}

/**
 * Aplica directamente el resultado de `compiler.sample(t)` al modelo VRM o Rig Técnico.
 * Garantiza que todos los huesos no presentes en la muestra permanezcan en su postura de reposo
 * y que las expresiones faciales se actualicen sin parpadeos.
 */
export function applyCompiledSampleToModel(model, isVRM, sampleResult) {
  if (!model || !sampleResult || !sampleResult.bones) return;

  const bones = sampleResult.bones;
  const expressions = sampleResult.expressions || {};

  for (const boneName of HUMAN_BONE_NAMES) {
    const qArr = bones[boneName] || CANONICAL_REST_BONES[boneName];
    if (!qArr) continue;
    const qNorm = quatNormalize(qArr);

    let node = null;
    if (isVRM && model.humanoid) {
      node = model.humanoid.getNormalizedBoneNode(boneName) || model.humanoid.getRawBoneNode(boneName);
    } else if (typeof model.getNormalizedBoneNode === 'function') {
      node = model.getNormalizedBoneNode(boneName);
    } else if (model.bones && model.bones[boneName]) {
      node = model.bones[boneName];
    }
    if (node && node.quaternion && typeof node.quaternion.set === 'function') {
      node.quaternion.set(qNorm[0], qNorm[1], qNorm[2], qNorm[3]);
    }
  }

  if (isVRM && model.expressionManager) {
    for (const exprName of FACIAL_EXPRESSION_NAMES) {
      const val = typeof expressions[exprName] === 'number' ? expressions[exprName] : 0.0;
      try {
        model.expressionManager.setValue(exprName, Math.max(0, Math.min(1, val)));
      } catch (_) {}
    }
    if (typeof model.expressionManager.update === 'function') {
      model.expressionManager.update();
    }
  } else if (typeof model.setExpressionWeight === 'function') {
    for (const exprName of FACIAL_EXPRESSION_NAMES) {
      const val = typeof expressions[exprName] === 'number' ? expressions[exprName] : 0.0;
      model.setExpressionWeight(exprName, Math.max(0, Math.min(1, val)));
    }
  }
}
