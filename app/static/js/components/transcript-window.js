/**
 * LSEC Studio — Controlador de la Ventana 1 («1. Transcripción con Whisper»)
 * Gestiona la vista dual de la transcripción:
 *  - Modo 'unified' (por defecto): Todo el texto continuo dentro de un único recuadro
 *    interactivo. Al hacer clic en cualquier frase, cambia a la vista detallada por frase
 *    y enfoca directamente la oración seleccionada.
 *  - Modo 'cards': Cada frase en su propio recuadro editable con marcas de tiempo
 *    [mm:ss - mm:ss], porcentaje de fidelidad ASR Whisper y acciones.
 */

class TranscriptWindowController {
  constructor(options = {}) {
    this.onProceedToStep2 = options.onProceedToStep2 || null;
    this.onRunWhisper = options.onRunWhisper || null;

    this.segmentsContainer = document.getElementById('transcript-segments-container');
    this.countBadge = document.getElementById('transcript-count-badge');
    this.statusLabel = document.getElementById('whisper-status-label');
    this.waveformCanvas = document.getElementById('whisper-waveform-canvas');
    this.btnToggleView = document.getElementById('btn-toggle-transcript-view');
    this.btnAddSegment = document.getElementById('btn-add-transcript-segment');
    this.btnTranscribe = document.getElementById('btn-step1-transcribe');
    this.btnProcessLsec = document.getElementById('btn-step1-process-lsec');

    // Por defecto todo el texto aparece dentro de un solo recuadro ('unified')
    this.viewMode = 'unified';
    this.focusedSegmentId = null;

    this.waveBars = this.generateWaveProfile(72);
    this.animFrameId = null;
    this.isExtracting = false;

    this.init();
  }

  init() {
    this.bindEvents();
    this.subscribeToStore();
    this.renderSegments();
    this.drawWaveform(0);
  }

  generateWaveProfile(count) {
    const bars = [];
    for (let i = 0; i < count; i++) {
      const base = 0.22 + 0.55 * Math.abs(Math.sin(i * 0.43) * Math.cos(i * 0.19));
      bars.push(Math.min(0.95, Math.max(0.16, base)));
    }
    return bars;
  }

  bindEvents() {
    if (this.btnToggleView) {
      this.btnToggleView.addEventListener('click', () => {
        this.setViewMode(this.viewMode === 'unified' ? 'cards' : 'unified');
      });
    }

    if (this.btnAddSegment) {
      this.btnAddSegment.addEventListener('click', () => this.handleAddSegment());
    }

    if (this.btnTranscribe) {
      this.btnTranscribe.addEventListener('click', () => {
        if (typeof this.onRunWhisper === 'function') {
          this.onRunWhisper();
        } else if (window.pipelineProcessor) {
          window.pipelineProcessor.runPipelineForCurrentVideo();
        }
      });
    }

    if (this.btnProcessLsec) {
      this.btnProcessLsec.addEventListener('click', () => {
        if (typeof this.onProceedToStep2 === 'function') {
          this.onProceedToStep2();
        } else if (typeof window.switchWizardStep === 'function') {
          window.switchWizardStep('traducir');
        }
      });
    }
  }

  setViewMode(mode, targetSegId = null) {
    this.viewMode = mode === 'cards' ? 'cards' : 'unified';
    this.focusedSegmentId = targetSegId || null;
    this.updateViewModeButton();
    this.renderSegments();

    if (this.viewMode === 'cards' && targetSegId && this.segmentsContainer) {
      requestAnimationFrame(() => {
        const targetCard = this.segmentsContainer.querySelector(
          `.transcript-seg-card[data-seg-id="${CSS.escape(String(targetSegId))}"]`
        );
        if (targetCard) {
          targetCard.classList.add('active');
          targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
          const textarea = targetCard.querySelector('.transcript-seg-input');
          if (textarea) {
            textarea.focus({ preventScroll: true });
          }
        }
      });
    }
  }

  updateViewModeButton() {
    if (!this.btnToggleView) return;
    if (this.viewMode === 'unified') {
      this.btnToggleView.textContent = 'Ver por Frases';
      this.btnToggleView.title = 'Cambiar a vista de recuadros individuales por oración';
    } else {
      this.btnToggleView.textContent = 'Ver Texto Unificado';
      this.btnToggleView.title = 'Volver a la vista de todo el texto en un solo recuadro';
    }
  }

