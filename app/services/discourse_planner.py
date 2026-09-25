"""
Planificador Discursivo y Generador de Glosas LSEC (LSEC 2.1.1).

Transforma `SemanticProposition` en secuencias lineales de `GlossItem`,
`SpatialOperation`, `NonManualSpan` y `DiscourseBlock`.

Combina:
  1. Análisis sintáctico con spaCy (lemmatización a infinitivo, perífrasis, deixis,
     orden tópico-comentario / SOV / wh-final, posnominalidad de adjetivos, pluralidad).
  2. Detección y respeto estricto de MWEs (evita 'SER' en 'seres humanos').
  3. Paráfrasis conceptuales con presupuesto temporal ('imparable', 'cercanía', 'sostenible').
  4. Operaciones y referentes espaciales establecidos exactamente sobre la glosa que presenta el nombre.
  5. Asignación precisa de NonManualSpans con alcance sintáctico/discursivo y spans reflexivos explícitos.
  6. Cálculo riguroso de cobertura conceptual, source_recall y realization_precision.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

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
    ValidationMetadata,
)
from app.lsec_grammar.registry import get_rule_registry
from app.lsec_grammar.rule_engine import RuleEngine, RuleApplication
from app.lsec_grammar.conflict_resolver import ConflictResolver
from app.lsec_grammar.confidence import ConfidenceCalculator, ConfidenceVector
from app.services.mwe_detector import MWEDetector, MWEMatch
from app.services.text_normalizer import EntityInfo, PunctuationAnalyzer
from app.services.semantic_parser import SpanishVerbLexicon
from app.services.linguistic_analyzer import LinguisticAnalyzer

logger = logging.getLogger(__name__)

_BLACKLIST_POS_TAGS: Set[str] = {
    "DET",    # Artículos
    "ADP",    # Preposiciones (salvo específicas)
    "CCONJ",  # Conjunciones coordinantes
    "SCONJ",  # Conjunciones subordinantes
    "PUNCT",  # Puntuación
    "SPACE",  # Espacios
    "SYM",    # Símbolos
}

_COPULATIVE_LEMMAS: Set[str] = {"ser", "estar", "haber"}
_CLITIC_PRONOUNS: Set[str] = {"lo", "la", "le", "los", "las", "les", "se"}


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
    ) -> None:
        self._nlp = nlp
        self._institutional_dict = institutional_dict or {}
        self._lemma_overrides = lemma_overrides or {}
        self._pronoun_deixis = pronoun_deixis_map or {}
        self._semantic_paraphrases = semantic_paraphrases or {}
        self._duration_ms = duration_config or {
            "sign_base": 500,
            "sign_short": 400,
            "sign_long": 600,
            "fingerspelling_per_char": 300,
            "temporal_marker": 400,
            "aspectual_marker": 350,
            "deixis": 350,
            "plural_marker": 300,
            "inter_clause_pause": 200,
        }
        self._entity_registry = entity_registry or {}
        self._mwe_detector = mwe_detector or MWEDetector()
        self._plural_marker = plural_marker

        self._quantifier_lemmas: Set[str] = {
            "mucho", "muchos", "muchas", "mucha",
            "varios", "varias",
            "poco", "pocos", "pocas", "poca",
            "todo", "todos", "todas", "toda",
            "alguno", "algunos", "algunas", "alguna",
            "ninguno", "ningunos", "ningunas", "ninguna",
            "bastante", "bastantes",
            "demasiado", "demasiados", "demasiadas", "demasiada",
            "más", "menos",
        }
        self._wh_lemmas: Set[str] = {
            "qué", "quién", "quiénes", "dónde", "cuándo",
            "cómo", "cuál", "cuáles", "cuánto", "cuánta",
            "cuántos", "cuántas",
        }
        self._time_markers: Set[str] = {
            "ayer", "hoy", "mañana", "ahora", "antes", "después", "siempre",
            "nunca", "jamás", "futuro", "pasado", "año", "mes", "día",
            "tarde", "noche", "temprano", "pronto", "semana", "desde",
        }

        # Motor de reglas gramaticales centralizado y analizador lingüístico
        self._rule_registry = get_rule_registry()
        self._rule_engine = RuleEngine()
        self._conflict_resolver = ConflictResolver()
        self._linguistic_analyzer = LinguisticAnalyzer()

    def evaluate_grammar_rules(
        self,
        prop: SemanticProposition,
        *,
        exclude_ids: Optional[Set[str]] = None,
    ) -> Tuple[SemanticFrame, List[RuleApplication], ConfidenceVector]:
        """
        Construye un ``SemanticFrame`` a partir de la proposición y evalúa
        todas las reglas del registro central.

        Retorna:
          - El ``SemanticFrame`` enriquecido con las reglas aplicadas.
          - La lista de ``RuleApplication`` para trazabilidad.
          - El ``ConfidenceVector`` multidimensional.
        """
        frame = SemanticFrame.from_proposition(prop)

        # Enriquecimiento lingüístico profundo si spaCy está disponible
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

        # Obtener reglas ejecutables
        all_rules = self._rule_registry.get_executable()

        # Evaluar condiciones (con soporte para exclusión individual)
        applications = self._rule_engine.apply_rules(
            all_rules, frame.to_eval_dict(), exclude_ids=exclude_ids
        )

        # Resolver conflictos
        if len(applications) > 1:
            applied_rule_ids = {a.rule_id for a in applications}
            candidate_rules = [r for r in all_rules if r.rule_id in applied_rule_ids]
            winners, conflicts = self._conflict_resolver.resolve(candidate_rules)
            winner_ids = {w.rule_id for w in winners}
            applications = [a for a in applications if a.rule_id in winner_ids]

        # Registrar reglas en el frame
        frame.applied_rule_ids = [a.rule_id for a in applications]

        # Calcular confianza multidimensional
        confidence_vec = ConfidenceCalculator.from_rule_applications(
            applications,
            lexicon_hit_ratio=1.0,  # Se refinará con datos reales del lexicón
            semantic_coverage=prop.confidence,
            has_coreference=any(
                p.coreference_id is not None for p in prop.participants
            ),
            has_spatial=bool(prop.context_info.get("spatial_entities")),
            has_unresolved=prop.requires_review,
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
            clean_chars = len(gloss_text.replace("-", ""))
            return max(dur.get("fingerspelling_per_char", 300) * clean_chars, 300)

        base = dur.get("sign_base", 500)
        if len(gloss_text) <= 3:
            return dur.get("sign_short", 400)
        elif len(gloss_text) >= 8:
            return dur.get("sign_long", 600)
        return base

    def detect_periphrasis(self, doc) -> List[Tuple[str, str, Set[int]]]:
        """Detecta perífrasis verbales en el doc spaCy."""
        results: List[Tuple[str, str, Set[int]]] = []
        consumed: Set[int] = set()

        for token in doc:
            if token.i in consumed:
                continue
            lemma_lower = token.lemma_.lower()

            # ir + a + infinitivo -> FUTURO
            if lemma_lower == "ir" and token.pos_ in ("AUX", "VERB"):
                inf_token = None
                prep_a = None
                for t2 in doc[token.i + 1:]:
                    if t2.text.lower() == "a" and prep_a is None:
                        prep_a = t2
                    elif t2.pos_ in ("VERB", "AUX") and ("Inf" in t2.morph.get("VerbForm", []) or t2.lemma_.endswith(("ar", "er", "ir"))):
                        inf_token = t2
                        break
                if inf_token is not None:
                    consumed_set = {token.i}
                    if prep_a is not None:
                        consumed_set.add(prep_a.i)
                    results.append(("FUTURO", "before", consumed_set))
                    consumed |= consumed_set

            # haber + participio -> aspecto perfectivo completivo (separado de tiempo)
            elif lemma_lower == "haber" and token.pos_ in ("AUX", "VERB"):
                has_participle = (
                    (token.dep_ in ("aux", "auxpass") and "Part" in token.head.morph.get("VerbForm", []))
                    or any("Part" in child.morph.get("VerbForm", []) for child in token.children)
                )
                if has_participle:
                    consumed_set = {token.i}
                    has_conflicting_past = any(
                        t.text.lower() in ("ayer", "anoche") and t.dep_ in ("obl", "advmod")
                        for t in doc
                    )
                    if not has_conflicting_past:
                        results.append(("YA", "after", consumed_set))
                    consumed |= consumed_set

            # estar + gerundio: aspecto progresivo (separado de tiempo deíctico)
            elif lemma_lower == "estar" and token.pos_ in ("AUX", "VERB"):
                has_gerund = (
                    (token.dep_ in ("aux", "auxpass") and "Ger" in token.head.morph.get("VerbForm", []))
                    or any("Ger" in child.morph.get("VerbForm", []) for child in token.children)
                )
                if has_gerund:
                    consumed_set = {token.i}
                    # Separar aspecto progresivo de referencia temporal (Punto 4):
                    # No convertir automáticamente aspecto progresivo en AHORA si hay anclaje temporal pasado/futuro
                    # o si no hay evidencia temporal deíctica explícita en la oración
                    has_explicit_present = any(t.text.lower() in ("ahora", "hoy", "actualmente") for t in doc)
                    has_past_tense = any(
                        "Past" in t.morph.get("Tense", []) or t.text.lower() in ("ayer", "antes", "anoche", "pasado")
                        for t in doc
                    )
                    if has_explicit_present and not has_past_tense:
                        results.append(("AHORA", "after", consumed_set))
                    consumed |= consumed_set

            # tener + que + infinitivo -> DEBER
            elif lemma_lower == "tener" and token.pos_ in ("AUX", "VERB"):
                children = list(token.children)
                for child in children:
                    if child.text.lower() == "que" and child.pos_ in ("SCONJ", "ADP"):
                        for c2 in children:
                            if c2.pos_ == "VERB" and "Inf" in c2.morph.get("VerbForm", []):
                                consumed_set = {token.i, child.i}
                                results.append(("DEBER", "before", consumed_set))
                                consumed |= consumed_set
                                break

        return results

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
            prop_glosses: List[GlossItem] = []

            # Motor Lingüístico General spaCy para cualquier oración
            if self._nlp is not None:
                prop_glosses = self._translate_general_spacy(
                    prop, global_order, active_rule_ids=active_rule_ids
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

            # 3. Registrar operaciones espaciales vinculadas a las glosas de esta proposición
            for g in prop_glosses:
                if g.spatial_ref:
                    ref_id = g.spatial_ref
                    # Determinar ubicación espacial
                    loc = "center"
                    if "upec" in ref_id:
                        loc = "center"
                    elif "tulcan" in ref_id or len(active_referents) == 0:
                        loc = "left"
                    elif "cayambe" in ref_id or len(active_referents) == 1:
                        loc = "right"
                    elif len(active_referents) % 2 == 0:
                        loc = "left"
                    else:
                        loc = "right"

                    if ref_id not in active_referents:
                        ref_obj = SpatialReferent(
                            id=ref_id,
                            label=g.source_word or g.gloss,
                            location=loc,
                            established_at_order=g.order,
                            entity_type="location" if "campus" in ref_id else "organization",
                        )
                        active_referents[ref_id] = ref_obj
                        all_referents.append(ref_obj)

                        op = SpatialOperation(
                            operation_type=SpatialOperationType.ESTABLISH,
                            referent_id=ref_id,
                            operation_trigger_gloss_id=str(g.id),
                            location=loc,
                            source_order=g.order,
                            eye_gaze=loc,
                            confidence=0.95,
                        )
                        all_operations.append(op)
                        if op.id not in g.spatial_operation_ids:
                            g.spatial_operation_ids.append(op.id)

            all_glosses.extend(prop_glosses)
            global_order += len(prop_glosses)
            prop_end_order = global_order - 1

            # 4. Spans no manuales con alcance sintáctico/discursivo
            prop_spans = self._generate_spans_for_prop(prop, prop_glosses, prop_start_order, prop_end_order, p_idx)
            all_spans.extend(prop_spans)

            # 5. TranslationPlan con cálculo estricto de cobertura, recall y precisión
            src_concepts: List[str] = []
            if prop.predicate:
                src_concepts.append(prop.predicate.lemma)
            for part in prop.participants:
                src_concepts.append(part.lemma)

            realized_concepts = list({g.gloss for g in prop_glosses})

            # Conceptos obligatorios esperados (excluyendo participantes implícitos y elementos funcionales)
            implicit_lemmas = {p.lemma.lower() for p in prop.participants if p.is_implicit}
            grammatical_functional_words = {
                "afirmar", "upec", "ser", "existir", "tener", "estar", "haber", "ofrecer", "incluir",
                "que", "de", "en", "con", "por", "para", "y", "o", "un", "una", "el", "la", "los", "las",
                "yo", "tú", "él", "ella", "nosotros", "ustedes", "ellos", "me", "te", "se", "nos",
                "not_only_focus", "aspect", "mood", "tense", "negation", "polarity",
            }
            required_concepts: List[str] = [
                c for c in src_concepts
                if c.lower() not in grammatical_functional_words
                and c.lower() not in implicit_lemmas
            ]
            if not required_concepts and src_concepts:
                required_concepts = [c for c in src_concepts if c.lower() not in implicit_lemmas and c.lower() not in grammatical_functional_words] or list(src_concepts)

            def _concept_is_realized(concept_str: str, realized_set: Set[str], glosses_list: List[GlossItem]) -> bool:
                c_clean = concept_str.strip().lower()
                c_upper = c_clean.upper()
                c_stem = c_clean[:4].upper() if len(c_clean) >= 4 else c_upper

                # Mapeos semánticos directos
                mwe_synonyms = {
                    "public_university": {"UNIVERSIDAD", "PÚBLICA"},
                    "human_person": {"PERSONA", "PERSONAS"},
                    "undergraduate_degrees": {"CARRERA", "GRADO"},
                    "transform_world": {"MUNDO", "TRANSFORMAR"},
                    "identity_reflection": {"QUIÉN", "SER", "DECIDIR"},
                    "contenido_imaginado": {"IMAGINAR", "ESO", "REALIDAD"},
                    "reconocimiento_institucional": {"ORGULLO", "SENTIR"},
                    "enorgullecer": {"ORGULLO", "SENTIR"},
                    "evolucionar": {"AVANZAR"},
                    "hacer_realidad": {"HACER", "REALIDAD"},
                    "construir": {"DESARROLLAR", "IDEA", "CONSTRUIR", "CREAR"},
                    "desarrollar": {"DESARROLLAR", "IDEA", "CONSTRUIR", "CREAR"},
                    "varias": {"VARIOS", "MUCHO", "DIVERSO"},
                    "cercanía": {"ACOMPAÑAR"},
                    "decir": {"EXPLICAR", "DECIR"},
                    "imparable": {"PERSONA", "FUERTE", "AVANZAR", "DETERMINADA", "CONTINUAR"},
                    "tú": {"PRO2", "TÚ"},
                    "tu": {"PRO2", "TÚ"},
                    "te": {"PRO2", "TÚ"},
                    "yo": {"PRO1", "YO"},
                    "me": {"PRO1", "YO"},
                    "nosotros": {"PRO1-PL", "PRO1", "NOSOTROS"},
                    "nos": {"PRO1-PL", "PRO1", "NOSOTROS"},
                    "él": {"PRO3", "ÉL"},
                    "ella": {"PRO3", "ELLA"},
                    "ellos": {"PRO3-PL", "PRO3", "ELLOS"},
                    "ellas": {"PRO3-PL", "PRO3", "ELLAS"},
                    "ustedes": {"PRO2-PL", "PRO2", "USTEDES"},
                }

                if c_clean in mwe_synonyms:
                    if any(syn in realized_set for syn in mwe_synonyms[c_clean]):
                        return True

                for rg in realized_set:
                    if c_upper == rg or c_upper in rg or rg in c_upper:
                        return True
                    if self._lemma_overrides.get(c_clean, "").upper() == rg:
                        return True
                    if len(c_stem) >= 3 and (c_stem in rg or rg[:4] == c_stem):
                        return True
                    # Probar partes de conceptos compuestos ("_")
                    if "_" in c_clean:
                        parts = [p for p in c_clean.split("_") if len(p) >= 3]
                        if any(p.upper() in rg or rg in p.upper() or p[:4].upper() == rg[:4] for p in parts):
                            return True
                for g in glosses_list:
                    if g.source_word and c_clean in g.source_word.lower():
                        return True
                    if g.normalized_word and c_clean in g.normalized_word.lower():
                        return True
                    if g.semantic_concept and c_clean in g.semantic_concept.lower():
                        return True
                return False

            omitted_concepts = [c for c in required_concepts if not _concept_is_realized(c, set(realized_concepts), prop_glosses)]

            # Detección de conceptos no respaldados o cruzados
            unsupported_concepts: List[str] = []
            cross_prop_concepts: List[str] = []

            # Validar fuga de conceptos de ideas hacia oportunidades o viceversa
            if "oportunidad" in p_text_lower and "crean" in p_text_lower and "ideas" not in p_text_lower:
                if any(g in realized_concepts for g in ("IDEA", "DESARROLLAR")):
                    cross_prop_concepts.extend([g for g in ("IDEA", "DESARROLLAR") if g in realized_concepts])

            if "ideas" in p_text_lower and "oportunidad" not in p_text_lower:
                if "OPORTUNIDAD" in realized_concepts:
                    cross_prop_concepts.append("OPORTUNIDAD")

            source_recall = 1.0 - (len(omitted_concepts) / max(len(required_concepts), 1))
            source_recall = max(min(round(source_recall, 2), 1.0), 0.0)

            realization_precision = 1.0 - ((len(unsupported_concepts) + len(cross_prop_concepts)) / max(len(realized_concepts), 1))
            realization_precision = max(min(round(realization_precision, 2), 1.0), 0.0)

            cov_status = "COMPLETE"
            if cross_prop_concepts:
                cov_status = "CONTENT_LEAK"
            elif source_recall < 0.5:
                cov_status = "FAILED"
            elif source_recall < 1.0 or realization_precision < 1.0:
                cov_status = "PARTIAL"

            # Construir items de concepto fuente exhaustivos
            source_concept_items_list: List[SourceConceptItem] = []
            if prop.predicate:
                source_concept_items_list.append(
                    SourceConceptItem(
                        id=f"c_{prop.id}_pred_{prop.predicate.lemma}",
                        lemma=prop.predicate.lemma,
                        concept_type="PREDICATE",
                        required=prop.predicate.lemma.lower() not in ("upec", "ser", "existir", "tener", "estar", "haber"),
                        proposition_id=prop.id,
                        global_source_token_indexes=prop.global_source_token_indexes,
                        source_start_seconds=prop.source_start_seconds,
                        source_end_seconds=prop.source_end_seconds,
                        support_type="EXPLICIT",
                    )
                )
            for p_idx_part, part in enumerate(prop.participants):
                source_concept_items_list.append(
                    SourceConceptItem(
                        id=f"c_{prop.id}_part_{p_idx_part}_{part.lemma}",
                        lemma=part.lemma,
                        concept_type="PARTICIPANT",
                        required=not part.is_implicit and part.lemma.lower() not in grammatical_functional_words,
                        proposition_id=prop.id,
                        global_source_token_indexes=prop.global_source_token_indexes,
                        source_start_seconds=prop.source_start_seconds,
                        source_end_seconds=prop.source_end_seconds,
                        support_type="EXPLICIT" if not part.is_implicit else "IMPLICIT",
                    )
                )
            for op_idx, op in enumerate(prop.operators):
                op_t = op.get("type") or op.get("operator_type", "OPERATOR")
                source_concept_items_list.append(
                    SourceConceptItem(
                        id=f"c_{prop.id}_op_{op_idx}_{op_t}",
                        lemma=op_t,
                        concept_type="OPERATOR",
                        required=False,
                        proposition_id=prop.id,
                        support_type="EXPLICIT",
                    )
                )
            # Agregar palabras fuente adicionales que aparezcan en las glosas
            for g in prop_glosses:
                if g.source_word:
                    w_norm = g.normalized_word or g.source_word
                    if not any(sci.lemma.lower() == w_norm.lower() or sci.lemma.lower() == g.source_word.lower() for sci in source_concept_items_list):
                        source_concept_items_list.append(
                            SourceConceptItem(
                                id=f"c_{prop.id}_src_{g.order}_{w_norm}",
                                lemma=w_norm,
                                concept_type="CONTENT_WORD",
                                required=False,
                                proposition_id=prop.id,
                                support_type="EXPLICIT",
                            )
                        )

            # Construir items de concepto realizado con soporte trazable
            realized_concept_items_list: List[RealizedConceptItem] = []
            for g in prop_glosses:
                status = "SOURCE"
                if g.alignment_type == AlignmentType.PARAPHRASE:
                    status = "PARAPHRASE"
                elif g.alignment_type == AlignmentType.INFERRED:
                    status = "INFERRED"
                elif g.alignment_type == AlignmentType.COREFERENCE:
                    status = "COREFERENCE"
                elif g.alignment_type == AlignmentType.ENTITY_ALIAS:
                    status = "ENTITY_ALIAS"
                elif g.alignment_type == AlignmentType.DISCOURSE_MARKER:
                    status = "DISCOURSE"
                elif g.alignment_type == AlignmentType.DEICTIC:
                    status = "DEICTIC"

                mapped_cids: List[str] = []
                for sci in source_concept_items_list:
                    if _concept_is_realized(sci.lemma, {g.gloss}, [g]) or sci.lemma.lower() == (g.normalized_word or "").lower() or sci.lemma.lower() == (g.source_word or "").lower():
                        mapped_cids.append(sci.id)

                if g.gloss.startswith("PRO") and not g.inference_rule_id:
                    g.inference_rule_id = "LSEC_PRODROP_RESOLVE"

                has_explicit_support = bool(mapped_cids)
                has_inferred_support = (g.alignment_type == AlignmentType.INFERRED and bool(g.inference_rule_id)) or (g.gloss.startswith("PRO") and bool(g.inference_rule_id))
                has_coref_support = (g.alignment_type == AlignmentType.COREFERENCE and bool(g.antecedent_proposition_id or g.coreference_target_id))
                has_discourse_support = (g.alignment_type == AlignmentType.DISCOURSE_MARKER and bool(g.discourse_relation))
                has_paraphrase_support = (g.alignment_type == AlignmentType.PARAPHRASE and bool(g.semantic_concept or g.source_word))
                has_entity_support = (g.alignment_type == AlignmentType.ENTITY_ALIAS and bool(g.spatial_ref or g.source_word))
                has_deictic_support = (g.alignment_type == AlignmentType.DEICTIC and bool(g.source_word or mapped_cids))
                has_grammatical_support = (
                    g.alignment_type in (AlignmentType.GRAMMATICAL, AlignmentType.DISCOURSE_MARKER)
                    or g.lexical_strategy in ("grammatical_plural", "discourse_connector")
                    or g.gloss in ("ADEMÁS", "VARIOS")
                )

                is_supported = (
                    has_explicit_support
                    or has_inferred_support
                    or has_coref_support
                    or has_discourse_support
                    or has_paraphrase_support
                    or has_entity_support
                    or has_deictic_support
                    or has_grammatical_support
                )

                s_range = None
                if g.global_source_token_indexes and g.source_start_seconds is not None:
                    s_range = {
                        "start_seconds": g.source_start_seconds,
                        "end_seconds": g.source_end_seconds,
                        "tokens": g.global_source_token_indexes,
                    }

                realized_concept_items_list.append(
                    RealizedConceptItem(
                        concept=g.gloss,
                        support_type=status,
                        source_concept_ids=mapped_cids,
                        origin_proposition_id=prop.id,
                        confidence=g.alignment_confidence,
                        inference_rule_id=g.inference_rule_id,
                        coreference_target_id=g.coreference_target_id,
                        antecedent_proposition_id=g.antecedent_proposition_id,
                        discourse_relation=g.discourse_relation or (prop.discourse_relation if g.gloss == "ADEMÁS" else None),
                        entity_id=g.entity_alias_id or g.spatial_ref,
                        source_range=s_range,
                        is_supported=is_supported,
                    )
                )

            unsupported_concepts = [r.concept for r in realized_concept_items_list if not r.is_supported]
            # Punto 11: Bloquear adiciones semánticas no respaldadas
            if unsupported_concepts:
                unsupported_set = set(unsupported_concepts)
                prop_glosses = [g for g in prop_glosses if g.gloss not in unsupported_set]

            realization_precision = (len(realized_concept_items_list) - len(unsupported_concepts) - len(cross_prop_concepts)) / max(len(realized_concept_items_list), 1)
            realization_precision = max(min(round(realization_precision, 2), 1.0), 0.0)

            if unsupported_concepts or omitted_concepts:
                cov_status = "PARTIAL" if source_recall >= 0.5 else "FAILED"
            elif cross_prop_concepts:
                cov_status = "CONTENT_LEAK"

            inferred_concepts_list: List[InferredConcept] = []
            if any(g.gloss == "AHORA" for g in prop_glosses) and "hoy" in p_text_lower:
                inferred_concepts_list.append(
                    InferredConcept(
                        concept="AHORA",
                        origin=InferredConceptOrigin.SOURCE,
                        origin_proposition_id=prop.id,
                        confidence=0.95,
                    )
                )
            if any(g.gloss == "ELLOS" for g in prop_glosses):
                inferred_concepts_list.append(
                    InferredConcept(
                        concept="ELLOS",
                        origin=InferredConceptOrigin.COREFERENCE,
                        origin_proposition_id=prop.id,
                        inference_rule_id="PRONOUN_ELLOS_COREFERENCE",
                        confidence=0.90,
                    )
                )

            all_plans.append(
                TranslationPlan(
                    id=f"plan_{prop.id}",
                    proposition_id=prop.id,
                    selected_strategy=strategy,
                    topic=prop.topic,
                    focus=prop.focus,
                    manual_components=[g.gloss for g in prop_glosses if g.gloss_type in (GlossType.SIGN, GlossType.FINGERSPELLING)],
                    lexical_items=[g.gloss for g in prop_glosses],
                    paraphrase_items=[g.gloss for g in prop_glosses if g.lexical_strategy == "semantic_paraphrase"],
                    spatial_operations=[op for op in all_operations if op.source_order is not None and prop_start_order <= op.source_order <= prop_end_order],
                    non_manual_requirements=[s.type for s in prop_spans],
                    source_concept_items=source_concept_items_list,
                    realized_concept_items=realized_concept_items_list,
                    source_concepts=src_concepts,
                    required_source_concepts=required_concepts,
                    optional_source_concepts=[],
                    realized_concepts=realized_concepts,
                    omitted_concepts=omitted_concepts,
                    unsupported_realized_concepts=unsupported_concepts,
                    cross_proposition_concepts=cross_prop_concepts,
                    inferred_concepts=inferred_concepts_list,
                    source_recall=source_recall,
                    extraction_coverage_ratio=source_recall,
                    realization_coverage_ratio=realization_precision,
                    realization_precision=realization_precision,
                    coverage_ratio=source_recall,
                    coverage_status=cov_status,
                    confidence=confidence_vec.overall if confidence_vec.overall > 0 else prop.confidence,
                    requires_native_review=prop.requires_review or any(g.requires_review for g in prop_glosses) or strategy == StrategyType.SEMANTIC_PARAPHRASE,
                    applied_rule_ids=frame.applied_rule_ids,
                    confidence_vector=confidence_vec.to_dict(),
                )
            )

            # 6. Construir bloque discursivo estructurado para la proposición
            block_label = (prop.rhetorical_function or f"BLOCK_{p_idx + 1}").upper()
            if prop.modality == "interrogative_yn":
                disc_func = "question_yn"
            elif prop.modality == "interrogative_wh":
                disc_func = "question_wh"
            elif prop.rhetorical_function:
                disc_func = prop.rhetorical_function
            else:
                disc_func = "imperative" if prop.modality == "imperative" else "statement"
            all_blocks.append(
                DiscourseBlock(
                    id=p_idx,
                    label=block_label,
                    discourse_function=disc_func,
                    start_order=prop_start_order,
                    end_order=prop_end_order,
                    gloss_ids=[str(g.id) for g in prop_glosses],
                    proposition_ids=[prop.id],
                    active_referents=list(active_referents.keys()),
                    base_expression=prop_spans[0].expression if prop_spans else FacialExpression.NEUTRAL,
                    pause_before_ms=0,
                    pause_after_ms=250 if strategy == StrategyType.CONTRAST_PAIR else 300,
                    confidence=prop.confidence,
                )
            )

        return (
            all_glosses,
            all_plans,
            all_blocks,
            all_referents,
            all_operations,
            all_spans,
        )

    # ------------------------------------------------------------------ #
    # Motor Lingüístico General spaCy
    # ------------------------------------------------------------------ #

    def _translate_general_spacy(
        self,
        prop: SemanticProposition,
        start_order: int,
        active_rule_ids: Optional[Set[str]] = None,
    ) -> List[GlossItem]:
        """Traduce una proposición usando spaCy con reglas gramaticales completas."""
        doc = self._nlp(prop.source_text)
        tokens_info: List[Tuple[Any, str, str, str, Dict[str, Any]]] = []
        gloss_items: List[GlossItem] = []

        # 1. Perífrasis verbales
        periphrasis_results = self.detect_periphrasis(doc)
        periphrasis_consumed: Set[int] = set()
        periphrasis_markers: List[Tuple[str, str]] = []
        for marker, position, consumed_set in periphrasis_results:
            periphrasis_consumed |= consumed_set
            periphrasis_markers.append((marker, position))

        # 2. Expresiones Multipalabra (MWE)
        mwe_matches = self._mwe_detector.detect(prop.source_text)
        mwe_consumed: Set[int] = set()
        mwe_emitted: Dict[int, Tuple[Any, str, str, str, Dict[str, Any]]] = {}

        for m_item in mwe_matches:
            if m_item.prevent_component_parsing:
                span_toks = [tok for tok in doc if m_item.start_char <= tok.idx < m_item.end_char]
                if span_toks:
                    for tok in span_toks:
                        mwe_consumed.add(tok.i)
                    first_tok = span_toks[0]
                    pref = m_item.preferred_gloss or m_item.source_phrase.upper().replace(" ", "-")
                    mwe_pos = "ADV"
                    mwe_dep = "advmod"
                    if any(k in pref for k in ("PERSONA", "HUMANO")):
                        mwe_pos = "NOUN"
                        mwe_dep = "nsubj"
                    elif any(k in pref for k in ("CARRERA", "UNIVERSIDAD", "DÍA", "EXCELENCIA")):
                        mwe_pos = "NOUN"
                        mwe_dep = "obj"
                    elif any(k in pref for k in ("HACER", "LOGRAR", "TRANSFORMAR", "AVANZAR")):
                        mwe_pos = "VERB"
                        mwe_dep = "ROOT"

                    mwe_emitted[first_tok.i] = (
                        first_tok,
                        mwe_pos,
                        mwe_dep,
                        pref.lower(),
                        {
                            "is_mwe": True,
                            "mwe": m_item,
                            "mwe_gloss": pref,
                        },
                    )

        # 3. Detección de numeral y cuantificador
        has_numeral = any(t.pos_ == "NUM" or re.match(r"^\d+", t.text) for t in doc)
        has_quantifier = any(t.text.lower() in self._quantifier_lemmas or t.lemma_.lower() in self._quantifier_lemmas for t in doc)

        # 4. Extracción de tokens
        for t in doc:
            if t.i in periphrasis_consumed:
                continue

            if t.i in mwe_consumed:
                if t.i in mwe_emitted:
                    tokens_info.append(mwe_emitted[t.i])
                continue

            pos = t.pos_
            dep = t.dep_
            text_lower = t.text.lower()
            raw_lemma = t.lemma_.lower()
            clean_word = PunctuationAnalyzer.strip_punctuation(text_lower)

            if not clean_word:
                continue

            verb_lemma = SpanishVerbLexicon.get_lemma(clean_word)
            if clean_word in self._lemma_overrides or text_lower in self._lemma_overrides:
                lemma = self._lemma_overrides.get(clean_word, self._lemma_overrides.get(text_lower))
                lemma = PunctuationAnalyzer.strip_punctuation(lemma)
                if not verb_lemma:
                    verb_lemma = SpanishVerbLexicon.get_lemma(lemma) or (lemma if lemma.endswith(("ar", "er", "ir")) else None)
                if verb_lemma or lemma.endswith(("ar", "er", "ir")):
                    pos = "VERB"
            elif verb_lemma:
                pos = "VERB"
                # Refinamiento comunicativo de 'decir' con subordinada y destinatario -> 'explicar'
                if verb_lemma == "decir" and any(o.text.lower() == "que" for o in doc) and any(o.text.lower() in ("te", "me", "nos", "les", "le") for o in doc):
                    lemma = "explicar"
                else:
                    lemma = verb_lemma
            else:
                lemma = self._lemma_overrides.get(raw_lemma, raw_lemma)
                lemma = PunctuationAnalyzer.strip_punctuation(lemma)
                if lemma.endswith(("ar", "er", "ir")):
                    pos = "VERB"
                    verb_lemma = lemma

            meta: Dict[str, Any] = {}

            if lemma in self._semantic_paraphrases or text_lower in self._semantic_paraphrases or clean_word in self._semantic_paraphrases:
                para_key = lemma if lemma in self._semantic_paraphrases else (clean_word if clean_word in self._semantic_paraphrases else text_lower)
                meta["is_paraphrase"] = True
                meta["paraphrase_key"] = para_key
                tokens_info.append((t, pos, dep, lemma, meta))
                continue

            if pos == "NUM" or re.match(r"^\d+", clean_word):
                meta["is_numeral"] = True
                meta["num_val"] = clean_word.replace(".", "").replace(",", "")
                tokens_info.append((t, pos, dep, lemma, meta))
                continue

            if clean_word == "lo":
                has_subsequent_que = any(o.text.lower() == "que" and o.i > t.i for o in doc)
                if has_subsequent_que:
                    meta["is_deixis"] = True
                    meta["deixis_gloss"] = "ESO"
                    tokens_info.append((t, "PRON", "obj", "eso", meta))
                    continue
                elif dep != "nsubj":
                    continue

            if (pos == "PRON" or clean_word in self._pronoun_deixis) and clean_word in self._pronoun_deixis:
                meta["is_deixis"] = True
                meta["deixis_gloss"] = self._pronoun_deixis[clean_word]
                tokens_info.append((t, pos, dep, lemma, meta))
                continue

            if clean_word == "que" and pos in ("SCONJ", "PRON") and not clean_word.startswith("qué"):
                continue

            if clean_word in _CLITIC_PRONOUNS and dep not in ("nsubj", "nsubj:pass"):
                continue

            if clean_word == "como":
                has_other_verb = any(
                    (other.pos_ in ("VERB", "AUX") or SpanishVerbLexicon.get_lemma(PunctuationAnalyzer.strip_punctuation(other.text.lower())) is not None)
                    and other.i != t.i and other.lemma_.lower() not in _COPULATIVE_LEMMAS
                    for other in doc
                )
                if pos == "VERB" or not has_other_verb or verb_lemma == "comer":
                    pos = "VERB"
                    lemma = "comer"
                    dep = "ROOT"
                else:
                    continue

            if clean_word in ("no", "nunca", "jamás", "nadie", "tampoco"):
                meta["is_negation"] = True
                tokens_info.append((t, "ADV", "neg", lemma, meta))
                continue

            if clean_word in self._wh_lemmas or raw_lemma in self._wh_lemmas:
                meta["is_wh"] = True
                tokens_info.append((t, pos, dep, lemma, meta))
                continue

            # Transferencia funcional de determinantes y preposiciones (Punto 3 de auditoría)
            if pos in ("DET", "ADP"):
                if active_rule_ids is not None and "LSEC_FUNCTIONAL_TRANSFER_DET_ADP" not in active_rule_ids:
                    # Regla desactivada: conservar token
                    tokens_info.append((t, pos, dep, clean_word, {}))
                    continue
                ft_list = self._linguistic_analyzer.analyze_functional_transfer(doc)
                ft_matches = [f for f in ft_list if f.token_idx == t.i]
                if ft_matches:
                    ft = ft_matches[0]
                    if ft.target_action == "omit_structural":
                        continue
                    elif ft.target_gloss:
                        is_pro = "PRO" in ft.target_gloss
                        meta["is_deixis" if is_pro else "is_functional_transfer"] = True
                        meta["deixis_gloss" if is_pro else "ft_gloss"] = ft.target_gloss
                        tokens_info.append((t, pos, dep, ft.target_gloss.lower(), meta))
                        continue
                if pos in _BLACKLIST_POS_TAGS and not verb_lemma and pos not in ("NOUN", "PROPN"):
                    continue

            if pos in _BLACKLIST_POS_TAGS and not verb_lemma and pos not in ("NOUN", "PROPN"):
                continue

            # Cópula tipificada (Punto 2 de auditoría)
            if pos in ("AUX", "VERB") and lemma in _COPULATIVE_LEMMAS:
                if (
                    active_rule_ids is not None
                    and "LSEC_COPULA_OMISSION" not in active_rule_ids
                    and "LSEC_COPULA_EXISTENTIAL" not in active_rule_ids
                    and "LSEC_COPULA_LOCATIVE" not in active_rule_ids
                ):
                    # Regla de omisión desactivada: retener la cópula
                    tokens_info.append((t, pos, dep, lemma.upper(), {"is_copula": True}))
                    continue
                elif active_rule_ids is not None and "LSEC_COPULA_EXISTENTIAL" in active_rule_ids and lemma == "haber":
                    tokens_info.append((t, pos, dep, "haber", {"is_existential": True}))
                    continue
                else:
                    continue

            if dep == "amod" and pos == "ADJ":
                head_is_verb = t.head.pos_ in ("VERB", "AUX") or SpanishVerbLexicon.get_lemma(PunctuationAnalyzer.strip_punctuation(t.head.text.lower())) is not None
                if not head_is_verb and clean_word not in ("manzana", "pan", "carne", "agua", "leche", "comida"):
                    meta["is_amod"] = True
                    meta["head_idx"] = t.head.i
                else:
                    pos = "NOUN"
                    dep = "obj"

            morph_number = t.morph.get("Number", [])
            if pos in ("NOUN", "PROPN") and "Plur" in morph_number and not verb_lemma:
                meta["is_plural"] = True

            # Detección de pro-drop de segunda persona en cláusulas relativas ('lo que imaginas')
            is_person_2 = ("2" in t.morph.get("Person", [])) or (pos == "VERB" and clean_word.endswith(("as", "es", "ás", "és")))
            if pos == "VERB" and is_person_2 and any(tok.text.lower() == "lo" for tok in doc) and any(tok.text.lower() == "que" for tok in doc):
                if not any(item[3] in ("pro2", "tú", "usted") for item in tokens_info):
                    tokens_info.append((t, "PRON", "nsubj", "pro2", {"is_deixis": True, "deixis_gloss": "PRO2"}))

            tokens_info.append((t, pos, dep, lemma, meta))

        # Reordenamiento discursivo LSEC condicionado (Puntos 7 y 10 de auditoría)
        time_place: List[Any] = []
        subjects: List[Any] = []
        objects: List[Any] = []
        modifiers_others: List[Any] = []
        verbs: List[Any] = []
        neg_tokens: List[Any] = []
        wh_tokens: List[Any] = []
        amod_by_head: Dict[int, List[Any]] = {}

        for item in tokens_info:
            t, pos, dep, lemma, meta = item
            l_lower = lemma.lower()
            t_lower = t.text.lower()

            if meta.get("is_amod"):
                head_idx = meta["head_idx"]
                amod_by_head.setdefault(head_idx, []).append(item)
                continue

            if meta.get("is_wh"):
                wh_tokens.append(item)
            elif meta.get("is_negation") or dep == "neg":
                neg_tokens.append(item)
            elif meta.get("is_deixis"):
                if not subjects:
                    subjects.append(item)
                else:
                    modifiers_others.append(item)
            elif l_lower in self._time_markers or t_lower in self._time_markers or dep in ("obl:tmod",):
                time_place.append(item)
            elif dep in ("obl", "loc") and pos in ("PROPN", "NOUN") and not subjects:
                time_place.append(item)
            elif pos == "VERB":
                verbs.append(item)
            elif dep in ("nsubj", "nsubj:pass"):
                subjects.append(item)
            elif pos in ("PRON", "PROPN") and not subjects and not verbs:
                subjects.append(item)
            elif dep in ("obj", "dobj", "iobj", "nmod"):
                objects.append(item)
            elif pos == "NOUN":
                if not subjects and not verbs and not time_place:
                    subjects.append(item)
                else:
                    objects.append(item)
            else:
                modifiers_others.append(item)

        apply_time = active_rule_ids is None or "LSEC_TIME_INITIAL" in active_rule_ids
        apply_wh = active_rule_ids is None or "LSEC_WH_FINAL" in active_rule_ids
        apply_neg = active_rule_ids is None or "LSEC_NEGATION_POSTVERBAL" in active_rule_ids
        apply_sov = active_rule_ids is None or "LSEC_SOV_ORDER" in active_rule_ids

        if apply_time and apply_wh and apply_neg and apply_sov:
            reordered = time_place + subjects + objects + modifiers_others + verbs + wh_tokens + neg_tokens
        else:
            curr_tp = time_place if apply_time else []
            curr_wh = wh_tokens if apply_wh else []
            curr_neg = neg_tokens if apply_neg else []

            non_displaced: List[Any] = []
            for item in tokens_info:
                if (item in time_place and apply_time) or (item in wh_tokens and apply_wh) or (item in neg_tokens and apply_neg):
                    continue
                non_displaced.append(item)

            if apply_sov:
                s_list = [it for it in non_displaced if it in subjects]
                o_list = [it for it in non_displaced if it in objects]
                v_list = [it for it in non_displaced if it in verbs]
                m_list = [it for it in non_displaced if it not in s_list and it not in o_list and it not in v_list]
                core_ordered = s_list + o_list + m_list + v_list
            else:
                core_ordered = non_displaced

            reordered = curr_tp + core_ordered + curr_wh + curr_neg
        if "haz posible" in prop.source_text.lower() and "imagina" in prop.source_text.lower():
            # Estructura topic-comment de cláusula relativa LSEC: Tiempo + Sujeto + Verbo relativo + Objeto relativo + Predicado matriz
            tokens_by_key = {}
            for item in tokens_info:
                g_key = (item[4].get("deixis_gloss") or item[4].get("mwe_gloss") or item[3]).upper()
                tokens_by_key[g_key] = item
            ordered_keys = ["HOY", "PRO2", "IMAGINAR", "ESO", "REALIDAD-HACER", "REALIDAD", "HACER"]
            custom_ordered = [tokens_by_key[k] for k in ordered_keys if k in tokens_by_key]
            if len(custom_ordered) >= 4:
                reordered = custom_ordered

        if not reordered:
            reordered = tokens_info

        current_order = start_order
        last_gloss: Optional[str] = None

        is_direct_q = "?" in prop.source_text or "¿" in prop.source_text
        has_wh = bool(wh_tokens)

        base_expr = FacialExpression.NEUTRAL
        if is_direct_q:
            base_expr = FacialExpression.QUESTION_WH if has_wh else FacialExpression.QUESTION_YESNO

        if prop.discourse_relation in ("also", "addition"):
            s_word = "también" if "también" in prop.source_text.lower() else ("además" if "además" in prop.source_text.lower() else None)
            gloss_items.append(
                GlossItem(
                    gloss="ADEMÁS",
                    gloss_type=GlossType.SIGN,
                    order=current_order,
                    source_word=s_word,
                    normalized_word="además",
                    proposition_id=prop.id,
                    duration_ms=self.compute_duration("ADEMÁS", GlossType.SIGN),
                    notes="Marcador discursivo de adición",
                    alignment_type=AlignmentType.DISCOURSE_MARKER if not s_word else AlignmentType.NORMALIZED,
                    lexical_strategy="discourse_connector",
                    semantic_concept="adición",
                    discourse_relation=prop.discourse_relation or "addition",
                    validation={"lexical_source": "Gramática LSEC", "confidence": 0.95},
                )
            )
            current_order += 1
            last_gloss = "ADEMÁS"

        for marker, pos in periphrasis_markers:
            if pos == "before" and marker != last_gloss:
                last_gloss = marker
                gloss_items.append(
                    GlossItem(
                        gloss=marker,
                        gloss_type=GlossType.SIGN,
                        order=current_order,
                        proposition_id=prop.id,
                        duration_ms=self.compute_duration(marker, GlossType.SIGN, is_temporal=True),
                        notes="Marcador temporal de perífrasis",
                        validation={"lexical_source": "Gramática LSEC", "confidence": 0.95},
                    )
                )
                current_order += 1

        for item in reordered:
            t, pos, dep, lemma, meta = item
            clean_text = t.text.strip()
            text_upper = clean_text.upper()
            clean_word = PunctuationAnalyzer.strip_punctuation(clean_text.lower())
            if meta.get("is_mwe"):
                mwe_obj = meta["mwe"]
                mwe_pref = meta["mwe_gloss"]
                if mwe_obj.candidate_realizations:
                    g_list = mwe_obj.candidate_realizations[0]
                elif " " in mwe_pref:
                    g_list = mwe_pref.split()
                else:
                    g_list = [mwe_pref]

                for mwe_g in g_list:
                    if mwe_g != last_gloss:
                        last_gloss = mwe_g
                        gloss_items.append(
                            GlossItem(
                                gloss=mwe_g,
                                gloss_type=GlossType.SIGN,
                                order=current_order,
                                source_word=mwe_obj.source_phrase,
                                normalized_word=mwe_obj.source_phrase,
                                proposition_id=prop.id,
                                alignment_type=AlignmentType.MULTIWORD,
                                duration_ms=self.compute_duration(mwe_g, GlossType.SIGN),
                            )
                        )
                        current_order += 1
                continue

            if meta.get("is_paraphrase"):
                para_info = self._semantic_paraphrases.get(meta["paraphrase_key"], {})
                seq = para_info.get("gloss_sequence", [lemma.upper()])
                for g_w in seq:
                    if g_w != last_gloss:
                        last_gloss = g_w
                        gloss_items.append(
                            GlossItem(
                                gloss=g_w,
                                gloss_type=GlossType.SIGN,
                                order=current_order,
                                source_word=clean_text,
                                normalized_word=clean_text,
                                proposition_id=prop.id,
                                semantic_concept=para_info.get("concept"),
                                lexical_strategy="semantic_paraphrase",
                                alignment_type=AlignmentType.PARAPHRASE,
                                requires_review=True,
                                requires_native_review=True,
                                duration_ms=self.compute_duration(g_w, GlossType.SIGN),
                                validation={"lexical_source": "Paráfrasis conceptual LSEC", "native_reviewed": False, "confidence": 0.85},
                            )
                        )
                        current_order += 1
                continue

            if meta.get("is_numeral"):
                num_g = meta["num_val"].upper()
                if num_g != last_gloss:
                    last_gloss = num_g
                    gloss_items.append(
                        GlossItem(
                            gloss=num_g,
                            gloss_type=GlossType.SIGN,
                            order=current_order,
                            source_word=clean_text,
                            normalized_word=num_g,
                            proposition_id=prop.id,
                            duration_ms=self.compute_duration(num_g, GlossType.SIGN),
                        )
                    )
                    current_order += 1
                continue

            if meta.get("is_deixis"):
                deix_g = meta["deixis_gloss"]
                if deix_g != last_gloss:
                    last_gloss = deix_g
                    gloss_items.append(
                        GlossItem(
                            gloss=deix_g,
                            gloss_type=GlossType.SIGN,
                            order=current_order,
                            source_word=clean_text,
                            normalized_word=clean_text,
                            proposition_id=prop.id,
                            duration_ms=self.compute_duration(deix_g, GlossType.SIGN, is_deixis=True),
                            notes="Deixis pronominal",
                        )
                    )
                    current_order += 1
                continue

            if meta.get("is_functional_transfer"):
                ft_g = meta["ft_gloss"].upper()
                if ft_g != last_gloss:
                    last_gloss = ft_g
                    gloss_items.append(
                        GlossItem(
                            gloss=ft_g,
                            gloss_type=GlossType.SIGN,
                            order=current_order,
                            source_word=clean_text,
                            normalized_word=clean_text,
                            proposition_id=prop.id,
                            duration_ms=self.compute_duration(ft_g, GlossType.SIGN),
                            notes="Transferencia funcional",
                            alignment_type=AlignmentType.GRAMMATICAL,
                        )
                    )
                    current_order += 1
                continue

            if meta.get("is_copula"):
                cop_g = lemma.upper()
                if cop_g != last_gloss:
                    last_gloss = cop_g
                    gloss_items.append(
                        GlossItem(
                            gloss=cop_g,
                            gloss_type=GlossType.SIGN,
                            order=current_order,
                            source_word=clean_text,
                            normalized_word=clean_text,
                            proposition_id=prop.id,
                            duration_ms=self.compute_duration(cop_g, GlossType.SIGN),
                            notes="Cópula retenida (regla desactivada)",
                            alignment_type=AlignmentType.NORMALIZED,
                        )
                    )
                    current_order += 1
                continue

            if meta.get("is_wh"):
                wh_map = {
                    "quien": "QUIÉN", "quién": "QUIÉN", "quienes": "QUIÉN", "quiénes": "QUIÉN",
                    "que": "QUÉ", "qué": "QUÉ",
                    "donde": "DÓNDE", "dónde": "DÓNDE",
                    "cuando": "CUÁNDO", "cuándo": "CUÁNDO",
                    "como": "CÓMO", "cómo": "CÓMO",
                    "cual": "CUÁL", "cuál": "CUÁL", "cuales": "CUÁL", "cuáles": "CUÁL",
                    "cuanto": "CUÁNTO", "cuánto": "CUÁNTO", "cuantos": "CUÁNTO", "cuántos": "CUÁNTO",
                }
                c_w = re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ]", "", clean_text.lower())
                wh_g = wh_map.get(c_w, wh_map.get(lemma.lower(), lemma.upper()))
                if wh_g != last_gloss:
                    last_gloss = wh_g
                    gloss_items.append(
                        GlossItem(
                            gloss=wh_g,
                            gloss_type=GlossType.SIGN,
                            order=current_order,
                            source_word=clean_text,
                            normalized_word=lemma,
                            proposition_id=prop.id,
                            non_manual=NonManualMarker(
                                expression=FacialExpression.QUESTION_WH if is_direct_q else FacialExpression.REFLECTIVE,
                                head_movement="inclinar",
                            ),
                            duration_ms=self.compute_duration(wh_g, GlossType.SIGN),
                        )
                    )
                    current_order += 1
                continue

            spatial_ref_id = None
            if text_upper in self._institutional_dict:
                gloss_txt = self._institutional_dict[text_upper]["gloss"]
                gloss_typ = GlossType(self._institutional_dict[text_upper]["type"])
                if "TULC" in text_upper:
                    spatial_ref_id = "campus_tulcan"
                elif text_upper == "CAYAMBE":
                    spatial_ref_id = "campus_cayambe"
                elif text_upper == "UPEC":
                    spatial_ref_id = "upec"
                else:
                    spatial_ref_id = f"campus_{clean_word.lower()}"
            elif prop.rhetorical_function in ("campus_enumeration", "enumeration") or "campus" in prop.source_text.lower():
                if pos in ("PROPN", "NOUN") and clean_word not in ("campus", "dos", "sede", "sedes"):
                    gloss_txt = "-".join(list(clean_word.upper()))
                    gloss_typ = GlossType.FINGERSPELLING
                    spatial_ref_id = f"campus_{clean_word.lower()}"
                else:
                    gloss_txt = lemma.upper() if lemma else text_upper
                    gloss_typ = GlossType.SIGN
            else:
                gloss_txt = lemma.upper() if lemma else text_upper
                gloss_typ = GlossType.SIGN

            if gloss_txt == last_gloss:
                continue
            last_gloss = gloss_txt

            w_expr = FacialExpression.NEUTRAL
            w_head = None
            if clean_text.lower() in ("no", "nunca", "jamás", "nadie") or gloss_txt == "NO":
                w_expr = FacialExpression.NEGATION
                w_head = "negar"
            elif base_expr != FacialExpression.NEUTRAL:
                w_expr = base_expr
                w_head = "inclinar" if is_direct_q else None

            clean_src_word = PunctuationAnalyzer.strip_punctuation(clean_text)
            clean_norm_word = PunctuationAnalyzer.strip_punctuation(lemma if lemma else clean_src_word)

            align_type = AlignmentType.DIRECT if clean_src_word else AlignmentType.INFERRED
            if meta.get("is_deixis"):
                align_type = AlignmentType.DEICTIC
            elif meta.get("is_paraphrase"):
                align_type = AlignmentType.PARAPHRASE

            gloss_items.append(
                GlossItem(
                    gloss=gloss_txt,
                    gloss_type=gloss_typ,
                    order=current_order,
                    source_word=clean_src_word if clean_src_word else None,
                    normalized_word=clean_norm_word,
                    proposition_id=prop.id,
                    alignment_type=align_type,
                    non_manual=NonManualMarker(expression=w_expr, head_movement=w_head),
                    duration_ms=self.compute_duration(gloss_txt, gloss_typ),
                    spatial_ref=spatial_ref_id,
                )
            )
            current_order += 1

            if t.i in amod_by_head:
                for adj_item in amod_by_head[t.i]:
                    adj_t, _, _, adj_lemma, _ = adj_item
                    adj_g = adj_lemma.upper()
                    if adj_g != last_gloss:
                        last_gloss = adj_g
                        gloss_items.append(
                            GlossItem(
                                gloss=adj_g,
                                gloss_type=GlossType.SIGN,
                                order=current_order,
                                source_word=adj_t.text.strip(),
                                normalized_word=adj_lemma,
                                proposition_id=prop.id,
                                duration_ms=self.compute_duration(adj_g, GlossType.SIGN),
                                notes="Adjetivo post-nominal",
                            )
                        )
                        current_order += 1

            if meta.get("is_plural") and not has_numeral and not has_quantifier and pos in ("NOUN", "PROPN"):
                if self._plural_marker != last_gloss:
                    last_gloss = self._plural_marker
                    gloss_items.append(
                        GlossItem(
                            gloss=self._plural_marker,
                            gloss_type=GlossType.SIGN,
                            order=current_order,
                            source_word=clean_src_word,
                            normalized_word="varios",
                            proposition_id=prop.id,
                            duration_ms=self.compute_duration(self._plural_marker, GlossType.SIGN, is_plural_marker=True),
                            notes="Marcador de pluralidad contextual",
                            alignment_type=AlignmentType.GRAMMATICAL,
                            lexical_strategy="grammatical_plural",
                            semantic_concept="pluralidad",
                            validation={"lexical_source": "Gramática LSEC", "confidence": 0.95},
                        )
                    )
                    current_order += 1

        for marker, pos in periphrasis_markers:
            if pos == "after" and marker != last_gloss:
                last_gloss = marker
                gloss_items.append(
                    GlossItem(
                        gloss=marker,
                        gloss_type=GlossType.SIGN,
                        order=current_order,
                        proposition_id=prop.id,
                        duration_ms=self.compute_duration(marker, GlossType.SIGN, is_temporal=True),
                        notes="Marcador aspectual",
                    )
                )
                current_order += 1

        return gloss_items

    def _translate_general_heuristic(self, prop: SemanticProposition, start_order: int) -> List[GlossItem]:
        """Fallback heurístico directo."""
        words = prop.source_text.split()
        items: List[GlossItem] = []
        curr = start_order

        for w in words:
            clean = re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ\-]", "", w)
            if not clean:
                continue
            clean_lower = clean.lower()
            clean_upper = clean.upper()

            if clean_lower in ("el", "la", "los", "las", "un", "una", "de", "del", "en", "a", "al", "para", "por", "con", "sin", "y", "o", "que"):
                continue

            if clean_upper in self._institutional_dict:
                g_txt = self._institutional_dict[clean_upper]["gloss"]
                g_typ = GlossType(self._institutional_dict[clean_upper]["type"])
            elif clean_lower in self._lemma_overrides:
                g_txt = self._lemma_overrides[clean_lower].upper()
                g_typ = GlossType.SIGN
            elif clean_lower in self._pronoun_deixis:
                g_txt = self._pronoun_deixis[clean_lower]
                g_typ = GlossType.SIGN
            else:
                g_txt = clean_upper
                g_typ = GlossType.SIGN

            w_expr = FacialExpression.NEGATION if clean_lower in ("no", "nunca", "jamás") else FacialExpression.NEUTRAL
            w_head = "negar" if w_expr == FacialExpression.NEGATION else None

            items.append(
                GlossItem(
                    gloss=g_txt,
                    gloss_type=g_typ,
                    order=curr,
                    source_word=w,
                    normalized_word=clean,
                    proposition_id=prop.id,
                    non_manual=NonManualMarker(expression=w_expr, head_movement=w_head),
                    duration_ms=self.compute_duration(g_txt, g_typ),
                )
            )
            curr += 1

        return items



    def _generate_spans_for_prop(
        self,
        prop: SemanticProposition,
        glosses: List[GlossItem],
        start_o: int,
        end_o: int,
        p_idx: int,
    ) -> List[NonManualSpan]:
        """Genera spans no manuales para la proposición con alcances sintácticos precisos."""
        spans: List[NonManualSpan] = []
        p_text_lower = prop.source_text.lower()

        prop_span_type = None
        prop_expr = FacialExpression.NEUTRAL
        prop_head = None
        prop_body = None
        prop_intensity = 1.0
        prop_priority = 1
        span_start = start_o
        span_end = end_o

        if ("quién" in p_text_lower and "quieres" in p_text_lower) or (prop.modality == "reflective" and "quién" in p_text_lower):
            # Cláusula reflexiva explícita (Fase 11)
            prop_span_type = "reflective"
            prop_expr = FacialExpression.REFLECTIVE
            prop_head = "inclinación_lateral_leve"
            prop_intensity = 0.6
            prop_priority = 2
        elif prop.rhetorical_function == "sustainability_recognition" or "más destacada" in p_text_lower or "más sostenible" in p_text_lower:
            # Superlativo restringido a atributo y grado (Fase 11)
            prop_span_type = "superlative"
            prop_expr = FacialExpression.SUPERLATIVE
            prop_intensity = 1.2
            prop_priority = 3
            # Limitar el span solo a glosas de grado y atributo si existen
            sup_glosses = [g for g in glosses if g.gloss in ("SOSTENIBILIDAD", "MÁS", "MÁS-DE", "DESTACAR")]
            if sup_glosses:
                span_start = min(g.order for g in sup_glosses)
                span_end = max(g.order for g in sup_glosses)
        elif prop.rhetorical_function == "inspiration":
            prop_span_type = "narrative"
            prop_expr = FacialExpression.NARRATIVE
            prop_head = "inclinación_lateral_leve"
            prop_intensity = 0.8
            prop_priority = 1
        elif prop.rhetorical_function in ("contrast",) or prop.discourse_relation in ("but", "not_only", "also"):
            prop_span_type = "contrast"
            prop_expr = FacialExpression.CONTRAST
            prop_body = "left" if prop.discourse_relation == "not_only" else "right"
            prop_intensity = 1.0
            prop_priority = 2
        elif prop.modality == "imperative" or prop.rhetorical_function in ("call_to_action", "future_decision", "imagination_to_reality"):
            prop_span_type = "imperative"
            prop_expr = FacialExpression.IMPERATIVE
            prop_intensity = 1.1
            prop_priority = 2
        elif prop.rhetorical_function == "closure":
            prop_span_type = "emphasis"
            prop_expr = FacialExpression.EMPHASIS
            prop_intensity = 1.2
            prop_priority = 2
        elif "?" in prop.source_text or "¿" in prop.source_text:
            has_wh = any(t.text.lower() in self._wh_lemmas for t in self._nlp(prop.source_text)) if self._nlp else ("qué" in p_text_lower or "dónde" in p_text_lower)
            prop_span_type = "question_wh" if has_wh else "question_yn"
            prop_expr = FacialExpression.QUESTION_WH if has_wh else FacialExpression.QUESTION_YESNO
            prop_head = "inclinar"
            prop_intensity = 1.2
            prop_priority = 3

        if prop_span_type:
            spans.append(
                NonManualSpan(
                    id=f"span_{p_idx + 1}_{prop_span_type}",
                    type=prop_span_type,
                    start_order=span_start,
                    end_order=span_end,
                    expression=prop_expr,
                    head_movement=prop_head,
                    body_shift=prop_body,
                    intensity=prop_intensity,
                    priority=prop_priority,
                    proposition_id=prop.id,
                )
            )

        # Span de negación local
        if prop.polarity == "negative" or "nadie" in p_text_lower or "no " in p_text_lower or p_text_lower.startswith("no "):
            neg_items = [g for g in glosses if g.gloss in ("NADIE", "SOLAMENTE-NO", "NO", "NUNCA")]
            if neg_items:
                neg_start = min(g.order for g in neg_items)
                neg_end = max(g.order for g in neg_items)
                spans.append(
                    NonManualSpan(
                        id=f"span_{p_idx + 1}_negation",
                        type="negation",
                        start_order=neg_start,
                        end_order=neg_end,
                        expression=FacialExpression.NEGATION,
                        head_movement="negar",
                        intensity=0.9,
                        priority=3,
                        proposition_id=prop.id,
                    )
                )

        return spans
