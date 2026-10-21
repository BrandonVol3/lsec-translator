"""
Suite de Pruebas Canónicas del Informe de Reglas Lingüísticas LSEC.

Cubre los 7 casos canónicos estipulados en la Sección 8 de PROMPT_MEJORA_MOTOR_GLOSAS_LSEC.md
y la regresión de 2.mp4 (p1-p4).
"""

from __future__ import annotations

import re
import pytest

from app.core.schemas import (
    FacialExpression,
    NonManualSpan,
    SpatialLocation,
)
from app.services.nlp_service import LSECTranslatorService


def normalize_gloss_sequence(items: list[str] | str) -> list[str]:
    """
    Aplica la tabla de equivalencias de la Sección 7 del estándar / informe:
      - YO, TÚ, ÉL -> PRO1, PRO2, PRO3 (plural -PL)
      - tú-AYUDAR-yo -> AYUDAR[2->1]
      - TE-EXPLICO [1->2] / [1→2] -> EXPLICAR[1->2]
      - ME-PRESTAS-ATENCIÓN [2->1] -> PRESTAR-ATENCIÓN[2->1]
      - normaliza puntuación / delimitadores superfluos
    """
    if isinstance(items, str):
        # Separar por espacios
        tokens = items.strip().split()
    else:
        tokens = list(items)

    normalized: list[str] = []
    pronoun_map = {
        "YO": "PRO1",
        "TÚ": "PRO2",
        "TU": "PRO2",
        "ÉL": "PRO3",
        "EL": "PRO3",
        "ELLA": "PRO3",
        "NOSOTROS": "PRO1-PL",
        "NOSOTRAS": "PRO1-PL",
        "USTEDES": "PRO2-PL",
        "ELLOS": "PRO3-PL",
        "ELLAS": "PRO3-PL",
    }

    directional_regex = re.compile(
        r"^(?:(?:tú|tu)-([A-ZÁÉÍÓÚÑ\-]+)-(?:yo|me)|(?:yo)-([A-ZÁÉÍÓÚÑ\-]+)-(?:tú|te))\b",
        re.IGNORECASE,
    )

    for tok in tokens:
        clean = tok.strip()
        if not clean:
            continue

        # Equivalencias de pronombres
        if clean.upper() in pronoun_map:
            normalized.append(pronoun_map[clean.upper()])
            continue

        # tú-AYUDAR-yo -> AYUDAR[2->1]
        m = directional_regex.match(clean)
        if m:
            verb = (m.group(1) or m.group(2)).upper()
            if "tú" in clean.lower() and "yo" in clean.lower():
                if clean.lower().startswith("tú") or clean.lower().startswith("tu"):
                    normalized.append(f"{verb}[2->1]")
                else:
                    normalized.append(f"{verb}[1->2]")
                continue

        # TE-EXPLICO [1->2] / [1→2]
        if "EXPLICO" in clean.upper() and ("1->2" in clean or "1→2" in clean):
            normalized.append("EXPLICAR[1->2]")
            continue
        if "PRESTAS" in clean.upper() and ("2->1" in clean or "2→1" in clean):
            normalized.append("PRESTAR-ATENCIÓN[2->1]")
            continue

        # Limpiar flechas Unicode
        clean = clean.replace("→", "->")

        normalized.append(clean.upper())

    return normalized


@pytest.fixture(scope="module")
def service() -> LSECTranslatorService:
    return LSECTranslatorService()