  subscribeToStore() {
    if (typeof appState === 'undefined') return;

    appState.subscribe('projectLoaded', () => {
      this.waveBars = this.generateWaveProfile(72);
      // Al cargar un proyecto nuevo o transcribir con Whisper, iniciar en el recuadro único por defecto
      this.viewMode = 'unified';
      this.focusedSegmentId = null;
      this.updateViewModeButton();
      this.renderSegments();
      this.drawWaveform(appState.state.playback.currentTime || 0);
    });

    appState.subscribe('projectUpdated', () => this.renderSegments());
    appState.subscribe('segmentsChanged', () => this.renderSegments());
    appState.subscribe('segmentUpdated', () => this.updateCountBadge());

    appState.subscribe('timeChanged', (time) => {
      this.drawWaveform(time);
      this.highlightActiveSegmentByTime(time);
    });
  }

  setExtractingState(active, message = '') {
    this.isExtracting = Boolean(active);
    if (this.statusLabel && message) {
      this.statusLabel.textContent = message;
    }
    if (this.isExtracting) {
      this.startWaveformLoop();
    } else {
      this.stopWaveformLoop();
      const t = (typeof appState !== 'undefined' && appState.state?.playback?.currentTime) || 0;
      this.drawWaveform(t);
    }
  }

  startWaveformLoop() {
    if (this.animFrameId) return;
    const tick = () => {
      if (!this.isExtracting) return;
      this.drawWaveform(performance.now() / 450, true);
      this.animFrameId = requestAnimationFrame(tick);
    };
    this.animFrameId = requestAnimationFrame(tick);
  }

  stopWaveformLoop() {
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
  }

  drawWaveform(currentTime = 0, animateExtraction = false) {
    if (!this.waveformCanvas) return;
    const ctx = this.waveformCanvas.getContext('2d');
    if (!ctx) return;

    const width = this.waveformCanvas.width;
    const height = this.waveformCanvas.height;
    ctx.clearRect(0, 0, width, height);

    const playback = (typeof appState !== 'undefined' && appState.state?.playback) || {};
    const duration = Math.max(1, playback.duration || 18);
    const progress = animateExtraction
      ? ((currentTime % 10) / 10)
      : Math.min(1, Math.max(0, currentTime / duration));

    const barCount = this.waveBars.length;
    const gap = 3;
    const barWidth = Math.max(3, (width - gap * (barCount + 1)) / barCount);

    for (let i = 0; i < barCount; i++) {
      const ratio = i / barCount;
      let amp = this.waveBars[i];
      if (animateExtraction || playback.isPlaying) {
        amp = Math.min(0.96, Math.max(0.15, amp + 0.18 * Math.sin(currentTime * 6 + i * 0.5)));
      }
      const barH = Math.max(6, amp * (height - 12));
      const x = gap + i * (barWidth + gap);
      const y = (height - barH) / 2;

      ctx.fillStyle = ratio <= progress ? '#0284c7' : '#93c5fd';
      ctx.beginPath();
      if (ctx.roundRect) {
        ctx.roundRect(x, y, barWidth, barH, 3);
      } else {
        ctx.rect(x, y, barWidth, barH);
      }
      ctx.fill();
    }
  }

  formatTimeRange(start = 0, end = 0) {
    const fmt = (sec) => {
      const s = Math.max(0, Number(sec) || 0);
      const mins = Math.floor(s / 60);
      const rem = (s % 60).toFixed(1).padStart(4, '0');
      return `${String(mins).padStart(2, '0')}:${rem}`;
    };
    return `[${fmt(start)} - ${fmt(end)}]`;
  }

  updateCountBadge() {
    const segments = (typeof appState !== 'undefined' && appState.state?.project?.segments) || [];
    if (this.countBadge) {
      this.countBadge.textContent = `${segments.length} ${segments.length === 1 ? 'segmento' : 'segmentos'}`;
    }
  }

