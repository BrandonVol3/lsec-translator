/**
 * LSEC Studio — Primitivas Matemáticas y Biomecánicas de Dactilología LSEC
 *
 * Codifica matemáticamente las reglas del documento oficial ilustrado
 * `Guia-Uso-ilustraciones.pdf` (páginas 2 a 9) para el avatar humanoide
 * VRM 1.0 de 54 huesos (`Avatar/LSEC-Interpreter-Female.vrm`):
 *
 * 1. Estados temporales por opacidad (70% inicial -> 100% final, mano estática c)
 *    y secuencias multi-etapa (A -> B en [0.0, 0.5] y [0.5, 1.0]) (Páginas 2 y 3).
 * 2. Sistema de referencia espacial (ARRIBA +Y, ABAJO -Y, ADELANTE +Z, ATRÁS -Z,
 *    AFUERA -X, ADENTRO +X) y Cinemática Inversa Analítica de Dos Huesos
 *    (Two-Bone Analytical IK) con margen anti-colisión >= 2 cm respecto al pecho
 *    y no oclusión del rostro (Página 9).
 * 3. Primitivas paramétricas de trayectoria (lineal, zigzag, curva Bézier,
 *    ondulada, circular, espiral), giro axial repartido antebrazo/muñeca con
 *    umbral anti-flip < 55°, repetición (1x, 2x, 3x), velocidad (1.0 / 0.65)
 *    y modo de contacto (DESPLAZAR vs DESLIZAR) (Páginas 4 y 5).
 * 4. Puntos anatómicos de referencia de mano, cuerpo y rostro (Páginas 6, 7 y 8).
 * 5. Filtro One-Euro en SO(3) (fc = 1.0 Hz, beta = 0.005) y SLERP con continuidad
 *    de hemisferio (q_t · q_{t-1} >= 0).
 */

/* ========================================================================== */
/* 1. SISTEMA DE REFERENCIA ESPACIAL Y CONSTANTES MÉTRICAS VRM 1.0 (PÁG. 9)   */
/* ========================================================================== */

export const CHEST_SURFACE_Z = 0.1373;
export const FACIAL_SURFACE_Z = 0.0893;
export const MIN_CHEST_CLEARANCE_M = 0.02; // >= 2 cm requerido por especificación
export const SAFE_FINGERSPELLING_MIN_Z = CHEST_SURFACE_Z + MIN_CHEST_CLEARANCE_M + 0.038; // 0.1953 m (incluye margen falángico)

export const AVATAR_UPPER_ARM_LEN = 0.2199;
export const AVATAR_FOREARM_LEN = 0.2147;
export const MAX_WRIST_STEP_DEG = 48.0; // Estricto < 55° para evitar inversiones bruscas

// Posiciones de reposo exactas del esqueleto VRM 1.0 (LSEC-Interpreter-Female.vrm)
export const VRM_RIGHT_ARM_REST_POS = Object.freeze({
  upperChest: [0.0, 1.180723, 0.004497],
  rightShoulder: [-0.022395, 1.28641, -0.025472],
  rightUpperArm: [-0.108556, 1.27415, -0.025472],
  rightLowerArm: [-0.328409, 1.274149, -0.025472],
  rightHand: [-0.543094, 1.274152, -0.025459]
});

/**
 * Espacio neutro de dactilología frente al hemitórax superior derecho:
 * - X = -0.172 m (costado pectoral derecho, fuera del cono visual del rostro [-0.14, 0.14])
 * - Y = 1.225 m (debajo del mentón 1.28 m, altura de hemitórax superior)
 * - Z = 0.215 m (7.77 cm por delante de la superficie torácica CHEST_SURFACE_Z = 0.1373 m)
 */
export const NEUTRAL_FINGERSPELLING_LOCUS = Object.freeze([-0.172, 1.225, 0.215]);

/**
 * Ejes espaciales oficiales según Página 9 de Guia-Uso-ilustraciones.pdf
 * (Leídos con el dorso hacia el señante y la palma hacia adelante):
 */
export const LSEC_PDF_SPATIAL_AXES = Object.freeze({
  ARRIBA: Object.freeze([0.0, 1.0, 0.0]),    // +Y vertical ascendente
  ABAJO: Object.freeze([0.0, -1.0, 0.0]),    // -Y vertical descendente
  ADELANTE: Object.freeze([0.0, 0.0, 1.0]),  // +Z sagital hacia la cámara
  ATRAS: Object.freeze([0.0, 0.0, -1.0]),    // -Z sagital hacia el pecho del avatar
  AFUERA: Object.freeze([-1.0, 0.0, 0.0]),   // -X transversal hacia el costado externo derecho
  ADENTRO: Object.freeze([1.0, 0.0, 0.0])    // +X transversal hacia la línea media del torso
});

/* ========================================================================== */
/* 2. PUNTOS ANATÓMICOS DE REFERENCIA (PÁGINAS 6, 7 Y 8 DEL PDF)              */
/* ========================================================================== */

