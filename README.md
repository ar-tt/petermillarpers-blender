# Limestone product models for Blender

3D models of three Indiana limestone products, built at real-world size and ready to open in Blender.

| File | What's in it |
|---|---|
| `models/limestone_coasters.glb` | Four 4 in (101.6 mm) honed limestone coasters with cork backs, stacked. The top one is flipped cork-side up to show the inked batch stamp. |
| `models/limestone_planters.glb` | Rough-split limestone planters in two sizes (160 mm and 320 mm cubes). Three sides are split, the front is sawn flat, and the rim and base are sawn. Each holds soil and a snake plant (Sansevieria 'Laurentii'). |
| `models/limestone_engraved_block_and_bookends.glb` | A hand-sized honed block (102 x 64 x 38 mm) engraved "BLOOMINGTON, INDIANA" with a name and year, beside a pair of rough-split bookends with sawn bases and book faces. |

Quick previews are in `previews/`. They come from a simple built-in renderer, so expect much better results from Blender.

## Opening in Blender

File > Import > glTF 2.0 (.glb/.gltf), then pick a file. Blender 2.80 and newer have this importer built in.

- Units come in as metres at true scale. A coaster is 0.1016 m across.
- Materials and textures are embedded. Stone, cork, soil and the leaf banding all use image textures on Principled BSDF materials.
- Every piece is its own named object (`Coaster_4_Flipped`, `Planter_Large_SnakePlant`, `Bookend_Left`, ...), so you can move or hide them separately. Planter parts are grouped under an empty per size.
- The engraved letters and the stamp are real geometry, cut 1 mm into the block and 0.22 mm into the cork. Recessed faces get their own material (`Limestone_Engraved`, `Stamp_Ink`), so you can paint-fill the letters by changing one material.
- To keep a `.blend`, import and then File > Save As.

## Changing the engraving or stamp

The name, year and batch number are placeholders. Rebuild with your own:

```
python3 build_models.py --name "Jordan Lee" --year 2027 --batch 26-0512
```

Use `--only coasters|planters|block` to rebuild one product, and `--no-preview` to skip the preview images (the coaster stamp close-up takes about 4 minutes).

The build uses only the Python standard library (3.8+). No Blender or pip installs needed. `tools/check_glb.py models/*.glb` reads the files back and checks them.

## How it's put together

- `stonekit/shapes.py`: eased-edge blocks, rough-split blocks (split faces bulge and break; sawn faces stay perfectly flat while their outline follows the broken edge), engraved panels, soil, and snake plant leaves with thickness, twist and channelled cross-sections.
- `stonekit/ttf.py`: reads the TrueType outlines used for the lettering.
- `stonekit/textures.py`: procedural limestone, cork, soil and leaf textures.
- `stonekit/glb.py`: glTF 2.0 binary writer.
- `fonts/`: Liberation Serif and Sans (SIL Open Font License, see `fonts/LICENSE-Liberation.txt`).
