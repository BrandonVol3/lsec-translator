"""
discourse_group_optimizer.py
Consolidación conservadora y auditable de glosas dentro de cada oración (idea completa).

Contexto (DATASET: Manual Práctico para Intérpretes en LSEC): el intérprete debe transmitir la idea con
fidelidad, «sin omisiones ni adiciones», y evitar el calco palabra por palabra del español. El
segmentador proposicional fragmenta las oraciones (p. ej. 8 oraciones -> 21 proposiciones en 1.mp4), lo
que deja artefactos en las fronteras entre proposiciones: glosas idénticas adyacentes, deixis
redundante, verbos repetidos en coordinación paralela.

Principios:
  * Solo opera DENTRO de una misma oración (`sentence_id`).
  * Nunca toca dactilología, números ni glosas de contenido distinto.
  * Cada acción queda registrada en `condensation_log` (regla, glosas afectadas, si se aplicó) para que
    la revisión por personas sordas nativas pueda aceptarla o revertirla.
  * Niveles: ``off`` | ``conservative`` (por defecto) | ``balanced``.

Reglas:
  R1  Glosa idéntica adyacente entre proposiciones de la misma oración  -> fusiona (conservative+).
  R2  PRO* inferido (sin palabra fuente) ya presente antes en la oración, sin otro pronombre entre
      ambos                                                          -> elimina (conservative+).
  R3  Verbo final repetido en coordinación paralela (`also`/`more_than`/`not_only`/`additive`)
      -> `conservative`: solo sugiere (applied=False); `balanced`: conserva el verbo final y marca
      la glosa para revisión nativa.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.schemas import (
    DiscourseBlock,
    GlossItem,
    NonManualSpan,
    SemanticProposition,
    SpatialOperation,
    SpatialReferent,
)

logger = logging.getLogger(__name__)

_PRONOUN_RE = re.compile(r"^PRO[123](?:-PL)?$")
_PARALLEL_RELATIONS = {"also", "more_than", "not_only", "additive", "addition"}
_VALID_LEVELS = {"off", "conservative", "balanced"}


def _gloss_type_name(g: GlossItem) -> str:
    gt = getattr(g, "gloss_type", None)
    return str(getattr(gt, "value", gt) or "").upper()


def _is_protected(g: GlossItem) -> bool:
    """Dactilología, números y glosas de letra aislada nunca se consolidan."""
    gt = _gloss_type_name(g)
    if "DACTIL" in gt or "FINGER" in gt or "NUMBER" in gt or "NUM" in gt:
        return True
    text = (g.gloss or "").upper()
    return bool(text) and all(len(p) == 1 for p in text.split("-") if p) and "-" in text


class DiscourseGroupOptimizer:
    def __init__(self, level: str = "conservative") -> None:
        self.level = level if level in _VALID_LEVELS else "conservative"

    # ------------------------------------------------------------------ API
    def optimize(
        self,
        propositions: List[SemanticProposition],
        glosses: List[GlossItem],
        blocks: List[DiscourseBlock],
        referents: List[SpatialReferent],
        operations: List[SpatialOperation],
        spans: List[NonManualSpan],
        level: Optional[str] = None,
    ) -> Tuple[List[GlossItem], List[DiscourseBlock], List[SpatialReferent], List[SpatialOperation], List[NonManualSpan], List[Dict[str, Any]]]:
        lvl = level if level in _VALID_LEVELS else self.level
        prop_by_id = {p.id: p for p in propositions}
        ordered = sorted(glosses, key=lambda g: g.order)

        # Anotar sentence_id en cada glosa (también cuando el optimizador está desactivado).
        for g in ordered:
            pid = g.proposition_id or g.origin_proposition_id
            prop = prop_by_id.get(pid) if pid else None
            if prop is not None and getattr(prop, "sentence_id", None) is not None:
                g.sentence_id = prop.sentence_id

        if lvl == "off" or len(ordered) < 2:
            return glosses, blocks, referents, operations, spans, []

        log: List[Dict[str, Any]] = []
        merged_into: Dict[str, GlossItem] = {}   # id de glosa eliminada -> glosa que la absorbe

        # ---- R1: duplicados adyacentes en la misma oración -------------------------------
        kept: List[GlossItem] = []
        for g in ordered:
            prev = kept[-1] if kept else None
            if (
                prev is not None
                and prev.sentence_id is not None
                and prev.sentence_id == g.sentence_id
                and (prev.gloss or "").upper() == (g.gloss or "").upper()
                and not _is_protected(g)
                and (
                    prev.proposition_id != g.proposition_id
                    # Misma proposición: solo si provienen de palabras fuente distintas (p. ej. «de» +
                    # «a partir de» -> DESDE DESDE). Una repetición real hablada («muy muy») se conserva.
                    or (prev.source_word or "").strip().lower() != (g.source_word or "").strip().lower()
                )
            ):
                merged_into[g.id] = prev
                log.append(self._entry("R1_MERGE_ADJACENT_DUPLICATE", g, prev, True,
                                       "Glosa idéntica adyacente entre proposiciones de la misma oración."))
                continue
            kept.append(g)

        # ---- R2: pronombre inferido redundante dentro de la oración -----------------------
        survivors: List[GlossItem] = []
        last_pronoun_in_sentence: Dict[int, str] = {}
        seen_pronoun: Dict[Tuple[int, str], GlossItem] = {}
        for g in kept:
            sid = g.sentence_id
            text = (g.gloss or "").upper()
            if sid is not None and _PRONOUN_RE.match(text):
                # Deixis inferida por sujeto tácito (regla LSEC_PRODROP_EXPLICIT). A esta altura del pipeline la
                # alineación fuente aún no asigna `alignment_type`, por eso se usa la regla de origen.
                inferred = not g.source_word and (
                    g.inference_rule_id == "LSEC_PRODROP_EXPLICIT"
                    or str(getattr(g.alignment_type, "value", g.alignment_type) or "").upper() == "INFERRED"
                )
                first = seen_pronoun.get((sid, text))
                if first is not None and inferred and last_pronoun_in_sentence.get(sid) == text:
                    merged_into[g.id] = first
                    log.append(self._entry("R2_DROP_REDUNDANT_INFERRED_PRONOUN", g, first, True,
                                           "Deixis inferida repetida en la misma oración sin otro pronombre entre ambas."))
                    continue
                seen_pronoun.setdefault((sid, text), g)
                last_pronoun_in_sentence[sid] = text
            survivors.append(g)

        # ---- R3: verbo final repetido en coordinación paralela ----------------------------
        survivors = self._parallel_verbs(survivors, prop_by_id, merged_into, log, lvl)

        if not merged_into:
            return glosses, blocks, referents, operations, spans, log

        return self._apply(glosses, survivors, merged_into, blocks, referents, operations, spans, log)

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _entry(rule: str, removed: GlossItem, retained: GlossItem, applied: bool, reason: str) -> Dict[str, Any]:
        return {
            "rule_id": rule,
            "applied": applied,
            "sentence_id": removed.sentence_id,
            "gloss": removed.gloss,
            "removed_gloss_id": removed.id,
            "retained_gloss_id": retained.id,
            "removed_proposition_id": removed.proposition_id,
            "retained_proposition_id": retained.proposition_id,
            "removed_source_word": removed.source_word,
            "reason": reason,
        }

    def _parallel_verbs(
        self,
        survivors: List[GlossItem],
        prop_by_id: Dict[str, SemanticProposition],
        merged_into: Dict[str, GlossItem],
        log: List[Dict[str, Any]],
        lvl: str,
    ) -> List[GlossItem]:
        last_of_prop: Dict[str, GlossItem] = {}
        for g in survivors:
            if g.proposition_id:
                last_of_prop[g.proposition_id] = g

        drop_ids = set()
        prop_ids_in_order: List[str] = []
        for g in survivors:
            if g.proposition_id and g.proposition_id not in prop_ids_in_order:
                prop_ids_in_order.append(g.proposition_id)

        for a_pid, b_pid in zip(prop_ids_in_order, prop_ids_in_order[1:]):
            a_prop, b_prop = prop_by_id.get(a_pid), prop_by_id.get(b_pid)
            if not a_prop or not b_prop:
                continue
            if getattr(a_prop, "sentence_id", None) is None or a_prop.sentence_id != b_prop.sentence_id:
                continue
            if (b_prop.discourse_relation or "") not in _PARALLEL_RELATIONS:
                continue
            ga, gb = last_of_prop.get(a_pid), last_of_prop.get(b_pid)
            if ga is None or gb is None or ga.id in merged_into or gb.id in merged_into:
                continue
            if (ga.gloss or "").upper() != (gb.gloss or "").upper() or _is_protected(ga):
                continue
            if _PRONOUN_RE.match((ga.gloss or "").upper()) or ga.lexical_strategy == "discourse_connector":
                continue
            applied = lvl == "balanced"
            log.append(self._entry(
                "R3_PARALLEL_FINAL_VERB", ga, gb, applied,
                "Verbo final repetido en coordinación paralela; se conserva el verbo final de la serie."
                if applied else "Sugerencia: el verbo final repetido podría consolidarse en la coordinación paralela.",
            ))
            if applied:
                merged_into[ga.id] = gb
                drop_ids.add(ga.id)
        return [g for g in survivors if g.id not in drop_ids]

    def _apply(
        self,
        original: List[GlossItem],
        survivors: List[GlossItem],
        merged_into: Dict[str, GlossItem],
        blocks: List[DiscourseBlock],
        referents: List[SpatialReferent],
        operations: List[SpatialOperation],
        spans: List[NonManualSpan],
        log: List[Dict[str, Any]],
    ):
        by_id = {g.id: g for g in original}

        def root(g: GlossItem) -> GlossItem:
            seen = set()
            while g.id in merged_into and g.id not in seen:
                seen.add(g.id)
                g = merged_into[g.id]
            return g

        # Cobertura fuente: el sobreviviente absorbe los tokens/tiempos de la glosa eliminada.
        for rid, target in merged_into.items():
            removed = by_id.get(rid)
            if removed is None:
                continue
            tgt = root(target)
            for attr in ("source_token_indexes", "local_token_indexes", "global_source_token_indexes"):
                merged = sorted(set(getattr(tgt, attr) or []) | set(getattr(removed, attr) or []))
                setattr(tgt, attr, merged)
            if removed.source_char_end is not None:
                tgt.source_char_end = max(tgt.source_char_end or 0, removed.source_char_end)
            if removed.source_char_start is not None:
                tgt.source_char_start = min(tgt.source_char_start if tgt.source_char_start is not None else removed.source_char_start, removed.source_char_start)

        survivors = sorted(survivors, key=lambda g: g.order)
        survivor_ids = {g.id for g in survivors}
        old_orders = {g.id: g.order for g in original}

        # old_order -> new_order (las eliminadas heredan el nuevo orden de quien las absorbe).
        new_order_of: Dict[str, int] = {}
        for new_order, g in enumerate(survivors):
            new_order_of[g.id] = new_order
        order_map: Dict[int, int] = {}
        for g in original:
            tgt = g if g.id in survivor_ids else root(g)
            if tgt.id in new_order_of:
                order_map[old_orders[g.id]] = new_order_of[tgt.id]
        for g in survivors:
            g.order = new_order_of[g.id]

        def remap(o: Optional[int]) -> Optional[int]:
            if o is None:
                return None
            if o in order_map:
                return order_map[o]
            lower = [k for k in order_map if k <= o]
            return order_map[max(lower)] if lower else 0

        removed_ids = set(merged_into.keys())

        def fix_ids(ids: List[str]) -> List[str]:
            out: List[str] = []
            for gid in ids:
                gid_s = str(gid)
                if gid_s in removed_ids:
                    tgt = root(by_id[gid_s]) if gid_s in by_id else None
                    gid_s = str(tgt.id) if tgt is not None else gid_s
                if gid_s not in out and (gid_s in survivor_ids or gid_s not in by_id):
                    out.append(gid_s)
            return out

        for b in blocks:
            b.start_order = remap(b.start_order) or 0
            b.end_order = max(b.start_order, remap(b.end_order) or 0)
            b.gloss_ids = fix_ids(b.gloss_ids)
        for s in spans:
            s.start_order = remap(s.start_order) or 0
            s.end_order = max(s.start_order, remap(s.end_order) or 0)
            s.gloss_ids = fix_ids(s.gloss_ids)
        for op in operations:
            if op.source_order is not None:
                op.source_order = remap(op.source_order)
            if op.target_order is not None:
                op.target_order = remap(op.target_order)
            trig = op.operation_trigger_gloss_id
            if trig and str(trig) in removed_ids and str(trig) in by_id:
                op.operation_trigger_gloss_id = str(root(by_id[str(trig)]).id)
        for r in referents:
            if r.established_at_order is not None:
                r.established_at_order = remap(r.established_at_order)

        logger.info("DiscourseGroupOptimizer: %d glosas consolidadas (%d acciones registradas).", len(removed_ids), len(log))
        return survivors, blocks, referents, operations, spans, log
