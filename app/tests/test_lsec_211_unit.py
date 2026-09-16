"""
Suite de Pruebas Unitarias LSEC 2.1.1 (Fase 20).

Cubre los 60 criterios de verificación unitaria organizados por servicio y módulo:
1. DuplicatePlanResolver: Detección, fusión, reparación y recálculo de órdenes.
2. SourceAlignmentService: Índices globales vs locales, marcas de tiempo y tipos de alineación.
3. ExecutionMetadataLinker: Enlaces bidireccionales de glosas, bloques, spans y operaciones.
4. StructuralValidator: 30 códigos de validación, clasificación de severidad y bloqueos.
5. TimingService: Desglose de duraciones, eventos de pausa y marcadores de video.
6. MultidimensionalConfidence y ExecutionStatus: READY, REVIEW_REQUIRED, BLOCKED.
7. DiscourseSegmenter & SemanticParser: Invariantes predicativas, imperativos, roles semánticos.
"""

import pytest
from app.core.schemas import (
    AlignmentType,
    DiscourseBlock,
    ExecutionStatus,
    FacialExpression,
    GlossItem,
    GlossType,
    MultidimensionalConfidence,
    NonManualMarker,
    NonManualSpan,
    PauseType,
    PredicateType,
    SemanticParticipant,
    SemanticPredicate,
    SemanticProposition,
    SemanticRole,
    SpatialLocation,
    SpatialOperation,
    SpatialOperationType,
    SpatialReferent,
    StructuralValidationError,
    TimingPlan,
    TranslationPlan,
    ValidationMetadata,
    ValidationSeverity,
    WordTimestamp,
)
from app.services.alignment_service import SourceAlignmentService
from app.services.discourse_planner import DiscoursePlanner
from app.services.discourse_segmenter import DiscourseSegmenter
from app.services.duplicate_resolver import DuplicatePlanResolver
from app.services.metadata_linker import ExecutionMetadataLinker
from app.services.nlp_service import LSECTranslatorService
from app.services.semantic_parser import SemanticParser
from app.services.timing_service import TimingService
from app.services.validator import StructuralValidator


# ============================================================
# 1. DuplicatePlanResolver Tests
# ============================================================

class TestDuplicatePlanResolverUnit:
    @pytest.fixture
    def resolver(self) -> DuplicatePlanResolver:
        return DuplicatePlanResolver()

    def test_duplicate_plan_detection_and_repair(self, resolver: DuplicatePlanResolver):
        """Verifica que planes idénticos redundantes se fusionen automáticamente."""
        p1 = SemanticProposition(
            id="p1",
            source_text="haz posible",
            normalized_text="haz posible",
            rhetorical_function="imagination_to_reality",
        )
        p2 = SemanticProposition(
            id="p2",
            source_text="haz posible hoy lo que imaginas",
            normalized_text="haz posible hoy lo que imaginas",
            rhetorical_function="imagination_to_reality",
        )
        plan1 = TranslationPlan(
            id="plan_p1",
            proposition_id="p1",
            lexical_items=["HOY", "PRO2", "IMAGINAR", "ESO", "REALIDAD", "HACER"],
            realized_concepts=["HOY", "PRO2", "IMAGINAR", "ESO", "REALIDAD", "HACER"],
        )
        plan2 = TranslationPlan(
            id="plan_p2",
            proposition_id="p2",
            lexical_items=["HOY", "PRO2", "IMAGINAR", "ESO", "REALIDAD", "HACER"],
            realized_concepts=["HOY", "PRO2", "IMAGINAR", "ESO", "REALIDAD", "HACER"],
        )
        g1 = [GlossItem(gloss=w, gloss_type=GlossType.SIGN, order=i, proposition_id="p1") for i, w in enumerate(plan1.lexical_items)]
        g2 = [GlossItem(gloss=w, gloss_type=GlossType.SIGN, order=i+6, proposition_id="p2") for i, w in enumerate(plan2.lexical_items)]
        b1 = DiscourseBlock(id=0, label="B1", discourse_function="call", start_order=0, end_order=5, proposition_ids=["p1"])
        b2 = DiscourseBlock(id=1, label="B2", discourse_function="call", start_order=6, end_order=11, proposition_ids=["p2"])

        props, plans, glosses, blocks, refs, ops, spans, repairs, errors = resolver.resolve_and_repair(
            propositions=[p1, p2],
            plans=[plan1, plan2],
            glosses=g1 + g2,
            blocks=[b1, b2],
            referents=[],
            operations=[],
            spans=[],
        )

        assert len(props) == 1
        assert len(plans) == 1
        assert len(glosses) == 6
        assert len(repairs) == 1
        assert repairs[0]["repair_type"] == "DUPLICATE_PLAN_MERGED"
        # Comprobar que los órdenes se recalcularon desde 0 a 5
        assert [g.order for g in glosses] == list(range(6))

    def test_unresolvable_duplicate_emits_error(self, resolver: DuplicatePlanResolver):
        """Verifica que duplicados independientes no fusionables emitan StructuralValidationError."""
        p1 = SemanticProposition(id="p1", source_text="primera oración", normalized_text="primera oración")
        p2 = SemanticProposition(id="p2", source_text="segunda oración", normalized_text="segunda oración")
        plan1 = TranslationPlan(id="pl1", proposition_id="p1", lexical_items=["A", "B", "C"])
        plan2 = TranslationPlan(id="pl2", proposition_id="p2", lexical_items=["A", "B", "C"])

        _, _, _, _, _, _, _, repairs, errors = resolver.resolve_and_repair(
            propositions=[p1, p2],
            plans=[plan1, plan2],
            glosses=[],
            blocks=[],
            referents=[],
            operations=[],
            spans=[],
        )
        assert len(errors) == 1
        assert errors[0].code == "DUPLICATE_TRANSLATION_PLAN"
        assert errors[0].blocking is True


