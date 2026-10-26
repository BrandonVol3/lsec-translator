"""
Resolutor Léxico y Morfológico LSEC sobre el Catálogo VRM en Disco (v2.7 / v2.6 / v2.5).

Indexa las carpetas reales normalizadas en NFC, desambigua homónimos, expande
variantes de género/número, resuelve alias gramaticales LSEC y derivaciones morfológicas
sin lanzar errores 404.
"""

from __future__ import annotations

import copy
import csv
import functools
import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.services.animation_catalog_service import (
    ensure_sign_animation_stabilized,
    get_sign_metadata,
    get_sign_stroke_entry,
    get_v25_dir,
    get_v26_dir,
    get_v27_dir,
    lsec_cnm,
    normalize_text,
)
from app.services.animation_fingerspelling_service import (
    is_fingerspelling_query, synthesize_fingerspelling_animation, tokenize_lsec_fingerspelling,
)

logger = logging.getLogger(__name__)

_v26_lexical_index: Optional[Dict[str, Any]] = None


@functools.lru_cache(maxsize=256)
def _load_raw_animation_json_cached(path_str: str, mtime_ns: int) -> Dict[str, Any]:
    """Lee un archivo animation.json desde disco con caché LRU en memoria validada por mtime_ns."""
    with open(path_str, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}

# Preferencias explícitas para homónimos con calificadores de dominio en el catálogo
_PREFERRED_HOMONYMS: Dict[str, str] = {
    "carrera": "Carrera, Estudios", "opcion": "Alternativa, Opción",
    "educacion": "Educación", "formacion": "Formación, Manualidad",
    "seguro": "Seguro", "fuerte": "Fuerte, Fuerza, Poder",
    "persona": "Persona", "poder": "Poder", "querer": "Querer",
    "mas": "Más", "con": "Con, Con(1)", "no": "No, De negación",
    "si": "SÍ", "dia": "Día", "ano": "Año", "facil": "Fácil",
}

