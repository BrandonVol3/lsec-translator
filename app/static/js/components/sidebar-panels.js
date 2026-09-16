/**
 * LSEC Studio 2.1.1 — Panel Lateral Derecho
 * 
 * Gestiona:
 * 1. Pestaña "Transcripción": Visualización continua de la transcripción total con minutos,
 *    búsqueda en tiempo real, seguimiento por reproducción y copia al portapapeles.
 * 2. Pestaña "Inspector": Inspector contextual reactivo para segmentos, glosas LSEC,
 *    referencias espaciales y rasgos no manuales.
 */

class ContextualInspectorController {
  constructor(containerId = 'contextual-inspector-zone') {
    this.container = document.getElementById(containerId);
    
    // Pestañas
    this.tabBtnTranscript = document.getElementById('tab-btn-side-transcript');
    this.tabBtnInspector = document.getElementById('tab-btn-side-inspector');
    this.tabBtnSubtitles = document.getElementById('tab-btn-side-subtitles');
    this.viewTranscript = document.getElementById('view-side-transcript');
    this.viewInspector = document.getElementById('view-side-inspector');
    this.viewSubtitles = document.getElementById('view-side-subtitles');

    // Elementos de la Transcripción Lateral
    this.transcriptListEl = document.getElementById('full-transcript-stream-list');
    this.searchInputEl = document.getElementById('side-transcript-search');
    this.copyBtnEl = document.getElementById('btn-copy-transcript-text');

    // Elementos del Inspector
    this.titleEl = document.getElementById('inspector-title-text');
    this.iconEl = document.getElementById('inspector-header-icon');
    this.badgeEl = document.getElementById('inspector-header-badge');
    this.bodyEl = document.getElementById('inspector-body-content');

    this.activeTab = 'transcript'; // 'transcript' | 'inspector'
    this.currentActiveSegId = null;

    this.init();
    this.subscribeState();
  }

  init() {
    this.initTabs();
    this.initSearchAndCopy();
    this.renderFullTranscript();
    this.renderEmptyInspector();
    if (this.badgeEl) {
      this.badgeEl.style.display = 'none';
    }
  }

  initTabs() {
    if (this.tabBtnTranscript) {
      this.tabBtnTranscript.addEventListener('click', () => {
        this.switchTab('transcript');
      });
    }

    if (this.tabBtnInspector) {
      this.tabBtnInspector.addEventListener('click', () => {
        this.switchTab('inspector');
      });
    }

    if (this.tabBtnSubtitles) {
      this.tabBtnSubtitles.addEventListener('click', () => {
        this.switchTab('subtitles');
      });
    }
  }

  switchTab(tabName) {
    this.activeTab = tabName;

    const tabs = [
      { name: 'transcript', btn: this.tabBtnTranscript, view: this.viewTranscript },
      { name: 'inspector', btn: this.tabBtnInspector, view: this.viewInspector },
      { name: 'subtitles', btn: this.tabBtnSubtitles, view: this.viewSubtitles }
    ];

    tabs.forEach(t => {
      const isActive = t.name === tabName;
      if (t.btn) t.btn.classList.toggle('active', isActive);
      if (t.view) t.view.style.display = isActive ? 'flex' : 'none';
    });

    if (this.badgeEl) {
      this.badgeEl.style.display = (tabName === 'inspector' && this.badgeEl.innerHTML.trim() !== '') ? 'inline-flex' : 'none';
    }
  }

  initSearchAndCopy() {
    if (this.searchInputEl) {
      this.searchInputEl.addEventListener('input', () => {
        this.filterTranscript(this.searchInputEl.value.trim().toLowerCase());
      });
    }

    if (this.copyBtnEl) {
      this.copyBtnEl.addEventListener('click', () => {
        this.copyFullTranscriptToClipboard();
      });
    }
  }

  subscribeState() {
    // 1. Sincronización en tiempo real con la reproducción del video
    appState.subscribe('timeupdate', ({ time }) => {
      this.syncActiveTranscriptRow(time);
    });

    // 2. Carga o cambio de proyecto
    appState.subscribe('projectLoaded', () => {
      this.renderFullTranscript();
      if (appState.state.playback.selectedItem) {
        this.renderInspector(appState.state.playback.selectedItem);
      } else {
        this.renderEmptyInspector();
      }
    });

    appState.subscribe('projectCleared', () => {
      this.renderFullTranscript();
      this.renderEmptyInspector();
    });

    // 3. Selección de elemento (segmento, glosa, locus)
    appState.subscribe('selectionChanged', (selection) => {
      this.renderInspector(selection);
      if (selection && selection.type === 'segment') {
        this.highlightSelectedTranscriptRow(selection.id);
      }
    });

    // 4. Cambio de etapa
    appState.subscribe('stageChanged', () => {
      if (!appState.state.playback.selectedItem) {
        this.renderEmptyInspector();
      }
    });
  }

  // ============================================================
  // PESTAÑA 1: TRANSCRIPCIÓN TOTAL CON MINUTOS
  // ============================================================

