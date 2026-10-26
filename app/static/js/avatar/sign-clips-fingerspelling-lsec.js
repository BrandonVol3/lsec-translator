/**
 * LSEC Studio — Generador Procedimental de Clips de Dactilología LSEC (54 Huesos VRM 1.0)
 *
 * Sintetiza clips de animación para los 30 grafemas del alfabeto manual ecuatoriano
 * y palabras/siglas completas con coarticulación continua en el espacio neutro
 * sin descenso intermedio al reposo, aplicando SLERP antipodal, filtro One-Euro
 * (fc = 1.0 Hz, beta = 0.005) y micro-rearticulación en letras repetidas.
 */

import { HUMAN_BONE_NAMES, REST_POSE, validateSignClip } from './sign-animation-schema.js';
import {
  Q_IDENTITY,
  NEUTRAL_FINGERSPELLING_LOCUS,
  LSEC_PDF_SPATIAL_AXES,
  LSEC_PDF_ANATOMICAL_POINTS,
  LSEC_PDF_MOVEMENT_PRIMITIVES,
  RIGHT_HAND_PHALANX_BONES,
  OneEuroQuaternionFilter,
  slerpQuatAntipodal,
  ensureHemisphereContinuity,
  clampQuaternionStepDeg,
  solveRightArmTwoBoneIK,
  applyRepetitionAndSpeedProfile,
  evaluateLinearTrajectoryOffset,
  evaluateCurvedTrajectoryOffset,
  evaluateCircularTrajectoryOffset,
  interpolatePhalangePoseSO3
} from './sign-clips-fingerspelling-primitives.js';

import {
  LSEC_FINGERSPELLING_GRAPHEMES,
  LSEC_FINGERSPELLING_CATALOG,
  tokenizeLSECFingerspelling
} from './sign-clips-fingerspelling-catalog.js';

export {
  LSEC_PDF_SPATIAL_AXES,
  LSEC_PDF_ANATOMICAL_POINTS,
  LSEC_PDF_MOVEMENT_PRIMITIVES,
  NEUTRAL_FINGERSPELLING_LOCUS,
  OneEuroQuaternionFilter,
  solveRightArmTwoBoneIK,
  LSEC_FINGERSPELLING_GRAPHEMES,
  LSEC_FINGERSPELLING_CATALOG,
  tokenizeLSECFingerspelling
};

const Q_REST_R_SHOULDER = REST_POSE.rightShoulder || Q_IDENTITY;
const Q_REST_R_UPPER = REST_POSE.rightUpperArm || [0.0435, -0.0028, 0.6087, 0.7921];
const Q_REST_R_LOWER = REST_POSE.rightLowerArm || [0, -0.0872, 0, 0.9962];
const Q_REST_R_HAND = REST_POSE.rightHand || Q_IDENTITY;

function computeTrajectoryDelta(trajectory, phase) {
  if (!trajectory || trajectory.type === 'none') return [0.0, 0.0, 0.0];
  const amp = Number(trajectory.amplitudeM) || 0.045;
  if (trajectory.type === 'linear') {
    return evaluateLinearTrajectoryOffset(trajectory.variant, phase, amp);
  }
  if (trajectory.type === 'curved') {
    return evaluateCurvedTrajectoryOffset(trajectory.variant, phase, amp);
  }
  if (trajectory.type === 'circular') {
    return evaluateCircularTrajectoryOffset(trajectory.variant, phase, amp);
  }
  return [0.0, 0.0, 0.0];
}

