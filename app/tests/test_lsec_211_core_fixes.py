"""
Suite de Pruebas Exhaustiva de Corrección de Causa Raíz e Invariantes LSEC 2.1.1.

Verifica:
  1. Los 7 casos mínimos de prueba (S1 a S7).
  2. Aislamiento total de signos de puntuación (¿, ?, ¡, !, etc.) sin contaminación léxica.
  3. Detección canónica de predicados y erradicación de selección espuria (yo, tú, qué, etc.).
  4. Lematización verbal consistente (comes -> comer, etc.).
  5. Preservación no destructiva de sustantivos (manzana -> manzana, glosa MANZANA).
  6. Extracción completa de participantes nucleares (AGENT, PATIENT/THEME) y pro-drop.
  7. Trazabilidad de soporte conceptual y eliminación de conceptos espurios (VARIOS).
  8. Modalidades interrogativas (interrogative_yn, interrogative_wh) y funciones discursivas.
  9. Operadores semánticos estructurados (NEGATION, QUESTION_YN, QUESTION_WH).
  10. Máquina de estados determinista (errors_count > 0 => BLOCKED).
  11. Consistencia aritmética del plan temporal y etiquetado de pausa final (FINAL_PAUSE).
  12. 12 Pruebas basadas en propiedades (Property-Based Testing).
  13. Aviso explícito de propuesta computacional sujeta a validación por personas sordas nativas.
"""

from __future__ import annotations

import pytest
from typing import List, Dict, Any

from app.core.schemas import (
    AlignmentType,
    ExecutionStatus,
    FacialExpression,
    GlossItem,
    GlossType,
    ReviewStatus,
    SemanticRole,
    ValidationSeverity,
)
from app.services.nlp_service import LSECTranslatorService


@pytest.fixture
def translator() -> LSECTranslatorService:
    return LSECTranslatorService()


