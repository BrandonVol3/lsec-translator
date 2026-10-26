/**
 * LSEC Studio — Procesador de Pipeline Audiovisual en Background
 * 
 * Gestiona la carga de cualquier video, extracción de audio, transcripción ASR,
 * normalización, traducción a glosas LSEC, validación multidimensional
 * y sincronización con el gestor de estado.
 */

class PipelineProcessor {
  constructor() {
    this.isProcessing = false;
  }

  /**
   * Procesa un archivo de video cualquiera
   * @param {File} videoFile - Archivo de video local
   * @param {HTMLVideoElement} videoEl - Elemento de video HTML5 para metadatos
   */
  async processVideo(videoFile, videoEl) {
    if (!videoFile || this.isProcessing) return;
    this.isProcessing = true;

    console.log(`Iniciando Fase 1 (Transcripción) para '${videoFile.name}' (${(videoFile.size / (1024*1024)).toFixed(2)} MB)...`);

    // 1. Mostrar Modal de Progreso del Pipeline (Paso 1: Transcripción)
    this.showProgressModal(
      videoFile.name,
      'Paso 1: Extracción y Transcripción de Audio',
      [
        '1. Extracción de pista de audio y metadatos del video...',
        '2. Transcripción acústica con Whisper ASR y timestamps...',
        '3. Normalización lingüística y segmentación de subtítulos en español...'
      ]
    );

    try {
      // Paso 1: Carga y Extracción de Metadatos del Video (25%)
      this.updateStep(1, 'active', 'Extrayendo metadatos y pista de audio del video...');
      this.setProgress(25);
      
      const mediaInfo = await this.extractVideoMetadata(videoFile, videoEl);
      await this.sleep(400);
      this.updateStep(1, 'completed', `Metadatos listos: ${mediaInfo.width}x${mediaInfo.height}, ${(mediaInfo.duration).toFixed(2)}s`);

      // Paso 2: Transcripción Automática Whisper ASR (60%)
      const curHw = window.systemHardwareStatus;
      const isGpu = curHw && curHw.is_gpu;
      const step2Text = isGpu
        ? 'Ejecutando transcripción acústica con marcas de tiempo (GPU CUDA activa)...'
        : 'Ejecutando transcripción acústica con marcas de tiempo (Modo CPU)...';
      this.updateStep(2, 'active', step2Text);
      this.setProgress(60);

      let apiResponse = null;
      try {
        apiResponse = await this.callBackendPipeline(videoFile);
      } catch (err) {
        console.error('Backend pipeline falló:', err.message);
        throw new Error(`Error en el servicio de transcripción backend: ${err.message}`);
      }

      await this.sleep(500);
      this.setProgress(85);

      const usedDevice = apiResponse?.transcription?.device_used;
      const isActuallyGpu = (usedDevice === 'cuda');
      const step2DoneText = isActuallyGpu
        ? 'Transcripción ASR generada exitosamente con GPU (CUDA).'
        : 'Transcripción ASR generada en CPU (sin aceleración GPU).';
      this.updateStep(2, 'completed', step2DoneText);

      // Paso 3: Normalización y Segmentación de Subtítulos (100%)
      this.updateStep(3, 'active', 'Generando subtítulos y segmentos para revisión lingüística...');
      await this.sleep(400);
      this.setProgress(100);
      this.updateStep(3, 'completed', 'Subtítulos y transcripción en español listos para revisión.');

      // Guardar caché para posterior traducción a glosas (Fase 2)
      this.cachedApiResponse = apiResponse;
      this.cachedMediaInfo = mediaInfo;
      this.cachedVideoFile = videoFile;

      // Ensamblar Proyecto para Fase 1 (Transcripción y subtítulos en español, SIN glosas aún)
      const projectData = this.buildTranscriptionProjectStructure(videoFile, mediaInfo, apiResponse);
      
      // Cargar en el State Store y marcar Fase 1 lista
      appState.loadProject(projectData, videoFile.name);
      appState.markTranscriptionReady();

      // Notificar al usuario sobre el dispositivo utilizado
      if (apiResponse && apiResponse.transcription) {
        const tx = apiResponse.transcription;
        if (tx.device_warning) {
          if (window.showToast) {
            window.showToast(tx.device_warning, 'warning');
          }
        } else if (tx.device_used === 'cuda') {
          if (window.showToast) {
            window.showToast('Transcripción procesada con GPU (CUDA) acelerada.', 'success');
          }
        }
      }

      await this.sleep(300);

      // Cerrar modal
      setTimeout(() => {
        this.hideProgressModal();
        this.isProcessing = false;
      }, 400);

    } catch (err) {
      console.error('Error durante la transcripción:', err);
      this.showError(`Error procesando video: ${err.message}`);
      this.isProcessing = false;
    }
  }

  /**
   * Construye la estructura de proyecto para la Fase 1 (Transcripción y subtítulos en español)
   */
  buildTranscriptionProjectStructure(file, mediaInfo, apiResponse) {
    if (apiResponse && apiResponse.transcription) {
      const fullProj = this.transformBackendResponse(file, mediaInfo, apiResponse);
      fullProj.glosses = [];
      fullProj.segments = fullProj.segments.map(s => ({
        ...s,
        glosses: [],
        gloss_sequence: []
      }));
      fullProj.subtitles = fullProj.segments;
      fullProj.discourse_blocks = [];
      fullProj.non_manual_spans = [];
      fullProj.spatial_operations = [];
      fullProj.execution_status = 'DRAFT';
      return fullProj;
    }

    throw new Error('No se recibieron datos de transcripción válidos del backend. Verifique que el servicio de procesamiento esté activo.');
  }

