"""
Servicio Centralizado de Propagación de Revisión y Validación Humana (LSEC 2.1.1).

Garantiza la coherencia total de marcas de revisión a lo largo de toda la jerarquía:
GlossItem -> TranslationPlan -> SemanticProposition -> DiscourseBlock -> ValidationMetadata -> ExecutionStatus.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.core.schemas import (
    AlignmentType,
    DiscourseBlock,
    ExecutionStatus,
    GlossItem,
    SemanticProposition,
    StrategyType,
    TranslationPlan,
    ValidationMetadata,
)

logger = logging.getLogger(__name__)


class ReviewPropagationService:
    """
    Propaga y valida banderas de revisión nativa y acústica.
    """

    def propagate_reviews(
        self,
        propositions: List[SemanticProposition],
        plans: List[TranslationPlan],
        glosses: List[GlossItem],
        blocks: List[DiscourseBlock],
        unresolved_items: Optional[List[Any]] = None,
        dubious_words: Optional[List[Any]] = None,
        has_blocking_errors: bool = False,
    ) -> Tuple[List[SemanticProposition], List[TranslationPlan], List[GlossItem], List[DiscourseBlock], ValidationMetadata]:
        """
        Aplica la política unificada de propagación de revisión y retorna ValidationMetadata consistente.
        """
        unresolved_items = unresolved_items or []
        if dubious_words:
            for dub in dubious_words:
                if hasattr(dub, "to_dict"):
                    unresolved_items.append(dub.to_dict())
                elif isinstance(dub, dict):
                    unresolved_items.append(dub)

        pending_native_gloss_ids: List[str] = []
        pending_audio_gloss_ids: List[str] = []
        pending_semantic_ids: List[str] = []
        review_reasons: List[str] = []
        dubious_words_set = set()
        for dub in unresolved_items:
            w = dub.get("source_word") or dub.get("word")
            if w:
                dubious_words_set.add(w.lower())

        # 1. Nivel GlossItem: auditar paráfrasis, acústica y conceptos especiales
        for g in glosses:
            is_paraphrase = (
                g.lexical_strategy == "semantic_paraphrase"
                or g.alignment_type == AlignmentType.PARAPHRASE
            )

            if is_paraphrase:
                g.requires_review = True
                g.requires_native_review = True
                if not g.review_reasons:
                    g.review_reasons.append(f"Paráfrasis conceptual de '{g.source_word or g.gloss}' sujeta a validación por personas sordas nativas.")

            src_w = (g.source_word or "").lower()
            norm_w = (g.normalized_word or "").lower()
            is_audio_doubt = bool(g.requires_audio_review) or (src_w in dubious_words_set) or (norm_w in dubious_words_set)

            if is_audio_doubt:
                g.requires_review = True
                g.requires_audio_review = True
                if not any("acústica" in r.lower() or "auditiva" in r.lower() for r in g.review_reasons):
                    g.review_reasons.append("Término con alta confianza acústica ASR pero baja coherencia contextual. Requiere revisión de audio.")

            if g.requires_native_review:
                pending_native_gloss_ids.append(str(g.id))
                review_reasons.extend(g.review_reasons)
            if g.requires_audio_review:
                pending_audio_gloss_ids.append(str(g.id))
                review_reasons.extend(g.review_reasons)

        # 2. Nivel TranslationPlan
        plan_by_prop_id: Dict[str, TranslationPlan] = {p.proposition_id: p for p in plans}
        for plan in plans:
            plan_glosses = [g for g in glosses if g.proposition_id == plan.proposition_id]
            has_paraphrase = any(g.requires_native_review for g in plan_glosses) or plan.selected_strategy == StrategyType.SEMANTIC_PARAPHRASE
            has_audio = any(g.requires_audio_review for g in plan_glosses)

            if has_paraphrase:
                plan.requires_native_review = True
            if has_audio:
                plan.requires_audio_review = True

        # 3. Nivel SemanticProposition
        for prop in propositions:
            prop_glosses = [g for g in glosses if g.proposition_id == prop.id]
            prop_plan = plan_by_prop_id.get(prop.id)

            prop_needs_native = any(g.requires_native_review for g in prop_glosses) or (prop_plan is not None and prop_plan.requires_native_review)
            prop_needs_audio = any(g.requires_audio_review for g in prop_glosses) or (prop_plan is not None and prop_plan.requires_audio_review)

            if prop_needs_native or prop_needs_audio:
                prop.requires_review = True
                for g in prop_glosses:
                    for r in g.review_reasons:
                        if r not in prop.review_reasons:
                            prop.review_reasons.append(r)

            if prop.requires_review:
                pending_semantic_ids.append(prop.id)

        # 4. Nivel DiscourseBlock
        for block in blocks:
            block_props = [p for p in propositions if p.id in block.proposition_ids]
            block_glosses = [g for g in glosses if g.discourse_block_id == block.id or str(g.id) in block.gloss_ids]

            block.requires_native_review = any(p.requires_review for p in block_props) or any(g.requires_native_review for g in block_glosses)
            block.requires_audio_review = any(g.requires_audio_review for g in block_glosses)

        # 5. Revisar elementos no resueltos
        for unres in unresolved_items:
            if unres.get("requires_audio_review", True):
                src_w = unres.get("source_word", "audio_item")
                if src_w not in pending_audio_gloss_ids:
                    pending_audio_gloss_ids.append(src_w)
                review_reasons.append(f"Elemento no resuelto '{src_w}' pendiente de verificación auditiva.")

        requires_native_review = bool(pending_native_gloss_ids)
        requires_audio_review = bool(pending_audio_gloss_ids)
        unique_reasons = list(dict.fromkeys(review_reasons))

        # 6. Determinar ExecutionStatus y ReviewStatus
        pending_review_types: List[str] = []
        if requires_native_review:
            pending_review_types.append("NATIVE_LINGUISTIC")
        if requires_audio_review:
            pending_review_types.append("AUDIO")

        if requires_native_review and requires_audio_review:
            review_status_val = "PENDING_NATIVE_AND_AUDIO_REVIEW"
        elif requires_native_review:
            review_status_val = "PENDING_NATIVE_REVIEW"
        elif requires_audio_review:
            review_status_val = "PENDING_AUDIO_REVIEW"
        else:
            review_status_val = "VERIFIED"

        if has_blocking_errors:
            exec_status = ExecutionStatus.BLOCKED
        elif requires_native_review or requires_audio_review or pending_semantic_ids:
            exec_status = ExecutionStatus.REVIEW_REQUIRED
        else:
            exec_status = ExecutionStatus.READY

        validation_metadata = ValidationMetadata(
            schema_version="2.1",
            engine_version="2.1.1",
            pipeline_version="2.1.1",
            execution_status=exec_status,
            native_reviewed=False,
            requires_native_review=requires_native_review,
            requires_audio_review=requires_audio_review,
            review_status=review_status_val,
            pending_review_types=pending_review_types,
            blocking_issue_codes=[],
            review_reasons=unique_reasons,
            pending_native_review_gloss_ids=list(dict.fromkeys(pending_native_gloss_ids)),
            pending_audio_review_ids=list(dict.fromkeys(pending_audio_gloss_ids)),
            pending_semantic_review_ids=list(dict.fromkeys(pending_semantic_ids)),
            propositions_count=len(propositions),
            plans_count=len(plans),
            glosses_count=len(glosses),
            blocks_count=len(blocks),
        )

        return propositions, plans, glosses, blocks, validation_metadata
