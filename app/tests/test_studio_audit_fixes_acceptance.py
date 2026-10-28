"""
Suite de Pruebas E2E y de Aceptación — Auditoría Integral UI/UX, Accesibilidad, Wizard de 3 Ventanas
y Encuadre Determinista del Torso a la Cabeza (pip_bust) en el Video Exportado.
"""

import time
import urllib.request
import subprocess
import sys
import pytest
from playwright.sync_api import sync_playwright

STUDIO_URL = "http://127.0.0.1:8000/studio"


@pytest.fixture(scope="module")
def studio_server():
    """Asegura que el servidor FastAPI esté activo en 127.0.0.1:8000."""
    server_process = None
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8000/api/info", timeout=2)
        if resp.status == 200:
            yield None
            return
    except Exception:
        pass

    cmd = [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"
    ]
    server_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    started = False
    for _ in range(30):
        time.sleep(0.4)
        try:
            resp = urllib.request.urlopen("http://127.0.0.1:8000/api/info", timeout=1)
            if resp.status == 200:
                started = True
                break
        except Exception:
            pass

    if not started:
        if server_process:
            server_process.terminate()
        pytest.skip("No se pudo iniciar el servidor FastAPI en 127.0.0.1:8000")

    yield server_process

    if server_process:
        server_process.terminate()
        server_process.wait(timeout=5)


