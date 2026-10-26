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
            "id": self.id, "normalization_id": self.normalization_id or self.id,
            "asr_text": self.asr_text, "normalized_text": self.normalized_text,
            "original": self.asr_text, "corrected": self.normalized_text, "type": self.reason,
            "source_char_start": self.source_char_start, "source_char_end": self.source_char_end,
            "source_token_indexes": self.source_token_indexes,
            "global_source_token_indexes": self.global_source_token_indexes or self.source_token_indexes,
            "source_start_seconds": self.source_start_seconds, "source_end_seconds": self.source_end_seconds,
            "alignment_type": self.alignment_type, "alignment_confidence": self.alignment_confidence,
            "asr_confidence": self.asr_confidence, "normalization_confidence": self.normalization_confidence,
            "correction_confidence": self.correction_confidence, "correction_reason": self.correction_reason,
            "reason": self.reason, "requires_human_review": self.requires_human_review,
            "alternative_candidates": self.alternative_candidates, "position": self.position,
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
        aliases=["Politécnica del Carchi", "Politécnica Carchi", "Universidad Politécnica Estatal del Carchi", "UPEC", "la universidad", "la institución", "Universidad Politécnica", "Estatal del Carchi"],
    ),
    "Tulcán": EntityInfo(full_name="Tulcán", entity_type="location", preferred_gloss="T-U-L-C-Á-N", default_spatial_location="left", aliases=["Tulkán", "Tulkan", "campus Tulcán"]),
    "Cayambe": EntityInfo(full_name="Cayambe", entity_type="location", preferred_gloss="C-A-Y-A-M-B-E", default_spatial_location="right", aliases=["Callambe", "Callambé", "campus Cayambe"]),
    "Carchi": EntityInfo(full_name="Carchi", entity_type="location", preferred_gloss="CARCHI", default_spatial_location="center", aliases=["Provincia del Carchi", "el Carchi"]),
    "Ecuador": EntityInfo(full_name="República del Ecuador", entity_type="location", preferred_gloss="ECUADOR", default_spatial_location="center", aliases=["país", "el Ecuador"]),
}


# ============================================================
# Correcciones Contextuales Predeterminadas
# ============================================================

