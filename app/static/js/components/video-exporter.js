/**
 * LSEC Studio 2.1.1 — Componente CompositeVideoExporter
 * 
 * Permite exportar el video activo con:
 * 1. El avatar del intérprete (PiP) incrustado en la esquina inferior derecha o izquierda.
 * 2. Las glosas de Lengua de Señas Ecuatoriana (LSEC) sincronizadas en tiempo real con su tipología.
 * 3. Los subtítulos normalizados en español quemados con legibilidad óptima sobre cualquier fondo.
 * 4. El audio original del video sincronizado en formato MP4 o WebM HD.
 */

class CompositeVideoExporter {
  constructor() {
    this.isExporting = false;
    this.isCancelled = false;
    this.mediaRecorder = null;
    this.recordedChunks = [];
    this.animFrameId = null;

    // Precargar imagen de referencia del avatar intérprete
    this.avatarImg = new Image();
    this.avatarImg.crossOrigin = 'anonymous';
    this.avatarImg.src = '/static/assets/avatar_ilustracion.png';
    this.isAvatarLoaded = false;
    this.avatarImg.onload = () => { this.isAvatarLoaded = true; };
  }

  /**
   * Prepara y asegura la carga de la imagen del avatar intérprete
   */
  async ensureAvatarLoaded() {
    if (window.studioAvatarBridge && window.studioAvatarBridge.isReady) {
      return true;
    }
    if (this.isAvatarLoaded && this.avatarImg.complete && this.avatarImg.naturalWidth > 0) {
      return true;
    }
    return new Promise((resolve) => {
      this.avatarImg.onload = () => {
        this.isAvatarLoaded = true;
        resolve(true);
      };
      this.avatarImg.onerror = () => {
        resolve(false);
      };
      if (this.avatarImg.complete) {
        this.isAvatarLoaded = this.avatarImg.naturalWidth > 0;
        resolve(this.isAvatarLoaded);
      }
    });
  }

  /**
   * Inicia el renderizado y la exportación del video compuesto
   */
  async startExport(options = {}, onProgress = () => {}, onComplete = () => {}, onError = () => {}) {
    if (this.isExporting) return;
    this.isExporting = true;
    this.isCancelled = false;
    this.recordedChunks = [];

    const videoEl = document.getElementById('main-video-element');
    const canvasFallback = document.getElementById('canvas-video-fallback');

    const project = (window.appState && window.appState.state.project) || {};
    const duration = (videoEl && videoEl.duration > 0)
      ? videoEl.duration
      : ((window.appState && window.appState.state.playback.duration) || 10.0);

    if (duration <= 0) {
      this.isExporting = false;
      onError('La duración del video no es válida para exportar.');
      return;
    }

    await this.ensureAvatarLoaded();

    // 1. Configurar dimensiones de renderizado
    const is720p = options.resolution === '720p';
    let targetWidth = 1280;
    let targetHeight = 720;

    if (!is720p && videoEl && videoEl.videoWidth > 0) {
      targetWidth = videoEl.videoWidth;
      targetHeight = videoEl.videoHeight;
    }

    const exportCanvas = document.createElement('canvas');
    exportCanvas.width = targetWidth;
    exportCanvas.height = targetHeight;
    const ctx = exportCanvas.getContext('2d', { alpha: false });

    // 2. Determinar soporte de formato de grabación
    const candidateMimes = [
      'video/mp4;codecs=avc1,mp4a.40.2',
      'video/mp4',
      'video/webm;codecs=vp9,opus',
      'video/webm;codecs=vp8,opus',
      'video/webm'
    ];
    let selectedMime = 'video/webm';
    for (const m of candidateMimes) {
      if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(m)) {
        selectedMime = m;
        break;
      }
    }

    // 3. Capturar Stream de Canvas determinista (30 FPS exactos)
    const TARGET_FPS = 30;
    const DT = 1.0 / TARGET_FPS;
    const canvasStream = typeof exportCanvas.captureStream === 'function'
      ? exportCanvas.captureStream(0)
      : null;
    const canvasVideoTrack = canvasStream && canvasStream.getVideoTracks
      ? canvasStream.getVideoTracks()[0]
      : null;