# Alias léxicos y gramaticales LSEC hacia entradas reales de las 5,061 carpetas v2.6
_LSEC_LEXICAL_ALIASES: Dict[str, Tuple[str, str]] = {
    "pro1": ("Yo", "synonym"), "pro1pl": ("Nosotros(as)", "synonym"),
    "pro2": ("Tú", "synonym"), "pro2pl": ("Ustedes", "synonym"),
    "pro2mismo": ("Por sí mismo(a)", "synonym"), "pro3": ("El, Ella", "synonym"),
    "pro3pl": ("Ellos, ellas", "synonym"), "esaspersonas": ("Ellos, ellas", "synonym"),
    "eso": ("Este", "synonym"), "esto": ("Este", "synonym"),
    "ese": ("Este", "synonym"), "esa": ("Este", "synonym"),
    "esta": ("Este", "synonym"), "aquel": ("Este", "synonym"), "aquella": ("Este", "synonym"),
    "masde": ("Más", "synonym"), "solamenteno": ("Solo", "synonym"), "solamente": ("Solo", "synonym"),
    "aqui": ("Abajo, Aquí", "compound"), "hoy": ("Ahora", "synonym"),
    "nadie": ("Ninguno(a)", "synonym"), "entre": ("Mitad", "synonym"),
    "junto": ("Juntar, Juntos", "lemma"), "juntos": ("Juntar, Juntos", "compound"),
    "primero": ("Primer", "lemma"), "primera": ("Primer", "lemma"),
    "4500": ("Mil", "synonym"), "8": ("Ocho", "synonym"), "60": ("Sesenta", "synonym"),
    "3000": ("Tres mil", "synonym"), "3200": ("Tres mil", "synonym"),
    "2800": ("Dos mil", "synonym"), "90": ("Noventa", "synonym"),
    "cinco": ("Cinco mil", "synonym"), "5": ("Cinco mil", "synonym"),
    "cero": ("Nada", "synonym"), "0": ("Nada", "synonym"),
    "quinientos": ("Quinientos", "synonym"), "quinientas": ("Quinientos", "synonym"),
    "cientos": ("Cien", "synonym"), "ciento": ("Cien", "synonym"),
    "proposito": ("Objetivo", "synonym"), "politecnica": ("Universidad", "synonym"),
    "politecnico": ("Universidad", "synonym"), "liderar": ("Jefe(a)", "synonym"),
    "lider": ("Jefe(a)", "synonym"), "liderazgo": ("Jefe(a)", "synonym"),
    "estudiantil": ("Estudiante", "synonym"), "quinto": ("Cinco mil", "synonym"),
    "quinta": ("Cinco mil", "synonym"), "registro": ("Inscribir, Inscripción", "synonym"),
    "actualizado": ("Actualización", "lemma"), "actualizada": ("Actualización", "lemma"),
    "actualizar": ("Actualización", "lemma"), "espacio": ("Local, Lugar", "synonym"),
    "universitario": ("Universidad", "synonym"), "universitaria": ("Universidad", "synonym"),
    "por": ("Por eso", "synonym"), "seguir": ("Continuar", "synonym"),
    "intentar": ("Esforzarse, Esfuerzo", "synonym"), "requerido": ("Requisito", "lemma"),
    "requerida": ("Requisito", "lemma"), "requerir": ("Requisito", "lemma"),
    "quedar": ("Quedarse, permanecer en un lugar", "lemma"), "ningun": ("Ninguno(a)", "lemma"),
    "practica": ("Practicar", "lemma"), "presente": ("En presencia", "synonym"),
    "muestra": ("Mostrar", "lemma"), "artificial": ("Robot", "approximate"),
    "hacia": ("Ir", "synonym"), "admision": ("Inscribir, Inscripción", "synonym"),
    "whatsapp": ("Mensaje", "synonym"), "arroba": ("Correo electrónico", "synonym"),
    "edu": ("Educación", "synonym"), "ec": ("Ecuador", "synonym"),
    "central": ("Centro", "lemma"), "gran": ("Grande", "lemma"),
    "joven": ("Joven, Juventud", "synonym"), "jovenes": ("Joven, Juventud", "synonym"),
    "inscribete": ("Inscribir", "synonym"), "inscribirse": ("Inscribir", "synonym"),
    "inscribir": ("Inscribir", "synonym"), "tecnologico": ("Tecnología", "synonym"),
    "tecnologia": ("Tecnología", "synonym"), "evaluacion": ("Examinar, Evaluar", "synonym"),
    "aspirante": ("Aspirar", "synonym"), "periodo": ("Período de tiempo, Transcurrir", "synonym"),
    "deber": ("Deberes", "synonym"), "hora": ("¿Qué hora es", "synonym"),
    "informacion": ("Extraer información", "synonym"), "iniciar": ("Empezar", "synonym"),
    "registrar": ("Registro Civil", "synonym"), "opcionar": ("Alternativa, Opción", "synonym"),
    "oferta": ("Ofrecer", "synonym"), "taller": ("Curso", "synonym"),
    "dificil": ("Difícil", "synonym"), "diseno": ("Dibujar", "synonym"),
    "dominar": ("Saber", "synonym"), "constante": ("Siempre", "synonym"),
    "integracion": ("Integrar", "synonym"), "modalidad": ("Forma", "synonym"),
    "presencial": ("En presencia", "synonym"), "desarrollo": ("Desarrollar", "synonym"),
    "sostenible": ("Cuidar", "synonym"), "semipresencial": ("En presencia", "synonym"),
    "seartesarrobaupecedues": ("Correo electrónico", "synonym"), "correo": ("Correo electrónico", "synonym"),
    "academico": ("Carrera, Estudios", "synonym"), "academica": ("Carrera, Estudios", "synonym"),
    "campus": ("Universidad", "synonym"), "conocimiento": ("Conocer", "lemma"),
    "conocimientos": ("Conocer", "lemma"), "destacar": ("Importante", "synonym"),
    "determinada": ("Decidir, Decisión", "synonym"), "determinado": ("Decidir, Decisión", "synonym"),
    "determinar": ("Decidir, Decisión", "synonym"), "educar": ("Educación", "lemma"),
    "excelencia": ("Excelente", "lemma"), "formar": ("Formación, Manualidad", "lemma"),
    "incluir": ("Inclusión", "lemma"), "innovacion": ("Nuevo(a)", "synonym"),
    "innovar": ("Nuevo(a)", "synonym"), "inspirar": ("Imaginar", "synonym"),
    "inspiracion": ("Imaginar", "synonym"), "liberar": ("Libertad, Libre", "lemma"),
    "obstaculo": ("Barrera", "synonym"), "obstaculos": ("Barrera", "synonym"),
    "orgullo": ("Orgulloso(a)", "lemma"), "preparacion": ("Preparar", "lemma"),
    "publica": ("Público, Pueblo", "lemma"), "publico": ("Público, Pueblo", "compound"),
    "realidad": ("Real", "lemma"), "sostenibilidad": ("Cuidar", "synonym"),
    "superar": ("Mejor, Mejorar", "synonym"), "trato": ("Tratar", "lemma"),
    "tratos": ("Tratar", "lemma"), "cercano": ("Cerca", "lemma"),
    "cercana": ("Cerca", "lemma"), "cercania": ("Cerca", "lemma"),
    "porcentaje": ("Porcentaje", "synonym"), "porciento": ("Porcentaje", "synonym"),
    "lugar": ("Local, Lugar", "synonym"), "puntaje": ("Punto", "synonym"),
    "promedio": ("Promedio", "synonym"), "minimo": ("Mínimo", "synonym"),
    "ingenieria": ("Ingeniero(a)", "synonym"), "computacion": ("Computadora", "synonym"),
    "enfermeria": ("Enfermera", "synonym"), "agropecuaria": ("Agricultor(a), Agricultura", "synonym"),
    "inicial": ("Primer", "synonym"), "exterior": ("Fuera", "synonym"),
    "comercio": ("Comerciar, Compartir", "synonym"), "nivelacion": ("Comenzar, Empezar", "synonym"),
    "cronograma": ("Horario, Cronograma", "synonym"), "semestre": ("Semestre", "synonym"),
    "facultad": ("Facultad", "synonym"), "secretaria": ("Secretario(a)", "synonym"),
    "coordinador": ("Coordinador(a)", "synonym"), "rector": ("Rector(a)", "synonym"),
    "directora": ("Director(a)", "synonym"), "docente": ("Docente", "synonym"),
    "becario": ("Beca", "synonym"), "matricula": ("Matrícula", "synonym"),
    "certificado": ("Certificado, Certificar", "synonym"), "comprobante": ("Certificado, Certificar", "synonym"),
    "carpeta": ("Carpeta", "synonym"), "requisito": ("Requisito", "synonym"),
    "preferir": ("Preferir", "synonym"), "solicitar": ("Solicitud", "synonym"),
    "reunir": ("Reunirse, Reunión", "synonym"), "fortalecer": ("Fuerte, Fuerza, Poder", "synonym"),
    "legalizar": ("Poder legal", "synonym"), "financiar": ("Banco, Una institución financiera", "synonym"),
    "postular": ("Inscribir, Inscripción", "synonym"), "debatir": ("Discutir", "synonym"),
    "cubrir": ("Cubrir", "synonym"), "alcanzar": ("Alcanzar", "synonym"),
    "preocupar": ("Preocuparse", "synonym"), "fallar": ("Falla", "synonym"),
    "plataforma": ("Computadora", "approximate"), "tarea": ("Oficio, Trabajo", "synonym"),
    "internet": ("Computadora", "approximate"), "duda": ("Dudar", "synonym"),
    "dificultad": ("Difícil", "synonym"), "rendimiento": ("Mejor, Mejorar", "approximate"),
    "bienestar": ("Salud, Saludable", "synonym"), "movilidad": ("Movilización, Transporte, Viático", "synonym"),
    "entusiasmo": ("Emoción, Entusiasmarse, Simpático", "synonym"), "equipamiento": ("Equipo", "synonym"),
    "intercultural": ("Cultura", "approximate"), "linguistico": ("Lingüista", "synonym"),
    "linguistica": ("Lingüista", "synonym"), "antiguedad": ("Antiguo(a)", "synonym"),
    "prestigio": ("Importante", "approximate"), "frontera": ("Frontera", "synonym"),
    "mutuamente": ("Juntar, Juntos", "synonym"), "alguien": ("Algunos(as)", "approximate"),
}


