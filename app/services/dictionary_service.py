"""
Servicio del Diccionario Oficial LSEC "Gabriel Román" (CONADIS).

Convierte el catálogo `catalogo_lsec.json` (4.252 señas) en un índice léxico en memoria que:

  1. Expande títulos con género/número y sinónimos:
       "Abuelo(a)"                -> abuelo, abuela
       "A diario, Cotidiano(a)"   -> a diario | cotidiano, cotidiana
       "Capitán (ana), Vocal"     -> capitán, capitana | vocal
       "Encontrar / Hallar"       -> encontrar | hallar
       "CONADIS (Consejo ...)"    -> conadis | consejo nacional de discapacidad
       "Cable (1)", "Mayo (Sierra)" -> cable, mayo (se descartan calificadores)
  2. Resuelve glosas y palabras españolas a una seña oficial (exacta, normalizada, por lema o
     flexionada en plural) y devuelve su ficha (video, ilustración, configuración manual...).
  3. Aplica la cascada OOV sobre una secuencia de `GlossItem`:
       - seña oficial CONADIS            -> `VERIFICADO_CONADIS`
       - dactilología / partículas       -> exentas
       - léxico curado del proyecto      -> `LEXICON_LOCAL`
       - resto de glosas léxicas         -> `NO_VERIFICADO` + revisión nativa (si está activado)
  4. Ofrece búsqueda exacta/prefijo/difusa para los endpoints REST.

ADVERTENCIA: figurar en el diccionario oficial no equivale a validación nativa; las salidas siguen
siendo propuestas computacionales sujetas a revisión por personas sordas usuarias de LSEC.
"""

from __future__ import annotations

import difflib
import hashlib
import html
import json
import logging
import re
import threading
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

from app.core.schemas import (
    AlignmentType,
    DictionarySignMetadata,
    GlossItem,
    GlossType,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_FILENAME = "catalogo_lsec.json"
INDEX_FILENAME = "lsec_dictionary_index.json"
INDEX_SCHEMA_VERSION = 1
MAX_PHRASE_WORDS = 6

STATUS_VERIFIED = "VERIFICADO_CONADIS"
STATUS_UNVERIFIED = "NO_VERIFICADO"
STATUS_GRAMMATICAL = "EXENTO_GRAMATICAL"
STATUS_FINGERSPELLING = "DACTILOLOGIA"
STATUS_LOCAL_LEXICON = "LEXICON_LOCAL"
STATUS_PARAPHRASE = "PARAFRASIS_REVISION"

UNVERIFIED_REVIEW_REASON = (
    "La glosa '{gloss}' no figura en el Diccionario Oficial LSEC (CONADIS); "
    "requiere validación por personas sordas usuarias nativas de LSEC."
)

# Sufijos de género que aparecen entre paréntesis en los títulos: "Abogado(a)", "Capitán (ana)".
_GENDER_SUFFIXES: Set[str] = {"a", "as", "es", "ana", "ora", "iza", "triz"}
_STANDALONE_GENDER_SUFFIXES: Set[str] = {"a", "as", "ana", "ora"}

# Glosas gramaticales/funcionales que no se esperan como entradas léxicas del diccionario.
_GRAMMATICAL_GLOSSES: Set[str] = {
    "VARIOS", "AHORA", "PASADO", "FUTURO", "PRESENTE", "HACIA", "IX", "NO", "NUNCA", "JAMÁS",
    "QUÉ", "QUIÉN", "QUIÉNES", "DÓNDE", "CUÁNDO", "CÓMO", "CUÁL", "CUÁLES", "CUÁNTO", "CUÁNTOS",
    "POR-QUÉ", "PORQUÉ", "TERMINADO", "FIN", "DURATIVO", "REITERATIVO", "COMPLETIVO",
}
_GRAMMATICAL_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"^PRO[123]"),
    re.compile(r"^(IX|POSS|REF)\d?([-_:].*)?$"),
    re.compile(r"^CL[:\-]"),
    re.compile(r"^\d+([.,]\d+)?$"),
    re.compile(r"^\+\+$"),
)
_GRAMMATICAL_ALIGNMENTS: Set[Any] = {
    AlignmentType.GRAMMATICAL,
    AlignmentType.DEICTIC,
    AlignmentType.DISCOURSE_MARKER,
    AlignmentType.IMPLICIT,
    AlignmentType.COREFERENCE,
    AlignmentType.ENTITY_ALIAS,
    "GRAMMATICAL", "DEICTIC", "DISCOURSE_MARKER", "IMPLICIT", "COREFERENCE", "ENTITY_ALIAS",
}
_PRIVATE_ENYE = "\ue000"


