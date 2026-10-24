"""
Utilidades morfosintácticas, detección de perífrasis verbales y saneamiento contextual de glosas LSEC.

Extraído de `discourse_planner.py` para cumplir con el principio de Responsabilidad Única (SRP).
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Set, Tuple

from app.core.schemas import (
    AlignmentType,
    GlossItem,
    GlossType,
    SemanticProposition,
)
from app.services.discourse_lexicon import (
    _NUMBER_WORD_VALUES,
    _cardinal_sequence,
    _number_words_value,
    _numeric_gloss_sequence,
)
from app.services.semantic_parser import SpanishVerbLexicon
from app.services.text_normalizer import PunctuationAnalyzer


def has_nominal_context(token: Any) -> bool:
    """Evidencia sintáctica de uso nominal (determinante, adjetivo o numeral)."""
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


def normalize_nominal_lemma(clean_word: str, raw_lemma: str) -> str:
    """
    Corrige lemas nominales truncados por spaCy (p. ej. *medicina* -> *medicín*)
    sin dañar plurales ni derivados regulares.
    """
    raw = PunctuationAnalyzer.strip_punctuation((raw_lemma or "").lower())
    clean = PunctuationAnalyzer.strip_punctuation((clean_word or "").lower())
    if not raw:
        return clean
    if not clean:
        return raw
    raw_flat = raw.translate(str.maketrans("áéíóúü", "aeiouu"))
    clean_flat = clean.translate(str.maketrans("áéíóúü", "aeiouu"))

    if clean.endswith("s"):
        if clean.endswith("es"):
            singular = clean[:-2]
        else:
            singular = clean[:-1]
        singular_flat = singular.translate(str.maketrans("áéíóúü", "aeiouu"))
        if (
            len(raw_flat) >= 3
            and singular_flat.startswith(raw_flat)
            and 0 < len(singular_flat) - len(raw_flat) <= 2
        ):
            return singular
        return raw

    if (
        len(raw_flat) >= 3
        and clean_flat.startswith(raw_flat)
        and 0 < len(clean_flat) - len(raw_flat) <= 2
    ):
        return clean
    return raw


def detect_periphrasis_in_doc(doc: Any) -> List[Tuple[str, str, Set[int]]]:
    """Detecta perífrasis verbales en el doc spaCy."""
    results: List[Tuple[str, str, Set[int]]] = []
    consumed: Set[int] = set()

    for token in doc:
        if token.i in consumed:
            continue
        clean_tok = PunctuationAnalyzer.strip_punctuation(token.text.lower())
        lemma_lower = (
            SpanishVerbLexicon.get_lemma(clean_tok, pos=token.pos_)
            or PunctuationAnalyzer.strip_punctuation(token.lemma_.lower())
        )

        # ir + a + infinitivo -> FUTURO (solo si 'a' e infinitivo son contiguos)
        if lemma_lower == "ir" and (
            token.pos_ in ("AUX", "VERB") or clean_tok in ("voy", "vas", "va", "vamos", "van")
        ):
            if (
                token.i + 2 < len(doc)
                and doc[token.i + 1].text.lower() == "a"
                and (
                    doc[token.i + 2].pos_ in ("VERB", "AUX")
                    or PunctuationAnalyzer.strip_punctuation(doc[token.i + 2].text.lower()).endswith(("ar", "er", "ir"))
                )
                and (
                    "Inf" in doc[token.i + 2].morph.get("VerbForm", [])
                    or PunctuationAnalyzer.strip_punctuation(doc[token.i + 2].text.lower()).endswith(("ar", "er", "ir"))
                )
            ):
                prep_a = doc[token.i + 1]
                consumed_set = {token.i, prep_a.i}
                has_future_adverb = any(
                    t.text.lower() in ("mañana", "después", "pronto", "futuro") for t in doc
                )
                if not has_future_adverb:
                    results.append(("FUTURO", "before", consumed_set))
                else:
                    results.append(("", "", consumed_set))
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
                has_explicit_ya = any(
                    PunctuationAnalyzer.strip_punctuation(t.text.lower()) == "ya" for t in doc
                )
                if not has_conflicting_past and not has_explicit_ya:
                    results.append(("YA", "after", consumed_set))
                else:
                    results.append(("", "", consumed_set))
                consumed |= consumed_set

        # estar + gerundio: aspecto progresivo (separado de tiempo deíctico)
        elif lemma_lower == "estar" and token.pos_ in ("AUX", "VERB"):
            has_gerund = (
                (token.dep_ in ("aux", "auxpass") and "Ger" in token.head.morph.get("VerbForm", []))
                or any("Ger" in child.morph.get("VerbForm", []) for child in token.children)
            )
            if has_gerund:
                consumed_set = {token.i}
                has_explicit_present = any(
                    t.text.lower() in ("ahora", "hoy", "actualmente") for t in doc
                )
                has_past_tense = any(
                    "Past" in t.morph.get("Tense", []) or t.text.lower() in ("ayer", "antes", "anoche", "pasado")
                    for t in doc
                )
                if has_explicit_present and not has_past_tense:
                    results.append(("AHORA", "after", consumed_set))
                else:
                    results.append(("", "", consumed_set))
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


def sanitize_contextual_glosses(
    proposition: SemanticProposition,
    glosses: List[GlossItem],
    start_order: int,
) -> List[GlossItem]:
    """Remueve transferencias espurias y conserva el orden semántico de la fuente."""
    source = (proposition.source_text or "").lower()

    # --- Composición numérica posicional ------------------------------
    expanded: List[GlossItem] = []
    for item in glosses:
        if (
            item.gloss.isdigit()
            and len(item.gloss) <= 2
            and re.search(rf"\b{re.escape(item.gloss)}\s+años\b", source)
        ):
            expanded.append(item)
            continue
        sequence = _numeric_gloss_sequence(item.gloss)
        if not sequence:
            expanded.append(item)
            continue
        for value in sequence:
            expanded.append(
                item.model_copy(
                    update={
                        "gloss": value,
                        "normalized_word": value.lower(),
                        "gloss_type": GlossType.SIGN,
                        "alignment_type": AlignmentType.MULTIWORD,
                        "notes": "Composición numérica posicional",
                    }
                )
            )
    glosses = expanded

    def _place(value: str) -> Optional[int]:
        if value == "MIL":
            return 3
        if value in ("CIENTOS", "CIENTO", "CIEN") or value.endswith("CIENTOS"):
            return 2
        if value in (
            "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA",
            "SETENTA", "OCHENTA", "NOVENTA",
        ):
            return 1
        if value.lower() in _NUMBER_WORD_VALUES or value.isdigit():
            return 0
        return None

    reordered: List[GlossItem] = []
    index = 0
    while index < len(glosses):
        if _place(glosses[index].gloss) is None:
            reordered.append(glosses[index])
            index += 1
            continue
        end = index
        while end < len(glosses) and _place(glosses[end].gloss) is not None:
            end += 1
        cluster = glosses[index:end]
        if any(_place(item.gloss) in (2, 3) for item in cluster):
            components: List[Tuple[int, List[GlossItem]]] = []
            cursor = 0
            while cursor < len(cluster):
                current = cluster[cursor]
                current_place = _place(current.gloss)
                following = cluster[cursor + 1].gloss if cursor + 1 < len(cluster) else None
                if current_place == 0 and following in ("MIL", "CIENTOS"):
                    pair_place = 3 if following == "MIL" else 2
                    components.append((pair_place, [current, cluster[cursor + 1]]))
                    cursor += 2
                    continue
                components.append((current_place or 0, [current]))
                cursor += 1
            components.sort(key=lambda entry: -entry[0])
            cluster = [item for _, items in components for item in items]
        reordered.extend(cluster)
        index = end
    glosses = reordered

    # Hora del día: el bloque HORA HH MM debe quedar contiguo.
    hour_index = 0
    while hour_index < len(glosses):
        if glosses[hour_index].gloss != "HORA":
            hour_index += 1
            continue
        hour_end = hour_index + 1
        while hour_end < len(glosses) and _place(glosses[hour_end].gloss) is not None:
            hour_end += 1
        hour_run = glosses[hour_index + 1:hour_end]
        if len(hour_run) > 2:
            extras = hour_run[:-2]
            hour_pair = hour_run[-2:]
            glosses = (
                glosses[:hour_index]
                + extras
                + [glosses[hour_index]]
                + hour_pair
                + glosses[hour_end:]
            )
            hour_index += len(extras) + 3
            continue
        hour_index = hour_end

    # El porcentaje se realiza DESPUÉS del bloque numérico: CIEN PORCENTAJE.
    idx = 0
    while idx < len(glosses):
        if (
            glosses[idx].gloss == "PORCENTAJE"
            and idx + 1 < len(glosses)
            and _place(glosses[idx + 1].gloss) is not None
        ):
            end = idx + 1
            while end < len(glosses) and _place(glosses[end].gloss) is not None:
                end += 1
            percentage = glosses.pop(idx)
            glosses.insert(end - 1, percentage)
            idx = end
            continue
        idx += 1

    # Consolidar frases numerales escritas ("ciento cincuenta")
    _HUNDRED_MARKERS = {
        "mil", "cien", "ciento", "doscientos", "trescientos",
        "cuatrocientos", "quinientos", "seiscientos", "setecientos",
        "ochocientos", "novecientos",
    }
    numeric_runs: List[List[str]] = []
    current_run: List[str] = []
    for token in re.findall(r"[a-záéíóúüñ]+", source):
        if token in _NUMBER_WORD_VALUES:
            current_run.append(token)
        elif token == "y" and current_run:
            current_run.append(token)
        else:
            if current_run:
                numeric_runs.append(current_run)
            current_run = []
    if current_run:
        numeric_runs.append(current_run)

    consumed_number_ids: Set[int] = set()
    for run in numeric_runs:
        clean_words = [word for word in run if word != "y"]
        if len(clean_words) < 2 or "cero" in clean_words:
            continue
        if not (("y" in run) or any(word in _HUNDRED_MARKERS for word in clean_words)):
            continue
        value = _number_words_value(clean_words)
        desired_numbers = _cardinal_sequence(value) if value else ()
        if len(desired_numbers) < 2:
            continue
        chosen_numbers: List[GlossItem] = []
        for component in desired_numbers:
            match_item = next(
                (
                    item
                    for item in glosses
                    if id(item) not in consumed_number_ids
                    and item.gloss == component
                    and (item.source_word or "").lower() in clean_words
                ),
                None,
            )
            if match_item is None:
                break
            chosen_numbers.append(match_item)
        if len(chosen_numbers) != len(desired_numbers):
            continue
        number_ids = {id(item) for item in chosen_numbers}
        number_insert_at = min(
            index for index, item in enumerate(glosses) if id(item) in number_ids
        )
        number_block = [
            anchor.model_copy(update={"gloss": gloss, "normalized_word": gloss.lower()})
            for gloss, anchor in zip(desired_numbers, chosen_numbers)
        ]
        consumed_number_ids |= number_ids
        glosses = [item for item in glosses if id(item) not in number_ids]
        glosses[number_insert_at:number_insert_at] = number_block
        consumed_number_ids |= {id(item) for item in number_block}

    # Consolidar "N porcentaje" como bloque contiguo
    consumed_percent_ids: Set[int] = set()
    percent_matches = list(
        re.finditer(
            r"([a-záéíóúüñ]+(?:\s+(?:y\s+)?[a-záéíóúüñ]+){0,3})\s+porcentaje\b",
            source,
        )
    )
    for match in percent_matches:
        numeric_words: List[str] = []
        for token in reversed(match.group(1).split()):
            if token in _NUMBER_WORD_VALUES or token == "y":
                numeric_words.insert(0, token)
            else:
                break
        raw_words = [w for w in numeric_words if w != "y"]
        if not raw_words or any(w not in _NUMBER_WORD_VALUES for w in raw_words):
            continue
        value = _number_words_value(raw_words)
        if value is None:
            continue
        desired = _cardinal_sequence(value) + ("PORCENTAJE",)
        remaining = list(desired[:-1])
        chosen: List[GlossItem] = []
        for component in list(remaining):
            match_item = next(
                (
                    item
                    for item in glosses
                    if id(item) not in consumed_percent_ids
                    and item.gloss == component
                    and (item.source_word or "").lower() in raw_words
                ),
                None,
            )
            if match_item is None:
                match_item = next(
                    (
                        item
                        for item in glosses
                        if id(item) not in consumed_percent_ids
                        and item.gloss == component
                    ),
                    None,
                )
            if match_item is None:
                break
            chosen.append(match_item)
            remaining.remove(component)
        if remaining or len(chosen) != len(desired) - 1:
            continue
        percentage = next(
            (
                item
                for item in glosses
                if id(item) not in consumed_percent_ids and item.gloss == "PORCENTAJE"
            ),
            None,
        )
        if percentage is None:
            continue
        block_ids = {id(item) for item in chosen} | {id(percentage)}
        insert_at = min(
            index for index, item in enumerate(glosses) if id(item) in block_ids
        )
        block = [
            anchor.model_copy(update={"gloss": gloss, "normalized_word": gloss.lower()})
            for gloss, anchor in zip(desired, chosen + [percentage])
        ]
        consumed_percent_ids |= block_ids
        glosses = [item for item in glosses if id(item) not in block_ids]
        glosses[insert_at:insert_at] = block
        consumed_percent_ids |= {id(item) for item in block}

    # --- Preposición instrumental --------------------------------
    glosses = [
        item
        for index, item in enumerate(glosses)
        if not (
            item.gloss == "POR"
            and index + 1 < len(glosses)
            and glosses[index + 1].gloss in ("CORREO-ELECTRÓNICO", "CORREO", "POR-QUÉ", "PORQUE")
        )
    ]

    # --- PROPÓSITO inicial en interrogativas ---------------------
    question_source = "?" in (proposition.source_text or "") or proposition.modality in (
        "interrogative_wh",
        "interrogative_yn",
    )
    if question_source:
        while glosses and glosses[0].gloss == "PROPÓSITO":
            glosses.pop(0)

    # La dirección espacial solo se introduce cuando la fuente la expresa.
    if "hacia" not in source:
        glosses = [g for g in glosses if g.gloss != "HACIA"]
    if re.search(r"\bhoy\b", source):
        for item in glosses:
            if item.gloss == "AHORA" and not (item.notes or "").startswith("Insertado por regla LSEC_ASPECT"):
                item.gloss = "HOY"

    if "más que" in source:
        glosses = [g for g in glosses if g.gloss not in {"VARIOS", "SOLAMENTE-NO"}]
        if not any(g.gloss == "MÁS-DE" for g in glosses):
            target_idx = next(
                (i for i, g in enumerate(glosses) if g.gloss in {"PROFESIONAL", "PROFESIONALES"}),
                len(glosses),
            )
            glosses.insert(
                target_idx + (1 if target_idx < len(glosses) else 0),
                GlossItem(
                    gloss="MÁS-DE",
                    gloss_type=GlossType.SIGN,
                    order=0,
                    source_word="más que",
                    normalized_word="más que",
                    proposition_id=proposition.id,
                    alignment_type=AlignmentType.MULTIWORD,
                    duration_ms=500,
                    notes="Comparativo LSEC: más que",
                ),
            )

    if "alrededor" in source:
        glosses = [g for g in glosses if g.gloss != "HACIA"]

    if "opcionando" in source or "están opcionando" in source:
        glosses = [g for g in glosses if g.gloss != "AHORA"]

    if "8 y cuarto" in source:
        eight = next((g for g in glosses if g.gloss in {"8", "OCHO"}), None)
        quarter = next((g for g in glosses if g.gloss == "CUARTO"), None)
        if eight is not None and quarter is not None:
            glosses.remove(eight)
            glosses.remove(quarter)
            insert_at = min(
                [i for i, g in enumerate(glosses) if g.source_word and g.source_word.lower() in {"a", "partir"}]
                or [0]
            )
            glosses[insert_at:insert_at] = [eight, quarter]
    if "8 y cuarto" in source:
        for item in glosses:
            if item.gloss == "CUARTO":
                item.gloss = "QUINCE"
    if "10 y media" in source:
        for item in glosses:
            if item.gloss == "MEDIA":
                item.gloss = "TREINTA"

    for index, gloss in enumerate(glosses):
        gloss.order = start_order + index
    return glosses
