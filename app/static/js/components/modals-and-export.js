/**
 * LSEC Studio — Componente ModalsAndExport
 * 
 * Gestiona los diálogos modales especializados:
 * 1. Modal de Revisión Auditiva (bucle, pitch preserve, boost +6/+12dB, candidatas)
 * 2. Modal de Revisión Nativa LSEC (paráfrasis, variantes regionales Sierra/Costa)
 * 3. Modal de Exportación Multiformato (TXT, JSON, SRT, VTT, Reporte MD, Bundle)
 * 4. Modal de Configuración y Accesibilidad (Temas, escalas, atajos de teclado)
 */

class ModalsAndExportController {
  constructor() {
    this.modalBackdrop = document.getElementById('generic-modal-backdrop');
    this.modalTitle = document.getElementById('generic-modal-title');
    this.modalBody = document.getElementById('generic-modal-body');
    this.modalFooter = document.getElementById('generic-modal-footer');
    this.modalCloseBtn = document.getElementById('generic-modal-close');

    this.init();
  }

  init() {
    if (this.modalCloseBtn) {
      this.modalCloseBtn.addEventListener('click', () => this.close());
    }

    if (this.modalBackdrop) {
      this.modalBackdrop.addEventListener('click', (e) => {
        if (e.target === this.modalBackdrop) this.close();
      });
    }

    // Botones de la barra superior
    const exportBtn = document.getElementById('btn-top-export');
    if (exportBtn) {
      exportBtn.addEventListener('click', () => this.openExportDialog());
    }

    const settingsBtn = document.getElementById('btn-top-settings');
    if (settingsBtn) {
      settingsBtn.addEventListener('click', () => this.openSettingsDialog());
    }
  }

  close() {
    if (this.modalBackdrop) {
      this.modalBackdrop.classList.remove('open');
    }
  }

  // ============================================================
  // 1. MODAL DE REVISIÓN AUDITIVA
  // ============================================================

