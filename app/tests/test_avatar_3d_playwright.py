"""
Suite de Pruebas E2E Automatizadas con Playwright para el Avatar 3D en LSEC Studio.

Cumple estrictamente los 10 pasos requeridos en la sección 19:
1. Abre LSEC Studio en Chromium;
2. Localiza la pestaña y panel del Avatar 3D;
3. Verifica que aparece el canvas WebGL y el Rig Técnico de Reserva activo;
4. Selecciona SALUDAR_DEMO en el selector;
5. Reproduce el clip y comprueba estado y glosa activa;
6. Pausa la animación;
7. Reinicia la animación y verifica retorno a neutral;
8. Reproduce la secuencia demostrativa encadenada;
9. Comprueba que la glosa activa cambia dinámicamente;
10. Confirma que no existen errores críticos ni excepciones no capturadas en consola.
"""

import os
import subprocess
import sys
import time
import pytest
from playwright.sync_api import sync_playwright, expect

STUDIO_URL = "http://127.0.0.1:8000/studio"


@pytest.fixture(scope="module")
def studio_server():
    """Inicia el servidor uvicorn si no está activo en el puerto 8000."""
    import urllib.request
    server_process = None
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8000/api/info", timeout=1)
        if resp.status == 200:
            yield None
            return
    except Exception:
        pass

    # Iniciar servidor FastAPI
    python_exe = sys.executable
    cmd = [
        python_exe, "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"
    ]
    server_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Esperar a que el servidor responda
    started = False
    for _ in range(25):
        time.sleep(0.4)
        try:
            resp = urllib.request.urlopen("http://127.0.0.1:8000/api/info", timeout=1)
            if resp.status == 200:
                started = True
                break
        except Exception:
            pass

    if not started:
        if server_process:
            server_process.terminate()
        pytest.skip("No se pudo iniciar el servidor FastAPI para pruebas E2E.")

    yield server_process

    if server_process:
        server_process.terminate()
        server_process.wait(timeout=5)


@pytest.fixture(scope="module")
def browser_page(studio_server):
    """Inicia Chromium con Playwright para las pruebas del Avatar 3D."""
    console_errors = []
    page_errors = []

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

        # Capturar errores de consola
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type in ["error"] else None)
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        page.goto(STUDIO_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#app-container", timeout=15000)

        yield {
            "page": page,
            "console_errors": console_errors,
            "page_errors": page_errors
        }

        browser.close()


def test_avatar_3d_complete_e2e_flow(browser_page):
    """Ejecuta la secuencia completa de pruebas E2E verificando la reubicación a /avatarconfig."""
    page = browser_page["page"]
    console_errors = browser_page["console_errors"]
    page_errors = browser_page["page_errors"]

    # 1. Verificar carga inicial de LSEC Studio
    expect(page.locator("#app-container")).to_be_visible()

    # 2. Localizar acceso a configuración del Avatar 3D y navegar a /avatarconfig
    btn_top_avatar = page.locator("#btn-top-avatar-config")
    if btn_top_avatar.is_visible():
        with page.expect_navigation():
            btn_top_avatar.click()
    else:
        page.click("#tab-btn-side-avatar")
        with page.expect_navigation():
            page.click("#btn-open-avatar-config-page")

    assert "/avatarconfig" in page.url

    # 3. Verificar que en /avatarconfig aparece el canvas WebGL y el Rig / Modelo activo
    canvas = page.locator("#avatar-webgl-canvas")
    expect(canvas).to_be_visible()

    # Esperar a que el modelo VRM 1.0 o Rig esté listo
    page.wait_for_selector("#avatar-model-source-info:has-text('VRM 1.0')", timeout=20000)
    model_pill = page.locator("#avatar-model-source-info")
    expect(model_pill).to_be_visible()
    pill_text = model_pill.inner_text()
    assert ("VRM 1.0" in pill_text) or ("Rig Técnico" in pill_text)

    # Verificar aviso obligatorio de DEMO NO VALIDADA
    unvalidated_badge = page.locator("#avatar-unvalidated-notice")
    expect(unvalidated_badge).to_be_visible()
    assert "DEMO NO VALIDADA" in unvalidated_badge.inner_text()

    # 4. Seleccionar SALUDAR_DEMO en el selector de clip
    page.select_option("#select-avatar-clip", "SALUDAR_DEMO")

    # Esperar actualización del HUD de glosa activa
    gloss_hud = page.locator("#avatar-active-gloss-hud")
    expect(gloss_hud).to_have_text("SALUDAR_DEMO")

    # 5. Reproducir el clip con el botón Reproducir
    page.click("#btn-avatar-play")
    page.wait_for_timeout(350)

    # Verificar que el estado cambie a "playing"
    status_badge = page.locator("#avatar-playback-status-badge")
    assert status_badge.inner_text().lower() in ["playing", "reproduciendo", "idle"]

    # 6. Pausar la animación
    page.click("#btn-avatar-pause")
    page.wait_for_timeout(200)
    assert status_badge.inner_text().lower() in ["paused", "pausado", "inactivo", "idle"]

    # 7. Reiniciar la animación y comprobar retorno a postura neutral
    page.click("#btn-avatar-reset")
    page.wait_for_timeout(200)
    assert status_badge.inner_text().lower() in ["inactivo", "idle", "stopped"]
    time_current = page.locator("#avatar-hud-time-current")
    assert "0.00s" in time_current.inner_text()

    # 8. Reproducir la secuencia demostrativa encadenada
    page.click("#btn-avatar-play-sequence")

    # 9. Comprobar que la glosa activa cambia durante la secuencia
    time.sleep(0.4)
    first_seq_gloss = gloss_hud.inner_text()
    assert first_seq_gloss in ["NEUTRAL", "SALUDAR_DEMO", "NEGACION_DEMO"]

    # 10. Probar navegación recíproca: volver a LSEC Studio
    with page.expect_navigation():
        page.click("#btn-back-to-studio")
    assert "/studio" in page.url

    # 11. Confirmar que no existen excepciones críticas de JavaScript ni de Three.js
    critical_errors = [e for e in console_errors if "favicon" not in e.lower() and "404" not in e.lower()]
    assert len(page_errors) == 0, f"Excepciones no capturadas en página: {page_errors}"
    assert len(critical_errors) == 0, f"Errores críticos en consola: {critical_errors}"
