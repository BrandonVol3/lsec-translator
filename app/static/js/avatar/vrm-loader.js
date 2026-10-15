/**
 * LSEC Studio — Servicio de Carga de Modelos VRM 1.0
 * 
 * Utiliza Three.js GLTFLoader y el plugin oficial @pixiv/three-vrm para:
 * - Cargar archivos locales .vrm (vía ruta estática o input de archivo local).
 * - Validar la conformidad del avatar humanoide VRM 1.0.
 * - Orientar el modelo hacia la cámara frontal (+Z).
 * - Mapear y normalizar acceso a huesos humanoides.
 * - Detectar expresiones disponibles en expressionManager.
 * - Gestionar la liberación estricta de memoria (geometrías, texturas, shaders).
 */

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

export class VRMLoaderService {
  constructor() {
    this.loader = new GLTFLoader();
    this.loader.register((parser) => {
      return new VRMLoaderPlugin(parser);
    });

    this.currentVRM = null;
    this.currentObjectUrl = null;
    this.availableExpressions = new Set();
  }

  /**
   * Carga un modelo VRM desde una URL o un objeto File local.
   * @param {string|File|Blob} source - Ruta relativa/absoluta o archivo seleccionado.
   * @param {Function} [onProgress] - Callback opcional de progreso (0.0 a 1.0).
   * @returns {Promise<Object>} Instancia de VRM cargada.
   */
  async loadVRM(source, onProgress = null) {
    // 1. Descargar y liberar modelo anterior si existe
    this.unloadCurrentVRM();

    let loadUrl = '';
    if (typeof source === 'string') {
      loadUrl = source;
    } else if (source instanceof File || source instanceof Blob) {
      this.currentObjectUrl = URL.createObjectURL(source);
      loadUrl = this.currentObjectUrl;
    } else {
      throw new Error('[VRMLoaderService] Origen de modelo no válido. Debe ser URL string o File/Blob.');
    }

    console.info(`[VRMLoaderService] Iniciando carga de avatar VRM desde: ${typeof source === 'string' ? source : source.name}`);

    return new Promise((resolve, reject) => {
      this.loader.load(
        loadUrl,
        (gltf) => {
          try {
            const vrm = gltf.userData.vrm;

            if (!vrm) {
              throw new Error('El archivo cargado no contiene metadatos VRM 1.0 válidos.');
            }

            // Optimizaciones de malla VRM oficiales si están disponibles
            if (VRMUtils) {
              try {
                if (typeof VRMUtils.removeUnnecessaryVertices === 'function') {
                  VRMUtils.removeUnnecessaryVertices(gltf.scene);
                }
                if (typeof VRMUtils.combineSkeletons === 'function') {
                  VRMUtils.combineSkeletons(gltf.scene);
                } else if (typeof VRMUtils.removeUnnecessaryJoints === 'function') {
                  VRMUtils.removeUnnecessaryJoints(gltf.scene);
                }
              } catch (optErr) {
                console.warn('[VRMLoaderService] Aviso en optimización de vértices VRM:', optErr);
              }
            }

            // En VRM 1.0, el modelo ya viene orientado hacia el frente (+Z)
            vrm.scene.rotation.y = 0;

            // Desactivar frustum culling y activar sombras suaves en la malla del avatar
            vrm.scene.traverse((obj) => {
              if (obj.isMesh) {
                obj.frustumCulled = false;
                obj.castShadow = true;
                obj.receiveShadow = true;
              }
            });

            // Registrar expresiones faciales disponibles
            this.availableExpressions.clear();
            if (vrm.expressionManager) {
              if (vrm.expressionManager.expressions) {
                vrm.expressionManager.expressions.forEach((expr) => {
                  this.availableExpressions.add(expr.expressionName);
                });
              } else if (vrm.expressionManager.customExpressions) {
                Object.keys(vrm.expressionManager.customExpressions).forEach((k) => {
                  this.availableExpressions.add(k);
                });
              }
            }

            console.info(`[VRMLoaderService] Avatar VRM cargado con éxito. Expresiones disponibles: ${Array.from(this.availableExpressions).join(', ') || 'ninguna'}`);

            this.currentVRM = vrm;
            resolve(vrm);
          } catch (err) {
            console.error('[VRMLoaderService] Error procesando modelo VRM:', err);
            reject(err);
          }
        },
        (event) => {
          if (onProgress && event.lengthComputable && event.total > 0) {
            onProgress(event.loaded / event.total);
          }
        },
        (error) => {
          console.error('[VRMLoaderService] Fallo en la descarga del modelo VRM:', error);
          reject(error);
        }
      );
    });
  }

  /**
   * Verifica si una expresión facial existe en el avatar cargado.
   * @param {string} expressionName 
   * @returns {boolean}
   */
  hasExpression(expressionName) {
    return this.availableExpressions.has(expressionName);
  }

  /**
   * Aplica de forma segura una expresión facial si está soportada.
   * @param {string} expressionName 
   * @param {number} weight - [0, 1]
   */
  setExpression(expressionName, weight) {
    if (!this.currentVRM || !this.currentVRM.expressionManager) return;
    if (this.hasExpression(expressionName)) {
      this.currentVRM.expressionManager.setValue(expressionName, Math.max(0, Math.min(1, weight)));
    }
  }

  /**
   * Obtiene un hueso normalizado del avatar actual.
   * @param {string} boneName 
   * @returns {THREE.Object3D|null}
   */
  getNormalizedBoneNode(boneName) {
    if (!this.currentVRM || !this.currentVRM.humanoid) return null;
    return this.currentVRM.humanoid.getNormalizedBoneNode(boneName);
  }

  /**
   * Retira y libera la memoria del avatar actual.
   */
  unloadCurrentVRM() {
    if (this.currentVRM) {
      if (VRMUtils && VRMUtils.deepDispose) {
        try {
          VRMUtils.deepDispose(this.currentVRM.scene);
        } catch (e) {
          this.manualDeepDispose(this.currentVRM.scene);
        }
      } else {
        this.manualDeepDispose(this.currentVRM.scene);
      }

      if (this.currentVRM.scene.parent) {
        this.currentVRM.scene.parent.remove(this.currentVRM.scene);
      }

      this.currentVRM = null;
    }

    if (this.currentObjectUrl) {
      URL.revokeObjectURL(this.currentObjectUrl);
      this.currentObjectUrl = null;
    }

    this.availableExpressions.clear();
  }

  manualDeepDispose(rootNode) {
    if (!rootNode) return;
    rootNode.traverse((child) => {
      if (child.isMesh) {
        if (child.geometry) child.geometry.dispose();
        if (child.material) {
          if (Array.isArray(child.material)) {
            child.material.forEach((m) => this.disposeMaterial(m));
          } else {
            this.disposeMaterial(child.material);
          }
        }
      }
    });
  }

  disposeMaterial(material) {
    if (!material) return;
    ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'emissiveMap', 'alphaMap'].forEach((prop) => {
      if (material[prop]) material[prop].dispose();
    });
    material.dispose();
  }
}
