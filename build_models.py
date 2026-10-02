#!/usr/bin/env python3
"""Build the limestone product models as .glb files for Blender.

    python3 build_models.py                      # all three products + previews
    python3 build_models.py --name "Jordan Lee" --year 2027 --qr-base https://yourshop.com/s/

Pure Python standard library, no installs. Output goes to models/ and
previews/. Open in Blender with File > Import > glTF 2.0 (.glb/.gltf).
"""
import argparse
import math
import os
import random
import time

from stonekit import qr, shapes, textures, ttf
from stonekit.glb import Material, Node, write_glb
from stonekit.mesh import Mesh
from stonekit.preview import render

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
OUT = os.path.join(HERE, "models")
PREV = os.path.join(HERE, "previews")

FLIP_DOWN = ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0))   # panel faces -z
FACE_FRONT = ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0))   # panel faces -y


def make_materials():
    stone = textures.limestone()
    return {
        "Limestone_Honed": Material("Limestone_Honed", roughness=0.62, texture=stone),
        "Limestone_Split": Material("Limestone_Split", roughness=0.92, texture=stone),
        "Limestone_Sawn": Material("Limestone_Sawn", roughness=0.78, texture=stone),
        "Limestone_Engraved": Material("Limestone_Engraved", color=(0.80, 0.78, 0.74, 1.0),
                                       roughness=0.9, texture=stone),
        "Cork": Material("Cork", roughness=0.88, texture=textures.cork()),
        "Stamp_Ink": Material("Stamp_Ink", color=(0.025, 0.025, 0.03, 1.0), roughness=0.55),
        "Felt": Material("Felt", color=(0.045, 0.045, 0.05, 1.0), roughness=1.0),
        "Soil": Material("Soil", roughness=1.0, texture=textures.soil()),
        "Pebble": Material("Pebble", color=(0.62, 0.61, 0.58, 1.0), roughness=0.7, texture=stone),
        "SnakePlant_Leaf": Material("SnakePlant_Leaf", roughness=0.42,
                                    texture=textures.snake_leaf(), double_sided=True),
    }


def used(nodes, materials):
    names = set()

    def walk(ns):
        for n in ns:
            if n.mesh:
                names.update(n.mesh.prims)
            walk(n.children)
    walk(nodes)
    return {k: v for k, v in materials.items() if k in names}


def export(stem, nodes, materials):
    mats = used(nodes, materials)
    path = os.path.join(OUT, stem + ".glb")
    size = write_glb(path, nodes, mats)
    tris = 0

    def walk(ns):
        nonlocal tris
        for n in ns:
            if n.mesh:
                tris += n.mesh.ntris
            walk(n.children)
    walk(nodes)
    print(f"  wrote {os.path.relpath(path, HERE)}  ({size / 1e6:.1f} MB, {tris:,} triangles)")
    return mats


def panel(w, h, cell, depth, mat_top, mat_cut, uvf, polys=(), qrs=()):
    """Engraved/stamped panel centred on the origin, facing +z.

    qrs: (text, size_mm, (cx, cy)). Modules are snapped to whole cells and
    their edges land between sample points, so the squares come out crisp.
    """
    nx, ny = round(w / cell), round(h / cell)
    x0, y0 = -nx * cell / 2, -ny * cell / 2
    polys = list(polys)
    for text, size, (cx, cy) in qrs:
        m = qr.encode(text)
        n = len(m)
        mc = max(3, round(size / n / cell))
        half = 0.5 if (n * mc) % 2 == 0 else 0.0   # keep module edges between samples
        sx = x0 + (round((cx - x0) / cell) + half) * cell
        sy = y0 + (round((cy - y0) / cell) + half) * cell
        polys += qr.polys(m, mc * cell, (sx, sy))
    mask = ttf.rasterize(polys, x0, y0, nx, ny, cell)
    return shapes.engraved_panel(mask, x0, y0, nx, ny, cell, depth, mat_top, mat_cut, uvf)


def initials(name):
    words = [w for w in name.replace(".", " ").split() if w]
    return words[-1][0].upper() if words else ""


