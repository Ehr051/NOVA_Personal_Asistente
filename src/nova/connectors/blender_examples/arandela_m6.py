"""
arandela_m6.py
M6 flat washer. Outer 12mm, inner 6.5mm, thickness 1.6mm. Zinc plated.
"""
import bpy, bmesh, math, mathutils

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

OUTER_R = 6.0
INNER_R = 3.25
THICK   = 1.6
SEG     = 64

mesh = bpy.data.meshes.new("WasherMesh")
washer = bpy.data.objects.new("WasherM6", mesh)
bpy.context.collection.objects.link(washer)

bm = bmesh.new()
bot_outer, top_outer, bot_inner, top_inner = [], [], [], []
for i in range(SEG):
    a = 2 * math.pi * i / SEG
    co = math.cos(a); si = math.sin(a)
    bot_outer.append(bm.verts.new((OUTER_R*co, OUTER_R*si, 0)))
    top_outer.append(bm.verts.new((OUTER_R*co, OUTER_R*si, THICK)))
    bot_inner.append(bm.verts.new((INNER_R*co, INNER_R*si, 0)))
    top_inner.append(bm.verts.new((INNER_R*co, INNER_R*si, THICK)))

bm.verts.ensure_lookup_table()

# Outer side
for i in range(SEG):
    j = (i + 1) % SEG
    bm.faces.new((bot_outer[i], bot_outer[j], top_outer[j], top_outer[i]))
# Inner side (flipped winding -> faces inward)
for i in range(SEG):
    j = (i + 1) % SEG
    bm.faces.new((bot_inner[j], bot_inner[i], top_inner[i], top_inner[j]))
# Top and bottom annular caps
for i in range(SEG):
    j = (i + 1) % SEG
    bm.faces.new((top_outer[i], top_outer[j], top_inner[j], top_inner[i]))
    bm.faces.new((bot_outer[j], bot_outer[i], bot_inner[i], bot_inner[j]))

# Slight bevel on outer edges
outer_edges_top = [e for e in bm.edges
                   if e.verts[0] in top_outer and e.verts[1] in top_outer]
outer_edges_bot = [e for e in bm.edges
                   if e.verts[0] in bot_outer and e.verts[1] in bot_outer]
bmesh.ops.bevel(bm, geom=outer_edges_top + outer_edges_bot,
                offset=0.15, segments=2, affect='EDGES')

bm.normal_update()
bm.to_mesh(mesh)
bm.free()

# Smooth shading
for p in mesh.polygons:
    p.use_smooth = True

# Material: zinc plated, slight blue tint
mat = bpy.data.materials.new("ZincPlated")
mat.use_nodes = True
b = mat.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.78, 0.82, 0.88, 1.0)
b.inputs["Metallic"].default_value = 0.8
b.inputs["Roughness"].default_value = 0.3
washer.data.materials.append(mat)

# Camera
cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (20, -25, 15)
cam.rotation_euler = (math.radians(65), 0, math.radians(40))
bpy.context.scene.camera = cam

def add_light(name, kind, energy, loc, size=10):
    ld = bpy.data.lights.new(name, type=kind); ld.energy = energy
    if hasattr(ld, "size"): ld.size = size
    o = bpy.data.objects.new(name, ld); bpy.context.collection.objects.link(o)
    o.location = loc; return o

add_light("Key",  'AREA', 500, ( 18, -18, 22), 12)
add_light("Fill", 'AREA', 200, (-22,  -8, 16), 18)
add_light("Rim",  'AREA', 350, (  0,  18, 22), 10)

bpy.context.scene.render.engine = 'CYCLES'
