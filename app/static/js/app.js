/**
 * LSEC Studio 2.1.1 — Coordinador Principal de la Estación de Trabajo
 * 
 * Orquesta las 3 etapas (Preparar, Traducir, Revisar), los 4 paneles principales,
 * el Inspector Contextual, el Editor Central de Segmentos y los atajos de teclado globales.
 */

document.addEventListener('DOMContentLoaded', () => {
  console.log('Iniciando LSEC Studio 2.1.1 — Estación de Trabajo Lingüística...');

  // 1. Inicializar Controladores con aislamiento de errores
  try {
    window.videoPlayer = new VideoPlayerController('left-video-zone');
  } catch (e) {
    console.error('Error inicializando VideoPlayerController:', e);
  }

  try {
    window.subtitleOverlay = new SubtitleOverlayController('subtitle-overlay-container');
  } catch (e) {
    console.error('Error inicializando SubtitleOverlayController:', e);
  }

  try {
    window.glossOverlay = new GlossOverlayController('gloss-overlay-container');
  } catch (e) {
    console.error('Error inicializando GlossOverlayController:', e);
  }

  try {
    window.contextualInspector = new ContextualInspectorController('contextual-inspector-zone');
  } catch (e) {
    console.error('Error inicializando ContextualInspectorController:', e);
  }

  try {
    window.subtitleEditorPanel = new SubtitleEditorPanel('view-side-subtitles');
  } catch (e) {
    console.error('Error inicializando SubtitleEditorPanel:', e);
  }

  try {
    window.transcriptWindow = new TranscriptWindowController('segment-hub-view');
  } catch (e) {
    console.error('Error inicializando TranscriptWindowController:', e);
  }

  try {
    window.timeline = new MultiTrackTimelineController('timeline-view-wrap');
  } catch (e) {
    console.error('Error inicializando MultiTrackTimelineController:', e);
  }

  try {
    window.modalsController = new ModalsAndExportController();
  } catch (e) {
    console.error('Error inicializando ModalsAndExportController:', e);
  }

  // 2. Inicializar Splitters Redimensionables
  try {
    initSplitters();
  } catch (e) {
    console.error('Error inicializando splitters:', e);
  }

  // 3. Inicializar Atajos de Teclado Globales
  try {
    initKeyboardShortcuts();
  } catch (e) {
    console.error('Error inicializando atajos:', e);
  }

  // 4. Inicializar Barra Superior y las 3 Etapas
  try {
    initTopNavbarAndStages();
  } catch (e) {
    console.error('Error inicializando top navbar:', e);
  }

  // 5. Inicializar Pestañas del Dock Inferior
  try {
    initBottomDockTabs();
  } catch (e) {
    console.error('Error inicializando bottom dock tabs:', e);
  }

  // 5.1. Inicializar Control de Ocultar / Mostrar Dock Inferior
  try {
    initBottomDockToggle();
  } catch (e) {
    console.error('Error inicializando bottom dock toggle:', e);
  }

  // 6. Carga de Archivos JSON y Drag & Drop
  try {
    initFileLoadersAndDragDrop();
  } catch (e) {
    console.error('Error inicializando carga de archivos:', e);
  }

  // 7. Comprobar Backend FastAPI
  checkBackendHealth();

  console.log('LSEC Studio 2.1.1 listo.');
});

// ============================================================
// BARRA SUPERIOR Y CONMUTACIÓN DE LAS 3 ETAPAS
// ============================================================

// ============================================================
// SISTEMA DE TOASTS Y CONTROL DE FLUJO SECUENCIAL
// ============================================================