  openAudioReviewModal(segment) {
    if (!this.modalBackdrop || !this.modalTitle || !this.modalBody) return;

    const candidates = segment.acoustic_candidates || ['lideran', 'crean', 'proyectan', 'liberan'];
    let selectedWord = candidates[0];

    this.modalTitle.innerHTML = `
      <div style="display:flex; align-items:center; gap:8px;">
        <span>Asistente de Revisión Auditiva — Segmento #${segment.index}</span>
      </div>
    `;

    this.modalBody.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:14px;">
        <div style="background:var(--lsec-red-bg); border:1px solid rgba(239, 68, 68, 0.4); padding:10px 14px; border-radius:var(--radius-md); font-size:0.82rem; color:#fca5a5;">
          <strong>Ambigüedad acústica detectada:</strong> El reconocedor Whisper decodificó con 78% de confianza. Se requiere validación auditiva del fonema original.
        </div>

        <div class="audio-snippet-player-box">
          <div style="font-family:var(--font-mono); font-size:0.85rem; color:var(--text-secondary);">
            Intervalo: <strong>${(segment.start_seconds || 0).toFixed(3)}s → ${(segment.end_seconds || 0).toFixed(3)}s</strong> (${((segment.duration !== undefined && !isNaN(segment.duration)) ? segment.duration : Math.max(0, (segment.end_seconds || 0) - (segment.start_seconds || 0))).toFixed(2)}s)
          </div>
          
          <div style="display:flex; align-items:center; gap:10px; width:100%; justify-content:center;">
            <button class="btn btn-primary" id="btn-modal-play-snippet">Escuchar Fragmento en Bucle</button>
            <button class="btn btn-secondary" id="btn-modal-stop-snippet">Detener</button>
          </div>

          <div style="display:flex; gap:16px; align-items:center; font-size:0.75rem; color:var(--text-muted); margin-top:4px;">
            <label style="display:flex; align-items:center; gap:6px;">
              Velocidad sin alterar tono:
              <select id="modal-audio-speed" class="speed-select">
                <option value="0.5">0.5x (Lenta)</option>
                <option value="0.75" selected>0.75x</option>
                <option value="1.0">1.0x (Normal)</option>
              </select>
            </label>

            <label style="display:flex; align-items:center; gap:6px;">
              Amplificación de audio:
              <select id="modal-audio-boost" class="speed-select">
                <option value="0">Normal (0 dB)</option>
                <option value="6">+6 dB</option>
                <option value="12" selected>+12 dB (Realce vocal)</option>
              </select>
            </label>
          </div>
        </div>

        <div>
          <label style="font-weight:600; font-size:0.85rem; margin-bottom:6px; display:block;">Palabras candidatas recomendadas:</label>
          <div class="candidate-chips-grid">
            ${candidates.map((cand, i) => `
              <button class="candidate-chip-btn ${i === 0 ? 'selected' : ''}" data-word="${cand}">
                "${cand}"
              </button>
            `).join('')}
          </div>
        </div>

        <div>
          <label style="font-size:0.78rem; color:var(--text-muted);">O introduce otra palabra escuchada:</label>
          <input type="text" id="modal-custom-word" placeholder="Escribe aquí si escuchas otra palabra..." style="width:100%; padding:6px 10px; background:var(--bg-surface-2); border:1px solid var(--border-medium); border-radius:4px; margin-top:4px;">
        </div>

        <div>
          <label style="font-size:0.78rem; color:var(--text-muted);">Observaciones del revisor:</label>
          <textarea id="modal-audio-comment" rows="2" placeholder="Notas sobre acústica, acento regional o ruido de fondo..." style="width:100%; padding:6px 10px; background:var(--bg-surface-2); border:1px solid var(--border-medium); border-radius:4px; resize:vertical;"></textarea>
        </div>

        <div style="font-size:0.7rem; color:var(--text-muted);">
          Revisor: <strong>${appState.state.currentUser.name}</strong> (${appState.state.currentUser.role})
        </div>
      </div>
    `;

    this.modalFooter.innerHTML = `
      <button class="btn btn-secondary" id="btn-cancel-modal">Cancelar</button>
      <button class="btn btn-success" id="btn-confirm-audio-rev">Confirmar Palabra y Validar</button>
    `;

    // Bindings internos del modal
    const playBtn = this.modalBody.querySelector('#btn-modal-play-snippet');
    const stopBtn = this.modalBody.querySelector('#btn-modal-stop-snippet');
    
    playBtn.addEventListener('click', () => {
      appState.setCurrentTime(segment.start_seconds, 'modal_audio_play');
      appState.setInPoint(segment.start_seconds);
      appState.setOutPoint(segment.end_seconds);
      appState.state.playback.isLooping = true;
      appState.setIsPlaying(true);
    });

    stopBtn.addEventListener('click', () => {
      appState.setIsPlaying(false);
      appState.state.playback.isLooping = false;
    });

    const candidateBtns = this.modalBody.querySelectorAll('.candidate-chip-btn');
    candidateBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        candidateBtns.forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        selectedWord = btn.getAttribute('data-word');
      });
    });

    this.modalFooter.querySelector('#btn-cancel-modal').addEventListener('click', () => this.close());

    this.modalFooter.querySelector('#btn-confirm-audio-rev').addEventListener('click', () => {
      const customWord = this.modalBody.querySelector('#modal-custom-word').value.trim();
      const finalWord = customWord || selectedWord;
      const comment = this.modalBody.querySelector('#modal-audio-comment').value.trim();

      appState.resolveAudioReview(segment.id, finalWord, comment);
      appState.state.playback.isLooping = false;
      this.close();
      alert(`Revisión auditiva confirmada: '${finalWord}'`);
    });

    this.modalBackdrop.classList.add('open');
  }

  // ============================================================
  // 2. MODAL DE REVISIÓN NATIVA LSEC
  // ============================================================

  openNativeReviewModal(segment) {
    if (!this.modalBackdrop || !this.modalTitle || !this.modalBody) return;

    this.modalTitle.innerHTML = `
      <div style="display:flex; align-items:center; gap:8px;">
        <span>Validación Lingüística LSEC por Persona Sorda Nativa — Segmento #${segment.index}</span>
      </div>
    `;

    this.modalBody.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:14px;">
        <div style="background:var(--lsec-yellow-bg); border:1px solid rgba(234, 179, 8, 0.4); padding:10px 14px; border-radius:var(--radius-md); font-size:0.82rem; color:var(--lsec-yellow);">
          <strong>Revisión de Paráfrasis Conceptual:</strong> El concepto en español <em>"${segment.normalized_text}"</em> incluye términos abstractos que requieren evaluación de naturalidad y sintaxis visual LSEC.
        </div>

        <div style="background:var(--bg-surface-2); padding:12px; border-radius:var(--radius-md); font-size:0.82rem;">
          <div style="margin-bottom:6px;"><strong>Texto Fuente:</strong> "${segment.normalized_text}"</div>
          <div><strong>Secuencia de Glosas Propuesta:</strong></div>
          <div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:6px;">
            ${(segment.gloss_sequence || []).map(g => `<span class="gloss-pill active" style="font-size:0.95rem;">${g}</span>`).join('')}
          </div>
        </div>

        <div>
          <label style="font-weight:600; font-size:0.82rem;">Variante Regional Evaluada:</label>
          <select id="modal-native-variant" class="speed-select" style="width:100%; padding:6px 10px; margin-top:4px;">
            <option value="Sierra / Carchi" selected>Sierra Norte (Carchi / Tulcán)</option>
            <option value="Sierra Centro">Sierra Centro (Quito / Pichincha)</option>
            <option value="Costa">Costa (Guayaquil / Guayas)</option>
            <option value="Nacional Estándar">Estándar LSEC Nacional (FENASEC)</option>
          </select>
        </div>

        <div>
          <label style="font-weight:600; font-size:0.82rem;">Alternativa o Paráfrasis sugerida por signante:</label>
          <input type="text" id="modal-native-suggested" placeholder="Ej: U-P-E-C PRO2 CARRERA ELEGIR FUERTE AVANZAR CONTINUAR" style="width:100%; padding:6px 10px; background:var(--bg-surface-2); border:1px solid var(--border-medium); border-radius:4px; font-weight:700; text-transform:uppercase;">
        </div>

        <div>
          <label style="font-size:0.78rem; color:var(--text-muted);">Comentarios lingüísticos o expresión facial requerida:</label>
          <textarea id="modal-native-comment" rows="2" placeholder="Indicar si la paráfrasis es natural o requiere ajuste de clasificadores..." style="width:100%; padding:6px 10px; background:var(--bg-surface-2); border:1px solid var(--border-medium); border-radius:4px;"></textarea>
        </div>
      </div>
    `;

    this.modalFooter.innerHTML = `
      <button class="btn btn-secondary" id="btn-cancel-modal">Cerrar</button>
      <button class="btn btn-warning" id="btn-reject-native-rev">Proponer Cambios</button>
      <button class="btn btn-success" id="btn-approve-native-rev">Aprobar Paráfrasis LSEC</button>
    `;

    this.modalFooter.querySelector('#btn-cancel-modal').addEventListener('click', () => this.close());

    this.modalFooter.querySelector('#btn-approve-native-rev').addEventListener('click', () => {
      const comment = this.modalBody.querySelector('#modal-native-comment').value.trim();
      appState.resolveNativeReview(segment.id, 'approved', null, comment);
      this.close();
      alert('Paráfrasis LSEC validada y aprobada por el revisor nativo.');
    });

    this.modalFooter.querySelector('#btn-reject-native-rev').addEventListener('click', () => {
      const suggested = this.modalBody.querySelector('#modal-native-suggested').value.trim();
      const comment = this.modalBody.querySelector('#modal-native-comment').value.trim();
      const glossList = suggested ? suggested.split(/\s+/).map(s => s.toUpperCase()) : null;

      appState.resolveNativeReview(segment.id, 'modified', glossList, comment);
      this.close();
      alert('Paráfrasis modificada con la propuesta del signante.');
    });

    this.modalBackdrop.classList.add('open');
  }

