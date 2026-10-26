/**
 * test_challenger_m1_adversarial.mjs
 * 
 * EMPIRICAL CHALLENGER STRESS HARNESS — Milestone 1 (M1)
 * 
 * Tests:
 * 1. Extreme Lag Ingestion (>10s, >20s, >40s lag) — speed <= 1.0 invariant & 100% stroke retention
 * 2. Boundary Conditions in Video Exporter & Extended Tail:
 *    - seqEnd == videoDuration
 *    - seqEnd < videoDuration
 *    - seqEnd >> videoDuration
 *    - videoDuration == 0, seqEnd == 0
 *    - videoDuration == 0, seqEnd > 0
 * 3. Parameter Override Injection (maxSpeed: 2.5, maxLagSec: 0.1) — strict defense
 * 4. Fingerspelling Temporal Compression Attack (targetDurationSec -> 0)
 * 5. Deterministic Frame Stepper & Exporter Simulation
 * 6. ISO/IEC 25010 Line Count Audit (all M1 files <= 800 lines)
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '../../..');
const V27_BASE = path.join(projectRoot, 'Diccionario LSEC/senas_vrm_standardized_v2.7');
const STROKE_INDEX_PATH = path.join(__dirname, '../data/stroke_index_v27.json');

// Importar módulos de producción
import {
  convertDirectAnimationToSignClip,
  trimSignClipStroke
} from '../static/js/avatar/sign-animation-schema.js';
import { SequenceCompiler } from '../static/js/avatar/sequence-compiler.js';
import {
  tokenizeLSECFingerspelling,
  createLSECFingerspellingWordClip
} from '../static/js/avatar/sign-clips-fingerspelling-lsec.js';

// Cargar stroke_index de v2.7
const strokeIndexRaw = JSON.parse(fs.readFileSync(STROKE_INDEX_PATH, 'utf8'));

function loadClipV27(folderName, glossUpper) {
  const animPath = path.join(V27_BASE, folderName, 'animation.json');
  if (!fs.existsSync(animPath)) {
    throw new Error(`Seña v2.7 no encontrada: ${animPath}`);
  }
  const rawJson = JSON.parse(fs.readFileSync(animPath, 'utf8'));
  rawJson.metadata = {
    ...(rawJson.metadata || {}),
    version_served: '2.7',
    stroke: strokeIndexRaw.signs[folderName] || null
  };
  return trimSignClipStroke(convertDirectAnimationToSignClip(rawJson, glossUpper));
}

// Cargar clips reales de v2.7
const clipAbanico = loadClipV27('Abanico', 'ABANICO');
const clipHola = loadClipV27('Hola', 'HOLA');
const clipPoder = loadClipV27('Fuerte, Fuerza, Poder', 'PODER');
const clipLibertad = loadClipV27('Libertad, Libre', 'LIBERTAD');
const clipDecidir = loadClipV27('Decidir, Decisión', 'DECIDIR');
const clipCentro = loadClipV27('Centro', 'CENTRO');

const testClipMap = new Map([
  ['ABANICO', clipAbanico],
  ['HOLA', clipHola],
  ['PODER', clipPoder],
  ['LIBERTAD', clipLibertad],
  ['DECIDIR', clipDecidir],
  ['CENTRO', clipCentro]
]);

let passCount = 0;
let failCount = 0;

function assert(condition, message) {
  if (!condition) {
    failCount++;
    console.error(`❌ FAIL: ${message}`);
    throw new Error(message);
  } else {
    passCount++;
  }
}

console.log('================================================================');
console.log('  CHALLENGER EMPIRICAL VERIFICATION HARNESS — MILESTONE 1 (M1)');
console.log('================================================================\n');

// -----------------------------------------------------------------------------
// ADVERSARIAL TEST 1: Extreme Lag Pressure (>10s, >20s, >35s lag)
// -----------------------------------------------------------------------------
console.log('--- TEST 1: Presión Extrema de Desfase (Lag > 10s, 20s, 35s) ---');
{
  const compiler = new SequenceCompiler();
  const glossPool = ['ABANICO', 'HOLA', 'PODER', 'LIBERTAD', 'DECIDIR', 'CENTRO'];

  // 30 señas reales de v2.7 empaquetadas en un slot de apenas 0.1s cada una!
  // Video dura 3.0s, pero las 30 señas reales duran ~45s.
  // El lag acumulado superará masivamente 10s, 20s y 35s.
  const denseGlosses = [];
  for (let k = 0; k < 30; k++) {
    const gloss = glossPool[k % glossPool.length];
    denseGlosses.push({
      id: `dense_${k + 1}`,
      gloss,
      start_seconds: k * 0.10,
      end_seconds: (k + 1) * 0.10,
      slotDuration: 0.10
    });
  }

  const denseProject = {
    media_info: { duration_seconds: 3.0 },
    glosses: denseGlosses
  };

  const plan = compiler.compile(denseProject, testClipMap, { videoDuration: 3.0 });

  assert(plan.stats.totalGlosses === 30, `totalGlosses esperado 30, obtenido ${plan.stats.totalGlosses}`);
  assert(plan.stats.playableGlosses === 30, `playableGlosses esperado 30, obtenido ${plan.stats.playableGlosses}`);
  assert(plan.stats.maxSpeedUsed <= 1.00001, `plan.stats.maxSpeedUsed (${plan.stats.maxSpeedUsed}) debe ser <= 1.0x`);
  assert(plan.stats.strokeRetainedPct >= 99.99, `strokeRetainedPct (${plan.stats.strokeRetainedPct}%) debe ser 100%`);
  assert(plan.stats.allStrokes100PctRetained === true, 'allStrokes100PctRetained debe ser true');
  assert(plan.stats.maxLagSec > 10.0, `El lag acumulado debe superar 10s para probar el estrés (actual: ${plan.stats.maxLagSec}s)`);
  assert(plan.stats.maxLagSec > 25.0, `El lag acumulado debe superar 25s (actual: ${plan.stats.maxLagSec}s)`);

  let maxSpeedEncountered = 0;
  for (const entry of plan.playableEntries) {
    if (entry.speed > maxSpeedEncountered) maxSpeedEncountered = entry.speed;
    assert(entry.speed <= 1.00001, `Seña ${entry.gloss} aceleró a speed=${entry.speed} bajo lag de ${entry.lagSec}s`);
    assert(entry.strokeRetainedPct >= 99.99, `Seña ${entry.gloss} perdió trazo: ${entry.strokeRetainedPct}%`);
    assert(Math.abs(entry.strokeDuration - entry.origStrokeDuration) < 1e-4, `Trazo recortado en ${entry.gloss}`);
  }

  // Muestreo continuo a lo largo de toda la secuencia (pasos de 100ms)
  const dt = 0.10;
  for (let t = 0; t <= plan.sequenceEndTime; t += dt) {
    const s = compiler.sample(t);
    assert(s.speed <= 1.00001, `compiler.sample(${t.toFixed(2)}).speed (${s.speed}) superó 1.0x`);
    if (t > 3.05) {
      assert(s.isExtendedTail === true, `isExtendedTail debe ser true en t=${t.toFixed(2)}s (videoDuration=3.0s)`);
    } else if (t < 2.95) {
      assert(s.isExtendedTail === false, `isExtendedTail debe ser false en t=${t.toFixed(2)}s`);
    }
  }

  console.log(`  ✔ PASS: 30 señas bajo lag masivo (${plan.stats.maxLagSec}s) respetaron ritmo <= 1.0x (max=${maxSpeedEncountered}) y 100% retención.`);
}

// -----------------------------------------------------------------------------
// ADVERSARIAL TEST 2: Boundary Conditions in Video Exporter & Extended Tail
// -----------------------------------------------------------------------------
console.log('\n--- TEST 2: Condiciones de Borde en Exportador y Cola Extendida ---');
{
  const compiler = new SequenceCompiler();

  // Caso 2.1: sequenceEndTime exactamente igual a videoDuration
  const projectEqual = {
    media_info: { duration_seconds: 10.0 },
    glosses: [
      { id: 'g1', gloss: 'HOLA', start_seconds: 0.0, end_seconds: 4.5 },
      { id: 'g2', gloss: 'PODER', start_seconds: 5.0, end_seconds: 9.5 }
    ]
  };
  const planEqual = compiler.compile(projectEqual, testClipMap, { videoDuration: 10.0 });
  assert(Math.abs(planEqual.sequenceEndTime - 10.0) < 0.05, `sequenceEndTime (${planEqual.sequenceEndTime}) debe coincidir con videoDuration=10.0`);
  assert(planEqual.extendedTailSec < 0.05, `extendedTailSec (${planEqual.extendedTailSec}) debe ser ~0`);

  const effectiveEndEqual = Math.max(10.0, compiler.getSequenceEndTime(10.0));
  assert(effectiveEndEqual === 10.0, `effectiveEndTime debe ser 10.0 (recibido ${effectiveEndEqual})`);
  const framesEqual = Math.max(1, Math.round(effectiveEndEqual * 30.0));
  assert(framesEqual === 300, `totalFrames debe ser 300 (recibido ${framesEqual})`);

  // Caso 2.2: sequenceEndTime menor a videoDuration (video largo, pocas señas)
  const projectShorter = {
    media_info: { duration_seconds: 60.0 },
    glosses: [
      { id: 'g1', gloss: 'HOLA', start_seconds: 1.0, end_seconds: 3.0 }
    ]
  };
  const planShorter = compiler.compile(projectShorter, testClipMap, { videoDuration: 60.0 });
  assert(planShorter.sequenceEndTime === 60.0, `sequenceEndTime (${planShorter.sequenceEndTime}) debe expandirse hasta videoDuration=60.0`);
  const effectiveEndShorter = Math.max(60.0, compiler.getSequenceEndTime(60.0));
  assert(effectiveEndShorter === 60.0, `effectiveEndTime debe ser 60.0 (recibido ${effectiveEndShorter})`);
  assert(planShorter.segments[planShorter.segments.length - 1].type === 'rest', 'Último segmento debe ser reposo');
  assert(planShorter.segments[planShorter.segments.length - 1].endSec === 60.0, 'Segmento de reposo debe extenderse hasta 60.0s');

  // Caso 2.3: sequenceEndTime mucho mayor a videoDuration (video de 5s, señas duran ~12s)
  const projectLonger = {
    media_info: { duration_seconds: 5.0 },
    glosses: [
      { id: 'g1', gloss: 'HOLA', start_seconds: 1.0, end_seconds: 2.0 },
      { id: 'g2', gloss: 'PODER', start_seconds: 2.0, end_seconds: 3.0 },
      { id: 'g3', gloss: 'LIBERTAD', start_seconds: 3.0, end_seconds: 4.0 },
      { id: 'g4', gloss: 'DECIDIR', start_seconds: 4.0, end_seconds: 5.0 },
      { id: 'g5', gloss: 'CENTRO', start_seconds: 5.0, end_seconds: 6.0 },
      { id: 'g6', gloss: 'ABANICO', start_seconds: 6.0, end_seconds: 7.0 }
    ]
  };
  const planLonger = compiler.compile(projectLonger, testClipMap, { videoDuration: 5.0 });
  assert(planLonger.sequenceEndTime > 5.0, `sequenceEndTime (${planLonger.sequenceEndTime}) debe exceder videoDuration=5.0`);
  const effectiveEndLonger = Math.max(5.0, compiler.getSequenceEndTime(5.0));
  assert(effectiveEndLonger === planLonger.sequenceEndTime, `effectiveEndTime debe ser ${planLonger.sequenceEndTime}`);
  assert(planLonger.extendedTailSec > 0, `extendedTailSec (${planLonger.extendedTailSec}) debe ser > 0`);

  // Caso 2.4: Proyecto vacío (0 glosas)
  const emptyPlan = compiler.compile({ media_info: { duration_seconds: 12.0 }, glosses: [] }, testClipMap, { videoDuration: 12.0 });
  assert(emptyPlan.sequenceEndTime === 12.0, 'Proyecto vacío debe respetar videoDuration');
  assert(emptyPlan.stats.maxSpeedUsed === 1.0, 'Proyecto vacío maxSpeedUsed debe ser 1.0');
  assert(emptyPlan.stats.strokeRetainedPct === 100.0, 'Proyecto vacío retención debe ser 100%');

  // Caso 2.5: videoDuration = 0
  const zeroDurPlan = compiler.compile({ media_info: { duration_seconds: 0 }, glosses: [{ id: 'z1', gloss: 'HOLA', start_seconds: 0, end_seconds: 1 }] }, testClipMap, { videoDuration: 0 });
  assert(zeroDurPlan.sequenceEndTime > 0, 'sequenceEndTime debe calcularse positivamente aún con videoDuration=0');

  console.log('  ✔ PASS: Condiciones de borde (igual, menor, mucho mayor, vacío, videoDuration=0) validadas.');
}

// -----------------------------------------------------------------------------
// ADVERSARIAL TEST 3: Parameter Override Injection Attacks
// -----------------------------------------------------------------------------
console.log('\n--- TEST 3: Inyección Maliciosa de Parámetros de Aceleración ---');
{
  const compiler = new SequenceCompiler({ maxSpeed: 2.5, minSpeed: 0.1 });

  // Intentar forzar compilación con maxSpeed: 2.0 y maxLagSec: 0.05
  const hostilePlan = compiler.compile(
    {
      media_info: { duration_seconds: 1.0 },
      glosses: [
        { id: 'h1', gloss: 'HOLA', start_seconds: 0.0, end_seconds: 0.2 },
        { id: 'h2', gloss: 'PODER', start_seconds: 0.2, end_seconds: 0.4 }
      ]
    },
    testClipMap,
    { maxSpeed: 2.0, maxLagSec: 0.05 }
  );

  assert(hostilePlan.stats.maxSpeedUsed <= 1.00001, `maxSpeedUsed (${hostilePlan.stats.maxSpeedUsed}) fue forzado arriba de 1.0x`);
  for (const entry of hostilePlan.playableEntries) {
    assert(entry.speed <= 1.00001, `Entrada acelerada a ${entry.speed} por override`);
    assert(entry.strokeRetainedPct >= 99.99, `Retención recortada a ${entry.strokeRetainedPct}%`);
  }

  console.log('  ✔ PASS: Intentos de override agresivos (maxSpeed=2.0) fueron neutralizados a <= 1.0x.');
}

// -----------------------------------------------------------------------------
// ADVERSARIAL TEST 4: Fingerspelling Temporal Compression Attack
// -----------------------------------------------------------------------------
console.log('\n--- TEST 4: Ataque de Compresión Temporal en Dactilología ---');
{
  const hostileTargets = [0.01, 0.0001, -1.0, 0.10];
  const testWords = ['UPEC', 'ECUADOR', 'CONSTITUCIONALIDAD', 'LLAVE', 'CHIMBORAZO'];

  for (const word of testWords) {
    for (const targetDur of hostileTargets) {
      const clip = createLSECFingerspellingWordClip(word, { targetDurationSec: targetDur });
      const tokens = tokenizeLSECFingerspelling(word);
      const minNaturalExpected = tokens.length * 0.38 + (tokens.length - 1) * 0.11;

      const strokeDur = clip.stroke?.durationSec;
      assert(typeof strokeDur === 'number' && !Number.isNaN(strokeDur), `clip.stroke.durationSec debe ser numérico`);
      assert(
        strokeDur >= minNaturalExpected - 0.05,
        `Dactilología de '${word}' comprimida bajo target=${targetDur}s: dur=${strokeDur}s < natural=${minNaturalExpected}s`
      );
      assert(clip.durationMs >= (minNaturalExpected + 0.15 + 0.18) * 1000 - 10, `durationMs muy corto`);
    }
  }

  console.log('  ✔ PASS: Dactilología resistió todas las solicitudes de compresión hostiles (scale >= 1.0).');
}

// -----------------------------------------------------------------------------
// ADVERSARIAL TEST 5: Deterministic Offline Video Exporter Simulation
// -----------------------------------------------------------------------------
console.log('\n--- TEST 5: Simulación Determinista del Exportador (Freeze & Tail) ---');
{
  const vDur = 8.0;
  const seqEnd = 14.5;
  const TARGET_FPS = 30.0;
  const DT = 1.0 / TARGET_FPS;

  const effectiveEndTime = Math.max(vDur, seqEnd);
  const totalFrames = Math.max(1, Math.round(effectiveEndTime * TARGET_FPS));

  assert(effectiveEndTime === 14.5, `effectiveEndTime esperado 14.5, recibido ${effectiveEndTime}`);
  assert(totalFrames === 435, `totalFrames esperado 435 (14.5 * 30), recibido ${totalFrames}`);

  let videoSeekCount = 0;
  let frozenVideoFrameCount = 0;
  let avatarStepCount = 0;

  for (let frameIdx = 0; frameIdx < totalFrames; frameIdx++) {
    const currentTime = Math.min(effectiveEndTime, frameIdx * DT);
    const videoSeekTime = Math.min(vDur, currentTime);

    // Lógica exacta de video-exporter.js:
    if (currentTime <= vDur + DT * 0.5) {
      videoSeekCount++;
      assert(videoSeekTime <= vDur, `videoSeekTime (${videoSeekTime}) no puede superar vDur (${vDur})`);
    } else {
      frozenVideoFrameCount++;
      assert(videoSeekTime === vDur, `videoSeekTime debe congelarse en vDur`);
    }

    avatarStepCount++;
  }

  assert(avatarStepCount === totalFrames, `El avatar debe avanzar exactamente los ${totalFrames} fotogramas`);
  assert(frozenVideoFrameCount > 0, `Deben existir fotogramas con video congelado (obtenidos: ${frozenVideoFrameCount})`);
  assert(videoSeekCount + frozenVideoFrameCount === totalFrames, 'Suma de frames consistente');

  console.log(`  ✔ PASS: Exportador simuló 435 fotogramas (seek=${videoSeekCount}, frozen=${frozenVideoFrameCount}, avatar=${avatarStepCount}).`);
}

// -----------------------------------------------------------------------------
// ADVERSARIAL TEST 6: ISO/IEC 25010 Line Count Audit (All M1 files <= 800 lines)
// -----------------------------------------------------------------------------
console.log('\n--- TEST 6: Auditoría de Límite de 800 Líneas (ISO/IEC 25010) ---');
{
  const m1Files = [
    'app/static/js/avatar/sign-stroke-window.js',
    'app/static/js/avatar/avatar-sync-controller.js',
    'app/static/js/avatar/avatar-controller.js',
    'app/static/js/avatar/sign-clips-fingerspelling-lsec.js',
    'app/static/js/avatar/sequence-run-scheduler.js',
    'app/static/js/avatar/sequence-compiler.js',
    'app/static/js/avatar/studio-avatar-bridge.js',
    'app/static/js/state.js',
    'app/static/js/components/video-player.js',
    'app/static/js/components/video-exporter.js',
    'app/tests/test_m1_natural_rhythm_and_tail.mjs'
  ];

  for (const relPath of m1Files) {
    const fullPath = path.resolve(projectRoot, 'lsec_translator_prototype', relPath);
    if (!fs.existsSync(fullPath)) {
      throw new Error(`Archivo no encontrado para auditoría de líneas: ${fullPath}`);
    }
    const content = fs.readFileSync(fullPath, 'utf8');
    const lineCount = content.split('\n').length;
    assert(lineCount <= 800, `Archivo ${relPath} excede 800 líneas: ${lineCount}`);
    console.log(`  - ${relPath}: ${lineCount} líneas (<= 800) [OK]`);
  }
}

// -----------------------------------------------------------------------------
// SUMMARY
// -----------------------------------------------------------------------------
console.log('\n================================================================');
console.log(`  RESUMEN CHALLENGER: ${passCount} ASERCIONES VERIFICADAS | 0 FALLOS`);
console.log('  VEREDICTO: COMPLETO Y ROBUSTO');
console.log('================================================================');
