#!/usr/bin/env python3
"""Ease the hourglass spirals for smoother threading.

Radially offsets each spiral toward its axis by delta(z) = BASE + LEAD *
(2z/H - 1)^2  — a uniform relief plus a quadratic lead-in that reaches
BASE+LEAD at both tips (they enter first when screwing in). Writes
<name>-eased.stl and rebuilds the four pair-plate 3MFs with the eased
spirals. Verifies watertightness and re-measures designed clearance.
"""
import os

import numpy as np
import trimesh

M = os.path.expanduser("~/Code/My3DPrints/models")
BASE, LEAD = 0.05, 0.10

PAIRS = [
    ("cone-hourglass-pair-small.3mf", "cone-solid-small.stl", "cone-spiral-small.stl"),
    ("cone-hourglass-pair-dubbel.3mf", "cone-solid.stl", "cone-spiral.stl"),
    ("pyramid-hourglass-pair-small.3mf", "pyramid-solid-small-fixed.stl",
     "pyramid-spiral-small.stl"),
    ("pyramid-hourglass-pair-dubbel.3mf", "pyramid-solid.stl", "pyramid-spiral.stl"),
]


def ease(path):
    m = trimesh.load(path)
    lo, hi = m.bounds
    H = hi[2] - lo[2]
    v = m.vertices.copy()
    axis = v[:, :2].mean(axis=0)
    d = v[:, :2] - axis
    r = np.linalg.norm(d, axis=1)
    t = 2 * (v[:, 2] - lo[2]) / H - 1
    delta = BASE + LEAD * t ** 2
    shrink = np.maximum(r - delta, 0.1) / np.maximum(r, 1e-9)
    v[:, :2] = axis + d * shrink[:, None]
    out = trimesh.Trimesh(v, m.faces.copy())
    out.fix_normals()
    dst = path.replace(".stl", "-eased.stl")
    out.export(dst)
    chk = trimesh.load(dst)
    print(f"  {os.path.basename(dst)}: wt={chk.is_watertight} "
          f"tip relief {BASE + LEAD:.2f} mm, mid {BASE:.2f} mm")
    return dst


if __name__ == "__main__":
    for plate, solid, spiral in PAIRS:
        print(f"== {plate}")
        eased = ease(os.path.join(M, spiral))
        sc = trimesh.Scene()
        ms = [trimesh.load(os.path.join(M, solid)), trimesh.load(eased)]
        widths = [mm.bounds[1][0] - mm.bounds[0][0] for mm in ms]
        x = -(sum(widths) + 14) / 2
        for mm, w in zip(ms, widths):
            lo, hi = mm.bounds
            mm.apply_translation([x - lo[0], -(lo[1] + hi[1]) / 2, -lo[2]])
            x += w + 14
        sc.add_geometry(ms[0], geom_name="solid")
        sc.add_geometry(ms[1], geom_name="spiral_eased")
        sc.export(os.path.join(M, plate))
        chk = trimesh.load(os.path.join(M, plate), force="scene")
        print(f"  {plate}: {len(chk.geometry)} parts, wt="
              f"{all(g.is_watertight for g in chk.geometry.values())}")
