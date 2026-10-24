/**
 * LSEC Studio — Gestión de Manifiesto, Sombreado MToon VRM y Secuencias del Controlador 3D
 *
 * Submódulo extraído de avatar-controller.js para cumplir SRP (< 800 líneas).
 */

import { HUMAN_BONE_NAMES, trimSignClipStroke } from './sign-animation-schema.js';
import { defaultAnimationCache } from './animation-cache.js';
import { createNeutralClip } from './sign-clip-factory.js';

export const BONE_LOWER_MAP = new Map((HUMAN_BONE_NAMES || []).map(b => [b.toLowerCase(), b]));

export const BONE_ALIASES = {
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

export function normalizeBoneName(name) {
  if (typeof name !== 'string') return name;
  const clean = name.replace(/^mixamorig:?/i, '').trim();
  const lower = clean.toLowerCase();
  if (BONE_ALIASES[lower]) return BONE_ALIASES[lower];
  if (BONE_LOWER_MAP.has(lower)) return BONE_LOWER_MAP.get(lower);
  return clean;
}

export function detectDatasetQuaternionLayout(data) {
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

export async function loadAvatarManifestClips(ctrl) {
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
          const activeVer = ctrl.preferredVersion || '2.7';
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
                    let clip = ctrl.convertHamerAnimationToSignClip(directData, clipMeta.clipId || normKey);
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

          const clipRes = await fetch(`/static/assets/clips/${clipMeta.file}?t=${Date.now()}`);
          let clipData = await clipRes.json();
          if (clipData && !clipData.boneTracks && (Array.isArray(clipData.frames) || clipData.extractedTracks)) {
            clipData = ctrl.convertHamerAnimationToSignClip(clipData, clipMeta.clipId || normKey);
            clipData = trimSignClipStroke(clipData);
          }
          if (clipData && !clipData.clipId) {
            clipData.clipId = clipMeta.clipId || normKey;
          }
          defaultAnimationCache.setClip(clipData.clipId, clipData);
          return clipData;
        };

        ctrl.clips[glossKey] = loaderFn;
        ctrl.clips[normKey] = loaderFn;
        ctrl.clipLoaders[glossKey] = loaderFn;
        ctrl.clipLoaders[normKey] = loaderFn;

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

      const dynamicGroups = [
        { groupName: '📅 Días de la Semana (Glosario LSEC)', clips: weekClips },
        ...(numberClips.length > 0 ? [{ groupName: '🔢 Números y Cantidades (LSEC)', clips: numberClips }] : []),
        ...(vocabClips.length > 0 ? [{ groupName: '🤟 Vocabulario y Léxico LSEC', clips: vocabClips }] : [])
      ];

      const existingWeekIdx = ctrl.categories.findIndex(c => c.groupName.includes('Léxico LSEC') || c.groupName.includes('Días de la Semana'));
      if (existingWeekIdx >= 0) {
        ctrl.categories.splice(existingWeekIdx, 1, ...dynamicGroups);
      } else {
        ctrl.categories.unshift(...dynamicGroups);
      }

      ctrl.renderClipOptions();
      console.info(`[AvatarPanelController] ${weekClips.length} días, ${numberClips.length} numerales y ${vocabClips.length} señas léxicas cargadas desde manifest.json`);
    }
  } catch (err) {
    console.warn('[AvatarPanelController] No se pudo cargar manifest.json:', err);
  }
}

