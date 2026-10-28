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
    if (this.btnRetranslateAll) this.btnRetranslateAll.addEventListener('click', () => this.retranslateAllRows());
  }

  subscribeToState() {
    if (typeof appState === 'undefined') return;
    appState.subscribe('projectLoaded', () => { this.selectedSegmentIndex = 0; this.renderAll(); });
    appState.subscribe('projectUpdated', () => this.renderAll());
    appState.subscribe('segmentsChanged', () => this.renderAll());
    appState.subscribe('glossesChanged', () => this.renderAll());
  }

  getSegmentsList() {
    if (typeof appState === 'undefined' || !appState.state?.project) return [];
    return appState.state.project.segments || [];
  }

  deduplicateConsecutiveGlosses(glossList) {
    if (!Array.isArray(glossList) || glossList.length <= 1) return glossList || [];
    const result = [];
    for (const g of glossList) {
      const currNorm = this.formatCleanGlossLabel(g?.gloss || g?.lemma || '');
      const prev = result[result.length - 1];
      const prevNorm = prev ? this.formatCleanGlossLabel(prev?.gloss || prev?.lemma || '') : null;
      if (prev && currNorm && currNorm === prevNorm && !g?.manually_edited) continue;
      result.push(g);
    }
    return result;
  }

  formatCleanGlossLabel(rawToken) {
    return String(rawToken || '').toUpperCase().replace(/^FS:/i, '').replace(/\[[^\]]*\]/g, '').trim();
  }

  describeGlossNotation(rawToken, glossObj = {}) {
    const raw = String(rawToken || '').toUpperCase().replace(/^FS:/i, '').trim();
    const personNames = {
      '1': '1.ª persona singular (YO)',
      '1-PL': '1.ª persona plural (NOSOTROS)',
      '2': '2.ª persona singular (TÚ / USTED)',
      '2-PL': '2.ª persona plural (USTEDES)',
      '3': '3.ª persona singular (ÉL / ELLA)',
      '3-PL': '3.ª persona plural (ELLOS / ELLAS)'
    };
    const proMap = {
      'PRO1': {
        label: 'YO',
        badge: 'PRO1',
        category: 'Pronombre Deíctico (PRO1)',
        explanation: 'Indexación espacial de 1.ª persona singular: el dedo índice apunta hacia el pecho del propio signante («YO»).'
      },
      'PRO1-PL': {
        label: 'NOSOTROS',
        badge: 'PRO1-PL',
        category: 'Pronombre Deíctico Plural (PRO1-PL)',
        explanation: 'Indexación espacial de 1.ª persona plural («NOSOTROS/AS»).'
      },
      'PRO2': {
        label: 'TÚ',
        badge: 'PRO2',
        category: 'Pronombre Deíctico (PRO2)',
        explanation: 'Indexación espacial de 2.ª persona singular: el índice apunta hacia el interlocutor situado al frente («TÚ / USTED»).'
      },
      'PRO2-PL': {
        label: 'USTEDES',
        badge: 'PRO2-PL',
        category: 'Pronombre Deíctico Plural (PRO2-PL)',
        explanation: 'Indexación espacial de 2.ª persona plural hacia los interlocutores («USTEDES»).'
      },
      'PRO3': {
        label: 'ÉL/ELLA',
        badge: 'PRO3',
        category: 'Pronombre Deíctico / Anafórico (PRO3)',
        explanation: 'Indexación espacial de 3.ª persona singular: apunta a un punto (locus) lateral en el espacio de señado («ÉL / ELLA»).'
      },
      'PRO3-PL': {
        label: 'ELLOS',
        badge: 'PRO3-PL',
        category: 'Pronombre Deíctico Plural (PRO3-PL)',
        explanation: 'Indexación espacial hacia el locus de 3.ª persona plural («ELLOS / ELLAS»).'
      },
      'POSS1': {
        label: 'MÍO',
        badge: 'POSS1',
        category: 'Posesivo de 1.ª Persona (POSS1)',
        explanation: 'Posesivo en LSEC orientado hacia el signante («MÍO/A, MI»).'
      },
      'POSS2': {
        label: 'TUYO',
        badge: 'POSS2',
        category: 'Posesivo de 2.ª Persona (POSS2)',
        explanation: 'Posesivo en LSEC orientado hacia el interlocutor («TUYO/A, TU»).'
      },
      'POSS3': {
        label: 'SUYO',
        badge: 'POSS3',
        category: 'Posesivo de 3.ª Persona (POSS3)',
        explanation: 'Posesivo en LSEC orientado hacia el referente lateral («SUYO/A, SU»).'
      }
    };

    if (proMap[raw]) {
      return { ...proMap[raw], raw };
    }

    const dirMatch = raw.match(/^(.+?)\[([^\]]+)\]$/);
    if (dirMatch) {
      const baseVerb = dirMatch[1].replace(/\++$/, '').trim();
      const hasPlus = dirMatch[1].endsWith('++') || raw.endsWith('++');
      const rawVec = dirMatch[2].trim();
      const arrowParts = rawVec.split('->').map(s => s.trim());
      const fromP = personNames[arrowParts[0]] || `persona ${arrowParts[0]}`;
      const toP = personNames[arrowParts[1]] || `persona ${arrowParts[1]}`;
      const prettyVec = rawVec.replace('->', '→') + (hasPlus ? ' ++' : '');
      return {
        label: baseVerb,
        badge: prettyVec,
        raw,
        category: `Verbo Direccional de Concordancia [${rawVec}]`,
        explanation: `En LSEC el verbo «${baseVerb}» modifica la trayectoria espacial de las manos desde la ${fromP} hacia la ${toP}, absorbiendo los pronombres dentro del propio movimiento verbal.`
      };
    }

    if (raw.endsWith('++')) {
      const baseWord = raw.replace(/\++$/, '').trim();
      return {
        label: baseWord,
        badge: '++',
        raw,
        category: 'Reduplicación Segmental de Intensidad (++)',
        explanation: `La marca «++» indica reduplicación o énfasis cinemático de la seña «${baseWord}». En LSEC sustituye adverbios de grado («muy», «mucho», «demasiado») o superlativos («-ísimo»).`
      };
    }

    if (/^NO-(SABER|PODER|QUERER|GUSTAR|HABER|OÍR|OIR|ALCANZAR)$/.test(raw)) {
      return {
        label: raw,
        badge: 'NEG-INC',
        raw,
        category: 'Negación Léxica Incorporada (FENASEC)',
        explanation: `En LSEC ciertos verbos frecuentes («${raw.replace('NO-', '')}») no colocan «NO» separado al final, sino que poseen una seña léxica propia con negación incorporada («${raw}»).`
      };
    }

    if (TIME_MARKERS_SET.has(raw)) {
      return {
        label: raw,
        badge: 'TIEMPO',
        raw,
        category: 'Marcador de Marco Temporal Inicial',
        explanation: `Los adverbios temporales («${raw}») se anteponen al inicio de la oración en LSEC para fijar el tiempo de toda la proposición, ya que los verbos se señan en infinitivo.`
      };
    }

    if (NEGATION_MARKERS_SET.has(raw)) {
      return {
        label: raw,
        badge: 'NEG',
        raw,
        category: 'Negación Post-Verbal LSEC',
        explanation: `En la gramática LSEC el operador negativo («${raw}») se ubica al cierre de la cláusula (después del verbo) acompañado de movimiento negativo de cabeza.`
      };
    }

    const isFs = Boolean(
      glossObj?.is_fingerspelling ||
      glossObj?.gloss_type === 'DACTILOLOGÍA' ||
      raw.startsWith('FS:') ||
      (raw.includes('-') && raw.split('-').every(p => p.length === 1))
    );
    if (isFs) {
      return {
        label: raw,
        badge: 'A-B-C',
        raw,
        category: 'Dactilología (Deletreo Manual)',
        explanation: `Término o nombre propio deletreado grafema por grafema con el alfabeto dactilológico ecuatoriano (${raw}).`
      };
    }

    const srcWord = glossObj?.source_word ? ` (desde «${glossObj.source_word}»)` : '';
    const dictTitle = glossObj?.dictionary_metadata?.title ? ` — Ficha CONADIS: «${glossObj.dictionary_metadata.title}»` : '';
    return {
      label: raw.replace(/\[[^\]]*\]/g, '').trim(),
      badge: null,
      raw,
      category: 'Seña Léxica Oficial CONADIS',
      explanation: `Concepto léxico nuclear en forma base/lematizada${srcWord}${dictTitle}, ubicado según el orden sintáctico Sujeto–Objeto–Verbo (SOV).`
    };
  }

  getGlossObjectsForSegment(seg) {
    if (!seg || typeof appState === 'undefined' || !appState.state?.project) return [];
    const project = appState.state.project;
    const allGlosses = project.glosses || [];

    // 1. Coincidencia directa por segment_id o proposition_id del segmento
    const bySegOrProp = allGlosses.filter(g => {
      if (g.segment_id && g.segment_id === seg.id) return true;
      const gProp = g.prop_id || g.proposition_id || g.origin_proposition_id;
      if (gProp && (gProp === seg.id || (seg.proposition_id && gProp === seg.proposition_id))) return true;
      return false;
    });
    if (bySegOrProp.length > 0) return this.deduplicateConsecutiveGlosses(bySegOrProp);

    // 2. Si el propio segmento tiene un arreglo de objetos glosses
    if (Array.isArray(seg.glosses) && seg.glosses.length > 0 && typeof seg.glosses[0] === 'object') {
      return this.deduplicateConsecutiveGlosses(seg.glosses);
    }

    // 3. Coincidencia por ventana temporal cuando las glosas no tienen propietario explícito
    const segStart = Number(seg.start_time ?? seg.start_seconds ?? 0);
    const segEnd = Number(seg.end_time ?? seg.end_seconds ?? 0);
    const byTimeWindow = allGlosses.filter(g => {
      const hasOtherOwner = (g.segment_id && g.segment_id !== seg.id) ||
        ((g.prop_id || g.proposition_id) && (g.prop_id || g.proposition_id) !== seg.proposition_id && (g.prop_id || g.proposition_id) !== seg.id);
      if (hasOtherOwner) return false;
      const gs = Number(g.start_seconds ?? g.start_time ?? -1);
      const ge = Number(g.end_seconds ?? g.end_time ?? -1);
      return gs >= (segStart - 0.1) && ge <= (segEnd + 0.1);
    });
    if (byTimeWindow.length > 0) return this.deduplicateConsecutiveGlosses(byTimeWindow);

    // 4. Fallback a la secuencia de strings gloss_sequence del segmento
    const seq = Array.isArray(seg.gloss_sequence) ? seg.gloss_sequence : [];
    return this.deduplicateConsecutiveGlosses(seq.map((token, idx) => ({
      id: `${seg.id}_g_${idx}`,
      segment_id: seg.id,
      gloss: String(token).toUpperCase(),
      lemma: String(token).toUpperCase(),
      status: seg.manually_edited ? 'EDITED' : 'READY',
      manually_edited: Boolean(seg.manually_edited),
      is_fingerspelling: String(token).includes('-') || String(token).startsWith('FS:')
    })));
  }

  classifyChipStatus(glossObj) {
    const rawToken = String(glossObj?.gloss || glossObj?.lemma || '').toUpperCase();
    const isEdited = Boolean(
      glossObj?.manually_edited ||
      glossObj?.status === 'EDITED' ||
      glossObj?.alignment_type === 'MANUAL_EDIT'
    );
    const isFingerspell = Boolean(
      glossObj?.is_fingerspelling ||
      glossObj?.source === 'FINGERSPELLING' ||
      glossObj?.gloss_type === 'DACTILOLOGÍA' ||
      rawToken.startsWith('FS:') ||
      (rawToken.includes('-') && rawToken.split('-').every(part => part.length === 1))
    );

    if (isEdited) return { cssClass: 'gloss-chip-edited', symbol: '✎', badgeText: 'Editada manualmente', statusKey: 'EDITED' };
    if (isFingerspell) return { cssClass: 'gloss-chip-fingerspell', symbol: '✦', badgeText: 'Dactilología', statusKey: 'FINGERSPELLING' };
    return { cssClass: 'gloss-chip-conadis', symbol: '✓', badgeText: 'Seña CONADIS', statusKey: 'CONADIS' };
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
    let total = 0, conadisCount = 0, editedCount = 0;
    segments.forEach((seg) => {
      const glosses = this.getGlossObjectsForSegment(seg);
      glosses.forEach((g) => {
        total++;
        const info = this.classifyChipStatus(g);
        if (info.statusKey === 'CONADIS') conadisCount++;
        if (info.statusKey === 'EDITED') editedCount++;
      });
    });
    if (this.coverageBadgeEl) {
      this.coverageBadgeEl.textContent = total > 0
        ? `${conadisCount}/${total} Señas CONADIS · ${editedCount} Editadas`
        : '4.142 Fichas CONADIS';
    }
    const footerSummaryEl = document.getElementById('step2-footer-summary');
    if (footerSummaryEl) {
      footerSummaryEl.textContent = segments.length > 0
        ? `${segments.length} ${segments.length === 1 ? 'oración' : 'oraciones'} · ${total} señas LSEC listas${editedCount > 0 ? ` (${editedCount} editadas)` : ''}`
        : '';
    }
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
    return `${fmt(start)} – ${fmt(end)}`;
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
      const rowNumFormatted = String(rowIndex + 1).padStart(2, '0');
      const estRows = Math.max(1, Math.min(4, Math.ceil(spanishText.length / 56)));

      // Activar fila al hacer clic en cualquier zona
      row.addEventListener('click', () => {
        if (this.selectedSegmentIndex !== rowIndex) {
          this.selectedSegmentIndex = rowIndex;
          this.renderGrammarMonitor(seg, rowIndex);
          this.highlightSelectedRow();
        }
      });

      // 1. Columna Izquierda: Español (Editorial, limpio y sin recortes verticales)
      const leftCell = document.createElement('div');
      leftCell.className = 'comparative-cell-spanish';
      leftCell.innerHTML = `
        <div class="comparative-cell-meta-bar">
          <button type="button" class="comparative-row-meta" data-action="select-and-seek" title="Escuchar este fragmento del video">
            <span class="comparative-row-num">${rowNumFormatted}</span>
            <span class="comparative-row-time">${timeRange}</span>
          </button>
          <div style="display:inline-flex; align-items:center; gap:6px; flex-wrap:wrap;">
            <button type="button" class="btn btn-sm comparative-explain-btn" data-action="explain-row" title="Ver explicación paso a paso de las reglas lingüísticas aplicadas en esta oración" style="font-size:0.74rem; padding:3px 9px; border-color:#0284c7; color:#0369a1; background:#f0f9ff; font-weight:700;">
              ¿Cómo se tradujo?
            </button>
            <button type="button" class="btn btn-sm comparative-retranslate-btn" data-action="retranslate-row" title="Re-traducir esta oración con el motor LSEC">
              Re-traducir
            </button>
          </div>
        </div>
        <textarea id="comparative-seg-input-${rowIndex + 1}" name="comparative_segment_${rowIndex + 1}" class="transcript-seg-input comparative-spanish-input" rows="${estRows}" aria-label="Oración en español fila ${rowIndex + 1}">${this.escapeHtml(spanishText)}</textarea>
      `;

      const selectSeekBtn = leftCell.querySelector('[data-action="select-and-seek"]');
      if (selectSeekBtn) {
        selectSeekBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.selectedSegmentIndex = rowIndex;
          this.renderGrammarMonitor(seg, rowIndex);
          this.highlightSelectedRow();
          if (typeof appState !== 'undefined') {
            appState.setCurrentTime(Number(seg.start_time ?? seg.start_seconds) || 0, true);
          }
        });
      }

      const textarea = leftCell.querySelector('.transcript-seg-input');
      const retranslateBtn = leftCell.querySelector('[data-action="retranslate-row"]');
      const explainBtn = leftCell.querySelector('[data-action="explain-row"]');

      if (explainBtn) {
        explainBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.selectedSegmentIndex = rowIndex;
          this.renderGrammarMonitor(seg, rowIndex);
          this.highlightSelectedRow();
          this.openSentenceExplanationModal(seg, rowIndex);
        });
      }

      if (textarea) {
        textarea.addEventListener('focus', () => {
          this.selectedSegmentIndex = rowIndex;
          this.renderGrammarMonitor(seg, rowIndex);
          this.highlightSelectedRow();
        });
        textarea.addEventListener('input', () => {
          textarea.rows = Math.max(1, Math.min(5, Math.ceil(textarea.value.length / 56)));
          if (retranslateBtn) retranslateBtn.classList.add('is-dirty');
        });
        textarea.addEventListener('change', (e) => {
          const newText = e.target.value.trim();
          appState.updateSegment(seg.id, { normalized_text: newText, raw_text: newText, status: 'CORRECTED' });
        });
      }

      if (retranslateBtn) {
        retranslateBtn.addEventListener('mousedown', (e) => e.preventDefault());
        retranslateBtn.addEventListener('click', async (e) => {
          e.stopPropagation();
          const currentText = textarea ? textarea.value.trim() : spanishText;
          retranslateBtn.disabled = true;
          retranslateBtn.textContent = 'Traduciendo...';
          try {
            await this.retranslateSingleRow(seg, currentText, rowIndex);
            retranslateBtn.classList.remove('is-dirty');
          } finally {
            retranslateBtn.disabled = false;
            retranslateBtn.textContent = 'Re-traducir';
          }
        });
      }

      // 2. Columna Derecha: Secuencia de Señas LSEC (Fluida con conectores → y revelación progresiva)
      const rightCell = document.createElement('div');
      rightCell.className = 'comparative-cell-glosses';

      const topLine = document.createElement('div');
      topLine.className = 'comparative-glosses-topline';

      const rack = document.createElement('div');
      rack.className = 'gloss-chips-rack';

      glossObjects.forEach((glossObj, gIdx) => {
        if (gIdx > 0) {
          const arrow = document.createElement('span');
          arrow.className = 'gloss-seq-arrow';
          arrow.setAttribute('aria-hidden', 'true');
          arrow.textContent = '→';
          rack.appendChild(arrow);
        }
        const chipEl = this.createTactileGlossChip(seg, glossObj, gIdx, glossObjects.length, rowIndex);
        rack.appendChild(chipEl);
      });

      // Botón discreto "+ Agregar seña" (visible solo en fila activa o hover)
      const addBtn = document.createElement('button');
      addBtn.type = 'button';
      addBtn.className = 'gloss-add-chip-btn';
      addBtn.textContent = '+ Agregar seña';
      addBtn.title = 'Agregar nueva glosa LSEC al final de esta oración';
      addBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.selectedSegmentIndex = rowIndex;
        this.highlightSelectedRow();
        this.openInlineNewGlossInput(rack, addBtn, seg, rowIndex);
      });
      rack.appendChild(addBtn);

      const countMeta = document.createElement('span');
      countMeta.className = 'comparative-sign-count';
      countMeta.textContent = `${glossObjects.length} ${glossObjects.length === 1 ? 'seña' : 'señas'}`;

      topLine.appendChild(rack);
      topLine.appendChild(countMeta);
      rightCell.appendChild(topLine);

      const rowHint = document.createElement('div');
      rowHint.className = 'comparative-row-hint';
      rowHint.textContent = 'Clic en cualquier seña para cambiarla · Pasa el cursor sobre una seña para moverla o quitarla';
      rightCell.appendChild(rowHint);

      row.appendChild(leftCell);
      row.appendChild(rightCell);
      this.rowsContainer.appendChild(row);
    });
  }

  createTactileGlossChip(seg, glossObj, gIdx, totalGlosses, rowIndex) {
    const info = this.classifyChipStatus(glossObj);
    const rawToken = String(glossObj.gloss || glossObj.lemma || '').toUpperCase();
    const notation = this.describeGlossNotation(rawToken, glossObj);
    const displayToken = notation.label || this.formatCleanGlossLabel(rawToken) || rawToken;
    const badgeHtml = notation.badge
      ? `<span class="gloss-chip-ling-badge" style="font-size:0.66rem; font-weight:800; padding:1px 5px; border-radius:4px; background:rgba(15,23,42,0.10); color:inherit; margin-left:3px; letter-spacing:0.02em;">${this.escapeHtml(notation.badge)}</span>`
      : '';

    const chip = document.createElement('div');
    chip.className = `gloss-chip-tactile ${info.cssClass}`;
    chip.dataset.glossId = glossObj.id || `${seg.id}_${gIdx}`;
    chip.dataset.glossIndex = String(gIdx);
    chip.title = `${displayToken}${notation.badge ? ` [${notation.badge}]` : ''} · ${notation.category}: ${notation.explanation} (Clic para editar)`;

    chip.innerHTML = `
      <span class="gloss-chip-symbol" aria-hidden="true">${info.symbol}</span>
      <span class="gloss-chip-text" data-action="edit-gloss">${this.escapeHtml(displayToken)}${badgeHtml}</span>
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
    input.id = `inline-gloss-edit-${rowIndex + 1}-${gIdx + 1}`;
    input.name = `inline_gloss_edit_${rowIndex + 1}_${gIdx + 1}`;
    input.setAttribute('aria-label', `Editar glosa ${currentVal} en oración ${rowIndex + 1}`);
    input.value = currentVal;
    input.className = 'transcript-seg-input';
    input.style.width = `${Math.max(96, currentVal.length * 12 + 28)}px`;
    input.style.minHeight = '30px';
    input.style.padding = '2px 8px';
    input.style.textTransform = 'uppercase';
    input.style.fontWeight = '800';

    let committed = false;
    const finish = (save) => {
      if (committed) return;
      committed = true;
      const nextToken = input.value.trim().toUpperCase();
      if (save && nextToken && nextToken !== currentVal) {
        this.updateGlossInRow(seg, glossObj, gIdx, nextToken, rowIndex);
      } else {
        this.renderAll();
      }
    };

    input.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        finish(true);
      } else if (ev.key === 'Escape') {
        ev.preventDefault();
        finish(false);
      }
    });
    input.addEventListener('blur', () => finish(true));

    chipEl.innerHTML = '';
    chipEl.appendChild(input);
    input.focus();
    input.select();
  }

  openInlineNewGlossInput(rackEl, addBtnEl, seg, rowIndex) {
    const input = document.createElement('input');
    input.type = 'text';
    input.id = `inline-gloss-new-${rowIndex + 1}`;
    input.name = `inline_gloss_new_${rowIndex + 1}`;
    input.setAttribute('aria-label', `Agregar nueva glosa a oración ${rowIndex + 1}`);
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

  syncSegmentGlossesToProject(seg, updatedGlossObjects, pushHistory = true) {
    if (pushHistory && typeof appState !== 'undefined' && typeof appState.pushHistory === 'function') {
      appState.pushHistory();
    }
    seg.gloss_sequence = updatedGlossObjects.map(g => String(g.gloss || g.lemma || '').toUpperCase());
    seg.status = 'CORRECTED';
    seg.manually_edited = true;

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
        proposition_id: seg.proposition_id || g.proposition_id || seg.id,
        start_time: gStart,
        end_time: gEnd,
        start_seconds: gStart,
        end_seconds: gEnd,
        duration: Number(dur.toFixed(3))
      };
    });

    seg.glosses = timedGlosses;

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
      status: 'EDITED',
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
      status: 'EDITED',
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
    const [rawMoved] = list.splice(fromIdx, 1);
    const moved = { ...rawMoved, status: 'EDITED', manually_edited: true, alignment_type: 'MANUAL_EDIT' };
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
      const glossList = Array.isArray(result) ? result : (result && Array.isArray(result.glosses) ? result.glosses : []);
      if (glossList.length > 0) {
        if (result && result.applied_rules) seg.applied_rules = result.applied_rules;
        this.syncSegmentGlossesToProject(seg, glossList, false);
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
    this.syncSegmentGlossesToProject(seg, fallbackObjects, false);
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

  openSentenceExplanationModal(seg, rowIndex = 0) {
    if (!seg) return;
    const backdrop = document.getElementById('generic-modal-backdrop');
    const titleEl = document.getElementById('generic-modal-title');
    const bodyEl = document.getElementById('generic-modal-body');
    const footerEl = document.getElementById('generic-modal-footer');
    const closeBtn = document.getElementById('generic-modal-close');
    if (!backdrop || !titleEl || !bodyEl || !footerEl) return;

    const spanishText = seg.normalized_text || seg.raw_text || seg.original_text || '';
    const rawWords = spanishText.split(/\s+/).filter(Boolean);
    const glossObjects = this.getGlossObjectsForSegment(seg);
    const glossTokens = glossObjects.map(g => String(g.gloss || g.lemma || '').toUpperCase());
    const glossSet = new Set(glossTokens.map(t => t.replace(/\[[^\]]*\]|\++$/g, '')));

    let elidedWords = [];
    let infinitivePairs = [];
    const wordSpansHtml = rawWords.map((rawWord) => {
      const cleanLower = rawWord.toLowerCase().replace(/[.,;!?¿¡"()]/g, '');
      if (ELIDED_SPANISH_WORDS.has(cleanLower)) {
        elidedWords.push(rawWord);
        return `<span class="grammar-token-elided" title="Palabra funcional omitida en LSEC">${this.escapeHtml(rawWord)}</span>`;
      }
      const matchedInf = this.isInfinitiveVerb(cleanLower, glossSet);
      if (matchedInf) {
        const infLabel = typeof matchedInf === 'string' ? matchedInf : rawWord.toUpperCase();
        infinitivePairs.push({ from: rawWord, to: infLabel });
        return `<span class="grammar-token-infinitive" title="Verbo lematizado a infinitivo">${this.escapeHtml(rawWord)} → ${this.escapeHtml(infLabel)}</span>`;
      }
      return `<span class="grammar-token-word">${this.escapeHtml(rawWord)}</span>`;
    }).join(' ');

    let hasTime = false;
    let hasNeg = false;
    let hasIncNeg = false;
    let hasDir = false;
    let hasPlus = false;
    let hasPro = false;

    const glossRowsHtml = glossObjects.map((g, idx) => {
      const rawTok = String(g.gloss || g.lemma || '').toUpperCase();
      const notInfo = this.describeGlossNotation(rawTok, g);
      const chipInfo = this.classifyChipStatus(g);
      if (notInfo.badge === 'TIEMPO') hasTime = true;
      if (notInfo.badge === 'NEG') hasNeg = true;
      if (notInfo.badge === 'NEG-INC') hasIncNeg = true;
      if (notInfo.badge && notInfo.badge.includes('→')) hasDir = true;
      if (notInfo.badge && notInfo.badge.includes('++')) hasPlus = true;
      if (notInfo.badge && (notInfo.badge.startsWith('PRO') || notInfo.badge.startsWith('POSS'))) hasPro = true;

      return `
        <div style="display:grid; grid-template-columns: 36px minmax(150px, 210px) 1fr; gap:12px; align-items:start; padding:10px 12px; border-radius:10px; background:var(--color-canvas-bg); border:1px solid var(--color-border-subtle);">
          <div style="font-weight:800; color:var(--color-accent-cobalt); font-family:var(--font-mono); padding-top:3px;">#${idx + 1}</div>
          <div>
            <span class="gloss-chip-tactile ${chipInfo.cssClass}" style="padding:4px 10px; font-size:0.82rem; display:inline-flex;">
              <span class="gloss-chip-symbol" aria-hidden="true">${chipInfo.symbol}</span>
              <span>${this.escapeHtml(notInfo.label)}</span>
              ${notInfo.badge ? `<span style="font-size:0.68rem; font-weight:800; padding:1px 5px; border-radius:4px; background:rgba(15,23,42,0.12); margin-left:4px;">${this.escapeHtml(notInfo.badge)}</span>` : ''}
            </span>
            <div style="font-size:0.71rem; font-weight:700; color:var(--color-text-secondary); margin-top:4px; font-family:var(--font-mono);">
              Glosa técnica: ${this.escapeHtml(notInfo.raw)}
            </div>
          </div>
          <div>
            <div style="font-size:0.8rem; font-weight:800; color:var(--color-text-primary); margin-bottom:2px;">
              ${this.escapeHtml(notInfo.category)}
            </div>
            <div style="font-size:0.79rem; color:var(--color-text-secondary); line-height:1.45;">
              ${this.escapeHtml(notInfo.explanation)}
            </div>
          </div>
        </div>
      `;
    }).join('');

    const rulesSummary = [
      {
        title: '1. Reordenamiento Sintáctico Español (SVO) → LSEC (TIEMPO + TÓPICO + SOV + NEGACIÓN)',
        desc: 'En español el verbo suele ir en medio (Sujeto–Verbo–Objeto). En LSEC primero se presentan los referentes/participantes en el espacio (Sujeto y Objeto) y al final se ejecuta la acción (Verbo).'
      }
    ];
    if (elidedWords.length > 0) {
      rulesSummary.push({
        title: `2. Elisión de Palabras Funcionales (${elidedWords.length} omitidas: ${elidedWords.join(', ')})`,
        desc: 'Artículos determinados/indeterminados, verbos copulativos («ser/estar» sin valor locativo) y preposiciones gramaticales vacías se eliden porque LSEC establece las relaciones mediante el orden espacial y rasgos no manuales.'
      });
    }
    if (infinitivePairs.length > 0) {
      rulesSummary.push({
        title: '3. Reducción Morfológica Verbal a Infinitivo (Lematización)',
        desc: `Los verbos conjugados (${infinitivePairs.map(p => `«${p.from}» → ${p.to}`).join(', ')}) pasan a su forma infinitiva canónica; el tiempo verbal recae sobre el marcador temporal al inicio de la oración.`
      });
    }
    if (hasTime) {
      rulesSummary.push({
        title: '4. Frontalización del Marco Temporal (TIEMPO al inicio)',
        desc: 'Los adverbios de tiempo (hoy, ayer, mañana, ahora, antes) se colocan al inicio absoluto de la oración para fijar la línea temporal antes de presentar a los participantes.'
      });
    }
    if (hasPro) {
      rulesSummary.push({
        title: '5. Indexación Pronominal Deíctica (PRO1 = YO, PRO2 = TÚ, PRO3 = ÉL/ELLA)',
        desc: 'Los pronombres personales y posesivos se codifican como indexación espacial: 1.ª persona apunta al pecho del signante (PRO1), 2.ª persona al interlocutor (PRO2) y 3.ª persona a un locus lateral (PRO3).'
      });
    }
    if (hasDir) {
      rulesSummary.push({
        title: '6. Verbos Direccionales de Concordancia ([1→2], [2→1], [2→3])',
        desc: 'Los verbos direccionales (como AYUDAR, EXPLICAR, AVISAR, DAR, DECIR) mueven las manos desde el locus del sujeto hacia el locus del objeto/destinatario, absorbiendo los pronombres clíticos («me», «te», «le»).'
      });
    }
    if (hasPlus) {
      rulesSummary.push({
        title: '7. Reduplicación Segmental de Intensidad (++)',
        desc: 'Los intensificadores («muy», «mucho», «demasiado») y superlativos («-ísimo») se transforman en la marca «++», que indica repetir o enfatizar el movimiento de la seña base.'
      });
    }
    if (hasNeg || hasIncNeg) {
      rulesSummary.push({
        title: '8. Negación Post-Verbal y Negación Léxica Incorporada (FENASEC)',
        desc: 'En LSEC el adverbio NO se sitúa después del verbo, salvo en verbos con negación léxica fusionada propia del diccionario (NO-SABER, NO-PODER, NO-QUERER, NO-GUSTAR, NO-HABER).'
      });
    }

    titleEl.textContent = `¿Cómo se tradujo la Oración #${rowIndex + 1} a LSEC?`;
    bodyEl.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:14px; max-height:68vh; overflow-y:auto; padding-right:4px;">
        <div style="padding:12px 14px; border-radius:12px; background:#f8fafc; border:2px solid var(--color-border-subtle);">
          <div style="font-size:0.74rem; font-weight:800; text-transform:uppercase; color:var(--color-text-secondary); margin-bottom:6px;">
            Paso 1 · Análisis de la Oración en Español (Palabras tachadas = Elisión · Azul = Infinitivo)
          </div>
          <div class="grammar-tokens-flow" style="margin-bottom:6px;">${wordSpansHtml}</div>
        </div>

        <div style="display:flex; flex-direction:column; gap:8px;">
          <div style="font-size:0.76rem; font-weight:800; text-transform:uppercase; color:#065f46;">
            Paso 2 · Secuencia de Glosas LSEC y Significado de cada Notación (${glossObjects.length} señas)
          </div>
          ${glossRowsHtml}
        </div>

        <div style="padding:12px 14px; border-radius:12px; background:#f0fdf4; border:1.5px solid #86efac;">
          <div style="font-size:0.76rem; font-weight:800; text-transform:uppercase; color:#065f46; margin-bottom:8px;">
            Paso 3 · Reglas Gramaticales LSEC / FENASEC Aplicadas
          </div>
          <div style="display:flex; flex-direction:column; gap:8px;">
            ${rulesSummary.map(r => `
              <div>
                <div style="font-size:0.8rem; font-weight:800; color:#064e3b;">${this.escapeHtml(r.title)}</div>
                <div style="font-size:0.78rem; color:#1e293b; line-height:1.4;">${this.escapeHtml(r.desc)}</div>
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    `;

    const closeModal = () => {
      backdrop.classList.remove('open');
      backdrop.setAttribute('aria-hidden', 'true');
    };

    footerEl.innerHTML = `
      <button type="button" class="btn btn-primary" id="btn-close-explain-modal">Entendido</button>
    `;
    const btnOk = document.getElementById('btn-close-explain-modal');
    if (btnOk) btnOk.onclick = closeModal;
    if (closeBtn) closeBtn.onclick = closeModal;

    backdrop.classList.add('open');
    backdrop.setAttribute('aria-hidden', 'false');
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
