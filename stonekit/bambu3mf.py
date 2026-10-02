"""Write a multi-plate Bambu Studio project (.3mf).

Uses the same layout Bambu Studio saves: one model file per object (3MF
production extension), plates and per-object print settings in
Metadata/model_settings.config. Plates sit side by side in world space the
way Bambu Studio arranges them, so each object lands on its own plate.
"""
import math
import uuid
import zipfile

GAP = 0.2   # Bambu Studio's spacing between plates, as a fraction of plate size
NS = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
      'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
      'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
      'requiredextensions="p"')
APP = "BambuStudio-01.10.01.50"


def _uid(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "stonekit/" + "/".join(map(str, parts))))


def plate_origin(i, n, bed):
    """Where plate i (0-based) of n sits in Bambu Studio's world space."""
    v = math.sqrt(n)
    cols = int(round(v) + 1) if v > round(v) else int(round(v))
    row, col = divmod(i, cols)
    return col * bed[0] * (1 + GAP), -row * bed[1] * (1 + GAP)


def write_project(path, objects, plates, bed=(256.0, 256.0), settings=None, margin=2.0):
    """objects: {name: (verts, tris)} in mm, base at z = 0.
    plates: [(plate_name, [(object_name, cx, cy, rotate_90), ...]), ...] with
    (cx, cy) the footprint centre on that plate in bed coordinates.
    settings: per-object print setting overrides, e.g. {"layer_height": "0.28"}.
    """
    settings = settings or {}
    files = {}
    model_rels, items, cfg_objects, cfg_plates, assemble = [], [], [], [], []
    next_id = 1
    n = len(plates)
    for pi, (pname, placements) in enumerate(plates):
        ox, oy = plate_origin(pi, n, bed)
        boxes = []
        insts = []
        for name, cx, cy, rot in placements:
            verts, tris = objects[name]
            xs = [v[0] for v in verts]; ys = [v[1] for v in verts]; zs = [v[2] for v in verts]
            mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            w, d = max(xs) - min(xs), max(ys) - min(ys)
            if rot:
                w, d = d, w
            box = (cx - w / 2, cy - d / 2, cx + w / 2, cy + d / 2)
            if box[0] < margin or box[1] < margin or box[2] > bed[0] - margin or box[3] > bed[1] - margin:
                raise ValueError(f"{name} does not fit on plate {pi + 1}: {box}")
            for o in boxes:
                if box[0] < o[0][2] and o[0][0] < box[2] and box[1] < o[0][3] and o[0][1] < box[3]:
                    raise ValueError(f"{name} overlaps {o[1]} on plate {pi + 1}")
            boxes.append((box, name))

            mesh_id, obj_id = next_id, next_id + 1
            next_id += 2
            fname = f"3D/Objects/object_{mesh_id}.model"
            vtxt = "".join(f'<vertex x="{x - mx:.4f}" y="{y - my:.4f}" z="{z:.4f}"/>'
                           for x, y, z in verts)
            ttxt = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tris)
            files[fname] = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" '
                            f'xml:lang="en-US" {NS}>\n<metadata name="BambuStudio:3mfVersion">1</metadata>\n'
                            f'<resources><object id="{mesh_id}" p:UUID="{_uid(name, "mesh")}" type="model">'
                            f'<mesh><vertices>{vtxt}</vertices><triangles>{ttxt}</triangles></mesh>'
                            f'</object></resources><build/></model>\n')
            model_rels.append(fname)
            m = "0 1 0 -1 0 0 0 0 1" if rot else "1 0 0 0 1 0 0 0 1"
            tf = f"{m} {ox + cx:.4f} {oy + cy:.4f} 0"
            items.append((obj_id, name, mesh_id, tf))
            setting_lines = "".join(f'    <metadata key="{k}" value="{v}"/>\n' for k, v in settings.items())
            cfg_objects.append(
                f'  <object id="{obj_id}">\n'
                f'    <metadata key="name" value="{name}"/>\n'
                f'    <metadata key="extruder" value="1"/>\n{setting_lines}'
                f'    <part id="{mesh_id}" subtype="normal_part">\n'
                f'      <metadata key="name" value="{name}"/>\n'
                f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
                f'    </part>\n  </object>\n')
            insts.append(obj_id)
            assemble.append(f'   <assemble_item object_id="{obj_id}" instance_id="0" '
                            f'transform="{tf}" offset="0 0 0" />\n')
        inst_txt = "".join(
            f'    <model_instance>\n      <metadata key="object_id" value="{o}"/>\n'
            f'      <metadata key="instance_id" value="0"/>\n'
            f'      <metadata key="identify_id" value="{100 + o}"/>\n    </model_instance>\n'
            for o in insts)
        cfg_plates.append(
            f'  <plate>\n    <metadata key="plater_id" value="{pi + 1}"/>\n'
            f'    <metadata key="plater_name" value="{pname}"/>\n'
            f'    <metadata key="locked" value="false"/>\n{inst_txt}  </plate>\n')

    res = "".join(
        f' <object id="{oid}" p:UUID="{_uid(name, "obj")}" type="model">\n'
        f'  <components><component p:path="/3D/Objects/object_{mid}.model" objectid="{mid}" '
        f'p:UUID="{_uid(name, "comp")}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/></components>\n'
        f' </object>\n' for oid, name, mid, tf in items)
    build = "".join(f'  <item objectid="{oid}" p:UUID="{_uid(name, "item")}" transform="{tf}" '
                    f'printable="1"/>\n' for oid, name, mid, tf in items)
    files["3D/3dmodel.model"] = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}>\n'
        f' <metadata name="Application">{APP}</metadata>\n'
        f' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
        f' <metadata name="Title">Indiana limestone set</metadata>\n'
        f' <resources>\n{res} </resources>\n <build p:UUID="{_uid("build")}">\n{build} </build>\n</model>\n')
    files["3D/_rels/3dmodel.model.rels"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n' +
        "".join(f' <Relationship Target="/{f}" Id="rel-{k + 1}" '
                f'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
                for k, f in enumerate(model_rels)) + '</Relationships>\n')
    files["_rels/.rels"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n</Relationships>\n')
    files["[Content_Types].xml"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        ' <Default Extension="png" ContentType="image/png"/>\n'
        ' <Default Extension="config" ContentType="text/xml"/>\n</Types>\n')
    files["Metadata/model_settings.config"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + "".join(cfg_objects) +
        "".join(cfg_plates) + "  <assemble>\n" + "".join(assemble) + "  </assemble>\n</config>\n")
    order = ["[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model", "3D/_rels/3dmodel.model.rels",
             "Metadata/model_settings.config"] + model_rels
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in order:
            z.writestr(f, files[f])
