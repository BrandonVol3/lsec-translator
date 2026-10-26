"""
Router REST para consultar y servir animaciones VRM 1:1 generadas por el Pipeline LSEC v2.5/v2.6/v2.7
y videos originales Ultra HD del Diccionario Oficial LSEC.

Proporciona:
  GET /api/v1/animations/list?q=...&limit=50   (Ordenado estrictamente según catalogo_lsec.json)
  GET /api/v1/animations/{sign_name}           (Archivo animation.json, con soporte fallback/caché)
  GET /api/v1/animations/{sign_name}/qa        (Métricas cinemáticas QA)
  GET /api/v1/animations/{sign_name}/info      (Ficha lingüística e info.json de catálogo)
  GET /api/v1/animations/{sign_name}/video     (Streaming del video MP4 original Ultra HD)
  GET /api/v1/animations/stats                 (Estadísticas globales)

Nota arquitectónica (Patrón Fachada):
  La lógica pesada de catálogo, resolución léxica/morfológica e integridad de medios
  reside en `app.services.animation_catalog_service`, `app.services.animation_lexical_resolver`
  y `app.services.animation_media_service`. Se re-exportan todos los símbolos públicos y privados
  para preservar el 100 % de retrocompatibilidad en tests y servicios.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

# Re-exportaciones (Patrón Fachada) desde los servicios modulares
from app.services.animation_catalog_service import (
    CANDIDATE_PATHS,
    SENAS_CANDIDATE_PATHS,
    UHD_CANDIDATE_PATHS,
    V25_CANDIDATE_PATHS,
    V26_CANDIDATE_PATHS,
    V27_CANDIDATE_PATHS,
    _DICCIONARIO_LSEC_DIR,
    _MAIN_CM_IDS,
    _cm_sort_key,
    _enrich_item_with_handshape_meta,
    _get_norm_dir_map,
    _load_catalog_cache,
    _load_handshape_schema,
    _variant_sort_key,
    build_animation_stats_payload,
    build_animations_list_payload,
    build_handshapes_catalog_payload,
    build_non_manual_standard_payload,
    build_stroke_index_payload,
    get_animations_dir,
    get_available_signs,
    get_configuracion_manual_dir,
    get_senas_dir,
    get_sign_metadata,
    get_sign_stroke_entry,
    get_uhd_dir,
    get_v25_dir,
    get_v26_dir,
    get_v27_dir,
    get_v27_stroke_index,
    lsec_cnm,
    normalize_text,
)
from app.services.animation_fingerspelling_service import (
    DYNAMIC_GRAPHEMES,
    GRAPHEME_METADATA,
    LSEC_FINGERSPELLING_GRAPHEMES,
    STATIC_GRAPHEMES,
    build_fingerspelling_catalog_payload,
    is_fingerspelling_query,
    synthesize_fingerspelling_animation,
    tokenize_lsec_fingerspelling,
)
from app.services.animation_lexical_resolver import (
    _LSEC_LEXICAL_ALIASES,
    _PREFERRED_HOMONYMS,
    _build_v26_lexical_index,
    _expand_gender_token,
    _generate_morphological_candidates,
    _is_fingerspelling_gloss,
    _select_best_candidate,
    build_animation_catalog_contract,
    parse_sign_title_tokens,
    resolve_batch_glosses_payload,
    resolve_gloss_to_sign,
)
from app.services.animation_media_service import (
    _is_video_stream_healthy,
    encode_deterministic_mp4_response,
    resolve_sign_animation_response,
    resolve_sign_illustration_response,
    resolve_sign_info_response,
    resolve_sign_qa_response,
    resolve_sign_video_response,
)

animation_router = APIRouter(prefix="/api/v1/animations", tags=["Animaciones Directas 1:1 (VRM)"])


@animation_router.get("/list", summary="Lista todas las señas con animación directa 1:1 con filtros de Configuración Manual, Sub-variante, Geolecto y Parámetros Querológicos")
async def list_animations(
    q: Optional[str] = Query(None, description="Término de búsqueda opcional"),
    hand_config: Optional[str] = Query(None, description="Filtrar por Configuración Manual (ej. configuracion_manual_3, configuracion_manual_rostro o configuracion_manual_*)"),
    hand_variant: Optional[str] = Query(None, description="Filtrar por sub-variante (ej. configuracion_manual_3_v2 o configuracion_manual_rostro_base)"),
    alfa: Optional[str] = Query(None, description="Filtrar por letra inicial del catálogo (ej. alfa-a)"),
    category: Optional[str] = Query(None, description="Filtrar por categoría arbitraria en info.json"),
    geolect: Optional[str] = Query(None, description="Filtrar por geolecto regional: 'Nacional', 'Sierra' o 'Costa'"),
    bimanual: Optional[str] = Query(None, description="Filtrar por lateralidad/bimanualidad: 'both', 'right', 'left', 'none'"),
    facial_archetype: Optional[str] = Query(None, description="Filtrar por arquetipo de Rasgo No Manual (ej. 'open_kiss_pucker', 'lips_projected_closed', 'non_neutral')"),
    sort_by: Optional[str] = Query("catalog", description="Ordenamiento: 'catalog' (defecto), 'hand_config', 'alfa'"),
    version: Optional[str] = Query(None, description="Versión preferida: '2.7', '2.6' o '2.5'"),
    limit: int = Query(5000, ge=1, le=10000, description="Límite de resultados devueltos"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginación"),
) -> Dict[str, Any]:
    """
    Retorna la lista de señas directas 1:1 ordenadas según catalogo_lsec.json (o por configuración manual),
    incluyendo metadata de Configuración Manual (I–IX, Rostro y *), sub-variante, geolecto y rasgos no manuales.
    """
    return build_animations_list_payload(
        q=q,
        hand_config=hand_config,
        hand_variant=hand_variant,
        alfa=alfa,
        category=category,
        geolect=geolect,
        bimanual=bimanual,
        facial_archetype=facial_archetype,
        sort_by=sort_by,
        version=version,
        limit=limit,
        offset=offset,
    )


@animation_router.get("/handshapes", summary="Obtiene el catálogo jerárquico de Configuraciones Manuales LSEC (I–IX, Rostro y *) y sus sub-variantes")
async def get_handshapes_catalog(
    include_signs: bool = Query(False, description="Incluir el listado completo de señas dentro de cada configuración y sub-variante"),
) -> Dict[str, Any]:
    """
    Devuelve la estructura oficial de las 9 Configuraciones Manuales (I a IX) + 'Rostro' + '*',
    sus colores oficiales, URLs de las láminas completas y de los recortes de sub-variantes,
    junto con el conteo exacto de señas por configuración, sub-variante y letra alfabética.
    """
    return build_handshapes_catalog_payload(include_signs=include_signs)


@animation_router.get("/stats", summary="Estadísticas globales de cobertura y QA del pipeline 1:1")
async def animation_stats(version: Optional[str] = Query(None, description="Versión preferida: '2.7', '2.6' o '2.5'")) -> Dict[str, Any]:
    return build_animation_stats_payload(version=version)


@animation_router.get(
    "/catalog",
    summary="Contrato de versiones y disponibilidad del catálogo VRM",
)
async def animation_catalog() -> Dict[str, Any]:
    """Expone un manifiesto estable de las versiones de animación disponibles."""
    return build_animation_catalog_contract()


@animation_router.get("/non-manual-standard", summary="Obtiene el estándar auditable de Componentes No Manuales (CNM) y sus excepciones explícitas")
async def get_non_manual_standard() -> Dict[str, Any]:
    payload = build_non_manual_standard_payload()
    if payload is not None:
        return payload
    raise HTTPException(status_code=404, detail="Manifiesto de estándar CNM no disponible.")


@animation_router.get("/stroke-index", summary="Consulta el índice precalculado de trazos activos (stroke_index.json) para el catálogo v2.7")
async def get_stroke_index_endpoint(
    q: Optional[str] = Query(None, description="Filtro opcional por nombre de seña"),
    signs: Optional[str] = Query(None, description="Lista separada por comas de señas o glosas a consultar"),
    limit: int = Query(100, ge=1, le=5000, description="Máximo de entradas a devolver"),
    summary_only: bool = Query(False, description="Devolver únicamente las estadísticas globales del índice"),
) -> Dict[str, Any]:
    return build_stroke_index_payload(
        q=q,
        signs=signs,
        limit=limit,
        summary_only=summary_only,
        resolve_fn=resolve_gloss_to_sign,
    )


@animation_router.get("/fingerspelling/catalog", summary="Obtiene el catálogo oficial de las 30 señas de dactilología LSEC (Guía Oficial PDF)")
async def get_fingerspelling_catalog() -> Dict[str, Any]:
    return build_fingerspelling_catalog_payload()


@animation_router.get("/fingerspelling/{text}", summary="Sintetiza la animación VRM 1.0 de dactilología LSEC para una letra, dígrafo o palabra")
async def get_fingerspelling_animation(text: str, fps: int = Query(30, ge=15, le=60)) -> Dict[str, Any]:
    return synthesize_fingerspelling_animation(text, fps=fps)


@animation_router.get("/resolve/{gloss:path}", summary="Resuelve una glosa LSEC en el catálogo v2.7/v2.6 sin lanzar 404")
async def resolve_single_gloss(
    gloss: str,
    version: Optional[str] = Query("2.7", description="Versión preferida: '2.7', '2.6' o '2.5'"),
    include_animation: bool = Query(True, description="Incluir el JSON completo de animation.json"),
    geolect: Optional[str] = Query(None, description="Preferencia geolectal opcional: 'Sierra', 'Costa' o 'Nacional'"),
) -> Dict[str, Any]:
    res = resolve_gloss_to_sign(gloss, version=version or "2.7", include_animation=include_animation, geolect=geolect)
    res.pop("anim_path", None)
    return res


@animation_router.post("/resolve", summary="Resuelve un lote de glosas LSEC contra el catálogo v2.7/v2.6 sin 404")
async def resolve_batch_glosses(payload: Dict[str, Any]) -> Dict[str, Any]:
    return resolve_batch_glosses_payload(payload)


@animation_router.get("/{sign_name}", summary="Obtiene el archivo animation.json de una seña específica")
async def get_sign_animation(sign_name: str, version: Optional[str] = Query(None, description="Versión preferida: '2.7', '2.6' o '2.5'")):
    return resolve_sign_animation_response(sign_name=sign_name, version=version)


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
    return resolve_sign_qa_response(sign_name=sign_name, version=version)


@animation_router.get("/{sign_name}/info", summary="Obtiene la ficha lingüística e info.json de catálogo de una seña")
async def get_sign_info(sign_name: str):
    return resolve_sign_info_response(sign_name=sign_name)


@animation_router.get("/{sign_name}/video", summary="Sirve el video MP4 original Ultra HD de la seña para verificación")
async def get_sign_video(sign_name: str, request: Request):
    """
    Busca y sirve en streaming el video MP4 de la seña original Ultra HD para comparación
    directa con la animación del avatar 3D. Si el archivo en senas_ultra_hd/ no existe o
    presenta corrupción de bitstream, aplica fallback automático hacia Diccionario LSEC/senas/.
    """
    return resolve_sign_video_response(sign_name=sign_name)


@animation_router.get("/{sign_name}/illustration", summary="Sirve la imagen de ilustración oficial de la seña")
@animation_router.get("/{sign_name}/ilustracion", summary="Alias en español para la ilustración de la seña")
async def get_sign_illustration(sign_name: str):
    """
    Busca y sirve la imagen de ilustración oficial (PNG/JPG) de la seña desde el disco local.
    Si no existe localmente, retorna 404 informando si existe URL remota en el catálogo.
    """
    return resolve_sign_illustration_response(sign_name=sign_name)


@animation_router.post("/finalize-export-mp4", summary="Remuxea/codifica video determinista a MP4 H.264 + AAC a 30.0 FPS constantes")
async def finalize_export_mp4(request: Request):
    """
    Recibe un archivo de video renderizado cuadro a cuadro desde el navegador (WebM o MP4)
    y opcionalmente el archivo de video/audio original, y genera un MP4 (H.264 + AAC)
    con tasa de cuadros constante exacta (por defecto 30.0 FPS) y audio original sincronizado.
    """
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

    return encode_deterministic_mp4_response(
        video_bytes=video_bytes,
        audio_bytes=audio_bytes,
        target_fps=target_fps,
    )


# Router alias en /api/animations-direct para compatibilidad directa con el frontend
animation_direct_alias_router = APIRouter(
    prefix="/api/animations-direct",
    tags=["Animaciones Directas 1:1 (Alias)"],
)
animation_direct_alias_router.add_api_route("/non-manual-standard", get_non_manual_standard, methods=["GET"])
animation_direct_alias_router.add_api_route("/stroke-index", get_stroke_index_endpoint, methods=["GET"])
animation_direct_alias_router.add_api_route("/fingerspelling/catalog", get_fingerspelling_catalog, methods=["GET"])
animation_direct_alias_router.add_api_route("/fingerspelling/{text}", get_fingerspelling_animation, methods=["GET"])
animation_direct_alias_router.add_api_route("/resolve/{gloss:path}", resolve_single_gloss, methods=["GET"])
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
