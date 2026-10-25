/**
 * LSEC Studio — Controlador Principal del Avatar 3D (AvatarPanelController)
 * 
 * Integra todos los subsistemas del avatar 3D:
 * - Motor de renderizado (AvatarEngine);
 * - Rig técnico de reserva (TechnicalRig);
 * - Cargador de modelos VRM 1.0 (VRMLoaderService);
 * - Reproductor de clips esqueléticos (SignPlayer);
 * - Secuenciador de glosas continuas (SignSequencer);
 * - Sincronizador lingüístico con LSEC Studio (AvatarSyncController);
 * - Gestión de interfaz, botones, selectores y avisos de validación;
 * - Monitoreo de rendimiento en tiempo real (FPS, memoria, tiempos de carga, consola).
 */

import { AvatarEngine } from './avatar-engine.js?v=3.1.8';
import { TechnicalRig } from './technical-rig.js';
import { VRMLoaderService } from './vrm-loader.js';
import { SignPlayer } from './sign-player.js';
import { SignSequencer } from './sign-sequencer.js';
import { AvatarSyncController } from './avatar-sync-controller.js';
import { NonManualController } from './non-manual-controller.js';
import {
  getAllTechnicalClips,
  getTechnicalClipsCategorized,
  createNeutralClip,
  createSaludarDemoClip,
  createNegacionDemoClip
} from './sign-clip-factory.js';
import { defaultAnimationCache } from './animation-cache.js';
import { validateSignClip } from './sign-animation-schema.js';
import { HUMAN_BONE_NAMES } from './sign-animation-schema.js';
import {
  trimSignClipStroke,
  convertDirectAnimationToSignClip
} from './sign-animation-schema.js';
import {
  renderAvatarClipOptions,
  buildAvatarPanelDOM,
  bindAvatarPanelDOM,
  syncAvatarPresetButtons
} from './avatar-controller-dom.js';
import {
  BONE_LOWER_MAP,
  BONE_ALIASES,
  normalizeBoneName,
  detectDatasetQuaternionLayout,
  loadAvatarManifestClips,
  applyAvatarToonVisualShading,
  playAvatarWeekSequence,
  playAvatarAllTestsSequence,
  exportAvatarCurrentClip,
  updateAvatarFPSMetrics,
  updateAvatarPerfDisplay,
  getAvatarPerformanceReport,
  loadInitialAvatarModel,
  activateAvatarTechnicalRig,
  loadAvatarVRMFromFile,
  loadAvatarVRMFromUrl,
  handleVRMLoadSuccess
} from './avatar-controller-vrm-io.js';

export {
  BONE_LOWER_MAP,
  BONE_ALIASES,
  normalizeBoneName,
  detectDatasetQuaternionLayout
};

export class AvatarPanelController {
  constructor(panelContainerId = 'view-side-avatar') {
    this.container = document.getElementById(panelContainerId);

    // Subsistemas
    this.engine = null;
    this.vrmLoader = null;
    this.technicalRig = null;
    this.player = null;
    this.sequencer = null;
    this.syncController = null;
    this.nonManual = null;

    // Estado del modelo
    this.isVRMActive = false;
    this.currentModelSource = 'TECHNICAL_RIG'; // 'TECHNICAL_RIG' | 'VRM_LOCAL'
    this.preferredVersion = '2.7';

    // Catálogo de clips técnicos precargados
    this.clips = getAllTechnicalClips();
    this.clipLoaders = {};
    this.categories = getTechnicalClipsCategorized();
    this.selectedClipId = 'SALUDAR_DEMO';

    // Métricas de Rendimiento en Tiempo Real
    this.perfMetrics = {
      loadTimeMs: 0,
      fps: 60,
      frameCount: 0,
      lastFpsTime: (typeof performance !== 'undefined' ? performance.now() : 0),
      usedMemoryMB: 0,
      consoleErrors: 0,
      consoleWarnings: 0
    };

    this.setupConsoleMonitoring();
    this.init();
  }

