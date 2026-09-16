/**
 * LSEC Studio 2.1.1 — Línea de Tiempo Compacta (3 Capas Base + Avanzadas)
 * 
 * Capas Base:
 * 1. Audio Waveform & Transcripción (ASR)
 * 2. Glosas LSEC (Secuencia gramatical)
 * 3. Revisiones humanas e incidencias
 * 
 * Capas Avanzadas (Opcionales):
 * 4. Subtítulos CC
 * 5. Bloques Discursivos (RST)
 * 6. Expresiones No Manuales
 * 7. Espacio / Loci
 * 8. Incidencias Técnicas
 */

class MultiTrackTimelineController {
  constructor(containerId = 'timeline-view-wrap') {
    this.container = document.getElementById(containerId);
    this.scrollArea = document.getElementById('timeline-tracks-scrollable');
    this.tracksContent = document.getElementById('timeline-tracks-content');
    this.rulerBar = document.getElementById('timeline-ruler-bar');
    this.waveformCanvas = document.getElementById('timeline-waveform-canvas');
    this.waveformCtx = this.waveformCanvas ? this.waveformCanvas.getContext('2d') : null;
    this.mainPlayhead = document.getElementById('timeline-main-playhead');
    
    this.zoomSlider = document.getElementById('timeline-zoom-slider');
    this.toggleAdvancedBtn = document.getElementById('btn-toggle-advanced-layers');

    this.prevErrBtn = document.getElementById('btn-timeline-prev-error');
    this.nextErrBtn = document.getElementById('btn-timeline-next-error');
    this.prevSegBtn = document.getElementById('btn-timeline-prev-seg');
    this.nextSegBtn = document.getElementById('btn-timeline-next-seg');

    this.pxPerSecond = 45; // Base: 45px por segundo
    this.isDraggingPlayhead = false;
    this.sentenceUnits = [];
    this.dragState = {
      active: false,
      glossId: null,
      sourceSentenceId: null,
      draggedPill: null,
      placeholder: null
    };

    this.init();
    this.subscribeState();
  }

