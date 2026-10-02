"""Shape builders. All sizes in millimetres, Z up, objects sit on z = 0."""
import math
import random

from .mesh import Mesh, Prim, flat_poly, newell_normal, normalize, cross, sub, dot, add, scale
from .noise import Perlin, smoothstep

# --------------------------------------------------------------------------
# Rounded (eased-edge) box
# --------------------------------------------------------------------------


def _band_coords(a, r, seg, flat_div, extra=()):
    inner = a - r
    out = []
    for k in range(seg):
        phi = (math.pi / 4) * (seg - k) / seg
        out.append(-inner - r * math.tan(phi))
    out += [-inner + 2 * inner * i / flat_div for i in range(flat_div + 1)]
    for k in range(seg - 1, -1, -1):
        phi = (math.pi / 4) * (seg - k) / seg
        out.append(inner + r * math.tan(phi))
    out = sorted(set(round(v, 9) for v in list(out) + list(extra)))
    return out


def rounded_box(size, r, material, seg=4, flat_div=2, uv_scale=1 / 180.0,
                uv_off=(0.0, 0.0), z0=0.0, hole=None):
    """Box with radius-r eased edges, base at z0, centred in x/y.

    hole=(x0, y0, x1, y1) leaves a rectangle open in the flat part of the top
    face so an engraved panel can be dropped in.
    """
    a = [s / 2 for s in size]
    lim = [ai - r for ai in a]
    mesh = Mesh("rounded_box")
    prim = mesh.prim(material)
    for k in range(3):
        for s in (1, -1):
            i, j = (k + 1) % 3, (k + 2) % 3
            ex_i = ex_j = ()
            top_hole = hole if (hole and k == 2 and s == 1) else None
            if top_hole:
                ex_i, ex_j = (top_hole[0], top_hole[2]), (top_hole[1], top_hole[3])
            us = _band_coords(a[i], r, seg, flat_div, ex_i)
            vs = _band_coords(a[j], r, seg, flat_div, ex_j)
            face = Prim()
            for v in vs:
                for u in us:
                    q = [0.0, 0.0, 0.0]
                    q[k], q[i], q[j] = s * a[k], u, v
                    inner = [max(-lim[m], min(lim[m], q[m])) for m in range(3)]
                    n = normalize(sub(q, inner))
                    p = [inner[m] + r * n[m] for m in range(3)]
                    p[2] += a[2] + z0
                    face.vert(tuple(p), n, (p[i] * uv_scale + uv_off[0],
                                            p[j] * uv_scale + uv_off[1]))
            nu = len(us)
            for jv in range(len(vs) - 1):
                for iu in range(nu - 1):
                    if top_hole:
                        cu = (us[iu] + us[iu + 1]) / 2
                        cv = (vs[jv] + vs[jv + 1]) / 2
                        if top_hole[0] < cu < top_hole[2] and top_hole[1] < cv < top_hole[3]:
                            continue
                    A = jv * nu + iu
                    B, C, D = A + 1, A + nu + 1, A + nu
                    if s > 0:
                        face.tri(A, B, C); face.tri(A, C, D)
                    else:
                        face.tri(A, C, B); face.tri(A, D, C)
            prim.extend(face)
    return mesh


# --------------------------------------------------------------------------
# Rough-split block (planters, bookends)
# --------------------------------------------------------------------------

FACES = {"+x": (0, 1), "-x": (0, -1), "+y": (1, 1), "-y": (1, -1), "+z": (2, 1), "-z": (2, -1)}


def _rough_field(k, per, amp, lo, hi):
    i, j = (k + 1) % 3, (k + 2) % 3
    ci, cj = (lo[i] + hi[i]) / 2, (lo[j] + hi[j]) / 2
    hi_, hj_ = (hi[i] - lo[i]) / 2, (hi[j] - lo[j]) / 2

    def fn(p):
        u = (p[i] - ci) / hi_
        v = (p[j] - cj) / hj_
        bulge = (1 - u ** 4) * (1 - v ** 4)       # pitched face: proud in the middle
        x, y, z = p
        # broad conchoidal breaks, a few sharper ridges, a little grain
        broad = per.fbm(x / 75.0, y / 75.0, z / 75.0, 4, gain=0.55)
        ridge = 1 - abs(per.noise(x / 36.0 + 5.3, y / 36.0 + 1.7, z / 36.0 + 9.1))
        grain = per.fbm(x / 7.0, y / 7.0, z / 7.0 + 40.0, 2)
        # arrises break back rather than jutting out where two split faces meet
        chip = smoothstep(0.82, 1.0, max(abs(u), abs(v)))
        return amp * (0.15 + 0.35 * bulge + 1.0 * broad + 0.3 * (ridge ** 2 - 0.4)
                      + 0.05 * grain - 0.55 * chip)
    return fn


