import bpy

armature = None
for obj in bpy.context.scene.objects:
    if obj.type == 'ARMATURE':
        armature = obj
        break

if armature:
    bone_names = [b.name for b in armature.data.bones]
    print(f"Total bones: {len(bone_names)}")
    print("Primeros 25 huesos:")
    for name in bone_names[:25]:
        print(f"  - {name}")
    # Buscar huesos de brazos/manos
    arm_bones = [b for b in bone_names if any(k in b.lower() for k in ['arm', 'hand', 'thumb', 'index', 'shoulder'])]
    print("Huesos de brazos/manos encontrados:")
    for ab in arm_bones[:25]:
        print(f"  * {ab}")
else:
    print("No se encontró armadura.")
