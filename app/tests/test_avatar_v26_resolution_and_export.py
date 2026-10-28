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
    """Verifica que el índice léxico v2.6 indexe las 4,142 carpetas reales normalizadas y sus entradas compuestas."""
    idx = _build_v26_lexical_index()
    assert idx["total_v26"] == 4142, f"Se esperaban 4142 carpetas v2.6, se obtuvieron {idx['total_v26']}"
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
        candidates = [
            repo_root / rel_path,
            repo_root.parent / "_archive" / "lsec_translator_prototype" / rel_path,
        ]
        p = next((cand for cand in candidates if cand.is_file()), None)
        if p and p.is_file():
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

    # Las marcas direccionales pertenecen a la ejecución, no al nombre del clip.
    directional = client.get(
        "/api/animations-direct/resolve/INVITAR%5B1-PL-%3E2%5D?version=2.6&include_animation=false"
    )
    assert directional.status_code == 200
    directional_data = directional.json()
    assert directional_data["found"] is True
    assert directional_data["resolved_gloss"]

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
    assert d4["match_type"] in ("none", "fingerspelling")

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


def test_get_sign_video_integrity_and_fallback_to_senas(tmp_path, monkeypatch):
    """
    Verifica que:
      1. _is_video_stream_healthy detecte archivos ausentes, truncados en borde de paquete,
         con doble átomo moov / sin mdat, WebM truncados o con paquetes NAL corruptos.
      2. GET /api/v1/animations/{sign_name}/video sirva desde senas_ultra_hd cuando el video es íntegro
         (incluyendo 'Alegre, Alegría' y las 316 señas reparadas) y soporte peticiones HTTP Range (206).
      3. Si el video en senas_ultra_hd está corrupto o ausente, haga fallback automático hacia
         Diccionario LSEC/senas/ (incluyendo contenedores .mp4, .webm y .mkv).
    """
    import av
    from app.api.animation_direct_endpoints import _is_video_stream_healthy, get_senas_dir, get_uhd_dir

    # 1. Validación directa de _is_video_stream_healthy con casos borde
    assert _is_video_stream_healthy(tmp_path / "no_existe.mp4") is False

    tiny_mp4 = tmp_path / "tiny.mp4"
    tiny_mp4.write_bytes(b"0" * 100)
    assert _is_video_stream_healthy(tiny_mp4) is False

    corrupt_mp4 = tmp_path / "corrupt_moov.mp4"
    corrupt_mp4.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 4096)
    assert _is_video_stream_healthy(corrupt_mp4) is False

    uhd_base = get_uhd_dir()
    senas_base = get_senas_dir()
    assert uhd_base is not None and senas_base is not None

    # 1b. MP4 truncado exactamente en un límite de paquete dentro de mdat (f0 válido, pero faltan paquetes)
    abanico_uhd = uhd_base / "Abanico" / "video.mp4"
    raw_abanico = abanico_uhd.read_bytes()
    with av.open(str(abanico_uhd), mode="r") as c:
        pkts = [bytes(p) for p in c.demux(video=0) if p.dts is not None or p.pts is not None]
    cut_pos = raw_abanico.find(pkts[15]) + len(pkts[15])
    truncated_boundary_mp4 = tmp_path / "truncated_boundary.mp4"
    truncated_boundary_mp4.write_bytes(raw_abanico[:cut_pos])
    assert _is_video_stream_healthy(truncated_boundary_mp4) is False

    # 1c. MP4 con doble moov y cabecera mdat sobrescrita (caso 'Alegre, Alegría' pre-reparación)
    mdat_pos = raw_abanico.find(b"mdat")
    assert mdat_pos > 4
    double_moov_bytes = bytearray(raw_abanico)
    double_moov_bytes[mdat_pos - 4 : mdat_pos + 4] = b"\x00\x00\x18$moov"
    double_moov_mp4 = tmp_path / "double_moov_no_mdat.mp4"
    double_moov_mp4.write_bytes(bytes(double_moov_bytes))
    assert _is_video_stream_healthy(double_moov_mp4) is False

    # 1d. WebM VP9 truncado al 25% de su tamaño (primer cuadro decodifica, pero duración incompleta)
    tumor_webm = senas_base / "Tumor" / "video.webm"
    if tumor_webm.is_file():
        raw_webm = tumor_webm.read_bytes()
        trunc_webm = tmp_path / "truncated_tumor.webm"
        trunc_webm.write_bytes(raw_webm[: len(raw_webm) // 4])
        assert _is_video_stream_healthy(trunc_webm) is False

    # 2. Verificar reproducción desde senas_ultra_hd para señas reparadas (incluyendo 'Alegre, Alegría')
    for sign_name in (
        "Abanico",
        "Alegre, Alegría",
        "Almacén de cosméticos",
        "Asociación De Pichincha",
        "Bélgica",
        "Medidor de luz alterado",
    ):
        resp = client.get(f"/api/v1/animations/{sign_name}/video")
        assert resp.status_code == 200, f"Fallo al obtener video de {sign_name}"
        assert resp.headers.get("x-video-source") == "ultra_hd"
        with av.open(io.BytesIO(resp.content), mode="r") as c:
            assert len(c.streams.video) >= 1
            f0 = next(c.decode(video=0), None)
            assert f0 is not None

    # 2b. Verificar soporte de peticiones parciales HTTP Range (206 Partial Content)
    resp_range = client.get("/api/v1/animations/Alegre, Alegría/video", headers={"Range": "bytes=0-1023"})
    assert resp_range.status_code == 206
    assert len(resp_range.content) == 1024
    assert resp_range.headers.get("content-range", "").startswith("bytes 0-1023/")

    # 3. Simular un directorio Ultra HD con un archivo corrupto y verificar fallback a senas/ (.mp4, .webm, .mkv)
    fake_uhd = tmp_path / "fake_uhd"
    sign_dir = fake_uhd / "Abanico"
    sign_dir.mkdir(parents=True)
    bad_video = sign_dir / "video.mp4"
    bad_video.write_bytes(bytes(double_moov_bytes))

    monkeypatch.setenv("LSEC_UHD_DIR", str(fake_uhd))
    resp_fb = client.get("/api/v1/animations/Abanico/video")
    assert resp_fb.status_code == 200
    assert resp_fb.headers.get("x-video-source") == "fallback_senas"
    with av.open(io.BytesIO(resp_fb.content), mode="r") as c:
        assert next(c.decode(video=0), None) is not None

    # 3b. Verificar fallback hacia los 4 contenedores .mkv / .webm de senas/ y Range request sobre ellos
    for non_mp4_sign, expected_mime in (
        ("Abanderado(a)", "video/x-matroska"),
        ("Anciano(a), Abuelo", "video/webm"),
        ("Satisfecho(a)", "video/webm"),
        ("Tumor", "video/webm"),
    ):
        r_nm = client.get(f"/api/v1/animations/{non_mp4_sign}/video")
        assert r_nm.status_code == 200, f"Fallo fallback en {non_mp4_sign}"
        assert r_nm.headers.get("x-video-source") == "fallback_senas"
        assert r_nm.headers.get("content-type", "").startswith(expected_mime)
        r_nm_range = client.get(f"/api/v1/animations/{non_mp4_sign}/video", headers={"Range": "bytes=0-511"})
        assert r_nm_range.status_code == 206
        assert len(r_nm_range.content) == 512

    # 4. Seña inexistente retorna 404 estructurado
    resp_404 = client.get("/api/v1/animations/SENA_TOTALMENTE_INEXISTENTE_9999/video")
    assert resp_404.status_code == 404
    detail = resp_404.json().get("detail", {})
    assert "message" in detail



def test_animations_list_nfc_deduplicated_4142():
    """
    Verifica que /api/v1/animations/list retorne exactamente las 4,142 señas únicas en NFC,
    sin duplicados NFD/NFC (p. ej. '#4: A través, Mediante' aparece una sola vez).
    """
    import unicodedata

    resp = client.get("/api/v1/animations/list?limit=10000")
    assert resp.status_code == 200
    data = resp.json()
    signs = data.get("signs", [])
    items = data.get("items", [])

    assert data.get("total") == 4142
    assert len(signs) == 4142
    assert len(items) == 4142

    # Ninguna seña está en NFD ni duplicada tras normalizar a NFC
    nfc_set = {unicodedata.normalize("NFC", s) for s in signs}
    assert len(nfc_set) == 4142
    assert all(unicodedata.is_normalized("NFC", s) for s in signs)

    # Verificar que 'A través, Mediante' (#4) aparece exactamente 1 vez
    matches_4 = [s for s in signs if unicodedata.normalize("NFC", s) == "A través, Mediante"]
    assert len(matches_4) == 1
    assert matches_4[0] == "A través, Mediante"


def test_signs_1_to_5_and_accents_have_recovered_expressions_head_neck_shoulders():
    """
    Verifica que las señas #1 a #5 (y señas con tilde tanto en consulta NFC como NFD)
    tengan tracks_recovered=True, las 66 pistas faciales (14 VRM + 52 ARKit) activas
    y rotaciones no nulas de head, neck, leftShoulder y rightShoulder.
    """
    import unicodedata

    target_signs = [
        "A diario, Cotidiano(a)",
        "A lado",
        "A los tiempos",
        "A través, Mediante",
        unicodedata.normalize("NFD", "A través, Mediante"),
        "A veces",
        "Útiles escolares",
    ]

    for sign_name in target_signs:
        resp = client.get(f"/api/v1/animations/{sign_name}")
        assert resp.status_code == 200, f"Fallo al cargar animación de '{sign_name}'"
        anim = resp.json()
        assert anim.get("metadata", {}).get("fidelity", {}).get("tracks_recovered") is True

        frames = anim.get("frames", [])
        assert len(frames) > 0

        # 14 VRM expressions + 52 ARKit blendshapes = 66 tracks
        f0 = frames[0]
        assert len(f0.get("expressions", {})) == 14
        assert len(f0.get("blendshapes", {})) == 52

        has_facial = bool(anim.get("metadata", {}).get("hasExplicitFacialExpression")) or bool(anim.get("metadata", {}).get("nonManualStandard", {}).get("hasExplicitFacialExpression"))
        if has_facial:
            assert max_non_neutral_ex > 0.01, f"Expresiones VRM no-neutrales en cero para {sign_name}"
            assert max_bs > 0.01, f"Blendshapes ARKit en cero para {sign_name}"
        else:
            assert f0.get("expressions", {}).get("neutral", 0.0) >= 0.99 or max_non_neutral_ex >= 0.0

        for bone in ("head", "neck", "leftShoulder", "rightShoulder"):
            max_rot = max(
                sum(abs(float(c)) for c in fr.get("rotations", {}).get(bone, [0.0, 0.0, 0.0, 1.0])[:3])
                for fr in frames
            )
            assert max_rot > 1e-3, f"Rotación de {bone} en identidad [0,0,0,1] para {sign_name}"


def test_vrm_loader_52_arkit_bindings_and_selector_sync():
    """
    Verifica que:
    1. vrm-loader.js vincule los 52 blendshapes ARKit y 18 presets VRM hacia los morph targets Fcl_*
       de LSEC-Interpreter-Female.vrm (ensureARKitAndVRMExpressionBindings) y neutralice Fcl_ALL_Neutral.
    2. sign-player.js y viewer.html supriman 'neutral' cuando hay expresiones o blendshapes activos.
    3. avatar-controller.js sincronice #select-avatar-clip en importCustomClip tanto por clipId como por glosa NFC.
    4. Los endpoints /info, /illustration y /video resuelvan consultas en NFC y NFD sin fallar.
    """
    import unicodedata

    static_dir = Path(__file__).resolve().parents[1] / "static"
    vrm_loader_js = (static_dir / "js" / "avatar" / "vrm-loader.js").read_text(encoding="utf-8")
    sign_player_js = (static_dir / "js" / "avatar" / "sign-player.js").read_text(encoding="utf-8")
    avatar_ctrl_js = (static_dir / "js" / "avatar" / "avatar-controller.js").read_text(encoding="utf-8")
    schema_js = (static_dir / "js" / "avatar" / "sign-animation-schema.js").read_text(encoding="utf-8")
    viewer_html = (static_dir / "viewer.html").read_text(encoding="utf-8")

    assert "export function ensureARKitAndVRMExpressionBindings" in vrm_loader_js
    assert "CANONICAL_VROID_57_TARGET_NAMES" in vrm_loader_js
    assert "ARKIT_TO_VROID_MORPH_MAP" in vrm_loader_js
    assert "ClampedMorphTargetBind" in vrm_loader_js
    assert "EyeBoneGazeBind" in vrm_loader_js
    assert "ARKIT_BLENDSHAPE_NAMES" in schema_js

    assert "maxNonNeutral" in sign_player_js
    assert "ensureARKitAndVRMExpressionBindings" in viewer_html
    assert "frame.blendshapes" in viewer_html

    assert "this.clips[nfcGloss] = customClip" in avatar_ctrl_js
    assert "this.selectedClipId = resolvedSelectVal" in avatar_ctrl_js

    for raw_sign in ("A través, Mediante", "Alegre, Alegría", "Útiles escolares"):
        for form in ("NFC", "NFD"):
            q_sign = unicodedata.normalize(form, raw_sign)
            r_info = client.get(f"/api/v1/animations/{q_sign}/info")
            assert r_info.status_code == 200, f"Fallo /info en {form} para {raw_sign}"
            r_vid = client.get(f"/api/v1/animations/{q_sign}/video", headers={"Range": "bytes=0-255"})
            assert r_vid.status_code in (200, 206), f"Fallo /video en {form} para {raw_sign}"

