"""
Endpoints HTTP (REST) del sistema LSEC Translator 2.0.

Proporciona endpoints para transcripción, traducción a glosas LSEC,
ejecución del pipeline completo y gestión del flujo de revisión lingüística.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from app.core.schemas import GlossOutput, TranscriptionResult, TranslationMode
from app.services.asr_service import WhisperASRService
from app.services.storage_service import LocalStorageService
from app.services.nlp_service import LSECTranslatorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["LSEC Pipeline"])

# ============================================================
# Instancias de servicios (inyectadas desde main.py via lifespan)
# ============================================================

_asr_service: WhisperASRService | None = None
_nlp_service: LSECTranslatorService | None = None
_storage_service: LocalStorageService | None = None

# Almacén en memoria de revisiones (para auditoría, delimitado a 500 registros)
_MAX_REVIEW_LOG_SIZE = 500
_REVIEW_LOG: List[Dict[str, Any]] = []


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
    except Exception:
        return False


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


class PipelineResponse(BaseModel):
    """Respuesta del pipeline completo."""
    transcription: TranscriptionResult
    gloss_output: GlossOutput


class HealthResponse(BaseModel):
    """Respuesta del health check."""
    status: str
    services: Dict[str, bool]
    version: str = "2.0.0"


class ReviewSubmission(BaseModel):
    """Envío de revisión lingüística por persona sorda usuaria nativa o lingüista."""
    session_id: Optional[UUID] = None
    reviewer_id: str = Field(min_length=1, description="ID o nombre del revisor autorizado")
    is_native_signer: bool = Field(default=False, description="¿El revisor es persona sorda usuaria nativa de LSEC?")
    regional_variant: Optional[str] = Field(default=None, description="Variante regional evaluada (ej. Sierra, Costa)")
    decision: str = Field(description="'approved', 'rejected', 'modified'")
    target_type: str = Field(default="gloss_sequence", description="'gloss_sequence', 'paraphrase', 'spatial_operation', 'non_manual'")
    target_id: Optional[str] = None
    suggested_glosses: Optional[List[str]] = None
    comments: Optional[str] = None


class ReviewRecordResponse(BaseModel):
    """Confirmación de registro de revisión."""
    review_id: str
    status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str


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
    return HealthResponse(
        status="ok",
        services={
            "asr": _asr_service is not None and _asr_service.is_ready(),
            "nlp": _nlp_service is not None,
            "storage": _storage_service is not None and _storage_service.is_connected,
        },
        version="2.0.0",
    )


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
        suffix = Path(file.filename or "audio.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
            shutil.copyfileobj(file.file, tmp)

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

        result = _asr_service.transcribe_file(tmp_path)
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

        result = await _nlp_service.translate_to_gloss(
            text=body.text,
            mode=selected_mode,
            paraphrase_budget=budget,
        )

        if _storage_service is not None:
            try:
                await _storage_service.save_translation_log({
                    "original_text": body.text,
                    "glosses_count": len(result.glosses),
                    "session_id": str(result.session_id),
                    "schema_version": result.schema_version,
                })
            except Exception:
                logger.warning("No se pudo guardar el log de traducción en la base local.")

        return result

    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
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
        suffix = Path(file.filename or "audio.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
            shutil.copyfileobj(file.file, tmp)

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

        transcription = _asr_service.transcribe_file(tmp_path)
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
    except Exception as exc:
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


# ============================================================
# Endpoints de Revisión Lingüística (Fase 26)
# ============================================================

@router.post(
    "/review/validate",
    response_model=ReviewRecordResponse,
    summary="Registrar Revisión Lingüística / Nativa",
    description="Permite a personas sordas nativas o lingüistas documentar validación o ajustes.",
    status_code=status.HTTP_200_OK,
)
async def submit_linguistic_review(review: ReviewSubmission) -> ReviewRecordResponse:
    """Registra una revisión formal de una propuesta computacional."""
    review_id = f"rev_{uuid4().hex[:8]}"
    record = {
        "review_id": review_id,
        "session_id": str(review.session_id) if review.session_id else None,
        "reviewer_id": review.reviewer_id,
        "is_native_signer": review.is_native_signer,
        "regional_variant": review.regional_variant,
        "decision": review.decision,
        "target_type": review.target_type,
        "target_id": review.target_id,
        "suggested_glosses": review.suggested_glosses,
        "comments": review.comments,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _REVIEW_LOG.append(record)
    if len(_REVIEW_LOG) > _MAX_REVIEW_LOG_SIZE:
        _REVIEW_LOG.pop(0)
    if _storage_service is not None:
        try:
            await _storage_service.save_review(record)
        except Exception:
            logger.warning("No se pudo persistir la revisión en la base local.")

    logger.info(
        "Revisión registrada [%s]: revisor=%s (nativo=%s), decisión=%s",
        review_id, review.reviewer_id, review.is_native_signer, review.decision,
    )

    return ReviewRecordResponse(
        review_id=review_id,
        status="recorded",
        message="Revisión documentada exitosamente para trazabilidad y entrenamiento del motor.",
    )


@router.get(
    "/review/history",
    summary="Consultar Historial de Revisiones",
    description="Devuelve el registro de revisiones documentadas en la sesión.",
)
async def get_review_history() -> List[Dict[str, Any]]:
    """Consulta el registro histórico de revisiones."""
    if _storage_service is not None:
        try:
            return await _storage_service.get_reviews(_MAX_REVIEW_LOG_SIZE)
        except Exception:
            logger.warning("No se pudo leer el historial desde la base local; se usa la memoria.")
    return list(_REVIEW_LOG)
