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
import { VRMLoaderPlugin, VRMUtils, VRMExpression } from '@pixiv/three-vrm';
import { ARKIT_BLENDSHAPE_NAMES, VRM_EXPRESSION_NAMES } from './sign-animation-schema.js';

/**
 * Orden canónico de los 57 morph targets faciales VRoid en LSEC-Interpreter-Female.vrm.
 * Se utiliza como respaldo si GLTFLoader no pobló mesh.morphTargetDictionary desde primitive.extras.targetNames.
 */
const CANONICAL_VROID_57_TARGET_NAMES = Object.freeze([
  'Fcl_ALL_Neutral',
  'Fcl_ALL_Angry',
  'Fcl_ALL_Fun',
  'Fcl_ALL_Joy',
  'Fcl_ALL_Sorrow',
  'Fcl_ALL_Surprised',
  'Fcl_BRW_Angry',
  'Fcl_BRW_Fun',
  'Fcl_BRW_Joy',
  'Fcl_BRW_Sorrow',
  'Fcl_BRW_Surprised',
  'Fcl_EYE_Natural',
  'Fcl_EYE_Angry',
  'Fcl_EYE_Close',
  'Fcl_EYE_Close_R',
  'Fcl_EYE_Close_L',
  'Fcl_EYE_Fun',
  'Fcl_EYE_Joy',
  'Fcl_EYE_Joy_R',
  'Fcl_EYE_Joy_L',
  'Fcl_EYE_Sorrow',
  'Fcl_EYE_Surprised',
  'Fcl_EYE_Spread',
  'Fcl_EYE_Iris_Hide',
  'Fcl_EYE_Highlight_Hide',
  'Fcl_MTH_Close',
  'Fcl_MTH_Up',
  'Fcl_MTH_Down',
  'Fcl_MTH_Angry',
  'Fcl_MTH_Small',
  'Fcl_MTH_Large',
  'Fcl_MTH_Neutral',
  'Fcl_MTH_Fun',
  'Fcl_MTH_Joy',
  'Fcl_MTH_Sorrow',
  'Fcl_MTH_Surprised',
  'Fcl_MTH_SkinFung',
  'Fcl_MTH_SkinFung_R',
  'Fcl_MTH_SkinFung_L',
  'Fcl_MTH_A',
  'Fcl_MTH_I',
  'Fcl_MTH_U',
  'Fcl_MTH_E',
  'Fcl_MTH_O',
  'Fcl_HA_Hide',
  'Fcl_HA_Fung1',
  'Fcl_HA_Fung1_Low',
  'Fcl_HA_Fung1_Up',
  'Fcl_HA_Fung2',
  'Fcl_HA_Fung2_Low',
  'Fcl_HA_Fung2_Up',
  'Fcl_HA_Fung3',
  'Fcl_HA_Fung3_Up',
  'Fcl_HA_Fung3_Low',
  'Fcl_HA_Short',
  'Fcl_HA_Short_Up',
  'Fcl_HA_Short_Low'
]);

/**
 * Mapeo anatómico de los 52 blendshapes ARKit + 4 presets lookAt hacia los morph targets VRoid Fcl_*.
 * Los pesos están calibrados para sumarse de forma natural con los 14 presets VRM sin saturar la malla.
 */
