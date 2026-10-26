"""
Suite de Pruebas Adversariales y Verificación Empírica — Hito 3 (Milestone 3).

Autor: challenger_m3_1 (Role: teamwork_preview_challenger)
Objetivo: Someter a estrés adversarial agresivo el subsistema de desambiguación de homónimos
y blindaje morfológico (Features 13, 14, 15):
1. Sensibilidad a mayúsculas, minúsculas, tildes, signos de interrogación, exclamación y puntuación.
2. Ataque de falso lema / sobre-lematización (false stem attack):
   - cola, col, colas
   - medio, media, medios, medias
   - cura, curas, curar
3. Test de colisión de las 23 carpetas con calificadores de dominio ', De ':
   Verificar que para TODOS los lemas base de las 23 carpetas, la resolución sin contexto
   NUNCA produzca una acepción restringida ni colisión semántica indebida.
4. Pruebas de límite con tokens inusuales, numéricos ('0', '00', 'cero'), vacíos y degenerados.
5. Robustez contextual adversarial con ruido, puntuación, mayúsculas y stopwords.
6. Cumplimiento de límites de líneas ISO/IEC 25010 (<= 800 líneas).
"""

from __future__ import annotations

import re
import pytest
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.animation_catalog_service import get_v27_dir, normalize_text
from app.services.animation_lexical_resolver import (
    _generate_morphological_candidates,
    resolve_batch_glosses_payload,
    resolve_gloss_to_sign,
)
from app.services.dictionary_service import LSECDictionaryService, get_dictionary_service
from app.services.lexical_homonym_rules import (
    DEFAULT_BASE_RESOLUTIONS,
    RESTRICTED_DOMAIN_QUALIFIERS_23,
    SHIELDED_4LETTER_NOUNS,
    is_restricted_domain_folder,
    is_shielded_4letter_noun,
    resolve_homonym_with_context,
)


@pytest.fixture(scope="module")
def dict_svc() -> LSECDictionaryService:
    return get_dictionary_service()


# ==============================================================================
# 1. PUNTUACIÓN, MAYÚSCULAS/MINÚSCULAS, SIGNOS ADVERSARIALES Y TILDES
# ==============================================================================


@pytest.mark.parametrize(
    "token,expected_sign,is_fs",
    [
        ("CARRERA", "Carrera, Estudios", False),
        ("Carrera!", "Carrera, Estudios", False),
        ("¡CARRERA!", "Carrera, Estudios", False),
        ("¿carrera?", "Carrera, Estudios", False),
        ("cola...", None, True),
        ("¡COLA!", None, True),
        ("¿cola?", None, True),
        ("¿Medio?", "Mitad", False),
        ("MEDIO", "Mitad", False),
        ("¡medio!", "Mitad", False),
        ("MÉDIO", "Mitad", False),
        ("0", None, True),
        ("00", None, True),
        ("cero", None, True),
        ("CERO", None, True),
        ("¡cero!", None, True),
        ("¿CERO?", None, True),
        ("LIMPIO", "Limpiar, Limpio", False),
        ("¡Limpio!", "Limpiar, Limpio", False),
        ("MENOS", "Menos, De menor cantidad", False),
        ("¿Menos?", "Menos, De menor cantidad", False),
        ("RECETA", "Receta, De médico", False),
        ("¡Receta!", "Receta, De médico", False),
        ("RATÓN", "Ratón", False),
        ("raton...", "Ratón", False),
        ("¿RATÓN?", "Ratón", False),
    ],
)
def test_adversarial_casing_punctuation_and_accents(
    token: str, expected_sign: Optional[str], is_fs: bool
):
    """
    Verifica que la normalización sea robusta frente a mayúsculas, tildes y puntuación agresiva
    sin perder la resolución canónica ni desviar a dominios restringidos.
    """
    res = resolve_gloss_to_sign(token, include_animation=False)
    actual_sign = res.get("sign")
    actual_fs = res.get("is_fingerspelling")

    if expected_sign is not None:
        assert actual_sign == expected_sign, (
            f"Fallo de resolución para '{token}': obtenido '{actual_sign}', "
            f"esperado '{expected_sign}'"
        )
    else:
        assert actual_sign != "Col", f"CRÍTICO: '{token}' resolvió a 'Col'!"
        assert actual_sign != "Nada", f"CRÍTICO: '{token}' resolvió a 'Nada'!"

    assert actual_fs == is_fs, (
        f"Fallo de flag is_fingerspelling para '{token}': obtenido {actual_fs}, esperado {is_fs}"
    )


