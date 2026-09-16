"""
Pipeline MLOps y Evaluación de Modelos contra Frozen Test Set (Fase 10).

Controla el ciclo de vida de versiones de modelos, calcula métricas de evaluación objetivas
y aplica la puerta de calidad estricta antes de autorizar cualquier despliegue.
"""

from __future__ import annotations

import difflib
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.core.dataset_schemas import LSECDatasetItem
from app.core.schemas import ExecutionStatus, GlossOutput


class BenchmarkMetrics(BaseModel):
    total_test_samples: int
    exact_match_ratio: float = Field(ge=0.0, le=1.0)
    average_gloss_f1: float = Field(ge=0.0, le=1.0)
    concept_recall: float = Field(ge=0.0, le=1.0)
    average_edit_distance: float
    unsupported_concepts_count: int
    blocking_errors_count: int
    deployment_gate_decision: str  # "PASS", "PASS_WITH_LIMITATIONS", "FAIL"
    gate_justification: str


class MLOpsPipeline:
    """Motor de evaluación y compuerta de despliegue para modelos LSEC."""

    @classmethod
    def compute_gloss_f1(cls, predicted_glosses: List[str], ground_truth_glosses: List[str]) -> float:
        """Calcula el F1-Score a nivel de tokens de glosas."""
        p_set = [g.upper().strip() for g in predicted_glosses]
        g_set = [g.upper().strip() for g in ground_truth_glosses]

        if not p_set and not g_set:
            return 1.0
        if not p_set or not g_set:
            return 0.0

        common = 0
        temp_g = list(g_set)
        for pg in p_set:
            if pg in temp_g:
                common += 1
                temp_g.remove(pg)

        precision = common / len(p_set)
        recall = common / len(g_set)

        if precision + recall == 0:
            return 0.0
        return round(2 * (precision * recall) / (precision + recall), 4)

    @classmethod
    def compute_edit_distance(cls, predicted_glosses: List[str], ground_truth_glosses: List[str]) -> int:
        """Calcula la distancia de edición de Levenshtein a nivel de secuencia de glosas."""
        matcher = difflib.SequenceMatcher(None, predicted_glosses, ground_truth_glosses)
        # Operaciones necesarias para transformar predicted en ground_truth
        ops = matcher.get_opcodes()
        distance = 0
        for tag, i1, i2, j1, j2 in ops:
            if tag == "replace":
                distance += max(i2 - i1, j2 - j1)
            elif tag == "delete":
                distance += (i2 - i1)
            elif tag == "insert":
                distance += (j2 - j1)
        return distance

    @classmethod
    def evaluate_against_frozen_test(
        cls,
        model_predictions: List[Tuple[LSECDatasetItem, GlossOutput]],
        baseline_f1: float = 0.85,
    ) -> BenchmarkMetrics:
        """
        Evalúa un lote de predicciones de un modelo candidato contra los datos del Frozen Test Set
        y emite la decisión de la puerta de calidad MLOps.
        """
        total = len(model_predictions)
        if total == 0:
            return BenchmarkMetrics(
                total_test_samples=0,
                exact_match_ratio=0.0,
                average_gloss_f1=0.0,
                concept_recall=0.0,
                average_edit_distance=0.0,
                unsupported_concepts_count=0,
                blocking_errors_count=0,
                deployment_gate_decision="FAIL",
                gate_justification="El conjunto de evaluación está vacío.",
            )

        exact_matches = 0
        total_f1 = 0.0
        total_dist = 0
        total_unsupported = 0
        total_blocking = 0
        total_concept_recall = 0.0

        for item, pred in model_predictions:
            pred_glosses = [g.gloss.upper().strip() for g in pred.glosses]
            target_glosses = [g.upper().strip() for g in item.validated_glosses]

            if pred_glosses == target_glosses:
                exact_matches += 1

            f1 = cls.compute_gloss_f1(pred_glosses, target_glosses)
            total_f1 += f1

            dist = cls.compute_edit_distance(pred_glosses, target_glosses)
            total_dist += dist

            # Concept Recall
            if pred.translation_plans:
                plan_recalls = [pl.source_recall for pl in pred.translation_plans]
                total_concept_recall += sum(plan_recalls) / len(plan_recalls)
            else:
                total_concept_recall += 1.0

            # Contar conceptos no soportados
            for pl in pred.translation_plans:
                total_unsupported += len(pl.unsupported_realized_concepts)

            # Contar errores bloqueantes
            if pred.execution_status == ExecutionStatus.BLOCKED:
                total_blocking += 1

        avg_f1 = round(total_f1 / total, 4)
        avg_rec = round(total_concept_recall / total, 4)
        avg_dist = round(total_dist / total, 2)
        em_ratio = round(exact_matches / total, 4)

        # Reglas de la Puerta de Calidad MLOps
        if total_blocking > 0:
            decision = "FAIL"
            justification = f"Rechazado: {total_blocking} ejemplos del Frozen Test generaron errores bloqueantes (BLOCKED)."
        elif total_unsupported > 0:
            decision = "FAIL"
            justification = f"Rechazado: {total_unsupported} conceptos realizados sin evidencia ni soporte trazable."
        elif avg_f1 < baseline_f1:
            decision = "FAIL"
            justification = f"Rechazado: F1 promedio ({avg_f1}) inferior a la línea base requerida ({baseline_f1})."
        elif em_ratio >= 0.85 and avg_f1 >= 0.90:
            decision = "PASS"
            justification = f"Aprobado: F1={avg_f1}, ExactMatch={em_ratio}, 0 errores bloqueantes y 0 conceptos no soportados."
        else:
            decision = "PASS_WITH_LIMITATIONS"
            justification = f"Aprobado con limitaciones: F1={avg_f1}, ExactMatch={em_ratio}. Requiere revisión nativa en producción."

        return BenchmarkMetrics(
            total_test_samples=total,
            exact_match_ratio=em_ratio,
            average_gloss_f1=avg_f1,
            concept_recall=avg_rec,
            average_edit_distance=avg_dist,
            unsupported_concepts_count=total_unsupported,
            blocking_errors_count=total_blocking,
            deployment_gate_decision=decision,
            gate_justification=justification,
        )
