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

## 3D printing (Bambu Lab A1, one color)

**Easiest:** open `print/limestone_set_A1.3mf` in Bambu Studio. It's a project with all four plates laid out below, and each piece carries the speed settings (0.28 mm layers, 2 walls, lightning infill, no supports). Pick your printer and filament, click **Slice all**, then send plate 1. When it finishes, clear the bed and send the next plate.

`print/` also holds the individual STL files in millimeters. They're stone only (no plant, soil, pebbles, cork or felt), every mesh is checked watertight, and they import into Bambu Studio at the right size with no scaling.

| File | Size (mm) | Scale | Rough time* |
|---|---|---|---|
| `coaster_1` to `coaster_4` | 101.6 x 101.6 x 9.5 | true size | 0.5 h each |
| `engraved_block` | 106 x 67 x 38 | true size | 1 h |
| `bookend_left`, `bookend_right` | 96 x 121 x 166 | true size | 4 h each |
| `planter_small` | 179 x 168 x 160 | true size | 6.5 h |
| `planter_large` | 250 x 238 x 225 | 70% (the full 34 cm won't fit the A1) | 15 h |

*About 32 h in total with the settings below. These are my estimates; trust Bambu Studio's number after slicing.

**Filament:** beige PLA (closest to Indiana limestone; grey is the fallback).

**Settings:** 0.28 mm layer height, 2 walls, **lightning infill**, no supports. Lightning only builds infill under top surfaces, which roughly halves the time on these solid shapes. The pieces print fine but come out light, so the bookends won't hold heavy books on their own. If you have spare time, print the bookends at 15% gyroid infill instead (about 10 h each).

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
- `stonekit/printprep.py`: welds meshes, closes hairline cracks, checks they're watertight and writes STL.
- `fonts/`: Liberation Serif and Sans (SIL Open Font License, see `fonts/LICENSE-Liberation.txt`).
