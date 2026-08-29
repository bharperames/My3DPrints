#!/usr/bin/env python3
"""Embed Bambu Studio project settings into a generated 3MF.

A trimesh-exported 3MF is geometry-only; Studio applies whatever presets the
user last touched (brim Auto often skips the brim these models need). This
injects Metadata/project_settings.config + model_settings.config and stamps
the archive as a Bambu project so the file opens (and CLI-slices) with the
intended settings baked in.

The config base is models/bambu_project_template.json — a full settings dump
exported by the user's own Bambu Studio (581 keys, version-matched), so the
GUI's config validation accepts it. Fallback: flattened system presets.
Only the keys in OVERRIDES are changed.
"""
import json
import os
import re
import sys
import zipfile

M = os.path.expanduser("~/Code/My3DPrints/models")
TEMPLATE = os.path.join(M, "bambu_project_template.json")
PRESETS = os.path.expanduser(
    "~/Library/Application Support/BambuStudio/system/BBL")
MACHINE = "Bambu Lab P2S 0.4 nozzle"
PROCESS = "0.20mm Standard @BBL P2S"
FILAMENT = "Bambu PLA Basic @BBL P2S"
META_KEYS = {"type", "name", "inherits", "from", "instantiation",
             "setting_id", "filament_id", "info_file"}
# Studio treats `different_settings_to_system` as the list of keys that
# really differ from the named system preset; anything not listed is reset
# to the preset value on load. Overrides must be declared there or the GUI
# silently drops them (the CLI applies the raw config either way).
PROCESS_OVERRIDES = ("brim_type", "brim_width", "brim_object_gap",
                     "enable_support", "reduce_crossing_wall")
OVERRIDES = {
    "curr_bed_type": "Textured PEI Plate",
    "brim_type": "outer_only",
    "brim_width": "5",
    "brim_object_gap": "0.1",
    "enable_support": "0",             # template came from a supported print
    # Travels that cross an open bore drag a string across it, once or more
    # per layer, and a helical thread turns each one a little further round
    # — which is the fan of strings that shows up inside a printed nut. The
    # system preset leaves this off. Measured on the coupler: 1029 crossings
    # of the open hole (20.5 m) become 34 (0.8 m), at no cost in time.
    "reduce_crossing_wall": "1",
}


def flatten(kind, name):
    chain = []
    while name:
        with open(os.path.join(PRESETS, kind, name + ".json")) as f:
            j = json.load(f)
        chain.insert(0, j)
        name = j.get("inherits")
    merged = {}
    for j in chain:
        merged.update(j)
    return {k: v for k, v in merged.items() if k not in META_KEYS}


def base_config():
    if os.path.exists(TEMPLATE):
        with open(TEMPLATE) as f:
            return json.load(f)
    cfg = {}
    cfg.update(flatten("filament", FILAMENT))
    cfg.update(flatten("machine", MACHINE))
    cfg.update(flatten("process", PROCESS))
    cfg.update({"printer_settings_id": MACHINE,
                "print_settings_id": PROCESS,
                "filament_settings_id": [FILAMENT]})
    return cfg


def embed(path, overrides=None, brim=True):
    """Stamp `path` as a Bambu project carrying the P2S presets.

    `brim` is a per-part decision, not a global: an outer brim earns its
    keep on a small or curved footprint, and costs peeling on a part that
    already has hundreds of cm2 on the plate.
    """
    cfg = base_config()
    cfg.update(OVERRIDES)
    if not brim:
        cfg["brim_type"] = "no_brim"
    cfg.update(overrides or {})
    dsts = list(cfg.get("different_settings_to_system") or [])
    while len(dsts) < 3:
        dsts.append("")
    declared = [k for k in str(dsts[0]).split(";") if k]
    for k in list(PROCESS_OVERRIDES) + [k for k in (overrides or {})]:
        if k not in declared and k in cfg:
            declared.append(k)
    dsts[0] = ";".join(declared)
    cfg["different_settings_to_system"] = dsts
    version = cfg.get("version", "02.02.02.56")
    with zipfile.ZipFile(path) as z:
        items = {n: z.read(n) for n in z.namelist()}
    mdl = items["3D/3dmodel.model"].decode("utf-8")
    # Bambu only reads project_settings.config from archives stamped as its
    # own projects: namespace + version metadata on the model XML
    if "BambuStudio:3mfVersion" not in mdl:
        i = mdl.index("<model ")
        j = mdl.index(">", i)
        if "xmlns:BambuStudio" not in mdl:
            mdl = (mdl[:j] +
                   ' xmlns:BambuStudio="http://schemas.bambulab.com/'
                   'package/2021"' + mdl[j:])
            j = mdl.index(">", i)
        mdl = (mdl[:j + 1] +
               f'<metadata name="Application">BambuStudio-{version}'
               '</metadata>'
               '<metadata name="BambuStudio:3mfVersion">1</metadata>' +
               mdl[j + 1:])
    # A project trusts stored placement, so a mesh built around z=0 stays
    # half under the bed and silently slices to half its height — the top
    # half only, starting from a cut through the middle of the part.
    dz, mx, my = 0.0, 0.0, 0.0
    try:
        import trimesh
        b = trimesh.load(path, force="scene").bounds
        dz = -float(b[0][2])
        mx, my = float((b[0][0] + b[1][0]) / 2), float((b[0][1] + b[1][1]) / 2)
    except Exception:
        pass
    if abs(dz) < 1e-4:
        dz = 0.0
    # move build items from the origin corner to the plate centre
    pa = cfg.get("printable_area", ["0x0", "256x0", "256x256", "0x256"])
    xs = [float(p.split("x")[0]) for p in pa]
    ys = [float(p.split("x")[1]) for p in pa]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    # centre the mesh's own bounds on the plate, not its origin: a part
    # modelled from its corner would otherwise be pushed a half-bed sideways
    # and fall off the plate
    mdl = mdl.replace(
        'transform="1.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0"',
        f'transform="1 0 0 0 1 0 0 0 1 {cx - mx:g} {cy - my:g} {dz:g}"')
    items["3D/3dmodel.model"] = mdl.encode("utf-8")
    items["Metadata/project_settings.config"] = json.dumps(
        cfg, indent=1).encode("utf-8")
    # object/plate records: the GUI's project loader expects them
    oids = re.findall(r'<object id="(\d+)"', mdl)
    obj_xml = "".join(
        f'  <object id="{o}">\n'
        f'    <metadata key="name" value="object_{o}"/>\n'
        f'    <metadata key="extruder" value="1"/>\n'
        f'  </object>\n' for o in oids)
    inst_xml = "".join(
        f'    <model_instance>\n'
        f'      <metadata key="object_id" value="{o}"/>\n'
        f'      <metadata key="instance_id" value="0"/>\n'
        f'      <metadata key="identify_id" value="{100 + int(o)}"/>\n'
        f'    </model_instance>\n' for o in oids)
    items["Metadata/model_settings.config"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + obj_xml +
        '  <plate>\n'
        '    <metadata key="plater_id" value="1"/>\n'
        '    <metadata key="plater_name" value=""/>\n'
        '    <metadata key="locked" value="false"/>\n' + inst_xml +
        '  </plate>\n</config>\n').encode("utf-8")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in items.items():
            z.writestr(n, data)


if __name__ == "__main__":
    embed(sys.argv[1])
    print(f"embedded project settings (outer brim 5mm, supports off) "
          f"into {sys.argv[1]}")
