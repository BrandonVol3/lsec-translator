/**
 * LSEC Studio 2.1.1 — Gestor de Estado Central Reactivo (State Store)
 * 
 * Centraliza el flujo de las 3 etapas (Preparar, Traducir, Revisar),
 * los 4 estados de segmentos (Borrador, Revisar, Corregido, Validado),
 * la selección del Inspector Contextual y el historial de revisiones humanas.
 */

class LSECStateStore {
  constructor() {
    this.listeners = new Map();
    this.undoStack = [];
    this.redoStack = [];
    this.saveTimeout = null;
    this.copiedSubtitleStyle = null;

    // Estado inicial limpio por defecto
    this.state = {
      // 1. Estado de Reproducción Audiovisual
      playback: {
        currentTime: 0.0,
        duration: 0.0,
        isPlaying: false,
        playbackRate: 1.0,
        volume: 0.9,
        isMuted: false,
        inPoint: null,
        outPoint: null,
        isLooping: false,
        activeWordIndex: -1,
        activeSegmentId: null,
        activeGlossId: null,
        activeBlockId: null,
        activeSpanId: null,
        selectedItem: null // { type: 'segment'|'gloss'|'locus'|'non_manual'|'issue', id: '...', data: {...} }
      },

      // 2. Datos del Proyecto y Validación Humana
      project: null,
      saveStatus: 'saved', // 'saved' | 'saving' | 'unsaved'
      unsavedChangesCount: 0,
      currentUser: {
        id: 'usr_reviewer',
        name: 'Revisor Lingüístico',
        role: 'Intérprete / Revisor LSEC',
        isNativeSigner: true
      },

      // 3. Preferencias de Capas Overlays
      overlays: {
        subtitlesEnabled: true,
        glossesEnabled: true,
        subtitleMode: 'normalized',
        subtitleWordHighlight: false,
        glossMode: 'current_proposition',
        subtitleStyle: {
          fontFamily: 'Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
          fontSize: 20,
          textColor: '#ffffff',
          bgColor: '#000000',
          bgOpacity: 0.0, // Fondo transparente por defecto
          outlineWidth: 0, // Sin contorno por defecto
          outlineColor: 'transparent',
          shadow: true,
          shadowBlur: 3,
          shadowColor: 'rgba(0, 0, 0, 0.85)',
          shadowOffsetX: 0,
          shadowOffsetY: 1,
          bold: false,
          italic: false,
          textAlign: 'center',
          positionX: 50,
          positionY: 88,
          margin: 6,
          safeArea: 5
        },
        glossStyle: {
          fontSize: 18,
          textColor: '#B7D36B',
          bgColor: 'rgba(25, 27, 24, 0.85)'
        }
      },

      // 4. Espacio de Trabajo y 3 Etapas Principales
      workspace: {
        stage: 'preparar', // 'preparar' | 'traducir' | 'revisar'
        theme: 'dark', // 'dark' | 'light' | 'high-contrast'
        fontSizeScale: 'normal',
        reducedMotion: false,
        autoScrollTranscript: true,
        isEditingTranscript: false,
        timelineZoom: 100, // 30% a 250%
        showAdvancedLayers: false, // false: 3 pistas base | true: 8 pistas completas
        bottomDockCollapsed: false,
        
        // Control de Flujo Secuencial y Bloqueo de Etapas
        videoLoaded: false,
        transcriptionReady: false,
        translationReady: false,
        translationConfirmed: false,
        workflowStep: 'no_video' // 'no_video' | 'step1_preparar' | 'step2_traducir' | 'step3_revisar' | 'completed'
      },

      // 5. Filtros de Búsqueda
      filters: {
        textQuery: '',
        statusFilter: 'ALL',
        quickFilter: 'ALL'
      }
    };

    this.init();
  }

  init() {
    this.loadPreferencesFromStorage();
  }

  // ============================================================
  // Sistema Pub/Sub de Eventos
  // ============================================================

  subscribe(eventName, callback) {
    if (!this.listeners.has(eventName)) {
      this.listeners.set(eventName, new Set());
    }
    this.listeners.get(eventName).add(callback);
    return () => this.unsubscribe(eventName, callback);
  }

  unsubscribe(eventName, callback) {
    if (this.listeners.has(eventName)) {
      this.listeners.get(eventName).delete(callback);
    }
  }

  emit(eventName, data) {
    if (this.listeners.has(eventName)) {
      this.listeners.get(eventName).forEach(cb => {
        try {
          cb(data);
        } catch (err) {
          console.error(`Error en listener de evento '${eventName}':`, err);
        }
      });
    }
  }

  // ============================================================
  // Carga y Normalización del Proyecto LSEC 2.1.1
  // ============================================================