  // ============================================================
  // 3. MODAL DE EXPORTACIÓN MULTIFORMATO
  // ============================================================

  openExportDialog() {
    if (!this.modalBackdrop || !this.modalTitle || !this.modalBody) return;

    const project = appState.state.project;
    if (!project) {
      alert('Por favor carga o selecciona un video para habilitar la exportación.');
      return;
    }

    const isBlocked = project.execution_status === 'BLOCKED';
    const isReviewReq = project.execution_status === 'REVIEW_REQUIRED';

    this.modalTitle.innerHTML = 'Exportar Resultados del Proyecto LSEC';

    this.modalBody.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:14px;">
        ${(isBlocked || isReviewReq) ? `
          <div class="export-warning-gate">
            <strong>Control de Calidad LSEC:</strong> El proyecto se encuentra en estado <em>${project.execution_status}</em>. Existen ${project.validation_metadata?.blocking_errors_count || 0} errores bloqueantes y revisiones pendientes. Se recomienda completar la validación antes de publicar traducciones oficiales.
          </div>
        ` : ''}

        <div style="font-weight:600; font-size:0.85rem;">Selecciona el formato de exportación deseado:</div>

        <div class="export-format-grid">
          <!-- Opción Principal: Video con Intérprete, Glosas y Subtítulos Incrustados -->
          <button class="export-card-btn export-card-featured" id="btn-exp-composite-video">
            <div style="display:flex; align-items:center; justify-content:space-between; width:100%;">
              <div style="display:flex; align-items:center; gap:8px;">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" style="color:var(--action-primary);"><path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/></svg>
                <span style="font-weight:700; color:var(--action-primary); font-size:0.92rem;">Exportar Video con Intérprete, Glosas y Subtítulos</span>
              </div>
              <span class="avatar-pip-tag" style="background:rgba(183,211,107,0.25); color:var(--action-primary); font-size:0.65rem; font-weight:700; padding:2px 8px; border-radius:4px; border:1px solid rgba(183,211,107,0.4);">RECOMENDADO</span>
            </div>
            <div style="font-size:0.75rem; color:var(--text-secondary); line-height:1.4; margin-top:4px;">
              Genera y descarga el video con el avatar del intérprete (PiP), las glosas LSEC sincronizadas en tiempo real y los subtítulos en español incrustados en la imagen.
            </div>
            <div style="margin-top:8px; display:flex; gap:6px; flex-wrap:wrap;">
              <span style="background:rgba(183,211,107,0.12); color:var(--action-primary); font-size:0.68rem; padding:2px 6px; border-radius:3px; border:1px solid rgba(183,211,107,0.25);">✓ Intérprete Avatar 3D</span>
              <span style="background:rgba(234,179,8,0.12); color:var(--lsec-yellow); font-size:0.68rem; padding:2px 6px; border-radius:3px; border:1px solid rgba(234,179,8,0.25);">✓ Glosas LSEC</span>
              <span style="background:rgba(59,130,246,0.12); color:#93c5fd; font-size:0.68rem; padding:2px 6px; border-radius:3px; border:1px solid rgba(59,130,246,0.25);">✓ Subtítulos Quemados</span>
              <span style="background:rgba(255,255,255,0.06); color:var(--text-muted); font-size:0.68rem; padding:2px 6px; border-radius:3px;">MP4 / WebM HD</span>
            </div>
          </button>

          <button class="export-card-btn" id="btn-exp-srt">
            <div style="font-weight:700; color:var(--primary);">Subtítulos SRT (.srt)</div>
            <div style="font-size:0.72rem; color:var(--text-muted);">Formato estándar para reproductores y plataformas de video.</div>
          </button>

          <button class="export-card-btn" id="btn-exp-vtt">
            <div style="font-weight:700; color:var(--primary);">WebVTT (.vtt)</div>
            <div style="font-size:0.72rem; color:var(--text-muted);">Subtítulos web enriquecidos con marcas de tiempo.</div>
          </button>

          <button class="export-card-btn" id="btn-exp-gloss-txt">
            <div style="font-weight:700; color:var(--lsec-yellow);">Glosas LSEC (.txt)</div>
            <div style="font-size:0.72rem; color:var(--text-muted);">Secuencia de glosas en mayúsculas por renglón temporal.</div>
          </button>

          <button class="export-card-btn" id="btn-exp-gloss-json">
            <div style="font-weight:700; color:var(--lsec-yellow);">Glosas JSON LSEC 2.1.1</div>
            <div style="font-size:0.72rem; color:var(--text-muted);">Esquema de traducción completo para avatar 3D y APIs.</div>
          </button>

          <button class="export-card-btn" id="btn-exp-txt">
            <div style="font-weight:700; color:var(--text-primary);">Transcripción TXT (.txt)</div>
            <div style="font-size:0.72rem; color:var(--text-muted);">Texto plano normalizado y revisado.</div>
          </button>

          <button class="export-card-btn" id="btn-exp-report">
            <div style="font-weight:700; color:var(--lsec-green);">Informe de Auditoría (.md)</div>
            <div style="font-size:0.72rem; color:var(--text-muted);">Reporte de calidad y validación con métricas.</div>
          </button>

          <button class="export-card-btn" id="btn-exp-csv">
            <div style="font-weight:700; color:var(--primary);">Segmentos CSV (.csv)</div>
            <div style="font-size:0.72rem; color:var(--text-muted);">Tiempos, texto y glosas en formato tabular.</div>
          </button>

          <button class="export-card-btn" id="btn-exp-elan">
            <div style="font-weight:700; color:var(--primary);">Anotación ELAN (.eaf)</div>
            <div style="font-size:0.72rem; color:var(--text-muted);">Formato estándar para análisis lingüístico multimodal.</div>
          </button>
        </div>

        <button class="btn btn-secondary" style="width:100%;" id="btn-exp-bundle">
          Descargar Proyecto Completo (.json bundle)
        </button>
      </div>
    `;

    this.modalFooter.innerHTML = `
      <button class="btn btn-secondary" onclick="document.getElementById('generic-modal-backdrop').classList.remove('open')">Cerrar</button>
    `;

    // Bindings de Descargas
    this.modalBody.querySelector('#btn-exp-composite-video').addEventListener('click', () => this.openCompositeVideoExportDialog());
    this.modalBody.querySelector('#btn-exp-srt').addEventListener('click', () => this.downloadSRT());
    this.modalBody.querySelector('#btn-exp-vtt').addEventListener('click', () => this.downloadVTT());
    this.modalBody.querySelector('#btn-exp-gloss-txt').addEventListener('click', () => this.downloadGlossTXT());
    this.modalBody.querySelector('#btn-exp-gloss-json').addEventListener('click', () => this.downloadGlossJSON());
    this.modalBody.querySelector('#btn-exp-txt').addEventListener('click', () => this.downloadTranscriptionTXT());
    this.modalBody.querySelector('#btn-exp-report').addEventListener('click', () => this.downloadAuditReport());
    this.modalBody.querySelector('#btn-exp-csv').addEventListener('click', () => this.downloadCSV());
    this.modalBody.querySelector('#btn-exp-elan').addEventListener('click', () => this.downloadELAN());
    this.modalBody.querySelector('#btn-exp-bundle').addEventListener('click', () => this.downloadProjectBundle());

    this.modalBackdrop.classList.add('open');
  }

  // ============================================================
  // DIÁLOGO ESPECIALIZADO: EXPORTACIÓN DE VIDEO COMPUESTO
  // ============================================================

  openCompositeVideoExportDialog() {
    if (!this.modalBackdrop || !this.modalTitle || !this.modalBody) return;

    const project = appState.state.project || {};
    const mediaInfo = project.media_info || {};
    const duration = appState.state.playback.duration || mediaInfo.duration_seconds || 0;
    const filename = mediaInfo.filename || 'video.mp4';

    this.modalTitle.innerHTML = `
      <div style="display:flex; align-items:center; gap:8px;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="color:var(--action-primary);"><path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/></svg>
        <span>Exportar Video con Intérprete y Subtítulos</span>
      </div>
    `;

    this.modalBody.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:14px;" id="composite-export-container">
        
        <!-- Info del video -->
        <div style="display:flex; justify-content:space-between; align-items:center; background:var(--bg-surface-subtle); padding:8px 12px; border-radius:var(--radius-sm); font-size:0.78rem; border:1px solid var(--border-subtle);">
          <div><strong>Archivo:</strong> <span style="color:var(--text-secondary);">${filename}</span></div>
          <div><strong>Duración:</strong> <span style="font-family:var(--font-mono); color:var(--action-primary);">${duration.toFixed(2)}s</span></div>
          <div><strong>Resolución:</strong> <span style="font-family:var(--font-mono); color:var(--text-secondary);">${mediaInfo.resolution || 'HD'}</span></div>
        </div>

        <!-- Panel de configuración de incrustación -->
        <div class="export-video-config-panel" id="composite-config-panel">
          <div style="font-weight:600; font-size:0.84rem; color:var(--text-primary); margin-bottom:2px;">
            Ajustes de Incrustación Audiovisual:
          </div>

          <div class="export-config-row">
            <label class="export-config-label" for="cfg-pip-position">
              <span>Posición del Intérprete (PiP):</span>
            </label>
            <select id="cfg-pip-position" class="export-config-select">
              <option value="bottom-right" selected>Inferior Derecha (Estándar LSEC)</option>
              <option value="bottom-left">Inferior Izquierda</option>
            </select>
          </div>

          <div class="export-config-row">
            <label class="export-config-label" for="cfg-resolution">
              <span>Resolución de Salida:</span>
            </label>
            <select id="cfg-resolution" class="export-config-select">
              <option value="original" selected>Resolución Original (Máxima Calidad)</option>
              <option value="720p">720p HD (Rápida)</option>
            </select>
          </div>

          <div class="export-config-row">
            <label class="export-config-label">
              <span>Elementos Incrustados:</span>
            </label>
            <div style="display:flex; gap:12px;">
              <label style="display:flex; align-items:center; gap:4px; font-size:0.78rem; cursor:pointer;">
                <input type="checkbox" id="cfg-include-avatar" checked style="accent-color:var(--action-primary);">
                Avatar Intérprete
              </label>
              <label style="display:flex; align-items:center; gap:4px; font-size:0.78rem; cursor:pointer;">
                <input type="checkbox" id="cfg-include-glosses" checked style="accent-color:var(--action-primary);">
                Glosas LSEC
              </label>
              <label style="display:flex; align-items:center; gap:4px; font-size:0.78rem; cursor:pointer;">
                <input type="checkbox" id="cfg-include-subs" checked style="accent-color:var(--action-primary);">
                Subtítulos
              </label>
            </div>
          </div>
        </div>

        <!-- Caja de Previsualización y Progreso durante renderizado (inicialmente oculta) -->
        <div id="composite-progress-panel" style="display:none; flex-direction:column; gap:10px;">
          <div class="export-preview-box">
            <canvas id="composite-export-preview-canvas" class="export-preview-canvas" width="640" height="360"></canvas>
            <div style="position:absolute; top:8px; left:10px; background:rgba(0,0,0,0.7); padding:2px 8px; border-radius:4px; font-size:0.68rem; font-family:var(--font-mono); color:var(--action-primary); border:1px solid rgba(183,211,107,0.3);">
              ● EN PROCESO
            </div>
          </div>

          <div class="export-progress-wrap">
            <div class="export-progress-fill" id="composite-export-progress-fill"></div>
          </div>

          <div class="export-stats-row">
            <span id="composite-export-status-label">Preparando renderizado...</span>
            <span id="composite-export-timecode-label">00:00 / 00:00 (0%)</span>
          </div>
        </div>

        <!-- Panel de Éxito al finalizar (inicialmente oculto) -->
        <div id="composite-success-panel" style="display:none; flex-direction:column; gap:10px; background:rgba(183,211,107,0.1); border:1px solid rgba(183,211,107,0.3); border-radius:var(--radius-md); padding:14px; text-align:center;">
          <div style="color:var(--action-primary); font-size:1.4rem;">✓</div>
          <div style="font-weight:700; font-size:0.92rem; color:var(--text-primary);">¡Video exportado exitosamente!</div>
          <div style="font-size:0.75rem; color:var(--text-secondary);" id="composite-success-filename"></div>
        </div>

      </div>
    `;

    this.modalFooter.innerHTML = `
      <button class="btn btn-secondary" id="btn-back-export-options">Volver a Formatos</button>
      <button class="btn btn-primary" id="btn-start-video-export">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
        Iniciar Renderizado y Descarga
      </button>
    `;

    // Eventos del diálogo de video compuesto
    const backBtn = this.modalFooter.querySelector('#btn-back-export-options');
    backBtn.addEventListener('click', () => {
      if (window.compositeVideoExporter && window.compositeVideoExporter.isExporting) {
        if (!confirm('¿Deseas cancelar el renderizado en curso?')) return;
        window.compositeVideoExporter.cancelExport();
      }
      this.openExportDialog();
    });

    const startBtn = this.modalFooter.querySelector('#btn-start-video-export');
    startBtn.addEventListener('click', () => this.runCompositeVideoExport());
  }

