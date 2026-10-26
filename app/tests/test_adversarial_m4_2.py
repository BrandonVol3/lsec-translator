# -*- coding: utf-8 -*-
"""
test_adversarial_m4_2.py
========================
Empirical Adversarial Verification Suite — Challenger M4.2.

Independently and empirically challenges:
1. Dual cryptographic parity (SHA-256) of stroke_index_v27.json.
2. Global stroke window validity (0 <= startFrame < endFrame < totalFrames) for ALL entries in stroke_index_v27.json (4,142+ signs).
3. Frame count synchronization between stroke_index and animation.json for all resolved signs and target remediated signs.
4. Zero (0) MISSING glosses across 1.mp4, 2.mp4, 3.mp4 (full & snippets) and all 20 validation corpus texts.
5. Absolute resolution integrity: every found sign has an existing animation.json in senas_vrm_standardized_v2.7/.
6. Biomechanical safety invariants: Centro wrist step rotation < 45.0° (< 55.0°) and all 17 target signs thoracic clearance >= 2.0 cm.
7. ISO/IEC 25010 line count compliance (all audited files <= 800 lines).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
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

from app.services.nlp_service import LSECTranslatorService
from app.services.animation_lexical_resolver import (
    resolve_batch_glosses_payload,
    resolve_gloss_to_sign,
)
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

# 20-text validation corpus + real video transcripts
VALIDATION_TEXTS: Dict[str, str] = {
    "1.mp4_real_full": (
        "Dicen que el conocimiento es poder, pero nadie te dice que también es libertad, "
        "libertad para decidir quién quieres ser. "
        "En la Politécnica del Carchi no solo eliges una carrera, eliges ser imparable. "
        "Con carreras de grado en los campus Tulcán y Cayambe nos enorgullece ser la universidad pública más sostenible del Ecuador. "
        "Formamos más que profesionales, formamos seres humanos que inspiran confianza y cercanía. "
        "Aquí te preparamos desde el primer día, con excelencia académica, con innovación, con tecnología que evoluciona contigo. "
        "Más de 4.500 graduados ya lo hicieron, hoy crean oportunidades, liberan y construyen ideas. "
        "Decide sobre tu futuro, haz posible hoy lo que imaginas. "
        "UPEC, educamos para transformar el mundo."
    ),
    "2.mp4_real_full": (
        "Te invitamos a formar parte del Centro Académico de Arte y Cultura. "
        "En donde te puedes inscribir en las diferentes asignaturas de cuerpo y movimiento. "
        "Apreciación de la música en el Ecuador y dibujo experimental. "
        "Para más información comunícate al WhatsApp 099 28 72 993 o al correo seartes@upec.edu.ec"
    ),
    "3.mp4_real_full": (
        "Al momento la UPEC registra alrededor de 3.000 aspirantes que están opcionando para un cupo. "
        "A partir de las 8 y cuarto realizamos la jornada de inducción para nuevos estudiantes."
    ),
    "1.mp4_whisper_variant": (
        "Regístrate en www.upec.edu.ec y postula por una de nuestras carreras de grado. "
        "Estandel Karczym 20-26a."
    ),
    "2.mp4_whisper_variant": (
        "Para mayor información comunícate al 099 28 72 993 o al correo seartes@upec.edu.ec."
    ),
    "3.mp4_whisper_variant": (
        "Si estás opcionando por una carrera focalizada, desarrolla la etapa de evaluación "
        "en el horario determinado."
    ),
    "text_4": "La evaluación de admisión en la mañana incluye música, diseño y tecnología.",
    "text_5": "Hoy los aspirantes revisan la oferta en los campos de Tulcán y Cayambe.",
    "text_6": "Invitamos a los cuatro mil quinientos graduados y a los tres mil aspirantes.",
    "text_7": "Aunque hace frío y calor, mi ñaño y mi pana revisan el formulario de inscripción.",
    "text_8": "Si mañana no llueve, realizaremos la jornada de integración.",
    "text_9": "Los programas presenciales y semipresenciales promueven el desarrollo sostenible.",
    "text_10": "Nuestros docentes investigan nuevas formas de enseñar.",
    "text_11": (
        "En el año 2026 la beca estudiantil cubre el cien por ciento de la matrícula "
        "para quinientos veinte estudiantes y el ochenta y cinco por ciento para "
        "ciento cincuenta becarios nuevos. El primer grupo entregará los requisitos "
        "el 15 de mayo desde las 14:15 hasta las 16:30, mientras que el segundo, "
        "tercer y quinto grupo asistirán el 22 de mayo. Para aprobar necesitas un "
        "promedio mínimo de nueve punto cinco sobre diez."
    ),
    "text_12": (
        "En la secretaría de la facultad se revisaron las carpetas y se entregaron "
        "los certificados a quienes se inscribieron a tiempo. Si el comprobante está "
        "listo, pídeselo al coordinador o dímelo hoy para enviártelo por correo "
        "electrónico. En la UPEC nos apoyamos mutuamente, nos comunicamos con respeto "
        "y nos preparamos para graduarnos juntos."
    ),
    "text_13": (
        "Los aspirantes que han completado el registro tienen que presentar el "
        "formulario firmado y la cédula actualizada. Mañana vamos a construir nuevos "
        "espacios de investigación porque debemos seguir fortaleciendo el proyecto "
        "aprobado por el consejo universitario. Si vuelves a intentar la prueba, "
        "podrás alcanzar el puntaje requerido sin dificultad."
    ),
    "text_14": (
        "Antes nosotros no sabíamos cómo usar la plataforma, no podíamos subir las "
        "tareas y no nos gustaba estudiar en línea. Sin embargo, hoy nadie se queda "
        "atrás: no tenemos ningún problema ni ninguna duda porque el sistema nunca "
        "falla. Si mañana no hay internet en tu casa y no quieres perder la clase, "
        "tampoco te preocupes, porque ningún docente te pondrá falta."
    ),
    "text_15": (
        "Yo estudio en la biblioteca porque el estudio constante mejora mi "
        "rendimiento, y luego trabajo en el laboratorio donde presento mi trabajo "
        "final. Cuando el profesor pregunta sobre la práctica profesional, cada "
        "estudiante presente muestra su informe y practica la exposición frente a la "
        "muestra científica. Solicita ayuda en bienestar estudiantil si necesitas que "
        "alguien te ayude hoy."
    ),
    "text_16": (
        "Estudiamos desde temprano con entusiasmo para transformar nuestra provincia "
        "y trabajamos por el bienestar de la comunidad sin descanso. Durante el "
        "semestre debatimos sobre inteligencia artificial entre compañeros según el "
        "cronograma académico. Hasta el viernes puedes postular para la beca de "
        "movilidad hacia universidades extranjeras."
    ),
    "text_17": (
        "¿Con quién debemos hablar para legalizar la matrícula y en dónde queda la "
        "oficina de admisión? ¿Desde cuándo están abiertas las inscripciones para "
        "nivelación y hasta qué hora atienden hoy? ¿Cuál de las carreras de la UPEC "
        "prefieres estudiar, cómo piensas financiar tus estudios y por qué elegiste "
        "esta universidad?"
    ),
    "text_18": (
        "Eh... o sea, en la en la universidad nos pidieron llegar tempranito, así que "
        "ven ahorita mismo rapidito. ¡Atatai, qué sucio está ese piso por la lluvia!, "
        "y ¡ayayay, me duele la cabeza!, pero de ley mi ñaño y mi guagua entran hoy a "
        "clases. Por favor, dame viendo si ya abrieron el aula y deme avisando al "
        "WhatsApp tres cero cinco veinte dieciocho o al correo bienestar arroba upec "
        "punto edu punto ec."
    ),
    "text_19": (
        "El rector se reunió ayer con la directora de carrera en el edificio central; "
        "él le solicitó a ella el informe de evaluación y ella se lo entregó antes del "
        "mediodía. Después, ambos conversaron con los docentes y les explicaron que "
        "este semestre recibirán equipamiento nuevo en sus laboratorios."
    ),
    "text_20": (
        "La educación intercultural bilingüe y la investigación lingüística tienen "
        "gran antigüedad y prestigio en nuestra frontera norte. En coordinación con "
        "la SENESCYT, el CES y el CONADIS, la UPEC ofrece carreras como Ingeniería en "
        "Computación, Comercio Exterior, Administración de Empresas, Enfermería, "
        "Turismo, Agropecuaria y Educación Inicial. ¡Inscríbete hoy: \"Tu esfuerzo "
        "construye el mañana\"!"
    ),
}

TARGET_THORACIC_17_SIGNS = [
    "Veinte", "Carrera, Estudios", "Forma", "Investigar", "Carpeta",
    "Anterior, Antes", "Rector(a), Rectorado", "Equipo", "Salud, Saludable",
    "El, Ella", "Enfermera", "Esforzarse, Esfuerzo", "Ingeniero(a)",
    "Centro", "Ocho", "Promedio", "Diez",
]

WRIST_BONES = ["rightHand", "leftHand", "rightLowerArm", "leftLowerArm"]
EVAL_CHEST_BONES = [
    "rightHand", "leftHand",
    "rightIndexDistal", "leftIndexDistal",
    "rightMiddleDistal", "leftMiddleDistal",
    "rightThumbDistal", "leftThumbDistal",
    "rightRingDistal", "leftRingDistal",
    "rightLittleDistal", "leftLittleDistal",
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


class TestAdversarialM42:
    """Empirical challenge suite for M4 timing, stroke windows, and 0 MISSING glosses."""

    def test_01_dual_stroke_index_sha256_cryptographic_parity(self):
        """Item 1: Cryptographic parity between prototype and standardized dictionary copies."""
        assert STROKE_INDEX_PROTO.is_file(), f"Falta archivo prototype: {STROKE_INDEX_PROTO}"
        assert STROKE_INDEX_DICC.is_file(), f"Falta archivo diccionario: {STROKE_INDEX_DICC}"

        bytes_proto = STROKE_INDEX_PROTO.read_bytes()
        bytes_dicc = STROKE_INDEX_DICC.read_bytes()

        assert len(bytes_proto) > 0, "stroke_index_v27.json prototype está vacío"
        assert len(bytes_dicc) > 0, "stroke_index.json diccionario está vacío"
        assert bytes_proto == bytes_dicc, "Discrepancia exacta a nivel de bytes entre índices duales"

        h_proto = hashlib.sha256(bytes_proto).hexdigest()
        h_dicc = hashlib.sha256(bytes_dicc).hexdigest()
        assert h_proto == h_dicc, f"Discrepancia SHA-256: {h_proto} != {h_dicc}"
        assert len(h_proto) == 64

    def test_02_global_stroke_windows_validity_all_entries(self):
        """Item 2: For ALL entries in stroke_index_v27.json, assert 0 <= startFrame < endFrame < totalFrames."""
        with open(STROKE_INDEX_PROTO, "r", encoding="utf-8") as f:
            data = json.load(f)

        signs = data.get("signs", {})
        total_signs = len(signs)
        assert total_signs >= 4142, f"Total de señas indexadas insuficiente: {total_signs} < 4142"

        invalid_entries: List[Tuple[str, Any, Any, Any, str]] = []
        zero_length_strokes: List[str] = []

        for sign_name, info in signs.items():
            if not isinstance(info, dict):
                invalid_entries.append((sign_name, None, None, None, "Entry is not a dictionary"))
                continue

            s_f = info.get("startFrame")
            e_f = info.get("endFrame")
            t_f = info.get("totalFrames")

            if s_f is None or e_f is None or t_f is None:
                invalid_entries.append((sign_name, s_f, e_f, t_f, "Missing frame fields"))
                continue

            if not (isinstance(s_f, int) and isinstance(e_f, int) and isinstance(t_f, int)):
                invalid_entries.append((sign_name, s_f, e_f, t_f, "Frame fields are not integers"))
                continue

            if not (0 <= s_f < e_f < t_f):
                invalid_entries.append((sign_name, s_f, e_f, t_f, "Violates 0 <= startFrame < endFrame < totalFrames"))

            if e_f <= s_f:
                zero_length_strokes.append(sign_name)

        assert len(invalid_entries) == 0, (
            f"Se encontraron {len(invalid_entries)} señas con ventanas de stroke inválidas en el índice global: {invalid_entries[:10]}"
        )
        assert len(zero_length_strokes) == 0

    def test_03_stroke_total_frames_matches_disk_animation_json(self):
        """Item 2 Extension: Verify totalFrames in index matches actual len(frames) in animation.json for target signs."""
        with open(STROKE_INDEX_PROTO, "r", encoding="utf-8") as f:
            stroke_signs = json.load(f)["signs"]

        # Check all 17 target thoracic signs + Centro
        signs_to_check = set(TARGET_THORACIC_17_SIGNS) | {"Centro"}
        mismatches: List[Tuple[str, int, int]] = []

        for s in sorted(signs_to_check):
            anim_p = V27_DIR / s / "animation.json"
            assert anim_p.is_file(), f"No existe animación para seña objetivo: {s}"
            with open(anim_p, "r", encoding="utf-8") as f:
                anim = json.load(f)
            actual_f = len(anim.get("frames", []))
            indexed_f = stroke_signs[s]["totalFrames"]
            if actual_f != indexed_f:
                mismatches.append((s, indexed_f, actual_f))

        assert len(mismatches) == 0, f"Discrepancia en totalFrames entre index y animation.json: {mismatches}"

    def test_04_zero_missing_glosses_corpus_and_videos(self):
        """Item 3: Translate all 20 texts in validation corpus + 1.mp4, 2.mp4, 3.mp4 and assert 0 MISSING."""
        svc = LSECTranslatorService()
        missing_records: List[Dict[str, Any]] = []
        total_glosses_evaluated = 0
        unique_resolved_folders: Set[str] = set()

        for text_key, raw_text in VALIDATION_TEXTS.items():
            translation = asyncio.run(
                svc.translate_to_gloss(raw_text, mode="detailed", paraphrase_budget="compact")
            )
            gloss_tokens = [g.gloss for g in translation.glosses]
            total_glosses_evaluated += len(gloss_tokens)

            # Test individual resolution
            for g in gloss_tokens:
                res = resolve_gloss_to_sign(g, version="2.7", include_animation=False)
                status = res.get("status")
                found = res.get("found", False)
                is_fs = res.get("is_fingerspelling", False)

                if status == "MISSING" or (not found and not is_fs and "-" not in g):
                    missing_records.append({
                        "text": text_key,
                        "gloss": g,
                        "status": status,
                        "res": res,
                    })
                elif found:
                    folder = res.get("sign_folder") or res.get("resolved_gloss")
                    if folder:
                        unique_resolved_folders.add(folder)

            # Test batch resolution endpoint
            batch_payload = {"glosses": gloss_tokens, "version": "2.7", "include_animation": False}
            batch_res = resolve_batch_glosses_payload(batch_payload)
            batch_missing = [it["gloss"] for it in batch_res.get("items", []) if it.get("status") == "MISSING"]
            if batch_missing:
                missing_records.append({
                    "text": text_key,
                    "batch_missing": batch_missing,
                })

        assert total_glosses_evaluated > 200, f"Conteo de glosas evaluadas muy bajo: {total_glosses_evaluated}"
        assert len(missing_records) == 0, f"Glosas MISSING detectadas en corpus/videos: {missing_records}"

        # Assert every found sign folder actually exists on disk in v2.7
        missing_folders_on_disk: List[str] = []
        for folder in unique_resolved_folders:
            anim_file = V27_DIR / folder / "animation.json"
            if not anim_file.is_file():
                missing_folders_on_disk.append(folder)

        assert len(missing_folders_on_disk) == 0, (
            f"Carpetas resueltas no existen en disco ({V27_DIR}): {missing_folders_on_disk}"
        )

    def test_05_centro_wrist_rotation_adversarial_bound(self):
        """Item 4: Centro wrist flip step rotation strictly < 45.0° (requirement < 55.0°)."""
        centro_path = V27_DIR / "Centro" / "animation.json"
        assert centro_path.is_file()
        with open(centro_path, "r", encoding="utf-8") as f:
            anim = json.load(f)

        frames = anim["frames"]
        max_step_flip = 0.0
        worst_frame = -1
        worst_bone = ""

        for k in range(1, len(frames)):
            r_prev = frames[k - 1].get("rotations", {})
            r_curr = frames[k].get("rotations", {})
            for wb in WRIST_BONES:
                if wb in r_prev and wb in r_curr:
                    deg = quat_angular_distance_deg(r_prev[wb], r_curr[wb])
                    if deg > max_step_flip:
                        max_step_flip = deg
                        worst_frame = k
                        worst_bone = wb

        assert max_step_flip < 55.0, f"Centro excede 55.0°: {max_step_flip:.2f}° en frame {worst_frame} ({worst_bone})"
        assert max_step_flip <= 45.0, f"Centro excede 45.0° objetivo: {max_step_flip:.2f}° en frame {worst_frame} ({worst_bone})"

    def test_06_thoracic_clearance_all_17_target_signs(self):
        """Item 4: Direct kinematic FK confirms >= 2.0 cm thoracic clearance on all 17 remediated signs."""
        with open(STROKE_INDEX_PROTO, "r", encoding="utf-8") as f:
            stroke_data = json.load(f)["signs"]

        failures: List[Tuple[str, float]] = []

        for sign in TARGET_THORACIC_17_SIGNS:
            anim_path = V27_DIR / sign / "animation.json"
            assert anim_path.is_file()
            with open(anim_path, "r", encoding="utf-8") as f:
                anim = json.load(f)

            frames = anim["frames"]
            stroke_info = stroke_data.get(sign) or {}
            s_f = stroke_info.get("startFrame", 0)
            e_f = stroke_info.get("endFrame", len(frames) - 1)
            step = max(1, (e_f - s_f + 1) // 10)

            min_clr = 999.0
            for k in range(s_f, e_f + 1, step):
                w_pos = run_fk_for_frame(frames[k]["rotations"])
                for pt in EVAL_CHEST_BONES:
                    if pt in w_pos:
                        p = w_pos[pt]
                        if CHEST_BBOX_X[0] <= p[0] <= CHEST_BBOX_X[1] and CHEST_BBOX_Y[0] <= p[1] <= CHEST_BBOX_Y[1]:
                            z_clr = p[2] - CHEST_SURFACE_Z
                            if z_clr < min_clr:
                                min_clr = z_clr

            if min_clr < 0.020:
                failures.append((sign, min_clr * 100.0))

        assert len(failures) == 0, f"Señas con margen torácico < 2.0 cm: {failures}"

    def test_07_iso_iec_25010_line_count_limits(self):
        """ISO/IEC 25010 maintainability rule: all created/modified files <= 800 lines."""
        files_to_check = [
            PROTO_ROOT / "app" / "tests" / "test_r4_biomechanical_certification.py",
            PROTO_ROOT / "app" / "tests" / "test_adversarial_m4_2.py",
            WORKSPACE_ROOT / "Diccionario LSEC" / "tools" / "apply_biomechanical_remediations.py",
        ]
        for fpath in files_to_check:
            if fpath.is_file():
                lines = len(fpath.read_text(encoding="utf-8").splitlines())
                assert lines <= 800, f"Violación ISO/IEC 25010: {fpath.name} tiene {lines} líneas (> 800)"