_DEFAULT_CONTEXTUAL_CORRECTIONS: List[Dict[str, Any]] = [
    {"pattern": r"\bcampos\s+Tulk[aá]n\b", "replacement": "campus Tulcán", "asr_confidence": 0.588, "normalization_confidence": 0.99, "reason": "contextual: universidad tiene campus, no campos agrícolas", "requires_human_review": False, "alternative_candidates": ["campus Tulcán"]},
    {"pattern": r"\bcampos\s+Tulc[aá]n\b", "replacement": "campus Tulcán", "asr_confidence": 0.650, "normalization_confidence": 0.99, "reason": "contextual: universidad tiene campus, no campos", "requires_human_review": False, "alternative_candidates": ["campus Tulcán"]},
    {"pattern": r"\bTulk[aá]n\b", "replacement": "Tulcán", "asr_confidence": 0.700, "normalization_confidence": 0.98, "reason": "topónimo oficial Carchi", "requires_human_review": False, "alternative_candidates": ["Tulcán"]},
    {"pattern": r"\b[Cc]allambe\b", "replacement": "Cayambe", "asr_confidence": 0.720, "normalization_confidence": 0.98, "reason": "topónimo oficial Pichincha", "requires_human_review": False, "alternative_candidates": ["Cayambe"]},
    {"pattern": r"\bEstandel\s+(?:Karczym|Karchim)\b", "replacement": "Estatal del Carchi", "asr_confidence": 0.50, "normalization_confidence": 0.99, "reason": "corrección fonética ASR: 'Estandel Karczym' -> 'Estatal del Carchi'", "requires_human_review": False, "alternative_candidates": ["Estatal del Carchi"]},
    {"pattern": r"\b20[-–]26[aA]\b", "replacement": "2026-A", "asr_confidence": 0.85, "normalization_confidence": 0.98, "reason": "periodo académico ASR: '20-26a' -> '2026-A'", "requires_human_review": False, "alternative_candidates": ["2026-A"]},
    {"pattern": r"\b(?:8|ocho)\s+y\s+cuarto\b", "replacement": "ocho y quince", "asr_confidence": 0.95, "normalization_confidence": 0.98, "reason": "expresión horaria: '8 y cuarto' -> 'ocho y quince'", "requires_human_review": False, "alternative_candidates": ["ocho y quince"]},
    {"pattern": r"\b(\d{1,2})\s+y\s+cuarto\b", "replacement": r"\1 y quince", "asr_confidence": 0.95, "normalization_confidence": 0.98, "reason": "expresión horaria: 'X y cuarto' -> 'X y quince'", "requires_human_review": False, "alternative_candidates": ["X y quince"]},
    {"pattern": r"\bopcionando\b", "replacement": "optando", "asr_confidence": 0.85, "normalization_confidence": 0.95, "reason": "neologismo administrativo 'opcionando' -> 'optando'", "requires_human_review": False, "alternative_candidates": ["optando"]},
    {"pattern": r"\bopcionan\b", "replacement": "optan", "asr_confidence": 0.85, "normalization_confidence": 0.95, "reason": "neologismo administrativo 'opcionan' -> 'optan'", "requires_human_review": False, "alternative_candidates": ["optan"]},
    {"pattern": r"\bopcionar\b", "replacement": "optar", "asr_confidence": 0.85, "normalization_confidence": 0.95, "reason": "neologismo administrativo 'opcionar' -> 'optar'", "requires_human_review": False, "alternative_candidates": ["optar"]},
    {"pattern": r"\bdesarrolla\s+la\s+etapa\b", "replacement": "realiza la etapa", "asr_confidence": 0.90, "normalization_confidence": 0.95, "reason": "desarrollar etapa administrativa -> realiza la etapa", "requires_human_review": False, "alternative_candidates": ["realiza la etapa"]},
    {"pattern": r"\bexcelencia\s+cad[eé]nica\b", "replacement": "excelencia académica", "asr_confidence": 0.550, "normalization_confidence": 0.99, "reason": "colocación semántica académica", "requires_human_review": False, "alternative_candidates": ["excelencia académica"]},
    {"pattern": r"\bcad[eé]nica\b", "replacement": "académica", "asr_confidence": 0.600, "normalization_confidence": 0.97, "reason": "corrección fonética ASR", "requires_human_review": False, "alternative_candidates": ["académica"]},
    {"pattern": r"\bcadenica\b", "replacement": "académica", "asr_confidence": 0.600, "normalization_confidence": 0.97, "reason": "corrección fonética ASR", "requires_human_review": False, "alternative_candidates": ["académica"]},
    {"pattern": r"\bya\s+le\s+hicieron\b", "replacement": "ya lo hicieron", "asr_confidence": 0.850, "normalization_confidence": 0.95, "reason": "corrección anafórica pronominal", "requires_human_review": False, "alternative_candidates": ["ya lo hicieron"]},
    {"pattern": r"\bhas\s+posible\b", "replacement": "haz posible", "asr_confidence": 0.900, "normalization_confidence": 0.99, "reason": "imperativo de hacer", "requires_human_review": False, "alternative_candidates": ["haz posible"]},
    {"pattern": r"\bqui[eé]n\s+quiere\s+ser\b", "replacement": "quién quieres ser", "asr_confidence": 0.800, "normalization_confidence": 0.93, "reason": "concordancia segunda persona", "requires_human_review": False, "alternative_candidates": ["quién quieres ser"]},
    {"pattern": r"\bpolit[eé]cnica\s+del\s+carchi\b", "replacement": "Politécnica del Carchi", "asr_confidence": 0.880, "normalization_confidence": 0.95, "reason": "normalización institucional", "requires_human_review": False, "alternative_candidates": ["Politécnica del Carchi"]},
    {"pattern": r"\bseres\s+humanos\b", "replacement": "seres humanos", "asr_confidence": 0.920, "normalization_confidence": 0.90, "reason": "preservación de locución nominal", "requires_human_review": False, "alternative_candidates": ["seres humanos"]},
    {"pattern": r"\bcampos\b(?!\s+(?:de|del|magnético|eléctrico|visual))", "replacement": "campus", "asr_confidence": 0.750, "normalization_confidence": 0.85, "reason": "contextual: 'campus' universitario", "requires_human_review": False, "alternative_candidates": ["campus"]},
]


