"""glTF 2.0 binary (.glb) writer.

Input is Z-up millimetres; output is glTF's Y-up metres, which Blender's
built-in importer turns back into Z-up at true scale.
"""
import json
import math
import struct

from .mesh import normalize, rot_quat

MM = 0.001


def _to_gltf(v):
    return (v[0], v[2], -v[1])


class Material:
    def __init__(self, name, color=(1, 1, 1, 1), roughness=0.8, texture=None,
                 double_sided=False, metallic=0.0):
        self.name, self.color, self.roughness = name, color, roughness
        self.texture, self.double_sided, self.metallic = texture, double_sided, metallic


class Node:
    def __init__(self, name, mesh=None, t=(0.0, 0.0, 0.0), rot=None, children=()):
        """rot is (axis, degrees), or a list of them applied in order, in the Z-up frame."""
        self.name, self.mesh, self.t, self.rot = name, mesh, t, rot
        self.children = list(children)


def write_glb(path, nodes, materials):
    bin_ = bytearray()
    views, accessors = [], []
    gl_meshes, mesh_index, prim_cache = [], {}, {}
    mats = list(materials.values())
    mat_index = {m.name: i for i, m in enumerate(mats)}

    def view(data, target=None):
        while len(bin_) % 4:
            bin_.append(0)
        v = {"buffer": 0, "byteOffset": len(bin_), "byteLength": len(data)}
        if target:
            v["target"] = target
        bin_.extend(data)
        views.append(v)
        return len(views) - 1

    def accessor(data, ctype, count, typ, target, mn=None, mx=None):
        a = {"bufferView": view(data, target), "componentType": ctype,
             "count": count, "type": typ}
        if mn is not None:
            a["min"], a["max"] = mn, mx
        accessors.append(a)
        return len(accessors) - 1

    def prim_accessors(p):
        key = id(p)
        if key in prim_cache:
            return prim_cache[key]
        pos = [_to_gltf(v) for v in p.pos]
        pos = [(x * MM, y * MM, z * MM) for x, y, z in pos]
        nrm = [normalize(_to_gltf(n)) for n in p.nrm]
        flat = [c for v in pos for c in v]
        mn = [min(v[k] for v in pos) for k in range(3)]
        mx = [max(v[k] for v in pos) for k in range(3)]
        n = len(pos)
        res = {
            "POSITION": accessor(struct.pack("<%df" % (3 * n), *flat), 5126, n, "VEC3", 34962, mn, mx),
            "NORMAL": accessor(struct.pack("<%df" % (3 * n), *[c for v in nrm for c in v]),
                               5126, n, "VEC3", 34962),
            "TEXCOORD_0": accessor(struct.pack("<%df" % (2 * n), *[c for v in p.uv for c in v]),
                                   5126, n, "VEC2", 34962),
        }
        ind = accessor(struct.pack("<%dI" % len(p.idx), *p.idx), 5125, len(p.idx), "SCALAR", 34963)
        prim_cache[key] = (res, ind)
        return res, ind

    def mesh_id(mesh):
        if id(mesh) in mesh_index:
            return mesh_index[id(mesh)]
        prims = []
        for mat, p in mesh.prims.items():
            if not p.idx:
                continue
            attrs, ind = prim_accessors(p)
            prims.append({"attributes": attrs, "indices": ind, "material": mat_index[mat], "mode": 4})
        gl_meshes.append({"name": mesh.name, "primitives": prims})
        mesh_index[id(mesh)] = len(gl_meshes) - 1
        return mesh_index[id(mesh)]

    # textures
    images, textures, tex_index = [], [], {}
    for m in mats:
        if m.texture is not None and m.texture.name not in tex_index:
            bv = view(m.texture.png())
            images.append({"name": m.texture.name, "bufferView": bv, "mimeType": "image/png"})
            textures.append({"sampler": 0, "source": len(images) - 1})
            tex_index[m.texture.name] = len(textures) - 1
    gl_mats = []
    for m in mats:
        pbr = {"baseColorFactor": list(m.color), "metallicFactor": m.metallic,
               "roughnessFactor": m.roughness}
        if m.texture is not None:
            pbr["baseColorTexture"] = {"index": tex_index[m.texture.name]}
        gm = {"name": m.name, "pbrMetallicRoughness": pbr}
        if m.double_sided:
            gm["doubleSided"] = True
        gl_mats.append(gm)

    gl_nodes = []

    def add_node(nd):
        g = {"name": nd.name}
        if nd.mesh is not None:
            g["mesh"] = mesh_id(nd.mesh)
        if any(nd.t):
            g["translation"] = [c * MM for c in _to_gltf(nd.t)]
        if nd.rot:
            g["rotation"] = list(rot_quat(nd.rot, _to_gltf))
        gl_nodes.append(g)
        me = len(gl_nodes) - 1
        if nd.children:
            g["children"] = [add_node(c) for c in nd.children]
        return me

    roots = [add_node(n) for n in nodes]

    while len(bin_) % 4:
        bin_.append(0)
    gltf = {
        "asset": {"version": "2.0", "generator": "petermillarpers-blender stonekit"},
        "scene": 0,
        "scenes": [{"name": "Scene", "nodes": roots}],
        "nodes": gl_nodes,
        "meshes": gl_meshes,
        "materials": gl_mats,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(bin_)}],
    }
    if textures:
        gltf["images"] = images
        gltf["textures"] = textures
        gltf["samplers"] = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    total = 12 + 8 + len(js) + 8 + len(bin_)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(bin_), 0x004E4942) + bytes(bin_))
    return total