function showToast(message, type = 'warning') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `app-toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${type === 'success' ? '✓' : (type === 'error' ? '✗' : 'ℹ')}</span>
    <span class="toast-message">${message}</span>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('fade-out');
    setTimeout(() => toast.remove(), 350);
  }, 3800);
}

window.showToast = showToast;

function updateWorkflowUI() {
  const ws = appState.state.workspace;
  const step = ws.workflowStep; // 'no_video' | 'step1_preparar' | 'step2_traducir' | 'step3_revisar' | 'completed'
  const isVideoLoaded = ws.videoLoaded;

  // 1. Botones de Etapa (Top Navbar)
  const btnPrep = document.getElementById('stage-btn-preparar');
  const btnTrad = document.getElementById('stage-btn-traducir');
  const btnRev = document.getElementById('stage-btn-revisar');
  const lockPrep = document.getElementById('lock-icon-preparar');
  const lockTrad = document.getElementById('lock-icon-traducir');
  const lockRev = document.getElementById('lock-icon-revisar');

  const canPrep = appState.canAccessStage('preparar');
  const canTrad = appState.canAccessStage('traducir');
  const canRev = appState.canAccessStage('revisar');

  if (btnPrep) {
    btnPrep.disabled = !canPrep;
    btnPrep.classList.toggle('disabled', !canPrep);
    btnPrep.classList.toggle('stage-locked', !canPrep);
    btnPrep.classList.toggle('active', ws.stage === 'preparar');
    if (lockPrep) lockPrep.style.display = canPrep ? 'none' : 'inline';
    btnPrep.title = canPrep ? '1. Preparar: Audio, transcripción y segmentación (Tecla 1)' : '1. Preparar: Carga un video primero (Paso 1)';
  }

  if (btnTrad) {
    btnTrad.disabled = !canTrad;
    btnTrad.classList.toggle('disabled', !canTrad);
    btnTrad.classList.toggle('stage-locked', !canTrad);
    btnTrad.classList.toggle('active', ws.stage === 'traducir');
    if (lockTrad) lockTrad.style.display = canTrad ? 'none' : 'inline';
    btnTrad.title = canTrad ? '2. Traducir: Glosas LSEC, sintaxis y rasgos espaciales (Tecla 2)' : '2. Traducir: Bloqueado hasta revisar y traducir texto (Paso 2)';
  }

  if (btnRev) {
    btnRev.disabled = !canRev;
    btnRev.classList.toggle('disabled', !canRev);
    btnRev.classList.toggle('stage-locked', !canRev);
    btnRev.classList.toggle('active', ws.stage === 'revisar');
    if (lockRev) lockRev.style.display = canRev ? 'none' : 'inline';
    btnRev.title = canRev ? '3. Revisar: Incidencias, validación humana y exportación (Tecla 3)' : '3. Revisar: Bloqueado hasta confirmar glosas LSEC (Paso 3)';
  }

  // 2. Botón Guardar y Exportar
  const btnSave = document.getElementById('btn-top-save');
  if (btnSave) {
    btnSave.disabled = !isVideoLoaded;
    btnSave.classList.toggle('disabled', !isVideoLoaded);
  }

  const btnExport = document.getElementById('btn-top-export');
  const canExport = appState.canExport();
  if (btnExport) {
    btnExport.disabled = !canExport;
    btnExport.classList.toggle('disabled', !canExport);
    btnExport.title = canExport ? 'Exportar video con señas, subtítulos o proyecto JSON' : 'Exportar: Bloqueado hasta confirmar y aprobar la traducción final';
  }

  // 3. Empty State del Video
  const emptyStateEl = document.getElementById('video-empty-state');
  if (emptyStateEl) {
    emptyStateEl.style.display = isVideoLoaded ? 'none' : 'flex';
  }

  // 4. Nodos del Stepper Bar
  const nodeVideo = document.getElementById('step-node-video');
  const nodePrep = document.getElementById('step-node-prep');
  const nodeTrans = document.getElementById('step-node-trans');
  const nodeRev = document.getElementById('step-node-rev');

  if (nodeVideo) {
    nodeVideo.className = `stepper-step ${isVideoLoaded ? 'completed' : 'active'}`;
  }

  if (nodePrep) {
    const isPrepActive = step === 'step1_preparar';
    const isPrepDone = ws.translationReady;
    nodePrep.className = `stepper-step ${!isVideoLoaded ? 'locked' : (isPrepDone ? 'completed' : (isPrepActive ? 'active' : ''))}`;
  }

  if (nodeTrans) {
    const isTransActive = step === 'step2_traducir';
    const isTransDone = step === 'step3_revisar' || step === 'completed';
    nodeTrans.className = `stepper-step ${!ws.translationReady ? 'locked' : (isTransDone ? 'completed' : (isTransActive ? 'active' : ''))}`;
  }

  if (nodeRev) {
    const isRevActive = step === 'step3_revisar';
    const isRevDone = step === 'completed';
    nodeRev.className = `stepper-step ${step !== 'step3_revisar' && step !== 'completed' ? 'locked' : (isRevDone ? 'completed' : (isRevActive ? 'active' : ''))}`;
  }

  // 5. Botón de Avance Dinámico del Stepper
  const btnStepAction = document.getElementById('btn-step-action');
  const txtStepAction = document.getElementById('btn-step-action-text');

  if (btnStepAction && txtStepAction) {
    if (step === 'no_video') {
      btnStepAction.style.display = 'none';
    } else if (step === 'step1_preparar') {
      btnStepAction.style.display = 'inline-flex';
      btnStepAction.className = 'btn btn-action-step btn-action-primary';
      txtStepAction.textContent = 'Traducir a Glosas LSEC ▶';
      btnStepAction.title = 'Generar propuesta de glosas LSEC con las palabras revisadas';
    } else if (step === 'step2_traducir') {
      btnStepAction.style.display = 'inline-flex';
      btnStepAction.className = 'btn btn-action-step btn-action-highlight';
      txtStepAction.textContent = 'Confirmar Glosas y Pasar a Revisión ▶';
      btnStepAction.title = 'Avanzar a la etapa de revisión final de incidencias';
    } else if (step === 'step3_revisar') {
      btnStepAction.style.display = 'inline-flex';
      btnStepAction.className = 'btn btn-action-step btn-action-success';
      txtStepAction.textContent = 'Confirmar y Aprobar Traducción Final ✓';
      btnStepAction.title = 'Aprobar definitivamente la traducción para habilitar la exportación';
    } else if (step === 'completed') {
      btnStepAction.style.display = 'inline-flex';
      btnStepAction.className = 'btn btn-action-step btn-action-secondary';
      txtStepAction.textContent = 'Traducción Aprobada ✓ (Abrir Exportación)';
      btnStepAction.title = 'Abrir diálogo de exportación';
    }
  }
}

// ============================================================
// BARRA SUPERIOR Y CONMUTACIÓN DE LAS 3 ETAPAS
// ============================================================

function initTopNavbarAndStages() {
  // 1. Selector de 3 Etapas con control secuencial
  const stageBtns = document.querySelectorAll('.stage-btn');
  stageBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const stage = btn.getAttribute('data-stage');
      applyStage(stage);
    });
  });

  // 2. Botón Guardar
  const btnSave = document.getElementById('btn-top-save');
  if (btnSave) {
    btnSave.addEventListener('click', () => {
      if (!appState.state.workspace.videoLoaded) {
        showToast('Carga un video primero antes de guardar.', 'warning');
        return;
      }
      appState.saveToLocalStorage();
      showToast('Proyecto guardado en almacenamiento local.', 'success');
    });
  }

  // 3. Botón Exportar
  const btnExport = document.getElementById('btn-top-export');
  if (btnExport) {
    btnExport.addEventListener('click', (e) => {
      e.preventDefault();
      if (!appState.canExport()) {
        showToast('La exportación está bloqueada: debes confirmar y aprobar la traducción final en la Etapa 3.', 'warning');
        return;
      }
      if (window.modalsController) {
        if (typeof window.modalsController.openExportModal === 'function') {
          window.modalsController.openExportModal();
        } else if (typeof window.modalsController.openExportDialog === 'function') {
          window.modalsController.openExportDialog();
        }
      }
    });
  }

  // 4. Botón de Acción Dinámico del Stepper Bar
  const btnStepAction = document.getElementById('btn-step-action');
  if (btnStepAction) {
    btnStepAction.addEventListener('click', (e) => {
      e.preventDefault();
      const step = appState.state.workspace.workflowStep;
      if (step === 'step1_preparar') {
        if (window.pipelineProcessor) {
          window.pipelineProcessor.translateProjectGlosses();
        }
      } else if (step === 'step2_traducir') {
        appState.markTranslationReviewStep();
        showToast('Glosas LSEC confirmadas. Pasando a Etapa 3: Revisión de incidencias.', 'info');
      } else if (step === 'step3_revisar') {
        appState.markTranslationConfirmed();
        showToast('¡Traducción final confirmada y validada! Ya puedes exportar tu video.', 'success');
      } else if (step === 'completed') {
        if (window.modalsController) {
          if (typeof window.modalsController.openExportModal === 'function') {
            window.modalsController.openExportModal();
          } else if (typeof window.modalsController.openExportDialog === 'function') {
            window.modalsController.openExportDialog();
          }
        }
      }
    });
  }

  // 5. Deshacer / Rehacer
  const btnUndo = document.getElementById('btn-undo');
  const btnRedo = document.getElementById('btn-redo');
  const syncUndoRedoButtons = () => {
    const canUndo = Array.isArray(appState.historyStack) && appState.historyStack.length > 0;
    const canRedo = Array.isArray(appState.redoStack) && appState.redoStack.length > 0;
    if (btnUndo) {
      btnUndo.disabled = !canUndo;
      btnUndo.classList.toggle('disabled', !canUndo);
    }
    if (btnRedo) {
      btnRedo.disabled = !canRedo;
      btnRedo.classList.toggle('disabled', !canRedo);
    }
  };
  if (btnUndo) btnUndo.addEventListener('click', () => appState.undo());
  if (btnRedo) btnRedo.addEventListener('click', () => appState.redo());
  appState.subscribe('historyChanged', syncUndoRedoButtons);
  appState.subscribe('projectLoaded', syncUndoRedoButtons);
  appState.subscribe('projectCleared', syncUndoRedoButtons);
  syncUndoRedoButtons();

  // 6. Actualización del Nombre del Proyecto e Indicadores
  const projectNameEl = document.getElementById('nav-project-name');
  const saveIndicatorEl = document.getElementById('nav-save-indicator');

  const updateNavbar = (project) => {
    if (projectNameEl) {
      projectNameEl.textContent = project?.media_info?.filename || 'Sin video cargado';
    }
  };

  appState.subscribe('projectLoaded', (proj) => {
    updateNavbar(proj);
    updateWorkflowUI();
  });

  appState.subscribe('saveStatusChanged', (status) => {
    if (saveIndicatorEl) {
      saveIndicatorEl.textContent = status === 'saved' ? 'Guardado' : 'Cambios sin guardar';
      saveIndicatorEl.classList.toggle('unsaved', status !== 'saved');
    }
  });

  appState.subscribe('stageChanged', (stage) => {
    updateWorkflowUI();
  });

  appState.subscribe('workflowChanged', () => {
    updateWorkflowUI();
  });

  appState.subscribe('stageBlocked', ({ reason }) => {
    showToast(reason, 'warning');
  });

  // Aplicar estado inicial
  updateWorkflowUI();
}

function applyStage(stage) {
  const allowed = appState.setStage(stage);
  if (!allowed) return;

  const tabSegmentHub = document.getElementById('tab-btn-segment-hub');
  const tabTimeline = document.getElementById('tab-btn-timeline');
  const segmentHubView = document.getElementById('segment-hub-view');
  const timelineView = document.getElementById('timeline-view-wrap');

  if (stage === 'preparar') {
    // Foco en segmentación y transcripción
    if (tabSegmentHub && tabTimeline) {
      tabSegmentHub.classList.add('active');
      tabTimeline.classList.remove('active');
    }
    if (segmentHubView) segmentHubView.style.display = 'flex';
    if (timelineView) timelineView.style.display = 'none';
    appState.setFilter('quickFilter', 'ALL');
  } else if (stage === 'traducir') {
    // Foco en glosas y orden sintáctico
    if (tabSegmentHub && tabTimeline) {
      tabSegmentHub.classList.add('active');
      tabTimeline.classList.remove('active');
    }
    if (segmentHubView) segmentHubView.style.display = 'flex';
    if (timelineView) timelineView.style.display = 'none';
  } else if (stage === 'revisar') {
    // Foco en incidencias y validación
    if (tabSegmentHub && tabTimeline) {
      tabSegmentHub.classList.add('active');
      tabTimeline.classList.remove('active');
    }
    if (segmentHubView) segmentHubView.style.display = 'flex';
    if (timelineView) timelineView.style.display = 'none';
    appState.setFilter('quickFilter', 'REVIEW');
  }

  if (window.transcriptWindow) window.transcriptWindow.render();
  updateWorkflowUI();
}

// ============================================================
// PESTAÑAS DEL DOCK INFERIOR (EDITOR DE SEGMENTO VS TIMELINE)
// ============================================================

function initBottomDockTabs() {
  const btnSegmentHub = document.getElementById('tab-btn-segment-hub');
  const btnTimeline = document.getElementById('tab-btn-timeline');
  const segmentHubView = document.getElementById('segment-hub-view');
  const timelineView = document.getElementById('timeline-view-wrap');

  if (btnSegmentHub) {
    btnSegmentHub.addEventListener('click', () => {
      btnSegmentHub.classList.add('active');
      if (btnTimeline) btnTimeline.classList.remove('active');
      if (segmentHubView) segmentHubView.style.display = 'flex';
      if (timelineView) timelineView.style.display = 'none';
      if (window.transcriptWindow) window.transcriptWindow.render();
    });
  }

  if (btnTimeline) {
    btnTimeline.addEventListener('click', () => {
      btnTimeline.classList.add('active');
      if (btnSegmentHub) btnSegmentHub.classList.remove('active');
      if (segmentHubView) segmentHubView.style.display = 'none';
      if (timelineView) timelineView.style.display = 'flex';
      if (window.timeline) window.timeline.render();
    });
  }
}

// ============================================================
// SPLITTERS REDIMENSIONABLES (DIVISORES ARRASTRABLES)
// ============================================================

function initSplitters() {
  const vSplitter = document.getElementById('vertical-splitter');
  const leftZone = document.getElementById('left-video-zone');
  const rightZone = document.getElementById('contextual-inspector-zone');
  const container = document.getElementById('top-split-container');

  if (vSplitter && leftZone && rightZone && container) {
    let isDraggingV = false;

    vSplitter.addEventListener('mousedown', () => {
      isDraggingV = true;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    });

    window.addEventListener('mousemove', (e) => {
      if (!isDraggingV) return;
      const containerRect = container.getBoundingClientRect();
      const newRightWidth = containerRect.right - e.clientX;
      if (newRightWidth >= 260 && newRightWidth <= 600) {
        rightZone.style.width = `${newRightWidth}px`;
      }
    });

    window.addEventListener('mouseup', () => {
      if (isDraggingV) {
        isDraggingV = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    });
  }

  const hSplitter = document.getElementById('horizontal-splitter');
  const bottomDock = document.getElementById('bottom-dock-zone');
  const mainWorkspace = document.getElementById('main-workspace');

  if (hSplitter && bottomDock && mainWorkspace) {
    let isDraggingH = false;

    hSplitter.addEventListener('mousedown', () => {
      isDraggingH = true;
      document.body.style.cursor = 'row-resize';
      document.body.style.userSelect = 'none';
    });

    window.addEventListener('mousemove', (e) => {
      if (!isDraggingH) return;
      const workspaceRect = mainWorkspace.getBoundingClientRect();
      const newHeight = workspaceRect.bottom - e.clientY;
      if (newHeight >= 200 && newHeight <= 600) {
        bottomDock.style.height = `${newHeight}px`;
        if (window._setSavedBottomDockHeight) {
          window._setSavedBottomDockHeight(newHeight);
        }
      }
    });

    window.addEventListener('mouseup', () => {
      if (isDraggingH) {
        isDraggingH = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    });
  }
}

// ============================================================
// CONTROL DE OCULTAR / MOSTRAR BARRA INFERIOR (DOCK & TIMELINE)
// ============================================================

function initBottomDockToggle() {
  const mainWorkspace = document.getElementById('main-workspace');
  const bottomDock = document.getElementById('bottom-dock-zone');
  const collapsedBar = document.getElementById('bottom-dock-collapsed-bar');
  const btnToggleTop = document.getElementById('btn-toggle-bottom-dock');
  const btnToggleText = document.getElementById('btn-toggle-bottom-dock-text');
  const btnCollapseDock = document.getElementById('btn-collapse-bottom-dock');
  const btnExpandDock = document.getElementById('btn-expand-bottom-dock');

  let savedHeight = null;
  window._setSavedBottomDockHeight = (h) => { savedHeight = h; };

  function updateDockUI(isCollapsed) {
    if (!mainWorkspace || !bottomDock) return;

    if (isCollapsed) {
      if (bottomDock.offsetHeight > 100) {
        savedHeight = bottomDock.offsetHeight;
      }
      mainWorkspace.classList.add('bottom-dock-hidden');
      if (collapsedBar) collapsedBar.style.display = 'flex';
      if (btnToggleTop) {
        btnToggleTop.classList.add('dock-hidden');
        btnToggleTop.setAttribute('title', 'Mostrar panel inferior de edición y línea de tiempo (Tecla B)');
      }
      if (btnToggleText) {
        btnToggleText.textContent = 'Mostrar Inferior';
      }
    } else {
      mainWorkspace.classList.remove('bottom-dock-hidden');
      if (savedHeight >= 200) {
        bottomDock.style.height = `${savedHeight}px`;
      }
      if (collapsedBar) collapsedBar.style.display = 'none';
      if (btnToggleTop) {
        btnToggleTop.classList.remove('dock-hidden');
        btnToggleTop.setAttribute('title', 'Ocultar panel inferior de edición y línea de tiempo (Tecla B)');
      }
      if (btnToggleText) {
        btnToggleText.textContent = 'Panel Inferior';
      }

      // Re-renderizar componentes dependientes de dimensiones
      setTimeout(() => {
        if (window.timeline && typeof window.timeline.render === 'function') {
          window.timeline.render();
        }
        if (window.transcriptWindow && typeof window.transcriptWindow.render === 'function') {
          window.transcriptWindow.render();
        }
      }, 50);
    }

    // Notificar a observadores de redimensionamiento de ventana
    window.dispatchEvent(new Event('resize'));
  }

  // Suscripción al estado reactivo
  appState.subscribe('bottomDockToggled', ({ collapsed }) => {
    updateDockUI(collapsed);
  });

  // Botón en barra superior
  if (btnToggleTop) {
    btnToggleTop.addEventListener('click', () => {
      appState.toggleBottomDock();
    });
  }

  // Botón minimizar en dock inferior
  if (btnCollapseDock) {
    btnCollapseDock.addEventListener('click', () => {
      appState.setBottomDockCollapsed(true);
    });
  }

  // Botón expandir en la barra colapsada
  if (btnExpandDock) {
    btnExpandDock.addEventListener('click', () => {
      appState.setBottomDockCollapsed(false);
    });
  }

  // Aplicar estado inicial
  updateDockUI(appState.state.workspace.bottomDockCollapsed);
}

// ============================================================
// ATAJOS DE TECLADO GLOBALES
// ============================================================

function initKeyboardShortcuts() {
  window.addEventListener('keydown', (e) => {
    const isInputActive = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName);
    if (isInputActive) return;

    // 1, 2, 3: Etapas (respetan bloqueo secuencial)
    if (e.key === '1') { e.preventDefault(); applyStage('preparar'); }
    if (e.key === '2') { e.preventDefault(); applyStage('traducir'); }
    if (e.key === '3') { e.preventDefault(); applyStage('revisar'); }

    // Si no hay video cargado, no permitir controles de reproducción multimedia
    if (!appState.state.workspace.videoLoaded) {
      if ([' ', 'k', 'K', 'j', 'J', 'l', 'L', 'i', 'I', 'o', 'O'].includes(e.key)) {
        e.preventDefault();
        showToast('Debes cargar un video primero (Paso 1).', 'warning');
        return;
      }
    }

    // Espacio o K: Play / Pause
    if (e.key === ' ' || e.key === 'k' || e.key === 'K') {
      e.preventDefault();
      appState.togglePlayPause();
    }

    // J / L: Retroceder / Avanzar 5s
    if (e.key === 'j' || e.key === 'J') {
      e.preventDefault();
      appState.setCurrentTime(appState.state.playback.currentTime - 5.0, 'shortcut_j');
    }
    if (e.key === 'l' || e.key === 'L') {
      e.preventDefault();
      appState.setCurrentTime(appState.state.playback.currentTime + 5.0, 'shortcut_l');
    }

    // I / O: In / Out bucle
    if (e.key === 'i' || e.key === 'I') {
      e.preventDefault();
      appState.setInPoint(appState.state.playback.currentTime);
    }
    if (e.key === 'o' || e.key === 'O') {
      e.preventDefault();
      appState.setOutPoint(appState.state.playback.currentTime);
    }

    // C: Conmutar subtítulos
    if (e.key === 'c' || e.key === 'C') {
      e.preventDefault();
      const next = !appState.state.overlays.subtitlesEnabled;
      appState.state.overlays.subtitlesEnabled = next;
      appState.emit('overlayPrefChanged', { key: 'subtitlesEnabled', value: next });
    }

    // G: Conmutar glosas LSEC
    if (e.key === 'g' || e.key === 'G') {
      e.preventDefault();
      const next = !appState.state.overlays.glossesEnabled;
      appState.state.overlays.glossesEnabled = next;
      appState.emit('overlayPrefChanged', { key: 'glossesEnabled', value: next });
    }

    // M: Mute
    if (e.key === 'm' || e.key === 'M') {
      e.preventDefault();
      appState.toggleMute();
    }

    // B: Ocultar / Mostrar Barra Inferior (Dock y Timeline)
    if (e.key === 'b' || e.key === 'B') {
      e.preventDefault();
      appState.toggleBottomDock();
    }

    // Ctrl + S: Guardar
    if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
      e.preventDefault();
      if (!appState.state.workspace.videoLoaded) {
        showToast('Carga un video primero antes de guardar.', 'warning');
        return;
      }
      appState.saveToLocalStorage();
      showToast('Proyecto guardado en almacenamiento local.', 'success');
    }

    // Ctrl + Z / Ctrl + Y: Deshacer / Rehacer
    if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) {
      e.preventDefault();
      appState.undo();
    }
    if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || e.key === 'Y')) {
      e.preventDefault();
      appState.redo();
    }
  });
}

// ============================================================
// CARGA DE ARCHIVOS Y DRAG & DROP GLOBAL
// ============================================================

function initFileLoadersAndDragDrop() {
  const btnLoadVideo = document.getElementById('btn-top-load-video');
  const videoInput = document.getElementById('video-file-input');
  if (btnLoadVideo && videoInput) {
    btnLoadVideo.addEventListener('click', (e) => {
      e.preventDefault();
      videoInput.value = '';
      videoInput.click();
    });
  }

  // Botón Empty State: Cargar Video Local
  const btnEmptyLoad = document.getElementById('btn-empty-load-video');
  if (btnEmptyLoad && videoInput) {
    btnEmptyLoad.addEventListener('click', (e) => {
      e.preventDefault();
      videoInput.value = '';
      videoInput.click();
    });
  }



  const btnLoadJSON = document.getElementById('btn-top-load-json');
  const jsonInput = document.getElementById('json-file-input');
  if (btnLoadJSON && jsonInput) {
    btnLoadJSON.addEventListener('click', (e) => {
      e.preventDefault();
      jsonInput.value = '';
      jsonInput.click();
    });
  }

  if (jsonInput) {
    jsonInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (evt) => {
          appState.loadProjectFromJSON(evt.target.result, file.name);
        };
        reader.readAsText(file);
      }
    });
  }

  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => {
    e.preventDefault();
    if (e.dataTransfer?.files?.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.type.startsWith('video/') || file.name.match(/\.(mp4|webm|mov|mkv)$/i)) {
        if (window.videoPlayer) window.videoPlayer.loadLocalVideoFile(file);
      } else if (file.name.endsWith('.json')) {
        const reader = new FileReader();
        reader.onload = (evt) => appState.loadProjectFromJSON(evt.target.result, file.name);
        reader.readAsText(file);
      }
    }
  });
}



// ============================================================
// VERIFICACIÓN CON BACKEND FASTAPI Y HARDWARE ACCELERATION
// ============================================================

async function checkBackendHealth() {
  try {
    const res = await fetch('/api/v1/health');
    if (res.ok) {
      const data = await res.json();
      console.log('Backend FastAPI conectado:', data);
      updateHardwareStatusBadge(data.hardware);
    }
  } catch (err) {
    console.log('Operando en modo autónomo.');
    updateHardwareStatusBadge(null);
  }
}

function updateHardwareStatusBadge(hw) {
  const badge = document.getElementById('hardware-accel-badge');
  const dot = document.getElementById('hardware-accel-dot');
  const text = document.getElementById('hardware-accel-text');
  if (!badge || !dot || !text) return;

  if (!hw) {
    dot.style.background = '#888';
    dot.style.boxShadow = 'none';
    text.textContent = 'Autónomo';
    badge.title = 'Modo local autónomo (backend desconectado)';
    return;
  }

  window.systemHardwareStatus = hw;

  if (hw.is_gpu) {
    dot.style.background = '#10b981';
    dot.style.boxShadow = '0 0 6px #10b981';
    text.textContent = 'GPU Activa (CUDA)';
    text.style.color = '#10b981';
    badge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
    badge.style.background = 'rgba(16, 185, 129, 0.12)';
    badge.title = `Aceleración por GPU NVIDIA activa (${hw.compute_type || 'float16'}). Procesamiento Whisper de alta velocidad.`;
    badge.onclick = () => {
      alert(`[ACELERACIÓN POR GPU ACTIVA]\n\nDispositivo: GPU NVIDIA (CUDA)\nTipo de cómputo: ${hw.compute_type || 'float16'}\nEstado: Operacional`);
    };
  } else {
    dot.style.background = '#f59e0b';
    dot.style.boxShadow = '0 0 6px #f59e0b';
    text.textContent = 'Modo CPU';
    text.style.color = '#f59e0b';
    badge.style.borderColor = 'rgba(245, 158, 11, 0.4)';
    badge.style.background = 'rgba(245, 158, 11, 0.12)';
    const warningMsg = hw.notice || 'Whisper está operando en la CPU sin aceleración GPU.';
    badge.title = `${warningMsg} Haga clic para ver detalles.`;
    badge.onclick = () => {
      alert(`[AVISO DE HARDWARE - MODO CPU]\n\n${warningMsg}\n\nDispositivo: CPU\nTipo de cómputo: ${hw.compute_type || 'int8'}\nFallback: ${hw.fallback_occurred ? 'Sí (' + hw.fallback_reason + ')' : 'No'}`);
    };
  }
}

window.checkBackendHealth = checkBackendHealth;
window.updateHardwareStatusBadge = updateHardwareStatusBadge;

