import bpy, bmesh, math

bpy.ops.object.select_all(action='DESELECT')

DIENTES  = 16
MOD      = 1.0
ANCHO    = 1.2
HELIX    = math.radians(20)
RP       = MOD * DIENTES / 2   # 8.0
RC       = RP + MOD            # 9.0
RF       = RP - 1.25 * MOD    # 6.75
RI       = 1.8
PASO     = 2 * math.pi / DIENTES

def perfil(z):
    """Perfil exterior del engranaje con dientes helicoidales."""
    off = z * math.tan(HELIX) / RP
    pts = []
    for i in range(DIENTES):
        a0 = i * PASO + off
        # Pie (4 puntos en RF)
        for k in range(4):
            a = a0 - PASO * 0.5 + (k + 0.5) * PASO * 0.5 / 4
            pts.append((math.cos(a) * RF, math.sin(a) * RF, z))
        # Flanco entrada (RF → RC, 3 intermedios)
        for k in range(1, 4):
            t = k / 3.0
            r = RF + (RC - RF) * t
            a = a0 - PASO * 0.14 + PASO * 0.07 * t
            pts.append((math.cos(a) * r, math.sin(a) * r, z))
        # Cresta (3 puntos en RC)
        for k in range(3):
            a = a0 - PASO * 0.07 + k * PASO * 0.07
            pts.append((math.cos(a) * RC, math.sin(a) * RC, z))
        # Flanco salida (RC → RF, 3 intermedios)
        for k in range(1, 4):
            t = k / 3.0
            r = RC - (RC - RF) * t
            a = a0 + PASO * 0.07 + PASO * 0.07 * t
            pts.append((math.cos(a) * r, math.sin(a) * r, z))
    return pts

def ring(z, radius, n):
    """Anillo simple de n puntos a radio dado."""
    off = z * math.tan(HELIX) / RP
    return [(math.cos(i * 2*math.pi/n + off) * radius,
             math.sin(i * 2*math.pi/n + off) * radius, z) for i in range(n)]

bm = bmesh.new()

# ── Anillos de vértices ──────────────────────────────────────────────────────
N_CAP = DIENTES * 4   # anillo intermedio para caps

bot_ext = [bm.verts.new(p) for p in perfil(0)]
top_ext = [bm.verts.new(p) for p in perfil(ANCHO)]
bot_mid = [bm.verts.new(p) for p in ring(0,     RF * 0.97, N_CAP)]
top_mid = [bm.verts.new(p) for p in ring(ANCHO, RF * 0.97, N_CAP)]
bot_inn = [bm.verts.new(p) for p in ring(0,     RI,        N_CAP)]
top_inn = [bm.verts.new(p) for p in ring(ANCHO, RI,        N_CAP)]

N_EXT = len(bot_ext)  # = 16 * 13 = 208

# ── Paredes exteriores (dientes) ─────────────────────────────────────────────
for i in range(N_EXT):
    j = (i + 1) % N_EXT
    bm.faces.new([bot_ext[i], bot_ext[j], top_ext[j], top_ext[i]])

# ── Caps: anillo ext → mid → inn ─────────────────────────────────────────────
# Cada N_EXT / N_CAP = 208/64 ≈ 3.25 — usamos skip para emparejar
# Conectamos solo bot_mid ↔ bot_inn y top_mid ↔ top_inn (anillos regulares)

# Face anular mid ↔ inner (quads)
for i in range(N_CAP):
    j = (i + 1) % N_CAP
    # Bottom (winding hacia adentro = normal apuntando -Z)
    bm.faces.new([bot_inn[i], bot_inn[j], bot_mid[j], bot_mid[i]])
    # Top (normal apuntando +Z)
    bm.faces.new([top_mid[i], top_mid[j], top_inn[j], top_inn[i]])

# Face anular mid ↔ ext: emparejamos por índice proporcional
for i in range(N_CAP):
    j = (i + 1) % N_CAP
    # índices en ext_ring proporcionales
    ie0 = int(i       * N_EXT / N_CAP) % N_EXT
    ie1 = int((i + 1) * N_EXT / N_CAP) % N_EXT
    if ie0 == ie1:
        # 1 ext vertex: tri
        bm.faces.new([bot_mid[i], bot_ext[ie0], bot_mid[j]])
        bm.faces.new([top_mid[j], top_ext[ie0], top_mid[i]])
    else:
        # múltiples ext verts: fan desde mid[i] a los ext intermedios
        ext_seg = []
        k = ie0
        while True:
            ext_seg.append(k)
            if k == ie1:
                break
            k = (k + 1) % N_EXT
        for s in range(len(ext_seg) - 1):
            bm.faces.new([bot_mid[i], bot_ext[ext_seg[s]], bot_ext[ext_seg[s+1]]])
            bm.faces.new([top_mid[i], top_ext[ext_seg[s+1]], top_ext[ext_seg[s]]])
        # quad cierre mid[i]-mid[j]-ext[ie1]
        if len(ext_seg) > 1:
            bm.faces.new([bot_mid[i], bot_ext[ie1], bot_mid[j]])
            bm.faces.new([top_mid[j], top_ext[ie1], top_mid[i]])