  setupConsoleMonitoring() {
    if (window.__avatarConsoleMonitored) return;
    window.__avatarConsoleMonitored = true;

    const originalError = console.error;
    const originalWarn = console.warn;

    console.error = (...args) => {
      this.perfMetrics.consoleErrors++;
      originalError.apply(console, args);
    };

    console.warn = (...args) => {
      this.perfMetrics.consoleWarnings++;
      originalWarn.apply(console, args);
    };
  }

  init() {
    if (this.container && !this.container.querySelector('#avatar-webgl-canvas')) {
      this.buildDOM();
    }
    this.bindDOM();
    this.initSubsystems();
    this.initClipsCache();
    this.loadManifestClips();
    this.loadInitialAvatar();
  }

  renderClipOptions() {
    renderAvatarClipOptions(this);
  }

  async loadManifestClips() {
    return loadAvatarManifestClips(this);
  }

  buildDOM() {
    // Construye el panel con el selector <select id="select-avatar-version"> y controles 3D
    buildAvatarPanelDOM(this);
  }

  bindDOM() {
    bindAvatarPanelDOM(this);
  }

  initSubsystems() {
    try {
      this.engine = new AvatarEngine(this.canvas);
      this.vrmLoader = new VRMLoaderService();
      this.technicalRig = new TechnicalRig();
      this.player = new SignPlayer();
      this.sequencer = new SignSequencer(this.player);
      this.syncController = new AvatarSyncController(this.sequencer);
      this.nonManual = new NonManualController();

      this.mixer = {
        update: (dt) => this.stepDeterministic(dt)
      };
      this.lastPlayedResolutionMeta = null;
      this.onPreUpdateCallback = null;

      this.engine.setUpdateCallback((delta) => {
        if (typeof this.onPreUpdateCallback === 'function') {
          this.onPreUpdateCallback(delta);
        }
        this.sequencer.update(delta);
        this.updateFPSMetrics();
      });

      this.player.onProgress = ({ currentTime, duration, progress }) => {
        this.updateTimeDisplay(currentTime, duration);
        if (this.progressBarFill) {
          this.progressBarFill.style.width = `${(progress * 100).toFixed(1)}%`;
        }
      };

      this.player.onStateChange = (state) => {
        this.updateStatusDisplay(state);
      };

      this.sequencer.onGlossChanged = ({ gloss, clipId, index, total }) => {
        if (this.activeGlossHud) {
          this.activeGlossHud.textContent = gloss || '—';
        }
        this.updateStatusDisplay(`Secuencia: ${index + 1}/${total}`);
      };

      this.sequencer.onSequenceEnded = () => {
        this.updateStatusDisplay('Completado');
        if (this.activeGlossHud) {
          this.activeGlossHud.textContent = 'NEUTRAL';
        }
      };

      this.engine.start();
      console.info('[AvatarPanelController] Subsistemas del avatar inicializados correctamente.');
    } catch (err) {
      console.error('[AvatarPanelController] Error al inicializar subsistemas:', err);
      this.showError('No se pudo inicializar WebGL o Three.js en este navegador.');
    }
  }

  initClipsCache() {
    for (const [id, clip] of Object.entries(this.clips)) {
      if (clip && typeof clip === 'object') {
        defaultAnimationCache.setClip(clip.clipId || `${id}_V1`, clip);
      }
    }
  }

  updateFPSMetrics() {
    updateAvatarFPSMetrics(this);
  }

  updatePerfDisplay() {
    updateAvatarPerfDisplay(this);
  }

  getPerformanceReport() {
    return getAvatarPerformanceReport(this);
  }

  async loadInitialAvatar() {
    return loadInitialAvatarModel(this);
  }

  activateTechnicalRig() {
    activateAvatarTechnicalRig(this);
  }

