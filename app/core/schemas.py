"""
Esquemas Pydantic v2 para el sistema LSEC Translator 2.1.1.

Define los contratos de datos para todo el pipeline lingüístico y discursivo:
Audio/Texto → Transcripción → Normalización Trazable → Alineación de Tokens
→ Segmentación en Proposiciones → Representación Semántica Intermedia
→ Detección y Reparación de Duplicados → Planificación Discursiva
→ Glosas LSEC → Operaciones Espaciales → Componentes No Manuales
→ Enlace de Metadatos de Ejecución → Temporización → Validación Multidimensional
→ Estado de Ejecución (READY / REVIEW_REQUIRED / BLOCKED) → Avatar Payload / API.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field


# ============================================================
# Enumeraciones Básicas y Tipos
# ============================================================

class GlossType(str, Enum):
    """Tipo de elemento en la secuencia de glosas LSEC."""
    SIGN = "SEÑA"                    # Seña directa del vocabulario LSEC
    FINGERSPELLING = "DACTILOLOGÍA"  # Deletreo manual letra por letra
    CLASSIFIER = "CLASIFICADOR"      # Clasificador de forma/tamaño
    EXPRESSION = "EXPRESIÓN"         # Marcador no-manual puro


class FacialExpression(str, Enum):
    """Marcadores no-manuales (expresiones faciales) de la LSEC."""
    NEUTRAL = "neutral"
    QUESTION_WH = "pregunta_qu"        # Cejas fruncidas (qué, quién, dónde)
    QUESTION_YESNO = "pregunta_sn"     # Cejas levantadas (sí/no)
    RHETORICAL = "pregunta_retorica"   # Cejas levantadas: pregunta retórica seguida de su respuesta (FENASEC)
    NEGATION = "negación"              # Cabeza negando + ceño fruncido
    AFFIRMATION = "afirmación"         # Cabeza asintiendo
    EMPHASIS = "énfasis"               # Ojos abiertos, movimiento exagerado
    CONDITIONAL = "condicional"        # Cejas levantadas + pausa
    SURPRISE = "sorpresa"              # Cejas levantadas + boca abierta
    CONTRAST = "contraste"             # Cambio de postura corporal para contraste
    IMPERATIVE = "imperativo"          # Expresión de orden/motivación
    REFLECTIVE = "reflexiva"           # Interrogativa indirecta/reflexión (menor intensidad)
    NARRATIVE = "narrativa"            # Introducción de relato / cita
    SUPERLATIVE = "superlativo"        # Énfasis de grado máximo


class WSMessageType(str, Enum):
    """Tipos de mensajes WebSocket."""
    AUDIO_CHUNK = "audio_chunk"
    TEXT_INPUT = "text_input"
    CONTROL = "control"
    TRANSCRIPTION = "transcription"
    GLOSS_RESULT = "gloss_result"
    AVATAR_PAYLOAD = "avatar_payload"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


# ============================================================
# Modelos de Entrada y Transcripción
# ============================================================

class WordTimestamp(BaseModel):
    """Marca de tiempo individual para una palabra de la transcripción de audio."""
    word: str = Field(description="Palabra o token reconocido")
    start: float = Field(ge=0.0, description="Segundo de inicio")
    end: float = Field(ge=0.0, description="Segundo de fin")
    probability: float = Field(default=0.95, ge=0.0, le=1.0, description="Probabilidad o confianza acústica")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Alias para retrocompatibilidad")

    def model_post_init(self, __context: Any) -> None:
        if self.confidence is not None and (self.probability == 0.95 or self.probability == 0.0):
            self.probability = self.confidence
        elif self.confidence is None:
            self.confidence = self.probability


class TranscriptionInput(BaseModel):
    """Entrada opcional de transcripción con marcas de tiempo para alineación multimodal."""
    text: str = Field(description="Texto transcrito")
    word_timestamps: List[WordTimestamp] = Field(default_factory=list)
    asr_confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    audio_duration_seconds: Optional[float] = Field(default=None, ge=0.0)


# ============================================================
# Enumeraciones de la Capa Semántica y Discursiva
# ============================================================

class ParticipantType(str, Enum):
    """Categoría ontológica del participante semántico."""
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    LOCATION = "LOCATION"
    ABSTRACT_CONCEPT = "ABSTRACT_CONCEPT"
    EVENT = "EVENT"
    GROUP = "GROUP"
    UNKNOWN = "UNKNOWN"


class SemanticRole(str, Enum):
    """Rol semántico del participante en la proposición."""
    AGENT = "AGENT"
    PATIENT = "PATIENT"
    EXPERIENCER = "EXPERIENCER"
    BENEFICIARY = "BENEFICIARY"
    RECIPIENT = "RECIPIENT"
    ADDRESSEE = "ADDRESSEE"
    THEME = "THEME"
    LOCATION = "LOCATION"
    SOURCE = "SOURCE"
    GOAL = "GOAL"
    ATTRIBUTE = "ATTRIBUTE"
    QUANTIFIER = "QUANTIFIER"
    DEGREE = "DEGREE"
    INSTRUMENT = "INSTRUMENT"
    CAUSE = "CAUSE"
    TOPIC = "TOPIC"
    TEMPORAL_MODIFIER = "TEMPORAL_MODIFIER"
    INSTITUTIONAL_CONTEXT = "INSTITUTIONAL_CONTEXT"
    GROUP = "GROUP"
    QUANTITATIVE_COMPARISON = "QUANTITATIVE_COMPARISON"


class PredicateType(str, Enum):
    """Tipo de predicado semántico."""
    ACTION = "ACTION"
    STATE = "STATE"
    EQUATIVE = "EQUATIVE"
    ATTRIBUTIVE = "ATTRIBUTIVE"
    COMPARATIVE_STATE = "COMPARATIVE_STATE"
    EXISTENTIAL = "EXISTENTIAL"
    MODAL = "MODAL"
    CAUSATIVE = "CAUSATIVE"
    IMPERATIVE = "IMPERATIVE"


class FragmentType(str, Enum):
    """Tipo de fragmento o constituyente proposicional."""
    COMPLETE_PROPOSITION = "COMPLETE_PROPOSITION"
    EMBEDDED_PROPOSITION = "EMBEDDED_PROPOSITION"
    RELATIVE_PROPOSITION = "RELATIVE_PROPOSITION"
    CONTEXT_FRAGMENT = "CONTEXT_FRAGMENT"
    ENUMERATION_FRAGMENT = "ENUMERATION_FRAGMENT"
    DISCOURSE_OPERATOR = "DISCOURSE_OPERATOR"
    PREPARATION_START = "PREPARATION_START"
    EDUCATIONAL_RESOURCES = "EDUCATIONAL_RESOURCES"
    TECHNOLOGY_DEVELOPMENT = "TECHNOLOGY_DEVELOPMENT"
    INVALID_FRAGMENT = "INVALID_FRAGMENT"


class ConceptClassification(str, Enum):
    """Clasificación de conceptos para validación de cobertura semántica."""
    MANDATORY = "mandatory"
    OPTIONAL = "optional"
    INFERRABLE = "inferrable"
    OMITTABLE = "omittable"
    DISCOURSE_OPERATOR = "discourse_operator"
    PENDING_REVIEW = "pending_review"


class InferredConceptOrigin(str, Enum):
    """Origen justificado de un concepto inferido en el plan."""
    SOURCE = "SOURCE"
    COREFERENCE = "COREFERENCE"
    ACTIVE_TOPIC = "ACTIVE_TOPIC"
    DISCOURSE_INFERENCE = "DISCOURSE_INFERENCE"
    PARAPHRASE = "PARAPHRASE"


class RelationType(str, Enum):
    """Tipo de relación semántica o discursiva."""
    CAUSE = "CAUSE"
    PURPOSE = "PURPOSE"
    CONTRAST = "CONTRAST"
    ELABORATION = "ELABORATION"
    ENUMERATION = "ENUMERATION"
    CONDITION = "CONDITION"
    TEMPORAL = "TEMPORAL"
    COMPARISON = "COMPARISON"
    SUPERLATIVE = "SUPERLATIVE"
    ATTRIBUTION = "ATTRIBUTION"
    COREFERENCE = "COREFERENCE"
    RESULT = "RESULT"
    ADDITIVE = "ADDITIVE"
    ADDITIVE_EXPANSION = "ADDITIVE_EXPANSION"
    NOT_ONLY_BUT_ALSO = "NOT_ONLY_BUT_ALSO"
    BEYOND_NOT_ONLY = "BEYOND_NOT_ONLY"
    ORGANIZATION_OFFERS_PROGRAM = "ORGANIZATION_OFFERS_PROGRAM"
    PROGRAM_AVAILABLE_AT_LOCATION = "PROGRAM_AVAILABLE_AT_LOCATION"
    HAS_LOCATION = "HAS_LOCATION"
    NOT_ONLY = "NOT_ONLY"
    INDIRECT_QUESTION = "INDIRECT_QUESTION"
    ACHIEVEMENT = "ACHIEVEMENT"
    HUMAN_PERSON = "HUMAN_PERSON"
    INCLUDES = "INCLUDES"
    MEANS = "MEANS"
    RELATIVE_MODIFIER = "RELATIVE_MODIFIER"
    ACCOMPANIED_DEVELOPMENT = "ACCOMPANIED_DEVELOPMENT"
    PREPARATION_START_TIME = "PREPARATION_START_TIME"
    QUANTITATIVE_COMPARISON = "QUANTITATIVE_COMPARISON"


class AlignmentType(str, Enum):
    """Tipo de correspondencia y alineación temporal entre fuente y glosa."""
    DIRECT = "DIRECT"
    MULTIWORD = "MULTIWORD"
    NORMALIZED = "NORMALIZED"
    NORMALIZED_MULTIWORD = "NORMALIZED_MULTIWORD"
    PARAPHRASE = "PARAPHRASE"
    COREFERENCE = "COREFERENCE"
    INFERRED = "INFERRED"
    DEICTIC = "DEICTIC"
    IMPLICIT = "IMPLICIT"
    GRAMMATICAL = "GRAMMATICAL"
    DISCOURSE_MARKER = "DISCOURSE_MARKER"
    ENTITY_ALIAS = "ENTITY_ALIAS"
    DISCONTINUOUS = "DISCONTINUOUS"


class StrategyType(str, Enum):
    """Estrategia de composición y orden lineal LSEC."""
    TOPIC_COMMENT = "TOPIC_COMMENT"
    TIME_TOPIC_COMMENT = "TIME_TOPIC_COMMENT"
    LOCATION_TOPIC_COMMENT = "LOCATION_TOPIC_COMMENT"
    AGENT_PATIENT_PREDICATE = "AGENT_PATIENT_PREDICATE"
    EQUATIVE_PAUSE = "EQUATIVE_PAUSE"
    CONTRAST_PAIR = "CONTRAST_PAIR"
    NEGATED_ONLY = "NEGATED_ONLY"
    ENUMERATION_SPATIAL = "ENUMERATION_SPATIAL"
    IMPERATIVE_DIRECT = "IMPERATIVE_DIRECT"
    EMBEDDED_WH_REFLECTIVE = "EMBEDDED_WH_REFLECTIVE"
    SLOGAN_COMPACT = "SLOGAN_COMPACT"
    SEMANTIC_PARAPHRASE = "SEMANTIC_PARAPHRASE"


class SpatialOperationType(str, Enum):
    """Operación sobre el espacio signante."""
    ESTABLISH = "ESTABLISH"
    REFERENCE = "REFERENCE"
    RELOCATE = "RELOCATE"
    ENUMERATE = "ENUMERATE"
    DISTRIBUTE = "DISTRIBUTE"
    COMPARE = "COMPARE"
    CLEAR = "CLEAR"


class SpatialLocation(str, Enum):
    """Ubicación en el espacio signante."""
    LEFT = "left"
    RIGHT = "right"
    CENTER = "center"
    UP = "up"
    DOWN = "down"
    LEFT_FORWARD = "left_forward"
    RIGHT_FORWARD = "right_forward"


class ReviewStatus(str, Enum):
    """Estado de validación lingüística de una propuesta computacional."""
    VERIFIED = "VERIFIED"
    AUTO_VERIFIED = "AUTO_VERIFIED"
    COMPUTATIONALLY_VALIDATED = "COMPUTATIONALLY_VALIDATED"
    READY = "READY"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    CANDIDATE = "CANDIDATE"
    REQUIRES_CONTEXT_REVIEW = "REQUIRES_CONTEXT_REVIEW"
    REQUIRES_AUDIO_REVIEW = "REQUIRES_AUDIO_REVIEW"
    REQUIRES_NATIVE_REVIEW = "REQUIRES_NATIVE_REVIEW"
    UNSUPPORTED = "UNSUPPORTED"
    PENDING = "PENDING"
    PENDING_NATIVE_REVIEW = "PENDING_NATIVE_REVIEW"
    PENDING_AUDIO_REVIEW = "PENDING_AUDIO_REVIEW"
    PENDING_NATIVE_AND_AUDIO_REVIEW = "PENDING_NATIVE_AND_AUDIO_REVIEW"


class ExecutionStatus(str, Enum):
    """Estado de ejecución y disponibilidad para el avatar / renderizador 3D."""
    READY = "READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


class TranslationMode(str, Enum):
    """Modo de respuesta de la API."""
    LEGACY = "legacy"        # Contrato anterior 100% compatible
    DETAILED = "detailed"    # Incluye proposiciones, planes, operaciones espaciales y validación
    DEBUG = "debug"          # Incluye reglas aplicadas, candidatos descartados y trazabilidad exhaustiva


class ValidationSeverity(str, Enum):
    """Severidad de un hallazgo del validador automático."""
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


# ============================================================
# Módulo 1 — Entrada de Audio y Transcripción
# ============================================================


class TranscriptionResult(BaseModel):
    """Resultado de la transcripción de voz a texto."""
    text: str = Field(description="Texto transcrito completo")
    language: str = Field(default="es", description="Idioma detectado")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confianza promedio")
    duration_seconds: float = Field(default=0.0, description="Duración del audio procesado")
    word_timestamps: List[WordTimestamp] = Field(default_factory=list)
    device_used: Optional[str] = Field(default=None, description="Dispositivo de cómputo utilizado (cuda o cpu)")
    device_warning: Optional[str] = Field(default=None, description="Aviso del sistema si se ejecutó en CPU sin GPU")

    @property
    def asr_confidence(self) -> float:
        return self.confidence




# ============================================================
# Módulo 2 — Capa Semántica Intermedia
# ============================================================

class SemanticParticipant(BaseModel):
    """Participante semántico en una proposición."""
    id: str = Field(default_factory=lambda: f"part_{uuid4().hex[:6]}")
    lemma: str = Field(description="Lema o forma base en español")
    normalized_text: str = Field(description="Texto superficial normalizado")
    participant_type: ParticipantType = Field(default=ParticipantType.UNKNOWN)
    semantic_role: SemanticRole = Field(default=SemanticRole.THEME)
    entity_id: Optional[str] = Field(default=None, description="ID en registro de entidades si aplica")
    coreference_id: Optional[str] = Field(default=None, description="ID del antecedente si es anafórico")
    grammatical_person: Optional[str] = Field(default=None, description="'1', '2', '3', '1-PL', '2-PL', '3-PL'")
    number: Optional[str] = Field(default=None, description="'singular', 'plural', 'collective'")
    is_implicit: bool = Field(default=False, description="Verdadero si es argumento elidido/sujeto tácito")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)


class SemanticPredicate(BaseModel):
    """Predicado semántico de una proposición."""
    lemma: str = Field(description="Lema verbal o concepto predicativo")
    predicate_type: PredicateType = Field(default=PredicateType.ACTION)
    tense_or_aspect: Optional[str] = Field(default=None, description="'past', 'present', 'future', 'perfect', 'habitual'")
    polarity: str = Field(default="positive", description="'positive' o 'negative'")
    modality: Optional[str] = Field(default=None, description="'declarative', 'imperative', 'reflective', 'conditional'")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)


class InferredConcept(BaseModel):
    """Concepto inferido o recuperado con justificación y origen trazable."""
    concept: str
    origin: InferredConceptOrigin = Field(default=InferredConceptOrigin.DISCOURSE_INFERENCE)
    origin_proposition_id: Optional[str] = None
    inference_rule_id: Optional[str] = None
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)


class SourceConceptItem(BaseModel):
    """Concepto obligatorio u opcional derivado de la proposición fuente."""
    id: str = Field(description="ID único del concepto (ej: 'c_p1_1')")
    lemma: str = Field(description="Lema o concepto canónico")
    concept_type: str = Field(default="LEXICAL", description="'LEXICAL' | 'PREDICATE' | 'PARTICIPANT' | 'OPERATOR' | 'MWE'")
    required: bool = Field(default=True, description="¿Es concepto obligatorio para cobertura?")
    global_source_token_indexes: List[int] = Field(default_factory=list)
    source_start_seconds: Optional[float] = None
    source_end_seconds: Optional[float] = None
    proposition_id: str
    support_type: str = Field(default="SOURCE", description="'SOURCE' | 'INFERRED' | 'COREFERENCE' | 'DISCOURSE' | 'PARAPHRASE' | 'ENTITY_ALIAS'")
    inference_rule_id: Optional[str] = None
    antecedent_concept_id: Optional[str] = None
    confidence: float = Field(default=0.90, ge=0.0, le=1.0)


class RealizedConceptItem(BaseModel):
    """Concepto realizado en la secuencia de glosas con justificación de respaldo."""
    concept: str = Field(description="Glosa o concepto realizado")
    support_type: str = Field(default="SOURCE", description="'SOURCE' | 'COREFERENCE' | 'INFERRED' | 'PARAPHRASE' | 'DISCOURSE' | 'ENTITY_ALIAS'")
    source_concept_ids: List[str] = Field(default_factory=list)
    inference_rule_id: Optional[str] = None
    coreference_target_id: Optional[str] = None
    antecedent_proposition_id: Optional[str] = None
    discourse_relation: Optional[str] = None
    entity_id: Optional[str] = None
    source_range: Optional[List[int]] = None
    is_supported: bool = Field(default=True)
    origin_proposition_id: Optional[str] = None
    confidence: float = Field(default=0.90, ge=0.0, le=1.0)


class ConceptCoverageInfo(BaseModel):
    """Información de cobertura semántica de un plan respecto a su proposición fuente."""
    source_concepts: List[str] = Field(default_factory=list)
    realized_concepts: List[str] = Field(default_factory=list)
    omitted_concepts: List[str] = Field(default_factory=list)
    inferred_concepts: List[str] = Field(default_factory=list)
    extraction_coverage_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    realization_coverage_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    realization_precision: float = Field(default=1.0, ge=0.0, le=1.0)
    coverage_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    coverage_status: str = Field(default="COMPLETE", description="'COMPLETE' | 'PARTIAL' | 'CONTENT_LEAK' | 'FAILED'")


class SemanticRelation(BaseModel):
    """Relación entre proposiciones o entre entidades."""
    source_id: str
    target_id: str
    relation_type: RelationType
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    notes: Optional[str] = None


class SemanticProposition(BaseModel):
    """
    Proposición semántica unitaria (LSEC 2.1.1).

    Capa explícita entre la unidad discursiva y las glosas LSEC.
    Representa una aserción, relación predicativa o evento completo.
    """
    id: str = Field(description="Identificador único (ej: 'p1', 'p2')")
    source_text: str = Field(description="Texto original del fragmento")
    normalized_text: str = Field(description="Texto normalizado del fragmento")
    fragment_type: FragmentType = Field(default=FragmentType.COMPLETE_PROPOSITION)
    source_token_indexes: List[int] = Field(default_factory=list)
    local_token_indexes: List[int] = Field(default_factory=list)
    global_source_token_indexes: List[int] = Field(default_factory=list)
    source_char_start: Optional[int] = Field(default=None)
    source_char_end: Optional[int] = Field(default=None)
    source_start_seconds: Optional[float] = Field(default=None)
    source_end_seconds: Optional[float] = Field(default=None)
    alignment_type: Optional[AlignmentType | str] = Field(default=None)
    alignment_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    normalization_id: Optional[str] = Field(default=None)
    source_ranges: List[Dict[str, Any]] = Field(default_factory=list)
    predicate: Optional[SemanticPredicate] = Field(default=None)
    participants: List[SemanticParticipant] = Field(default_factory=list)
    semantic_relations: List[SemanticRelation] = Field(default_factory=list)
    head_concept: Optional[str | Dict[str, Any]] = Field(default=None)
    enumerated_participants: List[str] = Field(default_factory=list)
    context_info: Dict[str, Any] = Field(default_factory=dict, description="Contexto institucional o locativo adjunto")
    operators: List[Dict[str, Any]] = Field(default_factory=list, description="Operadores discursivos y semánticos")
    discourse_relation: Optional[str] = Field(default=None)
    rhetorical_function: Optional[str] = Field(default=None)
    polarity: str = Field(default="positive", description="'positive' | 'negative'")
    modality: str = Field(default="declarative")
    focus: Optional[str] = Field(default=None)
    topic: Optional[str] = Field(default=None)
    contrast_pair_id: Optional[str] = Field(default=None)
    parent_proposition_id: Optional[str] = Field(default=None)
    parent_participant_id: Optional[str] = Field(default=None)
    dependency_type: Optional[str] = Field(default=None)
    embedded_propositions: List[Dict[str, Any]] = Field(default_factory=list)
    temporal_modifiers: List[Dict[str, Any]] = Field(default_factory=list)
    is_embedded: bool = Field(default=False)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    requires_review: bool = Field(default=False)
    review_reasons: List[str] = Field(default_factory=list)


class SemanticFrame(BaseModel):
    """
    Representación semántica intermedia para la traducción a LSEC.

    Abstracción entre la ``SemanticProposition`` (análisis lingüístico del español)
    y la secuencia de ``GlossItem`` (producción LSEC). El motor de reglas
    (``RuleEngine``) evalúa sus condiciones contra los campos de este frame.

    Invariante: cada ``SemanticFrame`` se construye a partir de exactamente
    una ``SemanticProposition`` y produce exactamente una secuencia de glosas.
    """
    frame_id: str = Field(description="ID único del frame (ej: 'frame_p1')")
    proposition_id: str = Field(description="ID de la proposición fuente")
    source_text: str = Field(default="")

    # ── Tipo de oración ────────────────────────────────────────
    sentence_type: str = Field(
        default="declarative",
        description="'declarative', 'interrogative_wh', 'interrogative_yn', 'imperative', 'exclamative', 'reflective'",
    )
    is_embedded: bool = Field(default=False, description="Indica si la cláusula está subordinada o embebida")
    has_subordinate: bool = Field(default=False, description="Indica si la proposición contiene cláusula subordinada o relativa")

    # ── Predicado ──────────────────────────────────────────────
    predicate_lemma: Optional[str] = Field(default=None)
    predicate_type: Optional[str] = Field(default=None, description="PredicateType value")
    has_patient_or_theme: bool = Field(default=False)
    explicit_subject: bool = Field(default=True)
    is_copulative: bool = Field(default=False)
    copula_type: Optional[str] = Field(
        default=None,
        description="'attributive', 'identificational', 'locativa', 'existencial', 'temporal'",
    )
    has_adjectival_predicate: bool = Field(default=False)
    has_attributive_adjective: bool = Field(default=False)

    # ── Polaridad, modalidad ───────────────────────────────────
    polarity: str = Field(default="positive", description="'positive' | 'negative'")
    modality: str = Field(default="declarative")
    negation_scope: Optional[str] = Field(default=None, description="'clausal', 'constituent', 'existential'")

    # ── Temporalidad y aspecto ─────────────────────────────────
    has_temporal_reference: bool = Field(default=False)
    has_past_reference: bool = Field(default=False)
    temporal_marker: Optional[str] = Field(default=None, description="Marcador temporal (ej: 'hoy', 'ayer', 'futuro')")
    grammatical_aspect: Optional[str] = Field(default=None, description="'progressive', 'perfect', 'prospective', 'habitual'")
    tense: Optional[str] = Field(default=None, description="'past', 'present', 'future'")

    # ── Participantes semánticos ───────────────────────────────
    agent: Optional[str] = Field(default=None, description="Lema del agente")
    agent_person: Optional[str] = Field(default=None, description="Persona gramatical: '1', '2', '3', etc.")
    prodrop_type: Optional[str] = Field(
        default=None,
        description="'pro1', 'pro2', 'anaphoric', 'locus', 'generic', 'impersonal', 'ambiguous'",
    )
    patient: Optional[str] = Field(default=None, description="Lema del paciente/tema")
    beneficiary: Optional[str] = Field(default=None, description="Lema del beneficiario")
    instrument: Optional[str] = Field(default=None, description="Lema del instrumento")
    location: Optional[str] = Field(default=None, description="Lema del lugar")
    participants: List[Dict[str, Any]] = Field(default_factory=list)

    # ── Estructura informativa ─────────────────────────────────
    topic: Optional[str] = Field(default=None)
    focus: Optional[str] = Field(default=None)
    discourse_relation: Optional[str] = Field(default=None)
    rhetorical_function: Optional[str] = Field(default=None)

    # ── Correferencia y espacialidad ───────────────────────────
    coreference_chains: List[Dict[str, Any]] = Field(default_factory=list)
    spatial_assignments: List[Dict[str, Any]] = Field(default_factory=list)
    functional_transfers: List[Dict[str, Any]] = Field(default_factory=list)
    classifier_candidates: List[Dict[str, Any]] = Field(default_factory=list)

    # ── Reglas aplicadas (trazabilidad) ────────────────────────
    applied_rule_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    requires_review: bool = Field(default=False)
    review_reasons: List[str] = Field(default_factory=list)

    def to_eval_dict(self) -> Dict[str, Any]:
        """Convierte el frame a un diccionario para evaluación de reglas."""
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_proposition(cls, prop: "SemanticProposition") -> "SemanticFrame":
        """Construye un SemanticFrame a partir de una SemanticProposition existente."""
        has_patient = any(
            p.semantic_role in (SemanticRole.PATIENT, SemanticRole.THEME)
            for p in prop.participants
        )
        explicit_subj = any(
            p.semantic_role == SemanticRole.AGENT and not p.is_implicit
            for p in prop.participants
        ) if prop.participants else not bool(prop.predicate)

        agent_p = next(
            (p for p in prop.participants if p.semantic_role == SemanticRole.AGENT), None
        )
        patient_p = next(
            (p for p in prop.participants if p.semantic_role in (SemanticRole.PATIENT, SemanticRole.THEME)), None
        )
        beneficiary_p = next(
            (p for p in prop.participants if p.semantic_role == SemanticRole.BENEFICIARY), None
        )
        instrument_p = next(
            (p for p in prop.participants if p.semantic_role == SemanticRole.INSTRUMENT), None
        )
        location_p = next(
            (p for p in prop.participants if p.semantic_role == SemanticRole.LOCATION), None
        )

        # Determinar tipo de oración
        s_type = prop.modality if prop.modality != "declarative" else "declarative"
        text_lower = prop.source_text.lower()
        if "?" in prop.source_text or "¿" in prop.source_text:
            wh_words = {"quién", "quiénes", "qué", "dónde", "cuándo", "cómo", "cuál", "cuáles", "cuánto", "cuánta", "cuántos", "cuántas"}
            if any(w in text_lower for w in wh_words):
                s_type = "interrogative_wh"
            else:
                s_type = "interrogative_yn"
        elif prop.modality == "imperative":
            s_type = "imperative"

        # Detectar aspecto gramatical y tiempo desde el predicado
        g_aspect = None
        tense = None
        pred_lemma = prop.predicate.lemma.lower() if prop.predicate else None
        pred_type_val = prop.predicate.predicate_type.value if prop.predicate else None

        if prop.predicate:
            ta = prop.predicate.tense_or_aspect
            if ta in ("progressive", "perfect", "prospective", "habitual"):
                g_aspect = ta
            elif ta in ("past", "present", "future"):
                tense = ta

        # Detectar marcador temporal y referencia al pasado
        has_temp = bool(prop.temporal_modifiers)
        temp_marker = None
        if prop.temporal_modifiers:
            temp_marker = prop.temporal_modifiers[0].get("value") or prop.temporal_modifiers[0].get("lemma")

        past_words = {"ayer", "anoche", "antes", "pasado", "año_pasado", "mes_pasado", "hace", "anterior"}
        has_past = tense == "past" or any(pw in text_lower for pw in past_words)

        temp_words = {"ayer", "anoche", "hoy", "mañana", "antes", "después", "pasado", "futuro", "siempre", "ahora", "tarde", "temprano", "pronto"}
        has_temp_word = any(re.search(rf"\b{tw}\b", text_lower) for tw in temp_words)

        # Cópula tipificada: atributiva, identificacional, locativa, existencial, temporal
        is_cop = False
        c_type = None
        has_adj_pred = False
        if pred_lemma in ("ser", "estar", "haber"):
            is_cop = True
            if pred_lemma == "haber":
                c_type = "existencial"
            elif any(tw in text_lower for tw in ("tarde", "temprano", "noche", "día", "lunes", "martes", "hora")):
                c_type = "temporal"
            elif location_p is not None or any(loc_w in text_lower for loc_w in ("en ", "sobre ", "bajo ", "aquí", "allí", "tulcán", "cayambe")):
                c_type = "locativa"
            elif pred_type_val in ("EQUATIVE",) or (prop.participants and any(p.semantic_role == SemanticRole.THEME for p in prop.participants) and not has_patient):
                c_type = "identificacional"
            else:
                c_type = "attributive"
                has_adj_pred = True
        elif pred_type_val in ("STATE", "EQUATIVE") and not has_patient:
            has_adj_pred = True

        # Tipificación de pro-drop
        pdrop_type = None
        if not explicit_subj:
            if agent_p and agent_p.grammatical_person in ("1", "1-PL"):
                pdrop_type = "pro1"
            elif agent_p and agent_p.grammatical_person in ("2", "2-PL") and prop.modality != "imperative":
                pdrop_type = "pro2"
            elif agent_p and agent_p.coreference_id:
                pdrop_type = "anaphoric"
            elif pred_lemma in ("llover", "nevar", "granizar", "tronar") or "se " in text_lower:
                pdrop_type = "impersonal"
            elif agent_p and agent_p.grammatical_person in ("3", "3-PL"):
                pdrop_type = "ambiguous"
            else:
                pdrop_type = "ambiguous"

        # Detección de subordinación / embebido
        has_subord = bool(prop.embedded_propositions) or "lo que" in text_lower or ("haz" in text_lower and "imagina" in text_lower)
        is_emb = getattr(prop, "is_embedded", False) or bool(prop.parent_proposition_id)

        return cls(
            frame_id=f"frame_{prop.id}",
            proposition_id=prop.id,
            source_text=prop.source_text,
            sentence_type=s_type,
            is_embedded=is_emb,
            has_subordinate=has_subord,
            predicate_lemma=pred_lemma,
            predicate_type=pred_type_val,
            has_patient_or_theme=has_patient,
            explicit_subject=explicit_subj,
            is_copulative=is_cop,
            copula_type=c_type,
            has_adjectival_predicate=has_adj_pred,
            has_attributive_adjective=False,
            polarity=prop.polarity,
            modality=prop.modality,
            negation_scope="clausal" if prop.polarity == "negative" else None,
            has_temporal_reference=has_temp or (temp_marker is not None) or has_temp_word,
            has_past_reference=has_past,
            temporal_marker=temp_marker,
            grammatical_aspect=g_aspect,
            tense=tense,
            agent=agent_p.lemma if agent_p else None,
            agent_person=agent_p.grammatical_person if agent_p else None,
            prodrop_type=pdrop_type,
            patient=patient_p.lemma if patient_p else None,
            beneficiary=beneficiary_p.lemma if beneficiary_p else None,
            instrument=instrument_p.lemma if instrument_p else None,
            location=location_p.lemma if location_p else None,
            participants=[
                {"lemma": p.lemma, "role": p.semantic_role.value, "person": p.grammatical_person, "implicit": p.is_implicit}
                for p in prop.participants
            ],
            topic=prop.topic,
            focus=prop.focus,
            discourse_relation=prop.discourse_relation,
            rhetorical_function=prop.rhetorical_function,
            confidence=prop.confidence,
            requires_review=prop.requires_review or (pdrop_type == "ambiguous"),
            review_reasons=list(prop.review_reasons) + (["Sujeto tácito ambiguo de 3ra persona"] if pdrop_type == "ambiguous" else []),
        )


# ============================================================
# Módulo 3 — Operaciones Espaciales y Referentes
# ============================================================

class SpatialReferent(BaseModel):
    """Referente establecido en el espacio signante para correferencia."""
    id: str = Field(description="Identificador único del referente (ej: 'campus_tulcan')")
    label: str = Field(description="Etiqueta legible (ej: 'Tulcán')")
    location: str = Field(description="Ubicación en el espacio: 'left', 'right', 'center', 'up', 'down'")
    established_at_order: Optional[int] = Field(default=None, description="Orden de la glosa donde se establece")
    entity_type: Optional[str] = Field(default=None)


class SpatialOperation(BaseModel):
    """Operación espacial ejecutable asociada a un referente en el discurso."""
    id: str = Field(default_factory=lambda: f"sp_{uuid4().hex[:6]}")
    operation_type: SpatialOperationType = Field(default=SpatialOperationType.ESTABLISH)
    referent_id: str = Field(description="ID del referente espacial involucrado")
    operation_trigger_gloss_id: Optional[str] = Field(default=None, description="ID de la glosa que dispara la operación")
    location: str = Field(description="Ubicación objetivo ('left', 'right', 'center', etc.)")
    source_order: Optional[int] = Field(default=None, description="Orden de glosa origen")
    target_order: Optional[int] = Field(default=None, description="Orden de glosa destino")
    hand_or_body_direction: Optional[str] = Field(default=None)
    eye_gaze: Optional[str] = Field(default=None)
    duration_ms: int = Field(default=200, ge=0)
    confidence: float = Field(default=0.90, ge=0.0, le=1.0)


# ============================================================
# Módulo 4 — Componentes No Manuales y Spans
# ============================================================

class NonManualMarker(BaseModel):
    """Marcador no-manual asociado a una glosa individual."""
    expression: FacialExpression = Field(default=FacialExpression.NEUTRAL)
    head_movement: Optional[str] = Field(default=None)
    mouth_pattern: Optional[str] = Field(default=None)
    eye_gaze: Optional[str] = Field(default=None)
    intensity: float = Field(default=1.0, ge=0.0, le=2.0)


class NonManualSpan(BaseModel):
    """Marcador no-manual que abarca un rango de glosas con alcance sintáctico/discursivo."""
    id: str = Field(default_factory=lambda: f"span_{uuid4().hex[:6]}")
    type: str = Field(description="Tipo de span: 'negation', 'contrast', 'question_wh', 'question_yn', 'emphasis', 'conditional', 'imperative', 'narrative', 'reflective', 'superlative'")
    start_order: int = Field(ge=0)
    end_order: int = Field(ge=0)
    gloss_ids: List[str] = Field(default_factory=list, description="IDs de glosas cubiertas por el span")
    expression: FacialExpression = Field(default=FacialExpression.NEUTRAL)
    head_movement: Optional[str] = Field(default=None)
    body_shift: Optional[str] = Field(default=None)
    eye_gaze: Optional[str] = Field(default=None)
    mouth_pattern: Optional[str] = Field(default=None)
    brow_position: Optional[str] = Field(default=None)
    torso_orientation: Optional[str] = Field(default=None)
    shoulder_shift: Optional[str] = Field(default=None)
    intensity: float = Field(default=1.0, ge=0.0, le=2.0)
    priority: int = Field(default=1, ge=1, le=10)
    onset_ms: int = Field(default=50, ge=0)
    offset_ms: int = Field(default=50, ge=0)
    blend_in_ms: int = Field(default=100, ge=0)
    blend_out_ms: int = Field(default=100, ge=0)
    proposition_id: Optional[str] = Field(default=None)


# ============================================================
# Módulo 5 — Planificación Discursiva y Bloques
# ============================================================

class TranslationPlan(BaseModel):
    """Plan de traducción discursivo para una proposición semántica (LSEC 2.1.1)."""
    id: str = Field(default_factory=lambda: f"plan_{uuid4().hex[:6]}")
    proposition_id: str
    selected_strategy: StrategyType = Field(default=StrategyType.TOPIC_COMMENT)
    topic: Optional[str] = None
    focus: Optional[str] = None
    manual_components: List[str] = Field(default_factory=list)
    lexical_items: List[str] = Field(default_factory=list)
    paraphrase_items: List[str] = Field(default_factory=list)
    spatial_operations: List[SpatialOperation] = Field(default_factory=list)
    non_manual_requirements: List[str] = Field(default_factory=list)
    source_concept_items: List[SourceConceptItem] = Field(default_factory=list)
    realized_concept_items: List[RealizedConceptItem] = Field(default_factory=list)
    source_concepts: List[str] = Field(default_factory=list)
    required_source_concepts: List[str] = Field(default_factory=list)
    optional_source_concepts: List[str] = Field(default_factory=list)
    realized_concepts: List[str] = Field(default_factory=list)
    omitted_concepts: List[str] = Field(default_factory=list)
    unsupported_realized_concepts: List[str] = Field(default_factory=list)
    cross_proposition_concepts: List[str] = Field(default_factory=list)
    inferred_concepts: List[InferredConcept] = Field(default_factory=list)
    source_recall: float = Field(default=1.0, ge=0.0, le=1.0)
    extraction_coverage_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    realization_coverage_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    realization_precision: float = Field(default=1.0, ge=0.0, le=1.0)
    coverage_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    coverage_status: str = Field(default="COMPLETE", description="'COMPLETE' | 'PARTIAL' | 'CONTENT_LEAK' | 'FAILED'")
    pause_before_ms: int = Field(default=0, ge=0)
    pause_after_ms: int = Field(default=250, ge=0)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    requires_native_review: bool = Field(default=True)
    requires_audio_review: bool = Field(default=False)
    applied_rule_ids: List[str] = Field(default_factory=list, description="IDs de reglas gramaticales aplicadas por el motor")
    confidence_vector: Optional[Dict[str, Any]] = Field(default=None, description="Vector de confianza multidimensional")


class DiscourseBlock(BaseModel):
    """Bloque discursivo estructurado que agrupa una o más proposiciones afines."""
    id: int = Field(ge=0)
    label: str = Field(description="Etiqueta descriptiva")
    discourse_function: str = Field(description="Función retórica o tipo discursivo")
    start_order: int = Field(ge=0)
    end_order: int = Field(ge=0)
    gloss_ids: List[str] = Field(default_factory=list, description="IDs de las glosas del bloque")
    proposition_ids: List[str] = Field(default_factory=list)
    child_block_ids: List[int] = Field(default_factory=list)
    active_referents: List[str] = Field(default_factory=list)
    base_expression: FacialExpression = Field(default=FacialExpression.NEUTRAL)
    pause_before_ms: int = Field(default=0, ge=0)
    pause_after_ms: int = Field(default=300, ge=0)
    confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    requires_native_review: bool = Field(default=False)
    requires_audio_review: bool = Field(default=False)


# ============================================================
# Módulo 6 — Elementos de Glosa y Temporización
# ============================================================

class DictionarySignMetadata(BaseModel):
    """
    Ficha de una seña del Diccionario Oficial LSEC "Gabriel Román" (CONADIS).

    `verified_in_conadis=True` solo indica que la seña existe en el diccionario oficial;
    no sustituye la validación por personas sordas usuarias nativas de LSEC.
    """
    verified_in_conadis: bool = Field(default=False)
    status: str = Field(
        default="NO_VERIFICADO",
        description="'VERIFICADO_CONADIS' | 'NO_VERIFICADO' | 'EXENTO_GRAMATICAL' | 'DACTILOLOGIA'",
    )
    conadis_slug: Optional[str] = None
    official_sign_title: Optional[str] = None
    matched_variant: Optional[str] = Field(default=None, description="Variante léxica del título que coincidió")
    match_type: Optional[str] = Field(default=None, description="'exact' | 'normalized' | 'lemma' | 'fuzzy'")
    hand_configuration: Optional[str] = None
    alphabetical_group: Optional[str] = None
    geolect: Optional[str] = Field(default="Nacional", description="Geolecto LSEC: 'Nacional' | 'Sierra' | 'Costa'")
    thematic_categories: List[str] = Field(default_factory=list)
    video_url: Optional[str] = None
    illustration_url: Optional[str] = None
    source_url: Optional[str] = None
    lexical_alternatives: List[str] = Field(default_factory=list)


class GlossItem(BaseModel):
    """Elemento individual de la secuencia de glosas LSEC."""
    id: str = Field(default_factory=lambda: f"g_{uuid4().hex[:6]}")
    gloss: str = Field(description="Texto de la glosa en mayúsculas")
    gloss_type: GlossType = Field(description="Tipo de glosa")
    order: int = Field(ge=0)
    proposition_id: Optional[str] = Field(default=None)
    discourse_unit_id: Optional[int] = Field(default=None)
    discourse_block_id: Optional[int] = Field(default=None)
    source_word: Optional[str] = Field(default=None)
    normalized_word: Optional[str] = Field(default=None)
    semantic_concept: Optional[str] = Field(default=None)
    source_token_indexes: List[int] = Field(default_factory=list)
    local_token_indexes: List[int] = Field(default_factory=list)
    global_source_token_indexes: List[int] = Field(default_factory=list)
    source_char_start: Optional[int] = Field(default=None)
    source_char_end: Optional[int] = Field(default=None)
    source_start_seconds: Optional[float] = Field(default=None)
    source_end_seconds: Optional[float] = Field(default=None)
    alignment_type: Optional[AlignmentType | str] = Field(default=None)
    alignment_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    coreference_target_id: Optional[str] = Field(default=None)
    antecedent_proposition_id: Optional[str] = Field(default=None)
    origin_proposition_id: Optional[str] = Field(default=None)
    inference_rule_id: Optional[str] = Field(default=None)
    supported_by_concept_ids: List[str] = Field(default_factory=list)
    discourse_relation: Optional[str] = Field(default=None)
    entity_alias_id: Optional[str] = Field(default=None)
    normalization_id: Optional[str] = Field(default=None)
    lexical_strategy: Optional[str] = Field(default=None)
    grammatical_function: Optional[str] = Field(default=None)
    semantic_role: Optional[SemanticRole] = Field(default=None)
    non_manual: NonManualMarker = Field(default_factory=NonManualMarker)
    duration_ms: int = Field(default=500, ge=100)
    pause_before_ms: int = Field(default=0, ge=0)
    pause_after_ms: int = Field(default=0, ge=0)
    notes: Optional[str] = Field(default=None)
    spatial_ref: Optional[str] = Field(default=None)
    spatial_operation_ids: List[str] = Field(default_factory=list)
    non_manual_span_ids: List[str] = Field(default_factory=list)
    validation: Optional[Dict[str, Any]] = Field(default=None)
    alternatives: List[str] = Field(default_factory=list)
    requires_review: bool = Field(default=False)
    requires_native_review: bool = Field(default=False)
    requires_audio_review: bool = Field(default=False)
    review_reasons: List[str] = Field(default_factory=list)
    dictionary_metadata: Optional[DictionarySignMetadata] = Field(
        default=None,
        description="Ficha del Diccionario Oficial LSEC (CONADIS) asociada a la glosa, si aplica.",
    )
    facial_expression: Optional[FacialExpression] = Field(default=None, description="Expresión facial directa")
    spatial_location: Optional[SpatialLocation] = Field(default=None, description="Locus espacial de origen/asociación")
    target_spatial_location: Optional[SpatialLocation] = Field(default=None, description="Locus espacial de destino")

    # Compatibilidad hacia atrás: alias de original_word
    original_word: Optional[str] = Field(default=None, description="[DEPRECATED] Use source_word o normalized_word")

    def model_post_init(self, __context: Any) -> None:
        """Sincroniza original_word, source_word y facial_expression para máxima compatibilidad."""
        if self.original_word is None and self.source_word is not None:
            self.original_word = self.source_word
        elif self.source_word is None and self.original_word is not None:
            self.source_word = self.original_word

        if self.facial_expression is not None and self.non_manual is not None:
            self.non_manual.expression = self.facial_expression
        elif self.non_manual is not None and self.non_manual.expression != FacialExpression.NEUTRAL:
            self.facial_expression = self.non_manual.expression


class PauseType(str, Enum):
    """Tipo de pausa en la línea de tiempo."""
    SOURCE_AUDIO_PAUSE = "SOURCE_AUDIO_PAUSE"
    EXTENDED_VIDEO_PAUSE = "EXTENDED_VIDEO_PAUSE"


class PauseEvent(BaseModel):
    """Evento de pausa en la línea de tiempo."""
    pause_type: PauseType = Field(default=PauseType.SOURCE_AUDIO_PAUSE)
    start_ms: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    related_block_id: Optional[int] = None
    reason: Optional[str] = None


class VideoTimelineMarker(BaseModel):
    """Hito o marcador temporal para la reproducción del avatar."""
    marker_type: str = Field(description="Tipo de hito: 'START', 'BLOCK_START', 'PAUSE', 'END'")
    at_ms: int = Field(default=0, ge=0)
    label: str = Field(description="Etiqueta descriptiva")
    related_gloss_id: Optional[str] = None
    related_block_id: Optional[int] = None
    related_span_id: Optional[str] = None


class TimingPlan(BaseModel):
    """Plan de temporización y sincronización de la secuencia LSEC (LSEC 2.1.1)."""
    source_duration_ms: Optional[int] = Field(default=None)
    planned_duration_ms: int = Field(default=0)
    total_duration_ms: int = Field(default=0)
    signs_duration_ms: int = Field(default=0)
    fingerspelling_duration_ms: int = Field(default=0)
    source_audio_pauses_duration_ms: int = Field(default=0)
    extended_video_pauses_duration_ms: int = Field(default=0)
    manual_sign_duration_ms: int = Field(default=0)
    spatial_operation_duration_ms: int = Field(default=0)
    non_manual_concurrent_duration_ms: int = Field(default=0)
    sequential_duration_ms: int = Field(default=0)
    concurrent_duration_ms: int = Field(default=0)
    pause_budget_ms: int = Field(default=0)
    paraphrase_budget_ms: int = Field(default=0)
    paraphrase_duration_ms: int = Field(default=0)
    compression_ratio: float = Field(default=1.0)
    signing_rate: float = Field(default=2.2)
    requires_extended_video: bool = Field(default=False)
    synchronization_status: str = Field(default="SYNCHRONIZED_WITH_SOURCE")
    recommended_playback_strategy: str = Field(default="natural_signing_rate")
    source_audio_pause_points_seconds: List[float] = Field(default_factory=list)
    translated_video_timeline_markers_seconds: List[float] = Field(default_factory=list)
    extended_video_pause_points_seconds: List[float] = Field(default_factory=list)
    recommended_audio_pause_points: List[float] = Field(default_factory=list)
    recommended_video_pause_points: List[float] = Field(default_factory=list)
    pause_events: List[PauseEvent] = Field(default_factory=list)
    video_timeline_markers: List[VideoTimelineMarker] = Field(default_factory=list)
    timing_warnings: List[str] = Field(default_factory=list)
    timing_warning: Optional[str] = None


class MultidimensionalConfidence(BaseModel):
    """Desglose multidimensional de confianza de traducción."""
    overall_score: float = Field(default=0.88, ge=0.0, le=1.0)
    overall_linguistic_confidence: float = Field(default=0.88, ge=0.0, le=1.0)
    structural_confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    asr_confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    normalization_confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    alignment_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    segmentation_confidence: float = Field(default=0.92, ge=0.0, le=1.0)
    semantic_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    coverage_confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    lexical_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    ordering_confidence: float = Field(default=0.92, ge=0.0, le=1.0)
    spatial_confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    non_manual_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    timing_confidence: float = Field(default=0.92, ge=0.0, le=1.0)
    native_validation_confidence: Optional[float] = Field(default=0.0, ge=0.0, le=1.0)
    planning_confidence: float = Field(default=0.92, ge=0.0, le=1.0)
    structural_penalties: float = Field(default=0.0, ge=0.0, le=1.0)


class ValidationMetadata(BaseModel):
    """Metadatos exhaustivos de validación y control de calidad."""
    schema_version: str = Field(default="2.1")
    engine_version: str = Field(default="2.1.1")
    pipeline_version: str = Field(default="2.1.1")
    execution_status: ExecutionStatus = Field(default=ExecutionStatus.REVIEW_REQUIRED)
    multidimensional_confidence: MultidimensionalConfidence = Field(default_factory=MultidimensionalConfidence)
    overall_linguistic_confidence: float = Field(default=0.88, ge=0.0, le=1.0)
    native_reviewed: bool = Field(default=False)
    requires_native_review: bool = Field(default=False)
    requires_audio_review: bool = Field(default=False)
    review_status: str = Field(default="PENDING_NATIVE_REVIEW")
    review_reasons: List[str] = Field(default_factory=list)
    pending_native_review_gloss_ids: List[str] = Field(default_factory=list)
    pending_audio_review_ids: List[str] = Field(default_factory=list)
    pending_semantic_review_ids: List[str] = Field(default_factory=list)
    pending_ordering_review_ids: List[str] = Field(default_factory=list)
    pending_review_types: List[str] = Field(default_factory=list)
    blocking_issue_codes: List[str] = Field(default_factory=list)
    warnings_count: int = Field(default=0)
    errors_count: int = Field(default=0)
    propositions_count: int = Field(default=0)
    plans_count: int = Field(default=0)
    glosses_count: int = Field(default=0)
    blocks_count: int = Field(default=0)
    spatial_referents_count: int = Field(default=0)
    spatial_operations_count: int = Field(default=0)
    non_manual_spans_count: int = Field(default=0)
    automatic_repairs_applied: List[Dict[str, Any]] = Field(default_factory=list)
    computational_proposal_notice: str = Field(
        default="Propuesta computacional sujeta a validación por personas sordas usuarias nativas de LSEC."
    )


class StructuralValidationError(BaseModel):
    """Error o advertencia detectado por el validador estructural automático."""
    severity: ValidationSeverity = Field(default=ValidationSeverity.WARNING)
    code: str = Field(description="Código del error")
    message: str = Field(description="Descripción legible del hallazgo")
    affected_ids: List[str] = Field(default_factory=list)
    suggested_fix: Optional[str] = None
    automatic_fix_available: bool = Field(default=False)
    blocking: bool = Field(default=False)


# ============================================================
# Módulo 7 — Salida Completa GlossOutput (v2.1.1)
# ============================================================

class GlossOutput(BaseModel):
    """
    Resultado completo de la traducción a glosas LSEC (Versión 2.1.1).

    Ofrece trazabilidad completa, representación intermedia, bloques
    discursivos estructurados, operaciones espaciales, spans no manuales,
    plan de temporización, cobertura semántica, resumen de validación
    y estado de ejecución (READY / REVIEW_REQUIRED / BLOCKED).
    """
    schema_version: str = Field(default="2.1", description="Versión del esquema de salida (2.1 compatible)")
    engine_version: str = Field(default="2.1.1", description="Versión del motor lingüístico")
    pipeline_version: str = Field(default="2.1.1", description="Versión del pipeline de ejecución")
    mode: TranslationMode = Field(default=TranslationMode.DETAILED)
    session_id: UUID = Field(default_factory=uuid4)
    original_text: str = Field(description="Texto original en español")
    normalized_text: Optional[str] = Field(default=None)
    corrections_applied: List[Dict[str, Any]] = Field(default_factory=list)
    entities: List[Dict[str, Any]] = Field(default_factory=list)

    # Estado de ejecución para avatar / cliente
    execution_status: ExecutionStatus = Field(default=ExecutionStatus.REVIEW_REQUIRED)
    blocking_issue_codes: List[str] = Field(default_factory=list)
    automatic_repairs_applied: List[Dict[str, Any]] = Field(default_factory=list)
    remaining_issues: List[Dict[str, Any]] = Field(default_factory=list)

    # Representación intermedia
    semantic_propositions: List[SemanticProposition] = Field(default_factory=list)
    translation_plans: List[TranslationPlan] = Field(default_factory=list)

    # Salida lineal de glosas
    glosses: List[GlossItem] = Field(default_factory=list)
    discourse_blocks: List[DiscourseBlock] = Field(default_factory=list)
    spatial_referents: List[SpatialReferent] = Field(default_factory=list)
    spatial_operations: List[SpatialOperation] = Field(default_factory=list)
    non_manual_spans: List[NonManualSpan] = Field(default_factory=list)

    # Temporización y métricas
    timing_plan: Optional[TimingPlan] = Field(default=None)
    total_duration_ms: int = Field(default=0)

    # Validación y notas
    validation_metadata: Optional[ValidationMetadata] = Field(default=None)
    confidence: Optional[ValidationMetadata] = Field(default=None)
    validation_summary: Optional[Dict[str, Any]] = Field(default=None)
    unresolved_items: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[StructuralValidationError] = Field(default_factory=list)
    grammar_notes: Optional[str] = Field(default=None)
    grammar_engine_version: str = Field(default="0.1.0", description="Versión del motor de gramática LSEC")
    semantic_frames: List[SemanticFrame] = Field(default_factory=list, description="Frames semánticos intermedios (modo debug)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def model_post_init(self, __context: Any) -> None:
        """Calcula duración total, plan de temporización y sincroniza metadatos si faltan."""
        if self.validation_metadata is not None and self.confidence is None:
            self.confidence = self.validation_metadata
        elif self.confidence is not None and self.validation_metadata is None:
            self.validation_metadata = self.confidence

        if self.total_duration_ms == 0 and self.glosses:
            self.total_duration_ms = sum(g.duration_ms for g in self.glosses)
        if self.timing_plan is None and self.total_duration_ms > 0:
            self.timing_plan = TimingPlan(
                planned_duration_ms=self.total_duration_ms,
                total_duration_ms=self.total_duration_ms,
                signing_rate=round(len(self.glosses) / (self.total_duration_ms / 1000.0), 2) if self.total_duration_ms > 0 else 2.0,
            )


# ============================================================
# Módulo 8 — Keypoints y Payload para el visor 3D
# ============================================================

class Landmark3D(BaseModel):
    """Punto de referencia tridimensional normalizado."""
    x: float = Field(description="Coordenada X normalizada [0, 1]")
    y: float = Field(description="Coordenada Y normalizada [0, 1]")
    z: float = Field(description="Coordenada Z normalizada (profundidad)")
    visibility: float = Field(default=1.0, ge=0.0, le=1.0)


class HandKeypoints(BaseModel):
    """21 puntos de referencia de una mano (formato de mano)."""
    landmarks: List[Landmark3D] = Field(min_length=21, max_length=21)
    handedness: str = Field(default="right")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class PoseKeypoints(BaseModel):
    """33 puntos de referencia del cuerpo (formato de pose)."""
    landmarks: List[Landmark3D] = Field(min_length=33, max_length=33)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class FaceKeypoints(BaseModel):
    """468 puntos de referencia del rostro (formato de malla facial)."""
    landmarks: List[Landmark3D] = Field(min_length=468, max_length=468)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class BlendshapeValue(BaseModel):
    """Valor de un blendshape facial para animación."""
    name: str = Field(description="Nombre del blendshape")
    value: float = Field(ge=0.0, le=1.0)


class KeypointsFrame(BaseModel):
    """Frame completo de keypoints extraídos de una imagen/video."""
    frame_index: int = Field(default=0, ge=0)
    timestamp_ms: float = Field(default=0.0, ge=0.0)
    left_hand: Optional[HandKeypoints] = None
    right_hand: Optional[HandKeypoints] = None
    pose: Optional[PoseKeypoints] = None
    face: Optional[FaceKeypoints] = None
    blendshapes: List[BlendshapeValue] = Field(default_factory=list)


class AvatarPayload(BaseModel):
    """Payload por glosa para el visor 3D (glosa, marcadores no manuales y metadatos de secuencia)."""
    session_id: UUID = Field(default_factory=uuid4)
    sequence_index: int = Field(default=0, ge=0)
    gloss: Optional[GlossItem] = Field(default=None)
    keypoints: Optional[KeypointsFrame] = None
    non_manual_markers: NonManualMarker = Field(default_factory=NonManualMarker)
    blendshapes: List[BlendshapeValue] = Field(default_factory=list)
    timestamp_ms: float = Field(default=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WebSocketMessage(BaseModel):
    """Wrapper genérico para mensajes WebSocket bidireccionales."""
    type: WSMessageType
    payload: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[UUID] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None
