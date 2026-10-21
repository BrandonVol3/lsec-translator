"""
Suite de Pruebas Adversariales de Estrés de Navegador (Playwright / Chromium).
Challenger 2 — LSEC Studio Auditoría Milestone 2.

Objetivo:
Someter a estrés empírico y hostil la interfaz web de LSEC Studio:
1. Conmutación ultrarrápida de layout (atajo 'B' 10 veces consecutivas, tabs de inspector en bucle rápido).
2. Entradas rápidas de texto, borrado violento y llamadas concurrentes al motor de traducción.
3. Ráfaga de toggles (play / pause / reset / sequence) y cambios de clips en el visor 3D del Avatar VRM.
4. Navegación cruzada y recíproca entre /studio, /viewer y /avatarconfig bajo estrés.
5. Monitorización estricta de telemetría:
   - 0 excepciones JavaScript no capturadas (pageerror).
   - 0 bloqueos / deadlocks.
   - 0 errores HTTP 404 / 500 en assets esenciales y endpoints de API.
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
        self.total_requests = 0
        self.report = {
            "layout_stress": {},
            "translation_stress": {},
            "avatar_playback_stress": {},
            "cross_navigation_stress": {},
            "telemetry": {}
        }

    def setup_listeners(self, page):
        def handle_response(response):
            self.total_requests += 1
            status = response.status
            url = response.url
            if status >= 400:
                # Filtrar favicons opcionales
                if "favicon.ico" not in url:
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

        page.on("response", handle_response)
        page.on("console", handle_console)
        page.on("pageerror", handle_pageerror)

    def run_all(self):
        print("=" * 80)
        print("INICIANDO SUITE ADVERSARIAL DE ESTRÉS DE NAVEGADOR (CHALLENGER 2)")
        print(f"Target: {self.base_url}")
        print("=" * 80)

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
            self.setup_listeners(page)

            # -------------------------------------------------------------
            # TEST 1: Navegación a /studio y Estrés de Layout
            # -------------------------------------------------------------
            print("\n[FASE 1] Estrés de Layout en /studio...")
            res = page.goto(f"{self.base_url}/studio", wait_until="domcontentloaded")
            assert res.status == 200, f"/studio devolvió HTTP {res.status}"
            page.wait_for_selector("#app-container", timeout=15000)

            # 1.1 Ráfaga de tecla 'B' (10 conmutaciones consecutivas)
            print("  -> Ráfaga de atajo de teclado 'B' (10 veces rápidas)...")
            initial_collapsed = page.evaluate("() => document.getElementById('main-workspace').classList.contains('bottom-dock-hidden')")
            
            toggle_history = []
            for i in range(10):
                page.keyboard.press("b")
                time.sleep(0.04)  # Ráfaga ultrarrápida (40ms)
                is_hidden = page.evaluate("() => document.getElementById('main-workspace').classList.contains('bottom-dock-hidden')")
                toggle_history.append(is_hidden)

            # Tras 10 conmutaciones (número par), debe volver al estado inicial
            final_collapsed = page.evaluate("() => document.getElementById('main-workspace').classList.contains('bottom-dock-hidden')")
            assert final_collapsed == initial_collapsed, f"Desincronización de estado tras 10 conmutaciones 'b': inicial={initial_collapsed}, final={final_collapsed}"
            print(f"  -> Conmutaciones 'B' completadas exitosamente. Estado final consistente: {final_collapsed}")

            # 1.2 Ráfaga de conmutación de pestañas del Inspector Contextual
            print("  -> Ráfaga de conmutación de pestañas del Inspector (20 cambios continuos)...")
            inspector_tabs = [
                "#tab-btn-side-transcript",
                "#tab-btn-side-inspector",
                "#tab-btn-side-subtitles",
                "#tab-btn-side-avatar"
            ]
            for cycle in range(5):
                for tab in inspector_tabs:
                    page.click(tab)
                    time.sleep(0.03)

            # 1.3 Ráfaga de conmutación de tabs en Dock Inferior
            print("  -> Ráfaga de conmutación en Dock Inferior (10 cambios Segment Hub <-> Timeline)...")
            dock_tabs = ["#tab-btn-timeline", "#tab-btn-segment-hub"]
            for cycle in range(5):
                for dtab in dock_tabs:
                    page.click(dtab)
                    time.sleep(0.03)

            self.report["layout_stress"] = {
                "b_key_toggles": len(toggle_history),
                "state_coherent": final_collapsed == initial_collapsed,
                "inspector_tab_switches": 20,
                "dock_tab_switches": 10
            }

            # -------------------------------------------------------------
            # TEST 2: Carga de Datos y Estrés de Traducción y Edición de Texto
            # -------------------------------------------------------------
            print("\n[FASE 2] Estrés de Entrada de Texto y Traducción Rápida...")
            
            # 2.1 Carga rápida de proyecto demo
            page.evaluate("""() => {
                if (typeof DEMO_PROJECT_DATA !== 'undefined' && window.appState) {
                    window.appState.loadProject(DEMO_PROJECT_DATA);
                    window.appState.markTranscriptionReady();
                }
            }""")
            page.wait_for_timeout(300)

            # 2.2 Estrés en campos de búsqueda
            print("  -> Ráfaga de búsquedas rápidas con borrado continuo...")
            search_input = page.locator("#side-transcript-search")
            if search_input.is_visible():
                for query in ["universidad", "libertad", "conocimiento", "sostenible", "xyz123"]:
                    search_input.fill(query)
                    time.sleep(0.02)
                    search_input.fill("")
                    time.sleep(0.02)

            # 2.3 Edición de subtítulo en el primer segmento
            print("  -> Estrés de edición interactiva en tarjeta de segmento...")
            edit_btn = page.locator("[id^='btn-edit-']").first
            if edit_btn.is_visible():
                edit_btn.click()
                time.sleep(0.1)
                text_input = page.locator("[id^='edit-text-']").first
                if text_input.is_visible():
                    text_input.fill("Texto original de prueba rápida")
                    time.sleep(0.05)
                    text_input.fill("Texto rápido reemplazado")
                    time.sleep(0.05)
                    save_btn = page.locator("[id^='btn-save-']").first
                    if save_btn.is_visible():
                        save_btn.click()
                        time.sleep(0.1)

            # 2.4 Ráfaga concurrente y secuencial al motor de traducción (/api/v1/translate)
            print("  -> Ráfaga de peticiones al motor lingüístico (/api/v1/translate)...")
            stress_inputs = [
                "Hola buenos días",
                "Educación pública superior de calidad",
                "¿Cómo estás tú hoy?",
                "1 2 3 4 5 números",
                "!@#$%^&*()_+~`-={}|[]:;\"'<>?,./ caracteres especiales",
                "A" * 300,  # Texto muy largo
                "   espacios en blanco   ",
                "El estudiante viaja a Quito mañana por la mañana"
            ]

            translation_results = page.evaluate("""async (inputs) => {
                const results = [];
                for (const text of inputs) {
                    try {
                        const glosses = await window.pipelineProcessor.translateSegmentViaBackend(text, 0.0, 3.0, "seg_stress");
                        results.push({
                            text: text.substring(0, 30),
                            gloss_count: glosses.length,
                            success: true
                        });
                    } catch (err) {
                        results.push({
                            text: text.substring(0, 30),
                            error: err.message,
                            success: false
                        });
                    }
                }
                return results;
            }""", stress_inputs)

            print(f"  -> {len(translation_results)} traducciones de estrés evaluadas.")
            for r in translation_results:
                print(f"     '{r['text']}...': success={r['success']}, gloss_count={r.get('gloss_count', 'N/A')}")
                assert r["success"], f"Fallo en traducción de '{r['text']}': {r.get('error')}"

            self.report["translation_stress"] = {
                "inputs_tested": len(stress_inputs),
                "results": translation_results
            }

            # -------------------------------------------------------------
            # TEST 3: Ráfaga de Playback en Avatar 3D Viewport
            # -------------------------------------------------------------
            print("\n[FASE 3] Estrés en Visor 3D del Avatar VRM...")
            
            # Cambiar a pestaña Avatar 3D
            page.click("#tab-btn-side-avatar")
            print("  -> Esperando inicialización de studioAvatarBridge...")
            page.wait_for_function("() => window.studioAvatarBridge && window.studioAvatarBridge.isReady", timeout=30000)
            page.wait_for_timeout(300)

            # Ráfaga de toggles Play / Pause / Reset / Sequence (20 clics rápidos)
            print("  -> Ráfaga de play/pause/reset/sequence (24 operaciones rápidas)...")
            avatar_actions = [
                "#btn-avatar-play",
                "#btn-avatar-pause",
                "#btn-avatar-play",
                "#btn-avatar-reset",
                "#btn-avatar-play-sequence",
                "#btn-avatar-pause",
                "#btn-avatar-reset"
            ]
            for cycle in range(3):
                for act in avatar_actions:
                    btn = page.locator(act)
                    if btn.is_visible():
                        btn.click()
                        time.sleep(0.04)

            # Cambio rápido de clips demostrativos existentes
            print("  -> Conmutación rápida de clips en selector...")
            available_clips = page.evaluate("""() => {
                const sel = document.getElementById('select-avatar-clip');
                return sel ? Array.from(sel.options).map(o => o.value).filter(v => v) : [];
            }""")
            print(f"     Opciones disponibles en #select-avatar-clip: {len(available_clips)}")
            clips_to_test = [c for c in ["SALUDAR_DEMO", "NEGACION_DEMO", "NEUTRAL", "TEST_MANO_ABIERTA", "TEST_PUNO", "TEST_CNM_HEAD_NOD"] if c in available_clips]
            if not clips_to_test and available_clips:
                clips_to_test = available_clips[:5]
            
            for clip in clips_to_test:
                page.select_option("#select-avatar-clip", clip)
                time.sleep(0.05)

            # Verificar que el canvas WebGL permanece activo y sin errores
            canvas_alive = page.evaluate("""() => {
                const canvas = document.getElementById('avatar-webgl-canvas');
                if (!canvas) return false;
                const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
                return gl ? !gl.isContextLost() : false;
            }""")
            print(f"  -> Contexto WebGL del avatar tras estrés: activo={canvas_alive}")
            assert canvas_alive, "El contexto WebGL del avatar se perdió o crasheó"

            self.report["avatar_playback_stress"] = {
                "action_cycles": 3,
                "actions_per_cycle": len(avatar_actions),
                "clips_tested": clips_to_test,
                "webgl_alive": canvas_alive
            }

            # -------------------------------------------------------------
            # TEST 4: Navegación Cruzada /studio <-> /viewer <-> /avatarconfig
            # -------------------------------------------------------------
            print("\n[FASE 4] Estrés de Navegación Cruzada Multiruta...")
            
            # 4.1 /studio -> /viewer
            print("  -> Navegando a /viewer (Visualizador Autónomo 1:1)...")
            res_v = page.goto(f"{self.base_url}/viewer", wait_until="domcontentloaded")
            assert res_v.status == 200, f"/viewer devolvió HTTP {res_v.status}"
            page.wait_for_selector("#stage", timeout=15000)
            page.wait_for_timeout(500)

            # Ráfaga de interacción en /viewer
            print("  -> Ráfaga de controles de cámara y reproducción en /viewer...")
            cams = ["#cam-mano", "#cam-macro-rh", "#cam-macro-lh", "#cam-full"]
            for cam in cams:
                btn = page.locator(cam)
                if btn.is_visible():
                    btn.click()
                    time.sleep(0.03)

            viewer_btns = ["#play", "#stop", "#prev", "#next"]
            for vb in viewer_btns:
                btn = page.locator(vb)
                if btn.is_visible():
                    btn.click()
                    time.sleep(0.04)

            # 4.2 /viewer -> /avatarconfig
            print("  -> Navegando a /avatarconfig (Entorno de Calibración)...")
            res_c = page.goto(f"{self.base_url}/avatarconfig", wait_until="domcontentloaded")
            assert res_c.status == 200, f"/avatarconfig devolvió HTTP {res_c.status}"
            page.wait_for_selector("#avatar-config-workspace", timeout=15000)
            page.wait_for_timeout(500)

            # 4.3 /avatarconfig -> /studio mediante botón de retorno
            print("  -> Retornando a /studio mediante #btn-back-to-studio...")
            btn_back = page.locator("#btn-back-to-studio")
            assert btn_back.is_visible(), "Botón #btn-back-to-studio no visible en /avatarconfig"
            
            with page.expect_navigation():
                btn_back.click()
            
            assert "/studio" in page.url, f"La URL esperada era /studio pero es {page.url}"
            page.wait_for_selector("#app-container", timeout=15000)
            print("  -> Regreso a /studio exitoso. Comprobando persistencia del DOM...")
            assert page.locator("#top-navbar").is_visible(), "Navbar no visible tras retorno a /studio"
            assert page.locator("#main-workspace").is_visible(), "Main workspace no visible tras retorno a /studio"

            self.report["cross_navigation_stress"] = {
                "routes_visited": ["/studio", "/viewer", "/avatarconfig", "/studio"],
                "return_navigation_success": True
            }

            browser.close()

        # -------------------------------------------------------------
        # TELEMETRÍA Y CONCLUSIÓN
        # -------------------------------------------------------------
        print("\n" + "=" * 80)
        print("TELEMETRÍA DE ESTRÉS FINAL")
        print("=" * 80)
        print(f"Peticiones de red totales: {self.total_requests}")
        print(f"Excepciones JS no controladas (pageerror): {len(self.page_errors)}")
        print(f"Errores en consola (console.error): {len(self.console_errors)}")
        print(f"Errores de red HTTP 4xx/5xx: {len(self.network_errors)}")

        self.report["telemetry"] = {
            "total_requests": self.total_requests,
            "page_errors": self.page_errors,
            "console_errors": self.console_errors,
            "network_errors": self.network_errors,
            "zero_uncaught_js": len(self.page_errors) == 0,
            "zero_console_errors": len(self.console_errors) == 0,
            "zero_network_errors": len(self.network_errors) == 0
        }

        # Aserciones adversariales críticas
        assert len(self.page_errors) == 0, f"Se produjeron {len(self.page_errors)} excepciones JS: {self.page_errors}"
        assert len(self.console_errors) == 0, f"Se produjeron {len(self.console_errors)} errores de consola: {self.console_errors}"
        assert len(self.network_errors) == 0, f"Se produjeron {len(self.network_errors)} respuestas de red 4xx/5xx: {self.network_errors}"

        print("\n>>> AUDITORÍA ADVERSARIAL SUPERADA: 0 ERRORES, 0 DEADLOCKS, 0 FALLOS DE RED <<<\n")
        return self.report


def test_adversarial_browser_stress():
    """Ejecuta el arnés de estrés adversarial de navegador para pytest."""
    harness = AdversarialStressHarness(BASE_URL)
    results = harness.run_all()
    assert results["telemetry"]["zero_uncaught_js"] is True
    assert results["telemetry"]["zero_console_errors"] is True
    assert results["telemetry"]["zero_network_errors"] is True


if __name__ == "__main__":
    harness = AdversarialStressHarness(BASE_URL)
    results = harness.run_all()
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adversarial_stress_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Resultados guardados en: {output_path}")
