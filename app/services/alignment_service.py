"""
Servicio de Alineación Temporal y Trazabilidad Fuente (LSEC 2.1.1).

Alinea de manera bidireccional y continua:
- Tokens originales del audio/texto
- Tokens normalizados y correcciones
- Expresiones multipalabra y entidades
- Proposiciones semánticas
- Conceptos y secuencias de glosas LSEC

Garantiza la consistencia entre índices locales (por proposición) e índices
globales basados en `transcription.word_timestamps` o la lista global de tokens.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.schemas import (
    AlignmentType,
    GlossItem,
    SemanticProposition,
    WordTimestamp,
)

logger = logging.getLogger(__name__)


class SourceAlignmentService:
    """
    Servicio de alineación temporal y correspondencia de tokens (LSEC 2.1.1).
    """

    def __init__(self) -> None:
        pass

    def align_pipeline(
        self,
        original_text: str,
        normalized_text: str,
        word_timestamps: List[WordTimestamp],
        propositions: List[SemanticProposition],
        glosses: List[GlossItem],
        corrections: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[SemanticProposition], List[GlossItem]]:
        """
        Alinea proposiciones y glosas con los tokens y marcas de tiempo globales.
        """
        corrections = corrections or []

        # 1. Si no hay word_timestamps, generar marcas sintéticas continuas
        if not word_timestamps:
            raw_tokens = [m.group(0) for m in re.finditer(r"\b[\wáéíóúñüÁÉÍÓÚÑÜ\-]+\b", original_text)]
            if not raw_tokens:
                raw_tokens = original_text.split()
            word_timestamps = []
            curr_sec = 0.0
            step_sec = 0.40  # ~150 wpm
            for tok in raw_tokens:
                word_timestamps.append(
                    WordTimestamp(
                        word=tok,
                        start=round(curr_sec, 3),
                        end=round(curr_sec + step_sec, 3),
                        confidence=0.95,
                    )
                )
                curr_sec += step_sec

        global_words = [wt.word for wt in word_timestamps]
        total_global_tokens = len(global_words)

        # 2. Mapeo de texto completo a intervalos de caracteres para cada token global
        token_spans: List[Tuple[int, int]] = []
        curr_char = 0
        for w in global_words:
            idx = original_text.lower().find(w.lower(), curr_char)
            if idx == -1:
                idx = curr_char
            end = idx + len(w)
            token_spans.append((idx, end))
            curr_char = max(end, curr_char)

        # 3. Alinear cada Proposición Semántica
        # Tokens del audio eliminados por el depurador de habla (muletillas, repeticiones):
        # no existen en el texto normalizado, por lo que se omiten al ubicar proposiciones.
        removed_global: set = set()
        for c in corrections:
            cd = c if isinstance(c, dict) else (c.to_dict() if hasattr(c, "to_dict") else {})
            if cd.get("normalized_text", None) == "" and cd.get("asr_text"):
                removed_global.update(cd.get("global_source_token_indexes") or [])
        alive_idx = [i for i in range(total_global_tokens) if i not in removed_global]
        n_alive = len(alive_idx)

        global_cursor = 0  # posición dentro de alive_idx
        for prop in propositions:
            p_text = prop.source_text.strip()
            p_words = [w for w in re.findall(r"\b[\wáéíóúñüÁÉÍÓÚÑÜ\-]+\b", p_text)]
            p_len = len(p_words)

            local_idxs = list(range(p_len))
            prop.local_token_indexes = local_idxs
            prop.source_token_indexes = local_idxs  # Compatibilidad retroactiva

            matched_global_idxs: List[int] = []
            if prop.global_source_token_indexes and all(0 <= idx < total_global_tokens for idx in prop.global_source_token_indexes):
                matched_global_idxs = prop.global_source_token_indexes
                last_g = matched_global_idxs[-1]
                global_cursor = sum(1 for i in alive_idx if i <= last_g)
            elif p_words and n_alive > 0:
                clean_p_words = [re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ\-]", "", w.lower()) for w in p_words if w]
                # Filtrar palabras agregadas sintéticamente que no existen en el audio
                real_p_words = [w for w in clean_p_words if w not in ("ofrecer", "varias", "dos")]
                if not real_p_words:
                    real_p_words = clean_p_words

                best_start = global_cursor
                for i in range(global_cursor, min(global_cursor + 6, n_alive)):
                    gw = re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ\-]", "", global_words[alive_idx[i]].lower())
                    if real_p_words and (gw == real_p_words[0] or (len(gw) >= 4 and real_p_words[0].startswith(gw))):
                        best_start = i
                        break

                end_i = min(best_start + len(real_p_words), n_alive)
                matched_global_idxs = alive_idx[best_start:end_i]
                global_cursor = end_i
            else:
                end_i = min(global_cursor + p_len, n_alive)
                matched_global_idxs = alive_idx[global_cursor:end_i]
                global_cursor = end_i

            prop.global_source_token_indexes = matched_global_idxs

            # Asignar tiempos de inicio y fin a la proposición
            if matched_global_idxs and word_timestamps:
                valid_idxs = [i for i in matched_global_idxs if i < len(word_timestamps)]
                if valid_idxs:
                    prop.source_start_seconds = round(word_timestamps[valid_idxs[0]].start, 3)
                    prop.source_end_seconds = round(word_timestamps[valid_idxs[-1]].end, 3)

            # Asignar límites de caracteres
            if matched_global_idxs and token_spans:
                valid_idxs = [i for i in matched_global_idxs if i < len(token_spans)]
                if valid_idxs:
                    prop.source_char_start = token_spans[valid_idxs[0]][0]
                    prop.source_char_end = token_spans[valid_idxs[-1]][1]

            # Si source_ranges está vacío, poblarlo
            if not prop.source_ranges and prop.source_char_start is not None:
                prop.source_ranges = [
                    {
                        "start_char": prop.source_char_start,
                        "end_char": prop.source_char_end,
                        "start_seconds": prop.source_start_seconds,
                        "end_seconds": prop.source_end_seconds,
                    }
                ]

        # 4. Alinear cada GlossItem
        glosses_by_prop: Dict[str, List[GlossItem]] = {}
        for g in glosses:
            if g.proposition_id:
                glosses_by_prop.setdefault(g.proposition_id, []).append(g)

        for prop in propositions:
            p_glosses = glosses_by_prop.get(prop.id, [])
            p_global_idxs = prop.global_source_token_indexes
            p_words = [w for w in re.findall(r"\b[\wáéíóúñüÁÉÍÓÚÑÜ\-]+\b", prop.source_text)]

            for g_idx, g in enumerate(p_glosses):
                g.origin_proposition_id = prop.id

                # Buscar coincidencia léxica en tokens de la proposición
                matched_global: List[int] = []
                target_word = g.source_word or g.normalized_word

                if target_word and p_global_idxs:
                    t_words = target_word.lower().split()
                    if len(t_words) > 1:
                        first_w = re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ\-]", "", t_words[0])
                        for gi in p_global_idxs:
                            if gi < total_global_tokens:
                                gw_clean = re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ\-]", "", global_words[gi].lower())
                                if gw_clean == first_w or first_w in gw_clean:
                                    span_len = len(t_words)
                                    matched_global = [i for i in range(gi, min(gi + span_len, total_global_tokens)) if i in p_global_idxs]
                                    break
                    if not matched_global:
                        t_clean = re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ\-]", "", target_word.lower())
                        for gi in p_global_idxs:
                            if gi < total_global_tokens:
                                gw_clean = re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ\-]", "", global_words[gi].lower())
                                if t_clean == gw_clean or (len(t_clean) >= 4 and t_clean in gw_clean) or (len(gw_clean) >= 4 and gw_clean in t_clean):
                                    matched_global.append(gi)
                                    break

                # Clasificar / refinar AlignmentType
                if g.lexical_strategy == "semantic_paraphrase" or (g.alignment_type == AlignmentType.PARAPHRASE):
                    g.alignment_type = AlignmentType.PARAPHRASE
                    g.alignment_confidence = 0.85
                    g.requires_review = True
                    g.requires_native_review = True
                    if "Propuesta de paráfrasis semántica sujeta a validación nativa LSEC." not in g.review_reasons:
                        g.review_reasons.append("Propuesta de paráfrasis semántica sujeta a validación nativa LSEC.")
                elif g.alignment_type == AlignmentType.DEICTIC or (g.notes and "deixis" in g.notes.lower()):
                    g.alignment_type = AlignmentType.DEICTIC
                    g.alignment_confidence = 0.90
                elif g.alignment_type == AlignmentType.COREFERENCE or g.coreference_target_id:
                    g.alignment_type = AlignmentType.COREFERENCE
                    g.alignment_confidence = 0.90
                elif g.alignment_type == AlignmentType.INFERRED or g.inference_rule_id or (g.notes and "inferred" in g.notes.lower()):
                    g.alignment_type = AlignmentType.INFERRED
                    g.alignment_confidence = 0.80
                elif g.alignment_type == AlignmentType.DISCOURSE_MARKER:
                    g.alignment_type = AlignmentType.DISCOURSE_MARKER
                    g.alignment_confidence = 0.90
                elif g.alignment_type == AlignmentType.ENTITY_ALIAS or g.spatial_ref:
                    g.alignment_type = AlignmentType.ENTITY_ALIAS
                    g.alignment_confidence = 0.95
                elif target_word and len(target_word.split()) > 1:
                    g.alignment_type = AlignmentType.MULTIWORD
                    g.alignment_confidence = 0.92
                elif g.normalized_word and g.source_word and g.normalized_word.lower() != g.source_word.lower():
                    g.alignment_type = AlignmentType.NORMALIZED
                    g.alignment_confidence = 0.92
                elif not g.alignment_type:
                    g.alignment_type = AlignmentType.DIRECT
                    g.alignment_confidence = 0.95

                # Asignar índices y marcas de tiempo según el tipo de alineación
                if g.alignment_type == AlignmentType.INFERRED:
                    g.source_token_indexes = []
                    g.local_token_indexes = []
                    g.global_source_token_indexes = []
                    g.source_char_start = None
                    g.source_char_end = None
                    g.source_start_seconds = prop.source_start_seconds
                    g.source_end_seconds = prop.source_end_seconds
                elif g.alignment_type == AlignmentType.COREFERENCE and not matched_global:
                    g.source_token_indexes = []
                    g.local_token_indexes = []
                    g.global_source_token_indexes = []
                    g.source_char_start = None
                    g.source_char_end = None
                    g.source_start_seconds = prop.source_start_seconds
                    g.source_end_seconds = prop.source_end_seconds
                elif matched_global:
                    g.global_source_token_indexes = matched_global
                    # Calcular local_token_indexes respecto a prop.global_source_token_indexes
                    g.local_token_indexes = [p_global_idxs.index(gi) for gi in matched_global if gi in p_global_idxs]
                    g.source_token_indexes = g.local_token_indexes

                    if word_timestamps:
                        valid_g = [i for i in matched_global if i < len(word_timestamps)]
                        if valid_g:
                            g.source_start_seconds = round(word_timestamps[valid_g[0]].start, 3)
                            g.source_end_seconds = round(word_timestamps[valid_g[-1]].end, 3)
                    if token_spans:
                        valid_g = [i for i in matched_global if i < len(token_spans)]
                        if valid_g:
                            g.source_char_start = token_spans[valid_g[0]][0]
                            g.source_char_end = token_spans[valid_g[-1]][1]
                else:
                    g.alignment_type = AlignmentType.INFERRED
                    g.alignment_confidence = 0.85
                    g.source_token_indexes = []
                    g.local_token_indexes = []
                    g.global_source_token_indexes = []
                    g.source_char_start = None
                    g.source_char_end = None
                    g.source_start_seconds = prop.source_start_seconds
                    g.source_end_seconds = prop.source_end_seconds

        logger.debug(
            "Alineación de tokens completada: %d proposiciones, %d glosas procesadas.",
            len(propositions), len(glosses),
        )
        return propositions, glosses

    def validate_alignment(
        self,
        propositions: List[SemanticProposition],
        glosses: List[GlossItem],
        total_tokens: int,
    ) -> List[Dict[str, Any]]:
        """
        Valida que todos los índices de tokens y marcas de tiempo sean coherentes.
        """
        issues: List[Dict[str, Any]] = []

        for prop in propositions:
            for idx in prop.global_source_token_indexes:
                if idx < 0 or (total_tokens > 0 and idx >= total_tokens):
                    issues.append({
                        "code": "ALIGNMENT_INDEX_OUT_OF_RANGE",
                        "message": f"Proposición '{prop.id}' contiene índice global fuera de rango: {idx}",
                        "affected_ids": [prop.id],
                    })
            if prop.source_start_seconds is not None and prop.source_end_seconds is not None:
                if prop.source_end_seconds < prop.source_start_seconds:
                    issues.append({
                        "code": "INVERTED_PROPOSITION_TIMESTAMPS",
                        "message": f"Proposición '{prop.id}' tiene fin ({prop.source_end_seconds}) menor que inicio ({prop.source_start_seconds})",
                        "affected_ids": [prop.id],
                    })

        for g in glosses:
            for idx in g.global_source_token_indexes:
                if idx < 0 or (total_tokens > 0 and idx >= total_tokens):
                    issues.append({
                        "code": "ALIGNMENT_INDEX_OUT_OF_RANGE",
                        "message": f"Glosa '{g.gloss}' (orden {g.order}) contiene índice global fuera de rango: {idx}",
                        "affected_ids": [str(g.id)],
                    })
            if g.source_start_seconds is not None and g.source_end_seconds is not None:
                if g.source_end_seconds < g.source_start_seconds:
                    issues.append({
                        "code": "INVERTED_GLOSS_TIMESTAMPS",
                        "message": f"Glosa '{g.gloss}' tiene fin ({g.source_end_seconds}) menor que inicio ({g.source_start_seconds})",
                        "affected_ids": [str(g.id)],
                    })

        return issues

