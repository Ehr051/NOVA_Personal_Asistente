"""
laptop_apertura_animada.py
──────────────────────────
Crea un laptop animado que abre y cierra usando un Empty como pivot de bisagra.

Animación:
  Frame  1 → cerrado (tapa 0°)
  Frame 40 → abierto (tapa 110° hacia atrás)
  Frame 80 → cerrado de nuevo (tapa 0°)

Técnicas:
  - Empty como pivot de rotación en el borde trasero de la base
  - La tapa es hija del Empty, no rota alrededor de su propio centro
  - Keyframes con handles BEZIER para easing suave
  - Materiales Principled BSDF, sin bpy.ops.transform
  - Cámara 3/4 + iluminación tres puntos (Sun + Area fill)
"""

import bpy
import math

# ─── Limpieza de escena ───────────────────────────────────────────────────────

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

for block in list(bpy.data.meshes) + list(bpy.data.lights) + list(bpy.data.cameras):
    try:
        bpy.data.batch_remove(ids=[block])
    except Exception:
        pass


# ─── Helpers de material ──────────────────────────────────────────────────────

def make_material(name, base_color, metallic=0.0, roughness=0.5):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = [n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'][0]
    bsdf.inputs["Base Color"].default_value = (*base_color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def assign_mat(obj, mat):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


# ─── Materiales ───────────────────────────────────────────────────────────────

mat_aluminio   = make_material("Aluminio",   (0.75, 0.75, 0.78), metallic=0.8, roughness=0.25)
mat_teclado    = make_material("TecladoMat", (0.08, 0.08, 0.09), metallic=0.0, roughness=0.85)
mat_pantalla   = make_material("Pantalla",   (0.03, 0.03, 0.04), metallic=0.0, roughness=0.3)

# ─── Dimensiones del laptop (en unidades Blender ≈ metros) ───────────────────
#
#  Base:     largo=2.8   ancho=2.0   alto=0.12
#  Tapa:     largo=2.8   ancho=2.0   alto=0.06  (mismo footprint, más delgada)
#
#  Origen de la escena:
#    Centro de la base en X=0, Y=0, Z=0
#    La base ocupa Z de  0  a  0.12
#    Borde trasero (bisagra) en Y = +1.0  (mitad del ancho)

BASE_L, BASE_W, BASE_H = 2.8, 2.0, 0.12   # largo, ancho, alto base
LID_H   = 0.06
HINGE_Y = BASE_W / 2.0                     # Y del borde trasero
HINGE_Z = BASE_H                           # Z superior de la base


# ─── Base del laptop ──────────────────────────────────────────────────────────

bpy.ops.mesh.primitive_cube_add(location=(0, 0, BASE_H / 2))
base = bpy.context.active_object
base.name = "Laptop_Base"
base.scale = (BASE_L / 2, BASE_W / 2, BASE_H / 2)
bpy.ops.object.transform_apply(scale=True)
assign_mat(base, mat_aluminio)


# ─── Área de teclado (plano ligeramente hundido) ──────────────────────────────
#  Desplazado levemente en Y negativo (parte frontal del laptop)

KEY_L, KEY_W, KEY_H = 2.3, 1.3, 0.01
bpy.ops.mesh.primitive_cube_add(
    location=(0, -0.18, BASE_H + KEY_H / 2)
)
keyboard = bpy.context.active_object
keyboard.name = "Laptop_Keyboard"
keyboard.scale = (KEY_L / 2, KEY_W / 2, KEY_H / 2)
bpy.ops.object.transform_apply(scale=True)
assign_mat(keyboard, mat_teclado)


# ─── Empty pivot de bisagra ───────────────────────────────────────────────────
#  Se coloca exactamente en el borde trasero de la base, a la altura superior.
#  La tapa rotará sobre el eje X del Empty.

bpy.ops.object.empty_add(type='ARROWS', location=(0, HINGE_Y, HINGE_Z))
hinge = bpy.context.active_object
hinge.name = "Laptop_Hinge_Pivot"


# ─── Tapa del laptop ──────────────────────────────────────────────────────────
#  La tapa se crea en el espacio local del Empty.
#  Cuando el Empty rota 0° → tapa plana sobre la base (cerrado).
#  Cuando rota 110° en X positivo → tapa abierta hacia atrás.
#
#  Para que la bisagra sea el borde inferior de la tapa necesitamos que el
#  centro geométrico de la tapa quede desplazado -Y desde el pivot.
#  En espacio local del Empty:
#    La tapa cuelga hacia -Y local (que es hacia el frente del laptop),
#    centrada en Y_local = -(LID_H/2 + ε) para separación mínima, pero
#    en la configuración "cerrada" la tapa descansa sobre la base y se
#    extiende desde el borde trasero hacia el frente.
#
#  Desplazamiento del centro de la tapa desde el pivot:
#    Y_local = -(BASE_W / 2)   → llega justo al borde frontal
#    Z_local = -(LID_H / 2)    → descansa sobre la base cuando cerrado

LID_CENTER_Y_LOCAL = -(BASE_W / 2)
LID_CENTER_Z_LOCAL = -(LID_H / 2)

bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
lid = bpy.context.active_object
lid.name = "Laptop_Lid"
lid.scale = (BASE_L / 2, BASE_W / 2, LID_H / 2)
bpy.ops.object.transform_apply(scale=True)

# Reposicionar en espacio global usando la posición del pivot + offset local
lid.location = (
    0,
    HINGE_Y + LID_CENTER_Y_LOCAL,   # = HINGE_Y - BASE_W/2 = 0  (centro X global)
    HINGE_Z + LID_CENTER_Z_LOCAL,   # = BASE_H - LID_H/2
)
assign_mat(lid, mat_aluminio)

# Pantalla (cara interior de la tapa, plano sobre la tapa)
SCREEN_L, SCREEN_W = 2.4, 1.6
bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
screen = bpy.context.active_object
screen.name = "Laptop_Screen"
screen.scale = (SCREEN_L / 2, SCREEN_W / 2, 0.005)
bpy.ops.object.transform_apply(scale=True)
screen.location = (
    0,
    HINGE_Y + LID_CENTER_Y_LOCAL,
    HINGE_Z + LID_CENTER_Z_LOCAL - LID_H / 2 - 0.006,  # cara inferior de la tapa
)
assign_mat(screen, mat_pantalla)


# ─── Jerarquía: lid y screen como hijos del pivot ────────────────────────────

lid.parent    = hinge
screen.parent = hinge

# Conservar posición global al emparentar
lid.matrix_parent_inverse    = hinge.matrix_world.inverted()
screen.matrix_parent_inverse = hinge.matrix_world.inverted()


# ─── Animación del hinge ──────────────────────────────────────────────────────

scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end   = 80

def set_hinge_rotation(frame, deg_x):
    """Inserta keyframe de rotación en el Empty pivot."""
    scene.frame_set(frame)
    hinge.rotation_euler = (math.radians(deg_x), 0.0, 0.0)
    hinge.keyframe_insert(data_path="rotation_euler", index=0, frame=frame)

set_hinge_rotation(1,  0.0)    # Cerrado
set_hinge_rotation(40, 110.0)  # Abierto 110°
set_hinge_rotation(80, 0.0)    # Cerrado de nuevo

# Aplicar easing BEZIER a todos los keyframes del hinge
if hinge.animation_data and hinge.animation_data.action:
    for fcurve in hinge.animation_data.action.fcurves:
        for kp in fcurve.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.handle_left_type  = 'AUTO_CLAMPED'
            kp.handle_right_type = 'AUTO_CLAMPED'

scene.frame_set(1)


# ─── Cámara ───────────────────────────────────────────────────────────────────

bpy.ops.object.camera_add(location=(4.5, -4.0, 3.5))
cam = bpy.context.active_object
cam.name = "Laptop_Camera"
cam.rotation_euler = (math.radians(58), 0.0, math.radians(48))
scene.camera = cam


# ─── Iluminación tres puntos ──────────────────────────────────────────────────

# Key light — Sun desde arriba-derecha
bpy.ops.object.light_add(type='SUN', location=(5, -3, 8))
sun = bpy.context.active_object
sun.name = "Light_Key_Sun"
sun.rotation_euler = (math.radians(45), 0.0, math.radians(30))
sun.data.energy = 3.0

# Fill light — Area desde la izquierda
bpy.ops.object.light_add(type='AREA', location=(-4, -2, 4))
fill = bpy.context.active_object
fill.name = "Light_Fill_Area"
fill.rotation_euler = (math.radians(60), 0.0, math.radians(-40))
fill.data.energy  = 200.0
fill.data.size    = 3.0

# Rim light — Area desde atrás para separar el laptop del fondo
bpy.ops.object.light_add(type='AREA', location=(0, 5, 5))
rim = bpy.context.active_object
rim.name = "Light_Rim_Area"
rim.rotation_euler = (math.radians(-45), 0.0, 0.0)
rim.data.energy = 120.0
rim.data.size   = 2.0


# ─── Configuración del renderizado ───────────────────────────────────────────

scene.render.engine               = 'CYCLES'
scene.cycles.samples              = 64
scene.render.resolution_x         = 1280
scene.render.resolution_y         = 720
scene.render.film_transparent     = True

bpy.context.view_layer.update()

print("[laptop_apertura_animada] Escena creada. F1=cerrado, F40=abierto(110°), F80=cerrado.")
