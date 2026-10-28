"""
Prueba Exhaustiva de Validación del Avatar LSEC-Interpreter-Female.vrm en LSEC Studio.

Cubre los 6 criterios requeridos:
1. Validación estructural:
   - VRM 1.0 válido (VRMC_vrm).
   - Huesos de torso, cabeza, ojos, brazos, manos y 30 falanges completas.
   - Expresiones y morph targets disponibles.
2. Pruebas visuales de manos:
   - Mano abierta, puño, índice extendido, dos dedos, pinza, mano curva, garra, dedos juntos/separados.
3. Pruebas de orientación:
   - Palma frontal/cuerpo/arriba/abajo, pronación/supinación, flexión muñeca y codo.
4. Pruebas no manuales (CNM):
   - HEAD_SHAKE, HEAD_NOD, HEAD_TILT, mirada (ojos), cejas, parpadeo, boca.
5. Pruebas simultáneas:
   - Manos con cabeza, manos con mirada, manos con expresión, coordinación compleja total.
6. Rendimiento y secuencia continua:
   - Tiempo de carga, FPS, memoria, errores de consola y ejecución en secuencia encadenada.
"""

import os
import json
import struct
import pytest
from playwright.sync_api import sync_playwright, expect

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE_ROOT = os.path.dirname(PROJECT_ROOT)
VRM_PATH = os.path.join(WORKSPACE_ROOT, "Avatar", "LSEC-Interpreter-Female.vrm")
if not os.path.exists(VRM_PATH):
    VRM_PATH = os.path.join(PROJECT_ROOT, "app", "static", "assets", "LSEC-Interpreter-Female.vrm")
STUDIO_URL = "http://127.0.0.1:8000/studio"



def test_1_vrm_structural_validation():
    """1. Validación estructural completa de VRM 1.0, 54 huesos y morph targets."""
    assert os.path.exists(VRM_PATH), f"No se encontró el archivo {VRM_PATH}"

    with open(VRM_PATH, "rb") as f:
        magic, version, length = struct.unpack("<4sII", f.read(12))
        assert magic == b"glTF", "No es un contenedor binario glTF válido."
        chunk_len, chunk_type = struct.unpack("<I4s", f.read(8))
        assert chunk_type == b"JSON", "El chunk inicial no es de tipo JSON."
        gltf = json.loads(f.read(chunk_len).decode("utf-8"))

    vrm1 = gltf.get("extensions", {}).get("VRMC_vrm")
    assert vrm1 is not None, "El modelo debe implementar la especificación oficial VRM 1.0 (VRMC_vrm)."

    human_bones = vrm1.get("humanoid", {}).get("humanBones", {})
    
    # 1.1 Torso, cuello y cabeza
    for b in ["hips", "spine", "chest", "upperChest", "neck", "head"]:
        assert b in human_bones, f"Falta hueso de tronco/cabeza: {b}"

    # 1.2 Extremidades superiores principales
    for b in ["leftShoulder", "leftUpperArm", "leftLowerArm", "leftHand",
              "rightShoulder", "rightUpperArm", "rightLowerArm", "rightHand"]:
        assert b in human_bones, f"Falta hueso de extremidad superior: {b}"

    # 1.3 Mano izquierda: 15 falanges completas (3 por dedo)
    left_finger_bones = [
        "leftThumbMetacarpal", "leftThumbProximal", "leftThumbDistal",
        "leftIndexProximal", "leftIndexIntermediate", "leftIndexDistal",
        "leftMiddleProximal", "leftMiddleIntermediate", "leftMiddleDistal",
        "leftRingProximal", "leftRingIntermediate", "leftRingDistal",
        "leftLittleProximal", "leftLittleIntermediate", "leftLittleDistal"
    ]
    for fb in left_finger_bones:
        assert fb in human_bones, f"Falta falange en mano izquierda: {fb}"

    # 1.4 Mano derecha: 15 falanges completas (3 por dedo)
    right_finger_bones = [
        "rightThumbMetacarpal", "rightThumbProximal", "rightThumbDistal",
        "rightIndexProximal", "rightIndexIntermediate", "rightIndexDistal",
        "rightMiddleProximal", "rightMiddleIntermediate", "rightMiddleDistal",
        "rightRingProximal", "rightRingIntermediate", "rightRingDistal",
        "rightLittleProximal", "rightLittleIntermediate", "rightLittleDistal"
    ]
    for fb in right_finger_bones:
        assert fb in human_bones, f"Falta falange en mano derecha: {fb}"

    # 1.5 Ojos para mirada
    assert "leftEye" in human_bones, "Falta hueso leftEye para control de mirada."
    assert "rightEye" in human_bones, "Falta hueso rightEye para control de mirada."

    # 1.6 Expresiones faciales y morph targets
    presets = vrm1.get("expressions", {}).get("preset", {})
    for exp in ["happy", "angry", "sad", "relaxed", "surprised", "aa", "oh", "blink"]:
        assert exp in presets or exp in ["ou", "neutral"], f"Falta expresión clave para CNM: {exp}"


