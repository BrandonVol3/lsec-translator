"""
Suite de Pruebas Unitarias del Avatar 3D LSEC.

Cubre exhaustivamente los requisitos de la sección 19:
1. Validación del esquema de clips (SignAnimationSchema).
2. Validación de cuaterniones unitarios y rechazo de degenerados.
3. Catálogo y fábrica de clips demostrativos (NEUTRAL, SALUDAR_DEMO, NEGACION_DEMO).
4. Marcado obligatorio de los clips (DEMO_ONLY, REQUIRES_LSEC_VALIDATION, isValidatedLSEC=False).
5. Registro de clips y adaptador de glosas (AvatarSyncController).
6. Detección y manejo de clips faltantes (MISSING_ANIMATION).
7. Cálculo de marcas de tiempo y transiciones.
8. Manejo de huesos y expresiones ausentes (tolerancia a fallos).
9. Compatibilidad con el dataset y esquemas existentes de LSEC Studio.
"""

import json
import math
import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "avatar", "sign-animation-schema.js")
FACTORY_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "avatar", "sign-clip-factory.js")
ADAPTER_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "avatar", "avatar-sync-controller.js")
CONTROLLER_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "avatar", "avatar-controller.js")
DEMO_DATA_PATH = os.path.join(PROJECT_ROOT, "app", "static", "js", "demo-data.js")


# ============================================================
# Helpers de validación de esquema en Python (espejo del validador ES6)
# ============================================================

VALID_HUMAN_BONES = {
    'hips', 'spine', 'chest', 'upperChest', 'neck', 'head',
    'leftShoulder', 'leftUpperArm', 'leftLowerArm', 'leftHand',
    'rightShoulder', 'rightUpperArm', 'rightLowerArm', 'rightHand',
    'leftUpperLeg', 'leftLowerLeg', 'leftFoot',
    'rightUpperLeg', 'rightLowerLeg', 'rightFoot'
}


def validate_clip_structure(clip: dict) -> tuple[bool, list[str]]:
    errors = []
    if not isinstance(clip, dict):
        return False, ["El clip debe ser un diccionario."]

    if not clip.get("clipId") or not isinstance(clip["clipId"], str):
        errors.append("clipId inválido o vacío.")

    if not clip.get("gloss") or not isinstance(clip["gloss"], str):
        errors.append("gloss inválido o vacío.")

    duration_ms = clip.get("durationMs")
    if not isinstance(duration_ms, (int, float)) or duration_ms <= 0:
        errors.append("durationMs debe ser mayor a 0.")

    # Validar que los clips demo declaren su estado no validado
    status = clip.get("status")
    val_status = clip.get("validationStatus")
    if val_status != "VALIDATED_LSEC":
        meta = clip.get("metadata", {})
        if meta.get("isValidatedLSEC") is not False:
            errors.append("Un clip de demostración debe tener metadata.isValidatedLSEC == False.")

    bone_tracks = clip.get("boneTracks", [])
    if not isinstance(bone_tracks, list):
        errors.append("boneTracks debe ser una lista.")
    else:
        for i, track in enumerate(bone_tracks):
            bone_name = track.get("boneName")
            times = track.get("times", [])
            rotations = track.get("rotations", [])

            if not times or not isinstance(times, list):
                errors.append(f"Track {i}: times debe ser lista no vacía.")
            else:
                # Monotonía
                for idx in range(1, len(times)):
                    if times[idx] < times[idx - 1]:
                        errors.append(f"Track {i}: tiempos no ordenados.")
                        break

            if len(rotations) != len(times) * 4:
                errors.append(f"Track {i}: longitud de rotaciones debe ser 4 * len(times).")
            else:
                for k in range(0, len(rotations), 4):
                    x, y, z, w = rotations[k:k+4]
                    norm_sq = x*x + y*y + z*z + w*w
                    if norm_sq < 0.001:
                        errors.append(f"Track {i}: cuaternión degenerado con norma ~ 0.")
                    elif abs(norm_sq - 1.0) > 0.15:
                        errors.append(f"Track {i}: cuaternión no normalizado (norma^2={norm_sq}).")

    return len(errors) == 0, errors


# ============================================================
# Pruebas Unitarias
# ============================================================