function evaluateGraphemeStateAtPhase(spec, uStroke, extraLocusOffset = [0, 0, 0], prevArm = null) {
  const phase = applyRepetitionAndSpeedProfile(uStroke, spec.repetition, spec.speedFactor);
  const fingerPose = spec.isStaticHold
    ? spec.poseB100
    : interpolatePhalangePoseSO3(spec.poseA70, spec.poseB100, phase);

  const orientA = spec.handOrientationA || spec.handOrientationB;
  const orientB = spec.handOrientationB;
  const handOrient = {
    pitchDeg: orientA.pitchDeg + (orientB.pitchDeg - orientA.pitchDeg) * phase,
    yawDeg: orientA.yawDeg + (orientB.yawDeg - orientA.yawDeg) * phase,
    rollDeg: orientA.rollDeg + (orientB.rollDeg - orientA.rollDeg) * phase,
    axialTwistDeg: (orientA.axialTwistDeg || 0) + ((orientB.axialTwistDeg || 0) - (orientA.axialTwistDeg || 0)) * phase
  };

  const trajDelta = spec.isStaticHold ? [0, 0, 0] : computeTrajectoryDelta(spec.trajectory, phase);
  const contactZBias = spec.contactMode === 'DESLIZAR' ? -0.010 : 0.0;

  const targetWristPos = [
    NEUTRAL_FINGERSPELLING_LOCUS[0] + trajDelta[0] + (extraLocusOffset[0] || 0),
    NEUTRAL_FINGERSPELLING_LOCUS[1] + trajDelta[1] + (extraLocusOffset[1] || 0),
    NEUTRAL_FINGERSPELLING_LOCUS[2] + trajDelta[2] + (extraLocusOffset[2] || 0) + contactZBias
  ];

  const armSolved = solveRightArmTwoBoneIK(targetWristPos, handOrient, prevArm);
  return {
    arm: armSolved,
    fingers: fingerPose,
    wristWorldPos: armSolved.wristWorldPos
  };
}

function buildFull54BoneTracks(times, framePoses, applyOneEuro = true) {
  const tracks = [];
  for (const boneName of HUMAN_BONE_NAMES) {
    const restQ = REST_POSE[boneName] || Q_IDENTITY;
    const filter = applyOneEuro ? new OneEuroQuaternionFilter(1.0, 0.005, 1.0) : null;
    const flatRotations = [];
    let prevQ = null;

    for (let k = 0; k < times.length; k++) {
      const t = times[k];
      const rawQ = (framePoses[k] && framePoses[k][boneName]) || restQ;
      const isStaticStrokeSample = Boolean(framePoses[k] && framePoses[k]._preserveExactStaticHold);
      let qStep;
      if (isStaticStrokeSample && prevQ) {
        qStep = ensureHemisphereContinuity(rawQ, prevQ);
        if (filter) filter.filter(qStep, t);
      } else if (filter) {
        qStep = filter.filter(rawQ, t);
      } else {
        qStep = clampQuaternionStepDeg(prevQ, rawQ);
      }
      prevQ = qStep;
      flatRotations.push(qStep[0], qStep[1], qStep[2], qStep[3]);
    }

    tracks.push({
      boneName,
      times: [...times],
      rotations: flatRotations,
      interpolation: 'SLERP'
    });
  }
  return tracks;
}

/**
 * Crea un `SignClip` validado sobre los 54 huesos VRM 1.0 para cualquiera de
 * los 30 grafemas del alfabeto manual LSEC (`A`..`Z`, `CH`, `LL`, `Ñ`, `RR`).
 */
