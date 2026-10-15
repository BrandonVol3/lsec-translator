/**
 * LSEC Studio — Reproductor de Animación de Señas (SignPlayer)
 * 
 * Controla la reproducción precisa de clips individuales sobre el avatar:
 * - Interpolación esférica de cuaterniones (SLERP) entre keyframes;
 * - Interpolación lineal de pesos de expresiones faciales;
 * - Control de reproducción: play, pause, resume, stop, reset, velocidad;
 * - Emisión reactiva de progreso temporal;
 * - Restauración suave a la postura neutral.
 */

import * as THREE from 'three';
import { validateSignClip, HUMAN_BONE_NAMES, REST_POSE } from './sign-animation-schema.js';

export class SignPlayer {
  constructor() {
    this.model = null;
    this.isVRM = false;

    this.currentClip = null;
    this.playbackState = 'idle'; // 'idle' | 'playing' | 'paused' | 'stopped'
    this.currentTime = 0.0;
    this.speed = 1.0;
    this.isLooping = false;

    // Callbacks
    this.onProgress = null;
    this.onEnded = null;
    this.onStateChange = null;

    // Cache interno de estructuras de keyframes para evaluación ultra rápida
    this.processedTracks = [];
    this.processedTrackMap = new Map();
    this.processedExpressions = [];

    // Objetos temporales reciclables para evitar alloc en el render loop
    this.tempQuat0 = new THREE.Quaternion();
    this.tempQuat1 = new THREE.Quaternion();
    this.tempQuatResult = new THREE.Quaternion();

    // Estado para interpolación suave (ease-out) a postura neutral
    this.isTransitioning = false;
    this.transitionTime = 0.0;
    this.transitionDuration = 0.25;
    this.transitionBoneSnapshots = new Map();
    this.transitionExpressionSnapshots = new Map();
    this.transitionOnComplete = null;

    // Estado para coarticulación SLERP directa entre señas consecutivas (sin pasar por neutral)
    this.coartActive = false;
    this.coartDuration = 0.12;
    this.coartBoneSnapshots = new Map();
    this.returnToNeutralOnEnd = true;
  }

  /**
   * Asigna el modelo objetivo (VRM o TechnicalRig).
   * @param {Object} model 
   * @param {boolean} isVRM 
   */
  setModel(model, isVRM = false) {
    this.stop(false);
    this.model = model;
    this.isVRM = isVRM;
    this.restoreNeutralPose();
  }

  /**
   * Captura la postura actual de todos los huesos del avatar para coarticulación SLERP.
   */
  captureCurrentPoseSnapshot() {
    this.coartBoneSnapshots.clear();
    if (!this.model) return;
    for (const bName of HUMAN_BONE_NAMES) {
      const node = this.getBoneNode(bName);
      if (node) {
        this.coartBoneSnapshots.set(bName, node.quaternion.clone());
      }
    }
  }

  /**
   * Carga un clip para reproducción validando su estructura.
   * @param {Object} clip 
   * @param {Object} [options] - { coarticulate: boolean, blendDuration: number, returnToNeutralOnEnd: boolean }
   * @returns {boolean}
   */
  loadClip(clip, options = {}) {
    const { valid, errors } = validateSignClip(clip);
    if (!valid) {
      console.warn(`[SignPlayer] No se pudo cargar el clip "${clip ? clip.clipId : 'nulo'}":`, errors);
      return false;
    }

    const shouldCoarticulate = options.coarticulate !== undefined
      ? Boolean(options.coarticulate)
      : Boolean(this.currentClip && (this.playbackState === 'playing' || this.isTransitioning));

    if (shouldCoarticulate && this.model) {
      this.captureCurrentPoseSnapshot();
      this.coartActive = true;
      this.coartDuration = typeof options.blendDuration === 'number' ? Math.max(0.02, options.blendDuration) : 0.12;
    } else {
      this.coartActive = false;
      this.coartBoneSnapshots.clear();
    }

    if (options.returnToNeutralOnEnd !== undefined) {
      this.returnToNeutralOnEnd = Boolean(options.returnToNeutralOnEnd);
    } else {
      this.returnToNeutralOnEnd = true;
    }

    this.isTransitioning = false;
    this.currentClip = clip;
    this.currentTime = 0.0;
    this.processClipData(clip);

    // Si no estamos coarticulando, limpiar huesos ausentes a su pose de reposo natural
    if (!this.coartActive && this.model) {
      this.resetUntrackedBonesToNeutral();
    }

    return true;
  }

