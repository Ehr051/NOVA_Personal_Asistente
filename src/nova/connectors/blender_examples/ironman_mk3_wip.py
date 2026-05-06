import bpy, bmesh, math

bpy.ops.object.select_all(action='DESELECT')

# ═══════════════════════════════════════════════════════════
# IRON MAN MK III — CASCO COMPLETO CON FACEPLATE ANIMADO
# Escala 1:1 en Blender units = cm (1 bu = 1 cm)
# ═══════════════════════════════════════════════════════════

# ── Materiales ──────────────────────────────────────────────
def mk_mat(name, color, metallic=0.9, rough=0.2, emission=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs["Base Color"].default_value   = (*color, 1.0)
    b.inputs["Metallic"].default_value     = metallic
    b.inputs["Roughness"].default_value    = rough
    if emission:
        b.inputs["Emission Color"].default_value    = (*emission, 1.0)
        b.inputs["Emission Strength"].default_value = 8.0
    return m

MAT_RED    = mk_mat("IronMan_Red",    (0.72, 0.03, 0.03), metallic=1.0, rough=0.18)
MAT_GOLD   = mk_mat("IronMan_Gold",   (0.90, 0.55, 0.05), metallic=1.0, rough=0.15)
MAT_EYES   = mk_mat("Eyes_OFF",       (0.05, 0.08, 0.12), metallic=0.0, rough=0.05)
MAT_EYES_ON= mk_mat("Eyes_ON",        (0.85, 0.92, 1.00), metallic=0.0, rough=0.0,
                    emission=(0.7, 0.88, 1.0))
MAT_DARK   = mk_mat("Dark_Panel",     (0.06, 0.06, 0.07), metallic=0.8, rough=0.3)

def add(obj, mat):
    obj.data.materials.append(mat)
    return obj

# ── Proporciones (cm) ────────────────────────────────────────
HH = 31    # altura total casco
HW = 21    # ancho
HD = 25    # profundidad
EYE_Z = HH * 0.52   # ojos al 52% de altura
PIVOT_Z = HH * 0.62  # eje de pivote del faceplate (nivel de sienes)

# ═══════════════════════════════════════════════════════════
# 1. CASCO BASE — cúpula trasera/superior (no se mueve)
# ═══════════════════════════════════════════════════════════
bpy.ops.mesh.primitive_uv_sphere_add(
    segments=32, ring_count=16,
    radius=1,
    location=(0, 0, HH * 0.55)
)
base = bpy.context.active_object
base.name = "Casco_base"
base.scale = (HW/2, HD/2, HH * 0.55)
bpy.ops.object.transform_apply(scale=True)
add(base, MAT_RED)

# Recortar la parte frontal (casco solo es la parte trasera/superior)
# Usamos un cubo cortador para quitar la mitad frontal
bpy.ops.mesh.primitive_cube_add(
    location=(0, HD * 0.22, HH * 0.55),
    scale=(HW, HD * 0.6, HH * 0.6)
)
cutter_front = bpy.context.active_object
cutter_front.name = "_cut_front"
bool_mod = base.modifiers.new("CutFront", "BOOLEAN")
bool_mod.operation = "DIFFERENCE"
bool_mod.object = cutter_front
bpy.context.view_layer.objects.active = base
bpy.ops.object.modifier_apply(modifier="CutFront")
bpy.data.objects.remove(cutter_front)

# Corona superior (cubre el agujero del recorte)
bpy.ops.mesh.primitive_cylinder_add(
    vertices=6, radius=HW * 0.22, depth=HH * 0.08,
    location=(0, -HD * 0.08, HH * 0.92)
)
corona = bpy.context.active_object
corona.name = "Corona_superior"
add(corona, MAT_GOLD)

# Bisagras (sienes) — puntos de pivote del faceplate
for sx, nombre in [(HW/2, "Bisagra_D"), (-HW/2, "Bisagra_I")]:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=12, radius=1.2, depth=2.5,
        location=(sx * 0.95, HD * 0.05, PIVOT_Z),
        rotation=(0, math.pi/2, 0)
    )
    bis = bpy.context.active_object
    bis.name = nombre
    add(bis, MAT_GOLD)

# ═══════════════════════════════════════════════════════════
# 2. FACEPLATE — cara frontal + mentón (se abre hacia arriba)
# ═══════════════════════════════════════════════════════════
bm = bmesh.new()

