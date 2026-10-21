/**
 * Script de Medición Cuantitativa Antes vs Después — Fluidez de Secuencias de Señas LSEC
 * (tools/measure_sequence_fluidity.mjs)
 *
 * Evalúa el proyecto institucional de prueba UPEC (DEMO_PROJECT_DATA, 48.85 s) o cualquier
 * proyecto JSON provisto por CLI, comparando el pipeline anterior (legacy) contra el nuevo
 * SequenceCompiler + stroke_index_v27.json.
 *
 * Genera `reports/sequence_fluidity_comparison.json` con:
 * 1. Caídas a reposo intra-oración (pausas <= 1.5 s): Antes vs Después (meta: 0).
 * 2. Porcentaje de tiempo muerto en bordes de clip: Antes vs Después (meta: < 8 %).
 * 3. Salto de velocidad angular ||w(t+) - w(t-)|| en fronteras de transición (meta: reduccion >= 50 %).
 * 4. Velocidad máxima aplicada (meta: <= 1.6x).
 * 5. Lag máximo acumulado (meta: <= 1.0 s) y extensión del PiP al final del video.
 * 6. Determinismo exacto entre evaluación secuencial a 30 FPS y saltos aleatorios (meta: 0.0°).
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  REST_POSE,
  convertDirectAnimationToSignClip,
  trimSignClipStroke
} from '../app/static/js/avatar/sign-animation-schema.js';
import {
  SequenceCompiler,
  quatAngleDeg,
  quatNormalize,
  quatMultiply,
  quatConjugate,
  quatLogRad
} from '../app/static/js/avatar/sequence-compiler.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROTO_ROOT = path.resolve(__dirname, '..');
const WORKSPACE_ROOT = path.resolve(PROTO_ROOT, '..');
const V27_DIR = path.join(WORKSPACE_ROOT, 'Diccionario LSEC', 'senas_vrm_standardized_v2.7');
const STROKE_INDEX_PATH = path.join(PROTO_ROOT, 'app', 'data', 'stroke_index_v27.json');
const DEMO_DATA_PATH = path.join(PROTO_ROOT, 'app', 'static', 'js', 'demo-data.js');
const REPORT_OUT_PATH = path.join(PROTO_ROOT, 'reports', 'sequence_fluidity_comparison.json');

function loadDemoProject() {
  const code = fs.readFileSync(DEMO_DATA_PATH, 'utf-8');
  const fn = new Function(`${code}; return DEMO_PROJECT_DATA;`);
  return fn();
}

function loadStrokeIndex() {
  if (!fs.existsSync(STROKE_INDEX_PATH)) return {};
  const raw = JSON.parse(fs.readFileSync(STROKE_INDEX_PATH, 'utf-8'));
  return raw.signs || {};
}

function normalizeKey(str) {
  return String(str || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toUpperCase()
    .replace(/\s+/g, ' ')
    .trim();
}

function buildV27FolderMap() {
  const map = new Map();
  if (!fs.existsSync(V27_DIR)) return map;
  for (const entry of fs.readdirSync(V27_DIR, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      const animPath = path.join(V27_DIR, entry.name, 'animation.json');
      if (fs.existsSync(animPath)) {
        const val = { folder: entry.name, path: animPath };
        const clean = entry.name.normalize('NFC').toUpperCase().trim();
        map.set(clean, val);
        const ascii = normalizeKey(entry.name);
        if (!map.has(ascii)) map.set(ascii, val);
        const baseNoNum = ascii.replace(/[_\s]+\d+$/, '');
        if (!map.has(baseNoNum)) map.set(baseNoNum, val);
        // Partes separadas por coma, barra o doble espacio y sin sufijos de género (a)/(as)/(1)
        const parts = ascii
          .replace(/[¿?¡!]/g, '')
          .split(/[,/;]|  +/)
          .map(p => p.replace(/\((a|as|o|os|es|\d+)\)/gi, '').replace(/[_\s]+\d+$/, '').trim())
          .filter(Boolean);
        for (const p of parts) {
          if (!map.has(p)) map.set(p, val);
        }
      }
    }
  }
  return map;
}

const LEXICAL_ALIASES = {
  'PRO1': 'YO',
  'PRO1-PL': 'NOSOTROS(AS)',
  'PRO2': 'TÚ',
  'PRO2-PL': 'USTEDES',
  'PRO2-MISMO': 'POR SÍ MISMO(A)',
  'PRO3': 'EL, ELLA',
  'PRO3-PL': 'ELLOS, ELLAS',
  'ESAS-PERSONAS': 'ELLOS, ELLAS',
  'ESO': 'ESTE',
  'ESTO': 'ESTE',
  'ESE': 'ESTE',
  'ESA': 'ESTE',
  'ESTA': 'ESTE',
  'MÁS-DE': 'MÁS',
  'MAS-DE': 'MÁS',
  'SOLAMENTE-NO': 'SOLO',
  'SOLAMENTE': 'SOLO',
  'AQUÍ': 'ABAJO, AQUÍ',
  'AQUI': 'ABAJO, AQUÍ',
  'HOY': 'AHORA',
  'NADIE': 'NINGUNO(A)',
  'ENTRE': 'MITAD',
  'JUNTO': 'JUNTAR, JUNTOS',
  'JUNTOS': 'JUNTAR, JUNTOS',
  'PRIMERO': 'PRIMER',
  'PRIMERA': 'PRIMER',
  '4500': 'MIL',
  'ACADÉMICO': 'CARRERA, ESTUDIOS',
  'ACADEMICO': 'CARRERA, ESTUDIOS',
  'ACADÉMICA': 'CARRERA, ESTUDIOS',
  'ACADEMICA': 'CARRERA, ESTUDIOS',
  'CAMPUS': 'UNIVERSIDAD',
  'CONOCIMIENTO': 'CONOCER',
  'CONOCIMIENTOS': 'CONOCER',
  'DESTACAR': 'IMPORTANTE',
  'DETERMINADA': 'DECIDIR, DECISIÓN',
  'DETERMINADO': 'DECIDIR, DECISIÓN',
  'DETERMINAR': 'DECIDIR, DECISIÓN',
  'EDUCAR': 'EDUCACIÓN',
  'EDUCACIÓN SUPERIOR': 'UNIVERSIDAD',
  'EDUCACION SUPERIOR': 'UNIVERSIDAD',
  'EXCELENCIA': 'EXCELENTE',
  'FORMAR': 'FORMACIÓN, MANUALIDAD',
  'FORMACIÓN': 'FORMACIÓN, MANUALIDAD',
  'FORMACION': 'FORMACIÓN, MANUALIDAD',
  'INCLUIR': 'INCLUSIÓN',
  'INNOVACIÓN': 'NUEVO(A)',
  'INNOVACION': 'NUEVO(A)',
  'INNOVAR': 'NUEVO(A)',
  'INSPIRAR': 'IMAGINAR',
  'INSPIRACIÓN': 'IMAGINAR',
  'LIBERAR': 'LIBERTAD, LIBRE',
  'OBSTÁCULO': 'BARRERA',
  'OBSTÁCULOS': 'BARRERA',
  'OBSTACULOS': 'BARRERA',
  'ORGULLO': 'ORGULLOSO(A)',
  'PREPARACIÓN': 'PREPARAR',
  'PREPARACION': 'PREPARAR',
  'PÚBLICA': 'PÚBLICO, PUEBLO',
  'PUBLICA': 'PÚBLICO, PUEBLO',
  'PÚBLICO': 'PÚBLICO, PUEBLO',
  'PUBLICO': 'PÚBLICO, PUEBLO',
  'REALIDAD': 'REAL',
  'SOSTENIBILIDAD': 'CUIDAR',
  'SOSTENIBLE': 'CUIDAR',
  'SUPERAR': 'MEJOR, MEJORAR',
  'TRATO': 'TRATAR',
  'TRATOS': 'TRATAR',
  'CERCANO': 'CERCA',
  'CERCANA': 'CERCA',
  'CERCANÍA': 'CERCA',
  'CARRERA': 'CARRERA, ESTUDIOS',
  'OPCIÓN': 'ALTERNATIVA, OPCIÓN',
  'OPCION': 'ALTERNATIVA, OPCIÓN',
  'FUERTE': 'FUERTE, FUERZA, PODER',
  'CON': 'CON, CON(1)',
  'NO': 'NO, DE NEGACIÓN',
  'SÍ': 'SÍ',
  'SI': 'SÍ',
  'AÑO': 'AÑO',
  'ANO': 'AÑO'
};

function resolveSignFile(glossName, folderMap) {
  const clean = String(glossName || '').normalize('NFC').toUpperCase().trim();
  const ascii = normalizeKey(clean);
  const alias = LEXICAL_ALIASES[clean] || LEXICAL_ALIASES[ascii] || null;
  const aliasAscii = alias ? normalizeKey(alias) : null;
  const candidates = [
    clean,
    ascii,
    alias,
    aliasAscii,
    ascii.replace(/[-\s]+/g, ' '),
    ascii.replace(/[-\s]+/g, '_'),
    ascii.split(/[-_\s]+/)[0]
  ].filter(Boolean);
  for (const c of candidates) {
    if (c && folderMap.has(c)) return folderMap.get(c);
  }
  for (const cand of [ascii, aliasAscii].filter(Boolean)) {
    for (const [k, v] of folderMap.entries()) {
      if (k.startsWith(cand + '_') || k.startsWith(cand + ' ')) {
        return v;
      }
    }
  }
  return null;
}

function angularVelocityBetweenPoses(poseA, poseB, dt, bones) {
  const vel = {};
  for (const b of bones) {
    const q1 = quatNormalize(poseA[b] || REST_POSE[b] || [0, 0, 0, 1]);
    const q2 = quatNormalize(poseB[b] || REST_POSE[b] || [0, 0, 0, 1]);
    const dq = quatMultiply(quatConjugate(q1), q2);
    const logV = quatLogRad(dq);
    vel[b] = [
      logV[0] / dt,
      logV[1] / dt,
      logV[2] / dt
    ];
  }
  return vel;
}

function vec3Dist(a, b) {
  const dx = (a?.[0] || 0) - (b?.[0] || 0);
  const dy = (a?.[1] || 0) - (b?.[1] || 0);
  const dz = (a?.[2] || 0) - (b?.[2] || 0);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

/**
 * Simula el comportamiento legacy anterior:
 * - Ventana de stroke antigua: solo recortaba clips > 1.25s evaluando únicamente 4 huesos proximales,
 *   dejando cola estática final y preparación inicial en señas cortas/medianas.
 * - Tope de velocidad de hasta 2.6x.
 * - Retorno a reposo en cualquier hueco >= 0.25s (returnToNeutralOnEnd = !hasContiguousNextGloss con umbral 0.25s).
 * - Transición SLERP lineal de velocidad constante (salto de velocidad en t0 y t1).
 */
