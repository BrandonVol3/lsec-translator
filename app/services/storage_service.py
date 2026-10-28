"""
Servicio de persistencia local (SQLite).

Reemplaza a Firebase para que la aplicación sea 100% offline y portable
(CD / USB / carpeta). Usa únicamente la biblioteca estándar (``sqlite3``) y
guarda el archivo en ``data/lsec_database.sqlite`` (configurable con
``LSEC_DATABASE_PATH``).

Tablas:
- ``translations``: log de cada traducción solicitada.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    session_id TEXT,
    original_text TEXT,
    glosses_count INTEGER,
    schema_version TEXT,
    payload_json TEXT NOT NULL
);
"""


class LocalStorageService:
    """
    Persistencia local ligera sobre SQLite.

    Si el archivo no se puede abrir/crear (p. ej. medio de solo lectura como un CD),
    opera en modo memoria para no interrumpir el flujo de trabajo.
    """

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self._path: Optional[Path] = Path(db_path or settings.lsec_database_path)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._persistent = False
        self._open()

    # ------------------------------------------------------------------ #
    # Conexión
    # ------------------------------------------------------------------ #
    def _open(self) -> None:
        try:
            assert self._path is not None
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
            self._persistent = True
            logger.info("Persistencia local SQLite lista: %s", self._path)
        except (OSError, sqlite3.Error) as exc:
            logger.warning(
                "No se pudo abrir '%s' (%s). Operando con SQLite en memoria (datos no persistentes).",
                self._path, exc,
            )
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
            self._persistent = False

    @property
    def is_persistent(self) -> bool:
        """True si los datos se guardan en disco (no en memoria)."""
        return self._persistent

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ------------------------------------------------------------------ #
    # Operaciones síncronas
    # ------------------------------------------------------------------ #
    def _insert_translation(self, log_data: Dict[str, Any]) -> int:
        record = dict(log_data)
        record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        with self._lock:
            assert self._conn is not None
            cur = self._conn.execute(
                "INSERT INTO translations (timestamp, session_id, original_text, glosses_count, schema_version, payload_json)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record["timestamp"],
                    record.get("session_id"),
                    record.get("original_text"),
                    record.get("glosses_count"),
                    record.get("schema_version"),
                    json.dumps(record, ensure_ascii=False, default=str),
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def _select(self, table: str, limit: int) -> List[Dict[str, Any]]:
        if table != "translations":
            raise ValueError(f"Tabla no permitida: {table}")
        with self._lock:
            assert self._conn is not None
            rows = self._conn.execute(
                f"SELECT payload_json FROM {table} ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [json.loads(r[0]) for r in reversed(rows)]

    # ------------------------------------------------------------------ #
    # API asíncrona (misma forma que el antiguo FirebaseService)
    # ------------------------------------------------------------------ #
    async def save_translation_log(self, log_data: Dict[str, Any]) -> str:
        """Almacena un log de traducción y devuelve su identificador."""
        row_id = await asyncio.to_thread(self._insert_translation, log_data)
        return str(row_id)

    async def get_translation_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._select, "translations", limit)
