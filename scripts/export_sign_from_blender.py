import bpy
import json
import os

# ==============================================================================
# SCRIPT: Exportar Animación Corregida de Blender a JSON para el Avatar LSEC
# Compatible con el esquema canónico HUMAN_BONE_NAMES y Three.js / three-vrm
# ==============================================================================

# RUTA DE SALIDA (donde se guardará el archivo corregido)
OUTPUT_PATH = r"C:\Users\brana\Desktop\TIC Software\lsec_translator_prototype\app\static\assets\clips\LUNES_CORREGIDO.json"
GLOSS_NAME = "LUNES"
FPS = 30.0

# Mapeo de nombres de huesos Blender (VRM addon) -> Nombres estándar VRM Humanoid
BLENDER_TO_HUMANOID = {
    'j_bip_c_hips': 'hips',
    'j_bip_c_spine': 'spine',
    'j_bip_c_chest': 'chest',
    'j_bip_c_upperchest': 'upperChest',
    'j_bip_c_neck': 'neck',
    'j_bip_c_head': 'head',
    'j_bip_l_eye': 'leftEye',
    'j_bip_r_eye': 'rightEye',
    
    # Brazo y mano izquierda
    'j_bip_l_shoulder': 'leftShoulder',
    'j_bip_l_upperarm': 'leftUpperArm',
    'j_bip_l_lowerarm': 'leftLowerArm',
    'j_bip_l_hand': 'leftHand',
    'j_bip_l_thumb1': 'leftThumbMetacarpal',
    'j_bip_l_thumb2': 'leftThumbProximal',
    'j_bip_l_thumb3': 'leftThumbDistal',
    'j_bip_l_index1': 'leftIndexProximal',
    'j_bip_l_index2': 'leftIndexIntermediate',
    'j_bip_l_index3': 'leftIndexDistal',
    'j_bip_l_middle1': 'leftMiddleProximal',
    'j_bip_l_middle2': 'leftMiddleIntermediate',
    'j_bip_l_middle3': 'leftMiddleDistal',
    'j_bip_l_ring1': 'leftRingProximal',
    'j_bip_l_ring2': 'leftRingIntermediate',
    'j_bip_l_ring3': 'leftRingDistal',
    'j_bip_l_little1': 'leftLittleProximal',
    'j_bip_l_little2': 'leftLittleIntermediate',
    'j_bip_l_little3': 'leftLittleDistal',
    
    # Brazo y mano derecha
    'j_bip_r_shoulder': 'rightShoulder',
    'j_bip_r_upperarm': 'rightUpperArm',
    'j_bip_r_lowerarm': 'rightLowerArm',
    'j_bip_r_hand': 'rightHand',
    'j_bip_r_thumb1': 'rightThumbMetacarpal',
    'j_bip_r_thumb2': 'rightThumbProximal',
    'j_bip_r_thumb3': 'rightThumbDistal',
    'j_bip_r_index1': 'rightIndexProximal',
    'j_bip_r_index2': 'rightIndexIntermediate',
    'j_bip_r_index3': 'rightIndexDistal',
    'j_bip_r_middle1': 'rightMiddleProximal',
    'j_bip_r_middle2': 'rightMiddleIntermediate',
    'j_bip_r_middle3': 'rightMiddleDistal',
    'j_bip_r_ring1': 'rightRingProximal',
    'j_bip_r_ring2': 'rightRingIntermediate',
    'j_bip_r_ring3': 'rightRingDistal',
    'j_bip_r_little1': 'rightLittleProximal',
    'j_bip_r_little2': 'rightLittleIntermediate',
    'j_bip_r_little3': 'rightLittleDistal'
}

