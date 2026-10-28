"""
Suite de Pruebas Adversariales de Estrés de Navegador y Monkey Testing (Playwright / Chromium).
LSEC Studio — Auditoría General Pre-Producción (RF-01 a RF-08).

Objetivo:
Someter a estrés empírico, caos de interfaz (Monkey Testing) y fuzzing la interfaz de LSEC Studio:
1. Rage Clicking y Navegación Frenética (UI Chaos):
   - 45 clics rápidos sobre #workflow-stepper (Ventana 1 -> 2 -> 3 -> 1) con reproducción activa.
   - Verificación de reparenting sin pérdida de contexto WebGL (webglcontextlost) ni nodos DOM duplicados.
   - Doble y triple clic rápido en PROCESAR TRADUCCIÓN LSEC, Re-traducir fila, Play/Pause, Exportar SRT y Exportar MP4.
2. Estrés de Mutación de Estado y Ráfagas Undo/Redo (Ctrl+Z / Ctrl+Y):
   - 15 mutaciones consecutivas de fichas de glosas en Ventana 2 (agregar, editar, reordenar, eliminar) + ráfagas Ctrl+Z / Ctrl+Y.
3. Fuzzing de Entradas de Usuario (Inputs Extremos y Maliciosos):
   - Cadenas vacías "", solo espacios "     ", XSS (<script>alert('xss')</script><img src=x onerror=alert(1)>),
     emojis/símbolos (🔥🔥 ¿¿¿Hola??? ¡¡¡100% @#$%^&*()!!!), párrafos +1.500 caracteres y números (4500, 0992872993, 14:30).
   - Verificación de 0 ejecución XSS en Ventanas 1, 2 y 3 (#step3-live-sign-monitor), sin desborde CSS ni HTTP 500.
4. Estrés Multimedia, Redimensionamiento de Viewport, Persistencia F5 y Navegación Multiruta:
   - Mutación rápida del Personalizador de Subtítulos en vivo.
   - Redimensionamiento brusco (1920x1080 -> 1280x720 -> 768x1024 -> 1920x1080).
   - Recarga de página (F5) a mitad de edición verificando recuperación limpia del estado persistido.
   - Navegación cruzada /studio <-> /viewer <-> /avatarconfig.
"""

import sys
import os
import json
import time
import pytest
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"


