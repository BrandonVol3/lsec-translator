"""Pruebas de límites y validación de cargas multimedia."""

from __future__ import annotations

import io

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

from app.api.endpoints import _save_upload_to_temp
from app.config import Settings, settings


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_extension():
    upload = UploadFile(filename="payload.exe", file=io.BytesIO(b"data"))
    with pytest.raises(HTTPException) as error:
        await _save_upload_to_temp(upload)
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_enforces_configured_size_limit(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    upload = UploadFile(filename="audio.wav", file=io.BytesIO(b"x" * (1024 * 1024 + 1)))
    with pytest.raises(HTTPException) as error:
        await _save_upload_to_temp(upload)
    assert error.value.status_code == 413


def test_cors_rejects_wildcard_with_credentials():
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(cors_origins=["*"])
