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
                uv_scale=1 / 200.0, name="split_block", holes=None, face_mats=None):
    """Box whose faces are 'rough' (split) or 'sawn' (flat).

    Rough faces are displaced along their own normal. Where a rough face meets
    a neighbour, the neighbour's border moves sideways (inside its own plane)
    by the same amount, so sawn faces stay perfectly flat while their outline
    follows the broken edge.

    cavity=(cx, cy, depth): open-topped pocket centred in the top face.
    holes={face: (a0, b0, a1, b1)}: rectangles left open on flat faces (in that
    face's two in-plane axes, (k+1)%3 then (k+2)%3) for engraved panels. Keep
    them at least `edge_band` mm (returned on the mesh) away from split faces.
    face_mats={face: material} overrides the material per face.
    """
    holes = holes or {}
    face_mats = face_mats or {}
    sx, sy, sz = size
    lo = (-sx / 2, -sy / 2, 0.0)
    hi = (sx / 2, sy / 2, sz)
    per = Perlin(seed)
    rnd = random.Random(seed)
    falloff = max(amp * 3.0, 8.0)
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

    # grid lines added for openings are shared by every face along that axis,
    # so neighbouring faces meet vertex-for-vertex along their common edge
    extra = {0: set(), 1: set(), 2: set()}
    if cavity:
        extra[0].update((-cavity[0] / 2, cavity[0] / 2))
        extra[1].update((-cavity[1] / 2, cavity[1] / 2))
    for key, hole in holes.items():
        k = FACES[key][0]
        extra[(k + 1) % 3].update((hole[0], hole[2]))
        extra[(k + 2) % 3].update((hole[1], hole[3]))
    mesh = Mesh(name)
    mesh.face_uv = {}
    for key, (k, s) in FACES.items():
        i, j = (k + 1) % 3, (k + 2) % 3
        cav = cavity if (cavity and key == "+z") else None
        hole = holes.get(key)
        us = _axis_coords(lo[i], hi[i], step, tuple(sorted(extra[i])))
        vs = _axis_coords(lo[j], hi[j], step, tuple(sorted(extra[j])))
        face = Prim()
        off = (rnd.random(), rnd.random())
        mesh.face_uv[key] = off
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
                if hole:
                    cu = (us[iu] + us[iu + 1]) / 2
                    cv = (vs[jv] + vs[jv + 1]) / 2
                    if hole[0] < cu < hole[2] and hole[1] < cv < hole[3]:
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
        mat = mat_split if kinds.get(key, "sawn") == "rough" else mat_sawn
        mesh.prim(face_mats.get(key, mat)).extend(face)

    if cavity:
        cx, cy, depth = cavity
        top, bot = sz, sz - depth
        xs_all = _axis_coords(lo[0], hi[0], step, tuple(sorted(extra[0])))
        ys_all = _axis_coords(lo[1], hi[1], step, tuple(sorted(extra[1])))
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
    mesh.edge_band = falloff
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

    open_runs = {}   # (i0, i1, val) -> first row; identical spans merge downward

    def rect(prim, xa, ya, xb, yb, z):
        flat_poly(prim, [(xa, ya, z), (xb, ya, z), (xb, yb, z), (xa, yb, z)], up, uvf)

    def quad(i0, i1, j0, j1, val):
        xa, xb = x0 + i0 * cell, x0 + i1 * cell
        ya, yb = y0 + j0 * cell, y0 + j1 * cell
        if val in (0, 1):
            rect(cut if val else top, xa, ya, xb, yb, zf if val else 0.0)
            return
        # straight edge strip: half cut, half top, one wall down the middle
        if val in (3, 12):
            ym = (ya + yb) / 2
            lo_cut = val == 3
            rect(cut if lo_cut else top, xa, ya, xb, ym, zf if lo_cut else 0.0)
            rect(top if lo_cut else cut, xa, ym, xb, yb, 0.0 if lo_cut else zf)
            n = (0.0, -1.0 if lo_cut else 1.0, 0.0)
            flat_poly(cut, [(xa, ym, 0.0), (xb, ym, 0.0), (xb, ym, zf), (xa, ym, zf)], n, uvf)
        else:
            xm = (xa + xb) / 2
            right_cut = val == 6
            rect(top if right_cut else cut, xa, ya, xm, yb, 0.0 if right_cut else zf)
            rect(cut if right_cut else top, xm, ya, xb, yb, zf if right_cut else 0.0)
            n = (1.0 if right_cut else -1.0, 0.0, 0.0)
            flat_poly(cut, [(xm, ya, 0.0), (xm, yb, 0.0), (xm, yb, zf), (xm, ya, zf)], n, uvf)

    def end_row(j, runs):
        for key in list(open_runs):
            if key not in runs:
                quad(key[0], key[1], open_runs.pop(key), j, key[2])
        for key in runs:
            open_runs.setdefault(key, j)

    for j in range(ny):
        r0, r1 = mask[j], mask[j + 1]
        if not any(r0) and not any(r1):
            end_row(j, {(0, nx, 0)})
            continue
        runs = set()
        rs, rv = 0, None
        for i in range(nx):
            c = (r0[i], r0[i + 1], r1[i + 1], r1[i])
            code = c[0] | c[1] << 1 | c[2] << 2 | c[3] << 3
            if code in (0, 15, 3, 12):
                val = {0: 0, 15: 1}.get(code, code)
                if rv is not None and rv != val:
                    runs.add((rs, i, rv))
                    rv = None
                if rv is None:
                    rs, rv = i, val
                continue
            if rv is not None:
                runs.add((rs, i, rv))
                rv = None
            if code in (6, 9):            # vertical edge: merges down the column
                runs.add((i, i + 1, code))
                continue
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
            runs.add((rs, nx, rv))
        end_row(j, runs)
    end_row(ny, set())
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
               rnd, n_len=40, n_wid=10):
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


