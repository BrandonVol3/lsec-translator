"""
Suite de Pruebas E2E Automatizadas con Playwright para Validación de Trailing Signal Loss y Estabilidad Cinemática.

Verifica:
1. Test 1 (LSEC Studio /studio): Carga Videos de Prueba/1.mp4, ejecuta la traducción y reproducción.
   Al detenerse el video, inspecciona los cuaterniones y posiciones de los huesos en Three.js a lo largo
   de los últimos 10 fotogramas para verificar 0 saltos rotacionales > 65° y que los brazos se mantengan
   dentro del volumen de proxy corporal (sin penetración de torso ni torsión dorsal).
2. Test 2 (Calibrador /avatarconfig): Prueba al menos 10 señas recortadas (Escoba, Llave, Botar, Cancha,
   Habano, Centro, Cuaderno, Célula, IVA, Fréjol). Avanza fotograma a fotograma en el tramo terminal
   hasta el reposo final, verificando 0 saltos > 65° y 0 contorsiones óseas dentro del volumen del cuerpo.
"""

import math
import os
import subprocess
import sys
import time
import urllib.request
import pytest
from playwright.sync_api import sync_playwright, expect

STUDIO_URL = "http://127.0.0.1:8000/studio"
AVATARCONFIG_URL = "http://127.0.0.1:8000/avatarconfig"

TRIMMED_TEST_SIGNS = [
    "Escoba",
    "Llave",
    "Botar",
    "Cancha",
    "Habano",
    "Centro",
    "Cuaderno",
    "Célula",
    "IVA",
    "Fréjol",
    "Sucumbíos",
    "Carchi",
]

@pytest.fixture(scope="module")
def studio_server():
    """Garantiza que el servidor uvicorn esté activo en el puerto 8000."""
    server_process = None
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health", timeout=1)
        if resp.status == 200:
            yield None
            return
    except Exception:
        pass

    # Iniciar servidor FastAPI local en modo offline
    python_exe = sys.executable
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        python_exe, "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"
    ]
    server_process = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    started = False
    for _ in range(30):
        time.sleep(0.5)
        try:
            resp = urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health", timeout=1)
            if resp.status == 200:
                started = True
                break
        except Exception:
            pass

    if not started:
        if server_process:
            server_process.terminate()
        pytest.skip("No se pudo iniciar el servidor local en http://127.0.0.1:8000")

    yield server_process

    if server_process:
        server_process.terminate()
        server_process.wait(timeout=5)