export function createLSECFingerspellingSignClip(graphemeInput, options = {}) {
  const tokens = tokenizeLSECFingerspelling(String(graphemeInput || 'A'));
  const token = tokens[0] || { grapheme: 'A', displayChar: 'A' };
  const g = token.grapheme;
  const spec = LSEC_FINGERSPELLING_CATALOG[g] || LSEC_FINGERSPELLING_CATALOG.A;

  const baseDurationMs = options.durationMs || (spec.isDynamic ? 1450 : 1250);
  const durationMs = Math.round(baseDurationMs / (spec.speedFactor || 1.0));
  const durationSec = durationMs / 1000.0;

  const strokeStartSec = Number((durationSec * 0.22).toFixed(4));
  const strokeEndSec = Number((durationSec * 0.78).toFixed(4));
  const numStrokeSamples = spec.isDynamic ? 15 : 7;

  const times = [
    0.0,
    Number((strokeStartSec * 0.20).toFixed(4)),
    Number((strokeStartSec * 0.40).toFixed(4)),
    Number((strokeStartSec * 0.60).toFixed(4)),
    Number((strokeStartSec * 0.80).toFixed(4))
  ];
  for (let i = 0; i < numStrokeSamples; i++) {
    const u = i / (numStrokeSamples - 1);
    const t = strokeStartSec + u * (strokeEndSec - strokeStartSec);
    times.push(Number(t.toFixed(4)));
  }
  const recSpan = durationSec - strokeEndSec;
  times.push(
    Number((strokeEndSec + recSpan * 0.20).toFixed(4)),
    Number((strokeEndSec + recSpan * 0.40).toFixed(4)),
    Number((strokeEndSec + recSpan * 0.60).toFixed(4)),
    Number((strokeEndSec + recSpan * 0.80).toFixed(4)),
    Number(durationSec.toFixed(4))
  );

  const startStrokeEval = evaluateGraphemeStateAtPhase(spec, 0.0);
  const endStrokeEval = evaluateGraphemeStateAtPhase(spec, 1.0);

  const framePoses = [];
  let prevArm = null;

  for (let k = 0; k < times.length; k++) {
    const t = times[k];
    const poseMap = { ...REST_POSE };

    if (t <= 1e-5 || t >= durationSec - 1e-5) {
      prevArm = {
        rightShoulder: Q_REST_R_SHOULDER,
        rightUpperArm: Q_REST_R_UPPER,
        rightLowerArm: Q_REST_R_LOWER,
        rightHand: Q_REST_R_HAND
      };
      framePoses.push(poseMap);
      continue;
    }

    if (t < strokeStartSec) {
      const alphaPrep = t / strokeStartSec;
      const smoothPrep = 0.5 * (1.0 - Math.cos(Math.PI * alphaPrep));
      poseMap.rightShoulder = slerpQuatAntipodal(Q_REST_R_SHOULDER, startStrokeEval.arm.rightShoulder, smoothPrep);
      poseMap.rightUpperArm = slerpQuatAntipodal(Q_REST_R_UPPER, startStrokeEval.arm.rightUpperArm, smoothPrep);
      poseMap.rightLowerArm = slerpQuatAntipodal(Q_REST_R_LOWER, startStrokeEval.arm.rightLowerArm, smoothPrep);
      poseMap.rightHand = slerpQuatAntipodal(Q_REST_R_HAND, startStrokeEval.arm.rightHand, smoothPrep);
      for (const fBone of RIGHT_HAND_PHALANX_BONES) {
        poseMap[fBone] = slerpQuatAntipodal(Q_IDENTITY, startStrokeEval.fingers[fBone], smoothPrep);
      }
      prevArm = {
        rightShoulder: poseMap.rightShoulder,
        rightUpperArm: poseMap.rightUpperArm,
        rightLowerArm: poseMap.rightLowerArm,
        rightHand: poseMap.rightHand
      };
      framePoses.push(poseMap);
      continue;
    }

    if (t > strokeEndSec) {
      const alphaRec = (t - strokeEndSec) / Math.max(1e-4, durationSec - strokeEndSec);
      const smoothRec = 0.5 * (1.0 - Math.cos(Math.PI * alphaRec));
      poseMap.rightShoulder = slerpQuatAntipodal(endStrokeEval.arm.rightShoulder, Q_REST_R_SHOULDER, smoothRec);
      poseMap.rightUpperArm = slerpQuatAntipodal(endStrokeEval.arm.rightUpperArm, Q_REST_R_UPPER, smoothRec);
      poseMap.rightLowerArm = slerpQuatAntipodal(endStrokeEval.arm.rightLowerArm, Q_REST_R_LOWER, smoothRec);
      poseMap.rightHand = slerpQuatAntipodal(endStrokeEval.arm.rightHand, Q_REST_R_HAND, smoothRec);
      for (const fBone of RIGHT_HAND_PHALANX_BONES) {
        poseMap[fBone] = slerpQuatAntipodal(endStrokeEval.fingers[fBone], Q_IDENTITY, smoothRec);
      }
      prevArm = {
        rightShoulder: poseMap.rightShoulder,
        rightUpperArm: poseMap.rightUpperArm,
        rightLowerArm: poseMap.rightLowerArm,
        rightHand: poseMap.rightHand
      };
      framePoses.push(poseMap);
      continue;
    }

    const uStroke = (t - strokeStartSec) / Math.max(1e-4, strokeEndSec - strokeStartSec);
    const stepEval = evaluateGraphemeStateAtPhase(spec, uStroke, [0, 0, 0], prevArm);
    poseMap.rightShoulder = stepEval.arm.rightShoulder;
    poseMap.rightUpperArm = stepEval.arm.rightUpperArm;
    poseMap.rightLowerArm = stepEval.arm.rightLowerArm;
    poseMap.rightHand = stepEval.arm.rightHand;
    for (const fBone of RIGHT_HAND_PHALANX_BONES) {
      poseMap[fBone] = stepEval.fingers[fBone];
    }
    if (spec.isStaticHold) {
      poseMap._preserveExactStaticHold = true;
    }
    prevArm = stepEval.arm;
    framePoses.push(poseMap);
  }

  const boneTracks = buildFull54BoneTracks(times, framePoses, !spec.isStaticHold);

  const clip = {
    clipId: `LSEC_DACT_${g === 'Ñ' ? 'NH' : g}_V1`,
    gloss: `DACT_${g}`,
    conceptId: `lsec.dactilologia.${g.toLowerCase()}`,
    version: '1.0.0',
    durationMs,
    status: 'VALIDATED_LSEC',
    provenance: 'LSEC_OFFICIAL_GUIDE_PDF_P10',
    validationStatus: 'VALIDATED_LSEC',
    dominantHand: 'RIGHT',
    twoHanded: false,
    entryPose: 'NEUTRAL',
    exitPose: 'NEUTRAL',
    boneTracks,
    expressionTracks: [
      { expressionName: 'neutral', times: [0.0, Number(durationSec.toFixed(4))], values: [0.95, 0.95], interpolation: 'LINEAR' }
    ],
    spatialConstraints: [
      { type: 'MIN_CHEST_CLEARANCE_M', minClearanceM: 0.02, locus: [...NEUTRAL_FINGERSPELLING_LOCUS] }
    ],
    stroke: {
      startSec: strokeStartSec,
      endSec: strokeEndSec,
      durationSec: Number((strokeEndSec - strokeStartSec).toFixed(4)),
      source: 'fingerspelling_lsec_pdf'
    },
    metadata: {
      description: spec.description,
      isValidatedLSEC: true,
      isFingerspelling: true,
      grapheme: g,
      displayChar: token.displayChar,
      isStaticHold: spec.isStaticHold,
      isDynamic: spec.isDynamic,
      opacityMode: spec.opacityMode,
      trajectory: spec.trajectory,
      repetition: spec.repetition,
      speedFactor: spec.speedFactor,
      contactMode: spec.contactMode,
      sourceDocument: 'Guia-Uso-ilustraciones.pdf (Páginas 1-10)'
    }
  };

  validateSignClip(clip);
  return clip;
}

