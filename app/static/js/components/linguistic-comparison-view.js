/**
 * LSEC Studio — Controlador de la Ventana 2 («2. Motor Lingüístico y Glosas LSEC»)
 *
 * 1. Monitor Visual de Transformación Gramatical (SVO -> TIEMPO + TÓPICO + SOV + NEGACIÓN):
 *    - Tacha suavemente palabras omitidas por elisión (artículos, copulativos, preposiciones).
 *    - Destaca verbos llevados a infinitivo.
 *    - Muestra etiquetas azules (#0284c7) de las reglas lingüísticas LSEC/FENASEC aplicadas.
 * 2. Mesa Comparativa Paralela de 2 Columnas Sincronizadas:
 *    - Columna Izquierda: Oración en español editable in-situ + marca de tiempo + botón "Re-traducir fila".
 *    - Columna Derecha: Fichas táctiles de glosas LSEC al frente de cada oración
 *      (Seña CONADIS #10b981, Dactilología #0284c7, Editada HUMAN_VERIFIED #f59e0b)
 *      con edición inline, adición, borrado y reordenamiento sin scroll largo.
 */

const ELIDED_SPANISH_WORDS = new Set([
  'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
  'es', 'son', 'está', 'están', 'fue', 'era', 'ser', 'estar', 'sido',
  'de', 'del', 'a', 'al', 'en', 'con', 'por', 'para', 'que', 'se', 'lo', 'le', 'les', 'y', 'o'
]);

const TIME_MARKERS_SET = new Set([
  'HOY', 'AYER', 'MAÑANA', 'MANANA', 'AHORA', 'ANTES', 'DESPUÉS', 'DESPUES',
  'SIEMPRE', 'NUNCA', 'PASADO', 'FUTURO', 'SEMANA', 'MES', 'AÑO', 'ANO', 'DÍA', 'DIA'
]);

const NEGATION_MARKERS_SET = new Set([
  'NO', 'NADA', 'NUNCA', 'JAMÁS', 'JAMAS', 'NINGUNO', 'TAMPOCO'
]);

class LinguisticComparisonView {
  constructor() {
    this.rowsContainer = document.getElementById('comparative-rows-container');
    this.spanishTokensEl = document.getElementById('grammar-spanish-tokens');
    this.lsecTokensEl = document.getElementById('grammar-lsec-tokens');
    this.rulesListEl = document.getElementById('grammar-applied-rules-list');
    this.sentenceBadgeEl = document.getElementById('grammar-active-sentence-index');
    this.coverageBadgeEl = document.getElementById('comparative-coverage-badge');
    this.btnRetranslateAll = document.getElementById('btn-retranslate-all-rows');

    this.selectedSegmentIndex = 0;
    this.init();
  }

  init() {
    this.bindGlobalEvents();
    this.subscribeToState();
    this.renderAll();
  }

  bindGlobalEvents() {
    if (this.btnRetranslateAll) {
      this.btnRetranslateAll.addEventListener('click', () => this.retranslateAllRows());
    }
  }

  subscribeToState() {
    if (typeof appState === 'undefined') return;

    appState.subscribe('projectLoaded', () => {
      this.selectedSegmentIndex = 0;
      this.renderAll();
    });
    appState.subscribe('projectUpdated', () => this.renderAll());
    appState.subscribe('segmentsChanged', () => this.renderAll());
    appState.subscribe('glossesChanged', () => this.renderAll());
  }

  getSegmentsList() {
    if (typeof appState === 'undefined' || !appState.state?.project) return [];
    return appState.state.project.segments || [];
  }