  async loadVRMFromFile(file) {
    return loadAvatarVRMFromFile(this, file);
  }

  async loadVRMFromUrl(url) {
    return loadAvatarVRMFromUrl(this, url);
  }

  onVRMLoadSuccess(vrm, sourceName) {
    handleVRMLoadSuccess(this, vrm, sourceName);
  }

  applyToonVisualShading(vrm) {
    applyAvatarToonVisualShading(this, vrm);
  }

  async _resolveClipForSelection(rawKey) {
    const nfcKey = String(rawKey || 'NEUTRAL').normalize('NFC').trim();
    const upperKey = nfcKey.toUpperCase();
    const activeVer = this.preferredVersion || '2.7';

    const loader = this.clipLoaders && (this.clipLoaders[rawKey] || this.clipLoaders[nfcKey] || this.clipLoaders[upperKey]);
    let clip = this.clips[rawKey] || this.clips[nfcKey] || this.clips[upperKey];

    const clipVer = clip && typeof clip === 'object'
      ? (clip.metadata?.versionServed || clip.metadata?.version_served || clip.metadata?.standardizedVersion)
      : null;

    if (typeof clip === 'function') {
      try {
        clip = await clip();
        if (clip) {
          this.clips[rawKey] = clip;
          this.clips[nfcKey] = clip;
          this.clips[upperKey] = clip;
        }
      } catch (e) {
        console.error('Error al resolver clip dinámico:', e);
        clip = null;
      }
    } else if (loader && clipVer && String(clipVer) !== String(activeVer)) {
      try {
        clip = await loader();
        if (clip) {
          this.clips[rawKey] = clip;
          this.clips[nfcKey] = clip;
          this.clips[upperKey] = clip;
        }
      } catch (e) {
        console.error('Error al recargar clip dinámico para nueva versión:', e);
      }
    } else if ((!clip || (clipVer && String(clipVer) !== String(activeVer) && !clip.metadata?.isCustomImport)) && this.syncController && upperKey !== 'NEUTRAL') {
      try {
        const fetched = await this.syncController.loadClipAsync(nfcKey, { version: activeVer });
        if (fetched) {
          clip = fetched;
          this.clips[rawKey] = clip;
          this.clips[nfcKey] = clip;
          this.clips[upperKey] = clip;
        }
      } catch (e) {
        // Silencioso si no existe en catálogo directo
      }
    }

    return clip || this.clips.NEUTRAL;
  }

  async prepareSelectedClip() {
    const rawKey = this.selectedClipId || 'NEUTRAL';
    const clip = await this._resolveClipForSelection(rawKey);
    if (this.player) {
      this.player.loadClip(clip);
    }

    if (this.activeGlossHud && clip) {
      this.activeGlossHud.textContent = clip.gloss || '';
    }

    const duration = this.player ? this.player.getDuration() : ((clip && clip.durationMs ? clip.durationMs / 1000 : 0));
    this.updateTimeDisplay(0, duration);
    if (this.progressBarFill) {
      this.progressBarFill.style.width = '0%';
    }
    return clip;
  }

  async playCurrentSelection() {
    this.hideError();
    if (this.player) this.player.externalPoseControl = false;
    if (typeof window !== 'undefined' && window.studioAvatarBridge) {
      window.studioAvatarBridge.isManualPreviewActive = true;
    }
    const rawKey = this.selectedClipId || 'NEUTRAL';
    const clip = await this._resolveClipForSelection(rawKey);
    if (this.activeGlossHud && clip) {
      this.activeGlossHud.textContent = clip.gloss;
    }
    if (this.player && clip) {
      this.player.play(clip);
    }
  }

  pause() {
    if (this.sequencer.sequence.length > 0) {
      this.sequencer.pause();
    } else {
      this.player.pause();
    }
  }

