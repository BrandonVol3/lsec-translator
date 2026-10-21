"""
Pruebas Automatizadas de Integración — Catálogo LSEC v2.7 Estandarizado (4,142 señas),
Conmutación de Versiones (v2.7 / v2.6 / v2.5) y Controles UI en /studio, /viewer y /avatarconfig.
"""

import json
import unicodedata
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.api.animation_direct_endpoints import (
    _build_v26_lexical_index,
    get_animations_dir,
    get_v25_dir,
    get_v26_dir,
    get_v27_dir,
    resolve_gloss_to_sign,
)


client = TestClient(app)


def test_v27_directories_and_default_source():
    """Verifica que senas_vrm_standardized_v2.7 exista y sea la fuente principal por defecto."""
    v27_dir = get_v27_dir()
    v26_dir = get_v26_dir()
    v25_dir = get_v25_dir()
    default_dir = get_animations_dir()

    assert v27_dir is not None and v27_dir.is_dir()
    assert v27_dir.name == "senas_vrm_standardized_v2.7"
    assert default_dir == v27_dir
    assert v26_dir is not None and v26_dir.is_dir()
    assert v25_dir is not None and v25_dir.is_dir()


def test_v27_lexical_index_counts():
    """Verifica que el índice léxico registre las 4,142 carpetas estandarizadas v2.7 junto con v2.6 y v2.5."""
    idx = _build_v26_lexical_index()
    assert idx["total_v27"] == 4142
    assert idx["unique_v27"] == 4142
    assert idx["total_v26"] == 4142
    assert len(idx["v27_folders"]) == 4142


def test_v27_stats_endpoint():
    """Verifica que /api/v1/animations/stats exponga métricas completas de v2.7, v2.6 y v2.5."""
    resp_default = client.get("/api/v1/animations/stats")
    assert resp_default.status_code == 200
    data_def = resp_default.json()
    assert data_def["total_signs"] == 4142
    assert data_def["active_default_version"] == "2.7"
    assert data_def["version_active"] == "2.7"
    assert data_def["pipeline_version"] == "2.7_Estandarizado"
    assert "senas_vrm_standardized_v2.7" in data_def["directory"]
    assert "v27_stats" in data_def
    v27_stats = data_def["v27_stats"]
    assert v27_stats["available"] is True
    assert v27_stats["total"] == 4142
    assert v27_stats["standardized"] == 3762
    assert v27_stats["skipped"] == 380
    assert v27_stats["version"] == "2.7_Estandarizado"

    resp_v27 = client.get("/api/v1/animations/stats?version=2.7")
    assert resp_v27.status_code == 200
    data_v27 = resp_v27.json()
    assert data_v27["pipeline_version"] == "2.7_Estandarizado"
    assert "senas_vrm_standardized_v2.7" in data_v27["directory"]

    resp_v26 = client.get("/api/v1/animations/stats?version=2.6")
    assert resp_v26.status_code == 200
    data_v26 = resp_v26.json()
    assert data_v26["version_active"] == "2.6"
    assert data_v26["pipeline_version"] == "2.6_Directo_1a1_corregido"
    assert data_v26["directory"] == str(get_v26_dir())

    resp_v25 = client.get("/api/v1/animations/stats?version=2.5")
    assert resp_v25.status_code == 200
    data_v25 = resp_v25.json()
    assert data_v25["version_active"] == "2.5"
    assert data_v25["pipeline_version"] == "2.5_Directo_1a1"
    assert data_v25["directory"] == str(get_v25_dir())


def test_list_animations_version_switching():
    """Verifica que GET /api/v1/animations/list soporte el parámetro version (2.7, 2.6, 2.5)."""
    r_def = client.get("/api/v1/animations/list")
    assert r_def.status_code == 200
    d_def = r_def.json()
    assert d_def["version"] == "2.7"
    assert d_def["pipeline_version"] == "2.7_Estandarizado"
    assert d_def["total"] == 4142

    r_26 = client.get("/api/v1/animations/list?version=2.6")
    assert r_26.status_code == 200
    d_26 = r_26.json()
    assert d_26["version"] == "2.6"
    assert d_26["pipeline_version"] == "2.6_Directo_1a1_corregido"
    assert d_26["total"] == 4142

    r_25 = client.get("/api/v1/animations/list?version=2.5")
    assert r_25.status_code == 200
    d_25 = r_25.json()
    assert d_25["version"] == "2.5"
    assert d_25["pipeline_version"] == "2.5_Directo_1a1"
    assert d_25["total"] > 4000