  resetUntrackedBonesToNeutral() {
    if (!this.model) return;
    for (const bName of HUMAN_BONE_NAMES) {
      if (!this.processedTrackMap.has(bName)) {
        const node = this.getBoneNode(bName);
        if (node) {
          node.quaternion.copy(this.getNeutralPoseForBone(bName));
        }
      }
    }
  }

  processClipData(clip) {
    this.processedTracks = [];
    this.processedTrackMap.clear();
    this.processedExpressions = [];

    // Pre-procesar pistas esqueléticas
    if (Array.isArray(clip.boneTracks)) {
      clip.boneTracks.forEach((bt) => {
        const keyframes = [];
        for (let i = 0; i < bt.times.length; i++) {
          const t = bt.times[i];
          const k4 = i * 4;
          const q = new THREE.Quaternion(
            bt.rotations[k4],
            bt.rotations[k4 + 1],
            bt.rotations[k4 + 2],
            bt.rotations[k4 + 3]
          ).normalize();

          keyframes.push({ time: t, quat: q });
        }

        const trackObj = {
          boneName: bt.boneName,
          keyframes
        };
        this.processedTracks.push(trackObj);
        this.processedTrackMap.set(bt.boneName, trackObj);
      });
    }

    // Pre-procesar pistas de expresiones faciales
    if (Array.isArray(clip.expressionTracks)) {
      clip.expressionTracks.forEach((et) => {
        const keyframes = [];
        for (let i = 0; i < et.times.length; i++) {
          keyframes.push({
            time: et.times[i],
            value: et.values[i]
          });
        }

        this.processedExpressions.push({
          expressionName: et.expressionName,
          keyframes
        });
      });
    }
  }

  /**
   * Inicia la reproducción del clip especificado (o del actual).
   * @param {Object} [clip]
   * @param {Object} [options]
   */
  play(clip = null, options = {}) {
    if (clip) {
      const loaded = this.loadClip(clip, options);
      if (!loaded) return;
    }

    if (!this.currentClip) {
      console.warn('[SignPlayer] Ningún clip asignado para reproducir.');
      return;
    }

    if (typeof options.speed === 'number' && options.speed > 0) {
      this.setSpeed(options.speed);
    }

    this.setState('playing');
  }

  pause() {
    if (this.playbackState === 'playing') {
      this.setState('paused');
    }
  }

  resume() {
    if (this.playbackState === 'paused') {
      this.setState('playing');
    }
  }

  stop(smooth = true) {
    this.setState('stopped');
    this.currentTime = 0.0;
    this.coartActive = false;
    if (smooth) {
      this.easeOutToNeutral(0.25);
    } else {
      this.isTransitioning = false;
      this.restoreNeutralPose();
    }
    this.emitProgress();
  }

  reset() {
    this.stop(false);
  }

  /**
   * Salto temporal a un offset en segundos dentro del clip activo.
   * @param {number} timeSec
   */
  seek(timeSec) {
    if (!this.model || !this.currentClip) return;
    const duration = this.getDuration();
    this.currentTime = Math.max(0, Math.min(duration, Number(timeSec) || 0));
    this.isTransitioning = false;
    this.applyBonesAtTime(this.currentTime);
    this.applyExpressionsAtTime(this.currentTime);
    this.emitProgress();
  }

  setSpeed(rate) {
    this.speed = Math.max(0.1, Math.min(3.0, Number(rate) || 1.0));
  }

  getCurrentTime() {
    return this.currentTime;
  }

  getDuration() {
    return this.currentClip ? (this.currentClip.durationMs / 1000.0) : 0.0;
  }

  getPlaybackState() {
    return this.playbackState;
  }

  setState(newState) {
    if (this.playbackState !== newState) {
      this.playbackState = newState;
      if (typeof this.onStateChange === 'function') {
        this.onStateChange(newState);
      }
    }
  }

  /**
   * Búsqueda binaria O(log N) del índice del keyframe derecho j tal que kf[j-1].time <= time <= kf[j].time.
   * @param {Array<{time: number}>} kf 
   * @param {number} time 
   * @returns {number}
   */
  findKeyframeIndex(kf, time) {
    let low = 1;
    let high = kf.length - 1;
    let result = kf.length - 1;

    while (low <= high) {
      const mid = (low + high) >> 1;
      if (kf[mid].time >= time) {
        result = mid;
        high = mid - 1;
      } else {
        low = mid + 1;
      }
    }
    return result;
  }

