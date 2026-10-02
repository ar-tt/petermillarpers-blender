# Limestone product models for Blender

3D models of three Indiana limestone products, built at real-world size and ready to open in Blender. Every piece carries a working QR code on its underside.

| File | What's in it |
|---|---|
| `models/limestone_coasters.glb` | Four round 4 in (101.6 mm) limestone coasters with honed tops, hand-chipped rough rims and cork backs, stacked. The top one is flipped to show the cork underside: an inked maker's stamp (batch, name, Bloomington, year) next to a QR code. |
| `models/limestone_planters.glb` | Round rough-split limestone planters in two sizes (170 mm and 340 mm across). The sides are split stone with one flat sawn facet on the front. The rim and base are sawn, and the pocket is drilled. Each holds soil, pebble top-dressing and a snake plant (Sansevieria 'Laurentii') with young pups. The base carries the maker's stamp and a QR code. |
| `models/limestone_engraved_block_and_bookends.glb` | A hand-sized block (102 x 64 x 38 mm) with split sides and a honed top engraved "BLOOMINGTON, INDIANA", a name and a year inside a border. Beside it sits a pair of rough-split bookends, each with an engraved front panel (place, monogram, name, year), a sawn book face and felt pads. The block and both bookends have a QR code and label on the base. |

Quick previews are in `previews/`, including the undersides. They come from a simple built-in renderer, so expect much better results from Blender.

## Opening in Blender

File > Import > glTF 2.0 (.glb/.gltf), then pick a file. Blender 2.80 and newer have this importer built in.

- Units come in as metres at true scale. A coaster is 0.1016 m across.
- Materials and textures are embedded: limestone (honed, split, sawn), cork, felt, soil, pebbles and the banded leaf.
- Every piece is its own named object (`Coaster_4_Flipped`, `Planter_Large_SnakePlant`, `Bookend_Left`, ...). Planter parts are grouped under an empty per size.
- Engraving, stamps and QR codes are real geometry cut into the surface. Engraved letters use `Limestone_Engraved` and stamps and QR codes use `Stamp_Ink`, so you can recolor either by changing one material.
- To keep a `.blend`, import and then File > Save As.

## QR codes

Each piece gets its own code. A code links to `--qr-base` + batch + a piece suffix:

| Piece | Default link |
|---|---|
| Coasters | `https://example.com/s/26-0417-CO` |
| Small / large planter | `.../26-0417-PS`, `.../26-0417-PL` |
| Engraved block | `.../26-0417-BK` |
| Left / right bookend | `.../26-0417-BL`, `.../26-0417-BR` |

`example.com` is a placeholder. Point the codes at your real site with `--qr-base`. The encoder is in `stonekit/qr.py` (standard QR, error correction level M), and the codes in the previews were decoded back from the rendered models to check they scan.

## Personalizing

The name, year, batch and link are placeholders. Rebuild with your own:

```
python3 build_models.py --name "Jordan Lee" --year 2027 --batch 26-0512 --qr-base https://yourshop.com/s/
```

The bookend monogram is the first letter of the last word of the name. Use `--only coasters|planters|block` to rebuild one product, and `--no-preview` to skip the preview images (they take several minutes).

The build uses only the Python standard library (3.8+), so no Blender or pip installs are needed. `tools/check_glb.py models/*.glb` reads the files back and checks them.

## Product photos and Blender scenes

`renders/` holds finished product photos (PNG plus a smaller JPEG of each), rendered in Blender Cycles:

| Product | Hero shot | Detail shot |
|---|---|---|
| Coasters | `coasters_hero` - stack on a walnut tray with a rocks glass of whiskey and an ice sphere, one coaster flipped to show the stamp | `coasters_detail` - the cork underside with the inked stamp and QR code |
| Planters | `planters_hero` (portrait) - both planters with snake plants, the small one on a plaster pedestal | `planters_detail` - split-stone texture, sawn rim, soil and pebbles |
| Keepsake | `keepsake_hero` - bookends holding a row of clothbound books, engraved block in front, walnut desk | `keepsake_detail` - the gold-filled engraving on the block |

`blender/` holds the scenes as `.blend` files (Blender 4.2 or newer) with everything set up: materials, props, softbox lighting, and two cameras (`Camera_Hero`, `Camera_Detail`). Open one and press F12 to render, or pick the other camera under Scene properties > Camera. Everything is packed into the file.

