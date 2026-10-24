/**
 * LSEC Studio — Coordinador Principal del Flujo Guiado en 3 Ventanas (Wizard)
 * Sistema de diseño «Pedagogical Tactile Light» (DESIGN.md)
 *
 * Ventana 1 (preparar): Video + Onda Acústica Whisper ASR + Segmentos Editables
 * Ventana 2 (traducir): Monitor de Transformación Gramatical + Mesa Comparativa Paralela
 * Ventana 3 (revisar): Escenario Multimedia (Video + Subtítulos + Avatar 3D VRM) + Monitor en Vivo + Estilos/Exportación
 */

document.addEventListener('DOMContentLoaded', () => {
  // Asegurar tema claro pedagógico por defecto
  if (document.documentElement) {
    document.documentElement.setAttribute('data-theme', 'light');
  }

  // 1. Inicializar Controladores Base con Aislamiento de Errores
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
    window.subtitleEditorPanel = new SubtitleEditorPanel('view-side-subtitles');
  } catch (e) {
    console.error('Error inicializando SubtitleEditorPanel:', e);
  }

  try {
    window.avatarPanel = new AvatarPanelController('view-side-avatar');
  } catch (e) {
    console.error('Error inicializando AvatarPanelController:', e);
  }

  try {
    window.modalsController = new ModalsAndExportController();
  } catch (e) {
    console.error('Error inicializando ModalsAndExportController:', e);
  }

  // 2. Inicializar Ventana 1 (Transcripción con Whisper)
  try {
    window.transcriptWindow = new TranscriptWindowController({
      onRunWhisper: () => {
        if (window.pipelineProcessor) {
          window.transcriptWindow?.setExtractingState(true, 'Extrayendo audio y transcribiendo con Faster-Whisper...');
          Promise.resolve(window.pipelineProcessor.runPipelineForCurrentVideo()).finally(() => {
            window.transcriptWindow?.setExtractingState(false, 'Transcripción Whisper completada y sincronizada');
          });
        }
      },
      onProceedToStep2: async () => {
        await processTranslationAndOpenStep2();
      }
    });
  } catch (e) {
    console.error('Error inicializando TranscriptWindowController:', e);
  }

  // 3. Inicializar Ventana 2 (Motor Lingüístico y Mesa Comparativa Paralela)
  if (typeof LinguisticComparisonView !== 'undefined') {
    try {
      window.linguisticComparisonView = new LinguisticComparisonView();
    } catch (e) {
      console.error('Error inicializando LinguisticComparisonView:', e);
    }
  }

  // 4. Función Global de Navegación entre las 3 Ventanas Independientes (Wizard)
  const STEP_ORDER = ['preparar', 'traducir', 'revisar'];

  function dockVideoZoneForStep(stepName) {
    const videoZone = document.getElementById('left-video-zone');
    if (!videoZone) return;

    const slot1 = document.getElementById('step1-video-slot');
    const slot3 = document.getElementById('step3-video-slot');
    const stageLabel = document.getElementById('video-stage-mode-label');

    if (stepName === 'revisar' && slot3) {
      if (videoZone.parentElement !== slot3) {
        slot3.appendChild(videoZone);
      }
      if (stageLabel) {
        stageLabel.textContent = 'Video + Subtítulos + Avatar 3D LSEC';
      }
      if (window.studioAvatarBridge && typeof window.studioAvatarBridge.handleResize === 'function') {
        setTimeout(() => window.studioAvatarBridge.handleResize(), 60);
      }
    } else if (slot1) {
      if (videoZone.parentElement !== slot1) {
        slot1.appendChild(videoZone);
      }
      if (stageLabel) {
        stageLabel.textContent = 'MP4 / WebM Local';
      }
    }
  }

  window.switchWizardStep = function switchWizardStep(stepName) {
    const normalized = STEP_ORDER.includes(stepName) ? stepName : 'preparar';
    const targetIdx = STEP_ORDER.indexOf(normalized);

    // Actualizar visibilidad de las 3 ventanas independientes
    document.querySelectorAll('.wizard-window').forEach((win) => {
      const isMatch = win.dataset.wizardStep === normalized;
      win.classList.toggle('active', isMatch);
    });

    // Actualizar botones del Stepper Superior
    document.querySelectorAll('#workflow-stepper .step-btn').forEach((btn) => {
      const btnStep = btn.dataset.step;
      const btnIdx = STEP_ORDER.indexOf(btnStep);
      const isActive = btnStep === normalized;
      const isCompleted = btnIdx >= 0 && btnIdx < targetIdx;

      btn.classList.toggle('active', isActive);
      btn.classList.toggle('completed', isCompleted);
      if (isActive) {
        btn.setAttribute('aria-current', 'step');
      } else {
        btn.removeAttribute('aria-current');
      }
    });

    // Anclar el escenario de video compartido en Ventana 1 o Ventana 3
    dockVideoZoneForStep(normalized);

    // Sincronizar con el estado global
    if (typeof appState !== 'undefined') {
      appState.state.workspace.stage = normalized;
      appState.emit('stageChanged', normalized);
    }

    if (normalized === 'traducir' && window.linguisticComparisonView) {
      window.linguisticComparisonView.renderAll();
    } else if (normalized === 'revisar') {
      renderStep3LiveSignMonitor();
    }
  };

  // Procesar traducción hacia Ventana 2
  async function processTranslationAndOpenStep2() {
    const segments = appState?.state?.project?.segments || [];
    if (segments.length === 0 && window.pipelineProcessor) {
      await window.pipelineProcessor.runPipelineForCurrentVideo();
    }
    if (typeof appState !== 'undefined') {
      appState.state.workspace.transcriptionReady = true;
      appState.state.workspace.translationReady = true;
    }
    window.switchWizardStep('traducir');
    showToast('Motor lingüístico LSEC aplicado. Revisa la mesa comparativa.', 'success');
  }

  // 5. Enlazar Eventos de Navegación del Stepper y Botones de Ventanas
  document.querySelectorAll('#workflow-stepper .step-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetStep = btn.dataset.step;
      window.switchWizardStep(targetStep);
    });
  });

  const btnChangeVideo = document.getElementById('btn-stage-change-video');
  const fileUploadInput = document.getElementById('file-upload-input');
  if (btnChangeVideo && fileUploadInput) {
    btnChangeVideo.addEventListener('click', () => fileUploadInput.click());
  }

  const btnStep2Back = document.getElementById('btn-step2-back');
  if (btnStep2Back) {
    btnStep2Back.addEventListener('click', () => window.switchWizardStep('preparar'));
  }

  const btnStep2Confirm = document.getElementById('btn-step2-confirm-glosses');
  if (btnStep2Confirm) {
    btnStep2Confirm.addEventListener('click', () => {
      if (typeof appState !== 'undefined' && typeof appState.confirmTranslationStage === 'function') {
        appState.confirmTranslationStage();
      }
      window.switchWizardStep('revisar');
      showToast('Glosas LSEC confirmadas. Avatar 3D VRM listo en vista previa.', 'success');
    });
  }

  const btnStep3Back = document.getElementById('btn-step3-back-to-glosses');
  if (btnStep3Back) {
    btnStep3Back.addEventListener('click', () => window.switchWizardStep('traducir'));
  }

  const btnStep3Replay = document.getElementById('btn-step3-replay-sentence');
  if (btnStep3Replay) {
    btnStep3Replay.addEventListener('click', () => {
      const currentTime = appState?.state?.playback?.currentTime || 0;
      const segments = appState?.state?.project?.segments || [];
      const activeSeg = segments.find(s => currentTime >= s.start_time && currentTime <= s.end_time) || segments[0];
      if (activeSeg) {
        appState.setCurrentTime(Number(activeSeg.start_time) || 0, true);
        if (window.videoPlayer && typeof window.videoPlayer.play === 'function') {
          window.videoPlayer.play();
        }
      }
    });
  }

  // Botones prominentes de Exportación en Ventana 3
  const btnExportMp4 = document.getElementById('btn-step3-export-mp4');
  if (btnExportMp4) {
    btnExportMp4.addEventListener('click', () => {
      if (window.modalsController && typeof window.modalsController.openExportModal === 'function') {
        window.modalsController.openExportModal();
      }
    });
  }

  const btnExportSrt = document.getElementById('btn-step3-export-srt');
  if (btnExportSrt) {
    btnExportSrt.addEventListener('click', () => {
      if (window.modalsController && typeof window.modalsController.exportSRT === 'function') {
        window.modalsController.exportSRT();
      } else if (window.modalsController && typeof window.modalsController.openExportModal === 'function') {
        window.modalsController.openExportModal();
      }
    });
  }

  // 6. Monitor en Vivo de Señas para la Ventana 3
  function classifyGlossSignType(glossItem) {
    if (!glossItem) return { label: 'Seña CONADIS', css: 'gloss-chip-conadis', badgeBg: '#10b981' };
    const token = String(glossItem.gloss || glossItem.text || glossItem || '').toUpperCase();
    const isManual = Boolean(
      glossItem.manually_edited ||
      glossItem.status === 'HUMAN_VERIFIED' ||
      glossItem.alignment_type === 'MANUAL_EDIT'
    );
    const isFingerspell = Boolean(
      glossItem.source === 'FINGERSPELLING' ||
      glossItem.is_fingerspelling ||
      token.startsWith('FS:') ||
      token.includes('-')
    );

    if (isManual) {
      return { label: 'Editada Manualmente', css: 'gloss-chip-edited', badgeBg: '#f59e0b' };
    }
    if (isFingerspell) {
      return { label: 'Dactilología', css: 'gloss-chip-fingerspell', badgeBg: '#0284c7' };
    }
    return { label: 'Seña CONADIS', css: 'gloss-chip-conadis', badgeBg: '#10b981' };
  }

  function renderStep3LiveSignMonitor(currentTime = null) {
    if (typeof appState === 'undefined' || !appState.state?.project) return;
    const t = currentTime !== null ? currentTime : (appState.state.playback.currentTime || 0);
    const segments = appState.state.project.segments || [];
    const allGlosses = appState.state.project.glosses || [];

    const timeBadge = document.getElementById('live-monitor-time-badge');
    if (timeBadge) {
      const mins = Math.floor(t / 60);
      const secs = (t % 60).toFixed(1).padStart(4, '0');
      timeBadge.textContent = `${String(mins).padStart(2, '0')}:${secs}`;
    }

    const activeSeg = segments.find(s => t >= s.start_time && t <= s.end_time) || segments[0] || null;
    const activeGloss = allGlosses.find(g => t >= g.start_time && t <= g.end_time) || null;

    const wordEl = document.getElementById('live-current-sign-word');
    const typeEl = document.getElementById('live-current-sign-type');
    const pipSourceEl = document.getElementById('pip-sign-source-badge');

    if (wordEl && typeEl) {
      if (activeGloss) {
        const info = classifyGlossSignType(activeGloss);
        wordEl.textContent = activeGloss.gloss || 'SEÑA';
        typeEl.textContent = info.label;
        typeEl.style.background = info.badgeBg;
        if (pipSourceEl) pipSourceEl.textContent = info.label.toUpperCase();
      } else if (activeSeg && Array.isArray(activeSeg.gloss_sequence) && activeSeg.gloss_sequence.length > 0) {
        wordEl.textContent = activeSeg.gloss_sequence[0];
        typeEl.textContent = 'Seña CONADIS';
        typeEl.style.background = '#10b981';
      } else {
        wordEl.textContent = 'EN ESPERA';
        typeEl.textContent = 'Avatar en Reposo';
        typeEl.style.background = '#64748b';
      }
    }

    const sentenceBox = document.getElementById('live-current-sentence-box');
    if (sentenceBox) {
      sentenceBox.textContent = activeSeg
        ? (activeSeg.normalized_text || activeSeg.raw_text || 'Oración sin texto')
        : 'Reproduce el video o selecciona una oración.';
    }

    const rackEl = document.getElementById('live-sentence-gloss-rack');
    if (rackEl) {
      rackEl.innerHTML = '';
      const segGlosses = activeSeg
        ? allGlosses.filter(g => g.segment_id === activeSeg.id)
        : [];
      const itemsToRender = segGlosses.length > 0
        ? segGlosses
        : ((activeSeg?.gloss_sequence || []).map(tok => ({ gloss: tok })));

      itemsToRender.forEach((g) => {
        const info = classifyGlossSignType(g);
        const isExecuting = activeGloss && g.id && activeGloss.id === g.id;
        const chip = document.createElement('span');
        chip.className = `gloss-chip-tactile ${info.css}`;
        if (isExecuting) {
          chip.style.outline = '3px solid #0f172a';
        }
        chip.innerHTML = `
          <span>${g.gloss || g}</span>
          <span class="gloss-chip-badge-tag">${info.label === 'Dactilología' ? 'DACTIL.' : (info.label === 'Editada Manualmente' ? 'EDITADA' : 'CONADIS')}</span>
        `;
        chip.addEventListener('click', () => {
          if (typeof g.start_time === 'number') {
            appState.setCurrentTime(g.start_time, true);
          }
        });
        rackEl.appendChild(chip);
      });
    }

    const listEl = document.getElementById('live-all-sentences-list');
    if (listEl && listEl.dataset.renderedCount !== String(segments.length)) {
      listEl.dataset.renderedCount = String(segments.length);
      listEl.innerHTML = '';
      segments.forEach((seg, i) => {
        const rowBtn = document.createElement('button');
        rowBtn.type = 'button';
        rowBtn.className = 'btn btn-sm';
        rowBtn.style.justifyContent = 'flex-start';
        rowBtn.style.textAlign = 'left';
        rowBtn.innerHTML = `<strong>#${i + 1}</strong> <span>${(seg.normalized_text || seg.raw_text || '').slice(0, 52)}</span>`;
        rowBtn.addEventListener('click', () => {
          appState.setCurrentTime(Number(seg.start_time) || 0, true);
          appState.selectItem('segment', seg.id, seg);
          renderStep3LiveSignMonitor(Number(seg.start_time) || 0);
        });
        listEl.appendChild(rowBtn);
      });
    }
  }

  // 7. Suscripciones de Sincronización en Segundo Plano
  if (typeof appState !== 'undefined') {
    appState.subscribe('timeChanged', (t) => {
      if (appState.state.workspace.stage === 'revisar') {
        renderStep3LiveSignMonitor(t);
      }
    });

    appState.subscribe('projectLoaded', () => {
      const listEl = document.getElementById('live-all-sentences-list');
      if (listEl) listEl.dataset.renderedCount = '';
      const titleEl = document.getElementById('project-title-display');
      if (titleEl && appState.state.project?.title) {
        titleEl.textContent = appState.state.project.title;
      }
      renderStep3LiveSignMonitor();
    });

    appState.subscribe('glossesChanged', () => renderStep3LiveSignMonitor());
    appState.subscribe('segmentsChanged', () => {
      const listEl = document.getElementById('live-all-sentences-list');
      if (listEl) listEl.dataset.renderedCount = '';
      renderStep3LiveSignMonitor();
    });
  }

  // Utilidad Global de Notificaciones Toast
  window.showToast = function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.remove();
    }, 3400);
  };
});
