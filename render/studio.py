"""Blender studio kit: premium procedural materials, props, lights, cameras.

Runs inside Blender's Python (bpy). Geometry comes from stonekit in
millimetres and is converted to metres here.
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from stonekit import shapes  # noqa: E402
from stonekit.mesh import rot_matrix  # noqa: E402

MM = 0.001


# --------------------------------------------------------------------------
# scene
# --------------------------------------------------------------------------

def reset_scene(samples=192):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.unit_settings.system = "METRIC"
    s.render.engine = "CYCLES"
    c = s.cycles
    c.device = "CPU"
    c.samples = samples
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.01
    c.use_denoising = True
    c.max_bounces = 12
    c.diffuse_bounces = 4
    c.glossy_bounces = 6
    c.transmission_bounces = 12
    c.transparent_max_bounces = 8
    c.caustics_reflective = False
    c.caustics_refractive = False
    c.blur_glossy = 1.0
    s.view_settings.view_transform = "AgX"
    s.view_settings.exposure = -1.2
    for look in ("AgX - Medium High Contrast", "AgX - Base Contrast"):
        try:
            s.view_settings.look = look
            break
        except TypeError:
            continue
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_depth = "8"
    world = bpy.data.worlds.new("Studio")
    s.world = world
    return s


def world_color(color, strength):
    w = bpy.context.scene.world
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes.get("Background") or nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (*color, 1.0)
    bg.inputs["Strength"].default_value = strength
    out = nt.nodes.get("World Output") or nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs[0], out.inputs[0])


# --------------------------------------------------------------------------
# node helpers
# --------------------------------------------------------------------------

class Tree:
    """Tiny wrapper to keep shader graphs readable."""

    def __init__(self, mat):
        mat.use_nodes = True
        self.nt = mat.node_tree
        self.nt.nodes.clear()
        self.x = 0

    def node(self, kind, inputs=None, **props):
        n = self.nt.nodes.new(kind)
        n.location = (self.x, 0)
        self.x += 220
        for k, v in props.items():
            setattr(n, k, v)
        for k, v in (inputs or {}).items():
            sock(n.inputs, k).default_value = v
        return n

    def link(self, a, b):
        self.nt.links.new(a, b)


def sock(coll, name, kind=None):
    if isinstance(name, int):
        return coll[name]
    for s_ in coll:
        if s_.name == name and (kind is None or s_.type == kind) and s_.enabled:
            return s_
    for s_ in coll:
        if s_.name == name and (kind is None or s_.type == kind):
            return s_
    raise KeyError(name)


def coords(t, scale=1.0, stretch=(1.0, 1.0, 1.0), seed_per_object=True):
    """Object-space coordinates, offset per object so copies don't match."""
    tc = t.node("ShaderNodeTexCoord")
    vec = tc.outputs["Object"]
    if seed_per_object:
        oi = t.node("ShaderNodeObjectInfo")
        cx = t.node("ShaderNodeCombineXYZ")
        for i, f in enumerate((13.7, 7.3, 5.1)):
            m = t.node("ShaderNodeMath", operation="MULTIPLY", inputs={1: f})
            t.link(oi.outputs["Random"], m.inputs[0])
            t.link(m.outputs[0], cx.inputs[i])
        add = t.node("ShaderNodeVectorMath", operation="ADD")
        t.link(vec, add.inputs[0]); t.link(cx.outputs[0], add.inputs[1])
        vec = add.outputs[0]
    mp = t.node("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = tuple(scale * k for k in stretch)
    t.link(vec, mp.inputs["Vector"])
    return mp.outputs[0]


def noise(t, vec, scale, detail=4.0, rough=0.5, distortion=0.0):
    n = t.node("ShaderNodeTexNoise", inputs={"Scale": scale, "Detail": detail,
                                            "Roughness": rough, "Distortion": distortion})
    t.link(vec, n.inputs["Vector"])
    return n


def voronoi(t, vec, scale, feature="F1", randomness=1.0):
    v = t.node("ShaderNodeTexVoronoi", feature=feature, inputs={"Scale": scale, "Randomness": randomness})
    t.link(vec, v.inputs["Vector"])
    return v


def ramp(t, fac, stops, interp="LINEAR"):
    r = t.node("ShaderNodeValToRGB")
    cr = r.color_ramp
    cr.interpolation = interp
    while len(cr.elements) > len(stops):
        cr.elements.remove(cr.elements[-1])
    while len(cr.elements) < len(stops):
        cr.elements.new(0.5)
    for el, (pos, col) in zip(cr.elements, stops):
        el.position = pos
        el.color = (*col, 1.0) if len(col) == 3 else col
    t.link(fac, r.inputs["Fac"])
    return r.outputs["Color"]


def mix(t, fac, a, b, blend="MIX"):
    m = t.node("ShaderNodeMix", data_type="RGBA", blend_type=blend)
    if isinstance(fac, (int, float)):
        m.inputs[0].default_value = fac
    else:
        t.link(fac, m.inputs[0])
    for s_, v in ((sock(m.inputs, "A", "RGBA"), a), (sock(m.inputs, "B", "RGBA"), b)):
        if isinstance(v, tuple):
            s_.default_value = (*v, 1.0) if len(v) == 3 else v
        else:
            t.link(v, s_)
    return sock(m.outputs, "Result", "RGBA")


def math_(t, op, a, b=None):
    m = t.node("ShaderNodeMath", operation=op)
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = v
        else:
            t.link(v, m.inputs[i])
    return m.outputs[0]


def bump(t, height, strength, distance, normal=None):
    b = t.node("ShaderNodeBump", inputs={"Strength": strength, "Distance": distance})
    t.link(height, b.inputs["Height"])
    if normal is not None:
        t.link(normal, b.inputs["Normal"])
    return b.outputs["Normal"]


def principled(t, base, rough, normal=None, **extra):
    p = t.node("ShaderNodeBsdfPrincipled")
    for k, v in (("Base Color", base), ("Roughness", rough), ("Normal", normal)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            p.inputs[k].default_value = v
        elif isinstance(v, tuple):
            p.inputs[k].default_value = (*v, 1.0) if len(v) == 3 else v
        else:
            t.link(v, p.inputs[k])
    for k, v in extra.items():
        p.inputs[k.replace("_", " ")].default_value = v
    out = t.node("ShaderNodeOutputMaterial")
    t.link(p.outputs[0], out.inputs["Surface"])
    return p


def new_mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    return m, Tree(m)


# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------

BUFF_DARK = (0.34, 0.285, 0.195)
BUFF_LIGHT = (0.53, 0.465, 0.345)


def limestone(name, finish):
    """Indiana limestone: buff mottling, fossil hash, finish-specific relief."""
    m, t = new_mat(name)
    v = coords(t)
    mott = noise(t, v, 6.0, 8.0, 0.55)
    col = ramp(t, mott.outputs["Fac"], [(0.32, BUFF_DARK), (0.68, BUFF_LIGHT)])
    cloud = noise(t, v, 1.3, 3.0, 0.5)
    col = mix(t, 0.35, col, ramp(t, cloud.outputs["Fac"], [(0.35, (0.80, 0.80, 0.82)),
                                                           (0.65, (1.0, 0.97, 0.90))]), "MULTIPLY")
    # fossil hash: dark shell fragments, sparse
    v1 = voronoi(t, v, 430.0)
    sparse = noise(t, v, 160.0, 2.0)
    shell = math_(t, "MULTIPLY",
                  math_(t, "LESS_THAN", v1.outputs["Distance"], 0.16),
                  math_(t, "GREATER_THAN", sparse.outputs["Fac"], 0.52))
    col = mix(t, math_(t, "MULTIPLY", shell, 0.85), col, (0.17, 0.14, 0.10))
    # bright calcite flecks
    v2 = voronoi(t, v, 1100.0)
    calc = math_(t, "MULTIPLY", math_(t, "LESS_THAN", v2.outputs["Distance"], 0.12),
                 math_(t, "GREATER_THAN", noise(t, v, 90.0, 2.0).outputs["Fac"], 0.56))
    col = mix(t, math_(t, "MULTIPLY", calc, 0.7), col, (0.70, 0.66, 0.56))

    rough_var = noise(t, v, 40.0, 3.0).outputs["Fac"]
    if finish == "honed":
        r = math_(t, "ADD", math_(t, "MULTIPLY", rough_var, 0.12), 0.34)
        fine = noise(t, v, 1800.0, 2.0)
        n = bump(t, fine.outputs["Fac"], 0.04, 0.00004)
        n = bump(t, shell, 0.25, 0.00012, n)              # fossils sit a hair proud/pitted
    elif finish == "split":
        r = math_(t, "ADD", math_(t, "MULTIPLY", rough_var, 0.08), 0.82)
        big = noise(t, v, 70.0, 12.0, 0.62)
        n = bump(t, big.outputs["Fac"], 0.55, 0.0025)
        grit = noise(t, v, 900.0, 4.0, 0.6)
        n = bump(t, grit.outputs["Fac"], 0.25, 0.0002, n)
        # weathering: hollows hold a little dust and iron stain, ridges catch light
        stain = ramp(t, big.outputs["Fac"], [(0.35, (0.80, 0.75, 0.68)), (0.62, (1.04, 1.02, 0.99))])
        col = mix(t, 1.0, col, stain, "MULTIPLY")
    elif finish == "sawn":
        r = math_(t, "ADD", math_(t, "MULTIPLY", rough_var, 0.1), 0.58)
        w = t.node("ShaderNodeTexWave", wave_type="RINGS", inputs={"Scale": 22.0, "Distortion": 1.5,
                                                                  "Detail": 3.0})
        t.link(v, w.inputs["Vector"])
        n = bump(t, w.outputs["Fac"], 0.06, 0.00008)        # faint diamond-saw arcs
        n = bump(t, noise(t, v, 1500.0, 2.0).outputs["Fac"], 0.06, 0.00005, n)
    else:
        raise ValueError(finish)
    principled(t, col, r, n, Subsurface_Weight=0.06, Subsurface_Scale=0.003,
               Subsurface_Radius=(1.0, 0.65, 0.4), Specular_IOR_Level=0.45)
    return m


def gold_leaf(name="Gold_Leaf"):
    m, t = new_mat(name)
    v = coords(t, seed_per_object=False)
    var = noise(t, v, 260.0, 4.0)
    col = ramp(t, var.outputs["Fac"], [(0.3, (0.86, 0.64, 0.30)), (0.7, (0.98, 0.80, 0.44))])
    r = math_(t, "ADD", math_(t, "MULTIPLY", var.outputs["Fac"], 0.12), 0.18)
    n = bump(t, noise(t, v, 2500.0, 2.0).outputs["Fac"], 0.08, 0.00003)
    principled(t, col, r, n, Metallic=1.0)
    return m


def ink(name="Ink"):
    m, t = new_mat(name)
    v = coords(t, seed_per_object=False)
    var = noise(t, v, 400.0, 3.0)
    col = ramp(t, var.outputs["Fac"], [(0.3, (0.010, 0.010, 0.012)), (0.7, (0.03, 0.028, 0.03))])
    principled(t, col, 0.55)
    return m


def cork(name="Cork"):
    m, t = new_mat(name)
    v0 = coords(t)
    warp = noise(t, v0, 260.0, 2.0)
    off = t.node("ShaderNodeVectorMath", operation="MULTIPLY_ADD")
    t.link(warp.outputs["Color"], off.inputs[0])
    off.inputs[1].default_value = (0.0016, 0.0016, 0.0016)
    t.link(v0, off.inputs[2])
    v = off.outputs[0]                                   # wobbly cells, not tiles
    cells = voronoi(t, v, 650.0)
    # each granule gets its own shade (voronoi cell colour -> brightness)
    col = ramp(t, cells.outputs["Color"],
               [(0.2, (0.12, 0.055, 0.022)), (0.5, (0.28, 0.15, 0.060)), (0.8, (0.44, 0.26, 0.11))])
    speck = noise(t, v0, 2600.0, 3.0)
    col = mix(t, math_(t, "GREATER_THAN", speck.outputs["Fac"], 0.62), col, (0.06, 0.03, 0.012))
    edge = voronoi(t, v, 650.0, "DISTANCE_TO_EDGE")
    seam = ramp(t, edge.outputs["Distance"], [(0.0, (0.25, 0.25, 0.25)), (0.05, (1, 1, 1))])
    col = mix(t, 1.0, col, seam, "MULTIPLY")
    dome = math_(t, "SUBTRACT", 1.0, cells.outputs["Distance"])
    n = bump(t, dome, 0.6, 0.00025)
    n = bump(t, speck.outputs["Fac"], 0.3, 0.00006, n)
    principled(t, col, 0.88, n, Sheen_Weight=0.15)
    return m


def felt(name="Felt"):
    m, t = new_mat(name)
    v = coords(t, seed_per_object=False)
    n = bump(t, noise(t, v, 3000.0, 6.0).outputs["Fac"], 0.4, 0.0001)
    principled(t, (0.018, 0.018, 0.02), 1.0, n, Sheen_Weight=0.9, Sheen_Roughness=0.6)
    return m


def soil(name="Soil"):
    m, t = new_mat(name)
    v = coords(t)
    clump = noise(t, v, 60.0, 8.0, 0.65)
    col = ramp(t, clump.outputs["Fac"], [(0.35, (0.022, 0.014, 0.009)), (0.65, (0.075, 0.050, 0.032))])
    perl = voronoi(t, v, 700.0)
    flake = math_(t, "MULTIPLY", math_(t, "LESS_THAN", perl.outputs["Distance"], 0.14),
                  math_(t, "GREATER_THAN", noise(t, v, 120.0, 2.0).outputs["Fac"], 0.6))
    col = mix(t, flake, col, (0.75, 0.73, 0.70))
    n = bump(t, clump.outputs["Fac"], 0.8, 0.002)
    n = bump(t, perl.outputs["Distance"], 0.4, 0.0005, n)
    principled(t, col, 0.95, n)
    return m


def river_pebble(name="Pebble"):
    m, t = new_mat(name)
    v = coords(t, seed_per_object=False)
    big = noise(t, v, 55.0, 2.0)            # changes pebble to pebble
    col = ramp(t, big.outputs["Fac"], [(0.30, (0.035, 0.035, 0.038)), (0.5, (0.12, 0.115, 0.11)),
                                       (0.7, (0.30, 0.27, 0.22))])
    vein = noise(t, v, 300.0, 6.0, 0.6)
    col = mix(t, 0.25, col, ramp(t, vein.outputs["Fac"], [(0.45, (0.7, 0.7, 0.7)), (0.55, (1, 1, 1))]),
              "MULTIPLY")
    n = bump(t, noise(t, v, 1200.0, 3.0).outputs["Fac"], 0.1, 0.0001)
    principled(t, col, 0.28, n, Coat_Weight=0.3)
    return m


def leaf(name, texture):
    m, t = new_mat(name)
    img = to_image(texture)
    tex = t.node("ShaderNodeTexImage")
    tex.image = img
    uv = t.node("ShaderNodeUVMap")
    t.link(uv.outputs[0], tex.inputs["Vector"])
    v = coords(t, seed_per_object=False)
    n = bump(t, noise(t, v, 800.0, 3.0).outputs["Fac"], 0.12, 0.00005)
    principled(t, tex.outputs["Color"], 0.33, n, Subsurface_Weight=0.12, Subsurface_Scale=0.002,
               Subsurface_Radius=(0.4, 1.0, 0.3), Coat_Weight=0.15)
    return m


def wood(name, light=False):
    """Oiled walnut (or white oak when light=True), grain running along x."""
    m, t = new_mat(name)
    v = coords(t, 1.0, (0.12, 1.0, 1.0))
    warp = noise(t, v, 8.0, 4.0, 0.55)
    off = t.node("ShaderNodeVectorMath", operation="MULTIPLY_ADD")
    t.link(warp.outputs["Color"], off.inputs[0])
    off.inputs[1].default_value = (0.0, 0.035, 0.0)
    t.link(v, off.inputs[2])
    grain = t.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="Y",
                   inputs={"Scale": 20.0, "Distortion": 7.0, "Detail": 6.0, "Detail Scale": 1.5,
                           "Detail Roughness": 0.6})
    t.link(off.outputs[0], grain.inputs["Vector"])
    pores = noise(t, coords(t, 1.0, (6.0, 1800.0, 1800.0)), 1.0, 4.0, 0.6)
    figure = noise(t, coords(t, 1.0, (0.5, 4.0, 4.0)), 3.0, 4.0, 0.5)
    fac = math_(t, "ADD", math_(t, "MULTIPLY", grain.outputs["Fac"], 0.33),
                math_(t, "ADD", math_(t, "MULTIPLY", pores.outputs["Fac"], 0.22),
                      math_(t, "MULTIPLY", figure.outputs["Fac"], 0.45)))
    stops = ([(0.3, (0.32, 0.20, 0.10)), (0.7, (0.55, 0.38, 0.21))] if light else
             [(0.30, (0.018, 0.009, 0.005)), (0.55, (0.045, 0.024, 0.013)), (0.78, (0.085, 0.048, 0.025))])
    col = ramp(t, fac, stops)
    n = bump(t, pores.outputs["Fac"], 0.15, 0.00005)
    principled(t, col, 0.48 if not light else 0.55, n, Coat_Weight=0.12, Coat_Roughness=0.3)
    return m


def plaster(name, color, scale_=40.0):
    m, t = new_mat(name)
    v = coords(t, seed_per_object=False)
    var = noise(t, v, 3.0, 4.0)
    col = mix(t, 0.15, color, ramp(t, var.outputs["Fac"], [(0.3, (0.8, 0.8, 0.8)), (0.7, (1.1, 1.1, 1.1))]),
              "MULTIPLY")
    n = bump(t, noise(t, v, scale_, 8.0, 0.6).outputs["Fac"], 0.08, 0.001)
    principled(t, col, 0.9, n)
    return m


def cloth(name, color):
    """Book cloth: tight weave, slight sheen."""
    m, t = new_mat(name)
    v = coords(t)
    wx = t.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="X", inputs={"Scale": 1800.0})
    wy = t.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="Y", inputs={"Scale": 1800.0})
    t.link(v, wx.inputs["Vector"]); t.link(v, wy.inputs["Vector"])
    weave = math_(t, "MULTIPLY", wx.outputs["Fac"], wy.outputs["Fac"])
    var = noise(t, v, 30.0, 3.0)
    col = mix(t, 0.12, color, ramp(t, var.outputs["Fac"], [(0.3, (0.75, 0.75, 0.75)), (0.7, (1.15, 1.15, 1.15))]),
              "MULTIPLY")
    n = bump(t, weave, 0.25, 0.00004)
    principled(t, col, 0.72, n, Sheen_Weight=0.35)
    return m


