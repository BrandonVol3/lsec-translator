"""
Suite de Pruebas de Aceptación: Flujo Secuencial y Bloqueo Progresivo de Etapas en LSEC Studio.

Verifica:
1. Bloqueo inicial antes de cargar video (Etapas 1, 2 y 3 bloqueadas con candado, exportación deshabilitada).
2. Stepper Bar y Empty State interactivo en index.html.
3. Métodos y reactividad de estado en state.js (canAccessStage, canExport, markTranscriptionReady, markTranslationReady, etc.).
4. Desacoplamiento del pipeline en pipeline-processor.js (Fase 1: Transcripción / Fase 2: Glosas LSEC).
5. Orquestación y toasts de bloqueo en app.js.
6. Estilos CSS para etapas bloqueadas, stepper y empty state.
"""

import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX_HTML_PATH = os.path.join(PROJECT_ROOT, "app", "static", "index.html")
APP_CSS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "css", "app.css")
STATE_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "state.js")
APP_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "app.js")
PIPELINE_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "components", "pipeline-processor.js")
TRANSCRIPT_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "components", "transcript-window.js")


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
def pipeline_js_content():
    with open(PIPELINE_JS_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def transcript_js_content():
    with open(TRANSCRIPT_JS_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_ac1_initial_locked_html_elements(html_content):
    """AC1: Los botones de etapa están inicialmente bloqueados con candado y exportar deshabilitado."""
    assert 'id="stage-btn-preparar"' in html_content
    assert 'id="stage-btn-traducir"' in html_content
    assert 'id="stage-btn-revisar"' in html_content
    assert 'stage-locked' in html_content
    assert 'lock-icon-preparar' in html_content
    assert 'lock-icon-traducir' in html_content
    assert 'lock-icon-revisar' in html_content

    # Botón exportar deshabilitado inicialmente
    assert 'id="btn-top-export"' in html_content
    assert 'disabled' in html_content


def test_ac2_workflow_stepper_and_empty_state_exist(html_content):
    """AC2: La barra Stepper de progreso y el Empty State del video existen con sus IDs."""
    assert 'id="workflow-stepper-bar"' in html_content
    assert 'id="step-node-video"' in html_content
    assert 'id="step-node-prep"' in html_content
    assert 'id="step-node-trans"' in html_content
    assert 'id="step-node-rev"' in html_content
    assert 'id="btn-step-action"' in html_content
    assert 'id="btn-step-action-text"' in html_content

    # Empty State dentro del visor de video
    assert 'id="video-empty-state"' in html_content
    assert 'id="btn-empty-load-video"' in html_content
    assert 'id="btn-empty-load-upec"' not in html_content

    # Toast container
    assert 'id="toast-container"' in html_content


def test_ac3_state_store_sequential_gating(state_js_content):
    """AC3: state.js implementa banderas y métodos para acceso secuencial y validación."""
    assert "videoLoaded: false" in state_js_content
    assert "transcriptionReady: false" in state_js_content
    assert "translationReady: false" in state_js_content
    assert "translationConfirmed: false" in state_js_content
    assert "workflowStep: 'no_video'" in state_js_content

    # Métodos de validación
    assert "canAccessStage(stage)" in state_js_content
    assert "canExport()" in state_js_content
    assert "getStageBlockReason(stage)" in state_js_content
    assert "markTranscriptionReady()" in state_js_content
    assert "markTranslationReady()" in state_js_content
    assert "markTranslationReviewStep()" in state_js_content
    assert "markTranslationConfirmed()" in state_js_content
    assert "invalidateTranslation()" in state_js_content


def test_ac4_pipeline_processor_decoupled_phases(pipeline_js_content):
    """AC4: pipeline-processor.js divide el trabajo en Fase 1 (Transcripción) y Fase 2 (Glosas)."""
    assert "buildTranscriptionProjectStructure" in pipeline_js_content
    assert "translateProjectGlosses()" in pipeline_js_content
    assert "performGlossesTranslation" in pipeline_js_content
    assert "generateGlossesFromText" in pipeline_js_content
    assert "markTranscriptionReady()" in pipeline_js_content
    assert "markTranslationReady()" in pipeline_js_content


def test_ac5_app_orchestrator_sequential_updates(app_js_content):
    """AC5: app.js actualiza la interfaz reactivamente según el paso activo y restringe atajos."""
    assert "updateWorkflowUI()" in app_js_content
    assert "showToast(" in app_js_content
    assert "stageBlocked" in app_js_content
    assert "btn-empty-load-video" in app_js_content
    assert "btn-empty-load-upec" not in app_js_content
    assert "btn-step-action" in app_js_content


def test_ac6_css_rules_for_sequential_flow(css_content):
    """AC6: app.css define clases para botones bloqueados, stepper, empty state y toasts."""
    assert ".stage-btn.stage-locked" in css_content
    assert ".workflow-stepper-container" in css_content
    assert ".stepper-step.active" in css_content
    assert ".stepper-step.completed" in css_content
    assert ".stepper-step.locked" in css_content
    assert ".btn-action-step" in css_content
    assert ".video-empty-overlay" in css_content
    assert ".app-toast" in css_content


def test_ac7_transcript_shows_pending_glosses(transcript_js_content):
    """AC7: transcript-window.js muestra badge de glosas pendientes y reactividad al editar."""
    assert "gloss-pending-badge" in transcript_js_content
    assert "invalidateTranslation()" in transcript_js_content