  reset() {
    if (this.player) this.player.externalPoseControl = false;
    if (this.sequencer.sequence.length > 0) {
      this.sequencer.cancel();
    }
    this.player.reset();
    this.prepareSelectedClip();
    this.updateStatusDisplay('Inactivo');
  }

  setSpeed(rate) {
    this.player.setSpeed(rate);
    this.sequencer.setSpeed(rate);
  }

  /**
   * Cambia la versión activa del catálogo de señas VRM ('2.7' estandarizado, '2.6' directo corregido, '2.5' original)
   * y recarga la seña actual para comparación inmediata.
   * @param {string} version
   */
  async setAnimationVersion(version) {
    const ver = (version === '2.5' || version === '2.6') ? version : '2.7';
    this.preferredVersion = ver;
    if (this.selectVersion && this.selectVersion.value !== ver) {
      this.selectVersion.value = ver;
    }
    if (this.syncController && typeof this.syncController.setPreferredVersion === 'function') {
      this.syncController.setPreferredVersion(ver);
    }
    if (this.clipLoaders) {
      for (const [k, fn] of Object.entries(this.clipLoaders)) {
        this.clips[k] = fn;
      }
    }
    const noticeEl = this.container ? this.container.querySelector('#avatar-unvalidated-notice') : null;
    if (noticeEl) {
      noticeEl.textContent = ver === '2.7' ? 'CATÁLOGO v2.7 ESTANDARIZADO' : (ver === '2.6' ? 'CATÁLOGO v2.6 DIRECTO 1:1' : 'CATÁLOGO v2.5 ORIGINAL');
    }
    await this.prepareSelectedClip();
    if (typeof window !== 'undefined' && window.studioAvatarBridge) {
      if (typeof window.studioAvatarBridge.clearClipCache === 'function') {
        window.studioAvatarBridge.clearClipCache(ver);
      } else {
        window.studioAvatarBridge.clipMap?.clear();
        window.studioAvatarBridge.currentGlossKey = null;
      }
      if (window.appState?.state?.project) {
        await window.studioAvatarBridge.preloadProjectSigns(window.appState.state.project);
        const currentTime = window.appState.state.playback?.currentTime || 0;
        window.studioAvatarBridge.onTimeUpdate(currentTime);
      }
    }
    return ver;
  }

  playDemoSequence() {
    this.hideError();
    if (this.player) this.player.externalPoseControl = false;
    if (typeof window !== 'undefined' && window.studioAvatarBridge) {
      window.studioAvatarBridge.isManualPreviewActive = true;
    }
    this.sequencer.playSequence([
      this.clips.NEUTRAL,
      this.clips.SALUDAR_DEMO,
      this.clips.NEGACION_DEMO,
      this.clips.NEUTRAL
    ]);
  }

  async playWeekSequence() { return playAvatarWeekSequence(this); }
  playAllTestsSequence() { playAvatarAllTestsSequence(this); }

  onTabActivated() {
    if (!this.engine) return;
    this.engine.onResize();
    if (!this.engine.isRunning) this.engine.start();
  }

  updateTimeDisplay(curr, total) {
    if (this.timeCurrentEl) this.timeCurrentEl.textContent = `${curr.toFixed(2)}s`;
    if (this.timeTotalEl) this.timeTotalEl.textContent = `${total.toFixed(2)}s`;
  }

  updateStatusDisplay(status) {
    if (!this.statusBadge) return;
    this.statusBadge.textContent = status;
    this.statusBadge.setAttribute('data-state', status.toLowerCase());
  }

  showLoading(show, text = 'Cargando...') {
    if (!this.loadingIndicator) return;
    this.loadingIndicator.style.display = show ? 'flex' : 'none';
    const textEl = this.container.querySelector('#avatar-loading-text');
    if (textEl) textEl.textContent = text;
  }

  showError(msg) {
    if (!this.errorBanner) return;
    this.errorBanner.style.display = 'flex';
    if (this.errorMessageEl) this.errorMessageEl.textContent = msg;
  }

