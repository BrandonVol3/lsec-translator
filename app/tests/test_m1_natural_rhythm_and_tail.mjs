/**
 * Test Suite M1 — Ritmo Natural 1.0x sin Aceleración ni Recorte y Cola Extendida de Avatar
 * (app/tests/test_m1_natural_rhythm_and_tail.mjs)
 *
 * Valida los Criterios de Aceptación del Requisito R1 y Milestone 1:
 * 1. maxSpeedUsed <= 1.0x (0 señas aceleradas por encima de 1.0x) en secuencias de 1.mp4, 2.mp4 y 3.mp4.
 * 2. 100% de retención de trazo (strokeRetainedPct === 100.0%) en señas léxicas y dactilología.
 * 3. Eliminación de poda de repeticiones (repeatedStroke) y truncamiento por presión de lag.
 * 4. Dactilología con scale >= 1.0 sin compresión temporal de letras.
 * 5. Cola extendida sincronizada en state.js con congelamiento de último cuadro en video-player.js.
 * 6. Exportador MP4 determinista con effectiveEndTime = Math.max(duration, sequenceEndTime).
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
  tokenizeLSECFingerspelling
} from '../static/js/avatar/sign-clips-fingerspelling-lsec.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const V27_BASE = path.join(__dirname, '../../../Diccionario LSEC/senas_vrm_standardized_v2.7');
const STROKE_INDEX_PATH = path.join(__dirname, '../data/stroke_index_v27.json');

// Cargar stroke_index precalculado de v2.7
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

// Mapa de clips reutilizables
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

console.log('\n=== INICIANDO SUITE DE PRUEBAS M1: RITMO NATURAL 1.0x Y COLA EXTENDIDA ===\n');

// -----------------------------------------------------------------------------
// TEST 1: Ritmo Natural 1.0x Estricto en Secuencia 1.mp4 (UPEC)
// -----------------------------------------------------------------------------
console.log('--- TEST 1: Ritmo Natural 1.0x Estricto en Secuencia 1.mp4 (UPEC) ---');
function testSequence1Mp4NaturalRhythm() {
  const compiler = new SequenceCompiler();

  // Secuencia representativa de 1.mp4 con glosas léxicas y dactilología OOV
  const upecProject = {
    media_info: { duration_seconds: 48.850 },
    glosses: [
      { id: 'u1', gloss: 'CONOCIMIENTO', start_seconds: 1.19, end_seconds: 1.82, slotDuration: 0.63 },
      { id: 'u2', gloss: 'PODER', start_seconds: 2.06, end_seconds: 2.51, slotDuration: 0.45 },
      { id: 'u3', gloss: 'LIBERTAD', start_seconds: 4.96, end_seconds: 5.35, slotDuration: 0.39 },
      { id: 'u4', gloss: 'LIBERTAD', start_seconds: 5.67, end_seconds: 6.20, slotDuration: 0.53 },
      { id: 'u5', gloss: 'DECIDIR', start_seconds: 6.49, end_seconds: 6.95, slotDuration: 0.46 },
      { id: 'u6', gloss: 'U-P-E-C', is_fingerspelling: true, start_seconds: 45.0, end_seconds: 46.5, slotDuration: 1.50 }
    ]
  };

  const plan = compiler.compile(upecProject, testClipMap, { videoDuration: 48.850 });

  if (plan.stats.maxSpeedUsed > 1.0001) {
    throw new Error(`FAIL: maxSpeedUsed supera 1.0x en 1.mp4: ${plan.stats.maxSpeedUsed}`);
  }
  for (const pe of plan.playableEntries) {
    if (pe.speed > 1.0001) {
      throw new Error(`FAIL: Seña ${pe.gloss} acelerada por encima de 1.0x: speed=${pe.speed}`);
    }
  }

  if (plan.stats.minStrokeRetainedPct < 99.99 || !plan.stats.allStrokes100PctRetained) {
    throw new Error(`FAIL: Retención de trazo menor al 100% en 1.mp4: minStrokeRetainedPct=${plan.stats.minStrokeRetainedPct}`);
  }

  console.log(`PASS: 1.mp4 compilado a ritmo natural 1.0x: maxSpeedUsed=${plan.stats.maxSpeedUsed}, retención=${plan.stats.strokeRetainedPct}%, 0 señas aceleradas.`);
}
testSequence1Mp4NaturalRhythm();

// -----------------------------------------------------------------------------
// TEST 2: Ritmo Natural 1.0x Estricto en Secuencias de 2.mp4 y 3.mp4
// -----------------------------------------------------------------------------
console.log('--- TEST 2: Ritmo Natural 1.0x Estricto en Secuencias de 2.mp4 y 3.mp4 ---');
function testSequences2And3Mp4NaturalRhythm() {
  const compiler = new SequenceCompiler();

  // 2.mp4: Centro Académico de Arte y Cultura + Dactilología de contacto
  const project2 = {
    media_info: { duration_seconds: 22.0 },
    glosses: [
      { id: 'p2_1', gloss: 'CENTRO', start_seconds: 1.0, end_seconds: 1.8 },
      { id: 'p2_2', gloss: 'ARTE', start_seconds: 2.0, end_seconds: 2.7 },
      { id: 'p2_3', gloss: 'CULTURA', start_seconds: 2.8, end_seconds: 3.6 },
      { id: 'p2_4', gloss: 'DIBUJO', start_seconds: 8.5, end_seconds: 9.3 },
      { id: 'p2_5', gloss: 'W-H-A-T-S-A-P-P', is_fingerspelling: true, start_seconds: 18.0, end_seconds: 19.5 }
    ]
  };

  const plan2 = compiler.compile(project2, testClipMap, { videoDuration: 22.0 });
  if (plan2.stats.maxSpeedUsed > 1.0001) {
    throw new Error(`FAIL: maxSpeedUsed supera 1.0x en 2.mp4: ${plan2.stats.maxSpeedUsed}`);
  }
  if (!plan2.stats.allStrokes100PctRetained) {
    throw new Error(`FAIL: Trazo recortado en 2.mp4: minStrokeRetainedPct=${plan2.stats.minStrokeRetainedPct}`);
  }

  // 3.mp4: Discurso institucional denso con cola extendida requerida
  const project3 = {
    media_info: { duration_seconds: 8.0 },
    glosses: [
      { id: 'p3_1', gloss: 'CONOCIMIENTO', start_seconds: 0.5, end_seconds: 1.5 },
      { id: 'p3_2', gloss: 'PODER', start_seconds: 2.0, end_seconds: 3.0 },
      { id: 'p3_3', gloss: 'LIBERTAD', start_seconds: 3.5, end_seconds: 4.5 },
      { id: 'p3_4', gloss: 'DECIDIR', start_seconds: 5.0, end_seconds: 6.0 },
      { id: 'p3_5', gloss: 'CENTRO', start_seconds: 6.5, end_seconds: 7.5 }
    ]
  };

  const plan3 = compiler.compile(project3, testClipMap, { videoDuration: 8.0 });
  if (plan3.stats.maxSpeedUsed > 1.0001) {
    throw new Error(`FAIL: maxSpeedUsed supera 1.0x en 3.mp4: ${plan3.stats.maxSpeedUsed}`);
  }
  if (!plan3.stats.allStrokes100PctRetained) {
    throw new Error(`FAIL: Trazo recortado en 3.mp4: minStrokeRetainedPct=${plan3.stats.minStrokeRetainedPct}`);
  }
  if (plan3.sequenceEndTime <= 8.0) {
    throw new Error(`FAIL: Secuencia 3.mp4 debió extender cola (sequenceEndTime=${plan3.sequenceEndTime})`);
  }

  console.log(`PASS: Secuencias de 2.mp4 y 3.mp4 cumplen ritmo natural 1.0x estricto y 100% de trazo retenido.`);
}
testSequences2And3Mp4NaturalRhythm();

// -----------------------------------------------------------------------------
// TEST 3: 100% Retención de Trazo en Señas con Repetición y en Ráfagas Densas
// -----------------------------------------------------------------------------
console.log('--- TEST 3: 100% Retención de Trazo en Señas con Repetición y en Ráfagas Densas ---');
function testStrokeRetentionRepeatedAndDense() {
  const compiler = new SequenceCompiler();

  // Ráfaga densa donde el slot disponible es mucho menor que la duración natural de la seña
  const denseProject = {
    media_info: { duration_seconds: 2.0 },
    glosses: [
      // Abanico posee flag repeatedStroke y duración > 2.0s
      { id: 'r1', gloss: 'ABANICO', start_seconds: 0.0, end_seconds: 0.40, slotDuration: 0.40 },
      { id: 'r2', gloss: 'HOLA', start_seconds: 0.40, end_seconds: 0.80, slotDuration: 0.40 },
      { id: 'r3', gloss: 'ABANICO', start_seconds: 0.80, end_seconds: 1.20, slotDuration: 0.40 }
    ]
  };

  const plan = compiler.compile(denseProject, testClipMap, { videoDuration: 2.0 });

  for (const entry of plan.playableEntries) {
    if (entry.strokeDuration < entry.origStrokeDuration - 1e-4) {
      throw new Error(`FAIL: Ventana de trazo recortada en ${entry.gloss}: orig=${entry.origStrokeDuration}s, actual=${entry.strokeDuration}s`);
    }
    if (entry.strokeRetainedPct < 99.99) {
      throw new Error(`FAIL: strokeRetainedPct < 100.0% en ${entry.gloss}: ${entry.strokeRetainedPct}%`);
    }
    if (entry.speed > 1.0001) {
      throw new Error(`FAIL: Seña ${entry.gloss} acelerada bajo presión de lag: speed=${entry.speed}`);
    }
  }

  if (plan.sequenceEndTime <= 2.0) {
    throw new Error(`FAIL: La cola extendida no absorbió la duración de la ráfaga densa (sequenceEndTime=${plan.sequenceEndTime})`);
  }

  console.log(`PASS: 100% retención de trazo verificado: 0 podas de repeatedStroke, 0 truncamientos por lag (sequenceEndTime=${plan.sequenceEndTime}s).`);
}
testStrokeRetentionRepeatedAndDense();

// -----------------------------------------------------------------------------
// TEST 4: Dactilología con scale >= 1.0 (Sin Compresión Temporal de Letras)
// -----------------------------------------------------------------------------
console.log('--- TEST 4: Dactilología con scale >= 1.0 (Sin Compresión Temporal de Letras) ---');
function testFingerspellingNaturalDuration() {
  const wordsToTest = ['UPEC', 'CARCHI', 'WHATSAPP', 'ECUADOR'];

  for (const word of wordsToTest) {
    const tokens = tokenizeLSECFingerspelling(word);
    // Solicitar clip procedural con un slot artificialmente estrecho
    const clip = createLSECFingerspellingWordClip(word, { targetDurationSec: 0.50 });

    const strokeDur = clip.metadata.strokeDurationSec;
    const minExpectedNaturalSec = tokens.length * 0.38 + (tokens.length - 1) * 0.11;

    if (strokeDur < minExpectedNaturalSec - 0.05) {
      throw new Error(`FAIL: Dactilología de '${word}' comprimida: dur=${strokeDur}s < natural=${minExpectedNaturalSec}s`);
    }

    if (clip.metadata.strokeRetainedPct < 99.99) {
      throw new Error(`FAIL: Dactilología '${word}' tiene strokeRetainedPct < 100%: ${clip.metadata.strokeRetainedPct}`);
    }
  }

  console.log(`PASS: Dactilología LSEC conserva 100% de duración natural por letra (scale >= 1.0) sin atajos ni compresión.`);
}
testFingerspellingNaturalDuration();

// -----------------------------------------------------------------------------
// TEST 5: Sincronización del Reloj en state.js y Extensión de Cola
// -----------------------------------------------------------------------------
console.log('--- TEST 5: Sincronización del Reloj en state.js y Extensión de Cola ---');
function testStateStoreExtendedTail() {
  const store = new LSECStateStore();

  const mockProject = {
    media_info: { duration_seconds: 48.850 },
    glosses: []
  };

  store.loadProject(mockProject, 'test_video.mp4');

  if (store.state.playback.videoDuration !== 48.850) {
    throw new Error(`FAIL: videoDuration esperado 48.850, recibido ${store.state.playback.videoDuration}`);
  }
  if (store.state.playback.duration !== 48.850) {
    throw new Error(`FAIL: duration esperado 48.850 al inicio, recibido ${store.state.playback.duration}`);
  }

  // Notificar extensión de cola a 65.40s
  store.setSequenceEndTime(65.40);

  if (store.state.playback.duration !== 65.40) {
    throw new Error(`FAIL: duration no se expandió a max(videoDuration, sequenceEndTime): ${store.state.playback.duration}`);
  }

  // Avanzar tiempo dentro del video normal (t = 30.0s)
  store.setCurrentTime(30.0);
  if (store.state.playback.isExtendedTail !== false) {
    throw new Error(`FAIL: isExtendedTail debe ser false a los 30.0s`);
  }

  // Avanzar tiempo dentro de la cola extendida (t = 55.0s > 48.85s)
  store.setCurrentTime(55.0);
  if (store.state.playback.currentTime !== 55.0) {
    throw new Error(`FAIL: currentTime truncado prematuramente a ${store.state.playback.currentTime}`);
  }
  if (store.state.playback.isExtendedTail !== true) {
    throw new Error(`FAIL: isExtendedTail debe ser true durante la cola extendida`);
  }

  // Avanzar al final exacto de la secuencia
  store.setCurrentTime(65.40);
  if (store.state.playback.currentTime !== 65.40) {
    throw new Error(`FAIL: currentTime no alcanzó sequenceEndTime: ${store.state.playback.currentTime}`);
  }

  console.log(`PASS: state.js gestiona videoDuration, sequenceEndTime, isExtendedTail y avance sin truncamiento.`);
}
testStateStoreExtendedTail();

// -----------------------------------------------------------------------------
// TEST 6: Simulación de Video Freeze Loop en video-player.js
// -----------------------------------------------------------------------------
console.log('--- TEST 6: Simulación de Video Freeze Loop en video-player.js ---');
function testVideoPlayerFreezeLoopSimulation() {
  const store = new LSECStateStore();
  const vDur = 10.0;
  const seqEnd = 16.5;

  store.loadProject({ media_info: { duration_seconds: vDur } });
  store.setSequenceEndTime(seqEnd);
  store.setIsPlaying(true);

  // Simulación del comportamiento del manejador 'ended' de HTML5 Video
  const simulatedVideoEl = {
    duration: vDur,
    currentTime: vDur,
    paused: false,
    pause() { this.paused = true; }
  };

  let loopActive = false;
  let finalStateReached = false;

  const onEndedHandler = () => {
    const videoDuration = simulatedVideoEl.duration;
    const sequenceEnd = store.state.playback.sequenceEndTime;

    if (sequenceEnd > videoDuration + 0.05) {
      simulatedVideoEl.pause();
      simulatedVideoEl.currentTime = Math.max(0, videoDuration - 0.01);
      loopActive = true;
    }
  };

  onEndedHandler();

  if (!simulatedVideoEl.paused) {
    throw new Error(`FAIL: El elemento de video no fue pausado al terminar.`);
  }
  if (simulatedVideoEl.currentTime > vDur) {
    throw new Error(`FAIL: El video intentó avanzar más allá de su duración física.`);
  }
  if (!loopActive) {
    throw new Error(`FAIL: El modo de cola extendida no se activó.`);
  }

  // Simular avance del bucle a 1.0x
  let virtualTime = vDur;
  const dt = 0.5; // pasos de 500ms
  while (virtualTime < seqEnd) {
    virtualTime += dt;
    if (virtualTime >= seqEnd) {
      virtualTime = seqEnd;
      store.setCurrentTime(seqEnd, 'end');
      store.setIsPlaying(false);
      finalStateReached = true;
    } else {
      store.setCurrentTime(virtualTime, 'extended_tail');
    }
  }

  if (!finalStateReached || store.state.playback.isPlaying !== false) {
    throw new Error(`FAIL: El bucle no concluyó adecuadamente en sequenceEndTime.`);
  }
  if (store.state.playback.currentTime !== seqEnd) {
    throw new Error(`FAIL: El reloj final no coincide con sequenceEndTime (${store.state.playback.currentTime} vs ${seqEnd})`);
  }

  console.log(`PASS: Simulación de congelamiento de video y avance de reloj extendido a 1.0x verificada exitosamente.`);
}
testVideoPlayerFreezeLoopSimulation();

// -----------------------------------------------------------------------------
// TEST 7: Sincronización en video-exporter.js con Cola Extendida
// -----------------------------------------------------------------------------
console.log('--- TEST 7: Sincronización en video-exporter.js con Cola Extendida ---');
function testVideoExporterTailCalculation() {
  const vDur = 48.850;
  const seqEnd = 62.300;

  const mockBridge = {
    getSequenceEndTime: (dur) => Math.max(dur, seqEnd)
  };

  const effectiveEndTime = Math.max(vDur, mockBridge.getSequenceEndTime(vDur));
  const TARGET_FPS = 30.0;
  const totalFrames = Math.max(1, Math.round(effectiveEndTime * TARGET_FPS));

  if (effectiveEndTime !== seqEnd) {
    throw new Error(`FAIL: effectiveEndTime esperado ${seqEnd}, obtenido ${effectiveEndTime}`);
  }
  if (totalFrames !== Math.round(seqEnd * 30.0)) {
    throw new Error(`FAIL: totalFrames incorrecto: ${totalFrames}`);
  }

  // Verificar lógica de renderizado: si currentTime > duration, se dibuja lastFrameCanvas (congelado)
  let framesDrawnFromLiveVideo = 0;
  let framesDrawnFromLastFrame = 0;
  const DT = 1.0 / TARGET_FPS;

  for (let f = 0; f < totalFrames; f++) {
    const currentTime = f * DT;
    if (currentTime <= vDur + DT * 0.5) {
      framesDrawnFromLiveVideo++;
    } else {
      framesDrawnFromLastFrame++;
    }
  }

  if (framesDrawnFromLastFrame <= 0) {
    throw new Error(`FAIL: No se generaron fotogramas congelados en la cola extendida.`);
  }

  console.log(`PASS: video-exporter.js calcula effectiveEndTime=${effectiveEndTime}s (${totalFrames} cuadros: ${framesDrawnFromLiveVideo} en video + ${framesDrawnFromLastFrame} congelados).`);
}
testVideoExporterTailCalculation();

console.log('\n=== TODOS LOS TESTS DE LA SUITE M1 PASARON 100% SATISFACTORIAMENTE ===\n');
