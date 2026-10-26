/**
 * LSEC Studio — Detección y Recorte de Ventana de Trazo Léxico (Stroke Window)
 * Submódulo extraído de sign-animation-schema.js para mantener modularidad estricta (< 800 líneas).
 */

export const REST_POSE = Object.freeze({
  leftUpperArm:  Object.freeze([0.0435,  0.0028, -0.6087, 0.7921]),
  rightUpperArm: Object.freeze([0.0435, -0.0028,  0.6087, 0.7921]),
  leftLowerArm:  Object.freeze([0,       0.0872,  0,       0.9962]),
  rightLowerArm: Object.freeze([0,      -0.0872,  0,       0.9962])
});

export const UPPER_LIMB_REST_BONES = new Set([
  'hips', 'spine', 'chest', 'upperChest',
  'leftShoulder', 'leftUpperArm', 'leftLowerArm', 'leftHand',
  'leftThumbMetacarpal', 'leftThumbProximal', 'leftThumbDistal',
  'leftIndexProximal', 'leftIndexIntermediate', 'leftIndexDistal',
  'leftMiddleProximal', 'leftMiddleIntermediate', 'leftMiddleDistal',
  'leftRingProximal', 'leftRingIntermediate', 'leftRingDistal',
  'leftLittleProximal', 'leftLittleIntermediate', 'leftLittleDistal',
  'rightShoulder', 'rightUpperArm', 'rightLowerArm', 'rightHand',
  'rightThumbMetacarpal', 'rightThumbProximal', 'rightThumbDistal',
  'rightIndexProximal', 'rightIndexIntermediate', 'rightIndexDistal',
  'rightMiddleProximal', 'rightMiddleIntermediate', 'rightMiddleDistal',
  'rightRingProximal', 'rightRingIntermediate', 'rightRingDistal',
  'rightLittleProximal', 'rightLittleIntermediate', 'rightLittleDistal'
]);

const LEFT_ARM_CHAIN = ['leftShoulder', 'leftUpperArm', 'leftLowerArm', 'leftHand'];
const RIGHT_ARM_CHAIN = ['rightShoulder', 'rightUpperArm', 'rightLowerArm', 'rightHand'];
const FINGER_BONE_SUFFIXES = [
  'ThumbMetacarpal', 'ThumbProximal', 'ThumbDistal',
  'IndexProximal', 'IndexIntermediate', 'IndexDistal',
  'MiddleProximal', 'MiddleIntermediate', 'MiddleDistal',
  'RingProximal', 'RingIntermediate', 'RingDistal',
  'LittleProximal', 'LittleIntermediate', 'LittleDistal'
];
const LEFT_FINGER_CHAIN = FINGER_BONE_SUFFIXES.map(s => `left${s}`);
const RIGHT_FINGER_CHAIN = FINGER_BONE_SUFFIXES.map(s => `right${s}`);
const TORSO_HEAD_CHAIN = ['hips', 'spine', 'chest', 'neck', 'head'];

function quatAngleDeg(q1, q2) {
  if (!q1 || !q2 || q1.length < 4 || q2.length < 4) return 0;
  const dot = Math.abs(q1[0] * q2[0] + q1[1] * q2[1] + q1[2] * q2[2] + q1[3] * q2[3]);
  const clamped = Math.min(1.0, Math.max(0.0, dot));
  return (2.0 * Math.acos(clamped) * 180.0) / Math.PI;
}

function quatLogTangentRad(qFrom, qTo) {
  if (!qFrom || !qTo || qFrom.length < 4 || qTo.length < 4) return [0, 0, 0];
  let x1 = -qFrom[0], y1 = -qFrom[1], z1 = -qFrom[2], w1 = qFrom[3];
  let x2 = qTo[0], y2 = qTo[1], z2 = qTo[2], w2 = qTo[3];
  const dot = (-x1) * x2 + (-y1) * y2 + (-z1) * z2 + w1 * w2;
  if (dot < 0) {
    x2 = -x2; y2 = -y2; z2 = -z2; w2 = -w2;
  }
  const dx = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2;
  const dy = w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2;
  const dz = w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2;
  const dw = Math.min(1.0, Math.max(-1.0, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2));
  const angle = 2.0 * Math.acos(dw);
  const sinH = Math.sqrt(Math.max(0.0, 1.0 - dw * dw));
  if (sinH < 1e-6 || angle < 1e-6) return [0, 0, 0];
  const scale = angle / sinH;
  return [dx * scale, dy * scale, dz * scale];
}