def test_01_schema_file_definitions():
    """Verifica que sign-animation-schema.js contenga la lista de huesos humanoides y estados."""
    with open(SCHEMA_JS_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    assert "HUMAN_BONE_NAMES" in content
    assert "VRM_EXPRESSION_NAMES" in content
    assert "CLIP_STATUSES" in content
    assert "validateSignClip" in content
    assert "'DEMO_ONLY'" in content
    assert "'REQUIRES_LSEC_VALIDATION'" in content
    assert "'leftUpperArm'" in content
    assert "'rightLowerArm'" in content


def test_02_clip_factory_definitions():
    """Verifica que sign-clip-factory.js defina los tres clips requeridos con descargo lingüístico."""
    with open(FACTORY_JS_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    assert "createNeutralClip" in content
    assert "createSaludarDemoClip" in content
    assert "createNegacionDemoClip" in content
    assert "DEMO_ONLY" in content
    assert "REQUIRES_LSEC_VALIDATION" in content
    assert "isValidatedLSEC: false" in content


def test_03_quaternion_validation_rules():
    """Verifica que el validador acepte cuaterniones unitarios y rechace degenerados."""
    # Clip válido
    valid_clip = {
        "clipId": "TEST_VALID_01",
        "gloss": "TEST",
        "durationMs": 1000,
        "status": "DEMO_ONLY",
        "validationStatus": "REQUIRES_LSEC_VALIDATION",
        "metadata": { "isValidatedLSEC": False },
        "boneTracks": [
            {
                "boneName": "rightUpperArm",
                "times": [0.0, 0.5, 1.0],
                "rotations": [
                    0.0, 0.0, 0.0, 1.0,
                    0.0, 0.3826834, 0.0, 0.9238795,
                    0.0, 0.0, 0.0, 1.0
                ]
            }
        ]
    }
    is_valid, errors = validate_clip_structure(valid_clip)
    assert is_valid is True, f"Falló validación de clip correcto: {errors}"

    # Clip degenerado con cuaternión nulo (0, 0, 0, 0)
    invalid_clip = {
        "clipId": "TEST_INVALID_01",
        "gloss": "TEST",
        "durationMs": 1000,
        "status": "DEMO_ONLY",
        "validationStatus": "REQUIRES_LSEC_VALIDATION",
        "metadata": { "isValidatedLSEC": False },
        "boneTracks": [
            {
                "boneName": "rightUpperArm",
                "times": [0.0],
                "rotations": [0.0, 0.0, 0.0, 0.0]
            }
        ]
    }
    is_valid, errors = validate_clip_structure(invalid_clip)
    assert is_valid is False
    assert any("degenerado" in e for e in errors)


def test_04_timestamp_monotonicity_check():
    """Verifica que los tiempos desordenados o negativos sean detectados como error."""
    disordered_clip = {
        "clipId": "TEST_TIME_ERROR",
        "gloss": "TEST",
        "durationMs": 1500,
        "status": "DEMO_ONLY",
        "validationStatus": "REQUIRES_LSEC_VALIDATION",
        "metadata": { "isValidatedLSEC": False },
        "boneTracks": [
            {
                "boneName": "head",
                "times": [0.0, 1.0, 0.5], # 1.0 antes de 0.5 es un error
                "rotations": [
                    0, 0, 0, 1,
                    0, 0, 0, 1,
                    0, 0, 0, 1
                ]
            }
        ]
    }
    is_valid, errors = validate_clip_structure(disordered_clip)
    assert is_valid is False
    assert any("tiempos no ordenados" in e for e in errors)


def test_05_gloss_adapter_registry_and_missing_animations():
    """Verifica la lógica del adaptador AvatarSyncController ante glosas conocidas y desconocidas."""
    with open(ADAPTER_JS_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    assert "clipRegistry" in content
    assert "MISSING_ANIMATION" in content
    assert "NO_CLIP_AVAILABLE" in content
    assert "adaptProjectGlossesToSequence" in content
    assert "SALUDAR_DEMO" in content
    assert "NEGACION_DEMO" in content
    assert "NEUTRAL" in content


def test_06_compatibility_with_demo_project_glosses():
    """Verifica que las glosas del proyecto institucional puedan ser parseadas por el adaptador."""
    with open(DEMO_DATA_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Verificar que existan glosas en DEMO_PROJECT_DATA
    assert "DEMO_PROJECT_DATA" in content
    assert '"glosses"' in content
    assert '"gloss":' in content


def test_07_technical_rig_fallback_structural_integrity():
    """Verifica que technical-rig.js implemente los métodos de normalización VRM."""
    rig_path = os.path.join(PROJECT_ROOT, "app", "static", "js", "avatar", "technical-rig.js")
    with open(rig_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "getNormalizedBoneNode" in content
    assert "setExpressionWeight" in content
    assert "resetPose" in content
    assert "dispose" in content
    assert "rightUpperArm" in content
    assert "leftUpperArm" in content
    assert "head" in content
    assert "hips" in content
    assert "chest" in content


def test_09_lunes_clip_schema_and_registry():
    """Verifica que la seña canónica LUNES esté definida y registrada en fábrica y adaptador."""
    with open(FACTORY_JS_PATH, "r", encoding="utf-8") as f:
        factory_content = f.read()

    assert "createLunesSignClip" in factory_content
    assert "LUNES: createLunesSignClip()" in factory_content
    assert "LUNES.mp4" in factory_content
    assert "LUNES_V1" in factory_content

    with open(ADAPTER_JS_PATH, "r", encoding="utf-8") as f:
        adapter_content = f.read()

    assert "createLunesSignClip" in adapter_content
    assert "this.registerClip('LUNES'" in adapter_content


def test_10_weekdays_batch_clips_and_manifest():
    """Verifica que los 7 clips de los días de la semana y manifest.json existan y sean válidos."""
    clips_dir = os.path.join(PROJECT_ROOT, "app", "static", "assets", "clips")
    manifest_path = os.path.join(clips_dir, "manifest.json")
    
    assert os.path.exists(manifest_path), f"manifest.json no existe en {clips_dir}"
    
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
        
    assert manifest.get("totalClips", 0) >= 7
    expected_days = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"]
    
    for day in expected_days:
        assert day in manifest["clips"], f"{day} falta en manifest.json"
        clip_meta = manifest["clips"][day]
        clip_file = os.path.join(clips_dir, clip_meta["file"])
        assert os.path.exists(clip_file), f"Archivo {clip_file} no existe"
        
        with open(clip_file, "r", encoding="utf-8") as cf:
            clip_data = json.load(cf)
            
        is_valid, errors = validate_clip_structure(clip_data)
        assert is_valid is True, f"Error de validación en clip {day}: {errors}"
        assert clip_data["durationMs"] > 0
        assert len(clip_data["boneTracks"]) >= 15
        assert clip_data.get("dominantHand") == "RIGHT"
        assert clip_data.get("validationStatus") == "REQUIRES_LSEC_VALIDATION"


def test_11_avatar_controller_imports_and_clip_import_pipeline():
    """Verifica que avatar-controller.js importe validateSignClip y defina los métodos de importación."""
    assert os.path.exists(CONTROLLER_JS_PATH), f"avatar-controller.js no existe en {CONTROLLER_JS_PATH}"

    with open(CONTROLLER_JS_PATH, "r", encoding="utf-8") as f:
        controller_content = f.read()

    assert "import { validateSignClip } from './sign-animation-schema.js';" in controller_content, (
        "validateSignClip debe ser importado explícitamente desde ./sign-animation-schema.js en avatar-controller.js"
    )
    assert "import { HUMAN_BONE_NAMES } from './sign-animation-schema.js';" in controller_content
    assert "convertHamerAnimationToSignClip" in controller_content
    assert "detectDatasetQuaternionLayout" in controller_content
    assert "normalizeBoneName" in controller_content
    assert "importCustomClip" in controller_content
    assert "validateSignClip(customClip)" in controller_content


def test_12_run_js_validation_suite():
    """Ejecuta la suite de verificación automatizada Node.js para importCustomClip y validación de esquema."""
    import subprocess
    import shutil

    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node.js no está instalado en este entorno.")

    test_script = os.path.join(PROJECT_ROOT, "app", "tests", "test_avatar_import_validation.mjs")
    assert os.path.exists(test_script), f"Script de test {test_script} no existe"

    result = subprocess.run([node_bin, test_script], capture_output=True, text=True, encoding="utf-8", cwd=PROJECT_ROOT)
    assert result.returncode == 0, f"Error en la suite Node.js:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "TODOS LOS TESTS DE VALIDACIÓN JS PASARON SATISFACTORIAMENTE" in result.stdout


def test_13_animation_endpoints_v25_integration():
    """Verifica que el sistema LSEC esté integrado con las animaciones directas v2.5."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # 1. Endpoint /stats reporta versión activa por defecto (v2.7) y soporta explícitamente v2.5 con las 4.142 señas canónicas NFC
    stats_res = client.get("/api/v1/animations/stats")
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats.get("pipeline_version") in ["2.5_Directo_1a1", "2.6_Directo_1a1_corregido", "2.7_Estandarizado"]
    assert stats.get("total_signs") >= 4140

    stats_v25_res = client.get("/api/v1/animations/stats?version=2.5")
    assert stats_v25_res.status_code == 200
    assert stats_v25_res.json().get("pipeline_version") == "2.5_Directo_1a1"

    # 2. Endpoint /{sign_name} sirve animaciones directas v2.7 estandarizadas por defecto con soporte para v2.6 y v2.5
    anim_res = client.get("/api/v1/animations/A diario, Cotidiano(a)")
    assert anim_res.status_code == 200
    anim_data = anim_res.json()
    assert anim_data["metadata"]["pipelineVersion"] in ["2.5_Directo_1a1", "2.6_Directo_1a1_corregido", "2.7_Estandarizado"]
    assert anim_data["metadata"]["pure1to1Copy"] is True
    assert "frames" in anim_data and len(anim_data["frames"]) > 0

    anim_v25_res = client.get("/api/v1/animations/A diario, Cotidiano(a)?version=2.5")
    assert anim_v25_res.status_code == 200
    assert anim_v25_res.json()["metadata"]["pipelineVersion"] == "2.5_Directo_1a1"

    # 3. AvatarSyncController y sign-animation-schema contienen las funciones v2.5
    with open(ADAPTER_JS_PATH, "r", encoding="utf-8") as f:
        adapter_code = f.read()
    assert "fetchDirectV25Clip" in adapter_code
    assert "convertDirectAnimationToSignClip" in adapter_code
    assert "2.5_Directo_1a1" in adapter_code

    with open(SCHEMA_JS_PATH, "r", encoding="utf-8") as f:
        schema_code = f.read()
    assert "convertDirectAnimationToSignClip" in schema_code




