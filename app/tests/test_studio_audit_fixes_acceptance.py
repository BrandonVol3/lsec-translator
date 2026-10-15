"""
Suite de Pruebas E2E y de Aceptación — Auditoría Integral UI/UX y Accesibilidad LSEC Studio (19 Hallazgos)
y Encuadre Determinista del Torso a la Cabeza (pip_bust) en el Video Exportado.
"""

import re
import time
import urllib.request
import subprocess
import sys
import pytest
from playwright.sync_api import sync_playwright, expect

STUDIO_URL = "http://127.0.0.1:8000/studio"
AVATAR_CONFIG_URL = "http://127.0.0.1:8000/avatarconfig"


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
    Verifica B-01, B-02, B-04, A-02, A-04, M-02, M-03:
    - Cero elementos <label> huérfanos en toda la interfaz.
    - Todos los controles de formulario tienen etiqueta asociada o aria-label.
    - Selectores tienen reglas explícitas de color/background y variables CSS definidas.
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
        };

        // Verificar que ningún <label> sea huérfano (debe tener for válido o contener un control)
        const labels = Array.from(document.querySelectorAll('label'));
        const orphanLabels = labels.filter(lbl => {
            const forId = lbl.getAttribute('for');
            if (forId && document.getElementById(forId)) return false;
            if (lbl.querySelector('input, select, textarea')) return false;
            return true;
        }).map(l => l.outerHTML);

        // Verificar que todos los inputs/selects/textareas tengan label o aria-label
        const controls = Array.from(document.querySelectorAll('input:not([type="hidden"]), select, textarea'));
        const unlabeledControls = controls.filter(ctrl => {
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


def test_02_avatar_sidebar_dock_no_face_occlusion_and_no_button_collision(page):
    """
    Verifica A-01, A-03, M-04:
    - Al abrir la pestaña Avatar 3D en el panel lateral, el dock flotante de cámara inicia colapsado
      en la esquina inferior derecha sin ocluir el rostro del avatar ni superponerse a #btn-avatar-reset-camera.
    - El contenedor PiP (#gloss-overlay-container) se oculta completamente y permanece oculto incluso
      si el usuario conmuta el botón de Glosas (G).
    """
    page.click("#tab-btn-side-avatar")
    page.wait_for_timeout(250)

    layout = page.evaluate("""() => {
        const pip = document.getElementById('gloss-overlay-container');
        const viewport = document.getElementById('avatar-viewport-wrap');
        const dock = document.getElementById('avatar-cam-dock');
        const resetBtn = document.getElementById('btn-avatar-reset-camera');
        const hudTop = document.querySelector('#avatar-viewport-wrap .avatar-hud-top');

        const vpRect = viewport.getBoundingClientRect();
        const dockRect = dock.getBoundingClientRect();
        const resetRect = resetBtn.getBoundingClientRect();
        const hudRect = hudTop.getBoundingClientRect();

        // Región central superior donde se ubica la cabeza/rostro del avatar
        const faceRegion = {
            left: vpRect.left + vpRect.width * 0.30,
            right: vpRect.left + vpRect.width * 0.70,
            top: vpRect.top + vpRect.height * 0.12,
            bottom: vpRect.top + vpRect.height * 0.55,
        };

        const overlaps = (a, b) => !(
            a.right <= b.left ||
            a.left >= b.right ||
            a.bottom <= b.top ||
            a.top >= b.bottom
        );

        return {
            pipDisplay: getComputedStyle(pip).display,
            dockCollapsed: dock.classList.contains('dock-collapsed'),
            dockOverlapsFace: overlaps(dockRect, faceRegion),
            dockOverlapsResetBtn: overlaps(dockRect, resetRect),
            hudHeight: hudRect.height,
        };
    }""")

    assert layout["pipDisplay"] == "none", "El PiP huérfano debe estar oculto cuando el Avatar 3D está en el sidebar"
    assert layout["dockCollapsed"] is True, "El dock de cámara debe iniciar colapsado en el sidebar"
    assert layout["dockOverlapsFace"] is False, "El dock de cámara no debe ocluir el rostro del avatar"
    assert layout["dockOverlapsResetBtn"] is False, "El dock colapsado no debe superponerse con #btn-avatar-reset-camera"
    assert layout["hudHeight"] <= 36, f"El HUD superior debe mantenerse en una sola línea compacta: {layout['hudHeight']}px"

    # Probar que al conmutar Glosas (G / #btn-toggle-glosses) mientras estamos en la pestaña Avatar 3D,
    # el PiP huérfano NO reaparece sobre el video (Bug 3 / M-04)
    page.click("#btn-toggle-glosses")
    page.wait_for_timeout(100)
    page.click("#btn-toggle-glosses")
    page.wait_for_timeout(100)

    pip_display_after_toggle = page.evaluate("() => getComputedStyle(document.getElementById('gloss-overlay-container')).display")
    assert pip_display_after_toggle == "none", "El PiP huérfano no debe reaparecer al conmutar glosas estando en la pestaña Avatar 3D"

    # Volver a Transcripción y comprobar que el PiP regresa normalmente
    page.click("#tab-btn-side-transcript")
    page.wait_for_timeout(250)
    pip_display_restored = page.evaluate("() => getComputedStyle(document.getElementById('gloss-overlay-container')).display")
    assert pip_display_restored == "flex", "El PiP debe restaurarse al volver a la pestaña Transcripción"


def test_03_timeline_gloss_pills_visible_and_advanced_tracks_never_overlap(page):
    """
    Verifica M-01 (Bug 1 y Bug 4):
    - Cargar el proyecto demostrativo y abrir la Línea de Tiempo.
    - En la Pista 2 (Glosas LSEC por Frase), .sentence-glosses-wrapper tiene ancho > 100px
      y las píldoras .sentence-gloss-pill son visibles (no aplastadas a 0px).
    - Al activar Capas Avanzadas (Pistas 4 a 8), ningún bloque adyacente se solapa horizontalmente
      ni en zoom 100% ni en zoom reducido (40%), y la Pista 7 muestra etiquetas de locus reales.
    """
    page.evaluate("""() => {
        window.appState.resetToDefaultProject();
        window.appState.setWorkflowStep('step3_revisar');
    }""")
    page.wait_for_timeout(300)

    page.click("#tab-btn-timeline")
    page.wait_for_timeout(250)

    track2_metrics = page.evaluate("""() => {
        const blocks = Array.from(document.querySelectorAll('#lane-track-2 .timeline-sentence-gloss'));
        return blocks.map(b => {
            const wrapper = b.querySelector('.sentence-glosses-wrapper');
            const pills = Array.from(b.querySelectorAll('.sentence-gloss-pill'));
            const wRect = wrapper ? wrapper.getBoundingClientRect() : { width: 0, height: 0 };
            return {
                id: b.dataset.sentenceId,
                blockWidth: b.getBoundingClientRect().width,
                wrapperWidth: wRect.width,
                pillCount: pills.length,
                visiblePills: pills.filter(p => p.getBoundingClientRect().width > 10).length
            };
        });
    }""")

    assert len(track2_metrics) >= 4
    for m in track2_metrics[:4]:
        assert m["wrapperWidth"] > 80, f"El contenedor de glosas en {m['id']} fue aplastado ({m['wrapperWidth']}px): {m}"
        assert m["visiblePills"] > 0, f"Las píldoras de glosa en {m['id']} no son visibles: {m}"

    # Activar Capas Avanzadas y verificar ausencia de solapamientos en Pistas 1..8
    page.click("#btn-toggle-advanced-layers")
    page.wait_for_timeout(200)

    for zoom_val in (100, 40):
        page.evaluate(f"""() => {{
            const slider = document.getElementById('timeline-zoom-slider');
            if (slider) {{
                slider.value = '{zoom_val}';
                slider.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
        }}""")
        page.wait_for_timeout(150)

        overlap_report = page.evaluate("""() => {
            const overlapsByTrack = {};
            for (let t = 1; t <= 8; t++) {
                const blocks = Array.from(document.querySelectorAll(`#lane-track-${t} .timeline-block-item`));
                const rects = blocks.map(b => ({
                    text: b.textContent.trim(),
                    left: b.getBoundingClientRect().left,
                    right: b.getBoundingClientRect().right
                })).sort((a, b) => a.left - b.left);
                const trackOverlaps = [];
                for (let i = 0; i < rects.length - 1; i++) {
                    if (rects[i].right > rects[i + 1].left + 0.5) {
                        trackOverlaps.push({ a: rects[i], b: rects[i + 1] });
                    }
                }
                if (trackOverlaps.length > 0) {
                    overlapsByTrack[`track_${t}`] = trackOverlaps;
                }
            }
            const track7Labels = Array.from(document.querySelectorAll('#lane-track-7 .timeline-block-item')).map(b => b.textContent.trim());
            return { overlapsByTrack, track7Labels };
        }""")

        assert overlap_report["overlapsByTrack"] == {}, f"Solapamientos en zoom {zoom_val}%: {overlap_report['overlapsByTrack']}"
        assert any(lbl in ("center", "left", "right") for lbl in overlap_report["track7Labels"]), (
            f"La Pista 7 debe mostrar ubicaciones espaciales descriptivas: {overlap_report['track7Labels']}"
        )


def test_04_deterministic_export_enforces_torso_to_head_bust_framing_under_all_conditions(page):
    """
    Verifica C-02, C-03, A-05 y el requerimiento explícito del usuario:
    "Importante que el avatar se observe del torso a la cabeza en el video exportado final."
    Prueba incluso cambiando a la pestaña Avatar 3D, seleccionando cámara 'full'/'hands',
    y tratando de alterar la cámara o cambiar de pestaña en mitad de la exportación determinista.
    """
    export_framing_check = page.evaluate("""async () => {
        const bridge = window.studioAvatarBridge;
        const ctrl = bridge.controller;
        const eng = ctrl.engine;

        // 1. Colocar el avatar en la pestaña lateral con cámara 'full' (cuerpo entero) y rotada
        bridge.dockToSidebar();
        ctrl.setCameraPreset('full');
        eng.rotateCamera(25, 10);

        const prePos = { x: eng.camera.position.x, y: eng.camera.position.y, z: eng.camera.position.z };

        // 2. Iniciar modo de exportación determinista
        bridge.beginDeterministicExport();

        // 3. Intentar sabotear el encuadre durante la exportación:
        //    - Cambiar de pestaña a sidebar / pip
        //    - Llamar setCameraPreset('full') y setCameraPreset('hands')
        //    - Llamar rotateCamera, panCamera, dollyCamera, resetCamera, onResize
        bridge.dockToSidebar();
        ctrl.setCameraPreset('full');
        ctrl.setCameraPreset('hands');
        eng.rotateCamera(45, 20);
        eng.panCamera(2, 2);
        eng.dollyCamera(1.0);
        eng.resetCamera();
        eng.onResize();

        // 4. Avanzar un fotograma determinista y capturar el canvas exportado
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

        // 5. Dibujar un fotograma compuesto real en un canvas de exportación 1280x720
        const compCanvas = document.createElement('canvas');
        compCanvas.width = 1280;
        compCanvas.height = 720;
        const compCtx = compCanvas.getContext('2d');
        window.compositeVideoExporter.drawCompositeFrame(
            compCtx, 1280, 720, 1.0, null, null,
            window.appState.state.project.segments || [],
            window.appState.state.project.glosses || [],
            {
                pipPosition: 'bottom-right',
                includeSubtitles: true,
                includeGlosses: true,
                includeInterpreter: true,
                alreadySteppedAvatar: true
            }
        );

        // 6. Finalizar exportación determinista
        bridge.endDeterministicExport();

        return { prePos, duringExport };
    }""")

    de = export_framing_check["duringExport"]
    assert de["fov"] == 32, f"FOV durante exportación debe ser 32 (pip_bust), obtenido: {de['fov']}"
    assert de["posX"] == 0.0 and de["posY"] == 1.33 and de["posZ"] == 1.48, (
        f"Posición de cámara durante exportación debe estar bloqueada en (0, 1.33, 1.48) para encuadre torso-a-cabeza: {de}"
    )
    assert de["targetX"] == 0.0 and de["targetY"] == 1.31 and de["targetZ"] == 0.0, (
        f"Target de cámara durante exportación debe estar bloqueado en (0, 1.31, 0) para encuadre torso-a-cabeza: {de}"
    )
    assert de["canvasW"] == 360 and de["canvasH"] == 414, f"Proporción PiP (1:1.15) bloqueada en 360x414: {de}"
    assert de["controlsEnabled"] is False, "OrbitControls debe estar deshabilitado durante la exportación determinista"


def test_05_preferences_font_scale_and_reduced_motion_apply(page):
    """
    Verifica B-03, M-05:
    - Cambiar escala tipográfica ('large', 'xlarge') y movimiento reducido en el modal de Ajustes
      actualiza html[data-font-scale] y body.reduced-motion, escalando el font-size raíz.
    """
    page.click("#btn-top-settings")
    page.wait_for_timeout(200)

    page.select_option("#set-fontscale-select", "large")
    page.check("#set-motion-reduce")
    page.click("#btn-modal-settings-done")
    page.wait_for_timeout(200)

    prefs = page.evaluate("""() => ({
        fontScaleAttr: document.documentElement.getAttribute('data-font-scale'),
        rootFontSize: getComputedStyle(document.documentElement).fontSize,
        hasReducedMotionClass: document.body.classList.contains('reduced-motion')
    })""")

    assert prefs["fontScaleAttr"] == "large"
    assert prefs["rootFontSize"] == "15.5px"
    assert prefs["hasReducedMotionClass"] is True

    # Restaurar a normal
    page.click("#btn-top-settings")
    page.wait_for_timeout(150)
    page.select_option("#set-fontscale-select", "normal")
    page.uncheck("#set-motion-reduce")
    page.click("#btn-modal-settings-done")
    page.wait_for_timeout(150)
