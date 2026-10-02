"""Premium product scenes and photos, rendered with Blender Cycles.

Run with Blender's Python (Blender 4.2+ or the `bpy` module):

    blender -b -P render/render_products.py -- --product all
    python render/render_products.py --product keepsake --quick   # with pip bpy

Each product gets a styled set, a hero camera and a detail camera. Output:
renders/<product>_hero.png/.jpg, renders/<product>_detail.png/.jpg and
blender/<product>.blend (cameras and lights set, open and press F12).
"""
import argparse
import math
import os
import random
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import studio as S  # noqa: E402
import build_models as bm  # noqa: E402
from stonekit import shapes  # noqa: E402
from stonekit.mesh import Mesh  # noqa: E402

RENDERS = os.path.join(ROOT, "renders")
BLENDS = os.path.join(ROOT, "blender")


def material_map(M):
    """stonekit material names -> premium Blender materials (plus props)."""
    return {
        "Limestone_Honed": S.limestone("Limestone_Honed", "honed"),
        "Limestone_Split": S.limestone("Limestone_Split", "split"),
        "Limestone_Sawn": S.limestone("Limestone_Sawn", "sawn"),
        "Limestone_Engraved": S.gold_leaf("Gold_Leaf"),
        "Gold_Leaf": bpy.data.materials["Gold_Leaf"],
        "Stamp_Ink": S.ink("Stamp_Ink"),
        "Cork": S.cork("Cork"),
        "Felt": S.felt("Felt"),
        "Soil": S.soil("Soil"),
        "Pebble": S.river_pebble("Pebble"),
        "SnakePlant_Leaf": S.leaf("SnakePlant_Leaf", M["SnakePlant_Leaf"].texture),
    }


def glass_set(mats, x, y, z):
    """Crystal rocks glass, two fingers of whiskey, one clear ice sphere (mm)."""
    mats["Glass"] = S.glass("Glass")
    mats["Whiskey"] = S.whiskey("Whiskey")
    mats["Ice"] = S.ice("Ice")
    g = shapes.revolve([("Glass", "side", [
        (0.0, 0.0, 0), (36.0, 0.0, 0), (39.4, 0.6, 0), (40.6, 2.6, 0), (41.4, 30.0, 0), (42.4, 86.0, 0),
        (42.2, 88.6, 0), (41.4, 89.6, 0), (40.4, 89.2, 0), (39.9, 87.0, 0), (38.9, 30.0, 0),
        (38.2, 15.0, 0), (36.4, 12.6, 0), (32.0, 12.0, 0), (0.0, 11.8, 0)])], 160, name="glass")
    level = 50.0
    lq = shapes.revolve([("Whiskey", "side", [
        (0.0, 11.75, 0), (32.0, 11.95, 0), (36.5, 12.55, 0), (38.3, 15.0, 0), (38.98, 30.0, 0),
        (39.2, level, 0), (20.0, level, 0), (0.0, level, 0)])], 160, name="whiskey")
    R = 26.5
    rows = [(R * math.sin(math.pi * k / 40), 12.3 + R - R * math.cos(math.pi * k / 40), 0) for k in range(41)]
    rows[0] = (0.0, rows[0][1], 0); rows[-1] = (0.0, rows[-1][1], 0)
    sphere = shapes.revolve([("Ice", "side", rows)], 96, name="ice")
    for mesh, name in ((g, "Rocks_Glass"), (lq, "Whiskey"), (sphere, "Ice_Sphere")):
        S.simple_object(mesh, name, mats, (x * S.MM, y * S.MM, z * S.MM))


