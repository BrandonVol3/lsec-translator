"""
Prueba E2E Automatizada de Conexión LSEC Studio ⇄ LSEC Avatar 3D.

Verifica:
1. Carga de /studio con el avatar 3D montado en el PiP minimalista sobre el video.
2. Fondo sólido contrastante (#20242b) y ausencia de marcas de agua o etiquetas de ilustración obsoletas.
3. Encuadre estricto de torso a cabeza con manos ocultas en reposo (pip_bust).
4. Acoplamiento dinámico de canvas entre PiP y panel lateral de inspección "Avatar 3D".
5. Reproducción reactiva de glosas (v2.6 oficial) y manejo de dactilología pendiente.
6. Integración del renderizado 3D para exportación de video (captureFrame).
"""

import os
import json
import time
import pytest
from playwright.sync_api import sync_playwright, expect

STUDIO_URL = "http://127.0.0.1:8000/studio"


def test_studio_avatar_pip_and_bridge_integration():
    """Valida la conexión completa del avatar 3D en /studio."""
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
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        page.goto(STUDIO_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#app-container", timeout=15000)
        page.evaluate("() => window.switchWizardStep && window.switchWizardStep('revisar')")

        # 1. Verificar existencia del host de PiP y ausencia de marcas obsoletas
        pip_card = page.locator("#gloss-overlay-container")
        expect(pip_card).to_be_attached()

        # No debe haber texto de ilustración ni marca de agua
        pip_text = pip_card.inner_text().lower()
        assert "ilustración" not in pip_text
        assert "espacio para avatar" not in pip_text

        # 2. Esperar inicialización del puente 3D y acoplamiento del canvas en PiP
        page.wait_for_function("() => window.studioAvatarBridge && window.studioAvatarBridge.isReady", timeout=25000)
        page.evaluate("() => window.switchWizardStep && window.switchWizardStep('revisar')")

        bridge_status = page.evaluate("""() => {
            const b = window.studioAvatarBridge;
            const c = b?.controller;
            const canvas = c?.engine?.canvas;
            const inPip = canvas && canvas.parentElement?.id === 'avatar-pip-canvas-host';
            const bg = c?.engine?.scene?.background?.getHexString();
            return {
                isReady: b.isReady,
                currentLocation: b.currentLocation,
                inPip,
                hasCanvas: !!canvas,
                bgHex: bg ? '#' + bg : null
            };
        }""")

        assert bridge_status["isReady"] is True
        assert bridge_status["currentLocation"] == "pip"
        assert bridge_status["inPip"] is True
        assert bridge_status["hasCanvas"] is True
        # Fondo contrastante #20242b
        assert bridge_status["bgHex"] == "#20242b"

        # 3. Validar encuadre de busto y manos ocultas en reposo (preset pip_bust)
        cam_info = page.evaluate("""() => {
            const ctrl = window.avatarController;
            const cam = ctrl.engine.camera;
            const target = ctrl.engine.controls.target;
            return {
                targetY: target.y,
                camPosY: cam.position.y,
                camPosZ: cam.position.z
            };
        }""")
        assert cam_info["targetY"] >= 1.25, f"Target de cámara no focalizado en torso superior/cuello: {cam_info}"

        # 4. Probar conmutación programática de acoplamiento sidebar <-> PiP
        side_status = page.evaluate("""() => {
            const b = window.studioAvatarBridge;
            b.dockToSidebar();
            const canvas = b?.controller?.engine?.canvas;
            const inSidebar = canvas && canvas.parentElement?.id === 'avatar-viewport-wrap';
            return {
                currentLocation: b.currentLocation,
                inSidebar
            };
        }""")
        assert side_status["currentLocation"] == "sidebar"
        assert side_status["inSidebar"] is True

        pip_return = page.evaluate("""() => {
            const b = window.studioAvatarBridge;
            b.dockToPip();
            const canvas = b?.controller?.engine?.canvas;
            return {
                currentLocation: b.currentLocation,
                inPip: canvas && canvas.parentElement?.id === 'avatar-pip-canvas-host'
            };
        }""")
        assert pip_return["currentLocation"] == "pip"
        assert pip_return["inPip"] is True

        # 5. Probar reproducción de una seña mediante playGloss
        play_res = page.evaluate("""async () => {
            const ctrl = window.avatarController;
            const ok = await ctrl.playGloss('LUNES');
            return {
                ok,
                state: ctrl.player?.playbackState,
                gloss: ctrl.activeGlossHud?.textContent
            };
        }""")
        assert play_res["ok"] is True
        assert "LUNES" in play_res["gloss"]

        # 6. Probar manejo de glosa dactilológica (pendiente)
        fs_res = page.evaluate("""async () => {
            const ctrl = window.avatarController;
            const ok = await ctrl.playGloss('G-U-A-Y-A-Q-U-I-L', { isFingerspelling: true });
            return {
                ok,
                gloss: ctrl.activeGlossHud?.textContent
            };
        }""")
        assert fs_res["ok"] is True
        assert "G-U-A-Y-A-Q-U-I-L" in fs_res["gloss"]

        # 7. Validar soporte de captura para exportación de video (captureFrame)
        capture_info = page.evaluate("""() => {
            const canvas = window.studioAvatarBridge.captureFrame();
            return {
                hasCanvas: !!canvas,
                width: canvas?.width,
                height: canvas?.height
            };
        }""")
        assert capture_info["hasCanvas"] is True
        assert capture_info["width"] > 0
        assert capture_info["height"] > 0

        # Capturar screenshot del PiP para comprobación visual
        os.makedirs("scratch", exist_ok=True)
        pip_card.screenshot(path="scratch/pip_avatar_3d.png")

        # Verificar que no hay errores críticos de JavaScript
        crit = [e for e in console_errors if "favicon" not in e.lower() and "404" not in e.lower()]
        assert len(crit) == 0, f"Errores de consola: {crit}"

        browser.close()


def test_studio_fluid_sequence_compiler_and_pip_tail_extension():
    """
    Valida en navegador real:
    1. Compilación de secuencia fluida sobre DEMO_PROJECT_DATA (velocidad <= 1.6x, lag <= 1.0s, 0 caídas intra-oración).
    2. Preservación de badges DACTILOLOGÍA (PENDIENTE) (T-U-L-C-Á-N, C-A-Y-A-M-B-E, U-P-E-C) mientras el avatar mantiene su postura (phase != 'rest').
    3. Limpieza inmediata del badge a 'LSEC' al saltar (seek) a un tramo de reposo.
    4. Invalidación de clipMap al cambiar de versión ('2.7' -> '2.6' -> '2.7').
    5. Activación de la cola extendida del PiP (_extendedTailActive) al finalizar el video en 48.85s.
    """
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
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.goto(STUDIO_URL, wait_until="domcontentloaded")
        page.wait_for_function(
            "() => window.studioAvatarBridge && window.studioAvatarBridge.isReady && window.avatarController?.engine?.currentModel",
            timeout=30000
        )

        # Cargar DEMO_PROJECT_DATA y esperar a que preloadProjectSigns compile el plan
        plan_stats = page.evaluate("""async () => {
            if (!window.appState.state.project) {
                window.appState.resetToDefaultProject();
            }
            const b = window.studioAvatarBridge;
            await b.preloadProjectSigns(window.appState.state.project);
            const plan = b.compiler.compiled;
            return {
                clipCount: b.clipMap.size,
                clipMapVersion: b.clipMapVersion,
                videoDurationSec: plan.videoDurationSec,
                sequenceEndTime: plan.sequenceEndTime,
                extendedTailSec: plan.extendedTailSec,
                stats: plan.stats
            };
        }""")

        assert plan_stats["clipCount"] >= 55, f"Se esperaban >= 55 clips cargados, obtenidos: {plan_stats}"
        assert plan_stats["clipMapVersion"] == "2.7"
        assert plan_stats["stats"]["intraSentenceRestDrops"] == 0
        assert plan_stats["stats"]["maxSpeedUsed"] <= 1.6001
        assert plan_stats["stats"]["maxLagSec"] <= 1.0001
        assert plan_stats["sequenceEndTime"] > plan_stats["videoDurationSec"]

        # Verificar glosas de dactilología (T-U-L-C-Á-N, C-A-Y-A-M-B-E, U-P-E-C)
        fs_checks = page.evaluate("""() => {
            const results = [];
            const segs = window.studioAvatarBridge.compiler.compiled?.segments || [];
            for (const [fallbackT, expectedGloss] of [[15.35, 'T-U-L-C-Á-N'], [16.00, 'C-A-Y-A-M-B-E'], [27.20, 'U-P-E-C']]) {
                const matchSeg = segs.find(s => s.type === 'stroke' && s.activeEntry?.gloss === expectedGloss);
                const t = matchSeg ? Number(((matchSeg.startSec + matchSeg.endSec) * 0.5).toFixed(2)) : fallbackT;
                window.appState.setCurrentTime(t, 'seek');
                const hostText = document.getElementById('avatar-pip-gloss-host')?.innerText || '';
                const hudText = document.getElementById('avatar-active-gloss-hud')?.textContent || '';
                const sample = window.studioAvatarBridge.lastSampleResult;
                results.push({
                    t,
                    expectedGloss,
                    hostText,
                    hudText,
                    phase: sample?.phase,
                    activeGloss: sample?.activeGloss
                });
            }
            return results;
        }""")

        for item in fs_checks:
            assert item["expectedGloss"] in item["hostText"], f"Badge PiP omitió dactilología: {item}"
            assert "DACTILOLOGÍA" in item["hostText"], f"Falta etiqueta DACTILOLOGÍA en PiP: {item}"
            assert item["activeGloss"] == item["expectedGloss"], f"activeGloss incorrecto: {item}"
            assert item["phase"] != "rest", f"El avatar cayó a reposo durante dactilología intra-oración: {item}"

        # Verificar transición a estado idle ('LSEC') y fase 'rest' al alcanzar el final de la cola extendida
        seek_idle = page.evaluate("""() => {
            const b = window.studioAvatarBridge;
            window.appState.setCurrentTime(5.0, 'seek');
            const activeText = document.getElementById('avatar-pip-gloss-host')?.innerText || '';
            const afterEndSec = (b.compiler.compiled?.sequenceEndTime || 49.5) + 0.25;
            b.applyFluidSampleAtTime(afterEndSec);
            window.glossOverlay.render(afterEndSec);
            const idleText = document.getElementById('avatar-pip-gloss-host')?.innerText || '';
            return { activeText, idleText, phase: b.lastSampleResult?.phase };
        }""")
        assert "LSEC" in seek_idle["idleText"] and "SEÑA" not in seek_idle["idleText"], f"Badge no volvió a idle tras finalizar secuencia: {seek_idle}"
        assert seek_idle["phase"] == "rest"

        # Verificar invalidación de caché al cambiar versión ('2.7' -> '2.6' -> '2.7')
        ver_switch = page.evaluate("""async () => {
            const b = window.studioAvatarBridge;
            b.clearClipCache('2.6');
            const sizeAfterClear = b.clipMap.size;
            const verAfterClear = b.clipMapVersion;
            await window.avatarController.setAnimationVersion('2.7');
            return {
                sizeAfterClear,
                verAfterClear,
                restoredVer: b.clipMapVersion,
                restoredCount: b.clipMap.size
            };
        }""")
        assert ver_switch["sizeAfterClear"] == 0
        assert ver_switch["verAfterClear"] == "2.6"
        assert ver_switch["restoredVer"] == "2.7"
        assert ver_switch["restoredCount"] >= 55

        # Verificar activación de la extensión del PiP al finalizar el video en 48.85s
        tail_check = page.evaluate("""() => {
            const b = window.studioAvatarBridge;
            const dur = window.appState.state.project.media_info.duration_seconds;
            window.appState.setIsPlaying(true);
            window.appState.setCurrentTime(dur, 'end');
            window.appState.setIsPlaying(false);
            const activeAtEnd = b._extendedTailActive;
            const startTailTime = b._extendedTailTime;
            b.onEngineFrame(0.08);
            const afterStepTime = b._extendedTailTime;
            // Avanzar hasta completar la cola extendida
            for (let i = 0; i < 15; i++) {
                b.onEngineFrame(0.08);
            }
            return {
                activeAtEnd,
                startTailTime,
                afterStepTime,
                activeAfterFinish: b._extendedTailActive
            };
        }""")
        assert tail_check["activeAtEnd"] is True, f"No se activó _extendedTailActive al llegar al final del video: {tail_check}"
        assert tail_check["afterStepTime"] > tail_check["startTailTime"]
        assert tail_check["activeAfterFinish"] is False

        browser.close()