  getGlossObjectsForSegment(seg) {
    if (!seg || typeof appState === 'undefined' || !appState.state?.project) return [];
    const project = appState.state.project;
    const units = typeof appState.getSentenceUnits === 'function' ? appState.getSentenceUnits() : [];
    const matchingUnit = units.find(u =>
      u.id === seg.id ||
      (Array.isArray(u.segments) && u.segments.some(s => s.id === seg.id))
    );

    if (matchingUnit && Array.isArray(matchingUnit.glosses) && matchingUnit.glosses.length > 0) {
      return matchingUnit.glosses;
    }

    const allGlosses = project.glosses || [];
    const bySegId = allGlosses.filter(g =>
      g.segment_id === seg.id ||
      (seg.proposition_id && g.prop_id === seg.proposition_id) ||
      (g.start_seconds !== undefined && g.start_seconds >= (seg.start_time - 0.1) && g.end_seconds <= (seg.end_time + 0.1)) ||
      (g.start_time !== undefined && g.start_time >= (seg.start_time - 0.1) && g.end_time <= (seg.end_time + 0.1))
    );

    if (bySegId.length > 0) return bySegId;

    const seq = Array.isArray(seg.gloss_sequence) ? seg.gloss_sequence : [];
    return seq.map((token, idx) => ({
      id: `${seg.id}_g_${idx}`,
      segment_id: seg.id,
      gloss: String(token).toUpperCase(),
      lemma: String(token).toUpperCase(),
      status: seg.status === 'HUMAN_VERIFIED' ? 'HUMAN_VERIFIED' : 'VALIDATED',
      manually_edited: Boolean(seg.manually_edited),
      is_fingerspelling: String(token).includes('-') || String(token).startsWith('FS:')
    }));
  }

  classifyChipStatus(glossObj) {
    const rawToken = String(glossObj?.gloss || glossObj?.lemma || '').toUpperCase();
    const isEdited = Boolean(
      glossObj?.manually_edited ||
      glossObj?.status === 'HUMAN_VERIFIED' ||
      glossObj?.alignment_type === 'MANUAL_EDIT'
    );
    const isFingerspell = Boolean(
      glossObj?.is_fingerspelling ||
      glossObj?.source === 'FINGERSPELLING' ||
      glossObj?.gloss_type === 'DACTILOLOGÍA' ||
      rawToken.startsWith('FS:') ||
      (rawToken.includes('-') && rawToken.split('-').every(part => part.length === 1))
    );

    if (isEdited) {
      return {
        cssClass: 'gloss-chip-edited',
        badgeText: 'Editada',
        statusKey: 'HUMAN_VERIFIED'
      };
    }
    if (isFingerspell) {
      return {
        cssClass: 'gloss-chip-fingerspell',
        badgeText: 'Dactilología',
        statusKey: 'FINGERSPELLING'
      };
    }
    return {
      cssClass: 'gloss-chip-conadis',
      badgeText: 'Seña CONADIS',
      statusKey: 'CONADIS'
    };
  }

  isInfinitiveVerb(wordUpper, glossTokensSet) {
    const clean = wordUpper.toLowerCase().replace(/[^a-záéíóúñ]/gi, '');
    if (clean.length < 3) return false;
    if (/^(ar|er|ir)$/i.test(clean.slice(-2)) && glossTokensSet.has(clean.toUpperCase())) {
      return true;
    }
    for (const g of glossTokensSet) {
      if (g.length >= 4 && /^(AR|ER|IR)$/.test(g.slice(-2))) {
        const stem = g.slice(0, -2).toLowerCase();
        if (clean.startsWith(stem.slice(0, Math.max(3, stem.length - 1)))) {
          return g;
        }
      }
    }
    return false;
  }

  renderAll() {
    const segments = this.getSegmentsList();
    if (this.selectedSegmentIndex >= segments.length) {
      this.selectedSegmentIndex = Math.max(0, segments.length - 1);
    }
    this.renderGrammarMonitor(segments[this.selectedSegmentIndex], this.selectedSegmentIndex);
    this.renderParallelRows(segments);
    this.updateCoverageBadge(segments);
  }

  updateCoverageBadge(segments) {
    if (!this.coverageBadgeEl) return;
    let total = 0;
    let conadisCount = 0;
    let editedCount = 0;
    segments.forEach((seg) => {
      const glosses = this.getGlossObjectsForSegment(seg);
      glosses.forEach((g) => {
        total++;
        const info = this.classifyChipStatus(g);
        if (info.statusKey === 'CONADIS') conadisCount++;
        if (info.statusKey === 'HUMAN_VERIFIED') editedCount++;
      });
    });
    this.coverageBadgeEl.textContent = total > 0
      ? `${conadisCount}/${total} Señas CONADIS · ${editedCount} Editadas`
      : '4.252 Fichas CONADIS';
  }