def pages(name="Pages"):
    m, t = new_mat(name)
    v = coords(t)
    w = t.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="Y", inputs={"Scale": 2400.0})
    t.link(v, w.inputs["Vector"])
    n = bump(t, w.outputs["Fac"], 0.2, 0.00003)
    principled(t, (0.78, 0.73, 0.62), 0.8, n)
    return m


def glass(name="Glass"):
    m, t = new_mat(name)
    principled(t, (1, 1, 1), 0.0, None, Transmission_Weight=1.0, IOR=1.52)
    return m


def whiskey(name="Whiskey"):
    m, t = new_mat(name)
    p = principled(t, (1.0, 0.55, 0.18), 0.0, None, Transmission_Weight=1.0, IOR=1.36)
    vol = t.node("ShaderNodeVolumeAbsorption", inputs={"Color": (0.85, 0.42, 0.10, 1.0), "Density": 45.0})
    out = [n for n in t.nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial"][0]
    t.link(vol.outputs[0], out.inputs["Volume"])
    return m


def ice(name="Ice"):
    m, t = new_mat(name)
    v = coords(t)
    n = bump(t, noise(t, v, 90.0, 6.0).outputs["Fac"], 0.3, 0.0004)
    principled(t, (1, 1, 1), 0.08, n, Transmission_Weight=1.0, IOR=1.31)
    return m


def to_image(texture):
    if texture.name in bpy.data.images:
        return bpy.data.images[texture.name]
    w, h = texture.w, texture.h
    img = bpy.data.images.new(texture.name, w, h)
    d = texture.data
    px = [0.0] * (w * h * 4)
    for y in range(h):
        src = (h - 1 - y) * w * 3          # Blender stores rows bottom-up
        dst = y * w * 4
        for x in range(w):
            o = src + x * 3
            q = dst + x * 4
            px[q] = d[o] / 255.0; px[q + 1] = d[o + 1] / 255.0; px[q + 2] = d[o + 2] / 255.0
            px[q + 3] = 1.0
    img.pixels = px
    img.pack()
    return img


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def mesh_object(mesh, name, mats, parent=None, matrix=None):
    """stonekit Mesh (mm) -> Blender object (m) with custom normals and UVs."""
    verts, faces, nrm, uvv, mat_idx, slots = [], [], [], [], [], []
    for mname, prim in mesh.prims.items():
        if not prim.idx:
            continue
        off = len(verts)
        verts.extend((x * MM, y * MM, z * MM) for x, y, z in prim.pos)
        nrm.extend(prim.nrm)
        uvv.extend((u, 1.0 - v) for u, v in prim.uv)
        slots.append(mname)
        si = len(slots) - 1
        I = prim.idx
        faces.extend((I[k] + off, I[k + 1] + off, I[k + 2] + off) for k in range(0, len(I), 3))
        mat_idx.extend([si] * (len(I) // 3))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    uvl = me.uv_layers.new(name="UVMap")
    li = [0] * len(me.loops)
    me.loops.foreach_get("vertex_index", li)
    uvl.data.foreach_set("uv", [c for i in li for c in uvv[i]])
    me.polygons.foreach_set("material_index", mat_idx)
    me.polygons.foreach_set("use_smooth", [True] * len(faces))
    me.normals_split_custom_set_from_vertices(nrm)
    for mname in slots:
        me.materials.append(mats[mname])
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if parent:
        ob.parent = parent
    if matrix is not None:
        ob.matrix_basis = matrix
    return ob


def node_matrix(nd, offset=(0.0, 0.0, 0.0)):
    R = Matrix(rot_matrix(nd.rot)).to_4x4()
    t = Vector(nd.t) * MM + Vector(offset)
    return Matrix.Translation(t) @ R


def add_nodes(nodes, mats, parent=None):
    """Recreate a stonekit Node tree as Blender objects/empties."""
    out = {}
    for nd in nodes:
        if nd.mesh is None:
            ob = bpy.data.objects.new(nd.name, None)
            ob.empty_display_size = 0.05
            bpy.context.scene.collection.objects.link(ob)
            if parent:
                ob.parent = parent
            ob.matrix_basis = node_matrix(nd)
        else:
            ob = mesh_object(nd.mesh, nd.name, mats, parent, node_matrix(nd))
        out[nd.name] = ob
        out.update(add_nodes(nd.children, mats, ob))
    return out


def cyclorama(material, width=4.0, depth=3.0, height=2.0, radius=0.6, y_wall=1.0):
    """Seamless studio sweep: floor curving up into a back wall."""
    prof = []
    for k in range(12):
        prof.append((-depth + y_wall + (depth - radius) * k / 11, 0.0))
    for k in range(1, 17):
        a = math.pi / 2 * k / 16
        prof.append((y_wall - radius + radius * math.sin(a), radius - radius * math.cos(a)))
    for k in range(1, 9):
        prof.append((y_wall, radius + (height - radius) * k / 8))
    nx = 24
    verts, faces = [], []
    for j, (y, z) in enumerate(prof):
        for i in range(nx + 1):
            verts.append((-width / 2 + width * i / nx, y, z))
    W = nx + 1
    for j in range(len(prof) - 1):
        for i in range(nx):
            a = j * W + i
            faces.append((a, a + 1, a + W + 1, a + W))
    me = bpy.data.meshes.new("Backdrop")
    me.from_pydata(verts, [], faces)
    me.polygons.foreach_set("use_smooth", [True] * len(faces))
    me.materials.append(material)
    ob = bpy.data.objects.new("Backdrop", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def simple_object(mesh, name, mat_map, location=(0, 0, 0), rot_z=0.0):
    ob = mesh_object(mesh, name, mat_map)
    ob.matrix_basis = Matrix.Translation(Vector(location)) @ Matrix.Rotation(math.radians(rot_z), 4, "Z")
    return ob


def area_light(name, location, target, size, energy, color=(1.0, 0.97, 0.92), size_y=None):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.color = color
    if size_y:
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = size, size_y
    else:
        ld.size = size
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = location
    aim(ob, target)
    return ob


def aim(ob, target):
    d = Vector(target) - Vector(ob.location)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def camera(name, location, target, lens=70.0, fstop=None, focus=None):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_width = 36.0
    ob = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = location
    aim(ob, target)
    if fstop:
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = fstop
        f = Vector(focus or target)
        cd.dof.focus_distance = (f - Vector(location)).length
    return ob


def render_to(cam, path_png, res, samples=None):
    s = bpy.context.scene
    s.camera = cam
    s.render.resolution_x, s.render.resolution_y = res
    s.render.resolution_percentage = 100
    if samples:
        s.cycles.samples = samples
    s.render.filepath = path_png
    s.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    # a JPEG alongside for easy sharing
    img = bpy.data.images["Render Result"]
    s.render.image_settings.file_format = "JPEG"
    s.render.image_settings.quality = 92
    img.save_render(path_png[:-4] + ".jpg", scene=s)
    s.render.image_settings.file_format = "PNG"
