"""Procedural textures written as PNG, stdlib only."""
import math
import random
import struct
import zlib

from .noise import TileFBM, TileNoise, smoothstep


class Texture:
    def __init__(self, name, w, h):
        self.name, self.w, self.h = name, w, h
        self.data = bytearray(w * h * 3)

    def set(self, x, y, rgb):
        o = (y * self.w + x) * 3
        d = self.data
        d[o] = max(0, min(255, int(rgb[0])))
        d[o + 1] = max(0, min(255, int(rgb[1])))
        d[o + 2] = max(0, min(255, int(rgb[2])))

    def sample(self, u, v):
        """Nearest sample, wrapping; returns floats in 0..1 (sRGB)."""
        x = int((u % 1.0) * self.w) % self.w
        y = int((v % 1.0) * self.h) % self.h
        o = (y * self.w + x) * 3
        d = self.data
        return d[o] / 255.0, d[o + 1] / 255.0, d[o + 2] / 255.0

    def png(self):
        raw = b"".join(b"\x00" + bytes(self.data[y * self.w * 3:(y + 1) * self.w * 3])
                       for y in range(self.h))

        def chunk(tag, payload):
            return (struct.pack(">I", len(payload)) + tag + payload +
                    struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
        return (b"\x89PNG\r\n\x1a\n" +
                chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)) +
                chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def _stamp_flecks(buf, size, rnd, count, rad, factor, elong=(1.0, 2.6)):
    """Scatter small soft elliptical flecks (fossil hash) into a float RGB buffer, wrapping."""
    for _ in range(count):
        cx, cy = rnd.uniform(0, size), rnd.uniform(0, size)
        r = rnd.uniform(*rad)
        e = rnd.uniform(*elong)
        a = rnd.uniform(0, math.pi)
        f = rnd.uniform(*factor)
        ca, sa = math.cos(a), math.sin(a)
        R = int(r * e) + 2
        for dy in range(-R, R + 1):
            for dx in range(-R, R + 1):
                px, py = dx + 0.5 - (cx % 1), dy + 0.5 - (cy % 1)
                lu = (px * ca + py * sa) / (r * e)
                lv = (-px * sa + py * ca) / r
                d = math.sqrt(lu * lu + lv * lv)
                if d >= 1.0:
                    continue
                w = smoothstep(1.0, 0.55, d)
                o = (((int(cy) + dy) % size) * size + (int(cx) + dx) % size) * 3
                k = 1 + (f - 1) * w
                buf[o] *= k; buf[o + 1] *= k; buf[o + 2] *= k


def limestone(seed=7, size=512):
    """Indiana limestone: warm buff, soft mottling, fine fossil hash."""
    t = Texture("limestone", size, size)
    mottle = TileFBM(seed, 3, 4)
    grain = TileFBM(seed + 1, 64, 2)
    base = (203, 191, 164)
    buf = [0.0] * (size * size * 3)
    for y in range(size):
        v = y / size
        for x in range(size):
            u = x / size
            m = mottle(u, v)
            k = 1 + 0.07 * m + 0.03 * grain(u, v)
            o = (y * size + x) * 3
            buf[o], buf[o + 1], buf[o + 2] = base[0] * k, base[1] * k, base[2] * k * (1 - 0.02 * m)
    rnd = random.Random(seed)
    _stamp_flecks(buf, size, rnd, 2600, (0.5, 1.6), (0.80, 0.92))    # darker shell fragments
    _stamp_flecks(buf, size, rnd, 1400, (0.5, 1.2), (1.05, 1.11))    # bright calcite
    for y in range(size):
        for x in range(size):
            o = (y * size + x) * 3
            t.set(x, y, (buf[o], buf[o + 1], buf[o + 2]))
    return t


