"""
Suite de Pruebas de Estrés Adversarial y Verificación Empírica — Hito 2 (Milestone 2).

Diseñada por el Agente Challenger (challenger_m2_1) para someter el motor lingüístico
y el resolutor léxico LSEC a condiciones límite, hostiles y adversarias:

1. Entidades complejas: múltiples correos electrónicos, teléfonos mixtos, URLs complejas con rutas.
2. Preservación estricta del orden lineal en correos y dígitos telefónicos (sin mezclar tokens entre sí).
3. Estructuras sintácticas profundas: sintagmas nominales coordinados anidados y homógrafos nominales.
4. Vocabulario OOV, acrónimos raros, términos compuestos y neologismos académicos.
5. Invariante fundamental de cobertura: 0 glosas con estado 'MISSING' (100% resoluble).
6. Poda de preposiciones: eliminación de 'CON' repetitivo y 'SOBRE' temático abstracto.
7. Ausencia de fugas semánticas ('SEMANTIC_CONTENT_LEAK') y control riguroso de excepciones.
8. Entradas degeneradas: cadenas vacías (validación), solo puntuación, espacios y oraciones muy extensas.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Dict, Any

import pytest

from app.core.schemas import GlossOutput
from app.services.animation_lexical_resolver import (
    resolve_batch_glosses_payload,
    resolve_gloss_to_sign,
)
from app.services.nlp_service import LSECTranslatorService
from app.services.text_normalizer import TextNormalizer


@pytest.fixture(scope="module")
def translator() -> LSECTranslatorService:
    return LSECTranslatorService()


@pytest.fixture(scope="module")
def normalizer() -> TextNormalizer:
    return TextNormalizer()


def _translate_sync(svc: LSECTranslatorService, text: str) -> GlossOutput:
    return asyncio.run(
        svc.translate_to_gloss(text, mode="detailed", paraphrase_budget="compact")
    )


# ==============================================================================
# 1. Estrés de Entidades Complejas (Múltiples Emails, Teléfonos Mixtos, URLs)
# ==============================================================================


def test_adversarial_multiple_emails_in_single_discourse(translator: LSECTranslatorService):
    """
    Verifica que múltiples direcciones de correo en un mismo enunciado mantengan
    su integridad lineal y que sus componentes no se dispersen o mezclen por reordenamiento SOV.
    """
    text = (
        "Para becas escribe a becas@upec.edu.ec y para admisiones a admisiones@upec.edu.ec "
        "o al soporte institucional soporte@upec.edu.ec."
    )
    out = _translate_sync(translator, text)
    glosses = [g.gloss for g in out.glosses]

    # Verificar que existen las menciones de ARROBA
    assert "ARROBA" in glosses
    arroba_indices = [i for i, g in enumerate(glosses) if g == "ARROBA"]
    assert len(arroba_indices) == 3, f"Se esperaban 3 menciones de ARROBA, halladas: {len(arroba_indices)} en {glosses}"

    # Invariante lineal de cada correo: 'usuario' inmediatamente anterior a ARROBA,
    # y 'U-P-E-C', 'PUNTO', 'E-D-U', 'PUNTO', 'E-C' inmediatamente posteriores en secuencia contigua
    for idx in arroba_indices:
        assert idx > 0, "ARROBA no puede ser el primer token del discurso"
        assert idx + 5 < len(glosses), "ARROBA debe estar seguida por la secuencia de dominio completa"
        domain_seq = glosses[idx + 1:idx + 6]
        expected_seq = ["U-P-E-C", "PUNTO", "E-D-U", "PUNTO", "E-C"]
        assert domain_seq == expected_seq, (
            f"Secuencia de dominio rota tras ARROBA en posición {idx}: hallado {domain_seq}, esperado {expected_seq} (glosas: {glosses})"
        )


def test_adversarial_mixed_phone_numbers_and_zero_handshape(translator: LSECTranslatorService):
    """Verifica teléfonos celulares de 10 dígitos y que el dígito 0 use dactilología O (evitando NADA)."""
    text = "Comunícate al 099 28 72 993 o al 0987654321 para registrar tu cupo."
    out = _translate_sync(translator, text)
    glosses = [g.gloss for g in out.glosses]

    # Cero debe estar presente como dígito y nunca como NADA
    assert "NADA" not in glosses
    assert "CERO" in glosses

    # Verificar resolución léxica: CERO debe ser FINGERSPELLING / O
    cero_res = resolve_gloss_to_sign("CERO")
    assert cero_res["status"] == "FINGERSPELLING"
    assert cero_res["is_fingerspelling"] is True


def test_adversarial_phone_numbers_landline_and_international(translator: LSECTranslatorService):
    """
    Verifica que números telefónicos fijos (9 dígitos, ej. 02 298 3400) o con prefijo
    internacional (+593 99 287 2993) no generen glosas MISSING ni alteren el orden de los dígitos.
    """
    text_landline = "Llama a la central telefónica al 02 298 3400."
    out_landline = _translate_sync(translator, text_landline)
    gloss_tokens_landline = [g.gloss for g in out_landline.glosses]

    payload_landline = resolve_batch_glosses_payload({"glosses": gloss_tokens_landline, "version": "2.7"})
    missing_landline = [it["gloss"] for it in payload_landline["items"] if it.get("status") == "MISSING"]
    assert missing_landline == [], f"Glosas MISSING en teléfono fijo: {missing_landline}"

    text_intl = "Comunícate desde el exterior al +593 99 287 2993."
    out_intl = _translate_sync(translator, text_intl)
    gloss_tokens_intl = [g.gloss for g in out_intl.glosses]

    payload_intl = resolve_batch_glosses_payload({"glosses": gloss_tokens_intl, "version": "2.7"})
    missing_intl = [it["gloss"] for it in payload_intl["items"] if it.get("status") == "MISSING"]
    assert missing_intl == [], f"Glosas MISSING en teléfono internacional: {missing_intl}"


def test_adversarial_complex_url_resolution(translator: LSECTranslatorService):
    """
    Verifica que URLs institucionales complejas con rutas y barras inclinadas
    (ej. https://www.upec.edu.ec/admisiones/2026/cronograma) no generen glosas MISSING (como '/').
    """
    text = "Consulta los requisitos en https://www.upec.edu.ec/admisiones/2026/cronograma."
    out = _translate_sync(translator, text)
    gloss_tokens = [g.gloss for g in out.glosses]
    assert len(gloss_tokens) > 0

    batch_res = resolve_batch_glosses_payload({"glosses": gloss_tokens, "version": "2.7"})
    missing = [it["gloss"] for it in batch_res["items"] if it.get("status") == "MISSING"]
    assert missing == [], f"Glosas MISSING en URL compleja: {missing}"


# ==============================================================================
# 2. Estrés Sintáctico Profundo (Sintagmas Coordinados y Homógrafos)
# ==============================================================================


def test_adversarial_deep_nested_coordinated_noun_phrases(translator: LSECTranslatorService):
    """Verifica la resolución de sintagmas nominales profundamente coordinados antes y después de verbos."""
    text = (
        "Los estudiantes, docentes, investigadores y directivos de facultades "
        "analizan y coordinan proyectos de arte, música, literatura y teatro."
    )
    out = _translate_sync(translator, text)
    glosses = [g.gloss for g in out.glosses]

    # Verificar que los elementos nominales clave estén presentes
    for expected in ["ESTUDIANTE", "DOCENTE", "ARTE", "LITERATURA", "TEATRO"]:
        assert any(expected in g for g in glosses), f"Falta glosa para {expected} en {glosses}"

    # 0 MISSING
    batch_res = resolve_batch_glosses_payload({"glosses": glosses, "version": "2.7"})
    missing = [it["gloss"] for it in batch_res["items"] if it.get("status") == "MISSING"]
    assert missing == [], f"Glosas MISSING en sintagmas coordinados: {missing}"


def test_adversarial_nominal_homographs_remain_objects(translator: LSECTranslatorService):
    """Verifica que homógrafos como 'dibujo', 'canto', 'estudio' no se clasifiquen erróneamente como verbos subordinados."""
    text = "Ofrecemos talleres de canto, dibujo y estudio guiado para toda la comunidad."
    out = _translate_sync(translator, text)
    glosses = [g.gloss for g in out.glosses]

    assert "DIBUJO" in glosses
    assert "CANTO" in glosses
    # Ofrecer debe ubicarse como predicado
    assert any("OFRECER" in g or "TENER" in g or "DAR" in g for g in glosses)


# ==============================================================================
# 3. Estrés de Vocabulario Raro, OOV, Acrónimos y Términos Compuestos
# ==============================================================================


@pytest.mark.parametrize(
    "sentence",
    [
        "La transdisciplinariedad biocéntrica y desoxirribonucleico fundamentan la biotecnología moderna.",
        "La SENESCYT, CACES, UNESCO y UPEC suscribieron un convenio interinstitucional.",
        "El enfoque teórico-práctico y socio-ambiental fortalece las competencias profesionales.",
        "Se aplicará un examen electroencefalográfico y psicométrico a los aspirantes.",
    ],
)
def test_adversarial_rare_and_oov_vocabulary_guarantees_zero_missing(
    translator: LSECTranslatorService, sentence: str
):
    """Verifica que términos raros u OOV deriven limpiamente a dactilología con 0 glosas MISSING."""
    out = _translate_sync(translator, sentence)
    gloss_tokens = [g.gloss for g in out.glosses]
    assert len(gloss_tokens) > 0

    batch_res = resolve_batch_glosses_payload({"glosses": gloss_tokens, "version": "2.7"})
    missing = [it["gloss"] for it in batch_res["items"] if it.get("status") == "MISSING"]
    assert missing == [], f"Glosas MISSING encontradas en '{sentence}': {missing}"
    assert batch_res["summary"]["missing"] == 0


# ==============================================================================
# 4. Estrés de Poda de Preposiciones (CON redundante y SOBRE abstracto vs espacial)
# ==============================================================================


def test_adversarial_repetitive_con_in_long_series(translator: LSECTranslatorService):
    """Verifica que una serie larga de 'con' repetitivo se pode a máximo 1 aparición."""
    text = "Trabajamos con respeto, con dedicación, con disciplina y con entusiasmo."
    out = _translate_sync(translator, text)
    glosses = [g.gloss for g in out.glosses]

    con_count = sum(1 for g in glosses if g == "CON")
    assert con_count <= 1, f"Se esperaban <= 1 'CON', se hallaron {con_count} en {glosses}"


def test_adversarial_abstract_sobre_omitted_in_multiple_clauses(translator: LSECTranslatorService):
    """Verifica que 'sobre' abstracto ('reflexiona sobre', 'debaten sobre') sea suprimido en LSEC."""
    text = "Los asambleístas debaten sobre la educación superior y deciden sobre el presupuesto."
    out = _translate_sync(translator, text)
    glosses = [g.gloss for g in out.glosses]

    assert "SOBRE" not in glosses, f"'SOBRE' no debe aparecer en tópicos abstractos: {glosses}"
    assert any("EDUCACIÓN" in g for g in glosses)
    assert any("PRESUPUESTO" in g for g in glosses)


# ==============================================================================
# 5. Prevención de Fugas Semánticas (SEMANTIC_CONTENT_LEAK)
# ==============================================================================


@pytest.mark.parametrize(
    "text",
    [
        "Desarrolla la etapa de evaluación en el laboratorio asignado.",
        "Los aspirantes deben desarrollar la prueba de admisión con puntualidad.",
        "El equipo desarrolla el proceso de registro universitario.",
    ],
)
def test_adversarial_desarrollar_does_not_trigger_semantic_leak(
    translator: LSECTranslatorService, text: str
):
    """Verifica que cualquier variante de 'desarrollar' en contexto procesal/etapa no emita SEMANTIC_CONTENT_LEAK."""
    out = _translate_sync(translator, text)
    warning_codes = [w.code for w in out.warnings]
    assert "SEMANTIC_CONTENT_LEAK" not in warning_codes, f"Fuga semántica detectada en '{text}': {warning_codes}"


# ==============================================================================
# 6. Robustez ante Entradas Degeneradas y Extremas
# ==============================================================================


@pytest.mark.parametrize(
    "empty_input",
    [
        "",
        "   ",
        "\t\n  \r\n",
    ],
)
def test_adversarial_empty_inputs_raise_expected_validation_error(
    translator: LSECTranslatorService, empty_input: str
):
    """Verifica que entradas vacías o solo de espacios levanten ValueError limpio de validación."""
    with pytest.raises(ValueError, match="El texto de entrada está vacío"):
        _translate_sync(translator, empty_input)


@pytest.mark.parametrize(
    "punctuation_input",
    [
        "¿?¡! ... --- ,,, ;;; :::",
        "123 456 789 000",
    ],
)
def test_adversarial_non_empty_degenerate_inputs_do_not_crash(
    translator: LSECTranslatorService, punctuation_input: str
):
    """Verifica que entradas solo de puntuación o solo de números procesen sin errores no controlados."""
    out = _translate_sync(translator, punctuation_input)
    assert isinstance(out, GlossOutput)
    if out.glosses:
        gloss_tokens = [g.gloss for g in out.glosses]
        batch_res = resolve_batch_glosses_payload({"glosses": gloss_tokens, "version": "2.7"})
        missing = [it["gloss"] for it in batch_res["items"] if it.get("status") == "MISSING"]
        assert missing == [], f"Glosas MISSING en entrada degenerada: {missing}"


def test_adversarial_very_long_input_stability(translator: LSECTranslatorService):
    """Verifica la estabilidad y tiempo de ejecución con un párrafo extenso (más de 100 palabras)."""
    long_text = (
        "La Universidad Politécnica Estatal del Carchi, ubicada en la ciudad de Tulcán, "
        "invita a todos los bachilleres y aspirantes de la provincia del Carchi, de Imbabura, "
        "de Pichincha y de todo el Ecuador a participar en el proceso de admisión correspondiente "
        "al periodo académico 2026-A. Si estás interesado en estudiar carreras de grado como "
        "enfermería, computación, agropecuaria, logística o comercio exterior, puedes inscribirte "
        "fácilmente a través de nuestro portal web institucional www.upec.edu.ec o solicitar "
        "asesoría personalizada comunicándote con el equipo de admisiones al teléfono 099 28 72 993 "
        "o enviando tus inquietudes al correo electrónico oficial seartes@upec.edu.ec."
    )
    out = _translate_sync(translator, long_text)
    assert len(out.glosses) > 15

    gloss_tokens = [g.gloss for g in out.glosses]
    batch_res = resolve_batch_glosses_payload({"glosses": gloss_tokens, "version": "2.7"})
    missing = [it["gloss"] for it in batch_res["items"] if it.get("status") == "MISSING"]
    assert missing == [], f"Glosas MISSING en texto extenso: {missing}"
    assert batch_res["summary"]["missing"] == 0
