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

OUT_JSON = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "models", "knot_assembly.json")


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


def mesh_json(m, decimate=None):
    g = m
    if decimate and len(g.faces) > decimate:
        g = g.simplify_quadric_decimation(face_count=decimate)
    return {"v": [round(float(x), 3) for x in g.vertices.ravel()],
            "f": [int(x) for x in g.faces.ravel()]}


def build(thread=12.0):
    t = k.thread_for(thread)
    a = float(np.ceil(k.min_spacing(t, k.release(t))))
    slot = k.release(t)
    parts = k.assemble(t, a, entry="slot")
    d = {"thread_mm": thread, "a": a, "cube_mm": 2 * a, "slot_mm": slot,
         "head_h": t.head_h, "pocket_depth": k.pocket_depth(t),
         "head_af": t.hex_af, "pocket_af": 2 * k.pocket_cr(t)
         * float(np.cos(np.radians(30.0))), "lead": t.lead,
         "axes": [{"dir": list(map(float, dd)), "origin": list(map(float, oo))}
                  for dd, oo in k.lines(a)],
         "render": {}, "colliders": {}}
    for n, m in parts.items():
        d["render"][n] = mesh_json(m, decimate=12000)
    for i in range(3):
        d["colliders"][f"unit{i}"] = [mesh_json(p)
                                      for p in unit_collider(t, a, i, slot)]
    # The sequence, from an all-directions sweep of the real meshes rather
    # than from the axis-restricted search: every body pushed along 306
    # directions including the six exact axes, at a twentieth of a
    # millimetre, and the one that moves is the one that moves. Assembled,
    # exactly one does. Assembly is that read backwards.
    s = slot + 0.20
    d["steps"] = [
        {"unit": "unit2", "from": [0, 0, 0], "to": [0, 0, 0],
         "title": "Start with one unit",
         "text": "A unit is a bar with its own bolt threaded right through "
                 "it, eight turns, head standing 5 mm proud. Nothing in an "
                 "assembly that takes seconds separates those two, so treat "
                 "each as one rigid piece. There are three, and they are "
                 "identical but for one pocket."},
        {"unit": "unit1", "from": [0, 44, 0], "to": [0, 0, 0],
         "title": "Second unit, along its own bolt's axis",
         "text": "Its head goes into the first unit's pocket. Nothing is "
                 "clamped: the head simply sits in a blind hex socket, "
                 "which stops it turning and stops it moving sideways, and "
                 "does nothing at all against a pull."},
        {"unit": "unit0", "from": [s, 0, -44], "to": [s, 0, 0],
         "title": "Third unit, offset by the slot",
         "text": "It comes in held 5.9 mm off its final place, because its "
                 "own pocket has to drop over the second unit's head while "
                 "its bolt head still clears the first unit's pocket. This "
                 "is the step that cannot be done in the other order."},
        {"unit": "unit0", "from": [s, 0, 0], "to": [0, 0, 0],
         "title": "Slide it home — the lock",
         "text": "5.9 mm along its own axis, and the ring closes. Every "
                 "pocket now holds a head sideways, and every unit is "
                 "pinned by the next. This slide is the only motion the "
                 "finished object has, and finding it is the puzzle. Off "
                 "the axis by three degrees it jams at 2.4 mm."}]
    return d


if __name__ == "__main__":
    d = build()
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(d, f, separators=(",", ":"))
    tris = sum(len(v["f"]) // 3 for v in d["render"].values())
    hulls = sum(len(v) for v in d["colliders"].values())
    print(json.dumps({"ok": True, "file": os.path.basename(OUT_JSON),
                      "kb": round(os.path.getsize(OUT_JSON) / 1024),
                      "render_tris": tris, "convex_hulls": hulls,
                      "a": d["a"], "cube_mm": d["cube_mm"],
                      "slot_mm": round(d["slot_mm"], 2),
                      "steps": len(d["steps"])}))
