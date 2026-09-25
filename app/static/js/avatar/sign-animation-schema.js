/**
 * LSEC Studio — Esquema y Validador de Clips de Animación de Señas
 * 
 * Define la estructura de datos estandarizada para clips de animación de
 * Lengua de Señas Ecuatoriana (LSEC) y realiza validación estricta de:
 * - Identificadores y metadatos lingüísticos/técnicos.
 * - Duración y orden cronológico de marcas de tiempo.
 * - Pistas esqueléticas con cuaterniones normalizados [x, y, z, w].
 * - Pistas de expresiones faciales en rango [0, 1].
 * - Nombres normalizados de huesos humanoides compatibles con VRM 1.0.
 * 
 * Un clip inválido produce advertencias claras y se omite de forma controlada
 * sin interrumpir la ejecución de la aplicación.
 */

export const HUMAN_BONE_NAMES = Object.freeze([
  // Torso y columna
  'hips',
  'spine',
  'chest',
  'upperChest',
  'neck',
  'head',
  'leftEye',
  'rightEye',
  // Extremidad superior izquierda
  'leftShoulder',
  'leftUpperArm',
  'leftLowerArm',
  'leftHand',
  'leftThumbMetacarpal',
  'leftThumbProximal',
  'leftThumbDistal',
  'leftIndexProximal',
  'leftIndexIntermediate',
  'leftIndexDistal',
  'leftMiddleProximal',
  'leftMiddleIntermediate',
  'leftMiddleDistal',
  'leftRingProximal',
  'leftRingIntermediate',
  'leftRingDistal',
  'leftLittleProximal',
  'leftLittleIntermediate',
  'leftLittleDistal',
  // Extremidad superior derecha
  'rightShoulder',
  'rightUpperArm',
  'rightLowerArm',
  'rightHand',
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
  'rightLittleDistal',
  // Extremidades inferiores (base y estabilidad)
  'leftUpperLeg',
  'leftLowerLeg',
  'leftFoot',
  'leftToes',
  'rightUpperLeg',
  'rightLowerLeg',
  'rightFoot',
  'rightToes'
]);

export const VRM_EXPRESSION_NAMES = Object.freeze([
  'neutral',
  'happy',
  'angry',
  'sad',
  'relaxed',
  'surprised',
  'aa',
  'ih',
  'ou',
  'ee',
  'oh',
  'blink',
  'blinkLeft',
  'blinkRight',
  'lookUp',
  'lookDown',
  'lookLeft',
  'lookRight'
]);

export const CLIP_STATUSES = Object.freeze([
  'DEMO_ONLY',
  'MACHINE_PROPOSED',
  'EXPERIMENTAL',
  'REQUIRES_LSEC_VALIDATION',
  'HUMAN_REVIEWED',
  'VALIDATED_LSEC'
]);

/**
 * Valida un objeto clip contra el esquema de animación LSEC.
 * @param {Object} clip - Objeto que representa el clip de animación.
 * @returns {{ valid: boolean, errors: string[], warnings: string[] }}
 */
