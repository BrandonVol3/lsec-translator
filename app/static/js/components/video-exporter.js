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
    if (this.isAvatarLoaded && this.avatarImg.complete && this.avatarImg.naturalWidth > 0) {
      return true;
    }
    return new Promise((resolve) => {
      this.avatarImg.onload = () => {
        this.isAvatarLoaded = true;
        resolve(true);
      };
      this.avatarImg.onerror = () => {
        console.warn('No se pudo cargar avatar_ilustracion.png, se continuará con renderizado vectorial');
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

    // 3. Capturar Stream de Canvas y Audio
    const canvasStream = exportCanvas.captureStream(30);

    // Intentar capturar audio del video
    if (videoEl && typeof videoEl.captureStream === 'function') {
      try {
        const vStream = videoEl.captureStream();
        const audioTracks = vStream ? vStream.getAudioTracks() : [];
        if (audioTracks.length > 0) {
          canvasStream.addTrack(audioTracks[0]);
        }
      } catch (err) {
        console.warn('Captura directa de audio no soportada, continuando sin audio:', err);
      }
    }

    // 4. Inicializar MediaRecorder
    let mediaRecorder;
    try {
      mediaRecorder = new MediaRecorder(canvasStream, {
        mimeType: selectedMime,
        videoBitsPerSecond: 4500000 // 4.5 Mbps para alta definición
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

    mediaRecorder.onstop = () => {
      this.isExporting = false;
      if (this.isCancelled) {
        onProgress({ progress: 0, status: 'cancelled' });
        return;
      }

      const isMp4 = selectedMime.includes('mp4');
      const ext = isMp4 ? 'mp4' : 'webm';
      const baseFilename = (project.media_info && project.media_info.filename)
        ? project.media_info.filename.replace(/\.[^/.]+$/, '')
        : 'video_lsec';
      const outputFilename = `${baseFilename}_con_interprete_y_glosas.${ext}`;

      const blob = new Blob(this.recordedChunks, { type: selectedMime });
      onComplete(blob, outputFilename);
    };

    // 5. Guardar estado previo y preparar reproducción
    const previousTime = (window.appState && window.appState.state.playback.currentTime) || 0;
    const previousPlaybackRate = (videoEl && videoEl.playbackRate) || 1.0;
    const previousMuted = (videoEl && videoEl.muted) || false;

    if (window.appState && window.appState.state.playback.isPlaying) {
      window.appState.pause();
    }

    // Posición del PiP
    const pipPosition = options.pipPosition || 'bottom-right';
    const includeSubtitles = options.includeSubtitles !== false;
    const includeGlosses = options.includeGlosses !== false;
    const includeInterpreter = options.includeInterpreter !== false;
    const playbackSpeed = options.playbackSpeed || 1.0;

    // Colocar video en tiempo 0
    if (videoEl) {
      videoEl.currentTime = 0;
      videoEl.playbackRate = playbackSpeed;
    }

    // Esperar a que el video esté listo en tiempo 0
    await new Promise((res) => {
      if (!videoEl || videoEl.readyState >= 2) {
        setTimeout(res, 200);
      } else {
        videoEl.onseeked = () => {
          videoEl.onseeked = null;
          res();
        };
      }
    });

    // Iniciar grabación de stream
    mediaRecorder.start(250);

    if (videoEl) {
      try {
        await videoEl.play();
      } catch (e) {
        console.warn('Reproducción de video en exportador:', e);
      }
    }

    // 6. Ciclo de Renderizado Fotograma a Fotograma
    const segments = (window.appState && window.appState.state.project?.segments) || project.segments || [];
    const allGlosses = (window.appState && window.appState.state.project?.glosses) || project.glosses || [];

    const renderLoop = () => {
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

      const currentTime = (videoEl && !isNaN(videoEl.currentTime))
        ? videoEl.currentTime
        : (window.appState ? window.appState.state.playback.currentTime : 0);

      // Dibujar fotograma compuesto
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
          includeInterpreter
        }
      );

      // Reportar progreso
      const progress = Math.min(100, (currentTime / duration) * 100);
      onProgress({
        progress,
        currentTime,
        duration,
        exportCanvas,
        status: 'rendering'
      });

      // Verificar si finalizó el video
      const isFinished = (currentTime >= duration - 0.05) || (videoEl && videoEl.ended);

      if (isFinished) {
        if (videoEl) {
          videoEl.pause();
          videoEl.playbackRate = previousPlaybackRate;
          videoEl.muted = previousMuted;
        }
        if (mediaRecorder.state !== 'inactive') {
          mediaRecorder.stop();
        }
      } else {
        this.animFrameId = requestAnimationFrame(renderLoop);
      }
    };

    this.animFrameId = requestAnimationFrame(renderLoop);
  }

  /**
   * Cancela la exportación en progreso
   */
  cancelExport() {
    this.isCancelled = true;
    this.isExporting = false;
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
    // 1. Fondo base de video
    ctx.fillStyle = '#0a0c10';
    ctx.fillRect(0, 0, width, height);

    if (videoEl && videoEl.videoWidth > 0 && videoEl.readyState >= 2) {
      ctx.drawImage(videoEl, 0, 0, width, height);
    } else if (canvasFallback) {
      ctx.drawImage(canvasFallback, 0, 0, width, height);
    }

    // 2. Recuadro PiP del Intérprete y Glosas LSEC
    if (opts.includeInterpreter) {
      this.drawInterpreterPiPCard(ctx, width, height, currentTime, allGlosses, segments, opts);
    }

    // 3. Subtítulos en Español Sincronizados
    if (opts.includeSubtitles) {
      this.drawSubtitles(ctx, width, height, currentTime, segments);
    }
  }

  /**
   * Renderiza la tarjeta Picture-in-Picture del intérprete con su ilustración y glosas
   */
  drawInterpreterPiPCard(ctx, width, height, currentTime, allGlosses, segments, opts) {
    const cardWidth = Math.round(width * 0.23);
    const cardHeight = Math.round(cardWidth * 1.30);
    const margin = Math.round(width * 0.02);

    const isLeft = opts.pipPosition === 'bottom-left';
    const cardX = isLeft ? margin : (width - cardWidth - margin);
    const cardY = height - cardHeight - margin - Math.round(height * 0.02);
    const radius = 10;

    ctx.save();

    // Sombra exterior
    ctx.shadowColor = 'rgba(0, 0, 0, 0.75)';
    ctx.shadowBlur = 18;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 6;

    // Fondo degradado de la tarjeta
    ctx.beginPath();
    ctx.roundRect(cardX, cardY, cardWidth, cardHeight, radius);
    const bgGrad = ctx.createLinearGradient(cardX, cardY, cardX, cardY + cardHeight);
    bgGrad.addColorStop(0, 'rgba(24, 30, 42, 0.95)');
    bgGrad.addColorStop(1, 'rgba(10, 12, 16, 0.98)');
    ctx.fillStyle = bgGrad;
    ctx.fill();

    // Borde LSEC verde oliva característico
    ctx.shadowColor = 'transparent';
    ctx.strokeStyle = 'rgba(183, 211, 107, 0.45)';
    ctx.lineWidth = Math.max(1.5, Math.round(width * 0.0015));
    ctx.stroke();

    // Región de recorte para contenido interno
    ctx.clip();

    // Encabezado de la tarjeta
    const headerHeight = Math.round(cardHeight * 0.10);
    ctx.fillStyle = 'rgba(18, 22, 30, 0.95)';
    ctx.fillRect(cardX, cardY, cardWidth, headerHeight);

    // Línea divisoria del encabezado
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cardX, cardY + headerHeight);
    ctx.lineTo(cardX + cardWidth, cardY + headerHeight);
    ctx.stroke();

    // Punto indicador verde
    const dotRadius = Math.max(3, Math.round(cardWidth * 0.015));
    const dotX = cardX + Math.round(cardWidth * 0.05);
    const dotY = cardY + Math.round(headerHeight * 0.5);
    ctx.beginPath();
    ctx.arc(dotX, dotY, dotRadius, 0, Math.PI * 2);
    ctx.fillStyle = '#B7D36B';
    ctx.fill();

    // Título del encabezado
    ctx.font = `600 ${Math.round(cardHeight * 0.040)}px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`;
    ctx.fillStyle = '#F1F5F9';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText('Avatar 3D (LSEC)', dotX + dotRadius + 6, dotY);

    // Etiqueta "ILUSTRACIÓN"
    const tagText = 'Ilustración';
    ctx.font = `600 ${Math.round(cardHeight * 0.030)}px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`;
    const tagW = ctx.measureText(tagText).width + 8;
    const tagH = Math.round(headerHeight * 0.55);
    const tagX = cardX + cardWidth - tagW - Math.round(cardWidth * 0.04);
    const tagY = dotY - (tagH / 2);

    ctx.fillStyle = 'rgba(183, 211, 107, 0.18)';
    ctx.beginPath();
    ctx.roundRect(tagX, tagY, tagW, tagH, 3);
    ctx.fill();
    ctx.strokeStyle = 'rgba(183, 211, 107, 0.35)';
    ctx.stroke();

    ctx.fillStyle = '#B7D36B';
    ctx.textAlign = 'center';
    ctx.fillText(tagText, tagX + (tagW / 2), dotY);

    // Área central: Imagen del Avatar Intérprete
    const badgeHeight = opts.includeGlosses ? Math.round(cardHeight * 0.18) : 0;
    const imgAreaY = cardY + headerHeight;
    const imgAreaH = cardHeight - headerHeight - badgeHeight;

    if (this.isAvatarLoaded && this.avatarImg.naturalWidth > 0) {
      const imgRatio = this.avatarImg.naturalWidth / this.avatarImg.naturalHeight;
      let drawW = cardWidth * 0.95;
      let drawH = drawW / imgRatio;

      if (drawH > imgAreaH) {
        drawH = imgAreaH;
        drawW = drawH * imgRatio;
      }

      const drawX = cardX + (cardWidth - drawW) / 2;
      const drawY = imgAreaY + (imgAreaH - drawH) / 2;

      ctx.drawImage(this.avatarImg, drawX, drawY, drawW, drawH);
    }

    // Nota de marca de agua
    ctx.font = `500 ${Math.round(cardHeight * 0.028)}px monospace`;
    ctx.fillStyle = 'rgba(183, 211, 107, 0.45)';
    ctx.textAlign = 'center';
    ctx.fillText('ESPACIO PARA AVATAR 3D', cardX + (cardWidth / 2), imgAreaY + Math.round(imgAreaH * 0.08));

    // Badge inferior de Glosa LSEC Sincronizada
    if (opts.includeGlosses) {
      this.drawGlossBadge(ctx, cardX, cardY + cardHeight - badgeHeight - 6, cardWidth, badgeHeight, currentTime, allGlosses, segments);
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

    // Encontrar glosa activa
    let activeGloss = allGlosses.find(g => {
      const st = g.start_time !== undefined ? g.start_time : (g.start !== undefined ? g.start : 0);
      const et = g.end_time !== undefined ? g.end_time : (g.end !== undefined ? g.end : 0);
      return currentTime >= st && currentTime <= et;
    });

    // Fallback: interpolar desde el segmento activo
    if (!activeGloss && segments) {
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
      const glossName = (activeGloss.gloss || activeGloss.lemma || '').toUpperCase();
      const isFingerspelling = activeGloss.is_fingerspelling || glossName.includes('-') || (activeGloss.gloss_type === 'DACTILOLOGÍA');
      const isParaphrase = activeGloss.is_paraphrase || (activeGloss.type_badge === 'paráfrasis');
      
      let typeLabel = activeGloss.gloss_type || 'SEÑA LÉXICA';
      if (isFingerspelling) typeLabel = 'DACTILOLOGÍA';
      if (isParaphrase) typeLabel = 'PARÁFRASIS LSEC';

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
  drawSubtitles(ctx, width, height, currentTime, segments) {
    const segList = (window.appState && window.appState.state.project?.segments) || segments || [];
    const activeSeg = segList.find(s => {
      const st = s.start_seconds !== undefined ? s.start_seconds : (s.start_time || 0);
      const et = s.end_seconds !== undefined ? s.end_seconds : (s.end_time || 0);
      return currentTime >= st && currentTime <= et;
    });

    if (!activeSeg) return;

    const rawText = (activeSeg.normalized_text || activeSeg.original_text || activeSeg.text || '').trim();
    if (!rawText) return;

    const globalStyle = (window.appState && window.appState.state?.overlays?.subtitleStyle) || null;

    if (typeof SubtitleEngine !== 'undefined') {
      const effectiveStyle = SubtitleEngine.resolveEffectiveStyle(activeSeg, globalStyle);
      const layout = SubtitleEngine.calculateLayout(ctx, rawText, effectiveStyle, width, height);

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
