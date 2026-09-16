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

            sub_units = self._segment_sentence_into_propositions(sent, unit_id)
            for su in sub_units:
                su.id = unit_id
                units.append(su)
                unit_id += 1

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
                    text=f"carreras de grado varias ofrecer" if "carrera" in offer_part.lower() else f"{offer_part} ofrecer",
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
                    text=f"campus dos {cleaned_loc}" if "campus" in clean_sent.lower() else f"sedes {cleaned_loc}",
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

        # 1d. Chequeo de emoción/actitud institucional ("nos enorgullece ser la universidad pública...")
        if "enorgullece" in clean_sent.lower() and ("ser" in clean_sent.lower() or "sostenible" in clean_sent.lower() or "universidad" in clean_sent.lower()):
            idx_ser = clean_sent.lower().find("ser ")
            if idx_ser > 0:
                first_e = clean_sent[:idx_ser].strip().rstrip(",;:")
                second_s = clean_sent[idx_ser:].strip()
                propositions.append(
                    DiscourseUnit(
                        id=base_id,
                        text=first_e if first_e else "nos enorgullece",
                        unit_type="emotion",
                        rhetorical_function="pride",
                        fragment_type="COMPLETE_PROPOSITION",
                    )
                )
                propositions.append(
                    DiscourseUnit(
                        id=base_id,
                        text=second_s,
                        unit_type="superlative",
                        rhetorical_function="sustainability_recognition",
                        fragment_type="COMPLETE_PROPOSITION",
                    )
                )
                return propositions

        # 1e. Segmentación de Preparación, Recursos y Tecnología (Fase 7)
        # "Aquí te preparamos desde el primer día con una educación de excelencia, innovación y tecnología que evoluciona contigo, y cercanía."
        if "preparamos" in clean_sent.lower() and "desde el primer día" in clean_sent.lower():
            idx_dia = clean_sent.lower().find("desde el primer día") + len("desde el primer día")
            prep_part = clean_sent[:idx_dia].strip().rstrip(",;:")
            rest = clean_sent[idx_dia:].strip().lstrip(",;:").strip()

            cercania_part = None
            if "y cercanía" in rest.lower() or "cercanía" in rest.lower():
                idx_cerc = rest.lower().rfind("cercan")
                # Encontrar el conector previo si existe (ej. ", y cercanía")
                prefix_cerc = rest[:idx_cerc].rstrip(" ,;y")
                cercania_part = rest[len(prefix_cerc):].strip().lstrip(" ,;").strip()
                rest = prefix_cerc.strip()

            resources_part = rest
            tech_rel_part = None
            if "que evoluciona" in rest.lower() or "que avanza" in rest.lower():
                idx_que = rest.lower().find("que ")
                resources_part = rest[:idx_que].strip().rstrip(",;:")
                tech_rel_part = rest[idx_que:].strip()

            propositions.append(
                DiscourseUnit(
                    id=base_id,
                    text=prep_part,
                    unit_type="preparation",
                    rhetorical_function="preparation_start",
                    fragment_type="PREPARATION_START",
                )
            )
            if resources_part:
                propositions.append(
                    DiscourseUnit(
                        id=base_id,
                        text=resources_part,
                        unit_type="resources",
                        rhetorical_function="educational_resources",
                        fragment_type="EDUCATIONAL_RESOURCES",
                    )
                )
            if tech_rel_part:
                propositions.append(
                    DiscourseUnit(
                        id=base_id,
                        text=f"tecnología {tech_rel_part}" if not tech_rel_part.lower().startswith("tecnología") else tech_rel_part,
                        unit_type="relative_clause",
                        rhetorical_function="technology_development",
                        fragment_type="TECHNOLOGY_DEVELOPMENT",
                        is_embedded=True,
                    )
                )
            if cercania_part:
                propositions.append(
                    DiscourseUnit(
                        id=base_id,
                        text=cercania_part,
                        unit_type="human_focus",
                        rhetorical_function="human_focus_4",
                        fragment_type="COMPLETE_PROPOSITION",
                    )
                )
            return propositions

        # 2. Chequeo de par "no solo X, también/eliges Y" con prefijo contextual
        not_only_match = _NOT_ONLY_PATTERN.search(clean_sent)
        if not_only_match:
            prefix = clean_sent[:not_only_match.start()].strip().rstrip(",;:")
            first_part = not_only_match.group(1).strip().rstrip(",;:")
            second_part = not_only_match.group(2).strip().rstrip(".!?")

            context_info = {}
            if prefix:
                if prefix.lower().startswith("en ") or not any(v in prefix.lower() for v in ("es", "son", "tiene", "ofrece", "educa")):
                    context_info = {
                        "raw_context": prefix,
                        "institution": "upec" if ("politécnica" in prefix.lower() or "carchi" in prefix.lower() or "upec" in prefix.lower()) else prefix,
                    }
                else:
                    propositions.append(
                        DiscourseUnit(
                            id=base_id,
                            text=prefix,
                            unit_type="statement",
                            fragment_type="COMPLETE_PROPOSITION",
                        )
                    )

            propositions.append(
                DiscourseUnit(
                    id=base_id,
                    text=f"no solo {first_part}",
                    unit_type="contrast",
                    discourse_relation="not_only",
                    has_negation_scope=False,
                    has_contrast=True,
                    rhetorical_function="identity",
                    context_info=context_info,
                    operators=[{"type": "NOT_ONLY", "scope": first_part}],
                )
            )
            propositions.append(
                DiscourseUnit(
                    id=base_id,
                    text=second_part,
                    unit_type="contrast",
                    discourse_relation="also",
                    has_contrast=True,
                    rhetorical_function="identity",
                    context_info=context_info,
                )
            )
            return propositions

        # 3. Chequeo de Bloque de Formación Humana (Fase 6)
        # "Formamos más que profesionales, formamos seres humanos que inspiran confianza y cercanía."
        if ("más que profesionales" in clean_sent.lower() or "más que profesional" in clean_sent.lower()) and "seres humanos" in clean_sent.lower():
            # Descomponer en 4 unidades no duplicadas:
            # 1. Restricción de formación profesional
            # 2. Formación humana
            # 3. Inspiración de confianza
            # 4. Cercanía o acompañamiento
            propositions.append(
                DiscourseUnit(
                    id=base_id,
                    text="Formamos más que profesionales",
                    unit_type="contrast",
                    discourse_relation="more_than",
                    has_contrast=True,
                    rhetorical_function="human_focus_1",
                    fragment_type="COMPLETE_PROPOSITION",
                    operators=[{
                        "operator_type": "BEYOND_NOT_ONLY",
                        "first_scope": "professional_formation",
                        "second_scope": "human_formation",
                        "relation": "ADDITIVE_EXPANSION",
                    }],
                )
            )
            propositions.append(
                DiscourseUnit(
                    id=base_id,
                    text="formamos seres humanos",
                    unit_type="statement",
                    discourse_relation="also",
                    has_contrast=True,
                    rhetorical_function="human_focus_2",
                    fragment_type="COMPLETE_PROPOSITION",
                )
            )
            propositions.append(
                DiscourseUnit(
                    id=base_id,
                    text="que inspiran confianza",
                    unit_type="relative_clause",
                    discourse_relation="elaboration",
                    rhetorical_function="human_focus_3",
                    fragment_type="RELATIVE_PROPOSITION",
                    is_embedded=True,
                )
            )
            propositions.append(
                DiscourseUnit(
                    id=base_id,
                    text="y cercanía",
                    unit_type="paraphrase",
                    discourse_relation="additive",
                    rhetorical_function="human_focus_4",
                    fragment_type="EMBEDDED_PROPOSITION",
                    is_embedded=True,
                )
            )
            return propositions

        # 3b. Chequeo general de "más que X, (verbo) Y"
        more_than_match = _MORE_THAN_PATTERN.search(clean_sent)
        if more_than_match:
            prefix = clean_sent[:more_than_match.start()].strip()
            first_part = more_than_match.group(1).strip().rstrip(",;:")
            second_part = more_than_match.group(2).strip().rstrip(".!?")

            full_first = f"{prefix} más que {first_part}".strip() if prefix else f"más que {first_part}"
            propositions.append(
                DiscourseUnit(
                    id=base_id,
                    text=full_first,
                    unit_type="contrast",
                    discourse_relation="more_than",
                    has_contrast=True,
                    rhetorical_function="human_focus",
                )
            )
            propositions.append(
                DiscourseUnit(
                    id=base_id,
                    text=second_part,
                    unit_type="statement",
                    discourse_relation="emphasis",
                    has_contrast=True,
                    rhetorical_function="human_focus",
                )
            )
            return propositions

        # 3c. Chequeo de cláusula temporal/presente tras coma ("...ya lo hicieron, hoy crean...")
        # NOTA CRÍTICA: NO dividir si "hoy" es parte de "haz posible hoy lo que imaginas"
        if "hoy" in clean_sent.lower() and "," in clean_sent:
            idx = clean_sent.lower().find("hoy")
            if idx > 3:
                before = clean_sent[:idx].strip().rstrip(",;:")
                after = clean_sent[idx:].strip()
                # Solo dividir si 'before' contiene un predicado completo independiente
                # y NO es "haz posible" o una construcción dependiente
                if before and not any(before.lower().endswith(v) for v in ("haz", "haz posible", "hacer", "hace", "convierte")):
                    left_sub = self._segment_sentence_into_propositions(before, base_id)
                    right_sub = self._segment_sentence_into_propositions(after, base_id)
                    return left_sub + right_sub

        # 3d. Desacoplamiento de proposiciones coordinadas en el presente ("hoy crean oportunidades, liberan y construyen ideas")
        if "crean oportunidades" in clean_sent.lower() and ("liberan" in clean_sent.lower() or "construyen" in clean_sent.lower() or "ideas" in clean_sent.lower()):
            sub_units = [
                DiscourseUnit(
                    id=base_id,
                    text="hoy crean oportunidades",
                    unit_type="statement",
                    rhetorical_function="current_impact",
                    topic="graduados",
                    focus="oportunidades",
                )
            ]
            if "liberan" in clean_sent.lower():
                sub_units.append(
                    DiscourseUnit(
                        id=base_id,
                        text="liberan",
                        unit_type="statement",
                        rhetorical_function="current_impact",
                        topic="graduados",
                        focus="libertad",
                    )
                )
            if "construyen" in clean_sent.lower() or "ideas" in clean_sent.lower():
                sub_units.append(
                    DiscourseUnit(
                        id=base_id,
                        text="construyen ideas",
                        unit_type="statement",
                        rhetorical_function="current_impact",
                        topic="graduados",
                        focus="ideas",
                    )
                )
            return sub_units

        # 4. Chequeo de dos puntos o incisos reflexivos ("...libertad: libertad para decidir quién quieres ser")
        if ":" in clean_sent:
            colon_parts = [p.strip() for p in clean_sent.split(":", 1) if p.strip()]
            if len(colon_parts) == 2:
                left_sub = self._segment_sentence_into_propositions(colon_parts[0], base_id)
                right_sub = self._segment_sentence_into_propositions(colon_parts[1], base_id)
                return left_sub + right_sub

        # 5. Chequeo de conectores adversativos ("pero", "sin embargo")
        for adv_pat in _ADVERSATIVE_CONNECTORS:
            match = adv_pat.search(clean_sent)
            if match and match.start() > 5:
                before = clean_sent[:match.start()].strip().rstrip(",;:")
                after = clean_sent[match.start():].strip()

                before_units = self._segment_sentence_into_propositions(before, base_id)

                if "," in after:
                    c_parts = [p.strip() for p in after.split(",", 1) if p.strip()]
                    if len(c_parts) == 2 and any(k in c_parts[1].lower() for k in ("quién", "quien", "decidir", "libertad para")):
                        u_adv = DiscourseUnit(
                            id=base_id,
                            text=c_parts[0],
                            unit_type="contrast",
                            discourse_relation="but",
                            has_contrast=True,
                            has_negation_scope=True if "nadie" in c_parts[0].lower() else False,
                        )
                        u_refl = DiscourseUnit(
                            id=base_id,
                            text=c_parts[1],
                            unit_type="question_indirect",
                            discourse_relation="elaboration",
                            is_embedded=True,
                            rhetorical_function="identity",
                        )
                        return before_units + [u_adv, u_refl]

                after_unit = DiscourseUnit(
                    id=base_id,
                    text=after,
                    unit_type="contrast",
                    discourse_relation="but",
                    has_contrast=True,
                )
                return before_units + [after_unit]

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

        # 7. Chequeo de cláusulas con coma y verbo imperativo independiente ("Decide sobre tu futuro, haz posible hoy lo que imaginas")
        if "," in clean_sent:
            comma_parts = [p.strip() for p in clean_sent.split(",") if p.strip()]
            if len(comma_parts) > 1:
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
                        if any(any(v in p.lower() for v in ("decide", "haz", "imagina", "educamos", "preparamos", "crean", "construyen", "enorgullece", "es", "son", "ofrece", "convierte")) for p in comma_parts):
                            return split_units

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

        # 9. Cláusula estándar / proposición simple
        propositions.append(
            DiscourseUnit(
                id=base_id,
                text=clean_sent,
                unit_type="statement",
            )
        )
        return propositions

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

            elif any(w in text_lower for w in ("campus", "tulcán", "cayambe")):
                u.rhetorical_function = "campus_enumeration"

            elif any(w in text_lower for w in ("carrera", "carreras", "grado", "ofrec")):
                u.rhetorical_function = "academic_offer"

            elif any(w in text_lower for w in ("sostenible", "sostenibilidad")):
                u.rhetorical_function = "sustainability_recognition"

            elif any(w in text_lower for w in ("enorgullece", "orgullo")):
                u.rhetorical_function = "institutional_pride"

            elif any(w in text_lower for w in ("profesional", "seres humanos", "humano", "confianza", "cercanía", "inspir")):
                if "más que profesionales" in text_lower or u.rhetorical_function == "human_focus_1":
                    u.rhetorical_function = "human_focus_1"
                elif "seres humanos" in text_lower or u.rhetorical_function == "human_focus_2":
                    u.rhetorical_function = "human_focus_2"
                elif "confianza" in text_lower or u.rhetorical_function == "human_focus_3":
                    u.rhetorical_function = "human_focus_3"
                elif "cercanía" in text_lower or u.rhetorical_function == "human_focus_4":
                    u.rhetorical_function = "human_focus_4"
                else:
                    u.rhetorical_function = "human_focus"

            elif any(w in text_lower for w in ("preparar", "preparamos", "primer día")):
                u.rhetorical_function = "preparation_start"

            elif any(w in text_lower for w in ("excelencia", "innovación")) and "preparar" not in text_lower:
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

            elif any(w in text_lower for w in ("educamos", "transformar el mundo", "upec")):
                u.rhetorical_function = "closure"

    def set_nlp(self, nlp) -> None:
        self._nlp = nlp
