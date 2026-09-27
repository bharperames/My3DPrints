#!/usr/bin/env python3
"""Tinker set: a construction kit on the Knot's Ø12 thread.

About a third the size of the Montessori nuts-and-bolts set, and the same
thread as the bolted Knot -- Ø12, 4 mm lead, 0.30 mm running clearance --
because that thread is already printed and proven in PETG. The heads are
the Knot's 16.6 mm across the flats, so one wrench fits both.

THE SYSTEM

    U = 8 mm        plate thickness, head height, nut height. Two leads.
    PITCH = 20 mm   hole grid. A 16.6 hex is 19.2 across the corners, so
                    two nuts on neighboring holes can both turn.
    Bn              a bolt that grips n plates plus a nut: shank (n+1)·U.

THE THREAD LIVES ONLY IN WHAT THE TIP REACHES

Plates carry plain Ø13 clearance holes, never thread. Turning a helix about
its axis is the same as sliding it along the axis, so a threaded plate
turned 90° is a millimeter out of phase with the one under it -- three
times the clearance. Two threaded plates would stack square in only one of
four orientations and a crossed beam would never go together. With plain
holes, any stack in any orientation either side up passes a bolt, and the
nut (hex, wing, or coupler) clamps it.

Usage: gen_tinker.py [--out FILE.3mf]
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thread import Thread                                   # noqa: E402

U = 8.0
PITCH = 20.0
HEX_AF = 16.6          # the Knot's head: 2 (R + clearance + 2 mm bearing)
CLEAR_RADIAL = 0.50    # plain bore, as proven in the Knot
RUNOUT = 1.6         # thread fade at each nut face; see threaded_hex
MOUTH = 0.6            # 45° ease on each hole mouth; the first layer squeezes
CORNER_R = 3.0
EDGE_CHAM = 0.8        # top edges; the bottom gets an elephant-foot 0.4
BED = 256.0
GAP = 3.0             # between parts on the plate; Bambu arranges at ~2-3
BRIM = {"brim_type": "outer_only", "brim_width": "5", "brim_object_gap": "0"}

T = Thread(major_r=6.0, hex_af=HEX_AF, head_h=U, head_cham=0.8)
HOLE_R = T.major_r + CLEAR_RADIAL


def _ring(poly, z):
    xy = np.asarray(poly.exterior.coords)[:-1]
    return np.column_stack([xy, np.full(len(xy), z)])


def chamfered_slab(outline, h, top=EDGE_CHAM, bottom=0.4):
    """A convex outline extruded with its top and bottom edges chamfered.

    The hull of four rings: exact for a convex outline, and no boolean.
    """
    rings = [_ring(outline.buffer(-bottom, resolution=16), 0.0),
             _ring(outline, bottom),
             _ring(outline, h - top),
             _ring(outline.buffer(-top, resolution=16), h)]
    return trimesh.convex.convex_hull(np.vstack(rings))


def clearance_hole(x, y, h, teardrop=False):
    """A plain bore along z with a 45° ease at both mouths, one revolve.

    One profile, not a cylinder plus two cones: separate cutters meeting on
    the wall leave the exported mesh non-manifold. `teardrop` adds a 45°
    roof toward +y, for a bore that will print lying down.
    """
    r, m = HOLE_R, MOUTH
    prof = np.array([(0.5, -1.0), (r + m + 1.0, -1.0), (r, m),
                     (r, h - m), (r + m + 1.0, h + 1.0), (0.5, h + 1.0),
                     (0.5, -1.0)])
    c = trimesh.creation.revolve(prof, sections=96)
    # the revolve stays off the axis (a profile through r=0 leaves
    # degenerate polar triangles), so its core is filled separately --
    # without it every hole keeps a 1 mm pin standing in the middle
    core = trimesh.creation.cylinder(radius=1.0, height=h + 2.0, sections=24)
    core.apply_translation([0, 0, h / 2])
    c = trimesh.boolean.union([c, core], engine="manifold")
    if teardrop:
        s = r * np.sqrt(.5)
        roof = trimesh.creation.extrude_polygon(
            Polygon([(-s, s), (0, r * np.sqrt(2)), (s, s), (0, 0)]),
            h + 2.0)
        roof.apply_translation([0, 0, -1.0])
        c = trimesh.boolean.union([c, roof], engine="manifold")
    c.apply_translation([x, y, 0])
    return c


def plate(nx, ny):
    w, d = nx * PITCH, ny * PITCH
    outline = box(0, 0, w, d).buffer(-CORNER_R).buffer(CORNER_R,
                                                       resolution=16)
    slab = chamfered_slab(outline, U)
    cuts = [clearance_hole(PITCH * (i + .5), PITCH * (j + .5), U)
            for i in range(nx) for j in range(ny)]
    return slab.difference(trimesh.boolean.union(cuts, engine="manifold"),
                           engine="manifold")


def l_bracket():
    """Two 1x2 legs at 90°. Printed on the flat leg: its holes are vertical,
    the upright leg's are horizontal and get a teardrop roof.

    Holes sit 10 mm from the inside face, as on every plate, so a bracket
    lands its holes on the same grid as the plates it joins.
    """
    L = U + 2 * PITCH                     # 48: leg thickness + two pitches
    prof = Polygon([(0, 0), (L, 0), (L, U), (U, U), (U, L), (0, L)])
    body = trimesh.creation.extrude_polygon(prof, PITCH)
    body.apply_transform(trimesh.transformations.rotation_matrix(
        np.pi / 2, [1, 0, 0]))            # profile into x-z, width along -y
    body.apply_translation([0, PITCH, 0])
    # a bore built along z with its roof at +y, turned so the bore runs
    # along x and the roof points up: x->y, y->z, z->x
    P = np.eye(4)
    P[:3, :3] = [[0, 0, 1], [1, 0, 0], [0, 1, 0]]
    cuts = []
    for k in (1, 2):
        c = U + PITCH * (k - .5)                            # 18, 38
        cuts.append(clearance_hole(c, PITCH / 2, U))        # flat leg
        b = clearance_hole(0, 0, U, teardrop=True)
        b.apply_transform(P)
        b.apply_translation([0, PITCH / 2, c])              # upright leg
        cuts.append(b)
    return body.difference(trimesh.boolean.union(cuts, engine="manifold"),
                           engine="manifold")


def wheel(d=40.0, groove=1.5):
    """A disc on a clearance bore, with a V groove for a band tire and four
    windows so it reads as a wheel."""
    h, r = U, d / 2
    prof = np.array([(0.5, 0), (r - 0.4, 0), (r, 0.4),
                     (r, h / 2 - groove), (r - groove, h / 2),
                     (r, h / 2 + groove), (r, h - EDGE_CHAM),
                     (r - EDGE_CHAM, h), (0.5, h), (0.5, 0)])
    solid = trimesh.creation.revolve(prof, sections=192)
    cuts = [clearance_hole(0, 0, h)]
    for k in range(4):
        a = np.radians(45 + 90 * k)
        w = trimesh.creation.cylinder(radius=4.0, height=h + 2, sections=48)
        w.apply_translation([11.5 * np.cos(a), 11.5 * np.sin(a), h / 2])
        cuts.append(w)
    return solid.difference(trimesh.boolean.union(cuts, engine="manifold"),
                            engine="manifold")


def bolt(n):
    return T.bolt(shank_len=(n + 1) * U, head_h=U)


def threaded_hex(h):
    """A hex nut of height h on the family thread, faded out only as far
    as the mouth chamfer needs.

    Thread.nut() fades over a whole lead at each end. On the Knot's long
    bores that costs nothing; on an 8 mm nut the two fades meet in the
    middle and the thread reaches full depth only at the midplane --
    0.91 turns of effective engagement. Fading over RUNOUT instead gives
    1.35 turns -- 1.18 once the bed mouth is a true cone (bed_mouth).
    """
    body = T.head(height=h)
    return body.difference(nut_cutter(h), engine="manifold")


def bed_mouth():
    """The lead-in on the mouth that prints against the bed.

    One 45° cone from the chamfer's outer edge all the way in to the
    thread's crest, with nothing flat anywhere on it.

    Thread.mouth_chamfer() stops at the major radius under a FLAT roof.
    Opening upward that roof is a floor and harmless; opening onto the bed
    it is a ring-shaped ceiling 1.3 mm up, and every crest above it hangs
    over air. The slicer laid 87 mm of bridge and 18 mm of overhang wall
    there, in a ring right round the inside of the hole -- the strands
    across the opening -- and the shorter run-out made it four times worse
    by putting more crest above the roof. Carried in to the crest, the
    cone meets the thread at 45° everywhere: that layer slices with no
    bridge at all, and grip drops only from 1.35 to 1.18 turns.
    """
    outer = T.major_r + T.clearance + 1.0
    to_r = T.minor_r + T.clearance
    rise = outer - to_r
    prof = np.array([(to_r - 1.0, 0.0), (outer, 0.0), (to_r, rise),
                     (to_r - 1.0, rise + 1.0), (to_r - 1.0, 0.0)])
    return trimesh.creation.revolve(prof, sections=96)


def nut_cutter(h):
    return trimesh.boolean.union(
        [T.cutter(h + 2 * T.lead, z0=-T.lead,
                  runout=[(0.0, RUNOUT), (h, RUNOUT)]),
         T.mouth_chamfer(h, True), bed_mouth()],
        engine="manifold")


def nut():
    return threaded_hex(U)


def coupler():
    """A long nut: two bolts meet in it end to end."""
    return threaded_hex(2 * U)


def wing_nut(span=16.0, wing_t=3.6, wing_h=11.0):
    """A round boss with two upright wings, turned by fingers.

    Printed as it stands: the wings are vertical fins rooted on the bed.
    """
    boss_r = HEX_AF / 2
    boss = trimesh.creation.cylinder(radius=boss_r, height=U, sections=96)
    boss.apply_translation([0, 0, U / 2])
    # a wing in the x-z plane: rooted inside the boss, rising to a rounded top
    top = Point(span - 3.5, wing_h - 3.5).buffer(3.5, resolution=24)
    prof = unary_union([Polygon([(boss_r - 2, 0), (span, 0),
                                 (span, wing_h - 3.5), (span - 3.5, wing_h),
                                 # the slope lands on the boss's rim, not
                                 # inside it: inside, the wing stood above
                                 # the boss top as a blade beside the bore
                                 (boss_r, U), (boss_r - 2, U)]), top])
    prof = prof.intersection(box(boss_r - 2, 0, span, wing_h))
    parts = [boss]
    for s in (1, -1):
        w = trimesh.creation.extrude_polygon(prof, wing_t)
        w.apply_transform(trimesh.transformations.rotation_matrix(
            np.pi / 2, [1, 0, 0]))
        w.apply_translation([0, wing_t / 2, 0])
        if s < 0:
            w.apply_transform(trimesh.transformations.rotation_matrix(
                np.pi, [0, 0, 1]))
        parts.append(w)
    body = trimesh.boolean.union(parts, engine="manifold")
    return body.difference(nut_cutter(U), engine="manifold")


def double_bolt(side=2 * U):
    """A stud: thread both ends, a hex collar between them.

    Printed standing on one end, so the lower thread is the part's only
    footprint and the collar's underside is a ceiling. That underside bears
    on a plate, so it cannot simply be coned away: it keeps a flat ring out
    to BEAR_R -- past the plate's mouth ease -- and runs out at 45° beyond.
    The lower end is cut square, not eased, because it is what the part
    stands on.
    """
    BEAR_R = HOLE_R + MOUTH + 1.0
    h0 = side                                  # collar bottom
    lower = T.rod(side + 0.01, z0=0.0)
    upper = T.rod(side + 0.01, z0=h0 + U - 0.01)
    tip = h0 + U + side
    ease = T.amp * 2.0
    prof = np.array([(0.5, h0 + U - 1), (T.major_r + 1, h0 + U - 1),
                     (T.major_r + 1, tip - ease), (T.minor_r - 0.5, tip),
                     (0.5, tip), (0.5, h0 + U - 1)])
    upper = upper.intersection(trimesh.creation.revolve(prof, sections=192),
                               engine="manifold")
    collar = T.head(z0=h0, height=U)
    cr = T.hex_cr + 1.0
    under = np.array([(0.5, h0 - 0.01), (BEAR_R, h0 - 0.01),
                      (cr, h0 + (cr - BEAR_R)), (cr, h0 + U + 1),
                      (0.5, h0 + U + 1), (0.5, h0 - 0.01)])
    collar = collar.intersection(trimesh.creation.revolve(under, sections=192),
                                 engine="manifold")
    return trimesh.boolean.union([lower, collar, upper], engine="manifold")


# name, builder, count, brim
# name, dial key, builder, default count, brim. The dial key is what the
# shop card passes as --KEY N; the card's own list is checked against this
# one by tests/test_tinker.py, so the two cannot drift. Only the double
# bolt takes a brim: it stands 40 mm tall on the end of its own thread.
# Every bolt stands on its hex head and needs none.
SET = [
    ("plate_2x4", "p2x4", lambda: plate(2, 4), 2, False),
    ("plate_2x2", "p2x2", lambda: plate(2, 2), 2, False),
    ("plate_1x4", "p1x4", lambda: plate(1, 4), 3, False),
    ("plate_1x2", "p1x2", lambda: plate(1, 2), 4, False),
    ("bracket_L", "bracket", l_bracket, 2, False),
    ("wheel", "wheel", wheel, 2, False),
    ("bolt_B1", "b1", lambda: bolt(1), 2, False),
    ("bolt_B2", "b2", lambda: bolt(2), 10, False),
    ("bolt_B3", "b3", lambda: bolt(3), 5, False),
    ("bolt_B4", "b4", lambda: bolt(4), 5, False),
    ("double_bolt", "double", double_bolt, 3, True),
    ("coupler", "coupler", coupler, 3, False),
    ("wing_nut", "wing", wing_nut, 4, False),
    ("nut", "nut", nut, 24, False),
]


def pack(items, bed=BED, gap=GAP, margin=6.0, res=1.0):
    """First fit, largest footprint first, on a 1 mm occupancy grid.

    Each part claims its bounding box grown by the gap (a brimmed part by
    the brim too), and goes at the lowest, then leftmost, free spot. Rows
    would leave every nut-sized hole beside a tall plate empty.
    Returns (name, mesh, x, y).
    """
    n = int(bed / res)
    occ = np.zeros((n, n), bool)
    lo, hi = int(margin / res), int((bed - margin) / res)
    out = []
    order = sorted(items, key=lambda it: -(it[1].extents[0] * it[1].extents[1]))
    for name, m, pad in order:
        w = int(np.ceil((m.extents[0] + 2 * pad) / res))
        d = int(np.ceil((m.extents[1] + 2 * pad) / res))
        g = int(np.ceil(gap / res))
        # integral image: a window is free when its sum is zero
        ii = np.pad(occ.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        spot = None
        for y in range(lo, hi - d + 1):
            row = (ii[y + d, lo + w:hi + 1] - ii[y, lo + w:hi + 1]
                   - ii[y + d, lo:hi - w + 1] + ii[y, lo:hi - w + 1])
            free = np.flatnonzero(row == 0)
            if free.size:
                spot = (lo + int(free[0]), y)
                break
        if spot is None:
            raise ValueError(f"set does not fit the bed at {name}")
        x, y = spot
        occ[max(0, y - g):y + d + g, max(0, x - g):x + w + g] = True
        out.append((name, m, x * res + pad, y * res + pad))
    return out


def main():
    ap = argparse.ArgumentParser()
    for name, key, _, count, _ in SET:
        ap.add_argument(f"--{key}", type=int, default=count,
                        help=f"how many {name}")
    ap.add_argument("--out")
    a = ap.parse_args()
    counts = {name: max(0, getattr(a, key)) for name, key, _, _, _ in SET}
    if not sum(counts.values()):
        return _answer(False, error="every count is zero: nothing to print")
    built, bodies = {}, []
    for name, _, fn, _, brim in SET:
        if not counts[name]:
            continue
        m = fn()
        m.apply_translation(-m.bounds[0])          # on the bed, at origin
        built[name] = (m, brim)
        pad = float(BRIM["brim_width"]) if brim else 0.0
        bodies += [(f"{name}_{i + 1}", m.copy(), pad)
                   for i in range(counts[name])]
    # The shop does its own arranging: it splits this file into its pieces
    # (they never overlap, so plateshop.pieces reads them as separate
    # objects) and packs them onto as many plates as the order takes. So a
    # set bigger than one bed is not an error here -- the layout just grows,
    # and a set that does fit comes out as a ready plate on its own.
    bed = BED
    while True:
        try:
            placed = pack(bodies, bed=bed)
            break
        except ValueError:
            bed += PITCH * 4
    rep = {"part": "tinker-set", "thread": repr(T), "U_mm": U,
           "pitch_mm": PITCH, "hex_af": HEX_AF,
           "hex_across_corners": round(T.hex_cr * 2, 2),
           "hole_d": round(2 * HOLE_R, 2), "pieces": len(placed)}
    rep["watertight"] = {n: bool(m.is_watertight) for n, (m, _) in
                         built.items()}
    rep["bodies_each"] = {n: len(m.split(only_watertight=False))
                          for n, (m, _) in built.items()}
    rep["heights"] = {n: round(float(m.extents[2]), 1) for n, (m, _) in
                      built.items()}
    vol = sum(float(m.volume) for _, m, _, _ in placed) / 1000
    rep["solid_cm3"] = round(vol, 1)
    ext = max(x + m.extents[0] for _, m, x, _ in placed), \
        max(y + m.extents[1] for _, m, _, y in placed)
    rep["used_mm"] = [round(float(e), 1) for e in ext]
    ok = all(rep["watertight"].values()) and \
        all(v == 1 for v in rep["bodies_each"].values())
    if a.out and ok:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        sc = trimesh.Scene()
        for name, m, x, y in placed:
            g = m.copy()
            g.apply_translation([x, y, 0])
            sc.add_geometry(g, geom_name=name)
        sc.export(a.out)
        from embed_settings import embed
        brims = {n: dict(BRIM) for n, m, _, _ in placed
                 if built[n.rsplit("_", 1)[0]][1]}
        embed(a.out, brim=False, per_object=brims)
        from meshcheck import export_defects
        bad = export_defects(a.out)
        if bad:
            rep["defects"] = bad
            ok = False
        rep["file"] = os.path.basename(a.out)
    rep["counts"] = {k: counts[n] for n, k, _, _, _ in SET}
    return _answer(ok, **rep)


def _answer(ok, **rep):
    """One line of JSON: the shop reads the last line of stdout as the
    report, so an indented dump would be read as a lone closing brace."""
    print(json.dumps({"ok": ok, **rep}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
