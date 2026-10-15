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
import {
  convertDirectAnimationToSignClip,
  validateSignClip,
  trimSignClipStroke
} from './sign-animation-schema.js';

export class AvatarSyncController {
  /**
   * @param {import('./sign-sequencer.js').SignSequencer} sequencer 
   */
  constructor(sequencer) {
    this.sequencer = sequencer;

    // Registro canónico: glosa -> { clipId, version, validationStatus, factory }
    this.clipRegistry = new Map();
    this.resolutionCache = new Map();
    this.clipCache = new Map();
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

    // Cargar catálogo modular dinámico de clips LSEC (manifest.json)
    this.loadManifest('/static/assets/clips/manifest.json');
  }

  /**
   * Carga y registra dinámicamente clips desde el catálogo manifest.json.
   * Permite escalar a miles de clips sin sobrecargar la memoria del navegador.
   * @param {string} manifestUrl 
   */
  async loadManifest(manifestUrl = '/static/assets/clips/manifest.json') {
    try {
      const res = await fetch(manifestUrl);
      if (!res.ok) return;
      const manifest = await res.json();
      if (manifest && manifest.clips) {
        for (const [glossKey, clipMeta] of Object.entries(manifest.clips)) {
          this.registerClip(glossKey, {
            clipId: clipMeta.clipId,
            version: '2.0.0',
            validationStatus: clipMeta.validationStatus || 'REQUIRES_LSEC_VALIDATION',
            file: clipMeta.file,
            factory: () => this.fetchClipFile(clipMeta.file, clipMeta.clipId)
          });
        }
        console.info(`[AvatarSyncController] ${Object.keys(manifest.clips).length} clips registrados dinámicamente desde manifest.json.`);
      }
    } catch (e) {
      console.warn('[AvatarSyncController] No se pudo cargar el manifiesto de clips:', e);
    }
  }

  /**
   * Descarga un archivo de clip JSON modular y lo guarda en cache de animaciones.
   */
  async fetchClipFile(fileName, clipId) {
    let cached = defaultAnimationCache.getClip(clipId);
    if (cached) return cached;
    const res = await fetch(`/static/assets/clips/${fileName}?t=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status} al cargar /static/assets/clips/${fileName}`);
    const clipData = await res.json();
    defaultAnimationCache.setClip(clipId, clipData);
    return clipData;
  }

