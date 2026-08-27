#!/usr/bin/env python3
"""Embed Bambu Studio project settings into a generated 3MF.

A trimesh-exported 3MF is geometry-only; Studio applies whatever presets the
user last touched (brim Auto often skips the brim these models need). This
injects Metadata/project_settings.config — the flattened P2S machine +
process + filament presets plus our overrides — so the file opens (and CLI-
slices) with the intended settings baked in.
"""
import json
import os
import sys
import zipfile

PRESETS = os.path.expanduser(
    "~/Library/Application Support/BambuStudio/system/BBL")
MACHINE = "Bambu Lab P2S 0.4 nozzle"
PROCESS = "0.20mm Standard @BBL P2S"
FILAMENT = "Bambu PLA Basic @BBL P2S"
META_KEYS = {"type", "name", "inherits", "from", "instantiation",
             "setting_id", "filament_id", "info_file"}


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


def embed(path, overrides=None):
    cfg = {}
    cfg.update(flatten("filament", FILAMENT))
    cfg.update(flatten("machine", MACHINE))
    cfg.update(flatten("process", PROCESS))
    cfg.update({
        "printer_settings_id": MACHINE,
        "print_settings_id": PROCESS,
        "filament_settings_id": [FILAMENT],
        "curr_bed_type": "Textured PEI Plate",
        "brim_type": "outer_only",
        "brim_width": "5",
        "brim_object_gap": "0.1",
    })
    cfg.update(overrides or {})
    # Bambu only reads project_settings.config from archives stamped as its
    # own projects: the model XML needs the BambuStudio namespace + version
    # metadata. Rebuild the zip with the stamp and the config.
    with zipfile.ZipFile(path) as z:
        items = {n: z.read(n) for n in z.namelist()}
    mdl = items["3D/3dmodel.model"].decode("utf-8")
    if "BambuStudio:3mfVersion" not in mdl:
        i = mdl.index("<model ")
        j = mdl.index(">", i)
        if "xmlns:BambuStudio" not in mdl:
            mdl = (mdl[:j] +
                   ' xmlns:BambuStudio="http://schemas.bambulab.com/'
                   'package/2021"' + mdl[j:])
            j = mdl.index(">", i)
        mdl = (mdl[:j + 1] +
               '<metadata name="Application">BambuStudio-02.02.02</metadata>'
               '<metadata name="BambuStudio:3mfVersion">1</metadata>' +
               mdl[j + 1:])
    # a project trusts stored placement: move build items from the origin
    # corner to the plate center
    pa = cfg.get("printable_area", ["0x0", "256x0", "256x256", "0x256"])
    xs = [float(p.split("x")[0]) for p in pa]
    ys = [float(p.split("x")[1]) for p in pa]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    mdl = mdl.replace(
        'transform="1.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0"',
        f'transform="1 0 0 0 1 0 0 0 1 {cx:g} {cy:g} 0"')
    items["3D/3dmodel.model"] = mdl.encode("utf-8")
    items["Metadata/project_settings.config"] = json.dumps(
        cfg, indent=1).encode("utf-8")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in items.items():
            z.writestr(n, data)


if __name__ == "__main__":
    embed(sys.argv[1])
    print(f"embedded P2S settings (brim outer 5mm) into {sys.argv[1]}")