# ============================================================
# Modismos y quechuismos del habla ecuatoriana (LSEC 2.2)
# ============================================================

# Gerundios irregulares o de la 3.ª conjugación (-ir) que no siguen -iendo → -er.
_GERUND_TO_INFINITIVE_IRREGULAR: Dict[str, str] = {
    "trayendo": "traer", "yendo": "ir", "leyendo": "leer", "creyendo": "creer",
    "oyendo": "oír", "cayendo": "caer", "diciendo": "decir", "pidiendo": "pedir",
    "sirviendo": "servir", "durmiendo": "dormir", "viniendo": "venir",
    "escribiendo": "escribir", "abriendo": "abrir", "subiendo": "subir",
    "viviendo": "vivir", "recibiendo": "recibir", "partiendo": "partir",
    "repitiendo": "repetir", "siguiendo": "seguir", "sintiendo": "sentir",
    "prefiriendo": "preferir", "consiguiendo": "conseguir", "eligiendo": "elegir",
    "construyendo": "construir", "incluyendo": "incluir", "poniendo": "poner",
    "teniendo": "tener", "haciendo": "hacer", "pudiendo": "poder",
    "viendo": "ver", "avisando": "avisar",
}

# 'dame viendo' en el habla ecuatoriana no pide "ver": pide revisar.
_DAME_GERUND_SEMANTIC_OVERRIDES: Dict[str, str] = {
    "viendo": "ver",
    "avisando": "avisar",
}


def gerund_to_infinitive(gerund: str) -> Optional[str]:
    """Convierte un gerundio español a infinitivo mediante reglas morfológicas."""
    g = gerund.lower()
    if g in _GERUND_TO_INFINITIVE_IRREGULAR:
        return _GERUND_TO_INFINITIVE_IRREGULAR[g]
    if g.endswith("ando") and len(g) > 5:
        return g[:-4] + "ar"
    if g.endswith("iendo") and len(g) > 6:
        return g[:-5] + "er"
    return None


_DAME_GERUND_RE = (
    r"\b(?:d[aá]me|d[eé]me|d[aá]nos|d[eé]nos|dar[aá]s|dar[aá]|dar[aá]n|dar[eé]|daremos)\s+"
    r"([a-záéíóúñ]+(?:ando|iendo|yendo))\b"
)


def _dame_gerund_replacer(match: "re.Match[str]") -> str:
    """'dame pasando la sal' → 'por favor pasar la sal' (cortesía indirecta ecuatoriana)."""
    gerund = match.group(1).lower()
    infinitive = _DAME_GERUND_SEMANTIC_OVERRIDES.get(gerund) or gerund_to_infinitive(gerund)
    if infinitive is None:
        return match.group(0)  # sin base morfológica segura: no se altera
    tail = match.string[match.end():].lower()
    head = match.string[:match.start()].lower()
    already_polite = "por favor" in tail or "por favor" in head
    return infinitive if already_polite else f"por favor {infinitive}"


def _clock_time_replacer(match: "re.Match[str]") -> str:
    """'14:15' → 'hora 14 15' para que el planificador componga HORA + numerales."""
    return f"hora {match.group(1)} {match.group(2)}"


_DIGIT_SPOKEN_MAP: Dict[str, str] = {
    "0": "cero", "1": "uno", "2": "dos", "3": "tres", "4": "cuatro",
    "5": "cinco", "6": "seis", "7": "siete", "8": "ocho", "9": "nueve",
}


