/**
 * LSEC Studio 2.1.1 — Historial Undo/Redo, Persistencia, Estilos de Subtítulos y Preferencias
 *
 * Submódulo de estado extraído de state.js para cumplir SRP (< 800 líneas).
 */

const LSECStatePersistenceStyles = {
  // ============================================================
  // Capas Avanzadas y Filtros
  // ============================================================

  toggleAdvancedLayers() {
    this.state.workspace.showAdvancedLayers = !this.state.workspace.showAdvancedLayers;
    this.emit('advancedLayersToggled', this.state.workspace.showAdvancedLayers);
  },

  setFilter(key, value) {
    this.state.filters[key] = value;
    this.emit('filtersChanged', this.state.filters);
  },

  clearFilters() {
    this.state.filters = { textQuery: '', statusFilter: 'ALL', quickFilter: 'ALL' };
    this.emit('filtersChanged', this.state.filters);
  },

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
  },

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
  },

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
  },

  // ============================================================
  // Persistencia y Preferencias
  // ============================================================

  markUnsavedChange() {
    this.state.unsavedChangesCount++;
    this.setSaveStatus('unsaved');
  },

  setSaveStatus(status) {
    this.state.saveStatus = status;
    this.emit('saveStatusChanged', status);
  },

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
  },

  setDuration(duration) {
    this.state.playback.duration = duration;
    this.emit('durationChanged', duration);
  },

  setOverlayPreference(key, value) {
    if (this.state.overlays) {
      this.state.overlays[key] = value;
      this.emit('overlayPrefChanged', { key, value });
    }
  },

  setSubtitleStyle(changes) {
    if (this.state.overlays) {
      this.state.overlays.subtitleStyle = {
        ...this.state.overlays.subtitleStyle,
        ...changes
      };
      this.emit('subtitleStyleChanged', this.state.overlays.subtitleStyle);
    }
  },

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
  },

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
  },

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
  },

  pasteSegmentSubtitleStyle(segId) {
    if (!this.copiedSubtitleStyle) return false;
    this.updateSegmentSubtitleStyle(segId, this.copiedSubtitleStyle, true);
    return true;
  },

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
  },

  setTheme(theme) {
    const normalizedTheme = theme === 'high_contrast' ? 'high-contrast' : theme;
    this.state.workspace.theme = normalizedTheme;
    if (typeof document !== 'undefined' && document.documentElement) {
      document.documentElement.setAttribute('data-theme', normalizedTheme);
    }
    try {
      localStorage.setItem('lsec_studio_theme', normalizedTheme);
    } catch (e) {}
    this.emit('themeChanged', normalizedTheme);
  },

  setFontSizeScale(scale) {
    this.state.workspace.fontSizeScale = scale;
    if (typeof document !== 'undefined' && document.documentElement) {
      document.documentElement.setAttribute('data-font-scale', scale);
    }
    this.emit('fontScaleChanged', scale);
  },

  resetToDefaultProject() {
    if (typeof DEMO_PROJECT_DATA !== 'undefined') {
      const demoCopy = JSON.parse(JSON.stringify(DEMO_PROJECT_DATA));
      this.loadProject(demoCopy, 'Video UPEC Prueba.mp4');
    }
  },

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
  },

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
  },

  loadPreferencesFromStorage() {
    try {
      const rawTheme = localStorage.getItem('lsec_studio_theme') || 'dark';
      const savedTheme = rawTheme === 'high_contrast' ? 'high-contrast' : rawTheme;
      this.state.workspace.theme = savedTheme;
      if (typeof document !== 'undefined' && document.documentElement) {
        document.documentElement.setAttribute('data-theme', savedTheme);
      }
    } catch (e) {}
  },

  getStatusLabel(status) {
    const map = {
      'DRAFT': 'Borrador',
      'REVIEW_REQUIRED': 'Revisar',
      'CORRECTED': 'Corregido',
      'VALIDATED': 'Validado'
    };
    return map[status] || status;
  },

  explainConfidence(score, type = 'audio') {
    const pct = Math.round(score * 100);
    if (pct >= 90) return `${pct}% — Habla acústica clara y sin solapamiento`;
    if (pct >= 75) return `${pct}% — Claridad moderada con posible ruido leve`;
    return `${pct}% — Baja confianza acústica, requiere verificación humana`;
  }
};

if (typeof window !== 'undefined') {
  window.LSECStatePersistenceStyles = LSECStatePersistenceStyles;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { LSECStatePersistenceStyles };
}
