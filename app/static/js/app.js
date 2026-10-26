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

  // 4. Función Global de Navegación entre las 4 Ventanas Independientes (Wizard)
  const STEP_ORDER = ['preparar', 'traducir', 'avatar', 'revisar'];

  function dockVideoZoneForStep(stepName) {
    const videoZone = document.getElementById('left-video-zone');
    if (!videoZone) return;

    const slot1 = document.getElementById('step1-video-slot');
    const slot3 = document.getElementById('step3-video-slot');
    const slot4 = document.getElementById('step4-video-slot');
    const stageLabel = document.getElementById('video-stage-mode-label');
    const changeVideoBtn = document.getElementById('btn-stage-change-video');
    const hasVideo = Boolean(appState?.state?.workspace?.videoLoaded || appState?.state?.project);

    if (stepName === 'avatar' && slot3) {
      if (videoZone.parentElement !== slot3) {
        slot3.appendChild(videoZone);
      }
      if (stageLabel) {
        stageLabel.textContent = 'Video y Subtítulos Sincronizados';
      }
      if (changeVideoBtn) {
        changeVideoBtn.style.display = 'none';
      }
      setTimeout(() => {
        if (window.studioAvatarBridge && typeof window.studioAvatarBridge.dockToStep3Stage === 'function') {
          window.studioAvatarBridge.dockToStep3Stage();
        }
        if (window.subtitleOverlay && typeof window.subtitleOverlay.render === 'function') {
          window.subtitleOverlay.render(appState?.state?.playback?.currentTime || 0);
        }
      }, 50);
    } else if (stepName === 'revisar' && slot4) {
      if (videoZone.parentElement !== slot4) {
        slot4.appendChild(videoZone);
      }
      if (stageLabel) {
        stageLabel.textContent = 'Vista Previa Compuesta (Video + Subtítulos + Avatar 3D)';
      }
      if (changeVideoBtn) {
        changeVideoBtn.style.display = 'none';
      }
      setTimeout(() => {
        if (window.studioAvatarBridge && typeof window.studioAvatarBridge.dockToPip === 'function') {
          window.studioAvatarBridge.dockToPip();
        }
        if (window.subtitleOverlay && typeof window.subtitleOverlay.render === 'function') {
          window.subtitleOverlay.render(appState?.state?.playback?.currentTime || 0);
        }
      }, 50);
    } else if (slot1) {
      if (videoZone.parentElement !== slot1) {
        slot1.appendChild(videoZone);
      }
      if (stageLabel) {
        stageLabel.textContent = 'MP4 / WebM Local';
      }
      if (changeVideoBtn) {
        changeVideoBtn.style.display = hasVideo ? 'inline-flex' : 'none';
      }
      setTimeout(() => {
        if (window.subtitleOverlay && typeof window.subtitleOverlay.render === 'function') {
          window.subtitleOverlay.render(appState?.state?.playback?.currentTime || 0);
        }
      }, 50);
    }
  }

  window.switchWizardStep = function switchWizardStep(stepName) {
    const normalized = STEP_ORDER.includes(stepName) ? stepName : 'preparar';
    const targetIdx = STEP_ORDER.indexOf(normalized);

    // Actualizar visibilidad de las 4 ventanas independientes
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

    // Sincronizar con el estado global antes de acoplar el escenario para que SubtitleEngine conozca la etapa activa
    if (typeof appState !== 'undefined') {
      appState.state.workspace.stage = normalized;
      appState.emit('stageChanged', normalized);
    }

    // Anclar el escenario de video compartido en Ventana 1, Ventana 3 o Ventana 4
    dockVideoZoneForStep(normalized);

    if (normalized === 'traducir' && window.linguisticComparisonView) {
      window.linguisticComparisonView.renderAll();
    } else if (normalized === 'avatar' || normalized === 'revisar') {
      renderStep3LiveSignMonitor();
    }
  };

  // Procesar traducción hacia Ventana 2
  async function processTranslationAndOpenStep2() {
    let segments = appState?.state?.project?.segments || [];
    const glosses = appState?.state?.project?.glosses || [];
    if (window.pipelineProcessor) {
      if (segments.length === 0) {
        if (window.pipelineProcessor.cachedVideoFile && !appState?.state?.workspace?.transcriptionReady) {
          await window.pipelineProcessor.runPipelineForCurrentVideo();
          segments = appState?.state?.project?.segments || [];
        }
        if (segments.length === 0) {
          showToast('Agrega al menos una oración con "+ Oración" o carga un video con voz hablada antes de traducir a LSEC.', 'warning');
          return;
        }
      }
      if ((appState?.state?.project?.glosses || []).length === 0) {
        await window.pipelineProcessor.translateProjectGlosses();
      }
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
  const btnUploadVideo = document.getElementById('btn-upload-video');
  const btnRunPipeline = document.getElementById('btn-run-pipeline');
  const videoDropzone = document.getElementById('video-dropzone');
  const fileUploadInput = document.getElementById('file-upload-input');
  if (btnChangeVideo && fileUploadInput) {
    btnChangeVideo.addEventListener('click', () => fileUploadInput.click());
  }
  if (btnUploadVideo && fileUploadInput) {
    btnUploadVideo.addEventListener('click', () => fileUploadInput.click());
  }
  if (videoDropzone && fileUploadInput) {
    videoDropzone.addEventListener('click', () => fileUploadInput.click());
    videoDropzone.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        fileUploadInput.click();
      }
    });
  }
  if (btnRunPipeline) {
    btnRunPipeline.addEventListener('click', () => {
      if (window.pipelineProcessor) {
        window.transcriptWindow?.setExtractingState(true, 'Extrayendo audio y transcribiendo con Faster-Whisper...');
        Promise.resolve(window.pipelineProcessor.runPipelineForCurrentVideo()).finally(() => {
          window.transcriptWindow?.setExtractingState(false, 'Transcripción Whisper completada y sincronizada');
        });
      }
    });
  }

  const btnLoadDemo = document.getElementById('btn-load-demo');
  if (btnLoadDemo) {
    btnLoadDemo.addEventListener('click', () => {
      if (typeof DEMO_PROJECT_DATA !== 'undefined' && typeof appState !== 'undefined') {
        appState.loadProject(JSON.parse(JSON.stringify(DEMO_PROJECT_DATA)));
        showToast('Proyecto de demostración cargado en LSEC Studio.', 'success');
      }
    });
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
      window.switchWizardStep('avatar');
      showToast('Glosas LSEC confirmadas. Revisa la secuencia del Avatar 3D.', 'success');
    });
  }

  const btnStep3Back = document.getElementById('btn-step3-back-to-glosses');
  if (btnStep3Back) {
    btnStep3Back.addEventListener('click', () => window.switchWizardStep('traducir'));
  }

  const btnStep3ToStep4 = document.getElementById('btn-step3-to-step4');
  if (btnStep3ToStep4) {
    btnStep3ToStep4.addEventListener('click', () => {
      window.switchWizardStep('revisar');
      showToast('Ajusta los subtítulos y exporta el video final.', 'info');
    });
  }

  const btnStep4BackToAvatar = document.getElementById('btn-step4-back-to-avatar');
  if (btnStep4BackToAvatar) {
    btnStep4BackToAvatar.addEventListener('click', () => window.switchWizardStep('avatar'));
  }

  function stepSentenceInMonitor(delta) {
    const segments = appState?.state?.project?.segments || [];
    if (segments.length === 0) return;
    const currentTime = appState?.state?.playback?.currentTime || 0;
    const getStart = (s) => Number(s?.start_time ?? s?.start_seconds ?? 0);
    const getEnd = (s) => Number(s?.end_time ?? s?.end_seconds ?? 0);
    let idx = segments.findIndex(s => currentTime >= getStart(s) && currentTime <= getEnd(s));
    if (idx === -1) idx = 0;
    const nextIdx = Math.max(0, Math.min(segments.length - 1, idx + delta));
    const targetSeg = segments[nextIdx];
    if (targetSeg) {
      const targetTime = getStart(targetSeg) + 0.02;
      appState.setCurrentTime(targetTime, 'sentence_nav');
      appState.selectItem('segment', targetSeg.id, targetSeg);
      renderStep3LiveSignMonitor(targetTime);
    }
  }

  const btnStep3PrevSent = document.getElementById('btn-step3-prev-sentence');
  if (btnStep3PrevSent) {
    btnStep3PrevSent.addEventListener('click', () => stepSentenceInMonitor(-1));
  }

  const btnStep3NextSent = document.getElementById('btn-step3-next-sentence');
  if (btnStep3NextSent) {
    btnStep3NextSent.addEventListener('click', () => stepSentenceInMonitor(1));
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
      if (window.modalsController && typeof window.modalsController.openCompositeVideoExportDialog === 'function') {
        window.modalsController.openCompositeVideoExportDialog();
      } else if (window.modalsController && typeof window.modalsController.openExportModal === 'function') {
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
    if (!glossItem) return { label: '✓ Seña CONADIS', symbol: '✓', css: 'gloss-chip-conadis', badgeBg: '#047857' };
    const token = String(glossItem.gloss || glossItem.lemma || glossItem.text || glossItem || '').toUpperCase();
    const isManual = Boolean(
      glossItem.manually_edited ||
      glossItem.status === 'HUMAN_VERIFIED' ||
      glossItem.alignment_type === 'MANUAL_EDIT'
    );
    const isSingleLetterHyphenated = token.includes('-') && token.split('-').filter(Boolean).every(p => p.trim().length === 1);
    const isFingerspell = Boolean(
      glossItem.source === 'FINGERSPELLING' ||
      glossItem.is_fingerspelling ||
      glossItem.gloss_type === 'DACTILOLOGÍA' ||
      token.startsWith('FS:') ||
      isSingleLetterHyphenated
    );

    if (isManual) {
      return { label: '✎ Editada', symbol: '✎', css: 'gloss-chip-edited', badgeBg: '#b45309' };
    }
    if (isFingerspell) {
      return { label: '✦ Dactilología', symbol: '✦', css: 'gloss-chip-fingerspell', badgeBg: '#0369a1' };
    }
    return { label: '✓ Seña CONADIS', symbol: '✓', css: 'gloss-chip-conadis', badgeBg: '#047857' };
  }

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function cleanGlossDisplay(rawToken) {
    return String(rawToken || '')
      .toUpperCase()
      .replace(/^FS:/i, '')
      .replace(/\[[^\]]*\]/g, '')
      .trim();
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

    const getStart = (item) => Number(item?.start_time ?? item?.start_seconds ?? 0);
    const getEnd = (item) => Number(item?.end_time ?? item?.end_seconds ?? 0);

    const bridgeEntry = window.studioAvatarBridge?.lastSampleResult?.activeEntry || null;
    const activeGloss = (bridgeEntry && allGlosses.find(g => g.id === bridgeEntry.id || g.gloss === bridgeEntry.gloss && Math.abs(getStart(g) - bridgeEntry.slotStart) < 0.05))
      || allGlosses.find(g => t >= getStart(g) && t <= getEnd(g))
      || null;
    let activeSegIdx = segments.findIndex(s => t >= getStart(s) && t <= getEnd(s));
    if (activeSegIdx < 0 && activeGloss) {
      const propId = activeGloss.proposition_id || activeGloss.origin_proposition_id || activeGloss.segment_id;
      if (propId) activeSegIdx = segments.findIndex(s => s.id === propId);
    }
    if (activeSegIdx < 0) {
      for (let i = segments.length - 1; i >= 0; i--) {
        if (t >= getStart(segments[i])) { activeSegIdx = i; break; }
      }
    }
    const resolvedSegIdx = activeSegIdx >= 0 ? activeSegIdx : 0;
    const activeSeg = segments[resolvedSegIdx] || null;

    const sentBadgeEl = document.getElementById('live-monitor-sentence-badge');
    if (sentBadgeEl) {
      sentBadgeEl.textContent = segments.length > 0 ? `Oración #${resolvedSegIdx + 1} de ${segments.length}` : 'Sin oraciones';
    }

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
        ? (activeSeg.normalized_text || activeSeg.original_text || activeSeg.raw_text || 'Oración sin texto')
        : 'Reproduce el video o selecciona una oración.';
    }

    const rackEl = document.getElementById('live-sentence-gloss-rack');
    if (rackEl) {
      rackEl.innerHTML = '';
      const segGlosses = activeSeg
        ? allGlosses.filter(g =>
          g.segment_id === activeSeg.id ||
          g.proposition_id === activeSeg.id ||
          g.origin_proposition_id === activeSeg.id ||
          (getStart(g) >= getStart(activeSeg) - 0.15 && getEnd(g) <= getEnd(activeSeg) + 0.45)
        )
        : [];
      const itemsToRender = segGlosses.length > 0
        ? segGlosses
        : ((activeSeg?.gloss_sequence || []).map(tok => ({ gloss: tok })));

      itemsToRender.forEach((g) => {
        const info = classifyGlossSignType(g);
        const isExecuting = activeGloss && g.id && activeGloss.id === g.id;
        const cleanTok = cleanGlossDisplay(g.gloss || g.lemma || g);
        const chip = document.createElement('span');
        chip.className = `gloss-chip-tactile ${info.css}`;
        if (isExecuting) {
          chip.style.outline = '3px solid #0f172a';
        }
        chip.title = `${cleanTok} (${info.label}) — Clic para reproducir seña`;
        chip.innerHTML = `
          <span class="gloss-chip-symbol" aria-hidden="true">${info.symbol}</span>
          <span>${escapeHtml(cleanTok)}</span>
        `;
        chip.addEventListener('click', () => {
          const gStart = getStart(g);
          appState.setCurrentTime(gStart, true);
          if (window.avatarController && typeof window.avatarController.playGloss === 'function') {
            window.avatarController.playGloss(String(g.gloss || g));
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
        const segText = seg.normalized_text || seg.original_text || seg.raw_text || '';
        rowBtn.innerHTML = `<strong>#${i + 1}</strong> <span>${escapeHtml(segText.slice(0, 52))}</span>`;
        rowBtn.addEventListener('click', () => {
          const sTime = getStart(seg);
          appState.setCurrentTime(sTime, true);
          appState.selectItem('segment', seg.id, seg);
          renderStep3LiveSignMonitor(sTime);
        });
        listEl.appendChild(rowBtn);
      });
    }
  }

  // Atajos globales de teclado Undo / Redo (Ctrl+Z / Ctrl+Y)
  window.addEventListener('keydown', (e) => {
    const tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target?.isContentEditable) {
      return;
    }
    if ((e.ctrlKey || e.metaKey) && !e.altKey) {
      const key = String(e.key || '').toLowerCase();
      if (key === 'z' && !e.shiftKey) {
        e.preventDefault();
        if (typeof appState !== 'undefined' && typeof appState.undo === 'function') appState.undo();
      } else if (key === 'y' || (key === 'z' && e.shiftKey)) {
        e.preventDefault();
        if (typeof appState !== 'undefined' && typeof appState.redo === 'function') appState.redo();
      }
    }
  });

  // 7. Suscripciones de Sincronización en Segundo Plano
  if (typeof appState !== 'undefined') {
    appState.subscribe('timeChanged', (t) => {
      const stg = appState.state.workspace.stage;
      if (stg === 'avatar' || stg === 'revisar') {
        renderStep3LiveSignMonitor(t);
      }
    });

    appState.subscribe('projectLoaded', () => {
      const dropzone = document.getElementById('video-dropzone');
      const playerWrap = document.getElementById('video-player-wrapper');
      const changeVideoBtn = document.getElementById('btn-stage-change-video');
      if (dropzone) dropzone.style.display = 'none';
      if (playerWrap) playerWrap.classList.add('active');
      if (changeVideoBtn) {
        const stg = appState.state.workspace?.stage;
        changeVideoBtn.style.display = (stg === 'avatar' || stg === 'revisar') ? 'none' : 'inline-flex';
      }

      const listEl = document.getElementById('live-all-sentences-list');
      if (listEl) listEl.dataset.renderedCount = '';
      const titleEl = document.getElementById('project-title-display');
      const pName = appState.state.project?.title || appState.state.project?.project_name || appState.state.project?.media_info?.filename;
      if (titleEl && pName) {
        titleEl.textContent = pName;
      }
      if (window.transcriptWindow && typeof window.transcriptWindow.renderSegments === 'function') {
        window.transcriptWindow.renderSegments();
      }
      if (window.linguisticComparisonView && typeof window.linguisticComparisonView.renderAll === 'function') {
        window.linguisticComparisonView.renderAll();
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

  // Utilidad Global de Notificaciones Toast (WCAG 2.2 Criterio 4.1.3 Status Messages)
  window.showToast = function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    toast.setAttribute('aria-live', type === 'error' ? 'assertive' : 'polite');
    const prefix = type === 'error' ? '✗ [ERROR] ' : (type === 'warning' ? '⚠ [AVISO] ' : '✓ ');
    toast.textContent = `${prefix}${message}`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.remove();
    }, 3800);
  };
});
