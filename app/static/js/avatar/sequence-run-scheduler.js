/**
 * sequence-run-scheduler.js
 * Planificación temporal de corridas de glosas (backpropagation, tope 1.6x,
 * presupuesto de desfase lag <= 1.0 s y construcción de segmentos cinemáticos).
 */

import {
  LEFT_ARM_BONES,
  RIGHT_ARM_BONES,
  CANONICAL_REST_BONES,
  computeMaxArmAngleDeg,
  makeNeutralExpressions
} from './sequence-coarticulation-math.js';

/**
 * Extrae y ordena las entradas de glosas desde un proyecto de LSEC Studio o un arreglo.
 */
export function extractRawEntries(project) {
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
      && cleanUpper.split('-').filter(Boolean).every(p => {
        const tok = p.trim();
        return tok.length === 1 || tok === 'CH' || tok === 'LL' || tok === 'RR';
      });
    const gTypeUpper = String(item.gloss_type || '').toUpperCase();

    parsed.push({
      index: i,
      id: item.id || `g_${i}`,
      gloss,
      glossKey: cleanUpper,
      slotStart: st,
      slotEnd: et,
      slotDuration: Math.max(0.05, et - st),
      propositionId: item.proposition_id || item.origin_proposition_id || item.prop_id || item.segment_id || null,
      isFingerspelling: Boolean(
        item.is_fingerspelling ||
        item.isFingerspelling ||
        gTypeUpper.includes('DACTIL') ||
        gTypeUpper === 'FINGERSPELLING' ||
        item.validation?.is_fingerspelling ||
        item.dictionary_metadata?.status === 'DACTILOLOGIA' ||
        isSingleLetterHyphenated
      ),
      raw: item,
      rawItem: item
    });
  }

  parsed.sort((a, b) => (a.slotStart - b.slotStart) || (a.slotEnd - b.slotEnd) || (a.index - b.index));
  return parsed;
}

export function resolveClipFromMap(entry, clipMap) {
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
 * Agrupa glosas reproducibles en corridas contiguas (separadas únicamente cuando hay pausa > restGapThresholdSec).
 */
export function groupPlayableEntriesIntoRuns(entries, playableIndices, restGapThresholdSec) {
  const runs = [];
  if (playableIndices.length === 0) return runs;

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

    let effectiveSilenceGap = slotGap;
    if (sameProp && currIdx > prevIdx + 1) {
      effectiveSilenceGap = 0.0;
      for (let m = prevIdx; m < currIdx; m++) {
        const gBetween = entries[m + 1].slotStart - entries[m].slotEnd;
        if (gBetween > effectiveSilenceGap) effectiveSilenceGap = gBetween;
      }
    }

    if (effectiveSilenceGap > restGapThresholdSec) {
      runs.push(currentRun);
      currentRun = [currIdx];
    } else {
      currentRun.push(currIdx);
    }
  }
  if (currentRun.length > 0) runs.push(currentRun);
  return runs;
}

/**
 * Planifica cada corrida con duración de transición adaptativa, backpropagation de holgura,
 * tope de velocidad 1.6x y presupuesto estricto de desfase lag <= maxLagSec.
 */
