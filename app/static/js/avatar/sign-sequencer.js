/**
 * LSEC Studio — Secuenciador de Animaciones de Glosas (SignSequencer)
 * 
 * Gestiona la reproducción ordenada de secuencias continuas de glosas:
 * - Emite la glosa activa en tiempo real para sincronización de UI;
 * - Inserta transiciones ergonómicas suaves (blending de salida/entrada);
 * - Respeta velocidad y marcas de tiempo;
 * - Permite pausar, reanudar o cancelar en cualquier instante;
 * - Restaura el avatar a la postura neutral al concluir.
 */

import * as THREE from 'three';
import { HUMAN_BONE_NAMES } from './sign-animation-schema.js';

export class SignSequencer {
  /**
   * @param {import('./sign-player.js').SignPlayer} player 
   */
  constructor(player) {
    if (!player) {
      throw new Error('[SignSequencer] Se requiere una instancia de SignPlayer.');
    }

    this.player = player;
    this.sequence = [];
    this.currentIndex = -1;
    this.speed = 1.0;
    this.transitionDuration = 0.20; // 200ms de transición entre señas

    this.isTransitioning = false;
    this.transitionTime = 0.0;
    this.transitionFromPose = new Map();
    this.transitionToPose = new Map();

    // Callbacks
    this.onGlossChanged = null;
    this.onSequenceProgress = null;
    this.onSequenceEnded = null;
    this.onStateChange = null;

    this.setupPlayerCallbacks();
  }

  setupPlayerCallbacks() {
    this.player.onProgress = ({ currentTime, duration, progress }) => {
      if (this.currentIndex >= 0 && this.currentIndex < this.sequence.length) {
        const activeClip = this.sequence[this.currentIndex];
        if (typeof this.onSequenceProgress === 'function') {
          const total = this.sequence.length;
          const seqProgress = total > 0 ? (this.currentIndex + progress) / total : 0;
          this.onSequenceProgress({
            currentIndex: this.currentIndex,
            total,
            clipProgress: progress,
            sequenceProgress: seqProgress,
            activeGloss: activeClip.gloss
          });
        }
      }
    };

    this.player.onEnded = (finishedClip) => {
      this.handleClipEnded(finishedClip);
    };
  }

  /**
   * Inicia la reproducción de una secuencia de clips.
   * @param {Array<Object>} clips 
   */
  playSequence(clips) {
    if (!Array.isArray(clips) || clips.length === 0) {
      console.warn('[SignSequencer] La secuencia de clips está vacía.');
      return;
    }

    this.sequence = [...clips];
    this.currentIndex = 0;
    this.isTransitioning = false;

    this.notifyGlossChanged(this.sequence[0]);
    this.player.setSpeed(this.speed);
    this.player.play(this.sequence[0]);

    if (typeof this.onStateChange === 'function') {
      this.onStateChange('playing');
    }
  }

  handleClipEnded(clip) {
    if (!this.sequence || this.sequence.length === 0) {
      return;
    }

    if (this.currentIndex < this.sequence.length - 1) {
      const nextIndex = this.currentIndex + 1;
      const nextClip = this.sequence[nextIndex];

      // Iniciar transición suave hacia la pose inicial del siguiente clip
      this.beginTransition(nextClip, nextIndex);
    } else {
      // Secuencia finalizada con éxito
      this.currentIndex = -1;
      this.sequence = [];
      this.player.restoreNeutralPose();

      console.info('[SignSequencer] Secuencia de glosas finalizada con retorno a neutral.');
      if (typeof this.onSequenceEnded === 'function') {
        this.onSequenceEnded();
      }
      if (typeof this.onStateChange === 'function') {
        this.onStateChange('idle');
      }
    }
  }

  beginTransition(nextClip, nextIndex) {
    this.isTransitioning = true;
    this.transitionTime = 0.0;

    // Capturar pose final del avatar actual
    this.transitionFromPose.clear();
    this.transitionToPose.clear();

    HUMAN_BONE_NAMES.forEach((boneName) => {
      const node = this.player.getBoneNode(boneName);
      if (node) {
        this.transitionFromPose.set(boneName, node.quaternion.clone());
      }
    });

    // Obtener pose inicial (t=0) del siguiente clip
    if (Array.isArray(nextClip.boneTracks)) {
      nextClip.boneTracks.forEach((track) => {
        if (track.rotations && track.rotations.length >= 4) {
          const q = new THREE.Quaternion(
            track.rotations[0],
            track.rotations[1],
            track.rotations[2],
            track.rotations[3]
          ).normalize();
          this.transitionToPose.set(track.boneName, q);
        }
      });
    }

    this.currentIndex = nextIndex;
    this.notifyGlossChanged(nextClip);
  }

  /**
   * Actualización del secuenciador en cada fotograma.
   * Si está en transición, interpola entre poses; si no, delega a SignPlayer.
   * @param {number} delta 
   */
  update(delta) {
    if (this.isTransitioning) {
      this.transitionTime += delta * this.speed;
      const alpha = Math.min(1.0, this.transitionTime / this.transitionDuration);

      // Aplicar slerp de transición a los huesos
      this.transitionFromPose.forEach((qFrom, boneName) => {
        const qTo = this.transitionToPose.get(boneName) || qFrom;
        const node = this.player.getBoneNode(boneName);
        if (node) {
          node.quaternion.copy(qFrom).slerp(qTo, alpha);
        }
      });

      if (alpha >= 1.0) {
        // Fin de transición: arrancar reproducción del clip siguiente
        this.isTransitioning = false;
        const currentClip = this.sequence[this.currentIndex];
        this.player.play(currentClip);
      }
    } else {
      this.player.update(delta);
    }
  }

  notifyGlossChanged(clip) {
    if (typeof this.onGlossChanged === 'function') {
      this.onGlossChanged({
        gloss: clip.gloss,
        clipId: clip.clipId,
        index: this.currentIndex,
        total: this.sequence.length,
        status: clip.status,
        validationStatus: clip.validationStatus
      });
    }
  }

  pause() {
    this.player.pause();
    if (typeof this.onStateChange === 'function') {
      this.onStateChange('paused');
    }
  }

  resume() {
    this.player.resume();
    if (typeof this.onStateChange === 'function') {
      this.onStateChange('playing');
    }
  }

  cancel() {
    this.isTransitioning = false;
    this.currentIndex = -1;
    this.sequence = [];
    this.player.stop();
    this.player.restoreNeutralPose();

    if (typeof this.onSequenceEnded === 'function') {
      this.onSequenceEnded();
    }
    if (typeof this.onStateChange === 'function') {
      this.onStateChange('stopped');
    }
  }

  setSpeed(rate) {
    this.speed = Math.max(0.1, Math.min(3.0, Number(rate) || 1.0));
    this.player.setSpeed(this.speed);
  }

  getActiveGloss() {
    if (this.currentIndex >= 0 && this.currentIndex < this.sequence.length) {
      return this.sequence[this.currentIndex].gloss;
    }
    return null;
  }
}