# ======================================================================
# Normalización y análisis de títulos
# ======================================================================

def normalize_key(text: str) -> str:
    """Minúsculas, sin tildes (conserva la ñ), sin puntuación ni guiones y con espacios colapsados."""
    if not text:
        return ""
    text = html.unescape(text).lower().replace("ñ", _PRIVATE_ENYE)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace(_PRIVATE_ENYE, "ñ")
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _apply_gender(base: str, suffix: str) -> Optional[str]:
    """Deriva la forma de género de la última palabra de `base` según el sufijo del paréntesis."""
    words = base.split()
    if not words:
        return None
    last = words[-1]
    low = last.lower()
    suffix = suffix.lower()
    new_last: Optional[str] = None
    if suffix == "a":
        if low.endswith("o"):
            new_last = last[:-1] + "a"
        elif low.endswith("e"):
            new_last = last[:-1] + "a"
        elif low.endswith("or") or low.endswith("ón") or low.endswith("án") or low.endswith("l") or low.endswith("z"):
            new_last = last + "a"
        else:
            new_last = last + "a"
    elif suffix == "as":
        if low.endswith("os"):
            new_last = last[:-2] + "as"
        elif low.endswith("es"):
            new_last = last[:-2] + "as"
        else:
            new_last = last + "as"
    elif suffix == "ana":
        new_last = (last[:-2] + "ana") if low.endswith("án") else (last + "ana")
    elif suffix in {"ora", "iza", "triz", "es"}:
        new_last = last + suffix if suffix != "es" else last + "es"
    if not new_last:
        return None
    words[-1] = new_last
    return " ".join(words)


@dataclass
class TitleVariant:
    """Una variante léxica del título con sus formas indexables (género incluido)."""
    text: str
    forms: List[str] = field(default_factory=list)
    qualifiers: List[str] = field(default_factory=list)


def parse_title(palabra: str) -> List[TitleVariant]:
    """
    Descompone el título de una entrada en variantes léxicas.

    Separadores: coma, barra '/', guion largo. Paréntesis: sufijo de género -> formas extra;
    números '(1)' y calificadores '(Costa)' se descartan; en siglas '(Consejo ...)' la expansión
    se agrega como variante adicional.
    """
    raw = html.unescape(palabra or "").replace("\u2013", ",").replace("\u2014", ",")
    parts = re.split(r"\s*[,/]\s*", raw)
    variants: List[TitleVariant] = []
    seen: Set[str] = set()

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.lower() in _STANDALONE_GENDER_SUFFIXES and variants:
            # "Acobardado, a": el fragmento es un sufijo de género de la variante previa
            prev = variants[-1]
            derived = _apply_gender(prev.text, part)
            if derived and derived not in prev.forms:
                prev.forms.append(derived)
            continue
        parens = re.findall(r"\(([^)]*)\)", part)
        base = re.sub(r"\s*\([^)]*\)", "", part).strip()
        base = base.strip(" .;:")
        if not base:
            continue

        forms: List[str] = [base]
        qualifiers: List[str] = []
        extra_variants: List[str] = []

        letters = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", base)
        is_acronym = bool(letters) and letters.isupper() and len(letters) >= 2

        for content in parens:
            c = content.strip()
            if not c or re.fullmatch(r"\d+", c):
                continue
            if c.lower() in _GENDER_SUFFIXES:
                derived = _apply_gender(base, c)
                if derived and derived not in forms:
                    forms.append(derived)
            elif is_acronym and len(c.split()) >= 2:
                extra_variants.append(c)
            else:
                qualifiers.append(c)

        key = normalize_key(base)
        if key and key not in seen:
            seen.add(key)
            variants.append(TitleVariant(text=base, forms=forms, qualifiers=qualifiers))
        for ev in extra_variants:
            ekey = normalize_key(ev)
            if ekey and ekey not in seen:
                seen.add(ekey)
                variants.append(TitleVariant(text=ev, forms=[ev]))

    return variants


