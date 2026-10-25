"""
Analizador lingüístico avanzado para español orientado a LSEC.

Mejora la extracción de información semántica con spaCy mediante:
  1. Detección mejorada de pro-drop (sujeto tácito) con resolución por persona.
  2. Detección de negación con alcance (clausal vs. constituyente).
  3. Detección de correferencia pronominal básica.
  4. Extracción de temporalidad y aspecto desde la morfología verbal.
  5. Detección de clasificadores semánticos LSEC.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Mapeo de persona gramatical a deixis pronominal LSEC ──────

_PERSON_TO_PRODROP: Dict[str, str] = {
    "1": "PRO1",        # yo
    "2": "PRO2",        # tú/usted
    "3": "PRO3",        # él/ella
    "1-PL": "PRO1-PL",  # nosotros
    "2-PL": "PRO2-PL",  # ustedes
    "3-PL": "ELLOS",    # ellos/ellas
}


# ── Tiempos verbales LSEC ────────────────────────────────────

_TENSE_MARKERS: Dict[str, str] = {
    "past": "ANTES",      # Marcador temporal pasado
    "present": None,      # No se marca explícitamente
    "future": "FUTURO",   # Marcador temporal futuro
}

_ASPECT_MARKERS: Dict[str, Tuple[str, str]] = {
    "progressive": ("AHORA", "after"),     # estar+gerundio → AHORA después
    "perfect": ("YA", "after"),            # haber+participio → YA después
    "prospective": ("FUTURO", "before"),   # ir+a+infinitivo → FUTURO antes
    "habitual": ("SIEMPRE", "before"),     # soler+infinitivo → SIEMPRE antes
}


# ── Clasificadores semánticos LSEC ───────────────────────────

_SEMANTIC_CLASSIFIERS: Dict[str, str] = {
    # Clasificadores de forma/tamaño
    "persona": "CL_PERSONA",
    "animal": "CL_ANIMAL",
    "vehículo": "CL_VEHICULO",
    "edificio": "CL_SUPERFICIE_PLANA",
    "libro": "CL_OBJETO_PLANO",
    "botella": "CL_CILINDRICO",
    "pelota": "CL_ESFERA",
    "mesa": "CL_SUPERFICIE_PLANA",
    "puerta": "CL_SUPERFICIE_PLANA",
}


@dataclass
class NegationInfo:
    """Información de negación con alcance."""
    negation_type: str  # "clausal", "constituent", "existential", "emphatic"
    negation_word: str  # "no", "nunca", "nadie", "nada", "tampoco"
    scope_start_token: int = 0
    scope_end_token: int = 0
    affects_predicate: bool = True


@dataclass
class ProDropResolution:
    """Resultado de la resolución tipificada de un sujeto tácito."""
    person: str          # "1", "2", "3", "1-PL", "2-PL", "3-PL"
    category: str        # "pro1", "pro2", "anaphoric", "locus", "generic", "impersonal", "ambiguous"
    deixis_gloss: Optional[str] = None  # "PRO1", "PRO2", etc. (None para impersonal/genérico)
    requires_deixis: bool = True
    locus: Optional[str] = None
    source: str = "morphological"  # "morphological", "contextual", "discourse"
    confidence: float = 0.75
    requires_review: bool = False


@dataclass
class TemporalInfo:
    """Información temporal y aspectual separada."""
    tense: Optional[str] = None            # "past", "present", "future"
    aspect: Optional[str] = None           # "progressive", "perfect", "prospective", "habitual"
    temporal_marker_gloss: Optional[str] = None
    aspect_marker_gloss: Optional[str] = None
    marker_position: Optional[str] = None  # "before", "after"
    source_word: Optional[str] = None
    is_past_anchored: bool = False


@dataclass
class ClassifierCandidate:
    """Candidato a clasificador LSEC con requisito de respaldo o revisión humana."""
    token_idx: int
    referent_lemma: str
    token_text: str
    classifier_type: str  # ej: "CL_VEHICULO", "CL_PERSONA"
    status: str = "CLASSIFIER_CANDIDATE"
    has_lexical_support: bool = False
    requires_review: bool = True
    confidence: float = 0.60


@dataclass
class FunctionalTransfer:
    """Transferencia funcional de determinantes y preposiciones del español."""
    token_idx: int
    source_word: str
    lemma: str
    pos: str
    function_type: str   # definiteness, deixis, possession, origin, destination, location, instrument, beneficiary, purpose, time, structural_omission
    target_action: str   # e.g. "quantifier_one", "plural_quantifier", "deictic_demonstrative", "possessive_index", "source_locus", "direction_goal", "spatial_locus", "instrument_classifier", "beneficiary_marker", "purpose_marker", "temporal_operator", "omit_structural"
    target_gloss: Optional[str] = None
    locus_assignment: Optional[str] = None
    requires_review: bool = False
    justification: str = ""


@dataclass
class CoreferenceLink:
    """Enlace de correferencia pronominal."""
    pronoun: str
    pronoun_token_idx: int
    antecedent_type: str  # "institutional", "discourse", "anaphoric", "cataphoric"
    resolved_entity: Optional[str] = None
    resolved_gloss: Optional[str] = None
    confidence: float = 0.70


class EnhancedLinguisticAnalyzer:
    """
    Analiza fenómenos lingüísticos avanzados con spaCy para producir
    información que alimenta el ``SemanticFrame``.

    No reemplaza al ``SemanticParser``; lo complementa con análisis
    más fino de pro-drop, negación, correferencia y temporalidad.
    """

    def __init__(self, nlp=None) -> None:
        self._nlp = nlp
        self._negation_words: Set[str] = {"no", "nunca", "jamás", "nadie", "nada", "tampoco", "ninguno", "ningún"}
        self._existential_negation: Set[str] = {"nadie", "nada", "ninguno", "ningún"}
        self._emphatic_negation: Set[str] = {"jamás", "nunca"}

    # ── Pro-drop tipificado ───────────────────────────────────

    def detect_prodrop(self, doc) -> Optional[ProDropResolution]:
        """
        Detecta y tipifica el sujeto tácito (pro-drop) a partir de la morfología verbal
        y el contexto sintáctico.

        Distingue rigurosamente:
          - PRO1 / PRO1-PL: 1ra persona (deixis a sí mismo / grupo propio).
          - PRO2 / PRO2-PL: 2da persona (deixis al interlocutor).
          - ANAPHORIC: 3ra persona con referente anafórico en el contexto previo.
          - LOCUS: referente asociado a una entidad espacial ya establecida.
          - GENERIC: sujeto genérico impersonal ("uno", segunda persona no deíctica).
          - IMPERSONAL: verbos de clima, existenciales o construcciones impersonales (sin deixis).
          - AMBIGUOUS: 3ra persona sin antecedente claro (requiere revisión humana, no genera deixis ciega).
        """
        if doc is None:
            return None

        # 1. Detección de oraciones impersonales con 'se'
        has_se_impersonal = any(
            t.text.lower() == "se" and t.dep_ in ("expl", "expl:pass", "expl:pv")
            for t in doc
        )

        for token in doc:
            if token.pos_ not in ("VERB", "AUX"):
                continue
            if token.dep_ in ("aux", "auxpass", "cop"):
                continue

            # Verificar si tiene sujeto explícito
            has_explicit_subject = any(
                child.dep_ in ("nsubj", "nsubj:pass")
                for child in token.children
            )
            if has_explicit_subject:
                continue

            has_pronoun_subject = any(
                t.dep_ in ("nsubj", "nsubj:pass") and t.pos_ == "PRON"
                for t in doc
            )
            if has_pronoun_subject:
                continue

            lemma_lower = token.lemma_.lower()

            # Verbos estrictamente impersonales (clima, existencial)
            weather_verbs = {"llover", "nevar", "granizar", "tronar", "relampaguear", "amanecer", "anochecer"}
            if lemma_lower in weather_verbs or (lemma_lower == "haber" and token.dep_ == "ROOT"):
                return ProDropResolution(person="3", category="impersonal", deixis_gloss=None, requires_deixis=False, source="lexical_impersonal", confidence=0.95, requires_review=False)

            if has_se_impersonal:
                return ProDropResolution(person="3", category="generic", deixis_gloss=None, requires_deixis=False, source="impersonal_se", confidence=0.85, requires_review=False)

            # Extraer persona y número desde morfología
            person_morph = token.morph.get("Person", [])
            number_morph = token.morph.get("Number", [])
            if not person_morph:
                continue

            person = person_morph[0]
            is_plural = "Plur" in number_morph
            person_key = f"{person}-PL" if is_plural else person

            if person == "1":
                return ProDropResolution(person=person_key, category="pro1", deixis_gloss="PRO1-PL" if is_plural else "PRO1", requires_deixis=True, source="morphological", confidence=0.90, requires_review=False)
            elif person == "2":
                return ProDropResolution(person=person_key, category="pro2", deixis_gloss="PRO2-PL" if is_plural else "PRO2", requires_deixis=True, source="morphological", confidence=0.85, requires_review=False)
            elif person == "3":
                # En 3ra persona: no asumir deixis ciega
                return ProDropResolution(person=person_key, category="ambiguous", deixis_gloss=None, requires_deixis=False, source="morphological_unanchored_3p", confidence=0.45, requires_review=True)

        return None

    # ── Negación ──────────────────────────────────────────────

    def detect_negation(self, doc) -> Optional[NegationInfo]:
        """
        Detecta negación y determina su alcance (clausal vs. constituyente).

        En LSEC, la negación clausal se expresa con movimiento de cabeza
        sobre toda la cláusula, mientras que la negación constituyente
        afecta solo a un participante específico.
        """
        if doc is None:
            return None

        for token in doc:
            text_lower = token.text.lower()
            if text_lower not in self._negation_words:
                continue

            # Determinar tipo de negación
            if text_lower in self._existential_negation:
                neg_type = "existential"
            elif text_lower in self._emphatic_negation:
                neg_type = "emphatic"
            elif token.dep_ in ("neg", "advmod") and token.head.pos_ in ("VERB", "AUX"):
                neg_type = "clausal"
            else:
                neg_type = "constituent"

            # Determinar alcance
            if neg_type == "clausal":
                scope_start = min(t.i for t in doc)
                scope_end = max(t.i for t in doc)
            elif neg_type == "existential":
                scope_start = token.i
                scope_end = max(t.i for t in doc)
            else:
                scope_start = token.i
                scope_end = min(token.i + 3, len(doc) - 1)

            return NegationInfo(
                negation_type=neg_type,
                negation_word=text_lower,
                scope_start_token=scope_start,
                scope_end_token=scope_end,
                affects_predicate=neg_type in ("clausal", "emphatic"),
            )

        return None

    # ── Temporalidad y aspecto separados ───────────────────────

    def extract_temporal_info(self, doc) -> TemporalInfo:
        """
        Extrae información temporal y aspectual desde la morfología verbal y adverbios.

        SEPARA RIGUROSAMENTE referencia temporal (pasado/presente/futuro)
        del aspecto gramatical (progresivo/perfectivo/habitual/prospectivo):
          - NO convierte progresivo en AHORA si hay anclaje pasado o futuro.
          - NO convierte perfectivo en YA si es mero pretérito sin completitud enfatizada.
        """
        info = TemporalInfo()

        if doc is None:
            return info

        past_words = {"ayer", "anoche", "antes", "pasado", "año_pasado", "mes_pasado", "hace"}
        has_lexical_past = any(t.text.lower() in past_words for t in doc)

        # Buscar marcadores temporales léxicos explícitos primero
        time_words = {
            "hoy": ("present", "HOY"),
            "ayer": ("past", "AYER"),
            "mañana": ("future", "MAÑANA"),
            "ahora": ("present", "AHORA"),
            "antes": ("past", "ANTES"),
            "después": ("future", "DESPUÉS"),
            "siempre": (None, "SIEMPRE"),
        }
        for token in doc:
            t_lower = token.text.lower()
            if t_lower in time_words:
                tense_val, gloss = time_words[t_lower]
                if tense_val:
                    info.tense = tense_val
                    if tense_val == "past":
                        info.is_past_anchored = True
                info.temporal_marker_gloss = gloss
                info.marker_position = "before"
                info.source_word = t_lower
                break

        nominal_homographs = {"dibujo", "música", "danza", "cine", "teatro", "pintura", "arte", "artes", "taller", "club", "correo", "whatsapp", "parte", "grado"}
        for token in doc:
            if token.pos_ not in ("VERB", "AUX"):
                continue
            if token.dep_ in ("aux", "auxpass"):
                continue
            if token.text.lower() in nominal_homographs:
                continue
            if any(c.dep_ in ("amod", "det", "compound") for c in token.children) or (
                token.dep_ == "conj" and token.head.pos_ in ("NOUN", "PROPN")
            ):
                continue

            # Extraer tiempo desde morfología
            tense_morph = token.morph.get("Tense", [])
            aspect_morph = token.morph.get("Aspect", [])
            verb_form = token.morph.get("VerbForm", [])

            if "Past" in tense_morph or has_lexical_past:
                info.tense = "past"
                info.is_past_anchored = True
                if not info.temporal_marker_gloss:
                    info.temporal_marker_gloss = "ANTES"
                    info.marker_position = "before"
            elif "Fut" in tense_morph:
                if not info.tense:
                    info.tense = "future"
                if not info.temporal_marker_gloss:
                    info.temporal_marker_gloss = "FUTURO"
                    info.marker_position = "before"
            elif "Pres" in tense_morph:
                if not info.tense:
                    info.tense = "present"

            # Aspecto gramatical independiente del tiempo
            if "Ger" in verb_form or "Prog" in aspect_morph:
                info.aspect = "progressive"
                # Solo realizar AHORA si la referencia temporal es presente o neutra
                if not info.is_past_anchored and info.tense != "future":
                    info.aspect_marker_gloss = "AHORA"
            elif "Part" in verb_form or "Perf" in aspect_morph:
                info.aspect = "perfect"
                if not info.is_past_anchored:
                    info.aspect_marker_gloss = "YA"
            elif "Imp" in aspect_morph:
                info.aspect = "habitual"

            break  # Solo analizar el primer verbo principal

        return info

    # ── Transferencia funcional de determinantes y preposiciones ───

    def analyze_functional_transfer(self, doc) -> List[FunctionalTransfer]:
        """
        Analiza determinantes y preposiciones antes de omitir una forma española.

        En lugar de descartar indiscriminadamente DET y ADP, evalúa:
          - Definitud y número (un/una -> UNO; unos/unas -> VARIOS).
          - Deixis demostrativa (este/ese/aquel -> ESTO/ESO/AQUEL).
          - Posesión (mi/tu/su/de -> PRO1/PRO2/PRO3/índice posesivo).
          - Origen (de/desde -> DESDE / locus fuente).
          - Destino (a/hacia/para -> HACIA / concordancia direccional).
          - Ubicación (en/sobre/bajo -> locus espacial / clasificador topológico).
          - Instrumento (con -> clasificador instrumental).
          - Beneficiario (para -> asignación de locus beneficiario).
          - Finalidad (para / a fin de -> PROPÓSITO / OBJETIVO).
          - Tiempo (en / a las -> operador temporal).
          - Omisión justificada: marcas puramente estructurales del español.
        """
        transfers: List[FunctionalTransfer] = []
        if doc is None:
            return transfers

        for token in doc:
            pos = token.pos_
            text_l = token.text.lower()
            lemma_l = token.lemma_.lower()

            if pos not in ("DET", "ADP", "PRON"):
                continue

            # 1. Deixis demostrativa
            if text_l in ("este", "esta", "estos", "estas", "esto"):
                transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="deixis", target_action="deictic_demonstrative", target_gloss="ESTO", justification="Demostrativo proximal transferido a deixis espacial"))
            elif text_l in ("ese", "esa", "esos", "esas", "eso"):
                transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="deixis", target_action="deictic_demonstrative", target_gloss="ESO", justification="Demostrativo medial transferido a deixis espacial"))
            elif text_l in ("aquel", "aquella", "aquellos", "aquellas", "aquello"):
                transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="deixis", target_action="deictic_demonstrative", target_gloss="AQUEL", justification="Demostrativo distal transferido a deixis espacial"))

            # 2. Posesión
            elif text_l in ("mi", "mis"):
                transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="possession", target_action="possessive_index", target_gloss="PRO1", justification="Posesivo de 1ra persona transferido a deixis PRO1"))
            elif text_l in ("nuestro", "nuestra", "nuestros", "nuestras"):
                transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="possession", target_action="possessive_index", target_gloss="PRO1-PL", justification="Posesivo de 1ra persona plural transferido a deixis PRO1-PL"))
            elif text_l in ("tu", "tus"):
                transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="possession", target_action="possessive_index", target_gloss="PRO2", justification="Posesivo de 2da persona transferido a deixis PRO2"))
            elif text_l in ("su", "sus"):
                transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="possession", target_action="possessive_index", target_gloss="PRO3", requires_review=True, justification="Posesivo de 3ra persona transferido a índice anafórico"))

            # 3. Definitud indefinida numeral vs. plural
            elif text_l in ("un", "una") and pos == "DET":
                # Si modifica sustantivo singular contable específico
                transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="definiteness", target_action="omit_structural", justification="Artículo indefinido no numeral omitido en LSEC"))
            elif text_l in ("unos", "unas") and pos == "DET":
                transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="definiteness", target_action="plural_quantifier", target_gloss="VARIOS", justification="Indefinido plural transferido a cuantificador VARIOS"))

            # 4. Preposiciones funcionales
            elif pos == "ADP":
                head_tok = token.head
                dep = token.dep_

                if text_l == "desde":
                    transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="origin", target_action="source_locus", target_gloss="DESDE", justification="Preposición de origen espacial o temporal transferida a seña DESDE"))
                elif text_l == "de":
                    if head_tok.text.lower() in ("ayer", "hoy", "mañana", "temprano"):
                        transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="time", target_action="temporal_operator", target_gloss="DESDE", justification="Preposición temporal de inicio de intervalo"))
                    elif (
                        head_tok.pos_ in ("PROPN", "NOUN")
                        and head_tok.dep_ == "obl"
                        and head_tok.head.lemma_.lower() in ("venir", "salir", "partir", "regresar", "volver", "llegar")
                    ):
                        transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="origin", target_action="source_locus", target_gloss="DESDE", justification="Preposición de procedencia espacial transferida a locus de origen"))
                    elif dep in ("case", "nmod") and head_tok.pos_ in ("NOUN", "PROPN"):
                        transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="possession", target_action="possessive_relation", justification="Preposición 'de' genitiva/posesiva transferida a adyacencia de poseedor"))
                    else:
                        transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="structural_omission", target_action="omit_structural", justification="Preposición 'de' puramente conectiva omitida en LSEC"))

                elif text_l in ("a", "al", "hacia"):
                    next_tok = doc[token.i + 1] if token.i + 1 < len(doc) else None
                    next_is_inf = next_tok is not None and (
                        "Inf" in next_tok.morph.get("VerbForm", [])
                        or next_tok.text.lower().endswith(("ar", "er", "ir", "arse", "erse", "irse", "arte", "erte", "irte"))
                    )
                    head_is_inf = head_tok.pos_ in ("VERB", "AUX") and (
                        "Inf" in head_tok.morph.get("VerbForm", [])
                        or head_tok.text.lower().endswith(("ar", "er", "ir", "arse", "erse", "irse", "arte", "erte", "irte"))
                    )
                    non_locative_targets = {
                        "whatsapp", "correo", "teléfono", "telefono", "celular",
                        "número", "numero", "contacto", "parte", "través", "traves",
                        "todos", "todas", "todo", "toda", "varios", "varias", "nadie", "alguien", "quien", "quién",
                        "paciente", "pacientes", "director", "directora", "profesor", "profesora",
                        "estudiante", "estudiantes", "médico", "medico", "doctor", "doctora",
                        "niño", "niña", "niños", "niñas", "hermano", "hermana", "amigo", "amiga",
                        "mamá", "papá", "familia", "persona", "personas", "gente", "cliente", "clientes",
                        "hora", "horas", "tiempo", "día", "días", "semana", "mes", "año", "cabo", "pesar",
                    }
                    head_or_next_non_loc = (
                        head_tok.text.lower() in non_locative_targets
                        or head_tok.lemma_.lower() in non_locative_targets
                        or head_tok.pos_ in ("PRON", "DET", "NUM")
                        or (next_tok is not None and next_tok.text.lower() in non_locative_targets)
                    )
                    is_personal_acc = any(
                        c.dep_ in ("iobj", "obj") and c.pos_ == "NOUN" and "anim" in c.tag_.lower()
                        for c in token.children
                    ) or (dep == "case" and head_tok.dep_ in ("obj", "iobj") and head_tok.pos_ in ("NOUN", "PROPN", "PRON"))

                    head_verb_lemma = head_tok.head.lemma_.lower() if head_tok.head.pos_ in ("VERB", "AUX") else ""
                    regime_a_verbs = {"asistir", "pertenecer", "ayudar", "invitar", "llamar", "aprender", "enseñar", "dedicarse", "acceder"}
                    head_governs_a = head_verb_lemma in regime_a_verbs

                    if text_l in ("a", "al") and (
                        is_personal_acc or next_is_inf or head_is_inf
                        or head_or_next_non_loc or head_governs_a
                    ):
                        transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="structural_omission", target_action="omit_structural", justification="Preposición estructural 'a'/'al' (régimen verbal, infinitivo o canal de contacto) omitida en LSEC"))
                    else:
                        transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="destination", target_action="direction_goal", target_gloss="HACIA", justification="Preposición de destino o dirección transferida a movimiento"))

                elif text_l == "sin":
                    transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="privative", target_action="semantic_marker", target_gloss="SIN", justification="Preposición privativa con contenido semántico; se conserva como SIN"))
                elif text_l == "hasta":
                    transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="limit", target_action="semantic_marker", target_gloss="HASTA", justification="Preposición de límite temporal o espacial; se conserva como HASTA"))
                elif text_l == "sobre":
                    transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="topic_or_location", target_action="semantic_marker", target_gloss="SOBRE", justification="Preposición 'sobre' con contenido de tema o ubicación; se conserva"))

                elif text_l == "por":
                    # "por qué" forma una unidad interrogativa (POR-QUÉ);
                    # no se glosa la preposición por separado.
                    next_tok = doc[token.i + 1] if token.i + 1 < len(doc) else None
                    if next_tok is not None and (
                        (next_tok.text.lower() in ("qué", "que") and ("?" in doc.text or "¿" in doc.text))
                        or next_tok.text.lower() in ("favor", "ejemplo", "supuesto", "fin", "lo", "ciento")
                    ):
                        continue
                    motion_verbs = {"ir", "venir", "caminar", "viajar", "pasar", "correr", "volver", "llegar", "salir", "entrar", "recorrer", "cruzar", "subir", "bajar"}
                    governor = head_tok.head.lemma_.lower() if head_tok.head.pos_ in ("VERB", "AUX") else ""
                    if governor in motion_verbs:
                        transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="path", target_action="direction_goal", target_gloss="HACIA", justification="Preposición de trayectoria con verbo de movimiento"))
                    else:
                        transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="cause_or_agent", target_action="semantic_marker", target_gloss="POR", justification="Preposición 'por' causal o agentiva; se conserva para no deformar el significado"))

                elif text_l in ("en", "bajo", "entre"):
                    if any(ch.pos_ == "NUM" or ch.text.lower() in ("año", "mes", "día", "semana") for ch in token.head.children):
                        transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="time", target_action="temporal_operator", justification="Preposición temporal integrada en el marco temporal de la cláusula"))
                    else:
                        transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="location", target_action="spatial_locus", justification="Preposición locativa transferida a establecimiento de locus espacial"))

                elif text_l == "con":
                    if any(ch.dep_ in ("obj", "pobj") and ch.pos_ in ("NOUN", "PROPN") for ch in token.children):
                        transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="instrument", target_action="instrument_classifier", requires_review=True, justification="Preposición instrumental transferible a clasificador de manipulación"))
                    else:
                        transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="accompaniment", target_action="accompaniment_sign", target_gloss="CON", justification="Preposición de compañía transferida a seña CON"))

                elif text_l == "para":
                    # Distinguir beneficiario vs. finalidad
                    next_tok = doc[token.i + 1] if token.i + 1 < len(doc) else None
                    head_is_inf = head_tok.pos_ in ("VERB", "AUX") and (
                        "Inf" in head_tok.morph.get("VerbForm", [])
                        or head_tok.text.lower().endswith(("ar", "er", "ir", "arse", "erse", "irse"))
                    )
                    next_is_inf = next_tok is not None and next_tok.pos_ in ("VERB", "AUX") and (
                        "Inf" in next_tok.morph.get("VerbForm", [])
                        or next_tok.text.lower().endswith(("ar", "er", "ir", "arse", "erse", "irse"))
                    )
                    has_inf = head_is_inf or next_is_inf or any(ch.pos_ == "VERB" for ch in token.head.children if ch.i > token.i)
                    if has_inf:
                        transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="purpose", target_action="purpose_marker", target_gloss="PROPÓSITO", justification="Preposición de finalidad transferida a conector de propósito"))
                    else:
                        transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="beneficiary", target_action="beneficiary_marker", requires_review=True, justification="Preposición de beneficiario transferida a concordancia de locus"))

                else:
                    transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="structural_omission", target_action="omit_structural", justification="Preposición estructural sin contenido semántico independiente"))

            # 5. Artículos definidos genéricos
            elif pos == "DET" and text_l in ("el", "la", "los", "las"):
                transfers.append(FunctionalTransfer(token_idx=token.i, source_word=token.text, lemma=lemma_l, pos=pos, function_type="definiteness", target_action="omit_structural", justification="Artículo determinado genérico omitido por no tener marca explícita en LSEC"))

        return transfers

    # ── Correferencia pronominal ──────────────────────────────

    def detect_coreference(self, doc) -> List[CoreferenceLink]:
        """
        Detecta correferencia pronominal básica.

        Resuelve pronombres como 'nosotros' (institucional), 'lo' (anafórico),
        'te'/'me' (destinatario), siguiendo las convenciones LSEC.
        """
        links: List[CoreferenceLink] = []
        if doc is None:
            return links

        for token in doc:
            text_lower = token.text.lower()
            # "nosotros" / "nos" → referente institucional
            if text_lower in ("nosotros", "nos", "nuestro", "nuestra"):
                links.append(CoreferenceLink(pronoun=text_lower, pronoun_token_idx=token.i, antecedent_type="institutional", resolved_entity="hablante_institucional", resolved_gloss="PRO1-PL", confidence=0.85))
            # "lo" como anáfora a proposición previa
            elif text_lower == "lo" and token.dep_ == "obj":
                links.append(CoreferenceLink(pronoun=text_lower, pronoun_token_idx=token.i, antecedent_type="anaphoric", resolved_entity="proposición_previa", resolved_gloss="ESO", confidence=0.70))
            # "te"/"me" como destinatario
            elif text_lower in ("te", "me") and token.dep_ in ("obj", "iobj", "dobj"):
                links.append(CoreferenceLink(pronoun=text_lower, pronoun_token_idx=token.i, antecedent_type="discourse", resolved_entity="destinatario" if text_lower == "te" else "hablante", resolved_gloss="PRO2" if text_lower == "te" else "PRO1", confidence=0.75))
            # "ellos"/"ellas" → anáfora a grupo
            elif text_lower in ("ellos", "ellas") and token.dep_ in ("nsubj", "nsubj:pass"):
                links.append(CoreferenceLink(pronoun=text_lower, pronoun_token_idx=token.i, antecedent_type="anaphoric", resolved_entity="grupo_previo", resolved_gloss="ELLOS", confidence=0.70))

        return links

    # ── Clasificadores semánticos condicionados ───────────────

    def detect_classifiers(self, doc) -> List[ClassifierCandidate]:
        """
        Genera candidatos a clasificadores LSEC (CLASSIFIER_CANDIDATE).

        NO asigna clasificadores de manera puramente semántica o automática.
        Exige respaldo léxico o marca el candidato con requires_review=True.
        """
        candidates: List[ClassifierCandidate] = []
        if doc is None:
            return candidates

        for token in doc:
            if token.pos_ not in ("NOUN", "PROPN"):
                continue
            lemma_lower = token.lemma_.lower()
            if lemma_lower in _SEMANTIC_CLASSIFIERS:
                candidates.append(ClassifierCandidate(token_idx=token.i, referent_lemma=lemma_lower, token_text=token.text, classifier_type=_SEMANTIC_CLASSIFIERS[lemma_lower], status="CLASSIFIER_CANDIDATE", has_lexical_support=False, requires_review=True, confidence=0.60))

        return candidates


# Alias canónico
LinguisticAnalyzer = EnhancedLinguisticAnalyzer
