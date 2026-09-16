"""
Esquemas de Datos y Metadatos para el Corpus LSEC (Fase 3).

Define la estructura formal para el almacenamiento unificado de texto, semántica,
glosas, video, límites temporales de señas, anotaciones y trazabilidad de revisión humana.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field, field_validator, model_validator


class AnnotationStatus(str, Enum):
    UNANNOTATED = "UNANNOTATED"
    MACHINE_PROPOSED = "MACHINE_PROPOSED"
    HUMAN_CORRECTED = "HUMAN_CORRECTED"
    SECOND_REVIEW_REQUIRED = "SECOND_REVIEW_REQUIRED"
    NATIVE_VALIDATED = "NATIVE_VALIDATED"
    REJECTED = "REJECTED"
    DISPUTED = "DISPUTED"
    ARCHIVED = "ARCHIVED"


class DatasetSplit(str, Enum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"
    FROZEN_TEST = "FROZEN_TEST"
    UNASSIGNED = "UNASSIGNED"


class ConsentStatus(str, Enum):
    EXPLICIT_CONSENT_GRANTED = "EXPLICIT_CONSENT_GRANTED"
    RESTRICTED_RESEARCH_ONLY = "RESTRICTED_RESEARCH_ONLY"
    NO_CONSENT = "NO_CONSENT"
    REVOKED = "REVOKED"


class DisagreementStatus(str, Enum):
    NONE = "NONE"
    PENDING_RESOLUTION = "PENDING_RESOLUTION"
    RESOLVED_BY_CONSENSUS = "RESOLVED_BY_CONSENSUS"
    RESOLVED_BY_THIRD_REVIEWER = "RESOLVED_BY_THIRD_REVIEWER"
    UNRESOLVED_DISPUTED = "UNRESOLVED_DISPUTED"


class SignBoundary(BaseModel):
    sign_id: str
    gloss: str
    start_ms: int
    end_ms: int
    confidence: float = 1.0
    notes: Optional[str] = None

    @field_validator("end_ms")
    @classmethod
    def validate_end_after_start(cls, v: int, info) -> int:
        start = info.data.get("start_ms", 0)
        if v < start:
            raise ValueError(f"end_ms ({v}) debe ser mayor o igual a start_ms ({start}).")
        return v


class VideoMetadata(BaseModel):
    video_id: str
    file_path: Optional[str] = None
    file_hash_sha256: str
    frame_rate: float = Field(default=30.0, ge=1.0)
    resolution: str = Field(default="1920x1080")
    duration_ms: int = Field(ge=0)
    recording_conditions: str = Field(default="controlled_studio")
    prompted_or_spontaneous: str = Field(default="prompted")


class AnnotationAuditEntry(BaseModel):
    audit_id: str
    timestamp: str
    reviewer_id_anonymized: str
    field_changed: str
    previous_value: Any
    new_value: Any
    reason: str
    guide_version: str = "1.0"
    time_spent_seconds: Optional[int] = None
    reviewer_confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class LSECDatasetItem(BaseModel):
    """
    Elemento canónico del conjunto de datos LSEC (Fase 3).
    Garantiza trazabilidad completa entre texto, semántica, video, anotación y revisión.
    """
    example_id: str
    source_language: str = "es"
    target_language: str = "lsec"
    
    # Texto
    source_text: str
    normalized_text: str
    source_tokens: List[str] = Field(default_factory=list)
    source_ranges: List[List[int]] = Field(default_factory=list)
    
    # Semántica y Lingüística
    modality: str = "declarative"
    polarity: str = "positive"
    predicates: List[Dict[str, Any]] = Field(default_factory=list)
    participants: List[Dict[str, Any]] = Field(default_factory=list)
    semantic_roles: List[str] = Field(default_factory=list)
    operators: List[Dict[str, Any]] = Field(default_factory=list)
    temporal_modifiers: List[Dict[str, Any]] = Field(default_factory=list)
    source_concepts: List[str] = Field(default_factory=list)
    
    # Glosas LSEC y Alineación
    validated_glosses: List[str] = Field(default_factory=list)
    gloss_order: List[int] = Field(default_factory=list)
    gloss_alignments: List[Dict[str, Any]] = Field(default_factory=list)
    spatial_referents: List[Dict[str, Any]] = Field(default_factory=list)
    spatial_operations: List[Dict[str, Any]] = Field(default_factory=list)
    non_manual_spans: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Video y Temporización
    video_id: Optional[str] = None
    frame_rate: Optional[float] = 30.0
    resolution: Optional[str] = "1920x1080"
    duration_ms: Optional[int] = 0
    sign_boundaries: List[SignBoundary] = Field(default_factory=list)
    
    # Signante y Condiciones
    signer_id_anonymized: Optional[str] = None
    dominant_hand: Optional[str] = None
    regional_variant: Optional[str] = "Pichincha"
    recording_conditions: Optional[str] = "controlled_lighting"
    prompted_or_spontaneous: Optional[str] = "prompted"
    
    # Estado de Anotación y Revisión
    annotation_status: AnnotationStatus = AnnotationStatus.UNANNOTATED
    annotation_version: str = "1.0"
    reviewer_ids_anonymized: List[str] = Field(default_factory=list)
    native_validation_status: bool = False
    disagreement_status: DisagreementStatus = DisagreementStatus.NONE
    
    # Ética, Consentimiento y Licencia
    consent_status: ConsentStatus = ConsentStatus.EXPLICIT_CONSENT_GRANTED
    license: str = "CC-BY-NC-SA-4.0"
    
    # Partición y Versionado
    dataset_split: DatasetSplit = DatasetSplit.UNASSIGNED
    data_version: str = "1.0.0"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    audit_history: List[AnnotationAuditEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dataset_invariants(self) -> LSECDatasetItem:
        """Aplica las reglas obligatorias de contención, protección contra contaminación y consentimiento."""
        # 1. Regla: Sin consentimiento no puede pertenecer al dataset utilizable
        if self.consent_status in (ConsentStatus.NO_CONSENT, ConsentStatus.REVOKED):
            if self.dataset_split in (DatasetSplit.TRAIN, DatasetSplit.VALIDATION, DatasetSplit.TEST, DatasetSplit.FROZEN_TEST):
                raise ValueError(
                    f"El ejemplo '{self.example_id}' tiene consent_status='{self.consent_status}' y no puede asignarse a una partición de dataset."
                )

        # 2. Regla: Ejemplos MACHINE_PROPOSED no pueden entrar a TRAIN/TEST como ground truth
        if self.annotation_status == AnnotationStatus.MACHINE_PROPOSED:
            if self.dataset_split in (DatasetSplit.TRAIN, DatasetSplit.TEST, DatasetSplit.FROZEN_TEST):
                raise ValueError(
                    f"El ejemplo '{self.example_id}' está en estado MACHINE_PROPOSED y no puede usarse como etiqueta de referencia en {self.dataset_split}."
                )

        # 3. Regla: Ejemplos DISPUTED o REJECTED no pueden usarse para entrenamiento
        if self.annotation_status in (AnnotationStatus.DISPUTED, AnnotationStatus.REJECTED):
            if self.dataset_split == DatasetSplit.TRAIN:
                raise ValueError(
                    f"El ejemplo '{self.example_id}' en estado '{self.annotation_status}' está prohibido para entrenamiento."
                )

        # 4. Regla: NATIVE_VALIDATED requiere native_validation_status = True y revisores registrados
        if self.annotation_status == AnnotationStatus.NATIVE_VALIDATED:
            if not self.native_validation_status:
                raise ValueError(
                    f"El ejemplo '{self.example_id}' marcado NATIVE_VALIDATED debe tener native_validation_status=True."
                )
            if not self.reviewer_ids_anonymized:
                raise ValueError(
                    f"El ejemplo '{self.example_id}' marcado NATIVE_VALIDATED debe tener al menos un identificador de revisor en reviewer_ids_anonymized."
                )

        return self