class TestLSECReportCanonicalCases:
    """Casos canónicos del Informe y la Sección 8."""

    @pytest.mark.asyncio
    async def test_case_1_bus_muy_lento(self, service: LSECTranslatorService):
        """Caso 1: 'El bus es muy lento' -> BUS LENTO++ (ELIS-01, cópula nula, Fase 5 intensidad)."""
        res = await service.translate_to_gloss("El bus es muy lento", mode="detailed")
        gloss_texts = [g.gloss for g in res.glosses]
        norm = normalize_gloss_sequence(gloss_texts)

        # Reglas: ELIS-01 (sin 'EL'), cópula nula (sin 'ES'/'SER'), Fase 5 (sin 'MUY'/'MUCHO', LENTO++)
        assert "EL" not in norm
        assert "ES" not in norm
        assert "SER" not in norm
        assert "MUY" not in norm
        assert "MUCHO" not in norm
        assert norm == ["BUS", "LENTO++"]

        # Validar RNM superlativo en LENTO++
        lento_glosses = [g for g in res.glosses if "LENTO" in g.gloss]
        assert len(lento_glosses) > 0
        assert lento_glosses[0].facial_expression == FacialExpression.SUPERLATIVE

    @pytest.mark.asyncio
    async def test_case_2_ayer_comi_rapido_en_la_escuela(self, service: LSECTranslatorService):
        """Caso 2: 'Ayer comí rápido en la escuela' -> AYER ESCUELA PRO1 COMER RÁPIDO (Fase 3: T+L+S+V+Adv)."""
        res = await service.translate_to_gloss("Ayer comí rápido en la escuela", mode="detailed")
        gloss_texts = [g.gloss for g in res.glosses]
        norm = normalize_gloss_sequence(gloss_texts)

        # Reglas: ELIS-01 (sin LA), ELIS-02 (sin EN)
        assert "LA" not in norm
        assert "EN" not in norm
        # Orden: TIEMPO (AYER) + LUGAR (ESCUELA) + SUJETO (PRO1) + VERBO (COMER) + ADVERBIO (RÁPIDO)
        assert norm == ["AYER", "ESCUELA", "PRO1", "COMER", "RÁPIDO"]

    @pytest.mark.asyncio
    async def test_case_3_tu_me_ayudas_a_solucionar_el_problema(self, service: LSECTranslatorService):
        """Caso 3: 'Tú me ayudas a solucionar el problema' -> PROBLEMA SOLUCIONAR AYUDAR[2->1]."""
        res = await service.translate_to_gloss("Tú me ayudas a solucionar el problema", mode="detailed")
        gloss_texts = [g.gloss for g in res.glosses]
        norm = normalize_gloss_sequence(gloss_texts)

        # Topicalización del objeto y complemento infinitivo, sin 'A', sin 'EL'
        assert "EL" not in norm
        assert "A" not in norm
        assert norm == ["PROBLEMA", "SOLUCIONAR", "AYUDAR[2->1]"]

    @pytest.mark.asyncio
    async def test_case_4_esta_lloviendo_con_mucha_intensidad(self, service: LSECTranslatorService):
        """Caso 4: 'Está lloviendo con mucha intensidad' -> LLOVER++ (Fase 5: 'con mucha + sustantivo de grado')."""
        res = await service.translate_to_gloss("Está lloviendo con mucha intensidad", mode="detailed")
        gloss_texts = [g.gloss for g in res.glosses]
        norm = normalize_gloss_sequence(gloss_texts)

        # Sin sintagma 'CON', 'MUCHA', 'INTENSIDAD', 'ESTÁ', subsume AHORA por ++
        assert "CON" not in norm
        assert "MUCHA" not in norm
        assert "MUCHO" not in norm
        assert "INTENSIDAD" not in norm
        assert "ESTAR" not in norm
        assert norm == ["LLOVER++"]

        llover_glosses = [g for g in res.glosses if "LLOVER" in g.gloss]
        assert len(llover_glosses) > 0
        assert llover_glosses[0].facial_expression == FacialExpression.SUPERLATIVE

    @pytest.mark.asyncio
    async def test_case_5_padre_bien_pero_madre_murio(self, service: LSECTranslatorService):
        """
        Caso 5: 'Mi padre está bien, pero mi madre murió'
        -> PADRE BIEN / MADRE MORIR
        PADRE -> LEFT, MADRE -> RIGHT, MORIR en locus RIGHT, contrast activo, SIN glosa PERO.
        """
        res = await service.translate_to_gloss("Mi padre está bien, pero mi madre murió", mode="detailed")
        gloss_texts = [g.gloss for g in res.glosses]
        norm = normalize_gloss_sequence(gloss_texts)

        # Sin glosa PERO
        assert "PERO" not in norm
        assert "ESTÁ" not in norm
        assert "ESTAR" not in norm

        # Secuencia esencial normalizada: PADRE BIEN MADRE MORIR
        # Permitidos posesivos o deixis si los hubiera, pero base debe ser PADRE BIEN ... MADRE MORIR
        filtered = [x for x in norm if x not in ("PRO1", "MI", "/")]
        assert filtered == ["PADRE", "BIEN", "MADRE", "MORIR"]

        # Espacio Mental: Loci y coherencia
        padre_item = next(g for g in res.glosses if "PADRE" in g.gloss)
        madre_item = next(g for g in res.glosses if "MADRE" in g.gloss)
        morir_item = next(g for g in res.glosses if "MORIR" in g.gloss)

        # PADRE a la izquierda, MADRE a la derecha
        assert padre_item.spatial_location in (SpatialLocation.LEFT, "LEFT", "left")
        assert madre_item.spatial_location in (SpatialLocation.RIGHT, "RIGHT", "right")
        # MORIR articulado en locus de MADRE (RIGHT)
        assert (morir_item.spatial_location in (SpatialLocation.RIGHT, "RIGHT", "right")
                or morir_item.target_spatial_location in (SpatialLocation.RIGHT, "RIGHT", "right"))

        # Contraste activo (NonManualSpan o facial_expression CONTRAST)
        contrast_found = False
        if res.non_manual_spans:
            for nms in res.non_manual_spans:
                if getattr(nms, "type", "") == "contrast" or getattr(nms, "expression", None) == FacialExpression.CONTRAST:
                    contrast_found = True
                    break
        if not contrast_found:
            for g in res.glosses:
                if g.facial_expression == FacialExpression.CONTRAST:
                    contrast_found = True
                    break
        assert contrast_found is True

    @pytest.mark.asyncio
    async def test_case_6_yo_te_explico_y_tu_me_prestas_atencion(self, service: LSECTranslatorService):
        """Caso 6: 'Yo te explico y tú me prestas atención' -> EXPLICAR[1->2] PRESTAR-ATENCIÓN[2->1]."""
        res = await service.translate_to_gloss("Yo te explico y tú me prestas atención", mode="detailed")
        gloss_texts = [g.gloss for g in res.glosses]
        norm = normalize_gloss_sequence(gloss_texts)

        # Pronombres absorbidos por los verbos direccionales
        filtered = [x for x in norm if x != "/"]
        assert filtered == ["EXPLICAR[1->2]", "PRESTAR-ATENCIÓN[2->1]"]

    @pytest.mark.asyncio
    async def test_case_7_yo_te_abrazo_y_tu_me_aceptas(self, service: LSECTranslatorService):
        """Caso 7: 'Yo te abrazo y tú me aceptas' -> PRO1 PRO2 ABRAZAR y PRO2 PRO1 ACEPTAR (body_anchored sin vector)."""
        res = await service.translate_to_gloss("Yo te abrazo y tú me aceptas", mode="detailed")
        gloss_texts = [g.gloss for g in res.glosses]
        norm = normalize_gloss_sequence(gloss_texts)

        # Verbos no direccionales / anclados al cuerpo: conservan pronombres explícitos, SIN vector
        assert "ABRAZAR[1->2]" not in norm
        assert "ACEPTAR[2->1]" not in norm
        assert "ABRAZAR" in norm
        assert "ACEPTAR" in norm
        # Debe contener los pronombres explícitos
        assert norm.count("PRO1") >= 2
        assert norm.count("PRO2") >= 2

    @pytest.mark.asyncio
    async def test_regression_2_mp4_p1_to_p4(self, service: LSECTranslatorService):
        """Regresión de los 4 enunciados clave de 2.mp4."""
        # p1: "Te invitamos a formar parte del Centro Académico de Arte y Cultura"
        r1 = await service.translate_to_gloss(
            "Te invitamos a formar parte del Centro Académico de Arte y Cultura",
            mode="detailed",
        )
        g1 = [g.gloss for g in r1.glosses]
        assert any("INVITAR" in g for g in g1)
        assert "FORMAR" in g1
        assert "CENTRO" in g1

        # p2: "En donde te puedes inscribir en las diferentes asignaturas de cuerpo y movimiento"
        r2 = await service.translate_to_gloss(
            "En donde te puedes inscribir en las diferentes asignaturas de cuerpo y movimiento",
            mode="detailed",
        )
        g2 = [g.gloss for g in r2.glosses]
        assert "ASIGNATURA" in g2
        assert "VARIOS" in g2

        # p3: "Apreciación de la música en el Ecuador y dibujo experimental"
        r3 = await service.translate_to_gloss(
            "Apreciación de la música en el Ecuador y dibujo experimental",
            mode="detailed",
        )
        g3 = [g.gloss for g in r3.glosses]
        assert "DIBUJO" in g3
        assert "EXPERIMENTAL" in g3
        assert "ANTES" not in g3

        # p4: "Para más información comunícate al WhatsApp 099 28 72 993 o al correo..."
        r4 = await service.translate_to_gloss(
            "Para más información comunícate al WhatsApp 099 28 72 993 o al correo seartes@upec.edu.ec",
            mode="detailed",
        )
        g4 = [g.gloss for g in r4.glosses]
        assert "WHATSAPP" in g4
        assert "HACIA" not in g4