  loadProject(projectData, filename = null) {
    if (!projectData) return;

    // Normalizar metadatos del medio
    if (!projectData.media_info) {
      projectData.media_info = {
        filename: filename || 'Video_LSEC.mp4',
        duration_seconds: 48.850,
        resolution: '1920x1080',
        fps: 30.0
      };
    }
    if (filename) {
      projectData.media_info.filename = filename;
    }

    // Normalizar Estado Global
    if (!projectData.execution_status) {
      projectData.execution_status = 'REVIEW_REQUIRED';
    }

    // Normalizar Segmentos (4 Estados Principales + Causas Secundarias)
    if (projectData.segments) {
      projectData.segments = projectData.segments.map((s, idx) => {
        const start = s.start_seconds != null ? s.start_seconds : (s.start_time != null ? s.start_time : (s.start != null ? s.start : idx * 3.0));
        const end = s.end_seconds != null ? s.end_seconds : (s.end_time != null ? s.end_time : (s.end != null ? s.end : (idx + 1) * 3.0));
        
        // Mapear a los 4 estados principales
        let status = s.status || 'DRAFT';
        if (status === 'VALIDATED') status = 'VALIDATED';
        else if (status === 'CORRECTED') status = 'CORRECTED';
        else if (status === 'REVIEW_REQUIRED' || status === 'NATIVE_REVIEW' || status === 'AUDIO_REVIEW' || status === 'BLOCKED') status = 'REVIEW_REQUIRED';
        else status = 'DRAFT';

        // Determinar causa secundaria
        let secondaryCause = s.secondary_cause || null;
        if (!secondaryCause) {
          if (s.requires_audio_review || s.status === 'AUDIO_REVIEW') secondaryCause = 'Audio';
          else if (s.requires_native_review || s.status === 'NATIVE_REVIEW') secondaryCause = 'Sintaxis LSEC';
          else if (s.original_text !== s.normalized_text) secondaryCause = 'Corrección Léxica';
        }

        const segText = s.normalized_text || s.original_text || s.source_text || s.text || '';
        const isQuestionSeg = segText.includes('?') || segText.includes('¿');
        const derivedLoci = Array.isArray(s.glosses) && s.glosses.length > 0
          ? Array.from(new Set(s.glosses.map(g => g.spatial_locus || 'CENTRO')))
          : ['CENTRO'];
        const derivedNmf = isQuestionSeg ? ['Cejas levantadas (Pregunta)'] : ['Atención neutra'];

        return {
          ...s,
          id: s.id || `seg_${String(idx + 1).padStart(2, '0')}`,
          index: s.index !== undefined ? s.index : idx + 1,
          start_seconds: start,
          end_seconds: end,
          start_time: start,
          end_time: end,
          duration: parseFloat((end - start).toFixed(3)),
          original_text: s.original_text || s.source_text || s.text || '',
          normalized_text: segText,
          status: status, // 'DRAFT' | 'REVIEW_REQUIRED' | 'CORRECTED' | 'VALIDATED'
          status_label: this.getStatusLabel(status),
          secondary_cause: secondaryCause,
          confidence: s.confidence || 0.94,
          confidence_explanation: this.explainConfidence(s.confidence || 0.94, 'audio'),
          human_reviewed: !!s.human_reviewed,
          validated_by: s.validated_by || null,
          validated_at: s.validated_at || null,
          comments: s.comments || [],
          words: s.words || [],
          gloss_sequence: s.gloss_sequence || (s.glosses ? s.glosses.map(g => g.gloss || g.lemma) : []),
          spatial_loci: s.spatial_loci || derivedLoci,
          non_manual_features: s.non_manual_features || derivedNmf,
          subtitle_style: s.subtitle_style ? { ...s.subtitle_style } : null
        };
      });
    } else {
      projectData.segments = [];
    }

    // Normalizar Glosas
    if (projectData.glosses) {
      let fallbackCursor = 0.0;
      projectData.glosses = projectData.glosses.map((g, idx) => {
        const durFallback = g.duration_ms ? (g.duration_ms / 1000) : 0.45;
        const start = g.start_seconds != null ? g.start_seconds :
                      (g.source_start_seconds != null ? g.source_start_seconds :
                      (g.start_time != null ? g.start_time :
                      (g.start != null ? g.start : Number(fallbackCursor.toFixed(3)))));
        const end = g.end_seconds != null ? g.end_seconds :
                    (g.source_end_seconds != null ? g.source_end_seconds :
                    (g.end_time != null ? g.end_time :
                    (g.end != null ? g.end : Number((start + durFallback).toFixed(3)))));
        fallbackCursor = Math.max(fallbackCursor + durFallback, end);
        const gText = String(g.gloss || g.lemma || '').trim();
        const isSingleLetterHyphenated = gText.includes('-') && gText.split('-').filter(Boolean).every(p => p.trim().length === 1);
        const isFs = Boolean(g.is_fingerspelling || (g.gloss_type === 'DACTILOLOGÍA') || isSingleLetterHyphenated);
        return {
          ...g,
          id: g.id || `g_${idx + 1}`,
          gloss: g.gloss || g.lemma || 'GLOSA',
          lemma: g.lemma || g.gloss || 'GLOSA',
          source_start_seconds: g.source_start_seconds != null ? g.source_start_seconds : start,
          source_end_seconds: g.source_end_seconds != null ? g.source_end_seconds : end,
          start_seconds: start,
          end_seconds: end,
          start_time: start,
          end_time: end,
          is_fingerspelling: isFs,
          gloss_type: isFs ? 'DACTILOLOGÍA' : (g.gloss_type || 'SEÑA'),
          syntactic_role: g.syntactic_role || (idx === 0 ? 'TÓPICO' : (idx === 1 ? 'PREDICADO' : 'ARGUMENTO')),
          spatial_locus: g.spatial_locus || 'CENTRO',
          status: g.status || 'VALIDATED'
        };
      });

      // Resolver solapamientos o reordenamientos SOV dentro de cada proposición/segmento
      // para que TODAS las glosas se ejecuten secuencialmente en orden gramatical LSEC sin omisiones.
      this.resolveOverlappingGlossIntervals(projectData.glosses, projectData.segments);
    } else {
      projectData.glosses = [];
    }

    this.state.project = projectData;
    this.state.playback.duration = projectData.media_info.duration_seconds || 48.850;
    this.state.playback.currentTime = 0.0;
    this.state.unsavedChangesCount = 0;
    this.setSaveStatus('saved');

    // Seleccionar primer segmento automáticamente
    if (projectData.segments.length > 0) {
      this.selectItem('segment', projectData.segments[0].id, projectData.segments[0]);
    }

    // Determinar avance en el flujo secuencial según los datos cargados
    const hasSegments = projectData.segments && projectData.segments.length > 0;
    const hasGlosses = projectData.glosses && projectData.glosses.length > 0;
    const isValidated = projectData.execution_status === 'VALIDATED';

    this.state.workspace.videoLoaded = true;
    this.state.workspace.transcriptionReady = hasSegments;
    this.state.workspace.translationReady = hasGlosses;
    this.state.workspace.translationConfirmed = isValidated;

    if (isValidated) {
      this.state.workspace.workflowStep = 'completed';
    } else if (hasGlosses) {
      this.state.workspace.workflowStep = 'step2_traducir';
      this.state.workspace.stage = 'traducir';
    } else if (hasSegments) {
      this.state.workspace.workflowStep = 'step1_preparar';
      this.state.workspace.stage = 'preparar';
    } else {
      this.state.workspace.workflowStep = 'no_video';
    }

    this.emit('projectLoaded', this.state.project);
    this.emit('workflowChanged', this.state.workspace);
    this.emit('stageChanged', this.state.workspace.stage);
    this.emit('stateChanged', this.state);
    console.log(`Proyecto '${projectData.media_info.filename}' cargado exitosamente. Paso de flujo: ${this.state.workspace.workflowStep}`);
  }

  loadProjectFromJSON(jsonText, filename = 'Proyecto_LSEC.json') {
    try {
      const parsed = typeof jsonText === 'string' ? JSON.parse(jsonText) : jsonText;
      let projectData = parsed.project || parsed;
      this.loadProject(projectData, filename);
      return { success: true };
    } catch (err) {
      console.error('Error parseando JSON:', err);
      return { success: false, error: err.message };
    }
  }

  /**
   * Garantiza que las glosas dentro de cada proposición/segmento tengan intervalos
   * secuenciales no solapados en orden gramatical LSEC, evitando que glosas inferidas
   * de proposición completa (ej. PERSONA, FUTURO) o reordenadas por SOV oculten a
   * otras glosas (ej. SER, CON, ESO, DECIR, QUERER).
   */
  resolveOverlappingGlossIntervals(glosses, segments = []) {
    if (!Array.isArray(glosses) || glosses.length <= 1) return;

    const segMap = new Map();
    if (Array.isArray(segments)) {
      for (const s of segments) {
        if (s && s.id) segMap.set(s.id, s);
      }
    }

    // Agrupar glosas contiguas por proposition_id / origin_proposition_id / segmento
    const groups = [];
    let currentGroup = null;

    for (const g of glosses) {
      let groupKey = g.proposition_id || g.origin_proposition_id || g.segment_id || null;
      if (!groupKey && Array.isArray(segments) && segments.length > 0) {
        const matchedSeg = segments.find(s =>
          g.start_seconds >= (s.start_seconds - 0.15) && g.end_seconds <= (s.end_seconds + 0.15)
        );
        if (matchedSeg) groupKey = matchedSeg.id;
      }
      groupKey = groupKey || '__default__';

      if (!currentGroup || currentGroup.key !== groupKey) {
        currentGroup = { key: groupKey, items: [] };
        groups.push(currentGroup);
      }
      currentGroup.items.push(g);
    }

    let prevGroupEnd = 0.0;
    for (let gIdx = 0; gIdx < groups.length; gIdx++) {
      const grp = groups[gIdx];
      const items = grp.items;
      if (items.length === 0) continue;

      const seg = segMap.get(grp.key);
      let winStart = Math.min(...items.map(it => Number(it.start_seconds) || 0));
      let winEnd = Math.max(...items.map(it => Number(it.end_seconds) || (winStart + 0.45)));
      if (seg) {
        if (typeof seg.start_seconds === 'number') winStart = Math.min(winStart, seg.start_seconds);
        if (typeof seg.end_seconds === 'number') winEnd = Math.max(winEnd, seg.end_seconds);
      }
      if (winStart < prevGroupEnd) {
        winStart = prevGroupEnd;
      }

      // Comprobar si existe solapamiento o desorden temporal entre glosas consecutivas
      let hasOverlapOrOutOfOrder = (items[0].start_seconds < prevGroupEnd - 0.005);
      for (let i = 0; i < items.length - 1; i++) {
        if (items[i + 1].start_seconds < items[i].end_seconds - 0.005 ||
            items[i + 1].start_seconds < items[i].start_seconds) {
          hasOverlapOrOutOfOrder = true;
          break;
        }
      }
      if (!hasOverlapOrOutOfOrder) {
        prevGroupEnd = Math.max(prevGroupEnd, ...items.map(it => Number(it.end_seconds) || 0));
        continue;
      }

      // Aprovechar hasta 0.30s de pausa posterior si no invade el siguiente grupo
      if (gIdx + 1 < groups.length && groups[gIdx + 1].items.length > 0) {
        const nextItems = groups[gIdx + 1].items;
        const nextSeg = segMap.get(groups[gIdx + 1].key);
        let nextStart = Math.min(...nextItems.map(it => Number(it.start_seconds) || Infinity));
        if (nextSeg && typeof nextSeg.start_seconds === 'number') {
          nextStart = Math.min(nextStart, nextSeg.start_seconds);
        }
        if (Number.isFinite(nextStart) && nextStart > winEnd + 0.04) {
          winEnd = Math.min(nextStart - 0.02, winEnd + 0.30);
        }
      }

      const totalWindow = Math.max(items.length * 0.22, winEnd - winStart);
      const weights = items.map(it => {
        const rawDur = (typeof it.duration_ms === 'number' && it.duration_ms > 0)
          ? (it.duration_ms / 1000)
          : Math.max(0.35, (Number(it.end_seconds) || 0.45) - (Number(it.start_seconds) || 0));
        return Math.max(0.35, Math.min(0.95, rawDur));
      });
      const weightSum = weights.reduce((acc, w) => acc + w, 0) || items.length;

      let cursor = winStart;
      for (let i = 0; i < items.length; i++) {
        const slotDur = totalWindow * (weights[i] / weightSum);
        const st = Number(cursor.toFixed(3));
        const et = Number((i === items.length - 1 ? Math.max(st + 0.18, winStart + totalWindow) : (cursor + slotDur)).toFixed(3));
        items[i].start_seconds = st;
        items[i].end_seconds = et;
        items[i].start_time = st;
        items[i].end_time = et;
        items[i].start = st;
        items[i].end = et;
        cursor += slotDur;
      }
      prevGroupEnd = items[items.length - 1].end_seconds;
    }
  }

