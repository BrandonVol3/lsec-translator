"""
Recursos léxicos estáticos, constantes gramaticales y composición numérica posicional LSEC (LSEC 2.8).

Extraído de `discourse_planner.py` para cumplir con el principio de Responsabilidad Única (SRP).
"""

from __future__ import annotations

import unicodedata
from typing import Dict, List, Optional, Set, Tuple

# Tokens cuya glosa gestionan las reglas FENASEC por palabra individual (negación incorporada, cortesía).
_RULE_MANAGED_TOKENS: Set[str] = {
    "no", "nunca", "jamas", "nadie", "ni", "tampoco", "nada", "ninguno", "ninguna", "favor",
}


def _strip_accents_lower(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
    )


_BLACKLIST_POS_TAGS: Set[str] = {
    "DET",    # Artículos
    "ADP",    # Preposiciones (salvo específicas)
    "CCONJ",  # Conjunciones coordinantes
    "SCONJ",  # Conjunciones subordinantes
    "PUNCT",  # Puntuación
    "SPACE",  # Espacios
    "SYM",    # Símbolos
}

_COPULATIVE_LEMMAS: Set[str] = {"ser", "estar", "haber"}
_CLITIC_PRONOUNS: Set[str] = {"lo", "la", "le", "los", "las", "les", "se"}

# spaCy puede etiquetar nombres propios y adjetivos institucionales como
# verbos cuando el texto procede de ASR. Estas formas son léxicas, no verbales,
# y deben conservarse en NFC antes de convertirse a glosa.
_CANONICAL_SOURCE_LEMMAS: Dict[str, str] = {
    "politécnica": "politécnica",
    "politecnica": "politécnica",
    "académica": "académico",
    "academica": "académico",
    "evaluación": "evaluación",
    "evaluacion": "evaluación",
    "admisión": "admisión",
    "admision": "admisión",
    "mañana": "mañana",
    "educación": "educación",
    "educacion": "educación",
    "tecnología": "tecnología",
    "tecnologia": "tecnología",
    "inscripción": "inscripción",
    "inscripcion": "inscripción",
    "música": "música",
    "musica": "música",
    "diseño": "diseño",
    "diseno": "diseño",
    "coordinación": "coordinación",
    "coordinacion": "coordinación",
    "cómo": "cómo",
    "como": "como",
    "dónde": "dónde",
    "donde": "dónde",
    "frío": "frío",
    "frio": "frío",
    "calor": "calor",
    "jóvenes": "joven",
    "jovenes": "joven",
    "cientos": "cientos",
    "aprendes": "aprender",
    "aprende": "aprender",
    "implementó": "implementar",
    "implemento": "implementar",
    "inició": "iniciar",
    "inicio": "iniciar",
    "realizaremos": "realizar",
    "realizarán": "realizar",
    "escríbenos": "escribir",
    "escribenos": "escribir",
    "constante": "constante",
    "presencial": "presencial",
    "semipresencial": "semipresencial",
    "arroba": "arroba",
    "punto": "punto",
    "edu": "edu",
    "ec": "ec",
    # Sustantivos académicos e institucionales que spaCy puede verbalizar
    # (-o final) o enviar a dactilología por estar capitalizados.
    "comercio": "comercio",
    "exterior": "exterior",
    "presente": "presente",
    "ingeniería": "ingeniería",
    "ingenieria": "ingeniería",
    "computación": "computación",
    "computacion": "computación",
    "enfermería": "enfermería",
    "enfermeria": "enfermería",
    "agropecuaria": "agropecuaria",
    "inicial": "inicial",
    "porcentaje": "porcentaje",
    "puntaje": "puntaje",
    "nivelación": "nivelación",
    "nivelacion": "nivelación",
    "cronograma": "cronograma",
    "semestre": "semestre",
    "facultad": "facultad",
    "secretaría": "secretaría",
    "secretaria": "secretaría",
    "coordinador": "coordinador",
    "rector": "rector",
    "directora": "directora",
    "docente": "docente",
    "becario": "becario",
    "matrícula": "matrícula",
    "matricula": "matrícula",
    "certificado": "certificado",
    "comprobante": "comprobante",
    "carpeta": "carpeta",
    "requisito": "requisito",
    "plataforma": "plataforma",
    "tarea": "tarea",
    "internet": "internet",
    "duda": "duda",
    "dificultad": "dificultad",
    "rendimiento": "rendimiento",
    "bienestar": "bienestar",
    "movilidad": "movilidad",
    "entusiasmo": "entusiasmo",
    "equipamiento": "equipamiento",
    "intercultural": "intercultural",
    "lingüístico": "lingüístico",
    "linguistico": "lingüístico",
    "lingüística": "lingüístico",
    "linguistica": "lingüístico",
    "antigüedad": "antigüedad",
    "antiguedad": "antigüedad",
    "prestigio": "prestigio",
    "frontera": "frontera",
    "mutuamente": "mutuamente",
    "alguien": "alguien",
}

