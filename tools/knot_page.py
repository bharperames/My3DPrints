#!/usr/bin/env python3
"""Data for the Knot's assembly page: real meshes to look at, convex solids
to simulate with, and the sequence to drive.

Two representations of the same object, and the page must never confuse
them. What you SEE is the generated mesh, bores, thread and all. What the
solver feels is a set of convex pieces, because that is the only thing a
rigid-body engine can collide reliably -- cannon-es's own Trimesh shape
collides with spheres and planes and nothing else.

The decomposition is exact rather than approximate, which matters: a
V-HACD hull would round off the pocket mouth by a few tenths and the
0.25 mm keying fit would stop meaning anything. A block is a box with one
convex prism cut out of it, and

    box minus convex prism  =  union over the prism's faces of
                               (box on the outer side of that face)

each of which is a box cut by a plane, and so convex by construction. Six
pocket walls and the slab under the floor cover the block exactly, with no
gaps and no rounding. The pieces overlap along their shared planes, which
costs a contact pair and changes nothing.

A bolt is threaded eight turns into its own block. Nothing in an assembly
that takes seconds can separate them, so each block and its bolt are ONE
rigid body -- a unit -- and the thread is not simulated at all. Unscrewing
is a separate motion the page animates rather than solves.
"""
import json
import os
import sys

import numpy as np
import trimesh
from shapely.geometry import Polygon

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_knot as k                                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def out_paths(design):
    tag = "" if design == "burr" else "_" + design
    return (os.path.join(ROOT, "models", f"knot{tag}_assembly.json"),
            os.path.join(ROOT, "models", "glb", f"knot{tag}_assembly.glb"))


def _dedupe_planes(hull, tol=1e-4):
    """One plane per facet, not one per triangle."""
    out = []
    for n, c in zip(hull.face_normals, hull.triangles_center):
        d = float(n @ c)
        if not any(abs(d - d2) < tol and n @ n2 > 1 - tol for n2, d2 in out):
            out.append((n, d))
    return out


def convex_pieces(box, cavity):
    """`box` minus the convex `cavity`, as a list of convex meshes."""
    pieces = []
    for n, d in _dedupe_planes(cavity.convex_hull):
        p = box.slice_plane(n * d, n, cap=True)
        if p is not None and len(p.vertices) and p.volume > 1.0:
            pieces.append(p.convex_hull)
    return pieces


def pocket_prism(t, a, slot, gap=k.FACE_GAP):
    """The pocket cut, in block 0's world frame — the same construction
    `gen_knot.block` uses, so it is the same solid and not a copy of it."""
    from shapely import affinity
    from shapely.geometry import MultiPolygon
    hexp = t.hexagon(k.pocket_cr(t))
    if slot > 0:
        hexp = MultiPolygon([hexp, affinity.translate(hexp, 0, -slot)]) \
            .convex_hull
    pk = trimesh.creation.extrude_polygon(hexp, k.pocket_depth(t) + 2.0)
    pk = k.onto_x(pk, (k.datum(t, a, gap), a, 0))
    pk.apply_transform(k.CYCLE @ k.CYCLE)
    return pk


def unit_collider(t, a, i, slot, gap=k.FACE_GAP):
    """One unit's convex pieces: the block around its pocket, plus the head
    of its own bolt, which stands proud and is what the next pocket holds."""
    w = a / 2.0
    lo = np.array([w + gap, -w, -w])
    hi = np.array([a + w, a + w, w - gap])
    box = trimesh.creation.box(hi - lo)
    box.apply_translation((lo + hi) / 2.0)
    pieces = convex_pieces(box, pocket_prism(t, a, slot if i == 0 else 0.0,
                                             gap))
    pieces += head_collider(t, a, gap)
    turn = np.linalg.matrix_power(k.CYCLE, i)
    for p in pieces:
        p.apply_transform(turn)
    return pieces


