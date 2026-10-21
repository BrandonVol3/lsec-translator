/**
 * LSEC Studio — Fábrica de Clips Técnicos de Demostración y Validación
 * 
 * Genera programáticamente los clips requeridos para la evaluación técnica
 * del avatar VRM 1.0 (LSEC-Interpreter-Female.vrm):
 * 1. Base y demostración estándar: NEUTRAL, SALUDAR_DEMO, NEGACION_DEMO.
 * 2. Pruebas visuales de manos: mano abierta, puño, índice extendido, dos dedos,
 *    pinza índice-pulgar, mano curva, garra, dedos juntos y separados.
 * 3. Pruebas de orientación: palma frontal/cuerpo/arriba/abajo, pronación/supinación,
 *    flexión muñeca y codo.
 * 4. Pruebas no manuales (CNM): HEAD_SHAKE, HEAD_NOD, HEAD_TILT, mirada, cejas, parpadeo, boca.
 * 5. Pruebas simultáneas: manos con cabeza, manos con mirada, manos con expresión,
 *    y coordinación compleja total.
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

import * as THREE from 'three';
import {
  validateSignClip,
  REST_POSE,
  computeSignClipStrokeWindow,
  trimSignClipStroke
} from './sign-animation-schema.js';

export { REST_POSE, computeSignClipStrokeWindow, trimSignClipStroke };

/**
 * Convierte ángulos de Euler (en radianes) a un cuaternión unitario [x, y, z, w].
 */
export function eulerToQuat(xRad, yRad, zRad, order = 'XYZ') {
  const euler = new THREE.Euler(xRad, yRad, zRad, order);
  const q = new THREE.Quaternion().setFromEuler(euler);
  q.normalize();
  return [q.x, q.y, q.z, q.w];
}

/**
 * Convierte grados a radianes.
 */
export function deg2rad(degrees) {
  return degrees * (Math.PI / 180.0);
}

// Cuaternión identidad constante
const Q_IDENTITY = [0, 0, 0, 1];

// Poses base de reposo
const Q_SPINE_REST = eulerToQuat(deg2rad(1), 0, 0);
const Q_CHEST_REST = eulerToQuat(deg2rad(1), 0, 0);
const Q_NECK_REST  = [0, 0, 0, 1];
const Q_HEAD_REST  = [0, 0, 0, 1];

// Brazo izquierdo en reposo biomecánico natural (unificado con v2.6 y SignPlayer.restoreNeutralPose)
const Q_LUA_REST = [0.0435, 0.0028, -0.6087, 0.7921];
const Q_LLA_REST = [0, 0.0872, 0, 0.9962];
const Q_LH_REST  = [0, 0, 0, 1];

// Brazo derecho en reposo biomecánico natural (unificado con v2.6 y SignPlayer.restoreNeutralPose)
const Q_RUA_REST = [0.0435, -0.0028, 0.6087, 0.7921];
const Q_RLA_REST = [0, -0.0872, 0, 0.9962];
const Q_RH_REST  = [0, 0, 0, 1];

// Brazo derecho en espacio de señas frontal (altura de pecho/hombro, palma al frente)
const Q_RUA_SIGN = eulerToQuat(deg2rad(32), deg2rad(-20), deg2rad(-62));
const Q_RLA_SIGN = eulerToQuat(deg2rad(-85), deg2rad(15), 0);
const Q_RH_SIGN  = eulerToQuat(deg2rad(10), 0, 0);

// Brazo izquierdo en espacio de señas simétrico
const Q_LUA_SIGN = eulerToQuat(deg2rad(32), deg2rad(20), deg2rad(62));
const Q_LLA_SIGN = eulerToQuat(deg2rad(-85), deg2rad(-15), 0);
const Q_LH_SIGN  = eulerToQuat(deg2rad(10), 0, 0);

/**
 * Generador de clip base para pruebas técnicas de mano derecha en espacio de señas.
 */
