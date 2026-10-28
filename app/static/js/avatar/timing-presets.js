/**
 * timing-presets.js
 * Prioridad de exportación: Claridad (señas legibles, más desfase) o Sincronía (más ajustado al video).
 * Valores medidos con 1.mp4 real (barrido de parámetros del planificador):
 *   clarity: 1.30x / ventana nuclear 0.92 s -> avatar termina ~85 s (video 48.8 s), seña mediana 0.71 s
 *   sync:    1.50x / ventana nuclear 0.80 s -> avatar termina ~71 s,                seña mediana 0.53 s
 */
export const TIMING_PRESETS = Object.freeze({
  clarity: Object.freeze({ label: 'Claridad', maxSpeed: 1.30, coreStrokeMaxSec: 0.92 }),
  sync: Object.freeze({ label: 'Sincronía', maxSpeed: 1.50, coreStrokeMaxSec: 0.80 })
});

export function resolveTimingOptions(mode) {
  const p = TIMING_PRESETS[mode] || TIMING_PRESETS.clarity;
  return { maxSpeed: p.maxSpeed, coreStrokeMaxSec: p.coreStrokeMaxSec };
}

/** Cambia la prioridad, recompila el plan del avatar y devuelve la duración estimada resultante. */
export function applyTimingPriority(mode, bridge = (typeof window !== 'undefined' ? window.studioAvatarBridge : null)) {
  if (!bridge) return null;
  bridge.timingPriority = TIMING_PRESETS[mode] ? mode : 'clarity';
  const project = typeof window !== 'undefined' ? window.appState?.state?.project : null;
  const plan = project ? bridge.rebuildSequencePlan(project) : null;
  if (!plan) return { mode: bridge.timingPriority };
  return {
    mode: bridge.timingPriority,
    sequenceEndSec: plan.sequenceEndTime,
    videoDurationSec: plan.videoDurationSec,
    tailSec: plan.extendedTailSec
  };
}

if (typeof window !== 'undefined') {
  window.setLSECTimingPriority = (mode) => applyTimingPriority(mode);
  window.LSEC_TIMING_PRESETS = TIMING_PRESETS;
}