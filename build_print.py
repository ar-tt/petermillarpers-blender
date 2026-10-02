#!/usr/bin/env python3
"""Print-ready STL files (millimetres) for a Bambu Lab A1, single color PLA.

    python3 build_print.py
    python3 build_print.py --name "Jordan Lee" --year 2027 --qr-base https://yourshop.com/s/

Stone only: no plant, soil, pebbles, cork or felt. Stamps, QR codes and
lettering are cut 0.8-1 mm deep with bold strokes so a 0.4 mm nozzle keeps
them and they can be filled with paint. Everything is true size except the
large planter, which is scaled to the largest size that fits the A1's
256 mm build volume. Meshes are welded and checked watertight.
"""
import argparse
import os

from build_models import FACE_FRONT, FLIP_DOWN, Fonts, initials, panel
from stonekit import bambu3mf, printprep, shapes, ttf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "print")
BED = 256.0
QR_DEPTH = 0.8
ENGRAVE = 1.0
NOUV = lambda p: (0.0, 0.0)


def stamp(F, a, w, cx=0.0, cy=0.0, k=1.0):
    """Maker's stamp sized for printing: frame plus four bold lines."""
    T = ttf.text_polys
    tw = w - 6 * k
    polys = ttf.frame_polys(w, 40 * k, 0.9 * k, (cx, cy))
    polys += T(F.sans, "INDIANA LIMESTONE", 3.0 * k, (cx, cy + 12 * k), 0.4 * k, tw)
    polys += T(F.sans, f"BATCH {a.batch}", 5.0 * k, (cx, cy + 4 * k), 0.3 * k, tw)
    polys += T(F.sans, a.name.upper(), 3.6 * k, (cx, cy - 5 * k), 0.3 * k, tw)
    polys += T(F.sans, f"BLOOMINGTON · {a.year}", 3.0 * k, (cx, cy - 12.5 * k), 0.3 * k, tw)
    return polys


def label(F, a, suffix, w, cx, cy):
    T = ttf.text_polys
    polys = T(F.sans, "INDIANA LIMESTONE", 2.8, (cx, cy + 10.5), 0.3, w)
    polys += T(F.sans, a.name.upper(), 4.0, (cx, cy + 3.0), 0.3, w)
    polys += T(F.sans, f"BLOOMINGTON · {a.year}", 2.8, (cx, cy - 4.5), 0.3, w)
    polys += T(F.sans, f"No. {a.batch}-{suffix}", 2.8, (cx, cy - 11.5), 0.3, w)
    return polys


def coaster(F, a, k):
    R, T = 50.8, 9.5
    PW, PH = 86.0, 42.0
    stone = shapes.round_coaster(R, T, 0.0, 0.9, 30 + k, "stone", "stone",
                                 bottom_rect=(-PW / 2, -PH / 2, PW / 2, PH / 2))
    p = panel(PW, PH, 0.1, QR_DEPTH, "stone", "stone", NOUV, polys=stamp(F, a, 46, cx=-18.5),
              qrs=[(a.qr_base + a.batch + "-CO", 28.0, (24.5, 0.0))])
    stone.merge(p.transformed(FLIP_DOWN))
    return stone


def planter(F, a, label_, R, H, wall, depth, step, amp, seed, k, cell):
    PW, PH = 124 * k, 52 * k
    PW, PH = round(PW / cell) * cell, round(PH / cell) * cell   # panel must match the opening
    stone = shapes.round_planter(R, H, wall, depth, amp, seed, step, (-90.0, R - 6 * k),
                                 "stone", "stone", (-PW / 2, -PH / 2, PW / 2, PH / 2))
    p = panel(PW, PH, cell, QR_DEPTH, "stone", "stone", NOUV,
              polys=stamp(F, a, 58 * k, cx=-28 * k, k=1.2 * k),
              qrs=[(a.qr_base + a.batch + "-P" + label_[0], 40 * k, (36 * k, 0.0))])
    stone.merge(p.transformed(FLIP_DOWN))
    return stone