  hideError() {
    if (this.errorBanner) this.errorBanner.style.display = 'none';
  }

  setCameraPreset(preset) {
    if (!this.engine) return;
    this.engine.setCameraPreset(preset);
    this.syncPresetButtons(preset);
  }

  syncPresetButtons(preset) {
    syncAvatarPresetButtons(this, preset);
  }

  async playGloss(glossName, options = {}) {
    if (!glossName) {
      this.reset();
      return false;
    }
    if (this.player) this.player.externalPoseControl = false;

    const clean = glossName.trim();
    const isSingleLetterHyphenated = clean.includes('-') && clean.split('-').filter(Boolean).every(p => p.trim().length === 1);
    const isFingerspelling = Boolean(options.isFingerspelling || isSingleLetterHyphenated || options.gloss_type === 'DACTILOLOGÍA');

    if (isFingerspelling) {
      if (this.activeGlossHud) this.activeGlossHud.textContent = clean;
      this.lastPlayedResolutionMeta = {
        found: false, matchType: 'fingerspelling', needsReview: false,
        warning: null, resolvedGloss: clean, isFingerspelling: true
      };
      if (this.clips && this.clips.NEUTRAL) {
        this.player?.play(this.clips.NEUTRAL, { coarticulate: true, returnToNeutralOnEnd: false });
      } else {
        this.player?.reset();
      }
      return true;
    }

    if (this.activeGlossHud) this.activeGlossHud.textContent = clean;

    let clip = null;
    const reqVersion = options.version || this.preferredVersion || '2.7';
    if (this.syncController) {
      clip = await this.syncController.loadClipAsync(clean, { version: reqVersion });
      const resMeta = typeof this.syncController.getResolutionMeta === 'function'
        ? this.syncController.getResolutionMeta(clean, reqVersion)
        : (typeof this.syncController.getResolutionMetadata === 'function' ? this.syncController.getResolutionMetadata(clean, reqVersion) : null);
      if (resMeta) {
        this.lastPlayedResolutionMeta = resMeta;
        if (resMeta.isFingerspelling) {
          if (this.clips && this.clips.NEUTRAL) {
            this.player?.play(this.clips.NEUTRAL, { coarticulate: true, returnToNeutralOnEnd: false });
          } else {
            this.player?.reset();
          }
          return true;
        }
      }
    }

    if (!clip && this.clips) {
      clip = this.clips[clean.toUpperCase()] || this.clips[clean];
      if (typeof clip === 'function') {
        try {
          clip = await clip();
        } catch {
          clip = null;
        }
      }
    }

    if (this.activeGlossHud) this.activeGlossHud.textContent = clean;
    if (clip && this.player) {
      let targetSpeed = 1.0;
      if (typeof options.slotDurationSec === 'number' && options.slotDurationSec > 0 && clip.durationMs > 0) {
        const clipSec = clip.durationMs / 1000.0;
        const fitRatio = clipSec / Math.max(0.24, options.slotDurationSec);
        const baseRate = (typeof options.basePlaybackRate === 'number' && options.basePlaybackRate > 0)
          ? options.basePlaybackRate
          : 1.0;
        targetSpeed = Math.max(0.70, Math.min(1.6, fitRatio)) * baseRate;
      } else if (typeof options.speed === 'number' && options.speed > 0) {
        targetSpeed = options.speed;
      } else if (clip.metadata && typeof clip.metadata.recommendedSpeed === 'number') {
        targetSpeed = Math.min(1.6, clip.metadata.recommendedSpeed);
      }
      this.player.setSpeed(targetSpeed);
      this.player.play(clip, {
        coarticulate: options.coarticulate !== undefined ? options.coarticulate : true,
        blendDuration: options.coarticulationDurationSec || options.blendDuration || 0.14,
        returnToNeutralOnEnd: options.returnToNeutralOnEnd !== undefined ? options.returnToNeutralOnEnd : false,
        speed: targetSpeed
      });
      return true;
    } else {
      if (this.clips && this.clips.NEUTRAL) {
        this.player?.play(this.clips.NEUTRAL, { coarticulate: true, returnToNeutralOnEnd: false });
      }
      return false;
    }
  }

