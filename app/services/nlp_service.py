"""
Módulo 2 — Servicio de Traducción Discursiva y Semántica Español → LSEC (Versión 2.1.1).

Orquestador principal del pipeline lingüístico LSEC 2.1.1:
  1. NORMALIZACIÓN TRAZABLE (TextNormalizer)
  2. DETECCIÓN DE EXPRESIONES MULTIPALABRA Y ENTIDADES (MWEDetector)
  3. SEGMENTACIÓN EN PROPOSICIONES (DiscourseSegmenter)
  4. REPRESENTACIÓN SEMÁNTICA INTERMEDIA (SemanticParser)
  5. PLANIFICACIÓN DISCURSIVA Y GENERACIÓN PRELIMINAR (DiscoursePlanner)
  6. RESOLUCIÓN Y REPARACIÓN DE DUPLICADOS (DuplicatePlanResolver)
  7. ENLACE EXHAUSTIVO DE METADATOS DE EJECUCIÓN (ExecutionMetadataLinker)
  8. ALINEACIÓN TEMPORAL Y TRAZABILIDAD FUENTE (SourceAlignmentService)
  9. TEMPORIZACIÓN Y SINCRONIZACIÓN (TimingService)
  10. RESPUESTA API (Modos: Legacy, Detailed, Debug)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from uuid import UUID, uuid4

from app.config import settings
from app.core.schemas import (
    DiscourseBlock,
    FacialExpression,
    GlossItem,
    GlossOutput,
    GlossType,
    NonManualMarker,
    NonManualSpan,
    SemanticProposition,
    SpatialOperation,
    SpatialReferent,
    TimingPlan,
    TranslationMode,
    TranslationPlan,
    TranscriptionInput,
    TranscriptionResult,
    WordTimestamp,
)
from app.core.audio_reference import get_word_timestamps_for_text
from app.services.alignment_service import SourceAlignmentService
from app.services.discourse_planner import DiscoursePlanner
from app.services.discourse_segmenter import DiscourseSegmenter, DiscourseUnit
from app.services.discourse_group_optimizer import DiscourseGroupOptimizer
from app.services.duplicate_resolver import DuplicatePlanResolver
from app.services.metadata_linker import ExecutionMetadataLinker
from app.services.mwe_detector import MWEDetector
from app.services.semantic_parser import SemanticParser
from app.services.linguistic_analyzer import EnhancedLinguisticAnalyzer
from app.services.text_normalizer import CorrectionRecord, EntityInfo, TextNormalizer
from app.services.timing_service import TimingService

logger = logging.getLogger(__name__)

_LEXICON_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "lexicon_lsec.json"


def _load_lexicon_data() -> Dict[str, Any]:
    """Carga el lexicón lingüístico LSEC."""
    if not _LEXICON_PATH.exists():
        logger.info("Lexicón '%s' no encontrado. Usando configuración predeterminada.", _LEXICON_PATH)
        return {}
    try:
        with open(_LEXICON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Lexicón cargado (versión: %s)", data.get("_version", "2.1.1"))
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Error al cargar lexicón '%s': %s", _LEXICON_PATH, exc)
        return {}


class LSECTranslatorService:
    """
    Servicio principal de traducción discursiva a Lengua de Señas Ecuatoriana (LSEC 2.1.1).
    """

    def __init__(self) -> None:
        self._nlp = None
        self._lexicon_data = _load_lexicon_data()

        # 1. Normalizador de texto y registro de entidades
        self._normalizer = TextNormalizer()
        if self._lexicon_data:
            self._normalizer.load_from_lexicon(self._lexicon_data)

        # 2. Inicializar spaCy
        self._init_spacy()

        # 3. Diccionarios y tablas lingüísticas
        self._init_compat_tables()

        # 4. Detector de Expresiones Multipalabra (MWE)
        self._mwe_detector = MWEDetector()
        if self._lexicon_data:
            self._mwe_detector.load_from_lexicon(self._lexicon_data)

        # 5. Segmentador Discursivo
        self._segmenter = DiscourseSegmenter(nlp=self._nlp)

        # 6. Parser Semántico
        self._semantic_parser = SemanticParser(
            nlp=self._nlp,
            entity_registry=self._normalizer.get_all_entities(),
            mwe_detector=self._mwe_detector,
            pronoun_deixis_map=self._pronoun_deixis,
        )

        # 7. Planificador Discursivo y Generador LSEC
        self._planner = DiscoursePlanner(
            nlp=self._nlp,
            institutional_dict=self._institutional_dict,
            lemma_overrides=self._lemma_overrides,
            pronoun_deixis_map=self._pronoun_deixis,
            semantic_paraphrases=self._semantic_paraphrases,
            duration_config=self._duration_ms,
            entity_registry=self._normalizer.get_all_entities(),
            mwe_detector=self._mwe_detector,
            plural_marker=self._plural_marker,
            named_entities=self._lexicon_data.get("named_entities"),
        )

        # 7b. Analizador Lingüístico Avanzado
        self._linguistic_analyzer = EnhancedLinguisticAnalyzer(nlp=self._nlp)

        # 8. Servicios Especializados LSEC 2.1.1
        self._duplicate_resolver = DuplicatePlanResolver()
        self._metadata_linker = ExecutionMetadataLinker()
        self._alignment_service = SourceAlignmentService()
        self._timing_service = TimingService()

        logger.info(
            "LSECTranslatorService 2.1.1 inicializado exitosamente (spaCy: %s).",
            "activo" if self._nlp is not None else "modo respaldo",
        )

    def _init_spacy(self) -> None:
        """Carga el modelo lingüístico de spaCy si está disponible."""
        try:
            import spacy
            self._nlp = spacy.load("es_core_news_md")
            logger.info("Modelo spaCy es_core_news_md cargado correctamente.")
        except Exception as exc:
            try:
                import spacy
                self._nlp = spacy.load("es_core_news_sm")
                logger.info("Modelo spaCy es_core_news_sm cargado correctamente.")
            except Exception:
                logger.warning("No se pudo cargar modelo spaCy en español: %s. Operando en modo respaldo.", exc)
                self._nlp = None

    def _init_compat_tables(self) -> None:
        """Inicializa tablas lingüísticas."""
        lex = self._lexicon_data

        if lex.get("institutional_dictionary"):
            self._institutional_dict = {}
            for k, v in lex["institutional_dictionary"].items():
                raw_type = str(v.get("type", "SEÑA")).strip().upper()
                if raw_type in ("FINGERSPELLING", "DACTILOLOGÍA", "DACTILOLOGIA"):
                    g_typ = GlossType.FINGERSPELLING
                elif raw_type in ("CLASSIFIER", "CLASIFICADOR"):
                    g_typ = GlossType.CLASSIFIER
                elif raw_type in ("EXPRESSION", "EXPRESIÓN", "EXPRESION"):
                    g_typ = GlossType.EXPRESSION
                else:
                    g_typ = GlossType.SIGN
                self._institutional_dict[k] = {"gloss": v["gloss"], "type": g_typ}
        else:
            self._institutional_dict = {
                "UPEC": {"gloss": "U-P-E-C", "type": GlossType.FINGERSPELLING},
                "TIC": {"gloss": "T-I-C", "type": GlossType.FINGERSPELLING},
                "LSEC": {"gloss": "L-S-E-C", "type": GlossType.FINGERSPELLING},
                "TULCÁN": {"gloss": "T-U-L-C-Á-N", "type": GlossType.FINGERSPELLING},
                "TULCAN": {"gloss": "T-U-L-C-Á-N", "type": GlossType.FINGERSPELLING},
                "CAYAMBE": {"gloss": "C-A-Y-A-M-B-E", "type": GlossType.FINGERSPELLING},
                "ECUADOR": {"gloss": "ECUADOR", "type": GlossType.SIGN},
            }

        default_overrides = {
            "somos": "ser",
            "es": "ser",
            "son": "ser",
            "era": "ser",
            "fuimos": "ser",
            "fueron": "ser",
            "educamos": "educar",
            "formamos": "formar",
            "transformamos": "transformar",
            "preparamos": "preparar",
            "ofrece": "ofrecer",
            "ofrecemos": "ofrecer",
            "enorgullece": "orgullo",
            "enorgullecer": "orgullo",
            "crean": "crear",
            "construyen": "desarrollar",
            "graduados": "graduado",
            "profesionales": "profesional",
            "carreras": "carrera",
            "campus": "campus",
            "oportunidades": "oportunidad",
            "ideas": "idea",
            "futuro": "futuro",
            "conocimiento": "conocimiento",
            "libertad": "libertad",
            "confianza": "confianza",
            "cercanía": "acompañar",
            "sostenible": "sostenibilidad",
            "excelencia": "excelencia",
            "innovación": "innovación",
            "tecnología": "tecnología",
        }
        self._lemma_overrides = dict(default_overrides)
        if "lemma_overrides" in lex and isinstance(lex["lemma_overrides"], dict):
            self._lemma_overrides.update(lex["lemma_overrides"])

        self._pronoun_deixis = lex.get("pronoun_deixis", {
            "yo": "PRO1", "me": "PRO1", "mí": "PRO1", "conmigo": "PRO1",
            "tú": "PRO2", "te": "PRO2", "ti": "PRO2", "contigo": "PRO2", "tu": "PRO2", "tus": "PRO2",
            "él": "PRO3", "ella": "PRO3",
            "nosotros": "PRO1-PL", "nos": "PRO1-PL", "nosotras": "PRO1-PL",
            "ustedes": "PRO2-PL", "ellos": "PRO3-PL", "ellas": "PRO3-PL",
        })

        self._periphrasis_map = lex.get("periphrasis_patterns", {
            "ir_a": "FUTURO",
            "haber_participio": "YA",
            "estar_gerundio": "AHORA",
            "tener_que": "DEBER",
        })

        default_paraphrases = {
            "imparable": {
                "concept": "persona determinada que avanza y supera obstáculos",
                "default_gloss_sequence": ["PERSONA", "FUERTE", "AVANZAR"],
                "gloss_sequence": ["PERSONA", "FUERTE", "AVANZAR"],
                "realizations": {
                    "compact": ["PERSONA", "FUERTE", "AVANZAR"],
                    "expanded": ["PERSONA", "FUERTE", "OBSTÁCULO", "SUPERAR", "AVANZAR"],
                },
            },
            "cercanía": {
                "concept": "proximidad relacional / calidez humana / acompañamiento",
                "default_gloss_sequence": ["ACOMPAÑAR"],
                "gloss_sequence": ["ACOMPAÑAR"],
            },
            "lograr": {
                "concept": "meta alcanzada con éxito",
                "default_gloss_sequence": ["LOGRAR"],
                "gloss_sequence": ["LOGRAR"],
            },
            "evolucionar": {
                "concept": "progreso continuo y desarrollo hacia adelante",
                "default_gloss_sequence": ["AVANZAR"],
                "gloss_sequence": ["AVANZAR"],
                "realizations": {
                    "compact": ["AVANZAR"],
                    "medium": ["AVANZAR"],
                    "expanded": ["AVANZAR"],
                },
            },
        }
        self._semantic_paraphrases = dict(default_paraphrases)
        if "semantic_paraphrases" in lex and isinstance(lex["semantic_paraphrases"], dict):
            self._semantic_paraphrases.update(lex["semantic_paraphrases"])
            if "evolucionar" not in self._semantic_paraphrases:
                self._semantic_paraphrases["evolucionar"] = default_paraphrases["evolucionar"]


        self._duration_ms = lex.get("timing_config", {
            "sign_base": 500,
            "sign_short": 400,
            "sign_long": 600,
            "fingerspelling_per_char": 300,
            "temporal_marker": 400,
            "aspectual_marker": 350,
            "deixis": 350,
            "plural_marker": 300,
            "inter_clause_pause": 200,
        })
        self._plural_marker = lex.get("grammar_rules", {}).get("plural_marker", "VARIOS")

    # ------------------------------------------------------------------ #
    # Pipeline Principal de Traducción LSEC 2.1.1
    # ------------------------------------------------------------------ #

    async def translate_to_gloss(
        self,
        text: str,
        mode: str = "detailed",
        paraphrase_budget: str = "compact",
        source_audio_duration: Optional[float] = None,
        transcription: Optional[Union[TranscriptionInput, TranscriptionResult, Dict[str, Any]]] = None,
        exclude_rule_ids: Optional[Set[str]] = None,
        condense_level: Optional[str] = None,
        context_before: Optional[str] = None,
    ) -> GlossOutput:
        """
        Traduce texto o audio transcrito a representación intermedia y glosas LSEC 2.1.1.
        """
        text = text.strip()
        if not text:
            raise ValueError("El texto de entrada está vacío.")

        trans_mode = TranslationMode.DETAILED
        if mode == "legacy":
            trans_mode = TranslationMode.LEGACY
        elif mode == "debug":
            trans_mode = TranslationMode.DEBUG

        # Extraer marcas de tiempo de palabras si vienen en transcription, o usar referencia canónica
        if transcription and transcription.word_timestamps:
            word_timestamps = transcription.word_timestamps
        else:
            word_timestamps = get_word_timestamps_for_text(text)

        # Paso 1: Normalización Contextual Trazable
        normalized_text, corrections = self._normalizer.normalize(text, word_timestamps=word_timestamps)
        detected_numbers = self._normalizer.detect_numbers(normalized_text)

        # Paso 2: Segmentación en Unidades Discursivas / Proposiciones
        discourse_units = self._segmenter.segment(normalized_text)

        # Paso 3: Representación Semántica Intermedia
        # Contexto previo opcional (p. ej. la oración anterior al editar un segmento): se analiza solo para
        # resolver correferencias y relaciones de discurso; sus proposiciones NO forman parte de la salida.
        context_props: List[SemanticProposition] = []
        if context_before and context_before.strip():
            for cu in self._segmenter.segment(self._normalizer.normalize(context_before.strip())[0]):
                for cp in self._semantic_parser.parse_unit_to_propositions(
                    unit=cu, prev_propositions=context_props, active_speaker="narrator",
                ):
                    cp.id = f"ctx_{cp.id}"
                    context_props.append(cp)

        all_propositions: List[SemanticProposition] = []
        for du in discourse_units:
            props = self._semantic_parser.parse_unit_to_propositions(
                unit=du,
                prev_propositions=context_props + all_propositions,
                active_speaker="narrator",
            )
            for _p in props:
                _p.sentence_id = du.sentence_id
                _p.sentence_text = du.sentence_text
            all_propositions.extend(props)

        # Paso 3b: Enriquecimiento Lingüístico Avanzado
        if self._nlp is not None:
            for prop in all_propositions:
                doc = self._nlp(prop.source_text)

                # Pro-drop resolution
                prodrop = self._linguistic_analyzer.detect_prodrop(doc)
                if prodrop:
                    prop.context_info["prodrop_category"] = prodrop.category
                    if prodrop.requires_deixis and prodrop.deixis_gloss and not prop.participants:
                        from app.core.schemas import SemanticParticipant, ParticipantType, SemanticRole
                        prop.participants.append(SemanticParticipant(
                            lemma=prodrop.deixis_gloss.lower(),
                            normalized_text=prodrop.deixis_gloss,
                            participant_type=ParticipantType.PERSON,
                            semantic_role=SemanticRole.AGENT,
                            grammatical_person=prodrop.person,
                            is_implicit=True,
                        ))

                # Negation scope
                neg_info = self._linguistic_analyzer.detect_negation(doc)
                if neg_info and prop.polarity != "negative":
                    prop.polarity = "negative"
                    if not any(
                        op.get("type") == "NEGATION" for op in prop.operators
                    ):
                        prop.operators.append({
                            "type": "NEGATION",
                            "negation_type": neg_info.negation_type,
                            "scope": f"{neg_info.scope_start_token}-{neg_info.scope_end_token}",
                        })

                # Temporal enrichment
                temp_info = self._linguistic_analyzer.extract_temporal_info(doc)
                if temp_info.tense and not prop.temporal_modifiers:
                    prop.temporal_modifiers.append({
                        "type": "TENSE",
                        "value": temp_info.tense,
                        "marker_gloss": temp_info.temporal_marker_gloss,
                        "source_word": temp_info.source_word,
                    })
                if temp_info.aspect and prop.predicate and not prop.predicate.tense_or_aspect:
                    prop.predicate.tense_or_aspect = temp_info.aspect

                # Coreference links
                coref_links = self._linguistic_analyzer.detect_coreference(doc)
                for link in coref_links:
                    # Enrich participants with coreference data
                    for part in prop.participants:
                        if part.lemma.lower() == link.pronoun:
                            part.coreference_id = link.resolved_entity

        # Paso 4: Planificación Discursiva Preliminar
        (
            glosses,
            plans,
            blocks,
            referents,
            operations,
            spans,
        ) = self._planner.plan_and_generate(
            propositions=all_propositions,
            paraphrase_budget=paraphrase_budget,
            exclude_rule_ids=exclude_rule_ids,
        )

        # Paso 5: Resolución y Reparación de Planes Duplicados y Fugas
        (
            all_propositions,
            plans,
            glosses,
            blocks,
            referents,
            operations,
            spans,
            repairs_applied,
        ) = self._duplicate_resolver.resolve_and_repair(
            propositions=all_propositions,
            plans=plans,
            glosses=glosses,
            blocks=blocks,
            referents=referents,
            operations=operations,
            spans=spans,
        )

        # Paso 5b: Diccionario LSEC (idempotente; cubre glosas creadas durante la reparación)
        self._planner.apply_dictionary(glosses)

        # Paso 5c: Consolidación por oración (idea completa): duplicados en fronteras de proposición,
        # deixis inferida redundante y verbos paralelos. Auditable vía condensation_log.
        (
            glosses,
            blocks,
            referents,
            operations,
            spans,
            condensation_log,
        ) = DiscourseGroupOptimizer(settings.discourse_condense_level).optimize(
            propositions=all_propositions,
            glosses=glosses,
            blocks=blocks,
            referents=referents,
            operations=operations,
            spans=spans,
            level=condense_level or settings.discourse_condense_level,
        )

        # Paso 6: Enlace Bidireccional de Metadatos de Ejecución
        (
            glosses,
            blocks,
            spans,
            operations,
        ) = self._metadata_linker.link_metadata(
            glosses=glosses,
            blocks=blocks,
            spans=spans,
            operations=operations,
            referents=referents,
            propositions=all_propositions,
        )

        # Paso 7: Alineación Temporal y Trazabilidad Fuente
        all_propositions, glosses = self._alignment_service.align_pipeline(
            original_text=text,
            normalized_text=normalized_text,
            word_timestamps=word_timestamps,
            propositions=all_propositions,
            glosses=glosses,
            corrections=[c.to_dict() for c in corrections],
        )

        # Paso 8: Temporización y Sincronización Detallada
        timing_plan = self._timing_service.create_timing_plan(
            glosses=glosses,
            blocks=blocks,
            spans=spans,
            operations=operations,
            source_audio_duration_seconds=source_audio_duration,
        )

        # Paso 13: Resumen de Entidades
        entities_summary: List[Dict[str, Any]] = []
        for r in referents:
            entities_summary.append({
                "id": r.id,
                "label": r.label,
                "location": r.location,
                "type": r.entity_type or "unknown",
            })

        grammar_notes = (
            f"LSEC 2.1.1 Pipeline: {len(all_propositions)} proposiciones semánticas | "
            f"{len(blocks)} bloques discursivos | {len(referents)} referentes espaciales | "
            f"{len(spans)} spans no manuales."
        )

        output = GlossOutput(
            schema_version="2.1",
            engine_version="2.1.1",
            pipeline_version="2.1.1",
            mode=trans_mode,
            session_id=uuid4(),
            original_text=text,
            normalized_text=normalized_text,
            corrections_applied=[c.to_dict() for c in corrections],
            entities=entities_summary,
            semantic_propositions=all_propositions,
            translation_plans=plans,
            glosses=glosses,
            discourse_blocks=blocks,
            spatial_referents=referents,
            spatial_operations=operations,
            non_manual_spans=spans,
            timing_plan=timing_plan,
            total_duration_ms=timing_plan.planned_duration_ms,
            grammar_notes=grammar_notes,
            automatic_repairs_applied=repairs_applied,
            condensation_log=condensation_log,
        )

        return output

    # Alias de compatibilidad retroactiva
    translate_to_lsec = translate_to_gloss

    def _split_into_sentences(self, text: str) -> List[str]:
        """Divide el texto en oraciones (compatibilidad retroactiva)."""
        normalized, _ = self._normalizer.normalize(text)
        units = self._segmenter.segment(normalized)
        return [u.text for u in units] if units else [text]

    _split_into_clauses = _split_into_sentences

    def _translate_heuristic(self, text: str) -> GlossOutput:
        """Fallback heurístico directo."""
        normalized, corrections = self._normalizer.normalize(text)
        units = self._segmenter.segment(normalized)
        props: List[SemanticProposition] = []
        for u in units:
            props.extend(self._semantic_parser.parse_unit_to_propositions(u, props))

        glosses, plans, blocks, refs, ops, spans = self._planner.plan_and_generate(props)
        timing = self._timing_service.create_timing_plan(glosses, blocks)

        return GlossOutput(
            schema_version="2.1",
            mode=TranslationMode.LEGACY,
            original_text=text,
            normalized_text=normalized,
            glosses=glosses,
            grammar_notes="Traducción heurística de respaldo",
            discourse_blocks=blocks,
            spatial_referents=refs,
            spatial_operations=ops,
            non_manual_spans=spans,
            total_duration_ms=timing.planned_duration_ms,
            corrections_applied=[c.to_dict() for c in corrections],
        )


_nlp_service_instance: Optional[LSECTranslatorService] = None


def get_nlp_service() -> LSECTranslatorService:
    """Retorna una instancia singleton de LSECTranslatorService."""
    global _nlp_service_instance
    if _nlp_service_instance is None:
        _nlp_service_instance = LSECTranslatorService()
    return _nlp_service_instance