class AdversarialStressHarness:
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url
        self.page_errors = []
        self.console_errors = []
        self.network_errors = []
        self.xss_triggered = False
        self.total_requests = 0
        self.report = {
            "rage_click_chaos": {},
            "gloss_mutation_undo_redo": {},
            "input_fuzzing_xss": {},
            "multimedia_resize_persistence": {},
            "cross_navigation_stress": {},
            "telemetry": {},
        }

    def setup_listeners(self, page):
        def handle_response(response):
            self.total_requests += 1
            status = response.status
            url = response.url
            if status >= 400 and "favicon.ico" not in url:
                err = f"HTTP {status} en {url}"
                self.network_errors.append(err)
                print(f"  [RED ERROR] {err}")

        def handle_console(msg):
            if msg.type == "error":
                text = msg.text
                if "favicon" not in text.lower():
                    self.console_errors.append(text)
                    print(f"  [CONSOLA ERROR] {text}")

        def handle_pageerror(err):
            self.page_errors.append(str(err))
            print(f"  [UNCAUGHT JS ERROR] {err}")

        def handle_dialog(dialog):
            self.xss_triggered = True
            dialog.dismiss()

        page.on("response", handle_response)
        page.on("console", handle_console)
        page.on("pageerror", handle_pageerror)
        page.on("dialog", handle_dialog)

    def run_all(self):
        print("=" * 80)
        print("INICIANDO SUITE ADVERSARIAL DE MONKEY TESTING Y CAOS E2E (LSEC STUDIO)")
        print(f"Target: {self.base_url}")
        print("=" * 80)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--use-gl=angle",
                    "--use-angle=swiftshader",
                    "--enable-webgl",
                    "--ignore-gpu-blocklist",
                ],
            )
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            self.setup_listeners(page)

            # -------------------------------------------------------------
            # FASE 1: Rage Clicking y Navegación Frenética (UI Chaos)
            # -------------------------------------------------------------
            print("\n[FASE 1] Rage Clicking en Stepper (45 cambios rápidos) y Concurrencia...")
            res = page.goto(f"{self.base_url}/studio", wait_until="domcontentloaded")
            assert res.status == 200, f"/studio devolvió HTTP {res.status}"
            page.wait_for_selector("#app-container", timeout=15000)
            page.wait_for_function("() => window.studioAvatarBridge && window.studioAvatarBridge.isReady", timeout=30000)

            # Cargar proyecto demo y verificar 4 ventanas del Stepper
            initial_state = page.evaluate("""() => {
                if (!window.appState.state.project) {
                    window.appState.resetToDefaultProject();
                }
                const cards = document.querySelectorAll('#transcript-segments-container .transcript-seg-card, #transcript-segments-container .transcript-unified-sentence');
                const stepBtns = document.querySelectorAll('#workflow-stepper .step-btn');
                return {
                    stepperCount: stepBtns.length,
                    segmentCount: cards.length
                };
            }""")
            assert initial_state["stepperCount"] == 4, "Se esperaban las 4 ventanas en #workflow-stepper"
            assert initial_state["segmentCount"] >= 8, "El proyecto demo no se cargó en Ventana 1"

            # Iniciar reproducción y ejecutar 48 clics rápidos sobre #workflow-stepper (12 ciclos x 4 pasos)
            page.click("#btn-play-pause")
            step_buttons = ["#step-btn-preparar", "#step-btn-traducir", "#step-btn-avatar", "#step-btn-revisar"]
            for _ in range(12):
                for selector in step_buttons:
                    page.click(selector)
                    time.sleep(0.015)

            page.wait_for_timeout(120)

            # Doble y triple clic rápido en botones críticos (Debouncing / Idempotencia)
            page.click("#step-btn-preparar")
            page.evaluate("""() => {
                const btn = document.getElementById('btn-step1-process-lsec');
                if (btn) { btn.click(); btn.click(); btn.click(); }
            }""")
            page.wait_for_timeout(150)

            # Triple clic en Re-traducir fila en Ventana 2 (verifica bloqueo in-flight disabled=true)
            page.click("#step-btn-traducir")
            retranslate_disabled_on_flight = page.evaluate("""() => {
                const btn = document.querySelector("[data-action='retranslate-row']");
                if (!btn) return false;
                btn.click();
                const locked = Boolean(btn.disabled);
                btn.click();
                btn.click();
                return locked;
            }""")
            assert retranslate_disabled_on_flight is True
            page.wait_for_timeout(200)

            # Triple clic en Play/Pause, Exportar SRT y Exportar MP4 en Ventana 3
            page.click("#step-btn-revisar")
            page.wait_for_timeout(100)
            for _ in range(3):
                page.click("#btn-play-pause")
                time.sleep(0.02)

            for _ in range(3):
                page.evaluate("() => document.getElementById('btn-step3-export-srt')?.click()")

            for _ in range(3):
                page.evaluate("() => document.getElementById('btn-step3-export-mp4')?.click()")
            page.wait_for_timeout(100)
            page.evaluate("() => window.modalsController?.close()")

            chaos_metrics = page.evaluate("""() => {
                const canvas = document.getElementById('avatar-webgl-canvas');
                const gl = canvas ? (canvas.getContext('webgl2') || canvas.getContext('webgl')) : null;
                const rect = canvas ? canvas.getBoundingClientRect() : { width: 0, height: 0 };
                return {
                    webglAlive: Boolean(gl && !gl.isContextLost()),
                    canvasWidth: rect.width,
                    canvasHeight: rect.height,
                    videoZoneNodes: document.querySelectorAll('#left-video-zone').length,
                    videoElementNodes: document.querySelectorAll('#main-video-element').length,
                    avatarCanvasNodes: document.querySelectorAll('#avatar-webgl-canvas').length,
                    subtitleOverlayNodes: document.querySelectorAll('#subtitle-overlay-container').length
                };
            }""")
            assert chaos_metrics["webglAlive"] is True, "Se perdió el contexto WebGL tras Rage Clicking"
            assert chaos_metrics["canvasWidth"] > 0 and chaos_metrics["canvasHeight"] > 0
            assert chaos_metrics["videoZoneNodes"] == 1
            assert chaos_metrics["videoElementNodes"] == 1
            assert chaos_metrics["avatarCanvasNodes"] == 1
            assert chaos_metrics["subtitleOverlayNodes"] == 1
            self.report["rage_click_chaos"] = chaos_metrics

            # -------------------------------------------------------------
            # FASE 2: Estrés de Mutación de Estado (15 operaciones) y Ráfagas Undo/Redo
            # -------------------------------------------------------------
            print("\n[FASE 2] 15 mutaciones rápidas de fichas de glosas + Ráfagas Undo/Redo (Ctrl+Z / Ctrl+Y)...")
            page.click("#step-btn-traducir")
            page.wait_for_timeout(100)

            mutation_audit = page.evaluate("""() => {
                const view = window.linguisticComparisonView;
                const seg = window.appState.state.project.segments[0];
                const initialSeq = [...(seg.gloss_sequence || [])];

                // Ejecutar 15 mutaciones consecutivas sin pausa (add, update, reorder, delete)
                for (let i = 1; i <= 5; i++) {
                    view.addGlossToRow(seg, `GLOSA_STRESS_${i}`, 0);
                }
                for (let i = 0; i < 4; i++) {
                    const list = view.getGlossObjectsForSegment(seg);
                    const idx = Math.min(i, list.length - 1);
                    view.updateGlossInRow(seg, list[idx], idx, `EDITADA_${i}`, 0);
                }
                for (let i = 0; i < 3; i++) {
                    const list = view.getGlossObjectsForSegment(seg);
                    if (list.length >= 2) {
                        view.reorderGlossInRow(seg, list[list.length - 1], list.length - 1, 0, 0);
                    }
                }
                for (let i = 0; i < 3; i++) {
                    const list = view.getGlossObjectsForSegment(seg);
                    if (list.length > 1) {
                        view.deleteGlossFromRow(seg, list[list.length - 1], list.length - 1, 0);
                    }
                }

                const after15Seq = [...(window.appState.state.project.segments[0].gloss_sequence || [])];
                const undoStackDepth = window.appState.undoStack.length;
                return { initialSeq, after15Seq, undoStackDepth };
            }""")
            assert mutation_audit["undoStackDepth"] >= 15, f"Historial Undo insuficiente: {mutation_audit['undoStackDepth']}"

            # Disparar ráfagas rápidas de Ctrl+Z (15 veces) y Ctrl+Y (15 veces)
            for _ in range(15):
                page.keyboard.press("Control+z")
            page.wait_for_timeout(80)

            after_undo_seq = page.evaluate("() => [...(window.appState.state.project.segments[0].gloss_sequence || [])]")
            assert after_undo_seq == mutation_audit["initialSeq"], (
                f"Ctrl+Z no restauró la secuencia original: {after_undo_seq} != {mutation_audit['initialSeq']}"
            )

            for _ in range(15):
                page.keyboard.press("Control+y")
            page.wait_for_timeout(80)

            after_redo_seq = page.evaluate("() => [...(window.appState.state.project.segments[0].gloss_sequence || [])]")
            assert after_redo_seq == mutation_audit["after15Seq"], (
                f"Ctrl+Y no restauró la secuencia re-hecha: {after_redo_seq} != {mutation_audit['after15Seq']}"
            )

            self.report["gloss_mutation_undo_redo"] = {
                "mutations_executed": 15,
                "undo_restored_exact": after_undo_seq == mutation_audit["initialSeq"],
                "redo_restored_exact": after_redo_seq == mutation_audit["after15Seq"],
            }

            # -------------------------------------------------------------
            # FASE 3: Fuzzing de Entradas de Usuario (Inputs Extremos y Maliciosos)
            # -------------------------------------------------------------
            print("\n[FASE 3] Fuzzing de Entradas (Vacío, Espacios, XSS, Emojis, +1500 chars, Números)...")
            long_paragraph = "La educación inclusiva universitaria en el Ecuador garantiza accesibilidad lingüística " * 20
            assert len(long_paragraph) > 1500

            fuzz_payloads = [
                "",
                "     ",
                "<script>alert('xss')</script><img src=x onerror=alert(1)>",
                "🔥🔥 ¿¿¿Hola??? ¡¡¡100% @#$%^&*()!!!",
                long_paragraph,
                "El presupuesto es 4500 dólares, teléfono 0992872993 a las 14:30",
            ]

            fuzz_report = page.evaluate("""async (payloads) => {
                const results = [];
                const seg = window.appState.state.project.segments[0];
                const view = window.linguisticComparisonView;

                for (const text of payloads) {
                    window.appState.updateSegment(seg.id, {
                        normalized_text: text,
                        raw_text: text,
                        status: 'CORRECTED'
                    });
                    view.addGlossToRow(seg, text || 'VACIO', 0);

                    // Forzar renderizado en las 3 ventanas (incluyendo Monitor en Vivo de Ventana 3)
                    window.transcriptWindow.renderSegments();
                    view.renderAll();
                    window.switchWizardStep('revisar');

                    const injectedScripts = document.querySelectorAll('#main-workspace script').length;
                    const injectedImgsWithOnerror = document.querySelectorAll('#main-workspace img[onerror]').length;
                    const docOverflow = document.documentElement.scrollWidth > window.innerWidth + 2;

                    let apiStatus = 200;
                    try {
                        const resp = await fetch('/api/v1/translate', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ text })
                        });
                        apiStatus = resp.status;
                    } catch (e) {
                        apiStatus = 0;
                    }

                    results.push({
                        payloadPreview: text.slice(0, 32),
                        injectedScripts,
                        injectedImgsWithOnerror,
                        docOverflow,
                        apiStatus
                    });
                }
                return results;
            }""", fuzz_payloads)

            # Limpiar errores 400/422 esperados por cadenas vacías/espacios en fuzzing directo a /api/v1/translate
            self.network_errors = [
                e for e in self.network_errors
                if not (("HTTP 422" in e or "HTTP 400" in e) and "/api/v1/translate" in e)
            ]
            self.console_errors = [
                e for e in self.console_errors
                if not ("status of 422" in e or "status of 400" in e)
            ]

            assert self.xss_triggered is False, "¡ALERTA CRÍTICA: Se ejecutó payload XSS!"
            for item in fuzz_report:
                assert item["injectedScripts"] == 0, f"Script inyectado en DOM: {item}"
                assert item["injectedImgsWithOnerror"] == 0, f"Img onerror inyectado en DOM: {item}"
                assert item["docOverflow"] is False, f"Overflow horizontal detectado con payload: {item}"
                assert item["apiStatus"] in (200, 400, 422), f"Backend devolvió estado inesperado: {item}"

            self.report["input_fuzzing_xss"] = {
                "payloads_tested": len(fuzz_payloads),
                "xss_triggered": self.xss_triggered,
                "results": fuzz_report,
            }

            # -------------------------------------------------------------
            # FASE 4: Estrés Multimedia, Redimensionamiento de Viewport y Persistencia F5
            # -------------------------------------------------------------
            print("\n[FASE 4] Personalizador de Subtítulos, Resize brusco de Viewport y Recarga F5...")
            page.click("#step-btn-revisar")
            page.wait_for_timeout(80)

            # Mutación frenética del Personalizador de Subtítulos
            page.evaluate("""() => {
                const fontSlider = document.getElementById('sub-cfg-font-size');
                const opSlider = document.getElementById('sub-cfg-bg-opacity');
                const hexInput = document.getElementById('sub-cfg-text-color-hex');
                for (const sz of [14, 22, 30, 38, 24]) {
                    if (fontSlider) {
                        fontSlider.value = String(sz);
                        fontSlider.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }
                for (const op of [20, 50, 85, 100, 75]) {
                    if (opSlider) {
                        opSlider.value = String(op);
                        opSlider.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }
                if (hexInput) {
                    hexInput.value = '#ffeb3b';
                    hexInput.dispatchEvent(new Event('change', { bubbles: true }));
                }
                document.getElementById('btn-pos-preset-top')?.click();
                document.getElementById('btn-pos-preset-center')?.click();
                document.getElementById('btn-pos-preset-bottom')?.click();
            }""")

            # Redimensionamiento brusco del viewport (Desktop -> Laptop -> Tablet -> Desktop)
            viewports = [
                {"width": 1920, "height": 1080},
                {"width": 1280, "height": 720},
                {"width": 768, "height": 1024},
                {"width": 1920, "height": 1080},
            ]
            resize_checks = []
            for vp in viewports:
                page.set_viewport_size(vp)
                page.wait_for_timeout(80)
                dims = page.evaluate("""() => {
                    const c = document.getElementById('avatar-webgl-canvas');
                    const v = document.getElementById('video-player-wrapper');
                    const cr = c ? c.getBoundingClientRect() : { width: 0, height: 0 };
                    const vr = v ? v.getBoundingClientRect() : { width: 0, height: 0 };
                    return { canvasW: cr.width, canvasH: cr.height, videoW: vr.width, videoH: vr.height };
                }""")
                assert dims["canvasW"] > 0 and dims["canvasH"] > 0, f"Canvas colapsó en viewport {vp}: {dims}"
                assert dims["videoW"] > 0 and dims["videoH"] > 0, f"Video colapsó en viewport {vp}: {dims}"
                resize_checks.append({"viewport": vp, **dims})

            # Edición antes de F5 y comprobación de recuperación tras recarga (F5)
            marker_text = "Oración persistida antes de recarga F5 en auditoría"
            page.evaluate("""(marker) => {
                window.switchWizardStep('traducir');
                const seg = window.appState.state.project.segments[0];
                window.appState.updateSegment(seg.id, {
                    normalized_text: marker,
                    raw_text: marker,
                    status: 'CORRECTED'
                });
            }""", marker_text)

            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector("#app-container", timeout=15000)
            page.wait_for_function("() => window.studioAvatarBridge && window.studioAvatarBridge.isReady", timeout=30000)

            recovered = page.evaluate("""() => {
                const seg0 = window.appState?.state?.project?.segments?.[0];
                return {
                    recoveredText: seg0 ? seg0.normalized_text : null,
                    activeStage: window.appState?.state?.workspace?.stage
                };
            }""")
            assert recovered["recoveredText"] == marker_text, f"No se recuperó edición tras F5: {recovered}"
            assert recovered["activeStage"] == "traducir", f"No se recuperó etapa activa tras F5: {recovered}"

            self.report["multimedia_resize_persistence"] = {
                "resize_checks": resize_checks,
                "f5_reload_recovered": recovered["recoveredText"] == marker_text,
            }

            # -------------------------------------------------------------
            # FASE 5: Navegación Cruzada /studio <-> /viewer <-> /avatarconfig
            # -------------------------------------------------------------
            print("\n[FASE 5] Estrés de Navegación Cruzada Multiruta...")
            res_v = page.goto(f"{self.base_url}/viewer", wait_until="domcontentloaded")
            assert res_v.status == 200
            page.wait_for_selector("#stage", timeout=15000)

            res_c = page.goto(f"{self.base_url}/avatarconfig", wait_until="domcontentloaded")
            assert res_c.status == 200
            page.wait_for_selector("#avatar-config-workspace", timeout=15000)

            res_s = page.goto(f"{self.base_url}/studio", wait_until="domcontentloaded")
            assert res_s.status == 200
            page.wait_for_selector("#app-container", timeout=15000)

            self.report["cross_navigation_stress"] = {
                "routes_visited": ["/studio", "/viewer", "/avatarconfig", "/studio"],
                "return_navigation_success": True,
            }

            browser.close()

        self.report["telemetry"] = {
            "total_requests": self.total_requests,
            "page_errors": self.page_errors,
            "console_errors": self.console_errors,
            "network_errors": self.network_errors,
            "zero_uncaught_js": len(self.page_errors) == 0,
            "zero_console_errors": len(self.console_errors) == 0,
            "zero_network_errors": len(self.network_errors) == 0,
        }

        assert len(self.page_errors) == 0, f"Excepciones JS detectadas: {self.page_errors}"
        assert len(self.console_errors) == 0, f"Errores de consola detectados: {self.console_errors}"
        assert len(self.network_errors) == 0, f"Errores HTTP 4xx/5xx detectados: {self.network_errors}"
        return self.report


def test_adversarial_browser_stress():
    """Ejecuta el arnés completo de Monkey Testing y Estrés Adversarial para pytest."""
    harness = AdversarialStressHarness(BASE_URL)
    results = harness.run_all()
    assert results["telemetry"]["zero_uncaught_js"] is True
    assert results["telemetry"]["zero_console_errors"] is True
    assert results["telemetry"]["zero_network_errors"] is True
    assert results["input_fuzzing_xss"]["xss_triggered"] is False
    assert results["multimedia_resize_persistence"]["f5_reload_recovered"] is True


if __name__ == "__main__":
    harness = AdversarialStressHarness(BASE_URL)
    results = harness.run_all()
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adversarial_stress_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Resultados guardados en: {output_path}")
