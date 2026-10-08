"""
Pruebas de integración del Diccionario Oficial LSEC (CONADIS) en la generación de glosas.

Cubre: análisis de títulos (género, sinónimos, siglas), resolución léxica, cascada OOV,
enriquecimiento de `GlossItem`, validador, aprendizaje activo, índice pre-calculado y endpoints REST.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dictionary_endpoints import dictionary_router
from app.core.schemas import GlossItem, GlossType
from app.services.active_learning_service import ActiveLearningService
from app.services.dictionary_service import (
    LSECDictionaryService,
    STATUS_FINGERSPELLING,
    STATUS_GRAMMATICAL,
    STATUS_LOCAL_LEXICON,
    STATUS_UNVERIFIED,
    STATUS_VERIFIED,
    get_dictionary_service,
    normalize_key,
    parse_title,
)
from app.services.nlp_service import LSECTranslatorService


# ---------------------------------------------------------------------------
# Catálogo sintético (determinista) y catálogo real (si está disponible)
# ---------------------------------------------------------------------------

_SYNTHETIC_CATALOG = [
    {"slug": "abuelo-a", "palabra": "Abuelo(a)", "video_id": "v1",
     "video_url": "https://www.youtube.com/watch?v=v1", "imagen_url": "http://x/abuelo.png",
     "categorias": ["alfa-a", "configuracion_manual_3"], "url_origen": "http://x/?st_kb=abuelo-a"},
    {"slug": "a-diario", "palabra": "A diario, Cotidiano(a)", "video_id": "v2",
     "video_url": "https://www.youtube.com/watch?v=v2", "imagen_url": None,
     "categorias": ["alfa-a", "configuracion_manual_4"], "url_origen": "http://x/?st_kb=a-diario"},
    {"slug": "comer", "palabra": "Comer", "video_id": "v3",
     "video_url": "https://www.youtube.com/watch?v=v3", "imagen_url": "http://x/comer.png",
     "categorias": ["alfa-c", "configuracion_manual_1"], "url_origen": "http://x/?st_kb=comer"},
    {"slug": "perro", "palabra": "Perro", "video_id": "v4",
     "video_url": "https://www.youtube.com/watch?v=v4", "imagen_url": None,
     "categorias": ["alfa-p", "animales", "configuracion_manual_2"], "url_origen": None},
    {"slug": "acobardado-a", "palabra": "Acobardado, a", "video_id": "v5",
     "video_url": None, "imagen_url": None, "categorias": ["alfa-a"], "url_origen": None},
    {"slug": "buenos-dias", "palabra": "Buenos días", "video_id": "v6",
     "video_url": "https://www.youtube.com/watch?v=v6", "imagen_url": None,
     "categorias": ["alfa-b", "frases-comunes"], "url_origen": None},
    {"slug": "casa-grande", "palabra": "Casa grande", "video_id": "v7",
     "video_url": "https://www.youtube.com/watch?v=v7", "imagen_url": None,
     "categorias": ["alfa-c"], "url_origen": None},
    {"slug": "casa-grande-azul", "palabra": "Casa grande azul", "video_id": "v8",
     "video_url": "https://www.youtube.com/watch?v=v8", "imagen_url": None,
     "categorias": ["alfa-c"], "url_origen": None},
]


@pytest.fixture(scope="module")
def synthetic_service(tmp_path_factory) -> LSECDictionaryService:
    path = tmp_path_factory.mktemp("dic") / "catalogo_lsec.json"
    path.write_text(json.dumps(_SYNTHETIC_CATALOG, ensure_ascii=False), encoding="utf-8")
    return LSECDictionaryService(catalog_path=path, index_path=path.parent / "idx.json")


def _gloss(text: str, order: int = 0, **kw) -> GlossItem:
    kw.setdefault("gloss_type", GlossType.SIGN)
    return GlossItem(gloss=text, order=order, **kw)


# ---------------------------------------------------------------------------
# Análisis de títulos y normalización
# ---------------------------------------------------------------------------

class TestTitleParsing:
    def test_gender_parenthesis(self):
        v = parse_title("Abuelo(a)")
        assert [x.text for x in v] == ["Abuelo"]
        assert v[0].forms == ["Abuelo", "Abuela"]

    def test_synonyms_split_by_comma(self):
        v = parse_title("A diario, Cotidiano(a)")
        assert [x.text for x in v] == ["A diario", "Cotidiano"]
        assert v[1].forms == ["Cotidiano", "Cotidiana"]

    def test_slash_and_html_dash(self):
        assert [x.text for x in parse_title("Encontrar / Hallar")] == ["Encontrar", "Hallar"]
        assert [x.text for x in parse_title("Durable &#8211; Duradero")] == ["Durable", "Duradero"]

    def test_accent_gender_suffix(self):
        v = parse_title("Capitán (ana), Vocal")
        assert v[0].forms == ["Capitán", "Capitana"]
        assert v[1].text == "Vocal"

    def test_qualifiers_and_numbers_are_dropped(self):
        assert [x.text for x in parse_title("Cable (1)")] == ["Cable"]
        assert [x.text for x in parse_title("Mayo (Sierra)")] == ["Mayo"]
        assert [x.text for x in parse_title("Con, Con(1)")] == ["Con"]

    def test_acronym_expansion_becomes_variant(self):
        v = parse_title("CONADIS (Consejo Nacional De Discapacidad)")
        assert [x.text for x in v] == ["CONADIS", "Consejo Nacional De Discapacidad"]

    def test_standalone_gender_suffix_is_not_a_word(self):
        v = parse_title("Acobardado, a")
        assert [x.text for x in v] == ["Acobardado"]
        assert "Acobardada" in v[0].forms

    def test_normalize_key_keeps_enye(self):
        assert normalize_key("¡Año!") == "año"
        assert normalize_key("A-DIARIO") == "a diario"
        assert normalize_key("Teléfono") == "telefono"
        assert normalize_key("año") != normalize_key("ano")


# ---------------------------------------------------------------------------
# Resolución léxica
# ---------------------------------------------------------------------------

class TestLookup:
    def test_exact_and_gender_forms(self, synthetic_service):
        assert synthetic_service.lookup("abuela").entry.slug == "abuelo-a"
        assert synthetic_service.lookup("Abuelo").match_type == "exact"

    def test_plural_is_inflected_match(self, synthetic_service):
        m = synthetic_service.lookup("abuelos")
        assert m is not None and m.match_type == "inflected" and m.entry.slug == "abuelo-a"

    def test_synonym_and_phrase(self, synthetic_service):
        assert synthetic_service.lookup("cotidiana").entry.slug == "a-diario"
        assert synthetic_service.lookup("a diario").entry.slug == "a-diario"

    def test_gloss_style_hyphenated_and_duplication(self, synthetic_service):
        m = synthetic_service.lookup_gloss("A-DIARIO")
        assert m is not None and m.entry.slug == "a-diario"
        assert synthetic_service.lookup_gloss("COMER++").entry.slug == "comer"

    def test_verb_lemma_from_conjugated_source(self, synthetic_service):
        m = synthetic_service.lookup_gloss("COMIO", normalized_word="comio", source_word="comió")
        assert m is not None and m.entry.slug == "comer"

    def test_unknown_word_returns_none_and_suggests_diminutive_base(self, synthetic_service):
        assert synthetic_service.lookup("zapatilla") is None
        assert synthetic_service.suggest("perrito") == ["PERRO"]

    def test_metadata_card(self, synthetic_service):
        meta = synthetic_service.lookup("comer").to_metadata()
        assert meta.status == STATUS_VERIFIED and meta.verified_in_conadis
        assert meta.hand_configuration == "configuracion_manual_1"
        assert meta.alphabetical_group == "alfa-c"
        assert meta.video_url.endswith("v3")
        assert meta.illustration_url == "http://x/comer.png"
        alt = synthetic_service.lookup("a diario").to_metadata()
        assert alt.lexical_alternatives == ["COTIDIANO"]


# ---------------------------------------------------------------------------
# Cascada OOV sobre GlossItem
# ---------------------------------------------------------------------------

class TestEnrichGlosses:
    def test_cascade_statuses(self, synthetic_service):
        glosses = [
            _gloss("COMER", 0, normalized_word="comer"),
            _gloss("U-P-E-C", 1, gloss_type=GlossType.FINGERSPELLING),
            _gloss("PRO1", 2),
            _gloss("EXCELENCIA-ACADÉMICA", 3),
            _gloss("PERRITO", 4, normalized_word="perrito"),
        ]
        counts = synthetic_service.enrich_glosses(
            glosses, known_glosses={"EXCELENCIA-ACADÉMICA"}, flag_unverified=True
        )
        statuses = [g.dictionary_metadata.status for g in glosses]
        assert statuses == [
            STATUS_VERIFIED, STATUS_FINGERSPELLING, STATUS_GRAMMATICAL, STATUS_LOCAL_LEXICON, STATUS_UNVERIFIED,
        ]
        assert counts[STATUS_VERIFIED] == 1

    def test_unverified_gloss_is_flagged_for_native_review(self, synthetic_service):
        g = _gloss("PERRITO", 0, normalized_word="perrito")
        synthetic_service.enrich_glosses([g], flag_unverified=True)
        assert g.requires_native_review and g.requires_review
        assert any("CONADIS" in r for r in g.review_reasons)
        assert g.dictionary_metadata.lexical_alternatives == ["PERRO"]
        assert not g.dictionary_metadata.verified_in_conadis

    def test_flagging_can_be_disabled(self, synthetic_service):
        g = _gloss("PERRITO", 0, normalized_word="perrito")
        synthetic_service.enrich_glosses([g], flag_unverified=False)
        assert g.dictionary_metadata.status == STATUS_UNVERIFIED
        assert not g.requires_native_review and g.review_reasons == []

    def test_verified_gloss_gets_synonym_alternatives(self, synthetic_service):
        g = _gloss("A-DIARIO", 0)
        synthetic_service.enrich_glosses([g], flag_unverified=True)
        assert g.alternatives == ["COTIDIANO"]
        assert not g.requires_native_review

    def test_is_idempotent(self, synthetic_service):
        g = _gloss("PERRITO", 0, normalized_word="perrito")
        synthetic_service.enrich_glosses([g], flag_unverified=True)
        reasons = list(g.review_reasons)
        synthetic_service.enrich_glosses([g], flag_unverified=True)
        assert g.review_reasons == reasons

    def test_missing_catalog_is_a_safe_noop(self, tmp_path):
        svc = LSECDictionaryService(catalog_path=tmp_path / "no_existe.json", index_path=tmp_path / "i.json")
        assert not svc.available
        g = _gloss("ALGO", 0)
        assert svc.enrich_glosses([g], flag_unverified=True) == {}
        assert g.dictionary_metadata is None and not g.requires_native_review


# ---------------------------------------------------------------------------
# Índice pre-calculado
# ---------------------------------------------------------------------------

class TestIndexFile:
    def test_roundtrip_and_invalidation(self, tmp_path):
        catalog = tmp_path / "catalogo_lsec.json"
        catalog.write_text(json.dumps(_SYNTHETIC_CATALOG, ensure_ascii=False), encoding="utf-8")
        index = tmp_path / "index.json"
        first = LSECDictionaryService(catalog_path=catalog, index_path=index)
        assert first.loaded_from == "catalog"
        first.build_index_file()
        second = LSECDictionaryService(catalog_path=catalog, index_path=index)
        assert second.loaded_from == "index"
        assert second.lookup("abuela").entry.slug == "abuelo-a"
        # Al modificar el catálogo, el índice queda obsoleto y se reconstruye
        catalog.write_text(json.dumps(_SYNTHETIC_CATALOG[:2], ensure_ascii=False), encoding="utf-8")
        third = LSECDictionaryService(catalog_path=catalog, index_path=index)
        assert third.loaded_from == "catalog"
        assert third.lookup("comer") is None


# ---------------------------------------------------------------------------
# Catálogo real CONADIS (se omite si la carpeta no está presente)
# ---------------------------------------------------------------------------

_real = get_dictionary_service()
requires_real_catalog = pytest.mark.skipif(not _real.available, reason="Catálogo real LSEC no disponible")


@requires_real_catalog
class TestRealCatalog:
    def test_catalog_size_and_coverage(self):
        stats = _real.stats()
        assert stats["total_signs"] >= 4200
        assert stats["with_video"] >= 4200
        assert stats["multi_variant_entries"] > 500

    @pytest.mark.parametrize("term", ["comer", "manzana", "hola", "universidad", "buenos días", "abuela", "cotidiana"])
    def test_common_words_resolve(self, term):
        assert _real.lookup(term) is not None

    def test_gender_pairs_share_one_entry(self):
        assert _real.lookup("abogado").entry.slug == _real.lookup("abogada").entry.slug

    def test_search_orders_exact_first(self):
        hits = _real.search("comer", limit=5)
        assert hits and hits[0].match_type == "exact"

    def test_search_tolerates_typos(self):
        assert any(h.entry.slug == "universidad" for h in _real.search("universidd", limit=10))


# ---------------------------------------------------------------------------
# Pipeline completo de traducción
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def translator() -> LSECTranslatorService:
    return LSECTranslatorService()


@requires_real_catalog
class TestTranslationIntegration:
    @pytest.mark.asyncio
    async def test_verified_glosses_carry_conadis_card(self, translator):
        out = await translator.translate_to_gloss("Mi abuelo come manzana.", mode="detailed")
        by_gloss = {g.gloss: g for g in out.glosses}
        assert by_gloss["MANZANA"].dictionary_metadata.status == STATUS_VERIFIED
        card = by_gloss["MANZANA"].dictionary_metadata
        assert card.conadis_slug == "manzana"
        assert card.video_url and card.hand_configuration
        assert by_gloss["COMER"].dictionary_metadata.verified_in_conadis
        assert by_gloss["PRO1"].dictionary_metadata.status == STATUS_GRAMMATICAL

    @pytest.mark.asyncio
    async def test_unknown_word_is_flagged_and_reported(self, translator):
        out = await translator.translate_to_gloss("El perrito juega con la pelota.", mode="detailed")
        perrito = next(g for g in out.glosses if g.gloss == "PERRITO")
        assert perrito.dictionary_metadata.status == STATUS_UNVERIFIED
        assert perrito.requires_native_review
        assert "PERRO" in perrito.dictionary_metadata.lexical_alternatives
        assert out.execution_status.value == "REVIEW_REQUIRED"
        assert any(w.code == "UNVERIFIED_LEXICAL_SIGN" for w in out.warnings)

    @pytest.mark.asyncio
    async def test_fully_verified_sentence_stays_ready(self, translator):
        out = await translator.translate_to_gloss("¿Tú comes manzana?", mode="detailed")
        assert out.execution_status.value == "READY"
        assert not any(w.code == "UNVERIFIED_LEXICAL_SIGN" for w in out.warnings)

    @pytest.mark.asyncio
    async def test_active_learning_ranks_unverified_sentence_higher(self, translator):
        ok = await translator.translate_to_gloss("¿Tú comes manzana?", mode="detailed")
        oov = await translator.translate_to_gloss("El perrito juega con la pelota.", mode="detailed")
        s_ok, _ = ActiveLearningService.calculate_uncertainty_score(ok)
        s_oov, reasons = ActiveLearningService.calculate_uncertainty_score(oov)
        assert s_oov > s_ok
        assert any("Diccionario Oficial LSEC" in r for r in reasons)


# ---------------------------------------------------------------------------
# Endpoints REST
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client() -> TestClient:
    app = FastAPI()
    app.include_router(dictionary_router)
    return TestClient(app)


@requires_real_catalog
class TestDictionaryEndpoints:
    def test_search_returns_cards(self, client):
        r = client.get("/api/v1/dictionary/search", params={"q": "abuela", "limit": 5})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1
        first = body["results"][0]
        assert first["match_type"] == "exact"
        assert first["entry"]["video_url"]
        assert first["entry"]["canonical_gloss"]

    def test_entry_by_slug(self, client):
        r = client.get("/api/v1/dictionary/manzana")
        assert r.status_code == 200
        assert r.json()["slug"] == "manzana"
        assert r.json()["canonical_gloss"] == "MANZANA"

    def test_unknown_slug_is_404(self, client):
        assert client.get("/api/v1/dictionary/esta-sena-no-existe-xyz").status_code == 404

    def test_stats_route_not_shadowed_by_slug(self, client):
        r = client.get("/api/v1/dictionary/stats")
        assert r.status_code == 200
        assert r.json()["total_signs"] >= 4200

    def test_search_validation(self, client):
        assert client.get("/api/v1/dictionary/search").status_code == 422
        assert client.get("/api/v1/dictionary/search", params={"q": "a", "limit": 500}).status_code == 422


# ---------------------------------------------------------------------------
# Detección de frases oficiales (varias palabras)
# ---------------------------------------------------------------------------

def _tokens(text: str, lemmas: dict | None = None):
    """Tokeniza por espacios/puntuación simple: (superficie, lema, inicio, fin)."""
    import re as _re
    lemmas = lemmas or {}
    out = []
    for m in _re.finditer(r"\w+", text, flags=_re.UNICODE):
        w = m.group(0)
        out.append((w, lemmas.get(w.lower(), w.lower()), m.start(), m.end()))
    return out


class TestPhraseDetection:
    def test_single_phrase_by_surface(self, synthetic_service):
        text = "Buenos días a todos"
        found = synthetic_service.find_phrases(_tokens(text), text)
        assert [(p.entry.slug, p.start_token, p.end_token) for p in found] == [("buenos-dias", 0, 2)]
        assert text[found[0].start_char:found[0].end_char] == "Buenos días"

    def test_longest_phrase_wins(self, synthetic_service):
        text = "una casa grande azul"
        found = synthetic_service.find_phrases(_tokens(text), text)
        assert [p.entry.slug for p in found] == ["casa-grande-azul"]

    def test_match_by_lemma_sequence(self, synthetic_service):
        text = "casas grandes"
        found = synthetic_service.find_phrases(
            _tokens(text, {"casas": "casa", "grandes": "grande"}), text
        )
        assert [(p.entry.slug, p.match_basis) for p in found] == [("casa-grande", "lemma")]

    def test_punctuation_breaks_phrases(self, synthetic_service):
        text = "Buenos, días"
        assert synthetic_service.find_phrases(_tokens(text), text) == []

    def test_no_phrases_without_catalog(self, tmp_path):
        svc = LSECDictionaryService(catalog_path=tmp_path / "x.json", index_path=tmp_path / "i.json")
        assert svc.find_phrases(_tokens("buenos días"), "buenos días") == []


@requires_real_catalog
class TestPhraseIntegration:
    @pytest.mark.asyncio
    async def test_multiword_entry_becomes_single_verified_sign(self, translator):
        out = await translator.translate_to_gloss("Mi abuelo come manzana a diario.", mode="detailed")
        glosses = [g.gloss for g in out.glosses]
        assert "A-DIARIO" in glosses
        assert "DIARIO" not in glosses
        card = next(g for g in out.glosses if g.gloss == "A-DIARIO").dictionary_metadata
        assert card.status == STATUS_VERIFIED and card.conadis_slug == "a-diario"
        assert "COTIDIANO" in card.lexical_alternatives
        assert out.execution_status.value == "READY"

    @pytest.mark.asyncio
    async def test_greeting_and_courtesy_phrases(self, translator):
        out = await translator.translate_to_gloss("Buenos días, por favor ven a mi casa.", mode="detailed")
        glosses = [g.gloss for g in out.glosses]
        assert "BUENOS-DÍAS" in glosses and "POR-FAVOR" in glosses

    @pytest.mark.asyncio
    async def test_phrase_matching_can_be_disabled(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "lsec_dictionary_phrase_matching", False)
        out = await LSECTranslatorService().translate_to_gloss("Mi abuelo come manzana a diario.", mode="detailed")
        assert "A-DIARIO" not in [g.gloss for g in out.glosses]

    @pytest.mark.asyncio
    async def test_local_time_markers_are_not_flagged(self, translator):
        out = await translator.translate_to_gloss("Hoy como manzana.", mode="detailed")
        hoy = next(g for g in out.glosses if g.gloss == "HOY")
        assert hoy.dictionary_metadata.status == STATUS_LOCAL_LEXICON
        assert not hoy.requires_native_review


class TestGlossForm:
    def test_gloss_form_strips_catalog_punctuation(self):
        from app.services.dictionary_service import to_gloss_form
        assert to_gloss_form("¿Por qué?") == "POR-QUÉ"
        assert to_gloss_form("a diario") == "A-DIARIO"
        assert to_gloss_form("¡Buenos días!") == "BUENOS-DÍAS"


@requires_real_catalog
class TestPhraseGuards:
    @pytest.mark.asyncio
    async def test_conjugated_verb_phrases_keep_grammatical_analysis(self, translator):
        out = await translator.translate_to_gloss("mi año tiene dos guaguas", mode="detailed")
        assert "TENER-DOS" not in [g.gloss for g in out.glosses]

    @pytest.mark.asyncio
    async def test_question_phrase_gloss_has_no_punctuation(self, translator):
        out = await translator.translate_to_gloss("¿Por qué estudiamos? Para progresar", mode="detailed")
        glosses = [g.gloss for g in out.glosses]
        assert "POR-QUÉ" in glosses
        assert not any(("¿" in g or "?" in g) for g in glosses)
