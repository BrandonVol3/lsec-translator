/**
 * LSEC Studio 2.1.1 — Gestor de Estado Central Reactivo (State Store — Fachada Principal)
 * 
 * Centraliza el flujo de las 3 etapas (Preparar, Traducir, Revisar),
 * los 4 estados de segmentos (Borrador, Revisar, Corregido, Validado),
 * la selección del Inspector Contextual y el historial de revisiones humanas.
 *
 * Submódulos en app/static/js/state/:
 * - state-project-hydration.js
 * - state-gloss-mutations.js
 * - state-persistence-styles.js
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
          bgOpacity: 0.78,
          outlineWidth: 0,
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
          margin: 8,
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
        theme: 'light', // 'light' | 'high-contrast' | 'dark'
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
    if (typeof this.loadPreferencesFromStorage === 'function') {
      this.loadPreferencesFromStorage();
    }
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

    projectData = this.normalizeLoadedProjectData(projectData, filename);

    this.state.project = projectData;
    this.state.playback.duration = projectData.media_info?.duration_seconds || 48.850;
    this.state.playback.currentTime = 0.0;
    this.state.unsavedChangesCount = 0;
    this.setSaveStatus('saved');

    if (projectData.segments && projectData.segments.length > 0) {
      this.selectItem('segment', projectData.segments[0].id, projectData.segments[0]);
    }

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
    console.log(`Proyecto '${projectData.media_info?.filename || 'Proyecto_LSEC'}' cargado exitosamente. Paso de flujo: ${this.state.workspace.workflowStep}`);
  }

  normalizeLoadedProjectData(projectData, filename = null) {
    if (!projectData) return projectData;

    if (!projectData.media_info) {
      projectData.media_info = {
        filename: filename || 'Video_LSEC.mp4',
        duration_seconds: 48.850,
        resolution: '1920x1080',
        fps: 30.0
      };
    }
    if (filename) projectData.media_info.filename = filename;
    if (!projectData.execution_status) projectData.execution_status = 'REVIEW_REQUIRED';

    if (projectData.segments) {
      projectData.segments = projectData.segments.map((s, idx) => {
        const start = s.start_seconds != null ? s.start_seconds : (s.start_time != null ? s.start_time : (s.start != null ? s.start : idx * 3.0));
        const end = s.end_seconds != null ? s.end_seconds : (s.end_time != null ? s.end_time : (s.end != null ? s.end : (idx + 1) * 3.0));

        let status = s.status || 'DRAFT';
        if (status === 'VALIDATED') status = 'VALIDATED';
        else if (status === 'CORRECTED') status = 'CORRECTED';
        else if (status === 'REVIEW_REQUIRED' || status === 'NATIVE_REVIEW' || status === 'AUDIO_REVIEW' || status === 'BLOCKED') status = 'REVIEW_REQUIRED';
        else status = 'DRAFT';

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
          status: status,
          status_label: this.getStatusLabel ? this.getStatusLabel(status) : status,
          secondary_cause: secondaryCause,
          confidence: s.confidence || 0.94,
          confidence_explanation: this.explainConfidence ? this.explainConfidence(s.confidence || 0.94, 'audio') : '',
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
      this.resolveOverlappingGlossIntervals(projectData.glosses, projectData.segments);
    } else {
      projectData.glosses = [];
    }
    return projectData;
  }

  resolveOverlappingGlossIntervals(glosses, segments = []) {
    if (!Array.isArray(glosses) || glosses.length <= 1) return;

    const segMap = new Map();
    if (Array.isArray(segments)) {
      for (const s of segments) {
        if (s && s.id) segMap.set(s.id, s);
      }
    }

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
      if (winStart < prevGroupEnd) winStart = prevGroupEnd;

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

  setSaveStatus(status) {
    this.state.saveStatus = status;
    this.emit('saveStatusChanged', status);
  }

  loadProjectFromJSON(jsonText, filename = 'Proyecto_LSEC.json') {
    try {
      const parsed = typeof jsonText === 'string' ? JSON.parse(jsonText) : jsonText;
      const projectData = parsed.project || parsed;
      this.loadProject(projectData, filename);
      return { success: true };
    } catch (err) {
      console.error('Error parseando JSON:', err);
      return { success: false, error: err.message };
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
      type: type,
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

    if (this.state.playback.isLooping && this.state.playback.outPoint !== null) {
      if (clamped >= this.state.playback.outPoint) {
        this.state.playback.currentTime = this.state.playback.inPoint !== null ? this.state.playback.inPoint : 0;
      }
    }

    this.updateActiveElements(this.state.playback.currentTime);
    this.emit('timeupdate', { time: this.state.playback.currentTime, source });
    this.emit('timeChanged', this.state.playback.currentTime);
  }

  confirmTranslationStage() {
    this.markTranslationConfirmed();
    this.markTranslationReviewStep();
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

    const segments = this.state.project.segments || [];
    const activeSeg = segments.find(s => time >= s.start_seconds && time <= s.end_seconds) || null;
    const activeSegId = activeSeg ? activeSeg.id : null;
    if (activeSegId !== this.state.playback.activeSegmentId) {
      this.state.playback.activeSegmentId = activeSegId;
      this.emit('activeSegmentChanged', { id: activeSegId, segment: activeSeg });
    }

    const glosses = this.state.project.glosses || [];
    const activeGloss = glosses.find(g => time >= g.start_seconds && time <= g.end_seconds) || null;
    const activeGlossId = activeGloss ? activeGloss.id : null;
    if (activeGlossId !== this.state.playback.activeGlossId) {
      this.state.playback.activeGlossId = activeGlossId;
      this.emit('activeGlossChanged', { id: activeGlossId, gloss: activeGloss });
    }
  }
}

// Integrar submódulos de estado en el prototipo de LSECStateStore
if (typeof window !== 'undefined') {
  if (window.LSECStateProjectHydration) {
    Object.assign(LSECStateStore.prototype, window.LSECStateProjectHydration);
  }
  if (window.LSECStateGlossMutations) {
    Object.assign(LSECStateStore.prototype, window.LSECStateGlossMutations);
  }
  if (window.LSECStatePersistenceStyles) {
    Object.assign(LSECStateStore.prototype, window.LSECStatePersistenceStyles);
  }
} else if (typeof require === 'function') {
  try {
    const { LSECStateProjectHydration } = require('./state/state-project-hydration.js');
    const { LSECStateGlossMutations } = require('./state/state-gloss-mutations.js');
    const { LSECStatePersistenceStyles } = require('./state/state-persistence-styles.js');
    Object.assign(
      LSECStateStore.prototype,
      LSECStateProjectHydration,
      LSECStateGlossMutations,
      LSECStatePersistenceStyles
    );
  } catch (_) {}
}

// Instancia global única
const appState = new LSECStateStore();
if (typeof window !== 'undefined') {
  window.appState = appState;
  window.LSECStateStore = LSECStateStore;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { LSECStateStore, appState };
}
