/**
 * LSEC Studio 2.1.1 — SubtitleEditorPanel
 * 
 * Controlador del panel lateral de edición de estilos y posición de subtítulos por segmento.
 * Conectado directamente a AppState sin copias de estado intermedias.
 * Soporta actualización en tiempo real, presets de posición, drag & drop sincronizado,
 * guía de área segura, copiar/pegar estilos, aplicar a todos y undo/redo.
 */

class SubtitleEditorPanel {
  constructor(panelContainerId = 'view-side-subtitles') {
    this.container = document.getElementById(panelContainerId);
    this.tabBtn = document.getElementById('tab-btn-side-subtitles');
    this.currentSegmentId = null;
    this.isSafeAreaVisible = false;

    this.initElements();
    this.bindEvents();
    this.subscribeState();
  }

  initElements() {
    if (!this.container) return;

    this.container.innerHTML = `
      <div class="subtitle-editor-wrap">
        <div class="sub-editor-body custom-scrollbar">
          <!-- CONTROLES ESENCIALES (Visibles por defecto sin ruido visual) -->
          <div class="sub-editor-section">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:4px;">
              <div class="sub-section-title" style="border:none; margin:0; padding:0;">Apariencia Principal</div>
              <button class="btn btn-sm" id="btn-sub-apply-all" type="button" title="Aplicar este estilo a todas las oraciones del video">
                Aplicar a todos
              </button>
            </div>

            <div class="sub-form-row">
              <label for="sub-cfg-font-size">Tamaño de texto</label>
              <div class="sub-slider-group">
                <input type="range" id="sub-cfg-font-size" min="12" max="44" step="1" value="20">
                <span class="sub-value-display" id="sub-cfg-font-size-val">20px</span>
              </div>
            </div>

            <div class="sub-form-row">
              <span class="sub-field-label" id="lbl-sub-cfg-quick-pos">Ubicación en pantalla</span>
              <div class="sub-preset-buttons" role="group" aria-labelledby="lbl-sub-cfg-quick-pos">
                <button type="button" class="btn btn-sm" id="btn-pos-preset-bottom">Inferior</button>
                <button type="button" class="btn btn-sm" id="btn-pos-preset-center">Centro</button>
                <button type="button" class="btn btn-sm" id="btn-pos-preset-top">Superior</button>
              </div>
            </div>

            <div class="sub-form-row sub-row-dual">
              <div>
                <label for="sub-cfg-text-color">Color de texto</label>
                <div class="sub-color-input-wrap">
                  <input type="color" id="sub-cfg-text-color" value="#ffffff">
                  <input type="text" id="sub-cfg-text-color-hex" class="sub-hex-input" value="#ffffff" maxlength="7" aria-label="Código hexadecimal de color de texto">
                </div>
              </div>

              <div>
                <label for="sub-cfg-bg-color">Color de fondo</label>
                <div class="sub-color-input-wrap">
                  <input type="color" id="sub-cfg-bg-color" value="#000000">
                  <input type="text" id="sub-cfg-bg-color-hex" class="sub-hex-input" value="#000000" maxlength="7" aria-label="Código hexadecimal de color de fondo">
                </div>
              </div>
            </div>

            <div class="sub-form-row">
              <label for="sub-cfg-bg-opacity">Opacidad del fondo</label>
              <div class="sub-slider-group">
                <input type="range" id="sub-cfg-bg-opacity" min="0" max="100" step="5" value="78">
                <span class="sub-value-display" id="sub-cfg-bg-opacity-val">78%</span>
              </div>
            </div>
          </div>

          <!-- CONTROLES AVANZADOS (Ocultos bajo demanda para reducir carga cognitiva) -->
          <details class="sub-advanced-details">
            <summary class="sub-advanced-summary">Ajustes avanzados por segmento</summary>
            <div class="sub-advanced-content">
              <div class="sub-editor-section">
                <div class="sub-target-picker">
                  <label for="sub-cfg-segment-select" class="sub-label-title">Oración:</label>
                  <select id="sub-cfg-segment-select" class="sub-select-target">
                    <option value="">(Selecciona una oración)</option>
                  </select>
                </div>

                <div class="sub-quick-actions-bar" style="margin-top:6px;">
                  <button class="btn btn-sm" id="btn-sub-reset" type="button" title="Restablecer estilo al predeterminado">Restablecer</button>
                  <button class="btn btn-sm" id="btn-sub-copy" type="button" title="Copiar estilo de este segmento">Copiar</button>
                  <button class="btn btn-sm" id="btn-sub-paste" type="button" title="Pegar estilo copiado" disabled>Pegar</button>
                  <button class="btn btn-sm" id="btn-sub-toggle-safe-area" type="button" title="Mostrar/ocultar guía de área segura">Guía segura</button>
                </div>
              </div>

              <div class="sub-editor-section">
                <div class="sub-section-title">Tipografía y Alineación</div>
                <div class="sub-form-row">
                  <label for="sub-cfg-font-family">Familia tipográfica</label>
                  <select id="sub-cfg-font-family" class="sub-select">
                    <option value="Inter, system-ui, -apple-system, sans-serif">Inter / Sistema</option>
                    <option value="Roboto, sans-serif">Roboto</option>
                    <option value="Montserrat, sans-serif">Montserrat</option>
                    <option value="Arial, sans-serif">Arial</option>
                    <option value="Helvetica, Arial, sans-serif">Helvetica</option>
                    <option value="Georgia, serif">Georgia</option>
                    <option value="'Courier New', monospace">Courier New</option>
                    <option value="Impact, Charcoal, sans-serif">Impact</option>
                  </select>
                </div>

                <div class="sub-form-row sub-row-dual">
                  <div>
                    <span class="sub-field-label" id="lbl-sub-cfg-style">Estilo</span>
                    <div class="sub-toggle-group" role="group" aria-labelledby="lbl-sub-cfg-style">
                      <button type="button" class="sub-btn-toggle" id="sub-cfg-bold" title="Negrita" aria-label="Negrita"><b>B</b></button>
                      <button type="button" class="sub-btn-toggle" id="sub-cfg-italic" title="Cursiva" aria-label="Cursiva"><i>I</i></button>
                    </div>
                  </div>

                  <div>
                    <span class="sub-field-label" id="lbl-sub-cfg-align">Alineación</span>
                    <div class="sub-toggle-group" id="sub-cfg-align-group" role="group" aria-labelledby="lbl-sub-cfg-align">
                      <button type="button" class="sub-btn-toggle" data-align="left" title="Izquierda" aria-label="Alinear a la izquierda">Izq</button>
                      <button type="button" class="sub-btn-toggle active" data-align="center" title="Centro" aria-label="Alinear al centro">Cen</button>
                      <button type="button" class="sub-btn-toggle" data-align="right" title="Derecha" aria-label="Alinear a la derecha">Der</button>
                    </div>
                  </div>
                </div>
              </div>

              <div class="sub-editor-section">
                <div class="sub-section-title">Contorno, Sombra y Coordenadas</div>
                <div class="sub-form-row sub-row-dual">
                  <div>
                    <label for="sub-cfg-outline-width">Contorno</label>
                    <div class="sub-slider-group">
                      <input type="range" id="sub-cfg-outline-width" min="0" max="8" step="1" value="0">
                      <span class="sub-value-display" id="sub-cfg-outline-width-val">0px</span>
                    </div>
                  </div>
                  <div>
                    <label for="sub-cfg-outline-color">Color contorno</label>
                    <div class="sub-color-input-wrap">
                      <input type="color" id="sub-cfg-outline-color" value="#000000">
                    </div>
                  </div>
                </div>

                <div class="sub-form-row">
                  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                    <label for="sub-cfg-shadow-toggle" style="margin-bottom:0; cursor:pointer;">Sombra de texto</label>
                    <input type="checkbox" id="sub-cfg-shadow-toggle" checked style="width:16px; height:16px; cursor:pointer;">
                  </div>
                  <div class="sub-slider-group" id="sub-shadow-controls">
                    <input type="range" id="sub-cfg-shadow-blur" min="0" max="20" step="1" value="4" aria-label="Desenfoque de sombra de texto">
                    <span class="sub-value-display" id="sub-cfg-shadow-blur-val">4px</span>
                    <input type="color" id="sub-cfg-shadow-color" value="#000000" style="margin-left:6px;" title="Color de sombra" aria-label="Color de sombra de texto">
                  </div>
                </div>

                <div class="sub-form-row sub-row-dual">
                  <div>
                    <label for="sub-cfg-pos-x">Posición X</label>
                    <div class="sub-slider-group">
                      <input type="range" id="sub-cfg-pos-x" min="0" max="100" step="1" value="50">
                      <span class="sub-value-display" id="sub-cfg-pos-x-val">50%</span>
                    </div>
                  </div>
                  <div>
                    <label for="sub-cfg-pos-y">Posición Y</label>
                    <div class="sub-slider-group">
                      <input type="range" id="sub-cfg-pos-y" min="0" max="100" step="1" value="88">
                      <span class="sub-value-display" id="sub-cfg-pos-y-val">88%</span>
                    </div>
                  </div>
                </div>

                <div class="sub-form-row sub-row-dual">
                  <div>
                    <label for="sub-cfg-margin">Margen</label>
                    <div class="sub-slider-group">
                      <input type="range" id="sub-cfg-margin" min="4" max="36" step="2" value="12">
                      <span class="sub-value-display" id="sub-cfg-margin-val">12px</span>
                    </div>
                  </div>
                  <div>
                    <label for="sub-cfg-safe-area">Área segura</label>
                    <div class="sub-slider-group">
                      <input type="range" id="sub-cfg-safe-area" min="0" max="20" step="1" value="5">
                      <span class="sub-value-display" id="sub-cfg-safe-area-val">5%</span>
                    </div>
                  </div>
                </div>

                <div style="display:flex; justify-content:space-between; gap:8px; margin-top:4px;">
                  <button class="btn btn-sm" id="btn-sub-undo" type="button" title="Deshacer (Ctrl+Z)" disabled>Deshacer</button>
                  <button class="btn btn-sm" id="btn-sub-redo" type="button" title="Rehacer (Ctrl+Y)" disabled>Rehacer</button>
                </div>
              </div>
            </div>
          </details>
        </div>
      </div>
    `;

    this.cacheFieldRefs();
  }

