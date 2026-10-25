"""
Servicio Backend de Dactilología LSEC (30 Señas Oficiales — Guia-Uso-ilustraciones.pdf).

Codifica en el backend:
1. El catálogo oficial de los 30 grafemas del alfabeto manual ecuatoriano (Página 10):
   a, b, c, ch, d, e, f, g, h, i, j, k, l, ll, m, n, ñ, o, p, q, r, rr, s, t, u, v, w, x, y, z.
2. El tokenizador lingüístico NFC con detección prioritaria de dígrafos (CH, LL, RR),
   preservación de Ñ, mapeo de vocales tildadas/diéresis (Á, É, Í, Ó, Ú, Ü) y detección
   de letras idénticas consecutivas para micro-rearticulación espacial.
3. Carga y coarticulación en SO(3) de los 30 archivos físicos `animation.json` horneados
   en el catálogo v2.7 (`.dactilologia_v2.7/Letra <G>/animation.json` y
   `senas_vrm_dactilologia_v2.7/Letra <G>/animation.json`) con las 54 pistas óseas VRM 1.0
   y las 15 falanges de la mano derecha.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import external_path, settings

LSEC_FINGERSPELLING_GRAPHEMES: Tuple[str, ...] = (
    "A", "B", "C", "CH", "D",
    "E", "F", "G", "H", "I",
    "J", "K", "L", "LL", "M",
    "N", "Ñ", "O", "P", "Q",
    "R", "RR", "S", "T", "U",
    "V", "W", "X", "Y", "Z",
)

STATIC_GRAPHEMES = frozenset({
    "A", "B", "C", "D", "E", "F", "I", "L", "M",
    "N", "O", "R", "S", "T", "U", "V", "W", "Y",
})

DYNAMIC_GRAPHEMES = frozenset({
    "CH", "G", "H", "J", "K", "LL", "Ñ", "P", "Q", "RR", "X", "Z",
})

HUMAN_54_BONES: Tuple[str, ...] = (
    "hips", "spine", "chest", "upperChest", "neck", "head", "leftEye", "rightEye",
    "leftShoulder", "leftUpperArm", "leftLowerArm", "leftHand",
    "leftThumbMetacarpal", "leftThumbProximal", "leftThumbDistal",
    "leftIndexProximal", "leftIndexIntermediate", "leftIndexDistal",
    "leftMiddleProximal", "leftMiddleIntermediate", "leftMiddleDistal",
    "leftRingProximal", "leftRingIntermediate", "leftRingDistal",
    "leftLittleProximal", "leftLittleIntermediate", "leftLittleDistal",
    "rightShoulder", "rightUpperArm", "rightLowerArm", "rightHand",
    "rightThumbMetacarpal", "rightThumbProximal", "rightThumbDistal",
    "rightIndexProximal", "rightIndexIntermediate", "rightIndexDistal",
    "rightMiddleProximal", "rightMiddleIntermediate", "rightMiddleDistal",
    "rightRingProximal", "rightRingIntermediate", "rightRingDistal",
    "rightLittleProximal", "rightLittleIntermediate", "rightLittleDistal",
    "leftUpperLeg", "leftLowerLeg", "leftFoot", "leftToes",
    "rightUpperLeg", "rightLowerLeg", "rightFoot", "rightToes",
)

VOWEL_BASE_MAP: Dict[str, str] = {
    "Á": "A", "À": "A", "Ä": "A", "Â": "A",
    "É": "E", "È": "E", "Ë": "E", "Ê": "E",
    "Í": "I", "Ì": "I", "Ï": "I", "Î": "I",
    "Ó": "O", "Ò": "O", "Ö": "O", "Ô": "O",
    "Ú": "U", "Ù": "U", "Ü": "U", "Û": "U",
}

NEUTRAL_FINGERSPELLING_LOCUS: List[float] = [-0.172, 1.225, 0.215]
CHEST_SURFACE_Z: float = 0.1373
MIN_CHEST_CLEARANCE_M: float = 0.02

GRAPHEME_METADATA: Dict[str, Dict[str, Any]] = {
    "A": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": -6.0, "pitch_deg": 4.0, "roll_deg": 0.0},
    "B": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": 0.0, "pitch_deg": 4.0, "roll_deg": 0.0},
    "C": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": 48.0, "pitch_deg": 4.0, "roll_deg": 6.0},
    "CH": {"is_static": False, "opacity_mode": "TRANSITION_70_TO_100", "trajectory": "linear_left_to_right", "yaw_deg": -28.0, "pitch_deg": 10.0, "roll_deg": -74.0},
    "D": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": 34.0, "pitch_deg": 4.0, "roll_deg": 4.0},
    "E": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": -5.0, "pitch_deg": 5.0, "roll_deg": 0.0},
    "F": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": -14.0, "pitch_deg": 5.0, "roll_deg": 0.0},
    "G": {"is_static": False, "opacity_mode": "TRANSITION_70_TO_100", "trajectory": "linear_left_to_right", "yaw_deg": 24.0, "pitch_deg": 48.0, "roll_deg": -84.0},
    "H": {"is_static": False, "opacity_mode": "TRANSITION_70_TO_100", "trajectory": "linear_left_to_right", "yaw_deg": 24.0, "pitch_deg": 48.0, "roll_deg": -82.0},
    "I": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": -10.0, "pitch_deg": 4.0, "roll_deg": 0.0},
    "J": {"is_static": False, "opacity_mode": "TRANSITION_70_TO_100", "trajectory": "curved_j", "yaw_deg": -28.0, "pitch_deg": 14.0, "roll_deg": -14.0},
    "K": {"is_static": False, "opacity_mode": "TRANSITION_70_TO_100", "trajectory": "linear_bottom_to_top", "yaw_deg": -32.0, "pitch_deg": 8.0, "roll_deg": -10.0},
    "L": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": 0.0, "pitch_deg": 4.0, "roll_deg": 0.0},
    "LL": {"is_static": False, "opacity_mode": "TRANSITION_70_TO_100", "trajectory": "curved_left_to_right", "yaw_deg": -14.0, "pitch_deg": 6.0, "roll_deg": -6.0},
    "M": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": -10.0, "pitch_deg": 82.0, "roll_deg": -8.0},
    "N": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": -10.0, "pitch_deg": 82.0, "roll_deg": -8.0},
    "Ñ": {"is_static": False, "opacity_mode": "TRANSITION_70_TO_100", "trajectory": "curved_wavy", "yaw_deg": -20.0, "pitch_deg": 84.0, "roll_deg": -16.0},
    "O": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": 46.0, "pitch_deg": 4.0, "roll_deg": 6.0},
    "P": {"is_static": False, "opacity_mode": "TRANSITION_70_TO_100", "trajectory": "linear_top_to_bottom", "yaw_deg": -42.0, "pitch_deg": 42.0, "roll_deg": -56.0},
    "Q": {"is_static": False, "opacity_mode": "TRANSITION_70_TO_100", "trajectory": "linear_top_to_bottom", "yaw_deg": -24.0, "pitch_deg": 78.0, "roll_deg": -68.0},
    "R": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": -8.0, "pitch_deg": 4.0, "roll_deg": 0.0},
    "RR": {"is_static": False, "opacity_mode": "TRANSITION_70_TO_100", "trajectory": "curved_left_to_right", "yaw_deg": -18.0, "pitch_deg": 6.0, "roll_deg": -6.0},
    "S": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": -6.0, "pitch_deg": 4.0, "roll_deg": 0.0},
    "T": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": -10.0, "pitch_deg": 4.0, "roll_deg": 0.0},
    "U": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": -4.0, "pitch_deg": 4.0, "roll_deg": 0.0},
    "V": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": -4.0, "pitch_deg": 4.0, "roll_deg": 0.0},
    "W": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": -4.0, "pitch_deg": 4.0, "roll_deg": 0.0},
    "X": {"is_static": False, "opacity_mode": "TRANSITION_70_TO_100", "trajectory": "curved_displacement", "yaw_deg": -50.0, "pitch_deg": 14.0, "roll_deg": -12.0},
    "Y": {"is_static": True, "opacity_mode": "STATIC_100", "trajectory": "none", "yaw_deg": -8.0, "pitch_deg": 4.0, "roll_deg": 0.0},
    "Z": {"is_static": False, "opacity_mode": "TRANSITION_70_TO_100", "trajectory": "linear_zigzag_3seg", "yaw_deg": -24.0, "pitch_deg": 10.0, "roll_deg": -8.0},
}

_BAKED_DACT_DIRS: Tuple[Path, ...] = (
    external_path(settings.lsec_animations_v27_dir, "Diccionario LSEC/senas_vrm_standardized_v2.7") / ".dactilologia_v2.7",
    external_path("", "Diccionario LSEC/senas_vrm_dactilologia_v2.7"),
    external_path("", "senas_vrm_standardized_v2.7/.dactilologia_v2.7"),
    external_path("", "senas_vrm_dactilologia_v2.7"),
)

_baked_grapheme_cache: Dict[str, Dict[str, Any]] = {}


def _euler_deg_to_quat(x_deg: float, y_deg: float, z_deg: float) -> List[float]:
    rx = math.radians(x_deg) * 0.5
    ry = math.radians(y_deg) * 0.5
    rz = math.radians(z_deg) * 0.5
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    x = sx * cy * cz + cx * sy * sz
    y = cx * sy * cz - sx * cy * sz
    z = cx * cy * sz + sx * sy * cz
    w = cx * cy * cz - sx * sy * sz
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    return [round(x / n, 6), round(y / n, 6), round(z / n, 6), round(w / n, 6)]


def _slerp_quat_antipodal(q0: List[float], q1: List[float], t: float) -> List[float]:
    u = max(0.0, min(1.0, float(t)))
    x0, y0, z0, w0 = q0[0], q0[1], q0[2], q0[3]
    x1, y1, z1, w1 = q1[0], q1[1], q1[2], q1[3]
    dot = x0 * x1 + y0 * y1 + z0 * z1 + w0 * w1
    if dot < 0.0:
        dot = -dot
        x1, y1, z1, w1 = -x1, -y1, -z1, -w1
    if dot > 0.9995:
        rx = x0 + u * (x1 - x0)
        ry = y0 + u * (y1 - y0)
        rz = z0 + u * (z1 - z0)
        rw = w0 + u * (w1 - w0)
    else:
        theta_0 = math.acos(min(1.0, dot))
        theta = theta_0 * u
        sin_t0 = math.sin(theta_0) or 1.0
        s0 = math.cos(theta) - dot * math.sin(theta) / sin_t0
        s1 = math.sin(theta) / sin_t0
        rx = s0 * x0 + s1 * x1
        ry = s0 * y0 + s1 * y1
        rz = s0 * z0 + s1 * z1
        rw = s0 * w0 + s1 * w1
    n = math.sqrt(rx * rx + ry * ry + rz * rz + rw * rw) or 1.0
    return [round(rx / n, 6), round(ry / n, 6), round(rz / n, n and 6), round(rw / n, 6)]


def resolve_explicit_fingerspelling_grapheme(sign_or_gloss: str) -> Optional[str]:
    """Si la cadena representa un único grafema dactilológico ('Letra A', 'DACT_CH', 'Ñ'), devuelve el grafema canónico."""
    if not sign_or_gloss:
        return None
    s = unicodedata.normalize("NFC", sign_or_gloss.strip()).upper()
    m = re.match(r"^(?:LETRA|DACT|DACTILOLOGIA|DACTILOLOGÍA|FS)[\s:_-]+([A-ZÑ]{1,2})$", s)
    if m:
        cand = m.group(1)
        if cand == "NH":
            return "Ñ"
        if cand in GRAPHEME_METADATA:
            return cand
    if s in GRAPHEME_METADATA:
        return s
    return None


def get_baked_fingerspelling_folder(grapheme_or_sign: str) -> Optional[Path]:
    """Devuelve la carpeta física v2.7 (`Letra <G>`) para un grafema de dactilología."""
    g = resolve_explicit_fingerspelling_grapheme(grapheme_or_sign)
    if not g:
        return None
    folder_name = f"Letra {g}"
    for bdir in _BAKED_DACT_DIRS:
        if bdir and bdir.is_dir():
            for variant in (folder_name, unicodedata.normalize("NFC", folder_name), unicodedata.normalize("NFD", folder_name)):
                cand = bdir / variant
                if cand.is_dir() and (cand / "animation.json").is_file():
                    return cand
    return None


def load_baked_grapheme_animation(grapheme: str) -> Optional[Dict[str, Any]]:
    """Carga y cachea en memoria el archivo físico `animation.json` v2.7 de un grafema."""
    g = resolve_explicit_fingerspelling_grapheme(grapheme) or grapheme
    if g in _baked_grapheme_cache:
        return _baked_grapheme_cache[g]
    folder = get_baked_fingerspelling_folder(g)
    if folder and (folder / "animation.json").is_file():
        try:
            data = json.loads((folder / "animation.json").read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("frames"), list):
                _baked_grapheme_cache[g] = data
                return data
        except Exception:
            pass
    return None


def tokenize_lsec_fingerspelling(raw_input: str) -> List[Dict[str, Any]]:
    """
    Tokeniza una palabra, sigla o glosa deletreada detectando los dígrafos oficiales
    (CH, LL, RR) antes de dividir en letras individuales, preservando Ñ en NFC y
    mapeando vocales tildadas/diéresis a su vocal base.
    """
    if not raw_input or not isinstance(raw_input, str):
        return []
    cleaned = unicodedata.normalize("NFC", raw_input).strip().upper()
    cleaned = re.sub(r"^(DACTILOLOGIA|DACTILOLOGÍA|DACT|FS|LETRA)[\s:_-]+", "", cleaned, flags=re.IGNORECASE).strip()
    compact = re.sub(r"[\s\-_.]+", "", cleaned)
    if not compact:
        return []

    tokens: List[Dict[str, Any]] = []
    i = 0
    while i < len(compact):
        ch1 = compact[i]
        ch2 = compact[i + 1] if i + 1 < len(compact) else ""
        pair = ch1 + ch2
        if pair in ("CH", "LL", "RR"):
            prev = tokens[-1] if tokens else None
            is_rep = bool(prev and prev["grapheme"] == pair)
            tokens.append({
                "index": len(tokens),
                "grapheme": pair,
                "display_char": pair,
                "is_digraph": True,
                "is_static": False,
                "is_dynamic": True,
                "micro_rearticulation": is_rep,
            })
            i += 2
            continue

        mapped = VOWEL_BASE_MAP.get(ch1, ch1)
        if mapped in GRAPHEME_METADATA:
            meta = GRAPHEME_METADATA[mapped]
            prev = tokens[-1] if tokens else None
            is_rep = bool(prev and prev["grapheme"] == mapped)
            tokens.append({
                "index": len(tokens),
                "grapheme": mapped,
                "display_char": ch1,
                "is_digraph": False,
                "is_static": bool(meta["is_static"]),
                "is_dynamic": not bool(meta["is_static"]),
                "micro_rearticulation": is_rep,
            })
        i += 1

    return tokens


def format_lsec_fingerspelling_gloss(raw_word: str) -> str:
    """
    Formatea una palabra, nombre propio, sigla o término OOV como glosa dactilológica
    separada por guiones preservando los dígrafos oficiales LSEC (CH, LL, RR), la Ñ
    en NFC y las vocales tildadas/diéresis en su carácter visual.
    """
    tokens = tokenize_lsec_fingerspelling(raw_word)
    if not tokens:
        cleaned = unicodedata.normalize("NFC", (raw_word or "").strip().upper())
        letters = [c for c in cleaned if c.isalpha()]
        return "-".join(letters) if letters else cleaned
    return "-".join(t["display_char"] for t in tokens)


def count_lsec_fingerspelling_graphemes(raw_word_or_gloss: str) -> int:
    """Cuenta el número exacto de grafemas dactilológicos LSEC (CH, LL, RR cuentan como 1)."""
    tokens = tokenize_lsec_fingerspelling(raw_word_or_gloss)
    if tokens:
        return len(tokens)
    clean = re.sub(r"[^A-ZÁÉÍÓÚÜÑ]", "", unicodedata.normalize("NFC", (raw_word_or_gloss or "").upper()))
    return max(1, len(clean)) if clean else 0


def is_fingerspelling_query(gloss: str) -> bool:
    """Detecta si una consulta corresponde a dactilología letra por letra o grafema explícito."""
    s = unicodedata.normalize("NFC", (gloss or "").strip())
    if not s:
        return False
    upper = s.upper()
    if re.match(r"^(DACTILOLOGIA|DACTILOLOGÍA|DACT|FS|LETRA)[\s:_-]+", upper):
        return True
    if upper in LSEC_FINGERSPELLING_GRAPHEMES:
        return True
    if "-" in s:
        parts = [p.strip().upper() for p in s.split("-") if p.strip()]
        if len(parts) >= 2 and all(
            (len(p) == 1 and p.isalpha()) or p in ("CH", "LL", "RR")
            for p in parts
        ):
            return True
    return False


def _sample_baked_rotations_at(baked_frames: List[Dict[str, Any]], idx_float: float) -> Dict[str, List[float]]:
    n = len(baked_frames)
    if n == 0:
        return {b: [0.0, 0.0, 0.0, 1.0] for b in HUMAN_54_BONES}
    clamped = max(0.0, min(float(n - 1), idx_float))
    i0 = int(math.floor(clamped))
    i1 = min(n - 1, i0 + 1)
    alpha = clamped - i0
    r0 = baked_frames[i0].get("rotations") or {}
    r1 = baked_frames[i1].get("rotations") or {}
    if alpha <= 1e-5 or i0 == i1:
        return {b: list(r0.get(b, [0.0, 0.0, 0.0, 1.0])) for b in HUMAN_54_BONES}
    return {
        b: _slerp_quat_antipodal(
            r0.get(b, [0.0, 0.0, 0.0, 1.0]),
            r1.get(b, [0.0, 0.0, 0.0, 1.0]),
            alpha,
        )
        for b in HUMAN_54_BONES
    }


def synthesize_fingerspelling_animation(word_or_gloss: str, fps: int = 30) -> Dict[str, Any]:
    """
    Genera la estructura `animation.json` VRM 1.0 sobre los 54 huesos humanoides para
    una letra o palabra deletreada en dactilología LSEC, utilizando los archivos físicos
    horneados en v2.7 (`.dactilologia_v2.7/Letra <G>/animation.json`) con las 15 falanges
    de la mano derecha y coarticulación continua en SO(3) sin descenso al reposo intermedio.
    """
    tokens = tokenize_lsec_fingerspelling(word_or_gloss)
    if not tokens:
        tokens = tokenize_lsec_fingerspelling("A")

    first_baked = load_baked_grapheme_animation(tokens[0]["grapheme"])
    if first_baked is not None:
        if len(tokens) == 1:
            b_frames = first_baked["frames"]
            b_dur = float(first_baked.get("metadata", {}).get("duration") or 1.25)
            num_frames = max(15, int(round(b_dur * fps)) + 1)
            frames: List[Dict[str, Any]] = []
            for f_idx in range(num_frames):
                t = round(min(b_dur, f_idx / float(fps)), 4)
                u = f_idx / float(max(1, num_frames - 1))
                rot = _sample_baked_rotations_at(b_frames, u * (len(b_frames) - 1))
                frames.append({
                    "frame": f_idx,
                    "frame_index": f_idx,
                    "time": t,
                    "timestamp_sec": t,
                    "hipsPosition": [0.0, 0.907995, 0.003576],
                    "hips_position": [0.0, 0.907995, 0.003576],
                    "rotations": rot,
                    "expressions": dict(b_frames[0].get("expressions") or {"neutral": 1.0}),
                    "blendshapes": dict(b_frames[0].get("blendshapes") or {}),
                })
            meta = dict(first_baked.get("metadata") or {})
            meta.update({
                "signName": word_or_gloss,
                "pipelineVersion": "2.7_Estandarizado",
                "version_served": "2.7",
                "isFingerspelling": True,
                "bakedOnDisk": True,
                "fps": fps,
                "totalFrames": len(frames),
                "duration": b_dur,
                "durationSec": b_dur,
                "graphemes": [t["grapheme"] for t in tokens],
                "displayChars": [t["display_char"] for t in tokens],
                "tokens": tokens,
                "neutralLocus": NEUTRAL_FINGERSPELLING_LOCUS,
                "minChestClearanceM": MIN_CHEST_CLEARANCE_M,
            })
            return {
                "metadata": meta,
                "bones": list(HUMAN_54_BONES),
                "frames": frames,
                "stroke": first_baked.get("stroke"),
                "handStandardization": first_baked.get("handStandardization"),
            }

        # Palabra multi-grafema coarticulada en SO(3) usando los strokes horneados en disco
        prep_sec = 0.22
        per_letter_sec = 0.38
        trans_sec = 0.10
        rec_sec = 0.22
        body_sec = len(tokens) * per_letter_sec + (len(tokens) - 1) * trans_sec
        total_duration = round(prep_sec + body_sec + rec_sec, 4)
        num_frames = max(20, int(round(total_duration * fps)) + 1)

        baked_list = [load_baked_grapheme_animation(t["grapheme"]) or first_baked for t in tokens]
        last_baked = baked_list[-1]

        def _stroke_bounds(b_anim: Dict[str, Any]) -> Tuple[int, int]:
            st = b_anim.get("stroke") or b_anim.get("metadata", {}).get("stroke") or {}
            nf = len(b_anim.get("frames") or [])
            s_f = max(0, min(nf - 2, int(st.get("startFrame", int(nf * 0.22)))))
            e_f = max(s_f + 1, min(nf - 1, int(st.get("endFrame", int(nf * 0.78)))))
            return s_f, e_f

        frames = []
        for f_idx in range(num_frames):
            t = round(min(total_duration, f_idx / float(fps)), 4)
            if t < prep_sec:
                s0, _ = _stroke_bounds(baked_list[0])
                u_prep = t / max(1e-4, prep_sec)
                rot = _sample_baked_rotations_at(baked_list[0]["frames"], u_prep * s0)
            elif t > prep_sec + body_sec:
                _, e_last = _stroke_bounds(last_baked)
                nf_last = len(last_baked["frames"])
                u_rec = (t - (prep_sec + body_sec)) / max(1e-4, rec_sec)
                rot = _sample_baked_rotations_at(last_baked["frames"], e_last + u_rec * (nf_last - 1 - e_last))
            else:
                t_body = t - prep_sec
                stride = per_letter_sec + trans_sec
                k = min(len(tokens) - 1, int(t_body // stride))
                rem = t_body - k * stride
                b_cur = baked_list[k]
                s_c, e_c = _stroke_bounds(b_cur)
                if rem <= per_letter_sec or k == len(tokens) - 1:
                    u_hold = min(1.0, rem / max(1e-4, per_letter_sec))
                    rot = _sample_baked_rotations_at(b_cur["frames"], s_c + u_hold * (e_c - s_c))
                else:
                    u_tr = min(1.0, (rem - per_letter_sec) / max(1e-4, trans_sec))
                    smooth_u = 0.5 * (1.0 - math.cos(math.pi * u_tr))
                    b_next = baked_list[k + 1]
                    s_n, _ = _stroke_bounds(b_next)
                    r_end = _sample_baked_rotations_at(b_cur["frames"], float(e_c))
                    r_start = _sample_baked_rotations_at(b_next["frames"], float(s_n))
                    rot = {
                        b: _slerp_quat_antipodal(r_end[b], r_start[b], smooth_u)
                        for b in HUMAN_54_BONES
                    }
            frames.append({
                "frame": f_idx,
                "frame_index": f_idx,
                "time": t,
                "timestamp_sec": t,
                "hipsPosition": [0.0, 0.907995, 0.003576],
                "hips_position": [0.0, 0.907995, 0.003576],
                "rotations": rot,
                "expressions": {"neutral": 1.0, "aa": 0.0, "ih": 0.0, "ou": 0.0, "ee": 0.0, "oh": 0.0, "blink": 0.0, "blinkLeft": 0.0, "blinkRight": 0.0, "happy": 0.0, "angry": 0.0, "sad": 0.0, "relaxed": 0.0, "surprised": 0.0},
                "blendshapes": {},
            })

        return {
            "metadata": {
                "signName": word_or_gloss,
                "pipelineVersion": "2.7_Estandarizado",
                "version_served": "2.7",
                "pure1to1Copy": False,
                "isFingerspelling": True,
                "bakedOnDisk": True,
                "sourceDocument": "Guia-Uso-ilustraciones.pdf (Páginas 1-10)",
                "fps": fps,
                "totalFrames": len(frames),
                "duration": total_duration,
                "durationSec": total_duration,
                "graphemes": [t["grapheme"] for t in tokens],
                "displayChars": [t["display_char"] for t in tokens],
                "tokens": tokens,
                "neutralLocus": NEUTRAL_FINGERSPELLING_LOCUS,
                "minChestClearanceM": MIN_CHEST_CLEARANCE_M,
                "intraWordRestDrops": 0,
            },
            "bones": list(HUMAN_54_BONES),
            "frames": frames,
        }

    # Fallback analítico si no existen los archivos en disco
    per_letter_sec = 0.42
    total_duration = round(0.40 + len(tokens) * per_letter_sec, 4)
    num_frames = max(15, int(round(total_duration * fps)))
    base_rotations: Dict[str, List[float]] = {b: [0.0, 0.0, 0.0, 1.0] for b in HUMAN_54_BONES}
    base_rotations["leftUpperArm"] = [0.0435, 0.0028, -0.6087, 0.7921]
    base_rotations["leftLowerArm"] = [0.0, 0.0872, 0.0, 0.9962]
    base_rotations["rightShoulder"] = _euler_deg_to_quat(0.0, 3.0, -2.5)
    base_rotations["rightUpperArm"] = [-0.036, -0.052, 0.590, 0.805]
    base_rotations["rightLowerArm"] = [0.050, 0.745, 0.145, 0.648]

    frames = []
    for f_idx in range(num_frames):
        t = round(f_idx / float(fps), 4)
        u_global = f_idx / float(max(1, num_frames - 1))
        tok_pos = min(len(tokens) - 1, int(u_global * len(tokens)))
        tok = tokens[tok_pos]
        g_meta = GRAPHEME_METADATA[tok["grapheme"]]
        local_phase = (u_global * len(tokens)) - tok_pos
        rot = {k: list(v) for k, v in base_rotations.items()}
        dyn_mod = math.sin(math.pi * local_phase) if g_meta["is_static"] is False else 1.0
        rot["rightHand"] = _euler_deg_to_quat(
            g_meta["pitch_deg"] * (0.85 + 0.15 * dyn_mod),
            g_meta["yaw_deg"],
            g_meta["roll_deg"] * (0.85 + 0.15 * dyn_mod),
        )
        frames.append({
            "frame": f_idx,
            "frame_index": f_idx,
            "time": t,
            "timestamp_sec": t,
            "hipsPosition": [0.0, 0.908, 0.0036],
            "hips_position": [0.0, 0.908, 0.0036],
            "rotations": rot,
            "expressions": {"neutral": 0.95},
            "blendshapes": {},
        })

    return {
        "metadata": {
            "signName": word_or_gloss,
            "pipelineVersion": "1.0_Dactilologia_LSEC_PDF",
            "version_served": "2.7",
            "pure1to1Copy": False,
            "isFingerspelling": True,
            "sourceDocument": "Guia-Uso-ilustraciones.pdf (Páginas 1-10)",
            "fps": fps,
            "totalFrames": num_frames,
            "durationSec": total_duration,
            "graphemes": [t["grapheme"] for t in tokens],
            "displayChars": [t["display_char"] for t in tokens],
            "tokens": tokens,
            "neutralLocus": NEUTRAL_FINGERSPELLING_LOCUS,
            "minChestClearanceM": MIN_CHEST_CLEARANCE_M,
        },
        "frames": frames,
    }


def build_fingerspelling_catalog_payload() -> Dict[str, Any]:
    """Devuelve el catálogo completo auditable de los 30 grafemas LSEC incluyendo su estado horneado en disco v2.7."""
    baked_entries: Dict[str, Any] = {}
    for g in LSEC_FINGERSPELLING_GRAPHEMES:
        folder = get_baked_fingerspelling_folder(g)
        baked_entries[g] = {
            **GRAPHEME_METADATA[g],
            "sign_folder": f"Letra {g}",
            "gloss": f"DACT_{g}",
            "baked_v27_available": bool(folder and (folder / "animation.json").is_file()),
        }
    return {
        "total_graphemes": len(LSEC_FINGERSPELLING_GRAPHEMES),
        "graphemes": list(LSEC_FINGERSPELLING_GRAPHEMES),
        "static_graphemes": sorted(STATIC_GRAPHEMES),
        "dynamic_graphemes": sorted(DYNAMIC_GRAPHEMES),
        "neutral_locus_m": NEUTRAL_FINGERSPELLING_LOCUS,
        "min_chest_clearance_m": MIN_CHEST_CLEARANCE_M,
        "source_document": "Guia-Uso-ilustraciones.pdf (Páginas 1-10)",
        "baked_v27_count": sum(1 for v in baked_entries.values() if v["baked_v27_available"]),
        "catalog": baked_entries,
    }