# ==============================================================================
# 2. ATAQUE DE FALSO LEMA / SOBRE-LEMATIZACIÓN (FALSE STEM ATTACK)
# ==============================================================================


def test_false_stem_attack_cola_family():
    """
    Familia 'cola':
    - 'cola' -> fingerspelling (NUNCA 'Col')
    - 'col' -> 'Col' (verdura/repollo)
    - 'colas' -> NUNCA 'Col'
    """
    # 1. cola
    res_cola = resolve_gloss_to_sign("cola")
    assert res_cola.get("sign") != "Col", "CRÍTICO: 'cola' resolvió a 'Col'!"
    assert res_cola.get("is_fingerspelling") is True

    # 2. col
    res_col = resolve_gloss_to_sign("col")
    assert res_col.get("sign") == "Col", f"'col' debe resolver a verdura 'Col', obtenido {res_col.get('sign')}"

    # 3. colas (plural)
    cands_colas = _generate_morphological_candidates("colas")
    assert "col" not in cands_colas, f"'col' encontrado en candidatos morfológicos de 'colas': {cands_colas}"
    res_colas = resolve_gloss_to_sign("colas")
    assert res_colas.get("sign") != "Col", f"CRÍTICO: 'colas' resolvió a 'Col'! res={res_colas}"


def test_false_stem_attack_medio_family():
    """
    Familia 'medio':
    - 'medio' -> 'Mitad' (NUNCA 'Media' de calcetín)
    - 'media' -> 'Media'
    - 'medios' -> NUNCA 'Media' (calcetín)
    - 'medias' -> 'Media' (calcetines / ropa)
    """
    # 1. medio
    res_medio = resolve_gloss_to_sign("medio")
    assert res_medio.get("sign") == "Mitad", f"Esperado 'Mitad', obtenido {res_medio.get('sign')}"
    assert res_medio.get("sign") != "Media"

    # 2. media
    res_media = resolve_gloss_to_sign("media")
    assert res_media.get("sign") == "Media", f"Esperado 'Media', obtenido {res_media.get('sign')}"

    # 3. medios
    res_medios = resolve_gloss_to_sign("medios")
    assert res_medios.get("sign") != "Media", f"CRÍTICO: 'medios' resolvió a 'Media' (calcetín)! res={res_medios}"

    # 4. medias
    res_medias = resolve_gloss_to_sign("medias")
    assert res_medias.get("sign") == "Media", f"Esperado 'Media', obtenido {res_medias.get('sign')}"


def test_false_stem_attack_cura_family():
    """
    Familia 'cura':
    - 'cura' -> 'Curar, Curación' (NUNCA 'Papa, Cura' sin contexto eclesiástico)
    - 'curas' -> 'Curar, Curación' o dactilología (NUNCA 'Papa, Cura' sin contexto)
    - 'curar' -> 'Curar, Curación'
    """
    # 1. cura
    res_cura = resolve_gloss_to_sign("cura")
    assert res_cura.get("sign") == "Curar, Curación"
    assert res_cura.get("sign") != "Papa, Cura"

    # 2. curas
    res_curas = resolve_gloss_to_sign("curas")
    assert res_curas.get("sign") != "Papa, Cura", (
        f"CRÍTICO: 'curas' resolvió a 'Papa, Cura'! res={res_curas}"
    )

    # 3. curar
    res_curar = resolve_gloss_to_sign("curar")
    assert res_curar.get("sign") == "Curar, Curación"


