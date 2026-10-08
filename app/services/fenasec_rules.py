"""Reglas FENASEC/CONADIS deterministas aplicadas sobre las glosas planificadas.

Reglas cubiertas (100% lingüísticas, sin LLM):
  2b. Negación léxica incorporada: ``NO-SABER``, ``NO-QUERER``, ``NO-PODER``,
      ``NO-GUSTAR``, ``NO-HABER`` (se elimina el ``NO`` final).
  4.  Verbos direccionales: ``AVISAR[1->2]``, ``ENSEÑAR[3->1-PL]`` (se eliminan
      los pronombres redundantes de agente y receptor).
  5.  Duplicación segmental de intensidad: ``LLOVER++``, ``ESTUDIAR++``.
"""
import re
from typing import Any, List, Optional

from app.core.schemas import FacialExpression, GlossItem, NonManualMarker

INCORPORATED_NEGATION_VERBS = {"SABER", "QUERER", "PODER", "GUSTAR", "HABER"}
DIRECTIONAL_VERBS = {"AVISAR", "ENSEÑAR", "DAR", "PREGUNTAR", "INFORMAR", "MOSTRAR"}
_RECIPIENT_CLITICS = {"me", "te", "nos", "le", "les", "se", "os"}
_INTENSIFIER_RE = re.compile(r"^(muchísim[oa]s?|\w{3,}ísim[oa]s?)$", re.IGNORECASE)
_PRO_RE = re.compile(r"^PRO([123])(-PL)?$")


def _norm(src: Optional[str]) -> str:
    return re.sub(r"[^\wáéíóúñü]", "", (src or "").lower())


def _find_token(doc: Any, word: Optional[str]):
    w = _norm(word)
    if not w:
        return None
    for t in doc:
        if _norm(t.text) == w:
            return t
    return None


def _renumber(items: List[GlossItem], start_order: int) -> None:
    for i, it in enumerate(items):
        it.order = start_order + i


def _verb_person_label(doc: Any, verb_item: GlossItem) -> str:
    tok = _find_token(doc, verb_item.source_word)
    if tok is None:
        return "3"
    person = tok.morph.get("Person", [])
    number = tok.morph.get("Number", [])
    if not person:
        txt = tok.text.lower()
        if txt.endswith(("amos", "emos", "imos")):
            person, number = ["1"], ["Plur"]
        elif txt.endswith(("as", "es", "ás", "és")):
            person = ["2"]
        elif txt.endswith(("o", "é")):
            person = ["1"]
        else:
            person = ["3"]
    label = person[0]
    if "Plur" in number:
        label += "-PL"
    return label


def apply_incorporated_negation(items: List[GlossItem], doc: Any) -> None:
    neg_items = [it for it in items if it.gloss == "NO"]
    if not neg_items:
        return
    for it in list(items):
        if it.gloss not in INCORPORATED_NEGATION_VERBS:
            continue
        tok = _find_token(doc, it.source_word)
        if tok is None or tok.i == 0:
            continue
        if _norm(doc[tok.i - 1].text) != "no":
            continue
        it.gloss = f"NO-{it.gloss}"
        it.notes = "Negación léxica incorporada (FENASEC)"
        it.non_manual = NonManualMarker(expression=FacialExpression.NEGATION, head_movement="negar")
        for n in neg_items:
            if n in items:
                items.remove(n)
        return


def apply_directional_verbs(items: List[GlossItem], doc: Any) -> None:
    for vi, verb in enumerate(list(items)):
        if verb.gloss not in DIRECTIONAL_VERBS:
            continue
        idx = items.index(verb)
        pros = [(i, it) for i, it in enumerate(items[:idx]) if _PRO_RE.match(it.gloss)]
        if not pros:
            continue
        clitic_pros = [(i, it) for i, it in pros if _norm(it.source_word) in _RECIPIENT_CLITICS]
        if len(pros) >= 2:
            agent_i, agent = pros[0]
            rec_i, rec = pros[-1]
            agent_label = agent.gloss[3:]
            rec_label = rec.gloss[3:]
            drop = [agent, rec]
        elif clitic_pros:
            rec_i, rec = clitic_pros[0]
            rec_label = rec.gloss[3:]
            has_noun_subject = any(
                (not _PRO_RE.match(it.gloss)) and it.gloss not in ("NO",) and
                (_find_token(doc, it.source_word) is not None and
                 _find_token(doc, it.source_word).dep_ in ("nsubj", "nsubj:pass"))
                for it in items[:idx]
            )
            agent_label = "3" if has_noun_subject else _verb_person_label(doc, verb)
            drop = [rec]
        else:
            continue
        verb.gloss = f"{verb.gloss}[{agent_label}->{rec_label}]"
        verb.notes = "Verbo direccional (FENASEC)"
        for d in drop:
            if d in items:
                items.remove(d)


def apply_intensity_duplication(items: List[GlossItem], doc: Any) -> None:
    intens = [it for it in items if _INTENSIFIER_RE.match(_norm(it.source_word) or "")]
    if not intens:
        return
    verb_item = None
    for it in items:
        tok = _find_token(doc, it.source_word)
        if tok is not None and tok.pos_ in ("VERB", "AUX") and tok.lemma_.lower() not in ("estar", "ser"):
            verb_item = it
    if verb_item is None:
        return
    verb_item.gloss = f"{verb_item.gloss}++"
    verb_item.notes = "Duplicación segmental de intensidad (FENASEC)"
    verb_item.non_manual = NonManualMarker(expression=FacialExpression.SUPERLATIVE, head_movement=None)
    for it in intens:
        items.remove(it)
    for it in list(items):
        if it.gloss == "AHORA" and it.notes == "Marcador aspectual":
            items.remove(it)


def apply_por_favor(items: List[GlossItem], doc: Any) -> None:
    """Cortesía: 'por favor' se glosa POR-FAVOR y se antepone (marcador de apertura)."""
    txt = [_norm(t.text) for t in doc]
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


def apply_fenasec_rules(items: List[GlossItem], doc: Any, start_order: int) -> List[GlossItem]:
    """Aplica las reglas 2b, 4 y 5 in-place y devuelve la lista renumerada."""
    apply_por_favor(items, doc)
    apply_incorporated_negation(items, doc)
    apply_directional_verbs(items, doc)
    apply_intensity_duplication(items, doc)
    _renumber(items, start_order)
    return items
