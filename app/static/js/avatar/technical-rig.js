/**
 * LSEC Studio — Rig Técnico de Reserva (Fallback Humanoid Rig)
 * 
 * Implementa una estructura esquelética humanoide normalizada utilizando
 * primitivas geométricas de Three.js. Permite probar y validar:
 * - Renderizado en escena y encuadre de cámara;
 * - Ejecución de animaciones por cuaterniones;
 * - Secuenciación e interpolación de clips;
 * - Controles de reproducción, velocidad y sincronización;
 * 
 * Cumple con la misma interfaz `getNormalizedBoneNode(boneName)` que un avatar
 * VRM 1.0 real, garantizando total transparencia e interoperabilidad con
 * el reproductor y secuenciador.
 * 
 * NOTA DE DISEÑO:
 * Este rig es un instrumento técnico de verificación y reserva. No sustituye
 * al modelo VRM final ni simula anatomía humana completa.
 */

import * as THREE from 'three';

export class TechnicalRig {
  constructor() {
    this.root = new THREE.Group();
    this.root.name = 'TechnicalRig_Root';

    this.bones = new Map();
    this.initialTransforms = new Map();
    this.geometries = [];
    this.materials = [];

    this.expressionState = {
      angry: 0,
      happy: 0,
      blink: 0
    };

    this.buildSkeleton();
    this.saveInitialTransforms();
  }