def test_shielded_4letter_nouns_comprehensive():
    """
    Comprueba que ninguno de los sustantivos de 4 letras de la lista sea truncado a 3 letras.
    """
    for noun in sorted(SHIELDED_4LETTER_NOUNS):
        cands = _generate_morphological_candidates(noun)
        stem_3 = noun[:-1]
        assert stem_3 not in cands, f"Truncación espuria '{stem_3}' generada para '{noun}': {cands}"


# ==============================================================================
# 3. TEST DE COLISIÓN DE LAS 23 CARPETAS ', De ' Y SUS LEMAS BASE
# ==============================================================================


# Mapeo exhaustivo de los lemas base de las 23 carpetas con calificador de dominio
# a sus señas canónicas esperadas y señas estrictamente prohibidas por defecto.
BASE_WORDS_AUDIT_MAP: List[Dict[str, Any]] = [
    {
        "base_words": ["acuerdo", "de acuerdo"],
        "restricted": set(),  # "Acuerdo, De acuerdo" es la única entrada léxica
        "expected": "Acuerdo, De acuerdo",
    },
    {
        "base_words": ["babear", "baboso"],
        "restricted": {"Babear, De atracción"},
        "expected": "Babear, Baboso(a)",
    },
    {
        "base_words": ["babosa"],
        "restricted": {"Babear, De atracción"},
        "expected": "Babosa",
    },
    {
        "base_words": ["blanco", "blanca"],
        "restricted": {"Blanco(a), De piel clara"},
        "expected": "Blanco(a)",
    },
    {
        "base_words": ["buen provecho"],
        "restricted": {"Buen provecho, De alimento"},
        "expected": "Buen provecho",
    },
    {
        "base_words": ["carrera"],
        "restricted": {"Carrera, De autos", "Carrera, De competencia"},
        "expected": "Carrera, Estudios",
    },
    {
        "base_words": ["explotar", "explosion", "explosión"],
        "restricted": {"Explotar, De desahogarse"},
        "expected": "Explotar, Explosión",
    },
    {
        "base_words": ["facil", "fácil"],
        "restricted": {"Fácil, De expresión"},
        "expected": "Fácil",
    },
    {
        "base_words": ["igual"],
        "restricted": {"Igual, De idéntico"},
        "expected": "Igual",
    },
    {
        "base_words": ["limpio", "limpia", "limpiar"],
        "restricted": {"Limpio, De honesto"},
        "expected": "Limpiar, Limpio",
    },
    {
        "base_words": ["llamar"],
        "restricted": {"Lamar, De teléfono", "Llamar, De teléfono"},
        "expected": "Llamar, De acudir",
    },
    {
        "base_words": ["mayor"],
        "restricted": {"Mayor, De grado"},
        "expected": "Mayor",
    },
    {
        "base_words": ["menos"],
        "restricted": {"Menos, De la matemáticas"},
        "expected": "Menos, De menor cantidad",
    },
    {
        "base_words": ["mas", "más"],
        "restricted": {"Más, De comparación"},
        "expected": "Más",
    },
    {
        "base_words": ["no"],
        "restricted": set(),
        "expected": "No, De negación",
    },
    {
        "base_words": ["opcion", "opción"],
        "restricted": {"Opción, De línea"},
        "expected": "Alternativa, Opción",
    },
    {
        "base_words": ["polvo"],
        "restricted": {"Polvo, De cosmético"},
        "expected": "Polvo",
    },
    {
        "base_words": ["raton", "ratón"],
        "restricted": {"Ratón, De computador"},
        "expected": "Ratón",
    },
    {
        "base_words": ["receta"],
        "restricted": {"Receta, Recetario de cocina"},
        "expected": "Receta, De médico",
    },
    {
        "base_words": ["rapido", "rápido", "rapida", "rápida"],
        "restricted": {"Rápido(a), De velocidad"},
        "expected": "Rápido(a), Un acontecimiento veloz",
    },
    {
        "base_words": ["torre"],
        "restricted": {"Torre, De cd o dvd"},
        "expected": "Torre",
    },
]


