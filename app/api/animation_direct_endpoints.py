"""
Router REST para consultar y servir animaciones VRM 1:1 generadas por el Pipeline LSEC v2.5
y videos originales Ultra HD del Diccionario Oficial LSEC.

Proporciona:
  GET /api/v1/animations/list?q=...&limit=50   (Ordenado estrictamente según catalogo_lsec.json)
  GET /api/v1/animations/{sign_name}           (Archivo animation.json, con soporte fallback/caché)
  GET /api/v1/animations/{sign_name}/qa        (Métricas cinemáticas QA)
  GET /api/v1/animations/{sign_name}/info      (Ficha lingüística e info.json de catálogo)
  GET /api/v1/animations/{sign_name}/video     (Streaming del video MP4 original Ultra HD)
  GET /api/v1/animations/stats                 (Estadísticas globales)
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from app.config import external_path, settings

_DICCIONARIO_LSEC_DIR = external_path(settings.lsec_dictionary_root, "Diccionario LSEC")
if _DICCIONARIO_LSEC_DIR.is_dir() and str(_DICCIONARIO_LSEC_DIR) not in sys.path:
    sys.path.insert(0, str(_DICCIONARIO_LSEC_DIR))

try:
    import lsec_non_manual_standard as lsec_cnm
except Exception:
    lsec_cnm = None  # type: ignore

logger = logging.getLogger(__name__)

animation_router = APIRouter(prefix="/api/v1/animations", tags=["Animaciones Directas 1:1 (VRM)"])

# Directorios candidatos para localizar las animaciones generadas (100% disco local)
# Versión 2.7 estandarizada preferida, con fallback a versión 2.6 corregida y versión 2.5
CANDIDATE_PATHS = [
    external_path(settings.lsec_animations_v27_dir, "Diccionario LSEC/senas_vrm_standardized_v2.7"),
    external_path("", "senas_vrm_standardized_v2.7"),
    external_path(settings.lsec_animations_v26_dir, "Diccionario LSEC/senas_vrm_direct_v2.6"),
    external_path("", "senas_vrm_direct_v2.6"),
    external_path(settings.lsec_animations_dir, "Diccionario LSEC/senas_vrm_direct"),
    external_path("", "senas_vrm_direct"),
]

V27_CANDIDATE_PATHS = [
    external_path(settings.lsec_animations_v27_dir, "Diccionario LSEC/senas_vrm_standardized_v2.7"),
    external_path("", "senas_vrm_standardized_v2.7"),
]

V26_CANDIDATE_PATHS = [
    external_path(settings.lsec_animations_v26_dir, "Diccionario LSEC/senas_vrm_direct_v2.6"),
    external_path("", "senas_vrm_direct_v2.6"),
]

V25_CANDIDATE_PATHS = [
    external_path(settings.lsec_animations_dir, "Diccionario LSEC/senas_vrm_direct"),
    external_path("", "senas_vrm_direct"),
    external_path("", "Diccionario LSEC/senas_vrm_direct"),
    external_path("", "_archive/Diccionario LSEC/senas_vrm_direct"),
]

# Directorios candidatos para videos originales Ultra HD e ilustraciones (100% disco local)
UHD_CANDIDATE_PATHS = [
    external_path(settings.lsec_uhd_dir, "Diccionario LSEC/senas_ultra_hd"),
    external_path("", "senas_ultra_hd"),
]

# Directorios candidatos de respaldo para videos originales sanos del corpus (100% disco local)
SENAS_CANDIDATE_PATHS = [
    external_path(settings.lsec_senas_dir, "Diccionario LSEC/senas"),
    external_path("", "senas"),
]

_resolved_dir: Optional[Path] = None
_cached_signs: Optional[List[str]] = None
_cached_metadata: Optional[Dict[str, Dict[str, Any]]] = None
_cached_ordered_items: Optional[List[Dict[str, Any]]] = None
_video_health_cache: Dict[Tuple[str, float, int], bool] = {}
_dir_norm_map_cache: Dict[str, Dict[str, List[Path]]] = {}
_v27_stroke_index_cache: Optional[Dict[str, Any]] = None
_v27_stroke_norm_map: Optional[Dict[str, Dict[str, Any]]] = None


def _get_norm_dir_map(base_dir: Path) -> Dict[str, List[Path]]:
    """Construye y cachea un índice O(1) de nombre normalizado -> carpetas dentro de base_dir."""
    key = str(base_dir.resolve())
    if key in _dir_norm_map_cache:
        return _dir_norm_map_cache[key]
    mapping: Dict[str, List[Path]] = {}
    try:
        with os.scandir(str(base_dir)) as it:
            for entry in it:
                if entry.is_dir() and not entry.name.startswith("."):
                    nk = normalize_text(entry.name)
                    if nk:
                        mapping.setdefault(nk, []).append(Path(entry.path))
    except Exception:
        pass
    _dir_norm_map_cache[key] = mapping
    return mapping


def normalize_text(text: str) -> str:
    """Normaliza texto para comparaciones seguras de nombres de señas."""
    if not text:
        return ""
    s = text.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def get_v27_dir() -> Optional[Path]:
    """Devuelve el directorio base de animaciones directas VRM v2.7 estandarizadas si existe."""
    for candidate in V27_CANDIDATE_PATHS:
        if candidate and candidate.is_dir():
            return candidate
    return None


def get_v27_stroke_index() -> Dict[str, Any]:
    """Carga y cachea en memoria el índice de trazos activos precalculado (stroke_index.json) para v2.7."""
    global _v27_stroke_index_cache, _v27_stroke_norm_map
    if _v27_stroke_index_cache is not None:
        return _v27_stroke_index_cache

    candidates: List[Path] = []
    v27_dir = get_v27_dir()
    if v27_dir:
        candidates.append(v27_dir / "stroke_index.json")
    local_data_idx = Path(__file__).resolve().parent.parent / "data" / "stroke_index_v27.json"
    candidates.append(local_data_idx)

    for idx_path in candidates:
        if idx_path and idx_path.is_file():
            try:
                payload = json.loads(idx_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("signs"), dict):
                    _v27_stroke_index_cache = payload
                    norm_map: Dict[str, Dict[str, Any]] = {}
                    for k, v in payload["signs"].items():
                        if isinstance(v, dict):
                            nk = normalize_text(k)
                            if nk and nk not in norm_map:
                                norm_map[nk] = v
                    _v27_stroke_norm_map = norm_map
                    logger.info("✓ Índice de trazos v2.7 cargado (%d señas) desde %s", len(payload["signs"]), idx_path)
                    return _v27_stroke_index_cache
            except Exception as exc:
                logger.warning("Error leyendo stroke_index.json en %s: %s", idx_path, exc)

    _v27_stroke_index_cache = {"version": "2.7", "totalSigns": 0, "summary": {}, "signs": {}}
    _v27_stroke_norm_map = {}
    return _v27_stroke_index_cache


def get_sign_stroke_entry(sign_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Obtiene la entrada de trazo activo y poses de ancla para una seña del catálogo v2.7."""
    if not sign_name:
        return None
    idx_payload = get_v27_stroke_index()
    signs_map = idx_payload.get("signs") or {}
    if not signs_map:
        return None
    clean = unicodedata.normalize("NFC", sign_name.strip())
    if clean in signs_map:
        return signs_map[clean]
    if sign_name in signs_map:
        return signs_map[sign_name]
    if _v27_stroke_norm_map:
        return _v27_stroke_norm_map.get(normalize_text(clean))
    return None


def get_v26_dir() -> Optional[Path]:
    """Devuelve el directorio base de animaciones directas VRM v2.6 corregidas si existe."""
    for candidate in V26_CANDIDATE_PATHS:
        if candidate and candidate.is_dir():
            return candidate
    return None


def get_v25_dir() -> Path:
    """Devuelve el directorio base de animaciones directas VRM v2.5 (catálogo completo)."""
    for candidate in V25_CANDIDATE_PATHS:
        if candidate and candidate.is_dir():
            return candidate
    archive_fallback = external_path("", "_archive/Diccionario LSEC/senas_vrm_direct")
    if archive_fallback.is_dir():
        return archive_fallback
    return external_path(settings.lsec_animations_dir, "Diccionario LSEC/senas_vrm_direct")


def get_animations_dir() -> Path:
    """Devuelve el directorio base de animaciones directas VRM (v2.7 preferente, con fallback a v2.6 -> v2.5 / _archive)."""
    global _resolved_dir
    if _resolved_dir and _resolved_dir.is_dir():
        return _resolved_dir

    v27 = get_v27_dir()
    if v27 and v27.is_dir():
        _resolved_dir = v27
        logger.info("✓ Directorio de animaciones directas VRM resuelto en (v2.7 primario): %s", _resolved_dir)
        return _resolved_dir

    v26 = get_v26_dir()
    if v26 and v26.is_dir():
        _resolved_dir = v26
        logger.info("✓ Directorio de animaciones directas VRM resuelto en (v2.6 fallback): %s", _resolved_dir)
        return _resolved_dir

    _resolved_dir = get_v25_dir()
    logger.info("✓ Directorio de animaciones directas VRM resuelto en (v2.5 fallback): %s", _resolved_dir)
    return _resolved_dir


def get_uhd_dir() -> Optional[Path]:
    """Devuelve el directorio base de señas Ultra HD."""
    configured = os.environ.get("LSEC_UHD_DIR") or settings.lsec_uhd_dir
    if configured:
        path = external_path(configured, "Diccionario LSEC/senas_ultra_hd")
        return path if path.is_dir() else None
    for candidate in UHD_CANDIDATE_PATHS:
        if candidate and candidate.is_dir():
            return candidate
    return None


def get_senas_dir() -> Optional[Path]:
    """Devuelve el directorio base del corpus original de señas (fallback sano)."""
    configured = os.environ.get("LSEC_SENAS_DIR") or settings.lsec_senas_dir
    if configured:
        path = external_path(configured, "Diccionario LSEC/senas")
        return path if path.is_dir() else None
    for candidate in SENAS_CANDIDATE_PATHS:
        if candidate and candidate.is_dir():
            return candidate
    return None


def _is_video_stream_healthy(video_path: Path) -> bool:
    """
    Verifica rápidamente que un archivo de video local sea íntegro y reproducible
    (cajas ISO-BMFF íntegras en MP4, primer cuadro decodificable, demuxeado completo
    desde el paquete #0 sin truncamiento y paquetes NAL H.264 íntegros).
    Cachea el resultado por (ruta, mtime, tamaño).
    """
    try:
        if not video_path or not video_path.is_file():
            return False
        st = video_path.stat()
        file_size = st.st_size
        if file_size < 1024:
            return False
        cache_key = (str(video_path), st.st_mtime, file_size)
        if cache_key in _video_health_cache:
            return _video_health_cache[cache_key]
    except Exception:
        return False

    import struct
    healthy = True
    try:
        if video_path.suffix.lower() == ".mp4":
            with video_path.open("rb") as f:
                head = f.read(min(file_size, 65536))
                if b"moov" not in head and file_size <= 65536:
                    healthy = False
                elif b"moof" not in head:
                    # MP4 estándar no fragmentado: validar cajas ISO-BMFF de nivel superior
                    if head.count(b"moov") > 1:
                        healthy = False
                    else:
                        pos = 0
                        moov_count = 0
                        mdat_count = 0
                        while pos + 8 <= file_size:
                            f.seek(pos)
                            hdr = f.read(16)
                            if len(hdr) < 8:
                                break
                            bsz, btype = struct.unpack(">I4s", hdr[:8])
                            if bsz == 1 and len(hdr) >= 16:
                                bsz = struct.unpack(">Q", hdr[8:16])[0]
                            elif bsz == 0:
                                bsz = file_size - pos
                            if bsz < 8 or pos + bsz > file_size:
                                healthy = False
                                break
                            if btype == b"moov":
                                moov_count += 1
                            elif btype == b"mdat":
                                mdat_count += 1
                            pos += bsz
                        if moov_count != 1 or mdat_count < 1:
                            healthy = False

        if healthy:
            import av
            codec = ""
            expected_frames = 0
            expected_duration_sec = 0.0
            with av.open(str(video_path), mode="r", timeout=3.0) as container:
                if not container.streams.video:
                    healthy = False
                else:
                    vs = container.streams.video[0]
                    codec = vs.codec_context.name or ""
                    expected_frames = vs.frames or 0
                    if vs.duration is not None and vs.time_base is not None:
                        expected_duration_sec = float(vs.duration * vs.time_base)
                    elif container.duration is not None:
                        expected_duration_sec = float(container.duration) / 1_000_000.0
                    first_frame = next(container.decode(video=0), None)
                    if first_frame is None:
                        healthy = False

            if healthy:
                # Abrir contenedor fresco para demuxear desde el paquete #0 sin omitir paquetes de lookahead
                with av.open(str(video_path), mode="r", timeout=3.0) as c2:
                    vs2 = c2.streams.video[0]
                    tb2 = float(vs2.time_base) if vs2.time_base is not None else 0.0
                    total_pkts = 0
                    max_pts_sec = 0.0
                    for pkt in c2.demux(video=0):
                        if pkt.dts is None and pkt.pts is None:
                            continue
                        total_pkts += 1
                        pts_val = pkt.pts if pkt.pts is not None else pkt.dts
                        if pts_val is not None and tb2 > 0:
                            end_t = float(pts_val + (pkt.duration or 0)) * tb2
                            if end_t > max_pts_sec:
                                max_pts_sec = end_t
                        b = bytes(pkt)
                        n = len(b)
                        if n == 0:
                            healthy = False
                            break
                        if codec == "h264" and b[:4] != b"\x00\x00\x00\x01" and b[:3] != b"\x00\x00\x01":
                            pos = 0
                            while pos < n:
                                if pos + 4 > n:
                                    healthy = False
                                    break
                                nal_sz = struct.unpack(">I", b[pos : pos + 4])[0]
                                if nal_sz <= 0 or pos + 4 + nal_sz > n:
                                    healthy = False
                                    break
                                pos += 4 + nal_sz
                            if not healthy:
                                break
                    if healthy:
                        if total_pkts == 0:
                            healthy = False
                        elif expected_frames > 0 and total_pkts < expected_frames:
                            healthy = False
                        elif expected_duration_sec > 0.5 and max_pts_sec > 0 and max_pts_sec < expected_duration_sec * 0.75:
                            healthy = False
    except ImportError:
        healthy = True
    except Exception:
        healthy = False

    _video_health_cache[cache_key] = healthy
    return healthy