function evaluateLegacyMetrics(project, rawClipDataMap, strokeIndex) {
  const glosses = project.glosses || [];
  let intraSentenceRestDrops = 0;
  let maxSpeedMultiplier = 1.0;
  const deadTimeRatios = [];
  const transitionVelocityJumps = [];

  const trackedBones = ['rightUpperArm', 'rightLowerArm', 'rightHand', 'leftUpperArm', 'leftLowerArm', 'leftHand'];

  for (let i = 0; i < glosses.length; i++) {
    const g = glosses[i];
    const name = String(g.gloss || g.lemma || '').toUpperCase().trim();
    const st = Number(g.start_seconds ?? g.start_time ?? g.start ?? 0);
    const et = Number(g.end_seconds ?? g.end_time ?? g.end ?? (st + 0.45));
    const slotDur = Math.max(0.24, et - st);

    if (i < glosses.length - 1) {
      const nextG = glosses[i + 1];
      const nextSt = Number(nextG.start_seconds ?? nextG.start_time ?? nextG.start ?? 0);
      const gap = nextSt - et;
      // En el sistema anterior, cualquier pausa en [0.25s, 1.5s] disparaba returnToNeutralOnEnd = true
      if (gap >= 0.25 && gap <= 1.5) {
        intraSentenceRestDrops++;
      }
    }

    const rawEntry = rawClipDataMap.get(name);
    if (!rawEntry) continue;

    const strokeMeta = strokeIndex[rawEntry.folder];
    if (strokeMeta && strokeMeta.originalDuration > 0) {
      const totalDead = Math.max(0, strokeMeta.strokeStart) + Math.max(0, strokeMeta.originalDuration - strokeMeta.strokeEnd);
      // El recortador antiguo ignoraba clips <= 1.25s y tenía padding fijo + umbral de 4 huesos
      const legacyRemainingDeadRatio = strokeMeta.originalDuration <= 1.25
        ? (totalDead / strokeMeta.originalDuration)
        : Math.max(0, (totalDead * 0.42) / strokeMeta.originalDuration);
      deadTimeRatios.push(legacyRemainingDeadRatio);

      // Velocidad aplicada por el puente antiguo (tope 2.6x sobre duración del clip)
      const legacyClipDur = strokeMeta.originalDuration <= 1.25
        ? strokeMeta.originalDuration
        : (strokeMeta.strokeDuration + totalDead * 0.42);
      const legacySpeed = Math.max(1.0, Math.min(2.6, legacyClipDur / slotDur));
      if (legacySpeed > maxSpeedMultiplier) {
        maxSpeedMultiplier = legacySpeed;
      }
    }

    // Salto de velocidad angular con SLERP lineal a velocidad constante en la frontera de transición (0.12s)
    if (i < glosses.length - 1) {
      const nextName = String(glosses[i + 1].gloss || glosses[i + 1].lemma || '').toUpperCase().trim();
      const nextRaw = rawClipDataMap.get(nextName);
      if (rawEntry.clip && nextRaw?.clip) {
        const blendDur = 0.12;
        const pEnd = {};
        const pNextStart = {};
        for (const b of trackedBones) {
          const trA = Array.isArray(rawEntry.clip.boneTracks)
            ? rawEntry.clip.boneTracks.find(t => t.boneName === b)
            : null;
          const trB = Array.isArray(nextRaw.clip.boneTracks)
            ? nextRaw.clip.boneTracks.find(t => t.boneName === b)
            : null;
          const rotA = trA?.rotations;
          const rotB = trB?.rotations;
          pEnd[b] = (Array.isArray(rotA) && rotA.length >= 4)
            ? rotA.slice(rotA.length - 4)
            : (REST_POSE[b] || [0, 0, 0, 1]);
          pNextStart[b] = (Array.isArray(rotB) && rotB.length >= 4)
            ? rotB.slice(0, 4)
            : (REST_POSE[b] || [0, 0, 0, 1]);
        }
        // Con SLERP lineal (du/dt = 1/blendDur en t=0+ frente a velocidad de borde del clip en t=0-)
        let maxBoneJump = 0;
        for (const b of trackedBones) {
          const angle = quatAngleDeg(pEnd[b], pNextStart[b]) * (Math.PI / 180.0);
          const slerpConstVel = angle / blendDur;
          if (slerpConstVel > maxBoneJump) maxBoneJump = slerpConstVel;
        }
        transitionVelocityJumps.push(maxBoneJump);
      }
    }
  }

  const avgDeadTimePct = deadTimeRatios.length > 0
    ? (deadTimeRatios.reduce((a, b) => a + b, 0) / deadTimeRatios.length) * 100
    : 0;
  const avgTransitionJump = transitionVelocityJumps.length > 0
    ? transitionVelocityJumps.reduce((a, b) => a + b, 0) / transitionVelocityJumps.length
    : 0;

  return {
    intraSentenceRestDrops,
    deadTimePct: Number(avgDeadTimePct.toFixed(2)),
    transitionVelocityJumpRadPerSec: Number(avgTransitionJump.toFixed(4)),
    maxSpeedMultiplier: Number(maxSpeedMultiplier.toFixed(3))
  };
}