# Pared interior del agujero
for i in range(N_CAP):
    j = (i + 1) % N_CAP
    bm.faces.new([bot_inn[i], top_inn[i], top_inn[j], bot_inn[j]])

bm.normal_update()
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)

mesh = bpy.data.meshes.new("Gear_mesh")
bm.to_mesh(mesh)
bm.free()

gear = bpy.data.objects.new("Engranaje_16T", mesh)
bpy.context.collection.objects.link(gear)
bpy.context.view_layer.objects.active = gear
gear.select_set(True)
bpy.ops.object.shade_smooth()

# ── Material acero ───────────────────────────────────────────────────────────
mat = bpy.data.materials.new("Acero")
mat.use_nodes = True
bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
bsdf.inputs["Base Color"].default_value = (0.52, 0.53, 0.56, 1.0)
bsdf.inputs["Metallic"].default_value   = 1.0
bsdf.inputs["Roughness"].default_value  = 0.20
gear.data.materials.append(mat)

# ── Rodamiento ────────────────────────────────────────────────────────────────
bpy.ops.mesh.primitive_torus_add(
    location=(0, 0, ANCHO/2), major_radius=RI+0.55, minor_radius=0.28)
rod = bpy.context.active_object
rod.name = "Rodamiento"
mat2 = bpy.data.materials.new("Acero_oscuro")
mat2.use_nodes = True
b2 = next(n for n in mat2.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
b2.inputs["Base Color"].default_value = (0.12, 0.12, 0.14, 1.0)
b2.inputs["Metallic"].default_value   = 1.0
b2.inputs["Roughness"].default_value  = 0.10
rod.data.materials.append(mat2)
rod.parent = gear

# ── Perno + tuerca ─────────────────────────────────────────────────────────────
bpy.ops.mesh.primitive_cylinder_add(
    vertices=16, radius=RI*0.82, depth=ANCHO*2.8, location=(0,0,ANCHO/2))
bpy.context.active_object.name = "Perno"
bpy.context.active_object.data.materials.append(mat)
bpy.context.active_object.parent = gear

bpy.ops.mesh.primitive_cylinder_add(
    vertices=6, radius=RI*1.6, depth=0.45, location=(0,0,ANCHO*1.4+0.22))
bpy.context.active_object.name = "Cabeza_perno"
bpy.context.active_object.data.materials.append(mat)
bpy.context.active_object.parent = gear

bpy.ops.mesh.primitive_cylinder_add(
    vertices=6, radius=RI*1.6, depth=0.45, location=(0,0,-ANCHO*0.4-0.22))
bpy.context.active_object.name = "Tuerca"
bpy.context.active_object.data.materials.append(mat)
bpy.context.active_object.parent = gear

# ── Tornillo lateral ──────────────────────────────────────────────────────────
bpy.ops.mesh.primitive_cylinder_add(
    vertices=16, radius=0.3, depth=2.2,
    location=(RP*0.52, 0, ANCHO/2), rotation=(0, math.pi/2, 0))
bpy.context.active_object.name = "Tornillo_fijacion"
bpy.context.active_object.data.materials.append(mat)
bpy.context.active_object.parent = gear

bpy.ops.mesh.primitive_cylinder_add(
    vertices=6, radius=0.52, depth=0.38,
    location=(RP*0.52+1.15, 0, ANCHO/2), rotation=(0, math.pi/2, 0))
bpy.context.active_object.name = "Cabeza_tornillo"
bpy.context.active_object.data.materials.append(mat)
bpy.context.active_object.parent = gear

# ── Animación ─────────────────────────────────────────────────────────────────
gear.rotation_euler = (0, 0, 0)
gear.keyframe_insert(data_path="rotation_euler", frame=1)
gear.rotation_euler = (0, 0, math.radians(360))
gear.keyframe_insert(data_path="rotation_euler", frame=121)
for fc in gear.animation_data.action.fcurves:
    for kp in fc.keyframe_points:
        kp.interpolation = 'LINEAR'
    fc.modifiers.new('CYCLES')

bpy.context.view_layer.update()
print("Engranaje_16T OK: dientes suaves, caps limpias, acero, animacion rotacion lista")
