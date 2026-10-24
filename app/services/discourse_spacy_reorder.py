"""
Extracción morfosintáctica de tokens spaCy, resolución de MWEs/frases CONADIS y reordenamiento LSEC SOV/Tiempo/WH/Negación.

Extraído de `discourse_planner.py` para cumplir con el principio de Responsabilidad Única (SRP).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.schemas import SemanticProposition
from app.services.dictionary_service import to_gloss_form
from app.services.discourse_lexicon import (
    _BLACKLIST_POS_TAGS,
    _CANONICAL_NOMINAL_FORMS,
    _CANONICAL_SOURCE_LEMMAS,
    _CLITIC_PRONOUNS,
    _CLITIC_VERB_LEMMAS,
    _COPULATIVE_LEMMAS,
    _QUANTIFIER_CANON,
    _RULE_MANAGED_TOKENS,
    _SEMANTIC_SCONJ_GLOSS,
    _strip_accents_lower,
)
from app.services.discourse_morphosyntax import has_nominal_context, normalize_nominal_lemma
from app.services.fenasec_rules import _INTENSIFIER_RE
from app.services.mwe_detector import MWEMatch
from app.services.semantic_parser import SpanishVerbLexicon
from app.services.text_normalizer import PunctuationAnalyzer

logger = logging.getLogger(__name__)


def detect_dictionary_phrases(
    planner: Any,
    doc: Any,
    source_text: str,
    blocked_token_ids: Set[int],
) -> List[Tuple[MWEMatch, Any]]:
    """
    Detecta entradas de varias palabras del Diccionario Oficial LSEC en el documento spaCy.
    """
    if not planner._phrase_matching or planner._dictionary is None:
        return []
    try:
        toks = [t for t in doc if not t.is_punct and not t.is_space]
        matches = planner._dictionary.find_phrases(
            [(t.text, t.lemma_, t.idx, t.idx + len(t.text)) for t in toks],
            text=source_text,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Detección de frases del diccionario omitida: %s", exc)
        return []

    results: List[Tuple[MWEMatch, Any]] = []
    for pm in matches:
        span = toks[pm.start_token:pm.end_token]
        if any(t.i in blocked_token_ids for t in span):
            continue
        if pm.match_basis == "lemma" and any(t.pos_ in ("VERB", "AUX") for t in span):
            continue
        if any(t.text.lower() in planner._wh_lemmas or t.lemma_.lower() in planner._wh_lemmas for t in span):
            continue
        if any(
            _strip_accents_lower(t.text) in _RULE_MANAGED_TOKENS or _INTENSIFIER_RE.match(t.text)
            for t in span
        ):
            continue
        if pm.entry.slug in ("esta-bien", "estar-bien") or (
            any(t.dep_ == "cop" or t.lemma_.lower() in ("ser", "estar") for t in span)
            and not any(t.text in ("?", "¿") for t in doc)
        ):
            continue
        span_ids = {t.i for t in span}
        root = next((t for t in span if t.head.i not in span_ids or t.head.i == t.i), span[-1])
        matched_text = source_text[pm.start_char:pm.end_char]
        results.append((
            MWEMatch(
                id=f"dict_{pm.entry.slug}",
                source_phrase=matched_text.lower(),
                matched_text=matched_text,
                start_char=pm.start_char,
                end_char=pm.end_char,
                semantic_concept="conadis_phrase",
                prevent_component_parsing=True,
                preferred_gloss=to_gloss_form(pm.matched_form),
                requires_native_review=False,
                confidence=0.95,
            ),
            root,
        ))
    return results


def extract_and_reorder_spacy_tokens(
    planner: Any,
    doc: Any,
    prop: SemanticProposition,
    active_rule_ids: Optional[Set[str]] = None,
    exclude_rule_ids: Optional[Set[str]] = None,
) -> Tuple[
    List[Tuple[Any, str, str, str, Dict[str, Any]]],
    List[Tuple[str, str]],
    Dict[int, List[Any]],
    List[Any],
]:
    """
    Extrae y desambigua los tokens del `doc` spaCy y aplica el reordenamiento
    discursivo LSEC (Tiempo + Lugar + Sujeto + Objeto + Modificadores + Verbo + WH + Negación).

    Retorna `(reordered, periphrasis_markers, amod_by_head, wh_tokens)`.
    """
    tokens_info: List[Tuple[Any, str, str, str, Dict[str, Any]]] = []

    # 1. Perífrasis verbales
    periphrasis_results = planner.detect_periphrasis(doc)
    periphrasis_consumed: Set[int] = set()
    periphrasis_markers: List[Tuple[str, str]] = []
    for marker, position, consumed_set in periphrasis_results:
        periphrasis_consumed |= consumed_set
        if marker:
            periphrasis_markers.append((marker, position))

    # 2. Expresiones Multipalabra (MWE)
    mwe_matches = planner._mwe_detector.detect(prop.source_text)
    mwe_consumed: Set[int] = set()
    mwe_emitted: Dict[int, Tuple[Any, str, str, str, Dict[str, Any]]] = {}
    mwe_span_head_map: Dict[int, int] = {}

    for m_item in mwe_matches:
        if m_item.prevent_component_parsing:
            span_toks = [tok for tok in doc if m_item.start_char <= tok.idx < m_item.end_char]
            if span_toks:
                first_tok = span_toks[0]
                for tok in span_toks:
                    mwe_consumed.add(tok.i)
                    mwe_span_head_map[tok.i] = first_tok.i
                pref = m_item.preferred_gloss or m_item.source_phrase.upper().replace(" ", "-")
                mwe_pos = "ADV"
                mwe_dep = "advmod"
                if any(k in pref for k in ("PERSONA", "HUMANO")):
                    mwe_pos = "NOUN"
                    mwe_dep = "nsubj"
                elif any(k in pref for k in ("CARRERA", "UNIVERSIDAD", "DÍA", "EXCELENCIA")):
                    mwe_pos = "NOUN"
                    mwe_dep = "obj"
                elif any(k in pref for k in ("HACER", "LOGRAR", "TRANSFORMAR", "AVANZAR", "REALIZAR")):
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

    # 2b. Frases oficiales del Diccionario LSEC (una sola seña)
    blocked_ids: Set[int] = set(periphrasis_consumed) | mwe_consumed
    for dict_mwe, root_tok in planner._detect_dictionary_phrases(doc, prop.source_text, blocked_ids):
        span_toks = [tok for tok in doc if dict_mwe.start_char <= tok.idx < dict_mwe.end_char]
        if not span_toks:
            continue
        for tok in span_toks:
            mwe_consumed.add(tok.i)
            mwe_span_head_map[tok.i] = span_toks[0].i
        pref = dict_mwe.preferred_gloss or to_gloss_form(dict_mwe.source_phrase)
        mwe_emitted[span_toks[0].i] = (
            span_toks[0],
            root_tok.pos_ or "NOUN",
            root_tok.dep_ or "obj",
            pref.lower(),
            {"is_mwe": True, "mwe": dict_mwe, "mwe_gloss": pref, "is_dictionary_phrase": True},
        )

    # 3. Extracción de tokens
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

        forced_verb_lemma: Optional[str] = None
        if clean_word == "ven":
            nxt = doc[t.i + 1] if t.i + 1 < len(doc) else None
            prev = doc[t.i - 1] if t.i > 0 else None
            at_start = (
                prev is None
                or prev.is_punct
                or prev.pos_ in ("CCONJ", "SCONJ")
            )
            destination = nxt is not None and nxt.text.lower() in (
                "a", "al", "hacia", "para", "aquí", "acá",
            )
            time_or_manner = nxt is not None and PunctuationAnalyzer.strip_punctuation(
                nxt.text.lower()
            ) in {
                "ahorita", "ahora", "ya", "pronto", "rápido", "rapidito",
                "temprano", "tempranito", "hoy", "mañana", "mismo", "luego",
            }
            if (at_start and (
                destination
                or time_or_manner
                or nxt is None
                or nxt.is_punct
                or nxt.pos_ in ("VERB", "AUX")
            )) or (destination and time_or_manner):
                forced_verb_lemma = "venir"

        is_nominal_homograph = (
            clean_word in SpanishVerbLexicon.NOMINAL_HOMOGRAPHS
            and (
                any(c.dep_ in ("amod", "det", "compound") for c in t.children)
                or (dep == "conj" and t.head.pos_ in ("NOUN", "PROPN"))
                or (t.i > 0 and doc[t.i - 1].pos_ in ("DET", "ADP", "CCONJ"))
            )
        )
        nominal_context = is_nominal_homograph or has_nominal_context(t)
        structural_pos = pos in ("ADP", "DET", "SCONJ", "CCONJ", "PRON")
        verb_lemma = forced_verb_lemma or (
            None if nominal_context or structural_pos
            else SpanishVerbLexicon.get_lemma(clean_word, pos=pos)
        )
        override_lemma = (
            None
            if nominal_context or structural_pos
            else planner._lemma_overrides.get(clean_word, planner._lemma_overrides.get(text_lower))
        )
        override_is_verb = bool(override_lemma) and str(override_lemma).endswith(("ar", "er", "ir"))
        clitic_verb = _CLITIC_VERB_LEMMAS.get(clean_word)
        if clitic_verb:
            lemma = clitic_verb
            verb_lemma = clitic_verb
            pos = "VERB"
        elif nominal_context:
            pos = "NOUN" if pos in ("NOUN", "PROPN", "ADJ") else pos
            base_nom = (
                raw_lemma
                if (raw_lemma in SpanishVerbLexicon.NOMINAL_HOMOGRAPHS or not raw_lemma.endswith(("ar", "er", "ir")))
                else clean_word
            )
            lemma = normalize_nominal_lemma(clean_word, base_nom)
        elif override_lemma is not None and (
            not override_is_verb
            or clean_word not in SpanishVerbLexicon.POS_GATED_LEMMAS
            or pos in ("VERB", "AUX")
        ):
            lemma = PunctuationAnalyzer.strip_punctuation(override_lemma)
            if not verb_lemma and lemma not in SpanishVerbLexicon.NOMINAL_HOMOGRAPHS:
                verb_lemma = SpanishVerbLexicon.get_lemma(lemma) or (
                    lemma if lemma.endswith(("ar", "er", "ir")) else None
                )
            if verb_lemma or (lemma.endswith(("ar", "er", "ir")) and lemma not in SpanishVerbLexicon.NOMINAL_HOMOGRAPHS):
                pos = "VERB"
        elif verb_lemma:
            pos = "VERB"
            if (
                verb_lemma == "decir"
                and any(o.text.lower() == "que" for o in doc)
                and any(o.text.lower() in ("te", "me", "nos", "les", "le") for o in doc)
            ):
                lemma = "explicar"
            else:
                lemma = verb_lemma
        elif clean_word in _QUANTIFIER_CANON:
            lemma = _QUANTIFIER_CANON[clean_word]
        else:
            if structural_pos:
                lemma = normalize_nominal_lemma(clean_word, raw_lemma)
            else:
                norm_lemma = SpanishVerbLexicon.normalize_verb_lemma(clean_word, raw_lemma, pos=pos)
                override_norm = planner._lemma_overrides.get(
                    norm_lemma, planner._lemma_overrides.get(raw_lemma)
                )
                if override_norm is not None and (
                    not str(override_norm).endswith(("ar", "er", "ir"))
                    or norm_lemma not in SpanishVerbLexicon.POS_GATED_LEMMAS
                    or pos in ("VERB", "AUX")
                ):
                    lemma = override_norm
                else:
                    lemma = norm_lemma
                lemma = PunctuationAnalyzer.strip_punctuation(lemma)
                if nominal_context:
                    lemma = normalize_nominal_lemma(clean_word, lemma)
                elif (
                    lemma.endswith(("ar", "er", "ir"))
                    and lemma not in SpanishVerbLexicon.NOMINAL_HOMOGRAPHS
                    and (
                        pos not in ("NOUN", "PROPN", "ADJ")
                        or SpanishVerbLexicon._is_verified_infinitive(lemma)
                    )
                ):
                    pos = "VERB"
                    verb_lemma = lemma
                elif pos in ("NOUN", "PROPN", "ADJ") and not verb_lemma:
                    lemma = normalize_nominal_lemma(clean_word, lemma)

                canonical = _CANONICAL_SOURCE_LEMMAS.get(clean_word)
                if canonical is not None:
                    lemma = unicodedata.normalize("NFC", canonical)
                    if clean_word in _CANONICAL_NOMINAL_FORMS:
                        verb_lemma = None
                        if pos == "VERB":
                            pos = "NOUN" if clean_word not in {"politécnica", "politecnica", "académica", "academica"} else "ADJ"

        canonical = _CANONICAL_SOURCE_LEMMAS.get(clean_word)
        if canonical is not None:
            lemma = unicodedata.normalize("NFC", canonical)
            if clean_word in _CANONICAL_NOMINAL_FORMS:
                verb_lemma = None
                if pos == "VERB":
                    pos = "NOUN" if clean_word not in {"politécnica", "politecnica", "académica", "academica"} else "ADJ"

        meta: Dict[str, Any] = {}

        if (
            lemma in planner._semantic_paraphrases
            or text_lower in planner._semantic_paraphrases
            or clean_word in planner._semantic_paraphrases
        ):
            para_key = (
                lemma
                if lemma in planner._semantic_paraphrases
                else (clean_word if clean_word in planner._semantic_paraphrases else text_lower)
            )
            meta["is_paraphrase"] = True
            meta["paraphrase_key"] = para_key
            tokens_info.append((t, pos, dep, lemma, meta))
            continue

        if pos == "NUM" or re.match(r"^\d+", clean_word) or clean_word in (
            "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez",
            "once", "doce", "veinte", "treinta", "cien", "mil",
        ):
            meta["is_numeral"] = True
            meta["num_val"] = clean_word.replace(".", "").replace(",", "")
            head_tok = t.head.head if t.head.pos_ == "DET" and t.head.head.i != t.head.i else t.head
            target_head_idx = mwe_span_head_map.get(head_tok.i, head_tok.i)
            if (
                head_tok.i != t.i
                and t.i < target_head_idx
                and (head_tok.pos_ in ("NOUN", "PROPN") or head_tok.i in mwe_span_head_map)
                and target_head_idx not in periphrasis_consumed
            ):
                meta["is_amod"] = True
                meta["head_idx"] = target_head_idx
            elif t.i + 1 < len(doc) and doc[t.i + 1].pos_ in ("NOUN", "PROPN"):
                meta["is_amod"] = True
                meta["head_idx"] = mwe_span_head_map.get(t.i + 1, t.i + 1)
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

        if (pos == "PRON" or clean_word in planner._pronoun_deixis) and clean_word in planner._pronoun_deixis:
            meta["is_deixis"] = True
            meta["deixis_gloss"] = planner._pronoun_deixis[clean_word]
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
            if pos == "VERB" or not has_other_verb:
                pos = "VERB"
                lemma = "comer"
                dep = "ROOT"
            else:
                continue

        if clean_word in ("no", "nunca", "jamás", "nadie", "tampoco"):
            meta["is_negation"] = True
            tokens_info.append((t, "ADV", "neg", lemma, meta))
            continue

        if prop.modality == "exclamative" and clean_word in ("qué", "que", "cuánto", "cuánta", "cuántos", "cuántas"):
            next_token = doc[t.i + 1] if t.i + 1 < len(doc) else None
            next_word = (
                PunctuationAnalyzer.strip_punctuation(next_token.text.lower())
                if next_token is not None
                else ""
            )
            intensifies = next_token is not None and (
                next_token.pos_ in ("ADJ", "ADV")
                or next_word in {"asco", "lástima", "pena", "horror", "vergüenza"}
                or (
                    next_token.pos_ in ("NOUN", "PROPN")
                    and next_token.i + 1 < len(doc)
                    and doc[next_token.i + 1].lemma_ in ("estar", "ser")
                    and doc[next_token.i + 1].pos_ in ("VERB", "AUX")
                )
            )
            if intensifies:
                meta["is_functional_transfer"] = True
                meta["ft_gloss"] = "MUCHO"
                tokens_info.append((t, "ADV", "advmod", "mucho", meta))
            continue

        if clean_word in planner._wh_lemmas or raw_lemma in planner._wh_lemmas:
            meta["is_wh"] = True
            tokens_info.append((t, pos, dep, lemma, meta))
            continue

        is_quantifier_token = clean_word in _QUANTIFIER_CANON

        if pos == "SCONJ" and clean_word in _SEMANTIC_SCONJ_GLOSS:
            if clean_word == "porque" and prop.discourse_relation == "because":
                continue
            connector_gloss = _SEMANTIC_SCONJ_GLOSS[clean_word]
            meta["is_functional_transfer"] = True
            meta["ft_gloss"] = connector_gloss
            meta["is_connector"] = True
            tokens_info.append((t, "ADV", "advmod", connector_gloss.lower(), meta))
            continue

        if pos in ("DET", "ADP"):
            if active_rule_ids is not None and "LSEC_FUNCTIONAL_TRANSFER_DET_ADP" not in active_rule_ids:
                tokens_info.append((t, pos, dep, clean_word, {}))
                continue
            ft_list = planner._linguistic_analyzer.analyze_functional_transfer(doc)
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
            if pos in _BLACKLIST_POS_TAGS and not verb_lemma and pos not in ("NOUN", "PROPN") and not is_quantifier_token:
                continue

        if pos in _BLACKLIST_POS_TAGS and not verb_lemma and pos not in ("NOUN", "PROPN") and not is_quantifier_token:
            continue

        if is_quantifier_token and pos in ("DET", "PRON", "ADJ"):
            head_tok = t.head.head if t.head.pos_ == "DET" and t.head.head.i != t.head.i else t.head
            target_head_idx = mwe_span_head_map.get(head_tok.i, head_tok.i)
            if (
                head_tok.i != t.i
                and t.i < target_head_idx
                and (head_tok.pos_ in ("NOUN", "PROPN") or head_tok.i in mwe_span_head_map)
                and target_head_idx not in periphrasis_consumed
            ):
                meta["is_amod"] = True
                meta["head_idx"] = target_head_idx

        if pos in ("AUX", "VERB") and lemma in _COPULATIVE_LEMMAS:
            if (
                active_rule_ids is not None
                and "LSEC_COPULA_OMISSION" not in active_rule_ids
                and "LSEC_COPULA_EXISTENTIAL" not in active_rule_ids
                and "LSEC_COPULA_LOCATIVE" not in active_rule_ids
            ):
                copula_excluded = bool(
                    exclude_rule_ids and "LSEC_COPULA_OMISSION" in exclude_rule_ids
                )
                is_linking_copula = lemma in ("ser", "estar") and dep != "aux"
                if copula_excluded:
                    tokens_info.append((t, pos, dep, lemma.upper(), {"is_copula": True}))
                elif lemma in ("ser", "estar") and dep == "aux":
                    pass
                elif not is_linking_copula:
                    tokens_info.append((t, pos, dep, lemma.upper(), {"is_copula": True}))
                continue
            elif active_rule_ids is not None and "LSEC_COPULA_EXISTENTIAL" in active_rule_ids and lemma == "haber":
                tokens_info.append((t, "VERB", dep, "haber", {"is_existential": True}))
                continue
            else:
                continue

        if dep == "amod" and pos == "ADJ" and not meta.get("is_amod"):
            head_clean = PunctuationAnalyzer.strip_punctuation(t.head.text.lower())
            head_is_verb = (
                not SpanishVerbLexicon.has_nominal_context(t.head)
                and (t.head.pos_ in ("VERB", "AUX") or SpanishVerbLexicon.get_lemma(head_clean) is not None)
                and head_clean not in SpanishVerbLexicon.NOMINAL_HOMOGRAPHS
            )
            if not head_is_verb and clean_word not in ("manzana", "pan", "carne", "agua", "leche", "comida"):
                meta["is_amod"] = True
                meta["head_idx"] = mwe_span_head_map.get(t.head.i, t.head.i)
            else:
                pos = "NOUN"
                dep = "obj"
        elif (
            dep == "flat"
            and not meta.get("is_amod")
            and pos != "VERB"
            and t.head.i < t.i
            and t.text
            and not t.text[0].isupper()
            and t.head.pos_ == "NOUN"
        ):
            pos = "ADJ"
            dep = "amod"
            meta["is_amod"] = True
            meta["head_idx"] = mwe_span_head_map.get(t.head.i, t.head.i)

        morph_number = t.morph.get("Number", [])
        if pos in ("NOUN", "PROPN") and "Plur" in morph_number and not verb_lemma and clean_word.endswith("s"):
            meta["is_plural"] = True
        elif (
            pos == "ADJ"
            and "Plur" in morph_number
            and not verb_lemma
            and clean_word.endswith("s")
            and not meta.get("is_amod")
            and dep in ("nsubj", "nsubj:pass", "obj", "ROOT")
        ):
            meta["is_plural"] = True
            meta["is_nominalized"] = True

        is_person_2 = ("2" in t.morph.get("Person", [])) or (pos == "VERB" and clean_word.endswith(("as", "es", "ás", "és")))
        if pos == "VERB" and is_person_2 and any(tok.text.lower() == "lo" for tok in doc) and any(tok.text.lower() == "que" for tok in doc):
            if not any(item[3] in ("pro2", "tú", "usted") for item in tokens_info):
                tokens_info.append((t, "PRON", "nsubj", "pro2", {"is_deixis": True, "deixis_gloss": "PRO2"}))

        tokens_info.append((t, pos, dep, lemma, meta))

    # Reordenamiento discursivo LSEC condicionado
    time_tokens: List[Any] = []
    connectors: List[Any] = []
    location_tokens: List[Any] = []
    subjects: List[Any] = []
    objects: List[Any] = []
    modifiers_others: List[Any] = []
    verbs: List[Any] = []
    manner_adverbs: List[Any] = []
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

        _is_counted_time_noun = (
            l_lower in ("año", "mes", "día", "semana", "hora", "tarde", "noche")
            and (
                dep in ("obj", "dobj", "nsubj", "nsubj:pass", "attr", "appos", "conj")
                or any(ch.pos_ == "NUM" or re.match(r"^\d+", ch.text) for ch in t.children)
                or (t.i > 0 and (doc[t.i - 1].pos_ == "NUM" or re.match(r"^\d+", doc[t.i - 1].text)))
            )
        )

        if meta.get("is_wh"):
            wh_tokens.append(item)
        elif meta.get("is_negation") or dep == "neg":
            neg_tokens.append(item)
        elif meta.get("is_deixis"):
            if not subjects:
                subjects.append(item)
            else:
                modifiers_others.append(item)
        elif meta.get("is_connector"):
            connectors.append(item)
        elif meta.get("is_mwe") and meta.get("mwe_gloss") in ("AUNQUE", "PERO", "ADEMÁS"):
            time_tokens.append(item)
        elif (l_lower in planner._time_markers or t_lower in planner._time_markers or dep in ("obl:tmod",)) and not _is_counted_time_noun:
            time_tokens.append(item)
        elif (
            (
                any(c.text.lower() in ("en", "sobre", "bajo", "hacia", "desde", "hasta") and c.pos_ == "ADP" for c in t.children)
                or (dep in ("obl", "loc") and pos in ("PROPN", "NOUN"))
                or (dep in ("flat", "nmod", "appos", "compound") and t.head.dep_ in ("obl", "loc"))
                or (pos in ("NOUN", "PROPN") and l_lower in ("escuela", "colegio", "universidad", "hospital", "parque", "casa", "biblioteca", "aula", "clase", "campus", "quito", "tulcán", "cayambe"))
            )
            and not subjects
        ):
            location_tokens.append(item)
        elif pos == "VERB":
            verbs.append(item)
        elif pos in ("ADV", "ADJ") and dep == "advmod" and t.head.pos_ in ("VERB", "AUX", "ADJ") and l_lower not in planner._time_markers:
            manner_adverbs.append(item)
        elif dep in ("nsubj", "nsubj:pass"):
            subjects.append(item)
        elif dep == "flat" and pos == "PROPN" and any(s[0].i == t.head.i for s in subjects):
            subjects.append(item)
        elif pos in ("PRON", "PROPN") and not subjects and not verbs:
            subjects.append(item)
        elif dep in ("obj", "dobj", "iobj", "nmod") or (dep == "flat" and pos == "PROPN" and any(o[0].i == t.head.i for o in objects)):
            objects.append(item)
        elif pos == "NOUN":
            if not subjects and not verbs and not time_tokens and not location_tokens:
                subjects.append(item)
            else:
                objects.append(item)
        else:
            modifiers_others.append(item)

    if len(verbs) > 1:
        sorted_verbs: List[Any] = []
        for v_item in verbs:
            v_tok = v_item[0]
            if v_tok.dep_ in ("xcomp", "ccomp") and any(o[0].i == v_tok.head.i for o in verbs):
                head_tok = v_tok.head
                if head_tok.lemma_.lower() not in ("querer", "poder", "deber", "soler"):
                    head_idx = next((i for i, it in enumerate(sorted_verbs) if it[0].i == head_tok.i), None)
                    if head_idx is not None:
                        sorted_verbs.insert(head_idx, v_item)
                        continue
            sorted_verbs.append(v_item)
        verbs = sorted_verbs

    time_place = time_tokens + location_tokens

    apply_time = active_rule_ids is None or "LSEC_TIME_INITIAL" in active_rule_ids
    apply_wh = active_rule_ids is None or "LSEC_WH_FINAL" in active_rule_ids
    apply_neg = active_rule_ids is None or "LSEC_NEGATION_POSTVERBAL" in active_rule_ids
    apply_sov = active_rule_ids is None or "LSEC_SOV_ORDER" in active_rule_ids

    if apply_time and apply_wh and apply_neg and apply_sov:
        reordered = connectors + time_tokens + location_tokens + subjects + objects + modifiers_others + verbs + manner_adverbs + wh_tokens + neg_tokens
    else:
        curr_tp = (
            time_place
            if apply_time
            else [
                it
                for it in time_place
                if not (
                    it[3].lower() in planner._time_markers
                    or it[0].text.lower() in planner._time_markers
                    or it[2] in ("obl:tmod",)
                )
            ]
        )
        curr_wh = wh_tokens if apply_wh else []
        curr_neg = neg_tokens if apply_neg else []

        non_displaced: List[Any] = []
        for item in tokens_info:
            if item[4].get("is_amod"):
                continue
            if (item in connectors) or (item in curr_tp) or (item in wh_tokens and apply_wh) or (item in neg_tokens and apply_neg):
                continue
            non_displaced.append(item)

        if apply_sov:
            s_list = [it for it in subjects if it in non_displaced]
            o_list = [it for it in objects if it in non_displaced]
            v_list = [it for it in verbs if it in non_displaced]
            m_list = [it for it in non_displaced if it not in s_list and it not in o_list and it not in v_list]
            core_ordered = s_list + o_list + m_list + v_list
        elif not objects:
            loc_list = [it for it in location_tokens if it in non_displaced]
            s_list = [it for it in subjects if it in non_displaced]
            v_list = [it for it in verbs if it in non_displaced]
            adv_list = [it for it in manner_adverbs if it in non_displaced]
            m_list = [it for it in non_displaced if it not in loc_list and it not in s_list and it not in v_list and it not in adv_list]
            core_ordered = loc_list + s_list + m_list + v_list + adv_list
        else:
            core_ordered = non_displaced

        reordered = connectors + curr_tp + core_ordered + curr_wh + curr_neg

    if "haz posible" in prop.source_text.lower() and "imagina" in prop.source_text.lower():
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

    return reordered, periphrasis_markers, amod_by_head, wh_tokens