export const LSEC_PDF_ANATOMICAL_POINTS = Object.freeze({
  MANO: Object.freeze({
    menique: 'rightLittleDistal',
    anular: 'rightRingDistal',
    medio: 'rightMiddleDistal',
    indice: 'rightIndexDistal',
    pulgar: 'rightThumbDistal',
    borde_interno_dedo: 'radial_finger_border',
    borde_externo_dedo: 'ulnar_finger_border',
    unas: 'dorsal_distal_nail_bed',
    yema: 'volar_distal_fingertip_pad',
    nudillos: 'metacarpophalangeal_joints',
    falanges: 'proximal_intermediate_distal_phalanges',
    palma: 'volar_palm_surface',
    dorso: 'dorsal_hand_surface',
    borde_interno_mano: 'radial_hand_border_thumb_side',
    borde_externo_mano: 'ulnar_hand_border_little_side',
    base_mano: 'carpal_heel_of_hand',
    muneca: 'rightHand'
  }),
  CUERPO: Object.freeze({
    cabeza: [0.0, 1.42, 0.04],
    cuello: [0.0, 1.31, 0.02],
    hombro: [-0.11, 1.27, 0.04],
    pecho: [-0.08, 1.18, 0.16],
    brazo: [-0.18, 1.15, 0.06],
    codo: [-0.24, 1.06, 0.08],
    mano: [-0.172, 1.225, 0.215],
    cintura: [-0.12, 0.98, 0.14],
    vientre: [0.0, 0.96, 0.16],
    abdomen: [0.0, 1.02, 0.16],
    pierna: [-0.08, 0.72, 0.08]
  }),
  ROSTRO: Object.freeze({
    cabeza: [0.0, 1.44, 0.06],
    frente: [0.0, 1.46, 0.09],
    sien: [-0.06, 1.44, 0.06],
    ceja: [-0.03, 1.44, 0.095],
    pomulo: [-0.045, 1.39, 0.09],
    oreja: [-0.08, 1.40, 0.01],
    nariz: [0.0, 1.40, 0.105],
    mejilla: [-0.045, 1.36, 0.09],
    boca: [0.0, 1.35, 0.098],
    labio: [0.0, 1.35, 0.10],
    comisura_boca: [-0.025, 1.35, 0.095],
    dientes: [0.0, 1.35, 0.094],
    menton: [0.0, 1.315, 0.095],
    cara: [0.0, 1.39, 0.095]
  })
});

/* ========================================================================== */
/* 3. REGLAS DE OPACIDAD, VELOCIDAD, REPETICIÓN Y CONTACTO (PÁGS. 2, 3 Y 5)   */
/* ========================================================================== */

export const LSEC_PDF_MOVEMENT_PRIMITIVES = Object.freeze({
  OPACITY_STATES: Object.freeze({
    INITIAL_A_70: 0.70, // Posición inicial (a - Opacidad 70%) en t = 0.0 del stroke
    FINAL_B_100: 1.00,  // Posición final (b - Opacidad 100%) en t = 1.0 del stroke
    STATIC_C_100: 1.00  // Mano estática (c - Opacidad 100% sostenida)
  }),
  REPETITION: Object.freeze({
    SINGLE: 1, // Flecha simple: 1 vez
    DOUBLE: 2, // Flecha doble: 2 veces
    TRIPLE: 3  // Flecha triple: varias veces (oscilación >= 3 ciclos)
  }),
  SPEED_FACTOR: Object.freeze({
    NORMAL_CONTINUOUS: 1.00,  // Flecha de trazo continuo: velocidad normal
    SLOW_SEGMENTED: 0.65      // Flecha de trazo segmentado/punteado: menor velocidad
  }),
  CONTACT_MODE: Object.freeze({
    DESPLAZAR: 'DESPLAZAR',   // Movimiento en el espacio libre sin tocar otra parte
    DESLIZAR: 'DESLIZAR'      // Movimiento rozando sobre otra parte del cuerpo/mano
  })
});

export const RIGHT_HAND_PHALANX_BONES = Object.freeze([
  'rightThumbMetacarpal',
  'rightThumbProximal',
  'rightThumbDistal',
  'rightIndexProximal',
  'rightIndexIntermediate',
  'rightIndexDistal',
  'rightMiddleProximal',
  'rightMiddleIntermediate',
  'rightMiddleDistal',
  'rightRingProximal',
  'rightRingIntermediate',
  'rightRingDistal',
  'rightLittleProximal',
  'rightLittleIntermediate',
  'rightLittleDistal'
]);

/* ========================================================================== */
/* 4. ÁLGEBRA EN SO(3), CONTINUIDAD ANTIPODAL Y FILTRO ONE-EURO               */
/* ========================================================================== */

export const Q_IDENTITY = Object.freeze([0, 0, 0, 1]);

export function deg2rad(deg) {
  return deg * (Math.PI / 180.0);
}

export function rad2deg(rad) {
  return rad * (180.0 / Math.PI);
}

export function quatNormalize(q) {
  if (!q || !Array.isArray(q)) return [0, 0, 0, 1];
  const x = Number(q[0]) || 0;
  const y = Number(q[1]) || 0;
  const z = Number(q[2]) || 0;
  const w = Number(q[3]);
  const wSafe = Number.isFinite(w) ? w : 1;
  const n = Math.hypot(x, y, z, wSafe);
  if (n < 1e-9) return [0, 0, 0, 1];
  return [x / n, y / n, z / n, wSafe / n];
}

