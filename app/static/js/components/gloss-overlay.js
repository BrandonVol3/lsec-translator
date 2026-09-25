/**
 * LSEC Studio 2.1.1 — Componente GlossOverlay (Avatar Ilustrado 3D y Glosas LSEC)
 * 
 * Muestra un recuadro Picture-in-Picture en la esquina inferior derecha del video
 * con la ilustración de referencia del avatar intérprete de señas y proyecta dentro
 * las glosas LSEC una por una en tiempo real.
 */

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

    this.updateVisibility(appState.state.overlays.glossesEnabled);
    this.render(0);
  }

  buildDOM() {
    if (!this.container) return;
    this.container.innerHTML = `
      <div class="avatar-pip-card">
        <div class="avatar-pip-header">
          <div class="avatar-pip-title">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" style="color:var(--action-primary);"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"/></svg>
            <span>Avatar 3D (LSEC)</span>
          </div>
          <span class="avatar-pip-tag">Ilustración</span>
        </div>

        <div class="avatar-pip-image-wrap">
          <img src="/static/assets/avatar_ilustracion.png" class="avatar-pip-illustration-img" id="avatar-pip-img-el" alt="Avatar LSEC Intérprete Ilustración">
          <div class="avatar-pip-watermark-note">Espacio para Avatar 3D</div>
          <div class="avatar-pip-gradient-overlay"></div>
          <div class="avatar-pip-gloss-container" id="avatar-pip-gloss-host">
            <div class="avatar-pip-gloss-idle">
              <span class="avatar-pip-idle-dot"></span>
              <span>LSEC</span>
            </div>
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
    this.container.style.display = enabled ? 'flex' : 'none';
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

    // 1. Encontrar la glosa activa una por una para este instante exacto
    let activeGloss = allGlosses.find(g => {
      const st = g.start_seconds !== undefined ? g.start_seconds : (g.start_time !== undefined ? g.start_time : (g.start !== undefined ? g.start : 0));
      const et = g.end_seconds !== undefined ? g.end_seconds : (g.end_time !== undefined ? g.end_time : (g.end !== undefined ? g.end : 0));
      return time >= st && time <= et;
    });

    // Si no coincide exactamente con un intervalo pero hay un segmento activo, buscar la glosa por interpolación
    if (!activeGloss && project && project.segments) {
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
    const currentKey = activeGloss ? (activeGloss.id || activeGloss.gloss || activeGloss.lemma) : (project ? 'idle' : 'empty');
    if (this.lastRenderedKey === currentKey) return;
    this.lastRenderedKey = currentKey;

    if (activeGloss) {
      const glossName = (activeGloss.gloss || activeGloss.lemma || '').toUpperCase();
      const isFingerspelling = activeGloss.is_fingerspelling || glossName.includes('-') || (activeGloss.gloss_type === 'DACTILOLOGÍA');
      const isParaphrase = activeGloss.is_paraphrase || (activeGloss.type_badge === 'paráfrasis');
      
      let typeLabel = activeGloss.gloss_type || 'SEÑA LÉXICA';
      if (isFingerspelling) typeLabel = 'DACTILOLOGÍA';
      if (isParaphrase) typeLabel = 'PARÁFRASIS LSEC';

      this.glossHost.innerHTML = `
        <div class="avatar-pip-gloss-badge ${isFingerspelling ? 'fs' : ''}">
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
