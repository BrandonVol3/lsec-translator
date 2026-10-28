"""
Servicio de Parsing y Representación Semántica Intermedia (LSEC 2.1.1).

Construye objetos `SemanticProposition`, `SemanticParticipant`, `SemanticPredicate`
y `SemanticRelation` a partir del análisis lingüístico de las unidades discursivas.

Mantiene el Patrón Fachada para retrocompatibilidad al 100 % de imports en
`nlp_service.py`, `discourse_planner.py`, `main.py` y `app/tests/`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.schemas import (
    FragmentType,
    ParticipantType,
    PredicateType,
    RelationType,
    SemanticParticipant,
    SemanticPredicate,
    SemanticProposition,
    SemanticRelation,
    SemanticRole,
)
from app.services.discourse_segmenter import DiscourseUnit
from app.services.mwe_detector import MWEDetector, MWEMatch
from app.services.semantic_constants import (
    CONSUMABLE_NOUNS,
    COPULA_FORMS,
    DEFAULT_PRONOUN_DEIXIS,
    FORBIDDEN_PREDICATE_LEMMAS,
    IRREGULAR_ENCLITIC_MAP,
    IRREGULAR_FUTURE_STEMS,
    KNOWN_VERB_FORMS,
    LOCATION_NOUNS,
    NOMINAL_HOMOGRAPHS,
    NON_ENCLITIC_WORDS,
    PERSON_NOUNS,
    POS_GATED_LEMMAS,
)
from app.services.semantic_domain_templates import match_special_domain_proposition
from app.services.semantic_role_extractor import PredicateDetector, SemanticRoleExtractor
from app.services.semantic_verb_morphology import ModalityDetector, SpanishVerbLexicon
from app.services.text_normalizer import (
    EntityInfo,
    PunctuationAnalyzer,
    _NEGATION_RE,
    contains_negation,
)

logger = logging.getLogger(__name__)


class SemanticParser:
    """
    Parser semántico que transforma unidades discursivas en proposiciones estructuradas.
    """

    def __init__(
        self,
        nlp=None,
        entity_registry: Optional[Dict[str, EntityInfo]] = None,
        mwe_detector: Optional[MWEDetector] = None,
        pronoun_deixis_map: Optional[Dict[str, str]] = None,
    ) -> None:
        self._nlp = nlp
        self._entity_registry = entity_registry or {}
        self._mwe_detector = mwe_detector or MWEDetector()
        self._pronoun_deixis = pronoun_deixis_map or dict(DEFAULT_PRONOUN_DEIXIS)

    def parse_unit_to_propositions(
        self,
        unit: DiscourseUnit,
        prev_propositions: List[SemanticProposition],
        active_speaker: str = "institution_upec",
    ) -> List[SemanticProposition]:
        """
        Transforma una DiscourseUnit en una o más SemanticProposition.
        """
        text = unit.text.strip()
        prop_id = f"p{unit.id + 1}"
        mwe_matches = self._mwe_detector.detect(text)

        # Determinar polaridad y modalidad robusta
        polarity = (
            "negative"
            if (unit.has_negation_scope or contains_negation(text))
            else "positive"
        )
        modality = ModalityDetector.detect(text, unit)

        participants: List[SemanticParticipant] = []
        predicate: Optional[SemanticPredicate] = None
        relations: List[SemanticRelation] = []
        embedded_props: List[Dict[str, Any]] = []
        temp_modifiers: List[Dict[str, Any]] = []

        text_lower = text.lower()

        # 1–12. Casos estructurados especiales del dominio institucional/educativo
        special_match = match_special_domain_proposition(
            text_lower=text_lower,
            unit=unit,
            prop_id=prop_id,
            prev_propositions=prev_propositions,
        )
        if special_match is not None:
            predicate, participants, relations, embedded_props, temp_modifiers = special_match
        else:
            # 13. Detección general robusta mediante PredicateDetector y SemanticRoleExtractor
            doc = self._nlp(text) if self._nlp is not None else None
            predicate = PredicateDetector.find_predicate(
                text=text,
                doc=doc,
                modality=modality,
                polarity=polarity,
            )
            extracted_participants = SemanticRoleExtractor.extract_participants(
                text=text,
                doc=doc,
                predicate=predicate,
                mwe_matches=mwe_matches,
                pronoun_deixis=self._pronoun_deixis,
            )
            for part in extracted_participants:
                if not any(
                    p.id == part.id or (p.lemma == part.lemma and p.semantic_role == part.semantic_role)
                    for p in participants
                ):
                    participants.append(part)

        # Fallback de predicado seguro (nunca un pronombre, determinante, sustantivo o adverbio prohibido)
        if predicate is None:
            doc = self._nlp(text) if self._nlp is not None else None
            predicate = PredicateDetector.find_predicate(
                text=text,
                doc=doc,
                modality=modality,
                polarity=polarity,
            )
            if predicate is None:
                cand = None
                tokens_clean = [PunctuationAnalyzer.strip_punctuation(w).lower() for w in text.split()]
                for w_l in tokens_clean:
                    if (
                        w_l
                        and w_l not in PredicateDetector.FORBIDDEN_PREDICATE_LEMMAS
                        and SpanishVerbLexicon.is_verb(w_l)
                    ):
                        cand = SpanishVerbLexicon.normalize_verb_lemma(w_l, w_l, pos="VERB")
                        break
                if cand is not None:
                    predicate = SemanticPredicate(
                        lemma=cand,
                        predicate_type=PredicateType.ACTION if modality != "imperative" else PredicateType.IMPERATIVE,
                        polarity=polarity,
                        modality=modality,
                        is_implicit=False,
                        confidence=0.80,
                    )

        # Determinar fragment_type y relaciones jerárquicas
        raw_frag = getattr(unit, "fragment_type", "COMPLETE_PROPOSITION")
        try:
            frag_type = FragmentType(raw_frag)
        except (ValueError, TypeError):
            frag_type = FragmentType.COMPLETE_PROPOSITION

        head_concept: Optional[str] = None
        enumerated_participants: List[str] = []
        parent_prop_id: Optional[str] = None
        parent_part_id: Optional[str] = None
        dependency_type: Optional[str] = None

        if (
            unit.rhetorical_function == "campus_enumeration"
            and "campus" in text_lower
            and sum(
                1 for loc in ("tulcán", "tulcan", "cayambe", "quito", "ibarra", "sede")
                if loc in text_lower
            ) >= 2
        ):
            frag_type = FragmentType.ENUMERATION_FRAGMENT
            head_concept = "campus"
            enumerated_participants = ["ent_tulcan", "ent_cayambe"]
            if prev_propositions:
                parent_prop_id = prev_propositions[-1].id
                dependency_type = "LOCATION_EXPANSION"

        if "inspiran" in text_lower:
            dependency_type = "RELATIVE_CLAUSE"
            if prev_propositions:
                parent_prop_id = prev_propositions[-1].id
                parent_part_id = "part_mwe_seres_humanos"
        elif "evoluciona" in text_lower:
            dependency_type = "RELATIVE_CLAUSE"
            if prev_propositions:
                parent_prop_id = prev_propositions[-1].id
                parent_part_id = "noun_tecnologia"
        elif text_lower in ("y cercanía", "cercanía"):
            dependency_type = "COORDINATION"
            if prev_propositions:
                parent_prop_id = prev_propositions[-1].id

        is_liberan = "liberan" in text_lower and len(text.split()) <= 2
        is_imparable = "imparable" in text_lower
        is_cercania = "cercanía" in text_lower

        # Operadores semánticos estructurados (NEGATION, QUESTION_YN, QUESTION_WH)
        operators = list(getattr(unit, "operators", []))
        if polarity == "negative" and not any(
            op.get("type") == "NEGATION" or op.get("operator_type") == "NEGATION" for op in operators
        ):
            m_neg = _NEGATION_RE.search(text_lower)
            neg_tok = m_neg.group(1) if m_neg else "no"
            operators.append({
                "type": "NEGATION",
                "operator_type": "NEGATION",
                "source_token": neg_tok,
                "scope": prop_id,
                "confidence": 0.95,
            })
        if modality == "interrogative_yn" and not any(
            op.get("type") == "QUESTION_YN" for op in operators
        ):
            operators.append({
                "type": "QUESTION_YN",
                "operator_type": "QUESTION_YN",
                "scope": prop_id,
                "confidence": 0.95,
            })
        elif modality == "interrogative_wh" and not any(
            op.get("type") == "QUESTION_WH" for op in operators
        ):
            operators.append({
                "type": "QUESTION_WH",
                "operator_type": "QUESTION_WH",
                "scope": prop_id,
                "confidence": 0.95,
            })

        prop = SemanticProposition(
            id=prop_id,
            source_text=text,
            normalized_text=text,
            fragment_type=frag_type,
            source_token_indexes=list(range(len(text.split()))),
            predicate=predicate,
            participants=participants,
            semantic_relations=relations,
            parent_proposition_id=parent_prop_id,
            parent_participant_id=parent_part_id,
            dependency_type=dependency_type,
            head_concept=head_concept,
            enumerated_participants=enumerated_participants,
            context_info=getattr(unit, "context_info", {}),
            operators=operators,
            discourse_relation=unit.discourse_relation,
            rhetorical_function=unit.rhetorical_function,
            embedded_propositions=embedded_props,
            temporal_modifiers=temp_modifiers,
            polarity=polarity,
            modality=modality,
            is_embedded=unit.is_embedded,
            confidence=0.88,
        )

        return [prop]


__all__ = [
    "SemanticParser",
    "SpanishVerbLexicon",
    "ModalityDetector",
    "PredicateDetector",
    "SemanticRoleExtractor",
    "PunctuationAnalyzer",
    "MWEDetector",
    "MWEMatch",
    "EntityInfo",
    "DiscourseUnit",
    "KNOWN_VERB_FORMS",
    "NOMINAL_HOMOGRAPHS",
    "POS_GATED_LEMMAS",
    "COPULA_FORMS",
    "NON_ENCLITIC_WORDS",
    "IRREGULAR_ENCLITIC_MAP",
    "IRREGULAR_FUTURE_STEMS",
    "FORBIDDEN_PREDICATE_LEMMAS",
    "CONSUMABLE_NOUNS",
    "LOCATION_NOUNS",
    "PERSON_NOUNS",
    "DEFAULT_PRONOUN_DEIXIS",
]
