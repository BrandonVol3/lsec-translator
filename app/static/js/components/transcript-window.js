/**
 * LSEC Studio 2.1.1 — Editor Central de Segmentos (Segment Workspace)
 * 
 * Convierte al segmento en la unidad central de trabajo lingüístico:
 * - Español original y normalizado
 * - Propuesta de glosas LSEC editables y reordenables
 * - Referencias espaciales (Loci) y rasgos no manuales
 * - Registro y firma de validación humana
 * - Timestamps precisos estilo YouTube (MM:SS)
 */

class TranscriptWindowController {
  constructor(containerId = 'segment-hub-view') {
    this.container = document.getElementById(containerId);
    this.segmentsListEl = document.getElementById('transcript-segments-list');
    this.searchInput = document.getElementById('transcript-search-input');
    this.autoScrollToggle = document.getElementById('btn-toggle-auto-scroll');

    // Chips de Filtro Rápido
    this.chipAll = document.getElementById('chip-filter-all');
    this.chipReview = document.getElementById('chip-filter-review');
    this.chipAudio = document.getElementById('chip-filter-audio');
    this.chipNative = document.getElementById('chip-filter-native');
    this.chipCorrections = document.getElementById('chip-filter-corrections');

    this.editingSegmentId = null;

    this.init();
    this.subscribeState();
  }

  init() {
    // 1. Búsqueda en vivo
    if (this.searchInput) {
      this.searchInput.addEventListener('input', (e) => {
        appState.setFilter('textQuery', e.target.value.toLowerCase().trim());
      });
    }

    // 2. Toggle Auto-Scroll
    if (this.autoScrollToggle) {
      this.autoScrollToggle.addEventListener('click', () => {
        const next = !appState.state.workspace.autoScrollTranscript;
        appState.state.workspace.autoScrollTranscript = next;
        this.updateAutoScrollButton(next);
      });
    }

    // 3. Chips de filtro
    const chips = [
      { el: this.chipAll, filter: 'ALL' },
      { el: this.chipReview, filter: 'REVIEW' },
      { el: this.chipAudio, filter: 'AUDIO' },
      { el: this.chipNative, filter: 'NATIVE' },
      { el: this.chipCorrections, filter: 'CORRECTIONS' }
    ];

    chips.forEach(({ el, filter }) => {
      if (el) {
        el.addEventListener('click', () => {
          appState.setFilter('quickFilter', filter);
          this.updateQuickChipUI(filter);
        });
      }
    });
  }

  updateQuickChipUI(activeFilter) {
    const chipMap = {
      'ALL': this.chipAll,
      'REVIEW': this.chipReview,
      'AUDIO': this.chipAudio,
      'NATIVE': this.chipNative,
      'CORRECTIONS': this.chipCorrections
    };

    Object.entries(chipMap).forEach(([filter, el]) => {
      if (el) {
        if (filter === activeFilter) el.classList.add('active');
        else el.classList.remove('active');
      }
    });
  }

  updateAutoScrollButton(enabled) {
    if (!this.autoScrollToggle) return;
    this.autoScrollToggle.textContent = enabled ? 'Auto-Scroll: ON' : 'Auto-Scroll: OFF';
    this.autoScrollToggle.classList.toggle('active', enabled);
  }

  subscribeState() {
    appState.subscribe('activeSegmentChanged', ({ id }) => {
      this.highlightActiveSegment(id);
    });

    appState.subscribe('filtersChanged', () => {
      this.render();
    });

    appState.subscribe('segmentsChanged', () => {
      this.render();
    });

    appState.subscribe('stageChanged', () => {
      this.render();
    });

    appState.subscribe('projectLoaded', () => {
      this.render();
    });

    appState.subscribe('projectUpdated', () => {
      this.render();
    });

    this.render();
  }

