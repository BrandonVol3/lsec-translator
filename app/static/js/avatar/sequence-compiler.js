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
  LEFT_ARM_BONES,
  RIGHT_ARM_BONES,
  LEFT_FINGER_BONES,
  RIGHT_FINGER_BONES,
  TORSO_HEAD_BONES,
  ALL_COMPILER_BONES,
  FINGER_BONE_SET,
  ARM_BONE_SET,
  CANONICAL_REST_BONES,
  quatNormalize,
  quatDot,
  quatEnsureSameHemisphere,
  quatConjugate,
  quatMultiply,
  quatAngleDeg,
  quatLogRad,
  quatExpRad,
  quatSlerp,
  minimumJerk,
  interpolateSO3HermiteC1,
  buildPreparedClipDescriptor,
  applyBreathingMicroMotion,
  makeNeutralExpressions,
  interpolateExpressions,
  applyCompiledSampleToModel,
  OneEuroQuaternionFilter,
  LSEC_FINGERSPELLING_GRAPHEMES,
  LSEC_FINGERSPELLING_CATALOG,
  tokenizeLSECFingerspelling,
  createLSECFingerspellingSignClip,
  createLSECFingerspellingWordClip
} from './sequence-coarticulation-math.js';

import {
  extractRawEntries,
  resolveClipFromMap,
  groupPlayableEntriesIntoRuns,
  schedulePlayableRunsWithLagBudget,
  buildCompiledKinematicSegments
} from './sequence-run-scheduler.js';

export {
  LEFT_ARM_BONES,
  RIGHT_ARM_BONES,
  LEFT_FINGER_BONES,
  RIGHT_FINGER_BONES,
  TORSO_HEAD_BONES,
  ALL_COMPILER_BONES,
  CANONICAL_REST_BONES,
  quatNormalize,
  quatDot,
  quatEnsureSameHemisphere,
  quatConjugate,
  quatMultiply,
  quatAngleDeg,
  quatLogRad,
  quatExpRad,
  quatSlerp,
  minimumJerk,
  interpolateSO3HermiteC1,
  applyCompiledSampleToModel,
  OneEuroQuaternionFilter,
  LSEC_FINGERSPELLING_GRAPHEMES,
  LSEC_FINGERSPELLING_CATALOG,
  tokenizeLSECFingerspelling,
  createLSECFingerspellingSignClip,
  createLSECFingerspellingWordClip
};

// ---------------------------------------------------------------------------
// Clase Principal: SequenceCompiler
// ---------------------------------------------------------------------------

