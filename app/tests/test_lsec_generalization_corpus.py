"""
Corpus de Generalización de Gramática y Glosas LSEC (>= 48 oraciones).

Evalúa la robustez, generalidad y ausencia de dependencias contextuales o léxicas específicas
a través de 6 dominios: Salud, Transporte, Familia, Comercio, Clima y Trabajo.
Valida invariantes lingüísticos universales LSEC sin depender de glosas exactas frágiles.
"""

from __future__ import annotations

import re
import pytest
from typing import List, Tuple

from app.services.nlp_service import LSECTranslatorService
from app.services.fenasec_rules import get_verb_class


CORPUS_DATA: List[Tuple[str, str]] = [
    # --- 1. Salud (8 oraciones) ---
    ("salud", "El médico examina al paciente atentamente"),
    ("salud", "Ayer la enfermera curó la herida en el hospital"),
    ("salud", "El paciente no tiene dolor de cabeza"),
    ("salud", "¿Dónde trabaja el cirujano experto?"),
    ("salud", "El doctor receta medicina amarga"),
    ("salud", "Mañana la doctora visitará a la abuela enferma"),
    ("salud", "El paramédico atiende la emergencia rápidamente"),
    ("salud", "El dentista limpia los dientes con cuidado"),

    # --- 2. Transporte (8 oraciones) ---
    ("transporte", "El tren viaja rápido por la montaña"),
    ("transporte", "Ayer el avión aterrizó tarde en el aeropuerto"),
    ("transporte", "El conductor frena el camión despacio"),
    ("transporte", "¿Cuándo sale el barco grande?"),
    ("transporte", "El chofer no conduce el taxi peligroso"),
    ("transporte", "Hoy el ciclista recorre la avenida larga"),
    ("transporte", "El pasajero espera la furgoneta puntual"),
    ("transporte", "Mañana el capitán navegará el río verde"),

    # --- 3. Familia (8 oraciones) ---
    ("familia", "La hermana abraza al primo alegre"),
    ("familia", "El abuelo cuenta historias bonitas a los nietos"),
    ("familia", "Ayer el tío cocinó sopa deliciosa en la casa"),
    ("familia", "El sobrino no escucha el consejo sabio"),
    ("familia", "¿Quién ayuda a la tía anciana?"),
    ("familia", "Hoy la madre cuida al bebé tranquilo"),
    ("familia", "El padre enseña carpintería al hijo pequeño"),
    ("familia", "La prima visita el pueblo lejano"),

    # --- 4. Comercio (8 oraciones) ---
    ("comercio", "El vendedor ofrece frutas frescas en el mercado"),
    ("comercio", "Ayer el cliente pagó dinero exacto en la tienda"),
    ("comercio", "El panadero no vende pan quemado"),
    ("comercio", "¿Cuánto cuesta el pescado congelado?"),
    ("comercio", "La cajera cuenta monedas brillantes con paciencia"),
    ("comercio", "Hoy el carnicero corta carne tierna en la bodega"),
    ("comercio", "El comerciante guarda los productos caros"),
    ("comercio", "Mañana el dueño abrirá el negocio próspero"),

    # --- 5. Clima (8 oraciones) ---
    ("clima", "Está lloviendo muy fuerte"),
    ("clima", "Ayer granizó de repente en el campo"),
    ("clima", "El viento sopla fuerte en la colina"),
    ("clima", "Hoy nieva suave en la cima"),
    ("clima", "¿Por qué hace tanto calor?"),
    ("clima", "Mañana habrá tormenta oscura en la costa"),
    ("clima", "El sol calienta la arena seca"),
    ("clima", "La niebla cubre el valle profundo"),

    # --- 6. Trabajo (8 oraciones) ---
    ("trabajo", "El albañil construye una pared alta"),
    ("trabajo", "Ayer el electricista reparó el cable roto en la fábrica"),
    ("trabajo", "La arquitecta diseña planos modernos con empeño"),
    ("trabajo", "El bombero no teme el fuego ardiente"),
    ("trabajo", "¿Quién repara la máquina vieja?"),
    ("trabajo", "Hoy el carpintero pule una mesa lisa en el taller"),
    ("trabajo", "El mecánico ajusta el motor ruidoso"),
    ("trabajo", "Mañana el supervisor inspeccionará la obra nueva"),
]


@pytest.fixture(scope="module")
def service() -> LSECTranslatorService:
    return LSECTranslatorService()


