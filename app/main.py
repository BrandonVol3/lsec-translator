"""
LSEC Translator Prototype — Punto de entrada principal.

Inicializa FastAPI, configura middleware CORS, monta las rutas
HTTP y WebSocket, y gestiona el ciclo de vida de los servicios
pesados (Whisper, MediaPipe) mediante lifespan events.
"""

from __future__ import annotations

import os
import sys

# Inyectar librerías dinámicas de CUDA en Windows
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

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.annotation_endpoints import annotation_router
from app.api.endpoints import router as api_router, set_services
from app.api.websocket import ws_router, set_ws_services
from app.config import settings
from app.services.asr_service import WhisperASRService
from app.services.firebase_service import FirebaseService
from app.services.nlp_service import LSECTranslatorService
from app.services.vision_service import SpatialGestureService

# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    level=logging.DEBUG if settings.app_debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ============================================================
# Instancias globales de servicios
# ============================================================

asr_service: WhisperASRService | None = None
nlp_service: LSECTranslatorService | None = None
vision_service: SpatialGestureService | None = None
firebase_service: FirebaseService | None = None


# ============================================================
# Lifespan — Inicialización y cierre de servicios
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Gestiona el ciclo de vida de la aplicación.

    Startup: inicializa todos los servicios de IA.
    Shutdown: libera recursos (modelos, conexiones).
    """
    global asr_service, nlp_service, vision_service, firebase_service

    logger.info("=" * 60)
    logger.info("LSEC Translator Prototype — Iniciando servicios...")
    logger.info("=" * 60)

    # Inicializar servicios
    try:
        asr_service = WhisperASRService()
        logger.info("✓ WhisperASRService creado (carga lazy del modelo)")
    except Exception as exc:
        logger.error("✗ Error creando WhisperASRService: %s", exc)
        asr_service = None

    try:
        nlp_service = LSECTranslatorService()
        logger.info("✓ LSECTranslatorService creado")
    except Exception as exc:
        logger.error("✗ Error creando LSECTranslatorService: %s", exc)
        nlp_service = None

    # Vision service (MediaPipe) desacoplado del inicio para optimizar recursos
    vision_service = None

    try:
        firebase_service = FirebaseService()
        logger.info("✓ FirebaseService creado (conectado=%s)", firebase_service.is_connected)
    except Exception as exc:
        logger.error("✗ Error creando FirebaseService: %s", exc)
        firebase_service = None

    # Inyectar servicios en los routers
    if asr_service and nlp_service:
        set_services(asr_service, nlp_service, firebase_service)
        set_ws_services(asr_service, nlp_service)

    logger.info("=" * 60)
    logger.info("Servicios inicializados. Servidor listo.")
    logger.info("Documentación: http://%s:%d/docs", settings.app_host, settings.app_port)
    logger.info("=" * 60)

    yield  # --- La aplicación se ejecuta aquí ---

    # Shutdown: liberar recursos
    logger.info("Cerrando servicios...")
    if vision_service:
        vision_service.close()
    logger.info("Servicios cerrados correctamente.")


# ============================================================
# Instancia de FastAPI
# ============================================================

app = FastAPI(
    title="LSEC Translator Prototype",
    description=(
        "Sistema de Transcripción Inteligente y Traducción Automática "
        "a Lengua de Señas Ecuatoriana (LSEC). "
        "Pipeline: Whisper ASR → NLP/LLM Gloss → MediaPipe Vision → WebSocket → Avatar 3D."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ============================================================
# Middleware CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Montar Routers
# ============================================================

app.include_router(api_router)
app.include_router(annotation_router)
app.include_router(ws_router)


# ============================================================
# Montar Archivos Estáticos y Media para la Interfaz Web LSEC Studio
# ============================================================

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Montar carpeta de videos de prueba únicamente si app_debug está activo
if settings.app_debug:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    videos_dir = os.path.join(project_root, "Videos de Prueba")
    if not os.path.exists(videos_dir):
        videos_dir = os.path.join(os.path.dirname(project_root), "Videos de Prueba")
    if os.path.exists(videos_dir):
        logger.info("✓ Montando /media (modo debug) desde: %s", videos_dir)
        app.mount("/media", StaticFiles(directory=videos_dir), name="media")


# ============================================================
# Root and Studio Endpoints
# ============================================================

@app.get("/", tags=["Root"])
async def root_endpoint(request: Request):
    """Sirve metadata JSON por defecto o la interfaz web si se solicita explícitamente text/html."""
    info_payload = {
        "name": "LSEC Translator Prototype",
        "version": "0.1.0",
        "description": "Sistema de Traducción a Lengua de Señas Ecuatoriana",
        "docs": "/docs",
        "websocket": "/ws/pipeline",
        "endpoints": {
            "health": "/api/v1/health",
            "transcribe": "/api/v1/transcribe",
            "translate": "/api/v1/translate",
            "pipeline": "/api/v1/pipeline",
        },
    }
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
    return info_payload


@app.get("/studio", tags=["Root"])
async def studio_ui():
    """Sirve la interfaz web profesional LSEC Studio."""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "studio_interface_not_found"}


@app.get("/avatarconfig", tags=["Avatar"])
@app.get("/avatar-config", tags=["Avatar"])
async def avatar_config_ui():
    """Sirve la interfaz web dedicada para configuración y calibración del Avatar 3D LSEC."""
    avatar_config_path = os.path.join(static_dir, "avatarconfig.html")
    if os.path.exists(avatar_config_path):
        return FileResponse(avatar_config_path)
    return {"status": "avatar_config_interface_not_found"}


@app.get("/api/info", tags=["Root"])
async def api_info() -> dict:
    """Endpoint de información del sistema en formato JSON."""
    return {
        "name": "LSEC Translator Prototype",
        "version": "0.1.0",
        "description": "Sistema de Traducción a Lengua de Señas Ecuatoriana",
        "docs": "/docs",
        "websocket": "/ws/pipeline",
        "endpoints": {
            "health": "/api/v1/health",
            "transcribe": "/api/v1/transcribe",
            "translate": "/api/v1/translate",
            "pipeline": "/api/v1/pipeline",
            "studio": "/studio",
            "avatar_config": "/avatarconfig",
        },
    }