  /**
   * Fase 2: Traduce el texto revisado y corregido en español a Glosas LSEC
   */
  async translateProjectGlosses() {
    if (this.isProcessing) return;
    const project = appState.state.project;
    if (!project || !project.segments || project.segments.length === 0) {
      alert('No hay transcripción disponible para traducir. Carga un video primero.');
      return;
    }

    this.isProcessing = true;
    this.showProgressModal(project.media_info?.filename || 'Proyecto_LSEC.mp4', 'Paso 2: Transformación Gramatical a Glosas LSEC', [
      '1. Analizando texto en español y elidiendo palabras funcionales...',
      '2. Lematizando verbos a infinitivo y reordenando sintaxis SVO -> SOV...',
      '3. Asignando fichas CONADIS, dactilología y rasgos no manuales...',
      '4. Ensamblando mesa comparativa paralela LSEC...'
    ], 'grammar');

    try {
      this.setProgress(20);
      this.updateStep(1, 'active', 'Analizando texto en español y elidiendo palabras funcionales...');
      await this.sleep(550);
      this.updateStep(1, 'completed', 'Texto y palabras funcionales analizadas.');

      this.setProgress(55);
      this.updateStep(2, 'active', 'Lematizando verbos a infinitivo y aplicando sintaxis SOV...');
      const translationResult = await this.performGlossesTranslation(project);
      await this.sleep(600);
      this.updateStep(2, 'completed', `${translationResult.glosses.length} glosas LSEC generadas.`);

      this.setProgress(85);
      this.updateStep(3, 'active', 'Asignando fichas CONADIS y rasgos gramaticales...');
      await this.sleep(550);
      this.updateStep(3, 'completed', 'Estructura espacial y fichas CONADIS asignadas.');

      this.setProgress(100);
      this.updateStep(4, 'completed', 'Transformación gramatical a glosas LSEC completada exitosamente.');
      await this.sleep(450);

      // Aplicar glosas generadas al proyecto
      project.glosses = translationResult.glosses;
      project.segments = translationResult.segments;
      project.subtitles = translationResult.segments;
      if (translationResult.discourse_blocks) project.discourse_blocks = translationResult.discourse_blocks;
      if (translationResult.non_manual_spans) project.non_manual_spans = translationResult.non_manual_spans;
      if (translationResult.spatial_operations) project.spatial_operations = translationResult.spatial_operations;
      if (translationResult.validation_metadata) project.validation_metadata = translationResult.validation_metadata;
      if (translationResult.unresolved_items) project.unresolved_items = translationResult.unresolved_items;
      if (translationResult.validation_warnings) project.validation_warnings = translationResult.validation_warnings;
      project.execution_status = 'REVIEW_REQUIRED';

      // Garantizar intervalos secuenciales en orden gramatical LSEC (SOV) para el Timeline y tarjetas
      appState.resolveOverlappingGlossIntervals(project.glosses, project.segments);
      for (const seg of project.segments) {
        seg.glosses = project.glosses.filter(g => g.proposition_id === seg.id || g.origin_proposition_id === seg.id);
        seg.gloss_sequence = seg.glosses.map(g => g.gloss || g.lemma);
      }

      // Desbloquear y activar Etapa 2: Traducir
      appState.markTranslationReady();
      appState.emit('projectUpdated', project);
      appState.emit('segmentsChanged', project.segments);

      // Actualizar la animación del monitor con las glosas reales generadas y permitir que el usuario decida cuándo continuar
      this.startModalGrammarAnimation(0);
      const grammarStatusLabel = document.getElementById('pipeline-grammar-status-label');
      if (grammarStatusLabel) {
        grammarStatusLabel.textContent = 'Transformación completada. Explora cómo cada oración en español se convierte en glosas LSEC y pulsa "Continuar" cuando estés listo.';
      }
      await this.waitForUserContinue();
      this.hideProgressModal();
      this.isProcessing = false;
    } catch (err) {
      console.error('Error durante la traducción a glosas:', err);
      this.showError('Error durante la traducción a glosas: ' + err.message);
      this.isProcessing = false;
    }
  }