class TestLSECGeneralizationCorpus:
    """Valida los invariantes lingüísticos universales en las 48 oraciones del corpus."""

    @pytest.mark.parametrize("domain,sentence", CORPUS_DATA)
    @pytest.mark.asyncio
    async def test_generalization_linguistic_invariants(
        self, service: LSECTranslatorService, domain: str, sentence: str
    ):
        res = await service.translate_to_gloss(sentence, mode="detailed")
        glosses = [g.gloss.upper() for g in res.glosses]
        base_glosses = [re.sub(r"\[.*?\]|\+\+", "", g).strip() for g in glosses]

        # Invariante 1: No aparecen artículos en español (ELIS-01)
        articles = {"EL", "LA", "LOS", "LAS", "UN", "UNA", "UNOS", "UNAS"}
        leaked_articles = [g for g in base_glosses if g in articles]
        assert not leaked_articles, f"Fuga de artículos en '{sentence}': {leaked_articles}"

        # Invariante 2: No aparece cópula atributiva SER/ESTAR (cópula nula)
        copulas = {"SER", "ESTAR", "ES", "ESTÁ", "ESTA", "ERA", "FUE", "SOMOS", "SON"}
        leaked_copulas = [g for g in base_glosses if g in copulas]
        assert not leaked_copulas, f"Fuga de cópula en '{sentence}': {leaked_copulas}"

        # Invariante 3: No aparece glosa PERO léxica (adversativa como body shift)
        assert "PERO" not in base_glosses, f"Glosa PERO encontrada en '{sentence}'"

        # Invariante 4: No aparece adverbio MUY aislado (subsumido por intensidad ++)
        assert "MUY" not in base_glosses, f"Adverbio MUY aislado en '{sentence}'"

        # Invariante 5: En oraciones negativas, la negación NO está en posición final o postverbal
        if re.search(r"\bno\b", sentence, re.IGNORECASE):
            assert "NO" in base_glosses or any("NO-" in g for g in glosses), (
                f"Marca de negación ausente en '{sentence}': {glosses}"
            )
            # Debe estar hacia el final de la secuencia
            if "NO" in base_glosses:
                no_idx = base_glosses.index("NO")
                assert no_idx >= len(base_glosses) // 2, (
                    f"Negación NO prematura en '{sentence}': {glosses}"
                )

        # Invariante 6: En interrogativas Wh, el pronombre interrogativo está al final
        wh_spanish = {"dónde", "cuándo", "quién", "qué", "por qué", "cuánto", "cómo"}
        is_wh_sentence = ("?" in sentence or "¿" in sentence) and any(
            re.search(rf"\b{w}\b", sentence, re.IGNORECASE) for w in wh_spanish
        )
        if is_wh_sentence:
            wh_glosses = {"DÓNDE", "CUÁNDO", "QUIÉN", "QUÉ", "POR-QUÉ", "CUÁNTO", "CÓMO"}
            found_wh = [g for g in base_glosses if g in wh_glosses]
            assert found_wh, f"Palabra interrogativa no encontrada en '{sentence}': {glosses}"
            # Al menos un Wh debe estar en la segunda mitad / posición final
            last_wh_idx = max(base_glosses.index(w) for w in found_wh)
            assert last_wh_idx >= len(base_glosses) - 3, (
                f"Interrogativo no final en '{sentence}': posición {last_wh_idx} de {len(base_glosses)}"
            )

        # Invariante 7: Verbos meteorológicos no reciben sujeto tácito (PRO1/PRO2/PRO3)
        if domain == "clima" and any(v in sentence.lower() for v in ("lloviendo", "granizó", "nieva")):
            pronouns = [g for g in base_glosses if g.startswith("PRO")]
            assert not pronouns, f"Sujeto pronominal en verbo meteorológico en '{sentence}': {pronouns}"

        # Invariante 8: Si hay vector direccional [a->b], el verbo debe ser de clase directional o inverse
        for g in glosses:
            if "[" in g and "->" in g:
                v_name = g.split("[")[0]
                v_class = get_verb_class(v_name)
                assert v_class in ("directional", "inverse"), (
                    f"Vector direccional en verbo no direccional '{v_name}' ({v_class}) en '{sentence}'"
                )

    @pytest.mark.parametrize("original,substituted", [
        (
            "Ayer la enfermera curó la herida en el hospital",
            "Ayer la doctora limpió la pierna en la clínica",
        ),
        (
            "El conductor frena el camión despacio",
            "El chofer detiene el auto lentamente",
        ),
        (
            "Ayer el tío cocinó sopa deliciosa en la casa",
            "Ayer el abuelo preparó comida sabrosa en la cocina",
        ),
        (
            "El panadero no vende pan quemado",
            "El carnicero no corta carne dura",
        ),
        (
            "¿Dónde trabaja el cirujano experto?",
            "¿Dónde labora el médico sabio?",
        ),
        (
            "El albañil construye una pared alta",
            "El carpintero arma una puerta ancha",
        ),
    ])
    @pytest.mark.asyncio
    async def test_lexical_substitution_preserves_structural_invariants(
        self, service: LSECTranslatorService, original: str, substituted: str
    ):
        """
        Criterio 3 (Sustitución léxica): Sustituir sustantivos y verbos por otros
        de la misma clase conserva la estructura gramatical (posiciones relativas).
        """
        res_orig = await service.translate_to_gloss(original, mode="detailed")
        res_sub = await service.translate_to_gloss(substituted, mode="detailed")

        g_orig = [re.sub(r"\[.*?\]|\+\+", "", g.gloss).strip().upper() for g in res_orig.glosses]
        g_sub = [re.sub(r"\[.*?\]|\+\+", "", g.gloss).strip().upper() for g in res_sub.glosses]

        # Ambas oraciones deben tener el mismo número de glosas o longitud análoga
        assert len(g_orig) == len(g_sub), (
            f"Estructuras difieren en longitud: {g_orig} vs {g_sub}"
        )

        # Si había tiempo al inicio en original, debe estar al inicio en la sustituida
        if g_orig[0] in ("AYER", "HOY", "MAÑANA"):
            assert g_sub[0] == g_orig[0]

        # Si había negación en original, debe estar en la sustituida
        if "NO" in g_orig:
            assert "NO" in g_sub
            assert g_orig.index("NO") == g_sub.index("NO")

        # Si era interrogativa, la palabra Wh debe ocupar la misma posición relativa
        wh_set = {"DÓNDE", "CUÁNDO", "QUIÉN", "QUÉ", "CÓMO", "CUÁNTO", "POR-QUÉ"}
        orig_wh = [w for w in g_orig if w in wh_set]
        sub_wh = [w for w in g_sub if w in wh_set]
        if orig_wh and sub_wh:
            assert g_orig.index(orig_wh[0]) == g_sub.index(sub_wh[0])

