/**
 * LSEC Studio — Catálogo Oficial de los 30 Grafemas de Dactilología LSEC y Tokenizador NFC
 *
 * Codifica con exactitud biomecánica las 30 representaciones del alfabeto manual
 * ecuatoriano de la Página 10 de `Guia-Uso-ilustraciones.pdf` (a, b, c, ch, d, e,
 * f, g, h, i, j, k, l, ll, m, n, ñ, o, p, q, r, rr, s, t, u, v, w, x, y, z) y el
 * tokenizador lingüístico con detección prioritaria de dígrafos (CH, LL, RR).
 */

import { buildRightHandPhalangePose } from './sign-clips-fingerspelling-primitives.js';

export const LSEC_FINGERSPELLING_GRAPHEMES = Object.freeze([
  'A', 'B', 'C', 'CH', 'D',
  'E', 'F', 'G', 'H', 'I',
  'J', 'K', 'L', 'LL', 'M',
  'N', 'Ñ', 'O', 'P', 'Q',
  'R', 'RR', 'S', 'T', 'U',
  'V', 'W', 'X', 'Y', 'Z'
]);

const F_CURLED = Object.freeze({ proxFlex: 82, interFlex: 92, distFlex: 75, splay: 0 });
const F_EXTENDED = Object.freeze({ proxFlex: 0, interFlex: 0, distFlex: 0, splay: 0 });
const THUMB_TUCKED = Object.freeze({ metaX: 30, metaY: -44, metaZ: 34, proxX: 10, proxY: -28, proxZ: 44, distZ: 36 });
const THUMB_ACROSS_PALM = Object.freeze({ metaX: 28, metaY: -48, metaZ: 38, proxX: 10, proxY: -32, proxZ: 48, distZ: 35 });
const THUMB_SIDE_A = Object.freeze({ metaX: 8, metaY: -14, metaZ: 8, proxX: 0, proxY: -8, proxZ: 6, distZ: 4 });
const THUMB_OUT_L = Object.freeze({ metaX: 0, metaY: 6, metaZ: -8, proxX: 0, proxY: 4, proxZ: -4, distZ: 0 });
const THUMB_PINCH_F = Object.freeze({ metaX: 32, metaY: -38, metaZ: 24, proxX: 8, proxY: -22, proxZ: 32, distZ: 28 });
const THUMB_FRONT_S = Object.freeze({ metaX: 36, metaY: -42, metaZ: 32, proxX: 12, proxY: -28, proxZ: 45, distZ: 38 });