  runCompositeVideoExport() {
    if (!window.compositeVideoExporter) {
      alert('El motor de exportación de video no se encuentra disponible.');
      return;
    }

    const configPanel = this.modalBody.querySelector('#composite-config-panel');
    const progressPanel = this.modalBody.querySelector('#composite-progress-panel');
    const successPanel = this.modalBody.querySelector('#composite-success-panel');
    const previewCanvas = this.modalBody.querySelector('#composite-export-preview-canvas');
    const progressFill = this.modalBody.querySelector('#composite-export-progress-fill');
    const statusLabel = this.modalBody.querySelector('#composite-export-status-label');
    const timecodeLabel = this.modalBody.querySelector('#composite-export-timecode-label');

    const pipPosition = this.modalBody.querySelector('#cfg-pip-position').value;
    const resolution = this.modalBody.querySelector('#cfg-resolution').value;
    const includeInterpreter = this.modalBody.querySelector('#cfg-include-avatar').checked;
    const includeGlosses = this.modalBody.querySelector('#cfg-include-glosses').checked;
    const includeSubtitles = this.modalBody.querySelector('#cfg-include-subs').checked;

    // Cambiar a vista de renderizado
    if (configPanel) configPanel.style.display = 'none';
    if (progressPanel) progressPanel.style.display = 'flex';
    if (successPanel) successPanel.style.display = 'none';

    this.modalFooter.innerHTML = `
      <button class="btn btn-danger" id="btn-cancel-video-export">Cancelar Exportación</button>
    `;

    const cancelBtn = this.modalFooter.querySelector('#btn-cancel-video-export');
    cancelBtn.addEventListener('click', () => {
      window.compositeVideoExporter.cancelExport();
      if (progressPanel) progressPanel.style.display = 'none';
      if (configPanel) configPanel.style.display = 'flex';
      this.modalFooter.innerHTML = `
        <button class="btn btn-secondary" id="btn-back-export-options">Volver a Formatos</button>
        <button class="btn btn-primary" id="btn-start-video-export">Iniciar Renderizado y Descarga</button>
      `;
      this.modalFooter.querySelector('#btn-back-export-options').addEventListener('click', () => this.openExportDialog());
      this.modalFooter.querySelector('#btn-start-video-export').addEventListener('click', () => this.runCompositeVideoExport());
    });

    const formatTime = (sec) => {
      const m = Math.floor(sec / 60);
      const s = Math.floor(sec % 60);
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    };

    let lastBlob = null;
    let lastFilename = null;

    window.compositeVideoExporter.startExport(
      {
        pipPosition,
        resolution,
        includeInterpreter,
        includeGlosses,
        includeSubtitles,
        playbackSpeed: 1.0
      },
      // onProgress
      (info) => {
        if (progressFill) progressFill.style.width = `${info.progress.toFixed(1)}%`;
        if (statusLabel) statusLabel.textContent = `Renderizando fotogramas (${info.progress.toFixed(0)}%)...`;
        if (timecodeLabel) {
          timecodeLabel.textContent = `${formatTime(info.currentTime)} / ${formatTime(info.duration)} (${info.progress.toFixed(0)}%)`;
        }
        // Actualizar canvas de preview
        if (previewCanvas && info.exportCanvas) {
          const pCtx = previewCanvas.getContext('2d');
          pCtx.drawImage(info.exportCanvas, 0, 0, previewCanvas.width, previewCanvas.height);
        }
      },
      // onComplete
      (blob, filename) => {
        lastBlob = blob;
        lastFilename = filename;

        // Descargar automáticamente
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 10000);

        // Mostrar estado final
        if (progressPanel) progressPanel.style.display = 'none';
        if (successPanel) {
          successPanel.style.display = 'flex';
          const fnEl = successPanel.querySelector('#composite-success-filename');
          if (fnEl) fnEl.textContent = `Archivo generado: ${filename} (${(blob.size / (1024 * 1024)).toFixed(2)} MB)`;
        }

        this.modalFooter.innerHTML = `
          <button class="btn btn-secondary" id="btn-done-export">Cerrar</button>
          <button class="btn btn-primary" id="btn-redownload-video">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
            Descargar de Nuevo
          </button>
        `;

        this.modalFooter.querySelector('#btn-done-export').addEventListener('click', () => this.close());
        this.modalFooter.querySelector('#btn-redownload-video').addEventListener('click', () => {
          if (lastBlob && lastFilename) {
            const reUrl = URL.createObjectURL(lastBlob);
            const reA = document.createElement('a');
            reA.href = reUrl;
            reA.download = lastFilename;
            document.body.appendChild(reA);
            reA.click();
            document.body.removeChild(reA);
            setTimeout(() => URL.revokeObjectURL(reUrl), 10000);
          }
        });
      },
      // onError
      (errMsg) => {
        alert('Error durante la exportación de video: ' + errMsg);
        if (progressPanel) progressPanel.style.display = 'none';
        if (configPanel) configPanel.style.display = 'flex';
        this.modalFooter.innerHTML = `
          <button class="btn btn-secondary" id="btn-back-export-options">Volver a Formatos</button>
          <button class="btn btn-primary" id="btn-start-video-export">Reintentar</button>
        `;
        this.modalFooter.querySelector('#btn-back-export-options').addEventListener('click', () => this.openExportDialog());
        this.modalFooter.querySelector('#btn-start-video-export').addEventListener('click', () => this.runCompositeVideoExport());
      }
    );
  }

  // --- Generadores de Archivos de Exportación ---

  downloadFile(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  downloadSRT() {
    const segments = appState.state.project?.segments || [];
    const formatSrtTime = (sec) => {
      const h = Math.floor(sec / 3600);
      const m = Math.floor((sec % 3600) / 60);
      const s = Math.floor(sec % 60);
      const ms = Math.floor((sec % 1) * 1000);
      return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(ms).padStart(3, '0')}`;
    };

    let srt = '';
    segments.forEach((seg, i) => {
      srt += `${i + 1}\n`;
      srt += `${formatSrtTime(seg.start_seconds)} --> ${formatSrtTime(seg.end_seconds)}\n`;
      srt += `${seg.normalized_text || seg.original_text || ''}\n\n`;
    });

    this.downloadFile('subtitulos_lsec.srt', srt, 'text/plain;charset=utf-8');
  }

  downloadVTT() {
    const segments = appState.state.project?.segments || [];
    const formatVttTime = (sec) => {
      const m = Math.floor(sec / 60);
      const s = Math.floor(sec % 60);
      const ms = Math.floor((sec % 1) * 1000);
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
    };

    let vtt = 'WEBVTT - Subtítulos Generados LSEC Studio\n\n';
    segments.forEach((seg, i) => {
      vtt += `${i + 1}\n`;
      vtt += `${formatVttTime(seg.start_seconds)} --> ${formatVttTime(seg.end_seconds)}\n`;
      vtt += `${seg.normalized_text || seg.original_text || ''}\n\n`;
    });

    this.downloadFile('subtitulos_lsec.vtt', vtt, 'text/vtt;charset=utf-8');
  }

  downloadCSV() {
    const segments = appState.state.project?.segments || [];
    let csv = 'index,start_seconds,end_seconds,duration,normalized_text,original_text,status,gloss_sequence\n';
    segments.forEach((seg, i) => {
      const st = (seg.start_seconds !== undefined ? seg.start_seconds : (seg.start_time || 0)).toFixed(3);
      const et = (seg.end_seconds !== undefined ? seg.end_seconds : (seg.end_time || 0)).toFixed(3);
      const dur = (seg.duration !== undefined ? seg.duration : (et - st)).toFixed(3);
      const norm = `"${(seg.normalized_text || '').replace(/"/g, '""')}"`;
      const orig = `"${(seg.original_text || '').replace(/"/g, '""')}"`;
      const status = seg.status || 'DRAFT';
      const glosses = `"${(seg.gloss_sequence || []).join(' ')}"`;
      csv += `${i + 1},${st},${et},${dur},${norm},${orig},${status},${glosses}\n`;
    });
    this.downloadFile('segmentos_lsec.csv', csv, 'text/csv;charset=utf-8');
  }

  downloadELAN() {
    const project = appState.state.project || {};
    const segments = project.segments || [];
    const mediaName = project.media_info?.filename || 'video.mp4';
    const dateStr = new Date().toISOString();

    let eaf = `<?xml version="1.0" encoding="UTF-8"?>
<ANNOTATION_DOCUMENT AUTHOR="LSEC Studio" DATE="${dateStr}" FORMAT="3.0" VERSION="3.0">
  <HEADER MEDIA_FILE="" TIME_UNITS="milliseconds">
    <MEDIA_DESCRIPTOR MEDIA_URL="${mediaName}" MIME_TYPE="video/mp4" />
  </HEADER>
  <TIME_ORDER>\n`;

    segments.forEach((seg, i) => {
      const stMs = Math.round((seg.start_seconds !== undefined ? seg.start_seconds : (seg.start_time || 0)) * 1000);
      const etMs = Math.round((seg.end_seconds !== undefined ? seg.end_seconds : (seg.end_time || 0)) * 1000);
      eaf += `    <TIME_SLOT TIME_SLOT_ID="ts${i * 2 + 1}" TIME_VALUE="${stMs}" />\n`;
      eaf += `    <TIME_SLOT TIME_SLOT_ID="ts${i * 2 + 2}" TIME_VALUE="${etMs}" />\n`;
    });

    eaf += `  </TIME_ORDER>
  <TIER DEFAULT_LOCALE="es" LINGUISTIC_TYPE_REF="default-lt" TIER_ID="Transcripción_Español">\n`;

    segments.forEach((seg, i) => {
      const text = (seg.normalized_text || seg.original_text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      eaf += `    <ANNOTATION>
      <ALIGNABLE_ANNOTATION ANNOTATION_ID="a${i + 1}" TIME_SLOT_REF1="ts${i * 2 + 1}" TIME_SLOT_REF2="ts${i * 2 + 2}">
        <ANNOTATION_VALUE>${text}</ANNOTATION_VALUE>
      </ALIGNABLE_ANNOTATION>
    </ANNOTATION>\n`;
    });

    eaf += `  </TIER>
  <LINGUISTIC_TYPE GRAPHIC_REFERENCES="false" LINGUISTIC_TYPE_ID="default-lt" TIME_ALIGNABLE="true" />
  <LOCALE LANGUAGE_CODE="es" />
</ANNOTATION_DOCUMENT>`;

    this.downloadFile('anotacion_lsec.eaf', eaf, 'text/xml;charset=utf-8');
  }

  downloadGlossTXT() {
    const segments = appState.state.project.segments || [];
    let txt = 'GLOSAS LSEC — REPORTE DE EXPORTACIÓN\n\n';
    segments.forEach((seg) => {
      txt += `[${seg.start_seconds.toFixed(2)}s - ${seg.end_seconds.toFixed(2)}s] Fuente: "${seg.normalized_text}"\n`;
      txt += `GLOSAS: ${(seg.gloss_sequence || []).join(' ')}\n\n`;
    });
    this.downloadFile('glosas_lsec.txt', txt, 'text/plain;charset=utf-8');
  }

  downloadGlossJSON() {
    const content = JSON.stringify(appState.state.project, null, 2);
    this.downloadFile('lsec_2_1_1_export.json', content, 'application/json;charset=utf-8');
  }

  downloadTranscriptionTXT() {
    const text = appState.state.project.transcription?.text || '';
    this.downloadFile('transcripcion_lsec.txt', text, 'text/plain;charset=utf-8');
  }

  downloadAuditReport() {
    const p = appState.state.project;
    const meta = p.validation_metadata || {};
    const report = `# Informe de Auditoría y Validación LSEC
**Proyecto:** ${p.project_name}
**Fecha:** ${new Date().toLocaleString()}
**Estado de Ejecución:** ${p.execution_status}
**Confianza Global:** ${Math.round((meta.multidimensional_confidence?.overall || 0.88) * 100)}%

## Resumen de Validación
- Errores bloqueantes: ${meta.blocking_errors_count}
- Revisiones auditivas pendientes: ${meta.audio_reviews_count}
- Revisiones nativas LSEC pendientes: ${meta.native_reviews_count}

## Historial de Auditoría
${(p.audit_history || []).map(h => `- [${h.timestamp}] **${h.author}**: ${h.action}`).join('\n')}
`;
    this.downloadFile('informe_auditoria_lsec.md', report, 'text/markdown;charset=utf-8');
  }

  downloadProjectBundle() {
    const bundle = {
      project: appState.state.project,
      overlays: appState.state.overlays,
      exportedAt: new Date().toISOString(),
      user: appState.state.currentUser
    };
    this.downloadFile('lsec_studio_project_bundle.json', JSON.stringify(bundle, null, 2), 'application/json;charset=utf-8');
  }

  // ============================================================
  // 4. MODAL DE CONFIGURACIÓN Y ACCESIBILIDAD
  // ============================================================

  openSettingsDialog() {
    if (!this.modalBackdrop || !this.modalTitle || !this.modalBody) return;

    const ws = appState.state.workspace;

    this.modalTitle.innerHTML = 'Configuración y Accesibilidad';

    this.modalBody.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <label style="font-weight:600;">Tema Visual de la Interfaz:</label>
          <select id="set-theme-select" class="speed-select" style="padding:6px 10px;">
            <option value="dark" ${ws.theme === 'dark' ? 'selected' : ''}>Oscuro Tecnológico (Por Defecto)</option>
            <option value="light" ${ws.theme === 'light' ? 'selected' : ''}>Claro Profesional</option>
            <option value="high_contrast" ${ws.theme === 'high_contrast' ? 'selected' : ''}>Alto Contraste (WCAG AAA)</option>
          </select>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center;">
          <label style="font-weight:600;">Escala Tipográfica de la Interfaz:</label>
          <select id="set-fontscale-select" class="speed-select" style="padding:6px 10px;">
            <option value="normal" ${ws.fontSizeScale === 'normal' ? 'selected' : ''}>Estándar (100%)</option>
            <option value="large" ${ws.fontSizeScale === 'large' ? 'selected' : ''}>Grande (110%)</option>
            <option value="xlarge" ${ws.fontSizeScale === 'xlarge' ? 'selected' : ''}>Extra Grande (125%)</option>
          </select>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center;">
          <label style="font-weight:600;">Reducción de Movimiento (Reduced Motion):</label>
          <input type="checkbox" id="set-motion-reduce" ${ws.reducedMotion ? 'checked' : ''} style="width:18px; height:18px;">
        </div>

        <hr style="border:none; border-top:1px solid var(--border-subtle); margin:4px 0;">

        <div>
          <div style="font-weight:700; font-size:0.85rem; margin-bottom:8px;">Atajos de Teclado Profesionales:</div>
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:0.75rem; color:var(--text-secondary);">
            <div><kbd style="background:var(--bg-surface-3); padding:2px 6px; border-radius:3px;">Espacio / K</kbd> Reproducir / Pausa</div>
            <div><kbd style="background:var(--bg-surface-3); padding:2px 6px; border-radius:3px;">← / →</kbd> Retroceder / Avanzar 2s</div>
            <div><kbd style="background:var(--bg-surface-3); padding:2px 6px; border-radius:3px;">Shift + ← / →</kbd> Fotograma Ant. / Sig.</div>
            <div><kbd style="background:var(--bg-surface-3); padding:2px 6px; border-radius:3px;">J / L</kbd> Retroceder / Avanzar 5s</div>
            <div><kbd style="background:var(--bg-surface-3); padding:2px 6px; border-radius:3px;">M</kbd> Silenciar / Activar Sonido</div>
            <div><kbd style="background:var(--bg-surface-3); padding:2px 6px; border-radius:3px;">C</kbd> Conmutar Subtítulos ON/OFF</div>
            <div><kbd style="background:var(--bg-surface-3); padding:2px 6px; border-radius:3px;">G</kbd> Conmutar Glosas LSEC ON/OFF</div>
            <div><kbd style="background:var(--bg-surface-3); padding:2px 6px; border-radius:3px;">B</kbd> Ocultar / Mostrar Barra Inferior</div>
            <div><kbd style="background:var(--bg-surface-3); padding:2px 6px; border-radius:3px;">Ctrl / Cmd + S</kbd> Guardar Revisión</div>
          </div>
        </div>

        <div style="display:flex; justify-content:flex-end; margin-top:8px;">
          <button class="btn btn-danger btn-sm" id="btn-reset-defaults">Restaurar Valores por Defecto</button>
        </div>
      </div>
    `;

    this.modalFooter.innerHTML = `
      <button class="btn btn-primary" onclick="document.getElementById('generic-modal-backdrop').classList.remove('open')">Listo</button>
    `;

    // Eventos
    const themeSelect = this.modalBody.querySelector('#set-theme-select');
    themeSelect.addEventListener('change', (e) => appState.setTheme(e.target.value));

    const fontScaleSelect = this.modalBody.querySelector('#set-fontscale-select');
    fontScaleSelect.addEventListener('change', (e) => appState.setFontSizeScale(e.target.value));

    const motionCheck = this.modalBody.querySelector('#set-motion-reduce');
    motionCheck.addEventListener('change', (e) => {
      appState.state.workspace.reducedMotion = e.target.checked;
      if (e.target.checked) {
        document.body.classList.add('reduced-motion');
      } else {
        document.body.classList.remove('reduced-motion');
      }
    });

    const resetBtn = this.modalBody.querySelector('#btn-reset-defaults');
    resetBtn.addEventListener('click', () => {
      if (confirm('¿Restaurar todos los datos demo y configuración original?')) {
        appState.resetToDefaultProject();
        this.close();
      }
    });

    this.modalBackdrop.classList.add('open');
  }
}

// Instancia exportada
if (typeof window !== 'undefined') {
  window.ModalsAndExportController = ModalsAndExportController;
}
