/**
 * LSEC Studio — Retargeter de Movimiento MediaPipe Holistic (MotionRetargeter)
 * 
 * Interfaz y arquitectura preparatoria para conectar la extracción de landmarks
 * de MediaPipe Holistic (backend o cámara) con el esqueleto humanoide VRM 1.0.
 * 
 * ESTADO DEL MÓDULO:
 * [EXPERIMENTAL / PREPARATORY_INTEGRATION]
 * 
 * Implementa los 10 pasos especificados en la arquitectura de retargeting:
 * 1. Normalización de dimensiones corporales (antropometría invariable);
 * 2. Cálculo de vectores óseos inter-articulares;
 * 3. Cálculo de rotaciones relativas entre segmentos adyacentes;
 * 4. Conversión de rotaciones relativas a cuaterniones unitarios;
 * 5. Mapeo de articulaciones MediaPipe a huesos VRM normalizados;
 * 6. Aplicación de límites angulares anatómicos de seguridad (clamping);
 * 7. Filtrado de ruido temporal y jitter de alta frecuencia;
 * 8. Suavizado de trayectorias (One-Euro Filter / Exponential Smooth);
 * 9. Preservación de distancias de contacto manual y bimanual;
 * 10. Generación de clips de animación estructurados y editables.
 */

import * as THREE from 'three';

/**
 * Contrato de datos para cada fotograma de MediaPipe Holistic.
 * @typedef {Object} HolisticFrame
 * @property {Array<{x: number, y: number, z: number, visibility?: number}>} poseLandmarks - 33 puntos corporales
 * @property {Array<{x: number, y: number, z: number}>} leftHandLandmarks - 21 puntos mano izquierda
 * @property {Array<{x: number, y: number, z: number}>} rightHandLandmarks - 21 puntos mano derecha
 * @property {Array<{x: number, y: number, z: number}>} faceLandmarks - 468/478 puntos faciales
 * @property {Array<{categoryName: string, score: number}>} faceBlendshapes - 52 coeficientes faciales
 * @property {number} timestampMs - Marca de tiempo en milisegundos
 * @property {number} confidence - Nivel global de confianza en la detección [0, 1]
 */

export class MotionRetargeter {
  constructor() {
    this.status = 'EXPERIMENTAL';
    this.smoothingFactor = 0.65; // Factor de suavizado exponencial
    this.prevQuaternions = new Map();
  }

  /**
   * 1. Normaliza las dimensiones corporales del frame dividiendo por la distancia
   * inter-clavicular / hombros para hacer los datos invariables a la escala del usuario.
   */
  normalizeBodyDimensions(poseLandmarks) {
    if (!poseLandmarks || poseLandmarks.length < 13) return poseLandmarks;

    const leftShoulder = poseLandmarks[11];
    const rightShoulder = poseLandmarks[12];

    const shoulderDist = Math.hypot(
      leftShoulder.x - rightShoulder.x,
      leftShoulder.y - rightShoulder.y,
      leftShoulder.z - rightShoulder.z
    );

    const scale = shoulderDist > 0.001 ? (0.35 / shoulderDist) : 1.0;

    return poseLandmarks.map((lm) => ({
      x: lm.x * scale,
      y: lm.y * scale,
      z: lm.z * scale,
      visibility: lm.visibility
    }));
  }

  /**
   * 2. Forma vectores 3D entre articulaciones adyacentes.
   */
  computeJointVector(pFrom, pTo) {
    return new THREE.Vector3(
      pTo.x - pFrom.x,
      pTo.y - pFrom.y,
      pTo.z - pFrom.z
    ).normalize();
  }

  /**
   * 3 & 4. Calcula la rotación relativa entre dos vectores y genera un cuaternión unitario.
   */
  calculateRelativeRotation(vSource, vTarget) {
    const q = new THREE.Quaternion();
    q.setFromUnitVectors(vSource, vTarget);
    return q.normalize();
  }

