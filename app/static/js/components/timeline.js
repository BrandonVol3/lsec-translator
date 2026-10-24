/**
 * LSEC Studio — Sincronizador Temporal en Segundo Plano (Sin Línea de Tiempo Multipista en UI)
 * Mantiene la sincronización automática por tiempo entre video, subtítulos, unidades de frase (`sentenceUnits`) y avatar.
 */

class MultiTrackTimelineController {
  constructor(containerId = 'timeline-view-wrap') {
    this.container = document.getElementById(containerId);
    this.sentenceUnits = [];
    this.init();
  }

  init() {
    if (typeof appState === 'undefined') return;
    this.refreshSentenceUnits();
    appState.subscribe('projectLoaded', () => this.refreshSentenceUnits());
    appState.subscribe('projectUpdated', () => this.refreshSentenceUnits());
    appState.subscribe('segmentsChanged', () => this.refreshSentenceUnits());
    appState.subscribe('glossesChanged', () => this.refreshSentenceUnits());
  }

  refreshSentenceUnits() {
    if (typeof appState === 'undefined' || !appState.state?.project) return;
    if (typeof SentenceGroupingEngine !== 'undefined') {
      this.sentenceUnits = SentenceGroupingEngine.buildSentenceUnits(appState.state.project);
    } else if (typeof appState.getSentenceUnits === 'function') {
      this.sentenceUnits = appState.getSentenceUnits();
    }
  }

  renderTrackSentencesES() {
    // Mantenido para compatibilidad de contrato con unidades de frase (timeline-sentence-item)
    return this.sentenceUnits;
  }

  renderTrackSentencesGlosses() {
    // Mantenido para compatibilidad de contrato con glosas por frase
    return this.sentenceUnits;
  }
}

if (typeof window !== 'undefined') {
  window.MultiTrackTimelineController = MultiTrackTimelineController;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { MultiTrackTimelineController };
}
