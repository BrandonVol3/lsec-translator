"""
Suite de Pruebas Automatizadas — Motor de Dactilología LSEC (30 Señas Oficiales)

Verifica:
1. Los 30 grafemas de Guia-Uso-ilustraciones.pdf (Página 10) en backend y frontend.
2. Tokenización lingüística NFC con detección prioritaria de dígrafos (CH, LL, RR),
   preservación de Ñ, vocales tildadas/diéresis y micro-rearticulación en letras repetidas.
3. Síntesis de animación VRM 1.0 sobre los 54 huesos humanoides, sin inversiones de
   muñeca (>= 55°) y con margen anti-colisión >= 2 cm respecto al pecho.
4. Endpoints REST (/api/v1/animations/fingerspelling/catalog, /fingerspelling/{text}
   y /api/animations-direct/resolve/{gloss}).
5. Ejecución íntegra de la suite Node.js `app/tests/test_lsec_fingerspelling.mjs`.
6. Regla estricta de modularidad (<= 800 líneas de código por archivo modificado o creado).
"""

from __future__ import annotations

import math
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.schemas import GlossItem, GlossType
from app.main import app
from app.services.animation_fingerspelling_service import (
    DYNAMIC_GRAPHEMES,
    HUMAN_54_BONES,
    LSEC_FINGERSPELLING_GRAPHEMES,
    MIN_CHEST_CLEARANCE_M,
    STATIC_GRAPHEMES,
    build_fingerspelling_catalog_payload,
    count_lsec_fingerspelling_graphemes,
    format_lsec_fingerspelling_gloss,
    get_baked_fingerspelling_folder,
    is_fingerspelling_query,
    load_baked_grapheme_animation,
    synthesize_fingerspelling_animation,
    tokenize_lsec_fingerspelling,
)
from app.services.discourse_planner import DiscoursePlanner
from app.services.nlp_service import get_nlp_service

client = TestClient(app)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _quat_angle_deg(q1: list[float], q2: list[float]) -> float:
    dot = abs(sum(float(a) * float(b) for a, b in zip(q1, q2)))
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(2.0 * math.acos(dot))


def test_01_catalog_30_graphemes_static_vs_dynamic():
    """Verifica que el catálogo contenga las 30 señas exactas de la Página 10 del PDF."""
    assert len(LSEC_FINGERSPELLING_GRAPHEMES) == 30
    assert len(STATIC_GRAPHEMES) == 18
    assert len(DYNAMIC_GRAPHEMES) == 12
    assert STATIC_GRAPHEMES.isdisjoint(DYNAMIC_GRAPHEMES)
    assert STATIC_GRAPHEMES | DYNAMIC_GRAPHEMES == set(LSEC_FINGERSPELLING_GRAPHEMES)

    payload = build_fingerspelling_catalog_payload()
    assert payload["total_graphemes"] == 30
    assert payload["min_chest_clearance_m"] >= 0.02


def test_02_tokenizer_digraphs_nfc_and_repeated_letters():
    """Verifica detección de CH, LL, RR, Ñ, vocales tildadas NFC/NFD y micro-rearticulación."""
    # Palabras y siglas oficiales solicitadas
    for word, expected in (
        ("TULCÁN", ["T", "U", "L", "C", "A", "N"]),
        ("T-U-L-C-Á-N", ["T", "U", "L", "C", "A", "N"]),
        ("CAYAMBE", ["C", "A", "Y", "A", "M", "B", "E"]),
        ("U-P-E-C", ["U", "P", "E", "C"]),
        ("CONADIS", ["C", "O", "N", "A", "D", "I", "S"]),
        ("FENASEC", ["F", "E", "N", "A", "S", "E", "C"]),
        ("CHOTA", ["CH", "O", "T", "A"]),
        ("LLANO", ["LL", "A", "N", "O"]),
        ("IBARRA", ["I", "B", "A", "RR", "A"]),
        ("NIÑO", ["N", "I", "Ñ", "O"]),
    ):
        tokens = tokenize_lsec_fingerspelling(word)
        assert [t["grapheme"] for t in tokens] == expected

    # Verificar que en NFD también preserve display_char en NFC y mapee la pose vocal base
    nfd_input = unicodedata.normalize("NFD", "TULCÁN-NIÑO-CIGÜEÑA")
    tok_nfd = tokenize_lsec_fingerspelling(nfd_input)
    graphemes = [t["grapheme"] for t in tok_nfd]
    displays = [t["display_char"] for t in tok_nfd]
    assert "Ñ" in graphemes
    assert "Á" in displays and "Ü" in displays

    # Verificar micro-rearticulación en letras idénticas consecutivas que no sean LL ni RR
    tok_coop = tokenize_lsec_fingerspelling("COOPERATIVA")
    assert tok_coop[1]["grapheme"] == "O" and tok_coop[2]["grapheme"] == "O"
    assert tok_coop[1]["micro_rearticulation"] is False
    assert tok_coop[2]["micro_rearticulation"] is True


