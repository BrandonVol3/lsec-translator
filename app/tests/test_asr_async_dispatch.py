"""Pruebas de que ASR bloqueante se ejecuta fuera del event loop."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.api import endpoints


@pytest.mark.asyncio
async def test_transcribe_endpoint_dispatches_asr_to_worker_thread(monkeypatch, tmp_path):
    class FakeASR:
        def transcribe_file(self, file_path: str | Path):
            assert Path(file_path).exists()
            return type(
                "Result",
                (),
                {
                    "text": "hola",
                    "model_dump": lambda self: {},
                },
            )()

    async def fake_save_upload(_file):
        path = tmp_path / "audio.wav"
        path.write_bytes(b"RIFF" + b"\x00" * 4 + b"WAVE")
        return str(path)

    calls: list[str] = []
    original_to_thread = asyncio.to_thread

    async def tracking_to_thread(func, *args, **kwargs):
        calls.append(func.__name__)
        return await original_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(endpoints, "_asr_service", FakeASR())
    monkeypatch.setattr(endpoints, "_save_upload_to_temp", fake_save_upload)
    monkeypatch.setattr(endpoints.asyncio, "to_thread", tracking_to_thread)

    from fastapi import UploadFile
    import io

    result = await endpoints.transcribe_audio(UploadFile(filename="audio.wav", file=io.BytesIO(b"")))
    assert result.text == "hola"
    assert calls == ["transcribe_file"]
