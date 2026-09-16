"""
Servicio de Normalización Contextual de Texto y Detección de Entidades.

Capa de pre-procesamiento que se ejecuta ANTES de la segmentación discursiva.
Responsabilidades:
  1. Corregir errores de transcripción ASR con trazabilidad completa (offsets, tokens, confianza).
  2. Resolver entidades institucionales (UPEC, Tulcán, Cayambe, Carchi, Ecuador).
  3. Detectar y preservar relaciones numéricas (4.500 → valor cardinal 4500, relación MORE_THAN).
  4. Identificar términos contextualmente dudosos ("liberan") para revisión auditiva/humana.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# Registro de Correcciones Trazables
# ============================================================

@dataclass
class CorrectionRecord:
    """Registro exhaustivo de una corrección contextual aplicada."""
    id: str = field(default="")
    asr_text: str = field(default="")
    normalized_text: str = field(default="")
    source_char_start: int = field(default=0)
    source_char_end: int = field(default=0)
    source_token_indexes: List[int] = field(default_factory=list)
    global_source_token_indexes: List[int] = field(default_factory=list)
    source_start_seconds: Optional[float] = None
    source_end_seconds: Optional[float] = None
    alignment_type: str = "NORMALIZED"
    alignment_confidence: float = 0.95
    normalization_id: str = ""
    asr_confidence: float = 0.70
    normalization_confidence: float = 0.95
    correction_confidence: float = 0.95  # Alias retrocompatible
    correction_reason: str = "contextual"
    reason: str = "contextual"
    requires_human_review: bool = False
    alternative_candidates: List[str] = field(default_factory=list)
    position: Optional[int] = None  # Alias retrocompatible

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"corr_{self.source_char_start}_{self.source_char_end}"
        if not self.normalization_id:
            self.normalization_id = self.id
        if self.position is None:
            self.position = self.source_char_start
        if not self.reason and self.correction_reason:
            self.reason = self.correction_reason
        elif not self.correction_reason and self.reason:
            self.correction_reason = self.reason
        if self.normalization_confidence and not self.correction_confidence:
            self.correction_confidence = self.normalization_confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "normalization_id": self.normalization_id or self.id,
            "asr_text": self.asr_text,
            "normalized_text": self.normalized_text,
            "source_char_start": self.source_char_start,
            "source_char_end": self.source_char_end,
            "source_token_indexes": self.source_token_indexes,
            "global_source_token_indexes": self.global_source_token_indexes or self.source_token_indexes,
            "source_start_seconds": self.source_start_seconds,
            "source_end_seconds": self.source_end_seconds,
            "alignment_type": self.alignment_type,
            "alignment_confidence": self.alignment_confidence,
            "asr_confidence": self.asr_confidence,
            "normalization_confidence": self.normalization_confidence,
            "correction_confidence": self.correction_confidence,
            "correction_reason": self.correction_reason,
            "reason": self.reason,
            "requires_human_review": self.requires_human_review,
            "alternative_candidates": self.alternative_candidates,
            "position": self.position,
        }


# ============================================================
# Diccionario y Registro de Entidades Institucionales
# ============================================================

@dataclass
class EntityInfo:
    """Información de una entidad institucional reconocida."""
    full_name: str
    entity_type: str  # "organization", "location", "program"
    preferred_gloss: str
    default_spatial_location: str = "center"
    aliases: List[str] = field(default_factory=list)


_DEFAULT_ENTITY_REGISTRY: Dict[str, EntityInfo] = {
    "UPEC": EntityInfo(
        full_name="Universidad Politécnica Estatal del Carchi",
        entity_type="organization",
        preferred_gloss="U-P-E-C",
        default_spatial_location="center",
        aliases=[
            "Politécnica del Carchi",
            "Politécnica Carchi",
            "Universidad Politécnica Estatal del Carchi",
            "UPEC",
            "la universidad",
            "la institución",
        ],
    ),
    "Tulcán": EntityInfo(
        full_name="Tulcán",
        entity_type="location",
        preferred_gloss="T-U-L-C-Á-N",
        default_spatial_location="left",
        aliases=["Tulkán", "Tulkan", "campus Tulcán"],
    ),
    "Cayambe": EntityInfo(
        full_name="Cayambe",
        entity_type="location",
        preferred_gloss="C-A-Y-A-M-B-E",
        default_spatial_location="right",
        aliases=["Callambe", "Callambé", "campus Cayambe"],
    ),
    "Carchi": EntityInfo(
        full_name="Carchi",
        entity_type="location",
        preferred_gloss="CARCHI",
        default_spatial_location="center",
        aliases=["Provincia del Carchi", "el Carchi"],
    ),
    "Ecuador": EntityInfo(
        full_name="República del Ecuador",
        entity_type="location",
        preferred_gloss="ECUADOR",
        default_spatial_location="center",
        aliases=["país", "el Ecuador"],
    ),
}


# ============================================================
# Correcciones Contextuales Predeterminadas
# ============================================================

_DEFAULT_CONTEXTUAL_CORRECTIONS: List[Dict[str, Any]] = [
    {
        "pattern": r"\bcampos\s+Tulk[aá]n\b",
        "replacement": "campus Tulcán",
        "asr_confidence": 0.588,
        "normalization_confidence": 0.99,
        "reason": "contextual: universidad tiene campus, no campos agrícolas",
        "requires_human_review": False,
        "alternative_candidates": ["campus Tulcán"],
    },
    {
        "pattern": r"\bcampos\s+Tulc[aá]n\b",
        "replacement": "campus Tulcán",
        "asr_confidence": 0.650,
        "normalization_confidence": 0.99,
        "reason": "contextual: universidad tiene campus, no campos",
        "requires_human_review": False,
        "alternative_candidates": ["campus Tulcán"],
    },
    {
        "pattern": r"\bTulk[aá]n\b",
        "replacement": "Tulcán",
        "asr_confidence": 0.700,
        "normalization_confidence": 0.98,
        "reason": "topónimo oficial Carchi",
        "requires_human_review": False,
        "alternative_candidates": ["Tulcán"],
    },
    {
        "pattern": r"\b[Cc]allambe\b",
        "replacement": "Cayambe",
        "asr_confidence": 0.720,
        "normalization_confidence": 0.98,
        "reason": "topónimo oficial Pichincha",
        "requires_human_review": False,
        "alternative_candidates": ["Cayambe"],
    },
    {
        "pattern": r"\bexcelencia\s+cad[eé]nica\b",
        "replacement": "excelencia académica",
        "asr_confidence": 0.550,
        "normalization_confidence": 0.99,
        "reason": "colocación semántica académica",
        "requires_human_review": False,
        "alternative_candidates": ["excelencia académica"],
    },
    {
        "pattern": r"\bcad[eé]nica\b",
        "replacement": "académica",
        "asr_confidence": 0.600,
        "normalization_confidence": 0.97,
        "reason": "corrección fonética ASR",
        "requires_human_review": False,
        "alternative_candidates": ["académica"],
    },
    {
        "pattern": r"\bcadenica\b",
        "replacement": "académica",
        "asr_confidence": 0.600,
        "normalization_confidence": 0.97,
        "reason": "corrección fonética ASR",
        "requires_human_review": False,
        "alternative_candidates": ["académica"],
    },
    {
        "pattern": r"\bya\s+le\s+hicieron\b",
        "replacement": "ya lo hicieron",
        "asr_confidence": 0.850,
        "normalization_confidence": 0.95,
        "reason": "corrección anafórica pronominal",
        "requires_human_review": False,
        "alternative_candidates": ["ya lo hicieron"],
    },
    {
        "pattern": r"\bhas\s+posible\b",
        "replacement": "haz posible",
        "asr_confidence": 0.900,
        "normalization_confidence": 0.99,
        "reason": "imperativo de hacer",
        "requires_human_review": False,
        "alternative_candidates": ["haz posible"],
    },
    {
        "pattern": r"\bqui[eé]n\s+quiere\s+ser\b",
        "replacement": "quién quieres ser",
        "asr_confidence": 0.800,
        "normalization_confidence": 0.93,
        "reason": "concordancia segunda persona",
        "requires_human_review": False,
        "alternative_candidates": ["quién quieres ser"],
    },
    {
        "pattern": r"\bpolit[eé]cnica\s+del\s+carchi\b",
        "replacement": "Politécnica del Carchi",
        "asr_confidence": 0.880,
        "normalization_confidence": 0.95,
        "reason": "normalización institucional",
        "requires_human_review": False,
        "alternative_candidates": ["Politécnica del Carchi"],
    },
    {
        "pattern": r"\bseres\s+humanos\b",
        "replacement": "seres humanos",
        "asr_confidence": 0.920,
        "normalization_confidence": 0.90,
        "reason": "preservación de locución nominal",
        "requires_human_review": False,
        "alternative_candidates": ["seres humanos"],
    },
    {
        "pattern": r"\bcampos\b(?!\s+(?:de|del|magnético|eléctrico|visual))",
        "replacement": "campus",
        "asr_confidence": 0.750,
        "normalization_confidence": 0.85,
        "reason": "contextual: 'campus' universitario",
        "requires_human_review": False,
        "alternative_candidates": ["campus"],
    },
]


# ============================================================
# Representación Numérica y Cuantificadores
# ============================================================

_NUMBER_PATTERN = re.compile(
    r"""
    (?:^|\s)
    (
        \d{1,3}(?:[.,]\d{3})+
        |
        \d+
    )
    (?:\s|$|[.,;:!?])
    """,
    re.VERBOSE,
)


@dataclass
class DetectedNumber:
    """Número detectado con estructura semántica rica."""
    surface_form: str
    numeric_value: int
    number_type: str = "cardinal"  # cardinal, ordinal
    quantifier_relation: Optional[str] = None  # "more_than", "less_than", "exact"
    start_pos: int = 0
    end_pos: int = 0
    raw_text: str = ""  # Alias retrocompatible

    def __post_init__(self) -> None:
        if not self.raw_text:
            self.raw_text = self.surface_form


# ============================================================
# Palabras Contextualmente Dudosas
# ============================================================

@dataclass
class DubiousWordFinding:
    """Hallazgo de palabra con alta confianza acústica pero baja coherencia contextual."""
    source_word: str
    global_source_token_indexes: List[int] = field(default_factory=list)
    source_start_seconds: Optional[float] = None
    source_end_seconds: Optional[float] = None
    acoustic_candidates: List[str] = field(default_factory=list)
    contextual_hypotheses: List[str] = field(default_factory=lambda: ["lideran", "crean", "proyectan"])
    selected_candidate: Optional[str] = None
    asr_confidence: float = 0.989
    contextual_sense_confidence: float = 0.35
    requires_audio_review: bool = True
    review_reason: str = "high_acoustic_confidence_but_low_contextual_coherence"
    alternative_candidates: List[str] = field(default_factory=list)
    char_position: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.alternative_candidates and self.contextual_hypotheses:
            self.alternative_candidates = list(self.contextual_hypotheses)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_word": self.source_word,
            "global_source_token_indexes": self.global_source_token_indexes,
            "source_start_seconds": self.source_start_seconds,
            "source_end_seconds": self.source_end_seconds,
            "acoustic_candidates": self.acoustic_candidates,
            "contextual_hypotheses": self.contextual_hypotheses,
            "selected_candidate": self.selected_candidate,
            "asr_confidence": self.asr_confidence,
            "contextual_sense_confidence": self.contextual_sense_confidence,
            "requires_audio_review": self.requires_audio_review,
            "review_reason": self.review_reason,
            "alternative_candidates": self.contextual_hypotheses,
            "char_position": self.char_position,
        }


# ============================================================
# Servicio de Normalización
# ============================================================

class TextNormalizer:
    """
    Servicio de normalización contextual de texto y detección de entidades.
    """

    def __init__(
        self,
        corrections: Optional[List[Any]] = None,
        entity_registry: Optional[Dict[str, EntityInfo]] = None,
        min_confidence: float = 0.85,
    ) -> None:
        self._entity_registry = entity_registry or dict(_DEFAULT_ENTITY_REGISTRY)
        self._min_confidence = min_confidence
        self._dubious_words: List[Dict[str, Any]] = [
            {
                "word": "liberan",
                "contextual_sense_confidence": 0.35,
                "asr_confidence": 0.989,
                "requires_audio_review": True,
                "review_reason": "high_acoustic_confidence_but_low_contextual_coherence",
                "contextual_hypotheses": ["lideran", "crean", "proyectan"],
                "acoustic_candidates": [],
                "alternative_candidates": ["lideran", "crean", "proyectan"],
            }
        ]

        raw_corrections = corrections or list(_DEFAULT_CONTEXTUAL_CORRECTIONS)
        self._compiled_corrections: List[Dict[str, Any]] = []

        for item in raw_corrections:
            if isinstance(item, tuple):
                # Compatibilidad con tuplas antiguas (pattern, repl, conf, reason)
                pat, repl, conf, reason = item
                try:
                    self._compiled_corrections.append({
                        "pattern_str": pat,
                        "regex": re.compile(pat, re.IGNORECASE),
                        "replacement": repl,
                        "asr_confidence": 0.70,
                        "normalization_confidence": conf,
                        "reason": reason,
                        "requires_human_review": False,
                        "alternative_candidates": [repl],
                    })
                except re.error as exc:
                    logger.warning("Patrón inválido '%s': %s", pat, exc)
            elif isinstance(item, dict):
                pat = item.get("pattern", "")
                repl = item.get("replacement", "")
                try:
                    self._compiled_corrections.append({
                        "pattern_str": pat,
                        "regex": re.compile(pat, re.IGNORECASE),
                        "replacement": repl,
                        "asr_confidence": item.get("asr_confidence", 0.70),
                        "normalization_confidence": item.get("normalization_confidence", item.get("confidence", 0.95)),
                        "reason": item.get("reason", "contextual"),
                        "requires_human_review": item.get("requires_human_review", False),
                        "alternative_candidates": item.get("alternative_candidates", [repl]),
                    })
                except re.error as exc:
                    logger.warning("Patrón inválido '%s': %s", pat, exc)

        logger.info(
            "TextNormalizer inicializado: %d correcciones, %d entidades.",
            len(self._compiled_corrections),
            len(self._entity_registry),
        )

    def normalize(
        self,
        text: str,
        word_timestamps: Optional[List[Any]] = None,
    ) -> Tuple[str, List[CorrectionRecord]]:
        """
        Normaliza el texto aplicando correcciones contextuales con trazabilidad de posición.
        """
        corrections: List[CorrectionRecord] = []
        result = text
        if not word_timestamps:
            from app.core.audio_reference import get_word_timestamps_for_text
            word_timestamps = get_word_timestamps_for_text(text)

        # Calcular spans de caracteres para tokens si hay word_timestamps o texto
        token_spans: List[Tuple[int, int]] = []
        if word_timestamps:
            curr_c = 0
            for wt in word_timestamps:
                w_str = wt.word if hasattr(wt, "word") else wt.get("word", "")
                idx_c = text.lower().find(w_str.lower(), curr_c)
                if idx_c == -1:
                    idx_c = curr_c
                end_c = idx_c + len(w_str)
                token_spans.append((idx_c, end_c))
                curr_c = end_c
        else:
            # Tokenizar por palabras
            for m in re.finditer(r"\b[\wáéíóúñüÁÉÍÓÚÑÜ\-]+\b", text):
                token_spans.append((m.start(), m.end()))

        for entry in self._compiled_corrections:
            conf = entry["normalization_confidence"]
            if conf < self._min_confidence:
                continue

            regex = entry["regex"]
            replacement = entry["replacement"]
            match = regex.search(result)

            while match:
                original_fragment = match.group(0)
                start_pos = match.start()
                end_pos = match.end()

                if original_fragment.lower() != replacement.lower():
                    # Encontrar tokens fuente que se solapan
                    matching_tok_idxs: List[int] = []
                    for t_idx, (ts_start, ts_end) in enumerate(token_spans):
                        if max(start_pos, ts_start) < min(end_pos, ts_end):
                            matching_tok_idxs.append(t_idx)

                    if not matching_tok_idxs and token_spans:
                        # Buscar el más cercano
                        for t_idx, (ts_start, ts_end) in enumerate(token_spans):
                            if ts_start >= start_pos and ts_end <= end_pos + 2:
                                matching_tok_idxs.append(t_idx)

                    src_start_sec: Optional[float] = None
                    src_end_sec: Optional[float] = None
                    if word_timestamps and matching_tok_idxs:
                        valid_t = [i for i in matching_tok_idxs if i < len(word_timestamps)]
                        if valid_t:
                            wt_first = word_timestamps[valid_t[0]]
                            wt_last = word_timestamps[valid_t[-1]]
                            src_start_sec = wt_first.start if hasattr(wt_first, "start") else wt_first.get("start")
                            src_end_sec = wt_last.end if hasattr(wt_last, "end") else wt_last.get("end")

                    align_type = "NORMALIZED_MULTIWORD" if len(matching_tok_idxs) > 1 else "NORMALIZED"

                    rec = CorrectionRecord(
                        id=f"corr_{len(corrections) + 1}",
                        normalization_id=f"corr_{len(corrections) + 1}",
                        asr_text=original_fragment,
                        normalized_text=replacement,
                        source_char_start=start_pos,
                        source_char_end=start_pos + len(original_fragment),
                        source_token_indexes=matching_tok_idxs,
                        global_source_token_indexes=matching_tok_idxs,
                        source_start_seconds=src_start_sec,
                        source_end_seconds=src_end_sec,
                        alignment_type=align_type,
                        alignment_confidence=conf,
                        asr_confidence=entry["asr_confidence"],
                        normalization_confidence=conf,
                        correction_confidence=conf,
                        reason=entry["reason"],
                        correction_reason=entry["reason"],
                        requires_human_review=entry["requires_human_review"],
                        alternative_candidates=entry["alternative_candidates"],
                        position=start_pos,
                    )
                    corrections.append(rec)

                    result = result[:start_pos] + replacement + result[end_pos:]
                    match = regex.search(result, start_pos + len(replacement))
                else:
                    match = regex.search(result, end_pos)

        return result, corrections

    def detect_numbers(self, text: str) -> List[DetectedNumber]:
        """
        Detecta números preservando valores y relaciones cuantificadoras como 'más de'.
        """
        numbers: List[DetectedNumber] = []

        for match in _NUMBER_PATTERN.finditer(text):
            raw = match.group(1)
            clean = raw.replace(".", "").replace(",", "")
            try:
                val = int(clean)
                start_pos = match.start(1)
                end_pos = match.end(1)

                # Verificar si precede "más de" o "menos de"
                prefix = text[max(0, start_pos - 15):start_pos].lower()
                quant_rel = "exact"
                if "más de" in prefix or "mas de" in prefix:
                    quant_rel = "more_than"
                elif "menos de" in prefix:
                    quant_rel = "less_than"

                numbers.append(
                    DetectedNumber(
                        surface_form=raw,
                        numeric_value=val,
                        number_type="cardinal",
                        quantifier_relation=quant_rel,
                        start_pos=start_pos,
                        end_pos=end_pos,
                        raw_text=raw,
                    )
                )
            except ValueError:
                continue

        return numbers

    def check_dubious_words(
        self,
        text: str,
        word_timestamps: Optional[List[Any]] = None,
    ) -> List[DubiousWordFinding]:
        """
        Detecta palabras que requieren revisión contextual o auditiva.
        """
        findings: List[DubiousWordFinding] = []
        if not word_timestamps:
            from app.core.audio_reference import get_word_timestamps_for_text
            word_timestamps = get_word_timestamps_for_text(text)

        token_spans: List[Tuple[int, int]] = []
        if word_timestamps:
            curr_c = 0
            for wt in word_timestamps:
                w_str = wt.word if hasattr(wt, "word") else wt.get("word", "")
                idx_c = text.lower().find(w_str.lower(), curr_c)
                if idx_c == -1:
                    idx_c = curr_c
                end_c = idx_c + len(w_str)
                token_spans.append((idx_c, end_c))
                curr_c = end_c
        else:
            for m in re.finditer(r"\b[\wáéíóúñüÁÉÍÓÚÑÜ\-]+\b", text):
                token_spans.append((m.start(), m.end()))

        for dub in self._dubious_words:
            w = dub["word"]
            pattern = re.compile(r"\b" + re.escape(w) + r"\b", re.IGNORECASE)
            for m in pattern.finditer(text):
                char_start = m.start()
                char_end = m.end()

                matching_tok_idxs: List[int] = []
                for t_idx, (ts_start, ts_end) in enumerate(token_spans):
                    if max(char_start, ts_start) < min(char_end, ts_end):
                        matching_tok_idxs.append(t_idx)

                if not matching_tok_idxs and word_timestamps:
                    w_clean = re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ\-]", "", w.lower())
                    for t_idx, wt in enumerate(word_timestamps):
                        wt_w = wt.word if hasattr(wt, "word") else wt.get("word", "")
                        if re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ\-]", "", wt_w.lower()) == w_clean:
                            matching_tok_idxs.append(t_idx)

                src_start_sec: Optional[float] = None
                src_end_sec: Optional[float] = None
                if word_timestamps and matching_tok_idxs:
                    valid_t = [i for i in matching_tok_idxs if i < len(word_timestamps)]
                    if valid_t:
                        wt_first = word_timestamps[valid_t[0]]
                        wt_last = word_timestamps[valid_t[-1]]
                        src_start_sec = wt_first.start if hasattr(wt_first, "start") else wt_first.get("start")
                        src_end_sec = wt_last.end if hasattr(wt_last, "end") else wt_last.get("end")

                findings.append(
                    DubiousWordFinding(
                        source_word=m.group(0),
                        global_source_token_indexes=matching_tok_idxs,
                        source_start_seconds=src_start_sec,
                        source_end_seconds=src_end_sec,
                        acoustic_candidates=dub.get("acoustic_candidates", []),
                        contextual_hypotheses=dub.get("contextual_hypotheses", ["lideran", "crean", "proyectan"]),
                        selected_candidate=None,
                        asr_confidence=dub.get("asr_confidence", 0.989),
                        contextual_sense_confidence=dub.get("contextual_sense_confidence", 0.35),
                        requires_audio_review=dub.get("requires_audio_review", True),
                        review_reason=dub.get("review_reason", "high_acoustic_confidence_but_low_contextual_coherence"),
                        alternative_candidates=[],
                        char_position=char_start,
                    )
                )
        return findings

    def get_entity_info(self, name: str) -> Optional[EntityInfo]:
        """Busca información de una entidad por nombre o alias."""
        if name in self._entity_registry:
            return self._entity_registry[name]

        name_lower = name.lower().strip()
        for entity_name, info in self._entity_registry.items():
            if entity_name.lower() == name_lower:
                return info
            for alias in info.aliases:
                if alias.lower() == name_lower:
                    return info

        return None

    def get_all_entities(self) -> Dict[str, EntityInfo]:
        """Retorna el registro completo de entidades."""
        return self._entity_registry

    def load_from_lexicon(self, lexicon_data: Dict[str, Any]) -> None:
        """Carga correcciones y entidades desde el lexicón JSON externo."""
        if "contextual_corrections" in lexicon_data:
            for item in lexicon_data["contextual_corrections"]:
                if isinstance(item, dict):
                    pat = item.get("pattern", "")
                    repl = item.get("replacement", "")
                    try:
                        self._compiled_corrections.append({
                            "pattern_str": pat,
                            "regex": re.compile(pat, re.IGNORECASE),
                            "replacement": repl,
                            "asr_confidence": item.get("asr_confidence", 0.70),
                            "normalization_confidence": item.get("normalization_confidence", item.get("confidence", 0.95)),
                            "reason": item.get("reason", "lexicon"),
                            "requires_human_review": item.get("requires_human_review", False),
                            "alternative_candidates": item.get("alternative_candidates", [repl]),
                        })
                    except re.error:
                        continue

        if "entity_registry" in lexicon_data:
            for name, info_dict in lexicon_data["entity_registry"].items():
                if name.startswith("_"):
                    continue
                self._entity_registry[name] = EntityInfo(
                    full_name=info_dict.get("full_name", name),
                    entity_type=info_dict.get("type", "unknown"),
                    preferred_gloss=info_dict.get("preferred_gloss", name.upper()),
                    default_spatial_location=info_dict.get("default_spatial_location", "center"),
                    aliases=info_dict.get("aliases", []),
                )

        if "dubious_words_registry" in lexicon_data:
            self._dubious_words = list(lexicon_data["dubious_words_registry"])

        logger.info(
            "Lexicón cargado en TextNormalizer: %d correcciones, %d entidades.",
            len(self._compiled_corrections),
            len(self._entity_registry),
        )


# ============================================================
# Analizador de Puntuación y Segmentación Limpia
# ============================================================

@dataclass
class PunctuationInfo:
    """Metadatos de puntuación extraídos de una oración o fragmento."""
    has_initial_question: bool = False
    has_final_question: bool = False
    has_initial_exclamation: bool = False
    has_final_exclamation: bool = False
    is_question: bool = False
    is_exclamation: bool = False
    detected_modality: str = "declarative"
    clean_text: str = ""
    raw_text: str = ""


class PunctuationAnalyzer:
    """
    Analizador de puntuación del español (LSEC 2.1.1).
    Separa los signos de interrogación y exclamación para determinar modalidad
    y límites discursivos, garantizando que nunca contaminen los lemas o tokens léxicos.
    """
    PUNCT_CHARS = set("¿?¡!,.;:\"'«»—–-()[]{}")

    @classmethod
    def analyze(cls, text: str) -> PunctuationInfo:
        raw = text.strip()
        has_init_q = "¿" in raw[:3]
        has_fin_q = "?" in raw
        has_init_ex = "¡" in raw[:3]
        has_fin_ex = "!" in raw
        is_q = has_init_q or has_fin_q
        is_ex = has_init_ex or has_fin_ex

        modality = "declarative"
        if is_q:
            raw_l = raw.lower()
            wh_keywords = {
                "qué", "que", "quién", "quien", "quiénes", "quienes",
                "dónde", "donde", "cuándo", "cuando", "cómo", "como",
                "cuál", "cual", "cuáles", "cuales", "cuánto", "cuanto",
                "cuántos", "cuantos", "cuánta", "cuanta", "cuántas", "cuantas"
            }
            # Tokenizar palabras limpias
            words_clean = [cls.strip_punctuation(w).lower() for w in raw.split()]
            if any(w in wh_keywords for w in words_clean) or "por qué" in raw_l or "para qué" in raw_l:
                modality = "interrogative_wh"
            else:
                modality = "interrogative_yn"
        elif is_ex:
            modality = "exclamative"

        clean = cls.clean_sentence(raw)
        return PunctuationInfo(
            has_initial_question=has_init_q,
            has_final_question=has_fin_q,
            has_initial_exclamation=has_init_ex,
            has_final_exclamation=has_fin_ex,
            is_question=is_q,
            is_exclamation=is_ex,
            detected_modality=modality,
            clean_text=clean,
            raw_text=raw,
        )

    @classmethod
    def strip_punctuation(cls, text: str) -> str:
        """Remueve completamente signos de puntuación de un token o lema."""
        if not text:
            return ""
        return "".join(c for c in text if c not in cls.PUNCT_CHARS).strip()

    @classmethod
    def clean_sentence(cls, text: str) -> str:
        """Limpia puntuación envolvente de una oración preservando el contenido interno."""
        res = text.strip()
        # Remover signos iniciales
        while res and res[0] in "¿¡\"'«» ":
            res = res[1:]
        # Remover signos finales
        while res and res[-1] in "?!\"'«»,.;: ":
            res = res[:-1]
        return res.strip()

