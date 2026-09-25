"""
Resolución determinista de conflictos entre reglas gramaticales.

Cuando dos o más reglas se activan simultáneamente y son incompatibles
(ej: dos reordenamientos contradictorios), el ``ConflictResolver``
selecciona cuál se aplica basándose en:
  1. Prioridad (menor valor = mayor prioridad).
  2. Estado de validación (COMMUNITY_VALIDATED > HUMAN_REVIEWED > PROVISIONAL).
  3. Peso de confianza (``confidence_weight``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from app.lsec_grammar.schema import GrammarRule, RuleValidationStatus

logger = logging.getLogger(__name__)

_VALIDATION_ORDER = {
    RuleValidationStatus.COMMUNITY_VALIDATED: 0,
    RuleValidationStatus.HUMAN_REVIEWED: 1,
    RuleValidationStatus.BASELINE_LEGACY: 2,
    RuleValidationStatus.PROVISIONAL: 3,
    RuleValidationStatus.DRAFT: 4,
    RuleValidationStatus.DEPRECATED: 5,
    RuleValidationStatus.REJECTED: 6,
}


@dataclass
class ConflictRecord:
    """Registro de un conflicto detectado y su resolución."""
    winning_rule_id: str
    losing_rule_ids: List[str] = field(default_factory=list)
    reason: str = ""


class ConflictResolver:
    """
    Resuelve conflictos entre reglas incompatibles.

    Dado un conjunto de reglas activadas, detecta conflictos
    (exclusiones mutuas, incompatibilidades) y selecciona la
    regla ganadora de forma determinista.
    """

    @staticmethod
    def resolve(rules: List[GrammarRule]) -> tuple[List[GrammarRule], List[ConflictRecord]]:
        """
        Filtra reglas conflictivas y retorna las ganadoras con registros.

        Retorna:
            - Lista de reglas sin conflictos.
            - Lista de ``ConflictRecord`` para trazabilidad.
        """
        if len(rules) <= 1:
            return rules, []

        conflicts: List[ConflictRecord] = []
        excluded_ids: set[str] = set()
        winners: List[GrammarRule] = []

        # Ordenar por prioridad determinista
        sorted_rules = sorted(rules, key=lambda r: (
            r.priority,
            _VALIDATION_ORDER.get(r.validation_status, 99),
            -r.confidence_weight,
            r.rule_id,
        ))

        for rule in sorted_rules:
            if rule.rule_id in excluded_ids:
                continue

            # Detectar conflictos con reglas ya ganadoras
            conflicting_with = []
            for winner in winners:
                if (
                    rule.rule_id in winner.exclusions
                    or winner.rule_id in rule.exclusions
                    or rule.rule_id in winner.incompatible_rules
                    or winner.rule_id in rule.incompatible_rules
                ):
                    conflicting_with.append(winner)

            if conflicting_with:
                # El ganador ya está seleccionado (tiene mayor prioridad)
                conflicts.append(ConflictRecord(
                    winning_rule_id=conflicting_with[0].rule_id,
                    losing_rule_ids=[rule.rule_id],
                    reason=f"Prioridad {conflicting_with[0].priority} < {rule.priority}",
                ))
                excluded_ids.add(rule.rule_id)
            else:
                winners.append(rule)
                # Marcar exclusiones
                excluded_ids.update(rule.exclusions)
                excluded_ids.update(rule.incompatible_rules)

        if conflicts:
            logger.debug(
                "ConflictResolver: %d conflicto(s) resueltos entre %d reglas.",
                len(conflicts), len(rules),
            )

        return winners, conflicts
