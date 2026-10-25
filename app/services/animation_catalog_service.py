"""
Servicio de Catálogo, Esquemas de Configuración Manual e Índice de Trazos VRM (v2.7 / v2.6 / v2.5).

Centraliza la resolución de directorios en disco, normalización de nombres,
lectura y caché de catalogo_ordenado.json, esquema_variantes.json y stroke_index.json,
así como el cálculo de facetas y estadísticas de cobertura QA.
"""

from __future__ import annotations
import csv, json, logging, os, re, sys, unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from app.config import external_path, settings

_DICCIONARIO_LSEC_DIR = external_path(settings.lsec_dictionary_root, "Diccionario LSEC")
if _DICCIONARIO_LSEC_DIR.is_dir() and str(_DICCIONARIO_LSEC_DIR) not in sys.path:
    sys.path.insert(0, str(_DICCIONARIO_LSEC_DIR))
try:
    import lsec_non_manual_standard as lsec_cnm
except Exception:
    lsec_cnm = None  # type: ignore

try:
    import lsec_kinematic_stabilizer as lsec_stabilizer
except Exception:
    lsec_stabilizer = None  # type: ignore

logger = logging.getLogger(__name__)

CANDIDATE_PATHS = [
    external_path(settings.lsec_animations_v27_dir, "Diccionario LSEC/senas_vrm_standardized_v2.7"),
    external_path("", "senas_vrm_standardized_v2.7"),
    external_path(settings.lsec_animations_v26_dir, "Diccionario LSEC/senas_vrm_direct_v2.6"),
    external_path("", "senas_vrm_direct_v2.6"),
    external_path(settings.lsec_animations_dir, "Diccionario LSEC/senas_vrm_direct"),
    external_path("", "senas_vrm_direct"),
]
V27_CANDIDATE_PATHS = [external_path(settings.lsec_animations_v27_dir, "Diccionario LSEC/senas_vrm_standardized_v2.7"), external_path("", "senas_vrm_standardized_v2.7")]
V26_CANDIDATE_PATHS = [external_path(settings.lsec_animations_v26_dir, "Diccionario LSEC/senas_vrm_direct_v2.6"), external_path("", "senas_vrm_direct_v2.6")]
V25_CANDIDATE_PATHS = [
    external_path(settings.lsec_animations_dir, "Diccionario LSEC/senas_vrm_direct"),
    external_path("", "senas_vrm_direct"),
    external_path("", "Diccionario LSEC/senas_vrm_direct"),
    external_path("", "_archive/Diccionario LSEC/senas_vrm_direct"),
]
UHD_CANDIDATE_PATHS = [external_path(settings.lsec_uhd_dir, "Diccionario LSEC/senas_ultra_hd"), external_path("", "senas_ultra_hd")]
SENAS_CANDIDATE_PATHS = [external_path(settings.lsec_senas_dir, "Diccionario LSEC/senas"), external_path("", "senas")]

_resolved_dir: Optional[Path] = None
_cached_signs: Optional[List[str]] = None
_cached_metadata: Optional[Dict[str, Dict[str, Any]]] = None
_cached_ordered_items: Optional[List[Dict[str, Any]]] = None
_dir_norm_map_cache: Dict[str, Dict[str, List[Path]]] = {}
_v27_stroke_index_cache: Optional[Dict[str, Any]] = None
_v27_stroke_norm_map: Optional[Dict[str, Dict[str, Any]]] = None
_v27_fs_stroke_map: Optional[Dict[str, Dict[str, Any]]] = None
_cached_catalog_mtime: float = 0.0
_cached_handshape_schema_mtime: float = 0.0
_cached_handshape_schema: Optional[Dict[str, Any]] = None
_MAIN_CM_IDS = {*[f"configuracion_manual_{i}" for i in range(1, 10)], "configuracion_manual_rostro", "configuracion_manual_*"}