  /**
   * Transición suave con curva cúbica ease-out desde la postura actual a la postura neutral.
   * @param {number} [durationSec=0.25]
   * @param {Function} [onComplete]
   */
  easeOutToNeutral(durationSec = 0.25, onComplete = null) {
    if (!this.model) {
      this.isTransitioning = false;
      if (typeof onComplete === 'function') onComplete();
      return;
    }

    this.transitionBoneSnapshots.clear();
    for (const bName of HUMAN_BONE_NAMES) {
      const node = this.getBoneNode(bName);
      if (node) {
        this.transitionBoneSnapshots.set(bName, node.quaternion.clone());
      }
    }

    this.transitionTime = 0.0;
    this.transitionDuration = Math.max(0.01, durationSec);
    this.transitionOnComplete = onComplete;
    this.isTransitioning = true;
  }

  updateTransition(delta) {
    if (!this.isTransitioning || !this.model) return;

    this.transitionTime += delta;
    const rawProgress = this.transitionDuration > 0 ? this.transitionTime / this.transitionDuration : 1.0;
    const progress = Math.min(1.0, Math.max(0.0, rawProgress));
    // Curva cúbica ease-out: 1 - (1 - progress)^3
    const t = 1.0 - Math.pow(1.0 - progress, 3);

    for (const [boneName, startQuat] of this.transitionBoneSnapshots.entries()) {
      const node = this.getBoneNode(boneName);
      if (node) {
        const targetQuat = this.getNeutralPoseForBone(boneName);
        this.tempQuat0.copy(startQuat);
        this.tempQuat1.copy(targetQuat);
        this.tempQuatResult.copy(this.tempQuat0).slerp(this.tempQuat1, t);
        node.quaternion.copy(this.tempQuatResult);
      }
    }

    // Suavizar expresiones faciales
    if (this.isVRM && this.model.expressionManager && typeof this.model.expressionManager.resetValues === 'function') {
      if (progress >= 1.0) {
        this.model.expressionManager.resetValues();
      }
    }

    if (progress >= 1.0) {
      this.isTransitioning = false;
      this.restoreNeutralPose();
      if (typeof this.transitionOnComplete === 'function') {
        const cb = this.transitionOnComplete;
        this.transitionOnComplete = null;
        cb();
      }
    }
  }

  getNeutralPoseForBone(boneName) {
    if (REST_POSE && REST_POSE[boneName]) {
      const q = REST_POSE[boneName];
      return new THREE.Quaternion(q[0], q[1], q[2], q[3]);
    }
    return new THREE.Quaternion(0, 0, 0, 1);
  }

  /**
   * Actualiza el frame de animación según el tiempo transcurrido (delta en segundos).
   * @param {number} delta 
   */
  update(delta) {
    if (!this.model) return;

    if (this.isTransitioning) {
      this.updateTransition(delta);
      return;
    }

    if (this.playbackState !== 'playing' || !this.currentClip) {
      return;
    }

    const durationSec = this.getDuration();
    if (durationSec <= 0) return;

    this.currentTime += delta * this.speed;

    // Evaluación de pistas esqueléticas y aplicación al avatar
    this.applyBonesAtTime(this.currentTime);

    // Evaluación de expresiones faciales
    this.applyExpressionsAtTime(this.currentTime);

    this.emitProgress();

    // Comprobación de final de clip
    if (this.currentTime >= durationSec) {
      if (this.isLooping) {
        this.currentTime = 0.0;
      } else {
        this.currentTime = durationSec;
        this.setState('stopped');
        if (this.returnToNeutralOnEnd === false) {
          if (typeof this.onEnded === 'function') {
            this.onEnded(this.currentClip);
          }
        } else {
          this.easeOutToNeutral(0.25, () => {
            if (typeof this.onEnded === 'function') {
              this.onEnded(this.currentClip);
            }
          });
        }
      }
    }
  }

