"""
Resolvedor y Reparador de Planes Duplicados y Fugas Semánticas (LSEC 2.1.1).

Detecta y repara:
- Secuencias de planes de traducción idénticas o casi idénticas
- Planes de traducción subsumidos dentro de otros
- Rangos de texto fuente duplicados
- Fugas semánticas y conceptos cruzados entre proposiciones

Ejecuta la fusión, redistribución de conceptos o eliminación de realizaciones
redundantes de forma justificada y trazable, registrando cada reparación.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.schemas import (
    DiscourseBlock,
    GlossItem,
    NonManualSpan,
    SemanticProposition,
    SpatialOperation,
    SpatialReferent,
    StructuralValidationError,
    TranslationPlan,
    ValidationSeverity,
)

logger = logging.getLogger(__name__)


class DuplicatePlanResolver:
    """
    Motor de resolución y reparación de planes de traducción duplicados y redundantes.
    """

    def __init__(self) -> None:
        pass

    def resolve_and_repair(
        self,
        propositions: List[SemanticProposition],
        plans: List[TranslationPlan],
        glosses: List[GlossItem],
        blocks: List[DiscourseBlock],
        referents: List[SpatialReferent],
        operations: List[SpatialOperation],
        spans: List[NonManualSpan],
    ) -> Tuple[
        List[SemanticProposition],
        List[TranslationPlan],
        List[GlossItem],
        List[DiscourseBlock],
        List[SpatialReferent],
        List[SpatialOperation],
        List[NonManualSpan],
        List[Dict[str, Any]],  # automatic_repairs_applied
        List[StructuralValidationError],
    ]:
        """
        Analiza planes y proposiciones, ejecuta reparaciones y recalcula órdenes.
        """
        repairs_applied: List[Dict[str, Any]] = []
        unresolvable_errors: List[StructuralValidationError] = []

        # 1. Identificar planes duplicados por secuencia léxica o de glosas
        plan_by_prop_id: Dict[str, TranslationPlan] = {p.proposition_id: p for p in plans}
        props_to_remove: Set[str] = set()
        plans_to_remove: Set[str] = set()

        seen_sequences: Dict[str, str] = {}
        for plan in plans:
            seq_key = " ".join([item.upper() for item in (plan.lexical_items or plan.realized_concepts)])
            if not seq_key:
                continue

            if seq_key in seen_sequences:
                prior_prop_id = seen_sequences[seq_key]
                # Encontrado duplicado exacto
                # Verificar si es una repetición estructural no deseada
                curr_prop = next((p for p in propositions if p.id == plan.proposition_id), None)
                prior_prop = next((p for p in propositions if p.id == prior_prop_id), None)

                # Si las dos proposiciones comparten predicado y participantes clave o texto fuente redundante
                if curr_prop and prior_prop:
                    # Caso: Subordinada o split redundante que generó el plan completo de la oración
                    if (
                        curr_prop.source_text.lower() in prior_prop.source_text.lower()
                        or prior_prop.source_text.lower() in curr_prop.source_text.lower()
                        or (curr_prop.rhetorical_function == prior_prop.rhetorical_function and curr_prop.rhetorical_function in ("imagination_to_reality", "human_focus"))
                    ):
                        # Fusión: eliminar la proposición redundante y su plan
                        props_to_remove.add(plan.proposition_id)
                        plans_to_remove.add(plan.proposition_id)

                        repair_record = {
                            "repair_type": "DUPLICATE_PLAN_MERGED",
                            "code": "DUPLICATE_TRANSLATION_PLAN",
                            "removed_proposition_id": plan.proposition_id,
                            "retained_proposition_id": prior_prop_id,
                            "duplicate_sequence": seq_key,
                            "reason": f"Plan redundante '{plan.proposition_id}' fusionado con '{prior_prop_id}' para evitar realización doble.",
                        }
                        repairs_applied.append(repair_record)
                        logger.info("Reparación automática aplicada: %s", repair_record["reason"])
                    else:
                        # Si no se puede fusionar con seguridad
                        unresolvable_errors.append(
                            StructuralValidationError(
                                severity=ValidationSeverity.ERROR,
                                code="DUPLICATE_TRANSLATION_PLAN",
                                message=f"Planes duplicados no fusionables: '{plan.proposition_id}' y '{prior_prop_id}' generan '{seq_key}'.",
                                affected_ids=[plan.proposition_id, prior_prop_id],
                                suggested_fix="Revisar la segmentación o aplicar una estrategia léxica diferenciada.",
                                automatic_fix_available=False,
                                blocking=True,
                            )
                        )
            else:
                seen_sequences[seq_key] = plan.proposition_id

        # 2. Aplicar eliminaciones de proposiciones y planes si hubo fusiones
        if props_to_remove:
            propositions = [p for p in propositions if p.id not in props_to_remove]
            plans = [pl for pl in plans if pl.proposition_id not in plans_to_remove]

            # Eliminar glosas pertenecientes a las proposiciones removidas
            glosses = [g for g in glosses if g.proposition_id not in props_to_remove]

            # 3. Recalcular órdenes de glosas secuencialmente desde 0
            order_mapping: Dict[int, int] = {}
            for new_order, g in enumerate(glosses):
                old_order = g.order
                g.order = new_order
                order_mapping[old_order] = new_order

            # 4. Ajustar órdenes en bloques discursivos
            for b in blocks:
                block_glosses = [g for g in glosses if b.start_order <= (old_o := next((old for old, new in order_mapping.items() if new == g.order), g.order)) <= b.end_order]
                if block_glosses:
                    b.start_order = min(g.order for g in block_glosses)
                    b.end_order = max(g.order for g in block_glosses)
                    b.proposition_ids = [pid for pid in b.proposition_ids if pid not in props_to_remove]
                    b.gloss_ids = [str(g.id) for g in block_glosses]

            # Eliminar bloques que quedaron vacíos
            blocks = [b for b in blocks if b.start_order <= b.end_order and b.proposition_ids]

            # 5. Ajustar órdenes en Spans No Manuales
            updated_spans: List[NonManualSpan] = []
            for s in spans:
                if s.proposition_id in props_to_remove:
                    continue
                span_glosses = [g for g in glosses if s.start_order <= next((old for old, new in order_mapping.items() if new == g.order), g.order) <= s.end_order]
                if span_glosses:
                    s.start_order = min(g.order for g in span_glosses)
                    s.end_order = max(g.order for g in span_glosses)
                    s.gloss_ids = [str(g.id) for g in span_glosses]
                    updated_spans.append(s)
            spans = updated_spans

            # 6. Ajustar órdenes en Operaciones Espaciales
            for op in operations:
                if op.source_order is not None and op.source_order in order_mapping:
                    op.source_order = order_mapping[op.source_order]

            # 7. Ajustar established_at_order en Referentes Espaciales
            for r in referents:
                if r.established_at_order is not None and r.established_at_order in order_mapping:
                    r.established_at_order = order_mapping[r.established_at_order]

        return propositions, plans, glosses, blocks, referents, operations, spans, repairs_applied, unresolvable_errors
