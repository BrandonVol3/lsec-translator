/**
 * sequence-coarticulation-math.js
 * Álgebra de cuaterniones en SO(3)/so(3), interpolación Hermite C¹, evaluación de pistas
 * y descriptores de trazo para el compilador de secuencias LSEC Studio.
 */

import {
  HUMAN_BONE_NAMES,
  ALL_EXPRESSION_TRACK_NAMES as FACIAL_EXPRESSION_NAMES,
  REST_POSE,
  computeSignClipStrokeWindow
} from './sign-animation-schema.js';

import {
  OneEuroQuaternionFilter,
  LSEC_FINGERSPELLING_GRAPHEMES,
  LSEC_FINGERSPELLING_CATALOG,
  tokenizeLSECFingerspelling,
  createLSECFingerspellingSignClip,
  createLSECFingerspellingWordClip
} from './sign-clips-fingerspelling-lsec.js';

export {
  OneEuroQuaternionFilter,
  LSEC_FINGERSPELLING_GRAPHEMES,
  LSEC_FINGERSPELLING_CATALOG,
  tokenizeLSECFingerspelling,
  createLSECFingerspellingSignClip,
  createLSECFingerspellingWordClip
};

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

export const FINGER_BONE_SET = new Set([...LEFT_FINGER_BONES, ...RIGHT_FINGER_BONES]);
export const LEFT_CHAIN_SET = new Set([...LEFT_ARM_BONES, ...LEFT_FINGER_BONES]);
export const RIGHT_CHAIN_SET = new Set([...RIGHT_ARM_BONES, ...RIGHT_FINGER_BONES]);
export const ARM_BONE_SET = new Set([...LEFT_ARM_BONES, ...RIGHT_ARM_BONES]);

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

  // Acotar tangentes escaladas T*w proporcionalmente a deltaNorm para evitar bucles/sobreimpulso preservando C¹ exacto
  const maxTangentNorm = Math.min(2.20, Math.max(0.65, 1.35 * deltaNorm));
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
  const dExpInvNegSO3 = (uVec, vVec) => {
    const ux = uVec[0], uy = uVec[1], uz = uVec[2];
    const vx = vVec[0], vy = vVec[1], vz = vVec[2];
    const theta = Math.hypot(ux, uy, uz);
    if (theta < 1e-7) return [vx, vy, vz];
    const cx = uy * vz - uz * vy;
    const cy = uz * vx - ux * vz;
    const cz = ux * vy - uy * vx;
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

export function sampleBoneTrackAt(track, localSec) {
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

export function sampleExpressionTrackAt(track, localSec) {
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

export function buildPreparedClipDescriptor(clip) {
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
  const rawActiveHands = (strokeMeta && strokeMeta.activeHands)
    || (clip.metadata && clip.metadata.kinematicStabilizer && clip.metadata.kinematicStabilizer.activeHands)
    || null;
  let activeHands;
  if (Array.isArray(rawActiveHands)) {
    const hasLeft = rawActiveHands.includes('left');
    const hasRight = rawActiveHands.includes('right');
    const dom = (strokeMeta && strokeMeta.dominantHand)
      || (clip.metadata && clip.metadata.kinematicStabilizer && clip.metadata.kinematicStabilizer.dominantHand)
      || (hasRight ? 'right' : 'left');
    activeHands = { left: hasLeft || (!hasLeft && !hasRight), right: hasRight || (!hasLeft && !hasRight), dominant: dom };
  } else if (rawActiveHands && typeof rawActiveHands === 'object') {
    activeHands = {
      left: Boolean(rawActiveHands.left),
      right: Boolean(rawActiveHands.right),
      dominant: rawActiveHands.dominant || (rawActiveHands.right ? 'right' : 'left')
    };
  } else {
    activeHands = { left: true, right: true, dominant: 'right' };
  }
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

export function applyBreathingMicroMotion(baseBones, tSec, windowStartSec, windowEndSec, amplitudeDeg = 0.85, freqHz = 0.20) {
  const out = {};
  for (const [k, v] of Object.entries(baseBones)) {
    out[k] = [v[0], v[1], v[2], v[3]];
  }
  const dur = windowEndSec - windowStartSec;
  if (dur <= 0.08 || amplitudeDeg <= 0) return out;

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

export function computeMaxArmAngleDeg(bonesA, bonesB) {
  let maxDeg = 0;
  for (const bName of [...LEFT_ARM_BONES, ...RIGHT_ARM_BONES]) {
    const qa = (bonesA && bonesA[bName]) || CANONICAL_REST_BONES[bName];
    const qb = (bonesB && bonesB[bName]) || CANONICAL_REST_BONES[bName];
    const deg = quatAngleDeg(qa, qb);
    if (deg > maxDeg) maxDeg = deg;
  }
  return maxDeg;
}

export function makeNeutralExpressions() {
  const expr = {};
  for (const eName of FACIAL_EXPRESSION_NAMES) {
    expr[eName] = eName === 'neutral' ? 1.0 : 0.0;
  }
  return expr;
}

export function interpolateExpressions(exprA, exprB, u) {
  const s = minimumJerk(u);
  const out = {};
  for (const eName of FACIAL_EXPRESSION_NAMES) {
    const va = (exprA && typeof exprA[eName] === 'number') ? exprA[eName] : (eName === 'neutral' ? 1.0 : 0.0);
    const vb = (exprB && typeof exprB[eName] === 'number') ? exprB[eName] : (eName === 'neutral' ? 1.0 : 0.0);
    out[eName] = Math.max(0, Math.min(1, va + s * (vb - va)));
  }
  return out;
}

/**
 * Aplica directamente el resultado de `compiler.sample(t)` al modelo VRM o Rig Técnico.
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