function buildCatalogDefinitions() {
  const defs = {
    A: {
      grapheme: 'A', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra A LSEC: Puño cerrado con palma frontal y pulgar extendido adosado al borde radial del índice.',
      handOrientationB: { pitchDeg: 4, yawDeg: -6, rollDeg: 0, axialTwistDeg: 0 },
      poseB100: buildRightHandPhalangePose({ thumb: THUMB_SIDE_A, index: F_CURLED, middle: F_CURLED, ring: F_CURLED, little: F_CURLED })
    },
    B: {
      grapheme: 'B', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra B LSEC: Palma frontal con índice, medio, anular y meñique extendidos en aducción; pulgar flexionado sobre la palma.',
      handOrientationB: { pitchDeg: 4, yawDeg: 0, rollDeg: 0, axialTwistDeg: 0 },
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_ACROSS_PALM,
        index: { ...F_EXTENDED, splay: -5 }, middle: { ...F_EXTENDED, splay: 0 },
        ring: { ...F_EXTENDED, splay: 5 }, little: { ...F_EXTENDED, splay: 10 }
      })
    },
    C: {
      grapheme: 'C', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra C LSEC: Mano en orientación oblicua con curvatura cilíndrica de los 4 dedos opuestos al pulgar.',
      handOrientationB: { pitchDeg: 4, yawDeg: 48, rollDeg: 6, axialTwistDeg: 10 },
      poseB100: buildRightHandPhalangePose({
        thumb: { metaX: 22, metaY: -22, metaZ: 8, proxX: 6, proxY: -14, proxZ: 18, distZ: 16 },
        index: { proxFlex: 26, interFlex: 44, distFlex: 28, splay: -4 },
        middle: { proxFlex: 28, interFlex: 46, distFlex: 30, splay: 0 },
        ring: { proxFlex: 28, interFlex: 46, distFlex: 30, splay: 4 },
        little: { proxFlex: 30, interFlex: 44, distFlex: 28, splay: 8 }
      })
    },
    CH: {
      grapheme: 'CH', isStaticHold: false, isDynamic: true, opacityMode: 'TRANSITION_70_TO_100',
      localMovement: 'open_close_fingers', trajectory: { type: 'linear', variant: 'left_to_right', amplitudeM: 0.024 },
      repetition: 1, speedFactor: 1.0, contactMode: 'DESPLAZAR',
      description: 'Dígrafo CH LSEC: Mano horizontal apuntando hacia adentro con pulgar, índice y medio extendidos en transición 70%->100%.',
      handOrientationA: { pitchDeg: 8, yawDeg: -22, rollDeg: -68, axialTwistDeg: -12 },
      handOrientationB: { pitchDeg: 10, yawDeg: -28, rollDeg: -74, axialTwistDeg: -18 },
      poseA70: buildRightHandPhalangePose({
        thumb: { metaX: 6, metaY: -8, metaZ: -4, proxX: 0, proxY: -6, proxZ: 0, distZ: 0 },
        index: { proxFlex: 4, interFlex: 0, distFlex: 0, splay: 12 },
        middle: { proxFlex: 6, interFlex: 0, distFlex: 0, splay: -10 },
        ring: F_CURLED, little: F_CURLED
      }),
      poseB100: buildRightHandPhalangePose({
        thumb: { metaX: 16, metaY: -22, metaZ: 14, proxX: 4, proxY: -14, proxZ: 18, distZ: 14 },
        index: { proxFlex: 18, interFlex: 12, distFlex: 6, splay: 6 },
        middle: { proxFlex: 20, interFlex: 14, distFlex: 6, splay: -6 },
        ring: F_CURLED, little: F_CURLED
      })
    },
    D: {
      grapheme: 'D', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra D LSEC: Índice extendido verticalmente hacia arriba; medio, anular y meñique curvados en oposición con el pulgar.',
      handOrientationB: { pitchDeg: 4, yawDeg: 34, rollDeg: 4, axialTwistDeg: 8 },
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_PINCH_F,
        index: F_EXTENDED,
        middle: { proxFlex: 50, interFlex: 64, distFlex: 44, splay: 0 },
        ring: { proxFlex: 54, interFlex: 68, distFlex: 46, splay: 4 },
        little: { proxFlex: 58, interFlex: 70, distFlex: 48, splay: 8 }
      })
    },
    E: {
      grapheme: 'E', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra E LSEC: Palma frontal con los cuatro dedos flexionados en garra compacta apoyando las yemas sobre el pulgar.',
      handOrientationB: { pitchDeg: 5, yawDeg: -5, rollDeg: 0, axialTwistDeg: 0 },
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_ACROSS_PALM,
        index: { proxFlex: 36, interFlex: 88, distFlex: 78, splay: -4 },
        middle: { proxFlex: 36, interFlex: 90, distFlex: 80, splay: 0 },
        ring: { proxFlex: 38, interFlex: 88, distFlex: 78, splay: 4 },
        little: { proxFlex: 40, interFlex: 86, distFlex: 76, splay: 8 }
      })
    },
    F: {
      grapheme: 'F', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra F LSEC: Pinza circular entre las yemas del índice y pulgar con extensión abierta de medio, anular y meñique.',
      handOrientationB: { pitchDeg: 5, yawDeg: -14, rollDeg: 0, axialTwistDeg: -4 },
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_PINCH_F,
        index: { proxFlex: 46, interFlex: 64, distFlex: 44, splay: -4 },
        middle: { ...F_EXTENDED, splay: 4 }, ring: { ...F_EXTENDED, splay: -6 }, little: { ...F_EXTENDED, splay: -16 }
      })
    },
    G: {
      grapheme: 'G', isStaticHold: false, isDynamic: true, opacityMode: 'TRANSITION_70_TO_100',
      localMovement: 'open_close_fingers', trajectory: { type: 'linear', variant: 'left_to_right', amplitudeM: 0.022 },
      repetition: 1, speedFactor: 1.0, contactMode: 'DESPLAZAR',
      description: 'Letra G LSEC: Mano horizontal apuntando hacia adentro con dorso visible e índice extendido; transición 70%->100%.',
      handOrientationA: { pitchDeg: 42, yawDeg: 18, rollDeg: -78, axialTwistDeg: -24 },
      handOrientationB: { pitchDeg: 48, yawDeg: 24, rollDeg: -84, axialTwistDeg: -32 },
      poseA70: buildRightHandPhalangePose({
        thumb: { metaX: 16, metaY: -24, metaZ: 14, proxX: 4, proxY: -16, proxZ: 18, distZ: 12 },
        index: { proxFlex: 0, interFlex: 0, distFlex: 0, splay: 4 },
        middle: F_CURLED, ring: F_CURLED, little: F_CURLED
      }),
      poseB100: buildRightHandPhalangePose({
        thumb: { metaX: 24, metaY: -34, metaZ: 24, proxX: 8, proxY: -22, proxZ: 30, distZ: 22 },
        index: { proxFlex: 2, interFlex: 0, distFlex: 0, splay: 0 },
        middle: F_CURLED, ring: F_CURLED, little: F_CURLED
      })
    },
    H: {
      grapheme: 'H', isStaticHold: false, isDynamic: true, opacityMode: 'TRANSITION_70_TO_100',
      localMovement: 'open_close_fingers', trajectory: { type: 'linear', variant: 'left_to_right', amplitudeM: 0.024 },
      repetition: 1, speedFactor: 1.0, contactMode: 'DESPLAZAR',
      description: 'Letra H LSEC: Mano horizontal hacia adentro con índice y medio extendidos; transición 70%->100% de aducción.',
      handOrientationA: { pitchDeg: 42, yawDeg: 18, rollDeg: -76, axialTwistDeg: -22 },
      handOrientationB: { pitchDeg: 48, yawDeg: 24, rollDeg: -82, axialTwistDeg: -30 },
      poseA70: buildRightHandPhalangePose({
        thumb: THUMB_TUCKED, index: { ...F_EXTENDED, splay: 10 }, middle: { ...F_EXTENDED, splay: -8 },
        ring: F_CURLED, little: F_CURLED
      }),
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_TUCKED, index: { proxFlex: 2, interFlex: 0, distFlex: 0, splay: -4 },
        middle: { proxFlex: 2, interFlex: 0, distFlex: 0, splay: 4 }, ring: F_CURLED, little: F_CURLED
      })
    },
    I: {
      grapheme: 'I', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra I LSEC: Meñique extendido verticalmente hacia arriba; índice, medio y anular cerrados bajo el pulgar.',
      handOrientationB: { pitchDeg: 4, yawDeg: -10, rollDeg: 0, axialTwistDeg: -4 },
      poseB100: buildRightHandPhalangePose({ thumb: THUMB_TUCKED, index: F_CURLED, middle: F_CURLED, ring: F_CURLED, little: F_EXTENDED })
    },
    J: {
      grapheme: 'J', isStaticHold: false, isDynamic: true, opacityMode: 'TRANSITION_70_TO_100',
      localMovement: 'axial_twist', trajectory: { type: 'curved', variant: 'j_curve', amplitudeM: 0.064 },
      repetition: 1, speedFactor: 1.0, contactMode: 'DESPLAZAR',
      description: 'Letra J LSEC: Meñique extendido trazando una trayectoria curva descendente y ascendente hacia adentro en forma de J.',
      handOrientationA: { pitchDeg: 2, yawDeg: -8, rollDeg: 0, axialTwistDeg: 0 },
      handOrientationB: { pitchDeg: 14, yawDeg: -28, rollDeg: -14, axialTwistDeg: -20 },
      poseA70: buildRightHandPhalangePose({ thumb: THUMB_TUCKED, index: F_CURLED, middle: F_CURLED, ring: F_CURLED, little: F_EXTENDED }),
      poseB100: buildRightHandPhalangePose({ thumb: THUMB_TUCKED, index: F_CURLED, middle: F_CURLED, ring: F_CURLED, little: F_EXTENDED })
    },
    K: {
      grapheme: 'K', isStaticHold: false, isDynamic: true, opacityMode: 'TRANSITION_70_TO_100',
      localMovement: 'open_close_fingers', trajectory: { type: 'linear', variant: 'bottom_to_top', amplitudeM: 0.025 },
      repetition: 1, speedFactor: 1.0, contactMode: 'DESPLAZAR',
      description: 'Letra K LSEC: Índice vertical, medio proyectado en ángulo con pulgar apoyado entre ambos y transición ascendente 70%->100%.',
      handOrientationA: { pitchDeg: 4, yawDeg: -24, rollDeg: -6, axialTwistDeg: -8 },
      handOrientationB: { pitchDeg: 8, yawDeg: -32, rollDeg: -10, axialTwistDeg: -14 },
      poseA70: buildRightHandPhalangePose({
        thumb: { metaX: 18, metaY: -22, metaZ: 8, proxX: 4, proxY: -14, proxZ: 8, distZ: 4 },
        index: { ...F_EXTENDED, splay: 10 }, middle: { proxFlex: 26, interFlex: 6, distFlex: 0, splay: -10 },
        ring: F_CURLED, little: F_CURLED
      }),
      poseB100: buildRightHandPhalangePose({
        thumb: { metaX: 22, metaY: -26, metaZ: 12, proxX: 6, proxY: -18, proxZ: 12, distZ: 6 },
        index: { ...F_EXTENDED, splay: 8 }, middle: { proxFlex: 42, interFlex: 8, distFlex: 0, splay: -10 },
        ring: F_CURLED, little: F_CURLED
      })
    },
    L: {
      grapheme: 'L', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra L LSEC: Palma frontal con índice extendido verticalmente y pulgar extendido horizontalmente a 90 grados.',
      handOrientationB: { pitchDeg: 4, yawDeg: 0, rollDeg: 0, axialTwistDeg: 0 },
      poseB100: buildRightHandPhalangePose({ thumb: THUMB_OUT_L, index: F_EXTENDED, middle: F_CURLED, ring: F_CURLED, little: F_CURLED })
    },
    LL: {
      grapheme: 'LL', isStaticHold: false, isDynamic: true, opacityMode: 'TRANSITION_70_TO_100',
      localMovement: 'curved_displacement', trajectory: { type: 'curved', variant: 'left_to_right', amplitudeM: 0.056 },
      repetition: 1, speedFactor: 1.0, contactMode: 'DESPLAZAR',
      description: 'Dígrafo LL LSEC: Configuración de L ejecutando un desplazamiento curvo lateral.',
      handOrientationA: { pitchDeg: 4, yawDeg: 4, rollDeg: 4, axialTwistDeg: 4 },
      handOrientationB: { pitchDeg: 6, yawDeg: -14, rollDeg: -6, axialTwistDeg: -10 },
      poseA70: buildRightHandPhalangePose({ thumb: THUMB_OUT_L, index: F_EXTENDED, middle: F_CURLED, ring: F_CURLED, little: F_CURLED }),
      poseB100: buildRightHandPhalangePose({ thumb: THUMB_OUT_L, index: F_EXTENDED, middle: F_CURLED, ring: F_CURLED, little: F_CURLED })
    },
    M: {
      grapheme: 'M', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra M LSEC: Mano orientada hacia abajo con índice, medio y anular extendidos juntos sobre el pulgar; meñique recogido.',
      handOrientationB: { pitchDeg: 82, yawDeg: -10, rollDeg: -8, axialTwistDeg: -18 },
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_ACROSS_PALM,
        index: { proxFlex: 42, interFlex: 18, distFlex: 8, splay: -5 },
        middle: { proxFlex: 42, interFlex: 18, distFlex: 8, splay: 0 },
        ring: { proxFlex: 44, interFlex: 20, distFlex: 8, splay: 5 }, little: F_CURLED
      })
    },
    N: {
      grapheme: 'N', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra N LSEC: Mano orientada hacia abajo con índice y medio extendidos juntos sobre el pulgar; anular y meñique recogidos.',
      handOrientationB: { pitchDeg: 82, yawDeg: -10, rollDeg: -8, axialTwistDeg: -18 },
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_ACROSS_PALM,
        index: { proxFlex: 42, interFlex: 18, distFlex: 8, splay: -4 },
        middle: { proxFlex: 42, interFlex: 18, distFlex: 8, splay: 4 },
        ring: F_CURLED, little: F_CURLED
      })
    },
    'Ñ': {
      grapheme: 'Ñ', isStaticHold: false, isDynamic: true, opacityMode: 'TRANSITION_70_TO_100',
      localMovement: 'axial_twist', trajectory: { type: 'curved', variant: 'wavy', amplitudeM: 0.052 },
      repetition: 2, speedFactor: 1.0, contactMode: 'DESPLAZAR',
      description: 'Letra Ñ LSEC: Configuración de N con movimiento oscilatorio/curvo de muñeca trazando la virgulilla.',
      handOrientationA: { pitchDeg: 80, yawDeg: -4, rollDeg: -4, axialTwistDeg: -10 },
      handOrientationB: { pitchDeg: 84, yawDeg: -20, rollDeg: -16, axialTwistDeg: -24 },
      poseA70: buildRightHandPhalangePose({
        thumb: THUMB_ACROSS_PALM,
        index: { proxFlex: 42, interFlex: 18, distFlex: 8, splay: -4 },
        middle: { proxFlex: 42, interFlex: 18, distFlex: 8, splay: 4 },
        ring: F_CURLED, little: F_CURLED
      }),
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_ACROSS_PALM,
        index: { proxFlex: 42, interFlex: 18, distFlex: 8, splay: -4 },
        middle: { proxFlex: 42, interFlex: 18, distFlex: 8, splay: 4 },
        ring: F_CURLED, little: F_CURLED
      })
    },
    O: {
      grapheme: 'O', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra O LSEC: Los cuatro dedos curvados uniéndose con la yema del pulgar formando un anillo circular cerrado.',
      handOrientationB: { pitchDeg: 4, yawDeg: 46, rollDeg: 6, axialTwistDeg: 10 },
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_PINCH_F,
        index: { proxFlex: 46, interFlex: 62, distFlex: 44, splay: -4 },
        middle: { proxFlex: 48, interFlex: 64, distFlex: 46, splay: 0 },
        ring: { proxFlex: 48, interFlex: 64, distFlex: 46, splay: 4 },
        little: { proxFlex: 50, interFlex: 62, distFlex: 44, splay: 8 }
      })
    },
    P: {
      grapheme: 'P', isStaticHold: false, isDynamic: true, opacityMode: 'TRANSITION_70_TO_100',
      localMovement: 'open_close_fingers', trajectory: { type: 'linear', variant: 'top_to_bottom', amplitudeM: 0.022 },
      repetition: 1, speedFactor: 1.0, contactMode: 'DESPLAZAR',
      description: 'Letra P LSEC: Configuración en K inclinada con índice horizontal, medio hacia abajo y transición 70%->100%.',
      handOrientationA: { pitchDeg: 32, yawDeg: -34, rollDeg: -48, axialTwistDeg: -16 },
      handOrientationB: { pitchDeg: 42, yawDeg: -42, rollDeg: -56, axialTwistDeg: -24 },
      poseA70: buildRightHandPhalangePose({
        thumb: { metaX: 18, metaY: -22, metaZ: 10, proxX: 4, proxY: -14, proxZ: 12, distZ: 8 },
        index: { ...F_EXTENDED, splay: 6 }, middle: { proxFlex: 52, interFlex: 12, distFlex: 4, splay: -6 },
        ring: F_CURLED, little: F_CURLED
      }),
      poseB100: buildRightHandPhalangePose({
        thumb: { metaX: 22, metaY: -26, metaZ: 14, proxX: 6, proxY: -18, proxZ: 16, distZ: 10 },
        index: { proxFlex: 4, interFlex: 0, distFlex: 0, splay: 2 }, middle: { proxFlex: 68, interFlex: 14, distFlex: 4, splay: -4 },
        ring: F_CURLED, little: F_CURLED
      })
    },
    Q: {
      grapheme: 'Q', isStaticHold: false, isDynamic: true, opacityMode: 'TRANSITION_70_TO_100',
      localMovement: 'open_close_fingers', trajectory: { type: 'linear', variant: 'top_to_bottom', amplitudeM: 0.024 },
      repetition: 1, speedFactor: 1.0, contactMode: 'DESPLAZAR',
      description: 'Letra Q LSEC: Muñeca flexionada hacia abajo con índice y pulgar apuntando hacia abajo en transición de pinza 70%->100%.',
      handOrientationA: { pitchDeg: 72, yawDeg: -18, rollDeg: -62, axialTwistDeg: -22 },
      handOrientationB: { pitchDeg: 78, yawDeg: -24, rollDeg: -68, axialTwistDeg: -28 },
      poseA70: buildRightHandPhalangePose({
        thumb: { metaX: 24, metaY: -18, metaZ: 4, proxX: 4, proxY: -10, proxZ: 4, distZ: 0 },
        index: { proxFlex: 38, interFlex: 6, distFlex: 0, splay: 4 },
        middle: F_CURLED, ring: F_CURLED, little: F_CURLED
      }),
      poseB100: buildRightHandPhalangePose({
        thumb: { metaX: 32, metaY: -28, metaZ: 16, proxX: 8, proxY: -18, proxZ: 18, distZ: 12 },
        index: { proxFlex: 54, interFlex: 12, distFlex: 6, splay: -2 },
        middle: F_CURLED, ring: F_CURLED, little: F_CURLED
      })
    },
    R: {
      grapheme: 'R', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra R LSEC: Palma frontal con índice y medio extendidos hacia arriba, cruzando el dedo medio sobre el índice.',
      handOrientationB: { pitchDeg: 4, yawDeg: -8, rollDeg: 0, axialTwistDeg: 0 },
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_TUCKED, index: { proxFlex: 4, interFlex: 0, distFlex: 0, splay: -8 },
        middle: { proxFlex: 12, interFlex: 8, distFlex: 0, splay: 14, twist: -10 },
        ring: F_CURLED, little: F_CURLED
      })
    },
    RR: {
      grapheme: 'RR', isStaticHold: false, isDynamic: true, opacityMode: 'TRANSITION_70_TO_100',
      localMovement: 'curved_displacement', trajectory: { type: 'curved', variant: 'left_to_right', amplitudeM: 0.054 },
      repetition: 1, speedFactor: 1.0, contactMode: 'DESPLAZAR',
      description: 'Dígrafo RR LSEC: Configuración de R (medio cruzado sobre índice) ejecutando un desplazamiento curvo lateral.',
      handOrientationA: { pitchDeg: 4, yawDeg: -2, rollDeg: 4, axialTwistDeg: 2 },
      handOrientationB: { pitchDeg: 6, yawDeg: -18, rollDeg: -6, axialTwistDeg: -10 },
      poseA70: buildRightHandPhalangePose({
        thumb: THUMB_TUCKED, index: { proxFlex: 4, interFlex: 0, distFlex: 0, splay: -8 },
        middle: { proxFlex: 12, interFlex: 8, distFlex: 0, splay: 14, twist: -10 },
        ring: F_CURLED, little: F_CURLED
      }),
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_TUCKED, index: { proxFlex: 4, interFlex: 0, distFlex: 0, splay: -8 },
        middle: { proxFlex: 12, interFlex: 8, distFlex: 0, splay: 14, twist: -10 },
        ring: F_CURLED, little: F_CURLED
      })
    },
    S: {
      grapheme: 'S', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra S LSEC: Puño cerrado compacto con el pulgar cruzado frontalmente sobre las falanges intermedias.',
      handOrientationB: { pitchDeg: 4, yawDeg: -6, rollDeg: 0, axialTwistDeg: 0 },
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_FRONT_S,
        index: { proxFlex: 86, interFlex: 95, distFlex: 78, splay: 0 },
        middle: { proxFlex: 86, interFlex: 95, distFlex: 78, splay: 0 },
        ring: { proxFlex: 86, interFlex: 95, distFlex: 78, splay: 0 },
        little: { proxFlex: 86, interFlex: 95, distFlex: 78, splay: 0 }
      })
    },
    T: {
      grapheme: 'T', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra T LSEC: Medio, anular y meñique extendidos verticalmente en aducción; índice flexionado junto al pulgar.',
      handOrientationB: { pitchDeg: 4, yawDeg: -10, rollDeg: 0, axialTwistDeg: 0 },
      poseB100: buildRightHandPhalangePose({
        thumb: { metaX: 28, metaY: -36, metaZ: 28, proxX: 8, proxY: -24, proxZ: 36, distZ: 28 },
        index: { proxFlex: 68, interFlex: 72, distFlex: 45, splay: -8 },
        middle: { ...F_EXTENDED, splay: -2 }, ring: { ...F_EXTENDED, splay: 4 }, little: { ...F_EXTENDED, splay: 9 }
      })
    },
    U: {
      grapheme: 'U', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra U LSEC: Palma frontal con índice y medio extendidos verticalmente y unidos en aducción cerrada.',
      handOrientationB: { pitchDeg: 4, yawDeg: -4, rollDeg: 0, axialTwistDeg: 0 },
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_TUCKED, index: { ...F_EXTENDED, splay: -5 }, middle: { ...F_EXTENDED, splay: 4 },
        ring: F_CURLED, little: F_CURLED
      })
    },
    V: {
      grapheme: 'V', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra V LSEC: Palma frontal con índice y medio extendidos y separados en abducción formando una V.',
      handOrientationB: { pitchDeg: 4, yawDeg: -4, rollDeg: 0, axialTwistDeg: 0 },
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_TUCKED, index: { ...F_EXTENDED, splay: 14 }, middle: { ...F_EXTENDED, splay: -12 },
        ring: F_CURLED, little: F_CURLED
      })
    },
    W: {
      grapheme: 'W', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra W LSEC: Palma frontal con índice, medio y anular extendidos y separados formando una W.',
      handOrientationB: { pitchDeg: 4, yawDeg: -4, rollDeg: 0, axialTwistDeg: 0 },
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_TUCKED, index: { ...F_EXTENDED, splay: 16 }, middle: { ...F_EXTENDED, splay: 1 },
        ring: { ...F_EXTENDED, splay: -15 }, little: F_CURLED
      })
    },
    X: {
      grapheme: 'X', isStaticHold: false, isDynamic: true, opacityMode: 'TRANSITION_70_TO_100',
      localMovement: 'open_close_fingers', trajectory: { type: 'curved', variant: 'curved_displacement', amplitudeM: 0.036 },
      repetition: 1, speedFactor: 1.0, contactMode: 'DESPLAZAR',
      description: 'Letra X LSEC: Dedo índice en gancho ejecutando una transición de retracción y desplazamiento 70%->100%.',
      handOrientationA: { pitchDeg: 6, yawDeg: -42, rollDeg: -6, axialTwistDeg: -10 },
      handOrientationB: { pitchDeg: 14, yawDeg: -50, rollDeg: -12, axialTwistDeg: -18 },
      poseA70: buildRightHandPhalangePose({
        thumb: THUMB_TUCKED, index: { proxFlex: 14, interFlex: 52, distFlex: 46, splay: 0 },
        middle: F_CURLED, ring: F_CURLED, little: F_CURLED
      }),
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_TUCKED, index: { proxFlex: 24, interFlex: 86, distFlex: 80, splay: 0 },
        middle: F_CURLED, ring: F_CURLED, little: F_CURLED
      })
    },
    Y: {
      grapheme: 'Y', isStaticHold: true, isDynamic: false, opacityMode: 'STATIC_100',
      description: 'Letra Y LSEC: Palma frontal con extensión y abducción simultánea de pulgar y meñique; índice, medio y anular cerrados.',
      handOrientationB: { pitchDeg: 4, yawDeg: -8, rollDeg: 0, axialTwistDeg: 0 },
      poseB100: buildRightHandPhalangePose({
        thumb: THUMB_OUT_L, index: F_CURLED, middle: F_CURLED, ring: F_CURLED,
        little: { ...F_EXTENDED, splay: -18 }
      })
    },
    Z: {
      grapheme: 'Z', isStaticHold: false, isDynamic: true, opacityMode: 'TRANSITION_70_TO_100',
      localMovement: 'zigzag_stroke', trajectory: { type: 'linear', variant: 'zigzag', amplitudeM: 0.068 },
      repetition: 1, speedFactor: 1.0, contactMode: 'DESPLAZAR',
      description: 'Letra Z LSEC: Índice extendido ejecutando un trazo lineal en zigzag de 3 segmentos en el plano frontal.',
      handOrientationA: { pitchDeg: 6, yawDeg: -16, rollDeg: -4, axialTwistDeg: -4 },
      handOrientationB: { pitchDeg: 10, yawDeg: -24, rollDeg: -8, axialTwistDeg: -10 },
      poseA70: buildRightHandPhalangePose({ thumb: THUMB_TUCKED, index: F_EXTENDED, middle: F_CURLED, ring: F_CURLED, little: F_CURLED }),
      poseB100: buildRightHandPhalangePose({ thumb: THUMB_TUCKED, index: F_EXTENDED, middle: F_CURLED, ring: F_CURLED, little: F_CURLED })
    }
  };

  for (const g of LSEC_FINGERSPELLING_GRAPHEMES) {
    const d = defs[g];
    if (!d.poseA70) d.poseA70 = d.poseB100;
    if (!d.handOrientationA) d.handOrientationA = d.handOrientationB;
    if (!d.trajectory) d.trajectory = { type: 'none', variant: 'static_hold', amplitudeM: 0.0 };
    if (!d.repetition) d.repetition = 1;
    if (!d.speedFactor) d.speedFactor = 1.0;
    if (!d.contactMode) d.contactMode = 'DESPLAZAR';
  }
  return Object.freeze(defs);
}

