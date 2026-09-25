"""
Motor de gramática LSEC centralizado y versionado.

Proporciona:
  - Esquema de reglas tipado (``GrammarRule``).
  - Registro central de reglas (``RuleRegistry``).
  - Motor de ejecución con trazabilidad (``RuleEngine``).
  - Resolución de conflictos determinista (``ConflictResolver``).
  - Cálculo de confianza multidimensional (``ConfidenceCalculator``).
"""

from app.lsec_grammar.schema import (
    GrammarRule,
    RuleAction,
    RuleCondition,
    RuleScope,
    RuleValidationStatus,
)
from app.lsec_grammar.registry import RuleRegistry
from app.lsec_grammar.rule_engine import RuleEngine, RuleApplication
from app.lsec_grammar.conflict_resolver import ConflictResolver, ConflictRecord
from app.lsec_grammar.confidence import ConfidenceCalculator

__all__ = [
    "GrammarRule",
    "RuleAction",
    "RuleCondition",
    "RuleScope",
    "RuleValidationStatus",
    "RuleRegistry",
    "RuleEngine",
    "RuleApplication",
    "ConflictResolver",
    "ConflictRecord",
    "ConfidenceCalculator",
]