def cork(seed=11, size=512, cells=64):
    """Agglomerated cork: Worley cells for granules, dark seams between them."""
    t = Texture("cork", size, size)
    rnd = random.Random(seed)
    pts = [(rnd.random(), rnd.random()) for _ in range(cells * cells)]
    tint = [rnd.uniform(0.82, 1.14) for _ in range(cells * cells)]
    pore = [rnd.random() < 0.07 for _ in range(cells * cells)]
    big = TileFBM(seed, 5, 3)
    sc = cells / size
    for y in range(size):
        fy = y * sc
        iy = int(fy)
        for x in range(size):
            fx = x * sc
            ix = int(fx)
            d1 = d2 = 9.0
            best = 0
            for oy in (-1, 0, 1):
                cy = (iy + oy) % cells
                for ox in (-1, 0, 1):
                    cx = (ix + ox) % cells
                    c = cy * cells + cx
                    px, py = pts[c]
                    dx = ix + ox + px - fx
                    dy = iy + oy + py - fy
                    d = dx * dx + dy * dy
                    if d < d1:
                        d2, d1, best = d1, d, c
                    elif d < d2:
                        d2 = d
            d1, d2 = math.sqrt(d1), math.sqrt(d2)
            k = tint[best] * (1 + 0.08 * big(x / size, y / size))
            k *= 1 - 0.28 * smoothstep(0.12, 0.0, d2 - d1)       # seams
            if pore[best] and d1 < 0.28:
                k *= 0.55
            t.set(x, y, (176 * k, 129 * k, 84 * k))
    return t


def soil(seed=13, size=256):
    t = Texture("soil", size, size)
    clumps = TileFBM(seed, 8, 3)
    fine = TileNoise(seed + 1, 96)
    perl = TileNoise(seed + 2, 48)
    for y in range(size):
        v = y / size
        for x in range(size):
            u = x / size
            c = clumps(u, v)
            f = fine(u * 96, v * 96)
            k = 1 + 0.25 * c + 0.18 * f
            rgb = (58 * k, 43 * k, 31 * k)
            p = perl(u * 48, v * 48)
            if p > 0.86:                       # perlite grains
                rgb = (205, 200, 190)
            t.set(x, y, rgb)
    return t


def snake_leaf(seed=17, w=128, h=1024):
    """Sansevieria trifasciata 'Laurentii': banded dark green, yellow margins.

    u runs across the leaf (margins at 0 and 1), v from base (0) to tip (1).
    """
    t = Texture("snake_leaf", w, h)
    rnd = random.Random(seed)
    wav = TileNoise(seed, 16)
    edge = TileNoise(seed + 1, 64)
    mott = TileFBM(seed + 2, 4, 3)
    phase = rnd.random()
    for y in range(h):
        v = y / h
        for x in range(w):
            u = x / w
            # wavy cross bands
            band = math.sin(2 * math.pi * (v * 34 + phase + 0.18 * wav(u * 3, v * 16)))
            light = smoothstep(0.35, 0.8, band) * (0.55 + 0.45 * smoothstep(-0.2, 0.6, mott(u, v)))
            dark = (32, 58, 34)
            pale = (98, 128, 86)
            r = dark[0] + (pale[0] - dark[0]) * light
            g = dark[1] + (pale[1] - dark[1]) * light
            b = dark[2] + (pale[2] - dark[2]) * light
            # yellow margins with a ragged inner edge
            d = min(u, 1 - u)
            mw = 0.085 + 0.02 * edge(v * 64, u * 4)
            if d < mw:
                f = smoothstep(mw, mw - 0.015, d)
                r += (214 - r) * f; g += (198 - g) * f; b += (96 - b) * f
            elif d < mw + 0.03:              # thin dark line inside the margin
                r *= 0.8; g *= 0.85; b *= 0.8
            # pale base where the leaf leaves the soil, dry tip
            if v < 0.06:
                f = smoothstep(0.06, 0.0, v)
                r += (150 - r) * f * 0.6; g += (160 - g) * f * 0.6; b += (110 - b) * f * 0.6
            if v > 0.975:
                f = smoothstep(0.975, 1.0, v)
                r += (120 - r) * f; g += (98 - g) * f; b += (60 - b) * f
            t.set(x, y, (r, g, b))
    return t
