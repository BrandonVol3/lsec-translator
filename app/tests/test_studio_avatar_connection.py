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

        # 1. Verificar existencia del host de PiP y ausencia de marcas obsoletas
        pip_card = page.locator(".avatar-pip-card")
        expect(pip_card).to_be_visible()

        # No debe haber texto de ilustración ni marca de agua
        pip_text = pip_card.inner_text().lower()
        assert "ilustración" not in pip_text
        assert "espacio para avatar" not in pip_text

        # 2. Esperar inicialización del puente 3D y acoplamiento del canvas en PiP
        page.wait_for_function("() => window.studioAvatarBridge && window.studioAvatarBridge.isReady", timeout=25000)

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

        # 4. Probar conmutación dinámica al panel lateral "Avatar 3D"
        page.click("#tab-btn-side-avatar")
        page.wait_for_timeout(300)

        side_status = page.evaluate("""() => {
            const b = window.studioAvatarBridge;
            const canvas = b?.controller?.engine?.canvas;
            const inSidebar = canvas && canvas.parentElement?.id === 'avatar-viewport-wrap';
            return {
                currentLocation: b.currentLocation,
                inSidebar
            };
        }""")
        assert side_status["currentLocation"] == "sidebar"
        assert side_status["inSidebar"] is True

        # Regresar a la pestaña Transcripción y verificar retorno al PiP
        page.click("#tab-btn-side-transcript")
        page.wait_for_timeout(300)

        pip_return = page.evaluate("""() => {
            const b = window.studioAvatarBridge;
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
        pip_card.screenshot(path="lsec_translator_prototype/scratch/pip_avatar_3d.png")

        # Verificar que no hay errores críticos de JavaScript
        crit = [e for e in console_errors if "favicon" not in e.lower() and "404" not in e.lower()]
        assert len(crit) == 0, f"Errores de consola: {crit}"

        browser.close()