def head_collider(t, a, gap=k.FACE_GAP):
    """The proud head and its exposed neck, as solids containing the real ones.

    Hulling the generated head gives 539 vertices -- it is a hexagon
    intersected with a 192-section barrel and the hull keeps every corner
    facet -- and convex-convex SAT against that runs the simulation at a
    twentieth of real time. The shortcut has to go the right way, though,
    and twice it did not. Shrinking the end rings to the chamfer's
    circumradius pulls the FLATS in by 0.7 mm; so does cutting a 45 degree
    chamfer plane. Both leave a hundred cubic millimetres of real head
    outside its own collider, which is a simulation looser than the part.

    The head's chamfer takes its CORNERS off, not its flats: the barrel
    that makes it closes to just inside the corner circle and never reaches
    the flats at all. So the honest cheap solid is the full hexagonal
    prism, which contains the head exactly and is twelve vertices. It loses
    the lead-in at the pocket mouth, which can only make the simulation
    fussier about entry than the print will be.
    """
    x0 = k.datum(t, a, gap) + k.AXIAL_SLACK
    head = trimesh.creation.extrude_polygon(t.hexagon(t.hex_cr), t.head_h)
    # and the length of shank between the head and the block's face, which
    # spans the gap between two blocks and is inside neither the block's box
    # nor the head. Left out, seventy-five cubic millimetres of real bolt
    # had no collider at all, in exactly the place two blocks meet.
    span = (a / 2.0 + gap) - (x0 + t.head_h)
    ang = np.radians(np.arange(12) * 30.0 + 15.0)
    r = t.major_r / np.cos(np.radians(15.0))     # circumscribed, so it is
    ring = Polygon(np.column_stack([r * np.cos(ang), r * np.sin(ang)]))
    neck = trimesh.creation.extrude_polygon(ring, span + 0.02)
    neck.apply_translation([0, 0, t.head_h - 0.01])
    return [k.onto_x(g, (x0, a, 0)) for g in (head, neck)]


def mesh_json(m):
    """Colliders only. They are boxes and prisms of a couple of dozen
    vertices, so they go in the JSON; the parts themselves ship as a GLB at
    full resolution, because a decimated thread is a different thread."""
    return {"v": [round(float(x), 4) for x in m.vertices.ravel()],
            "f": [int(x) for x in m.faces.ravel()]}


def ring_poly(r, n=12):
    """A polygon that CONTAINS the circle of radius r.

    For a HOLE that is the loose direction: the modelled bore is a couple of
    tenths wider than the real one at the polygon corners, so a shank has
    more room in the simulation than in the print. For a "does it hold"
    test that is the safe way to be wrong.
    """
    from shapely.geometry import Polygon
    ang = np.radians(np.arange(n) * (360.0 / n) + 180.0 / n)
    R = r / np.cos(np.pi / n)
    return Polygon(np.column_stack([R * np.cos(ang), R * np.sin(ang)]))