def snake_plant(seed, n_leaves, h_range, w_range, spread, material, pups=0):
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
    # pups: short young shoots coming up near the rim
    for k in range(pups):
        ang = rnd.uniform(0, 2 * math.pi)
        r = spread * rnd.uniform(0.9, 1.25)
        base = (r * math.cos(ang), r * math.sin(ang), -12.0)
        h = rnd.uniform(*h_range) * rnd.uniform(0.18, 0.32)
        w = rnd.uniform(*w_range) * rnd.uniform(0.45, 0.65)
        leaves.append((base, h + 12.0, w, math.degrees(ang) + rnd.uniform(-60, 60),
                       rnd.uniform(0.05, 0.2)))
    for base, h, w, facing, lean in leaves:
        snake_leaf(prim, base, h, w, facing, lean,
                   twist_deg=rnd.uniform(-35, 35), curl=rnd.uniform(0.08, 0.18),
                   thickness=max(2.5, w * 0.08), rnd=rnd)
    return mesh


# --------------------------------------------------------------------------
# Round pieces: revolved profiles with rough displacement
# --------------------------------------------------------------------------


def revolve(segments, n_theta, disp=None, clamp=None, uv_scale=1 / 200.0, uv_off=(0.0, 0.0),
            name="revolve"):
    """Spin profile segments around the z axis.

    segments: list of (material, mapping, rows) where rows are (r, z, w),
    mapping is 'side' (wrap around) or 'top' (planar from above). Order the
    profile bottom-centre -> outward -> up -> inward so normals face out.
    disp(theta, r, z) gives a radial offset in mm, scaled by each row's w.
    clamp=(theta0_deg, D) slices a flat sawn facet: nothing pokes past the
    plane D mm from the axis, facing direction theta0.

    Returns the mesh; mesh.ring(r, z, w) gives the n_theta matching points of
    any row so other surfaces can join it without cracks.
    """
    n = n_theta
    th = [2 * math.pi * b / n for b in range(n + 1)]
    cs = [(math.cos(t), math.sin(t)) for t in th]
    t0, D = (math.radians(clamp[0]), clamp[1]) if clamp else (0.0, None)

    def pos(b, r, z, w):
        b %= n
        c, s = cs[b]
        rr = r + (w * disp(th[b], r, z) if (disp and w) else 0.0)
        if D is not None:
            k = math.cos(th[b] - t0)
            if k > 1e-6 and rr * k > D:
                rr = D / k
        return (rr * c, rr * s, z)

    mesh = Mesh(name)
    for mat, mapping, rows in segments:
        seg = Prim()
        for r, z, w in rows:
            for b in range(n + 1):
                p = pos(b, r, z, w)
                if mapping == "side":
                    uv = (th[b] * max(r, 1.0) * uv_scale + uv_off[0], z * uv_scale + uv_off[1])
                else:
                    uv = (p[0] * uv_scale + uv_off[0], p[1] * uv_scale + uv_off[1])
                seg.vert(p, (0.0, 0.0, 1.0), uv)
        W = n + 1
        P = seg.pos
        for a in range(len(rows) - 1):
            for b in range(n):
                A = a * W + b
                B, C, Dd = A + 1, A + W + 1, A + W
                for tri in ((A, B, C), (A, C, Dd)):
                    e = cross(sub(P[tri[1]], P[tri[0]]), sub(P[tri[2]], P[tri[0]]))
                    if dot(e, e) > 1e-14:
                        seg.tri(*tri)
        seg.smooth_normals()
        for a, (r, z, w) in enumerate(rows):
            row = range(a * W, a * W + W)
            if r == 0:
                avg = normalize(tuple(sum(seg.nrm[i][k] for i in row) for k in range(3)))
                for i in row:
                    seg.nrm[i] = avg
            else:
                i0, i1 = a * W, a * W + n
                avg = normalize(add(seg.nrm[i0], seg.nrm[i1]))
                seg.nrm[i0] = seg.nrm[i1] = avg
        mesh.prim(mat).extend(seg)
    mesh.ring = lambda r, z, w: [pos(b, r, z, w) for b in range(n)]
    return mesh


