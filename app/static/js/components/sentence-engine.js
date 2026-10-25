/**
 * LSEC Studio 2.1.1 — Motor de Agrupación Visual de Frases (SentenceGroupingEngine)
 * 
 * Agrupa el contenido en unidades de frase completas hasta su puntuación final (. ? !),
 * asociando a cada frase su secuencia completa de glosas LSEC directamente debajo.
 * 
 * Principio Fundamental:
 * Agrupación de presentación visual no destructiva. Preserva intactos:
 * - SemanticProposition (IDs p1, p2, etc.)
 * - DiscourseBlock (bloques RST)
 * - WordTimestamp (marcas acústicas por palabra)
 * - TranslationPlan
 * - GlossItem (IDs g_01, g_02, lemas, tipos, notas)
 * - SourceAlignment
 * - IDs existentes de segmentos y glosas
 */

class SentenceGroupingEngine {
  /**
   * Expresión regular para abreviaturas comunes en español que llevan punto
   * pero no indican fin de oración.
   */
  static ABBREVIATIONS_PATTERN = /\b(?:dr|dra|sr|sra|srta|lic|prof|ing|arq|etc|gob|núm|num|pág|pag|av|avda|ej|art|cap|vs|u\.s\.a|u\.p\.e\.c|e\.e\.u\.u)\.?$/i;

  /**
   * Determina si una palabra o token termina con puntuación de fin de frase (. ? !),
   * excluyendo abreviaturas y números decimales.
   */
  static isSentencePunctuation(word) {
    if (!word || typeof word !== 'string') return false;
    const clean = word.trim();
    if (clean.length === 0) return false;

    // Números con punto (e.g. 4.500) no son fin de frase
    if (/^\d+\.\d+$/.test(clean)) return false;

    // Abreviaturas no son fin de frase
    if (this.ABBREVIATIONS_PATTERN.test(clean)) return false;

    // Signos terminales
    return /[.!?]+$/.test(clean);
  }

  /**
   * Extrae la puntuación final de un texto si existe.
   */
  static extractTrailingPunctuation(text) {
    if (!text || typeof text !== 'string') return '';
    const match = text.trim().match(/[.!?]+$/);
    return match ? match[0] : '';
  }

  /**
   * Construye las unidades de frase completas a partir de los datos del proyecto.
   * 
   * @param {Object} project Proyecto LSEC normalizado
   * @returns {Array<SentenceUnit>} Lista de frases agrupadas
   */
  static buildSentenceUnits(project) {
    if (!project) return [];
    const segments = project.segments || [];
    if (segments.length === 0) return [];

    const allGlosses = project.glosses || [];
    const transcription = project.transcription || {};
    const wordTimestamps = transcription.word_timestamps || [];
    const transcriptionText = (transcription.text || '').trim();

    // Si existe texto de transcripción estructurado con puntuación, preparamos oraciones de referencia
    const referenceSentences = this.splitTranscriptionIntoSentences(transcriptionText);

    const sentenceUnits = [];
    let currentSegments = [];
    let sentenceIndex = 1;

    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];
      currentSegments.push(seg);

      const isLast = (i === segments.length - 1);
      const endsSentence = isLast || this.checkSegmentEndsSentence(seg, segments[i + 1], wordTimestamps, referenceSentences, sentenceIndex);

