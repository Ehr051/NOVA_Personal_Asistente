"""
engranaje_recto.py
Spur gear: 20 teeth, module 1, pressure angle 20 deg.
Width 8mm, hub diameter 12mm, bore 6mm.
Uses involute tooth profile.
"""
import bpy, bmesh, math, mathutils

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# ---------- Gear parameters ----------
Z       = 20                 # tooth count
M       = 1.0                # module
PA      = math.radians(20)   # pressure angle
WIDTH   = 8.0
HUB_R   = 6.0                # hub radius (12mm dia)
BORE_R  = 3.0                # bore radius (6mm dia)

# Standard gear geometry
PITCH_R   = M * Z / 2.0
BASE_R    = PITCH_R * math.cos(PA)
ADD_R     = PITCH_R + M           # addendum circle
DED_R     = PITCH_R - 1.25 * M    # dedendum circle
ROOT_R    = max(DED_R, BASE_R - 0.05)

TOOTH_ANG = 2 * math.pi / Z

# ---------- Involute helpers ----------
def involute_point(base_r, t):
    x = base_r * (math.cos(t) + t * math.sin(t))
    y = base_r * (math.sin(t) - t * math.cos(t))
    return x, y

def involute_at_radius(base_r, target_r):
    # solve r(t) = base_r * sqrt(1 + t^2) = target_r
    if target_r < base_r:
        return 0.0
    return math.sqrt((target_r / base_r) ** 2 - 1.0)

# Pressure-angle parameter at pitch circle defines the tooth half-thickness offset.
t_pitch = involute_at_radius(BASE_R, PITCH_R)
inv_alpha = math.tan(PA) - PA   # involute function at pitch
# tooth thickness at pitch circle = pi*M/2 -> half-angle subtended = pi/(2Z)
half_tooth_angle_at_pitch = math.pi / (2 * Z)
# angle offset so the tooth is centered at theta=0
t_addendum = involute_at_radius(BASE_R, ADD_R)

INV_SAMPLES = 12

def build_tooth_profile(theta_center):
    """Return list of (x,y) points for one tooth, traced root->flank->tip->flank->root."""
    pts = []
    # Right flank (from base/root up to addendum), evaluated as involute
    # Angle offset of involute curve so that at pitch radius we are at -half_tooth_angle_at_pitch
    # Generated involute angle at param t: phi(t) = atan2(y,x) where (x,y) = involute_point(BASE_R, t)
    # We want phi(t_pitch) + offset = -half_tooth_angle_at_pitch  -> offset
    px, py = involute_point(BASE_R, t_pitch)
    phi_at_pitch = math.atan2(py, px)
    offset_right = -half_tooth_angle_at_pitch - phi_at_pitch
    # Root point on right side at root radius along direction (offset_right_root_angle)
    # We start at base radius (or root) on the right flank
    t_start = 0.0 if ROOT_R <= BASE_R else involute_at_radius(BASE_R, ROOT_R)
    # Right flank
    for i in range(INV_SAMPLES + 1):
        t = t_start + (t_addendum - t_start) * i / INV_SAMPLES
        x, y = involute_point(BASE_R, t)
        ang = math.atan2(y, x) + offset_right + theta_center
        r   = math.hypot(x, y)
        pts.append((r * math.cos(ang), r * math.sin(ang)))
    # Tip arc (small)
    tip_arc_n = 4
    a_right_tip = math.atan2(pts[-1][1], pts[-1][0])
    a_left_tip  = 2 * theta_center - a_right_tip   # mirror around theta_center
    # ensure correct direction
    if a_left_tip < a_right_tip:
        a_left_tip += 2 * math.pi
    for i in range(1, tip_arc_n + 1):
        a = a_right_tip + (a_left_tip - a_right_tip) * i / (tip_arc_n + 1)
        pts.append((ADD_R * math.cos(a), ADD_R * math.sin(a)))
    # Left flank: mirror of right flank around theta_center, in reverse order
    for i in range(INV_SAMPLES + 1):
        t = t_addendum - (t_addendum - t_start) * i / INV_SAMPLES
        x, y = involute_point(BASE_R, t)
        ang_r = math.atan2(y, x) + offset_right
        r = math.hypot(x, y)
        # mirror: angle about 0 then shift to theta_center
        ang = -ang_r + theta_center  # we already shifted right by theta_center for first half;
        # but we need theta_center applied once. Recompute cleanly:
        ang = (-(ang_r)) + theta_center
        pts.append((r * math.cos(ang), r * math.sin(ang)))
    return pts