def annulus_to_rect(prim, ring, rect, z, n, uvf):
    """Flat surface between a closed ring (sorted by angle from 0) and a
    rectangle around the origin that an engraved panel will fill."""
    x0, y0, x1, y1 = rect

    def ray(c, s):
        tx = (x1 / c if c > 0 else x0 / c) if abs(c) > 1e-12 else float("inf")
        ty = (y1 / s if s > 0 else y0 / s) if abs(s) > 1e-12 else float("inf")
        t = min(tx, ty)
        return (c * t, s * t)

    norm_ang = lambda a: a % (2 * math.pi)
    outer = [(norm_ang(math.atan2(p[1], p[0])), (p[0], p[1])) for p in ring]
    inner = [(norm_ang(a), ray(math.cos(a), math.sin(a))) for a, _ in outer]
    inner += [(norm_ang(math.atan2(y, x)), (x, y)) for x, y in ((x1, y1), (x0, y1), (x0, y0), (x1, y0))]
    outer.sort(key=lambda e: e[0])
    inner.sort(key=lambda e: e[0])
    O = outer + [(outer[0][0] + 2 * math.pi, outer[0][1])]
    I = inner + [(inner[0][0] + 2 * math.pi, inner[0][1])]
    # start both loops near angle 0
    i = j = 0
    P = lambda q: (q[0], q[1], z)
    while i < len(O) - 1 or j < len(I) - 1:
        if j >= len(I) - 1 or (i < len(O) - 1 and O[i + 1][0] <= I[j + 1][0]):
            tri = [P(O[i][1]), P(O[i + 1][1]), P(I[j][1])]
            i += 1
        else:
            tri = [P(O[i][1]), P(I[j + 1][1]), P(I[j][1])]
            j += 1
        e = cross(sub(tri[1], tri[0]), sub(tri[2], tri[0]))
        if dot(e, e) > 1e-14:
            flat_poly(prim, tri, n, uvf)


def _rock_field(per, amp, R, H, z_pull=True):
    """Radial rough-split displacement for round stone, in mm."""
    def fn(t, r, z):
        x, y = math.cos(t) * R, math.sin(t) * R
        zn = 2 * z / H - 1 if H else 0.0
        bulge = 1 - zn ** 4
        broad = per.fbm(x / 75.0, y / 75.0, z / 75.0, 4, gain=0.55)
        ridge = 1 - abs(per.noise(x / 36.0 + 5.3, y / 36.0 + 1.7, z / 36.0 + 9.1))
        grain = per.fbm(x / 7.0, y / 7.0, z / 7.0 + 40.0, 2)
        chip = smoothstep(0.8, 1.0, abs(zn)) if z_pull else 0.0
        return amp * (0.15 + 0.35 * bulge + broad + 0.3 * (ridge ** 2 - 0.4)
                      + 0.06 * grain - 0.55 * chip)
    return fn


