"""
Pruebas de Integración y Contratos de API para Endpoints Raíz, UI y Avatar VRM.
Cubre requerimiento R1 de la Auditoría General del Ecosistema LSEC.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    """Fixture de cliente de pruebas para FastAPI con ciclo de vida completo."""
    with TestClient(app) as test_client:
        yield test_client


def test_health_and_hardware_status(client: TestClient):
    """
    Verifica que GET /api/v1/health y GET /api/v1/hardware-status
    respondan HTTP 200 con sus respectivos esquemas esperados.
    """
    health_resp = client.get("/api/v1/health")
    assert health_resp.status_code == 200, f"Health endpoint falló: {health_resp.status_code}"
    health_data = health_resp.json()
    assert health_data.get("status") in ("ok", "degraded")
    assert "services" in health_data
    assert isinstance(health_data["services"], dict)
    assert "nlp" in health_data["services"]
    assert "asr" in health_data["services"]
    assert "storage" in health_data["services"]
    assert "checks" in health_data
    assert "asr_model_loaded" in health_data["checks"]
    assert "storage_persistent" in health_data["checks"]
    assert "version" in health_data

    hw_resp = client.get("/api/v1/hardware-status")
    assert hw_resp.status_code == 200, f"Hardware status falló: {hw_resp.status_code}"
    hw_data = hw_resp.json()
    assert "device" in hw_data or "is_gpu" in hw_data


def test_root_and_studio_ui(client: TestClient):
    """
    Verifica que GET / (con Accept: text/html) y GET /studio
    respondan HTTP 200 y contengan marcado HTML válido de LSEC Studio.
    """
    # GET / por defecto devuelve JSON descriptivo
    json_resp = client.get("/")
    assert json_resp.status_code == 200
    json_data = json_resp.json()
    assert "name" in json_data
    assert "endpoints" in json_data

    # GET / con cabecera Accept text/html sirve la interfaz web
    html_resp = client.get("/", headers={"Accept": "text/html"})
    assert html_resp.status_code == 200
    assert "text/html" in html_resp.headers.get("content-type", "")
    assert "<!DOCTYPE html>" in html_resp.text or "<html" in html_resp.text
    assert "LSEC Studio" in html_resp.text

    # GET /studio sirve la SPA de LSEC Studio
    studio_resp = client.get("/studio")
    assert studio_resp.status_code == 200
    assert "text/html" in studio_resp.headers.get("content-type", "")
    assert "<!DOCTYPE html>" in studio_resp.text or "<html" in studio_resp.text
    assert "LSEC Studio" in studio_resp.text


def test_viewer_and_avatarconfig_ui(client: TestClient):
    """
    Verifica que GET /viewer y GET /avatarconfig
    respondan HTTP 200 y contengan marcado HTML correspondiente.
    """
    viewer_resp = client.get("/viewer")
    assert viewer_resp.status_code == 200
    assert "text/html" in viewer_resp.headers.get("content-type", "")
    assert "<!DOCTYPE html>" in viewer_resp.text or "<html" in viewer_resp.text

    # Alias /reproductor también debe responder 200
    reproductor_resp = client.get("/reproductor")
    assert reproductor_resp.status_code == 200
    assert "text/html" in reproductor_resp.headers.get("content-type", "")

    avatarconfig_resp = client.get("/avatarconfig")
    assert avatarconfig_resp.status_code == 200
    assert "text/html" in avatarconfig_resp.headers.get("content-type", "")
    assert "<!DOCTYPE html>" in avatarconfig_resp.text or "<html" in avatarconfig_resp.text

    # Alias /avatar-config también debe responder 200
    avatar_config_alias = client.get("/avatar-config")
    assert avatar_config_alias.status_code == 200


def test_api_info_and_docs(client: TestClient):
    """
    Verifica que GET /api/info y GET /docs respondan HTTP 200.
    """
    info_resp = client.get("/api/info")
    assert info_resp.status_code == 200
    info_data = info_resp.json()
    assert info_data.get("name") == "LSEC Translator Prototype"
    assert "endpoints" in info_data
    assert info_data["endpoints"].get("studio") == "/studio"
    assert info_data["endpoints"].get("viewer") == "/viewer"
    assert info_data["endpoints"].get("avatar_config") == "/avatarconfig"

    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200
    assert "text/html" in docs_resp.headers.get("content-type", "")

    openapi_resp = client.get("/openapi.json")
    assert openapi_resp.status_code == 200
    openapi_data = openapi_resp.json()
    assert "paths" in openapi_data


def test_active_vrm_avatar_download(client: TestClient):
    """
    Verifica que GET /avatar/LSEC-Interpreter-Female.vrm responda HTTP 200,
    con tamaño superior a 10,000,000 bytes y cabecera binaria glTF / GLB.
    """
    vrm_resp = client.get("/avatar/LSEC-Interpreter-Female.vrm")
    assert vrm_resp.status_code == 200, f"Error descargando avatar VRM: {vrm_resp.status_code}"

    content = vrm_resp.content
    content_len = len(content)
    assert content_len > 10_000_000, f"Tamaño del archivo VRM insuficiente: {content_len} bytes"

    # Los archivos VRM / GLB binarios inician obligatoriamente con el magic header 'glTF' (0x46546C67)
    assert content[:4] == b"glTF", "El archivo descargado no cuenta con cabecera binaria glTF/GLB válida"


def test_animations_and_dictionary_endpoints(client: TestClient):
    """
    Verifica que GET /api/v1/animations/list, GET /api/v1/animations/resolve/HOLA
    y GET /api/v1/dictionary/stats respondan HTTP 200 con datos conformes.
    """
    # 1. Catálogo de animaciones
    anim_list_resp = client.get("/api/v1/animations/list?limit=10")
    assert anim_list_resp.status_code == 200
    anim_data = anim_list_resp.json()
    assert "items" in anim_data
    assert "total" in anim_data
    assert anim_data["total"] >= 4000
    assert len(anim_data["items"]) <= 10

    # 2. Resolución de animación para la glosa HOLA
    resolve_resp = client.get("/api/v1/animations/resolve/HOLA")
    assert resolve_resp.status_code == 200
    resolve_data = resolve_resp.json()
    assert "metadata" in resolve_data or "frames" in resolve_data or "sign" in resolve_data

    # 3. Estadísticas del diccionario oficial LSEC
    dict_stats_resp = client.get("/api/v1/dictionary/stats")
    assert dict_stats_resp.status_code == 200
    dict_stats = dict_stats_resp.json()
    assert dict_stats.get("available") is True
    assert dict_stats.get("total_signs", 0) >= 4000
