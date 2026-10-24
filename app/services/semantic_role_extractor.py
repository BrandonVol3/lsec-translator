"""
Detector de predicados y extractor de participantes con roles semánticos (LSEC 2.1.1).

Extraído de `semantic_parser.py` para cumplir con el principio de Responsabilidad Única (SRP).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from app.core.schemas import (
    ParticipantType,
    PredicateType,
    SemanticParticipant,
    SemanticPredicate,
    SemanticRole,
)
from app.services.semantic_constants import (
    CONSUMABLE_NOUNS as _CONSUMABLE_NOUNS_CONST,
    FORBIDDEN_PREDICATE_LEMMAS as _FORBIDDEN_PREDICATE_LEMMAS_CONST,
    LOCATION_NOUNS as _LOCATION_NOUNS_CONST,
    PERSON_NOUNS as _PERSON_NOUNS_CONST,
)
from app.services.semantic_verb_morphology import SpanishVerbLexicon
from app.services.text_normalizer import PunctuationAnalyzer


class PredicateDetector:
    """Detector y validador del predicado principal de una proposición con invariantes estrictas."""

    FORBIDDEN_PREDICATE_LEMMAS: Set[str] = _FORBIDDEN_PREDICATE_LEMMAS_CONST

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

        # 0. Priorizar el verbo sintáctico principal (ROOT/VERB) antes de
        # recorrer el inventario. Esto evita que un sustantivo homógrafo
        # (*estudio*, *formas*) desplace al verdadero predicado.
        if doc is not None:
            verb_tokens = [
                t for t in doc
                if t.pos_ in ("VERB", "AUX")
                and not SpanishVerbLexicon.has_nominal_context(t)
            ]
            verb_tokens.sort(key=lambda t: (t.dep_ != "ROOT", t.i))
            for t in verb_tokens:
                t_clean = PunctuationAnalyzer.strip_punctuation(t.text.lower())
                if not t_clean or t_clean in cls.FORBIDDEN_PREDICATE_LEMMAS:
                    continue
                if t_clean in SpanishVerbLexicon.NOMINAL_HOMOGRAPHS:
                    continue
                if t.dep_ in ("aux", "aux:pass", "cop") and any(
                    ot.pos_ == "VERB" and ot.i != t.i for ot in doc
                ):
                    continue
                t_lemma = (
                    SpanishVerbLexicon.contextual_verb_lemma(t)
                    or SpanishVerbLexicon.get_lemma(t_clean, pos=t.pos_)
                    or (lemma_overrides.get(t_clean) if lemma_overrides else None)
                    or SpanishVerbLexicon.normalize_verb_lemma(t_clean, t.lemma_.lower(), pos=t.pos_)
                )
                t_lemma = PunctuationAnalyzer.strip_punctuation(t_lemma)
                if not t_lemma or t_lemma in cls.FORBIDDEN_PREDICATE_LEMMAS:
                    continue
                detected_lemma = t_lemma
                if t_lemma in ("ser", "estar"):
                    predicate_type = PredicateType.STATE
                elif t_lemma == "haber":
                    predicate_type = PredicateType.EXISTENTIAL
                elif modality == "imperative":
                    predicate_type = PredicateType.IMPERATIVE
                else:
                    predicate_type = PredicateType.ACTION
                break
            if detected_lemma:
                return SemanticPredicate(
                    lemma=detected_lemma,
                    predicate_type=predicate_type,
                    polarity=polarity,
                    modality=modality,
                    confidence=0.95,
                )

        # 1. Priorizar verbos explícitos por inventario morfológico
        doc_pos_seq: List[Tuple[str, str]] = []
        doc_tokens_seq: List[Any] = []
        if doc is not None:
            for dt in doc:
                if dt.is_space or dt.is_punct:
                    continue
                dt_clean = PunctuationAnalyzer.strip_punctuation(dt.text.lower())
                if dt_clean:
                    doc_pos_seq.append((dt_clean, dt.pos_))
                    doc_tokens_seq.append(dt)

        for idx_w, w in enumerate(tokens_lower):
            if w in SpanishVerbLexicon.NOMINAL_HOMOGRAPHS:
                continue
            if idx_w < len(doc_tokens_seq) and SpanishVerbLexicon.has_nominal_context(doc_tokens_seq[idx_w]):
                continue
            pos_guess = None
            if idx_w < len(doc_pos_seq) and doc_pos_seq[idx_w][0] == w:
                pos_guess = doc_pos_seq[idx_w][1]
            if w in SpanishVerbLexicon.POS_GATED_LEMMAS and pos_guess not in ("VERB", "AUX"):
                other_verb = any(
                    (
                        j < len(doc_pos_seq)
                        and doc_pos_seq[j][0] == other
                        and doc_pos_seq[j][1] in ("VERB", "AUX")
                    )
                    or SpanishVerbLexicon.get_lemma(
                        other,
                        pos=(
                            doc_pos_seq[j][1]
                            if j < len(doc_pos_seq) and doc_pos_seq[j][0] == other
                            else None
                        ),
                    )
                    is not None
                    for j, other in enumerate(tokens_lower)
                    if j != idx_w
                )
                if other_verb:
                    continue
                pos_guess = "VERB"
            verb_lemma = (
                SpanishVerbLexicon.contextual_verb_lemma(doc_tokens_seq[idx_w])
                if idx_w < len(doc_tokens_seq)
                else None
            ) or SpanishVerbLexicon.get_lemma(w, pos=pos_guess)
            if verb_lemma:
                if verb_lemma in ("ser", "estar", "haber") and (
                    any(
                        SpanishVerbLexicon.get_lemma(other) not in (None, "ser", "estar", "haber")
                        for other in tokens_lower if other != w
                    )
                    or (
                        verb_lemma == "haber"
                        and idx_w + 1 < len(tokens_lower)
                        and tokens_lower[idx_w + 1].endswith(("ado", "ido", "to", "so", "cho"))
                    )
                ):
                    continue
                if (
                    verb_lemma == "ir"
                    and idx_w + 2 < len(tokens_lower)
                    and tokens_lower[idx_w + 1] == "a"
                    and (
                        SpanishVerbLexicon.get_lemma(tokens_lower[idx_w + 2]) is not None
                        or tokens_lower[idx_w + 2].endswith(("ar", "er", "ir"))
                    )
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
                if t_clean in cls.FORBIDDEN_PREDICATE_LEMMAS or t_clean in SpanishVerbLexicon.NOMINAL_HOMOGRAPHS:
                    continue
                if t.pos_ in ("VERB", "AUX"):
                    if t.dep_ in ("aux", "aux:pass", "cop") and any(ot.pos_ == "VERB" for ot in doc):
                        continue
                    if any(
                        c.dep_ in ("amod", "det") or (c.dep_ == "compound" and c.text.lower() not in ("cabo", "acuerdo", "cuenta", "parte"))
                        for c in t.children
                    ) or (
                        t.dep_ == "conj" and t.head.pos_ in ("NOUN", "PROPN")
                    ):
                        continue
                    t_lemma = (
                        SpanishVerbLexicon.get_lemma(t_clean, pos=t.pos_)
                        or (lemma_overrides.get(t_clean) if lemma_overrides else None)
                        or SpanishVerbLexicon.normalize_verb_lemma(t_clean, t.lemma_.lower(), pos=t.pos_)
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

    CONSUMABLE_NOUNS: Set[str] = _CONSUMABLE_NOUNS_CONST
    LOCATION_NOUNS: Set[str] = _LOCATION_NOUNS_CONST
    PERSON_NOUNS: Set[str] = _PERSON_NOUNS_CONST

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

        doc_token_by_start = {t.idx: t for t in doc} if doc is not None else {}

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
                is_pre_verb_agent = (
                    pred_token_idx is not None
                    and idx < pred_token_idx
                    and ("seres" in mwe.source_phrase or part_type in (ParticipantType.GROUP, ParticipantType.PERSON))
                )
                if is_pre_verb_agent:
                    has_explicit_agent = True
                participants.append(
                    SemanticParticipant(
                        id=f"part_{mwe.id}",
                        lemma=mwe.semantic_concept,
                        normalized_text=mwe.matched_text,
                        participant_type=part_type,
                        semantic_role=SemanticRole.AGENT if is_pre_verb_agent else SemanticRole.THEME,
                        number="plural" if "seres" in mwe.source_phrase else "singular",
                        confidence=mwe.confidence,
                    )
                )
                continue
            elif mwe:
                continue

            # 1. Pronombres personales (sujetos vs. clíticos de objeto)
            if w_clean in pronoun_deixis or w_clean in (
                "yo", "tú", "tu", "él", "ella", "usted", "nosotros", "nosotras", "ustedes", "ellos", "ellas", "te", "me", "nos", "le", "les"
            ):
                if w_clean == "yo":
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
                elif w_clean in ("me", "mí", "conmigo"):
                    role = (
                        SemanticRole.EXPERIENCER
                        if pred_lemma in ("gustar", "enorgullecer", "encantar", "doler", "importar", "interesar", "molestar", "faltar")
                        else SemanticRole.ADDRESSEE
                    )
                    participants.append(
                        SemanticParticipant(
                            id=f"part_clitic_{uuid4().hex[:4]}",
                            lemma="yo",
                            normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                            participant_type=ParticipantType.PERSON,
                            semantic_role=role,
                            grammatical_person="1",
                            confidence=0.95,
                        )
                    )
                elif w_clean == "tú":
                    participants.append(
                        SemanticParticipant(
                            id=f"part_agent_{uuid4().hex[:4]}",
                            lemma="tú",
                            normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                            participant_type=ParticipantType.PERSON,
                            semantic_role=SemanticRole.AGENT,
                            grammatical_person="2",
                            confidence=0.95,
                        )
                    )
                    has_explicit_agent = True
                elif w_clean in ("te", "ti", "contigo"):
                    role = (
                        SemanticRole.ADDRESSEE
                        if pred_lemma in ("decir", "explicar", "avisar", "preguntar", "llamar")
                        else (SemanticRole.EXPERIENCER if pred_lemma in ("gustar", "enorgullecer") else SemanticRole.BENEFICIARY)
                    )
                    participants.append(
                        SemanticParticipant(
                            id=f"part_clitic_{uuid4().hex[:4]}",
                            lemma="tú",
                            normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                            participant_type=ParticipantType.PERSON,
                            semantic_role=role,
                            grammatical_person="2",
                            confidence=0.95,
                        )
                    )
                elif w_clean in ("él", "ella", "usted"):
                    participants.append(
                        SemanticParticipant(
                            id=f"part_agent_{uuid4().hex[:4]}",
                            lemma=w_clean,
                            normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                            participant_type=ParticipantType.PERSON,
                            semantic_role=SemanticRole.AGENT,
                            grammatical_person="3" if w_clean != "usted" else "2",
                            confidence=0.95,
                        )
                    )
                    has_explicit_agent = True
                elif w_clean in ("nosotros", "nosotras"):
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
                elif w_clean == "nos":
                    role = SemanticRole.EXPERIENCER if pred_lemma in ("enorgullecer", "gustar") else SemanticRole.BENEFICIARY
                    participants.append(
                        SemanticParticipant(
                            id=f"part_clitic_{uuid4().hex[:4]}",
                            lemma="nosotros",
                            normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                            participant_type=ParticipantType.GROUP,
                            semantic_role=role,
                            grammatical_person="1-PL",
                            confidence=0.95,
                        )
                    )
                elif w_clean in ("ellos", "ellas", "ustedes"):
                    participants.append(
                        SemanticParticipant(
                            id=f"part_agent_{uuid4().hex[:4]}",
                            lemma=w_clean,
                            normalized_text=PunctuationAnalyzer.strip_punctuation(raw_w),
                            participant_type=ParticipantType.GROUP,
                            semantic_role=SemanticRole.AGENT,
                            grammatical_person="3-PL" if w_clean != "ustedes" else "2-PL",
                            confidence=0.95,
                        )
                    )
                    has_explicit_agent = True
                continue

            # 2. Interrogativos
            is_q_sentence = "?" in text or "¿" in text
            if w_clean in ("quién", "quiénes") or (w_clean in ("quien", "quienes") and is_q_sentence):
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
            elif (
                w_clean == "qué"
                or (
                    w_clean == "que"
                    and is_q_sentence
                    and (
                        "¿" in raw_w
                        or idx == 0
                        or (idx == 1 and token_offsets[0][3] in ("por", "para", "a", "de", "en", "con"))
                    )
                )
            ) and is_q_sentence:
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
            elif w_clean == "dónde" or (w_clean == "donde" and is_q_sentence):
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
            elif w_clean == "cuándo" or (w_clean == "cuando" and is_q_sentence and ("¿" in raw_w or idx == 0)):
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
            elif (w_clean == "cómo" or (w_clean == "como" and ("¿" in raw_w or idx == 0))) and is_q_sentence:
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
                "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "a", "al", "en", "por", "para", "con", "sin", "sobre", "tras", "y", "o", "pero", "si", "no",
                "porque", "cuando", "mientras", "aunque", "como", "donde", "quien", "que", "cual", "embargo", "obstante", "desde", "hasta", "hacia", "según", "durante", "mediante", "entre",
            ) and w_clean not in SpanishVerbLexicon.COPULA_FORMS and len(w_clean) > 2 and not SpanishVerbLexicon.is_verb(w_clean):
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
            for idx, (_, _, _, w_clean) in enumerate(token_offsets):
                doc_tok = doc_token_by_start.get(token_offsets[idx][0])
                if doc_tok is not None and (
                    SpanishVerbLexicon.has_nominal_context(doc_tok)
                    or doc_tok.pos_ in ("DET", "ADP", "CCONJ", "SCONJ")
                ):
                    continue
                if idx > 0 and token_offsets[idx - 1][3] in (
                    "el", "la", "los", "las", "un", "una", "unos", "unas",
                    "mi", "mis", "tu", "tus", "su", "sus", "este", "esta", "ese", "esa",
                    "nuestro", "nuestra", "nuestros", "nuestras",
                ):
                    continue
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
                    elif person == "3" and "?" not in text and "¿" not in text and pred_lemma not in ("llover", "nevar", "granizar", "haber", "amanecer", "anochecer"):
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
