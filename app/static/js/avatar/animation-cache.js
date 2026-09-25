/**
 * LSEC Studio — Caché de Clips y Animaciones del Avatar
 * 
 * Almacena en memoria clips de animación validados y sus representaciones
 * procesadas de Three.js para evitar reprocesamiento y deserialización reiterada.
 */

export class AnimationCache {
  constructor() {
    this.clipStore = new Map();
    this.threeClipStore = new Map();
  }

  /**
   * Guarda un clip validado en la caché.
   * @param {string} clipId 
   * @param {Object} clip 
   */
  setClip(clipId, clip) {
    if (!clipId || !clip) return;
    this.clipStore.set(clipId, clip);
  }

  /**
   * Obtiene un clip por su ID.
   * @param {string} clipId 
   * @returns {Object|null}
   */
  getClip(clipId) {
    return this.clipStore.get(clipId) || null;
  }

  hasClip(clipId) {
    return this.clipStore.has(clipId);
  }

  /**
   * Guarda un AnimationClip de Three.js generado.
   * @param {string} clipId 
   * @param {THREE.AnimationClip} threeClip 
   */
  setThreeClip(clipId, threeClip) {
    if (!clipId || !threeClip) return;
    this.threeClipStore.set(clipId, threeClip);
  }

  getThreeClip(clipId) {
    return this.threeClipStore.get(clipId) || null;
  }

  getAllClips() {
    return Array.from(this.clipStore.values());
  }

  /**
   * Libera la memoria de la caché.
   */
  clear() {
    this.clipStore.clear();
    this.threeClipStore.clear();
  }
}

export const defaultAnimationCache = new AnimationCache();
