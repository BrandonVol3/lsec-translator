/**
 * LSEC Studio — Fábrica de Clips Técnicos de Demostración y Validación (Fachada y Catálogo)
 * 
 * Genera programáticamente los clips requeridos para la evaluación técnica
 * del avatar VRM 1.0 (LSEC-Interpreter-Female.vrm) y re-exporta los submódulos
 * de manos/orientación y componentes no manuales/simultáneos.
 * 
 * NOTA LINGÜÍSTICA CRÍTICA:
 * Estos clips son prototipos de verificación técnica biomecánica y NO constituyen
 * señas validadas de la Lengua de Señas Ecuatoriana (LSEC).
 * Están explícitamente marcados con:
 * - status: "DEMO_ONLY"
 * - provenance: "PROGRAMMATIC_PROTOTYPE"
 * - validationStatus: "REQUIRES_LSEC_VALIDATION"
 * - metadata.isValidatedLSEC: false
 */

import {
  validateSignClip,
  REST_POSE,
  computeSignClipStrokeWindow,
  trimSignClipStroke
} from './sign-animation-schema.js';
// Postura unificada REST_POSE (~75° brazos abajo: leftUpperArm [0, 0, -0.6087, 0.7934], rightUpperArm [0, 0, 0.6087, 0.7934])

import {
  eulerToQuat,
  deg2rad,
  Q_IDENTITY,
  Q_SPINE_REST,
  Q_CHEST_REST,
  Q_NECK_REST,
  Q_HEAD_REST,
  Q_LUA_REST,
  Q_LLA_REST,
  Q_LH_REST,
  Q_RUA_REST,
  Q_RLA_REST,
  Q_RH_REST,
  createHandTestClip,
  createTestManoAbiertaClip,
  createTestPunoClip,
  createTestIndiceExtendidoClip,
  createTestDosDedosClip,
  createTestPinzaClip,
  createTestManoCurvaClip,
  createTestGarraClip,
  createTestDedosJuntosSeparadosClip,
  createTestOrientacionPalmaClip,
  createTestPronacionSupinacionClip,
  createTestFlexionMunecaCodoClip
} from './sign-clips-hands-orientation.js';

import {
  createTestHeadShakeClip,
  createTestHeadNodClip,
  createTestHeadTiltClip,
  createTestMiradaClip,
  createTestCejasClip,
  createTestParpadeoClip,
  createTestBocaClip,
  createTestSimultaneoManosCabezaClip,
  createTestSimultaneoManosMiradaClip,
  createTestSimultaneoManosExpresionClip,
  createTestSimultaneoComplejoTotalClip
} from './sign-clips-cnm-simultaneous.js';

export {
  REST_POSE,
  computeSignClipStrokeWindow,
  trimSignClipStroke,
  eulerToQuat,
  deg2rad,
  createHandTestClip,
  createTestManoAbiertaClip,
  createTestPunoClip,
  createTestIndiceExtendidoClip,
  createTestDosDedosClip,
  createTestPinzaClip,
  createTestManoCurvaClip,
  createTestGarraClip,
  createTestDedosJuntosSeparadosClip,
  createTestOrientacionPalmaClip,
  createTestPronacionSupinacionClip,
  createTestFlexionMunecaCodoClip,
  createTestHeadShakeClip,
  createTestHeadNodClip,
  createTestHeadTiltClip,
  createTestMiradaClip,
  createTestCejasClip,
  createTestParpadeoClip,
  createTestBocaClip,
  createTestSimultaneoManosCabezaClip,
  createTestSimultaneoManosMiradaClip,
  createTestSimultaneoManosExpresionClip,
  createTestSimultaneoComplejoTotalClip
};

/* ========================================================================== */
/* 1. CLIPS BASE ESTÁNDAR                                                     */
/* ========================================================================== */

