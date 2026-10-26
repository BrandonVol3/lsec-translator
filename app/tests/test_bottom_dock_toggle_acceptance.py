"""
Suite de Pruebas de Aceptación: Limpieza de Línea de Tiempo Multipista (Bottom Dock) y Estructura Wizard de 3 Ventanas.

Verifica:
1. Eliminación del antiguo bottom-dock multipista en index.html en favor de las 3 ventanas independientes del Wizard.
2. Reglas CSS de layout para las 3 ventanas independientes (.wizard-window, .wizard-step1-grid, .wizard-step2-layout, .wizard-step3-grid).
3. Contrato retrocompatible en StateStore (state.js).
4. Coordinador app.js con acoplamiento dinámico del reproductor de video entre Ventana 1 y Ventana 3.
5. Navegación fluida entre las 3 ventanas sin recarga.
6. Modal de exportación y configuración accesible en modals-and-export.js.
"""

import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX_HTML_PATH = os.path.join(PROJECT_ROOT, "app", "static", "index.html")
LAYOUT_CSS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "css", "layout-workspace.css")
STATE_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "state.js")
APP_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "app.js")
MODALS_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "components", "modals-and-export.js")


@pytest.fixture(scope="module")
def html_content():
    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def css_content():
    with open(LAYOUT_CSS_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def state_js_content():
    with open(STATE_JS_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def app_js_content():
    with open(APP_JS_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def modals_js_content():
    with open(MODALS_JS_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_ac1_html_wizard_windows_replace_bottom_dock(html_content):
    """AC1: El antiguo bottom-dock multipista fue reemplazado por las 3 ventanas independientes del Wizard."""
    assert 'id="bottom-dock-zone"' not in html_content
    assert 'src="/static/js/components/timeline.js"' not in html_content
    assert 'id="wizard-window-1"' in html_content
    assert 'id="wizard-window-2"' in html_content
    assert 'id="wizard-window-3"' in html_content


def test_ac2_css_layout_expansion_rules(css_content):
    """AC2: layout-workspace.css define las grillas de las 3 ventanas del Wizard a pantalla completa."""
    assert ".wizard-window" in css_content
    assert ".wizard-window.active" in css_content
    assert ".wizard-step1-grid" in css_content
    assert ".wizard-step2-layout" in css_content
    assert ".wizard-step3-grid" in css_content


def test_ac3_state_store_contract(state_js_content):
    """AC3: state.js mantiene el contrato de workspace y sincronización por tiempo."""
    assert "bottomDockCollapsed: false" in state_js_content
    assert "toggleBottomDock()" in state_js_content
    assert "setBottomDockCollapsed(collapsed)" in state_js_content


def test_ac4_app_js_coordination_and_video_docking(app_js_content):
    """AC4: app.js coordina el cambio de ventana y acopla el reproductor de video entre Ventana 1 y Ventana 3."""
    assert "dockVideoZoneForStep" in app_js_content
    assert "step1-video-slot" in app_js_content
    assert "step3-video-slot" in app_js_content


def test_ac5_wizard_step_switching(app_js_content):
    """AC5: app.js expone switchWizardStep para navegar entre las 4 ventanas (preparar, traducir, avatar, revisar)."""
    assert "window.switchWizardStep" in app_js_content
    assert "STEP_ORDER = ['preparar', 'traducir', 'avatar', 'revisar']" in app_js_content


def test_ac6_modals_and_export_dialogs(modals_js_content):
    """AC6: modals-and-export.js incluye exportación de video compuesto MP4 y subtítulos SRT."""
    assert "openCompositeVideoExportDialog" in modals_js_content
    assert "downloadSRT" in modals_js_content