  renderSegments() {
    if (!this.segmentsContainer) return;
    const segments = (typeof appState !== 'undefined' && appState.state?.project?.segments) || [];
    const hasVideo = Boolean(
      (typeof appState !== 'undefined' && appState.state?.workspace?.videoLoaded) ||
      (window.pipelineProcessor && window.pipelineProcessor.cachedVideoFile)
    );
    this.updateCountBadge();
    this.updateViewModeButton();

    // Mostrar "Ver por Frases / Ver Texto Unificado" únicamente cuando existen segmentos
    if (this.btnToggleView) {
      this.btnToggleView.style.display = segments.length > 0 ? 'inline-flex' : 'none';
    }

    // Mostrar "Extraer con Whisper" únicamente si hay un video cargado PERO aún no se ha completado la extracción (segments.length === 0)
    if (this.btnTranscribe) {
      this.btnTranscribe.style.display = (hasVideo && segments.length === 0) ? 'inline-flex' : 'none';
    }

    if (segments.length === 0) {
      this.segmentsContainer.innerHTML = hasVideo
        ? `
          <div class="empty-state-box">
            No se detectó voz hablada en este archivo. Usa <strong>+ Oración</strong> para agregar subtítulos manualmente o selecciona otro video.
          </div>
        `
        : `
          <div class="empty-state-box">
            Selecciona tu video en el panel izquierdo para extraer y transcribir automáticamente el audio con <strong>Whisper ASR</strong>, o usa <strong>+ Oración</strong>.
          </div>
        `;
      return;
    }

    if (this.viewMode === 'unified') {
      this.renderUnifiedBox(segments);
    } else {
      this.renderSentenceCards(segments);
    }

    const currentTime = (typeof appState !== 'undefined' && appState.state?.playback?.currentTime) || 0;
    this.highlightActiveSegmentByTime(currentTime);
  }

