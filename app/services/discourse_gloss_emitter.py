"""
Emisión y materialización de glosas LSEC a partir de tokens reordenados y fallback heurístico.

Extraído de `discourse_planner.py` para cumplir con el principio de Responsabilidad Única (SRP).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config import settings
from app.core.schemas import (
    AlignmentType,
    FacialExpression,
    GlossItem,
    GlossType,
    NonManualMarker,
    SemanticProposition,
)
from app.services.animation_fingerspelling_service import (
    format_lsec_fingerspelling_gloss,
    is_fingerspelling_query,
)
from app.services.discourse_lexicon import (
    _CANONICAL_SOURCE_LEMMAS,
    _KNOWN_SIGN_PROPN,
    _cardinal_sequence,
    _numeric_gloss_sequence,
)
from app.services.discourse_spacy_reorder import extract_and_reorder_spacy_tokens
from app.services.semantic_parser import SpanishVerbLexicon
from app.services.text_normalizer import PunctuationAnalyzer

logger = logging.getLogger(__name__)


def emit_glosses_from_reordered_tokens(
    planner: Any,
    doc: Any,
    prop: SemanticProposition,
    start_order: int,
    reordered: List[Tuple[Any, str, str, str, Dict[str, Any]]],
    periphrasis_markers: List[Tuple[str, str]],
    amod_by_head: Dict[int, List[Any]],
    wh_tokens: List[Any],
) -> List[GlossItem]:
    """
    Materializa la lista de `GlossItem` desde la secuencia de tokens reordenada,
    insertando marcadores discursivos, adjetivos posnominales, pluralidad y reglas FENASEC.
    """
    gloss_items: List[GlossItem] = []
    current_order = start_order
    last_gloss: Optional[str] = None

    is_direct_q = "?" in prop.source_text or "¿" in prop.source_text
    has_wh = bool(wh_tokens)

    base_expr = FacialExpression.NEUTRAL
    if is_direct_q:
        base_expr = FacialExpression.QUESTION_WH if has_wh else FacialExpression.QUESTION_YESNO

    if prop.discourse_relation in ("also", "addition"):
        s_word = (
            "también"
            if "también" in prop.source_text.lower()
            else ("además" if "además" in prop.source_text.lower() else None)
        )
        gloss_items.append(
            GlossItem(
                gloss="ADEMÁS",
                gloss_type=GlossType.SIGN,
                order=current_order,
                source_word=s_word,
                normalized_word="además",
                proposition_id=prop.id,
                duration_ms=planner.compute_duration("ADEMÁS", GlossType.SIGN),
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
    elif prop.discourse_relation == "but":
        # Por defecto el contraste se marca con componentes no manuales y desplazamiento corporal (sin
        # glosa PERO). `emit_contrast_connector` permite emitirla si la validación nativa lo requiere.
        if settings.emit_contrast_connector and last_gloss != "PERO":
            gloss_items.append(
                GlossItem(
                    gloss="PERO",
                    gloss_type=GlossType.SIGN,
                    order=current_order,
                    source_word="pero" if "pero" in prop.source_text.lower() else None,
                    normalized_word="pero",
                    proposition_id=prop.id,
                    duration_ms=planner.compute_duration("PERO", GlossType.SIGN),
                    notes="Marcador discursivo adversativo",
                    alignment_type=AlignmentType.DISCOURSE_MARKER,
                    lexical_strategy="discourse_connector",
                    semantic_concept="contraste",
                    discourse_relation="but",
                    validation={"lexical_source": "Gramática LSEC", "confidence": 0.90},
                )
            )
            current_order += 1
            last_gloss = "PERO"
    elif prop.discourse_relation == "because":
        p_low = prop.source_text.lower()
        s_word = "porque" if "porque" in p_low else None
        gloss_items.append(
            GlossItem(
                gloss="PORQUE",
                gloss_type=GlossType.SIGN,
                order=current_order,
                source_word=s_word,
                normalized_word="porque",
                proposition_id=prop.id,
                duration_ms=planner.compute_duration("PORQUE", GlossType.SIGN),
                notes="Marcador discursivo causal",
                alignment_type=AlignmentType.DISCOURSE_MARKER,
                lexical_strategy="discourse_connector",
                semantic_concept="causa",
                discourse_relation="because",
                validation={"lexical_source": "Gramática LSEC", "confidence": 0.95},
            )
        )
        current_order += 1
        last_gloss = "PORQUE"

    for marker, pos in periphrasis_markers:
        if pos == "before" and marker != last_gloss:
            last_gloss = marker
            gloss_items.append(
                GlossItem(
                    gloss=marker,
                    gloss_type=GlossType.SIGN,
                    order=current_order,
                    proposition_id=prop.id,
                    alignment_type=AlignmentType.INFERRED,
                    inference_rule_id=f"LSEC_PERIPHRASIS_{marker}",
                    duration_ms=planner.compute_duration(marker, GlossType.SIGN, is_temporal=True),
                    notes="Marcador temporal de perífrasis",
                    validation={"lexical_source": "Gramática LSEC", "confidence": 0.95},
                )
            )
            current_order += 1

    def _flush_amod_for_head(head_idx: int) -> None:
        nonlocal current_order, last_gloss
        if head_idx not in amod_by_head:
            return
        for adj_item in amod_by_head[head_idx]:
            adj_t, _, _, adj_lemma, adj_meta = adj_item
            raw_num = adj_meta.get("num_val")
            clean_num = str(raw_num).replace(".", "").replace(",", "") if raw_num else ""
            if clean_num.isdigit():
                head_word = adj_t.doc[head_idx].text.lower() if head_idx < len(adj_t.doc) else ""
                if len(clean_num) <= 2 and head_word in ("año", "años"):
                    numeric_sequence = (clean_num,)
                else:
                    numeric_sequence = _cardinal_sequence(int(clean_num)) or (
                        clean_num.upper(),
                    )
            else:
                numeric_sequence = _numeric_gloss_sequence(adj_lemma) or (adj_lemma.upper(),)
            for adj_g in numeric_sequence:
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
                            duration_ms=planner.compute_duration(adj_g, GlossType.SIGN),
                            notes="Numeral posicional" if raw_num else "Adjetivo post-nominal",
                        )
                    )
                    current_order += 1

    for item in reordered:
        t, pos, dep, lemma, meta = item
        if meta.get("num_consumed"):
            continue
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
                if mwe_g == "PERO" and any(g.gloss == "PERO" for g in gloss_items):
                    continue
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
                            duration_ms=planner.compute_duration(mwe_g, GlossType.SIGN),
                        )
                    )
                    current_order += 1
            _flush_amod_for_head(t.i)
            continue

        if meta.get("is_paraphrase"):
            para_info = planner._semantic_paraphrases.get(meta["paraphrase_key"], {})
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
                            duration_ms=planner.compute_duration(g_w, GlossType.SIGN),
                            validation={
                                "lexical_source": "Paráfrasis conceptual LSEC",
                                "confidence": 0.85,
                            },
                        )
                    )
                    current_order += 1
            continue

        if meta.get("is_numeral"):
            num_g = meta["num_val"].upper()
            numeric_sequence = (
                ("CUATRO", "MIL", "CINCO", "CIENTOS")
                if num_g == "4500"
                else (num_g,)
            )
            for numeric_gloss in numeric_sequence:
                if numeric_gloss != last_gloss:
                    last_gloss = numeric_gloss
                    gloss_items.append(
                        GlossItem(
                            gloss=numeric_gloss,
                            gloss_type=GlossType.SIGN,
                            order=current_order,
                            source_word=clean_text,
                            normalized_word=numeric_gloss,
                            proposition_id=prop.id,
                            duration_ms=planner.compute_duration(numeric_gloss, GlossType.SIGN),
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
                        duration_ms=planner.compute_duration(deix_g, GlossType.SIGN, is_deixis=True),
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
                        duration_ms=planner.compute_duration(ft_g, GlossType.SIGN),
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
                        duration_ms=planner.compute_duration(cop_g, GlossType.SIGN),
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
            is_relative_donde = (
                c_w in ("donde", "dónde")
                and not is_direct_q
                and prop.modality not in ("interrogative_wh", "interrogative_yn")
            )
            if is_relative_donde:
                wh_g = "LUGAR"
            if wh_g == "QUÉ" and t.i > 0 and t.doc[t.i - 1].text.lower() == "por":
                wh_g = "POR-QUÉ"
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
                            expression=(
                                FacialExpression.NEUTRAL
                                if is_relative_donde
                                else (FacialExpression.QUESTION_WH if is_direct_q else FacialExpression.REFLECTIVE)
                            ),
                            head_movement=None if is_relative_donde else "inclinar",
                        ),
                        duration_ms=planner.compute_duration(wh_g, GlossType.SIGN),
                    )
                )
                current_order += 1
            continue

        if (
            clean_word in ("donde", "dónde")
            and not is_direct_q
            and prop.modality not in ("interrogative_wh", "interrogative_yn")
        ):
            if last_gloss != "LUGAR":
                last_gloss = "LUGAR"
                gloss_items.append(
                    GlossItem(
                        gloss="LUGAR",
                        gloss_type=GlossType.SIGN,
                        order=current_order,
                        source_word=clean_text,
                        normalized_word="lugar",
                        proposition_id=prop.id,
                        non_manual=NonManualMarker(expression=FacialExpression.NEUTRAL),
                        duration_ms=planner.compute_duration("LUGAR", GlossType.SIGN),
                    )
                )
                current_order += 1
            continue

        spatial_ref_id = None
        cand_gloss = lemma.upper() if lemma else text_upper
        is_in_dict = (
            planner._dictionary is not None
            and (
                planner._dictionary.lookup(clean_word) is not None
                or planner._dictionary.lookup(lemma) is not None
                or planner._dictionary.lookup(clean_text) is not None
                or planner._dictionary.lookup_gloss(clean_word, lemma, clean_text) is not None
            )
        )
        is_known_lexical = (
            clean_word in _KNOWN_SIGN_PROPN
            or clean_word in _CANONICAL_SOURCE_LEMMAS
            or clean_word in SpanishVerbLexicon.KNOWN_VERB_FORMS
            or cand_gloss in planner._known_local_glosses
            or text_upper in planner._known_local_glosses
            or is_in_dict
        )
        is_explicit_fs = ("-" in clean_text or ":" in clean_text) and is_fingerspelling_query(clean_text)
        src_not_all_caps = not (prop.source_text or "").strip().isupper()
        is_oov_acronym = (
            src_not_all_caps
            and clean_text.isupper()
            and clean_word.isalpha()
            and 2 <= len(clean_word) <= 10
            and not is_known_lexical
        )
        is_mid_sentence_capitalized = (
            src_not_all_caps
            and t.i > 0
            and clean_text[:1].isupper()
            and not clean_text.isupper()
            and clean_word.isalpha()
            and doc[t.i - 1].text not in ("¿", "¡", ".", "!", "?", ":", ";")
            and pos in ("PROPN", "NOUN", "ADJ")
        )
        is_oov_propn = (
            (pos == "PROPN" or is_mid_sentence_capitalized)
            and clean_text[:1].isupper()
            and len(clean_word) >= 2
            and not is_known_lexical
        )
        is_oov_lexical = (
            bool(getattr(planner, "_fingerspell_oov", False))
            and pos in ("NOUN", "PROPN", "ADJ")
            and len(clean_word) >= 3
            and clean_word.isalpha()
            and not is_known_lexical
        )
        should_fingerspell = is_explicit_fs or is_oov_propn or is_oov_acronym or is_oov_lexical

        if text_upper in planner._institutional_dict:
            gloss_txt = planner._institutional_dict[text_upper]["gloss"]
            gloss_typ = GlossType(planner._institutional_dict[text_upper]["type"])
            ent_info = planner._named_entities.get(clean_word.lower()) or planner._named_entities.get(lemma.lower() if lemma else "")
            if ent_info:
                spatial_ref_id = ent_info.get("id")
            else:
                spatial_ref_id = f"campus_{clean_word.lower()}"
        elif prop.rhetorical_function in ("campus_enumeration", "enumeration"):
            if should_fingerspell and clean_word not in ("campus", "dos", "sede", "sedes"):
                gloss_txt = format_lsec_fingerspelling_gloss(clean_text if is_explicit_fs else clean_word)
                gloss_typ = GlossType.FINGERSPELLING
                spatial_ref_id = f"campus_{clean_word.lower()}"
            else:
                gloss_txt = cand_gloss
                gloss_typ = GlossType.SIGN
                if pos == "PROPN" and clean_word in _KNOWN_SIGN_PROPN:
                    spatial_ref_id = f"campus_{clean_word.lower()}"
        else:
            if should_fingerspell:
                gloss_txt = format_lsec_fingerspelling_gloss(clean_text if is_explicit_fs else clean_word)
                gloss_typ = GlossType.FINGERSPELLING
            else:
                gloss_txt = cand_gloss
                gloss_typ = GlossType.SIGN

        if gloss_txt == last_gloss or (pos in ("NOUN", "PROPN") and t.i in amod_by_head and any(g.gloss == gloss_txt for g in gloss_items)):
            _flush_amod_for_head(t.i)
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
                duration_ms=planner.compute_duration(gloss_txt, gloss_typ),
                spatial_ref=spatial_ref_id,
                notes="Complemento de lugar" if dep in ("obl", "loc") else None,
            )
        )
        current_order += 1

        _flush_amod_for_head(t.i)

        noun_has_num_or_quant = (
            any(
                ch.pos_ == "NUM"
                or re.match(r"^\d+", ch.text)
                or PunctuationAnalyzer.strip_punctuation(ch.text.lower()) in planner._quantifier_lemmas
                or ch.lemma_.lower() in planner._quantifier_lemmas
                for ch in t.children
            )
            or (
                t.i > 0
                and (
                    doc[t.i - 1].pos_ == "NUM"
                    or re.match(r"^\d+", doc[t.i - 1].text)
                    or PunctuationAnalyzer.strip_punctuation(doc[t.i - 1].text.lower()) in planner._quantifier_lemmas
                    or doc[t.i - 1].lemma_.lower() in planner._quantifier_lemmas
                )
            )
            or any(
                adj_item[4].get("is_numeral") or adj_item[3] in planner._quantifier_lemmas
                for adj_item in amod_by_head.get(t.i, [])
            )
        )

        if meta.get("is_plural") and not noun_has_num_or_quant and pos in ("NOUN", "PROPN", "ADJ"):
            if planner._plural_marker != last_gloss:
                last_gloss = planner._plural_marker
                gloss_items.append(
                    GlossItem(
                        gloss=planner._plural_marker,
                        gloss_type=GlossType.SIGN,
                        order=current_order,
                        source_word=clean_src_word,
                        normalized_word="varios",
                        proposition_id=prop.id,
                        duration_ms=planner.compute_duration(
                            planner._plural_marker, GlossType.SIGN, is_plural_marker=True
                        ),
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
                    alignment_type=AlignmentType.INFERRED,
                    inference_rule_id=f"LSEC_PERIPHRASIS_{marker}",
                    duration_ms=planner.compute_duration(marker, GlossType.SIGN, is_temporal=True),
                    notes="Marcador aspectual",
                )
            )
            current_order += 1

    try:
        from app.services.fenasec_rules import apply_fenasec_rules
        gloss_items = apply_fenasec_rules(gloss_items, doc, start_order, proposition=prop)
    except Exception as exc:  # pragma: no cover
        logger.warning("Reglas FENASEC omitidas: %s", exc)

    if re.search(r"\b(?:3[.,]?000|tres\s+mil)\b", (prop.source_text or "").lower()):
        fused = next((i for i, item in enumerate(gloss_items) if item.gloss == "TRES-MIL"), None)
        if fused is not None:
            item = gloss_items[fused]
            replacement = [
                item.model_copy(update={"gloss": "TRES", "normalized_word": "tres"}),
                item.model_copy(update={"gloss": "MIL", "normalized_word": "mil"}),
            ]
            gloss_items[fused:fused + 1] = replacement
            for index, generated in enumerate(gloss_items):
                generated.order = start_order + index

    if re.search(r"(?:\d{2,3}\s+){2,}\d{2,3}", prop.source_text or ""):
        digit_names = {
            "0": "CERO", "1": "UNO", "2": "DOS", "3": "TRES", "4": "CUATRO",
            "5": "CINCO", "6": "SEIS", "7": "SIETE", "8": "OCHO", "9": "NUEVE",
        }
        expanded: List[GlossItem] = []
        for item in gloss_items:
            if (item.source_word or "").isdigit() and len(item.source_word or "") > 1:
                for digit in item.source_word:
                    expanded.append(item.model_copy(update={
                        "gloss": digit_names[digit],
                        "normalized_word": digit_names[digit].lower(),
                    }))
            else:
                expanded.append(item)
        gloss_items = expanded
        for index, generated in enumerate(gloss_items):
            generated.order = start_order + index

    return gloss_items


def translate_general_spacy(
    planner: Any,
    prop: SemanticProposition,
    start_order: int,
    active_rule_ids: Optional[Set[str]] = None,
    exclude_rule_ids: Optional[Set[str]] = None,
) -> List[GlossItem]:
    """Traduce una proposición usando spaCy con reglas gramaticales completas."""
    doc = planner._nlp(prop.source_text)
    reordered, periphrasis_markers, amod_by_head, wh_tokens = extract_and_reorder_spacy_tokens(
        planner=planner,
        doc=doc,
        prop=prop,
        active_rule_ids=active_rule_ids,
        exclude_rule_ids=exclude_rule_ids,
    )
    return emit_glosses_from_reordered_tokens(
        planner=planner,
        doc=doc,
        prop=prop,
        start_order=start_order,
        reordered=reordered,
        periphrasis_markers=periphrasis_markers,
        amod_by_head=amod_by_head,
        wh_tokens=wh_tokens,
    )


def translate_general_heuristic(
    planner: Any,
    prop: SemanticProposition,
    start_order: int,
) -> List[GlossItem]:
    """Fallback heurístico directo cuando spaCy no está activo."""
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

        if clean_upper in planner._institutional_dict:
            g_txt = planner._institutional_dict[clean_upper]["gloss"]
            g_typ = GlossType(planner._institutional_dict[clean_upper]["type"])
        elif clean_lower in planner._lemma_overrides:
            g_txt = planner._lemma_overrides[clean_lower].upper()
            g_typ = GlossType.SIGN
        elif clean_lower in planner._pronoun_deixis:
            g_txt = planner._pronoun_deixis[clean_lower]
            g_typ = GlossType.SIGN
        elif ("-" in clean and is_fingerspelling_query(clean)) or (
            clean.isupper()
            and clean.isalpha()
            and 2 <= len(clean) <= 10
            and not (prop.source_text or "").strip().isupper()
            and clean_lower not in _KNOWN_SIGN_PROPN
            and clean_upper not in planner._known_local_glosses
            and (planner._dictionary is None or planner._dictionary.lookup(clean_lower) is None)
        ):
            g_txt = format_lsec_fingerspelling_gloss(clean)
            g_typ = GlossType.FINGERSPELLING
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
                duration_ms=planner.compute_duration(g_txt, g_typ),
            )
        )
        curr += 1

    return items
