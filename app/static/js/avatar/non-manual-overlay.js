/**
 * non-manual-overlay.js
 * Capa de marcadores no manuales gramaticales (prosoponema) para la reproducción compilada
 * y la exportación MP4 del avatar LSEC.
 *
 * Base lingüística (DATASET/Lengua de Señas Ecuatoriana.docx y Manual Práctico para
 * Intérpretes en LSEC, CORDICOM-CONADIS-FENASEC, "Gramática Básica de la LSEC", pp. 53-54):
 *  - Oraciones negativas: sacudir la cabeza + fruncir las cejas.
 *  - Oraciones interrogativas (sí/no y parciales): levantar las cejas, cabeza ligeramente hacia
 *    adelante y a un costado, mirando directamente a la persona.
 *  - Preguntas retóricas: las cejas se levantan (en lugar de fruncirse).
 *  - Los rasgos no manuales son morfemas obligatorios que determinan la modalidad de la oración.
 *
 * Los spans provienen del motor gramatical del backend (`non_manual_spans`) y se vinculan a las
 * glosas mediante `gloss.non_manual_span_ids`; la ventana temporal se deriva del plan compilado
 * (no de los tiempos sintéticos de la tarjeta de UI), de modo que el marcador coincide con las
 * señas que gobierna.
 */

import { quatExpRad, quatMultiply, quatNormalize } from './sequence-coarticulation-math.js';

const DEG = Math.PI / 180;

const BROW_CHANNELS = Object.freeze([
  'browDownLeft', 'browDownRight', 'browInnerUp', 'browOuterUpLeft', 'browOuterUpRight'
]);
const BROW_CHANNEL_SET = new Set(BROW_CHANNELS);

const RAISED_BROWS = Object.freeze({
  browInnerUp: 0.80, browOuterUpLeft: 0.60, browOuterUpRight: 0.60, eyeWideLeft: 0.20, eyeWideRight: 0.20
});

/**
 * Perfiles articulatorios por tipo de span. `head` en grados; `shake` = sacudida lateral (negación).
 * `priority` resuelve conflictos entre cejas levantadas y fruncidas cuando los spans se solapan.
 */
export const NON_MANUAL_PROFILES = Object.freeze({
  negation: {
    priority: 4,
    expr: { browDownLeft: 0.60, browDownRight: 0.60, mouthFrownLeft: 0.25, mouthFrownRight: 0.25 },
    shake: { yawDeg: 11, hz: 2.4 }
  },
  question_yn: { priority: 4, expr: RAISED_BROWS, head: { pitchDeg: 5, rollDeg: 6 } },
  question_wh: { priority: 4, expr: RAISED_BROWS, head: { pitchDeg: 5, rollDeg: 6 } },
  rhetorical: {
    priority: 3,
    expr: { browInnerUp: 0.65, browOuterUpLeft: 0.50, browOuterUpRight: 0.50 },
    head: { rollDeg: 4 }
  },
  imperative: {
    priority: 3,
    expr: { browDownLeft: 0.25, browDownRight: 0.25 },
    nod: { pitchDeg: 4 }
  },
  conditional: { priority: 2, expr: { browInnerUp: 0.50, browOuterUpLeft: 0.35, browOuterUpRight: 0.35 }, head: { rollDeg: 5 } },
  topicalization: { priority: 2, expr: { browInnerUp: 0.45, browOuterUpLeft: 0.35, browOuterUpRight: 0.35 }, head: { rollDeg: 4 } },
  reflective: { priority: 2, expr: { browInnerUp: 0.35, browOuterUpLeft: 0.20, browOuterUpRight: 0.20 }, head: { rollDeg: 5 } },
  // El backend no emite la glosa PERO (el contraste se marca con el cuerpo): el desplazamiento corporal
  // (body_shift) es la señal principal; las cejas y la cabeza lo refuerzan.
  contrast: { priority: 1, expr: { browOuterUpLeft: 0.35, browOuterUpRight: 0.35 }, head: { rollDeg: 2 }, bodyShift: { yawDeg: 7, rollDeg: 4, headYawDeg: 6 } },
  emphasis: { priority: 2, expr: { browOuterUpLeft: 0.35, browOuterUpRight: 0.35, eyeWideLeft: 0.15, eyeWideRight: 0.15 }, nod: { pitchDeg: 3 } },
  superlative: { priority: 2, expr: { browOuterUpLeft: 0.35, browOuterUpRight: 0.35, eyeWideLeft: 0.15, eyeWideRight: 0.15 }, nod: { pitchDeg: 3 } }
});