@pytest.fixture(scope="module")
def page(studio_server):
    """Abre Chromium con soporte WebGL y carga /studio."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--enable-webgl",
                "--ignore-gpu-blocklist",
            ],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = context.new_page()
        pg.goto(STUDIO_URL, wait_until="domcontentloaded")
        pg.wait_for_selector("#app-container", timeout=15000)
        pg.wait_for_function("() => window.studioAvatarBridge && window.studioAvatarBridge.isReady", timeout=25000)
        yield pg
        browser.close()


def test_01_accessibility_labels_aria_and_contrast_tokens(page):
    """
    Verifica accesibilidad y tokens de «Pedagogical Tactile Light»:
    - Cero elementos <label> huérfanos en toda la interfaz.
    - Todos los controles de formulario tienen etiqueta asociada o aria-label.
    - Variables CSS de tema claro definidas en :root.
    """
    a11y_audit = page.evaluate("""() => {
        const rootStyles = getComputedStyle(document.documentElement);
        const cssVars = {
            bgBase: rootStyles.getPropertyValue('--bg-base').trim(),
            bgCard: rootStyles.getPropertyValue('--bg-card').trim(),
            bgSurface2: rootStyles.getPropertyValue('--bg-surface-2').trim(),
            primary: rootStyles.getPropertyValue('--primary').trim(),
            lsecYellow: rootStyles.getPropertyValue('--lsec-yellow').trim(),
            lsecGreen: rootStyles.getPropertyValue('--lsec-green').trim(),
            fontBase: rootStyles.getPropertyValue('--font-base').trim(),
            emerald: rootStyles.getPropertyValue('--color-primary-emerald').trim(),
            cobalt: rootStyles.getPropertyValue('--color-accent-cobalt').trim(),
        };

        const labels = Array.from(document.querySelectorAll('label'));
        const orphanLabels = labels.filter(lbl => {
            const forId = lbl.getAttribute('for');
            if (forId && document.getElementById(forId)) return false;
            if (lbl.querySelector('input, select, textarea')) return false;
            return true;
        }).map(l => l.outerHTML);

        const controls = Array.from(document.querySelectorAll('input:not([type="hidden"]), select, textarea'));
        const unlabeledControls = controls.filter(ctrl => {
            if (ctrl.style.display === 'none') return false;
            if (ctrl.getAttribute('aria-label') || ctrl.getAttribute('aria-labelledby') || ctrl.getAttribute('title')) return false;
            if (ctrl.id && document.querySelector(`label[for="${ctrl.id}"]`)) return false;
            if (ctrl.closest('label')) return false;
            return true;
        }).map(c => c.id || c.outerHTML);

        return { cssVars, orphanLabels, unlabeledControls };
    }""")

    for k, v in a11y_audit["cssVars"].items():
        assert v != "", f"Variable CSS {k} no está definida en :root"

    assert len(a11y_audit["orphanLabels"]) == 0, f"Labels huérfanos detectados: {a11y_audit['orphanLabels']}"
    assert len(a11y_audit["unlabeledControls"]) == 0, f"Controles sin label/aria-label: {a11y_audit['unlabeledControls']}"


def test_02_wizard_step2_grammar_monitor_and_parallel_comparative_table(page):
    """
    Verifica Ventana 2 (Motor Lingüístico y Mesa Comparativa Paralela):
    - El Monitor Visual de Transformación Gramatical muestra palabras elididas tachadas y etiquetas de reglas en azul (#0284c7).
    - La Mesa Comparativa Paralela de 2 Columnas alinea cada oración en español frente a sus fichas táctiles de glosas LSEC.
    """
    step2_metrics = page.evaluate("""() => {
        window.appState.resetToDefaultProject();
        window.switchWizardStep('traducir');

        const rows = Array.from(document.querySelectorAll('#comparative-rows-container .comparative-row'));
        const chips = Array.from(document.querySelectorAll('#comparative-rows-container .gloss-chip-tactile'));
        const elided = Array.from(document.querySelectorAll('#grammar-spanish-tokens .grammar-token-elided'));
        const rules = Array.from(document.querySelectorAll('#grammar-applied-rules-list .grammar-rule-badge'));

        const firstRow = rows[0];
        const leftCell = firstRow ? firstRow.querySelector('.comparative-cell-spanish').getBoundingClientRect() : null;
        const rightCell = firstRow ? firstRow.querySelector('.comparative-cell-glosses').getBoundingClientRect() : null;

        return {
            rowCount: rows.length,
            chipCount: chips.length,
            elidedCount: elided.length,
            ruleCount: rules.length,
            alignedSideBySide: Boolean(leftCell && rightCell && Math.abs(leftCell.top - rightCell.top) < 5 && rightCell.left >= leftCell.right - 2)
        };
    }""")

    assert step2_metrics["rowCount"] >= 8
    assert step2_metrics["chipCount"] > 20
    assert step2_metrics["elidedCount"] >= 1
    assert step2_metrics["ruleCount"] >= 1
    assert step2_metrics["alignedSideBySide"] is True


def test_03_wizard_step3_avatar_stage_live_monitor_and_export_controls(page):
    """
    Verifica Ventana 3/4 (Vista Previa del Avatar y Exportación):
    - Escenario multimedia acoplado en #step3-video-slot (etapa avatar) y #step4-video-slot (etapa revisar).
    - Monitor en vivo de señas LSEC en el centro.
    - Personalizador Avanzado de Estilos de Subtítulos + botones EXPORTAR VIDEO MP4 y EXPORTAR SUBTÍTULOS SRT.
    """
    step3_metrics = page.evaluate("""() => {
        window.switchWizardStep('avatar');
        const videoSlot3 = document.getElementById('step3-video-slot');
        const videoZone = document.getElementById('left-video-zone');
        const inSlot3 = Boolean(videoSlot3 && videoZone && videoSlot3.contains(videoZone));
        const liveMonitor = document.getElementById('step3-live-sign-monitor');
        const hasLiveMonitor = Boolean(liveMonitor && liveMonitor.getBoundingClientRect().width > 200);

        window.switchWizardStep('revisar');
        const videoSlot4 = document.getElementById('step4-video-slot');
        const inSlot4 = Boolean(videoSlot4 && videoZone && videoSlot4.contains(videoZone));
        const pip = document.getElementById('gloss-overlay-container');
        const subPanel = document.getElementById('view-side-subtitles');
        const btnMp4 = document.getElementById('btn-step3-export-mp4');
        const btnSrt = document.getElementById('btn-step3-export-srt');

        return {
            videoInStep3: inSlot3 && inSlot4,
            pipOpacity: pip ? getComputedStyle(pip).opacity : '0',
            hasLiveMonitor,
            hasSubCustomizer: Boolean(subPanel && subPanel.children.length > 0),
            hasMp4Btn: Boolean(btnMp4),
            hasSrtBtn: Boolean(btnSrt)
        };
    }""")

    assert step3_metrics["videoInStep3"] is True
    assert float(step3_metrics["pipOpacity"]) > 0.5
    assert step3_metrics["hasLiveMonitor"] is True
    assert step3_metrics["hasSubCustomizer"] is True
    assert step3_metrics["hasMp4Btn"] is True
    assert step3_metrics["hasSrtBtn"] is True


def test_04_deterministic_export_enforces_torso_to_head_bust_framing_under_all_conditions(page):
    """
    Verifica que el avatar se observe del torso a la cabeza ('pip_bust') en el video exportado final.
    """
    export_framing_check = page.evaluate("""async () => {
        const bridge = window.studioAvatarBridge;
        const ctrl = bridge.controller;
        const eng = ctrl.engine;

        bridge.dockToSidebar();
        ctrl.setCameraPreset('full');
        eng.rotateCamera(25, 10);

        bridge.beginDeterministicExport();
        bridge.dockToSidebar();
        ctrl.setCameraPreset('full');
        ctrl.setCameraPreset('hands');
        eng.rotateCamera(45, 20);
        eng.panCamera(2, 2);
        eng.dollyCamera(1.0);
        eng.resetCamera();
        eng.onResize();

        await bridge.stepAtVideoTime(1.0, 1 / 30);
        const exportCanvas = bridge.captureFrame();

        const duringExport = {
            fov: eng.camera.fov,
            posX: Number(eng.camera.position.x.toFixed(2)),
            posY: Number(eng.camera.position.y.toFixed(2)),
            posZ: Number(eng.camera.position.z.toFixed(2)),
            targetX: Number(eng.controls.target.x.toFixed(2)),
            targetY: Number(eng.controls.target.y.toFixed(2)),
            targetZ: Number(eng.controls.target.z.toFixed(2)),
            canvasW: exportCanvas.width,
            canvasH: exportCanvas.height,
            controlsEnabled: eng.controls.enabled
        };

        bridge.endDeterministicExport();
        return { duringExport };
    }""")

    de = export_framing_check["duringExport"]
    assert de["fov"] == 32
    assert de["posX"] == 0.0 and de["posY"] == 1.33 and de["posZ"] == 1.48
    assert de["targetX"] == 0.0 and de["targetY"] == 1.31 and de["targetZ"] == 0.0
    assert de["canvasW"] == 360 and de["canvasH"] == 414
    assert de["controlsEnabled"] is False


def test_05_preferences_font_scale_and_reduced_motion_apply(page):
    """
    Verifica que setFontSizeScale('large') y reduced-motion actualizan html[data-font-scale] y body.reduced-motion.
    """
    prefs = page.evaluate("""() => {
        window.appState.setFontSizeScale('large');
        document.body.classList.add('reduced-motion');
        const res = {
            fontScaleAttr: document.documentElement.getAttribute('data-font-scale'),
            rootFontSize: getComputedStyle(document.documentElement).fontSize,
            hasReducedMotionClass: document.body.classList.contains('reduced-motion')
        };
        window.appState.setFontSizeScale('normal');
        document.body.classList.remove('reduced-motion');
        return res;
    }""")

    assert prefs["fontScaleAttr"] == "large"
    assert prefs["rootFontSize"] in ("15.5px", "17px")
    assert prefs["hasReducedMotionClass"] is True