def to_gloss_form(text: str) -> str:
    """Forma de glosa canónica: MAYÚSCULAS, sin puntuación y con guiones entre palabras ('a diario' -> 'A-DIARIO')."""
    cleaned = re.sub(r"[¿?¡!.,;:\"“”()]", " ", text)
    return "-".join(cleaned.upper().split())


# ======================================================================
# Estructuras de datos
# ======================================================================

@dataclass
class DictionaryEntry:
    """Seña oficial del diccionario CONADIS con sus variantes léxicas expandidas."""
    slug: str
    title: str
    variants: List[str]
    forms: List[str]
    video_url: Optional[str] = None
    illustration_url: Optional[str] = None
    source_url: Optional[str] = None
    hand_configuration: Optional[str] = None
    alphabetical_group: Optional[str] = None
    categories: List[str] = field(default_factory=list)

    def gloss_alternatives(self, exclude: Optional[str] = None) -> List[str]:
        """Otras variantes del título (sinónimos) en forma de glosa, sin la variante emparejada."""
        skip = normalize_key(exclude) if exclude else None
        out: List[str] = []
        for v in self.variants:
            if skip is not None and normalize_key(v) == skip:
                continue
            g = to_gloss_form(v)
            if g not in out:
                out.append(g)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DictionaryMatch:
    """Resultado de resolver un término contra el diccionario."""
    entry: DictionaryEntry
    matched_variant: str
    match_type: str  # 'exact' | 'normalized' | 'lemma' | 'inflected'

    def to_metadata(self) -> DictionarySignMetadata:
        e = self.entry
        return DictionarySignMetadata(
            verified_in_conadis=True,
            status=STATUS_VERIFIED,
            conadis_slug=e.slug,
            official_sign_title=e.title,
            matched_variant=self.matched_variant,
            match_type=self.match_type,
            hand_configuration=e.hand_configuration,
            alphabetical_group=e.alphabetical_group,
            thematic_categories=list(e.categories),
            video_url=e.video_url,
            illustration_url=e.illustration_url,
            source_url=e.source_url,
            lexical_alternatives=e.gloss_alternatives(exclude=self.matched_variant),
        )


@dataclass
class SearchHit:
    entry: DictionaryEntry
    score: float
    match_type: str  # 'exact' | 'prefix' | 'word' | 'substring' | 'fuzzy'
    matched_form: str


@dataclass
class PhraseMatch:
    """Frase oficial de varias palabras localizada en un texto tokenizado."""
    start_token: int
    end_token: int  # exclusivo
    start_char: int
    end_char: int
    entry: DictionaryEntry
    matched_form: str
    match_basis: str  # 'surface' | 'lemma'



# ======================================================================
# Servicio
# ======================================================================

