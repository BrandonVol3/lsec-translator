"""
Suite de Pruebas E2E Automatizadas — Exportación Determinista a 30 FPS en MP4 y Stepper Bar.

Verifica:
1. El botón de acción dinámico del stepper avanza los pasos y abre el diálogo de exportación sin TypeError.
2. modalsController.openExportModal() y openExportDialog() abren el modal correctamente.
3. El pipeline de finalización de video genera MP4 con video H.264 a 30.0 FPS constantes y audio AAC.
"""

import io
import re
from fractions import Fraction
import numpy as np
import pytest
from playwright.sync_api import sync_playwright, expect
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
STUDIO_URL = "http://127.0.0.1:8000/studio"


def test_stepper_action_and_export_modal_without_errors():
    """Valida que el stepper bar transite pasos y abra el modal de exportación sin excepciones."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--enable-webgl",
                "--ignore-gpu-blocklist"
            ]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        page.goto(STUDIO_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#app-container", timeout=15000)

        # 1. Cargar proyecto real (1.mp4) en appState sin mocks sintéticos
        page.evaluate("""() => {
            window.appState.resetToDefaultProject();
            window.appState.setWorkflowStep('step3_revisar');
        }""")
        page.wait_for_timeout(300)

        # 3. Avanzar desde Ventana 1 -> Ventana 2 -> Ventana 3 con los botones del Wizard
        page.evaluate("() => window.appState.setStage('preparar')")
        page.wait_for_timeout(300)
        btn_step1 = page.locator("#btn-step1-process-lsec")
        expect(btn_step1).to_be_visible()
        btn_step1.click()
        page.wait_for_timeout(300)

        stage = page.evaluate("() => window.appState.state.workspace.stage")
        assert stage == "traducir"

        btn_step2 = page.locator("#btn-step2-confirm-glosses")
        expect(btn_step2).to_be_visible()
        btn_step2.click()
        page.wait_for_timeout(300)

        stage = page.evaluate("() => window.appState.state.workspace.stage")
        assert stage in ("avatar", "revisar")
        if stage == "avatar":
            btn_step3 = page.locator("#btn-step3-to-step4")
            expect(btn_step3).to_be_visible()
            btn_step3.click()
            page.wait_for_timeout(300)
            stage = page.evaluate("() => window.appState.state.workspace.stage")
        assert stage == "revisar"

        # 4. Activar #btn-export-modal para abrir el diálogo general de exportación
        page.evaluate("() => document.getElementById('btn-export-modal')?.click()")
        page.wait_for_timeout(500)

        # Verificar que el modal de exportación se abrió
        modal_backdrop = page.locator("#generic-modal-backdrop")
        expect(modal_backdrop).to_have_class(re.compile(r"open"))
        modal_title = page.locator("#generic-modal-title")
        expect(modal_title).to_contain_text("Exportar Resultados")

        # 5. Cerrar modal
        btn_close = page.locator("#generic-modal-close")
        btn_close.click()
        page.wait_for_timeout(300)

        # 6. Probar botón de Ventana 3 #btn-step3-export-mp4
        btn_step3_export = page.locator("#btn-step3-export-mp4")
        expect(btn_step3_export).to_be_visible()
        btn_step3_export.click()
        page.wait_for_timeout(500)
        expect(modal_backdrop).to_have_class(re.compile(r"open"))

        # 7. Verificar que no hubo ningún TypeError en consola
        type_errors = [e for e in console_errors if "TypeError" in e or "openExportModal" in e]
        assert len(type_errors) == 0, f"Errores de tipo en consola: {type_errors}"

        browser.close()


def test_offline_deterministic_mp4_generation_pyav():
    """Valida con PyAV que el endpoint de exportación genere H.264 a 30 FPS constantes con audio AAC."""
    import av

    src_buf = io.BytesIO()
    in_c = av.open(src_buf, mode="w", format="mp4")
    v_s = in_c.add_stream("libx264", rate=30)
    v_s.width = 640
    v_s.height = 360
    v_s.pix_fmt = "yuv420p"
    a_s = in_c.add_stream("aac", rate=48000)
    a_s.layout = "stereo"

    # 30 cuadros = 1 segundo exacto a 30 FPS
    for i in range(30):
        arr = np.full((360, 640, 3), fill_value=(i * 8) % 255, dtype=np.uint8)
        vf = av.VideoFrame.from_ndarray(arr, format="rgb24")
        vf.pts = i
        vf.time_base = Fraction(1, 30)
        for pkt in v_s.encode(vf):
            in_c.mux(pkt)
    for pkt in v_s.encode(None):
        in_c.mux(pkt)

    for j in range(24):
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
            "video_file": ("test_render.mp4", raw_bytes, "video/mp4"),
            "audio_file": ("test_render.mp4", raw_bytes, "video/mp4"),
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("video/mp4")
    assert resp.headers.get("x-export-fps") == "30"

    out_c = av.open(io.BytesIO(resp.content), mode="r")
    assert len(out_c.streams.video) == 1
    assert len(out_c.streams.audio) == 1
    out_vs = out_c.streams.video[0]
    assert out_vs.codec_context.name == "h264"
    assert float(out_vs.average_rate) == pytest.approx(30.0, abs=0.1)

    frames = list(out_c.decode(video=0))
    assert len(frames) == 30
    out_c.close()