export function applyAvatarToonVisualShading(ctrl, vrm) {
  if (!vrm || !vrm.scene) return;
  if (ctrl.engine && ctrl.engine.renderer) {
    ctrl.engine.renderer.shadowMap.enabled = true;
    if (typeof THREE !== 'undefined' && THREE.PCFSoftShadowMap) {
      ctrl.engine.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    }
  }
  vrm.scene.traverse((obj) => {
    if (obj.isMesh) {
      obj.castShadow = true;
      obj.receiveShadow = true;
      if (obj.material) {
        const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
        for (const mat of mats) {
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

export async function playAvatarWeekSequence(ctrl) {
  ctrl.hideError();
  if (ctrl.player) ctrl.player.externalPoseControl = false;
  if (typeof window !== 'undefined' && window.studioAvatarBridge) {
    window.studioAvatarBridge.isManualPreviewActive = true;
  }
  const weekDays = ['LUNES', 'MARTES', 'MIERCOLES', 'JUEVES', 'VIERNES', 'SABADO', 'DOMINGO'];
  const sequence = [ctrl.clips.NEUTRAL || createNeutralClip()];

  for (const day of weekDays) {
    let clip = ctrl.clips[day];
    if (typeof clip === 'function') {
      try {
        clip = await clip();
        ctrl.clips[day] = clip;
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
  sequence.push(ctrl.clips.NEUTRAL || createNeutralClip());

  console.info(`[AvatarPanelController] Iniciando secuencia de ${sequence.length - 2} días de la semana...`);
  ctrl.sequencer.playSequence(sequence);
}

export function playAvatarAllTestsSequence(ctrl) {
  ctrl.hideError();
  if (ctrl.player) ctrl.player.externalPoseControl = false;
  if (typeof window !== 'undefined' && window.studioAvatarBridge) {
    window.studioAvatarBridge.isManualPreviewActive = true;
  }
  const sequence = [
    ctrl.clips.NEUTRAL,
    ctrl.clips.TEST_MANO_ABIERTA,
    ctrl.clips.TEST_PUNO,
    ctrl.clips.TEST_INDICE_EXTENDIDO,
    ctrl.clips.TEST_DOS_DEDOS,
    ctrl.clips.TEST_PINZA,
    ctrl.clips.TEST_MANO_CURVA,
    ctrl.clips.TEST_GARRA,
    ctrl.clips.TEST_DEDOS_JUNTOS_SEPARADOS,
    ctrl.clips.TEST_ORIENTACION_PALMA,
    ctrl.clips.TEST_PRONACION_SUPINACION,
    ctrl.clips.TEST_FLEXION_MUNICA_CODO,
    ctrl.clips.TEST_CNM_HEAD_SHAKE,
    ctrl.clips.TEST_CNM_HEAD_NOD,
    ctrl.clips.TEST_CNM_HEAD_TILT,
    ctrl.clips.TEST_CNM_MIRADA,
    ctrl.clips.TEST_CNM_CEJAS,
    ctrl.clips.TEST_CNM_PARPADEO,
    ctrl.clips.TEST_CNM_BOCA,
    ctrl.clips.TEST_SIMULTANEO_MANOS_CABEZA,
    ctrl.clips.TEST_SIMULTANEO_MANOS_MIRADA,
    ctrl.clips.TEST_SIMULTANEO_MANOS_EXPRESION,
    ctrl.clips.TEST_SIMULTANEO_COMPLEJO_TOTAL,
    ctrl.clips.NEUTRAL
  ].filter(Boolean);

  ctrl.sequencer.playSequence(sequence);
}

export async function exportAvatarCurrentClip(ctrl) {
  let clip = ctrl.clips[ctrl.selectedClipId];
  if (typeof clip === 'function') {
    try {
      clip = await clip();
      ctrl.clips[ctrl.selectedClipId] = clip;
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

export function updateAvatarFPSMetrics(ctrl) {
  ctrl.perfMetrics.frameCount++;
  const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
  const elapsed = now - ctrl.perfMetrics.lastFpsTime;

  if (elapsed >= 500) {
    ctrl.perfMetrics.fps = Math.round((ctrl.perfMetrics.frameCount * 1000) / elapsed);
    ctrl.perfMetrics.frameCount = 0;
    ctrl.perfMetrics.lastFpsTime = now;

    if (typeof performance !== 'undefined' && performance.memory) {
      ctrl.perfMetrics.usedMemoryMB = (performance.memory.usedJSHeapSize / (1024 * 1024)).toFixed(1);
    }

    ctrl.updatePerfDisplay();
  }
}

export function updateAvatarPerfDisplay(ctrl) {
  if (ctrl.hudPerfBadge) {
    const memText = ctrl.perfMetrics.usedMemoryMB > 0 ? ` | ${ctrl.perfMetrics.usedMemoryMB} MB` : '';
    ctrl.hudPerfBadge.textContent = `${ctrl.perfMetrics.fps} FPS${memText}`;
    if (ctrl.perfMetrics.fps >= 50) {
      ctrl.hudPerfBadge.style.color = 'var(--action-primary)';
    } else if (ctrl.perfMetrics.fps >= 30) {
      ctrl.hudPerfBadge.style.color = 'var(--status-review)';
    } else {
      ctrl.hudPerfBadge.style.color = 'var(--status-error)';
    }
  }
}

export function getAvatarPerformanceReport(ctrl) {
  return {
    loadTimeMs: ctrl.perfMetrics.loadTimeMs,
    fps: ctrl.perfMetrics.fps,
    usedMemoryMB: ctrl.perfMetrics.usedMemoryMB,
    isVRMActive: ctrl.isVRMActive,
    modelSource: ctrl.currentModelSource,
    consoleErrors: ctrl.perfMetrics.consoleErrors,
    consoleWarnings: ctrl.perfMetrics.consoleWarnings
  };
}

export async function loadInitialAvatarModel(ctrl) {
  ctrl.showLoading(true, 'Verificando avatar VRM...');

  const candidates = [
    '/avatar/LSEC-Interpreter-Female.vrm',
    '/static/assets/LSEC-Interpreter-Female.vrm'
  ];

  for (const vrmUrl of candidates) {
    try {
      const check = await fetch(vrmUrl, { method: 'HEAD' });
      if (check.ok) {
        console.info(`[AvatarPanelController] Avatar VRM detectado en: ${vrmUrl}`);
        await ctrl.loadVRMFromUrl(vrmUrl);
        return;
      }
    } catch (e) {}
  }

  console.info('[AvatarPanelController] Modelo VRM no detectado en las rutas estándar. Activando Rig Técnico de Reserva.');
  ctrl.activateTechnicalRig();
  ctrl.showLoading(false);
}

export function activateAvatarTechnicalRig(ctrl) {
  ctrl.isVRMActive = false;
  ctrl.currentModelSource = 'TECHNICAL_RIG';

  ctrl.engine.setModel(ctrl.technicalRig, false);
  ctrl.player.setModel(ctrl.technicalRig, false);
  ctrl.nonManual.setModel(ctrl.technicalRig, false);

  if (ctrl.modelSourcePill) {
    ctrl.modelSourcePill.textContent = 'Rig Técnico (Reserva)';
    ctrl.modelSourcePill.className = 'avatar-model-pill avatar-pill-rig';
  }

  ctrl.prepareSelectedClip();
}

export async function loadAvatarVRMFromFile(ctrl, file) {
  if (!file) return;
  ctrl.showLoading(true, `Cargando ${file.name}...`);
  ctrl.hideError();
  const t0 = performance.now();

  try {
    const vrm = await ctrl.vrmLoader.loadVRM(file);
    ctrl.perfMetrics.loadTimeMs = Math.round(performance.now() - t0);
    ctrl.onVRMLoadSuccess(vrm, file.name);
  } catch (err) {
    console.error('[AvatarPanelController] Fallo al cargar VRM desde archivo:', err);
    ctrl.showError(`Error al cargar avatar VRM (${file.name}). Se mantiene el Rig de reserva.`);
    ctrl.activateTechnicalRig();
  } finally {
    ctrl.showLoading(false);
  }
}

export async function loadAvatarVRMFromUrl(ctrl, url) {
  ctrl.showLoading(true, 'Descargando avatar VRM...');
  ctrl.hideError();
  const t0 = performance.now();

  try {
    const vrm = await ctrl.vrmLoader.loadVRM(url);
    ctrl.perfMetrics.loadTimeMs = Math.round(performance.now() - t0);
    const fileName = url.split('/').pop() || 'avatar.vrm';
    ctrl.onVRMLoadSuccess(vrm, fileName);
  } catch (err) {
    console.warn('[AvatarPanelController] No se pudo cargar avatar VRM desde URL. Activando rig de reserva.', err);
    ctrl.activateTechnicalRig();
  } finally {
    ctrl.showLoading(false);
  }
}

export function handleVRMLoadSuccess(ctrl, vrm, sourceName) {
  ctrl.isVRMActive = true;
  ctrl.currentModelSource = 'VRM_LOCAL';

  ctrl.applyToonVisualShading(vrm);

  ctrl.engine.setModel(vrm, true);
  ctrl.player.setModel(vrm, true);
  ctrl.nonManual.setModel(vrm, true);

  if (ctrl.modelSourcePill) {
    ctrl.modelSourcePill.textContent = `VRM 1.0 (${sourceName})`;
    ctrl.modelSourcePill.className = 'avatar-model-pill avatar-pill-vrm';
  }

  ctrl.prepareSelectedClip();
}
