"""
Módulo 4 — Puente de Visualización WebSocket (3D Avatar Bridge).

Conexión WebSocket bidireccional que recibe eventos de audio/texto,
ejecuta el pipeline secuencial (ASR → NLP → ensamblaje) y emite
en tiempo real las glosas, marcadores no-manuales y coordenadas
espaciales al renderizador 3D (Unreal Engine 5 / MetaHuman).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.schemas import (
    AvatarPayload,
    GlossOutput,
    NonManualMarker,
    TranscriptionResult,
    WSMessageType,
    WebSocketMessage,
)
from app.services.asr_service import WhisperASRService
from app.services.nlp_service import LSECTranslatorService

logger = logging.getLogger(__name__)

ws_router = APIRouter(tags=["WebSocket Pipeline"])

# ============================================================
# Servicios (inyectados desde main.py)
# ============================================================

_asr_service: WhisperASRService | None = None
_nlp_service: LSECTranslatorService | None = None


def set_ws_services(
    asr: WhisperASRService,
    nlp: LSECTranslatorService,
) -> None:
    """Inyecta las instancias de servicios para WebSocket."""
    global _asr_service, _nlp_service
    _asr_service = asr
    _nlp_service = nlp


class ConnectionManager:
    """Gestiona conexiones WebSocket activas."""

    def __init__(self) -> None:
        self.active_connections: Dict[UUID, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: UUID) -> None:
        """Acepta y registra una nueva conexión."""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info("WebSocket conectado: session=%s (total: %d)", session_id, len(self.active_connections))

    def disconnect(self, session_id: UUID) -> None:
        """Desregistra una conexión cerrada."""
        self.active_connections.pop(session_id, None)
        logger.info("WebSocket desconectado: session=%s (total: %d)", session_id, len(self.active_connections))

    async def send_message(self, websocket: WebSocket, message: WebSocketMessage) -> None:
        """Envía un mensaje serializado como JSON."""
        await websocket.send_text(message.model_dump_json())

    async def send_error(self, websocket: WebSocket, error: str, session_id: Optional[UUID] = None) -> None:
        """Envía un mensaje de error."""
        msg = WebSocketMessage(
            type=WSMessageType.ERROR,
            payload={"detail": error},
            session_id=session_id,
        )
        await websocket.send_text(msg.model_dump_json())


manager = ConnectionManager()


async def _process_audio_chunk(
    audio_data: bytes,
    session_id: UUID,
    websocket: WebSocket,
) -> None:
    """
    Procesa un chunk de audio a través del pipeline completo.

    Pipeline: Audio → ASR (Whisper) → NLP (LSEC Gloss) → Avatar Payloads
    """
    start_time = time.time()

    if _asr_service is None or _nlp_service is None:
        await manager.send_error(websocket, "Servicios no inicializados.", session_id)
        return

    try:
        # Paso 1: Transcripción ASR
        transcription = await asyncio.to_thread(_asr_service.transcribe_buffer, audio_data)

        # Notificar transcripción al cliente
        trans_msg = WebSocketMessage(
            type=WSMessageType.TRANSCRIPTION,
            payload=transcription.model_dump(),
            session_id=session_id,
        )
        await manager.send_message(websocket, trans_msg)

        if not transcription.text.strip():
            logger.info("Transcripción vacía, omitiendo traducción.")
            return

        # Paso 2: Traducción a Glosa LSEC
        gloss_output = await _nlp_service.translate_to_gloss(transcription.text)

        # Notificar glosas al cliente
        gloss_msg = WebSocketMessage(
            type=WSMessageType.GLOSS_RESULT,
            payload=gloss_output.model_dump(mode="json"),
            session_id=session_id,
        )
        await manager.send_message(websocket, gloss_msg)

        # Paso 3: Generar payloads de avatar para cada glosa
        for idx, gloss_item in enumerate(gloss_output.glosses):
            avatar_payload = AvatarPayload(
                session_id=session_id,
                sequence_index=idx,
                gloss=gloss_item,
                non_manual_markers=gloss_item.non_manual,
                timestamp_ms=time.time() * 1000,
                metadata={
                    "original_text": transcription.text,
                    "total_glosses": len(gloss_output.glosses),
                    "pipeline_latency_ms": round((time.time() - start_time) * 1000, 2),
                },
            )

            payload_msg = WebSocketMessage(
                type=WSMessageType.AVATAR_PAYLOAD,
                payload=avatar_payload.model_dump(mode="json"),
                session_id=session_id,
            )
            await manager.send_message(websocket, payload_msg)

        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        logger.info(
            "Pipeline WS completado: session=%s, glosas=%d, latencia=%dms",
            session_id,
            len(gloss_output.glosses),
            elapsed_ms,
        )

    except Exception as exc:
        logger.error("Error en pipeline WS: %s", exc)
        await manager.send_error(websocket, f"Error en pipeline: {exc}", session_id)


async def _process_text_input(
    text: str,
    session_id: UUID,
    websocket: WebSocket,
) -> None:
    """Procesa entrada de texto directa (sin ASR) a través del pipeline NLP."""
    start_time = time.time()

    if _nlp_service is None:
        await manager.send_error(websocket, "Servicio NLP no inicializado.", session_id)
        return

    try:
        # Traducción directa a glosa
        gloss_output = await _nlp_service.translate_to_gloss(text)

        # Notificar glosas
        gloss_msg = WebSocketMessage(
            type=WSMessageType.GLOSS_RESULT,
            payload=gloss_output.model_dump(mode="json"),
            session_id=session_id,
        )
        await manager.send_message(websocket, gloss_msg)

        # Generar payloads de avatar
        for idx, gloss_item in enumerate(gloss_output.glosses):
            avatar_payload = AvatarPayload(
                session_id=session_id,
                sequence_index=idx,
                gloss=gloss_item,
                non_manual_markers=gloss_item.non_manual,
                timestamp_ms=time.time() * 1000,
                metadata={
                    "original_text": text,
                    "total_glosses": len(gloss_output.glosses),
                },
            )

            payload_msg = WebSocketMessage(
                type=WSMessageType.AVATAR_PAYLOAD,
                payload=avatar_payload.model_dump(mode="json"),
                session_id=session_id,
            )
            await manager.send_message(websocket, payload_msg)

        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        logger.info(
            "Pipeline texto WS completado: session=%s, glosas=%d, latencia=%dms",
            session_id,
            len(gloss_output.glosses),
            elapsed_ms,
        )

    except Exception as exc:
        logger.error("Error en pipeline texto WS: %s", exc)
        await manager.send_error(websocket, f"Error: {exc}", session_id)


@ws_router.websocket("/ws/pipeline")
async def websocket_pipeline(websocket: WebSocket) -> None:
    """
    Endpoint WebSocket para el pipeline de traducción en tiempo real.

    Protocolo de mensajes:
    - Cliente → Servidor:
        - {"type": "audio_chunk", "payload": {"data": "<base64>"}}
        - {"type": "text_input", "payload": {"text": "Hola mundo"}}
        - {"type": "ping"}

    - Servidor → Cliente:
        - {"type": "transcription", "payload": {...}}
        - {"type": "gloss_result", "payload": {...}}
        - {"type": "avatar_payload", "payload": {...}}
        - {"type": "error", "payload": {"detail": "..."}}
        - {"type": "pong"}
    """
    session_id = uuid4()
    await manager.connect(websocket, session_id)

    try:
        while True:
            # Recibir mensaje (texto o binario)
            try:
                raw_data = await websocket.receive()
            except WebSocketDisconnect:
                break

            # Manejar mensajes de texto (JSON)
            if "text" in raw_data:
                try:
                    message = json.loads(raw_data["text"])
                    msg_type = message.get("type", "")
                    payload = message.get("payload", {})

                    if msg_type == WSMessageType.AUDIO_CHUNK.value:
                        import base64
                        audio_bytes = base64.b64decode(payload.get("data", ""))
                        await _process_audio_chunk(audio_bytes, session_id, websocket)

                    elif msg_type == WSMessageType.TEXT_INPUT.value:
                        text = payload.get("text", "")
                        if text:
                            await _process_text_input(text, session_id, websocket)
                        else:
                            await manager.send_error(websocket, "Texto vacío.", session_id)

                    elif msg_type == WSMessageType.PING.value:
                        pong = WebSocketMessage(type=WSMessageType.PONG, session_id=session_id)
                        await manager.send_message(websocket, pong)

                    elif msg_type == WSMessageType.CONTROL.value:
                        logger.info("Mensaje de control recibido: %s", payload)

                    else:
                        await manager.send_error(
                            websocket,
                            f"Tipo de mensaje no soportado: '{msg_type}'",
                            session_id,
                        )

                except json.JSONDecodeError:
                    await manager.send_error(websocket, "JSON inválido.", session_id)

            # Manejar mensajes binarios (audio crudo)
            elif "bytes" in raw_data and raw_data["bytes"]:
                await _process_audio_chunk(raw_data["bytes"], session_id, websocket)

    except WebSocketDisconnect:
        logger.info("Cliente desconectado: session=%s", session_id)
    except Exception as exc:
        logger.error("Error inesperado en WebSocket session=%s: %s", session_id, exc)
    finally:
        manager.disconnect(session_id)