  stepDeterministic(dt = 1 / 30) {
    if (this.sequencer) {
      this.sequencer.update(dt);
    } else if (this.player) {
      this.player.update(dt);
    }
    if (this.engine && typeof this.engine.stepDeterministic === 'function') {
      this.engine.stepDeterministic(dt);
    }
  }

  stop() {
    this.reset();
  }

  resume() {
    if (this.sequencer && this.sequencer.sequence && this.sequencer.sequence.length > 0) {
      this.sequencer.resume();
    } else if (this.player && typeof this.player.resume === 'function') {
      this.player.resume();
    }
  }

  seek(timeSec) {
    if (this.player && typeof this.player.seek === 'function') {
      this.player.seek(timeSec);
    }
  }

  setClearColor(color) {
    if (this.engine) {
      this.engine.setClearColor(color);
    }
  }

  captureFrame() {
    return this.engine ? this.engine.captureFrame() : null;
  }

  rotateCamera(deltaAzimuthDeg, deltaPolarDeg = 0) {
    if (this.engine) this.engine.rotateCamera(deltaAzimuthDeg, deltaPolarDeg);
  }

  panCamera(deltaX, deltaY) {
    if (this.engine) this.engine.panCamera(deltaX, deltaY);
  }

  dollyCamera(deltaZoom) {
    if (this.engine) this.engine.dollyCamera(deltaZoom);
  }

  resetCamera() {
    if (this.engine) {
      this.engine.resetCamera();
      this.syncPresetButtons('medium');
    }
  }

  testExpression(markerType) {
    if (!this.nonManual) return;
    this.nonManual.applyMarker(markerType, 1.0);
    setTimeout(() => {
      this.nonManual.applyMarker(markerType, 0.0);
    }, 1500);
  }

  toggleModelSource() {
    if (this.isVRMActive) {
      this.activateTechnicalRig();
    } else {
      this.loadInitialAvatar();
    }
  }

  async exportCurrentClip() {
    return exportAvatarCurrentClip(this);
  }

  convertHamerAnimationToSignClip(data, defaultName = 'SEÑA_LSEC') {
    return convertDirectAnimationToSignClip(data, defaultName);
  }