class TestLSEC211CoreFixes:
    """Suite de validación de los 7 casos mínimos de prueba del pipeline LSEC 2.1.1."""

    # ------------------------------------------------------------------ #
    # 1. Caso S1: '¿Tú comes manzana?'
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_s1_tu_comes_manzana(self, translator: LSECTranslatorService):
        """¿Tú comes manzana? -> Predicado comer, AGENT tú, PATIENT manzana, modalidad interrogative_yn."""
        out = await translator.translate_to_gloss("¿Tú comes manzana?", mode="detailed")

        assert len(out.semantic_propositions) == 1
        prop = out.semantic_propositions[0]

        # Invariante de predicado
        assert prop.predicate is not None
        assert prop.predicate.lemma == "comer"
        assert prop.predicate.lemma != "tú"
        assert "¿" not in prop.predicate.lemma and "?" not in prop.predicate.lemma

        # Modalidad y operadores
        assert prop.modality == "interrogative_yn"
        assert any(op.get("type") == "QUESTION_YN" for op in prop.operators)

        # Participantes
        roles = {p.semantic_role: p.lemma for p in prop.participants}
        assert SemanticRole.AGENT in roles
        assert roles[SemanticRole.AGENT] in ("tú", "tu")
        assert SemanticRole.PATIENT in roles
        assert roles[SemanticRole.PATIENT] == "manzana"

        # Glosas
        gloss_texts = [g.gloss for g in out.glosses]
        assert "COMER" in gloss_texts
        assert "MANZANA" in gloss_texts
        assert "MANZÁN" not in gloss_texts
        assert "VARIOS" not in gloss_texts

        # Bloque discursivo
        assert out.discourse_blocks[0].discourse_function == "question_yn"

        # Tiempos
        assert out.timing_plan.total_duration_ms == (
            out.timing_plan.signs_duration_ms
            + out.timing_plan.fingerspelling_duration_ms
            + out.timing_plan.pause_budget_ms
        )

    # ------------------------------------------------------------------ #
    # 2. Caso S2: '¿Qué comes?'
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_s2_que_comes(self, translator: LSECTranslatorService):
        """¿Qué comes? -> Predicado comer, AGENT tú (pro-drop), PATIENT qué, modalidad interrogative_wh, SIN VARIOS."""
        out = await translator.translate_to_gloss("¿Qué comes?", mode="detailed")

        prop = out.semantic_propositions[0]
        assert prop.predicate.lemma == "comer"
        assert prop.predicate.lemma != "qué"
        assert prop.modality == "interrogative_wh"

        # Operador WH
        assert any(op.get("type") == "QUESTION_WH" for op in prop.operators)

        # Participantes: Agente implícito tú y argumento interrogativo qué
        agent_part = next((p for p in prop.participants if p.semantic_role == SemanticRole.AGENT), None)
        assert agent_part is not None
        assert agent_part.is_implicit is True

        patient_part = next((p for p in prop.participants if p.semantic_role in (SemanticRole.PATIENT, SemanticRole.THEME)), None)
        assert patient_part is not None
        assert patient_part.lemma == "qué"

        # Glosas: Erradicación de VARIOS
        gloss_texts = [g.gloss for g in out.glosses]
        assert "VARIOS" not in gloss_texts
        assert "COMER" in gloss_texts
        assert "QUÉ" in gloss_texts

        # Bloque discursivo
        assert out.discourse_blocks[0].discourse_function == "question_wh"

    # ------------------------------------------------------------------ #
    # 3. Caso S3: '¿Quién compró el pan?'
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_s3_quien_compro_el_pan(self, translator: LSECTranslatorService):
        """¿Quién compró el pan? -> Predicado comprar, AGENT quién, PATIENT pan, modalidad interrogative_wh."""
        out = await translator.translate_to_gloss("¿Quién compró el pan?", mode="detailed")

        prop = out.semantic_propositions[0]
        assert prop.predicate.lemma == "comprar"
        assert prop.modality == "interrogative_wh"

        agent_part = next((p for p in prop.participants if p.semantic_role == SemanticRole.AGENT), None)
        assert agent_part is not None
        assert agent_part.lemma == "quién"

        patient_part = next((p for p in prop.participants if p.semantic_role in (SemanticRole.PATIENT, SemanticRole.THEME)), None)
        assert patient_part is not None
        assert patient_part.lemma == "pan"

        gloss_texts = [g.gloss for g in out.glosses]
        assert "COMPRAR" in gloss_texts
        assert "PAN" in gloss_texts
        assert "QUIÉN" in gloss_texts

        # Puntuación no contaminada
        for g in out.glosses:
            assert "¿" not in g.gloss and "?" not in g.gloss

    # ------------------------------------------------------------------ #
    # 4. Caso S4: 'Yo como una manzana'
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_s4_yo_como_una_manzana(self, translator: LSECTranslatorService):
        """Yo como una manzana -> Predicado comer, AGENT yo, PATIENT manzana, declarativa positiva."""
        out = await translator.translate_to_gloss("Yo como una manzana", mode="detailed")

        prop = out.semantic_propositions[0]
        assert prop.predicate.lemma == "comer"
        assert prop.predicate.lemma != "yo"
        assert prop.polarity == "positive"
        assert prop.modality == "declarative"

        gloss_texts = [g.gloss for g in out.glosses]
        assert "COMER" in gloss_texts
        assert "MANZANA" in gloss_texts
        assert "MANZÁN" not in gloss_texts

    # ------------------------------------------------------------------ #
    # 5. Caso S5: 'Yo no como carne'
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_s5_yo_no_como_carne(self, translator: LSECTranslatorService):
        """Yo no como carne -> Predicado comer, AGENT yo, PATIENT carne, polaridad negativa y operador NEGATION."""
        out = await translator.translate_to_gloss("Yo no como carne", mode="detailed")

        prop = out.semantic_propositions[0]
        assert prop.predicate.lemma == "comer"
        assert prop.polarity == "negative"
        assert any(op.get("type") == "NEGATION" for op in prop.operators)

        roles = {p.semantic_role: p.lemma for p in prop.participants}
        assert roles[SemanticRole.AGENT] == "yo"
        assert roles[SemanticRole.PATIENT] == "carne"

        gloss_texts = [g.gloss for g in out.glosses]
        assert "CARNE" in gloss_texts
        assert "COMER" in gloss_texts
        assert "NO" in gloss_texts

        # Span no manual de negación
        neg_spans = [s for s in out.non_manual_spans if s.expression == FacialExpression.NEGATION or s.type == "negation"]
        assert len(neg_spans) > 0

    # ------------------------------------------------------------------ #
    # 6. Caso S6: 'María come pan'
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_s6_maria_come_pan(self, translator: LSECTranslatorService):
        """María come pan -> Predicado comer, AGENT María, PATIENT pan."""
        out = await translator.translate_to_gloss("María come pan", mode="detailed")

        prop = out.semantic_propositions[0]
        assert prop.predicate.lemma == "comer"
        roles = {p.semantic_role: p.lemma.lower() for p in prop.participants}
        assert roles[SemanticRole.AGENT] == "maría"
        assert roles[SemanticRole.PATIENT] == "pan"

        gloss_texts = [g.gloss for g in out.glosses]
        assert "MARÍA" in gloss_texts or "MARIA" in gloss_texts
        assert "PAN" in gloss_texts
        assert "COMER" in gloss_texts

    # ------------------------------------------------------------------ #
    # 7. Caso S7: '¿Dónde estudias?'
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_s7_donde_estudias(self, translator: LSECTranslatorService):
        """¿Dónde estudias? -> Predicado estudiar, LOCATION dónde, modalidad interrogative_wh."""
        out = await translator.translate_to_gloss("¿Dónde estudias?", mode="detailed")

        prop = out.semantic_propositions[0]
        assert prop.predicate.lemma == "estudiar"
        assert prop.modality == "interrogative_wh"

        loc_part = next((p for p in prop.participants if p.semantic_role == SemanticRole.LOCATION), None)
        assert loc_part is not None
        assert loc_part.lemma == "dónde"

        gloss_texts = [g.gloss for g in out.glosses]
        assert "ESTUDIAR" in gloss_texts
        assert "DÓNDE" in gloss_texts or "DONDE" in gloss_texts


