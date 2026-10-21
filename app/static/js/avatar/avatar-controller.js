/**
 * LSEC Studio — Controlador Principal del Avatar 3D (AvatarPanelController)
 * 
 * Integra todos los subsistemas del avatar 3D:
 * - Motor de renderizado (AvatarEngine);
 * - Rig técnico de reserva (TechnicalRig);
 * - Cargador de modelos VRM 1.0 (VRMLoaderService);
 * - Reproductor de clips esqueléticos (SignPlayer);
 * - Secuenciador de glosas continuas (SignSequencer);
 * - Sincronizador lingüístico con LSEC Studio (AvatarSyncController);
 * - Gestión de interfaz, botones, selectores y avisos de validación;
 * - Monitoreo de rendimiento en tiempo real (FPS, memoria, tiempos de carga, consola).
 */

import { AvatarEngine } from './avatar-engine.js';
import { TechnicalRig } from './technical-rig.js';
import { VRMLoaderService } from './vrm-loader.js';
import { SignPlayer } from './sign-player.js';
import { SignSequencer } from './sign-sequencer.js';
import { AvatarSyncController } from './avatar-sync-controller.js';
import { NonManualController } from './non-manual-controller.js';
import {
  getAllTechnicalClips,
  getTechnicalClipsCategorized,
  createNeutralClip,
  createSaludarDemoClip,
  createNegacionDemoClip
} from './sign-clip-factory.js';
import { defaultAnimationCache } from './animation-cache.js';
import { validateSignClip } from './sign-animation-schema.js';
import { HUMAN_BONE_NAMES } from './sign-animation-schema.js';
import {
  trimSignClipStroke,
  convertDirectAnimationToSignClip
} from './sign-animation-schema.js';

const BONE_LOWER_MAP = new Map((HUMAN_BONE_NAMES || []).map(b => [b.toLowerCase(), b]));

const BONE_ALIASES = {
  'j_bip_c_hips': 'hips',
  'j_bip_c_spine': 'spine',
  'j_bip_c_chest': 'chest',
  'j_bip_c_upperchest': 'upperChest',
  'j_bip_c_neck': 'neck',
  'j_bip_c_head': 'head',
  'j_bip_l_eye': 'leftEye',
  'j_bip_r_eye': 'rightEye',
  'j_bip_l_shoulder': 'leftShoulder',
  'j_bip_l_upperarm': 'leftUpperArm',
  'j_bip_l_lowerarm': 'leftLowerArm',
  'j_bip_l_hand': 'leftHand',
  'j_bip_l_thumb1': 'leftThumbMetacarpal',
  'j_bip_l_thumb2': 'leftThumbProximal',
  'j_bip_l_thumb3': 'leftThumbDistal',
  'j_bip_l_index1': 'leftIndexProximal',
  'j_bip_l_index2': 'leftIndexIntermediate',
  'j_bip_l_index3': 'leftIndexDistal',
  'j_bip_l_middle1': 'leftMiddleProximal',
  'j_bip_l_middle2': 'leftMiddleIntermediate',
  'j_bip_l_middle3': 'leftMiddleDistal',
  'j_bip_l_ring1': 'leftRingProximal',
  'j_bip_l_ring2': 'leftRingIntermediate',
  'j_bip_l_ring3': 'leftRingDistal',
  'j_bip_l_little1': 'leftLittleProximal',
  'j_bip_l_little2': 'leftLittleIntermediate',
  'j_bip_l_little3': 'leftLittleDistal',
  'j_bip_r_shoulder': 'rightShoulder',
  'j_bip_r_upperarm': 'rightUpperArm',
  'j_bip_r_lowerarm': 'rightLowerArm',
  'j_bip_r_hand': 'rightHand',
  'j_bip_r_thumb1': 'rightThumbMetacarpal',
  'j_bip_r_thumb2': 'rightThumbProximal',
  'j_bip_r_thumb3': 'rightThumbDistal',
  'j_bip_r_index1': 'rightIndexProximal',
  'j_bip_r_index2': 'rightIndexIntermediate',
  'j_bip_r_index3': 'rightIndexDistal',
  'j_bip_r_middle1': 'rightMiddleProximal',
  'j_bip_r_middle2': 'rightMiddleIntermediate',
  'j_bip_r_middle3': 'rightMiddleDistal',
  'j_bip_r_ring1': 'rightRingProximal',
  'j_bip_r_ring2': 'rightRingIntermediate',
  'j_bip_r_ring3': 'rightRingDistal',
  'j_bip_r_little1': 'rightLittleProximal',
  'j_bip_r_little2': 'rightLittleIntermediate',
  'j_bip_r_little3': 'rightLittleDistal',
  'wrist': 'rightHand',
  'r_wrist': 'rightHand',
  'l_wrist': 'leftHand',
  'righthandthumb1': 'rightThumbMetacarpal',
  'righthandthumb2': 'rightThumbProximal',
  'righthandthumb3': 'rightThumbDistal',
  'righthandindex1': 'rightIndexProximal',
  'righthandindex2': 'rightIndexIntermediate',
  'righthandindex3': 'rightIndexDistal',
  'righthandmiddle1': 'rightMiddleProximal',
  'righthandmiddle2': 'rightMiddleIntermediate',
  'righthandmiddle3': 'rightMiddleDistal',
  'righthandring1': 'rightRingProximal',
  'righthandring2': 'rightRingIntermediate',
  'righthandring3': 'rightRingDistal',
  'righthandpinky1': 'rightLittleProximal',
  'righthandpinky2': 'rightLittleIntermediate',
  'righthandpinky3': 'rightLittleDistal'
};

function normalizeBoneName(name) {
  if (typeof name !== 'string') return name;
  const clean = name.replace(/^mixamorig:?/i, '').trim();
  const lower = clean.toLowerCase();
  if (BONE_ALIASES[lower]) return BONE_ALIASES[lower];
  if (BONE_LOWER_MAP.has(lower)) return BONE_LOWER_MAP.get(lower);
  return clean;
}

function detectDatasetQuaternionLayout(data) {
  const meta = (data && data.metadata) || {};
  const explicit = (meta.quaternionOrder || meta.quaternionFormat || data.quaternionOrder || data.quaternionFormat || '').toLowerCase();
  if (explicit.includes('wxyz') || explicit.includes('[w, x, y, z]') || explicit.includes('[w,x,y,z]')) return 'wxyz';
  if (explicit.includes('xyzw') || explicit.includes('[x, y, z, w]') || explicit.includes('[x,y,z,w]')) return 'xyzw';

  let wxyzVotes = 0;
  let xyzwVotes = 0;

  const voteQuat = (q) => {
    if (!Array.isArray(q) || q.length < 4) return;
    const a = Number(q[0]) || 0;
    const d = Number(q[3]) || 0;
    if (Math.abs(a) > 0.7 && Math.abs(d) < 0.35) wxyzVotes++;
    else if (Math.abs(d) > 0.7 && Math.abs(a) < 0.35) xyzwVotes++;
  };

  if (Array.isArray(data.frames)) {
    for (const f of data.frames.slice(0, 10)) {
      if (f && f.rotations && typeof f.rotations === 'object') {
        for (const q of Object.values(f.rotations)) {
          voteQuat(q);
        }
      }
    }
  } else if (data.extractedTracks && typeof data.extractedTracks === 'object') {
    for (const track of Object.values(data.extractedTracks)) {
      if (track && Array.isArray(track.quaternions)) {
        for (const q of track.quaternions.slice(0, 10)) {
          voteQuat(q);
        }
      }
    }
  }

  return (wxyzVotes > xyzwVotes) ? 'wxyz' : 'xyzw';
}

export class AvatarPanelController {
  constructor(panelContainerId = 'view-side-avatar') {
    this.container = document.getElementById(panelContainerId);

    // Subsistemas
    this.engine = null;
    this.vrmLoader = null;
    this.technicalRig = null;
    this.player = null;
    this.sequencer = null;
    this.syncController = null;
    this.nonManual = null;

    // Estado del modelo
    this.isVRMActive = false;
    this.currentModelSource = 'TECHNICAL_RIG'; // 'TECHNICAL_RIG' | 'VRM_LOCAL'
    this.preferredVersion = '2.7';

    // Catálogo de clips técnicos precargados
    this.clips = getAllTechnicalClips();
    this.clipLoaders = {};
    this.categories = getTechnicalClipsCategorized();
    this.selectedClipId = 'SALUDAR_DEMO';

    // Métricas de Rendimiento en Tiempo Real
    this.perfMetrics = {
      loadTimeMs: 0,
      fps: 60,
      frameCount: 0,
      lastFpsTime: (typeof performance !== 'undefined' ? performance.now() : 0),
      usedMemoryMB: 0,
      consoleErrors: 0,
      consoleWarnings: 0
    };

    this.setupConsoleMonitoring();
    this.init();
  }

  setupConsoleMonitoring() {
    if (window.__avatarConsoleMonitored) return;
    window.__avatarConsoleMonitored = true;

    const originalError = console.error;
    const originalWarn = console.warn;

    console.error = (...args) => {
      this.perfMetrics.consoleErrors++;
      originalError.apply(console, args);
    };

    console.warn = (...args) => {
      this.perfMetrics.consoleWarnings++;
      originalWarn.apply(console, args);
    };
  }

  init() {
    if (this.container && !this.container.querySelector('#avatar-webgl-canvas')) {
      this.buildDOM();
    }
    this.bindDOM();
    this.initSubsystems();
    this.initClipsCache();
    this.loadManifestClips();
    this.loadInitialAvatar();
  }

