"""
Planificador Discursivo y Generador de Glosas LSEC (LSEC 2.1.1).

Transforma `SemanticProposition` en secuencias lineales de `GlossItem`,
`SpatialOperation`, `NonManualSpan` y `DiscourseBlock`.

Mantiene el Patrón Fachada para retrocompatibilidad al 100 % de imports en
`nlp_service.py`, `main.py` y `app/tests/`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.schemas import (
    AlignmentType,
    DiscourseBlock,
    FacialExpression,
    GlossItem,
    GlossType,
    InferredConcept,
    InferredConceptOrigin,
    NonManualMarker,
    NonManualSpan,
    RealizedConceptItem,
    RelationType,
    SemanticFrame,
    SemanticProposition,
    SemanticRole,
    SourceConceptItem,
    SpatialLocation,
    SpatialOperation,
    SpatialOperationType,
    SpatialReferent,
    StrategyType,
    TranslationPlan,
)
from app.lsec_grammar.confidence import ConfidenceCalculator, ConfidenceVector
from app.lsec_grammar.conflict_resolver import ConflictResolver
from app.lsec_grammar.registry import get_rule_registry
from app.lsec_grammar.rule_engine import RuleApplication, RuleEngine
from app.services.animation_fingerspelling_service import (
    count_lsec_fingerspelling_graphemes,
    format_lsec_fingerspelling_gloss,
    tokenize_lsec_fingerspelling,
)
from app.services.dictionary_service import (
    LSECDictionaryService,
    STATUS_FINGERSPELLING,
    STATUS_UNVERIFIED,
    get_dictionary_service,
    to_gloss_form,
)
from app.services.discourse_gloss_emitter import (
    emit_glosses_from_reordered_tokens,
    translate_general_heuristic,
    translate_general_spacy,
)
from app.services.discourse_lexicon import (
    DEFAULT_DURATION_MS,
    DEFAULT_QUANTIFIER_LEMMAS,
    DEFAULT_TIME_MARKERS,
    DEFAULT_WH_LEMMAS,
    GRAMMATICAL_FUNCTIONAL_WORDS,
    MWE_CONCEPT_SYNONYMS,
    _BLACKLIST_POS_TAGS,
    _CANONICAL_NOMINAL_FORMS,
    _CANONICAL_SOURCE_LEMMAS,
    _CLITIC_PRONOUNS,
    _CLITIC_VERB_LEMMAS,
    _COPULATIVE_LEMMAS,
    _KNOWN_SIGN_PROPN,
    _NUMBER_HUNDREDS,
    _NUMBER_TENS,
    _NUMBER_UNITS,
    _NUMBER_WORD_EXPANSIONS,
    _NUMBER_WORD_VALUES,
    _QUANTIFIER_CANON,
    _RULE_MANAGED_TOKENS,
    _SEMANTIC_SCONJ_GLOSS,
    _cardinal_sequence,
    _number_words_value,
    _numeric_gloss_sequence,
    _strip_accents_lower,
)
from app.services.discourse_morphosyntax import (
    detect_periphrasis_in_doc,
    has_nominal_context,
    normalize_nominal_lemma,
    sanitize_contextual_glosses,
)
from app.services.discourse_plan_builder import (
    apply_contrastive_pair_loci,
    build_translation_plan_and_block,
    generate_spans_for_prop,
    register_spatial_operations_for_prop,
)
from app.services.discourse_spacy_reorder import (
    detect_dictionary_phrases,
    extract_and_reorder_spacy_tokens,
)
from app.services.fenasec_rules import _INTENSIFIER_RE
from app.services.linguistic_analyzer import LinguisticAnalyzer
from app.services.mwe_detector import MWEDetector, MWEMatch
from app.services.semantic_parser import SpanishVerbLexicon
from app.services.text_normalizer import EntityInfo, PunctuationAnalyzer, contains_negation

logger = logging.getLogger(__name__)


class DiscoursePlanner:
    """
    Planificador de realizaciones discursivas LSEC.
    """

    def __init__(
        self,
        nlp=None,
        institutional_dict: Optional[Dict[str, Dict[str, Any]]] = None,
        lemma_overrides: Optional[Dict[str, str]] = None,
        pronoun_deixis_map: Optional[Dict[str, str]] = None,
        semantic_paraphrases: Optional[Dict[str, Dict[str, Any]]] = None,
        duration_config: Optional[Dict[str, int]] = None,
        entity_registry: Optional[Dict[str, EntityInfo]] = None,
        mwe_detector: Optional[MWEDetector] = None,
        plural_marker: str = "VARIOS",
        dictionary_service: Optional[LSECDictionaryService] = None,
        use_dictionary: Optional[bool] = None,
        named_entities: Optional[Dict[str, Any]] = None,
        fingerspell_oov: bool = False,
    ) -> None:
        self._nlp = nlp
        self._fingerspell_oov = bool(fingerspell_oov)
        self._institutional_dict = institutional_dict or {}
        self._lemma_overrides = lemma_overrides or {}
        self._pronoun_deixis = pronoun_deixis_map or {}
        self._semantic_paraphrases = semantic_paraphrases or {}
        self._named_entities = (
            named_entities if named_entities is not None else self._load_named_entities_from_data()
        )
        self._duration_ms = duration_config or dict(DEFAULT_DURATION_MS)
        self._entity_registry = entity_registry or {}
        self._mwe_detector = mwe_detector or MWEDetector()
        self._plural_marker = plural_marker

        self._quantifier_lemmas: Set[str] = set(DEFAULT_QUANTIFIER_LEMMAS)
        self._wh_lemmas: Set[str] = set(DEFAULT_WH_LEMMAS)
        self._time_markers: Set[str] = set(DEFAULT_TIME_MARKERS)

        # Motor de reglas gramaticales centralizado y analizador lingüístico
        self._rule_registry = get_rule_registry()
        self._rule_engine = RuleEngine()
        self._conflict_resolver = ConflictResolver()
        self._linguistic_analyzer = LinguisticAnalyzer()

        # Diccionario LSEC (CONADIS): fuente de verdad léxica y cascada OOV
        if use_dictionary is None:
            try:
                from app.config import settings
                use_dictionary = bool(settings.lsec_dictionary_enabled)
            except Exception:  # pragma: no cover
                use_dictionary = True
        self._dictionary: Optional[LSECDictionaryService] = None
        if use_dictionary:
            try:
                self._dictionary = dictionary_service or get_dictionary_service()
            except Exception as exc:  # pragma: no cover
                logger.warning("Diccionario LSEC no disponible: %s", exc)
        self._phrase_matching: bool = False
        if self._dictionary is not None:
            try:
                from app.config import settings
                self._phrase_matching = bool(settings.lsec_dictionary_phrase_matching)
            except Exception:  # pragma: no cover
                self._phrase_matching = True
        self._known_local_glosses: Set[str] = self._build_known_local_glosses()

    @staticmethod
    def _has_nominal_context(token: Any) -> bool:
        """Evidencia sintáctica de uso nominal (determinante, adjetivo o numeral)."""
        return has_nominal_context(token)

    @staticmethod
    def _normalize_nominal_lemma(clean_word: str, raw_lemma: str) -> str:
        """Corrige lemas nominales truncados por spaCy."""
        return normalize_nominal_lemma(clean_word, raw_lemma)

    def _build_known_local_glosses(self) -> Set[str]:
        """Glosas ya curadas en el léxico local del proyecto (no se marcan como no verificadas)."""
        known: Set[str] = {self._plural_marker.upper()}
        known.update(m.upper() for m in self._time_markers)
        for info in self._institutional_dict.values():
            g = info.get("gloss") if isinstance(info, dict) else None
            if g:
                known.add(str(g).upper())
        for g in self._pronoun_deixis.values():
            known.add(str(g).upper())
        for target in self._lemma_overrides.values():
            known.add(str(target).upper().replace(" ", "-"))
        for ent in self._entity_registry.values():
            pref = getattr(ent, "preferred_gloss", None)
            if pref:
                known.add(str(pref).upper())
        for d in getattr(self._mwe_detector, "_definitions", []) or []:
            pref = getattr(d, "preferred_gloss", None)
            if pref:
                known.add(str(pref).upper().replace(" ", "-"))
            for realization in getattr(d, "candidate_realizations", None) or []:
                for g in realization:
                    known.add(str(g).upper())
        for para in self._semantic_paraphrases.values():
            if not isinstance(para, dict):
                continue
            for g in para.get("gloss_sequence", []) or []:
                known.add(str(g).upper())
            for seq in (para.get("realizations") or {}).values():
                for g in seq:
                    known.add(str(g).upper())
        return known

    @staticmethod
    def _load_named_entities_from_data() -> Dict[str, Any]:
        """Carga entidades nombradas y asignaciones de loci espaciales desde el lexicón LSEC."""
        for p in (
            Path(__file__).resolve().parent.parent.parent / "data" / "lexicon_lsec.json",
            Path("data/lexicon_lsec.json"),
        ):
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return data.get("named_entities", {})
                except Exception:
                    pass
        return {}

    def _detect_dictionary_phrases(
        self,
        doc,
        source_text: str,
        blocked_token_ids: Set[int],
    ) -> List[Tuple[MWEMatch, Any]]:
        """Detecta entradas de varias palabras del Diccionario LSEC en el documento spaCy."""
        return detect_dictionary_phrases(self, doc, source_text, blocked_token_ids)

    def apply_dictionary(self, glosses: List[GlossItem]) -> Dict[str, int]:
        """
        Cascada léxica sobre las glosas: seña oficial CONADIS -> dactilología/partículas exentas ->
        léxico local curado -> glosa no verificada marcada para revisión nativa (con metadatos de
        respaldo dactilológico o promoción directa cuando `self._fingerspell_oov` está activo).
        """
        if not glosses:
            return {}
        counts: Dict[str, int] = {}
        if self._dictionary is not None:
            try:
                counts = self._dictionary.enrich_glosses(glosses, known_glosses=self._known_local_glosses)
            except Exception as exc:  # pragma: no cover
                logger.warning("Enriquecimiento con diccionario LSEC omitido: %s", exc)
        for g in glosses:
            if g.gloss_type == GlossType.FINGERSPELLING:
                val = dict(g.validation or {})
                tokens = tokenize_lsec_fingerspelling(g.gloss)
                val["is_fingerspelling"] = True
                val["fingerspelling_graphemes"] = [t["grapheme"] for t in tokens]
                g.validation = val
            elif g.dictionary_metadata is not None and g.dictionary_metadata.status == STATUS_UNVERIFIED:
                raw_probe = g.source_word or g.normalized_word or g.gloss
                fs_gloss = format_lsec_fingerspelling_gloss(raw_probe)
                tokens = tokenize_lsec_fingerspelling(fs_gloss)
                val = dict(g.validation or {})
                val["fallback_fingerspelling_gloss"] = fs_gloss
                val["fallback_graphemes"] = [t["grapheme"] for t in tokens]
                g.validation = val
                if self._fingerspell_oov and tokens:
                    g.gloss = fs_gloss
                    g.gloss_type = GlossType.FINGERSPELLING
                    g.duration_ms = self.compute_duration(fs_gloss, GlossType.FINGERSPELLING)
                    g.dictionary_metadata.status = STATUS_FINGERSPELLING
        return counts

    def evaluate_grammar_rules(
        self,
        prop: SemanticProposition,
        *,
        exclude_ids: Optional[Set[str]] = None,
    ) -> Tuple[SemanticFrame, List[RuleApplication], ConfidenceVector]:
        """
        Construye un ``SemanticFrame`` a partir de la proposición y evalúa
        todas las reglas del registro central.
        """
        frame = SemanticFrame.from_proposition(prop)

        if self._nlp is not None:
            doc = self._nlp(prop.source_text)
            ft = self._linguistic_analyzer.analyze_functional_transfer(doc)
            if ft:
                frame.functional_transfers = [
                    f.__dict__ if hasattr(f, "__dict__") else f for f in ft
                ]
            cl = self._linguistic_analyzer.detect_classifiers(doc)
            if cl:
                frame.classifier_candidates = [
                    c.__dict__ if hasattr(c, "__dict__") else c for c in cl
                ]

        all_rules = self._rule_registry.get_executable()
        applications = self._rule_engine.apply_rules(
            all_rules, frame.to_eval_dict(), exclude_ids=exclude_ids
        )

        if len(applications) > 1:
            applied_rule_ids = {a.rule_id for a in applications}
            candidate_rules = [r for r in all_rules if r.rule_id in applied_rule_ids]
            winners, _ = self._conflict_resolver.resolve(candidate_rules)
            winner_ids = {w.rule_id for w in winners}
            applications = [a for a in applications if a.rule_id in winner_ids]

        frame.applied_rule_ids = [a.rule_id for a in applications]

        confidence_vec = ConfidenceCalculator.from_rule_applications(
            applications,
            lexicon_hit_ratio=1.0,
            semantic_coverage=prop.confidence,
            has_coreference=any(
                p.coreference_id is not None for p in prop.participants
            ),
            has_spatial=bool(prop.context_info.get("spatial_entities")),
            has_unresolved=False,
        )

        return frame, applications, confidence_vec

    def compute_duration(
        self,
        gloss_text: str,
        gloss_type: GlossType,
        is_temporal: bool = False,
        is_deixis: bool = False,
        is_plural_marker: bool = False,
    ) -> int:
        """Calcula la duración estimada en ms para una glosa."""
        dur = self._duration_ms
        if is_temporal:
            return dur.get("temporal_marker", 400)
        if is_deixis:
            return dur.get("deixis", 350)
        if is_plural_marker:
            return dur.get("plural_marker", 300)
        if gloss_type == GlossType.FINGERSPELLING:
            clean_chars = count_lsec_fingerspelling_graphemes(gloss_text)
            return max(dur.get("fingerspelling_per_char", 300) * max(clean_chars, 1), 300)

        base = dur.get("sign_base", 500)
        if len(gloss_text) <= 3:
            return dur.get("sign_short", 400)
        elif len(gloss_text) >= 8:
            return dur.get("sign_long", 600)
        return base

    @staticmethod
    def _sanitize_contextual_glosses(
        proposition: SemanticProposition,
        glosses: List[GlossItem],
        start_order: int,
    ) -> List[GlossItem]:
        """Remueve transferencias espurias y conserva el orden semántico de la fuente."""
        return sanitize_contextual_glosses(proposition, glosses, start_order)

    def detect_periphrasis(self, doc) -> List[Tuple[str, str, Set[int]]]:
        """Detecta perífrasis verbales en el doc spaCy."""
        return detect_periphrasis_in_doc(doc)

    def plan_and_generate(
        self,
        propositions: List[SemanticProposition],
        paraphrase_budget: str = "compact",
        *,
        exclude_rule_ids: Optional[Set[str]] = None,
    ) -> Tuple[
        List[GlossItem],
        List[TranslationPlan],
        List[DiscourseBlock],
        List[SpatialReferent],
        List[SpatialOperation],
        List[NonManualSpan],
    ]:
        """
        Planifica y genera la secuencia completa de glosas LSEC para todas las proposiciones.
        """
        all_glosses: List[GlossItem] = []
        all_plans: List[TranslationPlan] = []
        all_blocks: List[DiscourseBlock] = []
        active_referents: Dict[str, SpatialReferent] = {}
        all_referents: List[SpatialReferent] = []
        all_operations: List[SpatialOperation] = []
        all_spans: List[NonManualSpan] = []

        global_order = 0

        for p_idx, prop in enumerate(propositions):
            p_text = prop.source_text.strip()
            p_text_lower = p_text.lower()
            prop_start_order = global_order

            # 1. Determinar estrategia discursiva
            strategy = StrategyType.TOPIC_COMMENT
            if prop.modality == "imperative" or prop.rhetorical_function in ("call_to_action", "imperative"):
                strategy = StrategyType.IMPERATIVE_DIRECT
            elif prop.modality == "reflective" or prop.is_embedded:
                strategy = StrategyType.EMBEDDED_WH_REFLECTIVE
            elif prop.discourse_relation in ("not_only", "also", "but", "more_than") or prop.rhetorical_function == "contrast":
                strategy = StrategyType.CONTRAST_PAIR
            elif prop.rhetorical_function == "enumeration":
                strategy = StrategyType.ENUMERATION_SPATIAL
            elif prop.rhetorical_function == "slogan":
                strategy = StrategyType.SLOGAN_COMPACT
            elif any(k in p_text_lower for k in self._semantic_paraphrases):
                strategy = StrategyType.SEMANTIC_PARAPHRASE

            # 1b. Evaluación de reglas gramaticales centralizadas
            frame, rule_applications, confidence_vec = self.evaluate_grammar_rules(
                prop, exclude_ids=exclude_rule_ids
            )
            active_rule_ids = set(frame.applied_rule_ids)

            # 2. Generación de Glosas LSEC generales con motor lingüístico spaCy
            if self._nlp is not None:
                prop_glosses = self._translate_general_spacy(
                    prop,
                    global_order,
                    active_rule_ids=active_rule_ids,
                    exclude_rule_ids=exclude_rule_ids,
                )
            else:
                prop_glosses = self._translate_general_heuristic(prop, global_order)

            # Ejecutar acciones directas del RuleEngine sobre la secuencia de glosas
            if prop_glosses:
                executable_rules = [
                    r for r in self._rule_registry.get_executable()
                    if r.rule_id in active_rule_ids
                ]
                prop_glosses = self._rule_engine.execute_actions(
                    rules=executable_rules,
                    applications=rule_applications,
                    glosses=prop_glosses,
                    frame=frame.to_eval_dict(),
                    start_order=global_order,
                )

            if not prop_glosses:
                continue

            prop_glosses = self._sanitize_contextual_glosses(
                prop,
                prop_glosses,
                prop_start_order,
            )

            # FENASEC: verbos de movimiento incorporan la dirección; se evita la fuga de 'a'/'al' (HACIA)
            _motion = {
                "ENTRAR", "SALIR", "IR", "LLEGAR", "VENIR", "REGRESAR", "VOLVER",
                "VIAJAR", "CAMINAR", "CORRER", "PARTIR", "SUBIR", "BAJAR",
            }
            if any(g.gloss == "HACIA" for g in prop_glosses) and any(
                g.gloss.rstrip("+") in _motion for g in prop_glosses
            ):
                prop_glosses = [
                    g for g in prop_glosses
                    if not (g.gloss == "HACIA" and (g.source_word or "").lower() in ("a", "al", ""))
                ]
                for k, g in enumerate(prop_glosses):
                    g.order = prop_start_order + k

            # FENASEC: la duplicación (++) subsume el aspecto durativo (AHORA)
            if any(g.gloss.endswith("++") for g in prop_glosses):
                prop_glosses = [
                    g for g in prop_glosses
                    if not (
                        g.gloss == "AHORA"
                        and (g.notes or "").startswith("Insertado por regla LSEC_ASPECT")
                    )
                ]
                for k, g in enumerate(prop_glosses):
                    g.order = prop_start_order + k

            # FENASEC regla 6: pregunta directa seguida de su respuesta => retórica (cejas levantadas)
            _is_q = "?" in p_text or "\u00bf" in p_text
            if _is_q and p_idx + 1 < len(propositions):
                _next_txt = propositions[p_idx + 1].source_text
                if "?" not in _next_txt and "\u00bf" not in _next_txt:
                    prop.context_info["is_rhetorical"] = True
                    for g in prop_glosses:
                        if g.non_manual and g.non_manual.expression in (
                            FacialExpression.QUESTION_WH, FacialExpression.QUESTION_YESNO
                        ):
                            g.non_manual.expression = FacialExpression.RHETORICAL

            # 2c. Diccionario LSEC (CONADIS)
            self.apply_dictionary(prop_glosses)

            # 3. Registrar operaciones espaciales y loci contrastivos
            register_spatial_operations_for_prop(
                planner=self,
                prop_glosses=prop_glosses,
                active_referents=active_referents,
                all_referents=all_referents,
                all_operations=all_operations,
            )
            apply_contrastive_pair_loci(
                prop=prop,
                p_idx=p_idx,
                propositions=propositions,
                all_glosses=all_glosses,
                prop_glosses=prop_glosses,
            )

            all_glosses.extend(prop_glosses)
            global_order += len(prop_glosses)
            prop_end_order = global_order - 1

            # 4. Spans no manuales con alcance sintáctico/discursivo
            prop_spans = self._generate_spans_for_prop(
                prop, prop_glosses, prop_start_order, prop_end_order, p_idx
            )
            all_spans.extend(prop_spans)

            # 5 & 6. TranslationPlan y DiscourseBlock
            prop_glosses, plan, block = build_translation_plan_and_block(
                planner=self,
                prop=prop,
                p_idx=p_idx,
                prop_glosses=prop_glosses,
                prop_spans=prop_spans,
                prop_start_order=prop_start_order,
                prop_end_order=prop_end_order,
                strategy=strategy,
                frame=frame,
                confidence_vec=confidence_vec,
                active_referents=active_referents,
                all_operations=all_operations,
            )
            all_plans.append(plan)
            all_blocks.append(block)

        return (
            all_glosses,
            all_plans,
            all_blocks,
            all_referents,
            all_operations,
            all_spans,
        )

    def _translate_general_spacy(
        self,
        prop: SemanticProposition,
        start_order: int,
        active_rule_ids: Optional[Set[str]] = None,
        exclude_rule_ids: Optional[Set[str]] = None,
    ) -> List[GlossItem]:
        """Traduce una proposición usando spaCy con reglas gramaticales completas."""
        return translate_general_spacy(
            planner=self,
            prop=prop,
            start_order=start_order,
            active_rule_ids=active_rule_ids,
            exclude_rule_ids=exclude_rule_ids,
        )

    def _translate_general_heuristic(
        self,
        prop: SemanticProposition,
        start_order: int,
    ) -> List[GlossItem]:
        """Fallback heurístico directo."""
        return translate_general_heuristic(self, prop, start_order)

    def _generate_spans_for_prop(
        self,
        prop: SemanticProposition,
        glosses: List[GlossItem],
        start_o: int,
        end_o: int,
        p_idx: int,
    ) -> List[NonManualSpan]:
        """Genera spans no manuales para la proposición con alcances sintácticos precisos."""
        return generate_spans_for_prop(self, prop, glosses, start_o, end_o, p_idx)


__all__ = [
    "DiscoursePlanner",
    "SpanishVerbLexicon",
    "PunctuationAnalyzer",
    "contains_negation",
    "EntityInfo",
    "MWEDetector",
    "MWEMatch",
    "LSECDictionaryService",
    "get_dictionary_service",
    "to_gloss_form",
    "_RULE_MANAGED_TOKENS",
    "_strip_accents_lower",
    "_BLACKLIST_POS_TAGS",
    "_COPULATIVE_LEMMAS",
    "_CLITIC_PRONOUNS",
    "_CANONICAL_SOURCE_LEMMAS",
    "_CANONICAL_NOMINAL_FORMS",
    "_SEMANTIC_SCONJ_GLOSS",
    "_CLITIC_VERB_LEMMAS",
    "_QUANTIFIER_CANON",
    "_KNOWN_SIGN_PROPN",
    "_NUMBER_UNITS",
    "_NUMBER_TENS",
    "_NUMBER_HUNDREDS",
    "_NUMBER_WORD_EXPANSIONS",
    "_cardinal_sequence",
    "_numeric_gloss_sequence",
    "_NUMBER_WORD_VALUES",
    "_number_words_value",
    "extract_and_reorder_spacy_tokens",
    "emit_glosses_from_reordered_tokens",
]
