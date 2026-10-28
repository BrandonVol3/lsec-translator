"""
Esquema tipado para reglas gramaticales LSEC versionadas.

Cada regla posee identificador, versión, prioridad, condiciones,
acciones, estado de validación, evidencia y pruebas asociadas.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Estados de validación ──────────────────────────────────────

class RuleValidationStatus(str, Enum):
    """Estado de validación lingüística de una regla."""
    DRAFT = "DRAFT"
    PROVISIONAL = "PROVISIONAL"
    HUMAN_REVIEWED = "HUMAN_REVIEWED"
    COMMUNITY_VALIDATED = "COMMUNITY_VALIDATED"
    BASELINE_LEGACY = "BASELINE_LEGACY"
    DEPRECATED = "DEPRECATED"
    REJECTED = "REJECTED"


# ── Ámbito de aplicación ──────────────────────────────────────

class RuleScope(str, Enum):
    """Dominio lingüístico sobre el que opera la regla."""
    WORD_ORDER = "WORD_ORDER"
    NEGATION = "NEGATION"
    INTERROGATION = "INTERROGATION"
    TEMPORALITY = "TEMPORALITY"
    ASPECT = "ASPECT"
    MODALITY = "MODALITY"
    PRODROP = "PRODROP"
    COREFERENCE = "COREFERENCE"
    CLASSIFIER = "CLASSIFIER"
    LOCUS = "LOCUS"
    NON_MANUAL = "NON_MANUAL"
    LEXICAL_SELECTION = "LEXICAL_SELECTION"
    DISCOURSE = "DISCOURSE"
    PARAPHRASE = "PARAPHRASE"
    SPATIAL = "SPATIAL"
    MWE = "MWE"
    INFORMATION_STRUCTURE = "INFORMATION_STRUCTURE"


# ── Condición y acción ────────────────────────────────────────

class RuleCondition(BaseModel):
    """Condición evaluable de una regla."""
    field: str = Field(description="Campo del SemanticFrame evaluado (ej: 'sentence_type', 'polarity')")
    operator: str = Field(description="Operador: 'eq', 'neq', 'in', 'not_in', 'contains', 'exists', 'gt', 'lt'")
    value: Any = Field(description="Valor de comparación")
    description: Optional[str] = None


class RuleAction(BaseModel):
    """Acción que ejecuta una regla cuando se cumple la condición."""
    action_type: str = Field(description=(
        "'reorder', 'insert_gloss', 'remove_gloss', 'replace_gloss', "
        "'set_non_manual', 'assign_locus', 'set_field', "
        "'apply_paraphrase', 'resolve_prodrop', 'set_negation_scope'"
    ))
    parameters: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None


# ── Regla gramatical ──────────────────────────────────────────

class GrammarRule(BaseModel):
    """
    Regla gramatical LSEC versionada con trazabilidad completa.

    No se ejecuta directamente: el ``RuleEngine`` evalúa sus condiciones
    y aplica sus acciones con registro de procedencia.
    """
    rule_id: str = Field(description="Identificador único (ej: 'LSEC_NEGATION_POSTVERBAL')")
    name: str = Field(description="Nombre legible de la regla")
    description: str = Field(default="")
    grammar_version: str = Field(default="0.1.0")
    priority: int = Field(default=50, ge=0, le=100, description="0 = más alta, 100 = más baja")
    scope: RuleScope = Field(default=RuleScope.WORD_ORDER)
    conditions: List[RuleCondition] = Field(default_factory=list)
    actions: List[RuleAction] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list, description="IDs de reglas que nunca deben co-activarse")
    incompatible_rules: List[str] = Field(default_factory=list)
    required_evidence: List[str] = Field(default_factory=list, description="Evidencia requerida (ej: 'spacy_dep', 'lexicon_entry')")
    validation_status: RuleValidationStatus = Field(default=RuleValidationStatus.PROVISIONAL)
    confidence_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    counterexamples: List[Dict[str, Any]] = Field(default_factory=list)
    test_ids: List[str] = Field(default_factory=list)

    @property
    def is_executable(self) -> bool:
        """Una regla solo puede ejecutarse si no está en DRAFT, REJECTED o DEPRECATED."""
        return self.validation_status not in (
            RuleValidationStatus.DRAFT,
            RuleValidationStatus.REJECTED,
        )

    @property
    def reduces_confidence(self) -> bool:
        return self.validation_status == RuleValidationStatus.PROVISIONAL