def bolted_collider(t, a, i, keyed=True, gap=None):
    """One clamped unit: the bar, hollowed for the bolt that passes through
    it, plus the head and shank of its own bolt where they stand outside.

    The bar carries two cavities on one line -- a through bore and a wider
    counterbore at the outer face -- and a stepped hole is not convex. So
    the bar is cut at the counterbore floor and each slab is decomposed
    against its own convex cavity, which is exact on both sides of the step.
    """
    import gen_bolted as B
    gap = B.FACE_GAP if gap is None else gap
    w = a / 2.0
    x0 = B.datum(t, a, gap)
    box = B.bar_solid(a, w, gap).bounding_box_oriented.copy()
    box = trimesh.creation.box(B.bar_solid(a, w, gap).extents)
    box.apply_translation(B.bar_solid(a, w, gap).bounds.mean(axis=0))

    floor = x0 + B.pocket_depth(t) - B.AXIAL_SLACK      # counterbore floor
    # exactly the real counterbore depth, over-run OUTWARD only: run it 2 mm
    # deeper instead and the collider loses material the bar really has,
    # right where the head bears
    cav_c = trimesh.creation.extrude_polygon(
        t.hexagon(B.pocket_cr(t)) if keyed else ring_poly(B.pocket_cr(t), 16),
        B.pocket_depth(t) + 2.0)
    cav_c.apply_translation([0, 0, -B.AXIAL_SLACK - 2.0])
    cav_t = trimesh.creation.extrude_polygon(
        ring_poly(t.major_r + t.clearance, 12), 3 * a)
    cav_t.apply_translation([0, 0, -a])
    turn = CY = k.CYCLE @ k.CYCLE
    cav_c = k.onto_x(cav_c, (x0, a, 0)); cav_c.apply_transform(CY)
    cav_t = k.onto_x(cav_t, (x0, a, 0)); cav_t.apply_transform(CY)
    # the step plane, in world coords, normal along the previous line
    d = np.array(k.lines(a)[2][0], float)
    o = np.array(k.lines(a)[2][1], float) + d * floor

    pieces = []
    # The counterbore is the OUTER end of the hole and the through bore is
    # the rest, so the counterbore takes the slab on the outer side of the
    # step. Swapped, each cavity is cut out of the slab it does not live in
    # and the bore stays full of material -- three cubic centimetres of
    # collider sitting exactly where the next unit's shank has to pass.
    for cav, keep in ((cav_c, -1), (cav_t, +1)):
        slab = box.slice_plane(o, d * keep, cap=True)
        if slab is None or not len(slab.vertices):
            continue
        pieces += convex_pieces(slab, cav)
    # this unit's own bolt, outside its bar: head and the shank beyond it
    blt = B.bolt(t, a, gap)
    face = np.array(k.lines(a)[0][1], float)
    out = blt.slice_plane([w + gap, a, 0], [-1, 0, 0], cap=True)
    if out is not None and len(out.vertices):
        # at x0, the same datum the bolt itself is built on. Offsetting the
        # collider head by one AXIAL_SLACK left the bottom 0.15 mm of every
        # head outside its own collider -- 35 mm3, exactly where the head
        # bears on the counterbore floor and takes the whole pull.
        head = trimesh.creation.extrude_polygon(t.hexagon(t.hex_cr), t.head_h)
        pieces.append(k.onto_x(head, (x0, a, 0)).convex_hull)
        neck = trimesh.creation.extrude_polygon(
            ring_poly(t.major_r, 12), (w + gap) - (x0 + t.head_h))
        neck.apply_translation([0, 0, t.head_h])
        pieces.append(k.onto_x(neck, (x0, a, 0)).convex_hull)
    turn_i = np.linalg.matrix_power(k.CYCLE, i)
    out = []
    for p in pieces:
        h = p.convex_hull
        h.apply_transform(turn_i)
        out.append(h)
    return out