  renderUnifiedBox(segments) {
    this.segmentsContainer.innerHTML = '';

    const firstStart = segments[0]?.start_time || 0;
    const lastEnd = segments[segments.length - 1]?.end_time || 0;
    const totalRange = this.formatTimeRange(firstStart, lastEnd);

    const confidences = segments.map(s => Number(s.asr_confidence ?? s.confidence ?? 0.94));
    const avgConf = Math.round((confidences.reduce((a, b) => a + b, 0) / Math.max(1, confidences.length)) * 100);

    const unifiedCard = document.createElement('div');
    unifiedCard.className = 'transcript-unified-box';

    const sentencesHtml = segments.map((seg, idx) => {
      const textValue = (seg.normalized_text || seg.raw_text || seg.original_text || '').trim();
      const timeLabel = this.formatTimeRange(seg.start_time, seg.end_time);
      const confPct = Math.round((seg.asr_confidence ?? seg.confidence ?? 0.94) * 100);
      return `<span class="transcript-unified-sentence" role="button" tabindex="0" data-seg-id="${this.escapeHtml(seg.id)}" data-start-time="${seg.start_time}" data-end-time="${seg.end_time}" title="Oración #${idx + 1} ${timeLabel} · ASR Whisper ${confPct}% — Haz clic para editar por frase">${this.escapeHtml(textValue)}</span>`;
    }).join(' ');

    unifiedCard.innerHTML = `
      <div class="transcript-unified-header">
        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
          <span class="transcript-seg-time-badge" style="cursor:default;">
            <span>Transcripción Completa</span>
            <span>${totalRange}</span>
          </span>
          <span style="font-size:0.76rem; font-weight:700; color:var(--color-text-secondary);">
            Fidelidad media: ${avgConf}%
          </span>
        </div>
        <span class="transcript-unified-hint">
          Clic en cualquier frase para editarla
        </span>
      </div>
      <div class="transcript-unified-body" id="transcript-unified-body">
        ${sentencesHtml}
      </div>
    `;

    unifiedCard.querySelectorAll('.transcript-unified-sentence').forEach((spanEl) => {
      const activateSentenceCardView = () => {
        const segId = spanEl.dataset.segId;
        const startSec = parseFloat(spanEl.dataset.startTime || '0');
        const targetSeg = segments.find(s => String(s.id) === String(segId));
        if (typeof appState !== 'undefined') {
          appState.setCurrentTime(startSec, true);
          if (targetSeg) {
            appState.selectItem('segment', targetSeg.id, targetSeg);
          }
        }
        this.setViewMode('cards', segId);
      };

      spanEl.addEventListener('click', activateSentenceCardView);
      spanEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          activateSentenceCardView();
        }
      });
    });

    this.segmentsContainer.appendChild(unifiedCard);
  }

  renderSentenceCards(segments) {
    this.segmentsContainer.innerHTML = '';

    segments.forEach((seg, idx) => {
      const card = document.createElement('div');
      card.className = 'transcript-seg-card';
      if (this.focusedSegmentId && String(seg.id) === String(this.focusedSegmentId)) {
        card.classList.add('active');
      }
      card.dataset.segId = seg.id;
      card.dataset.startTime = seg.start_time;
      card.dataset.endTime = seg.end_time;

      const textValue = seg.normalized_text || seg.raw_text || seg.original_text || '';
      const timeLabel = this.formatTimeRange(seg.start_time, seg.end_time);
      const confPct = Math.round((seg.asr_confidence ?? seg.confidence ?? 0.94) * 100);

      card.innerHTML = `
        <div class="transcript-seg-top">
          <button type="button" class="transcript-seg-time-badge" data-action="seek" title="Ir a este instante del video">
            <span>#${idx + 1}</span>
            <span>${timeLabel}</span>
          </button>
          <div style="display:flex; gap:6px; align-items:center;">
            <span style="font-size:0.74rem; font-weight:700; color:var(--color-text-secondary);">
              Fidelidad ${confPct}%
            </span>
            <button type="button" class="btn btn-sm transcript-seg-delete-btn" data-action="delete" title="Eliminar oración" style="padding:2px 8px;">
              Eliminar
            </button>
          </div>
        </div>
        <textarea id="transcript-seg-input-${idx + 1}" name="transcript_segment_${idx + 1}" class="transcript-seg-input" rows="2" aria-label="Texto transcrito oración ${idx + 1}" placeholder="Escribe o corrige la oración en español...">${this.escapeHtml(textValue)}</textarea>
      `;

      const seekBtn = card.querySelector('[data-action="seek"]');
      if (seekBtn) {
        seekBtn.addEventListener('click', () => {
          appState.setCurrentTime(Number(seg.start_time) || 0, true);
          appState.selectItem('segment', seg.id, seg);
        });
      }

      const deleteBtn = card.querySelector('[data-action="delete"]');
      if (deleteBtn) {
        deleteBtn.addEventListener('click', () => {
          if (typeof appState.deleteSegment === 'function') {
            appState.deleteSegment(seg.id);
          }
        });
      }

      const textarea = card.querySelector('.transcript-seg-input');
      if (textarea) {
        textarea.addEventListener('input', (e) => {
          const liveText = e.target.value;
          seg.normalized_text = liveText.trim();
          seg.raw_text = liveText.trim();
          seg.original_text = liveText.trim();
          seg.status = 'CORRECTED';
        });
        textarea.addEventListener('change', (e) => {
          const updatedText = e.target.value.trim();
          appState.updateSegment(seg.id, {
            normalized_text: updatedText,
            raw_text: updatedText,
            status: 'CORRECTED'
          });
        });
      }

      this.segmentsContainer.appendChild(card);
    });
  }

  highlightActiveSegmentByTime(currentTime) {
    if (!this.segmentsContainer) return;

    const findActiveIndex = (elements) => {
      const arr = Array.from(elements);
      let idx = arr.findIndex((el) => {
        const start = parseFloat(el.dataset.startTime || '0');
        const end = parseFloat(el.dataset.endTime || '0');
        return currentTime >= start && currentTime < end;
      });
      if (idx === -1) {
        idx = arr.findIndex((el) => {
          const start = parseFloat(el.dataset.startTime || '0');
          const end = parseFloat(el.dataset.endTime || '0');
          return currentTime >= start && currentTime <= end;
        });
      }
      return idx;
    };

    const cards = this.segmentsContainer.querySelectorAll('.transcript-seg-card');
    const activeCardIdx = findActiveIndex(cards);
    cards.forEach((card, i) => {
      card.classList.toggle('active', i === activeCardIdx);
    });

    const unifiedSpans = this.segmentsContainer.querySelectorAll('.transcript-unified-sentence');
    const activeSpanIdx = findActiveIndex(unifiedSpans);
    unifiedSpans.forEach((spanEl, i) => {
      spanEl.classList.toggle('active', i === activeSpanIdx);
    });
  }

  handleAddSegment() {
    if (typeof appState === 'undefined') return;
    const segments = appState.state?.project?.segments || [];
    const lastEnd = segments.length > 0 ? Number(segments[segments.length - 1].end_time) || 0 : 0;
    const newStart = Number(lastEnd.toFixed(1));
    const newEnd = Number((newStart + 3.0).toFixed(1));

    this.viewMode = 'cards';
    this.updateViewModeButton();
    if (typeof appState.addSegment === 'function') {
      const added = appState.addSegment(newStart, newEnd, 'Nueva oración educativa en español.');
      if (added && added.id) {
        this.focusedSegmentId = added.id;
        this.renderSegments();
        requestAnimationFrame(() => {
          const targetCard = this.segmentsContainer?.querySelector(
            `.transcript-seg-card[data-seg-id="${CSS.escape(String(added.id))}"]`
          );
          if (targetCard) {
            targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
            const ta = targetCard.querySelector('.transcript-seg-input');
            if (ta) {
              ta.focus();
              ta.select();
            }
          }
        });
      }
    }
  }

  escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
}

if (typeof window !== 'undefined') {
  window.TranscriptWindowController = TranscriptWindowController;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { TranscriptWindowController };
}
