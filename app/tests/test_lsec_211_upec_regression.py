"""
Suite de Pruebas de Regresión y Validación UPEC 2.1.1 (Fase 22).

Evalúa exhaustivamente el texto completo del anuncio publicitario de la UPEC
verificando los 29 criterios de exactitud lingüística, estructural, discursiva y de ejecución.
"""

import pytest
from app.core.schemas import (
    AlignmentType,
    ExecutionStatus,
    FacialExpression,
    GlossType,
    PauseType,
    PredicateType,
    SemanticRole,
    SpatialLocation,
    TranslationMode,
)
from app.services.nlp_service import LSECTranslatorService

UPEC_FULL_AD_TEXT = (
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


@pytest.fixture
def service() -> LSECTranslatorService:
    return LSECTranslatorService()


class TestLSEC211UPECRegression:
    """Validación exhaustiva de los 29 criterios en el anuncio institucional UPEC."""

    @pytest.mark.asyncio
    async def test_full_upec_ad_29_criteria_regression(self, service: LSECTranslatorService):
        """Ejecuta la traducción completa y valida los 29 criterios de control de calidad."""
        out = await service.translate_to_gloss(
            text=UPEC_FULL_AD_TEXT,
            mode="detailed",
            paraphrase_budget="compact",
            source_audio_duration=36.0,
        )

        # Criterio 1: Esquema de salida 2.1
        assert out.schema_version == "2.1"
        assert out.validation_summary["schema_version"] == "2.1"

        # Criterio 2: Cero duplicados de planes
        seen_plans = set()
        for pl in out.translation_plans:
            seq = " ".join(pl.lexical_items)
            assert seq not in seen_plans, f"Secuencia de plan duplicada: {seq}"
            seen_plans.add(seq)

        # Criterio 3: Cero fugas semánticas entre oportunidades e ideas
        prop_opp = next((p for p in out.semantic_propositions if "oportunidades" in p.source_text.lower()), None)
        assert prop_opp is not None
        plan_opp = next((pl for pl in out.translation_plans if pl.proposition_id == prop_opp.id), None)
        assert plan_opp is not None
        assert "IDEA" not in plan_opp.realized_concepts
        assert "DESARROLLAR" not in plan_opp.realized_concepts

        prop_ideas = next((p for p in out.semantic_propositions if "ideas" in p.source_text.lower()), None)
        assert prop_ideas is not None
        plan_ideas = next((pl for pl in out.translation_plans if pl.proposition_id == prop_ideas.id), None)
        assert plan_ideas is not None
        assert "OPORTUNIDAD" not in plan_ideas.realized_concepts

        # Criterio 4: 'haz posible hoy lo que imaginas' como proposición única
        prop_imag = next((p for p in out.semantic_propositions if "haz posible" in p.source_text.lower()), None)
        assert prop_imag is not None
        assert "hoy" in prop_imag.source_text.lower()
        assert "imaginas" in prop_imag.source_text.lower()
        assert prop_imag.predicate is not None
        assert prop_imag.predicate.lemma.lower() != "hoy"

        # Criterio 5: Realización de 'haz posible hoy lo que imaginas'
        plan_imag = next((pl for pl in out.translation_plans if pl.proposition_id == prop_imag.id), None)
        assert plan_imag is not None
        assert plan_imag.lexical_items == ["HOY", "PRO2", "IMAGINAR", "ESO", "REALIDAD", "HACER"]

        # Criterio 6: Bloque de formación humana en 4 unidades no solapadas
        human_props = [p for p in out.semantic_propositions if p.rhetorical_function in ("human_focus_1", "human_focus_2", "human_focus_3", "human_focus_4")]
        assert len(human_props) == 4

        # Criterio 7: Realización de formación humana 1 (restricción profesional)
        plan_h1 = next((pl for pl in out.translation_plans if pl.proposition_id == human_props[0].id), None)
        assert plan_h1 is not None
        assert "PROFESIONAL" in plan_h1.realized_concepts
        assert "SOLAMENTE-NO" in plan_h1.realized_concepts
        assert "PERSONA" not in plan_h1.realized_concepts

        # Criterio 8: Realización de formación humana 2 (formación humana)
        plan_h2 = next((pl for pl in out.translation_plans if pl.proposition_id == human_props[1].id), None)
        assert plan_h2 is not None
        assert "PERSONA" in plan_h2.realized_concepts
        assert "PROFESIONAL" not in plan_h2.realized_concepts

        # Criterio 9: Realización de formación humana 3 (confianza)
        plan_h3 = next((pl for pl in out.translation_plans if pl.proposition_id == human_props[2].id), None)
        assert plan_h3 is not None
        assert "CONFIANZA" in plan_h3.realized_concepts
        assert "INSPIRAR" in plan_h3.realized_concepts

        # Criterio 10: Realización de formación humana 4 (cercanía / acompañamiento)
        plan_h4 = next((pl for pl in out.translation_plans if pl.proposition_id == human_props[3].id), None)
        assert plan_h4 is not None
        assert "ACOMPAÑAR" in plan_h4.realized_concepts
        assert plan_h4.requires_native_review is True

        # Criterio 11: Segmentación de preparación en 3 unidades
        prep_props = [p for p in out.semantic_propositions if p.rhetorical_function in ("preparation_start", "educational_resources", "technology_development")]
        assert len(prep_props) == 3

        # Criterio 12: Realización de preparación inicial
        plan_p1 = next((pl for pl in out.translation_plans if pl.proposition_id == prep_props[0].id), None)
        assert plan_p1 is not None
        assert all(k in plan_p1.realized_concepts for k in ("PREPARAR", "DÍA", "PRIMERO"))

        # Criterio 13: Realización de recursos educativos
        plan_p2 = next((pl for pl in out.translation_plans if pl.proposition_id == prep_props[1].id), None)
        assert plan_p2 is not None
        assert all(k in plan_p2.realized_concepts for k in ("EXCELENCIA", "INNOVACIÓN", "TECNOLOGÍA"))

        # Criterio 14: Realización de desarrollo tecnológico acompañado
        plan_p3 = next((pl for pl in out.translation_plans if pl.proposition_id == prep_props[2].id), None)
        assert plan_p3 is not None
        assert "TECNOLOGÍA" in plan_p3.realized_concepts
        assert "AVANZAR" in plan_p3.realized_concepts

        # Criterio 15: Referentes espaciales registrados
        ref_ids = {r.id for r in out.spatial_referents}
        assert "campus_tulcan" in ref_ids
        assert "campus_cayambe" in ref_ids
        assert "upec" in ref_ids

        # Criterio 16: Operaciones espaciales establecidas en glosas de dactilología
        op_tulcan = next((op for op in out.spatial_operations if op.referent_id == "campus_tulcan"), None)
        assert op_tulcan is not None
        assert op_tulcan.operation_trigger_gloss_id is not None
        tg_tulcan = next((g for g in out.glosses if str(g.id) == op_tulcan.operation_trigger_gloss_id), None)
        assert tg_tulcan is not None
        assert "T-U-L-C" in tg_tulcan.gloss

        op_cayambe = next((op for op in out.spatial_operations if op.referent_id == "campus_cayambe"), None)
        assert op_cayambe is not None
        assert op_cayambe.operation_trigger_gloss_id is not None
        tg_cayambe = next((g for g in out.glosses if str(g.id) == op_cayambe.operation_trigger_gloss_id), None)
        assert tg_cayambe is not None
        assert "C-A-Y-A-M-B-E" in tg_cayambe.gloss

        # Criterio 17: Span no manual reflexivo en 'quién quieres ser'
        refl_spans = [s for s in out.non_manual_spans if s.type == "reflective" or s.expression == FacialExpression.REFLECTIVE]
        assert len(refl_spans) > 0

        # Criterio 18: Span superlativo acotado
        sup_spans = [s for s in out.non_manual_spans if s.type == "superlative" or s.expression == FacialExpression.SUPERLATIVE]
        for ss in sup_spans:
            assert (ss.end_order - ss.start_order + 1) <= 4

        # Criterio 19: Span de negación presente
        neg_spans = [s for s in out.non_manual_spans if s.expression == FacialExpression.NEGATION]
        assert len(neg_spans) >= 2  # 'nadie te dice', 'no solo eliges'

        # Criterio 20: Roles semánticos precisos
        prop_nadie = next((p for p in out.semantic_propositions if "nadie" in p.source_text.lower()), None)
        assert prop_nadie is not None
        part_nadie = next((pt for pt in prop_nadie.participants if pt.lemma == "nadie"), None)
        assert part_nadie is not None
        assert part_nadie.semantic_role == SemanticRole.AGENT

        part_te = next((pt for pt in prop_nadie.participants if pt.lemma in ("tú", "te")), None)
        assert part_te is not None
        assert part_te.semantic_role == SemanticRole.ADDRESSEE

        # Criterio 21: Palabra dudosa 'liberan' marcada para revisión auditiva
        liberan_gloss = next((g for g in out.glosses if g.gloss == "LIBERAR"), None)
        assert liberan_gloss is not None
        assert liberan_gloss.requires_review is True

        # Criterio 22: Paráfrasis conceptuales marcadas para revisión nativa
        imparable_glosses = [g for g in out.glosses if g.lexical_strategy == "semantic_paraphrase" and "imparable" in (g.source_word or "").lower()]
        assert len(imparable_glosses) > 0
        assert all(g.requires_review for g in imparable_glosses)

        # Criterio 23: Propagación de revisión a nivel global
        assert out.validation_metadata.requires_native_review is True
        assert len(out.validation_metadata.review_reasons) >= 2

        # Criterio 24: Estado de ejecución REVIEW_REQUIRED
        assert out.execution_status == ExecutionStatus.REVIEW_REQUIRED

        # Criterio 25: Enlaces bidireccionales en todas las glosas
        for g in out.glosses:
            assert g.discourse_block_id is not None
            assert g.proposition_id is not None

        # Criterio 26: Desglose de duraciones en TimingPlan
        tp = out.timing_plan
        assert tp is not None
        assert tp.signs_duration_ms > 0
        assert tp.fingerspelling_duration_ms > 0
        assert tp.total_duration_ms == tp.signs_duration_ms + tp.fingerspelling_duration_ms + tp.pause_budget_ms

        # Criterio 27: Pausas y marcadores de video
        assert len(tp.pause_events) > 0
        assert len(tp.video_timeline_markers) >= 5

        # Criterio 28: Confianza multidimensional calculada
        conf = out.validation_metadata.multidimensional_confidence
        assert conf.overall_score > 0.80
        assert conf.asr_confidence >= 0.90
        assert conf.segmentation_confidence >= 0.85
        assert conf.semantic_confidence >= 0.85

        # Criterio 29: Métricas de cobertura de cada plan > 0.0
        for pl in out.translation_plans:
            assert pl.coverage_ratio > 0.0
            assert pl.source_recall > 0.0
            assert pl.realization_precision > 0.0