def _phone_number_replacer(match: "re.Match[str]") -> str:
    """Convierte secuencias de números telefónicos (ej. 099 28 72 993) en dígitos hablados."""
    digits = [c for c in match.group(0) if c.isdigit()]
    return " ".join(_DIGIT_SPOKEN_MAP[d] for d in digits if d in _DIGIT_SPOKEN_MAP)


def _upec_email_replacer(match: "re.Match[str]") -> str:
    """Separa un correo UPEC en unidades que el planificador puede glosar."""
    user = match.group(1)
    return f"{user} arroba UPEC punto edu punto ec"


_SLANG_NOUN_MAP: Dict[str, str] = {
    "ñaño": "hermano", "ñaña": "hermana", "ñaños": "hermanos", "ñañas": "hermanas",
    "guagua": "niño", "guaguas": "niños",
    "pana": "amigo", "panas": "amigos",
}


def _slang_noun_replacer(match: "re.Match[str]") -> str:
    word = match.group(0)
    mapped = _SLANG_NOUN_MAP.get(word.lower())
    if mapped is None:
        return word
    return mapped.capitalize() if word[:1].isupper() else mapped


def _de_una_replacer(match: "re.Match[str]") -> str:
    """'de una' → 'ahora' solo como locución adverbial (inicio de cláusula o ante verbo)."""
    s = match.string
    before = s[:match.start()].rstrip()
    at_clause_start = (not before) or before[-1] in ",;.¿¡?!"
    nxt = re.match(r"\s*([\wáéíóúñ]+)", s[match.end():])
    nxt_word = nxt.group(1).lower() if nxt else ""
    try:
        from app.services.semantic_parser import SpanishVerbLexicon
        next_is_verb = nxt_word in SpanishVerbLexicon.KNOWN_VERB_FORMS
    except Exception:  # pragma: no cover
        next_is_verb = False
    # Excluye 'de una vez/manera/forma...' y usos nominales.
    if nxt_word in {"vez", "manera", "forma", "parte", "casa", "persona", "ciudad", "sola", "solo"}:
        return match.group(0)
    if at_clause_start or next_is_verb:
        return "ahora"
    return match.group(0)


_DEFAULT_CONTEXTUAL_CORRECTIONS.extend([
    {"pattern": r"\b([a-zA-Z0-9._%+-]+)(?:arrobaupec\.edu\.(?:es|ec)|@upec\.edu\.(?:es|ec))\b", "replacement": "", "replacer": _upec_email_replacer, "asr_confidence": 0.92, "normalization_confidence": 0.98, "reason": "correo institucional ASR: dominio UPEC normalizado a .edu.ec", "requires_human_review": False, "alternative_candidates": ["usuario arroba UPEC punto edu punto ec"]},
    {"pattern": r"(?:(?:\+593|\b593)[\s.-]?0?|\b0)\d(?:[\s.-]?\d){7,9}\b", "replacement": "", "replacer": _phone_number_replacer, "asr_confidence": 0.95, "normalization_confidence": 0.98, "reason": "número telefónico -> dígitos hablados", "requires_human_review": False, "alternative_candidates": ["cero nueve ..."]},
    {"pattern": _DAME_GERUND_RE, "replacement": "", "replacer": _dame_gerund_replacer, "asr_confidence": 0.90, "normalization_confidence": 0.95, "reason": "cortesía indirecta ecuatoriana: 'dame + gerundio' → 'por favor + infinitivo'", "requires_human_review": False, "alternative_candidates": ["por favor + infinitivo"]},
    {"pattern": r"\b(?:ñaños?|ñañas?|guaguas?)\b", "replacement": "", "replacer": _slang_noun_replacer, "asr_confidence": 0.90, "normalization_confidence": 0.95, "reason": "quechuismo/coloquialismo ecuatoriano → léxico general LSEC", "requires_human_review": False, "alternative_candidates": ["hermano", "niño"]},
    # 'pana' (amigo) no debe confundirse con la tela: 'pantalón de pana'.
    {"pattern": r"(?<!de )(?<!la )(?<!una )\bpanas?\b", "replacement": "", "replacer": _slang_noun_replacer, "asr_confidence": 0.90, "normalization_confidence": 0.90, "reason": "coloquialismo ecuatoriano 'pana' → 'amigo'", "requires_human_review": False, "alternative_candidates": ["amigo"]},
    {"pattern": r"\bachachay\b", "replacement": "frío", "asr_confidence": 0.90, "normalization_confidence": 0.95, "reason": "interjección quechua 'achachay' (¡qué frío!)", "requires_human_review": False, "alternative_candidates": ["frío"]},
    {"pattern": r"\barrarray\b", "replacement": "calor", "asr_confidence": 0.90, "normalization_confidence": 0.95, "reason": "interjección quechua 'arrarray' (¡qué calor!)", "requires_human_review": False, "alternative_candidates": ["calor"]},
    {"pattern": r"\bde\s+una\b", "replacement": "", "replacer": _de_una_replacer, "asr_confidence": 0.85, "normalization_confidence": 0.90, "reason": "locución adverbial ecuatoriana 'de una' → 'ahora'", "requires_human_review": False, "alternative_candidates": ["ahora", "de inmediato"]},
    {"pattern": r"\bya\s+(?:regreso|vuelvo)\s+no\s?m[aá]s\b", "replacement": "vuelvo pronto", "asr_confidence": 0.90, "normalization_confidence": 0.95, "reason": "locución ecuatoriana 'ya regreso nomás' → 'vuelvo pronto'", "requires_human_review": False, "alternative_candidates": ["vuelvo pronto"]},
])