  async importCustomClip(file) {
    if (!file) return null;

    try {
      let customClip;
      const fileName = (file && typeof file === 'object' && file.name) ? file.name : 'custom_clip.json';

      if (typeof file === 'string') {
        try {
          customClip = JSON.parse(file);
        } catch (jsonErr) {
          throw new Error('El archivo no contiene un formato JSON válido.');
        }
      } else if (file && typeof file.text === 'function') {
        const text = await file.text();
        try {
          customClip = JSON.parse(text);
        } catch (jsonErr) {
          throw new Error('El archivo no contiene un formato JSON válido.');
        }
      } else if (file && typeof file === 'object') {
        customClip = JSON.parse(JSON.stringify(file));
      } else {
        throw new Error('El archivo o dato proporcionado no es válido.');
      }

      if (customClip && !customClip.boneTracks && (Array.isArray(customClip.frames) || customClip.extractedTracks)) {
        console.info('[AvatarPanelController] Detectado formato animation.json de HaMeR Pipeline. Adaptando a SignClip...');
        customClip = this.convertHamerAnimationToSignClip(customClip, fileName.replace(/\.[^/.]+$/, ''));
      }

      if (customClip && typeof customClip === 'object') {
        if (!customClip.clipId && customClip.gloss) {
          customClip.clipId = customClip.gloss.toLowerCase().replace(/[^a-z0-9_-]/gi, '_');
        } else if (!customClip.clipId) {
          customClip.clipId = `CUSTOM_${Date.now()}`;
        }
        if (!customClip.gloss && customClip.clipId) {
          customClip.gloss = customClip.clipId.toUpperCase();
        } else if (!customClip.gloss) {
          customClip.gloss = 'PERSONALIZADA';
        }
        if (typeof customClip.durationMs !== 'number' || customClip.durationMs <= 0) {
          if (Array.isArray(customClip.boneTracks) && customClip.boneTracks.length > 0) {
            let maxT = 0;
            customClip.boneTracks.forEach(tr => {
              if (Array.isArray(tr.times) && tr.times.length > 0) {
                const tLast = tr.times[tr.times.length - 1];
                if (typeof tLast === 'number' && tLast > maxT) maxT = tLast;
              }
            });
            if (maxT > 0) {
              customClip.durationMs = Math.round((maxT + 0.15) * 1000);
            }
          }
        }
      }

      const validation = validateSignClip(customClip);
      if (!validation.valid) {
        const errorList = validation.errors.join('\n- ');
        throw new Error(`Estructura de seña incompatible:\n- ${errorList}`);
      }

      const clipId = customClip.clipId || `CUSTOM_${Date.now()}`;
      const gloss = customClip.gloss || 'PERSONALIZADA';
      const nfcGloss = String(gloss).normalize('NFC').trim();
      customClip.metadata = {
        ...(customClip.metadata || {}),
        isCustomImport: true
      };

      this.clips[clipId] = customClip;
      this.clips[gloss] = customClip;
      this.clips[nfcGloss] = customClip;
      this.clips[nfcGloss.toUpperCase()] = customClip;
      defaultAnimationCache.setClip(clipId, customClip);
      defaultAnimationCache.setClip(nfcGloss, customClip);
      defaultAnimationCache.setClip(nfcGloss.toUpperCase(), customClip);

      let customCategory = this.categories.find(c => c.groupName.includes('Señas Corregidas / Importadas'));
      if (!customCategory) {
        customCategory = {
          groupName: '✨ Señas Corregidas / Importadas',
          clips: []
        };
        this.categories.unshift(customCategory);
      }

      const existingClipIdx = customCategory.clips.findIndex(c => c.id === clipId);
      const clipEntry = {
        id: clipId,
        label: `✨ ${nfcGloss} (Corregida / Importada)`
      };

      if (existingClipIdx >= 0) {
        customCategory.clips[existingClipIdx] = clipEntry;
      } else {
        customCategory.clips.unshift(clipEntry);
      }

      this.renderClipOptions();
      let resolvedSelectVal = clipId;
      if (this.selectClip && this.selectClip.options) {
        const opts = Array.from(this.selectClip.options);
        const matchOpt = opts.find(opt => {
          const v = String(opt.value || '');
          const vNfc = v.normalize('NFC').trim();
          return v === clipId || v === gloss || vNfc === nfcGloss;
        });
        if (matchOpt) {
          resolvedSelectVal = matchOpt.value;
        }
        this.selectClip.value = resolvedSelectVal;
      }
      this.selectedClipId = resolvedSelectVal;
      this.clips[resolvedSelectVal] = customClip;

      await this.prepareSelectedClip();
      if (this.player) {
        this.player.play(customClip);
      }

      console.info(`[AvatarPanelController] Seña personalizada "${nfcGloss}" importada y cargada con éxito.`);
      return customClip;
    } catch (err) {
      console.error('[AvatarPanelController] Error al importar seña:', err);
      if (typeof alert === 'function') {
        alert('Error al importar la seña: ' + err.message);
      }
      return null;
    }
  }

  dispose() {
    if (this.engine) this.engine.dispose();
    if (this.technicalRig) this.technicalRig.dispose();
    if (this.vrmLoader) this.vrmLoader.unloadCurrentVRM();
  }
}