  buildSkeleton() {
    // Paleta de materiales sobrios y de alto contraste
    const bodyMat = new THREE.MeshStandardMaterial({
      color: 0x2A2E28,
      roughness: 0.45,
      metalness: 0.1
    });
    const jointMat = new THREE.MeshStandardMaterial({
      color: 0xB7D36B, // Verde lima del sistema de diseño
      roughness: 0.35,
      metalness: 0.2
    });
    const handMat = new THREE.MeshStandardMaterial({
      color: 0xD8A84E, // Acento cálido para máxima visibilidad de manos
      roughness: 0.4,
      metalness: 0.15
    });
    const headMat = new THREE.MeshStandardMaterial({
      color: 0x3E453A,
      roughness: 0.4,
      metalness: 0.1
    });
    const eyeMat = new THREE.MeshBasicMaterial({ color: 0xF2F1EC });
    const mouthMat = new THREE.MeshBasicMaterial({ color: 0x111210 });

    this.materials.push(bodyMat, jointMat, handMat, headMat, eyeMat, mouthMat);

    // 1. Cadera / Pelvis (Hips) a altura natural (~0.95m)
    const hips = new THREE.Group();
    hips.name = 'hips';
    hips.position.set(0, 0.95, 0);
    this.root.add(hips);
    this.bones.set('hips', hips);

    const pelvisGeo = new THREE.CylinderGeometry(0.13, 0.11, 0.14, 16);
    this.geometries.push(pelvisGeo);
    const pelvisMesh = new THREE.Mesh(pelvisGeo, bodyMat);
    hips.add(pelvisMesh);

    // 2. Columna / Spine
    const spine = new THREE.Group();
    spine.name = 'spine';
    spine.position.set(0, 0.11, 0);
    hips.add(spine);
    this.bones.set('spine', spine);

    const spineGeo = new THREE.CylinderGeometry(0.10, 0.12, 0.13, 16);
    this.geometries.push(spineGeo);
    const spineMesh = new THREE.Mesh(spineGeo, bodyMat);
    spineMesh.position.set(0, 0.065, 0);
    spine.add(spineMesh);

    // 3. Pecho / Chest
    const chest = new THREE.Group();
    chest.name = 'chest';
    chest.position.set(0, 0.13, 0);
    spine.add(chest);
    this.bones.set('chest', chest);

    const chestGeo = new THREE.BoxGeometry(0.28, 0.20, 0.15);
    this.geometries.push(chestGeo);
    const chestMesh = new THREE.Mesh(chestGeo, bodyMat);
    chestMesh.position.set(0, 0.10, 0);
    chest.add(chestMesh);

    // 4. Cuello / Neck
    const neck = new THREE.Group();
    neck.name = 'neck';
    neck.position.set(0, 0.21, 0);
    chest.add(neck);
    this.bones.set('neck', neck);

    const neckGeo = new THREE.CylinderGeometry(0.045, 0.05, 0.08, 12);
    this.geometries.push(neckGeo);
    const neckMesh = new THREE.Mesh(neckGeo, bodyMat);
    neckMesh.position.set(0, 0.04, 0);
    neck.add(neckMesh);

    // 5. Cabeza / Head
    const head = new THREE.Group();
    head.name = 'head';
    head.position.set(0, 0.08, 0);
    neck.add(head);
    this.bones.set('head', head);

    const headGeo = new THREE.SphereGeometry(0.105, 20, 20);
    this.geometries.push(headGeo);
    const headMesh = new THREE.Mesh(headGeo, headMat);
    headMesh.position.set(0, 0.10, 0);
    head.add(headMesh);

    // Rasgos faciales para expresiones y dirección de mirada (miran hacia +Z)
    const eyeGeo = new THREE.SphereGeometry(0.015, 8, 8);
    this.geometries.push(eyeGeo);

    this.leftEye = new THREE.Mesh(eyeGeo, eyeMat);
    this.leftEye.position.set(0.038, 0.11, 0.095);
    head.add(this.leftEye);

    this.rightEye = new THREE.Mesh(eyeGeo, eyeMat);
    this.rightEye.position.set(-0.038, 0.11, 0.095);
    head.add(this.rightEye);

    const browGeo = new THREE.BoxGeometry(0.035, 0.007, 0.01);
    this.geometries.push(browGeo);

    this.leftBrow = new THREE.Mesh(browGeo, jointMat);
    this.leftBrow.position.set(0.038, 0.13, 0.096);
    head.add(this.leftBrow);

    this.rightBrow = new THREE.Mesh(browGeo, jointMat);
    this.rightBrow.position.set(-0.038, 0.13, 0.096);
    head.add(this.rightBrow);

    const mouthGeo = new THREE.BoxGeometry(0.04, 0.008, 0.01);
    this.geometries.push(mouthGeo);
    this.mouth = new THREE.Mesh(mouthGeo, mouthMat);
    this.mouth.position.set(0, 0.065, 0.098);
    head.add(this.mouth);

    // --- EXTREMIDAD SUPERIOR DERECHA ---
    const rightShoulder = new THREE.Group();
    rightShoulder.name = 'rightShoulder';
    rightShoulder.position.set(-0.16, 0.18, 0);
    chest.add(rightShoulder);
    this.bones.set('rightShoulder', rightShoulder);

    const rightUpperArm = new THREE.Group();
    rightUpperArm.name = 'rightUpperArm';
    rightUpperArm.position.set(-0.05, 0, 0);
    rightShoulder.add(rightUpperArm);
    this.bones.set('rightUpperArm', rightUpperArm);

    const upperArmGeo = new THREE.CylinderGeometry(0.038, 0.032, 0.25, 12);
    this.geometries.push(upperArmGeo);
    const rUaMesh = new THREE.Mesh(upperArmGeo, bodyMat);
    rUaMesh.position.set(0, -0.125, 0);
    rightUpperArm.add(rUaMesh);

    const jointGeo = new THREE.SphereGeometry(0.042, 12, 12);
    this.geometries.push(jointGeo);
    const rElbowJoint = new THREE.Mesh(jointGeo, jointMat);
    rElbowJoint.position.set(0, -0.25, 0);
    rightUpperArm.add(rElbowJoint);

    const rightLowerArm = new THREE.Group();
    rightLowerArm.name = 'rightLowerArm';
    rightLowerArm.position.set(0, -0.25, 0);
    rightUpperArm.add(rightLowerArm);
    this.bones.set('rightLowerArm', rightLowerArm);

    const lowerArmGeo = new THREE.CylinderGeometry(0.032, 0.026, 0.23, 12);
    this.geometries.push(lowerArmGeo);
    const rLaMesh = new THREE.Mesh(lowerArmGeo, bodyMat);
    rLaMesh.position.set(0, -0.115, 0);
    rightLowerArm.add(rLaMesh);

    const rightHand = new THREE.Group();
    rightHand.name = 'rightHand';
    rightHand.position.set(0, -0.23, 0);
    rightLowerArm.add(rightHand);
    this.bones.set('rightHand', rightHand);

    // Palma y dedos esquemáticos
    const palmGeo = new THREE.BoxGeometry(0.065, 0.075, 0.022);
    this.geometries.push(palmGeo);
    const rPalmMesh = new THREE.Mesh(palmGeo, handMat);
    rPalmMesh.position.set(0, -0.04, 0);
    rightHand.add(rPalmMesh);

    // Dedos esquemáticos del brazo derecho para ver orientación clara
    this.createFingers(rightHand, handMat, false);

    // --- EXTREMIDAD SUPERIOR IZQUIERDA ---
    const leftShoulder = new THREE.Group();
    leftShoulder.name = 'leftShoulder';
    leftShoulder.position.set(0.16, 0.18, 0);
    chest.add(leftShoulder);
    this.bones.set('leftShoulder', leftShoulder);

    const leftUpperArm = new THREE.Group();
    leftUpperArm.name = 'leftUpperArm';
    leftUpperArm.position.set(0.05, 0, 0);
    leftShoulder.add(leftUpperArm);
    this.bones.set('leftUpperArm', leftUpperArm);

    const lUaMesh = new THREE.Mesh(upperArmGeo, bodyMat);
    lUaMesh.position.set(0, -0.125, 0);
    leftUpperArm.add(lUaMesh);

    const lElbowJoint = new THREE.Mesh(jointGeo, jointMat);
    lElbowJoint.position.set(0, -0.25, 0);
    leftUpperArm.add(lElbowJoint);

    const leftLowerArm = new THREE.Group();
    leftLowerArm.name = 'leftLowerArm';
    leftLowerArm.position.set(0, -0.25, 0);
    leftUpperArm.add(leftLowerArm);
    this.bones.set('leftLowerArm', leftLowerArm);

    const lLaMesh = new THREE.Mesh(lowerArmGeo, bodyMat);
    lLaMesh.position.set(0, -0.115, 0);
    leftLowerArm.add(lLaMesh);

    const leftHand = new THREE.Group();
    leftHand.name = 'leftHand';
    leftHand.position.set(0, -0.23, 0);
    leftLowerArm.add(leftHand);
    this.bones.set('leftHand', leftHand);

    const lPalmMesh = new THREE.Mesh(palmGeo, handMat);
    lPalmMesh.position.set(0, -0.04, 0);
    leftHand.add(lPalmMesh);

    this.createFingers(leftHand, handMat, true);

    // --- EXTREMIDADES INFERIORES Y PEDESTAL TÉCNICO ---
    const legGeo = new THREE.CylinderGeometry(0.055, 0.04, 0.85, 12);
    this.geometries.push(legGeo);

    const leftLegMesh = new THREE.Mesh(legGeo, bodyMat);
    leftLegMesh.position.set(0.10, -0.45, 0);
    hips.add(leftLegMesh);

    const rightLegMesh = new THREE.Mesh(legGeo, bodyMat);
    rightLegMesh.position.set(-0.10, -0.45, 0);
    hips.add(rightLegMesh);

    // Base circular estilizada para soporte visual
    const baseGeo = new THREE.CylinderGeometry(0.35, 0.38, 0.04, 24);
    this.geometries.push(baseGeo);
    const baseMesh = new THREE.Mesh(baseGeo, jointMat);
    baseMesh.position.set(0, 0.02, 0);
    this.root.add(baseMesh);
  }

