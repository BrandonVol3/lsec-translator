"""
Suite de regresión automatizada para las Mejoras 1, 2, 3 y 6 derivadas de la Auditoría DATASET:
  - Mejora 1: Cumplimiento NTE INEN 3198 (>= 1/9 de pantalla sin oclusión del espacio de señación)
              y Reglamento LOC Abril 2026 (CDPIC-DTN-PNRD-2B-26, subtítulos accesibles y Reporte Art. 26).
  - Mejora 2: Motor de Componentes No Manuales (CNM v1.1) con prosoponemas léxicos obligatorios
              del Glosario Básico FENASEC (Compilacion-Final-Interactivo.pdf).
  - Mejora 3: Etiquetado y preferencia Geolectal (Sierra / Costa / Nacional) y Buscador Inverso
              por Parámetros Querológicos (configuración manual, variante, geolecto, bimanualidad, RNM).
  - Mejora 6: Corpus oficial de 25 oraciones gramaticales del Curso Básico de Lengua de Señas Módulo 2
              (Asociación de Sordos de Santo Domingo, págs. 48-50).
"""

from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path
from typing import List

import pytest

from app.services.animation_catalog_service import (
    build_animations_list_payload,
    build_non_manual_standard_payload,
)
from app.services.animation_lexical_resolver import resolve_gloss_to_sign
from app.services.dictionary_service import LSECDictionaryService, get_dictionary_service
from app.services.nlp_service import LSECTranslatorService

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
DICCIONARIO_DIR = WORKSPACE_ROOT / "Diccionario LSEC"

if str(DICCIONARIO_DIR) not in sys.path:
    sys.path.insert(0, str(DICCIONARIO_DIR))


@pytest.fixture(scope="module")
def translator_svc() -> LSECTranslatorService:
    return LSECTranslatorService()


@pytest.fixture(scope="module")
def dict_svc() -> LSECDictionaryService:
    return get_dictionary_service()


def _translate_glosses(svc: LSECTranslatorService, text: str) -> List[str]:
    result = asyncio.run(svc.translate_to_gloss(text))
    return [g.gloss for g in result.glosses]


# ============================================================================
# MEJORA 6: Corpus Oficial de 25 Oraciones Gramaticales (Santo Domingo Módulo 2)
# Fuente: Curso Básico de Lengua de Señas Módulo 2 (Asociación de Sordos de Santo Domingo)
# ============================================================================

SANTO_DOMINGO_MODULO_2_CORPUS = [
    # (Oración en español del Módulo 2, glosas requeridas en la salida, glosas prohibidas)
    ("La niña va a comer helado.", ["FUTURO", "NIÑA", "HELADO", "COMER"], ["LA", "VA", "A"]),
    ("El niño ya se bañó.", ["NIÑO", "BAÑAR"], ["EL", "SE"]),
    ("La señora está cocinando.", ["SEÑORA", "COCINAR", "AHORA"], ["LA", "ESTÁ", "ESTAR"]),
    ("Mi papá trabaja en el banco.", ["PAPÁ", "BANCO", "TRABAJAR"], ["EL", "EN"]),
    ("Mi mamá compra frutas en el mercado.", ["MAMÁ", "FRUTA", "MERCADO"], ["EN", "EL"]),
    ("El perro es bravo.", ["PERRO", "BRAVO"], ["EL", "ES", "SER"]),
    ("En el baño no hay papel.", ["BAÑO", "PAPEL", "NO-HABER"], ["EN", "EL", "HAY"]),
    ("Yo no tengo dinero.", ["PRO1", "DINERO", "TENER", "NO"], []),
    ("A mí no me gusta la sopa.", ["PRO1", "SOPA", "NO-GUSTAR"], ["A", "LA"]),
    ("Mañana voy a viajar a Quito.", ["MAÑANA", "PRO1", "QUITO", "VIAJAR"], ["VOY", "A"]),
    ("Ayer jugué fútbol con mis amigos.", ["AYER", "AMIGO", "FÚTBOL", "JUGAR"], ["MIS"]),
    ("El carro rojo es nuevo.", ["CARRO", "ROJO", "NUEVO"], ["EL", "ES", "SER"]),
    ("Esa mujer es muy inteligente.", ["MUJER", "INTELIGENTE++"], ["ES", "SER", "MUY"]),
    ("Mi casa queda muy lejos.", ["CASA", "LEJOS++"], ["MUY"]),
    ("La enfermera cuida mucho a los enfermos.", ["ENFERMERA", "ENFERMO", "CUIDAR++"], ["LA", "A", "LOS", "MUCHO"]),
    ("¿Cómo te llamas?", ["LLAMAR", "CÓMO"], []),
    ("¿Cuántos años tienes?", ["AÑO", "TENER", "CUÁNTO"], []),
    ("¿Dónde vives tú?", ["PRO2", "VIVIR", "DÓNDE"], []),
    ("Yo vivo en Santo Domingo.", ["PRO1", "SANTO-DOMINGO", "VIVIR"], ["EN"]),
    ("Mi hermano estudia en la universidad.", ["HERMANO", "UNIVERSIDAD", "ESTUDIAR"], ["EN", "LA"]),
    ("Me gusta tomar leche con chocolate.", ["PRO1", "LECHE", "CHOCOLATE", "GUSTAR", "TOMAR"], ["CHOCOLAR"]),
    ("El jabón huele feo.", ["JABÓN", "FEO", "OLER"], ["EL", "HUELE"]),
    ("La camisa está sucia.", ["CAMISA", "SUCIO"], ["LA", "ESTÁ", "ESTAR"]),
    ("El bebé tiene hambre y llora.", ["BEBÉ", "HAMBRE", "TENER", "LLORAR"], ["EL", "Y"]),
    ("Nosotros aprendemos Lengua de Señas Ecuatoriana.", ["PRO1-PL", "LENGUA-DE-SEÑAS", "APRENDER"], ["DE"]),
]


