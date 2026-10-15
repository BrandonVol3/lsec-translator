/**
 * LSEC Studio ⇄ LSEC Avatar — Puente de Integración 3D (studio-avatar-bridge.js)
 * 
 * Conecta reactivamente el estado central de Studio (appState) con el motor 3D
 * de LSEC Avatar (AvatarPanelController, Three.js, VRM 1.0, Pipeline v2.6 Oficial):
 * 
 * 1. PiP Minimalista sobre el reproductor de video:
 *    - Fondo sólido contrastante (#20242b) calibrado para contrastar con la ropa oscura.
 *    - Encuadre estricto de torso a cabeza (preset 'pip_bust').
 *    - Ocultamiento de manos en reposo (las manos descansan bajo el borde inferior).
 * 2. Glosas letra por letra / dactilología pendientes:
 *    - Si la glosa es deletreada, el avatar permanece en pose de reposo neutro sin bloquear.
 * 3. Sincronización continua de reproducción, saltos (seek) y velocidad (playbackRate).
 * 4. Gestión dinámica de canvas entre el PiP y la pestaña lateral "Avatar 3D".
 * 5. Captura síncrona de fotogramas 3D para el exportador de video (CompositeVideoExporter).
 */

import { AvatarPanelController } from './avatar-controller.js?v=2.4.0';

export class StudioAvatarBridge {
  constructor() {
    this.controller = null;
    this.currentLocation = 'pip'; // 'pip' | 'sidebar'
    this.pipHost = null;
    this.sidebarContainer = null;
    this.currentGlossKey = null;
    this.isReady = false;
    this.solidBgColor = '#20242b';

    this.init();
  }

  async init() {
    if (document.readyState === 'loading') {
      await new Promise(res => document.addEventListener('DOMContentLoaded', res));
    }

    // Esperar a que el host de PiP esté en el DOM (creado por GlossOverlayController)
    let retries = 0;
    while (!document.getElementById('avatar-pip-canvas-host') && retries < 40) {
      await new Promise(r => setTimeout(r, 50));
      retries++;
    }

    this.pipHost = document.getElementById('avatar-pip-canvas-host');
    this.sidebarContainer = document.getElementById('view-side-avatar');

    try {
      // 1. Inicializar AvatarPanelController usando el contenedor lateral
      this.controller = new AvatarPanelController('view-side-avatar');
      window.avatarController = this.controller;

      // 2. Acoplar al PiP inicialmente
      if (this.controller && this.controller.engine) {
        this.dockToPip();
        this.isReady = true;
      }
    } catch (err) {
      console.error('[StudioAvatarBridge] Error inicializando AvatarPanelController:', err);
    }

    this.subscribeAppState();
    this.subscribeSidebarTabs();
  }

  /**
   * Acopla el canvas WebGL al PiP minimalista sobre el video.
   */
  dockToPip() {
    if (!this.controller || !this.controller.engine) return;
    this.pipHost = document.getElementById('avatar-pip-canvas-host');
    const pipContainer = document.getElementById('gloss-overlay-container');
    const canvas = this.controller.engine.canvas;

    if (pipContainer && pipContainer.dataset.hiddenBySidebar === 'true') {
      delete pipContainer.dataset.hiddenBySidebar;
      const glossesEnabled = window.appState?.state?.overlays?.glossesEnabled !== false;
      pipContainer.style.display = glossesEnabled ? 'flex' : 'none';
    }

    if (this.pipHost && canvas && canvas.parentElement !== this.pipHost) {
      this.pipHost.appendChild(canvas);
      canvas.style.width = '100%';
      canvas.style.height = '100%';
      canvas.style.display = 'block';
      canvas.style.borderRadius = '6px';
    }

    this.currentLocation = 'pip';
    this.controller.setClearColor(this.solidBgColor);
    if (!this.isExportingDeterministic) {
      this.controller.setCameraPreset('pip_bust');
      this.controller.engine.onResize();
    } else if (this._preExportCameraState) {
      this._preExportCameraState.preset = 'pip_bust';
      this._preExportCameraState.position = null;
      this._preExportCameraState.target = null;
    }
  }

