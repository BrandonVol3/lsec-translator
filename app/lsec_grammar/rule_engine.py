"""
Motor de ejecución de reglas gramaticales LSEC.

Evalúa condiciones sobre un ``SemanticFrame`` y aplica acciones,
registrando cada aplicación para trazabilidad completa.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from app.lsec_grammar.schema import (
    GrammarRule,
    RuleAction,
    RuleCondition,
    RuleScope,
)

from app.core.schemas import (
    AlignmentType,
    FacialExpression,
    GlossItem,
    GlossType,
    NonManualMarker,
)

logger = logging.getLogger(__name__)

_COPULA_GLOSSES: Set[str] = {"SER", "ESTAR", "ES", "SON", "ERA", "FUE", "ESTÁ", "ESTÁN", "ESTABA"}
_WH_GLOSSES: Set[str] = {"QUIÉN", "QUIÉNES", "QUÉ", "DÓNDE", "CUÁNDO", "CÓMO", "CUÁL", "CUÁLES", "CUÁNTO", "CUÁNTOS"}
_NEG_GLOSSES: Set[str] = {"NO", "NUNCA", "JAMÁS", "NADIE", "TAMPOCO"}
_TIME_GLOSSES: Set[str] = {"AYER", "HOY", "MAÑANA", "AHORA", "ANTES", "DESPUÉS", "FUTURO", "PASADO", "SIEMPRE"}


@dataclass
class RuleApplication:
    """Registro de la aplicación de una regla sobre un frame semántico."""
    rule_id: str
    rule_name: str
    scope: RuleScope
    actions_applied: List[str] = field(default_factory=list)
    confidence_delta: float = 0.0
    notes: str = ""
    affected_gloss_ids: List[str] = field(default_factory=list)


class RuleEngine:
    """
    Motor que evalúa reglas contra un ``SemanticFrame`` y ejecuta acciones
    que modifican directamente la secuencia final de glosas LSEC.

    Garantiza que las reglas gramaticales centrales gobiernen la transformación
    y no se limiten a registrar metadatos pasivos.
    """

    def evaluate_conditions(
        self,
        conditions: List[RuleCondition],
        frame: Dict[str, Any],
    ) -> bool:
        """Evalúa TODAS las condiciones contra el frame (conjunción)."""
        for cond in conditions:
            if not self._eval_single(cond, frame):
                return False
        return True

    def apply_rules(
        self,
        rules: List[GrammarRule],
        frame: Dict[str, Any],
        *,
        exclude_ids: Optional[Set[str]] = None,
    ) -> List[RuleApplication]:
        """
        Evalúa una lista de reglas contra un frame.

        Respeta prioridad, exclusiones mutuas e incompatibilidades.
        Retorna las ``RuleApplication`` de las reglas activadas.
        """
        exclude_ids = exclude_ids or set()
        applied: List[RuleApplication] = []
        activated_ids: Set[str] = set()

        for rule in rules:
            if not rule.is_executable:
                continue
            if rule.rule_id in exclude_ids:
                continue
            # Verificar exclusiones mutuas
            if any(exc in activated_ids for exc in rule.exclusions):
                continue
            if any(inc in activated_ids for inc in rule.incompatible_rules):
                continue

            if self.evaluate_conditions(rule.conditions, frame):
                app = RuleApplication(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    scope=rule.scope,
                    actions_applied=[a.action_type for a in rule.actions],
                    confidence_delta=-0.05 if rule.reduces_confidence else 0.0,
                )
                applied.append(app)
                activated_ids.add(rule.rule_id)
                # Agregar exclusiones transitivas
                exclude_ids.update(rule.exclusions)

        return applied

    def execute_actions(
        self,
        rules: List[GrammarRule],
        applications: List[RuleApplication],
        glosses: List[GlossItem],
        frame: Dict[str, Any],
        start_order: int = 0,
    ) -> List[GlossItem]:
        """
        Ejecuta directamente las acciones de las reglas activadas sobre la secuencia de glosas.

        Modifica el orden de constituyentes (SOV, WH final, negación final, tiempo inicial),
        inserta marcadores aspectuales/temporales/deícticos, omite cópulas vacías,
        asigna componentes no manuales y actualiza los identificadores de glosas afectadas.
        """
        if not glosses:
            return []

        rules_by_id = {r.rule_id: r for r in rules}
        current_glosses = list(glosses)

        for app in applications:
            rule = rules_by_id.get(app.rule_id)
            if not rule:
                continue

            for action in rule.actions:
                atype = action.action_type
                params = action.parameters or {}

                # 1. Omisión de cópula vacía
                if atype == "omit_predicate":
                    reason = params.get("reason", "")
                    if "copula" in reason:
                        kept: List[GlossItem] = []
                        for g in current_glosses:
                            g_clean = g.gloss.upper()
                            src_clean = (g.normalized_word or g.source_word or "").lower()
                            if g_clean in _COPULA_GLOSSES or src_clean in ("ser", "estar"):
                                app.affected_gloss_ids.append(str(g.id))
                            else:
                                kept.append(g)
                        if kept:  # No dejar vacía la secuencia si sólo había cópula
                            current_glosses = kept

                # 2. Reemplazo de glosa (ej: cópula existencial → HABER)
                elif atype == "replace_gloss":
                    target_g = params.get("gloss")
                    if target_g:
                        for g in current_glosses:
                            if g.gloss.upper().startswith("NO-"):
                                continue
                            if g.gloss.upper() in _COPULA_GLOSSES or (g.normalized_word and g.normalized_word.lower() in ("haber", "ser", "estar")):
                                g.gloss = target_g
                                g.normalized_word = target_g.lower()
                                app.affected_gloss_ids.append(str(g.id))

                # 3. Inserción de glosa (aspecto, tiempo, deixis, modalidad)
                elif atype == "insert_gloss":
                    raw_g = params.get("gloss", "")
                    # Sustitución dinámica de variables de persona
                    if "{agent_person}" in raw_g:
                        p_val = frame.get("agent_person") or "1"
                        target_gloss = raw_g.replace("{agent_person}", p_val)
                    elif "{person}" in raw_g:
                        p_val = frame.get("agent_person") or "1"
                        target_gloss = raw_g.replace("{person}", p_val)
                    else:
                        target_gloss = raw_g

                    pos = params.get("position", "before_predicate")

                    # Evitar duplicar si la glosa ya está presente
                    already_present = any(g.gloss == target_gloss for g in current_glosses)
                    if target_gloss and not already_present:
                        new_item = GlossItem(
                            gloss=target_gloss,
                            gloss_type=GlossType.SIGN,
                            order=0,
                            proposition_id=frame.get("proposition_id", "p0"),
                            duration_ms=400,
                            notes=f"Insertado por regla {rule.rule_id}",
                            alignment_type=AlignmentType.GRAMMATICAL,
                            inference_rule_id=rule.rule_id,
                            lexical_strategy="grammatical_rule",
                        )

                        # Posicionamiento exacto
                        if pos == "time_first" or pos == "clause_start":
                            current_glosses.insert(0, new_item)
                        elif pos == "clause_end":
                            current_glosses.append(new_item)
                        elif pos == "after_predicate":
                            # Buscar último verbo/predicado
                            verb_idx = -1
                            for idx, g in enumerate(current_glosses):
                                if g.gloss not in _TIME_GLOSSES and g.gloss not in _NEG_GLOSSES and g.gloss not in _WH_GLOSSES:
                                    verb_idx = idx
                            if verb_idx >= 0 and verb_idx + 1 < len(current_glosses):
                                current_glosses.insert(verb_idx + 1, new_item)
                            else:
                                current_glosses.append(new_item)
                        else:  # before_predicate
                            # Posición canónica del sujeto en LSEC: después de TIEMPO y LUGAR, antes del OBJETO y VERBO
                            insert_idx = 0
                            leading_temporal = False
                            is_question = str(frame.get("sentence_type", "")).startswith("interrogative")
                            if current_glosses and current_glosses[0].gloss in ("AUNQUE", "PERO", "ADEMÁS"):
                                insert_idx = 1
                                leading_temporal = True
                            scan_indexes = [] if is_question else range(insert_idx, len(current_glosses))
                            for idx in scan_indexes:
                                g = current_glosses[idx]
                                g_up = g.gloss.upper()
                                is_time_g = (
                                    g_up in _TIME_GLOSSES
                                    or (g.normalized_word and g.normalized_word.lower() in ("ayer", "hoy", "mañana", "antes", "futuro", "después", "ahora", "siempre"))
                                )
                                is_loc_g = (
                                    g.spatial_location is not None
                                    or (g.notes and "lugar" in g.notes.lower())
                                    or (g.normalized_word and g.normalized_word.lower() in ("escuela", "casa", "colegio", "universidad", "hospital", "parque", "aula", "clase"))
                                    or (g.source_word and g.source_word.lower() in ("escuela", "casa", "colegio", "universidad", "hospital", "parque", "aula", "clase"))
                                )
                                if is_time_g:
                                    insert_idx = idx + 1
                                    leading_temporal = True
                                elif is_loc_g and leading_temporal:
                                    insert_idx = idx + 1
                                elif g_up.startswith("PRO"):
                                    insert_idx = idx + 1
                                else:
                                    break
                            current_glosses.insert(insert_idx, new_item)

                        app.affected_gloss_ids.append(str(new_item.id))

                # 4. Reordenamiento discursivo
                elif atype == "reorder":
                    pattern = params.get("pattern", "")

                    if pattern == "time_first":
                        time_items = [g for g in current_glosses if g.gloss in _TIME_GLOSSES or (g.normalized_word and g.normalized_word.lower() in ("ayer", "hoy", "mañana", "antes", "futuro"))]
                        other_items = [g for g in current_glosses if g not in time_items]
                        if time_items:
                            current_glosses = time_items + other_items
                            for ti in time_items:
                                app.affected_gloss_ids.append(str(ti.id))

                    elif pattern == "wh_final":
                        wh_items = [g for g in current_glosses if g.gloss in _WH_GLOSSES or (g.source_word and g.source_word.lower() in ("dónde", "qué", "quién", "cuándo", "cómo", "cuál", "cuánto"))]
                        non_wh = [g for g in current_glosses if g not in wh_items]
                        if wh_items:
                            current_glosses = non_wh + wh_items
                            for wi in wh_items:
                                app.affected_gloss_ids.append(str(wi.id))

                    elif pattern == "negation_final":
                        neg_items = [g for g in current_glosses if g.gloss in _NEG_GLOSSES or (g.source_word and g.source_word.lower() in ("no", "nunca", "jamás", "nadie", "tampoco"))]
                        non_neg = [g for g in current_glosses if g not in neg_items]
                        if neg_items:
                            current_glosses = non_neg + neg_items
                            for ni in neg_items:
                                app.affected_gloss_ids.append(str(ni.id))

                    elif pattern == "verb_first":
                        # En imperativos directivos simples, ubicar el verbo de mandato al inicio tras el tiempo/cortesía
                        time_items = [g for g in current_glosses if g.gloss in _TIME_GLOSSES or g.gloss == "POR-FAVOR"]
                        non_time = [g for g in current_glosses if g not in time_items]
                        if len(non_time) >= 2:
                            pred_lem = str(frame.get("predicate_lemma", "")).lower()
                            verb_idx = -1
                            for idx, g in enumerate(non_time):
                                if (g.normalized_word and g.normalized_word.lower() == pred_lem):
                                    verb_idx = idx
                                    break
                            if verb_idx == -1:
                                verb_idx = len(non_time) - 1
                            if verb_idx > 0:
                                v_item = non_time[verb_idx]
                                rest = [g for i, g in enumerate(non_time) if i != verb_idx]
                                current_glosses = time_items + rest + [v_item]
                                app.affected_gloss_ids.append(str(v_item.id))

                    elif pattern == "topic_first":
                        t_val = str(frame.get("topic", "")).upper()
                        if t_val:
                            top_items = [g for g in current_glosses if t_val in g.gloss or g.gloss in t_val]
                            rest = [g for g in current_glosses if g not in top_items]
                            time_items = [g for g in rest if g.gloss in _TIME_GLOSSES]
                            non_time_rest = [g for g in rest if g not in time_items]
                            if top_items:
                                current_glosses = time_items + top_items + non_time_rest
                                for ti in top_items:
                                    app.affected_gloss_ids.append(str(ti.id))

                # 5. Componentes no manuales (CNM)
                elif atype == "set_non_manual":
                    marker_type = params.get("marker_type") or params.get("expression")
                    if marker_type == "negation":
                        for g in current_glosses:
                            if g.gloss in _NEG_GLOSSES:
                                g.non_manual = NonManualMarker(
                                    expression=FacialExpression.NEGATION,
                                    head_movement="negar",
                                )
                                app.affected_gloss_ids.append(str(g.id))
                    elif marker_type in ("question_wh", "pregunta_qu"):
                        for g in current_glosses:
                            if g.gloss in _WH_GLOSSES:
                                g.non_manual = NonManualMarker(
                                    expression=FacialExpression.QUESTION_WH,
                                    head_movement="inclinar",
                                )
                                app.affected_gloss_ids.append(str(g.id))
                    elif marker_type in ("question_yn", "pregunta_sn"):
                        for g in current_glosses:
                            g.non_manual = NonManualMarker(
                                expression=FacialExpression.QUESTION_YESNO,
                            )
                            app.affected_gloss_ids.append(str(g.id))
                    elif marker_type == "directiva":
                        for g in current_glosses:
                            if g.gloss not in _TIME_GLOSSES and g.gloss not in _NEG_GLOSSES:
                                g.non_manual = NonManualMarker(
                                    expression=FacialExpression.NEUTRAL,
                                    head_movement="firme",
                                )
                                app.affected_gloss_ids.append(str(g.id))
                                break

                # 6. Clasificador candidato
                elif atype in ("set_classifier", "generate_classifier_candidate"):
                    candidate_info = {
                        "status": "CLASSIFIER_CANDIDATE",
                        "requires_lexical_support": True,
                        "rule_id": rule.rule_id,
                    }
                    frame.setdefault("classifier_candidates", []).append(candidate_info)

        # Normalizar orden secuencial monótono
        for i, g in enumerate(current_glosses):
            g.order = start_order + i

        return current_glosses

    # ── Evaluador de condición individual ──────────────────────

    @staticmethod
    def _eval_single(cond: RuleCondition, frame: Dict[str, Any]) -> bool:
        """Evalúa una condición individual contra el frame."""
        val = _deep_get(frame, cond.field)

        op = cond.operator
        expected = cond.value

        if op == "eq":
            if expected is False:
                return bool(val) is False
            return val == expected
        if op == "neq":
            if expected is True:
                return bool(val) is False
            return val != expected
        if op == "in":
            return val in expected if isinstance(expected, (list, set, tuple)) else val == expected
        if op == "not_in":
            return val not in expected if isinstance(expected, (list, set, tuple)) else val != expected
        if op == "contains":
            if isinstance(val, str):
                return expected in val
            if isinstance(val, (list, set)):
                return expected in val
            return False
        if op == "exists":
            if expected:
                return val is not None and val != "" and val != []
            return val is None or val == "" or val == []
        if op == "gt":
            try:
                return float(val) > float(expected)
            except (TypeError, ValueError):
                return False
        if op == "lt":
            try:
                return float(val) < float(expected)
            except (TypeError, ValueError):
                return False

        logger.warning("RuleEngine: operador desconocido '%s'", op)
        return False


def _deep_get(d: Dict[str, Any], dotted_key: str) -> Any:
    """Accede a claves anidadas separadas por '.'."""
    keys = dotted_key.split(".")
    current: Any = d
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k)
        else:
            return None
    return current