  cacheFieldRefs() {
    this.segSelect = document.getElementById('sub-cfg-segment-select');
    this.btnReset = document.getElementById('btn-sub-reset');
    this.btnCopy = document.getElementById('btn-sub-copy');
    this.btnPaste = document.getElementById('btn-sub-paste');
    this.btnApplyAll = document.getElementById('btn-sub-apply-all');
    this.btnToggleSafeArea = document.getElementById('btn-sub-toggle-safe-area');
    this.btnUndo = document.getElementById('btn-sub-undo');
    this.btnRedo = document.getElementById('btn-sub-redo');

    this.fontFamily = document.getElementById('sub-cfg-font-family');
    this.fontSize = document.getElementById('sub-cfg-font-size');
    this.fontSizeVal = document.getElementById('sub-cfg-font-size-val');
    this.btnBold = document.getElementById('sub-cfg-bold');
    this.btnItalic = document.getElementById('sub-cfg-italic');

    this.alignGroup = document.getElementById('sub-cfg-align-group');

    this.textColor = document.getElementById('sub-cfg-text-color');
    this.textColorHex = document.getElementById('sub-cfg-text-color-hex');
    this.bgColor = document.getElementById('sub-cfg-bg-color');
    this.bgColorHex = document.getElementById('sub-cfg-bg-color-hex');
    this.bgOpacity = document.getElementById('sub-cfg-bg-opacity');
    this.bgOpacityVal = document.getElementById('sub-cfg-bg-opacity-val');

    this.outlineWidth = document.getElementById('sub-cfg-outline-width');
    this.outlineWidthVal = document.getElementById('sub-cfg-outline-width-val');
    this.outlineColor = document.getElementById('sub-cfg-outline-color');

    this.shadowToggle = document.getElementById('sub-cfg-shadow-toggle');
    this.shadowBlur = document.getElementById('sub-cfg-shadow-blur');
    this.shadowBlurVal = document.getElementById('sub-cfg-shadow-blur-val');
    this.shadowColor = document.getElementById('sub-cfg-shadow-color');

    this.posX = document.getElementById('sub-cfg-pos-x');
    this.posXVal = document.getElementById('sub-cfg-pos-x-val');
    this.posY = document.getElementById('sub-cfg-pos-y');
    this.posYVal = document.getElementById('sub-cfg-pos-y-val');

    this.margin = document.getElementById('sub-cfg-margin');
    this.marginVal = document.getElementById('sub-cfg-margin-val');
    this.safeArea = document.getElementById('sub-cfg-safe-area');
    this.safeAreaVal = document.getElementById('sub-cfg-safe-area-val');

    this.btnPresetBottom = document.getElementById('btn-pos-preset-bottom');
    this.btnPresetCenter = document.getElementById('btn-pos-preset-center');
    this.btnPresetTop = document.getElementById('btn-pos-preset-top');
  }