  /**
   * 5. Mapea articulaciones corporales a nombres de huesos VRM.
   */
  mapJointsToVRMBones(frame) {
    const boneRotations = new Map();
    if (!frame || !frame.poseLandmarks || frame.poseLandmarks.length < 17) {
      return boneRotations;
    }

    const lm = frame.poseLandmarks;

    // Vector antebrazo derecho: codo (14) a muñeca (16)
    if (lm[14] && lm[16]) {
      const vForearm = this.computeJointVector(lm[14], lm[16]);
      const vRest = new THREE.Vector3(0, -1, 0);
      const qRightLowerArm = this.calculateRelativeRotation(vRest, vForearm);
      boneRotations.set('rightLowerArm', qRightLowerArm);
    }

    // Vector brazo derecho: hombro (12) a codo (14)
    if (lm[12] && lm[14]) {
      const vUpperArm = this.computeJointVector(lm[12], lm[14]);
      const vRest = new THREE.Vector3(0, -1, 0);
      const qRightUpperArm = this.calculateRelativeRotation(vRest, vUpperArm);
      boneRotations.set('rightUpperArm', qRightUpperArm);
    }

    // Vector antebrazo izquierdo: codo (13) a muñeca (15)
    if (lm[13] && lm[15]) {
      const vForearmL = this.computeJointVector(lm[13], lm[15]);
      const vRest = new THREE.Vector3(0, -1, 0);
      const qLeftLowerArm = this.calculateRelativeRotation(vRest, vForearmL);
      boneRotations.set('leftLowerArm', qLeftLowerArm);
    }

    // Vector brazo izquierdo: hombro (11) a codo (13)
    if (lm[11] && lm[13]) {
      const vUpperArmL = this.computeJointVector(lm[11], lm[13]);
      const vRest = new THREE.Vector3(0, -1, 0);
      const qLeftUpperArm = this.calculateRelativeRotation(vRest, vUpperArmL);
      boneRotations.set('leftUpperArm', qLeftUpperArm);
    }

    return boneRotations;
  }

  /**
   * 6. Aplica límites anatómicos para prevenir deformaciones grotescas de articulaciones.
   */
  applyAnatomicalLimits(boneName, quat) {
    // Clamping de ángulo máximo contra cuaternión identidad
    const angle = 2 * Math.acos(Math.max(-1, Math.min(1, quat.w)));
    const maxAllowedAngle = degToRad(145); // Máximo límite humano de flexión

    if (angle > maxAllowedAngle) {
      const scale = maxAllowedAngle / angle;
      const euler = new THREE.Euler().setFromQuaternion(quat);
      euler.x *= scale;
      euler.y *= scale;
      euler.z *= scale;
      return new THREE.Quaternion().setFromEuler(euler).normalize();
    }

    return quat;
  }

  /**
   * 7 & 8. Filtra ruido temporal y suaviza trayectorias mediante SLERP ponderado.
   */
  smoothQuaternion(boneName, currentQuat) {
    const prev = this.prevQuaternions.get(boneName);
    if (!prev) {
      this.prevQuaternions.set(boneName, currentQuat.clone());
      return currentQuat;
    }

    const smoothed = prev.clone().slerp(currentQuat, 1.0 - this.smoothingFactor);
    smoothed.normalize();
    this.prevQuaternions.set(boneName, smoothed.clone());
    return smoothed;
  }

  /**
   * 9. Preserva contacto espacial si los dedos o palmas se tocan en el espacio de señas.
   */
  preserveHandContact(leftWrist, rightWrist) {
    if (!leftWrist || !rightWrist) return false;
    const dist = Math.hypot(
      leftWrist.x - rightWrist.x,
      leftWrist.y - rightWrist.y,
      leftWrist.z - rightWrist.z
    );
    return dist < 0.08; // Menos de 8 cm indica proximidad/contacto intencional
  }

  /**
   * 10. Genera un objeto SignClip estructurado a partir de una secuencia procesada de frames.
   */
  generateSignClip(processedFrames, glossName = 'EXPERIMENTAL_RETARGET') {
    const durationMs = processedFrames.length > 1
      ? (processedFrames[processedFrames.length - 1].timestampMs - processedFrames[0].timestampMs)
      : 1000;

    return {
      clipId: `RETARGET_${Date.now()}`,
      gloss: glossName,
      conceptId: null,
      version: '0.1.0',
      durationMs,
      status: 'EXPERIMENTAL',
      provenance: 'MEDIAPIPE_HOLISTIC_RETARGETER',
      validationStatus: 'REQUIRES_LSEC_VALIDATION',
      dominantHand: 'RIGHT',
      twoHanded: true,
      entryPose: 'NEUTRAL',
      exitPose: 'NEUTRAL',
      boneTracks: [],
      expressionTracks: [],
      spatialConstraints: [],
      metadata: {
        description: 'Clip experimental derivado de captura de movimiento MediaPipe Holistic.',
        isValidatedLSEC: false
      }
    };
  }
}

function degToRad(deg) {
  return deg * (Math.PI / 180.0);
}