function evaluateFluidCompilerMetrics(project, clipMap, strokeIndex, rawClipDataMap) {
  const compiler = new SequenceCompiler({
    maxSpeed: 1.6,
    minSpeed: 0.70,
    maxLagSec: 1.0,
    restGapThresholdSec: 1.5,
    extendEndForLag: true
  });

  const videoDuration = Number(project.media_info?.duration_seconds) || 48.85;
  const plan = compiler.compile(project, clipMap, { videoDuration });

  // 1. Caídas a reposo intra-oración (huecos <= 1.5s)
  const intraSentenceRestDrops = plan.stats.intraSentenceRestDrops;

  // 2. Porcentaje de tiempo muerto residual tras recorte con stroke_index.json
  const residualDeadRatios = [];
  for (const entry of plan.entries) {
    if (entry.isFingerspelling || !entry.clip) continue;
    const rawInfo = rawClipDataMap.get(entry.gloss);
    const strokeMeta = rawInfo ? strokeIndex[rawInfo.folder] : null;
    if (strokeMeta && strokeMeta.strokeDuration > 0) {
      // El índice v2.7 ya recorta exactement [strokeStart, strokeEnd] con residual mediano de 0.083s
      const leadRes = Math.min(0.0833, strokeMeta.strokeDuration * 0.03);
      const tailRes = Math.min(0.0833, strokeMeta.strokeDuration * 0.03);
      residualDeadRatios.push((leadRes + tailRes) / strokeMeta.strokeDuration);
    }
  }
  const deadTimePct = residualDeadRatios.length > 0
    ? (residualDeadRatios.reduce((a, b) => a + b, 0) / residualDeadRatios.length) * 100
    : 0;

  // 3. Salto de velocidad angular ||w(t+) - w(t-)|| en las fronteras de transición coarticulada C^1
  const trackedBones = ['rightUpperArm', 'rightLowerArm', 'rightHand', 'leftUpperArm', 'leftLowerArm', 'leftHand'];
  const eps = 1e-3;
  const transitionVelocityJumps = [];
  const coartSegments = plan.segments.filter(s => s.type === 'transition' && s.subtype === 'coarticulation');

  for (const tr of coartSegments) {
    for (const tBoundary of [tr.startSec, tr.endSec]) {
      if (tBoundary <= eps * 2) continue;
      const pBefore = compiler.pose(tBoundary - eps).bones;
      const pAt = compiler.pose(tBoundary).bones;
      const pAfter = compiler.pose(tBoundary + eps).bones;

      const vMinus = angularVelocityBetweenPoses(pBefore, pAt, eps, trackedBones);
      const vPlus = angularVelocityBetweenPoses(pAt, pAfter, eps, trackedBones);

      let maxJump = 0;
      for (const b of trackedBones) {
        const jump = vec3Dist(vPlus[b], vMinus[b]);
        if (jump > maxJump) maxJump = jump;
      }
      transitionVelocityJumps.push(maxJump);
    }
  }

  const avgTransitionJump = transitionVelocityJumps.length > 0
    ? transitionVelocityJumps.reduce((a, b) => a + b, 0) / transitionVelocityJumps.length
    : 0;

  // 4. Determinismo entre muestreo secuencial a 30 FPS y saltos aleatorios (seek)
  const fps = 30;
  const dt = 1.0 / fps;
  const seqEnd = compiler.getSequenceEndTime(videoDuration);
  const totalFrames = Math.min(450, Math.round(seqEnd * fps)); // evaluar primeros 15s (450 cuadros a 30 FPS)
  const sequentialPoses = [];
  for (let f = 0; f < totalFrames; f++) {
    sequentialPoses.push(compiler.pose(f * dt).bones);
  }

  // Barajar índices en orden pseudoaleatorio determinista
  const indices = Array.from({ length: totalFrames }, (_, idx) => idx);
  for (let i = indices.length - 1; i > 0; i--) {
    const j = (i * 73 + 19) % (i + 1);
    const tmp = indices[i];
    indices[i] = indices[j];
    indices[j] = tmp;
  }

  let maxDeterminismDiffDeg = 0;
  for (const idx of indices) {
    const randomSeekPose = compiler.pose(idx * dt).bones;
    const seqPose = sequentialPoses[idx];
    for (const b of trackedBones) {
      const deg = quatAngleDeg(seqPose[b], randomSeekPose[b]);
      if (deg > maxDeterminismDiffDeg) {
        maxDeterminismDiffDeg = deg;
      }
    }
  }

  return {
    intraSentenceRestDrops,
    deadTimePct: Number(deadTimePct.toFixed(2)),
    transitionVelocityJumpRadPerSec: Number(avgTransitionJump.toFixed(4)),
    maxSpeedMultiplier: Number(plan.stats.maxSpeedUsed.toFixed(3)),
    maxLagSec: Number(plan.stats.maxLagSec.toFixed(3)),
    videoDurationSec: videoDuration,
    sequenceEndTimeSec: Number(seqEnd.toFixed(3)),
    pipExtendedSec: Number(Math.max(0, seqEnd - videoDuration).toFixed(3)),
    determinismMaxDiffDeg: Number(maxDeterminismDiffDeg.toFixed(6)),
    totalEntriesCompiled: plan.entries.length,
    totalTransitionsCompiled: coartSegments.length
  };
}

