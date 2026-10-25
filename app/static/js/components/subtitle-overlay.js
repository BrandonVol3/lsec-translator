/**
 * LSEC Studio 2.1.1 — Componente SubtitleOverlay
 * 
 * Capa de renderizado de subtítulos sincronizados sobre el reproductor de video.
 * Integrado con SubtitleEngine para aplicar el estilo efectivo resuelto (estilo predeterminado + segmento).
 * Soporta arrastre directo (drag & drop) en tiempo real con confinamiento en área segura,
 * guía visual de área segura durante edición y renderizado fiel 1:1 idéntico a la exportación de video.
 */

class SubtitleOverlayController {
  constructor(containerId = 'subtitle-overlay-container') {
    this.container = document.getElementById(containerId);
    this.toggleBtn = document.getElementById('btn-toggle-subtitles');
    this.quickConfigBtn = document.getElementById('btn-subtitle-quick-config');

    this.currentSegment = null;
    this.currentWordIdx = -1;

    // Estado de arrastre
    this.isDragging = false;
    this.dragSegment = null;
    this.dragStartX = 0;
    this.dragStartY = 0;
    this.initialPosX = 50;
    this.initialPosY = 88;
    this.currentDragX = 50;
    this.currentDragY = 88;

    // Guía de área segura
    this.showSafeAreaGuide = false;
    this.safeAreaGuideEl = null;

    this.init();
    this.subscribeState();
  }

  init() {
    if (this.toggleBtn) {
      this.toggleBtn.addEventListener('click', () => {
        const next = !appState.state.overlays.subtitlesEnabled;
        appState.setOverlayPreference('subtitlesEnabled', next);
      });
    }

    if (this.quickConfigBtn) {
      this.quickConfigBtn.addEventListener('click', () => {
        // Abrir pestaña de subtítulos en el panel lateral si existe
        const tabBtn = document.getElementById('tab-btn-side-subtitles');
        if (tabBtn) {
          tabBtn.click();
        } else {
          this.openQuickConfigDialog();
        }
      });
    }

    // Inicializar elementos dentro del contenedor
    if (this.container) {
      this.container.innerHTML = `
        <div id="safe-area-guide" class="safe-area-guide" style="display:none;">
          <span class="safe-area-guide-label" id="safe-area-guide-label">Área Segura</span>
        </div>
        <div id="subtitle-box-wrapper"></div>
      `;
      this.safeAreaGuideEl = this.container.querySelector('#safe-area-guide');
      this.safeAreaGuideLabel = this.container.querySelector('#safe-area-guide-label');
      this.boxWrapper = this.container.querySelector('#subtitle-box-wrapper');
    }

    // Listeners globales para Drag & Drop
    window.addEventListener('mousemove', (e) => this.onWindowMouseMove(e));
    window.addEventListener('mouseup', (e) => this.onWindowMouseUp(e));
    window.addEventListener('touchmove', (e) => this.onWindowTouchMove(e), { passive: false });
    window.addEventListener('touchend', (e) => this.onWindowTouchEnd(e));

    // Redimensionamiento de ventana
    window.addEventListener('resize', () => {
      this.render(appState.state?.playback?.currentTime || 0);
    });
  }

  subscribeState() {
    appState.subscribe('timeupdate', ({ time }) => {
      if (!this.isDragging) {
        this.render(time);
      }
    });

    appState.subscribe('overlayPrefChanged', ({ key, value }) => {
      if (key === 'subtitlesEnabled') {
        this.updateVisibility(value);
      } else if (key === 'subtitleMode' || key === 'subtitleWordHighlight') {
        this.render(appState.state.playback.currentTime);
      }
    });

    appState.subscribe('subtitleStyleChanged', () => {
      this.render(appState.state.playback.currentTime);
    });

    appState.subscribe('segmentSubtitleStyleChanged', () => {
      this.render(appState.state.playback.currentTime);
    });

    appState.subscribe('selectionChanged', (selection) => {
      if (selection && selection.type === 'segment') {
        this.render(appState.state.playback.currentTime);
      }
    });

    // Actualización inmediata al editar o cambiar segmentos o subtítulos
    appState.subscribe('segmentUpdated', () => {
      this.render(appState.state?.playback?.currentTime || 0);
    });

    appState.subscribe('segmentsChanged', () => {
      this.render(appState.state?.playback?.currentTime || 0);
    });

    appState.subscribe('subtitlesChanged', () => {
      this.render(appState.state?.playback?.currentTime || 0);
    });

    appState.subscribe('projectUpdated', () => {
      this.render(appState.state?.playback?.currentTime || 0);
    });

    appState.subscribe('stageChanged', () => {
      setTimeout(() => {
        this.render(appState.state?.playback?.currentTime || 0);
      }, 40);
    });

    appState.subscribe('safeAreaGuideToggled', (show) => {
      this.showSafeAreaGuide = !!show;
      this.updateSafeAreaGuideVisibility();
      this.render(appState.state.playback.currentTime);
    });

    this.updateVisibility(appState.state.overlays.subtitlesEnabled);
  }

