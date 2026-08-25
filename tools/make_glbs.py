#!/usr/bin/env python3
"""Export decimated, colored GLB previews + manifest for the local viewer."""
import json, os
import numpy as np
import trimesh

MODELS = os.path.expanduser("~/Code/My3DPrints/models")
OUT = os.path.join(MODELS, "glb")
os.makedirs(OUT, exist_ok=True)

PALETTE = [(233, 122, 60), (64, 160, 150), (108, 130, 200), (212, 170, 66),
           (170, 100, 170), (100, 170, 90), (200, 90, 100), (90, 150, 200)]

# (glb_slug, source file, family, display name)
ITEMS = [
 ("held_sphere", "held-sphere.3mf", "Designed here", "Held sphere (captive ball)"),
 ("chain_test", "chain-test-5seg.3mf", "Designed here", "Chain test — 5 links"),
 ("voro_fixed", "voro_sphere_2-fixed.stl", "One-off Experiments", "Voronoi sphere (fixed)"),
 ("nuts_bolts", "montessori+nuts+and+bolts.3mf", "Nuts & Bolts", "Montessori nuts & bolts"),
 ("c_shape", "c-shape copy 16.stl", "One-off STLs", "C-shape (copy 16)"),
 ("remesh_avg", "remesh_averaged_model_thresh0.900.stl", "One-off STLs", "Averaged remesh"),
 ("voro_sphere", "voro_sphere_2.stl", "One-off STLs", "Voronoi sphere"),
 ("pufferfish_threeplates", "pufferfish-p2s-threeplates.3mf", "Pufferfish", "Pufferfish (3-plate re-save)"),
 ("pufferfish_onecolor", "pufferfish-p2s-onecolor.3mf", "Pufferfish", "Pufferfish (one-color re-save)"),
 ("cone_pair_small", ["cone-solid-small.stl", "cone-spiral-small.stl"], "Hourglass · Cone", "Cone pair · 90 mm"),
 ("cone_pair_dubbel", ["cone-solid.stl", "cone-spiral.stl"], "Hourglass · Cone", "Cone pair · dubbel 180 mm"),
 ("pyramid_pair_small", ["pyramid-solid-small-fixed.stl", "pyramid-spiral-small.stl"], "Hourglass · Pyramid", "Pyramid pair · 90 mm (fixed)"),
 ("pyramid_pair_dubbel", ["pyramid-solid.stl", "pyramid-spiral.stl"], "Hourglass · Pyramid", "Pyramid pair · dubbel 180 mm"),
 ("pyramid_solid_small_orig", "pyramid-solid-small.stl", "Hourglass · Pyramid", "Pyramid solid · 90 mm (orig, pinch)"),
 ("sphere_stand_1in", "sphere_stand_1.0in.3mf", "Sphere Stands", "1″ sphere stand"),
 ("sphere_stand_2in", "sphere_stand_2.0in.3mf", "Sphere Stands", "2″ sphere stand"),
 ("sphere_stand_3in", "sphere_stand_3.0in.3mf", "Sphere Stands", "3″ sphere stand"),
 ("vortex_v3", "Vortex+v3+project.3mf", "Vortex v3", "Vortex v3 (3 sleeves)"),
 ("mini_fidget_ball", "Mini+Fidget+Ball.3mf", "Passthrough series", "Mini Fidget Ball"),
 ("mini_stackable", "Mini+Stackable+Supports+added+back+in.3mf", "Passthrough series", "Mini Stackable tube"),
 ("spinning_top", "magic_spinning_top_+23+de+fight+d.3mf", "Spinning Top", "Magic spinning top"),
 ("quantum_skull", "Quantum+Skull.3mf", "Quantum Skull", "Quantum Skull halves"),
 ("pufferfish", "pufferfish.3mf", "Pufferfish", "Pufferfish (all parts)"),
 ("pikachu", "pikachu+more+resistant+one+color.3mf", "Pikachu Flexy", "Pikachu flexy keychain"),
 ("staryu_starmie", "Staryu_Starmie_Spin_Spin.3mf", "Staryu & Starmie", "Both spinners + hardware"),
 ("cone_solid_small", "cone-solid-small.stl", "Hourglass · Cone", "Cone solid · 90 mm"),
 ("cone_spiral_small", "cone-spiral-small.stl", "Hourglass · Cone", "Cone spiral · 90 mm"),
 ("cone_solid", "cone-solid.stl", "Hourglass · Cone", "Cone solid · dubbel 180 mm"),
 ("cone_spiral", "cone-spiral.stl", "Hourglass · Cone", "Cone spiral · dubbel 180 mm"),
 ("pyramid_solid_small_fixed", "pyramid-solid-small-fixed.stl", "Hourglass · Pyramid", "Pyramid solid · 90 mm (fixed)"),
 ("pyramid_spiral_small", "pyramid-spiral-small.stl", "Hourglass · Pyramid", "Pyramid spiral · 90 mm"),
 ("pyramid_solid", "pyramid-solid.stl", "Hourglass · Pyramid", "Pyramid solid · dubbel 180 mm"),
 ("pyramid_spiral", "pyramid-spiral.stl", "Hourglass · Pyramid", "Pyramid spiral · dubbel 180 mm"),
]
BUDGET = 180_000