_cached_catalog_mtime: float = 0.0
_cached_handshape_schema_mtime: float = 0.0
_cached_handshape_schema: Optional[Dict[str, Any]] = None

_MAIN_CM_IDS = {
    *[f"configuracion_manual_{i}" for i in range(1, 10)],
    "configuracion_manual_rostro",
    "configuracion_manual_*",
}


def get_configuracion_manual_dir() -> Optional[Path]:
    """Devuelve el directorio local de láminas y variantes de Configuración Manual (I a IX, Rostro y *)."""
    candidates = [
        external_path(settings.lsec_manual_config_dir, "Diccionario LSEC/configuracion_manual"),
        external_path("", "configuracion_manual"),
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def _load_handshape_schema() -> Dict[str, Any]:
    """Carga el esquema de las 9 configuraciones manuales + Rostro + * y sus sub-variantes."""
    global _cached_handshape_schema, _cached_handshape_schema_mtime
    cm_dir = get_configuracion_manual_dir()
    if cm_dir:
        schema_file = cm_dir / "esquema_variantes.json"
        if schema_file.is_file():
            try:
                mtime = schema_file.stat().st_mtime
                if _cached_handshape_schema is not None and _cached_handshape_schema_mtime == mtime:
                    return _cached_handshape_schema
                _cached_handshape_schema = json.loads(schema_file.read_text(encoding="utf-8"))
                _cached_handshape_schema_mtime = mtime
                return _cached_handshape_schema
            except Exception as exc:
                logger.warning("Error leyendo esquema_variantes.json: %s", exc)
    if _cached_handshape_schema is not None:
        return _cached_handshape_schema
    _cached_handshape_schema = {}
    return _cached_handshape_schema


def _enrich_item_with_handshape_meta(item: Dict[str, Any]) -> Dict[str, Any]:
    """Asegura que un ítem de seña contenga metadata completa de Configuración Manual, sub-variante y URLs."""
    schema = _load_handshape_schema()
    cats = [str(c) for c in (item.get("categorias") or [])]

    cm_id = item.get("hand_configuration") or item.get("configuracion_manual")
    if not cm_id or cm_id not in _MAIN_CM_IDS:
        cm_id = next((c for c in cats if c in _MAIN_CM_IDS), "configuracion_manual_*")
    item["hand_configuration"] = cm_id

    alfa = item.get("alphabetical_group")
    if not alfa:
        alfa = next((c for c in cats if c.startswith("alfa-")), None)
    item["alphabetical_group"] = alfa

    cm_meta = schema.get(cm_id) or {}
    roman = cm_meta.get("roman") or ("*" if cm_id.endswith("*") else cm_id.replace("configuracion_manual_", "").upper())
    color_hex = cm_meta.get("color_hex") or "#64748B"
    sheet_img = cm_meta.get("sheet_image")
    sheet_url = f"/configuracion-manual/{sheet_img}" if sheet_img else None

    v_id = item.get("hand_variant") or item.get("configuracion_manual_variante")
    if not v_id:
        v_id = next(
            (c for c in cats if c.startswith(f"{cm_id}_") and c not in _MAIN_CM_IDS),
            "configuracion_manual_*_sin_recuadro" if cm_id == "configuracion_manual_*" else f"{cm_id}_base",
        )
    item["hand_variant"] = v_id

    v_meta: Dict[str, Any] = {}
    for v in cm_meta.get("variants") or []:
        if v.get("variant_id") == v_id:
            v_meta = v
            break
    if not v_meta and (cm_meta.get("variants") or []):
        v_meta = cm_meta["variants"][0]

    v_short = item.get("hand_variant_key") or item.get("configuracion_manual_variante_key") or v_meta.get("short_key") or "base"
    v_label = item.get("hand_variant_label") or item.get("configuracion_manual_variante_label") or v_meta.get("label") or f"{roman}-{v_short.upper()}"
    v_img_rel = v_meta.get("image_file")
    v_img_url = f"/configuracion-manual/{v_img_rel}" if v_img_rel else None

    is_face_only = bool(
        cm_id == "configuracion_manual_rostro"
        or cm_meta.get("face_only")
        or item.get("face_only")
        or item.get("solo_rostro")
    )
    arms_rest = bool(
        is_face_only
        or cm_meta.get("arms_in_rest_pose")
        or item.get("arms_in_rest_pose")
        or item.get("brazos_en_reposo")
    )

    item["hand_variant_key"] = v_short
    item["hand_variant_label"] = v_label
    item["face_only"] = is_face_only
    item["arms_in_rest_pose"] = arms_rest

    if lsec_cnm is not None:
        cnm_cls = lsec_cnm.classify_sign_non_manual(
            sign_name=str(item.get("sign") or item.get("palabra") or ""),
            slug=str(item.get("slug") or ""),
            palabra=str(item.get("palabra") or item.get("sign") or ""),
            hand_configuration=cm_id,
            hand_variant=v_id,
            solo_rostro=is_face_only,
            extra_metadata=item,
        )
        item["has_explicit_facial_expression"] = cnm_cls["hasExplicitFacialExpression"]
        item["default_neutral_facial_mode"] = cnm_cls["defaultNeutralMode"]
        item["facial_archetype"] = cnm_cls["archetype"]
        item["facial_archetype_label"] = cnm_cls["archetypeLabel"]
        item["non_manual_standard"] = cnm_cls
    else:
        item["has_explicit_facial_expression"] = is_face_only
        item["default_neutral_facial_mode"] = not is_face_only
        item["facial_archetype"] = "plea_empathy" if is_face_only else "neutral"
        item["facial_archetype_label"] = "Expresión Facial" if is_face_only else "Neutral (Por Defecto)"

    item["hand_configuration_meta"] = {
        "id": cm_id,
        "number": cm_meta.get("number"),
        "roman": roman,
        "name": cm_meta.get("name") or cm_id,
        "color_hex": color_hex,
        "sheet_image": sheet_img,
        "sheet_url": sheet_url,
        "variant_id": v_id,
        "variant_key": v_short,
        "variant_label": v_label,
        "variant_description": v_meta.get("description") or v_label,
        "variant_image_url": v_img_url,
        "face_only": is_face_only,
        "arms_in_rest_pose": arms_rest,
    }
    return item


def _load_catalog_cache():
    """Carga y cachea la lista ordenada según catalogo_lsec.json y metadata enriquecida (normalizada en NFC y sin duplicados)."""
    global _cached_signs, _cached_metadata, _cached_ordered_items, _cached_catalog_mtime

    base_dir = get_animations_dir()
    ordered_json = base_dir / "catalogo_ordenado.json"
    if not ordered_json.is_file():
        # Probar en directorio superior si existiese
        parent_ordered = base_dir.parent / "catalogo_ordenado_vrm.json"
        if parent_ordered.is_file():
            ordered_json = parent_ordered

    current_mtime = 0.0
    if ordered_json.is_file():
        try:
            current_mtime = ordered_json.stat().st_mtime
        except OSError:
            current_mtime = 0.0

    schema = _load_handshape_schema()
    effective_mtime = current_mtime + _cached_handshape_schema_mtime

    if (
        _cached_signs is not None
        and _cached_metadata is not None
        and _cached_catalog_mtime == effective_mtime
    ):
        return

    signs_list: List[str] = []
    meta_dict: Dict[str, Dict[str, Any]] = {}
    ordered_items: List[Dict[str, Any]] = []

    if ordered_json.is_file():
        try:
            with open(ordered_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_signs = data.get("signs", [])
            for item in raw_signs:
                raw_name = item.get("sign")
                if not raw_name:
                    continue
                s_name = unicodedata.normalize("NFC", str(raw_name).strip())
                if not s_name or s_name in meta_dict:
                    continue
                norm_item = dict(item)
                norm_item["sign"] = s_name
                if "palabra" in norm_item and isinstance(norm_item["palabra"], str):
                    norm_item["palabra"] = unicodedata.normalize("NFC", norm_item["palabra"].strip())
                _enrich_item_with_handshape_meta(norm_item)
                signs_list.append(s_name)
                meta_dict[s_name] = norm_item
                ordered_items.append(norm_item)
            _cached_signs = signs_list
            _cached_metadata = meta_dict
            _cached_ordered_items = ordered_items
            _cached_catalog_mtime = effective_mtime
            logger.info("✓ Cargadas %d señas ordenadas (NFC únicas) desde %s", len(_cached_signs), ordered_json)
            return
        except Exception as exc:
            logger.warning("Error leyendo %s: %s", ordered_json, exc)

    # Fallback 1: qa_summary.csv
    csv_file = base_dir / "qa_summary.csv"
    if csv_file.is_file():
        try:
            with open(csv_file, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader, start=1):
                    raw_sign = row.get("sign", "").strip()
                    sign = unicodedata.normalize("NFC", raw_sign)
                    if sign and sign not in meta_dict:
                        signs_list.append(sign)
                        palabra_nfc = unicodedata.normalize("NFC", (row.get("palabra") or sign).strip())
                        item_meta = _enrich_item_with_handshape_meta({
                            "sign": sign,
                            "catalog_index": int(row.get("catalog_index", idx)) if row.get("catalog_index") else idx,
                            "slug": row.get("slug", ""),
                            "palabra": palabra_nfc,
                            "qa": row,
                        })
                        meta_dict[sign] = item_meta
                        ordered_items.append(item_meta)
            _cached_signs = signs_list
            _cached_metadata = meta_dict
            _cached_ordered_items = ordered_items
            logger.info("✓ Indexadas %d señas únicas (NFC) desde qa_summary.csv", len(_cached_signs))
            return
        except Exception as exc:
            logger.warning("Error leyendo qa_summary.csv: %s", exc)

    # Fallback 2: listdir directo
    try:
        raw = [
            unicodedata.normalize("NFC", name) for name in os.listdir(base_dir)
            if not name.startswith(".") and not name.endswith(".csv") and not name.endswith(".json")
            and (base_dir / name).is_dir()
        ]
        signs_list = sorted(set(raw), key=lambda s: s.lower())
        for idx, s in enumerate(signs_list, start=1):
            meta_dict[s] = _enrich_item_with_handshape_meta({"sign": s, "catalog_index": idx, "palabra": s})
            ordered_items.append(meta_dict[s])
        _cached_signs = signs_list
        _cached_metadata = meta_dict
        _cached_ordered_items = ordered_items
        logger.info("✓ Indexadas %d señas únicas (NFC) mediante listdir", len(_cached_signs))
    except Exception as exc:
        logger.warning("Error listando directorio %s: %s", base_dir, exc)
        _cached_signs = []
        _cached_metadata = {}
        _cached_ordered_items = []


def get_available_signs() -> List[str]:
    """Devuelve la lista de señas en el orden oficial del catálogo."""
    _load_catalog_cache()
    return _cached_signs or []


def get_sign_metadata(sign_name: str) -> Optional[Dict[str, Any]]:
    """Obtiene la metadata oficial y lingüística de una seña."""
    _load_catalog_cache()
    if not _cached_metadata:
        return None

    sign_nfc = unicodedata.normalize("NFC", sign_name)

    # Búsqueda exacta (NFC o literal)
    if sign_nfc in _cached_metadata:
        return _cached_metadata[sign_nfc]
    if sign_name in _cached_metadata:
        return _cached_metadata[sign_name]

    # Búsqueda insensible a mayúsculas y acentos
    norm_target = normalize_text(sign_nfc)
    for name, meta in _cached_metadata.items():
        if (
            normalize_text(name) == norm_target
            or normalize_text(meta.get("palabra", "")) == norm_target
            or normalize_text(meta.get("slug", "")) == norm_target
        ):
            return meta

    # Búsqueda en info.json dentro de la carpeta local de la seña
    base_dir = get_animations_dir()
    for candidate_name in (sign_nfc, sign_name, unicodedata.normalize("NFD", sign_nfc)):
        info_file = base_dir / candidate_name / "info.json"
        if info_file.is_file():
            try:
                with open(info_file, "r", encoding="utf-8") as f:
                    info_obj = json.load(f)
                return _enrich_item_with_handshape_meta(info_obj)
            except Exception:
                pass

    return None


def _cm_sort_key(cm_id: Optional[str]) -> int:
    if not cm_id:
        return 99
    if cm_id.endswith("rostro"):
        return 10
    if cm_id.endswith("*"):
        return 11
    m = re.search(r"(\d+)$", cm_id)
    return int(m.group(1)) if m else 99


def _variant_sort_key(v_key: Optional[str]) -> int:
    if not v_key or v_key in ("base", "sin_recuadro"):
        return 0
    m = re.search(r"(\d+)$", str(v_key))
    return int(m.group(1)) if m else 99


@animation_router.get("/list", summary="Lista todas las señas con animación directa 1:1 con filtros de Configuración Manual, Sub-variante y Letra")
async def list_animations(
    q: Optional[str] = Query(None, description="Término de búsqueda opcional"),
    hand_config: Optional[str] = Query(None, description="Filtrar por Configuración Manual (ej. configuracion_manual_3, configuracion_manual_rostro o configuracion_manual_*)"),
    hand_variant: Optional[str] = Query(None, description="Filtrar por sub-variante (ej. configuracion_manual_3_v2 o configuracion_manual_rostro_base)"),
    alfa: Optional[str] = Query(None, description="Filtrar por letra inicial del catálogo (ej. alfa-a)"),
    category: Optional[str] = Query(None, description="Filtrar por categoría arbitraria en info.json"),
    sort_by: Optional[str] = Query("catalog", description="Ordenamiento: 'catalog' (defecto), 'hand_config', 'alfa'"),
    version: Optional[str] = Query(None, description="Versión preferida: '2.7', '2.6' o '2.5'"),
    limit: int = Query(5000, ge=1, le=10000, description="Límite de resultados devueltos"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginación"),
) -> Dict[str, Any]:
    """
    Retorna la lista de señas directas 1:1 ordenadas según catalogo_lsec.json (o por configuración manual),
    incluyendo metadata de Configuración Manual (I–IX, Rostro y *), sub-variante y letra para verificación.
    """
    _load_catalog_cache()
    all_signs = _cached_signs or []
    all_items = _cached_ordered_items or []

    v27_dir = get_v27_dir()
    v26_dir = get_v26_dir()
    eff_version = version or ("2.7" if v27_dir else ("2.6" if v26_dir else "2.5"))
    if eff_version == "2.7" and v27_dir:
        pipeline_ver = "2.7_Estandarizado"
    elif eff_version == "2.6" and v26_dir:
        pipeline_ver = "2.6_Directo_1a1_corregido"
    else:
        pipeline_ver = "2.5_Directo_1a1"

    # Normalizar parámetros de filtro
    hc_filter = hand_config.strip() if hand_config and hand_config.strip() else None
    if hc_filter and hc_filter.isdigit():
        hc_filter = f"configuracion_manual_{hc_filter}"
    elif hc_filter and hc_filter.lower() in ("rostro", "face"):
        hc_filter = "configuracion_manual_rostro"
    elif hc_filter == "*":
        hc_filter = "configuracion_manual_*"

    hv_filter = hand_variant.strip() if hand_variant and hand_variant.strip() else None
    alfa_filter = alfa.strip().lower() if alfa and alfa.strip() else None
    if alfa_filter and len(alfa_filter) == 1 and alfa_filter.isalpha():
        alfa_filter = f"alfa-{alfa_filter}"
    cat_filter = category.strip().lower() if category and category.strip() else None
    q_term = normalize_text(q) if (q and q.strip()) else None

    filtered_pairs: List[Tuple[str, Dict[str, Any]]] = []
    for s, it in zip(all_signs, all_items):
        if hc_filter and it.get("hand_configuration") != hc_filter:
            continue
        if hv_filter and it.get("hand_variant") != hv_filter and it.get("hand_variant_key") != hv_filter:
            continue
        if alfa_filter:
            it_alfa = (it.get("alphabetical_group") or "").lower()
            it_cats = [str(c).lower() for c in (it.get("categorias") or [])]
            if it_alfa != alfa_filter and alfa_filter not in it_cats:
                continue
        if cat_filter:
            it_cats = [str(c).lower() for c in (it.get("categorias") or [])]
            if cat_filter not in it_cats:
                continue
        if q_term:
            if q_term not in normalize_text(s) and q_term not in normalize_text(it.get("palabra", "")):
                continue
        filtered_pairs.append((s, it))

    if sort_by == "hand_config":
        filtered_pairs.sort(
            key=lambda pair: (
                _cm_sort_key(pair[1].get("hand_configuration")),
                _variant_sort_key(pair[1].get("hand_variant_key")),
                str(pair[1].get("alphabetical_group") or "zzz"),
                int(pair[1].get("catalog_index") or 999999),
            )
        )
    elif sort_by == "alfa":
        filtered_pairs.sort(
            key=lambda pair: (
                str(pair[1].get("alphabetical_group") or "zzz"),
                int(pair[1].get("catalog_index") or 999999),
            )
        )

    filtered_signs = [p[0] for p in filtered_pairs]
    filtered_items = [p[1] for p in filtered_pairs]

    # Calcular facetas sobre el conjunto filtrado para poblar selectores dinámicos
    cm_facets: Dict[str, int] = {}
    variant_facets: Dict[str, int] = {}
    alfa_facets: Dict[str, int] = {}
    for _, it in filtered_pairs:
        cm_k = it.get("hand_configuration") or "configuracion_manual_*"
        hv_k = it.get("hand_variant") or f"{cm_k}_base"
        al_k = it.get("alphabetical_group") or "sin-alfa"
        cm_facets[cm_k] = cm_facets.get(cm_k, 0) + 1
        variant_facets[hv_k] = variant_facets.get(hv_k, 0) + 1
        alfa_facets[al_k] = alfa_facets.get(al_k, 0) + 1

    total = len(filtered_signs)
    paged_signs = filtered_signs[offset : offset + limit]
    paged_items = filtered_items[offset : offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "query": q,
        "version": eff_version,
        "pipeline_version": pipeline_ver,
        "filters": {
            "hand_config": hc_filter,
            "hand_variant": hv_filter,
            "alfa": alfa_filter,
            "category": cat_filter,
            "sort_by": sort_by or "catalog",
        },
        "facets": {
            "by_hand_configuration": cm_facets,
            "by_hand_variant": variant_facets,
            "by_alphabet": alfa_facets,
        },
        "order": "Catálogo Oficial Diccionario LSEC (CONADIS)",
        "signs": paged_signs,
        "items": paged_items,
    }


@animation_router.get("/handshapes", summary="Obtiene el catálogo jerárquico de Configuraciones Manuales LSEC (I–IX, Rostro y *) y sus sub-variantes")
async def get_handshapes_catalog(
    include_signs: bool = Query(False, description="Incluir el listado completo de señas dentro de cada configuración y sub-variante"),
) -> Dict[str, Any]:
    """
    Devuelve la estructura oficial de las 9 Configuraciones Manuales (I a IX) + 'Rostro' + '*',
    sus colores oficiales, URLs de las láminas completas y de los recortes de sub-variantes,
    junto con el conteo exacto de señas por configuración, sub-variante y letra alfabética.
    """
    _load_catalog_cache()
    schema = _load_handshape_schema()
    all_items = _cached_ordered_items or []

    all_cm_keys = [f"configuracion_manual_{i}" for i in range(1, 10)] + ["configuracion_manual_rostro", "configuracion_manual_*"]
    configurations: List[Dict[str, Any]] = []
    cm_lookup: Dict[str, Dict[str, Any]] = {}

    for cm_key in all_cm_keys:
        cm_meta = schema.get(cm_key) or {
            "id": cm_key,
            "number": None if cm_key.endswith("*") else (10 if cm_key.endswith("rostro") else int(cm_key.split("_")[-1])),
            "roman": "*" if cm_key.endswith("*") else ("ROSTRO" if cm_key.endswith("rostro") else cm_key.split("_")[-1]),
            "name": cm_key,
            "color_hex": "#64748B",
            "sheet_image": None if cm_key.endswith("*") else f"{cm_key}.jpg",
            "variants": [],
        }
        sheet_img = cm_meta.get("sheet_image")
        sheet_url = f"/configuracion-manual/{sheet_img}" if sheet_img else None

        variants_list: List[Dict[str, Any]] = []
        variants_map: Dict[str, Dict[str, Any]] = {}
        for v in cm_meta.get("variants") or []:
            v_id = v["variant_id"]
            v_img = v.get("image_file")
            v_entry: Dict[str, Any] = {
                "variant_id": v_id,
                "short_key": v.get("short_key") or "base",
                "label": v.get("label") or v_id,
                "description": v.get("description") or "",
                "image_file": v_img,
                "image_url": f"/configuracion-manual/{v_img}" if v_img else None,
                "total_signs": 0,
            }
            if include_signs:
                v_entry["signs"] = []
            variants_list.append(v_entry)
            variants_map[v_id] = v_entry

        cfg_entry: Dict[str, Any] = {
            "id": cm_key,
            "number": cm_meta.get("number"),
            "roman": cm_meta.get("roman"),
            "name": cm_meta.get("name"),
            "color_hex": cm_meta.get("color_hex"),
            "sheet_image": sheet_img,
            "sheet_url": sheet_url,
            "face_only": bool(cm_meta.get("face_only") or cm_key == "configuracion_manual_rostro"),
            "arms_in_rest_pose": bool(cm_meta.get("arms_in_rest_pose") or cm_key == "configuracion_manual_rostro"),
            "total_signs": 0,
            "variants_count": len(variants_list),
            "by_alphabet": {},
            "variants": variants_list,
            "_variants_map": variants_map,
        }
        if include_signs:
            cfg_entry["signs"] = []
        configurations.append(cfg_entry)
        cm_lookup[cm_key] = cfg_entry

    global_alfa_counts: Dict[str, int] = {}
    for it in all_items:
        cm_key = it.get("hand_configuration") or "configuracion_manual_*"
        if cm_key not in cm_lookup:
            cm_key = "configuracion_manual_*"
        cfg = cm_lookup[cm_key]
        cfg["total_signs"] += 1

        alfa = it.get("alphabetical_group") or "sin-alfa"
        cfg["by_alphabet"][alfa] = cfg["by_alphabet"].get(alfa, 0) + 1
        global_alfa_counts[alfa] = global_alfa_counts.get(alfa, 0) + 1

        v_id = it.get("hand_variant") or f"{cm_key}_base"
        v_map = cfg["_variants_map"]
        v_target = v_map.get(v_id)
        if v_target is None and v_map:
            v_target = next(iter(v_map.values()))
        if v_target is not None:
            v_target["total_signs"] += 1
            if include_signs:
                v_target["signs"].append(it["sign"])

        if include_signs:
            cfg["signs"].append(it["sign"])

    for cfg in configurations:
        cfg.pop("_variants_map", None)

    return {
        "total_signs": len(all_items),
        "total_configurations": len(configurations),
        "total_handshape_variants": sum(len(c["variants"]) for c in configurations if c["id"] != "configuracion_manual_*"),
        "by_alphabet": dict(sorted(global_alfa_counts.items())),
        "configurations": configurations,
    }


@animation_router.get("/stats", summary="Estadísticas globales de cobertura y QA del pipeline 1:1")
async def animation_stats(version: Optional[str] = Query(None, description="Versión preferida: '2.7', '2.6' o '2.5'")) -> Dict[str, Any]:
    v27_dir = get_v27_dir()
    v26_dir = get_v26_dir()
    v25_dir = get_v25_dir()
    eff_version = version or ("2.7" if v27_dir else ("2.6" if v26_dir else "2.5"))
    if eff_version == "2.7" and v27_dir:
        target_dir = v27_dir
    elif eff_version == "2.6" and v26_dir:
        target_dir = v26_dir
    else:
        target_dir = v25_dir
    all_signs = get_available_signs()
    summary_csv = target_dir / "qa_summary.csv"

    approved = 0
    needs_review = 0
    fps_counts: Dict[str, int] = {}

    if summary_csv.is_file():
        try:
            with open(summary_csv, "r", encoding="utf-8", errors="replace") as fp:
                reader = csv.DictReader(fp)
                for row in reader:
                    if row.get("needs_review") == "True":
                        needs_review += 1
                    else:
                        approved += 1
                    fps_val = str(row.get("fps", "60.0"))
                    fps_counts[fps_val] = fps_counts.get(fps_val, 0) + 1
        except Exception as exc:
            logger.warning("Error leyendo qa_summary.csv: %s", exc)

    if eff_version == "2.7" and v27_dir:
        ver_tag = "2.7_Estandarizado"
    elif eff_version == "2.6" and v26_dir:
        ver_tag = "2.6_Directo_1a1_corregido"
    else:
        ver_tag = "2.5_Directo_1a1"

    v26_approved = 0
    v26_needs_review = 0
    if v26_dir and (v26_dir / "qa_summary.csv").is_file():
        try:
            with open(v26_dir / "qa_summary.csv", "r", encoding="utf-8", errors="replace") as fp:
                for row in csv.DictReader(fp):
                    if row.get("needs_review") == "True":
                        v26_needs_review += 1
                    else:
                        v26_approved += 1
        except Exception:
            pass

    v27_approved = 0
    v27_needs_review = 0
    v27_standardized = 0
    v27_skipped = 0
    if v27_dir and (v27_dir / "qa_summary.csv").is_file():
        try:
            with open(v27_dir / "qa_summary.csv", "r", encoding="utf-8", errors="replace") as fp:
                for row in csv.DictReader(fp):
                    if row.get("needs_review") == "True":
                        v27_needs_review += 1
                    else:
                        v27_approved += 1
                    h_status = (row.get("hand_std_status") or "").strip()
                    if h_status == "STANDARDIZED":
                        v27_standardized += 1
                    elif h_status:
                        v27_skipped += 1
        except Exception:
            pass

    return {
        "total_signs": len(all_signs),
        "directory": str(target_dir),
        "approved_high_quality": approved if approved else len(all_signs),
        "needs_review": needs_review,
        "fps_distribution": fps_counts,
        "pipeline_version": ver_tag,
        "version_active": eff_version,
        "active_default_version": "2.7" if v27_dir else ("2.6" if v26_dir else "2.5"),
        "order": "Catálogo Oficial Diccionario LSEC (CONADIS)",
        "v27_stats": {
            "available": bool(v27_dir),
            "approved": v27_approved,
            "needs_review": v27_needs_review,
            "standardized": v27_standardized,
            "skipped": v27_skipped,
            "total": v27_approved + v27_needs_review,
            "version": "2.7_Estandarizado",
            "directory": str(v27_dir) if v27_dir else None,
        },
        "v26_stats": {
            "available": bool(v26_dir),
            "approved": v26_approved,
            "needs_review": v26_needs_review,
            "total": v26_approved + v26_needs_review,
            "version": "2.6_Directo_1a1_corregido",
        },
    }


# ==============================================================================
# RESOLUTOR LÉXICO V2.7 / V2.6 SOBRE LAS CARPETAS REALES EN DISCO
# ==============================================================================

_v26_lexical_index: Optional[Dict[str, Any]] = None

# Preferencias explícitas para homónimos con calificadores de dominio en el catálogo
_PREFERRED_HOMONYMS: Dict[str, str] = {
    "carrera": "Carrera, Estudios",
    "opcion": "Alternativa, Opción",
    "educacion": "Educación",
    "formacion": "Formación, Manualidad",
    "seguro": "Seguro",
    "fuerte": "Fuerte, Fuerza, Poder",
    "persona": "Persona",
    "poder": "Poder",
    "querer": "Querer",
    "mas": "Más",
    "con": "Con, Con(1)",
    "no": "No, De negación",
    "si": "SÍ",
    "dia": "Día",
    "ano": "Año",
    "facil": "Fácil",
}

# Alias léxicos y gramaticales LSEC hacia entradas reales de las 5,061 carpetas v2.6
# Tupla: (nombre_carpeta_objetivo, match_type)
_LSEC_LEXICAL_ALIASES: Dict[str, Tuple[str, str]] = {
    # Pronombres y deícticos LSEC
    "pro1": ("Yo", "synonym"),
    "pro1pl": ("Nosotros(as)", "synonym"),
    "pro2": ("Tú", "synonym"),
    "pro2pl": ("Ustedes", "synonym"),
    "pro2mismo": ("Por sí mismo(a)", "synonym"),
    "pro3": ("El, Ella", "synonym"),
    "pro3pl": ("Ellos, ellas", "synonym"),
    "esaspersonas": ("Ellos, ellas", "synonym"),
    "eso": ("Este", "synonym"),
    "esto": ("Este", "synonym"),
    "ese": ("Este", "synonym"),
    "esa": ("Este", "synonym"),
    "esta": ("Este", "synonym"),
    "aquel": ("Este", "synonym"),
    "aquella": ("Este", "synonym"),
    # Conectores, cuantificadores y partículas temporales/espaciales
    "masde": ("Más", "synonym"),
    "solamenteno": ("Solo", "synonym"),
    "solamente": ("Solo", "synonym"),
    "aqui": ("Abajo, Aquí", "compound"),
    "hoy": ("Ahora", "synonym"),
    "nadie": ("Ninguno(a)", "synonym"),
    "entre": ("Mitad", "synonym"),
    "junto": ("Juntar, Juntos", "lemma"),
    "juntos": ("Juntar, Juntos", "compound"),
    "primero": ("Primer", "lemma"),
    "primera": ("Primer", "lemma"),
    "4500": ("Mil", "synonym"),
    # Vocabulario académico e institucional frecuente (ej. 1.mp4)
    "academico": ("Carrera, Estudios", "synonym"),
    "academica": ("Carrera, Estudios", "synonym"),
    "campus": ("Universidad", "synonym"),
    "conocimiento": ("Conocer", "lemma"),
    "conocimientos": ("Conocer", "lemma"),
    "destacar": ("Importante", "synonym"),
    "determinada": ("Decidir, Decisión", "synonym"),
    "determinado": ("Decidir, Decisión", "synonym"),
    "determinar": ("Decidir, Decisión", "synonym"),
    "educar": ("Educación", "lemma"),
    "excelencia": ("Excelente", "lemma"),
    "formar": ("Formación, Manualidad", "lemma"),
    "incluir": ("Inclusión", "lemma"),
    "innovacion": ("Nuevo(a)", "synonym"),
    "innovar": ("Nuevo(a)", "synonym"),
    "inspirar": ("Imaginar", "synonym"),
    "inspiracion": ("Imaginar", "synonym"),
    "liberar": ("Libertad, Libre", "lemma"),
    "obstaculo": ("Barrera", "synonym"),
    "obstaculos": ("Barrera", "synonym"),
    "orgullo": ("Orgulloso(a)", "lemma"),
    "preparacion": ("Preparar", "lemma"),
    "publica": ("Público, Pueblo", "lemma"),
    "publico": ("Público, Pueblo", "compound"),
    "realidad": ("Real", "lemma"),
    "sostenibilidad": ("Cuidar", "synonym"),
    "sostenible": ("Cuidar", "synonym"),
    "superar": ("Mejor, Mejorar", "synonym"),
    "trato": ("Tratar", "lemma"),
    "tratos": ("Tratar", "lemma"),
    "cercano": ("Cerca", "lemma"),
    "cercana": ("Cerca", "lemma"),
    "cercania": ("Cerca", "lemma"),
}


def _expand_gender_token(token: str) -> List[str]:
    """Expande sufijos de género/número como Bueno(a) -> ['Bueno', 'Buena'] o Nosotros(as)."""
    t = token.strip()
    if not t:
        return []
    results = [t]
    m = re.match(r"^(.+?)\((a|as|o|os|es)\)$", t, flags=re.IGNORECASE)
    if m:
        stem = m.group(1).strip()
        suf = m.group(2).lower()
        results = [stem]
        stem_low = stem.lower()
        if suf == "a":
            if stem_low.endswith("o"):
                results.append(stem[:-1] + "a")
            else:
                results.append(stem + "a")
        elif suf == "as":
            if stem_low.endswith("os"):
                results.append(stem[:-2] + "as")
                results.append(stem[:-1])
                results.append(stem[:-2] + "a")
            elif stem_low.endswith("o"):
                results.append(stem[:-1] + "a")
                results.append(stem + "s")
                results.append(stem[:-1] + "as")
            else:
                results.append(stem + "as")
        elif suf in ("o", "os"):
            results.append(stem + suf)
    return results


def parse_sign_title_tokens(folder_name: str) -> Tuple[List[str], List[str]]:
    """
    Extrae tokens de cabecera (head) y sinónimos/partes de un nombre de carpeta v2.6.
    Soporta separadores ',', '/', ';', doble espacio ('Escoger  Elegir'), signos '¿?¡!',
    sufijos '(1)', '__2' y expansiones de género '(a)', '(as)'.
    """
    cleaned = re.sub(r"[¿?¡!]", "", folder_name).strip()
    cleaned = re.sub(r"__\d+$", "", cleaned).strip()
    cleaned = re.sub(r"\(\d+\)$", "", cleaned).strip()

    # Caso especial: "Seguro, a"
    if re.search(r",\s*a$", cleaned, flags=re.IGNORECASE):
        base = re.sub(r",\s*a$", "", cleaned, flags=re.IGNORECASE).strip()
        expanded = _expand_gender_token(f"{base}(a)")
        return expanded, expanded

    raw_parts = [p.strip() for p in re.split(r"[,/;]|\s{2,}", cleaned) if p.strip()]
    head_tokens: List[str] = []
    all_tokens: List[str] = []

    for idx, part in enumerate(raw_parts):
        part_clean = re.sub(r"\(\d+\)$", "", part).strip()
        # También extraer sin paréntesis descriptivos largos como "Zona, Sector (Donde lugar)"
        part_no_desc = re.sub(r"\([^)]{3,}\)", "", part_clean).strip()
        candidates = _expand_gender_token(part_clean)
        if part_no_desc and part_no_desc != part_clean:
            candidates.extend(_expand_gender_token(part_no_desc))
        for cand in candidates:
            if idx == 0 and cand not in head_tokens:
                head_tokens.append(cand)
            if cand not in all_tokens:
                all_tokens.append(cand)

    return head_tokens, all_tokens


def _build_v26_lexical_index() -> Dict[str, Any]:
    """Construye y cachea el índice completo sobre las carpetas reales de v2.7, v2.6 y v2.5."""
    global _v26_lexical_index
    if _v26_lexical_index is not None:
        return _v26_lexical_index

    v27_dir = get_v27_dir()
    v26_dir = get_v26_dir()
    v25_dir = get_v25_dir()

    # 1. Leer qa_summary.csv de v2.6 y enriquecer con v2.7 para obtener needs_review y métricas
    qa_map: Dict[str, Dict[str, Any]] = {}
    qa_norm_map: Dict[str, Dict[str, Any]] = {}
    for qa_src_dir in (v26_dir, v27_dir):
        if qa_src_dir and (qa_src_dir / "qa_summary.csv").is_file():
            try:
                with open(qa_src_dir / "qa_summary.csv", "r", encoding="utf-8", errors="replace") as f:
                    for row in csv.DictReader(f):
                        s_name = unicodedata.normalize("NFC", (row.get("sign") or "").strip())
                        if s_name:
                            merged_row = dict(qa_map.get(s_name, {}))
                            merged_row.update({k: v for k, v in row.items() if v is not None and v != ""})
                            qa_map[s_name] = merged_row
                            qa_norm_map[normalize_text(s_name)] = merged_row
            except Exception as exc:
                logger.warning("No se pudo leer qa_summary.csv de %s: %s", qa_src_dir, exc)

    # 2. Escanear carpetas reales en v2.7, v2.6 y v2.5
    v27_folders: Dict[str, Path] = {}
    v26_folders: Dict[str, Path] = {}
    v25_folders: Dict[str, Path] = {}
    raw_v27_count = 0
    raw_v26_count = 0
    raw_v25_count = 0

    if v27_dir and v27_dir.is_dir():
        try:
            for entry in os.scandir(v27_dir):
                if entry.is_dir() and not entry.name.startswith("."):
                    anim_p = Path(entry.path) / "animation.json"
                    if anim_p.is_file():
                        raw_v27_count += 1
                        nfc_name = unicodedata.normalize("NFC", entry.name)
                        if nfc_name not in v27_folders or unicodedata.is_normalized("NFC", entry.name):
                            v27_folders[nfc_name] = Path(entry.path)
        except Exception as exc:
            logger.warning("Error escaneando v27_dir: %s", exc)

    if v26_dir and v26_dir.is_dir():
        try:
            for entry in os.scandir(v26_dir):
                if entry.is_dir() and not entry.name.startswith("."):
                    anim_p = Path(entry.path) / "animation.json"
                    if anim_p.is_file():
                        raw_v26_count += 1
                        nfc_name = unicodedata.normalize("NFC", entry.name)
                        # Preferir carpeta cuyo nombre ya está en NFC en disco si hay duplicado NFD/NFC
                        if nfc_name not in v26_folders or unicodedata.is_normalized("NFC", entry.name):
                            v26_folders[nfc_name] = Path(entry.path)
        except Exception as exc:
            logger.warning("Error escaneando v26_dir: %s", exc)

    if v25_dir and v25_dir.is_dir():
        try:
            for entry in os.scandir(v25_dir):
                if entry.is_dir() and not entry.name.startswith("."):
                    anim_p = Path(entry.path) / "animation.json"
                    if anim_p.is_file():
                        raw_v25_count += 1
                        nfc_name = unicodedata.normalize("NFC", entry.name)
                        if nfc_name not in v25_folders or unicodedata.is_normalized("NFC", entry.name):
                            v25_folders[nfc_name] = Path(entry.path)
        except Exception as exc:
            logger.warning("Error escaneando v25_dir: %s", exc)

    all_canonical_names = sorted(set(v27_folders.keys()) | set(v26_folders.keys()) | set(v25_folders.keys()))

    exact_map: Dict[str, str] = {}
    head_map: Dict[str, List[str]] = {}
    part_map: Dict[str, List[str]] = {}

    for canonical in all_canonical_names:
        norm_full = normalize_text(canonical)
        if norm_full and norm_full not in exact_map:
            exact_map[norm_full] = canonical

        cleaned = re.sub(r"[¿?¡!]", "", canonical).strip()
        cleaned = re.sub(r"__\d+$", "", cleaned).strip()
        norm_cleaned = normalize_text(cleaned)
        if norm_cleaned and norm_cleaned not in exact_map:
            exact_map[norm_cleaned] = canonical

        heads, parts = parse_sign_title_tokens(canonical)
        for h in heads:
            nh = normalize_text(h)
            if nh:
                head_map.setdefault(nh, []).append(canonical)
        for p in parts:
            np = normalize_text(p)
            if np:
                part_map.setdefault(np, []).append(canonical)

    _v26_lexical_index = {
        "v27_folders": v27_folders,
        "v26_folders": v26_folders,
        "v25_folders": v25_folders,
        "qa_map": qa_map,
        "qa_norm_map": qa_norm_map,
        "exact_map": exact_map,
        "head_map": head_map,
        "part_map": part_map,
        "total_v27": raw_v27_count,
        "unique_v27": len(v27_folders),
        "total_v26": raw_v26_count,
        "unique_v26": len(v26_folders),
        "total_v25": raw_v25_count,
        "unique_v25": len(v25_folders),
    }
    logger.info(
        "✓ Índice léxico v2.7/v2.6 construido: %d carpetas v2.7, %d carpetas v2.6 (%d únicas NFC), %d exactas, %d cabeceras, %d partes",
        raw_v27_count,
        raw_v26_count,
        len(v26_folders),
        len(exact_map),
        len(head_map),
        len(part_map),
    )
    return _v26_lexical_index


def _select_best_candidate(norm_key: str, candidates: List[str], exact_map: Dict[str, str]) -> str:
    """Selecciona la mejor carpeta cuando existen múltiples variantes para un término."""
    if norm_key in _PREFERRED_HOMONYMS:
        pref = _PREFERRED_HOMONYMS[norm_key]
        for c in candidates:
            if unicodedata.normalize("NFC", c) == unicodedata.normalize("NFC", pref):
                return c
        for c in candidates:
            if normalize_text(c) == normalize_text(pref):
                return c
    if norm_key in exact_map and exact_map[norm_key] in candidates:
        return exact_map[norm_key]
    # Preferir entradas más cortas y sin calificadores restrictivos ("De autos", "De línea")
    scored = sorted(
        candidates,
        key=lambda c: (
            1 if re.search(r",\s*de\s+", c, flags=re.IGNORECASE) else 0,
            len(c),
            c.lower(),
        ),
    )
    return scored[0]


def _generate_morphological_candidates(gloss: str) -> List[str]:
    """Genera candidatos morfológicos (lemas verbales, nominalizaciones, género y número)."""
    norm = normalize_text(gloss)
    if not norm or len(norm) < 3:
        return []

    cands: List[str] = []

    def _add(val: str):
        nv = normalize_text(val)
        if nv and nv != norm and nv not in cands:
            cands.append(nv)

    # 1. Consultar SpanishVerbLexicon si está disponible
    try:
        from app.services.text_normalizer import SpanishVerbLexicon
        inf = SpanishVerbLexicon.get_infinitive(gloss.lower())
        if inf:
            _add(inf)
    except Exception:
        pass

    # 2. Nominalizaciones <-> verbos (-ación/-ición -> -ar/-ir, -miento/-cimiento -> -er/-ar/-ir)
    if norm.endswith("amiento"):
        _add(norm[:-7] + "ar")
    if norm.endswith("imiento"):
        _add(norm[:-7] + "ir")
        _add(norm[:-7] + "er")
    if norm.endswith("cimiento"):
        _add(norm[:-8] + "cer")
    if norm.endswith("acion"):
        _add(norm[:-5] + "ar")
    if norm.endswith("icion"):
        _add(norm[:-5] + "ir")
    if norm.endswith("sion"):
        _add(norm[:-4] + "ir")
        _add(norm[:-4] + "dir")
        _add(norm[:-4] + "tir")
    if norm.endswith("ar") and len(norm) > 4:
        _add(norm[:-2] + "acion")
        _add(norm[:-2] + "o")
    if norm.endswith("ir") and len(norm) > 4:
        _add(norm[:-2] + "icion")
        _add(norm[:-3] + "sion") if norm.endswith("uir") else None

    # 3. Sufijos adjetivales/nominales (-idad -> base, -encia -> -ente, -oso -> -o)
    if norm.endswith("idad") and len(norm) > 6:
        _add(norm[:-4])
        _add(norm[:-4] + "o")
    if norm.endswith("encia") and len(norm) > 6:
        _add(norm[:-5] + "ente")
    if norm.endswith("ancia") and len(norm) > 6:
        _add(norm[:-5] + "ante")
    if norm.endswith("ullo"):
        _add(norm[:-1] + "oso")
    if norm.endswith("ero"):
        _add(norm[:-1])  # primero -> primer, tercero -> tercer

    # 4. Plurales y género
    if norm.endswith("es") and len(norm) > 4:
        _add(norm[:-2])
        _add(norm[:-1])
    if norm.endswith("s") and len(norm) > 3:
        _add(norm[:-1])
        if norm.endswith("as"):
            _add(norm[:-2] + "o")
            _add(norm[:-2] + "os")
    if norm.endswith("ano") and len(norm) > 5:
        _add(norm[:-3] + "a")
    if norm.endswith("ana") and len(norm) > 5:
        _add(norm[:-3] + "a")
    if norm.endswith("a") and len(norm) > 3:
        _add(norm[:-1] + "o")
        _add(norm[:-1])
    if norm.endswith("o") and len(norm) > 3:
        _add(norm[:-1] + "a")
        _add(norm[:-1])
        _add(norm[:-1] + "ar")

    # 5. Participios y gerundios regulares
    if norm.endswith("ado") and len(norm) > 5:
        _add(norm[:-3] + "ar")
    if norm.endswith("ada") and len(norm) > 5:
        _add(norm[:-3] + "ar")
        _add(norm[:-1] + "o")
    if norm.endswith("ido") and len(norm) > 5:
        _add(norm[:-3] + "er")
        _add(norm[:-3] + "ir")

    return cands


def _is_fingerspelling_gloss(gloss: str) -> bool:
    """Detecta si una glosa corresponde a dactilología letra por letra (ej. G-U-A-Y-A-Q-U-I-L, U-P-E-C)."""
    s = (gloss or "").strip()
    if s.upper().startswith("FS:") or s.upper().startswith("DACT:"):
        return True
    if "-" in s:
        parts = [p.strip() for p in s.split("-") if p.strip()]
        if len(parts) >= 2 and all(len(p) == 1 and p.isalpha() for p in parts):
            return True
    return False


def resolve_gloss_to_sign(
    gloss: str,
    version: Optional[str] = "2.7",
    include_animation: bool = False,
) -> Dict[str, Any]:
    """
    Resuelve una glosa LSEC contra las carpetas reales del catálogo v2.7 (con respaldo v2.6 -> v2.5).
    Nunca lanza HTTPException 404; devuelve estructura trazable con:
      found, gloss, resolved_gloss, sign, match_type, status, needs_review, warning,
      version_served, is_fingerspelling, qa, animation (opcional).
    """
    clean_gloss = (gloss or "").strip()
    if not clean_gloss:
        return {
            "found": False,
            "gloss": "",
            "resolved_gloss": None,
            "sign": None,
            "match_type": "none",
            "status": "EMPTY",
            "needs_review": False,
            "warning": "Glosa vacía",
            "version_served": None,
            "is_fingerspelling": False,
            "qa": None,
            "animation": None,
        }
    idx = _build_v26_lexical_index()
    exact_map: Dict[str, str] = idx["exact_map"]
    head_map: Dict[str, List[str]] = idx["head_map"]
    part_map: Dict[str, List[str]] = idx["part_map"]
    v27_folders: Dict[str, Path] = idx.get("v27_folders", {})
    v26_folders: Dict[str, Path] = idx["v26_folders"]
    v25_folders: Dict[str, Path] = idx["v25_folders"]
    qa_map: Dict[str, Dict[str, Any]] = idx["qa_map"]
    qa_norm_map: Dict[str, Dict[str, Any]] = idx["qa_norm_map"]

    # 0. Dactilología explícita (ej. C-A-Y-A-M-B-E, T-U-L-C-Á-N, U-P-E-C, G-U-A-Y-A-Q-U-I-L)
    if _is_fingerspelling_gloss(clean_gloss):
        return {
            "found": False,
            "gloss": clean_gloss,
            "resolved_gloss": None,
            "sign": None,
            "match_type": "fingerspelling",
            "status": "FINGERSPELLING",
            "needs_review": False,
            "warning": "Dactilología pendiente",
            "version_served": None,
            "is_fingerspelling": True,
            "qa": None,
            "animation": None,
        }

    norm_g = normalize_text(clean_gloss)
    resolved_sign: Optional[str] = None
    match_type: str = "none"
    status_label: str = "MISSING"

    # Nivel 1: Coincidencia exacta con el nombre de carpeta (o preferencia de homónimo directo)
    if norm_g in _PREFERRED_HOMONYMS:
        pref = _PREFERRED_HOMONYMS[norm_g]
        if pref in v27_folders or pref in v26_folders or pref in v25_folders:
            resolved_sign = pref
            match_type = "exact" if normalize_text(pref) == norm_g else "compound"
            status_label = "EXACT" if match_type == "exact" else "VARIANT"

    if not resolved_sign and norm_g in exact_map:
        resolved_sign = exact_map[norm_g]
        match_type = "exact"
        status_label = "EXACT"

    # Nivel 2: Cabecera o parte de título compuesto en disco ("Decidir, Decisión", "Escoger  Elegir", "Libertad, Libre")
    if not resolved_sign and norm_g in head_map:
        resolved_sign = _select_best_candidate(norm_g, head_map[norm_g], exact_map)
        match_type = "compound"
        status_label = "VARIANT"

    if not resolved_sign and norm_g in part_map:
        resolved_sign = _select_best_candidate(norm_g, part_map[norm_g], exact_map)
        match_type = "compound"
        status_label = "VARIANT"

    # Nivel 3: LSECDictionaryService.lookup_gloss(gloss)
    if not resolved_sign:
        try:
            from app.services.dictionary_service import get_dictionary_service
            dict_svc = get_dictionary_service()
            entry = dict_svc.lookup_gloss(clean_gloss)
            if entry:
                for cand_title in [entry.title, entry.head_word] + list(entry.synonyms or []):
                    nc = normalize_text(cand_title)
                    if not nc:
                        continue
                    if nc in exact_map:
                        resolved_sign = exact_map[nc]
                        match_type = "compound"
                        status_label = "DICTIONARY"
                        break
                    if nc in head_map:
                        resolved_sign = _select_best_candidate(nc, head_map[nc], exact_map)
                        match_type = "compound"
                        status_label = "DICTIONARY"
                        break
                    if nc in part_map:
                        resolved_sign = _select_best_candidate(nc, part_map[nc], exact_map)
                        match_type = "compound"
                        status_label = "DICTIONARY"
                        break
        except Exception as exc:
            logger.debug("LSECDictionaryService lookup fallo para %s: %s", clean_gloss, exc)

    # Nivel 4: Alias léxicos y gramaticales LSEC curados
    if not resolved_sign and norm_g in _LSEC_LEXICAL_ALIASES:
        alias_target, alias_mtype = _LSEC_LEXICAL_ALIASES[norm_g]
        nt = normalize_text(alias_target)
        if alias_target in v27_folders or alias_target in v26_folders or alias_target in v25_folders:
            resolved_sign = alias_target
            match_type = alias_mtype
            status_label = "ALIAS" if alias_mtype == "synonym" else "APPROXIMATE"
        elif nt in exact_map:
            resolved_sign = exact_map[nt]
            match_type = alias_mtype
            status_label = "ALIAS" if alias_mtype == "synonym" else "APPROXIMATE"
        elif nt in part_map:
            resolved_sign = _select_best_candidate(nt, part_map[nt], exact_map)
            match_type = alias_mtype
            status_label = "ALIAS" if alias_mtype == "synonym" else "APPROXIMATE"

    # Nivel 5: Derivación morfológica (lemas verbales, nominalizaciones, plurales, género)
    if not resolved_sign:
        for morph_norm in _generate_morphological_candidates(clean_gloss):
            if morph_norm in _PREFERRED_HOMONYMS:
                resolved_sign = _PREFERRED_HOMONYMS[morph_norm]
                match_type = "lemma"
                status_label = "APPROXIMATE"
                break
            if morph_norm in exact_map:
                resolved_sign = exact_map[morph_norm]
                match_type = "lemma"
                status_label = "APPROXIMATE"
                break
            if morph_norm in head_map:
                resolved_sign = _select_best_candidate(morph_norm, head_map[morph_norm], exact_map)
                match_type = "lemma"
                status_label = "APPROXIMATE"
                break
            if morph_norm in part_map:
                resolved_sign = _select_best_candidate(morph_norm, part_map[morph_norm], exact_map)
                match_type = "lemma"
                status_label = "APPROXIMATE"
                break

    # Nivel 6: Descomposición de glosas compuestas con guion (ej. MÁS-DE -> MÁS)
    if not resolved_sign and "-" in clean_gloss:
        sub_tokens = [t.strip() for t in clean_gloss.split("-") if len(t.strip()) >= 2]
        for sub_tok in sub_tokens:
            sub_res = resolve_gloss_to_sign(sub_tok, version=version, include_animation=False)
            if sub_res.get("found"):
                resolved_sign = sub_res["sign"]
                match_type = "synonym"
                status_label = "APPROXIMATE"
                break

    if not resolved_sign:
        return {
            "found": False,
            "gloss": clean_gloss,
            "resolved_gloss": None,
            "sign": None,
            "match_type": "none",
            "status": "MISSING",
            "needs_review": False,
            "warning": f"Sin animación en catálogo v2.7/v2.6 para '{clean_gloss}'",
            "version_served": None,
            "is_fingerspelling": False,
            "qa": None,
            "animation": None,
        }

    # Localizar archivo animation.json según la versión solicitada (por defecto 2.7 -> 2.6 -> 2.5)
    anim_path: Optional[Path] = None
    version_served = "2.7"
    if version == "2.5":
        if resolved_sign in v25_folders:
            anim_path = v25_folders[resolved_sign] / "animation.json"
            version_served = "2.5"
    elif version == "2.6":
        if resolved_sign in v26_folders:
            anim_path = v26_folders[resolved_sign] / "animation.json"
            version_served = "2.6"
        elif resolved_sign in v25_folders:
            anim_path = v25_folders[resolved_sign] / "animation.json"
            version_served = "2.5"
    else:
        if resolved_sign in v27_folders:
            anim_path = v27_folders[resolved_sign] / "animation.json"
            version_served = "2.7"
        elif resolved_sign in v26_folders:
            anim_path = v26_folders[resolved_sign] / "animation.json"
            version_served = "2.6"
        elif resolved_sign in v25_folders:
            anim_path = v25_folders[resolved_sign] / "animation.json"
            version_served = "2.5"

    if not anim_path or not anim_path.is_file():
        return {
            "found": False,
            "gloss": clean_gloss,
            "resolved_gloss": resolved_sign,
            "sign": resolved_sign,
            "match_type": "none",
            "status": "MISSING",
            "needs_review": False,
            "warning": f"Archivo animation.json ausente para '{resolved_sign}'",
            "version_served": None,
            "is_fingerspelling": False,
            "qa": None,
            "animation": None,
        }

    qa_row = qa_map.get(resolved_sign) or qa_norm_map.get(normalize_text(resolved_sign)) or {}
    needs_review = str(qa_row.get("needs_review", "False")).lower() == "true"

    warning_msg: Optional[str] = None
    if match_type not in ("exact", "compound"):
        warning_msg = f"⚠ Aprox: {resolved_sign}" + (" · Revisión QA" if needs_review else "")
    elif needs_review:
        warning_msg = f"⚠ Revisión: {resolved_sign}"

    stroke_entry: Optional[Dict[str, Any]] = get_sign_stroke_entry(resolved_sign) if version_served == "2.7" else None

    anim_payload: Optional[Dict[str, Any]] = None
    if include_animation:
        try:
            with open(anim_path, "r", encoding="utf-8") as f:
                anim_payload = json.load(f)
            if isinstance(anim_payload, dict):
                cat_meta = get_sign_metadata(resolved_sign)
                if lsec_cnm is not None and not anim_payload.get("metadata", {}).get("nonManualStandard"):
                    lsec_cnm.standardize_animation_dict(
                        anim_payload, sign_name=resolved_sign, catalog_entry=cat_meta
                    )
                meta = anim_payload.setdefault("metadata", {})
                meta["version_served"] = version_served
                meta["resolved_sign"] = resolved_sign
                meta["match_type"] = match_type
                meta["status_label"] = status_label
                meta["needs_review"] = needs_review
                if version_served == "2.7":
                    meta["pipelineVersion"] = "2.7_Estandarizado"
                    if stroke_entry:
                        meta["stroke"] = stroke_entry
                    if cat_meta and isinstance(cat_meta.get("hand_standardization"), dict):
                        h_std = dict(cat_meta["hand_standardization"])
                        if isinstance(meta.get("handStandardization"), dict):
                            h_std.update(meta["handStandardization"])
                        if "distance_reduction_pct" in h_std and "reduction_pct" not in h_std:
                            h_std["reduction_pct"] = h_std["distance_reduction_pct"]
                        meta["handStandardization"] = h_std
        except Exception as exc:
            logger.warning("Error leyendo animation.json en %s: %s", anim_path, exc)

    return {
        "found": True,
        "gloss": clean_gloss,
        "resolved_gloss": resolved_sign,
        "sign": resolved_sign,
        "match_type": match_type,
        "status": status_label,
        "needs_review": needs_review,
        "warning": warning_msg,
        "version_served": version_served,
        "is_fingerspelling": False,
        "anim_path": str(anim_path),
        "stroke": stroke_entry,
        "qa": {
            "needs_review": needs_review,
            "review_reasons": qa_row.get("review_reasons", ""),
            "duration": float(qa_row.get("duration", 0.0) or 0.0),
            "fps": float(qa_row.get("fps", 60.0) or 60.0),
            "frames": int(float(qa_row.get("frames", 0) or 0)),
            "hand_std_status": qa_row.get("hand_std_status", ""),
            "bimanual_mode": qa_row.get("bimanual_mode", ""),
            "frames_modified": int(float(qa_row.get("frames_modified", 0) or 0)),
        },
        "animation": anim_payload,
    }


@animation_router.get("/non-manual-standard", summary="Obtiene el estándar auditable de Componentes No Manuales (CNM) y sus excepciones explícitas")
async def get_non_manual_standard() -> Dict[str, Any]:
    manifest_path = _DICCIONARIO_LSEC_DIR / "configuracion_manual" / "estandar_componentes_no_manuales.json"
    if manifest_path.is_file():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Error leyendo estandar_componentes_no_manuales.json: %s", exc)
    if lsec_cnm is not None:
        return lsec_cnm.build_manifest_and_update_dataset(_DICCIONARIO_LSEC_DIR, update_v26_files=False)
    raise HTTPException(status_code=404, detail="Manifiesto de estándar CNM no disponible.")


@animation_router.get("/stroke-index", summary="Consulta el índice precalculado de trazos activos (stroke_index.json) para el catálogo v2.7")
async def get_stroke_index_endpoint(
    q: Optional[str] = Query(None, description="Filtro opcional por nombre de seña"),
    signs: Optional[str] = Query(None, description="Lista separada por comas de señas o glosas a consultar"),
    limit: int = Query(100, ge=1, le=5000, description="Máximo de entradas a devolver"),
    summary_only: bool = Query(False, description="Devolver únicamente las estadísticas globales del índice"),
) -> Dict[str, Any]:
    idx_data = get_v27_stroke_index()
    all_signs_map: Dict[str, Any] = idx_data.get("signs") or {}
    if summary_only:
        return {
            "version": idx_data.get("version", "2.7"),
            "totalSigns": idx_data.get("totalSigns", len(all_signs_map)),
            "summary": idx_data.get("summary", {}),
        }

    selected: Dict[str, Any] = {}
    if signs:
        for raw_token in signs.split(","):
            tok = raw_token.strip()
            if not tok:
                continue
            entry = get_sign_stroke_entry(tok)
            if not entry:
                res = resolve_gloss_to_sign(tok, version="2.7", include_animation=False)
                if res.get("found") and res.get("resolved_gloss"):
                    entry = get_sign_stroke_entry(res["resolved_gloss"])
            if entry:
                selected[tok] = entry
    elif q:
        nq = normalize_text(q)
        for s_name, s_entry in all_signs_map.items():
            if nq in normalize_text(s_name):
                selected[s_name] = s_entry
                if len(selected) >= limit:
                    break
    else:
        for s_name, s_entry in all_signs_map.items():
            selected[s_name] = s_entry
            if len(selected) >= limit:
                break

    return {
        "version": idx_data.get("version", "2.7"),
        "totalSigns": idx_data.get("totalSigns", len(all_signs_map)),
        "returnedSigns": len(selected),
        "summary": idx_data.get("summary", {}),
        "signs": selected,
    }


@animation_router.get("/resolve/{gloss}", summary="Resuelve una glosa LSEC en el catálogo v2.7/v2.6 sin lanzar 404")
async def resolve_single_gloss(
    gloss: str,
    version: Optional[str] = Query("2.7", description="Versión preferida: '2.7', '2.6' o '2.5'"),
    include_animation: bool = Query(True, description="Incluir el JSON completo de animation.json"),
) -> Dict[str, Any]:
    res = resolve_gloss_to_sign(gloss, version=version or "2.7", include_animation=include_animation)
    res.pop("anim_path", None)
    return res


@animation_router.post("/resolve", summary="Resuelve un lote de glosas LSEC contra el catálogo v2.7/v2.6 sin 404")
async def resolve_batch_glosses(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_glosses = payload.get("glosses") or []
    version = payload.get("version") or "2.7"
    include_animation = bool(payload.get("include_animation", False))

    results: Dict[str, Dict[str, Any]] = {}
    items: List[Dict[str, Any]] = []
    exact_count = 0
    approx_count = 0
    review_count = 0
    fs_count = 0
    missing_count = 0

    for g in raw_glosses:
        g_str = str(g or "").strip()
        if not g_str:
            continue
        res = resolve_gloss_to_sign(g_str, version=version, include_animation=include_animation)
        res.pop("anim_path", None)
        results[g_str] = res
        items.append(res)
        if res["found"]:
            if res["match_type"] in ("exact", "compound"):
                exact_count += 1
            else:
                approx_count += 1
            if res["needs_review"]:
                review_count += 1
        elif res["is_fingerspelling"]:
            fs_count += 1
        else:
            missing_count += 1

    return {
        "version": version,
        "results": results,
        "items": items,
        "summary": {
            "total": len(items),
            "resolved": exact_count + approx_count,
            "exact_or_compound": exact_count,
            "approximate": approx_count,
            "needs_review": review_count,
            "fingerspelling": fs_count,
            "missing": missing_count,
        },
    }


@animation_router.get("/{sign_name}", summary="Obtiene el archivo animation.json de una seña específica")
async def get_sign_animation(sign_name: str, version: Optional[str] = Query(None, description="Versión preferida: '2.7', '2.6' o '2.5'")):
    clean_name = sign_name.strip()
    v27_dir = get_v27_dir()
    v26_dir = get_v26_dir()
    v25_dir = get_v25_dir()

    if version == "2.5":
        search_dirs = [v25_dir]
    elif version == "2.6":
        search_dirs = [d for d in (v26_dir, v25_dir) if d]
    else:
        search_dirs = [d for d in (v27_dir, v26_dir, v25_dir) if d]

    anim_file: Optional[Path] = None
    resolved_name: str = clean_name
    if version == "2.5":
        version_served = "2.5"
    elif version == "2.6":
        version_served = "2.6" if v26_dir else "2.5"
    else:
        version_served = "2.7" if v27_dir else ("2.6" if v26_dir else "2.5")
    match_type: str = "exact"
    status_label: str = "EXACT"
    needs_review: bool = False
    warning_msg: Optional[str] = None

    name_variants = list(dict.fromkeys([
        clean_name,
        unicodedata.normalize("NFC", clean_name),
        unicodedata.normalize("NFD", clean_name),
    ]))

    for bdir in search_dirs:
        if not bdir or not bdir.is_dir():
            continue
        for variant in name_variants:
            cand = bdir / variant / "animation.json"
            if cand.is_file():
                anim_file = cand
                resolved_name = unicodedata.normalize("NFC", variant)
                if v27_dir and bdir == v27_dir:
                    version_served = "2.7"
                elif v26_dir and bdir == v26_dir:
                    version_served = "2.6"
                else:
                    version_served = "2.5"
                break
        if anim_file:
            break

    # Usar el resolutor léxico completo v2.7/v2.6 sobre las carpetas si no hubo match directo por ruta
    res = resolve_gloss_to_sign(clean_name, version=version or "2.7", include_animation=False)
    if res.get("found") and res.get("anim_path"):
        if not anim_file:
            anim_file = Path(res["anim_path"])
            resolved_name = res.get("resolved_gloss") or resolved_name
            version_served = res.get("version_served") or version_served
            match_type = res.get("match_type") or match_type
            status_label = res.get("status") or status_label
            needs_review = bool(res.get("needs_review", False))
            warning_msg = res.get("warning")
        elif res.get("match_type") == "exact":
            resolved_name = res.get("resolved_gloss") or resolved_name
            status_label = res.get("status") or status_label
            needs_review = bool(res.get("needs_review", False))
            warning_msg = res.get("warning")

    if not anim_file or not anim_file.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Animación no encontrada para la seña '{sign_name}'. Verifique /api/v1/animations/list.",
        )

    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", resolved_name)
    headers = {
        "Cache-Control": "no-cache",
        "X-Sign-Resolved": unicodedata.normalize("NFKD", resolved_name).encode("ascii", "ignore").decode("ascii"),
        "X-Sign-Version": str(version_served),
        "X-Sign-Status": str(status_label),
        "X-Sign-Match-Type": str(match_type),
        "X-Sign-Needs-Review": "true" if needs_review else "false",
    }
    if warning_msg:
        headers["X-Sign-Warning"] = unicodedata.normalize("NFKD", warning_msg).encode("ascii", "ignore").decode("ascii")

    try:
        raw_data = json.loads(anim_file.read_text(encoding="utf-8"))
        if isinstance(raw_data, dict):
            cat_meta = get_sign_metadata(resolved_name)
            if lsec_cnm is not None and not raw_data.get("metadata", {}).get("nonManualStandard"):
                lsec_cnm.standardize_animation_dict(raw_data, sign_name=resolved_name, catalog_entry=cat_meta)
            meta = raw_data.setdefault("metadata", {})
            meta["version_served"] = version_served
            meta["resolved_sign"] = resolved_name
            meta["requested_gloss"] = clean_name
            meta["match_type"] = match_type
            meta["status_label"] = status_label
            meta["needs_review"] = needs_review
            meta["warning"] = warning_msg
            if version_served == "2.7":
                meta["pipelineVersion"] = "2.7_Estandarizado"
                stroke_entry = get_sign_stroke_entry(resolved_name)
                if stroke_entry:
                    meta["stroke"] = stroke_entry
                    headers["X-Sign-Stroke-Window"] = f"{stroke_entry.get('strokeStart', 0.0)}-{stroke_entry.get('strokeEnd', 0.0)}"
                if cat_meta and isinstance(cat_meta.get("hand_standardization"), dict):
                    h_std = dict(cat_meta["hand_standardization"])
                    if isinstance(meta.get("handStandardization"), dict):
                        h_std.update(meta["handStandardization"])
                    if "distance_reduction_pct" in h_std and "reduction_pct" not in h_std:
                        h_std["reduction_pct"] = h_std["distance_reduction_pct"]
                    meta["handStandardization"] = h_std
            cnm_std = meta.get("nonManualStandard", {})
            headers["X-Sign-Facial-Archetype"] = str(cnm_std.get("archetype", "neutral"))
            headers["X-Sign-Explicit-Expression"] = "true" if cnm_std.get("hasExplicitFacialExpression") else "false"
            hand_std = meta.get("handStandardization", {})
            if isinstance(hand_std, dict) and hand_std:
                headers["X-Sign-Hand-Standardization"] = str(hand_std.get("status", ""))
                headers["X-Sign-Hand-Template"] = str(hand_std.get("template_id") or (cat_meta.get("hand_variant") if cat_meta else "") or "")
            return JSONResponse(content=raw_data, headers=headers)
    except Exception as exc:
        logger.warning("Aviso normalizando metadata al vuelo para %s: %s", resolved_name, exc)

    return FileResponse(
        path=str(anim_file),
        media_type="application/json",
        filename=f"{safe_name}_animation.json",
        headers=headers,
    )


@animation_router.get("/{sign_name}/stroke", summary="Obtiene la ventana de trazo activo y poses de ancla precalculadas (v2.7) de una seña")
async def get_sign_stroke_endpoint(sign_name: str):
    clean_name = sign_name.strip()
    stroke_entry = get_sign_stroke_entry(clean_name)
    if not stroke_entry:
        res = resolve_gloss_to_sign(clean_name, version="2.7", include_animation=False)
        if res.get("found") and res.get("version_served") == "2.7" and res.get("resolved_gloss"):
            stroke_entry = get_sign_stroke_entry(res["resolved_gloss"])
    if not stroke_entry:
        raise HTTPException(
            status_code=404,
            detail=f"Índice de trazo activo (v2.7) no encontrado para '{sign_name}'.",
        )
    return JSONResponse(content=stroke_entry)


@animation_router.get("/{sign_name}/qa", summary="Obtiene las métricas de QA de una seña específica")
async def get_sign_qa(sign_name: str, version: Optional[str] = Query(None, description="Versión preferida: '2.7', '2.6' o '2.5'")):
    clean_name = sign_name.strip()
    v27_dir = get_v27_dir()
    v26_dir = get_v26_dir()
    v25_dir = get_v25_dir()

    if version == "2.5":
        search_dirs = [v25_dir]
    elif version == "2.6":
        search_dirs = [d for d in (v26_dir, v25_dir) if d]
    else:
        search_dirs = [d for d in (v27_dir, v26_dir, v25_dir) if d]

    qa_file: Optional[Path] = None
    name_variants = list(dict.fromkeys([
        clean_name,
        unicodedata.normalize("NFC", clean_name),
        unicodedata.normalize("NFD", clean_name),
    ]))

    for bdir in search_dirs:
        if not bdir or not bdir.is_dir():
            continue
        for variant in name_variants:
            cand = bdir / variant / "qa.json"
            if cand.is_file():
                qa_file = cand
                break
        if qa_file:
            break

    if not qa_file:
        norm_target = normalize_text(clean_name)
        for candidate in get_available_signs():
            if normalize_text(candidate) == norm_target:
                for bdir in search_dirs:
                    if not bdir or not bdir.is_dir():
                        continue
                    for variant in (candidate, unicodedata.normalize("NFD", candidate)):
                        cand = bdir / variant / "qa.json"
                        if cand.is_file():
                            qa_file = cand
                            break
                    if qa_file:
                        break
                if qa_file:
                    break

    if not qa_file or not qa_file.is_file():
        # Intentar metadata en memoria
        meta = get_sign_metadata(clean_name)
        if meta and meta.get("qa"):
            return JSONResponse(content=meta["qa"])
        raise HTTPException(status_code=404, detail=f"Métricas QA no encontradas para '{sign_name}'.")

    return FileResponse(path=str(qa_file), media_type="application/json")


@animation_router.get("/{sign_name}/info", summary="Obtiene la ficha lingüística e info.json de catálogo de una seña")
async def get_sign_info(sign_name: str):
    clean_name = sign_name.strip()
    meta = get_sign_metadata(clean_name)

    if meta:
        return JSONResponse(content=meta)

    # Buscar directamente archivo info.json en disco (NFC o NFD) en v2.7 -> v2.6 -> v2.5
    for base_dir in [d for d in (get_v27_dir(), get_v26_dir(), get_v25_dir()) if d]:
        for variant in (clean_name, unicodedata.normalize("NFC", clean_name), unicodedata.normalize("NFD", clean_name)):
            info_file = base_dir / variant / "info.json"
            if info_file.is_file():
                return FileResponse(path=str(info_file), media_type="application/json")

    raise HTTPException(status_code=404, detail=f"Ficha lingüística no encontrada para '{sign_name}'.")


@animation_router.get("/{sign_name}/video", summary="Sirve el video MP4 original Ultra HD de la seña para verificación")
async def get_sign_video(sign_name: str, request: Request):
    """
    Busca y sirve en streaming el video MP4 de la seña original Ultra HD para comparación
    directa con la animación del avatar 3D. Si el archivo en senas_ultra_hd/ no existe o
    presenta corrupción de bitstream, aplica fallback automático hacia Diccionario LSEC/senas/.
    """
    clean_name = sign_name.strip()
    meta = get_sign_metadata(clean_name)

    # Nombres candidatos para la carpeta del video en senas_ultra_hd y senas
    candidates: List[str] = [clean_name]
    if meta:
        for k in ("sign", "palabra", "slug"):
            val = meta.get(k)
            if val and val not in candidates:
                candidates.append(val)

    res = resolve_gloss_to_sign(clean_name, include_animation=False)
    if res.get("found") and res.get("resolved_gloss"):
        rg = res["resolved_gloss"]
        if rg not in candidates:
            candidates.append(rg)
        rg_base = re.sub(r"__\d+$", "", rg).strip()
        if rg_base and rg_base not in candidates:
            candidates.append(rg_base)

    uhd_dirs = [p for p in [get_uhd_dir()] if p is not None]
    fallback_dirs = [p for p in [get_senas_dir()] if p is not None]

    def _find_healthy_video_in_dirs(dirs: List[Path], filenames: Tuple[str, ...]) -> Optional[Path]:
        expanded_cands: List[str] = []
        for c in candidates:
            if not c:
                continue
            for v in (c, unicodedata.normalize("NFC", c), unicodedata.normalize("NFD", c)):
                if v not in expanded_cands:
                    expanded_cands.append(v)
        norm_candidates = [normalize_text(c) for c in candidates if c and normalize_text(c)]
        for s_dir in dirs:
            if not s_dir.is_dir():
                continue

            checked_paths: set[str] = set()

            # 1. Búsqueda directa por candidato exacto (incluyendo variantes NFC y NFD)
            for cand in expanded_cands:
                for fname in filenames:
                    v_path = s_dir / cand / fname
                    if v_path.is_file():
                        checked_paths.add(str(v_path.resolve()))
                        if _is_video_stream_healthy(v_path):
                            return v_path
                        logger.warning("Video dañado detectado en %s; buscando respaldo sano.", v_path)

            # 2. Búsqueda O(1) por nombre normalizado cacheado
            norm_map = _get_norm_dir_map(s_dir)
            for nc in norm_candidates:
                for sub in norm_map.get(nc, ()):
                    for fname in filenames:
                        v_path = sub / fname
                        if v_path.is_file():
                            rp = str(v_path.resolve())
                            if rp in checked_paths:
                                continue
                            checked_paths.add(rp)
                            if _is_video_stream_healthy(v_path):
                                return v_path
                            logger.warning("Video dañado detectado en %s; buscando respaldo sano.", v_path)
        return None

    target_video: Optional[Path] = _find_healthy_video_in_dirs(uhd_dirs, ("video.mp4",))
    source_tier = "ultra_hd"

    if target_video is None:
        target_video = _find_healthy_video_in_dirs(fallback_dirs, ("video.mp4", "video.webm", "video.mkv"))
        if target_video is not None:
            source_tier = "fallback_senas"

    if target_video and target_video.is_file():
        safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_name)
        ext = target_video.suffix.lower()
        media_type = "video/mp4"
        if ext == ".webm":
            media_type = "video/webm"
        elif ext == ".mkv":
            media_type = "video/x-matroska"

        return FileResponse(
            path=str(target_video),
            media_type=media_type,
            filename=f"{safe_name}_original_uhd{ext or '.mp4'}",
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=7200",
                "X-Video-Source": source_tier,
            },
        )

    # Si no existe archivo de video local sano, verificar si hay enlace oficial de YouTube
    yt_url = meta.get("video_url") if meta else None
    yt_id = meta.get("video_id") if meta else None

    raise HTTPException(
        status_code=404,
        detail={
            "message": f"Video MP4 local no encontrado para '{sign_name}'.",
            "youtube_url": yt_url,
            "video_id": yt_id,
            "has_remote": bool(yt_url or yt_id),
        },
    )


@animation_router.get("/{sign_name}/illustration", summary="Sirve la imagen de ilustración oficial de la seña")
@animation_router.get("/{sign_name}/ilustracion", summary="Alias en español para la ilustración de la seña")
async def get_sign_illustration(sign_name: str):
    """
    Busca y sirve la imagen de ilustración oficial (PNG/JPG) de la seña desde el disco local.
    Si no existe localmente, retorna 404 informando si existe URL remota en el catálogo.
    """
    clean_name = sign_name.strip()
    meta = get_sign_metadata(clean_name)

    base_candidates = [clean_name]
    if meta:
        for k in ("sign", "palabra", "slug"):
            val = meta.get(k)
            if val and val not in base_candidates:
                base_candidates.append(val)

    candidates: List[str] = []
    for c in base_candidates:
        if not c:
            continue
        for v in (c, unicodedata.normalize("NFC", c), unicodedata.normalize("NFD", c)):
            if v not in candidates:
                candidates.append(v)

    raw_search_dirs: List[Optional[Path]] = [
        get_animations_dir(),
        get_v27_dir(),
        get_uhd_dir(),
        get_senas_dir(),
        get_v26_dir(),
        *CANDIDATE_PATHS,
        *UHD_CANDIDATE_PATHS,
        *SENAS_CANDIDATE_PATHS,
    ]
    search_dirs: List[Path] = []
    for p in raw_search_dirs:
        if p is not None and p not in search_dirs:
            search_dirs.append(p)

    target_img: Optional[Path] = None
    norm_candidates = [normalize_text(c) for c in base_candidates if c and normalize_text(c)]

    for s_dir in search_dirs:
        if not s_dir.is_dir():
            continue

        # 1. Búsqueda directa por candidato exacto (NFC y NFD)
        for cand in candidates:
            for ext in ("ilustracion.png", "ilustracion.jpg", "ilustracion.jpeg", "ilustracion.webp"):
                p = s_dir / cand / ext
                if p.is_file():
                    target_img = p
                    break
            if target_img:
                break
        if target_img:
            break

        # 2. Búsqueda O(1) por nombre normalizado cacheado
        norm_map = _get_norm_dir_map(s_dir)
        for nc in norm_candidates:
            for sub in norm_map.get(nc, ()):
                for ext in ("ilustracion.png", "ilustracion.jpg", "ilustracion.jpeg", "ilustracion.webp"):
                    p = sub / ext
                    if p.is_file():
                        target_img = p
                        break
                if target_img:
                    break
            if target_img:
                break
        if target_img:
            break

    if target_img and target_img.is_file():
        safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_name)
        media_type = "image/png"
        if target_img.suffix.lower() in [".jpg", ".jpeg"]:
            media_type = "image/jpeg"
        elif target_img.suffix.lower() == ".webp":
            media_type = "image/webp"

        return FileResponse(
            path=str(target_img),
            media_type=media_type,
            filename=f"{safe_name}_ilustracion{target_img.suffix}",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    remote_url = meta.get("imagen_url") if meta else None
    raise HTTPException(
        status_code=404,
        detail={
            "message": f"Ilustración local no encontrada para '{sign_name}'.",
            "remote_url": remote_url,
            "has_remote": bool(remote_url),
        },
    )


@animation_router.post("/finalize-export-mp4", summary="Remuxea/codifica video determinista a MP4 H.264 + AAC a 30.0 FPS constantes")
async def finalize_export_mp4(request: Request):
    """
    Recibe un archivo de video renderizado cuadro a cuadro desde el navegador (WebM o MP4)
    y opcionalmente el archivo de video/audio original, y genera un MP4 (H.264 + AAC)
    con tasa de cuadros constante exacta (por defecto 30.0 FPS) y audio original sincronizado.
    """
    import io
    from fractions import Fraction
    from fastapi.responses import Response

    form = await request.form()
    video_upload = form.get("video_file")
    audio_upload = form.get("audio_file")
    target_fps = int(float(form.get("fps") or 30))
    if target_fps <= 0:
        target_fps = 30

    if video_upload is None:
        raise HTTPException(status_code=400, detail="Falta 'video_file' en el formulario.")

    video_bytes = await video_upload.read()
    audio_bytes = await audio_upload.read() if audio_upload is not None else None

    try:
        import av
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"PyAV no disponible: {exc}")

    in_vid = av.open(io.BytesIO(video_bytes), mode="r")
    if not in_vid.streams.video:
        in_vid.close()
        raise HTTPException(status_code=400, detail="El archivo de video recibido no contiene pista de video.")

    in_vstream = in_vid.streams.video[0]
    width = in_vstream.width or 1280
    height = in_vstream.height or 720
    # Asegurar dimensiones pares para yuv420p (libx264)
    width = width - (width % 2)
    height = height - (height % 2)

    out_buf = io.BytesIO()
    out_container = av.open(out_buf, mode="w", format="mp4")
    out_vstream = out_container.add_stream("libx264", rate=target_fps)
    out_vstream.width = width
    out_vstream.height = height
    out_vstream.pix_fmt = "yuv420p"
    out_vstream.options = {"preset": "ultrafast", "crf": "20"}

    # Configurar pista de audio AAC si existe fuente de audio
    in_aud = None
    out_astream = None
    audio_resampler = None
    aud_source_bytes = audio_bytes if audio_bytes else video_bytes
    try:
        cand_aud = av.open(io.BytesIO(aud_source_bytes), mode="r")
        if cand_aud.streams.audio:
            in_aud = cand_aud
            out_astream = out_container.add_stream("aac", rate=48000)
            out_astream.layout = "stereo"
            audio_resampler = av.AudioResampler(format="fltp", layout="stereo", rate=48000)
        else:
            cand_aud.close()
    except Exception:
        pass

    tb = Fraction(1, target_fps)
    frame_idx = 0
    for frame in in_vid.decode(video=0):
        rgb = frame.to_ndarray(format="rgb24")
        if rgb.shape[1] != width or rgb.shape[0] != height:
            rgb = rgb[:height, :width, :]
        new_vf = av.VideoFrame.from_ndarray(rgb, format="rgb24")
        new_vf.pts = frame_idx
        new_vf.time_base = tb
        for packet in out_vstream.encode(new_vf):
            out_container.mux(packet)
        frame_idx += 1

    for packet in out_vstream.encode(None):
        out_container.mux(packet)

    max_duration_sec = frame_idx / float(target_fps) if frame_idx > 0 else 0.0

    if in_aud and out_astream and audio_resampler:
        try:
            audio_pts = 0
            max_samples = int(max_duration_sec * 48000) + 2048 if max_duration_sec > 0 else 0
            for aframe in in_aud.decode(audio=0):
                aframe.pts = None
                resampled_frames = audio_resampler.resample(aframe)
                for rf in resampled_frames:
                    if max_samples > 0 and audio_pts >= max_samples:
                        break
                    rf.pts = audio_pts
                    rf.time_base = Fraction(1, 48000)
                    audio_pts += rf.samples
                    for packet in out_astream.encode(rf):
                        out_container.mux(packet)
                if max_samples > 0 and audio_pts >= max_samples:
                    break
            for packet in out_astream.encode(None):
                out_container.mux(packet)
        except Exception as exc:
            logger.warning("Aviso codificando pista de audio AAC: %s", exc)
        finally:
            in_aud.close()

    in_vid.close()
    out_container.close()

    mp4_data = out_buf.getvalue()
    return Response(
        content=mp4_data,
        media_type="video/mp4",
        headers={
            "X-Export-FPS": str(target_fps),
            "X-Export-Frames": str(frame_idx),
            "Cache-Control": "no-store",
        },
    )