  renderClipOptions() {
    if (!this.selectClip) return;
    const optionsHtml = this.categories.map((group) => {
      const options = group.clips.map((c) => {
        const isSelected = c.id === this.selectedClipId ? 'selected' : '';
        return `<option value="${c.id}" ${isSelected}>${c.label}</option>`;
      }).join('\n');
      return `<optgroup label="${group.groupName}">\n${options}\n</optgroup>`;
    }).join('\n');
    this.selectClip.innerHTML = optionsHtml;
  }

  async loadManifestClips() {
    try {
      const res = await fetch(`/static/assets/clips/manifest.json?t=${Date.now()}`);
      if (!res.ok) return;
      const manifest = await res.json();
      if (manifest && manifest.clips) {
        const weekClips = [];
        const numberClips = [];
        const vocabClips = [];
        const labelMap = {
          'LUNES': '📅 Lunes (LSEC — Queirema L, Vaivén)',
          'MARTES': '📅 Martes (LSEC — Queirema M, Doble Descenso)',
          'MIERCOLES': '📅 Miércoles (LSEC — Queirema M, Vaivén Pectoral)',
          'JUEVES': '📅 Jueves (LSEC — Queirema J, Trazo Curvo)',
          'VIERNES': '📅 Viernes (LSEC — Queirema V, Vaivén)',
          'SABADO': '📅 Sábado (LSEC — Queirema Y, Diagonal ↙)',
          'DOMINGO': '📅 Domingo (LSEC — Cruz en Frente)'
        };

        const weekDayKeys = ['LUNES', 'MARTES', 'MIERCOLES', 'JUEVES', 'VIERNES', 'SABADO', 'DOMINGO'];
        const numeralRegex = /^(CERO|UNO|DOS|TRES|CUATRO|CINCO|SEIS|SIETE|OCHO|NUEVE|DIEZ|ONCE|DOCE|VEINTE|TREINTA|CUARENTA|CINCUENTA|CIEN|MIL|MILLON)(_\d+)?$/i;
        const seenNormalizedKeys = new Set();

        for (const [glossKey, clipMeta] of Object.entries(manifest.clips)) {
          const normKey = String(glossKey).normalize('NFC').toUpperCase().trim();
          const loaderFn = async () => {
            // 1. Intentar resolver versión activa (por defecto 2.7 estandarizada) desde la API REST
            const activeVer = this.preferredVersion || '2.7';
            if (typeof fetch === 'function') {
              const endpoints = [
                `/api/animations-direct/resolve/${encodeURIComponent(normKey)}?version=${encodeURIComponent(activeVer)}`,
                `/api/v1/animations/resolve/${encodeURIComponent(normKey)}?version=${encodeURIComponent(activeVer)}`
              ];
              for (const url of endpoints) {
                try {
                  const directRes = await fetch(url);
                  if (directRes && directRes.ok) {
                    const payload = await directRes.json();
                    const directData = (payload && typeof payload === 'object' && 'animation' in payload)
                      ? payload.animation
                      : payload;
                    if (directData && !directData.boneTracks && (Array.isArray(directData.frames) || directData.extractedTracks)) {
                      let clip = this.convertHamerAnimationToSignClip(directData, clipMeta.clipId || normKey);
                      clip = trimSignClipStroke(clip);
                      defaultAnimationCache.setClip(`${activeVer}_${clip.clipId}`, clip);
                      return clip;
                    }
                  }
                } catch (e) {
                  // Fallback silencioso ante modo offline
                }
              }
            }

            // 2. Fallback estático desde /static/assets/clips/
            const clipRes = await fetch(`/static/assets/clips/${clipMeta.file}?t=${Date.now()}`);
            let clipData = await clipRes.json();
            if (clipData && !clipData.boneTracks && (Array.isArray(clipData.frames) || clipData.extractedTracks)) {
              clipData = this.convertHamerAnimationToSignClip(clipData, clipMeta.clipId || normKey);
              clipData = trimSignClipStroke(clipData);
            }
            if (clipData && !clipData.clipId) {
              clipData.clipId = clipMeta.clipId || normKey;
            }
            defaultAnimationCache.setClip(clipData.clipId, clipData);
            return clipData;
          };

          // Registrar cargador tanto en clave original como normalizada en mayúsculas
          this.clips[glossKey] = loaderFn;
          this.clips[normKey] = loaderFn;
          this.clipLoaders[glossKey] = loaderFn;
          this.clipLoaders[normKey] = loaderFn;

          // Evitar duplicados por diferencias de mayúsculas/minúsculas en el selector UI
          if (seenNormalizedKeys.has(normKey)) continue;
          seenNormalizedKeys.add(normKey);

          const isWeekDay = weekDayKeys.includes(normKey);
          const isNumeral = !isWeekDay && numeralRegex.test(normKey);

          if (isWeekDay) {
            const label = labelMap[normKey] || `📅 ${normKey} (LSEC)`;
            weekClips.push({ id: normKey, label });
          } else if (isNumeral) {
            numberClips.push({ id: normKey, label: `🔢 ${normKey} (LSEC)` });
          } else {
            vocabClips.push({ id: normKey, label: `🤟 ${normKey} (LSEC)` });
          }
        }

        vocabClips.sort((a, b) => a.id.localeCompare(b.id, 'es'));

        // Categoría de Días de la Semana
        const weekCategory = {
          groupName: '📅 Días de la Semana (Glosario LSEC)',
          clips: weekClips
        };

        // Categoría de Numerales
        const numberCategory = {
          groupName: '🔢 Números y Cantidades (LSEC)',
          clips: numberClips
        };

        // Categoría de Vocabulario General LSEC
        const vocabCategory = {
          groupName: '🤟 Vocabulario y Léxico LSEC',
          clips: vocabClips
        };

        const dynamicGroups = [
          weekCategory,
          ...(numberClips.length > 0 ? [numberCategory] : []),
          ...(vocabClips.length > 0 ? [vocabCategory] : [])
        ];

        // Reemplazar o anteponer categorías
        const existingWeekIdx = this.categories.findIndex(c => c.groupName.includes('Léxico LSEC') || c.groupName.includes('Días de la Semana'));
        if (existingWeekIdx >= 0) {
          this.categories.splice(existingWeekIdx, 1, ...dynamicGroups);
        } else {
          this.categories.unshift(...dynamicGroups);
        }

        this.renderClipOptions();
        console.info(`[AvatarPanelController] ${weekClips.length} días, ${numberClips.length} numerales y ${vocabClips.length} señas léxicas cargadas desde manifest.json`);
      }
    } catch (err) {
      console.warn('[AvatarPanelController] No se pudo cargar manifest.json:', err);
    }
  }

