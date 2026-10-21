"""Pruebas del flujo de anotaciones persistido en SQLite."""

from __future__ import annotations

import pytest

from app.api.annotation_endpoints import (
    AnnotationSubmissionRequest,
    set_annotation_storage,
    submit_annotation_review,
)
from app.services.storage_service import LocalStorageService


@pytest.mark.asyncio
async def test_annotation_submission_survives_storage_reopen(tmp_path):
    db_path = tmp_path / "annotations.sqlite"
    first = LocalStorageService(db_path)
    set_annotation_storage(first)

    result = await submit_annotation_review(
        AnnotationSubmissionRequest(
            example_id="pilot_ex_001",
            reviewer_id_anonymized="reviewer_001",
            action="APPROVE",
            change_reason="Validación inicial",
        )
    )
    assert result["status"] == "SUCCESS"
    first.close()

    second = LocalStorageService(db_path)
    set_annotation_storage(second)
    persisted = await second.get_annotation_snapshot("pilot_ex_001")
    assert persisted is not None
    assert persisted["annotation_status"] == "NATIVE_VALIDATED"
    assert persisted["native_validation_status"] is True
    assert len(persisted["audit_history"]) == 1
    second.close()
    set_annotation_storage(None)