export function quatConjugate(q) {
  const qn = quatNormalize(q);
  return [-qn[0], -qn[1], -qn[2], qn[3]];
}

export function quatMultiply(a, b) {
  const [x1, y1, z1, w1] = quatNormalize(a);
  const [x2, y2, z2, w2] = quatNormalize(b);
  return quatNormalize([
    w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
    w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
    w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2
  ]);
}

export function eulerDegToQuat(xDeg, yDeg, zDeg, order = 'XYZ') {
  const hx = deg2rad(Number(xDeg) || 0) * 0.5;
  const hy = deg2rad(Number(yDeg) || 0) * 0.5;
  const hz = deg2rad(Number(zDeg) || 0) * 0.5;

  const qx = [Math.sin(hx), 0, 0, Math.cos(hx)];
  const qy = [0, Math.sin(hy), 0, Math.cos(hy)];
  const qz = [0, 0, Math.sin(hz), Math.cos(hz)];

  switch (order) {
    case 'ZXY':
      return quatMultiply(quatMultiply(qz, qx), qy);
    case 'YXZ':
      return quatMultiply(quatMultiply(qy, qx), qz);
    case 'ZYX':
      return quatMultiply(quatMultiply(qz, qy), qx);
    case 'XYZ':
    default:
      return quatMultiply(quatMultiply(qx, qy), qz);
  }
}

/**
 * Garantiza continuidad de hemisferio antipodal: qCurr · qPrev >= 0.
 */
export function ensureHemisphereContinuity(qCurr, qPrev) {
  const qc = quatNormalize(qCurr);
  if (!qPrev) return qc;
  const qp = quatNormalize(qPrev);
  const dot = qc[0] * qp[0] + qc[1] * qp[1] + qc[2] * qp[2] + qc[3] * qp[3];
  if (dot < 0.0) {
    return [-qc[0], -qc[1], -qc[2], -qc[3]];
  }
  return qc;
}

/**
 * SLERP geodésico en SO(3) con alineación antipodal automática.
 */
export function slerpQuatAntipodal(qStart, qEnd, alpha) {
  const t = Math.max(0.0, Math.min(1.0, Number(alpha) || 0.0));
  const qa = quatNormalize(qStart);
  const qb = ensureHemisphereContinuity(qEnd, qa);
  let dot = qa[0] * qb[0] + qa[1] * qb[1] + qa[2] * qb[2] + qa[3] * qb[3];
  dot = Math.max(-1.0, Math.min(1.0, dot));

  if (dot > 0.9995) {
    return quatNormalize([
      qa[0] + t * (qb[0] - qa[0]),
      qa[1] + t * (qb[1] - qa[1]),
      qa[2] + t * (qb[2] - qa[2]),
      qa[3] + t * (qb[3] - qa[3])
    ]);
  }

  const theta0 = Math.acos(dot);
  const sinTheta0 = Math.sin(theta0);
  const theta = theta0 * t;
  const sinTheta = Math.sin(theta);
  const s0 = Math.cos(theta) - (dot * sinTheta) / sinTheta0;
  const s1 = sinTheta / sinTheta0;

  return quatNormalize([
    s0 * qa[0] + s1 * qb[0],
    s0 * qa[1] + s1 * qb[1],
    s0 * qa[2] + s1 * qb[2],
    s0 * qa[3] + s1 * qb[3]
  ]);
}

/**
 * Distancia angular geodésica en grados entre dos cuaterniones unitarios.
 */
export function quatAngularDistanceDeg(q1, q2) {
  const qa = quatNormalize(q1);
  const qb = ensureHemisphereContinuity(q2, qa);
  const dot = Math.max(-1.0, Math.min(1.0, qa[0] * qb[0] + qa[1] * qb[1] + qa[2] * qb[2] + qa[3] * qb[3]));
  return rad2deg(2.0 * Math.acos(dot));
}

/**
 * Limita el salto angular entre dos muestras consecutivas a maxStepDeg (< 55°).
 */
export function clampQuaternionStepDeg(qPrev, qTarget, maxStepDeg = MAX_WRIST_STEP_DEG) {
  if (!qPrev) return quatNormalize(qTarget);
  const alignedTarget = ensureHemisphereContinuity(qTarget, qPrev);
  const distDeg = quatAngularDistanceDeg(qPrev, alignedTarget);
  if (distDeg <= maxStepDeg || distDeg < 1e-6) {
    return alignedTarget;
  }
  const ratio = maxStepDeg / distDeg;
  return slerpQuatAntipodal(qPrev, alignedTarget, ratio);
}

/**
 * Filtro One-Euro en SO(3) para suavizado cinemático adaptativo (fc = 1.0 Hz, beta = 0.005).
 */
export class OneEuroQuaternionFilter {
  constructor(minCutoffHz = 1.0, beta = 0.005, dCutoffHz = 1.0) {
    this.minCutoffHz = minCutoffHz;
    this.beta = beta;
    this.dCutoffHz = dCutoffHz;
    this._prevQuat = null;
    this._prevTime = null;
    this._prevSpeedRadSec = 0.0;
  }