def test_get_sign_animation_version_switching_and_headers():
    """
    Verifica que GET /api/v1/animations/{sign_name} sirva v2.7 por defecto,
    permita conmutar explícitamente a v2.7, v2.6 y v2.5, y haga fallback limpio ante versiones inválidas.
    """
    # 1. Por defecto (sin parámetro version) -> sirve v2.7
    r_def = client.get("/api/v1/animations/Abanico")
    assert r_def.status_code == 200
    assert r_def.headers.get("x-sign-version") == "2.7"
    assert r_def.headers.get("x-sign-hand-standardization") == "STANDARDIZED"
    assert r_def.headers.get("x-sign-hand-template") == "configuracion_manual_2_v4"
    anim_def = r_def.json()
    assert anim_def["metadata"]["pipelineVersion"] == "2.7_Estandarizado"
    assert anim_def["metadata"]["version_served"] == "2.7"
    hand_std = anim_def.get("metadata", {}).get("handStandardization", {})
    assert hand_std.get("version") == "v2.7"
    assert hand_std.get("status") == "STANDARDIZED"
    assert hand_std.get("template_id") == "configuracion_manual_2_v4"
    assert hand_std.get("frames_modified", 0) == 83
    assert hand_std.get("dominant_hand") == "left"
    assert hand_std.get("bimanual_mode") == "monomanual"
    assert float(hand_std.get("reduction_pct", 0)) > 0

    # 2. Explícito version=2.7 (incluyendo consulta en NFD con tildes)
    nfd_sign = unicodedata.normalize("NFD", "A través, Mediante")
    r_27 = client.get(f"/api/v1/animations/{nfd_sign}?version=2.7")
    assert r_27.status_code == 200
    assert r_27.headers.get("x-sign-version") == "2.7"
    assert r_27.json()["metadata"]["handStandardization"]["version"] == "v2.7"
    assert r_27.json()["metadata"]["pipelineVersion"] == "2.7_Estandarizado"

    # 3. Explícito version=2.6 -> sirve v2.6 sin sobrescribir con v2.7
    r_26 = client.get("/api/v1/animations/Abanico?version=2.6")
    assert r_26.status_code == 200
    assert r_26.headers.get("x-sign-version") == "2.6"
    anim_26 = r_26.json()
    assert anim_26["metadata"]["pipelineVersion"] == "2.6_Directo_1a1_corregido"
    assert anim_26["metadata"]["version_served"] == "2.6"
    assert "handStandardization" not in anim_26["metadata"]

    # 4. Explícito version=2.5 -> sirve v2.5 original
    r_25 = client.get("/api/v1/animations/Abanico?version=2.5")
    assert r_25.status_code == 200
    assert r_25.headers.get("x-sign-version") == "2.5"
    anim_25 = r_25.json()
    assert anim_25["metadata"]["pipelineVersion"] == "2.5_Directo_1a1"
    assert anim_25["metadata"]["version_served"] == "2.5"

    # 5. Versión desconocida (ej. version=9.9) -> fallback seguro a v2.7
    r_invalid = client.get("/api/v1/animations/Abanico?version=9.9")
    assert r_invalid.status_code == 200
    assert r_invalid.headers.get("x-sign-version") == "2.7"