def block(F, a):
    T = ttf.text_polys
    SIZE = (102.0, 64.0, 38.0)
    HOLE = (-42.0, -23.0, 42.0, 23.0)
    kinds = {"+x": "rough", "-x": "rough", "+y": "rough", "-y": "rough", "+z": "sawn", "-z": "sawn"}
    b = shapes.split_block(SIZE, kinds, 1.2, 2.2, 5, "stone", "stone",
                           holes={"+z": HOLE, "-z": HOLE})
    w, h = HOLE[2] - HOLE[0], HOLE[3] - HOLE[1]
    top = ttf.frame_polys(w - 2, h - 2, 0.9)
    top += T(F.serif_b, "BLOOMINGTON, INDIANA", 4.0, (0, 14.0), 0.6, 74)
    top.append(ttf.rect_poly(-14, 7.8, 14, 8.6))
    top += T(F.serif_b, a.name, 7.5, (0, -1.0), 0.2, 74)
    top += T(F.serif_b, str(a.year), 4.5, (0, -13.5), 1.4, 74)
    b.merge(panel(w, h, 0.1, ENGRAVE, "stone", "stone", NOUV, polys=top)
            .transformed(t=(0.0, 0.0, SIZE[2])))
    pb = panel(w, h, 0.1, QR_DEPTH, "stone", "stone", NOUV,
               polys=label(F, a, "BK", 38, -20.0, 0.0),
               qrs=[(a.qr_base + a.batch + "-BK", 32.0, (21.0, 0.0))])
    b.merge(pb.transformed(FLIP_DOWN))
    return b


def bookend(F, a, side, seed, inner, outer):
    T = ttf.text_polys
    BE = (90.0, 115.0, 160.0)
    FRONT = (12.0, -25.0, 138.0, 25.0)
    BOTTOM = (-25.0, -36.0, 25.0, 36.0)
    kinds = {inner: "sawn", "-y": "sawn", "-z": "sawn", outer: "rough", "+y": "rough", "+z": "rough"}
    be = shapes.split_block(BE, kinds, 2.0, 6.0, seed, "stone", "stone",
                            holes={"-y": FRONT, "-z": BOTTOM})
    fw, fh = FRONT[3] - FRONT[1], FRONT[2] - FRONT[0]
    face = ttf.frame_polys(fw - 2, fh - 2, 0.9)
    face += T(F.serif_b, "BLOOMINGTON", 4.6, (0, 50.0), 0.5, 42)
    face += T(F.serif_b, "INDIANA", 4.6, (0, 42.0), 0.5, 42)
    face.append(ttf.rect_poly(-10, 35.2, 10, 36.0))
    if initials(a.name):
        face += T(F.serif_b, initials(a.name), 30.0, (0, 10.0), 0.0, 40)
    face += T(F.serif_b, a.name, 6.0, (0, -17.0), 0.1, 44)
    face += T(F.serif_b, str(a.year), 5.0, (0, -28.0), 1.2, 44)
    face.append(ttf.rect_poly(-10, -35.4, 10, -34.6))
    zc = (FRONT[0] + FRONT[2]) / 2
    be.merge(panel(fw, fh, 0.1, ENGRAVE, "stone", "stone", NOUV, polys=face)
             .transformed(FACE_FRONT, (0.0, -BE[1] / 2, zc)))
    tag = "B" + side[0]
    bw, bh = BOTTOM[2] - BOTTOM[0], BOTTOM[3] - BOTTOM[1]
    pb = panel(bw, bh, 0.1, QR_DEPTH, "stone", "stone", NOUV,
               polys=label(F, a, tag, 44, 0.0, -19.0),
               qrs=[(a.qr_base + a.batch + "-" + tag, 32.0, (0.0, 17.0))])
    be.merge(pb.transformed(FLIP_DOWN))
    return be