/** Deduce el tipo de span a partir de `type`, del sufijo del id (`span_3_negation`) o de la etiqueta. */
export function resolveNonManualSpanType(span) {
  if (!span) return null;
  const direct = String(span.type || '').toLowerCase();
  if (NON_MANUAL_PROFILES[direct]) return direct;
  const idMatch = /^span_\d+_(.+)$/.exec(String(span.id || ''));
  if (idMatch && NON_MANUAL_PROFILES[idMatch[1]]) return idMatch[1];
  const label = String(span.expression || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const byLabel = {
    negacion: 'negation', contraste: 'contrast', reflexiva: 'reflective', imperativo: 'imperative',
    enfasis: 'emphasis', superlativo: 'superlative', retorica: 'rhetorical', condicional: 'conditional',
    topicalizacion: 'topicalization', 'pregunta si/no': 'question_yn', 'pregunta wh': 'question_wh'
  };
  return byLabel[label] || null;
}

/**
 * Construye los marcadores no manuales con ventanas temporales reales a partir del plan compilado.
 * @param {Array} entries - entradas compiladas (con `startSec`/`endSec` si son reproducibles)
 * @param {Array} spans - `project.non_manual_spans`
 * @returns {Array<{id,type,startSec,endSec,intensity,profile}>}
 */
export function buildNonManualMarkers(entries, spans) {
  if (!Array.isArray(entries) || !Array.isArray(spans) || spans.length === 0) return [];
  const spanById = new Map();
  for (const s of spans) {
    if (s && s.id) spanById.set(String(s.id), s);
  }

  const windows = new Map();
  for (const e of entries) {
    const ids = (e && e.raw && Array.isArray(e.raw.non_manual_span_ids)) ? e.raw.non_manual_span_ids : [];
    if (ids.length === 0) continue;
    const st = Number.isFinite(e.startSec) ? e.startSec : e.slotStart;
    const en = Number.isFinite(e.endSec) ? e.endSec : e.slotEnd;
    if (!Number.isFinite(st) || !Number.isFinite(en)) continue;
    for (const id of ids) {
      const key = String(id);
      if (!spanById.has(key)) continue;
      const w = windows.get(key);
      if (w) {
        w.startSec = Math.min(w.startSec, st);
        w.endSec = Math.max(w.endSec, en);
      } else {
        windows.set(key, { startSec: st, endSec: en });
      }
    }
  }

  const markers = [];
  for (const [id, w] of windows.entries()) {
    const span = spanById.get(id);
    const type = resolveNonManualSpanType(span);
    if (!type) continue;
    markers.push({
      id,
      type,
      startSec: Math.max(0, w.startSec - 0.12),
      endSec: w.endSec + 0.08,
      intensity: Math.max(0.2, Math.min(1.4, Number(span.intensity) || 1.0)),
      // Convención: body_shift left/right desde la perspectiva del avatar (su izquierda = +X del mundo VRM).
      bodySide: span.body_shift === 'left' ? 1 : (span.body_shift === 'right' ? -1 : 0),
      profile: NON_MANUAL_PROFILES[type]
    });
  }
  markers.sort((a, b) => a.startSec - b.startSec);
  return markers;
}

function envelope(t, m) {
  const ramp = Math.min(0.18, 0.4 * (m.endSec - m.startSec));
  const up = Math.min(1, Math.max(0, (t - m.startSec) / Math.max(1e-3, ramp)));
  const down = Math.min(1, Math.max(0, (m.endSec - t) / Math.max(1e-3, ramp)));
  const x = Math.min(up, down);
  return x * x * (3 - 2 * x);
}

/**
 * Evalúa, de forma pura y determinista, el aporte no manual en el instante `t`.
 * @returns {{expressions:Object, headRotVec:number[]}|null} rotación de cabeza como vector de rotación (rad)
 */
export function sampleNonManualAt(markers, t) {
  if (!Array.isArray(markers) || markers.length === 0) return null;
  const active = [];
  for (const m of markers) {
    if (m.startSec > t) break;
    if (t <= m.endSec) active.push(m);
  }
  if (active.length === 0) return null;

  // Las cejas las gobierna únicamente el marcador activo de mayor prioridad (evita cejas
  // simultáneamente fruncidas y levantadas cuando un span de negación cae dentro de uno reflexivo).
  let dominant = active[0];
  for (const m of active) {
    if (m.profile.priority > dominant.profile.priority) dominant = m;
  }

  const expressions = {};
  let pitch = 0;
  let yaw = 0;
  let roll = 0;
  let bodyYaw = 0;
  let bodyRoll = 0;
  for (const m of active) {
    const env = envelope(t, m) * m.intensity;
    if (env <= 1e-4) continue;
    const p = m.profile;
    for (const [name, base] of Object.entries(p.expr || {})) {
      if (BROW_CHANNEL_SET.has(name) && m !== dominant) continue;
      expressions[name] = Math.max(expressions[name] || 0, Math.min(1, base * env));
    }
    if (p.head) {
      pitch += (p.head.pitchDeg || 0) * DEG * env;
      roll += (p.head.rollDeg || 0) * DEG * env;
    }
    if (p.nod) {
      pitch += p.nod.pitchDeg * DEG * env * Math.sin(Math.PI * Math.min(1, (t - m.startSec) / Math.max(0.3, m.endSec - m.startSec)));
    }
    if (p.bodyShift && m.bodySide) {
      bodyYaw += m.bodySide * p.bodyShift.yawDeg * DEG * env;
      bodyRoll += -m.bodySide * p.bodyShift.rollDeg * DEG * env;
      yaw += m.bodySide * p.bodyShift.headYawDeg * DEG * env;
    }
    if (p.shake) {
      yaw += p.shake.yawDeg * DEG * env * Math.sin(2 * Math.PI * p.shake.hz * (t - m.startSec));
    }
  }
  return { expressions, headRotVec: [pitch, yaw, roll], bodyRotVec: [0, bodyYaw, bodyRoll] };
}

/**
 * Superpone el marcador no manual sobre un resultado de `sample()` (muta `bones` y `expressions`).
 * La rotación de cabeza se reparte 65 % cabeza / 35 % cuello; el desplazamiento corporal, 60 % pecho alto / 40 % pecho.
 */
export function applyNonManualOverlay(result, markers, t) {
  const nm = sampleNonManualAt(markers, t);
  if (!nm || !result) return result;
  const exprOut = { ...(result.expressions || {}) };
  for (const [name, w] of Object.entries(nm.expressions)) {
    exprOut[name] = Math.max(exprOut[name] || 0, w);
  }
  result.expressions = exprOut;

  const [px, py, pz] = nm.headRotVec;
  if (Math.abs(px) + Math.abs(py) + Math.abs(pz) > 1e-6 && result.bones) {
    const bones = { ...result.bones };
    if (bones.head) bones.head = quatNormalize(quatMultiply(bones.head, quatExpRad([px * 0.65, py * 0.65, pz * 0.65])));
    if (bones.neck) bones.neck = quatNormalize(quatMultiply(bones.neck, quatExpRad([px * 0.35, py * 0.35, pz * 0.35])));
    result.bones = bones;
  }
  const [bx, by, bz] = nm.bodyRotVec;
  if (Math.abs(by) + Math.abs(bz) > 1e-6 && result.bones) {
    const bones = { ...result.bones };
    if (bones.upperChest) bones.upperChest = quatNormalize(quatMultiply(bones.upperChest, quatExpRad([bx * 0.6, by * 0.6, bz * 0.6])));
    if (bones.chest) bones.chest = quatNormalize(quatMultiply(bones.chest, quatExpRad([bx * 0.4, by * 0.4, bz * 0.4])));
    result.bones = bones;
  }
  result.nonManual = nm.expressions;
  return result;
}