The look comes from procedural materials built in `render/studio.py`: buff limestone with fossil flecks and calcite sparkle, separate honed, sawn and split finishes, gold-leaf lettering, ink, granular cork, oiled walnut, clothbound books, soil, river pebbles, glass, whiskey and ice. They generate detail at any zoom, so close-ups stay sharp.

To re-render with your own name, year, batch or link (needs Blender 4.2+ on your computer, or the `bpy` Python module):

```
blender -b -P render/render_products.py -- --product all --name "Jordan Lee" --year 2027
```

`--product coasters|planters|keepsake` renders one scene; `--quick` makes small test images in about a minute.

## 3D printing (Bambu Lab A1, one color)

**Easiest:** open `print/limestone_set_A1.3mf` in Bambu Studio. It's a project with all four plates laid out below, and each piece carries the speed settings (0.28 mm layers, 2 walls, lightning infill, no supports). Pick your printer and filament, click **Slice all**, then send plate 1. When it finishes, clear the bed and send the next plate.

`print/` also holds the individual STL files in millimeters. They're stone only (no plant, soil, pebbles, cork or felt), every mesh is checked watertight, and they import into Bambu Studio at the right size with no scaling.

| File | Size (mm) | Scale | Default settings* | Fast settings* |
|---|---|---|---|---|
| `coaster_1` to `coaster_4` | 101.6 x 101.6 x 9.5 | true size | 0.8 h each | 0.5 h each |
| `engraved_block` | 106 x 67 x 38 | true size, hollow core | 1.6 h | 0.8 h |
| `bookend_left`, `bookend_right` | 94 x 120 x 165 | true size, hollow core | 6.4 h each | 3 h each |
| `planter_small` | 177 x 168 x 160 | true size, 11 mm walls | 10 h | 5 h |
| `planter_large` | 212 x 202 x 192 | 60% (the full 34 cm won't fit the A1), thin walls | 14 h | 7 h |

*My estimates, about 42 h in total at Bambu's defaults and about 22 h with the fast settings. My numbers have come in low against a real slice, so **use the fast settings** to stay comfortably under 48 h, and trust Bambu Studio's estimate.

The block and bookends have a sealed hollow core (at least 3 mm of solid wall everywhere, including under the engraving), and the planter walls are thinner than the display models. From the outside they look the same.

**Filament:** white PLA. It reads as pale stone, and black paint in the QR codes gives the strongest contrast for scanning. For a warmer limestone look, brush on a thin tan wash and wipe most of it off.

**Fast settings (set these in Bambu Studio before slicing):**
1. Process preset: **0.28mm Extra Draft @BBL A1**
2. Strength tab: Sparse infill pattern **Lightning** (keep 2 walls)
3. Support: off

The project file also carries these settings on each piece, but Bambu Studio doesn't always load them, so set them once in the process panel to be sure. Lightning infill only fills under top surfaces, so the pieces come out light, and the bookends won't hold heavy books on their own.

**Orientation:** as exported, base down. The QR codes and stamps print against the plate, and the coaster tops and block engraving face up.

**Plates (longest first, so the overnight runs carry the big pieces):**
1. Large planter
2. Small planter
3. Both bookends + engraved block (bookends side by side along their long side, block next to them)
4. All four coasters (2 x 2)

**After printing:** the QR codes, stamps and lettering are cut 0.8-1 mm deep. Work black acrylic paint (or a paint marker) into them, then wipe the surface with a damp paper towel so only the cuts stay dark. The QR codes need that contrast to scan. Glue 2 mm cork sheet under the coasters to bring them to the full 11.5 mm.

Rebuild the STLs with your own details using `python3 build_print.py --name ... --year ... --batch ... --qr-base ...`.

## How it's put together

- `stonekit/shapes.py`: rough-split blocks (split faces bulge and break while sawn faces stay flat), revolved round pieces with rough rims and sawn facets, engraved panels, soil, pebbles and snake plant leaves.
- `stonekit/qr.py`: QR code encoder.
- `stonekit/ttf.py`: reads the TrueType outlines used for lettering.
- `stonekit/textures.py`: procedural limestone, cork, soil and leaf textures.
- `stonekit/glb.py`: glTF 2.0 binary writer.
- `render/studio.py`, `render/render_products.py`: Blender materials, props, lights, cameras and the three photo scenes.
- `stonekit/printprep.py`: welds meshes, closes hairline cracks, checks they're watertight and writes STL.
- `fonts/`: Liberation Serif and Sans (SIL Open Font License, see `fonts/LICENSE-Liberation.txt`).
