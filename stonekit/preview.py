"""Tiny z-buffer renderer for preview PNGs (no Blender needed).

Flat-shaded, textured, no shadows. It's for checking geometry and getting a
quick look; final renders belong in Blender.
"""
import math

from .mesh import (IDENTITY, add, cross, dot, mat_mul, mat_vec, normalize,
                   rot_matrix, sub)
from .textures import Texture


def _walk(nodes, R=IDENTITY, t=(0.0, 0.0, 0.0)):
    for nd in nodes:
        Rl = rot_matrix(nd.rot)
        Rw = mat_mul(R, Rl)
        tw = add(mat_vec(R, nd.t), t)
        if nd.mesh is not None:
            yield nd.mesh, Rw, tw
        yield from _walk(nd.children, Rw, tw)


def render(path, nodes, materials, cam, target, fov=30.0, size=(960, 640), ss=2,
           light=(-0.45, -0.6, 0.75), ground=0.0):
    W, H = size[0] * ss, size[1] * ss
    fwd = normalize(sub(target, cam))
    right = normalize(cross(fwd, (0.0, 0.0, 1.0)))
    up = cross(right, fwd)
    f = (H / 2) / math.tan(math.radians(fov) / 2)
    L = normalize(light)
    fill = normalize((0.7, 0.3, 0.35))
    zbuf = [float("inf")] * (W * H)
    img = bytearray(W * H * 3)
    # backdrop: soft vertical gradient
    for y in range(H):
        g = 236 - int(30 * y / H)
        row = bytes((g, g, g - 2)) * W
        img[y * W * 3:(y + 1) * W * 3] = row

    def project(p):
        d = sub(p, cam)
        z = dot(d, fwd)
        return (W / 2 + f * dot(d, right) / z, H / 2 - f * dot(d, up) / z, z)

    # ground plane as two big triangles, plain grey
    tris = []
    gs = 20000.0
    gp = [(target[0] - gs, target[1] - gs, ground), (target[0] + gs, target[1] - gs, ground),
          (target[0] + gs, target[1] + gs, ground), (target[0] - gs, target[1] + gs, ground)]

    def raster(P, UV, shade, tex, col):
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = P
        if min(z0, z1, z2) < 1.0:
            return
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            return
        minx = max(0, int(min(x0, x1, x2))); maxx = min(W - 1, int(max(x0, x1, x2)) + 1)
        miny = max(0, int(min(y0, y1, y2))); maxy = min(H - 1, int(max(y0, y1, y2)) + 1)
        if minx > maxx or miny > maxy:
            return
        iz0, iz1, iz2 = 1 / z0, 1 / z1, 1 / z2
        inv = 1.0 / area
        for py in range(miny, maxy + 1):
            cy = py + 0.5
            for px in range(minx, maxx + 1):
                cx = px + 0.5
                w0 = ((x1 - cx) * (y2 - cy) - (x2 - cx) * (y1 - cy)) * inv
                w1 = ((x2 - cx) * (y0 - cy) - (x0 - cx) * (y2 - cy)) * inv
                w2 = 1 - w0 - w1
                if w0 < 0 or w1 < 0 or w2 < 0:
                    continue
                iz = w0 * iz0 + w1 * iz1 + w2 * iz2
                z = 1 / iz
                k = py * W + px
                if z >= zbuf[k]:
                    continue
                zbuf[k] = z
                if tex is not None:
                    u = (w0 * UV[0][0] * iz0 + w1 * UV[1][0] * iz1 + w2 * UV[2][0] * iz2) * z
                    v = (w0 * UV[0][1] * iz0 + w1 * UV[1][1] * iz1 + w2 * UV[2][1] * iz2) * z
                    r, g, b = tex.sample(u, v)
                else:
                    r, g, b = 1.0, 1.0, 1.0
                o = k * 3
                img[o] = min(255, int(255 * r * col[0] * shade))
                img[o + 1] = min(255, int(255 * g * col[1] * shade))
                img[o + 2] = min(255, int(255 * b * col[2] * shade))

    gpp = [project(p) for p in gp]
    for tri in ((0, 1, 2), (0, 2, 3)):
        raster([gpp[i] for i in tri], None, 1.0, None, (0.86, 0.85, 0.83))

    for mesh, R, t in _walk(nodes):
        for mname, prim in mesh.prims.items():
            m = materials[mname]
            col = tuple(c ** (1 / 2.2) for c in m.color[:3])   # factor is linear
            tex = m.texture
            P = [add(mat_vec(R, p), t) for p in prim.pos]
            S = [project(p) for p in P]
            I = prim.idx
            for k in range(0, len(I), 3):
                a, b, c = I[k], I[k + 1], I[k + 2]
                n = cross(sub(P[b], P[a]), sub(P[c], P[a]))
                if dot(n, sub(P[a], cam)) > 0:
                    if not m.double_sided:
                        continue
                    n = (-n[0], -n[1], -n[2])
                n = normalize(n)
                shade = 0.38 + 0.62 * max(0.0, dot(n, L)) + 0.18 * max(0.0, dot(n, fill))
                raster((S[a], S[b], S[c]), (prim.uv[a], prim.uv[b], prim.uv[c]), shade, tex, col)

    out = Texture("preview", size[0], size[1])
    for y in range(size[1]):
        for x in range(size[0]):
            r = g = b = 0
            for sy in range(ss):
                o = ((y * ss + sy) * W + x * ss) * 3
                for sx in range(ss):
                    r += img[o]; g += img[o + 1]; b += img[o + 2]
                    o += 3
            n = ss * ss
            out.set(x, y, (r / n, g / n, b / n))
    with open(path, "wb") as fh:
        fh.write(out.png())