def test_resolve_endpoints_default_to_v27_and_support_all_versions():
    """
    Verifica que GET y POST /api/animations-direct/resolve usen v2.7 por defecto
    y soporten version='2.7', '2.6' y '2.5'.
    """
    # 1. GET resolve por defecto -> v2.7
    r_get = client.get("/api/animations-direct/resolve/ABANICO?include_animation=true")
    assert r_get.status_code == 200
    d_get = r_get.json()
    assert d_get["found"] is True
    assert d_get["version_served"] == "2.7"
    assert d_get["animation"]["metadata"]["pipelineVersion"] == "2.7_Estandarizado"
    assert d_get["animation"]["metadata"]["version_served"] == "2.7"
    assert d_get["animation"]["metadata"]["handStandardization"]["version"] == "v2.7"
    assert d_get["animation"]["metadata"]["handStandardization"]["dominant_hand"] == "left"

    # 2. GET resolve explícito v2.6 y v2.5
    r_get_26 = client.get("/api/animations-direct/resolve/ABANICO?version=2.6&include_animation=false")
    assert r_get_26.status_code == 200
    assert r_get_26.json()["version_served"] == "2.6"

    r_get_25 = client.get("/api/animations-direct/resolve/ABANICO?version=2.5&include_animation=false")
    assert r_get_25.status_code == 200
    assert r_get_25.json()["version_served"] == "2.5"

    # 3. POST resolve en lote por defecto (sin especificar version -> 2.7)
    r_post = client.post(
        "/api/animations-direct/resolve",
        json={"glosses": ["HOLA", "PRO1-PL", "CARRERA", "U-P-E-C"], "include_animation": False},
    )
    assert r_post.status_code == 200
    p_data = r_post.json()
    assert p_data["summary"]["resolved"] == 3
    assert p_data["summary"]["fingerspelling"] == 1
    assert p_data["summary"]["missing"] == 0
    for g in ("HOLA", "PRO1-PL", "CARRERA"):
        assert p_data["results"][g]["version_served"] == "2.7"

    # 4. Función directa resolve_gloss_to_sign por defecto -> 2.7
    direct_res = resolve_gloss_to_sign("UNIVERSIDAD", include_animation=False)
    assert direct_res["found"] is True
    assert direct_res["version_served"] == "2.7"


def test_qa_endpoint_returns_v27_hand_standardization_metrics():
    """Verifica que /api/v1/animations/{sign}/qa devuelva las métricas de estandarización manual v2.7."""
    r_qa = client.get("/api/v1/animations/Abanico/qa?version=2.7")
    assert r_qa.status_code == 200
    qa = r_qa.json()
    assert qa.get("hand_std_status") == "STANDARDIZED"
    assert qa.get("hand_std_dominant_hand") == "left"
    assert qa.get("hand_std_bimanual_mode") == "monomanual"
    assert int(qa.get("frames_modified", 0)) == 83
    assert float(qa.get("distance_after_deg", 999)) < float(qa.get("distance_before_deg", 0))

    # También verificar que sin parámetro version devuelva v2.7 por defecto
    r_qa_def = client.get("/api/v1/animations/Abanico/qa")
    assert r_qa_def.status_code == 200
    assert r_qa_def.json().get("hand_std_status") == "STANDARDIZED"


def test_frontend_ui_version_controls_present():
    """
    Verifica que los controles de versión v2.7 / v2.6 / v2.5 estén integrados
    en /viewer (viewer.html), /studio (avatar-controller.js + avatar-sync-controller.js)
    y /avatarconfig (avatarconfig.html).
    """
    static_dir = Path(__file__).resolve().parents[1] / "static"
    viewer_html = (static_dir / "viewer.html").read_text(encoding="utf-8")
    avatarconfig_html = (static_dir / "avatarconfig.html").read_text(encoding="utf-8")
    avatar_ctrl_js = (static_dir / "js" / "avatar" / "avatar-controller.js").read_text(encoding="utf-8")
    avatar_sync_js = (static_dir / "js" / "avatar" / "avatar-sync-controller.js").read_text(encoding="utf-8")
    schema_js = (static_dir / "js" / "avatar" / "sign-animation-schema.js").read_text(encoding="utf-8")

    # 1. /viewer
    assert 'id="selectVersion"' in viewer_html
    assert '<option value="2.7" selected>' in viewer_html
    assert '<option value="2.6">' in viewer_html
    assert '<option value="2.5">' in viewer_html

    # 2. /studio
    assert 'id="select-avatar-version"' in avatar_ctrl_js
    assert "this.preferredVersion = '2.7'" in avatar_ctrl_js
    assert "setAnimationVersion(" in avatar_ctrl_js
    assert "this.preferredVersion = '2.7'" in avatar_sync_js
    assert "fetchDirectV27Clip" in avatar_sync_js
    assert "standardizedVersion" in schema_js

    # 3. /avatarconfig
    assert 'id="nav-btn-v27"' in avatarconfig_html
    assert 'id="card-btn-v27"' in avatarconfig_html
    assert "let preferredVersion = '2.7'" in avatarconfig_html

    # 4. Rutas HTTP de páginas estáticas sirven el HTML actualizado
    for route in ("/viewer", "/studio", "/avatarconfig"):
        resp = client.get(route)
        assert resp.status_code == 200, f"Fallo al servir ruta {route}"