      if (endsSentence && currentSegments.length > 0) {
        const sentenceUnit = this.createSentenceUnit(
          sentenceIndex,
          currentSegments,
          allGlosses,
          wordTimestamps,
          referenceSentences[sentenceIndex - 1] || null
        );
        sentenceUnits.push(sentenceUnit);
        currentSegments = [];
        sentenceIndex++;
      }
    }

    // Manejo de caso borde: si quedaron segmentos sueltos sin cerrar
    if (currentSegments.length > 0) {
      const sentenceUnit = this.createSentenceUnit(
        sentenceIndex,
        currentSegments,
        allGlosses,
        wordTimestamps,
        referenceSentences[sentenceIndex - 1] || null
      );
      sentenceUnits.push(sentenceUnit);
    }

    return sentenceUnits;
  }

  /**
   * Divide un texto en oraciones respetando abreviaturas y puntuación.
   */
  static splitTranscriptionIntoSentences(text) {
    if (!text) return [];
    // Dividir por puntuación mayor (. ? ! o salto de línea) seguida de espacio o inicio de frase
    const rawParts = text.split(/(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])/);
    const results = [];

    for (let j = 0; j < rawParts.length; j++) {
      const part = rawParts[j].trim();
      if (!part) continue;

      // Si la parte anterior terminaba en abreviatura, se fusiona
      if (results.length > 0 && this.ABBREVIATIONS_PATTERN.test(results[results.length - 1])) {
        results[results.length - 1] += ' ' + part;
      } else {
        results.push(part);
      }
    }
    return results;
  }

  /**
   * Evalúa si un segmento representa el corte final de una frase.
   */
  static checkSegmentEndsSentence(segment, nextSegment, wordTimestamps, referenceSentences, currentSentenceIndex) {
    // 1. Verificar si el texto del segmento termina explícitamente en puntuación
    const segText = (segment.normalized_text || segment.original_text || '').trim();
    if (this.isSentencePunctuation(segText)) {
      return true;
    }

    // 2. Verificar en las palabras del segmento (WordTimestamp)
    const segWords = segment.words && segment.words.length > 0 ? segment.words : [];
    if (segWords.length > 0) {
      const lastWord = segWords[segWords.length - 1];
      const wordStr = (lastWord.word || '').trim();
      if (this.isSentencePunctuation(wordStr)) {
        return true;
      }
    }

    // 3. Verificar en las marcas acústicas globales si coinciden con el final del segmento
    const segEnd = segment.end_seconds !== undefined ? segment.end_seconds : (segment.end_time || 0);
    const matchingWord = wordTimestamps.find(w => Math.abs(w.end - segEnd) <= 0.15);
    if (matchingWord && this.isSentencePunctuation(matchingWord.word)) {
      return true;
    }

    // 4. Contrastar con las oraciones de referencia de la transcripción
    if (referenceSentences && referenceSentences.length >= currentSentenceIndex) {
      const refSentence = referenceSentences[currentSentenceIndex - 1];
      if (refSentence) {
        const cleanRef = this.cleanForComparison(refSentence);
        const cleanSeg = this.cleanForComparison(segText);
        // Si el segmento contiene el final de la oración de referencia
        if (cleanRef.endsWith(cleanSeg) || cleanRef.includes(cleanSeg + '.')) {
          return true;
        }
      }
    }

    return false;
  }

  /**
   * Limpia cadenas para comparación fonética/textual simple.
   */
  static cleanForComparison(str) {
    return (str || '')
      .toLowerCase()
      .replace(/[.,\/#!$%\^&\*;:{}=\-_`~()¿¡?]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  /**
   * Crea una unidad de frase completa integrando sus segmentos, proposiciones y glosas.
   */
  static createSentenceUnit(index, segments, allGlosses, wordTimestamps, referenceSentenceText = null) {
    const firstSeg = segments[0];
    const lastSeg = segments[segments.length - 1];

    // Intervalo temporal que engloba a todos los segmentos (soporta solapamientos)
    let startSec = Infinity;
    let endSec = -Infinity;

    segments.forEach(s => {
      const sStart = s.start_seconds !== undefined ? s.start_seconds : (s.start_time !== undefined ? s.start_time : 0);
      const sEnd = s.end_seconds !== undefined ? s.end_seconds : (s.end_time !== undefined ? s.end_time : sStart + 2.0);
      if (sStart < startSec) startSec = sStart;
      if (sEnd > endSec) endSec = sEnd;
    });

    if (startSec === Infinity) startSec = 0;
    if (endSec === -Infinity) endSec = startSec + 2.0;

    startSec = parseFloat(startSec.toFixed(3));
    endSec = parseFloat(endSec.toFixed(3));
    const duration = parseFloat((endSec - startSec).toFixed(3));

    // Construir texto completo de la frase en español
    let sentenceText = '';
    if (referenceSentenceText) {
      sentenceText = referenceSentenceText.trim();
    } else {
      // Unir los textos de los segmentos respetando signos existentes
      const texts = segments.map(s => (s.normalized_text || s.original_text || '').trim()).filter(Boolean);
      sentenceText = texts.join(', ');
      
      // Comprobar si la última palabra del segmento tenía punto en sus palabras
      const lastWords = lastSeg.words || [];
      const lastWord = lastWords.length > 0 ? lastWords[lastWords.length - 1].word : '';
      const trailingPunct = this.extractTrailingPunctuation(lastWord);
      
      if (!this.extractTrailingPunctuation(sentenceText) && trailingPunct) {
        sentenceText += trailingPunct;
      }
    }

    // Recopilar IDs y estructuras internas sin destruirlas
    const segmentIds = segments.map(s => s.id);
    const propositionIds = [];
    const discourseBlockIds = [];
    const containedWords = [];
    const reviewReasons = [];

    let hasReviewRequired = false;

    segments.forEach(s => {
      // Proposiciones
      if (s.proposition_id && !propositionIds.includes(s.proposition_id)) {
        propositionIds.push(s.proposition_id);
      }
      if (Array.isArray(s.proposition_ids)) {
        s.proposition_ids.forEach(pid => {
          if (!propositionIds.includes(pid)) propositionIds.push(pid);
        });
      }

      // Bloques discursivos
      if (s.block_id !== undefined && !discourseBlockIds.includes(s.block_id)) {
        discourseBlockIds.push(s.block_id);
      }

      // Palabras
      if (s.words && Array.isArray(s.words)) {
        containedWords.push(...s.words);
      }

      // Estado de revisión
      if (s.status === 'REVIEW_REQUIRED' || s.status === 'NATIVE_REVIEW' || s.status === 'AUDIO_REVIEW' || s.status === 'BLOCKED') {
        hasReviewRequired = true;
        if (s.review_reason) reviewReasons.push(s.review_reason);
        else if (s.status_label) reviewReasons.push(`${s.id}: ${s.status_label}`);
      }
    });

    // Recopilar glosas LSEC vinculadas a esta frase
    const sentenceGlosses = this.collectSentenceGlosses(segments, propositionIds, allGlosses, startSec, endSec);

    // Secuencia canónica de nombres de glosa
    const glossSequence = sentenceGlosses.map(g => g.gloss || g.lemma || 'GLOSA');

    // Revisión en glosas
    sentenceGlosses.forEach(g => {
      if (g.status === 'AUDIO_REVIEW' || g.status === 'NATIVE_REVIEW' || g.status === 'BLOCKED' || g.status === 'REVIEW_REQUIRED') {
        hasReviewRequired = true;
        if (g.notes) reviewReasons.push(`Glosa ${g.gloss}: ${g.notes}`);
      }
    });

    return {
      id: `sentence_${String(index).padStart(2, '0')}`,
      index: index,
      text: sentenceText,
      start_seconds: startSec,
      end_seconds: endSec,
      start_time: startSec,
      end_time: endSec,
      duration: duration,
      // Asociaciones preservadas
      segments: segments,
      segment_ids: segmentIds,
      proposition_ids: propositionIds,
      discourse_block_ids: discourseBlockIds,
      words: containedWords,
      glosses: sentenceGlosses,
      gloss_sequence: glossSequence,
      status: hasReviewRequired ? 'REVIEW_REQUIRED' : 'VALIDATED',
      status_label: hasReviewRequired ? 'Requiere Revisión' : 'Validado',
      has_review: hasReviewRequired,
      review_reasons: reviewReasons,
      confidence: segments.reduce((acc, s) => acc + (s.confidence || 0.95), 0) / Math.max(1, segments.length)
    };
  }

  /**
   * Recopila y ordena las glosas correspondientes a una frase.
   */
  static collectSentenceGlosses(segments, propositionIds, allGlosses, startSec, endSec) {
    const collectedMap = new Map();

    // 1. Por coincidencia de proposición o segmento
    allGlosses.forEach(g => {
      const gProp = g.prop_id || g.proposition_id;
      const gStart = g.start_seconds !== undefined ? g.start_seconds : (g.start !== undefined ? g.start : null);
      const gEnd = g.end_seconds !== undefined ? g.end_seconds : (g.end !== undefined ? g.end : null);

      let matches = false;

      // Coincidencia exacta por proposition_id o segment_id
      if (gProp && propositionIds.some(pid => pid === gProp)) {
        matches = true;
      } else if (g.segment_id && segments.some(s => s.id === g.segment_id)) {
        matches = true;
      }
      // Coincidencia temporal estricta solo cuando la glosa no pertenece a otra proposición
      else if (!gProp && !g.segment_id && gStart !== null && gEnd !== null) {
        if (gStart >= startSec - 0.15 && gEnd <= endSec + 0.25) {
          matches = true;
        }
      }

      if (matches && !collectedMap.has(g.id)) {
        collectedMap.set(g.id, g);
      }
    });

    // 2. Si no se encontraron glosas globales, buscar en s.glosses o s.gloss_sequence
    if (collectedMap.size === 0) {
      segments.forEach(s => {
        if (s.glosses && Array.isArray(s.glosses)) {
          s.glosses.forEach(g => {
            if (!collectedMap.has(g.id)) collectedMap.set(g.id, g);
          });
        } else if (s.gloss_sequence && Array.isArray(s.gloss_sequence)) {
          s.gloss_sequence.forEach((glossName, gIdx) => {
            const virtualId = `g_${s.id}_${gIdx}`;
            if (!collectedMap.has(virtualId)) {
              collectedMap.set(virtualId, {
                id: virtualId,
                gloss: glossName,
                lemma: glossName,
                start_seconds: startSec + (gIdx * (endSec - startSec)) / Math.max(1, s.gloss_sequence.length),
                end_seconds: startSec + ((gIdx + 1) * (endSec - startSec)) / Math.max(1, s.gloss_sequence.length),
                prop_id: s.proposition_id || null,
                status: 'VALIDATED'
              });
            }
          });
        }
      });
    }

    // Ordenar cronológicamente o por propiedad 'order'
    return Array.from(collectedMap.values()).sort((a, b) => {
      if (a.order !== undefined && b.order !== undefined) return a.order - b.order;
      const aStart = a.start_seconds !== undefined ? a.start_seconds : (a.start || 0);
      const bStart = b.start_seconds !== undefined ? b.start_seconds : (b.start || 0);
      return aStart - bStart;
    });
  }
}

// Exportación global para entorno navegador y Node.js/pruebas
if (typeof window !== 'undefined') {
  window.SentenceGroupingEngine = SentenceGroupingEngine;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { SentenceGroupingEngine };
}
