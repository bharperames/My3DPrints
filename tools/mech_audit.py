#!/usr/bin/env python3
"""Print-time mechanics audit: can each body survive being printed?

wobble_index(mesh): max over heights z of (grams of material above z) /
(cross-section area at z, mm^2). A tall mass on a thin neck wobbles under
nozzle drag; layers shift, bonding degrades, the part breaks free.

Field calibration (caged-ball prints, PLA on a P2S):
  FAILED  Ø28 ball on Ø2.4 pip: index ≈ 2.9  (total spaghetti)
  PRINTED Ø19 ball on Ø2.4 pip: index ≈ 0.8  (survived, marginal)
Threshold: reject above 1.0.
"""
import numpy as np
import trimesh

PLA_G_PER_MM3 = 1.24e-3


def wobble_index(mesh, step=1.0):
    lo, hi = mesh.bounds[0][2], mesh.bounds[1][2]
    zs = np.arange(lo + step, hi - step / 2, step)
    if not len(zs):
        return 0.0, None
    total = mesh.volume
    worst, worst_z = 0.0, None
    for z in zs:
        sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        if sec is None:
            continue
        try:
            p2, _ = sec.to_2D()
            area = sum(p.area for p in p2.polygons_full)
        except Exception:
            continue
        if area < 1e-6:
            continue
        # volume above z via slicing the volume integral (cheap approx:
        # sample sections upward is costly; use convexity-free exact split)
        above = float(mesh.slice_plane([0, 0, z], [0, 0, 1], cap=True).volume) \
            if hasattr(mesh, "slice_plane") else None
        if above is None:
            continue
        idx = above * PLA_G_PER_MM3 / area
        if idx > worst:
            worst, worst_z = idx, float(z)
    return round(worst, 2), worst_z


if __name__ == "__main__":
    import sys
    sc = trimesh.load(sys.argv[1], force="scene")
    for name, g in sc.geometry.items():
        w, z = wobble_index(g)
        print(f"{name}: wobble index {w}" + (f" (worst at z={z:.0f} mm)" if z else ""))