def test_v27_stroke_index_endpoints_and_resolve_integration():
    """
    Verifica que el índice precalculado de trazos (stroke_index.json de v2.7) cubra las 4,142 señas,
    se exponga en /api/v1/animations/stroke-index y /api/v1/animations/{sign}/stroke,
    y se adjunte exclusivamente cuando version_served == '2.7'.
    """
    # 1. Endpoint global /api/v1/animations/stroke-index
    r_idx = client.get("/api/v1/animations/stroke-index?limit=5000")
    assert r_idx.status_code == 200
    d_idx = r_idx.json()
    assert d_idx["version"] == "2.7"
    assert d_idx["totalSigns"] == 4142
    assert "signs" in d_idx and len(d_idx["signs"]) == 4142
    abanico_stroke = d_idx["signs"].get("Abanico")
    assert abanico_stroke is not None
    assert 0.0 <= abanico_stroke["strokeStart"] < abanico_stroke["strokeEnd"] <= abanico_stroke["originalDuration"] + 0.01
    assert abanico_stroke["strokeDuration"] > 0.1
    assert "activeHands" in abanico_stroke and "flags" in abanico_stroke

    # 2. Endpoint individual /api/v1/animations/{sign}/stroke
    r_single = client.get("/api/v1/animations/Abanico/stroke")
    assert r_single.status_code == 200
    d_single = r_single.json()
    assert d_single["sign"] == "Abanico"
    assert d_single["strokeStart"] == abanico_stroke["strokeStart"]
    assert d_single["strokeEnd"] == abanico_stroke["strokeEnd"]

    # Seña inexistente en /stroke -> 404
    r_404 = client.get("/api/v1/animations/SENA_INEXISTENTE_XYZ_999/stroke")
    assert r_404.status_code == 404

    # 3. GET /api/v1/animations/{sign} adjunta metadata.stroke solo en v2.7
    r_anim_27 = client.get("/api/v1/animations/Abanico?version=2.7")
    assert r_anim_27.status_code == 200
    meta_27 = r_anim_27.json().get("metadata", {})
    assert "stroke" in meta_27
    assert meta_27["stroke"]["strokeStart"] == abanico_stroke["strokeStart"]

    r_anim_26 = client.get("/api/v1/animations/Abanico?version=2.6")
    assert r_anim_26.status_code == 200
    meta_26 = r_anim_26.json().get("metadata", {})
    assert "stroke" not in meta_26

    # 4. GET y POST /api/animations-direct/resolve incluyen 'stroke' para v2.7
    r_res = client.get("/api/animations-direct/resolve/UNIVERSIDAD?include_animation=true")
    assert r_res.status_code == 200
    d_res = r_res.json()
    assert d_res["version_served"] == "2.7"
    assert isinstance(d_res.get("stroke"), dict)
    assert isinstance(d_res["animation"]["metadata"].get("stroke"), dict)


def test_fluid_sequence_compiler_frontend_wiring():
    """
    Verifica que SequenceCompiler, el tope 1.6x, el umbral de 1.5s y la extensión del PiP
    estén conectados en los módulos frontend de LSEC Studio.
    """
    static_js = Path(__file__).resolve().parents[1] / "static" / "js"
    seq_compiler = (static_js / "avatar" / "sequence-compiler.js").read_text(encoding="utf-8")
    bridge_js = (static_js / "avatar" / "studio-avatar-bridge.js").read_text(encoding="utf-8")
    exporter_js = (static_js / "components" / "video-exporter.js").read_text(encoding="utf-8")
    overlay_js = (static_js / "components" / "gloss-overlay.js").read_text(encoding="utf-8")

    assert "export class SequenceCompiler" in seq_compiler
    assert "interpolateSO3HermiteC1" in seq_compiler
    assert "maxSpeed: 1.6" in seq_compiler
    assert "restGapThresholdSec: 1.5" in seq_compiler
    assert "SequenceCompiler" in bridge_js
    assert "getSequenceEndTime" in bridge_js
    assert "getSequenceEndTime" in exporter_js
    assert "lastSampleResult" in overlay_js

