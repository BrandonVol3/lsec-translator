"""
Configuración centralizada del proyecto.

Utiliza pydantic-settings para cargar variables de entorno
desde un archivo .env con validación de tipos automática.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración global del sistema LSEC Translator."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Whisper ASR ---
    whisper_model_size: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Carpeta con pesos locales de faster-whisper (modo 100% offline). Si existe, tiene prioridad
    # sobre la descarga automática desde Internet.
    whisper_model_path: str = "data/models/whisper"

    # --- Persistencia local (SQLite, 100% offline) ---
    lsec_database_path: str = "data/lsec_database.sqlite"

    # --- Servidor ---
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8080"]

    # --- Diccionario Oficial LSEC (CONADIS) ---
    # Ruta al catálogo; si está vacía se resuelve automáticamente (data/ → ../Diccionario LSEC/).
    lsec_dictionary_catalog_path: str = ""
    lsec_dictionary_enabled: bool = True
    # Marca para revisión nativa las glosas léxicas ausentes del diccionario (política OOV).
    lsec_dictionary_flag_unverified: bool = True
    # Detecta entradas de varias palabras del diccionario ("a diario", "buenos días") como una sola seña.
    lsec_dictionary_phrase_matching: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | List[str]) -> List[str]:
        """Parsea orígenes CORS desde string JSON o lista."""
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v  # type: ignore[return-value]


# Instancia singleton de configuración
settings = Settings()
