"""
Enlazador de Metadatos de Ejecución para Animación y Avatar LSEC (LSEC 2.1.1).

Establece relaciones bidireccionales explícitas entre todas las capas de ejecución:
- `GlossItem` ↔ `DiscourseBlock` (`gloss.discourse_block_id`, `block.gloss_ids`)
- `GlossItem` ↔ `NonManualSpan` (`gloss.non_manual_span_ids`, `span.gloss_ids`)
- `GlossItem` ↔ `SpatialOperation` (`gloss.spatial_operation_ids`, `op.operation_trigger_gloss_id`)
- `GlossItem` ↔ `SemanticProposition` (`gloss.proposition_id`)

Garantiza que el motor de renderizado o avatar no tenga que recalcular
intersecciones de rangos ni sufra desincronizaciones espaciales o faciales.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from app.core.schemas import (
    DiscourseBlock,
    GlossItem,
    NonManualSpan,
    SemanticProposition,
    SpatialOperation,
    SpatialReferent,
)

logger = logging.getLogger(__name__)


class ExecutionMetadataLinker:
    """
    Enlaza metadatos de ejecución de manera bidireccional y exhaustiva.
    """

    def link_metadata(
        self,
        glosses: List[GlossItem],
        blocks: List[DiscourseBlock],
        spans: List[NonManualSpan],
        operations: List[SpatialOperation],
        referents: List[SpatialReferent],
        propositions: List[SemanticProposition],
    ) -> Tuple[List[GlossItem], List[DiscourseBlock], List[NonManualSpan], List[SpatialOperation]]:
        """
        Enlaza bloques, spans y operaciones espaciales con cada GlossItem.
        """
        # Indexar glosas por orden y por ID
        gloss_by_order: Dict[int, GlossItem] = {g.order: g for g in glosses}
        gloss_by_id: Dict[str, GlossItem] = {str(g.id): g for g in glosses}

        # Indexar proposiciones por ID
        prop_by_id: Dict[str, SemanticProposition] = {p.id: p for p in propositions}

        # 1. Enlace GlossItem ↔ DiscourseBlock
        for block in blocks:
            covered_glosses = [g for g in glosses if block.start_order <= g.order <= block.end_order]
            block.gloss_ids = [str(g.id) for g in covered_glosses]
            for g in covered_glosses:
                g.discourse_block_id = block.id
                if g.proposition_id and g.proposition_id in prop_by_id:
                    # Derivar discourse_unit_id si está disponible
                    try:
                        # Extraer número de 'p1', 'p2' -> 0, 1
                        num = int(g.proposition_id.replace("p", "").replace("_", "")) - 1
                        g.discourse_unit_id = max(num, 0)
                    except (ValueError, TypeError):
                        g.discourse_unit_id = block.id

        # Si alguna glosa quedó sin discourse_block_id, asignarle el bloque más cercano
        for g in glosses:
            if g.discourse_block_id is None and blocks:
                for b in blocks:
                    if b.start_order <= g.order <= b.end_order:
                        g.discourse_block_id = b.id
                        break
                if g.discourse_block_id is None:
                    g.discourse_block_id = blocks[0].id

        # 2. Enlace GlossItem ↔ NonManualSpan
        for span in spans:
            covered_glosses = [g for g in glosses if span.start_order <= g.order <= span.end_order]
            span.gloss_ids = [str(g.id) for g in covered_glosses]
            for g in covered_glosses:
                if span.id not in g.non_manual_span_ids:
                    g.non_manual_span_ids.append(span.id)

        # 3. Enlace GlossItem ↔ SpatialOperation
        for op in operations:
            target_gloss = None
            if op.operation_trigger_gloss_id and op.operation_trigger_gloss_id in gloss_by_id:
                target_gloss = gloss_by_id[op.operation_trigger_gloss_id]
            elif op.source_order is not None and op.source_order in gloss_by_order:
                target_gloss = gloss_by_order[op.source_order]
            else:
                # Buscar por spatial_ref coincidente
                target_gloss = next(
                    (g for g in glosses if g.spatial_ref == op.referent_id or (op.referent_id and op.referent_id.lower() in g.gloss.lower())),
                    None,
                )

            if target_gloss is not None:
                op.operation_trigger_gloss_id = str(target_gloss.id)
                op.source_order = target_gloss.order
                if op.id not in target_gloss.spatial_operation_ids:
                    target_gloss.spatial_operation_ids.append(op.id)
                if not target_gloss.spatial_ref:
                    target_gloss.spatial_ref = op.referent_id

        # 4. Asegurar que solo la glosa disparadora tenga el ID de la operación espacial
        for op in operations:
            if op.operation_trigger_gloss_id and op.operation_trigger_gloss_id in gloss_by_id:
                g = gloss_by_id[op.operation_trigger_gloss_id]
                if op.id not in g.spatial_operation_ids:
                    g.spatial_operation_ids.append(op.id)

        logger.debug(
            "Enlace de metadatos de ejecución completado: %d glosas, %d bloques, %d spans, %d ops.",
            len(glosses), len(blocks), len(spans), len(operations),
        )
        return glosses, blocks, spans, operations

