#!/usr/bin/env python3
"""The Knot -- three bolts woven so that none of them can turn.

WHY THE SEED CUBE IS NOT THE PUZZLE

`gen_puzzle.py` builds the primitive: one bolt, two halves. It is naive on
purpose -- one affordance, and that affordance is visible. The depth search
scores it in two moves with one legal first move and no retrograde, which is
exactly what it was built to be. Six of those in a row is still six obvious
turns. What follows is what makes it a puzzle instead.

THE VOCABULARY

Six primitives, each an edge in a dependency graph:

  P1  coaxial split    blocks pulling; costs a full unscrew to defeat
  P2  pinned shear     a shank crossing a sliding joint; blocks the slide
  P3  head capture     a head sunk in a NEIGHBOR's hex pocket cannot turn
                       until that neighbor moves axially by the pocket depth
  P4  travel block     rotation is free but the shank has no corridor to
                       retreat into
  P5  captive nut      a nut trapped in a slot cannot rotate, so turning the
                       bolt drives it ALONG the shank like a screw jack --
                       turning here moves something THERE
  P6  proud head       a head standing proud blocks a neighbor's slide, so
                       it must be screwed further IN to release it

P5 and P6 are what would lift it out of naive. P5 separates cause from
effect in space; P6 is a retrograde move -- the correct action is to do up
the thing you are trying to undo. Whether this first Knot needs either is
not a matter of opinion any more: `mobility.py` counts legal first moves,
shortest solve and retrograde moves, so the geometry can be asked.

THE WEAVE

Three bolt axes, cyclic under a 120 degree turn about [1,1,1]:

    A along x at (y,z) = (a, 0)
    B along y at (z,x) = (a, 0)
    C along z at (x,y) = (a, 0)

Every pair is skew and their common perpendicular is the third coordinate,
so all three pairwise distances are exactly `a` whatever a is. That equal
spacing is what lets ONE block design serve all three positions -- and one
bolt design serve all three bolts, because the same 120 degree rotation
that carries block 0 to block 1 carries bolt 2 to bolt 0. Two parts, printed
three times each.

WHAT SETS THE SIZE, WHICH IS NOT WHAT THE FIRST SKETCH ASSUMED

The sketch chose `a` from the daylight between neighboring shanks and landed
on 20-22 mm. That is not what decides it. Blocks are bars of half-section w,
and block i's bar and block i+1's bar occupy the same band unless w <= a/2,
so the section is capped by the spacing. Two things then have to fit in it,
and neither is a shank.

ACROSS the block, a hex head: the pocket's corner radius is 1.642 R_major,
so a >= 2 (1.642 R_major + slop + wall + gap), which for the seed's 16 mm
thread is 36, not 22. The head, not the shank, is the widest thing a block
has to contain.

ALONG the block, the SLOT, and this is the one that decides whether the
puzzle can open at all. A block frees its neighbor's bolt by sliding until
the head clears the pocket, so the slot has to be at least as long as the
pocket is deep, and pocket, slot and two walls all have to fit inside the
block's own length of a - gap:

    a >= 2 pocket_cr + 2 wall + slot + gap

At a = 36 the longest slot that fits is under a millimetre and the pocket is
thirteen deep. That is why the first Knot measured welded at every slot size
tried, including sizes that could not be built -- the geometry was being
asked to swallow a 13 mm slide in 1 mm of room, and no search finds a way
through that because there isn't one. Sizing from the slot instead gives
a = 49 and a cube 98 mm on a side. It is a big object, and it is the size
the mechanism costs.

At that spacing the blocks meet face to face on three planes and the
assembly closes into a cube 2a on a side: three faces show a bolt tip flush
in a threaded hole, three are blank, and nothing protrudes anywhere. The
equal spacing did that, not a decision.

THE LAW THAT CONSTRAINS THE LAYOUT

From `gen_puzzle.py`, paid for twice:

    A keyed head cannot be screwed into its own keyway.

So a block that captures a head takes a CLEARANCE bore; thread lives only in
the block the tip reaches. Here that means bolt i's head is captured in
block i+1 through a plain bore, and bolt i's thread engages block i. Get it
backwards and the object cannot be assembled, and no disassembly argument
will tell you.

WHY A SLOT IS NOT A CHEAT BUT A THEOREM

Every body in the weave has exactly two bores, on two perpendicular axes.
Translating along either carries the OTHER bore sideways across the shank
running through it, and a bore does not move sideways over a shank. So no
body translates at all, in any direction, and the fully symmetric weave is
welded -- not hard, impossible, and impossible to ASSEMBLE too, which is the
same fact read backwards. The search says so: `--entry none` reports zero
legal first moves, in four hundred queries.

The way in therefore cannot be found by looking harder; it has to be built,
and it costs two things rather than one. One own-line bore is plain instead
of threaded, because the last thread in a cycle cannot be closed by turning
-- by then nothing is free to turn. And one pocket is elongated along its
block's own axis, because a plain bore alone still leaves the block pinned
sideways by the head it holds.

The pocket opens on the face that ABUTS the next block, not on the outside
of the cube, and that is the lock rather than a detail. Opening outward, a
block has to travel outward to slide off the head it holds -- and outward is
exactly where its neighbor is, four tenths of a millimetre away. The search
found that: with the first bolt lifted out, every remaining body had zero
legal moves and the object was as welded five parts in as it had been at
six.

Usage: gen_knot.py [--a MM] [--thread MM] [--entry none|slip|slot]
                   [--float MM] [--measure] [--out FILE.3mf]
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh
import trimesh.collision as tc
from shapely import affinity
from shapely.geometry import MultiPolygon

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thread import Thread                                    # noqa: E402

WALL_MIN = 4.0         # material outside the hex pocket at its corners
POCKET_SLOP = 0.50     # across flats, total: 0.25 per face
RO = 0.75              # thread run-out, in leads
FILLET = 2.0           # edge break on the bar, mm
# Blocks meet face to face on three planes. Built to the same plane they
# print as one fused surface and slide on each other with nothing between,
# and a sweep along a shared face never leaves contact, so the search calls
# every such slide blocked from its first sample to its last. Both problems
# are the same missing millimetre.
FACE_GAP = 0.20        # per face; neighbors are two of these apart
# A head bottomed on its pocket floor is contact, not fit. The mesh shows
# zero penetration and the boolean says the parts do not overlap, and FCL
# still scores the shared surface as a collision -- so every sweep of that
# block or that bolt died on its second sample and four designs that differ
# reported byte-identical searches. The head is floated off the floor by
# half the slack the pocket already carries, which is also what a printed
# part needs at both ends rather than all of it at one.
AXIAL_SLACK = 0.15     # head to pocket floor, and head to mouth

# The cyclic map: (p, q, r) -> (r, p, q), a 120 degree turn about [1,1,1].
# It carries axis x to y to z, block 0 to block 1, and bolt 2 to bolt 0, so
# the whole assembly is one block and one bolt plus this matrix twice.
CYCLE = np.array([[0.0, 0, 1, 0], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]])


def lines(a):
    """The three bolt axes as (direction, origin), in cyclic order."""
    return [((1, 0, 0), (0, a, 0)), ((0, 1, 0), (0, 0, a)),
            ((0, 0, 1), (a, 0, 0))]


def pocket_cr(t):
    return t.hex_cr + POCKET_SLOP / 2.0 / np.cos(np.radians(30.0))


def min_spacing(t, slot=0.0, gap=FACE_GAP):
    """The smallest `a` that leaves WALL_MIN of wall around a head pocket.

    Two constraints, and the second is the one that decides whether the
    puzzle can open at all.

    Across the block, the pocket has to fit in the section with wall
    outside it, which is what moved the design from the 22 mm the first
    sketch guessed to 36: the head, not the shank, is the widest thing a
    block has to contain.

    Along the block, the SLOT has to fit too -- the pocket plus its
    elongation plus the same wall at both ends, inside the block's own
    length of a - gap. That bound is why the first Knot could not open. A
    block frees its neighbor's bolt by sliding until the head clears the
    pocket, so the slot has to be as long as the pocket is deep; at a = 36
    the longest slot that fits is under a millimetre and the pocket is
    thirteen deep. No amount of searching finds a way through that, because
    there isn't one -- the design was asking a 36 mm block to swallow a
    13 mm slide it had 1 mm of room for.
    """
    cr = pocket_cr(t)
    across = 2.0 * (cr + WALL_MIN + gap)
    along = 2.0 * cr + 2.0 * WALL_MIN + float(slot) + gap
    return max(across, along)


def max_slot(t, a, gap=FACE_GAP):
    """The longest elongation that still leaves WALL_MIN at both ends."""
    return (a - gap) - 2.0 * pocket_cr(t) - 2.0 * WALL_MIN


def onto_x(mesh, origin):
    """Move a z-built feature onto the x line through `origin`.

    Everything is built here and carried to the other two lines by CYCLE,
    which is not merely tidy: reaching a line by two different rotations
    clocks a hexagon differently and phases a helix differently, and both
    of those are invisible until the part will not go together.
    """
    m = mesh.copy()
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2,
                                                             [0, 1, 0]))
    m.apply_translation(np.asarray(origin, float))
    return m


def bar(a, w, fillet=FILLET, gap=FACE_GAP):
    """One block before its bores: a rectangular bar, edges broken.

    x in [w, a+w], y in [-w, a+w], z in [-w, w]. Its own line runs down the
    x extent at y = a; the previous bolt crosses it down the z extent at
    x = a. With w = a/2 the two arms share a footprint and the L collapses
    into a single bar, which is both less material and one fewer feature to
    get wrong.

    Two of the six faces abut a neighbor -- the near face on its own line
    and the far face on the previous one -- and those two are held back by
    `gap`. The other four are the outside of the finished cube and stay
    exactly on it, so the object still closes to 2a on a side.
    """
    lo = np.array([w + gap, -w, -w])
    hi = np.array([a + w, a + w, w - gap])
    m = trimesh.creation.box(hi - lo)
    m.apply_translation((lo + hi) / 2.0)
    if fillet > 0:
        m = _break_edges(m, fillet)
    return m


def _break_edges(m, r):
    """A chamfer, not a round: one plane per edge and no boolean surprises."""
    lo, hi = m.bounds
    cuts = []
    for i in range(3):
        for j in range(i + 1, 3):
            for si in (1, -1):
                for sj in (1, -1):
                    n = np.zeros(3)
                    n[i], n[j] = si, sj
                    n /= np.linalg.norm(n)
                    p = np.zeros(3)
                    p[i] = hi[i] if si > 0 else lo[i]
                    p[j] = hi[j] if sj > 0 else lo[j]
                    for k in range(3):
                        if k not in (i, j):
                            p[k] = (lo[k] + hi[k]) / 2.0
                    cuts.append((p - n * r * np.sqrt(2) / 2.0, n))
    for p, n in cuts:
        m = m.slice_plane(p, -n, cap=True)
    return m


def datum(t, a, gap=FACE_GAP):
    """Where the head bottom sits on its line: the origin everything shares.

    One number, and both the bore and the bolt are measured from it. A
    thread is a helix with a phase, so a bore and a bolt laid out from
    different datums are out of step by 2 pi times their offset over the
    lead and foul over the whole engagement. It came out clean at one value
    of `a` and interfered at the next millimetre down, which is what a thing
    that works by luck looks like.
    """
    return a / 2.0 - gap - (t.head_h + 2 * AXIAL_SLACK)


def block(t, a, threaded=True, slot=0.0, gap=FACE_GAP):
    """One block: a threaded bore on its own line, a head pocket on the last.

    The pocket opens on the face that ABUTS the next block, not on the
    outside of the cube, and that is the whole lock rather than a detail.
    Opening outward, a block has to travel outward to slide off the head it
    holds -- and outward is exactly where its neighbor is, half a millimetre
    away. The search found that: with the first bolt lifted out, every
    remaining body had zero legal moves, and the object was as welded five
    parts in as it had been at six. Turned inward, the same slide runs into
    open air, the neighbor's face caps the head instead of blocking the
    block, and the cycle unzips.

    So the pocket is blind. No bore passes through to the outer face, and
    the finished cube shows three flush bolt tips and three blank faces.

    `threaded=False` makes the own-line bore a plain slip fit -- the one
    joint a cyclic weave has to have, because the last thread in a cycle
    cannot be closed by turning: by then nothing is free to turn. `slot`
    elongates the pocket along the block's own axis, which is the only
    translation any body in this weave has, and so the way in.
    """
    w = a / 2.0
    m = bar(a, w, gap=gap)
    p_depth = t.head_h + 2 * AXIAL_SLACK
    x0 = datum(t, a, gap)

    # Its own line, L0: along x at y = a, over world x in [w+gap, a+w].
    near, far = w + gap - x0, a + w - x0
    if threaded:
        own = t.cutter(far - near + 2 * RO * t.lead, z0=near - RO * t.lead,
                       runout=[(near, RO * t.lead), (far, RO * t.lead)])
    else:
        own = trimesh.creation.cylinder(radius=t.major_r + t.clearance,
                                        height=far - near + 4.0,
                                        sections=192)
        own.apply_translation([0, 0, (near + far) / 2.0])
    cuts = [onto_x(own, (x0, a, 0)),
            onto_x(t.mouth_chamfer(near, False), (x0, a, 0)),
            onto_x(t.mouth_chamfer(far, True), (x0, a, 0))]

    # The previous bolt's line, carried there by the cyclic map -- the same
    # map that carries this block's bolt to the bolt this pocket holds.
    # Reaching the line by a different rotation instead clocks the hexagon
    # differently: the pocket came out 30 degrees from the head, which for a
    # hexagon is as far from aligned as it can be, and neither construction
    # looks wrong on its own. The head simply would not go in.
    hexp = t.hexagon(pocket_cr(t))
    if slot > 0:
        # Swept along what becomes the block's own axis: for a convex
        # section the hull of the two ends IS the sweep, and it stays one
        # simple polygon. In this frame that direction is +y; the cyclic map
        # turns it into the block's own +x.
        # Toward -y, which the cyclic map turns into the block's own -x:
        # the block has to travel the OTHER way, out of the cube and into
        # open air. Elongated the other way it would have to travel into
        # its neighbor, which is four tenths of a millimetre away, and the
        # slot buys exactly that much.
        hexp = MultiPolygon([hexp, affinity.translate(hexp, 0, -slot)]) \
            .convex_hull
    pk = trimesh.creation.extrude_polygon(hexp, p_depth + 2.0)
    pk = onto_x(pk, (x0, a, 0))
    pk.apply_transform(CYCLE @ CYCLE)
    cuts.append(pk)
    return m.difference(trimesh.boolean.union(cuts, engine="manifold"),
                        engine="manifold")


def bolt(t, a, gap=FACE_GAP):
    """The bolt for line L0: head sunk in block 1, tip flush at x = 3a/2.

    Length is derived, not chosen. The head bottoms in its pocket and the
    tip lands flush with the far outer face, so nothing protrudes anywhere
    -- which is what makes the object read as a solid block rather than as
    an assembly. Built through the same `onto_x` from the same datum as the
    bore it turns in, so the two helices are in step.
    """
    return onto_x(t.bolt(shank_len=a + gap + AXIAL_SLACK),
                  (datum(t, a, gap) + AXIAL_SLACK, a, 0))


def assemble(t, a, entry="slot", slot=4.0):
    """The six bodies in their home poses, keyed by name.

    One block and one bolt, rotated twice. Bolt i's head is captured in
    block i+1 and its thread engages block i, which is the law -- clearance
    hole near, thread far -- and the cyclic map carries the whole
    relationship round with it. The block that carries the asymmetry is
    block 0, and the bolt that slips into it is bolt 0.
    """
    plain = entry in ("slip", "slot")
    sl = slot if entry == "slot" else 0.0
    b0 = block(t, a, threaded=not plain, slot=sl)
    bl = block(t, a, threaded=True, slot=0.0)
    k0 = bolt(t, a)
    parts, m = {}, np.eye(4)
    for i in range(3):
        for name, src_ in ((f"block{i}", b0 if i == 0 else bl),
                           (f"bolt{i}", k0)):
            g = src_.copy()
            g.apply_transform(m)
            parts[name] = g
        m = CYCLE @ m
    return parts


def layout(t, a, entry="slot", slot=0.0):
    """The six parts as they go on the bed, not as they sit in the cube.

    Every block has two bores at right angles, so whichever way it lies one
    of them is horizontal. The choice is not close. Printed along its axis
    this thread's flank never exceeds 32.5 degrees from vertical, at any
    scale -- that is the property the whole family was kept for -- and
    printed across it the same bore is a 16.6 mm horizontal hole whose
    crown droops onto the crest the bolt has to turn against. So the
    threaded bore stands vertical and the hex pocket lies on its side. The
    pocket's ceiling is then one hex flat, 13 mm wide over a 13 mm depth,
    a bridge the printer manages without help; the cyclic map happens to
    clock the hexagon with a flat toward the block's own axis, which is
    the orientation that makes that true, and the bolt heads are clocked
    to match so it is not a choice that could be made differently.

    Bolts stand on their heads, thread up, for the same reason. They are
    75 mm tall on a 27 mm base and get the brim `embed` puts on by default.
    """
    from gen_puzzle import tidy
    up = trimesh.transformations.rotation_matrix(-np.pi / 2, [0, 1, 0])
    rel = t.head_h + 2 * AXIAL_SLACK
    plain = entry in ("slip", "slot")
    blocks = [block(t, a, threaded=not plain, slot=slot if entry == "slot"
                    else 0.0), block(t, a), block(t, a)]
    out = {}
    pitch = a + 8.0
    for i, g in enumerate(blocks):
        g.apply_transform(up)
        g.apply_translation([-g.bounds[0][0] + (i - 1) * pitch
                             - g.extents[0] / 2.0, -g.bounds[0][1]
                             - g.extents[1] / 2.0, -g.bounds[0][2]])
        out[f"knot_block{'_key' if i == 0 and plain else ''}{i}"] = tidy(g)
    row = a + 8.0 + t.hex_cr + 4.0
    for i in range(3):
        g = bolt(t, a)
        g.apply_transform(up)
        g.apply_translation([-g.bounds[0][0] + (i - 1) * pitch
                             - g.extents[0] / 2.0, row - g.bounds[0][1]
                             - g.extents[1] / 2.0, -g.bounds[0][2]])
        out[f"knot_bolt{i}"] = tidy(g)
    return out


def head_descends(t, a, parts):
    """The law, as a motion: bolt 0 drops into block 1's pocket unturned.

    The seed cube's first build had thread under the pocket and could never
    have been assembled, and nothing in a disassembly argument catches it --
    the head arrives at its keyway rotating, presents the right sixth of a
    turn once every 60 degrees, and lands on the face and grinds.

    Two halves, and the second is the one that means anything. Square on,
    the bolt travels the whole way by pure translation. Off-key it must
    still travel freely until the head reaches the pocket, and must foul
    there: free the whole way at 27 degrees would mean the pocket is not
    keying anything, and fouling early would mean the bore is not plain.
    """
    from assembly import Sweep, screw_path
    blk, blt = parts["block1"], parts["bolt0"]
    start = 2.0 * a                    # clear of the mouth, on the +x side
    travel = start - 0.15
    out = {}
    for deg in (0, 11, 27, 49):
        m = blt.copy()
        m.apply_transform(trimesh.transformations.rotation_matrix(
            np.radians(deg), [1, 0, 0], [0, a, 0]))
        m.apply_translation([start, 0, 0])
        s = Sweep(blk, m)
        p = screw_path(0.0, -travel, None, 0.0, s.max_r,
                       clearance=t.clearance, axis=0)
        hit = s.run(p)
        # where along the travel the head first reaches the pocket mouth
        mouth = (start - (t.head_h + 2 * AXIAL_SLACK)) / travel
        out[deg] = {"home": hit is None,
                    "free_to_pocket": hit is None or hit / (len(p) - 1)
                    >= mouth - 0.02}
    return out


def measure(t, a, parts, budget=3000):
    """The three numbers, on maximal moves.

    A move here takes a part as far as it will go, which is what a hand
    does; the search is not offered every intermediate stop. That keeps the
    state count to what a player can distinguish -- the enumerating search
    was still at depth three after a quarter of an hour, walking block 0
    through every 5 mm of a 13 mm slide -- and it makes the reported solve
    length an upper bound on the true shortest, never an underestimate,
    since maximal moves are a subset of all moves. Legal first moves is
    exact either way: it counts directions, not distances.
    """
    from mobility import Mobility, describe
    mb = Mobility(parts, lines(a), t.lead, clearance=t.clearance,
                  quantum=1e6, budget=budget)
    r = mb.solve()
    sol = r.pop("solution", None)
    if sol:
        r["solution"] = [describe(x) for x in sol]
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=float, default=None,
                    help="axis spacing; default is the derived minimum")
    ap.add_argument("--thread", type=float, default=16.0,
                    help="major diameter of the thread")
    ap.add_argument("--entry", choices=("none", "slip", "slot"),
                    default="slot")
    ap.add_argument("--float", dest="slot", type=float, default=None,
                    help="pocket elongation, mm — the way in. Default is "
                         "the release distance, which is what the slot has "
                         "to be worth to open anything")
    ap.add_argument("--measure", action="store_true",
                    help="run the depth search; it costs minutes")
    ap.add_argument("--budget", type=int, default=600)
    ap.add_argument("--out")
    a_ = ap.parse_args()

    t = Thread(major_r=a_.thread / 2.0)
    if a_.entry != "slot":
        slot = 0.0
    elif a_.slot is None:
        slot = t.head_h + 2 * AXIAL_SLACK      # clear the pocket, exactly
    else:
        slot = float(a_.slot)
    need = min_spacing(t, slot)
    a = float(np.ceil(need)) if a_.a is None else a_.a
    rep = {"part": "knot", "thread": repr(t), "entry": a_.entry,
           "spacing_mm": a, "min_spacing_mm": round(need, 2),
           "cube_mm": 2 * a, "slot_mm": round(slot, 2),
           "shank_gap_mm": round(a - 2 * t.major_r, 2),
           "pocket_wall_mm": round(a / 2.0 - t.hex_cr - POCKET_SLOP / 2.0
                                   / np.cos(np.radians(30.0)), 2)}
    if a < need:
        why = (f"spacing {a} below the derived minimum {need:.2f} — a "
               f"{slot:.1f} mm slot and {WALL_MIN} mm of wall do not both "
               f"fit in a block {a - FACE_GAP:.1f} mm long")
        print(json.dumps({"ok": False, **rep, "error": why, "failed": [why]}))
        return 1

    rep["max_slot_mm"] = round(max_slot(t, a), 2)
    rep["release_needed_mm"] = round(t.head_h + 2 * AXIAL_SLACK, 2)
    parts = assemble(t, a, entry=a_.entry, slot=slot)
    rep["bodies"] = len(parts)
    rep["watertight"] = all(m.is_watertight for m in parts.values())
    whole = trimesh.util.concatenate(list(parts.values()))
    rep["bbox_mm"] = [round(float(x), 1) for x in whole.extents]
    # Home is contact by design, so overlap is measured as volume, not as a
    # collision query: FCL calls a shared face a hit and would fail on a
    # design that is exactly right.
    import itertools
    worst = 0.0
    for x, y in itertools.combinations(sorted(parts), 2):
        worst = max(worst, float(parts[x].intersection(
            parts[y], engine="manifold").volume))
    rep["worst_overlap_mm3"] = round(worst, 2)
    # Volume says nothing about contact. Two parts can share a surface with
    # zero penetration and no overlapping volume at all, and FCL scores that
    # as a collision -- so the depth search dies on its second sample and
    # reports the design welded no matter what the design is. That is not a
    # quirk of the search either: parts built to touch cannot be printed to
    # touch. Both problems are the same missing slack.
    cm = tc.CollisionManager()
    for n, g in parts.items():
        cm.add_object(n, g)
    hit, pairs = cm.in_collision_internal(return_names=True)
    rep["touching_at_home"] = sorted("|".join(sorted(x)) for x in pairs)
    rep["head_descends"] = head_descends(t, a, parts)

    vol = sum(float(m.volume) for m in parts.values()) / 1000.0
    rep["volume_cm3"] = round(vol, 1)
    rep["est_g"] = round(vol * 1.27, 1)      # PETG, not PLA — see below
    rep["distinct_parts"] = 2 if a_.entry == "none" else 3

    hd = rep["head_descends"]
    gates = [("watertight", rep["watertight"]),
             ("no_overlap", worst < 1.0),
             ("nothing_touching", not rep["touching_at_home"]),
             ("head_seats_square_on", hd[0]["home"]),
             ("bore_is_plain", all(v["free_to_pocket"] for v in hd.values())),
             ("pocket_keys_the_head",
              not any(hd[d]["home"] for d in (11, 27, 49)))]
    if a_.measure:
        rep["depth"] = measure(t, a, parts, budget=a_.budget)
        gates.append(("comes_apart", bool(rep["depth"].get("comes_apart"))))
    failed = [n for n, ok in gates if not ok]
    ok = not failed
    if failed:
        rep["failed"] = failed
        rep["error"] = "gate failed: " + ", ".join(failed)

    plate = None
    if ok:
        plate = layout(t, a, entry=a_.entry, slot=slot)
        rep["bodies"] = sum(len(g.split(only_watertight=False))
                            for g in plate.values())
        ext = trimesh.util.concatenate(list(plate.values())).extents
        rep["plate_mm"] = [round(float(x), 1) for x in ext]
        ok = rep["bodies"] == 6
    if a_.out and ok:
        os.makedirs(os.path.dirname(a_.out), exist_ok=True)
        sc = trimesh.Scene()
        for n, g in plate.items():
            sc.add_geometry(g, geom_name=n)
        sc.export(a_.out)
        from embed_settings import embed
        # bolts stand 75 mm on a 27 mm head, lever ratio over five: brim on
        embed(a_.out)
        # the honest check is the exported file, not the mesh in memory:
        # 3MF precision collapses tangent surfaces into duplicate faces
        from meshcheck import export_defects
        bad = export_defects(a_.out)
        rep["watertight"] = not bad
        if bad:
            rep["defects"] = bad
            ok = False
        rep["file"] = os.path.basename(a_.out)
    print(json.dumps({"ok": ok, **rep}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