  // ============================================================
  // Control de las 3 Etapas y Flujo Secuencial
  // ============================================================

  canAccessStage(stage) {
    if (!this.state.workspace.videoLoaded) return false;
    if (stage === 'preparar') {
      return this.state.workspace.transcriptionReady;
    }
    if (stage === 'traducir') {
      return this.state.workspace.translationReady;
    }
    if (stage === 'revisar') {
      return this.state.workspace.translationReady && (this.state.workspace.workflowStep === 'step3_revisar' || this.state.workspace.workflowStep === 'completed');
    }
    return false;
  }

  canExport() {
    return this.state.workspace.translationConfirmed || this.state.workspace.workflowStep === 'completed';
  }

  getStageBlockReason(stage) {
    if (!this.state.workspace.videoLoaded) {
      return 'Debes cargar un video primero (Paso 1).';
    }
    if (stage === 'traducir' && !this.state.workspace.translationReady) {
      return 'Debes revisar los subtítulos, corregir palabras y presionar "Traducir a Glosas LSEC" para continuar.';
    }
    if (stage === 'revisar' && this.state.workspace.workflowStep === 'step2_traducir') {
      return 'Debes confirmar la traducción a glosas antes de pasar a la revisión final.';
    }
    return 'Completa el paso previo del flujo secuencial.';
  }

  setStage(stage) {
    if (!['preparar', 'traducir', 'revisar'].includes(stage)) return false;
    
    if (!this.canAccessStage(stage)) {
      const reason = this.getStageBlockReason(stage);
      console.warn(`Etapa '${stage}' bloqueada: ${reason}`);
      this.emit('stageBlocked', { 
        attemptedStage: stage, 
        currentStep: this.state.workspace.workflowStep,
        reason: reason
      });
      return false;
    }

    this.state.workspace.stage = stage;
    this.emit('stageChanged', stage);
    this.emit('stateChanged', this.state);
    return true;
  }

  markVideoLoaded(filename = null) {
    this.state.workspace.videoLoaded = true;
    this.emit('workflowChanged', this.state.workspace);
    this.emit('stateChanged', this.state);
  }

  markTranscriptionReady() {
    this.state.workspace.videoLoaded = true;
    this.state.workspace.transcriptionReady = true;
    this.state.workspace.translationReady = false;
    this.state.workspace.translationConfirmed = false;
    this.state.workspace.workflowStep = 'step1_preparar';
    this.state.workspace.stage = 'preparar';
    this.emit('workflowChanged', this.state.workspace);
    this.emit('stageChanged', 'preparar');
    this.emit('stateChanged', this.state);
  }

  markTranslationReady() {
    this.state.workspace.videoLoaded = true;
    this.state.workspace.transcriptionReady = true;
    this.state.workspace.translationReady = true;
    this.state.workspace.translationConfirmed = false;
    this.state.workspace.workflowStep = 'step2_traducir';
    this.state.workspace.stage = 'traducir';
    this.emit('workflowChanged', this.state.workspace);
    this.emit('stageChanged', 'traducir');
    this.emit('stateChanged', this.state);
  }

  markTranslationReviewStep() {
    if (!this.state.workspace.translationReady) return;
    this.state.workspace.workflowStep = 'step3_revisar';
    this.state.workspace.stage = 'revisar';
    this.emit('workflowChanged', this.state.workspace);
    this.emit('stageChanged', 'revisar');
    this.emit('stateChanged', this.state);
  }

  markTranslationConfirmed() {
    if (!this.state.workspace.translationReady) return;
    this.state.workspace.translationConfirmed = true;
    this.state.workspace.workflowStep = 'completed';
    if (this.state.project) {
      this.state.project.execution_status = 'VALIDATED';
    }
    this.emit('workflowChanged', this.state.workspace);
    this.emit('stateChanged', this.state);
  }

  setWorkflowStep(step) {
    if (step === 'step1_preparar') {
      this.markTranscriptionReady();
    } else if (step === 'step2_traducir') {
      this.markTranslationReady();
    } else if (step === 'step3_revisar') {
      this.state.workspace.videoLoaded = true;
      this.state.workspace.transcriptionReady = true;
      this.state.workspace.translationReady = true;
      this.markTranslationReviewStep();
    } else if (step === 'completed') {
      this.state.workspace.videoLoaded = true;
      this.state.workspace.transcriptionReady = true;
      this.state.workspace.translationReady = true;
      this.markTranslationConfirmed();
    } else {
      this.state.workspace.workflowStep = step;
      this.emit('workflowChanged', this.state.workspace);
      this.emit('stateChanged', this.state);
    }
  }

  invalidateTranslation() {
    // Si se modifica texto en etapa 1 luego de haber traducido a glosas
    if (this.state.workspace.translationReady) {
      this.state.workspace.translationReady = false;
      this.state.workspace.translationConfirmed = false;
      this.state.workspace.workflowStep = 'step1_preparar';
      this.state.workspace.stage = 'preparar';
      this.emit('workflowChanged', this.state.workspace);
      this.emit('stageChanged', 'preparar');
      this.emit('stateChanged', this.state);
    }
  }

  toggleBottomDock() {
    this.setBottomDockCollapsed(!this.state.workspace.bottomDockCollapsed);
  }

  setBottomDockCollapsed(collapsed) {
    this.state.workspace.bottomDockCollapsed = !!collapsed;
    this.emit('bottomDockToggled', { collapsed: this.state.workspace.bottomDockCollapsed });
    this.emit('workspaceChanged', this.state.workspace);
    this.emit('stateChanged', this.state);
  }

  // ============================================================
  // Inspector Contextual: Selección Dinámica de Elementos
  // ============================================================

  selectItem(type, id, data = null) {
    let resolvedData = data;
    if (!resolvedData && this.state.project) {
      if (type === 'segment') {
        resolvedData = (this.state.project.segments || []).find(s => s.id === id);
      } else if (type === 'gloss') {
        resolvedData = (this.state.project.glosses || []).find(g => g.id === id);
      } else if (type === 'sentence') {
        const units = this.getSentenceUnits();
        resolvedData = units.find(u => u.id === id) || data;
      } else if (type === 'issue') {
        resolvedData = (this.state.project.unresolved_items || []).find(it => it.id === id) || data;
      }
    }

    this.state.playback.selectedItem = {
      type: type, // 'segment' | 'gloss' | 'sentence' | 'locus' | 'non_manual' | 'issue'
      id: id,
      data: resolvedData
    };

    if (type === 'segment' && resolvedData) {
      this.state.playback.activeSegmentId = id;
    } else if (type === 'sentence' && resolvedData) {
      if (resolvedData.segments && resolvedData.segments.length > 0) {
        this.state.playback.activeSegmentId = resolvedData.segments[0].id;
      }
    }

    this.emit('selectionChanged', this.state.playback.selectedItem);
  }

