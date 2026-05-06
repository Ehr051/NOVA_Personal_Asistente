"""
tornillo_allen_m4.py
M4 x 16mm socket head cap screw (Allen bolt). Black oxide steel.
"""
import bpy, bmesh, math, mathutils

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Parameters (mm)
HEAD_DIA   = 7.0
HEAD_H     = 4.0
SHANK_DIA  = 4.0
SHANK_LEN  = 12.0
HEX_KEY    = 3.0      # across flats
HEX_DEPTH  = 2.0
SEG        = 48

# ---------- Head ----------
mesh_h = bpy.data.meshes.new("HeadMesh")
head = bpy.data.objects.new("AllenHead", mesh_h)
bpy.context.collection.objects.link(head)
bm = bmesh.new()

# Build head as a cylinder with a hex pocket
HR = HEAD_DIA / 2
HEX_R = HEX_KEY / math.cos(math.radians(30)) / 2

# Outer rings
bot = []
top = []
for i in range(SEG):
    a = 2*math.pi*i/SEG
    bot.append(bm.verts.new((HR*math.cos(a), HR*math.sin(a), 0)))
    top.append(bm.verts.new((HR*math.cos(a), HR*math.sin(a), HEAD_H)))

# Hex pocket rings (top opening at HEAD_H, bottom of pocket at HEAD_H - HEX_DEPTH)
hex_top = []
hex_bot = []
for i in range(6):
    a = math.pi/6 + i*math.pi/3
    x = HEX_R*math.cos(a); y = HEX_R*math.sin(a)
    hex_top.append(bm.verts.new((x, y, HEAD_H)))
    hex_bot.append(bm.verts.new((x, y, HEAD_H - HEX_DEPTH)))

bm.verts.ensure_lookup_table()

# Outer side wall
for i in range(SEG):
    j = (i+1) % SEG
    bm.faces.new((bot[i], bot[j], top[j], top[i]))
# Bottom cap (closed disk)
bm.faces.new(tuple(reversed(bot)))

# Hex pocket walls (inward facing)
for i in range(6):
    j = (i+1) % 6
    bm.faces.new((hex_top[j], hex_top[i], hex_bot[i], hex_bot[j]))
# Hex pocket floor
bm.faces.new(tuple(hex_bot))

# Top annular face (between outer top circle and hex_top) using bridge_loops
def edges_loop(verts):
    es = []
    for i in range(len(verts)):
        j = (i+1) % len(verts)
        e = bm.edges.get((verts[i], verts[j])) or bm.edges.new((verts[i], verts[j]))
        es.append(e)
    return es

top_outer_edges = edges_loop(top)
hex_top_edges   = edges_loop(hex_top)
bmesh.ops.bridge_loops(bm, edges=top_outer_edges + hex_top_edges)

# Slight chamfer on outer top edge
bmesh.ops.bevel(bm,
                geom=[e for e in bm.edges if e.verts[0] in top and e.verts[1] in top],
                offset=0.2, segments=1, affect='EDGES')

bm.normal_update()
bm.to_mesh(mesh_h)
bm.free()
head.location = (0, 0, 0)

# ---------- Shank ----------
mesh_s = bpy.data.meshes.new("ShankMesh")
shank = bpy.data.objects.new("AllenShank", mesh_s)
bpy.context.collection.objects.link(shank)
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=32,
                      radius1=SHANK_DIA/2, radius2=SHANK_DIA/2,
                      depth=SHANK_LEN)
bm.to_mesh(mesh_s); bm.free()
shank.location = (0, 0, -SHANK_LEN/2)

# ---------- Material: Black oxide ----------
mat = bpy.data.materials.new("BlackOxide")
mat.use_nodes = True
b = mat.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.04, 0.04, 0.05, 1.0)
b.inputs["Metallic"].default_value = 0.9
b.inputs["Roughness"].default_value = 0.3
for o in (head, shank):
    o.data.materials.append(mat)

# Smooth shank
for p in shank.data.polygons:
    p.use_smooth = True

# Camera
cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (28, -32, 18)
cam.rotation_euler = (math.radians(70), 0, math.radians(42))
bpy.context.scene.camera = cam

def add_light(name, kind, energy, loc, size=10):
    ld = bpy.data.lights.new(name, type=kind); ld.energy = energy
    if hasattr(ld, "size"): ld.size = size
    o = bpy.data.objects.new(name, ld); bpy.context.collection.objects.link(o)
    o.location = loc; return o

add_light("Key",  'AREA', 700, ( 22, -22, 28), 14)
add_light("Fill", 'AREA', 280, (-26,  -8, 18), 20)
add_light("Rim",  'AREA', 450, (  0,  22, 28), 12)

bpy.context.scene.render.engine = 'CYCLES'