  buildDOM() {
    if (!this.container) return;

    // Generar opciones categorizadas para el selector
    const optionsHtml = this.categories.map((group) => {
      const options = group.clips.map((c) => {
        const isSelected = c.id === this.selectedClipId ? 'selected' : '';
        return `<option value="${c.id}" ${isSelected}>${c.label}</option>`;
      }).join('\n');
      return `<optgroup label="${group.groupName}">\n${options}\n</optgroup>`;
    }).join('\n');

    this.container.innerHTML = `
      <!-- Cabecera del Panel del Avatar -->
      <div class="avatar-panel-header">
        <div class="avatar-title-cluster">
          <div class="avatar-icon-badge" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2zM7.5 13A1.5 1.5 0 0 0 6 14.5 1.5 1.5 0 0 0 7.5 16 1.5 1.5 0 0 0 9 14.5 1.5 1.5 0 0 0 7.5 13zm9 0a1.5 1.5 0 0 0-1.5 1.5 1.5 1.5 0 0 0 1.5 1.5 1.5 1.5 0 0 0 1.5-1.5 1.5 1.5 0 0 0-1.5-1.5z"/>
            </svg>
          </div>
          <div>
            <h3 class="avatar-panel-title">Avatar 3D (LSEC)</h3>
            <span class="avatar-model-pill" id="avatar-model-source-info">Rig Técnico Activo</span>
          </div>
        </div>

        <div class="avatar-header-badges">
          <a href="/avatarconfig" class="btn btn-secondary btn-sm" id="btn-open-avatar-config-page" title="Abrir entorno dedicado de calibración (/avatarconfig)" style="text-decoration:none; font-size:0.65rem; padding:2px 6px; display:inline-flex; align-items:center; gap:3px;">
            <span>Calibración ↗</span>
          </a>
          <span class="unvalidated-warning-badge" id="avatar-unvalidated-notice" title="Las animaciones actuales son demostraciones técnicas no validadas lingüísticamente por la comunidad sorda">
            DEMO NO VALIDADA
          </span>
          <span class="avatar-status-badge" id="avatar-playback-status-badge">Inactivo</span>
        </div>
      </div>

      <!-- Viewport 3D WebGL con HUD reactivo -->
      <div class="avatar-viewport-container" id="avatar-viewport-wrap">
        <canvas id="avatar-webgl-canvas" class="avatar-canvas"></canvas>

        <!-- Indicador de Carga -->
        <div class="avatar-overlay-loading" id="avatar-loading-indicator" style="display:none;">
          <div class="avatar-spinner"></div>
          <span id="avatar-loading-text">Cargando modelo...</span>
        </div>

        <!-- Banner de Error / Información -->
        <div class="avatar-overlay-error" id="avatar-error-banner" style="display:none;">
          <div class="avatar-error-content">
            <span class="avatar-error-icon">⚠️</span>
            <span class="avatar-error-msg" id="avatar-error-message">Error de inicialización.</span>
            <button class="btn btn-secondary btn-sm" id="btn-avatar-error-retry">Reintentar</button>
          </div>
        </div>

        <!-- HUD superior con Glosa Activa, Rendimiento y Tiempo -->
        <div class="avatar-hud-top" id="avatar-hud-bar">
          <div class="avatar-hud-gloss">
            <span class="avatar-hud-label">PRUEBA:</span>
            <span class="avatar-hud-value" id="avatar-active-gloss-hud">—</span>
          </div>
          <div class="avatar-hud-perf">
            <span class="avatar-perf-badge" id="avatar-hud-perf-badge" title="Rendimiento en tiempo real (FPS | Heap)">60 FPS</span>
          </div>
          <div class="avatar-hud-time">
            <span id="avatar-hud-time-current">0.00s</span>
            <span style="opacity:0.4;">/</span>
            <span id="avatar-hud-time-total">0.00s</span>
          </div>
        </div>

        <!-- Barra de progreso temporal discreta -->
        <div class="avatar-viewport-progress-track">
          <div class="avatar-viewport-progress-fill" id="avatar-clip-progress-fill"></div>
        </div>

        <!-- Botón flotante para recentrar cámara -->
        <button class="btn-avatar-hud-action" id="btn-avatar-reset-camera" title="Recentrar cámara frontal" aria-label="Recentrar cámara frontal">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
        </button>

        <!-- DOCK FLOTANTE DE CONTROLES DE CÁMARA (Girar, Mover, Deslizar) -->
        <div class="avatar-cam-floating-dock dock-collapsed" id="avatar-cam-dock" aria-label="Controles de Cámara 3D">
          <div class="avatar-cam-dock-header">
            <span class="avatar-cam-dock-title">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
              Controles 3D
            </span>
            <button class="avatar-cam-dock-toggle" id="btn-cam-dock-toggle" title="Minimizar / Expandir panel de cámara" aria-label="Alternar panel de cámara 3D">▸</button>
          </div>
          
          <div class="avatar-cam-dock-body" id="avatar-cam-dock-body" style="display:none;">
            <!-- Girar (Órbita 360°) -->
            <div class="avatar-cam-tool-section">
              <div class="avatar-cam-section-label">Girar (Órbita)</div>
              <div class="avatar-cam-dpad-row">
                <button class="avatar-cam-btn" id="btn-cam-rot-left" title="Girar a la izquierda">↺ Izq</button>
                <button class="avatar-cam-btn" id="btn-cam-rot-up" title="Inclinar arriba">▲ Arr</button>
                <button class="avatar-cam-btn" id="btn-cam-rot-down" title="Inclinar abajo">▼ Aba</button>
                <button class="avatar-cam-btn" id="btn-cam-rot-right" title="Girar a la derecha">Der ↻</button>
              </div>
            </div>

            <!-- Mover (Desplazamiento / Pan) -->
            <div class="avatar-cam-tool-section">
              <div class="avatar-cam-section-label">Mover (Desplazamiento)</div>
              <div class="avatar-cam-grid-dpad">
                <button class="avatar-cam-btn avatar-cam-btn-up" id="btn-cam-pan-up" title="Mover hacia arriba" aria-label="Mover cámara arriba">▲</button>
                <div class="avatar-cam-dpad-mid">
                  <button class="avatar-cam-btn" id="btn-cam-pan-left" title="Mover a la izquierda" aria-label="Mover cámara izquierda">◄</button>
                  <button class="avatar-cam-btn avatar-cam-btn-center" id="btn-cam-pan-center" title="Recentrar vista" aria-label="Recentrar vista">●</button>
                  <button class="avatar-cam-btn" id="btn-cam-pan-right" title="Mover a la derecha" aria-label="Mover cámara derecha">►</button>
                </div>
                <button class="avatar-cam-btn avatar-cam-btn-down" id="btn-cam-pan-down" title="Mover hacia abajo" aria-label="Mover cámara abajo">▼</button>
              </div>
            </div>

            <!-- Deslizar (Dolly / Zoom) -->
            <div class="avatar-cam-tool-section">
              <div class="avatar-cam-section-label">Deslizar (Zoom)</div>
              <div class="avatar-cam-dpad-row">
                <button class="avatar-cam-btn" id="btn-cam-zoom-in" title="Acercar cámara (Dolly In)">
                  <span>＋ Acercar</span>
                </button>
                <button class="avatar-cam-btn" id="btn-cam-zoom-out" title="Alejar cámara (Dolly Out)">
                  <span>－ Alejar</span>
                </button>
              </div>
            </div>

            <!-- Hint Badge -->
            <div class="avatar-cam-hint-badge">
              <span class="avatar-cam-hint-icon">💡</span>
              <span>Arrastrar: Girar<br>Clic Der / Shift: Mover<br>Rueda: Deslizar Zoom</span>
            </div>
          </div>
        </div>

        <!-- Indicador flotante en la base del visor -->
        <div class="avatar-viewport-cam-hint" id="avatar-viewport-cam-hint">
          <span>🖱️ Arrastrar: Girar</span>
          <span>•</span>
          <span>Clic Der: Mover</span>
          <span>•</span>
          <span>Rueda: Deslizar</span>
        </div>
      </div>

      <!-- Barra de Controles de Reproducción y Secuenciación -->
      <div class="avatar-controls-panel">
        
        <!-- Fila 1: Selección de Clip / Prueba, Versión de Catálogo y Velocidad -->
        <div class="avatar-controls-row">
          <div class="avatar-control-group" style="flex:1; min-width: 140px;">
            <label for="select-avatar-clip" class="avatar-control-label">Prueba / Clip:</label>
            <select id="select-avatar-clip" class="avatar-select" style="flex:1;">
              ${optionsHtml}
            </select>
          </div>

          <div class="avatar-control-group">
            <label for="select-avatar-version" class="avatar-control-label">Catálogo:</label>
            <select id="select-avatar-version" class="avatar-select" style="min-width:118px;" title="Versión de animaciones VRM LSEC (v2.7 Estandarizado, v2.6 Directo 1:1 Corregido, v2.5 Original)">
              <option value="2.7" selected>v2.7 Estandarizado</option>
              <option value="2.6">v2.6 Directo 1:1</option>
              <option value="2.5">v2.5 Original</option>
            </select>
          </div>

          <div class="avatar-control-group">
            <label for="select-avatar-speed" class="avatar-control-label">Velocidad:</label>
            <select id="select-avatar-speed" class="avatar-select" style="min-width:64px;">
              <option value="0.25">0.25x</option>
              <option value="0.5">0.5x</option>
              <option value="0.75">0.75x</option>
              <option value="1.0" selected>1.0x</option>
              <option value="1.25">1.25x</option>
              <option value="1.5">1.5x</option>
              <option value="2.0">2.0x</option>
            </select>
          </div>
        </div>

        <!-- Fila 2: Botones de Acción Individual y Secuenciación -->
        <div class="avatar-controls-row avatar-buttons-row">
          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button class="btn btn-primary btn-sm" id="btn-avatar-play" title="Reproducir prueba seleccionada (Espacio)">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
              <span>Reproducir</span>
            </button>
            <button class="btn btn-secondary btn-sm" id="btn-avatar-pause" title="Pausar animación">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
              <span>Pausar</span>
            </button>
            <button class="btn btn-secondary btn-sm" id="btn-avatar-reset" title="Reiniciar y restaurar postura neutral">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg>
              <span>Reiniciar</span>
            </button>
          </div>

          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button class="btn btn-action-step btn-action-primary btn-sm" id="btn-avatar-play-sequence" title="Reproducir secuencia de demostración básica">
              <span>▶ Secuencia Básica</span>
            </button>
            <button class="btn btn-secondary btn-sm" id="btn-avatar-play-week" style="background:linear-gradient(135deg, #059669 0%, #047857 100%); border-color:#059669; color:#fff;" title="Reproducir secuencia completa de los 7 días de la semana (Lunes a Domingo)">
              <span>📅 7 Días Semana</span>
            </button>
            <button class="btn btn-secondary btn-sm" id="btn-avatar-play-all-tests" title="Ejecutar batería continua de todas las pruebas técnicas (22 clips)">
              <span>⚡ Batería Pruebas (22)</span>
            </button>
          </div>
        </div>

        <!-- Barra de Presets y Herramientas Rápidas de Cámara -->
        <div class="avatar-cam-presets-bar">
          <div class="avatar-cam-presets-group">
            <span style="font-size:0.72rem; color:var(--text-muted); font-weight:600; margin-right:4px;">Cámara:</span>
            <button class="avatar-cam-preset-btn active" id="btn-cam-medium" title="Vista plano medio">Plano Medio</button>
            <button class="avatar-cam-preset-btn" id="btn-cam-full" title="Vista de cuerpo entero">Cuerpo</button>
            <button class="avatar-cam-preset-btn" id="btn-cam-face" title="Vista rostro y mirada">Rostro</button>
            <button class="avatar-cam-preset-btn" id="btn-cam-hands" title="Vista manos y señas">Manos / Sien</button>

            <div class="avatar-cam-tools-compact">
              <button class="avatar-cam-icon-btn" id="btn-quick-rot-left" title="Girar izquierda ↺" aria-label="Girar izquierda">↺</button>
              <button class="avatar-cam-icon-btn" id="btn-quick-rot-right" title="Girar derecha ↻" aria-label="Girar derecha">↻</button>
              <button class="avatar-cam-icon-btn" id="btn-quick-zoom-in" title="Acercar ＋" aria-label="Acercar cámara">＋</button>
              <button class="avatar-cam-icon-btn" id="btn-quick-zoom-out" title="Alejar －" aria-label="Alejar cámara">－</button>
              <button class="avatar-cam-icon-btn" id="btn-quick-cam-dock-toggle" title="Dock de controles 3D" aria-label="Alternar controles de cámara 3D">🎮</button>
            </div>
          </div>
        </div>

        <!-- Fila 3: Carga de Archivo VRM Local -->
        <div class="avatar-vrm-load-row">
          <input type="file" id="avatar-vrm-file-input" accept=".vrm,.glb" style="display:none;" aria-label="Cargar modelo de avatar VRM o GLB">
          <button class="btn btn-secondary btn-sm" id="btn-avatar-load-vrm" style="width:100%; justify-content:center;">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16h6v-6h4l-7-7-7 7h4v6zm-4 2h14v2H5v-2z"/></svg>
            <span>Cargar Avatar VRM 1.0 (.vrm local)</span>
          </button>
        </div>

        <!-- Fila 4: Edición Manual y Carga de Señas Corregidas -->
        <div class="avatar-clip-edit-row" style="display:flex; flex-direction:column; gap:6px; margin-top:8px; padding-top:8px; border-top:1px dashed var(--border-subtle);">
          <div style="font-size:0.75rem; font-weight:600; color:var(--text-secondary); display:flex; align-items:center; gap:5px;">
            <span>✏️ Edición Manual de Señas (Blender / JSON)</span>
          </div>
          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button class="btn btn-secondary btn-sm" id="btn-avatar-export-clip" style="flex:1; justify-content:center;" title="Exportar la seña actualmente seleccionada (ej. LUNES) como archivo JSON para referencia o edición">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
              <span>Exportar Seña</span>
            </button>
            <input type="file" id="avatar-clip-file-input" accept=".json" style="display:none;" aria-label="Cargar animación de seña corregida JSON">
            <button class="btn btn-primary btn-sm" id="btn-avatar-import-clip" style="flex:1; justify-content:center; background:linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%); border-color:#2563EB;" title="Cargar seña corregida o personalizada (.json) y visualizar en el avatar">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16h6v-6h4l-7-7-7 7h4v6zm-4 2h14v2H5v-2z"/></svg>
              <span>Cargar Seña Corregida</span>
            </button>
          </div>
        </div>

      </div>

      <!-- Tarjeta Informativa de Trazabilidad y Descargo -->
      <div class="avatar-disclaimer-card">
        <div class="avatar-disclaimer-header">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="color:var(--status-review);"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
          <strong>Verificación Técnica — No son señas LSEC validadas</strong>
        </div>
        <p class="avatar-disclaimer-text">
          Las poses y clips técnicos ejecutan pruebas biomecánicas de falanges, orientaciones, componentes 
          no manuales y rendimiento. No constituyen realizaciones lingüísticas validadas de LSEC. 
          Requieren validación participativa con personas sordas señantes nativas.
        </p>
      </div>
    `;
  }