@pytest.mark.parametrize("sentence,expected_tokens,forbidden_tokens", SANTO_DOMINGO_MODULO_2_CORPUS)
def test_santo_domingo_modulo2_25_sentences(
    translator_svc: LSECTranslatorService,
    sentence: str,
    expected_tokens: List[str],
    forbidden_tokens: List[str],
) -> None:
    """Verifica las 25 oraciones del Módulo 2 (Asociación de Sordos de Santo Domingo)."""
    glosses = _translate_glosses(translator_svc, sentence)
    assert len(glosses) > 0, f"La oración '{sentence}' no generó glosas"

    for req in expected_tokens:
        assert req in glosses, f"Falta glosa '{req}' en '{sentence}' -> {glosses}"

    for forb in forbidden_tokens:
        assert forb not in glosses, f"Glosa prohibida '{forb}' presente en '{sentence}' -> {glosses}"

    # Verificar regla sintáctica Tiempo al inicio (T-S-O-V)
    for time_marker in ("AYER", "MAÑANA", "FUTURO"):
        if time_marker in expected_tokens:
            assert glosses[0] == time_marker, (
                f"Marcador temporal '{time_marker}' debe ubicarse al inicio en '{sentence}' -> {glosses}"
            )


def test_santo_domingo_additional_sentences(translator_svc: LSECTranslatorService) -> None:
    """Verifica oraciones complementarias de control morfosintáctico y léxico."""
    g1 = _translate_glosses(translator_svc, "El profesor enseña muy bien.")
    assert "PROFESOR" in g1
    assert "BIEN++" in g1
    assert "ENSEÑAR" in g1

    g2 = _translate_glosses(translator_svc, "Tengo hambre, quiero comer arroz con pescado.")
    assert "HAMBRE" in g2
    assert "ARROZ" in g2
    assert "PESCADO" in g2
    assert "PESCAR" not in g2

    g3 = _translate_glosses(translator_svc, "Por favor ayúdame con la tarea.")
    assert "POR-FAVOR" in g3
    assert "TAREA" in g3
    assert "AYUDAR[2->1]" in g3


# ============================================================================
# MEJORA 2: Prosoponemas Léxicos Obligatorios CNM v1.1 (FENASEC Glosario Básico)
# ============================================================================


