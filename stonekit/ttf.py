"""Minimal TrueType reader: glyph outlines -> flattened polygons in mm.

Only what the engraving needs: cmap format 4, simple and composite glyphs,
advance widths. No kerning or hinting.
"""
import math
import struct


class Font:
    def __init__(self, path):
        with open(path, "rb") as f:
            d = self.d = f.read()
        n = self._u16(4)
        self.tables = {}
        for t in range(n):
            off = 12 + 16 * t
            tag = d[off:off + 4].decode("latin1")
            self.tables[tag] = self._u32(off + 8)
        head = self.tables["head"]
        self.upem = self._u16(head + 18)
        loc_fmt = self._s16(head + 50)
        self.num_glyphs = self._u16(self.tables["maxp"] + 4)
        num_hm = self._u16(self.tables["hhea"] + 34)
        hmtx = self.tables["hmtx"]
        self.adv = [self._u16(hmtx + 4 * min(g, num_hm - 1)) for g in range(self.num_glyphs)]
        loca = self.tables["loca"]
        if loc_fmt == 0:
            self.loca = [self._u16(loca + 2 * g) * 2 for g in range(self.num_glyphs + 1)]
        else:
            self.loca = [self._u32(loca + 4 * g) for g in range(self.num_glyphs + 1)]
        self.glyf = self.tables["glyf"]
        self.cmap = self._read_cmap()
        self._cache = {}
        hg = self.cmap.get(ord("H"), 0)
        self.cap_height = self._s16(self.glyf + self.loca[hg] + 8)  # yMax of 'H'

    def _u16(self, o): return struct.unpack_from(">H", self.d, o)[0]
    def _s16(self, o): return struct.unpack_from(">h", self.d, o)[0]
    def _u32(self, o): return struct.unpack_from(">I", self.d, o)[0]

    def _read_cmap(self):
        base = self.tables["cmap"]
        n = self._u16(base + 2)
        best = None
        for k in range(n):
            pid, eid, off = struct.unpack_from(">HHI", self.d, base + 4 + 8 * k)
            if self._u16(base + off) == 4 and (pid == 3 and eid == 1 or pid == 0):
                best = base + off
                if pid == 3:
                    break
        if best is None:
            raise ValueError("font has no format-4 cmap")
        o = best
        segx2 = self._u16(o + 6)
        ends = o + 14
        starts = ends + segx2 + 2
        deltas = starts + segx2
        ros = deltas + segx2
        cmap = {}
        for s in range(segx2 // 2):
            end = self._u16(ends + 2 * s)
            start = self._u16(starts + 2 * s)
            delta = self._u16(deltas + 2 * s)
            ro = self._u16(ros + 2 * s)
            for c in range(start, end + 1):
                if c == 0xFFFF:
                    continue
                if ro == 0:
                    g = (c + delta) & 0xFFFF
                else:
                    g = self._u16(ros + 2 * s + ro + 2 * (c - start))
                    if g:
                        g = (g + delta) & 0xFFFF
                cmap[c] = g
        return cmap

    def contours(self, g):
        """List of contours, each a list of (x, y, on_curve) in font units."""
        if g in self._cache:
            return self._cache[g]
        d = self.d
        o, e = self.loca[g], self.loca[g + 1]
        out = []
        if o != e:
            p = self.glyf + o
            nc = self._s16(p)
            if nc >= 0:
                endpts = [self._u16(p + 10 + 2 * i) for i in range(nc)]
                il = self._u16(p + 10 + 2 * nc)
                q = p + 12 + 2 * nc + il
                npts = endpts[-1] + 1 if nc else 0
                flags = []
                while len(flags) < npts:
                    f = d[q]; q += 1
                    flags.append(f)
                    if f & 8:
                        r = d[q]; q += 1
                        flags.extend([f] * r)
                flags = flags[:npts]
                xs, x = [], 0
                for f in flags:
                    if f & 2:
                        dx = d[q]; q += 1
                        x += dx if f & 16 else -dx
                    elif not f & 16:
                        x += self._s16(q); q += 2
                    xs.append(x)
                ys, y = [], 0
                for f in flags:
                    if f & 4:
                        dy = d[q]; q += 1
                        y += dy if f & 32 else -dy
                    elif not f & 32:
                        y += self._s16(q); q += 2
                    ys.append(y)
                start = 0
                for ep in endpts:
                    out.append([(xs[i], ys[i], bool(flags[i] & 1)) for i in range(start, ep + 1)])
                    start = ep + 1
            else:
                q = p + 10
                while True:
                    flags, gi = self._u16(q), self._u16(q + 2)
                    q += 4
                    if flags & 1:
                        a1, a2 = self._s16(q), self._s16(q + 2); q += 4
                    else:
                        a1, a2 = struct.unpack_from(">bb", d, q); q += 2
                    a, b, c, dd = 1.0, 0.0, 0.0, 1.0
                    f2 = lambda off: self._s16(off) / 16384.0
                    if flags & 8:
                        a = dd = f2(q); q += 2
                    elif flags & 0x40:
                        a, dd = f2(q), f2(q + 2); q += 4
                    elif flags & 0x80:
                        a, b, c, dd = f2(q), f2(q + 2), f2(q + 4), f2(q + 6); q += 8
                    dx, dy = (a1, a2) if flags & 2 else (0, 0)
                    for con in self.contours(gi):
                        out.append([(a * x + c * y + dx, b * x + dd * y + dy, on) for x, y, on in con])
                    if not flags & 0x20:
                        break
        self._cache[g] = out
        return out


def flatten(contour, steps=8):
    """Quadratic B-spline contour -> closed polyline (list of (x, y))."""
    pts = []
    n = len(contour)
    for i in range(n):
        x, y, on = contour[i]
        nx, ny, non = contour[(i + 1) % n]
        pts.append((x, y, on))
        if not on and not non:
            pts.append(((x + nx) / 2, (y + ny) / 2, True))
    k = next(i for i, p in enumerate(pts) if p[2])
    pts = pts[k:] + pts[:k]
    pts.append(pts[0])
    out = [(pts[0][0], pts[0][1])]
    i = 0
    while i < len(pts) - 1:
        if pts[i + 1][2]:
            out.append((pts[i + 1][0], pts[i + 1][1]))
            i += 1
        else:
            (x0, y0, _), (cx, cy, _), (x1, y1, _) = pts[i], pts[i + 1], pts[i + 2]
            for s in range(1, steps + 1):
                t = s / steps
                mt = 1 - t
                out.append((mt * mt * x0 + 2 * mt * t * cx + t * t * x1,
                            mt * mt * y0 + 2 * mt * t * cy + t * t * y1))
            i += 2
    out.pop()  # closing point duplicates the first
    return out


def text_width(font, text, cap_mm, tracking_mm=0.0):
    s = cap_mm / font.cap_height
    w = sum(font.adv[font.cmap.get(ord(ch), 0)] * s + tracking_mm for ch in text)
    return w - tracking_mm


def text_polys(font, text, cap_mm, center=(0.0, 0.0), tracking_mm=0.0, max_width=None,
               rotate_deg=0.0):
    """Polygons for one centred line of text; cap height in mm.

    If max_width is given and the line is wider, cap height and tracking are
    scaled down together so it fits.
    """
    w = text_width(font, text, cap_mm, tracking_mm)
    if max_width and w > max_width:
        f = max_width / w
        cap_mm *= f
        tracking_mm *= f
        w = max_width
    s = cap_mm / font.cap_height
    x0 = -w / 2
    y0 = -cap_mm / 2
    polys = []
    pen = 0.0
    for ch in text:
        g = font.cmap.get(ord(ch), 0)
        for con in font.contours(g):
            polys.append([(x0 + pen + x * s, y0 + y * s) for x, y in flatten(con)])
        pen += font.adv[g] * s + tracking_mm
    return _place(polys, center, rotate_deg)


def rect_poly(x0, y0, x1, y1, ccw=True):
    p = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return p if ccw else p[::-1]


def frame_polys(w, h, thickness, center=(0.0, 0.0), rotate_deg=0.0):
    """Rectangular outline ring (outer CCW, inner CW so nonzero fill leaves a hole)."""
    polys = [rect_poly(-w / 2, -h / 2, w / 2, h / 2, True),
             rect_poly(-w / 2 + thickness, -h / 2 + thickness,
                       w / 2 - thickness, h / 2 - thickness, False)]
    return _place(polys, center, rotate_deg)


def _place(polys, center, rotate_deg):
    c, s = math.cos(math.radians(rotate_deg)), math.sin(math.radians(rotate_deg))
    cx, cy = center
    return [[(cx + x * c - y * s, cy + x * s + y * c) for x, y in poly] for poly in polys]


def rotate_polys(polys, deg, about=(0.0, 0.0)):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    ax, ay = about
    return [[(ax + (x - ax) * c - (y - ay) * s, ay + (x - ax) * s + (y - ay) * c)
             for x, y in poly] for poly in polys]


def rasterize(polys, x0, y0, nx, ny, cell):
    """Nonzero-winding fill sampled at grid points (nx+1 by ny+1).

    Returns a list of bytearrays, row j holding points at y = y0 + j*cell.
    """
    rows = [bytearray(nx + 1) for _ in range(ny + 1)]
    buckets = [[] for _ in range(ny + 1)]
    for poly in polys:
        n = len(poly)
        for k in range(n):
            (ax, ay), (bx, by) = poly[k], poly[(k + 1) % n]
            if ay == by:
                continue
            lo, hi = (ay, by) if ay < by else (by, ay)
            j0 = max(0, math.ceil((lo - y0) / cell))
            j1 = min(ny, math.ceil((hi - y0) / cell) - 1)
            edge = (ax, ay, bx, by, 1 if by > ay else -1, lo, hi)
            for j in range(j0, j1 + 1):
                buckets[j].append(edge)
    for j in range(ny + 1):
        if not buckets[j]:
            continue
        y = y0 + j * cell
        xs = []
        for ax, ay, bx, by, wdir, lo, hi in buckets[j]:
            if lo <= y < hi:
                xs.append((ax + (y - ay) * (bx - ax) / (by - ay), wdir))
        xs.sort()
        wind = 0
        row = rows[j]
        for k in range(len(xs) - 1):
            wind += xs[k][1]
            if wind != 0:
                i0 = max(0, math.ceil((xs[k][0] - x0) / cell))
                i1 = min(nx, math.ceil((xs[k + 1][0] - x0) / cell) - 1)
                for i in range(i0, i1 + 1):
                    row[i] = 1
    return rows