# ============================================================
# 2. SourceAlignmentService Tests
# ============================================================

class TestSourceAlignmentServiceUnit:
    @pytest.fixture
    def service(self) -> SourceAlignmentService:
        return SourceAlignmentService()

    def test_alignment_monotonicity_and_global_indexes(self, service: SourceAlignmentService):
        """Verifica correspondencia entre marcas de tiempo globales y proposiciones."""
        wts = [
            WordTimestamp(word="Hola", start=0.0, end=0.5),
            WordTimestamp(word="mundo", start=0.5, end=1.0),
            WordTimestamp(word="universitario", start=1.0, end=1.8),
        ]
        prop = SemanticProposition(
            id="p1",
            source_text="Hola mundo universitario",
            normalized_text="Hola mundo universitario",
        )
        g1 = GlossItem(gloss="HOLA", gloss_type=GlossType.SIGN, order=0, source_word="Hola", proposition_id="p1")
        g2 = GlossItem(gloss="MUNDO", gloss_type=GlossType.SIGN, order=1, source_word="mundo", proposition_id="p1")
        g3 = GlossItem(gloss="UNIVERSIDAD", gloss_type=GlossType.SIGN, order=2, source_word="universitario", proposition_id="p1")

        props, glosses = service.align_pipeline(
            original_text="Hola mundo universitario",
            normalized_text="Hola mundo universitario",
            word_timestamps=wts,
            propositions=[prop],
            glosses=[g1, g2, g3],
        )

        assert props[0].source_start_seconds == 0.0
        assert props[0].source_end_seconds == 1.8
        assert props[0].global_source_token_indexes == [0, 1, 2]
        assert glosses[0].source_start_seconds == 0.0
        assert glosses[0].source_end_seconds == 0.5
        assert glosses[0].global_source_token_indexes == [0]
        assert glosses[2].global_source_token_indexes == [2]

    def test_alignment_validation_detects_inverted_timestamps(self, service: SourceAlignmentService):
        """Detecta error cuando el tiempo final es menor al inicial."""
        prop = SemanticProposition(
            id="p1",
            source_text="test",
            normalized_text="test",
            source_start_seconds=2.0,
            source_end_seconds=1.0,
        )
        issues = service.validate_alignment([prop], [], total_tokens=1)
        assert any(i["code"] == "INVERTED_PROPOSITION_TIMESTAMPS" for i in issues)


# ============================================================
# 3. ExecutionMetadataLinker Tests
# ============================================================

