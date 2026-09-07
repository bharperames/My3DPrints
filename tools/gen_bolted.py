#!/usr/bin/env python3
"""The Knot, bolted: three bars each clamped to the next by a through bolt.

WHAT THE BURR GOT WRONG

`gen_knot.py` holds three bars together by sinking each bolt's head in the
NEXT bar's blind socket. Nothing is clamped: a head in a blind socket
resists sideways and resists nothing at all against a pull, and the object
came apart under half a newton -- fifty grams -- of outward pull. Worse, it
came apart for a reason no swept path could see: its release is a three-move
SEQUENCE, and the first move of that sequence points the same way you pull,
so handling the object performs its own solution.

WHAT THIS DOES INSTEAD

Every bolt goes right THROUGH the bar it is captured in and threads into the
next one:

    bolt i   head keyed in bar i's hex counterbore, at bar i's OUTER face
             shank running the length of bar i in a clearance bore
             thread engaging bar i+1 over that bar's whole length

so bar i is clamped to bar i+1 by a screw in tension, three times round.
Pull on it now and the load goes into a thread, not into a head sliding out
of a hole. There is no direction to pull that does anything, because the
only motion that ever separates two bars is one bolt UNSCREWING, and a pull
cannot turn a screw.

WHY IT LOCKS

Each bar has two bores on perpendicular axes: a clearance bore on its own
line, and a threaded bore on the previous line. A bar cannot translate --
either bore's shank blocks it sideways -- and it cannot rotate about its own
line either, because that swings its threaded bore around a shank that is
not going anywhere. And a bolt cannot turn independently of the bar its head
is keyed to. So every bolt is held by a bar that cannot move, and the ring
is closed.

Which makes it welded, and a welded assembly cannot be assembled either. One
release has to be built in, and the choice of WHICH release is the whole
design, because it decides what the puzzle is.

    --entry free    one bolt's counterbore is round instead of hex, so that
                    bolt alone can turn. It is sunk flush, so there is
                    nothing to grip but the hex itself: the puzzle is
                    finding that one of three identical-looking faces turns,
                    and having something to turn it with. Pulling still does
                    nothing -- the release is a rotation.
    --entry none    all three keyed, for the negative control. It must
                    measure welded, and it must fail the assembly gate,
                    because the two are the same fact read backwards.

Usage: gen_bolted.py [--a MM] [--thread MM] [--entry none|free] [--out F.3mf]
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh
import trimesh.collision as tc
from shapely.geometry import Point

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_knot as k                                        # noqa: E402
from thread import Thread                                   # noqa: E402

WALL_MIN = 4.0
POCKET_SLOP = 0.50
RO = 0.75
FACE_GAP = 0.20
AXIAL_SLACK = 0.15
CLOCK_SLACK = 0.40     # a hex head meets its keyway at one of six angles
BEARING = 2.0          # annulus of counterbore floor the head bears on
KEY_DEPTH = 5.0        # head height, and so hex engagement


def thread_for(major_d):
    r = major_d / 2.0
    clr = Thread(major_r=r).clearance
    return Thread(major_r=r, clearance=clr,
                  hex_af=2.0 * (r + clr + BEARING),
                  head_h=KEY_DEPTH, head_cham=0.8)


def pocket_cr(t):
    return t.hex_cr + POCKET_SLOP / 2.0 / np.cos(np.radians(30.0))


def pocket_depth(t):
    return t.head_h + 2 * AXIAL_SLACK + CLOCK_SLACK


def min_spacing(t, gap=FACE_GAP):
    """No slot to fit any more, so the counterbore alone sets the size.

    The burr had to swallow a slide as long as its pocket was deep, which
    forced a 68 mm cube. A clamped bolt needs no slide, so the bar only has
    to be wide enough for the head's counterbore with wall around it.
    """
    return max(2.0 * (pocket_cr(t) + WALL_MIN + gap),
               2.0 * (t.major_r + t.clearance + WALL_MIN + gap))


def bar_solid(a, w, gap=FACE_GAP):
    lo = np.array([w + gap, -w, -w])
    hi = np.array([a + w, a + w, w - gap])
    m = trimesh.creation.box(hi - lo)
    m.apply_translation((lo + hi) / 2.0)
    return k._break_edges(m, 2.0)


def datum(t, a, gap=FACE_GAP):
    """Head bottom on line L0 -- one origin for the bore and for the bolt.

    Everything is laid out in this single coordinate and carried to the
    other two lines by the cyclic map, so the helix cannot go out of phase
    and the hexagon cannot come out clocked differently from the head that
    fills it.
    """
    return -a / 2.0 + AXIAL_SLACK


def bar(t, a, keyed=True, gap=FACE_GAP):
    """One bar: a threaded bore on its own line, and on the previous line a
    clearance bore right through with a counterbore at the outer face.

    So the bolt whose head this bar holds does not stop in it -- it passes
    through and bites the NEXT bar. That is the whole difference from the
    burr: the joint is a screw in tension rather than a head resting
    sideways in a blind hole.
    """
    w = a / 2.0
    m = bar_solid(a, w, gap)
    x0 = datum(t, a, gap)

    # its OWN line L0: the thread, over this bar's x extent [w+gap, a+w]
    near, far = (w + gap) - x0, (a + w) - x0
    own = t.cutter(far - near + 2 * RO * t.lead, z0=near - RO * t.lead,
                   runout=[(near, RO * t.lead), (far, RO * t.lead)])
    cuts = [k.onto_x(own, (x0, a, 0)),
            k.onto_x(t.mouth_chamfer(near, False), (x0, a, 0)),
            k.onto_x(t.mouth_chamfer(far, True), (x0, a, 0))]

    # the PREVIOUS line: clearance right through, counterbore at the outer
    # face, built on L0 and carried round by the map that carries the bolt
    thru = trimesh.creation.cylinder(radius=t.major_r + t.clearance,
                                     height=2 * a, sections=192)
    thru.apply_translation([0, 0, a / 2.0 - x0 - a / 2.0])
    prof = (t.hexagon(pocket_cr(t)) if keyed
            else Point(0, 0).buffer(pocket_cr(t), resolution=64))
    cb = trimesh.creation.extrude_polygon(prof, pocket_depth(t))
    cb.apply_translation([0, 0, -AXIAL_SLACK])
    for g in (thru, cb):
        h = k.onto_x(g, (x0, a, 0))
        h.apply_transform(k.CYCLE @ k.CYCLE)
        cuts.append(h)
    return m.difference(trimesh.boolean.union(cuts, engine="manifold"),
                        engine="manifold")


def bolt(t, a, gap=FACE_GAP):
    """Head at one bar's outer face, tip flush with the next bar's far face.

    Length is derived: it has to reach right through the bar it is captured
    in and all the way across the one it threads into, so that the thread
    has that bar's whole length to bite and nothing protrudes at either end.
    """
    w = a / 2.0
    x0 = datum(t, a, gap)
    return k.onto_x(t.bolt(shank_len=(a + w) - x0 - t.head_h), (x0, a, 0))


def assemble(t, a, entry="free", gap=FACE_GAP):
    b_key = bar(t, a, keyed=(entry == "none"), gap=gap)
    b_std = bar(t, a, keyed=True, gap=gap)
    k0 = bolt(t, a, gap)
    parts, m = {}, np.eye(4)
    for i in range(3):
        for name, src in ((f"bar{i}", b_key if i == 0 else b_std),
                          (f"bolt{i}", k0)):
            g = src.copy()
            g.apply_transform(m)
            parts[name] = g
        m = k.CYCLE @ m
    return parts


def layout(t, a, entry="free", gap=FACE_GAP):
    """Six parts on the bed. Threaded bores stand vertical, because printed
    along its axis this thread's flank never exceeds 32.5 degrees from
    vertical at any scale, and printed across it the same bore is a 12.6 mm
    horizontal hole whose crown droops onto the crest the bolt turns on.
    The clearance bore and its counterbore then lie on their sides, which
    they can afford to: nothing threads in them."""
    from gen_puzzle import tidy
    up = trimesh.transformations.rotation_matrix(-np.pi / 2, [0, 1, 0])
    out, pitch = {}, a + 10.0
    bars = [bar(t, a, keyed=(entry == "none"), gap=gap),
            bar(t, a, keyed=True, gap=gap), bar(t, a, keyed=True, gap=gap)]
    for i, g in enumerate(bars):
        g.apply_transform(up)
        g.apply_translation([-g.bounds[0][0] + (i - 1) * pitch - g.extents[0] / 2,
                             -g.bounds[0][1] - g.extents[1] / 2,
                             -g.bounds[0][2]])
        out[f"knot_bar{'_key' if i == 0 and entry != 'none' else ''}{i}"] = tidy(g)
    row = a + 10.0 + t.hex_cr + 6.0
    for i in range(3):
        g = bolt(t, a, gap)
        g.apply_transform(up)
        g.apply_translation([-g.bounds[0][0] + (i - 1) * pitch - g.extents[0] / 2,
                             row - g.bounds[0][1] - g.extents[1] / 2,
                             -g.bounds[0][2]])
        out[f"knot_bolt{i}"] = tidy(g)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thread", type=float, default=12.0)
    ap.add_argument("--a", type=float, default=None)
    ap.add_argument("--entry", choices=("none", "free"), default="free")
    ap.add_argument("--out")
    A = ap.parse_args()
    t = thread_for(A.thread)
    need = min_spacing(t)
    a = float(np.ceil(need)) if A.a is None else A.a
    rep = {"part": "knot-bolted", "thread": repr(t), "entry": A.entry,
           "spacing_mm": a, "min_spacing_mm": round(need, 2), "cube_mm": 2 * a,
           "head_af_mm": round(t.hex_af, 2), "head_h_mm": t.head_h,
           "counterbore_mm": round(pocket_depth(t), 2),
           "wall_mm": round(a / 2.0 - pocket_cr(t), 2)}
    if a < need:
        why = (f"spacing {a} below the derived minimum {need:.2f} — the "
               f"counterbore would leave under {WALL_MIN} mm of wall")
        print(json.dumps({"ok": False, **rep, "error": why}))
        return 1
    parts = assemble(t, a, entry=A.entry, gap=FACE_GAP)
    rep["watertight"] = all(m.is_watertight for m in parts.values())
    import itertools
    worst = max(float(parts[x].intersection(parts[y], engine="manifold").volume)
                for x, y in itertools.combinations(sorted(parts), 2))
    rep["worst_overlap_mm3"] = round(worst, 2)
    cm = tc.CollisionManager()
    for n, g in parts.items():
        cm.add_object(n, g)
    rep["touching_at_home"] = sorted("|".join(sorted(x))
                                     for x in cm.in_collision_internal(
                                         return_names=True)[1])
    plate = layout(t, a, entry=A.entry)
    rep["bodies"] = sum(len(g.split(only_watertight=False))
                        for g in plate.values())
    ext = trimesh.util.concatenate(list(plate.values())).extents
    rep["plate_mm"] = [round(float(x), 1) for x in ext]
    vol = sum(float(g.volume) for g in plate.values()) / 1000.0
    rep["volume_cm3"] = round(vol, 1)
    rep["est_g"] = round(vol * 1.27, 1)
    gates = [("watertight", rep["watertight"]),
             ("no_overlap", worst < 1.0),
             ("nothing_touching", not rep["touching_at_home"]),
             ("six_bodies", rep["bodies"] == 6)]
    failed = [n for n, ok in gates if not ok]
    ok = not failed
    if failed:
        rep["failed"] = failed
        rep["error"] = "gate failed: " + ", ".join(failed)
    if A.out and ok:
        os.makedirs(os.path.dirname(A.out), exist_ok=True)
        sc = trimesh.Scene()
        for n, g in plate.items():
            sc.add_geometry(g, geom_name=n)
        sc.export(A.out)
        from embed_settings import embed
        embed(A.out, brim=False)
        from meshcheck import export_defects
        bad = export_defects(A.out)
        rep["watertight"] = not bad
        if bad:
            rep["defects"] = bad
            ok = False
        rep["file"] = os.path.basename(A.out)
    print(json.dumps({"ok": ok, **rep}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
