"""
Configuración centralizada del proyecto.

Utiliza pydantic-settings para cargar variables de entorno
desde un archivo .env con validación de tipos automática.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent


def resolve_path(value: str, default: Path) -> Path:
    """Resuelve una ruta configurada, relativa al proyecto cuando corresponde."""
    configured = (value or "").strip()
    if not configured:
        return default
    path = Path(configured)
    return path if path.is_absolute() else PROJECT_ROOT / path


class Settings(BaseSettings):
    """Configuración global del sistema LSEC Translator."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Whisper ASR ---
    whisper_model_size: str = "small"
    whisper_device: str = "cuda"
    whisper_compute_type: str = "float16"

    # Carpeta con pesos locales de faster-whisper (modo 100% offline). Si existe, tiene prioridad
    # sobre la descarga automática desde Internet.
    whisper_model_path: str = "data/models/whisper"

    # --- Persistencia local (SQLite, 100% offline) ---
    lsec_database_path: str = "data/lsec_database.sqlite"

    # --- Activos externos ---
    # Las rutas vacías usan la estructura recomendada junto al proyecto.
    lsec_dictionary_root: str = ""
    lsec_avatar_dir: str = ""
    lsec_manual_config_dir: str = ""
    lsec_videos_dir: str = ""
    lsec_animations_v27_dir: str = ""
    lsec_animations_v26_dir: str = ""
    lsec_animations_dir: str = ""
    lsec_uhd_dir: str = ""
    lsec_senas_dir: str = ""

    # --- Servidor ---
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
    ]
    max_upload_size_mb: int = Field(default=100, ge=1, le=2048)

    # --- Versionado público ---
    # La versión del sistema identifica la distribución integrada. Las versiones
    # del motor, esquema y API se mantienen separadas por compatibilidad.
    system_version: str = "2.7.0"
    api_version: str = "2.0.0"
    engine_version: str = "2.1.1"
    output_schema_version: str = "2.1"
    grammar_engine_version: str = "0.1.0"
    default_animation_version: str = "2.7"

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
                    origins = parsed
                else:
                    origins = [v.strip()]
            except (json.JSONDecodeError, TypeError):
                origins = [origin.strip() for origin in v.split(",") if origin.strip()]
        else:
            origins = v
        if "*" in origins:
            raise ValueError("CORS_ORIGINS no puede usar '*' con credenciales habilitadas.")
        return origins


def external_path(value: str, relative_default: str) -> Path:
    """Resuelve un activo externo desde configuración o desde el workspace."""
    configured = (value or "").strip()
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else PROJECT_ROOT / path
    return WORKSPACE_ROOT / relative_default


# Instancia singleton de configuración
settings = Settings()