  init() {
    // 1. Zoom
    if (this.zoomSlider) {
      this.zoomSlider.addEventListener('input', (e) => {
        const zoom = parseInt(e.target.value, 10);
        this.pxPerSecond = Math.max(15, Math.min(200, (zoom / 100) * 45));
        this.render();
      });
    }

    // 2. Toggle Capas Avanzadas
    if (this.toggleAdvancedBtn) {
      this.toggleAdvancedBtn.addEventListener('click', () => {
        appState.toggleAdvancedLayers();
      });
    }

    // 3. Navegación
    if (this.prevErrBtn) this.prevErrBtn.addEventListener('click', () => this.jumpRelativeError(-1));
    if (this.nextErrBtn) this.nextErrBtn.addEventListener('click', () => this.jumpRelativeError(1));
    if (this.prevSegBtn) this.prevSegBtn.addEventListener('click', () => this.jumpRelativeSegment(-1));
    if (this.nextSegBtn) this.nextSegBtn.addEventListener('click', () => this.jumpRelativeSegment(1));

    // 4. Arrastre de cabezal sobre la línea de tiempo
    if (this.scrollArea) {
      const handleScrub = (e) => {
        const rect = this.scrollArea.getBoundingClientRect();
        const clickX = e.clientX - rect.left + this.scrollArea.scrollLeft;
        const targetSec = clickX / this.pxPerSecond;
        appState.setCurrentTime(targetSec, 'timeline_scrub');
      };

      this.scrollArea.addEventListener('mousedown', (e) => {
        this.isDraggingPlayhead = true;
        handleScrub(e);
      });

      window.addEventListener('mousemove', (e) => {
        if (this.isDraggingPlayhead) handleScrub(e);
      });

      window.addEventListener('mouseup', () => {
        this.isDraggingPlayhead = false;
      });
    }

    // 5. Cancelación global de Drag & Drop con Escape
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.dragState && this.dragState.active) {
        this.cancelDrag();
      }
    });
  }

  subscribeState() {
    appState.subscribe('timeupdate', ({ time }) => {
      this.updatePlayheadPosition(time);
    });

    appState.subscribe('projectLoaded', () => {
      this.render();
    });

    appState.subscribe('segmentsChanged', () => {
      this.render();
    });

    appState.subscribe('glossesChanged', () => {
      this.render();
    });

    appState.subscribe('sentenceUpdated', () => {
      this.render();
    });

    appState.subscribe('selectionChanged', (selection) => {
      this.updateSelectionHighlight(selection);
    });

    appState.subscribe('advancedLayersToggled', (show) => {
      this.applyAdvancedLayersVisibility(show);
      this.render();
    });

    this.render();
  }

  applyAdvancedLayersVisibility(show) {
    if (this.toggleAdvancedBtn) {
      this.toggleAdvancedBtn.textContent = show ? 'Ocultar capas avanzadas ▴' : 'Capas avanzadas ▾';
    }

    const advancedCells = document.querySelectorAll('.advanced-layer');
    advancedCells.forEach(el => {
      el.style.display = show ? 'flex' : 'none';
    });
  }

  renderAllTracks() {
    this.render();
  }

  renderSegments() {
    this.render();
  }

  render() {
    if (!this.scrollArea) return;
    const project = appState.state.project;
    const duration = (project && project.media_info) ? project.media_info.duration_seconds : 48.850;
    const totalWidth = Math.max(800, duration * this.pxPerSecond);

    if (this.tracksContent) {
      this.tracksContent.style.width = `${totalWidth}px`;
    }

    this.drawRuler(duration, totalWidth);
    this.drawWaveform(totalWidth);

    if (!project) return;

    // Construcción de unidades de frase completas (agrupación de presentación no destructiva)
    this.sentenceUnits = (typeof SentenceGroupingEngine !== 'undefined')
      ? SentenceGroupingEngine.buildSentenceUnits(project)
      : this.fallbackSentenceUnits(project);

    // Fila 1: Frases completas en español
    this.renderTrackSentencesES(this.sentenceUnits);

    // Fila 2: Secuencia completa de glosas LSEC directamente debajo
    this.renderTrackSentencesGlosses(this.sentenceUnits);

    // Pista 3: Revisiones e incidencias
    this.renderTrackReviews(project.segments || [], this.sentenceUnits);

    // Pistas avanzadas (4-8)
    if (appState.state.workspace.showAdvancedLayers) {
      this.renderTrackSubtitles(project.segments || []);
      this.renderTrackDiscourse(project.discourse_blocks || []);
      this.renderTrackNonManual(project.non_manual_spans || []);
      this.renderTrackSpatial(project.spatial_operations || []);
      this.renderTrackIssues(project.unresolved_items || []);
    }

    // Actualizar resaltados acordes al tiempo y selección actual
    const curTime = appState.state.playback?.currentTime || 0;
    this.updateActiveSentenceHighlight(curTime);
    this.updateSelectionHighlight(appState.state.playback?.selectedItem || null);
  }

  drawRuler(duration, totalWidth) {
    if (!this.rulerBar) return;
    let canvas = this.rulerBar.querySelector('canvas');
    if (!canvas) {
      canvas = document.createElement('canvas');
      this.rulerBar.innerHTML = '';
      this.rulerBar.appendChild(canvas);
    }

    canvas.width = totalWidth;
    canvas.height = 24;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, totalWidth, 24);

    ctx.fillStyle = '#74796F';
    ctx.font = '10px JetBrains Mono, monospace';
    ctx.strokeStyle = 'rgba(242, 241, 236, 0.12)';
    ctx.lineWidth = 1;

    const secInterval = this.pxPerSecond < 30 ? 5 : (this.pxPerSecond < 60 ? 2 : 1);

    for (let sec = 0; sec <= duration; sec += secInterval) {
      const x = sec * this.pxPerSecond;
      ctx.beginPath();
      ctx.moveTo(x, 14);
      ctx.lineTo(x, 24);
      ctx.stroke();

      const mins = Math.floor(sec / 60);
      const secs = Math.floor(sec % 60);
      const label = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
      ctx.fillText(label, x + 3, 11);
    }
  }

  drawWaveform(totalWidth) {
    if (!this.waveformCanvas) return;
    this.waveformCanvas.width = totalWidth;
    this.waveformCanvas.height = 32;
    const ctx = this.waveformCanvas.getContext('2d');
    ctx.clearRect(0, 0, totalWidth, 32);

    ctx.fillStyle = 'rgba(183, 211, 107, 0.35)';
    const barWidth = 3;
    const barGap = 2;
    const totalBars = Math.floor(totalWidth / (barWidth + barGap));

    for (let i = 0; i < totalBars; i++) {
      const h = Math.max(3, Math.sin(i * 0.25) * 12 + Math.cos(i * 0.7) * 8 + 10);
      const x = i * (barWidth + barGap);
      const y = (32 - h) / 2;
      ctx.fillRect(x, y, barWidth, h);
    }
  }

  /**
   * PISTA 1: Frases completas en español.
   * Cada frase abarca el intervalo temporal general y muestra el texto hasta la puntuación final.
   */
  renderTrackSentencesES(sentenceUnits) {
    const lane = document.getElementById('lane-track-1');
    if (!lane) return;
    const existingBlocks = lane.querySelectorAll('.timeline-block-item');
    existingBlocks.forEach(b => b.remove());

    sentenceUnits.forEach(sentence => {
      const left = sentence.start_seconds * this.pxPerSecond;
      const width = Math.max(32, (sentence.end_seconds - sentence.start_seconds) * this.pxPerSecond - 2);

      const block = document.createElement('div');
      const isReview = sentence.status === 'REVIEW_REQUIRED';
      block.className = `timeline-block-item timeline-sentence-item timeline-sentence-es ${isReview ? 'issue' : ''}`;
      block.setAttribute('data-sentence-id', sentence.id);
      block.style.left = `${left}px`;
      block.style.width = `${width}px`;

      const subsegCountBadge = sentence.segments.length > 1
        ? `<span class="sentence-seg-count" title="Contiene ${sentence.segments.length} segmentos: ${sentence.segment_ids.join(', ')}">${sentence.segments.length} segs</span>`
        : '';

      const reviewIcon = isReview
        ? `<span class="sentence-alert-icon" title="${this.escapeHTML(sentence.review_reasons.join(' | '))}">⚠</span>`
        : '';

      block.innerHTML = `
        <span class="sentence-index-badge">F${sentence.index}</span>
        ${subsegCountBadge}
        <span class="sentence-text-content">${this.escapeHTML(sentence.text)}</span>
        ${reviewIcon}
      `;

      block.title = `Frase ${sentence.index} [${this.formatTime(sentence.start_seconds)} - ${this.formatTime(sentence.end_seconds)}]\n${sentence.segments.length} segmento(s): ${sentence.segment_ids.join(', ')}\n"${sentence.text}"`;

      block.addEventListener('click', (e) => {
        e.stopPropagation();
        this.onSentenceClick(sentence);
      });

      block.addEventListener('mouseenter', () => this.setSentenceHoverState(sentence.id, true));
      block.addEventListener('mouseleave', () => this.setSentenceHoverState(sentence.id, false));

      lane.appendChild(block);
    });
  }

  /**
   * PISTA 2: Secuencia completa de glosas LSEC correspondiente.
   * Fila interactiva con soporte para arrastrar y soltar (Drag & Drop), reordenamiento
   * intra-frase, movimiento inter-frases, atajos de teclado y acciones rápidas.
   */
  renderTrackSentencesGlosses(sentenceUnits) {
    const lane = document.getElementById('lane-track-2');
    if (!lane) return;
    lane.innerHTML = '';

    sentenceUnits.forEach(sentence => {
      const left = sentence.start_seconds * this.pxPerSecond;
      const width = Math.max(48, (sentence.end_seconds - sentence.start_seconds) * this.pxPerSecond - 2);

      const block = document.createElement('div');
      const isReview = sentence.status === 'REVIEW_REQUIRED' || sentence.has_review;
      block.className = `timeline-block-item timeline-sentence-item timeline-sentence-gloss ${isReview ? 'issue' : ''}`;
      block.setAttribute('data-sentence-id', sentence.id);
      block.style.left = `${left}px`;
      block.style.width = `${width}px`;

      // Renderizar los chips de glosas LSEC en secuencia interactiva
      let glossesHtml = '';
      if (sentence.glosses && sentence.glosses.length > 0) {
        glossesHtml = sentence.glosses.map((g, gIdx) => {
          const isFs = g.is_fingerspelling || g.gloss_type === 'DACTILOLOGÍA' || (g.gloss && g.gloss.includes('-'));
          const isPause = g.is_pause || g.gloss_type === 'PAUSA' || g.gloss === '[PAUSA]';
          const isGReview = g.status === 'AUDIO_REVIEW' || g.status === 'BLOCKED' || g.status === 'REVIEW_REQUIRED';
          const cls = `sentence-gloss-pill ${isFs ? 'dactilo' : ''} ${isPause ? 'is-pause' : ''} ${isGReview ? 'issue' : ''}`;
          const label = isPause ? '⏸ PAUSA' : (g.gloss || g.lemma);
          return `
            <span class="${cls}" 
                  draggable="true" 
                  tabindex="0"
                  role="button"
                  data-gloss-id="${g.id}" 
                  data-sentence-id="${sentence.id}"
                  data-gloss-index="${gIdx}"
                  aria-label="Glosa ${g.gloss}, orden ${gIdx + 1}"
                  title="${this.escapeHTML(g.gloss)} (${g.gloss_type || 'SEÑA'})${g.notes ? ': ' + this.escapeHTML(g.notes) : ''}\n[Arrastrar para reordenar o mover entre frases | Alt+←/→ mover | Del eliminar]">
              <span class="gloss-pill-label">${this.escapeHTML(label)}</span>
              <button class="gloss-pill-action btn-pill-dup" data-gloss-id="${g.id}" title="Duplicar glosa" tabindex="-1">⧉</button>
              <button class="gloss-pill-action btn-pill-del" data-gloss-id="${g.id}" title="Eliminar glosa" tabindex="-1">×</button>
            </span>
          `;
        }).join('');
      } else if (sentence.gloss_sequence && sentence.gloss_sequence.length > 0) {
        glossesHtml = sentence.gloss_sequence.map((gName, gIdx) => {
          return `
            <span class="sentence-gloss-pill" 
                  draggable="true" 
                  tabindex="0"
                  data-gloss-id="g_${sentence.id}_${gIdx}" 
                  data-sentence-id="${sentence.id}"
                  data-gloss-index="${gIdx}">
              <span class="gloss-pill-label">${this.escapeHTML(gName)}</span>
            </span>
          `;
        }).join('');
      } else {
        glossesHtml = '<span class="sentence-gloss-empty">[Sin glosas]</span>';
      }

      const reviewBadge = isReview
        ? `<span class="sentence-alert-icon" title="${this.escapeHTML((sentence.review_reasons || []).join(' | '))}">⚠</span>`
        : '';

      block.innerHTML = `
        <div class="sentence-gloss-header-row">
          <span class="sentence-index-badge gloss-badge">G${sentence.index}</span>
          ${reviewBadge}
          <div class="sentence-quick-tools">
            <button class="btn-sentence-quick-add" data-action="add-gloss" data-sentence-id="${sentence.id}" title="Añadir glosa a la Frase ${sentence.index}">+ Glosa</button>
            <button class="btn-sentence-quick-add" data-action="add-pause" data-sentence-id="${sentence.id}" title="Insertar pausa lingüística">+ Pausa</button>
          </div>
        </div>
        <div class="sentence-glosses-wrapper" data-sentence-id="${sentence.id}">${glossesHtml}</div>
      `;

      block.title = `Glosas Frase ${sentence.index} (${sentence.glosses ? sentence.glosses.length : sentence.gloss_sequence.length} glosas):\n${sentence.gloss_sequence.join(' ')}`;

      // Contenedor interno de glosas
      const wrapper = block.querySelector('.sentence-glosses-wrapper');

      // --------------------------------------------------------
      // Drag and Drop (Arrastrar y Soltar)
      // --------------------------------------------------------
      const pills = block.querySelectorAll('.sentence-gloss-pill');
      pills.forEach((pill, idx) => {
        pill.addEventListener('dragstart', (e) => {
          const gId = pill.dataset.glossId;
          this.dragState.active = true;
          this.dragState.glossId = gId;
          this.dragState.sourceSentenceId = sentence.id;
          this.dragState.draggedPill = pill;

          pill.classList.add('is-dragging');
          e.dataTransfer.effectAllowed = 'move';
          try {
            e.dataTransfer.setData('text/plain', JSON.stringify({ glossId: gId, sentenceId: sentence.id }));
          } catch (err) {}

          const ph = document.createElement('div');
          ph.className = 'gloss-drag-placeholder';
          ph.textContent = '⇊';
          this.dragState.placeholder = ph;
        });

        pill.addEventListener('dragend', () => {
          this.cleanDragState();
        });

        // Clic en acciones individuales del chip
        const dupBtn = pill.querySelector('.btn-pill-dup');
        if (dupBtn) {
          dupBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            appState.duplicateGloss(sentence.id, pill.dataset.glossId);
          });
        }

        const delBtn = pill.querySelector('.btn-pill-del');
        if (delBtn) {
          delBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            appState.deleteGloss(sentence.id, pill.dataset.glossId);
          });
        }

        // Selección al hacer clic en el chip
        pill.addEventListener('click', (e) => {
          e.stopPropagation();
          const gId = pill.dataset.glossId;
          const targetG = (sentence.glosses || []).find(g => g.id === gId) || (appState.state.project?.glosses || []).find(g => g.id === gId);
          if (targetG) {
            const gStart = targetG.start_seconds !== undefined ? targetG.start_seconds : (targetG.start || sentence.start_seconds);
            appState.setCurrentTime(gStart, 'timeline_gloss_click');
            appState.selectItem('gloss', targetG.id, targetG);
          }
        });

        // Controles de accesibilidad por teclado
        pill.addEventListener('keydown', (e) => {
          const gId = pill.dataset.glossId;
          const curIdx = parseInt(pill.dataset.glossIndex, 10);

          if (e.altKey && e.key === 'ArrowLeft') {
            e.preventDefault();
            e.stopPropagation();
            appState.reorderGlossInSentence(sentence.id, gId, Math.max(0, curIdx - 1));
          } else if (e.altKey && e.key === 'ArrowRight') {
            e.preventDefault();
            e.stopPropagation();
            appState.reorderGlossInSentence(sentence.id, gId, curIdx + 1);
          } else if (e.altKey && (e.key === 'ArrowUp' || (e.shiftKey && e.key === 'ArrowLeft'))) {
            // Mover a la frase anterior
            e.preventDefault();
            e.stopPropagation();
            const allSentences = appState.getSentenceUnits();
            const sIdx = allSentences.findIndex(u => u.id === sentence.id);
            if (sIdx > 0) {
              const targetS = allSentences[sIdx - 1];
              appState.moveGlossBetweenSentences(sentence.id, targetS.id, gId, -1);
            }
          } else if (e.altKey && (e.key === 'ArrowDown' || (e.shiftKey && e.key === 'ArrowRight'))) {
            // Mover a la frase siguiente
            e.preventDefault();
            e.stopPropagation();
            const allSentences = appState.getSentenceUnits();
            const sIdx = allSentences.findIndex(u => u.id === sentence.id);
            if (sIdx >= 0 && sIdx < allSentences.length - 1) {
              const targetS = allSentences[sIdx + 1];
              appState.moveGlossBetweenSentences(sentence.id, targetS.id, gId, 0);
            }
          } else if (e.key === 'Delete' || e.key === 'Backspace') {
            e.preventDefault();
            e.stopPropagation();
            appState.deleteGloss(sentence.id, gId);
          } else if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            e.stopPropagation();
            const targetG = (sentence.glosses || []).find(g => g.id === gId);
            if (targetG) appState.selectItem('gloss', targetG.id, targetG);
          }
        });
      });

      // Eventos Dragover y Drop sobre el contenedor de la frase
      if (wrapper) {
        wrapper.addEventListener('dragover', (e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = 'move';
          block.classList.add('drag-over-target');

          if (!this.dragState.placeholder) return;

          const nonDraggingPills = Array.from(wrapper.querySelectorAll('.sentence-gloss-pill:not(.is-dragging)'));
          let insertBeforeEl = null;

          for (const p of nonDraggingPills) {
            const rect = p.getBoundingClientRect();
            const midX = rect.left + rect.width / 2;
            if (e.clientX < midX) {
              insertBeforeEl = p;
              break;
            }
          }

          if (insertBeforeEl) {
            wrapper.insertBefore(this.dragState.placeholder, insertBeforeEl);
          } else {
            wrapper.appendChild(this.dragState.placeholder);
          }
        });

        wrapper.addEventListener('dragleave', (e) => {
          if (!block.contains(e.relatedTarget)) {
            block.classList.remove('drag-over-target');
          }
        });

        wrapper.addEventListener('drop', (e) => {
          e.preventDefault();
          e.stopPropagation();
          block.classList.remove('drag-over-target');

          if (!this.dragState.active) return;

          const { glossId, sourceSentenceId, placeholder } = this.dragState;
          let targetIndex = 0;

          if (placeholder && placeholder.parentNode === wrapper) {
            const children = Array.from(wrapper.children);
            for (const child of children) {
              if (child === placeholder) break;
              if (child.classList.contains('sentence-gloss-pill') && !child.classList.contains('is-dragging')) {
                targetIndex++;
              }
            }
          } else {
            targetIndex = (sentence.glosses || []).length;
          }

          this.cleanDragState();

          if (sourceSentenceId === sentence.id) {
            appState.reorderGlossInSentence(sentence.id, glossId, targetIndex);
          } else {
            appState.moveGlossBetweenSentences(sourceSentenceId, sentence.id, glossId, targetIndex);
          }
        });
      }

      // Acciones rápidas de cabecera (+ Glosa, + Pausa)
      const quickBtns = block.querySelectorAll('.btn-sentence-quick-add');
      quickBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const action = btn.dataset.action;
          if (action === 'add-gloss') {
            const input = prompt(`Añadir glosa a la Frase ${sentence.index}:`, 'NUEVA_GLOSA');
            if (input && input.trim()) {
              appState.addGlossToSentence(sentence.id, { gloss: input.trim() });
            }
          } else if (action === 'add-pause') {
            appState.insertPause(sentence.id);
          }
        });
      });

      // Clic en la frase completa (fuera de chips o botones)
      block.addEventListener('click', (e) => {
        if (!e.target.closest('.sentence-gloss-pill') && !e.target.closest('.btn-sentence-quick-add')) {
          e.stopPropagation();
          this.onSentenceClick(sentence);
        }
      });

      block.addEventListener('mouseenter', () => this.setSentenceHoverState(sentence.id, true));
      block.addEventListener('mouseleave', () => this.setSentenceHoverState(sentence.id, false));

      lane.appendChild(block);
    });
  }

  cleanDragState() {
    if (this.dragState.placeholder && this.dragState.placeholder.parentNode) {
      this.dragState.placeholder.parentNode.removeChild(this.dragState.placeholder);
    }
    if (this.dragState.draggedPill) {
      this.dragState.draggedPill.classList.remove('is-dragging');
    }
    document.querySelectorAll('.timeline-sentence-gloss.drag-over-target').forEach(el => {
      el.classList.remove('drag-over-target');
    });
    this.dragState = {
      active: false,
      glossId: null,
      sourceSentenceId: null,
      draggedPill: null,
      placeholder: null
    };
  }

  cancelDrag() {
    this.cleanDragState();
  }

  /**
   * Alias de compatibilidad hacia atrás
   */
  renderTrackSegments(segments) {
    if (this.sentenceUnits && this.sentenceUnits.length > 0) {
      this.renderTrackSentencesES(this.sentenceUnits);
    }
  }

  renderTrackGlosses(glosses) {
    if (this.sentenceUnits && this.sentenceUnits.length > 0) {
      this.renderTrackSentencesGlosses(this.sentenceUnits);
    }
  }

  /**
   * PISTA 3: Revisiones e incidencias
   */
  renderTrackReviews(segments, sentenceUnits = []) {
    const lane = document.getElementById('lane-track-3');
    if (!lane) return;
    lane.innerHTML = '';

    // Si tenemos frases con revisión, las priorizamos o combinamos
    const items = sentenceUnits.length > 0 ? sentenceUnits : segments;

    items.forEach(it => {
      const left = it.start_seconds * this.pxPerSecond;
      const width = Math.max(16, (it.end_seconds - it.start_seconds) * this.pxPerSecond - 2);

      const block = document.createElement('div');
      const isReview = it.status === 'REVIEW_REQUIRED';
      block.className = `timeline-block-item ${isReview ? 'issue' : ''}`;
      block.style.left = `${left}px`;
      block.style.width = `${width}px`;
      block.textContent = it.status_label || it.status;
      block.title = `${it.status_label || it.status}: ${it.review_reasons ? it.review_reasons.join(' | ') : it.text || ''}`;

      block.addEventListener('click', (e) => {
        e.stopPropagation();
        appState.setCurrentTime(it.start_seconds, 'timeline_review_click');
        const type = it.segments ? 'sentence' : 'segment';
        appState.selectItem(type, it.id, it);
      });

      lane.appendChild(block);
    });
  }

  renderTrackSubtitles(segments) {
    const lane = document.getElementById('lane-track-4');
    if (!lane) return;
    lane.innerHTML = '';
    segments.forEach(s => {
      const left = s.start_seconds * this.pxPerSecond;
      const width = Math.max(16, (s.end_seconds - s.start_seconds) * this.pxPerSecond - 2);
      const block = document.createElement('div');
      block.className = 'timeline-block-item';
      block.style.left = `${left}px`;
      block.style.width = `${width}px`;
      block.textContent = `CC: ${s.normalized_text}`;
      lane.appendChild(block);
    });
  }

  renderTrackDiscourse(blocks) {
    const lane = document.getElementById('lane-track-5');
    if (!lane) return;
    lane.innerHTML = '';
    blocks.forEach((b, idx) => {
      const left = (b.start_seconds || idx * 5.0) * this.pxPerSecond;
      const width = Math.max(20, ((b.end_seconds || (idx + 1) * 5.0) - (b.start_seconds || idx * 5.0)) * this.pxPerSecond - 2);
      const block = document.createElement('div');
      block.className = 'timeline-block-item';
      block.style.left = `${left}px`;
      block.style.width = `${width}px`;
      block.textContent = b.label || b.topic || `RST ${idx + 1}`;
      lane.appendChild(block);
    });
  }

  renderTrackNonManual(spans) {
    const lane = document.getElementById('lane-track-6');
    if (!lane) return;
    lane.innerHTML = '';
    spans.forEach(s => {
      const left = (s.start_seconds || 0) * this.pxPerSecond;
      const width = Math.max(16, ((s.end_seconds || 2) - (s.start_seconds || 0)) * this.pxPerSecond - 2);
      const block = document.createElement('div');
      block.className = 'timeline-block-item';
      block.style.left = `${left}px`;
      block.style.width = `${width}px`;
      block.textContent = s.facial_expression || s.expression || 'Facial';
      lane.appendChild(block);
    });
  }

  renderTrackSpatial(ops) {
    const lane = document.getElementById('lane-track-7');
    if (!lane) return;
    lane.innerHTML = '';
    ops.forEach(op => {
      const left = (op.time_seconds || 0) * this.pxPerSecond;
      const block = document.createElement('div');
      block.className = 'timeline-block-item';
      block.style.left = `${left}px`;
      block.style.width = '30px';
      block.textContent = op.target_space || 'Locus';
      lane.appendChild(block);
    });
  }

  renderTrackIssues(issues) {
    const lane = document.getElementById('lane-track-8');
    if (!lane) return;
    lane.innerHTML = '';
    issues.forEach(it => {
      const left = (it.time_seconds || 0) * this.pxPerSecond;
      const block = document.createElement('div');
      block.className = 'timeline-block-item issue';
      block.style.left = `${left}px`;
      block.style.width = '40px';
      block.textContent = 'Alerta';
      lane.appendChild(block);
    });
  }

  // ============================================================
  // SINCRONIZACIÓN Y NAVEGACIÓN
  // ============================================================

  updatePlayheadPosition(currentTime) {
    if (this.mainPlayhead) {
      const x = currentTime * this.pxPerSecond;
      this.mainPlayhead.style.left = `${x}px`;
    }
    this.updateActiveSentenceHighlight(currentTime);
  }

  /**
   * Resalta sincronizadamente ambas filas vinculadas (español y glosas) de la frase activa
   */
  updateActiveSentenceHighlight(currentTime) {
    if (!this.sentenceUnits || this.sentenceUnits.length === 0) return;
    const activeSentence = this.sentenceUnits.find(s => currentTime >= s.start_seconds && currentTime <= s.end_seconds);

    const allSentenceEls = this.container ? this.container.querySelectorAll('.timeline-sentence-item') : [];
    allSentenceEls.forEach(el => {
      const sId = el.getAttribute('data-sentence-id');
      const isActive = activeSentence && sId === activeSentence.id;
      el.classList.toggle('active', !!isActive);
    });
  }

  /**
   * Resalta los elementos seleccionados en la línea de tiempo
   */
  updateSelectionHighlight(selectedItem) {
    if (!this.container) return;
    const allSentenceEls = this.container.querySelectorAll('.timeline-sentence-item');
    allSentenceEls.forEach(el => el.classList.remove('selected'));

    if (!selectedItem) return;
    let targetSentenceId = null;

    if (selectedItem.type === 'sentence') {
      targetSentenceId = selectedItem.id;
    } else if (selectedItem.type === 'segment') {
      const found = (this.sentenceUnits || []).find(su => su.segment_ids && su.segment_ids.includes(selectedItem.id));
      if (found) targetSentenceId = found.id;
    } else if (selectedItem.type === 'gloss') {
      const found = (this.sentenceUnits || []).find(su => su.glosses && su.glosses.some(g => g.id === selectedItem.id));
      if (found) targetSentenceId = found.id;
    }

    if (targetSentenceId) {
      const targetEls = this.container.querySelectorAll(`[data-sentence-id="${targetSentenceId}"]`);
      targetEls.forEach(el => el.classList.add('selected'));
    }
  }

  onSentenceClick(sentence) {
    appState.setCurrentTime(sentence.start_seconds, 'timeline_sentence_click');
    appState.selectItem('sentence', sentence.id, sentence);
  }

  setSentenceHoverState(sentenceId, isHovered) {
    if (!this.container) return;
    const linkedItems = this.container.querySelectorAll(`[data-sentence-id="${sentenceId}"]`);
    linkedItems.forEach(el => {
      el.classList.toggle('hovered-link', isHovered);
    });
  }

  jumpRelativeSegment(direction) {
    if (this.sentenceUnits && this.sentenceUnits.length > 0) {
      const units = this.sentenceUnits;
      const cur = appState.state.playback.currentTime;
      let target = null;
      if (direction > 0) {
        target = units.find(u => u.start_seconds > cur + 0.05) || units[units.length - 1];
      } else {
        const prevs = units.filter(u => u.start_seconds < cur - 0.05);
        target = prevs.length > 0 ? prevs[prevs.length - 1] : units[0];
      }
      if (target) {
        appState.setCurrentTime(target.start_seconds, 'nav_button');
        appState.selectItem('sentence', target.id, target);
      }
      return;
    }

    const segs = appState.state.project?.segments || [];
    if (segs.length === 0) return;
    const cur = appState.state.playback.currentTime;
    let target = null;
    if (direction > 0) {
      target = segs.find(s => s.start_seconds > cur + 0.05) || segs[segs.length - 1];
    } else {
      const prevs = segs.filter(s => s.start_seconds < cur - 0.05);
      target = prevs.length > 0 ? prevs[prevs.length - 1] : segs[0];
    }
    if (target) {
      appState.setCurrentTime(target.start_seconds, 'nav_button');
      appState.selectItem('segment', target.id, target);
    }
  }

  jumpRelativeError(direction) {
    const errorUnits = (this.sentenceUnits && this.sentenceUnits.length > 0)
      ? this.sentenceUnits.filter(u => u.status === 'REVIEW_REQUIRED')
      : (appState.state.project?.segments || []).filter(s => s.status === 'REVIEW_REQUIRED');

    if (errorUnits.length === 0) return;
    const cur = appState.state.playback.currentTime;
    let target = null;
    if (direction > 0) {
      target = errorUnits.find(s => s.start_seconds > cur + 0.05) || errorUnits[0];
    } else {
      const prevs = errorUnits.filter(s => s.start_seconds < cur - 0.05);
      target = prevs.length > 0 ? prevs[prevs.length - 1] : errorUnits[errorUnits.length - 1];
    }
    if (target) {
      const type = target.segments ? 'sentence' : 'segment';
      appState.setCurrentTime(target.start_seconds, 'nav_error_button');
      appState.selectItem(type, target.id, target);
    }
  }

  fallbackSentenceUnits(project) {
    const segs = project.segments || [];
    return segs.map((s, idx) => ({
      id: `sentence_${String(idx + 1).padStart(2, '0')}`,
      index: idx + 1,
      text: s.normalized_text || s.original_text || '',
      start_seconds: s.start_seconds !== undefined ? s.start_seconds : (s.start_time || 0),
      end_seconds: s.end_seconds !== undefined ? s.end_seconds : (s.end_time || 0),
      duration: (s.end_seconds || 0) - (s.start_seconds || 0),
      segments: [s],
      segment_ids: [s.id],
      proposition_ids: [s.proposition_id || `p${idx + 1}`],
      discourse_block_ids: [s.block_id || 0],
      words: s.words || [],
      glosses: s.glosses || [],
      gloss_sequence: s.gloss_sequence || [],
      status: s.status || 'VALIDATED',
      status_label: s.status_label || s.status,
      has_review: s.status === 'REVIEW_REQUIRED',
      review_reasons: s.review_reason ? [s.review_reason] : []
    }));
  }

  formatTime(seconds) {
    if (seconds === undefined || seconds === null || isNaN(seconds)) return '00:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 10);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${ms}`;
  }

  escapeHTML(str) {
    if (!str || typeof str !== 'string') return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}

// Exportación global
window.MultiTrackTimelineController = MultiTrackTimelineController;

