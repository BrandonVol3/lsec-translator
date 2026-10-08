import bpy
import json
import os

# ==============================================================================
# CARGADOR DIRECTO Y NATIVO DE LA SEÑA 'LUNES' EN BLENDER
# Carga directamente el archivo canónico de la seña LUNES.json del proyecto
# ==============================================================================

JSON_PATH = r"C:\Users\brana\Desktop\TIC Software\lsec_translator_prototype\app\static\assets\clips\LUNES.json"
FPS = 30.0
# Configuración: mantener la cabeza y mirada mirando directamente al frente (interlocutor)
# En LSEC, el señante siempre mantiene contacto visual frontal hacia el usuario.
KEEP_HEAD_FORWARD = True

def load_canonical_lunes():
    if not os.path.exists(JSON_PATH):
        print(f"❌ Error: No se encontró el archivo: {JSON_PATH}")
        return

    # 1. Encontrar la armadura activa
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

    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode='POSE')

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        clip_data = json.load(f)

    gloss = clip_data.get("gloss", "LUNES")
    duration_sec = clip_data.get("durationMs", 4200) / 1000.0

    # 2. Asignar Acción de animación en Blender
    action_name = f"LSEC_{gloss}"
    action = bpy.data.actions.get(action_name)
    if action:
        bpy.data.actions.remove(action)
    action = bpy.data.actions.new(name=action_name)

    if not armature.animation_data:
        armature.animation_data_create()
    armature.animation_data.action = action

    # Configurar línea de tiempo
    bpy.context.scene.render.fps = int(FPS)
    bpy.context.scene.frame_start = 0
    bpy.context.scene.frame_end = int(round(duration_sec * FPS))

    # 3. Mapeo de nombres estándar VRM a los nombres de huesos en Blender
    bone_name_lookup = {}
    for pb in armature.pose.bones:
        bone_name_lookup[pb.name.lower()] = pb

    # Mapa de equivalencias VRM estándar -> Nomenclatura del esqueleto
    vrm_aliases = {
        'spine': ['j_bip_c_spine', 'spine'],
        'chest': ['j_bip_c_chest', 'chest'],
        'upperchest': ['j_bip_c_upperchest', 'upperchest'],
        'neck': ['j_bip_c_neck', 'neck'],
        'head': ['j_bip_c_head', 'head'],
        'leftupperarm': ['j_bip_l_upperarm', 'leftupperarm'],
        'leftlowerarm': ['j_bip_l_lowerarm', 'leftlowerarm'],
        'lefthand': ['j_bip_l_hand', 'lefthand'],
        'rightupperarm': ['j_bip_r_upperarm', 'rightupperarm'],
        'rightlowerarm': ['j_bip_r_lowerarm', 'rightlowerarm'],
        'righthand': ['j_bip_r_hand', 'righthand'],
        'rightthumbmetacarpal': ['j_bip_r_thumb1', 'rightthumbmetacarpal'],
        'rightthumbproximal': ['j_bip_r_thumb2', 'rightthumbproximal'],
        'rightthumbdistal': ['j_bip_r_thumb3', 'rightthumbdistal'],
        'rightindexproximal': ['j_bip_r_index1', 'rightindexproximal'],
        'rightindexintermediate': ['j_bip_r_index2', 'rightindexintermediate'],
        'rightindexdistal': ['j_bip_r_index3', 'rightindexdistal'],
        'rightmiddleproximal': ['j_bip_r_middle1', 'rightmiddleproximal'],
        'rightmiddleintermediate': ['j_bip_r_middle2', 'rightmiddleintermediate'],
        'rightmiddledistal': ['j_bip_r_middle3', 'rightmiddledistal'],
        'rightringproximal': ['j_bip_r_ring1', 'rightringproximal'],
        'rightringintermediate': ['j_bip_r_ring2', 'rightringintermediate'],
        'rightringdistal': ['j_bip_r_ring3', 'rightringdistal'],
        'rightlittleproximal': ['j_bip_r_little1', 'rightlittleproximal'],
        'rightlittleintermediate': ['j_bip_r_little2', 'rightlittleintermediate'],
        'rightlittledistal': ['j_bip_r_little3', 'rightlittledistal']
    }

    applied_count = 0

    for track in clip_data.get("boneTracks", []):
        std_name = track.get("boneName", "")
        times = track.get("times", [])
        rotations = track.get("rotations", [])

        # Buscar hueso en la armadura
        target_bone = None
        aliases = vrm_aliases.get(std_name.lower(), [std_name.lower()])
        for alias in aliases:
            if alias in bone_name_lookup:
                target_bone = bone_name_lookup[alias]
                break

        if not target_bone:
            # Búsqueda difusa
            for name_low, pb in bone_name_lookup.items():
                if std_name.lower() in name_low:
                    target_bone = pb
                    break

        if not target_bone:
            continue

        target_bone.rotation_mode = 'QUATERNION'

        for i, t in enumerate(times):
            frame = int(round(t * FPS))
            k4 = i * 4
            # JSON contiene [x, y, z, w]. Blender Quaternion usa (w, x, y, z)
            qx = rotations[k4]
            qy = rotations[k4 + 1]
            qz = rotations[k4 + 2]
            qw = rotations[k4 + 3]

            # Corregir la cabeza: en LSEC el señante mira de frente al interlocutor (cámara)
            # Evita que la cabeza gire lateralmente o mire hacia otro lado.
            if std_name.lower() == 'head' and KEEP_HEAD_FORWARD:
                qy = 0.0  # Sin giro lateral (yaw)
                qz = 0.0  # Sin inclinación no deseada (roll)
                norm = (qx * qx + qw * qw) ** 0.5
                if norm > 1e-6:
                    qx /= norm
                    qw /= norm
                else:
                    qx, qw = 0.0, 1.0

            target_bone.rotation_quaternion = (qw, qx, qy, qz)
            target_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame)

        applied_count += 1

    # Asegurar que el cuello y ojos también queden centrados al frente
    for neutral_bone_name in ['j_bip_c_neck', 'j_bip_l_eye', 'j_bip_r_eye']:
        if neutral_bone_name in bone_name_lookup:
            nb = bone_name_lookup[neutral_bone_name]
            nb.rotation_mode = 'QUATERNION'
            nb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)

    print(f"✓ Éxito: Animación oficial '{gloss}' ({clip_data.get('durationMs')}ms) cargada correctamente.")
    print(f"✓ {applied_count} pistas de huesos aplicadas. Mirada frontal asegurada.")
    print(f"✓ Fotogramas: 0 a {bpy.context.scene.frame_end}.")
    print("👉 Puedes presionar Barra Espaciadora para reproducir.")
    print("👉 Para ajustar cualquier hueso (ej. J_Bip_C_Head o dedos), selecciónalo en Pose Mode, pulsa 'R' y presiona 'I' para insertar fotograma.")
    bpy.context.scene.frame_set(0)

load_canonical_lunes()
