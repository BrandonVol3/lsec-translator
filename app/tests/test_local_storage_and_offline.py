"""Pruebas de la persistencia local SQLite (reemplazo offline de Firebase)."""

from __future__ import annotations

import pytest

from app.services.storage_service import LocalStorageService


@pytest.fixture
def storage(tmp_path):
    svc = LocalStorageService(tmp_path / "db" / "lsec.sqlite")
    yield svc
    svc.close()


@pytest.mark.asyncio
async def test_translation_log_roundtrip(storage):
    log_id = await storage.save_translation_log({
        "original_text": "Hola buenos días",
        "glosses_count": 3,
        "session_id": "s-1",
        "schema_version": "2.0",
    })
    assert log_id == "1"
    logs = await storage.get_translation_logs()
    assert len(logs) == 1
    assert logs[0]["original_text"] == "Hola buenos días"
    assert "timestamp" in logs[0]


@pytest.mark.asyncio
async def test_reviews_are_append_only_and_ordered(storage):
    for i in range(3):
        await storage.save_review({"review_id": f"rev_{i}", "reviewer_id": "r", "decision": "APPROVE"})
    reviews = await storage.get_reviews()
    assert [r["review_id"] for r in reviews] == ["rev_0", "rev_1", "rev_2"]
    with pytest.raises(Exception):  # review_id único: no se sobrescribe
        await storage.save_review({"review_id": "rev_0", "decision": "REJECT"})


@pytest.mark.asyncio
async def test_data_survives_reopen(tmp_path):
    path = tmp_path / "persist.sqlite"
    first = LocalStorageService(path)
    await first.save_translation_log({"original_text": "persistente"})
    first.close()

    second = LocalStorageService(path)
    assert second.is_persistent
    assert (await second.get_translation_logs())[0]["original_text"] == "persistente"
    second.close()


@pytest.mark.asyncio
async def test_annotation_snapshot_survives_reopen(tmp_path):
    path = tmp_path / "annotations.sqlite"
    item = {
        "example_id": "pilot_ex_001",
        "annotation_status": "NATIVE_VALIDATED",
        "validated_glosses": ["COMER", "MANZANA"],
        "audit_history": [{"audit_id": "audit_1"}],
        "updated_at": "2026-10-21T20:00:00+00:00",
    }
    first = LocalStorageService(path)
    await first.save_annotation_snapshot(item)
    first.close()

    second = LocalStorageService(path)
    assert await second.get_annotation_snapshot("pilot_ex_001") == item
    second.close()


def test_falls_back_to_memory_when_path_unusable(tmp_path):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x")
    svc = LocalStorageService(blocker / "sub" / "db.sqlite")  # padre es un archivo -> falla
    assert svc.is_connected
    assert not svc.is_persistent
    svc.close()


def test_whisper_prefers_local_weights(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.asr_service import WhisperASRService

    model_dir = tmp_path / "whisper" / "small"
    model_dir.mkdir(parents=True)
    (model_dir / "model.bin").write_bytes(b"0")
    monkeypatch.setattr(settings, "whisper_model_path", str(tmp_path / "whisper"))

    ref, local_only = WhisperASRService(model_size="small")._resolve_model_reference()
    assert local_only is True
    assert ref == str(model_dir)

    monkeypatch.setattr(settings, "whisper_model_path", str(tmp_path / "vacio"))
    assert WhisperASRService(model_size="small")._resolve_model_reference() == ("small", False)