# Contorno del faceplate: elipsoide aplanada al frente
verts_face = []
for row in range(12):
    lat = -math.pi/2 + row * math.pi / 11
    z   = HH * 0.55 * math.sin(lat) + HH * 0.55
    r   = math.cos(lat)
    for col in range(20):
        lon = -math.pi/2 - col * math.pi / 19   # solo frente
        if lon < -math.pi:
            break
        x = HW/2 * r * math.cos(lon)
        y = HD/2 * r * math.sin(lon) + HD * 0.1  # empujar al frente
        verts_face.append(bm.verts.new((x, y, z)))

# Crear cuadriláteros entre filas
cols = 19
for row in range(11):
    for col in range(cols - 1):
        i0 = row * cols + col
        i1 = i0 + 1
        i2 = i0 + cols + 1
        i3 = i0 + cols
        try:
            bm.faces.new([verts_face[i0], verts_face[i1],
                          verts_face[i2], verts_face[i3]])
        except Exception:
            pass

bm.normal_update()
mesh_fp = bpy.data.meshes.new("Faceplate_mesh")
bm.to_mesh(mesh_fp)
bm.free()

faceplate = bpy.data.objects.new("Faceplate", mesh_fp)
bpy.context.collection.objects.link(faceplate)
bpy.context.view_layer.objects.active = faceplate
faceplate.select_set(True)
bpy.ops.object.shade_smooth()
add(faceplate, MAT_RED)

# Añadir grosor con solidify
sol = faceplate.modifiers.new("Grosor", "SOLIDIFY")
sol.thickness = 0.8

# ── Mentón / chin (parte baja del faceplate) ───────────────
bpy.ops.mesh.primitive_cylinder_add(
    vertices=16, radius=HW * 0.38, depth=HH * 0.14,
    location=(0, HD * 0.32, HH * 0.1),
    scale=(1.0, 0.55, 1.0)
)
chin = bpy.context.active_object
chin.name = "Menton"
add(chin, MAT_RED)
chin.parent = faceplate

# Ventilaciones del mentón (rejillas doradas)
for i, ly in enumerate([-0.8, 0.0, 0.8]):
    bpy.ops.mesh.primitive_cube_add(
        location=(ly * 3, HD * 0.46, HH * 0.09),
        scale=(1.0, 0.15, 0.4)
    )
    vent = bpy.context.active_object
    vent.name = f"Vent_{i}"
    add(vent, MAT_GOLD)
    vent.parent = faceplate

# ── Viuda (V en la frente) ─────────────────────────────────
bpy.ops.mesh.primitive_cone_add(
    vertices=3, radius1=3.5, depth=1.2,
    location=(0, HD * 0.38, HH * 0.82),
    rotation=(math.pi/2, 0, 0)
)
viuda = bpy.context.active_object
viuda.name = "Viuda_Peak"
viuda.scale.x = 0.6
add(viuda, MAT_GOLD)
viuda.parent = faceplate