def test_03_backend_synthesis_54_bones_and_no_wrist_flips():
    """Verifica que los 30 grafemas y palabras generen 54 huesos VRM sin giros >= 55°."""
    for g in LSEC_FINGERSPELLING_GRAPHEMES:
        assert is_fingerspelling_query(g) is True
        anim = synthesize_fingerspelling_animation(g, fps=30)
        assert anim["metadata"]["isFingerspelling"] is True
        assert anim["metadata"]["minChestClearanceM"] >= MIN_CHEST_CLEARANCE_M
        frames = anim["frames"]
        assert len(frames) >= 15
        for f in frames:
            assert set(f["rotations"].keys()) == set(HUMAN_54_BONES)
        for idx in range(1, len(frames)):
            q_prev = frames[idx - 1]["rotations"]["rightHand"]
            q_curr = frames[idx]["rotations"]["rightHand"]
            assert _quat_angle_deg(q_prev, q_curr) < 55.0


def test_04_rest_endpoints_and_resolver_integration():
    """Verifica la resolución desde /api/v1/animations/fingerspelling/* y /resolve/*."""
    r_cat = client.get("/api/v1/animations/fingerspelling/catalog")
    assert r_cat.status_code == 200
    assert r_cat.json()["total_graphemes"] == 30

    r_word = client.get("/api/v1/animations/fingerspelling/T-U-L-C-%C3%81-N")
    assert r_word.status_code == 200
    d_word = r_word.json()
    assert d_word["metadata"]["graphemes"] == ["T", "U", "L", "C", "A", "N"]
    assert d_word["metadata"]["displayChars"] == ["T", "U", "L", "C", "Á", "N"]
    assert len(d_word["frames"]) >= 15

    # Resolución vía /api/animations-direct/resolve/{gloss} con include_animation=true
    r_res = client.get("/api/animations-direct/resolve/U-P-E-C?include_animation=true")
    assert r_res.status_code == 200
    d_res = r_res.json()
    assert d_res["found"] is False
    assert d_res["is_fingerspelling"] is True
    assert d_res["match_type"] == "fingerspelling"
    assert d_res["graphemes"] == ["U", "P", "E", "C"]
    assert d_res["animation"] is not None
    assert d_res["animation"]["metadata"]["isFingerspelling"] is True


