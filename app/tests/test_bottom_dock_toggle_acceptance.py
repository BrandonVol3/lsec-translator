"""
Suite de Pruebas de Aceptación: Ocultar/Mostrar Barra Inferior (Editor de Segmentos y Línea de Tiempo).

Verifica los criterios de aceptación:
1. Existencia y accesibilidad de los controles HTML (barra superior, cabecera del dock y barra colapsada).
2. Reglas CSS para colapsar dock y splitter, expandiendo el panel derecho (transcripción, inspector, subtítulos) al 100% de la altura.
3. Métodos y reactividad en StateStore (toggleBottomDock, setBottomDockCollapsed, evento bottomDockToggled).
4. Coordinador app.js con preservación de altura redimensionada y restauración al descolapsar.
5. Atajo de teclado 'b'/'B' para conmutar visibilidad sin interferir con inputs de texto.
6. Registro del atajo 'B' en el modal de accesibilidad y configuración.
"""

import os
import re
import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX_HTML_PATH = os.path.join(PROJECT_ROOT, "app", "static", "index.html")
APP_CSS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "css", "app.css")
STATE_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "state.js")
APP_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "app.js")
MODALS_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "components", "modals-and-export.js")


@pytest.fixture(scope="module")
def html_content():
    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def css_content():
    with open(APP_CSS_PATH, "r", encoding="utf-8") as f:
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


def test_ac1_html_toggle_elements_exist(html_content):
    """AC1: Los elementos HTML para alternar la barra inferior están presentes con semántica accesible."""
    # 1. Botón en la barra superior
    assert 'id="btn-toggle-bottom-dock"' in html_content
    assert 'id="btn-toggle-bottom-dock-text"' in html_content
    assert "Panel Inferior" in html_content

    # 2. Botón de minimizar/ocultar en la cabecera del dock inferior
    assert 'id="btn-collapse-bottom-dock"' in html_content
    assert "Ocultar" in html_content

    # 3. Barra comprimida y botón de restaurar/expandir cuando el dock está oculto
    assert 'id="bottom-dock-collapsed-bar"' in html_content
    assert 'id="btn-expand-bottom-dock"' in html_content
    assert "Mostrar Editor de Segmentos y Línea de Tiempo" in html_content


def test_ac2_css_layout_expansion_rules(css_content):
    """AC2: El CSS oculta dock y splitter y expande el contenedor superior y el panel derecho al 100% de la altura."""
    # Ocultar el dock inferior
    assert "#main-workspace.bottom-dock-hidden #bottom-dock-zone" in css_content
    assert "display: none !important;" in css_content

    # Ocultar el splitter horizontal
    assert "#main-workspace.bottom-dock-hidden #horizontal-splitter" in css_content

    # Expansión de altura completa para el contenedor de video y el panel derecho
    assert "#main-workspace.bottom-dock-hidden #top-split-container" in css_content
    assert "#main-workspace.bottom-dock-hidden #contextual-inspector-zone" in css_content
    assert "height: 100% !important;" in css_content

    # Estilos de la barra comprimida
    assert ".dock-collapsed-bar" in css_content
    assert ".btn-expand-dock" in css_content


def test_ac3_state_store_contract(state_js_content):
    """AC3: state.js incluye estado reactivo y métodos para conmutar la barra inferior."""
    # Variable de estado en workspace
    assert "bottomDockCollapsed: false" in state_js_content

    # Método toggleBottomDock
    assert "toggleBottomDock()" in state_js_content
    assert "this.setBottomDockCollapsed(!this.state.workspace.bottomDockCollapsed)" in state_js_content

    # Método setBottomDockCollapsed y emisión del evento bottomDockToggled
    assert "setBottomDockCollapsed(collapsed)" in state_js_content
    assert "bottomDockToggled" in state_js_content


def test_ac4_app_js_coordination_and_height_preservation(app_js_content):
    """AC4: app.js inicializa el controlador, gestiona el DOM y preserva la altura previa del dock."""
    # Inicialización en DOMContentLoaded
    assert "initBottomDockToggle()" in app_js_content

    # Definición de la función
    assert "function initBottomDockToggle()" in app_js_content
    assert "bottom-dock-hidden" in app_js_content

    # Preservación de altura guardada
    assert "savedHeight" in app_js_content

    # Suscripción a eventos
    assert "appState.subscribe('bottomDockToggled'" in app_js_content


def test_ac5_keyboard_shortcut_b(app_js_content):
    """AC5: El atajo 'b'/'B' conmuta la visibilidad del dock inferior respetando campos de texto activos."""
    assert "e.key === 'b' || e.key === 'B'" in app_js_content
    assert "appState.toggleBottomDock()" in app_js_content


def test_ac6_settings_modal_shortcut_documentation(modals_js_content):
    """AC6: El modal de configuración y accesibilidad documenta el atajo 'B'."""
    assert ">B</kbd> Ocultar / Mostrar Barra Inferior" in modals_js_content