const ARKIT_TO_VROID_MORPH_MAP = Object.freeze({
  // Cejas (Brows)
  browDownLeft: [['Fcl_BRW_Angry', 0.50], ['Fcl_BRW_Sorrow', 0.15]],
  browDownRight: [['Fcl_BRW_Angry', 0.50], ['Fcl_BRW_Sorrow', 0.15]],
  browInnerUp: [['Fcl_BRW_Surprised', 0.60], ['Fcl_BRW_Sorrow', 0.30]],
  browOuterUpLeft: [['Fcl_BRW_Surprised', 0.45], ['Fcl_BRW_Fun', 0.30], ['Fcl_BRW_Joy', 0.20]],
  browOuterUpRight: [['Fcl_BRW_Surprised', 0.45], ['Fcl_BRW_Fun', 0.30], ['Fcl_BRW_Joy', 0.20]],

  // Ojos y Párpados (Eyes)
  eyeBlinkLeft: [['Fcl_EYE_Close_L', 0.35]],
  eyeBlinkRight: [['Fcl_EYE_Close_R', 0.35]],
  eyeSquintLeft: [['Fcl_EYE_Joy_L', 0.45], ['Fcl_EYE_Fun', 0.35]],
  eyeSquintRight: [['Fcl_EYE_Joy_R', 0.45], ['Fcl_EYE_Fun', 0.35]],
  eyeWideLeft: [['Fcl_EYE_Surprised', 0.45], ['Fcl_EYE_Spread', 0.45]],
  eyeWideRight: [['Fcl_EYE_Surprised', 0.45], ['Fcl_EYE_Spread', 0.45]],
  eyeLookUpLeft: [['Fcl_EYE_Spread', 0.18], ['Fcl_BRW_Surprised', 0.12]],
  eyeLookUpRight: [['Fcl_EYE_Spread', 0.18], ['Fcl_BRW_Surprised', 0.12]],
  eyeLookDownLeft: [['Fcl_EYE_Close_L', 0.15], ['Fcl_EYE_Sorrow', 0.15]],
  eyeLookDownRight: [['Fcl_EYE_Close_R', 0.15], ['Fcl_EYE_Sorrow', 0.15]],
  eyeLookInLeft: [['Fcl_EYE_Fun', 0.10]],
  eyeLookInRight: [['Fcl_EYE_Fun', 0.10]],
  eyeLookOutLeft: [['Fcl_EYE_Spread', 0.12]],
  eyeLookOutRight: [['Fcl_EYE_Spread', 0.12]],

  // Mejillas y Nariz (Cheeks & Nose)
  cheekPuff: [['Fcl_MTH_Large', 0.40], ['Fcl_MTH_Close', 0.35], ['Fcl_MTH_O', 0.20]],
  cheekSquintLeft: [['Fcl_EYE_Fun', 0.35], ['Fcl_EYE_Joy_L', 0.25], ['Fcl_MTH_Fun', 0.20]],
  cheekSquintRight: [['Fcl_EYE_Fun', 0.35], ['Fcl_EYE_Joy_R', 0.25], ['Fcl_MTH_Fun', 0.20]],
  noseSneerLeft: [['Fcl_BRW_Angry', 0.25], ['Fcl_MTH_Angry', 0.25], ['Fcl_MTH_SkinFung_L', 0.35]],
  noseSneerRight: [['Fcl_BRW_Angry', 0.25], ['Fcl_MTH_Angry', 0.25], ['Fcl_MTH_SkinFung_R', 0.35]],

  // Mandíbula y Boca (Jaw & Mouth)
  jawOpen: [['Fcl_MTH_Surprised', 0.40], ['Fcl_MTH_A', 0.30]],
  jawForward: [['Fcl_MTH_Small', 0.25], ['Fcl_MTH_U', 0.20]],
  jawLeft: [['Fcl_MTH_SkinFung_L', 0.35], ['Fcl_MTH_Fun', 0.15]],
  jawRight: [['Fcl_MTH_SkinFung_R', 0.35], ['Fcl_MTH_Fun', 0.15]],
  mouthClose: [['Fcl_MTH_Close', 0.75], ['Fcl_MTH_Neutral', 0.20]],
  mouthFunnel: [['Fcl_MTH_O', 0.40], ['Fcl_MTH_Small', 0.45]],
  mouthPucker: [['Fcl_MTH_U', 0.45], ['Fcl_MTH_Small', 0.55]],
  mouthLeft: [['Fcl_MTH_SkinFung_L', 0.40], ['Fcl_MTH_Up', 0.20]],
  mouthRight: [['Fcl_MTH_SkinFung_R', 0.40], ['Fcl_MTH_Up', 0.20]],
  mouthSmileLeft: [['Fcl_MTH_Up', 0.40], ['Fcl_MTH_Fun', 0.35], ['Fcl_MTH_Joy', 0.20]],
  mouthSmileRight: [['Fcl_MTH_Up', 0.40], ['Fcl_MTH_Fun', 0.35], ['Fcl_MTH_Joy', 0.20]],
  mouthFrownLeft: [['Fcl_MTH_Down', 0.45], ['Fcl_MTH_Angry', 0.30], ['Fcl_MTH_Sorrow', 0.25]],
  mouthFrownRight: [['Fcl_MTH_Down', 0.45], ['Fcl_MTH_Angry', 0.30], ['Fcl_MTH_Sorrow', 0.25]],
  mouthDimpleLeft: [['Fcl_MTH_Fun', 0.30], ['Fcl_MTH_Up', 0.25]],
  mouthDimpleRight: [['Fcl_MTH_Fun', 0.30], ['Fcl_MTH_Up', 0.25]],
  mouthStretchLeft: [['Fcl_MTH_I', 0.35], ['Fcl_MTH_Large', 0.30]],
  mouthStretchRight: [['Fcl_MTH_I', 0.35], ['Fcl_MTH_Large', 0.30]],
  mouthRollLower: [['Fcl_MTH_Close', 0.50], ['Fcl_MTH_Small', 0.35]],
  mouthRollUpper: [['Fcl_MTH_Close', 0.50], ['Fcl_MTH_Small', 0.35]],
  mouthShrugLower: [['Fcl_MTH_Down', 0.45], ['Fcl_MTH_Sorrow', 0.30]],
  mouthShrugUpper: [['Fcl_MTH_Up', 0.45], ['Fcl_MTH_Small', 0.25]],
  mouthPressLeft: [['Fcl_MTH_Close', 0.45], ['Fcl_MTH_Neutral', 0.30]],
  mouthPressRight: [['Fcl_MTH_Close', 0.45], ['Fcl_MTH_Neutral', 0.30]],
  mouthLowerDownLeft: [['Fcl_MTH_E', 0.35], ['Fcl_MTH_Surprised', 0.20]],
  mouthLowerDownRight: [['Fcl_MTH_E', 0.35], ['Fcl_MTH_Surprised', 0.20]],
  mouthUpperUpLeft: [['Fcl_MTH_SkinFung_L', 0.45], ['Fcl_MTH_Up', 0.25]],
  mouthUpperUpRight: [['Fcl_MTH_SkinFung_R', 0.45], ['Fcl_MTH_Up', 0.25]],
  tongueOut: [['Fcl_MTH_A', 0.35], ['Fcl_MTH_Large', 0.25]],

  // Presets VRM lookAt
  lookUp: [['Fcl_EYE_Spread', 0.25], ['Fcl_BRW_Surprised', 0.15]],
  lookDown: [['Fcl_EYE_Close', 0.18], ['Fcl_EYE_Sorrow', 0.15]],
  lookLeft: [['Fcl_EYE_Fun', 0.12]],
  lookRight: [['Fcl_EYE_Fun', 0.12]]
});

