/**
 * LSEC Studio — Componente VideoPlayer
 * 
 * Controlador de reproducción de video de alta precisión sincronizado a 60fps.
 * Soporta video real HTML5 (<video>), fallback Canvas con audio sintetizado,
 * controles de paso por fotograma (step frame ~33ms), rango de bucle (In/Out),
 * amplificación de audio (+6/+12dB) y barra de progreso con marcadores interactivos.
 */

class VideoPlayerController {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.videoEl = document.getElementById('main-video-element');
    this.canvasEl = document.getElementById('canvas-video-fallback');
    this.canvasCtx = this.canvasEl ? this.canvasEl.getContext('2d') : null;
    
    this.isUsingCanvasFallback = true; // Si no hay video físico cargado, usa animación Canvas rica
    this.animFrameId = null;
    this.audioContext = null;
    this.gainNode = null;

    this.initElements();
    this.bindEvents();
    this.subscribeState();
  }

  initElements() {
    this.progressBar = document.getElementById('video-progress-bar');
    this.progressFill = document.getElementById('progress-fill');
    this.progressPlayhead = document.getElementById('progress-playhead');
    this.markersContainer = document.getElementById('progress-markers-container');
    this.timecodeDisplay = document.getElementById('timecode-display') || document.querySelector('.timecode-display');
    this.timecodeCurrentEl = document.getElementById('timecode-current');
    this.timecodeDurationEl = document.getElementById('timecode-duration');
    this.playPauseBtn = document.getElementById('btn-play-pause');
    this.prevFrameBtn = document.getElementById('btn-prev-frame');
    this.nextFrameBtn = document.getElementById('btn-next-frame');
    this.stepBack5sBtn = document.getElementById('btn-step-back-5s');
    this.stepFwd5sBtn = document.getElementById('btn-step-fwd-5s');
    this.speedSelect = document.getElementById('playback-speed-select') || document.getElementById('select-playback-speed');
    this.volumeSlider = document.getElementById('video-volume-slider');
    this.muteBtn = document.getElementById('btn-mute-toggle') || document.getElementById('btn-toggle-mute');
    this.loopBtn = document.getElementById('btn-toggle-loop');
    this.setInBtn = document.getElementById('btn-set-in');
    this.setOutBtn = document.getElementById('btn-set-out');
    this.fullscreenBtn = document.getElementById('btn-fullscreen');
    this.videoFileInput = document.getElementById('file-upload-input') || document.getElementById('video-file-input');
    // Referencia al empty state HTML existente (no crear duplicado)
    this.emptyStateOverlay = document.getElementById('video-empty-state');

    // Inicializar Empty State si no hay proyecto activo
    this.updateEmptyState();
  }

  updateEmptyState() {
    if (!this.emptyStateOverlay) {
      this.emptyStateOverlay = document.getElementById('video-empty-state');
    }

    const hasProject = !!appState.state.project;
    if (this.emptyStateOverlay) {
      this.emptyStateOverlay.style.display = hasProject ? 'none' : 'flex';
    }
  }

  bindEvents() {
    // 1. Play / Pause
    if (this.playPauseBtn) {
      this.playPauseBtn.addEventListener('click', () => this.togglePlay());
    }

    // 2. Step ±5s
    if (this.stepBack5sBtn) {
      this.stepBack5sBtn.addEventListener('click', () => {
        appState.setCurrentTime(appState.state.playback.currentTime - 5.0, 'seek_btn');
      });
    }
    if (this.stepFwd5sBtn) {
      this.stepFwd5sBtn.addEventListener('click', () => {
        appState.setCurrentTime(appState.state.playback.currentTime + 5.0, 'seek_btn');
      });
    }

    // 3. Paso de ±1 segundo (o Shift+Clic para 1 fotograma)
    if (this.prevFrameBtn) {
      this.prevFrameBtn.addEventListener('click', (e) => {
        this.pause();
        const delta = e.shiftKey ? -this.getFrameDuration() : -1.0;
        appState.stepFrame(delta);
      });
    }
    if (this.nextFrameBtn) {
      this.nextFrameBtn.addEventListener('click', (e) => {
        this.pause();
        const delta = e.shiftKey ? this.getFrameDuration() : 1.0;
        appState.stepFrame(delta);
      });
    }

    // 4. Velocidad de Reproducción
    if (this.speedSelect) {
      this.speedSelect.addEventListener('change', (e) => {
        const rate = parseFloat(e.target.value) || 1.0;
        appState.setPlaybackRate(rate);
        if (this.videoEl) this.videoEl.playbackRate = rate;
      });
    }

    // 5. Volumen y Silencio
    if (this.volumeSlider) {
      this.volumeSlider.addEventListener('input', (e) => {
        const vol = parseFloat(e.target.value);
        appState.setVolume(vol);
        if (this.videoEl) this.videoEl.volume = vol;
      });
    }
    if (this.muteBtn) {
      this.muteBtn.addEventListener('click', () => {
        appState.toggleMute();
        if (this.videoEl) this.videoEl.muted = appState.state.playback.isMuted;
      });
    }

    // 6. Puntos In / Out y Bucle
    if (this.setInBtn) {
      this.setInBtn.addEventListener('click', () => appState.setInPoint());
    }
    if (this.setOutBtn) {
      this.setOutBtn.addEventListener('click', () => appState.setOutPoint());
    }
    if (this.loopBtn) {
      this.loopBtn.addEventListener('click', () => appState.toggleLoop());
    }

    // 7. Pantalla Completa
    if (this.fullscreenBtn) {
      this.fullscreenBtn.addEventListener('click', () => this.toggleFullscreen());
    }

    // 8. Barra de Progreso (Click y Drag scrubbing)
    if (this.progressBar) {
      let isDragging = false;

      const handleSeek = (e) => {
        const rect = this.progressBar.getBoundingClientRect();
        const posX = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
        const percentage = posX / rect.width;
        const targetTime = percentage * (appState.state.playback.duration || 48.85);
        appState.setCurrentTime(targetTime, 'progress_seek');
      };

      this.progressBar.addEventListener('mousedown', (e) => {
        isDragging = true;
        handleSeek(e);
      });

      window.addEventListener('mousemove', (e) => {
        if (isDragging) handleSeek(e);
      });

      window.addEventListener('mouseup', () => {
        isDragging = false;
      });
    }

    // 9. Carga de Archivo de Video Local por selector
    if (this.videoFileInput) {
      this.videoFileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
          this.loadLocalVideoFile(file);
          e.target.value = '';
        }
      });
    }

    // 10. Drag & Drop de Video sobre el contenedor
    if (this.container) {
      this.container.addEventListener('dragover', (e) => {
        e.preventDefault();
        this.container.classList.add('drag-over');
      });
      this.container.addEventListener('dragleave', () => {
        this.container.classList.remove('drag-over');
      });
      this.container.addEventListener('drop', (e) => {
        e.preventDefault();
        this.container.classList.remove('drag-over');
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
          const file = e.dataTransfer.files[0];
          if (file.type.startsWith('video/')) {
            this.loadLocalVideoFile(file);
          }
        }
      });
    }

    // 11. Eventos del elemento <video> físico
    if (this.videoEl) {
      this.videoEl.addEventListener('timeupdate', () => {
        if (!this.isUsingCanvasFallback) {
          appState.setCurrentTime(this.videoEl.currentTime, 'html5_video');
        }
      });
      this.videoEl.addEventListener('ended', () => {
        if (appState.state.playback.isLooping) {
          this.videoEl.currentTime = appState.state.playback.inPoint || 0;
          this.videoEl.play();
        } else {
          const endDur = Number.isFinite(this.videoEl.duration) && this.videoEl.duration > 0
            ? this.videoEl.duration
            : (appState.state.playback.duration || this.videoEl.currentTime || 0);
          if (endDur > 0) {
            appState.setCurrentTime(endDur, 'end');
          }
          appState.setIsPlaying(false);
        }
      });
    }
  }

  getFrameDuration() {
    const fps = (appState.state.project && appState.state.project.media_info && appState.state.project.media_info.fps) || this.detectedFps || 30.0;
    return 1.0 / (fps > 0 ? fps : 30.0);
  }

  loadLocalVideoFile(file) {
    if (!file) return;
    const objUrl = URL.createObjectURL(file);
    if (this.videoEl) {
      this.videoEl.src = objUrl;
      this.isUsingCanvasFallback = false;
      if (this.canvasEl) this.canvasEl.style.display = 'none';
      this.videoEl.style.display = 'block';
    }

    const initialProject = {
      version: '2.1.1',
      media_info: {
        filename: file.name,
        duration_seconds: 0,
        fps: this.detectedFps || 30.0,
        resolution: '1920x1080',
        size_bytes: file.size,
      },
      segments: [],
      glosses: [],
      subtitles: [],
      propositions: [],
      blocks: [],
      spans: [],
      operations: [],
      validation_metadata: null,
    };
    appState.loadProject(initialProject, file.name);

    if (this.videoEl) {
      this.videoEl.onloadedmetadata = () => {
        const rawDur = this.videoEl.duration;
        const dur = (Number.isFinite(rawDur) && rawDur > 0) ? rawDur : (appState.state.playback.duration || 0);
        if (dur > 0) {
          appState.setDuration(dur);
          if (appState.state.project && appState.state.project.media_info) {
            appState.state.project.media_info.duration_seconds = dur;
            appState.state.project.media_info.resolution = `${this.videoEl.videoWidth || 1920}x${this.videoEl.videoHeight || 1080}`;
          }
        }
        console.log(`Archivo '${file.name}' listo en reproductor (${dur.toFixed(2)}s).`);
      };
    }

    // Ejecutar pipeline real de extracción, transcripción y traducción en background
    if (window.pipelineProcessor) {
      window.pipelineProcessor.processVideo(file, this.videoEl);
    }
  }

  loadVideoUrl(url, filename = 'video.mp4') {
    if (!url) return;
    if (this.videoEl) {
      this.videoEl.src = url;
      this.isUsingCanvasFallback = false;
      if (this.canvasEl) this.canvasEl.style.display = 'none';
      this.videoEl.style.display = 'block';
    }

    const initialProject = {
      version: '2.1.1',
      media_info: {
        filename: filename,
        duration_seconds: 0,
        fps: this.detectedFps || 30.0,
        resolution: '1920x1080',
        size_bytes: 0,
      },
      segments: [],
      glosses: [],
      subtitles: [],
      propositions: [],
      blocks: [],
      spans: [],
      operations: [],
      validation_metadata: null,
    };
    appState.loadProject(initialProject, filename);

    if (this.videoEl) {
      this.videoEl.onloadedmetadata = () => {
        const rawDur = this.videoEl.duration;
        const dur = (Number.isFinite(rawDur) && rawDur > 0) ? rawDur : (appState.state.playback.duration || 0);
        if (dur > 0) {
          appState.setDuration(dur);
          if (appState.state.project && appState.state.project.media_info) {
            appState.state.project.media_info.duration_seconds = dur;
            appState.state.project.media_info.resolution = `${this.videoEl.videoWidth || 1920}x${this.videoEl.videoHeight || 1080}`;
          }
        }
        console.log(`Video '${filename}' listo en reproductor (${dur.toFixed(2)}s).`);
      };
    }
  }

  subscribeState() {
    appState.subscribe('timeupdate', ({ time, source }) => {
      this.updateTimeDisplay(time);
      this.updateProgressBar(time);

      if (this.videoEl && !this.isUsingCanvasFallback && source !== 'html5_video') {
        if (Math.abs(this.videoEl.currentTime - time) > 0.05) {
          this.videoEl.currentTime = time;
        }
      }
    });

    const handlePlayState = (isPlaying) => {
      this.updatePlayButton(isPlaying);
      if (isPlaying) {
        if (this.videoEl && !this.isUsingCanvasFallback) {
          this.videoEl.play().catch(e => console.warn('Video play error:', e));
        } else {
          this.startCanvasAnimationLoop();
        }
      } else {
        if (this.videoEl && !this.isUsingCanvasFallback) {
          this.videoEl.pause();
        }
      }
    };

    appState.subscribe('playbackStateChanged', handlePlayState);
    appState.subscribe('playstatechange', handlePlayState);

    appState.subscribe('inOutPointsChanged', ({ in: inPoint, out: outPoint }) => {
      this.updateInOutMarkers(inPoint, outPoint, appState.state.playback.isLooping);
    });

    appState.subscribe('loopStateChanged', (isLooping) => {
      this.updateInOutMarkers(appState.state.playback.inPoint, appState.state.playback.outPoint, isLooping);
    });

    appState.subscribe('inoutchange', ({ inPoint, outPoint, isLooping }) => {
      this.updateInOutMarkers(inPoint, outPoint, isLooping);
    });

    appState.subscribe('durationChanged', (duration) => {
      this.updateTimeDisplay(appState.state.playback.currentTime);
      this.updateProgressBar(appState.state.playback.currentTime);
      this.renderTimelineMarkers();
    });

    appState.subscribe('volumeChanged', ({ volume, isMuted }) => {
      if (this.volumeSlider) this.volumeSlider.value = isMuted ? 0 : volume;
      if (this.muteBtn) {
        this.muteBtn.classList.toggle('muted', isMuted);
        const iconOn = document.getElementById('icon-volume-on');
        const iconOff = document.getElementById('icon-volume-off');
        if (iconOn && iconOff) {
          iconOn.style.display = isMuted ? 'none' : 'inline';
          iconOff.style.display = isMuted ? 'inline' : 'none';
        }
      }
      if (this.videoEl) {
        this.videoEl.volume = volume;
        this.videoEl.muted = isMuted;
      }
    });

    appState.subscribe('projectLoaded', (proj) => {
      this.updateEmptyState();
      this.renderTimelineMarkers();
      this.updateTimeDisplay(appState.state.playback.currentTime || 0);
      
      const hud = document.getElementById('hud-res');
      if (hud && proj && proj.media_info) {
        hud.textContent = `${proj.media_info.resolution || '1080p'} · ${proj.media_info.fps || 30}fps · ${(proj.media_info.duration_seconds || 48.85).toFixed(2)}s`;
      }

      if (this.videoEl && this.videoEl.src && !this.videoEl.src.endsWith('/studio') && !this.videoEl.src.endsWith('/') && this.videoEl.src !== window.location.href) {
        this.isUsingCanvasFallback = false;
        if (this.canvasEl) this.canvasEl.style.display = 'none';
        if (this.videoEl) this.videoEl.style.display = 'block';
      } else {
        this.isUsingCanvasFallback = true;
        if (this.canvasEl) this.canvasEl.style.display = 'block';
        if (this.videoEl) this.videoEl.style.display = 'none';
        this.startCanvasAnimationLoop();
      }
    });

    appState.subscribe('projectCleared', () => {
      this.updateEmptyState();
      this.renderTimelineMarkers();
      this.updateTimeDisplay(0);
      this.updateProgressBar(0);
      if (this.videoEl) {
        this.videoEl.pause();
        this.videoEl.removeAttribute('src');
      }
    });

    // Render inicial
    this.updateEmptyState();
    this.renderTimelineMarkers();
  }

  togglePlay() {
    if (appState.state.playback.isPlaying) {
      this.pause();
    } else {
      this.play();
    }
  }

  play() {
    appState.setIsPlaying(true);
  }

  pause() {
    appState.setIsPlaying(false);
  }

  updatePlayButton(isPlaying) {
    if (!this.playPauseBtn) return;
    if (isPlaying) {
      this.playPauseBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
        </svg>
      `;
      this.playPauseBtn.setAttribute('title', 'Pausar (Espacio / K)');
      this.playPauseBtn.classList.add('playing');
    } else {
      this.playPauseBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <path d="M8 5v14l11-7z"/>
        </svg>
      `;
      this.playPauseBtn.setAttribute('title', 'Reproducir (Espacio / K)');
      this.playPauseBtn.classList.remove('playing');
    }
  }

  updateTimeDisplay(time) {
    const formatTime = (secs) => {
      if (secs === undefined || secs === null || !Number.isFinite(secs) || secs < 0) return '00:00.0';
      const m = Math.floor(secs / 60);
      const s = Math.floor(secs % 60);
      const tenths = Math.floor((secs % 1) * 10);
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${tenths}`;
    };

    const rawDur = appState.state.playback.duration;
    const duration = (Number.isFinite(rawDur) && rawDur > 0) ? rawDur : 0;
    if (this.timecodeCurrentEl && this.timecodeDurationEl) {
      this.timecodeCurrentEl.textContent = formatTime(time);
      this.timecodeDurationEl.textContent = formatTime(duration);
      return;
    }
    if (!this.timecodeDisplay) return;
    this.timecodeDisplay.innerHTML = `
      <span class="timecode-current">${formatTime(time)}</span>
      <span class="timecode-sep" style="opacity:0.3; margin:0 3px;">/</span>
      <span class="timecode-total">${formatTime(duration)}</span>
    `;
  }

  updateProgressBar(time) {
    if (!this.progressFill || !this.progressPlayhead) return;
    const duration = appState.state.playback.duration;
    if (!duration || duration <= 0) {
      this.progressFill.style.width = '0%';
      return;
    }
    const percentage = Math.min(100, Math.max(0, (time / duration) * 100));
    this.progressFill.style.width = `${percentage}%`;
  }

  renderTimelineMarkers() {
    if (!this.markersContainer) return;
    this.markersContainer.innerHTML = '';

    const project = appState.state.project;
    if (!project) return;

    const duration = appState.state.playback.duration || 48.850;

    // 1. Marcadores de Segmentos e Incidencias
    (project.segments || []).forEach(seg => {
      const dot = document.createElement('div');
      dot.className = `timeline-marker-dot ${seg.status.toLowerCase()}`;
      const pct = (seg.start_seconds / duration) * 100;
      dot.style.left = `${pct}%`;
      dot.setAttribute('title', `[${seg.start_seconds.toFixed(2)}s] ${seg.status_label}: ${seg.original_text.slice(0, 35)}...`);
      dot.addEventListener('click', (e) => {
        e.stopPropagation();
        appState.setCurrentTime(seg.start_seconds, 'marker_click');
        appState.selectItem('segment', seg.id);
      });
      this.markersContainer.appendChild(dot);
    });

    // 2. Marcadores de Referentes Espaciales
    (project.spatial_operations || []).forEach(sp => {
      const dot = document.createElement('div');
      dot.className = 'timeline-marker-dot spatial';
      const pct = (sp.time_seconds / duration) * 100;
      dot.style.left = `${pct}%`;
      dot.setAttribute('title', `Operación Espacial [${sp.time_seconds}s]: ${sp.label}`);
      dot.addEventListener('click', (e) => {
        e.stopPropagation();
        appState.setCurrentTime(sp.time_seconds, 'spatial_marker_click');
      });
      this.markersContainer.appendChild(dot);
    });
  }

  updateInOutMarkers(inPoint, outPoint, isLooping) {
    if (this.loopBtn) {
      if (isLooping) {
        this.loopBtn.classList.add('active');
        this.loopBtn.style.color = 'var(--primary)';
      } else {
        this.loopBtn.classList.remove('active');
        this.loopBtn.style.color = '';
      }
    }
  }


  // ============================================================
  // Fallback Canvas Video Player Animator & Waveform Visualizer
  // ============================================================

  startCanvasAnimationLoop() {
    let lastTimestamp = performance.now();

    const renderLoop = (currentTimestamp) => {
      const deltaSec = (currentTimestamp - lastTimestamp) / 1000;
      lastTimestamp = currentTimestamp;

      if (appState.state.playback.isPlaying) {
        const rate = appState.state.playback.playbackRate || 1.0;
        const nextTime = appState.state.playback.currentTime + (deltaSec * rate);
        const duration = appState.state.playback.duration || 48.850;

        if (nextTime >= duration) {
          if (appState.state.playback.isLooping) {
            appState.setCurrentTime(appState.state.playback.inPoint || 0, 'loop');
          } else {
            appState.setCurrentTime(duration, 'end');
            appState.setIsPlaying(false);
          }
        } else {
          appState.setCurrentTime(nextTime, 'canvas_loop');
        }
      }

      if (this.isUsingCanvasFallback && this.canvasCtx) {
        this.drawCanvasFrame(appState.state.playback.currentTime);
      }

      if (appState.state.playback.isPlaying || this.isUsingCanvasFallback) {
        this.animFrameId = requestAnimationFrame(renderLoop);
      }
    };

    if (this.animFrameId) cancelAnimationFrame(this.animFrameId);
    this.animFrameId = requestAnimationFrame(renderLoop);
  }

  drawCanvasFrame(time) {
    if (!this.canvasCtx || !this.canvasEl) return;
    const ctx = this.canvasCtx;
    const width = this.canvasEl.width = this.canvasEl.clientWidth || 800;
    const height = this.canvasEl.height = this.canvasEl.clientHeight || 450;

    // 1. Fondo Minimalista Dark Studio
    ctx.fillStyle = '#050811';
    ctx.fillRect(0, 0, width, height);

    // 2. Ondas Sutiles de Audio
    const barsCount = 64;
    const totalW = width * 0.55;
    const barWidth = totalW / barsCount;
    const startX = (width - totalW) / 2;
    const centerY = height * 0.48;

    for (let i = 0; i < barsCount; i++) {
      const freq = Math.sin(time * 3 + i * 0.25) * Math.cos(time * 1.5 + i * 0.08);
      const isPlaying = appState.state.playback.isPlaying;
      const barHeight = isPlaying ? Math.abs(freq) * 45 + 4 : 4;

      ctx.fillStyle = isPlaying ? 'rgba(183, 211, 107, 0.75)' : 'rgba(255, 255, 255, 0.08)';
      ctx.fillRect(startX + i * barWidth, centerY - barHeight / 2, barWidth - 2, barHeight);
    }
  }

  toggleFullscreen() {
    const target = document.getElementById('video-wrapper') || this.container || document.documentElement;
    if (!document.fullscreenElement) {
      if (target.requestFullscreen) {
        target.requestFullscreen().catch((err) => {
          console.warn('No se pudo activar pantalla completa:', err);
        });
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen().catch((err) => {
          console.warn('No se pudo salir de pantalla completa:', err);
        });
      }
    }
  }
}

// Instancia exportada
if (typeof window !== 'undefined') {
  window.VideoPlayerController = VideoPlayerController;
}