# Formas canónicas que deben conservarse como nombre/adjetivo aunque spaCy
# (o la morfología verbal) proponga un lema en -ar/-er/-ir.
_CANONICAL_NOMINAL_FORMS: Set[str] = {
    "politécnica", "politecnica", "académica", "academica",
    "evaluación", "evaluacion", "admisión", "admision",
    "mañana", "educación", "educacion", "tecnología", "tecnologia",
    "inscripción", "inscripcion", "música", "musica", "diseño",
    "diseno", "coordinación", "coordinacion", "frío", "frio",
    "jóvenes", "jovenes", "cientos", "aprendes", "aprende",
    "implementó", "implemento", "inició", "inicio",
    "realizaremos", "realizarán", "escríbenos", "escribenos",
    "comercio", "exterior", "presente", "ingeniería", "ingenieria",
    "computación", "computacion", "enfermería", "enfermeria",
    "agropecuaria", "inicial", "porcentaje", "puntaje",
    "nivelación", "nivelacion", "cronograma", "semestre", "facultad",
    "secretaría", "secretaria", "coordinador", "rector", "directora",
    "docente", "becario", "matrícula", "matricula", "certificado",
    "comprobante", "carpeta", "requisito", "plataforma", "tarea",
    "internet", "duda", "dificultad", "rendimiento", "bienestar",
    "movilidad", "entusiasmo", "equipamiento", "intercultural",
    "lingüístico", "linguistico", "lingüística", "linguistica",
    "antigüedad", "antiguedad", "prestigio", "frontera",
    "mutuamente", "alguien",
}

# Conjunciones subordinantes con contenido semántico que no deben omitirse.
_SEMANTIC_SCONJ_GLOSS: Dict[str, str] = {
    "aunque": "AUNQUE",
    "si": "SI",
    "cuando": "CUANDO",
    "mientras": "MIENTRAS",
    "porque": "PORQUE",
    "pues": "PUES",
    "apenas": "APENAS",
}

# Formas verbales con clítico que spaCy puede etiquetar como nombre y cuyo
# lema superficial no debe pasar por la normalización nominal (evita GRADUARNO).
_CLITIC_VERB_LEMMAS: Dict[str, str] = {
    "graduarme": "graduar",
    "graduarte": "graduar",
    "graduarse": "graduar",
    "graduarnos": "graduar",
    "graduarlos": "graduar",
    "graduarlas": "graduar",
    "prefiero": "preferir",
    "prefieres": "preferir",
    "prefiere": "preferir",
    "preferimos": "preferir",
    "preferís": "preferir",
    "prefieren": "preferir",
    "pídeselo": "pedir",
    "pideselo": "pedir",
    "pídesela": "pedir",
    "pidesela": "pedir",
    "pídemelo": "pedir",
    "pidemelo": "pedir",
}