def _axis_coords(lo, hi, step, extra=()):
    n = max(1, math.ceil((hi - lo) / step))
    base = [lo + (hi - lo) * t / n for t in range(n + 1)]
    # drop grid lines that would leave slivers next to the extra values
    keep = [v for k, v in enumerate(base)
            if k in (0, n) or all(abs(v - e) > step * 0.3 for e in extra)]
    return sorted(set(round(v, 6) for v in keep + list(extra)))


def split_block(size, kinds, step, amp, seed, mat_split, mat_sawn, cavity=None,
                uv_scale=1 / 200.0, name="split_block"):
    """Box whose faces are 'rough' (split) or 'sawn' (flat).

    Rough faces are displaced along their own normal. Where a rough face meets
    a neighbour, the neighbour's border moves sideways (inside its own plane)
    by the same amount, so sawn faces stay perfectly flat while their outline
    follows the broken edge.

    cavity=(cx, cy, depth): open-topped pocket centred in the top face.
    """
    sx, sy, sz = size
    lo = (-sx / 2, -sy / 2, 0.0)
    hi = (sx / 2, sy / 2, sz)
    per = Perlin(seed)
    rnd = random.Random(seed)
    falloff = max(amp * 4.0, 8.0)
    fields = []
    for key, (k, s) in FACES.items():
        if kinds.get(key, "sawn") == "rough":
            plane = hi[k] if s > 0 else lo[k]
            fields.append((key, k, s, plane, _rough_field(k, per, amp, lo, hi)))

    def displaced(p, face_key):
        x = list(p)
        for key, k, s, plane, fn in fields:
            if key == face_key:
                w = 1.0
            else:
                dist = abs(p[k] - plane)
                if dist >= falloff:
                    continue
                w = 1.0 - smoothstep(0.0, falloff, dist)
            x[k] += s * fn(p) * w
        return tuple(x)

    mesh = Mesh(name)
    for key, (k, s) in FACES.items():
        i, j = (k + 1) % 3, (k + 2) % 3
        ex_i = ex_j = ()
        cav = cavity if (cavity and key == "+z") else None
        if cav:
            ex = {0: (-cav[0] / 2, cav[0] / 2), 1: (-cav[1] / 2, cav[1] / 2)}
            ex_i, ex_j = ex[i], ex[j]
        us = _axis_coords(lo[i], hi[i], step, ex_i)
        vs = _axis_coords(lo[j], hi[j], step, ex_j)
        face = Prim()
        off = (rnd.random(), rnd.random())
        for v in vs:
            for u in us:
                q = [0.0, 0.0, 0.0]
                q[k] = hi[k] if s > 0 else lo[k]
                q[i], q[j] = u, v
                q = tuple(q)
                face.vert(displaced(q, key), (0.0, 0.0, 1.0),
                          (q[i] * uv_scale + off[0], q[j] * uv_scale + off[1]))
        nu = len(us)
        for jv in range(len(vs) - 1):
            for iu in range(nu - 1):
                if cav:
                    cu = (us[iu] + us[iu + 1]) / 2
                    cv = (vs[jv] + vs[jv + 1]) / 2
                    ci = cav[i] if i < 2 else 0
                    cj = cav[j] if j < 2 else 0
                    if abs(cu) < ci / 2 and abs(cv) < cj / 2:
                        continue
                A = jv * nu + iu
                B, C, D = A + 1, A + nu + 1, A + nu
                # alternate the diagonal so the facets don't all lean one way
                if (iu + jv) % 2 == 0:
                    t1, t2 = (A, B, C), (A, C, D)
                else:
                    t1, t2 = (A, B, D), (B, C, D)
                if s < 0:
                    t1, t2 = t1[::-1], t2[::-1]
                face.tri(*t1); face.tri(*t2)
        face.smooth_normals()
        mesh.prim(mat_split if kinds.get(key, "sawn") == "rough" else mat_sawn).extend(face)

    if cavity:
        cx, cy, depth = cavity
        top, bot = sz, sz - depth
        xs_all = _axis_coords(lo[0], hi[0], step, (-cx / 2, cx / 2))
        ys_all = _axis_coords(lo[1], hi[1], step, (-cy / 2, cy / 2))
        xs = [x for x in xs_all if -cx / 2 - 1e-6 <= x <= cx / 2 + 1e-6]
        ys = [y for y in ys_all if -cy / 2 - 1e-6 <= y <= cy / 2 + 1e-6]
        walls = [
            ([(x, -cy / 2) for x in xs], (0.0, 1.0, 0.0)),
            ([(x, cy / 2) for x in xs], (0.0, -1.0, 0.0)),
            ([(-cx / 2, y) for y in ys], (1.0, 0.0, 0.0)),
            ([(cx / 2, y) for y in ys], (-1.0, 0.0, 0.0)),
        ]
        prim = mesh.prim(mat_sawn)
        uvf = lambda p: (p[0] * uv_scale + p[1] * uv_scale * 0.7, p[2] * uv_scale)
        for line, n in walls:
            for a_, b_ in zip(line[:-1], line[1:]):
                pa = displaced((a_[0], a_[1], top), "+z")
                pb = displaced((b_[0], b_[1], top), "+z")
                flat_poly(prim, [pa, pb, (b_[0], b_[1], bot), (a_[0], a_[1], bot)], n, uvf)
        flat_poly(prim, [(-cx / 2, -cy / 2, bot), (cx / 2, -cy / 2, bot),
                         (cx / 2, cy / 2, bot), (-cx / 2, cy / 2, bot)], (0.0, 0.0, 1.0),
                  lambda p: (p[0] * uv_scale, p[1] * uv_scale))
    return mesh


