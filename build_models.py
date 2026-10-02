#!/usr/bin/env python3
"""Build the limestone product models as .glb files for Blender.

    python3 build_models.py                      # all three products + previews
    python3 build_models.py --name "Jordan Lee" --year 2027 --no-preview

Pure Python standard library, no installs. Output goes to models/ and
previews/. Open in Blender with File > Import > glTF 2.0 (.glb/.gltf).
"""
import argparse
import math
import os
import random
import time

from stonekit import shapes, textures, ttf
from stonekit.glb import Material, Node, write_glb
from stonekit.mesh import Mesh, flat_poly
from stonekit.preview import render

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
OUT = os.path.join(HERE, "models")
PREV = os.path.join(HERE, "previews")


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
        "Soil": Material("Soil", roughness=1.0, texture=textures.soil()),
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


def panel_mask(polys, w, h, cell):
    nx, ny = round(w / cell), round(h / cell)
    x0, y0 = -nx * cell / 2, -ny * cell / 2
    return ttf.rasterize(polys, x0, y0, nx, ny, cell), x0, y0, nx, ny


# --------------------------------------------------------------------------
# 1. Coasters
# --------------------------------------------------------------------------

def build_coasters(M, batch):
    print("Coasters: four 4-inch honed limestone coasters, cork backs, batch stamp")
    sans = ttf.Font(os.path.join(FONTS, "LiberationSans-Bold.ttf"))
    STONE = (101.6, 101.6, 9.5)          # 4 in square, 3/8 in thick
    CORK_W, CORK_T = 99.0, 2.0
    H = CORK_T + STONE[2]

    # cork pad with the batch stamp pressed into its underside
    tilt = -2.5                           # hand stamps never land square
    polys = []
    polys += ttf.frame_polys(64, 32, 0.7, rotate_deg=tilt)
    polys += ttf.text_polys(sans, "INDIANA LIMESTONE", 2.8, (0, 8.6), 0.55, 56, tilt)
    polys += ttf.text_polys(sans, f"BATCH {batch}", 5.2, (0, 0.6), 0.35, 56, tilt)
    polys += ttf.text_polys(sans, "HONED · 4 IN · CORK BACKED", 2.2, (0, -8.4), 0.3, 56, tilt)
    cell = 0.1
    mask, x0, y0, nx, ny = panel_mask(polys, CORK_W, CORK_W, cell)
    uvc = lambda p: (p[0] / 130.0 + 0.31, p[1] / 130.0 + 0.17)
    panel = shapes.engraved_panel(mask, x0, y0, nx, ny, cell, 0.22, "Cork", "Stamp_Ink", uvc)
    # panel is built facing +z; flip it to face down as the cork's underside
    flip = ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0))
    cork = panel.transformed(flip)
    c = CORK_W / 2
    cp = cork.prim("Cork")
    for n, quad in (((1, 0, 0), [(c, -c, 0), (c, c, 0), (c, c, CORK_T), (c, -c, CORK_T)]),
                    ((-1, 0, 0), [(-c, -c, 0), (-c, c, 0), (-c, c, CORK_T), (-c, -c, CORK_T)]),
                    ((0, 1, 0), [(-c, c, 0), (c, c, 0), (c, c, CORK_T), (-c, c, CORK_T)]),
                    ((0, -1, 0), [(-c, -c, 0), (c, -c, 0), (c, -c, CORK_T), (-c, -c, CORK_T)]),
                    ((0, 0, 1), [(-c, -c, CORK_T), (c, -c, CORK_T), (c, c, CORK_T), (-c, c, CORK_T)])):
        flat_poly(cp, [tuple(float(v) for v in p) for p in quad], tuple(float(v) for v in n),
                  lambda p: (p[0] / 130.0 + p[2] / 130.0, p[1] / 130.0 + p[2] / 130.0))

    rnd = random.Random(4)
    nodes = []
    for k in range(4):
        stone = shapes.rounded_box(STONE, 1.2, "Limestone_Honed", seg=3, flat_div=1,
                                   z0=CORK_T, uv_off=(rnd.random(), rnd.random()))
        mesh = Mesh(f"Coaster_{k + 1}")
        mesh.prims["Limestone_Honed"] = stone.prims["Limestone_Honed"]
        mesh.prims["Cork"] = cork.prims["Cork"]            # shared, written once
        mesh.prims["Stamp_Ink"] = cork.prims["Stamp_Ink"]
        if k < 3:
            nodes.append(Node(f"Coaster_{k + 1}", mesh,
                              t=(rnd.uniform(-1.5, 1.5), rnd.uniform(-1.5, 1.5), k * H),
                              rot=((0, 0, 1), rnd.uniform(-4, 4))))
        else:
            mesh.name = "Coaster_4_Flipped"
            nodes.append(Node("Coaster_4_Flipped", mesh, t=(2.0, -3.0, 4 * H),
                              rot=[((1, 0, 0), 180.0), ((0, 0, 1), 13.0)]))
    mats = export("limestone_coasters", nodes, M)
    return nodes, mats


# --------------------------------------------------------------------------
# 2. Planters
# --------------------------------------------------------------------------

def planter(label, size, wall, depth, soil_drop, step, amp, seed, plant):
    sx, sy, sz = size
    cav = (sx - 2 * wall, sy - 2 * wall, depth)
    kinds = {"+x": "rough", "-x": "rough", "+y": "rough", "-y": "sawn", "+z": "sawn", "-z": "sawn"}
    stone = shapes.split_block(size, kinds, step, amp, seed, "Limestone_Split", "Limestone_Sawn",
                               cavity=cav, name=f"Planter_{label}_Stone")
    soil = shapes.soil_patch(cav[0] + 3, cav[1] + 3, 4.0, 1.6, seed, "Soil")
    soil.name = f"Planter_{label}_Soil"
    leaves = shapes.snake_plant(seed, *plant, material="SnakePlant_Leaf")
    leaves.name = f"Planter_{label}_SnakePlant"
    zs = sz - soil_drop
    return [Node(f"Planter_{label}_Stone", stone),
            Node(f"Planter_{label}_Soil", soil, t=(0, 0, zs)),
            Node(f"Planter_{label}_SnakePlant", leaves, t=(0, 0, zs))]


