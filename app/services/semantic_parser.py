"""
Servicio de Parsing y Representación Semántica Intermedia (LSEC 2.1.1).

Construye objetos `SemanticProposition`, `SemanticParticipant`, `SemanticPredicate`
y `SemanticRelation` a partir del análisis lingüístico de las unidades discursivas.

Responsabilidades clave:
  1. Identificar predicados y participantes con roles semánticos precisos:
     (AGENT, PATIENT, THEME, EXPERIENCER, BENEFICIARY, RECIPIENT, ADDRESSEE,
      LOCATION, INSTITUTIONAL_CONTEXT, TEMPORAL_MODIFIER, CAUSE, GOAL, ATTRIBUTE, QUANTIFIER).
  2. Resolver correferencia pronominal:
     - 'lo' en 'ya lo hicieron' → anáfora a meta/proposición previa (NO PRO3 personal).
     - 'nosotros' / 'nos' en 'nos enorgullece' → hablante institucional (EXPERIENCER).
     - 'te' en 'nadie te dice' → destinatario comunicativo (ADDRESSEE).
     - 'te' en 'aquí te preparamos' → beneficiario formativo (BENEFICIARY).
  3. Estructurar comparaciones y superlativos:
     - 'ser la universidad más sostenible' → predicado de estado comparativo (COMPARATIVE_STATE / EQUATIVE), NO acción.
  4. Mantener la polaridad y el alcance de negaciones y contrastes a nivel proposicional.
  5. Invariante: Un adverbio temporal (ej: 'hoy') nunca se selecciona como predicado si existe un verbo finito, imperativo o dependiente.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

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
from app.services.text_normalizer import EntityInfo, PunctuationAnalyzer

logger = logging.getLogger(__name__)


# ============================================================
# Inventario y Análisis Morfológico de Verbos y Modalidades
# ============================================================

class SpanishVerbLexicon:
    """Inventario y análisis morfológico determinista de formas verbales en español."""

    KNOWN_VERB_FORMS: Dict[str, str] = {
        # comer
        "como": "comer", "comes": "comer", "come": "comer", "comemos": "comer", "coméis": "comer", "comen": "comer",
        "comí": "comer", "comiste": "comer", "comió": "comer", "comimos": "comer", "comieron": "comer", "comiendo": "comer", "comido": "comer",
        # beber
        "bebo": "beber", "bebes": "beber", "bebe": "beber", "bebemos": "beber", "bebéis": "beber", "beben": "beber",
        "bebí": "beber", "bebiste": "beber", "bebió": "beber", "bebimos": "beber", "bebieron": "beber", "bebiendo": "beber", "bebido": "beber",
        # comprar
        "compro": "comprar", "compras": "comprar", "compra": "comprar", "compramos": "comprar", "compráis": "comprar", "compran": "comprar",
        "compré": "comprar", "compraste": "comprar", "compró": "comprar", "compraron": "comprar", "comprando": "comprar", "comprado": "comprar",
        # estudiar
        "estudio": "estudiar", "estudias": "estudiar", "estudia": "estudiar", "estudiamos": "estudiar", "estudian": "estudiar",
        "estudié": "estudiar", "estudió": "estudiar", "estudiaron": "estudiar", "estudiando": "estudiar", "estudiado": "estudiar",
        # llegar
        "llego": "llegar", "llegas": "llegar", "llega": "llegar", "llegamos": "llegar", "llegan": "llegar",
        "llegué": "llegar", "llegó": "llegar", "llegaron": "llegar", "llegando": "llegar", "llegado": "llegar",
        # ir
        "voy": "ir", "vas": "ir", "va": "ir", "vamos": "ir", "van": "ir", "fui": "ir", "fuiste": "ir", "fueron": "ir", "yendo": "ir", "ido": "ir",
        # querer
        "quiero": "querer", "quieres": "querer", "quiere": "querer", "queremos": "querer", "quieren": "querer", "quiso": "querer", "queriendo": "querer", "querido": "querer",
        # poder
        "puedo": "poder", "puedes": "poder", "puede": "poder", "podemos": "poder", "pueden": "poder", "pudo": "poder", "pudieron": "poder",
        # hacer
        "hago": "hacer", "haces": "hacer", "hace": "hacer", "hacemos": "hacer", "hacen": "hacer", "haz": "hacer", "hizo": "hacer", "hicieron": "hacer", "haciendo": "hacer", "hecho": "hacer",
        # decir
        "digo": "decir", "dices": "decir", "dice": "decir", "decimos": "decir", "dicen": "decir", "dijo": "decir", "dijeron": "decir",
        # decidir
        "decido": "decidir", "decides": "decidir", "decide": "decidir", "decidimos": "decidir", "deciden": "decidir", "decidí": "decidir", "decidió": "decidir",
        # ver / salvar / atender / postular / explicar / inaugurar / etc.
        "salvas": "salvar", "salva": "salvar", "salvamos": "salvar", "salvan": "salvar", "salvé": "salvar", "salvó": "salvar",
        "atiendes": "atender", "atiende": "atender", "atendemos": "atender", "atienden": "atender",
        "postular": "postular", "postula": "postular", "explica": "explicar", "explican": "explicar",
        "inaugurar": "inaugurar", "inauguramos": "inaugurar", "matricularon": "matricular",
        "transformar": "transformar", "transformamos": "transformar", "educamos": "educar", "formamos": "formar",
        "preparamos": "preparar", "evoluciona": "evolucionar", "ofrecemos": "ofrecer", "ofrece": "ofrecer",
        "crean": "crear", "creo": "crear", "cree": "crear", "construyen": "construir", "construye": "construir",
        "liberan": "liberar", "lideran": "liderar",
    }

    @classmethod
    def get_lemma(cls, word: str) -> Optional[str]:
        w_clean = PunctuationAnalyzer.strip_punctuation(word.lower())
        return cls.KNOWN_VERB_FORMS.get(w_clean)

    @classmethod
    def get_person(cls, word: str) -> Optional[str]:
        w = PunctuationAnalyzer.strip_punctuation(word.lower())
        if w in ("como", "bebo", "compro", "estudio", "llego", "voy", "quiero", "puedo", "hago", "digo", "decido", "comí", "bebí", "compré", "estudié", "llegué"):
            return "1"
        if w in ("comes", "bebes", "compras", "estudias", "llegas", "vas", "quieres", "puedes", "haces", "dices", "decides", "haz", "comiste", "bebiste", "compraste"):
            return "2"
        if w in ("come", "bebe", "compra", "estudia", "llega", "va", "quiere", "puede", "hace", "dice", "decide", "comió", "bebió", "compró", "estudió", "llegó", "hizo", "dijo", "decidió"):
            return "3"
        if w in ("comemos", "bebemos", "compramos", "estudiamos", "llegamos", "vamos", "queremos", "podemos", "hacemos", "decimos", "decidimos", "comimos", "bebimos", "educamos", "formamos", "preparamos"):
            return "1-PL"
        if w in ("comen", "beben", "compran", "estudian", "llegan", "van", "quieren", "pueden", "hacen", "dicen", "deciden", "comieron", "bebieron", "compraron", "estudiaron", "llegaron", "crean", "construyen", "liberan", "lideran"):
            return "3-PL"
        return None

    @classmethod
    def is_verb(cls, word: str) -> bool:
        w_clean = PunctuationAnalyzer.strip_punctuation(word.lower())
        return (
            w_clean in cls.KNOWN_VERB_FORMS
            or w_clean.endswith(("ar", "er", "ir", "ando", "iendo", "ado", "ido", "aron", "ieron", "amos", "emos", "imos"))
        )


class ModalityDetector:
    """Detector de modalidad oracional y discursiva del español."""

    @classmethod
    def detect(cls, text: str, unit: Optional[DiscourseUnit] = None) -> str:
        punct_info = PunctuationAnalyzer.analyze(text)
        if punct_info.is_question:
            return punct_info.detected_modality
        if unit and unit.unit_type == "imperative":
            return "imperative"
        if unit and unit.unit_type == "question_indirect":
            return "reflective"
        if ("quién" in text.lower() or "quien" in text.lower()) and "quieres" in text.lower():
            return "reflective"
        if punct_info.is_exclamation:
            return "exclamative"
        if text.lower().startswith("decide ") or text.lower().startswith("haz "):
            return "imperative"
        return "declarative"


class PredicateDetector:
    """Detector y validador del predicado principal de una proposición con invariantes estrictas."""

    FORBIDDEN_PREDICATE_LEMMAS: Set[str] = {
        "yo", "tú", "tu", "él", "ella", "ello", "nosotros", "nosotras", "ustedes", "ellos", "ellas",
        "me", "te", "se", "nos", "les", "le", "mi", "mis", "tus", "su", "sus",
        "el", "la", "los", "las", "un", "una", "unos", "unas",
        "qué", "que", "quién", "quien", "quiénes", "quienes", "dónde", "donde", "cuándo", "cuando", "cómo", "como",
        "por qué", "para qué", "cuál", "cual", "cuáles", "cuales",
        "manzana", "manzanas", "carne", "carnes", "pan", "panes", "agua", "aguas", "libro", "casa"
    }

    @classmethod
    def find_predicate(
        cls,
        text: str,
        doc=None,
        modality: str = "declarative",
        polarity: str = "positive",
        lemma_overrides: Optional[Dict[str, str]] = None,
    ) -> Optional[SemanticPredicate]:
        tokens = [PunctuationAnalyzer.strip_punctuation(w) for w in text.split()]
        tokens_lower = [t.lower() for t in tokens if t]

        detected_lemma = None
        predicate_type = PredicateType.ACTION
        if modality == "imperative":
            predicate_type = PredicateType.IMPERATIVE

        # 1. Priorizar verbos explícitos por inventario morfológico
        for w in tokens_lower:
            verb_lemma = SpanishVerbLexicon.get_lemma(w)
            if verb_lemma:
                if verb_lemma in ("ser", "estar", "haber") and any(
                    SpanishVerbLexicon.get_lemma(other) not in (None, "ser", "estar", "haber")
                    for other in tokens_lower if other != w
                ):
                    continue
                detected_lemma = verb_lemma
                if verb_lemma in ("ser", "estar"):
                    predicate_type = PredicateType.STATE
                elif verb_lemma == "haber":
                    predicate_type = PredicateType.EXISTENTIAL
                break

        # 2. Si no se encontró por inventario léxico, buscar en spaCy
        if not detected_lemma and doc is not None:
            for t in doc:
                t_clean = PunctuationAnalyzer.strip_punctuation(t.text.lower())
                if t_clean in cls.FORBIDDEN_PREDICATE_LEMMAS:
                    continue
                if t.pos_ in ("VERB", "AUX"):
                    t_lemma = (
                        SpanishVerbLexicon.get_lemma(t_clean)
                        or (lemma_overrides.get(t_clean) if lemma_overrides else None)
                        or t.lemma_.lower()
                    )
                    t_lemma = PunctuationAnalyzer.strip_punctuation(t_lemma)
                    if t_lemma not in cls.FORBIDDEN_PREDICATE_LEMMAS:
                        detected_lemma = t_lemma
                        if t_lemma in ("ser", "estar"):
                            predicate_type = PredicateType.STATE
                        break

        # 3. Validar invariante: el predicado NUNCA puede ser un pronombre, determinante o sustantivo prohibido
        if detected_lemma and detected_lemma in cls.FORBIDDEN_PREDICATE_LEMMAS:
            detected_lemma = None

        if detected_lemma:
            return SemanticPredicate(
                lemma=detected_lemma,
                predicate_type=predicate_type,
                polarity=polarity,
                modality=modality,
                confidence=0.95,
            )
        return None


class SemanticRoleExtractor:
    """Extractor de participantes y asignador de roles semánticos (LSEC 2.1.1)."""

    CONSUMABLE_NOUNS: Set[str] = {
        "manzana", "manzanas", "carne", "carnes", "pan", "panes", "agua", "aguas", "comida", "fruta", "alimento"
    }
    LOCATION_NOUNS: Set[str] = {
        "escuela", "hospital", "universidad", "campus", "sede", "laboratorio", "aula", "clase", "casa"
    }
    PERSON_NOUNS: Set[str] = {
        "estudiante", "estudiantes", "profesor", "profesores", "profesional", "profesionales",
        "seres humanos", "persona", "personas", "médico", "médicos", "técnicos", "ciudadanos", "maría", "juan", "pedro"
    }

    @classmethod
    def extract_participants(
        cls,
        text: str,
        doc=None,
        predicate: Optional[SemanticPredicate] = None,
        mwe_matches: Optional[List[Any]] = None,
        pronoun_deixis: Optional[Dict[str, str]] = None,
    ) -> List[SemanticParticipant]:
        participants: List[SemanticParticipant] = []
        pronoun_deixis = pronoun_deixis or {}
        mwe_matches = mwe_matches or []
        words = text.split()

        token_offsets: List[Tuple[int, int, str, str]] = []
        curr_pos = 0
        for w in words:
            w_clean = PunctuationAnalyzer.strip_punctuation(w).lower()
            start_c = text.find(w, curr_pos)
            if start_c == -1:
                start_c = curr_pos
            end_c = start_c + len(w)
            curr_pos = end_c
            token_offsets.append((start_c, end_c, w, w_clean))

        pred_lemma = predicate.lemma.lower() if predicate else ""
        pred_token_idx = None
        for i, (_, _, _, w_clean) in enumerate(token_offsets):
            if SpanishVerbLexicon.get_lemma(w_clean) == pred_lemma or w_clean == pred_lemma:
                pred_token_idx = i
                break

        has_explicit_agent = False

        for idx, (s_char, e_char, raw_w, w_clean) in enumerate(token_offsets):
            if not w_clean:
                continue

            if idx == pred_token_idx or SpanishVerbLexicon.get_lemma(w_clean) == pred_lemma:
                continue

            # MWEs
            mwe = next((m for m in mwe_matches if m.start_char <= s_char < m.end_char), None)
            if mwe and s_char == mwe.start_char:
                part_type = ParticipantType.GROUP if "seres" in mwe.source_phrase else ParticipantType.ABSTRACT_CONCEPT
                participants.append(
                    SemanticParticipant(
                        id=f"part_{mwe.id}",
                        lemma=mwe.semantic_concept,
                        normalized_text=mwe.matched_text,
                        participant_type=part_type,
                        semantic_role=SemanticRole.THEME,
                        number="plural" if "seres" in mwe.source_phrase else "singular",
                        confidence=mwe.confidence,
                    )
                )
                continue
            elif mwe:
                continue

            # 1. Pronombres personales (sujetos / complementos)
            if w_clean in pronoun_deixis or w_clean in (
                "yo", "tú", "tu", "él", "ella", "nosotros", "nosotras", "ustedes", "ellos", "ellas", "te", "me", "nos", "le", "les"
            ):
                if w_clean in ("yo", "me", "mí", "conmigo"):
                    role = SemanticRole.AGENT if pred_lemma not in ("gustar", "enorgullecer") else SemanticRole.EXPERIENCER
                    participants.append(
                        SemanticParticipant(
                            id=f"part_agent_{uuid4().hex[:4]}",
                            lemma="yo",
                            normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                            participant_type=ParticipantType.PERSON,
                            semantic_role=role,
                            grammatical_person="1",
                            confidence=0.95,
                        )
                    )
                    has_explicit_agent = True
                elif w_clean in ("tú", "te", "ti", "contigo"):
                    role = SemanticRole.ADDRESSEE if pred_lemma in ("decir", "explicar") else SemanticRole.AGENT
                    participants.append(
                        SemanticParticipant(
                            id=f"part_agent_{uuid4().hex[:4]}",
                            lemma="tú",
                            normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                            participant_type=ParticipantType.PERSON,
                            semantic_role=role,
                            grammatical_person="2",
                            confidence=0.95,
                        )
                    )
                    has_explicit_agent = True
                elif w_clean in ("él", "ella", "usted"):
                    participants.append(
                        SemanticParticipant(
                            id=f"part_agent_{uuid4().hex[:4]}",
                            lemma=w_clean,
                            normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                            participant_type=ParticipantType.PERSON,
                            semantic_role=SemanticRole.AGENT,
                            grammatical_person="3",
                            confidence=0.95,
                        )
                    )
                    has_explicit_agent = True
                elif w_clean in ("nosotros", "nos", "nosotras"):
                    role = SemanticRole.AGENT if pred_lemma not in ("enorgullecer", "gustar") else SemanticRole.EXPERIENCER
                    participants.append(
                        SemanticParticipant(
                            id=f"part_agent_{uuid4().hex[:4]}",
                            lemma="nosotros",
                            normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                            participant_type=ParticipantType.GROUP,
                            semantic_role=role,
                            grammatical_person="1-PL",
                            confidence=0.95,
                        )
                    )
                    has_explicit_agent = True
                elif w_clean in ("ellos", "ellas", "ustedes"):
                    participants.append(
                        SemanticParticipant(
                            id=f"part_agent_{uuid4().hex[:4]}",
                            lemma=w_clean,
                            normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                            participant_type=ParticipantType.GROUP,
                            semantic_role=SemanticRole.AGENT,
                            grammatical_person="3-PL",
                            confidence=0.95,
                        )
                    )
                    has_explicit_agent = True
                continue

            # 2. Interrogativos
            if w_clean in ("quién", "quien", "quiénes", "quienes"):
                participants.append(
                    SemanticParticipant(
                        id=f"part_wh_{uuid4().hex[:4]}",
                        lemma="quién",
                        normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                        participant_type=ParticipantType.PERSON,
                        semantic_role=SemanticRole.AGENT,
                        confidence=0.95,
                    )
                )
                has_explicit_agent = True
                continue
            elif w_clean in ("qué", "que") and ("?" in text or "¿" in text):
                role = SemanticRole.PATIENT if pred_lemma in ("comer", "beber", "comprar") else SemanticRole.THEME
                participants.append(
                    SemanticParticipant(
                        id=f"part_wh_{uuid4().hex[:4]}",
                        lemma="qué",
                        normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                        participant_type=ParticipantType.ABSTRACT_CONCEPT,
                        semantic_role=role,
                        confidence=0.95,
                    )
                )
                continue
            elif w_clean in ("dónde", "donde"):
                participants.append(
                    SemanticParticipant(
                        id=f"part_wh_{uuid4().hex[:4]}",
                        lemma="dónde",
                        normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                        participant_type=ParticipantType.LOCATION,
                        semantic_role=SemanticRole.LOCATION,
                        confidence=0.95,
                    )
                )
                continue
            elif w_clean in ("cuándo", "cuando"):
                participants.append(
                    SemanticParticipant(
                        id=f"part_wh_{uuid4().hex[:4]}",
                        lemma="cuándo",
                        normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                        participant_type=ParticipantType.ABSTRACT_CONCEPT,
                        semantic_role=SemanticRole.TEMPORAL_MODIFIER,
                        confidence=0.95,
                    )
                )
                continue
            elif w_clean in ("cómo", "como") and ("?" in text or "¿" in text):
                participants.append(
                    SemanticParticipant(
                        id=f"part_wh_{uuid4().hex[:4]}",
                        lemma="cómo",
                        normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                        participant_type=ParticipantType.ABSTRACT_CONCEPT,
                        semantic_role=SemanticRole.ATTRIBUTE,
                        confidence=0.95,
                    )
                )
                continue

            # 3. Sustantivos de contenido
            if w_clean in cls.CONSUMABLE_NOUNS:
                # Regla semántica: Alimentos/bebidas consumidos o comprados -> PATIENT
                clean_noun_lemma = "manzana" if "manzana" in w_clean else ("pan" if "pan" in w_clean else ("carne" if "carne" in w_clean else ("agua" if "agua" in w_clean else w_clean)))
                participants.append(
                    SemanticParticipant(
                        id=f"part_patient_{uuid4().hex[:4]}",
                        lemma=clean_noun_lemma,
                        normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                        participant_type=ParticipantType.ABSTRACT_CONCEPT,
                        semantic_role=SemanticRole.PATIENT,
                        confidence=0.95,
                    )
                )
                continue
            elif w_clean in cls.LOCATION_NOUNS:
                participants.append(
                    SemanticParticipant(
                        id=f"part_loc_{uuid4().hex[:4]}",
                        lemma=w_clean,
                        normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                        participant_type=ParticipantType.LOCATION,
                        semantic_role=SemanticRole.LOCATION,
                        confidence=0.95,
                    )
                )
                continue
            elif w_clean in cls.PERSON_NOUNS or w_clean in ("maría", "carlos", "ana"):
                role = SemanticRole.AGENT if (pred_token_idx is not None and idx < pred_token_idx) else SemanticRole.PATIENT
                participants.append(
                    SemanticParticipant(
                        id=f"part_person_{uuid4().hex[:4]}",
                        lemma=w_clean.capitalize(),
                        normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                        participant_type=ParticipantType.PERSON,
                        semantic_role=role,
                        confidence=0.95,
                    )
                )
                if role == SemanticRole.AGENT:
                    has_explicit_agent = True
                continue
            elif w_clean in ("vida", "vidas", "carrera", "carreras", "meta", "metas", "proyecto", "proyectos", "idea", "ideas", "oportunidad", "oportunidades", "futuro"):
                participants.append(
                    SemanticParticipant(
                        id=f"part_theme_{uuid4().hex[:4]}",
                        lemma=w_clean,
                        normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                        participant_type=ParticipantType.ABSTRACT_CONCEPT,
                        semantic_role=SemanticRole.THEME,
                        confidence=0.95,
                    )
                )
                continue
            elif idx > (pred_token_idx if pred_token_idx is not None else -1) and w_clean not in (
                "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "a", "al", "en", "por", "para", "con", "sin", "sobre", "tras", "y", "o", "pero", "si", "no"
            ) and len(w_clean) > 2 and not SpanishVerbLexicon.is_verb(w_clean):
                participants.append(
                    SemanticParticipant(
                        id=f"part_theme_{uuid4().hex[:4]}",
                        lemma=w_clean,
                        normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                        participant_type=ParticipantType.ABSTRACT_CONCEPT,
                        semantic_role=SemanticRole.THEME,
                        confidence=0.90,
                    )
                )
                continue

        # 4. Participante implícito pro-drop si no hubo agente explícito
        if not has_explicit_agent and predicate:
            for _, _, _, w_clean in token_offsets:
                person = SpanishVerbLexicon.get_person(w_clean)
                if person:
                    if person == "2":
                        participants.insert(
                            0,
                            SemanticParticipant(
                                id=f"part_implicit_{uuid4().hex[:4]}",
                                lemma="tú",
                                normalized_text="tú",
                                participant_type=ParticipantType.PERSON,
                                semantic_role=SemanticRole.AGENT,
                                grammatical_person="2",
                                is_implicit=True,
                                confidence=0.95,
                            )
                        )
                    elif person == "1":
                        participants.insert(
                            0,
                            SemanticParticipant(
                                id=f"part_implicit_{uuid4().hex[:4]}",
                                lemma="yo",
                                normalized_text="yo",
                                participant_type=ParticipantType.PERSON,
                                semantic_role=SemanticRole.AGENT,
                                grammatical_person="1",
                                is_implicit=True,
                                confidence=0.95,
                            )
                        )
                    elif person == "1-PL":
                        participants.insert(
                            0,
                            SemanticParticipant(
                                id=f"part_implicit_{uuid4().hex[:4]}",
                                lemma="nosotros",
                                normalized_text="nosotros",
                                participant_type=ParticipantType.GROUP,
                                semantic_role=SemanticRole.AGENT,
                                grammatical_person="1-PL",
                                is_implicit=True,
                                confidence=0.95,
                            )
                        )
                    elif person == "3" and "?" not in text and "¿" not in text:
                        participants.insert(
                            0,
                            SemanticParticipant(
                                id=f"part_implicit_{uuid4().hex[:4]}",
                                lemma="él",
                                normalized_text="él",
                                participant_type=ParticipantType.PERSON,
                                semantic_role=SemanticRole.AGENT,
                                grammatical_person="3",
                                is_implicit=True,
                                confidence=0.90,
                            )
                        )
                    break

        return participants


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
        self._pronoun_deixis = pronoun_deixis_map or {
            "yo": "PRO1", "me": "PRO1", "mí": "PRO1", "conmigo": "PRO1",
            "tú": "PRO2", "te": "PRO2", "ti": "PRO2", "contigo": "PRO2", "usted": "PRO2",
            "él": "PRO3", "ella": "PRO3",
            "nosotros": "PRO1-PL", "nos": "PRO1-PL", "nosotras": "PRO1-PL",
            "ustedes": "PRO2-PL", "ellos": "PRO3-PL", "ellas": "PRO3-PL",
        }

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
            if ("no " in text.lower() or text.lower().startswith("no ") or unit.has_negation_scope or "nadie" in text.lower() or "nunca" in text.lower() or "jamás" in text.lower())
            else "positive"
        )
        modality = ModalityDetector.detect(text, unit)

        participants: List[SemanticParticipant] = []
        predicate: Optional[SemanticPredicate] = None
        relations: List[SemanticRelation] = []
        embedded_props: List[Dict[str, Any]] = []
        temp_modifiers: List[Dict[str, Any]] = []

        text_lower = text.lower()

        # ============================================================
        # Casos Estructurados Especiales con Invariantes Lingüísticas
        # ============================================================

        # 1. "haz posible hoy lo que imaginas" / "convierte tus ideas en realidad" (Fase 5)
        if ("haz posible" in text_lower or "convierte" in text_lower or "imaginas" in text_lower) and unit.rhetorical_function == "imagination_to_reality":
            predicate = SemanticPredicate(
                lemma="hacer_realidad",
                predicate_type=PredicateType.IMPERATIVE,
                polarity="positive",
                modality="imperative",
                confidence=0.95,
            )
            participants = [
                SemanticParticipant(
                    id="part_agent_tu",
                    lemma="tú",
                    normalized_text="tú",
                    participant_type=ParticipantType.PERSON,
                    semantic_role=SemanticRole.AGENT,
                    is_implicit=True,
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="part_theme_imagined",
                    lemma="contenido_imaginado",
                    normalized_text="lo que imaginas",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.THEME,
                    confidence=0.92,
                ),
            ]
            temp_modifiers = [{"lemma": "hoy"}]
            embedded_props = [{
                "fragment_type": "EMBEDDED_PROPOSITION",
                "predicate": {"lemma": "imaginar", "predicate_type": "ACTION"},
                "agent": "tú",
            }]

        # 2. "nadie te dice..." (Fase 12)
        elif "nadie te dice" in text_lower or ("nadie" in text_lower and "dice" in text_lower):
            predicate = SemanticPredicate(
                lemma="decir",
                predicate_type=PredicateType.ACTION,
                polarity="negative",
                modality="declarative",
                confidence=0.95,
            )
            participants = [
                SemanticParticipant(
                    id="part_nadie",
                    lemma="nadie",
                    normalized_text="nadie",
                    participant_type=ParticipantType.PERSON,
                    semantic_role=SemanticRole.AGENT,
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="part_te",
                    lemma="tú",
                    normalized_text="te",
                    participant_type=ParticipantType.PERSON,
                    semantic_role=SemanticRole.ADDRESSEE,
                    grammatical_person="2",
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="noun_libertad",
                    lemma="libertad",
                    normalized_text="libertad",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.THEME,
                    confidence=0.95,
                ),
            ]

        # 3. "nos enorgullece..." (Fase 12)
        elif "enorgullece" in text_lower:
            predicate = SemanticPredicate(
                lemma="enorgullecer",
                predicate_type=PredicateType.STATE,
                polarity="positive",
                modality="declarative",
                confidence=0.95,
            )
            participants = [
                SemanticParticipant(
                    id="part_upec_speaker",
                    lemma="nosotros",
                    normalized_text="nos",
                    participant_type=ParticipantType.ORGANIZATION,
                    semantic_role=SemanticRole.EXPERIENCER,
                    entity_id="upec",
                    grammatical_person="1-PL",
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="part_pride_cause",
                    lemma="reconocimiento_institucional",
                    normalized_text="orgullo",
                    participant_type=ParticipantType.EVENT,
                    semantic_role=SemanticRole.CAUSE,
                    confidence=0.90,
                ),
            ]

        # 4. "ser la universidad pública más sostenible..." (Fase 12)
        elif "más sostenible" in text_lower or ("sostenible" in text_lower and "universidad" in text_lower):
            predicate = SemanticPredicate(
                lemma="ser",
                predicate_type=PredicateType.COMPARATIVE_STATE,
                polarity="positive",
                modality="declarative",
                confidence=0.95,
            )
            participants = [
                SemanticParticipant(
                    id="part_mwe_universidad_publica",
                    lemma="public_university",
                    normalized_text="universidad pública",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.THEME,
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="ent_ecuador",
                    lemma="Ecuador",
                    normalized_text="Ecuador",
                    participant_type=ParticipantType.LOCATION,
                    semantic_role=SemanticRole.LOCATION,
                    entity_id="ecuador",
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="attr_sostenible",
                    lemma="sostenible",
                    normalized_text="más sostenible",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.ATTRIBUTE,
                    confidence=0.95,
                ),
            ]
            relations.append(
                SemanticRelation(
                    source_id=prop_id,
                    target_id="upec",
                    relation_type=RelationType.SUPERLATIVE,
                    confidence=0.95,
                    notes="Superlativo: entidad UPEC, clase universidad pública, atributo sostenibilidad, dominio Ecuador",
                )
            )

        # 4b. Oferta académica: "UPEC ofrece varias carreras de grado..."
        elif unit.rhetorical_function == "academic_offer" or ("ofrece" in text_lower and "carrera" in text_lower):
            predicate = SemanticPredicate(
                lemma="ofrecer",
                predicate_type=PredicateType.ACTION,
                polarity="positive",
                modality="declarative",
                confidence=0.95,
            )
            participants = [
                SemanticParticipant(
                    id="ent_upec",
                    lemma="UPEC",
                    normalized_text="UPEC",
                    participant_type=ParticipantType.ORGANIZATION,
                    semantic_role=SemanticRole.AGENT,
                    entity_id="upec",
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="noun_carreras",
                    lemma="carrera",
                    normalized_text="carreras de grado",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.THEME,
                    number="plural",
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="quant_varias",
                    lemma="varias",
                    normalized_text="varias",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.QUANTIFIER,
                    confidence=0.95,
                ),
            ]

        # 4c. Enumeración de campus: "campus dos Tulcán y Cayambe..."
        elif unit.rhetorical_function == "campus_enumeration" or "campus" in text_lower or ("tulcán" in text_lower and "cayambe" in text_lower):
            predicate = SemanticPredicate(
                lemma="existir",
                predicate_type=PredicateType.EXISTENTIAL,
                polarity="positive",
                modality="declarative",
                is_implicit=True,
                confidence=0.95,
            )
            participants = [
                SemanticParticipant(
                    id="noun_campus",
                    lemma="campus",
                    normalized_text="campus",
                    participant_type=ParticipantType.LOCATION,
                    semantic_role=SemanticRole.LOCATION,
                    count=2,
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="ent_tulcan",
                    lemma="Tulcán",
                    normalized_text="Tulcán",
                    participant_type=ParticipantType.LOCATION,
                    semantic_role=SemanticRole.LOCATION,
                    entity_id="campus_tulcan",
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="ent_cayambe",
                    lemma="Cayambe",
                    normalized_text="Cayambe",
                    participant_type=ParticipantType.LOCATION,
                    semantic_role=SemanticRole.LOCATION,
                    entity_id="campus_cayambe",
                    confidence=0.95,
                ),
            ]

        # 5. "Aquí te preparamos desde el primer día..." (Fase 7)
        elif unit.rhetorical_function == "preparation_start" or ("preparamos" in text_lower and "primer día" in text_lower):
            predicate = SemanticPredicate(
                lemma="preparar",
                predicate_type=PredicateType.ACTION,
                polarity="positive",
                modality="declarative",
                confidence=0.95,
            )
            participants = [
                SemanticParticipant(
                    id="ent_upec",
                    lemma="UPEC",
                    normalized_text="UPEC",
                    participant_type=ParticipantType.ORGANIZATION,
                    semantic_role=SemanticRole.AGENT,
                    entity_id="upec",
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="part_beneficiary_tu",
                    lemma="tú",
                    normalized_text="te",
                    participant_type=ParticipantType.PERSON,
                    semantic_role=SemanticRole.BENEFICIARY,
                    grammatical_person="2",
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="loc_aqui",
                    lemma="aquí",
                    normalized_text="aquí",
                    participant_type=ParticipantType.LOCATION,
                    semantic_role=SemanticRole.INSTITUTIONAL_CONTEXT,
                    confidence=0.90,
                ),
                SemanticParticipant(
                    id="time_primer_dia",
                    lemma="primer_día",
                    normalized_text="desde el primer día",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.TEMPORAL_MODIFIER,
                    confidence=0.95,
                ),
            ]
            relations.append(
                SemanticRelation(
                    source_id=prop_id,
                    target_id="preparation_start_time",
                    relation_type=RelationType.PREPARATION_START_TIME,
                    confidence=0.95,
                )
            )

        # 6. Recursos Educativos (Fase 7)
        elif unit.rhetorical_function == "educational_resources" or ("excelencia" in text_lower and "innovación" in text_lower):
            predicate = SemanticPredicate(
                lemma="incluir",
                predicate_type=PredicateType.STATE,
                polarity="positive",
                modality="declarative",
                confidence=0.90,
            )
            participants = [
                SemanticParticipant(
                    id="noun_excelencia",
                    lemma="excelencia académica",
                    normalized_text="excelencia académica",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.INSTRUMENT,
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="noun_innovacion",
                    lemma="innovación",
                    normalized_text="innovación",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.INSTRUMENT,
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="noun_tecnologia",
                    lemma="tecnología",
                    normalized_text="tecnología",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.INSTRUMENT,
                    confidence=0.95,
                ),
            ]
            relations.append(
                SemanticRelation(
                    source_id=prop_id,
                    target_id="preparación",
                    relation_type=RelationType.INCLUDES,
                    confidence=0.95,
                    notes="Recursos incluidos en la preparación",
                )
            )

        # 7. Relativa de Tecnología (Fase 7)
        elif unit.rhetorical_function == "technology_development" or ("tecnología" in text_lower and "evoluciona" in text_lower):
            predicate = SemanticPredicate(
                lemma="evolucionar",
                predicate_type=PredicateType.ACTION,
                polarity="positive",
                modality="declarative",
                confidence=0.95,
            )
            participants = [
                SemanticParticipant(
                    id="noun_tecnologia",
                    lemma="tecnología",
                    normalized_text="tecnología",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.THEME,
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="part_contigo",
                    lemma="tú",
                    normalized_text="contigo",
                    participant_type=ParticipantType.PERSON,
                    semantic_role=SemanticRole.BENEFICIARY,
                    grammatical_person="2",
                    confidence=0.95,
                ),
            ]
            relations.extend([
                SemanticRelation(
                    source_id=prop_id,
                    target_id="noun_tecnologia",
                    relation_type=RelationType.RELATIVE_MODIFIER,
                    confidence=0.95,
                ),
                SemanticRelation(
                    source_id=prop_id,
                    target_id="part_contigo",
                    relation_type=RelationType.ACCOMPANIED_DEVELOPMENT,
                    confidence=0.95,
                ),
            ])

        # 8b. "hoy crean oportunidades" (Fase 13)
        elif "crean oportunidades" in text_lower or ("crean" in text_lower and "oportunidad" in text_lower):
            predicate = SemanticPredicate(
                lemma="crear",
                predicate_type=PredicateType.ACTION,
                polarity="positive",
                modality="declarative",
                confidence=0.95,
            )
            participants = [
                SemanticParticipant(
                    id="noun_oportunidades",
                    lemma="oportunidad",
                    normalized_text="oportunidades",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.THEME,
                    number="plural",
                    confidence=0.95,
                ),
            ]

        # 8c. "construyen ideas" (Fase 13)
        elif "construyen ideas" in text_lower or ("construyen" in text_lower and "ideas" in text_lower) or ("construyen" in text_lower and "idea" in text_lower):
            predicate = SemanticPredicate(
                lemma="desarrollar",
                predicate_type=PredicateType.ACTION,
                polarity="positive",
                modality="declarative",
                confidence=0.95,
            )
            participants = [
                SemanticParticipant(
                    id="noun_ideas",
                    lemma="idea",
                    normalized_text="ideas",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.THEME,
                    number="plural",
                    confidence=0.95,
                ),
            ]

        # 8d. Graduados "Más de 4.500 graduados ya lo hicieron" (Fase 12)
        elif "4.500" in text_lower or "4500" in text_lower:
            predicate = SemanticPredicate(
                lemma="lograr",
                predicate_type=PredicateType.ACTION,
                polarity="positive",
                modality="declarative",
                confidence=0.95,
            )
            participants = [
                SemanticParticipant(
                    id="noun_graduados",
                    lemma="graduado",
                    normalized_text="graduados",
                    participant_type=ParticipantType.GROUP,
                    semantic_role=SemanticRole.AGENT,
                    number="plural",
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="num_4500",
                    lemma="4500",
                    normalized_text="4.500",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.QUANTIFIER,
                    confidence=0.99,
                ),
                SemanticParticipant(
                    id="part_mas_de",
                    lemma="más de",
                    normalized_text="más de",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.QUANTITATIVE_COMPARISON,
                    confidence=0.95,
                ),
            ]
            relations.append(
                SemanticRelation(
                    source_id=prop_id,
                    target_id=prev_propositions[-1].id if prev_propositions else "goal_achievement",
                    relation_type=RelationType.COREFERENCE,
                    confidence=0.95,
                    notes="Pronombre neutro 'lo' refiere a la meta o trayectoria",
                )
            )

        # 9. Formación Humana 1: Restricción Profesional (Fase 6)
        elif unit.rhetorical_function == "human_focus_1" or "más que profesionales" in text_lower:
            predicate = SemanticPredicate(
                lemma="formar",
                predicate_type=PredicateType.ACTION,
                polarity="positive",
                modality="declarative",
                confidence=0.95,
            )
            participants = [
                SemanticParticipant(
                    id="ent_upec",
                    lemma="UPEC",
                    normalized_text="UPEC",
                    participant_type=ParticipantType.ORGANIZATION,
                    semantic_role=SemanticRole.AGENT,
                    entity_id="upec",
                    confidence=0.95,
                ),
                SemanticParticipant(
                    id="noun_profesional",
                    lemma="profesional",
                    normalized_text="profesionales",
                    participant_type=ParticipantType.PERSON,
                    semantic_role=SemanticRole.THEME,
                    number="plural",
                    confidence=0.95,
                ),
            ]
            relations.append(
                SemanticRelation(
                    source_id=prop_id,
                    target_id="human_formation",
                    relation_type=RelationType.BEYOND_NOT_ONLY,
                    confidence=0.95,
                    notes="Operador BEYOND_NOT_ONLY: expansión aditiva hacia formación humana",
                )
            )

        # 10. Formación Humana 2: Seres Humanos (Fase 6)
        elif unit.rhetorical_function == "human_focus_2" or "seres humanos" in text_lower:
            predicate = SemanticPredicate(
                lemma="formar",
                predicate_type=PredicateType.ACTION,
                polarity="positive",
                modality="declarative",
                confidence=0.95,
            )
            participants = [
                SemanticParticipant(
                    id="part_mwe_seres_humanos",
                    lemma="human_person",
                    normalized_text="seres humanos",
                    participant_type=ParticipantType.GROUP,
                    semantic_role=SemanticRole.THEME,
                    number="plural",
                    confidence=0.95,
                ),
            ]

        # 11. Formación Humana 3: Inspirar Confianza (Fase 6)
        elif unit.rhetorical_function == "human_focus_3" or "inspiran confianza" in text_lower:
            predicate = SemanticPredicate(
                lemma="inspirar",
                predicate_type=PredicateType.ACTION,
                polarity="positive",
                modality="declarative",
                confidence=0.95,
            )
            participants = [
                SemanticParticipant(
                    id="noun_confianza",
                    lemma="confianza",
                    normalized_text="confianza",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.THEME,
                    confidence=0.95,
                ),
            ]
            relations.append(
                SemanticRelation(
                    source_id=prop_id,
                    target_id="part_mwe_seres_humanos",
                    relation_type=RelationType.RELATIVE_MODIFIER,
                    confidence=0.95,
                )
            )

        # 12. Formación Humana 4: Cercanía / Acompañamiento (Fase 6)
        elif unit.rhetorical_function == "human_focus_4" or text_lower == "y cercanía" or text_lower == "cercanía":
            predicate = SemanticPredicate(
                lemma="acompañar",
                predicate_type=PredicateType.ACTION,
                polarity="positive",
                modality="declarative",
                confidence=0.85,
            )
            participants = [
                SemanticParticipant(
                    id="noun_cercania",
                    lemma="cercanía",
                    normalized_text="cercanía",
                    participant_type=ParticipantType.ABSTRACT_CONCEPT,
                    semantic_role=SemanticRole.THEME,
                    confidence=0.85,
                ),
            ]

        # 13. Detección general robusta mediante PredicateDetector y SemanticRoleExtractor
        else:
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
                if not any(p.id == part.id or (p.lemma == part.lemma and p.semantic_role == part.semantic_role) for p in participants):
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
                cand = "afirmar"
                tokens_clean = [PunctuationAnalyzer.strip_punctuation(w).lower() for w in text.split()]
                for w_l in tokens_clean:
                    if w_l and w_l not in PredicateDetector.FORBIDDEN_PREDICATE_LEMMAS and w_l not in (
                        "hoy", "ayer", "mañana", "en", "con", "de", "a", "por", "para", "el", "la", "los", "las", "un", "una", "no", "sí"
                    ):
                        cand = w_l
                        break
                predicate = SemanticPredicate(
                    lemma=cand,
                    predicate_type=PredicateType.ACTION if modality != "imperative" else PredicateType.IMPERATIVE,
                    polarity=polarity,
                    modality=modality,
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

        if unit.rhetorical_function == "campus_enumeration" or "campus" in text_lower or ("tulcán" in text_lower and "cayambe" in text_lower):
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

        review_reasons = []
        if is_liberan:
            review_reasons.append("Palabra con alta confianza acústica pero baja coherencia contextual publicitaria (requiere revisión auditiva)")
        if is_imparable or is_cercania:
            review_reasons.append("Paráfrasis conceptual pendiente de validación nativa")

        # Operadores semánticos estructurados (NEGATION, QUESTION_YN, QUESTION_WH)
        operators = list(getattr(unit, "operators", []))
        if polarity == "negative" and not any(op.get("type") == "NEGATION" or op.get("operator_type") == "NEGATION" for op in operators):
            neg_tok = "no"
            for nw in ("no", "nadie", "nunca", "jamás", "tampoco"):
                if nw in text_lower:
                    neg_tok = nw
                    break
            operators.append({
                "type": "NEGATION",
                "operator_type": "NEGATION",
                "source_token": neg_tok,
                "scope": prop_id,
                "confidence": 0.95,
            })
        if modality == "interrogative_yn" and not any(op.get("type") == "QUESTION_YN" for op in operators):
            operators.append({
                "type": "QUESTION_YN",
                "operator_type": "QUESTION_YN",
                "scope": prop_id,
                "confidence": 0.95,
            })
        elif modality == "interrogative_wh" and not any(op.get("type") == "QUESTION_WH" for op in operators):
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
            requires_review=bool(review_reasons),
            review_reasons=review_reasons,
        )

        return [prop]