# Router alias en /api/animations-direct para compatibilidad directa con el frontend
animation_direct_alias_router = APIRouter(
    prefix="/api/animations-direct",
    tags=["Animaciones Directas 1:1 (Alias)"],
)
animation_direct_alias_router.add_api_route("/non-manual-standard", get_non_manual_standard, methods=["GET"])
animation_direct_alias_router.add_api_route("/stroke-index", get_stroke_index_endpoint, methods=["GET"])
animation_direct_alias_router.add_api_route("/resolve/{gloss}", resolve_single_gloss, methods=["GET"])
animation_direct_alias_router.add_api_route("/resolve", resolve_batch_glosses, methods=["POST"])
animation_direct_alias_router.add_api_route("/stats", animation_stats, methods=["GET"])
animation_direct_alias_router.add_api_route("/list", list_animations, methods=["GET"])
animation_direct_alias_router.add_api_route("/handshapes", get_handshapes_catalog, methods=["GET"])
animation_direct_alias_router.add_api_route("/finalize-export-mp4", finalize_export_mp4, methods=["POST"])
animation_direct_alias_router.add_api_route("/{sign_name}", get_sign_animation, methods=["GET"])
animation_direct_alias_router.add_api_route("/{sign_name}/stroke", get_sign_stroke_endpoint, methods=["GET"])
animation_direct_alias_router.add_api_route("/{sign_name}/qa", get_sign_qa, methods=["GET"])
animation_direct_alias_router.add_api_route("/{sign_name}/info", get_sign_info, methods=["GET"])
animation_direct_alias_router.add_api_route("/{sign_name}/video", get_sign_video, methods=["GET"])
animation_direct_alias_router.add_api_route("/{sign_name}/illustration", get_sign_illustration, methods=["GET"])
animation_direct_alias_router.add_api_route("/{sign_name}/ilustracion", get_sign_illustration, methods=["GET"])
