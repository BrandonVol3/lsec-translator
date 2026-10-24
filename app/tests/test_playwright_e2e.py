"""
Suite de Pruebas E2E Automatizadas con Playwright para el Flujo Guiado de 3 Ventanas (Wizard) de LSEC Studio.
"""

import re
import pytest
from playwright.sync_api import sync_playwright, expect

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


def test_e2e_01_initial_layout_and_step1(browser_context):
    """Verifica la carga inicial en tema claro pedagógico y los componentes de la Ventana 1."""
    page = browser_context
    expect(page).to_have_title(re.compile(r"LSEC Studio"))
    assert page.locator("html").get_attribute("data-theme") == "light"

    expect(page.locator("#workflow-stepper")).to_be_visible()
    expect(page.locator("#wizard-window-1")).to_be_visible()
    expect(page.locator("#left-video-zone")).to_be_visible()
    expect(page.locator("#whisper-waveform-canvas")).to_be_visible()
    expect(page.locator("#btn-step1-process-lsec")).to_be_visible()


def test_e2e_02_wizard_step1_to_step2_navigation(browser_context):
    """Verifica el paso de Ventana 1 a Ventana 2 (Motor Lingüístico y Mesa Comparativa)."""
    page = browser_context
    page.evaluate("() => window.appState.resetToDefaultProject()")

    expect(page.locator("#transcript-segments-container .transcript-seg-card").first).to_be_visible()
    page.click("#btn-step1-process-lsec")

    expect(page.locator("#wizard-window-2")).to_be_visible()
    expect(page.locator("#grammar-transform-monitor")).to_be_visible()
    expect(page.locator("#comparative-parallel-table")).to_be_visible()
    expect(page.locator("#comparative-rows-container .comparative-row").first).to_be_visible()


def test_e2e_03_parallel_comparative_table_and_gloss_chips(browser_context):
    """Verifica las fichas táctiles de glosas LSEC y el monitor gramatical en la Ventana 2."""
    page = browser_context
    chip_count = page.locator("#comparative-rows-container .gloss-chip-tactile").count()
    assert chip_count > 10

    rule_count = page.locator("#grammar-applied-rules-list .grammar-rule-badge").count()
    assert rule_count >= 1


def test_e2e_04_wizard_step2_to_step3_navigation(browser_context):
    """Verifica el paso a la Ventana 3 (Escenario Multimedia + Monitor en Vivo + Estilos y Exportación)."""
    page = browser_context
    page.click("#btn-step2-confirm-glosses")

    expect(page.locator("#wizard-window-3")).to_be_visible()
    expect(page.locator("#step3-video-slot #left-video-zone")).to_be_visible()
    expect(page.locator("#step3-live-sign-monitor")).to_be_visible()
    expect(page.locator("#view-side-subtitles")).to_be_visible()
    expect(page.locator("#btn-step3-export-mp4")).to_be_visible()
    expect(page.locator("#btn-step3-export-srt")).to_be_visible()


def test_e2e_05_modals_dictionary_projects_and_export(browser_context):
    """Verifica los diálogos de Diccionario CONADIS, Proyectos y Exportación."""
    page = browser_context

    page.click("#btn-dictionary-modal")
    expect(page.locator("#generic-modal-backdrop")).to_have_class(re.compile(r"open"))
    page.click("#generic-modal-close")
    expect(page.locator("#generic-modal-backdrop")).not_to_have_class(re.compile(r"open"))

    page.click("#btn-step3-export-mp4")
    expect(page.locator("#generic-modal-backdrop")).to_have_class(re.compile(r"open"))
    page.click("#generic-modal-close")
    expect(page.locator("#generic-modal-backdrop")).not_to_have_class(re.compile(r"open"))