  getSentenceUnits() {
    if (!this.state.project) return [];
    if (typeof SentenceGroupingEngine !== 'undefined') {
      return SentenceGroupingEngine.buildSentenceUnits(this.state.project);
    }
    return [];
  }

  clearSelection() {
    this.state.playback.selectedItem = null;
    this.emit('selectionChanged', null);
  }

  // ============================================================
  // Control de Reproducción Audiovisual y Sincronización
  // ============================================================

  setCurrentTime(time, source = 'unknown') {
    const clamped = Math.max(0, Math.min(this.state.playback.duration || 1000, time));
    this.state.playback.currentTime = clamped;

    // Sincronizar bucle si está activo
    if (this.state.playback.isLooping && this.state.playback.outPoint !== null) {
      if (clamped >= this.state.playback.outPoint) {
        this.state.playback.currentTime = this.state.playback.inPoint !== null ? this.state.playback.inPoint : 0;
      }
    }

    this.updateActiveElements(this.state.playback.currentTime);
    this.emit('timeupdate', { time: this.state.playback.currentTime, source });
  }

  setIsPlaying(isPlaying) {
    this.state.playback.isPlaying = isPlaying;
    this.emit('playbackStateChanged', isPlaying);
  }

  togglePlayPause() {
    this.setIsPlaying(!this.state.playback.isPlaying);
  }

  setInPoint(time = null) {
    this.state.playback.inPoint = time !== null ? time : this.state.playback.currentTime;
    this.emit('inOutPointsChanged', { in: this.state.playback.inPoint, out: this.state.playback.outPoint });
  }

  setOutPoint(time = null) {
    this.state.playback.outPoint = time !== null ? time : this.state.playback.currentTime;
    this.emit('inOutPointsChanged', { in: this.state.playback.inPoint, out: this.state.playback.outPoint });
  }

  stepFrame(delta) {
    const target = (this.state.playback.currentTime || 0) + delta;
    this.setCurrentTime(target, 'step_frame');
  }

  toggleLoop() {
    this.state.playback.isLooping = !this.state.playback.isLooping;
    this.emit('loopStateChanged', this.state.playback.isLooping);
  }

  setPlaybackRate(rate) {
    this.state.playback.playbackRate = rate;
    this.emit('playbackRateChanged', rate);
  }

  setVolume(volume) {
    this.state.playback.volume = Math.max(0, Math.min(1, volume));
    this.state.playback.isMuted = this.state.playback.volume === 0;
    this.emit('volumeChanged', { volume: this.state.playback.volume, isMuted: this.state.playback.isMuted });
  }

  toggleMute() {
    this.state.playback.isMuted = !this.state.playback.isMuted;
    this.emit('volumeChanged', { volume: this.state.playback.volume, isMuted: this.state.playback.isMuted });
  }

  updateActiveElements(time) {
    if (!this.state.project) return;

    // 1. Palabra activa
    let activeWordIdx = -1;
    const words = this.state.project.transcription?.word_timestamps || [];
    for (let i = 0; i < words.length; i++) {
      const st = words[i].start !== undefined ? words[i].start : words[i].start_time;
      const et = words[i].end !== undefined ? words[i].end : words[i].end_time;
      if (time >= st && time <= et) {
        activeWordIdx = i;
        break;
      }
    }
    if (activeWordIdx !== this.state.playback.activeWordIndex) {
      this.state.playback.activeWordIndex = activeWordIdx;
      this.emit('activeWordChanged', { index: activeWordIdx });
    }

    // 2. Segmento activo
    const segments = this.state.project.segments || [];
    const activeSeg = segments.find(s => time >= s.start_seconds && time <= s.end_seconds) || null;
    const activeSegId = activeSeg ? activeSeg.id : null;
    if (activeSegId !== this.state.playback.activeSegmentId) {
      this.state.playback.activeSegmentId = activeSegId;
      this.emit('activeSegmentChanged', { id: activeSegId, segment: activeSeg });
    }

    // 3. Glosa activa
    const glosses = this.state.project.glosses || [];
    const activeGloss = glosses.find(g => time >= g.start_seconds && time <= g.end_seconds) || null;
    const activeGlossId = activeGloss ? activeGloss.id : null;
    if (activeGlossId !== this.state.playback.activeGlossId) {
      this.state.playback.activeGlossId = activeGlossId;
      this.emit('activeGlossChanged', { id: activeGlossId, gloss: activeGloss });
    }
  }

  // ============================================================
  // Edición y Mutación de Segmentos (Validación Humana)
  // ============================================================

  updateSegment(segId, changes) {
    if (!this.state.project || !this.state.project.segments) return;
    this.pushHistory();

    const segIndex = this.state.project.segments.findIndex(s => s.id === segId);
    if (segIndex !== -1) {
      const current = this.state.project.segments[segIndex];
      const updated = {
        ...current,
        ...changes,
        human_reviewed: true,
        validated_by: changes.validated_by || this.state.currentUser.name,
        validated_at: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };

      if (changes.status) {
        updated.status_label = this.getStatusLabel(changes.status);
      }

      // Si se editó el texto del segmento, sincronizar texto y regenerar marcas de palabra (words)
      const hasTextChange = changes.normalized_text !== undefined || changes.original_text !== undefined || changes.text !== undefined;
      if (hasTextChange) {
        const textValue = (changes.normalized_text !== undefined ? changes.normalized_text : (changes.original_text !== undefined ? changes.original_text : changes.text || '')).trim();
        updated.normalized_text = textValue;
        updated.original_text = textValue;
        updated.text = textValue;

        const tokens = textValue.split(/\s+/).filter(Boolean);
        const st = updated.start_seconds !== undefined ? updated.start_seconds : (updated.start_time || 0);
        const et = updated.end_seconds !== undefined ? updated.end_seconds : (updated.end_time || (st + 2.5));
        const segDuration = Math.max(0.2, et - st);
        const wordDur = segDuration / Math.max(1, tokens.length);

        const newWords = tokens.map((w, idx) => ({
          word: w,
          start: parseFloat((st + (idx * wordDur)).toFixed(3)),
          end: parseFloat((st + ((idx + 1) * wordDur)).toFixed(3)),
          confidence: 0.99
        }));
        updated.words = newWords;

        // Sincronizar en project.transcription.word_timestamps para mantener coherencia en todo el proyecto
        if (this.state.project.transcription && Array.isArray(this.state.project.transcription.word_timestamps)) {
          const wts = this.state.project.transcription.word_timestamps;
          const filtered = wts.filter(w => {
            const wst = w.start !== undefined ? w.start : w.start_time;
            const wet = w.end !== undefined ? w.end : w.end_time;
            return !(wst >= st - 0.05 && wet <= et + 0.05);
          });
          this.state.project.transcription.word_timestamps = [...filtered, ...newWords].sort((a, b) => (a.start || 0) - (b.start || 0));
        }
      }

      this.state.project.segments[segIndex] = updated;

      // Mantener sincronizado project.subtitles si existe
      if (this.state.project.subtitles && Array.isArray(this.state.project.subtitles)) {
        const subIndex = this.state.project.subtitles.findIndex(s => s.id === segId);
        if (subIndex !== -1) {
          this.state.project.subtitles[subIndex] = updated;
        } else {
          this.state.project.subtitles = this.state.project.segments;
        }
      }

      this.markUnsavedChange();
      this.emit('segmentUpdated', updated);
      this.emit('segmentsChanged', this.state.project.segments);
      this.emit('subtitlesChanged', this.state.project.segments);

      // Si el segmento está seleccionado en el inspector, refrescarlo
      if (this.state.playback.selectedItem?.id === segId) {
        this.selectItem('segment', segId, updated);
      }
    }
  }

  validateSegment(segId) {
    this.updateSegment(segId, {
      status: 'VALIDATED',
      secondary_cause: null,
      human_reviewed: true,
      validated_by: this.state.currentUser.name
    });
  }

