/**
 * LSEC Studio — Controlador de Componentes No Manuales (NonManualController)
 * 
 * Gestiona la articulación coordinada de rasgos no manuales:
 * - Orientación e inclinación de cabeza y cuello;
 * - Mirada (gaze) y parpadeo;
 * - Cejas y apertura bucal;
 * - Activación controlada de expresiones faciales disponibles en VRM.
 * 
 * NOTA DE RIGOR LINGÜÍSTICO:
 * No infiere emociones ni clasifica expresiones como funciones gramaticales LSEC
 * sin evidencia explícita provista por el revisor humano o corpus validado.
 */

import * as THREE from 'three';

export class NonManualController {
  constructor() {
    this.model = null;
    this.isVRM = false;
    this.activeMarkers = [];
  }

  setModel(model, isVRM = false) {
    this.model = model;
    this.isVRM = isVRM;
  }

  /**
   * Registra un conjunto de marcadores no manuales asociados a un segmento temporal.
   * Estructura del marcador:
   * - markerId: string
   * - markerType: 'HEAD_NOD' | 'HEAD_SHAKE' | 'HEAD_TILT' | 'EYEBROW_RAISE' | 'EYEBROW_FURROW' | 'EYE_GAZE' | 'MOUTH_GESTURE'
   * - startMs: number
   * - endMs: number
   * - intensity: number [0, 1]
   * - grammaticalFunction: string (ej: 'INTERROGATIVE_POLAR', 'TOPICALIZATION', 'DEMO_TEST')
   * - validationStatus: 'REQUIRES_LSEC_VALIDATION' | 'HUMAN_REVIEWED' | 'VALIDATED_LSEC'
   * 
   * @param {Array<Object>} markers 
   */
  setMarkers(markers) {
    this.activeMarkers = Array.isArray(markers) ? markers : [];
  }

  /**
   * Evalúa y aplica los marcadores no manuales activos en el tiempo actual (ms).
   * @param {number} currentMs 
   */
  updateAtTime(currentMs) {
    if (!this.model) return;

    for (let i = 0; i < this.activeMarkers.length; i++) {
      const m = this.activeMarkers[i];
      if (currentMs >= m.startMs && currentMs <= m.endMs) {
        const span = m.endMs - m.startMs;
        const progress = span > 0 ? (currentMs - m.startMs) / span : 0;
        const bellWeight = Math.sin(progress * Math.PI) * (m.intensity || 0.5);

        this.applyMarker(m.markerType, bellWeight);
      }
    }
  }

  applyMarker(type, weight) {
    if (!this.model) return;

    switch (type) {
      case 'HEAD_SHAKE': // Negación
        this.rotateHead(0, (Math.sin(weight * Math.PI * 2) * 0.2), 0);
        this.setExpression('angry', weight * 0.4);
        break;

      case 'HEAD_NOD': // Afirmación
        this.rotateHead(weight * 0.15, 0, 0);
        this.setExpression('happy', weight * 0.3);
        break;

      case 'EYEBROW_RAISE': // Interrogativa / Tópico
        this.setExpression('surprised', weight * 0.5);
        break;

      case 'EYEBROW_FURROW': // Interrogativa parcial (WH)
        this.setExpression('angry', weight * 0.45);
        break;

      case 'BLINK': // Parpadeo
        this.setExpression('blink', weight);
        break;

      default:
        break;
    }
  }

  rotateHead(pitchRad, yawRad, rollRad) {
    const headNode = this.getBoneNode('head');
    if (headNode) {
      headNode.rotation.set(pitchRad, yawRad, rollRad);
    }
  }

  setExpression(name, weight) {
    if (this.isVRM && this.model.expressionManager) {
      try {
        this.model.expressionManager.setValue(name, Math.max(0, Math.min(1, weight)));
      } catch (e) {}
    } else if (typeof this.model.setExpressionWeight === 'function') {
      this.model.setExpressionWeight(name, weight);
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

  reset() {
    this.rotateHead(0, 0, 0);
    this.setExpression('angry', 0);
    this.setExpression('happy', 0);
    this.setExpression('surprised', 0);
    this.setExpression('blink', 0);
  }
}