  /**
   * Acopla el canvas WebGL a la pestaña lateral de inspección "Avatar 3D".
   */
  dockToSidebar() {
    if (!this.controller || !this.controller.engine) return;
    const sidebarViewport = document.getElementById('avatar-viewport-wrap');
    const pipContainer = document.getElementById('gloss-overlay-container');
    const canvas = this.controller.engine.canvas;

    if (sidebarViewport && canvas && canvas.parentElement !== sidebarViewport) {
      sidebarViewport.appendChild(canvas);
      canvas.style.width = '100%';
      canvas.style.height = '100%';
      canvas.style.display = 'block';
      canvas.style.borderRadius = '0px';
    }

    if (pipContainer) {
      pipContainer.dataset.hiddenBySidebar = 'true';
      pipContainer.style.display = 'none';
    }

    this.currentLocation = 'sidebar';
    if (!this.isExportingDeterministic) {
      this.controller.setCameraPreset('medium');
      this.controller.engine.onResize();
    } else if (this._preExportCameraState) {
      this._preExportCameraState.preset = 'medium';
      this._preExportCameraState.position = null;
      this._preExportCameraState.target = null;
    }
  }

  subscribeAppState() {
    if (!window.appState) return;

    // 1. Sincronización en tiempo real por reloj de reproducción
    window.appState.subscribe('timeupdate', ({ time }) => {
      this.onTimeUpdate(time);
    });

    // 2. Play / Pause (appState emits boolean or { isPlaying })
    window.appState.subscribe('playbackStateChanged', (payload) => {
      if (!this.controller || this.isExportingDeterministic) return;
      const isPlaying = (typeof payload === 'object' && payload !== null) ? Boolean(payload.isPlaying) : Boolean(payload);
      if (!isPlaying) {
        this.controller.pause();
      } else if (typeof this.controller.resume === 'function') {
        this.controller.resume();
      } else if (this.controller.player) {
        this.controller.player.resume();
      }
    });

    // 3. Velocidad de reproducción (appState emits number or { playbackRate })
    window.appState.subscribe('playbackRateChanged', (payload) => {
      if (!this.controller) return;
      const rate = (typeof payload === 'object' && payload !== null) ? Number(payload.playbackRate) : Number(payload);
      if (Number.isFinite(rate) && rate > 0) {
        this.controller.setSpeed(rate);
      }
    });

    // 4. Carga y limpieza de proyecto
    window.appState.subscribe('projectLoaded', (project) => {
      this.currentGlossKey = null;
      this.preloadProjectSigns(project);
    });

    window.appState.subscribe('projectCleared', () => {
      this.currentGlossKey = null;
      if (this.controller) {
        this.controller.stop();
      }
    });
  }