  bindEvents() {
    // Cambio de segmento desde el dropdown
    if (this.segSelect) {
      this.segSelect.addEventListener('change', (e) => {
        const segId = e.target.value;
        if (segId) {
          appState.selectItem('segment', segId);
          const seg = (appState.state.project?.segments || []).find(s => s.id === segId);
          if (seg) {
            appState.setCurrentTime(seg.start_seconds !== undefined ? seg.start_seconds : (seg.start_time || 0), 'editor_select');
          }
        }
      });
    }

    // Botones de acción principales
    if (this.btnReset) {
      this.btnReset.addEventListener('click', () => {
        const segId = this.getActiveSegmentId();
        if (segId) {
          appState.resetSegmentSubtitleStyle(segId);
          this.loadSegmentStyle(segId);
        }
      });
    }

    if (this.btnCopy) {
      this.btnCopy.addEventListener('click', () => {
        const segId = this.getActiveSegmentId();
        if (segId) {
          const copied = appState.copySegmentSubtitleStyle(segId);
          if (copied && this.btnPaste) {
            this.btnPaste.disabled = false;
            this.btnCopy.textContent = '✓ Copiado';
            setTimeout(() => { if (this.btnCopy) this.btnCopy.textContent = '📋 Copiar'; }, 1200);
          }
        }
      });
    }

    if (this.btnPaste) {
      this.btnPaste.addEventListener('click', () => {
        const segId = this.getActiveSegmentId();
        if (segId) {
          const ok = appState.pasteSegmentSubtitleStyle(segId);
          if (ok) this.loadSegmentStyle(segId);
        }
      });
    }

    if (this.btnApplyAll) {
      this.btnApplyAll.addEventListener('click', () => {
        const segId = this.getActiveSegmentId();
        if (segId) {
          appState.applySubtitleStyleToAllSegments(segId);
          this.btnApplyAll.textContent = '✓ Aplicado';
          setTimeout(() => { if (this.btnApplyAll) this.btnApplyAll.textContent = '✦ A todos'; }, 1200);
        }
      });
    }

    if (this.btnToggleSafeArea) {
      this.btnToggleSafeArea.addEventListener('click', () => {
        this.isSafeAreaVisible = !this.isSafeAreaVisible;
        this.btnToggleSafeArea.classList.toggle('active', this.isSafeAreaVisible);
        appState.emit('safeAreaGuideToggled', this.isSafeAreaVisible);
      });
    }

    if (this.btnUndo) this.btnUndo.addEventListener('click', () => appState.undo());
    if (this.btnRedo) this.btnRedo.addEventListener('click', () => appState.redo());

    // Presets rápidos de posición
    if (this.btnPresetBottom) {
      this.btnPresetBottom.addEventListener('click', () => {
        this.posY.value = 88;
        this.posYVal.textContent = '88%';
        this.commitChange({ positionY: 88 });
      });
    }
    if (this.btnPresetCenter) {
      this.btnPresetCenter.addEventListener('click', () => {
        this.posY.value = 50;
        this.posYVal.textContent = '50%';
        this.commitChange({ positionY: 50 });
      });
    }
    if (this.btnPresetTop) {
      this.btnPresetTop.addEventListener('click', () => {
        this.posY.value = 14;
        this.posYVal.textContent = '14%';
        this.commitChange({ positionY: 14 });
      });
    }

    // Tipografía
    if (this.fontFamily) {
      this.fontFamily.addEventListener('change', (e) => this.commitChange({ fontFamily: e.target.value }));
    }

    if (this.fontSize) {
      this.fontSize.addEventListener('input', (e) => {
        this.fontSizeVal.textContent = `${e.target.value}px`;
        this.liveChange({ fontSize: parseInt(e.target.value, 10) });
      });
      this.fontSize.addEventListener('change', (e) => {
        this.commitChange({ fontSize: parseInt(e.target.value, 10) });
      });
    }

    if (this.btnBold) {
      this.btnBold.addEventListener('click', () => {
        const next = !this.btnBold.classList.contains('active');
        this.btnBold.classList.toggle('active', next);
        this.commitChange({ bold: next });
      });
    }

    if (this.btnItalic) {
      this.btnItalic.addEventListener('click', () => {
        const next = !this.btnItalic.classList.contains('active');
        this.btnItalic.classList.toggle('active', next);
        this.commitChange({ italic: next });
      });
    }

    if (this.alignGroup) {
      const alignBtns = this.alignGroup.querySelectorAll('.sub-btn-toggle');
      alignBtns.forEach(btn => {
        btn.addEventListener('click', () => {
          alignBtns.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          const align = btn.dataset.align || 'center';
          this.commitChange({ textAlign: align });
        });
      });
    }

    // Colores
    if (this.textColor) {
      this.textColor.addEventListener('input', (e) => {
        this.textColorHex.value = e.target.value;
        this.liveChange({ textColor: e.target.value });
      });
      this.textColor.addEventListener('change', (e) => {
        this.commitChange({ textColor: e.target.value });
      });
    }
    if (this.textColorHex) {
      this.textColorHex.addEventListener('change', (e) => {
        let val = e.target.value.trim();
        if (!val.startsWith('#')) val = '#' + val;
        if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
          this.textColor.value = val;
          this.commitChange({ textColor: val });
        }
      });
    }