export function computeSignClipStrokeWindow(clip, options = {}) {
  const origDurSec = (clip && typeof clip.durationMs === 'number' ? clip.durationMs : 1000) / 1000.0;
  const defaultResult = {
    startSec: 0,
    endSec: origDurSec,
    strokeDurationSec: origDurSec,
    originalDurationSec: origDurSec,
    wasTrimmed: false
  };

  if (!clip || !Array.isArray(clip.boneTracks) || clip.boneTracks.length === 0) {
    return defaultResult;
  }

  const preStroke = (!options.ignorePrecomputedStroke && clip.metadata && !clip.metadata.isStrokeTrimmed && clip.metadata.stroke && typeof clip.metadata.stroke === 'object')
    ? clip.metadata.stroke
    : null;
  if (preStroke && typeof preStroke.strokeStart === 'number' && typeof preStroke.strokeEnd === 'number' && preStroke.strokeEnd > preStroke.strokeStart) {
    const startSec = Math.max(0, Math.min(origDurSec, Number(preStroke.strokeStart.toFixed(4))));
    const endSec = Math.max(startSec + 0.05, Math.min(origDurSec, Number(preStroke.strokeEnd.toFixed(4))));
    const strokeDurationSec = Number((endSec - startSec).toFixed(4));
    const wasTrimmed = strokeDurationSec < origDurSec - 0.05;
    return {
      startSec,
      endSec,
      strokeDurationSec,
      originalDurationSec: origDurSec,
      wasTrimmed,
      strokeMeta: preStroke
    };
  }

  if (origDurSec <= 0.35) {
    return defaultResult;
  }

  const trackMap = new Map();
  for (const bt of clip.boneTracks) {
    if (bt && bt.boneName && Array.isArray(bt.times) && bt.times.length >= 4) {
      trackMap.set(bt.boneName, bt);
    }
  }

  const refTrack = trackMap.get('rightUpperArm') || trackMap.get('leftUpperArm') || trackMap.get('head') || trackMap.values().next().value;
  if (!refTrack) return defaultResult;

  const times = refTrack.times;
  const n = times.length;
  if (n < 6) return defaultResult;

  const getQuatAt = (bName, idx) => {
    const tr = trackMap.get(bName);
    if (!tr || !Array.isArray(tr.rotations) || tr.rotations.length < 4) return REST_POSE[bName] || [0, 0, 0, 1];
    const clampedIdx = Math.max(0, Math.min((tr.times.length || 1) - 1, idx));
    const base = clampedIdx * 4;
    return [
      tr.rotations[base] ?? 0,
      tr.rotations[base + 1] ?? 0,
      tr.rotations[base + 2] ?? 0,
      tr.rotations[base + 3] ?? 1
    ];
  };

  const armWeights = {
    leftShoulder: 0.5, leftUpperArm: 1.0, leftLowerArm: 1.0, leftHand: 1.0,
    rightShoulder: 0.5, rightUpperArm: 1.0, rightLowerArm: 1.0, rightHand: 1.0
  };

  const startPoseAll = {};
  const endPoseAll = {};
  for (const bName of [...LEFT_ARM_CHAIN, ...RIGHT_ARM_CHAIN, ...LEFT_FINGER_CHAIN, ...RIGHT_FINGER_CHAIN, ...TORSO_HEAD_CHAIN]) {
    startPoseAll[bName] = getQuatAt(bName, 0);
    endPoseAll[bName] = getQuatAt(bName, n - 1);
  }

  const actLeftArm = new Float64Array(n);
  const actRightArm = new Float64Array(n);
  const actLeftFin = new Float64Array(n);
  const actRightFin = new Float64Array(n);
  let peakL = 0;
  let peakR = 0;

  for (let i = 0; i < n; i++) {
    let dl0 = 0, dlN = 0;
    for (const bName of LEFT_ARM_CHAIN) {
      const q = getQuatAt(bName, i);
      const w = armWeights[bName] || 1.0;
      dl0 = Math.max(dl0, quatAngleDeg(q, startPoseAll[bName]) * w);
      dlN = Math.max(dlN, quatAngleDeg(q, endPoseAll[bName]) * w);
    }
    const al = Math.min(dl0, dlN);
    actLeftArm[i] = al;
    if (al > peakL) peakL = al;

    let dr0 = 0, drN = 0;
    for (const bName of RIGHT_ARM_CHAIN) {
      const q = getQuatAt(bName, i);
      const w = armWeights[bName] || 1.0;
      dr0 = Math.max(dr0, quatAngleDeg(q, startPoseAll[bName]) * w);
      drN = Math.max(drN, quatAngleDeg(q, endPoseAll[bName]) * w);
    }
    const ar = Math.min(dr0, drN);
    actRightArm[i] = ar;
    if (ar > peakR) peakR = ar;

    let fl0 = 0, flN = 0;
    for (let f = 0; f < LEFT_FINGER_CHAIN.length; f += 3) {
      const bName = LEFT_FINGER_CHAIN[f + 1] || LEFT_FINGER_CHAIN[f];
      const q = getQuatAt(bName, i);
      fl0 = Math.max(fl0, quatAngleDeg(q, startPoseAll[bName]));
      flN = Math.max(flN, quatAngleDeg(q, endPoseAll[bName]));
    }
    actLeftFin[i] = Math.min(fl0, flN);

    let fr0 = 0, frN = 0;
    for (let f = 0; f < RIGHT_FINGER_CHAIN.length; f += 3) {
      const bName = RIGHT_FINGER_CHAIN[f + 1] || RIGHT_FINGER_CHAIN[f];
      const q = getQuatAt(bName, i);
      fr0 = Math.max(fr0, quatAngleDeg(q, startPoseAll[bName]));
      frN = Math.max(frN, quatAngleDeg(q, endPoseAll[bName]));
    }
    actRightFin[i] = Math.min(fr0, frN);
  }

  const finWeightL = peakL < 25.0 ? Math.max(0, Math.min(0.35, (25.0 - peakL) / 40.0)) : 0.04;
  const finWeightR = peakR < 25.0 ? Math.max(0, Math.min(0.35, (25.0 - peakR) / 40.0)) : 0.04;

  let leftActive = true;
  let rightActive = true;
  let dominantHand = 'right';
  if (peakL < 10.0 && peakR < 10.0) {
    leftActive = false;
    rightActive = false;
    dominantHand = 'none';
  } else if (peakR * 1.05 >= peakL) {
    dominantHand = 'right';
    rightActive = true;
    leftActive = peakL >= Math.max(14.0, 0.38 * peakR);
  } else {
    dominantHand = 'left';
    leftActive = true;
    rightActive = peakR >= Math.max(14.0, 0.38 * peakL);
  }

  const activity = new Float64Array(n);
  let minAct = Infinity;
  let maxAct = -Infinity;
  for (let i = 0; i < n; i++) {
    const scoreL = actLeftArm[i] + finWeightL * actLeftFin[i];
    const scoreR = actRightArm[i] + finWeightR * actRightFin[i];
    const score = (leftActive && rightActive)
      ? Math.max(scoreL, scoreR)
      : (leftActive ? scoreL : (rightActive ? scoreR : Math.max(scoreL, scoreR)));
    activity[i] = score;
    if (score < minAct) minAct = score;
    if (score > maxAct) maxAct = score;
  }

  if (!Number.isFinite(minAct) || !Number.isFinite(maxAct) || (maxAct - minAct) < 5.0) {
    return defaultResult;
  }

  const spanAct = maxAct - minAct;
  const thrHigh = minAct + 0.42 * spanAct;
  const thrLow = minAct + 0.38 * spanAct;

  let firstHigh = -1;
  let lastHigh = -1;
  for (let i = 0; i < n; i++) {
    if (activity[i] >= thrHigh) {
      if (firstHigh === -1) firstHigh = i;
      lastHigh = i;
    }
  }
  if (firstHigh === -1) {
    for (let i = 0; i < n; i++) {
      if (activity[i] >= thrLow) {
        if (firstHigh === -1) firstHigh = i;
        lastHigh = i;
      }
    }
  }

  if (firstHigh === -1 || lastHigh <= firstHigh) return defaultResult;

  let i0 = firstHigh;
  while (i0 > 0 && activity[i0 - 1] >= thrLow) i0--;
  let i1 = lastHigh;
  while (i1 < n - 1 && activity[i1 + 1] >= thrLow) i1++;

  const isFingerspellingClip = Boolean(
    clip.metadata?.isFingerspelling ||
    clip.stroke?.source === 'fingerspelling_word_lsec' ||
    clip.stroke?.source === 'fingerspelling_lsec_pdf'
  );
  const collapseRepetitions = options.collapseRepetitions === true && !isFingerspellingClip;
  const maxStrokeSec = typeof options.maxStrokeSec === 'number' && options.maxStrokeSec > 0 ? options.maxStrokeSec : 1.85;

  let repeatedStroke = false;
  if ((i1 - i0) >= 16) {
    const midStart = i0 + Math.floor((i1 - i0) * 0.22);
    const midEnd = i0 + Math.floor((i1 - i0) * 0.78);
    let valleyIdx = midStart;
    for (let k = midStart; k <= midEnd; k++) {
      if (activity[k] < activity[valleyIdx]) valleyIdx = k;
    }
    let peak1 = -Infinity;
    let peak2 = -Infinity;
    for (let k = i0; k <= valleyIdx; k++) if (activity[k] > peak1) peak1 = activity[k];
    for (let k = valleyIdx; k <= i1; k++) if (activity[k] > peak2) peak2 = activity[k];

    if (activity[valleyIdx] < minAct + 0.58 * spanAct && Math.min(peak1, peak2) >= thrHigh) {
      repeatedStroke = true;
      if (collapseRepetitions && (times[i1] - times[i0]) > maxStrokeSec) {
        if (peak1 >= peak2 * 0.88) {
          i1 = Math.min(n - 1, valleyIdx + 2);
        } else {
          i0 = Math.max(0, valleyIdx - 2);
        }
      }
    }
  }

  const marginSec = typeof options.marginSec === 'number' ? options.marginSec : 0.02;
  const startSec = Math.max(0, Number((times[i0] - marginSec).toFixed(4)));
  const endSec = Math.min(origDurSec, Number((times[i1] + marginSec).toFixed(4)));
  const strokeDurationSec = Math.max(0.25, Number((endSec - startSec).toFixed(4)));

  const buildChainPose = (frameIdx, chainBones, isActive) => {
    const out = {};
    for (const bName of chainBones) {
      out[bName] = isActive ? getQuatAt(bName, frameIdx) : (REST_POSE[bName] ? [...REST_POSE[bName]] : [0, 0, 0, 1]);
    }
    return out;
  };
  const buildChainVel = (frameIdx, dir, armBones, isActive) => {
    const out = {};
    const idxA = dir === 'forward' ? frameIdx : Math.max(0, frameIdx - 2);
    const idxB = dir === 'forward' ? Math.min(n - 1, frameIdx + 2) : frameIdx;
    const dt = Math.max(1e-3, (times[idxB] || 0) - (times[idxA] || 0));
    for (const bName of armBones) {
      if (!isActive || idxB <= idxA) {
        out[bName] = [0, 0, 0];
      } else {
        const wVec = quatLogTangentRad(getQuatAt(bName, idxA), getQuatAt(bName, idxB));
        out[bName] = [
          Number((wVec[0] / dt).toFixed(4)),
          Number((wVec[1] / dt).toFixed(4)),
          Number((wVec[2] / dt).toFixed(4))
        ];
      }
    }
    return out;
  };

  const strokeMeta = {
    strokeStart: startSec,
    strokeEnd: endSec,
    strokeDuration: strokeDurationSec,
    originalDuration: origDurSec,
    confidence: 0.75,
    flags: {
      repeatedStroke,
      oneHanded: leftActive !== rightActive,
      tooShort: strokeDurationSec < 0.38,
      faceOnly: !leftActive && !rightActive
    },
    activeHands: { left: leftActive, right: rightActive, dominant: dominantHand },
    startPose: {
      left: buildChainPose(i0, [...LEFT_ARM_CHAIN, ...LEFT_FINGER_CHAIN], leftActive),
      right: buildChainPose(i0, [...RIGHT_ARM_CHAIN, ...RIGHT_FINGER_CHAIN], rightActive),
      torsoHead: buildChainPose(i0, TORSO_HEAD_CHAIN, true)
    },
    endPose: {
      left: buildChainPose(i1, [...LEFT_ARM_CHAIN, ...LEFT_FINGER_CHAIN], leftActive),
      right: buildChainPose(i1, [...RIGHT_ARM_CHAIN, ...RIGHT_FINGER_CHAIN], rightActive),
      torsoHead: buildChainPose(i1, TORSO_HEAD_CHAIN, true)
    },
    boundaryVelocity: {
      startRadPerSec: {
        left: buildChainVel(i0, 'forward', LEFT_ARM_CHAIN, leftActive),
        right: buildChainVel(i0, 'forward', RIGHT_ARM_CHAIN, rightActive)
      },
      endRadPerSec: {
        left: buildChainVel(i1, 'backward', LEFT_ARM_CHAIN, leftActive),
        right: buildChainVel(i1, 'backward', RIGHT_ARM_CHAIN, rightActive)
      }
    }
  };

  if (strokeDurationSec >= origDurSec - 0.08) {
    return { ...defaultResult, strokeMeta };
  }

  return {
    startSec,
    endSec,
    strokeDurationSec,
    originalDurationSec: origDurSec,
    wasTrimmed: true,
    strokeMeta
  };
}

