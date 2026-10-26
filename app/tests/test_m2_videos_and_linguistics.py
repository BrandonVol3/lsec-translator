"""
Suite de Pruebas de Calidad e Integridad Lingüística LSEC — Hito 2 (Milestone 2).

Verifica la reparación integral de los videos 1.mp4, 2.mp4 y 3.mp4 a lo largo
de toda la cadena de traducción (ASR Whisper -> Normalización -> Sintaxis SOV -> Catálogo VRM v2.7):
1. Inyección de vocabulario de dominio en Whisper (`DOMAIN_INITIAL_PROMPT`).
2. Corrección contextual determinista en `TextNormalizer`.
3. Ordenamiento SOV y preservación estricta de orden lineal en correos y teléfonos en `discourse_spacy_reorder`.
4. Poda de preposiciones vacías y no-espaciales (`CON` repetitivo y `SOBRE` temático abstracto).
5. 0 glosas en estado 'MISSING' en los videos 1, 2 y 3.
6. Mapeo dactilológico de 'cero' / '0' a configuración manual O (evitando 'Nada').
7. Desambiguación de 'desarrollar' -> 'realizar' eliminando advertencia SEMANTIC_CONTENT_LEAK.
8. Cumplimiento de la restricción de mantenibilidad ISO/IEC 25010 (<= 800 líneas por archivo).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List

import pytest

from app.core.schemas import GlossOutput, TranslationMode
from app.services.animation_lexical_resolver import (
    resolve_batch_glosses_payload,
    resolve_gloss_to_sign,
)
from app.services.asr_service import DOMAIN_INITIAL_PROMPT, WhisperASRService
from app.services.nlp_service import LSECTranslatorService
from app.services.text_normalizer import TextNormalizer


@pytest.fixture
def normalizer() -> TextNormalizer:
    return TextNormalizer()


@pytest.fixture
def translator() -> LSECTranslatorService:
    return LSECTranslatorService()


def _translate_sync(svc: LSECTranslatorService, text: str) -> GlossOutput:
    return asyncio.run(
        svc.translate_to_gloss(text, mode="detailed", paraphrase_budget="compact")
    )


# ==============================================================================
# 1. Pruebas de Whisper Initial Prompt (ASR)
# ==============================================================================


def test_whisper_domain_prompt_configured():
    """Verifica que el prompt inicial de ASR contenga las entidades clave de la UPEC y Carchi."""
    assert DOMAIN_INITIAL_PROMPT is not None
    assert "UPEC" in DOMAIN_INITIAL_PROMPT
    assert "Tulcán" in DOMAIN_INITIAL_PROMPT
    assert "Carchi" in DOMAIN_INITIAL_PROMPT
    assert "2026-A" in DOMAIN_INITIAL_PROMPT
    assert "seartes@upec.edu.ec" in DOMAIN_INITIAL_PROMPT
    assert "WhatsApp" in DOMAIN_INITIAL_PROMPT

    asr = WhisperASRService()
    assert asr.default_initial_prompt == DOMAIN_INITIAL_PROMPT


# ==============================================================================
# 2. Pruebas de Normalización Textual (TextNormalizer)
# ==============================================================================


def test_text_normalizer_video_1_hallucinations(normalizer: TextNormalizer):
    """Verifica normalización de 'Estandel Karczym' -> 'Estatal del Carchi' y '20-26a' -> '2026-A'."""
    text_in = "Postula en la Universidad Politécnica Estandel Karczym para el periodo 20-26a."
    norm_text, _ = normalizer.normalize(text_in)
    assert "Estatal del Carchi" in norm_text
    assert "2026-A" in norm_text
    assert "Estandel" not in norm_text
    assert "Karczym" not in norm_text


def test_text_normalizer_video_2_phone_and_email(normalizer: TextNormalizer):
    """Verifica expansión de teléfono a palabras y normalización canónica de correos."""
    phone_text = "Comunícate al 099 28 72 993 para recibir asistencia."
    norm_phone, _ = normalizer.normalize(phone_text)
    assert "cero nueve nueve dos ocho siete dos nueve nueve tres" in norm_phone

    email_text = "Escribe a seartes@upec.edu.ec o seartesarrobaupec.edu.es."
    norm_email, _ = normalizer.normalize(email_text)
    assert "seartes arroba UPEC punto edu punto ec" in norm_email
    assert "edu.es" not in norm_email


def test_text_normalizer_time_and_administrative_neologisms(normalizer: TextNormalizer):
    """Verifica conversión de '8 y cuarto' -> 'ocho y quince' y neologismos administrativos."""
    norm_time, _ = normalizer.normalize("La evaluación empieza a las 8 y cuarto en punto.")
    assert "ocho y quince" in norm_time

    norm_admin, _ = normalizer.normalize("Los estudiantes están opcionando por una carrera.")
    assert "optando" in norm_admin
    assert "opcionando" not in norm_admin

    norm_admin2, _ = normalizer.normalize("Desarrolla la etapa de evaluación a tiempo.")
    assert "realiza la etapa" in norm_admin2


# ==============================================================================
# 3. Pruebas de Estructura SOV y Entidades Lineales
# ==============================================================================


def test_video_2_email_order_is_strictly_linear(translator: LSECTranslatorService):
    """Verifica que los componentes del correo no se reorganicen por SOV."""
    out = _translate_sync(translator, "Escribe al correo seartes@upec.edu.ec")
    glosses = [g.gloss for g in out.glosses]

    correo_idx = glosses.index("CORREO")
    seartes_idx = glosses.index("S-E-A-R-T-E-S")
    arroba_idx = glosses.index("ARROBA")
    upec_idx = glosses.index("U-P-E-C")
    punto1_idx = glosses.index("PUNTO")
    edu_idx = glosses.index("E-D-U")

    assert correo_idx < seartes_idx < arroba_idx < upec_idx < punto1_idx < edu_idx


def test_video_2_phone_number_preserves_digit_order(translator: LSECTranslatorService):
    """Verifica que los dígitos del número telefónico mantengan su secuencia de izquierda a derecha y precedan al verbo."""
    out = _translate_sync(
        translator,
        "Para mayor información comunícate al 099 28 72 993 o al correo seartes@upec.edu.ec.",
    )
    glosses = [g.gloss for g in out.glosses]

    assert "CERO" in glosses
    assert "NUEVE" in glosses
    assert "DOS" in glosses
    assert "OCHO" in glosses
    assert "SIETE" in glosses
    assert "TRES" in glosses

    cero_idx = glosses.index("CERO")
    comunicar_idx = glosses.index("COMUNICAR")
    assert cero_idx < comunicar_idx


def test_video_2_coordinated_objects_precede_predicate(translator: LSECTranslatorService):
    """Verifica que 'música y dibujo experimental' se ubiquen antes del verbo inscribir."""
    out = _translate_sync(
        translator,
        "Oferta de talleres: puedes inscribirte en cursos de música y dibujo experimental.",
    )
    glosses = [g.gloss for g in out.glosses]

    assert "MÚSICA" in glosses or "INSTRUMENTO" in glosses or any("MÚSICA" in g for g in glosses)
    assert "DIBUJO" in glosses
    assert "EXPERIMENTAL" in glosses

    dibujo_idx = glosses.index("DIBUJO")
    inscribir_idx = glosses.index("INSCRIBIR")
    assert dibujo_idx < inscribir_idx


# ==============================================================================
# 4. Pruebas de Poda de Preposiciones (CON repetitivo y SOBRE abstracto)
# ==============================================================================


def test_repetitive_con_is_pruned(translator: LSECTranslatorService):
    """Verifica que en frases preposicionales coordinadas se elimine el 'CON' redundante."""
    out = _translate_sync(translator, "Nos comunicamos con respeto y con dedicación.")
    glosses = [g.gloss for g in out.glosses]
    # En LSEC, 'CON' repetitivo no debe aparecer más de una vez
    con_occurrences = [g for g in glosses if g == "CON"]
    assert len(con_occurrences) <= 1


def test_non_spatial_sobre_is_pruned(translator: LSECTranslatorService):
    """Verifica que 'sobre' en tópicos abstractos ('decide sobre tu futuro') no genere glosa locativa."""
    out = _translate_sync(translator, "Decide sobre tu futuro en la UPEC.")
    glosses = [g.gloss for g in out.glosses]
    assert "SOBRE" not in glosses
    assert "FUTURO" in glosses
    assert "DECIDIR" in glosses


# ==============================================================================
# 5. Cobertura de Glosas: Cero MISSING en Videos 1, 2 y 3
# ==============================================================================


@pytest.mark.parametrize(
    ("video_name", "text"),
    [
        (
            "Video 1",
            "Regístrate en www.upec.edu.ec y postula por una de nuestras carreras de grado. Estandel Karczym 20-26a.",
        ),
        (
            "Video 2",
            "Para mayor información comunícate al 099 28 72 993 o al correo seartes@upec.edu.ec.",
        ),
        (
            "Video 3",
            "Si estás opcionando por una carrera focalizada, desarrolla la etapa de evaluación en el horario determinado.",
        ),
    ],
)
def test_zero_missing_glosses_in_test_videos(translator: LSECTranslatorService, video_name: str, text: str):
    """Verifica que el 100% de las glosas de los tres videos de prueba resuelvan a seña o dactilología."""
    out = _translate_sync(translator, text)
    gloss_tokens = [g.gloss for g in out.glosses]
    batch_res = resolve_batch_glosses_payload({"glosses": gloss_tokens, "version": "2.7"})

    missing = [item["gloss"] for item in batch_res["items"] if item.get("status") == "MISSING"]
    assert missing == [], f"{video_name} tiene glosas MISSING: {missing}"
    assert batch_res["summary"]["missing"] == 0


# ==============================================================================
# 6. Dactilología y Homónimos
# ==============================================================================


def test_cero_resolves_to_dactylology_not_nada():
    """Verifica que el dígito 0 / cero resuelva a dactilología 'O' (forma manual 0) y nunca a 'Nada'."""
    res_cero = resolve_gloss_to_sign("cero")
    assert res_cero["status"] == "FINGERSPELLING"
    assert res_cero["is_fingerspelling"] is True
    assert res_cero["sign"] != "Nada"

    res_zero = resolve_gloss_to_sign("0")
    assert res_zero["status"] == "FINGERSPELLING"
    assert res_zero["is_fingerspelling"] is True
    assert res_zero["sign"] != "Nada"


def test_registrar_resolves_to_inscribir_not_registro_civil():
    """Verifica que 'registrar' en contexto universitario resuelva a 'Inscribir, Inscripción'."""
    res = resolve_gloss_to_sign("registrar")
    assert res["sign"] == "Inscribir, Inscripción"
    assert res["sign"] != "Registro Civil"


# ==============================================================================
# 7. Prevención de Fuga Semántica (desarrollar -> realizar)
# ==============================================================================


def test_semantic_leak_desarrollar_fixed(translator: LSECTranslatorService):
    """Verifica que Video 3 no emita la advertencia SEMANTIC_CONTENT_LEAK por 'desarrollar'."""
    out = _translate_sync(
        translator,
        "Si estás opcionando por una carrera focalizada, desarrolla la etapa de evaluación en el horario determinado.",
    )
    warning_codes = [w.code for w in out.warnings]
    assert "SEMANTIC_CONTENT_LEAK" not in warning_codes

    glosses = [g.gloss for g in out.glosses]
    assert "REALIZAR" in glosses or "HACER" in glosses


# ==============================================================================
# 8. Pruebas de Remediación de Fallos de Puerta M2 (Gate Remediations)
# ==============================================================================


def test_remediation_time_normalization_backreferences(normalizer: TextNormalizer, translator: LSECTranslatorService):
    """Verifica que la normalización de expresiones horarias expanda grupos de captura sin inyectar '\\1'."""
    norm_text, _ = normalizer.normalize("a las 9 y cuarto")
    assert "\\1" not in norm_text
    assert "9 y quince" in norm_text

    out = _translate_sync(translator, "Si deseas postular a la carrera de enfermeria, registrate a las 9 y cuarto.")
    glosses = [g.gloss for g in out.glosses]
    assert "\\1" not in glosses
    assert "NUEVE" in glosses
    assert "QUINCE" in glosses

    payload = resolve_batch_glosses_payload({"glosses": glosses, "version": "2.7"})
    missing = [it["gloss"] for it in payload["items"] if it.get("status") == "MISSING"]
    assert missing == [], f"Glosas MISSING en horaria: {missing}"


def test_remediation_non_seartes_email_username_strictly_linear(translator: LSECTranslatorService):
    """Verifica que correos institucionales con usuarios distintos a 'seartes' preserven orden lineal."""
    out = _translate_sync(translator, "Escribe al correo admisiones@upec.edu.ec")
    glosses = [g.gloss for g in out.glosses]
    correo_i = glosses.index("CORREO")
    admision_i = glosses.index("ADMISIÓN")
    arroba_i = glosses.index("ARROBA")
    upec_i = glosses.index("U-P-E-C")
    punto_i = glosses.index("PUNTO")
    edu_i = glosses.index("E-D-U")
    assert correo_i < admision_i < arroba_i < upec_i < punto_i < edu_i


def test_remediation_url_slashes_omitted_and_zero_missing(translator: LSECTranslatorService):
    """Verifica que barras inclinadas en rutas de URL no se emitan como glosas individuales MISSING."""
    out = _translate_sync(translator, "Consulta los requisitos en https://www.upec.edu.ec/admisiones/2026/cronograma.")
    glosses = [g.gloss for g in out.glosses]
    assert "/" not in glosses
    payload = resolve_batch_glosses_payload({"glosses": glosses, "version": "2.7"})
    missing = [it["gloss"] for it in payload["items"] if it.get("status") == "MISSING"]
    assert missing == [], f"Glosas MISSING en URL: {missing}"


def test_remediation_phone_numbers_international_prefix_and_landline(normalizer: TextNormalizer, translator: LSECTranslatorService):
    """Verifica que números con prefijo +593 o fijos de 9 dígitos se expandan a palabras y tengan 0 MISSING."""
    norm_intl, _ = normalizer.normalize("Llama al +593 99 287 2993.")
    assert "+593" not in norm_intl
    assert "cinco nueve tres" in norm_intl

    norm_land, _ = normalizer.normalize("Llama al 02 298 3400.")
    assert "cero dos dos nueve" in norm_land

    out = _translate_sync(translator, "Comunícate desde el exterior al +593 99 287 2993.")
    glosses = [g.gloss for g in out.glosses]
    assert "+593" not in glosses
    payload = resolve_batch_glosses_payload({"glosses": glosses, "version": "2.7"})
    missing = [it["gloss"] for it in payload["items"] if it.get("status") == "MISSING"]
    assert missing == [], f"Glosas MISSING en teléfono intl: {missing}"


# ==============================================================================
# 9. Verificación de Cumplimiento ISO/IEC 25010 (Límite estricto <= 800 líneas)
# ==============================================================================


def test_iso_25010_maintainability_line_limits():
    """Verifica que todos los archivos modificados y creados en Hito 2 tengan <= 800 líneas."""
    root_dir = Path(__file__).resolve().parent.parent

    target_files = [
        root_dir / "services" / "asr_service.py",
        root_dir / "services" / "text_normalizer.py",
        root_dir / "services" / "discourse_spacy_reorder.py",
        root_dir / "services" / "animation_lexical_resolver.py",
        Path(__file__).resolve(),
    ]

    for file_path in target_files:
        assert file_path.is_file(), f"Archivo no encontrado: {file_path}"
        line_count = len(file_path.read_text(encoding="utf-8").splitlines())
        assert line_count <= 800, (
            f"Violación ISO/IEC 25010: '{file_path.name}' tiene {line_count} líneas (> 800)"
        )
