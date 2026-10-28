"""
Endpoints HTTP (REST) del sistema LSEC Translator 2.0.

Proporciona endpoints para transcripción, traducción a glosas LSEC,
ejecución del pipeline completo y gestión del flujo de revisión lingüística.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from app.core.schemas import GlossOutput, TranscriptionResult, TranslationMode
from app.config import settings
from app.services.asr_service import WhisperASRService
from app.services.storage_service import LocalStorageService
from app.services.nlp_service import LSECTranslatorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["LSEC Pipeline"])

_ALLOWED_UPLOAD_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".webm", ".mp4", ".mov", ".avi", ".mkv"}
_UPLOAD_CHUNK_SIZE = 1024 * 1024

# ============================================================
# Instancias de servicios (inyectadas desde main.py via lifespan)
# ============================================================

_asr_service: WhisperASRService | None = None
_nlp_service: LSECTranslatorService | None = None
_storage_service: LocalStorageService | None = None


def validate_media_magic_bytes(file_path: str) -> bool:
    """
    Valida la cabecera del archivo multimedia contra números mágicos conocidos
    (MP4, MOV, AVI, MKV, WebM, WAV, MP3, OGG, FLAC).
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(64)
        if len(header) < 4:
            return False

        # WAV / AVI (RIFF container)
        if header.startswith(b"RIFF") and len(header) >= 12:
            fourcc = header[8:12]
            if fourcc in (b"WAVE", b"AVI ", b"AVIX"):
                return True

        # MP4 / MOV (ISO Base Media File Format)
        if len(header) >= 8:
            if header[4:8] in (b"ftyp", b"moov", b"wide", b"mdat", b"free", b"skip", b"pnot"):
                return True

        # WebM / MKV (EBML ID: 0x1A 0x45 0xDF 0xA3)
        if header.startswith(b"\x1a\x45\xdf\xa3"):
            return True

        # Ogg Vorbis / Opus
        if header.startswith(b"OggS"):
            return True

        # FLAC
        if header.startswith(b"fLaC"):
            return True

        # MP3 (ID3v2 tag or MPEG audio sync frame)
        if header.startswith(b"ID3"):
            return True
        if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0 == 0xE0):
            return True

        return False
    except OSError:
        return False