/**
 * Mapeo de mirada ocular en grados (yaw, pitch) para los blendshapes ARKit eyeLook* y presets look*.
 */
const EYE_GAZE_DEGREES_MAP = Object.freeze({
  eyeLookUpLeft: { yaw: 0, pitch: 5.0 },
  eyeLookUpRight: { yaw: 0, pitch: 5.0 },
  eyeLookDownLeft: { yaw: 0, pitch: -5.0 },
  eyeLookDownRight: { yaw: 0, pitch: -5.0 },
  eyeLookInLeft: { yaw: -4.5, pitch: 0 },
  eyeLookOutRight: { yaw: -4.5, pitch: 0 },
  eyeLookOutLeft: { yaw: 4.5, pitch: 0 },
  eyeLookInRight: { yaw: 4.5, pitch: 0 },
  lookUp: { yaw: 0, pitch: 8.0 },
  lookDown: { yaw: 0, pitch: -8.0 },
  lookLeft: { yaw: 8.0, pitch: 0 },
  lookRight: { yaw: -8.0, pitch: 0 }
});

class ClampedMorphTargetBind {
  constructor({ primitives, index, weight }) {
    this.primitives = primitives;
    this.index = index;
    this.weight = weight;
  }

  applyWeight(weight) {
    if (weight <= 0) return;
    const delta = this.weight * weight;
    for (let i = 0; i < this.primitives.length; i++) {
      const mesh = this.primitives[i];
      if (mesh.morphTargetInfluences && mesh.morphTargetInfluences[this.index] != null) {
        mesh.morphTargetInfluences[this.index] = Math.min(
          1.0,
          Math.max(0.0, mesh.morphTargetInfluences[this.index] + delta)
        );
      }
    }
  }

