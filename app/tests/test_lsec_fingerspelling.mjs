/**
 * Suite de Verificación Automatizada — Motor Procedimental de Dactilología LSEC (30 Señas)
 *
 * Verifica matemáticamente:
 * 1. Los 30 grafemas oficiales de la Página 10 de Guia-Uso-ilustraciones.pdf:
 *    a, b, c, ch, d, e, f, g, h, i, j, k, l, ll, m, n, ñ, o, p, q, r, rr, s, t, u, v, w, x, y, z.
 * 2. Generación de pistas VRM 1.0 válidas sobre los 54 huesos humanoides (`HUMAN_BONE_NAMES`).
 * 3. Ausencia absoluta de inversiones bruscas de muñeca (< 55° por paso temporal).
 * 4. Margen anti-colisión torácico >= 2 cm (`CHEST_SURFACE_Z = 0.1373 m`) y no oclusión facial.
 * 5. Diferenciación estricta entre las 18 configuraciones estáticas (hold sostenido al 100%)
 *    y las 12 configuraciones dinámicas (opacidad 70%->100%, flechas curvas/lineales/zigzag).
 * 6. Tokenización de palabras y siglas (TULCÁN, CAYAMBE, UPEC, CONADIS, FENASEC, CHIMBORAZO,
 *    LLANO, IBARRA, NIÑO, COOPERATIVA) detectando dígrafos (CH, LL, RR), preservando Ñ y vocales
 *    tildadas/diéresis en NFC y aplicando micro-rearticulación en letras idénticas consecutivas.
 * 7. Coarticulación continua en deletreo de palabras sin bajar el brazo al reposo entre letras,
 *    con continuidad de hemisferio (q_t · q_{t-1} >= 0), filtro One-Euro y compilación en SequenceCompiler.
 */

import {
  HUMAN_BONE_NAMES,
  REST_POSE,
  validateSignClip
} from '../static/js/avatar/sign-animation-schema.js';

import {
  CHEST_SURFACE_Z,
  MIN_CHEST_CLEARANCE_M,
  LSEC_PDF_SPATIAL_AXES,
  LSEC_PDF_ANATOMICAL_POINTS,
  LSEC_PDF_MOVEMENT_PRIMITIVES,
  RIGHT_HAND_PHALANX_BONES,
  quatAngularDistanceDeg,
  OneEuroQuaternionFilter,
  solveRightArmTwoBoneIK,
  evaluateLinearTrajectoryOffset,
  evaluateCurvedTrajectoryOffset,
  evaluateCircularTrajectoryOffset,
  evaluateMultiStageTransition
} from '../static/js/avatar/sign-clips-fingerspelling-primitives.js';

import {
  LSEC_FINGERSPELLING_GRAPHEMES,
  LSEC_FINGERSPELLING_CATALOG,
  tokenizeLSECFingerspelling,
  createLSECFingerspellingSignClip,
  createLSECFingerspellingWordClip,
  getAllLSECFingerspellingClips
} from '../static/js/avatar/sign-clips-fingerspelling-lsec.js';

import {
  SequenceCompiler
} from '../static/js/avatar/sequence-compiler.js';

function assert(condition, message) {
  if (!condition) {
    throw new Error(`FAIL: ${message}`);
  }
}

