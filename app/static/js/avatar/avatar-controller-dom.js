/**
 * LSEC Studio — Construcción y Enlace DOM del Panel del Avatar 3D
 *
 * Submódulo extraído de avatar-controller.js para cumplir SRP (< 800 líneas).
 */

export function renderAvatarClipOptions(ctrl) {
  if (!ctrl.selectClip) return;
  const optionsHtml = ctrl.categories.map((group) => {
    const options = group.clips.map((c) => {
      const isSelected = c.id === ctrl.selectedClipId ? 'selected' : '';
      return `<option value="${c.id}" ${isSelected}>${c.label}</option>`;
    }).join('\n');
    return `<optgroup label="${group.groupName}">\n${options}\n</optgroup>`;
  }).join('\n');
  ctrl.selectClip.innerHTML = optionsHtml;
}

export function buildAvatarPanelDOM(ctrl) {
  if (!ctrl.container) return;

  const optionsHtml = ctrl.categories.map((group) => {
    const options = group.clips.map((c) => {
      const isSelected = c.id === ctrl.selectedClipId ? 'selected' : '';
      return `<option value="${c.id}" ${isSelected}>${c.label}</option>`;
    }).join('\n');
    return `<optgroup label="${group.groupName}">\n${options}\n</optgroup>`;
  }).join('\n');

  ctrl.container.innerHTML = `
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
          <a href="/avatarconfig" class="btn btn-secondary btn-sm" id="btn-open-avatar-config-page" title="Abrir entorno dedicado de calibración (/avatarconfig)" style="text-decoration:none; font-size:0.65rem; padding:2px 6px; display:inline-flex; align-items:center; gap:3px;">
            <span>Calibración ↗</span>
          </a>
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
        <button class="btn-avatar-hud-action" id="btn-avatar-reset-camera" title="Recentrar cámara frontal" aria-label="Recentrar cámara frontal">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
        </button>

        <!-- DOCK FLOTANTE DE CONTROLES DE CÁMARA (Girar, Mover, Deslizar) -->
        <div class="avatar-cam-floating-dock dock-collapsed" id="avatar-cam-dock" aria-label="Controles de Cámara 3D">
          <div class="avatar-cam-dock-header">
            <span class="avatar-cam-dock-title">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
              Controles 3D
            </span>
            <button class="avatar-cam-dock-toggle" id="btn-cam-dock-toggle" title="Minimizar / Expandir panel de cámara" aria-label="Alternar panel de cámara 3D">▸</button>
          </div>
          
          <div class="avatar-cam-dock-body" id="avatar-cam-dock-body" style="display:none;">
            <div class="avatar-cam-tool-section">
              <div class="avatar-cam-section-label">Girar (Órbita)</div>
              <div class="avatar-cam-dpad-row">
                <button class="avatar-cam-btn" id="btn-cam-rot-left" title="Girar a la izquierda">↺ Izq</button>
                <button class="avatar-cam-btn" id="btn-cam-rot-up" title="Inclinar arriba">▲ Arr</button>
                <button class="avatar-cam-btn" id="btn-cam-rot-down" title="Inclinar abajo">▼ Aba</button>
                <button class="avatar-cam-btn" id="btn-cam-rot-right" title="Girar a la derecha">Der ↻</button>
              </div>
            </div>

            <div class="avatar-cam-tool-section">
              <div class="avatar-cam-section-label">Mover (Desplazamiento)</div>
              <div class="avatar-cam-grid-dpad">
                <button class="avatar-cam-btn avatar-cam-btn-up" id="btn-cam-pan-up" title="Mover hacia arriba" aria-label="Mover cámara arriba">▲</button>
                <div class="avatar-cam-dpad-mid">
                  <button class="avatar-cam-btn" id="btn-cam-pan-left" title="Mover a la izquierda" aria-label="Mover cámara izquierda">◄</button>
                  <button class="avatar-cam-btn avatar-cam-btn-center" id="btn-cam-pan-center" title="Recentrar vista" aria-label="Recentrar vista">●</button>
                  <button class="avatar-cam-btn" id="btn-cam-pan-right" title="Mover a la derecha" aria-label="Mover cámara derecha">►</button>
                </div>
                <button class="avatar-cam-btn avatar-cam-btn-down" id="btn-cam-pan-down" title="Mover hacia abajo" aria-label="Mover cámara abajo">▼</button>
              </div>
            </div>

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

            <div class="avatar-cam-hint-badge">
              <span class="avatar-cam-hint-icon">💡</span>
              <span>Arrastrar: Girar<br>Clic Der / Shift: Mover<br>Rueda: Deslizar Zoom</span>
            </div>
          </div>
        </div>

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
        <div class="avatar-controls-row">
          <div class="avatar-control-group" style="flex:1; min-width: 140px;">
            <label for="select-avatar-clip" class="avatar-control-label">Prueba / Clip:</label>
            <select id="select-avatar-clip" class="avatar-select" style="flex:1;">
              ${optionsHtml}
            </select>
          </div>

          <div class="avatar-control-group">
            <label for="select-avatar-version" class="avatar-control-label">Catálogo:</label>
            <select id="select-avatar-version" class="avatar-select" style="min-width:118px;" title="Versión de animaciones VRM LSEC (v2.7 Estandarizado, v2.6 Directo 1:1 Corregido, v2.5 Original)">
              <option value="2.7" selected>v2.7 Estandarizado</option>
              <option value="2.6">v2.6 Directo 1:1</option>
              <option value="2.5">v2.5 Original</option>
            </select>
          </div>

          <div class="avatar-control-group">
            <label for="select-avatar-speed" class="avatar-control-label">Velocidad:</label>
            <select id="select-avatar-speed" class="avatar-select" style="min-width:64px;">
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

        <div class="avatar-controls-row avatar-buttons-row">
          <div style="display:flex; gap:6px; flex-wrap:wrap;">
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
            <button class="btn btn-action-step btn-action-primary btn-sm" id="btn-avatar-play-sequence" title="Reproducir secuencia de demostración básica">
              <span>▶ Secuencia Básica</span>
            </button>
            <button class="btn btn-secondary btn-sm" id="btn-avatar-play-week" style="background:linear-gradient(135deg, #059669 0%, #047857 100%); border-color:#059669; color:#fff;" title="Reproducir secuencia completa de los 7 días de la semana (Lunes a Domingo)">
              <span>📅 7 Días Semana</span>
            </button>
            <button class="btn btn-secondary btn-sm" id="btn-avatar-play-all-tests" title="Ejecutar batería continua de todas las pruebas técnicas (22 clips)">
              <span>⚡ Batería Pruebas (22)</span>
            </button>
          </div>
        </div>

        <div class="avatar-cam-presets-bar">
          <div class="avatar-cam-presets-group">
            <span style="font-size:0.72rem; color:var(--text-muted); font-weight:600; margin-right:4px;">Cámara:</span>
            <button class="avatar-cam-preset-btn active" id="btn-cam-medium" title="Vista plano medio">Plano Medio</button>
            <button class="avatar-cam-preset-btn" id="btn-cam-full" title="Vista de cuerpo entero">Cuerpo</button>
            <button class="avatar-cam-preset-btn" id="btn-cam-face" title="Vista rostro y mirada">Rostro</button>
            <button class="avatar-cam-preset-btn" id="btn-cam-hands" title="Vista manos y señas">Manos / Sien</button>

            <div class="avatar-cam-tools-compact">
              <button class="avatar-cam-icon-btn" id="btn-quick-rot-left" title="Girar izquierda ↺" aria-label="Girar izquierda">↺</button>
              <button class="avatar-cam-icon-btn" id="btn-quick-rot-right" title="Girar derecha ↻" aria-label="Girar derecha">↻</button>
              <button class="avatar-cam-icon-btn" id="btn-quick-zoom-in" title="Acercar ＋" aria-label="Acercar cámara">＋</button>
              <button class="avatar-cam-icon-btn" id="btn-quick-zoom-out" title="Alejar －" aria-label="Alejar cámara">－</button>
              <button class="avatar-cam-icon-btn" id="btn-quick-cam-dock-toggle" title="Dock de controles 3D" aria-label="Alternar controles de cámara 3D">🎮</button>
            </div>
          </div>
        </div>

        <div class="avatar-vrm-load-row">
          <input type="file" id="avatar-vrm-file-input" accept=".vrm,.glb" style="display:none;" aria-label="Cargar modelo de avatar VRM o GLB">
          <button class="btn btn-secondary btn-sm" id="btn-avatar-load-vrm" style="width:100%; justify-content:center;">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16h6v-6h4l-7-7-7 7h4v6zm-4 2h14v2H5v-2z"/></svg>
            <span>Cargar Avatar VRM 1.0 (.vrm local)</span>
          </button>
        </div>

        <div class="avatar-clip-edit-row" style="display:flex; flex-direction:column; gap:6px; margin-top:8px; padding-top:8px; border-top:1px dashed var(--border-subtle);">
          <div style="font-size:0.75rem; font-weight:600; color:var(--text-secondary); display:flex; align-items:center; gap:5px;">
            <span>✏️ Edición Manual de Señas (Blender / JSON)</span>
          </div>
          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button class="btn btn-secondary btn-sm" id="btn-avatar-export-clip" style="flex:1; justify-content:center;" title="Exportar la seña actualmente seleccionada (ej. LUNES) como archivo JSON para referencia o edición">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
              <span>Exportar Seña</span>
            </button>
            <input type="file" id="avatar-clip-file-input" accept=".json" style="display:none;" aria-label="Cargar animación de seña corregida JSON">
            <button class="btn btn-primary btn-sm" id="btn-avatar-import-clip" style="flex:1; justify-content:center; background:linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%); border-color:#2563EB;" title="Cargar seña corregida o personalizada (.json) y visualizar en el avatar">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16h6v-6h4l-7-7-7 7h4v6zm-4 2h14v2H5v-2z"/></svg>
              <span>Cargar Seña Corregida</span>
            </button>
          </div>
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

export function bindAvatarPanelDOM(ctrl) {
  if (!ctrl.container) return;
  const findEl = (sel) => (ctrl.container ? ctrl.container.querySelector(sel) : null) || document.querySelector(sel);

  ctrl.canvas = findEl('#avatar-webgl-canvas');
  ctrl.statusBadge = findEl('#avatar-playback-status-badge');
  ctrl.modelSourcePill = findEl('#avatar-model-source-info');
  ctrl.activeGlossHud = findEl('#avatar-active-gloss-hud');
  ctrl.hudPerfBadge = findEl('#avatar-hud-perf-badge');
  ctrl.timeCurrentEl = findEl('#avatar-hud-time-current');
  ctrl.timeTotalEl = findEl('#avatar-hud-time-total');
  ctrl.progressBarFill = findEl('#avatar-clip-progress-fill');
  ctrl.loadingIndicator = findEl('#avatar-loading-indicator');
  ctrl.errorBanner = findEl('#avatar-error-banner');
  ctrl.errorMessageEl = findEl('#avatar-error-message');

  ctrl.btnPlay = findEl('#btn-avatar-play');
  ctrl.btnPause = findEl('#btn-avatar-pause');
  ctrl.btnReset = findEl('#btn-avatar-reset');
  ctrl.btnPlaySeq = findEl('#btn-avatar-play-sequence');
  ctrl.btnPlayAllTests = findEl('#btn-avatar-play-all-tests');
  ctrl.btnPlayWeek = findEl('#btn-avatar-play-week');
  ctrl.btnLoadVrm = findEl('#btn-avatar-load-vrm');
  ctrl.btnResetCam = findEl('#btn-avatar-reset-camera');
  ctrl.btnRetry = findEl('#btn-avatar-error-retry');
  ctrl.fileInputVrm = findEl('#avatar-vrm-file-input');

  ctrl.btnExportClip = findEl('#btn-avatar-export-clip');
  ctrl.btnImportClip = findEl('#btn-avatar-import-clip');
  ctrl.fileInputClip = findEl('#avatar-clip-file-input');

  ctrl.selectClip = findEl('#select-avatar-clip');
  ctrl.selectVersion = findEl('#select-avatar-version');
  ctrl.selectSpeed = findEl('#select-avatar-speed');

  if (ctrl.selectClip && ctrl.selectClip.children.length === 0) {
    renderAvatarClipOptions(ctrl);
  }

  if (ctrl.btnPlay) ctrl.btnPlay.addEventListener('click', () => ctrl.playCurrentSelection());
  if (ctrl.btnPause) ctrl.btnPause.addEventListener('click', () => ctrl.pause());
  if (ctrl.btnReset) ctrl.btnReset.addEventListener('click', () => ctrl.reset());
  if (ctrl.btnPlaySeq) ctrl.btnPlaySeq.addEventListener('click', () => ctrl.playDemoSequence());
  if (ctrl.btnPlayAllTests) ctrl.btnPlayAllTests.addEventListener('click', () => ctrl.playAllTestsSequence());
  if (ctrl.btnPlayWeek) ctrl.btnPlayWeek.addEventListener('click', () => ctrl.playWeekSequence());
  if (ctrl.btnResetCam) ctrl.btnResetCam.addEventListener('click', () => ctrl.resetCamera());

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

  bindContinuousAction(findEl('#btn-cam-rot-left'), () => ctrl.rotateCamera(-4, 0));
  bindContinuousAction(findEl('#btn-cam-rot-right'), () => ctrl.rotateCamera(4, 0));
  bindContinuousAction(findEl('#btn-cam-rot-up'), () => ctrl.rotateCamera(0, -4));
  bindContinuousAction(findEl('#btn-cam-rot-down'), () => ctrl.rotateCamera(0, 4));
  bindContinuousAction(findEl('#btn-quick-rot-left'), () => ctrl.rotateCamera(-6, 0));
  bindContinuousAction(findEl('#btn-quick-rot-right'), () => ctrl.rotateCamera(6, 0));

  bindContinuousAction(findEl('#btn-cam-pan-left'), () => ctrl.panCamera(-1, 0));
  bindContinuousAction(findEl('#btn-cam-pan-right'), () => ctrl.panCamera(1, 0));
  bindContinuousAction(findEl('#btn-cam-pan-up'), () => ctrl.panCamera(0, 1));
  bindContinuousAction(findEl('#btn-cam-pan-down'), () => ctrl.panCamera(0, -1));
  const btnPanCenter = findEl('#btn-cam-pan-center');
  if (btnPanCenter) btnPanCenter.addEventListener('click', () => ctrl.resetCamera());

  bindContinuousAction(findEl('#btn-cam-zoom-in'), () => ctrl.dollyCamera(0.12));
  bindContinuousAction(findEl('#btn-cam-zoom-out'), () => ctrl.dollyCamera(-0.12));
  bindContinuousAction(findEl('#btn-quick-zoom-in'), () => ctrl.dollyCamera(0.15));
  bindContinuousAction(findEl('#btn-quick-zoom-out'), () => ctrl.dollyCamera(-0.15));

  const presetBtns = {
    medium: findEl('#btn-cam-medium'),
    full: findEl('#btn-cam-full'),
    face: findEl('#btn-cam-face'),
    hands: findEl('#btn-cam-hands')
  };

  Object.entries(presetBtns).forEach(([preset, btn]) => {
    if (!btn) return;
    btn.addEventListener('click', () => {
      ctrl.setCameraPreset(preset);
    });
  });

  const camDock = findEl('#avatar-cam-dock');
  const dockBody = findEl('#avatar-cam-dock-body');
  const dockToggle = findEl('#btn-cam-dock-toggle');
  const quickDockToggle = findEl('#btn-quick-cam-dock-toggle');

  const toggleDock = () => {
    if (!dockBody) return;
    const isHidden = dockBody.style.display === 'none';
    dockBody.style.display = isHidden ? 'flex' : 'none';
    if (camDock) camDock.classList.toggle('dock-collapsed', !isHidden);
    if (dockToggle) dockToggle.textContent = isHidden ? '▾' : '▸';
  };

  if (dockToggle) dockToggle.addEventListener('click', toggleDock);
  if (quickDockToggle) quickDockToggle.addEventListener('click', toggleDock);

  if (ctrl.selectClip) {
    ctrl.selectClip.addEventListener('change', (e) => {
      ctrl.selectedClipId = e.target.value;
      ctrl.prepareSelectedClip();
    });
  }

  if (ctrl.selectVersion) {
    ctrl.selectVersion.addEventListener('change', (e) => {
      ctrl.setAnimationVersion(e.target.value);
    });
  }

  if (ctrl.selectSpeed) {
    ctrl.selectSpeed.addEventListener('change', (e) => {
      const rate = parseFloat(e.target.value) || 1.0;
      ctrl.setSpeed(rate);
    });
  }

  if (ctrl.btnLoadVrm && ctrl.fileInputVrm) {
    ctrl.btnLoadVrm.addEventListener('click', () => {
      ctrl.fileInputVrm.click();
    });

    ctrl.fileInputVrm.addEventListener('change', (e) => {
      const file = e.target.files && e.target.files[0];
      if (file) {
        ctrl.loadVRMFromFile(file);
      }
    });
  }

  if (ctrl.btnExportClip) {
    ctrl.btnExportClip.addEventListener('click', () => {
      ctrl.exportCurrentClip();
    });
  }

  if (ctrl.btnImportClip && ctrl.fileInputClip) {
    ctrl.btnImportClip.addEventListener('click', () => {
      ctrl.fileInputClip.click();
    });

    ctrl.fileInputClip.addEventListener('change', async (e) => {
      const file = e.target.files && e.target.files[0];
      if (file) {
        try {
          await ctrl.importCustomClip(file);
        } finally {
          ctrl.fileInputClip.value = '';
        }
      }
    });
  }

  if (ctrl.btnRetry) {
    ctrl.btnRetry.addEventListener('click', () => {
      ctrl.hideError();
      ctrl.loadInitialAvatar();
    });
  }

  const viewportWrap = findEl('#avatar-viewport-wrap') || ctrl.canvas;
  if (viewportWrap) {
    viewportWrap.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'copy';
      }
    });
    viewportWrap.addEventListener('drop', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (!e.dataTransfer || !e.dataTransfer.files || e.dataTransfer.files.length === 0) return;
      for (const file of e.dataTransfer.files) {
        const name = file.name.toLowerCase();
        if (name.endsWith('.json')) {
          await ctrl.importCustomClip(file);
        } else if (name.endsWith('.vrm') || name.endsWith('.glb')) {
          await ctrl.loadVRMFromFile(file);
        }
      }
    });
  }
}

export function syncAvatarPresetButtons(ctrl, preset) {
  const findEl = (sel) => (ctrl.container ? ctrl.container.querySelector(sel) : null) || document.querySelector(sel);
  const presetMap = {
    pip_bust: findEl('#btn-cam-pip-bust'),
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
