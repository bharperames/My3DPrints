#!/usr/bin/env python3
"""Companion parts for the Montessori nuts-and-bolts set.

  double-nut  a coupling nut: two bolts screw in from either end and meet
  plate       a 2x3 board of threaded sockets to stand the bolts in

The thread is not re-invented. It is lifted out of the designer's own nut:
a cylinder minus the nut leaves a solid cast of the bore, thread profile and
running clearance included, and translating that cast by exactly one lead
maps the helix onto itself, so copies stack into a thread of any length.
Anything cut with it mates like the original nut does, by construction.

Measured off the source mesh (three independent ways, all agreeing):
  lead 11.66 mm, right hand, single start
  bolt  major r 17.50, minor r 11.67
  nut   bore crest r 12.17, root r 18.00  -> 0.50 mm radial clearance

Every generated thread is then proved by screwing the designer's actual
bolt into it: at each depth there must be a rotation window where FCL
reports no collision, and that window must advance by one turn per lead.

Usage: gen_montessori.py --part double-nut|plate [--out FILE.3mf]
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh
import trimesh.collision as tc
from shapely.geometry import Polygon

SRC = os.path.expanduser(
    "~/Code/My3DPrints/models/montessori+nuts+and+bolts.3mf")
NUT_ID, BOLT_ID = "11", "9"
LEAD = 11.660                      # mm, right-hand single start
BORE_ROOT = 18.00                  # female thread root radius
HEX_CR = 28.55                     # nut circumradius (57.1 across corners)
CHAMFER = 2.2
# The designer's nut chamfers its outer hex at both ends: the end face is a
# circle of r 22.56 flaring to the full 28.55 corner by z 5.26. Measured off
# the source, and reused here so the coupler reads as the same family of
# part rather than a raw prism with square edges.
FACE_R, CHAM_H = 22.56, 5.26
BOSS_CHAM = 2.5      # radial chamfer on each socket lip


def source_parts():
    sc = trimesh.load(SRC, force="scene")
    nut = sc.geometry[NUT_ID].copy()
    nut.merge_vertices()
    nut.update_faces(nut.nondegenerate_faces())
    nut.process(validate=True)
    # the bolt's head would foul any test fixture: keep the shank
    shank = sc.geometry[BOLT_ID].slice_plane([0, 0, 1.0], [0, 0, 1], cap=True)
    return nut, shank


def thread_plug(nut, length, lead=LEAD):
    """A solid cast of the nut's bore, stacked to `length` about z=0."""
    core = trimesh.creation.cylinder(radius=BORE_ROOT + 2.0, height=LEAD,
                                     sections=180).difference(
        nut, engine="manifold")
    n = int(np.ceil(length / lead)) + 2
    parts = []
    for k in range(-n // 2 - 1, n // 2 + 2):
        c = core.copy()
        c.apply_translation([0, 0, k * lead])
        parts.append(c)
    plug = trimesh.boolean.union(parts, engine="manifold")
    plug = plug.slice_plane([0, 0, -length / 2], [0, 0, 1], cap=True)
    return plug.slice_plane([0, 0, length / 2], [0, 0, -1], cap=True)


def entry_chamfer(z_face, opens_up):
    """A cone that flares the bore where it meets a face of the part.

    It must sit at the part's face, not at the end of the cutting plug —
    a plug that overshoots the part carries its chamfer outside the
    material, where it cuts nothing.
    """
    c = trimesh.creation.cone(radius=BORE_ROOT + CHAMFER, height=CHAMFER,
                              sections=96)
    if opens_up:
        c.apply_transform(trimesh.transformations.rotation_matrix(
            np.pi, [1, 0, 0]))          # wide at the face, tapering inward
    c.apply_translation([0, 0, z_face])
    return c


def hexagon(cr, rot=0.0):
    a = np.radians(np.arange(6) * 60.0) + rot
    return Polygon(np.column_stack([cr * np.cos(a), cr * np.sin(a)]))


def screw_test(part, shank, depths, step_deg=3, at=(0.0, 0.0)):
    """Screw the real bolt in: a free rotation window must exist at depth."""
    cm = tc.CollisionManager()
    cm.add_object("part", part)
    out = []
    for dz in depths:
        free = []
        for adeg in range(0, 360, step_deg):
            T = trimesh.transformations.rotation_matrix(
                np.radians(adeg), [0, 0, 1])
            T[0, 3], T[1, 3], T[2, 3] = at[0], at[1], dz
            if not cm.in_collision_single(shank, transform=T):
                free.append(adeg)
        if not free:
            return None, out
        arr = np.radians(free)
        ctr = np.degrees(np.arctan2(np.sin(arr).mean(),
                                    np.cos(arr).mean())) % 360
        out.append((float(dz), float(ctr), len(free) * step_deg))
    z = np.array([o[0] for o in out])
    a = np.unwrap(np.radians([o[1] for o in out]))
    lead = 2 * np.pi / abs(np.polyfit(z, a, 1)[0])
    return lead, out


def end_chamfers(height):
    """A barrel whose conical ends cut the hex corners, as a nut's do."""
    # the cone must pass exactly through (HEX_CR, CHAM_H) — that is the
    # measured point where the original reaches its full corner. Running it
    # straight to a clearance radius instead gets there too early.
    slope = (HEX_CR - FACE_R) / CHAM_H
    zc = CHAM_H + 2.0 / slope
    # keep the profile off the axis: a revolve through r=0 leaves degenerate
    # polar triangles that survive the boolean as non-manifold edges. A 1 mm
    # axial hole is harmless — it sits inside the bore, which is open anyway.
    prof = np.array([(1.0, 0.0), (FACE_R, 0.0), (HEX_CR + 2.0, zc),
                     (HEX_CR + 2.0, height - zc), (FACE_R, height),
                     (1.0, height), (1.0, 0.0)])
    return trimesh.creation.revolve(prof, sections=192)


def build_double_nut(nut, height=42.0, lead=LEAD):
    body = trimesh.creation.extrude_polygon(hexagon(HEX_CR), height)
    body = body.intersection(end_chamfers(height), engine="manifold")
    body.apply_translation([0, 0, -height / 2])   # centred while cutting
    # a waist groove marks the two halves and gives fingers a purchase
    groove = trimesh.creation.cylinder(radius=HEX_CR + 1.0, height=4.0,
                                       sections=96)
    ring = trimesh.creation.cylinder(radius=HEX_CR - 2.2, height=4.6,
                                     sections=96)
    body = body.difference(groove.difference(ring), engine="manifold")
    cut = trimesh.boolean.union(
        [thread_plug(nut, height + 6.0, lead=lead),
         entry_chamfer(height / 2, True),
         entry_chamfer(-height / 2, False)], engine="manifold")
    return body.difference(cut, engine="manifold")


def build_plate(nut, cols=2, rows=3, pitch=64.0, base=6.0, boss=15.0 + LEAD,
                floor=5.0):
    # boss height carries one more full turn of thread than the first cut:
    # 16 mm of socket was 1.4 turns, which is thin for a toy that gets
    # levered on. One lead deeper makes it 2.4.
    socket = boss + base - floor
    xs = (np.arange(cols) - (cols - 1) / 2) * pitch
    ys = (np.arange(rows) - (rows - 1) / 2) * pitch
    w, d = (cols - 1) * pitch + HEX_CR * 2 + 8, (rows - 1) * pitch + HEX_CR * 2 + 8
    plate = trimesh.creation.extrude_polygon(
        Polygon([(-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2),
                 (-w / 2, d / 2)]).buffer(6.0, resolution=16), base)
    parts = [plate]
    for x in xs:
        for y in ys:
            # a revolve, not a cylinder, so the boss can carry the same
            # chamfered lip the source nut has — a square rim is what reads
            # as unfinished
            br = BORE_ROOT + 4.0
            slope = (HEX_CR - FACE_R) / CHAM_H          # the nut's own angle
            cz = BOSS_CHAM / slope
            prof = np.array([(1.0, base), (br, base), (br, base + boss - cz),
                             (br - BOSS_CHAM, base + boss),
                             (1.0, base + boss), (1.0, base)])
            b = trimesh.creation.revolve(prof, sections=128)
            b.apply_translation([x, y, 0])
            parts.append(b)
    solid = trimesh.boolean.union(parts, engine="manifold")
    top = base + boss
    cuts = []
    for x in xs:
        for y in ys:
            p = thread_plug(nut, socket)          # blind: stops on the floor
            p.apply_translation([x, y, top - socket / 2])
            ch = entry_chamfer(top, True)
            ch.apply_translation([x, y, 0])
            cuts += [p, ch]
    return solid.difference(trimesh.boolean.union(cuts, engine="manifold"),
                            engine="manifold"), (w, d, base + boss)


def prep_for_export(m):
    """3MF stores coordinates to finite precision, so surfaces that meet
    tangentially come back as duplicate faces and read non-manifold. Quantise
    to that precision and drop the duplicates — but keep the original if the
    pass does not actually help, since a coarse vertex merge can weld a fine
    chamfer's corners and break a solid that was sound.
    """
    q = m.copy()
    q.vertices = q.vertices.round(4)
    q.merge_vertices(digits_vertex=5)
    q.update_faces(q.unique_faces())
    q.update_faces(q.nondegenerate_faces())
    q.process(validate=True)
    return q if q.is_watertight else m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["double-nut", "plate"], required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    nut, shank = source_parts()
    rep = {"part": a.part, "lead_mm": LEAD}
    if a.part == "double-nut":
        H = 42.0
        m = build_double_nut(nut, H)
        rep["height_mm"] = H
        depths = [13.0, 17.0, 21.0, 25.0, 29.0]
        probe, at = m, (0.0, 0.0)
    else:
        m, (w, d, h) = build_plate(nut)
        rep.update(plate_mm=[round(w + 12, 1), round(d + 12, 1), round(h, 1)],
                   socket_depth=round(6.0 + (15.0 + LEAD) - 5.0, 1),
                   socket_turns=round((6.0 + (15.0 + LEAD) - 5.0) / LEAD, 2),
                   floor_mm=5.0,
                   sockets=6, pitch_mm=64.0)
        depths = [8.0, 13.0, 18.0, 23.0]
        probe, at = m, (-32.0, -64.0)      # a real socket, not the origin
    # Only repair what is broken. An unconditional merge_vertices welds the
    # chamfer revolve's near-coincident vertices near the hex corners and
    # turns a watertight solid into a non-manifold one.
    if not m.is_watertight:
        m.merge_vertices(digits_vertex=5)
        m.update_faces(m.unique_faces())
        m.update_faces(m.nondegenerate_faces())
        m.process(validate=True)
    m.apply_translation([0, 0, -m.bounds[0][2]])      # stand it on the bed
    m = prep_for_export(m)
    rep["bodies"] = int(len(m.split(only_watertight=False)))
    lead, windows = screw_test(probe, shank, depths, at=at)
    if lead is None:
        print(json.dumps({"ok": False, "error":
              "the designer's own bolt will not screw into this thread",
              **rep}))
        return 1
    rep["screw_lead_mm"] = round(float(lead), 2)
    rep["free_window_deg"] = [w[2] for w in windows]
    if abs(lead - LEAD) > 0.6:
        print(json.dumps({"ok": False, "error":
              f"thread advances {lead:.2f} mm/turn, not {LEAD}", **rep}))
        return 1
    sec = m.section(plane_origin=[0, 0, m.bounds[0][2] + 0.15],
                    plane_normal=[0, 0, 1])
    if sec is not None:
        p2, _ = sec.to_2D()
        rep["bed_mm2"] = round(sum(p.area for p in p2.polygons_full))
    rep["volume_cm3"] = round(float(m.volume) / 1000, 1)
    rep["est_g"] = round(float(m.volume) / 1000 * 1.24, 1)
    ok = rep["bodies"] == 1
    if a.out and ok:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        sc = trimesh.Scene()
        sc.add_geometry(m, geom_name=a.part.replace("-", "_"))
        sc.export(a.out)
        from embed_settings import embed
        # neither part wants a brim: both land a large flat footprint
        # (the coupler an 11 cm2 hex, the plate ~290 cm2) and the skirt is
        # only cleanup — field-reported
        embed(a.out, brim=False)
        # the honest check is the exported file, not the mesh in memory:
        # 3MF precision collapses tangent surfaces into duplicate faces
        chk = trimesh.load(a.out, force="scene")
        rep["watertight"] = all(g.is_watertight
                                for g in chk.geometry.values())
        ok = ok and rep["watertight"]
        rep["file"] = os.path.basename(a.out)
    else:
        rep["watertight"] = bool(m.is_watertight)
    print(json.dumps({"ok": ok, **rep}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
