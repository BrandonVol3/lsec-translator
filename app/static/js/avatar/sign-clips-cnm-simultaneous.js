/**
 * LSEC Studio — Pruebas Técnicas de Componentes No Manuales (CNM) y Coordinación Simultánea
 *
 * Submódulo extraído de sign-clip-factory.js para cumplir SRP (< 800 líneas).
 */

import { validateSignClip } from './sign-animation-schema.js';
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
  Q_RUA_SIGN,
  Q_RLA_SIGN,
  Q_RH_SIGN,
  Q_LUA_SIGN,
  Q_LLA_SIGN,
  Q_LH_SIGN
} from './sign-clips-hands-orientation.js';

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
 * Generador paramétrico de rasgos no manuales de boca (Página 5 de Guia-Uso-ilustraciones.pdf):
 * - 'open_close_mouth': Abrir o cerrar la boca (jawOpen, mouthClose, aa)
 * - 'expel_air_open_mouth': Expulsar aire con la boca abierta (jawOpen, cheekPuff, mouthFunnel, oh)
 * - 'expel_air_closed_mouth': Expulsar aire con la boca cerrada (cheekPuff, mouthClose, mouthPressLeft/Right, ou)
 */
export function createLSECMouthNonManualTracks(mouthMode = 'open_close_mouth', durationSec = 2.2) {
  const t = [0.0, Number((durationSec * 0.25).toFixed(4)), Number((durationSec * 0.72).toFixed(4)), Number(durationSec.toFixed(4))];
  if (mouthMode === 'expel_air_open_mouth') {
    return [
      { expressionName: 'jawOpen', times: t, values: [0.0, 0.65, 0.60, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'cheekPuff', times: t, values: [0.0, 0.80, 0.35, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'mouthFunnel', times: t, values: [0.0, 0.75, 0.70, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'oh', times: t, values: [0.0, 0.70, 0.65, 0.0], interpolation: 'LINEAR' }
    ];
  }
  if (mouthMode === 'expel_air_closed_mouth') {
    return [
      { expressionName: 'mouthClose', times: t, values: [0.0, 0.85, 0.85, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'cheekPuff', times: t, values: [0.0, 0.90, 0.45, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'mouthPressLeft', times: t, values: [0.0, 0.75, 0.70, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'mouthPressRight', times: t, values: [0.0, 0.75, 0.70, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'ou', times: t, values: [0.0, 0.60, 0.55, 0.0], interpolation: 'LINEAR' }
    ];
  }
  return [
    { expressionName: 'jawOpen', times: t, values: [0.0, 0.82, 0.05, 0.0], interpolation: 'LINEAR' },
    { expressionName: 'mouthClose', times: t, values: [0.0, 0.0, 0.75, 0.0], interpolation: 'LINEAR' },
    { expressionName: 'aa', times: t, values: [0.0, 0.82, 0.0, 0.0], interpolation: 'LINEAR' }
  ];
}

/**
 * 4.7 Boca: Abrir/cerrar boca y expulsar aire con boca abierta/cerrada (Página 5 PDF).
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
      { expressionName: 'aa', times, values: [0.0, 0.85, 0.85, 0.0, 0.0, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'jawOpen', times, values: [0.0, 0.85, 0.80, 0.0, 0.0, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'oh', times, values: [0.0, 0.0, 0.70, 0.80, 0.0, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'mouthFunnel', times, values: [0.0, 0.0, 0.65, 0.75, 0.0, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'cheekPuff', times, values: [0.0, 0.0, 0.75, 0.85, 0.80, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'mouthClose', times, values: [0.0, 0.0, 0.0, 0.80, 0.85, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'mouthPressLeft', times, values: [0.0, 0.0, 0.0, 0.70, 0.75, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'mouthPressRight', times, values: [0.0, 0.0, 0.0, 0.70, 0.75, 0.0], interpolation: 'LINEAR' }
    ],
    spatialConstraints: [],
    metadata: {
      description: 'Componente no manual (Pág. 5 PDF): abrir/cerrar boca y expulsar aire con boca abierta y cerrada mediante ARKit Blendshapes.',
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

  const qRUA_PointRight = eulerToQuat(deg2rad(25), deg2rad(-45), deg2rad(-50));
  const qRLA_PointRight = eulerToQuat(deg2rad(-65), deg2rad(30), 0);
  const qRH_PointRight  = eulerToQuat(deg2rad(10), deg2rad(-25), 0);
  const qEye_Right = eulerToQuat(0, deg2rad(-20), 0);
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

  const qSpine_Lean = eulerToQuat(deg2rad(8), 0, deg2rad(2));
  const qChest_Lean = eulerToQuat(deg2rad(6), 0, deg2rad(2));
  const qHead_Complex = eulerToQuat(deg2rad(8), deg2rad(10), deg2rad(-6));
  const qEye_Complex = eulerToQuat(deg2rad(8), deg2rad(6), 0);
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
      { boneName: 'spine', times, rotations: [...Q_SPINE_REST, ...qSpine_Lean, ...qSpine_Lean, ...qSpine_Lean, ...Q_SPINE_REST], interpolation: 'SLERP' },
      { boneName: 'chest', times, rotations: [...Q_CHEST_REST, ...qChest_Lean, ...qChest_Lean, ...qChest_Lean, ...Q_CHEST_REST], interpolation: 'SLERP' },
      { boneName: 'head', times, rotations: [...Q_HEAD_REST, ...qHead_Complex, ...qHead_Complex, ...qHead_Complex, ...Q_HEAD_REST], interpolation: 'SLERP' },
      { boneName: 'leftEye', times, rotations: [...[0, 0, 0, 1], ...qEye_Complex, ...qEye_Complex, ...qEye_Complex, ...[0, 0, 0, 1]], interpolation: 'SLERP' },
      { boneName: 'rightEye', times, rotations: [...[0, 0, 0, 1], ...qEye_Complex, ...qEye_Complex, ...qEye_Complex, ...[0, 0, 0, 1]], interpolation: 'SLERP' },
      { boneName: 'rightUpperArm', times, rotations: [...Q_RUA_REST, ...Q_RUA_SIGN, ...Q_RUA_SIGN, ...Q_RUA_SIGN, ...Q_RUA_REST], interpolation: 'SLERP' },
      { boneName: 'rightLowerArm', times, rotations: [...Q_RLA_REST, ...Q_RLA_SIGN, ...Q_RLA_SIGN, ...Q_RLA_SIGN, ...Q_RLA_REST], interpolation: 'SLERP' },
      { boneName: 'rightHand', times, rotations: [...Q_RH_REST, ...Q_RH_SIGN, ...Q_RH_SIGN, ...Q_RH_SIGN, ...Q_RH_REST], interpolation: 'SLERP' },
      { boneName: 'rightIndexProximal', times: [0.0, 0.6, 2.1, 2.8], rotations: [...Q_IDENTITY, ...qProx, ...qProx, ...Q_IDENTITY], interpolation: 'SLERP' },
      { boneName: 'rightIndexIntermediate', times: [0.0, 0.6, 2.1, 2.8], rotations: [...Q_IDENTITY, ...qInter, ...qInter, ...Q_IDENTITY], interpolation: 'SLERP' },
      { boneName: 'leftUpperArm', times, rotations: [...Q_LUA_REST, ...Q_LUA_SIGN, ...Q_LUA_SIGN, ...Q_LUA_SIGN, ...Q_LUA_REST], interpolation: 'SLERP' },
      { boneName: 'leftLowerArm', times, rotations: [...Q_LLA_REST, ...Q_LLA_SIGN, ...Q_LLA_SIGN, ...Q_LLA_SIGN, ...Q_LLA_REST], interpolation: 'SLERP' },
      { boneName: 'leftHand', times, rotations: [...Q_LH_REST, ...Q_LH_SIGN, ...Q_LH_SIGN, ...Q_LH_SIGN, ...Q_LH_REST], interpolation: 'SLERP' },
      { boneName: 'leftIndexProximal', times: [0.0, 0.6, 2.1, 2.8], rotations: [...Q_IDENTITY, ...eulerToQuat(0, 0, deg2rad(-40)), ...eulerToQuat(0, 0, deg2rad(-40)), ...Q_IDENTITY], interpolation: 'SLERP' },
      { boneName: 'leftIndexIntermediate', times: [0.0, 0.6, 2.1, 2.8], rotations: [...Q_IDENTITY, ...eulerToQuat(0, 0, deg2rad(-45)), ...eulerToQuat(0, 0, deg2rad(-45)), ...Q_IDENTITY], interpolation: 'SLERP' }
    ],
    expressionTracks: [
      { expressionName: 'surprised', times: [0.0, 0.6, 1.4, 2.1, 2.8], values: [0.0, 0.60, 0.60, 0.0, 0.0], interpolation: 'LINEAR' },
      { expressionName: 'aa', times: [0.0, 0.6, 1.4, 2.1, 2.8], values: [0.0, 0.50, 0.50, 0.0, 0.0], interpolation: 'LINEAR' }
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