  reset() {
    this._prevQuat = null;
    this._prevTime = null;
    this._prevSpeedRadSec = 0.0;
  }

  _alpha(cutoffHz, dt) {
    const tau = 1.0 / (2.0 * Math.PI * Math.max(1e-4, cutoffHz));
    return 1.0 / (1.0 + tau / Math.max(1e-4, dt));
  }

  filter(qRaw, timestampSec) {
    const qNorm = quatNormalize(qRaw);
    if (!this._prevQuat || this._prevTime === null) {
      this._prevQuat = qNorm;
      this._prevTime = timestampSec;
      return qNorm;
    }
    const dt = Math.max(1.0 / 120.0, timestampSec - this._prevTime);
    this._prevTime = timestampSec;

    const qAligned = ensureHemisphereContinuity(qNorm, this._prevQuat);
    const instAngleRad = deg2rad(quatAngularDistanceDeg(this._prevQuat, qAligned));
    const instSpeed = instAngleRad / dt;

    const alphaD = this._alpha(this.dCutoffHz, dt);
    const filteredSpeed = alphaD * instSpeed + (1.0 - alphaD) * this._prevSpeedRadSec;
    this._prevSpeedRadSec = filteredSpeed;

    const cutoff = this.minCutoffHz + this.beta * Math.abs(filteredSpeed);
    const alphaQ = this._alpha(cutoff, dt);
    const qFiltered = slerpQuatAntipodal(this._prevQuat, qAligned, alphaQ);
    const qSafe = clampQuaternionStepDeg(this._prevQuat, qFiltered, MAX_WRIST_STEP_DEG);
    this._prevQuat = qSafe;
    return qSafe;
  }
}

/* ========================================================================== */
/* 5. CINEMÁTICA INVERSA ANALÍTICA DE DOS HUESOS (TWO-BONE ANALYTICAL IK)     */
/* ========================================================================== */

/**
 * Garantiza que la posición espacial de la muñeca respete:
 * 1) Margen anti-colisión >= 2 cm frente al pecho (Z >= SAFE_FINGERSPELLING_MIN_Z).
 * 2) No oclusión del rostro (fuera de X in [-0.135, 0.135] cuando Y > 1.27 m).
 */
export function enforceFingerspellingCollisionFreeLocus(pos, options = {}) {
  const minZ = options.minZ ?? SAFE_FINGERSPELLING_MIN_Z;
  let x = Number(pos[0]);
  let y = Number(pos[1]);
  let z = Number(pos[2]);

  // Límite espacial ergonómico frente al hemitórax superior derecho
  x = Math.max(-0.30, Math.min(-0.07, x));
  y = Math.max(1.08, Math.min(1.31, y));
  z = Math.max(minZ, Math.min(0.32, z));

  // Evitar oclusión de la zona facial (Y > 1.265 m requiere mantener X <= -0.145 m)
  if (y > 1.265 && x > -0.145) {
    x = -0.145;
  }
  return [x, y, z];
}

// Orientación mundial canónica exacta en SO(3) de la mano derecha VRM 1.0 con:
// - Dedos (-X en T-pose) apuntando hacia ARRIBA (+Y)
// - Palma (-Y en T-pose) mirando hacia ADELANTE (+Z)
// - Borde radial/pulgar (+Z en T-pose) apuntando hacia ADENTRO (+X)
const Q_CANONICAL_RH_WORLD = [-0.5, 0.5, -0.5, 0.5];

/**
 * Cuaternión de arco mínimo que rota el vector unitario vFrom al vector unitario vTo.
 */
function quatFromUnitVectors(vFrom, vTo) {
  const dot = vFrom[0] * vTo[0] + vFrom[1] * vTo[1] + vFrom[2] * vTo[2];
  if (dot < -0.999999) {
    return [0.0, 1.0, 0.0, 0.0];
  }
  const cx = vFrom[1] * vTo[2] - vFrom[2] * vTo[1];
  const cy = vFrom[2] * vTo[0] - vFrom[0] * vTo[2];
  const cz = vFrom[0] * vTo[1] - vFrom[1] * vTo[0];
  const w = 1.0 + dot;
  return quatNormalize([cx, cy, cz, w]);
}

/**
 * Rota un vector 3D v por un cuaternión unitario q = [x, y, z, w].
 */
function rotateVec3ByQuat(v, q) {
  const [qx, qy, qz, qw] = q;
  const [vx, vy, vz] = v;
  const tx = 2.0 * (qy * vz - qz * vy);
  const ty = 2.0 * (qz * vx - qx * vz);
  const tz = 2.0 * (qx * vy - qy * vx);
  return [
    vx + qw * tx + (qy * tz - qz * ty),
    vy + qw * ty + (qz * tx - qx * tz),
    vz + qw * tz + (qx * ty - qy * tx)
  ];
}

/**
 * Resuelve analíticamente `rightShoulder`, `rightUpperArm`, `rightLowerArm` y `rightHand`
 * para posicionar la mano derecha exactamente en `targetWristPos` con orientación palmar
 * `handOrientation` y giro axial repartido entre antebrazo y muñeca (Página 5 y Página 9 del PDF).
 *
 * @param {number[]} targetWristPos - Posición 3D objetivo [x, y, z] en metros VRM
 * @param {object} [handOrientation] - { pitchDeg, yawDeg, rollDeg, axialTwistDeg }
 * @param {object} [prevArmState] - Cuaterniones previos para continuidad y anti-flip
 */
