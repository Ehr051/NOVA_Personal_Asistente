"""
tornillo_hexagonal_m6.py
M6 x 25mm hex head bolt. Standalone Blender script.
Units in millimeters (Blender units).
"""
import bpy, bmesh, math, mathutils

# ---------- Clear scene ----------
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# ---------- Parameters (mm) ----------
HEAD_FLATS    = 10.0          # flat-to-flat
HEAD_HEIGHT   = 4.0
SHANK_DIA     = 6.0
SHANK_LEN     = 16.0
THREAD_LEN    = 14.0
THREAD_PITCH  = 1.0           # M6 standard pitch
THREAD_TURNS  = int(THREAD_LEN / THREAD_PITCH)

head_radius = HEAD_FLATS / math.cos(math.radians(30)) / 2.0  # circumscribed

# ---------- Hex head ----------
mesh = bpy.data.meshes.new("HeadMesh")
head = bpy.data.objects.new("BoltHead", mesh)
bpy.context.collection.objects.link(head)
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=6,
                      radius1=head_radius, radius2=head_radius,
                      depth=HEAD_HEIGHT)
# Slight chamfer on top edges
top_edges = [e for e in bm.edges if all(v.co.z > HEAD_HEIGHT/2 - 0.01 for v in e.verts)]
bmesh.ops.bevel(bm, geom=top_edges, offset=0.4, segments=2, affect='EDGES')
bm.to_mesh(mesh)
bm.free()
head.location = (0, 0, HEAD_HEIGHT / 2.0)

# ---------- Shank ----------
mesh_s = bpy.data.meshes.new("ShankMesh")
shank = bpy.data.objects.new("BoltShank", mesh_s)
bpy.context.collection.objects.link(shank)
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=32,
                      radius1=SHANK_DIA/2, radius2=SHANK_DIA/2,
                      depth=SHANK_LEN)
bm.to_mesh(mesh_s)
bm.free()
shank.location = (0, 0, -SHANK_LEN / 2.0)

# ---------- Thread (helical torus stack approximation) ----------
mesh_t = bpy.data.meshes.new("ThreadMesh")
thread = bpy.data.objects.new("BoltThread", mesh_t)
bpy.context.collection.objects.link(thread)
bm = bmesh.new()

# Build a helix of small profile rings to approximate a thread
PROFILE_SEG = 6   # segments around wire
PATH_SEG    = 64  # segments per turn
WIRE_R      = 0.35
HELIX_R     = SHANK_DIA / 2 - 0.1
total_steps = THREAD_TURNS * PATH_SEG
prev_ring = None
for i in range(total_steps + 1):
    t = i / PATH_SEG  # in turns
    ang = t * 2 * math.pi
    z = -SHANK_LEN + 1.0 + t * THREAD_PITCH
    if z > -1.0:
        break
    cx = HELIX_R * math.cos(ang)
    cy = HELIX_R * math.sin(ang)
    # tangent direction
    tx = -math.sin(ang)
    ty =  math.cos(ang)
    # radial out
    rx =  math.cos(ang)
    ry =  math.sin(ang)
    ring = []
    for j in range(PROFILE_SEG):
        a = 2 * math.pi * j / PROFILE_SEG
        # offset in (radial, z) plane
        ox = WIRE_R * math.cos(a) * rx
        oy = WIRE_R * math.cos(a) * ry
        oz = WIRE_R * math.sin(a)
        v = bm.verts.new((cx + ox, cy + oy, z + oz))
        ring.append(v)
    bm.verts.ensure_lookup_table()
    if prev_ring:
        for k in range(PROFILE_SEG):
            k2 = (k + 1) % PROFILE_SEG
            bm.faces.new((prev_ring[k], prev_ring[k2], ring[k2], ring[k]))
    prev_ring = ring
bm.normal_update()
bm.to_mesh(mesh_t)
bm.free()

# ---------- Material: Steel ----------
mat = bpy.data.materials.new("SteelM6")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.72, 0.72, 0.74, 1.0)
bsdf.inputs["Metallic"].default_value = 1.0
bsdf.inputs["Roughness"].default_value = 0.15
for o in (head, shank, thread):
    o.data.materials.append(mat)

# ---------- Camera ----------
cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (45, -55, 25)
cam.rotation_euler = (math.radians(70), 0, math.radians(40))
bpy.context.scene.camera = cam

# ---------- 3-point lighting ----------
def add_light(name, kind, energy, loc):
    ld = bpy.data.lights.new(name, type=kind)
    ld.energy = energy
    obj = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    return obj

key  = add_light("Key",  'AREA', 800, ( 30,  -30, 40))
fill = add_light("Fill", 'AREA', 300, (-40,  -20, 25))
rim  = add_light("Rim",  'AREA', 500, (  0,   40, 35))
key.data.size  = 20
fill.data.size = 30
rim.data.size  = 15

bpy.context.scene.render.engine = 'CYCLES'