export function schedulePlayableRunsWithLagBudget(entries, runs, params) {
  const {
    maxSpeed,
    minSpeed,
    maxLagSec,
    minTrans,
    maxTrans,
    angleRate,
    restTransSec
  } = params;

  let prevRunFinishSec = 0.0;
  for (let rIdx = 0; rIdx < runs.length; rIdx++) {
    const run = runs[rIdx];
    const m = run.length;
    const runItems = run.map(idx => entries[idx]);

    const transDur = new Float64Array(m);
    const effStrokeLen = new Float64Array(m);
    const effStrokeStart = new Float64Array(m);
    const effStrokeEnd = new Float64Array(m);
    const origStrokeStart = new Float64Array(m);
    const origStrokeEnd = new Float64Array(m);
    const origStrokeLen = new Float64Array(m);

    for (let j = 0; j < m; j++) {
      const it = runItems[j];
      const prep = it.prepared;
      let sStart = prep.strokeStart;
      let sEnd = prep.strokeEnd;
      let sLen = prep.strokeDuration;

      origStrokeStart[j] = sStart;
      origStrokeEnd[j] = sEnd;
      origStrokeLen[j] = sLen;
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
        if (maxSpeed > 1.0 && strokeLen > availForTarget) {
          const neededSpeed = strokeLen / availForTarget;
          speed = Math.max(1.0, Math.min(maxSpeed, neededSpeed));
        }
        speed = Math.min(Math.min(1.0, maxSpeed), Math.max(minSpeedFloor[j], speed));
        const playDur = strokeLen / speed;
        const endSec = startSec + playDur;

        startArr[j] = startSec;
        endArr[j] = endSec;
        speedArr[j] = speed;
        if (maxSpeed > 1.0 && (strokeLen / availForSlotEnd) > maxSpeed + 0.05) {
          adjArr[j] = 1;
        }
        prevStrokeEndSec = endSec;
      }
    };

    runForwardSchedule();

    const maxCompressIters = (maxSpeed > 1.0) ? Math.max(16, m * 2) : 0;
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

      let j0 = violIdx;
      while (j0 > 0 && startArr[j0] <= endArr[j0 - 1] + transDur[j0] + 1e-3) {
        j0--;
      }

      const strokeRangeEnd = (isStartViol && violIdx > j0) ? (violIdx - 1) : violIdx;
      let neededReduction = violExcess + 0.002;

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

      for (let k = j0 + 1; k <= violIdx && neededReduction > 1e-5; k++) {
        const reducibleTrans = Math.max(0, transDur[k] - minTrans);
        if (reducibleTrans > 0) {
          const cut = Math.min(reducibleTrans, neededReduction);
          transDur[k] -= cut;
          neededReduction -= cut;
        }
      }

      // Lag-induced stroke truncation eliminated: 100% stroke retention

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

    const scaleVelMap = (rawVel, spd) => {
      const out = {};
      const effScale = spd * 0.45;
      for (const [k, v] of Object.entries(rawVel || {})) {
        out[k] = [v[0] * effScale, v[1] * effScale, v[2] * effScale];
      }
      return out;
    };

    for (let j = 0; j < m; j++) {
      const it = runItems[j];
      const sStart = origStrokeStart[j];
      const sEnd = origStrokeEnd[j];
      const strokeLen = origStrokeLen[j];
      const origLen = origStrokeLen[j];
      const strokeRetainedPct = origLen > 0 ? Number(((strokeLen / origLen) * 100).toFixed(2)) : 100.0;
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
      const sweepRate = playDur > 1e-6 ? (sEnd - sStart) / playDur : speed;
      const exactSpeed = Math.min(1.0, Math.min(maxSpeed, speed));

      it.origStrokeDuration = origLen;
      it.strokeRetainedPct = strokeRetainedPct;
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
      it.startVel = scaleVelMap(rawStartVel, sweepRate);
      it.endVel = scaleVelMap(rawEndVel, sweepRate);
      it.runIndex = rIdx;
      it.indexInRun = j;
    }

    prevRunFinishSec = endArr[m - 1] + restTransSec;
  }
}

/**
 * Construye la lista continua y sin huecos de segmentos cinemáticos ('rest' | 'transition' | 'stroke' | 'hold').
 */
export function buildCompiledKinematicSegments(entries, runs, params, baseVideoDuration, extendEndForLag) {
  const { minTrans, maxTrans, restTransSec } = params;
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

    for (let j = 0; j < run.length; j++) {
      const currEntry = entries[run[j]];

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
  const sequenceEndTime = extendEndForLag !== false
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

  return {
    segments,
    avatarEndTimeSec,
    sequenceEndTime,
    intraSentenceRestDrops,
    interSentenceRestDrops
  };
}
