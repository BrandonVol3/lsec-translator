"""
Reglas y utilidades de desambiguación léxica de homónimos y dominios restringidos LSEC (CONADIS / v2.7).

Garantiza que términos genéricos y lemas base nunca colisionen hacia acepciones restringidas
(", De " o acepciones ultra-especializadas) y permite la resolución contextual guiada por tokens.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Set, Tuple

# Las 23 carpetas estandarizadas en v2.7 que contienen calificadores de dominio explícitos ", De "
RESTRICTED_DOMAIN_QUALIFIERS_23: Tuple[str, ...] = (
    "Acuerdo, De acuerdo",
    "Babear, De atracción",
    "Blanco(a), De piel clara",
    "Buen provecho, De alimento",
    "Carrera, De autos",
    "Carrera, De competencia",
    "Explotar, De desahogarse",
    "Fácil, De expresión",
    "Igual, De idéntico",
    "Limpio, De honesto",
    "Llamar, De acudir",
    "Llamar, De teléfono",
    "Mayor, De grado",
    "Menos, De la matemáticas",
    "Menos, De menor cantidad",
    "Más, De comparación",
    "No, De negación",
    "Opción, De línea",
    "Polvo, De cosmético",
    "Ratón, De computador",
    "Receta, De médico",
    "Rápido(a), De velocidad",
    "Torre, De cd o dvd",
)

# Sustantivos invariables de 4 letras protegidos contra truncación espuria de '-a' (ej. cola != col)
SHIELDED_4LETTER_NOUNS: Set[str] = {
    "cola", "bota", "boda", "copa", "coca", "coma", "foca", "gota", "hoja", "joya",
    "lata", "luna", "masa", "mesa", "mota", "nota", "ola", "pera", "pila", "pipa",
    "rata", "rosa", "ruta", "sala", "sopa", "taza", "tela", "tiza", "vaca", "puma",
    "cuna", "fama", "lana", "lima", "mina", "mora", "pala", "papa", "rana", "tapa", "vela",
}

# Resoluciones canónicas por defecto para los términos base (evitando colisiones hacia dominios restringidos)
DEFAULT_BASE_RESOLUTIONS: Dict[str, str] = {
    "limpio": "Limpiar, Limpio",
    "menos": "Menos, De menor cantidad",
    "receta": "Receta, De médico",
    "carrera": "Carrera, Estudios",
    "blanco": "Blanco(a)",
    "blanca": "Blanco(a)",
    "explotar": "Explotar, Explosión",
    "polvo": "Polvo",
    "torre": "Torre",
    "babear": "Babear, Baboso(a)",
    "llamar": "Llamar, De acudir",
    "raton": "Ratón",
    "ratón": "Ratón",
    "facil": "Fácil",
    "fácil": "Fácil",
    "igual": "Igual",
    "mayor": "Mayor",
    "mas": "Más",
    "más": "Más",
    "no": "No, De negación",
    "opcion": "Alternativa, Opción",
    "opción": "Alternativa, Opción",
    "rapido": "Rápido(a), Un acontecimiento veloz",
    "rápido": "Rápido(a), Un acontecimiento veloz",
    "rapida": "Rápido(a), Un acontecimiento veloz",
    "rápida": "Rápido(a), Un acontecimiento veloz",
    "buen provecho": "Buen provecho",
    "acuerdo": "Acuerdo, De acuerdo",
    "banco": "Banco, Una institución financiera",
    "planta": "Planta",
    "medio": "Mitad",
    "cura": "Curar, Curación",
    "curas": "Curar, Curación",
    "registrar": "Inscribir, Inscripción",
    "registro": "Inscribir, Inscripción",
    "automovilismo": "Carrera, De autos",
    "educacion": "Educación",
    "educación": "Educación",
    "formacion": "Formación, Manualidad",
    "formación": "Formación, Manualidad",
    "seguro": "Seguro",
    "fuerte": "Fuerte, Fuerza, Poder",
    "persona": "Persona",
    "poder": "Poder",
    "querer": "Querer",
    "con": "Con, Con(1)",
    "si": "SÍ",
    "sí": "SÍ",
    "dia": "Día",
    "día": "Día",
    "ano": "Año",
    "año": "Año",
}

# Reglas de desambiguación contextual: (sign_target, keywords)
_CONTEXTUAL_RULES: Dict[str, List[Tuple[str, Set[str]]]] = {
    "raton": [
        ("Ratón, De computador", {
            "computador", "computadora", "pc", "mouse", "tecnologia", "teclado", "pantalla",
            "oficina", "informatica", "software", "hardware", "usb", "clic", "escritorio",
        }),
        ("Ratón", {"animal", "roedor", "queso", "gato", "trampa", "campo", "cueva"}),
    ],
    "llamar": [
        ("Llamar, De teléfono", {
            "telefono", "celular", "whatsapp", "llamada", "timbre", "marcar", "linea",
            "movil", "numero", "contactar", "contacto", "telefonico", "telefonica", "hablar",
        }),
        ("Llamar, De acudir", {
            "acudir", "venir", "persona", "gritar", "atencion", "llamar", "acercarse", "nombre",
        }),
    ],
    "carrera": [
        ("Carrera, De autos", {
            "auto", "autos", "coche", "coches", "automovil", "automovilismo", "formula",
            "pista", "rally", "piloto", "velocidad", "carreras", "motor", "circuito",
        }),
        ("Carrera, De competencia", {
            "atletismo", "correr", "maraton", "competencia", "velocidad", "deporte", "atleta",
            "meta", "carrera pedestre", "100 metros",
        }),
        ("Carrera, Estudios", {
            "estudios", "universidad", "academico", "upec", "grado", "profesion", "titulo",
            "licenciatura", "ingenieria", "estudiante", "facultad", "asignatura",
        }),
    ],
    "receta": [
        ("Receta, Recetario de cocina", {
            "cocina", "cocinar", "comida", "ingredientes", "plato", "chef", "gastronomia",
            "alimento", "recetario", "sabor", "preparacion", "hornear", "sopa", "postre",
        }),
        ("Receta, De médico", {
            "medico", "salud", "enfermedad", "farmacia", "medicamento", "pastilla", "medicina",
            "doctor", "prescripcion", "clinica", "hospital", "tratamiento", "dosis", "remedio",
        }),
    ],
    "limpio": [
        ("Limpio, De honesto", {
            "honesto", "honradez", "integridad", "transparente", "corrupcion", "moral", "etico",
            "etica", "virtud", "conducta", "justo", "recto",
        }),
        ("Limpiar, Limpio", {
            "aseo", "higiene", "lavar", "suciedad", "agua", "casa", "bano", "limpiar",
            "mancha", "ropa", "piso", "desinfectar", "jabon",
        }),
    ],
    "menos": [
        ("Menos, De la matemáticas", {
            "matematicas", "resta", "restar", "signo", "calculo", "aritmetica", "ecuacion",
            "operacion", "signos", "algebra", "numero",
        }),
        ("Menos, De menor cantidad", {
            "cantidad", "poco", "menor", "reducir", "disminuir", "escaso", "bajar",
            "comparacion", "mas o menos", "minimo", "porcentaje",
        }),
    ],
    "blanco": [
        ("Blanco(a), De piel clara", {
            "piel", "tez", "raza", "persona blanca", "etnia", "clara", "rubio", "caucasico", "caucásico",
        }),
        ("Blanco(a)", {
            "color", "pintura", "pared", "hoja", "camisa", "ropa", "blanco", "blanca", "tiza",
        }),
    ],
    "explotar": [
        ("Explotar, De desahogarse", {
            "desahogo", "desahogarse", "llanto", "ira", "rabia", "emocional", "sentimientos",
            "estres", "crisis", "llorar", "gritar",
        }),
        ("Explotar, Explosión", {
            "bomba", "dinamita", "volcan", "mina", "detonacion", "fuego", "explosion", "estallar",
        }),
    ],
    "babear": [
        ("Babear, De atracción", {
            "atraccion", "atractivo", "enamorar", "gustar", "linda", "guapo", "chica", "chico",
            "amor", "belleza", "deseo", "guapa",
        }),
        ("Babear, Baboso(a)", {
            "saliva", "boca", "fisiologico", "bebe", "dormir", "babas", "baba", "enfermo",
        }),
    ],
    "torre": [
        ("Torre, De cd o dvd", {
            "cd", "dvd", "disco", "discos", "estuche", "grabadora", "cdrom",
        }),
        ("Torre", {
            "edificio", "construccion", "arquitectura", "campus", "torre eiffel", "castillo",
            "antena", "piso",
        }),
    ],
    "polvo": [
        ("Polvo, De cosmético", {
            "cosmetico", "maquillaje", "cara", "rostro", "belleza", "polvera", "maquillar",
        }),
        ("Polvo", {
            "tierra", "suciedad", "aire", "viento", "limpiar", "polvareda", "suelo", "barrer",
        }),
    ],
    "cura": [
        ("Papa, Cura", {
            "iglesia", "sacerdote", "papa", "religion", "misa", "catolico", "parroco",
            "templo", "fe", "dios", "obispo", "clero", "parroquia",
        }),
        ("Curar, Curación", {
            "medico", "salud", "enfermedad", "remedio", "sanar", "medicina", "curacion",
            "tratamiento", "hospital", "clinica", "doctor", "herida", "dolor", "paciente",
        }),
    ],
    "curas": [
        ("Papa, Cura", {
            "iglesia", "sacerdote", "papa", "religion", "misa", "catolico", "parroco",
            "templo", "fe", "dios", "obispo", "clero", "parroquia",
        }),
        ("Curar, Curación", {
            "medico", "salud", "enfermedad", "remedio", "sanar", "medicina", "curacion",
            "tratamiento", "hospital", "clinica", "doctor", "herida", "dolor", "paciente",
        }),
    ],
    "registrar": [
        ("Registro Civil", {
            "civil", "cedula", "partida", "nacimiento", "matrimonio", "defuncion",
            "identidad", "registro civil", "tramite civil",
        }),
        ("Inscribir, Inscripción", {
            "universidad", "academico", "estudiante", "curso", "materia", "alumno",
            "admision", "periodo", "evaluacion", "upec", "aspirante", "postular", "inscribir",
        }),
    ],
    "medio": [
        ("Medioambiente", {
            "ambiente", "medioambiente", "ecologia", "naturaleza", "verde", "planeta",
            "contaminacion", "sostenible", "arboles", "tierra",
        }),
        ("Medianoche, Mediodía", {
            "medianoche", "mediodia", "noche", "dia", "doce", "hora", "reloj",
        }),
        ("Mitad", {
            "mitad", "promedio", "parte", "dividido", "centro", "repartir", "porcion",
        }),
    ],
    "cola": [
        ("Fila", {"fila", "espera", "personas", "turno", "banco", "hacer fila", "gente"}),
        ("Pegar", {"pegar", "adhesivo", "goma", "carpinteria", "papel", "resistol"}),
        ("Destapar, Gaseosa", {"gaseosa", "refresco", "bebida", "soda", "coca cola", "tomar"}),
    ],
    "banco": [
        ("Banco, Una institución financiera", {
            "dinero", "cuenta", "plata", "credito", "finanzas", "financiero", "prestamo",
            "pago", "bancario", "tarjeta", "cajero", "transferencia", "deposito", "matricula",
        }),
        ("Banco", {
            "parque", "sentar", "sentarse", "asiento", "madera", "plaza", "banca",
        }),
    ],
    "planta": [
        ("Piso, Planta de edificio", {
            "edificio", "piso", "primera", "segunda", "baja", "arquitectura", "campus",
            "aula", "oficina", "nivel",
        }),
        ("Planta", {
            "hoja", "verde", "flor", "vegetal", "semilla", "arbol", "raiz", "regar",
            "jardin", "botanica", "maceta",
        }),
    ],
}


def _norm_clean(text: str) -> str:
    """Normaliza texto eliminando acentos y puntuación."""
    if not text:
        return ""
    t = unicodedata.normalize("NFD", text.lower().replace("ñ", "\ue000"))
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn").replace("\ue000", "ñ")
    return " ".join(re.sub(r"[\W_]+", " ", t).split())


def _extract_context_tokens(context: Optional[str | Sequence[str]]) -> Set[str]:
    """Extrae un conjunto de tokens normalizados a partir de una cadena o secuencia de contexto."""
    if not context:
        return set()
    tokens: Set[str] = set()
    if isinstance(context, str):
        for w in _norm_clean(context).split():
            if len(w) >= 2:
                tokens.add(w)
    elif isinstance(context, (list, tuple, set)):
        for item in context:
            for w in _norm_clean(str(item)).split():
                if len(w) >= 2:
                    tokens.add(w)
    return tokens


def resolve_homonym_with_context(
    term: str,
    context: Optional[str | Sequence[str]] = None,
) -> Optional[str]:
    """
    Resuelve un homónimo hacia su seña canónica óptima basándose en el contexto temático.
    Si no hay contexto o no coincide ninguna regla especializada, retorna la preferencia por defecto.
    """
    key = _norm_clean(term)
    if not key:
        return None

    ctx_tokens = _extract_context_tokens(context)
    if ctx_tokens and key in _CONTEXTUAL_RULES:
        best_candidate: Optional[str] = None
        best_score = 0
        for target_sign, keywords in _CONTEXTUAL_RULES[key]:
            score = sum(1 for kw in keywords if kw in ctx_tokens or any(kw in tok for tok in ctx_tokens))
            if score > best_score:
                best_score = score
                best_candidate = target_sign
        if best_candidate and best_score > 0:
            return best_candidate

    return DEFAULT_BASE_RESOLUTIONS.get(key)


def get_conadis_homonym_priority(title: str, form: str) -> Optional[int]:
    """
    Determina la prioridad de indexación en CONADIS para títulos polémicos o con ', De '.
    Retorna 1 (prioridad alta / genérica) o 3 (restringida / despriorizada) para resolver colisiones.
    """
    t_clean = _norm_clean(title)
    f_clean = _norm_clean(form)

    # 1. Menos
    if f_clean == "menos":
        if "menor cantidad" in t_clean:
            return 1
        if "matematicas" in t_clean:
            return 3

    # 2. Receta
    if f_clean == "receta":
        if "medico" in t_clean:
            return 1
        if "cocina" in t_clean or "recetario" in t_clean:
            return 3

    # 3. Limpio
    if f_clean == "limpio":
        if "limpiar" in t_clean or t_clean == "limpiar limpio":
            return 1
        if "honesto" in t_clean:
            return 3

    # 4. Carrera
    if f_clean == "carrera":
        if "estudios" in t_clean:
            return 1
        if "autos" in t_clean or "competencia" in t_clean:
            return 3

    # 5. Ratón
    if f_clean == "raton":
        if t_clean == "raton":
            return 1
        if "computador" in t_clean:
            return 3

    # 6. Blanco
    if f_clean in ("blanco", "blanca"):
        if "piel clara" in t_clean:
            return 3
        if "blanco" in t_clean:
            return 1

    # 7. Explotar
    if f_clean == "explotar":
        if "explosion" in t_clean:
            return 1
        if "desahogarse" in t_clean:
            return 3

    # 8. Babear
    if f_clean == "babear":
        if "baboso" in t_clean:
            return 1
        if "atraccion" in t_clean:
            return 3

    # 9. Torre
    if f_clean == "torre":
        if t_clean == "torre":
            return 1
        if "cd" in t_clean or "dvd" in t_clean:
            return 3

    # 10. Polvo
    if f_clean == "polvo":
        if t_clean == "polvo":
            return 1
        if "cosmetico" in t_clean:
            return 3

    # 11. Llamar
    if f_clean == "llamar":
        if "acudir" in t_clean:
            return 1
        if "telefono" in t_clean:
            return 3

    # 12. Mayor
    if f_clean == "mayor":
        if t_clean == "mayor":
            return 1
        if "grado" in t_clean:
            return 3

    # 13. Más
    if f_clean == "mas":
        if t_clean == "mas":
            return 1
        if "comparacion" in t_clean:
            return 3

    # 14. Opción
    if f_clean in ("opcion", "alternativa"):
        if "linea" in t_clean:
            return 3
        if "alternativa" in t_clean or t_clean == "opcion":
            return 1

    # 15. Rápido
    if f_clean in ("rapido", "rapida"):
        if "velocidad" in t_clean:
            return 3
        if "acontecimiento" in t_clean or "rapido" in t_clean:
            return 1

    # 16. Fácil
    if f_clean == "facil":
        if "expresion" in t_clean:
            return 3
        if t_clean == "facil":
            return 1

    # 17. Igual
    if f_clean == "igual":
        if "identico" in t_clean:
            return 3
        if t_clean == "igual":
            return 1

    # 18. Buen provecho
    if f_clean == "buen provecho":
        if "alimento" in t_clean:
            return 3
        if t_clean == "buen provecho":
            return 1

    # 19. Cura / Curas
    if f_clean in ("cura", "curas"):
        if "curar" in t_clean or "curacion" in t_clean:
            return 1
        if "papa" in t_clean or "sacerdote" in t_clean:
            return 3

    return None


def is_shielded_4letter_noun(norm: str) -> bool:
    """Verifica si un término corresponde a un sustantivo invariable de 4 letras protegido."""
    return norm.lower() in SHIELDED_4LETTER_NOUNS


def is_restricted_domain_folder(folder_name: str) -> bool:
    """Determina si un nombre de carpeta corresponde a una acepción restringida (con ', De ')."""
    return bool(re.search(r",\s*de\s+", folder_name, flags=re.IGNORECASE))