# ============================================================
# Modismos, cuantificación y expresiones numéricas (LSEC 2.8)
# ============================================================

_DEFAULT_CONTEXTUAL_CORRECTIONS.extend([
    # 'de ley' es certeza, no el sustantivo jurídico.
    {"pattern": r"\bde\s+ley\b", "replacement": "seguro", "asr_confidence": 0.90, "normalization_confidence": 0.95, "reason": "locución ecuatoriana 'de ley' → certeza ('seguro')", "requires_human_review": False, "alternative_candidates": ["seguro", "cierto"]},
    # 'Atatai' expresa asco; nunca debe ir a dactilología.
    {"pattern": r"\bat[aá]tai\b", "replacement": "asco", "asr_confidence": 0.88, "normalization_confidence": 0.93, "reason": "interjección ecuatoriana 'atatai' → asco", "requires_human_review": False, "alternative_candidates": ["asco"]},
    # 'Ayayay' acompaña una queja de dolor.
    {"pattern": r"\bay(?:ay)+\b", "replacement": "dolor", "asr_confidence": 0.88, "normalization_confidence": 0.92, "reason": "interjección ecuatoriana 'ayayay' → dolor", "requires_human_review": False, "alternative_candidates": ["dolor"]},
    # Diminutivos adverbiales andinos: base léxica, sin sufijo.
    {"pattern": r"\bahorita\b", "replacement": "ahora", "asr_confidence": 0.92, "normalization_confidence": 0.96, "reason": "diminutivo adverbial andino 'ahorita' → ahora", "requires_human_review": False, "alternative_candidates": ["ahora"]},
    {"pattern": r"\btempranito\b", "replacement": "temprano", "asr_confidence": 0.92, "normalization_confidence": 0.96, "reason": "diminutivo adverbial andino 'tempranito' → temprano", "requires_human_review": False, "alternative_candidates": ["temprano"]},
    {"pattern": r"\brapidito\b", "replacement": "rápido", "asr_confidence": 0.92, "normalization_confidence": 0.96, "reason": "diminutivo adverbial andino 'rapidito' → rápido", "requires_human_review": False, "alternative_candidates": ["rápido"]},
    # El porcentaje se realiza con la seña existente PORCENTAJE.
    {"pattern": r"\bpor\s+ciento\b", "replacement": "porcentaje", "asr_confidence": 0.95, "normalization_confidence": 0.98, "reason": "porcentaje léxico: 'por ciento' → 'porcentaje'", "requires_human_review": False, "alternative_candidates": ["porcentaje"]},
    # 14:15 → hora 14 15; el planificador compone HORA + numerales.
    {"pattern": r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", "replacement": "", "replacer": _clock_time_replacer, "asr_confidence": 0.95, "normalization_confidence": 0.98, "reason": "horario 24h: se antepone HORA y se separan sus componentes", "requires_human_review": False, "alternative_candidates": ["hora + hora + minutos"]},
])


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
        from app.services.spoken_text_cleaner import SpokenTextCleaner
        self._spoken_cleaner: Optional[SpokenTextCleaner] = SpokenTextCleaner()
        self._dubious_words: List[Dict[str, Any]] = [{
            "word": "liberan", "contextual_sense_confidence": 0.35, "asr_confidence": 0.989,
            "requires_audio_review": True, "review_reason": "high_acoustic_confidence_but_low_contextual_coherence",
            "contextual_hypotheses": ["lideran", "crean", "proyectan"], "acoustic_candidates": [],
            "alternative_candidates": ["lideran", "crean", "proyectan"],
        }]

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
                        "replacer": item.get("replacer"),
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

        # ── Etapa 0: depuración del habla espontánea (LSEC 2.2) ──────────────
        def _ts_seconds(idxs: List[int]) -> Tuple[Optional[float], Optional[float]]:
            valid = [i for i in idxs if word_timestamps and i < len(word_timestamps)]
            if not valid:
                return None, None
            first, last = word_timestamps[valid[0]], word_timestamps[valid[-1]]
            s = first.start if hasattr(first, "start") else first.get("start")
            e = last.end if hasattr(last, "end") else last.get("end")
            return s, e

        char_map: List[int] = list(range(len(text)))
        if self._spoken_cleaner is not None:
            clean_res = self._spoken_cleaner.clean(text, token_spans)
            if clean_res.removed:
                for seg in clean_res.removed:
                    s_sec, e_sec = _ts_seconds(seg.token_indexes)
                    corrections.append(CorrectionRecord(
                        id=f"corr_{len(corrections) + 1}", normalization_id=f"corr_{len(corrections) + 1}",
                        asr_text=seg.text, normalized_text="", source_char_start=seg.start, source_char_end=seg.end,
                        source_token_indexes=list(seg.token_indexes), global_source_token_indexes=list(seg.token_indexes),
                        source_start_seconds=s_sec, source_end_seconds=e_sec, alignment_type="NORMALIZED",
                        alignment_confidence=0.97, asr_confidence=0.90, normalization_confidence=0.97, correction_confidence=0.97,
                        reason=f"disfluencia oral eliminada: {seg.reason}", correction_reason=f"disfluencia oral eliminada: {seg.reason}",
                        requires_human_review=False, alternative_candidates=[], position=seg.start,
                    ))
                result = clean_res.text
                char_map = list(clean_res.char_map)

        def _interp_map(orig_s: int, orig_e: int, length: int) -> List[int]:
            """Mapa de offsets para un tramo de reemplazo de ``length`` caracteres."""
            if length <= 0:
                return []
            if length == 1 or orig_e - 1 <= orig_s:
                return [orig_s] * length
            span = orig_e - 1 - orig_s
            return [orig_s + round(i * span / (length - 1)) for i in range(length)]

        for entry in self._compiled_corrections:
            conf = entry["normalization_confidence"]
            if conf < self._min_confidence:
                continue

            regex = entry["regex"]
            replacer = entry.get("replacer")
            match = regex.search(result)

            while match:
                original_fragment = match.group(0)
                start_pos, end_pos = match.start(), match.end()
                replacement = replacer(match) if replacer else match.expand(entry["replacement"])

                if original_fragment.lower() != replacement.lower():
                    # Offsets reales en el texto ORIGINAL (tras depuración y reemplazos previos)
                    if char_map and start_pos < len(char_map):
                        orig_s = char_map[start_pos]
                        last_i = min(max(end_pos - 1, start_pos), len(char_map) - 1)
                        orig_e = char_map[last_i] + 1
                    else:
                        orig_s, orig_e = start_pos, end_pos

                    # Encontrar tokens fuente que se solapan
                    matching_tok_idxs: List[int] = [t_idx for t_idx, (ts_start, ts_end) in enumerate(token_spans) if max(orig_s, ts_start) < min(orig_e, ts_end)]
                    if not matching_tok_idxs and token_spans:
                        # Buscar el más cercano
                        matching_tok_idxs = [t_idx for t_idx, (ts_start, ts_end) in enumerate(token_spans) if ts_start >= orig_s and ts_end <= orig_e + 2]

                    src_start_sec, src_end_sec = _ts_seconds(matching_tok_idxs)
                    align_type = "NORMALIZED_MULTIWORD" if len(matching_tok_idxs) > 1 else "NORMALIZED"

                    rec = CorrectionRecord(
                        id=f"corr_{len(corrections) + 1}", normalization_id=f"corr_{len(corrections) + 1}",
                        asr_text=original_fragment, normalized_text=replacement,
                        source_char_start=orig_s, source_char_end=orig_s + len(original_fragment),
                        source_token_indexes=matching_tok_idxs, global_source_token_indexes=matching_tok_idxs,
                        source_start_seconds=src_start_sec, source_end_seconds=src_end_sec,
                        alignment_type=align_type, alignment_confidence=conf,
                        asr_confidence=entry["asr_confidence"], normalization_confidence=conf, correction_confidence=conf,
                        reason=entry["reason"], correction_reason=entry["reason"],
                        requires_human_review=entry["requires_human_review"], alternative_candidates=entry["alternative_candidates"],
                        position=orig_s,
                    )
                    corrections.append(rec)

                    result = result[:start_pos] + replacement + result[end_pos:]
                    char_map = char_map[:start_pos] + _interp_map(orig_s, orig_e, len(replacement)) + char_map[end_pos:]
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
                start_pos, end_pos = match.start(1), match.end(1)
                # Verificar si precede "más de" o "menos de"
                prefix = text[max(0, start_pos - 15):start_pos].lower()
                quant_rel = "more_than" if ("más de" in prefix or "mas de" in prefix) else ("less_than" if "menos de" in prefix else "exact")
                numbers.append(DetectedNumber(surface_form=raw, numeric_value=val, number_type="cardinal", quantifier_relation=quant_rel, start_pos=start_pos, end_pos=end_pos, raw_text=raw))
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
                char_start, char_end = m.start(), m.end()
                matching_tok_idxs: List[int] = [t_idx for t_idx, (ts_start, ts_end) in enumerate(token_spans) if max(char_start, ts_start) < min(char_end, ts_end)]

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
                        wt_first, wt_last = word_timestamps[valid_t[0]], word_timestamps[valid_t[-1]]
                        src_start_sec = wt_first.start if hasattr(wt_first, "start") else wt_first.get("start")
                        src_end_sec = wt_last.end if hasattr(wt_last, "end") else wt_last.get("end")

                findings.append(DubiousWordFinding(
                    source_word=m.group(0), global_source_token_indexes=matching_tok_idxs,
                    source_start_seconds=src_start_sec, source_end_seconds=src_end_sec,
                    acoustic_candidates=dub.get("acoustic_candidates", []),
                    contextual_hypotheses=dub.get("contextual_hypotheses", ["lideran", "crean", "proyectan"]),
                    selected_candidate=None, asr_confidence=dub.get("asr_confidence", 0.989),
                    contextual_sense_confidence=dub.get("contextual_sense_confidence", 0.35),
                    requires_audio_review=dub.get("requires_audio_review", True),
                    review_reason=dub.get("review_reason", "high_acoustic_confidence_but_low_contextual_coherence"),
                    alternative_candidates=[], char_position=char_start,
                ))
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
    PUNCT_CHARS = set("¿?¡!,.;:\"'«»—–-()[]{}/\\")

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


_NEGATION_RE = re.compile(
    r"(?<![\wáéíóúñü])(no|nadie|nunca|jamás|tampoco|ni)(?![\wáéíóúñü])",
    re.IGNORECASE,
)


def contains_negation(text: str) -> bool:
    return bool(_NEGATION_RE.search(text or ""))
