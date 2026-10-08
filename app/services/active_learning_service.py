"""
Servicio de Aprendizaje Activo y Muestreo de Incertidumbre (Fase 9).

Identifica los ejemplos más informativos y prioritarios para revisión humana:
1. Ejemplos con baja confianza o alta entropía.
2. Conflictos entre reglas deterministas y predicciones del modelo.
3. Vocabulario o conceptos desconocidos (OOV).
4. Estructuras sintácticas o modalidades poco representadas.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.dataset_schemas import AnnotationStatus, LSECDatasetItem
from app.core.schemas import ExecutionStatus, GlossOutput, ValidationSeverity


class ActiveLearningPriority(BaseModel):
    example_id: str
    source_text: str
    uncertainty_score: float = Field(ge=0.0, le=1.0)
    priority_level: str = "MEDIUM"  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    sampling_reasons: List[str] = Field(default_factory=list)
    suggested_action: str = "SEND_TO_NATIVE_REVIEW"


class ActiveLearningService:
    """Motor de selección activa de muestras informativas para revisión humana."""

    @classmethod
    def calculate_uncertainty_score(cls, output: GlossOutput) -> Tuple[float, List[str]]:
        """
        Calcula el puntaje de incertidumbre (0.0 a 1.0) combinando:
        - Confianza lingüística global.
        - Presencia de advertencias o errores.
        - Frecuencia de paráfrasis o conceptos inferidos.
        - Estados de revisión requerida.
        """
        reasons: List[str] = []
        c_global = output.validation_metadata.overall_linguistic_confidence
        
        # 1. Base por confianza lingüística inversa
        uncertainty = 1.0 - c_global

        # 2. Penalización por estado de ejecución
        if output.execution_status == ExecutionStatus.BLOCKED:
            uncertainty = max(uncertainty, 0.95)
            reasons.append("Ejecución bloqueada por inconsistencia estructural.")
        elif output.execution_status == ExecutionStatus.REVIEW_REQUIRED:
            uncertainty = max(uncertainty, 0.70)
            reasons.append("Revisión nativa o acústica requerida.")

        # 3. Advertencias de validación
        warn_count = len(output.warnings)
        if warn_count > 0:
            uncertainty = min(uncertainty + (warn_count * 0.1), 1.0)
            reasons.append(f"{warn_count} advertencias de validación detectadas.")

        # 4. Paráfrasis conceptuales
        paraphrases = [g for g in output.glosses if g.lexical_strategy == "semantic_paraphrase"]
        if paraphrases:
            uncertainty = min(uncertainty + 0.15, 1.0)
            reasons.append(f"{len(paraphrases)} paráfrasis conceptuales requieren validación de naturalidad.")

        # 5. Elementos no resueltos
        if output.unresolved_items:
            uncertainty = min(uncertainty + 0.20, 1.0)
            reasons.append(f"{len(output.unresolved_items)} elementos no resueltos o acústicamente dudosos.")

        # 6. Señas léxicas ausentes del Diccionario Oficial LSEC (CONADIS): prioridad de validación sorda
        unverified = [
            g for g in output.glosses
            if getattr(getattr(g, "dictionary_metadata", None), "status", None) == "NO_VERIFICADO"
        ]
        if unverified:
            uncertainty = min(uncertainty + min(0.10 + 0.05 * len(unverified), 0.30), 1.0)
            sample = ", ".join(g.gloss for g in unverified[:5])
            reasons.append(
                f"{len(unverified)} glosas léxicas no figuran en el Diccionario Oficial LSEC (CONADIS): {sample}."
            )

        uncertainty_score = round(max(0.0, min(uncertainty, 1.0)), 3)
        return uncertainty_score, reasons

    @classmethod
    def prioritize_batch(
        cls,
        unannotated_outputs: List[GlossOutput],
        top_k: int = 50,
        min_threshold: float = 0.30,
    ) -> List[ActiveLearningPriority]:
        """Prioriza y filtra los ejemplos no anotados más informativos para la cola de revisión."""
        prioritized: List[ActiveLearningPriority] = []

        for out in unannotated_outputs:
            score, reasons = cls.calculate_uncertainty_score(out)
            if score >= min_threshold:
                if score >= 0.80:
                    level = "CRITICAL"
                elif score >= 0.60:
                    level = "HIGH"
                elif score >= 0.40:
                    level = "MEDIUM"
                else:
                    level = "LOW"

                prioritized.append(
                    ActiveLearningPriority(
                        example_id=str(out.session_id),
                        source_text=out.original_text,
                        uncertainty_score=score,
                        priority_level=level,
                        sampling_reasons=reasons,
                        suggested_action="SEND_TO_NATIVE_REVIEW",
                    )
                )

        # Ordenar de mayor a menor incertidumbre (los más informativos primero)
        prioritized.sort(key=lambda x: x.uncertainty_score, reverse=True)
        return prioritized[:top_k]
