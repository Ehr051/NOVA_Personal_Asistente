"""
perfil_aluminio_2020.py
20x20mm T-slot aluminum extrusion profile, 100mm long.
Cross-section: outer 20x20, 4 T-slots (one per face), center bore 4.2mm.
Built by tracing the 2D profile outline then extruding along Z.
"""
import bpy, bmesh, math, mathutils

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# ---------- Parameters (mm) ----------
SIDE          = 20.0
LENGTH        = 100.0
SLOT_OPEN     = 6.0     # outer slot opening width
SLOT_INNER    = 11.0    # inner T-slot width
SLOT_DEPTH    = 6.5     # depth from outer face to inner T-slot floor
SLOT_OPEN_DEP = 1.6     # depth of straight outer opening before T widens
CENTER_BORE_R = 2.1     # 4.2mm dia
BORE_SEG      = 32

half = SIDE / 2.0

# ---------- Build 2D outline of one quadrant of the cross-section ----------
# Strategy: build the full closed outer outline as a list of (x, y) points
# starting at top-right corner, going clockwise around the part.
# For each of the 4 sides we insert a T-slot cut-in.

def slot_profile_for_side(side_index):
    """
    Returns list of points describing the slot intrusion on the given side.
    side_index: 0=top (+Y), 1=right (+X), 2=bottom (-Y), 3=left (-X)
    Points are in CW order, in the slot's local frame, then transformed.
    Local frame: x along the face (left->right CW), y inward (toward center).
    """
    o2 = SLOT_OPEN / 2
    i2 = SLOT_INNER / 2
    d_open = SLOT_OPEN_DEP
    d_full = SLOT_DEPTH
    # In local CW order along the face going from left edge to right edge of slot:
    return [
        (-o2, 0),              # slot mouth left
        (-o2, d_open),         # straight opening left
        (-i2, d_open),         # widen left
        (-i2, d_full),         # T floor left
        ( i2, d_full),         # T floor right
        ( i2, d_open),         # widen right
        ( o2, d_open),         # straight opening right
        ( o2, 0),              # slot mouth right
    ]

def transform_to_side(pts, side_index):
    """Map slot-local (x,y) to global (X,Y) on the 20x20 face."""
    out = []
    for (x, y) in pts:
        if side_index == 0:    # top (+Y), local x = +X, inward = -Y
            X, Y =  x, half - y
        elif side_index == 1:  # right (+X), local x = -Y, inward = -X
            X, Y =  half - y, -x
        elif side_index == 2:  # bottom (-Y), local x = -X, inward = +Y
            X, Y = -x, -half + y
        else:                  # left (-X), local x = +Y, inward = +X
            X, Y = -half + y,  x
        out.append((X, Y))
    return out

# Build outer outline CW starting at corner (+X,+Y) -> top side -> (-X,+Y)...
outline = []
corners = [( half,  half),
           (-half,  half),
           (-half, -half),
           ( half, -half)]
# side i goes from corner i to corner i+1
side_corner_pairs = [(0, 1), (3, 0), (2, 3), (1, 2)]
# But we want CW starting at (+X,+Y): top edge goes (+X,+Y) -> (-X,+Y) which is side 0
sides_cw = [
    ( 0, ( half,  half), (-half,  half)),  # top
    ( 3, (-half,  half), (-half, -half)),  # left
    ( 2, (-half, -half), ( half, -half)),  # bottom
    ( 1, ( half, -half), ( half,  half)),  # right
]

for side_index, c_from, c_to in sides_cw:
    outline.append(c_from)
    slot_pts = transform_to_side(slot_profile_for_side(side_index), side_index)
    # The slot points must be inserted in correct order along the traversal.
    # Determine direction along face: vector from c_from to c_to.
    vx = c_to[0] - c_from[0]
    vy = c_to[1] - c_from[1]
    def proj(p):
        return (p[0] - c_from[0]) * vx + (p[1] - c_from[1]) * vy
    slot_pts_sorted = sorted(slot_pts, key=proj)
    outline.extend(slot_pts_sorted)
# close to first corner naturally as next iter inserts it; final corner handled by loop closure

# ---------- Build mesh ----------
mesh = bpy.data.meshes.new("Extrusion2020Mesh")
ext = bpy.data.objects.new("Aluminio2020", mesh)
bpy.context.collection.objects.link(ext)
bm = bmesh.new()

# Bottom (z=0) and top (z=LENGTH) outer outlines
bot_outer = [bm.verts.new((x, y, 0))      for (x, y) in outline]
top_outer = [bm.verts.new((x, y, LENGTH)) for (x, y) in outline]

# Center bore loops
bot_bore = []
top_bore = []
for i in range(BORE_SEG):
    a = 2 * math.pi * i / BORE_SEG
    bot_bore.append(bm.verts.new((CENTER_BORE_R * math.cos(a),
                                  CENTER_BORE_R * math.sin(a), 0)))
    top_bore.append(bm.verts.new((CENTER_BORE_R * math.cos(a),
                                  CENTER_BORE_R * math.sin(a), LENGTH)))

bm.verts.ensure_lookup_table()

N = len(outline)
# Outer side walls
for i in range(N):
    j = (i + 1) % N
    bm.faces.new((bot_outer[i], bot_outer[j], top_outer[j], top_outer[i]))
# Bore side wall (inward)
for i in range(BORE_SEG):
    j = (i + 1) % BORE_SEG
    bm.faces.new((bot_bore[j], bot_bore[i], top_bore[i], top_bore[j]))

def edges_loop(verts):
    es = []
    for i in range(len(verts)):
        j = (i + 1) % len(verts)
        e = bm.edges.get((verts[i], verts[j])) or bm.edges.new((verts[i], verts[j]))
        es.append(e)
    return es

bmesh.ops.bridge_loops(bm, edges=edges_loop(bot_outer) + edges_loop(bot_bore))
bmesh.ops.bridge_loops(bm, edges=edges_loop(top_outer) + edges_loop(top_bore))

bm.normal_update()
bm.to_mesh(mesh)
bm.free()

# Material: anodized aluminum
mat = bpy.data.materials.new("AnodizedAlu")
mat.use_nodes = True
b = mat.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.78, 0.79, 0.81, 1.0)
b.inputs["Metallic"].default_value = 0.9
b.inputs["Roughness"].default_value = 0.1
ext.data.materials.append(mat)

# Camera
cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (90, -120, 90)
cam.rotation_euler = (math.radians(65), 0, math.radians(40))
bpy.context.scene.camera = cam

def add_light(name, kind, energy, loc, size=20):
    ld = bpy.data.lights.new(name, type=kind); ld.energy = energy
    if hasattr(ld, "size"): ld.size = size
    o = bpy.data.objects.new(name, ld); bpy.context.collection.objects.link(o)
    o.location = loc; return o

add_light("Key",  'AREA', 1500, ( 80, -80, 120), 35)
add_light("Fill", 'AREA',  500, (-90, -30,  60), 50)
add_light("Rim",  'AREA',  900, (  0,  90, 100), 25)

bpy.context.scene.render.engine = 'CYCLES'
