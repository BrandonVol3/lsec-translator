/**
 * LSEC Studio — Motor de Renderizado 3D del Avatar (AvatarEngine)
 * 
 * Gestiona la escena de Three.js, WebGLRenderer, iluminación optimizada
 * para claridad de manos y rostro, encuadre de cámara frontal, ciclo
 * de renderizado controlado (requestAnimationFrame) y redimensionamiento reactivo.
 * 
 * Diseñado para bajo consumo computacional, compatibilidad en equipos modestos
 * y contraste cromático con el sistema de diseño editorial de LSEC Studio.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export class AvatarEngine {
  /**
   * @param {HTMLCanvasElement} canvas 
   * @param {Object} [options]
   */
  constructor(canvas, options = {}) {
    if (!canvas) {
      throw new Error('[AvatarEngine] Se requiere un elemento canvas HTML para inicializar el motor.');
    }

    this.canvas = canvas;
    this.options = {
      clearColor: 0x151714, // Grafito neutro suave de LSEC Studio
      clearAlpha: 1.0,
      fov: 28,
      cameraPos: new THREE.Vector3(0, 1.28, 2.15),
      cameraTarget: new THREE.Vector3(0, 1.15, 0),
      ...options
    };

    this.scene = null;
    this.camera = null;
    this.controls = null;
    this.renderer = null;
    this.clock = new THREE.Clock();

    this.currentModel = null;
    this.isVRM = false;

    this.isRunning = false;
    this.animFrameId = null;
    this.resizeObserver = null;
    this.onUpdateCallback = null;

    this.init();
  }

  init() {
    try {
      // 1. Escena
      this.scene = new THREE.Scene();
      this.scene.background = new THREE.Color(this.options.clearColor);

      // 2. Cámara frontal ergonómica para lengua de señas
      const rect = this.canvas.getBoundingClientRect();
      const width = rect.width > 0 ? rect.width : 400;
      const height = rect.height > 0 ? rect.height : 450;
      const aspect = width / height;

      this.camera = new THREE.PerspectiveCamera(this.options.fov, aspect, 0.1, 20.0);
      this.camera.position.copy(this.options.cameraPos);
      this.camera.lookAt(this.options.cameraTarget);

      // 3. WebGLRenderer
      this.renderer = new THREE.WebGLRenderer({
        canvas: this.canvas,
        antialias: true,
        alpha: false,
        powerPreference: 'default'
      });

      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
      this.renderer.setSize(width, height, false);
      this.renderer.outputColorSpace = THREE.SRGBColorSpace;

      // 4. Iluminación uniforme: luz ambiental + clave frontal + relleno + contraluz sutil
      this.setupLighting();

      // 5. Controles de Cámara Ergonómicos (OrbitControls: Girar, Mover, Deslizar)
      this.setupCameraControls();

      // 6. Gestión del cambio de tamaño
      this.setupResizeObserver();

      // 7. Manejo de pérdida de contexto WebGL
      this.setupContextLostHandling();

      console.info('[AvatarEngine] Motor 3D y controles de cámara inicializados con éxito.');
    } catch (err) {
      console.error('[AvatarEngine] Error crítico inicializando WebGL:', err);
      throw err;
    }
  }

  setupCameraControls() {
    if (!this.camera || !this.renderer) return;

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.screenSpacePanning = true; // Paneo libre en pantalla (arriba/abajo/izq/der)
    
    // Distancias ergonómicas: permite inspección cercana de dedos sin cortar el avatar
    this.controls.minDistance = 0.35;
    this.controls.maxDistance = 5.5;

    // Ángulos polares limitados para evitar gimbal lock e inversión cenital/nadiral
    this.controls.minPolarAngle = Math.PI * 0.05;
    this.controls.maxPolarAngle = Math.PI * 0.90;

    // Centro inicial de atención: torso superior / espacio articulatorio
    this.controls.target.copy(this.options.cameraTarget);
    this.controls.update();

    // Actualizar estilo del cursor para indicar interactividad táctil/ratón
    this.canvas.style.cursor = 'grab';
    this.canvas.addEventListener('mousedown', () => {
      this.canvas.style.cursor = 'grabbing';
    });
    window.addEventListener('mouseup', () => {
      if (this.canvas) this.canvas.style.cursor = 'grab';
    });
  }

  setupLighting() {
    // Luz ambiental suave para no crear sombras opacas en dedos
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.85);
    this.scene.add(ambientLight);

    // Luz principal frontal superior derecha
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.15);
    keyLight.position.set(1.4, 2.5, 2.0);
    this.scene.add(keyLight);

    // Luz de relleno lateral izquierda
    const fillLight = new THREE.DirectionalLight(0xdde8d0, 0.65);
    fillLight.position.set(-1.4, 1.8, 1.5);
    this.scene.add(fillLight);

    // Luz trasera de recorte (rim light) con leve matiz lima
    // Delimita con precisión el contorno de los dedos y las manos sobre el torso
    const rimLight = new THREE.DirectionalLight(0xb7d36b, 0.40);
    rimLight.position.set(0, 2.2, -1.8);
    this.scene.add(rimLight);
  }

  setupResizeObserver() {
    const parent = this.canvas.parentElement || this.canvas;
    this.resizeObserver = new ResizeObserver(() => {
      this.onResize();
    });
    this.resizeObserver.observe(parent);
    window.addEventListener('resize', this.onResizeBound = () => this.onResize());
  }

  setupContextLostHandling() {
    this.onContextLostBound = (e) => {
      e.preventDefault();
      console.warn('[AvatarEngine] Contexto WebGL perdido temporalmente.');
      this.stop();
    };

    this.onContextRestoredBound = () => {
      console.info('[AvatarEngine] Contexto WebGL restaurado.');
      this.init();
      this.start();
    };

    this.canvas.addEventListener('webglcontextlost', this.onContextLostBound, false);
    this.canvas.addEventListener('webglcontextrestored', this.onContextRestoredBound, false);
  }

  onResize() {
    if (!this.canvas || !this.renderer || !this.camera) return;

    const parent = this.canvas.parentElement;
    const width = parent ? parent.clientWidth : this.canvas.clientWidth;
    const height = parent ? parent.clientHeight : this.canvas.clientHeight;

    if (width > 0 && height > 0) {
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(width, height, false);
    }
  }

  /**
   * Conecta un avatar (VRM o TechnicalRig) a la escena.
   * @param {Object} modelInstance - Objeto VRM o TechnicalRig
   * @param {boolean} isVRM 
   */
  setModel(modelInstance, isVRM = false) {
    this.removeModel();

    this.currentModel = modelInstance;
    this.isVRM = isVRM;

    if (isVRM && modelInstance.scene) {
      this.scene.add(modelInstance.scene);
    } else if (modelInstance.root) {
      this.scene.add(modelInstance.root);
    }

    this.autoFrameCamera();
  }

  /**
   * Retira el avatar activo de la escena.
   */
  removeModel() {
    if (!this.currentModel) return;

    if (this.isVRM && this.currentModel.scene) {
      this.scene.remove(this.currentModel.scene);
    } else if (this.currentModel.root) {
      this.scene.remove(this.currentModel.root);
    }

    this.currentModel = null;
    this.isVRM = false;
  }

  /**
   * Ajusta automáticamente el encuadre de la cámara para centrar el torso,
   * rostro y brazos del avatar en el viewport.
   */
  autoFrameCamera() {
    if (!this.camera) return;

    let targetY = 1.20;
    const distance = 1.95;

    if (this.isVRM && this.currentModel && this.currentModel.humanoid) {
      const head = this.currentModel.humanoid.getNormalizedBoneNode('head');
      if (head) {
        const headPos = new THREE.Vector3();
        head.getWorldPosition(headPos);
        targetY = Math.max(headPos.y - 0.28, 0.90);
      }
    }

    if (this.controls) {
      this.controls.target.set(0, targetY, 0);
      this.camera.position.set(0, targetY + 0.08, distance);
      this.controls.update();
    } else {
      this.camera.position.set(0, targetY + 0.08, distance);
      this.camera.lookAt(new THREE.Vector3(0, targetY, 0));
    }
  }

  /**
   * Girar la cámara alrededor del avatar (Rotación orbital).
   * @param {number} deltaAzimuthDeg - Grados horizontales (+ gira a la derecha, - a la izquierda)
   * @param {number} [deltaPolarDeg=0] - Grados verticales (+ inclina arriba, - inclina abajo)
   */
  rotateCamera(deltaAzimuthDeg, deltaPolarDeg = 0) {
    if (!this.camera || !this.controls) return;
    const deltaAzimuthRad = THREE.MathUtils.degToRad(deltaAzimuthDeg);
    const deltaPolarRad = THREE.MathUtils.degToRad(deltaPolarDeg);

    const offset = new THREE.Vector3().subVectors(this.camera.position, this.controls.target);
    const spherical = new THREE.Spherical().setFromVector3(offset);
    spherical.theta += deltaAzimuthRad;
    spherical.phi = THREE.MathUtils.clamp(
      spherical.phi + deltaPolarRad,
      this.controls.minPolarAngle,
      this.controls.maxPolarAngle
    );
    offset.setFromSpherical(spherical);
    this.camera.position.copy(this.controls.target).add(offset);
    this.controls.update();
  }

  /**
   * Mover / trasladar (Pan) la cámara y su objetivo en el plano de visión.
   * @param {number} deltaX - Desplazamiento horizontal (+ derecha, - izquierda)
   * @param {number} deltaY - Desplazamiento vertical (+ arriba, - abajo)
   */
  panCamera(deltaX, deltaY) {
    if (!this.camera || !this.controls) return;
    const dist = this.camera.position.distanceTo(this.controls.target);
    const factor = Math.max(dist, 0.5) * 0.04;

    const right = new THREE.Vector3();
    const up = new THREE.Vector3();
    this.camera.matrixWorld.extractBasis(right, up, new THREE.Vector3());

    const offset = new THREE.Vector3()
      .addScaledVector(right, deltaX * factor)
      .addScaledVector(up, deltaY * factor);

    this.camera.position.add(offset);
    this.controls.target.add(offset);
    this.controls.update();
  }

  /**
   * Deslizar / acercar / alejar (Dolly / Zoom) la cámara a lo largo del eje de visión.
   * @param {number} deltaZoom - Cantidad de deslizamiento (+ acercar, - alejar)
   */
  dollyCamera(deltaZoom) {
    if (!this.camera || !this.controls) return;
    const offset = new THREE.Vector3().subVectors(this.camera.position, this.controls.target);
    const currentDist = offset.length();
    const newDist = THREE.MathUtils.clamp(
      currentDist - deltaZoom,
      this.controls.minDistance,
      this.controls.maxDistance
    );
    offset.setLength(newDist);
    this.camera.position.copy(this.controls.target).add(offset);
    this.controls.update();
  }

  /**
   * Restaura la cámara a la posición y objetivo por defecto de señas.
   */
  resetCamera() {
    if (!this.camera || !this.controls) return;
    this.controls.target.copy(this.options.cameraTarget);
    this.camera.position.copy(this.options.cameraPos);
    this.camera.lookAt(this.options.cameraTarget);
    this.controls.update();
  }

  /**
   * Aplica un encuadre predeterminado focalizado.
   * @param {'face'|'medium'|'full'|'hands'} preset
   */
  setCameraPreset(preset) {
    if (!this.camera || !this.controls) return;
    if (preset === 'face') {
      this.controls.target.set(0, 1.38, 0);
      this.camera.position.set(0, 1.42, 0.95);
    } else if (preset === 'medium') {
      this.controls.target.set(0, 1.20, 0);
      this.camera.position.set(0, 1.28, 1.55);
    } else if (preset === 'full') {
      this.controls.target.set(0, 1.05, 0);
      this.camera.position.set(0, 1.15, 2.45);
    } else if (preset === 'hands') {
      // Enfoque en la sien y espacio torácico para señas manuales y faciales
      this.controls.target.set(-0.10, 1.38, 0.05);
      this.camera.position.set(-0.12, 1.42, 1.15);
    } else {
      this.resetCamera();
    }
    this.controls.update();
  }

  /**
   * Inicia el ciclo continuo de animación y render.
   */
  start() {
    if (this.isRunning) return;
    this.isRunning = true;
    this.clock.start();

    const loop = () => {
      if (!this.isRunning) return;
      this.animFrameId = requestAnimationFrame(loop);

      // Si la pestaña no está visible, reducimos la carga de renderizado
      if (document.hidden) {
        return;
      }

      const delta = Math.min(this.clock.getDelta(), 0.1);

      // 0. Amortiguación y actualización continua de cámara (OrbitControls)
      if (this.controls) {
        this.controls.update();
      }

      // 1. Actualizar modelo VRM si corresponde
      if (this.isVRM && this.currentModel && typeof this.currentModel.update === 'function') {
        this.currentModel.update(delta);
      }

      // 2. Callback del reproductor de señas
      if (typeof this.onUpdateCallback === 'function') {
        try {
          this.onUpdateCallback(delta);
        } catch (updateErr) {
          console.error('[AvatarEngine] Error en onUpdateCallback:', updateErr);
        }
      }

      // 3. Renderizar escena
      if (this.renderer && this.scene && this.camera) {
        this.renderer.render(this.scene, this.camera);
      }
    };

    this.animFrameId = requestAnimationFrame(loop);
  }

  /**
   * Detiene el ciclo de renderizado.
   */
  stop() {
    this.isRunning = false;
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
  }

  /**
   * Registra el callback de actualización en cada fotograma.
   * @param {Function} cb - (delta: number) => void
   */
  setUpdateCallback(cb) {
    this.onUpdateCallback = cb;
  }

  /**
   * Libera todos los recursos WebGL, listeners y texturas.
   */
  dispose() {
    this.stop();

    if (this.controls) {
      this.controls.dispose();
      this.controls = null;
    }

    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }
    if (this.onResizeBound) {
      window.removeEventListener('resize', this.onResizeBound);
    }
    if (this.canvas) {
      this.canvas.removeEventListener('webglcontextlost', this.onContextLostBound);
      this.canvas.removeEventListener('webglcontextrestored', this.onContextRestoredBound);
    }

    this.removeModel();

    if (this.renderer) {
      this.renderer.dispose();
      this.renderer = null;
    }

    this.scene = null;
    this.camera = null;
    console.info('[AvatarEngine] Recursos del motor 3D liberados.');
  }
}
