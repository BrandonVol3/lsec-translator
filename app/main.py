"""
LSEC Translator Prototype — Punto de entrada principal.

Inicializa FastAPI, configura middleware CORS, monta las rutas
HTTP y WebSocket, y gestiona el ciclo de vida de los servicios
pesados (Whisper) y la persistencia local SQLite mediante lifespan events.
"""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path

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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.dictionary_endpoints import dictionary_router
from app.api.animation_direct_endpoints import animation_router, animation_direct_alias_router
from app.api.endpoints import router as api_router, set_services
from app.api.websocket import ws_router, set_ws_services
from app.config import external_path, settings
from app.services.asr_service import WhisperASRService
from app.services.nlp_service import LSECTranslatorService
from app.services.storage_service import LocalStorageService

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
storage_service: LocalStorageService | None = None


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
    global asr_service, nlp_service, storage_service

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

    try:
        storage_service = LocalStorageService()
        logger.info("✓ LocalStorageService creado (persistente=%s)", storage_service.is_persistent)
    except Exception as exc:
        logger.error("✗ Error creando LocalStorageService: %s", exc)
        storage_service = None

    # Inyectar servicios en los routers
    if asr_service and nlp_service:
        set_services(asr_service, nlp_service, storage_service)
        set_ws_services(asr_service, nlp_service)

    try:
        from app.services.video_export_service import get_default_export_directory
        export_dir = get_default_export_directory(ensure_exists=True)
        logger.info("✓ Carpeta de exportación por defecto lista: %s", export_dir)
    except Exception as exc:
        logger.warning("Aviso verificando carpeta de exportación en Escritorio: %s", exc)

    logger.info("=" * 60)
    logger.info("Servicios inicializados. Servidor listo.")
    logger.info("Documentación: http://%s:%d/docs", settings.app_host, settings.app_port)
    logger.info("=" * 60)

    yield  # --- La aplicación se ejecuta aquí ---

    # Shutdown: liberar recursos
    logger.info("Cerrando servicios...")
    if storage_service:
        storage_service.close()
    logger.info("Servicios cerrados correctamente.")


# ============================================================
# Instancia de FastAPI
# ============================================================

app = FastAPI(
    title="LSEC Translator Prototype",
    description=(
        "Sistema de Transcripción Inteligente y Traducción Automática "
        "a Lengua de Señas Ecuatoriana (LSEC). "
        "Pipeline: Whisper ASR → NLP basado en reglas (glosas LSEC) → WebSocket → LSEC Studio."
    ),
    version=settings.system_version,
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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "Range"],
)


@app.middleware("http")
async def no_cache_static_code(request, call_next):
    """Fuerza revalidación (ETag/Last-Modified) de JS/HTML/CSS servidos desde /static.

    Los módulos ES internos (p. ej. ``sequence-run-scheduler.js``) se importan sin query string de
    versión, por lo que el navegador podía conservar copias obsoletas tras un cambio y seguir
    ejecutando lógica antigua del avatar (señas zurdas, dactilología difuminada, etc.).
    """
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/") and path.lower().endswith((".js", ".mjs", ".html", ".css")):
        response.headers["Cache-Control"] = "no-cache"
    return response

# ============================================================
# Montar Routers
# ============================================================

app.include_router(api_router)
app.include_router(dictionary_router)
app.include_router(animation_router)
app.include_router(animation_direct_alias_router)
app.include_router(ws_router)


# ============================================================
# Montar Archivos Estáticos y Media para la Interfaz Web LSEC Studio
# ============================================================

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Sirve un isotipo SVG como favicon para evitar 404 en el navegador."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" fill="none">'
        '<rect width="40" height="40" rx="10" fill="#10B981"/>'
        '<path d="M11 26V16C11 14.8954 11.8954 14 13 14C14.1046 14 15 14.8954 15 16V21'
        'M15 21V12C15 10.8954 15.8954 10 17 10C18.1046 10 19 10.8954 19 12V21'
        'M19 21V14C19 12.8954 19.8954 12 21 12C22.1046 12 23 12.8954 23 14V23'
        'C23 26.866 19.866 30 16 30H15C12.7909 30 11 28.2091 11 26Z" '
        'stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M27 15V25M31 18V22" stroke="#ECFDF5" stroke-width="2.4" stroke-linecap="round"/>'
        '</svg>'
    )
    return Response(content=svg, media_type="image/svg+xml")

# Montar carpeta de modelos VRM desde la carpeta Avatar del proyecto
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


avatar_dir = external_path(settings.lsec_avatar_dir, "Avatar")
if os.path.exists(avatar_dir):
    logger.info("✓ Montando /avatar desde: %s", avatar_dir)
    app.mount("/avatar", StaticFiles(directory=avatar_dir), name="avatar")

# Montar carpeta de láminas y variantes de Configuración Manual LSEC (I a IX)
cm_dir = external_path(settings.lsec_manual_config_dir, os.path.join("Diccionario LSEC", "configuracion_manual"))
if os.path.exists(cm_dir):
    logger.info("✓ Montando /configuracion-manual desde: %s", cm_dir)
    app.mount("/configuracion-manual", StaticFiles(directory=cm_dir), name="configuracion_manual")

# Montar carpeta de videos de prueba únicamente si app_debug está activo
if settings.app_debug:
    videos_dir = external_path(settings.lsec_videos_dir, "Videos de Prueba")
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
        "version": settings.system_version,
        "api_version": settings.api_version,
        "engine_version": settings.engine_version,
        "output_schema_version": settings.output_schema_version,
        "default_animation_version": settings.default_animation_version,
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


@app.get("/viewer", tags=["Avatar"])
@app.get("/reproductor", tags=["Avatar"])
async def viewer_ui():
    """Sirve el reproductor 3D interactivo autónomo con acceso a las 4.143 señas directas 1:1."""
    viewer_path = os.path.join(static_dir, "viewer.html")
    if os.path.exists(viewer_path):
        return FileResponse(viewer_path)
    return {"status": "viewer_interface_not_found"}


@app.get("/api/info", tags=["Root"])
async def api_info() -> dict:
    """Endpoint de información del sistema en formato JSON."""
    return {
        "name": "LSEC Translator Prototype",
        "version": settings.system_version,
        "api_version": settings.api_version,
        "engine_version": settings.engine_version,
        "output_schema_version": settings.output_schema_version,
        "default_animation_version": settings.default_animation_version,
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
            "viewer": "/viewer",
        },
    }
