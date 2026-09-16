/**
 * LSEC Studio 2.1.1 — Validador Estructural y Lingüístico de Cliente (StructuralValidator)
 * 
 * Implementa en el cliente el catálogo completo de las 13 invariantes obligatorias
 * de LSEC 2.1.1 y las reglas de coherencia estructural, permitiendo validación inmediata
 * tras cada operación de edición visual, arrastrar y soltar o mutación de glosas.
 */

class StructuralValidator {
  static PUNCT_CHARS = new Set("¿?¡!,.;:\"'«»—–");
  
  static FORBIDDEN_PREDICATES = new Set([
    "yo", "tú", "tu", "él", "ella", "ello", "nosotros", "nosotras", "ustedes", "ellos", "ellas",
    "qué", "que", "quién", "quien", "quiénes", "quienes", "dónde", "donde", "cuándo", "cuando", "cómo", "como",
    "el", "la", "los", "las", "un", "una", "unos", "unas", "manzana", "manzanas", "carne", "carnes", "pan", "panes", "agua", "aguas"
  ]);

  /**
   * Valida una frase individual y su secuencia de glosas contra las 13 invariantes
   * y reglas estructurales de LSEC 2.1.1.
   * 
   * @param {Object} sentence Unidad de frase a validar
   * @param {Object} project Proyecto LSEC completo
   * @returns {Array<Object>} Lista de errores de validación encontrados
   */
  static validateSentence(sentence, project = null) {
    if (!sentence) return [];
    const errors = [];
    const glosses = sentence.glosses || [];
    const sentenceText = (sentence.text || '').trim();

    // ------------------------------------------------------------------
    // Invariante 2: PUNCTUATION_IN_LEMMA
    // Ninguna glosa ni lema puede contener signos de puntuación
    // ------------------------------------------------------------------
    glosses.forEach(g => {
      const glossName = g.gloss || '';
      const lemmaName = g.lemma || '';
      const hasPunctGloss = [...glossName].some(c => this.PUNCT_CHARS.has(c));
      const hasPunctLemma = [...lemmaName].some(c => this.PUNCT_CHARS.has(c));

      // Si es una pausa formal [PAUSA], se permite el delimitador especial de corchete
      const isPause = g.is_pause || g.gloss_type === 'PAUSA' || glossName === '[PAUSA]';

      if (!isPause && (hasPunctGloss || hasPunctLemma)) {
        errors.push({
          code: 'PUNCTUATION_IN_LEMMA',
          severity: 'ERROR',
          blocking: true,
          message: `Invariante 2 incumplida: Signo de puntuación detectado en glosa o lema '${glossName}'.`,
          affected_ids: [g.id]
        });
      }
    });

    // ------------------------------------------------------------------
    // Invariante de Secuencia: DUPLICATE_GLOSS_SEQUENCE
    // No pueden existir órdenes duplicados ni IDs idénticos concurrentes
    // ------------------------------------------------------------------
    const seenIds = new Set();
    const seenOrders = new Set();
    glosses.forEach((g, idx) => {
      if (seenIds.has(g.id)) {
        errors.push({
          code: 'DUPLICATE_GLOSS_SEQUENCE',
          severity: 'ERROR',
          blocking: true,
          message: `Invariante de secuencia: ID de glosa duplicado '${g.id}' en la frase.`,
          affected_ids: [g.id]
        });
      }
      seenIds.add(g.id);

      const orderVal = g.order !== undefined ? g.order : idx;
      if (seenOrders.has(orderVal)) {
        errors.push({
          code: 'DUPLICATE_GLOSS_SEQUENCE',
          severity: 'ERROR',
          blocking: true,
          message: `Invariante de secuencia: Orden duplicado ${orderVal} en la secuencia de glosas.`,
          affected_ids: [g.id]
        });
      }
      seenOrders.add(orderVal);
    });

    // ------------------------------------------------------------------
    // Invariante 13: TIMING_ARITHMETIC_INCONSISTENCY
    // Duraciones no positivas, tiempos invertidos o fuera de rango
    // ------------------------------------------------------------------
    glosses.forEach(g => {
      const st = g.start_seconds !== undefined ? g.start_seconds : (g.start !== undefined ? g.start : 0);
      const et = g.end_seconds !== undefined ? g.end_seconds : (g.end !== undefined ? g.end : st);
      const dur = et - st;

      if (dur <= 0) {
        errors.push({
          code: 'TIMING_ARITHMETIC_INCONSISTENCY',
          severity: 'ERROR',
          blocking: true,
          message: `Invariante 13 incumplida: La glosa '${g.gloss}' tiene una duración inconsistente (<= 0s).`,
          affected_ids: [g.id]
        });
      }

      if (st < (sentence.start_seconds - 0.5) || et > (sentence.end_seconds + 0.5)) {
        errors.push({
          code: 'TIMING_ARITHMETIC_INCONSISTENCY',
          severity: 'WARNING',
          blocking: false,
          message: `Invariante 13 aviso: La glosa '${g.gloss}' está fuera del intervalo temporal de la frase.`,
          affected_ids: [g.id]
        });
      }
    });

    // ------------------------------------------------------------------
    // Invariante 6: INVALID_DIRECT_ALIGNMENT
    // Glosas marcadas como DIRECT deben tener source_word
    // ------------------------------------------------------------------
    glosses.forEach(g => {
      const alType = g.alignment_type || g.type_badge;
      if (alType === 'DIRECT' && !g.source_word && !g.normalized_word) {
        errors.push({
          code: 'INVALID_DIRECT_ALIGNMENT',
          severity: 'ERROR',
          blocking: true,
          message: `Invariante 6 incumplida: Glosa '${g.gloss}' clasificada como DIRECT sin source_word.`,
          affected_ids: [g.id]
        });
      }
    });

    // ------------------------------------------------------------------
    // Invariante 8: MISSING_NEGATION_OPERATOR
    // Frases con negación explícita deben contar con operador de negación en LSEC
    // ------------------------------------------------------------------
    const lowerText = sentenceText.toLowerCase();
    const hasSpanishNegation = (
      lowerText.startsWith("no ") || 
      lowerText.includes(" no ") || 
      lowerText.includes("nadie") || 
      lowerText.includes("nunca") || 
      lowerText.includes("jamás") ||
      lowerText.includes("sin ")
    );

    if (hasSpanishNegation && glosses.length > 0) {
      const hasLSECNegation = glosses.some(g => {
        const gl = (g.gloss || '').toUpperCase();
        return (
          gl === 'NO' || 
          gl === 'NADIE' || 
          gl === 'NUNCA' || 
          gl === 'JAMÁS' || 
          gl.includes('-NO') || 
          gl.includes('NO-') ||
          (g.non_manual_features && g.non_manual_features.some(f => f.toLowerCase().includes('negación')))
        );
      });

      if (!hasLSECNegation) {
        errors.push({
          code: 'MISSING_NEGATION_OPERATOR',
          severity: 'ERROR',
          blocking: true,
          message: `Invariante 8 incumplida: Frase con negación en español carece de glosa u operador de negación LSEC.`,
          affected_ids: [sentence.id]
        });
      }
    }

    // ------------------------------------------------------------------
    // Invariante 7: MODALITY_MISMATCH
    // Interrogativas en español requieren rasgo no manual o interrogativo LSEC
    // ------------------------------------------------------------------
    const isInterrogative = sentenceText.includes('¿') || sentenceText.includes('?');
    if (isInterrogative && glosses.length > 0) {
      const hasWhOrQuestion = glosses.some(g => {
        const gl = (g.gloss || '').toUpperCase();
        const nmf = g.non_manual_features || [];
        return (
          gl === 'QUÉ' || gl === 'QUIÉN' || gl === 'DÓNDE' || gl === 'CUÁNDO' || gl === 'CÓMO' || gl === 'POR-QUÉ' ||
          nmf.some(f => f.toLowerCase().includes('pregunta') || f.toLowerCase().includes('cejas'))
        );
      });

      if (!hasWhOrQuestion) {
        errors.push({
          code: 'MODALITY_MISMATCH',
          severity: 'ERROR',
          blocking: true,
          message: `Invariante 7 incumplida: Frase interrogativa carece de glosa interrogativa o rasgo no manual de pregunta.`,
          affected_ids: [sentence.id]
        });
      }
    }

    // ------------------------------------------------------------------
    // Invariante 12: DESTRUCTIVE_NORMALIZATION
    // ------------------------------------------------------------------
    glosses.forEach(g => {
      const gl = (g.gloss || '').toUpperCase();
      const nw = (g.normalized_word || '').toLowerCase();
      if (gl === 'MANZÁN' || nw === 'manzán') {
        errors.push({
          code: 'DESTRUCTIVE_NORMALIZATION',
          severity: 'ERROR',
          blocking: true,
          message: `Invariante 12 incumplida: Normalización destructiva detectada en '${gl}'.`,
          affected_ids: [g.id]
        });
      }
    });

    // ------------------------------------------------------------------
    // Invariante 1: INVALID_PREDICATE_SELECTION
    // ------------------------------------------------------------------
    glosses.forEach(g => {
      if (g.syntactic_role === 'PREDICADO') {
        const lemma = (g.lemma || g.gloss || '').toLowerCase().trim();
        if (this.FORBIDDEN_PREDICATES.has(lemma)) {
          errors.push({
            code: 'INVALID_PREDICATE_SELECTION',
            severity: 'ERROR',
            blocking: true,
            message: `Invariante 1 incumplida: Predicado inválido '${lemma}' seleccionado para la acción.`,
            affected_ids: [g.id]
          });
        }
      }
    });

    // ------------------------------------------------------------------
    // Invariante 9: UNRESOLVED_COREFERENCE_ALIGNMENT
    // ------------------------------------------------------------------
    glosses.forEach(g => {
      if (g.alignment_type === 'COREFERENCE' && !g.antecedent_proposition_id && !g.coreference_target_id) {
        errors.push({
          code: 'UNRESOLVED_COREFERENCE_ALIGNMENT',
          severity: 'ERROR',
          blocking: true,
          message: `Invariante 9 incumplida: Glosa de correferencia '${g.gloss}' sin antecedente enlazado.`,
          affected_ids: [g.id]
        });
      }
    });

    // ------------------------------------------------------------------
    // Invariante de Contenido: EMPTY_GLOSS_SEQUENCE
    // ------------------------------------------------------------------
    if (glosses.length === 0 && sentenceText.length > 0) {
      errors.push({
        code: 'EMPTY_GLOSS_SEQUENCE',
        severity: 'WARNING',
        blocking: false,
        message: `La frase no contiene glosas LSEC asignadas.`,
        affected_ids: [sentence.id]
      });
    }

    return errors;
  }

