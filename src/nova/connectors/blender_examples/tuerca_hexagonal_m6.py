"""
tuerca_hexagonal_m6.py
M6 hex nut. Hex prism with center hole and 30 deg chamfers top/bottom.
"""
import bpy, bmesh, math, mathutils

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Parameters (mm)
FLATS         = 10.0
HEIGHT        = 5.0
HOLE_DIA      = 6.0
CHAMFER_OFF   = 0.6
HEX_R         = FLATS / math.cos(math.radians(30)) / 2.0
HOLE_R        = HOLE_DIA / 2.0

# ---------- Build hex prism ----------
mesh = bpy.data.meshes.new("NutMesh")
nut = bpy.data.objects.new("HexNutM6", mesh)
bpy.context.collection.objects.link(nut)

bm = bmesh.new()
# Outer hex bottom ring
bottom_outer = []
top_outer = []
for i in range(6):
    a = math.pi / 6 + i * math.pi / 3
    x = HEX_R * math.cos(a)
    y = HEX_R * math.sin(a)
    bottom_outer.append(bm.verts.new((x, y, 0)))
    top_outer.append(bm.verts.new((x, y, HEIGHT)))

# Inner hole rings (32-sided)
HOLE_SEG = 32
bottom_inner = []
top_inner = []
for i in range(HOLE_SEG):
    a = 2 * math.pi * i / HOLE_SEG
    x = HOLE_R * math.cos(a)
    y = HOLE_R * math.sin(a)
    bottom_inner.append(bm.verts.new((x, y, 0)))
    top_inner.append(bm.verts.new((x, y, HEIGHT)))

bm.verts.ensure_lookup_table()

# Side faces (outer hex)
for i in range(6):
    j = (i + 1) % 6
    bm.faces.new((bottom_outer[i], bottom_outer[j], top_outer[j], top_outer[i]))

# Side faces (inner hole) - inward-facing
for i in range(HOLE_SEG):
    j = (i + 1) % HOLE_SEG
    bm.faces.new((bottom_inner[j], bottom_inner[i], top_inner[i], top_inner[j]))

# Bottom annular face: bridge hex to inner hole using grid_fill
# Use a simple fan approach: triangulate between hex vertices and nearest inner vertices
def annulus_caps(outer, inner, z_top):
    # connect each hex segment to the corresponding arc of inner verts
    for i in range(6):
        j = (i + 1) % 6
        # find inner verts whose angle is within this hex sector
        a0 = math.atan2(outer[i].co.y, outer[i].co.x)
        a1 = math.atan2(outer[j].co.y, outer[j].co.x)
        if a1 < a0:
            a1 += 2 * math.pi
        sector_inner = []
        for k, v in enumerate(inner):
            ang = math.atan2(v.co.y, v.co.x)
            if ang < a0 - 1e-4:
                ang += 2 * math.pi
            if a0 - 1e-4 <= ang <= a1 + 1e-4:
                sector_inner.append((ang, k, v))
        sector_inner.sort()
        # triangle fan: outer[i] -> sector_inner -> outer[j]
        verts_chain = [outer[i]] + [v for _, _, v in sector_inner] + [outer[j]]
        for m in range(len(verts_chain) - 1):
            try:
                if z_top:
                    bm.faces.new((verts_chain[m], verts_chain[m+1],
                                  bm.verts.new((0, 0, 0))))  # placeholder
            except Exception:
                pass

# Simpler: use bmesh.ops.bridge_loops between two closed loops by creating edge loops
def edges_from_loop(verts):
    edges = []
    for i in range(len(verts)):
        j = (i + 1) % len(verts)
        e = bm.edges.get((verts[i], verts[j])) or bm.edges.new((verts[i], verts[j]))
        edges.append(e)
    return edges

bot_outer_edges = edges_from_loop(bottom_outer)
bot_inner_edges = edges_from_loop(bottom_inner)
top_outer_edges = edges_from_loop(top_outer)
top_inner_edges = edges_from_loop(top_inner)

bmesh.ops.bridge_loops(bm, edges=bot_outer_edges + bot_inner_edges)
bmesh.ops.bridge_loops(bm, edges=top_outer_edges + top_inner_edges)

# ---------- Chamfers (top and bottom outer corners) ----------
top_corner_edges = [e for e in bm.edges
                    if e.verts[0] in top_outer and e.verts[1] in top_outer]
bot_corner_edges = [e for e in bm.edges
                    if e.verts[0] in bottom_outer and e.verts[1] in bottom_outer]
bmesh.ops.bevel(bm, geom=top_corner_edges, offset=CHAMFER_OFF,
                segments=1, profile=0.5, affect='EDGES')
bmesh.ops.bevel(bm, geom=bot_corner_edges, offset=CHAMFER_OFF,
                segments=1, profile=0.5, affect='EDGES')

bm.normal_update()
bm.to_mesh(mesh)
bm.free()
nut.location = (0, 0, 0)

# ---------- Material ----------
mat = bpy.data.materials.new("SteelNut")
mat.use_nodes = True
b = mat.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.7, 0.7, 0.72, 1.0)
b.inputs["Metallic"].default_value = 0.95
b.inputs["Roughness"].default_value = 0.2
nut.data.materials.append(mat)

# ---------- Camera ----------
cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (25, -30, 18)
cam.rotation_euler = (math.radians(65), 0, math.radians(40))
bpy.context.scene.camera = cam

# ---------- Lights ----------
def add_light(name, kind, energy, loc, size=10):
    ld = bpy.data.lights.new(name, type=kind); ld.energy = energy
    if hasattr(ld, "size"): ld.size = size
    o = bpy.data.objects.new(name, ld); bpy.context.collection.objects.link(o)
    o.location = loc; return o

add_light("Key",  'AREA', 600, ( 20, -20, 25), 15)
add_light("Fill", 'AREA', 250, (-25, -10, 18), 20)
add_light("Rim",  'AREA', 400, (  0,  20, 25), 12)

bpy.context.scene.render.engine = 'CYCLES'