  formatMinuteSeconds(secs) {
    if (secs === undefined || secs === null || isNaN(secs) || secs < 0) return '00:00';
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  renderFullTranscript() {
    if (!this.transcriptListEl) return;
    this.transcriptListEl.innerHTML = '';

    const project = appState.state.project;
    if (!project || !project.segments || project.segments.length === 0) {
      this.transcriptListEl.innerHTML = `
        <div style="padding: 36px 16px; text-align: center; color: var(--text-muted);">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor" style="opacity: 0.35; margin-bottom: 8px;">
            <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/>
          </svg>
          <div style="font-weight: 600; color: var(--text-secondary); margin-bottom: 4px; font-size: 0.88rem;">Sin Transcripción Disponible</div>
          <p style="font-size: 0.76rem; line-height: 1.4; color: var(--text-muted);">Carga un video para extraer el audio y visualizar la transcripción completa sincronizada con minutos.</p>
        </div>
      `;
      return;
    }

    const segments = project.segments;

    segments.forEach((seg, index) => {
      const startSec = seg.start_seconds !== undefined ? seg.start_seconds : (seg.start_time || 0);
      const endSec = seg.end_seconds !== undefined ? seg.end_seconds : (seg.end_time || 0);
      const durationSec = Math.max(0, endSec - startSec);
      const text = seg.normalized_text || seg.original_text || '';

      const row = document.createElement('div');
      row.className = 'transcript-entry-row';
      row.id = `side-transcript-row-${seg.id}`;
      row.dataset.segId = seg.id;
      row.dataset.start = startSec;
      row.dataset.end = endSec;

      row.innerHTML = `
        <div class="transcript-entry-meta">
          <button class="ts-badge-btn" title="Saltar al minuto ${this.formatMinuteSeconds(startSec)}">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            <span>[${this.formatMinuteSeconds(startSec)}]</span>
          </button>
          <span class="ts-duration-tag">${durationSec.toFixed(1)}s · #${index + 1}</span>
        </div>
        <div class="transcript-entry-text">${text}</div>
      `;

      // Clic para saltar al minuto y seleccionar segmento
      row.addEventListener('click', () => {
        appState.setCurrentTime(startSec, 'side_transcript_row_click');
        appState.selectItem('segment', seg.id);
      });

      this.transcriptListEl.appendChild(row);
    });
  }

  syncActiveTranscriptRow(currentTime) {
    if (!this.transcriptListEl) return;
    const project = appState.state.project;
    if (!project || !project.segments) return;

    const activeSeg = project.segments.find(s => {
      const st = s.start_seconds !== undefined ? s.start_seconds : (s.start_time || 0);
      const et = s.end_seconds !== undefined ? s.end_seconds : (s.end_time || 0);
      return currentTime >= st && currentTime <= et;
    });

    if (activeSeg && activeSeg.id !== this.currentActiveSegId) {
      this.currentActiveSegId = activeSeg.id;

      // Desactivar filas previas
      const allRows = this.transcriptListEl.querySelectorAll('.transcript-entry-row');
      allRows.forEach(r => r.classList.remove('active'));

      // Activar fila actual
      const activeRow = document.getElementById(`side-transcript-row-${activeSeg.id}`);
      if (activeRow) {
        activeRow.classList.add('active');
        activeRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }
  }

  highlightSelectedTranscriptRow(segId) {
    if (!this.transcriptListEl) return;
    const allRows = this.transcriptListEl.querySelectorAll('.transcript-entry-row');
    allRows.forEach(r => r.classList.remove('active'));

    const row = document.getElementById(`side-transcript-row-${segId}`);
    if (row) {
      row.classList.add('active');
      row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  filterTranscript(query) {
    if (!this.transcriptListEl) return;
    const rows = this.transcriptListEl.querySelectorAll('.transcript-entry-row');

    rows.forEach(row => {
      const textEl = row.querySelector('.transcript-entry-text');
      if (!textEl) return;
      const text = textEl.textContent.toLowerCase();

      if (!query || text.includes(query)) {
        row.style.display = 'flex';
        if (query) {
          row.classList.add('match-highlight');
        } else {
          row.classList.remove('match-highlight');
        }
      } else {
        row.style.display = 'none';
        row.classList.remove('match-highlight');
      }
    });
  }

  copyFullTranscriptToClipboard() {
    const project = appState.state.project;
    if (!project || !project.segments || project.segments.length === 0) {
      alert('No hay transcripción disponible para copiar.');
      return;
    }

    const lines = project.segments.map(seg => {
      const st = seg.start_seconds !== undefined ? seg.start_seconds : (seg.start_time || 0);
      const timeStr = `[${this.formatMinuteSeconds(st)}]`;
      const text = seg.normalized_text || seg.original_text || '';
      return `${timeStr} ${text}`;
    });

    const fullText = lines.join('\n\n');

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(fullText).then(() => {
        if (this.copyBtnEl) {
          const originalHTML = this.copyBtnEl.innerHTML;
          this.copyBtnEl.innerHTML = `<span>¡Copiado!</span>`;
          setTimeout(() => {
            this.copyBtnEl.innerHTML = originalHTML;
          }, 1500);
        }
      }).catch(err => {
        console.warn('Error al copiar portapapeles:', err);
      });
    }
  }

  // ============================================================
  // PESTAÑA 2: INSPECTOR CONTEXTUAL
  // ============================================================

  renderInspector(selection) {
    if (!this.bodyEl) return;

    if (!selection || !selection.type || !selection.data) {
      this.renderEmptyInspector();
      return;
    }

    const { type, data } = selection;

    switch (type) {
      case 'sentence':
        this.renderSentenceInspector(data);
        break;
      case 'segment':
        this.renderSegmentInspector(data);
        break;
      case 'gloss':
        this.renderGlossInspector(data);
        break;
      case 'locus':
        this.renderLocusInspector(data);
        break;
      case 'non_manual':
        this.renderNonManualInspector(data);
        break;
      case 'issue':
        this.renderIssueInspector(data);
        break;
      default:
        this.renderEmptyInspector();
    }
  }

  renderEmptyInspector() {
    if (!this.titleEl || !this.bodyEl) return;
    const ws = appState.state.workspace;
    const stage = ws.stage;
    this.titleEl.textContent = 'Guía de Etapa Secuencial';
    if (this.badgeEl) this.badgeEl.innerHTML = '';

    let stageGuide = '';
    if (!ws.videoLoaded) {
      stageGuide = `
        <div class="inspector-section">
          <div class="inspector-label">Paso 1: Carga de Video Requerida</div>
          <div class="inspector-readout highlight" style="color:var(--status-review); border-left:3px solid var(--status-review);">
            El sistema opera en secuencia estricta. Primero debes cargar un archivo de video para extraer audio y generar los subtítulos.
          </div>
        </div>
        <div class="inspector-section">
          <div class="inspector-label">Opciones para comenzar</div>
          <ul style="padding-left: 18px; font-size: 0.78rem; color: var(--text-secondary); line-height: 1.6;">
            <li>Haz clic en el botón superior <strong>Video</strong> para subir un archivo local.</li>
            <li>O arrastra y suelta tu archivo de video sobre la pantalla.</li>
          </ul>
        </div>
      `;
    } else if (stage === 'preparar') {
      stageGuide = `
        <div class="inspector-section">
          <div class="inspector-label">Etapa 1: Subtítulos y Transcripción</div>
          <div class="inspector-readout highlight">
            Revisa la transcripción en español generada por Whisper y corrige palabras mal reconocidas antes de traducir a glosas.
          </div>
        </div>
        <div class="inspector-section">
          <div class="inspector-label">Acciones recomendadas</div>
          <ul style="padding-left: 18px; font-size: 0.78rem; color: var(--text-secondary); line-height: 1.6;">
            <li>Reproduce el video y sigue los subtítulos en sincronía.</li>
            <li>Haz clic en <strong>Editar</strong> en cualquier segmento para corregir términos específicos.</li>
            <li>Cuando las palabras estén correctas, presiona <strong>Traducir a Glosas LSEC ▶</strong> para desbloquear la etapa 2.</li>
          </ul>
        </div>
      `;
    } else if (stage === 'traducir') {
      stageGuide = `
        <div class="inspector-section">
          <div class="inspector-label">Etapa 2: Traducción LSEC</div>
          <div class="inspector-readout highlight">
            Valida la sintaxis (Tópico-Comentario), la lematización de glosas y los clasificadores espaciales asignados.
          </div>
        </div>
        <div class="inspector-section">
          <div class="inspector-label">Acciones recomendadas</div>
          <ul style="padding-left: 18px; font-size: 0.78rem; color: var(--text-secondary); line-height: 1.6;">
            <li>Comprueba las glosas generadas en el editor inferior o en el visor de video.</li>
            <li>Haz clic en las glosas para inspeccionar su rol sintáctico y dactilología.</li>
            <li>Una vez revisadas, pulsa <strong>Confirmar Glosas y Pasar a Revisión ▶</strong> para desbloquear la etapa 3.</li>
          </ul>
        </div>
      `;
    } else {
      stageGuide = `
        <div class="inspector-section">
          <div class="inspector-label">Etapa 3: Revisión Final</div>
          <div class="inspector-readout highlight">
            Revisa las incidencias o advertencias pendientes para asegurar la calidad antes de la entrega final.
          </div>
        </div>
        <div class="inspector-section">
          <div class="inspector-label">Acciones recomendadas</div>
          <ul style="padding-left: 18px; font-size: 0.78rem; color: var(--text-secondary); line-height: 1.6;">
            <li>Comprueba los segmentos marcados en color ámbar (<span style="color:var(--status-review); font-weight:600;">Revisión</span>).</li>
            <li>Aprueba o ajusta cada uno de los ítems señalados.</li>
            <li>Haz clic en <strong>Confirmar y Aprobar Traducción Final ✓</strong> para desbloquear la exportación.</li>
          </ul>
        </div>
      `;
    }

    this.bodyEl.innerHTML = stageGuide;
  }

  renderSentenceInspector(sentence) {
    if (!this.titleEl || !this.bodyEl) return;

    this.titleEl.textContent = `Frase ${sentence.index}`;
    if (this.badgeEl) {
      const isRev = sentence.status === 'REVIEW_REQUIRED' || sentence.has_review;
      this.badgeEl.innerHTML = `<span class="badge-status ${isRev ? 'review' : 'validated'}">${sentence.status_label || sentence.status}</span>`;
    }

    const st = sentence.start_seconds !== undefined ? sentence.start_seconds : 0;
    const et = sentence.end_seconds !== undefined ? sentence.end_seconds : 0;
    const dur = sentence.duration !== undefined ? sentence.duration : (et - st);

    // Segmentos asociados como enlaces de selección rápida
    const segsHtml = (sentence.segments || []).map(s => {
      const isSRev = s.status === 'REVIEW_REQUIRED' || s.status === 'AUDIO_REVIEW' || s.status === 'NATIVE_REVIEW' || s.status === 'BLOCKED';
      return `<button class="btn btn-secondary btn-sm sentence-linked-seg-btn ${isSRev ? 'issue' : ''}" data-segment-id="${s.id}" style="padding: 2px 6px; font-size: 0.70rem;" title="${s.normalized_text || ''}">${s.id}</button>`;
    }).join(' ');

    // Glosas asociadas como lista editable y accesible
    const glossesListHtml = (sentence.glosses || []).map((g, gIdx) => {
      const isFs = g.is_fingerspelling || g.gloss_type === 'DACTILOLOGÍA';
      const isPause = g.is_pause || g.gloss_type === 'PAUSA';
      const isGRev = g.status === 'AUDIO_REVIEW' || g.status === 'BLOCKED' || g.status === 'REVIEW_REQUIRED';
      const color = isGRev ? 'var(--status-review)' : (isPause ? '#f59e0b' : (isFs ? '#7dd3fc' : 'var(--action-primary)'));
      const label = isPause ? '⏸ [PAUSA]' : (g.gloss || g.lemma);
      return `
        <div class="insp-sentence-gloss-row" data-gloss-id="${g.id}">
          <span class="gloss-chip" data-gloss-id="${g.id}" style="color:${color}; cursor:pointer; font-weight:600;" title="${g.gloss} (${g.gloss_type || 'SEÑA'})">
            ${gIdx + 1}. ${this.escapeHTML(label)}
          </span>
          <div class="insp-gloss-row-actions">
            <button class="btn-icon btn-sm btn-reorder-left" data-sentence-id="${sentence.id}" data-gloss-id="${g.id}" data-index="${gIdx}" title="Mover a la izquierda" ${gIdx === 0 ? 'disabled style="opacity:0.3;"' : ''}>◀</button>
            <button class="btn-icon btn-sm btn-reorder-right" data-sentence-id="${sentence.id}" data-gloss-id="${g.id}" data-index="${gIdx}" title="Mover a la derecha" ${gIdx === sentence.glosses.length - 1 ? 'disabled style="opacity:0.3;"' : ''}>▶</button>
            <button class="btn-icon btn-sm btn-insp-dup" data-sentence-id="${sentence.id}" data-gloss-id="${g.id}" title="Duplicar glosa">⧉</button>
            <button class="btn-icon btn-sm btn-insp-del" data-sentence-id="${sentence.id}" data-gloss-id="${g.id}" title="Eliminar glosa" style="color:var(--status-review);">×</button>
          </div>
        </div>
      `;
    }).join('') || '<span style="color:var(--text-muted); font-size:0.75rem;">Sin glosas asociadas</span>';

    // Observaciones e Invariantes Incumplidas si existen
    const violations = (typeof StructuralValidator !== 'undefined')
      ? StructuralValidator.validateSentence(sentence, appState.state.project)
      : [];

    const allReasons = Array.from(new Set([
      ...(sentence.review_reasons || []),
      ...violations.map(v => `[${v.code}] ${v.message}`)
    ]));

    const reviewAlertHtml = allReasons.length > 0
      ? `
        <div class="inspector-section invariant-alert-card" style="border-left: 3px solid var(--status-review); background: rgba(216, 168, 78, 0.10); padding: 8px; border-radius: 4px; margin-bottom: 8px;">
          <div class="inspector-label" style="color: var(--status-review); display:flex; align-items:center; gap:4px; font-weight:700;">
            <span>⚠</span>
            <span>Invariantes Incumplidas / Revisión Requerida</span>
          </div>
          <div style="font-size: 0.74rem; color: var(--text-primary); line-height: 1.4; margin-top: 4px;">
            ${allReasons.map(r => `<div style="margin-bottom: 2px;">• ${this.escapeHTML(r)}</div>`).join('')}
          </div>
        </div>
      `
      : '';

    this.bodyEl.innerHTML = `
      <div class="inspector-section">
        <div class="inspector-label">Intervalo Temporal General</div>
        <div class="inspector-readout" style="font-family: var(--font-mono); font-size: 0.75rem;">
          [${this.formatMinuteSeconds(st)}] → [${this.formatMinuteSeconds(et)}] (${dur.toFixed(2)}s)
        </div>
      </div>

      <div class="inspector-section">
        <div class="inspector-label">Frase Completa (Español)</div>
        <div class="inspector-readout" style="font-size: 0.78rem; line-height: 1.4; color: var(--text-primary); font-weight: 500;">
          "${sentence.text || ''}"
        </div>
      </div>

      ${reviewAlertHtml}

      <div class="inspector-section">
        <div class="inspector-label" style="display:flex; justify-content:space-between; align-items:center;">
          <span>Glosas LSEC (${(sentence.glosses ? sentence.glosses.length : sentence.gloss_sequence.length)})</span>
          <div style="display:flex; gap:4px;">
            <button class="btn btn-secondary btn-sm" id="btn-insp-add-gloss" style="padding:1px 6px; font-size:0.68rem;">+ Glosa</button>
            <button class="btn btn-secondary btn-sm" id="btn-insp-add-pause" style="padding:1px 6px; font-size:0.68rem;">+ Pausa</button>
          </div>
        </div>
        <div class="insp-glosses-list-container" style="display:flex; flex-direction:column; gap:4px; margin-top:4px;">
          ${glossesListHtml}
        </div>
      </div>

      <div class="inspector-section">
        <div class="inspector-label">Segmentos Contenidos (${sentence.segments ? sentence.segments.length : 0})</div>
        <div style="display:flex; flex-wrap:wrap; gap:4px; margin-top:2px;" id="insp-sentence-segs-container">
          ${segsHtml}
        </div>
      </div>

      <div class="inspector-section" style="margin-top: 8px;">
        <button class="btn btn-primary btn-sm" id="btn-jump-to-sentence-start" style="width:100%; justify-content:center; gap:6px;">
          <span>▶</span>
          <span>Reproducir desde el inicio</span>
        </button>
      </div>
    `;

    // Interacciones dentro del inspector de frase
    const jumpBtn = this.bodyEl.querySelector('#btn-jump-to-sentence-start');
    if (jumpBtn) {
      jumpBtn.addEventListener('click', () => {
        appState.setCurrentTime(st, 'inspector_sentence_jump');
        appState.setIsPlaying(true);
      });
    }

    const addGlossBtn = this.bodyEl.querySelector('#btn-insp-add-gloss');
    if (addGlossBtn) {
      addGlossBtn.addEventListener('click', () => {
        const name = prompt(`Nueva glosa para la Frase ${sentence.index}:`, 'NUEVA_GLOSA');
        if (name && name.trim()) {
          appState.addGlossToSentence(sentence.id, { gloss: name.trim() });
        }
      });
    }

    const addPauseBtn = this.bodyEl.querySelector('#btn-insp-add-pause');
    if (addPauseBtn) {
      addPauseBtn.addEventListener('click', () => {
        appState.insertPause(sentence.id);
      });
    }

    const segBtns = this.bodyEl.querySelectorAll('.sentence-linked-seg-btn');
    segBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const sId = btn.dataset.segmentId;
        const targetSeg = (sentence.segments || []).find(s => s.id === sId);
        if (targetSeg) {
          appState.setCurrentTime(targetSeg.start_seconds !== undefined ? targetSeg.start_seconds : (targetSeg.start_time || st), 'inspector_seg_click');
          appState.selectItem('segment', targetSeg.id, targetSeg);
        }
      });
    });