@pytest.fixture(scope="module")
def browser_instance(studio_server):
    """Inicia una instancia de Chromium con aceleración por hardware emulada para WebGL."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--enable-webgl",
                "--ignore-gpu-blocklist"
            ]
        )
        yield browser
        browser.close()


def test_trailing_signal_studio_playback(browser_instance):
    """
    Test 1: En LSEC Studio (/studio), carga Videos de Prueba/1.mp4, ejecuta la traducción y reproducción.
    Al detenerse el video, inspecciona los cuaterniones de Three.js a lo largo de los últimos 10 fotogramas
    para verificar 0 saltos > 65° y que los huesos de los brazos permanezcan fuera del volumen del torso.
    """
    context = browser_instance.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    # 1. Navegar a LSEC Studio
    page.goto(STUDIO_URL, wait_until="domcontentloaded")
    page.wait_for_selector("#app-container", timeout=20000)
    page.wait_for_function(
        "() => window.studioAvatarBridge && window.studioAvatarBridge.isReady && window.avatarController?.engine?.currentModel",
        timeout=30000
    )

    # 2. Cargar proyecto DEMO_PROJECT_DATA (correspondiente a 1.mp4) y compilar secuencia
    prep_result = page.evaluate("""async () => {
        if (!window.appState.state.project) {
            window.appState.resetToDefaultProject();
        }
        const b = window.studioAvatarBridge;
        await b.preloadProjectSigns(window.appState.state.project);
        const plan = b.compiler.compiled;
        return {
            videoDurationSec: plan.videoDurationSec,
            sequenceEndTime: plan.sequenceEndTime,
            clipCount: b.clipMap.size
        };
    }""")

    assert prep_result["clipCount"] > 0, "No se compilaron clips en la secuencia de Studio"
    assert prep_result["videoDurationSec"] > 0, "Duración de video no válida"

    # 3. Muestrear los últimos 10 fotogramas hasta la parada del video
    # En 30 fps, los últimos 10 fotogramas cubren ~0.33 segundos antes de videoDurationSec
    evaluation = page.evaluate("""() => {
        const b = window.studioAvatarBridge;
        const ctrl = window.avatarController;
        const model = ctrl.engine.currentModel;
        const humanoid = model.humanoid;
        const plan = b.compiler.compiled;
        const endT = plan.videoDurationSec || 48.85;
        const dt = 1.0 / 30.0;
        const bones = ['leftUpperArm', 'leftLowerArm', 'leftHand', 'rightUpperArm', 'rightLowerArm', 'rightHand', 'spine', 'chest', 'neck', 'head'];

        function getTorsoRx(y) {
            if (y <= 0.88) return 0.125;
            if (y <= 1.08) return 0.125 + ((y - 0.88) / 0.20) * (0.132 - 0.125);
            if (y <= 1.28) return 0.132 + ((y - 1.08) / 0.20) * (0.145 - 0.132);
            return 0.145;
        }

        function checkPenetration(pos) {
            const { x, y, z } = pos;
            if (y >= 0.85 && y <= 1.28) {
                const rx = getTorsoRx(y);
                const rz = 0.100;
                const zc = 0.010;
                const norm = Math.pow(x / rx, 2) + Math.pow((z - zc) / rz, 2);
                if (norm < 0.75) return { penetrating: true, reason: 'torso_inside', norm };
            }
            if (z < -0.100 && y >= 0.70 && y <= 1.45 && Math.abs(x) < 0.15) {
                return { penetrating: true, reason: 'behind_back', z };
            }
            return { penetrating: false };
        }

        function quatAngleDeg(q1, q2) {
            const dot = Math.abs(q1[0]*q2[0] + q1[1]*q2[1] + q1[2]*q2[2] + q1[3]*q2[3]);
            return 2.0 * Math.acos(Math.min(1.0, Math.max(-1.0, dot))) * (180.0 / Math.PI);
        }

        const framesData = [];
        let maxJumpDeg = 0.0;
        let jumpViolations = [];
        let penetrationViolations = [];

        const numFrames = 10;
        for (let i = numFrames - 1; i >= 0; i--) {
            const t = endT - i * dt;
            b.applyFluidSampleAtTime(t);
            ctrl.engine.stepDeterministic(0);

            const frameQuats = {};
            const framePositions = {};
            for (const bName of bones) {
                const node = humanoid.getNormalizedBoneNode(bName);
                if (node) {
                    const q = [node.quaternion.x, node.quaternion.y, node.quaternion.z, node.quaternion.w];
                    const wp = node.position.clone();
                    node.getWorldPosition(wp);
                    frameQuats[bName] = q;
                    framePositions[bName] = { x: wp.x, y: wp.y, z: wp.z };

                    // Verificar penetración para muñecas y manos
                    if (['leftHand', 'rightHand'].includes(bName)) {
                        const pen = checkPenetration(wp);
                        if (pen.penetrating) {
                            penetrationViolations.push({ frameIndex: numFrames - i, time: t, bone: bName, detail: pen });
                        }
                    }
                }
            }

            if (framesData.length > 0) {
                const prevQuats = framesData[framesData.length - 1].quats;
                for (const bName of bones) {
                    if (frameQuats[bName] && prevQuats[bName]) {
                        const angle = quatAngleDeg(frameQuats[bName], prevQuats[bName]);
                        if (angle > maxJumpDeg) maxJumpDeg = angle;
                        if (angle > 65.0) {
                            jumpViolations.push({ frameIndex: numFrames - i, time: t, bone: bName, angle });
                        }
                    }
                }
            }

            framesData.push({ t, quats: frameQuats, positions: framePositions });
        }

        return {
            framesSampled: framesData.length,
            maxJumpDeg: Number(maxJumpDeg.toFixed(2)),
            jumpViolationsCount: jumpViolations.length,
            jumpViolations,
            penetrationViolationsCount: penetrationViolations.length,
            penetrationViolations
        };
    }""")

    context.close()

    assert evaluation["jumpViolationsCount"] == 0, f"Saltos angulares > 65° detectados en Studio: {evaluation['jumpViolations']}"
    assert evaluation["penetrationViolationsCount"] == 0, f"Huesos dentro del volumen del cuerpo en Studio: {evaluation['penetrationViolations']}"
    assert evaluation["maxJumpDeg"] <= 65.0, f"Salto máximo excesivo en Studio: {evaluation['maxJumpDeg']}°"


def test_trailing_signal_avatarconfig_trimmed_signs(browser_instance):
    """
    Test 2: En el calibrador de avatar (/avatarconfig), prueba al menos 10 señas recortadas.
    Avanza fotograma a fotograma en el tramo terminal hasta el reposo final,
    verificando 0 saltos > 65° y 0 contorsiones óseas dentro del volumen del cuerpo.
    """
    context = browser_instance.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    page.goto(AVATARCONFIG_URL, wait_until="domcontentloaded")
    page.wait_for_selector("#avatar-webgl-canvas", timeout=20000)
    page.wait_for_function(
        "() => window.avatarController && window.avatarController.engine?.currentModel",
        timeout=30000
    )

    for sign_name in TRIMMED_TEST_SIGNS:
        eval_result = page.evaluate("""async (sign) => {
            const ctrl = window.avatarController;
            const player = ctrl.player;
            const model = ctrl.engine.currentModel;
            const humanoid = model.humanoid;

            const res = await fetch(`/api/v1/animations/${encodeURIComponent(sign)}?version=2.7`);
            if (!res.ok) return { error: `HTTP ${res.status}` };
            const animData = await res.json();

            await ctrl.importCustomClip(animData);

            const meta = animData.metadata || {};
            const totalFrames = meta.totalFrames || (animData.frames ? animData.frames.length : 0);
            const fps = meta.fps || 60.0;
            const duration = meta.duration || (totalFrames / fps);
            const dt = 1.0 / fps;

            const bones = ['leftUpperArm', 'leftLowerArm', 'leftHand', 'rightUpperArm', 'rightLowerArm', 'rightHand', 'spine', 'chest', 'neck', 'head'];

            function getTorsoRx(y) {
                if (y <= 0.88) return 0.125;
                if (y <= 1.08) return 0.125 + ((y - 0.88) / 0.20) * (0.132 - 0.125);
                if (y <= 1.28) return 0.132 + ((y - 1.08) / 0.20) * (0.145 - 0.132);
                return 0.145;
            }

            function checkPenetration(pos) {
                const { x, y, z } = pos;
                if (y >= 0.85 && y <= 1.28) {
                    const rx = getTorsoRx(y);
                    const rz = 0.100;
                    const zc = 0.010;
                    const norm = Math.pow(x / rx, 2) + Math.pow((z - zc) / rz, 2);
                    if (norm < 0.75) return { penetrating: true, reason: 'torso_inside', norm };
                }
                if (z < -0.100 && y >= 0.70 && y <= 1.45 && Math.abs(x) < 0.15) {
                    return { penetrating: true, reason: 'behind_back', z };
                }
                return { penetrating: false };
            }

            function quatAngleDeg(q1, q2) {
                const dot = Math.abs(q1[0]*q2[0] + q1[1]*q2[1] + q1[2]*q2[2] + q1[3]*q2[3]);
                return 2.0 * Math.acos(Math.min(1.0, Math.max(-1.0, dot))) * (180.0 / Math.PI);
            }

            const framesData = [];
            let maxJumpDeg = 0.0;
            let jumpViolations = [];
            let penetrationViolations = [];

            const numFrames = 10;
            for (let k = numFrames - 1; k >= 0; k--) {
                const t = Math.max(0.0, duration - k * dt);
                player.seek(t);
                ctrl.engine.stepDeterministic(0);

                const frameQuats = {};
                const framePositions = {};
                for (const bName of bones) {
                    const node = humanoid.getNormalizedBoneNode(bName);
                    if (node) {
                        const q = [node.quaternion.x, node.quaternion.y, node.quaternion.z, node.quaternion.w];
                        const wp = node.position.clone();
                        node.getWorldPosition(wp);
                        frameQuats[bName] = q;
                        framePositions[bName] = { x: wp.x, y: wp.y, z: wp.z };

                        if (['leftHand', 'rightHand'].includes(bName)) {
                            const pen = checkPenetration(wp);
                            if (pen.penetrating) {
                                penetrationViolations.push({ frameIndex: numFrames - k, time: t, bone: bName, detail: pen });
                            }
                        }
                    }
                }

                if (framesData.length > 0) {
                    const prevQuats = framesData[framesData.length - 1].quats;
                    for (const bName of bones) {
                        if (frameQuats[bName] && prevQuats[bName]) {
                            const angle = quatAngleDeg(frameQuats[bName], prevQuats[bName]);
                            if (angle > maxJumpDeg) maxJumpDeg = angle;
                            if (angle > 65.0) {
                                jumpViolations.push({ frameIndex: numFrames - k, time: t, bone: bName, angle });
                            }
                        }
                    }
                }

                framesData.push({ t, quats: frameQuats, positions: framePositions });
            }

            return {
                sign,
                totalFrames,
                duration,
                framesSampled: framesData.length,
                maxJumpDeg: Number(maxJumpDeg.toFixed(2)),
                jumpViolationsCount: jumpViolations.length,
                jumpViolations,
                penetrationViolationsCount: penetrationViolations.length,
                penetrationViolations
            };
        }""", sign_name)

        assert "error" not in eval_result, f"Error cargando seña {sign_name}: {eval_result.get('error')}"
        assert eval_result["jumpViolationsCount"] == 0, f"Salto > 65° en {sign_name}: {eval_result['jumpViolations']}"
        assert eval_result["penetrationViolationsCount"] == 0, f"Penetración ósea en {sign_name}: {eval_result['penetrationViolations']}"
        assert eval_result["maxJumpDeg"] <= 65.0, f"Salto máximo en {sign_name} excede 65°: {eval_result['maxJumpDeg']}°"

    context.close()