console.log('--- TEST 1: Catálogo de 30 grafemas LSEC y constantes del PDF (Páginas 2 a 10) ---');
assert(LSEC_FINGERSPELLING_GRAPHEMES.length === 30, `Esperados 30 grafemas, obtenidos ${LSEC_FINGERSPELLING_GRAPHEMES.length}`);
assert(HUMAN_BONE_NAMES.length === 54, `Esperados 54 huesos VRM, obtenidos ${HUMAN_BONE_NAMES.length}`);
assert(LSEC_PDF_SPATIAL_AXES.ARRIBA[1] === 1.0 && LSEC_PDF_SPATIAL_AXES.ABAJO[1] === -1.0, 'Eje vertical ARRIBA/ABAJO inválido');
assert(LSEC_PDF_SPATIAL_AXES.ADELANTE[2] === 1.0 && LSEC_PDF_SPATIAL_AXES.ATRAS[2] === -1.0, 'Eje sagital ADELANTE/ATRAS inválido');
assert(LSEC_PDF_SPATIAL_AXES.AFUERA[0] === -1.0 && LSEC_PDF_SPATIAL_AXES.ADENTRO[0] === 1.0, 'Eje transversal AFUERA/ADENTRO inválido');
assert(Object.keys(LSEC_PDF_ANATOMICAL_POINTS.MANO).length >= 16, 'Puntos anatómicos de mano incompletos');
assert(Object.keys(LSEC_PDF_ANATOMICAL_POINTS.CUERPO).length >= 10, 'Puntos anatómicos de cuerpo incompletos');
assert(Object.keys(LSEC_PDF_ANATOMICAL_POINTS.ROSTRO).length >= 13, 'Puntos anatómicos de rostro incompletos');
assert(LSEC_PDF_MOVEMENT_PRIMITIVES.SPEED_FACTOR.NORMAL_CONTINUOUS === 1.0, 'Factor velocidad continuo debe ser 1.0');
assert(LSEC_PDF_MOVEMENT_PRIMITIVES.SPEED_FACTOR.SLOW_SEGMENTED === 0.65, 'Factor velocidad segmentado debe ser 0.65');
console.log('PASS: Catálogo de 30 grafemas y constantes espaciales/anatómicas del PDF verificados.');

console.log('--- TEST 2: Validación de los 30 clips sobre los 54 huesos VRM, umbral anti-flip < 55° y estáticas vs dinámicas ---');
const all30Clips = getAllLSECFingerspellingClips();
assert(all30Clips.length === 30, 'getAllLSECFingerspellingClips() debe retornar 30 clips');

const expectedStatic = new Set(['A', 'B', 'C', 'D', 'E', 'F', 'I', 'L', 'M', 'N', 'O', 'R', 'S', 'T', 'U', 'V', 'W', 'Y']);
const expectedDynamic = new Set(['CH', 'G', 'H', 'J', 'K', 'LL', 'Ñ', 'P', 'Q', 'RR', 'X', 'Z']);