# --------------------------------------------------------------------------
# Engraved / stamped panel
# --------------------------------------------------------------------------

_CORNERS = ((0, 0), (1, 0), (1, 1), (0, 1))


def engraved_panel(mask, x0, y0, nx, ny, cell, depth, mat_top, mat_cut, uvf):
    """Flat panel at z = 0 with the masked area cut down to z = -depth.

    Uses marching squares on the mask so letter edges follow 45-degree cuts
    instead of pixel steps, and merges plain runs into long quads.
    """
    mesh = Mesh("panel")
    top, cut = mesh.prim(mat_top), mesh.prim(mat_cut)
    up = (0.0, 0.0, 1.0)
    zf = -depth

    def run(i0, i1, j, val):
        xa, xb = x0 + i0 * cell, x0 + i1 * cell
        ya, yb = y0 + j * cell, y0 + (j + 1) * cell
        z = zf if val else 0.0
        flat_poly(cut if val else top, [(xa, ya, z), (xb, ya, z), (xb, yb, z), (xa, yb, z)], up, uvf)

    for j in range(ny):
        r0, r1 = mask[j], mask[j + 1]
        if not any(r0) and not any(r1):
            run(0, nx, j, 0)
            continue
        rs, rv = 0, None
        for i in range(nx):
            c = (r0[i], r0[i + 1], r1[i + 1], r1[i])
            code = c[0] | c[1] << 1 | c[2] << 2 | c[3] << 3
            if code == 0 or code == 15:
                val = 1 if code == 15 else 0
                if rv is not None and rv != val:
                    run(rs, i, j, rv)
                    rv = None
                if rv is None:
                    rs, rv = i, val
                continue
            if rv is not None:
                run(rs, i, j, rv)
                rv = None
            # mixed cell
            bx, by = x0 + i * cell, y0 + j * cell
            seq = []
            for k in range(4):
                cx_, cy_ = _CORNERS[k]
                seq.append(("c", (bx + cx_ * cell, by + cy_ * cell), c[k]))
                if c[k] != c[(k + 1) % 4]:
                    nx_, ny_ = _CORNERS[(k + 1) % 4]
                    seq.append(("e", (bx + (cx_ + nx_) * cell / 2, by + (cy_ + ny_) * cell / 2), None))
            cross_idx = [m for m, s_ in enumerate(seq) if s_[0] == "e"]
            outside = [s_[1] for s_ in seq if s_[0] == "e" or s_[2] == 0]
            flat_poly(top, [(x, y, 0.0) for x, y in outside], up, uvf)
            nc = len(cross_idx)
            for m in range(nc):
                a, b = cross_idx[m], cross_idx[(m + 1) % nc]
                pts, t = [], (a + 1) % len(seq)
                while t != b:
                    pts.append(seq[t])
                    t = (t + 1) % len(seq)
                if not pts or pts[0][2] != 1:
                    continue
                pa, pb = seq[a][1], seq[b][1]
                poly = [pa] + [s_[1] for s_ in pts] + [pb]
                flat_poly(cut, [(x, y, zf) for x, y in poly], up, uvf)
                # wall along the contour, facing into the cut
                cxm = sum(p[0] for p in poly) / len(poly)
                cym = sum(p[1] for p in poly) / len(poly)
                dx, dy = pb[0] - pa[0], pb[1] - pa[1]
                n = normalize((-dy, dx, 0.0))
                if n[0] * (cxm - pa[0]) + n[1] * (cym - pa[1]) < 0:
                    n = (-n[0], -n[1], 0.0)
                flat_poly(cut, [(pa[0], pa[1], 0.0), (pb[0], pb[1], 0.0),
                                (pb[0], pb[1], zf), (pa[0], pa[1], zf)], n, uvf)
        if rv is not None:
            run(rs, nx, j, rv)
    return mesh


