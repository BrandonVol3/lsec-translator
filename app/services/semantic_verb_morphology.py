"""
Análisis morfológico determinista de verbos en español y detector de modalidad oracional (LSEC 2.1.1).

Extraído de `semantic_parser.py` para cumplir con el principio de Responsabilidad Única (SRP).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Set, Tuple

from app.services.discourse_segmenter import DiscourseUnit
from app.services.semantic_constants import (
    COPULA_FORMS as _COPULA_FORMS_CONST,
    IRREGULAR_ENCLITIC_MAP as _IRREGULAR_ENCLITIC_MAP_CONST,
    IRREGULAR_FUTURE_STEMS as _IRREGULAR_FUTURE_STEMS_CONST,
    KNOWN_VERB_FORMS as _KNOWN_VERB_FORMS_CONST,
    NOMINAL_HOMOGRAPHS as _NOMINAL_HOMOGRAPHS_CONST,
    NON_ENCLITIC_WORDS as _NON_ENCLITIC_WORDS_CONST,
    PERSON_1_FORMS,
    PERSON_1_PL_FORMS,
    PERSON_2_FORMS,
    PERSON_3_FORMS,
    PERSON_3_PL_FORMS,
    POS_GATED_LEMMAS as _POS_GATED_LEMMAS_CONST,
)
from app.services.text_normalizer import PunctuationAnalyzer


class SpanishVerbLexicon:
    """Inventario y análisis morfológico determinista de formas verbales en español."""

    KNOWN_VERB_FORMS: Dict[str, str] = _KNOWN_VERB_FORMS_CONST
    NOMINAL_HOMOGRAPHS: Set[str] = _NOMINAL_HOMOGRAPHS_CONST
    POS_GATED_LEMMAS: Set[str] = _POS_GATED_LEMMAS_CONST
    COPULA_FORMS: Set[str] = _COPULA_FORMS_CONST
    _NON_ENCLITIC_WORDS: Set[str] = _NON_ENCLITIC_WORDS_CONST
    _IRREGULAR_ENCLITIC_MAP: Dict[str, Tuple[str, str]] = _IRREGULAR_ENCLITIC_MAP_CONST
    _IRREGULAR_FUTURE_STEMS: Dict[str, str] = _IRREGULAR_FUTURE_STEMS_CONST

    @classmethod
    def get_lemma(cls, word: str, pos: Optional[str] = None) -> Optional[str]:
        """
        Devuelve el lema verbal de ``word``.

        El inventario contiene formas homógrafas con categorías no verbales
        (p. ej. ``como`` = preposición/conjunción vs. ``comer``; ``preguntas`` =
        sustantivo plural vs. ``preguntar``). Cuando se conoce la categoría
        gramatical (spaCy), se exige que sea verbal para no crear predicados
        falsos. Sin categoría se conserva el comportamiento histórico.
        """
        w_clean = PunctuationAnalyzer.strip_punctuation(word.lower())
        lemma = cls.KNOWN_VERB_FORMS.get(w_clean)
        if lemma is None:
            return None
        if pos is not None and w_clean in cls.POS_GATED_LEMMAS and pos not in ("VERB", "AUX"):
            return None
        return lemma

    @classmethod
    def _is_verified_infinitive(cls, candidate: str) -> bool:
        if candidate in cls.KNOWN_VERB_FORMS.values() or candidate in cls.KNOWN_VERB_FORMS:
            return True
        try:
            from app.services.dictionary_service import get_dictionary_service
            dict_svc = get_dictionary_service()
            if dict_svc and dict_svc.available:
                m = dict_svc.lookup(candidate)
                if m is not None and m.match_type in ("exact", "normalized"):
                    return True
        except Exception:
            pass
        return False

    @classmethod
    def contextual_verb_lemma(cls, token: Any) -> Optional[str]:
        """Resuelve homógrafos verbales que dependen del contexto sintáctico.

        ``ven`` es imperativo de *venir* y 3.ª persona plural de *ver*. Al
        inicio de oración o ante un destino/otro verbo predomina *venir*.
        """
        try:
            w = PunctuationAnalyzer.strip_punctuation(token.text.lower())
        except AttributeError:
            return None
        if w != "ven":
            return None
        doc = getattr(token, "doc", None)
        if doc is None:
            return None
        nxt = doc[token.i + 1] if token.i + 1 < len(doc) else None
        prev = doc[token.i - 1] if token.i > 0 else None
        at_start = (
            prev is None
            or prev.is_punct
            or prev.pos_ in ("CCONJ", "SCONJ")
        )
        destination = nxt is not None and nxt.text.lower() in (
            "a", "al", "hacia", "para", "aquí", "acá",
        )
        if at_start and (
            destination
            or nxt is None
            or nxt.is_punct
            or nxt.pos_ in ("VERB", "AUX")
        ):
            return "venir"
        return None

    @classmethod
    def split_enclitic(cls, word: str, pos: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Separa pronombres enclíticos (me, te, se, nos, lo, la, le, los, las, les)
        adheridos a infinitivos, gerundios o imperativos.
        Devuelve (infinitivo_base, clítico_principal).
        """
        w_clean = PunctuationAnalyzer.strip_punctuation(word.lower())
        if (
            not w_clean
            or pos in ("DET", "ADP", "CCONJ", "SCONJ", "NUM", "PUNCT")
            or w_clean in cls._NON_ENCLITIC_WORDS
            or w_clean in cls.NOMINAL_HOMOGRAPHS
        ):
            return w_clean, None

        if w_clean in cls._IRREGULAR_ENCLITIC_MAP:
            return cls._IRREGULAR_ENCLITIC_MAP[w_clean]

        # 1. Infinitivo + enclítico(s): ej. verlo, hacerlo, inscribirse, entregármelo
        m_inf = re.match(
            r"^([a-záéíóúñü]*?(?:ar|er|ir|ár|ér|ír))(?:(me|te|se|nos)(lo|la|le|los|las|les)|(me|te|se|nos|lo|la|le|los|las|les))$",
            w_clean,
        )
        if m_inf:
            base = m_inf.group(1).translate(str.maketrans("áéí", "aei"))
            clitic = m_inf.group(2) or m_inf.group(4)
            if base in ("ir", "ver", "dar", "ser", "oír", "reír") or (
                len(base) >= 4 and base not in cls.NOMINAL_HOMOGRAPHS
            ):
                return base, clitic

        # 2. Gerundio + enclítico(s): ej. mirándote, diciéndome
        m_ger = re.match(
            r"^([a-záéíóúñü]{2,}?)(ándo|iéndo|yendo|ando|iendo)(?:(me|te|se|nos)(lo|la|le|los|las|les)|(me|te|se|nos|lo|la|le|los|las|les))$",
            w_clean,
        )
        if m_ger:
            stem = m_ger.group(1).translate(str.maketrans("áéíóú", "aeiou"))
            ger_suf = m_ger.group(2)
            clitic = m_ger.group(3) or m_ger.group(5)
            if "a" in ger_suf or "á" in ger_suf:
                return stem + "ar", clitic
            for cand in (stem + "er", stem + "ir"):
                if cls._is_verified_infinitive(cand):
                    return cand, clitic
            return stem + "er", clitic

        # 3. Imperativo con tilde + enclítico(s): ej. avísame, ayúdame, entrégalo, comunícate, inscríbete
        if any(c in w_clean for c in "áéíóú"):
            m_imp = re.match(
                r"^([a-záéíóúñü]{3,}?)(?:(me|te|se|nos)(lo|la|le|los|las|les)|(me|te|se|nos|lo|la|le|los|las|les))$",
                w_clean,
            )
            if m_imp:
                raw_stem = m_imp.group(1)
                clitic = m_imp.group(2) or m_imp.group(4)
                stem_unacc = raw_stem.translate(str.maketrans("áéíóú", "aeiou"))
                known = cls.KNOWN_VERB_FORMS.get(stem_unacc)
                if known:
                    return known, clitic
                if stem_unacc.endswith("a") and len(stem_unacc) >= 3:
                    cand_ar = stem_unacc[:-1] + "ar"
                    if m_imp.group(2) is not None or cls._is_verified_infinitive(cand_ar):
                        return cand_ar, clitic
                if stem_unacc.endswith("e") and len(stem_unacc) >= 3:
                    root = stem_unacc[:-1]
                    if root.endswith("gu"):
                        cand_gar = root[:-2] + "gar"
                        if cls._is_verified_infinitive(cand_gar):
                            return cand_gar, clitic
                    if root.endswith("qu"):
                        cand_car = root[:-2] + "car"
                        if cls._is_verified_infinitive(cand_car):
                            return cand_car, clitic
                    for cand in (root + "ir", root + "er", root + "ar"):
                        if cls._is_verified_infinitive(cand):
                            return cand, clitic
                    if m_imp.group(2) is not None:
                        return root + "er", clitic

        return w_clean, None

    @classmethod
    def has_nominal_context(cls, token: Any) -> bool:
        """
        Determina si un token está en un contexto nominal inequívoco.

        spaCy etiqueta a veces formas verbales como sustantivos/adjetivos y
        viceversa. La presencia de determinante, adjetivo o numeral modificando
        al token es evidencia suficiente de uso nominal; en ese caso no debe
        convertirse en predicado ni en verbo conjugado.
        """
        try:
            pos = token.pos_
            dep = token.dep_
            if pos in ("NOUN", "PROPN"):
                if any(
                    c.dep_ == "det" and "Int" not in c.morph.get("PronType", [])
                    for c in token.children
                ):
                    return True
                if any(
                    c.dep_ == "nummod" and c.pos_ in ("NUM", "DET", "ADJ")
                    for c in token.children
                ):
                    return True
                if any(c.dep_ == "compound" for c in token.children):
                    return True
                if token.i > 0:
                    prev = token.doc[token.i - 1]
                    if prev.pos_ in ("DET", "ADJ") and not (
                        prev.pos_ == "DET" and "Int" in prev.morph.get("PronType", [])
                    ):
                        return True
                if dep != "ROOT" and any(c.dep_ == "amod" for c in token.children):
                    return True
            elif pos == "ADJ":
                if dep == "amod":
                    return False
                if dep in ("nsubj", "nsubj:pass", "obj", "ROOT") and (
                    any(c.dep_ in ("det", "amod", "nummod") for c in token.children)
                    or (token.i > 0 and token.doc[token.i - 1].pos_ in ("DET", "ADJ"))
                ):
                    return True
        except Exception:
            return False
        return False

    @classmethod
    def _derive_verified_infinitive(cls, word: str) -> Optional[str]:
        """
        Deriva un infinitivo verificado a partir de una forma conjugada.
        """
        w_clean = PunctuationAnalyzer.strip_punctuation(word.lower())
        if not w_clean or len(w_clean) < 4:
            return None

        suffix_map: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
            ("ábamos", ("ar",)),
            ("asteis", ("ar",)),
            ("ieron", ("er", "ir")),
            ("ieron", ("er", "ir")),
            ("aste", ("ar",)),
            ("iste", ("er", "ir")),
            ("aban", ("ar",)),
            ("abas", ("ar",)),
            ("ando", ("ar",)),
            ("iendo", ("er", "ir")),
            ("amos", ("ar", "er", "ir")),
            ("imos", ("ar", "er", "ir")),
            ("emos", ("ar", "er", "ir")),
            ("ado", ("ar",)),
            ("ido", ("er", "ir")),
            ("aba", ("ar",)),
            ("en", ("ar", "er", "ir")),
            ("es", ("ar", "er", "ir")),
            ("an", ("ar", "er", "ir")),
            ("as", ("ar", "er", "ir")),
            ("ó", ("ar", "er", "ir")),
            ("é", ("ar", "er", "ir")),
            ("í", ("er", "ir")),
            ("o", ("ar", "er", "ir")),
            ("a", ("ar", "er", "ir")),
            ("e", ("ar", "er", "ir")),
        )
        for suffix, endings in suffix_map:
            if not w_clean.endswith(suffix) or len(w_clean) <= len(suffix) + 1:
                continue
            stem = w_clean[: -len(suffix)].translate(str.maketrans("áéíóú", "aeiou"))
            candidates = [stem + ending for ending in endings]
            verified = [c for c in candidates if cls._is_verified_infinitive(c)]
            if verified:
                return verified[0]
        return None

    @classmethod
    def derive_ar_infinitive(cls, word: str) -> Optional[str]:
        """Deriva el infinitivo en -ar directamente desde la palabra flexionada."""
        w_clean = PunctuationAnalyzer.strip_punctuation(word.lower())
        if w_clean in ("cuando", "cuándo", "bando", "mando", "blando") or w_clean in cls.NOMINAL_HOMOGRAPHS:
            return None
        if w_clean == "vamos":
            return "ir"
        for suf in ("ábamos", "asteis", "aste", "aron", "amos", "aban", "abas", "aba", "ando", "ado"):
            if w_clean.endswith(suf) and len(w_clean) > len(suf) + 1:
                stem = w_clean[: -len(suf)].translate(str.maketrans("áéíóú", "aeiou"))
                cand = stem + "ar"
                if suf in ("ábamos", "asteis", "aste", "aron") or cls._is_verified_infinitive(cand):
                    return cand
        return None

    @classmethod
    def normalize_verb_lemma(cls, word: str, raw_lemma: str, pos: Optional[str] = None) -> str:
        """
        Corrige errores de lematización estadística de spaCy usando desinencias morfológicas
        y validación con el Diccionario Oficial LSEC.
        """
        w_clean = PunctuationAnalyzer.strip_punctuation(word.lower())
        known = cls.KNOWN_VERB_FORMS.get(w_clean)
        if known and w_clean not in cls.NOMINAL_HOMOGRAPHS:
            if pos is not None and w_clean in cls.POS_GATED_LEMMAS and pos not in ("VERB", "AUX"):
                return PunctuationAnalyzer.strip_punctuation((raw_lemma or w_clean).lower())
            return known
        lemma_clean = PunctuationAnalyzer.strip_punctuation((raw_lemma or "").lower())
        if w_clean in cls.NOMINAL_HOMOGRAPHS or lemma_clean in cls.NOMINAL_HOMOGRAPHS:
            if pos in ("VERB", "AUX") and known:
                return known
            return lemma_clean or w_clean

        # 0. Separación de enclíticos antes de validar el lema crudo
        base_inf, clitic = cls.split_enclitic(w_clean)
        if clitic is not None:
            return base_inf

        # 0b. Lema crudo con forma de infinitivo pero no verificado
        if lemma_clean.endswith(("ar", "er", "ir")):
            if not cls._is_verified_infinitive(lemma_clean):
                derived = cls._derive_verified_infinitive(w_clean)
                if derived:
                    return derived
                stem = lemma_clean[:-2]
                if len(stem) >= 3 and w_clean.startswith(stem):
                    return lemma_clean
        else:
            derived = cls._derive_verified_infinitive(w_clean)
            if derived:
                return derived

        # 1. Separación de enclíticos (infinitivos, gerundios, imperativos)
        base_inf, clitic = cls.split_enclitic(w_clean)
        if clitic is not None:
            return base_inf

        # 2. Futuro sintético y condicional
        if pos in (None, "VERB", "AUX"):
            m_fut = re.match(
                r"^([a-záéíóúñü]{2,})(?:é|ás|á|emos|éis|án|ía|ías|íamos|íais|ían)$",
                w_clean,
            )
            if m_fut:
                f_stem = m_fut.group(1)
                if f_stem in cls._IRREGULAR_FUTURE_STEMS:
                    return cls._IRREGULAR_FUTURE_STEMS[f_stem]
                if f_stem.endswith(("ar", "er", "ir")) and len(f_stem) >= 4:
                    return f_stem

        # 3. Imperativos sin tilde con enclítico -te
        if w_clean.endswith("ate") and lemma_clean.endswith(("atir", "ater", "ate")) and len(lemma_clean) > 5:
            stem = w_clean[:-3].translate(str.maketrans("áéíóú", "aeiou"))
            return stem + "ar"

        # 4. Sufijos inequívocos de 1ª conjugación (-ar)
        ar_inf = cls.derive_ar_infinitive(w_clean)
        if ar_inf and (
            not lemma_clean.endswith("ar")
            or lemma_clean.endswith(("astar", "arer", "arar"))
            or lemma_clean == w_clean
        ):
            return ar_inf

        # 5. Alternancias ortográficas de subjuntivo/imperativo
        if pos in (None, "VERB", "AUX") and w_clean not in ("que", "qué", "porque", "aunque"):
            if w_clean.endswith(("gues", "guen")) and len(w_clean) > 5:
                return w_clean[:-4] + "gar"
            if w_clean.endswith("gue") and len(w_clean) > 4:
                return w_clean[:-3] + "gar"
            if w_clean.endswith(("ques", "quen")) and len(w_clean) > 5:
                return w_clean[:-4] + "car"
            if w_clean.endswith("que") and len(w_clean) > 4:
                return w_clean[:-3] + "car"

        # 6. Si spaCy dejó la forma flexionada intacta como lema en un VERB/AUX
        if pos in ("VERB", "AUX") and (lemma_clean == w_clean or not lemma_clean.endswith(("ar", "er", "ir"))) and not w_clean.endswith(("ar", "er", "ir")):
            derived = cls._derive_verified_infinitive(w_clean)
            if derived:
                return derived
            for suf in ("ieron", "iste", "imos", "iendo", "ido", "emos", "en", "es", "an", "as", "ó", "é", "í", "o", "a", "e"):
                if w_clean.endswith(suf) and len(w_clean) > len(suf) + 1:
                    stem = w_clean[: -len(suf)].translate(str.maketrans("áéíóú", "aeiou"))
                    cands = [stem + "ar", stem + "er", stem + "ir"] if suf in ("o", "e", "en", "es", "é") else (
                        [stem + "ar"] if suf in ("as", "an", "a", "ó") else [stem + "er", stem + "ir", stem + "ar"]
                    )
                    for cand in cands:
                        if cls._is_verified_infinitive(cand):
                            return cand
                    return cands[0]

        return lemma_clean or w_clean

    @classmethod
    def get_person(cls, word: str) -> Optional[str]:
        w = PunctuationAnalyzer.strip_punctuation(word.lower())
        if w in cls.NOMINAL_HOMOGRAPHS:
            return None
        _, clitic = cls.split_enclitic(w)
        if clitic is not None and not w[: -len(clitic)].translate(str.maketrans("áéí", "aei")).endswith(("ar", "er", "ir", "ando", "iendo")):
            return "2"
        if w in PERSON_1_FORMS:
            return "1"
        if w in PERSON_2_FORMS or (w.endswith(("aste", "iste", "arás", "erás", "irás")) and len(w) > 4):
            return "2"
        if w in PERSON_3_FORMS:
            return "3"
        if w in PERSON_1_PL_FORMS or (w.endswith(("amos", "emos", "imos")) and len(w) > 4):
            return "1-PL"
        if w in PERSON_3_PL_FORMS or (w.endswith(("aron", "ieron")) and len(w) > 5):
            return "3-PL"
        return None

    @classmethod
    def is_verb(cls, word: str) -> bool:
        w_clean = PunctuationAnalyzer.strip_punctuation(word.lower())
        if w_clean in cls.NOMINAL_HOMOGRAPHS:
            return False
        _, clitic = cls.split_enclitic(w_clean)
        if clitic is not None:
            return True
        return (
            w_clean in cls.KNOWN_VERB_FORMS
            or w_clean.endswith(("ar", "er", "ir", "ando", "iendo", "ado", "ido", "aron", "ieron", "amos", "emos", "imos", "aste", "iste"))
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
        for tok in text.split():
            w_c = PunctuationAnalyzer.strip_punctuation(tok.lower())
            if not w_c or w_c in ("por", "favor", "primero", "después", "luego", "entonces", "además"):
                continue
            _, clitic = SpanishVerbLexicon.split_enclitic(w_c)
            if clitic and not w_c[: -len(clitic)].translate(str.maketrans("áéíóú", "aeiou")).endswith(
                ("ar", "er", "ir", "ando", "iendo", "yendo")
            ):
                return "imperative"
            break
        return "declarative"