    if (this.bgColor) {
      this.bgColor.addEventListener('input', (e) => {
        this.bgColorHex.value = e.target.value;
        this.liveChange({ bgColor: e.target.value });
      });
      this.bgColor.addEventListener('change', (e) => {
        this.commitChange({ bgColor: e.target.value });
      });
    }
    if (this.bgColorHex) {
      this.bgColorHex.addEventListener('change', (e) => {
        let val = e.target.value.trim();
        if (!val.startsWith('#')) val = '#' + val;
        if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
          this.bgColor.value = val;
          this.commitChange({ bgColor: val });
        }
      });
    }

    if (this.bgOpacity) {
      this.bgOpacity.addEventListener('input', (e) => {
        this.bgOpacityVal.textContent = `${e.target.value}%`;
        this.liveChange({ bgOpacity: parseInt(e.target.value, 10) / 100 });
      });
      this.bgOpacity.addEventListener('change', (e) => {
        this.commitChange({ bgOpacity: parseInt(e.target.value, 10) / 100 });
      });
    }

    // Contorno y Sombra
    if (this.outlineWidth) {
      this.outlineWidth.addEventListener('input', (e) => {
        this.outlineWidthVal.textContent = `${e.target.value}px`;
        this.liveChange({ outlineWidth: parseInt(e.target.value, 10) });
      });
      this.outlineWidth.addEventListener('change', (e) => {
        this.commitChange({ outlineWidth: parseInt(e.target.value, 10) });
      });
    }
    if (this.outlineColor) {
      this.outlineColor.addEventListener('input', (e) => this.liveChange({ outlineColor: e.target.value }));
      this.outlineColor.addEventListener('change', (e) => this.commitChange({ outlineColor: e.target.value }));
    }

    if (this.shadowToggle) {
      this.shadowToggle.addEventListener('change', (e) => {
        this.commitChange({ shadow: e.target.checked });
      });
    }
    if (this.shadowBlur) {
      this.shadowBlur.addEventListener('input', (e) => {
        this.shadowBlurVal.textContent = `${e.target.value}px`;
        this.liveChange({ shadowBlur: parseInt(e.target.value, 10) });
      });
      this.shadowBlur.addEventListener('change', (e) => {
        this.commitChange({ shadowBlur: parseInt(e.target.value, 10) });
      });
    }
    if (this.shadowColor) {
      this.shadowColor.addEventListener('input', (e) => this.liveChange({ shadowColor: e.target.value }));
      this.shadowColor.addEventListener('change', (e) => this.commitChange({ shadowColor: e.target.value }));
    }

    // Posición X y Y
    if (this.posX) {
      this.posX.addEventListener('input', (e) => {
        this.posXVal.textContent = `${e.target.value}%`;
        this.liveChange({ positionX: parseInt(e.target.value, 10) });
      });
      this.posX.addEventListener('change', (e) => {
        this.commitChange({ positionX: parseInt(e.target.value, 10) });
      });
    }
    if (this.posY) {
      this.posY.addEventListener('input', (e) => {
        this.posYVal.textContent = `${e.target.value}%`;
        this.liveChange({ positionY: parseInt(e.target.value, 10) });
      });
      this.posY.addEventListener('change', (e) => {
        this.commitChange({ positionY: parseInt(e.target.value, 10) });
      });
    }

    // Márgenes y Área Segura
    if (this.margin) {
      this.margin.addEventListener('input', (e) => {
        this.marginVal.textContent = `${e.target.value}px`;
        this.liveChange({ margin: parseInt(e.target.value, 10) });
      });
      this.margin.addEventListener('change', (e) => {
        this.commitChange({ margin: parseInt(e.target.value, 10) });
      });
    }
    if (this.safeArea) {
      this.safeArea.addEventListener('input', (e) => {
        this.safeAreaVal.textContent = `${e.target.value}%`;
        this.liveChange({ safeArea: parseInt(e.target.value, 10) });
      });
      this.safeArea.addEventListener('change', (e) => {
        this.commitChange({ safeArea: parseInt(e.target.value, 10) });
      });
    }
  }

  subscribeState() {
    appState.subscribe('projectLoaded', () => {
      this.populateSegmentsDropdown();
      if (appState.state.playback.selectedItem?.type === 'segment') {
        this.loadSegmentStyle(appState.state.playback.selectedItem.id);
      }
    });

    appState.subscribe('selectionChanged', (selection) => {
      if (selection && selection.type === 'segment') {
        this.currentSegmentId = selection.id;
        if (this.segSelect) this.segSelect.value = selection.id;
        this.loadSegmentStyle(selection.id);
      }
    });

    appState.subscribe('activeSegmentChanged', ({ id }) => {
      if (!this.currentSegmentId && id) {
        this.loadSegmentStyle(id);
      }
    });

    appState.subscribe('segmentSubtitleStyleChanged', ({ segId, style }) => {
      if (segId === this.currentSegmentId) {
        this.loadSegmentStyle(segId);
      }
    });

    appState.subscribe('historyChanged', ({ canUndo, canRedo }) => {
      if (this.btnUndo) this.btnUndo.disabled = !canUndo;
      if (this.btnRedo) this.btnRedo.disabled = !canRedo;
    });

    appState.subscribe('subtitlePositionDragged', ({ segId, posX, posY }) => {
      if (segId === this.currentSegmentId) {
        if (this.posX) {
          this.posX.value = posX;
          this.posXVal.textContent = `${posX}%`;
        }
        if (this.posY) {
          this.posY.value = posY;
          this.posYVal.textContent = `${posY}%`;
        }
      }
    });
  }

  populateSegmentsDropdown() {
    if (!this.segSelect) return;
    this.segSelect.innerHTML = '';

    const segments = appState.state.project?.segments || [];
    if (segments.length === 0) {
      this.segSelect.innerHTML = '<option value="">(Sin segmentos)</option>';
      return;
    }

    segments.forEach((seg, idx) => {
      const opt = document.createElement('option');
      opt.value = seg.id;
      const st = seg.start_seconds !== undefined ? seg.start_seconds : (seg.start_time || 0);
      const et = seg.end_seconds !== undefined ? seg.end_seconds : (seg.end_time || 0);
      const textPreview = (seg.normalized_text || seg.original_text || '').slice(0, 30);
      opt.textContent = `#${idx + 1} [${st.toFixed(1)}s - ${et.toFixed(1)}s] ${textPreview}`;
      this.segSelect.appendChild(opt);
    });

    if (this.currentSegmentId) {
      this.segSelect.value = this.currentSegmentId;
    } else if (segments.length > 0) {
      this.currentSegmentId = segments[0].id;
      this.segSelect.value = segments[0].id;
      this.loadSegmentStyle(segments[0].id);
    }
  }

  getActiveSegmentId() {
    return this.currentSegmentId || (appState.state.project?.segments?.[0]?.id) || null;
  }

  loadSegmentStyle(segId) {
    if (!segId) return;
    this.currentSegmentId = segId;
    if (this.segSelect) this.segSelect.value = segId;

    const seg = (appState.state.project?.segments || []).find(s => s.id === segId);
    const style = (typeof SubtitleEngine !== 'undefined')
      ? SubtitleEngine.resolveEffectiveStyle(seg, appState.state.overlays?.subtitleStyle)
      : { ...appState.state.overlays?.subtitleStyle, ...(seg?.subtitle_style || {}) };

    if (!style) return;

    // Actualizar campos del formulario
    if (this.fontFamily) {
      this.fontFamily.value = style.fontFamily || 'Inter, system-ui, -apple-system, sans-serif';
      if (this.fontFamily.selectedIndex === -1) {
        this.fontFamily.selectedIndex = 0;
      }
    }
    if (this.fontSize) {
      this.fontSize.value = style.fontSize || 20;
      this.fontSizeVal.textContent = `${style.fontSize || 20}px`;
    }

    if (this.btnBold) this.btnBold.classList.toggle('active', !!style.bold);
    if (this.btnItalic) this.btnItalic.classList.toggle('active', !!style.italic);

    if (this.alignGroup) {
      const alignBtns = this.alignGroup.querySelectorAll('.sub-btn-toggle');
      alignBtns.forEach(b => {
        b.classList.toggle('active', b.dataset.align === (style.textAlign || 'center'));
      });
    }

    if (this.textColor) this.textColor.value = style.textColor || '#ffffff';
    if (this.textColorHex) this.textColorHex.value = style.textColor || '#ffffff';

    if (this.bgColor) this.bgColor.value = (style.bgColor && style.bgColor !== 'transparent') ? style.bgColor : '#000000';
    if (this.bgColorHex) this.bgColorHex.value = (style.bgColor && style.bgColor !== 'transparent') ? style.bgColor : '#000000';

    if (this.bgOpacity) {
      const opPct = Math.round((style.bgOpacity !== undefined ? style.bgOpacity : 0.0) * 100);
      this.bgOpacity.value = opPct;
      this.bgOpacityVal.textContent = `${opPct}%`;
    }

    if (this.outlineWidth) {
      this.outlineWidth.value = style.outlineWidth !== undefined ? style.outlineWidth : 0;
      this.outlineWidthVal.textContent = `${style.outlineWidth !== undefined ? style.outlineWidth : 0}px`;
    }
    if (this.outlineColor) this.outlineColor.value = style.outlineColor || '#000000';

    if (this.shadowToggle) this.shadowToggle.checked = style.shadow !== false;
    if (this.shadowBlur) {
      this.shadowBlur.value = style.shadowBlur !== undefined ? style.shadowBlur : 4;
      this.shadowBlurVal.textContent = `${style.shadowBlur !== undefined ? style.shadowBlur : 4}px`;
    }
    if (this.shadowColor) this.shadowColor.value = style.shadowColor || '#000000';

    if (this.posX) {
      this.posX.value = style.positionX !== undefined ? style.positionX : 50;
      this.posXVal.textContent = `${style.positionX !== undefined ? style.positionX : 50}%`;
    }
    if (this.posY) {
      this.posY.value = style.positionY !== undefined ? style.positionY : 88;
      this.posYVal.textContent = `${style.positionY !== undefined ? style.positionY : 88}%`;
    }

    if (this.margin) {
      this.margin.value = style.margin !== undefined ? style.margin : 12;
      this.marginVal.textContent = `${style.margin !== undefined ? style.margin : 12}px`;
    }
    if (this.safeArea) {
      this.safeArea.value = style.safeArea !== undefined ? style.safeArea : 5;
      this.safeAreaVal.textContent = `${style.safeArea !== undefined ? style.safeArea : 5}%`;
    }

    if (this.btnPaste) {
      this.btnPaste.disabled = !appState.copiedSubtitleStyle;
    }
  }

  liveChange(changes) {
    const segId = this.getActiveSegmentId();
    if (segId) {
      appState.updateSegmentSubtitleStyle(segId, changes, false);
    }
  }

  commitChange(changes) {
    const segId = this.getActiveSegmentId();
    if (segId) {
      appState.updateSegmentSubtitleStyle(segId, changes, true);
    }
  }
}

// Instancia global disponible en el navegador
if (typeof window !== 'undefined') {
  window.SubtitleEditorPanel = SubtitleEditorPanel;
}