export class SequenceCompiler {
  constructor(options = {}) {
    this.options = {
      maxSpeed: 1.0,
      minSpeed: 0.70,
      maxLagSec: Infinity,
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
    return extractRawEntries(project);
  }

  _resolveClipFromMap(entry, clipMap) {
    return resolveClipFromMap(entry, clipMap);
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
    const maxSpeed = Math.min(1.0, Math.max(0.1, Number(opts.maxSpeed) || 1.0));
    const minSpeed = Math.max(0.4, Math.min(maxSpeed, Number(opts.minSpeed) || 0.70));
    const maxLagSec = (opts.maxLagSec !== undefined && opts.maxLagSec !== null)
      ? Number(opts.maxLagSec)
      : Infinity;
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

    // 1. Preparar descriptores de trazo para cada glosa (incluyendo síntesis dactilológica continua y fallback OOV)
    const entries = rawEntries.map((item, idx) => {
      let clip = this._resolveClipFromMap(item, clipMap);
      const isOovFallback = Boolean(
        !clip &&
        !item.isFingerspelling &&
        opts.fingerspellOovFallback !== false
      );
      const effectiveFingerspelling = Boolean(item.isFingerspelling || isOovFallback);
      if (effectiveFingerspelling && opts.synthesizeFingerspelling !== false) {
        const fsTarget = item.isFingerspelling
          ? item.gloss
          : (item.raw?.validation?.fallback_fingerspelling_gloss || item.gloss || item.raw?.source_word);
        const slotDur = Math.max(0.55, Number(item.slotDuration) || 1.0);
        const needsProceduralWordClip = !clip
          || clip.stroke?.source !== 'fingerspelling_word_lsec'
          || (clip.stroke?.durationSec > slotDur * maxSpeed * 1.05);
        if (needsProceduralWordClip) {
          clip = createLSECFingerspellingWordClip(fsTarget, {
            targetDurationSec: Math.max(0.65, slotDur * 1.35)
          });
        }
      }
      const prepared = clip ? buildPreparedClipDescriptor(clip) : null;
      return {
        ...item,
        isFingerspelling: effectiveFingerspelling,
        orderIndex: idx,
        clip: clip || null,
        prepared,
        playable: Boolean(prepared),
        status: effectiveFingerspelling ? 'FINGERSPELLING' : (prepared ? 'PLAYABLE' : 'MISSING')
      };
    });

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
          maxSpeedUsed: 1.0,
          strokeRetainedPct: 100.0,
          minStrokeRetainedPct: 100.0,
          allStrokes100PctRetained: true
        }
      };
      this.compiled = this.plan;
      return this.plan;
    }

    // 2. Agrupar glosas reproducibles en corridas contiguas (separadas únicamente cuando hay pausa > restGapThresholdSec)
    const runs = groupPlayableEntriesIntoRuns(entries, playableIndices, restGapThresholdSec);

    // 3. Planificar cada corrida con transición adaptativa, backpropagation y presupuesto de lag <= 1.0 s
    const schedParams = { maxSpeed, minSpeed, maxLagSec, minTrans, maxTrans, angleRate, restTransSec };
    schedulePlayableRunsWithLagBudget(entries, runs, schedParams);

    // 4. Construir segmentos cinemáticos continuos
    const {
      segments,
      avatarEndTimeSec,
      sequenceEndTime,
      intraSentenceRestDrops,
      interSentenceRestDrops
    } = buildCompiledKinematicSegments(entries, runs, schedParams, baseVideoDuration, opts.extendEndForLag);

    const playableEntries = playableIndices.map(idx => entries[idx]);
    let maxLagFound = 0;
    let maxSpeedFound = 1.0;
    let adjustedCount = 0;
    let minStrokeRetainedPct = 100.0;
    for (const pe of playableEntries) {
      if (pe.lagSec > maxLagFound) maxLagFound = pe.lagSec;
      if (pe.speed > maxSpeedFound) maxSpeedFound = pe.speed;
      if (pe.adjusted) adjustedCount++;
      if (typeof pe.strokeRetainedPct === 'number' && pe.strokeRetainedPct < minStrokeRetainedPct) {
        minStrokeRetainedPct = pe.strokeRetainedPct;
      }
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
        maxSpeedUsed: Number(Math.min(1.0, maxSpeedFound).toFixed(4)),
        strokeRetainedPct: Number(minStrokeRetainedPct.toFixed(2)),
        minStrokeRetainedPct: Number(minStrokeRetainedPct.toFixed(2)),
        allStrokes100PctRetained: Boolean(minStrokeRetainedPct >= 99.99)
      }
    };
    this.compiled = this.plan;

    return this.plan;
  }

  /**
   * Resuelve qué entrada de glosa debe mostrarse como activa (HUD / PiP badge / exportación)
   * en el instante `t`.
   */
  resolveActiveEntryAt(t, seg) {
    const allEntries = (this.plan && Array.isArray(this.plan.entries)) ? this.plan.entries : [];
    for (let i = 0; i < allEntries.length; i++) {
      const e = allEntries[i];
      if (!e.playable && t >= e.slotStart - 1e-4 && t <= e.slotEnd + 1e-4) {
        return e;
      }
    }

    if (!seg) return null;

    if (seg.type === 'stroke') {
      return seg.activeEntry || null;
    }

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
      const playSpan = Math.max(1e-6, entry.endSec - entry.startSec);
      const uStroke = Math.min(1.0, Math.max(0.0, (t - entry.startSec) / playSpan));
      const localClipSec = entry.strokeStart + uStroke * (entry.strokeEnd - entry.strokeStart);
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
        let qArm = interpolateSO3HermiteC1(q0, q1, fromVel[bName], toVel[bName], T, u);
        // Epéntesis de Arco Frontal C¹: cuando el brazo recorre > 14° entre dos señas (o baja del rostro
        // al abdomen / cruza el tórax), proyectar suavemente el arco medio hacia adelante (+Z) con campana
        // sin²(π·u) (derivada nula en u=0 y u=1) para garantizar despeje pectoral/abdominal en u=0.5.
        if (
          seg.subtype === 'coarticulation' &&
          u > 0.005 &&
          u < 0.995
        ) {
          const bell = Math.sin(Math.PI * u);
          const bellC1 = bell * bell;
          if (bName === 'leftUpperArm' || bName === 'rightUpperArm') {
            const travelDeg = quatAngleDeg(q0, q1);
            if (travelDeg > 14.0) {
              const dzSpan = Math.abs((q1[2] || 0) - (q0[2] || 0));
              const dySpan = Math.abs((q1[1] || 0) - (q0[1] || 0));
              const torsoCrossBoost = Math.min(0.06, 0.14 * (dzSpan + dySpan));
              const maxArcRad = Math.min(0.21, ((travelDeg - 14.0) / 82.0) * 0.16 + torsoCrossBoost);
              const sideSign = bName === 'leftUpperArm' ? -1.0 : 1.0;
              const qArc = quatExpRad([0, sideSign * maxArcRad * bellC1, 0]);
              qArm = quatNormalize(quatMultiply(qArc, qArm));
            }
          } else if (bName === 'leftLowerArm' || bName === 'rightLowerArm') {
            const upName = bName === 'leftLowerArm' ? 'leftUpperArm' : 'rightUpperArm';
            const upTravelDeg = quatAngleDeg(
              fromBones[upName] || CANONICAL_REST_BONES[upName],
              toBones[upName] || CANONICAL_REST_BONES[upName]
            );
            if (upTravelDeg > 26.0) {
              const sideSign = bName === 'leftLowerArm' ? -1.0 : 1.0;
              const loClearRad = Math.min(0.08, ((upTravelDeg - 26.0) / 95.0) * 0.08);
              const qLoArc = quatExpRad([0, sideSign * loClearRad * bellC1, 0]);
              qArm = quatNormalize(quatMultiply(qLoArc, qArm));
            }
          }
        }
        bones[bName] = qArm;
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
