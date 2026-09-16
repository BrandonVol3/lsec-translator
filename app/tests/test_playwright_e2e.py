"""
Suite de Pruebas E2E Automatizadas con Playwright para LSEC Studio 2.1.1.

Verifica en un navegador Chromium real (Playwright):
1. Carga inicial de LSEC Studio (HTTP 200, título, layout de 4 zonas).
2. Pestañas del Inspector Contextual (Transcripción, Inspector, Subtítulos).
3. Pestañas del Dock Inferior (Editor de Segmentos vs Línea de Tiempo).
4. Ocultamiento de la Barra Inferior (colapso del dock, expansión al 100% de altura del panel derecho).
5. Restauración del Dock Inferior mediante botón en barra comprimida.
6. Conmutación mediante atajo de teclado 'B'.
7. Conmutación mediante botón en barra superior (#btn-toggle-bottom-dock).
8. Modal de configuración y accesibilidad con listado de atajos.
9. Captura de evidencias visuales (screenshots PNG) para auditoría.
"""

import os
import re
import pytest
from playwright.sync_api import sync_playwright, expect

ARTIFACTS_DIR = r"C:\Users\brana\.gemini\antigravity-ide\brain\454798ea-8857-4f01-9662-f1927c5ad703"
STUDIO_URL = "http://127.0.0.1:8000/studio"