manifest = []
for slug, fname, family, label in ITEMS:
    fnames = fname if isinstance(fname, list) else [fname]
    meshes = []
    for fn in fnames:
        scene = trimesh.load(os.path.join(MODELS, fn), force="scene")
        for node in scene.graph.nodes_geometry:
            tf, gname = scene.graph[node]
            g = scene.geometry[gname]
            if isinstance(g, trimesh.Trimesh) and len(g.faces):
                gm = g.copy(); gm.apply_transform(tf); meshes.append(gm)
    fname = " + ".join(fnames)
    total = sum(len(m.faces) for m in meshes)
    # compact display layout: re-pack multi-part models into wrapped rows
    if len(meshes) > 1 and slug not in ("held_sphere", "chain_test"):
        GAP = 6.0
        widths = [(m.bounds[1][0] - m.bounds[0][0]) for m in meshes]
        target_w = max(max(widths) + GAP,
                       (sum((w + GAP) for w in widths)) ** 0.5 * ((max(
                           (m.bounds[1][1] - m.bounds[0][1]) for m in meshes) + GAP) ** 0.5))
        x = y = row_d = 0.0
        for m in meshes:
            lo, hi = m.bounds
            w, dep = hi[0] - lo[0], hi[1] - lo[1]
            if x > 0 and x + w > target_w:
                x = 0.0; y += row_d + GAP; row_d = 0.0
            m.apply_translation([x - lo[0], y - lo[1], -lo[2]])
            x += w + GAP; row_d = max(row_d, dep)
    out_scene = trimesh.Scene()
    tri_out = 0
    for i, m in enumerate(meshes):
        if total > BUDGET:
            target = max(500, int(len(m.faces) * BUDGET / total))
            if target < len(m.faces):
                try:
                    m = m.simplify_quadric_decimation(face_count=target)
                except BaseException:
                    pass
        c = PALETTE[i % len(PALETTE)]
        m.visual = trimesh.visual.ColorVisuals(m, face_colors=(*c, 255))
        tri_out += len(m.faces)
        out_scene.add_geometry(m, node_name=f"part_{i}")
    # center on origin, floor at z=0
    b = out_scene.bounds
    ctr = (b[0] + b[1]) / 2
    for gname in list(out_scene.geometry):
        out_scene.geometry[gname].apply_translation([-ctr[0], -ctr[1], -b[0][2]])
    glb = os.path.join(OUT, slug + ".glb")
    out_scene.export(glb)
    ext = out_scene.bounds[1] - out_scene.bounds[0]
    manifest.append(dict(slug=slug, file=fname, family=family, label=label,
        parts=len(meshes), tris=tri_out, tris_full=total,
        dims=[round(float(x), 1) for x in ext],
        glb_mb=round(os.path.getsize(glb) / 1e6, 1)))
    print(f"{slug:28s} {total:>9,d} -> {tri_out:>8,d} tris  {manifest[-1]['glb_mb']} MB")

with open(os.path.join(MODELS, "manifest.json"), "w") as f:
    json.dump(manifest, f, indent=1)
print("manifest written:", len(manifest), "entries")
