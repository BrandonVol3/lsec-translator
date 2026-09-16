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

    # --- OpenAI / LLM (OpenAI u Ollama) ---
    openai_api_key: str = "llave-local-gratuita"
    openai_model: str = "qwen2.5:3b"
    openai_base_url: str = "http://localhost:11434/v1"

    # --- Protección GPU (GTX 1650 4GB VRAM) ---
    llm_max_tokens: int = 800
    llm_request_timeout: int = 300

    # --- Whisper ASR ---
    whisper_model_size: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # --- Firebase ---
    firebase_credentials_path: str = "./firebase-credentials.json"
    firebase_project_id: str = ""

    # --- Servidor ---
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8080"]

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

    @property
    def firebase_credentials_file(self) -> Path:
        """Retorna la ruta al archivo de credenciales Firebase."""
        return Path(self.firebase_credentials_path)

    @property
    def has_openai_key(self) -> bool:
        """Verifica si hay un proveedor LLM configurado (OpenAI u Ollama local)."""
        if self.openai_base_url:
            return True
        return bool(self.openai_api_key and self.openai_api_key != "sk-your-api-key-here")

    @property
    def has_firebase_credentials(self) -> bool:
        """Verifica si existen credenciales de Firebase."""
        return self.firebase_credentials_file.exists()


# Instancia singleton de configuración
settings = Settings()
