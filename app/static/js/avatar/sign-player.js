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
import { validateSignClip, HUMAN_BONE_NAMES } from './sign-animation-schema.js';

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
    this.processedExpressions = [];

    // Objetos temporales reciclables para evitar alloc en el render loop
    this.tempQuat0 = new THREE.Quaternion();
    this.tempQuat1 = new THREE.Quaternion();
    this.tempQuatResult = new THREE.Quaternion();
  }

  /**
   * Asigna el modelo objetivo (VRM o TechnicalRig).
   * @param {Object} model 
   * @param {boolean} isVRM 
   */
  setModel(model, isVRM = false) {
    this.stop();
    this.model = model;
    this.isVRM = isVRM;
    this.restoreNeutralPose();
  }

  /**
   * Carga un clip para reproducción validando su estructura.
   * @param {Object} clip 
   * @returns {boolean}
   */
  loadClip(clip) {
    const { valid, errors } = validateSignClip(clip);
    if (!valid) {
      console.warn(`[SignPlayer] No se pudo cargar el clip "${clip ? clip.clipId : 'nulo'}":`, errors);
      return false;
    }

    this.currentClip = clip;
    this.currentTime = 0.0;
    this.processClipData(clip);
    return true;
  }

  processClipData(clip) {
    this.processedTracks = [];
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

        this.processedTracks.push({
          boneName: bt.boneName,
          keyframes
        });
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
   */
  play(clip = null) {
    if (clip) {
      const loaded = this.loadClip(clip);
      if (!loaded) return;
    }

    if (!this.currentClip) {
      console.warn('[SignPlayer] Ningún clip asignado para reproducir.');
      return;
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

  stop() {
    this.setState('stopped');
    this.currentTime = 0.0;
    this.restoreNeutralPose();
    this.emitProgress();
  }

  reset() {
    this.stop();
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
   * Actualiza el frame de animación según el tiempo transcurrido (delta en segundos).
   * @param {number} delta 
   */
  update(delta) {
    if (this.playbackState !== 'playing' || !this.currentClip || !this.model) {
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
        this.restoreNeutralPose();

        if (typeof this.onEnded === 'function') {
          this.onEnded(this.currentClip);
        }
      }
    }
  }

  applyBonesAtTime(time) {
    if (!this.model) return;

    for (let i = 0; i < this.processedTracks.length; i++) {
      const track = this.processedTracks[i];
      const node = this.getBoneNode(track.boneName);
      if (!node) continue;

      const kf = track.keyframes;
      if (kf.length === 0) continue;

      if (time <= kf[0].time) {
        node.quaternion.copy(kf[0].quat);
        continue;
      }

      if (time >= kf[kf.length - 1].time) {
        node.quaternion.copy(kf[kf.length - 1].quat);
        continue;
      }

      // Buscar segmento temporal [kf[j-1], kf[j]]
      let j = 1;
      while (j < kf.length && kf[j].time < time) {
        j++;
      }

      const prev = kf[j - 1];
      const next = kf[j];
      const span = next.time - prev.time;
      const alpha = span > 0.0001 ? (time - prev.time) / span : 0.0;

      // Slerp suave de cuaterniones
      this.tempQuat0.copy(prev.quat);
      this.tempQuat1.copy(next.quat);
      this.tempQuatResult.copy(this.tempQuat0).slerp(this.tempQuat1, Math.max(0, Math.min(1, alpha)));

      node.quaternion.copy(this.tempQuatResult);
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
        let j = 1;
        while (j < kf.length && kf[j].time < time) {
          j++;
        }
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
          node.quaternion.identity();
        }
      }

      // Postura natural de reposo biomecánico para brazos (caídos junto al torso)
      const lArm = this.model.humanoid.getNormalizedBoneNode('leftUpperArm');
      if (lArm) {
        lArm.quaternion.set(0.0435, 0.0028, -0.6087, 0.7921);
      }
      const rArm = this.model.humanoid.getNormalizedBoneNode('rightUpperArm');
      if (rArm) {
        rArm.quaternion.set(0.0435, -0.0028, 0.6087, 0.7921);
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
