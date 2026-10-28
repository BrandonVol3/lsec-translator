"""
Módulo de Detección de Expresiones Multipalabra (MWE).

Identifica colocaciones fijas, unidades nominales compuestas, locuciones y frases
institucionales antes del análisis sintáctico. Evita la sobre-segmentación morfológica
(por ejemplo, evita generar el verbo copulativo 'SER' a partir de 'seres humanos').
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MWEMatch:
    """Coincidencia de una expresión multipalabra en el texto."""
    id: str
    source_phrase: str
    matched_text: str
    start_char: int
    end_char: int
    semantic_concept: str
    prevent_component_parsing: bool
    prevent_verb_generation: List[str] = field(default_factory=list)
    preferred_gloss: Optional[str] = None
    candidate_realizations: List[List[str]] = field(default_factory=list)
    confidence: float = 0.90
    token_span: Optional[Tuple[int, int]] = None


@dataclass
class MWEDefinition:
    """Definición de regla MWE."""
    id: str
    source_phrase: str
    semantic_concept: str
    prevent_component_parsing: bool = True
    prevent_verb_generation: List[str] = field(default_factory=list)
    preferred_gloss: Optional[str] = None
    candidate_realizations: List[List[str]] = field(default_factory=list)
    confidence: float = 0.90
    regex_pattern: Optional[re.Pattern] = None


# Reglas predeterminadas integradas
_DEFAULT_MWE_DEFINITIONS: List[MWEDefinition] = [
    MWEDefinition(
        id="mwe_seres_humanos",
        source_phrase="seres humanos",
        semantic_concept="human_person",
        prevent_component_parsing=True,
        prevent_verb_generation=["SER"],
        preferred_gloss="PERSONA",
        candidate_realizations=[["PERSONA"], ["PERSONA", "HUMANA"], ["PERSONA", "ÍNTEGRA"]],
        confidence=0.88,
    ),
    MWEDefinition(
        id="mwe_primer_dia",
        source_phrase="primer día",
        semantic_concept="from_the_start",
        prevent_component_parsing=True,
        preferred_gloss="DÍA-PRIMERO",
        candidate_realizations=[["DÍA", "PRIMERO"], ["INICIO", "DESDE"]],
        confidence=0.90,
    ),
    MWEDefinition(
        id="mwe_excelencia_academica",
        source_phrase="excelencia académica",
        semantic_concept="academic_excellence",
        prevent_component_parsing=True,
        preferred_gloss="EXCELENCIA-ACADÉMICA",
        candidate_realizations=[["EXCELENCIA", "ACADÉMICA"], ["CALIDAD", "EDUCACIÓN", "ALTA"]],
        confidence=0.92,
    ),
    MWEDefinition(
        id="mwe_carreras_de_grado",
        source_phrase="carreras de grado",
        semantic_concept="undergraduate_degrees",
        prevent_component_parsing=True,
        preferred_gloss="CARRERA-GRADO",
        candidate_realizations=[["CARRERA", "GRADO"], ["CARRERA", "UNIVERSIDAD"]],
        confidence=0.90,
    ),
    MWEDefinition(
        id="mwe_universidad_publica",
        source_phrase="universidad pública",
        semantic_concept="public_university",
        prevent_component_parsing=True,
        preferred_gloss="UNIVERSIDAD-PÚBLICA",
        candidate_realizations=[["UNIVERSIDAD", "PÚBLICA"], ["UNIVERSIDAD", "ESTADO"]],
        confidence=0.92,
    ),
    MWEDefinition(
        id="mwe_haz_posible",
        source_phrase="haz posible",
        semantic_concept="make_possible_realize",
        prevent_component_parsing=True,
        preferred_gloss="REALIDAD-HACER",
        candidate_realizations=[["REALIDAD", "HACER"], ["LOGRAR", "PODER"]],
        confidence=0.89,
    ),
    MWEDefinition(
        id="mwe_transformar_mundo",
        source_phrase="transformar el mundo",
        semantic_concept="transform_world",
        prevent_component_parsing=True,
        preferred_gloss="MUNDO-TRANSFORMAR",
        candidate_realizations=[["MUNDO", "TRANSFORMAR"], ["SOCIEDAD", "CAMBIAR", "MEJORAR"]],
        confidence=0.91,
    ),
    MWEDefinition(
        id="mwe_mas_de",
        source_phrase="más de",
        semantic_concept="more_than_quantifier",
        prevent_component_parsing=True,
        preferred_gloss="MÁS-DE",
        candidate_realizations=[["MÁS-DE"], ["SUPERAR"]],
        confidence=0.95,
    ),
    MWEDefinition(
        id="mwe_mas_que",
        source_phrase="más que",
        semantic_concept="beyond_not_only",
        prevent_component_parsing=True,
        preferred_gloss="SOLAMENTE-NO",
        candidate_realizations=[["SOLAMENTE-NO"], ["ADEMÁS"]],
        confidence=0.90,
    ),
    MWEDefinition(
        id="mwe_no_solo",
        source_phrase="no solo",
        semantic_concept="not_only_focus",
        prevent_component_parsing=True,
        preferred_gloss="SOLAMENTE-NO",
        candidate_realizations=[["SOLAMENTE-NO"]],
        confidence=0.95,
    ),
    MWEDefinition(
        id="mwe_quien_quieres_ser",
        source_phrase="quién quieres ser",
        semantic_concept="identity_reflection",
        prevent_component_parsing=False,
        preferred_gloss="QUIÉN-SER-QUERER",
        candidate_realizations=[["PRO2", "QUIÉN", "SER", "QUERER"]],
        confidence=0.88,
    ),
    MWEDefinition(
        id="mwe_ya_lo_hicieron",
        source_phrase="ya lo hicieron",
        semantic_concept="goal_achievement",
        prevent_component_parsing=True,
        preferred_gloss="YA LOGRAR",
        candidate_realizations=[["YA", "LOGRAR"], ["YA", "HACER"]],
        confidence=0.90,
    ),
    MWEDefinition(
        id="mwe_sin_embargo",
        source_phrase="sin embargo",
        semantic_concept="contrast_connector",
        prevent_component_parsing=True,
        preferred_gloss="PERO",
        candidate_realizations=[["PERO"]],
        confidence=0.95,
    ),
    MWEDefinition(
        id="mwe_no_obstante",
        source_phrase="no obstante",
        semantic_concept="contrast_connector",
        prevent_component_parsing=True,
        preferred_gloss="PERO",
        candidate_realizations=[["PERO"]],
        confidence=0.95,
    ),
    MWEDefinition(
        id="mwe_a_pesar_de",
        source_phrase="a pesar de",
        semantic_concept="concessive_connector",
        prevent_component_parsing=True,
        preferred_gloss="AUNQUE",
        candidate_realizations=[["AUNQUE"]],
        confidence=0.95,
    ),
    MWEDefinition(
        id="mwe_a_partir_de",
        source_phrase="a partir de",
        semantic_concept="temporal_start_point",
        prevent_component_parsing=True,
        preferred_gloss="DESDE",
        candidate_realizations=[["DESDE"], ["A-PARTIR-DE"]],
        confidence=0.95,
        regex_pattern=re.compile(r"\ba\s+partir\s+de(?:l)?\b", re.IGNORECASE),
    ),
    MWEDefinition(
        id="mwe_llevar_a_cabo",
        source_phrase="llevar a cabo",
        semantic_concept="realizar",
        prevent_component_parsing=True,
        preferred_gloss="REALIZAR",
        candidate_realizations=[["REALIZAR"]],
        confidence=0.95,
        regex_pattern=re.compile(r"\bllev[a-záéíóúñ]+\s+a\s+cabo\b", re.IGNORECASE),
    ),
    MWEDefinition(
        id="mwe_prestar_atencion",
        source_phrase="prestar atención",
        semantic_concept="pay_attention",
        prevent_component_parsing=True,
        preferred_gloss="PRESTAR-ATENCIÓN",
        candidate_realizations=[["PRESTAR-ATENCIÓN"]],
        confidence=0.95,
        regex_pattern=re.compile(r"\bprest[a-záéíóúñ]*\s+atenci[oó]n\b", re.IGNORECASE),
    ),
    MWEDefinition(
        id="mwe_de_nuevo",
        source_phrase="de nuevo",
        semantic_concept="otra_vez",
        prevent_component_parsing=True,
        preferred_gloss="OTRA-VEZ",
        candidate_realizations=[["OTRA-VEZ"]],
        confidence=0.95,
    ),
    MWEDefinition(
        id="mwe_hacer_reir_mucho",
        source_phrase="hizo reír mucho",
        semantic_concept="matarse_de_la_risa",
        prevent_component_parsing=True,
        preferred_gloss="MATARSE-DE-LA-RISA",
        candidate_realizations=[["MATARSE-DE-LA-RISA"]],
        confidence=0.96,
        regex_pattern=re.compile(
            r"\b(?:(?:era|fue|es)\s+(?:muy\s+)?c[oó]mic[ao]\s+)?(?:me\s+|nos\s+|te\s+|le\s+|les\s+)?(?:hizo|hace|hacen|hacer)\s+re[íi]r\s+mucho\b",
            re.IGNORECASE,
        ),
    ),
    MWEDefinition(
        id="mwe_matarse_de_la_risa",
        source_phrase="matarse de la risa",
        semantic_concept="matarse_de_la_risa",
        prevent_component_parsing=True,
        preferred_gloss="MATARSE-DE-LA-RISA",
        candidate_realizations=[["MATARSE-DE-LA-RISA"]],
        confidence=0.96,
        regex_pattern=re.compile(r"\bmat(?:ar(?:se)?|[oó]|amos|aron)\s+de\s+la\s+risa\b", re.IGNORECASE),
    ),
    MWEDefinition(
        id="mwe_de_nuevo_alt",
        source_phrase="de nuevo",
        semantic_concept="otra_vez",
        prevent_component_parsing=True,
        preferred_gloss="OTRA-VEZ",
        candidate_realizations=[["OTRA-VEZ"]],
        confidence=0.95,
    ),
    MWEDefinition(
        id="mwe_cara_sucia",
        source_phrase="cara sucia",
        semantic_concept="cara_sucia",
        prevent_component_parsing=True,
        preferred_gloss="CARA-SUCIA",
        candidate_realizations=[["CARA-SUCIA"]],
        confidence=0.98,
        regex_pattern=re.compile(r"\bcaras?\s+sucias?\b", re.IGNORECASE),
    ),
]


class MWEDetector:
    """
    Detector de unidades multipalabra y colocaciones léxicas en texto español.
    """

    def __init__(self, definitions: Optional[List[MWEDefinition]] = None) -> None:
        self._definitions: List[MWEDefinition] = []
        defs = definitions or list(_DEFAULT_MWE_DEFINITIONS)
        for d in defs:
            if d.regex_pattern is None:
                # Compilar regex para búsqueda flexible de espacios y acentos
                pattern_str = r"\b" + re.escape(d.source_phrase).replace(r"\ ", r"\s+") + r"\b"
                compiled = re.compile(pattern_str, re.IGNORECASE)
                d.regex_pattern = compiled
            self._definitions.append(d)

        logger.info("MWEDetector inicializado con %d reglas MWE.", len(self._definitions))

    def load_from_lexicon(self, lexicon_data: Dict[str, Any]) -> None:
        """Carga definiciones MWE adicionales desde el lexicón JSON."""
        if "multi_word_expressions" in lexicon_data:
            for item in lexicon_data["multi_word_expressions"]:
                phrase = item.get("source_phrase", "")
                if not phrase:
                    continue
                mwe_def = MWEDefinition(
                    id=item.get("id", f"mwe_{phrase.replace(' ', '_')}"),
                    source_phrase=phrase,
                    semantic_concept=item.get("semantic_concept", phrase),
                    prevent_component_parsing=item.get("prevent_component_parsing", True),
                    prevent_verb_generation=item.get("prevent_verb_generation", []),
                    preferred_gloss=item.get("preferred_gloss"),
                    candidate_realizations=item.get("candidate_realizations", []),
                    confidence=item.get("confidence", 0.90),
                )
                pattern_str = r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b"
                mwe_def.regex_pattern = re.compile(pattern_str, re.IGNORECASE)
                self._definitions.append(mwe_def)
            logger.info("MWEDetector: %d reglas cargadas desde lexicón.", len(self._definitions))

    def detect(self, text: str) -> List[MWEMatch]:
        """
        Encuentra todas las MWE en el texto sin solapamientos conflictivos.
        """
        matches: List[MWEMatch] = []
        occupied_spans: List[Tuple[int, int]] = []

        for d in self._definitions:
            if not d.regex_pattern:
                continue
            for m in d.regex_pattern.finditer(text):
                start, end = m.start(), m.end()
                # Evitar solapamiento
                if any(start < o_end and end > o_start for o_start, o_end in occupied_spans):
                    continue

                occupied_spans.append((start, end))
                matches.append(
                    MWEMatch(
                        id=d.id,
                        source_phrase=d.source_phrase,
                        matched_text=m.group(0),
                        start_char=start,
                        end_char=end,
                        semantic_concept=d.semantic_concept,
                        prevent_component_parsing=d.prevent_component_parsing,
                        prevent_verb_generation=d.prevent_verb_generation,
                        preferred_gloss=d.preferred_gloss,
                        candidate_realizations=d.candidate_realizations,
                        confidence=d.confidence,
                    )
                )

        # Ordenar por posición en el texto
        matches.sort(key=lambda x: x.start_char)
        return matches

    def check_token_in_mwe(self, char_idx: int, matches: List[MWEMatch]) -> Optional[MWEMatch]:
        """Verifica si un índice de carácter cae dentro de alguna MWE detectada."""
        for m in matches:
            if m.start_char <= char_idx < m.end_char:
                return m
        return None
