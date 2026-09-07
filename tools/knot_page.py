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


def bolted_collider(t, a, i, keyed=True, gap=None, part="bar"):
    """Convex pieces for ONE part -- a bar or a bolt, not the two merged.

    They have to be separate bodies, because assembly moves them
    separately: a bolt goes in after its bars are already laid together.
    Merged, a step that says "insert the first bolt" drags a whole bar in
    with it and the object never reaches its own assembled pose.

    What re-ties them is the thread, which no convex decomposition can
    represent -- so the pull test locks each bolt to the bar it is threaded
    into with a constraint instead, which is what a thread does.

    The bar carries two cavities on one line, a through bore and a wider
    counterbore at the outer face, and a stepped hole is not convex. So the
    bar is cut at the counterbore floor and each slab decomposed against
    its own convex cavity, which is exact on both sides of the step.
    """
    import gen_bolted as B
    gap = B.FACE_GAP if gap is None else gap
    w = a / 2.0
    proud = B.proud_of(t) if (part == 'bolt' and i == 2) else 0.0
    x0 = B.datum(t, a, gap, proud)
    turn_i = np.linalg.matrix_power(k.CYCLE, i)
    CY = k.CYCLE @ k.CYCLE

    if part == "bolt":
        # head, the neck across the gap, and the threaded length that lies
        # inside its own bar
        hh = B.KEY_DEPTH + proud
        segs = [(trimesh.creation.extrude_polygon(t.hexagon(t.hex_cr),
                                                  hh), 0.0),
                (trimesh.creation.extrude_polygon(
                    ring_poly(t.major_r, 12),
                    max(0.05, (w + gap) - (x0 + hh))), hh),
                (trimesh.creation.extrude_polygon(
                    ring_poly(t.major_r, 12),
                    (a + w) - (w + gap)), (w + gap) - x0)]
        out = []
        for g, z in segs:
            g.apply_translation([0, 0, z])
            h = k.onto_x(g, (x0, a, 0)).convex_hull
            h.apply_transform(turn_i)
            out.append(h)
        return out

    box = B.bar_solid(a, w, gap)
    box = trimesh.creation.box(box.extents)
    box.apply_translation(B.bar_solid(a, w, gap).bounds.mean(axis=0))
    floor = (-a / 2.0) + B.pocket_depth(t)
    cav_c = trimesh.creation.extrude_polygon(
        t.hexagon(B.pocket_cr(t)) if keyed else ring_poly(B.pocket_cr(t), 16),
        B.pocket_depth(t) + 2.0)
    cav_c.apply_translation([0, 0, -2.0])
    cav_t = trimesh.creation.extrude_polygon(
        ring_poly(t.major_r + t.clearance, 12), 3 * a)
    cav_t.apply_translation([0, 0, -a])
    cav_c = k.onto_x(cav_c, (x0, a, 0)); cav_c.apply_transform(CY)
    cav_t = k.onto_x(cav_t, (x0, a, 0)); cav_t.apply_transform(CY)
    d = np.array(k.lines(a)[2][0], float)
    o = np.array(k.lines(a)[2][1], float) + d * floor
    pieces = []
    # the counterbore owns the OUTER slab, the through bore the rest
    for cav, keep in ((cav_c, -1), (cav_t, +1)):
        slab = box.slice_plane(o, d * keep, cap=True)
        if slab is None or not len(slab.vertices):
            continue
        pieces += convex_pieces(slab, cav)
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
        parts = B.assemble(t, a, entry=entry,
                           rounds=() if entry == "none" else (0,))
        d = {"design": design, "entry": entry, "thread_mm": thread, "a": a,
             "cube_mm": 2 * a, "slot_mm": 0.0, "head_h": t.head_h,
             "pocket_depth": B.pocket_depth(t), "head_af": t.hex_af,
             "pocket_af": 2 * B.pocket_cr(t) * float(np.cos(np.radians(30.0))),
             "lead": t.lead,
             "axes": [{"dir": list(map(float, dd)), "origin": list(map(float, oo))}
                      for dd, oo in k.lines(a)],
             "parts": sorted(parts), "colliders": {}}
        for i in range(3):
            d["colliders"][f"bar{i}"] = [
                mesh_json(p) for p in bolted_collider(
                    t, a, i, keyed=(entry == "none" or i != 0), part="bar")]
            d["colliders"][f"bolt{i}"] = [
                mesh_json(p) for p in bolted_collider(t, a, i, part="bolt")]
        # a thread is not a convex solid, so it is a constraint instead:
        # bolt i is threaded into bar i and cannot leave it
        d["threads"] = [[f"bolt{i}", f"bar{i}"] for i in range(3)]
        d["members"] = {f"bar{i}": [f"bar{i}"] for i in range(3)}
        d["members"].update({f"bolt{i}": [f"bolt{i}"] for i in range(3)})
        d["hold"] = [f"bar{i}" for i in range(3)]
        # The order the object has to be built in, and every step of it is
        # forced by one law the seed cube paid for twice: a head sunk in a
        # hex counterbore CANNOT TURN, so the bolt is never what you turn.
        # You drop the bolt into the block that keys it, and then you turn
        # the block it threads into -- or the block carrying it. The block
        # is the wrench.
        L = [np.asarray(x[0], float) for x in k.lines(a)]
        far = 2.6 * a
        diag = np.array([-1.0, -1.0, 0.0]) / np.sqrt(2.0)
        diag = np.array([-1.0, -1.0, 0.0]) / np.sqrt(2.0)
        BIG = 2.4 * a
        # Engagement in WHOLE LEADS, so a screw step ends on a whole number
        # of turns and the part lands square instead of a quarter turn off.
        eng = np.floor(a / t.lead) * t.lead
        park = 0.5 * t.lead                     # half a turn short of home
        d["steps"] = [
            {"parts": ["bar1"], "from": [0, 0, 0], "to": [0, 0, 0],
             "title": "Start with the blue bar",
             "text": "Three bars, four distinct parts. A threaded bore runs "
                     "the length of each; across it, a clearance bore with a "
                     "counterbore at the outer face. Colours are only so the "
                     "steps can name them."},
            {"parts": ["bolt0"], "from": list(-L[0] * BIG), "to": [0, 0, 0],
             "title": "Push the red bolt into the blue bar",
             "text": "Tip first, through the clearance bore until the head "
                     "seats. No turning: a hex head cannot be screwed into "
                     "its own keyway, since it arrives rotating and presents "
                     "the right sixth of a turn only once every sixty "
                     "degrees. The thread now stands out of the far face."},
            {"parts": ["bar0"], "from": list(L[0] * BIG),
             "to": list(L[0] * park), "screw": True, "spin": 1,
             "engage": eng, "line": 0,
             "title": "Turn the red bar on — but stop half a turn short",
             "text": "The bolt is keyed in the blue bar and cannot rotate, so "
                     "the red bar is the wrench. It is deliberately left two "
                     "millimetres proud: a bar swung about its own line "
                     "sweeps a 45 mm radius, and at home the red bar's body "
                     "sits exactly where the green bar needs to sweep. "
                     "Parked between a quarter and three quarters of a turn "
                     "short, it clears."},
            {"parts": ["bolt1"], "from": list(-L[1] * (BIG + 45.0)),
             "to": list(-L[1] * BIG), "show": ["bar2"],
             "title": "Drop the blue bolt into the green bar",
             "text": "Done off to one side while the green bar is still "
                     "loose in the hand. The head seats flush in its "
                     "hexagonal counterbore."},
            {"parts": ["bar2", "bolt1"], "from": list(-L[1] * BIG),
             "to": [0, 0, 0], "screw": True, "spin": -1,
             "engage": eng, "line": 1,
             "title": "Turn the green bar into the blue one",
             "text": "Bar and bolt turn together, keyed to each other, and "
                     "thread into the blue bar. This is the sweep the parked "
                     "red bar was making room for — measured, it is free "
                     "over the whole 28 mm, where with the red bar home it "
                     "jams after three."},
            {"parts": ["bar0"], "from": list(L[0] * park), "to": [0, 0, 0],
             "screw": True, "spin": 1, "engage": park, "line": 0,
             "title": "Swing the red bar down the last half turn",
             "text": "Now that the green bar is in, the red bar has room to "
                     "finish. Two millimetres, half a turn, and the three "
                     "bars are square."},
            {"parts": ["bolt2"], "from": list(-L[2] * BIG), "to": [0, 0, 0],
             "screw": True, "spin": -1, "engage": eng, "line": 2,
             "title": "The green bolt closes the ring, by hand",
             "text": "By now no bar can turn at all, so no bar can be the "
                     "wrench. This one counterbore is round rather than "
                     "hexagonal, so the bolt in it spins freely and can be "
                     "driven directly — and its head stands one thread lead "
                     "proud so fingers can reach it. It is the only turnable "
                     "thing in the finished object, the only way the ring "
                     "closes, and the only way back out."}]
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
    # a burr unit is a block and the bolt threaded through it, moving as one
    d["members"] = {f"unit{i}": [f"block{i}", f"bolt{i}"] for i in range(3)}
    d["threads"] = []
    d["hold"] = [f"unit{i}" for i in range(3)]
    # The burr's sequence, from an all-directions sweep of the real meshes:
    # every body pushed along 406 directions including the six exact axes,
    # at a twentieth of a millimetre. Assembled, exactly one moves.
    sl = slot + 0.20
    d["steps"] = [
        {"unit": "unit2", "from": [0, 0, 0], "to": [0, 0, 0],
         "title": "Start with one unit",
         "text": "A unit is a bar with its own bolt threaded through it, "
                 "head standing proud. There are three."},
        {"unit": "unit1", "from": [0, 44, 0], "to": [0, 0, 0],
         "title": "Second unit",
         "text": "Its head drops into the first unit's blind socket. "
                 "Nothing is clamped: the socket stops the head turning and "
                 "moving sideways, and does nothing against a pull."},
        {"unit": "unit0", "from": [sl, 0, -44], "to": [sl, 0, 0],
         "title": "Third unit, offset by the slot",
         "text": "It arrives held 5.9 mm off its final place, so its own "
                 "socket can drop over the second unit's head."},
        {"unit": "unit0", "from": [sl, 0, 0], "to": [0, 0, 0],
         "title": "Slide it home",
         "text": "5.9 mm, and the ring closes. This slide is the only "
                 "motion the finished object has \u2014 and it points the "
                 "same way you would pull, which is why half a newton takes "
                 "the whole thing apart."}]
    return d, parts


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", choices=("burr", "bolted"), default="bolted")
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