  formatYouTubeTime(seconds) {
    if (seconds === undefined || seconds === null || isNaN(seconds)) return '00:00';
    const s = Math.max(0, seconds);
    const hrs = Math.floor(s / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const secs = Math.floor(s % 60);
    
    if (hrs > 0) {
      return `${hrs}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }

  escapeHTML(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  render() {
    if (!this.segmentsListEl) {
      this.segmentsListEl = document.getElementById('transcript-segments-list');
    }
    if (!this.segmentsListEl) return;

    const project = appState.state.project;
    if (!project || !project.segments || project.segments.length === 0) {
      this.segmentsListEl.innerHTML = `
        <div style="padding: 36px 16px; text-align: center; color: var(--text-muted); font-size: 0.82rem;">
          <div style="font-weight: 600; color: var(--text-secondary); margin-bottom: 4px; font-size: 0.90rem;">
            Sin Segmentos Disponibles
          </div>
          <p style="color: var(--text-muted); line-height: 1.4;">Carga un video para procesar la transcripción y propuesta de glosas LSEC, o abre un archivo JSON.</p>
        </div>
      `;
      return;
    }

    const filters = appState.state.filters;
    let filtered = [...project.segments];

    // Filtro por texto
    if (filters.textQuery) {
      filtered = filtered.filter(s => 
        (s.original_text && s.original_text.toLowerCase().includes(filters.textQuery)) ||
        (s.normalized_text && s.normalized_text.toLowerCase().includes(filters.textQuery)) ||
        (s.gloss_sequence && s.gloss_sequence.some(g => g.toLowerCase().includes(filters.textQuery)))
      );
    }

    // Filtro rápido
    if (filters.quickFilter === 'REVIEW') {
      filtered = filtered.filter(s => s.status === 'REVIEW_REQUIRED');
    } else if (filters.quickFilter === 'AUDIO') {
      filtered = filtered.filter(s => s.secondary_cause === 'Audio');
    } else if (filters.quickFilter === 'NATIVE') {
      filtered = filtered.filter(s => s.secondary_cause === 'Sintaxis LSEC');
    } else if (filters.quickFilter === 'CORRECTIONS') {
      filtered = filtered.filter(s => s.status === 'CORRECTED');
    }

    this.segmentsListEl.innerHTML = '';

    filtered.forEach(seg => {
      const card = this.createSegmentCard(seg);
      this.segmentsListEl.appendChild(card);
    });

    if (filtered.length === 0) {
      this.segmentsListEl.innerHTML = `
        <div style="padding: 24px; text-align: center; color: var(--text-muted); font-size: 0.80rem;">
          No hay segmentos que coincidan con el filtro activo.
        </div>
      `;
    }

    this.highlightActiveSegment(appState.state.playback.activeSegmentId);
  }

  createSegmentCard(seg) {
    const card = document.createElement('div');
    const isEditing = this.editingSegmentId === seg.id;
    const isActive = appState.state.playback.activeSegmentId === seg.id;

    const statusClass = (seg.status || 'draft').toLowerCase();
    card.className = `segment-card-unit status-${statusClass} ${isActive ? 'active' : ''}`;
    card.id = `segment-card-${seg.id}`;

    const startFormatted = this.formatYouTubeTime(seg.start_seconds);
    const endFormatted = this.formatYouTubeTime(seg.end_seconds);

    // Mapeo de estado para clase CSS
    let statusBadgeClass = 'draft';
    if (seg.status === 'REVIEW_REQUIRED') statusBadgeClass = 'review';
    else if (seg.status === 'CORRECTED') statusBadgeClass = 'corrected';
    else if (seg.status === 'VALIDATED') statusBadgeClass = 'validated';

    const durSec = (seg.duration !== undefined && !isNaN(seg.duration)) ? seg.duration : Math.max(0, (seg.end_seconds || 0) - (seg.start_seconds || 0));

    card.innerHTML = `
      <!-- Columna Izquierda: Timestamp estilo YouTube con minutos y segundos -->
      <div class="unit-time-column">
        <button class="yt-time-btn" id="btn-time-${seg.id}" title="Reproducir desde ${startFormatted}">
          <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
          <span>${startFormatted}</span>
        </button>
        <span class="unit-time-range">${startFormatted} - ${endFormatted}</span>
        <span style="font-size:0.62rem; color:var(--text-muted); font-family:var(--font-mono);">${durSec.toFixed(2)}s</span>
      </div>

      <!-- Columna Principal: Contenido Lingüístico Completo -->
      <div class="unit-main-column">
        
        <!-- Header del Segmento -->
        <div class="unit-header-meta">
          <div class="meta-left">
            <span class="badge-index">#${String(seg.index).padStart(2, '0')}</span>
            <span class="badge-status ${statusBadgeClass}">${seg.status_label || seg.status}</span>
            ${seg.secondary_cause ? `<span class="tag-cause">${seg.secondary_cause}</span>` : ''}
          </div>

          <div class="meta-right">
            <span style="font-size:0.68rem; color:var(--text-muted);">
              Confianza: <strong style="color:var(--text-secondary);">${Math.round((seg.confidence || 0.94) * 100)}%</strong>
            </span>
          </div>
        </div>

        <!-- Fila de Texto de Subtítulo -->
        <div class="text-row-spanish">
          ${isEditing ? `
            <div style="margin:4px 0; width:100%;">
              <input type="text" id="edit-text-${seg.id}" aria-label="Editar texto del subtítulo #${seg.index}" value="${this.escapeHTML(seg.normalized_text || seg.original_text || '')}" class="inspector-input" style="font-weight:600; width:100%; box-sizing:border-box; font-size:0.86rem;" placeholder="Escribe el texto del subtítulo...">
            </div>
          ` : `
            <div><strong>${this.escapeHTML(seg.normalized_text || seg.original_text || '')}</strong></div>
            ${(seg.original_text && seg.normalized_text && seg.original_text !== seg.normalized_text) ? `
              <div class="text-orig-note">Original ASR: "${this.escapeHTML(seg.original_text)}"</div>
            ` : ''}
          `}
        </div>

        <!-- Fila de Glosas LSEC -->
        <div class="glosses-row-unit">
          <span style="font-size:0.66rem; font-weight:600; color:var(--text-muted); margin-right:2px;">LSEC:</span>
          ${(seg.gloss_sequence && seg.gloss_sequence.length > 0) ? `
            ${(seg.gloss_sequence || []).map((g, gIdx) => `
              <span class="gloss-chip ${g.includes('-') ? 'fs' : ''}" data-gloss-idx="${gIdx}" title="Glosa LSEC: ${g}">
                ${g}
              </span>
            `).join('')}
            ${(seg.spatial_loci || []).map(l => `
              <span class="gloss-chip locus-tag" title="Locus Espacial: ${l}">[${l}]</span>
            `).join('')}
          ` : `
            <span class="gloss-pending-badge" title="Glosas aún no generadas. Revisa las palabras y haz clic en 'Traducir a Glosas LSEC'">
              [Pendiente de traducción a glosas LSEC]
            </span>
          `}
        </div>

        <!-- Fila de Atribución y Acciones -->
        <div class="unit-footer-actions">
          <div class="attribution-text">
            ${(seg.human_reviewed || seg.status === 'VALIDATED') ? `
              <span style="color:var(--status-validated);">Validado por: ${seg.validated_by || appState.state.currentUser?.name || 'Revisor LSEC'}${seg.validated_at ? ` (${seg.validated_at})` : ''}</span>
            ` : `
              <span>Propuesta generada automáticamente, aún no validada</span>
            `}
          </div>

          <div class="actions-group">
            <button class="btn btn-secondary btn-sm" id="btn-loop-${seg.id}" title="Reproducir este segmento en bucle">Bucle</button>
            ${isEditing ? `
              <button class="btn btn-primary btn-sm" id="btn-save-${seg.id}">Guardar</button>
              <button class="btn btn-secondary btn-sm" id="btn-cancel-${seg.id}">Cancelar</button>
            ` : `
              <button class="btn btn-secondary btn-sm" id="btn-edit-${seg.id}">Editar</button>
            `}
            <button class="btn btn-secondary btn-sm" id="btn-split-${seg.id}" title="Dividir en cabezal">Dividir</button>
            <button class="btn btn-secondary btn-sm" id="btn-merge-${seg.id}" title="Unir con siguiente">Unir</button>
            <button class="btn btn-primary btn-sm" id="btn-val-${seg.id}" title="Validar este segmento">Validar</button>
          </div>
        </div>

      </div>
    `;

    // Clic en la tarjeta selecciona el segmento en el Inspector
    card.addEventListener('click', (e) => {
      if (['BUTTON', 'INPUT', 'TEXTAREA'].includes(e.target.tagName) || e.target.closest('button')) return;
      appState.setCurrentTime(seg.start_seconds, 'segment_card_click');
      appState.selectItem('segment', seg.id, seg);
    });

    // Clic en el botón de tiempo estilo YouTube
    const btnTime = card.querySelector(`#btn-time-${seg.id}`);
    if (btnTime) {
      btnTime.addEventListener('click', (e) => {
        e.stopPropagation();
        appState.setCurrentTime(seg.start_seconds, 'yt_time_click');
        appState.selectItem('segment', seg.id, seg);
        appState.setIsPlaying(true);
      });
    }

    // Clic en chips de glosa
    const glossChips = card.querySelectorAll('.gloss-chip');
    glossChips.forEach(chip => {
      chip.addEventListener('click', (e) => {
        e.stopPropagation();
        const glossText = chip.textContent.trim().replace(/^\[|\]$/g, '');
        const matchingGloss = (appState.state.project.glosses || []).find(g => g.gloss === glossText) || {
          id: `g_${seg.id}_${glossText}`,
          gloss: glossText,
          lemma: glossText,
          start_seconds: seg.start_seconds,
          end_seconds: seg.end_seconds,
          syntactic_role: 'TÓPICO',
          spatial_locus: 'CENTRO'
        };
        appState.selectItem('gloss', matchingGloss.id, matchingGloss);
      });
    });

    // Botones de acción
    const btnLoop = card.querySelector(`#btn-loop-${seg.id}`);
    if (btnLoop) {
      btnLoop.addEventListener('click', (e) => {
        e.stopPropagation();
        appState.setCurrentTime(seg.start_seconds, 'loop_snippet');
        appState.setInPoint(seg.start_seconds);
        appState.setOutPoint(seg.end_seconds);
        appState.state.playback.isLooping = true;
        appState.setIsPlaying(true);
      });
    }

    const btnEdit = card.querySelector(`#btn-edit-${seg.id}`);
    if (btnEdit) {
      btnEdit.addEventListener('click', (e) => {
        e.stopPropagation();
        this.editingSegmentId = seg.id;
        this.render();
      });
    }

    const btnSave = card.querySelector(`#btn-save-${seg.id}`);
    if (btnSave) {
      btnSave.addEventListener('click', (e) => {
        e.stopPropagation();
        const inputEl = card.querySelector(`#edit-text-${seg.id}`);
        const newText = inputEl ? inputEl.value.trim() : (seg.normalized_text || seg.original_text || '');
        appState.updateSegment(seg.id, {
          original_text: newText,
          normalized_text: newText,
          text: newText,
          status: 'CORRECTED'
        });
        // Si ya se había generado la traducción, marcar que requiere re-traducir a glosas
        if (appState.state.workspace.translationReady) {
          appState.invalidateTranslation();
          if (typeof window.showToast === 'function') {
            window.showToast('Has modificado un subtítulo. Presiona "Traducir a Glosas LSEC" para actualizar las señas.', 'info');
          }
        }
        this.editingSegmentId = null;
        this.render();
      });
    }

    // Auto-focus y atajos de teclado (Enter para guardar, Escape para cancelar)
    const textInput = card.querySelector(`#edit-text-${seg.id}`);
    if (textInput) {
      setTimeout(() => textInput.focus(), 60);
      textInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          e.stopPropagation();
          const saveBtn = card.querySelector(`#btn-save-${seg.id}`);
          if (saveBtn) saveBtn.click();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          e.stopPropagation();
          const cancelBtn = card.querySelector(`#btn-cancel-${seg.id}`);
          if (cancelBtn) cancelBtn.click();
        }
      });
    }

