/**
 * LSEC Studio — Controlador de la Ventana 1 («1. Transcripción con Whisper»)
 * Gestiona el visualizador animado de onda acústica Whisper ASR,
 * la lista limpia de segmentos editables [mm:ss - mm:ss] y el paso hacia Ventana 2.
 */

class TranscriptWindowController {
  constructor(options = {}) {
    this.onProceedToStep2 = options.onProceedToStep2 || null;
    this.onRunWhisper = options.onRunWhisper || null;

    this.segmentsContainer = document.getElementById('transcript-segments-container');
    this.countBadge = document.getElementById('transcript-count-badge');
    this.statusLabel = document.getElementById('whisper-status-label');
    this.waveformCanvas = document.getElementById('whisper-waveform-canvas');
    this.btnAddSegment = document.getElementById('btn-add-transcript-segment');
    this.btnTranscribe = document.getElementById('btn-step1-transcribe');
    this.btnProcessLsec = document.getElementById('btn-step1-process-lsec');

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

  subscribeToStore() {
    if (typeof appState === 'undefined') return;

    appState.subscribe('projectLoaded', () => {
      this.waveBars = this.generateWaveProfile(72);
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
    this.updateCountBadge();

    if (segments.length === 0) {
      this.segmentsContainer.innerHTML = `
        <div class="empty-state-box">
          No hay segmentos transcritos aún. Carga un video y presiona <strong>Extraer con Whisper</strong> o usa <strong>+ Oración</strong>.
        </div>
      `;
      return;
    }

    this.segmentsContainer.innerHTML = '';

    segments.forEach((seg, idx) => {
      const card = document.createElement('div');
      card.className = 'transcript-seg-card';
      card.dataset.segId = seg.id;
      card.dataset.startTime = seg.start_time;
      card.dataset.endTime = seg.end_time;

      const textValue = seg.normalized_text || seg.raw_text || '';
      const timeLabel = this.formatTimeRange(seg.start_time, seg.end_time);

      card.innerHTML = `
        <div class="transcript-seg-top">
          <button type="button" class="transcript-seg-time-badge" data-action="seek" title="Ir a este instante del video">
            <span>#${idx + 1}</span>
            <span>${timeLabel}</span>
          </button>
          <div style="display:flex; gap:6px; align-items:center;">
            <span style="font-size:0.74rem; font-weight:700; color:var(--color-text-secondary);">
              ASR Whisper ${Math.round((seg.asr_confidence || 0.94) * 100)}%
            </span>
            <button type="button" class="btn btn-sm" data-action="delete" title="Eliminar oración" style="padding:2px 8px;">
              Eliminar
            </button>
          </div>
        </div>
        <textarea class="transcript-seg-input" rows="2" aria-label="Texto transcrito oración ${idx + 1}" placeholder="Escribe o corrige la oración en español...">${this.escapeHtml(textValue)}</textarea>
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
    const cards = this.segmentsContainer.querySelectorAll('.transcript-seg-card');
    cards.forEach((card) => {
      const start = parseFloat(card.dataset.startTime || '0');
      const end = parseFloat(card.dataset.endTime || '0');
      const isCurrent = currentTime >= start && currentTime <= end;
      card.classList.toggle('active', isCurrent);
    });
  }

  handleAddSegment() {
    if (typeof appState === 'undefined') return;
    const segments = appState.state?.project?.segments || [];
    const lastEnd = segments.length > 0 ? Number(segments[segments.length - 1].end_time) || 0 : 0;
    const newStart = Number(lastEnd.toFixed(1));
    const newEnd = Number((newStart + 3.0).toFixed(1));

    if (typeof appState.addSegment === 'function') {
      appState.addSegment(newStart, newEnd, 'Nueva oración educativa en español.');
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