  bindDOM() {
    if (!this.container) return;
    const findEl = (sel) => (this.container ? this.container.querySelector(sel) : null) || document.querySelector(sel);

    this.canvas = findEl('#avatar-webgl-canvas');
    this.statusBadge = findEl('#avatar-playback-status-badge');
    this.modelSourcePill = findEl('#avatar-model-source-info');
    this.activeGlossHud = findEl('#avatar-active-gloss-hud');
    this.hudPerfBadge = findEl('#avatar-hud-perf-badge');
    this.timeCurrentEl = findEl('#avatar-hud-time-current');
    this.timeTotalEl = findEl('#avatar-hud-time-total');
    this.progressBarFill = findEl('#avatar-clip-progress-fill');
    this.loadingIndicator = findEl('#avatar-loading-indicator');
    this.errorBanner = findEl('#avatar-error-banner');
    this.errorMessageEl = findEl('#avatar-error-message');

    // Botones
    this.btnPlay = findEl('#btn-avatar-play');
    this.btnPause = findEl('#btn-avatar-pause');
    this.btnReset = findEl('#btn-avatar-reset');
    this.btnPlaySeq = findEl('#btn-avatar-play-sequence');
    this.btnPlayAllTests = findEl('#btn-avatar-play-all-tests');
    this.btnPlayWeek = findEl('#btn-avatar-play-week');
    this.btnLoadVrm = findEl('#btn-avatar-load-vrm');
    this.btnResetCam = findEl('#btn-avatar-reset-camera');
    this.btnRetry = findEl('#btn-avatar-error-retry');
    this.fileInputVrm = findEl('#avatar-vrm-file-input');

    // Botones de Importación y Exportación de Señas
    this.btnExportClip = findEl('#btn-avatar-export-clip');
    this.btnImportClip = findEl('#btn-avatar-import-clip');
    this.fileInputClip = findEl('#avatar-clip-file-input');

    // Selectores
    this.selectClip = findEl('#select-avatar-clip');
    this.selectVersion = findEl('#select-avatar-version');
    this.selectSpeed = findEl('#select-avatar-speed');

    // Poblar selector de clips si no tiene opciones previas
    if (this.selectClip && this.selectClip.children.length === 0) {
      const optionsHtml = this.categories.map((group) => {
        const options = group.clips.map((c) => {
          const isSelected = c.id === this.selectedClipId ? 'selected' : '';
          return `<option value="${c.id}" ${isSelected}>${c.label}</option>`;
        }).join('\n');
        return `<optgroup label="${group.groupName}">\n${options}\n</optgroup>`;
      }).join('\n');
      this.selectClip.innerHTML = optionsHtml;
    }

    // Listeners principales
    if (this.btnPlay) this.btnPlay.addEventListener('click', () => this.playCurrentSelection());
    if (this.btnPause) this.btnPause.addEventListener('click', () => this.pause());
    if (this.btnReset) this.btnReset.addEventListener('click', () => this.reset());
    if (this.btnPlaySeq) this.btnPlaySeq.addEventListener('click', () => this.playDemoSequence());
    if (this.btnPlayAllTests) this.btnPlayAllTests.addEventListener('click', () => this.playAllTestsSequence());
    if (this.btnPlayWeek) this.btnPlayWeek.addEventListener('click', () => this.playWeekSequence());
    if (this.btnResetCam) this.btnResetCam.addEventListener('click', () => this.resetCamera());

    // Helper para acciones continuas al mantener presionado un botón
    const bindContinuousAction = (btn, actionFn) => {
      if (!btn) return;
      let timer = null;
      const startAction = (e) => {
        if (e) e.preventDefault();
        actionFn();
        if (timer) clearInterval(timer);
        timer = setInterval(() => {
          actionFn();
        }, 70);
      };
      const stopAction = () => {
        if (timer) {
          clearInterval(timer);
          timer = null;
        }
      };

      btn.addEventListener('mousedown', startAction);
      btn.addEventListener('mouseup', stopAction);
      btn.addEventListener('mouseleave', stopAction);
      btn.addEventListener('touchstart', startAction, { passive: false });
      btn.addEventListener('touchend', stopAction);
      btn.addEventListener('touchcancel', stopAction);
    };

    // Controles de Rotación / Giro (Órbita 360°)
    bindContinuousAction(findEl('#btn-cam-rot-left'), () => this.rotateCamera(-4, 0));
    bindContinuousAction(findEl('#btn-cam-rot-right'), () => this.rotateCamera(4, 0));
    bindContinuousAction(findEl('#btn-cam-rot-up'), () => this.rotateCamera(0, -4));
    bindContinuousAction(findEl('#btn-cam-rot-down'), () => this.rotateCamera(0, 4));
    bindContinuousAction(findEl('#btn-quick-rot-left'), () => this.rotateCamera(-6, 0));
    bindContinuousAction(findEl('#btn-quick-rot-right'), () => this.rotateCamera(6, 0));

    // Controles de Traslación / Desplazamiento (Pan)
    bindContinuousAction(findEl('#btn-cam-pan-left'), () => this.panCamera(-1, 0));
    bindContinuousAction(findEl('#btn-cam-pan-right'), () => this.panCamera(1, 0));
    bindContinuousAction(findEl('#btn-cam-pan-up'), () => this.panCamera(0, 1));
    bindContinuousAction(findEl('#btn-cam-pan-down'), () => this.panCamera(0, -1));
    const btnPanCenter = findEl('#btn-cam-pan-center');
    if (btnPanCenter) btnPanCenter.addEventListener('click', () => this.resetCamera());

    // Controles de Deslizamiento / Zoom (Dolly)
    bindContinuousAction(findEl('#btn-cam-zoom-in'), () => this.dollyCamera(0.12));
    bindContinuousAction(findEl('#btn-cam-zoom-out'), () => this.dollyCamera(-0.12));
    bindContinuousAction(findEl('#btn-quick-zoom-in'), () => this.dollyCamera(0.15));
    bindContinuousAction(findEl('#btn-quick-zoom-out'), () => this.dollyCamera(-0.15));

    // Presets de Cámara
    const presetBtns = {
      medium: findEl('#btn-cam-medium'),
      full: findEl('#btn-cam-full'),
      face: findEl('#btn-cam-face'),
      hands: findEl('#btn-cam-hands')
    };

    Object.entries(presetBtns).forEach(([preset, btn]) => {
      if (!btn) return;
      btn.addEventListener('click', () => {
        this.setCameraPreset(preset);
      });
    });

    // Toggle de Dock Flotante de Cámara
    const camDock = findEl('#avatar-cam-dock');
    const dockBody = findEl('#avatar-cam-dock-body');
    const dockToggle = findEl('#btn-cam-dock-toggle');
    const quickDockToggle = findEl('#btn-quick-cam-dock-toggle');

    const toggleDock = () => {
      if (!dockBody) return;
      const isHidden = dockBody.style.display === 'none';
      dockBody.style.display = isHidden ? 'flex' : 'none';
      if (camDock) camDock.classList.toggle('dock-collapsed', !isHidden);
      if (dockToggle) dockToggle.textContent = isHidden ? '▾' : '▸';
    };

    if (dockToggle) dockToggle.addEventListener('click', toggleDock);
    if (quickDockToggle) quickDockToggle.addEventListener('click', toggleDock);

    if (this.selectClip) {
      this.selectClip.addEventListener('change', (e) => {
        this.selectedClipId = e.target.value;
        this.prepareSelectedClip();
      });
    }

    if (this.selectVersion) {
      this.selectVersion.addEventListener('change', (e) => {
        this.setAnimationVersion(e.target.value);
      });
    }

    if (this.selectSpeed) {
      this.selectSpeed.addEventListener('change', (e) => {
        const rate = parseFloat(e.target.value) || 1.0;
        this.setSpeed(rate);
      });
    }

    if (this.btnLoadVrm && this.fileInputVrm) {
      this.btnLoadVrm.addEventListener('click', () => {
        this.fileInputVrm.click();
      });

      this.fileInputVrm.addEventListener('change', (e) => {
        const file = e.target.files && e.target.files[0];
        if (file) {
          this.loadVRMFromFile(file);
        }
      });
    }

    // Manejo de exportación e importación de clips de señas
    if (this.btnExportClip) {
      this.btnExportClip.addEventListener('click', () => {
        this.exportCurrentClip();
      });
    }

    if (this.btnImportClip && this.fileInputClip) {
      this.btnImportClip.addEventListener('click', () => {
        this.fileInputClip.click();
      });

      this.fileInputClip.addEventListener('change', async (e) => {
        const file = e.target.files && e.target.files[0];
        if (file) {
          try {
            await this.importCustomClip(file);
          } finally {
            // Limpiar valor en finally para permitir recargar el mismo archivo si se edita de nuevo
            this.fileInputClip.value = '';
          }
        }
      });
    }

    if (this.btnRetry) {
      this.btnRetry.addEventListener('click', () => {
        this.hideError();
        this.loadInitialAvatar();
      });
    }

    // Drag & Drop directo de archivos (.json o .vrm) sobre el viewport 3D
    const viewportWrap = findEl('#avatar-viewport-wrap') || this.canvas;
    if (viewportWrap) {
      viewportWrap.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.dataTransfer) {
          e.dataTransfer.dropEffect = 'copy';
        }
      });
      viewportWrap.addEventListener('drop', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!e.dataTransfer || !e.dataTransfer.files || e.dataTransfer.files.length === 0) return;
        for (const file of e.dataTransfer.files) {
          const name = file.name.toLowerCase();
          if (name.endsWith('.json')) {
            await this.importCustomClip(file);
          } else if (name.endsWith('.vrm') || name.endsWith('.glb')) {
            await this.loadVRMFromFile(file);
          }
        }
      });
    }
  }

  initSubsystems() {
    try {
      // 1. Motor Three.js
      this.engine = new AvatarEngine(this.canvas);

      // 2. Cargador VRM
      this.vrmLoader = new VRMLoaderService();

      // 3. Rig Técnico de Reserva
      this.technicalRig = new TechnicalRig();

      // 4. Reproductor
      this.player = new SignPlayer();

      // 5. Secuenciador
      this.sequencer = new SignSequencer(this.player);

      // 6. Sincronizador lingüístico
      this.syncController = new AvatarSyncController(this.sequencer);

      // 7. No manuales
      this.nonManual = new NonManualController();

      // 8. Fachada de mixer determinista (para exportación offline cuadro por cuadro a 30 FPS)
      this.mixer = {
        update: (dt) => this.stepDeterministic(dt)
      };
      this.lastPlayedResolutionMeta = null;
      this.onPreUpdateCallback = null;

      // Conectar loop de renderizado del motor con el secuenciador y perfilador de rendimiento
      this.engine.setUpdateCallback((delta) => {
        if (typeof this.onPreUpdateCallback === 'function') {
          this.onPreUpdateCallback(delta);
        }
        this.sequencer.update(delta);
        this.updateFPSMetrics();
      });

      // Callbacks de progreso y estado
      this.player.onProgress = ({ currentTime, duration, progress }) => {
        this.updateTimeDisplay(currentTime, duration);
        if (this.progressBarFill) {
          this.progressBarFill.style.width = `${(progress * 100).toFixed(1)}%`;
        }
      };

      this.player.onStateChange = (state) => {
        this.updateStatusDisplay(state);
      };

      this.sequencer.onGlossChanged = ({ gloss, clipId, index, total }) => {
        if (this.activeGlossHud) {
          this.activeGlossHud.textContent = gloss || '—';
        }
        this.updateStatusDisplay(`Secuencia: ${index + 1}/${total}`);
      };

      this.sequencer.onSequenceEnded = () => {
        this.updateStatusDisplay('Completado');
        if (this.activeGlossHud) {
          this.activeGlossHud.textContent = 'NEUTRAL';
        }
      };

      // Iniciar ciclo de renderizado
      this.engine.start();

      console.info('[AvatarPanelController] Subsistemas del avatar inicializados correctamente.');
    } catch (err) {
      console.error('[AvatarPanelController] Error al inicializar subsistemas:', err);
      this.showError('No se pudo inicializar WebGL o Three.js en este navegador.');
    }
  }

  initClipsCache() {
    for (const [id, clip] of Object.entries(this.clips)) {
      if (clip && typeof clip === 'object') {
        defaultAnimationCache.setClip(clip.clipId || `${id}_V1`, clip);
      }
    }
  }

  updateFPSMetrics() {
    this.perfMetrics.frameCount++;
    const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
    const elapsed = now - this.perfMetrics.lastFpsTime;

    if (elapsed >= 500) {
      this.perfMetrics.fps = Math.round((this.perfMetrics.frameCount * 1000) / elapsed);
      this.perfMetrics.frameCount = 0;
      this.perfMetrics.lastFpsTime = now;

      if (typeof performance !== 'undefined' && performance.memory) {
        this.perfMetrics.usedMemoryMB = (performance.memory.usedJSHeapSize / (1024 * 1024)).toFixed(1);
      }

      this.updatePerfDisplay();
    }
  }

  updatePerfDisplay() {
    if (this.hudPerfBadge) {
      const memText = this.perfMetrics.usedMemoryMB > 0 ? ` | ${this.perfMetrics.usedMemoryMB} MB` : '';
      this.hudPerfBadge.textContent = `${this.perfMetrics.fps} FPS${memText}`;
      if (this.perfMetrics.fps >= 50) {
        this.hudPerfBadge.style.color = 'var(--action-primary)';
      } else if (this.perfMetrics.fps >= 30) {
        this.hudPerfBadge.style.color = 'var(--status-review)';
      } else {
        this.hudPerfBadge.style.color = 'var(--status-error)';
      }
    }
  }

  /**
   * Reporte estructurado de rendimiento para inspección y testing automatizado.
   */
  getPerformanceReport() {
    return {
      loadTimeMs: this.perfMetrics.loadTimeMs,
      fps: this.perfMetrics.fps,
      usedMemoryMB: this.perfMetrics.usedMemoryMB,
      isVRMActive: this.isVRMActive,
      modelSource: this.currentModelSource,
      consoleErrors: this.perfMetrics.consoleErrors,
      consoleWarnings: this.perfMetrics.consoleWarnings
    };
  }

  /**
   * Intenta cargar el avatar inicial:
   * 1. Carga el modelo predeterminado LSEC-Interpreter-Female.vrm.
   * 2. Si no se puede cargar, activa el Rig Técnico de Reserva.
   */
  async loadInitialAvatar() {
    this.showLoading(true, 'Verificando avatar VRM...');

    const candidates = [
      '/avatar/LSEC-Interpreter-Female.vrm',
      '/static/assets/LSEC-Interpreter-Female.vrm'
    ];

    for (const vrmUrl of candidates) {
      try {
        const check = await fetch(vrmUrl, { method: 'HEAD' });
        if (check.ok) {
          console.info(`[AvatarPanelController] Avatar VRM detectado en: ${vrmUrl}`);
          await this.loadVRMFromUrl(vrmUrl);
          return;
        }
      } catch (e) {
        // Continuar con el siguiente candidato
      }
    }

    console.info('[AvatarPanelController] Modelo VRM no detectado en las rutas estándar. Activando Rig Técnico de Reserva.');
    this.activateTechnicalRig();
    this.showLoading(false);
  }

  activateTechnicalRig() {
    this.isVRMActive = false;
    this.currentModelSource = 'TECHNICAL_RIG';

    this.engine.setModel(this.technicalRig, false);
    this.player.setModel(this.technicalRig, false);
    this.nonManual.setModel(this.technicalRig, false);

    if (this.modelSourcePill) {
      this.modelSourcePill.textContent = 'Rig Técnico (Reserva)';
      this.modelSourcePill.className = 'avatar-model-pill avatar-pill-rig';
    }

    this.prepareSelectedClip();
  }

  /**
   * Carga un modelo VRM provisto como archivo local (vía file input o drag&drop).
   * @param {File} file 
   */
  async loadVRMFromFile(file) {
    if (!file) return;
    this.showLoading(true, `Cargando ${file.name}...`);
    this.hideError();
    const t0 = performance.now();

    try {
      const vrm = await this.vrmLoader.loadVRM(file);
      this.perfMetrics.loadTimeMs = Math.round(performance.now() - t0);
      this.onVRMLoadSuccess(vrm, file.name);
    } catch (err) {
      console.error('[AvatarPanelController] Fallo al cargar VRM desde archivo:', err);
      this.showError(`Error al cargar avatar VRM (${file.name}). Se mantiene el Rig de reserva.`);
      this.activateTechnicalRig();
    } finally {
      this.showLoading(false);
    }
  }

  /**
   * Carga un modelo VRM desde una URL.
   * @param {string} url 
   */
  async loadVRMFromUrl(url) {
    this.showLoading(true, 'Descargando avatar VRM...');
    this.hideError();
    const t0 = performance.now();

    try {
      const vrm = await this.vrmLoader.loadVRM(url);
      this.perfMetrics.loadTimeMs = Math.round(performance.now() - t0);
      const fileName = url.split('/').pop() || 'avatar.vrm';
      this.onVRMLoadSuccess(vrm, fileName);
    } catch (err) {
      console.warn('[AvatarPanelController] No se pudo cargar avatar VRM desde URL. Activando rig de reserva.', err);
      this.activateTechnicalRig();
    } finally {
      this.showLoading(false);
    }
  }

  onVRMLoadSuccess(vrm, sourceName) {
    this.isVRMActive = true;
    this.currentModelSource = 'VRM_LOCAL';

    // Aplicar mejoras visuales: sombreado Toon, sombras suaves y realce de silueta de dedos
    this.applyToonVisualShading(vrm);

    this.engine.setModel(vrm, true);
    this.player.setModel(vrm, true);
    this.nonManual.setModel(vrm, true);

    if (this.modelSourcePill) {
      this.modelSourcePill.textContent = `VRM 1.0 (${sourceName})`;
      this.modelSourcePill.className = 'avatar-model-pill avatar-pill-vrm';
    }

    this.prepareSelectedClip();
  }

  /**
   * Configura sombras suaves y ajusta los materiales Toon (MToon) del avatar VRM
   * para destacar la silueta de los dedos y brindar volumen tridimensional.
   */
  applyToonVisualShading(vrm) {
    if (!vrm || !vrm.scene) return;
    if (this.engine && this.engine.renderer) {
      this.engine.renderer.shadowMap.enabled = true;
      if (typeof THREE !== 'undefined' && THREE.PCFSoftShadowMap) {
        this.engine.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      }
    }
    vrm.scene.traverse((obj) => {
      if (obj.isMesh) {
        obj.castShadow = true;
        obj.receiveShadow = true;
        if (obj.material) {
          const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
          for (const mat of mats) {
            // Ajuste fino para materiales MToon de VRM
            if (mat.isMToonMaterial || mat.type === 'MToonMaterial' || mat.userData?.vrmMaterial) {
              if (mat.shadeShift !== undefined) mat.shadeShift = -0.10;
              if (mat.shadeToony !== undefined) mat.shadeToony = 0.85;
              if (mat.rimLightingMixFactor !== undefined) mat.rimLightingMixFactor = 0.80;
              if (mat.rimMultiply !== undefined) mat.rimMultiply = 1.25;
              if (mat.outlineWidthFactor !== undefined && mat.outlineWidthFactor > 0) {
                mat.outlineWidthFactor = Math.max(mat.outlineWidthFactor, 0.0035);
              }
            } else if (mat.isMeshStandardMaterial) {
              mat.roughness = Math.min(mat.roughness, 0.65);
            }
          }
        }
      }
    });
  }

  async _resolveClipForSelection(rawKey) {
    const nfcKey = String(rawKey || 'NEUTRAL').normalize('NFC').trim();
    const upperKey = nfcKey.toUpperCase();
    const activeVer = this.preferredVersion || '2.7';

    const loader = this.clipLoaders && (this.clipLoaders[rawKey] || this.clipLoaders[nfcKey] || this.clipLoaders[upperKey]);
    let clip = this.clips[rawKey] || this.clips[nfcKey] || this.clips[upperKey];

    const clipVer = clip && typeof clip === 'object'
      ? (clip.metadata?.versionServed || clip.metadata?.version_served || clip.metadata?.standardizedVersion)
      : null;

    if (typeof clip === 'function') {
      try {
        clip = await clip();
        if (clip) {
          this.clips[rawKey] = clip;
          this.clips[nfcKey] = clip;
          this.clips[upperKey] = clip;
        }
      } catch (e) {
        console.error('Error al resolver clip dinámico:', e);
        clip = null;
      }
    } else if (loader && clipVer && String(clipVer) !== String(activeVer)) {
      try {
        clip = await loader();
        if (clip) {
          this.clips[rawKey] = clip;
          this.clips[nfcKey] = clip;
          this.clips[upperKey] = clip;
        }
      } catch (e) {
        console.error('Error al recargar clip dinámico para nueva versión:', e);
      }
    } else if ((!clip || (clipVer && String(clipVer) !== String(activeVer) && !clip.metadata?.isCustomImport)) && this.syncController && upperKey !== 'NEUTRAL') {
      try {
        const fetched = await this.syncController.loadClipAsync(nfcKey, { version: activeVer });
        if (fetched) {
          clip = fetched;
          this.clips[rawKey] = clip;
          this.clips[nfcKey] = clip;
          this.clips[upperKey] = clip;
        }
      } catch (e) {
        // Silencioso si no existe en catálogo directo
      }
    }

    return clip || this.clips.NEUTRAL;
  }

  async prepareSelectedClip() {
    const rawKey = this.selectedClipId || 'NEUTRAL';
    const clip = await this._resolveClipForSelection(rawKey);
    if (this.player) {
      this.player.loadClip(clip);
    }

    if (this.activeGlossHud && clip) {
      this.activeGlossHud.textContent = clip.gloss || '';
    }

    const duration = this.player ? this.player.getDuration() : ((clip && clip.durationMs ? clip.durationMs / 1000 : 0));
    this.updateTimeDisplay(0, duration);
    if (this.progressBarFill) {
      this.progressBarFill.style.width = '0%';
    }
    return clip;
  }

  async playCurrentSelection() {
    this.hideError();
    if (this.player) this.player.externalPoseControl = false;
    if (typeof window !== 'undefined' && window.studioAvatarBridge) {
      window.studioAvatarBridge.isManualPreviewActive = true;
    }
    const rawKey = this.selectedClipId || 'NEUTRAL';
    const clip = await this._resolveClipForSelection(rawKey);
    if (this.activeGlossHud && clip) {
      this.activeGlossHud.textContent = clip.gloss;
    }
    if (this.player && clip) {
      this.player.play(clip);
    }
  }

  pause() {
    if (this.sequencer.sequence.length > 0) {
      this.sequencer.pause();
    } else {
      this.player.pause();
    }
  }

  reset() {
    if (this.player) this.player.externalPoseControl = false;
    if (this.sequencer.sequence.length > 0) {
      this.sequencer.cancel();
    }
    this.player.reset();
    this.prepareSelectedClip();
    this.updateStatusDisplay('Inactivo');
  }

  setSpeed(rate) {
    this.player.setSpeed(rate);
    this.sequencer.setSpeed(rate);
  }

  /**
   * Cambia la versión activa del catálogo de señas VRM ('2.7' estandarizado, '2.6' directo corregido, '2.5' original)
   * y recarga la seña actual para comparación inmediata.
   * @param {string} version
   */
  async setAnimationVersion(version) {
    const ver = (version === '2.5' || version === '2.6') ? version : '2.7';
    this.preferredVersion = ver;
    if (this.selectVersion && this.selectVersion.value !== ver) {
      this.selectVersion.value = ver;
    }
    if (this.syncController && typeof this.syncController.setPreferredVersion === 'function') {
      this.syncController.setPreferredVersion(ver);
    }
    if (this.clipLoaders) {
      for (const [k, fn] of Object.entries(this.clipLoaders)) {
        this.clips[k] = fn;
      }
    }
    const noticeEl = this.container ? this.container.querySelector('#avatar-unvalidated-notice') : null;
    if (noticeEl) {
      noticeEl.textContent = ver === '2.7' ? 'CATÁLOGO v2.7 ESTANDARIZADO' : (ver === '2.6' ? 'CATÁLOGO v2.6 DIRECTO 1:1' : 'CATÁLOGO v2.5 ORIGINAL');
    }
    await this.prepareSelectedClip();
    if (typeof window !== 'undefined' && window.studioAvatarBridge) {
      if (typeof window.studioAvatarBridge.clearClipCache === 'function') {
        window.studioAvatarBridge.clearClipCache(ver);
      } else {
        window.studioAvatarBridge.clipMap?.clear();
        window.studioAvatarBridge.currentGlossKey = null;
      }
      if (window.appState?.state?.project) {
        await window.studioAvatarBridge.preloadProjectSigns(window.appState.state.project);
        const currentTime = window.appState.state.playback?.currentTime || 0;
        window.studioAvatarBridge.onTimeUpdate(currentTime);
      }
    }
    return ver;
  }

  /**
   * Reproduce la secuencia demostrativa básica:
   * NEUTRAL -> SALUDAR_DEMO -> NEGACION_DEMO -> NEUTRAL
   */
  playDemoSequence() {
    this.hideError();
    if (this.player) this.player.externalPoseControl = false;
    if (typeof window !== 'undefined' && window.studioAvatarBridge) {
      window.studioAvatarBridge.isManualPreviewActive = true;
    }
    const sequence = [
      this.clips.NEUTRAL,
      this.clips.SALUDAR_DEMO,
      this.clips.NEGACION_DEMO,
      this.clips.NEUTRAL
    ];

    this.sequencer.playSequence(sequence);
  }

  /**
   * Reproduce la secuencia completa de los 7 Días de la Semana en LSEC:
   * NEUTRAL -> LUNES -> MARTES -> MIERCOLES -> JUEVES -> VIERNES -> SABADO -> DOMINGO -> NEUTRAL
   */
  async playWeekSequence() {
    this.hideError();
    if (this.player) this.player.externalPoseControl = false;
    if (typeof window !== 'undefined' && window.studioAvatarBridge) {
      window.studioAvatarBridge.isManualPreviewActive = true;
    }
    const weekDays = ['LUNES', 'MARTES', 'MIERCOLES', 'JUEVES', 'VIERNES', 'SABADO', 'DOMINGO'];
    const sequence = [this.clips.NEUTRAL || createNeutralClip()];

    for (const day of weekDays) {
      let clip = this.clips[day];
      if (typeof clip === 'function') {
        try {
          clip = await clip();
          this.clips[day] = clip;
        } catch (e) {
          console.error(`[AvatarPanelController] Error al resolver clip dinámico de ${day}:`, e);
        }
      }
      if (clip) {
        sequence.push(clip);
      } else {
        console.warn(`[AvatarPanelController] Clip no disponible para el día: ${day}`);
      }
    }
    sequence.push(this.clips.NEUTRAL || createNeutralClip());

    console.info(`[AvatarPanelController] Iniciando secuencia de ${sequence.length - 2} días de la semana...`);
    this.sequencer.playSequence(sequence);
  }

  /**
   * Reproduce la batería continua completa de todas las pruebas técnicas.
   */
  playAllTestsSequence() {
    this.hideError();
    if (this.player) this.player.externalPoseControl = false;
    if (typeof window !== 'undefined' && window.studioAvatarBridge) {
      window.studioAvatarBridge.isManualPreviewActive = true;
    }
    const sequence = [
      this.clips.NEUTRAL,
      this.clips.TEST_MANO_ABIERTA,
      this.clips.TEST_PUNO,
      this.clips.TEST_INDICE_EXTENDIDO,
      this.clips.TEST_DOS_DEDOS,
      this.clips.TEST_PINZA,
      this.clips.TEST_MANO_CURVA,
      this.clips.TEST_GARRA,
      this.clips.TEST_DEDOS_JUNTOS_SEPARADOS,
      this.clips.TEST_ORIENTACION_PALMA,
      this.clips.TEST_PRONACION_SUPINACION,
      this.clips.TEST_FLEXION_MUNICA_CODO,
      this.clips.TEST_CNM_HEAD_SHAKE,
      this.clips.TEST_CNM_HEAD_NOD,
      this.clips.TEST_CNM_HEAD_TILT,
      this.clips.TEST_CNM_MIRADA,
      this.clips.TEST_CNM_CEJAS,
      this.clips.TEST_CNM_PARPADEO,
      this.clips.TEST_CNM_BOCA,
      this.clips.TEST_SIMULTANEO_MANOS_CABEZA,
      this.clips.TEST_SIMULTANEO_MANOS_MIRADA,
      this.clips.TEST_SIMULTANEO_MANOS_EXPRESION,
      this.clips.TEST_SIMULTANEO_COMPLEJO_TOTAL,
      this.clips.NEUTRAL
    ].filter(Boolean);

    this.sequencer.playSequence(sequence);
  }

  /**
   * Notificación cuando el panel o pestaña "Avatar 3D" se hace visible.
   */
  onTabActivated() {
    if (this.engine) {
      this.engine.onResize();
      if (!this.engine.isRunning) {
        this.engine.start();
      }
    }
  }

  updateTimeDisplay(curr, total) {
    if (this.timeCurrentEl) this.timeCurrentEl.textContent = `${curr.toFixed(2)}s`;
    if (this.timeTotalEl) this.timeTotalEl.textContent = `${total.toFixed(2)}s`;
  }

  updateStatusDisplay(status) {
    if (this.statusBadge) {
      this.statusBadge.textContent = status;
      this.statusBadge.setAttribute('data-state', status.toLowerCase());
    }
  }

  showLoading(show, text = 'Cargando...') {
    if (!this.loadingIndicator) return;
    this.loadingIndicator.style.display = show ? 'flex' : 'none';
    const textEl = this.container.querySelector('#avatar-loading-text');
    if (textEl) textEl.textContent = text;
  }

  showError(msg) {
    if (!this.errorBanner) return;
    this.errorBanner.style.display = 'flex';
    if (this.errorMessageEl) this.errorMessageEl.textContent = msg;
  }

  hideError() {
    if (this.errorBanner) this.errorBanner.style.display = 'none';
  }

  setCameraPreset(preset) {
    if (!this.engine) return;
    this.engine.setCameraPreset(preset);
    this.syncPresetButtons(preset);
  }

  syncPresetButtons(preset) {
    const findEl = (sel) => (this.container ? this.container.querySelector(sel) : null) || document.querySelector(sel);
    const presetMap = {
      pip_bust: findEl('#btn-cam-pip-bust'),
      medium: findEl('#btn-cam-medium'),
      full: findEl('#btn-cam-full'),
      face: findEl('#btn-cam-face'),
      hands: findEl('#btn-cam-hands')
    };
    Object.entries(presetMap).forEach(([k, btn]) => {
      if (btn) {
        if (k === preset) btn.classList.add('active');
        else btn.classList.remove('active');
      }
    });
  }

  /**
   * Reproduce una glosa lingüística por nombre en el avatar.
   * Maneja glosas léxicas (v2.7 estandarizada preferida -> v2.6 -> v2.5 -> local) y dactilología pendiente.
   * @param {string} glossName
   * @param {Object} [options]
   * @param {boolean} [options.isFingerspelling=false]
   * @returns {Promise<boolean>}
   */
  async playGloss(glossName, options = {}) {
    if (!glossName) {
      this.reset();
      return false;
    }

    if (this.player) {
      this.player.externalPoseControl = false;
    }

    const clean = glossName.trim();
    const isSingleLetterHyphenated = clean.includes('-')
      && clean.split('-').filter(Boolean).every(p => p.trim().length === 1);
    const isFingerspelling = Boolean(
      options.isFingerspelling || isSingleLetterHyphenated || options.gloss_type === 'DACTILOLOGÍA'
    );

    // Directriz: Dactilología / Glosas letra por letra quedan pendientes por el momento.
    // El avatar permanece en pose neutra/reposo con manos abajo sin trabar la interfaz.
    if (isFingerspelling) {
      if (this.activeGlossHud) {
        this.activeGlossHud.textContent = clean;
      }
      this.lastPlayedResolutionMeta = {
        found: false,
        matchType: 'fingerspelling',
        needsReview: false,
        warning: null,
        resolvedGloss: clean,
        isFingerspelling: true
      };
      if (this.clips && this.clips.NEUTRAL) {
        this.player?.play(this.clips.NEUTRAL, { coarticulate: true, returnToNeutralOnEnd: false });
      } else {
        this.player?.reset();
      }
      return true;
    }

    if (this.activeGlossHud) {
      this.activeGlossHud.textContent = clean;
    }

    let clip = null;
    const reqVersion = options.version || this.preferredVersion || '2.7';
    if (this.syncController) {
      clip = await this.syncController.loadClipAsync(clean, { version: reqVersion });
      const resMeta = typeof this.syncController.getResolutionMeta === 'function'
        ? this.syncController.getResolutionMeta(clean, reqVersion)
        : (typeof this.syncController.getResolutionMetadata === 'function' ? this.syncController.getResolutionMetadata(clean, reqVersion) : null);
      if (resMeta) {
        this.lastPlayedResolutionMeta = resMeta;
        if (resMeta.isFingerspelling) {
          if (this.clips && this.clips.NEUTRAL) {
            this.player?.play(this.clips.NEUTRAL, { coarticulate: true, returnToNeutralOnEnd: false });
          } else {
            this.player?.reset();
          }
          return true;
        }
      }
    }

    if (!clip && this.clips) {
      clip = this.clips[clean.toUpperCase()] || this.clips[clean];
      if (typeof clip === 'function') {
        try {
          clip = await clip();
        } catch {
          clip = null;
        }
      }
    }

    if (clip && this.player) {
      let targetSpeed = 1.0;
      if (typeof options.slotDurationSec === 'number' && options.slotDurationSec > 0 && clip.durationMs > 0) {
        const clipSec = clip.durationMs / 1000.0;
        const fitRatio = clipSec / Math.max(0.24, options.slotDurationSec);
        const baseRate = (typeof options.basePlaybackRate === 'number' && options.basePlaybackRate > 0)
          ? options.basePlaybackRate
          : 1.0;
        targetSpeed = Math.max(0.70, Math.min(1.6, fitRatio)) * baseRate;
      } else if (typeof options.speed === 'number' && options.speed > 0) {
        targetSpeed = options.speed;
      } else if (clip.metadata && typeof clip.metadata.recommendedSpeed === 'number') {
        targetSpeed = Math.min(1.6, clip.metadata.recommendedSpeed);
      }
      this.player.setSpeed(targetSpeed);
      this.player.play(clip, {
        coarticulate: options.coarticulate !== undefined ? options.coarticulate : true,
        blendDuration: options.coarticulationDurationSec || options.blendDuration || 0.14,
        returnToNeutralOnEnd: options.returnToNeutralOnEnd !== undefined ? options.returnToNeutralOnEnd : false,
        speed: targetSpeed
      });
      return true;
    } else {
      // Seña sin animación registrada: mantener reposo sin interrumpir
      if (this.clips && this.clips.NEUTRAL) {
        this.player?.play(this.clips.NEUTRAL, { coarticulate: true, returnToNeutralOnEnd: false });
      }
      return false;
    }
  }

  /**
   * Avanza el estado del avatar de forma determinista un paso de tiempo dt (segundos)
   * y fuerza un renderizado síncrono del viewport 3D.
   * @param {number} dt
   */
  stepDeterministic(dt = 1 / 30) {
    if (this.sequencer) {
      this.sequencer.update(dt);
    } else if (this.player) {
      this.player.update(dt);
    }
    if (this.engine && typeof this.engine.stepDeterministic === 'function') {
      this.engine.stepDeterministic(dt);
    }
  }

  /**
   * Detiene la reproducción y regresa al avatar a postura neutra de reposo.
   */
  stop() {
    this.reset();
  }

  /**
   * Reanuda la reproducción del clip o secuencia actual si estaba en pausa.
   */
  resume() {
    if (this.sequencer && this.sequencer.sequence && this.sequencer.sequence.length > 0) {
      this.sequencer.resume();
    } else if (this.player && typeof this.player.resume === 'function') {
      this.player.resume();
    }
  }

  /**
   * Salto temporal a un offset en segundos.
   * @param {number} timeSec
   */
  seek(timeSec) {
    if (this.player && typeof this.player.seek === 'function') {
      this.player.seek(timeSec);
    }
  }

  /**
   * Establece dinámicamente el color de fondo contrastante.
   * @param {string|number} color
   */
  setClearColor(color) {
    if (this.engine) {
      this.engine.setClearColor(color);
    }
  }

  /**
   * Captura frame actual para exportador de video.
   * @returns {HTMLCanvasElement|null}
   */
  captureFrame() {
    return this.engine ? this.engine.captureFrame() : null;
  }

  rotateCamera(deltaAzimuthDeg, deltaPolarDeg = 0) {
    if (this.engine) this.engine.rotateCamera(deltaAzimuthDeg, deltaPolarDeg);
  }

  panCamera(deltaX, deltaY) {
    if (this.engine) this.engine.panCamera(deltaX, deltaY);
  }

  dollyCamera(deltaZoom) {
    if (this.engine) this.engine.dollyCamera(deltaZoom);
  }

  resetCamera() {
    if (this.engine) {
      this.engine.resetCamera();
      this.syncPresetButtons('medium');
    }
  }

  testExpression(markerType) {
    if (!this.nonManual) return;
    this.nonManual.applyMarker(markerType, 1.0);
    setTimeout(() => {
      this.nonManual.applyMarker(markerType, 0.0);
    }, 1500);
  }

  toggleModelSource() {
    if (this.isVRMActive) {
      this.activateTechnicalRig();
    } else {
      this.loadInitialAvatar();
    }
  }

  /**
   * Exporta el clip actualmente seleccionado como archivo JSON descargable.
   */
  async exportCurrentClip() {
    let clip = this.clips[this.selectedClipId];
    if (typeof clip === 'function') {
      try {
        clip = await clip();
        this.clips[this.selectedClipId] = clip;
      } catch (err) {
        console.error('Error al resolver clip para exportar:', err);
        alert('No se pudo resolver el clip seleccionado para exportar.');
        return;
      }
    }

    if (!clip) {
      alert('No hay ninguna seña o clip seleccionado para exportar.');
      return;
    }

    try {
      const fileName = `${clip.gloss || clip.clipId || 'sign_clip'}.json`;
      const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(clip, null, 2));
      const downloadAnchor = document.createElement('a');
      downloadAnchor.setAttribute('href', dataStr);
      downloadAnchor.setAttribute('download', fileName);
      document.body.appendChild(downloadAnchor);
      downloadAnchor.click();
      downloadAnchor.remove();
      console.info(`[AvatarPanelController] Clip "${clip.gloss || clip.clipId}" exportado exitosamente como ${fileName}`);
    } catch (exportErr) {
      console.error('[AvatarPanelController] Error al descargar JSON del clip:', exportErr);
      alert('Error al generar la descarga del clip: ' + exportErr.message);
    }
  }

  /**
   * Adapta automáticamente un archivo animation.json proveniente del pipeline HaMeR / Colab
   * al esquema estandarizado SignClip de LSEC Studio.
   * Soporta tanto cuaterniones [w, x, y, z] (PyTorch / SMPL-X / HaMeR / Scipy)
   * como [x, y, z, w] (Three.js / Blender / VRM), normaliza nombres de huesos a nomenclatura
   * VRM humanoide y ajusta la duración con base en el tiempo máximo real de las pistas.
   * @param {Object} data - Objeto JSON con frames y metadata de HaMeR
   * @param {string} defaultName - Nombre base derivado del archivo
   * @returns {Object} Clip compatible con validateSignClip y SignPlayer
   */
  convertHamerAnimationToSignClip(data, defaultName = 'SEÑA_LSEC') {
    return convertDirectAnimationToSignClip(data, defaultName);
  }

  /**
   * Importa y valida un archivo JSON de seña corregida o personalizada.
   * Admite tanto el formato SignClip de LSEC Studio como el formato animation.json de HaMeR / Colab.
   * @param {File|Object|string} file 
   */
  async importCustomClip(file) {
    if (!file) return null;

    try {
      let customClip;
      const fileName = (file && typeof file === 'object' && file.name) ? file.name : 'custom_clip.json';

      if (typeof file === 'string') {
        try {
          customClip = JSON.parse(file);
        } catch (jsonErr) {
          throw new Error('El archivo no contiene un formato JSON válido.');
        }
      } else if (file && typeof file.text === 'function') {
        const text = await file.text();
        try {
          customClip = JSON.parse(text);
        } catch (jsonErr) {
          throw new Error('El archivo no contiene un formato JSON válido.');
        }
      } else if (file && typeof file === 'object') {
        customClip = JSON.parse(JSON.stringify(file));
      } else {
        throw new Error('El archivo o dato proporcionado no es válido.');
      }

      // Si el archivo proviene del pipeline HaMeR / Colab (frames o extractedTracks)
      if (customClip && !customClip.boneTracks && (Array.isArray(customClip.frames) || customClip.extractedTracks)) {
        console.info('[AvatarPanelController] Detectado formato animation.json de HaMeR Pipeline. Adaptando a SignClip...');
        customClip = this.convertHamerAnimationToSignClip(customClip, fileName.replace(/\.[^/.]+$/, ''));
      }

      // Garantizar campos mínimos obligatorios para clips personalizados antes de validar
      if (customClip && typeof customClip === 'object') {
        if (!customClip.clipId && customClip.gloss) {
          customClip.clipId = customClip.gloss.toLowerCase().replace(/[^a-z0-9_-]/gi, '_');
        } else if (!customClip.clipId) {
          customClip.clipId = `CUSTOM_${Date.now()}`;
        }
        if (!customClip.gloss && customClip.clipId) {
          customClip.gloss = customClip.clipId.toUpperCase();
        } else if (!customClip.gloss) {
          customClip.gloss = 'PERSONALIZADA';
        }
        if (typeof customClip.durationMs !== 'number' || customClip.durationMs <= 0) {
          if (Array.isArray(customClip.boneTracks) && customClip.boneTracks.length > 0) {
            let maxT = 0;
            customClip.boneTracks.forEach(tr => {
              if (Array.isArray(tr.times) && tr.times.length > 0) {
                const tLast = tr.times[tr.times.length - 1];
                if (typeof tLast === 'number' && tLast > maxT) maxT = tLast;
              }
            });
            if (maxT > 0) {
              customClip.durationMs = Math.round((maxT + 0.15) * 1000);
            }
          }
        }
      }

      // Validar esquema
      const validation = validateSignClip(customClip);
      if (!validation.valid) {
        const errorList = validation.errors.join('\n- ');
        throw new Error(`Estructura de seña incompatible:\n- ${errorList}`);
      }

      const clipId = customClip.clipId || `CUSTOM_${Date.now()}`;
      const gloss = customClip.gloss || 'PERSONALIZADA';
      const nfcGloss = String(gloss).normalize('NFC').trim();
      customClip.metadata = {
        ...(customClip.metadata || {}),
        isCustomImport: true
      };

      // Registrar en el catálogo de clips bajo clipId y glosa NFC para compatibilidad con Studio y Calibrador
      this.clips[clipId] = customClip;
      this.clips[gloss] = customClip;
      this.clips[nfcGloss] = customClip;
      this.clips[nfcGloss.toUpperCase()] = customClip;
      defaultAnimationCache.setClip(clipId, customClip);
      defaultAnimationCache.setClip(nfcGloss, customClip);
      defaultAnimationCache.setClip(nfcGloss.toUpperCase(), customClip);

      // Buscar o crear la categoría de Señas Personalizadas / Corregidas
      let customCategory = this.categories.find(c => c.groupName.includes('Señas Corregidas / Importadas'));
      if (!customCategory) {
        customCategory = {
          groupName: '✨ Señas Corregidas / Importadas',
          clips: []
        };
        this.categories.unshift(customCategory);
      }

      // Si ya existía el clip con ese ID en la categoría, actualizarlo; sino añadirlo
      const existingClipIdx = customCategory.clips.findIndex(c => c.id === clipId);
      const clipEntry = {
        id: clipId,
        label: `✨ ${nfcGloss} (Corregida / Importada)`
      };

      if (existingClipIdx >= 0) {
        customCategory.clips[existingClipIdx] = clipEntry;
      } else {
        customCategory.clips.unshift(clipEntry);
      }

      // Actualizar selector y sincronizar con la opción existente (por clipId o por glosa NFC)
      this.renderClipOptions();
      let resolvedSelectVal = clipId;
      if (this.selectClip && this.selectClip.options) {
        const opts = Array.from(this.selectClip.options);
        const matchOpt = opts.find(opt => {
          const v = String(opt.value || '');
          const vNfc = v.normalize('NFC').trim();
          return v === clipId || v === gloss || vNfc === nfcGloss;
        });
        if (matchOpt) {
          resolvedSelectVal = matchOpt.value;
        }
        this.selectClip.value = resolvedSelectVal;
      }
      this.selectedClipId = resolvedSelectVal;
      this.clips[resolvedSelectVal] = customClip;

      // Cargar en el reproductor y reproducir de inmediato para verificación visual
      await this.prepareSelectedClip();
      if (this.player) {
        this.player.play(customClip);
      }

      console.info(`[AvatarPanelController] Seña personalizada "${nfcGloss}" importada y cargada con éxito.`);
      return customClip;
    } catch (err) {
      console.error('[AvatarPanelController] Error al importar seña:', err);
      if (typeof alert === 'function') {
        alert('Error al importar la seña: ' + err.message);
      }
      return null;
    }
  }

  dispose() {
    if (this.engine) this.engine.dispose();
    if (this.technicalRig) this.technicalRig.dispose();
    if (this.vrmLoader) this.vrmLoader.unloadCurrentVRM();
  }
}