_QUANTIFIER_CANON: Dict[str, str] = {
    "todo": "todo", "todos": "todo", "toda": "todo", "todas": "todo",
    "mucho": "mucho", "muchos": "mucho", "mucha": "mucho", "muchas": "mucho",
    "varios": "varios", "varias": "varios",
    "poco": "poco", "pocos": "poco", "poca": "poco", "pocas": "poco",
    "alguno": "alguno", "algunos": "alguno", "alguna": "alguna", "algunas": "alguno",
    "bastante": "bastante", "bastantes": "bastante",
    "demasiado": "demasiado", "demasiados": "demasiado", "demasiada": "demasiado", "demasiadas": "demasiado",
    "cada": "cada",
}

_KNOWN_SIGN_PROPN: Set[str] = {
    "maría", "maria", "juan", "pedro", "carlos", "ana", "josé", "jose", "luis",
    "carchi", "politécnica", "politecnica", "ecuador", "quito", "guayaquil",
    "cuenca", "ibarra", "tulcán", "tulcan", "cayambe", "sierra", "costa",
    "oriente", "galápagos", "galapagos", "ambato", "loja", "manta", "portoviejo",
    "riobamba", "esmeraldas", "machala", "babahoyo", "latacunga", "guaranda",
    "azogues", "macas", "tena", "puyo", "zamora", "whatsapp", "lsec", "conadis", "fenasec", "upec",
    "estatal",
}

DEFAULT_QUANTIFIER_LEMMAS: Set[str] = {
    "mucho", "muchos", "muchas", "mucha",
    "varios", "varias",
    "poco", "pocos", "pocas", "poca",
    "todo", "todos", "todas", "toda",
    "alguno", "algunos", "algunas", "alguna",
    "ninguno", "ningunos", "ningunas", "ninguna",
    "bastante", "bastantes",
    "demasiado", "demasiados", "demasiadas", "demasiada",
    "más", "menos", "cada",
}

DEFAULT_WH_LEMMAS: Set[str] = {
    "qué", "quién", "quiénes", "dónde", "cuándo",
    "cómo", "cuál", "cuáles", "cuánto", "cuánta",
    "cuántos", "cuántas",
}

DEFAULT_TIME_MARKERS: Set[str] = {
    "ayer", "hoy", "mañana", "ahora", "antes", "después", "siempre",
    "nunca", "jamás", "futuro", "pasado", "año", "mes", "día",
    "tarde", "noche", "temprano", "pronto", "semana", "desde",
    "primero", "luego",
}

DEFAULT_DURATION_MS: Dict[str, int] = {
    "sign_base": 500,
    "sign_short": 400,
    "sign_long": 600,
    "fingerspelling_per_char": 300,
    "temporal_marker": 400,
    "aspectual_marker": 350,
    "deixis": 350,
    "plural_marker": 300,
    "inter_clause_pause": 200,
}

GRAMMATICAL_FUNCTIONAL_WORDS: Set[str] = {
    "afirmar", "upec", "ser", "existir", "tener", "estar", "haber", "ofrecer", "incluir",
    "que", "de", "en", "con", "por", "para", "y", "o", "un", "una", "el", "la", "los", "las",
    "yo", "tú", "él", "ella", "nosotros", "ustedes", "ellos", "me", "te", "se", "nos",
    "not_only_focus", "aspect", "mood", "tense", "negation", "polarity",
    "contrast_connector", "concessive_connector",
}

