/**
 * LSEC Studio 2.1.1 — Componente GlossOverlay (Avatar Ilustrado 3D y Glosas LSEC)
 * 
 * Muestra un recuadro Picture-in-Picture en la esquina inferior derecha del video
 * con la ilustración de referencia del avatar intérprete de señas y proyecta dentro
 * las glosas LSEC una por una en tiempo real.
 */

/**
 * Devuelve la letra (displayChar) que el avatar está articulando en el instante 	imeSec dentro de una
 * palabra deletreada, usando clip.metadata.letterSegments y el mapeo tiempo-de-video -> tiempo-de-clip
 * del plan compilado. Retorna null si la entrada no es una palabra deletreada o aún no hay letra activa.
 */
function lsecFingerspellingLetterAt(entry, timeSec) {
  const segs = entry && entry.clip && entry.clip.metadata && entry.clip.metadata.letterSegments;
  if (!Array.isArray(segs) || segs.length === 0) return null;
  const st = Number(entry.startSec);
  const en = Number(entry.endSec);
  const cs = Number(entry.strokeStart);
  const ce = Number(entry.strokeEnd);
  if (![st, en, cs, ce].every(Number.isFinite) || en <= st) return null;
  if (timeSec < st - 1e-3 || timeSec > en + 1e-3) return null;
  const u = Math.min(1, Math.max(0, (timeSec - st) / (en - st)));
  const localSec = cs + u * (ce - cs);
  for (const seg of segs) {
    if (localSec >= seg.startSec - 1e-3 && localSec <= seg.endSec + 1e-3) return seg.displayChar || seg.grapheme || null;
  }
  let best = segs[0];
  for (const seg of segs) {
    if (Math.abs(localSec - seg.endSec) < Math.abs(localSec - best.endSec)) best = seg;
  }
  return best.displayChar || best.grapheme || null;
}
if (typeof window !== 'undefined') {
  window.lsecFingerspellingLetterAt = lsecFingerspellingLetterAt;
}

class GlossOverlayController {
  constructor(containerId = 'gloss-overlay-container') {
    this.container = document.getElementById(containerId);
    this.toggleBtn = document.getElementById('btn-toggle-glosses');
    this.glossHost = null;
    this.lastRenderedKey = null;

    this.init();
    this.subscribeState();
  }

  init() {
    this.buildDOM();

    if (this.toggleBtn) {
      this.toggleBtn.addEventListener('click', () => {
        const next = !appState.state.overlays.glossesEnabled;
        appState.setOverlayPreference('glossesEnabled', next);
      });
    }

    if (window.studioAvatarBridge) {
      window.studioAvatarBridge.dockToPip();
    }

    this.updateVisibility(appState.state.overlays.glossesEnabled);
    this.render(0);
  }

  buildDOM() {
    if (!this.container) return;
    this.container.innerHTML = `
      <div class="avatar-pip-card">
        <div class="avatar-pip-canvas-host" id="avatar-pip-canvas-host">
          <!-- Canvas 3D WebGL acoplado dinámicamente por studio-avatar-bridge.js -->
        </div>
        <div class="avatar-pip-gloss-container" id="avatar-pip-gloss-host">
          <div class="avatar-pip-gloss-idle">
            <span class="avatar-pip-idle-dot"></span>
            <span>LSEC</span>
          </div>
        </div>
      </div>
    `;

    this.glossHost = this.container.querySelector('#avatar-pip-gloss-host');

    const pipCard = this.container.querySelector('.avatar-pip-card');
    if (pipCard) {
      pipCard.style.cursor = 'pointer';
      pipCard.title = 'Abrir panel de control y previsualización de Avatar 3D';
      pipCard.addEventListener('click', () => {
        if (window.contextualInspector) {
          window.contextualInspector.switchTab('avatar');
        }
      });
    }
  }

  subscribeState() {
    appState.subscribe('timeupdate', ({ time }) => {
      this.render(time);
    });

    appState.subscribe('overlayPrefChanged', ({ key, value }) => {
      if (key === 'glossesEnabled') {
        this.updateVisibility(value);
      }
    });

    appState.subscribe('projectLoaded', () => {
      this.lastRenderedKey = null;
      this.render(appState.state.playback.currentTime || 0);
    });

    appState.subscribe('projectCleared', () => {
      this.lastRenderedKey = null;
      this.render(0);
    });
  }

  updateVisibility(enabled) {
    if (!this.container) return;
    const isHiddenBySidebar = this.container.dataset.hiddenBySidebar === 'true' ||
      (window.studioAvatarBridge && window.studioAvatarBridge.currentLocation === 'sidebar');
    this.container.style.display = (enabled && !isHiddenBySidebar) ? 'flex' : 'none';
    if (this.toggleBtn) {
      if (enabled) {
        this.toggleBtn.classList.add('active');
        this.toggleBtn.setAttribute('aria-pressed', 'true');
      } else {
        this.toggleBtn.classList.remove('active');
        this.toggleBtn.setAttribute('aria-pressed', 'false');
      }
    }
  }