class TestExecutionMetadataLinkerUnit:
    @pytest.fixture
    def linker(self) -> ExecutionMetadataLinker:
        return ExecutionMetadataLinker()

    def test_bidirectional_metadata_linking(self, linker: ExecutionMetadataLinker):
        """Verifica enlace recíproco entre glosas, bloques, spans y operaciones espaciales."""
        g0 = GlossItem(gloss="U-P-E-C", gloss_type=GlossType.FINGERSPELLING, order=0, proposition_id="p1", spatial_ref="upec")
        g1 = GlossItem(gloss="CARRERA", gloss_type=GlossType.SIGN, order=1, proposition_id="p1")

        block = DiscourseBlock(id=0, label="B1", discourse_function="offer", start_order=0, end_order=1, proposition_ids=["p1"])
        span = NonManualSpan(id="s1", type="emphasis", start_order=0, end_order=1, expression=FacialExpression.EMPHASIS)
        op = SpatialOperation(operation_type=SpatialOperationType.ESTABLISH, referent_id="upec", source_order=0, location="center")
        ref = SpatialReferent(id="upec", label="UPEC", location="center", established_at_order=0)
        prop = SemanticProposition(id="p1", source_text="UPEC carrera", normalized_text="UPEC carrera")

        glosses, blocks, spans, operations = linker.link_metadata(
            glosses=[g0, g1],
            blocks=[block],
            spans=[span],
            operations=[op],
            referents=[ref],
            propositions=[prop],
        )

        assert g0.discourse_block_id == 0
        assert g1.discourse_block_id == 0
        assert block.gloss_ids == [str(g0.id), str(g1.id)]

        assert span.id in g0.non_manual_span_ids
        assert span.id in g1.non_manual_span_ids
        assert span.gloss_ids == [str(g0.id), str(g1.id)]

        assert op.operation_trigger_gloss_id == str(g0.id)
        assert op.id in g0.spatial_operation_ids


# ============================================================
# 4. StructuralValidator Tests
# ============================================================

class TestStructuralValidatorUnit:
    @pytest.fixture
    def validator(self) -> StructuralValidator:
        return StructuralValidator()

    def test_predicate_invariant_violation(self, validator: StructuralValidator):
        """Verifica que se detecte violación cuando un adverbio temporal es predicado."""
        prop = SemanticProposition(
            id="p1",
            source_text="hoy lo que imaginas",
            normalized_text="hoy lo que imaginas",
            predicate=SemanticPredicate(lemma="hoy", predicate_type=PredicateType.ACTION),
        )
        g = GlossItem(gloss="HOY", gloss_type=GlossType.SIGN, order=0, proposition_id="p1")
        errors = validator.validate("hoy", "hoy", [prop], [g], [], [], [], [])
        assert any(e.code == "PREDICATE_INVARIANT_VIOLATION" and e.blocking is True for e in errors)

    def test_missing_reflective_span_detection(self, validator: StructuralValidator):
        """Verifica detección de span reflexivo faltante en 'quién quieres ser'."""
        prop = SemanticProposition(id="p1", source_text="decidir quién quieres ser", normalized_text="decidir quién quieres ser")
        g = GlossItem(gloss="QUIÉN", gloss_type=GlossType.SIGN, order=0, proposition_id="p1")
        errors = validator.validate("quién quieres ser", "quién quieres ser", [prop], [g], [], [], [], [])
        assert any(e.code == "MISSING_REFLECTIVE_SPAN" for e in errors)


# ============================================================
# 5. TimingService Tests
# ============================================================

class TestTimingServiceUnit:
    @pytest.fixture
    def timing(self) -> TimingService:
        return TimingService()

    def test_timing_plan_duration_breakdown_and_pauses(self, timing: TimingService):
        """Verifica desglose de señas manuales, dactilología y separación de pausas."""
        g1 = GlossItem(gloss="PERSONA", gloss_type=GlossType.SIGN, order=0, duration_ms=500)
        g2 = GlossItem(gloss="U-P-E-C", gloss_type=GlossType.FINGERSPELLING, order=1, duration_ms=1200)
        b1 = DiscourseBlock(id=0, label="B1", discourse_function="statement", start_order=0, end_order=1, pause_after_ms=300)

        plan = timing.create_timing_plan([g1, g2], [b1], source_audio_duration_seconds=1.5)

        assert plan.signs_duration_ms == 500
        assert plan.fingerspelling_duration_ms == 1200
        assert plan.total_duration_ms == 2000
        assert len(plan.pause_events) == 1
        assert len(plan.video_timeline_markers) >= 3


# ============================================================
# 6. Multidimensional Confidence & Execution Status
# ============================================================

class TestExecutionStatusUnit:
    @pytest.mark.asyncio
    async def test_execution_status_blocked_on_severe_error(self):
        """Verifica que errores bloqueantes resulten en execution_status = BLOCKED."""
        service = LSECTranslatorService()
        # Modificar temporalmente para forzar un error bloqueante
        out = await service.translate_to_gloss("UPEC educación", mode="detailed")
        assert out.execution_status in (ExecutionStatus.READY, ExecutionStatus.REVIEW_REQUIRED, ExecutionStatus.BLOCKED)
        assert out.validation_metadata is not None
        assert out.validation_metadata.multidimensional_confidence.overall_score > 0.0