def book(k, t, d, h, cloth_name):
    """Clothbound hardback, spine facing -y at y = 0, standing on z = 0 (mm)."""
    b = Mesh(f"Book_{k}")
    board = 2.2
    for sx in (-1, 1):
        m = shapes.rounded_box((board, d, h), 0.8, cloth_name, seg=2, flat_div=1)
        b.merge(m.transformed(t=(sx * (t / 2 - board / 2), d / 2, 0.0)))
    spine = shapes.rounded_box((t, 3.0, h), 1.2, cloth_name, seg=3, flat_div=1)
    b.merge(spine.transformed(t=(0.0, 1.5, 0.0)))
    pg = shapes.rounded_box((t - 2 * board, d - 5.0, h - 6.0), 0.4, "Pages", seg=1, flat_div=1)
    b.merge(pg.transformed(t=(0.0, 2.5 + (d - 5.0) / 2, 3.0)))
    for zf in (0.12, 0.88):
        band = shapes.rounded_box((t - 3.0, 0.4, 2.2), 0.15, "Gold_Leaf", seg=1, flat_div=1)
        b.merge(band.transformed(t=(0.0, -0.15, h * zf)))
    title = shapes.rounded_box((max(6.0, t * 0.45), 0.4, 34.0), 0.15, "Gold_Leaf", seg=1, flat_div=1)
    b.merge(title.transformed(t=(0.0, -0.15, h * 0.58)))
    return b


SAVE_ONLY = False
HERO_ONLY = False