def _expand_gender_token(token: str) -> List[str]:
    """Expande sufijos de género/número como Bueno(a) -> ['Bueno', 'Buena'] o Nosotros(as)."""
    t = token.strip()
    if not t:
        return []
    m = re.match(r"^(.+?)\((a|as|o|os|es)\)$", t, flags=re.IGNORECASE)
    if not m:
        return [t]
    stem, suf = m.group(1).strip(), m.group(2).lower()
    stem_low = stem.lower()
    if suf == "a":
        return [stem, (stem[:-1] if stem_low.endswith("o") else stem) + "a"]
    if suf == "as":
        if stem_low.endswith("os"):
            return [stem, stem[:-2] + "as", stem[:-1], stem[:-2] + "a"]
        if stem_low.endswith("o"):
            return [stem, stem[:-1] + "a", stem + "s", stem[:-1] + "as"]
        return [stem, stem + "as"]
    return [stem, stem + suf] if suf in ("o", "os") else [stem]


def parse_sign_title_tokens(folder_name: str) -> Tuple[List[str], List[str]]:
    """Extrae tokens de cabecera (head) y sinónimos/partes de un nombre de carpeta v2.6."""
    cleaned = re.sub(r"\(\d+\)$", "", re.sub(r"__\d+$", "", re.sub(r"[¿?¡!]", "", folder_name).strip()).strip()).strip()
    if re.search(r",\s*a$", cleaned, flags=re.IGNORECASE):
        expanded = _expand_gender_token(f"{re.sub(r',\s*a$', '', cleaned, flags=re.IGNORECASE).strip()}(a)")
        return expanded, expanded
    raw_parts = [p.strip() for p in re.split(r"[,/;]|\s{2,}", cleaned) if p.strip()]
    head_tokens: List[str] = []
    all_tokens: List[str] = []
    for idx, part in enumerate(raw_parts):
        part_clean = re.sub(r"\(\d+\)$", "", part).strip()
        part_no_desc = re.sub(r"\([^)]{3,}\)", "", part_clean).strip()
        candidates = _expand_gender_token(part_clean)
        if part_no_desc and part_no_desc != part_clean:
            candidates.extend(_expand_gender_token(part_no_desc))
        for cand in candidates:
            if idx == 0 and cand not in head_tokens:
                head_tokens.append(cand)
            if cand not in all_tokens:
                all_tokens.append(cand)
    return head_tokens, all_tokens


