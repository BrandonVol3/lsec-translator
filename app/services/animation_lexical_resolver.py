"""
Resolutor Léxico y Morfológico LSEC sobre el Catálogo VRM en Disco (v2.7 / v2.6 / v2.5).

Indexa las carpetas reales normalizadas en NFC, desambigua homónimos, expande
variantes de género/número, resuelve alias gramaticales LSEC y derivaciones morfológicas
sin lanzar errores 404.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.services.animation_catalog_service import (
    get_sign_metadata,
    get_sign_stroke_entry,
    get_v25_dir,
    get_v26_dir,
    get_v27_dir,
    lsec_cnm,
    normalize_text,
)

logger = logging.getLogger(__name__)

_v26_lexical_index: Optional[Dict[str, Any]] = None

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
    "cientos": ("Cien", "synonym"), "ciento": ("Cien", "synonym"),
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
    results = [t]
    m = re.match(r"^(.+?)\((a|as|o|os|es)\)$", t, flags=re.IGNORECASE)
    if m:
        stem = m.group(1).strip()
        suf = m.group(2).lower()
        results = [stem]
        stem_low = stem.lower()
        if suf == "a":
            if stem_low.endswith("o"):
                results.append(stem[:-1] + "a")
            else:
                results.append(stem + "a")
        elif suf == "as":
            if stem_low.endswith("os"):
                results.append(stem[:-2] + "as")
                results.append(stem[:-1])
                results.append(stem[:-2] + "a")
            elif stem_low.endswith("o"):
                results.append(stem[:-1] + "a")
                results.append(stem + "s")
                results.append(stem[:-1] + "as")
            else:
                results.append(stem + "as")
        elif suf in ("o", "os"):
            results.append(stem + suf)
    return results


def parse_sign_title_tokens(folder_name: str) -> Tuple[List[str], List[str]]:
    """
    Extrae tokens de cabecera (head) y sinónimos/partes de un nombre de carpeta v2.6.
    Soporta separadores ',', '/', ';', doble espacio ('Escoger  Elegir'), signos '¿?¡!',
    sufijos '(1)', '__2' y expansiones de género '(a)', '(as)'.
    """
    cleaned = re.sub(r"[¿?¡!]", "", folder_name).strip()
    cleaned = re.sub(r"__\d+$", "", cleaned).strip()
    cleaned = re.sub(r"\(\d+\)$", "", cleaned).strip()

    if re.search(r",\s*a$", cleaned, flags=re.IGNORECASE):
        base = re.sub(r",\s*a$", "", cleaned, flags=re.IGNORECASE).strip()
        expanded = _expand_gender_token(f"{base}(a)")
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


def _build_v26_lexical_index() -> Dict[str, Any]:
    """Construye y cachea el índice completo sobre las carpetas reales de v2.7, v2.6 y v2.5."""
    global _v26_lexical_index
    if _v26_lexical_index is not None:
        return _v26_lexical_index

    v27_dir = get_v27_dir()
    v26_dir = get_v26_dir()
    v25_dir = get_v25_dir()

    qa_map: Dict[str, Dict[str, Any]] = {}
    qa_norm_map: Dict[str, Dict[str, Any]] = {}
    for qa_src_dir in (v26_dir, v27_dir):
        if qa_src_dir and (qa_src_dir / "qa_summary.csv").is_file():
            try:
                with open(qa_src_dir / "qa_summary.csv", "r", encoding="utf-8", errors="replace") as f:
                    for row in csv.DictReader(f):
                        s_name = unicodedata.normalize("NFC", (row.get("sign") or "").strip())
                        if s_name:
                            merged_row = dict(qa_map.get(s_name, {}))
                            merged_row.update({k: v for k, v in row.items() if v is not None and v != ""})
                            qa_map[s_name] = merged_row
                            qa_norm_map[normalize_text(s_name)] = merged_row
            except Exception as exc:
                logger.warning("No se pudo leer qa_summary.csv de %s: %s", qa_src_dir, exc)

    v27_folders: Dict[str, Path] = {}
    v26_folders: Dict[str, Path] = {}
    v25_folders: Dict[str, Path] = {}
    raw_v27_count = 0
    raw_v26_count = 0
    raw_v25_count = 0

    if v27_dir and v27_dir.is_dir():
        try:
            for entry in os.scandir(v27_dir):
                if entry.is_dir() and not entry.name.startswith("."):
                    anim_p = Path(entry.path) / "animation.json"
                    if anim_p.is_file():
                        raw_v27_count += 1
                        nfc_name = unicodedata.normalize("NFC", entry.name)
                        if nfc_name not in v27_folders or unicodedata.is_normalized("NFC", entry.name):
                            v27_folders[nfc_name] = Path(entry.path)
        except Exception as exc:
            logger.warning("Error escaneando v27_dir: %s", exc)

    if v26_dir and v26_dir.is_dir():
        try:
            for entry in os.scandir(v26_dir):
                if entry.is_dir() and not entry.name.startswith("."):
                    anim_p = Path(entry.path) / "animation.json"
                    if anim_p.is_file():
                        raw_v26_count += 1
                        nfc_name = unicodedata.normalize("NFC", entry.name)
                        if nfc_name not in v26_folders or unicodedata.is_normalized("NFC", entry.name):
                            v26_folders[nfc_name] = Path(entry.path)
        except Exception as exc:
            logger.warning("Error escaneando v26_dir: %s", exc)

    if v25_dir and v25_dir.is_dir():
        try:
            for entry in os.scandir(v25_dir):
                if entry.is_dir() and not entry.name.startswith("."):
                    anim_p = Path(entry.path) / "animation.json"
                    if anim_p.is_file():
                        raw_v25_count += 1
                        nfc_name = unicodedata.normalize("NFC", entry.name)
                        if nfc_name not in v25_folders or unicodedata.is_normalized("NFC", entry.name):
                            v25_folders[nfc_name] = Path(entry.path)
        except Exception as exc:
            logger.warning("Error escaneando v25_dir: %s", exc)

    all_canonical_names = sorted(set(v27_folders.keys()) | set(v26_folders.keys()) | set(v25_folders.keys()))

    exact_map: Dict[str, str] = {}
    head_map: Dict[str, List[str]] = {}
    part_map: Dict[str, List[str]] = {}

    for canonical in all_canonical_names:
        norm_full = normalize_text(canonical)
        if norm_full and norm_full not in exact_map:
            exact_map[norm_full] = canonical

        cleaned = re.sub(r"[¿?¡!]", "", canonical).strip()
        cleaned = re.sub(r"__\d+$", "", cleaned).strip()
        norm_cleaned = normalize_text(cleaned)
        if norm_cleaned and norm_cleaned not in exact_map:
            exact_map[norm_cleaned] = canonical

        heads, parts = parse_sign_title_tokens(canonical)
        for h in heads:
            nh = normalize_text(h)
            if nh:
                head_map.setdefault(nh, []).append(canonical)
        for p in parts:
            np = normalize_text(p)
            if np:
                part_map.setdefault(np, []).append(canonical)

    _v26_lexical_index = {
        "v27_folders": v27_folders,
        "v26_folders": v26_folders,
        "v25_folders": v25_folders,
        "qa_map": qa_map,
        "qa_norm_map": qa_norm_map,
        "exact_map": exact_map,
        "head_map": head_map,
        "part_map": part_map,
        "total_v27": raw_v27_count,
        "unique_v27": len(v27_folders),
        "total_v26": raw_v26_count,
        "unique_v26": len(v26_folders),
        "total_v25": raw_v25_count,
        "unique_v25": len(v25_folders),
    }
    logger.info(
        "✓ Índice léxico v2.7/v2.6 construido: %d carpetas v2.7, %d carpetas v2.6 (%d únicas NFC), %d exactas, %d cabeceras, %d partes",
        raw_v27_count,
        raw_v26_count,
        len(v26_folders),
        len(exact_map),
        len(head_map),
        len(part_map),
    )
    return _v26_lexical_index


def _select_best_candidate(norm_key: str, candidates: List[str], exact_map: Dict[str, str]) -> str:
    """Selecciona la mejor carpeta cuando existen múltiples variantes para un término."""
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
    s = (gloss or "").strip()
    if s.upper().startswith("FS:") or s.upper().startswith("DACT:"):
        return True
    if "-" in s:
        parts = [p.strip() for p in s.split("-") if p.strip()]
        if len(parts) >= 2 and all(len(p) == 1 and p.isalpha() for p in parts):
            return True
    return False


def resolve_gloss_to_sign(
    gloss: str,
    version: Optional[str] = "2.7",
    include_animation: bool = False,
) -> Dict[str, Any]:
    """
    Resuelve una glosa LSEC contra las carpetas reales del catálogo v2.7 (con respaldo v2.6 -> v2.5).
    Nunca lanza HTTPException 404; devuelve estructura trazable con:
      found, gloss, resolved_gloss, sign, match_type, status, needs_review, warning,
      version_served, is_fingerspelling, qa, animation (opcional).
    """
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
        return {
            "found": False,
            "gloss": clean_gloss,
            "resolved_gloss": None,
            "sign": None,
            "match_type": "fingerspelling",
            "status": "FINGERSPELLING",
            "needs_review": False,
            "warning": "Dactilología pendiente",
            "version_served": None,
            "is_fingerspelling": True,
            "qa": None,
            "animation": None,
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

    if not resolved_sign and norm_g in exact_map:
        resolved_sign = exact_map[norm_g]
        match_type = "exact"
        status_label = "EXACT"

    if not resolved_sign and norm_g in head_map:
        resolved_sign = _select_best_candidate(norm_g, head_map[norm_g], exact_map)
        match_type = "compound"
        status_label = "VARIANT"

    if not resolved_sign and norm_g in part_map:
        resolved_sign = _select_best_candidate(norm_g, part_map[norm_g], exact_map)
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
            with open(anim_path, "r", encoding="utf-8") as f:
                anim_payload = json.load(f)
            if isinstance(anim_payload, dict):
                cat_meta = get_sign_metadata(resolved_sign)
                if lsec_cnm is not None and not anim_payload.get("metadata", {}).get("nonManualStandard"):
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
                        meta["stroke"] = stroke_entry
                    if cat_meta and isinstance(cat_meta.get("hand_standardization"), dict):
                        h_std = dict(cat_meta["hand_standardization"])
                        if isinstance(meta.get("handStandardization"), dict):
                            h_std.update(meta["handStandardization"])
                        if "distance_reduction_pct" in h_std and "reduction_pct" not in h_std:
                            h_std["reduction_pct"] = h_std["distance_reduction_pct"]
                        meta["handStandardization"] = h_std
        except Exception as exc:
            logger.warning("Error leyendo animation.json en %s: %s", anim_path, exc)

    return {
        "found": True, "gloss": clean_gloss, "resolved_gloss": resolved_sign, "sign": resolved_sign,
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

    results: Dict[str, Dict[str, Any]] = {}
    items: List[Dict[str, Any]] = []
    exact_count, approx_count, review_count, fs_count, missing_count = 0, 0, 0, 0, 0

    for g in raw_glosses:
        g_str = str(g or "").strip()
        if not g_str:
            continue
        res = resolve_gloss_to_sign(g_str, version=version, include_animation=include_animation)
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