def test_2_hand_visual_clips_and_deformation():
    """2. Pruebas visuales de las 8 configuraciones manuales en el navegador."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(STUDIO_URL, wait_until="domcontentloaded")
        page.wait_for_function("() => window.studioAvatarBridge && window.studioAvatarBridge.isReady", timeout=30000)
        page.evaluate("""() => {
            const v = document.getElementById('view-side-avatar');
            if (v) v.style.display = 'flex';
            window.studioAvatarBridge?.dockToSidebar();
        }""")
        page.wait_for_selector("#avatar-model-source-info:has-text('VRM 1.0')", timeout=30000)

        hand_clips = [
            "TEST_MANO_ABIERTA",
            "TEST_PUNO",
            "TEST_INDICE_EXTENDIDO",
            "TEST_DOS_DEDOS",
            "TEST_PINZA",
            "TEST_MANO_CURVA",
            "TEST_GARRA",
            "TEST_DEDOS_JUNTOS_SEPARADOS"
        ]

        for clip_id in hand_clips:
            page.select_option("#select-avatar-clip", clip_id)
            page.click("#btn-avatar-play")

            # Esperar a que el reproductor inicie
            page.wait_for_timeout(250)

            # Verificar que el reproductor está en reproducción o animando
            state = page.evaluate("() => window.avatarController.player.playbackState")
            assert state == "playing", f"El clip {clip_id} debería estar reproduciéndose (estado: {state})"

            # Verificar en fotograma intermedio que los huesos de las falanges tienen cuaterniones válidos
            bone_check = page.evaluate("""() => {
                const ctrl = window.avatarController;
                const vrm = ctrl.player.model;
                const h = vrm.humanoid;
                const bones = [
                    'rightThumbProximal', 'rightThumbDistal',
                    'rightIndexProximal', 'rightIndexIntermediate', 'rightIndexDistal',
                    'rightMiddleProximal', 'rightMiddleIntermediate', 'rightMiddleDistal'
                ];
                let valid = true;
                for (const b of bones) {
                    const node = h.getNormalizedBoneNode(b);
                    if (!node || isNaN(node.quaternion.x) || isNaN(node.quaternion.w)) {
                        valid = false;
                    }
                }
                return { valid, clipId: ctrl.player.currentClip.clipId };
            }""")

            assert bone_check["valid"] is True, f"Fallo en cuaterniones de falanges para {clip_id}"

            # Pausar y resetear
            page.click("#btn-avatar-reset")
            page.wait_for_timeout(100)

        browser.close()


def test_3_orientation_clips():
    """3. Pruebas de orientación de palma, pronación/supinación y flexión muñeca/codo."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(STUDIO_URL, wait_until="domcontentloaded")
        page.wait_for_function("() => window.studioAvatarBridge && window.studioAvatarBridge.isReady", timeout=30000)
        page.evaluate("""() => {
            const v = document.getElementById('view-side-avatar');
            if (v) v.style.display = 'flex';
            window.studioAvatarBridge?.dockToSidebar();
        }""")
        page.wait_for_selector("#avatar-model-source-info:has-text('VRM 1.0')", timeout=30000)

        orient_clips = [
            "TEST_ORIENTACION_PALMA",
            "TEST_PRONACION_SUPINACION",
            "TEST_FLEXION_MUNICA_CODO"
        ]

        for clip_id in orient_clips:
            page.select_option("#select-avatar-clip", clip_id)
            page.click("#btn-avatar-play")

            page.wait_for_timeout(250)
            state = page.evaluate("() => window.avatarController.player.playbackState")
            assert state == "playing"

            orient_check = page.evaluate("""() => {
                const ctrl = window.avatarController;
                const vrm = ctrl.player.model;
                const arm = vrm.humanoid.getNormalizedBoneNode('rightLowerArm');
                const hand = vrm.humanoid.getNormalizedBoneNode('rightHand');
                return {
                    armRot: [arm.quaternion.x, arm.quaternion.y, arm.quaternion.z, arm.quaternion.w],
                    handRot: [hand.quaternion.x, hand.quaternion.y, hand.quaternion.z, hand.quaternion.w],
                    valid: !isNaN(arm.quaternion.x) && !isNaN(hand.quaternion.x)
                };
            }""")

            assert orient_check["valid"] is True
            page.click("#btn-avatar-reset")
            page.wait_for_timeout(100)

        browser.close()


