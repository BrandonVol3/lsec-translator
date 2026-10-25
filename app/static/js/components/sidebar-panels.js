/**
 * LSEC Studio — Controladores de Paneles Auxiliares y Host del Avatar
 * Refactorizado bajo modularidad estricta (< 800 líneas) y sin paneles manuales CNM/Loci/MLOps.
 */

class ContextualInspectorController {
  constructor(containerId = 'contextual-inspector-zone') {
    this.container = document.getElementById(containerId);
    this.viewSubtitles = document.getElementById('view-side-subtitles');
    this.viewAvatar = document.getElementById('view-side-avatar');
    this.activeTab = 'subtitles';
    this.init();
  }

  init() {
    if (typeof appState === 'undefined') return;
    appState.subscribe('selectionChanged', (sel) => {
      this.currentSelection = sel;
    });
  }

  switchTab(tabName) {
    this.activeTab = tabName;
  }

  escapeHTML(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}

class AvatarPanelHostStub {
  constructor(containerId = 'view-side-avatar') {
    this.container = document.getElementById(containerId);
  }
}

if (typeof window !== 'undefined') {
  window.SidebarPanelsController = ContextualInspectorController;
  window.ContextualInspectorController = ContextualInspectorController;
  if (!window.AvatarPanelController) {
    window.AvatarPanelController = AvatarPanelHostStub;
  }
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ContextualInspectorController, AvatarPanelController: AvatarPanelHostStub };
}