def finish(name, cams, quick, res_hero, res_detail):
    os.makedirs(RENDERS, exist_ok=True)
    os.makedirs(BLENDS, exist_ok=True)
    bpy.context.scene.camera = cams[0]
    s = bpy.context.scene
    for cam, res in ((cams[0], res_hero), (cams[1], res_detail)):
        cam["resolution"] = res            # remembered per camera for anyone re-rendering
    s.render.resolution_x, s.render.resolution_y = res_hero
    if not quick:
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BLENDS, name + ".blend"), compress=True)
    if SAVE_ONLY:
        return
    shots = ((cams[0], "hero", res_hero), (cams[1], "detail", res_detail))
    for cam, tag, res in shots[:1] if HERO_ONLY else shots:
        if quick:
            r = (res[0] // 4, res[1] // 4)
            S.render_to(cam, os.path.join(RENDERS, f"_quick_{name}_{tag}.png"), r, samples=24)
        else:
            S.render_to(cam, os.path.join(RENDERS, f"{name}_{tag}.png"), res)


# --------------------------------------------------------------------------
# 1. coasters
# --------------------------------------------------------------------------

def coasters(M, F, a, quick):
    S.reset_scene(samples=160)
    mats = material_map(M)
    _, views = bm.build_coasters(M, F, a)
    nodes = views[0][1]
    H = 11.5
    rnd = random.Random(3)
    for k in range(3):
        nodes[k].t = (-35.0 + rnd.uniform(-1.2, 1.2), 18.0 + rnd.uniform(-1.2, 1.2), k * H)
    nodes[3].t = (95.0, -62.0, H)
    nodes[3].rot = [((1, 0, 0), 180.0), ((0, 0, 1), -16.0)]
    S.add_nodes(nodes, mats)
    mats["Walnut"] = S.wood("Walnut")
    tray = shapes.rounded_box((430.0, 280.0, 22.0), 4.0, "Walnut", seg=4, flat_div=3, z0=-22.0)
    S.simple_object(tray, "Walnut_Tray", mats, (0.03, -0.02, 0.0), rot_z=0.0)
    glass_set(mats, -35.0, 18.0, 3 * H)
    back = S.cyclorama(S.plaster("Backdrop", (0.34, 0.29, 0.24)), width=3.0, depth=2.0, y_wall=0.55)
    back.location.z = -0.022
    S.world_color((0.30, 0.27, 0.24), 0.05)
    S.area_light("Key", (-0.55, -0.42, 0.62), (0.02, 0.0, 0.03), 0.9, 36.0, (1.0, 0.95, 0.88))
    S.area_light("Fill", (0.65, -0.55, 0.30), (0.02, 0.0, 0.03), 1.2, 8.0, (0.92, 0.95, 1.0))
    S.area_light("Rim", (0.25, 0.55, 0.45), (0.0, 0.0, 0.05), 0.5, 26.0, (1.0, 0.92, 0.80))
    S.area_light("Glass_Kicker", (-0.30, 0.45, 0.25), (-0.035, 0.018, 0.08), 0.25, 7.0)
    hero = S.camera("Camera_Hero", (-0.17, -0.60, 0.30), (0.02, -0.015, 0.045), lens=62.0, fstop=6.3,
                    focus=(0.0, -0.02, 0.03))
    detail = S.camera("Camera_Detail", (0.13, -0.27, 0.24), (0.095, -0.062, 0.012), lens=105.0,
                      fstop=4.5, focus=(0.095, -0.062, 0.012))
    finish("coasters", (hero, detail), quick, (2400, 1600), (2400, 1600))


# --------------------------------------------------------------------------
# 2. planters
# --------------------------------------------------------------------------

def planters(M, F, a, quick):
    S.reset_scene(samples=128)
    mats = material_map(M)
    _, views = bm.build_planters(M, F, a)
    nodes = views[0][1]
    PL = 120.0
    nodes[0].t = (-255.0, -80.0, PL)
    nodes[0].rot = ((0, 0, 1), 28.0)
    nodes[1].t = (130.0, 40.0, 0.0)
    nodes[1].rot = ((0, 0, 1), -8.0)
    S.add_nodes(nodes, mats)
    mats["Pedestal"] = S.plaster("Pedestal", (0.40, 0.355, 0.30), 60.0)
    plinth = shapes.rounded_box((250.0, 250.0, PL), 2.0, "Pedestal", seg=3, flat_div=2)
    S.simple_object(plinth, "Plaster_Pedestal", mats, (-0.255, -0.080, 0.0), rot_z=12.0)
    S.cyclorama(S.plaster("Backdrop", (0.62, 0.56, 0.48), 25.0), width=5.0, depth=3.5, height=2.6,
                radius=0.8, y_wall=0.75)
    S.world_color((0.55, 0.52, 0.48), 0.05)
    S.area_light("Window", (-1.7, -0.7, 1.5), (-0.05, 0.0, 0.45), 1.4, 420.0, (1.0, 0.94, 0.85), 1.9)
    S.area_light("Fill", (1.6, -1.4, 0.8), (0.0, 0.0, 0.4), 2.0, 30.0, (0.93, 0.96, 1.0))
    S.area_light("Rim", (0.9, 0.9, 1.6), (0.05, 0.0, 0.6), 0.8, 140.0, (1.0, 0.93, 0.82))
    S.area_light("Top", (0.0, -0.3, 2.3), (0.0, 0.0, 0.3), 1.5, 25.0)
    hero = S.camera("Camera_Hero", (0.30, -2.45, 0.74), (-0.05, 0.0, 0.47), lens=72.0, fstop=8.0,
                    focus=(0.05, 0.0, 0.25))
    detail = S.camera("Camera_Detail", (-0.22, -0.76, 0.52), (0.13, 0.02, 0.27), lens=62.0, fstop=5.6,
                      focus=(0.06, -0.12, 0.26))
    finish("planters", (hero, detail), quick, (2000, 2500), (2400, 1600))


# --------------------------------------------------------------------------
# 3. engraved block and bookends
# --------------------------------------------------------------------------

BOOKS = [  # (thickness, depth, height, cloth colour, linear RGB)
    (30, 158, 236, (0.055, 0.012, 0.012)),   # oxblood
    (24, 150, 218, (0.012, 0.020, 0.055)),   # navy
    (38, 165, 244, (0.020, 0.045, 0.025)),   # forest
    (22, 142, 205, (0.42, 0.30, 0.10)),      # ochre
    (33, 160, 232, (0.50, 0.46, 0.38)),      # natural linen
    (27, 152, 224, (0.030, 0.032, 0.036)),   # charcoal
    (35, 162, 240, (0.11, 0.035, 0.018)),    # rust
    (25, 148, 212, (0.07, 0.10, 0.12)),      # slate blue
]


def keepsake(M, F, a, quick):
    S.reset_scene(samples=160)
    mats = material_map(M)
    _, views = bm.build_block(M, F, a)
    nodes = views[0][1]
    nodes[0].t = (-8.0, -112.0, 0.0)
    nodes[0].rot = ((0, 0, 1), 9.0)
    total = sum(b[0] for b in BOOKS) + (len(BOOKS) - 1) * 1.2
    for nd, sx in ((nodes[1], -1), (nodes[2], 1)):     # bookends snug against the books
        nd.t = (sx * (total / 2 + 45.0 + 0.6), nd.t[1], nd.t[2])
    S.add_nodes(nodes, mats)
    mats["Walnut"] = S.wood("Walnut")
    mats["Pages"] = S.pages("Pages")
    desk = shapes.rounded_box((1200.0, 560.0, 32.0), 3.0, "Walnut", seg=3, flat_div=3, z0=-32.0)
    S.simple_object(desk, "Walnut_Desk", mats, (0.0, 0.03, 0.0))
    total = sum(b[0] for b in BOOKS) + (len(BOOKS) - 1) * 1.2
    x = -total / 2
    rnd = random.Random(9)
    for k, (t, d, h, col) in enumerate(BOOKS):
        cname = f"Cloth_{k}"
        mats[cname] = S.cloth(cname, col)
        bk = book(k, t, d, h, cname)
        S.simple_object(bk, f"Book_{k + 1}", mats, ((x + t / 2) * S.MM, -14.0 * S.MM, 0.0),
                        rot_z=rnd.uniform(-0.8, 0.8))
        x += t + 1.2
    S.cyclorama(S.plaster("Backdrop", (0.030, 0.050, 0.036), 30.0), width=3.0, depth=2.0, y_wall=0.45)
    bpy.data.objects["Backdrop"].location.z = -0.032
    S.world_color((0.20, 0.22, 0.20), 0.04)
    S.area_light("Key", (-0.62, -0.55, 0.70), (0.0, -0.02, 0.08), 0.9, 34.0, (1.0, 0.94, 0.86))
    S.area_light("Fill", (0.75, -0.60, 0.35), (0.0, -0.02, 0.08), 1.2, 7.0, (0.92, 0.95, 1.0))
    S.area_light("Rim", (0.35, 0.55, 0.60), (0.0, 0.03, 0.14), 0.6, 30.0, (1.0, 0.90, 0.78))
    S.area_light("Engraving_Rake", (-0.40, -0.15, 0.12), (-0.008, -0.112, 0.038), 0.25, 4.0, (1.0, 0.92, 0.82))
    hero = S.camera("Camera_Hero", (0.22, -0.86, 0.36), (0.0, -0.03, 0.085), lens=58.0, fstop=7.1,
                    focus=(-0.008, -0.10, 0.04))
    detail = S.camera("Camera_Detail", (0.05, -0.33, 0.22), (-0.008, -0.112, 0.036), lens=100.0,
                      fstop=5.0, focus=(-0.008, -0.112, 0.038))
    finish("keepsake", (hero, detail), quick, (2400, 1600), (2400, 1600))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", default="all", choices=["all", "coasters", "planters", "keepsake"])
    ap.add_argument("--quick", action="store_true", help="small, fast test renders only")
    ap.add_argument("--save-only", action="store_true", help="write the .blend files, skip rendering")
    ap.add_argument("--hero-only", action="store_true", help="render the hero shot, skip the detail shot")
    ap.add_argument("--name", default="E. Hartwell")
    ap.add_argument("--year", default="2026")
    ap.add_argument("--batch", default="26-0417")
    ap.add_argument("--qr-base", default="https://example.com/s/")
    a = ap.parse_args(argv)
    global SAVE_ONLY, HERO_ONLY
    SAVE_ONLY = a.save_only
    HERO_ONLY = a.hero_only
    bm.DETAIL = 1.0 if a.quick else 1.6
    bm.WRITE_GLB = False
    M = bm.make_materials()
    F = bm.Fonts()
    jobs = {"coasters": coasters, "planters": planters, "keepsake": keepsake}
    for key, fn in jobs.items():
        if a.product in ("all", key):
            print(f"=== {key} ===", flush=True)
            fn(M, F, a, a.quick)


if __name__ == "__main__":
    main()