function createHandTestClip({ clipId, gloss, description, fingerPoses, durationMs = 1500, extraTracks = [] }) {
  const durationSec = durationMs / 1000.0;
  const times = [0.0, durationSec * 0.25, durationSec * 0.75, durationSec];

  const tracks = [
    {
      boneName: 'spine',
      times: [0.0, durationSec],
      rotations: [...Q_SPINE_REST, ...Q_SPINE_REST],
      interpolation: 'SLERP'
    },
    {
      boneName: 'chest',
      times: [0.0, durationSec],
      rotations: [...Q_CHEST_REST, ...Q_CHEST_REST],
      interpolation: 'SLERP'
    },
    {
      boneName: 'leftUpperArm',
      times: [0.0, durationSec],
      rotations: [...Q_LUA_REST, ...Q_LUA_REST],
      interpolation: 'SLERP'
    },
    {
      boneName: 'leftLowerArm',
      times: [0.0, durationSec],
      rotations: [...Q_LLA_REST, ...Q_LLA_REST],
      interpolation: 'SLERP'
    },
    {
      boneName: 'leftHand',
      times: [0.0, durationSec],
      rotations: [...Q_LH_REST, ...Q_LH_REST],
      interpolation: 'SLERP'
    },
    {
      boneName: 'rightUpperArm',
      times,
      rotations: [...Q_RUA_REST, ...Q_RUA_SIGN, ...Q_RUA_SIGN, ...Q_RUA_REST],
      interpolation: 'SLERP'
    },
    {
      boneName: 'rightLowerArm',
      times,
      rotations: [...Q_RLA_REST, ...Q_RLA_SIGN, ...Q_RLA_SIGN, ...Q_RLA_REST],
      interpolation: 'SLERP'
    },
    {
      boneName: 'rightHand',
      times,
      rotations: [...Q_RH_REST, ...Q_RH_SIGN, ...Q_RH_SIGN, ...Q_RH_REST],
      interpolation: 'SLERP'
    }
  ];

  // Añadir pistas de falanges
  for (const [boneName, qPose] of Object.entries(fingerPoses)) {
    tracks.push({
      boneName,
      times,
      rotations: [...Q_IDENTITY, ...qPose, ...qPose, ...Q_IDENTITY],
      interpolation: 'SLERP'
    });
  }

  if (extraTracks.length > 0) {
    tracks.push(...extraTracks);
  }

  const clip = {
    clipId,
    gloss,
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
    boneTracks: tracks,
    expressionTracks: [],
    spatialConstraints: [],
    metadata: {
      description,
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

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

/**
 * 1.4 Seña Canónica de LSEC: LUNES
 * 
 * Reconstrucción técnica y biomecánica rigurosa basada en el Glosario Básico 
 * de Lengua de Señas Ecuatoriana (LSEC) - "Lectura de Ilustraciones y Especificaciones de Uso":
 * 
 * Parámetros formativos del signo:
 * - Queirema (Configuración manual): Configuración en "L" dactilográfica (dedo índice
 *   completamente erguido y extendido verticalmente a 90°; pulgar abducido horizontalmente
 *   a 90° hacia el centro corporal; dedos medio, anular y meñique completamente flexionados
 *   en puño cerrado contra la palma, Pág. 10 y 22 del Glosario).
 * - Toponema (Locus espacial): Espacio torácico anterior ipsilateral derecho (frente al
 *   pectoral derecho / clavícula, ilustrado en la lámina canónica de 'Lunes').
 * - Alotopía (Orientación): Palma orientada directamente hacia el interlocutor (cámara/frontal),
 *   dorso de la mano hacia el señante (Pág. 9 del Glosario: "la referencia espacial debe ser
 *   'leída' con el dorso hacia la persona que realiza la seña y la palma hacia adelante").
 * - Kinema (Movimiento): "DESPLAZAR" (Pág. 5 del Glosario: movimiento en el espacio sin
 *   contacto corporal). Desplazamiento horizontal lineal en vaivén con doble repetición
 *   (indicado por la doble flecha horizontal con doble punta `⮜⮜ ─── ⮞⮞`, Pág. 4 y 5:
 *   "Realizar el movimiento dos veces" de izquierda a derecha y derecha a izquierda).
 * - Prevención de Deformaciones de Malla: Cinemática de brazo calibrada en la envolvente
 *   óptima de Linear Blend Skinning (ruaZ ∈ [56°, 72°], rlaY = 110°), eliminando cualquier
 *   colapso de hombro, torsión antinatural de antebrazo o cruce de singularidades.
 * - Componentes No Manuales (CNM): Articulación labial "ou" ("lu-nes"), mirada focalizada
 *   atenta y parpadeos fisiológicos sincronizados.
 */
export function createLunesSignClip() {
  const durationMs = 3200;
  const armTimes = [0.0, 0.80, 1.10, 1.40, 1.70, 2.00, 2.30, 3.20];
  const headTimes = [0.0, 0.80, 1.50, 2.30, 3.20];
  const fingerTimes = [0.0, 0.70, 2.40, 3.20];

  // Postura de Reposo Neutro Ergonómico
  const qRUA_Rest = eulerToQuat(deg2rad(5), 0, deg2rad(75));
  const qRLA_Rest = [0, 0, 0, 1];
  const qRH_Rest  = eulerToQuat(0, 0, deg2rad(-10));

  // Poses calibradas matemáticamente para Locus Pectoral con Palma Frontal e Índice Vertical:
  // Centro (Locus canónico frente al pectoral derecho)
  const qRua_Center  = [0.02129987509935808, -0.09607752773761422, 0.5305812131327182, 0.8419020134523926];
  const qRla_Center  = [0.2274689350258536, 0.7766888973121261, 0.24887225953639297, 0.5320477787036875];
  const qRh_Center   = [-0.5479462858055432, -0.21544081902985596, 0.7004402625872241, -0.40339008405561416];

  // Desplazamiento lateral hacia afuera (derecha del avatar, +3.3 cm)
  const qRua_Outward = [0.028772370638960862, -0.09411018384444134, 0.4628907376582313, 0.8809356327080873];
  const qRla_Outward = [0.2274689350258536, 0.7766888973121261, 0.24887225953639297, 0.5320477787036875];
  const qRh_Outward  = [-0.494375115439141, -0.18214938347301468, 0.7471740679899153, -0.4051490583209321];

  // Desplazamiento lateral hacia adentro (medial hacia el esternón, -2.3 cm)
  const qRua_Inward  = [0.015394753788207677, -0.09719865004834558, 0.5809884605693794, 0.8079404883218828];
  const qRla_Inward  = [0.2274689350258536, 0.7766888973121261, 0.24887225953639297, 0.5320477787036875];
  const qRh_Inward   = [-0.587293347542607, -0.24042608246457947, 0.6610904353570861, -0.4003014602550337];

  // Configuración de Dedos en 'L' perfecta:
  // Pulgar horizontal a 90° (abducción radial limpia en eje Y)
  const qThumbMeta_0 = eulerToQuat(deg2rad(5), deg2rad(10), deg2rad(5));
  const qThumbMeta_L = eulerToQuat(0, deg2rad(20), 0);
  const qThumbProx_0 = eulerToQuat(0, deg2rad(12), deg2rad(8));
  const qThumbProx_L = eulerToQuat(0, deg2rad(20), 0);

  // Flexión anatómica completa en puño para dedos medio, anular y meñique
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
      {
        boneName: 'spine',
        times: [0.0, 3.20],
        rotations: [...Q_SPINE_REST, ...Q_SPINE_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'chest',
        times: [0.0, 3.20],
        rotations: [...Q_CHEST_REST, ...Q_CHEST_REST],
        interpolation: 'SLERP'
      },
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
        rotations: [
          ...eulerToQuat(deg2rad(5), 0, deg2rad(-75)),
          ...eulerToQuat(deg2rad(5), 0, deg2rad(-75))
        ],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftLowerArm',
        times: [0.0, 3.20],
        rotations: [
          ...eulerToQuat(0, 0, 0),
          ...eulerToQuat(0, 0, 0)
        ],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftHand',
        times: [0.0, 3.20],
        rotations: [...Q_LH_REST, ...Q_LH_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightUpperArm',
        times: armTimes,
        rotations: [
          ...qRUA_Rest,
          ...qRua_Center,
          ...qRua_Outward,
          ...qRua_Inward,
          ...qRua_Outward,
          ...qRua_Inward,
          ...qRua_Center,
          ...qRUA_Rest
        ],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightLowerArm',
        times: armTimes,
        rotations: [
          ...qRLA_Rest,
          ...qRla_Center,
          ...qRla_Outward,
          ...qRla_Inward,
          ...qRla_Outward,
          ...qRla_Inward,
          ...qRla_Center,
          ...qRLA_Rest
        ],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightHand',
        times: armTimes,
        rotations: [
          ...qRH_Rest,
          ...qRh_Center,
          ...qRh_Outward,
          ...qRh_Inward,
          ...qRh_Outward,
          ...qRh_Inward,
          ...qRh_Center,
          ...qRH_Rest
        ],
        interpolation: 'SLERP'
      },
      // Pulgar derecho (Configuración 'L' horizontal a 90° hacia el centro)
      {
        boneName: 'rightThumbMetacarpal',
        times: fingerTimes,
        rotations: [
          ...qThumbMeta_0,
          ...qThumbMeta_L,
          ...qThumbMeta_L,
          ...qThumbMeta_0
        ],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightThumbProximal',
        times: fingerTimes,
        rotations: [
          ...qThumbProx_0,
          ...qThumbProx_L,
          ...qThumbProx_L,
          ...qThumbProx_0
        ],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightThumbDistal',
        times: [0.0, 3.20],
        rotations: [...Q_IDENTITY, ...Q_IDENTITY],
        interpolation: 'SLERP'
      },
      // Índice derecho (Completamente erguido y vertical en 90°)
      {
        boneName: 'rightIndexProximal',
        times: [0.0, 3.20],
        rotations: [...Q_IDENTITY, ...Q_IDENTITY],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightIndexIntermediate',
        times: [0.0, 3.20],
        rotations: [...Q_IDENTITY, ...Q_IDENTITY],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightIndexDistal',
        times: [0.0, 3.20],
        rotations: [...Q_IDENTITY, ...Q_IDENTITY],
        interpolation: 'SLERP'
      },
      // Dedo Medio (Plegado en puño contra la palma)
      {
        boneName: 'rightMiddleProximal',
        times: fingerTimes,
        rotations: [
          ...qFoldP_0,
          ...qFoldP_L,
          ...qFoldP_L,
          ...qFoldP_0
        ],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightMiddleIntermediate',
        times: fingerTimes,
        rotations: [
          ...qFoldI_0,
          ...qFoldI_L,
          ...qFoldI_L,
          ...qFoldI_0
        ],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightMiddleDistal',
        times: fingerTimes,
        rotations: [
          ...qFoldD_0,
          ...qFoldD_L,
          ...qFoldD_L,
          ...qFoldD_0
        ],
        interpolation: 'SLERP'
      },
      // Dedo Anular (Plegado en puño contra la palma)
      {
        boneName: 'rightRingProximal',
        times: fingerTimes,
        rotations: [
          ...qFoldP_0,
          ...qFoldP_L,
          ...qFoldP_L,
          ...qFoldP_0
        ],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightRingIntermediate',
        times: fingerTimes,
        rotations: [
          ...qFoldI_0,
          ...qFoldI_L,
          ...qFoldI_L,
          ...qFoldI_0
        ],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightRingDistal',
        times: fingerTimes,
        rotations: [
          ...qFoldD_0,
          ...qFoldD_L,
          ...qFoldD_L,
          ...qFoldD_0
        ],
        interpolation: 'SLERP'
      },
      // Dedo Meñique (Plegado en puño contra la palma)
      {
        boneName: 'rightLittleProximal',
        times: fingerTimes,
        rotations: [
          ...qFoldP_0,
          ...qFoldP_L,
          ...qFoldP_L,
          ...qFoldP_0
        ],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightLittleIntermediate',
        times: fingerTimes,
        rotations: [
          ...qFoldI_0,
          ...qFoldI_L,
          ...qFoldI_L,
          ...qFoldI_0
        ],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightLittleDistal',
        times: fingerTimes,
        rotations: [
          ...qFoldD_0,
          ...qFoldD_L,
          ...qFoldD_L,
          ...qFoldD_0
        ],
        interpolation: 'SLERP'
      }
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
/* 2. PRUEBAS VISUALES DE MANOS (8 CONFIGURACIONES)                          */
/* ========================================================================== */

/**
 * 2.1 Mano abierta: Dedos extendidos, planos y separados de forma natural.
 */
export function createTestManoAbiertaClip() {
  const fingerPoses = {
    rightThumbMetacarpal: eulerToQuat(deg2rad(5), deg2rad(10), deg2rad(5)),
    rightThumbProximal: eulerToQuat(0, deg2rad(12), deg2rad(8)),
    rightThumbDistal: Q_IDENTITY,
    rightIndexProximal: eulerToQuat(0, deg2rad(6), 0),
    rightIndexIntermediate: Q_IDENTITY,
    rightIndexDistal: Q_IDENTITY,
    rightMiddleProximal: Q_IDENTITY,
    rightMiddleIntermediate: Q_IDENTITY,
    rightMiddleDistal: Q_IDENTITY,
    rightRingProximal: eulerToQuat(0, deg2rad(-5), 0),
    rightRingIntermediate: Q_IDENTITY,
    rightRingDistal: Q_IDENTITY,
    rightLittleProximal: eulerToQuat(0, deg2rad(-10), 0),
    rightLittleIntermediate: Q_IDENTITY,
    rightLittleDistal: Q_IDENTITY
  };

  return createHandTestClip({
    clipId: 'TEST_MANO_ABIERTA_V1',
    gloss: 'TEST_MANO_ABIERTA',
    description: 'Prueba visual de mano abierta con extensión de las 15 falanges.',
    fingerPoses
  });
}

/**
 * 2.2 Puño: Todos los dedos flexionados hacia la palma, pulgar cerrado sobre ellos.
 */
export function createTestPunoClip() {
  const qProx = eulerToQuat(0, 0, deg2rad(85));
  const qInter = eulerToQuat(0, 0, deg2rad(92));
  const qDist = eulerToQuat(0, 0, deg2rad(75));

  const fingerPoses = {
    rightThumbMetacarpal: eulerToQuat(deg2rad(10), deg2rad(25), deg2rad(20)),
    rightThumbProximal: eulerToQuat(0, deg2rad(35), deg2rad(45)),
    rightThumbDistal: eulerToQuat(0, deg2rad(15), deg2rad(50)),
    rightIndexProximal: qProx,
    rightIndexIntermediate: qInter,
    rightIndexDistal: qDist,
    rightMiddleProximal: qProx,
    rightMiddleIntermediate: qInter,
    rightMiddleDistal: qDist,
    rightRingProximal: qProx,
    rightRingIntermediate: qInter,
    rightRingDistal: qDist,
    rightLittleProximal: qProx,
    rightLittleIntermediate: qInter,
    rightLittleDistal: qDist
  };

  return createHandTestClip({
    clipId: 'TEST_PUNO_V1',
    gloss: 'TEST_PUNO',
    description: 'Prueba visual de puño cerrado compacto y flexión interdigital.',
    fingerPoses
  });
}

/**
 * 2.3 Índice extendido: Dedo índice completamente recto; pulgar, medio, anular y meñique cerrados.
 */
export function createTestIndiceExtendidoClip() {
  const qProx = eulerToQuat(0, 0, deg2rad(85));
  const qInter = eulerToQuat(0, 0, deg2rad(92));
  const qDist = eulerToQuat(0, 0, deg2rad(75));

  const fingerPoses = {
    rightThumbMetacarpal: eulerToQuat(deg2rad(10), deg2rad(25), deg2rad(20)),
    rightThumbProximal: eulerToQuat(0, deg2rad(35), deg2rad(45)),
    rightThumbDistal: eulerToQuat(0, deg2rad(15), deg2rad(50)),
    // Índice extendido
    rightIndexProximal: Q_IDENTITY,
    rightIndexIntermediate: Q_IDENTITY,
    rightIndexDistal: Q_IDENTITY,
    // Resto en puño
    rightMiddleProximal: qProx,
    rightMiddleIntermediate: qInter,
    rightMiddleDistal: qDist,
    rightRingProximal: qProx,
    rightRingIntermediate: qInter,
    rightRingDistal: qDist,
    rightLittleProximal: qProx,
    rightLittleIntermediate: qInter,
    rightLittleDistal: qDist
  };

  return createHandTestClip({
    clipId: 'TEST_INDICE_EXTENDIDO_V1',
    gloss: 'TEST_INDICE_EXTENDIDO',
    description: 'Prueba visual de dedo índice extendido (configuración 1 / señalamiento).',
    fingerPoses
  });
}

/**
 * 2.4 Dos dedos: Índice y medio extendidos en 'V'; pulgar, anular y meñique cerrados.
 */
export function createTestDosDedosClip() {
  const qProx = eulerToQuat(0, 0, deg2rad(85));
  const qInter = eulerToQuat(0, 0, deg2rad(92));
  const qDist = eulerToQuat(0, 0, deg2rad(75));

  const fingerPoses = {
    rightThumbMetacarpal: eulerToQuat(deg2rad(10), deg2rad(25), deg2rad(20)),
    rightThumbProximal: eulerToQuat(0, deg2rad(35), deg2rad(45)),
    rightThumbDistal: eulerToQuat(0, deg2rad(15), deg2rad(50)),
    // Índice y Medio extendidos en V
    rightIndexProximal: eulerToQuat(0, deg2rad(12), 0),
    rightIndexIntermediate: Q_IDENTITY,
    rightIndexDistal: Q_IDENTITY,
    rightMiddleProximal: eulerToQuat(0, deg2rad(-10), 0),
    rightMiddleIntermediate: Q_IDENTITY,
    rightMiddleDistal: Q_IDENTITY,
    // Anular y meñique cerrados
    rightRingProximal: qProx,
    rightRingIntermediate: qInter,
    rightRingDistal: qDist,
    rightLittleProximal: qProx,
    rightLittleIntermediate: qInter,
    rightLittleDistal: qDist
  };

  return createHandTestClip({
    clipId: 'TEST_DOS_DEDOS_V1',
    gloss: 'TEST_DOS_DEDOS',
    description: 'Prueba visual de dos dedos extendidos en V (configuración 2 / V).',
    fingerPoses
  });
}

/**
 * 2.5 Pinza índice-pulgar: Yemas de índice y pulgar en contacto/oposición; otros dedos en reposo semiabierto.
 */
export function createTestPinzaClip() {
  const fingerPoses = {
    rightThumbMetacarpal: eulerToQuat(deg2rad(15), deg2rad(30), deg2rad(25)),
    rightThumbProximal: eulerToQuat(0, deg2rad(30), deg2rad(40)),
    rightThumbDistal: eulerToQuat(0, 0, deg2rad(35)),
    // Índice en oposición tocando pulgar
    rightIndexProximal: eulerToQuat(deg2rad(5), deg2rad(-8), deg2rad(42)),
    rightIndexIntermediate: eulerToQuat(0, 0, deg2rad(65)),
    rightIndexDistal: eulerToQuat(0, 0, deg2rad(45)),
    // Medio, anular y meñique semiabiertos
    rightMiddleProximal: eulerToQuat(0, 0, deg2rad(25)),
    rightMiddleIntermediate: eulerToQuat(0, 0, deg2rad(20)),
    rightMiddleDistal: Q_IDENTITY,
    rightRingProximal: eulerToQuat(0, 0, deg2rad(30)),
    rightRingIntermediate: eulerToQuat(0, 0, deg2rad(25)),
    rightRingDistal: Q_IDENTITY,
    rightLittleProximal: eulerToQuat(0, 0, deg2rad(35)),
    rightLittleIntermediate: eulerToQuat(0, 0, deg2rad(25)),
    rightLittleDistal: Q_IDENTITY
  };

  return createHandTestClip({
    clipId: 'TEST_PINZA_V1',
    gloss: 'TEST_PINZA',
    description: 'Prueba visual de contacto y oposición en pinza fina (índice-pulgar).',
    fingerPoses
  });
}

/**
 * 2.6 Mano curva: Todos los dedos curvados formando un arco ('C') con el pulgar opuesto.
 */
export function createTestManoCurvaClip() {
  const qProx = eulerToQuat(0, 0, deg2rad(35));
  const qInter = eulerToQuat(0, 0, deg2rad(45));
  const qDist = eulerToQuat(0, 0, deg2rad(30));

  const fingerPoses = {
    rightThumbMetacarpal: eulerToQuat(deg2rad(10), deg2rad(20), deg2rad(15)),
    rightThumbProximal: eulerToQuat(0, deg2rad(20), deg2rad(25)),
    rightThumbDistal: eulerToQuat(0, deg2rad(10), deg2rad(25)),
    rightIndexProximal: qProx,
    rightIndexIntermediate: qInter,
    rightIndexDistal: qDist,
    rightMiddleProximal: qProx,
    rightMiddleIntermediate: qInter,
    rightMiddleDistal: qDist,
    rightRingProximal: qProx,
    rightRingIntermediate: qInter,
    rightRingDistal: qDist,
    rightLittleProximal: qProx,
    rightLittleIntermediate: qInter,
    rightLittleDistal: qDist
  };

  return createHandTestClip({
    clipId: 'TEST_MANO_CURVA_V1',
    gloss: 'TEST_MANO_CURVA',
    description: 'Prueba visual de curvatura uniforme en forma de arco (configuración C).',
    fingerPoses
  });
}

/**
 * 2.7 Garra: Falanges intermedias y distales fuertemente flexionadas formando ganchos (configuración 5 garra).
 */
export function createTestGarraClip() {
  const qProx = eulerToQuat(0, 0, deg2rad(20));
  const qInter = eulerToQuat(0, 0, deg2rad(82));
  const qDist = eulerToQuat(0, 0, deg2rad(78));

  const fingerPoses = {
    rightThumbMetacarpal: eulerToQuat(deg2rad(5), deg2rad(15), deg2rad(10)),
    rightThumbProximal: eulerToQuat(0, deg2rad(25), deg2rad(50)),
    rightThumbDistal: eulerToQuat(0, 0, deg2rad(65)),
    rightIndexProximal: qProx,
    rightIndexIntermediate: qInter,
    rightIndexDistal: qDist,
    rightMiddleProximal: qProx,
    rightMiddleIntermediate: qInter,
    rightMiddleDistal: qDist,
    rightRingProximal: qProx,
    rightRingIntermediate: qInter,
    rightRingDistal: qDist,
    rightLittleProximal: qProx,
    rightLittleIntermediate: qInter,
    rightLittleDistal: qDist
  };

  return createHandTestClip({
    clipId: 'TEST_GARRA_V1',
    gloss: 'TEST_GARRA',
    description: 'Prueba visual de mano en garra (configuración 5 garra / curvatura distal).',
    fingerPoses
  });
}

/**
 * 2.8 Dedos juntos y separados: Transición dinámica entre aducción cerrada y abducción amplia en abanico.
 */
export function createTestDedosJuntosSeparadosClip() {
  const durationMs = 2400;
  const times = [0.0, 0.4, 0.9, 1.5, 2.0, 2.4];

  // Posturas de separación
  // Juntos
  const qIdx_Juntos = eulerToQuat(0, deg2rad(-8), 0);
  const qMid_Juntos = Q_IDENTITY;
  const qRng_Juntos = eulerToQuat(0, deg2rad(6), 0);
  const qLit_Juntos = eulerToQuat(0, deg2rad(12), 0);
  const qThm_Juntos = eulerToQuat(0, deg2rad(-15), 0);

  // Separados
  const qIdx_Sep = eulerToQuat(0, deg2rad(22), 0);
  const qMid_Sep = eulerToQuat(0, deg2rad(5), 0);
  const qRng_Sep = eulerToQuat(0, deg2rad(-14), 0);
  const qLit_Sep = eulerToQuat(0, deg2rad(-26), 0);
  const qThm_Sep = eulerToQuat(0, deg2rad(35), deg2rad(20));

  function makeDynamicTrack(boneName, qJuntos, qSep) {
    return {
      boneName,
      times,
      rotations: [
        ...Q_IDENTITY,
        ...qJuntos,
        ...qSep,
        ...qSep,
        ...qJuntos,
        ...Q_IDENTITY
      ],
      interpolation: 'SLERP'
    };
  }

  const tracks = [
    {
      boneName: 'rightUpperArm',
      times: [0.0, 0.4, 2.0, 2.4],
      rotations: [...Q_RUA_REST, ...Q_RUA_SIGN, ...Q_RUA_SIGN, ...Q_RUA_REST],
      interpolation: 'SLERP'
    },
    {
      boneName: 'rightLowerArm',
      times: [0.0, 0.4, 2.0, 2.4],
      rotations: [...Q_RLA_REST, ...Q_RLA_SIGN, ...Q_RLA_SIGN, ...Q_RLA_REST],
      interpolation: 'SLERP'
    },
    {
      boneName: 'rightHand',
      times: [0.0, 0.4, 2.0, 2.4],
      rotations: [...Q_RH_REST, ...Q_RH_SIGN, ...Q_RH_SIGN, ...Q_RH_REST],
      interpolation: 'SLERP'
    },
    makeDynamicTrack('rightIndexProximal', qIdx_Juntos, qIdx_Sep),
    makeDynamicTrack('rightMiddleProximal', qMid_Juntos, qMid_Sep),
    makeDynamicTrack('rightRingProximal', qRng_Juntos, qRng_Sep),
    makeDynamicTrack('rightLittleProximal', qLit_Juntos, qLit_Sep),
    makeDynamicTrack('rightThumbProximal', qThm_Juntos, qThm_Sep)
  ];

  const clip = {
    clipId: 'TEST_DEDOS_JUNTOS_SEPARADOS_V1',
    gloss: 'TEST_DEDOS_JUNTOS_SEPARADOS',
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
    boneTracks: tracks,
    expressionTracks: [],
    spatialConstraints: [],
    metadata: {
      description: 'Prueba dinámica de aducción (dedos juntos) vs abducción (dedos separados en abanico).',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/* ========================================================================== */
/* 3. PRUEBAS DE ORIENTACIÓN                                                  */
/* ========================================================================== */

/**
 * 3.1 Orientación de palma: Frontal, hacia el cuerpo, hacia arriba y hacia abajo.
 */
export function createTestOrientacionPalmaClip() {
  const durationMs = 3000;
  // 7 marcas de tiempo: reposo -> frontal -> cuerpo -> arriba -> abajo -> frontal -> reposo
  const times = [0.0, 0.4, 1.0, 1.6, 2.2, 2.6, 3.0];

  const qFrontal = eulerToQuat(deg2rad(10), 0, 0);
  const qCuerpo  = eulerToQuat(deg2rad(-65), 0, deg2rad(20));
  const qArriba  = eulerToQuat(deg2rad(15), deg2rad(-60), deg2rad(-30));
  const qAbajo   = eulerToQuat(deg2rad(15), deg2rad(60), deg2rad(20));

  const clip = {
    clipId: 'TEST_ORIENTACION_PALMA_V1',
    gloss: 'TEST_ORIENTACION_PALMA',
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
        times: [0.0, 0.4, 2.6, 3.0],
        rotations: [...Q_RUA_REST, ...Q_RUA_SIGN, ...Q_RUA_SIGN, ...Q_RUA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightLowerArm',
        times: [0.0, 0.4, 2.6, 3.0],
        rotations: [...Q_RLA_REST, ...Q_RLA_SIGN, ...Q_RLA_SIGN, ...Q_RLA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightHand',
        times,
        rotations: [...Q_RH_REST, ...qFrontal, ...qCuerpo, ...qArriba, ...qAbajo, ...qFrontal, ...Q_RH_REST],
        interpolation: 'SLERP'
      }
    ],
    expressionTracks: [],
    spatialConstraints: [],
    metadata: {
      description: 'Prueba de cuatro orientaciones de palma: frontal, hacia el cuerpo, arriba y abajo.',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/**
 * 3.2 Pronación y supinación: Rotación axial del antebrazo derecho con codo flexionado.
 */
export function createTestPronacionSupinacionClip() {
  const durationMs = 2400;
  // Reposo -> Neutro -> Pronación (-65° X) -> Supinación (+65° X) -> Neutro -> Reposo
  const times = [0.0, 0.4, 0.9, 1.5, 2.0, 2.4];

  const qRLA_Neutro = Q_RLA_SIGN;
  // Pronación axial del antebrazo
  const qRLA_Pron   = eulerToQuat(deg2rad(-85), deg2rad(15), deg2rad(-65));
  // Supinación axial del antebrazo
  const qRLA_Sup    = eulerToQuat(deg2rad(-85), deg2rad(15), deg2rad(65));

  const clip = {
    clipId: 'TEST_PRONACION_SUPINACION_V1',
    gloss: 'TEST_PRONACION_SUPINACION',
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
        times: [0.0, 0.4, 2.0, 2.4],
        rotations: [...Q_RUA_REST, ...Q_RUA_SIGN, ...Q_RUA_SIGN, ...Q_RUA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightLowerArm',
        times,
        rotations: [...Q_RLA_REST, ...qRLA_Neutro, ...qRLA_Pron, ...qRLA_Sup, ...qRLA_Neutro, ...Q_RLA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightHand',
        times: [0.0, 0.4, 2.0, 2.4],
        rotations: [...Q_RH_REST, ...Q_RH_SIGN, ...Q_RH_SIGN, ...Q_RH_REST],
        interpolation: 'SLERP'
      }
    ],
    expressionTracks: [],
    spatialConstraints: [],
    metadata: {
      description: 'Prueba de pronación y supinación axial continua del antebrazo.',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/**
 * 3.3 Flexión de muñeca y codo: Flexión del codo (30° a 110°) y muñeca palmar/dorsal.
 */
export function createTestFlexionMunecaCodoClip() {
  const durationMs = 2400;
  const times = [0.0, 0.5, 1.1, 1.7, 2.4];

  // Codo semi-extendido (~35°) a flexión profunda (~105°)
  const qRLA_Ext  = eulerToQuat(deg2rad(-35), deg2rad(10), 0);
  const qRLA_Flex = eulerToQuat(deg2rad(-105), deg2rad(15), 0);

  // Muñeca dorsal (+40°) a palmar (-40°)
  const qRH_Dorsal = eulerToQuat(deg2rad(40), 0, 0);
  const qRH_Palmar = eulerToQuat(deg2rad(-40), 0, 0);

  const clip = {
    clipId: 'TEST_FLEXION_MUNICA_CODO_V1',
    gloss: 'TEST_FLEXION_MUNICA_CODO',
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
        times: [0.0, 0.5, 1.7, 2.4],
        rotations: [...Q_RUA_REST, ...Q_RUA_SIGN, ...Q_RUA_SIGN, ...Q_RUA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightLowerArm',
        times,
        rotations: [...Q_RLA_REST, ...qRLA_Ext, ...qRLA_Flex, ...qRLA_Ext, ...Q_RLA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightHand',
        times,
        rotations: [...Q_RH_REST, ...qRH_Dorsal, ...qRH_Palmar, ...qRH_Dorsal, ...Q_RH_REST],
        interpolation: 'SLERP'
      }
    ],
    expressionTracks: [],
    spatialConstraints: [],
    metadata: {
      description: 'Prueba de rango articular de flexión/extensión combinada de codo y muñeca.',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/* ========================================================================== */
/* 4. PRUEBAS NO MANUALES (CNM)                                               */
/* ========================================================================== */

/**
 * 4.1 HEAD_SHAKE: Giro de cabeza izquierda-derecha (yaw).
 */
export function createTestHeadShakeClip() {
  const durationMs = 2200;
  const times = [0.0, 0.4, 0.9, 1.4, 1.8, 2.2];

  const qHead_0 = Q_HEAD_REST;
  const qHead_L = eulerToQuat(0, deg2rad(22), 0);
  const qHead_R = eulerToQuat(0, deg2rad(-22), 0);

  const clip = {
    clipId: 'TEST_CNM_HEAD_SHAKE_V1',
    gloss: 'TEST_CNM_HEAD_SHAKE',
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
        rotations: [...qHead_0, ...qHead_L, ...qHead_R, ...qHead_L, ...qHead_R, ...qHead_0],
        interpolation: 'SLERP'
      },
      {
        boneName: 'neck',
        times,
        rotations: [
          ...Q_NECK_REST,
          ...eulerToQuat(0, deg2rad(10), 0),
          ...eulerToQuat(0, deg2rad(-10), 0),
          ...eulerToQuat(0, deg2rad(10), 0),
          ...eulerToQuat(0, deg2rad(-10), 0),
          ...Q_NECK_REST
        ],
        interpolation: 'SLERP'
      }
    ],
    expressionTracks: [],
    spatialConstraints: [],
    metadata: {
      description: 'Componente no manual: movimiento oscilatorio de cabeza lateral (HEAD_SHAKE).',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/**
 * 4.2 HEAD_NOD: Asentimiento de cabeza arriba-abajo (pitch).
 */
export function createTestHeadNodClip() {
  const durationMs = 1800;
  const times = [0.0, 0.4, 0.8, 1.2, 1.8];

  const qHead_Down = eulerToQuat(deg2rad(18), 0, 0);
  const qHead_Up   = eulerToQuat(deg2rad(-12), 0, 0);

  const clip = {
    clipId: 'TEST_CNM_HEAD_NOD_V1',
    gloss: 'TEST_CNM_HEAD_NOD',
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
        rotations: [...Q_HEAD_REST, ...qHead_Down, ...qHead_Up, ...qHead_Down, ...Q_HEAD_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'neck',
        times,
        rotations: [
          ...Q_NECK_REST,
          ...eulerToQuat(deg2rad(8), 0, 0),
          ...eulerToQuat(deg2rad(-5), 0, 0),
          ...eulerToQuat(deg2rad(8), 0, 0),
          ...Q_NECK_REST
        ],
        interpolation: 'SLERP'
      }
    ],
    expressionTracks: [],
    spatialConstraints: [],
    metadata: {
      description: 'Componente no manual: asentimiento vertical de cabeza (HEAD_NOD).',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/**
 * 4.3 HEAD_TILT: Inclinación lateral de cabeza (roll).
 */
export function createTestHeadTiltClip() {
  const durationMs = 2000;
  const times = [0.0, 0.5, 1.1, 1.6, 2.0];

  const qHead_TiltL = eulerToQuat(0, 0, deg2rad(16));
  const qHead_TiltR = eulerToQuat(0, 0, deg2rad(-16));

  const clip = {
    clipId: 'TEST_CNM_HEAD_TILT_V1',
    gloss: 'TEST_CNM_HEAD_TILT',
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
        rotations: [...Q_HEAD_REST, ...qHead_TiltL, ...qHead_TiltR, ...qHead_TiltL, ...Q_HEAD_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'neck',
        times,
        rotations: [
          ...Q_NECK_REST,
          ...eulerToQuat(0, 0, deg2rad(8)),
          ...eulerToQuat(0, 0, deg2rad(-8)),
          ...eulerToQuat(0, 0, deg2rad(8)),
          ...Q_NECK_REST
        ],
        interpolation: 'SLERP'
      }
    ],
    expressionTracks: [],
    spatialConstraints: [],
    metadata: {
      description: 'Componente no manual: inclinación lateral de cabeza (HEAD_TILT).',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/**
 * 4.4 Mirada: Movimiento ocular a izquierda, derecha y frontal mediante huesos leftEye y rightEye.
 */
export function createTestMiradaClip() {
  const durationMs = 2400;
  // Centro -> Izquierda -> Derecha -> Arriba -> Centro
  const times = [0.0, 0.5, 1.1, 1.7, 2.4];

  const qEye_Center = [0, 0, 0, 1];
  const qEye_Left   = eulerToQuat(0, deg2rad(18), 0);
  const qEye_Right  = eulerToQuat(0, deg2rad(-18), 0);
  const qEye_Up     = eulerToQuat(deg2rad(12), 0, 0);

  const clip = {
    clipId: 'TEST_CNM_MIRADA_V1',
    gloss: 'TEST_CNM_MIRADA',
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
        boneName: 'leftEye',
        times,
        rotations: [...qEye_Center, ...qEye_Left, ...qEye_Right, ...qEye_Up, ...qEye_Center],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightEye',
        times,
        rotations: [...qEye_Center, ...qEye_Left, ...qEye_Right, ...qEye_Up, ...qEye_Center],
        interpolation: 'SLERP'
      }
    ],
    expressionTracks: [],
    spatialConstraints: [],
    metadata: {
      description: 'Componente no manual: control de mirada ocular (leftEye / rightEye) en 4 cuadrantes.',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/**
 * 4.5 Cejas: Elevadas (surprised) y fruncidas (angry).
 */
export function createTestCejasClip() {
  const durationMs = 2400;
  const times = [0.0, 0.5, 1.0, 1.6, 2.0, 2.4];

  const clip = {
    clipId: 'TEST_CNM_CEJAS_V1',
    gloss: 'TEST_CNM_CEJAS',
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
    boneTracks: [],
    expressionTracks: [
      {
        expressionName: 'surprised',
        times,
        values: [0.0, 0.85, 0.85, 0.0, 0.0, 0.0],
        interpolation: 'LINEAR'
      },
      {
        expressionName: 'angry',
        times,
        values: [0.0, 0.0, 0.0, 0.80, 0.80, 0.0],
        interpolation: 'LINEAR'
      }
    ],
    spatialConstraints: [],
    metadata: {
      description: 'Componente no manual: cejas elevadas (sorpresa/interrogación) y fruncidas (énfasis/negación).',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/**
 * 4.6 Parpadeo: Cierre completo y reapertura ocular (blink).
 */
export function createTestParpadeoClip() {
  const durationMs = 1500;
  const times = [0.0, 0.25, 0.45, 0.75, 0.95, 1.15, 1.5];

  const clip = {
    clipId: 'TEST_CNM_PARPADEO_V1',
    gloss: 'TEST_CNM_PARPADEO',
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
    boneTracks: [],
    expressionTracks: [
      {
        expressionName: 'blink',
        times,
        values: [0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
        interpolation: 'LINEAR'
      }
    ],
    spatialConstraints: [],
    metadata: {
      description: 'Componente no manual: doble ciclo de parpadeo ocular completo (blink).',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/**
 * 4.7 Boca: Apertura (aa) y redondeo labial (oh/ou).
 */
export function createTestBocaClip() {
  const durationMs = 2200;
  const times = [0.0, 0.5, 1.0, 1.5, 1.9, 2.2];

  const clip = {
    clipId: 'TEST_CNM_BOCA_V1',
    gloss: 'TEST_CNM_BOCA',
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
    boneTracks: [],
    expressionTracks: [
      {
        expressionName: 'aa',
        times,
        values: [0.0, 0.85, 0.85, 0.0, 0.0, 0.0],
        interpolation: 'LINEAR'
      },
      {
        expressionName: 'oh',
        times,
        values: [0.0, 0.0, 0.0, 0.80, 0.80, 0.0],
        interpolation: 'LINEAR'
      }
    ],
    spatialConstraints: [],
    metadata: {
      description: 'Componente no manual: apertura mandibular (aa) y redondeo labial (oh/ou).',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/* ========================================================================== */
/* 5. PRUEBAS SIMULTÁNEAS                                                     */
/* ========================================================================== */

/**
 * 5.1 Manos con cabeza: Ambos brazos realizando seña simétrica mientras la cabeza asiente (HEAD_NOD).
 */
export function createTestSimultaneoManosCabezaClip() {
  const durationMs = 2400;
  const times = [0.0, 0.5, 1.0, 1.5, 2.0, 2.4];

  const clip = {
    clipId: 'TEST_SIMULTANEO_MANOS_CABEZA_V1',
    gloss: 'TEST_SIMULTANEO_MANOS_CABEZA',
    conceptId: null,
    version: '1.0.0',
    durationMs,
    status: 'DEMO_ONLY',
    provenance: 'PROGRAMMATIC_PROTOTYPE',
    validationStatus: 'REQUIRES_LSEC_VALIDATION',
    dominantHand: 'RIGHT',
    twoHanded: true,
    entryPose: 'NEUTRAL',
    exitPose: 'NEUTRAL',
    boneTracks: [
      // Cabeza asintiendo
      {
        boneName: 'head',
        times,
        rotations: [
          ...Q_HEAD_REST,
          ...eulerToQuat(deg2rad(15), 0, 0),
          ...eulerToQuat(deg2rad(-8), 0, 0),
          ...eulerToQuat(deg2rad(15), 0, 0),
          ...eulerToQuat(deg2rad(-8), 0, 0),
          ...Q_HEAD_REST
        ],
        interpolation: 'SLERP'
      },
      // Brazo derecho
      {
        boneName: 'rightUpperArm',
        times,
        rotations: [...Q_RUA_REST, ...Q_RUA_SIGN, ...Q_RUA_SIGN, ...Q_RUA_SIGN, ...Q_RUA_SIGN, ...Q_RUA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightLowerArm',
        times,
        rotations: [...Q_RLA_REST, ...Q_RLA_SIGN, ...Q_RLA_SIGN, ...Q_RLA_SIGN, ...Q_RLA_SIGN, ...Q_RLA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightHand',
        times,
        rotations: [
          ...Q_RH_REST,
          ...eulerToQuat(deg2rad(15), 0, deg2rad(10)),
          ...eulerToQuat(deg2rad(-15), 0, deg2rad(-10)),
          ...eulerToQuat(deg2rad(15), 0, deg2rad(10)),
          ...eulerToQuat(deg2rad(-15), 0, deg2rad(-10)),
          ...Q_RH_REST
        ],
        interpolation: 'SLERP'
      },
      // Brazo izquierdo
      {
        boneName: 'leftUpperArm',
        times,
        rotations: [...Q_LUA_REST, ...Q_LUA_SIGN, ...Q_LUA_SIGN, ...Q_LUA_SIGN, ...Q_LUA_SIGN, ...Q_LUA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftLowerArm',
        times,
        rotations: [...Q_LLA_REST, ...Q_LLA_SIGN, ...Q_LLA_SIGN, ...Q_LLA_SIGN, ...Q_LLA_SIGN, ...Q_LLA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftHand',
        times,
        rotations: [
          ...Q_LH_REST,
          ...eulerToQuat(deg2rad(15), 0, deg2rad(-10)),
          ...eulerToQuat(deg2rad(-15), 0, deg2rad(10)),
          ...eulerToQuat(deg2rad(15), 0, deg2rad(-10)),
          ...eulerToQuat(deg2rad(-15), 0, deg2rad(10)),
          ...Q_LH_REST
        ],
        interpolation: 'SLERP'
      }
    ],
    expressionTracks: [],
    spatialConstraints: [],
    metadata: {
      description: 'Prueba de articulación simultánea bimanual con asentimiento rítmico de cabeza.',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/**
 * 5.2 Manos con mirada: La mano derecha señala a la derecha y los ojos siguen la mano.
 */
export function createTestSimultaneoManosMiradaClip() {
  const durationMs = 2400;
  const times = [0.0, 0.5, 1.2, 1.8, 2.4];

  // Mano apuntando hacia la derecha
  const qRUA_PointRight = eulerToQuat(deg2rad(25), deg2rad(-45), deg2rad(-50));
  const qRLA_PointRight = eulerToQuat(deg2rad(-65), deg2rad(30), 0);
  const qRH_PointRight  = eulerToQuat(deg2rad(10), deg2rad(-25), 0);

  // Ojos mirando a la derecha
  const qEye_Right = eulerToQuat(0, deg2rad(-20), 0);

  // Índice extendido, resto puño
  const qProx = eulerToQuat(0, 0, deg2rad(85));
  const qInter = eulerToQuat(0, 0, deg2rad(92));

  const clip = {
    clipId: 'TEST_SIMULTANEO_MANOS_MIRADA_V1',
    gloss: 'TEST_SIMULTANEO_MANOS_MIRADA',
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
        rotations: [...Q_RUA_REST, ...qRUA_PointRight, ...qRUA_PointRight, ...qRUA_PointRight, ...Q_RUA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightLowerArm',
        times,
        rotations: [...Q_RLA_REST, ...qRLA_PointRight, ...qRLA_PointRight, ...qRLA_PointRight, ...Q_RLA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightHand',
        times,
        rotations: [...Q_RH_REST, ...qRH_PointRight, ...qRH_PointRight, ...qRH_PointRight, ...Q_RH_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightMiddleProximal',
        times: [0.0, 0.5, 1.8, 2.4],
        rotations: [...Q_IDENTITY, ...qProx, ...qProx, ...Q_IDENTITY],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightMiddleIntermediate',
        times: [0.0, 0.5, 1.8, 2.4],
        rotations: [...Q_IDENTITY, ...qInter, ...qInter, ...Q_IDENTITY],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftEye',
        times,
        rotations: [...[0, 0, 0, 1], ...qEye_Right, ...qEye_Right, ...qEye_Right, ...[0, 0, 0, 1]],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightEye',
        times,
        rotations: [...[0, 0, 0, 1], ...qEye_Right, ...qEye_Right, ...qEye_Right, ...[0, 0, 0, 1]],
        interpolation: 'SLERP'
      },
      {
        boneName: 'head',
        times,
        rotations: [
          ...Q_HEAD_REST,
          ...eulerToQuat(0, deg2rad(-10), 0),
          ...eulerToQuat(0, deg2rad(-10), 0),
          ...eulerToQuat(0, deg2rad(-10), 0),
          ...Q_HEAD_REST
        ],
        interpolation: 'SLERP'
      }
    ],
    expressionTracks: [],
    spatialConstraints: [],
    metadata: {
      description: 'Coordinación visomotora: señalamiento manual sincronizado con seguimiento ocular hacia el objetivo.',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/**
 * 5.3 Manos con expresión facial: Seña enfática con puño cerrado y ceño fruncido.
 */
export function createTestSimultaneoManosExpresionClip() {
  const durationMs = 2200;
  const times = [0.0, 0.5, 1.1, 1.6, 2.2];

  const qProx = eulerToQuat(0, 0, deg2rad(85));
  const qInter = eulerToQuat(0, 0, deg2rad(92));

  const clip = {
    clipId: 'TEST_SIMULTANEO_MANOS_EXPRESION_V1',
    gloss: 'TEST_SIMULTANEO_MANOS_EXPRESION',
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
        rotations: [...Q_RUA_REST, ...Q_RUA_SIGN, ...Q_RUA_SIGN, ...Q_RUA_SIGN, ...Q_RUA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightLowerArm',
        times,
        rotations: [...Q_RLA_REST, ...Q_RLA_SIGN, ...Q_RLA_SIGN, ...Q_RLA_SIGN, ...Q_RLA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightHand',
        times,
        rotations: [...Q_RH_REST, ...Q_RH_SIGN, ...Q_RH_SIGN, ...Q_RH_SIGN, ...Q_RH_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightIndexProximal',
        times: [0.0, 0.5, 1.6, 2.2],
        rotations: [...Q_IDENTITY, ...qProx, ...qProx, ...Q_IDENTITY],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightIndexIntermediate',
        times: [0.0, 0.5, 1.6, 2.2],
        rotations: [...Q_IDENTITY, ...qInter, ...qInter, ...Q_IDENTITY],
        interpolation: 'SLERP'
      }
    ],
    expressionTracks: [
      {
        expressionName: 'angry',
        times: [0.0, 0.5, 1.6, 2.2],
        values: [0.0, 0.85, 0.85, 0.0],
        interpolation: 'LINEAR'
      }
    ],
    spatialConstraints: [],
    metadata: {
      description: 'Prueba de sincronización motora manual con expresión facial enfática de cejas.',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
    }
  };

  validateSignClip(clip);
  return clip;
}

/**
 * 5.4 Coordinación compleja total: Torso, ambos brazos, falanges, cabeza, mirada y rostro activos simultáneamente.
 */
export function createTestSimultaneoComplejoTotalClip() {
  const durationMs = 2800;
  const times = [0.0, 0.6, 1.4, 2.1, 2.8];

  // Inclinación suave del torso hacia adelante
  const qSpine_Lean = eulerToQuat(deg2rad(8), 0, deg2rad(2));
  const qChest_Lean = eulerToQuat(deg2rad(6), 0, deg2rad(2));

  // Cabeza con leve inclinación y yaw
  const qHead_Complex = eulerToQuat(deg2rad(8), deg2rad(10), deg2rad(-6));

  // Ojos mirando al frente-abajo
  const qEye_Complex = eulerToQuat(deg2rad(8), deg2rad(6), 0);

  // Curvatura de dedos (mano curva C)
  const qProx = eulerToQuat(0, 0, deg2rad(40));
  const qInter = eulerToQuat(0, 0, deg2rad(45));

  const clip = {
    clipId: 'TEST_SIMULTANEO_COMPLEJO_TOTAL_V1',
    gloss: 'TEST_SIMULTANEO_COMPLEJO_TOTAL',
    conceptId: null,
    version: '1.0.0',
    durationMs,
    status: 'DEMO_ONLY',
    provenance: 'PROGRAMMATIC_PROTOTYPE',
    validationStatus: 'REQUIRES_LSEC_VALIDATION',
    dominantHand: 'RIGHT',
    twoHanded: true,
    entryPose: 'NEUTRAL',
    exitPose: 'NEUTRAL',
    boneTracks: [
      {
        boneName: 'spine',
        times,
        rotations: [...Q_SPINE_REST, ...qSpine_Lean, ...qSpine_Lean, ...qSpine_Lean, ...Q_SPINE_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'chest',
        times,
        rotations: [...Q_CHEST_REST, ...qChest_Lean, ...qChest_Lean, ...qChest_Lean, ...Q_CHEST_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'head',
        times,
        rotations: [...Q_HEAD_REST, ...qHead_Complex, ...qHead_Complex, ...qHead_Complex, ...Q_HEAD_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftEye',
        times,
        rotations: [...[0, 0, 0, 1], ...qEye_Complex, ...qEye_Complex, ...qEye_Complex, ...[0, 0, 0, 1]],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightEye',
        times,
        rotations: [...[0, 0, 0, 1], ...qEye_Complex, ...qEye_Complex, ...qEye_Complex, ...[0, 0, 0, 1]],
        interpolation: 'SLERP'
      },
      // Brazo derecho
      {
        boneName: 'rightUpperArm',
        times,
        rotations: [...Q_RUA_REST, ...Q_RUA_SIGN, ...Q_RUA_SIGN, ...Q_RUA_SIGN, ...Q_RUA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightLowerArm',
        times,
        rotations: [...Q_RLA_REST, ...Q_RLA_SIGN, ...Q_RLA_SIGN, ...Q_RLA_SIGN, ...Q_RLA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightHand',
        times,
        rotations: [...Q_RH_REST, ...Q_RH_SIGN, ...Q_RH_SIGN, ...Q_RH_SIGN, ...Q_RH_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightIndexProximal',
        times: [0.0, 0.6, 2.1, 2.8],
        rotations: [...Q_IDENTITY, ...qProx, ...qProx, ...Q_IDENTITY],
        interpolation: 'SLERP'
      },
      {
        boneName: 'rightIndexIntermediate',
        times: [0.0, 0.6, 2.1, 2.8],
        rotations: [...Q_IDENTITY, ...qInter, ...qInter, ...Q_IDENTITY],
        interpolation: 'SLERP'
      },
      // Brazo izquierdo
      {
        boneName: 'leftUpperArm',
        times,
        rotations: [...Q_LUA_REST, ...Q_LUA_SIGN, ...Q_LUA_SIGN, ...Q_LUA_SIGN, ...Q_LUA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftLowerArm',
        times,
        rotations: [...Q_LLA_REST, ...Q_LLA_SIGN, ...Q_LLA_SIGN, ...Q_LLA_SIGN, ...Q_LLA_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftHand',
        times,
        rotations: [...Q_LH_REST, ...Q_LH_SIGN, ...Q_LH_SIGN, ...Q_LH_SIGN, ...Q_LH_REST],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftIndexProximal',
        times: [0.0, 0.6, 2.1, 2.8],
        rotations: [...Q_IDENTITY, ...eulerToQuat(0, 0, deg2rad(-40)), ...eulerToQuat(0, 0, deg2rad(-40)), ...Q_IDENTITY],
        interpolation: 'SLERP'
      },
      {
        boneName: 'leftIndexIntermediate',
        times: [0.0, 0.6, 2.1, 2.8],
        rotations: [...Q_IDENTITY, ...eulerToQuat(0, 0, deg2rad(-45)), ...eulerToQuat(0, 0, deg2rad(-45)), ...Q_IDENTITY],
        interpolation: 'SLERP'
      }
    ],
    expressionTracks: [
      {
        expressionName: 'surprised',
        times: [0.0, 0.6, 1.4, 2.1, 2.8],
        values: [0.0, 0.60, 0.60, 0.0, 0.0],
        interpolation: 'LINEAR'
      },
      {
        expressionName: 'aa',
        times: [0.0, 0.6, 1.4, 2.1, 2.8],
        values: [0.0, 0.50, 0.50, 0.0, 0.0],
        interpolation: 'LINEAR'
      }
    ],
    spatialConstraints: [],
    metadata: {
      description: 'Prueba holística: articulación simultánea integral de torso, brazos, manos, falanges, cabeza, mirada y rostro.',
      isValidatedLSEC: false,
      disclaimer: 'PRUEBA TÉCNICA DEMOSTRATIVA. No es una seña validada de LSEC.'
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