  splitSegment(segId, splitTime) {
    if (!this.state.project || !this.state.project.segments) return;
    this.pushHistory();

    const segIndex = this.state.project.segments.findIndex(s => s.id === segId);
    if (segIndex === -1) return;

    const orig = this.state.project.segments[segIndex];
    if (splitTime <= orig.start_seconds || splitTime >= orig.end_seconds) return;

    const words = orig.original_text.split(' ');
    const midWord = Math.floor(words.length / 2);
    const text1 = words.slice(0, midWord).join(' ') || orig.original_text;
    const text2 = words.slice(midWord).join(' ') || orig.original_text;

    const seg1 = {
      ...orig,
      end_seconds: splitTime,
      end_time: splitTime,
      duration: parseFloat((splitTime - orig.start_seconds).toFixed(3)),
      original_text: text1,
      normalized_text: text1,
      status: 'CORRECTED',
      secondary_cause: 'Segmentación',
      human_reviewed: true
    };

    const seg2 = {
      ...orig,
      id: `seg_${Date.now().toString().slice(-4)}`,
      index: orig.index + 1,
      start_seconds: splitTime,
      start_time: splitTime,
      duration: parseFloat((orig.end_seconds - splitTime).toFixed(3)),
      original_text: text2,
      normalized_text: text2,
      status: 'CORRECTED',
      secondary_cause: 'Segmentación',
      human_reviewed: true
    };

    this.state.project.segments.splice(segIndex, 1, seg1, seg2);
    this.state.project.segments.forEach((s, i) => s.index = i + 1);

    this.markUnsavedChange();
    this.emit('segmentsChanged', this.state.project.segments);
    this.selectItem('segment', seg1.id, seg1);
  }

  mergeSegmentWithNext(segId) {
    if (!this.state.project || !this.state.project.segments) return;
    const idx = this.state.project.segments.findIndex(s => s.id === segId);
    if (idx === -1 || idx >= this.state.project.segments.length - 1) return;

    this.pushHistory();
    const curr = this.state.project.segments[idx];
    const next = this.state.project.segments[idx + 1];

    const merged = {
      ...curr,
      end_seconds: next.end_seconds,
      end_time: next.end_seconds,
      duration: parseFloat((next.end_seconds - curr.start_seconds).toFixed(3)),
      original_text: `${curr.original_text} ${next.original_text}`,
      normalized_text: `${curr.normalized_text} ${next.normalized_text}`,
      gloss_sequence: [...(curr.gloss_sequence || []), ...(next.gloss_sequence || [])],
      status: 'CORRECTED',
      secondary_cause: 'Segmentación',
      human_reviewed: true
    };

    this.state.project.segments.splice(idx, 2, merged);
    this.state.project.segments.forEach((s, i) => s.index = i + 1);

    this.markUnsavedChange();
    this.emit('segmentsChanged', this.state.project.segments);
    this.selectItem('segment', merged.id, merged);
  }

  // ============================================================
  // Edición Visual de Glosas LSEC, Drag & Drop y Reordenamiento
  // ============================================================

  findSentence(sentenceId) {
    const units = this.getSentenceUnits();
    return units.find(u => u.id === sentenceId || u.index === sentenceId || String(u.index) === String(sentenceId)) || null;
  }

  syncSentenceToProject(sentence) {
    if (!this.state.project) return;
    if (!this.state.project.glosses) this.state.project.glosses = [];

    const sentenceGlosses = sentence.glosses || [];
    const sentenceGlossNames = sentenceGlosses.map(g => g.gloss || g.lemma || '');

    // Actualizar los segmentos asociados a esta frase
    (sentence.segments || []).forEach(seg => {
      seg.gloss_sequence = [...sentenceGlossNames];
      seg.manually_edited = true;
      seg.human_reviewed = true;
    });

    // Actualizar o insertar cada glosa en project.glosses
    sentenceGlosses.forEach(g => {
      const pIdx = this.state.project.glosses.findIndex(pg => pg.id === g.id);
      if (pIdx !== -1) {
        this.state.project.glosses[pIdx] = { ...this.state.project.glosses[pIdx], ...g };
      } else {
        this.state.project.glosses.push({ ...g });
      }
    });

    // Ordenar project.glosses cronológicamente
    this.state.project.glosses.sort((a, b) => {
      const aStart = a.start_seconds !== undefined ? a.start_seconds : (a.start || 0);
      const bStart = b.start_seconds !== undefined ? b.start_seconds : (b.start || 0);
      return aStart - bStart;
    });
  }

  recalculateSentenceTiming(sentence) {
    if (!sentence || !sentence.glosses || sentence.glosses.length === 0) return;
    const st = sentence.start_seconds !== undefined ? sentence.start_seconds : 0;
    const et = sentence.end_seconds !== undefined ? sentence.end_seconds : (st + 2.0);
    const totalSpan = Math.max(0.3, et - st);
    const n = sentence.glosses.length;

    // Calcular suma de duraciones preferidas (o 0.45s por defecto)
    const totalPrefDur = sentence.glosses.reduce((acc, g) => {
      const d = g.duration !== undefined ? g.duration : ((g.end_seconds || 0) - (g.start_seconds || 0));
      return acc + (d > 0.05 ? d : 0.45);
    }, 0);

    let curr = st;
    sentence.glosses.forEach((g, idx) => {
      g.order = idx;
      const prefD = g.duration !== undefined ? g.duration : ((g.end_seconds || 0) - (g.start_seconds || 0));
      const dur = totalPrefDur > 0 ? ((prefD > 0.05 ? prefD : 0.45) / totalPrefDur) * totalSpan : (totalSpan / n);
      const cleanDur = Math.max(0.1, parseFloat(dur.toFixed(3)));

      g.start_seconds = parseFloat(curr.toFixed(3));
      g.start = g.start_seconds;
      g.start_time = g.start_seconds;
      g.end_seconds = parseFloat((curr + cleanDur).toFixed(3));
      g.end = g.end_seconds;
      g.end_time = g.end_seconds;
      g.duration = cleanDur;

      curr = g.end_seconds;
    });

    // Ajustar el final de la última glosa para encajar exactamente en el intervalo
    if (sentence.glosses.length > 0) {
      const last = sentence.glosses[sentence.glosses.length - 1];
      last.end_seconds = et;
      last.end = et;
      last.end_time = et;
      last.duration = parseFloat((last.end_seconds - last.start_seconds).toFixed(3));
    }
  }

  validateSentenceWithInvariants(sentence) {
    if (typeof StructuralValidator !== 'undefined') {
      const violations = StructuralValidator.validateSentence(sentence, this.state.project);
      if (violations.length > 0) {
        sentence.status = 'REVIEW_REQUIRED';
        sentence.status_label = 'Requiere Revisión';
        sentence.has_review = true;
        sentence.review_reasons = violations.map(v => `[${v.code}] ${v.message}`);
        (sentence.segments || []).forEach(s => {
          s.status = 'REVIEW_REQUIRED';
          s.status_label = 'Revisar';
          s.requires_native_review = true;
        });
        if (this.state.project) this.state.project.execution_status = 'REVIEW_REQUIRED';
        return violations;
      } else {
        sentence.status = 'CORRECTED';
        sentence.status_label = 'Corregido';
        sentence.has_review = false;
        sentence.review_reasons = [];
        (sentence.segments || []).forEach(s => {
          if (s.status !== 'VALIDATED') {
            s.status = 'CORRECTED';
            s.status_label = 'Corregido';
          }
        });
        return [];
      }
    }
    return [];
  }

  reorderGlossInSentence(sentenceId, glossId, newIndex) {
    if (!this.state.project) return false;
    const sentence = this.findSentence(sentenceId);
    if (!sentence || !sentence.glosses || sentence.glosses.length === 0) return false;

    const oldIndex = sentence.glosses.findIndex(g => g.id === glossId);
    if (oldIndex === -1) return false;
    const targetIdx = Math.max(0, Math.min(sentence.glosses.length - 1, newIndex));
    if (oldIndex === targetIdx) return true;

    this.pushHistory();

    const [movedGloss] = sentence.glosses.splice(oldIndex, 1);
    sentence.glosses.splice(targetIdx, 0, movedGloss);

    // Marcar alineación como pendiente tras reordenar
    movedGloss.alignment_status = 'PENDING';
    movedGloss.alignment_type = 'MANUAL_EDIT';

    // Recalcular orden y tiempos
    this.recalculateSentenceTiming(sentence);

    // Validar invariantes
    this.validateSentenceWithInvariants(sentence);

    // Sincronizar hacia el proyecto
    this.syncSentenceToProject(sentence);
    this.markUnsavedChange();

    // Actualizar selección si aplica
    if (this.state.playback.selectedItem?.id === glossId) {
      this.state.playback.selectedItem.data = movedGloss;
      this.emit('selectionChanged', this.state.playback.selectedItem);
    } else if (this.state.playback.selectedItem?.id === sentence.id) {
      this.state.playback.selectedItem.data = sentence;
      this.emit('selectionChanged', this.state.playback.selectedItem);
    }

    this.emit('glossesChanged', this.state.project.glosses);
    this.emit('segmentsChanged', this.state.project.segments);
    this.emit('sentenceUpdated', sentence);
    this.emit('projectUpdated', this.state.project);
    return true;
  }