export function solveRightArmTwoBoneIK(targetWristPos, handOrientation = {}, prevArmState = null) {
  const pSafe = enforceFingerspellingCollisionFreeLocus(targetWristPos);
  const pClavicle = VRM_RIGHT_ARM_REST_POS.rightShoulder;
  const vClavToShoulderRest = [
    VRM_RIGHT_ARM_REST_POS.rightUpperArm[0] - pClavicle[0],
    VRM_RIGHT_ARM_REST_POS.rightUpperArm[1] - pClavicle[1],
    VRM_RIGHT_ARM_REST_POS.rightUpperArm[2] - pClavicle[2]
  ];

  // 1. Ritmo escapulohumeral suave en rightShoulder
  const dx = pSafe[0] - NEUTRAL_FINGERSPELLING_LOCUS[0];
  const dy = pSafe[1] - NEUTRAL_FINGERSPELLING_LOCUS[1];
  const dz = pSafe[2] - NEUTRAL_FINGERSPELLING_LOCUS[2];

  const shElevDeg = Math.max(-3.0, Math.min(6.0, 1.5 + dy * 18.0));
  const shProtrDeg = Math.max(-3.0, Math.min(6.0, 1.5 + dz * 14.0 + dx * 10.0));
  let qRightShoulder = eulerDegToQuat(0.0, shProtrDeg, -shElevDeg, 'XYZ');

  const vClavRotated = rotateVec3ByQuat(vClavToShoulderRest, qRightShoulder);
  const pShoulder = [
    pClavicle[0] + vClavRotated[0],
    pClavicle[1] + vClavRotated[1],
    pClavicle[2] + vClavRotated[2]
  ];
  const pWrist = pSafe;

  // 2. Ley de los cosenos analítica (Two-Bone Analytical IK) sobre brazo y antebrazo
  const Lu = AVATAR_UPPER_ARM_LEN;
  const Lf = AVATAR_FOREARM_LEN;
  const vSW = [pWrist[0] - pShoulder[0], pWrist[1] - pShoulder[1], pWrist[2] - pShoulder[2]];
  const distRaw = Math.hypot(vSW[0], vSW[1], vSW[2]) || 1e-6;
  const minReach = Math.abs(Lu - Lf) * 1.02;
  const maxReach = (Lu + Lf) * 0.992;
  const D = Math.max(minReach, Math.min(maxReach, distRaw));

  const uSW = [vSW[0] / distRaw, vSW[1] / distRaw, vSW[2] / distRaw];
  const cosAlpha = Math.max(-1.0, Math.min(1.0, (Lu * Lu + D * D - Lf * Lf) / (2.0 * Lu * D)));
  const sinAlpha = Math.sqrt(Math.max(0.0, 1.0 - cosAlpha * cosAlpha));

  // Vector polar anatómico del codo derecho (hacia abajo -Y, afuera -X y ligeramente atrás -Z)
  const pLen = Math.hypot(-0.45, -0.85, -0.25);
  const poleVec = [-0.45 / pLen, -0.85 / pLen, -0.25 / pLen];
  const dotPole = poleVec[0] * uSW[0] + poleVec[1] * uSW[1] + poleVec[2] * uSW[2];
  const poleProj = [
    poleVec[0] - dotPole * uSW[0],
    poleVec[1] - dotPole * uSW[1],
    poleVec[2] - dotPole * uSW[2]
  ];
  const projNorm = Math.hypot(poleProj[0], poleProj[1], poleProj[2]);
  const uPole = projNorm > 1e-4 ? [poleProj[0] / projNorm, poleProj[1] / projNorm, poleProj[2] / projNorm] : [0, -1, 0];

  const pElbow = [
    pShoulder[0] + uSW[0] * (Lu * cosAlpha) + uPole[0] * (Lu * sinAlpha),
    pShoulder[1] + uSW[1] * (Lu * cosAlpha) + uPole[1] * (Lu * sinAlpha),
    pShoulder[2] + uSW[2] * (Lu * cosAlpha) + uPole[2] * (Lu * sinAlpha)
  ];

  // 3. Construcción exacta en SO(3) de rightUpperArm y rightLowerArm a partir de uUA y uFA
  const vSE = [pElbow[0] - pShoulder[0], pElbow[1] - pShoulder[1], pElbow[2] - pShoulder[2]];
  const lenSE = Math.hypot(vSE[0], vSE[1], vSE[2]) || 1e-6;
  const uUA = [vSE[0] / lenSE, vSE[1] / lenSE, vSE[2] / lenSE];

  const vEW = [pWrist[0] - pElbow[0], pWrist[1] - pElbow[1], pWrist[2] / 1.0 - pElbow[2]];
  const lenEW = Math.hypot(vEW[0], vEW[1], vEW[2]) || 1e-6;
  const uFA = [vEW[0] / lenEW, vEW[1] / lenEW, vEW[2] / lenEW];

  const qWorldRua = quatFromUnitVectors([-1.0, 0.0, 0.0], uUA);
  let qRightUpperArm = quatMultiply(quatConjugate(qRightShoulder), qWorldRua);

  // Reparto del giro axial (pronación/supinación) entre rightLowerArm (42%) y rightHand (58%)
  const axialTwistDeg = Number(handOrientation.axialTwistDeg) || 0.0;
  const pitchDeg = Number(handOrientation.pitchDeg) || 0.0;
  const yawDeg = Number(handOrientation.yawDeg) || 0.0;
  const rollDeg = Number(handOrientation.rollDeg) || 0.0;

  const sharedForearmTwistDeg = Math.max(-38.0, Math.min(38.0, axialTwistDeg * 0.42));
  const residualHandTwistDeg = axialTwistDeg - sharedForearmTwistDeg;

  const qWorldRlaBase = quatFromUnitVectors([-1.0, 0.0, 0.0], uFA);
  // Torsión axial local del antebrazo alrededor de su eje longitudinal (-X en T-pose)
  const qForearmAxialLocal = eulerDegToQuat(-sharedForearmTwistDeg, 0.0, 0.0, 'XYZ');
  const qWorldRla = quatMultiply(qWorldRlaBase, qForearmAxialLocal);
  let qRightLowerArm = quatMultiply(quatConjugate(qWorldRua), qWorldRla);

  // Orientación mundial objetivo de la mano derecha a partir del marco de la Página 9
  const qHandOffsetWorld = eulerDegToQuat(pitchDeg, yawDeg, rollDeg + residualHandTwistDeg, 'XYZ');
  const qTargetHandWorld = quatMultiply(qHandOffsetWorld, Q_CANONICAL_RH_WORLD);

  // Cuaternión local de muñeca: q_rh_local = q_world_rla^{-1} * q_target_hand_world
  let qRightHand = quatMultiply(quatConjugate(qWorldRla), qTargetHandWorld);

  if (prevArmState) {
    qRightShoulder = clampQuaternionStepDeg(prevArmState.rightShoulder, qRightShoulder, MAX_WRIST_STEP_DEG);
    qRightUpperArm = clampQuaternionStepDeg(prevArmState.rightUpperArm, qRightUpperArm, MAX_WRIST_STEP_DEG);
    qRightLowerArm = clampQuaternionStepDeg(prevArmState.rightLowerArm, qRightLowerArm, MAX_WRIST_STEP_DEG);
    qRightHand = clampQuaternionStepDeg(prevArmState.rightHand, qRightHand, MAX_WRIST_STEP_DEG);
  }

  return {
    rightShoulder: qRightShoulder,
    rightUpperArm: qRightUpperArm,
    rightLowerArm: qRightLowerArm,
    rightHand: qRightHand,
    wristWorldPos: pSafe,
    elbowWorldPos: pElbow
  };
}

