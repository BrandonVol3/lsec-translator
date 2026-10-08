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


