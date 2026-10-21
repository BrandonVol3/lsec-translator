"""Reglas FENASEC/CONADIS deterministas aplicadas sobre las glosas planificadas.

Reglas cubiertas (100% lingüísticas, sin LLM):
  2b. Negación léxica incorporada: ``NO-SABER``, ``NO-QUERER``, ``NO-PODER``,
      ``NO-GUSTAR``, ``NO-HABER`` (se elimina el ``NO`` final).
  4.  Clases verbales (datos en lexicon_lsec.json):
      - direccionales: ``AVISAR[1->2]``, ``EXPLICAR[1->2]``, ``AYUDAR[2->1]``,
        ``PRESTAR-ATENCIÓN[2->1]`` (suprimen pronombres absorbidos).
      - inversos: ``ROBAR[2->1]`` (trayectoria invertida).
      - anclados al cuerpo (body_anchored): ``ABRAZAR``, ``ACEPTAR`` (sin vector,
        conservan pronombres explícitos).
      - argumento único (single_arg_locus): ``MORIR``, ``CRECER`` (concordancia
        en locus del sujeto).
  5.  Duplicación segmental de intensidad generalizada:
      - Adverbios de grado sobre adjetivo/adverbio/verbo: ``LENTO++``, ``RÁPIDO++``.
      - Superlativos en -ísimo: ``LENTO++``.
      - Sintagma preposicional de grado (con mucha intensidad): ``LLOVER++``.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Set

from app.core.schemas import FacialExpression, GlossItem, NonManualMarker, SpatialLocation

INCORPORATED_NEGATION_VERBS = {"SABER", "QUERER", "PODER", "GUSTAR", "HABER"}

_LEXICON_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "lexicon_lsec.json")


def _load_lexicon_data() -> dict:
    if os.path.exists(_LEXICON_PATH):
        try:
            with open(_LEXICON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


_LEXICON_CACHE = _load_lexicon_data()
_VERB_CLASSES: Dict[str, List[str]] = _LEXICON_CACHE.get("verb_classes", {})
_DEGREE_NOUNS: Set[str] = set(
    _LEXICON_CACHE.get(
        "degree_nouns",
        [
            "intensidad",
            "fuerza",
            "ganas",
            "énfasis",
            "empeño",
            "velocidad",
            "rapidez",
            "energía",
            "pasión",
        ],
    )
)

_DIRECTIONAL_VERBS_DEFAULT: Set[str] = {
    "AYUDAR", "ACONSEJAR", "ANIMAR", "PRESTAR-ATENCIÓN", "COPIAR", "ENSEÑAR",
    "EXPLICAR", "ENVIAR", "ENGAÑAR", "INVITAR", "JUZGAR", "FASTIDIAR",
    "OBLIGAR", "OBEDECER", "ODIAR", "RECHAZAR", "TRAICIONAR", "RESPETAR",
    "VISITAR", "VENCER", "DECIR", "MIRAR", "APOYAR", "LLAMAR-CON-LA-MANO",
    "REVISAR", "AVISAR", "DAR", "PREGUNTAR", "INFORMAR", "MOSTRAR", "ENTREGAR",
}
_INVERSE_VERBS_DEFAULT: Set[str] = {"ROBAR"}
_BODY_ANCHORED_VERBS_DEFAULT: Set[str] = {"ABRAZAR", "ACEPTAR", "BUSCAR"}
_SINGLE_ARG_LOCUS_VERBS_DEFAULT: Set[str] = {"MORIR", "CRECER"}

DIRECTIONAL_VERBS = set(_VERB_CLASSES.get("directional", list(_DIRECTIONAL_VERBS_DEFAULT)))

_RECIPIENT_CLITICS = {"me", "te", "nos", "le", "les", "se", "os"}
_CLITICS_AFTER_NO = {"me", "te", "se", "le", "lo", "la", "nos", "os", "les", "los", "las"}
_PRETERITE_1SG = {"di", "vi", "fui", "hice", "dije", "puse", "supe", "quise", "pude", "tuve"}
_DEGREE_ADVERBS = {"muy", "mucho", "bastante", "demasiado", "tan", "sumamente"}
_PLAIN_INTENSIFIERS = {"mucho", "bastante", "demasiado", "muy", "tan", "sumamente"}
_INTENSIFIER_RE = re.compile(
    r"^(muchísim[oa]s?|\w{3,}ísim[oa]s?|mucho|mucha|bastante|demasiado|muy|tan|sumamente)$",
    re.IGNORECASE,
)
_PRO_RE = re.compile(r"^PRO([123])(-PL)?$")
_COMMUNICATION_TRANSFER_LEMMAS = {
    "comunicar", "transferir", "transmitir", "mandar", "donar", "ceder", "regalar", "prestar"
}


def get_verb_class(gloss: str) -> str:
    """Retorna la clase verbal ('directional', 'inverse', 'body_anchored', 'single_arg_locus')."""
    clean = re.sub(r"\[.*?\]|\+\+", "", gloss).upper().strip()
    for cls_name, vlist in _VERB_CLASSES.items():
        if clean in vlist:
            return cls_name
    if clean in _DIRECTIONAL_VERBS_DEFAULT:
        return "directional"
    if clean in _INVERSE_VERBS_DEFAULT:
        return "inverse"
    if clean in _BODY_ANCHORED_VERBS_DEFAULT:
        return "body_anchored"
    if clean in _SINGLE_ARG_LOCUS_VERBS_DEFAULT:
        return "single_arg_locus"
    return "body_anchored"


def _norm(src: Optional[str]) -> str:
    return re.sub(r"[^\wáéíóúñü]", "", (src or "").lower())


def _find_token(doc: Any, word: Optional[str]):
    if not word or doc is None:
        return None
    words = [_norm(p) for p in word.split() if _norm(p)]
    if not words:
        return None
    # 1. Búsqueda exacta de palabra o lema
    for t in doc:
        t_norm = _norm(t.text)
        t_lem = _norm(getattr(t, "lemma_", ""))
        for w in words:
            if t_norm == w or t_lem == w:
                return t
    return None


def _renumber(items: List[GlossItem], start_order: int) -> None:
    for i, it in enumerate(items):
        it.order = start_order + i


_CLITIC_PERSON_LEMMAS: Dict[str, Set[str]] = {
    "me": {"yo", "mí"},
    "te": {"tú", "usted", "vos", "ti"},
    "nos": {"nosotros", "nosotras"},
    "le": {"él", "ella", "usted"},
    "les": {"ellos", "ellas", "ustedes"},
}

# Verbos que rigen un destinatario dativo: el clítico se absorbe en el vector
# direccional ("te di las llaves" -> DAR[1->2]), a diferencia de los verbos
# transitivos que conservan el objeto directo ("te invitamos al evento").
_DATIVE_RECIPIENT_VERBS: Set[str] = {
    "dar", "entregar", "enviar", "mandar", "regalar", "prestar", "comprar",
    "traer", "llevar", "dedicar", "conceder", "otorgar", "pagar", "deber",
    "escribir", "decir", "contar", "explicar", "mostrar", "comunicar",
    "transferir", "transmitir", "donar", "ceder", "ofrecer", "presentar",
}


def _verb_lemma_from_gloss(gloss: str) -> str:
    return re.sub(r"\[.*?\]|\+\+", "", gloss or "").lower().strip()


def _beneficiary_lemmas(proposition: Any) -> Set[str]:
    """Lemas de participantes con rol BENEFICIARY de la proposición."""
    lemmas: Set[str] = set()
    for p in getattr(proposition, "participants", None) or []:
        role = getattr(p, "semantic_role", None)
        role_val = getattr(role, "value", str(role))
        if role_val == "BENEFICIARY":
            lemma = getattr(p, "lemma", None)
            if lemma:
                lemmas.add(_norm(lemma))
    return lemmas


def _keep_accusative_beneficiary(
    gloss_item: GlossItem,
    doc: Any,
    beneficiary_lemmas: Set[str],
    verb_lemma: str = "",
) -> bool:
    """
    Distingue el objeto directo benefactivo explícito ("te invitamos al evento")
    del dativo de destinatario que absorbe el verbo direccional ("te di", "me ayudas").
    Solo se conserva el PRO cuando el clítico es acusativo (dep ``obj``), su
    participante tiene rol BENEFICIARY y el verbo no rige dativo.
    """
    if verb_lemma in _DATIVE_RECIPIENT_VERBS:
        return False
    if not beneficiary_lemmas:
        return False
    src = _norm(gloss_item.source_word)
    if src not in _CLITIC_PERSON_LEMMAS:
        return False
    if not (_CLITIC_PERSON_LEMMAS[src] & beneficiary_lemmas):
        return False
    tok = _find_token(doc, gloss_item.source_word)
    return tok is not None and getattr(tok, "dep_", "") == "obj"


def _agent_label_from_proposition(
    proposition: Any, verb_gloss: Optional[str] = None
) -> Optional[str]:
    """Etiqueta de persona del agente a partir de los participantes.

    Solo se usa cuando el verbo analizado es el predicado principal de la
    proposición; en cláusulas con varios verbos el agente compartido puede
    corresponder a otro verbo (p. ej. "dejaste ... que te di").
    """
    if verb_gloss and proposition is not None:
        pred = getattr(getattr(proposition, "predicate", None), "lemma", None)
        if pred and _norm(pred) != _verb_lemma_from_gloss(verb_gloss):
            return None
    for p in getattr(proposition, "participants", None) or []:
        role = getattr(p, "semantic_role", None)
        role_val = getattr(role, "value", str(role))
        if role_val != "AGENT":
            continue
        lemma = _norm(getattr(p, "lemma", "") or "")
        if lemma in ("yo", "mi", "me"):
            return "1"
        if lemma in ("nosotros", "nosotras", "nos"):
            return "1-PL"
        if lemma in ("tu", "tú", "usted", "vos", "ti", "te"):
            return "2"
        if lemma in ("ustedes", "vosotros", "vosotras"):
            return "2-PL"
    return None


def _verb_person_label(doc: Any, verb_item: GlossItem) -> str:
    tok = _find_token(doc, verb_item.source_word)
    if tok is None:
        return "3"
    txt = _norm(tok.text)
    if txt in _PRETERITE_1SG or txt.endswith(("é", "í")):
        return "1"
    person = tok.morph.get("Person", []) if hasattr(tok, "morph") else []
    number = tok.morph.get("Number", []) if hasattr(tok, "morph") else []
    if not person:
        if txt.endswith(("amos", "emos", "imos")):
            person, number = ["1"], ["Plur"]
        elif txt.endswith(("as", "es", "ás", "és")):
            person = ["2"]
        elif txt in _PRETERITE_1SG or txt.endswith(("o", "é", "í")):
            person = ["1"]
        else:
            person = ["3"]
    label = person[0]
    if "Plur" in number:
        label += "-PL"
    return label


def apply_incorporated_negation(items: List[GlossItem], doc: Any) -> None:
    neg_items = [it for it in items if it.gloss == "NO"]
    doc_list = list(doc) if doc is not None else []
    no_positions = [k for k, t in enumerate(doc_list) if _norm(t.text) == "no"]
    if not neg_items or not no_positions:
        return
    paired = len(no_positions) == len(neg_items)
    unincorporated_count = 0
    for idx, pos in enumerate(no_positions):
        j = pos + 1
        while j < len(doc_list) and _norm(doc_list[j].text) in _CLITICS_AFTER_NO:
            j += 1
        verb_item = None
        if j < len(doc_list):
            target_word = _norm(doc_list[j].text)
            verb_item = next(
                (
                    it for it in items
                    if it.gloss in INCORPORATED_NEGATION_VERBS
                    and _norm(it.source_word) == target_word
                ),
                None,
            )
        if verb_item is None:
            unincorporated_count += 1
            continue
        verb_item.gloss = f"NO-{verb_item.gloss}"
        verb_item.notes = "Negación léxica incorporada (FENASEC)"
        verb_item.non_manual = NonManualMarker(
            expression=FacialExpression.NEGATION, head_movement="negar"
        )
        if paired:
            neg_item = neg_items[idx]
            if neg_item in items:
                items.remove(neg_item)
    if not paired and unincorporated_count == 0:
        for neg_item in neg_items:
            if neg_item in items:
                items.remove(neg_item)


def _belongs_to_verb(tok: Any, verb_tok: Any) -> bool:
    if tok is None or verb_tok is None:
        return True
    head = getattr(tok, "head", None)
    if head is None:
        return True
    if getattr(head, "i", None) == getattr(verb_tok, "i", None):
        return True
    return False


def apply_directional_verbs(items: List[GlossItem], doc: Any, proposition: Any = None) -> None:
    """Aplica comportamiento por clase verbal según D3 (Fase 2)."""
    beneficiary_lemmas = _beneficiary_lemmas(proposition)
    for verb in list(items):
        clean_gloss = re.sub(r"\[.*?\]|\+\+", "", verb.gloss).strip()
        verb_lemma = clean_gloss.lower()
        v_class = get_verb_class(clean_gloss)

        if v_class not in ("directional", "inverse", "single_arg_locus", "body_anchored"):
            v_class = "body_anchored"

        if verb not in items:
            continue

        idx = items.index(verb)
        verb_tok = _find_token(doc, verb.source_word)
        if verb_tok is None and doc is not None:
            clean_lower = clean_gloss.lower()
            for t in doc:
                if t.pos_ in ("VERB", "AUX") or _norm(t.lemma_) in clean_lower:
                    verb_tok = t
                    break

        if v_class == "single_arg_locus":
            # Concordancia de argumento único con el locus del sujeto
            subject_item = None
            for it in reversed(items[:idx]):
                if it.spatial_location or it.spatial_ref or it.target_spatial_location:
                    subject_item = it
                    break
            if subject_item is not None:
                loc_val = subject_item.spatial_location or subject_item.target_spatial_location
                verb.spatial_ref = subject_item.spatial_ref
                verb.spatial_location = loc_val
                verb.target_spatial_location = loc_val
            continue

        if v_class == "body_anchored":
            # Verbo anclado al cuerpo: NO añade vector y conserva pronombres explícitos
            clean_norm = (verb.normalized_word or clean_gloss).lower()
            if clean_norm in _COMMUNICATION_TRANSFER_LEMMAS:
                verb.notes = "DIRECTIONAL_CANDIDATE (Revisión requerida)"
                verb.requires_review = True
            continue

        # Proceso para 'directional' e 'inverse'
        pros = [
            (i, it)
            for i, it in enumerate(items[:idx])
            if _PRO_RE.match(it.gloss)
            and (verb_tok is None or _belongs_to_verb(_find_token(doc, it.source_word), verb_tok))
        ]
        clitic_pros = [(i, it) for i, it in pros if _norm(it.source_word) in _RECIPIENT_CLITICS]

        if len(pros) >= 2:
            agent_i, agent = pros[0]
            rec_i, rec = pros[-1]
            agent_label = agent.gloss[3:]
            rec_label = rec.gloss[3:]
            drop = [agent]
            if not _keep_accusative_beneficiary(rec, doc, beneficiary_lemmas, verb_lemma):
                drop.append(rec)
        elif clitic_pros:
            rec_i, rec = clitic_pros[0]
            rec_label = rec.gloss[3:]
            has_noun_subject = False
            for it in items[:idx]:
                if _PRO_RE.match(it.gloss) or it.gloss in ("NO", "/"):
                    continue
                t_cand = _find_token(doc, it.source_word)
                if (
                    t_cand is not None
                    and getattr(t_cand, "dep_", "") in ("nsubj", "nsubj:pass")
                    and (verb_tok is None or _belongs_to_verb(t_cand, verb_tok))
                ):
                    has_noun_subject = True
                    break
            agent_label = _agent_label_from_proposition(proposition, verb.gloss) or (
                "3" if has_noun_subject else _verb_person_label(doc, verb)
            )
            drop = [] if _keep_accusative_beneficiary(rec, doc, beneficiary_lemmas, verb_lemma) else [rec]
        else:
            from app.services.semantic_parser import SpanishVerbLexicon
            raw_src = _norm(verb.source_word)
            _, enclitic = SpanishVerbLexicon.split_enclitic(raw_src)
            enclitic_map = {"me": "1", "te": "2", "nos": "1-PL", "le": "3", "les": "3-PL", "se": "3"}
            if enclitic in enclitic_map and (enclitic != "se" or raw_src.endswith(("selo", "sela", "selos", "selas"))):
                rec_label = enclitic_map[enclitic]
                raw_stem = re.sub(
                    r"(?:(?:me|te|se|nos)(?:lo|la|le|los|las|les)|(?:me|te|se|nos|lo|la|le|los|las|les))$",
                    "",
                    raw_src,
                )
                raw_stem_unacc = raw_stem.translate(str.maketrans("áéíóú", "aeiou"))
                if pros:
                    agent_label = pros[0][1].gloss[3:]
                    drop = [pros[0][1]]
                elif raw_stem_unacc and not raw_stem_unacc.endswith(("ar", "er", "ir", "ando", "iendo", "yendo")):
                    agent_label = "2"
                    drop = []
                else:
                    agent_label = _verb_person_label(doc, verb)
                    drop = []
            else:
                continue

        if agent_label == rec_label:
            continue

        if v_class == "inverse":
            verb.gloss = f"{clean_gloss}[{rec_label}->{agent_label}]"
            verb.notes = "Verbo de concordancia inversa (FENASEC)"
        else:
            verb.gloss = f"{clean_gloss}[{agent_label}->{rec_label}]"
            verb.notes = "Verbo direccional (FENASEC)"

        for d in drop:
            if d in items:
                items.remove(d)


def apply_intensity_duplication(items: List[GlossItem], doc: Any) -> None:
    """Duplicación segmental de intensidad generalizada (Fase 5, D6c)."""
    duplicated_any = False

    # 1. Detección de sintagmas preposicionales de grado: con + mucha/mucho + sustantivo_de_grado
    if doc is not None:
        pp_degree_nouns = []
        for t in doc:
            t_norm = _norm(t.text)
            t_lemma = _norm(t.lemma_)
            if t_norm in _DEGREE_NOUNS or t_lemma in _DEGREE_NOUNS:
                has_con = any(_norm(c.text) == "con" for c in t.children) or (
                    t.i >= 2 and _norm(doc[t.i - 2].text) == "con"
                ) or (t.i >= 1 and _norm(doc[t.i - 1].text) == "con")
                has_mucha = any(
                    _norm(c.text) in ("mucho", "mucha", "gran", "bastante", "alto", "alta")
                    for c in t.children
                ) or (
                    t.i >= 1 and _norm(doc[t.i - 1].text) in ("mucho", "mucha", "gran", "bastante", "alta", "alto")
                )
                if has_con and has_mucha:
                    pp_degree_nouns.append(t)

        for t_deg in pp_degree_nouns:
            head_tok = t_deg.head
            verb_item = None
            if head_tok is not None:
                verb_item = next(
                    (
                        v for v in items
                        if _find_token(doc, v.source_word) is not None
                        and getattr(_find_token(doc, v.source_word), "i", -1) == head_tok.i
                    ),
                    None,
                )
            if verb_item is None:
                for v in items:
                    v_tok = _find_token(doc, v.source_word)
                    if v_tok is not None and getattr(v_tok, "pos_", "") in ("VERB", "AUX"):
                        verb_item = v
                        break
            if verb_item is not None:
                if not verb_item.gloss.endswith("++"):
                    verb_item.gloss = f"{verb_item.gloss}++"
                verb_item.facial_expression = FacialExpression.SUPERLATIVE
                verb_item.non_manual = NonManualMarker(
                    expression=FacialExpression.SUPERLATIVE, head_movement=None
                )
                verb_item.notes = "Duplicación segmental de intensidad por sintagma de grado (FENASEC)"
                duplicated_any = True

                # Suprimir componentes del sintagma preposicional de grado
                to_remove = [
                    it for it in items
                    if _norm(it.source_word) in ("con", "mucha", "mucho", "intensidad")
                    or it.gloss in ("CON", "MUCHO", "MUCHA", "INTENSIDAD")
                    or _norm(it.source_word) in _DEGREE_NOUNS
                    or it.gloss.lower() in _DEGREE_NOUNS
                ]
                for r in to_remove:
                    if r in items:
                        items.remove(r)

    # 2. Adverbios de grado y superlativos léxicos
    for it in list(items):
        w = _norm(it.source_word)
        if not w:
            continue

        tok = _find_token(doc, it.source_word)

        # Guarda 1: mucho/a(s) como determinante de sustantivo (cuantificador nominal -> VARIOS, no ++)
        if tok is not None and (
            getattr(tok, "pos_", "") == "DET"
            or (tok.head is not None and getattr(tok.head, "pos_", "") in ("NOUN", "PROPN"))
        ):
            continue

        # Guarda 2: adverbio bajo negación clausal directa (ej. 'no muy bueno' -> revisión)
        if tok is not None:
            has_neg = any(getattr(c, "dep_", "") == "neg" for c in tok.children) or (
                tok.head is not None and any(getattr(c, "dep_", "") == "neg" for c in tok.head.children)
            )
            if has_neg:
                it.requires_review = True
                it.notes = "Intensidad bajo negación - revisión requerida"
                continue

        is_degree_adv = w in _DEGREE_ADVERBS or _INTENSIFIER_RE.match(w)
        if not is_degree_adv:
            continue

        target_item = None
        if tok is not None and tok.head is not None:
            head_tok = tok.head
            if getattr(head_tok, "pos_", "") in ("ADJ", "ADV", "VERB", "AUX"):
                target_item = next(
                    (
                        v for v in items
                        if _find_token(doc, v.source_word) is not None
                        and getattr(_find_token(doc, v.source_word), "i", -1) == head_tok.i
                    ),
                    None,
                )

        if target_item is None:
            for v in items:
                if v == it:
                    continue
                v_tok = _find_token(doc, v.source_word)
                if (
                    v_tok is not None
                    and getattr(v_tok, "pos_", "") in ("ADJ", "ADV", "VERB", "AUX")
                    and getattr(v_tok, "lemma_", "").lower() not in ("estar", "ser", "haber")
                ):
                    target_item = v
                    break

        if target_item is not None:
            if not target_item.gloss.endswith("++"):
                target_item.gloss = f"{target_item.gloss}++"
            target_item.facial_expression = FacialExpression.SUPERLATIVE
            target_item.non_manual = NonManualMarker(
                expression=FacialExpression.SUPERLATIVE, head_movement=None
            )
            target_item.notes = "Duplicación segmental de intensidad (FENASEC)"
            if it in items:
                items.remove(it)
            duplicated_any = True

    # 3. Superlativos directos en -ísimo adheridos al adjetivo
    for it in list(items):
        w = _norm(it.source_word)
        if w.endswith(("ísimo", "ísima", "ísimos", "ísimas")):
            if not it.gloss.endswith("++"):
                it.gloss = f"{it.gloss}++"
            it.facial_expression = FacialExpression.SUPERLATIVE
            it.non_manual = NonManualMarker(
                expression=FacialExpression.SUPERLATIVE, head_movement=None
            )
            duplicated_any = True

    # 4. Subsunción de AHORA aspectual
    if duplicated_any:
        for it in list(items):
            if it.gloss == "AHORA" and (it.notes or "").startswith("Marcador aspectual"):
                items.remove(it)


def apply_por_favor(items: List[GlossItem], doc: Any) -> None:
    """Cortesía: 'por favor' se glosa POR-FAVOR y se antepone (marcador de apertura)."""
    txt = [_norm(t.text) for t in doc] if doc is not None else []
    if not any(txt[i] == "por" and txt[i + 1] == "favor" for i in range(len(txt) - 1)):
        return
    favor = [it for it in items if it.gloss == "FAVOR"]
    if not favor:
        return
    it = favor[0]
    items.remove(it)
    it.gloss = "POR-FAVOR"
    it.notes = "Cortesía (FENASEC)"
    items.insert(0, it)


def apply_fenasec_rules(
    items: List[GlossItem], doc: Any, start_order: int, proposition: Any = None
) -> List[GlossItem]:
    """Aplica las reglas 2b, 4 y 5 in-place y devuelve la lista renumerada."""
    apply_por_favor(items, doc)
    apply_incorporated_negation(items, doc)
    apply_directional_verbs(items, doc, proposition=proposition)
    apply_intensity_duplication(items, doc)
    _renumber(items, start_order)
    return items