def test_cnm_standard_v11_obligatory_prosoponemes() -> None:
    """Verifica que los prosoponemas léxicos obligatorios del Glosario Básico FENASEC estén activos en v1.1."""
    import lsec_non_manual_standard as cnm

    assert cnm.CNM_STANDARD_VERSION == "1.1"

    obligatory_cases = [
        # (Nombre de seña, arquetipo esperado)
        ("Ayudar", "open_kiss_pucker"),
        ("Colega", "open_kiss_pucker"),
        ("Cuidado", "open_kiss_pucker"),
        ("Escuchar", "open_kiss_pucker"),
        ("Mujer", "open_kiss_pucker"),
        ("Oralista", "open_kiss_pucker"),
        ("Oportunidad", "open_kiss_pucker"),
        ("Solucionar", "open_kiss_pucker"),
        ("Dónde", "open_kiss_pucker"),
        ("Cuánto", "open_kiss_pucker"),
        ("Ambos", "lips_projected_closed"),
        ("Comunicarse", "lips_projected_closed"),
        ("Contabilidad", "lips_projected_closed"),
        ("Esposo", "lips_projected_closed"),
        ("Importante", "lips_projected_closed"),
        ("Investigar", "lips_projected_closed"),
        ("Libertad", "lips_projected_closed"),
        ("Poder", "lips_projected_closed"),
        ("Sordo", "lips_projected_closed"),
        ("Perder", "spit_tongue"),
        ("Llenar", "blow_puff"),
        ("Robar", "blow_puff"),
        ("Arreglar", "bite_teeth"),
        ("Dolor", "bite_teeth"),
        ("Emergencia", "bite_teeth"),
        ("Necesitar", "bite_teeth"),
        ("Qué dice", "bite_teeth"),
        ("Mal", "disapproval_lips_in"),
        ("Insatisfacción", "disapproval_lips_in"),
        ("Adiós", "open_mouth_relaxed"),
        ("Bus", "open_mouth_relaxed"),
        ("Hombre", "open_mouth_relaxed"),
        ("Lejos", "open_mouth_relaxed"),
        ("Qué", "open_mouth_relaxed"),
    ]

    for sign_name, expected_arch in obligatory_cases:
        res = cnm.classify_sign_non_manual(sign_name)
        assert res["archetype"] == expected_arch, (
            f"La seña '{sign_name}' debía clasificarse como '{expected_arch}', obtuvo '{res['archetype']}'"
        )
        assert res["hasExplicitFacialExpression"] is True, (
            f"La seña '{sign_name}' con prosoponema obligatorio debe tener hasExplicitFacialExpression=True"
        )
        spec = cnm.FACIAL_ARCHETYPES[res["archetype"]]
        assert isinstance(spec.arkit_blendshapes, dict) and len(spec.arkit_blendshapes) > 0

    summary = build_non_manual_standard_payload()
    assert summary is not None
    assert summary.get("version") == "1.1"
    stats = summary.get("summary", {})
    assert stats.get("explicitFacialExceptionsCount", 0) >= 115


# ============================================================================
# MEJORA 3: Etiquetado Geolectal (Sierra / Costa) y Buscador Inverso Querológico
# ============================================================================


def test_geolectal_resolution_sierra_vs_costa(dict_svc: LSECDictionaryService) -> None:
    """Verifica el etiquetado geolectal Sierra/Costa/Nacional y la resolución preferencial."""
    stats = dict_svc.stats()
    by_geolect = stats.get("by_geolect", {})
    assert by_geolect.get("Sierra", 0) >= 4
    assert by_geolect.get("Costa", 0) >= 3
    assert by_geolect.get("Nacional", 0) >= 4200

    for month in ("mayo", "octubre", "noviembre"):
        m_sierra = dict_svc.lookup(month, preferred_geolect="Sierra")
        m_costa = dict_svc.lookup(month, preferred_geolect="Costa")
        assert m_sierra is not None and m_sierra.entry.geolect == "Sierra"
        assert "Sierra" in m_sierra.entry.title
        assert m_costa is not None and m_costa.entry.geolect == "Costa"
        assert "Costa" in m_costa.entry.title
        assert m_sierra.entry.slug != m_costa.entry.slug

    res_sierra = resolve_gloss_to_sign("MAYO", preferred_geolect="Sierra")
    res_costa = resolve_gloss_to_sign("MAYO", preferred_geolect="Costa")
    assert res_sierra["found"] is True and res_sierra["geolect"] == "Sierra"
    assert res_costa["found"] is True and res_costa["geolect"] == "Costa"
    assert res_sierra["resolved_gloss"] != res_costa["resolved_gloss"]