def _scan_anim_folders(base_dir: Optional[Path]) -> Tuple[Dict[str, Path], int]:
    """Escanea un directorio de animaciones VRM y devuelve el mapa NFC -> Path junto al conteo bruto."""
    folders: Dict[str, Path] = {}
    raw_count = 0
    if base_dir and base_dir.is_dir():
        try:
            for entry in os.scandir(base_dir):
                if entry.is_dir() and not entry.name.startswith(".") and (Path(entry.path) / "animation.json").is_file():
                    raw_count += 1
                    nfc_name = unicodedata.normalize("NFC", entry.name)
                    if nfc_name not in folders or unicodedata.is_normalized("NFC", entry.name):
                        folders[nfc_name] = Path(entry.path)
        except Exception as exc:
            logger.warning("Error escaneando %s: %s", base_dir, exc)
    return folders, raw_count


def _build_v26_lexical_index() -> Dict[str, Any]:
    """Construye y cachea el índice completo sobre las carpetas reales de v2.7, v2.6 y v2.5."""
    global _v26_lexical_index
    if _v26_lexical_index is not None:
        return _v26_lexical_index
    v27_dir, v26_dir, v25_dir = get_v27_dir(), get_v26_dir(), get_v25_dir()
    qa_map: Dict[str, Dict[str, Any]] = {}
    qa_norm_map: Dict[str, Dict[str, Any]] = {}
    for qa_src_dir in (v26_dir, v27_dir):
        if qa_src_dir and (qa_src_dir / "qa_summary.csv").is_file():
            try:
                with open(qa_src_dir / "qa_summary.csv", "r", encoding="utf-8", errors="replace") as f:
                    for row in csv.DictReader(f):
                        s_name = unicodedata.normalize("NFC", (row.get("sign") or "").strip())
                        if s_name:
                            merged_row = dict(qa_map.get(s_name, {}), **{k: v for k, v in row.items() if v is not None and v != ""})
                            qa_map[s_name] = merged_row
                            qa_norm_map[normalize_text(s_name)] = merged_row
            except Exception as exc:
                logger.warning("No se pudo leer qa_summary.csv de %s: %s", qa_src_dir, exc)

    v27_folders, raw_v27_count = _scan_anim_folders(v27_dir)
    v26_folders, raw_v26_count = _scan_anim_folders(v26_dir)
    v25_folders, raw_v25_count = _scan_anim_folders(v25_dir)
    all_canonical_names = sorted(set(v27_folders) | set(v26_folders) | set(v25_folders))
    exact_map: Dict[str, str] = {}
    head_map: Dict[str, List[str]] = {}
    part_map: Dict[str, List[str]] = {}
    for canonical in all_canonical_names:
        for variant_str in (canonical, re.sub(r"__\d+$", "", re.sub(r"[¿?¡!]", "", canonical).strip()).strip()):
            nk = normalize_text(variant_str)
            if nk and nk not in exact_map:
                exact_map[nk] = canonical
        heads, parts = parse_sign_title_tokens(canonical)
        for h in heads:
            if normalize_text(h):
                head_map.setdefault(normalize_text(h), []).append(canonical)
        for p in parts:
            if normalize_text(p):
                part_map.setdefault(normalize_text(p), []).append(canonical)

    _v26_lexical_index = {
        "v27_folders": v27_folders, "v26_folders": v26_folders, "v25_folders": v25_folders,
        "qa_map": qa_map, "qa_norm_map": qa_norm_map, "exact_map": exact_map, "head_map": head_map, "part_map": part_map,
        "total_v27": raw_v27_count, "unique_v27": len(v27_folders), "total_v26": raw_v26_count, "unique_v26": len(v26_folders),
        "total_v25": raw_v25_count, "unique_v25": len(v25_folders),
    }
    logger.info("✓ Índice léxico v2.7/v2.6 construido: %d carpetas v2.7, %d carpetas v2.6 (%d únicas NFC)", raw_v27_count, raw_v26_count, len(v26_folders))
    return _v26_lexical_index


def _select_best_candidate(
    norm_key: str,
    candidates: List[str],
    exact_map: Dict[str, str],
    preferred_geolect: Optional[str] = None,
) -> str:
    """Selecciona la mejor carpeta cuando existen múltiples variantes para un término."""
    if preferred_geolect:
        g_low = preferred_geolect.strip().lower()
        if g_low in ("sierra", "costa"):
            for c in candidates:
                c_low = c.lower()
                if f"({g_low})" in c_low or f"en la {g_low}" in c_low:
                    return c
    if norm_key in _PREFERRED_HOMONYMS:
        pref = _PREFERRED_HOMONYMS[norm_key]
        for c in candidates:
            if unicodedata.normalize("NFC", c) == unicodedata.normalize("NFC", pref):
                return c
        for c in candidates:
            if normalize_text(c) == normalize_text(pref):
                return c
    if norm_key in exact_map and exact_map[norm_key] in candidates:
        return exact_map[norm_key]
    scored = sorted(
        candidates,
        key=lambda c: (
            1 if re.search(r",\s*de\s+", c, flags=re.IGNORECASE) else 0,
            len(c),
            c.lower(),
        ),
    )
    return scored[0]


