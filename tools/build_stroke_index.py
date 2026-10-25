#!/usr/bin/env python3
"""
tools/build_stroke_index.py
Generador offline del índice de trazos activos (stroke_index.json) para las 4,142 señas
del catálogo LSEC v2.7 (senas_vrm_standardized_v2.7).

Características:
- Analiza ambas cadenas cinemáticas completas (hombro -> brazo -> antebrazo -> muñeca -> 15 huesos de dedos)
  más cabeza/torso/expresiones para señas faciales (solo_rostro).
- Detecta la ventana activa [strokeStart, strokeEnd] por salida de zona de reposo y velocidad angular
  con histéresis (Schmitt trigger), sin el límite antiguo de >1.25s ni el filtro de solo 4 huesos.
- Identifica manos activas por cadena (left, right, dominant); si una mano permanece en reposo durante
  todo el clip, su pose de ancla inicial y final se fija al reposo canónico (REST_POSE).
- Calcula poses de ancla inicial/final y velocidades angulares en bordes (en rad/s en el espacio tangente
  so(3) y magnitud en deg/s) para coarticulación C¹ Hermite / minimum-jerk.
- NO modifica ningún archivo animation.json original en disco.
- Produce el índice completo stroke_index.json y el informe QA con histogramas y las 50 señas de menor
  confianza para revisión manual.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import math
import os
from pathlib import Path
import random
import sys
import time
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Constantes de Esqueleto VRM y Reposo Canónico
# ---------------------------------------------------------------------------

LEFT_ARM_BONES: List[str] = ["leftShoulder", "leftUpperArm", "leftLowerArm", "leftHand"]
RIGHT_ARM_BONES: List[str] = ["rightShoulder", "rightUpperArm", "rightLowerArm", "rightHand"]

FINGER_SUFFIXES: List[str] = [
    "ThumbMetacarpal", "ThumbProximal", "ThumbDistal",
    "IndexProximal", "IndexIntermediate", "IndexDistal",
    "MiddleProximal", "MiddleIntermediate", "MiddleDistal",
    "RingProximal", "RingIntermediate", "RingDistal",
    "LittleProximal", "LittleIntermediate", "LittleDistal",
]

LEFT_FINGER_BONES: List[str] = [f"left{s}" for s in FINGER_SUFFIXES]
RIGHT_FINGER_BONES: List[str] = [f"right{s}" for s in FINGER_SUFFIXES]

LEFT_CHAIN_BONES: List[str] = LEFT_ARM_BONES + LEFT_FINGER_BONES
RIGHT_CHAIN_BONES: List[str] = RIGHT_ARM_BONES + RIGHT_FINGER_BONES
TORSO_HEAD_BONES: List[str] = ["hips", "spine", "chest", "neck", "head"]

ALL_TRACKED_BONES: List[str] = TORSO_HEAD_BONES + LEFT_CHAIN_BONES + RIGHT_CHAIN_BONES

CANONICAL_REST_POSE: Dict[str, List[float]] = {
    "leftUpperArm": [0.0435, 0.0028, -0.6087, 0.7921],
    "rightUpperArm": [0.0435, -0.0028, 0.6087, 0.7921],
    "leftLowerArm": [0.0, 0.0872, 0.0, 0.9962],
    "rightLowerArm": [0.0, -0.0872, 0.0, 0.9962],
}
for _b in ALL_TRACKED_BONES:
    if _b not in CANONICAL_REST_POSE:
        CANONICAL_REST_POSE[_b] = [0.0, 0.0, 0.0, 1.0]

CANONICAL_REST_NP: Dict[str, np.ndarray] = {
    k: np.asarray(v, dtype=np.float64) for k, v in CANONICAL_REST_POSE.items()
}


# ---------------------------------------------------------------------------
# Álgebra de Cuaterniones y Espacio Tangente so(3)
# ---------------------------------------------------------------------------

def quat_normalize_batch(q: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(q, axis=-1, keepdims=True)
    safe = np.where(norms > 1e-12, norms, 1.0)
    ident = np.zeros_like(q)
    ident[..., 3] = 1.0
    return np.where(norms > 1e-12, q / safe, ident)


def enforce_antipodal_continuity(q_seq: np.ndarray) -> np.ndarray:
    """Asegura norma unitaria y <q[t], q[t-1]> >= 0 a lo largo del eje temporal 0."""
    out = quat_normalize_batch(np.asarray(q_seq, dtype=np.float64).copy())
    for t in range(1, out.shape[0]):
        dots = np.sum(out[t] * out[t - 1], axis=-1)
        flip = dots < 0.0
        if np.any(flip):
            out[t, flip] = -out[t, flip]
    return out


def quat_angle_deg_batch(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    dots = np.clip(np.abs(np.sum(q1 * q2, axis=-1)), 0.0, 1.0)
    return np.degrees(2.0 * np.arccos(dots))


def quat_mul(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    """Producto de Hamilton q1 * q2 en convención [x, y, z, w]."""
    x1, y1, z1, w1 = q1[..., 0], q1[..., 1], q1[..., 2], q1[..., 3]
    x2, y2, z2, w2 = q2[..., 0], q2[..., 1], q2[..., 2], q2[..., 3]
    return np.stack([
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
    ], axis=-1)


def quat_conj(q: np.ndarray) -> np.ndarray:
    out = q.copy()
    out[..., :3] = -out[..., :3]
    return out


def quat_log_rad(q: np.ndarray) -> np.ndarray:
    """Mapa logarítmico en SO(3): convierte cuaternión unitario q -> vector de rotación en radianes (..., 3)."""
    qn = quat_normalize_batch(q)
    if qn.ndim == 1:
        if qn[3] < 0.0:
            qn = -qn
        w = min(1.0, max(-1.0, float(qn[3])))
        angle = 2.0 * math.acos(w)
        sin_h = math.sqrt(max(0.0, 1.0 - w * w))
        if sin_h < 1e-7 or angle < 1e-7:
            return np.zeros(3, dtype=np.float64)
        return (qn[:3] / sin_h) * angle

    flip = qn[..., 3] < 0.0
    if np.any(flip):
        qn = qn.copy()
        qn[flip] = -qn[flip]
    w = np.clip(qn[..., 3], -1.0, 1.0)
    angle = 2.0 * np.arccos(w)
    sin_h = np.sqrt(np.maximum(0.0, 1.0 - w * w))
    safe_sin = np.where(sin_h > 1e-7, sin_h, 1.0)
    scale = np.where((sin_h > 1e-7) & (angle > 1e-7), angle / safe_sin, 0.0)
    return qn[..., :3] * scale[..., None]


def compute_tangent_velocity_rad_s(
    q_seq: np.ndarray,
    times: np.ndarray,
    frame_idx: int,
    direction: str = "central",
    step_frames: int = 2,
) -> np.ndarray:
    """
    Calcula la velocidad angular en el espacio tangente local (rad/s) en `frame_idx`:
    w = (1 / dt) * log(q(t0)^-1 * q(t1))
    """
    n = q_seq.shape[0]
    if n < 2:
        return np.zeros(q_seq.shape[1:-1] + (3,), dtype=np.float64)

    idx = max(0, min(n - 1, int(frame_idx)))
    if direction == "forward":
        i0 = idx
        i1 = min(n - 1, idx + max(1, step_frames))
    elif direction == "backward":
        i1 = idx
        i0 = max(0, idx - max(1, step_frames))
    else:
        i0 = max(0, idx - max(1, step_frames))
        i1 = min(n - 1, idx + max(1, step_frames))

    if i1 <= i0:
        return np.zeros(q_seq.shape[1:-1] + (3,), dtype=np.float64)

    dt = float(times[i1] - times[i0])
    if dt <= 1e-5:
        return np.zeros(q_seq.shape[1:-1] + (3,), dtype=np.float64)

    dq = quat_mul(quat_conj(q_seq[i0]), q_seq[i1])
    rot_vec_rad = quat_log_rad(dq)
    return rot_vec_rad / dt


# ---------------------------------------------------------------------------
# Detección de Ventana de Trazo Activo (Stroke Window) y Anclas por Seña
# ---------------------------------------------------------------------------

def analyze_sign_stroke(
    sign_dir: Path,
    fixed_window: Optional[Tuple[int, int]] = None,
) -> Optional[Dict[str, Any]]:
    anim_path = sign_dir / "animation.json"
    if not anim_path.is_file():
        return None

    try:
        raw = json.loads(anim_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    frames = raw.get("frames") or []
    meta = raw.get("metadata") or {}
    t_count = len(frames)
    if t_count == 0:
        return None

    sign_name = unicodedata.normalize("NFC", str(meta.get("sign") or sign_dir.name).strip())
    fps = float(meta.get("fps") or 60.0)
    if fps <= 0:
        fps = 60.0

    info_path = sign_dir / "info.json"
    info_data: Dict[str, Any] = {}
    if info_path.is_file():
        try:
            info_data = json.loads(info_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    qa_path = sign_dir / "qa.json"
    qa_data: Dict[str, Any] = {}
    if qa_path.is_file():
        try:
            qa_data = json.loads(qa_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    is_face_only = bool(
        meta.get("faceOnly")
        or meta.get("armsInRestPose")
        or info_data.get("solo_rostro")
        or info_data.get("face_only")
        or info_data.get("hand_configuration") == "configuracion_manual_rostro"
        or info_data.get("configuracion_manual") == "configuracion_manual_rostro"
    )

    times = np.empty(t_count, dtype=np.float64)
    bone_idx_map = {b: i for i, b in enumerate(ALL_TRACKED_BONES)}
    q_all = np.zeros((t_count, len(ALL_TRACKED_BONES), 4), dtype=np.float64)
    for b_i, b_name in enumerate(ALL_TRACKED_BONES):
        q_all[:, b_i, :] = CANONICAL_REST_NP[b_name]

    expr_activity = np.zeros(t_count, dtype=np.float64)

    for t, fr in enumerate(frames):
        times[t] = float(fr.get("time", t / fps))
        rots = fr.get("rotations") or {}
        for b_i, b_name in enumerate(ALL_TRACKED_BONES):
            q_val = rots.get(b_name)
            if q_val is not None and len(q_val) == 4:
                q_all[t, b_i] = q_val
        if is_face_only:
            ex = fr.get("expressions") or {}
            bs = fr.get("blendshapes") or {}
            max_ex = max((float(v) for k, v in ex.items() if k != "neutral" and isinstance(v, (int, float))), default=0.0)
            max_bs = max((float(v) for v in bs.values() if isinstance(v, (int, float))), default=0.0)
            expr_activity[t] = max(max_ex, max_bs) * 45.0

    q_all = enforce_antipodal_continuity(q_all)
    orig_dur = float(times[-1] - times[0]) if t_count > 1 else (t_count / fps)
    if orig_dur <= 0:
        orig_dur = t_count / fps

    # Índices de cadenas
    l_arm_idx = [bone_idx_map[b] for b in LEFT_ARM_BONES]
    r_arm_idx = [bone_idx_map[b] for b in RIGHT_ARM_BONES]
    l_fin_idx = [bone_idx_map[b] for b in LEFT_FINGER_BONES]
    r_fin_idx = [bone_idx_map[b] for b in RIGHT_FINGER_BONES]
    torso_idx = [bone_idx_map[b] for b in TORSO_HEAD_BONES]

    q_l_arm = q_all[:, l_arm_idx, :]  # (T, 4, 4)
    q_r_arm = q_all[:, r_arm_idx, :]  # (T, 4, 4)
    q_l_fin = q_all[:, l_fin_idx, :]  # (T, 15, 4)
    q_r_fin = q_all[:, r_fin_idx, :]  # (T, 15, 4)
    q_torso = q_all[:, torso_idx, :]  # (T, 5, 4)

    rest_l_arm = np.stack([CANONICAL_REST_NP[b] for b in LEFT_ARM_BONES], axis=0)[None, :, :]
    rest_r_arm = np.stack([CANONICAL_REST_NP[b] for b in RIGHT_ARM_BONES], axis=0)[None, :, :]

    # Distancias angulares de brazo respecto al frame inicial, final y reposo canónico
    # Ponderamos hombro a 0.50 y brazo/antebrazo/muñeca a 1.0 para reflejar el desplazamiento real del efector.
    arm_weights = np.array([0.50, 1.0, 1.0, 1.0], dtype=np.float64)[None, :]

    d_l_arm_0 = np.max(quat_angle_deg_batch(q_l_arm, q_l_arm[0:1]) * arm_weights, axis=1)
    d_l_arm_N = np.max(quat_angle_deg_batch(q_l_arm, q_l_arm[-1:]) * arm_weights, axis=1)
    # Solo UpperArm y LowerArm tienen pose canónica explícita; la muñeca en reposo natural varía en pronación
    prox_weights = np.array([0.35, 1.0, 0.85, 0.0], dtype=np.float64)[None, :]
    d_l_arm_rest = np.max(quat_angle_deg_batch(q_l_arm, rest_l_arm) * prox_weights, axis=1)

    d_r_arm_0 = np.max(quat_angle_deg_batch(q_r_arm, q_r_arm[0:1]) * arm_weights, axis=1)
    d_r_arm_N = np.max(quat_angle_deg_batch(q_r_arm, q_r_arm[-1:]) * arm_weights, axis=1)
    d_r_arm_rest = np.max(quat_angle_deg_batch(q_r_arm, rest_r_arm) * prox_weights, axis=1)

    # Distancias angulares de los 15 huesos de dedos respecto a bordes (percentil 75)
    d_l_fin_0 = np.percentile(quat_angle_deg_batch(q_l_fin, q_l_fin[0:1]), 75, axis=1)
    d_l_fin_N = np.percentile(quat_angle_deg_batch(q_l_fin, q_l_fin[-1:]), 75, axis=1)

    d_r_fin_0 = np.percentile(quat_angle_deg_batch(q_r_fin, q_r_fin[0:1]), 75, axis=1)
    d_r_fin_N = np.percentile(quat_angle_deg_batch(q_r_fin, q_r_fin[-1:]), 75, axis=1)

    # Si el clip ya inicia o termina con el brazo muy elevado (>48° respecto al reposo canónico proximal),
    # usar la referencia canónica en ese borde para no perder el inicio/fin real del trazo.
    eff_l_0 = np.maximum(d_l_arm_0, d_l_arm_rest) if d_l_arm_rest[0] > 48.0 else d_l_arm_0
    eff_l_N = np.maximum(d_l_arm_N, d_l_arm_rest) if d_l_arm_rest[-1] > 48.0 else d_l_arm_N
    eff_r_0 = np.maximum(d_r_arm_0, d_r_arm_rest) if d_r_arm_rest[0] > 48.0 else d_r_arm_0
    eff_r_N = np.maximum(d_r_arm_N, d_r_arm_rest) if d_r_arm_rest[-1] > 48.0 else d_r_arm_N

    act_l_arm = np.minimum(eff_l_0, eff_l_N)
    act_r_arm = np.minimum(eff_r_0, eff_r_N)

    act_l_fin = np.minimum(d_l_fin_0, d_l_fin_N)
    act_r_fin = np.minimum(d_r_fin_0, d_r_fin_N)

    peak_l = float(np.max(act_l_arm)) if t_count > 0 else 0.0
    peak_r = float(np.max(act_r_arm)) if t_count > 0 else 0.0

    # Cuando el brazo tiene excursión normal (>22°), la entrada/salida del espacio de señación
    # la determina la cadena hombro-brazo-antebrazo-muñeca; para señas de baja excursión braquial
    # (<22°), los 15 huesos de dedos aportan directamente a la envolvente de posición.
    fin_weight_l = max(0.0, min(0.35, (25.0 - peak_l) / 40.0)) if peak_l < 25.0 else 0.04
    fin_weight_r = max(0.0, min(0.35, (25.0 - peak_r) / 40.0)) if peak_r < 25.0 else 0.04

    # Señal combinada por cadena completa (hombro -> dedos)
    act_l = act_l_arm + fin_weight_l * act_l_fin
    act_r = act_r_arm + fin_weight_r * act_r_fin

    # Velocidad angular instantánea por cadena (deg/s)
    vel_l_arm = np.zeros(t_count, dtype=np.float64)
    vel_r_arm = np.zeros(t_count, dtype=np.float64)
    vel_l_fin = np.zeros(t_count, dtype=np.float64)
    vel_r_fin = np.zeros(t_count, dtype=np.float64)
    if t_count > 1:
        dt_arr = np.maximum(1e-4, np.diff(times))
        vel_l_arm[1:] = np.max(quat_angle_deg_batch(q_l_arm[1:], q_l_arm[:-1]), axis=1) / dt_arr
        vel_r_arm[1:] = np.max(quat_angle_deg_batch(q_r_arm[1:], q_r_arm[:-1]), axis=1) / dt_arr
        vel_l_fin[1:] = np.percentile(quat_angle_deg_batch(q_l_fin[1:], q_l_fin[:-1]), 75, axis=1) / dt_arr
        vel_r_fin[1:] = np.percentile(quat_angle_deg_batch(q_r_fin[1:], q_r_fin[:-1]), 75, axis=1) / dt_arr

    # Determinar manos activas
    energy_l = float(np.mean(act_l)) if t_count > 0 else 0.0
    energy_r = float(np.mean(act_r)) if t_count > 0 else 0.0

    h_std = raw.get("handStandardization") or meta.get("handStandardization") or {}
    std_hands = h_std.get("hand_applied") or []

    if is_face_only or (peak_l < 10.0 and peak_r < 10.0):
        left_active = False
        right_active = False
        dominant_hand = "none"
    else:
        if peak_r * 1.05 >= peak_l:
            dominant_hand = "right"
            right_active = True
            left_active = bool(
                ("left" in std_hands)
                or (peak_l >= max(14.0, 0.38 * peak_r) and energy_l >= 0.28 * energy_r)
            )
        else:
            dominant_hand = "left"
            left_active = True
            right_active = bool(
                ("right" in std_hands)
                or (peak_r >= max(14.0, 0.38 * peak_l) and energy_r >= 0.28 * energy_l)
            )

    one_handed = (left_active != right_active)

    # Construir curva de actividad maestra para segmentación del trazo
    if is_face_only or dominant_hand == "none":
        d_torso_0 = np.max(quat_angle_deg_batch(q_torso, q_torso[0:1]), axis=1)
        d_torso_N = np.max(quat_angle_deg_batch(q_torso, q_torso[-1:]), axis=1)
        master_act = np.minimum(d_torso_0, d_torso_N) + expr_activity
        master_vel = np.zeros(t_count, dtype=np.float64)
        if t_count > 1:
            dt_arr = np.maximum(1e-4, np.diff(times))
            master_vel[1:] = np.max(quat_angle_deg_batch(q_torso[1:], q_torso[:-1]), axis=1) / dt_arr
    elif left_active and right_active:
        master_act = np.maximum(act_l, act_r)
        master_vel = np.maximum(vel_l_arm + 0.25 * vel_l_fin, vel_r_arm + 0.25 * vel_r_fin)
    elif left_active:
        master_act = act_l
        master_vel = vel_l_arm + 0.25 * vel_l_fin
    else:
        master_act = act_r
        master_vel = vel_r_arm + 0.25 * vel_r_fin

    # Suavizado ligero de 3 puntos para inmunidad a ruido puntual
    act_smooth = master_act.copy()
    if t_count >= 5:
        act_smooth[1:-1] = 0.25 * master_act[:-2] + 0.50 * master_act[1:-1] + 0.25 * master_act[2:]

    min_act = float(np.min(act_smooth))
    max_act = float(np.max(act_smooth))
    span_act = max_act - min_act

    repeated_stroke = False
    if t_count < 6 or span_act < 5.0:
        i0 = 0
        i1 = t_count - 1
    else:
        # Histéresis: umbral alto de confirmación de trazo (42%) y umbral de borde de zona activa (38%)
        thr_high = min_act + 0.42 * span_act
        thr_low = min_act + 0.38 * span_act

        high_indices = np.where(act_smooth >= thr_high)[0]
        if len(high_indices) == 0:
            high_indices = np.where(act_smooth >= thr_low)[0]

        if len(high_indices) == 0:
            i0, i1 = 0, t_count - 1
        else:
            first_high = int(high_indices[0])
            last_high = int(high_indices[-1])

            # Retroceder desde first_high hasta cruzar thr_low (salida de zona de reposo)
            i0 = first_high
            while i0 > 0 and act_smooth[i0 - 1] >= thr_low:
                i0 -= 1

            # Avanzar desde last_high hasta cruzar thr_low (entrada a retracción hacia reposo)
            i1 = last_high
            while i1 < t_count - 1 and act_smooth[i1 + 1] >= thr_low:
                i1 += 1

            # Si en el borde inmediato aún hay articulación de dedos con brazo ya en posición (>= 0.33 * span_act),
            # incluir hasta 2 frames de margen para no truncar el inicio/fin del queirema.
            floor_hold = min_act + 0.33 * span_act
            steps_back = 0
            while i0 > 0 and steps_back < 2 and act_smooth[i0 - 1] >= floor_hold and master_vel[i0 - 1] > 25.0:
                i0 -= 1
                steps_back += 1
            steps_fwd = 0
            while i1 < t_count - 1 and steps_fwd < 2 and act_smooth[i1 + 1] >= floor_hold and master_vel[i1 + 1] > 25.0:
                i1 += 1
                steps_fwd += 1

            # Detectar si existe repetición de diccionario (valle profundo entre dos picos de trazo)
            if (i1 - i0) >= 24:
                mid_s = i0 + int((i1 - i0) * 0.22)
                mid_e = i0 + int((i1 - i0) * 0.78)
                if mid_e > mid_s + 4:
                    valley_idx = mid_s + int(np.argmin(act_smooth[mid_s : mid_e + 1]))
                    peak1 = float(np.max(act_smooth[i0 : valley_idx + 1]))
                    peak2 = float(np.max(act_smooth[valley_idx : i1 + 1]))
                    valley_val = float(act_smooth[valley_idx])
                    if (
                        peak1 >= thr_high
                        and peak2 >= thr_high
                        and valley_val < min_act + 0.55 * span_act
                    ):
                        repeated_stroke = True

    # Calcular trayectorias 3D de muñeca por FK para garantizar que [i0, i1] incluya el ápice cinemático
    if t_count > 30:
        def _q_to_mat_batch(q: np.ndarray) -> np.ndarray:
            x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
            xx, yy, zz = x * x, y * y, z * z
            xy, xz, yz = x * y, x * z, y * z
            wx, wy, wz = w * x, w * y, w * z
            m = np.empty(q.shape[:-1] + (3, 3), dtype=np.float64)
            m[..., 0, 0] = 1.0 - 2.0 * (yy + zz)
            m[..., 0, 1] = 2.0 * (xy - wz)
            m[..., 0, 2] = 2.0 * (xz + wy)
            m[..., 1, 0] = 2.0 * (xy + wz)
            m[..., 1, 1] = 1.0 - 2.0 * (xx + zz)
            m[..., 1, 2] = 2.0 * (yz - wx)
            m[..., 2, 0] = 2.0 * (xz - wy)
            m[..., 2, 1] = 2.0 * (yz + wx)
            m[..., 2, 2] = 1.0 - 2.0 * (xx + yy)
            return m

        def _detect_apex(wrist_traj: np.ndarray) -> int:
            n_f = len(wrist_traj)
            if n_f <= 1:
                return 0
            y_vals = wrist_traj[:, 1]
            v_vals = np.zeros(n_f, dtype=np.float64)
            if n_f > 2:
                disp = wrist_traj[2:] - wrist_traj[:-2]
                v_vals[1:-1] = np.linalg.norm(disp, axis=1) * (fps / 2.0)
                v_vals[0] = float(np.linalg.norm(wrist_traj[1] - wrist_traj[0])) * fps
                v_vals[-1] = float(np.linalg.norm(wrist_traj[-1] - wrist_traj[-2])) * fps
            y_min, y_max = float(np.min(y_vals)), float(np.max(y_vals))
            v_min, v_max = float(np.min(v_vals)), float(np.max(v_vals))
            y_tilde = (y_vals - y_min) / (y_max - y_min + 1e-6)
            v_tilde = (v_vals - v_min) / (v_max - v_min + 1e-6)
            s_apex = 0.65 * y_tilde + 0.35 * (1.0 - v_tilde)
            sk = max(0, min(int(0.20 * n_f), n_f - 1)) if n_f >= 10 else 0
            ek = max(sk + 1, min(int(0.80 * n_f), n_f)) if n_f >= 10 else n_f
            return sk + int(np.argmax(s_apex[sk:ek]))

        m_hips = _q_to_mat_batch(q_all[:, bone_idx_map["hips"]])
        m_spine = m_hips @ _q_to_mat_batch(q_all[:, bone_idx_map["spine"]])
        m_chest = m_spine @ _q_to_mat_batch(q_all[:, bone_idx_map["chest"]])
        p_hips = np.zeros((t_count, 3), dtype=np.float64)
        p_hips[:, 1] = 0.907995
        p_hips[:, 2] = 0.003576
        for t, fr in enumerate(frames):
            hp = fr.get("hipsPosition")
            if hp is not None and len(hp) == 3:
                p_hips[t] = [float(hp[0]), float(hp[1]), float(hp[2])]
        p_spine = p_hips + np.einsum("nij,j->ni", m_hips, np.array([0.0, 0.052071, 0.012517]))
        p_chest = p_spine + np.einsum("nij,j->ni", m_spine, np.array([0.0, 0.113013, 0.003050]))
        p_uch = p_chest + np.einsum("nij,j->ni", m_chest, np.array([0.0, 0.107644, -0.014646]))

        m_lsh = m_chest @ _q_to_mat_batch(q_all[:, bone_idx_map["leftShoulder"]])
        p_lsh = p_uch + np.einsum("nij,j->ni", m_chest, np.array([0.022395, 0.105687, -0.029969]))
        m_lua = m_lsh @ _q_to_mat_batch(q_all[:, bone_idx_map["leftUpperArm"]])
        p_lua = p_lsh + np.einsum("nij,j->ni", m_lsh, np.array([0.086161, -0.012260, 0.0]))
        m_lla = m_lua @ _q_to_mat_batch(q_all[:, bone_idx_map["leftLowerArm"]])
        p_lla = p_lua + np.einsum("nij,j->ni", m_lua, np.array([0.219853, -0.000001, 0.0]))
        p_lwr = p_lla + np.einsum("nij,j->ni", m_lla, np.array([0.214685, 0.000003, 0.000013]))

        m_rsh = m_chest @ _q_to_mat_batch(q_all[:, bone_idx_map["rightShoulder"]])
        p_rsh = p_uch + np.einsum("nij,j->ni", m_chest, np.array([-0.022395, 0.105687, -0.029969]))
        m_rua = m_rsh @ _q_to_mat_batch(q_all[:, bone_idx_map["rightUpperArm"]])
        p_rua = p_rsh + np.einsum("nij,j->ni", m_rsh, np.array([-0.086161, -0.012260, 0.0]))
        m_rla = m_rua @ _q_to_mat_batch(q_all[:, bone_idx_map["rightLowerArm"]])
        p_rla = p_rua + np.einsum("nij,j->ni", m_rua, np.array([-0.219853, -0.000001, 0.0]))
        p_rwr = p_rla + np.einsum("nij,j->ni", m_rla, np.array([-0.214685, 0.000003, 0.000013]))

        apex_l = _detect_apex(p_lwr)
        apex_r = _detect_apex(p_rwr)
        std_dom = str(h_std.get("dominant_hand") or "")
        if std_dom == "left":
            apex_targets = [apex_l]
        elif std_dom == "right":
            apex_targets = [apex_r]
        else:
            yl_max = float(np.max(p_lwr[:, 1]))
            yr_max = float(np.max(p_rwr[:, 1]))
            apex_targets = [apex_l if yl_max > yr_max + 0.03 else apex_r]
        if left_active and apex_l not in apex_targets:
            apex_targets.append(apex_l)
        if right_active and apex_r not in apex_targets:
            apex_targets.append(apex_r)

        for apx in apex_targets:
            if apx < i0 - 4:
                i0 = max(0, apx - 2)
            if apx > i1 + 4:
                i1 = min(t_count - 1, apx + 2)

    # Garantizar duración mínima razonable (>= 24 frames si t_count > 36)
    min_frames = min(t_count - 1, max(23 if t_count > 36 else 4, int(round(0.40 * fps))))
    if (i1 - i0) < min_frames and t_count > min_frames:
        center = (i0 + i1) // 2
        i0 = max(0, min(t_count - 1 - min_frames, center - min_frames // 2))
        i1 = min(t_count - 1, i0 + min_frames)

    if fixed_window is not None and len(fixed_window) == 2:
        fw0 = max(0, min(t_count - 1, int(fixed_window[0])))
        fw1 = max(fw0, min(t_count - 1, int(fixed_window[1])))
        i0, i1 = fw0, fw1

    stroke_start = round(float(times[i0]), 4)
    stroke_end = round(float(times[i1]), 4)
    stroke_dur = round(max(0.05, stroke_end - stroke_start), 4)
    too_short = bool(stroke_dur < 0.38)

    # Construir poses de ancla (redondeadas a 4 decimales para índice compacto y rápido)
    def _extract_chain_anchor(frame_idx: int, chain_bones: List[str], is_active: bool) -> Dict[str, List[float]]:
        out_pose: Dict[str, List[float]] = {}
        for b_name in chain_bones:
            if not is_active:
                q_val = CANONICAL_REST_POSE[b_name]
            else:
                q_np = q_all[frame_idx, bone_idx_map[b_name]]
                q_val = [round(float(q_np[0]), 4), round(float(q_np[1]), 4), round(float(q_np[2]), 4), round(float(q_np[3]), 4)]
            out_pose[b_name] = q_val
        return out_pose

    def _extract_torso_anchor(frame_idx: int) -> Dict[str, List[float]]:
        out_pose: Dict[str, List[float]] = {}
        for b_name in TORSO_HEAD_BONES:
            q_np = q_all[frame_idx, bone_idx_map[b_name]]
            out_pose[b_name] = [round(float(q_np[0]), 4), round(float(q_np[1]), 4), round(float(q_np[2]), 4), round(float(q_np[3]), 4)]
        return out_pose

    # Velocidades angulares en los bordes del trazo (en rad/s para los huesos de brazo+mano)
    v_start_all = compute_tangent_velocity_rad_s(q_all, times, i0, direction="forward", step_frames=2)
    v_end_all = compute_tangent_velocity_rad_s(q_all, times, i1, direction="backward", step_frames=2)

    def _extract_arm_velocity(vel_arr: np.ndarray, arm_bones: List[str], is_active: bool) -> Dict[str, List[float]]:
        out_vel: Dict[str, List[float]] = {}
        for b_name in arm_bones:
            if not is_active:
                out_vel[b_name] = [0.0, 0.0, 0.0]
            else:
                v = vel_arr[bone_idx_map[b_name]]
                out_vel[b_name] = [round(float(v[0]), 4), round(float(v[1]), 4), round(float(v[2]), 4)]
        return out_vel

    v_start_l = _extract_arm_velocity(v_start_all, LEFT_ARM_BONES, left_active)
    v_start_r = _extract_arm_velocity(v_start_all, RIGHT_ARM_BONES, right_active)
    v_end_l = _extract_arm_velocity(v_end_all, LEFT_ARM_BONES, left_active)
    v_end_r = _extract_arm_velocity(v_end_all, RIGHT_ARM_BONES, right_active)

    start_speed_l = round(math.degrees(max((math.hypot(*v) for v in v_start_l.values()), default=0.0)), 2)
    start_speed_r = round(math.degrees(max((math.hypot(*v) for v in v_start_r.values()), default=0.0)), 2)
    end_speed_l = round(math.degrees(max((math.hypot(*v) for v in v_end_l.values()), default=0.0)), 2)
    end_speed_r = round(math.degrees(max((math.hypot(*v) for v in v_end_r.values()), default=0.0)), 2)

    # Calcular puntaje de confianza [0, 1]
    snr_score = min(1.0, max(0.1, (span_act - 5.0) / 35.0))
    dur_score = 1.0 if (0.40 <= stroke_dur <= 2.60) else (0.65 if not too_short else 0.45)
    qa_cov = float(qa_data.get("any_hand_coverage", 1.0) or 1.0)
    qa_rev_penalty = 0.15 if str(qa_data.get("needs_review", "False")).lower() == "true" else 0.0
    rep_penalty = 0.08 if repeated_stroke else 0.0
    confidence = round(float(np.clip(0.55 * snr_score + 0.25 * dur_score + 0.20 * qa_cov - qa_rev_penalty - rep_penalty, 0.05, 0.99)), 4)

    # Métrica de tiempo muerto residual dentro del trazo recortado [i0, i1]
    # (tiempo en los extremos de [i0, i1] por debajo de 0.38 * act_arm_max)
    ref_bones_6 = ["leftUpperArm", "rightUpperArm", "leftLowerArm", "rightLowerArm", "leftHand", "rightHand"]
    ref_idx_6 = [bone_idx_map[b] for b in ref_bones_6]
    q_ref6 = q_all[:, ref_idx_6, :]
    d0_ref6 = np.max(quat_angle_deg_batch(q_ref6, q_ref6[0:1]), axis=1)
    dN_ref6 = np.max(quat_angle_deg_batch(q_ref6, q_ref6[-1:]), axis=1)
    act_ref6 = np.minimum(d0_ref6, dN_ref6)
    max_ref6 = float(np.max(act_ref6))
    if max_ref6 > 8.0:
        thr_ref6 = 0.38 * max_ref6
        active_ref6 = np.where(act_ref6 >= thr_ref6)[0]
        if len(active_ref6) > 0:
            gt_i0 = int(active_ref6[0])
            gt_i1 = int(active_ref6[-1])
            lead_residual_sec = round(abs(i0 - gt_i0) / fps, 4)
            tail_residual_sec = round(abs(i1 - gt_i1) / fps, 4)
        else:
            lead_residual_sec = 0.0
            tail_residual_sec = 0.0
    else:
        lead_residual_sec = 0.0
        tail_residual_sec = 0.0

    return {
        "sign": sign_name,
        "strokeStart": stroke_start,
        "strokeEnd": stroke_end,
        "strokeDuration": stroke_dur,
        "originalDuration": round(orig_dur, 4),
        "startFrame": int(i0),
        "endFrame": int(i1),
        "totalFrames": int(t_count),
        "fps": round(fps, 2),
        "confidence": confidence,
        "flags": {
            "repeatedStroke": bool(repeated_stroke),
            "oneHanded": bool(one_handed),
            "tooShort": bool(too_short),
            "faceOnly": bool(is_face_only),
        },
        "activeHands": {
            "left": bool(left_active),
            "right": bool(right_active),
            "dominant": dominant_hand,
        },
        "anchors": {
            "start": {
                "left": _extract_chain_anchor(i0, LEFT_CHAIN_BONES, left_active),
                "right": _extract_chain_anchor(i0, RIGHT_CHAIN_BONES, right_active),
                "torso": _extract_torso_anchor(i0),
            },
            "end": {
                "left": _extract_chain_anchor(i1, LEFT_CHAIN_BONES, left_active),
                "right": _extract_chain_anchor(i1, RIGHT_CHAIN_BONES, right_active),
                "torso": _extract_torso_anchor(i1),
            },
        },
        "boundaryVelocity": {
            "start": {
                "left": v_start_l,
                "right": v_start_r,
                "speedDegPerSec": {"left": start_speed_l, "right": start_speed_r},
            },
            "end": {
                "left": v_end_l,
                "right": v_end_r,
                "speedDegPerSec": {"left": end_speed_l, "right": end_speed_r},
            },
        },
        "_qa_metrics": {
            "leadRemovedSec": round(stroke_start, 4),
            "tailRemovedSec": round(max(0.0, orig_dur - stroke_end), 4),
            "leadResidualSec": lead_residual_sec,
            "tailResidualSec": tail_residual_sec,
        },
    }


def _worker_analyze(task_arg: Any) -> Optional[Dict[str, Any]]:
    if isinstance(task_arg, tuple):
        sign_dir_str, fw = task_arg
        return analyze_sign_stroke(Path(sign_dir_str), fixed_window=fw)
    return analyze_sign_stroke(Path(task_arg))


def build_histogram(values: Sequence[float], bins: Sequence[float]) -> List[Dict[str, Any]]:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return []
    counts, edges = np.histogram(arr, bins=bins)
    return [
        {"range": f"[{edges[i]:.2f}, {edges[i + 1]:.2f})", "min": round(float(edges[i]), 3), "max": round(float(edges[i + 1]), 3), "count": int(counts[i]), "pct": round(100.0 * float(counts[i]) / float(arr.size), 2)}
        for i in range(len(counts))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Construye stroke_index.json para el catálogo v2.7 LSEC.")
    parser.add_argument("--v27-dir", type=str, default=r"c:\Users\brana\Desktop\TIC Software\Diccionario LSEC\senas_vrm_standardized_v2.7", help="Ruta al directorio senas_vrm_standardized_v2.7")
    parser.add_argument("--output", type=str, default="", help="Ruta de salida para stroke_index.json")
    parser.add_argument("--preserve-windows-from", type=str, default="", help="Ruta opcional a un stroke_index existente cuyas ventanas deben preservarse")
    parser.add_argument("--sample", type=int, default=0, help="Si > 0, evalúa únicamente una muestra aleatoria reproducible (seed=1) de N señas")
    parser.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 4))), help="Número de procesos paralelos")
    args = parser.parse_args()
    v27_dir = Path(args.v27_dir)
    if not v27_dir.is_dir():
        print(f"ERROR: No existe el directorio {v27_dir}", file=sys.stderr)
        return 1

    preserved_windows: Dict[str, Tuple[int, int]] = {}
    if args.preserve_windows_from and Path(args.preserve_windows_from).is_file():
        pw_doc = json.loads(Path(args.preserve_windows_from).read_text(encoding="utf-8"))
        for sn, st_e in (pw_doc.get("signs") or {}).items():
            if "startFrame" in st_e and "endFrame" in st_e:
                preserved_windows[unicodedata.normalize("NFC", str(sn).strip())] = (int(st_e["startFrame"]), int(st_e["endFrame"]))

    sign_dirs = sorted([v27_dir / d for d in os.listdir(v27_dir) if (v27_dir / d).is_dir() and not d.startswith(".")], key=lambda p: unicodedata.normalize("NFC", p.name))
    if 0 < args.sample < len(sign_dirs):
        sign_dirs = random.Random(1).sample(sign_dirs, args.sample)

    t0 = time.time()
    print(f"Procesando {len(sign_dirs)} señas desde {v27_dir} con {args.workers} workers...")
    task_items = [(str(p), preserved_windows.get(unicodedata.normalize("NFC", p.name.strip()))) for p in sign_dirs]
    results: List[Dict[str, Any]] = []
    if args.workers > 1 and len(sign_dirs) > 30:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            results = [item for item in ex.map(_worker_analyze, task_items, chunksize=25) if item is not None]
    else:
        results = [item for p, fw in task_items if (item := analyze_sign_stroke(Path(p), fixed_window=fw)) is not None]

    elapsed = time.time() - t0
    results.sort(key=lambda r: r["sign"])
    lead_rem = [r["_qa_metrics"]["leadRemovedSec"] for r in results]
    tail_rem = [r["_qa_metrics"]["tailRemovedSec"] for r in results]
    lead_res = [r["_qa_metrics"]["leadResidualSec"] for r in results]
    tail_res = [r["_qa_metrics"]["tailResidualSec"] for r in results]
    stroke_durs = [r["strokeDuration"] for r in results]
    orig_durs = [r["originalDuration"] for r in results]
    confs = [r["confidence"] for r in results]

    lowest_50 = sorted(
        [{"sign": r["sign"], "confidence": r["confidence"], "strokeStart": r["strokeStart"], "strokeEnd": r["strokeEnd"], "strokeDuration": r["strokeDuration"], "originalDuration": r["originalDuration"], "flags": r["flags"], "activeHands": r["activeHands"]} for r in results],
        key=lambda x: (x["confidence"], x["strokeDuration"]),
    )[:50]

    def _stats_3(arr: List[float]) -> Dict[str, float]:
        return {"mean": round(float(np.mean(arr)), 3) if arr else 0.0, "median": round(float(np.median(arr)), 3) if arr else 0.0, "p90": round(float(np.percentile(arr, 90)), 3) if arr else 0.0}

    summary_stats = {
        "version": "2.7", "totalSignsIndexed": len(results), "processingTimeSec": round(elapsed, 2),
        "originalDurationSec": _stats_3(orig_durs),
        "strokeDurationSec": {**_stats_3(stroke_durs), "p10": round(float(np.percentile(stroke_durs, 10)), 3) if stroke_durs else 0.0},
        "leadInTrimmedSec": _stats_3(lead_rem), "tailOutTrimmedSec": _stats_3(tail_rem),
        "residualDeadTimeSec": {
            "leadMedian": round(float(np.median(lead_res)), 4) if lead_res else 0.0, "tailMedian": round(float(np.median(tail_res)), 4) if tail_res else 0.0,
            "leadMean": round(float(np.mean(lead_res)), 4) if lead_res else 0.0, "tailMean": round(float(np.mean(tail_res)), 4) if tail_res else 0.0,
            "leadP90": round(float(np.percentile(lead_res, 90)), 4) if lead_res else 0.0, "tailP90": round(float(np.percentile(tail_res, 90)), 4) if tail_res else 0.0,
        },
        "deadTimeShareRemovedPct": round(100.0 * (sum(lead_rem) + sum(tail_rem)) / max(1e-6, sum(orig_durs)), 2),
        "flagsCount": {k: sum(1 for r in results if r["flags"][k]) for k in ("repeatedStroke", "oneHanded", "tooShort", "faceOnly")},
        "histograms": {
            "strokeDurationSec": build_histogram(stroke_durs, [0.0, 0.4, 0.8, 1.2, 1.6, 2.0, 2.5, 3.5, 10.0]),
            "leadInTrimmedSec": build_histogram(lead_rem, [0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 10.0]),
            "tailOutTrimmedSec": build_histogram(tail_rem, [0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 10.0]),
            "confidence": build_histogram(confs, [0.0, 0.4, 0.6, 0.75, 0.85, 0.92, 1.01]),
        },
        "lowestConfidence50": lowest_50,
    }
    print(f"Completado en {elapsed:.2f}s | Señas: {len(results)} | Duración trazo mediana: {summary_stats['strokeDurationSec']['median']:.2f}s")
    if args.sample > 0 and not args.output:
        return 0
    signs_dict = {r["sign"]: {k: v for k, v in r.items() if k != "_qa_metrics"} for r in results}
    payload = {"version": "2.7", "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "totalSigns": len(signs_dict), "canonicalRestPose": CANONICAL_REST_POSE, "summary": summary_stats, "signs": signs_dict}
    repo_root = Path(__file__).resolve().parents[1]
    out_paths = [Path(args.output)] if args.output else [v27_dir / "stroke_index.json", repo_root / "app" / "data" / "stroke_index_v27.json"]
    qa_report_path = repo_root / "reports" / "stroke_index_v27_qa.json"
    qa_report_path.parent.mkdir(parents=True, exist_ok=True)
    qa_report_path.write_text(json.dumps(summary_stats, ensure_ascii=False, indent=2), encoding="utf-8")
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    for p in out_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(serialized, encoding="utf-8")
        print(f"Índice guardado en: {p} ({len(serialized) / (1024 * 1024):.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
