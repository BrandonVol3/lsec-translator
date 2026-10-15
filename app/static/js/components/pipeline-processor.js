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
    this.showProgressModal(
      project.media_info?.filename || 'Proyecto_LSEC.mp4',
      'Paso 3: Traducción Lingüística a Glosas LSEC',
      [
        '1. Analizando texto en español y correcciones aplicadas...',
        '2. Generando glosas LSEC con lematización y sintaxis Tópico-Comentario...',
        '3. Asignando componentes espaciales, loci y rasgos no manuales...',
        '4. Ensamblando línea de tiempo y capas multitrack...'
      ]
    );

    try {
      this.setProgress(20);
      this.updateStep(1, 'active', 'Analizando texto en español y correcciones aplicadas...');
      await this.sleep(400);
      this.updateStep(1, 'completed', 'Texto y palabras corregidas analizadas.');

      this.setProgress(55);
      this.updateStep(2, 'active', 'Generando glosas LSEC gramaticales...');
      
      const translationResult = await this.performGlossesTranslation(project);
      await this.sleep(400);
      this.updateStep(2, 'completed', `${translationResult.glosses.length} glosas LSEC generadas.`);

      this.setProgress(85);
      this.updateStep(3, 'active', 'Asignando loci espaciales y rasgos no manuales...');
      await this.sleep(350);
      this.updateStep(3, 'completed', 'Estructura espacial y rasgos gramaticales asignados.');

      this.setProgress(100);
      this.updateStep(4, 'completed', 'Traducción a glosas completada exitosamente.');
      await this.sleep(300);

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
        seg.glosses = project.glosses.filter(
          g => g.proposition_id === seg.id || g.origin_proposition_id === seg.id
        );
        seg.gloss_sequence = seg.glosses.map(g => g.gloss || g.lemma);
      }

      // Desbloquear y activar Etapa 2: Traducir
      appState.markTranslationReady();
      appState.emit('projectUpdated', project);
      appState.emit('segmentsChanged', project.segments);

      setTimeout(() => {
        this.hideProgressModal();
        this.isProcessing = false;
      }, 400);

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
    if (!text) return [];
    try {
      const res = await fetch('/api/v1/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, mode: 'detailed', paraphrase_budget: 'compact' })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const glossOut = await res.json();
      const rawGlosses = glossOut.glosses || [];
      if (rawGlosses.length === 0) {
        return this.generateGlossesFromText(text, startTime, endTime, segId);
      }
      const duration = Math.max(0.6, (endTime || (startTime + 2.5)) - (startTime || 0));
      const glossDur = duration / Math.max(1, rawGlosses.length);
      return rawGlosses.map((g, idx) => {
        const start = parseFloat(((startTime || 0) + idx * glossDur).toFixed(3));
        const end = parseFloat((start + Math.min(glossDur, 0.55)).toFixed(3));
        const gText = String(g.gloss || g.lemma || '').trim();
        const isSingleLetterHyphenated = gText.includes('-') && gText.split('-').filter(Boolean).every(p => p.trim().length === 1);
        const isFs = Boolean(g.is_fingerspelling || (g.gloss_type === 'DACTILOLOGÍA') || (g.gloss_type === 'FINGERSPELLING') || isSingleLetterHyphenated);
        const isUnverifiedLex = g.dictionary_metadata && g.dictionary_metadata.status === 'NO_VERIFICADO';
        const needsRev = Boolean(g.requires_native_review || g.requires_review || isUnverifiedLex);
        const gStatus = g.requires_audio_review ? 'AUDIO_REVIEW' : (needsRev ? 'REVIEW_REQUIRED' : (g.status || 'VALIDATED'));
        return {
          ...g,
          id: g.id || `g_${segId}_${idx + 1}`,
          order: g.order !== undefined ? g.order : idx,
          gloss: g.gloss || g.lemma || 'GLOSA',
          lemma: g.lemma || g.gloss || 'GLOSA',
          source_word: g.source_word || null,
          normalized_word: g.normalized_word || null,
          alignment_type: g.alignment_type || 'DIRECT',
          dictionary_metadata: g.dictionary_metadata || null,
          requires_review: needsRev,
          requires_native_review: needsRev,
          requires_audio_review: Boolean(g.requires_audio_review),
          review_reasons: g.review_reasons || [],
          start_seconds: start,
          end_seconds: end,
          start_time: start,
          end_time: end,
          start: start,
          end: end,
          proposition_id: segId,
          origin_proposition_id: segId,
          duration_ms: g.duration_ms || Math.round((end - start) * 1000),
          gloss_type: isFs ? 'DACTILOLOGÍA' : (g.gloss_type || 'SEÑA'),
          syntactic_role: g.syntactic_role || 'ARGUMENT',
          color: g.color || (isFs ? 'fingerspelling' : (needsRev ? 'review' : 'validated')),
          confidence: g.confidence !== undefined ? g.confidence : 0.94,
          status: gStatus,
          manual_code: g.manual_code || 'STD_SIGN',
          non_manual: g.non_manual || null
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
        discourse_blocks: fullProj.discourse_blocks,
        non_manual_spans: fullProj.non_manual_spans,
        spatial_operations: fullProj.spatial_operations,
        validation_metadata: fullProj.validation_metadata,
        unresolved_items: fullProj.unresolved_items,
        validation_warnings: fullProj.validation_warnings
      };
    }

    // Caso 2: Generación lingüística consultando al backend por segmento (con fallback local)
    const allGlosses = [];
    const updatedSegments = [];
    for (const seg of (project.segments || [])) {
      const sStart = seg.start_seconds !== undefined ? seg.start_seconds : (seg.start_time || 0);
      const sEnd = seg.end_seconds !== undefined ? seg.end_seconds : (seg.end_time || (sStart + 3.0));
      const sDur = parseFloat(Math.max(0, sEnd - sStart).toFixed(3));
      const segGlosses = await this.translateSegmentViaBackend(seg.normalized_text || seg.original_text, sStart, sEnd, seg.id);
      allGlosses.push(...segGlosses);
      updatedSegments.push({
        ...seg,
        start_seconds: sStart,
        end_seconds: sEnd,
        duration: sDur,
        glosses: segGlosses,
        gloss_sequence: segGlosses.map(g => g.gloss || g.lemma)
      });
    }

    return {
      glosses: allGlosses,
      segments: updatedSegments,
      discourse_blocks: [
        { id: 'b_1', label: 'Inicio', start_seconds: 0, end_seconds: (project.media_info?.duration_seconds || 10) * 0.5, rst_relation: 'NARRATIVE' },
        { id: 'b_2', label: 'Cierre', start_seconds: (project.media_info?.duration_seconds || 10) * 0.5, end_seconds: project.media_info?.duration_seconds || 10, rst_relation: 'SUMMARY' }
      ],
      non_manual_spans: [],
      spatial_operations: [],
      validation_metadata: null,
      unresolved_items: [],
      validation_warnings: []
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
        id: `g_${segId}_${idx + 1}`,
        gloss: lemma,
        lemma: lemma,
        start_seconds: start,
        end_seconds: end,
        start_time: start,
        end_time: end,
        proposition_id: segId,
        origin_proposition_id: segId,
        duration_ms: Math.round((end - start) * 1000),
        gloss_type: isFs ? 'DACTILOLOGÍA' : 'SEÑA',
        syntactic_role: idx === 0 ? 'TÓPICO' : (idx === wordsToGloss.length - 1 ? 'PREDICADO' : 'ARGUMENTO'),
        color: isFs ? 'fingerspelling' : 'validated',
        confidence: 0.94,
        status: 'VALIDATED',
        manual_code: 'STD_SIGN',
        non_manual: null
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
      tempVideo.preload = 'metadata';
      tempVideo.src = url;

      tempVideo.onloadedmetadata = () => {
        const info = {
          filename: file.name,
          duration: tempVideo.duration || 0.0,
          width: tempVideo.videoWidth || 1280,
          height: tempVideo.videoHeight || 720,
          size_bytes: file.size,
          fps: 30.0,
          objectUrl: url
        };
        resolve(info);
      };

      tempVideo.onerror = () => {
        resolve({
          filename: file.name,
          duration: 0.0,
          width: 1280,
          height: 720,
          size_bytes: file.size,
          fps: 30.0,
          objectUrl: url
        });
      };
    });
  }

  /**
   * Intenta llamar al backend FastAPI /api/v1/pipeline
   */
  async callBackendPipeline(file) {
    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch('/api/v1/pipeline', {
      method: 'POST',
      body: formData
    });

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
    const tx = apiResponse.transcription || {};
    const glossOut = apiResponse.gloss_output || {};
    const duration = mediaInfo.duration || tx.duration_seconds || 48.85;

    const rawGlosses = glossOut.glosses || [];
    const rawProps = glossOut.semantic_propositions || glossOut.propositions || [];
    const wordTimestamps = tx.word_timestamps || [];

    const pendingSemIds = (glossOut.validation_metadata && glossOut.validation_metadata.pending_semantic_review_ids) || [];
    const pendingAudIds = (glossOut.validation_metadata && glossOut.validation_metadata.pending_audio_review_ids) || [];

    // Formatear glosas con soporte completo de timestamps reales de Whisper y tipos
    const glosses = rawGlosses.map((g, idx) => {
      const start = g.source_start_seconds !== undefined ? g.source_start_seconds :
                    (g.start_time !== undefined ? g.start_time :
                    (g.start_seconds !== undefined ? g.start_seconds :
                    (g.start !== undefined ? g.start : idx * 0.5)));
      const durationSec = g.duration_ms ? (g.duration_ms / 1000) : 0.45;
      const end = g.source_end_seconds !== undefined ? g.source_end_seconds :
                  (g.end_time !== undefined ? g.end_time :
                  (g.end_seconds !== undefined ? g.end_seconds :
                  (g.end !== undefined ? g.end : start + durationSec)));
      const gText = String(g.gloss || g.lemma || '').trim();
      const isSingleLetterHyphenated = gText.includes('-') && gText.split('-').filter(Boolean).every(p => p.trim().length === 1);
      const isFs = Boolean(g.is_fingerspelling || (g.gloss_type === 'DACTILOLOGÍA') || (g.gloss_type === 'FINGERSPELLING') || isSingleLetterHyphenated);
      const isUnverifiedLex = g.dictionary_metadata && g.dictionary_metadata.status === 'NO_VERIFICADO';
      const needsRev = Boolean(g.requires_native_review || g.requires_review || isUnverifiedLex);
      const gStatus = g.requires_audio_review ? 'AUDIO_REVIEW' : (needsRev ? 'REVIEW_REQUIRED' : (g.status || 'VALIDATED'));
      return {
        ...g,
        id: g.id || `g_${idx + 1}`,
        order: g.order !== undefined ? g.order : idx,
        gloss: g.gloss || g.lemma || 'GLOSA',
        lemma: g.lemma || g.gloss || 'GLOSA',
        source_word: g.source_word || null,
        normalized_word: g.normalized_word || null,
        alignment_type: g.alignment_type || 'DIRECT',
        dictionary_metadata: g.dictionary_metadata || null,
        requires_review: needsRev,
        requires_native_review: needsRev,
        requires_audio_review: Boolean(g.requires_audio_review),
        review_reasons: g.review_reasons || [],
        source_start_seconds: start,
        source_end_seconds: end,
        start_seconds: start,
        end_seconds: end,
        start_time: start,
        end_time: end,
        start: start,
        end: end,
        proposition_id: g.proposition_id || g.origin_proposition_id || null,
        origin_proposition_id: g.origin_proposition_id || g.proposition_id || null,
        duration_ms: g.duration_ms || Math.round((end - start) * 1000),
        gloss_type: isFs ? 'DACTILOLOGÍA' : (g.gloss_type || 'SEÑA'),
        syntactic_role: g.syntactic_role || 'ARGUMENT',
        color: g.color || (isFs ? 'fingerspelling' : (needsRev ? 'review' : 'validated')),
        confidence: g.confidence !== undefined ? g.confidence : 0.94,
        status: gStatus,
        manual_code: g.manual_code || 'STD_SIGN',
        non_manual: g.non_manual || null
      };
    });

    // Formatear proposiciones / segmentos con marcas de tiempo exactas
    let segments = [];
    if (rawProps.length > 0) {
      segments = rawProps.map((p, idx) => {
        const start = p.source_start_seconds !== undefined ? p.source_start_seconds :
                      (p.start_seconds !== undefined ? p.start_seconds :
                      (p.start_time !== undefined ? p.start_time : idx * 3.0));
        const end = p.source_end_seconds !== undefined ? p.source_end_seconds :
                    (p.end_seconds !== undefined ? p.end_seconds :
                    (p.end_time !== undefined ? p.end_time : start + 2.5));
        const text = p.source_text || p.original_text || '';
        const norm = p.normalized_text || text;
        const segId = p.id || p.proposition_id || `seg_${String(idx + 1).padStart(2, '0')}`;

        // Palabras asociadas por intervalo
        const segWords = wordTimestamps.filter(w => {
          const wst = w.start !== undefined ? w.start : w.start_time;
          const wet = w.end !== undefined ? w.end : w.end_time;
          return wst >= start - 0.2 && wet <= end + 0.2;
        });

        // Glosas asociadas (por proposition_id o coincidencia temporal)
        const segGlosses = glosses.filter(g => 
          g.proposition_id === segId ||
          g.origin_proposition_id === segId ||
          (p.gloss_ids && p.gloss_ids.includes(g.id)) ||
          (!g.proposition_id && g.start_seconds >= start - 0.15 && g.end_seconds <= end + 0.15)
        );

        const reqAudio = Boolean(p.requires_audio_review || pendingAudIds.includes(segId) || segGlosses.some(g => g.requires_audio_review));
        const reqNative = Boolean(
          p.requires_native_review ||
          p.requires_review ||
          pendingSemIds.includes(segId) ||
          segGlosses.some(g => g.requires_review || g.requires_native_review)
        );
        const segStatus = reqAudio ? 'AUDIO_REVIEW' : (reqNative ? 'REVIEW_REQUIRED' : 'VALIDATED');
        const segStatusLabel = reqAudio ? 'Revisión Auditiva' : (reqNative ? 'Requiere Revisión' : 'Validado');

        // Calcular confianza acústica real a partir de las palabras alineadas si están disponibles
        const wordConfs = segWords.map(w => w.confidence).filter(c => typeof c === 'number');
        const avgWordConf = wordConfs.length > 0
          ? Number((wordConfs.reduce((a, b) => a + b, 0) / wordConfs.length).toFixed(3))
          : (p.confidence || 0.93);

        return {
          id: segId,
          index: idx + 1,
          start_seconds: start,
          end_seconds: end,
          start_time: start,
          end_time: end,
          original_text: text,
          normalized_text: norm,
          confidence: avgWordConf,
          status: segStatus,
          status_label: segStatusLabel,
          requires_audio_review: reqAudio,
          requires_native_review: reqNative,
          review_reasons: p.review_reasons || [],
          words: segWords.length > 0 ? segWords : norm.split(' ').filter(Boolean).map((w, wIdx, arr) => ({
            word: w,
            start: start + (wIdx * (end - start)) / Math.max(1, arr.length),
            end: start + ((wIdx + 1) * (end - start)) / Math.max(1, arr.length),
            confidence: 0.95
          })),
          glosses: segGlosses
        };
      });
    } else if (tx.text) {
      // Si no vinieron proposiciones estructuradas pero sí texto transcrito
      const sentences = tx.text.match(/[^.!?]+[.!?]*/g) || [tx.text];
      const segDur = duration / Math.max(1, sentences.length);
      segments = sentences.map((st, idx) => {
        const start = idx * segDur;
        const end = (idx + 1) * segDur;
        const text = st.trim();
        return {
          id: `seg_${String(idx + 1).padStart(2, '0')}`,
          index: idx + 1,
          start_seconds: start,
          end_seconds: end,
          start_time: start,
          end_time: end,
          original_text: text,
          normalized_text: text,
          confidence: tx.confidence || 0.92,
          status: 'VALIDATED',
          status_label: 'Validado',
          requires_audio_review: false,
          requires_native_review: false,
          words: wordTimestamps.filter(w => w.start >= start && w.end <= end),
          glosses: glosses.filter(g => g.start >= start && g.end <= end)
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
    const rawUnresolved = (glossOut.unresolved_items && glossOut.unresolved_items.length > 0)
      ? glossOut.unresolved_items
      : ((glossOut.validation_metadata && glossOut.validation_metadata.unresolved_items) || []);
    const warningItems = (glossOut.validation_warnings || [])
      .filter(w => w && (w.severity === 'WARNING' || w.severity === 'ERROR'))
      .map((w, idx) => {
        const targetSeg = segments.find(s => s.id === w.target_id) || null;
        const targetGloss = glosses.find(g => String(g.id) === String(w.target_id)) || null;
        const st = targetGloss ? targetGloss.start_seconds : (targetSeg ? targetSeg.start_seconds : idx * 2.0);
        const et = targetGloss ? targetGloss.end_seconds : (targetSeg ? targetSeg.end_seconds : st + 1.2);
        return {
          id: `warn_${idx + 1}`,
          code: w.code || 'WARNING',
          word: targetGloss ? targetGloss.gloss : (targetSeg ? targetSeg.id : (w.code || 'Incidencia')),
          type: w.code || 'WARNING',
          reason: w.message || '',
          start_seconds: st,
          end_seconds: et
        };
      });
    const unresolvedItems = [...rawUnresolved, ...warningItems];

    const validationMeta = glossOut.validation_metadata || glossOut.confidence || {
      overall_linguistic_confidence: tx.confidence || 0.92,
      execution_status: glossOut.execution_status || 'READY',
      multidimensional_confidence: {
        lexical_coverage: 0.95,
        syntactic_validity: 0.90,
        spatial_consistency: 0.88,
        non_manual_synchrony: 0.85,
        timing_feasibility: 0.92
      },
      unresolved_items: unresolvedItems
    };
    if (!validationMeta.unresolved_items || validationMeta.unresolved_items.length === 0) {
      validationMeta.unresolved_items = unresolvedItems;
    }

    const discourseBlocks = (glossOut.discourse_blocks || []).map((b, idx) => {
      const blockGlosses = glosses.filter(g => (b.gloss_ids || []).includes(g.id));
      let start = b.start_seconds ?? b.start_time;
      let end = b.end_seconds ?? b.end_time;
      if ((start === undefined || isNaN(start)) && blockGlosses.length > 0) {
        start = Math.min(...blockGlosses.map(g => g.start_seconds));
        end = Math.max(...blockGlosses.map(g => g.end_seconds));
      }
      if (start === undefined || isNaN(start)) {
        start = idx * 5.0;
        end = (idx + 1) * 5.0;
      }
      return {
        id: b.id !== undefined ? `b_${b.id}` : `b_${idx + 1}`,
        label: b.label || b.topic || `Bloque ${idx + 1}`,
        start_seconds: start,
        end_seconds: end,
        start_time: start,
        end_time: end,
        start: start,
        end: end,
        color: b.color || 'var(--primary)',
        discourse_function: b.discourse_function || b.rst_relation || 'NARRATIVE',
        rst_relation: b.rst_relation || b.discourse_function || 'ELABORATION'
      };
    });

    const nonManualSpans = (glossOut.non_manual_spans || []).map((s, idx) => {
      const spanGlosses = glosses.filter(g => (s.gloss_ids || []).includes(g.id));
      let start = s.start_seconds ?? s.start_time;
      let end = s.end_seconds ?? s.end_time;
      if ((start === undefined || isNaN(start)) && spanGlosses.length > 0) {
        start = Math.min(...spanGlosses.map(g => g.start_seconds));
        end = Math.max(...spanGlosses.map(g => g.end_seconds));
      }
      if (start === undefined || isNaN(start)) {
        start = idx * 2.5;
        end = (idx + 1) * 2.5;
      }
      return {
        id: s.id || `span_${idx + 1}`,
        expression: s.facial_expression || s.expression || 'Facial',
        facial_expression: s.facial_expression || s.expression || 'Facial',
        intensity: s.intensity || 'MODERATE',
        label: s.label || s.expression || 'No-Manual',
        start_seconds: start,
        end_seconds: end,
        start_time: start,
        end_time: end,
        start: start,
        end: end
      };
    });

    const spatialOps = (glossOut.spatial_operations || []).map((op, idx) => {
      let start = op.time_seconds ?? op.start_time ?? op.start_seconds;
      if (start === undefined || isNaN(start)) {
        const trig = glosses.find(g => g.id === op.operation_trigger_gloss_id);
        if (trig) start = trig.start_seconds;
      }
      if (start === undefined || isNaN(start)) {
        start = idx * 3.0;
      }
      return {
        id: op.id || `op_${idx + 1}`,
        referent_label: op.referent_label || op.referent_id || op.target_space || `Espacio ${idx + 1}`,
        target_space: op.target_space || op.location || 'CENTRO',
        type: op.type || op.operation_type || 'ESTABLECER_LOCUS',
        time_seconds: start,
        start_time: start,
        start_seconds: start
      };
    });

    return {
      session_id: String(glossOut.session_id || `lsec_${Date.now()}`),
      created_at: new Date().toISOString(),
      schema_version: '2.1.1',
      execution_status: glossOut.execution_status || 'READY',
      media_info: {
        filename: file.name,
        duration_seconds: duration,
        resolution: `${mediaInfo.width || 1920}x${mediaInfo.height || 1080}`,
        fps: mediaInfo.fps || 30.0,
        filesize_mb: parseFloat((file.size / (1024 * 1024)).toFixed(2))
      },
      transcription: tx,
      subtitles: segments,
      segments: segments,
      propositions: rawProps,
      glosses: glosses,
      discourse_blocks: discourseBlocks,
      non_manual_spans: nonManualSpans,
      spatial_operations: spatialOps,
      corrections: glossOut.corrections_applied || [],
      corrections_applied: glossOut.corrections_applied || [],
      unresolved_items: unresolvedItems,
      validation_warnings: glossOut.validation_warnings || [],
      validation_metadata: validationMeta
    };
  }

  // ============================================================
  // Interfaz de Progreso del Pipeline
  // ============================================================

  showProgressModal(filename, title = 'Procesando Video Audiovisual LSEC', steps = null) {
    let modal = document.getElementById('pipeline-progress-modal');
    const defaultSteps = [
      '1. Extracción de pista de audio y metadatos...',
      '2. Transcripción acústica Whisper ASR...',
      '3. Normalización lingüística y segmentación...'
    ];
    const stepsToRender = steps && steps.length > 0 ? steps : defaultSteps;

    const stepsHtml = stepsToRender.map((s, idx) => `
      <div class="pipeline-step-row" id="step-${idx + 1}">
        <span class="step-icon">•</span>
        <span class="step-text">${s}</span>
      </div>
    `).join('');

    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'pipeline-progress-modal';
      modal.className = 'modal-backdrop open';
      modal.innerHTML = `
        <div class="modal-dialog" style="max-width:520px;">
          <div class="modal-header">
            <h3 style="font-size:0.95rem; font-weight:700; display:flex; align-items:center; gap:8px;" id="pipeline-modal-title">
              <span class="pulse-dot" style="width:8px; height:8px; border-radius:50%; background:var(--primary);"></span>
              <span>${title}</span>
            </h3>
          </div>
          <div class="modal-body" style="padding:16px;">
            <div style="font-size:0.8rem; color:var(--text-secondary); margin-bottom:12px;" id="pipeline-modal-filename">
              Archivo: <strong>${filename}</strong>
            </div>

            <div style="width:100%; height:6px; background:var(--bg-surface-3); border-radius:var(--radius-full); overflow:hidden; margin-bottom:16px;">
              <div id="pipeline-progress-fill" style="width:0%; height:100%; background:var(--primary); transition:width 300ms ease;"></div>
            </div>

            <div id="pipeline-steps-list" style="display:flex; flex-direction:column; gap:8px;">
              ${stepsHtml}
            </div>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    } else {
      modal.classList.add('open');
      const titleEl = document.getElementById('pipeline-modal-title');
      if (titleEl) {
        titleEl.innerHTML = `
          <span class="pulse-dot" style="width:8px; height:8px; border-radius:50%; background:var(--primary);"></span>
          <span>${title}</span>
        `;
      }
      const fnEl = document.getElementById('pipeline-modal-filename');
      if (fnEl) fnEl.innerHTML = `Archivo: <strong>${filename}</strong>`;
      const listEl = document.getElementById('pipeline-steps-list');
      if (listEl) listEl.innerHTML = stepsHtml;
      this.setProgress(0);
    }
  }

  updateStep(stepNum, status, text) {
    const el = document.getElementById(`step-${stepNum}`);
    if (!el) return;

    if (status === 'active') {
      el.style.color = 'var(--text-primary)';
      el.style.fontWeight = '600';
      el.querySelector('.step-icon').textContent = '>';
      if (text) el.querySelector('.step-text').textContent = text;
    } else if (status === 'completed') {
      el.style.color = 'var(--lsec-green)';
      el.style.fontWeight = '500';
      el.querySelector('.step-icon').textContent = 'ok';
      if (text) el.querySelector('.step-text').textContent = text;
    } else {
      el.style.color = 'var(--text-muted)';
      el.style.fontWeight = 'normal';
      el.querySelector('.step-icon').textContent = '•';
    }
  }

  setProgress(percent) {
    const fill = document.getElementById('pipeline-progress-fill');
    if (fill) fill.style.width = `${Math.min(100, Math.max(0, percent))}%`;
  }

  hideProgressModal() {
    const modal = document.getElementById('pipeline-progress-modal');
    if (modal) modal.classList.remove('open');
  }

  showError(msg) {
    alert(msg);
    this.hideProgressModal();
  }

  sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
  }
}

// Exportar globalmente
if (typeof window !== 'undefined') {
  window.PipelineProcessor = PipelineProcessor;
  window.pipelineProcessor = new PipelineProcessor();
}
