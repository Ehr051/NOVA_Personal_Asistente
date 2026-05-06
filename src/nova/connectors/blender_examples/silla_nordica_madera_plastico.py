import bpy, math

bpy.ops.object.select_all(action='DESELECT')

# ── Materiales ────────────────────────────────────────────────────────────────
def mat_madera():
    m = bpy.data.materials.new("Roble")
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs["Base Color"].default_value = (0.48, 0.28, 0.10, 1.0)
    b.inputs["Roughness"].default_value  = 0.80
    b.inputs["Metallic"].default_value   = 0.0
    return m

def mat_plastico():
    m = bpy.data.materials.new("Plastico_Blanco")
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs["Base Color"].default_value = (0.94, 0.94, 0.93, 1.0)
    b.inputs["Roughness"].default_value  = 0.12
    b.inputs["Metallic"].default_value   = 0.0
    return m

MAD = mat_madera()
PLA = mat_plastico()

def add_obj(name, mat):
    obj = bpy.context.active_object
    obj.name = name
    obj.data.materials.append(mat)
    return obj

# ── Proporciones (metros reales ~1:10) ────────────────────────────────────────
# Silla: 45cm asiento, 85cm total, 42cm ancho, 40cm profundidad
AW  = 0.42   # ancho asiento
AD  = 0.40   # profundidad asiento
AH  = 0.45   # altura del asiento al piso
LEG = 0.43   # largo visible de la pata
LEG_R = 0.022  # radio pata
TRV_R = 0.015  # radio travesano
INC = 0.06   # inclinación lateral patas (outward)

# ── 4 Patas inclinadas hacia afuera ──────────────────────────────────────────
# Ángulo de inclinación: ~5° hacia fuera en X e Y
ang = math.radians(5)
patas = [
    (+AW/2 - 0.02, +AD/2 - 0.02, +ang, +ang, "PataFD"),   # frente-derecha
    (-AW/2 + 0.02, +AD/2 - 0.02, -ang, +ang, "PataFI"),   # frente-izq
    (+AW/2 - 0.02, -AD/2 + 0.02, +ang, -ang, "PataAD"),   # atras-derecha
    (-AW/2 + 0.02, -AD/2 + 0.02, -ang, -ang, "PataAI"),   # atras-izq
]
for (px, py, rx, ry, nombre) in patas:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=12, radius=LEG_R, depth=LEG,
        location=(px, py, AH/2 - 0.01),
        rotation=(rx, ry, 0)
    )
    add_obj(nombre, MAD)

# ── Travesanos horizontales (conectan patas) ──────────────────────────────────
trv_z = AH * 0.35   # altura travesano

# Travesanos laterales (frente-atrás)
for lx, nombre in [(+AW/2 - 0.02, "TrvLadoDer"), (-AW/2 + 0.02, "TrvLadoIzq")]:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=10, radius=TRV_R, depth=AD - 0.06,
        location=(lx, 0, trv_z),
        rotation=(math.pi/2, 0, 0)  # horizontal eje Y
    )
    add_obj(nombre, MAD)

# Travesano frontal y trasero
for ly, nombre in [(+AD/2 - 0.02, "TrvFrente"), (-AD/2 + 0.02, "TrvAtras")]:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=10, radius=TRV_R, depth=AW - 0.06,
        location=(0, ly, trv_z),
        rotation=(0, math.pi/2, 0)  # horizontal eje X
    )
    add_obj(nombre, MAD)

# ── Asiento (plástico blanco, ligeramente redondeado con scale Z) ─────────────
bpy.ops.mesh.primitive_cube_add(
    location=(0, 0.01, AH + 0.02),
    scale=(AW/2, AD/2, 0.025)
)
asiento = add_obj("Asiento", PLA)
# Suavizar bordes con bevel modifier
mod = asiento.modifiers.new("Bevel", "BEVEL")
mod.width = 0.008
mod.segments = 3

# ── Respaldo: dos postes de madera + panel plástico ──────────────────────────
BACK_H = 0.36    # alto del respaldo
BACK_W = AW - 0.06
BACK_Z = AH + BACK_H/2 + 0.03
BACK_TILT = math.radians(12)   # inclinación hacia atrás

# Postes laterales del respaldo
for px, nombre in [(+BACK_W/2, "PosteDer"), (-BACK_W/2, "PosteIzq")]:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=10, radius=LEG_R, depth=BACK_H + 0.05,
        location=(px, -AD/2 + 0.02, BACK_Z),
        rotation=(BACK_TILT, 0, 0)
    )
    add_obj(nombre, MAD)

# Panel del respaldo (plástico, curvado simulado con scale)
bpy.ops.mesh.primitive_cube_add(
    location=(0, -AD/2 + 0.015, BACK_Z),
    scale=(BACK_W/2, 0.012, BACK_H/2)
)
resp = bpy.context.active_object
resp.name = "Respaldo"
resp.rotation_euler.x = BACK_TILT
resp.data.materials.append(PLA)
mod2 = resp.modifiers.new("Bevel", "BEVEL")
mod2.width = 0.006
mod2.segments = 2

bpy.context.view_layer.update()
print("Silla_Nordica OK: madera/plastico, patas inclinadas, travesanos horizontales, respaldo inclinado")