async def _save_upload_to_temp(file: UploadFile) -> str:
    """Guarda una carga multimedia acotada y devuelve su ruta temporal."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Extensión multimedia no soportada.",
        )

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    total_bytes = 0
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
            while chunk := await file.read(_UPLOAD_CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"El archivo supera el límite de {settings.max_upload_size_mb} MB.",
                    )
                tmp.write(chunk)
        return tmp_path
    except (OSError, HTTPException):
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def set_services(
    asr: WhisperASRService,
    nlp: LSECTranslatorService,
    storage: Optional[LocalStorageService] = None,
) -> None:
    """Inyecta las instancias de servicios en los endpoints."""
    global _asr_service, _nlp_service, _storage_service
    _asr_service = asr
    _nlp_service = nlp
    _storage_service = storage


# ============================================================
# Modelos de Request/Response
# ============================================================

class TextInput(BaseModel):
    """Entrada de texto para traducción directa."""
    text: str = Field(min_length=1, max_length=5000, description="Texto en español a traducir")
    mode: Optional[str] = Field(default="detailed", description="Modo de salida: 'legacy', 'detailed', 'debug'")
    paraphrase_budget: Optional[str] = Field(default="compact", description="'compact', 'medium', 'expanded'")
    context_before: Optional[str] = Field(default=None, max_length=1500, description="Oración(es) previas: solo aportan contexto (correferencia, relaciones de discurso); no se traducen")
    word_timestamps: Optional[List[Dict[str, Any]]] = Field(default=None, description="Marcas de tiempo por palabra del texto (alineación fuente real en lugar de reparto uniforme)")


class PipelineResponse(BaseModel):
    """Respuesta del pipeline completo."""
    transcription: TranscriptionResult
    gloss_output: GlossOutput


class HealthResponse(BaseModel):
    """Respuesta del health check."""
    status: str
    services: Dict[str, bool]
    checks: Dict[str, bool] = Field(default_factory=dict)
    version: str = settings.system_version
    api_version: str = settings.api_version
    engine_version: str = settings.engine_version
    output_schema_version: str = settings.output_schema_version
    default_animation_version: str = settings.default_animation_version
    hardware: Optional[Dict[str, Any]] = None


# ============================================================
# Endpoints Principales
# ============================================================

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Verifica el estado del sistema y sus servicios.",
)
async def health_check() -> HealthResponse:
    """Endpoint de verificación de salud del sistema."""
    services = {
        "asr": _asr_service is not None,
        "nlp": _nlp_service is not None,
        "storage": _storage_service is not None and _storage_service.is_connected,
    }
    checks = {
        "asr_model_loaded": _asr_service is not None and _asr_service.is_ready(),
        "storage_persistent": _storage_service is not None and _storage_service.is_persistent,
    }
    hw = _asr_service.get_hardware_status() if _asr_service else None
    return HealthResponse(
        status="ok" if all(services.values()) else "degraded",
        services=services,
        checks=checks,
        version=settings.system_version,
        api_version=settings.api_version,
        engine_version=settings.engine_version,
        output_schema_version=settings.output_schema_version,
        default_animation_version=settings.default_animation_version,
        hardware=hw,
    )


@router.get(
    "/hardware-status",
    summary="Estado de Aceleración por Hardware",
    description="Devuelve información sobre el uso de GPU CUDA o CPU.",
)
async def hardware_status() -> Dict[str, Any]:
    """Endpoint para inspeccionar si se está utilizando GPU o CPU."""
    if _asr_service is None:
        return {"device": "unknown", "is_gpu": False, "status_text": "Servicio no disponible"}
    return _asr_service.get_hardware_status()


@router.post(
    "/transcribe",
    response_model=TranscriptionResult,
    summary="Transcribir Audio",
    description="Recibe un archivo de audio y devuelve la transcripción en texto.",
    status_code=status.HTTP_200_OK,
)
async def transcribe_audio(
    file: UploadFile = File(..., description="Archivo de audio (wav, mp3, ogg, webm)"),
) -> TranscriptionResult:
    """Transcribe un archivo de audio a texto usando Whisper."""
    if _asr_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio ASR no disponible.",
        )

    tmp_path = None
    try:
        tmp_path = await _save_upload_to_temp(file)

        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo multimedia está vacío (0 bytes).",
            )

        if not validate_media_magic_bytes(tmp_path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato multimedia no reconocido o cabecera inválida. Formatos soportados: mp4, mov, avi, mkv, webm, wav, mp3, ogg, flac.",
            )

        result = await asyncio.to_thread(_asr_service.transcribe_file, tmp_path)
        logger.info("Audio transcrito: '%s...'", result.text[:80])
        return result

    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en transcripción: {exc}",
        )
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@router.post(
    "/translate",
    response_model=GlossOutput,
    summary="Traducir Texto a Glosa LSEC 2.0",
    description="Recibe texto en español y devuelve la representación intermedia y glosas LSEC.",
    status_code=status.HTTP_200_OK,
)
async def translate_text(
    body: TextInput,
    mode_query: Optional[str] = Query(None, alias="mode", description="Modo de salida opcional ('legacy', 'detailed', 'debug')"),
) -> GlossOutput:
    """
    Traduce texto en español a glosas LSEC con análisis discursivo y semántico.
    """
    if _nlp_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio NLP no disponible.",
        )

    try:
        selected_mode = mode_query or body.mode or "detailed"
        budget = body.paraphrase_budget or "compact"

        transcription_in = None
        if body.word_timestamps:
            from app.core.schemas import TranscriptionInput, WordTimestamp
            _words = [WordTimestamp.model_validate(w) for w in body.word_timestamps if isinstance(w, dict) and 'word' in w and 'start' in w and 'end' in w]
            if _words:
                transcription_in = TranscriptionInput(text=body.text, word_timestamps=_words)

        result = await _nlp_service.translate_to_gloss(
            text=body.text,
            mode=selected_mode,
            paraphrase_budget=budget,
            transcription=transcription_in,
            context_before=body.context_before,
        )

        if _storage_service is not None:
            try:
                await _storage_service.save_translation_log({
                    "original_text": body.text,
                    "glosses_count": len(result.glosses),
                    "session_id": str(result.session_id),
                    "schema_version": result.schema_version,
                })
            except (OSError, sqlite3.Error) as exc:
                logger.warning("No se pudo guardar el log de traducción en la base local: %s", exc)

        return result

    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except (RuntimeError, OSError) as exc:
        logger.error("Error en traducción: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en traducción: {exc}",
        )


@router.post(
    "/pipeline",
    response_model=PipelineResponse,
    summary="Pipeline Completo LSEC",
    description="Ejecuta el pipeline completo: audio → transcripción → normalización → LSEC 2.0.",
    status_code=status.HTTP_200_OK,
)
async def full_pipeline(
    file: UploadFile = File(..., description="Archivo de audio"),
    mode: str = Query("detailed", description="Modo de respuesta"),
) -> PipelineResponse:
    """Pipeline completo de audio a glosas LSEC 2.0."""
    if _asr_service is None or _nlp_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicios ASR/NLP no disponibles.",
        )

    tmp_path = None
    try:
        tmp_path = await _save_upload_to_temp(file)

        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo multimedia está vacío (0 bytes).",
            )

        if not validate_media_magic_bytes(tmp_path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato multimedia no reconocido o cabecera inválida. Formatos soportados: mp4, mov, avi, mkv, webm, wav, mp3, ogg, flac.",
            )

        transcription = await asyncio.to_thread(_asr_service.transcribe_file, tmp_path)
        if not transcription.text.strip():
            logger.info("Pipeline 2.0: Audio sin habla detectada en '%s'. Devolviendo estructura vacía editable.", file.filename)
            gloss_output = GlossOutput(
                original_text="",
                normalized_text="",
                glosses=[],
                semantic_propositions=[],
                discourse_blocks=[],
                spatial_referents=[],
                spatial_operations=[],
                non_manual_spans=[],
                translation_plans=[],
            )
            return PipelineResponse(
                transcription=transcription,
                gloss_output=gloss_output,
            )

        gloss_output = await _nlp_service.translate_to_gloss(
            text=transcription.text,
            mode=mode,
            source_audio_duration=transcription.duration_seconds,
            transcription=transcription,
        )

        logger.info(
            "Pipeline 2.0 completado: '%s...' → %d glosas",
            transcription.text[:50],
            len(gloss_output.glosses),
        )

        return PipelineResponse(
            transcription=transcription,
            gloss_output=gloss_output,
        )

    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except (RuntimeError, OSError) as exc:
        logger.error("Error en pipeline: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en pipeline: {exc}",
        )
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