/**
 * Compila una palabra o glosa deletreada completa manteniendo la mano activa en el
 * espacio neutro de dactilología entre letra y letra (sin caer al reposo intermedio).
 */
export function createLSECFingerspellingWordClip(wordOrGloss, options = {}) {
  const tokens = tokenizeLSECFingerspelling(wordOrGloss);
  if (tokens.length === 0) {
    return createLSECFingerspellingSignClip('A', options);
  }
  if (tokens.length === 1 && !options.forceWordContainer) {
    const singleClip = createLSECFingerspellingSignClip(tokens[0].displayChar, options);
    singleClip.gloss = String(wordOrGloss).trim().toUpperCase();
    return singleClip;
  }

  const perLetterSec = options.perLetterSec || 0.38;
  const interLetterTransitionSec = options.interLetterTransitionSec || 0.11;
  const prepSec = options.prepSec ?? 0.20;
  const recSec = options.recSec ?? 0.22;

  const rawBodySec = tokens.length * perLetterSec + (tokens.length - 1) * interLetterTransitionSec;
  const hasExplicitTarget = Boolean(options.targetDurationSec && Number(options.targetDurationSec) > 0);
  const targetDurationSec = hasExplicitTarget
    ? Math.max(0.60, Number(options.targetDurationSec))
    : (prepSec + rawBodySec + recSec);

  const minScale = 1.0;
  const scale = Math.max(minScale, (targetDurationSec - prepSec - recSec) / Math.max(0.15, rawBodySec));
  const letterHoldSec = perLetterSec * scale;
  const letterTransSec = interLetterTransitionSec * scale;

  const strokeStartSec = Number(prepSec.toFixed(4));
  const strokeEndSec = Number((prepSec + tokens.length * letterHoldSec + (tokens.length - 1) * letterTransSec).toFixed(4));
  const totalDurationSec = Number((strokeEndSec + recSec).toFixed(4));
  const durationMs = Math.round(totalDurationSec * 1000);

  const letterSegments = [];
  let cursorSec = strokeStartSec;
  for (let idx = 0; idx < tokens.length; idx++) {
    const tk = tokens[idx];
    const spec = LSEC_FINGERSPELLING_CATALOG[tk.grapheme] || LSEC_FINGERSPELLING_CATALOG.A;
    const segStart = cursorSec;
    const segEnd = cursorSec + letterHoldSec;
    const repeatPulseOffset = tk.microRearticulation ? [-0.018, 0.008, 0.012] : [0.0, 0.0, 0.0];
    letterSegments.push({
      token: tk,
      spec,
      startSec: segStart,
      endSec: segEnd,
      repeatPulseOffset,
      startEval: evaluateGraphemeStateAtPhase(spec, 0.0, repeatPulseOffset),
      endEval: evaluateGraphemeStateAtPhase(spec, 1.0, repeatPulseOffset)
    });
    cursorSec = segEnd + (idx < tokens.length - 1 ? letterTransSec : 0.0);
  }

  const dt = 1.0 / 30.0;
  const numSteps = Math.max(12, Math.ceil(totalDurationSec / dt));
  const times = [];
  const framePoses = [];
  let prevArm = null;

  for (let step = 0; step <= numSteps; step++) {
    const t = step === numSteps ? totalDurationSec : Number((step * (totalDurationSec / numSteps)).toFixed(4));
    times.push(t);
    const poseMap = { ...REST_POSE };

    if (t <= 1e-5 || t >= totalDurationSec - 1e-5) {
      prevArm = {
        rightShoulder: Q_REST_R_SHOULDER,
        rightUpperArm: Q_REST_R_UPPER,
        rightLowerArm: Q_REST_R_LOWER,
        rightHand: Q_REST_R_HAND
      };
      framePoses.push(poseMap);
      continue;
    }

    if (t < strokeStartSec) {
      const firstSeg = letterSegments[0];
      const uPrep = 0.5 * (1.0 - Math.cos(Math.PI * (t / strokeStartSec)));
      poseMap.rightShoulder = slerpQuatAntipodal(Q_REST_R_SHOULDER, firstSeg.startEval.arm.rightShoulder, uPrep);
      poseMap.rightUpperArm = slerpQuatAntipodal(Q_REST_R_UPPER, firstSeg.startEval.arm.rightUpperArm, uPrep);
      poseMap.rightLowerArm = slerpQuatAntipodal(Q_REST_R_LOWER, firstSeg.startEval.arm.rightLowerArm, uPrep);
      poseMap.rightHand = slerpQuatAntipodal(Q_REST_R_HAND, firstSeg.startEval.arm.rightHand, uPrep);
      for (const fBone of RIGHT_HAND_PHALANX_BONES) {
        poseMap[fBone] = slerpQuatAntipodal(Q_IDENTITY, firstSeg.startEval.fingers[fBone], uPrep);
      }
      prevArm = {
        rightShoulder: poseMap.rightShoulder,
        rightUpperArm: poseMap.rightUpperArm,
        rightLowerArm: poseMap.rightLowerArm,
        rightHand: poseMap.rightHand
      };
      framePoses.push(poseMap);
      continue;
    }

    if (t > strokeEndSec) {
      const lastSeg = letterSegments[letterSegments.length - 1];
      const uRec = 0.5 * (1.0 - Math.cos(Math.PI * ((t - strokeEndSec) / Math.max(1e-4, totalDurationSec - strokeEndSec))));
      poseMap.rightShoulder = slerpQuatAntipodal(lastSeg.endEval.arm.rightShoulder, Q_REST_R_SHOULDER, uRec);
      poseMap.rightUpperArm = slerpQuatAntipodal(lastSeg.endEval.arm.rightUpperArm, Q_REST_R_UPPER, uRec);
      poseMap.rightLowerArm = slerpQuatAntipodal(lastSeg.endEval.arm.rightLowerArm, Q_REST_R_LOWER, uRec);
      poseMap.rightHand = slerpQuatAntipodal(lastSeg.endEval.arm.rightHand, Q_REST_R_HAND, uRec);
      for (const fBone of RIGHT_HAND_PHALANX_BONES) {
        poseMap[fBone] = slerpQuatAntipodal(lastSeg.endEval.fingers[fBone], Q_IDENTITY, uRec);
      }
      prevArm = {
        rightShoulder: poseMap.rightShoulder,
        rightUpperArm: poseMap.rightUpperArm,
        rightLowerArm: poseMap.rightLowerArm,
        rightHand: poseMap.rightHand
      };
      framePoses.push(poseMap);
      continue;
    }

    let handled = false;
    for (let idx = 0; idx < letterSegments.length; idx++) {
      const seg = letterSegments[idx];
      if (t >= seg.startSec && t <= seg.endSec + 1e-6) {
        const uLocal = (t - seg.startSec) / Math.max(1e-4, seg.endSec - seg.startSec);
        const pulseWeight = seg.token.microRearticulation ? Math.sin(Math.PI * uLocal) : 0.0;
        const offset = [
          seg.repeatPulseOffset[0] * pulseWeight,
          seg.repeatPulseOffset[1] * pulseWeight,
          seg.repeatPulseOffset[2] * pulseWeight
        ];
        const stepEval = evaluateGraphemeStateAtPhase(seg.spec, uLocal, offset, prevArm);
        poseMap.rightShoulder = stepEval.arm.rightShoulder;
        poseMap.rightUpperArm = stepEval.arm.rightUpperArm;
        poseMap.rightLowerArm = stepEval.arm.rightLowerArm;
        poseMap.rightHand = stepEval.arm.rightHand;
        for (const fBone of RIGHT_HAND_PHALANX_BONES) {
          poseMap[fBone] = stepEval.fingers[fBone];
        }
        prevArm = stepEval.arm;
        handled = true;
        break;
      }

      if (idx < letterSegments.length - 1) {
        const nextSeg = letterSegments[idx + 1];
        if (t > seg.endSec && t < nextSeg.startSec) {
          const uBridge = 0.5 * (1.0 - Math.cos(Math.PI * ((t - seg.endSec) / Math.max(1e-4, nextSeg.startSec - seg.endSec))));
          const bridgeDip = nextSeg.token.microRearticulation ? Math.sin(Math.PI * uBridge) : 0.0;
          const nextStartEval = bridgeDip > 0
            ? evaluateGraphemeStateAtPhase(nextSeg.spec, 0.0, [
              nextSeg.repeatPulseOffset[0] * bridgeDip,
              nextSeg.repeatPulseOffset[1] * bridgeDip,
              nextSeg.repeatPulseOffset[2] * bridgeDip
            ], prevArm)
            : nextSeg.startEval;

          poseMap.rightShoulder = slerpQuatAntipodal(seg.endEval.arm.rightShoulder, nextStartEval.arm.rightShoulder, uBridge);
          poseMap.rightUpperArm = slerpQuatAntipodal(seg.endEval.arm.rightUpperArm, nextStartEval.arm.rightUpperArm, uBridge);
          poseMap.rightLowerArm = slerpQuatAntipodal(seg.endEval.arm.rightLowerArm, nextStartEval.arm.rightLowerArm, uBridge);
          poseMap.rightHand = slerpQuatAntipodal(seg.endEval.arm.rightHand, nextStartEval.arm.rightHand, uBridge);
          for (const fBone of RIGHT_HAND_PHALANX_BONES) {
            poseMap[fBone] = slerpQuatAntipodal(seg.endEval.fingers[fBone], nextStartEval.fingers[fBone], uBridge);
          }
          prevArm = {
            rightShoulder: poseMap.rightShoulder,
            rightUpperArm: poseMap.rightUpperArm,
            rightLowerArm: poseMap.rightLowerArm,
            rightHand: poseMap.rightHand
          };
          handled = true;
          break;
        }
      }
    }

    if (!handled) {
      const lastSeg = letterSegments[letterSegments.length - 1];
      poseMap.rightShoulder = lastSeg.endEval.arm.rightShoulder;
      poseMap.rightUpperArm = lastSeg.endEval.arm.rightUpperArm;
      poseMap.rightLowerArm = lastSeg.endEval.arm.rightLowerArm;
      poseMap.rightHand = lastSeg.endEval.arm.rightHand;
      for (const fBone of RIGHT_HAND_PHALANX_BONES) {
        poseMap[fBone] = lastSeg.endEval.fingers[fBone];
      }
    }
    framePoses.push(poseMap);
  }

  const boneTracks = buildFull54BoneTracks(times, framePoses, true);
  const cleanGloss = String(wordOrGloss).trim().toUpperCase();
  const graphemeList = tokens.map(tk => tk.grapheme);
  const displayList = tokens.map(tk => tk.displayChar);

  const clip = {
    clipId: `LSEC_DACT_WORD_${graphemeList.join('_').replace(/Ñ/g, 'NH')}_V1`,
    gloss: cleanGloss,
    conceptId: `lsec.dactilologia.word.${cleanGloss.toLowerCase()}`,
    version: '1.0.0',
    durationMs,
    status: 'VALIDATED_LSEC',
    provenance: 'LSEC_OFFICIAL_GUIDE_PDF_P10',
    validationStatus: 'VALIDATED_LSEC',
    dominantHand: 'RIGHT',
    twoHanded: false,
    entryPose: 'NEUTRAL',
    exitPose: 'NEUTRAL',
    boneTracks,
    expressionTracks: [
      { expressionName: 'neutral', times: [0.0, totalDurationSec], values: [0.95, 0.95], interpolation: 'LINEAR' }
    ],
    spatialConstraints: [
      { type: 'MIN_CHEST_CLEARANCE_M', minClearanceM: 0.02, locus: [...NEUTRAL_FINGERSPELLING_LOCUS] }
    ],
    stroke: {
      startSec: strokeStartSec,
      endSec: strokeEndSec,
      durationSec: Number((strokeEndSec - strokeStartSec).toFixed(4)),
      source: 'fingerspelling_word_lsec'
    },
    metadata: {
      description: `Deletreo continuo LSEC (${displayList.join(' -> ')}) en espacio neutro sin descenso intermedio al reposo.`,
      isValidatedLSEC: true,
      isFingerspelling: true,
      isWordFingerspelling: true,
      graphemes: graphemeList,
      displayChars: displayList,
      tokens,
      letterSegments: letterSegments.map(s => ({
        grapheme: s.token.grapheme,
        displayChar: s.token.displayChar,
        startSec: Number(s.startSec.toFixed(4)),
        endSec: Number(s.endSec.toFixed(4)),
        microRearticulation: s.token.microRearticulation
      }))
    }
  };

  validateSignClip(clip);
  return clip;
}

export function getAllLSECFingerspellingClips() {
  return LSEC_FINGERSPELLING_GRAPHEMES.map(g => createLSECFingerspellingSignClip(g));
}