def estimate_hours(verts, tris, layer=0.2, infill=0.15, flow=9.0):
    """Very rough A1 time: 2 walls + shells around a sparse core, ~9 mm3/s average."""
    area = 0.0
    for a, b, c in tris:
        p, q, r = verts[a], verts[b], verts[c]
        ux, uy, uz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
        vx, vy, vz = r[0] - p[0], r[1] - p[1], r[2] - p[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        area += 0.5 * (nx * nx + ny * ny + nz * nz) ** 0.5
    rep = printprep.report(verts, tris)
    vol = rep["volume_cm3"] * 1000.0
    shell = min(vol, area * 0.85)
    extruded = shell + (vol - shell) * infill
    hours = extruded / flow / 3600.0 * (0.2 / layer) ** 0.35
    return hours, extruded * 1.24 / 1000.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="E. Hartwell")
    ap.add_argument("--year", default="2026")
    ap.add_argument("--batch", default="26-0417")
    ap.add_argument("--qr-base", default="https://example.com/s/")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    F = Fonts()
    pieces = [(f"coaster_{k + 1}", lambda k=k: coaster(F, a, k), 1.0) for k in range(4)]
    pieces += [
        ("engraved_block", lambda: block(F, a), 1.0),
        ("bookend_left", lambda: bookend(F, a, "Left", 7, "+x", "-x"), 1.0),
        ("bookend_right", lambda: bookend(F, a, "Right", 8, "-x", "+x"), 1.0),
        ("planter_small", lambda: planter(F, a, "Small", 85, 160, 22, 110, 2.0, 5.0, 21, 1.0, 0.1), 1.0),
        ("planter_large", lambda: planter(F, a, "Large", 170, 320, 40, 230, 3.0, 9.0, 42, 1.6, 0.15), None),
    ]
    objects = {}
    total_h = total_g = 0.0
    print(f"{'piece':<16}{'size (mm)':>24}{'scale':>7}{'open':>6}{'grams':>7}{'hours':>7}")
    for name, build, scale in pieces:
        mesh = build()
        if scale is None:   # biggest that fits the bed with a little margin
            v0, _ = printprep.to_soup(mesh)
            span = max(max(v[k] for v in v0) - min(v[k] for v in v0) for k in range(3))
            scale = (BED - 6.0) / span
        verts, tris = printprep.to_soup(mesh, scale)
        verts, tris = printprep.fix_t_junctions(verts, tris)
        rep = printprep.report(verts, tris)
        zmin = rep["min"][2]
        verts = [(x, y, z - zmin) for x, y, z in verts]
        printprep.write_stl(os.path.join(OUT, name + ".stl"), verts, tris, name)
        objects[name] = (verts, tris)
        h, g = estimate_hours(verts, tris)
        total_h += h; total_g += g
        sx, sy, sz = rep["size_mm"]
        print(f"{name:<16}{sx:>8.1f} x{sy:>6.1f} x{sz:>6.1f}{scale:>7.0%}"
              f"{rep['open_edges'] + rep['overshared_edges']:>6}{g:>7.0f}{h:>7.1f}")
    print(f"{'total':<16}{'':>37}{total_g:>7.0f}{total_h:>7.1f}")
    if len(objects) == len(pieces):
        write_project(objects)


# Four plates, longest print first. Bookends stand side by side along their
# long side with the block turned 90 degrees next to them.
PLATES = [
    ("1 Large planter", [("planter_large", 128.0, 128.0, False)]),
    ("2 Small planter", [("planter_small", 128.0, 128.0, False)]),
    ("3 Bookends + block", [("bookend_left", 60.0, 66.0, False),
                            ("bookend_right", 60.0, 192.0, False),
                            ("engraved_block", 168.0, 128.0, True)]),
    ("4 Coasters", [("coaster_1", 72.0, 72.0, False), ("coaster_2", 184.0, 72.0, False),
                    ("coaster_3", 72.0, 184.0, False), ("coaster_4", 184.0, 184.0, False)]),
]
# per-object overrides so the speed settings travel with the project
SETTINGS = {"layer_height": "0.28", "wall_loops": "2", "sparse_infill_pattern": "lightning",
            "sparse_infill_density": "15%", "enable_support": "0"}


def write_project(objects):
    path = os.path.join(OUT, "limestone_set_A1.3mf")
    bambu3mf.write_project(path, objects, PLATES, settings=SETTINGS)
    print(f"wrote {os.path.relpath(path, HERE)} ({os.path.getsize(path) / 1e6:.1f} MB, "
          f"{len(PLATES)} plates)")


if __name__ == "__main__":
    main()