  updateVisibility(enabled) {
    if (!this.container) return;
    this.container.style.display = enabled ? 'block' : 'none';
    if (this.toggleBtn) {
      if (enabled) {
        this.toggleBtn.classList.add('active');
        this.toggleBtn.setAttribute('aria-pressed', 'true');
      } else {
        this.toggleBtn.classList.remove('active');
        this.toggleBtn.setAttribute('aria-pressed', 'false');
      }
    }
  }

  updateSafeAreaGuideVisibility() {
    if (!this.safeAreaGuideEl) return;
    const shouldShow = this.isDragging || this.showSafeAreaGuide;
    this.safeAreaGuideEl.style.display = shouldShow ? 'block' : 'none';
  }

  render(time) {
    if (!this.container || !this.boxWrapper) return;

    if (!appState.state.overlays.subtitlesEnabled) {
      this.boxWrapper.innerHTML = '';
      if (this.safeAreaGuideEl) this.safeAreaGuideEl.style.display = 'none';
      return;
    }

    const project = appState.state.project;
    if (!project || !project.segments || project.segments.length === 0) {
      this.boxWrapper.innerHTML = '';
      if (this.safeAreaGuideEl) this.safeAreaGuideEl.style.display = 'none';
      return;
    }

    // Buscar segmento correspondiente al tiempo actual
    let seg = project.segments.find(s => {
      const st = s.start_time !== undefined ? s.start_time : (s.start_seconds !== undefined ? s.start_seconds : 0);
      const et = s.end_time !== undefined ? s.end_time : (s.end_seconds !== undefined ? s.end_seconds : 0);
      return time >= st && time <= et;
    });

    // Si el video está en pausa y el usuario tiene un segmento seleccionado, renderizarlo para permitir edición y vista previa inmediata
    if (!seg && !appState.state.playback.isPlaying && appState.state.playback.selectedItem?.type === 'segment') {
      const selId = appState.state.playback.selectedItem.id;
      seg = project.segments.find(s => s.id === selId) || appState.state.playback.selectedItem.data;
    }

    if (!seg) {
      this.boxWrapper.innerHTML = '';
      this.currentSegment = null;
      if (!this.showSafeAreaGuide && this.safeAreaGuideEl) {
        this.safeAreaGuideEl.style.display = 'none';
      }
      return;
    }

    this.currentSegment = seg;

    // 1. Resolver Estilo Efectivo Unificado (Predeterminado + Segmento)
    const style = (typeof SubtitleEngine !== 'undefined')
      ? SubtitleEngine.resolveEffectiveStyle(seg, appState.state.overlays.subtitleStyle)
      : { ...appState.state.overlays.subtitleStyle, ...(seg.subtitle_style || {}) };

    const mode = appState.state.overlays.subtitleMode; // 'normalized' | 'original'
    const displayText = mode === 'normalized' ? (seg.normalized_text || seg.original_text) : seg.original_text;

    // Dimensiones del contenedor del reproductor
    const containerW = this.container.clientWidth || 800;
    const containerH = this.container.clientHeight || 450;

    // 2. Calcular Layout Métrica con Confinamiento al Área Segura
    let layout;
    if (typeof SubtitleEngine !== 'undefined') {
      layout = SubtitleEngine.calculateLayout(null, displayText, style, containerW, containerH);
    } else {
      layout = {
        boxLeft: Math.round(containerW * 0.1),
        boxTop: Math.round(containerH * 0.85),
        boxWidth: Math.round(containerW * 0.8),
        boxHeight: 45,
        computedFontSize: style.fontSize || 20,
        computedMargin: style.margin || 12,
        computedOutline: style.outlineWidth || 0,
        computedShadowBlur: style.shadowBlur || 4,
        safeRect: { left: 40, top: 20, width: containerW - 80, height: containerH - 40 }
      };
    }

    // 3. Actualizar Posición de la Guía de Área Segura
    if (this.safeAreaGuideEl && layout.safeRect) {
      this.safeAreaGuideEl.style.left = `${layout.safeRect.left}px`;
      this.safeAreaGuideEl.style.top = `${layout.safeRect.top}px`;
      this.safeAreaGuideEl.style.width = `${layout.safeRect.width}px`;
      this.safeAreaGuideEl.style.height = `${layout.safeRect.height}px`;
      if (this.safeAreaGuideLabel) {
        this.safeAreaGuideLabel.textContent = `Área Segura (${style.safeArea || 5}%)`;
      }
      this.updateSafeAreaGuideVisibility();
    }

    // 4. Construir Caja de Subtítulo Interactiva
    const box = document.createElement('div');
    box.className = `subtitle-box ${this.isDragging ? 'is-dragging' : ''}`;
    box.id = `sub-box-${seg.id}`;
    box.title = 'Arrastra para reubicar este subtítulo (o haz clic para editar)';

    // Posicionamiento absoluto exacto calculado
    box.style.position = 'absolute';
    box.style.left = `${layout.boxLeft}px`;
    box.style.top = `${layout.boxTop}px`;
    box.style.width = `${layout.boxWidth}px`;
    box.style.height = `${layout.boxHeight}px`;
    box.style.boxSizing = 'border-box';

    // Tipografía y estética
    box.style.fontFamily = style.fontFamily || 'Inter, system-ui, sans-serif';
    box.style.fontSize = `${layout.computedFontSize}px`;
    box.style.fontWeight = style.bold ? '700' : '500';
    box.style.fontStyle = style.italic ? 'italic' : 'normal';
    box.style.color = style.textColor || '#ffffff';
    box.style.textAlign = style.textAlign || 'center';
    box.style.padding = `${layout.computedMargin}px`;
    box.style.borderRadius = `${Math.max(4, Math.round((layout.scaleFactor || 1) * 6))}px`;
    box.style.pointerEvents = 'auto';
    box.style.cursor = this.isDragging ? 'grabbing' : 'grab';
    box.style.userSelect = 'none';

    // Color y opacidad de fondo
    const isTransparentBg = (style.bgOpacity !== undefined && style.bgOpacity <= 0) || style.bgColor === 'transparent';
    if (isTransparentBg) {
      box.style.backgroundColor = 'transparent';
      box.style.backdropFilter = 'none';
      box.style.webkitBackdropFilter = 'none';
      box.style.boxShadow = 'none';
      box.style.border = '1px solid transparent';
    } else {
      if (typeof SubtitleEngine !== 'undefined') {
        box.style.backgroundColor = SubtitleEngine.hexToRgba(style.bgColor || '#000000', style.bgOpacity !== undefined ? style.bgOpacity : 0.85);
      } else {
        box.style.backgroundColor = style.bgColor || 'rgba(11, 14, 20, 0.85)';
      }
      box.style.border = '1px solid rgba(255, 255, 255, 0.12)';
    }

    // Contorno y Sombra (idéntico a SubtitleEngine.drawToCanvas)
    let textShadowParts = [];
    if (style.shadow) {
      const sOffsetX = style.shadowOffsetX !== undefined ? style.shadowOffsetX : 0;
      const sOffsetY = style.shadowOffsetY !== undefined ? style.shadowOffsetY : 1;
      const sBlur = layout.computedShadowBlur !== undefined ? layout.computedShadowBlur : 3;
      const sColor = style.shadowColor || 'rgba(0, 0, 0, 0.85)';
      textShadowParts.push(`${sOffsetX}px ${sOffsetY}px ${sBlur}px ${sColor}`);
    }
    if (layout.computedOutline > 0) {
      box.style.webkitTextStroke = `${layout.computedOutline}px ${style.outlineColor || '#000000'}`;
    } else {
      box.style.webkitTextStroke = '0px transparent';
    }
    if (textShadowParts.length > 0) {
      box.style.textShadow = textShadowParts.join(', ');
    } else {
      box.style.textShadow = 'none';
    }

    // 5. Contenido de Texto Unificado 1:1 con la Exportación (Sin modo karaoke)
    if (layout.lines && layout.lines.length > 0) {
      layout.lines.forEach((line) => {
        const lineDiv = document.createElement('div');
        lineDiv.className = 'subtitle-line';
        lineDiv.textContent = line;
        lineDiv.style.lineHeight = `${layout.lineHeight}px`;
        lineDiv.style.height = `${layout.lineHeight}px`;
        lineDiv.style.whiteSpace = 'pre-wrap';
        lineDiv.style.wordBreak = 'break-word';
        box.appendChild(lineDiv);
      });
    } else {
      const lineDiv = document.createElement('div');
      lineDiv.className = 'subtitle-line';
      lineDiv.textContent = displayText;
      lineDiv.style.lineHeight = `${layout.lineHeight}px`;
      lineDiv.style.height = `${layout.lineHeight}px`;
      box.appendChild(lineDiv);
    }

    // Indicador visual discreto de arrastre en edición
    const dragHandle = document.createElement('span');
    dragHandle.className = 'subtitle-drag-handle';
    dragHandle.innerHTML = '⋮⋮';
    box.appendChild(dragHandle);

    // 6. Listeners para Arrastre (Drag & Drop) y Selección
    box.addEventListener('mousedown', (e) => this.onBoxMouseDown(e, seg, style));
    box.addEventListener('touchstart', (e) => this.onBoxTouchStart(e, seg, style), { passive: false });

    // Clic simple para seleccionar segmento en el editor lateral
    box.addEventListener('click', (e) => {
      e.stopPropagation();
      appState.selectItem('segment', seg.id);
      const tabBtn = document.getElementById('tab-btn-side-subtitles');
      if (tabBtn && !tabBtn.classList.contains('active')) {
        tabBtn.click();
      }
    });

    this.boxWrapper.innerHTML = '';
    this.boxWrapper.appendChild(box);
  }