    const glossChips = this.bodyEl.querySelectorAll('.gloss-chip[data-gloss-id]');
    glossChips.forEach(chip => {
      chip.addEventListener('click', (e) => {
        e.stopPropagation();
        const gId = chip.dataset.glossId;
        const targetGloss = (sentence.glosses || []).find(g => g.id === gId);
        if (targetGloss) {
          const gTime = targetGloss.start_seconds !== undefined ? targetGloss.start_seconds : (targetGloss.start || st);
          appState.setCurrentTime(gTime, 'inspector_gloss_click');
          appState.selectItem('gloss', targetGloss.id, targetGloss);
        }
      });
    });

    // Reordenar izquierda/derecha por botones en el inspector
    this.bodyEl.querySelectorAll('.btn-reorder-left').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const gId = btn.dataset.glossId;
        const idx = parseInt(btn.dataset.index, 10);
        appState.reorderGlossInSentence(sentence.id, gId, Math.max(0, idx - 1));
      });
    });

    this.bodyEl.querySelectorAll('.btn-reorder-right').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const gId = btn.dataset.glossId;
        const idx = parseInt(btn.dataset.index, 10);
        appState.reorderGlossInSentence(sentence.id, gId, idx + 1);
      });
    });

    this.bodyEl.querySelectorAll('.btn-insp-dup').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        appState.duplicateGloss(sentence.id, btn.dataset.glossId);
      });
    });

    this.bodyEl.querySelectorAll('.btn-insp-del').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        appState.deleteGloss(sentence.id, btn.dataset.glossId);
      });
    });
  }

  renderGlossInspector(gloss) {
    if (!this.titleEl || !this.bodyEl) return;

    this.titleEl.textContent = `Glosa: ${gloss.gloss || gloss.lemma || ''}`;
    if (this.badgeEl) {
      const isRev = gloss.status === 'REVIEW_REQUIRED' || gloss.status === 'BLOCKED' || gloss.status === 'AUDIO_REVIEW';
      this.badgeEl.innerHTML = `<span class="badge-status ${isRev ? 'review' : (gloss.color || 'validated')}">${gloss.gloss_type || 'SEÑA'}</span>`;
    }

    const st = gloss.start_seconds !== undefined ? gloss.start_seconds : (gloss.start || 0);
    const et = gloss.end_seconds !== undefined ? gloss.end_seconds : (gloss.end || 0);
    const dur = gloss.duration !== undefined ? gloss.duration : Math.max(0.1, et - st);

    // Encontrar frase padre
    const units = appState.getSentenceUnits();
    const parentSentence = units.find(u => (u.glosses || []).some(g => g.id === gloss.id)) || null;

    // Validar invariantes para esta glosa
    const violations = [];
    if (typeof StructuralValidator !== 'undefined' && parentSentence) {
      const allV = StructuralValidator.validateSentence(parentSentence, appState.state.project);
      allV.forEach(v => {
        if (!v.affected_ids || v.affected_ids.includes(gloss.id) || v.affected_ids.includes(parentSentence.id)) {
          violations.push(v);
        }
      });
    }

    const invariantAlertHtml = violations.length > 0
      ? `
        <div class="inspector-section invariant-alert-card" style="border-left: 3px solid var(--status-review); background: rgba(216, 168, 78, 0.12); padding: 8px; border-radius: 4px; margin-bottom: 8px;">
          <div class="inspector-label" style="color: var(--status-review); display:flex; align-items:center; gap:4px; font-weight:700;">
            <span>⚠</span>
            <span>Invariante Incumplida (${violations.length})</span>
          </div>
          <div style="font-size: 0.74rem; color: var(--text-primary); line-height: 1.4; margin-top: 4px;">
            ${violations.map(v => `<div>• <strong>[${v.code}]</strong> ${this.escapeHTML(v.message)}</div>`).join('')}
          </div>
        </div>
      `
      : '';

    const lociOptions = ['CENTRO', 'DERECHA', 'IZQUIERDA', 'ARRIBA', 'ABAJO', 'REFERENTE_1', 'REFERENTE_2'];
    const currentLocus = gloss.spatial_locus || 'CENTRO';

    const typeOptions = ['SEÑA', 'DACTILOLOGÍA', 'CLASIFICADOR', 'PAUSA'];
    const currentType = gloss.gloss_type || (gloss.is_pause ? 'PAUSA' : (gloss.is_fingerspelling ? 'DACTILOLOGÍA' : 'SEÑA'));

    const nonManualOptions = [
      'Atención neutra',
      'Cejas levantadas (Pregunta)',
      'Cejas fruncidas (Wh-)',
      'Negación con cabeza',
      'Asentimiento',
      'Intensificación facial',
      'Pausa transicional'
    ];
    const currentNMF = gloss.non_manual_features || ['Atención neutra'];

    this.bodyEl.innerHTML = `
      ${invariantAlertHtml}

      <!-- 1. Texto y Lema de la Glosa -->
      <div class="inspector-section">
        <div class="inspector-label">Texto de Glosa (Lema LSEC)</div>
        <input type="text" class="inspector-input" id="insp-gloss-text-input" value="${this.escapeHTML(gloss.gloss || gloss.lemma || '')}" style="font-weight:700; font-family:var(--font-mono); text-transform:uppercase;">
        <span style="font-size:0.68rem; color:var(--text-muted); margin-top:2px; display:block;">El ID permanente se conserva: <code>${gloss.id}</code></span>
      </div>

      <!-- 2. Tipo y Rol Sintáctico -->
      <div class="inspector-section" style="display:flex; gap:8px;">
        <div style="flex:1;">
          <div class="inspector-label">Tipo de Seña</div>
          <select class="inspector-select" id="insp-gloss-type-select">
            ${typeOptions.map(t => `<option value="${t}" ${t === currentType ? 'selected' : ''}>${t}</option>`).join('')}
          </select>
        </div>
        <div style="flex:1;">
          <div class="inspector-label">Locus Espacial</div>
          <select class="inspector-select" id="insp-gloss-locus-select">
            ${lociOptions.map(l => `<option value="${l}" ${l === currentLocus ? 'selected' : ''}>${l}</option>`).join('')}
          </select>
        </div>
      </div>

      <!-- 3. Duración y Temporización -->
      <div class="inspector-section">
        <div class="inspector-label">Duración y Tiempos</div>
        <div style="display:flex; align-items:center; gap:6px; margin-top:2px;">
          <button class="btn btn-secondary btn-sm" id="btn-gloss-dur-minus">-0.1s</button>
          <input type="number" step="0.05" min="0.1" max="10" id="insp-gloss-dur-input" value="${dur.toFixed(2)}" class="inspector-input" style="width:70px; text-align:center; font-family:var(--font-mono);">
          <button class="btn btn-secondary btn-sm" id="btn-gloss-dur-plus">+0.1s</button>
          <span style="font-family:var(--font-mono); font-size:0.72rem; color:var(--text-muted); margin-left:auto;">
            [${st.toFixed(2)}s - ${et.toFixed(2)}s]
          </span>
        </div>
      </div>

      <!-- 4. Rasgos No Manuales -->
      <div class="inspector-section">
        <div class="inspector-label">Rasgos No Manuales (Expresiones Faciales)</div>
        <select class="inspector-select" id="insp-gloss-nmf-select">
          ${nonManualOptions.map(opt => `<option value="${opt}" ${currentNMF.includes(opt) ? 'selected' : ''}>${opt}</option>`).join('')}
        </select>
      </div>

      <!-- 5. Trazabilidad y SourceAlignment -->
      <div class="inspector-section">
        <div class="inspector-label">Alineación con Fuente (SourceAlignment)</div>
        <div class="inspector-readout" style="display:flex; justify-content:space-between; align-items:center; font-size:0.74rem;">
          <span>Palabra: <strong>${gloss.source_word || gloss.normalized_word || '(Manual / Inferencia)'}</strong></span>
          <span class="badge-status ${gloss.alignment_status === 'PENDING' ? 'review' : 'validated'}" style="font-size:0.65rem;">
            ${gloss.alignment_status || 'ALINEADA'}
          </span>
        </div>
      </div>

      <!-- 6. Acciones Operacionales -->
      <div class="inspector-section" style="margin-top:10px; display:flex; flex-direction:column; gap:6px;">
        <div style="display:flex; gap:6px;">
          <button class="btn btn-secondary btn-sm" id="btn-gloss-dup" style="flex:1; justify-content:center; gap:4px;">
            <span>⧉</span>
            <span>Duplicar Glosa</span>
          </button>
          <button class="btn btn-secondary btn-sm" id="btn-gloss-del" style="flex:1; justify-content:center; gap:4px; color:var(--status-review);">
            <span>×</span>
            <span>Eliminar Glosa</span>
          </button>
        </div>

        <div style="display:flex; gap:6px;">
          <button class="btn btn-secondary btn-sm" id="btn-gloss-shift-left" style="flex:1; justify-content:center; gap:4px;">
            <span>◀</span>
            <span>Mover Izquierda</span>
          </button>
          <button class="btn btn-secondary btn-sm" id="btn-gloss-shift-right" style="flex:1; justify-content:center; gap:4px;">
            <span>Mover Derecha</span>
            <span>▶</span>
          </button>
        </div>

        <div style="display:flex; gap:6px;">
          <button class="btn btn-secondary btn-sm" id="btn-gloss-move-prev-sent" style="flex:1; justify-content:center; gap:4px; font-size:0.70rem;" title="Mover a la frase anterior">
            <span>▲ Frase Anterior</span>
          </button>
          <button class="btn btn-secondary btn-sm" id="btn-gloss-move-next-sent" style="flex:1; justify-content:center; gap:4px; font-size:0.70rem;" title="Mover a la frase siguiente">
            <span>Frase Siguiente ▼</span>
          </button>
        </div>
      </div>
    `;

    // Eventos de edición de texto/lema
    const txtInput = this.bodyEl.querySelector('#insp-gloss-text-input');
    if (txtInput) {
      txtInput.addEventListener('change', () => {
        const val = txtInput.value.trim().toUpperCase();
        if (val) {
          appState.updateGloss(gloss.id, { gloss: val, lemma: val });
        }
      });
      txtInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          txtInput.blur();
        }
      });
    }

    // Tipo de seña
    const typeSelect = this.bodyEl.querySelector('#insp-gloss-type-select');
    if (typeSelect) {
      typeSelect.addEventListener('change', () => {
        const val = typeSelect.value;
        const isPause = val === 'PAUSA';
        const isFs = val === 'DACTILOLOGÍA';
        appState.updateGloss(gloss.id, {
          gloss_type: val,
          is_pause: isPause,
          is_fingerspelling: isFs,
          gloss: isPause ? '[PAUSA]' : gloss.gloss
        });
      });
    }

    // Locus espacial
    const locusSelect = this.bodyEl.querySelector('#insp-gloss-locus-select');
    if (locusSelect) {
      locusSelect.addEventListener('change', () => {
        appState.updateGlossSpatialLocus(gloss.id, locusSelect.value);
      });
    }

    // Rasgos no manuales
    const nmfSelect = this.bodyEl.querySelector('#insp-gloss-nmf-select');
    if (nmfSelect) {
      nmfSelect.addEventListener('change', () => {
        appState.updateGlossNonManual(gloss.id, [nmfSelect.value]);
      });
    }

    // Ajuste de duración
    const durInput = this.bodyEl.querySelector('#insp-gloss-dur-input');
    const durMinus = this.bodyEl.querySelector('#btn-gloss-dur-minus');
    const durPlus = this.bodyEl.querySelector('#btn-gloss-dur-plus');

    if (durInput) {
      durInput.addEventListener('change', () => {
        const d = parseFloat(durInput.value);
        if (d > 0.05) {
          appState.updateGlossTiming(gloss.id, { duration: d });
        }
      });
    }

    if (durMinus) {
      durMinus.addEventListener('click', () => {
        const d = Math.max(0.1, dur - 0.1);
        appState.updateGlossTiming(gloss.id, { duration: d });
      });
    }

    if (durPlus) {
      durPlus.addEventListener('click', () => {
        const d = dur + 0.1;
        appState.updateGlossTiming(gloss.id, { duration: d });
      });
    }

    // Acciones operacionales
    const dupBtn = this.bodyEl.querySelector('#btn-gloss-dup');
    if (dupBtn && parentSentence) {
      dupBtn.addEventListener('click', () => {
        appState.duplicateGloss(parentSentence.id, gloss.id);
      });
    }

    const delBtn = this.bodyEl.querySelector('#btn-gloss-del');
    if (delBtn && parentSentence) {
      delBtn.addEventListener('click', () => {
        appState.deleteGloss(parentSentence.id, gloss.id);
      });
    }

    // Mover a la izquierda / derecha
    const shiftLeftBtn = this.bodyEl.querySelector('#btn-gloss-shift-left');
    if (shiftLeftBtn && parentSentence) {
      const idx = (parentSentence.glosses || []).findIndex(g => g.id === gloss.id);
      shiftLeftBtn.disabled = idx <= 0;
      shiftLeftBtn.addEventListener('click', () => {
        appState.reorderGlossInSentence(parentSentence.id, gloss.id, Math.max(0, idx - 1));
      });
    }

    const shiftRightBtn = this.bodyEl.querySelector('#btn-gloss-shift-right');
    if (shiftRightBtn && parentSentence) {
      const idx = (parentSentence.glosses || []).findIndex(g => g.id === gloss.id);
      shiftRightBtn.disabled = idx >= (parentSentence.glosses || []).length - 1;
      shiftRightBtn.addEventListener('click', () => {
        appState.reorderGlossInSentence(parentSentence.id, gloss.id, idx + 1);
      });
    }

    // Mover a frase anterior / siguiente
    const movePrevBtn = this.bodyEl.querySelector('#btn-gloss-move-prev-sent');
    if (movePrevBtn && parentSentence) {
      const allS = appState.getSentenceUnits();
      const sIdx = allS.findIndex(u => u.id === parentSentence.id);
      movePrevBtn.disabled = sIdx <= 0;
      movePrevBtn.addEventListener('click', () => {
        if (sIdx > 0) {
          appState.moveGlossBetweenSentences(parentSentence.id, allS[sIdx - 1].id, gloss.id, -1);
        }
      });
    }

    const moveNextBtn = this.bodyEl.querySelector('#btn-gloss-move-next-sent');
    if (moveNextBtn && parentSentence) {
      const allS = appState.getSentenceUnits();
      const sIdx = allS.findIndex(u => u.id === parentSentence.id);
      moveNextBtn.disabled = sIdx < 0 || sIdx >= allS.length - 1;
      moveNextBtn.addEventListener('click', () => {
        if (sIdx >= 0 && sIdx < allS.length - 1) {
          appState.moveGlossBetweenSentences(parentSentence.id, allS[sIdx + 1].id, gloss.id, 0);
        }
      });
    }
  }

  renderLocusInspector(data) {
    if (!this.titleEl || !this.bodyEl) return;
    this.titleEl.textContent = 'Espacio de Señas (Locus)';
    if (this.badgeEl) this.badgeEl.innerHTML = `<span class="badge-status corrected">Espacial</span>`;
    this.bodyEl.innerHTML = `
      <div class="inspector-section">
        <div class="inspector-label">Referencia en el Espacio</div>
        <div class="inspector-readout highlight">
          Espacio Asignado: <strong>${data.space || 'CENTRO'}</strong>
        </div>
      </div>
    `;
  }

  renderNonManualInspector(data) {
    if (!this.titleEl || !this.bodyEl) return;
    this.titleEl.textContent = 'Expresión No Manual';
    if (this.badgeEl) this.badgeEl.innerHTML = `<span class="badge-status review">Facial</span>`;
    this.bodyEl.innerHTML = `
      <div class="inspector-section">
        <div class="inspector-label">Rasgo Facial / Corporal</div>
        <div class="inspector-readout highlight">
          Rasgo: <strong>${data.expression || 'Cejas levantadas'}</strong>
        </div>
      </div>
    `;
  }

  renderSegmentInspector(segment) {
    if (!this.titleEl || !this.bodyEl) return;

    this.titleEl.textContent = `Segmento: ${segment.id || ''}`;
    if (this.badgeEl) {
      const isRev = segment.status === 'REVIEW_REQUIRED' || segment.status === 'AUDIO_REVIEW' || segment.status === 'NATIVE_REVIEW' || segment.status === 'BLOCKED';
      this.badgeEl.innerHTML = `<span class="badge-status ${isRev ? 'review' : 'validated'}">${segment.status || 'OK'}</span>`;
    }

    const st = segment.start_seconds !== undefined ? segment.start_seconds : (segment.start_time || 0);
    const et = segment.end_seconds !== undefined ? segment.end_seconds : (segment.end_time || 0);
    const dur = segment.duration !== undefined ? segment.duration : Math.max(0, et - st);

    const units = appState.getSentenceUnits();
    const parentSentence = units.find(u => (u.segments || []).some(s => s.id === segment.id)) || null;

    this.bodyEl.innerHTML = `
      <div class="inspector-section">
        <div class="inspector-label">Intervalo Temporal</div>
        <div class="inspector-readout" style="font-family: var(--font-mono); font-size: 0.75rem;">
          [${this.formatMinuteSeconds(st)}] → [${this.formatMinuteSeconds(et)}] (${dur.toFixed(2)}s)
        </div>
      </div>

      <div class="inspector-section">
        <div class="inspector-label">Texto Reconocido</div>
        <div class="inspector-readout" style="font-size: 0.78rem; line-height: 1.4; color: var(--text-primary); font-weight: 500;">
          "${this.escapeHTML(segment.normalized_text || segment.text || '')}"
        </div>
      </div>

      <div class="inspector-section">
        <div class="inspector-label">Confianza Acústica</div>
        <div class="inspector-readout" style="font-size: 0.75rem; color: ${(segment.confidence !== undefined && segment.confidence < 0.7) ? 'var(--status-review)' : 'var(--status-validated)'};">
          ${(((segment.confidence !== undefined ? segment.confidence : 0.95)) * 100).toFixed(1)}%
        </div>
      </div>

      ${parentSentence ? `
        <div class="inspector-section">
          <div class="inspector-label">Frase Asociada</div>
          <button class="btn btn-secondary btn-sm" id="btn-insp-jump-parent-sentence" style="width:100%; justify-content:center; gap:6px;">
            <span>Ir a Frase ${parentSentence.index}</span>
          </button>
        </div>
      ` : ''}

      <div class="inspector-section" style="margin-top: 8px;">
        <button class="btn btn-primary btn-sm" id="btn-jump-to-segment-start" style="width:100%; justify-content:center; gap:6px;">
          <span>▶ Reproducir segmento</span>
        </button>
      </div>
    `;

    const jumpBtn = this.bodyEl.querySelector('#btn-jump-to-segment-start');
    if (jumpBtn) {
      jumpBtn.addEventListener('click', () => {
        appState.setCurrentTime(st, 'inspector_segment_jump');
        appState.setIsPlaying(true);
      });
    }

    const jumpSentenceBtn = this.bodyEl.querySelector('#btn-insp-jump-parent-sentence');
    if (jumpSentenceBtn && parentSentence) {
      jumpSentenceBtn.addEventListener('click', () => {
        appState.selectItem('sentence', parentSentence.id, parentSentence);
      });
    }
  }

  renderIssueInspector(issue) {
    if (!this.titleEl || !this.bodyEl) return;
    this.titleEl.textContent = 'Incidencia Lingüística';
    if (this.badgeEl) this.badgeEl.innerHTML = `<span class="badge-status review">Revisar</span>`;
    this.bodyEl.innerHTML = `
      <div class="inspector-section">
        <div class="inspector-label">Descripción del Problema</div>
        <div class="inspector-readout" style="border-left: 3px solid var(--status-review);">
          ${this.escapeHTML(issue.message || 'Desalineación temporal detectada.')}
        </div>
      </div>
    `;
  }

  escapeHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}

// Exportación
if (typeof window !== 'undefined') {
  window.SidebarPanelsController = ContextualInspectorController;
  window.ContextualInspectorController = ContextualInspectorController;
}