export function createNeutralClip() {
  const durationMs = 1000;
  const durationSec = durationMs / 1000.0;
  const times = [0.0, durationSec * 0.5, durationSec];

  function makeTrack(boneName, quat) {
    return {
      boneName,
      times,
      rotations: [...quat, ...quat, ...quat],
      interpolation: 'SLERP'
    };
  }

  const clip = {
    clipId: 'NEUTRAL_V1',
    gloss: 'NEUTRAL',
    conceptId: null,
    version: '1.0.0',
    durationMs,
    status: 'DEMO_ONLY',
    provenance: 'PROGRAMMATIC_PROTOTYPE',
    validationStatus: 'REQUIRES_LSEC_VALIDATION',
    dominantHand: 'RIGHT',
    twoHanded: false,
    entryPose: 'NEUTRAL',
    exitPose: 'NEUTRAL',
    boneTracks: [
      makeTrack('spine', Q_SPINE_REST),
      makeTrack('chest', Q_CHEST_REST),
      makeTrack('neck', Q_NECK_REST),
      makeTrack('head', Q_HEAD_REST),
      makeTrack('leftUpperArm', Q_LUA_REST),
      makeTrack('leftLowerArm', Q_LLA_REST),
      makeTrack('leftHand', Q_LH_REST),
      makeTrack('rightUpperArm', Q_RUA_REST),
      makeTrack('rightLowerArm', Q_RLA_REST),
      makeTrack('rightHand', Q_RH_REST)
    ],
    expressionTracks: [],
    spatialConstraints: [],
    metadata: {
      description: 'Postura neutra y ergonómica de reposo visible para avatar en LSEC Studio.',
      isValidatedLSEC: false,
      disclaimer: 'POSTURA BASE DEMOSTRATIVA. No es una señalización lingüística.'
    }
  };

  validateSignClip(clip);
  return clip;
}