class Fonts:
    def __init__(self):
        self.serif = ttf.Font(os.path.join(FONTS, "LiberationSerif-Regular.ttf"))
        self.serif_b = ttf.Font(os.path.join(FONTS, "LiberationSerif-Bold.ttf"))
        self.sans = ttf.Font(os.path.join(FONTS, "LiberationSans-Bold.ttf"))


def maker_stamp(F, name, year, batch, w, cx=0.0, cy=0.0, k=1.0, tilt=0.0):
    """Inked maker's stamp: frame, quarry line, batch, owner, place/year."""
    T = ttf.text_polys
    polys = []
    polys += ttf.frame_polys(w, 30 * k, 0.6 * k, (cx, cy), tilt)
    tw = w - 6 * k
    rot = lambda p: ttf.rotate_polys(p, tilt, (cx, cy))
    polys += rot(T(F.sans, "INDIANA LIMESTONE", 2.4 * k, (cx, cy + 9.5 * k), 0.45 * k, tw))
    polys += rot(T(F.sans, f"BATCH {batch}", 4.0 * k, (cx, cy + 2.6 * k), 0.3 * k, tw))
    polys += rot(T(F.sans, name.upper(), 2.6 * k, (cx, cy - 4.4 * k), 0.35 * k, tw))
    polys += rot(T(F.sans, f"BLOOMINGTON, IN · {year}", 2.1 * k, (cx, cy - 10.2 * k), 0.3 * k, tw))
    return polys


# --------------------------------------------------------------------------
# 1. Coasters
# --------------------------------------------------------------------------

def build_coasters(M, F, a):
    print("Coasters: four round 4-inch limestone coasters, cork backs, stamp + QR")
    R, T, CORK_T = 50.8, 9.5, 2.0
    RC, CH = R - 1.5, 0.3
    H = CORK_T + T
    PW, PH = 76.0, 34.0
    # cork disc; its underside is a ring joined to the stamp panel
    cork = shapes.disc(RC, CORK_T, "Cork", n=200, chamfer=CH, bottom=False)
    ring = cork.ring(RC - CH, 0.0, 0.0)
    rect = (-PW / 2, -PH / 2, PW / 2, PH / 2)
    shapes.annulus_to_rect(cork.prim("Cork"), ring, rect, 0.0, (0.0, 0.0, -1.0),
                           lambda p: (p[0] / 130.0, p[1] / 130.0))
    stamp = maker_stamp(F, a.name, a.year, a.batch, 40.0, cx=-16.0, tilt=-2.0)
    pnl = panel(PW, PH, 0.1, 0.22, "Cork", "Stamp_Ink", lambda p: (p[0] / 130.0, -p[1] / 130.0),
                polys=stamp, qrs=[(a.qr_base + a.batch + "-CO", 26.0, (22.0, 0.0))])
    cork.merge(pnl.transformed(FLIP_DOWN))

    rnd = random.Random(4)
    nodes = []
    for k in range(4):
        stone = shapes.round_coaster(R, T, CORK_T, 0.9, 30 + k, "Limestone_Honed",
                                     "Limestone_Split", uv_off=(rnd.random(), rnd.random()))
        mesh = Mesh(f"Coaster_{k + 1}")
        mesh.prims.update(stone.prims)
        mesh.prims["Cork"] = cork.prims["Cork"]            # shared, written once
        mesh.prims["Stamp_Ink"] = cork.prims["Stamp_Ink"]
        if k < 3:
            nodes.append(Node(f"Coaster_{k + 1}", mesh,
                              t=(rnd.uniform(-1.5, 1.5), rnd.uniform(-1.5, 1.5), k * H),
                              rot=((0, 0, 1), rnd.uniform(0, 360))))
        else:
            mesh.name = "Coaster_4_Flipped"
            nodes.append(Node("Coaster_4_Flipped", mesh, t=(3.0, -4.0, 4 * H),
                              rot=[((1, 0, 0), 180.0), ((0, 0, 1), 9.0)]))
    mats = export("limestone_coasters", nodes, M)
    views = [("limestone_coasters.png", nodes, (175, -235, 150), (0, 0, 24), 30, (960, 640)),
             ("limestone_coasters_bottom.png", nodes, (3, -14, 215), (3, -4, 46), 30, (800, 560))]
    return mats, views


# --------------------------------------------------------------------------
# 2. Planters
# --------------------------------------------------------------------------

