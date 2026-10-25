/**
 * LSEC Studio — Constantes Biomecánicas, Helpers de Cuaterniones y Pruebas de Manos/Orientación
 *
 * Submódulo extraído de sign-clip-factory.js para cumplir SRP (< 800 líneas).
 */

import * as THREE from 'three';
import { validateSignClip } from './sign-animation-schema.js';
import {
  LSEC_FINGERSPELLING_GRAPHEMES,
  LSEC_FINGERSPELLING_CATALOG,
  tokenizeLSECFingerspelling,
  createLSECFingerspellingSignClip,
  createLSECFingerspellingWordClip,
  getAllLSECFingerspellingClips
} from './sign-clips-fingerspelling-lsec.js';

export {
  LSEC_FINGERSPELLING_GRAPHEMES,
  LSEC_FINGERSPELLING_CATALOG,
  tokenizeLSECFingerspelling,
  createLSECFingerspellingSignClip,
  createLSECFingerspellingWordClip,
  getAllLSECFingerspellingClips
};

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
export const Q_IDENTITY = [0, 0, 0, 1];

// Poses base de reposo
export const Q_SPINE_REST = eulerToQuat(deg2rad(1), 0, 0);
export const Q_CHEST_REST = eulerToQuat(deg2rad(1), 0, 0);
export const Q_NECK_REST  = [0, 0, 0, 1];
export const Q_HEAD_REST  = [0, 0, 0, 1];

// Brazo izquierdo en reposo biomecánico natural (unificado con v2.6 y SignPlayer.restoreNeutralPose)
export const Q_LUA_REST = [0.0435, 0.0028, -0.6087, 0.7921];
export const Q_LLA_REST = [0, 0.0872, 0, 0.9962];
export const Q_LH_REST  = [0, 0, 0, 1];

// Brazo derecho en reposo biomecánico natural (unificado con v2.6 y SignPlayer.restoreNeutralPose)
export const Q_RUA_REST = [0.0435, -0.0028, 0.6087, 0.7921];
export const Q_RLA_REST = [0, -0.0872, 0, 0.9962];
export const Q_RH_REST  = [0, 0, 0, 1];

// Brazo derecho en espacio de señas frontal (altura de pecho/hombro, palma al frente)
export const Q_RUA_SIGN = eulerToQuat(deg2rad(32), deg2rad(-20), deg2rad(-62));
export const Q_RLA_SIGN = eulerToQuat(deg2rad(-85), deg2rad(15), 0);
export const Q_RH_SIGN  = eulerToQuat(deg2rad(10), 0, 0);

// Brazo izquierdo en espacio de señas simétrico
export const Q_LUA_SIGN = eulerToQuat(deg2rad(32), deg2rad(20), deg2rad(62));
export const Q_LLA_SIGN = eulerToQuat(deg2rad(-85), deg2rad(-15), 0);
export const Q_LH_SIGN  = eulerToQuat(deg2rad(10), 0, 0);

/**
 * Generador de clip base para pruebas técnicas de mano derecha en espacio de señas.
 */
export function createHandTestClip({ clipId, gloss, description, fingerPoses, durationMs = 1500, extraTracks = [] }) {
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
    rightIndexProximal: Q_IDENTITY,
    rightIndexIntermediate: Q_IDENTITY,
    rightIndexDistal: Q_IDENTITY,
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
    rightIndexProximal: eulerToQuat(0, deg2rad(12), 0),
    rightIndexIntermediate: Q_IDENTITY,
    rightIndexDistal: Q_IDENTITY,
    rightMiddleProximal: eulerToQuat(0, deg2rad(-10), 0),
    rightMiddleIntermediate: Q_IDENTITY,
    rightMiddleDistal: Q_IDENTITY,
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
    rightIndexProximal: eulerToQuat(deg2rad(5), deg2rad(-8), deg2rad(42)),
    rightIndexIntermediate: eulerToQuat(0, 0, deg2rad(65)),
    rightIndexDistal: eulerToQuat(0, 0, deg2rad(45)),
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

  const qIdx_Juntos = eulerToQuat(0, deg2rad(-8), 0);
  const qMid_Juntos = Q_IDENTITY;
  const qRng_Juntos = eulerToQuat(0, deg2rad(6), 0);
  const qLit_Juntos = eulerToQuat(0, deg2rad(12), 0);
  const qThm_Juntos = eulerToQuat(0, deg2rad(-15), 0);

  const qIdx_Sep = eulerToQuat(0, deg2rad(22), 0);
  const qMid_Sep = eulerToQuat(0, deg2rad(5), 0);
  const qRng_Sep = eulerToQuat(0, deg2rad(-14), 0);
  const qLit_Sep = eulerToQuat(0, deg2rad(-26), 0);
  const qThm_Sep = eulerToQuat(0, deg2rad(35), deg2rad(20));

  function makeDynamicTrack(boneName, qJuntos, qSep) {
    return {
      boneName,
      times,
      rotations: [...Q_IDENTITY, ...qJuntos, ...qSep, ...qSep, ...qJuntos, ...Q_IDENTITY],
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
  const times = [0.0, 0.4, 0.9, 1.5, 2.0, 2.4];

  const qRLA_Neutro = Q_RLA_SIGN;
  const qRLA_Pron   = eulerToQuat(deg2rad(-85), deg2rad(15), deg2rad(-65));
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

  const qRLA_Ext  = eulerToQuat(deg2rad(-35), deg2rad(10), 0);
  const qRLA_Flex = eulerToQuat(deg2rad(-105), deg2rad(15), 0);

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
