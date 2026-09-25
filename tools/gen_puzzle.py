#!/usr/bin/env python3
"""Puzzle blocks on the Montessori thread family, at puzzle scale.

  seed-cube   a cube split across the bolt axis into two threaded halves,
              plus the bolt that holds them

Inspired by the toddler set, not compatible with it: the thread comes from
`thread.py`, which keeps the original's cosine profile and its three exact
ratios and throws the 35 mm diameter away. Default here is a 16 mm thread
in a 38 mm block, so the finished puzzle is a thing for hands rather than
for a toy box.

Only the lower half is threaded. The upper half takes a plain clearance
bore and a hex pocket, and that is not a simplification — it is the only
arrangement that can be assembled.

  A keyed head cannot be screwed into its own keyway.

The head arrives at its pocket by turning, because it is on a thread, so it
can only present the right rotation once every sixty degrees. Sixty degrees
is 0.89 mm of descent on this lead and the corners need the whole pocket
depth to clear, so the head lands on the top face and grinds there. The
first build of this part had thread under the pocket and would have jammed
on assembly; nothing in a disassembly argument catches it, which is why
`head_descends` below is a gate and not a comment. Real bolted joints have
known this forever: clearance hole in the near part, thread in the far one.

So the cube is held as a clamp, and it still cannot be pulled apart. The
bolt drops through the upper half without turning, seats its head in the
pocket, and threads into the lower half. The upper half is capped by the
head above and the lower half below. Because the head is keyed to it, the
whole top of the cube is the wrench: turn it and the bolt backs out of the
lower half.

A split *along* the bolt would not lock at all, which is the trap this part
exists to rule out. A plane through a round bore leaves one arc over 180
degrees and one under it; the half holding the shallow arc is a groove, and
a groove lifts straight off a cylinder. Splitting across the axis is what
makes the halves captive.

The pocket is the joint the larger puzzles are built from — a head sunk in
a neighbor's pocket cannot turn until that neighbor moves, which is the
edge a dependency cycle is made of. The law above says where the thread may
go in those too.

Shank length is not chosen, it is derived: the head sinks by the pocket
depth and the tip lands flush with the underside. Ask for a longer shank
and it protrudes by a stated amount, which is how one block reaches into
the next.

Usage: gen_puzzle.py [--side MM] [--thread MM] [--split F] [--pocket MM]
                     [--shank MM] [--out FILE.3mf]
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh
import trimesh.collision as tc
from shapely.geometry import Polygon

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thread import Thread
from assembly import Sweep, screw_path, find_phase, disassemble

POCKET_SLOP = 0.50     # across flats, total: 0.25 per face
FILLET_F = 0.11        # vertical edge radius, as a fraction of the side
WALL_MIN = 4.0         # material outside the hex pocket at its corners
TURNS_MIN = 1.2        # engagement each half must keep after its run-outs
# Run-out spans, in leads. They differ because the three mouths do different
# jobs. The pocket floor is where the bolt is started by hand and gets a full
# lead of plain bore to find. The underside only lets the tip out, so half a
# lead. The seam is not a mouth at all — nothing is ever started there, the
# bolt runs straight through it — so it gets the least that still keeps the
# thread from ending in a feather on the two faces that have to sit flat
# against each other.
RO_ENTRY, RO_END, RO_SEAM = 1.00, 0.50, 0.35
# Seated is face-on-face contact, and FCL scores contact as collision. So
# the screw-home path is verified to within this standoff of home rather
# than to home itself — half the running clearance, which is also the
# sampling step, so the unverified remainder is smaller than one sample.
SEAT_EPS = 0.15


def block_profile(side, fillet):
    s = side / 2.0
    sq = Polygon([(-s, -s), (s, -s), (s, s), (-s, s)])
    return sq.buffer(-fillet).buffer(fillet, resolution=24)


def build_seed(t, side, split_frac, pocket_d, thread_through=False):
    """Thread below the seam, plain bore above it, hex pocket in the top.

    The thread stops at the seam because the block above it has to swallow a
    head, and a block that swallows a head can never be threaded: the head
    would have to be screwed into its own keyway. See the law in the module
    docstring — this is where it is spent.
    """
    S, c = float(side), float(side) * split_frac
    pocket_cr = t.hex_cr + POCKET_SLOP / 2.0 / np.cos(np.radians(30.0))
    land = S / 2.0 - pocket_cr
    if land < WALL_MIN:
        raise ValueError(
            f"{land:.2f} mm of wall outside the hex pocket (min {WALL_MIN}) — "
            f"the head's corners reach {pocket_cr:.2f} mm from the axis; "
            f"raise --side to {2 * (pocket_cr + WALL_MIN):.0f} or lower "
            f"--thread")

    floor = S - pocket_d
    solid = trimesh.creation.extrude_polygon(block_profile(S, FILLET_F * S), S)
    pk = trimesh.creation.extrude_polygon(t.hexagon(pocket_cr), pocket_d + 2.0)
    pk.apply_translation([0, 0, floor])
    if thread_through:
        # The defect, kept buildable on purpose: thread under the pocket.
        # It is the negative control for the mobility check — a gate nobody
        # can trust until it has been shown to fail on the thing it exists
        # to catch.
        thr = t.cutter(floor + t.lead, z0=-t.lead,
                       runout=[(0.0, RO_END * t.lead),
                               (floor, RO_ENTRY * t.lead)])
    else:
        thr = t.cutter(c + t.lead, z0=-t.lead,
                       runout=[(0.0, RO_END * t.lead), (c, RO_SEAM * t.lead)])
    # The plain bore starts a third of a millimeter below the seam rather
    # than on it. Ending one cut exactly where another begins leaves two
    # coincident cylindrical faces for the boolean to reconcile, and it
    # reconciles them into slivers; the overlap costs nothing because the
    # run-out has already opened the bore to nearly this radius there.
    lo, hi = c - 0.3, floor + 2.0
    plain = trimesh.creation.cylinder(radius=t.major_r + t.clearance,
                                      height=hi - lo, sections=192)
    plain.apply_translation([0, 0, (hi + lo) / 2.0])
    cuts = [thr, pk, t.mouth_chamfer(0.0, False),
            t.mouth_chamfer(floor, True)]
    if not thread_through:
        cuts.append(plain)
    solid = solid.difference(trimesh.boolean.union(cuts, engine="manifold"),
                             engine="manifold")

    bottom = solid.slice_plane([0, 0, c], [0, 0, -1], cap=True)
    top = solid.slice_plane([0, 0, c], [0, 0, 1], cap=True)
    turns = (c - (RO_END + RO_SEAM) * t.lead) / t.lead
    if turns < TURNS_MIN:
        raise ValueError(
            f"engagement {turns:.2f} turns (min {TURNS_MIN}) — the run-outs "
            f"have eaten the thread; raise --side, or move --split up, which "
            f"costs the upper half nothing now that it carries no thread")
    return bottom, top, round(land, 2), round(turns, 2)


def as_used(t, bolt):
    """The bolt the way a hand holds it: head up, shank down, base at z=0.

    A rotation about x, not a mirror — a mirror would hand back a left-hand
    thread that fits nothing.
    """
    m = bolt.copy()
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    m.apply_translation([0, 0, t.head_h])
    return m


def tidy(m):
    # Only repair what is broken: an unconditional merge welds the chamfer
    # revolve's near-coincident vertices and turns a watertight solid into
    # a non-manifold one.
    if not m.is_watertight:
        m.merge_vertices(digits_vertex=5)
        m.update_faces(m.unique_faces())
        m.update_faces(m.nondegenerate_faces())
        m.process(validate=True)
    return m


def verify(t, bottom, top, bolt, S, c, floor, shank_len, rep):
    """Every claim the part makes, as a motion rather than a pose."""
    down = as_used(t, bolt)
    clr = t.clearance

    # 1. The bolt drops into the upper half and its head seats — by pure
    #    translation, no rotation anywhere on the path. This is the gate the
    #    first build would have failed: it had thread under the pocket, so
    #    this motion did not exist and the head could never have arrived.
    s1 = Sweep(top, down)
    drop = screw_path(S + shank_len, floor, None, 0.0, s1.max_r,
                      clearance=clr)
    rep["path_head_seats"] = {"samples": len(drop),
                              "free": s1.run(drop) is None}

    # 2. The same drop at rotations that are not multiples of 60, stopped
    #    before the head reaches the pocket. Free at every one of them means
    #    the bore really is plain: a thread would catch at some angle.
    plain = {}
    for a in (10, 25, 47):
        p = screw_path(S + shank_len, S, None, np.radians(a), s1.max_r,
                       clearance=clr)
        plain[a] = s1.run(p) is None
    rep["path_bore_plain"] = plain

    # 3. Seated, the head must be keyed. Free square-on and at a whole
    #    sixth of a turn, fouling anywhere between.
    hd = t.head()
    hd.apply_translation([0, 0, floor + 0.3])   # off the floor: FCL scores
    s3 = Sweep(top, hd)                         # coplanar contact as a hit
    key = {}
    for a in (0, 15, 30, 60):
        T = trimesh.transformations.rotation_matrix(np.radians(a), [0, 0, 1])
        s3.cm.set_transform("mover", T)
        key[a] = bool(s3.cm.in_collision_internal())
    rep["head_keyed"] = (not key[0]) and (not key[60]) and key[15] and key[30]
    rep["key_fouls_at_deg"] = key

    # 4. The upper half, with the bolt seated in it, screws down onto the
    #    lower half. One rigid body on a helix: the head and its pocket turn
    #    together, so there is no relative rotation left to jam on.
    mover = trimesh.util.concatenate([top, _seated(t, bolt, floor)])
    s4 = Sweep(bottom, mover)
    th, win = find_phase(bottom, mover, 3.0, t.lead, clearance=clr)
    rep["start_window_deg"] = win
    if th is None:
        rep["path_screws_home"] = {"free": False,
                                   "why": "no free rotation 3 mm from home"}
        return rep
    hands = {}
    for sgn in (1, -1):
        th_end = th - sgn * 2 * np.pi * 3.0 / t.lead
        n = int(np.ceil(np.hypot(s4.max_r * 2 * np.pi * c / t.lead, c)
                        / (clr / 2.0))) + 1
        path = []
        for u in np.linspace(1.0, 0.0, n):
            d = SEAT_EPS + (c - SEAT_EPS) * u
            T = trimesh.transformations.rotation_matrix(
                th_end + sgn * 2 * np.pi * d / t.lead, [0, 0, 1])
            T[2, 3] = d
            path.append(T)
        hands[sgn] = (s4.run(path) is None, len(path))
    rep["path_screws_home"] = {"right_hand": hands[1][0],
                               "left_hand": hands[-1][0],
                               "samples": hands[1][1],
                               "standoff_mm": SEAT_EPS}
    # exactly one handedness may work; both would mean it is not a thread
    rep["handed"] = hands[1][0] != hands[-1][0]
    th_end = th - 2 * np.pi * 3.0 / t.lead
    # How far off square the top half lands when it is tight. It matters
    # only against the thread's own backlash: the free window is the play
    # the seated block still has, so anything inside half of it can be
    # nudged square by hand and anything outside it cannot.
    off = float(np.degrees(th_end) % 90.0)
    off = off - 90.0 if off > 45.0 else off
    rep["seated_off_square_deg"] = round(off, 1)
    rep["square_within_backlash"] = bool(abs(off) <= win / 2.0)

    # 5. And then take it apart. The gates above each check a motion I
    #    thought of, which cannot catch a part that is trapped — that
    #    failure is the absence of a motion, so there is no path to sample
    #    and nothing to fail. This one tries every motion the assembly
    #    could allow on every body and every pair, and reports what it
    #    cannot free. The design this replaced passed all four gates above
    #    and could not be taken apart at all.
    steps, stuck = disassemble(
        {"lower": bottom, "upper": top, "bolt": _seated(t, bolt, floor)},
        t.lead, clearance=clr)
    rep["disassembly"] = [{"free": x["free"],
                           "by": sorted({("slide" if b["coupling"] is None
                                          else "screw") for b in x["by"]})}
                          for x in steps]
    rep["comes_apart"] = not stuck
    if stuck:
        rep["welded"] = stuck
    return rep


def _seated(t, bolt, floor):
    m = as_used(t, bolt)
    m.apply_translation([0, 0, floor])
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", type=float, default=40.0)
    ap.add_argument("--thread", type=float, default=16.0,
                    help="major diameter of the thread")
    ap.add_argument("--split", type=float, default=0.5)
    ap.add_argument("--pocket", type=float, default=5.0)
    ap.add_argument("--shank", type=float, default=None,
                    help="default: flush with the underside")
    ap.add_argument("--out")
    a = ap.parse_args()

    t = Thread(major_r=a.thread / 2.0)
    S, c, p = a.side, a.side * a.split, a.pocket
    floor = S - p
    shank_len = floor if a.shank is None else a.shank

    try:
        bottom, top, land, turns = build_seed(t, S, a.split, p)
    except ValueError as e:
        # build_seed raises for settings that cannot be drawn at all. It
        # used to escape main(), and the page printed the Python stack.
        print(json.dumps({"ok": False, "part": "seed-cube",
                          "error": str(e)}))
        return 1
    bolt = t.bolt(shank_len=shank_len)
    rep = {"part": "seed-cube", "thread": repr(t), "side_mm": S,
           "seam_mm": round(c, 2), "pocket_depth_mm": p,
           "shank_mm": round(shank_len, 2),
           "head_proud_mm": round(t.head_h - p, 2),
           "tip_protrudes_mm": round(shank_len - floor, 2),
           "pocket_wall_mm": land, "engagement_turns": turns}
    verify(t, bottom, top, bolt, S, c, floor, shank_len, rep)

    gates = [("path_head_seats", rep["path_head_seats"]["free"]),
             ("path_bore_plain", all(rep["path_bore_plain"].values())),
             ("head_keyed", rep["head_keyed"]),
             ("path_screws_home", rep.get("path_screws_home", {}).get(
                 "right_hand", False)),
             ("handed", rep.get("handed", False)),
             ("comes_apart", rep.get("comes_apart", False))]
    failed = [n for n, ok in gates if not ok]
    if failed:
        # every other generator supplies "error"; without it the shop
        # showed the user the words "generation refused" and nothing else
        print(json.dumps({"ok": False, **rep, "failed": failed,
                          "error": "these settings do not come apart: "
                                   + ", ".join(failed)}))
        return 1

    bottom, top, bolt = tidy(bottom), tidy(top), tidy(bolt)
    for m in (top, bolt):
        m.apply_translation([0, 0, -m.bounds[0][2]])
    pitch = S + 8.0
    bottom.apply_translation([-pitch, 0, 0])
    bolt.apply_translation([pitch, 0, 0])

    parts = {"seed_lower": bottom, "seed_upper": top, "seed_bolt": bolt}
    rep["bodies"] = sum(len(m.split(only_watertight=False))
                        for m in parts.values())
    vol = sum(float(m.volume) for m in parts.values()) / 1000
    rep["volume_cm3"] = round(vol, 1)
    rep["est_g"] = round(vol * 1.24, 1)
    rep["plate_mm"] = [round(3 * S + 16, 1), round(S, 1)]
    ok = rep["bodies"] == 3

    if a.out and ok:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        sc = trimesh.Scene()
        for n, m in parts.items():
            sc.add_geometry(m, geom_name=n)
        sc.export(a.out)
        from embed_settings import embed
        # three flat footprints, none of them tall: the skirt is cleanup
        embed(a.out, brim=False)
        # the honest check is the exported file, not the mesh in memory:
        # 3MF precision collapses tangent surfaces into duplicate faces
        from meshcheck import export_defects
        bad = export_defects(a.out)
        rep["watertight"] = not bad
        if bad:
            rep["defects"] = bad
            ok = False
        rep["file"] = os.path.basename(a.out)
    else:
        rep["watertight"] = all(m.is_watertight for m in parts.values())
    print(json.dumps({"ok": ok, **rep}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
