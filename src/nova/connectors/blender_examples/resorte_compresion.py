"""
resorte_compresion.py
Compression spring. Wire 1.5mm, coil 20mm, 8 active coils, free length 40mm,
plus 1 dead coil top + 1 dead coil bottom (ground ends).
"""
import bpy, bmesh, math, mathutils

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

WIRE_R       = 0.75
COIL_R       = 10.0          # coil radius (20mm dia)
ACTIVE_COILS = 8
DEAD_TOP     = 1
DEAD_BOT     = 1
TOTAL_COILS  = ACTIVE_COILS + DEAD_TOP + DEAD_BOT
FREE_LENGTH  = 40.0
PITCH_ACTIVE = (FREE_LENGTH - 2*WIRE_R*2) / ACTIVE_COILS
PATH_PER_TURN = 64
PROFILE_SEG   = 12

mesh = bpy.data.meshes.new("SpringMesh")
spring = bpy.data.objects.new("CompressionSpring", mesh)
bpy.context.collection.objects.link(spring)
bm = bmesh.new()

# Build helix path with variable pitch:
# dead bottom: pitch = wire diameter (closed/ground)
# active: PITCH_ACTIVE
# dead top: pitch = wire diameter
def pitch_for_turn(turn_idx):
    if turn_idx < DEAD_BOT:
        return 2 * WIRE_R
    if turn_idx >= DEAD_BOT + ACTIVE_COILS:
        return 2 * WIRE_R
    return PITCH_ACTIVE

# Pre-compute z for each path step
path_points = []
z = WIRE_R
for turn in range(TOTAL_COILS):
    p = pitch_for_turn(turn)
    for s in range(PATH_PER_TURN):
        frac = s / PATH_PER_TURN
        ang = 2 * math.pi * (turn + frac)
        zz = z + p * frac
        path_points.append((ang, zz))
    z += p
# Closing point
path_points.append((2 * math.pi * TOTAL_COILS, z))

# Build tube around path
prev_ring = None
for idx, (ang, zz) in enumerate(path_points):
    cx = COIL_R * math.cos(ang)
    cy = COIL_R * math.sin(ang)
    # Frenet-ish frame: tangent ~ d/dang (-sin, cos, dz/dang)
    # use radial out + global Z to build profile plane
    rx, ry = math.cos(ang), math.sin(ang)
    ring = []
    for j in range(PROFILE_SEG):
        a = 2 * math.pi * j / PROFILE_SEG
        ox = WIRE_R * math.cos(a) * rx
        oy = WIRE_R * math.cos(a) * ry
        oz = WIRE_R * math.sin(a)
        v = bm.verts.new((cx + ox, cy + oy, zz + oz))
        ring.append(v)
    bm.verts.ensure_lookup_table()
    if prev_ring is not None:
        for k in range(PROFILE_SEG):
            k2 = (k + 1) % PROFILE_SEG
            bm.faces.new((prev_ring[k], prev_ring[k2], ring[k2], ring[k]))
    prev_ring = ring

# Cap both ends
first_ring = []
# rebuild references is unsafe; instead cap by creating polygons from the first/last PROFILE_SEG verts
all_verts = list(bm.verts)
first = all_verts[:PROFILE_SEG]
last  = all_verts[-PROFILE_SEG:]
bm.faces.new(tuple(reversed(first)))
bm.faces.new(tuple(last))

bm.normal_update()
bm.to_mesh(mesh)
bm.free()

for p in mesh.polygons:
    p.use_smooth = True

# Material: spring steel
mat = bpy.data.materials.new("SpringSteel")
mat.use_nodes = True
b = mat.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.82, 0.83, 0.85, 1.0)
b.inputs["Metallic"].default_value = 1.0
b.inputs["Roughness"].default_value = 0.2
spring.data.materials.append(mat)

# Camera
cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (60, -70, 35)
cam.rotation_euler = (math.radians(72), 0, math.radians(40))
bpy.context.scene.camera = cam

def add_light(name, kind, energy, loc, size=15):
    ld = bpy.data.lights.new(name, type=kind); ld.energy = energy
    if hasattr(ld, "size"): ld.size = size
    o = bpy.data.objects.new(name, ld); bpy.context.collection.objects.link(o)
    o.location = loc; return o

add_light("Key",  'AREA', 1000, ( 40, -40, 60), 25)
add_light("Fill", 'AREA',  400, (-50, -20, 35), 35)
add_light("Rim",  'AREA',  600, (  0,  40, 50), 20)

bpy.context.scene.render.engine = 'CYCLES'