  render(time) {
    if (!this.container || !this.glossHost) return;
    if (!appState.state.overlays.glossesEnabled) return;

    const project = appState.state.project;
    const allGlosses = (project && project.glosses) ? project.glosses : [];

    if (allGlosses.length > 1 && project && !project.__sequentialGlossesNormalized && appState.resolveOverlappingGlossIntervals) {
      appState.resolveOverlappingGlossIntervals(allGlosses, project.segments || []);
      project.__sequentialGlossesNormalized = true;
    }

    // 1. Encontrar la glosa activa (evaluando SequenceCompiler en `time` exacto para evitar lecturas desfasadas tras seek)
    const bridge = window.studioAvatarBridge;
    const hasCompiledPlan = Boolean(bridge && bridge.fluidMode && bridge.compiler?.compiled);
    const sampleResult = hasCompiledPlan
      ? ((bridge.lastSampleResult && Math.abs(bridge.lastSampleResult.timeSec - time) < 1e-3)
          ? bridge.lastSampleResult
          : bridge.compiler.sample(time))
      : null;
    const sampleEntry = sampleResult?.activeEntry || null;
    let activeGloss = (sampleEntry && sampleEntry.raw) ? sampleEntry.raw : null;

    if (!hasCompiledPlan && !activeGloss) {
      activeGloss = allGlosses.find(g => {
        const st = g.start_seconds !== undefined ? g.start_seconds : (g.start_time !== undefined ? g.start_time : (g.start !== undefined ? g.start : 0));
        const et = g.end_seconds !== undefined ? g.end_seconds : (g.end_time !== undefined ? g.end_time : (g.end !== undefined ? g.end : 0));
        return time >= st && time <= et;
      });
    }

    // Si no coincide exactamente con un intervalo pero hay un segmento activo (solo antes de compilar plan), buscar por interpolación
    if (!hasCompiledPlan && !activeGloss && project && project.segments) {
      const activeSeg = project.segments.find(s => {
        const st = s.start_time !== undefined ? s.start_time : (s.start_seconds || 0);
        const et = s.end_time !== undefined ? s.end_time : (s.end_seconds || 0);
        return time >= st && time <= et;
      });

      if (activeSeg && activeSeg.glosses && activeSeg.glosses.length > 0) {
        const sStart = activeSeg.start_time !== undefined ? activeSeg.start_time : (activeSeg.start_seconds || 0);
        const sEnd = activeSeg.end_time !== undefined ? activeSeg.end_time : (activeSeg.end_seconds || 0);
        const sDur = Math.max(0.2, sEnd - sStart);
        const progress = Math.min(0.99, Math.max(0, (time - sStart) / sDur));
        const idx = Math.floor(progress * activeSeg.glosses.length);
        activeGloss = activeSeg.glosses[idx] || activeSeg.glosses[0];
      }
    }

    // 2. Comprobar si la glosa cambió para no reescribir innecesariamente el DOM
    const activeLetter = (activeGloss && sampleEntry) ? lsecFingerspellingLetterAt(sampleEntry, time) : null;
    const currentKey = activeGloss ? ((activeGloss.id || activeGloss.gloss || activeGloss.lemma) + (activeLetter ? '|' + activeLetter : '')) : (project ? 'idle' : 'empty');
    if (this.lastRenderedKey === currentKey) return;
    this.lastRenderedKey = currentKey;

    if (activeGloss) {
      const glossName = (activeGloss.gloss || activeGloss.lemma || '').toUpperCase().trim();
      const isSingleLetterHyphenated = glossName.includes('-') && glossName.split('-').filter(Boolean).every(p => p.trim().length === 1);
      const isFingerspelling = Boolean(activeGloss.is_fingerspelling || isSingleLetterHyphenated || (activeGloss.gloss_type === 'DACTILOLOGÍA'));
      const isParaphrase = activeGloss.is_paraphrase || (activeGloss.type_badge === 'paráfrasis');
      
      let typeLabel = activeGloss.gloss_type || 'SEÑA LÉXICA';
      if (isFingerspelling) typeLabel = activeLetter ? `DELETREO LSEC · LETRA [ ${activeLetter} ]` : 'DELETREO LSEC';
      if (isParaphrase) typeLabel = 'PARÁFRASIS LSEC';

      this.glossHost.innerHTML = `
        <div class="avatar-pip-gloss-badge ${isFingerspelling ? 'fs' : ''}" data-gloss-name="${glossName}">
          <span class="avatar-pip-gloss-type">${typeLabel}</span>
          <span class="avatar-pip-gloss-text">${glossName}</span>
        </div>
      `;
    } else if (project) {
      this.glossHost.innerHTML = `
        <div class="avatar-pip-gloss-idle">
          <span class="avatar-pip-idle-dot"></span>
          <span>LSEC</span>
        </div>
      `;
    } else {
      this.glossHost.innerHTML = `
        <div class="avatar-pip-gloss-idle">
          <span>Esperando video</span>
        </div>
      `;
    }
  }
}

// Instancia exportada
if (typeof window !== 'undefined') {
  window.GlossOverlayController = GlossOverlayController;
}
