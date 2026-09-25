/**
 * LSEC Studio — Adaptador y Sincronizador de Glosas (AvatarSyncController)
 * 
 * Conecta los datos lingüísticos del proyecto (glosas, subtítulos, marcas de tiempo)
 * con el motor del avatar y el secuenciador:
 * - Mantiene el Registro Oficial de Clips (glosa -> clipId -> versión -> estado);
 * - Mapea rigurosamente solo glosas con clips registrados;
 * - Detecta glosas desconocidas y las marca como MISSING_ANIMATION;
 * - Emite advertencias de trazabilidad sin bloquear la secuencia;
 * - Sincroniza la previsualización del avatar con la línea de tiempo.
 */

import {
  createNeutralClip,
  createSaludarDemoClip,
  createNegacionDemoClip,
  createLunesSignClip
} from './sign-clip-factory.js';
import { defaultAnimationCache } from './animation-cache.js';

export class AvatarSyncController {
  /**
   * @param {import('./sign-sequencer.js').SignSequencer} sequencer 
   */
  constructor(sequencer) {
    this.sequencer = sequencer;

    // Registro canónico: glosa -> { clipId, version, validationStatus, factory }
    this.clipRegistry = new Map();
    this.initDefaultRegistry();
  }

  initDefaultRegistry() {
    // Registro explícito y trazable
    this.registerClip('LUNES', {
      clipId: 'LUNES_V1',
      version: '1.0.0',
      validationStatus: 'REQUIRES_LSEC_VALIDATION',
      factory: createLunesSignClip
    });

    this.registerClip('NEUTRAL', {
      clipId: 'NEUTRAL_V1',
      version: '1.0.0',
      validationStatus: 'REQUIRES_LSEC_VALIDATION',
      factory: createNeutralClip
    });

    this.registerClip('SALUDAR_DEMO', {
      clipId: 'SALUDAR_DEMO_V1',
      version: '1.0.0',
      validationStatus: 'REQUIRES_LSEC_VALIDATION',
      factory: createSaludarDemoClip
    });

    this.registerClip('SALUDAR', {
      clipId: 'SALUDAR_DEMO_V1',
      version: '1.0.0',
      validationStatus: 'REQUIRES_LSEC_VALIDATION',
      factory: createSaludarDemoClip
    });

    this.registerClip('HOLA', {
      clipId: 'SALUDAR_DEMO_V1',
      version: '1.0.0',
      validationStatus: 'REQUIRES_LSEC_VALIDATION',
      factory: createSaludarDemoClip
    });

    this.registerClip('NEGACION_DEMO', {
      clipId: 'NEGACION_DEMO_V1',
      version: '1.0.0',
      validationStatus: 'REQUIRES_LSEC_VALIDATION',
      factory: createNegacionDemoClip
    });

    this.registerClip('NEGACION', {
      clipId: 'NEGACION_DEMO_V1',
      version: '1.0.0',
      validationStatus: 'REQUIRES_LSEC_VALIDATION',
      factory: createNegacionDemoClip
    });

    this.registerClip('NO', {
      clipId: 'NEGACION_DEMO_V1',
      version: '1.0.0',
      validationStatus: 'REQUIRES_LSEC_VALIDATION',
      factory: createNegacionDemoClip
    });
  }

  /**
   * Registra una nueva asociación entre glosa y clip de animación.
   */
  registerClip(glossName, entry) {
    const key = (glossName || '').trim().toUpperCase();
    if (!key) return;

    this.clipRegistry.set(key, {
      clipId: entry.clipId,
      version: entry.version || '1.0.0',
      validationStatus: entry.validationStatus || 'REQUIRES_LSEC_VALIDATION',
      factory: entry.factory
    });
  }

  /**
   * Consulta el registro de clips para una glosa dada.
   */
  lookup(glossName) {
    const key = (glossName || '').trim().toUpperCase();
    return this.clipRegistry.get(key) || null;
  }

  /**
   * Adapta una estructura de glosas de LSEC Studio para el secuenciador.
   * Acepta:
   * {
   *   glosses: [{ id, gloss, startMs, endMs, validationStatus }],
   *   nonManualMarkers: [],
   *   spatialLoci: []
   * }
   * 
   * @param {Object} inputData 
   * @returns {Object} Resultado de la adaptación con clips listos y advertencias.
   */
  adaptProjectGlossesToSequence(inputData) {
    const rawGlosses = (inputData && Array.isArray(inputData.glosses))
      ? inputData.glosses
      : [];

    const playableClips = [];
    const sequencePlan = [];
    const missingGlosses = [];

    rawGlosses.forEach((item, index) => {
      const glossName = (item.gloss || item.text || '').trim();
      const normKey = glossName.toUpperCase();
      const startMs = typeof item.startMs === 'number' ? item.startMs : (item.start ? item.start * 1000 : index * 1000);
      const endMs = typeof item.endMs === 'number' ? item.endMs : (item.end ? item.end * 1000 : startMs + 1000);

      const regEntry = this.lookup(normKey);

      if (regEntry && typeof regEntry.factory === 'function') {
        let clip = defaultAnimationCache.getClip(regEntry.clipId);
        if (!clip) {
          clip = regEntry.factory();
          defaultAnimationCache.setClip(regEntry.clipId, clip);
        }

        playableClips.push(clip);
        sequencePlan.push({
          index,
          id: item.id || `g_${index}`,
          gloss: glossName,
          clipId: regEntry.clipId,
          version: regEntry.version,
          status: 'AVAILABLE',
          validationStatus: regEntry.validationStatus,
          startMs,
          endMs
        });
      } else {
        // Glosa sin animación en el registro
        missingGlosses.push(glossName);
        sequencePlan.push({
          index,
          id: item.id || `g_${index}`,
          gloss: glossName,
          clipId: null,
          version: null,
          status: 'MISSING_ANIMATION',
          validationStatus: 'NO_CLIP_AVAILABLE',
          startMs,
          endMs,
          warning: `Sin animación registrada para la glosa "${glossName}". Se omite sin interrumpir el flujo.`
        });

        console.warn(`[AvatarSyncController] Glosa "${glossName}" marcada como MISSING_ANIMATION (sin clip en catálogo).`);
      }
    });

    return {
      playableClips,
      sequencePlan,
      missingGlosses,
      totalInputGlosses: rawGlosses.length,
      totalPlayableClips: playableClips.length
    };
  }

  /**
   * Reproduce la secuencia adaptada en el secuenciador.
   * @param {Object} inputData 
   * @returns {Object} Resultado de la adaptación
   */
  playAdaptedSequence(inputData) {
    const result = this.adaptProjectGlossesToSequence(inputData);

    if (result.playableClips.length > 0) {
      this.sequencer.playSequence(result.playableClips);
    } else {
      console.warn('[AvatarSyncController] No hay clips disponibles para reproducir en la secuencia suministrada.');
    }

    return result;
  }
}