    const btnCancel = card.querySelector(`#btn-cancel-${seg.id}`);
    if (btnCancel) {
      btnCancel.addEventListener('click', (e) => {
        e.stopPropagation();
        this.editingSegmentId = null;
        this.render();
      });
    }

    const btnSplit = card.querySelector(`#btn-split-${seg.id}`);
    if (btnSplit) {
      btnSplit.addEventListener('click', (e) => {
        e.stopPropagation();
        const cur = appState.state.playback.currentTime;
        if (cur > seg.start_seconds && cur < seg.end_seconds) {
          appState.splitSegment(seg.id, cur);
        } else {
          alert('Ubica el cabezal de reproducción dentro del rango de este segmento para dividirlo.');
        }
      });
    }

    const btnMerge = card.querySelector(`#btn-merge-${seg.id}`);
    if (btnMerge) {
      btnMerge.addEventListener('click', (e) => {
        e.stopPropagation();
        appState.mergeSegmentWithNext(seg.id);
      });
    }

    const btnVal = card.querySelector(`#btn-val-${seg.id}`);
    if (btnVal) {
      btnVal.addEventListener('click', (e) => {
        e.stopPropagation();
        appState.validateSegment(seg.id);
      });
    }

    return card;
  }

  highlightActiveSegment(segId) {
    if (!this.segmentsListEl) return;
    const cards = this.segmentsListEl.querySelectorAll('.segment-card-unit');
    cards.forEach(c => c.classList.remove('active'));

    if (segId) {
      const activeCard = this.segmentsListEl.querySelector(`#segment-card-${segId}`);
      if (activeCard) {
        activeCard.classList.add('active');

        if (appState.state.workspace.autoScrollTranscript && !this.editingSegmentId) {
          activeCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      }
    }
  }
}

// Exportación global
window.TranscriptWindowController = TranscriptWindowController;