# --------------------------------------------------------------------------
# Soil and snake plant
# --------------------------------------------------------------------------


def soil_patch(w, d, step, amp, seed, material, uv_scale=1 / 120.0):
    """Lumpy soil surface centred on the origin at z ~ 0."""
    per = Perlin(seed + 101)
    mesh = Mesh("soil")
    prim = mesh.prim(material)
    nu, nv = max(2, math.ceil(w / step)), max(2, math.ceil(d / step))
    for jv in range(nv + 1):
        for iu in range(nu + 1):
            x = -w / 2 + w * iu / nu
            y = -d / 2 + d * jv / nv
            z = amp * (per.fbm(x / 30.0, y / 30.0, 0.5, 3) + 0.35 * per.noise(x / 4.0, y / 4.0, 3.3))
            prim.vert((x, y, z), (0.0, 0.0, 1.0), (x * uv_scale, y * uv_scale))
    for jv in range(nv):
        for iu in range(nu):
            A = jv * (nu + 1) + iu
            B, C, D = A + 1, A + nu + 2, A + nu + 1
            prim.tri(A, B, C); prim.tri(A, C, D)
    prim.smooth_normals()
    return mesh


def snake_leaf(prim, base, height, width, facing_deg, lean, twist_deg, curl, thickness,
               rnd, n_len=30, n_wid=8):
    """One Sansevieria leaf: sword-shaped, channelled, slightly twisted, with thickness.

    UVs run u across the leaf (0..1, margins at the ends) and v from base (0)
    to tip (1) so the leaf texture can paint the bands and yellow margins.
    """
    phi = math.radians(facing_deg)
    radial = (math.cos(phi), math.sin(phi), 0.0)
    tangent = (-math.sin(phi), math.cos(phi), 0.0)
    wobble = rnd.uniform(0, 6.28)
    rows = []
    for a in range(n_len + 1):
        t = a / n_len
        # sword profile: narrow base, widest around 40%, long taper to a point
        w = width * (0.42 + 0.58 * math.sin(min(t / 0.4, 1.0) * math.pi / 2))
        w *= (1 - smoothstep(0.5, 1.0, t)) ** 0.75
        w *= 1 + 0.04 * math.sin(t * 9 + wobble)
        bend = lean * height * t ** 1.8
        c = (base[0] + radial[0] * bend, base[1] + radial[1] * bend, base[2] + height * t)
        tw = math.radians(twist_deg) * t
        side = add(scale(tangent, math.cos(tw)), scale(radial, math.sin(tw)))
        face_n = add(scale(radial, math.cos(tw)), scale(tangent, -math.sin(tw)))
        row = []
        for b in range(n_wid + 1):
            s = -1 + 2 * b / n_wid
            off = add(scale(side, s * w / 2), scale(face_n, -curl * w * s * s))
            row.append(add(c, off))
        rows.append((row, face_n, t))
    # front and back sheets
    th = thickness
    front, back = Prim(), Prim()
    for row, fn, t in rows:
        taper = th * (1 - 0.85 * t)
        for b, p in enumerate(row):
            u = b / n_wid
            edge = 1 - 0.6 * abs(2 * u - 1) ** 2
            front.vert(add(p, scale(fn, taper * edge / 2)), fn, (u, t))
            back.vert(add(p, scale(fn, -taper * edge / 2)), fn, (u, t))
    W = n_wid + 1
    for a in range(n_len):
        for b in range(n_wid):
            A = a * W + b
            B, C, D = A + 1, A + W + 1, A + W
            front.tri(A, B, C); front.tri(A, C, D)
            back.tri(A, C, B); back.tri(A, D, C)
    # make sure the front sheet faces along +face_n
    P = front.pos
    if dot(cross(sub(P[1], P[0]), sub(P[W], P[0])), rows[0][1]) < 0:
        for sheet in (front, back):
            sheet.idx = [v for k in range(0, len(sheet.idx), 3)
                         for v in (sheet.idx[k], sheet.idx[k + 2], sheet.idx[k + 1])]
    front.smooth_normals()
    back.smooth_normals()
    # thin strips closing the two margins, facing away from the midrib
    edges = Prim()
    for b, u in ((0, 0.01), (n_wid, 0.99)):
        for a in range(n_len):
            quad = [front.pos[a * W + b], front.pos[(a + 1) * W + b],
                    back.pos[(a + 1) * W + b], back.pos[a * W + b]]
            out = sub(quad[0], rows[a][0][n_wid // 2])
            n = newell_normal(quad)
            if dot(n, out) < 0:
                n = scale(n, -1)
            flat_poly(edges, quad, n, lambda p, v=a / n_len: (u, v))
    for part in (front, back, edges):
        prim.extend(part)


def snake_plant(seed, n_leaves, h_range, w_range, spread, material):
    """A pot's worth of snake plant: leaves in two or three clumps."""
    rnd = random.Random(seed)
    mesh = Mesh("snake_plant")
    prim = mesh.prim(material)
    n_clumps = 3 if n_leaves > 10 else 2
    clumps = []
    for c in range(n_clumps):
        ang = 2 * math.pi * c / n_clumps + rnd.uniform(-0.4, 0.4)
        r = spread * rnd.uniform(0.25, 0.55)
        clumps.append((r * math.cos(ang), r * math.sin(ang)))
    leaves = []
    for k in range(n_leaves):
        cx, cy = clumps[k % n_clumps]
        order = k // n_clumps
        ang = rnd.uniform(0, 360)
        jitter = spread * 0.12
        base = (cx + rnd.uniform(-jitter, jitter), cy + rnd.uniform(-jitter, jitter), -15.0)
        # inner leaves of a clump are taller and more upright
        tall = 1.0 - 0.35 * (order / max(1, n_leaves // n_clumps))
        h = rnd.uniform(*h_range) * tall
        w = rnd.uniform(*w_range)
        lean = rnd.uniform(0.04, 0.16) + 0.08 * (1 - tall)
        # face mostly away from the pot centre so the rosette opens outward
        out_ang = math.degrees(math.atan2(base[1], base[0])) if (base[0] or base[1]) else ang
        facing = out_ang + rnd.uniform(-70, 70)
        leaves.append((base, h + 15.0, w, facing, lean))
    for base, h, w, facing, lean in leaves:
        snake_leaf(prim, base, h, w, facing, lean,
                   twist_deg=rnd.uniform(-35, 35), curl=rnd.uniform(0.08, 0.18),
                   thickness=max(2.5, w * 0.08), rnd=rnd)
    return mesh
