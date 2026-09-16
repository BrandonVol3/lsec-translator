"""
Servicio de conexión y persistencia con Firebase.

Utiliza Firebase Admin SDK para almacenar perfiles de usuario,
sesiones de traducción y logs del pipeline.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class FirebaseService:
    """
    Servicio de persistencia con Firebase Firestore.

    Gestiona perfiles de usuario, sesiones de traducción y
    logs del pipeline. Si no hay credenciales configuradas,
    opera en modo in-memory (solo para desarrollo/prototipo).
    """

    def __init__(self) -> None:
        self._db = None
        self._initialized = False
        self._in_memory_store: Dict[str, Dict[str, Any]] = {
            "users": {},
            "sessions": {},
            "translations": {},
        }

        if settings.has_firebase_credentials:
            self._init_firebase()
        else:
            logger.warning(
                "Credenciales Firebase no encontradas en '%s'. "
                "Operando en modo in-memory (datos no persistentes).",
                settings.firebase_credentials_path,
            )

    def _init_firebase(self) -> None:
        """Inicializa Firebase Admin SDK y Firestore."""
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore

            # Evitar inicialización duplicada
            if not firebase_admin._apps:
                cred = credentials.Certificate(str(settings.firebase_credentials_file))
                firebase_admin.initialize_app(cred, {
                    "projectId": settings.firebase_project_id,
                })

            self._db = firestore.client()
            self._initialized = True
            logger.info("Firebase inicializado correctamente con proyecto: %s", settings.firebase_project_id)

        except ImportError:
            logger.error("firebase-admin no instalado. Ejecute: pip install firebase-admin")
            logger.warning("Continuando en modo in-memory.")
        except Exception as exc:
            logger.error("Error inicializando Firebase: %s", exc)
            logger.warning("Continuando en modo in-memory.")

    @property
    def is_connected(self) -> bool:
        """Verifica si Firebase está conectado."""
        return self._initialized and self._db is not None


    async def save_translation_log(self, log_data: Dict[str, Any]) -> str:
        """
        Almacena un log de traducción para análisis posterior.

        Args:
            log_data: Diccionario con datos de la traducción
                      (texto original, glosas, timestamps, etc.).

        Returns:
            ID del documento creado.
        """
        log_data["timestamp"] = datetime.now(timezone.utc).isoformat()

        if self.is_connected:
            try:
                doc_ref = self._db.collection("translations").document()
                doc_ref.set(log_data)
                logger.info("Log de traducción guardado: %s", doc_ref.id)
                return doc_ref.id
            except Exception as exc:
                logger.error("Error guardando log en Firestore: %s", exc)
                return self._save_in_memory("translations", log_data)
        else:
            return self._save_in_memory("translations", log_data)

    def _save_in_memory(self, collection: str, data: Dict[str, Any]) -> str:
        """Guarda datos en el almacenamiento in-memory (fallback)."""
        import uuid

        doc_id = str(uuid.uuid4())
        self._in_memory_store.setdefault(collection, {})[doc_id] = data
        logger.debug("Dato guardado in-memory [%s/%s]", collection, doc_id)
        return doc_id
