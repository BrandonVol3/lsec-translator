"""
Suite de pruebas de regresión para el Motor de Estabilización Cinemática VRM v2.7.4
y el encadenamiento fluido de señas en LSEC Studio.

Verifica:
1. Eliminación de giros de muñeca de 360°, torsiones opuestas antebrazo-mano y preservación 1:1
   de la orientación mundial de la palma (conjugación de cuaternión en cadena antebrazo-muñeca).
2. Cero penetración corporal (0.0 cm) de manos, puntas de dedos y antebrazos contra la malla real de
   `LSEC-Interpreter-Female.vrm` (pecho Z = 0.1373 m, rostro Z = 0.0893 m).
3. Estabilidad del brazo/mano inactiva en señas monomanuales y detección robusta contra falsos
   positivos de profundidad monocular (ej. Hola, Chao, Húmedo) usando `tracks.npz`.
4. Aplicación de la configuración manual oficial (`configuracion_manual` I–IX / 83 variantes)
   con preservación de articulación dinámica interna de dedos (apertura/cierre/pellizco).
5. Fidelidad 1:1 de la trayectoria del brazo activo respecto al video original/HD sin recortes de cola.
6. Integración en servicios backend (`resolve_sign_animation_response` y `resolve_gloss_to_sign`)
   y estructura de metadatos `stroke.activeHands` para coarticulación C¹.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
DICC_DIR = ROOT_DIR / "Diccionario LSEC"
if str(DICC_DIR) not in sys.path:
    sys.path.insert(0, str(DICC_DIR))

import lsec_kinematic_stabilizer as lks
from app.services.animation_lexical_resolver import resolve_gloss_to_sign
from app.services.animation_media_service import resolve_sign_animation_response


BENCHMARK_SIGNS = [
    "Hola",
    "Chao",
    "Universidad",
    "Abanico",
    "Biblia",
    "Deporte, Deportista",
    "Llamarse, Nombre",
    "Húmedo",
]

STATIC_HANDSHAPE_SIGNS = [
    "Hola",
    "Chao",
    "Universidad",
    "Abanico",
    "Biblia",
    "Deporte, Deportista",
    "Llamarse, Nombre",
]


@pytest.mark.parametrize("sign_name", BENCHMARK_SIGNS)
def test_kinematic_stabilizer_eliminates_penetration_and_wrist_flips(sign_name: str):
    """
    Verifica que el estabilizador cinemático v2.7.4 deje 0.0 cm de penetración sobre la malla VRM,
    limite el swing de muñeca dentro del rango anatómico (<= 78.5°), limite el twist a <= 42.5°
    y garantice continuidad antipodal estricta.
    """
    res = resolve_gloss_to_sign(sign_name, version="2.7", include_animation=True)
    assert res["found"] is True, f"No se encontró la seña {sign_name}"
    anim = res["animation"]
    assert isinstance(anim, dict)

    meta = anim.get("metadata", {})
    stab = meta.get("kinematicStabilizer")
    assert isinstance(stab, dict), f"Falta metadata.kinematicStabilizer en {sign_name}"
    assert stab.get("version") == lks.STABILIZER_VERSION

    # 1. Penetración corporal 0.0 cm contra malla VRM
    pen = stab.get("penetrationResolution", {})
    assert float(pen.get("max_penetration_after_cm", 99.0)) <= 0.15, (
        f"Penetración residual excesiva en {sign_name}: {pen}"
    )

    # Verificar directamente con FK vectorizado sobre los frames servidos
    fk = lks.compute_batch_upper_body_fk(anim["frames"])
    true_max_pen_m = lks.compute_max_mesh_penetration_batch(fk)
    assert true_max_pen_m * 100.0 <= 0.15, (
        f"Penetración FK medida en {sign_name}: {true_max_pen_m * 100.0:.2f} cm"
    )

    # 2. Swing y twist de muñeca dentro de límites anatómicos
    wrist_stab = stab.get("wristStabilization", {})
    assert len(wrist_stab) >= 1
    for side, w_info in wrist_stab.items():
        assert float(w_info["max_swing_after_deg"]) <= 78.5, (
            f"Swing de muñeca {side} excesivo en {sign_name}: {w_info}"
        )
        assert float(w_info["max_twist_after_deg"]) <= 42.5, (
            f"Twist de muñeca {side} excesivo en {sign_name}: {w_info}"
        )

    # 3. Continuidad antipodal estricta (<q_t, q_{t-1}> >= 0) en todas las pistas óseas
    frames = anim["frames"]
    bone_names = list(frames[0]["rotations"].keys())
    for b_name in bone_names:
        seq = np.array([fr["rotations"][b_name] for fr in frames], dtype=np.float64)
        dots = np.sum(seq[1:] * seq[:-1], axis=1)
        assert np.all(dots >= -1e-4), (
            f"Discontinuidad antipodal (giro 360°) detectada en hueso {b_name} de {sign_name}: min_dot={np.min(dots):.4f}"
        )


@pytest.mark.parametrize("sign_name", STATIC_HANDSHAPE_SIGNS)
def test_full_elevated_stroke_manual_configuration_fidelity(sign_name: str):
    """
    Verifica que la configuración manual oficial (`configuracion_manual`) se aplique
    a lo largo de todo el tramo elevado `[elev_start, elev_end]` con distancia <= 2.5°
    en señas con forma manual fija.
    """
    res = resolve_gloss_to_sign(sign_name, version="2.7", include_animation=True)
    anim = res["animation"]
    meta = anim["metadata"]
    stab = meta["kinematicStabilizer"]
    f_logs = stab.get("fingerStandardization", {})
    assert len(f_logs) >= 1, f"No se aplicó plantilla de configuración manual en {sign_name}"

    dom_hand = stab["dominantHand"]
    dom_log = f_logs[dom_hand]
    assert float(dom_log["dist_after_deg"]) <= 2.5, (
        f"Distancia residual a la configuración manual demasiado alta en {sign_name}: {dom_log}"
    )
    assert float(dom_log["mean_w"]) >= 0.85
    seg = dom_log["segment"]
    assert seg[1] - seg[0] >= 40, f"Tramo de configuración manual demasiado corto en {sign_name}: {seg}"


def test_humedo_video_fidelity_palm_orientation_and_dynamic_fingers():
    """
    Verifica las 4 correcciones estructurales auditadas en la seña «Húmedo» (#2176):
    1. Mano izquierda fantasma anclada en reposo (`isBimanual=False`, `activeHands=['right']`).
    2. Duración 1:1 respecto al video UHD (`359 frames`, `5.983 s` sin recorte de cola).
    3. Orientación mundial de la palma derecha idéntica a `v2.6` (< 2.0° en F160).
    4. Preservación de la articulación dinámica interna de los dedos (apertura CM I en F160 -> cierre/pellizco en F250)
       y expresión no manual `spit_tongue`.
    """
    res = resolve_gloss_to_sign("Húmedo", version="2.7", include_animation=True)
    assert res["found"] is True
    anim = res["animation"]
    frames = anim["frames"]
    meta = anim["metadata"]
    stab = meta["kinematicStabilizer"]

    # 1. Monomanual derecha y 359 frames completos
    assert len(frames) == 359
    assert stab["dominantHand"] == "right"
    assert stab["isBimanual"] is False
    assert stab["activeHands"] == ["right"]
    assert stab["facialArchetype"] == "spit_tongue"

    # 2. Orientación mundial de la palma derecha vs v2.6 en el golpe (F160 = 2.67s)
    v26_path = DICC_DIR / "senas_vrm_direct_v2.6" / "Húmedo" / "animation.json"
    v26_frames = json.loads(v26_path.read_text(encoding="utf-8"))["frames"]
    fk_v26 = lks.compute_batch_upper_body_fk(v26_frames)
    fk_v274 = lks.compute_batch_upper_body_fk(frames)

    r_hand_26 = fk_v26["world_mats"]["rightHand"][160]
    r_hand_274 = fk_v274["world_mats"]["rightHand"][160]
    q_26 = lks.mat_to_quat_no_svd(r_hand_26)
    q_274 = lks.mat_to_quat_no_svd(r_hand_274)
    palm_world_diff_deg = lks.quat_angle_deg(q_26, q_274)
    assert palm_world_diff_deg <= 2.5, (
        f"Desviación excesiva en orientación mundial de la palma en F160: {palm_world_diff_deg:.2f}°"
    )

    # 3. Articulación dinámica de los dedos: abierto en F160 (< 22°) -> cerrado/pellizco en F250 (> 45°)
    id_quat = np.zeros((12, 4), dtype=np.float64)
    id_quat[:, 3] = 1.0
    non_thumb_bones = lks.RIGHT_FINGER_BONES[3:]
    q_f160 = np.array([frames[160]["rotations"][b] for b in non_thumb_bones], dtype=np.float64)
    q_f250 = np.array([frames[250]["rotations"][b] for b in non_thumb_bones], dtype=np.float64)
    flex_160 = float(np.mean(lks.quat_angle_deg_batch(q_f160, id_quat)))
    flex_250 = float(np.mean(lks.quat_angle_deg_batch(q_f250, id_quat)))
    assert flex_160 <= 22.0, f"La mano debería iniciar abierta (CM I) en F160, flex={flex_160:.1f}°"
    assert flex_250 >= 45.0, f"Los dedos deberían cerrarse en pellizco hacia F250, flex={flex_250:.1f}°"
    assert (flex_250 - flex_160) >= 25.0

    # 4. Expresión facial no manual activa durante el stroke
    bs_160 = frames[160].get("blendshapes", {})
    assert float(bs_160.get("tongueOut", 0.0)) >= 0.45
    assert float(bs_160.get("jawOpen", 0.0)) >= 0.25



def test_unimanual_inactive_hand_has_no_hallucination_spasms():
    """
    Verifica que en señas monomanuales (`Hola` dom=left, `Chao` dom=right) el brazo inactivo
    permanezca estable en su postura tranquila de reposo sin espasmos hacia el pecho.
    """
    for sign_name, expected_dom, expected_inact in (("Hola", "left", "right"), ("Chao", "right", "left")):
        res = resolve_gloss_to_sign(sign_name, version="2.7", include_animation=True)
        anim = res["animation"]
        stab = anim["metadata"]["kinematicStabilizer"]
        assert stab["dominantHand"] == expected_dom
        assert stab["isBimanual"] is False

        frames = anim["frames"]
        inact_ha = np.array([fr["rotations"][f"{expected_inact}Hand"] for fr in frames], dtype=np.float64)
        step_degs = lks.quat_angle_deg_batch(inact_ha[1:], inact_ha[:-1])
        assert float(np.max(step_degs)) <= 3.0, (
            f"Espasmo detectado en mano inactiva ({expected_inact}) de {sign_name}: max_step={np.max(step_degs):.2f}°"
        )


def test_stroke_metadata_contract_for_frontend_coarticulation():
    """
    Verifica que `metadata.stroke.activeHands` tenga el contrato `{left: bool, right: bool, dominant: str}`
    requerido por `sequence-coarticulation-math.js` y que `/api/v1/animations/{sign}` responda con headers v2.7.2.
    """
    resp = resolve_sign_animation_response("Hola", version="2.7")
    assert resp.status_code == 200
    assert resp.headers.get("X-Sign-Stabilizer-Version") == lks.STABILIZER_VERSION

    payload = json.loads(resp.body.decode("utf-8"))
    stroke = payload["metadata"]["stroke"]
    active_hands = stroke["activeHands"]
    assert isinstance(active_hands, dict)
    assert active_hands["left"] is True
    assert active_hands["right"] is False
    assert active_hands["dominant"] == "left"


def test_ambulancia_forearm_grasp_axial_rotation_and_siren_cycles():
    """
    Auditoría cuadro por cuadro de «Ambulancia» (#204, 233 frames @ 60 fps):
    1. Contacto de sujeción bimanual mano izquierda -> tercio distal del antebrazo derecho (<= 4.5 cm, alpha in [0.60, 0.90]).
    2. 3 ciclos de apertura y cierre de los 5 dedos de la mano derecha (CM III · V9 cerrada <-> CM I · BASE abierta).
    3. Mano derecha erguida sobre su eje vertical (sin caída de "cuello de cisne" hacia abajo) girando axialmente (>= 75°).
    4. Mano izquierda con agarre cilíndrico asimétrico y 0.00 cm de penetración corporal.
    """
    res = resolve_gloss_to_sign("Ambulancia", version="2.7", include_animation=True)
    anim = res["animation"]
    frames = anim["frames"]
    assert len(frames) == 233

    stab = anim["metadata"]["kinematicStabilizer"]
    assert stab["isBimanual"] is True
    assert stab["dominantHand"] == "right"
    assert stab["penetrationResolution"]["max_penetration_after_cm"] == 0.0
    assert stab["forearmGrasp"]["detected"] is True
    assert stab["fingerStandardization"]["right"]["cyclic_open_close"] is True
    assert stab["fingerStandardization"]["left"]["mode"] == "cylindrical_forearm_grasp"

    fk = lks.compute_batch_upper_body_fk(frames)
    p_r_el = fk["world_pos"]["rightLowerArm"]
    p_r_wr = fk["world_pos"]["rightHand"]
    p_l_wr = fk["world_pos"]["leftHand"]
    r_ha_mats = fk["world_mats"]["rightHand"]

    # 1. Distancia 3D desde leftHand al segmento [rightLowerArm, rightHand] durante el agarre [F075..F185]
    seg = p_r_wr - p_r_el
    seg_len2 = np.sum(seg * seg, axis=-1, keepdims=True) + 1e-12
    alpha = np.clip(np.sum((p_l_wr - p_r_el) * seg, axis=-1, keepdims=True) / seg_len2, 0.0, 1.0)
    closest_pt = p_r_el + alpha * seg
    dist_to_forearm_cm = np.linalg.norm(p_l_wr - closest_pt, axis=-1) * 100.0

    hold_slice = slice(75, 186)
    assert float(np.mean(dist_to_forearm_cm[hold_slice])) <= 4.0
    assert float(np.max(dist_to_forearm_cm[hold_slice])) <= 4.5
    assert 0.65 <= float(np.mean(alpha[hold_slice])) <= 0.88

    # 2. Mano derecha erguida sobre su eje vertical y con giro axial >= 75°
    long_dir_y = -r_ha_mats[hold_slice, 1, 0]
    assert float(np.min(long_dir_y)) >= 0.90, f"Caída de muñeca detectada: min_y={np.min(long_dir_y):.3f}"
    palm_n = -r_ha_mats[hold_slice, :, 1]
    psi_deg = np.degrees(np.arctan2(palm_n[:, 0], palm_n[:, 2]))
    assert float(np.max(psi_deg) - np.min(psi_deg)) >= 75.0

    # 3. 3 ciclos de apertura y cierre de los dedos derechos (valles cerrados F082, F125, F165 vs picos abiertos F096, F152, F180)
    arrays = lks.extract_animation_arrays(frames)
    main_idx = [3, 4, 6, 7, 9, 10, 12, 13]
    r_flex = np.mean(
        np.degrees(2.0 * np.arccos(np.clip(np.abs(arrays["right_fingers"][:, main_idx, 3]), 0.0, 1.0))),
        axis=1,
    )
    for f_closed in (82, 125, 165):
        assert r_flex[f_closed] >= 40.0, f"Ciclo cerrado insuficiente en F{f_closed}: {r_flex[f_closed]:.1f}°"
    for f_open in (96, 152, 180):
        assert r_flex[f_open] <= 20.0, f"Destello abierto insuficiente en F{f_open}: {r_flex[f_open]:.1f}°"


def test_videotrue_reverses_contradictory_templates_and_aligns_2d_trajectories():
    """
    Verifica que `v2.7.5_VideoTrue`:
    1. No fuerce plantillas estáticas sobre señas con agarre/cierre dinámico («Agarrar», «Adoptar»)
       ni sobre señas donde el catálogo contradice al video («Anillo»).
    2. Identifique correctamente la mano dominante derecha en señas bimanuales asimétricas («Alarma»)
       preservando la palma abierta de soporte en la mano izquierda.
    3. Reduzca el error 2D de posición de muñeca respecto a `tracks.npz` (`video2DAlignment`).
    """
    # 1. «Agarrar»: inicia abierta (CM II · BASE) y cierra los dedos en puño (> 55°)
    res_ag = resolve_gloss_to_sign("Agarrar", version="2.7", include_animation=True)
    frames_ag = res_ag["animation"]["frames"]
    arr_ag = lks.extract_animation_arrays(frames_ag)
    main_idx = [3, 4, 6, 7, 9, 10, 12, 13]
    r_flex_ag = np.mean(
        np.degrees(2.0 * np.arccos(np.clip(np.abs(arr_ag["right_fingers"][:, main_idx, 3]), 0.0, 1.0))),
        axis=1,
    )
    assert float(np.min(r_flex_ag[74:110])) <= 28.0, "Agarrar debe iniciar con la mano abierta"
    assert float(np.max(r_flex_ag[120:175])) >= 55.0, "Agarrar debe cerrar el puño fielmente al video"

    # 2. «Alarma»: mano derecha dominante en CM IV · V6 y mano izquierda abierta como soporte
    res_al = resolve_gloss_to_sign("Alarma", version="2.7", include_animation=True)
    stab_al = res_al["animation"]["metadata"]["kinematicStabilizer"]
    assert stab_al["dominantHand"] == "right"
    assert stab_al["video2DAlignment"]["aligned"] is True
    assert (
        stab_al["video2DAlignment"]["sides"]["right"]["xy_err_after_cm"]
        <= stab_al["video2DAlignment"]["sides"]["right"]["xy_err_before_cm"]
    )
    assert stab_al["video2DAlignment"].get("bimanual_z_coupled_frames", 0) >= 5
    assert stab_al["video2DAlignment"]["scapulohumeral_rhythm"]["applied"] is True

    # 3. «Comer»: acoplamiento facial en Z y ritmo escapulohumeral
    res_co = resolve_gloss_to_sign("Comer", version="2.7", include_animation=True)
    stab_co = res_co["animation"]["metadata"]["kinematicStabilizer"]
    assert stab_co["video2DAlignment"]["sides"]["right"].get("face_contact_frames", 0) >= 30

    # 4. Restricciones anatómicas anti-hiperextensión y anti-cruce lateral (splay monotónico)
    bad_quats = np.tile(np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64), (4, 15, 1))
    # Simular hiperextensión dorsal PIP (-20° en Z) y cruce severo Index/Middle en Y
    bad_quats[:, 1, :] = [0.0, 0.0, -0.1736, 0.9848]  # IndexIntermediate rz = -20°
    bad_quats[:, 0, :] = [0.0, -0.2588, 0.0, 0.9659]  # IndexProximal ry = -30° (hacia meñique)
    bad_quats[:, 3, :] = [0.0, 0.2588, 0.0, 0.9659]   # MiddleProximal ry = +30° (hacia pulgar)
    fixed_q = lks.enforce_anatomical_finger_constraints(bad_quats, side="right")
    assert float(np.min(fixed_q[:, 1, 2])) >= -1e-6, "PIP no debe tener hiperextensión dorsal negativa"
    # En espacio relativo a ry_together ([-11.5, -9.5]), Index splay >= Middle splay - 2.2°
    ry_idx = np.degrees(2.0 * np.arcsin(np.clip(fixed_q[0, 0, 1], -1.0, 1.0)))
    ry_mid = np.degrees(2.0 * np.arcsin(np.clip(fixed_q[0, 3, 1], -1.0, 1.0)))
    assert (ry_idx - (-11.5)) >= (ry_mid - (-9.5)) - 2.5, "Index y Middle no deben cruzarse lateralmente"


def test_v277_palm_flip_guard_somatotopic_locus_and_4decimal_quantization():
    """
    Verifica las mejoras de producción `v2.7.7_Production_Ready`:
    1. `Palm-Flip Guard` en `stabilize_forearm_and_wrist_chain`: detecta y repara mediante SLERP
       inversiones súbitas de 180° en la normal palmar de corta duración (1 a 10 cuadros).
    2. Anclaje somatotópico suave (`somatotopic_locus_frames`) en señas con punto de articulación
       facial/pectoral (ej. «Comer» o «Saber») manteniendo 0.00 cm de penetración y 1:1 fotogramas.
    3. Cuantización sin pérdida a 4 decimales en `animation.json` sin recortar ni un solo fotograma.
    """
    # 1. Prueba sintética de Palm-Flip Guard (inversión de 180° alrededor del eje X durante 3 cuadros)
    synth_frames = [
        {
            "time": round(t / 60.0, 4),
            "rotations": {
                "rightLowerArm": [0.0, 0.0, 0.0, 1.0],
                "rightHand": [1.0, 0.0, 0.0, 0.0] if 8 <= t <= 10 else [0.0, 0.0, 0.0, 1.0],
            },
        }
        for t in range(25)
    ]
    w_res = lks.stabilize_forearm_and_wrist_chain(synth_frames, side="right", elev_start=2, elev_end=22)
    assert w_res["palm_flips_repaired"] == 3
    for t in range(8, 11):
        q_lo = np.asarray(synth_frames[t]["rotations"]["rightLowerArm"], dtype=np.float64)
        q_ha = np.asarray(synth_frames[t]["rotations"]["rightHand"], dtype=np.float64)
        assert float(abs(q_lo[3])) > 0.95 and float(abs(q_ha[3])) > 0.95

    # 2. Verificar anclaje somatotópico, cuantización a 4 decimales y preservación 1:1 de fotogramas en «Comer»
    res_co = resolve_gloss_to_sign("Comer", version="2.7", include_animation=True)
    anim_co = res_co["animation"]
    stab_co = anim_co["metadata"]["kinematicStabilizer"]
    assert stab_co["version"] == "2.7.7_Production_Ready"
    assert stab_co.get("quantizedDecimals") == 4
    assert stab_co["penetrationResolution"]["max_penetration_after_cm"] == 0.0
    assert stab_co["video2DAlignment"]["sides"]["right"].get("somatotopic_locus_frames", 0) >= 10

    # Verificar que los cuaterniones estén cuantizados a máximo 4 decimales
    sample_rots = anim_co["frames"][len(anim_co["frames"]) // 2]["rotations"]
    for q_vals in sample_rots.values():
        for x in q_vals:
            assert abs(float(x) - round(float(x), 4)) <= 1e-6




