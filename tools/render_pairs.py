#!/usr/bin/env python3
"""Render solid+spiral STL pairs side by side into thumbs dir."""
import numpy as np, trimesh, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

D = os.path.expanduser("~/Downloads/impossible-passthrough-pyramid-and-cone-style-hourglass-dubbel-size-also-helical-fidget-vortex-model_files")
THUMBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index_out", "thumbs")

PAIRS = [
    ("hourglass_cone", ["cone-solid-small.stl", "cone-spiral-small.stl", "cone-solid.stl", "cone-spiral.stl"]),
    ("hourglass_pyramid", ["pyramid-solid-small-fixed.stl", "pyramid-spiral-small.stl", "pyramid-solid.stl", "pyramid-spiral.stl"]),
]
# orange for solid, teal for spiral
BASE = {True: (0.95, 0.55, 0.25), False: (0.30, 0.75, 0.70)}

for slug, files in PAIRS:
    fig = plt.figure(figsize=(5.2, 3.9), dpi=100)
    ax = fig.add_subplot(111, projection="3d")
    x_off = 0.0
    bounds = []
    for f in files:
        m = trimesh.load(os.path.join(D, f))
        if len(m.faces) > 50000:
            idx = np.random.default_rng(0).choice(len(m.faces), 50000, replace=False)
            faces = m.faces[idx]
        else:
            faces = m.faces
        lo, hi = m.bounds
        m.apply_translation([x_off - lo[0], 0, -lo[2]])
        tris = m.vertices[faces]
        n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        nn = n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)
        light = np.array([0.45, 0.3, 0.85]); light /= np.linalg.norm(light)
        lum = 0.35 + 0.65 * np.clip(nn @ light, 0, 1)
        base = BASE["solid" in f]
        colors = np.stack([lum * base[0], lum * base[1], lum * base[2], np.ones_like(lum)], axis=1)
        ax.add_collection3d(Poly3DCollection(tris, facecolors=colors, edgecolors="none"))
        bounds.append(m.bounds)
        x_off += (hi[0] - lo[0]) + 12
    los = np.min([b[0] for b in bounds], axis=0); his = np.max([b[1] for b in bounds], axis=0)
    ctr = (los + his) / 2; span = (his - los).max() / 2
    ax.set_xlim(ctr[0]-span, ctr[0]+span); ax.set_ylim(ctr[1]-span, ctr[1]+span)
    ax.set_zlim(0, 2*span)
    ax.set_axis_off(); ax.view_init(elev=12, azim=-80)
    fig.savefig(os.path.join(THUMBS, slug + ".png"), bbox_inches="tight", pad_inches=0, transparent=True)
    plt.close(fig)
    print("rendered", slug)