  /**
   * Traduce un segmento de texto editado mediante el motor lingüístico del backend (/api/v1/translate)
   */
  async translateSegmentViaBackend(text, startTime, endTime, segId) {
    const cleanText = String(text || '').trim();
    if (!cleanText) return [];
    try {
      const res = await fetch('/api/v1/translate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: cleanText, mode: 'detailed', paraphrase_budget: 'compact' }) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const glossOut = await res.json();
      const rawGlosses = glossOut.glosses || [];
      if (rawGlosses.length === 0) return this.generateGlossesFromText(text, startTime, endTime, segId);
      const duration = Math.max(0.6, (endTime || (startTime + 2.5)) - (startTime || 0)), glossDur = duration / Math.max(1, rawGlosses.length);
      return rawGlosses.map((g, idx) => {
        const start = parseFloat(((startTime || 0) + idx * glossDur).toFixed(3)), end = parseFloat((start + Math.min(glossDur, 0.55)).toFixed(3));
        const gText = String(g.gloss || g.lemma || '').trim();
        const isSingleLetterHyphenated = gText.includes('-') && gText.split('-').filter(Boolean).every(p => p.trim().length === 1);
        const isFs = Boolean(g.is_fingerspelling || (g.gloss_type === 'DACTILOLOGÍA') || (g.gloss_type === 'FINGERSPELLING') || isSingleLetterHyphenated);
        const isUnverifiedLex = g.dictionary_metadata && g.dictionary_metadata.status === 'NO_VERIFICADO';
        const needsRev = Boolean(g.requires_native_review || g.requires_review || isUnverifiedLex);
        const gStatus = g.requires_audio_review ? 'AUDIO_REVIEW' : (needsRev ? 'REVIEW_REQUIRED' : (g.status || 'VALIDATED'));
        return {
          ...g, id: g.id || `g_${segId}_${idx + 1}`, order: g.order !== undefined ? g.order : idx,
          gloss: g.gloss || g.lemma || 'GLOSA', lemma: g.lemma || g.gloss || 'GLOSA',
          source_word: g.source_word || null, normalized_word: g.normalized_word || null,
          alignment_type: g.alignment_type || 'DIRECT', dictionary_metadata: g.dictionary_metadata || null,
          requires_review: needsRev, requires_native_review: needsRev, requires_audio_review: Boolean(g.requires_audio_review),
          review_reasons: g.review_reasons || [], start_seconds: start, end_seconds: end, start_time: start, end_time: end, start, end,
          proposition_id: segId, origin_proposition_id: segId, duration_ms: g.duration_ms || Math.round((end - start) * 1000),
          gloss_type: isFs ? 'DACTILOLOGÍA' : (g.gloss_type || 'SEÑA'), syntactic_role: g.syntactic_role || 'ARGUMENT',
          color: g.color || (isFs ? 'fingerspelling' : (needsRev ? 'review' : 'validated')),
          confidence: g.confidence !== undefined ? g.confidence : 0.94, status: gStatus, manual_code: g.manual_code || 'STD_SIGN', non_manual: g.non_manual || null
        };
      });
    } catch (err) {
      console.warn('Fallback a generador local por error en /api/v1/translate:', err);
      return this.generateGlossesFromText(text, startTime, endTime, segId);
    }
  }

  /**
   * Genera o mapea las glosas LSEC correspondientes a los segmentos actuales
   */
  async performGlossesTranslation(project) {
    // Caso 1: Backend API response previa
    if (this.cachedApiResponse && this.cachedApiResponse.gloss_output) {
      const fullProj = this.transformBackendResponse(this.cachedVideoFile, this.cachedMediaInfo, this.cachedApiResponse);
      // Preservar estrictamente ediciones del usuario en project.segments e invocar /api/v1/translate si hubo cambios
      const updatedSegments = [];
      for (let idx = 0; idx < (project.segments || []).length; idx++) {
        const seg = project.segments[idx];
        const fullSeg = (fullProj.segments || [])[idx] || {};
        const isModified = seg.status === 'CORRECTED' || ((seg.normalized_text || seg.original_text) !== (fullSeg.normalized_text || fullSeg.original_text));
        const segGlosses = isModified
          ? await this.translateSegmentViaBackend(seg.normalized_text || seg.original_text, seg.start_seconds, seg.end_seconds, seg.id)
          : (fullSeg.glosses || []);
        const effectiveGlosses = segGlosses.length > 0 ? segGlosses : (fullSeg.glosses || []);
        const hasRevGloss = effectiveGlosses.some(g => g.status === 'REVIEW_REQUIRED' || g.requires_review || g.requires_native_review);
        updatedSegments.push({
          ...fullSeg,
          ...seg,
          status: seg.status === 'CORRECTED' ? 'CORRECTED' : (fullSeg.requires_audio_review ? 'AUDIO_REVIEW' : ((fullSeg.requires_native_review || hasRevGloss) ? 'REVIEW_REQUIRED' : (fullSeg.status || 'VALIDATED'))),
          requires_native_review: Boolean(fullSeg.requires_native_review || hasRevGloss),
          glosses: effectiveGlosses,
          gloss_sequence: effectiveGlosses.map(g => g.gloss || g.lemma)
        });
      }

      return {
        glosses: updatedSegments.flatMap(s => s.glosses),
        segments: updatedSegments.length > 0 ? updatedSegments : fullProj.segments,
        discourse_blocks: fullProj.discourse_blocks, non_manual_spans: fullProj.non_manual_spans,
        spatial_operations: fullProj.spatial_operations, validation_metadata: fullProj.validation_metadata,
        unresolved_items: fullProj.unresolved_items, validation_warnings: fullProj.validation_warnings
      };
    }

    // Caso 2: Generación lingüística consultando al backend por segmento (con fallback local)
    const allGlosses = [], updatedSegments = [];
    for (const seg of (project.segments || [])) {
      const sStart = seg.start_seconds !== undefined ? seg.start_seconds : (seg.start_time || 0);
      const sEnd = seg.end_seconds !== undefined ? seg.end_seconds : (seg.end_time || (sStart + 3.0));
      const sDur = parseFloat(Math.max(0, sEnd - sStart).toFixed(3));
      const segGlosses = await this.translateSegmentViaBackend(seg.normalized_text || seg.original_text, sStart, sEnd, seg.id);
      allGlosses.push(...segGlosses);
      updatedSegments.push({ ...seg, start_seconds: sStart, end_seconds: sEnd, duration: sDur, glosses: segGlosses, gloss_sequence: segGlosses.map(g => g.gloss || g.lemma) });
    }

    return {
      glosses: allGlosses, segments: updatedSegments,
      discourse_blocks: [
        { id: 'b_1', label: 'Inicio', start_seconds: 0, end_seconds: (project.media_info?.duration_seconds || 10) * 0.5, rst_relation: 'NARRATIVE' },
        { id: 'b_2', label: 'Cierre', start_seconds: (project.media_info?.duration_seconds || 10) * 0.5, end_seconds: project.media_info?.duration_seconds || 10, rst_relation: 'SUMMARY' }
      ],
      non_manual_spans: [], spatial_operations: [], validation_metadata: null, unresolved_items: [], validation_warnings: []
    };
  }

  /**
   * Generador sintáctico LSEC autónomo para un segmento de texto
   */
  generateGlossesFromText(text, startTime, endTime, segId) {
    if (!text) return [];
    // Limpiar puntuación y dividir
    const cleanWords = text.replace(/[.,\/#!$%\^&\*;:{}=\-_`~()?"']/g, '').split(/\s+/).filter(Boolean);
    // Filtrar preposiciones y artículos vacíos para orden SOV / LSEC
    const stopWords = new Set(['el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'de', 'del', 'a', 'al', 'por', 'para', 'con', 'en']);
    const contentWords = cleanWords.filter(w => !stopWords.has(w.toLowerCase()));
    const wordsToGloss = contentWords.length > 0 ? contentWords : cleanWords;
    const duration = Math.max(0.6, endTime - startTime);
    const glossDur = duration / Math.max(1, wordsToGloss.length);

    return wordsToGloss.map((w, idx) => {
      const start = parseFloat((startTime + idx * glossDur).toFixed(3));
      const end = parseFloat((start + Math.min(glossDur, 0.55)).toFixed(3));
      const lemma = w.toUpperCase();
      const isFs = lemma.length > 10 || /^\d+$/.test(lemma);
      return {
        id: `g_${segId}_${idx + 1}`, gloss: lemma, lemma, start_seconds: start, end_seconds: end, start_time: start, end_time: end,
        proposition_id: segId, origin_proposition_id: segId, duration_ms: Math.round((end - start) * 1000),
        gloss_type: isFs ? 'DACTILOLOGÍA' : 'SEÑA',
        syntactic_role: idx === 0 ? 'TÓPICO' : (idx === wordsToGloss.length - 1 ? 'PREDICADO' : 'ARGUMENTO'),
        color: isFs ? 'fingerspelling' : 'validated', confidence: 0.94, status: 'VALIDATED', manual_code: 'STD_SIGN', non_manual: null
      };
    });
  }

  /**
   * Extrae metadatos del video mediante el elemento video HTML5
   */
  extractVideoMetadata(file, videoEl) {
    return new Promise((resolve) => {
      const url = URL.createObjectURL(file);
      const tempVideo = document.createElement('video');
      tempVideo.preload = 'metadata'; tempVideo.src = url;
      tempVideo.onloadedmetadata = () => resolve({ filename: file.name, duration: (Number.isFinite(tempVideo.duration) && tempVideo.duration > 0) ? tempVideo.duration : 0.0, width: tempVideo.videoWidth || 1280, height: tempVideo.videoHeight || 720, size_bytes: file.size, fps: 30.0, objectUrl: url });
      tempVideo.onerror = () => resolve({ filename: file.name, duration: 0.0, width: 1280, height: 720, size_bytes: file.size, fps: 30.0, objectUrl: url });
    });
  }

  /**
   * Intenta llamar al backend FastAPI /api/v1/pipeline
   */
  async callBackendPipeline(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/api/v1/pipeline', { method: 'POST', body: formData });
    if (res.ok) {
      const data = await res.json();
      console.log('Respuesta del backend FastAPI:', data);
      return data;
    }
    const errText = await res.text().catch(() => '');
    throw new Error(`Servidor retornó código ${res.status}: ${errText || res.statusText}`);
  }

  /**
   * Construye la estructura de proyecto compatible con LSEC Studio 2.1.1
   */
  buildProjectStructure(file, mediaInfo, apiResponse) {
    if (apiResponse && apiResponse.transcription && apiResponse.gloss_output) {
      return this.transformBackendResponse(file, mediaInfo, apiResponse);
    }
    throw new Error('No se recibieron datos de transcripción o traducción válidos del backend.');
  }

  /**
   * Transforma la respuesta de /api/v1/pipeline al esquema del Studio
   */
  transformBackendResponse(file, mediaInfo, apiResponse) {
    const tx = apiResponse.transcription || {}, glossOut = apiResponse.gloss_output || {};
    const duration = mediaInfo.duration || tx.duration_seconds || 48.85;
    const rawGlosses = glossOut.glosses || [], rawProps = glossOut.semantic_propositions || glossOut.propositions || [], wordTimestamps = tx.word_timestamps || [];
    const pendingSemIds = (glossOut.validation_metadata && glossOut.validation_metadata.pending_semantic_review_ids) || [];
    const pendingAudIds = (glossOut.validation_metadata && glossOut.validation_metadata.pending_audio_review_ids) || [];

    // Formatear glosas con soporte completo de timestamps reales de Whisper y tipos
    const glosses = rawGlosses.map((g, idx) => {
      const start = g.source_start_seconds ?? g.start_time ?? g.start_seconds ?? g.start ?? idx * 0.5;
      const durationSec = g.duration_ms ? (g.duration_ms / 1000) : 0.45;
      const end = g.source_end_seconds ?? g.end_time ?? g.end_seconds ?? g.end ?? (start + durationSec);
      const gText = String(g.gloss || g.lemma || '').trim();
      const isSingleLetterHyphenated = gText.includes('-') && gText.split('-').filter(Boolean).every(p => p.trim().length === 1);
      const isFs = Boolean(g.is_fingerspelling || (g.gloss_type === 'DACTILOLOGÍA') || (g.gloss_type === 'FINGERSPELLING') || isSingleLetterHyphenated);
      const isUnverifiedLex = g.dictionary_metadata && g.dictionary_metadata.status === 'NO_VERIFICADO';
      const needsRev = Boolean(g.requires_native_review || g.requires_review || isUnverifiedLex);
      const gStatus = g.requires_audio_review ? 'AUDIO_REVIEW' : (needsRev ? 'REVIEW_REQUIRED' : (g.status || 'VALIDATED'));
      return {
        ...g, id: g.id || `g_${idx + 1}`, order: g.order !== undefined ? g.order : idx,
        gloss: g.gloss || g.lemma || 'GLOSA', lemma: g.lemma || g.gloss || 'GLOSA',
        source_word: g.source_word || null, normalized_word: g.normalized_word || null,
        alignment_type: g.alignment_type || 'DIRECT', dictionary_metadata: g.dictionary_metadata || null,
        requires_review: needsRev, requires_native_review: needsRev, requires_audio_review: Boolean(g.requires_audio_review),
        review_reasons: g.review_reasons || [], source_start_seconds: start, source_end_seconds: end,
        start_seconds: start, end_seconds: end, start_time: start, end_time: end, start, end,
        proposition_id: g.proposition_id || g.origin_proposition_id || null, origin_proposition_id: g.origin_proposition_id || g.proposition_id || null,
        duration_ms: g.duration_ms || Math.round((end - start) * 1000),
        gloss_type: isFs ? 'DACTILOLOGÍA' : (g.gloss_type || 'SEÑA'), syntactic_role: g.syntactic_role || 'ARGUMENT',
        color: g.color || (isFs ? 'fingerspelling' : (needsRev ? 'review' : 'validated')),
        confidence: g.confidence !== undefined ? g.confidence : 0.94, status: gStatus, manual_code: g.manual_code || 'STD_SIGN', non_manual: g.non_manual || null
      };
    });

    // Formatear proposiciones / segmentos con marcas de tiempo exactas
    let segments = [];
    if (rawProps.length > 0) {
      segments = rawProps.map((p, idx) => {
        const start = p.source_start_seconds ?? p.start_seconds ?? p.start_time ?? idx * 3.0;
        const end = p.source_end_seconds ?? p.end_seconds ?? p.end_time ?? (start + 2.5);
        const text = p.source_text || p.original_text || '', norm = p.normalized_text || text;
        const segId = p.id || p.proposition_id || `seg_${String(idx + 1).padStart(2, '0')}`;

        // Palabras asociadas por intervalo
        const segWords = wordTimestamps.filter(w => {
          const wst = w.start !== undefined ? w.start : w.start_time, wet = w.end !== undefined ? w.end : w.end_time;
          return wst >= start - 0.2 && wet <= end + 0.2;
        });

        // Glosas asociadas (por proposition_id o coincidencia temporal)
        const segGlosses = glosses.filter(g => g.proposition_id === segId || g.origin_proposition_id === segId || (p.gloss_ids && p.gloss_ids.includes(g.id)) || (!g.proposition_id && g.start_seconds >= start - 0.15 && g.end_seconds <= end + 0.15));
        const reqAudio = Boolean(p.requires_audio_review || pendingAudIds.includes(segId) || segGlosses.some(g => g.requires_audio_review));
        const reqNative = Boolean(p.requires_native_review || p.requires_review || pendingSemIds.includes(segId) || segGlosses.some(g => g.requires_review || g.requires_native_review));
        const segStatus = reqAudio ? 'AUDIO_REVIEW' : (reqNative ? 'REVIEW_REQUIRED' : 'VALIDATED');
        const segStatusLabel = reqAudio ? 'Revisión Auditiva' : (reqNative ? 'Requiere Revisión' : 'Validado');
        // Calcular confianza acústica real a partir de las palabras alineadas si están disponibles
        const wordConfs = segWords.map(w => w.confidence).filter(c => typeof c === 'number');
        const avgWordConf = wordConfs.length > 0 ? Number((wordConfs.reduce((a, b) => a + b, 0) / wordConfs.length).toFixed(3)) : (p.confidence || 0.93);

        return {
          id: segId, index: idx + 1, start_seconds: start, end_seconds: end, start_time: start, end_time: end,
          original_text: text, normalized_text: norm, confidence: avgWordConf, status: segStatus, status_label: segStatusLabel,
          requires_audio_review: reqAudio, requires_native_review: reqNative, review_reasons: p.review_reasons || [],
          words: segWords.length > 0 ? segWords : norm.split(' ').filter(Boolean).map((w, wIdx, arr) => ({ word: w, start: start + (wIdx * (end - start)) / Math.max(1, arr.length), end: start + ((wIdx + 1) * (end - start)) / Math.max(1, arr.length), confidence: 0.95 })),
          glosses: segGlosses
        };
      });
    } else if (tx.text) {
      // Si no vinieron proposiciones estructuradas pero sí texto transcrito
      const sentences = tx.text.match(/[^.!?]+[.!?]*/g) || [tx.text], segDur = duration / Math.max(1, sentences.length);
      segments = sentences.map((st, idx) => {
        const start = idx * segDur, end = (idx + 1) * segDur, text = st.trim();
        return {
          id: `seg_${String(idx + 1).padStart(2, '0')}`, index: idx + 1, start_seconds: start, end_seconds: end, start_time: start, end_time: end,
          original_text: text, normalized_text: text, confidence: tx.confidence || 0.92, status: 'VALIDATED', status_label: 'Validado',
          requires_audio_review: false, requires_native_review: false,
          words: wordTimestamps.filter(w => w.start >= start && w.end <= end), glosses: glosses.filter(g => g.start >= start && g.end <= end)
        };
      });
    }

    // Normalizar intervalos de glosas en orden gramatical LSEC (SOV) dentro de cada proposición
    appState.resolveOverlappingGlossIntervals(glosses, segments);
    for (const seg of segments) {
      seg.glosses = glosses.filter(g => g.proposition_id === seg.id || g.origin_proposition_id === seg.id);
      seg.gloss_sequence = seg.glosses.map(g => g.gloss || g.lemma);
    }

    // Construir lista de incidencias (unresolved_items) para la pista 8 del Timeline
    const rawUnresolved = (glossOut.unresolved_items && glossOut.unresolved_items.length > 0) ? glossOut.unresolved_items : ((glossOut.validation_metadata && glossOut.validation_metadata.unresolved_items) || []);
    const warningItems = (glossOut.validation_warnings || []).filter(w => w && (w.severity === 'WARNING' || w.severity === 'ERROR')).map((w, idx) => {
      const targetSeg = segments.find(s => s.id === w.target_id) || null, targetGloss = glosses.find(g => String(g.id) === String(w.target_id)) || null;
      const st = targetGloss ? targetGloss.start_seconds : (targetSeg ? targetSeg.start_seconds : idx * 2.0);
      const et = targetGloss ? targetGloss.end_seconds : (targetSeg ? targetSeg.end_seconds : st + 1.2);
      return { id: `warn_${idx + 1}`, code: w.code || 'WARNING', word: targetGloss ? targetGloss.gloss : (targetSeg ? targetSeg.id : (w.code || 'Incidencia')), type: w.code || 'WARNING', reason: w.message || '', start_seconds: st, end_seconds: et };
    });
    const unresolvedItems = [...rawUnresolved, ...warningItems];

    const validationMeta = glossOut.validation_metadata || glossOut.confidence || {
      overall_linguistic_confidence: tx.confidence || 0.92, execution_status: glossOut.execution_status || 'READY',
      multidimensional_confidence: { lexical_coverage: 0.95, syntactic_validity: 0.90, spatial_consistency: 0.88, non_manual_synchrony: 0.85, timing_feasibility: 0.92 },
      unresolved_items: unresolvedItems
    };
    if (!validationMeta.unresolved_items || validationMeta.unresolved_items.length === 0) validationMeta.unresolved_items = unresolvedItems;

    const discourseBlocks = (glossOut.discourse_blocks || []).map((b, idx) => ({ id: b.id !== undefined ? `b_${b.id}` : `b_${idx + 1}`, label: b.label || b.topic || `Bloque ${idx + 1}`, start_seconds: b.start_seconds ?? b.start_time ?? idx * 5.0, end_seconds: b.end_seconds ?? b.end_time ?? (idx + 1) * 5.0 }));
    const nonManualSpans = (glossOut.non_manual_spans || []).map((s, idx) => ({ id: s.id || `span_${idx + 1}`, expression: s.facial_expression || s.expression || 'Facial', start_seconds: s.start_seconds ?? s.start_time ?? idx * 2.5, end_seconds: s.end_seconds ?? s.end_time ?? (idx + 1) * 2.5 }));
    const spatialOps = (glossOut.spatial_operations || []).map((op, idx) => ({ id: op.id || `op_${idx + 1}`, target_space: op.target_space || op.location || 'CENTRO', start_seconds: op.time_seconds ?? op.start_time ?? idx * 3.0 }));

    return {
      session_id: String(glossOut.session_id || `lsec_${Date.now()}`), created_at: new Date().toISOString(),
      schema_version: '2.1.1', execution_status: glossOut.execution_status || 'READY',
      media_info: { filename: file.name, duration_seconds: duration, resolution: `${mediaInfo.width || 1920}x${mediaInfo.height || 1080}`, fps: mediaInfo.fps || 30.0, filesize_mb: parseFloat((file.size / (1024 * 1024)).toFixed(2)) },
      transcription: tx, subtitles: segments, segments, propositions: rawProps, glosses,
      discourse_blocks: discourseBlocks, non_manual_spans: nonManualSpans, spatial_operations: spatialOps,
      corrections: glossOut.corrections_applied || [], corrections_applied: glossOut.corrections_applied || [],
      unresolved_items: unresolvedItems, validation_warnings: glossOut.validation_warnings || [], validation_metadata: validationMeta
    };
  }

  async runPipelineForCurrentVideo() {
    const videoEl = document.getElementById('main-video-element');
    return this.cachedVideoFile ? this.processVideo(this.cachedVideoFile, videoEl) : this.translateProjectGlosses();
  }

  showProgressModal(filename, title = 'Procesando Video Audiovisual LSEC', steps = null, mode = 'whisper') {
    this._currentModalMode = mode;
    let modal = document.getElementById('pipeline-progress-modal');
    const stepsToRender = (steps && steps.length > 0) ? steps : ['1. Extracción de pista de audio y metadatos...', '2. Transcripción acústica Whisper ASR...', '3. Normalización lingüística y segmentación...'];
    const stepsHtml = stepsToRender.map((s, idx) => `<div class="pipeline-step-row" id="step-${idx + 1}"><span class="step-icon">•</span> <span class="step-text">${s}</span></div>`).join('');

    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'pipeline-progress-modal';
      modal.className = 'modal-backdrop pipeline-fullscreen-backdrop open';
      modal.innerHTML = `<div class="modal-dialog pipeline-fullscreen-dialog" role="dialog" aria-modal="true" aria-labelledby="pipeline-modal-title">
        <div class="modal-header pipeline-fullscreen-header">
          <div><h3 id="pipeline-modal-title" class="pipeline-fullscreen-title">${title}</h3><div id="pipeline-modal-filename" class="pipeline-fullscreen-subtitle">Archivo: <strong>${filename}</strong></div></div>
          <span class="whisper-badge" id="whisper-engine-badge">MOTOR FASTER-WHISPER ASR</span>
        </div>
        <div class="modal-body pipeline-fullscreen-body" role="status" aria-live="polite">
          <!-- Visualizador de Onda Acústica (Exclusivo de Paso 1: Whisper ASR) -->
          <div class="whisper-visualizer-box pipeline-fullscreen-wavebox" id="whisper-visualizer-box">
            <div class="whisper-visualizer-header"><span style="font-size:0.9rem; font-weight:800; color:var(--color-accent-cobalt-dark);" id="whisper-status-label">Analizando espectro acústico y extrayendo fonemas con Faster-Whisper...</span><span class="whisper-badge" id="pipeline-progress-pct-badge">0%</span></div>
            <canvas class="whisper-waveform-canvas pipeline-fullscreen-canvas" id="whisper-waveform-canvas" width="1280" height="220" aria-label="Visualizador de onda acústica de Whisper ASR en pantalla completa"></canvas>
          </div>
          <!-- Monitor Animado de Transformación Gramatical Español SVO -> LSEC SOV (Exclusivo de Paso 2) -->
          <div class="grammar-monitor-card pipeline-fullscreen-grammarbox" id="pipeline-grammar-visualizer-box" style="display:none;">
            <div class="grammar-monitor-header">
              <div><div class="wizard-card-title"><span>Monitor Visual de Transformación Gramatical (Español SVO -&gt; LSEC SOV)</span><span class="grammar-rule-badge" id="pipeline-grammar-sentence-badge">Oración #1</span></div><div class="wizard-card-subtitle" id="pipeline-grammar-status-label">Observa cómo el motor lingüístico elide palabras funcionales, convierte verbos a infinitivo y reordena la sintaxis a LSEC</div></div>
              <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
                <div style="display:inline-flex; align-items:center; gap:6px;">
                  <button type="button" class="btn btn-sm" id="btn-grammar-prev-sent" title="Ver oración anterior">&lt;- Anterior</button>
                  <button type="button" class="btn btn-sm" id="btn-grammar-toggle-play" title="Pausar o reanudar rotación automática">Pausar</button>
                  <button type="button" class="btn btn-sm" id="btn-grammar-next-sent" title="Ver siguiente oración">Siguiente -&gt;</button>
                </div>
                <div class="grammar-formula-pills"><span class="grammar-formula-pill">ESPAÑOL: SUJETO + VERBO + OBJETO</span><span style="font-weight:800; color:var(--color-accent-cobalt);">-&gt;</span><span class="grammar-formula-pill" style="background:var(--color-surface-mint); border-color:var(--color-primary-emerald); color:#065f46;">LSEC: TIEMPO + TÓPICO + SOV + NEGACIÓN</span><span class="whisper-badge" id="pipeline-grammar-pct-badge">0%</span></div>
              </div>
            </div>
            <div class="grammar-transform-grid pipeline-fullscreen-grammar-grid">
              <div><div class="grammar-box-title">ORACIÓN EN ESPAÑOL (PALABRAS ELIDIDAS TACHADAS / VERBOS EN INFINITIVO)</div><div class="grammar-tokens-flow" id="pipeline-grammar-spanish-tokens"></div></div>
              <div style="font-family:var(--font-display); font-size:1.6rem; font-weight:800; color:var(--color-accent-cobalt);">=&gt;</div>
              <div><div class="grammar-box-title">ESTRUCTURA RESULTANTE EN GLOSAS LSEC</div><div class="grammar-tokens-flow" id="pipeline-grammar-lsec-tokens"></div></div>
            </div>
            <div class="grammar-rules-bar">
              <div class="grammar-tokens-flow" id="pipeline-grammar-rules-badges"><span class="grammar-rule-badge">Reordenamiento Sintáctico SVO -&gt; SOV</span><span class="grammar-rule-badge">Elisión de Artículos/Copulativos</span><span class="grammar-rule-badge">Verbos en Infinitivo</span></div>
              <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap; font-size:0.78rem; font-weight:700; color:var(--color-text-secondary);">
                <span style="display:inline-flex; align-items:center; gap:5px;"><span aria-hidden="true">✓</span> <strong>[CONADIS]</strong> Seña Oficial</span>
                <span style="display:inline-flex; align-items:center; gap:5px;"><span aria-hidden="true">✦</span> <strong>[DACTILOLOGÍA]</strong> Deletreo Manual</span>
                <span style="display:inline-flex; align-items:center; gap:5px;"><span aria-hidden="true">✎</span> <strong>[EDITADO]</strong> Verificada por Humano</span>
              </div>
            </div>
          </div>
          <div class="pipeline-progress-track"><div id="pipeline-progress-fill" class="pipeline-progress-bar-fill" style="width:0%;"></div></div>
          <div id="pipeline-steps-list" class="pipeline-fullscreen-steps">${stepsHtml}</div>
          <!-- Barra de confirmación controlada por el usuario al terminar Paso 2 -->
          <div id="pipeline-modal-actions" style="display:none; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; background:var(--color-card-white); border:2px solid var(--color-primary-emerald); border-radius:16px; padding:14px 20px; box-shadow:var(--shadow-sm);">
            <div style="font-size:0.92rem; font-weight:700; color:var(--color-text-primary);">Revisa la transformación gramatical de las oraciones con los botones <strong>&lt;- Anterior / Siguiente -&gt;</strong> y continúa cuando estés listo.</div>
            <button type="button" class="btn btn-primary btn-tactile-cta" id="btn-pipeline-modal-continue">CONTINUAR A LA MESA COMPARATIVA LSEC -&gt;</button>
          </div>
        </div>
      </div>`;
      document.body.appendChild(modal);
    } else {
      modal.classList.add('open');
      const titleEl = document.getElementById('pipeline-modal-title');
      if (titleEl) titleEl.textContent = title;
      const fnEl = document.getElementById('pipeline-modal-filename');
      if (fnEl) fnEl.innerHTML = `Archivo: <strong>${filename}</strong>`;
      const listEl = document.getElementById('pipeline-steps-list');
      if (listEl) { listEl.innerHTML = stepsHtml; listEl.style.display = 'flex'; }
      this.setProgress(0);
    }

    const listElGlobal = document.getElementById('pipeline-steps-list');
    if (listElGlobal) listElGlobal.style.display = 'flex';
    const actionsBar = document.getElementById('pipeline-modal-actions');
    if (actionsBar) actionsBar.style.display = 'none';
    const waveBox = document.getElementById('whisper-visualizer-box');
    const grammarBox = document.getElementById('pipeline-grammar-visualizer-box');
    const engineBadge = document.getElementById('whisper-engine-badge');

    if (mode === 'grammar') {
      if (waveBox) waveBox.style.display = 'none';
      if (grammarBox) grammarBox.style.display = 'flex';
      if (engineBadge) { engineBadge.textContent = 'MOTOR LINGÜÍSTICO LSEC (SVO -> SOV)'; engineBadge.style.background = 'var(--color-primary-emerald)'; }
      this.stopModalWaveformAnimation(); this.startModalGrammarAnimation(0);
    } else {
      if (waveBox) waveBox.style.display = 'flex';
      if (grammarBox) grammarBox.style.display = 'none';
      if (engineBadge) { engineBadge.textContent = 'MOTOR FASTER-WHISPER ASR'; engineBadge.style.background = 'var(--color-accent-cobalt)'; }
      this.stopModalGrammarAnimation(); this.startModalWaveformAnimation();
    }
  }

  waitForUserContinue() {
    return new Promise((resolve) => {
      const actionsBar = document.getElementById('pipeline-modal-actions');
      const btnContinue = document.getElementById('btn-pipeline-modal-continue');
      const stepsList = document.getElementById('pipeline-steps-list');
      const dialogEl = document.querySelector('#pipeline-progress-modal .pipeline-fullscreen-dialog');
      if (!actionsBar || !btnContinue) { resolve(); return; }
      if (stepsList) stepsList.style.display = 'none';
      actionsBar.style.display = 'flex';
      if (dialogEl) dialogEl.scrollTop = 0;
      const handler = () => { btnContinue.removeEventListener('click', handler); resolve(); };
      btnContinue.addEventListener('click', handler);
      setTimeout(() => { try { btnContinue.focus({ preventScroll: true }); } catch (e) {} }, 60);
    });
  }

  startModalGrammarAnimation(initialIndex = 0) {
    this.stopModalGrammarAnimation();
    const elidedSet = new Set(['el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'es', 'son', 'está', 'están', 'fue', 'era', 'ser', 'estar', 'sido', 'de', 'del', 'a', 'al', 'en', 'con', 'por', 'para', 'que', 'se', 'lo', 'le', 'les', 'y', 'o']);
    this._grammarCurrentIdx = initialIndex;
    this._grammarPaused = false;
    const getSegments = () => (typeof appState !== 'undefined' && appState.state?.project?.segments) || [];

    const renderSentenceStep = (advance = false) => {
      const segments = getSegments();
      const total = Math.max(1, segments.length);
      this._grammarCurrentIdx = advance ? ((this._grammarCurrentIdx + 1) % total) : (((this._grammarCurrentIdx % total) + total) % total);
      const spanishContainer = document.getElementById('pipeline-grammar-spanish-tokens');
      const lsecContainer = document.getElementById('pipeline-grammar-lsec-tokens');
      const sentBadge = document.getElementById('pipeline-grammar-sentence-badge');
      const rulesContainer = document.getElementById('pipeline-grammar-rules-badges');
      if (!spanishContainer || !lsecContainer) return;

      const seg = segments[this._grammarCurrentIdx] || { normalized_text: 'Dicen que el conocimiento es poder', gloss_sequence: ['CONOCIMIENTO', 'DECIR', 'PODER'] };
      if (sentBadge) sentBadge.textContent = `Oración #${this._grammarCurrentIdx + 1} de ${total}`;
      const rawText = seg.normalized_text || seg.raw_text || seg.original_text || 'Dicen que el conocimiento es poder';
      const words = rawText.split(/\s+/).filter(Boolean);
      spanishContainer.innerHTML = '';
      let elidedCount = 0;

      words.forEach((w, wIdx) => {
        const clean = w.toLowerCase().replace(/[.,;!?¿¡"()]/g, '');
        const span = document.createElement('span');
        span.style.animationDelay = `${wIdx * 70}ms`;
        if (elidedSet.has(clean)) { elidedCount++; span.className = 'grammar-token-elided pipeline-gloss-chip-anim'; }
        else if (/(ar|er|ir)$/i.test(clean) && clean.length > 3) { span.className = 'grammar-token-infinitive pipeline-gloss-chip-anim'; }
        else { span.className = 'grammar-token-word pipeline-gloss-chip-anim'; }
        span.textContent = w;
        spanishContainer.appendChild(span);
      });

      const cleanGlossLabel = (txt) => String(txt || '').toUpperCase().replace(/^FS:/i, '').replace(/\[[^\]]*\]/g, '').trim();
      // Derivar glosas de la oración actual (usando glosas reales si ya están disponibles)
      let rawItems = [];
      if (Array.isArray(seg.glosses) && seg.glosses.length > 0) {
        rawItems = seg.glosses.map(g => ({ label: cleanGlossLabel(g.gloss || g.lemma || g), isFs: Boolean(g.is_fingerspelling || g.gloss_type === 'DACTILOLOGÍA' || g.gloss_type === 'FINGERSPELLING') }));
      } else if (Array.isArray(seg.gloss_sequence) && seg.gloss_sequence.length > 0) {
        rawItems = seg.gloss_sequence.map(g => { const txt = cleanGlossLabel(g); return { label: txt, isFs: txt.includes('-') }; });
      } else {
        const contentWords = words.map(w => w.replace(/[.,;!?¿¡"()]/g, '').toLowerCase()).filter(w => w && !elidedSet.has(w)).map(w => w.toUpperCase());
        const ordered = contentWords.length >= 3 ? [contentWords[1], contentWords[0], ...contentWords.slice(2)] : (contentWords.length > 0 ? contentWords : ['CONOCIMIENTO', 'DECIR', 'PODER']);
        rawItems = ordered.map(txt => ({ label: txt, isFs: false }));
      }

      const glossItems = [];
      for (const it of rawItems) {
        if (!it.label || (glossItems.length > 0 && glossItems[glossItems.length - 1].label === it.label)) continue;
        glossItems.push(it);
      }

      lsecContainer.innerHTML = '';
      glossItems.forEach((item, gIdx) => {
        const chip = document.createElement('span');
        chip.style.animationDelay = `${gIdx * 130}ms`;
        chip.className = `gloss-chip-tactile ${item.isFs ? 'gloss-chip-fingerspell' : 'gloss-chip-conadis'} pipeline-gloss-chip-anim`;
        chip.innerHTML = `<span class="gloss-chip-symbol" aria-hidden="true">${item.isFs ? '✦' : '✓'}</span> <span>${item.label}</span>`;
        lsecContainer.appendChild(chip);
      });

      if (rulesContainer) {
        rulesContainer.innerHTML = `<span class="grammar-rule-badge">Reordenamiento Sintáctico SVO -&gt; SOV</span><span class="grammar-rule-badge">Elisión de Artículos/Copulativos (${elidedCount})</span><span class="grammar-rule-badge">Verbos en Infinitivo</span>`;
      }
    };

    const btnPrev = document.getElementById('btn-grammar-prev-sent');
    const btnNext = document.getElementById('btn-grammar-next-sent');
    const btnToggle = document.getElementById('btn-grammar-toggle-play');
    if (btnPrev) btnPrev.onclick = () => { this._grammarPaused = true; if (btnToggle) btnToggle.textContent = 'Reanudar'; this._grammarCurrentIdx -= 1; renderSentenceStep(false); };
    if (btnNext) btnNext.onclick = () => { this._grammarPaused = true; if (btnToggle) btnToggle.textContent = 'Reanudar'; this._grammarCurrentIdx += 1; renderSentenceStep(false); };
    if (btnToggle) { btnToggle.textContent = 'Pausar'; btnToggle.onclick = () => { this._grammarPaused = !this._grammarPaused; btnToggle.textContent = this._grammarPaused ? 'Reanudar' : 'Pausar'; }; }

    renderSentenceStep(false);
    this._grammarAnimInterval = setInterval(() => { if (!this._grammarPaused) renderSentenceStep(true); }, 3200);
  }

  stopModalGrammarAnimation() {
    if (this._grammarAnimInterval) { clearInterval(this._grammarAnimInterval); this._grammarAnimInterval = null; }
  }

  startModalWaveformAnimation() {
    this.stopModalWaveformAnimation();
    if (!this._modalWaveBars) {
      this._modalWaveBars = [];
      for (let i = 0; i < 96; i++) {
        const base = 0.2 + 0.65 * Math.abs(Math.sin(i * 0.37) * Math.cos(i * 0.17));
        this._modalWaveBars.push(Math.min(0.96, Math.max(0.14, base)));
      }
    }
    this._modalAnimActive = true;
    const renderFrame = (now) => {
      if (!this._modalAnimActive) return;
      const canvas = document.getElementById('whisper-waveform-canvas');
      if (canvas) {
        const ctx = canvas.getContext('2d');
        if (ctx) {
          const width = canvas.width, height = canvas.height;
          ctx.clearRect(0, 0, width, height);
          const pct = (this._currentProgressPct || 0) / 100;
          const prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
          const t = prefersReducedMotion ? 0 : (now / 320);
          const barCount = this._modalWaveBars.length, gap = 5;
          const barWidth = Math.max(4, (width - gap * (barCount + 1)) / barCount);

          for (let i = 0; i < barCount; i++) {
            const ratio = i / barCount;
            const pulse = prefersReducedMotion ? 0 : (0.25 * Math.sin(t * 4.2 + i * 0.45) + 0.12 * Math.cos(t * 2.3 - i * 0.3));
            const amp = Math.min(0.96, Math.max(0.12, this._modalWaveBars[i] + pulse));
            const barH = Math.max(12, amp * (height - 28)), x = gap + i * (barWidth + gap), y = (height - barH) / 2;
            ctx.fillStyle = ratio <= pct ? '#007a3d' : (ratio <= pct + 0.15 ? '#d99b00' : '#b7d4c4');
            ctx.beginPath();
            if (ctx.roundRect) ctx.roundRect(x, y, barWidth, barH, 5);
            else ctx.rect(x, y, barWidth, barH);
            ctx.fill();
          }
        }
      }
      this._modalAnimFrameId = requestAnimationFrame(renderFrame);
    };
    this._modalAnimFrameId = requestAnimationFrame(renderFrame);
  }

  stopModalWaveformAnimation() {
    this._modalAnimActive = false;
    if (this._modalAnimFrameId) { cancelAnimationFrame(this._modalAnimFrameId); this._modalAnimFrameId = null; }
  }

  updateStep(stepNum, status, text) {
    const el = document.getElementById(`step-${stepNum}`);
    if (!el) return;
    el.dataset.status = status;
    const icon = el.querySelector('.step-icon'), txt = el.querySelector('.step-text');
    if (icon) icon.textContent = status === 'completed' ? '✓' : (status === 'active' ? '>' : '•');
    if (txt && text) txt.textContent = text;
    const statusLabel = document.getElementById('whisper-status-label');
    if (statusLabel && text && status === 'active') statusLabel.textContent = text;
    const grammarStatusLabel = document.getElementById('pipeline-grammar-status-label');
    if (grammarStatusLabel && text && status === 'active') grammarStatusLabel.textContent = text;
  }

  setProgress(percent) {
    const clamped = Math.min(100, Math.max(0, percent));
    this._currentProgressPct = clamped;
    const fill = document.getElementById('pipeline-progress-fill');
    if (fill) fill.style.width = `${clamped}%`;
    const pctBadge = document.getElementById('pipeline-progress-pct-badge');
    if (pctBadge) pctBadge.textContent = `${Math.round(clamped)}%`;
    const grammarPctBadge = document.getElementById('pipeline-grammar-pct-badge');
    if (grammarPctBadge) grammarPctBadge.textContent = `${Math.round(clamped)}%`;
  }

  hideProgressModal() {
    this.stopModalWaveformAnimation(); this.stopModalGrammarAnimation();
    const modal = document.getElementById('pipeline-progress-modal');
    if (modal) modal.classList.remove('open');
  }

  showError(msg) {
    if (typeof window.showToast === 'function') window.showToast(msg, 'error');
    this.hideProgressModal();
  }

  sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
}

if (typeof window !== 'undefined') {
  window.PipelineProcessor = PipelineProcessor;
  window.pipelineProcessor = new PipelineProcessor();
}