class TestLSEC211PropertyInvariants:
    """12 Pruebas de Propiedades e Invariantes Universales del Pipeline LSEC 2.1.1."""

    # Propiedad 1: Invariante de Aislamiento de Puntuación
    @pytest.mark.asyncio
    @pytest.mark.parametrize("sentence", [
        "¿Tú comes manzana?",
        "¡Tú comes manzana!",
        "¿Quién compró el pan?",
        "¿Dónde estudias?",
        "¡Excelente oportunidad!",
    ])
    async def test_property_1_punctuation_isolation(self, translator: LSECTranslatorService, sentence: str):
        """Ningún lema de predicado, participante o glosa debe contener signos de puntuación."""
        out = await translator.translate_to_gloss(sentence, mode="detailed")
        punct_set = set("¿?¡!,.;:\"'«»—–")

        for prop in out.semantic_propositions:
            if prop.predicate:
                assert not any(c in punct_set for c in prop.predicate.lemma)
            for part in prop.participants:
                assert not any(c in punct_set for c in part.lemma)

        for g in out.glosses:
            assert not any(c in punct_set for c in g.gloss)
            if g.normalized_word:
                assert not any(c in punct_set for c in g.normalized_word)

    # Propiedad 2: Invariante de No Selección de Pronombres/Sustantivos como Predicado
    @pytest.mark.asyncio
    @pytest.mark.parametrize("sentence", [
        "Yo como una manzana",
        "Tú comes manzana",
        "¿Qué comes?",
        "¿Quién compró el pan?",
        "Él bebe agua",
        "Nosotros estudiamos",
    ])
    async def test_property_2_forbidden_predicate_invariance(self, translator: LSECTranslatorService, sentence: str):
        """Un pronombre o sustantivo nunca debe ser asignado como predicado de acción."""
        out = await translator.translate_to_gloss(sentence, mode="detailed")
        forbidden = {"yo", "tú", "él", "ella", "nosotros", "ellos", "qué", "quién", "dónde", "manzana", "carne", "pan"}

        for prop in out.semantic_propositions:
            assert prop.predicate.lemma.lower() not in forbidden

    # Propiedad 3: Preservación Canónica de Lemas Verbales
    @pytest.mark.asyncio
    @pytest.mark.parametrize("verb_form,expected_lemma", [
        ("comes", "comer"),
        ("como", "comer"),
        ("bebe", "beber"),
        ("compró", "comprar"),
        ("estudias", "estudiar"),
        ("llegas", "llegar"),
    ])
    async def test_property_3_canonical_verb_lemmatization(self, translator: LSECTranslatorService, verb_form: str, expected_lemma: str):
        """Las formas verbales conjugadas deben lematizarse siempre a su infinitivo canónico."""
        out = await translator.translate_to_gloss(f"Tú {verb_form}", mode="detailed")
        prop = out.semantic_propositions[0]
        assert prop.predicate.lemma == expected_lemma

    # Propiedad 4: No Destrucción de Sustantivos
    @pytest.mark.asyncio
    async def test_property_4_non_destructive_noun_normalization(self, translator: LSECTranslatorService):
        """'manzana' nunca debe convertirse en 'manzán' ni generar notas de adjetivo post-nominal."""
        out = await translator.translate_to_gloss("¿Tú comes manzana?", mode="detailed")
        manzana_glosses = [g for g in out.glosses if "MANZANA" in g.gloss or "MANZÁN" in g.gloss]
        assert len(manzana_glosses) == 1
        assert manzana_glosses[0].gloss == "MANZANA"
        assert manzana_glosses[0].notes != "Adjetivo post-nominal"

    # Propiedad 5: Participantes en Cláusulas Transitivas
    @pytest.mark.asyncio
    @pytest.mark.parametrize("transitive_sentence", [
        "Yo como manzana",
        "¿Quién compró el pan?",
        "María bebe agua",
        "Carlos estudia medicina",
    ])
    async def test_property_5_transitive_clause_participants(self, translator: LSECTranslatorService, transitive_sentence: str):
        """Las oraciones transitivas deben contener tanto AGENT como PATIENT/THEME."""
        out = await translator.translate_to_gloss(transitive_sentence, mode="detailed")
        prop = out.semantic_propositions[0]
        has_agent = any(p.semantic_role in (SemanticRole.AGENT, SemanticRole.EXPERIENCER) for p in prop.participants)
        has_patient = any(p.semantic_role in (SemanticRole.PATIENT, SemanticRole.THEME, SemanticRole.LOCATION) for p in prop.participants)
        assert has_agent is True
        assert has_patient is True

    # Propiedad 6: Erradicación de VARIOS en Preguntas Individuales
    @pytest.mark.asyncio
    async def test_property_6_no_spurious_varios(self, translator: LSECTranslatorService):
        """¿Qué comes? no debe generar la glosa VARIOS."""
        out = await translator.translate_to_gloss("¿Qué comes?", mode="detailed")
        assert "VARIOS" not in [g.gloss for g in out.glosses]

    # Propiedad 7: Soporte Conceptual Trazable
    @pytest.mark.asyncio
    @pytest.mark.parametrize("sentence", [
        "¿Tú comes manzana?",
        "¿Quién compró el pan?",
        "Yo no como carne",
    ])
    async def test_property_7_traceable_conceptual_support(self, translator: LSECTranslatorService, sentence: str):
        """Ningún RealizedConceptItem debe tener is_supported=True con source_concept_ids vacío sin regla justificada."""
        out = await translator.translate_to_gloss(sentence, mode="detailed")
        for plan in out.translation_plans:
            for rci in plan.realized_concept_items:
                if rci.is_supported:
                    has_source_ids = bool(rci.source_concept_ids)
                    has_rule = bool(rci.inference_rule_id or rci.coreference_target_id or rci.discourse_relation or rci.entity_id)
                    assert has_source_ids or has_rule

    # Propiedad 8: Modalidad Interrogativa y Función Discursiva
    @pytest.mark.asyncio
    @pytest.mark.parametrize("q_text,expected_modality,expected_func", [
        ("¿Tú comes manzana?", "interrogative_yn", "question_yn"),
        ("¿Qué comes?", "interrogative_wh", "question_wh"),
        ("¿Quién compró el pan?", "interrogative_wh", "question_wh"),
        ("¿Dónde estudias?", "interrogative_wh", "question_wh"),
    ])
    async def test_property_8_interrogative_modality_discourse(
        self, translator: LSECTranslatorService, q_text: str, expected_modality: str, expected_func: str
    ):
        """Las preguntas deben tener modalidad interrogativa y función discursiva correspondiente."""
        out = await translator.translate_to_gloss(q_text, mode="detailed")
        assert out.semantic_propositions[0].modality == expected_modality
        assert out.discourse_blocks[0].discourse_function == expected_func

    # Propiedad 9: Operador Semántico de Negación
    @pytest.mark.asyncio
    @pytest.mark.parametrize("neg_text", [
        "Yo no como carne",
        "Nadie te dice nada",
        "Nunca comemos tarde",
    ])
    async def test_property_9_negation_operator_generation(self, translator: LSECTranslatorService, neg_text: str):
        """Las oraciones negativas deben registrar el operador NEGATION y tener polaridad negativa."""
        out = await translator.translate_to_gloss(neg_text, mode="detailed")
        prop = out.semantic_propositions[0]
        assert prop.polarity == "negative"
        assert any(op.get("type") == "NEGATION" for op in prop.operators)

    # Propiedad 10: Determinismo de la Máquina de Estados (Inconsistencias Bloquean)
    @pytest.mark.asyncio
    async def test_property_10_state_machine_determinism(self, translator: LSECTranslatorService):
        """Si errors_count > 0, execution_status NUNCA puede ser READY ni review_status VERIFIED."""
        out = await translator.translate_to_gloss("¿Tú comes manzana?", mode="detailed")
        if out.validation_metadata.errors_count > 0:
            assert out.execution_status == ExecutionStatus.BLOCKED
            assert out.validation_metadata.review_status == ReviewStatus.BLOCKED
        else:
            assert out.execution_status in (ExecutionStatus.READY, ExecutionStatus.REVIEW_REQUIRED)

    # Propiedad 11: Coherencia Aritmética Temporal
    @pytest.mark.asyncio
    @pytest.mark.parametrize("sentence", [
        "¿Tú comes manzana?",
        "¿Qué comes?",
        "Yo como una manzana",
        "¿Quién compró el pan?",
    ])
    async def test_property_11_timing_arithmetic_consistency(self, translator: LSECTranslatorService, sentence: str):
        """total_duration_ms == signs_duration_ms + fingerspelling_duration_ms + pause_budget_ms."""
        out = await translator.translate_to_gloss(sentence, mode="detailed")
        tp = out.timing_plan
        expected_total = tp.signs_duration_ms + tp.fingerspelling_duration_ms + tp.pause_budget_ms
        assert abs(tp.total_duration_ms - expected_total) <= 2
        # Pausa final tipificada
        if tp.pause_events:
            last_pause = tp.pause_events[-1]
            assert "FINAL_PAUSE" in last_pause.reason or "Transición" in last_pause.reason

    # Propiedad 12: Aviso Obligatorio de Propuesta Computacional LSEC
    @pytest.mark.asyncio
    @pytest.mark.parametrize("sentence", [
        "¿Tú comes manzana?",
        "¿Qué comes?",
        "Yo no como carne",
    ])
    async def test_property_12_computational_proposal_notice(self, translator: LSECTranslatorService, sentence: str):
        """La salida debe incluir explícitamente el aviso de validación por personas sordas nativas."""
        out = await translator.translate_to_gloss(sentence, mode="detailed")
        assert "Propuesta computacional sujeta a validación por personas sordas usuarias nativas de LSEC." in out.validation_metadata.computational_proposal_notice
        assert "Propuesta computacional sujeta a validación por personas sordas usuarias nativas de LSEC." in out.validation_summary["computational_proposal_notice"]
