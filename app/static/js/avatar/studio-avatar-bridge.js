/**
 * LSEC Studio ⇄ LSEC Avatar — Puente de Integración 3D (studio-avatar-bridge.js)
 * 
 * Conecta reactivamente el estado central de Studio (appState) con el motor 3D
 * de LSEC Avatar (AvatarPanelController, Three.js, VRM 1.0, Pipeline v2.7/v2.6 Oficial)
 * y el Compilador de Secuencias Fluidas (SequenceCompiler):
 * 
 * 1. PiP Minimalista sobre el reproductor de video:
 *    - Fondo sólido contrastante (#20242b) calibrado para contrastar con la ropa oscura.
 *    - Encuadre estricto de torso a cabeza (preset 'pip_bust').
 *    - Ocultamiento de manos en reposo (las manos descansan bajo el borde inferior).
 * 2. Secuencias Fluidas de Señas (SequenceCompiler):
 *    - Evaluación determinista pura pose(t) compartida por reproducción en vivo (60 FPS),
 *      scrub de línea de tiempo y exportación de video cuadro por cuadro (30 FPS).
 *    - Cero retorno a reposo entre señas de una oración (umbral de pausa > 1.5 s).
 *    - Coarticulación C^1 (Hermite + minimum-jerk en so(3)) con anticipación dactilar.
 *    - Velocidad máxima 1.6x, lag máximo controlado de 1.0 s y extensión del PiP al final del video.
 * 3. Glosas letra por letra / dactilología pendientes:
 *    - Si la glosa es deletreada, el avatar permanece en pose de reposo neutro sin bloquear.
 * 4. Gestión dinámica de canvas entre el PiP y la pestaña lateral "Avatar 3D".
 * 5. Captura síncrona de fotogramas 3D para el exportador de video (CompositeVideoExporter).
 */

import { AvatarPanelController } from './avatar-controller.js?v=2.4.0';
import { SequenceCompiler, applyCompiledSampleToModel } from './sequence-compiler.js';

export class StudioAvatarBridge {
  constructor() {
    this.controller = null;
    this.currentLocation = 'pip'; // 'pip' | 'sidebar'
    this.pipHost = null;
    this.sidebarContainer = null;
    this.currentGlossKey = null;
    this.isReady = false;
    this.solidBgColor = '#20242b';

    // Motor de compilación de secuencia fluida (pose(t) determinista)
    this.fluidMode = true;
    this.compiler = new SequenceCompiler({
      maxSpeed: 1.6,
      minSpeed: 0.70,
      maxLagSec: 1.0,
      restGapThresholdSec: 1.5,
      extendEndForLag: true
    });
    this.clipMap = new Map();
    this.clipMapVersion = '2.7';
    this.lastSampleResult = null;
    this.isManualPreviewActive = false;
    this._extendedTailActive = false;
    this._extendedTailTime = 0;
    this._rebuildTimer = null;

    this.init();
  }

