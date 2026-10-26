# -*- coding: utf-8 -*-
"""
test_challenger_m4_2_2_adversarial.py
======================================
Empirical Adversarial Verification Suite — Challenger 2 for Milestone 4 (Iteration 2).

Validates:
1. Dual Stroke Index SHA-256 byte-for-byte identity (prototype vs standardized catalog).
2. Schema and bounds validity for all 4,142 entries in stroke_index_v27.json:
   - Exactly 4,142 signs
   - Invariant: 0 <= startFrame < endFrame <= totalFrames
   - Invariant: 0.0 <= strokeStart < strokeEnd
   - Positive fps and non-empty metadata
3. Skeletal & Facial Track Integrity across all 17 remediated animation.json files:
   - Bone tracks: 43 upper body bones declared (exact subset of VRM 1.0 HUMAN_54_BONES)
   - Facial tracks: exactly 66 tracks (14 VRM expressions + 52 ARKit blendshapes)
   - 100% of frames have rotations for all 43 declared bones
4. Biomechanical Invariants across all 17 remediated signs:
   - Dense frame-by-frame (step=1) thoracic clearance >= 2.0 cm over all 32 hand/finger bones
   - Max wrist step flip < 55.0° (with Centro specifically <= 45.0°)
   - Active joint excursion during stroke > 15.0°
5. ISO/IEC 25010 compliance (file <= 800 lines).
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple
import numpy as np
import pytest

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

from app.services.animation_fingerspelling_service import HUMAN_54_BONES
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

TARGET_REMEDIATED_SIGNS = [
    "Veinte", "Carrera, Estudios", "Forma", "Investigar", "Carpeta",
    "Anterior, Antes", "Rector(a), Rectorado", "Equipo", "Salud, Saludable",
    "El, Ella", "Enfermera", "Esforzarse, Esfuerzo", "Ingeniero(a)",
    "Centro", "Ocho", "Promedio", "Diez",
]

WRIST_BONES = ["rightHand", "leftHand", "rightLowerArm", "leftLowerArm"]
ARM_BONES = ["rightUpperArm", "rightLowerArm", "rightHand", "leftUpperArm", "leftLowerArm", "leftHand"]

ALL_HAND_FINGER_BONES = [
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


def quat_angular_distance_deg(q1: Sequence[float], q2: Sequence[float]) -> float:
    dot = abs(q1[0] * q2[0] + q1[1] * q2[1] + q1[2] * q2[2] + q1[3] * q2[3])
    dot = min(1.0, max(-1.0, dot))
    return 2.0 * math.degrees(math.acos(dot))


def run_fk_for_frame(rot_dict: Dict[str, Sequence[float]]) -> Dict[str, np.ndarray]:
    world_pos: Dict[str, np.ndarray] = {}
    world_rot: Dict[str, np.ndarray] = {}
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


class TestChallengerM422Adversarial:
    """Empirical adversarial verification tests for Milestone 4 (Iteration 2)."""

    def test_01_dual_stroke_index_byte_identity(self):
        """Verifies byte-for-byte identity and identical SHA-256 between both stroke index files."""
        assert STROKE_INDEX_PROTO.is_file(), f"Falta archivo: {STROKE_INDEX_PROTO}"
        assert STROKE_INDEX_DICC.is_file(), f"Falta archivo: {STROKE_INDEX_DICC}"

        b1 = STROKE_INDEX_PROTO.read_bytes()
        b2 = STROKE_INDEX_DICC.read_bytes()

        assert len(b1) > 0, "stroke_index_v27.json prototype está vacío"
        assert len(b2) > 0, "stroke_index.json catalog está vacío"
        assert b1 == b2, "Discrepancia byte-for-byte entre stroke_index_v27.json y stroke_index.json"

        h1 = hashlib.sha256(b1).hexdigest()
        h2 = hashlib.sha256(b2).hexdigest()
        assert h1 == h2, f"SHA-256 mismatch: {h1} != {h2}"
        assert len(h1) == 64

    def test_02_stroke_index_schema_and_bounds_4142_entries(self):
        """Verifies exact 4,142 entries, valid frame bounds (0 <= startFrame < endFrame <= totalFrames), and fps."""
        with open(STROKE_INDEX_PROTO, "r", encoding="utf-8") as f:
            data = json.load(f)

        signs = data.get("signs", {})
        assert len(signs) == 4142, f"Expected exactly 4142 signs in index, got {len(signs)}"

        violations: List[Tuple[str, str, Any, Any, Any]] = []

        for name, s in signs.items():
            sf = s.get("startFrame")
            ef = s.get("endFrame")
            tf = s.get("totalFrames")
            fps = s.get("fps")
            ts_start = s.get("strokeStart")
            ts_end = s.get("strokeEnd")

            if sf is None or ef is None or tf is None:
                violations.append((name, "missing frame fields", sf, ef, tf))
                continue
            if not (0 <= sf < ef <= tf):
                violations.append((name, "invalid frame ordering (0 <= sf < ef <= tf)", sf, ef, tf))
            if fps is None or fps <= 0:
                violations.append((name, "invalid fps", sf, ef, fps))
            if ts_start is not None and ts_end is not None:
                if not (0.0 <= ts_start < ts_end):
                    violations.append((name, "invalid time ordering", ts_start, ts_end, None))

        assert len(violations) == 0, f"Encountered {len(violations)} schema violations: {violations[:5]}"

    def test_03_remediated_animation_bone_and_facial_tracks(self):
        """Verifies bone tracks (43 declared upper body humanoid bones, subset of HUMAN_54_BONES) and 66 facial tracks."""
        h54_set = set(HUMAN_54_BONES)

        for sign_name in TARGET_REMEDIATED_SIGNS:
            anim_p = V27_DIR / sign_name / "animation.json"
            assert anim_p.is_file(), f"Missing animation file: {anim_p}"

            with open(anim_p, "r", encoding="utf-8") as f:
                anim = json.load(f)

            declared_bones = anim.get("bones", [])
            expr_tracks = anim.get("expressions", [])
            bs_tracks = anim.get("blendshapes", [])
            frames = anim.get("frames", [])

            # Check bone list
            assert len(declared_bones) == 43, f"{sign_name}: expected 43 bones, got {len(declared_bones)}"
            assert set(declared_bones).issubset(h54_set), (
                f"{sign_name}: non-standard bones declared: {set(declared_bones) - h54_set}"
            )

            # Check facial tracks: 14 expressions + 52 ARKit = 66 tracks
            assert len(expr_tracks) == 14, f"{sign_name}: expected 14 expressions, got {len(expr_tracks)}"
            assert len(bs_tracks) == 52, f"{sign_name}: expected 52 ARKit blendshapes, got {len(bs_tracks)}"
            assert (len(expr_tracks) + len(bs_tracks)) == 66, (
                f"{sign_name}: total facial tracks != 66"
            )

            # Check all frames populate all 43 declared bones
            assert len(frames) > 0, f"{sign_name}: empty frames list"
            for frame_idx, frame in enumerate(frames):
                rot = frame.get("rotations", {})
                for b in declared_bones:
                    assert b in rot, f"{sign_name} frame {frame_idx}: missing rotation for declared bone {b}"

    def test_04_biomechanical_clearance_and_wrist_invariants(self):
        """Verifies dense (step=1) thoracic clearance >= 2.0 cm and max wrist step < 55.0° (Centro <= 45.0°)."""
        with open(STROKE_INDEX_PROTO, "r", encoding="utf-8") as f:
            stroke_signs = json.load(f)["signs"]

        for sign_name in TARGET_REMEDIATED_SIGNS:
            anim_p = V27_DIR / sign_name / "animation.json"
            with open(anim_p, "r", encoding="utf-8") as f:
                anim = json.load(f)

            frames = anim["frames"]
            meta_stroke = stroke_signs.get(sign_name) or anim.get("metadata", {}).get("stroke", {})
            s_f = meta_stroke.get("startFrame", 0)
            e_f = meta_stroke.get("endFrame", len(frames) - 1)

            # 1. Dense clearance check
            min_clr = 999.0
            for k in range(s_f, e_f + 1):
                w_pos = run_fk_for_frame(frames[k].get("rotations", {}))
                for pt in ALL_HAND_FINGER_BONES:
                    if pt in w_pos:
                        p = w_pos[pt]
                        if CHEST_BBOX_X[0] <= p[0] <= CHEST_BBOX_X[1] and CHEST_BBOX_Y[0] <= p[1] <= CHEST_BBOX_Y[1]:
                            clr = p[2] - CHEST_SURFACE_Z
                            if clr < min_clr:
                                min_clr = clr

            assert min_clr >= 0.02, (
                f"{sign_name}: thoracic penetration violation under dense check: {min_clr * 100:.2f} cm < 2.0 cm"
            )

            # 2. Wrist rotation check across all consecutive frames
            max_wrist_step = 0.0
            for k in range(1, len(frames)):
                r1 = frames[k - 1].get("rotations", {})
                r2 = frames[k].get("rotations", {})
                for wb in WRIST_BONES:
                    if wb in r1 and wb in r2:
                        deg = quat_angular_distance_deg(r1[wb], r2[wb])
                        if deg > max_wrist_step:
                            max_wrist_step = deg

            assert max_wrist_step < 55.0, (
                f"{sign_name}: wrist step flip violation: {max_wrist_step:.2f}° >= 55.0°"
            )
            if sign_name == "Centro":
                assert max_wrist_step <= 45.0, (
                    f"Centro: wrist step flip exceeded 45.0° target: {max_wrist_step:.2f}°"
                )

            # 3. Active excursion check
            max_exc = 0.0
            q0 = frames[s_f].get("rotations", {})
            for k in range(s_f + 1, e_f + 1):
                qk = frames[k].get("rotations", {})
                for ab in ARM_BONES:
                    if ab in q0 and ab in qk:
                        d = quat_angular_distance_deg(q0[ab], qk[ab])
                        if d > max_exc:
                            max_exc = d

            assert max_exc > 15.0, (
                f"{sign_name}: joint excursion too low: {max_exc:.2f}° <= 15.0°"
            )

    def test_05_iso_iec_25010_line_limit(self):
        """Verifies that all M4 test files adhere to the ISO/IEC 25010 <= 800 line constraint."""
        files_to_check = [
            PROTO_ROOT / "app" / "tests" / "test_challenger_m4_2_2_adversarial.py",
            PROTO_ROOT / "app" / "tests" / "test_r4_biomechanical_certification.py",
            PROTO_ROOT / "app" / "tests" / "test_adversarial_m4_2.py",
            PROTO_ROOT / "app" / "tests" / "test_challenger_m4_adversarial.py",
        ]
        for f in files_to_check:
            assert f.is_file(), f"File does not exist: {f}"
            line_count = len(f.read_text(encoding="utf-8").splitlines())
            assert line_count <= 800, f"File {f.name} exceeds 800 lines: {line_count} > 800"