  moveGlossBetweenSentences(sourceSentenceId, targetSentenceId, glossId, targetIndex = -1) {
    if (!this.state.project || sourceSentenceId === targetSentenceId) {
      if (sourceSentenceId === targetSentenceId) {
        return this.reorderGlossInSentence(sourceSentenceId, glossId, targetIndex);
      }
      return false;
    }

    const source = this.findSentence(sourceSentenceId);
    const target = this.findSentence(targetSentenceId);
    if (!source || !target || !source.glosses) return false;

    const glossIdx = source.glosses.findIndex(g => g.id === glossId);
    if (glossIdx === -1) return false;

    this.pushHistory();

    const [movedGloss] = source.glosses.splice(glossIdx, 1);

    // Conservar ID estrictamente y actualizar asociación de proposición
    const targetPropId = (target.proposition_ids && target.proposition_ids.length > 0)
      ? target.proposition_ids[0]
      : (target.segments?.[0]?.proposition_id || 'p1');

    movedGloss.prop_id = targetPropId;
    movedGloss.alignment_status = 'PENDING';
    movedGloss.alignment_type = 'MANUAL_EDIT';
    movedGloss.notes = (movedGloss.notes ? movedGloss.notes + '; ' : '') + `Movida manualmente de Frase ${source.index} a Frase ${target.index}`;

    if (!target.glosses) target.glosses = [];
    const insertPos = targetIndex >= 0 ? Math.min(targetIndex, target.glosses.length) : target.glosses.length;
    target.glosses.splice(insertPos, 0, movedGloss);

    // Recalcular tiempos en ambas frases
    this.recalculateSentenceTiming(source);
    this.recalculateSentenceTiming(target);

    // Marcar ambas frases y sus segmentos como REVIEW_REQUIRED
    source.status = 'REVIEW_REQUIRED';
    source.status_label = 'Requiere Revisión';
    source.has_review = true;
    source.review_reasons = [...(source.review_reasons || []), `Glosa '${movedGloss.gloss}' transferida hacia Frase ${target.index}. Requiere revisión.`];
    (source.segments || []).forEach(s => {
      s.status = 'REVIEW_REQUIRED';
      s.status_label = 'Revisar';
      s.requires_native_review = true;
    });

    target.status = 'REVIEW_REQUIRED';
    target.status_label = 'Requiere Revisión';
    target.has_review = true;
    target.review_reasons = [...(target.review_reasons || []), `Glosa '${movedGloss.gloss}' recibida desde Frase ${source.index}. Requiere revisión.`];
    (target.segments || []).forEach(s => {
      s.status = 'REVIEW_REQUIRED';
      s.status_label = 'Revisar';
      s.requires_native_review = true;
    });

    // Validar estructuralmente ambas frases
    this.validateSentenceWithInvariants(source);
    this.validateSentenceWithInvariants(target);

    // Sincronizar ambas frases al proyecto
    this.syncSentenceToProject(source);
    this.syncSentenceToProject(target);
    this.markUnsavedChange();

    // Actualizar selección
    if (this.state.playback.selectedItem?.id === glossId) {
      this.state.playback.selectedItem.data = movedGloss;
      this.emit('selectionChanged', this.state.playback.selectedItem);
    }

    this.emit('glossesChanged', this.state.project.glosses);
    this.emit('segmentsChanged', this.state.project.segments);
    this.emit('sentenceUpdated', source);
    this.emit('sentenceUpdated', target);
    this.emit('projectUpdated', this.state.project);
    return true;
  }

  addGlossToSentence(sentenceId, glossData = {}, targetIndex = -1) {
    if (!this.state.project) return null;
    const sentence = this.findSentence(sentenceId);
    if (!sentence) return null;

    this.pushHistory();

    const uniqueId = `g_${Date.now().toString().slice(-6)}_${Math.random().toString(36).substr(2, 3)}`;
    const rawName = (glossData.gloss || glossData.lemma || 'NUEVA_GLOSA').toUpperCase().trim();

    const newGloss = {
      id: uniqueId,
      gloss: rawName,
      lemma: (glossData.lemma || rawName).toUpperCase().trim(),
      gloss_type: glossData.gloss_type || 'SEÑA',
      spatial_locus: glossData.spatial_locus || 'CENTRO',
      non_manual_features: glossData.non_manual_features || ['Atención neutra'],
      syntactic_role: glossData.syntactic_role || 'ARGUMENTO',
      alignment_type: 'MANUAL_EDIT',
      alignment_status: 'PENDING',
      status: 'DRAFT',
      type_badge: 'seña',
      color: 'yellow',
      confidence: 0.90,
      notes: 'Glosa añadida manualmente',
      prop_id: sentence.proposition_ids?.[0] || 'p1',
      is_fingerspelling: (rawName.includes('-') && rawName.split('-').filter(Boolean).every(p => p.trim().length === 1)) || (glossData.gloss_type === 'DACTILOLOGÍA'),
      is_pause: glossData.is_pause || false,
      duration: glossData.duration || 0.45
    };

    if (!sentence.glosses) sentence.glosses = [];
    const insertPos = targetIndex >= 0 ? Math.min(targetIndex, sentence.glosses.length) : sentence.glosses.length;
    sentence.glosses.splice(insertPos, 0, newGloss);

    this.recalculateSentenceTiming(sentence);
    this.validateSentenceWithInvariants(sentence);
    this.syncSentenceToProject(sentence);
    this.markUnsavedChange();

    this.emit('glossesChanged', this.state.project.glosses);
    this.emit('segmentsChanged', this.state.project.segments);
    this.emit('sentenceUpdated', sentence);
    this.emit('projectUpdated', this.state.project);

    this.selectItem('gloss', newGloss.id, newGloss);
    return newGloss;
  }

  deleteGloss(sentenceId, glossId) {
    if (!this.state.project) return false;
    let sentence = this.findSentence(sentenceId);
    if (!sentence) {
      // Buscar la frase que contiene esta glosa
      const units = this.getSentenceUnits();
      sentence = units.find(u => (u.glosses || []).some(g => g.id === glossId));
    }
    if (!sentence || !sentence.glosses) return false;

    const idx = sentence.glosses.findIndex(g => g.id === glossId);
    if (idx === -1) return false;

    this.pushHistory();

    sentence.glosses.splice(idx, 1);

    // Eliminar también de project.glosses
    if (this.state.project.glosses) {
      this.state.project.glosses = this.state.project.glosses.filter(g => g.id !== glossId);
    }

    this.recalculateSentenceTiming(sentence);
    this.validateSentenceWithInvariants(sentence);
    this.syncSentenceToProject(sentence);
    this.markUnsavedChange();

    if (this.state.playback.selectedItem?.id === glossId) {
      this.clearSelection();
    }

    this.emit('glossesChanged', this.state.project.glosses);
    this.emit('segmentsChanged', this.state.project.segments);
    this.emit('sentenceUpdated', sentence);
    this.emit('projectUpdated', this.state.project);
    return true;
  }