def planter(M, F, a, label, R, H, wall, depth, soil_drop, step, amp, seed, plant, pups,
            k, cell, n_pebbles):
    PW, PH = 110 * k, 50 * k
    stone = shapes.round_planter(R, H, wall, depth, amp, seed, step, (-90.0, R - 6 * k),
                                 "Limestone_Split", "Limestone_Sawn",
                                 (-PW / 2, -PH / 2, PW / 2, PH / 2), name=f"Planter_{label}_Stone")
    stamp = maker_stamp(F, a.name, a.year, a.batch, 60 * k, cx=-22 * k, cy=0.0, k=1.35 * k)
    pnl = panel(PW, PH, cell, 0.5, "Limestone_Sawn", "Stamp_Ink",
                lambda p: (p[0] / 200.0, -p[1] / 200.0), polys=stamp,
                qrs=[(a.qr_base + a.batch + "-P" + label[0], 36 * k, (31 * k, 0.0))])
    stone.merge(pnl.transformed(FLIP_DOWN))
    r_in = R - wall
    soil = shapes.soil_disc(r_in + 1.5, 4.0, 1.6, seed, "Soil")
    soil.name = f"Planter_{label}_Soil"
    stones = shapes.pebbles(n_pebbles, r_in - 2, seed + 5, "Pebble", size=(4.0 * k ** 0.5, 9.0 * k ** 0.5))
    stones.name = f"Planter_{label}_Pebbles"
    leaves = shapes.snake_plant(seed, *plant, material="SnakePlant_Leaf", pups=pups)
    leaves.name = f"Planter_{label}_SnakePlant"
    zs = H - soil_drop
    return stone, [Node(f"Planter_{label}_Stone", stone),
                   Node(f"Planter_{label}_Soil", soil, t=(0, 0, zs)),
                   Node(f"Planter_{label}_Pebbles", stones, t=(0, 0, zs)),
                   Node(f"Planter_{label}_SnakePlant", leaves, t=(0, 0, zs))]


def build_planters(M, F, a):
    print("Planters: round rough-split limestone, sawn facet, stamp + QR underneath")
    s_stone, small = planter(M, F, a, "Small", 85, 160, 22, 110, 18, 2.0, 5.0, 21,
                             (10, (250, 390), (30, 46), 34), 2, 1.0, 0.1, 45)
    l_stone, large = planter(M, F, a, "Large", 170, 320, 40, 230, 28, 3.0, 9.0, 42,
                             (18, (520, 820), (46, 70), 80), 4, 1.8, 0.15, 110)
    nodes = [Node("Planter_Small", None, t=(-250, -40, 0), rot=((0, 0, 1), 20), children=small),
             Node("Planter_Large", None, t=(140, 60, 0), rot=((0, 0, 1), -12), children=large)]
    mats = export("limestone_planters", nodes, M)
    bottom = [Node("Large_bottom_view", None, t=(0, 0, 320), rot=((1, 0, 0), 180.0),
                   children=[Node("stone", l_stone)])]
    views = [("limestone_planters.png", nodes, (420, -2150, 900), (-20, 0, 430), 30, (960, 640)),
             ("limestone_planter_bottom.png", bottom, (0, -30, 1050), (0, 0, 320), 30, (800, 560))]
    return mats, views


# --------------------------------------------------------------------------
# 3. Engraved block + bookends
# --------------------------------------------------------------------------

def bottom_label(F, a, suffix, w, cx, cy, k=1.0):
    T = ttf.text_polys
    polys = []
    polys += T(F.sans, "INDIANA LIMESTONE", 2.6 * k, (cx, cy + 9 * k), 0.45 * k, w)
    polys += T(F.serif_b, a.name, 3.6 * k, (cx, cy + 2 * k), 0.1 * k, w)
    polys += T(F.sans, f"BLOOMINGTON, IN · {a.year}", 2.3 * k, (cx, cy - 4.5 * k), 0.3 * k, w)
    polys += T(F.sans, f"No. {a.batch}-{suffix}", 2.3 * k, (cx, cy - 10 * k), 0.3 * k, w)
    return polys


