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

import { AvatarEngine } from './avatar-engine.js';
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

    // Catálogo de clips técnicos precargados
    this.clips = getAllTechnicalClips();
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
    this.loadInitialAvatar();
  }

  buildDOM() {
    if (!this.container) return;

    // Generar opciones categorizadas para el selector
    const optionsHtml = this.categories.map((group) => {
      const options = group.clips.map((c) => {
        const isSelected = c.id === this.selectedClipId ? 'selected' : '';
        return `<option value="${c.id}" ${isSelected}>${c.label}</option>`;
      }).join('\n');
      return `<optgroup label="${group.groupName}">\n${options}\n</optgroup>`;
    }).join('\n');

    this.container.innerHTML = `
      <!-- Cabecera del Panel del Avatar -->
      <div class="avatar-panel-header">
        <div class="avatar-title-cluster">
          <div class="avatar-icon-badge" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2zM7.5 13A1.5 1.5 0 0 0 6 14.5 1.5 1.5 0 0 0 7.5 16 1.5 1.5 0 0 0 9 14.5 1.5 1.5 0 0 0 7.5 13zm9 0a1.5 1.5 0 0 0-1.5 1.5 1.5 1.5 0 0 0 1.5 1.5 1.5 1.5 0 0 0 1.5-1.5 1.5 1.5 0 0 0-1.5-1.5z"/>
            </svg>
          </div>
          <div>
            <h3 class="avatar-panel-title">Avatar 3D (LSEC)</h3>
            <span class="avatar-model-pill" id="avatar-model-source-info">Rig Técnico Activo</span>
          </div>
        </div>

        <div class="avatar-header-badges">
          <span class="unvalidated-warning-badge" id="avatar-unvalidated-notice" title="Las animaciones actuales son demostraciones técnicas no validadas lingüísticamente por la comunidad sorda">
            DEMO NO VALIDADA
          </span>
          <span class="avatar-status-badge" id="avatar-playback-status-badge">Inactivo</span>
        </div>
      </div>

      <!-- Viewport 3D WebGL con HUD reactivo -->
      <div class="avatar-viewport-container" id="avatar-viewport-wrap">
        <canvas id="avatar-webgl-canvas" class="avatar-canvas"></canvas>

        <!-- Indicador de Carga -->
        <div class="avatar-overlay-loading" id="avatar-loading-indicator" style="display:none;">
          <div class="avatar-spinner"></div>
          <span id="avatar-loading-text">Cargando modelo...</span>
        </div>

        <!-- Banner de Error / Información -->
        <div class="avatar-overlay-error" id="avatar-error-banner" style="display:none;">
          <div class="avatar-error-content">
            <span class="avatar-error-icon">⚠️</span>
            <span class="avatar-error-msg" id="avatar-error-message">Error de inicialización.</span>
            <button class="btn btn-secondary btn-sm" id="btn-avatar-error-retry">Reintentar</button>
          </div>
        </div>

        <!-- HUD superior con Glosa Activa, Rendimiento y Tiempo -->
        <div class="avatar-hud-top" id="avatar-hud-bar">
          <div class="avatar-hud-gloss">
            <span class="avatar-hud-label">PRUEBA:</span>
            <span class="avatar-hud-value" id="avatar-active-gloss-hud">—</span>
          </div>
          <div class="avatar-hud-perf">
            <span class="avatar-perf-badge" id="avatar-hud-perf-badge" title="Rendimiento en tiempo real (FPS | Heap)">60 FPS</span>
          </div>
          <div class="avatar-hud-time">
            <span id="avatar-hud-time-current">0.00s</span>
            <span style="opacity:0.4;">/</span>
            <span id="avatar-hud-time-total">0.00s</span>
          </div>
        </div>

        <!-- Barra de progreso temporal discreta -->
        <div class="avatar-viewport-progress-track">
          <div class="avatar-viewport-progress-fill" id="avatar-clip-progress-fill"></div>
        </div>

        <!-- Botón flotante para recentrar cámara -->
        <button class="btn-avatar-hud-action" id="btn-avatar-reset-camera" title="Recentrar cámara frontal">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
        </button>

        <!-- DOCK FLOTANTE DE CONTROLES DE CÁMARA (Girar, Mover, Deslizar) -->
        <div class="avatar-cam-floating-dock" id="avatar-cam-dock" aria-label="Controles de Cámara 3D">
          <div class="avatar-cam-dock-header">
            <span class="avatar-cam-dock-title">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
              Controles 3D
            </span>
            <button class="avatar-cam-dock-toggle" id="btn-cam-dock-toggle" title="Minimizar / Expandir panel de cámara">▾</button>
          </div>
          
          <div class="avatar-cam-dock-body" id="avatar-cam-dock-body">
            <!-- Girar (Órbita 360°) -->
            <div class="avatar-cam-tool-section">
              <div class="avatar-cam-section-label">Girar (Órbita)</div>
              <div class="avatar-cam-dpad-row">
                <button class="avatar-cam-btn" id="btn-cam-rot-left" title="Girar a la izquierda">↺ Izq</button>
                <button class="avatar-cam-btn" id="btn-cam-rot-up" title="Inclinar arriba">▲ Arr</button>
                <button class="avatar-cam-btn" id="btn-cam-rot-down" title="Inclinar abajo">▼ Aba</button>
                <button class="avatar-cam-btn" id="btn-cam-rot-right" title="Girar a la derecha">Der ↻</button>
              </div>
            </div>

            <!-- Mover (Desplazamiento / Pan) -->
            <div class="avatar-cam-tool-section">
              <div class="avatar-cam-section-label">Mover (Desplazamiento)</div>
              <div class="avatar-cam-grid-dpad">
                <button class="avatar-cam-btn avatar-cam-btn-up" id="btn-cam-pan-up" title="Mover hacia arriba">▲</button>
                <div class="avatar-cam-dpad-mid">
                  <button class="avatar-cam-btn" id="btn-cam-pan-left" title="Mover a la izquierda">◄</button>
                  <button class="avatar-cam-btn avatar-cam-btn-center" id="btn-cam-pan-center" title="Recentrar vista">●</button>
                  <button class="avatar-cam-btn" id="btn-cam-pan-right" title="Mover a la derecha">►</button>
                </div>
                <button class="avatar-cam-btn avatar-cam-btn-down" id="btn-cam-pan-down" title="Mover hacia abajo">▼</button>
              </div>
            </div>

            <!-- Deslizar (Dolly / Zoom) -->
            <div class="avatar-cam-tool-section">
              <div class="avatar-cam-section-label">Deslizar (Zoom)</div>
              <div class="avatar-cam-dpad-row">
                <button class="avatar-cam-btn" id="btn-cam-zoom-in" title="Acercar cámara (Dolly In)">
                  <span>＋ Acercar</span>
                </button>
                <button class="avatar-cam-btn" id="btn-cam-zoom-out" title="Alejar cámara (Dolly Out)">
                  <span>－ Alejar</span>
                </button>
              </div>
            </div>

            <!-- Hint Badge -->
            <div class="avatar-cam-hint-badge">
              <span class="avatar-cam-hint-icon">💡</span>
              <span>Arrastrar: Girar<br>Clic Der / Shift: Mover<br>Rueda: Deslizar Zoom</span>
            </div>
          </div>
        </div>

        <!-- Indicador flotante en la base del visor -->
        <div class="avatar-viewport-cam-hint" id="avatar-viewport-cam-hint">
          <span>🖱️ Arrastrar: Girar</span>
          <span>•</span>
          <span>Clic Der: Mover</span>
          <span>•</span>
          <span>Rueda: Deslizar</span>
        </div>
      </div>

      <!-- Barra de Controles de Reproducción y Secuenciación -->
      <div class="avatar-controls-panel">
        
        <!-- Fila 1: Selección de Clip / Prueba y Velocidad -->
        <div class="avatar-controls-row">
          <div class="avatar-control-group" style="flex:1;">
            <label for="select-avatar-clip" class="avatar-control-label">Prueba / Clip:</label>
            <select id="select-avatar-clip" class="avatar-select">
              ${optionsHtml}
            </select>
          </div>

          <div class="avatar-control-group">
            <label for="select-avatar-speed" class="avatar-control-label">Velocidad:</label>
            <select id="select-avatar-speed" class="avatar-select" style="min-width:70px;">
              <option value="0.25">0.25x</option>
              <option value="0.5">0.5x</option>
              <option value="0.75">0.75x</option>
              <option value="1.0" selected>1.0x</option>
              <option value="1.25">1.25x</option>
              <option value="1.5">1.5x</option>
              <option value="2.0">2.0x</option>
            </select>
          </div>
        </div>

        <!-- Fila 2: Botones de Acción Individual y Secuenciación -->
        <div class="avatar-controls-row avatar-buttons-row">
          <div style="display:flex; gap:6px;">
            <button class="btn btn-primary btn-sm" id="btn-avatar-play" title="Reproducir prueba seleccionada (Espacio)">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
              <span>Reproducir</span>
            </button>
            <button class="btn btn-secondary btn-sm" id="btn-avatar-pause" title="Pausar animación">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
              <span>Pausar</span>
            </button>
            <button class="btn btn-secondary btn-sm" id="btn-avatar-reset" title="Reiniciar y restaurar postura neutral">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg>
              <span>Reiniciar</span>
            </button>
          </div>

          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button class="btn btn-action-step btn-sm" id="btn-avatar-play-sequence" title="Reproducir secuencia de demostración básica">
              <span>▶ Secuencia Básica</span>
            </button>
            <button class="btn btn-secondary btn-sm" id="btn-avatar-play-all-tests" title="Ejecutar batería continua de todas las pruebas técnicas (22 clips)">
              <span>⚡ Batería Pruebas (22)</span>
            </button>
          </div>
        </div>

        <!-- Barra de Presets y Herramientas Rápidas de Cámara -->
        <div class="avatar-cam-presets-bar">
          <div class="avatar-cam-presets-group">
            <span style="font-size:0.72rem; color:var(--text-muted); font-weight:600; margin-right:4px;">Cámara:</span>
            <button class="avatar-cam-preset-btn active" id="btn-cam-medium" title="Vista plano medio">Plano Medio</button>
            <button class="avatar-cam-preset-btn" id="btn-cam-full" title="Vista de cuerpo entero">Cuerpo</button>
            <button class="avatar-cam-preset-btn" id="btn-cam-face" title="Vista rostro y mirada">Rostro</button>
            <button class="avatar-cam-preset-btn" id="btn-cam-hands" title="Vista manos y señas">Manos / Sien</button>

            <div class="avatar-cam-tools-compact">
              <button class="avatar-cam-icon-btn" id="btn-quick-rot-left" title="Girar izquierda ↺">↺</button>
              <button class="avatar-cam-icon-btn" id="btn-quick-rot-right" title="Girar derecha ↻">↻</button>
              <button class="avatar-cam-icon-btn" id="btn-quick-zoom-in" title="Acercar ＋">＋</button>
              <button class="avatar-cam-icon-btn" id="btn-quick-zoom-out" title="Alejar －">－</button>
              <button class="avatar-cam-icon-btn" id="btn-quick-cam-dock-toggle" title="Dock de controles 3D">🎮</button>
            </div>
          </div>
        </div>

        <!-- Fila 3: Carga de Archivo VRM Local -->
        <div class="avatar-vrm-load-row">
          <input type="file" id="avatar-vrm-file-input" accept=".vrm,.glb" style="display:none;">
          <button class="btn btn-secondary btn-sm" id="btn-avatar-load-vrm" style="width:100%; justify-content:center;">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16h6v-6h4l-7-7-7 7h4v6zm-4 2h14v2H5v-2z"/></svg>
            <span>Cargar Avatar VRM 1.0 (.vrm local)</span>
          </button>
        </div>

      </div>

      <!-- Tarjeta Informativa de Trazabilidad y Descargo -->
      <div class="avatar-disclaimer-card">
        <div class="avatar-disclaimer-header">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="color:var(--status-review);"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
          <strong>Verificación Técnica — No son señas LSEC validadas</strong>
        </div>
        <p class="avatar-disclaimer-text">
          Las poses y clips técnicos ejecutan pruebas biomecánicas de falanges, orientaciones, componentes 
          no manuales y rendimiento. No constituyen realizaciones lingüísticas validadas de LSEC. 
          Requieren validación participativa con personas sordas señantes nativas.
        </p>
      </div>
    `;
  }

  bindDOM() {
    if (!this.container) return;
    const findEl = (sel) => (this.container ? this.container.querySelector(sel) : null) || document.querySelector(sel);

    this.canvas = findEl('#avatar-webgl-canvas');
    this.statusBadge = findEl('#avatar-playback-status-badge');
    this.modelSourcePill = findEl('#avatar-model-source-info');
    this.activeGlossHud = findEl('#avatar-active-gloss-hud');
    this.hudPerfBadge = findEl('#avatar-hud-perf-badge');
    this.timeCurrentEl = findEl('#avatar-hud-time-current');
    this.timeTotalEl = findEl('#avatar-hud-time-total');
    this.progressBarFill = findEl('#avatar-clip-progress-fill');
    this.loadingIndicator = findEl('#avatar-loading-indicator');
    this.errorBanner = findEl('#avatar-error-banner');
    this.errorMessageEl = findEl('#avatar-error-message');

    // Botones
    this.btnPlay = findEl('#btn-avatar-play');
    this.btnPause = findEl('#btn-avatar-pause');
    this.btnReset = findEl('#btn-avatar-reset');
    this.btnPlaySeq = findEl('#btn-avatar-play-sequence');
    this.btnPlayAllTests = findEl('#btn-avatar-play-all-tests');
    this.btnLoadVrm = findEl('#btn-avatar-load-vrm');
    this.btnResetCam = findEl('#btn-avatar-reset-camera');
    this.btnRetry = findEl('#btn-avatar-error-retry');
    this.fileInputVrm = findEl('#avatar-vrm-file-input');

    // Selectores
    this.selectClip = findEl('#select-avatar-clip');
    this.selectSpeed = findEl('#select-avatar-speed');

    // Poblar selector de clips si no tiene opciones previas
    if (this.selectClip && this.selectClip.children.length === 0) {
      const optionsHtml = this.categories.map((group) => {
        const options = group.clips.map((c) => {
          const isSelected = c.id === this.selectedClipId ? 'selected' : '';
          return `<option value="${c.id}" ${isSelected}>${c.label}</option>`;
        }).join('\n');
        return `<optgroup label="${group.groupName}">\n${options}\n</optgroup>`;
      }).join('\n');
      this.selectClip.innerHTML = optionsHtml;
    }

    // Listeners principales
    if (this.btnPlay) this.btnPlay.addEventListener('click', () => this.playCurrentSelection());
    if (this.btnPause) this.btnPause.addEventListener('click', () => this.pause());
    if (this.btnReset) this.btnReset.addEventListener('click', () => this.reset());
    if (this.btnPlaySeq) this.btnPlaySeq.addEventListener('click', () => this.playDemoSequence());
    if (this.btnPlayAllTests) this.btnPlayAllTests.addEventListener('click', () => this.playAllTestsSequence());
    if (this.btnResetCam) this.btnResetCam.addEventListener('click', () => this.resetCamera());

    // Helper para acciones continuas al mantener presionado un botón
    const bindContinuousAction = (btn, actionFn) => {
      if (!btn) return;
      let timer = null;
      const startAction = (e) => {
        if (e) e.preventDefault();
        actionFn();
        if (timer) clearInterval(timer);
        timer = setInterval(() => {
          actionFn();
        }, 70);
      };
      const stopAction = () => {
        if (timer) {
          clearInterval(timer);
          timer = null;
        }
      };

      btn.addEventListener('mousedown', startAction);
      btn.addEventListener('mouseup', stopAction);
      btn.addEventListener('mouseleave', stopAction);
      btn.addEventListener('touchstart', startAction, { passive: false });
      btn.addEventListener('touchend', stopAction);
      btn.addEventListener('touchcancel', stopAction);
    };

    // Controles de Rotación / Giro (Órbita 360°)
    bindContinuousAction(findEl('#btn-cam-rot-left'), () => this.rotateCamera(-4, 0));
    bindContinuousAction(findEl('#btn-cam-rot-right'), () => this.rotateCamera(4, 0));
    bindContinuousAction(findEl('#btn-cam-rot-up'), () => this.rotateCamera(0, -4));
    bindContinuousAction(findEl('#btn-cam-rot-down'), () => this.rotateCamera(0, 4));
    bindContinuousAction(findEl('#btn-quick-rot-left'), () => this.rotateCamera(-6, 0));
    bindContinuousAction(findEl('#btn-quick-rot-right'), () => this.rotateCamera(6, 0));

    // Controles de Traslación / Desplazamiento (Pan)
    bindContinuousAction(findEl('#btn-cam-pan-left'), () => this.panCamera(-1, 0));
    bindContinuousAction(findEl('#btn-cam-pan-right'), () => this.panCamera(1, 0));
    bindContinuousAction(findEl('#btn-cam-pan-up'), () => this.panCamera(0, 1));
    bindContinuousAction(findEl('#btn-cam-pan-down'), () => this.panCamera(0, -1));
    const btnPanCenter = findEl('#btn-cam-pan-center');
    if (btnPanCenter) btnPanCenter.addEventListener('click', () => this.resetCamera());

    // Controles de Deslizamiento / Zoom (Dolly)
    bindContinuousAction(findEl('#btn-cam-zoom-in'), () => this.dollyCamera(0.12));
    bindContinuousAction(findEl('#btn-cam-zoom-out'), () => this.dollyCamera(-0.12));
    bindContinuousAction(findEl('#btn-quick-zoom-in'), () => this.dollyCamera(0.15));
    bindContinuousAction(findEl('#btn-quick-zoom-out'), () => this.dollyCamera(-0.15));

    // Presets de Cámara
    const presetBtns = {
      medium: findEl('#btn-cam-medium'),
      full: findEl('#btn-cam-full'),
      face: findEl('#btn-cam-face'),
      hands: findEl('#btn-cam-hands')
    };

    Object.entries(presetBtns).forEach(([preset, btn]) => {
      if (!btn) return;
      btn.addEventListener('click', () => {
        this.setCameraPreset(preset);
      });
    });

    // Toggle de Dock Flotante de Cámara
    const dockBody = findEl('#avatar-cam-dock-body');
    const dockToggle = findEl('#btn-cam-dock-toggle');
    const quickDockToggle = findEl('#btn-quick-cam-dock-toggle');

    const toggleDock = () => {
      if (!dockBody) return;
      const isHidden = dockBody.style.display === 'none';
      dockBody.style.display = isHidden ? 'flex' : 'none';
      if (dockToggle) dockToggle.textContent = isHidden ? '▾' : '▸';
    };

    if (dockToggle) dockToggle.addEventListener('click', toggleDock);
    if (quickDockToggle) quickDockToggle.addEventListener('click', toggleDock);

    if (this.selectClip) {
      this.selectClip.addEventListener('change', (e) => {
        this.selectedClipId = e.target.value;
        this.prepareSelectedClip();
      });
    }

    if (this.selectSpeed) {
      this.selectSpeed.addEventListener('change', (e) => {
        const rate = parseFloat(e.target.value) || 1.0;
        this.setSpeed(rate);
      });
    }

    if (this.btnLoadVrm && this.fileInputVrm) {
      this.btnLoadVrm.addEventListener('click', () => {
        this.fileInputVrm.click();
      });

      this.fileInputVrm.addEventListener('change', (e) => {
        const file = e.target.files && e.target.files[0];
        if (file) {
          this.loadVRMFromFile(file);
        }
      });
    }

    if (this.btnRetry) {
      this.btnRetry.addEventListener('click', () => {
        this.hideError();
        this.loadInitialAvatar();
      });
    }
  }

  initSubsystems() {
    try {
      // 1. Motor Three.js
      this.engine = new AvatarEngine(this.canvas);

      // 2. Cargador VRM
      this.vrmLoader = new VRMLoaderService();

      // 3. Rig Técnico de Reserva
      this.technicalRig = new TechnicalRig();

      // 4. Reproductor
      this.player = new SignPlayer();

      // 5. Secuenciador
      this.sequencer = new SignSequencer(this.player);

      // 6. Sincronizador lingüístico
      this.syncController = new AvatarSyncController(this.sequencer);

      // 7. No manuales
      this.nonManual = new NonManualController();

      // Conectar loop de renderizado del motor con el secuenciador y perfilador de rendimiento
      this.engine.setUpdateCallback((delta) => {
        this.sequencer.update(delta);
        this.updateFPSMetrics();
      });

      // Callbacks de progreso y estado
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

      // Iniciar ciclo de renderizado
      this.engine.start();

      console.info('[AvatarPanelController] Subsistemas del avatar inicializados correctamente.');
    } catch (err) {
      console.error('[AvatarPanelController] Error al inicializar subsistemas:', err);
      this.showError('No se pudo inicializar WebGL o Three.js en este navegador.');
    }
  }

  initClipsCache() {
    for (const [id, clip] of Object.entries(this.clips)) {
      defaultAnimationCache.setClip(clip.clipId || `${id}_V1`, clip);
    }
  }

  updateFPSMetrics() {
    this.perfMetrics.frameCount++;
    const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
    const elapsed = now - this.perfMetrics.lastFpsTime;

    if (elapsed >= 500) {
      this.perfMetrics.fps = Math.round((this.perfMetrics.frameCount * 1000) / elapsed);
      this.perfMetrics.frameCount = 0;
      this.perfMetrics.lastFpsTime = now;

      if (typeof performance !== 'undefined' && performance.memory) {
        this.perfMetrics.usedMemoryMB = (performance.memory.usedJSHeapSize / (1024 * 1024)).toFixed(1);
      }

      this.updatePerfDisplay();
    }
  }

  updatePerfDisplay() {
    if (this.hudPerfBadge) {
      const memText = this.perfMetrics.usedMemoryMB > 0 ? ` | ${this.perfMetrics.usedMemoryMB} MB` : '';
      this.hudPerfBadge.textContent = `${this.perfMetrics.fps} FPS${memText}`;
      if (this.perfMetrics.fps >= 50) {
        this.hudPerfBadge.style.color = 'var(--action-primary)';
      } else if (this.perfMetrics.fps >= 30) {
        this.hudPerfBadge.style.color = 'var(--status-review)';
      } else {
        this.hudPerfBadge.style.color = 'var(--status-error)';
      }
    }
  }

  /**
   * Reporte estructurado de rendimiento para inspección y testing automatizado.
   */
  getPerformanceReport() {
    return {
      loadTimeMs: this.perfMetrics.loadTimeMs,
      fps: this.perfMetrics.fps,
      usedMemoryMB: this.perfMetrics.usedMemoryMB,
      isVRMActive: this.isVRMActive,
      modelSource: this.currentModelSource,
      consoleErrors: this.perfMetrics.consoleErrors,
      consoleWarnings: this.perfMetrics.consoleWarnings
    };
  }

  /**
   * Intenta cargar el avatar inicial:
   * 1. Verifica si existe el prototipo en /static/assets/lsec_avatar_prototype.vrm
   * 2. Si no existe, prueba /static/assets/avatar.vrm
   * 3. Si ninguno existe, activa el Rig Técnico de Reserva.
   */
  async loadInitialAvatar() {
    this.showLoading(true, 'Verificando avatar VRM...');

    const candidates = [
      '/static/assets/lsec_avatar_prototype.vrm',
      '/static/assets/avatar.vrm'
    ];

    for (const vrmUrl of candidates) {
      try {
        const check = await fetch(vrmUrl, { method: 'HEAD' });
        if (check.ok) {
          console.info(`[AvatarPanelController] Avatar VRM detectado en: ${vrmUrl}`);
          await this.loadVRMFromUrl(vrmUrl);
          return;
        }
      } catch (e) {
        // Continuar con el siguiente candidato
      }
    }

    console.info('[AvatarPanelController] Modelo VRM no detectado en las rutas estándar. Activando Rig Técnico de Reserva.');
    this.activateTechnicalRig();
    this.showLoading(false);
  }

  activateTechnicalRig() {
    this.isVRMActive = false;
    this.currentModelSource = 'TECHNICAL_RIG';

    this.engine.setModel(this.technicalRig, false);
    this.player.setModel(this.technicalRig, false);
    this.nonManual.setModel(this.technicalRig, false);

    if (this.modelSourcePill) {
      this.modelSourcePill.textContent = 'Rig Técnico (Reserva)';
      this.modelSourcePill.className = 'avatar-model-pill avatar-pill-rig';
    }

    this.prepareSelectedClip();
  }

  /**
   * Carga un modelo VRM provisto como archivo local (vía file input o drag&drop).
   * @param {File} file 
   */
  async loadVRMFromFile(file) {
    if (!file) return;
    this.showLoading(true, `Cargando ${file.name}...`);
    this.hideError();
    const t0 = performance.now();

    try {
      const vrm = await this.vrmLoader.loadVRM(file);
      this.perfMetrics.loadTimeMs = Math.round(performance.now() - t0);
      this.onVRMLoadSuccess(vrm, file.name);
    } catch (err) {
      console.error('[AvatarPanelController] Fallo al cargar VRM desde archivo:', err);
      this.showError(`Error al cargar avatar VRM (${file.name}). Se mantiene el Rig de reserva.`);
      this.activateTechnicalRig();
    } finally {
      this.showLoading(false);
    }
  }

  /**
   * Carga un modelo VRM desde una URL.
   * @param {string} url 
   */
  async loadVRMFromUrl(url) {
    this.showLoading(true, 'Descargando avatar VRM...');
    this.hideError();
    const t0 = performance.now();

    try {
      const vrm = await this.vrmLoader.loadVRM(url);
      this.perfMetrics.loadTimeMs = Math.round(performance.now() - t0);
      const fileName = url.split('/').pop() || 'avatar.vrm';
      this.onVRMLoadSuccess(vrm, fileName);
    } catch (err) {
      console.warn('[AvatarPanelController] No se pudo cargar avatar VRM desde URL. Activando rig de reserva.', err);
      this.activateTechnicalRig();
    } finally {
      this.showLoading(false);
    }
  }

  onVRMLoadSuccess(vrm, sourceName) {
    this.isVRMActive = true;
    this.currentModelSource = 'VRM_LOCAL';

    this.engine.setModel(vrm, true);
    this.player.setModel(vrm, true);
    this.nonManual.setModel(vrm, true);

    if (this.modelSourcePill) {
      this.modelSourcePill.textContent = `VRM 1.0 (${sourceName})`;
      this.modelSourcePill.className = 'avatar-model-pill avatar-pill-vrm';
    }

    this.prepareSelectedClip();
  }

  prepareSelectedClip() {
    const clip = this.clips[this.selectedClipId] || this.clips.NEUTRAL;
    this.player.loadClip(clip);

    if (this.activeGlossHud) {
      this.activeGlossHud.textContent = clip.gloss;
    }

    this.updateTimeDisplay(0, this.player.getDuration());
    if (this.progressBarFill) {
      this.progressBarFill.style.width = '0%';
    }
  }

  playCurrentSelection() {
    this.hideError();
    const clip = this.clips[this.selectedClipId] || this.clips.NEUTRAL;
    if (this.activeGlossHud) {
      this.activeGlossHud.textContent = clip.gloss;
    }
    this.player.play(clip);
  }

  pause() {
    if (this.sequencer.sequence.length > 0) {
      this.sequencer.pause();
    } else {
      this.player.pause();
    }
  }

  reset() {
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
   * Reproduce la secuencia demostrativa básica:
   * NEUTRAL -> SALUDAR_DEMO -> NEGACION_DEMO -> NEUTRAL
   */
  playDemoSequence() {
    this.hideError();
    const sequence = [
      this.clips.NEUTRAL,
      this.clips.SALUDAR_DEMO,
      this.clips.NEGACION_DEMO,
      this.clips.NEUTRAL
    ];

    this.sequencer.playSequence(sequence);
  }

  /**
   * Reproduce la batería continua completa de todas las pruebas técnicas.
   */
  playAllTestsSequence() {
    this.hideError();
    const sequence = [
      this.clips.NEUTRAL,
      this.clips.TEST_MANO_ABIERTA,
      this.clips.TEST_PUNO,
      this.clips.TEST_INDICE_EXTENDIDO,
      this.clips.TEST_DOS_DEDOS,
      this.clips.TEST_PINZA,
      this.clips.TEST_MANO_CURVA,
      this.clips.TEST_GARRA,
      this.clips.TEST_DEDOS_JUNTOS_SEPARADOS,
      this.clips.TEST_ORIENTACION_PALMA,
      this.clips.TEST_PRONACION_SUPINACION,
      this.clips.TEST_FLEXION_MUNICA_CODO,
      this.clips.TEST_CNM_HEAD_SHAKE,
      this.clips.TEST_CNM_HEAD_NOD,
      this.clips.TEST_CNM_HEAD_TILT,
      this.clips.TEST_CNM_MIRADA,
      this.clips.TEST_CNM_CEJAS,
      this.clips.TEST_CNM_PARPADEO,
      this.clips.TEST_CNM_BOCA,
      this.clips.TEST_SIMULTANEO_MANOS_CABEZA,
      this.clips.TEST_SIMULTANEO_MANOS_MIRADA,
      this.clips.TEST_SIMULTANEO_MANOS_EXPRESION,
      this.clips.TEST_SIMULTANEO_COMPLEJO_TOTAL,
      this.clips.NEUTRAL
    ].filter(Boolean);

    this.sequencer.playSequence(sequence);
  }

  /**
   * Notificación cuando el panel o pestaña "Avatar 3D" se hace visible.
   */
  onTabActivated() {
    if (this.engine) {
      this.engine.onResize();
      if (!this.engine.isRunning) {
        this.engine.start();
      }
    }
  }

  updateTimeDisplay(curr, total) {
    if (this.timeCurrentEl) this.timeCurrentEl.textContent = `${curr.toFixed(2)}s`;
    if (this.timeTotalEl) this.timeTotalEl.textContent = `${total.toFixed(2)}s`;
  }

  updateStatusDisplay(status) {
    if (this.statusBadge) {
      this.statusBadge.textContent = status;
      this.statusBadge.setAttribute('data-state', status.toLowerCase());
    }
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
    const findEl = (sel) => (this.container ? this.container.querySelector(sel) : null) || document.querySelector(sel);
    const presetMap = {
      medium: findEl('#btn-cam-medium'),
      full: findEl('#btn-cam-full'),
      face: findEl('#btn-cam-face'),
      hands: findEl('#btn-cam-hands')
    };
    Object.entries(presetMap).forEach(([k, btn]) => {
      if (btn) {
        if (k === preset) btn.classList.add('active');
        else btn.classList.remove('active');
      }
    });
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

  dispose() {
    if (this.engine) this.engine.dispose();
    if (this.technicalRig) this.technicalRig.dispose();
    if (this.vrmLoader) this.vrmLoader.unloadCurrentVRM();
  }
}
