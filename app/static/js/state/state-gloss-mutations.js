/**
 * LSEC Studio 2.1.1 — Mutaciones de Segmentos, Edición Visual de Glosas y Reordenamiento
 *
 * Submódulo de estado extraído de state.js para cumplir SRP (< 800 líneas).
 */

const LSECStateGlossMutations = {
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

      if (this.state.playback.selectedItem?.id === segId) {
        this.selectItem('segment', segId, updated);
      }
    }
  },

  validateSegment(segId) {
    this.updateSegment(segId, {
      status: 'VALIDATED',
      secondary_cause: null,
      human_reviewed: true,
      validated_by: this.state.currentUser.name
    });
  },

  addSegment(startTime = 0, endTime = 3.0, text = 'Nueva oración educativa en español.') {
    if (!this.state.project) {
      this.loadProject({
        version: '2.1.1',
        media_info: {
          filename: 'Proyecto_Manual_LSEC.mp4',
          duration_seconds: Math.max(10.0, Number(endTime) || 3.0),
          fps: 30.0,
          resolution: '1920x1080'
        },
        segments: [],
        glosses: [],
        subtitles: []
      });
    }
    this.pushHistory();

    const segments = this.state.project.segments || [];
    const idx = segments.length + 1;
    const st = Number(startTime) || 0;
    const et = Math.max(st + 0.5, Number(endTime) || (st + 3.0));
    const segId = `seg_${String(idx).padStart(2, '0')}_${Date.now().toString().slice(-3)}`;

    const newSeg = {
      id: segId,
      index: idx,
      start_seconds: st,
      end_seconds: et,
      start_time: st,
      end_time: et,
      duration: parseFloat((et - st).toFixed(3)),
      original_text: text,
      normalized_text: text,
      raw_text: text,
      status: 'DRAFT',
      status_label: this.getStatusLabel ? this.getStatusLabel('DRAFT') : 'Borrador',
      confidence: 0.99,
      human_reviewed: true,
      words: [],
      glosses: [],
      gloss_sequence: []
    };

    segments.push(newSeg);
    this.state.project.segments = segments;
    this.state.project.subtitles = segments;
    if (et > (this.state.playback.duration || 0)) {
      this.setDuration(et);
    }

    this.markUnsavedChange();
    this.emit('segmentUpdated', newSeg);
    this.emit('segmentsChanged', this.state.project.segments);
    this.emit('subtitlesChanged', this.state.project.segments);
    return newSeg;
  },

  deleteSegment(segId) {
    if (!this.state.project || !Array.isArray(this.state.project.segments)) return false;
    const idx = this.state.project.segments.findIndex(s => s.id === segId);
    if (idx === -1) return false;

    this.pushHistory();
    const [removed] = this.state.project.segments.splice(idx, 1);
    this.state.project.segments.forEach((s, i) => {
      s.index = i + 1;
    });
    this.state.project.subtitles = this.state.project.segments;

    if (Array.isArray(this.state.project.glosses) && removed) {
      this.state.project.glosses = this.state.project.glosses.filter(
        g => g.segment_id !== segId && g.proposition_id !== segId && g.origin_proposition_id !== segId
      );
    }

    this.markUnsavedChange();
    this.emit('segmentsChanged', this.state.project.segments);
    this.emit('glossesChanged', this.state.project.glosses || []);
    this.emit('subtitlesChanged', this.state.project.segments);
    return true;
  },

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
  },

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
  },

  // ============================================================
  // Edición Visual de Glosas LSEC, Drag & Drop y Reordenamiento
  // ============================================================

  findSentence(sentenceId) {
    const units = this.getSentenceUnits();
    return units.find(u => u.id === sentenceId || u.index === sentenceId || String(u.index) === String(sentenceId)) || null;
  },

  syncSentenceToProject(sentence) {
    if (!this.state.project) return;
    if (!this.state.project.glosses) this.state.project.glosses = [];

    const sentenceGlosses = sentence.glosses || [];
    const sentenceGlossNames = sentenceGlosses.map(g => g.gloss || g.lemma || '');

    (sentence.segments || []).forEach(seg => {
      seg.gloss_sequence = [...sentenceGlossNames];
      seg.manually_edited = true;
      seg.human_reviewed = true;
    });

    sentenceGlosses.forEach(g => {
      const pIdx = this.state.project.glosses.findIndex(pg => pg.id === g.id);
      if (pIdx !== -1) {
        this.state.project.glosses[pIdx] = { ...this.state.project.glosses[pIdx], ...g };
      } else {
        this.state.project.glosses.push({ ...g });
      }
    });

    this.state.project.glosses.sort((a, b) => {
      const aStart = a.start_seconds !== undefined ? a.start_seconds : (a.start || 0);
      const bStart = b.start_seconds !== undefined ? b.start_seconds : (b.start || 0);
      return aStart - bStart;
    });
  },

  recalculateSentenceTiming(sentence) {
    if (!sentence || !sentence.glosses || sentence.glosses.length === 0) return;
    const st = sentence.start_seconds !== undefined ? sentence.start_seconds : 0;
    const et = sentence.end_seconds !== undefined ? sentence.end_seconds : (st + 2.0);
    const totalSpan = Math.max(0.3, et - st);
    const n = sentence.glosses.length;

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

    if (sentence.glosses.length > 0) {
      const last = sentence.glosses[sentence.glosses.length - 1];
      last.end_seconds = et;
      last.end = et;
      last.end_time = et;
      last.duration = parseFloat((last.end_seconds - last.start_seconds).toFixed(3));
    }
  },

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
  },

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

    movedGloss.alignment_status = 'PENDING';
    movedGloss.alignment_type = 'MANUAL_EDIT';

    this.recalculateSentenceTiming(sentence);
    this.validateSentenceWithInvariants(sentence);
    this.syncSentenceToProject(sentence);
    this.markUnsavedChange();

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
  },

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

    this.recalculateSentenceTiming(source);
    this.recalculateSentenceTiming(target);

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

    this.validateSentenceWithInvariants(source);
    this.validateSentenceWithInvariants(target);

    this.syncSentenceToProject(source);
    this.syncSentenceToProject(target);
    this.markUnsavedChange();

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
  },

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
  },

  deleteGloss(sentenceId, glossId) {
    if (!this.state.project) return false;
    let sentence = this.findSentence(sentenceId);
    if (!sentence) {
      const units = this.getSentenceUnits();
      sentence = units.find(u => (u.glosses || []).some(g => g.id === glossId));
    }
    if (!sentence || !sentence.glosses) return false;

    const idx = sentence.glosses.findIndex(g => g.id === glossId);
    if (idx === -1) return false;

    this.pushHistory();

    sentence.glosses.splice(idx, 1);

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
  },

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
  },

  updateGloss(glossId, changes) {
    if (!this.state.project) return null;
    const safeChanges = { ...changes };
    delete safeChanges.id;

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
  },

  updateGlossTiming(glossId, { duration, start_seconds, end_seconds }) {
    const changes = {};
    if (duration !== undefined && duration > 0) changes.duration = parseFloat(duration.toFixed(3));
    if (start_seconds !== undefined) changes.start_seconds = parseFloat(start_seconds.toFixed(3));
    if (end_seconds !== undefined) changes.end_seconds = parseFloat(end_seconds.toFixed(3));
    return this.updateGloss(glossId, changes);
  },

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
  },

  updateGlossNonManual(glossId, features) {
    const arr = Array.isArray(features) ? features : [features];
    return this.updateGloss(glossId, { non_manual_features: arr });
  },

  updateGlossSpatialLocus(glossId, locus) {
    return this.updateGloss(glossId, { spatial_locus: locus || 'CENTRO' });
  }
};

if (typeof window !== 'undefined') {
  window.LSECStateGlossMutations = LSECStateGlossMutations;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { LSECStateGlossMutations };
}