def test_all_23_base_words_never_resolve_to_restricted_qualifiers_without_context(
    dict_svc: LSECDictionaryService,
):
    """
    Verifica sistemáticamente que TODOS los lemas base asociados a las 23 carpetas ', De '
    nunca colisionen hacia sus acepciones restringidas cuando no se aporta contexto.
    """
    total_tested = 0
    for entry in BASE_WORDS_AUDIT_MAP:
        base_words = entry["base_words"]
        restricted_senses = entry["restricted"]
        expected_canonical = entry["expected"]

        for bw in base_words:
            total_tested += 1
            # 1. Probar en AnimationLexicalResolver
            res = resolve_gloss_to_sign(bw, include_animation=False)
            resolved_sign = res.get("sign")

            assert resolved_sign is not None, f"Lema base '{bw}' devolvió None"
            assert resolved_sign not in restricted_senses, (
                f"COLISIÓN RESTRINGIDA EN RESOLVER: '{bw}' resolvió a '{resolved_sign}', "
                f"el cual está en el conjunto restringido prohibido: {restricted_senses}"
            )
            assert resolved_sign == expected_canonical, (
                f"Desviación canónica para '{bw}': obtenido '{resolved_sign}', "
                f"esperado '{expected_canonical}'"
            )

            # 2. Probar en DictionaryService
            dm = dict_svc.lookup(bw)
            if dm and dm.entry:
                assert dm.entry.title not in restricted_senses, (
                    f"COLISIÓN RESTRINGIDA EN CONADIS: '{bw}' resolvió a '{dm.entry.title}', "
                    f"prohibido: {restricted_senses}"
                )

    assert total_tested >= 28, f"Se esperaban al menos 28 variantes de lemas base, probadas {total_tested}"


# ==============================================================================
# 4. ROBUSTEZ CONTEXTUAL ADVERSARIAL (RUIDO, STOPWORDS, PUNTUACIÓN, MAYÚSCULAS)
# ==============================================================================


@pytest.mark.parametrize(
    "term,adversarial_context,expected_sign",
    [
        # Contexto ruidoso con puntuación, mayúsculas y stopwords
        ("raton", "¡El MOUSE USB de la COMPUTADORA portátil falló ayer!", "Ratón, De computador"),
        ("raton", "¿Viste ese gato cazando un roedor en la cueva?", "Ratón"),
        ("llamar", "Por favor, CONTÁCTAME AL WHATSAPP o envíame una LLAMADA telefónica...", "Llamar, De teléfono"),
        ("llamar", "¡Oiga, señor! Acérquese aquí a la oficina, por favor.", "Llamar, De acudir"),
        ("carrera", "Gran Premio de FÓRMULA 1: pilotos de automovilismo en el circuito.", "Carrera, De autos"),
        ("carrera", "Estudió la LICENCIATURA en la UNIVERSIDAD UPEC.", "Carrera, Estudios"),
        ("carrera", "Maratón de 100 metros: atletas de velocidad en pista.", "Carrera, De competencia"),
        ("receta", "El CHEF compartió los INGREDIENTES de la sopa en la cocina.", "Receta, Recetario de cocina"),
        ("receta", "El MÉDICO recetó pastillas en la farmacia de la clínica.", "Receta, De médico"),
        ("limpio", "Un funcionario con CONDUCTA ÉTICA, moral y transparente.", "Limpio, De honesto"),
        ("limpio", "Lavar el piso del baño con jabón y agua para sacar la suciedad.", "Limpiar, Limpio"),
        ("menos", "En la clase de ÁLGEBRA aprendimos la operación de RESTA.", "Menos, De la matemáticas"),
        ("menos", "Hubo una REDUCCIÓN en la CANTIDAD de agua disponible.", "Menos, De menor cantidad"),
        ("blanco", "Una persona de TEZ CLARA de origen caucásico.", "Blanco(a), De piel clara"),
        ("blanco", "Pintar la PARED de la sala con COLOR claro.", "Blanco(a)"),
        ("explotar", "Estaba bajo mucho ESTRÉS y estalló en LLANTO de rabia.", "Explotar, De desahogarse"),
        ("explotar", "La BOMBA causó una DETONACIÓN destructiva.", "Explotar, Explosión"),
        ("babear", "Quedó fascinado por la BELLEZA de la chica guapa.", "Babear, De atracción"),
        ("babear", "El bebé dormido tenía SALIVA en la boca.", "Babear, Baboso(a)"),
        ("torre", "Guardar los discos grabados en un estuche para CD / DVD.", "Torre, De cd o dvd"),
        ("torre", "El CAMPUS universitario tiene un EDIFICIO con vista panorámica.", "Torre"),
        ("polvo", "Aplicar el MAQUILLAJE con brocha sobre el rostro.", "Polvo, De cosmético"),
        ("polvo", "Barrer la TIERRA y el suelo sucio con la escoba.", "Polvo"),
    ],
)
def test_adversarial_context_token_extraction(
    term: str, adversarial_context: str, expected_sign: str
):
    """
    Verifica que la extracción de tokens contextuales funcione correctamente
    incluso cuando el contexto está inmerso en oraciones complejas con mayúsculas,
    puntuación y palabras vacías.
    """
    res = resolve_gloss_to_sign(term, context=adversarial_context, include_animation=False)
    actual_sign = res.get("sign")
    assert actual_sign == expected_sign, (
        f"Fallo de resolución contextual para '{term}' con contexto '{adversarial_context}': "
        f"obtenido '{actual_sign}', esperado '{expected_sign}'"
    )