  duplicateGloss(sentenceId, glossId) {
    if (!this.state.project) return null;
    let sentence = this.findSentence(sentenceId);
    if (!sentence) {
      const units = this.getSentenceUnits();
      sentence = units.find(u => (u.glosses || []).some(g => g.id === glossId));
    }
    if (!sentence || !sentence.glosses) return null;

    const idx = sentence.glosses.findIndex(g => g.id === glossId);
    if (idx === -1) return null;

    this.pushHistory();

    const orig = sentence.glosses[idx];
    const dup = JSON.parse(JSON.stringify(orig));
    dup.id = `g_${orig.id}_dup_${Date.now().toString().slice(-4)}`;
    dup.alignment_status = 'PENDING';
    dup.alignment_type = 'MANUAL_EDIT';
    dup.status = 'DRAFT';
    dup.notes = (dup.notes ? dup.notes + '; ' : '') + 'Duplicado manualmente';

    sentence.glosses.splice(idx + 1, 0, dup);

    this.recalculateSentenceTiming(sentence);
    this.validateSentenceWithInvariants(sentence);
    this.syncSentenceToProject(sentence);
    this.markUnsavedChange();

    this.emit('glossesChanged', this.state.project.glosses);
    this.emit('segmentsChanged', this.state.project.segments);
    this.emit('sentenceUpdated', sentence);
    this.emit('projectUpdated', this.state.project);

    this.selectItem('gloss', dup.id, dup);
    return dup;
  }

  updateGloss(glossId, changes) {
    if (!this.state.project) return null;
    const safeChanges = { ...changes };
    delete safeChanges.id; // Conservar estrictamente el ID de la glosa

    const units = this.getSentenceUnits();
    let parentSentence = null;
    let targetGloss = null;

    for (const u of units) {
      const g = (u.glosses || []).find(it => it.id === glossId);
      if (g) {
        parentSentence = u;
        targetGloss = g;
        break;
      }
    }

    if (!targetGloss) {
      targetGloss = (this.state.project.glosses || []).find(it => it.id === glossId);
    }
    if (!targetGloss) return null;

    this.pushHistory();

    // Si cambió el lema o texto, marcar alineación como pendiente
    if (safeChanges.gloss && safeChanges.gloss !== targetGloss.gloss) {
      safeChanges.alignment_status = 'PENDING';
      safeChanges.alignment_type = 'MANUAL_EDIT';
      if (!safeChanges.lemma) safeChanges.lemma = safeChanges.gloss;
    }

    Object.assign(targetGloss, safeChanges);

    if (parentSentence) {
      if (safeChanges.duration !== undefined || safeChanges.start_seconds !== undefined) {
        this.recalculateSentenceTiming(parentSentence);
      }
      this.validateSentenceWithInvariants(parentSentence);
      this.syncSentenceToProject(parentSentence);
    } else {
      const pIdx = (this.state.project.glosses || []).findIndex(it => it.id === glossId);
      if (pIdx !== -1) {
        this.state.project.glosses[pIdx] = { ...this.state.project.glosses[pIdx], ...safeChanges };
      }
    }

    this.markUnsavedChange();

    if (this.state.playback.selectedItem?.id === glossId) {
      this.state.playback.selectedItem.data = targetGloss;
      this.emit('selectionChanged', this.state.playback.selectedItem);
    }

    this.emit('glossesChanged', this.state.project.glosses);
    this.emit('segmentsChanged', this.state.project.segments);
    if (parentSentence) this.emit('sentenceUpdated', parentSentence);
    this.emit('projectUpdated', this.state.project);
    return targetGloss;
  }

  updateGlossTiming(glossId, { duration, start_seconds, end_seconds }) {
    const changes = {};
    if (duration !== undefined && duration > 0) changes.duration = parseFloat(duration.toFixed(3));
    if (start_seconds !== undefined) changes.start_seconds = parseFloat(start_seconds.toFixed(3));
    if (end_seconds !== undefined) changes.end_seconds = parseFloat(end_seconds.toFixed(3));
    return this.updateGloss(glossId, changes);
  }

  insertPause(sentenceId, targetIndex = -1, durationSeconds = 0.5) {
    const dur = Math.max(0.1, parseFloat(durationSeconds) || 0.5);
    return this.addGlossToSentence(sentenceId, {
      gloss: '[PAUSA]',
      lemma: '[PAUSA]',
      gloss_type: 'PAUSA',
      is_pause: true,
      duration: dur,
      spatial_locus: 'CENTRO',
      non_manual_features: ['Pausa transicional'],
      notes: `Pausa lingüística (${dur}s)`
    }, targetIndex);
  }

  updateGlossNonManual(glossId, features) {
    const arr = Array.isArray(features) ? features : [features];
    return this.updateGloss(glossId, { non_manual_features: arr });
  }

  updateGlossSpatialLocus(glossId, locus) {
    return this.updateGloss(glossId, { spatial_locus: locus || 'CENTRO' });
  }

  // ============================================================
  // Capas Avanzadas y Filtros
  // ============================================================

  toggleAdvancedLayers() {
    this.state.workspace.showAdvancedLayers = !this.state.workspace.showAdvancedLayers;
    this.emit('advancedLayersToggled', this.state.workspace.showAdvancedLayers);
  }

  setFilter(key, value) {
    this.state.filters[key] = value;
    this.emit('filtersChanged', this.state.filters);
  }

  clearFilters() {
    this.state.filters = { textQuery: '', statusFilter: 'ALL', quickFilter: 'ALL' };
    this.emit('filtersChanged', this.state.filters);
  }

  // ============================================================
  // Historial de Deshacer / Rehacer (Undo / Redo)
  // ============================================================

  pushHistory() {
    if (this.state.project) {
      this.undoStack.push(JSON.stringify(this.state.project));
      if (this.undoStack.length > 25) this.undoStack.shift();
      this.redoStack = [];
      this.emit('historyChanged', { canUndo: true, canRedo: false });
    }
  }

  undo() {
    if (this.undoStack.length > 0) {
      const prev = this.undoStack.pop();
      this.redoStack.push(JSON.stringify(this.state.project));
      this.state.project = JSON.parse(prev);

      if (this.state.playback.selectedItem?.type === 'segment') {
        const seg = (this.state.project?.segments || []).find(s => s.id === this.state.playback.selectedItem.id);
        if (seg) {
          this.state.playback.selectedItem.data = seg;
          this.emit('selectionChanged', this.state.playback.selectedItem);
        }
      } else if (this.state.playback.selectedItem?.type === 'gloss') {
        const gl = (this.state.project?.glosses || []).find(g => g.id === this.state.playback.selectedItem.id);
        if (gl) {
          this.state.playback.selectedItem.data = gl;
          this.emit('selectionChanged', this.state.playback.selectedItem);
        }
      } else if (this.state.playback.selectedItem?.type === 'sentence') {
        const u = this.findSentence(this.state.playback.selectedItem.id);
        if (u) {
          this.state.playback.selectedItem.data = u;
          this.emit('selectionChanged', this.state.playback.selectedItem);
        }
      }

      this.emit('projectUpdated', this.state.project);
      this.emit('segmentsChanged', this.state.project.segments);
      this.emit('glossesChanged', this.state.project.glosses);
      this.emit('subtitleStyleChanged', this.state.overlays.subtitleStyle);
      this.emit('historyChanged', { canUndo: this.undoStack.length > 0, canRedo: true });
    }
  }

  redo() {
    if (this.redoStack.length > 0) {
      const next = this.redoStack.pop();
      this.undoStack.push(JSON.stringify(this.state.project));
      this.state.project = JSON.parse(next);

      if (this.state.playback.selectedItem?.type === 'segment') {
        const seg = (this.state.project?.segments || []).find(s => s.id === this.state.playback.selectedItem.id);
        if (seg) {
          this.state.playback.selectedItem.data = seg;
          this.emit('selectionChanged', this.state.playback.selectedItem);
        }
      } else if (this.state.playback.selectedItem?.type === 'gloss') {
        const gl = (this.state.project?.glosses || []).find(g => g.id === this.state.playback.selectedItem.id);
        if (gl) {
          this.state.playback.selectedItem.data = gl;
          this.emit('selectionChanged', this.state.playback.selectedItem);
        }
      } else if (this.state.playback.selectedItem?.type === 'sentence') {
        const u = this.findSentence(this.state.playback.selectedItem.id);
        if (u) {
          this.state.playback.selectedItem.data = u;
          this.emit('selectionChanged', this.state.playback.selectedItem);
        }
      }

      this.emit('projectUpdated', this.state.project);
      this.emit('segmentsChanged', this.state.project.segments);
      this.emit('glossesChanged', this.state.project.glosses);
      this.emit('subtitleStyleChanged', this.state.overlays.subtitleStyle);
      this.emit('historyChanged', { canUndo: true, canRedo: this.redoStack.length > 0 });
    }
  }