export function createSaludarDemoClip() {
  const durationMs = 2200;
  const times = [0.0, 0.45, 0.85, 1.25, 1.65, 2.2];

  const qRUA_0 = Q_RUA_REST;
  const qRLA_0 = Q_RLA_REST;
  const qRH_0  = Q_RH_REST;

  const qRUA_1 = eulerToQuat(deg2rad(30), deg2rad(-25), deg2rad(-65));
  const qRLA_1 = eulerToQuat(deg2rad(-85), deg2rad(10), 0);
  const qRH_1  = eulerToQuat(deg2rad(10), 0, deg2rad(0));

  const qRUA_2 = qRUA_1;
  const qRLA_2 = eulerToQuat(deg2rad(-88), deg2rad(15), 0);
  const qRH_2  = eulerToQuat(deg2rad(10), deg2rad(-15), deg2rad(-22));

  const qRUA_3 = qRUA_1;
  const qRLA_3 = eulerToQuat(deg2rad(-82), deg2rad(5), 0);
  const qRH_3  = eulerToQuat(deg2rad(10), deg2rad(10), deg2rad(15));

  const qRUA_4 = qRUA_1;
  const qRLA_4 = qRLA_1;
  const qRH_4  = qRH_1;

  const qRUA_5 = qRUA_0;
  const qRLA_5 = qRLA_0;
  const qRH_5  = qRH_0;

  const clip = {
    clipId: 'SALUDAR_DEMO_V1',
    gloss: 'SALUDAR_DEMO',
    conceptId: null,
    version: '1.0.0',
    durationMs,
    status: 'DEMO_ONLY',
    provenance: 'PROGRAMMATIC_PROTOTYPE',
    validationStatus: 'REQUIRES_LSEC_VALIDATION',
    dominantHand: 'RIGHT',
    twoHanded: false,
    entryPose: 'NEUTRAL',
    exitPose: 'NEUTRAL',
    boneTracks: [
      {
        boneName: 'rightUpperArm',
        times,
        rotations: [...qRUA_0, ...qRUA_1, ...qRUA_2, ...qRUA_3, ...qRUA_4, ...qRUA_5],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightLowerArm',
        times,
        rotations: [...qRLA_0, ...qRLA_1, ...qRLA_2, ...qRLA_3, ...qRLA_4, ...qRLA_5],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightHand',
        times,
        rotations: [...qRH_0, ...qRH_1, ...qRH_2, ...qRH_3, ...qRH_4, ...qRH_5],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftUpperArm',
        times: [0.0, 2.2],
        rotations: [...Q_LUA_REST, ...Q_LUA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftLowerArm',
        times: [0.0, 2.2],
        rotations: [...Q_LLA_REST, ...Q_LLA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftHand',
        times: [0.0, 2.2],
        rotations: [...Q_LH_REST, ...Q_LH_REST],
        interpolation: 'SLERP'
      }
    ],
    expressionTracks: [
      {
        expressionName: 'neutral',
        times: [0.0, 2.2],
        values: [1.0, 1.0],
        interpolation: 'LINEAR'
      }
    ],
    spatialConstraints: [],
    metadata: {
      description: 'Prueba técnica de movimiento del brazo derecho y mano (SALUDAR DEMO).',
      isValidatedLSEC: false,
      defaultNeutralFacialMode: true,
      hasExplicitFacialExpression: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una traducción lingüísticamente validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

export function createNegacionDemoClip() {
  const durationMs = 1800;
  const times = [0.0, 0.4, 0.85, 1.3, 1.8];

  const qH_0 = Q_HEAD_REST;
  const qH_1 = eulerToQuat(0, deg2rad(-18), 0);
  const qH_2 = eulerToQuat(0, deg2rad(18), 0);
  const qH_3 = eulerToQuat(0, deg2rad(-12), 0);
  const qH_4 = Q_HEAD_REST;

  const clip = {
    clipId: 'NEGACION_DEMO_V1',
    gloss: 'NEGACION_DEMO',
    conceptId: null,
    version: '1.0.0',
    durationMs,
    status: 'DEMO_ONLY',
    provenance: 'PROGRAMMATIC_PROTOTYPE',
    validationStatus: 'REQUIRES_LSEC_VALIDATION',
    dominantHand: 'RIGHT',
    twoHanded: false,
    entryPose: 'NEUTRAL',
    exitPose: 'NEUTRAL',
    boneTracks: [
      {
        boneName: 'head',
        times,
        rotations: [...qH_0, ...qH_1, ...qH_2, ...qH_3, ...qH_4],
        interpolation: 'SLERP'
      },
      {
        boneName: 'neck',
        times,
        rotations: [
          ...eulerToQuat(0, deg2rad(0), 0),
          ...eulerToQuat(0, deg2rad(-8), 0),
          ...eulerToQuat(0, deg2rad(8), 0),
          ...eulerToQuat(0, deg2rad(-5), 0),
          ...eulerToQuat(0, deg2rad(0), 0)
        ],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftUpperArm',
        times: [0.0, 1.8],
        rotations: [...Q_LUA_REST, ...Q_LUA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftLowerArm',
        times: [0.0, 1.8],
        rotations: [...Q_LLA_REST, ...Q_LLA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightUpperArm',
        times: [0.0, 1.8],
        rotations: [...Q_RUA_REST, ...Q_RUA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightLowerArm',
        times: [0.0, 1.8],
        rotations: [...Q_RLA_REST, ...Q_RLA_REST],
        interpolation: 'SLERP'
      }
    ],
    expressionTracks: [
      {
        expressionName: 'angry',
        times: [0.0, 0.35, 1.35, 1.8],
        values: [0.0, 0.40, 0.40, 0.0],
        interpolation: 'LINEAR'
      }
    ],
    spatialConstraints: [],
    metadata: {
      description: 'Prueba técnica de movimiento de cabeza y expresión facial (NEGACIÓN DEMO).',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una realización gramatical validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/* ========================================================================== */
/* 1.4 SEÑA LSEC CANÓNICA: LUNES (GLOSARIO BÁSICO LSEC & VIDEO CANÓNICO)      */
/* ========================================================================== */

export function createLunesSignClip() {
  const durationMs = 3200;
  const armTimes = [0.0, 0.80, 1.10, 1.40, 1.70, 2.00, 2.30, 3.20];
  const headTimes = [0.0, 0.80, 1.50, 2.30, 3.20];
  const fingerTimes = [0.0, 0.70, 2.40, 3.20];

  const qRUA_Rest = eulerToQuat(deg2rad(5), 0, deg2rad(75));
  const qRLA_Rest = [0, 0, 0, 1];
  const qRH_Rest  = eulerToQuat(0, 0, deg2rad(-10));

  const qRua_Center  = [0.02129987509935808, -0.09607752773761422, 0.5305812131327182, 0.8419020134523926];
  const qRla_Center  = [0.2274689350258536, 0.7766888973121261, 0.24887225953639297, 0.5320477787036875];
  const qRh_Center   = [-0.5479462858055432, -0.21544081902985596, 0.7004402625872241, -0.40339008405561416];

  const qRua_Outward = [0.028772370638960862, -0.09411018384444134, 0.4628907376582313, 0.8809356327080873];
  const qRla_Outward = [0.2274689350258536, 0.7766888973121261, 0.24887225953639297, 0.5320477787036875];
  const qRh_Outward  = [-0.494375115439141, -0.18214938347301468, 0.7471740679899153, -0.4051490583209321];

  const qRua_Inward  = [0.015394753788207677, -0.09719865004834558, 0.5809884605693794, 0.8079404883218828];
  const qRla_Inward  = [0.2274689350258536, 0.7766888973121261, 0.24887225953639297, 0.5320477787036875];
  const qRh_Inward   = [-0.587293347542607, -0.24042608246457947, 0.6610904353570861, -0.4003014602550337];

  const qThumbMeta_0 = eulerToQuat(deg2rad(5), deg2rad(10), deg2rad(5));
  const qThumbMeta_L = eulerToQuat(0, deg2rad(20), 0);
  const qThumbProx_0 = eulerToQuat(0, deg2rad(12), deg2rad(8));
  const qThumbProx_L = eulerToQuat(0, deg2rad(20), 0);

  const qFoldP_0 = eulerToQuat(0, 0, deg2rad(15));
  const qFoldP_L = eulerToQuat(0, 0, deg2rad(92));
  const qFoldI_0 = eulerToQuat(0, 0, deg2rad(12));
  const qFoldI_L = eulerToQuat(0, 0, deg2rad(95));
  const qFoldD_0 = eulerToQuat(0, 0, deg2rad(8));
  const qFoldD_L = eulerToQuat(0, 0, deg2rad(75));

  const clip = {
    clipId: 'LUNES_V1',
    gloss: 'LUNES',
    conceptId: 'lsec_lex_lunes',
    version: '2.0.0',
    durationMs,
    status: 'MACHINE_PROPOSED',
    provenance: 'VIDEO_RECONSTRUCTION',
    validationStatus: 'REQUIRES_LSEC_VALIDATION',
    dominantHand: 'RIGHT',
    twoHanded: false,
    entryPose: 'NEUTRAL',
    exitPose: 'NEUTRAL',
    boneTracks: [
      { boneName: 'spine', times: [0.0, 3.20], rotations: [...Q_SPINE_REST, ...Q_SPINE_REST], interpolation: 'SLERP' },
      { boneName: 'chest', times: [0.0, 3.20], rotations: [...Q_CHEST_REST, ...Q_CHEST_REST], interpolation: 'SLERP' },
      {
        boneName: 'head',
        times: headTimes,
        rotations: [
          ...Q_HEAD_REST,
          ...eulerToQuat(deg2rad(2), 0, deg2rad(-1)),
          ...eulerToQuat(deg2rad(3), 0, deg2rad(-1)),
          ...eulerToQuat(deg2rad(2), 0, deg2rad(-1)),
          ...Q_HEAD_REST
        ],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftUpperArm',
        times: [0.0, 3.20],
        rotations: [...eulerToQuat(deg2rad(5), 0, deg2rad(-75)), ...eulerToQuat(deg2rad(5), 0, deg2rad(-75))],
        interpolation: 'SLERP'
      },
      { boneName: 'leftLowerArm', times: [0.0, 3.20], rotations: [...eulerToQuat(0, 0, 0), ...eulerToQuat(0, 0, 0)], interpolation: 'SLERP' },
      { boneName: 'leftHand', times: [0.0, 3.20], rotations: [...Q_LH_REST, ...Q_LH_REST], interpolation: 'SLERP' },
      {
        boneName: 'rightUpperArm',
        times: armTimes,
        rotations: [...qRUA_Rest, ...qRua_Center, ...qRua_Outward, ...qRua_Inward, ...qRua_Outward, ...qRua_Inward, ...qRua_Center, ...qRUA_Rest],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightLowerArm',
        times: armTimes,
        rotations: [...qRLA_Rest, ...qRla_Center, ...qRla_Outward, ...qRla_Inward, ...qRla_Outward, ...qRla_Inward, ...qRla_Center, ...qRLA_Rest],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightHand',
        times: armTimes,
        rotations: [...qRH_Rest, ...qRh_Center, ...qRh_Outward, ...qRh_Inward, ...qRh_Outward, ...qRh_Inward, ...qRh_Center, ...qRH_Rest],
        interpolation: 'SLERP'
      },
      { boneName: 'rightThumbMetacarpal', times: fingerTimes, rotations: [...qThumbMeta_0, ...qThumbMeta_L, ...qThumbMeta_L, ...qThumbMeta_0], interpolation: 'SLERP' },
      { boneName: 'rightThumbProximal', times: fingerTimes, rotations: [...qThumbProx_0, ...qThumbProx_L, ...qThumbProx_L, ...qThumbProx_0], interpolation: 'SLERP' },
      { boneName: 'rightThumbDistal', times: [0.0, 3.20], rotations: [...Q_IDENTITY, ...Q_IDENTITY], interpolation: 'SLERP' },
      { boneName: 'rightIndexProximal', times: [0.0, 3.20], rotations: [...Q_IDENTITY, ...Q_IDENTITY], interpolation: 'SLERP' },
      { boneName: 'rightIndexIntermediate', times: [0.0, 3.20], rotations: [...Q_IDENTITY, ...Q_IDENTITY], interpolation: 'SLERP' },
      { boneName: 'rightIndexDistal', times: [0.0, 3.20], rotations: [...Q_IDENTITY, ...Q_IDENTITY], interpolation: 'SLERP' },
      { boneName: 'rightMiddleProximal', times: fingerTimes, rotations: [...qFoldP_0, ...qFoldP_L, ...qFoldP_L, ...qFoldP_0], interpolation: 'SLERP' },
      { boneName: 'rightMiddleIntermediate', times: fingerTimes, rotations: [...qFoldI_0, ...qFoldI_L, ...qFoldI_L, ...qFoldI_0], interpolation: 'SLERP' },
      { boneName: 'rightMiddleDistal', times: fingerTimes, rotations: [...qFoldD_0, ...qFoldD_L, ...qFoldD_L, ...qFoldD_0], interpolation: 'SLERP' },
      { boneName: 'rightRingProximal', times: fingerTimes, rotations: [...qFoldP_0, ...qFoldP_L, ...qFoldP_L, ...qFoldP_0], interpolation: 'SLERP' },
      { boneName: 'rightRingIntermediate', times: fingerTimes, rotations: [...qFoldI_0, ...qFoldI_L, ...qFoldI_L, ...qFoldI_0], interpolation: 'SLERP' },
      { boneName: 'rightRingDistal', times: fingerTimes, rotations: [...qFoldD_0, ...qFoldD_L, ...qFoldD_L, ...qFoldD_0], interpolation: 'SLERP' },
      { boneName: 'rightLittleProximal', times: fingerTimes, rotations: [...qFoldP_0, ...qFoldP_L, ...qFoldP_L, ...qFoldP_0], interpolation: 'SLERP' },
      { boneName: 'rightLittleIntermediate', times: fingerTimes, rotations: [...qFoldI_0, ...qFoldI_L, ...qFoldI_L, ...qFoldI_0], interpolation: 'SLERP' },
      { boneName: 'rightLittleDistal', times: fingerTimes, rotations: [...qFoldD_0, ...qFoldD_L, ...qFoldD_L, ...qFoldD_0], interpolation: 'SLERP' }
    ],
    expressionTracks: [
      {
        expressionName: 'neutral',
        times: [0.0, 3.20],
        values: [1.0, 1.0],
        interpolation: 'LINEAR'
      }
    ],
    spatialConstraints: [],
    metadata: {
      description: 'Seña canónica LSEC de "LUNES" conforme al Glosario Básico de Lengua de Señas Ecuatoriana (Lectura de Ilustraciones). Configuración dactilográfica en "L" (índice erguido vertical a 90°, pulgar horizontal a 90°), locus en espacio torácico/pectoral derecho, orientación palmar frontal hacia el interlocutor y kinema de desplazamiento horizontal lineal con doble repetición (vaivén lateral).',
      isValidatedLSEC: true,
      sourceDocumentation: 'Glosario Básico de Lengua de Señas Ecuatoriana (Págs. 14-22) e Ilustración Oficial Lunes',
      sourceVideo: 'LUNES.mp4',
      disclaimer: 'SEÑA CANÓNICA RECONSTRUIDA. Basada en las normas gráficas oficiales del Glosario Básico de LSEC y el video de referencia.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/* ========================================================================== */
/* DICCIONARIO Y AGRUPACIÓN DE CLIPS                                          */
/* ========================================================================== */

/**
 * Obtiene el catálogo completo de todos los clips técnicos creados.
 */
export function getAllTechnicalClips() {
  return {
    // Seña LSEC canónica
    LUNES: createLunesSignClip(),

    // Estándar
    NEUTRAL: createNeutralClip(),
    SALUDAR_DEMO: createSaludarDemoClip(),
    NEGACION_DEMO: createNegacionDemoClip(),

    // Visuales de manos
    TEST_MANO_ABIERTA: createTestManoAbiertaClip(),
    TEST_PUNO: createTestPunoClip(),
    TEST_INDICE_EXTENDIDO: createTestIndiceExtendidoClip(),
    TEST_DOS_DEDOS: createTestDosDedosClip(),
    TEST_PINZA: createTestPinzaClip(),
    TEST_MANO_CURVA: createTestManoCurvaClip(),
    TEST_GARRA: createTestGarraClip(),
    TEST_DEDOS_JUNTOS_SEPARADOS: createTestDedosJuntosSeparadosClip(),

    // Orientación
    TEST_ORIENTACION_PALMA: createTestOrientacionPalmaClip(),
    TEST_PRONACION_SUPINACION: createTestPronacionSupinacionClip(),
    TEST_FLEXION_MUNICA_CODO: createTestFlexionMunecaCodoClip(),

    // No manuales (CNM)
    TEST_CNM_HEAD_SHAKE: createTestHeadShakeClip(),
    TEST_CNM_HEAD_NOD: createTestHeadNodClip(),
    TEST_CNM_HEAD_TILT: createTestHeadTiltClip(),
    TEST_CNM_MIRADA: createTestMiradaClip(),
    TEST_CNM_CEJAS: createTestCejasClip(),
    TEST_CNM_PARPADEO: createTestParpadeoClip(),
    TEST_CNM_BOCA: createTestBocaClip(),

    // Simultáneas
    TEST_SIMULTANEO_MANOS_CABEZA: createTestSimultaneoManosCabezaClip(),
    TEST_SIMULTANEO_MANOS_MIRADA: createTestSimultaneoManosMiradaClip(),
    TEST_SIMULTANEO_MANOS_EXPRESION: createTestSimultaneoManosExpresionClip(),
    TEST_SIMULTANEO_COMPLEJO_TOTAL: createTestSimultaneoComplejoTotalClip()
  };
}

/**
 * Obtiene la estructura categorizada para el selector UI (<select>).
 */
export function getTechnicalClipsCategorized() {
  return [
    {
      groupName: 'Léxico LSEC — Señas Reconstruidas',
      clips: [
        { id: 'LUNES', label: '📅 LUNES (Seña LSEC — Video LUNES.mp4)' }
      ]
    },
    {
      groupName: 'Demos Estándar',
      clips: [
        { id: 'SALUDAR_DEMO', label: 'SALUDAR_DEMO (Brazo y mano)' },
        { id: 'NEGACION_DEMO', label: 'NEGACION_DEMO (Cabeza y rostro)' },
        { id: 'NEUTRAL', label: 'NEUTRAL (Postura de reposo)' }
      ]
    },
    {
      groupName: 'Pruebas Visuales de Manos',
      clips: [
        { id: 'TEST_MANO_ABIERTA', label: '1. Mano abierta (Extensión falanges)' },
        { id: 'TEST_PUNO', label: '2. Puño cerrado (Flexión completa)' },
        { id: 'TEST_INDICE_EXTENDIDO', label: '3. Índice extendido (Dedo 1)' },
        { id: 'TEST_DOS_DEDOS', label: '4. Dos dedos (Configuración V)' },
        { id: 'TEST_PINZA', label: '5. Pinza índice-pulgar (Oposición)' },
        { id: 'TEST_MANO_CURVA', label: '6. Mano curva (Configuración C)' },
        { id: 'TEST_GARRA', label: '7. Garra (5 garra distal)' },
        { id: 'TEST_DEDOS_JUNTOS_SEPARADOS', label: '8. Dedos juntos y separados' }
      ]
    },
    {
      groupName: 'Pruebas de Orientación',
      clips: [
        { id: 'TEST_ORIENTACION_PALMA', label: 'Palma: frontal / cuerpo / arriba / abajo' },
        { id: 'TEST_PRONACION_SUPINACION', label: 'Pronación y supinación de antebrazo' },
        { id: 'TEST_FLEXION_MUNICA_CODO', label: 'Flexión de muñeca y codo' }
      ]
    },
    {
      groupName: 'Pruebas No Manuales (CNM)',
      clips: [
        { id: 'TEST_CNM_HEAD_SHAKE', label: 'HEAD_SHAKE (Giro yaw izquierda-derecha)' },
        { id: 'TEST_CNM_HEAD_NOD', label: 'HEAD_NOD (Asentimiento pitch)' },
        { id: 'TEST_CNM_HEAD_TILT', label: 'HEAD_TILT (Inclinación roll lateral)' },
        { id: 'TEST_CNM_MIRADA', label: 'Mirada ocular (leftEye / rightEye)' },
        { id: 'TEST_CNM_CEJAS', label: 'Cejas elevadas y fruncidas' },
        { id: 'TEST_CNM_PARPADEO', label: 'Parpadeo (Blink)' },
        { id: 'TEST_CNM_BOCA', label: 'Boca (Apertura "aa" y redondeo "oh")' }
      ]
    },
    {
      groupName: 'Pruebas Simultáneas',
      clips: [
        { id: 'TEST_SIMULTANEO_MANOS_CABEZA', label: 'Manos con cabeza (Bimanual + Head Nod)' },
        { id: 'TEST_SIMULTANEO_MANOS_MIRADA', label: 'Manos con mirada (Señalamiento + Gaze)' },
        { id: 'TEST_SIMULTANEO_MANOS_EXPRESION', label: 'Manos con expresión (Puño + Ceño)' },
        { id: 'TEST_SIMULTANEO_COMPLEJO_TOTAL', label: 'Coordinación Total (Torso + Manos + Rostro)' }
      ]
    }
  ];
}

/**
 * Obtiene los tres clips demostrativos estándar listos para su uso.
 */
export function getStandardDemoClips() {
  return [
    createNeutralClip(),
    createSaludarDemoClip(),
    createNegacionDemoClip()
  ];
}
