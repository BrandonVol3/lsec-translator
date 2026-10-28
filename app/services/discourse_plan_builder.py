"""
Construcción de referentes/operaciones espaciales, spans no manuales, TranslationPlan y DiscourseBlock LSEC.

Extraído de `discourse_planner.py` para cumplir con el principio de Responsabilidad Única (SRP).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.schemas import (
    AlignmentType,
    DiscourseBlock,
    FacialExpression,
    GlossItem,
    GlossType,
    InferredConcept,
    InferredConceptOrigin,
    NonManualSpan,
    RealizedConceptItem,
    SemanticFrame,
    SemanticProposition,
    SemanticRole,
    SourceConceptItem,
    SpatialLocation,
    SpatialOperation,
    SpatialOperationType,
    SpatialReferent,
    StrategyType,
    TranslationPlan,
)
from app.lsec_grammar.confidence import ConfidenceVector
from app.services.discourse_lexicon import (
    GRAMMATICAL_FUNCTIONAL_WORDS,
    MWE_CONCEPT_SYNONYMS,
)
from app.services.fenasec_rules import _INTENSIFIER_RE
from app.services.text_normalizer import contains_negation


def register_spatial_operations_for_prop(
    planner: Any,
    prop_glosses: List[GlossItem],
    active_referents: Dict[str, SpatialReferent],
    all_referents: List[SpatialReferent],
    all_operations: List[SpatialOperation],
) -> None:
    """Registra operaciones y referentes espaciales vinculados a las glosas de una proposición."""
    for g in prop_glosses:
        if g.spatial_ref:
            ref_id = g.spatial_ref
            loc = "center"
            ent_match = next((e for e in planner._named_entities.values() if e.get("id") == ref_id), None)
            if ent_match and ent_match.get("location"):
                loc = ent_match["location"]
            elif len(active_referents) == 0:
                loc = "left"
            elif len(active_referents) == 1:
                loc = "right"
            elif len(active_referents) % 2 == 0:
                loc = "left"
            else:
                loc = "right"

            if ref_id not in active_referents:
                ent_type = (
                    ent_match.get("type", "location")
                    if ent_match
                    else ("location" if "campus" in ref_id else "organization")
                )
                ref_obj = SpatialReferent(
                    id=ref_id,
                    label=g.source_word or g.gloss,
                    location=loc,
                    established_at_order=g.order,
                    entity_type=ent_type,
                )
                active_referents[ref_id] = ref_obj
                all_referents.append(ref_obj)

                op = SpatialOperation(
                    operation_type=SpatialOperationType.ESTABLISH,
                    referent_id=ref_id,
                    operation_trigger_gloss_id=str(g.id),
                    location=loc,
                    source_order=g.order,
                    eye_gaze=loc,
                    confidence=0.95,
                )
                all_operations.append(op)
                if op.id not in g.spatial_operation_ids:
                    g.spatial_operation_ids.append(op.id)


def apply_contrastive_pair_loci(
    prop: SemanticProposition,
    p_idx: int,
    propositions: List[SemanticProposition],
    all_glosses: List[GlossItem],
    prop_glosses: List[GlossItem],
) -> None:
    """Loci espaciales y cambio de postura para pares contrastivos (Informe Sección 4 / Decisión D6)."""
    if prop.discourse_relation in ("but", "contrast") and p_idx > 0:
        prev_prop = propositions[p_idx - 1]
        for g in all_glosses:
            if g.proposition_id == prev_prop.id:
                is_ref = (
                    any(
                        part.semantic_role in (SemanticRole.AGENT, SemanticRole.THEME, SemanticRole.PATIENT)
                        and part.lemma.lower() in (g.normalized_word or g.gloss).lower()
                        for part in prev_prop.participants
                    )
                    or (
                        g.gloss not in ("PRO1", "PRO2", "PRO3", "MI", "TU", "SU")
                        and g.gloss in ("PADRE", "PAPA", "HOMBRE", "HERMANO", "HIJO")
                    )
                )
                if is_ref:
                    g.spatial_location = SpatialLocation.LEFT
        for g in prop_glosses:
            is_ref = (
                any(
                    part.semantic_role in (SemanticRole.AGENT, SemanticRole.THEME, SemanticRole.PATIENT)
                    and part.lemma.lower() in (g.normalized_word or g.gloss).lower()
                    for part in prop.participants
                )
                or (
                    g.gloss not in ("PRO1", "PRO2", "PRO3", "MI", "TU", "SU")
                    and g.gloss in ("MADRE", "MAMA", "MUJER", "HERMANA", "HIJA")
                )
            )
            if is_ref:
                g.spatial_location = SpatialLocation.RIGHT
            from app.services.fenasec_rules import get_verb_class
            if get_verb_class(g.gloss) == "single_arg_locus" or g.gloss in ("MORIR", "VIVIR", "NACER"):
                g.spatial_location = SpatialLocation.RIGHT
                g.target_spatial_location = SpatialLocation.RIGHT
            if not g.facial_expression or g.facial_expression == FacialExpression.NEUTRAL:
                g.facial_expression = FacialExpression.CONTRAST


def generate_spans_for_prop(
    planner: Any,
    prop: SemanticProposition,
    glosses: List[GlossItem],
    start_o: int,
    end_o: int,
    p_idx: int,
) -> List[NonManualSpan]:
    """Genera spans no manuales para la proposición con alcances sintácticos precisos."""
    spans: List[NonManualSpan] = []
    p_text_lower = prop.source_text.lower()

    prop_span_type = None
    prop_expr = FacialExpression.NEUTRAL
    prop_head = None
    prop_body = None
    prop_intensity = 1.0
    prop_priority = 1
    span_start = start_o
    span_end = end_o

    if ("quién" in p_text_lower and "quieres" in p_text_lower) or (
        prop.modality == "reflective" and "quién" in p_text_lower
    ):
        prop_span_type = "reflective"
        prop_expr = FacialExpression.REFLECTIVE
        prop_head = "inclinación_lateral_leve"
        prop_intensity = 0.6
        prop_priority = 2
    elif (
        prop.rhetorical_function == "sustainability_recognition"
        or "más destacada" in p_text_lower
        or "más sostenible" in p_text_lower
    ):
        prop_span_type = "superlative"
        prop_expr = FacialExpression.SUPERLATIVE
        prop_intensity = 1.2
        prop_priority = 3
        sup_glosses = [g for g in glosses if g.gloss in ("SOSTENIBILIDAD", "MÁS", "MÁS-DE", "DESTACAR")]
        if sup_glosses:
            span_start = min(g.order for g in sup_glosses)
            span_end = max(g.order for g in sup_glosses)
    elif prop.rhetorical_function == "inspiration":
        prop_span_type = "narrative"
        prop_expr = FacialExpression.NARRATIVE
        prop_head = "inclinación_lateral_leve"
        prop_intensity = 0.8
        prop_priority = 1
    elif prop.rhetorical_function in ("contrast",) or prop.discourse_relation in ("but", "not_only", "also"):
        prop_span_type = "contrast"
        prop_expr = FacialExpression.CONTRAST
        prop_body = "left" if prop.discourse_relation == "not_only" else "right"
        prop_intensity = 1.0
        prop_priority = 2
    elif prop.modality == "imperative" or prop.rhetorical_function in (
        "call_to_action", "future_decision", "imagination_to_reality"
    ):
        prop_span_type = "imperative"
        prop_expr = FacialExpression.IMPERATIVE
        prop_intensity = 1.1
        prop_priority = 2
    elif prop.rhetorical_function == "closure" or prop.modality == "exclamative":
        prop_span_type = "emphasis"
        prop_expr = FacialExpression.EMPHASIS
        prop_intensity = 1.2
        prop_priority = 2
    elif "?" in prop.source_text or "¿" in prop.source_text:
        has_wh = (
            any(t.text.lower() in planner._wh_lemmas for t in planner._nlp(prop.source_text))
            if planner._nlp
            else ("qué" in p_text_lower or "dónde" in p_text_lower)
        )
        prop_span_type = "question_wh" if has_wh else "question_yn"
        prop_expr = FacialExpression.QUESTION_WH if has_wh else FacialExpression.QUESTION_YESNO
        prop_head = "inclinar"
        prop_intensity = 1.2
        prop_priority = 3
        if prop.context_info.get("is_rhetorical"):
            prop_span_type = "rhetorical"
            prop_expr = FacialExpression.RHETORICAL

    if prop_span_type:
        spans.append(
            NonManualSpan(
                id=f"span_{p_idx + 1}_{prop_span_type}",
                type=prop_span_type,
                start_order=span_start,
                end_order=span_end,
                expression=prop_expr,
                head_movement=prop_head,
                body_shift=prop_body,
                intensity=prop_intensity,
                priority=prop_priority,
                proposition_id=prop.id,
            )
        )

    # El contraste (pero / no solo… sino / más que…) se marca siempre con su propio span, aunque otra
    # función retórica (p. ej. reflexiva) haya definido el span principal de la proposición: el sistema
    # no emite la glosa PERO, de modo que este marcador (desplazamiento corporal + cejas) es la señal.
    if prop.discourse_relation in ("but", "not_only", "more_than") and prop_span_type != "contrast":
        spans.append(
            NonManualSpan(
                id=f"span_{p_idx + 1}_contrast",
                type="contrast",
                start_order=start_o,
                end_order=end_o,
                expression=FacialExpression.CONTRAST,
                body_shift="left" if prop.discourse_relation == "not_only" else "right",
                intensity=1.0,
                priority=2,
                proposition_id=prop.id,
            )
        )

    if prop.polarity == "negative" or contains_negation(p_text_lower):
        neg_items = [
            g for g in glosses
            if g.gloss in ("NADIE", "SOLAMENTE-NO", "NO", "NUNCA") or g.gloss.startswith("NO-")
        ]
        if neg_items:
            neg_start = min(g.order for g in neg_items)
            neg_end = max(g.order for g in neg_items)
            spans.append(
                NonManualSpan(
                    id=f"span_{p_idx + 1}_negation",
                    type="negation",
                    start_order=neg_start,
                    end_order=neg_end,
                    expression=FacialExpression.NEGATION,
                    head_movement="negar",
                    intensity=0.9,
                    priority=3,
                    proposition_id=prop.id,
                )
            )

    if prop.context_info.get("tag_question") and glosses:
        spans.append(
            NonManualSpan(
                id=f"span_{p_idx + 1}_tag_q",
                type="question_yn",
                start_order=end_o,
                end_order=end_o,
                expression=FacialExpression.QUESTION_YESNO,
                head_movement="inclinar",
                intensity=1.0,
                priority=3,
                proposition_id=prop.id,
            )
        )

    return spans


def build_translation_plan_and_block(
    planner: Any,
    prop: SemanticProposition,
    p_idx: int,
    prop_glosses: List[GlossItem],
    prop_spans: List[NonManualSpan],
    prop_start_order: int,
    prop_end_order: int,
    strategy: StrategyType,
    frame: SemanticFrame,
    confidence_vec: ConfidenceVector,
    active_referents: Dict[str, SpatialReferent],
    all_operations: List[SpatialOperation],
) -> Tuple[List[GlossItem], TranslationPlan, DiscourseBlock]:
    """
    Calcula la cobertura conceptual, source_recall y realization_precision,
    filtra glosas no respaldadas y construye el `TranslationPlan` y `DiscourseBlock`.
    """
    p_text_lower = prop.source_text.strip().lower()
    src_concepts: List[str] = []
    if prop.predicate:
        src_concepts.append(prop.predicate.lemma)
    for part in prop.participants:
        src_concepts.append(part.lemma)

    realized_concepts = list({g.gloss for g in prop_glosses})

    implicit_lemmas = {p.lemma.lower() for p in prop.participants if p.is_implicit}
    required_concepts: List[str] = [
        c for c in src_concepts
        if c.lower() not in GRAMMATICAL_FUNCTIONAL_WORDS
        and c.lower() not in implicit_lemmas
    ]
    if not required_concepts and src_concepts:
        required_concepts = [
            c for c in src_concepts
            if c.lower() not in implicit_lemmas and c.lower() not in GRAMMATICAL_FUNCTIONAL_WORDS
        ] or list(src_concepts)

    def _concept_is_realized(
        concept_str: str,
        realized_set: Set[str],
        glosses_list: List[GlossItem],
    ) -> bool:
        c_clean = concept_str.strip().lower()
        c_upper = c_clean.upper()
        c_stem = c_clean[:4].upper() if len(c_clean) >= 4 else c_upper

        if c_clean in MWE_CONCEPT_SYNONYMS:
            if any(syn in realized_set for syn in MWE_CONCEPT_SYNONYMS[c_clean]):
                return True

        if _INTENSIFIER_RE.match(c_clean) and any(rg.endswith("++") for rg in realized_set):
            return True

        for rg in realized_set:
            rg_no_hyphen = rg.replace("-", "")
            if c_upper == rg or c_upper == rg_no_hyphen or c_upper in rg or rg in c_upper:
                return True
            if planner._lemma_overrides.get(c_clean, "").upper() == rg:
                return True
            if len(c_stem) >= 3 and (c_stem in rg or rg[:4] == c_stem):
                return True
            if "_" in c_clean:
                parts = [p for p in c_clean.split("_") if len(p) >= 3]
                if any(p.upper() in rg or rg in p.upper() or p[:4].upper() == rg[:4] for p in parts):
                    return True
        for g in glosses_list:
            if g.source_word and c_clean in g.source_word.lower():
                return True
            if g.normalized_word and c_clean in g.normalized_word.lower():
                return True
            if g.semantic_concept and c_clean in g.semantic_concept.lower():
                return True
        return False

    omitted_concepts = [
        c for c in required_concepts
        if not _concept_is_realized(c, set(realized_concepts), prop_glosses)
    ]
    if (
        "ver" in {c.lower() for c in omitted_concepts}
        and any(g.gloss == "VENIR" for g in prop_glosses)
        and re.search(r"\bven(?:ga|gan)?\b", p_text_lower)
    ):
        omitted_concepts = [c for c in omitted_concepts if c.lower() != "ver"]
    if (
        "quinientos" in p_text_lower
        and "CINCO" in realized_concepts
        and "CIENTOS" in realized_concepts
    ):
        omitted_concepts = [c for c in omitted_concepts if c.lower() != "quinientos"]

    unsupported_concepts: List[str] = []
    cross_prop_concepts: List[str] = []

    if "oportunidad" in p_text_lower and "crean" in p_text_lower and "ideas" not in p_text_lower:
        if any(g in realized_concepts for g in ("IDEA", "DESARROLLAR")):
            cross_prop_concepts.extend([g for g in ("IDEA", "DESARROLLAR") if g in realized_concepts])

    if "ideas" in p_text_lower and "oportunidad" not in p_text_lower:
        if "OPORTUNIDAD" in realized_concepts:
            cross_prop_concepts.append("OPORTUNIDAD")

    source_recall = 1.0 - (len(omitted_concepts) / max(len(required_concepts), 1))
    source_recall = max(min(round(source_recall, 2), 1.0), 0.0)

    realization_precision = 1.0 - (
        (len(unsupported_concepts) + len(cross_prop_concepts)) / max(len(realized_concepts), 1)
    )
    realization_precision = max(min(round(realization_precision, 2), 1.0), 0.0)

    cov_status = "COMPLETE"
    if cross_prop_concepts:
        cov_status = "CONTENT_LEAK"
    elif source_recall < 0.5:
        cov_status = "FAILED"
    elif source_recall < 1.0 or realization_precision < 1.0:
        cov_status = "PARTIAL"

    source_concept_items_list: List[SourceConceptItem] = []
    if prop.predicate:
        source_concept_items_list.append(
            SourceConceptItem(
                id=f"c_{prop.id}_pred_{prop.predicate.lemma}",
                lemma=prop.predicate.lemma,
                concept_type="PREDICATE",
                required=prop.predicate.lemma.lower() not in ("upec", "ser", "existir", "tener", "estar", "haber"),
                proposition_id=prop.id,
                global_source_token_indexes=prop.global_source_token_indexes,
                source_start_seconds=prop.source_start_seconds,
                source_end_seconds=prop.source_end_seconds,
                support_type="EXPLICIT",
            )
        )
    for p_idx_part, part in enumerate(prop.participants):
        source_concept_items_list.append(
            SourceConceptItem(
                id=f"c_{prop.id}_part_{p_idx_part}_{part.lemma}",
                lemma=part.lemma,
                concept_type="PARTICIPANT",
                required=not part.is_implicit and part.lemma.lower() not in GRAMMATICAL_FUNCTIONAL_WORDS,
                proposition_id=prop.id,
                global_source_token_indexes=prop.global_source_token_indexes,
                source_start_seconds=prop.source_start_seconds,
                source_end_seconds=prop.source_end_seconds,
                support_type="EXPLICIT" if not part.is_implicit else "IMPLICIT",
            )
        )
    for op_idx, op in enumerate(prop.operators):
        op_t = op.get("type") or op.get("operator_type", "OPERATOR")
        source_concept_items_list.append(
            SourceConceptItem(
                id=f"c_{prop.id}_op_{op_idx}_{op_t}",
                lemma=op_t,
                concept_type="OPERATOR",
                required=False,
                proposition_id=prop.id,
                support_type="EXPLICIT",
            )
        )
    for g in prop_glosses:
        if g.source_word:
            w_norm = g.normalized_word or g.source_word
            if not any(
                sci.lemma.lower() == w_norm.lower() or sci.lemma.lower() == g.source_word.lower()
                for sci in source_concept_items_list
            ):
                source_concept_items_list.append(
                    SourceConceptItem(
                        id=f"c_{prop.id}_src_{g.order}_{w_norm}",
                        lemma=w_norm,
                        concept_type="CONTENT_WORD",
                        required=False,
                        proposition_id=prop.id,
                        support_type="EXPLICIT",
                    )
                )

    realized_concept_items_list: List[RealizedConceptItem] = []
    for g in prop_glosses:
        status = "SOURCE"
        if g.alignment_type == AlignmentType.PARAPHRASE:
            status = "PARAPHRASE"
        elif g.alignment_type == AlignmentType.INFERRED:
            status = "INFERRED"
        elif g.alignment_type == AlignmentType.COREFERENCE:
            status = "COREFERENCE"
        elif g.alignment_type == AlignmentType.ENTITY_ALIAS:
            status = "ENTITY_ALIAS"
        elif g.alignment_type == AlignmentType.DISCOURSE_MARKER:
            status = "DISCOURSE"
        elif g.alignment_type == AlignmentType.DEICTIC:
            status = "DEICTIC"

        mapped_cids: List[str] = []
        for sci in source_concept_items_list:
            if (
                _concept_is_realized(sci.lemma, {g.gloss}, [g])
                or sci.lemma.lower() == (g.normalized_word or "").lower()
                or sci.lemma.lower() == (g.source_word or "").lower()
            ):
                mapped_cids.append(sci.id)

        if g.gloss.startswith("PRO") and not g.inference_rule_id:
            g.inference_rule_id = "LSEC_PRODROP_RESOLVE"

        has_explicit_support = bool(mapped_cids)
        has_inferred_support = (
            (g.alignment_type == AlignmentType.INFERRED and bool(g.inference_rule_id))
            or (g.gloss.startswith("PRO") and bool(g.inference_rule_id))
        )
        has_coref_support = (
            g.alignment_type == AlignmentType.COREFERENCE
            and bool(g.antecedent_proposition_id or g.coreference_target_id)
        )
        has_discourse_support = (
            g.alignment_type == AlignmentType.DISCOURSE_MARKER and bool(g.discourse_relation)
        )
        has_paraphrase_support = (
            g.alignment_type == AlignmentType.PARAPHRASE and bool(g.semantic_concept or g.source_word)
        )
        has_entity_support = (
            g.alignment_type == AlignmentType.ENTITY_ALIAS and bool(g.spatial_ref or g.source_word)
        )
        has_deictic_support = (
            g.alignment_type == AlignmentType.DEICTIC and bool(g.source_word or mapped_cids)
        )
        has_grammatical_support = (
            g.alignment_type in (AlignmentType.GRAMMATICAL, AlignmentType.DISCOURSE_MARKER)
            or g.lexical_strategy in ("grammatical_plural", "discourse_connector")
            or g.gloss in ("ADEMÁS", "VARIOS", "PERO", "AUNQUE", "PORQUE", "CAUSA")
        )

        is_supported = (
            has_explicit_support
            or has_inferred_support
            or has_coref_support
            or has_discourse_support
            or has_paraphrase_support
            or has_entity_support
            or has_deictic_support
            or has_grammatical_support
        )

        s_range = None
        if g.global_source_token_indexes and g.source_start_seconds is not None:
            s_range = {
                "start_seconds": g.source_start_seconds,
                "end_seconds": g.source_end_seconds,
                "tokens": g.global_source_token_indexes,
            }

        realized_concept_items_list.append(
            RealizedConceptItem(
                concept=g.gloss,
                support_type=status,
                source_concept_ids=mapped_cids,
                origin_proposition_id=prop.id,
                confidence=g.alignment_confidence,
                inference_rule_id=g.inference_rule_id,
                coreference_target_id=g.coreference_target_id,
                antecedent_proposition_id=g.antecedent_proposition_id,
                discourse_relation=g.discourse_relation
                or (prop.discourse_relation if g.gloss == "ADEMÁS" else None),
                entity_id=g.entity_alias_id or g.spatial_ref,
                source_range=s_range,
                is_supported=is_supported,
            )
        )

    unsupported_concepts = [r.concept for r in realized_concept_items_list if not r.is_supported]
    if unsupported_concepts:
        unsupported_set = set(unsupported_concepts)
        prop_glosses = [g for g in prop_glosses if g.gloss not in unsupported_set]

    realization_precision = (
        len(realized_concept_items_list) - len(unsupported_concepts) - len(cross_prop_concepts)
    ) / max(len(realized_concept_items_list), 1)
    realization_precision = max(min(round(realization_precision, 2), 1.0), 0.0)

    if unsupported_concepts or omitted_concepts:
        cov_status = "PARTIAL" if source_recall >= 0.5 else "FAILED"
    elif cross_prop_concepts:
        cov_status = "CONTENT_LEAK"

    inferred_concepts_list: List[InferredConcept] = []
    if any(g.gloss == "AHORA" for g in prop_glosses) and "hoy" in p_text_lower:
        inferred_concepts_list.append(
            InferredConcept(
                concept="AHORA",
                origin=InferredConceptOrigin.SOURCE,
                origin_proposition_id=prop.id,
                confidence=0.95,
            )
        )
    if any(g.gloss == "ELLOS" for g in prop_glosses):
        inferred_concepts_list.append(
            InferredConcept(
                concept="ELLOS",
                origin=InferredConceptOrigin.COREFERENCE,
                origin_proposition_id=prop.id,
                inference_rule_id="PRONOUN_ELLOS_COREFERENCE",
                confidence=0.90,
            )
        )

    plan = TranslationPlan(
        id=f"plan_{prop.id}",
        proposition_id=prop.id,
        selected_strategy=strategy,
        topic=prop.topic,
        focus=prop.focus,
        manual_components=[
            g.gloss for g in prop_glosses
            if g.gloss_type in (GlossType.SIGN, GlossType.FINGERSPELLING)
        ],
        lexical_items=[g.gloss for g in prop_glosses],
        paraphrase_items=[
            g.gloss for g in prop_glosses if g.lexical_strategy == "semantic_paraphrase"
        ],
        spatial_operations=[
            op for op in all_operations
            if op.source_order is not None and prop_start_order <= op.source_order <= prop_end_order
        ],
        non_manual_requirements=[s.type for s in prop_spans],
        source_concept_items=source_concept_items_list,
        realized_concept_items=realized_concept_items_list,
        source_concepts=src_concepts,
        required_source_concepts=required_concepts,
        optional_source_concepts=[],
        realized_concepts=realized_concepts,
        omitted_concepts=omitted_concepts,
        unsupported_realized_concepts=unsupported_concepts,
        cross_proposition_concepts=cross_prop_concepts,
        inferred_concepts=inferred_concepts_list,
        source_recall=source_recall,
        extraction_coverage_ratio=source_recall,
        realization_coverage_ratio=realization_precision,
        realization_precision=realization_precision,
        coverage_ratio=source_recall,
        coverage_status=cov_status,
        confidence=confidence_vec.overall if confidence_vec.overall > 0 else prop.confidence,
        applied_rule_ids=frame.applied_rule_ids,
        confidence_vector=confidence_vec.to_dict(),
    )

    block_label = (prop.rhetorical_function or f"BLOCK_{p_idx + 1}").upper()
    if prop.modality == "interrogative_yn":
        disc_func = "question_yn"
    elif prop.modality == "interrogative_wh":
        disc_func = "question_wh"
    elif prop.rhetorical_function:
        disc_func = prop.rhetorical_function
    else:
        disc_func = "imperative" if prop.modality == "imperative" else "statement"

    block = DiscourseBlock(
        id=p_idx,
        label=block_label,
        discourse_function=disc_func,
        start_order=prop_start_order,
        end_order=prop_end_order,
        gloss_ids=[str(g.id) for g in prop_glosses],
        proposition_ids=[prop.id],
        active_referents=list(active_referents.keys()),
        base_expression=prop_spans[0].expression if prop_spans else FacialExpression.NEUTRAL,
        pause_before_ms=0,
        pause_after_ms=250 if strategy == StrategyType.CONTRAST_PAIR else 300,
        confidence=prop.confidence,
    )

    return prop_glosses, plan, block