  subscribeSidebarTabs() {
    const checkTab = () => {
      const avatarView = document.getElementById('view-side-avatar');
      if (avatarView && avatarView.style.display !== 'none') {
        if (this.currentLocation !== 'sidebar') {
          this.dockToSidebar();
        }
      } else {
        if (this.currentLocation !== 'pip') {
          this.dockToPip();
        }
      }
    };

    const tabBtns = [
      'tab-btn-side-transcript',
      'tab-btn-side-inspector',
      'tab-btn-side-subtitles',
      'tab-btn-side-avatar'
    ];

    tabBtns.forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener('click', () => {
          setTimeout(checkTab, 50);
        });
      }
    });
  }

  /**
   * Resuelve la glosa activa y su ventana temporal en el instante dado,
   * garantizando que ninguna glosa (incluyendo SER, CON, ESO, PRO1-PL, etc.) sea omitida.
   * @param {Object} project
   * @param {number} time
   * @returns {Object|null}
   */
  resolveActiveGlossEntry(project, time) {
    if (!project) return null;
    const allGlosses = project.glosses || [];

    // Asegurar normalización secuencial si aún existen intervalos solapados
    if (allGlosses.length > 1 && !project.__sequentialGlossesNormalized && window.appState?.resolveOverlappingGlossIntervals) {
      window.appState.resolveOverlappingGlossIntervals(allGlosses, project.segments || []);
      project.__sequentialGlossesNormalized = true;
    }

    let activeIdx = -1;
    let activeGloss = null;

    for (let i = 0; i < allGlosses.length; i++) {
      const g = allGlosses[i];
      const st = g.start_seconds !== undefined ? g.start_seconds : (g.start_time !== undefined ? g.start_time : (g.start !== undefined ? g.start : 0));
      const et = g.end_seconds !== undefined ? g.end_seconds : (g.end_time !== undefined ? g.end_time : (g.end !== undefined ? g.end : 0));
      if (time >= st && time <= et) {
        activeIdx = i;
        activeGloss = g;
        break;
      }
    }

    if (!activeGloss && project.segments) {
      const activeSeg = project.segments.find(s => {
        const st = s.start_time !== undefined ? s.start_time : (s.start_seconds || 0);
        const et = s.end_time !== undefined ? s.end_time : (s.end_seconds || 0);
        return time >= st && time <= et;
      });

      if (activeSeg && activeSeg.glosses && activeSeg.glosses.length > 0) {
        const sStart = activeSeg.start_time !== undefined ? activeSeg.start_time : (activeSeg.start_seconds || 0);
        const sEnd = activeSeg.end_time !== undefined ? activeSeg.end_time : (activeSeg.end_seconds || 0);
        const sDur = Math.max(0.2, sEnd - sStart);
        const progress = Math.min(0.99, Math.max(0, (time - sStart) / sDur));
        const idx = Math.floor(progress * activeSeg.glosses.length);
        activeGloss = activeSeg.glosses[idx] || activeSeg.glosses[0];
      }
    }

    if (!activeGloss) return null;

    const st = activeGloss.start_seconds !== undefined ? activeGloss.start_seconds : (activeGloss.start_time !== undefined ? activeGloss.start_time : (activeGloss.start !== undefined ? activeGloss.start : 0));
    const et = activeGloss.end_seconds !== undefined ? activeGloss.end_seconds : (activeGloss.end_time !== undefined ? activeGloss.end_time : (activeGloss.end !== undefined ? activeGloss.end : st + 0.45));
    const slotDurationSec = Math.max(0.22, et - st);

    let hasContiguousNextGloss = false;
    if (activeIdx >= 0 && activeIdx + 1 < allGlosses.length) {
      const nextG = allGlosses[activeIdx + 1];
      const nextSt = nextG.start_seconds !== undefined ? nextG.start_seconds : (nextG.start_time !== undefined ? nextG.start_time : 0);
      if (nextSt - et < 0.25) {
        hasContiguousNextGloss = true;
      }
    }

    return {
      gloss: activeGloss,
      index: activeIdx,
      startSec: st,
      endSec: et,
      slotDurationSec,
      hasContiguousNextGloss
    };
  }

  /**
   * Devuelve los metadatos de resolución v2.6 (matchType, needsReview, warning, resolvedGloss)
   * para mostrar avisos discretos en el PiP cuando una seña usa aproximación o requiere revisión.
   * @param {string} glossName
   * @returns {Object|null}
   */
  getResolutionMetaForGloss(glossName) {
    if (!glossName || !this.controller?.syncController) return null;
    return this.controller.syncController.getResolutionMeta(glossName);
  }

  /**
   * Inicia el modo de exportación determinista pausando el bucle rAF en segundo plano
   * y forzando el encuadre calibrado desde el torso a la cabeza ('pip_bust', aspecto 1:1.15)
   * independientemente de qué pestaña o preset de cámara estuviera activo antes de exportar.
   */
  beginDeterministicExport() {
    this.isExportingDeterministic = true;
    this.currentGlossKey = null;
    if (this.controller && this.controller.engine) {
      const engine = this.controller.engine;
      engine.stop();

      // Guardar estado previo de cámara para restaurar tras la exportación
      this._preExportCameraState = {
        preset: engine.currentPreset || (this.currentLocation === 'sidebar' ? 'medium' : 'pip_bust'),
        fov: engine.camera ? engine.camera.fov : 32,
        position: engine.camera ? engine.camera.position.clone() : null,
        target: engine.controls ? engine.controls.target.clone() : null
      };

      // Forzar fondo sólido y bloquear encuadre del torso a la cabeza ('pip_bust') con proporción PiP (1:1.15)
      this.controller.setClearColor(this.solidBgColor);
      if (typeof engine.lockExportCamera === 'function') {
        engine.lockExportCamera('pip_bust', 360, 414);
      } else {
        this.controller.setCameraPreset('pip_bust');
        engine.exportLockSize = { width: 360, height: 414 };
        engine.onResize();
      }
      engine.stepDeterministic(0);
    }
  }

  /**
   * Finaliza el modo de exportación determinista, restaura el encuadre previo y reanuda el bucle rAF en vivo.
   */
  endDeterministicExport() {
    this.isExportingDeterministic = false;
    this.currentGlossKey = null;
    if (this.controller && this.controller.engine) {
      const engine = this.controller.engine;
      if (typeof engine.unlockExportCamera === 'function') {
        engine.unlockExportCamera();
      } else {
        engine.exportLockSize = null;
      }

      if (this._preExportCameraState) {
        const saved = this._preExportCameraState;
        this._preExportCameraState = null;
        if (saved.preset) {
          this.controller.setCameraPreset(saved.preset);
        }
        if (saved.position && engine.camera) {
          engine.camera.position.copy(saved.position);
        }
        if (saved.target && engine.controls) {
          engine.controls.target.copy(saved.target);
        }
        if (saved.fov && engine.camera) {
          engine.camera.fov = saved.fov;
          engine.camera.updateProjectionMatrix();
        }
        if (engine.controls) {
          engine.controls.update();
        }
      } else {
        this.controller.setCameraPreset(this.currentLocation === 'sidebar' ? 'medium' : 'pip_bust');
      }

      engine.onResize();
      engine.start();
    }
  }

  /**
   * Resuelve la glosa activa en el tiempo actual y solicita la animación.
   * @param {number} time
   */
  onTimeUpdate(time) {
    if (!this.controller || this.isExportingDeterministic) return;
    const project = window.appState?.state?.project;
    if (!project) return;

    const entry = this.resolveActiveGlossEntry(project, time);
    const activeGloss = entry ? entry.gloss : null;

    const glossKey = activeGloss ? (activeGloss.id || `${entry.index}_${activeGloss.gloss || activeGloss.lemma}`) : 'idle';
    if (glossKey === this.currentGlossKey) return;
    this.currentGlossKey = glossKey;

    if (activeGloss) {
      const glossName = (activeGloss.gloss || activeGloss.lemma || '').toUpperCase().trim();
      const isSingleLetterHyphenated = glossName.includes('-') && glossName.split('-').filter(Boolean).every(p => p.trim().length === 1);
      const isFingerspelling = Boolean(activeGloss.is_fingerspelling || isSingleLetterHyphenated || (activeGloss.gloss_type === 'DACTILOLOGÍA'));

      // Calcular timeScale dinámico para que la seña quepa legiblemente en su ventana sin ser omitida
      const basePlaybackRate = window.appState?.state?.playback?.playbackRate || 1.0;
      let dynamicSpeed = undefined;
      const cachedClip = this.controller.syncController?.getCachedClip
        ? this.controller.syncController.getCachedClip(glossName)
        : this.controller.syncController?.clipCache?.get(glossName);
      if (cachedClip && cachedClip.durationMs && entry.slotDurationSec > 0) {
        const clipSec = cachedClip.durationMs / 1000;
        const fitRatio = clipSec / Math.max(0.24, entry.slotDurationSec);
        dynamicSpeed = Math.max(1.0, Math.min(2.6, fitRatio)) * basePlaybackRate;
      }

      // Reproducir seña en avatar con coarticulación SLERP sin regresar a neutral entre señas contiguas
      this.controller.playGloss(glossName, {
        isFingerspelling,
        gloss_type: activeGloss.gloss_type,
        speed: dynamicSpeed,
        slotDurationSec: entry.slotDurationSec,
        basePlaybackRate,
        coarticulate: true,
        coarticulationDurationSec: 0.12,
        returnToNeutralOnEnd: !entry.hasContiguousNextGloss
      }).then(() => {
        if (window.glossOverlay && typeof window.glossOverlay.refreshBadgeWarning === 'function') {
          window.glossOverlay.refreshBadgeWarning(glossName);
        }
      }).catch(() => {});
    } else {
      // Fuera de intervalo de seña: volver a reposo neutro (manos abajo, ocultas en PiP)
      if (this.controller.player && this.controller.clips?.NEUTRAL) {
        this.controller.player.play(this.controller.clips.NEUTRAL, {
          coarticulate: true,
          coarticulationDurationSec: 0.16,
          returnToNeutralOnEnd: true
        });
      }
    }
  }

  /**
   * Avanza el avatar determinísticamente para un instante de video dado y un delta fijo dt (ej. 1/30 s).
   * Usado por el exportador offline cuadro por cuadro a 30 FPS constantes.
   * @param {number} videoTimeSec
   * @param {number} dt
   */
  async stepAtVideoTime(videoTimeSec, dt = 1 / 30) {
    if (!this.controller) return;
    const project = window.appState?.state?.project;
    if (project) {
      const entry = this.resolveActiveGlossEntry(project, videoTimeSec);
      const activeGloss = entry ? entry.gloss : null;
      const glossKey = activeGloss ? (activeGloss.id || `${entry.index}_${activeGloss.gloss || activeGloss.lemma}`) : 'idle';

      if (glossKey !== this.currentGlossKey) {
        this.currentGlossKey = glossKey;
        if (activeGloss) {
          const glossName = (activeGloss.gloss || activeGloss.lemma || '').toUpperCase().trim();
          const isSingleLetterHyphenated = glossName.includes('-') && glossName.split('-').filter(Boolean).every(p => p.trim().length === 1);
          const isFingerspelling = Boolean(activeGloss.is_fingerspelling || isSingleLetterHyphenated || (activeGloss.gloss_type === 'DACTILOLOGÍA'));

          if (!isFingerspelling && this.controller.syncController) {
            await this.controller.syncController.loadClipAsync(glossName);
          }
          const cachedClip = this.controller.syncController?.getCachedClip
            ? this.controller.syncController.getCachedClip(glossName)
            : this.controller.syncController?.clipCache?.get(glossName);
          let dynamicSpeed = undefined;
          if (cachedClip && cachedClip.durationMs && entry.slotDurationSec > 0) {
            const clipSec = cachedClip.durationMs / 1000;
            dynamicSpeed = Math.max(1.0, Math.min(2.6, clipSec / Math.max(0.24, entry.slotDurationSec)));
          }
          await this.controller.playGloss(glossName, {
            isFingerspelling,
            gloss_type: activeGloss.gloss_type,
            speed: dynamicSpeed,
            slotDurationSec: entry.slotDurationSec,
            basePlaybackRate: 1.0,
            coarticulate: true,
            coarticulationDurationSec: 0.12,
            returnToNeutralOnEnd: !entry.hasContiguousNextGloss
          });
        } else if (this.controller.player && this.controller.clips?.NEUTRAL) {
          this.controller.player.play(this.controller.clips.NEUTRAL, {
            coarticulate: true,
            coarticulationDurationSec: 0.16,
            returnToNeutralOnEnd: true
          });
        }
      }
    }

    this.controller.stepDeterministic(dt);
  }

  /**
   * Precarga en segundo plano todas las señas léxicas de la transcripción (incluyendo compuestas con guión como PRO1-PL o MÁS-DE) para cero latencia.
   */
  async preloadProjectSigns(project) {
    if (!project || !this.controller?.syncController) return;
    const glosses = project.glosses || [];
    if (glosses.length > 1 && window.appState?.resolveOverlappingGlossIntervals) {
      window.appState.resolveOverlappingGlossIntervals(glosses, project.segments || []);
      project.__sequentialGlossesNormalized = true;
    }
    for (const g of glosses) {
      const name = (g.gloss || g.lemma || '').trim();
      const isSingleLetterHyphenated = name.includes('-') && name.split('-').filter(Boolean).every(p => p.trim().length === 1);
      if (name && !isSingleLetterHyphenated && g.gloss_type !== 'DACTILOLOGÍA') {
        this.controller.syncController.loadClipAsync(name).catch(() => {});
      }
    }
  }

  /**
   * Captura el frame actual renderizado (para exportador de video).
   * @returns {HTMLCanvasElement|null}
   */
  captureFrame() {
    return this.controller ? this.controller.captureFrame() : null;
  }

  /**
   * Obtiene el elemento canvas WebGL activo.
   */
  getCanvas() {
    return this.controller?.engine?.canvas || null;
  }
}

// Instancia global del puente
if (typeof window !== 'undefined') {
  window.StudioAvatarBridge = StudioAvatarBridge;
  window.studioAvatarBridge = new StudioAvatarBridge();
}