def normalize_text(text: str) -> str:
    """Normaliza texto para comparaciones seguras de nombres de señas."""
    if not text:
        return ""
    s = "".join(c for c in unicodedata.normalize("NFKD", text.strip().lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s)


def _get_norm_dir_map(base_dir: Path) -> Dict[str, List[Path]]:
    """Construye y cachea un índice O(1) de nombre normalizado -> carpetas dentro de base_dir."""
    key = str(base_dir.resolve())
    if key in _dir_norm_map_cache:
        return _dir_norm_map_cache[key]
    mapping: Dict[str, List[Path]] = {}
    try:
        with os.scandir(str(base_dir)) as it:
            for entry in it:
                if entry.is_dir() and not entry.name.startswith(".") and normalize_text(entry.name):
                    mapping.setdefault(normalize_text(entry.name), []).append(Path(entry.path))
    except Exception:
        pass
    _dir_norm_map_cache[key] = mapping
    return mapping


def get_v27_dir() -> Optional[Path]:
    """Devuelve el directorio base de animaciones directas VRM v2.7 estandarizadas si existe."""
    return next((c for c in V27_CANDIDATE_PATHS if c and c.is_dir()), None)


def get_v27_stroke_index() -> Dict[str, Any]:
    """Carga y cachea en memoria el índice de trazos activos precalculado (stroke_index.json) para v2.7."""
    global _v27_stroke_index_cache, _v27_stroke_norm_map, _v27_fs_stroke_map
    if _v27_stroke_index_cache is not None:
        return _v27_stroke_index_cache
    v27_dir = get_v27_dir()
    candidates = ([v27_dir / "stroke_index.json"] if v27_dir else []) + [
        Path(__file__).resolve().parent.parent / "data" / "stroke_index_v27.json"
    ]
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
                    fs_map: Dict[str, Dict[str, Any]] = {}
                    for fk, fv in (payload.get("fingerspellingSigns") or {}).items():
                        if isinstance(fv, dict):
                            g = str(fv.get("grapheme") or "").strip().upper()
                            for alias in (fk, f"DACT_{g}", g, normalize_text(fk), f"dact{g.lower()}"):
                                if alias:
                                    fs_map[unicodedata.normalize("NFC", alias)] = fv
                    _v27_stroke_norm_map = norm_map
                    _v27_fs_stroke_map = fs_map
                    logger.info("✓ Índice de trazos v2.7 cargado (%d señas) desde %s", len(payload["signs"]), idx_path)
                    return _v27_stroke_index_cache
            except Exception as exc:
                logger.warning("Error leyendo stroke_index.json en %s: %s", idx_path, exc)
    _v27_stroke_index_cache = {"version": "2.7", "totalSigns": 0, "summary": {}, "signs": {}, "fingerspellingSigns": {}}
    _v27_stroke_norm_map, _v27_fs_stroke_map = {}, {}
    return _v27_stroke_index_cache


def get_sign_stroke_entry(sign_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Obtiene la entrada de trazo activo y poses de ancla para una seña léxica o de dactilología v2.7."""
    if not sign_name:
        return None
    signs_map = get_v27_stroke_index().get("signs") or {}
    clean = unicodedata.normalize("NFC", sign_name.strip())
    if clean in signs_map:
        return signs_map[clean]
    if sign_name in signs_map:
        return signs_map[sign_name]
    nk = normalize_text(clean)
    if _v27_stroke_norm_map and nk in _v27_stroke_norm_map:
        return _v27_stroke_norm_map[nk]
    if _v27_fs_stroke_map:
        return _v27_fs_stroke_map.get(clean) or _v27_fs_stroke_map.get(clean.upper()) or _v27_fs_stroke_map.get(nk)
    return None


def get_v26_dir() -> Optional[Path]:
    """Devuelve el directorio base de animaciones directas VRM v2.6 corregidas si existe."""
    return next((c for c in V26_CANDIDATE_PATHS if c and c.is_dir()), None)


def get_v25_dir() -> Path:
    """Devuelve el directorio base de animaciones directas VRM v2.5 (catálogo completo)."""
    for candidate in V25_CANDIDATE_PATHS:
        if candidate and candidate.is_dir():
            return candidate
    archive_fallback = external_path("", "_archive/Diccionario LSEC/senas_vrm_direct")
    return archive_fallback if archive_fallback.is_dir() else external_path(settings.lsec_animations_dir, "Diccionario LSEC/senas_vrm_direct")


def get_animations_dir() -> Path:
    """Devuelve el directorio base de animaciones directas VRM (v2.7 preferente, con fallback a v2.6 -> v2.5 / _archive)."""
    global _resolved_dir
    if _resolved_dir and _resolved_dir.is_dir():
        return _resolved_dir
    for getter, label in ((get_v27_dir, "v2.7 primario"), (get_v26_dir, "v2.6 fallback")):
        d = getter()
        if d and d.is_dir():
            _resolved_dir = d
            logger.info("✓ Directorio de animaciones directas VRM resuelto en (%s): %s", label, _resolved_dir)
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
    return next((c for c in UHD_CANDIDATE_PATHS if c and c.is_dir()), None)


def get_senas_dir() -> Optional[Path]:
    """Devuelve el directorio base del corpus original de señas (fallback sano)."""
    configured = os.environ.get("LSEC_SENAS_DIR") or settings.lsec_senas_dir
    if configured:
        path = external_path(configured, "Diccionario LSEC/senas")
        return path if path.is_dir() else None
    return next((c for c in SENAS_CANDIDATE_PATHS if c and c.is_dir()), None)


def get_configuracion_manual_dir() -> Optional[Path]:
    """Devuelve el directorio local de láminas y variantes de Configuración Manual (I a IX, Rostro y *)."""
    candidates = [external_path(settings.lsec_manual_config_dir, "Diccionario LSEC/configuracion_manual"), external_path("", "configuracion_manual")]
    return next((c for c in candidates if c.is_dir()), None)


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

    is_face_only = bool(cm_id == "configuracion_manual_rostro" or cm_meta.get("face_only") or item.get("face_only") or item.get("solo_rostro"))
    arms_rest = bool(is_face_only or cm_meta.get("arms_in_rest_pose") or item.get("arms_in_rest_pose") or item.get("brazos_en_reposo"))

    item["hand_variant_key"] = v_short
    item["hand_variant_label"] = v_label
    item["face_only"] = is_face_only
    item["arms_in_rest_pose"] = arms_rest

    # Inferir geolecto (Sierra / Costa / Nacional) y bimanualidad querológica (stroke_index_v27)
    sign_str = str(item.get("sign") or item.get("palabra") or "")
    slug_str = str(item.get("slug") or "")
    palabra_str = str(item.get("palabra") or sign_str)
    low_title = f"{sign_str} {palabra_str} {slug_str}".lower()
    if "(sierra)" in low_title or "en la sierra" in low_title or slug_str.lower().endswith("-sierra"):
        item["geolect"] = "Sierra"
    elif "(costa)" in low_title or "en la costa" in low_title or slug_str.lower().endswith("-costa"):
        item["geolect"] = "Costa"
    else:
        item["geolect"] = item.get("geolect") or "Nacional"

    stroke_meta = get_sign_stroke_entry(sign_str) or get_sign_stroke_entry(palabra_str)
    raw_ah = stroke_meta.get("activeHands") if stroke_meta else None
    if is_face_only:
        active_hands = "none"
    elif isinstance(raw_ah, (list, tuple, set)):
        ah_set = {str(h).lower() for h in raw_ah}
        if "left" in ah_set and "right" in ah_set:
            active_hands = "both"
        elif "right" in ah_set:
            active_hands = "right"
        elif "left" in ah_set:
            active_hands = "left"
        else:
            active_hands = "none"
    elif isinstance(raw_ah, str) and raw_ah.strip():
        active_hands = raw_ah.strip().lower()
    else:
        active_hands = "both"
    item["active_hands"] = active_hands
    item["bimanual"] = "bimanual" if active_hands == "both" else ("face_only" if active_hands == "none" else "unimanual")

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
        "id": cm_id, "number": cm_meta.get("number"), "roman": roman,
        "name": cm_meta.get("name") or cm_id, "color_hex": color_hex,
        "sheet_image": sheet_img, "sheet_url": sheet_url,
        "variant_id": v_id, "variant_key": v_short, "variant_label": v_label,
        "variant_description": v_meta.get("description") or v_label,
        "variant_image_url": v_img_url, "face_only": is_face_only, "arms_in_rest_pose": arms_rest,
    }
    return item


def _load_catalog_cache() -> None:
    """Carga y cachea la lista ordenada según catalogo_lsec.json y metadata enriquecida (normalizada en NFC y sin duplicados)."""
    global _cached_signs, _cached_metadata, _cached_ordered_items, _cached_catalog_mtime
    base_dir = get_animations_dir()
    ordered_json = base_dir / "catalogo_ordenado.json"
    if not ordered_json.is_file() and (base_dir.parent / "catalogo_ordenado_vrm.json").is_file():
        ordered_json = base_dir.parent / "catalogo_ordenado_vrm.json"
    try:
        current_mtime = ordered_json.stat().st_mtime if ordered_json.is_file() else 0.0
    except OSError:
        current_mtime = 0.0
    _load_handshape_schema()
    effective_mtime = current_mtime + _cached_handshape_schema_mtime
    if _cached_signs is not None and _cached_metadata is not None and _cached_catalog_mtime == effective_mtime:
        return
    signs_list: List[str] = []
    meta_dict: Dict[str, Dict[str, Any]] = {}
    ordered_items: List[Dict[str, Any]] = []
    if ordered_json.is_file():
        try:
            data = json.loads(ordered_json.read_text(encoding="utf-8"))
            for item in data.get("signs", []):
                raw_name = item.get("sign")
                s_name = unicodedata.normalize("NFC", str(raw_name).strip()) if raw_name else ""
                if not s_name or s_name in meta_dict:
                    continue
                norm_item = dict(item, sign=s_name)
                if isinstance(norm_item.get("palabra"), str):
                    norm_item["palabra"] = unicodedata.normalize("NFC", norm_item["palabra"].strip())
                _enrich_item_with_handshape_meta(norm_item)
                signs_list.append(s_name)
                meta_dict[s_name] = norm_item
                ordered_items.append(norm_item)
            _cached_signs, _cached_metadata, _cached_ordered_items, _cached_catalog_mtime = signs_list, meta_dict, ordered_items, effective_mtime
            logger.info("✓ Cargadas %d señas ordenadas (NFC únicas) desde %s", len(_cached_signs), ordered_json)
            return
        except Exception as exc:
            logger.warning("Error leyendo %s: %s", ordered_json, exc)
    csv_file = base_dir / "qa_summary.csv"
    if csv_file.is_file():
        try:
            with open(csv_file, "r", encoding="utf-8", errors="replace") as f:
                for idx, row in enumerate(csv.DictReader(f), start=1):
                    sign = unicodedata.normalize("NFC", (row.get("sign") or "").strip())
                    if sign and sign not in meta_dict:
                        signs_list.append(sign)
                        palabra_nfc = unicodedata.normalize("NFC", (row.get("palabra") or sign).strip())
                        c_idx = int(row["catalog_index"]) if row.get("catalog_index") else idx
                        item_meta = _enrich_item_with_handshape_meta({"sign": sign, "catalog_index": c_idx, "slug": row.get("slug", ""), "palabra": palabra_nfc, "qa": row})
                        meta_dict[sign] = item_meta
                        ordered_items.append(item_meta)
            _cached_signs, _cached_metadata, _cached_ordered_items = signs_list, meta_dict, ordered_items
            logger.info("✓ Indexadas %d señas únicas (NFC) desde qa_summary.csv", len(_cached_signs))
            return
        except Exception as exc:
            logger.warning("Error leyendo qa_summary.csv: %s", exc)
    try:
        raw = [unicodedata.normalize("NFC", n) for n in os.listdir(base_dir) if not n.startswith(".") and not n.endswith((".csv", ".json")) and (base_dir / n).is_dir()]
        signs_list = sorted(set(raw), key=lambda s: s.lower())
        for idx, s in enumerate(signs_list, start=1):
            meta_dict[s] = _enrich_item_with_handshape_meta({"sign": s, "catalog_index": idx, "palabra": s})
            ordered_items.append(meta_dict[s])
        _cached_signs, _cached_metadata, _cached_ordered_items = signs_list, meta_dict, ordered_items
        logger.info("✓ Indexadas %d señas únicas (NFC) mediante listdir", len(_cached_signs))
    except Exception as exc:
        logger.warning("Error listando directorio %s: %s", base_dir, exc)
        _cached_signs, _cached_metadata, _cached_ordered_items = [], {}, []


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
    if sign_nfc in _cached_metadata:
        return _cached_metadata[sign_nfc]
    if sign_name in _cached_metadata:
        return _cached_metadata[sign_name]
    norm_target = normalize_text(sign_nfc)
    for name, meta in _cached_metadata.items():
        if norm_target in (normalize_text(name), normalize_text(meta.get("palabra", "")), normalize_text(meta.get("slug", ""))):
            return meta
    base_dir = get_animations_dir()
    for candidate_name in (sign_nfc, sign_name, unicodedata.normalize("NFD", sign_nfc)):
        info_file = base_dir / candidate_name / "info.json"
        if info_file.is_file():
            try:
                return _enrich_item_with_handshape_meta(json.loads(info_file.read_text(encoding="utf-8")))
            except Exception:
                pass
    return None


def _cm_sort_key(cm_id: Optional[str]) -> int:
    if not cm_id:
        return 99
    if cm_id.endswith(("rostro", "*")):
        return 10 if cm_id.endswith("rostro") else 11
    m = re.search(r"(\d+)$", cm_id)
    return int(m.group(1)) if m else 99


def _variant_sort_key(v_key: Optional[str]) -> int:
    if not v_key or v_key in ("base", "sin_recuadro"):
        return 0
    m = re.search(r"(\d+)$", str(v_key))
    return int(m.group(1)) if m else 99


def build_animations_list_payload(
    q: Optional[str] = None, hand_config: Optional[str] = None, hand_variant: Optional[str] = None,
    alfa: Optional[str] = None, category: Optional[str] = None, geolect: Optional[str] = None,
    bimanual: Optional[str] = None, facial_archetype: Optional[str] = None,
    sort_by: Optional[str] = "catalog", version: Optional[str] = None, limit: int = 5000, offset: int = 0,
) -> Dict[str, Any]:
    """Construye la respuesta paginada y facetada para /api/v1/animations/list."""
    _load_catalog_cache()
    all_signs, all_items = _cached_signs or [], _cached_ordered_items or []
    v27_dir, v26_dir = get_v27_dir(), get_v26_dir()
    eff_version = version or ("2.7" if v27_dir else ("2.6" if v26_dir else "2.5"))
    pipeline_ver = "2.7_Estandarizado" if (eff_version == "2.7" and v27_dir) else ("2.6_Directo_1a1_corregido" if (eff_version == "2.6" and v26_dir) else "2.5_Directo_1a1")

    _roman_to_num = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6", "VII": "7", "VIII": "8", "IX": "9"}
    hc_filter = hand_config.strip() if hand_config and hand_config.strip() else None
    if hc_filter and hc_filter.isdigit():
        hc_filter = f"configuracion_manual_{hc_filter}"
    elif hc_filter and hc_filter.upper() in _roman_to_num:
        hc_filter = f"configuracion_manual_{_roman_to_num[hc_filter.upper()]}"
    elif hc_filter and hc_filter.upper().startswith("CONFIGURACION_MANUAL_") and hc_filter.split("_")[-1].upper() in _roman_to_num:
        hc_filter = f"configuracion_manual_{_roman_to_num[hc_filter.split('_')[-1].upper()]}"
    elif hc_filter and hc_filter.lower() in ("rostro", "face"):
        hc_filter = "configuracion_manual_rostro"
    elif hc_filter == "*":
        hc_filter = "configuracion_manual_*"

    hv_filter = hand_variant.strip() if hand_variant and hand_variant.strip() else None
    alfa_filter = alfa.strip().lower() if alfa and alfa.strip() else None
    if alfa_filter and len(alfa_filter) == 1 and alfa_filter.isalpha():
        alfa_filter = f"alfa-{alfa_filter}"
    cat_filter = category.strip().lower() if category and category.strip() else None
    geo_filter = geolect.strip().capitalize() if geolect and geolect.strip() else None
    bim_filter = bimanual.strip().lower() if bimanual and bimanual.strip() else None
    arch_filter = facial_archetype.strip().lower() if facial_archetype and facial_archetype.strip() else None
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
        if cat_filter and cat_filter not in [str(c).lower() for c in (it.get("categorias") or [])]:
            continue
        if geo_filter and (it.get("geolect") or "Nacional") != geo_filter:
            continue
        if bim_filter:
            act_h = str(it.get("active_hands") or "both").lower()
            bim_tag = str(it.get("bimanual") or ("bimanual" if act_h == "both" else "unimanual")).lower()
            if bim_filter not in (act_h, bim_tag):
                continue
        if arch_filter:
            it_arch = str(it.get("facial_archetype") or "neutral").lower()
            if arch_filter == "non_neutral":
                if it_arch == "neutral":
                    continue
            elif it_arch != arch_filter:
                continue
        if q_term and q_term not in normalize_text(s) and q_term not in normalize_text(it.get("palabra", "")):
            continue
        filtered_pairs.append((s, it))

    if sort_by == "hand_config":
        filtered_pairs.sort(key=lambda pair: (_cm_sort_key(pair[1].get("hand_configuration")), _variant_sort_key(pair[1].get("hand_variant_key")), str(pair[1].get("alphabetical_group") or "zzz"), int(pair[1].get("catalog_index") or 999999)))
    elif sort_by == "alfa":
        filtered_pairs.sort(key=lambda pair: (str(pair[1].get("alphabetical_group") or "zzz"), int(pair[1].get("catalog_index") or 999999)))

    filtered_signs, filtered_items = [p[0] for p in filtered_pairs], [p[1] for p in filtered_pairs]
    cm_facets, variant_facets, alfa_facets = {}, {}, {}
    geo_facets, bim_facets, arch_facets = {}, {}, {}
    for _, it in filtered_pairs:
        cm_k = it.get("hand_configuration") or "configuracion_manual_*"
        hv_k = it.get("hand_variant") or f"{cm_k}_base"
        al_k = it.get("alphabetical_group") or "sin-alfa"
        geo_k = it.get("geolect") or "Nacional"
        bim_k = it.get("active_hands") or "both"
        ar_k = it.get("facial_archetype") or "neutral"
        cm_facets[cm_k] = cm_facets.get(cm_k, 0) + 1
        variant_facets[hv_k] = variant_facets.get(hv_k, 0) + 1
        alfa_facets[al_k] = alfa_facets.get(al_k, 0) + 1
        geo_facets[geo_k] = geo_facets.get(geo_k, 0) + 1
        bim_facets[bim_k] = bim_facets.get(bim_k, 0) + 1
        arch_facets[ar_k] = arch_facets.get(ar_k, 0) + 1

    total = len(filtered_signs)
    return {
        "total": total, "offset": offset, "limit": limit, "query": q,
        "version": eff_version, "pipeline_version": pipeline_ver,
        "filters": {
            "hand_config": hc_filter, "hand_variant": hv_filter, "alfa": alfa_filter,
            "category": cat_filter, "geolect": geo_filter, "bimanual": bim_filter,
            "facial_archetype": arch_filter, "sort_by": sort_by or "catalog",
        },
        "facets": {
            "by_hand_configuration": cm_facets, "by_hand_variant": variant_facets,
            "by_alphabet": alfa_facets, "by_geolect": geo_facets,
            "by_bimanual": bim_facets, "by_facial_archetype": arch_facets,
        },
        "order": "Catálogo Oficial Diccionario LSEC (CONADIS)",
        "signs": filtered_signs[offset : offset + limit],
        "items": filtered_items[offset : offset + limit],
    }


def build_handshapes_catalog_payload(include_signs: bool = False) -> Dict[str, Any]:
    """Construye la jerarquía de Configuraciones Manuales LSEC (I–IX, Rostro y *) para /api/v1/animations/handshapes."""
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
            "name": cm_key, "color_hex": "#64748B",
            "sheet_image": None if cm_key.endswith("*") else f"{cm_key}.jpg", "variants": [],
        }
        sheet_img = cm_meta.get("sheet_image")
        sheet_url = f"/configuracion-manual/{sheet_img}" if sheet_img else None

        variants_list: List[Dict[str, Any]] = []
        variants_map: Dict[str, Dict[str, Any]] = {}
        for v in cm_meta.get("variants") or []:
            v_id = v["variant_id"]
            v_img = v.get("image_file")
            v_entry: Dict[str, Any] = {
                "variant_id": v_id, "short_key": v.get("short_key") or "base",
                "label": v.get("label") or v_id, "description": v.get("description") or "",
                "image_file": v_img, "image_url": f"/configuracion-manual/{v_img}" if v_img else None,
                "total_signs": 0,
            }
            if include_signs:
                v_entry["signs"] = []
            variants_list.append(v_entry)
            variants_map[v_id] = v_entry

        cfg_entry: Dict[str, Any] = {
            "id": cm_key, "number": cm_meta.get("number"), "roman": cm_meta.get("roman"),
            "name": cm_meta.get("name"), "color_hex": cm_meta.get("color_hex"),
            "sheet_image": sheet_img, "sheet_url": sheet_url,
            "face_only": bool(cm_meta.get("face_only") or cm_key == "configuracion_manual_rostro"),
            "arms_in_rest_pose": bool(cm_meta.get("arms_in_rest_pose") or cm_key == "configuracion_manual_rostro"),
            "total_signs": 0, "variants_count": len(variants_list),
            "by_alphabet": {}, "variants": variants_list, "_variants_map": variants_map,
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


def build_animation_stats_payload(version: Optional[str] = None) -> Dict[str, Any]:
    """Construye las estadísticas globales de cobertura y QA para /api/v1/animations/stats."""
    v27_dir, v26_dir, v25_dir = get_v27_dir(), get_v26_dir(), get_v25_dir()
    eff_version = version or ("2.7" if v27_dir else ("2.6" if v26_dir else "2.5"))
    target_dir = v27_dir if (eff_version == "2.7" and v27_dir) else (v26_dir if (eff_version == "2.6" and v26_dir) else v25_dir)
    all_signs = get_available_signs()
    summary_csv = target_dir / "qa_summary.csv"
    approved, needs_review = 0, 0
    fps_counts: Dict[str, int] = {}
    if summary_csv.is_file():
        try:
            with open(summary_csv, "r", encoding="utf-8", errors="replace") as fp:
                for row in csv.DictReader(fp):
                    if row.get("needs_review") == "True":
                        needs_review += 1
                    else:
                        approved += 1
                    fps_val = str(row.get("fps", "60.0"))
                    fps_counts[fps_val] = fps_counts.get(fps_val, 0) + 1
        except Exception as exc:
            logger.warning("Error leyendo qa_summary.csv: %s", exc)
    ver_tag = "2.7_Estandarizado" if (eff_version == "2.7" and v27_dir) else ("2.6_Directo_1a1_corregido" if (eff_version == "2.6" and v26_dir) else "2.5_Directo_1a1")
    v26_approved, v26_needs_review = 0, 0
    if v26_dir and (v26_dir / "qa_summary.csv").is_file():
        try:
            with open(v26_dir / "qa_summary.csv", "r", encoding="utf-8", errors="replace") as fp:
                for row in csv.DictReader(fp):
                    v26_needs_review += int(row.get("needs_review") == "True")
                    v26_approved += int(row.get("needs_review") != "True")
        except Exception:
            pass
    v27_approved, v27_needs_review, v27_standardized, v27_skipped = 0, 0, 0, 0
    if v27_dir and (v27_dir / "qa_summary.csv").is_file():
        try:
            with open(v27_dir / "qa_summary.csv", "r", encoding="utf-8", errors="replace") as fp:
                for row in csv.DictReader(fp):
                    v27_needs_review += int(row.get("needs_review") == "True")
                    v27_approved += int(row.get("needs_review") != "True")
                    h_status = (row.get("hand_std_status") or "").strip()
                    v27_standardized += int(h_status == "STANDARDIZED")
                    v27_skipped += int(bool(h_status and h_status != "STANDARDIZED"))
        except Exception:
            pass
    return {
        "total_signs": len(all_signs), "directory": str(target_dir),
        "approved_high_quality": approved if approved else len(all_signs),
        "needs_review": needs_review, "fps_distribution": fps_counts,
        "pipeline_version": ver_tag, "version_active": eff_version,
        "active_default_version": "2.7" if v27_dir else ("2.6" if v26_dir else "2.5"),
        "order": "Catálogo Oficial Diccionario LSEC (CONADIS)",
        "v27_stats": {
            "available": bool(v27_dir), "approved": v27_approved, "needs_review": v27_needs_review,
            "standardized": v27_standardized, "skipped": v27_skipped, "total": v27_approved + v27_needs_review,
            "version": "2.7_Estandarizado", "directory": str(v27_dir) if v27_dir else None,
        },
        "v26_stats": {
            "available": bool(v26_dir), "approved": v26_approved, "needs_review": v26_needs_review,
            "total": v26_approved + v26_needs_review, "version": "2.6_Directo_1a1_corregido",
        },
    }


def build_non_manual_standard_payload() -> Optional[Dict[str, Any]]:
    """Carga el manifiesto de estándar CNM o lo construye dinámicamente si lsec_cnm está presente."""
    manifest_path = _DICCIONARIO_LSEC_DIR / "configuracion_manual" / "estandar_componentes_no_manuales.json"
    expected_ver = getattr(lsec_cnm, "CNM_STANDARD_VERSION", "1.1") if lsec_cnm is not None else None
    if manifest_path.is_file():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if expected_ver is None or payload.get("version") == expected_ver:
                return payload
        except Exception as exc:
            logger.warning("Error leyendo estandar_componentes_no_manuales.json: %s", exc)
    return lsec_cnm.build_manifest_and_update_dataset(_DICCIONARIO_LSEC_DIR, update_v26_files=False) if lsec_cnm is not None else None


def build_stroke_index_payload(
    q: Optional[str] = None, signs: Optional[str] = None, limit: int = 100,
    summary_only: bool = False, resolve_fn: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Construye la consulta filtrada sobre el índice de trazos activos v2.7."""
    idx_data = get_v27_stroke_index()
    all_signs_map: Dict[str, Any] = idx_data.get("signs") or {}
    if summary_only:
        return {"version": idx_data.get("version", "2.7"), "totalSigns": idx_data.get("totalSigns", len(all_signs_map)), "summary": idx_data.get("summary", {})}
    selected: Dict[str, Any] = {}
    if signs:
        for tok in (t.strip() for t in signs.split(",") if t.strip()):
            entry = get_sign_stroke_entry(tok)
            if not entry and resolve_fn is not None:
                res = resolve_fn(tok, version="2.7", include_animation=False)
                if res.get("found") and res.get("resolved_gloss"):
                    entry = get_sign_stroke_entry(res["resolved_gloss"])
            if entry:
                selected[tok] = entry
    else:
        nq = normalize_text(q) if q else None
        for s_name, s_entry in all_signs_map.items():
            if nq is None or nq in normalize_text(s_name):
                selected[s_name] = s_entry
                if len(selected) >= limit:
                    break
    fs_signs_map: Dict[str, Any] = idx_data.get("fingerspellingSigns") or {}
    return {
        "version": idx_data.get("version", "2.7"), "totalSigns": idx_data.get("totalSigns", len(all_signs_map)),
        "totalFingerspellingSigns": idx_data.get("totalFingerspellingSigns", len(fs_signs_map)),
        "returnedSigns": len(selected), "summary": idx_data.get("summary", {}),
        "signs": selected, "fingerspellingSigns": fs_signs_map,
    }


def ensure_sign_animation_stabilized(
    raw_data: Dict[str, Any], sign_name: str, anim_file: Optional[Path] = None,
    cat_meta: Optional[Dict[str, Any]] = None, persist_to_disk: bool = True,
) -> Dict[str, Any]:
    """Garantiza que el diccionario `animation.json` haya sido estabilizado por `lsec_kinematic_stabilizer`."""
    if lsec_stabilizer is None or not isinstance(raw_data, dict):
        return raw_data
    clean_sign = str(sign_name or "").strip()
    if clean_sign.upper().startswith("DACT_"):
        return raw_data
    meta = raw_data.setdefault("metadata", {})
    stab_ver = getattr(lsec_stabilizer, "STABILIZER_VERSION", "2.7.2_Stabilized")
    existing_stab = meta.get("kinematicStabilizer")
    if isinstance(existing_stab, dict) and existing_stab.get("version") == stab_ver:
        return raw_data
    info_data: Optional[Dict[str, Any]] = None
    if anim_file and anim_file.parent.is_dir() and (anim_file.parent / "info.json").is_file():
        try:
            info_data = json.loads((anim_file.parent / "info.json").read_text(encoding="utf-8"))
        except Exception:
            info_data = None
    try:
        lsec_stabilizer.stabilize_sign_animation_dict(raw_data, sign_name=clean_sign, cat_entry=cat_meta, info_data=info_data, force=False)
        if persist_to_disk and anim_file and anim_file.is_file():
            v27_dir = get_v27_dir()
            if v27_dir and str(anim_file.resolve()).startswith(str(v27_dir.resolve())):
                tmp_file = anim_file.with_suffix(".json.tmp")
                tmp_file.write_text(json.dumps(raw_data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                tmp_file.replace(anim_file)
    except Exception as exc:
        logger.warning("No se pudo aplicar estabilizador cinemático en '%s': %s", clean_sign, exc)
    return raw_data
