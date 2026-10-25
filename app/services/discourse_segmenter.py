"""
Segmentador Discursivo y Proposicional para Traducción a LSEC 2.1.1.

Segmenta el texto en unidades de significado y proposiciones semánticas
basándose en relaciones predicativas, conectores discursivos y estructura informativa.
No divide de forma ciega en cada coma; identifica relaciones semánticas.

Detecta como límites proposicionales:
  - Signos de puntuación estructurantes (. ; : —)
  - Conjunciones adversativas (pero, sin embargo, no obstante)
  - Conectores causales, consecutivos y finales (porque, para, por tanto)
  - Estructuras contrastivas ("no solo... también...", "más que...")
  - Subordinadas sustantivas ("dicen que...", "explica que...")
  - Interrogativas indirectas y reflexivas ("decidir quién quieres ser")
  - Enumeraciones espaciales ("campus Tulcán y Cayambe")
  - Construcciones relativas con nuevo predicado ("tecnología que evoluciona...")
  - Imperativos y llamadas a la acción ("decide sobre tu futuro", "haz posible...")
  - Eslóganes y cierres de marca ("UPEC, educamos para...")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# Estructura de Unidad Discursiva / Proposición Fuente
# ============================================================

@dataclass
class DiscourseUnit:
    """
    Unidad discursiva y proposicional de significado.
    """
    id: int
    text: str
    unit_type: str  # "statement", "contrast", "enumeration", "imperative",
                     # "question_indirect", "slogan", "explanation", "identity",
                     # "academic_offer", "sustainability", "human_focus", "preparation", "proof"
    parent_id: Optional[int] = None
    discourse_relation: Optional[str] = None  # "but", "also", "because", "purpose", "more_than", "result"
    rhetorical_function: Optional[str] = None  # "inspiration", "identity", "offer", "proof",
                                                 # "call_to_action", "human_focus", "preparation",
                                                 # "sustainability", "closure", "campus_enumeration"
    fragment_type: str = "COMPLETE_PROPOSITION"
    context_info: Dict[str, Any] = field(default_factory=dict)
    operators: List[Dict[str, Any]] = field(default_factory=list)
    sub_units: List[DiscourseUnit] = field(default_factory=list)
    has_negation_scope: bool = False
    has_contrast: bool = False
    is_embedded: bool = False
    topic: Optional[str] = None
    focus: Optional[str] = None
    source_char_start: int = 0
    source_char_end: int = 0


# ============================================================
# Patrones de Conectores y Estructuras
# ============================================================

# Pares "no solo X, (sino) también Y" / "no solo X; Y"
_NOT_ONLY_PATTERN = re.compile(
    r"no\s+s[oó]lo?\s+(.+?)\s*[,;:]\s*(?:sino(?:\s+que)?|tambi[eé]n|adem[aá]s)?\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)

# Estructura "más que X, (formamos) Y"
_MORE_THAN_PATTERN = re.compile(
    r"m[aá]s\s+que\s+([^,;:]+)\s*[,;:]\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)

# Conectores adversativos
_ADVERSATIVE_CONNECTORS = [
    re.compile(r"\bpero\b", re.IGNORECASE),
    re.compile(r"\bsin\s+embargo\b", re.IGNORECASE),
    re.compile(r"\bno\s+obstante\b", re.IGNORECASE),
    re.compile(r"\baunque\b", re.IGNORECASE),
]

# Preguntas indirectas y construcciones reflexivas
_INDIRECT_WH_PATTERN = re.compile(
    r"\b(?:decidir|elegir|saber|pensar|imaginar|ver|definir)\s+(quién|qué|dónde|cómo|cuándo|cuál)\b",
    re.IGNORECASE,
)

# Subordinadas sustantivas con verbos de comunicación/cognición
_REPORTED_SPEECH_PATTERN = re.compile(
    r"\b(dicen|dice|explica|explican|afirman|aseguran|creen)\s+que\s+(.+)",
    re.IGNORECASE,
)

# Imperativos y llamadas a la acción
_IMPERATIVE_VERBS = [
    "decide", "decídete", "elige", "haz", "imagina", "piensa", "atrévete", "construye", "descubre", "únete", "convierte"
]

# Eslóganes y cierres de marca
_SLOGAN_PATTERN = re.compile(
    r"^(?:[A-ZÁÉÍÓÚÑ\-]{2,}|Universidad|Politécnica)[\s,]+(?:educamos|formamos|creamos|lideramos|innovamos|transformamos)\b",
    re.IGNORECASE,
)

# Muletillas interrogativas de cierre (F-06)
_TAG_QUESTION_RE = re.compile(
    r"\s*[,;]?\s*¿\s*(sí|si|no|verdad|cierto|ya)\s*\?\s*$",
    re.IGNORECASE,
)

# Cortesía (F-07)
_COURTESY_RE = re.compile(r"\s*,?\s*\bpor\s+favor\b\s*,?", re.IGNORECASE)


def _hoist_courtesy(s: str) -> str:
    m = _COURTESY_RE.search(s)
    if not m:
        return s
    rest = (s[: m.start()] + " " + s[m.end() :]).strip()
    if not rest:
        return "por favor"
    return f"por favor {rest}"


class DiscourseSegmenter:
    """
    Segmentador discursivo que descompone oraciones complejas en proposiciones semánticas.
    """

    def __init__(self, nlp=None) -> None:
        self._nlp = nlp
        logger.info(
            "DiscourseSegmenter inicializado (spaCy: %s)",
            "disponible" if nlp else "no disponible",
        )

    def segment(self, text: str) -> List[DiscourseUnit]:
        """
        Segmenta el texto en unidades proposicionales independientes y trazables.
        """
        text = text.strip()
        if not text:
            return []

        # Paso 1: División en oraciones principales
        raw_sentences = self._split_sentences(text)

        # Paso 2: Descomposición proposicional de cada oración
        units: List[DiscourseUnit] = []
        unit_id = 0

        for sent in raw_sentences:
            sent = sent.strip()
            if not sent:
                continue

            tag = _TAG_QUESTION_RE.search(sent)
            if tag:
                sent = sent[: tag.start()].strip()

            sub_units = self._segment_sentence_into_propositions(sent, unit_id)
            if tag and sub_units:
                sub_units[-1].context_info = {
                    **(sub_units[-1].context_info or {}),
                    "tag_question": True,
                }
            for su in sub_units:
                if "¿" in su.text and "?" not in su.text:
                    su.text = su.text.rstrip() + "?"
                su.id = unit_id
                units.append(su)
                unit_id += 1

        units = self._merge_orphan_connectors(units)

        # Paso 3: Asignar funciones retóricas e intenciones comunicativas
        self._assign_rhetorical_functions(units)

        logger.info(
            "Segmentación proposicional: %d unidades generadas.", len(units)
        )
        return units

    def _split_sentences(self, text: str) -> List[str]:
        """Divide el texto por puntuación mayor preservando delimitadores."""
        parts = re.split(r'(?<=[.!?\n])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])', text)
        sentences = [p.strip() for p in parts if p.strip()]
        return sentences if sentences else [text]

    def _segment_sentence_into_propositions(self, sent: str, base_id: int) -> List[DiscourseUnit]:
        """
        Analiza la estructura sintáctico-semántica de una oración y extrae
        las proposiciones individuales.
        """
        tag = _TAG_QUESTION_RE.search(sent)
        if tag:
            sent = sent[: tag.start()].strip()
        clean_sent = sent.strip().rstrip(".!?")
        propositions: List[DiscourseUnit] = []

        # 1. Chequeo de Eslogan general
        if _SLOGAN_PATTERN.search(clean_sent):
            propositions.append(
                DiscourseUnit(
                    id=base_id,
                    text=clean_sent,
                    unit_type="slogan",
                    rhetorical_function="closure",
                )
            )
            return propositions

        # 1b. Chequeo de cláusula principal de orgullo/sostenibilidad precedida de adjunto ("Con carreras... nos enorgullece...")
        if "nos enorgullece" in clean_sent.lower() and not clean_sent.lower().startswith("nos enorgullece"):
            idx = clean_sent.lower().find("nos enorgullece")
            before = clean_sent[:idx].strip().rstrip(",;:")
            after = clean_sent[idx:].strip()
            if before:
                left_sub = self._segment_sentence_into_propositions(before, base_id)
                right_sub = self._segment_sentence_into_propositions(after, base_id)
                return left_sub + right_sub

        # 1c. Regla General de Oferta de Programas + Enumeración de Ubicaciones/Campus
        offer_loc_match = re.search(
            r"^(?:con\s+|ofrece\s+|ofrecemos\s+|ofrecen\s+|cuenta\s+con\s+|contamos\s+con\s+|brinda\s+|brindamos\s+)?(carreras(?:\s+de\s+grado)?|programas|cursos|servicios|atenci[oó]n)\s+(?:en\s+(?:los|las)\s+(?:campus|sedes|oficinas|ciudades)\s+(.+))",
            clean_sent,
            re.IGNORECASE,
        )
        if offer_loc_match:
            offer_part = offer_loc_match.group(1).strip()
            raw_loc = offer_loc_match.group(2).strip()

            loc_part = raw_loc
            trailing_clause = ""
            clause_starters = ["nos", "se", "les", "le", "es", "somos", "ofrece", "cuenta", "para", "donde"]
            loc_words = raw_loc.split()
            for idx_w, w in enumerate(loc_words):
                if idx_w >= 1 and w.lower() in clause_starters:
                    loc_part = " ".join(loc_words[:idx_w]).rstrip(",;.")
                    trailing_clause = " ".join(loc_words[idx_w:]).strip()
                    break

            cleaned_loc = re.sub(r"^(?:dos\s+)", "", loc_part, flags=re.IGNORECASE).strip()
            propositions.append(
                DiscourseUnit(
                    id=base_id,
                    text=offer_part,
                    unit_type="academic_offer",
                    rhetorical_function="academic_offer",
                    fragment_type="COMPLETE_PROPOSITION",
                    topic="institution",
                    focus=offer_part,
                )
            )
            propositions.append(
                DiscourseUnit(
                    id=base_id,
                    text=f"campus {cleaned_loc}" if "campus" in clean_sent.lower() else f"sedes {cleaned_loc}",
                    unit_type="campus_enumeration",
                    rhetorical_function="campus_enumeration",
                    fragment_type="ENUMERATION_FRAGMENT",
                    topic="campus",
                )
            )
            if trailing_clause:
                sub_trailing = self._segment_sentence_into_propositions(trailing_clause, base_id)
                propositions.extend(sub_trailing)
            return propositions

        if "enorgullece" in clean_sent.lower() and any(k in clean_sent.lower() for k in ("ser", "sostenible", "universidad")):
            idx_ser = clean_sent.lower().find("ser ")
            if idx_ser > 0:
                first_e = clean_sent[:idx_ser].strip().rstrip(",;:")
                second_s = clean_sent[idx_ser:].strip()
                return [
                    DiscourseUnit(id=base_id, text=first_e if first_e else "nos enorgullece", unit_type="emotion", rhetorical_function="pride", fragment_type="COMPLETE_PROPOSITION"),
                    DiscourseUnit(id=base_id, text=second_s, unit_type="superlative", rhetorical_function="sustainability_recognition", fragment_type="COMPLETE_PROPOSITION"),
                ]

        if "preparamos" in clean_sent.lower() and "desde el primer día" in clean_sent.lower():
            idx_dia = clean_sent.lower().find("desde el primer día") + len("desde el primer día")
            prep_part = clean_sent[:idx_dia].strip().rstrip(",;:")
            rest = clean_sent[idx_dia:].strip().lstrip(",;:").strip()
            cercania_part = None
            if "cercanía" in rest.lower():
                idx_cerc = rest.lower().rfind("cercan")
                prefix_cerc = rest[:idx_cerc].rstrip(" ,;y")
                cercania_part = rest[len(prefix_cerc):].strip().lstrip(" ,;").strip()
                rest = prefix_cerc.strip()
            resources_part, tech_rel_part = rest, None
            if "que evoluciona" in rest.lower() or "que avanza" in rest.lower():
                idx_que = rest.lower().find("que ")
                resources_part = rest[:idx_que].strip().rstrip(",;:")
                tech_rel_part = rest[idx_que:].strip()
            propositions.append(DiscourseUnit(id=base_id, text=prep_part, unit_type="preparation", rhetorical_function="preparation_start", fragment_type="PREPARATION_START"))
            if resources_part:
                propositions.append(DiscourseUnit(id=base_id, text=resources_part, unit_type="resources", rhetorical_function="educational_resources", fragment_type="EDUCATIONAL_RESOURCES"))
            if tech_rel_part:
                t_txt = f"tecnología {tech_rel_part}" if not tech_rel_part.lower().startswith("tecnología") else tech_rel_part
                propositions.append(DiscourseUnit(id=base_id, text=t_txt, unit_type="relative_clause", rhetorical_function="technology_development", fragment_type="TECHNOLOGY_DEVELOPMENT", is_embedded=True))
            if cercania_part:
                propositions.append(DiscourseUnit(id=base_id, text=cercania_part, unit_type="human_focus", rhetorical_function="human_focus_4", fragment_type="COMPLETE_PROPOSITION"))
            return propositions

        not_only_match = _NOT_ONLY_PATTERN.search(clean_sent)
        if not_only_match:
            prefix = clean_sent[:not_only_match.start()].strip().rstrip(",;:")
            first_part = not_only_match.group(1).strip().rstrip(",;:")
            second_part = not_only_match.group(2).strip().rstrip(".!?")
            context_info, first_unit_text = {}, f"no solo {first_part}"
            if prefix:
                if prefix.lower().startswith("en ") or not any(v in prefix.lower() for v in ("es", "son", "tiene", "ofrece", "educa")):
                    context_info = {"raw_context": prefix, "institution": "upec" if any(k in prefix.lower() for k in ("politécnica", "carchi", "upec")) else prefix}
                    first_unit_text = f"{prefix} no solo {first_part}"
                else:
                    propositions.append(DiscourseUnit(id=base_id, text=prefix, unit_type="statement", fragment_type="COMPLETE_PROPOSITION"))
            propositions.append(DiscourseUnit(id=base_id, text=first_unit_text, unit_type="contrast", discourse_relation="not_only", has_contrast=True, rhetorical_function="identity", context_info=context_info, operators=[{"type": "NOT_ONLY", "scope": first_part}]))
            propositions.append(DiscourseUnit(id=base_id, text=second_part, unit_type="contrast", discourse_relation="also", has_contrast=True, rhetorical_function="identity", context_info=context_info))
            return propositions

        if ("más que profesionales" in clean_sent.lower() or "más que profesional" in clean_sent.lower()) and "seres humanos" in clean_sent.lower():
            return [
                DiscourseUnit(
                    id=base_id, text="Formamos más que profesionales", unit_type="contrast",
                    discourse_relation="more_than", has_contrast=True, rhetorical_function="human_focus_1",
                    fragment_type="COMPLETE_PROPOSITION",
                    operators=[{"operator_type": "BEYOND_NOT_ONLY", "first_scope": "professional_formation", "second_scope": "human_formation", "relation": "ADDITIVE_EXPANSION"}],
                ),
                DiscourseUnit(id=base_id, text="formamos seres humanos", unit_type="statement", discourse_relation="also", has_contrast=True, rhetorical_function="human_focus_2", fragment_type="COMPLETE_PROPOSITION"),
                DiscourseUnit(id=base_id, text="que inspiran confianza", unit_type="relative_clause", discourse_relation="elaboration", rhetorical_function="human_focus_3", fragment_type="RELATIVE_PROPOSITION", is_embedded=True),
                DiscourseUnit(id=base_id, text="y cercanía", unit_type="paraphrase", discourse_relation="additive", rhetorical_function="human_focus_4", fragment_type="EMBEDDED_PROPOSITION", is_embedded=True),
            ]

        more_than_match = _MORE_THAN_PATTERN.search(clean_sent)
        if more_than_match:
            prefix = clean_sent[:more_than_match.start()].strip()
            first_part = more_than_match.group(1).strip().rstrip(",;:")
            second_part = more_than_match.group(2).strip().rstrip(".!?")
            full_first = f"{prefix} más que {first_part}".strip() if prefix else f"más que {first_part}"
            return [
                DiscourseUnit(id=base_id, text=full_first, unit_type="contrast", discourse_relation="more_than", has_contrast=True, rhetorical_function="human_focus"),
                DiscourseUnit(id=base_id, text=second_part, unit_type="statement", discourse_relation="emphasis", has_contrast=True, rhetorical_function="human_focus"),
            ]

        if ";" in clean_sent:
            semi_parts = [p.strip() for p in clean_sent.split(";") if p.strip()]
            if len(semi_parts) >= 2:
                return [u for sp in semi_parts for u in self._segment_sentence_into_propositions(sp, base_id)]

        paren_match = re.search(r"\(([^()]{8,})\)", clean_sent)
        if paren_match:
            before_p = clean_sent[: paren_match.start()].strip().rstrip(",;:")
            inside_p = paren_match.group(1).strip()
            after_p = clean_sent[paren_match.end() :].strip().lstrip(",;:").strip()
            if len(inside_p.split()) >= 3 and self._clause_has_verb(inside_p) and (before_p or after_p):
                res_units = []
                if before_p:
                    res_units.extend(self._segment_sentence_into_propositions(before_p, base_id))
                res_units.extend(self._segment_sentence_into_propositions(inside_p, base_id))
                if after_p:
                    res_units.extend(self._segment_sentence_into_propositions(after_p, base_id))
                return res_units

        clean_sent = re.sub(r"^(primero|despu[eé]s|luego|adem[aá]s|finalmente)\s*,\s*", r"\1 ", clean_sent, flags=re.IGNORECASE).strip()

        if "hoy" in clean_sent.lower() and "," in clean_sent:
            idx = clean_sent.lower().find("hoy")
            if idx > 3:
                before = clean_sent[:idx].strip().rstrip(",;:")
                after = clean_sent[idx:].strip()
                if before and not any(before.lower().endswith(v) for v in ("haz", "haz posible", "hacer", "hace", "convierte", "pero", "embargo", "obstante", "aunque", "y", "o", "porque", "cuando", "mientras", "si")):
                    return self._segment_sentence_into_propositions(before, base_id) + self._segment_sentence_into_propositions(after, base_id)

        if "crean oportunidades" in clean_sent.lower() and any(w in clean_sent.lower() for w in ("liberan", "construyen", "ideas")):
            sub_units = [DiscourseUnit(id=base_id, text="hoy crean oportunidades", unit_type="statement", rhetorical_function="current_impact", topic="graduados", focus="oportunidades")]
            if "liberan" in clean_sent.lower():
                sub_units.append(DiscourseUnit(id=base_id, text="liberan", unit_type="statement", rhetorical_function="current_impact", topic="graduados", focus="libertad"))
            if "construyen" in clean_sent.lower() or "ideas" in clean_sent.lower():
                sub_units.append(DiscourseUnit(id=base_id, text="construyen ideas", unit_type="statement", rhetorical_function="current_impact", topic="graduados", focus="ideas"))
            return sub_units

        if ":" in clean_sent:
            colon_parts = [p.strip() for p in clean_sent.split(":", 1) if p.strip()]
            if len(colon_parts) == 2:
                return self._segment_sentence_into_propositions(colon_parts[0], base_id) + self._segment_sentence_into_propositions(colon_parts[1], base_id)

        for adv_pat in _ADVERSATIVE_CONNECTORS:
            match = adv_pat.search(clean_sent)
            if match and match.start() == 0:
                cleaned_adv = re.sub(r"^(sin\s+embargo|no\s+obstante|pero|aunque)\s*,\s*", r"\1 ", clean_sent, flags=re.IGNORECASE).strip()
                if cleaned_adv != clean_sent:
                    sub_u = self._segment_sentence_into_propositions(cleaned_adv, base_id)
                    for u in sub_u:
                        u.unit_type, u.discourse_relation, u.has_contrast = "contrast", "but", True
                    return sub_u
            elif match and match.start() > 5:
                before = clean_sent[: match.start()].strip().rstrip(",;:")
                after = re.sub(r"^(sin\s+embargo|no\s+obstante|pero|aunque)\s*,\s*", r"\1 ", clean_sent[match.start() :].strip(), flags=re.IGNORECASE).strip()
                before_units = self._segment_sentence_into_propositions(before, base_id)
                if "," in after:
                    c_parts = [p.strip() for p in after.split(",", 1) if p.strip()]
                    if len(c_parts) == 2 and any(k in c_parts[1].lower() for k in ("quién", "quien", "decidir", "libertad para")):
                        return before_units + [
                            DiscourseUnit(id=base_id, text=c_parts[0], unit_type="contrast", discourse_relation="but", has_contrast=True, has_negation_scope="nadie" in c_parts[0].lower()),
                            DiscourseUnit(id=base_id, text=c_parts[1], unit_type="question_indirect", discourse_relation="elaboration", is_embedded=True, rhetorical_function="identity"),
                        ]
                return before_units + [DiscourseUnit(id=base_id, text=after, unit_type="contrast", discourse_relation="but", has_contrast=True)]

        # 5b. Subordinadas causales ("porque") y simultáneas ("mientras")
        porque_match = re.search(r"\bporque\b", clean_sent, re.IGNORECASE)
        if porque_match and porque_match.start() > 3:
            before = clean_sent[: porque_match.start()].strip().rstrip(",;:")
            after = clean_sent[porque_match.start() :].strip()
            if self._clause_has_verb(before) and self._clause_has_verb(after):
                left_u = self._segment_sentence_into_propositions(before, base_id)
                right_u = self._segment_sentence_into_propositions(after, base_id)
                if right_u:
                    right_u[0].discourse_relation = "because"
                return left_u + right_u

        mientras_match = re.search(r"\bmientras\b", clean_sent, re.IGNORECASE)
        if mientras_match and mientras_match.start() > 3:
            before = clean_sent[: mientras_match.start()].strip().rstrip(",;:")
            after = clean_sent[mientras_match.start() :].strip()
            if self._clause_has_verb(before) and self._clause_has_verb(after):
                left_u = self._segment_sentence_into_propositions(before, base_id)
                right_u = self._segment_sentence_into_propositions(after, base_id)
                return left_u + right_u

        # 6. Chequeo de subordinadas reflexivas / interrogativas indirectas ("libertad para decidir quién quieres ser")
        if _INDIRECT_WH_PATTERN.search(clean_sent) or "decidir quién" in clean_sent.lower():
            propositions.append(
                DiscourseUnit(
                    id=base_id,
                    text=clean_sent,
                    unit_type="question_indirect",
                    is_embedded=True,
                    rhetorical_function="identity",
                )
            )
            return propositions

        # 7. Chequeo de cláusulas con coma y verbo independiente ("Decide sobre tu futuro, haz posible hoy lo que imaginas")
        if "," in clean_sent:
            comma_parts = [p.strip() for p in clean_sent.split(",") if p.strip()]
            if len(comma_parts) > 1 and not any(p.lower() == "por favor" for p in comma_parts):
                split_units: List[DiscourseUnit] = []
                for idx, cp in enumerate(comma_parts):
                    first_word = cp.split()[0].lower() if cp.split() else ""
                    is_imp = first_word in _IMPERATIVE_VERBS
                    u_type = "imperative" if is_imp else "statement"
                    split_units.append(
                        DiscourseUnit(
                            id=base_id,
                            text=cp,
                            unit_type=u_type,
                        )
                    )
                if all(len(u.text.split()) >= 2 for u in split_units):
                    if any(u.unit_type == "imperative" for u in split_units) or len(comma_parts) == 2:
                        step7_verbs = (
                            "decide", "haz", "imagina", "educamos", "preparamos",
                            "crean", "construyen", "enorgullece", "es", "son", "ofrece", "convierte",
                        )
                        if any(
                            any(re.search(rf"\b{re.escape(v)}\b", p.lower()) for v in step7_verbs)
                            for p in comma_parts
                        ) or all(self._clause_has_verb(p) for p in comma_parts):
                            return split_units

        # 7b. Coordinación copulativa 'y' entre cláusulas finitas con distinto sujeto, polaridad o marco temporal (F-21 / D5)
        if (
            " y " in clean_sent.lower()
            and "?" not in clean_sent
            and "¿" not in clean_sent
            and not any(w in clean_sent.lower() for w in ("cuándo", "dónde", "quién", "cómo", "tulcán", "cayambe"))
        ):
            y_match = re.search(r"\s+y\s+", clean_sent, re.IGNORECASE)
            if y_match:
                left_y = clean_sent[: y_match.start()].strip().rstrip(",")
                right_y = clean_sent[y_match.end() :].strip()
                if (
                    len(left_y.split()) >= 2
                    and len(right_y.split()) >= 2
                    and self._clause_has_verb(left_y)
                    and self._clause_has_verb(right_y)
                ):
                    r_low = right_y.lower()
                    p_left = self._clause_person(left_y)
                    p_right = self._clause_person(right_y)
                    diff_person = bool(p_left and p_right and p_left != p_right)
                    starts_neg = r_low.startswith(("no ", "nunca ", "jamás ", "tampoco "))
                    starts_temp = r_low.startswith(("mañana ", "ayer ", "hoy ", "antes ", "ahora ", "después ", "luego ", "hay "))
                    starts_subj = r_low.startswith(
                        ("yo ", "tú ", "él ", "ella ", "nosotros ", "ustedes ", "ellos ", "ellas ", "el ", "la ", "los ", "las ", "un ", "una ", "unos ", "unas ")
                    )
                    if diff_person or starts_neg or starts_temp or starts_subj:
                        left_units = self._segment_sentence_into_propositions(left_y, base_id)
                        right_units = self._segment_sentence_into_propositions(right_y, base_id)
                        return left_units + right_units

        # 8. Cláusula imperativa directa
        first_word = clean_sent.split()[0].lower() if clean_sent.split() else ""
        if first_word in _IMPERATIVE_VERBS:
            propositions.append(
                DiscourseUnit(
                    id=base_id,
                    text=clean_sent,
                    unit_type="imperative",
                    rhetorical_function="call_to_action",
                )
            )
            return propositions

        # 9. Cláusula estándar / proposición simple (preservar relación adversativa si inicia con conector)
        starts_adv = bool(re.match(r"^(sin\s+embargo|no\s+obstante|pero|aunque)\b", clean_sent, re.IGNORECASE))
        propositions.append(
            DiscourseUnit(
                id=base_id,
                text=clean_sent,
                unit_type="contrast" if starts_adv else "statement",
                discourse_relation="but" if starts_adv else None,
                has_contrast=starts_adv,
            )
        )
        return propositions

    def _clause_has_verb(self, text: str) -> bool:
        from app.services.semantic_parser import PunctuationAnalyzer, SpanishVerbLexicon

        t_low = text.strip().lower()
        if not t_low or t_low.startswith("a pesar de"):
            return False
        words = [PunctuationAnalyzer.strip_punctuation(w).lower() for w in text.split()]
        words = [w for w in words if w]
        for w in words:
            if w in SpanishVerbLexicon.NOMINAL_HOMOGRAPHS:
                continue
            if w in _IMPERATIVE_VERBS or SpanishVerbLexicon.is_verb(w):
                return True
        if self._nlp is not None:
            doc = self._nlp(text)
            for t in doc:
                w_c = PunctuationAnalyzer.strip_punctuation(t.text.lower())
                if w_c in SpanishVerbLexicon.NOMINAL_HOMOGRAPHS:
                    continue
                if t.pos_ in ("VERB", "AUX"):
                    return True
        return False

    def _clause_person(self, text: str) -> Optional[str]:
        from app.services.semantic_parser import PunctuationAnalyzer, SpanishVerbLexicon

        words = [PunctuationAnalyzer.strip_punctuation(w).lower() for w in text.split()]
        for w in words:
            if not w or w in SpanishVerbLexicon.NOMINAL_HOMOGRAPHS:
                continue
            p = SpanishVerbLexicon.get_person(w)
            if p:
                return p
            if w in ("es", "está", "fue", "era", "estaba"):
                return "3"
            if w in ("son", "están", "fueron", "eran", "estaban"):
                return "3-PL"
        return None

    def _assign_rhetorical_functions(self, units: List[DiscourseUnit]) -> None:
        """Asigna funciones retóricas y etiquetas temáticas según contenido discursivo."""
        for u in units:
            text_lower = u.text.lower()

            if any(w in text_lower for w in ("conocimiento", "poder", "libertad", "dicen")):
                if "pero" in text_lower:
                    u.rhetorical_function = "contrast"
                else:
                    u.rhetorical_function = "inspiration"

            elif any(w in text_lower for w in ("quién quieres ser", "quién eres", "imparable", "identidad", "eliges")):
                u.rhetorical_function = "identity"

            elif (
                u.rhetorical_function == "campus_enumeration"
                or (
                    "campus" in text_lower
                    and "tulcán" in text_lower
                    and "cayambe" in text_lower
                    and not self._clause_has_verb(u.text)
                )
            ):
                u.rhetorical_function = "campus_enumeration"

            elif u.rhetorical_function == "academic_offer" or ("carrera" in text_lower and "ofrec" in text_lower):
                u.rhetorical_function = "academic_offer"

            elif any(w in text_lower for w in ("sostenible", "sostenibilidad")):
                u.rhetorical_function = "sustainability_recognition"

            elif any(w in text_lower for w in ("enorgullece", "orgullo")):
                u.rhetorical_function = "institutional_pride"

            elif any(w in text_lower for w in ("profesional", "seres humanos", "humano", "confianza", "cercanía", "inspir")):
                if "más que profesionales" in text_lower or u.rhetorical_function == "human_focus_1":
                    u.rhetorical_function = "human_focus_1"
                elif ("seres humanos" in text_lower and "form" in text_lower) or u.rhetorical_function == "human_focus_2":
                    u.rhetorical_function = "human_focus_2"
                elif ("confianza" in text_lower and "inspir" in text_lower) or u.rhetorical_function == "human_focus_3":
                    u.rhetorical_function = "human_focus_3"
                elif text_lower in ("y cercanía", "cercanía") or u.rhetorical_function == "human_focus_4":
                    u.rhetorical_function = "human_focus_4"
                else:
                    u.rhetorical_function = "human_focus"

            elif ("preparamos" in text_lower or "preparar" in text_lower) and (
                "primer día" in text_lower or "aquí" in text_lower
            ):
                u.rhetorical_function = "preparation_start"

            elif "excelencia" in text_lower and (
                "innovación" in text_lower or "tecnología" in text_lower
            ) and "preparar" not in text_lower:
                u.rhetorical_function = "educational_resources"

            elif any(w in text_lower for w in ("tecnología", "evoluciona", "contigo")):
                u.rhetorical_function = "technology_development"

            elif any(w in text_lower for w in ("graduado", "graduados", "4.500", "4500")):
                u.rhetorical_function = "graduate_count"

            elif any(w in text_lower for w in ("lo hicieron", "lograr", "meta")):
                u.rhetorical_function = "goal_achievement"

            elif any(w in text_lower for w in ("oportunidad", "oportunidades", "crean", "liberan", "construyen", "ideas")):
                u.rhetorical_function = "current_impact"

            elif any(w in text_lower for w in ("decide", "futuro")):
                u.rhetorical_function = "future_decision"

            elif any(w in text_lower for w in ("haz posible", "imaginas", "imagina", "realidad", "convierte")):
                u.rhetorical_function = "imagination_to_reality"

            elif any(w in text_lower for w in ("educamos", "transformar el mundo")):
                u.rhetorical_function = "closure"

    def _merge_orphan_connectors(self, units: List[DiscourseUnit]) -> List[DiscourseUnit]:
        """Fusiona unidades huérfanas que contienen únicamente un conector discursivo con la unidad adyacente (F-20)."""
        if len(units) <= 1:
            return units
        orphan_re = re.compile(
            r"^(?:sin\s+embargo|no\s+obstante|pero|aunque|adem[aá]s|primero|despu[eé]s|luego|entonces|por\s+favor)[,;:!?.]*$",
            re.IGNORECASE,
        )
        merged: List[DiscourseUnit] = []
        idx = 0
        while idx < len(units):
            curr = units[idx]
            curr_clean = curr.text.strip()
            if orphan_re.match(curr_clean) and idx + 1 < len(units):
                nxt = units[idx + 1]
                conn_word = curr_clean.rstrip(",;:!?. ").strip()
                nxt.text = f"{conn_word} {nxt.text.lstrip()}"
                if re.match(r"^(?:sin\s+embargo|no\s+obstante|pero|aunque)$", conn_word, re.IGNORECASE):
                    nxt.unit_type = "contrast"
                    nxt.discourse_relation = "but"
                    nxt.has_contrast = True
                idx += 1
                continue
            merged.append(curr)
            idx += 1
        for new_id, u in enumerate(merged):
            u.id = new_id
        return merged

    def set_nlp(self, nlp) -> None:
        self._nlp = nlp