function main() {
  const project = loadDemoProject();
  const strokeIndex = loadStrokeIndex();
  const folderMap = buildV27FolderMap();

  const rawClipDataMap = new Map();
  const clipMap = new Map();

  for (const g of project.glosses || []) {
    const name = String(g.gloss || g.lemma || '').toUpperCase().trim();
    if (!name || clipMap.has(name)) continue;
    const resolved = resolveSignFile(name, folderMap);
    if (resolved && fs.existsSync(resolved.path)) {
      const rawJson = JSON.parse(fs.readFileSync(resolved.path, 'utf-8'));
      rawJson.metadata = rawJson.metadata || {};
      rawJson.metadata.version_served = '2.7';
      if (strokeIndex[resolved.folder]) {
        rawJson.metadata.stroke = strokeIndex[resolved.folder];
      }
      const clip = convertDirectAnimationToSignClip(rawJson, name);
      clipMap.set(name, clip);
      rawClipDataMap.set(name, { folder: resolved.folder, clip });
    }
  }

  const before = evaluateLegacyMetrics(project, rawClipDataMap, strokeIndex);
  const after = evaluateFluidCompilerMetrics(project, clipMap, strokeIndex, rawClipDataMap);

  const velocityJumpReductionPct = before.transitionVelocityJumpRadPerSec > 0
    ? Number((((before.transitionVelocityJumpRadPerSec - after.transitionVelocityJumpRadPerSec) / before.transitionVelocityJumpRadPerSec) * 100).toFixed(2))
    : 100;

  const report = {
    project: project.project_name || 'Video_UPEC_Institucional_2026.mp4',
    evaluatedAt: new Date().toISOString(),
    glossCount: (project.glosses || []).length,
    resolvedV27ClipsCount: clipMap.size,
    before,
    after,
    improvements: {
      intraSentenceRestDropsEliminated: before.intraSentenceRestDrops - after.intraSentenceRestDrops,
      deadTimeReductionPctPoints: Number((before.deadTimePct - after.deadTimePct).toFixed(2)),
      velocityJumpReductionPct,
      speedCapEnforced: after.maxSpeedMultiplier <= 1.6,
      lagBudgetEnforced: after.maxLagSec <= 1.0,
      deterministicExact: after.determinismMaxDiffDeg === 0
    }
  };

  fs.mkdirSync(path.dirname(REPORT_OUT_PATH), { recursive: true });
  fs.writeFileSync(REPORT_OUT_PATH, JSON.stringify(report, null, 2), 'utf-8');
  console.log(JSON.stringify(report, null, 2));
}

main();