def build(thread=12.0, design="burr", entry=None):
    if design == "bolted":
        import gen_bolted as B
        t = B.thread_for(thread)
        a = float(np.ceil(B.min_spacing(t)))
        entry = entry or "free"
        parts = B.assemble(t, a, entry=entry)
        d = {"design": design, "entry": entry, "thread_mm": thread, "a": a,
             "cube_mm": 2 * a, "slot_mm": 0.0, "head_h": t.head_h,
             "pocket_depth": B.pocket_depth(t), "head_af": t.hex_af,
             "pocket_af": 2 * B.pocket_cr(t) * float(np.cos(np.radians(30.0))),
             "lead": t.lead,
             "axes": [{"dir": list(map(float, dd)), "origin": list(map(float, oo))}
                      for dd, oo in k.lines(a)],
             "parts": sorted(parts), "colliders": {}}
        for i in range(3):
            d["colliders"][f"unit{i}"] = [
                mesh_json(p) for p in
                bolted_collider(t, a, i, keyed=(entry == "none" or i != 0))]
        # The order the object has to be built in, and it is forced. Bars go
        # together first, because a bolt can only be tightened while
        # something is still free to turn; the last bolt closes the ring and
        # after that nothing turns at all.
        L = [np.asarray(x[0], float) for x in k.lines(a)]
        far = 2.4 * a
        d["steps"] = [
            {"unit": "bar0", "from": [0, 0, 0], "to": [0, 0, 0],
             "title": "One bar",
             "text": "Three of these, identical but for one counterbore. "
                     "Each has a threaded bore down its own length and, "
                     "across it, a clearance bore with a counterbore at the "
                     "outer face."},
            {"unit": "bar1", "from": list(-L[0] * far), "to": [0, 0, 0],
             "title": "Second bar, face to face",
             "text": "Nothing holds them together yet. They only meet on one "
                     "plane, so the second bar slides straight up to the "
                     "first."},
            {"unit": "bolt0", "from": list(-L[0] * far), "to": [0, 0, 0],
             "screw": True,
             "title": "First bolt — right through",
             "text": "Through the second bar's clearance bore and into the "
                     "first bar's thread. This is the joint the burr never "
                     "had: the bolt does not stop in a socket, it passes "
                     "through one bar and bites the next, so a pull loads a "
                     "thread instead of sliding a head out of a hole."},
            {"unit": "bar2", "from": list(-L[1] * far), "to": [0, 0, 0],
             "title": "Third bar",
             "text": "Laid against the second. Still free — nothing is "
                     "clamped to it yet."},
            {"unit": "bolt1", "from": list(-L[1] * far), "to": [0, 0, 0],
             "screw": True,
             "title": "Second bolt",
             "text": "Turned by holding the third bar, which is keyed to the "
                     "head by its hexagonal counterbore. That is the trick "
                     "the seed cube taught: the block IS the wrench."},
            {"unit": "bolt2", "from": list(-L[2] * far), "to": [0, 0, 0],
             "screw": True,
             "title": "Last bolt — the ring closes",
             "text": "By now no bar can turn, so this one cannot be driven "
                     "by a bar. Its counterbore is round rather than "
                     "hexagonal, so the bolt itself turns freely and can be "
                     "driven directly. Once home, every bar is clamped to "
                     "the next and nothing moves: measured, 0.7 mm of play "
                     "under two newtons of pull. Undoing it means finding "
                     "which one of three identical faces has the bolt that "
                     "turns."}]
        return d, parts
    t = k.thread_for(thread)
    a = float(np.ceil(k.min_spacing(t, k.release(t))))
    slot = k.release(t)
    parts = k.assemble(t, a, entry="slot")
    d = {"design": design, "thread_mm": thread, "a": a, "cube_mm": 2 * a,
         "slot_mm": slot, "head_h": t.head_h,
         "pocket_depth": k.pocket_depth(t),
         "head_af": t.hex_af, "pocket_af": 2 * k.pocket_cr(t)
         * float(np.cos(np.radians(30.0))), "lead": t.lead,
         "axes": [{"dir": list(map(float, dd)), "origin": list(map(float, oo))}
                  for dd, oo in k.lines(a)],
         "parts": sorted(parts), "colliders": {}}
    for i in range(3):
        d["colliders"][f"unit{i}"] = [mesh_json(p)
                                      for p in unit_collider(t, a, i, slot)]
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", choices=("burr", "bolted"), default="burr")
    ap.add_argument("--entry")
    ap.add_argument("--thread", type=float, default=12.0)
    A = ap.parse_args()
    OUT_JSON, OUT_GLB = out_paths(A.design)
    d, parts = build(A.thread, A.design, A.entry)
    for path in (OUT_JSON, OUT_GLB):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(d, f, separators=(",", ":"))
    sc = trimesh.Scene()
    for n, m in sorted(parts.items()):
        sc.add_geometry(m, geom_name=n, node_name=n)
    sc.export(OUT_GLB)
    tris = sum(len(m.faces) for m in parts.values())
    hulls = sum(len(v) for v in d["colliders"].values())
    print(json.dumps({"ok": True, "design": A.design,
                      "json_kb": round(os.path.getsize(OUT_JSON) / 1024),
                      "glb_kb": round(os.path.getsize(OUT_GLB) / 1024),
                      "render_tris": tris, "convex_hulls": hulls,
                      "a": d["a"], "cube_mm": d["cube_mm"]}))
