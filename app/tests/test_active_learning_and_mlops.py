"""
Suite de Pruebas para Aprendizaje Activo, Pipeline MLOps y Corpus Piloto (Fases 5, 9 y 10).
"""

import json
import pytest
from pathlib import Path

from app.core.dataset_schemas import DatasetSplit, LSECDatasetItem
from app.core.schemas import (
    ExecutionStatus,
    GlossItem,
    GlossOutput,
    ReviewStatus,
    TranslationPlan,
    ValidationMetadata,
)
from app.services.active_learning_service import ActiveLearningService
from app.services.dataset_validator import DatasetValidator
from app.services.mlops_pipeline import MLOpsPipeline
from app.services.nlp_service import LSECTranslatorService


class TestActiveLearningAndMLOps:
    """Pruebas de aprendizaje activo, compuertas de despliegue MLOps y dataset piloto."""

    def test_pilot_corpus_integrity_and_no_leakage(self):
        """El archivo data/corpus/pilot_corpus_lsec.json cumple con el esquema y no tiene fugas."""
        corpus_path = Path("data/corpus/pilot_corpus_lsec.json")
        assert corpus_path.exists(), "El archivo pilot_corpus_lsec.json debe existir."

        with open(corpus_path, "r", encoding="utf-8") as f:
            raw_items = json.load(f)

        items = [LSECDatasetItem(**raw) for raw in raw_items]
        assert len(items) >= 5

        # Validar cada ítem
        for it in items:
            errs = DatasetValidator.validate_item(it)
            assert len(errs) == 0, f"Errores en ítem {it.example_id}: {errs}"

        # Validar ausencia de fugas
        leakage_report = DatasetValidator.validate_split_leakage(items)
        assert leakage_report["has_leakage"] is False
        assert leakage_report["leakage_count"] == 0

    @pytest.mark.asyncio
    async def test_active_learning_uncertainty_and_prioritization(self):
        """ActiveLearningService prioriza ejemplos bloqueados o inciertos sobre ejemplos listos."""
        service = LSECTranslatorService()
        
        # Caso 1: Oración clara y correcta
        out_ready = await service.translate_to_gloss("¿Tú comes manzana?", mode="detailed")
        score_ready, _ = ActiveLearningService.calculate_uncertainty_score(out_ready)

        # Caso 2: Simular salida con estado de revisión requerida y advertencias
        out_review = await service.translate_to_gloss("¿Qué comes?", mode="detailed")
        out_review.execution_status = ExecutionStatus.REVIEW_REQUIRED
        score_review, _ = ActiveLearningService.calculate_uncertainty_score(out_review)

        # Caso 3: Simular salida bloqueada
        out_blocked = await service.translate_to_gloss("Yo no como carne", mode="detailed")
        out_blocked.execution_status = ExecutionStatus.BLOCKED
        score_blocked, _ = ActiveLearningService.calculate_uncertainty_score(out_blocked)

        assert score_blocked > score_ready
        assert score_blocked >= 0.80

        # Priorizar lote
        batch_prioritized = ActiveLearningService.prioritize_batch([out_ready, out_blocked, out_review], top_k=2)
        assert len(batch_prioritized) == 2
        assert batch_prioritized[0].priority_level in ("CRITICAL", "HIGH")

    def test_mlops_f1_and_edit_distance_computation(self):
        """MLOpsPipeline calcula con exactitud F1 y distancia de edición."""
        pred = ["PRO2", "MANZANA", "COMER"]
        target = ["PRO2", "MANZANA", "COMER"]
        f1_perfect = MLOpsPipeline.compute_gloss_f1(pred, target)
        dist_perfect = MLOpsPipeline.compute_edit_distance(pred, target)
        assert f1_perfect == 1.0
        assert dist_perfect == 0

        pred_diff = ["MANZANA", "COMER"]
        f1_diff = MLOpsPipeline.compute_gloss_f1(pred_diff, target)
        dist_diff = MLOpsPipeline.compute_edit_distance(pred_diff, target)
        assert f1_diff < 1.0
        assert dist_diff > 0

    @pytest.mark.asyncio
    async def test_mlops_frozen_test_evaluation_pass_gate(self):
        """Evaluación contra Frozen Test aprueba (PASS) cuando el modelo predice correctamente."""
        service = LSECTranslatorService()
        corpus_path = Path("data/corpus/pilot_corpus_lsec.json")
        with open(corpus_path, "r", encoding="utf-8") as f:
            raw_items = json.load(f)

        frozen_items = [LSECDatasetItem(**raw) for raw in raw_items if raw.get("dataset_split") == "FROZEN_TEST"]
        assert len(frozen_items) > 0

        pairs = []
        for it in frozen_items:
            pred_out = await service.translate_to_gloss(it.source_text, mode="detailed")
            pairs.append((it, pred_out))

        metrics = MLOpsPipeline.evaluate_against_frozen_test(pairs, baseline_f1=0.80)
        assert metrics.total_test_samples == len(frozen_items)
        assert metrics.blocking_errors_count == 0
        assert metrics.unsupported_concepts_count == 0
        assert metrics.deployment_gate_decision in ("PASS", "PASS_WITH_LIMITATIONS")

    @pytest.mark.asyncio
    async def test_mlops_frozen_test_evaluation_fail_gate(self):
        """Evaluación falla (FAIL) si el modelo candidato introduce errores bloqueantes."""
        service = LSECTranslatorService()
        corpus_path = Path("data/corpus/pilot_corpus_lsec.json")
        with open(corpus_path, "r", encoding="utf-8") as f:
            raw_items = json.load(f)

        frozen_item = LSECDatasetItem(**[r for r in raw_items if r.get("dataset_split") == "FROZEN_TEST"][0])
        pred_out = await service.translate_to_gloss(frozen_item.source_text, mode="detailed")
        
        # Simular falla crítica en el modelo candidato
        pred_out.execution_status = ExecutionStatus.BLOCKED
        
        metrics = MLOpsPipeline.evaluate_against_frozen_test([(frozen_item, pred_out)], baseline_f1=0.80)
        assert metrics.deployment_gate_decision == "FAIL"
        assert "BLOCKED" in metrics.gate_justification