  // ============================================================
  // LÓGICA DE ARRASTRE Y SOLTAR (DRAG & DROP)
  // ============================================================

  onBoxMouseDown(e, seg, style) {
    if (e.button !== 0) return; // Sólo clic primario
    e.preventDefault();
    e.stopPropagation();

    this.startDrag(e.clientX, e.clientY, seg, style);
  }

  onBoxTouchStart(e, seg, style) {
    if (e.touches.length !== 1) return;
    e.preventDefault();
    e.stopPropagation();

    const touch = e.touches[0];
    this.startDrag(touch.clientX, touch.clientY, seg, style);
  }

  startDrag(clientX, clientY, seg, style) {
    this.isDragging = true;
    this.dragSegment = seg;
    this.dragStartX = clientX;
    this.dragStartY = clientY;

    this.initialPosX = style.positionX !== undefined ? style.positionX : 50;
    this.initialPosY = style.positionY !== undefined ? style.positionY : 88;
    this.currentDragX = this.initialPosX;
    this.currentDragY = this.initialPosY;

    // Seleccionar segmento en el estado
    appState.selectItem('segment', seg.id);

    // Mostrar guía de área segura
    this.updateSafeAreaGuideVisibility();

    // Feedback en cursor
    if (this.container) this.container.classList.add('dragging-subtitle');
  }

