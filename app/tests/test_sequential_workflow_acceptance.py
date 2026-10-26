"""
Suite de Pruebas de Aceptación: Flujo Secuencial Guiado en 3 Ventanas (Wizard) en LSEC Studio.

Verifica:
1. Stepper superior con las 3 ventanas independientes (1. Transcripción con Whisper, 2. Motor Lingüístico y Glosas LSEC, 3. Vista Previa del Avatar y Exportación).
2. Ventana 1 (Extractor acústico Whisper ASR + lista de segmentos editables + CTA hacia Ventana 2).
3. Métodos y reactividad de estado en state.js.
4. Desacoplamiento del pipeline en pipeline-processor.js (Fase 1: Transcripción / Fase 2: Glosas LSEC).
5. Coordinación Wizard en app.js (switchWizardStep, docking de #left-video-zone entre Ventana 1 y Ventana 3).
6. Tokens y estilos CSS del sistema de diseño «Pedagogical Tactile Light».
7. Ventana 2 (Monitor Visual de Transformación Gramatical + Mesa Comparativa Paralela de 2 Columnas).
"""

import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX_HTML_PATH = os.path.join(PROJECT_ROOT, "app", "static", "index.html")
TOKENS_CSS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "css", "base-tokens.css")
LAYOUT_CSS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "css", "layout-workspace.css")
STATE_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "state.js")
APP_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "app.js")
PIPELINE_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "components", "pipeline-processor.js")
TRANSCRIPT_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "components", "transcript-window.js")
COMPARISON_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "components", "linguistic-comparison-view.js")


@pytest.fixture(scope="module")
def html_content():
    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def css_content():
    with open(TOKENS_CSS_PATH, "r", encoding="utf-8") as f1, open(LAYOUT_CSS_PATH, "r", encoding="utf-8") as f2:
        return f1.read() + "\n" + f2.read()


@pytest.fixture(scope="module")
def state_js_content():
    with open(STATE_JS_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def app_js_content():
    with open(APP_JS_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def pipeline_js_content():
    with open(PIPELINE_JS_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def transcript_js_content():
    with open(TRANSCRIPT_JS_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def comparison_js_content():
    with open(COMPARISON_JS_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_ac1_wizard_stepper_and_3_windows_exist(html_content):
    """AC1: El Stepper superior y las 3 ventanas independientes del Wizard existen en index.html."""
    assert 'id="workflow-stepper"' in html_content
    assert 'id="step-btn-preparar"' in html_content
    assert 'id="step-btn-traducir"' in html_content
    assert 'id="step-btn-revisar"' in html_content

    assert 'id="wizard-window-1"' in html_content
    assert 'id="wizard-window-2"' in html_content
    assert 'id="wizard-window-3"' in html_content

    # Ocultación de enlaces técnicos /avatarconfig y /viewer en la barra superior
    assert 'href="/avatarconfig"' not in html_content
    assert 'href="/viewer"' not in html_content


def test_ac2_window1_whisper_and_window3_export_controls_exist(html_content, pipeline_js_content):
    """AC2: Ventana 1 tiene segmentos y CTA; pipeline-processor tiene visualizador Whisper fullscreen; Ventanas 3 y 4 tienen Avatar, estilos y exportación."""
    assert 'id="whisper-waveform-canvas"' in pipeline_js_content
    assert 'id="transcript-segments-container"' in html_content
    assert 'id="btn-step1-process-lsec"' in html_content
    assert 'id="grammar-transform-monitor"' in html_content
    assert 'id="comparative-parallel-table"' in html_content
    assert 'id="btn-step2-confirm-glosses"' in html_content
    assert 'id="step3-live-sign-monitor"' in html_content
    assert 'id="view-side-subtitles"' in html_content
    assert 'id="btn-step3-export-mp4"' in html_content
    assert 'id="btn-step3-export-srt"' in html_content
    assert 'id="toast-container"' in html_content


def test_ac3_state_store_sequential_gating(state_js_content):
    """AC3: state.js implementa banderas y métodos para acceso secuencial y validación."""
    assert "videoLoaded: false" in state_js_content
    assert "transcriptionReady: false" in state_js_content
    assert "translationReady: false" in state_js_content
    assert "translationConfirmed: false" in state_js_content
    assert "workflowStep: 'no_video'" in state_js_content
    assert "canAccessStage(stage)" in state_js_content
    assert "canExport()" in state_js_content
    assert "markTranscriptionReady()" in state_js_content
    assert "markTranslationReady()" in state_js_content


def test_ac4_pipeline_processor_decoupled_phases(pipeline_js_content):
    """AC4: pipeline-processor.js divide el trabajo en Fase 1 (Transcripción) y Fase 2 (Glosas)."""
    assert "buildTranscriptionProjectStructure" in pipeline_js_content
    assert "translateProjectGlosses()" in pipeline_js_content
    assert "performGlossesTranslation" in pipeline_js_content
    assert "generateGlossesFromText" in pipeline_js_content
    assert "markTranscriptionReady()" in pipeline_js_content
    assert "markTranslationReady()" in pipeline_js_content


def test_ac5_app_orchestrator_wizard_navigation(app_js_content):
    """AC5: app.js coordina las 3 ventanas del Wizard y acopla el reproductor de video entre Paso 1 y Paso 3."""
    assert "switchWizardStep" in app_js_content
    assert "dockVideoZoneForStep" in app_js_content
    assert "renderStep3LiveSignMonitor" in app_js_content
    assert "showToast" in app_js_content


def test_ac6_css_rules_for_pedagogical_tactile_light(css_content):
    """AC6: base-tokens.css y layout-workspace.css definen los tokens «Pedagogical Tactile Light» (UPEC) y el layout de 4 pasos."""
    assert "--color-canvas-bg:" in css_content
    assert "--color-card-white: #ffffff" in css_content
    assert "--color-primary-emerald:" in css_content
    assert "--color-accent-cobalt:" in css_content
    assert ".workflow-stepper" in css_content
    assert ".wizard-window" in css_content


def test_ac7_transcript_and_comparison_controllers(transcript_js_content, comparison_js_content):
    """AC7: transcript-window.js y linguistic-comparison-view.js implementan edición in-situ y fichas táctiles."""
    assert "drawWaveform" in transcript_js_content
    assert "transcript-seg-card" in transcript_js_content
    assert "renderGrammarMonitor" in comparison_js_content
    assert "renderParallelRows" in comparison_js_content
    assert "retranslateSingleRow" in comparison_js_content
    assert "gloss-chip-conadis" in comparison_js_content
    assert "gloss-chip-fingerspell" in comparison_js_content
    assert "gloss-chip-edited" in comparison_js_content
