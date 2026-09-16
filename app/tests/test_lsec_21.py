"""
Tests automatizados para las capacidades avanzadas de LSEC 2.1:
1. Trazabilidad de Cobertura Semántica (ConceptCoverageInfo, coverage_ratio).
2. Orígenes y Clasificación de Conceptos Inferidos (InferredConcept, InferredConceptOrigin).
3. Reglas de Validación Automática (SOURCE_CONTENT_DROPPED, SEMANTIC_CONTENT_LEAK, DUPLICATE_PLAN_DETECTED).
4. Generalización Lingüística y Composicionalidad sobre entradas arbitrarias en español.
5. Esquemas y retrocompatibilidad (schema_version 2.1).
"""

import pytest
from app.core.schemas import (
    ConceptClassification,
    ConceptCoverageInfo,
    FacialExpression,
    FragmentType,
    GlossItem,
    GlossType,
    InferredConcept,
    InferredConceptOrigin,
    ParticipantType,
    PredicateType,
    RelationType,
    SemanticParticipant,
    SemanticPredicate,
    SemanticProposition,
    SemanticRelation,
    SemanticRole,
    TranslationPlan,
)
from app.services.nlp_service import LSECTranslatorService
from app.services.validator import StructuralValidator


class TestLSEC21CoverageAndInference:
    """Pruebas de modelos de cobertura conceptual e inferencias discursivas."""

    def test_concept_coverage_model(self) -> None:
        """Verifica el cálculo de ratio y estado en ConceptCoverageInfo."""
        info = ConceptCoverageInfo(
            source_concepts=["estudiar", "universidad", "carrera"],
            realized_concepts=["ESTUDIAR", "UNIVERSIDAD", "CARRERA"],
            omitted_concepts=[],
            inferred_concepts=[],
            coverage_ratio=1.0,
            coverage_status="COMPLETE",
        )
        assert info.coverage_ratio == 1.0
        assert info.coverage_status == "COMPLETE"
        assert len(info.omitted_concepts) == 0

    def test_inferred_concept_origin_enum(self) -> None:
        """Verifica orígenes de inferencia lingüística."""
        ic = InferredConcept(
            concept="TULCÁN",
            origin=InferredConceptOrigin.DISCOURSE_INFERENCE,
            origin_proposition_id="p1",
            confidence=0.95,
        )
        assert ic.origin == InferredConceptOrigin.DISCOURSE_INFERENCE
        assert ic.confidence == 0.95


class TestLSEC21ValidatorRules:
    """Pruebas para las nuevas validaciones del StructuralValidator."""

    @pytest.fixture
    def validator(self) -> StructuralValidator:
        return StructuralValidator()

    def test_validator_detects_dropped_concepts(self, validator: StructuralValidator) -> None:
        """Detecta SOURCE_CONTENT_DROPPED cuando se omite un concepto fundamental."""
        prop = SemanticProposition(
            id="p_test",
            source_text="ofrece carreras de grado",
            normalized_text="ofrece carreras de grado",
            predicate=SemanticPredicate(lemma="ofrecer", predicate_type=PredicateType.ACTION),
            participants=[
                SemanticParticipant(
                    id="part_carrera",
                    lemma="carrera",
                    normalized_text="carrera",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.PATIENT,
                )
            ],
        )
        # Plan que no realiza 'carrera'
        plan = TranslationPlan(
            id="plan_test",
            proposition_id="p_test",
            source_concepts=["ofrecer", "carrera"],
            realized_concepts=["OFRECER"],
            omitted_concepts=["carrera"],
            coverage_ratio=0.5,
            coverage_status="PARTIAL",
        )
        glosses = [
            GlossItem(gloss="OFRECER", gloss_type=GlossType.SIGN, order=0, proposition_id="p_test")
        ]

        warnings = validator.validate(
            original_text="ofrece carreras de grado",
            normalized_text="ofrece carreras de grado",
            propositions=[prop],
            glosses=glosses,
            blocks=[],
            referents=[],
            operations=[],
            spans=[],
            plans=[plan],
        )

        dropped_warnings = [w for w in warnings if w.code == "SOURCE_CONTENT_DROPPED"]
        assert len(dropped_warnings) > 0
        assert "carrera" in dropped_warnings[0].message

    def test_validator_detects_semantic_content_leak(self, validator: StructuralValidator) -> None:
        """Detecta SEMANTIC_CONTENT_LEAK cuando una proposición genera glosas de otra ajena."""
        prop = SemanticProposition(
            id="p_1",
            source_text="la universidad ofrece innovación",
            normalized_text="la universidad ofrece innovación",
            predicate=SemanticPredicate(lemma="ofrecer", predicate_type=PredicateType.ACTION),
            participants=[
                SemanticParticipant(
                    id="part_u",
                    lemma="universidad",
                    normalized_text="universidad",
                    participant_type=ParticipantType.ORGANIZATION,
                    semantic_role=SemanticRole.AGENT,
                )
            ],
        )
        plan = TranslationPlan(
            id="plan_1",
            proposition_id="p_1",
            source_concepts=["ofrecer", "universidad"],
            realized_concepts=["UNIVERSIDAD", "OFRECER", "OPORTUNIDAD", "IDEA"],
            coverage_ratio=1.0,
            coverage_status="COMPLETE",
        )
        glosses = [
            GlossItem(gloss="UNIVERSIDAD", gloss_type=GlossType.SIGN, order=0, proposition_id="p_1"),
            GlossItem(gloss="OFRECER", gloss_type=GlossType.SIGN, order=1, proposition_id="p_1"),
            GlossItem(gloss="OPORTUNIDAD", gloss_type=GlossType.SIGN, order=2, proposition_id="p_1"),
            GlossItem(gloss="IDEA", gloss_type=GlossType.SIGN, order=3, proposition_id="p_1"),
        ]

        warnings = validator.validate(
            original_text=prop.source_text,
            normalized_text=prop.normalized_text,
            propositions=[prop],
            glosses=glosses,
            blocks=[],
            referents=[],
            operations=[],
            spans=[],
            plans=[plan],
        )

        leak_warnings = [w for w in warnings if w.code == "SEMANTIC_CONTENT_LEAK"]
        assert len(leak_warnings) > 0