  onWindowMouseMove(e) {
    if (!this.isDragging) return;
    this.handleDragMove(e.clientX, e.clientY);
  }

  onWindowTouchMove(e) {
    if (!this.isDragging || e.touches.length !== 1) return;
    e.preventDefault();
    const touch = e.touches[0];
    this.handleDragMove(touch.clientX, touch.clientY);
  }

  handleDragMove(clientX, clientY) {
    if (!this.isDragging || !this.dragSegment || !this.container) return;

    const rect = this.container.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;

    const deltaX = clientX - this.dragStartX;
    const deltaY = clientY - this.dragStartY;

    const pctDeltaX = (deltaX / rect.width) * 100;
    const pctDeltaY = (deltaY / rect.height) * 100;

    const newX = Math.max(0, Math.min(100, Math.round(this.initialPosX + pctDeltaX)));
    const newY = Math.max(0, Math.min(100, Math.round(this.initialPosY + pctDeltaY)));

    this.currentDragX = newX;
    this.currentDragY = newY;

    // Emitir coordenadas para sincronizar sliders del panel editor en tiempo real
    appState.emit('subtitlePositionDragged', {
      segId: this.dragSegment.id,
      posX: newX,
      posY: newY
    });

    // Actualizar estilo en memoria viva (sin pushHistory en cada pixel)
    appState.updateSegmentSubtitleStyle(this.dragSegment.id, {
      positionX: newX,
      positionY: newY
    }, false);

    // Re-renderizar fotograma de vista previa
    this.render(appState.state.playback.currentTime);
  }

  onWindowMouseUp(e) {
    if (this.isDragging) {
      this.finishDrag();
    }
  }

  onWindowTouchEnd(e) {
    if (this.isDragging) {
      this.finishDrag();
    }
  }

  finishDrag() {
    if (!this.isDragging || !this.dragSegment) return;
    this.isDragging = false;

    if (this.container) this.container.classList.remove('dragging-subtitle');

    // Registrar snapshot en el historial Undo/Redo al finalizar el arrastre
    appState.updateSegmentSubtitleStyle(this.dragSegment.id, {
      positionX: this.currentDragX,
      positionY: this.currentDragY
    }, true);

    this.dragSegment = null;
    this.updateSafeAreaGuideVisibility();
    this.render(appState.state.playback.currentTime);
  }
}

// Instancia global en navegador
if (typeof window !== 'undefined') {
  window.SubtitleOverlayController = SubtitleOverlayController;
}
