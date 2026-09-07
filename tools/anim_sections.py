"""For each animation step: find the sample where two parts come CLOSEST,
then cut a cross-section there so the gap can be seen rather than trusted."""
import os, sys, json, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, trimesh, trimesh.collision as tc
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anim_audit import P, STEPS, AX, D, PARTS, pose, offsets, visible

COL = {"bar0":"#C2554B","bolt0":"#8B2820","bar1":"#3E7C99","bolt1":"#1F4E63",
       "bar2":"#5A8F4E","bolt2":"#2F5B26"}
N = 120
rows = []
for i, st in enumerate(STEPS):
    vis = sorted(visible(i))
    if len(vis) < 2: continue
    cm = tc.CollisionManager()
    for n in vis: cm.add_object(n, P[n])
    best = (1e9, None)
    for k in range(N + 1):
        u = k / N
        off = offsets(i, u)
        for n in vis: cm.set_transform(n, pose(n, off[n]))
        d = cm.min_distance_internal()
        if d < best[0]: best = (d, u)
    rows.append((i, st, best[0], best[1], vis))
    print(f"  step {i+1}: closest approach {best[0]:6.3f} mm at u={best[1]:.2f}"
          f"   ({'CONTACT' if best[0] <= 0 else 'clear'})")

fig, axes = plt.subplots(2, 3, figsize=(16, 9))
for ax, (i, st, dmin, u, vis) in zip(axes.ravel(), rows):
    off = offsets(i, u)
    li = st.get("line", 0)
    d, o = AX[li]
    # cut through the line this step works on, so the bore and bolt both show
    normal = np.cross(d, [0, 0, 1.0])
    if np.linalg.norm(normal) < 1e-6: normal = np.cross(d, [0, 1.0, 0])
    normal /= np.linalg.norm(normal)
    for n in vis:
        g = P[n].copy(); g.apply_transform(pose(n, off[n]))
        sec = g.section(plane_origin=o, plane_normal=normal)
        if sec is None: continue
        pl, _ = sec.to_2D()
        # outlines only: a filled section of one part drawn over another's
        # hole reads as interference when there is none
        for poly in pl.polygons_full:
            xy = np.array(poly.exterior.coords)
            ax.plot(xy[:,0], xy[:,1], color=COL[n], lw=1.5, zorder=2)
            for ring in poly.interiors:
                r = np.array(ring.coords)
                ax.plot(r[:,0], r[:,1], color=COL[n], lw=1.0, zorder=2)
    ax.set_aspect("equal"); ax.axis("off")
    ax.set_title(f"step {i+1}  u={u:.2f}   closest {dmin:.3f} mm", fontsize=10)
for ax in axes.ravel()[len(rows):]: ax.axis("off")
plt.tight_layout()
out = os.environ.get("SECTIONS_OUT", "sections.png")
plt.savefig(out, dpi=95, facecolor="#F2F2EE")
print("\nwrote", out)