  renderGrammarMonitor(seg, index = 0) {
    if (!this.spanishTokensEl || !this.lsecTokensEl || !this.rulesListEl) return;

    if (!seg) {
      if (this.sentenceBadgeEl) this.sentenceBadgeEl.textContent = 'Sin Oración';
      this.spanishTokensEl.innerHTML = '<span class="grammar-token-word">Carga o transcribe un video en el Paso 1</span>';
      this.lsecTokensEl.innerHTML = '<span class="grammar-token-word">EN ESPERA DE GLOSAS LSEC</span>';
      this.rulesListEl.innerHTML = '<span class="grammar-rule-badge">Estructura SOV</span>';
      return;
    }

    if (this.sentenceBadgeEl) {
      this.sentenceBadgeEl.textContent = `Oración #${index + 1}`;
    }

    const spanishText = seg.normalized_text || seg.raw_text || seg.original_text || '';
    const rawWords = spanishText.split(/\s+/).filter(Boolean);
    const glossObjects = this.getGlossObjectsForSegment(seg);
    const glossTokens = glossObjects.map(g => String(g.gloss || g.lemma || '').toUpperCase());
    const glossSet = new Set(glossTokens);

    this.spanishTokensEl.innerHTML = '';
    let elidedCount = 0;
    let infinitiveCount = 0;

    rawWords.forEach((rawWord) => {
      const cleanLower = rawWord.toLowerCase().replace(/[.,;!?¿¡"()]/g, '');
      const span = document.createElement('span');

      if (ELIDED_SPANISH_WORDS.has(cleanLower)) {
        elidedCount++;
        span.className = 'grammar-token-elided';
        span.title = 'Palabra funcional omitida por elisión gramatical en LSEC';
        span.textContent = rawWord;
      } else {
        const matchedInf = this.isInfinitiveVerb(cleanLower, glossSet);
        if (matchedInf) {
          infinitiveCount++;
          span.className = 'grammar-token-infinitive';
          span.title = 'Verbo lematizado a infinitivo en LSEC';
          span.textContent = typeof matchedInf === 'string' ? `${rawWord} (${matchedInf})` : rawWord;
        } else {
          span.className = 'grammar-token-word';
          span.textContent = rawWord;
        }
      }
      this.spanishTokensEl.appendChild(span);
    });

    // Renderizar Estructura LSEC (TIEMPO + TÓPICO + SOV + NEGACIÓN)
    this.lsecTokensEl.innerHTML = '';
    let hasTimeMarker = false;
    let hasNegation = false;

    glossObjects.forEach((g) => {
      const token = String(g.gloss || g.lemma || '').toUpperCase();
      if (TIME_MARKERS_SET.has(token)) hasTimeMarker = true;
      if (NEGATION_MARKERS_SET.has(token)) hasNegation = true;

      const info = this.classifyChipStatus(g);
      const chip = document.createElement('span');
      chip.className = `gloss-chip-tactile ${info.cssClass}`;
      chip.style.padding = '4px 10px';
      chip.style.fontSize = '0.82rem';
      chip.textContent = token;
      this.lsecTokensEl.appendChild(chip);
    });

    // Etiquetas azules (#0284c7) de reglas lingüísticas aplicadas
    const rules = ['Reordenamiento Sintáctico SVO -> SOV'];
    if (elidedCount > 0) rules.push(`Elisión de Artículos/Copulativos (${elidedCount})`);
    if (infinitiveCount > 0) rules.push('Verbos en Infinitivo');
    if (hasTimeMarker) rules.push('Marcador Temporal al Inicio (TIEMPO)');
    if (hasNegation) rules.push('Negación Post-Verbal (NEGACIÓN)');
    if (Array.isArray(seg.applied_rules)) {
      seg.applied_rules.slice(0, 3).forEach((r) => {
        const label = typeof r === 'string' ? r : (r.rule_name || r.name || r.code);
        if (label && !rules.includes(label)) rules.push(label);
      });
    }

    this.rulesListEl.innerHTML = '';
    rules.forEach((ruleText) => {
      const badge = document.createElement('span');
      badge.className = 'grammar-rule-badge';
      badge.textContent = ruleText;
      this.rulesListEl.appendChild(badge);
    });
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

  renderParallelRows(segments) {
    if (!this.rowsContainer) return;

    if (!segments || segments.length === 0) {
      this.rowsContainer.innerHTML = `
        <div class="empty-state-box" style="margin:20px;">
          No hay oraciones cargadas. Regresa a la <strong>Ventana 1 (Transcripción con Whisper)</strong> para extraer o agregar oraciones.
        </div>
      `;
      return;
    }

    this.rowsContainer.innerHTML = '';

    segments.forEach((seg, rowIndex) => {
      const row = document.createElement('div');
      row.className = `comparative-row ${rowIndex === this.selectedSegmentIndex ? 'selected-row' : ''}`;
      row.dataset.segId = seg.id;
      row.dataset.rowIndex = String(rowIndex);

      const spanishText = seg.normalized_text || seg.raw_text || seg.original_text || '';
      const timeRange = this.formatTimeRange(seg.start_time ?? seg.start_seconds, seg.end_time ?? seg.end_seconds);
      const glossObjects = this.getGlossObjectsForSegment(seg);

      // 1. Columna Izquierda: TRANSCRIPCIÓN OBTENIDA - WHISPER
      const leftCell = document.createElement('div');
      leftCell.className = 'comparative-cell-spanish';
      leftCell.innerHTML = `
        <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
          <button type="button" class="transcript-seg-time-badge" data-action="select-and-seek" title="Inspeccionar esta oración en el monitor gramatical y reproducir">
            <span>Oración #${rowIndex + 1}</span>
            <span>${timeRange}</span>
          </button>
          <button type="button" class="btn btn-cobalt btn-sm" data-action="retranslate-row" title="Re-traducir esta fila con spaCy y reglas LSEC">
            Re-traducir fila
          </button>
        </div>
        <textarea class="transcript-seg-input" rows="2" aria-label="Oración en español fila ${rowIndex + 1}">${this.escapeHtml(spanishText)}</textarea>
      `;

      const selectSeekBtn = leftCell.querySelector('[data-action="select-and-seek"]');
      if (selectSeekBtn) {
        selectSeekBtn.addEventListener('click', () => {
          this.selectedSegmentIndex = rowIndex;
          this.renderGrammarMonitor(seg, rowIndex);
          this.highlightSelectedRow();
          if (typeof appState !== 'undefined') {
            appState.setCurrentTime(Number(seg.start_time ?? seg.start_seconds) || 0, true);
          }
        });
      }

      const textarea = leftCell.querySelector('.transcript-seg-input');
      if (textarea) {
        textarea.addEventListener('focus', () => {
          this.selectedSegmentIndex = rowIndex;
          this.renderGrammarMonitor(seg, rowIndex);
          this.highlightSelectedRow();
        });
        textarea.addEventListener('change', (e) => {
          const newText = e.target.value.trim();
          appState.updateSegment(seg.id, {
            normalized_text: newText,
            raw_text: newText,
            status: 'CORRECTED'
          });
        });
      }

      const retranslateBtn = leftCell.querySelector('[data-action="retranslate-row"]');
      if (retranslateBtn) {
        retranslateBtn.addEventListener('click', async () => {
          const currentText = textarea ? textarea.value.trim() : spanishText;
          retranslateBtn.disabled = true;
          retranslateBtn.textContent = 'Traduciendo...';
          try {
            await this.retranslateSingleRow(seg, currentText, rowIndex);
          } finally {
            retranslateBtn.disabled = false;
            retranslateBtn.textContent = 'Re-traducir fila';
          }
        });
      }

      // 2. Columna Derecha: CONTRAPARTE EN GLOSAS LSEC (Fichas táctiles frente a cada oración)
      const rightCell = document.createElement('div');
      rightCell.className = 'comparative-cell-glosses';

      const rack = document.createElement('div');
      rack.className = 'gloss-chips-rack';

      glossObjects.forEach((glossObj, gIdx) => {
        const chipEl = this.createTactileGlossChip(seg, glossObj, gIdx, glossObjects.length, rowIndex);
        rack.appendChild(chipEl);
      });

      // Botón inline "+ Glosa"
      const addBtn = document.createElement('button');
      addBtn.type = 'button';
      addBtn.className = 'btn btn-sm';
      addBtn.textContent = '+ Glosa';
      addBtn.title = 'Agregar nueva glosa LSEC a esta oración';
      addBtn.addEventListener('click', () => {
        this.openInlineNewGlossInput(rack, addBtn, seg, rowIndex);
      });
      rack.appendChild(addBtn);

      rightCell.appendChild(rack);
      row.appendChild(leftCell);
      row.appendChild(rightCell);
      this.rowsContainer.appendChild(row);
    });
  }

  createTactileGlossChip(seg, glossObj, gIdx, totalGlosses, rowIndex) {
    const info = this.classifyChipStatus(glossObj);
    const token = String(glossObj.gloss || glossObj.lemma || '').toUpperCase();

    const chip = document.createElement('div');
    chip.className = `gloss-chip-tactile ${info.cssClass}`;
    chip.dataset.glossId = glossObj.id || `${seg.id}_${gIdx}`;
    chip.dataset.glossIndex = String(gIdx);
    chip.title = `${token} (${info.badgeText}) — Clic en el nombre para editar`;

    chip.innerHTML = `
      <span class="gloss-chip-text" data-action="edit-gloss">${this.escapeHtml(token)}</span>
      <span class="gloss-chip-badge-tag">${info.badgeText}</span>
      <span class="gloss-chip-actions">
        ${gIdx > 0 ? '<button type="button" class="gloss-chip-btn" data-action="move-left" title="Mover a la izquierda" aria-label="Mover glosa a la izquierda">&lt;</button>' : ''}
        ${gIdx < totalGlosses - 1 ? '<button type="button" class="gloss-chip-btn" data-action="move-right" title="Mover a la derecha" aria-label="Mover glosa a la derecha">&gt;</button>' : ''}
        <button type="button" class="gloss-chip-btn" data-action="delete-gloss" title="Eliminar glosa" aria-label="Eliminar glosa">&times;</button>
      </span>
    `;

    // Edición inline de la glosa (RF-05: HUMAN_VERIFIED en color ámbar #f59e0b)
    const textEl = chip.querySelector('[data-action="edit-gloss"]');
    if (textEl) {
      textEl.addEventListener('click', (e) => {
        e.stopPropagation();
        this.openInlineGlossEditor(chip, seg, glossObj, gIdx, rowIndex);
      });
    }

    const leftBtn = chip.querySelector('[data-action="move-left"]');
    if (leftBtn) {
      leftBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.reorderGlossInRow(seg, glossObj, gIdx, gIdx - 1, rowIndex);
      });
    }

    const rightBtn = chip.querySelector('[data-action="move-right"]');
    if (rightBtn) {
      rightBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.reorderGlossInRow(seg, glossObj, gIdx, gIdx + 1, rowIndex);
      });
    }