  clearAppliedWeight() {
    for (let i = 0; i < this.primitives.length; i++) {
      const mesh = this.primitives[i];
      if (mesh.morphTargetInfluences && mesh.morphTargetInfluences[this.index] != null) {
        mesh.morphTargetInfluences[this.index] = 0;
      }
    }
  }
}

class EyeBoneGazeBind {
  constructor({ accumulator, yawDeg, pitchDeg }) {
    this.accumulator = accumulator;
    this.yawDeg = yawDeg;
    this.pitchDeg = pitchDeg;
  }

  applyWeight(weight) {
    if (weight <= 0.0001) return;
    this.accumulator.add(this.yawDeg * weight, this.pitchDeg * weight);
  }

  clearAppliedWeight() {
    this.accumulator.reset();
  }
}

/**
 * Garantiza que el modelo VRM tenga registrados y vinculados a sus morph targets faciales
 * (y huesos oculares) tanto los 18 presets VRM 1.0 como los 52 blendshapes ARKit.
 * @param {Object} vrm - Instancia VRM cargada.
 * @param {Object} [gltf] - Objeto GLTF opcional devuelto por GLTFLoader.
 */
export function ensureARKitAndVRMExpressionBindings(vrm, gltf = null) {
  if (!vrm || !vrm.scene || !vrm.expressionManager) return;

  // 1. Extraer targetNames desde el JSON GLTF si están anidados en primitives[0].extras.targetNames
  let gltfTargetNames = null;
  const gltfMeshes = gltf?.parser?.json?.meshes;
  if (Array.isArray(gltfMeshes)) {
    for (const mDef of gltfMeshes) {
      if (Array.isArray(mDef?.extras?.targetNames) && mDef.extras.targetNames.length > 0) {
        gltfTargetNames = mDef.extras.targetNames;
        break;
      }
      if (Array.isArray(mDef?.primitives)) {
        for (const pDef of mDef.primitives) {
          if (Array.isArray(pDef?.extras?.targetNames) && pDef.extras.targetNames.length > 0) {
            gltfTargetNames = pDef.extras.targetNames;
            break;
          }
        }
      }
      if (gltfTargetNames) break;
    }
  }

  // 2. Localizar mallas faciales con morphTargetInfluences y asegurar morphTargetDictionary
  const morphMeshes = [];
  const targetNameToIndex = new Map();

  vrm.scene.traverse((obj) => {
    if (obj.isMesh && Array.isArray(obj.morphTargetInfluences) && obj.morphTargetInfluences.length > 0) {
      morphMeshes.push(obj);
      if (!obj.morphTargetDictionary || Object.keys(obj.morphTargetDictionary).length === 0) {
        const names =
          gltfTargetNames && gltfTargetNames.length === obj.morphTargetInfluences.length
            ? gltfTargetNames
            : obj.morphTargetInfluences.length === CANONICAL_VROID_57_TARGET_NAMES.length
              ? CANONICAL_VROID_57_TARGET_NAMES
              : null;
        if (names) {
          obj.morphTargetDictionary = {};
          for (let i = 0; i < names.length; i++) {
            obj.morphTargetDictionary[names[i]] = i;
          }
        }
      }
      if (obj.morphTargetDictionary) {
        for (const [tName, tIdx] of Object.entries(obj.morphTargetDictionary)) {
          if (!targetNameToIndex.has(tName)) {
            targetNameToIndex.set(tName, tIdx);
          }
        }
      }
    }
  });

  // 3. Neutralizar el peso de Fcl_ALL_Neutral en la expresión 'neutral' para que no oponga resistencia
  //    a los 13 presets expresivos ni a los 52 blendshapes ARKit, y envolver binds existentes con clamp [0, 1].
  const existingExpressions = vrm.expressionManager.expressions || [];
  for (const expr of existingExpressions) {
    if (!expr || !Array.isArray(expr._binds)) continue;
    if (expr.expressionName === 'neutral') {
      for (const b of expr._binds) {
        if (typeof b.weight === 'number') {
          b.weight = 0.0;
        }
      }
    } else {
      for (let i = 0; i < expr._binds.length; i++) {
        const b = expr._binds[i];
        if (b && Array.isArray(b.primitives) && typeof b.index === 'number' && !(b instanceof ClampedMorphTargetBind)) {
          expr._binds[i] = new ClampedMorphTargetBind({
            primitives: b.primitives,
            index: b.index,
            weight: typeof b.weight === 'number' ? b.weight : 1.0
          });
        }
      }
    }
  }

  // 4. Habilitar escala horizontal interna en lookAt si el exportador VRoid la dejó en 0
  if (vrm.lookAt?.applier?.rangeMapHorizontalInner && vrm.lookAt.applier.rangeMapHorizontalInner.outputScale === 0) {
    vrm.lookAt.applier.rangeMapHorizontalInner.outputScale = 10;
  }

  const eyeAccumulator = {
    yaw: 0,
    pitch: 0,
    isReset: true,
    reset() {
      if (!this.isReset) {
        this.yaw = 0;
        this.pitch = 0;
        this.isReset = true;
        if (vrm.lookAt?.applier && typeof vrm.lookAt.applier.applyYawPitch === 'function') {
          vrm.lookAt.applier.applyYawPitch(0, 0);
        }
      }
    },
    add(dYaw, dPitch) {
      this.yaw = Math.max(-18, Math.min(18, this.yaw + dYaw));
      this.pitch = Math.max(-15, Math.min(15, this.pitch + dPitch));
      this.isReset = false;
      if (vrm.lookAt?.applier && typeof vrm.lookAt.applier.applyYawPitch === 'function') {
        vrm.lookAt.applier.applyYawPitch(this.yaw, this.pitch);
      }
    }
  };

  // 5. Registrar y vincular los 52 blendshapes ARKit y cualquier preset VRM faltante
  const allTrackNames = [...VRM_EXPRESSION_NAMES, ...ARKIT_BLENDSHAPE_NAMES];
  for (const exprName of allTrackNames) {
    let expr = vrm.expressionManager.getExpression(exprName);
    if (!expr) {
      expr = new VRMExpression(exprName);
      vrm.scene.add(expr);
      vrm.expressionManager.registerExpression(expr);
    }

    if (expr._binds && expr._binds.length === 0) {
      const morphTargets = ARKIT_TO_VROID_MORPH_MAP[exprName];
      if (Array.isArray(morphTargets) && morphMeshes.length > 0) {
        for (const [morphName, morphWeight] of morphTargets) {
          const morphIndex = targetNameToIndex.get(morphName);
          if (typeof morphIndex === 'number') {
            expr.addBind(
              new ClampedMorphTargetBind({
                primitives: morphMeshes,
                index: morphIndex,
                weight: morphWeight
              })
            );
          }
        }
      }

      const gazeDef = EYE_GAZE_DEGREES_MAP[exprName];
      if (gazeDef && vrm.lookAt?.applier) {
        expr.addBind(
          new EyeBoneGazeBind({
            accumulator: eyeAccumulator,
            yawDeg: gazeDef.yaw,
            pitchDeg: gazeDef.pitch
          })
        );
      }
    }
  }
}

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

            // Vincular los 52 blendshapes ARKit y 18 presets VRM a los morph targets faciales y mirada
            ensureARKitAndVRMExpressionBindings(vrm, gltf);

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

            console.info(`[VRMLoaderService] Avatar VRM cargado con éxito. Expresiones disponibles (${this.availableExpressions.size}): ${Array.from(this.availableExpressions).slice(0, 18).join(', ')}...`);

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
