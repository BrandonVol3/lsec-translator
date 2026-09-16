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
  10. VALIDACIÓN ESTRUCTURAL Y BLOQUEOS (StructuralValidator)
  11. CÁLCULO DE CONFIANZA MULTIDIMENSIONAL Y ESTADO DE EJECUCIÓN (READY, REVIEW_REQUIRED, BLOCKED)
  12. RESPUESTA API (Modos: Legacy, Detailed, Debug)
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
    ExecutionStatus,
    FacialExpression,
    GlossItem,
    GlossOutput,
    GlossType,
    MultidimensionalConfidence,
    NonManualMarker,
    NonManualSpan,
    SemanticProposition,
    SpatialOperation,
    SpatialReferent,
    StructuralValidationError,
    TimingPlan,
    TranslationMode,
    TranslationPlan,
    TranscriptionInput,
    TranscriptionResult,
    ValidationMetadata,
    ValidationSeverity,
    WordTimestamp,
)
from app.core.audio_reference import get_word_timestamps_for_text
from app.services.alignment_service import SourceAlignmentService
from app.services.discourse_planner import DiscoursePlanner
from app.services.discourse_segmenter import DiscourseSegmenter, DiscourseUnit
from app.services.duplicate_resolver import DuplicatePlanResolver
from app.services.metadata_linker import ExecutionMetadataLinker
from app.services.mwe_detector import MWEDetector
from app.services.review_service import ReviewPropagationService
from app.services.semantic_parser import SemanticParser
from app.services.text_normalizer import CorrectionRecord, DubiousWordFinding, EntityInfo, TextNormalizer
from app.services.timing_service import TimingService
from app.services.validator import StructuralValidator

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
        )

        # 8. Servicios Especializados LSEC 2.1.1
        self._duplicate_resolver = DuplicatePlanResolver()
        self._metadata_linker = ExecutionMetadataLinker()
        self._alignment_service = SourceAlignmentService()
        self._timing_service = TimingService()
        self._validator = StructuralValidator()
        self._review_service = ReviewPropagationService()

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
                g_typ = GlossType(v["type"]) if isinstance(v.get("type"), str) else GlossType.SIGN
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
                "requires_review": True,
                "realizations": {
                    "compact": ["PERSONA", "FUERTE", "AVANZAR"],
                    "expanded": ["PERSONA", "FUERTE", "OBSTÁCULO", "SUPERAR", "AVANZAR"],
                },
            },
            "cercanía": {
                "concept": "proximidad relacional / calidez humana / acompañamiento",
                "default_gloss_sequence": ["ACOMPAÑAR"],
                "gloss_sequence": ["ACOMPAÑAR"],
                "requires_review": True,
            },
            "lograr": {
                "concept": "meta alcanzada con éxito",
                "default_gloss_sequence": ["LOGRAR"],
                "gloss_sequence": ["LOGRAR"],
                "requires_review": False,
            },
            "evolucionar": {
                "concept": "progreso continuo y desarrollo hacia adelante",
                "default_gloss_sequence": ["AVANZAR"],
                "gloss_sequence": ["AVANZAR"],
                "requires_review": True,
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
        dubious_words = self._normalizer.check_dubious_words(normalized_text, word_timestamps=word_timestamps)

        # Paso 2: Segmentación en Unidades Discursivas / Proposiciones
        discourse_units = self._segmenter.segment(normalized_text)

        # Paso 3: Representación Semántica Intermedia
        all_propositions: List[SemanticProposition] = []
        for du in discourse_units:
            props = self._semantic_parser.parse_unit_to_propositions(
                unit=du,
                prev_propositions=all_propositions,
                active_speaker="narrator",
            )
            all_propositions.extend(props)

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
            unresolvable_errors,
        ) = self._duplicate_resolver.resolve_and_repair(
            propositions=all_propositions,
            plans=plans,
            glosses=glosses,
            blocks=blocks,
            referents=referents,
            operations=operations,
            spans=spans,
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

        # Paso 9: Propagación Centralizada de Banderas de Revisión
        (
            all_propositions,
            plans,
            glosses,
            blocks,
            rev_meta,
        ) = self._review_service.propagate_reviews(
            propositions=all_propositions,
            plans=plans,
            glosses=glosses,
            blocks=blocks,
            dubious_words=dubious_words,
        )
        has_audio_review = rev_meta.requires_audio_review
        has_native_review = rev_meta.requires_native_review
        combined_reasons = rev_meta.review_reasons

        unresolved_items: List[Dict[str, Any]] = []
        for dub in dubious_words:
            unresolved_items.append(dub.to_dict())

        # Paso 10: Validación Estructural Completa
        validation_warnings = self._validator.validate(
            original_text=text,
            normalized_text=normalized_text,
            propositions=all_propositions,
            glosses=glosses,
            blocks=blocks,
            referents=referents,
            operations=operations,
            spans=spans,
            plans=plans,
            timing_plan=timing_plan,
            corrections=[c.to_dict() for c in corrections],
            unresolved_items=unresolved_items,
            word_timestamps=word_timestamps,
            validation_metadata=rev_meta,
        )
        validation_warnings.extend(unresolvable_errors)

        if transcription:
            c_asr = getattr(transcription, "asr_confidence", getattr(transcription, "confidence", 0.98))
            if isinstance(transcription, dict):
                c_asr = transcription.get("asr_confidence", transcription.get("confidence", 0.98))
            if c_asr is None or c_asr <= 0.0:
                c_asr = 0.98
        else:
            c_asr = 0.98
        c_seg = 0.95 if len(all_propositions) > 0 else 0.80
        c_sem = 0.92
        c_plan = 0.92
        c_spatial = 0.95 if operations else 1.0
        c_non_manual = 0.92 if spans else 1.0
        c_timing = 0.95
        c_align = round(sum(g.alignment_confidence for g in glosses) / max(len(glosses), 1), 3) if glosses else 0.95

        # Penalizaciones por advertencias o errores estructurales
        penalties = 0.0
        for w in validation_warnings:
            if w.severity == ValidationSeverity.ERROR:
                penalties += 0.20
            elif w.severity == ValidationSeverity.WARNING:
                penalties += 0.04
        penalties = min(penalties, 0.50)

        # Media geométrica de dimensiones centrales (puntuación técnica/estructural)
        c_geom = (
            (c_asr ** 0.15) *
            (c_seg ** 0.15) *
            (c_sem ** 0.20) *
            (c_plan ** 0.20) *
            (c_align ** 0.10) *
            (c_timing ** 0.10) *
            (c_spatial ** 0.05) *
            (c_non_manual ** 0.05)
        )
        c_structural = max(min(round(c_geom * (1.0 - penalties), 3), 1.0), 0.0)

        # Puntuación global restringida por dudas acústicas o paráfrasis no validadas
        c_global = c_structural
        if has_audio_review:
            c_global = min(c_global, 0.65)
        elif has_native_review:
            c_global = min(c_global, 0.88)

        c_global = max(min(round(c_global, 3), 1.0), 0.0)

        confidence_meta = MultidimensionalConfidence(
            overall_score=c_structural,
            overall_linguistic_confidence=c_global,
            structural_confidence=c_structural,
            asr_confidence=c_asr,
            segmentation_confidence=c_seg,
            semantic_confidence=c_sem,
            planning_confidence=c_plan,
            structural_penalties=round(penalties, 2),
            spatial_confidence=c_spatial,
            non_manual_confidence=c_non_manual,
            timing_confidence=c_timing,
            alignment_confidence=c_align,
        )

        # Paso 12: Determinación del Estado de Ejecución y Validación
        blocking_issues = [w.code for w in validation_warnings if w.blocking or w.severity == ValidationSeverity.ERROR]
        has_blocking = bool(blocking_issues) or any(w.severity == ValidationSeverity.ERROR for w in validation_warnings)
        if has_blocking:
            execution_status = ExecutionStatus.BLOCKED
            review_status_str = "BLOCKED"
        elif has_audio_review and has_native_review:
            execution_status = ExecutionStatus.REVIEW_REQUIRED
            review_status_str = "PENDING_NATIVE_AND_AUDIO_REVIEW"
        elif has_audio_review:
            execution_status = ExecutionStatus.REVIEW_REQUIRED
            review_status_str = "PENDING_AUDIO_REVIEW"
        elif has_native_review or any(w.severity == ValidationSeverity.WARNING for w in validation_warnings):
            execution_status = ExecutionStatus.REVIEW_REQUIRED
            review_status_str = "PENDING_NATIVE_REVIEW"
        else:
            execution_status = ExecutionStatus.READY
            review_status_str = "AUTO_VERIFIED"

        # Paso 13: Resumen de Entidades
        entities_summary: List[Dict[str, Any]] = []
        for r in referents:
            entities_summary.append({
                "id": r.id,
                "label": r.label,
                "location": r.location,
                "type": r.entity_type or "unknown",
            })

        validation_metadata = ValidationMetadata(
            schema_version="2.1",
            engine_version="2.1.1",
            pipeline_version="2.1.1",
            execution_status=execution_status,
            multidimensional_confidence=confidence_meta,
            overall_linguistic_confidence=c_global,
            native_reviewed=False,
            requires_native_review=has_native_review,
            requires_audio_review=has_audio_review,
            requires_review=has_audio_review or has_native_review,
            review_status=review_status_str,
            review_reasons=combined_reasons,
            pending_review_types=getattr(rev_meta, "pending_review_types", ["NATIVE_LINGUISTIC", "AUDIO"] if (has_native_review and has_audio_review) else (["AUDIO"] if has_audio_review else (["NATIVE_LINGUISTIC"] if has_native_review else []))),
            pending_native_review_gloss_ids=getattr(rev_meta, "pending_native_review_gloss_ids", []),
            pending_audio_review_ids=getattr(rev_meta, "pending_audio_review_ids", []),
            pending_semantic_review_ids=getattr(rev_meta, "pending_semantic_review_ids", []),
            blocking_issue_codes=blocking_issues,
            warnings_count=len(validation_warnings),
            errors_count=len([w for w in validation_warnings if w.severity == ValidationSeverity.ERROR]),
            propositions_count=len(all_propositions),
            plans_count=len(plans),
            glosses_count=len(glosses),
            blocks_count=len(blocks),
            spatial_referents_count=len(referents),
            spatial_operations_count=len(operations),
            non_manual_spans_count=len(spans),
            automatic_repairs_applied=repairs_applied,
            computational_proposal_notice="Propuesta computacional sujeta a validación por personas sordas usuarias nativas de LSEC.",
        )

        validation_summary = {
            "schema_version": "2.1",
            "engine_version": "2.1.1",
            "pipeline_version": "2.1.1",
            "execution_status": execution_status.value,
            "overall_linguistic_confidence": c_global,
            "native_reviewed": False,
            "requires_audio_review": has_audio_review,
            "requires_native_review": has_native_review,
            "requires_review": has_audio_review or has_native_review,
            "review_status": review_status_str,
            "warnings_count": len(validation_warnings),
            "propositions_count": len(all_propositions),
            "plans_count": len(plans),
            "glosses_count": len(glosses),
            "blocks_count": len(blocks),
            "spatial_referents_count": len(referents),
            "spatial_operations_count": len(operations),
            "non_manual_spans_count": len(spans),
            "computational_proposal_notice": "Propuesta computacional sujeta a validación por personas sordas usuarias nativas de LSEC.",
        }

        grammar_notes = (
            f"LSEC 2.1.1 Pipeline [{execution_status.value}]: {len(all_propositions)} proposiciones semánticas | "
            f"{len(blocks)} bloques discursivos | {len(referents)} referentes espaciales | "
            f"{len(spans)} spans no manuales. Confianza global: {c_global}."
        )

        output = GlossOutput(
            schema_version="2.1",
            engine_version="2.1.1",
            pipeline_version="2.1.1",
            mode=trans_mode,
            execution_status=execution_status,
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
            validation_metadata=validation_metadata,
            validation_summary=validation_summary,
            unresolved_items=unresolved_items,
            warnings=validation_warnings,
            grammar_notes=grammar_notes,
            automatic_repairs_applied=repairs_applied,
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

        validation_summary = {
            "schema_version": "2.1",
            "execution_status": "READY",
            "overall_linguistic_confidence": 0.85,
        }

        return GlossOutput(
            schema_version="2.1",
            mode=TranslationMode.LEGACY,
            execution_status=ExecutionStatus.READY,
            original_text=text,
            normalized_text=normalized,
            glosses=glosses,
            grammar_notes="Traducción heurística de respaldo",
            discourse_blocks=blocks,
            spatial_referents=refs,
            spatial_operations=ops,
            non_manual_spans=spans,
            total_duration_ms=timing.planned_duration_ms,
            validation_summary=validation_summary,
            corrections_applied=[c.to_dict() for c in corrections],
        )
