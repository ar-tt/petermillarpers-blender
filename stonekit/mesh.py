"""Mesh containers and small vector helpers.

Everything is built Z-up in millimetres. The GLB writer converts to glTF's
Y-up metres on export, so Blender imports the models at true size.
"""
import math


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def normalize(a):
    L = length(a)
    if L < 1e-20:
        return (0.0, 0.0, 1.0)
    return (a[0] / L, a[1] / L, a[2] / L)


def rotation_matrix(axis, degrees):
    """Rodrigues rotation matrix as a tuple of three row tuples."""
    x, y, z = normalize(axis)
    t = math.radians(degrees)
    c, s, C = math.cos(t), math.sin(t), 1 - math.cos(t)
    return ((c + x * x * C, x * y * C - z * s, x * z * C + y * s),
            (y * x * C + z * s, c + y * y * C, y * z * C - x * s),
            (z * x * C - y * s, z * y * C + x * s, c + z * z * C))


def mat_mul(A, B):
    return tuple(tuple(sum(A[r][k] * B[k][c] for k in range(3)) for c in range(3))
                 for r in range(3))


def mat_vec(M, v):
    return (M[0][0] * v[0] + M[0][1] * v[1] + M[0][2] * v[2],
            M[1][0] * v[0] + M[1][1] * v[1] + M[1][2] * v[2],
            M[2][0] * v[0] + M[2][1] * v[1] + M[2][2] * v[2])


IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


class Prim:
    """One material's worth of indexed triangles."""
    __slots__ = ("pos", "nrm", "uv", "idx")

    def __init__(self):
        self.pos, self.nrm, self.uv, self.idx = [], [], [], []

    def vert(self, p, n, uv):
        self.pos.append(p)
        self.nrm.append(n)
        self.uv.append(uv)
        return len(self.pos) - 1

    def tri(self, a, b, c):
        self.idx.extend((a, b, c))

    def extend(self, other):
        off = len(self.pos)
        self.pos.extend(other.pos)
        self.nrm.extend(other.nrm)
        self.uv.extend(other.uv)
        self.idx.extend(i + off for i in other.idx)

    def transformed(self, R, t):
        out = Prim()
        out.pos = [add(mat_vec(R, p), t) for p in self.pos]
        out.nrm = [mat_vec(R, n) for n in self.nrm]
        out.uv = list(self.uv)
        out.idx = list(self.idx)
        return out

    def smooth_normals(self):
        acc = [[0.0, 0.0, 0.0] for _ in self.pos]
        P, I = self.pos, self.idx
        for k in range(0, len(I), 3):
            a, b, c = I[k], I[k + 1], I[k + 2]
            n = cross(sub(P[b], P[a]), sub(P[c], P[a]))  # area weighted
            for v in (a, b, c):
                s = acc[v]
                s[0] += n[0]; s[1] += n[1]; s[2] += n[2]
        self.nrm = [normalize(s) for s in acc]

    @property
    def ntris(self):
        return len(self.idx) // 3


class Mesh:
    """A named mesh made of one Prim per material."""

    def __init__(self, name):
        self.name = name
        self.prims = {}

    def prim(self, material):
        if material not in self.prims:
            self.prims[material] = Prim()
        return self.prims[material]

    def merge(self, other):
        for mat, p in other.prims.items():
            self.prim(mat).extend(p)

    def transformed(self, R=IDENTITY, t=(0.0, 0.0, 0.0), name=None):
        out = Mesh(name or self.name)
        for mat, p in self.prims.items():
            out.prims[mat] = p.transformed(R, t)
        return out

    @property
    def ntris(self):
        return sum(p.ntris for p in self.prims.values())


def newell_normal(pts):
    nx = ny = nz = 0.0
    n = len(pts)
    for k in range(n):
        x0, y0, z0 = pts[k]
        x1, y1, z1 = pts[(k + 1) % n]
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return normalize((nx, ny, nz))


def flat_poly(prim, pts, n, uvf):
    """Add a convex planar polygon with a flat normal, wound to face n."""
    if dot(newell_normal(pts), n) < 0:
        pts = pts[::-1]
    base = len(prim.pos)
    for p in pts:
        prim.vert(p, n, uvf(p))
    for k in range(1, len(pts) - 1):
        prim.tri(base, base + k, base + k + 1)


def rot_list(rot):
    """Normalise a rotation spec: None, (axis, deg) or [(axis, deg), ...] applied in order."""
    if not rot:
        return []
    if isinstance(rot[0], (int, float)) or (len(rot) == 2 and isinstance(rot[1], (int, float))):
        return [rot]
    return list(rot)


def rot_matrix(rot):
    M = IDENTITY
    for axis, deg in rot_list(rot):
        M = mat_mul(rotation_matrix(axis, deg), M)
    return M


def rot_quat(rot, convert=lambda v: v):
    """Quaternion (x, y, z, w) for a rotation spec; convert maps the axis frame."""
    q = (0.0, 0.0, 0.0, 1.0)
    for axis, deg in rot_list(rot):
        ax = normalize(convert(axis))
        s, c = math.sin(math.radians(deg) / 2), math.cos(math.radians(deg) / 2)
        r = (ax[0] * s, ax[1] * s, ax[2] * s, c)
        # q = r * q (apply r after q)
        x1, y1, z1, w1 = r
        x2, y2, z2, w2 = q
        q = (w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
             w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
             w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
             w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2)
    return q
