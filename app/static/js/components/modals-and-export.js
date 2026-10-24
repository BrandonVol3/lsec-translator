/**
 * LSEC Studio — Controlador de Modales, Diccionario CONADIS, Proyectos y Exportación (MP4 / SRT / JSON)
 * Modularizado bajo el límite estricto de 800 líneas.
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

    const exportBtns = [
      document.getElementById('btn-top-export'),
      document.getElementById('btn-export-modal')
    ];
    exportBtns.forEach((btn) => {
      if (btn) {
        btn.addEventListener('click', () => this.openExportDialog());
      }
    });

    const dictBtn = document.getElementById('btn-dictionary-modal');
    if (dictBtn) {
      dictBtn.addEventListener('click', () => this.openDictionaryDialog());
    }

    const projBtn = document.getElementById('btn-projects-modal');
    if (projBtn) {
      projBtn.addEventListener('click', () => this.openProjectsDialog());
    }

    const settingsBtn = document.getElementById('btn-top-settings');
    if (settingsBtn) {
      settingsBtn.addEventListener('click', () => this.openSettingsDialog());
    }
  }

  openBackdrop() {
    if (this.modalBackdrop) {
      this.modalBackdrop.classList.add('open');
      this.modalBackdrop.setAttribute('aria-hidden', 'false');
    }
  }

  close() {
    if (this.modalBackdrop) {
      if (document.activeElement && this.modalBackdrop.contains(document.activeElement) && typeof document.activeElement.blur === 'function') {
        document.activeElement.blur();
      }
      this.modalBackdrop.classList.remove('open');
      this.modalBackdrop.setAttribute('aria-hidden', 'true');
    }
  }

  openExportModal() {
    return this.openExportDialog();
  }

  exportSRT() {
    return this.downloadSRT();
  }

  // --- Diccionario Oficial CONADIS (4.252 Fichas) ---
  async openDictionaryDialog() {
    if (!this.modalBackdrop || !this.modalTitle || !this.modalBody) return;
    this.modalTitle.textContent = 'Diccionario Oficial LSEC — CONADIS (4.252 Señas)';
    this.modalBody.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:12px;">
        <div style="display:flex; gap:8px;">
          <input type="text" id="dict-search-input" class="transcript-seg-input" style="min-height:38px;" placeholder="Buscar glosa o palabra en el diccionario CONADIS (ej. HOLA, EDUCACIÓN, ECUADOR)...">
          <button type="button" class="btn btn-cobalt" id="btn-dict-search-go">Buscar</button>
        </div>
        <div id="dict-search-results" style="max-height:320px; overflow-y:auto; display:flex; flex-direction:column; gap:8px;">
          <div class="empty-state-box">Escribe un término para consultar las 4.252 fichas léxicas CONADIS.</div>
        </div>
      </div>
    `;
    this.modalFooter.innerHTML = `<button class="btn" id="btn-dict-close">Cerrar</button>`;
    this.modalFooter.querySelector('#btn-dict-close')?.addEventListener('click', () => this.close());

    const inputEl = this.modalBody.querySelector('#dict-search-input');
    const resultsEl = this.modalBody.querySelector('#dict-search-results');
    const runSearch = async () => {
      const q = (inputEl?.value || '').trim();
      if (!resultsEl) return;
      try {
        const res = await fetch(`/api/v1/dictionary/search?q=${encodeURIComponent(q || 'A')}&limit=20`);
        if (res.ok) {
          const data = await res.json();
          const items = data.results || data.entries || data.items || [];
          if (items.length > 0) {
            resultsEl.innerHTML = items.map(it => `
              <div style="padding:10px 12px; border:2px solid var(--color-border-subtle); border-radius:10px; display:flex; justify-content:space-between; align-items:center;">
                <div>
                  <strong style="color:var(--color-primary-emerald-dark); font-family:var(--font-display);">${it.gloss || it.lemma || it.word}</strong>
                  <div style="font-size:0.76rem; color:var(--color-text-secondary);">${it.category || 'Léxico Oficial CONADIS'}</div>
                </div>
                <span class="gloss-chip-tactile gloss-chip-conadis" style="font-size:0.75rem; padding:3px 8px;">Seña CONADIS</span>
              </div>
            `).join('');
            return;
          }
        }
      } catch (_) {}
      resultsEl.innerHTML = `<div class="empty-state-box">Si el término "${q.toUpperCase()}" no figura en CONADIS, el motor activa automáticamente el respaldo por <strong>Dactilología</strong>.</div>`;
    };

    this.modalBody.querySelector('#btn-dict-search-go')?.addEventListener('click', runSearch);
    inputEl?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') runSearch();
    });
    this.openBackdrop();
  }

  // --- Persistencia Local de Proyectos (RF-08) ---
  openProjectsDialog() {
    if (!this.modalBackdrop || !this.modalTitle || !this.modalBody) return;
    const project = appState?.state?.project || {};
    this.modalTitle.textContent = 'Gestión y Persistencia Local de Proyectos';
    this.modalBody.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:12px;">
        <div style="padding:12px; border:2px solid var(--color-border-subtle); border-radius:12px; background:var(--color-canvas-bg);">
          <div style="font-weight:800;">Proyecto Actual: ${project.project_name || project.title || 'Proyecto LSEC'}</div>
          <div style="font-size:0.8rem; color:var(--color-text-secondary);">
            Oraciones: ${(project.segments || []).length} · Glosas LSEC: ${(project.glosses || []).length}
          </div>
        </div>
        <div style="display:flex; gap:10px; flex-wrap:wrap;">
          <button type="button" class="btn btn-primary" id="btn-proj-save-local">Guardar en Almacenamiento Local</button>
          <button type="button" class="btn btn-cobalt" id="btn-proj-download-json">Exportar Proyecto (.json)</button>
          <button type="button" class="btn" id="btn-proj-reset-demo">Restaurar Proyecto Demo</button>
        </div>
      </div>
    `;
    this.modalFooter.innerHTML = `<button class="btn" id="btn-proj-close">Cerrar</button>`;
    this.modalFooter.querySelector('#btn-proj-close')?.addEventListener('click', () => this.close());

    this.modalBody.querySelector('#btn-proj-save-local')?.addEventListener('click', () => {
      appState.saveToLocalStorage();
      if (typeof window.showToast === 'function') window.showToast('Proyecto guardado localmente.', 'success');
      this.close();
    });
    this.modalBody.querySelector('#btn-proj-download-json')?.addEventListener('click', () => {
      this.downloadProjectBundle();
    });
    this.modalBody.querySelector('#btn-proj-reset-demo')?.addEventListener('click', () => {
      appState.resetToDefaultProject();
      this.close();
    });
    this.openBackdrop();
  }

  // --- Modal de Exportación Multiformato ---
  openExportDialog() {
    if (!this.modalBackdrop || !this.modalTitle || !this.modalBody) return;
    const project = appState?.state?.project;
    if (!project) return;

    this.modalTitle.innerHTML = 'Exportar Resultados del Proyecto LSEC';
    this.modalBody.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:14px;">
        <div style="font-weight:700; font-size:0.88rem;">Selecciona el formato de exportación deseado:</div>

        <div class="export-format-grid">
          <button class="export-card-btn export-card-featured" id="btn-exp-composite-video">
            <div style="display:flex; align-items:center; justify-content:space-between; width:100%;">
              <span style="font-weight:800; color:var(--color-primary-emerald-dark); font-size:0.95rem;">Exportar Video Compuesto MP4 / WebM (Video + Subtítulos + Avatar 3D)</span>
              <span class="whisper-badge">RECOMENDADO</span>
            </div>
            <div style="font-size:0.78rem; color:var(--color-text-secondary); margin-top:4px;">
              Genera y descarga el video final con el Avatar 3D LSEC en esquina inferior derecha, glosas y subtítulos estilizados.
            </div>
          </button>

          <button class="export-card-btn" id="btn-exp-srt">
            <div style="font-weight:800; color:var(--color-accent-cobalt-dark);">Subtítulos SRT (.srt)</div>
            <div style="font-size:0.74rem; color:var(--color-text-secondary);">Formato estándar para reproductores y plataformas educativas.</div>
          </button>

          <button class="export-card-btn" id="btn-exp-vtt">
            <div style="font-weight:800; color:var(--color-accent-cobalt-dark);">WebVTT (.vtt)</div>
            <div style="font-size:0.74rem; color:var(--color-text-secondary);">Subtítulos web enriquecidos con marcas de tiempo.</div>
          </button>

          <button class="export-card-btn" id="btn-exp-gloss-txt">
            <div style="font-weight:800; color:var(--color-primary-emerald-dark);">Glosas LSEC (.txt)</div>
            <div style="font-size:0.74rem; color:var(--color-text-secondary);">Secuencia de glosas en mayúsculas por oración.</div>
          </button>

          <button class="export-card-btn" id="btn-exp-gloss-json">
            <div style="font-weight:800; color:var(--color-primary-emerald-dark);">Proyecto JSON LSEC (.json)</div>
            <div style="font-size:0.74rem; color:var(--color-text-secondary);">Esquema completo con glosas, tiempos y estilos.</div>
          </button>

          <button class="export-card-btn" id="btn-exp-csv">
            <div style="font-weight:800; color:var(--color-text-primary);">Tabla Comparativa CSV (.csv)</div>
            <div style="font-size:0.74rem; color:var(--color-text-secondary);">Oraciones en español y contraparte en glosas LSEC.</div>
          </button>
        </div>

        <button class="btn" style="width:100%;" id="btn-exp-bundle">
          Descargar Paquete Completo del Proyecto (.json bundle)
        </button>
      </div>
    `;

    this.modalFooter.innerHTML = `<button class="btn" id="btn-modal-export-close">Cerrar</button>`;
    this.modalFooter.querySelector('#btn-modal-export-close')?.addEventListener('click', () => this.close());

    this.modalBody.querySelector('#btn-exp-composite-video')?.addEventListener('click', () => this.openCompositeVideoExportDialog());
    this.modalBody.querySelector('#btn-exp-srt')?.addEventListener('click', () => this.downloadSRT());
    this.modalBody.querySelector('#btn-exp-vtt')?.addEventListener('click', () => this.downloadVTT());
    this.modalBody.querySelector('#btn-exp-gloss-txt')?.addEventListener('click', () => this.downloadGlossTXT());
    this.modalBody.querySelector('#btn-exp-gloss-json')?.addEventListener('click', () => this.downloadGlossJSON());
    this.modalBody.querySelector('#btn-exp-csv')?.addEventListener('click', () => this.downloadCSV());
    this.modalBody.querySelector('#btn-exp-bundle')?.addEventListener('click', () => this.downloadProjectBundle());

    this.openBackdrop();
  }

  openCompositeVideoExportDialog() {
    if (!this.modalBackdrop || !this.modalTitle || !this.modalBody) return;

    const project = appState.state.project || {};
    const mediaInfo = project.media_info || {};
    const duration = appState.state.playback.duration || mediaInfo.duration_seconds || 0;
    const filename = mediaInfo.filename || 'video.mp4';

    this.modalTitle.innerHTML = 'Exportar Video Compuesto con Avatar 3D LSEC y Subtítulos';
    this.modalBody.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:14px;" id="composite-export-container">
        <div style="display:flex; justify-content:space-between; align-items:center; background:var(--color-canvas-bg); padding:8px 12px; border-radius:8px; font-size:0.8rem; border:2px solid var(--color-border-subtle);">
          <div><strong>Archivo:</strong> <span>${filename}</span></div>
          <div><strong>Duración:</strong> <span style="font-family:var(--font-mono);">${duration.toFixed(2)}s</span></div>
        </div>

        <div class="export-video-config-panel" id="composite-config-panel">
          <div class="export-config-row">
            <label class="export-config-label" for="cfg-pip-position">Posición del Avatar 3D (PiP):</label>
            <select id="cfg-pip-position" class="export-config-select">
              <option value="bottom-right" selected>Inferior Derecha (Estándar LSEC)</option>
              <option value="bottom-left">Inferior Izquierda</option>
            </select>
          </div>
          <div class="export-config-row">
            <label class="export-config-label" for="cfg-resolution">Resolución de Salida:</label>
            <select id="cfg-resolution" class="export-config-select">
              <option value="original" selected>Resolución Original (Máxima Calidad)</option>
              <option value="720p">720p HD (Rápida)</option>
            </select>
          </div>
          <div class="export-config-row">
            <span class="export-config-label">Capas Incrustadas:</span>
            <div style="display:flex; gap:12px;">
              <label style="display:flex; align-items:center; gap:4px; font-size:0.8rem;">
                <input type="checkbox" id="cfg-include-avatar" checked> Avatar 3D
              </label>
              <label style="display:flex; align-items:center; gap:4px; font-size:0.8rem;">
                <input type="checkbox" id="cfg-include-glosses" checked> Glosas LSEC
              </label>
              <label style="display:flex; align-items:center; gap:4px; font-size:0.8rem;">
                <input type="checkbox" id="cfg-include-subs" checked> Subtítulos
              </label>
            </div>
          </div>
        </div>

        <div id="composite-progress-panel" style="display:none; flex-direction:column; gap:10px;">
          <div class="export-preview-box">
            <canvas id="composite-export-preview-canvas" class="export-preview-canvas" width="640" height="360"></canvas>
          </div>
          <div class="export-progress-wrap">
            <div class="export-progress-fill" id="composite-export-progress-fill"></div>
          </div>
          <div class="export-stats-row">
            <span id="composite-export-status-label">Preparando renderizado...</span>
            <span id="composite-export-timecode-label">00:00 / 00:00 (0%)</span>
          </div>
        </div>

        <div id="composite-success-panel" style="display:none; flex-direction:column; gap:8px; background:var(--color-surface-mint); border:2px solid var(--color-primary-emerald); border-radius:12px; padding:14px; text-align:center;">
          <div style="font-weight:800; font-size:0.95rem; color:var(--color-primary-emerald-dark);">¡Video compuesto exportado exitosamente!</div>
          <div style="font-size:0.78rem; color:var(--color-text-secondary);" id="composite-success-filename"></div>
        </div>
      </div>
    `;

    this.modalFooter.innerHTML = `
      <button class="btn" id="btn-back-export-options">Volver a Formatos</button>
      <button class="btn btn-primary" id="btn-start-video-export">Iniciar Renderizado y Descarga</button>
    `;

    this.modalFooter.querySelector('#btn-back-export-options')?.addEventListener('click', () => {
      if (window.compositeVideoExporter && window.compositeVideoExporter.isExporting) {
        window.compositeVideoExporter.cancelExport();
      }
      this.openExportDialog();
    });

    this.modalFooter.querySelector('#btn-start-video-export')?.addEventListener('click', () => this.runCompositeVideoExport());
    this.openBackdrop();
  }

  runCompositeVideoExport() {
    if (!window.compositeVideoExporter) return;

    const configPanel = this.modalBody.querySelector('#composite-config-panel');
    const progressPanel = this.modalBody.querySelector('#composite-progress-panel');
    const successPanel = this.modalBody.querySelector('#composite-success-panel');
    const previewCanvas = this.modalBody.querySelector('#composite-export-preview-canvas');
    const progressFill = this.modalBody.querySelector('#composite-export-progress-fill');
    const statusLabel = this.modalBody.querySelector('#composite-export-status-label');
    const timecodeLabel = this.modalBody.querySelector('#composite-export-timecode-label');

    const pipPosition = this.modalBody.querySelector('#cfg-pip-position')?.value || 'bottom-right';
    const resolution = this.modalBody.querySelector('#cfg-resolution')?.value || 'original';
    const includeInterpreter = this.modalBody.querySelector('#cfg-include-avatar')?.checked ?? true;
    const includeGlosses = this.modalBody.querySelector('#cfg-include-glosses')?.checked ?? true;
    const includeSubtitles = this.modalBody.querySelector('#cfg-include-subs')?.checked ?? true;

    if (configPanel) configPanel.style.display = 'none';
    if (progressPanel) progressPanel.style.display = 'flex';
    if (successPanel) successPanel.style.display = 'none';

    this.modalFooter.innerHTML = `<button class="btn btn-amber" id="btn-cancel-video-export">Cancelar Exportación</button>`;
    this.modalFooter.querySelector('#btn-cancel-video-export')?.addEventListener('click', () => {
      window.compositeVideoExporter.cancelExport();
      this.openCompositeVideoExportDialog();
    });

    const formatTime = (sec) => {
      const m = Math.floor(sec / 60);
      const s = Math.floor(sec % 60);
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    };

    window.compositeVideoExporter.startExport(
      { pipPosition, resolution, includeInterpreter, includeGlosses, includeSubtitles, playbackSpeed: 1.0 },
      (info) => {
        if (progressFill) progressFill.style.width = `${info.progress.toFixed(1)}%`;
        if (statusLabel) statusLabel.textContent = `Renderizando fotogramas (${info.progress.toFixed(0)}%)...`;
        if (timecodeLabel) {
          timecodeLabel.textContent = `${formatTime(info.currentTime)} / ${formatTime(info.duration)} (${info.progress.toFixed(0)}%)`;
        }
        if (previewCanvas && info.exportCanvas) {
          const pCtx = previewCanvas.getContext('2d');
          pCtx.drawImage(info.exportCanvas, 0, 0, previewCanvas.width, previewCanvas.height);
        }
      },
      (blob, filename) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 10000);

        if (progressPanel) progressPanel.style.display = 'none';
        if (successPanel) {
          successPanel.style.display = 'flex';
          const fnEl = successPanel.querySelector('#composite-success-filename');
          if (fnEl) fnEl.textContent = `Archivo generado: ${filename} (${(blob.size / (1024 * 1024)).toFixed(2)} MB)`;
        }
        this.modalFooter.innerHTML = `<button class="btn btn-primary" id="btn-done-export">Cerrar</button>`;
        this.modalFooter.querySelector('#btn-done-export')?.addEventListener('click', () => this.close());
      },
      (errMsg) => {
        if (typeof window.showToast === 'function') window.showToast('Error en exportación: ' + errMsg, 'error');
        this.openCompositeVideoExportDialog();
      }
    );
  }

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
      const val = Number(sec) || 0;
      const h = Math.floor(val / 3600);
      const m = Math.floor((val % 3600) / 60);
      const s = Math.floor(val % 60);
      const ms = Math.floor((val % 1) * 1000);
      return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(ms).padStart(3, '0')}`;
    };

    let srt = '';
    segments.forEach((seg, i) => {
      const st = seg.start_seconds ?? seg.start_time ?? 0;
      const et = seg.end_seconds ?? seg.end_time ?? (st + 2);
      srt += `${i + 1}\n`;
      srt += `${formatSrtTime(st)} --> ${formatSrtTime(et)}\n`;
      srt += `${seg.normalized_text || seg.original_text || seg.raw_text || ''}\n\n`;
    });

    this.downloadFile('subtitulos_lsec.srt', srt, 'text/plain;charset=utf-8');
    if (typeof window.showToast === 'function') window.showToast('Archivo subtitulos_lsec.srt descargado.', 'success');
  }

  downloadVTT() {
    const segments = appState.state.project?.segments || [];
    const formatVttTime = (sec) => {
      const val = Number(sec) || 0;
      const m = Math.floor(val / 60);
      const s = Math.floor(val % 60);
      const ms = Math.floor((val % 1) * 1000);
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
    };

    let vtt = 'WEBVTT - Subtítulos Generados LSEC Studio\n\n';
    segments.forEach((seg, i) => {
      const st = seg.start_seconds ?? seg.start_time ?? 0;
      const et = seg.end_seconds ?? seg.end_time ?? (st + 2);
      vtt += `${i + 1}\n`;
      vtt += `${formatVttTime(st)} --> ${formatVttTime(et)}\n`;
      vtt += `${seg.normalized_text || seg.original_text || seg.raw_text || ''}\n\n`;
    });

    this.downloadFile('subtitulos_lsec.vtt', vtt, 'text/vtt;charset=utf-8');
  }

  downloadCSV() {
    const segments = appState.state.project?.segments || [];
    let csv = 'index,start_seconds,end_seconds,normalized_text,status,gloss_sequence\n';
    segments.forEach((seg, i) => {
      const st = Number(seg.start_seconds ?? seg.start_time ?? 0).toFixed(3);
      const et = Number(seg.end_seconds ?? seg.end_time ?? 0).toFixed(3);
      const norm = `"${(seg.normalized_text || seg.raw_text || '').replace(/"/g, '""')}"`;
      const status = seg.status || 'VALIDATED';
      const glosses = `"${(seg.gloss_sequence || []).join(' ')}"`;
      csv += `${i + 1},${st},${et},${norm},${status},${glosses}\n`;
    });
    this.downloadFile('segmentos_lsec.csv', csv, 'text/csv;charset=utf-8');
  }

  downloadGlossTXT() {
    const segments = appState.state.project?.segments || [];
    let txt = 'GLOSAS LSEC — REPORTE DE EXPORTACIÓN\n\n';
    segments.forEach((seg) => {
      const st = Number(seg.start_seconds ?? seg.start_time ?? 0).toFixed(2);
      const et = Number(seg.end_seconds ?? seg.end_time ?? 0).toFixed(2);
      txt += `[${st}s - ${et}s] Fuente: "${seg.normalized_text || seg.raw_text || ''}"\n`;
      txt += `GLOSAS: ${(seg.gloss_sequence || []).join(' ')}\n\n`;
    });
    this.downloadFile('glosas_lsec.txt', txt, 'text/plain;charset=utf-8');
  }

  downloadGlossJSON() {
    const content = JSON.stringify(appState.state.project, null, 2);
    this.downloadFile('lsec_export.json', content, 'application/json;charset=utf-8');
  }

  downloadProjectBundle() {
    const bundle = {
      project: appState.state.project,
      overlays: appState.state.overlays,
      exportedAt: new Date().toISOString()
    };
    this.downloadFile('lsec_studio_project_bundle.json', JSON.stringify(bundle, null, 2), 'application/json;charset=utf-8');
  }

  openSettingsDialog() {
    if (!this.modalBackdrop || !this.modalTitle || !this.modalBody) return;
    const ws = appState.state.workspace;
    this.modalTitle.innerHTML = 'Configuración y Accesibilidad Visual';
    this.modalBody.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <label for="set-theme-select" style="font-weight:700;">Tema Visual:</label>
          <select id="set-theme-select" class="speed-select">
            <option value="light" ${ws.theme === 'light' ? 'selected' : ''}>Pedagogical Tactile Light (Por Defecto)</option>
            <option value="high-contrast" ${ws.theme === 'high-contrast' ? 'selected' : ''}>Alto Contraste (WCAG AAA)</option>
            <option value="dark" ${ws.theme === 'dark' ? 'selected' : ''}>Oscuro Auxiliar</option>
          </select>
        </div>
      </div>
    `;
    this.modalFooter.innerHTML = `<button class="btn btn-primary" id="btn-modal-settings-done">Listo</button>`;
    this.modalFooter.querySelector('#btn-modal-settings-done')?.addEventListener('click', () => this.close());
    this.modalBody.querySelector('#set-theme-select')?.addEventListener('change', (e) => appState.setTheme(e.target.value));
    this.openBackdrop();
  }
}

if (typeof window !== 'undefined') {
  window.ModalsAndExportController = ModalsAndExportController;
}