  /**
   * Obtiene y convierte la animación de una seña usando el endpoint libre de 404
   * (/api/animations-direct/resolve/{gloss}?version=2.6) sobre las 5,061 señas v2.6.
   * Recorta automáticamente los frames muertos de reposo al stroke activo.
   * @param {string} glossName
   * @param {Object} [options]
   * @param {string} [options.version='2.6'] - Versión solicitada ('2.6' o '2.5')
   * @param {boolean} [options.trimStroke=true] - Recortar frames muertos de entrada/salida
   * @returns {Promise<Object|null>} SignClip compatible con SignPlayer o null si no existe.
   */
  async fetchDirectClip(glossName, options = { version: '2.6', trimStroke: true }) {
    if (!glossName || typeof glossName !== 'string') return null;
    const clean = glossName.trim();
    if (!clean) return null;
    const normKey = clean.toUpperCase();
    const verTag = (options && options.version) ? String(options.version) : '2.6';
    const shouldTrim = options && options.trimStroke !== undefined ? Boolean(options.trimStroke) : true;
    const verPrefix = verTag.startsWith('2.5') ? 'v25_' : 'v26_';
    const cacheKey = `${verPrefix}${shouldTrim ? 'trim_' : 'raw_'}${normKey}`;

    // 1. Revisar caché en memoria
    let cached = defaultAnimationCache.getClip(cacheKey);
    if (cached) return cached;

    if (this.resolutionCache.has(`${verPrefix}${normKey}`)) {
      const prevRes = this.resolutionCache.get(`${verPrefix}${normKey}`);
      if (prevRes && prevRes.found === false) {
        return null;
      }
    }

    // 2. Consultar el endpoint libre de 404 (/api/animations-direct/resolve/{gloss})
    if (typeof fetch === 'function') {
      try {
        const resolveUrl = `/api/animations-direct/resolve/${encodeURIComponent(clean)}?version=${encodeURIComponent(verTag)}&include_animation=true`;
        let res = await fetch(resolveUrl);
        if (!res || !res.ok) {
          res = await fetch(`/api/v1/animations/resolve/${encodeURIComponent(clean)}?version=${encodeURIComponent(verTag)}&include_animation=true`);
        }

        if (res && res.ok) {
          const payload = await res.json();
          const isEnvelope = payload && typeof payload === 'object' && ('found' in payload);
          if (isEnvelope) {
            this.resolutionCache.set(`${verPrefix}${normKey}`, {
              found: Boolean(payload.found),
              match_type: payload.match_type || 'none',
              warning: payload.warning || null,
              needs_review: Boolean(payload.needs_review),
              resolved_gloss: payload.resolved_gloss || payload.sign || null,
              version_served: payload.version_served || verTag,
              is_fingerspelling: Boolean(payload.is_fingerspelling)
            });
            if (!payload.found || !payload.animation) {
              return null;
            }
          }

          const rawData = isEnvelope ? payload.animation : payload;
          const resolvedGloss = isEnvelope ? (payload.resolved_gloss || payload.sign || clean) : clean;

          if (rawData && typeof rawData === 'object') {
            let clip = convertDirectAnimationToSignClip(rawData, clean);
            if (clip && Array.isArray(clip.boneTracks) && clip.boneTracks.length > 0) {
              if (isEnvelope) {
                clip.metadata = {
                  ...(clip.metadata || {}),
                  resolvedGloss,
                  matchType: payload.match_type || 'exact',
                  resolutionStatus: payload.status || 'EXACT',
                  needsReview: Boolean(payload.needs_review),
                  warning: payload.warning || null,
                  versionServed: payload.version_served || verTag
                };
              }
              if (shouldTrim) {
                clip = trimSignClipStroke(clip);
              }
              defaultAnimationCache.setClip(cacheKey, clip);
              defaultAnimationCache.setClip(`${verPrefix}${normKey}`, clip);
              this.clipCache.set(normKey, clip);
              this.clipCache.set(`${verPrefix}${normKey}`, clip);
              if (clip.clipId) {
                defaultAnimationCache.setClip(clip.clipId, clip);
              }
              return clip;
            }
          }
        }
      } catch (err) {
        // Fallback silencioso ante modo offline o error de red
      }
    }
    return null;
  }

  /**
   * Alias de retrocompatibilidad para el pipeline v2.5 Directo 1:1 ('2.5_Directo_1a1').
   * Preserva compatibilidad con suites de pruebas y componentes existentes.
   * @param {string} glossName
   * @returns {Promise<Object|null>}
   */
  async fetchDirectV25Clip(glossName) {
    return this.fetchDirectClip(glossName, { version: '2.5' });
  }

  /**
   * Obtiene un clip previamente cargado en caché para una glosa.
   * @param {string} glossName
   * @param {string} [version='2.6']
   * @returns {Object|null}
   */
  getCachedClip(glossName, version = '2.6') {
    const normKey = (glossName || '').trim().toUpperCase();
    if (!normKey) return null;
    if (this.clipCache.has(normKey)) {
      return this.clipCache.get(normKey);
    }
    const verPrefix = String(version).startsWith('2.5') ? 'v25_' : 'v26_';
    return (
      defaultAnimationCache.getClip(`${verPrefix}trim_${normKey}`) ||
      defaultAnimationCache.getClip(`${verPrefix}${normKey}`) ||
      defaultAnimationCache.getClip(`v25_trim_${normKey}`) ||
      defaultAnimationCache.getClip(`v25_${normKey}`) ||
      null
    );
  }