def _generate_morphological_candidates(gloss: str) -> List[str]:
    """Genera candidatos morfológicos (lemas verbales, nominalizaciones, género y número)."""
    norm = normalize_text(gloss)
    if not norm or len(norm) < 3:
        return []

    cands: List[str] = []

    def _add(val: str):
        nv = normalize_text(val)
        if nv and nv != norm and nv not in cands:
            cands.append(nv)

    try:
        from app.services.text_normalizer import SpanishVerbLexicon
        inf = SpanishVerbLexicon.get_infinitive(gloss.lower())
        if inf:
            _add(inf)
    except Exception:
        pass

    if norm.endswith("amiento"):
        _add(norm[:-7] + "ar")
    if norm.endswith("imiento"):
        _add(norm[:-7] + "ir")
        _add(norm[:-7] + "er")
    if norm.endswith("cimiento"):
        _add(norm[:-8] + "cer")
    if norm.endswith("acion"):
        _add(norm[:-5] + "ar")
    if norm.endswith("icion"):
        _add(norm[:-5] + "ir")
    if norm.endswith("sion"):
        _add(norm[:-4] + "ir")
        _add(norm[:-4] + "dir")
        _add(norm[:-4] + "tir")
    if norm.endswith("ar") and len(norm) > 4:
        _add(norm[:-2] + "acion")
        _add(norm[:-2] + "o")
    if norm.endswith("ir") and len(norm) > 4:
        _add(norm[:-2] + "icion")
        _add(norm[:-3] + "sion") if norm.endswith("uir") else None

    if norm.endswith("idad") and len(norm) > 6:
        _add(norm[:-4])
        _add(norm[:-4] + "o")
    if norm.endswith("encia") and len(norm) > 6:
        _add(norm[:-5] + "ente")
    if norm.endswith("ancia") and len(norm) > 6:
        _add(norm[:-5] + "ante")
    if norm.endswith("ullo"):
        _add(norm[:-1] + "oso")
    if norm.endswith("ero"):
        _add(norm[:-1])

    if norm.endswith("es") and len(norm) > 4:
        _add(norm[:-2])
        _add(norm[:-1])
    if norm.endswith("s") and len(norm) > 3:
        _add(norm[:-1])
        if norm.endswith("as"):
            _add(norm[:-2] + "o")
            _add(norm[:-2] + "os")
    if norm.endswith("ano") and len(norm) > 5:
        _add(norm[:-3] + "a")
    if norm.endswith("ana") and len(norm) > 5:
        _add(norm[:-3] + "a")
    if norm.endswith("a") and len(norm) > 3:
        _add(norm[:-1] + "o")
        _add(norm[:-1])
    if norm.endswith("o") and len(norm) > 3:
        _add(norm[:-1] + "a")
        _add(norm[:-1])
        _add(norm[:-1] + "ar")

    if norm.endswith("ado") and len(norm) > 5:
        _add(norm[:-3] + "ar")
    if norm.endswith("ada") and len(norm) > 5:
        _add(norm[:-3] + "ar")
        _add(norm[:-1] + "o")
    if norm.endswith("ido") and len(norm) > 5:
        _add(norm[:-3] + "er")
        _add(norm[:-3] + "ir")

    return cands


def _is_fingerspelling_gloss(gloss: str) -> bool:
    """Detecta si una glosa corresponde a dactilología letra por letra (ej. G-U-A-Y-A-Q-U-I-L, U-P-E-C)."""
    return is_fingerspelling_query(gloss)