/* ========================================================================== */
/* 6. GENERADORES PARAMÉTRICOS DE TRAYECTORIA (PÁGINAS 4 Y 5 DEL PDF)         */
/* ========================================================================== */

/**
 * Modula la fase normalizada u in [0, 1] según repetición (1x, 2x, 3x) y
 * factor de velocidad (1.0 trazo continuo, 0.65 trazo segmentado).
 */
export function applyRepetitionAndSpeedProfile(uNorm, repetition = 1, speedFactor = 1.0) {
  const u = Math.max(0.0, Math.min(1.0, Number(uNorm) || 0.0));
  const reps = Math.max(1, Math.min(4, Math.round(Number(repetition) || 1)));
  // Curva sigmoide cosenoidal suave (minimum-jerk aproximado)
  if (reps === 1) {
    const gamma = speedFactor < 0.85 ? 1.15 : 1.0;
    const uScaled = Math.pow(u, gamma);
    return 0.5 * (1.0 - Math.cos(Math.PI * uScaled));
  }
  // Para flecha doble (2x) o triple (3x): oscilación ida y vuelta suave culminando en b (1.0)
  const scaled = u * (2 * reps - 1);
  const seg = Math.min(2 * reps - 2, Math.floor(scaled));
  const localT = scaled - seg;
  const smoothLocal = 0.5 * (1.0 - Math.cos(Math.PI * localT));
  return seg % 2 === 0 ? smoothLocal : 1.0 - smoothLocal;
}

/**
 * 1. TRAYECTORIA LINEAL (Página 4):
 * Soporta: 'left_to_right', 'right_to_left', 'bottom_to_top', 'top_to_bottom',
 * 'diag_top_to_bottom', 'diag_bottom_to_top' y 'zigzag' (3 segmentos para la letra Z).
 */