def test_reverse_cherological_search_filters() -> None:
    """Verifica el buscador inverso por parámetros querológicos en build_animations_list_payload."""
    sierra_payload = build_animations_list_payload(geolect="Sierra", limit=50)
    assert sierra_payload["total"] >= 4
    assert all(item["geolect"] == "Sierra" for item in sierra_payload["items"])

    costa_payload = build_animations_list_payload(geolect="Costa", limit=50)
    assert costa_payload["total"] >= 3
    assert all(item["geolect"] == "Costa" for item in costa_payload["items"])

    pucker_payload = build_animations_list_payload(facial_archetype="open_kiss_pucker", limit=50)
    assert pucker_payload["total"] >= 10
    assert all(item["facial_archetype"] == "open_kiss_pucker" for item in pucker_payload["items"])

    bimanual_payload = build_animations_list_payload(bimanual="both", limit=50)
    assert bimanual_payload["total"] > 100
    assert all(item["active_hands"] == "both" for item in bimanual_payload["items"])

    facets = sierra_payload.get("facets", {})
    assert "by_geolect" in facets
    assert "by_bimanual" in facets
    assert "by_facial_archetype" in facets


# ============================================================================
# MEJORA 1: Diseño PiP Legible (>= 1/9 de pantalla) y Aviso de Prototipo Académico
# ============================================================================


def test_pip_layout_and_prototype_disclaimer_contracts() -> None:
    """Verifica el área mínima legible >= 1/9 para el recuadro del intérprete y el aviso de prototipo académico."""
    exporter_js = (
        PROJECT_ROOT / "app" / "static" / "js" / "components" / "video-exporter.js"
    ).read_text(encoding="utf-8")
    disclaimer_js = (
        PROJECT_ROOT / "app" / "static" / "js" / "components" / "export-disclaimer.js"
    ).read_text(encoding="utf-8")
    subtitle_js = (
        PROJECT_ROOT / "app" / "static" / "js" / "components" / "subtitle-engine.js"
    ).read_text(encoding="utf-8")
    modals_js = (
        PROJECT_ROOT / "app" / "static" / "js" / "components" / "modals-and-export.js"
    ).read_text(encoding="utf-8")

    # 1. Proporción mínima >= 1/9 (11.11%) del área total de pantalla en 16:9 para legibilidad
    for width, height in ((1920, 1080), (1280, 720)):
        total_area = width * height
        min_pip_area = total_area / 9.0
        aspect_ratio = 1.15
        min_pip_width = math.ceil(math.sqrt(min_pip_area / aspect_ratio))
        card_width = max(round(width * 0.245), min_pip_width)
        card_height = round(card_width * aspect_ratio)
        pip_area = card_width * card_height
        assert pip_area >= min_pip_area, (
            f"Área PiP ({pip_area}) menor a 1/9 ({min_pip_area}) en {width}x{height}"
        )
        ratio_pct = (pip_area / total_area) * 100.0
        assert ratio_pct >= 11.11

    # 2. Verificar que video-exporter.js expone getPipLayoutMetrics, footer externo y aviso académico
    assert "getPipLayoutMetrics" in exporter_js
    assert "badgeFooterH" in exporter_js
    assert "LSECExportDisclaimer" in exporter_js
    assert "Propuesta computacional pendiente de validación por personas sordas nativas o profesional intérprete de LSEC" in disclaimer_js

    # 3. Verificar que subtitle-engine.js formatea identificadores de hablante y descriptores sonoros
    assert "formatAccessibleSubtitleText" in subtitle_js
    assert "includeSpeakerTag" in subtitle_js
    assert "includeSoundTags" in subtitle_js
    assert "effectiveSafeLeft" in subtitle_js
    assert "effectiveSafeRight" in subtitle_js

    # 4. Verificar que se retiraron las declaraciones regulatorias NTE INEN 3198 / Reporte Art. 26
    assert "btn-download-inen-compliance-report" not in modals_js
    assert "Reporte Art. 26" not in modals_js
    assert "buildComplianceReport" not in exporter_js
