"""Seeded noise: 3D Perlin for geometry, tileable value noise for textures."""
import math
import random


class Perlin:
    """Ken Perlin's improved noise, seeded. Output roughly in [-1, 1]."""

    def __init__(self, seed=0):
        r = random.Random(seed)
        p = list(range(256))
        r.shuffle(p)
        self.p = p + p

    @staticmethod
    def _grad(h, x, y, z):
        h &= 15
        u = x if h < 8 else y
        v = y if h < 4 else (x if h in (12, 14) else z)
        return (u if h & 1 == 0 else -u) + (v if h & 2 == 0 else -v)

    def noise(self, x, y, z):
        p, g = self.p, self._grad
        X, Y, Z = math.floor(x), math.floor(y), math.floor(z)
        x -= X; y -= Y; z -= Z
        X &= 255; Y &= 255; Z &= 255
        u = x * x * x * (x * (x * 6 - 15) + 10)
        v = y * y * y * (y * (y * 6 - 15) + 10)
        w = z * z * z * (z * (z * 6 - 15) + 10)
        A = p[X] + Y; AA = p[A] + Z; AB = p[A + 1] + Z
        B = p[X + 1] + Y; BA = p[B] + Z; BB = p[B + 1] + Z
        x1, y1, z1 = x - 1, y - 1, z - 1
        a = g(p[AA], x, y, z);   b = g(p[BA], x1, y, z)
        c = g(p[AB], x, y1, z);  d = g(p[BB], x1, y1, z)
        e = g(p[AA + 1], x, y, z1);  f = g(p[BA + 1], x1, y, z1)
        h = g(p[AB + 1], x, y1, z1); i = g(p[BB + 1], x1, y1, z1)
        l1 = a + u * (b - a); l2 = c + u * (d - c)
        l3 = e + u * (f - e); l4 = h + u * (i - h)
        m1 = l1 + v * (l2 - l1); m2 = l3 + v * (l4 - l3)
        return m1 + w * (m2 - m1)

    def fbm(self, x, y, z, octaves=4, lacunarity=2.03, gain=0.5):
        total, amp, norm = 0.0, 1.0, 0.0
        for o in range(octaves):
            total += amp * self.noise(x + o * 17.17, y - o * 9.31, z + o * 5.73)
            norm += amp
            amp *= gain
            x *= lacunarity; y *= lacunarity; z *= lacunarity
        return total / norm


class TileNoise:
    """2D value noise that wraps every `period` lattice cells."""

    def __init__(self, seed, period):
        r = random.Random(seed)
        self.P = period
        self.t = [r.random() * 2 - 1 for _ in range(period * period)]

    def __call__(self, x, y):
        P, t = self.P, self.t
        xi, yi = math.floor(x), math.floor(y)
        fx, fy = x - xi, y - yi
        xi %= P; yi %= P
        x1 = (xi + 1) % P; y1 = (yi + 1) % P
        a = t[yi * P + xi]; b = t[yi * P + x1]
        c = t[y1 * P + xi]; d = t[y1 * P + x1]
        sx = fx * fx * (3 - 2 * fx); sy = fy * fy * (3 - 2 * fy)
        return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy


class TileFBM:
    """Sum of TileNoise octaves; sample with u, v in [0, 1) and it tiles."""

    def __init__(self, seed, base_period, octaves, gain=0.5):
        self.layers = []
        amp, norm = 1.0, 0.0
        for o in range(octaves):
            self.layers.append((TileNoise(seed * 31 + o, base_period * 2 ** o),
                                base_period * 2 ** o, amp))
            norm += amp
            amp *= gain
        self.norm = norm

    def __call__(self, u, v):
        s = 0.0
        for n, P, a in self.layers:
            s += a * n(u * P, v * P)
        return s / self.norm


def smoothstep(e0, e1, x):
    if e1 == e0:
        return 0.0 if x < e0 else 1.0
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)
