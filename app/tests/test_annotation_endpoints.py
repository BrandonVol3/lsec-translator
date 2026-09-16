"""
Suite de Pruebas de Integración para Endpoints de Anotación y MLOps (Fases 3, 4, 9 y 10).
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_api_dataset_manifest_and_leakage():
    """El endpoint /dataset/manifest retorna el manifiesto oficial y auditoría de fugas."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/dataset/manifest")
        assert resp.status_code == 200
        data = resp.json()
        assert "manifest" in data
        assert "leakage_audit" in data
        assert data["manifest"]["total_examples"] >= 5
        assert data["leakage_audit"]["has_leakage"] is False


@pytest.mark.asyncio
async def test_api_dataset_validate_item():
    """El endpoint /dataset/validate-item valida correctamente un elemento del dataset."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        valid_item_payload = {
            "example_id": "test_api_001",
            "source_text": "Yo como pan",
            "normalized_text": "Yo como pan",
            "annotation_status": "NATIVE_VALIDATED",
            "native_validation_status": True,
            "reviewer_ids_anonymized": ["rev_sordo_01"],
            "dataset_split": "TRAIN",
            "consent_status": "EXPLICIT_CONSENT_GRANTED",
            "validated_glosses": ["PAN", "COMER"],
        }
        resp = await client.post("/api/v1/dataset/validate-item", json=valid_item_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_valid"] is True
        assert len(data["errors"]) == 0


@pytest.mark.asyncio
async def test_api_dataset_export_only_native_validated():
    """El endpoint /dataset/export entrega únicamente ejemplos NATIVE_VALIDATED con consentimiento."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/dataset/export")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 5
        for it in items:
            assert it["annotation_status"] == "NATIVE_VALIDATED"
            assert it["consent_status"] == "EXPLICIT_CONSENT_GRANTED"


@pytest.mark.asyncio
async def test_api_annotation_submission_audit():
    """El endpoint /annotations/submit registra la acción y genera un ID de auditoría."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        sub_payload = {
            "example_id": "pilot_ex_001",
            "reviewer_id_anonymized": "rev_sordo_01",
            "action": "APPROVE",
            "change_reason": "Verificación lingüística nativa completa de orden y señas.",
            "confidence": 1.0,
        }
        resp = await client.post("/api/v1/annotations/submit", json=sub_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert data["example_id"] == "pilot_ex_001"
        assert "audit_id" in data


@pytest.mark.asyncio
async def test_api_active_learning_queue():
    """El endpoint /annotations/queue retorna ejemplos ordenados por prioridad de incertidumbre."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/annotations/queue?top_k=5")
        assert resp.status_code == 200
        queue = resp.json()
        assert len(queue) > 0
        assert "uncertainty_score" in queue[0]
        assert "priority_level" in queue[0]


@pytest.mark.asyncio
async def test_api_mlops_benchmark():
    """El endpoint /mlops/benchmark ejecuta la compuerta de evaluación sobre el Frozen Test Set."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post("/api/v1/mlops/benchmark")
        assert resp.status_code == 200
        data = resp.json()
        assert "deployment_gate_decision" in data
        assert data["deployment_gate_decision"] in ("PASS", "PASS_WITH_LIMITATIONS")
        assert data["blocking_errors_count"] == 0