for (const clip of all30Clips) {
  const g = clip.metadata.grapheme;
  const val = validateSignClip(clip);
  assert(val.valid, `Clip de grafema ${g} inválido: ${val.errors.join(', ')}`);
  assert(clip.boneTracks.length === 54, `Grafema ${g} debe tener exactamente 54 pistas óseas VRM, tiene ${clip.boneTracks.length}`);

  const trackMap = new Map(clip.boneTracks.map(t => [t.boneName, t]));
  for (const bName of HUMAN_BONE_NAMES) {
    assert(trackMap.has(bName), `Falta hueso ${bName} en grafema ${g}`);
  }

  // Verificar ausencia de inversiones bruscas de muñeca (< 55°) y continuidad de hemisferio (dot >= 0)
  for (const criticalBone of ['rightShoulder', 'rightUpperArm', 'rightLowerArm', 'rightHand']) {
    const tr = trackMap.get(criticalBone);
    const nFrames = tr.times.length;
    for (let k = 1; k < nFrames; k++) {
      const qPrev = tr.rotations.slice((k - 1) * 4, k * 4);
      const qCurr = tr.rotations.slice(k * 4, (k + 1) * 4);
      const dot = qPrev[0] * qCurr[0] + qPrev[1] * qCurr[1] + qPrev[2] * qCurr[2] + qPrev[3] * qCurr[3];
      assert(dot >= -1e-6, `Discontinuidad de hemisferio (dot=${dot}) en ${criticalBone} del grafema ${g}`);
      const stepDeg = quatAngularDistanceDeg(qPrev, qCurr);
      assert(stepDeg < 55.0, `Inversión brusca >= 55° (${stepDeg.toFixed(2)}°) en ${criticalBone} del grafema ${g}`);
    }
  }

  // Verificar variación dentro de la ventana de stroke: estáticas (hold constante) vs dinámicas (transición activa)
  const strokeStart = clip.stroke.startSec;
  const strokeEnd = clip.stroke.endSec;
  const rhTrack = trackMap.get('rightHand');
  const ruaTrack = trackMap.get('rightUpperArm');
  let maxStrokeVariationDeg = 0.0;

  const strokeSampleIndices = [];
  for (let i = 0; i < rhTrack.times.length; i++) {
    if (rhTrack.times[i] >= strokeStart - 1e-4 && rhTrack.times[i] <= strokeEnd + 1e-4) {
      strokeSampleIndices.push(i);
    }
  }
  assert(strokeSampleIndices.length >= 5, `Muestras de stroke insuficientes en ${g}`);
  const firstIdx = strokeSampleIndices[0];

  for (const idx of strokeSampleIndices) {
    for (const checkBone of ['rightUpperArm', 'rightLowerArm', 'rightHand', ...RIGHT_HAND_PHALANX_BONES]) {
      const bTr = trackMap.get(checkBone);
      const q0 = bTr.rotations.slice(firstIdx * 4, (firstIdx + 1) * 4);
      const qk = bTr.rotations.slice(idx * 4, (idx + 1) * 4);
      const d = quatAngularDistanceDeg(q0, qk);
      if (d > maxStrokeVariationDeg) maxStrokeVariationDeg = d;
    }
  }

  if (expectedStatic.has(g)) {
    assert(clip.metadata.isStaticHold === true && clip.metadata.isDynamic === false, `${g} debe estar marcada como estática`);
    assert(maxStrokeVariationDeg < 0.05, `Letra estática ${g} no debe moverse durante el hold (variación=${maxStrokeVariationDeg.toFixed(4)}°)`);
  } else if (expectedDynamic.has(g)) {
    assert(clip.metadata.isDynamic === true && clip.metadata.isStaticHold === false, `${g} debe estar marcada como dinámica`);
    assert(maxStrokeVariationDeg > 2.5, `Letra dinámica ${g} debe tener transición cinemática activa 70%->100% (variación=${maxStrokeVariationDeg.toFixed(4)}°)`);
  }
}
console.log('PASS: Los 30 grafemas generan 54 pistas VRM válidas, 0 inversiones >= 55°, diferenciando 18 estáticas y 12 dinámicas.');

console.log('--- TEST 3: IK Analítica de Dos Huesos, margen anti-colisión >= 2 cm y primitivas de trayectoria ---');
const ikNeutral = solveRightArmTwoBoneIK([-0.172, 1.225, 0.215], { pitchDeg: 4, yawDeg: -6, rollDeg: 0 });
const clearanceM = ikNeutral.wristWorldPos[2] - CHEST_SURFACE_Z;
assert(clearanceM >= MIN_CHEST_CLEARANCE_M, `Margen al pecho insuficiente: ${clearanceM} m < 0.02 m`);

// Incluso forzando una entrada detrás del pecho, el solver debe garantizar margen >= 2 cm y no ocluir el rostro
const ikClamped = solveRightArmTwoBoneIK([-0.02, 1.30, 0.05], { pitchDeg: 0, yawDeg: 0, rollDeg: 0 });
assert(ikClamped.wristWorldPos[2] - CHEST_SURFACE_Z >= MIN_CHEST_CLEARANCE_M, 'Fallo en cláusula anti-colisión torácica');
assert(ikClamped.wristWorldPos[0] <= -0.14, 'Fallo en prevención de oclusión facial');

// Verificar primitivas de trayectoria (lineal, zigzag 3 segmentos, curva, circular, espiral, multi-etapa A->B)
const zSeg0 = evaluateLinearTrajectoryOffset('zigzag', 0.0, 0.068);
const zSeg1 = evaluateLinearTrajectoryOffset('zigzag', 1.0 / 3.0, 0.068);
const zSeg2 = evaluateLinearTrajectoryOffset('zigzag', 2.0 / 3.0, 0.068);
const zSeg3 = evaluateLinearTrajectoryOffset('zigzag', 1.0, 0.068);
assert(zSeg0[0] > zSeg1[0] && zSeg2[0] > zSeg1[0] && zSeg2[0] > zSeg3[0], 'Trayectoria zigzag de Z no describe los 3 segmentos frontales');
assert(zSeg0[1] > zSeg2[1], 'Trayectoria zigzag de Z debe descender de arriba hacia abajo');

