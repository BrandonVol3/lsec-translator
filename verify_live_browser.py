"""
Script de Verificación E2E en Navegador Real con Playwright para LSEC Studio.
Auditoría Milestone 2:
1. /studio (Navbar, Timeline, Video Zone, Inspector Dock, Avatar 3D VRM 1.0, Traducción y Glosas)
2. /viewer (Visualizador Autónomo 1:1, Canvas Three.js, Controles)
3. /avatarconfig (Entorno de Calibración, Canvas WebGL, Selector v2.6/v2.5)
4. /docs (FastAPI Swagger UI)
5. Verificación de 0 excepciones JavaScript no capturadas y 0 errores HTTP 4xx/5xx en red.
"""

import sys
import json
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8000"

def run_live_audit():
    results = {
        "studio": {},
        "viewer": {},
        "avatarconfig": {},
        "docs": {},
        "telemetry": {
            "page_errors": [],
            "console_errors": [],
            "network_errors": [],
            "total_requests": 0,
            "passed_checks": 0,
            "failed_checks": 0
        }
    }

    page_errors = []
    console_errors = []
    network_errors = []
    total_requests = 0

    print("=" * 70)
    print("INICIANDO AUDITORÍA EN VIVO CON PLAYWRIGHT (LSEC STUDIO E2E)")
    print("=" * 70)

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

        # Listeners de telemetría de red y consola
        def handle_response(response):
            nonlocal total_requests
            total_requests += 1
            status = response.status
            url = response.url
            if status >= 400:
                # Ignorar favicon opcional si no es crítico
                if "favicon.ico" not in url:
                    err_entry = f"HTTP {status} en {url}"
                    network_errors.append(err_entry)
                    print(f"  [ERROR RED] {err_entry}")

        def handle_console(msg):
            if msg.type in ["error"]:
                text = msg.text
                # Ignorar avisos inocuos conocidos si los hubiera
                if "favicon" not in text.lower():
                    console_errors.append(text)
                    print(f"  [CONSOLA ERROR] {text}")

        def handle_pageerror(err):
            page_errors.append(str(err))
            print(f"  [EXCEPCIÓN JS] {err}")

        page.on("response", handle_response)
        page.on("console", handle_console)
        page.on("pageerror", handle_pageerror)

        # -------------------------------------------------------------
        # 1. AUDITORÍA DE /studio
        # -------------------------------------------------------------
        print("\n>>> 1. Verificando /studio...")
        res_studio = page.goto(f"{BASE_URL}/studio", wait_until="domcontentloaded")
        assert res_studio.status == 200, f"/studio devolvió HTTP {res_studio.status}"
        page.wait_for_selector("#app-container", timeout=15000)
        results["studio"]["http_status"] = res_studio.status

        # Comprobar componentes estructurales clave
        navbar_vis = page.locator("#top-navbar").is_visible()
        video_zone_vis = page.locator("#left-video-zone").is_visible()
        inspector_dock_vis = page.locator("#contextual-inspector-zone").is_visible()
        bottom_dock_vis = page.locator("#bottom-dock-zone").is_visible()

        print(f"  Navbar visible: {navbar_vis}")
        print(f"  Zona de Video visible: {video_zone_vis}")
        print(f"  Inspector Dock visible: {inspector_dock_vis}")
        print(f"  Panel Inferior / Dock visible: {bottom_dock_vis}")

        assert navbar_vis, "Navbar no está visible"
        assert video_zone_vis, "Zona de video no está visible"
        assert inspector_dock_vis, "Inspector dock no está visible"
        assert bottom_dock_vis, "Bottom dock no está visible"
        results["studio"]["structural_elements"] = {
            "navbar": navbar_vis,
            "video_zone": video_zone_vis,
            "inspector_dock": inspector_dock_vis,
            "bottom_dock": bottom_dock_vis
        }

        # Esperar a que el Avatar Bridge esté listo
        print("  Esperando inicialización de studioAvatarBridge y VRM...")
        page.wait_for_function("() => window.studioAvatarBridge && window.studioAvatarBridge.isReady", timeout=30000)
        
        # Abrir pestaña Avatar 3D en el dock contextual
        page.click("#tab-btn-side-avatar")
        page.wait_for_timeout(400)
        
        canvas_vis = page.locator("#avatar-webgl-canvas").is_visible()
        model_pill = page.locator("#avatar-model-source-info").inner_text()
        print(f"  Canvas WebGL Avatar visible: {canvas_vis}")
        print(f"  Fuente del modelo en HUD: '{model_pill}'")
        assert canvas_vis, "Canvas WebGL de Avatar 3D no está visible"
        assert ("VRM 1.0" in model_pill) or ("Rig" in model_pill), f"Modelo inesperado: {model_pill}"
        results["studio"]["avatar_3d"] = {
            "canvas_visible": canvas_vis,
            "model_source": model_pill
        }

        # Probar interacción del Avatar 3D (Reproducir, Pausar, Reset)
        page.select_option("#select-avatar-clip", "SALUDAR_DEMO")
        page.wait_for_timeout(200)
        page.click("#btn-avatar-play")
        page.wait_for_timeout(350)
        status_play = page.locator("#avatar-playback-status-badge").inner_text()
        page.click("#btn-avatar-pause")
        page.wait_for_timeout(200)
        status_pause = page.locator("#avatar-playback-status-badge").inner_text()
        page.click("#btn-avatar-reset")
        page.wait_for_timeout(200)
        status_reset = page.locator("#avatar-playback-status-badge").inner_text()
        print(f"  Avatar playback: play='{status_play}', pause='{status_pause}', reset='{status_reset}'")
        results["studio"]["avatar_playback"] = {
            "play_status": status_play,
            "pause_status": status_pause,
            "reset_status": status_reset
        }

        # Probar Flujo de Traducción: Texto "Hola buenos días" -> /api/v1/translate -> Glosas en Timeline
        print("\n  Ejecutando flujo de traducción en vivo: 'Hola buenos días'...")
        translation_eval = page.evaluate("""async () => {
            const testText = "Hola buenos días";
            // Iniciar o resetear proyecto base
            window.appState.resetToDefaultProject();
            
            // Invocar el traductor lingüístico mediante pipelineProcessor
            const glosses = await window.pipelineProcessor.translateSegmentViaBackend(testText, 0.0, 2.5, "seg_live_audit_1");
            
            // Asignar el segmento de prueba y las glosas traducidas
            const testSegment = {
                id: "seg_live_audit_1",
                start_seconds: 0.0,
                end_seconds: 2.5,
                start_time: 0.0,
                end_time: 2.5,
                duration: 2.5,
                original_text: testText,
                normalized_text: testText,
                status: "CORRECTED",
                requires_native_review: false,
                glosses: glosses,
                gloss_sequence: glosses.map(g => g.gloss || g.lemma)
            };
            
            window.appState.state.project.segments = [testSegment];
            window.appState.state.project.glosses = glosses;
            window.appState.setWorkflowStep('step3_revisar');
            window.appState.emit('projectUpdated', window.appState.state.project);
            window.appState.emit('segmentsChanged', window.appState.state.project.segments);
            
            return {
                glossesCount: glosses.length,
                glossTokens: glosses.map(g => g.gloss || g.lemma),
                status: window.appState.state.workflowStep
            };
        }""")
        print(f"  Traducción completada: {translation_eval['glossesCount']} glosas generadas ({translation_eval['glossTokens']})")
        assert translation_eval["glossesCount"] >= 2, "Se esperaban al menos 2 glosas para 'Hola buenos días'"
        results["studio"]["translation"] = translation_eval

        # Activar pestaña Línea de Tiempo y comprobar píldoras de glosas en Track 2
        page.click("#tab-btn-timeline")
        page.wait_for_timeout(300)
        
        timeline_pills = page.evaluate("""() => {
            const pills = Array.from(document.querySelectorAll('#lane-track-2 .sentence-gloss-pill'));
            return pills.map(p => p.innerText.trim());
        }""")
        print(f"  Píldoras visibles en Pista 2 del Timeline: {timeline_pills}")
        assert len(timeline_pills) >= 2, f"No se encontraron píldoras en la pista 2 del timeline: {timeline_pills}"
        results["studio"]["timeline_pills"] = timeline_pills

        # -------------------------------------------------------------
        # 2. AUDITORÍA DE /viewer
        # -------------------------------------------------------------
        print("\n>>> 2. Verificando /viewer (Reproductor Autónomo 1:1)...")
        res_viewer = page.goto(f"{BASE_URL}/viewer", wait_until="domcontentloaded")
        assert res_viewer.status == 200, f"/viewer devolvió HTTP {res_viewer.status}"
        page.wait_for_selector("#stage", timeout=15000)
        page.wait_for_timeout(1000)

        viewer_stage_vis = page.locator("#stage").is_visible()
        viewer_canvas_count = page.locator("#stage canvas").count()
        macro_canvas_count = page.locator("#macroManoWrap canvas").count()
        search_input_vis = page.locator("#signSearch").is_visible()
        btn_play_vis = page.locator("#play").is_visible()

        print(f"  Stage visible: {viewer_stage_vis}")
        print(f"  Canvas WebGL en #stage: {viewer_canvas_count}")
        print(f"  Canvas Sub-escena Macro: {macro_canvas_count}")
        print(f"  Buscador de señas visible: {search_input_vis}")
        print(f"  Botón Play/Pausa visible: {btn_play_vis}")

        assert viewer_stage_vis, "#stage no visible en /viewer"
        assert viewer_canvas_count >= 1, "Canvas WebGL no generado en #stage de /viewer"
        assert search_input_vis, "Buscador de señas no visible en /viewer"

        results["viewer"] = {
            "http_status": res_viewer.status,
            "stage_visible": viewer_stage_vis,
            "canvas_count": viewer_canvas_count,
            "macro_canvas_count": macro_canvas_count,
            "controls_present": search_input_vis and btn_play_vis
        }

        # -------------------------------------------------------------
        # 3. AUDITORÍA DE /avatarconfig
        # -------------------------------------------------------------
        print("\n>>> 3. Verificando /avatarconfig (Estación de Calibración)...")
        res_config = page.goto(f"{BASE_URL}/avatarconfig", wait_until="domcontentloaded")
        assert res_config.status == 200, f"/avatarconfig devolvió HTTP {res_config.status}"
        page.wait_for_selector("#avatar-config-workspace", timeout=15000)
        page.wait_for_timeout(1000)

        config_canvas_vis = page.locator("#avatar-webgl-canvas").is_visible()
        btn_back_vis = page.locator("#btn-back-to-studio").is_visible()
        version_group_vis = page.locator("#navbar-version-group").is_visible()
        uhd_layout_vis = page.locator("#comparison-layout-wrap").is_visible()

        print(f"  Canvas WebGL visible: {config_canvas_vis}")
        print(f"  Botón 'Volver a Studio' visible: {btn_back_vis}")
        print(f"  Conmutador v2.6/v2.5 visible: {version_group_vis}")
        print(f"  Layout comparativo UHD visible: {uhd_layout_vis}")

        assert config_canvas_vis, "Canvas WebGL no visible en /avatarconfig"
        assert btn_back_vis, "Botón volver a studio no visible en /avatarconfig"
        assert version_group_vis, "Conmutador de versiones no visible en /avatarconfig"

        results["avatarconfig"] = {
            "http_status": res_config.status,
            "canvas_visible": config_canvas_vis,
            "btn_back_visible": btn_back_vis,
            "version_group_visible": version_group_vis,
            "uhd_layout_visible": uhd_layout_vis
        }

        # -------------------------------------------------------------
        # 4. AUDITORÍA DE /docs
        # -------------------------------------------------------------
        print("\n>>> 4. Verificando /docs (FastAPI Swagger UI)...")
        res_docs = page.goto(f"{BASE_URL}/docs", wait_until="domcontentloaded")
        assert res_docs.status == 200, f"/docs devolvió HTTP {res_docs.status}"
        page.wait_for_selector("#swagger-ui", timeout=15000)
        
        swagger_present = page.locator("#swagger-ui").first.is_visible()
        openapi_title = page.title()
        print(f"  Swagger UI visible: {swagger_present}")
        print(f"  Título de página /docs: '{openapi_title}'")
        assert swagger_present, "Swagger UI no se renderizó en /docs"

        results["docs"] = {
            "http_status": res_docs.status,
            "swagger_ui_visible": swagger_present,
            "title": openapi_title
        }

        browser.close()

    # -------------------------------------------------------------
    # 5. VERIFICACIÓN FINAL DE TELEMETRÍA (0 ERRORES)
    # -------------------------------------------------------------
    print("\n" + "=" * 70)
    print("TELEMETRÍA DE RED Y CONSOLA FINAL")
    print("=" * 70)
    print(f"Total peticiones de red procesadas: {total_requests}")
    print(f"Total excepciones JavaScript de página (pageerror): {len(page_errors)}")
    print(f"Total errores de consola (console error): {len(console_errors)}")
    print(f"Total errores de red HTTP 4xx/5xx: {len(network_errors)}")

    results["telemetry"]["total_requests"] = total_requests
    results["telemetry"]["page_errors"] = page_errors
    results["telemetry"]["console_errors"] = console_errors
    results["telemetry"]["network_errors"] = network_errors

    assert len(page_errors) == 0, f"Se detectaron {len(page_errors)} excepciones JavaScript no capturadas: {page_errors}"
    assert len(console_errors) == 0, f"Se detectaron {len(console_errors)} errores críticos en consola: {console_errors}"
    assert len(network_errors) == 0, f"Se detectaron {len(network_errors)} respuestas HTTP 4xx/5xx en red: {network_errors}"

    print("\n>>> AUDITORÍA EN VIVO COMPLETADA EXITOSAMENTE CON 0 ERRORES <<<")
    return results

if __name__ == "__main__":
    audit_data = run_live_audit()
    output_path = "live_browser_audit_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(audit_data, f, indent=2, ensure_ascii=False)
    print(f"Resultados guardados en {output_path}")
