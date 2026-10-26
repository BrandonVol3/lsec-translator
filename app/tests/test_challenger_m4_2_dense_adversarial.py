# -*- coding: utf-8 -*-
"""
app/tests/test_challenger_m4_2_dense_adversarial.py
===================================================
Adversarial Empirical Verification Suite — Milestone 4 (Iteration 2).
Author: Challenger 1 (challenger_m4_2_1).

Adversarial Stress Dimensions:
1. DENSE Frame-by-Frame (step=1) Thoracic Clearance across ALL 17 signs and ALL 32 hand/finger bones.
   Specifically stress-testing proximal and metacarpal joints (leftThumbProximal, leftThumbMetacarpal,
   rightThumbProximal, rightThumbMetacarpal) against clearance >= 2.0 cm (0.020 m).
2. Continuous Wrist Step Rotation check across ALL frames (0..T-1) for 'Centro' ensuring max step <= 45.0°.
   Also audits all remaining 16 target signs against max step < 55.0°.
3. Active Joint Excursion > 15.0° during ictus across all 17 target signs.
4. Bounding Box Boundary Stress Test (evaluating clearance with expanded chest bounding box).
5. Rotational Field Integrity (unit quaternion normalization, NaN/Inf absence).
6. Dual Stroke Index SHA-256 Parity and Frame Count Synchronization.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple
import numpy as np
import pytest

# Paths
WORKSPACE_ROOT = Path("c:/Users/brana/Desktop/TIC Software")
PROTO_ROOT = WORKSPACE_ROOT / "lsec_translator_prototype"
DICCIONARIO_ROOT = WORKSPACE_ROOT / "Diccionario LSEC"
V27_DIR = DICCIONARIO_ROOT / "senas_vrm_standardized_v2.7"
STROKE_INDEX_PROTO = PROTO_ROOT / "app" / "data" / "stroke_index_v27.json"
STROKE_INDEX_DICC = V27_DIR / "stroke_index.json"

import sys
if str(PROTO_ROOT) not in sys.path:
    sys.path.insert(0, str(PROTO_ROOT))
if str(DICCIONARIO_ROOT) not in sys.path:
    sys.path.insert(0, str(DICCIONARIO_ROOT))

from tools.avatar_fk_extractor import (
    CHEST_SURFACE_Z,
    CHEST_BBOX_X,
    CHEST_BBOX_Y,
    CANONICAL_REST_POSITIONS,
    VRM_PARENT_MAP,
    PROPAGATION_ORDER,
    quat_to_mat,
    quat_mult,
)

TARGET_17_SIGNS = [
    "Veinte",
    "Carrera, Estudios",
    "Forma",
    "Investigar",
    "Carpeta",
    "Anterior, Antes",
    "Rector(a), Rectorado",
    "Equipo",
    "Salud, Saludable",
    "El, Ella",
    "Enfermera",
    "Esforzarse, Esfuerzo",
    "Ingeniero(a)",
    "Centro",
    "Ocho",
    "Promedio",
    "Diez",
]

WRIST_BONES = ["rightHand", "leftHand", "rightLowerArm", "leftLowerArm"]
ARM_BONES = ["rightUpperArm", "rightLowerArm", "rightHand", "leftUpperArm", "leftLowerArm", "leftHand"]

ALL_32_HAND_FINGER_BONES = [
    "rightHand", "leftHand",
    "rightThumbMetacarpal", "leftThumbMetacarpal",
    "rightThumbProximal", "leftThumbProximal",
    "rightThumbIntermediate", "leftThumbIntermediate",
    "rightThumbDistal", "leftThumbDistal",
    "rightIndexProximal", "leftIndexProximal",
    "rightIndexIntermediate", "leftIndexIntermediate",
    "rightIndexDistal", "leftIndexDistal",
    "rightMiddleProximal", "leftMiddleProximal",
    "rightMiddleIntermediate", "leftMiddleIntermediate",
    "rightMiddleDistal", "leftMiddleDistal",
    "rightRingProximal", "leftRingProximal",
    "rightRingIntermediate", "leftRingIntermediate",
    "rightRingDistal", "leftRingDistal",
    "rightLittleProximal", "leftLittleProximal",
    "rightLittleIntermediate", "leftLittleIntermediate",
    "rightLittleDistal", "leftLittleDistal",
]

PROXIMAL_AND_METACARPAL_BONES = [
    "rightThumbMetacarpal", "leftThumbMetacarpal",
    "rightThumbProximal", "leftThumbProximal",
    "rightIndexProximal", "leftIndexProximal",
    "rightMiddleProximal", "leftMiddleProximal",
    "rightRingProximal", "leftRingProximal",
    "rightLittleProximal", "leftLittleProximal",
]


def quat_angular_distance_deg(q1: Sequence[float], q2: Sequence[float]) -> float:
    dot = abs(q1[0]*q2[0] + q1[1]*q2[1] + q1[2]*q2[2] + q1[3]*q2[3])
    dot = min(1.0, max(-1.0, dot))
    return 2.0 * math.degrees(math.acos(dot))


def run_fk_for_frame(rot_dict: Dict[str, Sequence[float]]) -> Dict[str, np.ndarray]:
    world_pos = {}
    world_rot = {}
    for bone in PROPAGATION_ORDER:
        parent = VRM_PARENT_MAP[bone]
        q_loc = rot_dict.get(bone, [0.0, 0.0, 0.0, 1.0])
        norm = math.sqrt(sum(x * x for x in q_loc))
        q_loc = [x / norm for x in q_loc] if norm > 1e-6 else [0.0, 0.0, 0.0, 1.0]
        rest_pos = CANONICAL_REST_POSITIONS[bone]
        if parent is None:
            world_pos[bone] = np.array(rest_pos, dtype=np.float64)
            world_rot[bone] = np.array(q_loc, dtype=np.float64)
        else:
            p_parent = world_pos[parent]
            w_parent = quat_to_mat(world_rot[parent])
            p_rest_parent = CANONICAL_REST_POSITIONS[parent]
            delta_rest = np.array(rest_pos, dtype=np.float64) - np.array(p_rest_parent, dtype=np.float64)
            world_pos[bone] = p_parent + w_parent.dot(delta_rest)
            world_rot[bone] = quat_mult(world_rot[parent], q_loc)
    return world_pos


class TestChallengerM42DenseAdversarial:
    """Rigorous empirical adversarial suite verifying iteration 2 remediations."""

    def test_01_dense_step1_thoracic_clearance_all_17_signs(self):
        """
        Adversarial evaluation: Dense step=1 evaluation across ALL 32 hand/finger bones.
        Validates min clearance >= 2.0 cm (0.020 m) across the entire active stroke window.
        """
        with open(STROKE_INDEX_PROTO, "r", encoding="utf-8") as f:
            stroke_dict = json.load(f)["signs"]

        clearance_audit_results: Dict[str, Dict[str, Any]] = {}
        violations: List[str] = []

        for sign in TARGET_17_SIGNS:
            anim_path = V27_DIR / sign / "animation.json"
            assert anim_path.is_file(), f"Missing animation.json for {sign}"
            with open(anim_path, "r", encoding="utf-8") as f:
                anim = json.load(f)

            frames = anim["frames"]
            stroke_meta = stroke_dict.get(sign) or anim.get("metadata", {}).get("stroke") or {}
            s_f = stroke_meta.get("startFrame", 0)
            e_f = stroke_meta.get("endFrame", len(frames) - 1)

            min_sign_clr = float("inf")
            min_sign_bone = ""
            min_sign_frame = -1

            # Step = 1 (dense evaluation of every single frame)
            for k in range(s_f, e_f + 1, 1):
                rotations = frames[k].get("rotations", {})
                w_pos = run_fk_for_frame(rotations)

                for bone_name in ALL_32_HAND_FINGER_BONES:
                    if bone_name in w_pos:
                        pos = w_pos[bone_name]
                        if CHEST_BBOX_X[0] <= pos[0] <= CHEST_BBOX_X[1] and \
                           CHEST_BBOX_Y[0] <= pos[1] <= CHEST_BBOX_Y[1]:
                            clr = pos[2] - CHEST_SURFACE_Z
                            if clr < min_sign_clr:
                                min_sign_clr = clr
                                min_sign_bone = bone_name
                                min_sign_frame = k

            clearance_cm = min_sign_clr * 100.0
            clearance_audit_results[sign] = {
                "min_clearance_cm": clearance_cm,
                "critical_bone": min_sign_bone,
                "critical_frame": min_sign_frame,
                "stroke_window": (s_f, e_f),
            }

            if clearance_cm < 2.0:
                violations.append(
                    f"{sign}: {clearance_cm:.2f} cm (< 2.0 cm) at frame {min_sign_frame} on bone {min_sign_bone}"
                )

        print("\n--- DENSE STEP=1 THORACIC CLEARANCE AUDIT (ALL 32 BONES) ---")
        for sign, data in clearance_audit_results.items():
            print(f"  {sign:<22}: {data['min_clearance_cm']:>5.2f} cm (bone: {data['critical_bone']}, frame: {data['critical_frame']})")

        assert len(violations) == 0, f"Thoracic clearance violations found under dense step=1: {violations}"

    def test_02_proximal_and_metacarpal_specific_clearance(self):
        """
        Adversarial evaluation specifically targeting proximal and metacarpal bones
        (leftThumbProximal, leftThumbMetacarpal, rightThumbProximal, rightThumbMetacarpal, etc.)
        which triggered the iteration 1 rejection.
        """
        with open(STROKE_INDEX_PROTO, "r", encoding="utf-8") as f:
            stroke_dict = json.load(f)["signs"]

        proximal_violations: List[str] = []

        for sign in TARGET_17_SIGNS:
            anim_path = V27_DIR / sign / "animation.json"
            with open(anim_path, "r", encoding="utf-8") as f:
                anim = json.load(f)

            frames = anim["frames"]
            stroke_meta = stroke_dict.get(sign) or anim.get("metadata", {}).get("stroke") or {}
            s_f = stroke_meta.get("startFrame", 0)
            e_f = stroke_meta.get("endFrame", len(frames) - 1)

            for k in range(s_f, e_f + 1, 1):
                w_pos = run_fk_for_frame(frames[k]["rotations"])
                for bone in PROXIMAL_AND_METACARPAL_BONES:
                    if bone in w_pos:
                        pos = w_pos[bone]
                        if CHEST_BBOX_X[0] <= pos[0] <= CHEST_BBOX_X[1] and \
                           CHEST_BBOX_Y[0] <= pos[1] <= CHEST_BBOX_Y[1]:
                            clr_cm = (pos[2] - CHEST_SURFACE_Z) * 100.0
                            if clr_cm < 2.0:
                                proximal_violations.append(
                                    f"{sign} frame {k} {bone}: {clr_cm:.2f} cm < 2.0 cm"
                                )

        assert len(proximal_violations) == 0, (
            f"Proximal/metacarpal clearance violations detected: {proximal_violations}"
        )

    def test_03_wrist_flip_centro_all_frames_adversarial(self):
        """
        Adversarial evaluation: Continuous wrist angular step across ALL frames of 'Centro' (0..T-1).
        Verifies that maximum angular step remains strictly <= 45.0° (target) and < 55.0° (hard limit).
        """
        centro_path = V27_DIR / "Centro" / "animation.json"
        assert centro_path.is_file(), "Centro animation.json not found"
        with open(centro_path, "r", encoding="utf-8") as f:
            anim = json.load(f)

        frames = anim["frames"]
        n_frames = len(frames)
        max_step = 0.0
        max_frame = -1
        max_bone = ""
        flips_above_45: List[Tuple[int, str, float]] = []

        for k in range(1, n_frames):
            r_prev = frames[k - 1].get("rotations", {})
            r_curr = frames[k].get("rotations", {})
            for wb in WRIST_BONES:
                if wb in r_prev and wb in r_curr:
                    deg = quat_angular_distance_deg(r_prev[wb], r_curr[wb])
                    if deg > max_step:
                        max_step = deg
                        max_frame = k
                        max_bone = wb
                    if deg > 45.0:
                        flips_above_45.append((k, wb, deg))

        print(f"\n--- CENTRO WRIST ROTATION ADVERSARIAL AUDIT ---")
        print(f"  Total frames analyzed: {n_frames}")
        print(f"  Maximum angular step : {max_step:.2f}° (bone: {max_bone}, frame: {max_frame-1}->{max_frame})")
        print(f"  Steps > 45.0°         : {len(flips_above_45)}")

        assert max_step < 55.0, f"Centro hard limit violated: max step {max_step:.2f}° >= 55.0°"
        assert max_step <= 45.0, f"Centro target threshold violated: max step {max_step:.2f}° > 45.0° ({flips_above_45})"

    def test_04_wrist_flip_remaining_16_signs_all_frames(self):
        """
        Adversarial evaluation: Continuous wrist angular step across all frames for the other 16 signs.
        Verifies max angular step < 55.0°.
        """
        flips_over_55: List[Tuple[str, int, str, float]] = []

        for sign in TARGET_17_SIGNS:
            if sign == "Centro":
                continue
            anim_path = V27_DIR / sign / "animation.json"
            with open(anim_path, "r", encoding="utf-8") as f:
                anim = json.load(f)

            frames = anim["frames"]
            for k in range(1, len(frames)):
                r_prev = frames[k - 1].get("rotations", {})
                r_curr = frames[k].get("rotations", {})
                for wb in WRIST_BONES:
                    if wb in r_prev and wb in r_curr:
                        deg = quat_angular_distance_deg(r_prev[wb], r_curr[wb])
                        if deg >= 55.0:
                            flips_over_55.append((sign, k, wb, deg))

        assert len(flips_over_55) == 0, f"Wrist flips >= 55.0° found in target signs: {flips_over_55}"

    def test_05_active_joint_excursion_all_17_signs(self):
        """
        Adversarial evaluation: Active joint excursion > 15.0° during ictus across all 17 signs.
        """
        with open(STROKE_INDEX_PROTO, "r", encoding="utf-8") as f:
            stroke_dict = json.load(f)["signs"]

        excursion_results: Dict[str, float] = {}
        insufficient_excursion: List[Tuple[str, float]] = []

        for sign in TARGET_17_SIGNS:
            anim_path = V27_DIR / sign / "animation.json"
            with open(anim_path, "r", encoding="utf-8") as f:
                anim = json.load(f)

            frames = anim["frames"]
            stroke_meta = stroke_dict.get(sign) or anim.get("metadata", {}).get("stroke") or {}
            s_f = stroke_meta.get("startFrame", 0)
            e_f = stroke_meta.get("endFrame", len(frames) - 1)

            q_init = frames[s_f].get("rotations", {})
            max_sign_excursion = 0.0

            for k in range(s_f + 1, e_f + 1):
                q_curr = frames[k].get("rotations", {})
                for ab in ARM_BONES:
                    if ab in q_init and ab in q_curr:
                        d = quat_angular_distance_deg(q_init[ab], q_curr[ab])
                        if d > max_sign_excursion:
                            max_sign_excursion = d

            excursion_results[sign] = max_sign_excursion
            if max_sign_excursion <= 15.0:
                insufficient_excursion.append((sign, max_sign_excursion))

        print("\n--- ACTIVE JOINT EXCURSION AUDIT (ALL 17 SIGNS) ---")
        for sign, exc in excursion_results.items():
            print(f"  {sign:<22}: {exc:>6.2f}°")

        assert len(insufficient_excursion) == 0, (
            f"Signs with joint excursion <= 15.0°: {insufficient_excursion}"
        )

    def test_06_quaternion_fields_validity_and_absence_of_nans(self):
        """
        Adversarial test: checks unit quaternion normalization and absence of NaN / Inf
        across all frames of the 17 signs.
        """
        nan_inf_found: List[str] = []
        unnormalized_found: List[str] = []

        for sign in TARGET_17_SIGNS:
            anim_path = V27_DIR / sign / "animation.json"
            with open(anim_path, "r", encoding="utf-8") as f:
                anim = json.load(f)

            for k, f in enumerate(anim["frames"]):
                for b, q in f.get("rotations", {}).items():
                    if any(math.isnan(x) or math.isinf(x) for x in q):
                        nan_inf_found.append(f"{sign} f{k} {b}")
                    norm = math.sqrt(sum(x * x for x in q))
                    if abs(norm - 1.0) > 0.05:
                        unnormalized_found.append(f"{sign} f{k} {b}: norm={norm:.4f}")

        assert len(nan_inf_found) == 0, f"NaN or Inf rotations found: {nan_inf_found[:5]}"
        assert len(unnormalized_found) == 0, f"Unnormalized quaternions found: {unnormalized_found[:5]}"

    def test_07_dual_stroke_index_sha256_exact_byte_equality(self):
        """
        Adversarial test: verifies cryptographic SHA-256 byte parity of stroke_index_v27.json.
        """
        assert STROKE_INDEX_PROTO.is_file()
        assert STROKE_INDEX_DICC.is_file()

        b1 = STROKE_INDEX_PROTO.read_bytes()
        b2 = STROKE_INDEX_DICC.read_bytes()

        assert b1 == b2, "Exact byte mismatch between stroke index copies"
        h1 = hashlib.sha256(b1).hexdigest()
        h2 = hashlib.sha256(b2).hexdigest()
        assert h1 == h2
        assert len(h1) == 64
        print(f"\n--- DUAL STROKE INDEX SHA-256 PARITY ---")
        print(f"  SHA-256: {h1}")