  createFingers(handNode, material, isLeft) {
    const fingerGeo = new THREE.BoxGeometry(0.010, 0.035, 0.012);
    this.geometries.push(fingerGeo);

    const side = isLeft ? 1 : -1;
    // 4 dedos extendidos
    const xOffsets = [-0.022, -0.007, 0.008, 0.022];
    xOffsets.forEach(x => {
      const fMesh = new THREE.Mesh(fingerGeo, material);
      fMesh.position.set(x, -0.09, 0);
      handNode.add(fMesh);
    });

    // Pulgar orientado
    const thumbMesh = new THREE.Mesh(fingerGeo, material);
    thumbMesh.position.set(side * 0.038, -0.05, 0.015);
    thumbMesh.rotation.z = side * -0.5;
    handNode.add(thumbMesh);
  }

  saveInitialTransforms() {
    this.bones.forEach((node, name) => {
      this.initialTransforms.set(name, {
        position: node.position.clone(),
        quaternion: node.quaternion.clone(),
        scale: node.scale.clone()
      });
    });
  }

  /**
   * Obtiene el nodo Three.js correspondiente a un hueso normalizado VRM.
   * Compatible con la API de VRMHumanoid.
   * @param {string} boneName 
   * @returns {THREE.Object3D|null}
   */
  getNormalizedBoneNode(boneName) {
    return this.bones.get(boneName) || null;
  }

  /**
   * Simula expresiones faciales modificando cejas, ojos o boca.
   * @param {string} expressionName 
   * @param {number} weight - Rango [0, 1]
   */
  setExpressionWeight(expressionName, weight) {
    const w = Math.max(0, Math.min(1, weight));
    this.expressionState[expressionName] = w;

    if (expressionName === 'angry') {
      // Fruncir cejas hacia abajo y adentro
      if (this.leftBrow && this.rightBrow) {
        this.leftBrow.position.y = 0.13 - w * 0.012;
        this.leftBrow.rotation.z = -w * 0.35;
        this.rightBrow.position.y = 0.13 - w * 0.012;
        this.rightBrow.rotation.z = w * 0.35;
      }
    } else if (expressionName === 'blink') {
      // Escalar ojos en Y para simular parpadeo
      const scaleY = Math.max(0.1, 1.0 - w * 0.9);
      if (this.leftEye) this.leftEye.scale.y = scaleY;
      if (this.rightEye) this.rightEye.scale.y = scaleY;
    } else if (expressionName === 'happy') {
      // Elevar cejas y ensanchar boca
      if (this.leftBrow && this.rightBrow) {
        this.leftBrow.position.y = 0.13 + w * 0.008;
        this.rightBrow.position.y = 0.13 + w * 0.008;
      }
      if (this.mouth) {
        this.mouth.scale.x = 1.0 + w * 0.4;
      }
    }
  }

  /**
   * Restaura la postura y expresiones iniciales.
   */
  resetPose() {
    this.bones.forEach((node, name) => {
      const init = this.initialTransforms.get(name);
      if (init) {
        node.position.copy(init.position);
        node.quaternion.copy(init.quaternion);
        node.scale.copy(init.scale);
      }
    });

    this.setExpressionWeight('angry', 0);
    this.setExpressionWeight('blink', 0);
    this.setExpressionWeight('happy', 0);
  }

  /**
   * Libera geometrías y materiales.
   */
  dispose() {
    this.geometries.forEach(geo => geo.dispose());
    this.materials.forEach(mat => mat.dispose());
    this.geometries = [];
    this.materials = [];
    if (this.root.parent) {
      this.root.parent.remove(this.root);
    }
  }
}