# Build full closed outer profile: tooth + root arc, repeated Z times
outer_pts = []
ROOT_ARC_N = 4
for k in range(Z):
    theta_center = k * TOOTH_ANG
    tooth = build_tooth_profile(theta_center)
    outer_pts.extend(tooth)
    # Root arc to next tooth start
    a0 = math.atan2(tooth[-1][1], tooth[-1][0])
    next_tooth_first = build_tooth_profile((k + 1) * TOOTH_ANG)[0]
    a1 = math.atan2(next_tooth_first[1], next_tooth_first[0])
    if a1 < a0:
        a1 += 2 * math.pi
    for i in range(1, ROOT_ARC_N):
        a = a0 + (a1 - a0) * i / ROOT_ARC_N
        outer_pts.append((ROOT_R * math.cos(a), ROOT_R * math.sin(a)))

# ---------- Build mesh ----------
mesh = bpy.data.meshes.new("GearMesh")
gear = bpy.data.objects.new("SpurGear", mesh)
bpy.context.collection.objects.link(gear)
bm = bmesh.new()

# Outer profile bottom and top loops
bot_outer = [bm.verts.new((x, y, 0)) for (x, y) in outer_pts]
top_outer = [bm.verts.new((x, y, WIDTH)) for (x, y) in outer_pts]
# Bore loop
BORE_SEG = 48
bot_bore = []
top_bore = []
for i in range(BORE_SEG):
    a = 2 * math.pi * i / BORE_SEG
    bot_bore.append(bm.verts.new((BORE_R * math.cos(a), BORE_R * math.sin(a), 0)))
    top_bore.append(bm.verts.new((BORE_R * math.cos(a), BORE_R * math.sin(a), WIDTH)))

bm.verts.ensure_lookup_table()

# Side wall outer
N = len(outer_pts)
for i in range(N):
    j = (i + 1) % N
    bm.faces.new((bot_outer[i], bot_outer[j], top_outer[j], top_outer[i]))
# Side wall bore (inward)
for i in range(BORE_SEG):
    j = (i + 1) % BORE_SEG
    bm.faces.new((bot_bore[j], bot_bore[i], top_bore[i], top_bore[j]))

# Caps via bridge_loops between outer and bore
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

# Material: cast iron
mat = bpy.data.materials.new("CastIron")
mat.use_nodes = True
b = mat.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.20, 0.20, 0.22, 1.0)
b.inputs["Metallic"].default_value = 0.7
b.inputs["Roughness"].default_value = 0.6
gear.data.materials.append(mat)

# Camera
cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (45, -55, 38)
cam.rotation_euler = (math.radians(60), 0, math.radians(40))
bpy.context.scene.camera = cam

def add_light(name, kind, energy, loc, size=15):
    ld = bpy.data.lights.new(name, type=kind); ld.energy = energy
    if hasattr(ld, "size"): ld.size = size
    o = bpy.data.objects.new(name, ld); bpy.context.collection.objects.link(o)
    o.location = loc; return o

add_light("Key",  'AREA', 900, ( 35, -35, 50), 22)
add_light("Fill", 'AREA', 350, (-40, -15, 30), 30)
add_light("Rim",  'AREA', 550, (  0,  35, 45), 18)

bpy.context.scene.render.engine = 'CYCLES'