MWE_CONCEPT_SYNONYMS: Dict[str, Set[str]] = {
    "public_university": {"UNIVERSIDAD", "PÚBLICA"},
    "human_person": {"PERSONA", "PERSONAS"},
    "undergraduate_degrees": {"CARRERA", "GRADO"},
    "transform_world": {"MUNDO", "TRANSFORMAR"},
    "identity_reflection": {"QUIÉN", "SER", "DECIDIR"},
    "contenido_imaginado": {"IMAGINAR", "ESO", "REALIDAD"},
    "reconocimiento_institucional": {"ORGULLO", "SENTIR"},
    "enorgullecer": {"ORGULLO", "SENTIR"},
    "evolucionar": {"AVANZAR"},
    "hacer_realidad": {"HACER", "REALIDAD"},
    "construir": {"DESARROLLAR", "IDEA", "CONSTRUIR", "CREAR"},
    "desarrollar": {"DESARROLLAR", "IDEA", "CONSTRUIR", "CREAR"},
    "varias": {"VARIOS", "MUCHO", "DIVERSO"},
    "varios": {"VARIOS", "MUCHO", "DIVERSO"},
    "muchas": {"MUCHO", "VARIOS"},
    "muchos": {"MUCHO", "VARIOS"},
    "mucha": {"MUCHO", "VARIOS"},
    "todos": {"TODO", "TODOS"},
    "todas": {"TODO", "TODOS"},
    "toda": {"TODO", "TODOS"},
    "desde": {"DESDE", "DESDE-PRIMER-DÍA"},
    "from_the_start": {"DESDE", "PRIMERO", "DÍA", "DIA"},
    "more_than_quantifier": {"MÁS-DE", "MÁS", "CINCO-MIL"},
    "porque": {"PORQUE", "CAUSA"},
    "embargo": {"PERO", "SIN-EMBARGO"},
    "sin": {"PERO", "SIN-EMBARGO", "SIN"},
    "pero": {"PERO"},
    "pesar": {"AUNQUE"},
    "contrast_connector": {"PERO", "SIN-EMBARGO"},
    "concessive_connector": {"AUNQUE", "PESAR"},
    "cabo": {"REALIZAR"},
    "llevar": {"LLEVAR", "REALIZAR"},
    "llevaremos": {"LLEVAR", "REALIZAR"},
    "realizar": {"REALIZAR", "LLEVAR"},
    "nuevo": {"NUEVO", "OTRA-VEZ"},
    "otra_vez": {"OTRA-VEZ", "NUEVO"},
    "cercanía": {"ACOMPAÑAR"},
    "decir": {"EXPLICAR", "DECIR"},
    "imparable": {"PERSONA", "FUERTE", "AVANZAR", "DETERMINADA", "CONTINUAR"},
    "tú": {"PRO2", "TÚ"},
    "tu": {"PRO2", "TÚ"},
    "te": {"PRO2", "TÚ"},
    "yo": {"PRO1", "YO"},
    "me": {"PRO1", "YO"},
    "nosotros": {"PRO1-PL", "PRO1", "NOSOTROS"},
    "nos": {"PRO1-PL", "PRO1", "NOSOTROS"},
    "él": {"PRO3", "ÉL"},
    "ella": {"PRO3", "ELLA"},
    "ellos": {"PRO3-PL", "PRO3", "ELLOS"},
    "ellas": {"PRO3-PL", "PRO3", "ELLAS"},
    "ustedes": {"PRO2-PL", "PRO2", "USTEDES"},
}

# ============================================================
# Composición numérica posicional (LSEC 2.8)
# ============================================================

_NUMBER_UNITS: Dict[int, Tuple[str, ...]] = {
    0: ("CERO",), 1: ("UNO",), 2: ("DOS",), 3: ("TRES",), 4: ("CUATRO",),
    5: ("CINCO",), 6: ("SEIS",), 7: ("SIETE",), 8: ("OCHO",), 9: ("NUEVE",),
    10: ("DIEZ",), 11: ("ONCE",), 12: ("DOCE",), 13: ("TRECE",),
    14: ("CATORCE",), 15: ("QUINCE",), 16: ("DIECISÉIS",),
    17: ("DIECISIETE",), 18: ("DIECIOCHO",), 19: ("DIECINUEVE",),
    20: ("VEINTE",), 21: ("VEINTE", "UNO"), 22: ("VEINTE", "DOS"),
    23: ("VEINTE", "TRES"), 24: ("VEINTE", "CUATRO"), 25: ("VEINTE", "CINCO"),
    26: ("VEINTE", "SEIS"), 27: ("VEINTE", "SIETE"), 28: ("VEINTE", "OCHO"),
    29: ("VEINTE", "NUEVE"),
}