export function trimSignClipStroke(clip, options = {}) {
  if (!clip || typeof clip !== 'object' || !Array.isArray(clip.boneTracks)) return clip;
  if (clip.clipId === 'NEUTRAL_POSE_V1' || clip.gloss === 'NEUTRAL') return clip;
  if (clip.metadata && clip.metadata.isStrokeTrimmed && !options.forceRetrim) return clip;

  const hasPrecomputedStroke = Boolean(
    clip.metadata &&
    clip.metadata.stroke &&
    typeof clip.metadata.stroke.strokeStart === 'number' &&
    typeof clip.metadata.stroke.strokeEnd === 'number'
  );
  const strokeSource = hasPrecomputedStroke ? 'stroke_index_v27' : 'heuristic_runtime';
  const win = computeSignClipStrokeWindow(clip, options);
  const strokeMeta = (clip.metadata && clip.metadata.stroke) || win.strokeMeta || null;
  if (!win.wasTrimmed || win.strokeDurationSec <= 0) {
    if (clip.metadata) {
      if (strokeMeta && !clip.metadata.stroke) {
        clip.metadata.stroke = strokeMeta;
      }
      clip.metadata.strokeSource = strokeSource;
    }
    return clip;
  }

  const { startSec, endSec, strokeDurationSec, originalDurationSec } = win;
  const trimmedBoneTracks = [];
  for (const track of clip.boneTracks) {
    if (!track || !Array.isArray(track.times) || !Array.isArray(track.rotations)) continue;
    const newTimes = [];
    const newRots = [];

    for (let i = 0; i < track.times.length; i++) {
      const t = track.times[i];
      if (t >= startSec - 1e-4 && t <= endSec + 1e-4) {
        const shiftedT = Math.max(0, Number((t - startSec).toFixed(5)));
        if (newTimes.length > 0 && shiftedT <= newTimes[newTimes.length - 1]) continue;
        newTimes.push(shiftedT);
        const rIdx = i * 4;
        newRots.push(
          track.rotations[rIdx] ?? 0,
          track.rotations[rIdx + 1] ?? 0,
          track.rotations[rIdx + 2] ?? 0,
          track.rotations[rIdx + 3] ?? 1
        );
      }
    }

    if (newTimes.length >= 2) {
      if (newTimes[0] > 0) newTimes[0] = 0;
      trimmedBoneTracks.push({ boneName: track.boneName, times: newTimes, rotations: newRots });
    } else if (track.times.length > 0) {
      trimmedBoneTracks.push(track);
    }
  }

  const trimmedExprTracks = [];
  if (Array.isArray(clip.expressionTracks)) {
    for (const expr of clip.expressionTracks) {
      if (!expr || !Array.isArray(expr.times) || !Array.isArray(expr.values)) continue;
      const newTimes = [];
      const newVals = [];
      for (let i = 0; i < expr.times.length; i++) {
        const t = expr.times[i];
        if (t >= startSec - 1e-4 && t <= endSec + 1e-4) {
          const shiftedT = Math.max(0, Number((t - startSec).toFixed(5)));
          if (newTimes.length > 0 && shiftedT <= newTimes[newTimes.length - 1]) continue;
          newTimes.push(shiftedT);
          newVals.push(expr.values[i] ?? 0);
        }
      }
      if (newTimes.length >= 2) {
        if (newTimes[0] > 0) newTimes[0] = 0;
        trimmedExprTracks.push({ expressionName: expr.expressionName, times: newTimes, values: newVals });
      }
    }
  }

  const maxTrackEnd = trimmedBoneTracks.reduce((acc, tr) => {
    const last = tr.times.length > 0 ? tr.times[tr.times.length - 1] : 0;
    return Math.max(acc, last);
  }, strokeDurationSec);

  const newDurationMs = Math.max(250, Math.round(maxTrackEnd * 1000));
  const trimmedClip = {
    ...clip,
    durationMs: newDurationMs,
    boneTracks: trimmedBoneTracks,
    expressionTracks: trimmedExprTracks,
    metadata: {
      ...(clip.metadata || {}),
      stroke: strokeMeta || (clip.metadata && clip.metadata.stroke) || null,
      strokeSource,
      isStrokeTrimmed: true,
      originalDurationMs: clip.durationMs,
      originalDurationSec,
      strokeStartSec: startSec,
      strokeEndSec: endSec,
      strokeDurationSec: maxTrackEnd,
      recommendedSpeed: 1.0
    }
  };

  Object.defineProperty(trimmedClip, '_untrimmedBoneTracks', {
    value: clip.boneTracks,
    enumerable: false,
    configurable: true
  });
  Object.defineProperty(trimmedClip, '_untrimmedExpressionTracks', {
    value: clip.expressionTracks,
    enumerable: false,
    configurable: true
  });

  return trimmedClip;
}