def build_block(M, F, a):
    print("Keepsake: engraved block + personalised bookends, QR codes underneath")
    T = ttf.text_polys
    # hand-sized block: split sides, honed engraved top, sawn base with QR
    SIZE = (102.0, 64.0, 38.0)
    HOLE = (-42.0, -23.0, 42.0, 23.0)
    kinds = {"+x": "rough", "-x": "rough", "+y": "rough", "-y": "rough", "+z": "sawn", "-z": "sawn"}
    block = shapes.split_block(SIZE, kinds, 1.2, 2.2, 5, "Limestone_Split", "Limestone_Sawn",
                               name="Engraved_Block", holes={"+z": HOLE, "-z": HOLE},
                               face_mats={"+z": "Limestone_Honed"}, uv_scale=1 / 180.0)
    assert HOLE[2] <= SIZE[0] / 2 - block.edge_band and HOLE[3] <= SIZE[1] / 2 - block.edge_band
    w, h = HOLE[2] - HOLE[0], HOLE[3] - HOLE[1]
    ut, ub = block.face_uv["+z"], block.face_uv["-z"]
    top = []
    top += ttf.frame_polys(w - 2, h - 2, 0.5)
    top += T(F.serif_b, "BLOOMINGTON, INDIANA", 3.3, (0, 14.0), 0.7, 70)
    top.append(ttf.rect_poly(-14, 8.5, 14, 8.95))
    top += T(F.serif, a.name, 7.0, (0, -1.0), 0.15, 72)
    top += T(F.serif_b, str(a.year), 4.0, (0, -13.0), 1.5, 72)
    pt = panel(w, h, 0.1, 1.0, "Limestone_Honed", "Limestone_Engraved",
               lambda p: (p[0] / 180.0 + ut[0], p[1] / 180.0 + ut[1]), polys=top)
    block.merge(pt.transformed(t=(0.0, 0.0, SIZE[2])))
    pb = panel(w, h, 0.1, 0.4, "Limestone_Sawn", "Stamp_Ink",
               lambda p: (p[0] / 180.0 + ub[0], -p[1] / 180.0 + ub[1]),
               polys=bottom_label(F, a, "BK", 38, -19.5, 0.0),
               qrs=[(a.qr_base + a.batch + "-BK", 30.0, (20.0, 0.0))])
    block.merge(pb.transformed(FLIP_DOWN))

    # bookends: split top/back/outer side, sawn base, book face and engraved front
    BE = (90.0, 115.0, 160.0)
    AMP = 6.0
    FRONT = (12.0, -25.0, 138.0, 25.0)          # (z0, x0, z1, x1) on the -y face
    BOTTOM = (-25.0, -36.0, 25.0, 36.0)         # (x0, y0, x1, y1) on the -z face
    initial = initials(a.name)
    face = []
    fw, fh = FRONT[3] - FRONT[1], FRONT[2] - FRONT[0]
    face += ttf.frame_polys(fw - 2, fh - 2, 0.5)
    face += T(F.serif_b, "BLOOMINGTON", 3.6, (0, 50.0), 0.6, 42)
    face += T(F.serif_b, "INDIANA", 3.6, (0, 43.0), 0.6, 42)
    face.append(ttf.rect_poly(-10, 37.0, 10, 37.45))
    if initial:
        face += T(F.serif, initial, 28.0, (0, 12.0), 0.0, 40)
    face += T(F.serif, a.name, 5.6, (0, -16.0), 0.1, 42)
    face += T(F.serif_b, str(a.year), 4.4, (0, -26.0), 1.3, 42)
    face.append(ttf.rect_poly(-10, -33.0, 10, -32.55))
    pad = shapes.disc(7.0, 1.5, "Felt", n=32, chamfer=0.4)
    bookends = []
    for side, seed, inner, outer, x in (("Left", 7, "+x", "-x", -175.0), ("Right", 8, "-x", "+x", 175.0)):
        kinds = {inner: "sawn", "-y": "sawn", "-z": "sawn", outer: "rough", "+y": "rough", "+z": "rough"}
        be = shapes.split_block(BE, kinds, 2.0, AMP, seed, "Limestone_Split", "Limestone_Sawn",
                                name=f"Bookend_{side}", holes={"-y": FRONT, "-z": BOTTOM})
        band = be.edge_band
        assert BE[0] / 2 - FRONT[3] >= band and BE[2] - FRONT[2] >= band
        assert BE[1] / 2 - BOTTOM[3] >= band
        uf, ub = be.face_uv["-y"], be.face_uv["-z"]
        zc = (FRONT[0] + FRONT[2]) / 2
        pf = panel(fw, fh, 0.1, 1.0, "Limestone_Sawn", "Limestone_Engraved",
                   lambda p, zc=zc, uf=uf: ((p[1] + zc) / 200.0 + uf[0], p[0] / 200.0 + uf[1]),
                   polys=face)
        be.merge(pf.transformed(FACE_FRONT, (0.0, -BE[1] / 2, zc)))
        bw, bh = BOTTOM[2] - BOTTOM[0], BOTTOM[3] - BOTTOM[1]
        tag = "B" + side[0]
        pb = panel(bw, bh, 0.1, 0.4, "Limestone_Sawn", "Stamp_Ink",
                   lambda p, ub=ub: (p[0] / 200.0 + ub[0], -p[1] / 200.0 + ub[1]),
                   polys=bottom_label(F, a, tag, 44, 0.0, -20.0),
                   qrs=[(a.qr_base + a.batch + "-" + tag, 30.0, (0.0, 17.0))])
        be.merge(pb.transformed(FLIP_DOWN))
        for px in (-34.0, 34.0):
            for py in (-47.0, 47.0):
                be.merge(pad.transformed(FLIP_DOWN, (px, py, 0.0)))
        bookends.append(Node(f"Bookend_{side}", be, t=(x, 40.0, 1.5)))
    nodes = [Node("Engraved_Block", block, t=(0.0, -95.0, 0.0), rot=((0, 0, 1), 7.0))] + bookends
    mats = export("limestone_engraved_block_and_bookends", nodes, M)
    blk_bottom = [Node("v", None, t=(0, 0, 38), rot=((1, 0, 0), 180.0), children=[Node("b", block)])]
    be_bottom = [Node("v", None, t=(0, 0, 160), rot=((1, 0, 0), 180.0),
                      children=[Node("b", bookends[0].mesh)])]
    views = [
        ("limestone_engraved_block_and_bookends.png", nodes, (170, -760, 400), (0, -10, 60), 30, (960, 640)),
        ("limestone_engraved_block_closeup.png", nodes, (10, -150, 210), (0, -95, 38), 30, (800, 560)),
        ("limestone_engraved_block_bottom.png", blk_bottom, (0, -10, 230), (0, 0, 38), 30, (800, 560)),
        ("limestone_bookend_front.png", nodes, (-175, -330, 150), (-175, -17, 80), 30, (800, 560)),
        ("limestone_bookend_bottom.png", be_bottom, (0, -10, 470), (0, 0, 160), 30, (800, 560)),
    ]
    return mats, views


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="E. Hartwell", help="name engraved and stamped on the pieces")
    ap.add_argument("--year", default="2026", help="year engraved and stamped on the pieces")
    ap.add_argument("--batch", default="26-0417", help="batch number on the stamps and QR codes")
    ap.add_argument("--qr-base", default="https://example.com/s/",
                    help="QR codes link to this + batch + piece code, e.g. ...26-0417-CO")
    ap.add_argument("--no-preview", action="store_true", help="skip the preview PNGs")
    ap.add_argument("--only", choices=["coasters", "planters", "block"], help="build just one")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PREV, exist_ok=True)
    t0 = time.time()
    M = make_materials()
    F = Fonts()
    print(f"textures ready ({time.time() - t0:.0f}s)")
    jobs = {"coasters": build_coasters, "planters": build_planters, "block": build_block}
    for key, build in jobs.items():
        if args.only and args.only != key:
            continue
        t = time.time()
        mats, views = build(M, F, args)
        print(f"  built in {time.time() - t:.0f}s")
        if args.no_preview:
            continue
        for fname, nodes, cam, target, fov, size in views:
            t = time.time()
            render(os.path.join(PREV, fname), nodes, used(nodes, M), cam, target, fov, size=size)
            print(f"  preview {fname} ({time.time() - t:.0f}s)")


if __name__ == "__main__":
    main()