    const delBtn = chip.querySelector('[data-action="delete-gloss"]');
    if (delBtn) {
      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.deleteGlossFromRow(seg, glossObj, gIdx, rowIndex);
      });
    }

    return chip;
  }

  openInlineGlossEditor(chipEl, seg, glossObj, gIdx, rowIndex) {
    const currentVal = String(glossObj.gloss || glossObj.lemma || '').toUpperCase();
    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentVal;
    input.className = 'transcript-seg-input';
    input.style.width = `${Math.max(96, currentVal.length * 12 + 28)}px`;
    input.style.minHeight = '30px';
    input.style.padding = '2px 8px';
    input.style.textTransform = 'uppercase';
    input.style.fontWeight = '800';

    const commit = () => {
      const nextToken = input.value.trim().toUpperCase();
      if (nextToken && nextToken !== currentVal) {
        this.updateGlossInRow(seg, glossObj, gIdx, nextToken, rowIndex);
      } else {
        this.renderAll();
      }
    };

    input.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        commit();
      } else if (ev.key === 'Escape') {
        this.renderAll();
      }
    });
    input.addEventListener('blur', commit);

    chipEl.innerHTML = '';
    chipEl.appendChild(input);
    input.focus();
    input.select();
  }

  openInlineNewGlossInput(rackEl, addBtnEl, seg, rowIndex) {
    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'NUEVA GLOSA...';
    input.className = 'transcript-seg-input';
    input.style.width = '135px';
    input.style.minHeight = '34px';
    input.style.padding = '4px 8px';
    input.style.textTransform = 'uppercase';
    input.style.fontWeight = '800';

    let committed = false;
    const finish = (save) => {
      if (committed) return;
      committed = true;
      const val = input.value.trim().toUpperCase();
      if (save && val) {
        this.addGlossToRow(seg, val, rowIndex);
      } else {
        this.renderAll();
      }
    };

    input.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        finish(true);
      } else if (ev.key === 'Escape') {
        finish(false);
      }
    });
    input.addEventListener('blur', () => finish(true));

    rackEl.insertBefore(input, addBtnEl);
    addBtnEl.style.display = 'none';
    input.focus();
  }

  syncSegmentGlossesToProject(seg, updatedGlossObjects) {
    seg.gloss_sequence = updatedGlossObjects.map(g => String(g.gloss || g.lemma || '').toUpperCase());
    seg.status = 'HUMAN_VERIFIED';
    seg.human_reviewed = true;

    const project = appState?.state?.project;
    if (!project) return;

    const st = Number(seg.start_time ?? seg.start_seconds) || 0;
    const et = Number(seg.end_time ?? seg.end_seconds) || (st + 2.5);
    const dur = Math.max(0.25, (et - st) / Math.max(1, updatedGlossObjects.length));

    const timedGlosses = updatedGlossObjects.map((g, i) => {
      const gStart = Number((st + i * dur).toFixed(3));
      const gEnd = Number((st + (i + 1) * dur).toFixed(3));
      return {
        ...g,
        id: g.id || `g_${seg.id}_${i}_${Date.now().toString().slice(-3)}`,
        segment_id: seg.id,
        prop_id: seg.proposition_id || g.prop_id || seg.id,
        start_time: gStart,
        end_time: gEnd,
        start_seconds: gStart,
        end_seconds: gEnd,
        duration: Number(dur.toFixed(3))
      };
    });

    // Actualizar project.glosses reemplazando las glosas de este segmento
    const otherGlosses = (project.glosses || []).filter(g =>
      g.segment_id !== seg.id &&
      !(seg.proposition_id && g.prop_id === seg.proposition_id) &&
      !((g.start_time ?? g.start_seconds) >= st - 0.05 && (g.end_time ?? g.end_seconds) <= et + 0.05)
    );
    project.glosses = [...otherGlosses, ...timedGlosses].sort(
      (a, b) => (a.start_time ?? a.start_seconds ?? 0) - (b.start_time ?? b.start_seconds ?? 0)
    );

    // Sincronizar también sentence_units si existe
    if (Array.isArray(project.sentence_units)) {
      const unit = project.sentence_units.find(u =>
        u.id === seg.id || (Array.isArray(u.segments) && u.segments.some(s => s.id === seg.id))
      );
      if (unit) {
        unit.glosses = timedGlosses;
        unit.gloss_sequence = seg.gloss_sequence;
      }
    }

    appState.markUnsavedChange();
    appState.emit('glossesChanged', project.glosses);
    appState.emit('segmentsChanged', project.segments);
  }

  updateGlossInRow(seg, glossObj, gIdx, newToken, rowIndex) {
    this.selectedSegmentIndex = rowIndex;
    const list = [...this.getGlossObjectsForSegment(seg)];
    if (!list[gIdx]) return;

    list[gIdx] = {
      ...list[gIdx],
      gloss: newToken,
      lemma: newToken,
      status: 'HUMAN_VERIFIED',
      manually_edited: true,
      alignment_type: 'MANUAL_EDIT',
      is_fingerspelling: newToken.includes('-') || newToken.startsWith('FS:')
    };

    this.syncSegmentGlossesToProject(seg, list);
  }

  addGlossToRow(seg, newToken, rowIndex) {
    this.selectedSegmentIndex = rowIndex;
    const list = [...this.getGlossObjectsForSegment(seg)];
    list.push({
      id: `g_${seg.id}_${Date.now().toString().slice(-5)}`,
      segment_id: seg.id,
      gloss: newToken,
      lemma: newToken,
      status: 'HUMAN_VERIFIED',
      manually_edited: true,
      alignment_type: 'MANUAL_EDIT',
      is_fingerspelling: newToken.includes('-') || newToken.startsWith('FS:')
    });

    this.syncSegmentGlossesToProject(seg, list);
  }

  deleteGlossFromRow(seg, glossObj, gIdx, rowIndex) {
    this.selectedSegmentIndex = rowIndex;
    const list = [...this.getGlossObjectsForSegment(seg)];
    list.splice(gIdx, 1);
    this.syncSegmentGlossesToProject(seg, list);
  }

  reorderGlossInRow(seg, glossObj, fromIdx, toIdx, rowIndex) {
    this.selectedSegmentIndex = rowIndex;
    const list = [...this.getGlossObjectsForSegment(seg)];
    if (toIdx < 0 || toIdx >= list.length) return;
    const [moved] = list.splice(fromIdx, 1);
    moved.status = 'HUMAN_VERIFIED';
    moved.manually_edited = true;
    moved.alignment_type = 'MANUAL_EDIT';
    list.splice(toIdx, 0, moved);
    this.syncSegmentGlossesToProject(seg, list);
  }

  async retranslateSingleRow(seg, updatedSpanishText, rowIndex) {
    this.selectedSegmentIndex = rowIndex;
    appState.updateSegment(seg.id, {
      normalized_text: updatedSpanishText,
      raw_text: updatedSpanishText,
      status: 'CORRECTED'
    });

    const st = Number(seg.start_time ?? seg.start_seconds) || 0;
    const et = Number(seg.end_time ?? seg.end_seconds) || (st + 2.5);

    if (window.pipelineProcessor && typeof window.pipelineProcessor.translateSegmentViaBackend === 'function') {
      const result = await window.pipelineProcessor.translateSegmentViaBackend(updatedSpanishText, st, et, seg.id);
      if (result && Array.isArray(result.glosses) && result.glosses.length > 0) {
        seg.applied_rules = result.applied_rules || [];
        this.syncSegmentGlossesToProject(seg, result.glosses);
        if (typeof window.showToast === 'function') {
          window.showToast(`Fila #${rowIndex + 1} re-traducida con motor lingüístico LSEC.`, 'info');
        }
        return;
      }
    }

    // Respaldo local determinista si el endpoint está ocupado
    const fallbackTokens = updatedSpanishText
      .split(/\s+/)
      .map(w => w.replace(/[.,;!?¿¡"()]/g, '').toLowerCase())
      .filter(w => w && !ELIDED_SPANISH_WORDS.has(w))
      .map(w => w.toUpperCase());

    const fallbackObjects = (fallbackTokens.length > 0 ? fallbackTokens : ['ORACION']).map((tok, i) => ({
      id: `g_${seg.id}_re_${i}`,
      segment_id: seg.id,
      gloss: tok,
      lemma: tok,
      status: 'VALIDATED',
      manually_edited: false
    }));
    this.syncSegmentGlossesToProject(seg, fallbackObjects);
  }

  async retranslateAllRows() {
    const segments = this.getSegmentsList();
    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];
      const text = seg.normalized_text || seg.raw_text || '';
      await this.retranslateSingleRow(seg, text, i);
    }
    if (typeof window.showToast === 'function') {
      window.showToast('Todas las filas fueron re-procesadas con reglas LSEC.', 'success');
    }
  }

  highlightSelectedRow() {
    if (!this.rowsContainer) return;
    this.rowsContainer.querySelectorAll('.comparative-row').forEach((row) => {
      const idx = Number(row.dataset.rowIndex || '-1');
      row.classList.toggle('selected-row', idx === this.selectedSegmentIndex);
    });
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
  window.LinguisticComparisonView = LinguisticComparisonView;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { LinguisticComparisonView };
}