def round_coaster(R, thick, z0, amp, seed, mat_top, mat_edge, uv_off=(0.0, 0.0),
                  bottom_rect=None):
    """Honed round coaster with a hand-chipped, slightly rough rim.

    bottom_rect leaves that rectangle open in the underside for a stamp panel.
    """
    per = Perlin(seed)

    def disp(t, r, z):
        x, y = math.cos(t) * R, math.sin(t) * R
        return amp * (0.7 * per.fbm(x / 9.0, y / 9.0, z / 9.0, 3)
                      + 0.35 * per.noise(x / 2.6, y / 2.6, z / 2.6) - 0.3)

    zt = z0 + thick
    wall = [(R, z0 + 1.0 + (thick - 2.4) * k / 8, 1.0) for k in range(9)]
    segs = [
        (mat_top, "top", [(0.0, z0, 0.0), (R * 0.5, z0, 0.0), (R - 1.2, z0, 0.0)]),
        (mat_edge, "side", [(R - 1.2, z0, 0.0), (R - 0.35, z0 + 0.3, 0.6)] + wall +
         [(R - 0.35, zt - 0.35, 0.85), (R - 1.3, zt, 0.5)]),
        (mat_top, "top", [(R - 1.3, zt, 0.5), (R - 2.6, zt, 0.2), (R - 5.0, zt, 0.0),
                          (R * 0.7, zt, 0.0), (R * 0.4, zt, 0.0), (0.0, zt, 0.0)]),
    ]
    if bottom_rect is None:
        return revolve(segs, 400, disp, uv_scale=1 / 180.0, uv_off=uv_off, name="coaster")
    mesh = revolve(segs[1:], 400, disp, uv_scale=1 / 180.0, uv_off=uv_off, name="coaster")
    annulus_to_rect(mesh.prim(mat_top), mesh.ring(R - 1.2, z0, 0.0), bottom_rect, z0,
                    (0.0, 0.0, -1.0),
                    lambda p: (p[0] / 180.0 + uv_off[0], p[1] / 180.0 + uv_off[1]))
    return mesh


def disc(R, h, material, n=48, chamfer=0.0, uv_scale=1 / 130.0, top=True, bottom=True):
    """Plain cylinder (cork pad, felt pad). Base at z = 0."""
    segs = []
    if bottom:
        segs.append((material, "top", [(0.0, 0.0, 0.0), (R - chamfer, 0.0, 0.0)]))
    side = [(R - chamfer, 0.0, 0.0), (R, chamfer, 0.0), (R, h - chamfer, 0.0), (R - chamfer, h, 0.0)]
    if not chamfer:
        side = [(R, 0.0, 0.0), (R, h, 0.0)]
    segs.append((material, "side", side))
    if top:
        segs.append((material, "top", [(R - chamfer, h, 0.0), (0.0, h, 0.0)]))
    return revolve(segs, n, uv_scale=uv_scale, name="disc")


def round_planter(R, H, wall, depth, amp, seed, step, facet, mat_split, mat_sawn,
                  bottom_rect, name="planter"):
    """Round rough-split planter: split sides, one flat sawn facet, sawn rim,
    drilled pocket, sawn base with an open rectangle for the QR/stamp panel."""
    per = Perlin(seed)
    disp = _rock_field(per, amp, R, H)
    L = max(3 * amp, 8.0)
    r_in = R - wall
    n_theta = max(64, math.ceil(2 * math.pi * R / step))
    nz = max(4, math.ceil(H / step))
    walls = [(R, H * a / nz, 1.0) for a in range(nz + 1)]
    nr = max(3, math.ceil((wall - 2.0) / step))
    rim = []
    for a in range(nr + 1):
        r = R - (wall - 2.0) * a / nr
        rim.append((r, H, 1.0 - smoothstep(0.0, L, R - r)))
    rim += [(r_in + 0.6, H - 0.4, 0.0), (r_in, H - 2.0, 0.0)]
    nd = max(2, math.ceil(depth / 25.0))
    inner = [(r_in, H - 2.0 - (depth - 2.0) * a / nd, 0.0) for a in range(nd + 1)]
    floor = [(r_in, H - depth, 0.0), (r_in * 0.5, H - depth, 0.0), (0.0, H - depth, 0.0)]
    segs = [(mat_split, "side", walls), (mat_sawn, "top", rim),
            (mat_sawn, "side", inner), (mat_sawn, "top", floor)]
    mesh = revolve(segs, n_theta, disp, clamp=facet, uv_scale=1 / 200.0, name=name)
    ring = mesh.ring(R, 0.0, 1.0)
    annulus_to_rect(mesh.prim(mat_sawn), ring, bottom_rect, 0.0, (0.0, 0.0, -1.0),
                    lambda p: (p[0] / 200.0, p[1] / 200.0))
    mesh.edge_band = L
    return mesh


