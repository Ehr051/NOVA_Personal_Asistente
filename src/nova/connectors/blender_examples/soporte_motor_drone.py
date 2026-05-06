"""
soporte_motor_drone.py
Drone motor mount arm for 2204/2206 brushless motor.
Carbon fiber arm 120 x 18 x 3 mm, 16x16 motor plate at tip with 4x M2 holes
on a 12mm bolt circle, 2x M3 mounting holes at the root, central oval
lightening cutout.
"""
import bpy, bmesh, math, mathutils

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# ---------- Parameters (mm) ----------
ARM_LEN     = 120.0
ARM_W       = 18.0
ARM_T       = 3.0
PLATE_SIDE  = 16.0
PLATE_T     = 3.0
M2_R        = 1.0
BOLT_CIRCLE = 12.0     # diameter for motor pattern -> 6mm radius
M3_R        = 1.5
ROOT_HOLE_OFFSET_X = 8.0   # from arm root edge (x = -ARM_LEN/2)
ROOT_HOLE_PITCH_Y  = 10.0  # spacing between two M3 holes along Y
SLOT_LEN    = 30.0
SLOT_W      = 8.0

# Place arm centered on origin in X. Tip at +X, root at -X. Z is thickness.
arm_cx = 0.0

# ---------- Helper: cylinder cutter ----------
def make_cylinder(name, radius, depth, location, segments=32):
    mesh = bpy.data.meshes.new(name + "Mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=radius, radius2=radius, depth=depth)
    bm.to_mesh(mesh); bm.free()
    obj.location = location
    return obj

# ---------- Build arm + plate as one bmesh box union ----------
mesh = bpy.data.meshes.new("ArmMesh")
arm = bpy.data.objects.new("DroneArm", mesh)
bpy.context.collection.objects.link(arm)
bm = bmesh.new()

# Arm box
bmesh.ops.create_cube(bm, size=1.0)
for v in bm.verts:
    v.co.x *= ARM_LEN
    v.co.y *= ARM_W
    v.co.z *= ARM_T

# Add plate box (overlapping the tip end)
plate_bm_geom = bmesh.ops.create_cube(bm, size=1.0)
plate_verts = [v for v in plate_bm_geom['verts']]
for v in plate_verts:
    v.co.x = v.co.x * PLATE_SIDE + (ARM_LEN / 2 - PLATE_SIDE / 2 + 1.0)
    v.co.y = v.co.y * PLATE_SIDE
    v.co.z = v.co.z * PLATE_T

bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(mesh); bm.free()

# Apply boolean union via modifier-free workaround: the two boxes overlap,
# we accept the visible union since both share material; for clean topology
# we use boolean modifier with a temp object.

# Build temp plate object for boolean union, then cutters for holes
def add_modifier_bool(target, cutter, op):
    m = target.modifiers.new(type='BOOLEAN', name='bool_' + cutter.name)
    m.object = cutter
    m.operation = op
    m.solver = 'EXACT'

# ---------- Cutters: M2 motor holes (4x on 12mm bolt circle around plate center) ----------
plate_center_x = ARM_LEN / 2 - PLATE_SIDE / 2 + 1.0
plate_center_y = 0.0
plate_center_z = 0.0
cutters = []
for i in range(4):
    a = math.pi / 4 + i * math.pi / 2  # 45,135,225,315 deg
    cx = plate_center_x + (BOLT_CIRCLE / 2) * math.cos(a)
    cy = plate_center_y + (BOLT_CIRCLE / 2) * math.sin(a)
    c = make_cylinder(f"M2_{i}", M2_R, ARM_T * 4, (cx, cy, 0))
    cutters.append(c)

# Center hole on motor plate (motor shaft clearance ~ 6mm dia)
shaft = make_cylinder("ShaftHole", 3.0, ARM_T * 4,
                      (plate_center_x, plate_center_y, 0))
cutters.append(shaft)

# ---------- Cutters: M3 root mount holes ----------
root_x = -ARM_LEN / 2 + ROOT_HOLE_OFFSET_X
for sign in (+1, -1):
    c = make_cylinder(f"M3_{sign}", M3_R, ARM_T * 4,
                      (root_x, sign * ROOT_HOLE_PITCH_Y / 2, 0))
    cutters.append(c)

# ---------- Cutter: oval lightening slot ----------
# Build a rounded rectangle (slot) using bmesh
slot_mesh = bpy.data.meshes.new("SlotMesh")
slot_obj = bpy.data.objects.new("Slot", slot_mesh)
bpy.context.collection.objects.link(slot_obj)
bm = bmesh.new()
SEG = 24
half_len = (SLOT_LEN - SLOT_W) / 2
half_w   = SLOT_W / 2
ring_bot = []
ring_top = []
def slot_outline_z(z):
    pts = []
    # right semicircle
    for i in range(SEG // 2 + 1):
        a = -math.pi / 2 + math.pi * i / (SEG // 2)
        pts.append((half_len + half_w * math.cos(a),
                    half_w * math.sin(a), z))
    # left semicircle
    for i in range(SEG // 2 + 1):
        a = math.pi / 2 + math.pi * i / (SEG // 2)
        pts.append((-half_len + half_w * math.cos(a),
                    half_w * math.sin(a), z))
    return pts
bot = [bm.verts.new(p) for p in slot_outline_z(-ARM_T)]
top = [bm.verts.new(p) for p in slot_outline_z( ARM_T)]
bm.verts.ensure_lookup_table()
N = len(bot)
for i in range(N):
    j = (i + 1) % N
    bm.faces.new((bot[i], bot[j], top[j], top[i]))
bm.faces.new(tuple(reversed(bot)))
bm.faces.new(tuple(top))
bm.normal_update()
bm.to_mesh(slot_mesh); bm.free()
slot_obj.location = (0, 0, 0)
cutters.append(slot_obj)

# ---------- Apply union of plate+arm via boolean (the plate is already a separate
# island in the same mesh, that is fine) and difference for cutters ----------
for c in cutters:
    add_modifier_bool(arm, c, 'DIFFERENCE')

# Apply modifiers (Blender 3.x+ API)
ctx = {"object": arm, "active_object": arm, "selected_objects": [arm]}
for m in list(arm.modifiers):
    try:
        bpy.ops.object.modifier_apply({"object": arm, "active_object": arm}, modifier=m.name)
    except Exception:
        # Fallback for newer API
        with bpy.context.temp_override(object=arm, active_object=arm):
            bpy.ops.object.modifier_apply(modifier=m.name)

# Hide cutters
for c in cutters:
    c.hide_viewport = True
    c.hide_render = True

# ---------- Material: carbon fiber ----------
mat = bpy.data.materials.new("CarbonFiber")
mat.use_nodes = True
nt = mat.node_tree
b = nt.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.04, 0.04, 0.05, 1.0)
b.inputs["Metallic"].default_value = 0.0
b.inputs["Roughness"].default_value = 0.8
# Subtle weave hint via checker texture mixed into base color
tex = nt.nodes.new("ShaderNodeTexChecker")
tex.inputs["Scale"].default_value = 80.0
tex.inputs["Color1"].default_value = (0.03, 0.03, 0.04, 1.0)
tex.inputs["Color2"].default_value = (0.06, 0.06, 0.07, 1.0)
nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
arm.data.materials.append(mat)

# ---------- Camera ----------
cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (80, -130, 90)
cam.rotation_euler = (math.radians(65), 0, math.radians(35))
bpy.context.scene.camera = cam

def add_light(name, kind, energy, loc, size=25):
    ld = bpy.data.lights.new(name, type=kind); ld.energy = energy
    if hasattr(ld, "size"): ld.size = size
    o = bpy.data.objects.new(name, ld); bpy.context.collection.objects.link(o)
    o.location = loc; return o

add_light("Key",  'AREA', 1800, ( 80, -80, 120), 40)
add_light("Fill", 'AREA',  600, (-90, -30,  60), 50)
add_light("Rim",  'AREA', 1100, (  0,  90, 100), 30)

bpy.context.scene.render.engine = 'CYCLES'