  /**
   * Obtiene la información de resolución léxica para una glosa (match_type, warning, needs_review).
   * @param {string} glossName
   * @param {string} [version='2.6']
   */
  getResolutionMetadata(glossName, version = '2.6') {
    const normKey = (glossName || '').trim().toUpperCase();
    const verPrefix = String(version).startsWith('2.5') ? 'v25_' : 'v26_';
    return this.resolutionCache.get(`${verPrefix}${normKey}`) || null;
  }

  getResolutionMeta(glossName, version = '2.6') {
    return this.getResolutionMetadata(glossName, version);
  }

  /**
   * Obtiene un clip de forma asíncrona por nombre de glosa, priorizando la versión oficial 2.6
   * corregida, con fallback de continuidad a v2.5 y registro canónico local.
   */
  async loadClipAsync(glossName, options = {}) {
    const key = (glossName || '').trim().toUpperCase();
    if (!key) return null;

    const shouldTrim = options.trimStroke !== undefined ? Boolean(options.trimStroke) : true;

    // 1. Prioridad Máxima: Pipeline v2.6 Corregido Oficial
    let directClip = await this.fetchDirectClip(glossName, { version: '2.6', trimStroke: shouldTrim });
    if (directClip) {
      this.clipCache.set(key, directClip);
      return directClip;
    }

    const resMeta = this.getResolutionMetadata(glossName, '2.6');
    if (resMeta && resMeta.is_fingerspelling) {
      return null;
    }

    // 2. Fallback de Continuidad: Pipeline v2.5 Directo 1:1
    directClip = await this.fetchDirectClip(glossName, { version: '2.5', trimStroke: shouldTrim });
    if (directClip) {
      this.clipCache.set(key, directClip);
      return directClip;
    }

    // 3. Fallback: Registro canónico local / manifest offline
    const entry = this.lookup(key);
    if (!entry) return null;
    let clip = defaultAnimationCache.getClip(entry.clipId);
    if (!clip && typeof entry.factory === 'function') {
      const res = entry.factory();
      clip = (res instanceof Promise) ? await res : res;
      if (clip) {
        defaultAnimationCache.setClip(entry.clipId, clip);
      }
    }
    if (clip) {
      this.clipCache.set(key, clip);
    }
    return clip;
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
   * Ejecuta TODAS las glosas resueltas sin omisión (incluyendo SER, CON, ESO, etc.),
   * aplicando recorte de stroke activo y escalado dinámico de velocidad legible.
   * 
   * @param {Object} inputData 
   * @returns {Promise<Object>} Resultado de la adaptación con clips listos y advertencias.
   */
  async adaptProjectGlossesToSequence(inputData) {
    const rawGlosses = (inputData && Array.isArray(inputData.glosses))
      ? inputData.glosses
      : [];

    const playableClips = [];
    const sequencePlan = [];
    const missingGlosses = [];

    for (let index = 0; index < rawGlosses.length; index++) {
      const item = rawGlosses[index];
      const glossName = (item.gloss || item.text || '').trim();
      const normKey = glossName.toUpperCase();
      const startMs = typeof item.startMs === 'number' ? item.startMs : (item.start ? item.start * 1000 : index * 1000);
      const endMs = typeof item.endMs === 'number' ? item.endMs : (item.end ? item.end * 1000 : startMs + 1000);
      const slotSec = Math.max(0.4, (endMs - startMs) / 1000.0);

      // 1. Intentar resolver vía Pipeline v2.6 Oficial Corregido (o fallback v2.5 directo)
      let clip = await this.fetchDirectClip(glossName, { version: '2.6', trimStroke: true });
      if (!clip) {
        const rm = this.getResolutionMetadata(glossName, '2.6');
        if (!rm || !rm.is_fingerspelling) {
          clip = await this.fetchDirectClip(glossName, { version: '2.5', trimStroke: true });
        }
      }

      let clipVersion = (clip && clip.metadata && clip.metadata.pipelineVersion) || '2.6_Directo_1a1_corregido';
      let clipSource = (clip && clip.metadata && clip.metadata.source) || 'Pipeline v2.6 Directo 1:1 Oficial';
      let validationStatus = (clip && clip.validationStatus) || 'REQUIRES_LSEC_VALIDATION';
      let regEntry = null;

      // 2. Si no se resolvió vía API directa, buscar en el registro local / manifest offline
      const resMeta = this.getResolutionMetadata(glossName, '2.6');
      if (!clip && (!resMeta || !resMeta.is_fingerspelling)) {
        regEntry = this.lookup(normKey);

        if (regEntry && typeof regEntry.factory === 'function') {
          clip = defaultAnimationCache.getClip(regEntry.clipId);
          if (!clip) {
            try {
              const res = regEntry.factory();
              clip = (res instanceof Promise) ? await res : res;
              if (clip) {
                defaultAnimationCache.setClip(regEntry.clipId, clip);
              }
            } catch (fetchErr) {
              console.error(`[AvatarSyncController] Error al resolver clip para "${glossName}":`, fetchErr);
            }
          }

          if (clip) {
            clipVersion = regEntry.version || '1.0.0';
            clipSource = 'Registro Canónico Local';
            validationStatus = regEntry.validationStatus || 'REQUIRES_LSEC_VALIDATION';
          }
        }
      }

      if (clip) {
        const clipDurSec = Math.max(0.35, (clip.durationMs || 1000) / 1000.0);
        const recommendedSpeed = Math.max(1.0, Math.min(2.0, Number((clipDurSec / slotSec).toFixed(2))));
        const clipWithSpeed = {
          ...clip,
          gloss: glossName,
          recommendedSpeed,
          startMs,
          endMs
        };

        playableClips.push(clipWithSpeed);
        sequencePlan.push({
          index,
          id: item.id || `g_${index}`,
          gloss: glossName,
          resolvedGloss: (clip.metadata && clip.metadata.resolvedGloss) || (resMeta && resMeta.resolved_gloss) || glossName,
          matchType: (clip.metadata && clip.metadata.matchType) || (resMeta && resMeta.match_type) || 'exact',
          needsReview: Boolean((clip.metadata && clip.metadata.needsReview) || (resMeta && resMeta.needs_review)),
          warning: (clip.metadata && clip.metadata.warning) || (resMeta && resMeta.warning) || null,
          clipId: clip.clipId || regEntry?.clipId || normKey,
          version: clipVersion,
          source: clipSource,
          status: 'AVAILABLE',
          validationStatus: validationStatus,
          recommendedSpeed,
          startMs,
          endMs
        });
      } else {
        // Glosa sin animación en v2.6/v2.5 ni en registro
        missingGlosses.push(glossName);
        sequencePlan.push({
          index,
          id: item.id || `g_${index}`,
          gloss: glossName,
          resolvedGloss: null,
          matchType: (resMeta && resMeta.match_type) || 'none',
          needsReview: false,
          clipId: null,
          version: null,
          status: (resMeta && resMeta.is_fingerspelling) ? 'FINGERSPELLING_PENDING' : 'MISSING_ANIMATION',
          validationStatus: 'NO_CLIP_AVAILABLE',
          startMs,
          endMs,
          warning: (resMeta && resMeta.warning) || `Sin animación v2.6/v2.5 ni clip registrado para la glosa "${glossName}". Se omite sin interrumpir el flujo.`
        });
      }
    }

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
   * @returns {Promise<Object>} Resultado de la adaptación
   */
  async playAdaptedSequence(inputData) {
    const result = await this.adaptProjectGlossesToSequence(inputData);

    if (result.playableClips.length > 0) {
      this.sequencer.playSequence(result.playableClips);
    } else {
      console.warn('[AvatarSyncController] No hay clips disponibles para reproducir en la secuencia suministrada.');
    }

    return result;
  }
}
