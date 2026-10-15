"""
Pruebas Automatizadas de Integración — Catálogo LSEC v2.6 (5,061 señas),
Resolución Léxica sin 404, Preservación de Glosas y Exportación MP4 a 30.0 FPS.
"""

import io
import json
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.animation_direct_endpoints import (
    _build_v26_lexical_index,
    resolve_gloss_to_sign,
)


client = TestClient(app)


def test_v26_lexical_index_loads_all_5061_folders():
    """Verifica que el índice léxico v2.6 indexe las 5,061 carpetas reales y sus entradas compuestas."""
    idx = _build_v26_lexical_index()
    assert idx["total_v26"] == 5061, f"Se esperaban 5061 carpetas v2.6, se obtuvieron {idx['total_v26']}"
    assert idx["unique_v26"] >= 4140
    assert len(idx["exact_map"]) >= 4130
    assert len(idx["part_map"]) >= 5000


def test_all_1mp4_glosses_resolve_without_404_or_omission():
    """
    Verifica que las 85 glosas únicas de 1.mp4 (incluyendo SER, CON, ESO, PRO1-PL, PRO2,
    HOY, NADIE, ACADÉMICO, CAMPUS, CARRERA, MÁS-DE, SOLAMENTE-NO, ESAS-PERSONAS)
    resuelvan a animaciones v2.6 válidas sin errores 404 y sin omitir ninguna glosa.
    """
    repo_root = Path(__file__).resolve().parents[2]
    gloss_set = {"SER", "CON", "ESO", "PRO1", "PRO1-PL", "PRO2", "PRO3"}
    for rel_path in ("reports/lsec_2_1_1_after.json", "reports/upec_v21_inspection.json"):
        p = repo_root / rel_path
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            for g in data.get("glosses", []):
                name = (g.get("gloss") or g.get("lemma") or "").strip()
                if name:
                    gloss_set.add(name)

    assert len(gloss_set) >= 85

    # Probar lote completo vía POST /api/animations-direct/resolve
    resp = client.post(
        "/api/animations-direct/resolve",
        json={"glosses": sorted(gloss_set), "version": "2.6", "include_animation": False},
    )
    assert resp.status_code == 200
    payload = resp.json()
    summary = payload["summary"]

    assert summary["missing"] == 0, f"Glosas faltantes inesperadas: {[i for i in payload['items'] if i['status'] == 'MISSING']}"
    assert summary["fingerspelling"] == 3  # C-A-Y-A-M-B-E, T-U-L-C-Á-N, U-P-E-C
    assert summary["resolved"] == len(gloss_set) - 3

    results = payload["results"]
    # Verificar glosas críticas que antes fallaban con 404 o se omitían
    for critical in ("SER", "CON", "ESO", "PRO1-PL", "PRO2", "HOY", "NADIE", "ACADÉMICO", "CAMPUS", "MÁS-DE", "SOLAMENTE-NO", "ESAS-PERSONAS"):
        if critical in results:
            assert results[critical]["found"] is True, f"Glosa crítica {critical} no resuelta"
            assert results[critical]["version_served"] == "2.6"

    # Verificar desambiguación de homónimos (CARRERA -> Carrera, Estudios, NO Carrera, De autos)
    assert results["CARRERA"]["resolved_gloss"] == "Carrera, Estudios"
    assert results["HOY"]["resolved_gloss"] == "Ahora"
    assert results["NADIE"]["resolved_gloss"] == "Ninguno(a)"


def test_resolve_endpoint_edge_cases_and_zero_404():
    """Prueba casos borde: signos de interrogación, sufijos de género, dactilología y glosas inexistentes."""
    # 1. Glosa con signos de puntuación
    r1 = client.get("/api/animations-direct/resolve/%C2%BFQUI%C3%89N%3F?include_animation=false")
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["found"] is True
    assert "Quién" in d1["resolved_gloss"]

    # 2. Sufijo de género (a) en carpeta "A diario, Cotidiano(a)"
    r2 = client.get("/api/animations-direct/resolve/COTIDIANA?include_animation=false")
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["found"] is True
    assert "Cotidiano" in d2["resolved_gloss"]

    # 3. Dactilología explícita letra por letra
    r3 = client.get("/api/animations-direct/resolve/U-P-E-C?include_animation=false")
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["found"] is False
    assert d3["is_fingerspelling"] is True
    assert d3["match_type"] == "fingerspelling"

    # 4. Glosa inexistente no debe retornar HTTP 404 en /resolve/
    r4 = client.get("/api/animations-direct/resolve/GLOSA_INEXISTENTE_XYZ999?include_animation=false")
    assert r4.status_code == 200
    d4 = r4.json()
    assert d4["found"] is False
    assert d4["match_type"] == "none"

    # 5. Entrada vacía en resolve_gloss_to_sign
    empty_res = resolve_gloss_to_sign("   ", include_animation=False)
    assert empty_res["found"] is False
    assert empty_res["status"] == "EMPTY"


def test_finalize_export_mp4_constant_30fps():
    """Verifica que POST /api/v1/animations/finalize-export-mp4 genere un MP4 H.264 + AAC a 30.0 FPS constantes."""
    import av

    # Crear un clip de entrada sintético de 15 fotogramas (0.5s a 30 FPS) con audio
    src_buf = io.BytesIO()
    in_c = av.open(src_buf, mode="w", format="mp4")
    v_s = in_c.add_stream("libx264", rate=30)
    v_s.width = 320
    v_s.height = 240
    v_s.pix_fmt = "yuv420p"
    a_s = in_c.add_stream("aac", rate=48000)
    a_s.layout = "stereo"

    for i in range(15):
        arr = np.full((240, 320, 3), fill_value=(i * 12) % 255, dtype=np.uint8)
        vf = av.VideoFrame.from_ndarray(arr, format="rgb24")
        vf.pts = i
        vf.time_base = Fraction(1, 30)
        for pkt in v_s.encode(vf):
            in_c.mux(pkt)
    for pkt in v_s.encode(None):
        in_c.mux(pkt)

    for j in range(12):
        af = av.AudioFrame(format="fltp", layout="stereo", samples=1024)
        for p in af.planes:
            p.update(bytes(p.buffer_size))
        af.sample_rate = 48000
        af.pts = j * 1024
        af.time_base = Fraction(1, 48000)
        for pkt in a_s.encode(af):
            in_c.mux(pkt)
    for pkt in a_s.encode(None):
        in_c.mux(pkt)
    in_c.close()

    raw_bytes = src_buf.getvalue()
    resp = client.post(
        "/api/v1/animations/finalize-export-mp4",
        data={"fps": "30"},
        files={
            "video_file": ("capture.mp4", raw_bytes, "video/mp4"),
            "audio_file": ("source.mp4", raw_bytes, "video/mp4"),
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("video/mp4")
    assert resp.headers.get("x-export-fps") == "30"
    assert int(resp.headers.get("x-export-frames", "0")) == 15

    # Inspeccionar el MP4 resultante con PyAV
    out_c = av.open(io.BytesIO(resp.content), mode="r")
    assert len(out_c.streams.video) == 1
    assert len(out_c.streams.audio) == 1
    out_vs = out_c.streams.video[0]
    assert out_vs.codec_context.name == "h264"
    assert float(out_vs.average_rate) == pytest.approx(30.0, abs=0.1)
    decoded_frames = list(out_c.decode(video=0))
    assert len(decoded_frames) == 15
    out_c.close()