_NUMBER_TENS: Dict[int, str] = {
    3: "TREINTA", 4: "CUARENTA", 5: "CINCUENTA", 6: "SESENTA",
    7: "SETENTA", 8: "OCHENTA", 9: "NOVENTA",
}

_NUMBER_HUNDREDS: Dict[int, Tuple[str, ...]] = {
    1: ("CIEN",),
    2: ("DOSCIENTOS",),
    3: ("TRESCIENTOS",),
    4: ("CUATROCIENTOS",),
    5: ("CINCO", "CIENTOS"),
    6: ("SEISCIENTOS",),
    7: ("SETECIENTOS",),
    8: ("OCHOCIENTOS",),
    9: ("NOVECIENTOS",),
}

_NUMBER_WORD_EXPANSIONS: Dict[str, Tuple[str, ...]] = {
    "QUINIENTO": ("CINCO", "CIENTOS"),
    "QUINIENTOS": ("CINCO", "CIENTOS"),
    "QUINIENTAS": ("CINCO", "CIENTOS"),
    "CIENTO": ("CIEN",),
    "VEINTIDÓS": ("VEINTE", "DOS"),
    "VEINTIDOS": ("VEINTE", "DOS"),
    "VEINTISÉIS": ("VEINTE", "SEIS"),
    "VEINTISEIS": ("VEINTE", "SEIS"),
    "TRES-MIL": ("TRES", "MIL"),
    "CUATRO-MIL": ("CUATRO", "MIL"),
    "DOS-MIL": ("DOS", "MIL"),
}


def _cardinal_sequence(value: int) -> Tuple[str, ...]:
    """Descompone un entero en glosas posicionales resolubles por el avatar."""
    if value < 0:
        return ()
    if value < 30:
        return _NUMBER_UNITS.get(value, ())
    if value < 100:
        tens, units = divmod(value, 10)
        prefix = _NUMBER_TENS.get(tens)
        if prefix is None:
            return ()
        return (prefix,) + (_NUMBER_UNITS.get(units, ()) if units else ())
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        prefix = _NUMBER_HUNDREDS.get(hundreds, ())
        if rest == 0:
            return prefix
        return prefix + _cardinal_sequence(rest)
    if value < 1_000_000:
        thousands, rest = divmod(value, 1000)
        prefix = _cardinal_sequence(thousands) + ("MIL",)
        if rest == 0:
            return prefix
        return prefix + _cardinal_sequence(rest)
    return (str(value),)


def _numeric_gloss_sequence(gloss: str) -> Optional[Tuple[str, ...]]:
    """Devuelve la secuencia posicional de una glosa numérica, si aplica."""
    if not gloss:
        return None
    key = gloss.strip().upper()
    if key in _NUMBER_WORD_EXPANSIONS:
        return _NUMBER_WORD_EXPANSIONS[key]
    digits = key.replace(".", "").replace(",", "")
    if digits.isdigit() and len(digits) <= 6:
        return _cardinal_sequence(int(digits))
    return None


_NUMBER_WORD_VALUES: Dict[str, int] = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
    "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14,
    "quince": 15, "dieciséis": 16, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21,
    "veintidós": 22, "veintidos": 22, "veintitrés": 23, "veintitres": 23,
    "veinticuatro": 24, "veinticinco": 25, "veintiséis": 26, "veintiseis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90,
    "cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300,
    "cuatrocientos": 400, "quinientos": 500, "quiniento": 500, "seiscientos": 600,
    "setecientos": 700, "ochocientos": 800, "novecientos": 900,
    "mil": 1000,
}


def _number_words_value(words: List[str]) -> Optional[int]:
    """Calcula el valor de una secuencia contigua de numerales escritos."""
    if not words:
        return None
    total = 0
    current = 0
    for raw in words:
        word = raw.lower()
        if word == "y":
            continue
        value = _NUMBER_WORD_VALUES.get(word)
        if value is None:
            return None
        if value == 1000:
            current = (current or 1) * 1000
            total += current
            current = 0
        else:
            current += value
    return total + current