  /**
   * Limpia la caché de clips compilados cuando cambia la versión del catálogo ('2.7' | '2.6' | '2.5')
   * o se reinicia el proyecto.
   */
  clearClipCache(newVersion = null) {
    this.clipMap.clear();
    if (newVersion) {
      this.clipMapVersion = String(newVersion);
    }
    this.compiler.compiled = null;
    this.compiler.plan = null;
    this.lastSampleResult = null;
    this.currentGlossKey = null;
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

      // Conectar hook de pre-actualización de 60 FPS para muestreo continuo de SequenceCompiler
      this.controller.onPreUpdateCallback = (delta) => this.onEngineFrame(delta);

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

    if (window.appState?.state?.project) {
      this.preloadProjectSigns(window.appState.state.project);
    }
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

    // 1. Sincronización en tiempo real por reloj de reproducción o salto (seek)
    window.appState.subscribe('timeupdate', ({ time }) => {
      this._extendedTailActive = false;
      this.onTimeUpdate(time);
    });

    // 2. Play / Pause (appState emits boolean or { isPlaying })
    window.appState.subscribe('playbackStateChanged', (payload) => {
      if (!this.controller || this.isExportingDeterministic) return;
      const isPlaying = (typeof payload === 'object' && payload !== null) ? Boolean(payload.isPlaying) : Boolean(payload);
      this.isManualPreviewActive = false;

      if (!isPlaying) {
        const currentTime = Number(window.appState.state?.playback?.currentTime) || 0;
        const duration = Number(window.appState.state?.playback?.duration) ||
          Number(window.appState.state?.project?.media_info?.duration_seconds) || 0;
        const seqEnd = this.getSequenceEndTime(duration);

        // Política "se extiende el PiP": si el video llegó al final pero el avatar
        // aún tiene desfase acumulado (<= 1.0s + retorno a reposo), continuar animando el PiP
        if (this.fluidMode && duration > 0 && currentTime >= duration - 0.05 && seqEnd > currentTime + 0.03) {
          this._extendedTailActive = true;
          this._extendedTailTime = currentTime;
          return;
        }
        this._extendedTailActive = false;
        this.controller.pause();
      } else {
        this._extendedTailActive = false;
        if (typeof this.controller.resume === 'function') {
          this.controller.resume();
        } else if (this.controller.player) {
          this.controller.player.resume();
        }
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

    // 4. Carga, edición y limpieza de proyecto
    window.appState.subscribe('projectLoaded', (project) => {
      this.currentGlossKey = null;
      this.isManualPreviewActive = false;
      this._extendedTailActive = false;
      this.preloadProjectSigns(project);
    });

    const handleProjectMutation = () => {
      const proj = window.appState?.state?.project;
      if (proj) {
        proj.__sequentialGlossesNormalized = false;
        this.preloadProjectSigns(proj);
      }
    };

    window.appState.subscribe('glossesChanged', handleProjectMutation);
    window.appState.subscribe('segmentsChanged', handleProjectMutation);
    window.appState.subscribe('sentenceUpdated', handleProjectMutation);

    window.appState.subscribe('projectCleared', () => {
      this._extendedTailActive = false;
      this.clearClipCache();
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
   * Sincroniza los clips actualmente disponibles en caché hacia this.clipMap y recompila el plan de secuencia.
   * @param {Object} [project]
   * @returns {Object|null} Plan compilado por SequenceCompiler
   */
  rebuildSequencePlan(project = window.appState?.state?.project) {
    if (!project) {
      this.compiler.compiled = null;
      return null;
    }

    const syncCtrl = this.controller?.syncController;
    const activeVersion = String(syncCtrl?.preferredVersion || this.controller?.preferredVersion || '2.7');
    if (this.clipMapVersion !== activeVersion) {
      this.clipMap.clear();
      this.clipMapVersion = activeVersion;
    }

    const allGlosses = project.glosses || [];
    if (allGlosses.length > 1 && !project.__sequentialGlossesNormalized && window.appState?.resolveOverlappingGlossIntervals) {
      window.appState.resolveOverlappingGlossIntervals(allGlosses, project.segments || []);
      project.__sequentialGlossesNormalized = true;
    }

    const collectGlossName = (g) => {
      const name = String(g?.gloss || g?.lemma || '').trim().toUpperCase();
      if (!name) return;
      let cached = null;
      if (syncCtrl) {
        cached = typeof syncCtrl.getCachedClip === 'function'
          ? syncCtrl.getCachedClip(name, activeVersion)
          : syncCtrl.clipCache?.get(`${activeVersion}:${name}`);
      }
      if (!cached && this.controller?.clips && typeof this.controller.clips[name] === 'object') {
        cached = this.controller.clips[name];
      }
      if (cached && typeof cached === 'object') {
        this.clipMap.set(name, cached);
      }
    };

    for (const g of allGlosses) {
      collectGlossName(g);
    }
    if (Array.isArray(project.segments)) {
      for (const seg of project.segments) {
        if (Array.isArray(seg?.glosses)) {
          for (const g of seg.glosses) {
            collectGlossName(g);
          }
        }
      }
    }

    const videoDuration = Number(project.media_info?.duration_seconds) ||
      Number(window.appState?.state?.playback?.duration) || 0;

    return this.compiler.compile(project, this.clipMap, {
      maxSpeed: 1.6,
      minSpeed: 0.70,
      maxLagSec: 1.0,
      restGapThresholdSec: 1.5,
      extendEndForLag: true,
      videoDuration
    });
  }

  /**
   * Programa una recompilación diferida del plan cuando nuevos clips terminan de descargarse.
   */
  scheduleRebuildPlan() {
    if (this._rebuildTimer) return;
    this._rebuildTimer = setTimeout(() => {
      this._rebuildTimer = null;
      const proj = window.appState?.state?.project;
      if (proj) {
        this.rebuildSequencePlan(proj);
        if (!this.isExportingDeterministic && !this.isManualPreviewActive) {
          const t = Number(window.appState?.state?.playback?.currentTime) || 0;
          this.applyFluidSampleAtTime(t);
        }
      }
    }, 20);
  }

  /**
   * Devuelve el tiempo final efectivo de la secuencia del avatar (incluyendo extensión de PiP
   * si el avatar aún tiene lag acumulado al finalizar el video).
   * @param {number} [fallbackDuration=0]
   * @returns {number}
   */
  getSequenceEndTime(fallbackDuration = 0) {
    const proj = window.appState?.state?.project;
    if (proj && !this.compiler.compiled) {
      this.rebuildSequencePlan(proj);
    }
    return this.compiler.getSequenceEndTime(fallbackDuration);
  }

  /**
   * Evalúa determinísticamente el compilador en t = timeSec y aplica la pose resultante al modelo 3D.
   * @param {number} timeSec
   * @returns {Object|null} Resultado del muestreo
   */
  applyFluidSampleAtTime(timeSec) {
    if (!this.controller || !this.controller.engine?.currentModel) return null;
    const project = window.appState?.state?.project;
    if (!project) return null;

    const activeVersion = String(this.controller?.syncController?.preferredVersion || this.controller?.preferredVersion || '2.7');
    if (!this.compiler.compiled || this.clipMapVersion !== activeVersion) {
      this.rebuildSequencePlan(project);
    }

    // Verificar si la glosa nominalmente activa ya está en caché pero aún no en clipMap
    const nominalEntry = this.resolveActiveGlossEntry(project, timeSec);
    if (nominalEntry && nominalEntry.gloss) {
      const gName = String(nominalEntry.gloss.gloss || nominalEntry.gloss.lemma || '').trim().toUpperCase();
      if (gName && !this.clipMap.has(gName) && this.controller.syncController) {
        const newlyCached = typeof this.controller.syncController.getCachedClip === 'function'
          ? this.controller.syncController.getCachedClip(gName, activeVersion)
          : this.controller.syncController.clipCache?.get(`${activeVersion}:${gName}`);
        if (newlyCached) {
          this.clipMap.set(gName, newlyCached);
          this.rebuildSequencePlan(project);
        } else if (!this.isExportingDeterministic) {
          const isSingleLetterHyphenated = gName.includes('-') && gName.split('-').filter(Boolean).every(p => p.trim().length === 1);
          const isFs = Boolean(nominalEntry.gloss.is_fingerspelling || isSingleLetterHyphenated || nominalEntry.gloss.gloss_type === 'DACTILOLOGÍA');
          if (!isFs) {
            this.controller.syncController.loadClipAsync(gName, { version: activeVersion }).then((loaded) => {
              if (loaded && this.clipMapVersion === activeVersion) {
                this.clipMap.set(gName, loaded);
                this.scheduleRebuildPlan();
              }
            }).catch(() => {});
          }
        }
      }
    }

    if (this.controller.player) {
      this.controller.player.externalPoseControl = true;
    }

    const sampleResult = this.compiler.sample(timeSec);
    this.lastSampleResult = sampleResult;

    applyCompiledSampleToModel(
      this.controller.engine.currentModel,
      this.controller.isVRMActive,
      sampleResult
    );

    // Sincronizar HUD y metadatos de resolución con la seña actualmente ejecutada por el avatar
    const activeEntry = sampleResult.activeEntry;
    const glossKey = activeEntry
      ? `${activeEntry.orderIndex ?? 0}_${activeEntry.gloss}`
      : (sampleResult.phase === 'transition' ? `trans_${sampleResult.subtype || ''}` : 'idle');

    if (glossKey !== this.currentGlossKey) {
      this.currentGlossKey = glossKey;
      const displayGloss = activeEntry?.gloss || sampleResult.activeGloss || 'NEUTRAL';
      if (this.controller.activeGlossHud) {
        this.controller.activeGlossHud.textContent = displayGloss;
      }
      if (activeEntry?.gloss) {
        const resMeta = this.getResolutionMetaForGloss(activeEntry.gloss);
        if (resMeta) {
          this.controller.lastPlayedResolutionMeta = resMeta;
        }
        if (window.glossOverlay && typeof window.glossOverlay.refreshBadgeWarning === 'function') {
          window.glossOverlay.refreshBadgeWarning(activeEntry.gloss);
        }
      } else if (window.glossOverlay && typeof window.glossOverlay.render === 'function' && !this.isExportingDeterministic) {
        window.glossOverlay.render(timeSec);
      }
    }

    return sampleResult;
  }

  /**
   * Hook invocado en cada fotograma de 60 FPS de AvatarEngine antes de vrm.update(delta).
   * Garantiza interpolación suave a 60 FPS durante la reproducción en vivo y durante la
   * extensión de cola del PiP al final del video.
   * @param {number} delta
   */
  onEngineFrame(delta) {
    if (!this.fluidMode || this.isExportingDeterministic || this.isManualPreviewActive) return;
    const project = window.appState?.state?.project;
    if (!project) return;

    const isPlaying = Boolean(window.appState?.state?.playback?.isPlaying);
    if (isPlaying) {
      const videoEl = document.getElementById('main-video-element');
      let t = Number(window.appState?.state?.playback?.currentTime) || 0;
      if (videoEl && !videoEl.paused && videoEl.readyState >= 2 && Number.isFinite(videoEl.currentTime)) {
        t = videoEl.currentTime;
      }
      this._extendedTailActive = false;
      this.applyFluidSampleAtTime(t);
    } else if (this._extendedTailActive) {
      const rate = Number(window.appState?.state?.playback?.playbackRate) || 1.0;
      this._extendedTailTime += Math.max(0, Math.min(delta, 0.1)) * rate;
      const duration = Number(window.appState?.state?.playback?.duration) ||
        Number(project.media_info?.duration_seconds) || 0;
      const seqEnd = this.getSequenceEndTime(duration);

      this.applyFluidSampleAtTime(this._extendedTailTime);
      if (window.glossOverlay && typeof window.glossOverlay.render === 'function') {
        window.glossOverlay.render(this._extendedTailTime);
      }

      if (this._extendedTailTime >= seqEnd) {
        this._extendedTailActive = false;
      }
    }
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
      if (nextSt - et < 1.5) {
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
   * Devuelve los metadatos de resolución (matchType, needsReview, warning, resolvedGloss)
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
    this.isManualPreviewActive = false;
    this._extendedTailActive = false;
    this.currentGlossKey = null;
    const project = window.appState?.state?.project;
    if (project) {
      this.rebuildSequencePlan(project);
    }
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
   * Sincroniza la pose del avatar para el instante dado (reproducción o scrub en la línea de tiempo).
   * @param {number} time
   */
  onTimeUpdate(time) {
    if (!this.controller || this.isExportingDeterministic) return;
    const project = window.appState?.state?.project;
    if (!project) return;

    this.isManualPreviewActive = false;

    if (this.fluidMode) {
      this.applyFluidSampleAtTime(time);
      return;
    }

    // Fallback legado por clip individual (tope máximo 1.6x)
    const entry = this.resolveActiveGlossEntry(project, time);
    const activeGloss = entry ? entry.gloss : null;

    const glossKey = activeGloss ? (activeGloss.id || `${entry.index}_${activeGloss.gloss || activeGloss.lemma}`) : 'idle';
    if (glossKey === this.currentGlossKey) return;
    this.currentGlossKey = glossKey;

    if (activeGloss) {
      const glossName = (activeGloss.gloss || activeGloss.lemma || '').toUpperCase().trim();
      const isSingleLetterHyphenated = glossName.includes('-') && glossName.split('-').filter(Boolean).every(p => p.trim().length === 1);
      const isFingerspelling = Boolean(activeGloss.is_fingerspelling || isSingleLetterHyphenated || (activeGloss.gloss_type === 'DACTILOLOGÍA'));

      const basePlaybackRate = window.appState?.state?.playback?.playbackRate || 1.0;
      let dynamicSpeed = undefined;
      const cachedClip = this.controller.syncController?.getCachedClip
        ? this.controller.syncController.getCachedClip(glossName)
        : this.controller.syncController?.clipCache?.get(glossName);
      if (cachedClip && cachedClip.durationMs && entry.slotDurationSec > 0) {
        const clipSec = cachedClip.durationMs / 1000;
        const fitRatio = clipSec / Math.max(0.24, entry.slotDurationSec);
        dynamicSpeed = Math.max(0.70, Math.min(1.6, fitRatio)) * basePlaybackRate;
      }

      this.controller.playGloss(glossName, {
        isFingerspelling,
        gloss_type: activeGloss.gloss_type,
        speed: dynamicSpeed,
        slotDurationSec: entry.slotDurationSec,
        basePlaybackRate,
        coarticulate: true,
        coarticulationDurationSec: 0.14,
        returnToNeutralOnEnd: !entry.hasContiguousNextGloss
      }).then(() => {
        if (window.glossOverlay && typeof window.glossOverlay.refreshBadgeWarning === 'function') {
          window.glossOverlay.refreshBadgeWarning(glossName);
        }
      }).catch(() => {});
    } else {
      if (this.controller.player && this.controller.clips?.NEUTRAL) {
        this.controller.player.play(this.controller.clips.NEUTRAL, {
          coarticulate: true,
          coarticulationDurationSec: 0.18,
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
    this.isManualPreviewActive = false;
    const project = window.appState?.state?.project;

    if (project && this.fluidMode) {
      const entry = this.resolveActiveGlossEntry(project, videoTimeSec);
      if (entry && entry.gloss && this.controller.syncController) {
        const glossName = String(entry.gloss.gloss || entry.gloss.lemma || '').toUpperCase().trim();
        const isSingleLetterHyphenated = glossName.includes('-') && glossName.split('-').filter(Boolean).every(p => p.trim().length === 1);
        const isFingerspelling = Boolean(entry.gloss.is_fingerspelling || isSingleLetterHyphenated || (entry.gloss.gloss_type === 'DACTILOLOGÍA'));
        if (glossName && !isFingerspelling && !this.clipMap.has(glossName)) {
          const loaded = await this.controller.syncController.loadClipAsync(glossName);
          if (loaded) {
            this.clipMap.set(glossName, loaded);
            this.rebuildSequencePlan(project);
          }
        }
      }

      this.applyFluidSampleAtTime(videoTimeSec);
      this.controller.stepDeterministic(dt);
      return;
    }

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
            dynamicSpeed = Math.max(0.70, Math.min(1.6, clipSec / Math.max(0.24, entry.slotDurationSec)));
          }
          await this.controller.playGloss(glossName, {
            isFingerspelling,
            gloss_type: activeGloss.gloss_type,
            speed: dynamicSpeed,
            slotDurationSec: entry.slotDurationSec,
            basePlaybackRate: 1.0,
            coarticulate: true,
            coarticulationDurationSec: 0.14,
            returnToNeutralOnEnd: !entry.hasContiguousNextGloss
          });
        } else if (this.controller.player && this.controller.clips?.NEUTRAL) {
          this.controller.player.play(this.controller.clips.NEUTRAL, {
            coarticulate: true,
            coarticulationDurationSec: 0.18,
            returnToNeutralOnEnd: true
          });
        }
      }
    }

    this.controller.stepDeterministic(dt);
  }

  /**
   * Precarga en segundo plano todas las señas léxicas de la transcripción (incluyendo compuestas
   * con guión como PRO1-PL o MÁS-DE) y compila el plan de secuencia fluida para cero latencia.
   */
  async preloadProjectSigns(project) {
    if (!project || !this.controller?.syncController) return;
    const glosses = project.glosses || [];
    if (glosses.length > 1 && window.appState?.resolveOverlappingGlossIntervals) {
      window.appState.resolveOverlappingGlossIntervals(glosses, project.segments || []);
      project.__sequentialGlossesNormalized = true;
    }

    // Compilación inicial rápida con los clips ya presentes en caché
    this.rebuildSequencePlan(project);

    const uniqueNames = new Set();
    for (const g of glosses) {
      const name = String(g?.gloss || g?.lemma || '').trim().toUpperCase();
      const isSingleLetterHyphenated = name.includes('-') && name.split('-').filter(Boolean).every(p => p.trim().length === 1);
      if (name && !isSingleLetterHyphenated && g.gloss_type !== 'DACTILOLOGÍA') {
        uniqueNames.add(name);
      }
    }
    if (Array.isArray(project.segments)) {
      for (const seg of project.segments) {
        if (Array.isArray(seg?.glosses)) {
          for (const g of seg.glosses) {
            const name = String(g?.gloss || g?.lemma || '').trim().toUpperCase();
            const isSingleLetterHyphenated = name.includes('-') && name.split('-').filter(Boolean).every(p => p.trim().length === 1);
            if (name && !isSingleLetterHyphenated && g.gloss_type !== 'DACTILOLOGÍA') {
              uniqueNames.add(name);
            }
          }
        }
      }
    }

    const targetVersion = String(this.controller?.syncController?.preferredVersion || this.controller?.preferredVersion || '2.7');
    const loadPromises = [];
    for (const name of uniqueNames) {
      const p = this.controller.syncController.loadClipAsync(name, { version: targetVersion })
        .then((clip) => {
          if (clip && this.clipMapVersion === targetVersion) {
            this.clipMap.set(name, clip);
            this.scheduleRebuildPlan();
          }
          return clip;
        })
        .catch(() => null);
      loadPromises.push(p);
    }

    await Promise.all(loadPromises);
    if (this.clipMapVersion !== targetVersion) return;
    this.rebuildSequencePlan(project);
    if (!this.isExportingDeterministic && !this.isManualPreviewActive) {
      const currTime = Number(window.appState?.state?.playback?.currentTime) || 0;
      this.applyFluidSampleAtTime(currTime);
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