class LSECDictionaryService:
    """Índice léxico en memoria del Diccionario Oficial LSEC (CONADIS)."""

    def __init__(self, catalog_path: Optional[str | Path] = None, index_path: Optional[str | Path] = None) -> None:
        self._entries: List[DictionaryEntry] = []
        self._by_slug: Dict[str, DictionaryEntry] = {}
        # clave normalizada -> [(prioridad, idx_entrada, forma_original)] ordenada (mejor primero)
        self._index: Dict[str, List[Tuple[Tuple[int, int, int, int], int, str]]] = {}
        self._single_word_keys: Dict[str, List[str]] = {}
        self._suggest_cache: Dict[str, List[str]] = {}
        self._phrase_keys: Set[str] = set()
        self._max_phrase_words: int = 2
        self._lock = threading.Lock()
        self.catalog_path: Optional[Path] = self.resolve_catalog_path(catalog_path)
        self.index_path: Optional[Path] = Path(index_path) if index_path else _PROJECT_ROOT / "data" / INDEX_FILENAME
        self.loaded_from: Optional[str] = None
        self._load()

    # ------------------------------------------------------------------ carga

    @staticmethod
    def resolve_catalog_path(explicit: Optional[str | Path] = None) -> Optional[Path]:
        """Resuelve la ruta del catálogo: argumento -> configuración -> data/ -> ../Diccionario LSEC/."""
        candidates: List[Path] = []
        if explicit:
            candidates.append(Path(explicit))
        else:
            try:
                from app.config import settings
                configured = (settings.lsec_dictionary_catalog_path or "").strip()
            except Exception:  # pragma: no cover
                configured = ""
            if configured:
                p = Path(configured)
                candidates.append(p if p.is_absolute() else (_PROJECT_ROOT / p))
            candidates.append(_PROJECT_ROOT / "data" / CATALOG_FILENAME)
            candidates.append(_PROJECT_ROOT.parent / "Diccionario LSEC" / CATALOG_FILENAME)
        for c in candidates:
            try:
                if c.is_file():
                    return c.resolve()
            except OSError:
                continue
        return None

    @property
    def available(self) -> bool:
        return bool(self._entries)

    def _signature(self) -> Dict[str, Any]:
        st = self.catalog_path.stat()  # type: ignore[union-attr]
        return {"schema": INDEX_SCHEMA_VERSION, "catalog_size": st.st_size, "catalog_mtime_ns": st.st_mtime_ns}

    def _load(self) -> None:
        if self.catalog_path is None:
            logger.warning(
                "Catálogo del Diccionario LSEC no encontrado; el enriquecimiento léxico queda desactivado."
            )
            return
        entries = self._try_load_index()
        if entries is not None:
            self.loaded_from = "index"
        else:
            entries = self._parse_catalog(self.catalog_path)
            self.loaded_from = "catalog"
        self._entries = entries
        self._by_slug = {e.slug: e for e in entries}
        self._build_lookup()
        logger.info(
            "Diccionario LSEC cargado: %d señas, %d claves léxicas (%s).",
            len(self._entries), len(self._index), self.loaded_from,
        )

    def _try_load_index(self) -> Optional[List[DictionaryEntry]]:
        if not self.index_path or not self.index_path.is_file() or self.catalog_path is None:
            return None
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            if payload.get("signature") != self._signature():
                logger.info("Índice del diccionario desactualizado; se reconstruye desde el catálogo.")
                return None
            return [DictionaryEntry(**item) for item in payload["entries"]]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("No se pudo leer el índice del diccionario (%s); se reconstruye.", exc)
            return None

    @staticmethod
    def _parse_catalog(path: Path) -> List[DictionaryEntry]:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        entries: List[DictionaryEntry] = []
        seen_slugs: Set[str] = set()
        for item in raw:
            slug = str(item.get("slug") or "").strip()
            title = html.unescape(str(item.get("palabra") or "")).strip()
            if not slug or not title or slug in seen_slugs:
                continue
            variants = parse_title(title)
            if not variants:
                continue
            seen_slugs.add(slug)
            forms: List[str] = []
            for v in variants:
                for f in v.forms:
                    if f not in forms:
                        forms.append(f)
            cats = [str(c) for c in (item.get("categorias") or [])]
            hand = next((c for c in cats if c.startswith("configuracion_manual")), None)
            alpha = next((c for c in cats if c.startswith("alfa-")), None)
            themes = [c for c in cats if c != hand and c != alpha]
            video_url = item.get("video_url") or (
                f"https://www.youtube.com/watch?v={item['video_id']}" if item.get("video_id") else None
            )
            entries.append(
                DictionaryEntry(
                    slug=slug,
                    title=title,
                    variants=[v.text for v in variants],
                    forms=forms,
                    video_url=video_url,
                    illustration_url=item.get("imagen_url") or None,
                    source_url=item.get("url_origen") or None,
                    hand_configuration=hand,
                    alphabetical_group=alpha,
                    categories=themes,
                )
            )
        return entries

    def _build_lookup(self) -> None:
        index: Dict[str, List[Tuple[Tuple[int, int, int, int], int, str]]] = {}
        for idx, entry in enumerate(self._entries):
            n_variants = len(entry.variants)
            no_video = 0 if entry.video_url else 1
            variant_rank = {normalize_key(v): r for r, v in enumerate(entry.variants)}
            for form in entry.forms:
                key = normalize_key(form)
                if not key:
                    continue
                rank = variant_rank.get(key, 0)
                # Las formas de género comparten el rango de su variante base (aprox. por primera palabra)
                if key not in variant_rank:
                    for vk, r in variant_rank.items():
                        if vk.split()[0][:3] == key.split()[0][:3]:
                            rank = r
                            break
                prio = (0 if n_variants == 1 else 1, rank, n_variants, no_video)
                index.setdefault(key, []).append((prio, idx, form))
        for key in index:
            index[key].sort(key=lambda t: (t[0], t[1]))
        self._index = index
        singles: Dict[str, List[str]] = {}
        for key in index:
            if " " not in key and len(key) >= 3:
                singles.setdefault(key[0], []).append(key)
        self._single_word_keys = singles
        self._phrase_keys = {k for k in index if " " in k}
        self._max_phrase_words = min(
            max((len(k.split()) for k in self._phrase_keys), default=2), MAX_PHRASE_WORDS
        )
        self._suggest_cache.clear()

    # ----------------------------------------------------------- persistencia

    def build_index_file(self, output_path: Optional[str | Path] = None) -> Path:
        """Escribe el índice pre-calculado (entradas expandidas) para un arranque más rápido."""
        if self.catalog_path is None:
            raise FileNotFoundError("No hay catálogo LSEC disponible para indexar.")
        target = Path(output_path) if output_path else self.index_path
        if target is None:
            raise ValueError("Ruta de índice no definida.")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "signature": self._signature(),
            "catalog_sha256": hashlib.sha256(self.catalog_path.read_bytes()).hexdigest(),
            "entries": [e.to_dict() for e in self._entries],
        }
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return target

    # ----------------------------------------------------------- resolución

    @staticmethod
    def _inflection_candidates(key: str) -> Iterator[str]:
        """Claves alternativas por número (plural -> singular). Solo para palabras de 4+ letras."""
        if len(key) < 4:
            return
        if key.endswith("ces"):
            yield key[:-3] + "z"
        if key.endswith("es"):
            yield key[:-2]
        if key.endswith("s"):
            yield key[:-1]

    def _find(self, key: str) -> Optional[Tuple[int, str]]:
        hits = self._index.get(key)
        if not hits:
            return None
        _, idx, form = hits[0]
        return idx, form

    def lookup(self, term: str, *, match_type: str = "exact", allow_inflection: bool = True) -> Optional[DictionaryMatch]:
        """Resuelve un término (palabra o frase) a una seña oficial."""
        if not self.available or not term:
            return None
        key = normalize_key(term)
        if not key:
            return None
        found = self._find(key)
        label = match_type
        if found is None and allow_inflection:
            for cand in self._inflection_candidates(key):
                found = self._find(cand)
                if found is not None:
                    label = "inflected"
                    break
        if found is None:
            return None
        idx, form = found
        return DictionaryMatch(entry=self._entries[idx], matched_variant=form, match_type=label)

    @staticmethod
    def _verb_lemma(word: str) -> Optional[str]:
        try:
            from app.services.semantic_parser import SpanishVerbLexicon
            return SpanishVerbLexicon.get_lemma(word.lower())
        except Exception:  # pragma: no cover - dependencia opcional
            return None

    @staticmethod
    def clean_gloss_text(gloss: str) -> str:
        """Quita marcas de duplicación ('++') y convierte guiones en espacios para la búsqueda."""
        g = re.sub(r"\+{1,2}$", "", (gloss or "").strip())
        return g.replace("-", " ").strip()

    @staticmethod
    def is_fingerspelling_gloss(gloss: str) -> bool:
        parts = [p for p in (gloss or "").split("-") if p]
        return len(parts) >= 2 and all(len(p) == 1 for p in parts)

    @staticmethod
    def is_grammatical_gloss(gloss: str) -> bool:
        g = (gloss or "").strip().upper()
        g = re.sub(r"\+{1,2}$", "", g)
        if g in _GRAMMATICAL_GLOSSES:
            return True
        return any(p.search(g) for p in _GRAMMATICAL_PATTERNS)

    def lookup_gloss(
        self,
        gloss: str,
        normalized_word: Optional[str] = None,
        source_word: Optional[str] = None,
    ) -> Optional[DictionaryMatch]:
        """Resuelve una glosa generada probando glosa, palabra normalizada, fuente y lema verbal."""
        if not self.available:
            return None
        attempts: List[Tuple[str, str]] = []
        text = self.clean_gloss_text(gloss)
        if text:
            attempts.append((text, "exact"))
        for w, label in ((normalized_word, "normalized"), (source_word, "normalized")):
            if w and w.strip():
                attempts.append((w.strip(), label))
        for w in (source_word, normalized_word):
            if w and w.strip() and " " not in w.strip():
                lemma = self._verb_lemma(w.strip())
                if lemma:
                    attempts.append((lemma, "lemma"))
        seen: Set[Tuple[str, str]] = set()
        for term, label in attempts:
            marker = (normalize_key(term), label)
            if marker in seen:
                continue
            seen.add(marker)
            match = self.lookup(term, match_type=label)
            if match is not None:
                return match
        return None

    # ------------------------------------------------------------ consulta

    def find_phrases(
        self,
        tokens: Sequence[Tuple[str, str, int, int]],
        text: str = "",
    ) -> List["PhraseMatch"]:
        """
        Localiza entradas de varias palabras del diccionario en una secuencia de tokens.

        `tokens`: (texto_superficial, lema, inicio_char, fin_char) de los tokens no puntuación,
        en orden. Solo se aceptan tokens contiguos (sin puntuación ni otros caracteres entre ellos).
        Búsqueda voraz de izquierda a derecha con la coincidencia más larga; prueba la forma
        superficial y, si no coincide, la secuencia de lemas (p. ej. "casas grandes" -> "casa grande").
        """
        if not self.available or not self._phrase_keys or len(tokens) < 2:
            return []
        surface = [normalize_key(t[0]) for t in tokens]
        lemmas = [normalize_key(t[1]) or s for t, s in zip(tokens, surface)]
        found: List[PhraseMatch] = []
        n = len(tokens)
        i = 0
        while i < n:
            matched = False
            for length in range(min(self._max_phrase_words, n - i), 1, -1):
                window = range(i, i + length)
                if text and any(
                    text[tokens[k][3]:tokens[k + 1][2]].strip() for k in list(window)[:-1]
                ):
                    continue  # hay puntuación u otro texto entre los tokens
                if any(not surface[k] for k in window):
                    continue
                for label, seq in (("surface", surface), ("lemma", lemmas)):
                    key = " ".join(seq[k] for k in window)
                    if key in self._phrase_keys:
                        hit = self._find(key)
                        if hit is None:
                            continue
                        idx, form = hit
                        found.append(
                            PhraseMatch(
                                start_token=i,
                                end_token=i + length,
                                start_char=tokens[i][2],
                                end_char=tokens[i + length - 1][3],
                                entry=self._entries[idx],
                                matched_form=form,
                                match_basis=label,
                            )
                        )
                        matched = True
                        break
                if matched:
                    i += length
                    break
            if not matched:
                i += 1
        return found

    def get_by_slug(self, slug: str) -> Optional[DictionaryEntry]:
        return self._by_slug.get((slug or "").strip())

    def search(self, query: str, limit: int = 20) -> List[SearchHit]:
        """Búsqueda por exacta -> prefijo -> inicio de palabra -> subcadena -> difusa."""
        qn = normalize_key(query)
        if not self.available or not qn:
            return []
        hits: Dict[int, SearchHit] = {}

        def add(idx: int, score: float, mtype: str, form: str) -> None:
            if idx not in hits or hits[idx].score < score:
                hits[idx] = SearchHit(self._entries[idx], score, mtype, form)

        exact = self._index.get(qn, [])
        for prio, idx, form in exact:
            add(idx, 1.0 - prio[1] * 0.01, "exact", form)
        for key, rows in self._index.items():
            if key == qn:
                continue
            if key.startswith(qn):
                mtype, score = "prefix", 0.90 - min(len(key) - len(qn), 30) * 0.004
            elif any(w.startswith(qn) for w in key.split()):
                mtype, score = "word", 0.75
            elif len(qn) >= 3 and qn in key:
                mtype, score = "substring", 0.60
            else:
                continue
            for prio, idx, form in rows:
                add(idx, score - prio[1] * 0.005, mtype, form)
        if len(hits) < limit and len(qn) >= 3:
            pool = [k for k in self._index if abs(len(k) - len(qn)) <= 3]
            for key in difflib.get_close_matches(qn, pool, n=limit, cutoff=0.78):
                ratio = difflib.SequenceMatcher(None, qn, key).ratio()
                for prio, idx, form in self._index[key]:
                    add(idx, 0.50 * ratio, "fuzzy", form)
        ordered = sorted(hits.values(), key=lambda h: (-h.score, h.entry.title.lower()))
        return ordered[: max(1, limit)]

    def suggest(self, term: str, limit: int = 3) -> List[str]:
        """Sugerencias léxicas cercanas (glosa) para una palabra ausente del diccionario."""
        key = normalize_key(term)
        if not self.available or len(key) < 4 or " " in key:
            return []
        cached = self._suggest_cache.get(key)
        if cached is not None:
            return cached[:limit]
        out: List[str] = []

        def push(cand_key: str) -> None:
            found = self._find(cand_key)
            if found is None:
                return
            g = to_gloss_form(found[1])
            if g not in out:
                out.append(g)

        # Diminutivos / aumentativos: perrito -> perro, casita -> casa
        for suffix in ("itos", "itas", "illos", "illas", "ito", "ita", "illo", "illa", "ote", "ota"):
            if key.endswith(suffix) and len(key) - len(suffix) >= 3:
                stem = key[: -len(suffix)]
                for ending in ("o", "a", "", "e"):
                    if self._find(stem + ending) is not None:
                        push(stem + ending)
                        break
                break
        pool = [k for k in self._single_word_keys.get(key[0], []) if abs(len(k) - len(key)) <= 2]
        for cand in difflib.get_close_matches(key, pool, n=limit * 2, cutoff=0.8):
            push(cand)
        if len(self._suggest_cache) > 2048:
            self._suggest_cache.clear()
        self._suggest_cache[key] = out
        return out[:limit]

    def stats(self) -> Dict[str, Any]:
        entries = self._entries
        total = len(entries)
        return {
            "available": self.available,
            "catalog_path": str(self.catalog_path) if self.catalog_path else None,
            "loaded_from": self.loaded_from,
            "total_signs": total,
            "total_lexical_keys": len(self._index),
            "with_video": sum(1 for e in entries if e.video_url),
            "with_illustration": sum(1 for e in entries if e.illustration_url),
            "multi_variant_entries": sum(1 for e in entries if len(e.variants) > 1),
            "phrases": sum(1 for e in entries if "frases-comunes" in e.categories),
        }

    # ------------------------------------------------------------ enriquecimiento

    def enrich_glosses(
        self,
        glosses: Sequence[GlossItem],
        *,
        known_glosses: Optional[Iterable[str]] = None,
        flag_unverified: Optional[bool] = None,
    ) -> Dict[str, int]:
        """
        Aplica la cascada de resolución sobre `glosses` (modifica los elementos in situ).

        Devuelve un conteo por estado. Si el catálogo no está disponible no hace nada
        (nunca marca glosas como no verificadas sin poder consultar el diccionario).
        """
        counts: Dict[str, int] = {}
        if not self.available:
            return counts
        if flag_unverified is None:
            try:
                from app.config import settings
                flag_unverified = bool(settings.lsec_dictionary_flag_unverified)
            except Exception:  # pragma: no cover
                flag_unverified = True
        known: Set[str] = {k.upper() for k in (known_glosses or ()) if k}

        for g in glosses:
            if g.dictionary_metadata is not None:
                continue
            meta = self._classify(g, known)
            if meta is None:
                meta = self._flag_unverified(g, flag_unverified)
            elif meta.verified_in_conadis:
                if not g.alternatives and meta.lexical_alternatives:
                    g.alternatives = [a for a in meta.lexical_alternatives if a != g.gloss.upper()]
            g.dictionary_metadata = meta
            counts[meta.status] = counts.get(meta.status, 0) + 1
        return counts

    def _classify(self, g: GlossItem, known: Set[str]) -> Optional[DictionarySignMetadata]:
        """Estado de una glosa; `None` indica que es léxica y no figura en CONADIS (OOV)."""
        gloss_up = (g.gloss or "").strip().upper()
        if g.gloss_type == GlossType.FINGERSPELLING or self.is_fingerspelling_gloss(gloss_up):
            return DictionarySignMetadata(status=STATUS_FINGERSPELLING)
        if g.gloss_type in (GlossType.CLASSIFIER, GlossType.EXPRESSION):
            return DictionarySignMetadata(status=STATUS_GRAMMATICAL)
        # Marcas estructurales (PRO1, CL:, números, '++'): nunca se emparejan con entradas léxicas
        if any(p.search(re.sub(r"\+{1,2}$", "", gloss_up)) for p in _GRAMMATICAL_PATTERNS):
            return DictionarySignMetadata(status=STATUS_GRAMMATICAL)

        match = self.lookup_gloss(g.gloss, g.normalized_word, g.source_word)
        if match is not None:
            return match.to_metadata()

        if self.is_grammatical_gloss(gloss_up) or g.alignment_type in _GRAMMATICAL_ALIGNMENTS:
            return DictionarySignMetadata(status=STATUS_GRAMMATICAL)
        if g.lexical_strategy and str(g.lexical_strategy).startswith(("grammatical", "discourse")):
            return DictionarySignMetadata(status=STATUS_GRAMMATICAL)
        if gloss_up in known or re.sub(r"\+{1,2}$", "", gloss_up) in known or g.spatial_ref:
            return DictionarySignMetadata(status=STATUS_LOCAL_LEXICON)
        if g.alignment_type in (AlignmentType.PARAPHRASE, "PARAPHRASE") or g.requires_native_review:
            return DictionarySignMetadata(status=STATUS_PARAPHRASE)
        return None

    def _flag_unverified(self, g: GlossItem, flag: bool) -> DictionarySignMetadata:
        probe = g.normalized_word or g.source_word or self.clean_gloss_text(g.gloss)
        suggestions = self.suggest(probe) if probe else []
        meta = DictionarySignMetadata(status=STATUS_UNVERIFIED, lexical_alternatives=suggestions)
        if flag:
            g.requires_review = True
            g.requires_native_review = True
            reason = UNVERIFIED_REVIEW_REASON.format(gloss=g.gloss)
            if reason not in g.review_reasons:
                g.review_reasons.append(reason)
        return meta


