#!/usr/bin/env python3
"""Flexi Factory's skeleton T-Rex, with a gum trough instead of teeth.

NOT this project's geometry. Flexi Factory's model is paid for and stays in
Brett's ~/Downloads; nothing here is copied into the repo. This reads the
file he owns and writes a derivative for his own printer, which is what the
generator exists to do -- it refuses with a clear message if the source is
not on disk.

WHAT THE PAINT GIVES US

The designer painted the teeth and the paint ships in the 3MF: one
`paint_color` attribute per triangle, '8' for teeth and claws and '4' for
bone. So which triangles are a tooth is the author's own answer, not a
detector's guess, and every tooth arrives complete down to the ring where it
meets the jaw. That is worth knowing because the obvious readings are both
wrong: the head is a single watertight body, so the teeth are not separate
objects, and a curvature detector finds 18 cones on the skull where the
author painted 14.

THE TROUGH, AND WHY IT IS NOT FIFTY SOCKETS

Brett's idea, and a better one than the sockets first tried: one channel
following the gum line, which small tooth roots can be set anywhere along
and bedded in black epoxy. It is also far more robust to build -- individual
mirrored sockets failed on 4 of 14 teeth and shattered the skull into
fragments, where the channel is a single continuous cut.

IT HAS TO BE CENTRED ON THE BONE, NOT ON THE TEETH

Measured on this skull, the teeth sit 0.88 mm outboard of the middle of the
jaw ridge, and the ridge is only 6.13 mm wide (4.99 at its narrowest). A
3.5 mm trough centred on the tooth positions breaks through the palate for
81% of its length. Centred on the ridge instead, the same 3.5 mm clears
everywhere but 2% of samples, and the finished skull's thinnest wall is
0.40 mm -- exactly what the untouched skull already had, so the trough takes
nothing away from what the designer shipped.

THE CLAWS STAY ON, AND THAT IS DELIBERATE

The same treatment was built for the foot talons and the hand claws and then
taken back out. The foot talons are what the model stands on -- cut them and
he does not stand up -- and the hand claws are small enough that swapping
them for real ones buys little. The paint marks them, so they are easy to
find again if that ever changes; the reason not to is mechanical, not
technical.
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SRC = os.path.expanduser(
    "~/Downloads/FlexiFactory/Flexi Factory Skeleton T-Rex_stls_all/"
    "Bambu Flexi Factory Skeleton T-Rex_Curved.3mf")

OBJ = {
    "bone":   "3D/Objects/Flexi Factory Skeleton T-Rex bone.stl_43.model",
    "head":   "3D/Objects/Flexi Factory Skeleton T-Rex Head without Eye.stl_46.model",
    "eyes":   "3D/Objects/Flexi Factory Skeleton T-Rex Head with Eye.stl_45.model",
    "body":   "3D/Objects/Flexi Factory Skeleton T-Rex Body_Curved.stl_47.model",
}

PARTS = {
    "bone":    ("bone",  False, "the loose bone that comes with the set"),
    "head":    ("head",  False, "the eyeless skull as the designer drew it"),
    "eyes":    ("eyes",  False, "the skull with eyes"),
    "trough":  ("head",  True,  "the eyeless skull with a gum trough for real teeth"),
    "body":    ("body",  False, "the body, claws and jaw untouched"),
}

TOOTH_PAINT = "8"
WIDTH, DEPTH = 3.5, 3.0


def load(member):
    from paint import read
    if not os.path.exists(SRC):
        raise SystemExit(json.dumps({
            "ok": False,
            "error": f"source model not found: {SRC}. This derives from Flexi "
                     f"Factory's paid model, which is not redistributed here."}))
    V, F, P = read(SRC, member)
    return trimesh.Trimesh(V, F, process=False), P


def keep_real(mesh, floor=1.0):
    """Drop the boolean's zero-volume debris, keep every real part.

    The body is twenty-five separate pieces by design, so taking the largest
    component would throw the animal away and leave the rib cage.
    """
    parts = [p for p in mesh.split(only_watertight=False) if p.volume > floor]
    return trimesh.util.concatenate(parts) if parts else mesh


def trough(mesh, paint, width=WIDTH, depth=DEPTH):
    from channel import tooth_frames, channel
    idx = np.where(paint == TOOTH_PAINT)[0]
    lab = trimesh.graph.connected_component_labels(
        trimesh.graph.face_adjacency(mesh.faces[idx]), node_count=len(idx))
    regions = [idx[lab == r] for r in range(lab.max() + 1)]
    # a tooth is a cone, so its own convex hull is the tooth
    cuts = [mesh.submesh([r], append=True).convex_hull for r in regions]
    cuts += channel(mesh, tooth_frames(mesh, regions),
                    width=width, depth=depth, over=1.0, centre=True)
    u = trimesh.boolean.union(cuts, engine="manifold")
    return keep_real(trimesh.boolean.difference([mesh, u], engine="manifold")), len(regions)


def build(names, width=WIDTH, depth=DEPTH):
    out, rep = [], {}
    for name in names:
        member, cut, _ = PARTS[name]
        m, paint = load(OBJ[member])
        n = 0
        if cut:
            m, n = trough(m, paint, width, depth)
        out.append((name, m))
        rep[name] = dict(faces=len(m.faces), volume=round(float(m.volume), 1),
                         teeth_removed=n)
    return out, rep


def layout(items, gap=4.0):
    """Lay the chosen parts out in a row on the bed, largest first."""
    items = sorted(items, key=lambda kv: -kv[1].extents[0] * kv[1].extents[1])
    sc, x = trimesh.Scene(), 0.0
    for name, m in items:
        g = m.copy()
        g.apply_translation(-g.bounds[0])
        g.apply_translation([x, 0, 0])
        sc.add_geometry(g, geom_name=f"trex_{name}")
        x += g.extents[0] + gap
    return sc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", default="trough,body",
                    help="comma-separated: " + ", ".join(PARTS))
    ap.add_argument("--width", type=float, default=WIDTH,
                    help="gum trough width (mm)")
    ap.add_argument("--depth", type=float, default=DEPTH,
                    help="gum trough depth (mm)")
    ap.add_argument("--out")
    a = ap.parse_args()
    names = [p.strip() for p in a.parts.split(",") if p.strip()]
    bad = [n for n in names if n not in PARTS]
    if bad:
        print(json.dumps({"ok": False, "error": f"unknown part(s): {bad}. "
                                                f"choose from {list(PARTS)}"}))
        return 1
    items, rep = build(names, a.width, a.depth)
    sc = layout(items)
    out = a.out or os.path.join(os.path.dirname(HERE), "models", "custom",
                                "trex-" + "-".join(names) + ".3mf")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sc.export(out)
    ext = sc.extents
    print(json.dumps({"ok": True, "parts": names, "file": os.path.basename(out),
                      "span": [round(float(ext[0]), 1), round(float(ext[1]), 1)],
                      "height": round(float(ext[2]), 1),
                      "single_colour": True, "detail": rep}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