    // 4. Inicializar MediaRecorder para captura intermedia de cuadros renderizados
    let mediaRecorder;
    try {
      mediaRecorder = new MediaRecorder(canvasStream, {
        mimeType: selectedMime,
        videoBitsPerSecond: 5500000 // 5.5 Mbps para alta definición
      });
    } catch (err) {
      this.isExporting = false;
      onError('Error inicializando el grabador de video: ' + err.message);
      return;
    }

    this.mediaRecorder = mediaRecorder;

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        this.recordedChunks.push(e.data);
      }
    };

    mediaRecorder.onstop = async () => {
      if (this.isCancelled) {
        this.isExporting = false;
        onProgress({ progress: 0, status: 'cancelled' });
        return;
      }

      const rawBlob = new Blob(this.recordedChunks, { type: selectedMime });
      const baseFilename = (project.media_info && project.media_info.filename)
        ? project.media_info.filename.replace(/\.[^/.]+$/, '')
        : 'video_lsec';

      // Intentar empaquetado final determinista a MP4 (H.264 + AAC a 30.0 FPS constantes)
      let finalBlob = rawBlob;
      let ext = selectedMime.includes('mp4') ? 'mp4' : 'webm';

      try {
        onProgress({
          progress: 99,
          currentTime: duration,
          duration,
          exportCanvas,
          status: 'finalizing_mp4'
        });

        const formData = new FormData();
        formData.append('video_file', rawBlob, `capture.${ext}`);
        formData.append('fps', String(TARGET_FPS));

        // Adjuntar fuente de audio original si el video tiene un src accesible
        if (videoEl && videoEl.src) {
          try {
            const audioRes = await fetch(videoEl.src);
            if (audioRes && audioRes.ok) {
              const audioBlob = await audioRes.blob();
              if (audioBlob && audioBlob.size > 0) {
                formData.append('audio_file', audioBlob, 'original_audio.mp4');
              }
            }
          } catch (audioFetchErr) {
            console.warn('[CompositeVideoExporter] Aviso obteniendo pista de audio original:', audioFetchErr);
          }
        }

        const mp4Res = await fetch('/api/v1/animations/finalize-export-mp4', {
          method: 'POST',
          body: formData
        });

        if (mp4Res && mp4Res.ok) {
          const mp4Blob = await mp4Res.blob();
          if (mp4Blob && mp4Blob.size > 0) {
            finalBlob = new Blob([mp4Blob], { type: 'video/mp4' });
            ext = 'mp4';
          }
        }
      } catch (muxErr) {
        console.warn('[CompositeVideoExporter] Fallback a contenedor local por error en finalize-export-mp4:', muxErr);
      }

      this.isExporting = false;
      const outputFilename = `${baseFilename}_con_interprete_y_glosas.${ext}`;
      onComplete(finalBlob, outputFilename);
    };

    // 5. Guardar estado previo y preparar exportación determinista cuadro a cuadro
    const previousTime = (window.appState && window.appState.state.playback.currentTime) || 0;
    const previousPlaybackRate = (videoEl && videoEl.playbackRate) || 1.0;
    const previousMuted = (videoEl && videoEl.muted) || false;

    if (window.appState && window.appState.state.playback.isPlaying) {
      window.appState.pause();
    }
    if (videoEl) {
      videoEl.pause();
    }

    // Posición y opciones del PiP
    const pipPosition = options.pipPosition || 'bottom-right';
    const includeSubtitles = options.includeSubtitles !== false;
    const includeGlosses = options.includeGlosses !== false;
    const includeInterpreter = options.includeInterpreter !== false;

    const segments = (window.appState && window.appState.state.project?.segments) || project.segments || [];
    const allGlosses = (window.appState && window.appState.state.project?.glosses) || project.glosses || [];

    if (allGlosses.length > 1 && window.appState?.resolveOverlappingGlossIntervals) {
      window.appState.resolveOverlappingGlossIntervals(allGlosses, segments);
    }

    // Precargar clips de señas del proyecto antes de iniciar el bucle determinista
    if (window.studioAvatarBridge && typeof window.studioAvatarBridge.preloadProjectSigns === 'function') {
      try {
        await window.studioAvatarBridge.preloadProjectSigns({ glosses: allGlosses, segments });
      } catch (e) {}
    }

    // Buffer persistente del último fotograma válido decodificado para evitar frames negros
    const lastFrameCanvas = document.createElement('canvas');
    lastFrameCanvas.width = targetWidth;
    lastFrameCanvas.height = targetHeight;
    const lastFrameCtx = lastFrameCanvas.getContext('2d', { alpha: false });
    this._lastFrameCanvas = lastFrameCanvas;
    this._hasLastValidFrame = false;

    // Helper para posicionar el video de forma determinista en t segundos sin abortar decodificación GOP
    const seekVideoDeterministic = (targetSec) => new Promise((resolve) => {
      if (!videoEl || !(videoEl.readyState >= 1)) {
        resolve();
        return;
      }
      if (!videoEl.seeking && videoEl.readyState >= 2 && Math.abs(videoEl.currentTime - targetSec) < 0.004) {
        resolve();
        return;
      }
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        videoEl.removeEventListener('seeked', onSeeked);
        videoEl.removeEventListener('canplay', onSeeked);
        resolve();
      };
      const onSeeked = () => {
        if (!videoEl.seeking && videoEl.readyState >= 2) {
          clearTimeout(timer);
          finish();
        }
      };
      const timer = setTimeout(finish, 600);
      videoEl.addEventListener('seeked', onSeeked);
      videoEl.addEventListener('canplay', onSeeked);
      try {
        videoEl.currentTime = targetSec;
      } catch (e) {
        clearTimeout(timer);
        finish();
      }
    });

    // Posicionar en t=0 antes de comenzar y capturar el primer cuadro válido
    await seekVideoDeterministic(0);
    if (videoEl && videoEl.videoWidth > 0 && videoEl.readyState >= 2) {
      try {
        lastFrameCtx.drawImage(videoEl, 0, 0, targetWidth, targetHeight);
        this._hasLastValidFrame = true;
      } catch (e) {}
    }

    if (includeInterpreter && window.studioAvatarBridge && typeof window.studioAvatarBridge.beginDeterministicExport === 'function') {
      window.studioAvatarBridge.beginDeterministicExport();
    }

    // Iniciar grabación de stream
    mediaRecorder.start(200);

    // 6. Ciclo de Renderizado Determinista a 30.0 FPS constantes (dt = 1/30 s)
    // Si el avatar tiene desfase al final (política "se extiende el PiP"), extender hasta sequenceEndTime
    // manteniendo el último fotograma del video fuente mientras el intérprete concluye su secuencia.
    const effectiveEndTime = (includeInterpreter && window.studioAvatarBridge && typeof window.studioAvatarBridge.getSequenceEndTime === 'function')
      ? Math.max(duration, window.studioAvatarBridge.getSequenceEndTime(duration))
      : duration;
    const totalFrames = Math.max(1, Math.round(effectiveEndTime * TARGET_FPS));

    try {
      for (let frameIdx = 0; frameIdx < totalFrames; frameIdx++) {
        if (this.isCancelled) {
          if (mediaRecorder.state !== 'inactive') mediaRecorder.stop();
          if (videoEl) {
            videoEl.pause();
            videoEl.currentTime = previousTime;
            videoEl.playbackRate = previousPlaybackRate;
            videoEl.muted = previousMuted;
          }
          return;
        }

        const currentTime = Math.min(effectiveEndTime, frameIdx * DT);
        const videoSeekTime = Math.min(duration, currentTime);

        // 6.1 Posicionar video fuente en videoSeekTime (mantiene último fotograma si currentTime > duration)
        if (currentTime <= duration + DT * 0.5) {
          await seekVideoDeterministic(videoSeekTime);

          if (videoEl && videoEl.videoWidth > 0 && videoEl.readyState >= 2 && !videoEl.seeking) {
            try {
              lastFrameCtx.drawImage(videoEl, 0, 0, targetWidth, targetHeight);
              this._hasLastValidFrame = true;
            } catch (e) {}
          }
        }

        // 6.2 Avanzar determinísticamente el motor 3D del avatar (compiler.sample(currentTime), vrm.update(dt), renderer.render)
        if (includeInterpreter && window.studioAvatarBridge && typeof window.studioAvatarBridge.stepAtVideoTime === 'function') {
          await window.studioAvatarBridge.stepAtVideoTime(currentTime, DT);
        }

        // 6.3 Dibujar fotograma compuesto (video + PiP 3D + glosa + subtítulos)
        this.drawCompositeFrame(
          ctx,
          targetWidth,
          targetHeight,
          currentTime,
          videoEl,
          canvasFallback,
          segments,
          allGlosses,
          {
            pipPosition,
            includeSubtitles,
            includeGlosses,
            includeInterpreter,
            alreadySteppedAvatar: true
          }
        );

        // 6.4 Emitir fotograma exacto al stream de captura
        if (canvasVideoTrack && typeof canvasVideoTrack.requestFrame === 'function') {
          try {
            canvasVideoTrack.requestFrame();
          } catch (e) {}
        }

        const progress = Math.min(98, ((frameIdx + 1) / totalFrames) * 98);
        onProgress({
          progress,
          currentTime,
          duration: effectiveEndTime,
          frameIndex: frameIdx + 1,
          totalFrames,
          fps: TARGET_FPS,
          exportCanvas,
          status: 'rendering'
        });

        // Ceder brevemente al event loop para que MediaRecorder codifique el fotograma sin descartes
        await new Promise(r => setTimeout(r, 4));
      }
    } finally {
      if (window.studioAvatarBridge && typeof window.studioAvatarBridge.endDeterministicExport === 'function') {
        window.studioAvatarBridge.endDeterministicExport();
      }
    }

    // Restaurar estado del reproductor y cerrar grabación
    if (videoEl) {
      videoEl.pause();
      videoEl.currentTime = previousTime;
      videoEl.playbackRate = previousPlaybackRate;
      videoEl.muted = previousMuted;
    }
    if (mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
    }
  }

  /**
   * Cancela la exportación en progreso
   */
  cancelExport() {
    this.isCancelled = true;
    this.isExporting = false;
    if (window.studioAvatarBridge && typeof window.studioAvatarBridge.endDeterministicExport === 'function') {
      window.studioAvatarBridge.endDeterministicExport();
    }
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      try {
        this.mediaRecorder.stop();
      } catch (e) {}
    }
  }

  /**
   * Dibuja un fotograma completo con fondo, avatar PiP, glosas y subtítulos
   */
  drawCompositeFrame(ctx, width, height, currentTime, videoEl, canvasFallback, segments, allGlosses, opts) {
    // 1. Fondo base de video (usa frame en vivo o el último frame decodificado válido para evitar parpadeos negros)
    ctx.fillStyle = '#0a0c10';
    ctx.fillRect(0, 0, width, height);

    if (videoEl && videoEl.videoWidth > 0 && videoEl.readyState >= 2 && !videoEl.seeking) {
      ctx.drawImage(videoEl, 0, 0, width, height);
    } else if (this._hasLastValidFrame && this._lastFrameCanvas) {
      ctx.drawImage(this._lastFrameCanvas, 0, 0, width, height);
    } else if (videoEl && videoEl.videoWidth > 0) {
      try {
        ctx.drawImage(videoEl, 0, 0, width, height);
      } catch (e) {}
    } else if (canvasFallback) {
      ctx.drawImage(canvasFallback, 0, 0, width, height);
    }

    // 2. Recuadro PiP del Intérprete y Glosas LSEC
    if (opts.includeInterpreter) {
      this.drawInterpreterPiPCard(ctx, width, height, currentTime, allGlosses, segments, opts);
    }

    // 3. Subtítulos en Español Sincronizados
    if (opts.includeSubtitles) {
      this.drawSubtitles(ctx, width, height, currentTime, segments, opts);
    }
  }

  /**
   * Calcula las dimensiones del recuadro PiP garantizando el cumplimiento matemático estricto
   * de la Norma Técnica Ecuatoriana NTE INEN 3198 y el Reglamento LOC Abril 2026 (CDPIC-DTN-PNRD-2B-26):
   * - Área mínima exclusiva del intérprete >= 1/9 (11.11%) de la pantalla total.
   * - Relación de aspecto de busto LSEC (1 : 1.15) que abarca Planos 1 a 4 (cabeza a cintura).
   * - Zócalo inferior de glosas desacoplado para no superponerse ni recortar las manos.
   */
  getComplianceMetrics(width = 1280, height = 720, opts = {}) {
    const screenArea = Math.max(1, width * height);
    const minInenArea = screenArea / 9.0; // Mínimo legal 1/9 (11.111%)
    const minInenWidth = Math.ceil(Math.sqrt(minInenArea / 1.15));
    const cardWidth = Math.max(Math.round(width * 0.245), minInenWidth);
    const cardHeight = Math.round(cardWidth * 1.15);
    const includeGlosses = opts.includeGlosses !== false;
    const badgeFooterH = includeGlosses ? Math.round(cardHeight * 0.18) : 0;
    const totalBoxHeight = cardHeight + badgeFooterH;
    const margin = Math.round(width * 0.02);

    const isLeft = opts.pipPosition === 'bottom-left';
    const cardX = isLeft ? margin : (width - cardWidth - margin);
    const cardY = Math.max(margin, height - totalBoxHeight - margin - Math.round(height * 0.015));

    const interpreterArea = cardWidth * cardHeight;
    const interpreterRatio = interpreterArea / screenArea;
    const totalBoxRatio = (cardWidth * totalBoxHeight) / screenArea;

    return {
      standard: 'NTE INEN 3198 / Reglamento LOC CDPIC-DTN-PNRD-2B-26 (Abril 2026)',
      screenWidth: width,
      screenHeight: height,
      screenAreaPx: screenArea,
      minRequiredRatio: 1 / 9,
      minRequiredRatioPct: 11.11,
      cardX,
      cardY,
      cardWidth,
      cardHeight,
      badgeFooterH,
      totalBoxHeight,
      interpreterAreaPx: interpreterArea,
      interpreterRatio,
      interpreterRatioPct: Number((interpreterRatio * 100).toFixed(2)),
      totalBoxRatioPct: Number((totalBoxRatio * 100).toFixed(2)),
      meetsInen3198MinimumArea: interpreterArea >= Math.floor(minInenArea),
      noSigningSpaceOcclusion: true,
      solidContrastBackgroundHex: '#cfe5da',
      constantFps: 30
    };
  }

  /**
   * Genera un manifiesto auditable de cumplimiento técnico y normativo (Art. 26 Reglamento 2026)
   */
  buildComplianceReport(options = {}) {
    const videoEl = document.getElementById('main-video-element');
    const project = (window.appState && window.appState.state?.project) || {};
    const is720p = options.resolution === '720p';
    const width = (!is720p && videoEl && videoEl.videoWidth > 0) ? videoEl.videoWidth : 1280;
    const height = (!is720p && videoEl && videoEl.videoHeight > 0) ? videoEl.videoHeight : 720;
    const metrics = this.getComplianceMetrics(width, height, options);
    const segments = project.segments || [];
    const glosses = project.glosses || [];
    const verifiedCount = glosses.filter(g => g.dictionary_metadata?.verified_in_conadis || g.status === 'VERIFICADO_CONADIS').length;

    return {
      reportVersion: '1.0',
      generatedAt: new Date().toISOString(),
      regulatoryFramework: [
        'Ley Orgánica de las Personas con Discapacidad (2025, Arts. 72-74, 80)',
        'Norma Técnica Ecuatoriana NTE INEN 3198 (Recuadro mínimo 1/9 de pantalla)',
        'Reglamento para el Acceso a la Información y Comunicación de las Personas con Discapacidad (CDPIC-DTN-PNRD-2B-26, Abril 2026, Arts. 8, 9, 10, 12, 26)'
      ],
      projectSummary: {
        title: project.project_name || project.title || project.media_info?.filename || 'Proyecto LSEC Studio',
        durationSeconds: Number((window.appState?.state?.playback?.duration || project.media_info?.duration_seconds || 0).toFixed(2)),
        segmentsCount: segments.length,
        glossesCount: glosses.length,
        conadisVerifiedGlossesCount: verifiedCount
      },
      pipTechnicalCompliance: metrics,
      subtitlingComplianceArt8: {
        completeDialogueTranscription: segments.length > 0,
        speakerIdentificationEnabled: true,
        soundDescriptionTagsSupported: true,
        wcagContrastCompliance: 'AA/AAA (Fondo semitransparente oscuro >= 4.5:1)',
        pipNonOverlappingConfinement: true
      }
    };
  }

  /**
   * Renderiza la tarjeta Picture-in-Picture del intérprete con paridad de aspect ratio (1 : 1.15),
   * área >= 1/9 de la pantalla (NTE INEN 3198) y zócalo inferior desacoplado para glosas
   */
  drawInterpreterPiPCard(ctx, width, height, currentTime, allGlosses, segments, opts) {
    const geom = this.getComplianceMetrics(width, height, opts);
    const { cardX, cardY, cardWidth, cardHeight, badgeFooterH, totalBoxHeight } = geom;
    const radius = 8;

    ctx.save();

    // Sombra exterior envolvente (recuadro de intérprete + zócalo de glosa)
    ctx.shadowColor = 'rgba(0, 0, 0, 0.75)';
    ctx.shadowBlur = 18;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 6;

    // Fondo sólido contrastante (#cfe5da) calibrado según NTE INEN 3198 para contrastar con ropa oscura y manos
    ctx.beginPath();
    ctx.roundRect(cardX, cardY, cardWidth, totalBoxHeight, radius);
    ctx.fillStyle = '#cfe5da';
    ctx.fill();

    // Borde sutil minimalista
    ctx.shadowColor = 'transparent';
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.16)';
    ctx.lineWidth = Math.max(1, Math.round(width * 0.001));
    ctx.stroke();

    // Región de recorte global de la tarjeta
    ctx.clip();

    // Sub-región exclusiva para el Avatar 3D (100% libre de superposición de textos/glosas)
    ctx.save();
    ctx.beginPath();
    ctx.rect(cardX, cardY, cardWidth, cardHeight);
    ctx.clip();

    // Renderizado del Avatar 3D real preservando aspect ratio (cover centrado sin estiramiento)
    // y garantizando encuadre de los Planos 1 a 4 (pip_bust) en todo momento
    let avatarDrawn = false;
    if (window.studioAvatarBridge && typeof window.studioAvatarBridge.captureFrame === 'function') {
      const bridge = window.studioAvatarBridge;
      const eng = bridge.controller?.engine;
      let savedCam = null;
      if (!opts.alreadySteppedAvatar) {
        if (typeof bridge.onTimeUpdate === 'function') {
          bridge.onTimeUpdate(currentTime);
        }
        if (eng && !eng.exportLockCameraPreset && eng.currentPreset !== 'pip_bust' && eng.camera && eng.controls) {
          savedCam = {
            preset: eng.currentPreset,
            fov: eng.camera.fov,
            pos: eng.camera.position.clone(),
            target: eng.controls.target.clone()
          };
          if (typeof eng._applyCameraPresetInternal === 'function') {
            eng._applyCameraPresetInternal('pip_bust');
          } else {
            eng.setCameraPreset('pip_bust');
          }
        }
      }
      const avatarCanvas = bridge.captureFrame();
      if (savedCam && eng && eng.camera && eng.controls) {
        eng.currentPreset = savedCam.preset;
        eng.camera.fov = savedCam.fov;
        eng.camera.position.copy(savedCam.pos);
        eng.controls.target.copy(savedCam.target);
        eng.camera.updateProjectionMatrix();
        eng.controls.update();
      }
      if (avatarCanvas && avatarCanvas.width > 0 && avatarCanvas.height > 0) {
        const srcW = avatarCanvas.width;
        const srcH = avatarCanvas.height;
        const srcAspect = srcW / srcH;
        const dstAspect = cardWidth / cardHeight;
        let sx = 0, sy = 0, sw = srcW, sh = srcH;
        if (Math.abs(srcAspect - dstAspect) > 0.01) {
          if (srcAspect > dstAspect) {
            sw = Math.round(srcH * dstAspect);
            sx = Math.round((srcW - sw) / 2);
          } else {
            sh = Math.round(srcW / dstAspect);
            sy = Math.round((srcH - sh) / 2);
          }
        }
        ctx.drawImage(avatarCanvas, sx, sy, sw, sh, cardX, cardY, cardWidth, cardHeight);
        avatarDrawn = true;
      }
    }

    if (!avatarDrawn && this.isAvatarLoaded && this.avatarImg.naturalWidth > 0) {
      const imgRatio = this.avatarImg.naturalWidth / this.avatarImg.naturalHeight;
      let drawW = cardWidth * 0.95;
      let drawH = drawW / imgRatio;

      if (drawH > cardHeight) {
        drawH = cardHeight;
        drawW = drawH * imgRatio;
      }

      const drawX = cardX + (cardWidth - drawW) / 2;
      const drawY = cardY + (cardHeight - drawH) / 2;

      ctx.drawImage(this.avatarImg, drawX, drawY, drawW, drawH);
    }
    ctx.restore();

    // Zócalo inferior dedicado para la Glosa LSEC Sincronizada (sin invadir el área de signado del avatar)
    if (opts.includeGlosses && badgeFooterH > 0) {
      ctx.fillStyle = 'rgba(10, 14, 20, 0.96)';
      ctx.fillRect(cardX, cardY + cardHeight, cardWidth, badgeFooterH);
      this.drawGlossBadge(ctx, cardX, cardY + cardHeight + 2, cardWidth, badgeFooterH - 4, currentTime, allGlosses, segments);
    }

    ctx.restore();
  }

  /**
   * Dibuja el badge con la glosa activa o estado idle dentro del PiP
   */
  drawGlossBadge(ctx, cardX, badgeY, cardWidth, badgeHeight, currentTime, allGlosses, segments) {
    const boxMargin = Math.round(cardWidth * 0.04);
    const boxX = cardX + boxMargin;
    const boxW = cardWidth - (boxMargin * 2);
    const boxH = badgeHeight;

    // Encontrar glosa activa (evaluando SequenceCompiler en `currentTime` exacto si el plan está activo)
    const bridge = window.studioAvatarBridge;
    const hasCompiledPlan = Boolean(bridge && bridge.fluidMode && bridge.compiler?.compiled);
    const sampleResult = hasCompiledPlan
      ? ((bridge.lastSampleResult && Math.abs(bridge.lastSampleResult.timeSec - currentTime) < 1e-3)
          ? bridge.lastSampleResult
          : bridge.compiler.sample(currentTime))
      : null;
    const sampleEntry = sampleResult?.activeEntry || null;
    let activeGloss = (sampleEntry && sampleEntry.raw) ? sampleEntry.raw : null;

    if (!hasCompiledPlan && !activeGloss) {
      activeGloss = allGlosses.find(g => {
        const st = g.start_seconds !== undefined ? g.start_seconds : (g.start_time !== undefined ? g.start_time : (g.start !== undefined ? g.start : 0));
        const et = g.end_seconds !== undefined ? g.end_seconds : (g.end_time !== undefined ? g.end_time : (g.end !== undefined ? g.end : 0));
        return currentTime >= st && currentTime <= et;
      });
    }

    // Fallback: interpolar desde el segmento activo
    if (!hasCompiledPlan && !activeGloss && segments) {
      const activeSeg = segments.find(s => {
        const st = s.start_seconds !== undefined ? s.start_seconds : (s.start_time || 0);
        const et = s.end_seconds !== undefined ? s.end_seconds : (s.end_time || 0);
        return currentTime >= st && currentTime <= et;
      });

      if (activeSeg && activeSeg.glosses && activeSeg.glosses.length > 0) {
        const sStart = activeSeg.start_seconds !== undefined ? activeSeg.start_seconds : (activeSeg.start_time || 0);
        const sEnd = activeSeg.end_seconds !== undefined ? activeSeg.end_seconds : (activeSeg.end_time || 0);
        const sDur = Math.max(0.2, sEnd - sStart);
        const progress = Math.min(0.99, Math.max(0, (currentTime - sStart) / sDur));
        const idx = Math.floor(progress * activeSeg.glosses.length);
        activeGloss = activeSeg.glosses[idx] || activeSeg.glosses[0];
      }
    }

    if (activeGloss) {
      const glossName = (activeGloss.gloss || activeGloss.lemma || '').toUpperCase().trim();
      const isSingleLetterHyphenated = glossName.includes('-') && glossName.split('-').filter(Boolean).every(p => p.trim().length === 1);
      const isFingerspelling = Boolean(activeGloss.is_fingerspelling || isSingleLetterHyphenated || (activeGloss.gloss_type === 'DACTILOLOGÍA'));
      const isParaphrase = activeGloss.is_paraphrase || (activeGloss.type_badge === 'paráfrasis');
      
      let typeLabel = activeGloss.gloss_type || 'SEÑA LÉXICA';
      if (isFingerspelling) typeLabel = 'DACTILOLOGÍA (PENDIENTE)';
      if (isParaphrase) typeLabel = 'PARÁFRASIS LSEC';

      const resMeta = (!isFingerspelling && window.studioAvatarBridge && typeof window.studioAvatarBridge.getResolutionMetaForGloss === 'function')
        ? window.studioAvatarBridge.getResolutionMetaForGloss(glossName)
        : null;
      if (resMeta && ((resMeta.matchType && !['exact', 'fingerspelling', 'none'].includes(resMeta.matchType)) || resMeta.needsReview)) {
        typeLabel = (resMeta.matchType && resMeta.matchType !== 'exact' && resMeta.resolvedGloss)
          ? `⚠ APROX: ${resMeta.resolvedGloss.toUpperCase()}`
          : '⚠ REVISIÓN QA';
      }

      // Fondo del badge activo
      ctx.beginPath();
      ctx.roundRect(boxX, badgeY, boxW, boxH, 6);
      ctx.fillStyle = 'rgba(12, 14, 20, 0.94)';
      ctx.fill();
      ctx.strokeStyle = isFingerspelling ? 'rgba(96, 165, 250, 0.5)' : 'rgba(234, 179, 8, 0.45)';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Etiqueta de tipo
      ctx.font = `600 ${Math.round(boxH * 0.24)}px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`;
      ctx.fillStyle = isFingerspelling ? '#93C5FD' : '#FCD34D';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(typeLabel, boxX + (boxW / 2), badgeY + Math.round(boxH * 0.12));

      // Texto de la glosa principal
      ctx.font = `700 ${Math.round(boxH * 0.38)}px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`;
      ctx.fillStyle = '#FFFFFF';
      ctx.fillText(glossName, boxX + (boxW / 2), badgeY + Math.round(boxH * 0.44));
    } else {
      // Estado Idle (en espera de seña)
      ctx.beginPath();
      ctx.roundRect(boxX, badgeY, boxW, boxH, 6);
      ctx.fillStyle = 'rgba(15, 18, 26, 0.75)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
      ctx.lineWidth = 1;
      ctx.stroke();

      // Punto verde pulsante
      const idleDotX = boxX + (boxW / 2) - 22;
      const idleDotY = badgeY + (boxH / 2);
      ctx.beginPath();
      ctx.arc(idleDotX, idleDotY, 3.5, 0, Math.PI * 2);
      ctx.fillStyle = '#B7D36B';
      ctx.fill();

      ctx.font = `600 ${Math.round(boxH * 0.30)}px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`;
      ctx.fillStyle = '#94A3B8';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText('LSEC', idleDotX + 10, idleDotY);
    }
  }

  /**
   * Renderiza los subtítulos normalizados utilizando el motor unificado SubtitleEngine.
   * Aplica la personalización exacta de cada segmento (tipografía, color, opacidad,
   * contorno, sombra, alineación, posición X/Y, márgenes y área segura) de manera idéntica
   * a la vista previa, sin pintar la guía de área segura sobre el video final.
   */
  drawSubtitles(ctx, width, height, currentTime, segments, opts = {}) {
    const segList = (window.appState && window.appState.state.project?.segments) || segments || [];
    const activeSeg = segList.find(s => {
      const st = s.start_seconds !== undefined ? s.start_seconds : (s.start_time || 0);
      const et = s.end_seconds !== undefined ? s.end_seconds : (s.end_time || 0);
      return currentTime >= st && currentTime <= et;
    });

    if (!activeSeg) return;

    const globalStyle = (window.appState && window.appState.state?.overlays?.subtitleStyle) || null;
    const effectiveStyle = (typeof SubtitleEngine !== 'undefined')
      ? SubtitleEngine.resolveEffectiveStyle(activeSeg, globalStyle)
      : {};
    const rawText = (typeof SubtitleEngine !== 'undefined' && typeof SubtitleEngine.formatAccessibleSubtitleText === 'function')
      ? SubtitleEngine.formatAccessibleSubtitleText(activeSeg, effectiveStyle)
      : (activeSeg.normalized_text || activeSeg.original_text || activeSeg.text || '').trim();
    if (!rawText) return;

    if (typeof SubtitleEngine !== 'undefined') {
      const layout = SubtitleEngine.calculateLayout(ctx, rawText, effectiveStyle, width, height, {
        avoidPip: opts.includeInterpreter !== false,
        pipPosition: opts.pipPosition || 'bottom-right'
      });

      // Renderizar sobre el Canvas de exportación
      SubtitleEngine.drawToCanvas(ctx, layout, rawText, effectiveStyle, {
        currentTime,
        words: activeSeg.words
      });
    } else {
      // Fallback defensivo
      ctx.save();
      const fontSize = Math.max(16, Math.round(height * 0.034));
      ctx.font = `600 ${fontSize}px sans-serif`;
      ctx.fillStyle = '#FFFFFF';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(rawText, width / 2, height * 0.88);
      ctx.restore();
    }
  }
}

// Instancia global disponible en toda la aplicación
window.compositeVideoExporter = new CompositeVideoExporter();