def build_planters(M):
    print("Planters: rough-split limestone, one sawn face, snake plant, small + large")
    small = planter("Small", (160, 160, 150), wall=22, depth=105, soil_drop=18, step=2.0,
                    amp=5.0, seed=21, plant=(9, (250, 390), (30, 46), 34))
    large = planter("Large", (320, 320, 300), wall=40, depth=220, soil_drop=28, step=3.0,
                    amp=9.0, seed=42, plant=(16, (520, 820), (46, 70), 80))
    nodes = [Node("Planter_Small", None, t=(-230, -40, 0), rot=((0, 0, 1), 24), children=small),
             Node("Planter_Large", None, t=(130, 60, 0), rot=((0, 0, 1), -14), children=large)]
    mats = export("limestone_planters", nodes, M)
    return nodes, mats


# --------------------------------------------------------------------------
# 3. Engraved block + bookends
# --------------------------------------------------------------------------

def build_block(M, name, year):
    print("Keepsake: engraved hand-sized block beside a pair of bookends")
    serif = ttf.Font(os.path.join(FONTS, "LiberationSerif-Regular.ttf"))
    serif_b = ttf.Font(os.path.join(FONTS, "LiberationSerif-Bold.ttf"))
    SIZE = (102.0, 64.0, 38.0)           # about 4 x 2.5 x 1.5 in
    HOLE = (-47.0, -28.0, 47.0, 28.0)
    body = shapes.rounded_box(SIZE, 2.0, "Limestone_Honed", seg=4, flat_div=2,
                              hole=HOLE, uv_off=(0.37, 0.61))
    polys = []
    polys += ttf.text_polys(serif_b, "BLOOMINGTON, INDIANA", 3.6, (0, 15.5), 0.75, 84)
    polys.append(ttf.rect_poly(-16, 9.2, 16, 9.7))
    polys += ttf.text_polys(serif, name, 7.2, (0, -0.5), 0.15, 84)
    polys += ttf.text_polys(serif_b, str(year), 4.2, (0, -15.0), 1.5, 84)
    cell = 0.1
    w, h = HOLE[2] - HOLE[0], HOLE[3] - HOLE[1]
    mask, x0, y0, nx, ny = panel_mask(polys, w, h, cell)
    uvs = lambda p: (p[0] / 180.0 + 0.37, p[1] / 180.0 + 0.61)
    panel = shapes.engraved_panel(mask, x0, y0, nx, ny, cell, 1.0,
                                  "Limestone_Honed", "Limestone_Engraved", uvs)
    body.merge(panel.transformed(t=(0.0, 0.0, SIZE[2])))
    body.name = "Engraved_Block"

    kinds = {"+x": "sawn", "-z": "sawn", "-x": "rough", "+y": "rough", "-y": "rough", "+z": "rough"}
    BE = (75.0, 115.0, 160.0)
    left = shapes.split_block(BE, kinds, 2.2, 4.5, 7, "Limestone_Split", "Limestone_Sawn",
                              name="Bookend_Left")
    right = shapes.split_block(BE, kinds, 2.2, 4.5, 8, "Limestone_Split", "Limestone_Sawn",
                               name="Bookend_Right")
    nodes = [Node("Engraved_Block", body, t=(0.0, -95.0, 0.0), rot=((0, 0, 1), 7.0)),
             Node("Bookend_Left", left, t=(-170.0, 40.0, 0.0)),
             Node("Bookend_Right", right, t=(170.0, 40.0, 0.0), rot=((0, 0, 1), 180.0))]
    mats = export("limestone_engraved_block_and_bookends", nodes, M)
    return nodes, mats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="E. Hartwell", help="name engraved on the block")
    ap.add_argument("--year", default="2026", help="year engraved on the block")
    ap.add_argument("--batch", default="26-0417", help="batch number stamped on the cork")
    ap.add_argument("--no-preview", action="store_true", help="skip the preview PNGs")
    ap.add_argument("--only", choices=["coasters", "planters", "block"], help="build just one")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PREV, exist_ok=True)
    t0 = time.time()
    M = make_materials()
    print(f"textures ready ({time.time() - t0:.0f}s)")

    jobs = {
        "coasters": (lambda: build_coasters(M, args.batch),
                     [("limestone_coasters.png", (175, -235, 165), (0, 0, 24), 30),
                      ("limestone_coasters_stamp.png", (0, -12, 230), (2, -3, 46), 30)]),
        "planters": (lambda: build_planters(M),
                     [("limestone_planters.png", (420, -2100, 900), (-20, 0, 430), 30)]),
        "block": (lambda: build_block(M, args.name, args.year),
                  [("limestone_engraved_block_and_bookends.png", (160, -700, 380), (0, -10, 55), 30),
                   ("limestone_engraved_block_closeup.png", (10, -150, 210), (0, -95, 38), 30)]),
    }
    for key, (build, views) in jobs.items():
        if args.only and args.only != key:
            continue
        t = time.time()
        nodes, mats = build()
        print(f"  built in {time.time() - t:.0f}s")
        if not args.no_preview:
            for fname, cam, target, fov in views:
                t = time.time()
                render(os.path.join(PREV, fname), nodes, mats, cam, target, fov)
                print(f"  preview {fname} ({time.time() - t:.0f}s)")


if __name__ == "__main__":
    main()