def export_blender_action_to_json(output_file_path, gloss="LUNES"):
    armature = None
    if bpy.context.active_object and bpy.context.active_object.type == 'ARMATURE':
        armature = bpy.context.active_object
    else:
        for obj in bpy.context.scene.objects:
            if obj.type == 'ARMATURE':
                armature = obj
                break

    if not armature:
        print("❌ Error: No se encontró ningún objeto Armature en la escena.")
        return

    frame_start = int(bpy.context.scene.frame_start)
    frame_end = int(bpy.context.scene.frame_end)
    duration_ms = int(round(((frame_end - frame_start) / FPS) * 1000.0))

    bone_tracks = []
    exported_count = 0

    # Crear diccionario de huesos para acceso rápido
    pose_bones_dict = {pb.name.lower(): pb for pb in armature.pose.bones}

    # Inicializar colectores de datos para cada hueso
    active_bones = []
    for raw_name_lower, std_name in BLENDER_TO_HUMANOID.items():
        if raw_name_lower in pose_bones_dict:
            pb = pose_bones_dict[raw_name_lower]
            active_bones.append((pb, std_name))

    bone_data = {
        std_name: {
            "times": [],
            "rotations": [],
            "first_q": None,
            "has_movement": False
        }
        for _, std_name in active_bones
    }

    # Un solo recorrido por la línea de tiempo (100x más rápido)
    for f in range(frame_start, frame_end + 1):
        bpy.context.scene.frame_set(f)
        t_sec = round((f - frame_start) / FPS, 4)

        for pb, std_name in active_bones:
            if pb.rotation_mode == 'QUATERNION':
                q = pb.rotation_quaternion.normalized()
            else:
                q = pb.rotation_euler.to_quaternion().normalized()

            entry = bone_data[std_name]
            entry["times"].append(t_sec)
            entry["rotations"].extend([round(q.x, 6), round(q.y, 6), round(q.z, 6), round(q.w, 6)])

            if entry["first_q"] is None:
                entry["first_q"] = (q.x, q.y, q.z, q.w)
                if abs(q.w - 1.0) > 0.001 or abs(q.x) > 0.001 or abs(q.y) > 0.001 or abs(q.z) > 0.001:
                    entry["has_movement"] = True
            else:
                fq = entry["first_q"]
                diff = abs(q.x - fq[0]) + abs(q.y - fq[1]) + abs(q.z - fq[2]) + abs(q.w - fq[3])
                if diff > 0.0001:
                    entry["has_movement"] = True

    bone_tracks = []
    exported_count = 0
    for _, std_name in active_bones:
        entry = bone_data[std_name]
        is_essential = std_name in ['spine', 'chest', 'head', 'rightUpperArm', 'rightLowerArm', 'rightHand']
        if entry["has_movement"] or is_essential:
            bone_tracks.append({
                "boneName": std_name,
                "times": entry["times"],
                "rotations": entry["rotations"],
                "interpolation": "SLERP"
            })
            exported_count += 1

    clip_dict = {
        "clipId": f"{gloss}_CORREGIDO_BLENDER",
        "gloss": gloss,
        "version": "4.1.0",
        "durationMs": duration_ms,
        "status": "HUMAN_REVIEWED",
        "validationStatus": "VALIDATED_LSEC",
        "dominantHand": "RIGHT",
        "twoHanded": False,
        "entryPose": "NEUTRAL",
        "exitPose": "NEUTRAL",
        "metadata": {
            "isValidatedLSEC": True,
            "description": f"Seña canónica {gloss} corregida con precisión en Blender.",
            "sourceDocumentation": "Edición manual de postura en Blender 5.2 / VRM",
            "modifiedIn": "Blender 5.2.2 LTS"
        },
        "boneTracks": bone_tracks
    }

    os.makedirs(os.path.dirname(output_file_path), exist_ok=True)

    with open(output_file_path, "w", encoding="utf-8") as f:
        json.dump(clip_dict, f, indent=2)

    print(f"✓ Éxito: Animación exportada correctamente a JSON:")
    print(f"  📁 Archivo: {output_file_path}")
    print(f"  🦴 Huesos exportados: {exported_count}")
    print(f"  ⏱ Duración: {duration_ms} ms ({frame_start} a {frame_end} fotogramas)")
    print(f"👉 Ahora puedes ir a la interfaz web (Studio LSEC o avatarconfig.html) y presionar 'Cargar Seña Corregida'.")

export_blender_action_to_json(OUTPUT_PATH, GLOSS_NAME)