export function evaluateLinearTrajectoryOffset(variant, phase, amplitudeM = 0.055) {
  const s = Math.max(0.0, Math.min(1.0, Number(phase) || 0.0));
  const A = Number(amplitudeM) || 0.055;
  const half = 0.5 * A;

  switch (variant) {
    case 'left_to_right':
      // En la lámina (vista frontal): de izquierda (-X afuera) a derecha (+X adentro)
      return [(-half) + A * s, 0.0, 0.0];
    case 'right_to_left':
      return [(+half) - A * s, 0.0, 0.0];
    case 'bottom_to_top':
      return [0.0, (-half) + A * s, 0.0];
    case 'top_to_bottom':
      return [0.0, (+half) - A * s, 0.0];
    case 'diag_top_to_bottom':
      return [(-half) + A * s, (+half) - A * s, 0.0];
    case 'diag_bottom_to_top':
      return [(-half) + A * s, (-half) + A * s, 0.0];
    case 'zigzag': {
      // Trazo lineal en zigzag de 3 segmentos en el plano frontal (Letra Z, Página 4 y 10):
      // Seg 1 [0, 1/3]: superior derecha (+X, +Y) -> superior izquierda (-X, +Y)
      // Seg 2 [1/3, 2/3]: diagonal superior izquierda (-X, +Y) -> inferior derecha (+X, -Y)
      // Seg 3 [2/3, 1.0]: inferior derecha (+X, -Y) -> inferior izquierda (-X, -Y)
      const wX = A * 0.65;
      const hY = A * 0.55;
      if (s < 1.0 / 3.0) {
        const u = s * 3.0;
        return [wX * (0.5 - u), +hY * 0.5, 0.005 * Math.sin(Math.PI * u)];
      } else if (s < 2.0 / 3.0) {
        const u = (s - 1.0 / 3.0) * 3.0;
        return [wX * (-0.5 + u), hY * (0.5 - u), 0.008 * Math.sin(Math.PI * u)];
      } else {
        const u = (s - 2.0 / 3.0) * 3.0;
        return [wX * (0.5 - u), -hY * 0.5, 0.005 * Math.sin(Math.PI * u)];
      }
    }
    default:
      return [0.0, 0.0, 0.0];
  }
}

/**
 * 2. TRAYECTORIA CURVA (Página 4):
 * Curva Bézier cúbica / arco parabólico:
 * Soporta: 'right_to_left', 'left_to_right', 'bottom_to_top', 'top_to_bottom',
 * 'wavy' (ondulada), 'curved_displacement' (LL, RR, X) y 'j_curve' (Letra J).
 */
export function evaluateCurvedTrajectoryOffset(variant, phase, amplitudeM = 0.055) {
  const s = Math.max(0.0, Math.min(1.0, Number(phase) || 0.0));
  const A = Number(amplitudeM) || 0.055;
  const arc = Math.sin(Math.PI * s);

  switch (variant) {
    case 'right_to_left':
      // Desplazamiento curvo de derecha a izquierda (en lámina: hacia afuera -X con arco inferior)
      return [A * (0.45 - s), -0.38 * A * arc, 0.014 * arc];
    case 'left_to_right':
      // Desplazamiento curvo hacia adentro (+X) con arco inferior suave (LL, RR en lámina Pág. 10)
      return [A * (-0.35 + s), -0.35 * A * arc, 0.015 * arc];
    case 'bottom_to_top':
      return [0.32 * A * arc, A * (-0.5 + s), 0.015 * arc];
    case 'top_to_bottom':
      return [-0.32 * A * arc, A * (0.5 - s), 0.015 * arc];
    case 'wavy':
      // Trayectoria ondulada (Página 4 y virgulilla de Ñ en Página 10)
      return [
        A * (-0.45 + 0.90 * s),
        0.26 * A * Math.sin(2.0 * Math.PI * s),
        0.012 * arc
      ];
    case 'j_curve': {
      // Curva en J (Página 10): desciende en vertical (-Y), curva en el fondo y sube hacia adentro (+X, +Z)
      const p0 = [0.0, 0.025, 0.0];
      const p1 = [0.0, -A * 0.85, 0.008];
      const p2 = [A * 0.55, -A * 0.90, 0.022];
      const p3 = [A * 0.80, -A * 0.20, 0.030];
      const omt = 1.0 - s;
      return [
        omt * omt * omt * p0[0] + 3 * omt * omt * s * p1[0] + 3 * omt * s * s * p2[0] + s * s * s * p3[0],
        omt * omt * omt * p0[1] + 3 * omt * omt * s * p1[1] + 3 * omt * s * s * p2[1] + s * s * s * p3[1],
        omt * omt * omt * p0[2] + 3 * omt * omt * s * p1[2] + 3 * omt * s * s * p2[2] + s * s * s * p3[2]
      ];
    }
    case 'curved_displacement':
    default:
      return [A * (-0.30 + 0.85 * s), -0.30 * A * arc, 0.018 * arc];
  }
}

/**
 * 3. TRAYECTORIA CIRCULAR Y ESPIRAL (Página 4):
 * Soporta: 'left_to_right', 'right_to_left', 'spiral'.
 */
export function evaluateCircularTrajectoryOffset(variant, phase, radiusM = 0.035) {
  const s = Math.max(0.0, Math.min(1.0, Number(phase) || 0.0));
  const R = Number(radiusM) || 0.035;
  const theta = 2.0 * Math.PI * s;

  switch (variant) {
    case 'right_to_left':
      return [R * Math.cos(theta) - R, R * Math.sin(theta), 0.010 * Math.sin(Math.PI * s)];
    case 'spiral': {
      const rSpiral = R * (0.25 + 0.75 * s);
      const phi = 3.0 * Math.PI * s;
      return [rSpiral * Math.cos(phi), rSpiral * Math.sin(phi), 0.015 * s];
    }
    case 'left_to_right':
    default:
      return [-R * Math.cos(theta) + R, R * Math.sin(theta), 0.010 * Math.sin(Math.PI * s)];
  }
}

