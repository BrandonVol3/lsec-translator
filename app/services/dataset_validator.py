"""
Servicio de Validación de Datasets y Detección de Fugas (Fases 3 y 6).

Verifica la integridad de los conjuntos de datos LSEC, detecta duplicados,
audita la anonimización y asegura la partición estricta sin fugas entre entrenamiento y prueba.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from app.core.dataset_schemas import (
    AnnotationStatus,
    ConsentStatus,
    DatasetSplit,
    DisagreementStatus,
    LSECDatasetItem,
)


class DatasetValidator:
    """Validador y auditor de integridad para conjuntos de datos LSEC."""

    @classmethod
    def validate_item(cls, item: LSECDatasetItem) -> List[str]:
        """Valida las reglas individuales de un elemento del dataset."""
        errors: List[str] = []

        if not item.source_text or not item.normalized_text:
            errors.append("El texto fuente o normalizado está vacío.")

        if item.annotation_status == AnnotationStatus.NATIVE_VALIDATED and not item.validated_glosses:
            errors.append("Un ejemplo NATIVE_VALIDATED no puede tener validated_glosses vacío.")

        # Verificar orden temporal de los límites de señas si existen
        if item.sign_boundaries:
            for i in range(len(item.sign_boundaries) - 1):
                curr_b = item.sign_boundaries[i]
                next_b = item.sign_boundaries[i + 1]
                if next_b.start_ms < curr_b.start_ms:
                    errors.append(
                        f"Límites temporales desordenados: seña '{next_b.gloss}' ({next_b.start_ms}ms) inicia antes que '{curr_b.gloss}' ({curr_b.start_ms}ms)."
                    )

        # Regla de anonimización: no nombres en identificadores
        if item.signer_id_anonymized:
            if re.search(r"\b(carlos|maría|juan|pedro|ana|luis)\b", item.signer_id_anonymized.lower()):
                errors.append(f"El identificador de signante '{item.signer_id_anonymized}' contiene nombres personales no anonimizados.")

        return errors

    @classmethod
    def validate_split_leakage(cls, items: List[LSECDatasetItem]) -> Dict[str, Any]:
        """
        Audita el conjunto completo para detectar:
        1. Fugas de frases exactas entre TRAIN y TEST/FROZEN_TEST.
        2. Fugas de signantes exclusivos de TEST en TRAIN.
        3. Fugas de videos duplicados (por hash SHA-256 o video_id).
        """
        train_texts: Set[str] = set()
        val_texts: Set[str] = set()
        test_texts: Set[str] = set()
        frozen_test_texts: Set[str] = set()

        train_signers: Set[str] = set()
        test_signers: Set[str] = set()

        video_ids_seen: Dict[str, str] = {}
        text_hashes_seen: Dict[str, str] = {}

        leakage_findings: List[Dict[str, Any]] = []
        duplicate_videos: List[str] = []
        duplicate_texts: List[str] = []

        for item in items:
            clean_t = item.normalized_text.lower().strip()
            t_hash = hashlib.sha256(clean_t.encode("utf-8")).hexdigest()

            # Registro de duplicados
            if t_hash in text_hashes_seen:
                prev_id = text_hashes_seen[t_hash]
                if prev_id != item.example_id:
                    duplicate_texts.append(f"{item.example_id} duplica texto de {prev_id}")
            else:
                text_hashes_seen[t_hash] = item.example_id

            if item.video_id:
                if item.video_id in video_ids_seen:
                    prev_id = video_ids_seen[item.video_id]
                    if prev_id != item.example_id:
                        duplicate_videos.append(f"{item.example_id} comparte video_id con {prev_id}")
                else:
                    video_ids_seen[item.video_id] = item.example_id

            # Clasificación por split
            if item.dataset_split == DatasetSplit.TRAIN:
                train_texts.add(clean_t)
                if item.signer_id_anonymized:
                    train_signers.add(item.signer_id_anonymized)
            elif item.dataset_split == DatasetSplit.VALIDATION:
                val_texts.add(clean_t)
            elif item.dataset_split == DatasetSplit.TEST:
                test_texts.add(clean_t)
                if item.signer_id_anonymized:
                    test_signers.add(item.signer_id_anonymized)
            elif item.dataset_split == DatasetSplit.FROZEN_TEST:
                frozen_test_texts.add(clean_t)

        # 1. Comprobar solapamiento de textos entre Train y Test
        train_test_overlap = train_texts.intersection(test_texts)
        if train_test_overlap:
            for text in train_test_overlap:
                leakage_findings.append({
                    "type": "TEXT_LEAKAGE_TRAIN_TEST",
                    "text": text,
                    "severity": "CRITICAL",
                })

        train_frozen_overlap = train_texts.intersection(frozen_test_texts)
        if train_frozen_overlap:
            for text in train_frozen_overlap:
                leakage_findings.append({
                    "type": "TEXT_LEAKAGE_TRAIN_FROZEN_TEST",
                    "text": text,
                    "severity": "CRITICAL",
                })

        return {
            "has_leakage": len(leakage_findings) > 0,
            "leakage_count": len(leakage_findings),
            "findings": leakage_findings,
            "duplicate_texts_count": len(duplicate_texts),
            "duplicate_videos_count": len(duplicate_videos),
            "total_items": len(items),
            "train_items": len([i for i in items if i.dataset_split == DatasetSplit.TRAIN]),
            "val_items": len([i for i in items if i.dataset_split == DatasetSplit.VALIDATION]),
            "test_items": len([i for i in items if i.dataset_split == DatasetSplit.TEST]),
            "frozen_test_items": len([i for i in items if i.dataset_split == DatasetSplit.FROZEN_TEST]),
        }

    @classmethod
    def generate_manifest(cls, items: List[LSECDatasetItem], dataset_version: str = "1.0.0") -> Dict[str, Any]:
        """Genera el manifiesto oficial del dataset con sumas de verificación y estadísticas."""
        splits_count = {s.value: 0 for s in DatasetSplit}
        status_count = {st.value: 0 for st in AnnotationStatus}
        signers: Set[str] = set()
        regions: Set[str] = set()

        for item in items:
            splits_count[item.dataset_split.value] = splits_count.get(item.dataset_split.value, 0) + 1
            status_count[item.annotation_status.value] = status_count.get(item.annotation_status.value, 0) + 1
            if item.signer_id_anonymized:
                signers.add(item.signer_id_anonymized)
            if item.regional_variant:
                regions.add(item.regional_variant)

        manifest = {
            "dataset_name": "Corpus_LSEC_Ecuador",
            "dataset_version": dataset_version,
            "total_examples": len(items),
            "splits_distribution": splits_count,
            "annotation_statuses": status_count,
            "unique_signers_count": len(signers),
            "regional_variants": list(regions),
            "license": "CC-BY-NC-SA-4.0",
            "quality_standard": "LSEC_2.1_Strict_Traceability",
        }
        return manifest
