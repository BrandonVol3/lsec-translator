"""
Endpoints REST del Diccionario Oficial LSEC "Gabriel Román" (CONADIS).

  GET /api/v1/dictionary/search?q=...&limit=20   Búsqueda y autocompletado (exacta, prefijo, difusa)
  GET /api/v1/dictionary/stats                   Métricas de cobertura del catálogo
  GET /api/v1/dictionary/{slug}                  Ficha completa de una seña

Nota: las fichas provienen del diccionario oficial; no sustituyen la validación por personas
sordas usuarias nativas de LSEC.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.dictionary_service import (
    DictionaryEntry,
    LSECDictionaryService,
    get_dictionary_service,
    to_gloss_form,
)

dictionary_router = APIRouter(prefix="/api/v1/dictionary", tags=["Diccionario Oficial LSEC (CONADIS)"])


class DictionaryEntryResponse(BaseModel):
    slug: str
    title: str
    canonical_gloss: str = Field(description="Glosa canónica derivada de la primera variante del título")
    variants: List[str]
    gloss_variants: List[str]
    forms: List[str]
    hand_configuration: Optional[str] = None
    hand_variant: Optional[str] = None
    hand_variant_key: Optional[str] = None
    hand_variant_label: Optional[str] = None
    alphabetical_group: Optional[str] = None
    geolect: Optional[str] = "Nacional"
    categories: List[str] = Field(default_factory=list)
    video_url: Optional[str] = None
    illustration_url: Optional[str] = None
    source_url: Optional[str] = None


class DictionarySearchHitResponse(BaseModel):
    score: float
    match_type: str
    matched_form: str
    entry: DictionaryEntryResponse


class DictionarySearchResponse(BaseModel):
    query: str
    total: int
    results: List[DictionarySearchHitResponse]


def _service() -> LSECDictionaryService:
    svc = get_dictionary_service()
    if not svc.available:
        raise HTTPException(
            status_code=503,
            detail="El catálogo del Diccionario LSEC no está disponible en el servidor.",
        )
    return svc


def _to_response(entry: DictionaryEntry) -> DictionaryEntryResponse:
    return DictionaryEntryResponse(
        slug=entry.slug,
        title=entry.title,
        canonical_gloss=to_gloss_form(entry.variants[0]),
        variants=list(entry.variants),
        gloss_variants=[to_gloss_form(v) for v in entry.variants],
        forms=list(entry.forms),
        hand_configuration=entry.hand_configuration,
        hand_variant=entry.hand_variant,
        hand_variant_key=entry.hand_variant_key,
        hand_variant_label=entry.hand_variant_label,
        alphabetical_group=entry.alphabetical_group,
        geolect=getattr(entry, "geolect", "Nacional") or "Nacional",
        categories=list(entry.categories),
        video_url=entry.video_url,
        illustration_url=entry.illustration_url,
        source_url=entry.source_url,
    )


@dictionary_router.get("/search", response_model=DictionarySearchResponse)
async def search_dictionary(
    q: str = Query(..., min_length=1, max_length=120, description="Palabra o frase a buscar"),
    hand_config: Optional[str] = Query(None, description="Filtrar por configuración manual (ej. configuracion_manual_3)"),
    hand_variant: Optional[str] = Query(None, description="Filtrar por sub-variante (ej. configuracion_manual_3_v2)"),
    alfa: Optional[str] = Query(None, description="Filtrar por grupo alfabético (ej. alfa-a)"),
    geolect: Optional[str] = Query(None, description="Filtrar o priorizar por geolecto: Nacional, Sierra o Costa"),
    limit: int = Query(20, ge=1, le=100),
) -> DictionarySearchResponse:
    """Busca señas por coincidencia exacta, prefijo, inicio de palabra, subcadena o aproximada."""
    svc = _service()
    hits = svc.search(q, limit=100 if (hand_config or hand_variant or alfa or geolect) else limit)
    if hand_config:
        hits = [h for h in hits if h.entry.hand_configuration == hand_config]
    if hand_variant:
        hits = [h for h in hits if h.entry.hand_variant == hand_variant or h.entry.hand_variant_key == hand_variant]
    if alfa:
        hits = [h for h in hits if h.entry.alphabetical_group == alfa]
    if geolect:
        g_norm = geolect.strip().capitalize()
        if g_norm in ("Sierra", "Costa", "Nacional"):
            exact_geo = [h for h in hits if getattr(h.entry, "geolect", "Nacional") == g_norm]
            if exact_geo:
                hits = exact_geo + [h for h in hits if getattr(h.entry, "geolect", "Nacional") != g_norm]
    hits = hits[:limit]
    return DictionarySearchResponse(
        query=q,
        total=len(hits),
        results=[
            DictionarySearchHitResponse(
                score=round(h.score, 4),
                match_type=h.match_type,
                matched_form=h.matched_form,
                entry=_to_response(h.entry),
            )
            for h in hits
        ],
    )


@dictionary_router.get("/stats")
async def dictionary_stats() -> Dict[str, Any]:
    """Métricas del catálogo cargado (total de señas, con video, con ilustración, etc.)."""
    svc = get_dictionary_service()
    return svc.stats()


@dictionary_router.get("/{slug}", response_model=DictionaryEntryResponse)
async def get_dictionary_entry(slug: str) -> DictionaryEntryResponse:
    """Ficha completa de una seña del diccionario oficial por su `slug`."""
    svc = _service()
    entry = svc.get_by_slug(slug)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Seña '{slug}' no encontrada en el Diccionario LSEC.")
    return _to_response(entry)