# ======================================================================
# Singleton
# ======================================================================

_service_lock = threading.Lock()
_service_instance: Optional[LSECDictionaryService] = None


def get_dictionary_service(*, reload: bool = False) -> LSECDictionaryService:
    """Instancia compartida (carga perezosa y segura entre hilos)."""
    global _service_instance
    with _service_lock:
        if _service_instance is None or reload:
            _service_instance = LSECDictionaryService()
        return _service_instance


def _main(argv: Optional[Sequence[str]] = None) -> int:  # pragma: no cover - utilidad CLI
    import argparse

    parser = argparse.ArgumentParser(description="Utilidades del Diccionario LSEC (CONADIS)")
    parser.add_argument("--build-index", action="store_true", help="Genera data/lsec_dictionary_index.json")
    parser.add_argument("--catalog", default=None, help="Ruta a catalogo_lsec.json")
    parser.add_argument("--lookup", default=None, help="Consulta un término")
    args = parser.parse_args(argv)
    svc = LSECDictionaryService(catalog_path=args.catalog)
    if args.build_index:
        print(f"Índice escrito en: {svc.build_index_file()}")
    if args.lookup:
        m = svc.lookup(args.lookup)
        print(json.dumps(m.to_metadata().model_dump(), ensure_ascii=False, indent=2) if m else "Sin coincidencia")
    print(json.dumps(svc.stats(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