export const LSEC_FINGERSPELLING_CATALOG = buildCatalogDefinitions();

const VOWEL_BASE_MAP = Object.freeze({
  'Á': 'A', 'À': 'A', 'Ä': 'A', 'Â': 'A',
  'É': 'E', 'È': 'E', 'Ë': 'E', 'Ê': 'E',
  'Í': 'I', 'Ì': 'I', 'Ï': 'I', 'Î': 'I',
  'Ó': 'O', 'Ò': 'O', 'Ö': 'O', 'Ô': 'O',
  'Ú': 'U', 'Ù': 'U', 'Ü': 'U', 'Û': 'U'
});

/**
 * Tokeniza una palabra, glosa deletreada o sigla detectando dígrafos oficiales
 * (CH, LL, RR), preservando Ñ en NFC y marcando micro-rearticulación en letras repetidas.
 */
export function tokenizeLSECFingerspelling(rawInput) {
  if (!rawInput || typeof rawInput !== 'string') return [];

  let cleaned = rawInput.normalize('NFC').trim().toUpperCase();
  cleaned = cleaned.replace(/^(DACTILOLOGIA|DACTILOLOGÍA|DACT|FS|LETRA)[\s:_-]+/i, '').trim();

  const compactChars = cleaned.replace(/[\s\-_.]+/g, '');
  if (!compactChars) return [];

  const tokens = [];
  let i = 0;
  while (i < compactChars.length) {
    const ch1 = compactChars[i];
    const ch2 = i + 1 < compactChars.length ? compactChars[i + 1] : '';
    const pair = ch1 + ch2;

    if (pair === 'CH' || pair === 'LL' || pair === 'RR') {
      const prev = tokens.length > 0 ? tokens[tokens.length - 1] : null;
      const isRepeat = Boolean(prev && prev.grapheme === pair);
      tokens.push({
        index: tokens.length, grapheme: pair, displayChar: pair,
        isDigraph: true, isStaticHold: false, isDynamic: true,
        isRepeatedConsecutive: isRepeat, microRearticulation: isRepeat
      });
      i += 2;
      continue;
    }

    const mappedGrapheme = VOWEL_BASE_MAP[ch1] || ch1;
    if (LSEC_FINGERSPELLING_CATALOG[mappedGrapheme]) {
      const spec = LSEC_FINGERSPELLING_CATALOG[mappedGrapheme];
      const prev = tokens.length > 0 ? tokens[tokens.length - 1] : null;
      const isRepeat = Boolean(prev && prev.grapheme === mappedGrapheme);
      tokens.push({
        index: tokens.length, grapheme: mappedGrapheme, displayChar: ch1,
        isDigraph: false, isStaticHold: spec.isStaticHold, isDynamic: spec.isDynamic,
        isRepeatedConsecutive: isRepeat, microRearticulation: isRepeat
      });
    }
    i += 1;
  }

  return tokens;
}