@pytest.fixture(scope="module")
def browser_context():
    """Inicia Chromium con Playwright para la suite E2E."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(STUDIO_URL)
        page.wait_for_selector("#app-container", timeout=10000)
        yield page
        browser.close()


def test_e2e_01_initial_layout(browser_context):
    """Verifica que todos los componentes base de LSEC Studio se carguen."""
    page = browser_context
    expect(page).to_have_title("LSEC Studio 2.1.1 — Estación de Trabajo Lingüística y Audiovisual")

    # Layout de 4 zonas
    expect(page.locator("#top-navbar")).to_be_visible()
    expect(page.locator("#left-video-zone")).to_be_visible()
    expect(page.locator("#contextual-inspector-zone")).to_be_visible()
    expect(page.locator("#bottom-dock-zone")).to_be_visible()
    expect(page.locator("#horizontal-splitter")).to_be_visible()

    # Capturar screenshot inicial
    screenshot_path = os.path.join(ARTIFACTS_DIR, "playwright_01_initial_layout.png")
    page.screenshot(path=screenshot_path)
    assert os.path.exists(screenshot_path)


def test_e2e_02_contextual_inspector_tabs(browser_context):
    """Verifica la navegación entre Transcripción, Inspector y Subtítulos."""
    page = browser_context

    # 1. Pestaña Inspector
    page.click("#tab-btn-side-inspector")
    expect(page.locator("#view-side-inspector")).to_be_visible()
    expect(page.locator("#view-side-transcript")).to_be_hidden()

    # 2. Pestaña Subtítulos
    page.click("#tab-btn-side-subtitles")
    expect(page.locator("#view-side-subtitles")).to_be_visible()
    expect(page.locator("#view-side-inspector")).to_be_hidden()

    # 3. Pestaña Transcripción
    page.click("#tab-btn-side-transcript")
    expect(page.locator("#view-side-transcript")).to_be_visible()
    expect(page.locator("#view-side-subtitles")).to_be_hidden()


def test_e2e_03_bottom_dock_tabs(browser_context):
    """Verifica la alternancia entre Editor de Segmentos y Línea de Tiempo."""
    page = browser_context

    # Cambiar a Línea de Tiempo
    page.click("#tab-btn-timeline")
    expect(page.locator("#timeline-view-wrap")).to_be_visible()
    expect(page.locator("#segment-hub-view")).to_be_hidden()

    # Volver al Editor de Segmentos
    page.click("#tab-btn-segment-hub")
    expect(page.locator("#segment-hub-view")).to_be_visible()
    expect(page.locator("#timeline-view-wrap")).to_be_hidden()


def test_e2e_04_collapse_bottom_dock(browser_context):
    """Verifica que al colapsar la barra inferior, el panel derecho se expanda a altura completa."""
    page = browser_context

    # Obtener altura previa del panel derecho
    initial_box = page.locator("#contextual-inspector-zone").bounding_box()
    assert initial_box is not None

    # Hacer clic en el botón de ocultar en la cabecera del dock
    page.click("#btn-collapse-bottom-dock")

    # El contenedor principal adquiere la clase 'bottom-dock-hidden'
    expect(page.locator("#main-workspace")).to_have_class(re.compile(r"bottom-dock-hidden"))

    # El dock y el splitter están ocultos
    expect(page.locator("#bottom-dock-zone")).to_be_hidden()
    expect(page.locator("#horizontal-splitter")).to_be_hidden()

    # La barra comprimida de restauración aparece abajo
    expect(page.locator("#bottom-dock-collapsed-bar")).to_be_visible()

    # El panel derecho se expande verticalmente
    new_box = page.locator("#contextual-inspector-zone").bounding_box()
    assert new_box is not None
    assert new_box["height"] > initial_box["height"] + 150, "El panel derecho debe expandirse verticalmente"

    # Capturar screenshot con el dock colapsado
    screenshot_path = os.path.join(ARTIFACTS_DIR, "playwright_02_dock_collapsed_full_height.png")
    page.screenshot(path=screenshot_path)
    assert os.path.exists(screenshot_path)


def test_e2e_05_subtitles_expanded_in_full_height(browser_context):
    """Verifica que el panel de subtítulos se visualice en toda la altura disponible."""
    page = browser_context

    # Cambiar a la pestaña de subtítulos con el dock colapsado
    page.click("#tab-btn-side-subtitles")
    expect(page.locator("#view-side-subtitles")).to_be_visible()

    # Capturar screenshot del editor de subtítulos a pantalla completa
    screenshot_path = os.path.join(ARTIFACTS_DIR, "playwright_03_subtitles_full_height.png")
    page.screenshot(path=screenshot_path)
    assert os.path.exists(screenshot_path)


def test_e2e_06_restore_bottom_dock_via_expand_button(browser_context):
    """Verifica la restauración del dock inferior mediante el botón de la barra comprimida."""
    page = browser_context

    # Clic en el botón expandir
    page.click("#btn-expand-bottom-dock")

    # El workspace ya no tiene 'bottom-dock-hidden'
    expect(page.locator("#main-workspace")).not_to_have_class(re.compile(r"bottom-dock-hidden"))

    # El dock y el splitter vuelven a estar visibles
    expect(page.locator("#bottom-dock-zone")).to_be_visible()
    expect(page.locator("#horizontal-splitter")).to_be_visible()
    expect(page.locator("#bottom-dock-collapsed-bar")).to_be_hidden()


def test_e2e_07_toggle_via_keyboard_shortcut_b(browser_context):
    """Verifica que pulsar la tecla 'B' alterne la visibilidad del dock inferior."""
    page = browser_context

    # Pulsar 'b' -> Ocultar
    page.keyboard.press("b")
    expect(page.locator("#bottom-dock-zone")).to_be_hidden()
    expect(page.locator("#bottom-dock-collapsed-bar")).to_be_visible()

    # Pulsar 'b' de nuevo -> Restaurar
    page.keyboard.press("b")
    expect(page.locator("#bottom-dock-zone")).to_be_visible()
    expect(page.locator("#bottom-dock-collapsed-bar")).to_be_hidden()


def test_e2e_08_toggle_via_navbar_button(browser_context):
    """Verifica la conmutación mediante el botón de la barra superior (#btn-toggle-bottom-dock)."""
    page = browser_context

    # Clic en el botón de la barra superior -> Ocultar
    page.click("#btn-toggle-bottom-dock")
    expect(page.locator("#bottom-dock-zone")).to_be_hidden()
    expect(page.locator("#btn-toggle-bottom-dock-text")).to_have_text("Mostrar Inferior")

    # Clic de nuevo -> Restaurar
    page.click("#btn-toggle-bottom-dock")
    expect(page.locator("#bottom-dock-zone")).to_be_visible()
    expect(page.locator("#btn-toggle-bottom-dock-text")).to_have_text("Panel Inferior")


def test_e2e_09_settings_modal_shows_b_shortcut(browser_context):
    """Verifica que el diálogo de accesibilidad y atajos documente la tecla 'B'."""
    page = browser_context

    # Abrir modal de configuración
    page.click("#btn-top-settings")
    expect(page.locator("#generic-modal-backdrop")).to_have_class(re.compile(r"open"))

    # Verificar que el atajo 'B' aparece
    modal_body = page.locator("#generic-modal-body")
    expect(modal_body).to_contain_text("Ocultar / Mostrar Barra Inferior")

    # Capturar screenshot del modal
    screenshot_path = os.path.join(ARTIFACTS_DIR, "playwright_04_shortcuts_modal.png")
    page.screenshot(path=screenshot_path)
    assert os.path.exists(screenshot_path)

    # Cerrar modal
    page.click("#generic-modal-close")
    expect(page.locator("#generic-modal-backdrop")).not_to_have_class(re.compile(r"open"))