  applyBonesAtTime(time) {
    if (!this.model) return;

    const isCoartBlending = this.coartActive && this.coartDuration > 0 && time < this.coartDuration;
    const rawCoart = isCoartBlending ? Math.max(0, Math.min(1, time / this.coartDuration)) : 1.0;
    const coartT = rawCoart * rawCoart * (3.0 - 2.0 * rawCoart);

    if (this.coartActive && !isCoartBlending) {
      this.coartActive = false;
      this.resetUntrackedBonesToNeutral();
    }

    for (let i = 0; i < this.processedTracks.length; i++) {
      const track = this.processedTracks[i];
      const node = this.getBoneNode(track.boneName);
      if (!node) continue;

      const kf = track.keyframes;
      if (kf.length === 0) continue;

      if (time <= kf[0].time) {
        this.tempQuatResult.copy(kf[0].quat);
      } else if (time >= kf[kf.length - 1].time) {
        this.tempQuatResult.copy(kf[kf.length - 1].quat);
      } else {
        // Búsqueda binaria O(log N) del segmento temporal [kf[j-1], kf[j]]
        const j = this.findKeyframeIndex(kf, time);
        const prev = kf[j - 1];
        const next = kf[j];
        const span = next.time - prev.time;
        const alpha = span > 0.0001 ? (time - prev.time) / span : 0.0;

        // Slerp suave de cuaterniones
        this.tempQuat0.copy(prev.quat);
        this.tempQuat1.copy(next.quat);
        this.tempQuatResult.copy(this.tempQuat0).slerp(this.tempQuat1, Math.max(0, Math.min(1, alpha)));
      }

      if (isCoartBlending && this.coartBoneSnapshots.has(track.boneName)) {
        const snapQuat = this.coartBoneSnapshots.get(track.boneName);
        this.tempQuat0.copy(snapQuat).slerp(this.tempQuatResult, coartT);
        node.quaternion.copy(this.tempQuat0);
      } else {
        node.quaternion.copy(this.tempQuatResult);
      }
    }

    if (isCoartBlending) {
      for (const [bName, snapQuat] of this.coartBoneSnapshots.entries()) {
        if (!this.processedTrackMap.has(bName)) {
          const node = this.getBoneNode(bName);
          if (node) {
            const neutralQuat = this.getNeutralPoseForBone(bName);
            this.tempQuat0.copy(snapQuat).slerp(neutralQuat, coartT);
            node.quaternion.copy(this.tempQuat0);
          }
        }
      }
    }
  }

  applyExpressionsAtTime(time) {
    if (!this.model) return;

    for (let i = 0; i < this.processedExpressions.length; i++) {
      const track = this.processedExpressions[i];
      const kf = track.keyframes;
      if (kf.length === 0) continue;

      let value = 0;
      if (time <= kf[0].time) {
        value = kf[0].value;
      } else if (time >= kf[kf.length - 1].time) {
        value = kf[kf.length - 1].value;
      } else {
        // Búsqueda binaria O(log N) del segmento temporal [kf[j-1], kf[j]]
        const j = this.findKeyframeIndex(kf, time);
        const prev = kf[j - 1];
        const next = kf[j];
        const span = next.time - prev.time;
        const alpha = span > 0.0001 ? (time - prev.time) / span : 0.0;
        value = prev.value + alpha * (next.value - prev.value);
      }

      this.setExpressionValue(track.expressionName, value);
    }
  }

  getBoneNode(boneName) {
    if (!this.model) return null;
    if (this.isVRM && this.model.humanoid) {
      return this.model.humanoid.getNormalizedBoneNode(boneName);
    } else if (typeof this.model.getNormalizedBoneNode === 'function') {
      return this.model.getNormalizedBoneNode(boneName);
    }
    return null;
  }

  setExpressionValue(expressionName, value) {
    if (!this.model) return;
    const clamped = Math.max(0, Math.min(1, value));

    if (this.isVRM && this.model.expressionManager) {
      try {
        this.model.expressionManager.setValue(expressionName, clamped);
      } catch (e) {}
    } else if (typeof this.model.setExpressionWeight === 'function') {
      this.model.setExpressionWeight(expressionName, clamped);
    }
  }

  restoreNeutralPose() {
    if (!this.model) return;

    if (typeof this.model.resetPose === 'function') {
      this.model.resetPose();
    } else if (this.isVRM && this.model.humanoid) {
      // Restablecer todos los huesos normalizados para evitar residuos en dedos u ojos
      for (const bName of HUMAN_BONE_NAMES) {
        const node = this.model.humanoid.getNormalizedBoneNode(bName);
        if (node) {
          node.quaternion.copy(this.getNeutralPoseForBone(bName));
        }
      }

      if (this.model.expressionManager) {
        if (typeof this.model.expressionManager.resetValues === 'function') {
          this.model.expressionManager.resetValues();
        }
      }
    }
  }

  emitProgress() {
    if (typeof this.onProgress === 'function') {
      const duration = this.getDuration();
      const progress = duration > 0 ? Math.min(1.0, this.currentTime / duration) : 0;
      this.onProgress({
        currentTime: this.currentTime,
        duration,
        progress
      });
    }
  }
}