def resolve_gloss_to_sign(
    gloss: str,
    version: Optional[str] = "2.7",
    include_animation: bool = False,
    geolect: Optional[str] = None,
    preferred_geolect: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resuelve una glosa LSEC contra las carpetas reales del catálogo v2.7 (con respaldo v2.6 -> v2.5).
    Nunca lanza HTTPException 404; devuelve estructura trazable con:
      found, gloss, resolved_gloss, sign, match_type, status, needs_review, warning,
      version_served, is_fingerspelling, qa, animation (opcional).
    """
    geolect = geolect or preferred_geolect
    clean_gloss = (gloss or "").strip()
    if not clean_gloss:
        return {
            "found": False,
            "gloss": "",
            "resolved_gloss": None,
            "sign": None,
            "match_type": "none",
            "status": "EMPTY",
            "needs_review": False,
            "warning": "Glosa vacía",
            "version_served": None,
            "is_fingerspelling": False,
            "qa": None,
            "animation": None,
        }
    base_gloss_match = re.match(r"^(.+?)\[[^\]]+\]$", clean_gloss)
    lookup_gloss = base_gloss_match.group(1).strip() if base_gloss_match else clean_gloss

    idx = _build_v26_lexical_index()
    exact_map: Dict[str, str] = idx["exact_map"]
    head_map: Dict[str, List[str]] = idx["head_map"]
    part_map: Dict[str, List[str]] = idx["part_map"]
    v27_folders: Dict[str, Path] = idx.get("v27_folders", {})
    v26_folders: Dict[str, Path] = idx["v26_folders"]
    v25_folders: Dict[str, Path] = idx["v25_folders"]
    qa_map: Dict[str, Dict[str, Any]] = idx["qa_map"]
    qa_norm_map: Dict[str, Dict[str, Any]] = idx["qa_norm_map"]

    if _is_fingerspelling_gloss(lookup_gloss):
        fs_tokens = tokenize_lsec_fingerspelling(lookup_gloss)
        return {
            "found": False, "gloss": clean_gloss, "resolved_gloss": None, "sign": None,
            "match_type": "fingerspelling", "status": "FINGERSPELLING", "needs_review": False,
            "warning": None, "version_served": "2.7", "is_fingerspelling": True,
            "graphemes": [t["grapheme"] for t in fs_tokens], "tokens": fs_tokens, "qa": None,
            "animation": synthesize_fingerspelling_animation(clean_gloss) if include_animation else None,
        }

    norm_g = normalize_text(lookup_gloss)
    resolved_sign: Optional[str] = None
    match_type: str = "none"
    status_label: str = "MISSING"

    if norm_g in _PREFERRED_HOMONYMS:
        pref = _PREFERRED_HOMONYMS[norm_g]
        if pref in v27_folders or pref in v26_folders or pref in v25_folders:
            resolved_sign = pref
            match_type = "exact" if normalize_text(pref) == norm_g else "compound"
            status_label = "EXACT" if match_type == "exact" else "VARIANT"

    if not resolved_sign and geolect and norm_g in head_map:
        g_low = geolect.strip().lower()
        if g_low in ("sierra", "costa"):
            for cand in head_map[norm_g]:
                if f"({g_low})" in cand.lower() or f"en la {g_low}" in cand.lower():
                    resolved_sign = cand
                    match_type = "compound"
                    status_label = "VARIANT"
                    break

    if not resolved_sign and norm_g in exact_map:
        resolved_sign = exact_map[norm_g]
        match_type = "exact"
        status_label = "EXACT"

    if not resolved_sign and norm_g in head_map:
        resolved_sign = _select_best_candidate(norm_g, head_map[norm_g], exact_map, preferred_geolect=geolect)
        match_type = "compound"
        status_label = "VARIANT"

    if not resolved_sign and norm_g in part_map:
        resolved_sign = _select_best_candidate(norm_g, part_map[norm_g], exact_map, preferred_geolect=geolect)
        match_type = "compound"
        status_label = "VARIANT"

    if not resolved_sign:
        try:
            from app.services.dictionary_service import get_dictionary_service
            dict_svc = get_dictionary_service()
            entry = dict_svc.lookup_gloss(lookup_gloss)
            if entry:
                for cand_title in [entry.title, entry.head_word] + list(entry.synonyms or []):
                    nc = normalize_text(cand_title)
                    if not nc:
                        continue
                    if nc in exact_map:
                        resolved_sign = exact_map[nc]
                        match_type = "compound"
                        status_label = "DICTIONARY"
                        break
                    if nc in head_map:
                        resolved_sign = _select_best_candidate(nc, head_map[nc], exact_map)
                        match_type = "compound"
                        status_label = "DICTIONARY"
                        break
                    if nc in part_map:
                        resolved_sign = _select_best_candidate(nc, part_map[nc], exact_map)
                        match_type = "compound"
                        status_label = "DICTIONARY"
                        break
        except Exception as exc:
            logger.debug("LSECDictionaryService lookup fallo para %s: %s", clean_gloss, exc)

    if not resolved_sign and norm_g in _LSEC_LEXICAL_ALIASES:
        alias_target, alias_mtype = _LSEC_LEXICAL_ALIASES[norm_g]
        nt = normalize_text(alias_target)
        if alias_target in v27_folders or alias_target in v26_folders or alias_target in v25_folders:
            resolved_sign = alias_target
            match_type = alias_mtype
            status_label = "ALIAS" if alias_mtype == "synonym" else "APPROXIMATE"
        elif nt in exact_map:
            resolved_sign = exact_map[nt]
            match_type = alias_mtype
            status_label = "ALIAS" if alias_mtype == "synonym" else "APPROXIMATE"
        elif nt in part_map:
            resolved_sign = _select_best_candidate(nt, part_map[nt], exact_map)
            match_type = alias_mtype
            status_label = "ALIAS" if alias_mtype == "synonym" else "APPROXIMATE"

    if not resolved_sign:
        for morph_norm in _generate_morphological_candidates(lookup_gloss):
            if morph_norm in _PREFERRED_HOMONYMS:
                resolved_sign = _PREFERRED_HOMONYMS[morph_norm]
                match_type = "lemma"
                status_label = "APPROXIMATE"
                break
            if morph_norm in exact_map:
                resolved_sign = exact_map[morph_norm]
                match_type = "lemma"
                status_label = "APPROXIMATE"
                break
            if morph_norm in head_map:
                resolved_sign = _select_best_candidate(morph_norm, head_map[morph_norm], exact_map)
                match_type = "lemma"
                status_label = "APPROXIMATE"
                break
            if morph_norm in part_map:
                resolved_sign = _select_best_candidate(morph_norm, part_map[morph_norm], exact_map)
                match_type = "lemma"
                status_label = "APPROXIMATE"
                break

    if not resolved_sign and "-" in lookup_gloss:
        sub_tokens = [t.strip() for t in lookup_gloss.split("-") if len(t.strip()) >= 2]
        for sub_tok in sub_tokens:
            sub_res = resolve_gloss_to_sign(sub_tok, version=version, include_animation=False)
            if sub_res.get("found"):
                resolved_sign = sub_res["sign"]
                match_type = "synonym"
                status_label = "APPROXIMATE"
                break

    if not resolved_sign:
        return {
            "found": False,
            "gloss": clean_gloss,
            "resolved_gloss": None,
            "sign": None,
            "match_type": "none",
            "status": "MISSING",
            "needs_review": False,
            "warning": f"Sin animación en catálogo v2.7/v2.6 para '{lookup_gloss}'",
            "version_served": None,
            "is_fingerspelling": False,
            "qa": None,
            "animation": None,
        }

    anim_path: Optional[Path] = None
    version_served = "2.7"
    if version == "2.5":
        if resolved_sign in v25_folders:
            anim_path = v25_folders[resolved_sign] / "animation.json"
            version_served = "2.5"
    elif version == "2.6":
        if resolved_sign in v26_folders:
            anim_path = v26_folders[resolved_sign] / "animation.json"
            version_served = "2.6"
        elif resolved_sign in v25_folders:
            anim_path = v25_folders[resolved_sign] / "animation.json"
            version_served = "2.5"
    else:
        if resolved_sign in v27_folders:
            anim_path = v27_folders[resolved_sign] / "animation.json"
            version_served = "2.7"
        elif resolved_sign in v26_folders:
            anim_path = v26_folders[resolved_sign] / "animation.json"
            version_served = "2.6"
        elif resolved_sign in v25_folders:
            anim_path = v25_folders[resolved_sign] / "animation.json"
            version_served = "2.5"

    if not anim_path or not anim_path.is_file():
        return {
            "found": False,
            "gloss": clean_gloss,
            "resolved_gloss": resolved_sign,
            "sign": resolved_sign,
            "match_type": "none",
            "status": "MISSING",
            "needs_review": False,
            "warning": f"Archivo animation.json ausente para '{resolved_sign}'",
            "version_served": None,
            "is_fingerspelling": False,
            "qa": None,
            "animation": None,
        }

    qa_row = qa_map.get(resolved_sign) or qa_norm_map.get(normalize_text(resolved_sign)) or {}
    needs_review = str(qa_row.get("needs_review", "False")).lower() == "true"

    warning_msg: Optional[str] = None
    if match_type not in ("exact", "compound"):
        warning_msg = f"⚠ Aprox: {resolved_sign}" + (" · Revisión QA" if needs_review else "")
    elif needs_review:
        warning_msg = f"⚠ Revisión: {resolved_sign}"

    stroke_entry: Optional[Dict[str, Any]] = get_sign_stroke_entry(resolved_sign) if version_served == "2.7" else None

    anim_payload: Optional[Dict[str, Any]] = None
    if include_animation:
        try:
            stat_res = anim_path.stat()
            cached_anim = _load_raw_animation_json_cached(str(anim_path), int(stat_res.st_mtime_ns))
            anim_payload = copy.deepcopy(cached_anim)
            if isinstance(anim_payload, dict) and anim_payload:
                cat_meta = get_sign_metadata(resolved_sign)
                cnm_ver = getattr(lsec_cnm, "CNM_STANDARD_VERSION", "1.1")
                if lsec_cnm is not None and anim_payload.get("metadata", {}).get("nonManualStandard", {}).get("version") != cnm_ver:
                    lsec_cnm.standardize_animation_dict(
                        anim_payload, sign_name=resolved_sign, catalog_entry=cat_meta
                    )
                meta = anim_payload.setdefault("metadata", {})
                meta["version_served"] = version_served
                meta["resolved_sign"] = resolved_sign
                meta["match_type"] = match_type
                meta["status_label"] = status_label
                meta["needs_review"] = needs_review
                if version_served == "2.7":
                    meta["pipelineVersion"] = "2.7_Estandarizado"
                    if stroke_entry:
                        existing_stroke = meta.get("stroke") if isinstance(meta.get("stroke"), dict) else {}
                        merged_stroke = dict(stroke_entry)
                        merged_stroke.update(existing_stroke)
                        meta["stroke"] = merged_stroke
                    if cat_meta and isinstance(cat_meta.get("hand_standardization"), dict):
                        h_std = dict(cat_meta["hand_standardization"])
                        if isinstance(meta.get("handStandardization"), dict):
                            h_std.update(meta["handStandardization"])
                        if "distance_reduction_pct" in h_std and "reduction_pct" not in h_std:
                            h_std["reduction_pct"] = h_std["distance_reduction_pct"]
                        meta["handStandardization"] = h_std
                    ensure_sign_animation_stabilized(
                        anim_payload,
                        sign_name=resolved_sign,
                        anim_file=anim_path,
                        cat_meta=cat_meta,
                        persist_to_disk=True,
                    )
                    if isinstance(meta.get("stroke"), dict):
                        stroke_entry = meta["stroke"]
        except Exception as exc:
            logger.warning("Error leyendo animation.json en %s: %s", anim_path, exc)

    res_low = resolved_sign.lower()
    resolved_geolect = (
        "Sierra" if ("(sierra)" in res_low or "en la sierra" in res_low)
        else ("Costa" if ("(costa)" in res_low or "en la costa" in res_low) else "Nacional")
    )
    return {
        "found": True, "gloss": clean_gloss, "resolved_gloss": resolved_sign, "sign": resolved_sign,
        "geolect": resolved_geolect,
        "match_type": match_type, "status": status_label, "needs_review": needs_review,
        "warning": warning_msg, "version_served": version_served, "is_fingerspelling": False,
        "anim_path": str(anim_path), "stroke": stroke_entry,
        "qa": {
            "needs_review": needs_review, "review_reasons": qa_row.get("review_reasons", ""),
            "duration": float(qa_row.get("duration", 0.0) or 0.0), "fps": float(qa_row.get("fps", 60.0) or 60.0),
            "frames": int(float(qa_row.get("frames", 0) or 0)), "hand_std_status": qa_row.get("hand_std_status", ""),
            "bimanual_mode": qa_row.get("bimanual_mode", ""), "frames_modified": int(float(qa_row.get("frames_modified", 0) or 0)),
        },
        "animation": anim_payload,
    }


def resolve_batch_glosses_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Resuelve un lote de glosas LSEC contra el catálogo v2.7/v2.6 y construye el resumen de cobertura."""
    raw_glosses = payload.get("glosses") or []
    version = payload.get("version") or "2.7"
    include_animation = bool(payload.get("include_animation", False))
    geolect = payload.get("geolect")

    results: Dict[str, Dict[str, Any]] = {}
    items: List[Dict[str, Any]] = []
    exact_count, approx_count, review_count, fs_count, missing_count = 0, 0, 0, 0, 0

    for g in raw_glosses:
        g_str = str(g or "").strip()
        if not g_str:
            continue
        res = resolve_gloss_to_sign(g_str, version=version, include_animation=include_animation, geolect=geolect)
        res.pop("anim_path", None)
        results[g_str] = res
        items.append(res)
        if res["found"]:
            if res["match_type"] in ("exact", "compound"):
                exact_count += 1
            else:
                approx_count += 1
            if res["needs_review"]:
                review_count += 1
        elif res["is_fingerspelling"]:
            fs_count += 1
        else:
            missing_count += 1

    return {
        "version": version, "results": results, "items": items,
        "summary": {
            "total": len(items), "resolved": exact_count + approx_count,
            "exact_or_compound": exact_count, "approximate": approx_count,
            "needs_review": review_count, "fingerspelling": fs_count, "missing": missing_count,
        },
    }


def build_animation_catalog_contract() -> Dict[str, Any]:
    """Construye el manifiesto estable de versiones disponibles para /api/v1/animations/catalog."""
    index = _build_v26_lexical_index()
    version_specs = (
        ("2.7", get_v27_dir(), "2.7_Estandarizado", "total_v27"),
        ("2.6", get_v26_dir(), "2.6_Directo_1a1_corregido", "total_v26"),
        ("2.5", get_v25_dir(), "2.5_Directo_1a1", "total_v25"),
    )
    versions = []
    for version, directory, pipeline_version, total_key in version_specs:
        versions.append(
            {
                "version": version,
                "pipeline_version": pipeline_version,
                "available": directory is not None and directory.is_dir(),
                "directory": str(directory) if directory else None,
                "total_signs": int(index.get(total_key, 0)),
                "selection": "default" if version == settings.default_animation_version else "fallback",
            }
        )

    default_version = settings.default_animation_version
    default_entry = next(item for item in versions if item["version"] == default_version)
    return {
        "catalog_version": "1.0.0",
        "default_version": default_version,
        "default_available": default_entry["available"],
        "versions": versions,
        "resolution_order": ["2.7", "2.6", "2.5"],
        "contract": {
            "animation_file": "animation.json",
            "version_field": "metadata.version_served",
            "pipeline_field": "metadata.pipelineVersion",
        },
    }