def test_05_frontend_node_fingerspelling_suite():
    """Ejecuta la suite Node.js test_lsec_fingerspelling.mjs."""
    node_bin = shutil.which("node")
    assert node_bin is not None, "Node.js es requerido para ejecutar test_lsec_fingerspelling.mjs"
    script = REPO_ROOT / "app" / "tests" / "test_lsec_fingerspelling.mjs"
    res = subprocess.run(
        [node_bin, str(script)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert res.returncode == 0, f"Fallo en test_lsec_fingerspelling.mjs:\n{res.stdout}\n{res.stderr}"
    assert "TODOS LOS TESTS DE DACTILOLOGÍA LSEC (30 SEÑAS) PASARON SATISFACTORIAMENTE" in res.stdout


def test_06_nlp_sentence_integration_propn_acronyms_and_oov():
    """
    Verifica la integración del motor NLP (`nlp_service.py`, `discourse_gloss_emitter.py`,
    `discourse_planner.py`) para que nombres propios (con dígrafos CH, LL, RR y Ñ),
    siglas y palabras fuera del vocabulario (OOV) se deletreen automáticamente en oraciones completas.
    """
    # 1. Formateo y conteo de grafemas con preservación de dígrafos oficiales (CH, LL, RR) y Ñ
    assert format_lsec_fingerspelling_gloss("Chimborazo") == "CH-I-M-B-O-R-A-Z-O"
    assert count_lsec_fingerspelling_graphemes("CH-I-M-B-O-R-A-Z-O") == 9
    assert format_lsec_fingerspelling_gloss("Llacao") == "LL-A-C-A-O"
    assert count_lsec_fingerspelling_graphemes("LL-A-C-A-O") == 5
    assert format_lsec_fingerspelling_gloss("Ferrocarril") == "F-E-RR-O-C-A-RR-I-L"
    assert count_lsec_fingerspelling_graphemes("F-E-RR-O-C-A-RR-I-L") == 9
    assert format_lsec_fingerspelling_gloss("Rumiñahui") == "R-U-M-I-Ñ-A-H-U-I"
    assert format_lsec_fingerspelling_gloss("Tulcán") == "T-U-L-C-Á-N"

    # 2. Traducción de oración completa con nombres propios (con CH, LL, Ñ), campus y siglas (UPEC, SENESCYT)
    import asyncio
    nlp_svc = get_nlp_service()
    sentence = "Yo estudio en la UPEC de Tulcán y Chordeleg con beca de la SENESCYT."
    out = asyncio.run(nlp_svc.translate_to_gloss(sentence, mode="detailed"))
    by_gloss = {g.gloss: g for g in out.glosses}

    assert "U-P-E-C" in by_gloss
    assert by_gloss["U-P-E-C"].gloss_type == GlossType.FINGERSPELLING
    assert "T-U-L-C-Á-N" in by_gloss
    assert by_gloss["T-U-L-C-Á-N"].gloss_type == GlossType.FINGERSPELLING
    assert "CH-O-R-D-E-L-E-G" in by_gloss
    assert by_gloss["CH-O-R-D-E-L-E-G"].gloss_type == GlossType.FINGERSPELLING
    assert by_gloss["CH-O-R-D-E-L-E-G"].validation["fingerspelling_graphemes"][0] == "CH"
    assert "S-E-N-E-S-C-Y-T" in by_gloss
    assert by_gloss["S-E-N-E-S-C-Y-T"].gloss_type == GlossType.FINGERSPELLING

    # 3. Verificar que palabras OOV reciban fallback_fingerspelling_gloss y promoción directa con fingerspell_oov=True
    planner_oov = DiscoursePlanner(fingerspell_oov=True)
    oov_item = GlossItem(gloss="CIBERSEGURIDAD", gloss_type=GlossType.SIGN, order=0, source_word="ciberseguridad", normalized_word="ciberseguridad")
    planner_oov.apply_dictionary([oov_item])
    if oov_item.dictionary_metadata is not None:
        assert oov_item.gloss == "C-I-B-E-R-S-E-G-U-R-I-D-A-D"
        assert oov_item.gloss_type == GlossType.FINGERSPELLING
        assert oov_item.validation["fallback_fingerspelling_gloss"] == "C-I-B-E-R-S-E-G-U-R-I-D-A-D"


def test_07_v27_baked_files_on_disk_and_stroke_index():
    """
    Verifica que los 30 grafemas estén físicamente horneados como archivos animation.json e info.json
    en el catálogo v2.7 en disco y registrados en stroke_index_v27.json sin alterar el invariante de 4,142 señas léxicas.
    """
    for g in LSEC_FINGERSPELLING_GRAPHEMES:
        folder = get_baked_fingerspelling_folder(g)
        assert folder is not None and folder.is_dir(), f"Falta carpeta horneada v2.7 para {g}"
        assert (folder / "animation.json").is_file(), f"Falta animation.json horneado para {g}"
        assert (folder / "info.json").is_file(), f"Falta info.json horneado para {g}"
        baked = load_baked_grapheme_animation(g)
        assert baked is not None
        assert len(baked["bones"]) == 54
        assert len(baked["frames"]) >= 20
        mid_rot = baked["frames"][len(baked["frames"]) // 2]["rotations"]
        assert "rightIndexProximal" in mid_rot and "rightThumbProximal" in mid_rot

    r_idx = client.get("/api/v1/animations/stroke-index?limit=5000")
    assert r_idx.status_code == 200
    d_idx = r_idx.json()
    assert d_idx["totalSigns"] == 4142
    assert len(d_idx["signs"]) == 4142
    assert d_idx["totalFingerspellingSigns"] == 30
    assert len(d_idx["fingerspellingSigns"]) == 30
    assert "Letra Ñ" in d_idx["fingerspellingSigns"]
    assert "Letra CH" in d_idx["fingerspellingSigns"]

    for alias in ("Letra A", "DACT_CH", "Ñ", "RR"):
        r_st = client.get(f"/api/v1/animations/{alias}/stroke")
        assert r_st.status_code == 200, f"Fallo al consultar /stroke para {alias}"
        st_payload = r_st.json()
        assert st_payload["flags"]["isFingerspelling"] is True

    r_anim = client.get("/api/v1/animations/Letra%20CH?version=2.7")
    assert r_anim.status_code == 200
    anim_ch = r_anim.json()
    assert anim_ch["metadata"]["version_served"] == "2.7"
    assert anim_ch["metadata"]["stroke"]["grapheme"] == "CH"
    assert anim_ch["metadata"]["handStandardization"]["status"] == "STANDARDIZED"

    r_info = client.get("/api/v1/animations/Letra%20LL/info")
    assert r_info.status_code == 200
    assert r_info.json()["grapheme"] == "LL"


def test_08_strict_modularity_under_800_lines():
    """Verifica que ningún archivo modificado o creado supere las 800 líneas de código."""
    checked_files = [
        "app/static/js/avatar/sign-clips-fingerspelling-primitives.js",
        "app/static/js/avatar/sign-clips-fingerspelling-catalog.js",
        "app/static/js/avatar/sign-clips-fingerspelling-lsec.js",
        "app/static/js/avatar/sign-clip-factory.js",
        "app/static/js/avatar/sign-clips-hands-orientation.js",
        "app/static/js/avatar/sign-clips-cnm-simultaneous.js",
        "app/static/js/avatar/non-manual-controller.js",
        "app/static/js/avatar/sequence-coarticulation-math.js",
        "app/static/js/avatar/sequence-run-scheduler.js",
        "app/static/js/avatar/sequence-compiler.js",
        "app/static/js/avatar/sign-stroke-window.js",
        "app/static/js/avatar/avatar-sync-controller.js",
        "app/static/js/avatar/studio-avatar-bridge.js",
        "app/static/js/components/gloss-overlay.js",
        "app/services/animation_fingerspelling_service.py",
        "app/services/animation_catalog_service.py",
        "app/services/animation_media_service.py",
        "app/services/animation_lexical_resolver.py",
        "app/services/discourse_gloss_emitter.py",
        "app/services/discourse_planner.py",
        "app/services/nlp_service.py",
        "app/api/animation_direct_endpoints.py",
        "scripts/bake_lsec_fingerspelling_v27.mjs",
        "app/tests/test_lsec_fingerspelling.mjs",
        "app/tests/test_lsec_fingerspelling.py",
    ]
    for rel in checked_files:
        p = REPO_ROOT / rel
        assert p.is_file(), f"Archivo esperado no encontrado: {rel}"
        line_count = len(p.read_text(encoding="utf-8").splitlines())
        assert line_count <= 800, f"El archivo {rel} tiene {line_count} líneas (supera el límite estricto de 800 líneas)"
