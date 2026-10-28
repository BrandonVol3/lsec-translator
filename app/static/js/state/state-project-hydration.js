/**
 * LSEC Studio 2.1.1 — Hidratación de Proyecto y Resolución de Intervalos de Glosas
 *
 * Submódulo de estado extraído de state.js para cumplir SRP (< 800 líneas).
 */

const LSECStateProjectHydration = {
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
    if (filename) {
      projectData.media_info.filename = filename;
    }

    if (projectData.segments) {
      projectData.segments = projectData.segments.map((s, idx) => {
        const start = s.start_seconds != null ? s.start_seconds : (s.start_time != null ? s.start_time : (s.start != null ? s.start : idx * 3.0));
        const end = s.end_seconds != null ? s.end_seconds : (s.end_time != null ? s.end_time : (s.end != null ? s.end : (idx + 1) * 3.0));

        const status = s.status === 'CORRECTED' ? 'CORRECTED' : 'READY';
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
          confidence: s.confidence || 0.94,
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
  },

  /**
   * Garantiza que las glosas dentro de cada proposición/segmento tengan intervalos
   * secuenciales no solapados en orden gramatical LSEC, evitando que glosas inferidas
   * de proposición completa o reordenadas por SOV oculten a otras glosas.
   */
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
      if (winStart < prevGroupEnd) {
        winStart = prevGroupEnd;
      }

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
};

if (typeof window !== 'undefined') {
  window.LSECStateProjectHydration = LSECStateProjectHydration;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { LSECStateProjectHydration };
}
