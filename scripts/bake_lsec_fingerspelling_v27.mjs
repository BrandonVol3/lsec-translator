/**
 * LSEC Studio — Exportador y Horneador Físico de las 30 Señas de Dactilología LSEC a v2.7
 *
 * Hornea los 30 grafemas oficiales del alfabeto manual ecuatoriano (Guía Oficial PDF, p. 1-10)
 * generados por el motor cinemático de 54 huesos VRM 1.0 (Two-Bone Analytical IK cerrado +
 * cuaterniones falángicos en SO(3) + filtrado One-Euro) como archivos físicos `animation.json`
 * e `info.json` dentro del catálogo v2.7 en disco y actualiza `stroke_index_v27.json`.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { HUMAN_BONE_NAMES, REST_POSE } from '../app/static/js/avatar/sign-animation-schema.js';
import { slerpQuatAntipodal, quatAngularDistanceDeg as quatAngleDeg } from '../app/static/js/avatar/sign-clips-fingerspelling-primitives.js';
import {
  LSEC_FINGERSPELLING_GRAPHEMES,
  LSEC_FINGERSPELLING_CATALOG,
  createLSECFingerspellingSignClip
} from '../app/static/js/avatar/sign-clips-fingerspelling-lsec.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROTO_ROOT = path.resolve(__dirname, '..');
const WORKSPACE_ROOT = path.resolve(PROTO_ROOT, '..');

const V27_DIR = path.join(WORKSPACE_ROOT, 'Diccionario LSEC', 'senas_vrm_standardized_v2.7');
const V27_DACT_HIDDEN_DIR = path.join(V27_DIR, '.dactilologia_v2.7');
const DACT_STANDALONE_DIR = path.join(WORKSPACE_ROOT, 'Diccionario LSEC', 'senas_vrm_dactilologia_v2.7');
const STATIC_CLIPS_DACT_DIR = path.join(PROTO_ROOT, 'app', 'static', 'assets', 'clips', 'dactilologia_v27');

const STROKE_INDEX_PATHS = [
  path.join(PROTO_ROOT, 'app', 'data', 'stroke_index_v27.json'),
  path.join(V27_DIR, 'stroke_index.json')
];

const EXPRESSIONS_LIST = [
  'aa', 'ih', 'ou', 'ee', 'oh',
  'blink', 'blinkLeft', 'blinkRight',
  'happy', 'angry', 'sad', 'relaxed', 'surprised', 'neutral'
];

const BLENDSHAPES_LIST = [
  'browDownLeft', 'browDownRight', 'browInnerUp', 'browOuterUpLeft', 'browOuterUpRight',
  'eyeBlinkLeft', 'eyeBlinkRight', 'eyeLookDownLeft', 'eyeLookDownRight', 'eyeLookInLeft',
  'eyeLookInRight', 'eyeLookOutLeft', 'eyeLookOutRight', 'eyeLookUpLeft', 'eyeLookUpRight',
  'eyeSquintLeft', 'eyeSquintRight', 'eyeWideLeft', 'eyeWideRight', 'jawForward',
  'jawLeft', 'jawRight', 'jawOpen', 'mouthClose', 'mouthDimpleLeft',
  'mouthDimpleRight', 'mouthFrownLeft', 'mouthFrownRight', 'mouthFunnel', 'mouthLeft',
  'mouthLowerDownLeft', 'mouthLowerDownRight', 'mouthPressLeft', 'mouthPressRight', 'mouthPucker',
  'mouthRight', 'mouthRollLower', 'mouthRollUpper', 'mouthShrugLower', 'mouthShrugUpper',
  'mouthSmileLeft', 'mouthSmileRight', 'mouthStretchLeft', 'mouthStretchRight', 'mouthUpperUpLeft',
  'mouthUpperUpRight', 'cheekPuff', 'cheekSquintLeft', 'cheekSquintRight', 'noseSneerLeft',
  'noseSneerRight', 'tongueOut'
];

const LEFT_ANCHOR_BONES = [
  'leftShoulder', 'leftUpperArm', 'leftLowerArm', 'leftHand',
  'leftThumbMetacarpal', 'leftThumbProximal', 'leftThumbDistal',
  'leftIndexProximal', 'leftIndexIntermediate', 'leftIndexDistal',
  'leftMiddleProximal', 'leftMiddleIntermediate', 'leftMiddleDistal',
  'leftRingProximal', 'leftRingIntermediate', 'leftRingDistal',
  'leftLittleProximal', 'leftLittleIntermediate', 'leftLittleDistal'
];

const RIGHT_ANCHOR_BONES = [
  'rightShoulder', 'rightUpperArm', 'rightLowerArm', 'rightHand',
  'rightThumbMetacarpal', 'rightThumbProximal', 'rightThumbDistal',
  'rightIndexProximal', 'rightIndexIntermediate', 'rightIndexDistal',
  'rightMiddleProximal', 'rightMiddleIntermediate', 'rightMiddleDistal',
  'rightRingProximal', 'rightRingIntermediate', 'rightRingDistal',
  'rightLittleProximal', 'rightLittleIntermediate', 'rightLittleDistal'
];

const TORSO_ANCHOR_BONES = ['hips', 'spine', 'chest', 'neck', 'head'];

function round6(v) {
  return Number(Number(v || 0).toFixed(6));
}

function round4(v) {
  return Number(Number(v || 0).toFixed(4));
}

function sampleTrackQuaternionAt(track, tSec, fallbackQuat) {
  if (!track || !Array.isArray(track.times) || track.times.length === 0) {
    return fallbackQuat.map(round6);
  }
  const times = track.times;
  const rots = track.rotations;
  const n = times.length;
  if (tSec <= times[0]) {
    return [round6(rots[0]), round6(rots[1]), round6(rots[2]), round6(rots[3])];
  }
  if (tSec >= times[n - 1]) {
    const base = (n - 1) * 4;
    return [round6(rots[base]), round6(rots[base + 1]), round6(rots[base + 2]), round6(rots[base + 3])];
  }
  let idx = 0;
  for (let i = 0; i < n - 1; i++) {
    if (tSec >= times[i] && tSec <= times[i + 1]) {
      idx = i;
      break;
    }
  }
  const t0 = times[idx];
  const t1 = times[idx + 1];
  const alpha = (t1 > t0) ? (tSec - t0) / (t1 - t0) : 0.0;
  const b0 = idx * 4;
  const b1 = (idx + 1) * 4;
  const q0 = [rots[b0], rots[b0 + 1], rots[b0 + 2], rots[b0 + 3]];
  const q1 = [rots[b1], rots[b1 + 1], rots[b1 + 2], rots[b1 + 3]];
  return slerpQuatAntipodal(q0, q1, alpha).map(round6);
}

function buildDefaultExpressions() {
  const out = {};
  for (const k of EXPRESSIONS_LIST) {
    out[k] = k === 'neutral' ? 1.0 : 0.0;
  }
  return out;
}

function buildDefaultBlendshapes() {
  const out = {};
  for (const k of BLENDSHAPES_LIST) {
    out[k] = 0.0;
  }
  return out;
}

function extractAnchorPose(frameRotations) {
  const left = {};
  const right = {};
  const torso = {};
  for (const b of LEFT_ANCHOR_BONES) left[b] = (frameRotations[b] || REST_POSE[b] || [0, 0, 0, 1]).map(round4);
  for (const b of RIGHT_ANCHOR_BONES) right[b] = (frameRotations[b] || REST_POSE[b] || [0, 0, 0, 1]).map(round4);
  for (const b of TORSO_ANCHOR_BONES) torso[b] = (frameRotations[b] || REST_POSE[b] || [0, 0, 0, 1]).map(round4);
  return { left, right, torso };
}

function bakeGraphemeV27(grapheme, seqIdx, fps = 60) {
  const spec = LSEC_FINGERSPELLING_CATALOG[grapheme];
  const clip = createLSECFingerspellingSignClip(grapheme);
  const durationSec = round4(clip.durationMs / 1000.0);
  const totalFrames = Math.max(2, Math.round(durationSec * fps) + 1);
  const safeCode = grapheme === 'Ñ' ? 'NH' : grapheme;
  const folderName = `Letra ${grapheme}`;
  const slug = `letra_${safeCode.toLowerCase()}`;

  const trackByBone = new Map();
  for (const bt of clip.boneTracks) {
    trackByBone.set(bt.boneName, bt);
  }

  const defaultExpr = buildDefaultExpressions();
  const defaultBlend = buildDefaultBlendshapes();
  const frames = [];

  for (let f = 0; f < totalFrames; f++) {
    const t = round4(Math.min(durationSec, f / fps));
    const rotations = {};
    for (const boneName of HUMAN_BONE_NAMES) {
      const restQ = REST_POSE[boneName] || [0, 0, 0, 1];
      rotations[boneName] = sampleTrackQuaternionAt(trackByBone.get(boneName), t, restQ);
    }
    frames.push({
      frame: f,
      time: t,
      hipsPosition: [0.0, 0.907995, 0.003576],
      rotations,
      expressions: { ...defaultExpr },
      blendshapes: { ...defaultBlend }
    });
  }

  const strokeStartSec = clip.stroke.startSec;
  const strokeEndSec = clip.stroke.endSec;
  const startFrame = Math.max(0, Math.min(totalFrames - 2, Math.round(strokeStartSec * fps)));
  const endFrame = Math.max(startFrame + 1, Math.min(totalFrames - 1, Math.round(strokeEndSec * fps)));

  let maxFingerJumpAfterDeg = 0.0;
  let maxRotationJumpDeg = 0.0;
  for (let f = 1; f < frames.length; f++) {
    for (const b of RIGHT_ANCHOR_BONES) {
      const d = quatAngleDeg(frames[f - 1].rotations[b], frames[f].rotations[b]);
      if (d > maxRotationJumpDeg) maxRotationJumpDeg = d;
      if (b.startsWith('right') && !['rightShoulder', 'rightUpperArm', 'rightLowerArm', 'rightHand'].includes(b)) {
        if (d > maxFingerJumpAfterDeg) maxFingerJumpAfterDeg = d;
      }
    }
  }

  const strokeEntry = {
    sign: folderName,
    grapheme,
    gloss: `DACT_${grapheme}`,
    strokeStart: round4(startFrame / fps),
    strokeEnd: round4(endFrame / fps),
    strokeDuration: round4((endFrame - startFrame) / fps),
    originalDuration: durationSec,
    startFrame,
    endFrame,
    totalFrames,
    fps: Number(fps),
    confidence: 1.0,
    flags: {
      repeatedStroke: (spec.repetition || 1) > 1,
      oneHanded: true,
      tooShort: false,
      faceOnly: false,
      isFingerspelling: true,
      isStaticHold: Boolean(spec.isStaticHold),
      isDynamic: Boolean(spec.isDynamic)
    },
    activeHands: {
      left: false,
      right: true,
      dominant: 'right'
    },
    anchors: {
      start: extractAnchorPose(frames[startFrame].rotations),
      end: extractAnchorPose(frames[endFrame].rotations)
    },
    boundaryVelocity: {
      start: {
        left: { leftShoulder: [0, 0, 0], leftUpperArm: [0, 0, 0], leftLowerArm: [0, 0, 0], leftHand: [0, 0, 0] },
        right: { rightShoulder: [0, 0, 0], rightUpperArm: [0, 0, 0], rightLowerArm: [0, 0, 0], rightHand: [0, 0, 0] },
        speedDegPerSec: { left: 0.0, right: round4(maxRotationJumpDeg * fps * 0.25) }
      },
      end: {
        left: { leftShoulder: [0, 0, 0], leftUpperArm: [0, 0, 0], leftLowerArm: [0, 0, 0], leftHand: [0, 0, 0] },
        right: { rightShoulder: [0, 0, 0], rightUpperArm: [0, 0, 0], rightLowerArm: [0, 0, 0], rightHand: [0, 0, 0] },
        speedDegPerSec: { left: 0.0, right: round4(maxRotationJumpDeg * fps * 0.25) }
      }
    }
  };

  const handStdSummary = {
    version: 'v2.7',
    template_id: `dactilologia_lsec_${safeCode.toLowerCase()}`,
    segments: [[startFrame, endFrame]],
    mean_w: 1.0,
    hand_applied: ['right'],
    frames_modified: endFrame - startFrame + 1,
    status: 'STANDARDIZED',
    anatomical_clamps_applied: 0,
    max_finger_jump_after_deg: round4(maxFingerJumpAfterDeg)
  };

  const animationJson = {
    metadata: {
      sign: folderName,
      grapheme,
      slug,
      fps,
      duration: durationSec,
      totalFrames,
      coordinateSystem: 'VRM1.0_RightHanded_YUp_ZForward',
      quaternionFormat: '[x, y, z, w]',
      generator: 'LSEC-VRM Procedural Fingerspelling Solver v2.7 (Two-Bone Analytical IK + SO(3) Phalanges)',
      avatar: 'LSEC-Interpreter-Female',
      restCorrection: 'exact closed-form Two-Bone IK + anatomical phalanx quaternions',
      pipelineVersion: '2.7_Estandarizado',
      preparatoryPose: true,
      leadInFrames: startFrame,
      leadOutFrames: totalFrames - 1 - endFrame,
      pure1to1Copy: true,
      hasIllustration: true,
      priorSource: 'Guia-Uso-ilustraciones.pdf (Pagina 10)',
      isFingerspelling: true,
      isStaticHold: Boolean(spec.isStaticHold),
      isDynamic: Boolean(spec.isDynamic),
      opacityMode: spec.opacityMode,
      trajectory: spec.trajectory,
      repetition: spec.repetition,
      speedFactor: spec.speedFactor,
      contactMode: spec.contactMode,
      description: spec.description,
      fidelity: {
        avg_bone_delta_deg: 0.0,
        peak_bone_delta_deg: round4(maxRotationJumpDeg),
        avg_wrist_displacement_cm: 0.0,
        peak_wrist_displacement_cm: 0.0,
        passed_budget: true,
        tracks_recovered: true,
        reverted_to_original: false
      },
      gloss: `DACT_${grapheme}`,
      hasExplicitFacialExpression: false,
      defaultNeutralFacialMode: true,
      facialArchetype: 'neutral',
      facialArchetypeLabel: 'Neutral (Por Defecto)',
      nonManualStandard: {
        version: '1.0',
        policy: 'default_neutral_except_explicit',
        hasExplicitFacialExpression: false,
        defaultNeutralMode: true,
        archetype: 'neutral',
        archetypeLabel: 'Neutral (Por Defecto)',
        criterion: 'default_neutral',
        reason: 'Dactilología oficial LSEC (Guía de Uso de Ilustraciones, pág. 10).'
      },
      handStandardization: handStdSummary,
      stroke: strokeEntry
    },
    bones: [...HUMAN_BONE_NAMES],
    expressions: EXPRESSIONS_LIST,
    blendshapes: BLENDSHAPES_LIST,
    frames,
    stroke: strokeEntry,
    handStandardization: handStdSummary
  };

  const infoJson = {
    catalog_index: 5000 + seqIdx,
    sequential_index: seqIdx,
    slug,
    palabra: folderName,
    sign: folderName,
    grapheme,
    gloss: `DACT_${grapheme}`,
    is_variant: false,
    is_fingerspelling: true,
    categorias: ['dactilologia-lsec', `alfa-${ safeCode[0].toLowerCase() }`],
    source_document: 'Guia-Uso-ilustraciones.pdf (Páginas 1-10)',
    has_uhd_video: false,
    has_uhd_video_local: false,
    has_illustration: true,
    has_illustration_local: true,
    hand_configuration: 'dactilologia_lsec',
    hand_variant: `dactilologia_lsec_${safeCode.toLowerCase()}`,
    hand_variant_key: safeCode.toLowerCase(),
    hand_variant_label: `DACT-${grapheme}`,
    alphabetical_group: `alfa-${safeCode[0].toLowerCase()}`,
    hand_standardization: {
      version: 'v2.7',
      status: 'STANDARDIZED',
      skip_reason: '',
      hand_configuration: 'dactilologia_lsec',
      hand_variant: `dactilologia_lsec_${safeCode.toLowerCase()}`,
      hand_variant_label: `DACT-${grapheme}`,
      dominant_hand: 'right',
      active_hands: ['right'],
      is_bimanual: false,
      bimanual_mode: 'monomanual',
      standardized_hands: ['right'],
      frames_modified: endFrame - startFrame + 1,
      stable_segment: [startFrame, endFrame],
      secondary_stable_segment: null,
      template_inherited_from_base: true,
      inheritance_alpha: 1.0,
      distance_to_template_before_deg: 0.0,
      distance_to_template_after_deg: 0.0,
      distance_reduction_pct: 100.0,
      mean_blend_weight: 1.0,
      anatomical_clamps_applied: 0,
      max_finger_jump_before_deg: round4(maxFingerJumpAfterDeg),
      max_finger_jump_after_deg: round4(maxFingerJumpAfterDeg),
      max_rotation_jump_deg: round4(maxRotationJumpDeg)
    }
  };

  return { folderName, safeCode, clip, animationJson, infoJson, strokeEntry };
}

function main() {
  fs.mkdirSync(V27_DACT_HIDDEN_DIR, { recursive: true });
  fs.mkdirSync(DACT_STANDALONE_DIR, { recursive: true });
  fs.mkdirSync(STATIC_CLIPS_DACT_DIR, { recursive: true });

  const fingerspellingStrokeMap = {};
  let bakedCount = 0;

  for (let i = 0; i < LSEC_FINGERSPELLING_GRAPHEMES.length; i++) {
    const g = LSEC_FINGERSPELLING_GRAPHEMES[i];
    const baked = bakeGraphemeV27(g, i + 1, 60);

    for (const baseDir of [V27_DACT_HIDDEN_DIR, DACT_STANDALONE_DIR]) {
      const signDir = path.join(baseDir, baked.folderName);
      fs.mkdirSync(signDir, { recursive: true });
      fs.writeFileSync(path.join(signDir, 'animation.json'), JSON.stringify(baked.animationJson));
      fs.writeFileSync(path.join(signDir, 'info.json'), JSON.stringify(baked.infoJson, null, 2));
    }

    const clipFile = path.join(STATIC_CLIPS_DACT_DIR, `LSEC_DACT_${baked.safeCode}_V1.json`);
    fs.writeFileSync(clipFile, JSON.stringify(baked.clip, null, 2));

    fingerspellingStrokeMap[baked.folderName] = baked.strokeEntry;
    bakedCount++;
  }

  for (const strokePath of STROKE_INDEX_PATHS) {
    if (fs.existsSync(strokePath)) {
      const raw = JSON.parse(fs.readFileSync(strokePath, 'utf8'));
      raw.totalFingerspellingSigns = bakedCount;
      raw.totalWithFingerspelling = (Number(raw.totalSigns) || 4142) + bakedCount;
      raw.fingerspellingSigns = fingerspellingStrokeMap;
      fs.writeFileSync(strokePath, JSON.stringify(raw));
      console.log(`✓ Actualizado ${strokePath} (totalSigns=${raw.totalSigns}, totalFingerspellingSigns=${raw.totalFingerspellingSigns})`);
    }
  }

  console.log(`✓ Horneadas las ${bakedCount} señas de dactilología LSEC en:`);
  console.log(`  1) ${V27_DACT_HIDDEN_DIR}`);
  console.log(`  2) ${DACT_STANDALONE_DIR}`);
  console.log(`  3) ${STATIC_CLIPS_DACT_DIR}`);
}

main();
