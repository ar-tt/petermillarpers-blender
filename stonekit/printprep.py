"""Make meshes print-ready: weld, close T-junction cracks, check, write STL (mm)."""
import math
import struct


def to_soup(mesh, scale=1.0):
    """Flatten every prim of a Mesh into (vertices, triangles), welded."""
    verts, index, tris = [], {}, []
    q = 1e4  # weld to 0.1 micron

    def vid(p):
        key = (round(p[0] * scale * q), round(p[1] * scale * q), round(p[2] * scale * q))
        i = index.get(key)
        if i is None:
            i = index[key] = len(verts)
            verts.append((p[0] * scale, p[1] * scale, p[2] * scale))
        return i

    for prim in mesh.prims.values():
        P, I = prim.pos, prim.idx
        for k in range(0, len(I), 3):
            a, b, c = vid(P[I[k]]), vid(P[I[k + 1]]), vid(P[I[k + 2]])
            if a != b and b != c and a != c:
                tris.append((a, b, c))
    return verts, tris


def _edges(tris):
    cnt = {}
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            k = (u, v) if u < v else (v, u)
            cnt[k] = cnt.get(k, 0) + 1
    return cnt


def fix_t_junctions(verts, tris, tol=1e-4, max_rounds=6):
    """Split triangles whose edges have other vertices lying on them.

    Neighbouring patches built at different resolutions meet with vertices
    in the middle of each other's edges; slicers see those as hairline
    holes. Splitting the long edges makes every edge shared by two faces.
    """
    cell = 1.0
    for _ in range(max_rounds):
        cnt = _edges(tris)
        open_edges = {k for k, n in cnt.items() if n == 1}
        if not open_edges:
            break
        grid = {}
        used = set(v for k in open_edges for v in k)
        for i in used:
            x, y, z = verts[i]
            grid.setdefault((int(math.floor(x / cell)), int(math.floor(y / cell)),
                             int(math.floor(z / cell))), []).append(i)

        def on_edge(u, v):
            (ax, ay, az), (bx, by, bz) = verts[u], verts[v]
            dx, dy, dz = bx - ax, by - ay, bz - az
            L2 = dx * dx + dy * dy + dz * dz
            if L2 < 1e-16:
                return []
            found = []
            x0, x1 = sorted((ax, bx)); y0, y1 = sorted((ay, by)); z0, z1 = sorted((az, bz))
            # widen by tol so points sitting on a cell boundary aren't missed
            rng = lambda lo, hi: range(int(math.floor((lo - tol) / cell)),
                                       int(math.floor((hi + tol) / cell)) + 1)
            for gx in rng(x0, x1):
                for gy in rng(y0, y1):
                    for gz in rng(z0, z1):
                        for i in grid.get((gx, gy, gz), ()):
                            if i == u or i == v:
                                continue
                            px, py, pz = verts[i]
                            t = ((px - ax) * dx + (py - ay) * dy + (pz - az) * dz) / L2
                            if t <= 1e-9 or t >= 1 - 1e-9:
                                continue
                            ex, ey, ez = ax + t * dx - px, ay + t * dy - py, az + t * dz - pz
                            if ex * ex + ey * ey + ez * ez < tol * tol:
                                found.append((t, i))
            found.sort()
            return [i for _, i in found]

        new = []
        changed = False
        for a, b, c in tris:
            splits = []
            any_split = False
            for u, v in ((a, b), (b, c), (c, a)):
                k = (u, v) if u < v else (v, u)
                pts = on_edge(u, v) if k in open_edges else []
                splits.append(pts)
                any_split |= bool(pts)
            if not any_split:
                new.append((a, b, c))
                continue
            changed = True
            poly = [a] + splits[0] + [b] + splits[1] + [c] + splits[2]
            n_split_edges = sum(1 for s in splits if s)
            if n_split_edges == 1:
                # fan from the corner opposite the split edge
                e = next(k for k, s in enumerate(splits) if s)
                apex = (a, b, c)[(e + 2) % 3]
                r = poly.index(apex)
                ring = poly[r:] + poly[:r]
                for k in range(1, len(ring) - 1):
                    new.append((ring[0], ring[k], ring[k + 1]))
            else:
                cx = sum(verts[i][0] for i in (a, b, c)) / 3
                cy = sum(verts[i][1] for i in (a, b, c)) / 3
                cz = sum(verts[i][2] for i in (a, b, c)) / 3
                m = len(verts)
                verts.append((cx, cy, cz))
                for k in range(len(poly)):
                    new.append((m, poly[k], poly[(k + 1) % len(poly)]))
        tris = new
        if not changed:
            break
    return verts, tris


def report(verts, tris):
    cnt = _edges(tris)
    open_e = sum(1 for n in cnt.values() if n == 1)
    multi = sum(1 for n in cnt.values() if n > 2)
    vol = 0.0
    for a, b, c in tris:
        (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = verts[a], verts[b], verts[c]
        vol += (x1 * (y2 * z3 - y3 * z2) - x2 * (y1 * z3 - y3 * z1) + x3 * (y1 * z2 - y2 * z1)) / 6
    lo = [min(v[k] for v in verts) for k in range(3)]
    hi = [max(v[k] for v in verts) for k in range(3)]
    return {"triangles": len(tris), "open_edges": open_e, "overshared_edges": multi,
            "volume_cm3": vol / 1000.0, "size_mm": [hi[k] - lo[k] for k in range(3)], "min": lo}


def write_stl(path, verts, tris, name="stone"):
    with open(path, "wb") as f:
        f.write(name.encode()[:80].ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            p1, p2, p3 = verts[a], verts[b], verts[c]
            ux, uy, uz = p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]
            vx, vy, vz = p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            L = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            f.write(struct.pack("<12fH", nx / L, ny / L, nz / L, *p1, *p2, *p3, 0))