def soil_disc(R, step, amp, seed, material, uv_scale=1 / 120.0):
    """Lumpy round soil surface centred on the origin at z ~ 0."""
    per = Perlin(seed + 101)
    n = max(24, math.ceil(2 * math.pi * R / step))
    nr = max(2, math.ceil(R / step))
    mesh = Mesh("soil")
    prim = mesh.prim(material)
    W = n + 1
    for a in range(nr + 1):
        r = R * a / nr
        for b in range(W):
            t = 2 * math.pi * (b % n) / n
            x, y = r * math.cos(t), r * math.sin(t)
            z = amp * (per.fbm(x / 30.0, y / 30.0, 0.5, 3) + 0.35 * per.noise(x / 4.0, y / 4.0, 3.3))
            if a == 0:
                z = amp * (per.fbm(0.0, 0.0, 0.5, 3) + 0.35 * per.noise(0.0, 0.0, 3.3))
            prim.vert((x, y, z), (0.0, 0.0, 1.0), (x * uv_scale, y * uv_scale))
    for a in range(nr):
        for b in range(n):
            A = a * W + b
            if a > 0:
                prim.tri(A, A + 1, A + W + 1)
            prim.tri(A, A + W + 1, A + W)
    prim.smooth_normals()
    return mesh


def pebbles(count, R, seed, material, size=(4.0, 9.0), avoid=()):
    """Top-dressing of small squashed stones scattered inside radius R."""
    rnd = random.Random(seed)
    mesh = Mesh("pebbles")
    prim = mesh.prim(material)
    placed = 0
    tries = 0
    while placed < count and tries < count * 40:
        tries += 1
        a = rnd.uniform(*size)
        r = math.sqrt(rnd.random()) * (R - a)
        t = rnd.uniform(0, 2 * math.pi)
        cx, cy = r * math.cos(t), r * math.sin(t)
        if any(math.hypot(cx - ax, cy - ay) < ar + a * 0.5 for ax, ay, ar in avoid):
            continue
        b, c = a * rnd.uniform(0.6, 0.9), a * rnd.uniform(0.35, 0.55)
        rot = rnd.uniform(0, math.pi)
        cr, sr = math.cos(rot), math.sin(rot)
        lumps = [rnd.uniform(0.9, 1.1) for _ in range(5)]
        sp = Prim()
        nu, nv = 10, 6
        for j in range(nv + 1):
            ph = math.pi * j / nv - math.pi / 2
            for i in range(nu + 1):
                th = 2 * math.pi * (i % nu) / nu
                k = 1 + 0.08 * math.sin(3 * th + lumps[0] * 4) * math.cos(ph) * lumps[1]
                x = a / 2 * math.cos(ph) * math.cos(th) * k
                y = b / 2 * math.cos(ph) * math.sin(th) * k
                z = c / 2 * math.sin(ph)
                p = (cx + x * cr - y * sr, cy + x * sr + y * cr, z + c * 0.15)
                sp.vert(p, (0.0, 0.0, 1.0), ((cx + x) / 40.0 + placed * 0.37, (cy + y) / 40.0))
        W = nu + 1
        for j in range(nv):
            for i in range(nu):
                A = j * W + i
                for tri in ((A, A + 1, A + W + 1), (A, A + W + 1, A + W)):
                    e = cross(sub(sp.pos[tri[1]], sp.pos[tri[0]]), sub(sp.pos[tri[2]], sp.pos[tri[0]]))
                    if dot(e, e) > 1e-12:
                        sp.tri(*tri)
        sp.smooth_normals()
        prim.extend(sp)
        placed += 1
    return mesh


def box_void(lo, hi, material):
    """Closed box with inward-facing normals: a sealed empty pocket inside a
    solid, so slicers print walls around it instead of filling it."""
    mesh = Mesh("void")
    prim = mesh.prim(material)
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    uv = lambda p: (0.0, 0.0)
    for n, quad in (((1, 0, 0), [(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)]),
                    ((-1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),
                    ((0, 1, 0), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]),
                    ((0, -1, 0), [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)]),
                    ((0, 0, 1), [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]),
                    ((0, 0, -1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)])):
        flat_poly(prim, quad, tuple(float(c) for c in n), uv)
    return mesh
