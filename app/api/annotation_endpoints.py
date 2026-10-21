"""
Endpoints REST para Gestión de Anotaciones, Dataset y MLOps (Fases 3, 4, 9 y 10).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.dataset_schemas import (
    AnnotationAuditEntry,
    AnnotationStatus,
    ConsentStatus,
    DatasetSplit,
    LSECDatasetItem,
)
from app.services.active_learning_service import ActiveLearningPriority, ActiveLearningService
from app.services.dataset_validator import DatasetValidator
from app.services.mlops_pipeline import BenchmarkMetrics, MLOpsPipeline
from app.services.nlp_service import LSECTranslatorService
from app.services.storage_service import LocalStorageService

annotation_router = APIRouter(prefix="/api/v1", tags=["LSEC Dataset & Annotation Platform"])

CORPUS_PATH = Path("data/corpus/pilot_corpus_lsec.json")
_storage_service: Optional[LocalStorageService] = None


def set_annotation_storage(storage: Optional[LocalStorageService]) -> None:
    """Inyecta la persistencia local para conservar anotaciones entre reinicios."""
    global _storage_service
    _storage_service = storage


def _load_corpus_items() -> List[LSECDatasetItem]:
    if not CORPUS_PATH.exists():
        return []
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return [LSECDatasetItem(**it) for it in raw]


class AnnotationSubmissionRequest(BaseModel):
    example_id: str
    reviewer_id_anonymized: str
    action: str = Field(description="'APPROVE', 'REJECT', 'MODIFY', 'DISPUTE'")
    validated_glosses: Optional[List[str]] = None
    gloss_order: Optional[List[int]] = None
    change_reason: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


@annotation_router.get("/dataset/manifest")
async def get_dataset_manifest(version: str = "1.0.0") -> Dict[str, Any]:
    """Retorna el manifiesto oficial del dataset y el reporte de control de fugas."""
    items = _load_corpus_items()
    manifest = DatasetValidator.generate_manifest(items, dataset_version=version)
    leakage_report = DatasetValidator.validate_split_leakage(items)
    return {
        "manifest": manifest,
        "leakage_audit": leakage_report,
    }


@annotation_router.post("/dataset/validate-item")
async def validate_dataset_item(item: LSECDatasetItem) -> Dict[str, Any]:
    """Valida un ejemplo propuesto según las reglas de integridad y privacidad del esquema."""
    errors = DatasetValidator.validate_item(item)
    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "example_id": item.example_id,
        "annotation_status": item.annotation_status,
        "dataset_split": item.dataset_split,
    }


@annotation_router.get("/dataset/export")
async def export_validated_dataset(split: Optional[DatasetSplit] = None) -> List[Dict[str, Any]]:
    """Exporta exclusivamente ejemplos en estado NATIVE_VALIDATED para entrenamiento o evaluación."""
    items = await _load_persisted_corpus_items()
    filtered = [
        it for it in items
        if it.annotation_status == AnnotationStatus.NATIVE_VALIDATED
        and it.consent_status == ConsentStatus.EXPLICIT_CONSENT_GRANTED
    ]
    if split:
        filtered = [it for it in filtered if it.dataset_split == split]
    return [it.model_dump() for it in filtered]


@annotation_router.post("/annotations/submit")
async def submit_annotation_review(sub: AnnotationSubmissionRequest) -> Dict[str, Any]:
    """Registra una revisión humana con auditoría append-only sin sobrescritura destructiva."""
    items = await _load_persisted_corpus_items()
    target = next((it for it in items if it.example_id == sub.example_id), None)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ejemplo '{sub.example_id}' no encontrado en el corpus.",
        )

    timestamp_str = datetime.now(timezone.utc).isoformat()
    old_status = target.annotation_status
    old_glosses = target.validated_glosses

    # Actualizar estado y glosas según acción
    if sub.action == "APPROVE":
        target.annotation_status = AnnotationStatus.NATIVE_VALIDATED
        target.native_validation_status = True
        if sub.reviewer_id_anonymized not in target.reviewer_ids_anonymized:
            target.reviewer_ids_anonymized.append(sub.reviewer_id_anonymized)
    elif sub.action == "MODIFY":
        target.annotation_status = AnnotationStatus.HUMAN_CORRECTED
        if sub.validated_glosses is not None:
            target.validated_glosses = sub.validated_glosses
        if sub.gloss_order is not None:
            target.gloss_order = sub.gloss_order
    elif sub.action == "DISPUTE":
        target.annotation_status = AnnotationStatus.DISPUTED
    elif sub.action == "REJECT":
        target.annotation_status = AnnotationStatus.REJECTED

    # Agregar entrada inmutable al historial de auditoría
    audit_entry = AnnotationAuditEntry(
        audit_id=f"audit_{uuid4().hex[:8]}",
        timestamp=timestamp_str,
        reviewer_id_anonymized=sub.reviewer_id_anonymized,
        field_changed="annotation_status_and_glosses",
        previous_value={"status": old_status, "glosses": old_glosses},
        new_value={"status": target.annotation_status, "glosses": target.validated_glosses},
        reason=sub.change_reason,
        guide_version=target.annotation_version,
        reviewer_confidence=sub.confidence,
    )
    target.audit_history.append(audit_entry)
    target.updated_at = timestamp_str
    if _storage_service is not None:
        await _storage_service.save_annotation_snapshot(target.model_dump(mode="json"))

    return {
        "status": "SUCCESS",
        "example_id": target.example_id,
        "new_annotation_status": target.annotation_status,
        "audit_id": audit_entry.audit_id,
    }


async def _load_persisted_corpus_items() -> List[LSECDatasetItem]:
    """Carga el corpus base y aplica snapshots locales de anotaciones, si existen."""
    items = _load_corpus_items()
    if _storage_service is None:
        return items
    persisted_items = []
    for item in items:
        snapshot = await _storage_service.get_annotation_snapshot(item.example_id)
        persisted_items.append(LSECDatasetItem(**snapshot) if snapshot else item)
    return persisted_items


@annotation_router.get("/annotations/queue")
async def get_active_learning_queue(top_k: int = Query(default=20, ge=1, le=100)) -> List[ActiveLearningPriority]:
    """Retorna la cola de revisión priorizada por el motor de aprendizaje activo a partir de las muestras del corpus."""
    items = await _load_persisted_corpus_items()
    if not items:
        return []

    service = LSECTranslatorService()
    outputs = []
    for it in items:
        out = await service.translate_to_gloss(it.source_text, mode="detailed")
        out.session_id = it.example_id
        outputs.append(out)

    queue = ActiveLearningService.prioritize_batch(outputs, top_k=top_k, min_threshold=0.0)
    return queue


@annotation_router.post("/mlops/benchmark")
async def run_frozen_test_benchmark() -> BenchmarkMetrics:
    """Ejecuta la evaluación del pipeline contra el Frozen Test Set y emite el dictamen de la compuerta MLOps."""
    service = LSECTranslatorService()
    items = _load_corpus_items()
    frozen_items = [it for it in items if it.dataset_split == DatasetSplit.FROZEN_TEST]
    if not frozen_items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontraron ejemplos en la partición FROZEN_TEST.",
        )

    pairs = []
    for it in frozen_items:
        pred = await service.translate_to_gloss(it.source_text, mode="detailed")
        pairs.append((it, pred))

    metrics = MLOpsPipeline.evaluate_against_frozen_test(pairs, baseline_f1=0.80)
    return metrics