# ==============================================================================
# 5. CASOS BORDE Y TOKENS EXTRAÑOS / DEGENERADOS
# ==============================================================================


def test_adversarial_degenerate_and_boundary_inputs():
    """
    Somete a prueba entradas degeneradas: vacías, espacios, caracteres extraños,
    números repetidos, cadenas extremadamente largas.
    """
    # 1. Cadenas vacías o solo espacios
    res_empty = resolve_gloss_to_sign("")
    assert res_empty["status"] == "EMPTY"
    assert res_empty["found"] is False

    res_spaces = resolve_gloss_to_sign("     ")
    assert res_spaces["status"] == "EMPTY"
    assert res_spaces["found"] is False

    # 2. Puntuación pura
    res_punct = resolve_gloss_to_sign("???!!!.,")
    assert res_punct["found"] is False
    assert res_punct["status"] in ("MISSING", "FINGERSPELLING")

    # 3. Números repetidos
    res_zeros = resolve_gloss_to_sign("000")
    assert res_zeros["is_fingerspelling"] is True
    assert res_zeros["sign"] != "Nada"

    # 4. Cadena larga
    long_gloss = "supercalifragilisticoespialidoso" * 3
    res_long = resolve_gloss_to_sign(long_gloss)
    assert res_long["found"] is False
    assert res_long["status"] in ("MISSING", "FINGERSPELLING")


# ==============================================================================
# 6. AUDITORÍA ISO/IEC 25010 DE LÍMITES DE LÍNEAS (<= 800 LÍNEAS)
# ==============================================================================


def test_iso_25010_file_line_limits():
    """
    Garantiza que ningún archivo involucrado en Milestone 3 supere el límite
    arquitectónico de 800 líneas.
    """
    target_files = [
        Path("app/services/lexical_homonym_rules.py"),
        Path("app/services/animation_lexical_resolver.py"),
        Path("app/services/dictionary_service.py"),
        Path("app/tests/test_r3_homonym_disambiguation.py"),
        Path("app/tests/test_adversarial_m3.py"),
    ]

    for rel_path in target_files:
        assert rel_path.is_file(), f"Archivo no encontrado: {rel_path}"
        line_count = len(rel_path.read_text(encoding="utf-8").splitlines())
        assert line_count <= 800, (
            f"VIOLACIÓN ISO/IEC 25010: {rel_path} tiene {line_count} líneas (> 800)!"
        )