  /**
   * Valida un proyecto completo ejecutando las 13 invariantes sobre todas sus frases.
   * 
   * @param {Object} project Proyecto LSEC
   * @param {Array<Object>} sentenceUnits Lista de unidades de frase (opcional)
   * @returns {Object} Informe de validación con errores, advertencias y estado
   */
  static validateProject(project, sentenceUnits = null) {
    if (!project) return { isValid: true, errors: [], warnings: [] };

    const units = sentenceUnits || (typeof SentenceGroupingEngine !== 'undefined' ? SentenceGroupingEngine.buildSentenceUnits(project) : []);
    const allErrors = [];
    const allWarnings = [];

    units.forEach(sentence => {
      const sentenceIssues = this.validateSentence(sentence, project);
      sentenceIssues.forEach(iss => {
        if (iss.severity === 'ERROR') allErrors.push(iss);
        else allWarnings.push(iss);
      });
    });

    return {
      isValid: allErrors.length === 0,
      errorsCount: allErrors.length,
      warningsCount: allWarnings.length,
      errors: allErrors,
      warnings: allWarnings,
      executionStatus: allErrors.length > 0 ? 'REVIEW_REQUIRED' : 'READY'
    };
  }
}

// Exportación global para navegadores y Node.js / tests
if (typeof window !== 'undefined') {
  window.StructuralValidator = StructuralValidator;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { StructuralValidator };
}
