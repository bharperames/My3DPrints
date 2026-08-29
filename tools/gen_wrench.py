#!/usr/bin/env python3
"""Toy wrench for the Montessori nuts and bolts.

Combination spanner: a six-point box end at one end, an open jaw at the
other, both sized to the same hex. The nut and the bolt heads measure
49.68 and 49.78 mm across the flats, so one wrench drives all of them.

Like the clasp, it is a flat profile extruded in Z: no supports, no
bridges, no overhangs, and the whole silhouette lands on the bed. The
extrusion is deliberately thinner than the hex's full-width band — the
heads chamfer above and below, leaving about 18 mm of true flat — so the
jaw grips flat on flat rather than riding up a chamfer.

Fit is proved against the designer's own nut, not against a drawing: it
is dropped into the box end and slid into the jaw, and FCL has to report
a gap inside a band. Too tight and it will not go on; too loose and a
toy wrench rounds the corners it is supposed to turn.

Usage: gen_wrench.py [--af MM] [--thick MM] [--out FILE.3mf]
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

AF = 49.78              # hex across flats, measured off the source model
NUT_CR = 28.93          # and across-corners/2. Not af/sqrt(3): the real
                        # hex's corners sit prouder than a regular one's,
                        # and assuming regular put the rear corner 0.2 mm
                        # into the throat
CLR = 1.4               # on the flats; 0.75 measured 0.12 mm against
                        # the real nut, whose corners sit slightly
                        # prouder than a regular hexagon's
BOX_WALL = 7.5          # material around the box bore, at the corners
JAW_ARM = 13.5          # open-jaw arm; real spanners run ~0.28x across-flats,
                        # and 8 mm here failed the bending gate at 81 MPa
THICK = 14.0            # extrusion; the hex's flat band is ~18 mm
JAW_DEG = 15.0          # open jaw angle, as a real spanner has
THROAT_FWD = 12.0       # throat ahead of the head centre
JAW_DEPTH = 27.5        # tip to throat; real spanners run ~0.55x AF
GRIP_W = 26.0           # handle width at the grip
MIN_WALL = 5.0
FIT_MIN, FIT_MAX = 0.25, 1.1
PLA_YIELD = 50.0        # MPa
HAND_N = 40.0           # a determined child, at the end of the handle


def hexagon(across_flats, rot=0.0, cx=0.0, cy=0.0):
    r = across_flats / np.sqrt(3)          # circumradius
    a = np.radians(np.arange(6) * 60.0 + rot)
    return Polygon(np.column_stack([cx + r * np.cos(a), cy + r * np.sin(a)]))


def build(af=AF, thick=THICK, clr=CLR, box_wall=BOX_WALL,
          jaw_arm=JAW_ARM):
    rep = {}
    bore_af = af + clr
    bore_cr = bore_af / np.sqrt(3)
    r_box = bore_cr + box_wall
    span = af * 3.2                        # centre to centre
    r_open = bore_af / 2 + jaw_arm

    box = Point(0, 0).buffer(r_box, 96)
    # The open head is a rounded rectangle, not a disc. A disc tapers both
    # jaw arms to points at the tips; a real spanner keeps them parallel and
    # squares the tips off, which is also where the grip actually is.
    ang0 = np.radians(JAW_DEG)
    d0 = np.array([np.cos(ang0), np.sin(ang0)])
    tip = span + THROAT_FWD + JAW_DEPTH
    back = bore_af / 2 - THROAT_FWD + MIN_WALL + 3.0
    head = (LineString([np.array([span, 0.0]) - d0 * back,
                        np.array([span, 0.0]) + d0 * (tip - span)])
            .buffer(r_open, cap_style=2, resolution=24)
            .buffer(-7.0, join_style=1).buffer(7.0, join_style=1))
    # handle: a tapered waist between the two heads, pinched in the middle
    hw, mw = GRIP_W / 2, GRIP_W / 2 * 0.82
    handle = Polygon([(0, hw), (span * 0.42, mw), (span, hw),
                      (span, -hw), (span * 0.42, -mw), (0, -hw)])
    body = unary_union([box, head, handle])

    # six-point box bore, clocked so a flat faces the handle
    # clocked to the nut's own 30 deg, so the part sits the way the
    # nut does rather than needing a mental half-flat turn
    bore = hexagon(bore_af, rot=30.0)
    # open jaw: a stadium slot from the throat out past the head's edge
    ang = np.radians(JAW_DEG)
    d = np.array([np.cos(ang), np.sin(ang)])
    # A real spanner's throat is a semicircle of exactly across-flats/2, which
    # is what lets the hex's rear corner nest instead of butting a flat wall.
    # Seat the nut on the head's centre and put the throat one corner-overhang
    # behind it: corner radius minus half the flats.
    # Jaw geometry, from the constraint rather than by eye. A hex will not
    # enter a round-capped slot past the point where its rear pair of side
    # corners — half a corner-radius back, 0.866 out — fall behind the throat
    # plane, since the cap cannot reach them. So the throat sits forward of
    # the head centre and the nut seats a half corner-radius in front of it.
    centre = np.array([span, 0.0])
    throat = centre + d * THROAT_FWD
    seat = throat + d * (NUT_CR / 2 + 1.0)
    slot = LineString([throat, throat + d * (r_open + af)]
                      ).buffer(bore_af / 2, cap_style=1, resolution=32)
    wrench = body.difference(bore).difference(slot)
    if wrench.geom_type != "Polygon":
        raise ValueError("the jaw slot cut the wrench into pieces")

    # --- measured gates ------------------------------------------------
    ring = min(Point(bore_cr * np.cos(t), bore_cr * np.sin(t)).distance(
        box.exterior) for t in np.radians(np.arange(0, 360, 2)))
    rep["box_wall_mm"] = round(float(ring), 2)
    if ring < MIN_WALL:
        raise ValueError(f"box wall thins to {ring:.1f} mm (min {MIN_WALL})")
    rep["jaw_arm_mm"] = round(float(jaw_arm), 2)
    if jaw_arm < MIN_WALL:
        raise ValueError(f"jaw arms are {jaw_arm:.1f} mm (min {MIN_WALL})")

    # bending at the jaw root: the arm is a cantilever taking half the load
    lever = span + r_open
    torque = HAND_N * lever                       # N*mm
    force_at_flat = torque / (af / 2)             # N on one flat
    Z = thick * jaw_arm ** 2 / 6                  # mm^3
    stress = force_at_flat * (bore_af * 0.6) / Z  # MPa
    rep.update(lever_mm=round(lever, 1), torque_Nmm=round(torque),
               jaw_stress_MPa=round(float(stress), 1),
               safety=round(PLA_YIELD / max(stress, 1e-6), 2))
    if stress > PLA_YIELD / 2:
        raise ValueError(f"jaw stress {stress:.0f} MPa at {HAND_N:.0f} N "
                         f"— under half of PLA's {PLA_YIELD:.0f} MPa yield "
                         f"is the bar; thicken the arms")
    rep.update(across_flats=af, bore_af=round(bore_af, 2),
               length_mm=round(float(wrench.bounds[2] - wrench.bounds[0]), 1),
               width_mm=round(float(wrench.bounds[3] - wrench.bounds[1]), 1),
               thick_mm=thick, bed_mm2=round(wrench.area))
    behind = back - (bore_af / 2 - THROAT_FWD)
    rep.update(jaw_depth_mm=round(float(JAW_DEPTH), 1),
               grip_past_nut_mm=round(float(JAW_DEPTH - NUT_CR / 2 - 1.0), 1),
               behind_throat_mm=round(float(behind), 1))
    if behind < MIN_WALL:
        raise ValueError(f"only {behind:.1f} mm of head behind the throat "
                         f"(min {MIN_WALL}) — the slot would cut it off")
    return wrench, rep, dict(span=span, bore_af=bore_af, r_open=r_open,
                             throat=throat, seat=seat, ang=ang)


def fit_test(mesh, nut, at, thick, sweep=1.0):
    """Seat the designer's nut in a hole and measure the gap when clocked.

    A hex seats one way (every 60 deg). Sweeping and taking the smallest
    collision-free gap reports the worst near-miss instead — what matters is
    the best seating the part actually reaches, so take the largest.
    """
    import trimesh.collision as tc
    cm = tc.CollisionManager()
    cm.add_object("wrench", mesh)

    def probe(deg):
        T = trimesh.transformations.rotation_matrix(np.radians(deg), [0, 0, 1])
        T[0, 3], T[1, 3] = at[0], at[1]
        T[2, 3] = thick / 2 - 15.0            # centre the hex band on the jaw
        if cm.in_collision_single(nut, transform=T):
            return None
        return float(cm.min_distance_single(nut, transform=T))

    best, free = None, 0
    for deg in np.arange(0, 60, sweep):
        g = probe(deg)
        if g is None:
            continue
        free += 1
        if best is None or g > best[0]:
            best = (g, float(deg))
    if best is None:
        return None
    # refine around the best: a coarse sweep lands off the true clocking and
    # under-reports the gap, which would make the answer depend on step size
    step = sweep / 4
    while step > 0.05:
        for deg in (best[1] - step, best[1] + step):
            g = probe(deg)
            if g is not None and g > best[0]:
                best = (g, deg)
        step /= 2
    return (best[0], best[1], free)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--af", type=float, default=AF)
    ap.add_argument("--thick", type=float, default=THICK)
    ap.add_argument("--out")
    a = ap.parse_args()
    try:
        prof, rep, geo = build(a.af, a.thick)
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    m = trimesh.creation.extrude_polygon(prof, a.thick)
    rep["watertight_mesh"] = bool(m.is_watertight)

    # fit against the real nut, in both ends
    try:
        import gen_montessori as GM
        nut, _ = GM.source_parts()
        nut = nut.copy()
        nut.apply_translation([0, 0, -nut.bounds[0][2]])
        box_fit = fit_test(m, nut, (0.0, 0.0), a.thick)
        jaw_at = geo["seat"]
        jaw_fit = fit_test(m, nut, jaw_at, a.thick)
        rep["box_fit_mm"] = None if box_fit is None else round(box_fit[0], 2)
        rep["jaw_fit_mm"] = None if jaw_fit is None else round(jaw_fit[0], 2)
        rep["box_clock_deg"] = None if box_fit is None else box_fit[1]
        rep["seating_angles"] = [None if f is None else f[2]
                                 for f in (box_fit, jaw_fit)]
        for tag, f in (("box", box_fit), ("jaw", jaw_fit)):
            if f is None:
                print(json.dumps({"ok": False, **rep, "error":
                      f"the designer's nut does not go into the {tag} end"}))
                return 1
            if not FIT_MIN <= f[0] <= FIT_MAX:
                print(json.dumps({"ok": False, **rep, "error":
                      f"{tag} fit {f[0]:.2f} mm outside "
                      f"{FIT_MIN}-{FIT_MAX} — it will bind or round the hex"}))
                return 1
    except FileNotFoundError:
        rep["box_fit_mm"] = rep["jaw_fit_mm"] = None

    ok = m.is_watertight
    if a.out and ok:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        m.apply_translation([-m.bounds[0][0], -m.bounds[0][1], 0])
        sc = trimesh.Scene()
        sc.add_geometry(m, geom_name="wrench")
        sc.export(a.out)
        from embed_settings import embed
        embed(a.out, brim=False)
        from meshcheck import export_defects
        bad = export_defects(a.out)
        rep["defects"] = bad or None
        ok = not bad
        rep["file"] = os.path.basename(a.out)
    rep["volume_cm3"] = round(float(m.volume) / 1000, 1)
    print(json.dumps({"ok": ok, **rep}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
