"""
Suite de Pruebas para Esquemas de Datos, Protocolo de Anotación y Detección de Fugas (Fases 2, 3 y 6).
"""

import pytest
from app.core.dataset_schemas import (
    AnnotationAuditEntry,
    AnnotationStatus,
    ConsentStatus,
    DatasetSplit,
    DisagreementStatus,
    LSECDatasetItem,
    SignBoundary,
    VideoMetadata,
)
from app.services.dataset_validator import DatasetValidator


class TestDatasetSchemasAndValidation:
    """Pruebas unitarias de las reglas del esquema de datos y control de contaminación."""

    def test_valid_native_validated_item(self):
        """Un elemento completo y validado por personas sordas pasa el esquema."""
        item = LSECDatasetItem(
            example_id="ex_001",
            source_text="¿Tú comes manzana?",
            normalized_text="¿Tú comes manzana?",
            source_tokens=["¿", "Tú", "comes", "manzana", "?"],
            modality="interrogative_yn",
            polarity="positive",
            validated_glosses=["PRO2", "MANZANA", "COMER"],
            gloss_order=[1, 2, 3],
            annotation_status=AnnotationStatus.NATIVE_VALIDATED,
            native_validation_status=True,
            reviewer_ids_anonymized=["rev_sordo_01", "rev_ling_02"],
            consent_status=ConsentStatus.EXPLICIT_CONSENT_GRANTED,
            dataset_split=DatasetSplit.TRAIN,
            signer_id_anonymized="signer_ec_042",
            regional_variant="Pichincha",
            sign_boundaries=[
                SignBoundary(sign_id="s1", gloss="PRO2", start_ms=0, end_ms=450),
                SignBoundary(sign_id="s2", gloss="MANZANA", start_ms=450, end_ms=1100),
                SignBoundary(sign_id="s3", gloss="COMER", start_ms=1100, end_ms=1800),
            ],
        )
        assert item.example_id == "ex_001"
        assert item.annotation_status == AnnotationStatus.NATIVE_VALIDATED
        errors = DatasetValidator.validate_item(item)
        assert len(errors) == 0

    def test_rejection_of_unconsented_data_in_splits(self):
        """Un video o ejemplo sin consentimiento (NO_CONSENT / REVOKED) no puede entrar al dataset."""
        with pytest.raises(ValueError, match="no puede asignarse a una partición"):
            LSECDatasetItem(
                example_id="ex_unconsented",
                source_text="Hola",
                normalized_text="Hola",
                consent_status=ConsentStatus.NO_CONSENT,
                dataset_split=DatasetSplit.TRAIN,
            )

    def test_rejection_of_machine_proposed_as_ground_truth(self):
        """MACHINE_PROPOSED no puede asignarse a particiones de entrenamiento o prueba."""
        with pytest.raises(ValueError, match="MACHINE_PROPOSED y no puede usarse como etiqueta de referencia"):
            LSECDatasetItem(
                example_id="ex_machine",
                source_text="Yo como pan",
                normalized_text="Yo como pan",
                annotation_status=AnnotationStatus.MACHINE_PROPOSED,
                dataset_split=DatasetSplit.TRAIN,
            )

    def test_rejection_of_disputed_data_in_train(self):
        """Ejemplos DISPUTED o REJECTED no pueden ingresar al split de entrenamiento."""
        with pytest.raises(ValueError, match="está prohibido para entrenamiento"):
            LSECDatasetItem(
                example_id="ex_disputed",
                source_text="Texto dudoso",
                normalized_text="Texto dudoso",
                annotation_status=AnnotationStatus.DISPUTED,
                dataset_split=DatasetSplit.TRAIN,
            )

    def test_rejection_of_native_validated_without_reviewers(self):
        """NATIVE_VALIDATED requiere native_validation_status=True y al menos un revisor registrado."""
        with pytest.raises(ValueError, match="debe tener al menos un identificador de revisor"):
            LSECDatasetItem(
                example_id="ex_invalid_native",
                source_text="Texto",
                normalized_text="Texto",
                annotation_status=AnnotationStatus.NATIVE_VALIDATED,
                native_validation_status=True,
                reviewer_ids_anonymized=[],  # Vacío
                dataset_split=DatasetSplit.TRAIN,
            )

    def test_leakage_detection_train_test_overlap(self):
        """DatasetValidator detecta si una misma frase aparece en TRAIN y en TEST."""
        item_train = LSECDatasetItem(
            example_id="ex_tr_1",
            source_text="¿Qué comes?",
            normalized_text="¿Qué comes?",
            annotation_status=AnnotationStatus.NATIVE_VALIDATED,
            native_validation_status=True,
            reviewer_ids_anonymized=["rev_01"],
            dataset_split=DatasetSplit.TRAIN,
            signer_id_anonymized="signer_01",
        )
        item_test_leak = LSECDatasetItem(
            example_id="ex_ts_1",
            source_text="¿Qué comes?",
            normalized_text="¿Qué comes?",
            annotation_status=AnnotationStatus.NATIVE_VALIDATED,
            native_validation_status=True,
            reviewer_ids_anonymized=["rev_02"],
            dataset_split=DatasetSplit.TEST,
            signer_id_anonymized="signer_02",
        )
        report = DatasetValidator.validate_split_leakage([item_train, item_test_leak])
        assert report["has_leakage"] is True
        assert report["leakage_count"] == 1
        assert report["findings"][0]["type"] == "TEXT_LEAKAGE_TRAIN_TEST"

    def test_manifest_generation(self):
        """Generación correcta de estadísticas del manifiesto del corpus."""
        item1 = LSECDatasetItem(
            example_id="ex_1",
            source_text="Frase uno",
            normalized_text="Frase uno",
            annotation_status=AnnotationStatus.NATIVE_VALIDATED,
            native_validation_status=True,
            reviewer_ids_anonymized=["rev_01"],
            dataset_split=DatasetSplit.TRAIN,
            regional_variant="Pichincha",
        )
        item2 = LSECDatasetItem(
            example_id="ex_2",
            source_text="Frase dos",
            normalized_text="Frase dos",
            annotation_status=AnnotationStatus.NATIVE_VALIDATED,
            native_validation_status=True,
            reviewer_ids_anonymized=["rev_01"],
            dataset_split=DatasetSplit.VALIDATION,
            regional_variant="Guayas",
        )
        manifest = DatasetValidator.generate_manifest([item1, item2], dataset_version="1.0.0")
        assert manifest["total_examples"] == 2
        assert manifest["splits_distribution"]["TRAIN"] == 1
        assert manifest["splits_distribution"]["VALIDATION"] == 1
        assert "Pichincha" in manifest["regional_variants"]
        assert "Guayas" in manifest["regional_variants"]