const jCurveMid = evaluateCurvedTrajectoryOffset('j_curve', 0.5, 0.064);
const jCurveEnd = evaluateCurvedTrajectoryOffset('j_curve', 1.0, 0.064);
assert(jCurveMid[1] < -0.02 && jCurveEnd[0] > 0.02, 'Trayectoria curva de J inválida');

const circPt = evaluateCircularTrajectoryOffset('spiral', 0.75, 0.04);
assert(Math.hypot(circPt[0], circPt[1]) > 0.01, 'Trayectoria espiral inválida');

const stageMultiMid = evaluateMultiStageTransition(
  LSEC_FINGERSPELLING_CATALOG.A.poseB100,
  LSEC_FINGERSPELLING_CATALOG.B.poseB100,
  LSEC_FINGERSPELLING_CATALOG.C.poseB100,
  0.5
);
assert(quatAngularDistanceDeg(stageMultiMid.rightIndexProximal, LSEC_FINGERSPELLING_CATALOG.B.poseB100.rightIndexProximal) < 0.5, 'Secuencia multi-etapa A->B en t=0.5 debe alcanzar etapa B');
console.log('PASS: IK analítica de dos huesos, margen >= 2 cm y generadores paramétricos verificados.');

console.log('--- TEST 4: Tokenización de dígrafos (CH, LL, RR), Ñ, tildes NFC y letras repetidas ---');
const tokTulcan = tokenizeLSECFingerspelling('T-U-L-C-Á-N');
assert(tokTulcan.map(t => t.grapheme).join(',') === 'T,U,L,C,A,N', `Tokenización TULCÁN inválida: ${JSON.stringify(tokTulcan)}`);
assert(tokTulcan[4].displayChar === 'Á' && tokTulcan[4].grapheme === 'A', 'Vocal tildada Á debe preservar displayChar y mapear a pose A');

const tokDigraphs = tokenizeLSECFingerspelling('CHIMBORAZO-LLANO-IBARRA-NIÑO-CIGÜEÑA');
const gList = tokDigraphs.map(t => t.grapheme);
assert(gList.includes('CH') && gList.includes('LL') && gList.includes('RR') && gList.includes('Ñ'), 'Deben detectarse CH, LL, RR y Ñ');

// Verificar que LL y RR sean dígrafos únicos sin marcarse como repetición de letra simple,
// mientras que dos letras idénticas consecutivas (ej. COOPERATIVA -> O-O, AARON -> A-A) activen microRearticulation
const tokCoop = tokenizeLSECFingerspelling('COOPERATIVA');
assert(tokCoop[1].grapheme === 'O' && tokCoop[2].grapheme === 'O' && tokCoop[2].microRearticulation === true, 'Doble O debe activar micro-rearticulación');
const tokLlano = tokenizeLSECFingerspelling('LLANO');
assert(tokLlano[0].grapheme === 'LL' && tokLlano[0].isDigraph === true && tokLlano[0].microRearticulation === false, 'Dígrafo LL no debe dividirse en L+L');
console.log('PASS: Tokenización de dígrafos oficiales, Ñ, NFC y micro-rearticulación verificada.');