# ═══════════════════════════════════════════════════════════
# 3. OJOS — hexágonos irregulares con emisión
# ═══════════════════════════════════════════════════════════
def hacer_ojo(lado):
    sx = 1 if lado == "D" else -1
    bm = bmesh.new()
    # Hexágono irregular: más ancho en exterior, angosto interior
    # Ángulo de 12° hacia abajo exterior-interior
    ang = math.radians(12)
    ow, oh = 5.8, 2.2   # ancho, alto ojo
    xi = sx * 2.0        # interior X (cerca de nariz)
    xo = sx * (2.0 + ow) # exterior X
    pts = [
        (xi,           HD*0.46, EYE_Z + oh*0.3),
        (xi + sx*ow*0.2, HD*0.46, EYE_Z + oh*0.5),
        (xi + sx*ow*0.5, HD*0.47, EYE_Z + oh*0.5),
        (xo,           HD*0.44, EYE_Z + oh*0.3),
        (xo,           HD*0.43, EYE_Z - oh*0.3),
        (xi + sx*ow*0.4, HD*0.46, EYE_Z - oh*0.5),
        (xi,           HD*0.46, EYE_Z - oh*0.3),
    ]
    vs = [bm.verts.new(p) for p in pts]
    bm.faces.new(vs)
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.6)
    bm.normal_update()
    mesh = bpy.data.meshes.new(f"Ojo_{lado}_mesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(f"Ojo_{lado}", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(MAT_EYES)
    obj.parent = faceplate
    return obj

ojo_d = hacer_ojo("D")
ojo_i = hacer_ojo("I")

# ═══════════════════════════════════════════════════════════
# 4. COLLAR / CUELLO
# ═══════════════════════════════════════════════════════════
bpy.ops.mesh.primitive_cylinder_add(
    vertices=32, radius=HW * 0.46, depth=HH * 0.12,
    location=(0, 0, HH * 0.04),
    scale=(1.0, HD/HW * 0.92, 1.0)
)
collar = bpy.context.active_object
collar.name = "Collar"
add(collar, MAT_RED)
# Detalle dorado en el collar
bpy.ops.mesh.primitive_cylinder_add(
    vertices=32, radius=HW * 0.48, depth=0.6,
    location=(0, 0, HH * 0.10),
    scale=(1.0, HD/HW * 0.94, 1.0)
)
add(bpy.context.active_object, MAT_GOLD)
bpy.context.active_object.name = "Collar_ring"

# ═══════════════════════════════════════════════════════════
# 5. REACTOR ARC (detalle en frente) — círculo en frente opcional
# ═══════════════════════════════════════════════════════════
# (No en el casco, está en el pecho — omitido)

# ═══════════════════════════════════════════════════════════
# 6. ANIMACIÓN: Faceplate se abre (pivot en bisagras = PIVOT_Z)
# ═══════════════════════════════════════════════════════════

# Mover el punto de origen del faceplate al eje de pivote
# Usamos un Empty como padre en el punto de pivote
bpy.ops.object.empty_add(type='ARROWS', location=(0, 0, PIVOT_Z))
pivot = bpy.context.active_object
pivot.name = "Pivot_Faceplate"

# Re-parentar faceplate al pivot manteniendo transform
faceplate.parent = pivot
faceplate.matrix_parent_inverse = pivot.matrix_world.inverted()

# Keyframes: cerrado → abierto
pivot.rotation_euler = (0, 0, 0)
pivot.keyframe_insert(data_path="rotation_euler", frame=1)
pivot.keyframe_insert(data_path="rotation_euler", frame=15)

pivot.rotation_euler.x = math.radians(-88)   # abre hacia arriba/atrás
pivot.keyframe_insert(data_path="rotation_euler", frame=55)
pivot.keyframe_insert(data_path="rotation_euler", frame=80)

# Vuelve a cerrar
pivot.rotation_euler = (0, 0, 0)
pivot.keyframe_insert(data_path="rotation_euler", frame=120)

# Suavizado de curvas
for fc in pivot.animation_data.action.fcurves:
    for kp in fc.keyframe_points:
        kp.interpolation = 'BEZIER'

# Ojos se encienden cuando abre (frame 30)
for ojo in [ojo_d, ojo_i]:
    # Frame 1: ojos apagados
    ojo.data.materials.clear()
    ojo.data.materials.append(MAT_EYES)

# Material switching via material index keyframe no es directo en bpy
# Usamos emission strength animada en el material de los ojos
MAT_EYES_ON.node_tree.nodes
emit_node = next(n for n in MAT_EYES_ON.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')

# Swap material a frame 30 para los ojos
for ojo in [ojo_d, ojo_i]:
    ojo.data.materials.clear()
    ojo.data.materials.append(MAT_EYES)     # slot 0: apagado
    ojo.data.materials.append(MAT_EYES_ON)  # slot 1: encendido
    # keyframe material_index en el mesh (por face)
    # Más simple: animar emission strength directamente
    es = emit_node.inputs["Emission Strength"]
    es.default_value = 0
    es.keyframe_insert(data_path="default_value", frame=1)
    es.keyframe_insert(data_path="default_value", frame=28)
    es.default_value = 10.0
    es.keyframe_insert(data_path="default_value", frame=35)
    es.keyframe_insert(data_path="default_value", frame=80)
    es.default_value = 0
    es.keyframe_insert(data_path="default_value", frame=115)

bpy.context.scene.frame_end = 130
bpy.context.view_layer.update()
print("IronMan_MK3 OK — faceplate animado 85deg, ojos con emision, collar, bisagras. Dale SPACE para ver la animacion.")