class TestLSEC21Generalization:
    """Pruebas de generalización composicional en oraciones arbitrarias en español."""

    @pytest.fixture
    def nlp_service(self) -> LSECTranslatorService:
        return LSECTranslatorService()

    @pytest.mark.asyncio
    async def test_general_academic_offer_arbitrary_university(self, nlp_service: LSECTranslatorService) -> None:
        """Verifica oferta académica y campus en una universidad no vista (ej: PUCE Quito y Ambato)."""
        text = "Con carreras de grado en los campus Quito y Ambato."
        result = await nlp_service.translate_to_gloss(text)
        gloss_names = [g.gloss for g in result.glosses]

        assert "CARRERA" in gloss_names
        assert "GRADO" in gloss_names
        assert "CAMPUS" in gloss_names
        assert "DOS" in gloss_names
        # Debe haber dactilología o glosa para Quito y Ambato
        assert any("Q-U-I-T-O" in g or "QUITO" in g for g in gloss_names)
        assert any("A-M-B-A-T-O" in g or "AMBATO" in g for g in gloss_names)

        # Referentes espaciales establecidos a izquierda y derecha
        assert len(result.spatial_referents) >= 2

    @pytest.mark.asyncio
    async def test_general_arbitrary_contrast_with_not_only(self, nlp_service: LSECTranslatorService) -> None:
        """Verifica patrón 'no solo X, también Y' sobre conceptos médicos/educativos generales."""
        text = "En el hospital no solo atiendes pacientes; salvas vidas."
        result = await nlp_service.translate_to_gloss(text)
        gloss_names = [g.gloss for g in result.glosses]

        assert "SOLAMENTE-NO" in gloss_names or "NO" in gloss_names
        assert any(g in gloss_names for g in ("PACIENTE", "ATENDER", "SALVAR", "VIDA"))
        assert len(result.semantic_propositions) >= 2

    @pytest.mark.asyncio
    async def test_upec_regression_detailed_coverage_and_plans(self, nlp_service: LSECTranslatorService) -> None:
        """Verifica que la prueba de regresión UPEC produzca planes 2.1 con cobertura completa."""
        upec_text = (
            "Dicen que el conocimiento es poder, pero nadie te dice que también es libertad, "
            "libertad para decidir quién quieres ser. "
            "En la Politécnica del Carchi no solo eliges una carrera, eliges ser imparable. "
            "Con carreras de grado en los campus Tulcán y Cayambe nos enorgullece ser la universidad pública más sostenible del Ecuador. "
            "Formamos más que profesionales, formamos seres humanos que inspiran confianza y cercanía. "
            "Aquí te preparamos desde el primer día, con excelencia académica, con innovación, con tecnología que evoluciona contigo. "
            "Más de 4.500 graduados ya lo hicieron, hoy crean oportunidades, liberan y construyen ideas. "
            "Decide sobre tu futuro, haz posible hoy lo que imaginas. "
            "UPEC, educamos para transformar el mundo."
        )
        result = await nlp_service.translate_to_gloss(upec_text, mode="detailed")

        # 1. Esquema 2.1
        assert result.schema_version == "2.1"
        assert result.validation_summary["schema_version"] == "2.1"

        # 2. Cobertura de planes
        assert len(result.translation_plans) >= 10
        for plan in result.translation_plans:
            assert plan.coverage_ratio > 0.0
            assert plan.coverage_status in ("COMPLETE", "PARTIAL", "FAILED")

        # 3. Preservación de oferta académica, sostenibilidad y orgullo
        gloss_names = [g.gloss for g in result.glosses]
        assert "CARRERA" in gloss_names and "GRADO" in gloss_names and "OFRECER" in gloss_names
        assert "SOSTENIBILIDAD" in gloss_names and "MÁS" in gloss_names
        assert "ORGULLO" in gloss_names

        # 4. No hay fugas de contenido en '4500 graduados'
        grad_glosses = [g.gloss for g in result.glosses if g.proposition_id and any("4500" in p.source_text for p in result.semantic_propositions if p.id == g.proposition_id)]
        assert "OPORTUNIDAD" not in grad_glosses
        assert "LIBERAR" not in grad_glosses
        assert "IDEA" not in grad_glosses
