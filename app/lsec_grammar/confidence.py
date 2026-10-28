"""
Calculadora de confianza multidimensional para traducciones LSEC.

Dimensiones:
  1. Confianza lingüística (basada en reglas activadas y su validación).
  2. Confianza léxica (disponibilidad en el lexicón LSEC).
  3. Confianza semántica (cobertura de roles semánticos).
  4. Confianza de producción (correferencia, espacialidad, coherencia).

La confianza final es una ponderación de estas dimensiones.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.lsec_grammar.rule_engine import RuleApplication
from app.lsec_grammar.schema import RuleValidationStatus

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceVector:
    """Vector multidimensional de confianza de una traducción."""
    linguistic: float = 0.0
    lexical: float = 0.0
    semantic: float = 0.0
    production: float = 0.0
    overall: float = 0.0

    # Pesos por defecto
    w_linguistic: float = 0.30
    w_lexical: float = 0.25
    w_semantic: float = 0.25
    w_production: float = 0.20

    def compute_overall(self) -> float:
        self.overall = (
            self.linguistic * self.w_linguistic
            + self.lexical * self.w_lexical
            + self.semantic * self.w_semantic
            + self.production * self.w_production
        )
        self.overall = round(min(max(self.overall, 0.0), 1.0), 4)
        return self.overall

    def to_dict(self) -> dict:
        return {
            "linguistic": round(self.linguistic, 4),
            "lexical": round(self.lexical, 4),
            "semantic": round(self.semantic, 4),
            "production": round(self.production, 4),
            "overall": round(self.overall, 4),
        }


class ConfidenceCalculator:
    """
    Calcula la confianza de una proposición traducida basándose
    en las reglas aplicadas, cobertura léxica y roles semánticos.
    """

    @staticmethod
    def from_rule_applications(
        applications: List[RuleApplication],
        *,
        lexicon_hit_ratio: float = 1.0,
        semantic_coverage: float = 1.0,
        has_coreference: bool = False,
        has_spatial: bool = False,
        has_unresolved: bool = False,
    ) -> ConfidenceVector:
        """
        Construye el vector de confianza a partir de las aplicaciones de reglas
        y métricas de cobertura.
        """
        vec = ConfidenceVector()

        # 1. Confianza lingüística
        if not applications:
            vec.linguistic = 0.65  # Sin reglas = heurístico
        else:
            deltas = [a.confidence_delta for a in applications]
            base = 0.85
            vec.linguistic = min(max(base + sum(deltas), 0.3), 1.0)

        # 2. Confianza léxica
        vec.lexical = min(max(lexicon_hit_ratio, 0.0), 1.0)

        # 3. Confianza semántica
        vec.semantic = min(max(semantic_coverage, 0.0), 1.0)

        # 4. Confianza de producción
        prod = 0.80
        if has_coreference:
            prod += 0.05
        if has_spatial:
            prod += 0.05
        if has_unresolved:
            prod -= 0.15
        vec.production = min(max(prod, 0.3), 1.0)

        vec.compute_overall()
        return vec