export function validateSignClip(clip) {
  const errors = [];
  const warnings = [];

  if (!clip || typeof clip !== 'object') {
    return {
      valid: false,
      errors: ['El clip debe ser un objeto JSON válido y no nulo.'],
      warnings: []
    };
  }

  // 1. Identificadores y glosa
  if (!clip.clipId || typeof clip.clipId !== 'string' || clip.clipId.trim() === '') {
    errors.push('El campo "clipId" es obligatorio y debe ser una cadena no vacía.');
  }

  if (!clip.gloss || typeof clip.gloss !== 'string' || clip.gloss.trim() === '') {
    errors.push('El campo "gloss" es obligatorio y debe ser una cadena no vacía.');
  }

  // 2. Duración
  if (typeof clip.durationMs !== 'number' || clip.durationMs <= 0 || !Number.isFinite(clip.durationMs)) {
    errors.push(`El campo "durationMs" debe ser un número finito mayor a 0. Valor recibido: ${clip.durationMs}`);
  }

  const durationSec = (clip.durationMs || 0) / 1000.0;

  // 3. Estado y trazabilidad
  if (clip.status && !CLIP_STATUSES.includes(clip.status)) {
    warnings.push(`Estado "${clip.status}" no reconocido en el catálogo estándar de estados.`);
  }

  if (clip.validationStatus !== 'VALIDATED_LSEC') {
    if (!clip.metadata || clip.metadata.isValidatedLSEC !== false) {
      warnings.push('El clip no está validado como LSEC nativa. Debe registrarse explícitamente en metadata.isValidatedLSEC = false.');
    }
  }

  // 4. Pistas de huesos (Bone Tracks)
  if (!Array.isArray(clip.boneTracks)) {
    errors.push('El campo "boneTracks" debe ser un arreglo.');
  } else {
    clip.boneTracks.forEach((track, index) => {
      const trackId = `boneTrack[${index}](${track.boneName || 'sin_nombre'})`;

      if (!track.boneName || typeof track.boneName !== 'string') {
        errors.push(`${trackId}: "boneName" es obligatorio.`);
      } else if (!HUMAN_BONE_NAMES.includes(track.boneName)) {
        warnings.push(`${trackId}: El hueso "${track.boneName}" no pertenece a la nomenclatura estándar VRM.`);
      }

      if (!Array.isArray(track.times) || track.times.length === 0) {
        errors.push(`${trackId}: "times" debe ser un arreglo no vacío.`);
      } else {
        // Verificar orden ascendente y límites temporales
        let prevTime = -Infinity;
        for (let i = 0; i < track.times.length; i++) {
          const t = track.times[i];
          if (typeof t !== 'number' || !Number.isFinite(t) || t < 0) {
            errors.push(`${trackId}: El tiempo en índice ${i} (${t}) no es un número finito positivo.`);
            break;
          }
          if (t < prevTime) {
            errors.push(`${trackId}: Los tiempos deben ser estrictamente no decrecientes. ${t} < ${prevTime}`);
            break;
          }
          if (t > durationSec + 0.05) {
            warnings.push(`${trackId}: El tiempo ${t}s excede la duración declarada del clip (${durationSec}s).`);
          }
          prevTime = t;
        }
      }

      // Validar cuaterniones de rotación (4 componentes x, y, z, w por keyframe)
      if (!Array.isArray(track.rotations)) {
        errors.push(`${trackId}: "rotations" debe ser un arreglo de cuaterniones.`);
      } else {
        const expectedRotCount = (track.times ? track.times.length : 0) * 4;
        if (track.rotations.length !== expectedRotCount) {
          errors.push(`${trackId}: Longitud de "rotations" (${track.rotations.length}) debe ser exactamente 4 veces la de "times" (${expectedRotCount}).`);
        } else {
          // Validar longitud unitaria de cada cuaternión
          for (let k = 0; k < track.rotations.length; k += 4) {
            const x = track.rotations[k];
            const y = track.rotations[k + 1];
            const z = track.rotations[k + 2];
            const w = track.rotations[k + 3];

            if ([x, y, z, w].some(v => typeof v !== 'number' || !Number.isFinite(v))) {
              errors.push(`${trackId}: Cuaternión en fotograma ${k / 4} contiene componentes no numéricas.`);
              break;
            }

            const normSq = x * x + y * y + z * z + w * w;
            if (Math.abs(normSq - 1.0) > 0.15 && normSq > 0.0001) {
              warnings.push(`${trackId}: Cuaternión en fotograma ${k / 4} no está estrictamente normalizado (norma^2 = ${normSq.toFixed(3)}). Se normalizará automáticamente.`);
            } else if (normSq <= 0.0001) {
              errors.push(`${trackId}: Cuaternión degenerado con magnitud cercana a 0 en fotograma ${k / 4}.`);
              break;
            }
          }
        }
      }

      // Validar posiciones opcionales (3 componentes x, y, z por keyframe)
      if (track.positions) {
        if (!Array.isArray(track.positions)) {
          errors.push(`${trackId}: "positions" debe ser un arreglo si está presente.`);
        } else {
          const expectedPosCount = (track.times ? track.times.length : 0) * 3;
          if (track.positions.length !== expectedPosCount) {
            errors.push(`${trackId}: Longitud de "positions" (${track.positions.length}) debe ser exactamente 3 veces la de "times" (${expectedPosCount}).`);
          }
        }
      }
    });
  }

  // 5. Pistas de expresiones faciales (Expression Tracks)
  if (clip.expressionTracks && !Array.isArray(clip.expressionTracks)) {
    errors.push('El campo "expressionTracks" debe ser un arreglo si está presente.');
  } else if (Array.isArray(clip.expressionTracks)) {
    clip.expressionTracks.forEach((track, index) => {
      const trackId = `expressionTrack[${index}](${track.expressionName || 'sin_nombre'})`;

      if (!track.expressionName || typeof track.expressionName !== 'string') {
        errors.push(`${trackId}: "expressionName" es obligatorio.`);
      }

      if (!Array.isArray(track.times) || track.times.length === 0) {
        errors.push(`${trackId}: "times" debe ser un arreglo no vacío.`);
      }

      if (!Array.isArray(track.values) || (track.times && track.values.length !== track.times.length)) {
        errors.push(`${trackId}: Longitud de "values" debe coincidir exactamente con "times".`);
      } else {
        track.values.forEach((val, vIdx) => {
          if (typeof val !== 'number' || val < 0 || val > 1) {
            errors.push(`${trackId}: El valor en índice ${vIdx} (${val}) debe estar en el rango [0.0, 1.0].`);
          }
        });
      }
    });
  }

  const valid = errors.length === 0;
  if (!valid) {
    console.warn(`[SignAnimationSchema] Clip "${clip.clipId || 'desconocido'}" rechazado por validación:`, errors);
  } else if (warnings.length > 0) {
    console.info(`[SignAnimationSchema] Clip "${clip.clipId}" válido con advertencias:`, warnings);
  }

  return { valid, errors, warnings };
}