/* ========================================================================== */
/* 7. CONSTRUCTOR DE POSES FALÁNGICAS DE LAS 15 ARTICULACIONES (MANO ACTIVA)  */
/* ========================================================================== */

/**
 * Construye los 15 cuaterniones unitarios de la mano derecha a partir de una
 * especificación articular concisa en grados:
 * - Para índice, medio, anular y meñique:
 *   flexión hacia la palma (+Z en mano derecha VRM 1.0), abducción/splay (Y) y cruce axial (X).
 * - Para el pulgar:
 *   oposición/rotación en metacarpiano, proximal y distal.
 */
export function buildRightHandPhalangePose(spec = {}) {
  const fingerBone = (fingerCfg = {}, segment = 'prox') => {
    if (Array.isArray(fingerCfg[segment]) && fingerCfg[segment].length === 4) {
      return quatNormalize(fingerCfg[segment]);
    }
    const flexDeg = Number(fingerCfg[`${segment}Flex`] ?? fingerCfg.flex ?? 0.0);
    const splayDeg = segment === 'prox' ? Number(fingerCfg.splay ?? 0.0) : Number(fingerCfg[`${segment}Splay`] ?? 0.0);
    const twistDeg = segment === 'prox' ? Number(fingerCfg.twist ?? 0.0) : Number(fingerCfg[`${segment}Twist`] ?? 0.0);
    return eulerDegToQuat(twistDeg, splayDeg, flexDeg, 'XYZ');
  };

  const thumb = spec.thumb || {};
  const qThumbMeta = Array.isArray(thumb.meta)
    ? quatNormalize(thumb.meta)
    : eulerDegToQuat(thumb.metaX ?? 8, thumb.metaY ?? 18, thumb.metaZ ?? 12, 'XYZ');
  const qThumbProx = Array.isArray(thumb.prox)
    ? quatNormalize(thumb.prox)
    : eulerDegToQuat(thumb.proxX ?? 0, thumb.proxY ?? 22, thumb.proxZ ?? 18, 'XYZ');
  const qThumbDist = Array.isArray(thumb.dist)
    ? quatNormalize(thumb.dist)
    : eulerDegToQuat(thumb.distX ?? 0, thumb.distY ?? 0, thumb.distZ ?? 15, 'XYZ');

  return {
    rightThumbMetacarpal: qThumbMeta,
    rightThumbProximal: qThumbProx,
    rightThumbDistal: qThumbDist,
    rightIndexProximal: fingerBone(spec.index, 'prox'),
    rightIndexIntermediate: fingerBone(spec.index, 'inter'),
    rightIndexDistal: fingerBone(spec.index, 'dist'),
    rightMiddleProximal: fingerBone(spec.middle, 'prox'),
    rightMiddleIntermediate: fingerBone(spec.middle, 'inter'),
    rightMiddleDistal: fingerBone(spec.middle, 'dist'),
    rightRingProximal: fingerBone(spec.ring, 'prox'),
    rightRingIntermediate: fingerBone(spec.ring, 'inter'),
    rightRingDistal: fingerBone(spec.ring, 'dist'),
    rightLittleProximal: fingerBone(spec.little, 'prox'),
    rightLittleIntermediate: fingerBone(spec.little, 'inter'),
    rightLittleDistal: fingerBone(spec.little, 'dist')
  };
}

/**
 * Interpola en SO(3) las 15 falanges entre la pose inicial (a - Opacidad 70%)
 * y la pose final (b - Opacidad 100%).
 */
export function interpolatePhalangePoseSO3(poseA70, poseB100, alpha) {
  const out = {};
  for (const bone of RIGHT_HAND_PHALANX_BONES) {
    const qa = (poseA70 && poseA70[bone]) || Q_IDENTITY;
    const qb = (poseB100 && poseB100[bone]) || qa;
    out[bone] = slerpQuatAntipodal(qa, qb, alpha);
  }
  return out;
}

/**
 * Evalúa una secuencia multi-etapa (A -> B, Página 3 del PDF):
 * - Etapa A se ejecuta en t in [0.0, 0.5]
 * - Etapa B se ejecuta en t in [0.5, 1.0]
 */
export function evaluateMultiStageTransition(stageAPose, stageBPose, stageCPose, normalizedStrokeTime) {
  const u = Math.max(0.0, Math.min(1.0, Number(normalizedStrokeTime) || 0.0));
  if (u <= 0.5) {
    const localU = 0.5 * (1.0 - Math.cos(Math.PI * (u * 2.0)));
    return interpolatePhalangePoseSO3(stageAPose, stageBPose, localU);
  }
  const localU = 0.5 * (1.0 - Math.cos(Math.PI * ((u - 0.5) * 2.0)));
  return interpolatePhalangePoseSO3(stageBPose, stageCPose || stageBPose, localU);
}