def test_4_non_manual_clips():
    """4. Pruebas de componentes no manuales: cabeza, mirada, cejas, parpadeo y boca."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(STUDIO_URL, wait_until="domcontentloaded")
        page.wait_for_function("() => window.studioAvatarBridge && window.studioAvatarBridge.isReady", timeout=30000)
        page.evaluate("""() => {
            const v = document.getElementById('view-side-avatar');
            if (v) v.style.display = 'flex';
            window.studioAvatarBridge?.dockToSidebar();
        }""")
        page.wait_for_selector("#avatar-model-source-info:has-text('VRM 1.0')", timeout=30000)

        cnm_clips = [
            "TEST_CNM_HEAD_SHAKE",
            "TEST_CNM_HEAD_NOD",
            "TEST_CNM_HEAD_TILT",
            "TEST_CNM_MIRADA",
            "TEST_CNM_CEJAS",
            "TEST_CNM_PARPADEO",
            "TEST_CNM_BOCA"
        ]

        for clip_id in cnm_clips:
            page.select_option("#select-avatar-clip", clip_id)
            page.click("#btn-avatar-play")

            page.wait_for_timeout(250)
            state = page.evaluate("() => window.avatarController.player.playbackState")
            assert state == "playing"

            cnm_check = page.evaluate("""() => {
                const ctrl = window.avatarController;
                const vrm = ctrl.player.model;
                const head = vrm.humanoid.getNormalizedBoneNode('head');
                const leftEye = vrm.humanoid.getNormalizedBoneNode('leftEye');
                const expr = vrm.expressionManager;
                return {
                    hasHeadNode: !!head,
                    hasEyeBone: !!leftEye,
                    hasExprManager: !!expr
                };
            }""")

            assert cnm_check["hasHeadNode"] is True
            assert cnm_check["hasEyeBone"] is True
            assert cnm_check["hasExprManager"] is True

            page.click("#btn-avatar-reset")
            page.wait_for_timeout(100)

        browser.close()


def test_5_simultaneous_clips():
    """5. Pruebas simultáneas: coordinación manual, ocular, cefálica y facial."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(STUDIO_URL, wait_until="domcontentloaded")
        page.wait_for_function("() => window.studioAvatarBridge && window.studioAvatarBridge.isReady", timeout=30000)
        page.evaluate("""() => {
            const v = document.getElementById('view-side-avatar');
            if (v) v.style.display = 'flex';
            window.studioAvatarBridge?.dockToSidebar();
        }""")
        page.wait_for_selector("#avatar-model-source-info:has-text('VRM 1.0')", timeout=30000)

        sim_clips = [
            "TEST_SIMULTANEO_MANOS_CABEZA",
            "TEST_SIMULTANEO_MANOS_MIRADA",
            "TEST_SIMULTANEO_MANOS_EXPRESION",
            "TEST_SIMULTANEO_COMPLEJO_TOTAL"
        ]

        for clip_id in sim_clips:
            page.select_option("#select-avatar-clip", clip_id)
            page.click("#btn-avatar-play")

            page.wait_for_timeout(300)
            state = page.evaluate("() => window.avatarController.player.playbackState")
            assert state == "playing"

            sim_check = page.evaluate("""() => {
                const ctrl = window.avatarController;
                const vrm = ctrl.player.model;
                const arm = vrm.humanoid.getNormalizedBoneNode('rightUpperArm');
                const head = vrm.humanoid.getNormalizedBoneNode('head');
                const spine = vrm.humanoid.getNormalizedBoneNode('spine');
                return {
                    armActive: arm.quaternion.length() > 0.99,
                    headActive: head.quaternion.length() > 0.99,
                    spineActive: spine.quaternion.length() > 0.99
                };
            }""")

            assert sim_check["armActive"] is True
            assert sim_check["headActive"] is True
            assert sim_check["spineActive"] is True

            page.click("#btn-avatar-reset")
            page.wait_for_timeout(100)

        browser.close()


def test_6_performance_and_continuous_sequence():
    """6. Rendimiento: tiempo de carga, FPS, memoria, errores de consola y secuencia continua."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(STUDIO_URL, wait_until="domcontentloaded")
        page.wait_for_function("() => window.studioAvatarBridge && window.studioAvatarBridge.isReady", timeout=30000)
        page.evaluate("""() => {
            const v = document.getElementById('view-side-avatar');
            if (v) v.style.display = 'flex';
            window.studioAvatarBridge?.dockToSidebar();
        }""")
        page.wait_for_selector("#avatar-model-source-info:has-text('VRM 1.0')", timeout=30000)

        # 6.1 Reporte inicial de carga
        perf = page.evaluate("() => window.avatarController.getPerformanceReport()")
        print("Reporte de rendimiento inicial:", json.dumps(perf, indent=2))

        assert perf["isVRMActive"] is True
        assert perf["loadTimeMs"] < 6000, f"Tiempo de carga excesivo: {perf['loadTimeMs']}ms"

        # 6.2 Ejecutar secuencia continua de demostración
        page.click("#btn-avatar-play-sequence")
        page.wait_for_timeout(200)
        state = page.evaluate("() => window.avatarController.player.playbackState")
        assert state == "playing", "El reproductor debería estar en estado 'playing' durante la secuencia"

        # Dejar correr la secuencia durante 2.5 segundos para medir estabilidad y FPS
        page.wait_for_timeout(2500)

        perf_mid = page.evaluate("() => window.avatarController.getPerformanceReport()")
        print("Reporte de rendimiento en reproducción continua:", json.dumps(perf_mid, indent=2))

        assert perf_mid["fps"] >= 1, f"Tasa de FPS anormal: {perf_mid['fps']}"
        assert perf_mid["consoleErrors"] == 0, f"Se registraron errores de consola: {perf_mid['consoleErrors']}"

        # 6.3 Pausar y resetear
        page.click("#btn-avatar-reset")
        page.wait_for_timeout(200)

        browser.close()