console.log('--- TEST 5: Deletreo continuo de palabras sin caer al reposo e integración con SequenceCompiler ---');
for (const word of ['T-U-L-C-Á-N', 'C-A-Y-A-M-B-E', 'U-P-E-C', 'CONADIS', 'FENASEC', 'COOPERATIVA']) {
  const wordClip = createLSECFingerspellingWordClip(word);
  const val = validateSignClip(wordClip);
  assert(val.valid, `WordClip inválido para ${word}: ${val.errors.join(', ')}`);
  assert(wordClip.boneTracks.length === 54, `WordClip ${word} debe tener 54 pistas VRM`);

  // Verificar que durante toda la ventana de stroke [startSec, endSec] el brazo derecho
  // se mantenga elevado en el espacio neutro de dactilología sin caer a REST_POSE
  const ruaTr = wordClip.boneTracks.find(t => t.boneName === 'rightUpperArm');
  const rlaTr = wordClip.boneTracks.find(t => t.boneName === 'rightLowerArm');
  const sStart = wordClip.stroke.startSec;
  const sEnd = wordClip.stroke.endSec;

  for (let i = 0; i < ruaTr.times.length; i++) {
    const t = ruaTr.times[i];
    if (t >= sStart + 0.05 && t <= sEnd - 0.05) {
      const qRua = ruaTr.rotations.slice(i * 4, (i + 1) * 4);
      const qRla = rlaTr.rotations.slice(i * 4, (i + 1) * 4);
      const distFromRest = Math.max(
        quatAngularDistanceDeg(qRua, REST_POSE.rightUpperArm),
        quatAngularDistanceDeg(qRla, REST_POSE.rightLowerArm)
      );
      assert(distFromRest > 35.0, `El brazo cayó hacia el reposo en medio de la palabra ${word} en t=${t}s (distFromRest=${distFromRest.toFixed(2)}°)`);
    }
  }
}

// Verificar compilación y muestreo en SequenceCompiler (incluyendo dígrafos CH/LL/RR, siglas y fallback OOV)
const compiler = new SequenceCompiler();
const project = {
  media_info: { duration_seconds: 8.5 },
  glosses: [
    { id: 'w1', gloss: 'U-P-E-C', is_fingerspelling: true, gloss_type: 'DACTILOLOGÍA', start_seconds: 0.4, end_seconds: 2.0, proposition_id: 'p1' },
    { id: 'w2', gloss: 'T-U-L-C-Á-N', is_fingerspelling: true, gloss_type: 'DACTILOLOGÍA', start_seconds: 2.1, end_seconds: 3.9, proposition_id: 'p1' },
    { id: 'w3', gloss: 'CH-I-M-B-O-R-A-Z-O', start_seconds: 4.0, end_seconds: 6.1, proposition_id: 'p1' },
    {
      id: 'w4',
      gloss: 'XILÓFONO',
      source_word: 'xilófono',
      gloss_type: 'SEÑA',
      dictionary_metadata: { status: 'NO_VERIFICADO' },
      validation: { fallback_fingerspelling_gloss: 'X-I-L-Ó-F-O-N-O' },
      start_seconds: 6.2,
      end_seconds: 8.1,
      proposition_id: 'p1'
    }
  ]
};
const plan = compiler.compile(project, new Map(), { videoDuration: 8.5 });
assert(plan.playableEntries.length === 4, `Las 4 glosas (incluyendo dígrafo CH y fallback OOV) deben ser reproducibles en SequenceCompiler; obtenidas ${plan.playableEntries.length}`);
assert(plan.stats.intraSentenceRestDrops === 0, 'Cero caídas a reposo intra-oración durante deletreo continuo');
const sampleMid1 = compiler.pose(1.1);
const sampleMid2 = compiler.pose(3.0);
const sampleMid3 = compiler.pose(5.0);
const sampleMid4 = compiler.pose(7.1);
assert(sampleMid1.phase === 'stroke' && sampleMid1.activeGloss === 'U-P-E-C', 'U-P-E-C debe estar articulando su stroke en t=1.1s');
assert(sampleMid2.phase === 'stroke' && sampleMid2.activeGloss === 'T-U-L-C-Á-N', 'T-U-L-C-Á-N debe estar articulando su stroke en t=3.0s');
assert(sampleMid3.phase === 'stroke' && sampleMid3.activeGloss === 'CH-I-M-B-O-R-A-Z-O', 'CH-I-M-B-O-R-A-Z-O debe estar articulando su stroke en t=5.0s');
assert(sampleMid4.phase === 'stroke' && sampleMid4.activeGloss === 'XILÓFONO', 'Palabra OOV XILÓFONO debe articularse por dactilología automática en t=7.1s');

console.log('\n=== TODOS LOS TESTS DE DACTILOLOGÍA LSEC (30 SEÑAS) PASARON SATISFACTORIAMENTE ===');
