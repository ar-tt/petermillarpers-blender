#!/usr/bin/env python3
"""Read .glb files back and sanity-check them (structure, bounds, sizes).

    python3 tools/check_glb.py models/*.glb
"""
import json
import math
import struct
import sys

SIZES = {5126: 4, 5125: 4, 5123: 2, 5121: 1}
COMPS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def check(path):
    data = open(path, "rb").read()
    magic, ver, total = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67 and ver == 2 and total == len(data), "bad GLB header"
    jlen, jtype = struct.unpack_from("<II", data, 12)
    assert jtype == 0x4E4F534A
    g = json.loads(data[20:20 + jlen])
    blen, btype = struct.unpack_from("<II", data, 20 + jlen)
    assert btype == 0x004E4942
    binbuf = data[28 + jlen:28 + jlen + blen]
    assert g["buffers"][0]["byteLength"] <= blen

    def read(ai):
        a = g["accessors"][ai]
        bv = g["bufferViews"][a["bufferView"]]
        n = a["count"] * COMPS[a["type"]]
        size = n * SIZES[a["componentType"]]
        assert size <= bv["byteLength"], "accessor overruns its view"
        assert bv["byteOffset"] + bv["byteLength"] <= blen, "view overruns buffer"
        fmt = {5126: "f", 5125: "I", 5123: "H", 5121: "B"}[a["componentType"]]
        vals = struct.unpack_from("<%d%s" % (n, fmt), binbuf, bv["byteOffset"])
        k = COMPS[a["type"]]
        return [vals[i:i + k] for i in range(0, n, k)] if k > 1 else list(vals)

    for img in g.get("images", []):
        bv = g["bufferViews"][img["bufferView"]]
        assert binbuf[bv["byteOffset"]:bv["byteOffset"] + 8] == b"\x89PNG\r\n\x1a\n", "bad PNG"

    mesh_info = {}
    for mi, m in enumerate(g["meshes"]):
        lo, hi, tris = [math.inf] * 3, [-math.inf] * 3, 0
        for p in m["primitives"]:
            pos = read(p["attributes"]["POSITION"])
            nrm = read(p["attributes"]["NORMAL"])
            uv = read(p["attributes"]["TEXCOORD_0"])
            idx = read(p["indices"])
            assert len(pos) == len(nrm) == len(uv)
            assert len(idx) % 3 == 0 and max(idx) < len(pos), "index out of range"
            for v in pos:
                assert all(math.isfinite(c) for c in v), "NaN position"
            bad = sum(1 for n in nrm if abs(math.sqrt(sum(c * c for c in n)) - 1) > 1e-3)
            assert bad == 0, f"{bad} non-unit normals"
            acc = g["accessors"][p["attributes"]["POSITION"]]
            for k in range(3):
                lo[k] = min(lo[k], acc["min"][k]); hi[k] = max(hi[k], acc["max"][k])
                assert abs(acc["min"][k] - min(v[k] for v in pos)) < 1e-6
            assert 0 <= p["material"] < len(g["materials"])
            tris += len(idx) // 3
        mesh_info[mi] = (lo, hi, tris)

    print(f"{path}: OK  ({len(data) / 1e6:.1f} MB, {len(g['meshes'])} meshes, "
          f"{len(g['materials'])} materials, {len(g.get('images', []))} textures)")

    def walk(ni, depth):
        n = g["nodes"][ni]
        line = "    " + "  " * depth + n["name"]
        if "mesh" in n:
            lo, hi, tris = mesh_info[n["mesh"]]
            # glTF is Y-up metres; report Blender-style X x Y x Z in mm
            dx, dy, dz = (hi[0] - lo[0]) * 1000, (hi[2] - lo[2]) * 1000, (hi[1] - lo[1]) * 1000
            line += f"  {dx:.1f} x {dy:.1f} x {dz:.1f} mm, {tris:,} tris"
        print(line)
        for c in n.get("children", []):
            walk(c, depth + 1)
    for ni in g["scenes"][0]["nodes"]:
        walk(ni, 0)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        check(p)
