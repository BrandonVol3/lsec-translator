"""
Módulo 1 — Servicio de Reconocimiento Automático de Voz (ASR).

Utiliza faster-whisper (CTranslate2) para transcribir audio
en español con soporte para procesamiento por lotes y streaming.
"""

from __future__ import annotations

import io
import logging
import tempfile
from pathlib import Path
from typing import BinaryIO, Union

import numpy as np

from app.config import settings
from app.core.schemas import TranscriptionResult, WordTimestamp

logger = logging.getLogger(__name__)


class WhisperASRService:
    """
    Servicio de transcripción de voz a texto basado en Whisper.

    Soporta dos modos de operación:
    - Archivo: transcribe un archivo de audio completo desde disco.
    - Buffer: transcribe un buffer binario en memoria (para streaming).
    """

    def __init__(
        self,
        model_size: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
    ) -> None:
        self._model_size = model_size or settings.whisper_model_size
        self._device = device or settings.whisper_device
        self._compute_type = compute_type or settings.whisper_compute_type
        self._model = None
        logger.info(
            "WhisperASRService configurado: modelo=%s, device=%s, compute=%s",
            self._model_size,
            self._device,
            self._compute_type,
        )

    def _load_model(self) -> None:
        """Carga el modelo Whisper de forma lazy (primera invocación)."""
        if self._model is not None:
            return

        import os
        import sys

        # Asegurar registro de DLLs de CUDA en Windows
        if sys.platform == "win32":
            venv_base = os.path.dirname(os.path.dirname(sys.executable))
            site_packages = os.path.join(venv_base, "Lib", "site-packages")
            nvidia_dir = os.path.join(site_packages, "nvidia")
            if os.path.exists(nvidia_dir):
                for sub in os.listdir(nvidia_dir):
                    bin_path = os.path.join(nvidia_dir, sub, "bin")
                    if os.path.isdir(bin_path):
                        os.environ["PATH"] = bin_path + os.pathsep + os.environ.get("PATH", "")
                        if hasattr(os, "add_dll_directory"):
                            try:
                                os.add_dll_directory(bin_path)
                            except Exception:
                                pass

        try:
            from faster_whisper import WhisperModel

            model_ref, local_only = self._resolve_model_reference()
            logger.info("Cargando modelo Whisper '%s'%s...", model_ref, " (local)" if local_only else "")
            kwargs = {"local_files_only": True} if local_only else {}
            self._model = WhisperModel(
                model_ref,
                device=self._device,
                compute_type=self._compute_type,
                **kwargs,
            )
            logger.info("Modelo Whisper cargado exitosamente.")
        except ImportError:
            logger.error(
                "faster-whisper no está instalado. "
                "Ejecute: pip install faster-whisper"
            )
            raise
        except Exception as exc:
            logger.error("Error al cargar modelo Whisper: %s", exc)
            raise RuntimeError(f"No se pudo cargar el modelo Whisper: {exc}") from exc

    def _resolve_model_reference(self) -> tuple[str, bool]:
        """
        Devuelve (referencia_del_modelo, solo_local).

        Prioriza pesos locales para funcionar sin Internet: ``<whisper_model_path>/<tamaño>`` o
        ``<whisper_model_path>`` si contiene directamente ``model.bin``. Si no hay pesos locales,
        usa el nombre del modelo (descarga automática de faster-whisper).
        """
        project_root = Path(__file__).resolve().parent.parent.parent
        base = Path(settings.whisper_model_path)
        if not base.is_absolute():
            base = project_root / base
        for candidate in (base / self._model_size, base):
            if (candidate / "model.bin").exists():
                return str(candidate), True
        return self._model_size, False

    def transcribe_file(
        self,
        file_path: Union[str, Path],
        language: str = "es",
    ) -> TranscriptionResult:
        """
        Transcribe un archivo de audio desde disco.

        Args:
            file_path: Ruta al archivo de audio.
            language: Código de idioma ISO 639-1 (default: 'es').

        Returns:
            TranscriptionResult con texto, confianza y timestamps.

        Raises:
            FileNotFoundError: Si el archivo no existe.
            RuntimeError: Si ocurre un error durante la transcripción.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Archivo de audio no encontrado: {file_path}")

        self._load_model()

        try:
            segments, info = self._model.transcribe(
                str(file_path),
                language=language,
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,
            )

            words: list[WordTimestamp] = []
            text_parts: list[str] = []
            total_confidence = 0.0
            word_count = 0

            for segment in segments:
                text_parts.append(segment.text.strip())
                if segment.words:
                    for word in segment.words:
                        words.append(
                            WordTimestamp(
                                word=word.word.strip(),
                                start=word.start,
                                end=word.end,
                                probability=word.probability,
                            )
                        )
                        total_confidence += word.probability
                        word_count += 1

            full_text = " ".join(text_parts)
            avg_confidence = total_confidence / max(word_count, 1)

            result = TranscriptionResult(
                text=full_text,
                language=info.language,
                confidence=round(avg_confidence, 4),
                duration_seconds=round(info.duration, 2),
                word_timestamps=words,
            )

            logger.info(
                "Transcripción completada: %d caracteres, confianza=%.2f",
                len(full_text),
                avg_confidence,
            )
            return result

        except Exception as exc:
            logger.error("Error en transcripción de archivo: %s", exc)
            raise RuntimeError(f"Error durante la transcripción: {exc}") from exc

    def transcribe_buffer(
        self,
        audio_data: bytes,
        language: str = "es",
    ) -> TranscriptionResult:
        """
        Transcribe un buffer binario de audio.

        Escribe el buffer en un archivo temporal para procesamiento,
        ya que faster-whisper requiere acceso por archivo.

        Args:
            audio_data: Bytes crudos del audio.
            language: Código de idioma ISO 639-1 (default: 'es').

        Returns:
            TranscriptionResult con texto, confianza y timestamps.

        Raises:
            ValueError: Si el buffer está vacío.
            RuntimeError: Si ocurre un error durante la transcripción.
        """
        if not audio_data:
            raise ValueError("El buffer de audio está vacío.")

        tmp_path = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            tmp.write(audio_data)
            tmp.close()  # Cerrar antes de que faster-whisper lo abra
            return self.transcribe_file(tmp_path, language=language)
        except (ValueError, FileNotFoundError):
            raise
        except Exception as exc:
            logger.error("Error en transcripción de buffer: %s", exc)
            raise RuntimeError(f"Error procesando buffer de audio: {exc}") from exc
        finally:
            if tmp_path:
                import os
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def is_ready(self) -> bool:
        """Verifica si el servicio está listo (modelo cargado)."""
        return self._model is not None

    def warmup(self) -> None:
        """Pre-carga el modelo para reducir latencia en la primera solicitud."""
        self._load_model()
