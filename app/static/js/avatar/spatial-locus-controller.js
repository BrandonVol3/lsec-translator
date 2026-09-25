/**
 * LSEC Studio — Controlador de Espacio Lingüístico y Loci (SpatialLocusController)
 * 
 * Modela las coordenadas 3D de referencia en el espacio de señas:
 * - Locus Centro (neutro / discurso presente)
 * - Locus Izquierda (entidad A)
 * - Locus Derecha (entidad B / contraste)
 * - Locus Superior (autoridad / abstracto)
 * - Locus Inferior (concreto / temporal)
 */

import * as THREE from 'three';

export class SpatialLocusController {
  constructor() {
    // Coordenadas relativas al pecho del avatar (en metros)
    this.loci = {
      CENTER: new THREE.Vector3(0.0, 1.15, 0.35),
      LEFT:   new THREE.Vector3(0.32, 1.15, 0.30),
      RIGHT:  new THREE.Vector3(-0.32, 1.15, 0.30),
      HIGH:   new THREE.Vector3(0.0, 1.45, 0.30),
      LOW:    new THREE.Vector3(0.0, 0.85, 0.30)
    };
  }

  /**
   * Obtiene la posición 3D correspondiente a un locus lingüístico.
   * @param {string} locusName - 'CENTER' | 'LEFT' | 'RIGHT' | 'HIGH' | 'LOW'
   * @returns {THREE.Vector3}
   */
  getLocusPosition(locusName) {
    const key = (locusName || 'CENTER').toUpperCase();
    return this.loci[key] ? this.loci[key].clone() : this.loci.CENTER.clone();
  }

  /**
   * Calcula el vector de dirección desde la cabeza hacia el locus para orientar la mirada.
   * @param {THREE.Vector3} headPos 
   * @param {string} locusName 
   * @returns {THREE.Vector3} Vector normalizado
   */
  getGazeDirection(headPos, locusName) {
    const target = this.getLocusPosition(locusName);
    return target.sub(headPos).normalize();
  }
}