  // ============================================================
  // Persistencia y Preferencias
  // ============================================================

  markUnsavedChange() {
    this.state.unsavedChangesCount++;
    this.setSaveStatus('unsaved');
  }

  setSaveStatus(status) {
    this.state.saveStatus = status;
    this.emit('saveStatusChanged', status);
  }

  saveToLocalStorage() {
    if (!this.state.project) return;
    try {
      localStorage.setItem('lsec_studio_project', JSON.stringify(this.state.project));
      this.state.unsavedChangesCount = 0;
      this.setSaveStatus('saved');
      console.log('Cambios guardados exitosamente.');
    } catch (err) {
      console.error('Error guardando en localStorage:', err);
    }
  }

  setDuration(duration) {
    this.state.playback.duration = duration;
    this.emit('durationChanged', duration);
  }

  setOverlayPreference(key, value) {
    if (this.state.overlays) {
      this.state.overlays[key] = value;
      this.emit('overlayPrefChanged', { key, value });
    }
  }

  setSubtitleStyle(changes) {
    if (this.state.overlays) {
      this.state.overlays.subtitleStyle = {
        ...this.state.overlays.subtitleStyle,
        ...changes
      };
      this.emit('subtitleStyleChanged', this.state.overlays.subtitleStyle);
    }
  }

  updateSegmentSubtitleStyle(segId, changes, pushToHistory = true) {
    if (!this.state.project || !this.state.project.segments) return;
    const seg = this.state.project.segments.find(s => s.id === segId);
    if (!seg) return;

    if (pushToHistory) {
      this.pushHistory();
    }

    seg.subtitle_style = {
      ...(seg.subtitle_style || {}),
      ...changes
    };

    this.markUnsavedChange();

    if (this.state.playback.selectedItem?.id === segId) {
      this.state.playback.selectedItem.data = seg;
      this.emit('selectionChanged', this.state.playback.selectedItem);
    }

    this.emit('segmentSubtitleStyleChanged', { segId, style: seg.subtitle_style, segment: seg });
    this.emit('segmentUpdated', seg);
    this.emit('stateChanged', this.state);
  }

  resetSegmentSubtitleStyle(segId) {
    if (!this.state.project || !this.state.project.segments) return;
    const seg = this.state.project.segments.find(s => s.id === segId);
    if (!seg) return;

    this.pushHistory();
    seg.subtitle_style = null;
    this.markUnsavedChange();

    if (this.state.playback.selectedItem?.id === segId) {
      this.state.playback.selectedItem.data = seg;
      this.emit('selectionChanged', this.state.playback.selectedItem);
    }

    this.emit('segmentSubtitleStyleChanged', { segId, style: null, segment: seg });
    this.emit('segmentUpdated', seg);
    this.emit('stateChanged', this.state);
  }

  copySegmentSubtitleStyle(segId) {
    if (!this.state.project || !this.state.project.segments) return null;
    const seg = this.state.project.segments.find(s => s.id === segId);
    if (!seg) return null;

    const effective = (typeof SubtitleEngine !== 'undefined')
      ? SubtitleEngine.resolveEffectiveStyle(seg, this.state.overlays.subtitleStyle)
      : { ...this.state.overlays.subtitleStyle, ...(seg.subtitle_style || {}) };

    this.copiedSubtitleStyle = JSON.parse(JSON.stringify(effective));
    this.emit('subtitleStyleCopied', { segId, style: this.copiedSubtitleStyle });
    return this.copiedSubtitleStyle;
  }

  pasteSegmentSubtitleStyle(segId) {
    if (!this.copiedSubtitleStyle) return false;
    this.updateSegmentSubtitleStyle(segId, this.copiedSubtitleStyle, true);
    return true;
  }

  applySubtitleStyleToAllSegments(segId) {
    if (!this.state.project || !this.state.project.segments) return;
    const seg = this.state.project.segments.find(s => s.id === segId);
    const styleToApply = seg?.subtitle_style
      ? JSON.parse(JSON.stringify(seg.subtitle_style))
      : (this.copiedSubtitleStyle ? JSON.parse(JSON.stringify(this.copiedSubtitleStyle)) : null);

    this.pushHistory();
    this.state.project.segments.forEach(s => {
      s.subtitle_style = styleToApply ? JSON.parse(JSON.stringify(styleToApply)) : null;
    });

    this.markUnsavedChange();
    this.emit('segmentsChanged', this.state.project.segments);
    if (this.state.playback.selectedItem?.type === 'segment') {
      const current = this.state.project.segments.find(s => s.id === this.state.playback.selectedItem.id);
      if (current) {
        this.state.playback.selectedItem.data = current;
        this.emit('selectionChanged', this.state.playback.selectedItem);
      }
    }
    this.emit('subtitleStyleChanged', this.state.overlays.subtitleStyle);
  }

  setTheme(theme) {
    const normalizedTheme = theme === 'high_contrast' ? 'high-contrast' : theme;
    this.state.workspace.theme = normalizedTheme;
    document.documentElement.setAttribute('data-theme', normalizedTheme);
    try {
      localStorage.setItem('lsec_studio_theme', normalizedTheme);
    } catch (e) {}
    this.emit('themeChanged', normalizedTheme);
  }

  setFontSizeScale(scale) {
    this.state.workspace.fontSizeScale = scale;
    document.documentElement.setAttribute('data-font-scale', scale);
    this.emit('fontScaleChanged', scale);
  }

  resetToDefaultProject() {
    if (typeof DEMO_PROJECT_DATA !== 'undefined') {
      const demoCopy = JSON.parse(JSON.stringify(DEMO_PROJECT_DATA));
      this.loadProject(demoCopy, 'Video UPEC Prueba.mp4');
    }
  }

  resolveAudioReview(segId, finalWord, comment) {
    const seg = (this.state.project?.segments || []).find(s => s.id === segId);
    if (seg) {
      const comments = [...(seg.comments || [])];
      if (comment) comments.push(comment);
      this.updateSegment(segId, {
        normalized_text: seg.normalized_text.replace(seg.words?.[0]?.word || '', finalWord),
        status: 'CORRECTED',
        secondary_cause: null,
        comments: comments
      });
    }
  }

  resolveNativeReview(segId, action, glossList, comment) {
    const seg = (this.state.project?.segments || []).find(s => s.id === segId);
    if (seg) {
      const comments = [...(seg.comments || [])];
      if (comment) comments.push(comment);
      const changes = {
        status: action === 'approved' ? 'VALIDATED' : 'CORRECTED',
        secondary_cause: null,
        comments: comments
      };
      if (glossList && glossList.length > 0) {
        changes.gloss_sequence = glossList;
      }
      this.updateSegment(segId, changes);
    }
  }

  loadPreferencesFromStorage() {
    try {
      const rawTheme = localStorage.getItem('lsec_studio_theme') || 'dark';
      const savedTheme = rawTheme === 'high_contrast' ? 'high-contrast' : rawTheme;
      this.state.workspace.theme = savedTheme;
      document.documentElement.setAttribute('data-theme', savedTheme);
    } catch (e) {}
  }

  // ============================================================
  // Lenguaje Natural y Mapeos
  // ============================================================

  getStatusLabel(status) {
    const map = {
      'DRAFT': 'Borrador',
      'REVIEW_REQUIRED': 'Revisar',
      'CORRECTED': 'Corregido',
      'VALIDATED': 'Validado'
    };
    return map[status] || status;
  }

  explainConfidence(score, type = 'audio') {
    const pct = Math.round(score * 100);
    if (pct >= 90) return `${pct}% — Habla acústica clara y sin solapamiento`;
    if (pct >= 75) return `${pct}% — Claridad moderada con posible ruido leve`;
    return `${pct}% — Baja confianza acústica, requiere verificación humana`;
  }
}

// Instancia global única
const appState = new LSECStateStore();
if (typeof window !== 'undefined') {
  window.appState = appState;
}
