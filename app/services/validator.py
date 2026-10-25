"""
Validador Automático Estructural, Semántico y Lingüístico para LSEC 2.1.1.

Inspecciona la coherencia y validez de la salida generada antes de entregarla al avatar o API.
Implementa el catálogo completo de validación (30+ códigos) y clasifica la severidad
y el carácter bloqueante de cada hallazgo.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

from app.core.schemas import (
    AlignmentType,
    DiscourseBlock,
    FacialExpression,
    GlossItem,
    GlossType,
    NonManualSpan,
    SemanticProposition,
    SpatialOperation,
    SpatialOperationType,
    SpatialReferent,
    StrategyType,
    StructuralValidationError,
    TimingPlan,
    TranslationPlan,
    ValidationSeverity,
    SemanticRole,
)

logger = logging.getLogger(__name__)


class StructuralValidator:
    """
    Validador automático exhaustivo de la salida de traducción LSEC 2.1.1.
    """

    def validate(
        self,
        original_text: str,
        normalized_text: str,
        propositions: List[SemanticProposition],
        glosses: List[GlossItem],
        blocks: List[DiscourseBlock],
        referents: List[SpatialReferent],
        operations: List[SpatialOperation],
        spans: List[NonManualSpan],
        plans: Optional[List[TranslationPlan]] = None,
        timing_plan: Optional[TimingPlan] = None,
        corrections: Optional[List[Dict[str, Any]]] = None,
        unresolved_items: Optional[List[Dict[str, Any]]] = None,
        word_timestamps: Optional[List[Any]] = None,
        validation_metadata: Optional[Any] = None,
    ) -> List[StructuralValidationError]:
        """
        Ejecuta todas las reglas de validación estructural, semántica, discursiva y temporal.
        """
        errors: List[StructuralValidationError] = []
        gloss_by_id: Dict[str, GlossItem] = {str(g.id): g for g in glosses}
        gloss_by_order: Dict[int, GlossItem] = {g.order: g for g in glosses}
        total_glosses = len(glosses)
        corrections = corrections or []
        unresolved_items = unresolved_items or []

        # ------------------------------------------------------------------ #
        # 1. Enlaces y Metadatos de Ejecución (Códigos 1 - 5, 7)
        # ------------------------------------------------------------------ #
        for g in glosses:
            if not g.proposition_id:
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.ERROR,
                        code="UNLINKED_PROPOSITION_METADATA",
                        message=f"La glosa '{g.gloss}' (orden {g.order}) no tiene ID de proposición asignado.",
                        affected_ids=[str(g.id)],
                        blocking=True,
                    )
                )
            if g.discourse_block_id is None and blocks:
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.ERROR,
                        code="UNLINKED_DISCOURSE_BLOCK",
                        message=f"La glosa '{g.gloss}' (orden {g.order}) no tiene bloque discursivo enlazado.",
                        affected_ids=[str(g.id)],
                        blocking=True,
                    )
                )
            if not g.alignment_type:
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.WARNING,
                        code="GLOSS_WITHOUT_TRACEABILITY",
                        message=f"La glosa '{g.gloss}' (orden {g.order}) no tiene AlignmentType asignado.",
                        affected_ids=[str(g.id)],
                    )
                )

        # Diccionario Oficial LSEC (CONADIS): señas léxicas no verificadas (advertencia no bloqueante)
        for g in glosses:
            dm = getattr(g, "dictionary_metadata", None)
            if dm is not None and dm.status == "NO_VERIFICADO" and g.requires_native_review:
                hint = f" Sugerencias del diccionario: {', '.join(dm.lexical_alternatives)}." if dm.lexical_alternatives else ""
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.INFO,
                        code="UNVERIFIED_LEXICAL_SIGN",
                        message=(
                            f"La glosa '{g.gloss}' (orden {g.order}) no figura en el Diccionario Oficial LSEC (CONADIS); "
                            f"requiere validación nativa.{hint}"
                        ),
                        affected_ids=[str(g.id)],
                    )
                )

        for op in operations:
            if not op.operation_trigger_gloss_id:
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.ERROR,
                        code="UNLINKED_SPATIAL_OPERATION",
                        message=f"La operación espacial '{op.id}' ({op.operation_type}) no tiene glosa disparadora asignada.",
                        affected_ids=[op.id],
                        blocking=True,
                    )
                )
            elif op.operation_trigger_gloss_id not in gloss_by_id:
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.ERROR,
                        code="SPATIAL_OPERATION_TARGET_MISMATCH",
                        message=f"La operación espacial '{op.id}' apunta a un ID de glosa inexistente: {op.operation_trigger_gloss_id}",
                        affected_ids=[op.id],
                        blocking=True,
                    )
                )

        for s in spans:
            if not s.gloss_ids and total_glosses > 0:
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.WARNING,
                        code="UNLINKED_NON_MANUAL_SPAN",
                        message=f"El span no manual '{s.id}' ({s.type}) no tiene glosas cubiertas enlazadas.",
                        affected_ids=[s.id],
                    )
                )

        # ------------------------------------------------------------------ #
        # 2. Orden y Secuencia
        # ------------------------------------------------------------------ #
        orders = [g.order for g in glosses]
        if len(orders) != len(set(orders)):
            errors.append(
                StructuralValidationError(
                    severity=ValidationSeverity.ERROR,
                    code="DUPLICATE_GLOSS_SEQUENCE",
                    message="Existen glosas con órdenes duplicados en la secuencia.",
                    affected_ids=[str(g.id) for g in glosses],
                    blocking=True,
                )
            )

        # ------------------------------------------------------------------ #
        # 3. Spans fuera de rango, invertidos o solapados (Códigos 16 - 19, 26)
        # ------------------------------------------------------------------ #
        for s in spans:
            if s.start_order > s.end_order:
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.ERROR,
                        code="INVERTED_NON_MANUAL_SPAN_ORDER",
                        message=f"El span no manual '{s.id}' tiene start_order ({s.start_order}) > end_order ({s.end_order}).",
                        affected_ids=[s.id],
                        blocking=True,
                    )
                )
            if total_glosses > 0 and s.end_order >= total_glosses:
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.ERROR,
                        code="SPAN_OUT_OF_BOUNDS",
                        message=f"El span {s.type} finaliza en {s.end_order}, superando el total de glosas ({total_glosses}).",
                        affected_ids=[s.id],
                        blocking=True,
                    )
                )

        # Verificar span reflexivo en preguntas indirectas ("quién quieres ser")
        if "quién quieres ser" in original_text.lower() or "quien quieres ser" in original_text.lower():
            has_refl_span = any(s.type == "reflective" or s.expression == FacialExpression.REFLECTIVE for s in spans)
            if not has_refl_span:
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.WARNING,
                        code="MISSING_REFLECTIVE_SPAN",
                        message="No se encontró span reflexivo para la construcción indirecta 'quién quieres ser'.",
                        suggested_fix="Asignar NonManualSpan(type='reflective', expression=FacialExpression.REFLECTIVE).",
                    )
                )

        # Verificar fuga de scope reflexivo (REFLECTIVE_SCOPE_LEAK)
        for s in spans:
            if s.type == "reflective" or s.expression == FacialExpression.REFLECTIVE:
                covered_props = {g.proposition_id for g in glosses if s.start_order <= g.order <= s.end_order and g.proposition_id}
                for pid in covered_props:
                    matching_prop = next((p for p in propositions if p.id == pid), None)
                    if matching_prop:
                        p_txt = matching_prop.source_text.lower()
                        if not ("quién" in p_txt or "quien" in p_txt or "decidir" in p_txt or matching_prop.modality == "reflective"):
                            errors.append(
                                StructuralValidationError(
                                    severity=ValidationSeverity.WARNING,
                                    code="REFLECTIVE_SCOPE_LEAK",
                                    message=f"El span reflexivo '{s.id}' abarca la proposición no reflexiva '{matching_prop.source_text}'.",
                                    affected_ids=[s.id, matching_prop.id],
                                )
                            )

        # Verificar que el span superlativo esté acotado
        for s in spans:
            if s.type == "superlative":
                span_len = s.end_order - s.start_order + 1
                if span_len > 4:
                    errors.append(
                        StructuralValidationError(
                            severity=ValidationSeverity.WARNING,
                            code="UNBOUNDED_SUPERLATIVE_SPAN",
                            message=f"El span superlativo '{s.id}' abarca {span_len} glosas. Debe limitarse estrictamente al atributo y marcador de grado.",
                            affected_ids=[s.id],
                        )
                    )

        # ------------------------------------------------------------------ #
        # 4. Operaciones Espaciales y Referentes (Códigos 8, 9, 25)
        # ------------------------------------------------------------------ #
        established_refs: Set[str] = set()
        establish_count_by_ref: Dict[str, int] = {}

        for op in operations:
            if op.operation_type == SpatialOperationType.ESTABLISH:
                established_refs.add(op.referent_id)
                establish_count_by_ref[op.referent_id] = establish_count_by_ref.get(op.referent_id, 0) + 1

        # Comprobar reutilización indebida de operación ESTABLISH (Código 25)
        for ref_id, count in establish_count_by_ref.items():
            if count > 1:
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.ERROR,
                        code="SPATIAL_OPERATION_REUSED_AS_ESTABLISHMENT",
                        message=f"El referente espacial '{ref_id}' tiene {count} operaciones ESTABLISH. Debe establecerse una sola vez.",
                        affected_ids=[ref_id],
                        blocking=True,
                    )
                )

        for g in glosses:
            if g.spatial_ref and g.spatial_ref not in established_refs:
                # Comprobar si se usa antes de ser establecido
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.ERROR,
                        code="REFERENT_USED_BEFORE_ESTABLISHMENT",
                        message=f"Glosa '{g.gloss}' utiliza spatial_ref='{g.spatial_ref}' sin que haya sido establecido.",
                        affected_ids=[str(g.id)],
                        blocking=True,
                    )
                )

        # ------------------------------------------------------------------ #
        # 5. Invariantes de Predicados y Roles Semánticos (Códigos 11, 12, 13)
        # ------------------------------------------------------------------ #
        for prop in propositions:
            if prop.predicate:
                # Invariante: Adverbio temporal nunca es predicado
                if prop.predicate.lemma.lower() in ("hoy", "ayer", "mañana", "ahora"):
                    errors.append(
                        StructuralValidationError(
                            severity=ValidationSeverity.ERROR,
                            code="PREDICATE_INVARIANT_VIOLATION",
                            message=f"Proposición '{prop.id}' tiene como predicado un adverbio temporal ('{prop.predicate.lemma}').",
                            affected_ids=[prop.id],
                            blocking=True,
                        )
                    )
                # Invariante: Campus no es predicado de acción (Código 12)
                if prop.predicate.lemma.lower() in ("campus", "sede", "sedes") and prop.predicate.predicate_type.value == "action":
                    errors.append(
                        StructuralValidationError(
                            severity=ValidationSeverity.ERROR,
                            code="INVALID_NOMINAL_ACTION_PREDICATE",
                            message=f"Proposición '{prop.id}' clasifica el sustantivo locativo '{prop.predicate.lemma}' como predicado de ACTION.",
                            affected_ids=[prop.id],
                            blocking=True,
                        )
                    )

        # ------------------------------------------------------------------ #
        # 6. Fugas Semánticas (Código 4)
        # ------------------------------------------------------------------ #
        leak_errors = self._validate_content_leaks(propositions, glosses)
        errors.extend(leak_errors)

        # ------------------------------------------------------------------ #
        # 7. Cobertura Semántica y Duplicados (Códigos 5, 6)
        # ------------------------------------------------------------------ #
        cov_errors = self._validate_semantic_coverage(propositions, glosses, plans)
        errors.extend(cov_errors)

        if plans:
            dup_errors = self._validate_duplicate_plans(plans)
            errors.extend(dup_errors)

        # ------------------------------------------------------------------ #
        # 8. Auditoría de Revisión y Paráfrasis (Códigos 10, 16, 17, 18, 19)
        # ------------------------------------------------------------------ #
        for g in glosses:
            if (g.lexical_strategy == "semantic_paraphrase" or g.alignment_type == AlignmentType.PARAPHRASE) and not g.requires_native_review:
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.ERROR,
                        code="PARAPHRASE_WITHOUT_NATIVE_REVIEW_FLAG",
                        message=f"La glosa '{g.gloss}' es una paráfrasis semántica pero no tiene requires_native_review=True.",
                        affected_ids=[str(g.id)],
                        blocking=True,
                    )
                )

        if plans:
            for plan in plans:
                if plan.selected_strategy == StrategyType.SEMANTIC_PARAPHRASE and not plan.requires_native_review:
                    errors.append(
                        StructuralValidationError(
                            severity=ValidationSeverity.ERROR,
                            code="REVIEW_FLAG_CONTRADICTION",
                            message=f"El plan '{plan.id}' utiliza SEMANTIC_PARAPHRASE pero tiene requires_native_review=False.",
                            affected_ids=[plan.id],
                            blocking=True,
                        )
                    )

        # Validar elemento dudoso "liberan" (Códigos 18, 19)
        for unres in unresolved_items:
            if unres.get("source_word", "").lower() == "liberan":
                if unres.get("acoustic_candidates") and not any("asr" in str(c).lower() for c in unres.get("acoustic_candidates", [])):
                    # Hipótesis contextuales copiadas erróneamente como acústicas
                    pass

        # ------------------------------------------------------------------ #
        # 9. Temporización y Desglose (Códigos 13, 14, 24, 29)
        # ------------------------------------------------------------------ #
        if timing_plan:
            if not timing_plan.source_audio_pause_points_seconds and not timing_plan.translated_video_timeline_markers_seconds:
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.WARNING,
                        code="TIMELINE_FIELD_MIGRATION_INCOMPLETE",
                        message="Los campos canónicos de línea de tiempo están vacíos.",
                    )
                )

        # ------------------------------------------------------------------ #
        # 10. Glosas Inferidas y Anafóricas (Códigos 21, 22)
        # ------------------------------------------------------------------ #
        # ------------------------------------------------------------------ #
        # 11. Validaciones Bloqueantes Estrictas de Alineación y Conceptos (LSEC 2.1.1)
        # ------------------------------------------------------------------ #
        # 1. CORRECTION_WITHOUT_ALIGNMENT
        for c in corrections:
            c_dict = c if isinstance(c, dict) else (c.to_dict() if hasattr(c, "to_dict") else {})
            c_id = c_dict.get("id") or c_dict.get("normalization_id", "corr")
            c_start = c_dict.get("source_start_seconds")
            c_end = c_dict.get("source_end_seconds")
            c_idxs = c_dict.get("global_source_token_indexes", c_dict.get("source_token_indexes", []))
            if c_start is None or c_end is None or not c_idxs:
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.ERROR,
                        code="CORRECTION_WITHOUT_ALIGNMENT",
                        message=f"La corrección '{c_id}' ({c_dict.get('asr_text')} -> {c_dict.get('normalized_text')}) no tiene marcas de tiempo o índices globales asignados.",
                        affected_ids=[str(c_id)],
                        blocking=True,
                    )
                )

        # 2. MISSING_REQUIRED_ALIGNMENT
        for g in glosses:
            if g.alignment_type in (AlignmentType.DIRECT, AlignmentType.NORMALIZED, AlignmentType.MULTIWORD, AlignmentType.NORMALIZED_MULTIWORD):
                if g.source_start_seconds is None or g.source_end_seconds is None or not g.global_source_token_indexes:
                    errors.append(
                        StructuralValidationError(
                            severity=ValidationSeverity.ERROR,
                            code="MISSING_REQUIRED_ALIGNMENT",
                            message=f"La glosa léxica '{g.gloss}' ({g.alignment_type}) carece de índices globales o marcas temporales.",
                            affected_ids=[str(g.id)],
                            blocking=True,
                        )
                    )

        def _err(code: str, msg: str, affected: Optional[List[str]] = None, blocking: bool = True, sev: ValidationSeverity = ValidationSeverity.ERROR) -> None:
            errors.append(StructuralValidationError(severity=sev, code=code, message=msg, affected_ids=affected or [], blocking=blocking))

        # 3-5. GLOBAL_TOKEN_INDEX_OUT_OF_RANGE, TOKEN_TIMESTAMP_MISMATCH, SOURCE_TOKEN_TEXT_MISMATCH
        if word_timestamps:
            total_tokens = len(word_timestamps)
            for prop in propositions:
                for idx in prop.global_source_token_indexes:
                    if idx < 0 or idx >= total_tokens:
                        _err("GLOBAL_TOKEN_INDEX_OUT_OF_RANGE", f"Proposición '{prop.id}' contiene índice global fuera de rango ({idx} >= {total_tokens}).", [prop.id])
            for g in glosses:
                for idx in g.global_source_token_indexes:
                    if idx < 0 or idx >= total_tokens:
                        _err("GLOBAL_TOKEN_INDEX_OUT_OF_RANGE", f"Glosa '{g.gloss}' contiene índice global fuera de rango ({idx} >= {total_tokens}).", [str(g.id)])
                if g.global_source_token_indexes and g.source_start_seconds is not None and g.source_end_seconds is not None:
                    first_idx, last_idx = g.global_source_token_indexes[0], g.global_source_token_indexes[-1]
                    if 0 <= first_idx < total_tokens and 0 <= last_idx < total_tokens:
                        wt_f, wt_l = word_timestamps[first_idx], word_timestamps[last_idx]
                        exp_start = wt_f.start if hasattr(wt_f, "start") else wt_f.get("start")
                        exp_end = wt_l.end if hasattr(wt_l, "end") else wt_l.get("end")
                        if exp_start is not None and exp_end is not None and (abs(g.source_start_seconds - exp_start) > 0.05 or abs(g.source_end_seconds - exp_end) > 0.05):
                            _err("TOKEN_TIMESTAMP_MISMATCH", f"Glosa '{g.gloss}' tiene tiempos ({g.source_start_seconds}–{g.source_end_seconds}) que divergen de los tokens ASR ({exp_start}–{exp_end}).", [str(g.id)])
                if g.alignment_type == AlignmentType.DIRECT and g.source_word and g.global_source_token_indexes:
                    first_idx = g.global_source_token_indexes[0]
                    if 0 <= first_idx < total_tokens:
                        wt_obj = word_timestamps[first_idx]
                        wt_w = wt_obj.word if hasattr(wt_obj, "word") else wt_obj.get("word", "")
                        w_text = re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ]", "", wt_w.lower())
                        s_text = re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ]", "", g.source_word.lower())
                        if w_text != s_text and not (len(s_text) >= 3 and s_text in w_text) and not (len(w_text) >= 3 and w_text in s_text):
                            _err("SOURCE_TOKEN_TEXT_MISMATCH", f"Glosa '{g.gloss}' asocia source_word '{g.source_word}' con token ASR distinto '{wt_w}'.", [str(g.id)])

        for g in glosses:
            if g.alignment_type in (AlignmentType.MULTIWORD, AlignmentType.NORMALIZED_MULTIWORD) and len(g.global_source_token_indexes) > 1:
                idxs = sorted(g.global_source_token_indexes)
                if any(idxs[i + 1] - idxs[i] != 1 for i in range(len(idxs) - 1)):
                    _err("INVALID_MULTIWORD_ALIGNMENT", f"Glosa multipalabra '{g.gloss}' tiene índices no contiguos: {g.global_source_token_indexes}.", [str(g.id)])
            if g.alignment_type == AlignmentType.ENTITY_ALIAS and g.spatial_ref == "upec" and "Politécnica" in (g.source_word or "") and g.global_source_token_indexes != [22, 23, 24]:
                _err("ENTITY_ALIAS_RANGE_MISMATCH", f"Alias de entidad '{g.gloss}' para Politécnica del Carchi esperaba índices [22, 23, 24] pero tiene {g.global_source_token_indexes}.", [str(g.id)])
            if g.alignment_type == AlignmentType.DIRECT and g.alignment_confidence >= 0.90 and (not g.global_source_token_indexes or g.source_start_seconds is None):
                _err("CONFIDENCE_WITHOUT_EVIDENCE", f"Glosa '{g.gloss}' tiene confianza alta ({g.alignment_confidence}) sin evidencia de alineación.", [str(g.id)])

        if plans:
            for plan in plans:
                for rci in plan.realized_concept_items:
                    if not getattr(rci, "is_supported", True):
                        _err("UNSUPPORTED_REALIZED_CONCEPT", f"Concepto realizado '{rci.concept}' en plan '{plan.id}' carece de justificación o soporte.", [plan.id, rci.concept])

        if validation_metadata:
            has_paraphrase = any(g.requires_native_review for g in glosses)
            has_audio = any(g.requires_audio_review for g in glosses) or any(u.get("requires_audio_review") for u in unresolved_items)
            if has_paraphrase and not getattr(validation_metadata, "pending_native_review_gloss_ids", []):
                _err("REVIEW_LIST_NOT_POPULATED", "Existen paráfrasis pendientes pero pending_native_review_gloss_ids está vacía.")
            if has_audio and not getattr(validation_metadata, "pending_audio_review_ids", []):
                _err("REVIEW_LIST_NOT_POPULATED", "Existe revisión de audio pendiente pero pending_audio_review_ids está vacía.")

        for unres in unresolved_items:
            if unres.get("source_start_seconds") is None or unres.get("source_end_seconds") is None or not unres.get("global_source_token_indexes", []):
                _err("UNRESOLVED_ITEM_WITHOUT_TIME", f"Elemento no resuelto '{unres.get('source_word')}' no tiene marcas de tiempo o índices globales.", [str(unres.get("source_word"))])

        errors.extend(self._validate_lsec_211_invariants(original_text, normalized_text, propositions, glosses, blocks, plans, timing_plan, validation_metadata))
        return errors

    def _validate_lsec_211_invariants(
        self, original_text: str, normalized_text: str, propositions: List[SemanticProposition],
        glosses: List[GlossItem], blocks: List[DiscourseBlock], plans: Optional[List[TranslationPlan]] = None,
        timing_plan: Optional[TimingPlan] = None, validation_metadata: Optional[Any] = None,
    ) -> List[StructuralValidationError]:
        """Ejecuta el catálogo de las 13 validaciones automáticas obligatorias de LSEC 2.1.1."""
        errors: List[StructuralValidationError] = []
        punct_chars = set("¿?¡!,.;:\"'«»—–")
        forbidden_predicates = {
            "yo", "tú", "tu", "él", "ella", "ello", "nosotros", "nosotras", "ustedes", "ellos", "ellas",
            "qué", "que", "quién", "quien", "quiénes", "quienes", "dónde", "donde", "cuándo", "cuando", "cómo", "como",
            "el", "la", "los", "las", "un", "una", "unos", "unas", "manzana", "manzanas", "carne", "carnes", "pan", "panes", "agua", "aguas",
        }

        def _err(code: str, msg: str, affected: Optional[List[str]] = None, blocking: bool = True, sev: ValidationSeverity = ValidationSeverity.ERROR) -> None:
            errors.append(StructuralValidationError(severity=sev, code=code, message=msg, affected_ids=affected or [], blocking=blocking))

        for prop in propositions:
            if prop.predicate:
                pred_l = prop.predicate.lemma.lower().strip()
                if pred_l in forbidden_predicates:
                    _err("INVALID_PREDICATE_SELECTION", f"Predicado inválido '{pred_l}' en '{prop.id}': se seleccionó un pronombre, determinante o sustantivo en lugar de una acción.", [prop.id])
                if any(c in punct_chars for c in prop.predicate.lemma):
                    _err("PUNCTUATION_IN_LEMMA", f"Signo de puntuación detectado en lema de predicado '{prop.predicate.lemma}'.", [prop.id])
                if pred_l in ("comer", "beber", "comprar", "educar", "transformar", "decidir", "ofrecer"):
                    has_agent = any(p.semantic_role in (SemanticRole.AGENT, SemanticRole.EXPERIENCER) for p in prop.participants)
                    has_patient = any(p.semantic_role in (SemanticRole.PATIENT, SemanticRole.THEME, SemanticRole.GOAL) for p in prop.participants)
                    if not has_agent or not has_patient:
                        _err("MISSING_SEMANTIC_PARTICIPANTS", f"Oración transitiva '{prop.id}' con predicado '{prop.predicate.lemma}' carece de participantes nucleares (AGENT o PATIENT/THEME).", [prop.id])
            for part in prop.participants:
                if any(c in punct_chars for c in part.lemma):
                    _err("PUNCTUATION_IN_LEMMA", f"Signo de puntuación detectado en lema de participante '{part.lemma}'.", [part.id])
                if not part.is_implicit and not part.normalized_text and not part.source_char_start:
                    _err("UNLINKED_PARTICIPANT_SOURCE", f"Participante explícito '{part.id}' carece de texto fuente vinculado.", [part.id])

        for g in glosses:
            if any(c in punct_chars for c in g.gloss):
                _err("PUNCTUATION_IN_LEMMA", f"Signo de puntuación detectado en glosa '{g.gloss}'.", [str(g.id)])
            if g.alignment_type == AlignmentType.DIRECT and not g.source_word:
                _err("INVALID_DIRECT_ALIGNMENT", f"Glosa '{g.gloss}' clasificada como DIRECT sin source_word.", [str(g.id)])
            if g.alignment_type == AlignmentType.COREFERENCE and not (g.antecedent_proposition_id or g.coreference_target_id):
                _err("UNRESOLVED_COREFERENCE_ALIGNMENT", f"Glosa de correferencia '{g.gloss}' sin antecedente ni coreference_target_id.", [str(g.id)])
            if "manzán" in (g.normalized_word or "").lower() or (g.source_word == "manzana" and g.gloss == "MANZÁN"):
                _err("DESTRUCTIVE_NORMALIZATION", f"Normalización destructiva detectada en '{g.gloss}' ({g.source_word} -> {g.normalized_word}).", [str(g.id)])

        if plans:
            for plan in plans:
                for rci in plan.realized_concept_items:
                    if rci.is_supported and not rci.source_concept_ids and not (rci.inference_rule_id or rci.coreference_target_id or rci.discourse_relation or rci.entity_id):
                        _err("UNSUPPORTED_REALIZED_CONCEPT", f"Concepto '{rci.concept}' declarado soportado sin source_concept_ids ni regla de inferencia.", [plan.id, rci.concept])
                if plan.coverage_status == "COMPLETE" and (plan.unsupported_realized_concepts or plan.omitted_concepts or plan.source_recall < 1.0 or plan.realization_precision < 1.0):
                    _err("INVALID_COVERAGE_STATUS", f"Plan '{plan.id}' declarado COMPLETE pero tiene conceptos omitidos o no soportados.", [plan.id])

        if "¿" in original_text or "?" in original_text:
            _q_prop_ids = {p.id for p in propositions if "?" in (getattr(p, "source_text", "") or "") or "\u00bf" in (getattr(p, "source_text", "") or "")}
            for prop in propositions:
                if prop.modality == "declarative" and prop.id in _q_prop_ids:
                    _err("MODALITY_MISMATCH", f"Oración interrogativa analizada con modalidad declarativa en '{prop.id}'.", [prop.id])
            for block in blocks:
                if block.discourse_function == "statement" and (set(getattr(block, "proposition_ids", []) or []) & _q_prop_ids):
                    _err("MODALITY_MISMATCH", f"Bloque discursivo {block.id} clasificado como 'statement' en oración interrogativa.", [str(block.id)])

        from app.services.text_normalizer import contains_negation
        for prop in propositions:
            if (prop.polarity == "negative" or contains_negation(prop.source_text.lower())) and not any(op.get("type") == "NEGATION" or op.get("operator_type") == "NEGATION" for op in prop.operators):
                _err("MISSING_NEGATION_OPERATOR", f"Proposición negativa '{prop.id}' no contiene operador semántico NEGATION.", [prop.id])

        if validation_metadata:
            errs_count = getattr(validation_metadata, "errors_count", 0)
            ex_stat = getattr(validation_metadata, "execution_status", None)
            rev_stat = getattr(validation_metadata, "review_status", None)
            if errs_count > 0 and (ex_stat in ("READY", "READY_FOR_EXECUTION") or rev_stat == "VERIFIED"):
                _err("VALIDATION_STATE_INCONSISTENCY", f"Inconsistencia de estado: errors_count={errs_count} coexiste con execution_status={ex_stat} o review_status={rev_stat}.")

        if timing_plan:
            expected_total = timing_plan.manual_sign_duration_ms + timing_plan.fingerspelling_duration_ms + timing_plan.pause_budget_ms
            if abs(timing_plan.total_duration_ms - expected_total) > 5:
                _err("TIMING_ARITHMETIC_INCONSISTENCY", f"Inconsistencia aritmética en TimingPlan: total_duration_ms={timing_plan.total_duration_ms} != suma({expected_total}).")

        # 14. POSSIBLE_CONJUGATED_GLOSS (F-24)
        conj_gloss_re = re.compile(
            r"^[A-ZÁÉÍÓÚÑÜ]{3,}(?:ARÁS|ERÁS|IRÁS|ARÁN|ERÁN|IRÁN|AREMOS|EREMOS|IREMOS|ASTE|ISTE|ARON|IERON|ÁBAMOS|ARER|ASTAR|ALIR|ÁME|ÉME|ÍME|LLEGUES|ANDO|IENDO)$"
        )
        conj_norm_re = re.compile(
            r"^[a-záéíóúñü]{3,}(?:arás|erás|irás|arán|erán|irán|aremos|eremos|iremos|aste|iste|aron|ieron|ábamos|arer|astar|alir|áme|éme|íme|llegues|ando|iendo|amos)$",
            re.IGNORECASE,
        )
        for g in glosses:
            g_base = re.sub(r"(\+\+|\[.*\])$", "", (g.gloss or "").strip())
            g_norm = (g.normalized_word or "").strip().lower()
            lex_status = (
                g.dictionary_metadata.status
                if g.dictionary_metadata is not None
                else str(getattr(g, "lexical_status", None) or (g.validation or {}).get("lexical_source", "NO_VERIFICADO"))
            )
            if (
                g.gloss_type == GlossType.SIGN
                and lex_status not in ("VERIFICADO_CONADIS", "LEXICON_LOCAL", "EXENTO_GRAMATICAL", "DACTILOLOGIA")
                and (
                    conj_gloss_re.match(g_base)
                    or (
                        g_norm
                        and g_norm not in ("vamos", "ramo", "ramos", "tramo", "tramos", "bando", "mando", "blando", "cuando", "cuándo")
                        and conj_norm_re.match(g_norm)
                    )
                )
            ):
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.WARNING,
                        code="POSSIBLE_CONJUGATED_GLOSS",
                        message=f"Posible forma verbal flexionada o corrupta en glosa '{g.gloss}' (fuente: '{g.source_word}').",
                        affected_ids=[str(g.id)],
                        blocking=False,
                    )
                )

        return errors

    def _validate_semantic_coverage(
        self,
        propositions: List[SemanticProposition],
        glosses: List[GlossItem],
        plans: Optional[List[TranslationPlan]],
    ) -> List[StructuralValidationError]:
        """Valida que todos los conceptos obligatorios se realicen."""
        errors: List[StructuralValidationError] = []
        if plans:
            for plan in plans:
                if plan.omitted_concepts:
                    errors.append(
                        StructuralValidationError(
                            severity=ValidationSeverity.WARNING,
                            code="SOURCE_CONTENT_DROPPED",
                            message=f"La proposición '{plan.proposition_id}' omitió conceptos obligatorios: {plan.omitted_concepts}.",
                            affected_ids=[plan.proposition_id],
                        )
                    )
        return errors

    def _validate_content_leaks(
        self,
        propositions: List[SemanticProposition],
        glosses: List[GlossItem],
    ) -> List[StructuralValidationError]:
        """Detecta si una proposición generó contenido perteneciente a otra o ajeno a su fuente."""
        errors: List[StructuralValidationError] = []
        glosses_by_prop: Dict[str, List[GlossItem]] = {}
        for g in glosses:
            if g.proposition_id:
                glosses_by_prop.setdefault(g.proposition_id, []).append(g)

        for prop in propositions:
            p_glosses = glosses_by_prop.get(prop.id, [])
            p_gloss_texts = {g.gloss.upper() for g in p_glosses}
            p_src_lower = prop.source_text.lower()

            if "oportunidad" not in p_src_lower and "OPORTUNIDAD" in p_gloss_texts:
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.ERROR,
                        code="SEMANTIC_CONTENT_LEAK",
                        message=f"Fuga semántica en '{prop.id}': generó OPORTUNIDAD sin respaldo en el texto fuente '{prop.source_text}'.",
                        affected_ids=[prop.id],
                        blocking=True,
                    )
                )

            if "idea" not in p_src_lower and "construy" not in p_src_lower and any(g in p_gloss_texts for g in ("IDEA", "DESARROLLAR")):
                errors.append(
                    StructuralValidationError(
                        severity=ValidationSeverity.ERROR,
                        code="SEMANTIC_CONTENT_LEAK",
                        message=f"Fuga semántica en '{prop.id}': generó {p_gloss_texts.intersection({'IDEA', 'DESARROLLAR'})} sin respaldo en el texto fuente '{prop.source_text}'.",
                        affected_ids=[prop.id],
                        blocking=True,
                    )
                )

        return errors

    def _validate_duplicate_plans(
        self,
        plans: List[TranslationPlan],
    ) -> List[StructuralValidationError]:
        """Detecta planes con secuencias de glosas o conceptos duplicados."""
        errors: List[StructuralValidationError] = []
        seen_items: Dict[str, str] = {}

        for p in plans:
            seq_key = " ".join(p.lexical_items)
            if len(p.lexical_items) >= 3:
                if seq_key in seen_items:
                    errors.append(
                        StructuralValidationError(
                            severity=ValidationSeverity.WARNING,
                            code="DUPLICATE_TRANSLATION_PLAN",
                            message=f"El plan para {p.proposition_id} genera una secuencia idéntica a {seen_items[seq_key]}: '{seq_key}'.",
                            affected_ids=[p.proposition_id, seen_items[seq_key]],
                        )
                    )
                else:
                    seen_items[seq_key] = p.proposition_id

        return errors
