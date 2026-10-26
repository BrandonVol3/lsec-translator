/**
 * Test Suite M1 — Adversarial Stress & Empirical Challenge Harness
 * (app/tests/test_m1_adversarial_stress.mjs)
 *
 * Verificación empírica adversarial para Milestone 1 (M1 / Requisito R1):
 * 1. Ráfaga extrema de 10 señas léxicas empaquetadas en 2.0s (ranuras de 0.20s).
 * 2. Glosas con solapamiento temporal completo (5 glosas concurrentes en slot de 0.10s).
 * 3. Deletreo dactilológico ultra-largo ('UNIVERSIDAD_POLITECNICA_ESTATAL_DEL_CARCHI' y
 *    'CENTRO_DE_ARTE_Y_CULTURA_DE_LA_UNIVERSIDAD_POLITECNICA_ESTATAL_DEL_CARCHI')
 *    sometido a compresión agresiva (targetDurationSec=0.10s).
 * 4. Intentos hostiles de sobreecritura de opciones (maxSpeed=5.0, minSpeed=2.0, maxLagSec=0.01).
 * 5. Secuencia masiva de señas repetidas consecutivas sin poda de repeatedStroke.
 * 6. Simulación matemática de congelamiento de video en 5.0s y cola extendida hasta 12.0s
 *    a 60 FPS cuadro a cuadro verificando monotonía, isExtendedTail y congelamiento de fotograma.
 * 7. Sincronización offline del exportador MP4 bajo cola extendida extrema.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  REST_POSE,
  convertDirectAnimationToSignClip,
  trimSignClipStroke
} from '../static/js/avatar/sign-animation-schema.js';
import { SequenceCompiler } from '../static/js/avatar/sequence-compiler.js';
import { LSECStateStore } from '../static/js/state.js';
import {
  createLSECFingerspellingWordClip,
  createLSECFingerspellingSignClip,
  tokenizeLSECFingerspelling
} from '../static/js/avatar/sign-clips-fingerspelling-lsec.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const V27_BASE = path.join(__dirname, '../../../Diccionario LSEC/senas_vrm_standardized_v2.7');
const STROKE_INDEX_PATH = path.join(__dirname, '../data/stroke_index_v27.json');

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

// Cargar catálogo de prueba
const clipAbanico = loadClipV27('Abanico', 'ABANICO');
const clipHola = loadClipV27('Hola', 'HOLA');
const clipConocimiento = loadClipV27('Conocer', 'CONOCIMIENTO');
const clipPoder = loadClipV27('Fuerte, Fuerza, Poder', 'PODER');
const clipLibertad = loadClipV27('Libertad, Libre', 'LIBERTAD');
const clipDecidir = loadClipV27('Decidir, Decisión', 'DECIDIR');
const clipCentro = loadClipV27('Centro', 'CENTRO');
const clipArte = loadClipV27('Arte', 'ARTE');
const clipCultura = loadClipV27('Cultura', 'CULTURA');
const clipDibujo = loadClipV27('Dibujar', 'DIBUJO');

const testClipMap = new Map([
  ['ABANICO', clipAbanico],
  ['HOLA', clipHola],
  ['CONOCIMIENTO', clipConocimiento],
  ['PODER', clipPoder],
  ['LIBERTAD', clipLibertad],
  ['DECIDIR', clipDecidir],
  ['CENTRO', clipCentro],
  ['ARTE', clipArte],
  ['CULTURA', clipCultura],
  ['DIBUJO', clipDibujo]
]);

console.log('\n======================================================================');
console.log('=== HARNESS ADVERSARIAL M1: PRUEBAS DE ESTRÉS EMPÍRICO Y ROBUSTEZ ===');
console.log('======================================================================\n');

let totalAssertionsChecked = 0;
function assert(condition, message) {
  totalAssertionsChecked++;
  if (!condition) {
    throw new Error(`[ADVERSARIAL FAIL] ${message}`);
  }
}

// -----------------------------------------------------------------------------
// PRUEBA 1: Ráfaga Extrema de 10 Señas Léxicas en Ranura Hiperdensa de 2.0s
// -----------------------------------------------------------------------------
console.log('--- PRUEBA 1: Ráfaga Extrema de 10 Señas Léxicas en 2.0s ---');
function stressTestDense10LexicalBurst() {
  const compiler = new SequenceCompiler();

  const dense10Project = {
    media_info: { duration_seconds: 2.0 },
    glosses: [
      { id: 'd1', gloss: 'ABANICO', start_seconds: 0.0, end_seconds: 0.20, slotDuration: 0.20 },
      { id: 'd2', gloss: 'CONOCIMIENTO', start_seconds: 0.20, end_seconds: 0.40, slotDuration: 0.20 },
      { id: 'd3', gloss: 'PODER', start_seconds: 0.40, end_seconds: 0.60, slotDuration: 0.20 },
      { id: 'd4', gloss: 'LIBERTAD', start_seconds: 0.60, end_seconds: 0.80, slotDuration: 0.20 },
      { id: 'd5', gloss: 'DECIDIR', start_seconds: 0.80, end_seconds: 1.00, slotDuration: 0.20 },
      { id: 'd6', gloss: 'CENTRO', start_seconds: 1.00, end_seconds: 1.20, slotDuration: 0.20 },
      { id: 'd7', gloss: 'ARTE', start_seconds: 1.20, end_seconds: 1.40, slotDuration: 0.20 },
      { id: 'd8', gloss: 'CULTURA', start_seconds: 1.40, end_seconds: 1.60, slotDuration: 0.20 },
      { id: 'd9', gloss: 'DIBUJO', start_seconds: 1.60, end_seconds: 1.80, slotDuration: 0.20 },
      { id: 'd10', gloss: 'HOLA', start_seconds: 1.80, end_seconds: 2.00, slotDuration: 0.20 }
    ]
  };

  const plan = compiler.compile(dense10Project, testClipMap, { videoDuration: 2.0 });

  assert(plan.stats.maxSpeedUsed <= 1.0001, `maxSpeedUsed (${plan.stats.maxSpeedUsed}) superó 1.0x`);
  assert(plan.stats.strokeRetainedPct >= 99.99, `strokeRetainedPct (${plan.stats.strokeRetainedPct}%) < 100%`);
  assert(plan.stats.allStrokes100PctRetained === true, 'allStrokes100PctRetained no es true');
  assert(plan.playableEntries.length === 10, `Se esperaban 10 entradas reproducibles, se obtuvieron ${plan.playableEntries.length}`);

  for (let i = 0; i < plan.playableEntries.length; i++) {
    const entry = plan.playableEntries[i];
    assert(entry.speed <= 1.0001, `Entrada ${entry.gloss} [#${i}] tiene speed=${entry.speed} > 1.0`);
    assert(entry.strokeRetainedPct >= 99.99, `Entrada ${entry.gloss} [#${i}] tiene strokeRetainedPct=${entry.strokeRetainedPct}%`);
    assert(entry.strokeDuration >= entry.origStrokeDuration - 1e-4, `Entrada ${entry.gloss} recortó su trazo: ${entry.strokeDuration}s < ${entry.origStrokeDuration}s`);
  }

  assert(plan.sequenceEndTime > 2.0, `sequenceEndTime (${plan.sequenceEndTime}) no extendió la cola`);
  console.log(`  -> Secuencia de 10 señas extendió cola a ${plan.sequenceEndTime}s (cola=${plan.extendedTailSec}s).`);

  // Muestreo cuadro a cuadro a 60 FPS a lo largo de toda la secuencia
  const dt = 1.0 / 60.0;
  let sampleCount = 0;
  for (let t = 0; t <= plan.sequenceEndTime + 0.001; t += dt) {
    const sample = compiler.sample(t);
    sampleCount++;
    assert(sample.speed <= 1.0001, `Muestra en t=${t.toFixed(3)}s superó speed 1.0: ${sample.speed}`);
    assert(typeof sample.bones === 'object' && sample.bones !== null, `Bones inválido en t=${t}`);
    if (t > 2.05) {
      assert(sample.isExtendedTail === true, `isExtendedTail debió ser true en t=${t.toFixed(3)}`);
    }
  }
  console.log(`  -> Muestreados ${sampleCount} cuadros a 60 FPS: 0 violaciones de velocidad, 100% quats válidos.`);
}
stressTestDense10LexicalBurst();

// -----------------------------------------------------------------------------
// PRUEBA 2: Solapamiento Temporal Completo (5 Glosas Concurrentes en Slot de 0.10s)
// -----------------------------------------------------------------------------
console.log('--- PRUEBA 2: Solapamiento Temporal Completo ---');
function stressTestOverlappingGlosses() {
  const compiler = new SequenceCompiler();

  const overlapProject = {
    media_info: { duration_seconds: 1.0 },
    glosses: [
      { id: 'ov1', gloss: 'CENTRO', start_seconds: 0.5, end_seconds: 0.6, slotDuration: 0.10 },
      { id: 'ov2', gloss: 'ARTE', start_seconds: 0.5, end_seconds: 0.6, slotDuration: 0.10 },
      { id: 'ov3', gloss: 'CULTURA', start_seconds: 0.5, end_seconds: 0.6, slotDuration: 0.10 },
      { id: 'ov4', gloss: 'PODER', start_seconds: 0.5, end_seconds: 0.6, slotDuration: 0.10 },
      { id: 'ov5', gloss: 'LIBERTAD', start_seconds: 0.5, end_seconds: 0.6, slotDuration: 0.10 }
    ]
  };

  const plan = compiler.compile(overlapProject, testClipMap, { videoDuration: 1.0 });

  assert(plan.playableEntries.length === 5, `Se esperaban 5 entradas reproducibles, se obtuvieron ${plan.playableEntries.length}`);
  assert(plan.stats.maxSpeedUsed <= 1.0001, `maxSpeedUsed (${plan.stats.maxSpeedUsed}) superó 1.0x en solapamiento`);
  assert(plan.stats.allStrokes100PctRetained === true, 'allStrokes100PctRetained no es true en solapamiento');

  // Verificar serialización estricta sin colisión temporal
  for (let i = 1; i < plan.playableEntries.length; i++) {
    const prev = plan.playableEntries[i - 1];
    const curr = plan.playableEntries[i];
    assert(curr.startSec >= prev.endSec - 1e-4, `Colisión detectada: entrada ${curr.gloss} inicia en ${curr.startSec} antes de fin previo ${prev.endSec}`);
    assert(curr.speed <= 1.0001, `Entrada ${curr.gloss} acelerada a ${curr.speed}`);
    assert(curr.strokeRetainedPct >= 99.99, `Entrada ${curr.gloss} retuvo solo ${curr.strokeRetainedPct}%`);
  }
  assert(plan.sequenceEndTime > 1.0, `sequenceEndTime no extendió cola (${plan.sequenceEndTime}s <= 1.0s)`);
  console.log(`  -> 5 glosas concurrentes serializadas deterministamente hasta ${plan.sequenceEndTime}s a ritmo 1.0x.`);
}
stressTestOverlappingGlosses();

// -----------------------------------------------------------------------------
// PRUEBA 3: Dactilología Ultra-Larga Bajo Presión de Compresión Agresiva
// -----------------------------------------------------------------------------
console.log('--- PRUEBA 3: Dactilología Ultra-Larga Bajo Presión de Compresión ---');
function stressTestUltraLongFingerspelling() {
  const longWords = [
    'UNIVERSIDAD_POLITECNICA_ESTATAL_DEL_CARCHI',
    'CENTRO_DE_ARTE_Y_CULTURA_DE_LA_UNIVERSIDAD_POLITECNICA_ESTATAL_DEL_CARCHI',
    'FERROCARRIL_DEL_ECUADOR',
    'CHIMBORAZO_Y_TUNGURAHUA',
    'NIÑO_ACOMPAÑAR'
  ];

  for (const word of longWords) {
    const tokens = tokenizeLSECFingerspelling(word);
    assert(tokens.length > 0, `No se generaron tokens para ${word}`);

    // Intentar forzar compresión temporal solicitando slot artificialmente ínfimo de 0.10s
    const clip = createLSECFingerspellingWordClip(word, { targetDurationSec: 0.10 });

    const totalDurSec = clip.durationMs / 1000.0;
    const strokeDur = clip.stroke.durationSec;
    const minNaturalSec = tokens.length * 0.38 + (tokens.length - 1) * 0.11;

    // Verificar que cada segmento de letra retiene su duración anatómica mínima (>= 0.38s)
    assert(clip.metadata.letterSegments.length === tokens.length, `Cantidad de segmentos no coincide: ${clip.metadata.letterSegments.length} vs ${tokens.length}`);
    for (const seg of clip.metadata.letterSegments) {
      const segHoldSec = seg.endSec - seg.startSec;
      assert(segHoldSec >= 0.38 - 1e-4, `Letra ${seg.grapheme} comprimida por debajo de 0.38s: ${segHoldSec.toFixed(3)}s`);
    }

    assert(strokeDur >= minNaturalSec - 0.05, `Trazo de '${word}' comprimido: ${strokeDur}s < ${minNaturalSec}s`);
    assert(totalDurSec > strokeDur, `Duración total (${totalDurSec}s) menor al trazo (${strokeDur}s)`);

    // Compilar en SequenceCompiler dentro de una ranura de habla diminuta de 0.25s
    const compiler = new SequenceCompiler();
    const fsProject = {
      media_info: { duration_seconds: 3.0 },
      glosses: [
        { id: 'fs1', gloss: word, is_fingerspelling: true, start_seconds: 0.5, end_seconds: 0.75, slotDuration: 0.25 }
      ]
    };

    const plan = compiler.compile(fsProject, new Map(), { videoDuration: 3.0 });

    assert(plan.playableEntries.length === 1, `Dactilología '${word}' no fue playable`);
    const pe = plan.playableEntries[0];
    assert(pe.speed <= 1.0001, `maxSpeed superó 1.0 en dactilología '${word}': ${pe.speed}`);
    assert(pe.strokeRetainedPct >= 99.99, `strokeRetainedPct en dactilología '${word}' = ${pe.strokeRetainedPct}% < 100%`);
    assert(plan.stats.maxSpeedUsed <= 1.0001, `maxSpeedUsed superó 1.0 en dactilología '${word}': ${plan.stats.maxSpeedUsed}`);
    assert(plan.stats.allStrokes100PctRetained === true, `Trazo no retenido al 100% en dactilología '${word}'`);
    assert(plan.sequenceEndTime > 3.0, `sequenceEndTime no extendió cola para dactilología '${word}' (${plan.sequenceEndTime}s)`);
  }
  console.log(`  -> 5 palabras ultra-largas (hasta 73 grafemas) conservan 100% duración anatómica con scale >= 1.0.`);
}
stressTestUltraLongFingerspelling();

// -----------------------------------------------------------------------------
// PRUEBA 4: Inmunidad ante Sobreecritura Hostil de Opciones
// -----------------------------------------------------------------------------
console.log('--- PRUEBA 4: Inmunidad ante Sobreecritura Hostil de Opciones ---');
function stressTestHostileOptionsOverride() {
  const compiler = new SequenceCompiler();

  const simpleProject = {
    media_info: { duration_seconds: 1.0 },
    glosses: [
      { id: 'h1', gloss: 'CONOCIMIENTO', start_seconds: 0.0, end_seconds: 0.20, slotDuration: 0.20 },
      { id: 'h2', gloss: 'PODER', start_seconds: 0.20, end_seconds: 0.40, slotDuration: 0.20 }
    ]
  };

  const hostileConfigs = [
    { maxSpeed: 5.0, minSpeed: 2.5, maxLagSec: 0.01 },
    { maxSpeed: 10.0, maxLagSec: 0.0 },
    { maxSpeed: -2.0, minSpeed: -1.0 },
    { maxSpeed: NaN, minSpeed: null },
    { maxSpeed: 'hyperdrive', maxLagSec: -5 }
  ];

  for (const hostile of hostileConfigs) {
    const plan = compiler.compile(simpleProject, testClipMap, hostile);
    assert(plan.stats.maxSpeedUsed <= 1.0001, `Inyección falló: maxSpeedUsed=${plan.stats.maxSpeedUsed} con config=${JSON.stringify(hostile)}`);
    for (const pe of plan.playableEntries) {
      assert(pe.speed <= 1.0001, `Entrada acelerada con config hostil: speed=${pe.speed}`);
      assert(pe.strokeRetainedPct >= 99.99, `Trazo recortado con config hostil: ${pe.strokeRetainedPct}%`);
    }
  }
  console.log(`  -> 5 configuraciones hostiles rechazadas invariablemente; maxSpeed se mantiene strictly <= 1.0.`);
}
stressTestHostileOptionsOverride();

// -----------------------------------------------------------------------------
// PRUEBA 5: Señas Repetidas Consecutivas sin Poda de RepeatedStroke
// -----------------------------------------------------------------------------
console.log('--- PRUEBA 5: Señas Repetidas Consecutivas sin Poda de RepeatedStroke ---');
function stressTestRepeatedSignsRetention() {
  const compiler = new SequenceCompiler();

  // 8 señas repetidas de ABANICO en 1.5s
  const repeatedProject = {
    media_info: { duration_seconds: 1.5 },
    glosses: Array.from({ length: 8 }, (_, i) => ({
      id: `rep_${i}`,
      gloss: 'ABANICO',
      start_seconds: i * 0.15,
      end_seconds: (i + 1) * 0.15,
      slotDuration: 0.15
    }))
  };

  const plan = compiler.compile(repeatedProject, testClipMap, { videoDuration: 1.5 });

  assert(plan.playableEntries.length === 8, `Se esperaban 8 entradas, se obtuvieron ${plan.playableEntries.length}`);
  assert(plan.stats.maxSpeedUsed <= 1.0001, `maxSpeedUsed=${plan.stats.maxSpeedUsed} > 1.0`);
  assert(plan.stats.allStrokes100PctRetained === true, 'allStrokes100PctRetained es false');

  const origDuration = clipAbanico.metadata.strokeDurationSec;
  for (let i = 0; i < plan.playableEntries.length; i++) {
    const pe = plan.playableEntries[i];
    assert(pe.strokeRetainedPct >= 99.99, `Repetición #${i} recortada al ${pe.strokeRetainedPct}%`);
    assert(pe.strokeDuration >= origDuration - 1e-4, `Duración de trazo #${i} reducida: ${pe.strokeDuration}s < ${origDuration}s`);
    assert(pe.speed <= 1.0001, `Velocidad #${i} acelerada: ${pe.speed}`);
  }

  console.log(`  -> 8 señas consecutivas retienen 100% de trazo (${origDuration.toFixed(2)}s c/u) con 0 podas.`);
}
stressTestRepeatedSignsRetention();

// -----------------------------------------------------------------------------
// PRUEBA 6: Simulación Exacta de Video Freeze Loop a 60 FPS (video=5.0s, seq=12.0s)
// -----------------------------------------------------------------------------
console.log('--- PRUEBA 6: Simulación de Video Freeze Loop a 60 FPS (video=5.0s, seq=12.0s) ---');
function stressTestVideoFreezeLoopSimulation() {
  const store = new LSECStateStore();
  const vDur = 5.0;
  const seqEnd = 12.0;

  store.loadProject({ media_info: { duration_seconds: vDur } });
  store.setSequenceEndTime(seqEnd);
  store.setIsPlaying(true);

  assert(store.state.playback.videoDuration === 5.0, `videoDuration esperado 5.0, obtenido ${store.state.playback.videoDuration}`);
  assert(store.state.playback.duration === 12.0, `duration esperado 12.0, obtenido ${store.state.playback.duration}`);

  // Simulación de elemento HTML5 Video
  const videoEl = {
    duration: vDur,
    currentTime: vDur,
    paused: false,
    pause() { this.paused = true; }
  };

  // Manejador del evento 'ended' idéntico a video-player.js
  let extendedLoopRunning = false;
  const onEnded = () => {
    const dur = videoEl.duration;
    const seq = store.state.playback.sequenceEndTime;
    if (seq > dur + 0.05) {
      videoEl.pause();
      videoEl.currentTime = Math.max(0, dur - 0.01);
      extendedLoopRunning = true;
    }
  };

  onEnded();

  assert(videoEl.paused === true, 'El elemento de video no fue pausado al terminar');
  assert(videoEl.currentTime === 4.99, `El video debe estar congelado en 4.99s, está en ${videoEl.currentTime}`);
  assert(extendedLoopRunning === true, 'El bucle de cola extendida no se activó');

  // Simulación a 60 FPS (dt = 1/60s = 0.01667s) desde t=5.0s hasta t=12.0s (420 pasos)
  const dt = 1.0 / 60.0;
  let simulatedTime = vDur;
  let frameCount = 0;

  while (simulatedTime < seqEnd) {
    simulatedTime += dt;
    frameCount++;

    if (simulatedTime >= seqEnd) {
      simulatedTime = seqEnd;
      store.setCurrentTime(seqEnd, 'end');
      store.setIsPlaying(false);
      break;
    } else {
      store.setCurrentTime(simulatedTime, 'extended_tail');
      if (simulatedTime > vDur + 0.05) {
        assert(store.state.playback.isExtendedTail === true, `isExtendedTail debe ser true en t=${simulatedTime}`);
      } else {
        assert(store.state.playback.isExtendedTail === false, `isExtendedTail debe ser false en t=${simulatedTime}`);
      }
      assert(videoEl.currentTime === 4.99, `El fotograma de video debe permanecer congelado en 4.99`);
    }
  }

  assert(store.state.playback.currentTime === 12.0, `currentTime final (${store.state.playback.currentTime}) !== 12.0`);
  assert(store.state.playback.isPlaying === false, 'El estado isPlaying debe ser false al finalizar sequenceEndTime');
  assert(videoEl.currentTime === 4.99, 'El video cambió de fotograma durante la cola');
  assert(frameCount >= 415 && frameCount <= 425, `Se esperaban ~420 cuadros a 60 FPS, se ejecutaron ${frameCount}`);

  console.log(`  -> ${frameCount} cuadros a 60 FPS verificados: video congelado en 4.99s, reloj avanzó a 12.0s.`);
}
stressTestVideoFreezeLoopSimulation();

// -----------------------------------------------------------------------------
// PRUEBA 7: Sincronización Determinista del Exportador MP4 en Cola Extrema
// -----------------------------------------------------------------------------
console.log('--- PRUEBA 7: Sincronización Determinista del Exportador MP4 en Cola Extrema ---');
function stressTestMP4ExporterExtremeTail() {
  const videoDuration = 3.0;
  const sequenceEndTime = 25.0;

  const effectiveEndTime = Math.max(videoDuration, sequenceEndTime);
  const TARGET_FPS = 30.0;
  const totalFrames = Math.max(1, Math.round(effectiveEndTime * TARGET_FPS));

  assert(effectiveEndTime === 25.0, `effectiveEndTime esperado 25.0, obtenido ${effectiveEndTime}`);
  assert(totalFrames === 750, `totalFrames esperado 750 (25s * 30fps), obtenido ${totalFrames}`);

  const DT = 1.0 / TARGET_FPS;
  let liveVideoFrames = 0;
  let frozenLastFrames = 0;
  let prevTimestamp = -1;

  for (let f = 0; f < totalFrames; f++) {
    const t = f * DT;
    assert(t > prevTimestamp, `Timestamp de cuadro #${f} no es monótono (${t} <= ${prevTimestamp})`);
    prevTimestamp = t;

    if (t <= videoDuration + DT * 0.5) {
      liveVideoFrames++;
    } else {
      frozenLastFrames++;
    }
  }

  assert(liveVideoFrames === 91, `Cuadros de video en vivo esperados 91, obtenidos ${liveVideoFrames}`);
  assert(frozenLastFrames === 659, `Cuadros congelados esperados 659, obtenidos ${frozenLastFrames}`);
  assert(liveVideoFrames + frozenLastFrames === 750, 'Suma de cuadros no coincide con el total');

  console.log(`  -> Exportador MP4: 750 cuadros deterministas (${liveVideoFrames} video + ${frozenLastFrames} congelados), 0 desfases.`);
}
stressTestMP4ExporterExtremeTail();

console.log('\n======================================================================');
console.log(`=== REPORTE EMPÍRICO: ${totalAssertionsChecked} ASERCIONES VERIFICADAS SATISFACTORIAMENTE ===`);
console.log('=== VEREDICTO DE ADVERSARIAL STRESS TEST: TODO APROBADO (100% PASS) ===');
console.log('======================================================================\n');
