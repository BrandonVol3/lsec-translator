"""
Suite de Pruebas de Regresión R3: Desambiguación de Homónimos CONADIS / v2.7.

Valida exhaustivamente:
  1. Que los 23 calificadores de dominio ", De " nunca colisionen hacia acepciones restringidas por defecto.
  2. Que los términos críticos ("carrera", "limpio", "menos", "receta", "raton", "cola", "medio", "cura", "registrar", "cero")
     resuelvan con precisión léxica y semántica.
  3. Que la resolución contextual opere cuando se aportan tokens de dominio temático.
  4. Que el generador morfológico esté blindado contra derivaciones espurias (cola != col, medio != media).
  5. Que el servicio de diccionario CONADIS priorice las acepciones genéricas sobre las restringidas.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

from app.services.animation_catalog_service import get_v27_dir
from app.services.animation_lexical_resolver import (
    _generate_morphological_candidates,
    resolve_batch_glosses_payload,
    resolve_gloss_to_sign,
)
from app.services.dictionary_service import LSECDictionaryService, get_dictionary_service
from app.services.lexical_homonym_rules import (
    RESTRICTED_DOMAIN_QUALIFIERS_23,
    SHIELDED_4LETTER_NOUNS,
    is_restricted_domain_folder,
    is_shielded_4letter_noun,
    resolve_homonym_with_context,
)


@pytest.fixture(scope="module")
def dict_svc() -> LSECDictionaryService:
    return get_dictionary_service()


def test_all_23_folders_exist_in_v27_catalog():
    """Verifica que las 23 carpetas con calificador ', De ' existen en el catálogo VRM v2.7."""
    v27_dir = get_v27_dir()
    assert v27_dir is not None and v27_dir.is_dir(), f"Directorio v2.7 no encontrado: {v27_dir}"
    existing_folders = {f.name for f in v27_dir.iterdir() if f.is_dir()}

    missing = [f for f in RESTRICTED_DOMAIN_QUALIFIERS_23 if f not in existing_folders]
    assert len(missing) == 0, f"Carpetas v2.7 faltantes ({len(missing)}): {missing}"


def test_all_23_base_terms_avoid_restricted_senses_by_default(dict_svc: LSECDictionaryService):
    """
    Verifica que al consultar los términos base de las 23 entradas con ', De '
    ninguno resuelva por defecto a su acepción restringida.
    """
    test_cases: List[Tuple[str, str, str]] = [
        # (base_term, expected_canonical_default, forbidden_restricted_sense)
        ("limpio", "Limpiar, Limpio", "Limpio, De honesto"),
        ("menos", "Menos, De menor cantidad", "Menos, De la matemáticas"),
        ("receta", "Receta, De médico", "Receta, Recetario de cocina"),
        ("carrera", "Carrera, Estudios", "Carrera, De autos"),
        ("blanco", "Blanco(a)", "Blanco(a), De piel clara"),
        ("explotar", "Explotar, Explosión", "Explotar, De desahogarse"),
        ("polvo", "Polvo", "Polvo, De cosmético"),
        ("torre", "Torre", "Torre, De cd o dvd"),
        ("babear", "Babear, Baboso(a)", "Babear, De atracción"),
        ("llamar", "Llamar, De acudir", "Llamar, De teléfono"),
        ("raton", "Ratón", "Ratón, De computador"),
        ("facil", "Fácil", "Fácil, De expresión"),
        ("igual", "Igual", "Igual, De idéntico"),
        ("mayor", "Mayor", "Mayor, De grado"),
        ("mas", "Más", "Más, De comparación"),
        ("no", "No, De negación", "No"),
        ("opcion", "Alternativa, Opción", "Opción, De línea"),
        ("rapido", "Rápido(a), Un acontecimiento veloz", "Rápido(a), De velocidad"),
        ("buen provecho", "Buen provecho", "Buen provecho, De alimento"),
        ("acuerdo", "Acuerdo, De acuerdo", ""),
    ]

    for base_term, expected_default, forbidden in test_cases:
        res = resolve_gloss_to_sign(base_term, include_animation=False)
        resolved_sign = res.get("sign")

        assert resolved_sign is not None, f"Término '{base_term}' no resolvió a ninguna seña"
        if forbidden:
            assert resolved_sign != forbidden, (
                f"COLISIÓN RESTRINGIDA: '{base_term}' resolvió a '{resolved_sign}', "
                f"se esperaba '{expected_default}' y nunca '{forbidden}'"
            )
        assert resolved_sign == expected_default, (
            f"Término '{base_term}' resolvió a '{resolved_sign}', se esperaba '{expected_default}'"
        )

        # Verificar también en DictionaryService
        dm = dict_svc.lookup(base_term)
        if dm and forbidden:
            assert dm.entry.title != forbidden, (
                f"COLISIÓN EN DICCIONARIO: '{base_term}' resolvió en CONADIS a '{dm.entry.title}', "
                f"prohibido '{forbidden}'"
            )


def test_contextual_disambiguation_matrix():
    """Valida la resolución contextual guiada por tokens temáticos."""
    matrix: List[Tuple[str, Optional[str], str]] = [
        # Informática vs. roedor
        ("raton", "computadora teclado software oficina", "Ratón, De computador"),
        ("raton", "gato queso roedor trampa", "Ratón"),
        ("raton", None, "Ratón"),
        # Teléfono vs. acudir
        ("llamar", "telefono celular llamada whatsapp timbre", "Llamar, De teléfono"),
        ("llamar", "persona acudir venir gritar", "Llamar, De acudir"),
        ("llamar", None, "Llamar, De acudir"),
        # Estudios vs. deportes de motor vs. atletismo
        ("carrera", "formula 1 autos rally vehiculos pista", "Carrera, De autos"),
        ("carrera", "atletismo correr maraton competencia", "Carrera, De competencia"),
        ("carrera", "Maratón de 100 metros: atletas de velocidad en pista.", "Carrera, De competencia"),
        ("carrera", "universidad upec facultad grado", "Carrera, Estudios"),
        ("carrera", None, "Carrera, Estudios"),
        # Gastronomía vs. prescripción médica
        ("receta", "cocina chef comida hornear plato", "Receta, Recetario de cocina"),
        ("receta", "medico farmacia pastilla hospital", "Receta, De médico"),
        ("receta", None, "Receta, De médico"),
        # Moralidad vs. higiene
        ("limpio", "honesto transparencia corrupcion integridad", "Limpio, De honesto"),
        ("limpio", "jabon lavar aseo suciedad ropa", "Limpiar, Limpio"),
        ("limpio", None, "Limpiar, Limpio"),
        # Aritmética vs. reducción cuantitativa
        ("menos", "matematicas resta restar signo calculo", "Menos, De la matemáticas"),
        ("menos", "menor cantidad poco reducir disminuir", "Menos, De menor cantidad"),
        ("menos", None, "Menos, De menor cantidad"),
        # Piel clara vs. color
        ("blanco", "piel tez clara caucasico raza", "Blanco(a), De piel clara"),
        ("blanco", "color pintura pared hoja", "Blanco(a)"),
        ("blanco", None, "Blanco(a)"),
        # Emocional vs. detonación
        ("explotar", "desahogo llanto rabia estres ira", "Explotar, De desahogarse"),
        ("explotar", "bomba dinamita volcan detonacion", "Explotar, Explosión"),
        ("explotar", None, "Explotar, Explosión"),
        # Atracción erótica vs. fisiológico
        ("babear", "atraccion enamorar gusto linda guapo", "Babear, De atracción"),
        ("babear", "saliva boca dormir bebe", "Babear, Baboso(a)"),
        ("babear", None, "Babear, Baboso(a)"),
        # CD/DVD vs. edificio
        ("torre", "cd dvd disco discos estuche", "Torre, De cd o dvd"),
        ("torre", "edificio campus arquitectura castillo", "Torre"),
        ("torre", None, "Torre"),
        # Cosmético vs. polvo ambiental
        ("polvo", "cosmetico maquillaje belleza rostro", "Polvo, De cosmético"),
        ("polvo", "tierra suciedad aire barrer", "Polvo"),
        ("polvo", None, "Polvo"),
        # Entidad financiera vs. asiento de parque
        ("banco", "dinero cuenta finanzas prestamo cajero", "Banco, Una institución financiera"),
        ("banco", "parque sentarse asiento plaza madera", "Banco"),
        # Piso de edificio vs. planta botánica
        ("planta", "edificio piso arquitectura campus aula", "Piso, Planta de edificio"),
        ("planta", "verde flor semilla raiz regar jardin", "Planta"),
    ]

    for term, context, expected in matrix:
        res = resolve_gloss_to_sign(term, context=context, include_animation=False)
        actual = res.get("sign")
        assert actual == expected, (
            f"Fallo contextual para '{term}' con contexto '{context}': "
            f"obtenido '{actual}', esperado '{expected}'"
        )


def test_automovilismo_alias_to_carrera_de_autos():
    """Verifica que el término 'automovilismo' resuelva directamente a 'Carrera, De autos'."""
    res = resolve_gloss_to_sign("automovilismo", include_animation=False)
    assert res["found"] is True
    assert res["sign"] == "Carrera, De autos"


def test_morphological_stemmer_shielding_cola_never_stems_to_col():
    """
    Verifica que el sustantivo 'cola' esté blindado contra truncación morfológica
    y NUNCA derive a 'Col' (repollo / verdura).
    """
    # 1. Candidatos morfológicos no deben incluir 'col'
    morph_cands = _generate_morphological_candidates("cola")
    assert "col" not in morph_cands, f"'col' encontrado en candidatos morfológicos de 'cola': {morph_cands}"

    # 2. Resolución genérica nunca debe ser 'Col'
    res = resolve_gloss_to_sign("cola", include_animation=False)
    assert res.get("sign") != "Col", "CRÍTICO: 'cola' resolvió erróneamente a 'Col' (repollo)!"
    assert res.get("is_fingerspelling") is True, "Sin contexto, 'cola' debe recurrir a dactilología"

    # 3. La verdura 'col' sigue resolviendo a 'Col'
    res_col = resolve_gloss_to_sign("col", include_animation=False)
    assert res_col.get("sign") == "Col"

    # 4. Contextualizaciones válidas de 'cola'
    res_fila = resolve_gloss_to_sign("cola", context="fila espera personas banco", include_animation=False)
    assert res_fila.get("sign") == "Fila"

    res_pegar = resolve_gloss_to_sign("cola", context="pegar goma adhesivo carpinteria", include_animation=False)
    assert res_pegar.get("sign") == "Pegar"

    res_gaseosa = resolve_gloss_to_sign("cola", context="gaseosa bebida refresco", include_animation=False)
    assert res_gaseosa.get("sign") == "Destapar, Gaseosa"


def test_morphological_stemmer_shielding_medio_never_stems_to_media():
    """
    Verifica que 'medio' esté blindado contra flexión de género espuria
    y NUNCA resuelva a 'Media' (calcetín / prenda de vestir).
    """
    # 1. Candidatos morfológicos no deben incluir 'media'
    morph_cands = _generate_morphological_candidates("medio")
    assert "media" not in morph_cands, f"'media' encontrado en candidatos de 'medio': {morph_cands}"
    assert "mitad" in morph_cands or "medioambiente" in morph_cands

    # 2. Resolución por defecto es 'Mitad', NUNCA 'Media'
    res = resolve_gloss_to_sign("medio", include_animation=False)
    assert res.get("sign") != "Media", "CRÍTICO: 'medio' resolvió a 'Media' (calcetín)!"
    assert res.get("sign") == "Mitad"

    # 3. 'media' sigue resolviendo a 'Media'
    res_media = resolve_gloss_to_sign("media", include_animation=False)
    assert res_media.get("sign") == "Media"

    # 4. Contexto medioambiental
    res_amb = resolve_gloss_to_sign("medio", context="medioambiente ecologia verde", include_animation=False)
    assert res_amb.get("sign") == "Medioambiente"


def test_cura_shielding_medical_vs_priest():
    """
    Verifica que 'cura' y 'curas' resuelvan a 'Curar, Curación' en ámbito médico/salud/general
    y solo a 'Papa, Cura' cuando el contexto es explícitamente eclesiástico.
    """
    for token in ("cura", "curas"):
        # 1. Por defecto / general
        res_default = resolve_gloss_to_sign(token, include_animation=False)
        assert res_default.get("sign") == "Curar, Curación", (
            f"Se esperaba 'Curar, Curación' por defecto para '{token}', obtenido: '{res_default.get('sign')}'"
        )
        assert res_default.get("sign") != "Papa, Cura"

        # 2. Contexto de salud
        res_salud = resolve_gloss_to_sign(token, context="salud hospital doctor medicina remedio", include_animation=False)
        assert res_salud.get("sign") == "Curar, Curación"

        # 3. Contexto religioso
        res_iglesia = resolve_gloss_to_sign(token, context="iglesia sacerdote misa catolico parroco", include_animation=False)
        assert res_iglesia.get("sign") == "Papa, Cura"


def test_registrar_academic_vs_civil_registry():
    """
    Verifica que 'registrar' resuelva a 'Inscribir, Inscripción' en ámbito académico/admisiones
    y a 'Registro Civil' solo en trámites de identidad civil.
    """
    # 1. Por defecto / académico
    res_default = resolve_gloss_to_sign("registrar", include_animation=False)
    assert res_default.get("sign") == "Inscribir, Inscripción"

    # 2. Contexto académico institucional
    res_acad = resolve_gloss_to_sign("registrar", context="universidad materias upec admision periodo", include_animation=False)
    assert res_acad.get("sign") == "Inscribir, Inscripción"

    # 3. Contexto civil registral
    res_civil = resolve_gloss_to_sign("registrar", context="cedula partida nacimiento matrimonio defuncion", include_animation=False)
    assert res_civil.get("sign") == "Registro Civil"


def test_numeric_cero_and_zero_shielding():
    """
    Verifica que '0', '00', '000' y 'cero' nunca resuelvan a la seña léxica 'NADA' ni queden en MISSING,
    sino a la configuración manual del dígito 0 / dactilología.
    """
    for token in ("0", "00", "000", "cero", "CERO"):
        res = resolve_gloss_to_sign(token, include_animation=False)
        assert res.get("sign") != "Nada", f"CRÍTICO: '{token}' resolvió a 'Nada'!"
        assert res.get("status") != "MISSING", f"'{token}' no debe quedar en MISSING"
        assert res.get("is_fingerspelling") is True, f"'{token}' debe procesarse como dactilología/dígito manual"

    # Verificar síntesis de animación de dactilología para '0'
    res_anim = resolve_gloss_to_sign("0", include_animation=True)
    assert res_anim.get("animation") is not None
    assert "bones" in res_anim["animation"] and "frames" in res_anim["animation"]


def test_dictionary_service_homonym_priority_and_context(dict_svc: LSECDictionaryService):
    """Verifica que LSECDictionaryService aplique la prioridad correcta en homónimos."""
    # 1. Prioridades por defecto en CONADIS
    assert dict_svc.lookup("menos").entry.title == "Menos, De menor cantidad"
    assert dict_svc.lookup("receta").entry.title == "Receta, De médico"
    assert dict_svc.lookup("limpio").entry.title == "Limpiar, Limpio"
    assert dict_svc.lookup("carrera").entry.title == "Carrera, Estudios"
    assert dict_svc.lookup("raton").entry.title == "Ratón"
    assert dict_svc.lookup("blanco").entry.title == "Blanco(a)"
    assert dict_svc.lookup("explotar").entry.title == "Explotar, Explosión"
    assert dict_svc.lookup("babear").entry.title == "Babear, Baboso(a)"
    assert dict_svc.lookup("torre").entry.title == "Torre"
    assert dict_svc.lookup("polvo").entry.title == "Polvo"
    assert dict_svc.lookup("llamar").entry.title == "Llamar, De acudir"
    assert dict_svc.lookup("cura").entry.title == "Curar, Curación"
    assert dict_svc.lookup("curas").entry.title == "Curar, Curación"

    # 2. Búsqueda contextual en CONADIS
    m_raton_tech = dict_svc.lookup("raton", context="computadora oficina pc")
    assert m_raton_tech is not None
    assert m_raton_tech.entry.title == "Ratón, De computador"

    m_receta_cocina = dict_svc.lookup("receta", context="cocina gastronomia chef")
    assert m_receta_cocina is not None
    assert m_receta_cocina.entry.title == "Receta, Recetario de cocina"

    m_limpio_honesto = dict_svc.lookup("limpio", context="honesto integridad")
    assert m_limpio_honesto is not None
    assert m_limpio_honesto.entry.title == "Limpio, De honesto"

    m_carrera_autos = dict_svc.lookup("carrera", context="autos formula rally")
    assert m_carrera_autos is not None
    assert m_carrera_autos.entry.title == "Carrera, De autos"


def test_batch_resolution_with_context():
    """Verifica que resolve_batch_glosses_payload respete el contexto en lote."""
    payload = {
        "glosses": ["carrera", "raton", "receta", "menos"],
        "context": "computadora oficina informatica",
        "version": "2.7",
    }
    batch_res = resolve_batch_glosses_payload(payload)
    results = batch_res.get("results", {})

    assert results["raton"]["sign"] == "Ratón, De computador"
    assert results["carrera"]["sign"] == "Carrera, Estudios"
    assert results["receta"]["sign"] == "Receta, De médico"
    assert results["menos"]["sign"] == "Menos, De menor cantidad"


def test_shielded_4letter_nouns_registry():
    """Verifica que la lista de sustantivos de 4 letras invariables esté registrada y protegida."""
    sample = ["cola", "bota", "copa", "foca", "gota", "rata", "sopa", "taza", "vaca", "mesa"]
    for noun in sample:
        assert is_shielded_4letter_noun(noun) is True
        cands = _generate_morphological_candidates(noun)
        stem_no_a = noun[:-1]
        assert stem_no_a not in cands, f"Truncación espuria '{stem_no_a}' producida para '{noun}': {cands}"


def test_is_restricted_domain_folder_helper():
    """Verifica el helper de detección de carpetas de dominio restringido."""
    assert is_restricted_domain_folder("Limpio, De honesto") is True
    assert is_restricted_domain_folder("Menos, De la matemáticas") is True
    assert is_restricted_domain_folder("Carrera, De autos") is True
    assert is_restricted_domain_folder("Limpiar, Limpio") is False
    assert is_restricted_domain_folder("Carrera, Estudios") is False
    assert is_restricted_domain_folder("Blanco(a)") is False
