#!/usr/bin/env python3
"""The lap X-wing: a tooth holder with a plier's pivot instead of a bridge.

WHY ANOTHER X-WING

The scissor X-wing in gen_tooth_stand.py has both arms standing on the
table, which means the upper arm has to get over the lower one. It does
that with a pocket, and a pocket printed the right way up is a bridge,
so the upper arm prints roof-down -- and once it prints roof-down its
cones cannot be printed on it. They became four loose posts on four
dowels, and those are the parts that have given trouble: hard to seat,
easy to lose, and glued in the end.

A plier does not solve the crossing that way. Two frames bear on each
other face to face at the pivot, one riding on the other, and each frame
is a plain flat body with everything it carries on its own top face.
Nothing bridges anything. That is the joint this file builds:

    upper frame    z = t .. 2t      cones h - t tall on its own top
    lower frame    z = 0 .. t       cones h tall, flat on the table
    pin            pressed into the lower, running in the upper

Both frames are flat slabs with cones on top. Both print in the one
orientation they are used in, cones up, with no overhang, no support, no
bridge and nothing loose. The cones are part of the frames again.

WHAT IT COSTS

The upper frame does not reach the table: it is carried by the lower
frame across the bearing disc at the pivot, the way a plier's frame is.
That is the whole trade. It buys two things beyond the printing -- the
four tips are coplanar by construction, because face-on-face contact has
no clearance to take up, and the friction that holds a setting is now a
disc of some hundreds of square millimeters rather than a pin -- and it
costs the footprint, because only the lower frame touches the table. The
lower frame carries the tail for that reason, and tip_back below is the
number to compare against the scissor X-wing's.

Usage: gen_lap_wing.py [--wing lp_s|lp_m|lp_l|all] [--out FILE.3mf]
"""
import argparse
import json
import os
import sys
import zipfile

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# The cone, the cup, the fillet onto the deck and every measurement of
# what a tooth stand has to do are the tooth stand's to decide. This file
# borrows them rather than restating them, so a change to the cone is a
# change to both designs.
import gen_tooth_stand as T                                   # noqa: E402
from gen_orbital_jig import rot, rev, union, cut               # noqa: E402

ARM_T = 5.0                 # each frame this thick: the lap is 2 x 5
BAR_W = 12.0                # the bar between the two cones
ROUND = 1.5                 # inside corners of the plan
PAD_MARGIN = T.PAD_MARGIN   # pad stands this far outside the fillet's foot
SEAT_CLR = 0.0              # the frames BEAR, they do not clear: see above

# The pivot. The pin only has to not shear -- a tooth is a few newtons --
# so it stays Ø3 like the scissor X-wing's, and its fits are that design's
# measured ones: this printer takes about 0.15 mm off a small vertical
# hole, so Ø3.15 drawn is a push and Ø3.25 drawn is a friction turn.
PIN_R = T.XW_PIN_R
HOLE_PRESS_R = T.XW_HOLE_PRESS_R
HOLE_RUN_R = T.XW_HOLE_RUN_R
PIN_HEAD = (3.5, 2.0)       # Ø7 x 2, printed head-down like the other pin
# The head lands a tenth BELOW the upper frame's top face, so seating the
# pin squeezes the two frames together. That preload, not the pin's own
# grip, is what stops a tooth pushing the wings open -- see hold(). It is
# also the one adjustment the user has: press the pin until the action is
# as stiff as wanted, and no further. A gap here instead of an
# interference would leave the joint held by its own weight, which
# hold() shows is not enough.
HEAD_GAP = -0.1

# The bearing disc. This is the part that makes the design work: it
# carries the upper frame's two cones, it is the friction that stops a
# tooth pushing the wings open, and its radius sets how much the upper
# frame can lean. A tooth sitting on an upper cone at radius L bears down
# a lever of L / disc_r on the disc's rim.
DISC_MIN = 11.0
DISC_RATIO = 0.45           # of L

# The tail: the anti-tip foot, on the LOWER frame, where it is free. The
# upper frame rides a whole frame thickness above the table, so the tail
# can be any shape at all without fouling it -- unlike the scissor
# X-wing, where the tail has to pass under the upper arm at every angle.
TAIL = (9.0, 26.0)          # width at the mouth, reach behind the pivot
TAIL_AT = 30.0              # square to the crook at this half-angle

LAPWINGS = [
    dict(id="lp_s", name="Lap X-wing S", teeth=(25.0, 55.0), L=16.0,
         cone=16.0, tip=1.2, alpha=45.0, lap=True),
    dict(id="lp_m", name="Lap X-wing M", teeth=(50.0, 95.0), L=20.0,
         cone=20.0, alpha=45.0, lap=True),
    dict(id="lp_l", name="Lap X-wing L", teeth=(90.0, 150.0), L=31.3,
         cone=24.0, alpha=45.0, lap=True),
]
for _x in LAPWINGS:
    _b = np.radians(_x["alpha"])
    _x["cross"] = round(2 * _x["L"] * np.cos(_b), 2)
    _x["fore"] = round(2 * _x["L"] * np.sin(_b), 2)
BY_ID = {x["id"]: x for x in LAPWINGS}
ALL_IDS = [x["id"] for x in LAPWINGS]


# --- the two frames ----------------------------------------------------
def pad_r(spec):
    """The end pad, sized to the cone's own fillet foot."""
    return T.cone_foot_r(spec["cone"], spec) + PAD_MARGIN


def disc_r(spec):
    return round(max(DISC_MIN, DISC_RATIO * spec["L"]), 2)


def cone_h(spec, lower):
    """The lower frame's cones stand on its own top face at ARM_T; the
    upper frame's stand a whole frame higher, so they are shorter by
    exactly that much and the four tips land in one plane."""
    return spec["cone"] if lower else spec["cone"] - ARM_T


def contact_z(spec):
    return ARM_T + spec["cone"]


def dish_z(spec):
    return contact_z(spec) - T.dish_d(spec)


def tail_plan(spec):
    """A flat parabola growing out of the disc, the same foot the fixed L
    stand and the scissor X-wing carry. Set square to the crook of the
    open wings rather than to the bar, because that is the direction a
    tooth leans."""
    w, reach = TAIL
    r = disc_r(spec)
    xs = np.linspace(-w, w, 33)
    pts = [(x, -(reach - r) * (1.0 - (x / w) ** 2) - r * 0.2) for x in xs]
    poly = Polygon(pts + [(w, r), (-w, r)])
    # the bar lies along x; the crook of the open wings is at the half
    # angle, so the tail is turned to sit square to it
    from shapely import affinity
    return affinity.rotate(poly, -(90.0 - TAIL_AT), origin=(0, 0))


def frame_plan(spec, lower):
    """One frame's outline: a bar with a pad at each end and the bearing
    disc at the pivot, as ONE polygon with the inside corners rounded.
    Two solids meeting in the same plane export non-manifold, so the plan
    is unioned in 2D and extruded once."""
    L, w = spec["L"], BAR_W / 2.0
    parts = [Polygon([(-L, -w), (L, -w), (L, w), (-L, w)]),
             Point(L, 0.0).buffer(pad_r(spec), quad_segs=36),
             Point(-L, 0.0).buffer(pad_r(spec), quad_segs=36),
             Point(0.0, 0.0).buffer(disc_r(spec), quad_segs=48)]
    if lower:
        parts.append(tail_plan(spec))
    plan = unary_union(parts)
    return plan.buffer(ROUND, quad_segs=12).buffer(-ROUND, quad_segs=12)


def bore(r, z0, top, bottom_mouth=None):
    return T.xw_bore(r, z0, top, bottom_mouth)


def frame(spec, lower):
    """One frame in its own printing frame: underside flat on z = 0, slab
    ARM_T thick, a cone on each end of its own top face, the pivot bored.
    Nothing on it faces down, so it prints exactly as it is used."""
    slab = trimesh.creation.extrude_polygon(frame_plan(spec, lower), ARM_T)
    h = cone_h(spec, lower)
    body = union([slab] + [T.a_cone(h, x, 0.0, ARM_T, spec)
                           for x in (spec["L"], -spec["L"])])
    r = HOLE_PRESS_R if lower else HOLE_RUN_R
    return cut(body, [bore(r, -2.0, ARM_T, bottom_mouth=0.0)])


def pin(spec):
    """The pivot pin: tip flush with the lower frame's underside, head
    above the upper frame with HEAD_GAP under it. Printed head-down, on
    the flat of the head, which is the only flat face it has."""
    hr, hh = PIN_HEAD
    z1 = 2.0 * ARM_T
    top = z1 + HEAD_GAP + 0.5
    prof = [(0.0, 0.0), (PIN_R - 0.4, 0.0), (PIN_R, 0.4), (PIN_R, top),
            (0.0, top)]
    return union([rev(prof, sections=64),
                  T.cyl(hr, z1 + HEAD_GAP, z1 + HEAD_GAP + hh, sections=64)])


def lapwing(spec, beta=None):
    """The three bodies in the assembled pose at half-angle beta: the
    lower frame turned -beta, the upper frame turned +beta and lifted one
    frame thickness onto it, and the pin down the middle."""
    b = spec["alpha"] if beta is None else beta
    k = spec["id"][3:]
    lo = frame(spec, True)
    lo.apply_transform(rot(-b, [0, 0, 1]))
    up = frame(spec, False)
    up.apply_translation([0, 0, ARM_T + SEAT_CLR])
    up.apply_transform(rot(b, [0, 0, 1]))
    return {f"lapwing_{k}_lower": lo, f"lapwing_{k}_upper": up,
            f"lapwing_{k}_pin": pin(spec)}


def tips(spec, beta=None):
    """The four cup centers: two on each frame, at radius L."""
    b = np.radians(spec["alpha"] if beta is None else beta)
    L = spec["L"]
    return [(L * np.cos(b), -L * np.sin(b)), (-L * np.cos(b), L * np.sin(b)),
            (L * np.cos(b), L * np.sin(b)), (-L * np.cos(b), -L * np.sin(b))]


# --- measurement -------------------------------------------------------
def tips_coplanar(spec, parts, tol=0.05):
    """Read the four cup floors off the built bodies in the assembled
    pose, by raying down each cone's axis. Intent is not evidence: the
    upper frame's cones are shortened by a constant and this is the check
    that the constant is the right one."""
    k = spec["id"][3:]
    m = union([parts[f"lapwing_{k}_lower"], parts[f"lapwing_{k}_upper"]])
    pts = tips(spec)
    origins = np.array([[x, y, 500.0] for x, y in pts])
    dirs = np.tile([0.0, 0.0, -1.0], (4, 1))
    loc, idx_r, _ = m.ray.intersects_location(origins, dirs,
                                              multiple_hits=False)
    if len(loc) != 4:
        return None, None
    zs = np.zeros(4)
    zs[idx_r] = loc[:, 2]
    return float(zs.max() - zs.min()), [round(float(z), 3) for z in zs]


def opening(spec, parts, step=1.0):
    """The clear range of the half-angle, found by turning the BUILT
    upper frame against the BUILT lower one. The upper frame is lifted a
    tenth off its seat first, or the seat itself reads as a collision --
    this design's whole point is that the two frames touch."""
    import trimesh.collision as tc
    k = spec["id"][3:]
    cm = tc.CollisionManager()
    cm.add_object("lower", parts[f"lapwing_{k}_lower"])
    up = parts[f"lapwing_{k}_upper"].copy()
    up.apply_translation([0, 0, 0.1])
    cm.add_object("upper", up)
    a = spec["alpha"]

    def clear(beta):
        # twice the change in the half-angle: the lower frame stays put,
        # so turning the upper by 2 d-beta puts the pair at half-angle
        # beta, the same frame the spans are quoted in
        cm.set_transform("upper", rot(2.0 * (beta - a), [0, 0, 1]))
        return not cm.in_collision_internal()

    if not clear(a):
        return None
    lo = a
    while lo - step > 0.0 and clear(lo - step):
        lo -= step
    hi = a
    while hi + step < 90.0 and clear(hi + step):
        hi += step
    L = spec["L"]
    return dict(beta=[lo, hi],
                fore=[round(2 * L * np.sin(np.radians(lo)), 1),
                      round(2 * L * np.sin(np.radians(hi)), 1)],
                cross=[round(2 * L * np.cos(np.radians(hi)), 1),
                       round(2 * L * np.cos(np.radians(lo)), 1)])


def bearing(spec, parts):
    """The face the upper frame rides on: where the two plans overlap at
    the seat. Reported as an area and as a lever -- a cone at radius L
    leaning on a disc of this radius."""
    k = spec["id"][3:]
    lo = parts[f"lapwing_{k}_lower"]
    up = parts[f"lapwing_{k}_upper"]
    a = _section_area(lo, ARM_T - 0.2)
    b = _section_area(up, ARM_T + 0.2)
    from shapely.ops import unary_union as uu
    inter = uu(a).intersection(uu(b))
    return dict(area_mm2=round(float(inter.area), 1),
                disc_r=disc_r(spec),
                lever=round(spec["L"] / disc_r(spec), 2))


def _section_area(mesh, z):
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    polys, to3 = sec.to_planar()
    from shapely import affinity
    return [affinity.translate(p, to3[0, 3], to3[1, 3])
            for p in polys.polygons_full]


def print_overhang(mesh):
    """Downward-facing area steeper than about 45 degrees, in the pose
    the body prints in. A 45 degree chamfer is not an overhang, so the
    threshold is on the normal, not on the sign."""
    n = mesh.face_normals[:, 2]
    bad = n < -0.8
    if not bad.any():
        return dict(overhang_mm2=0.0, widest_mm=0.0)
    area = float(mesh.area_faces[bad].sum())
    zs = mesh.triangles_center[bad][:, 2]
    off = zs > 1e-6                      # anything not sitting on the plate
    return dict(overhang_mm2=round(area, 2),
                off_plate_mm2=round(float(mesh.area_faces[bad][off].sum()), 2))


def plate_contact(mesh):
    low = mesh.triangles_center[:, 2] < 1e-6
    down = mesh.face_normals[:, 2] < -0.5
    return round(float(mesh.area_faces[low & down].sum()), 1)


def support_edge(spec, direction=None):
    """How far the table contact reaches in the direction a tooth leans.
    Read off the lower frame's own outline, which IS the footprint: the
    upper frame never touches the table. The lean direction is the crook
    of the open wings, which is where the tail is put."""
    d = np.radians(90.0 - TAIL_AT) if direction is None else direction
    u = np.array([np.sin(d), -np.cos(d)])
    xy = np.array(frame_plan(spec, True).exterior.coords)
    R = np.array([[np.cos(np.radians(-spec["alpha"])),
                   -np.sin(np.radians(-spec["alpha"]))],
                  [np.sin(np.radians(-spec["alpha"])),
                   np.cos(np.radians(-spec["alpha"]))]])
    return float(np.max((xy @ R.T) @ u))


def tip_back(spec, tooth_mm=None):
    """How far a tooth can lean before the stand goes with it. Only the
    LOWER frame touches the table, so the supporting edge is its outline,
    not the quadrilateral of the tips: that is what this design trades
    away and the number to compare with the scissor X-wing's."""
    h = (spec["teeth"][1] if tooth_mm is None else tooth_mm) * 0.44
    return round(float(np.degrees(np.arctan2(support_edge(spec),
                                             contact_z(spec) + h))), 1)


def hold(spec, tooth_g=500.0, taper_deg=10.0, mu=0.3):
    """What stops a tooth pushing the wings open.

    A root wedged between the four cups pushes each one outward by about
    W/4 x tan(taper). Only the part of that across the radius turns the
    frames, so the torque on one frame is 2 F L cos(beta). What resists
    it is friction on the seat -- the whole reason this joint is a disc
    and not a pin -- with an effective radius of two thirds of the
    disc's. Under the tooth's weight alone that is not enough, which is
    why the pin's head seats a tenth proud of the bore: the preload it
    puts on the seat is the adjustment, and `preload_N` is how much of it
    buys a margin of two."""
    W = tooth_g / 1000.0 * 9.81
    F = (W / 4.0) * np.tan(np.radians(taper_deg))
    b = np.radians(spec["alpha"])
    spread = 2.0 * F * (spec["L"] * 1e-3) * np.cos(b)
    reff = (2.0 / 3.0) * disc_r(spec) * 1e-3
    weight_only = mu * (W / 2.0) * reff
    return dict(spread_Nm=round(spread, 4),
                seat_Nm_weight_only=round(weight_only, 4),
                margin_weight_only=round(weight_only / spread, 2),
                preload_N=round(max(0.0, (2.0 * spread / (mu * reff))
                                    - W / 2.0), 1))


def measure(parts):
    rep = dict(bodies=len(parts),
               watertight={n: bool(m.is_watertight) for n, m in parts.items()},
               dims_mm={n: [round(float(v), 2) for v in m.extents]
                        for n, m in parts.items()})
    flat, _ = layout(parts)
    rep["fits_plate"] = {n: bool(T.fits_plate(m)) for n, m in flat.items()}
    rep["coplanar_mm"], rep["tip_z"] = {}, {}
    rep["opening"], rep["bearing"], rep["print"] = {}, {}, {}
    rep["plate_mm2"], rep["occlusion"], rep["above_contact_mm"] = {}, {}, {}
    rep["tip_back_deg"], rep["hold"] = {}, {}
    for x in LAPWINGS:
        k = x["id"][3:]
        if f"lapwing_{k}_lower" not in parts:
            continue
        dz, zs = tips_coplanar(x, parts)
        rep["coplanar_mm"][x["id"]] = dz
        rep["tip_z"][x["id"]] = zs
        rep["opening"][x["id"]] = opening(x, parts)
        rep["bearing"][x["id"]] = bearing(x, parts)
        rep["tip_back_deg"][x["id"]] = tip_back(x)
        rep["hold"][x["id"]] = hold(x)
        both = union([parts[f"lapwing_{k}_lower"], parts[f"lapwing_{k}_upper"]])
        rep["above_contact_mm"][x["id"]] = round(
            float(both.bounds[1][2]) - contact_z(x), 4)
        rep["occlusion"][x["id"]] = T.occlusion(both, dict(x, cone=x["cone"]))
    for n, m in flat.items():
        rep["print"][n] = print_overhang(m)
        rep["plate_mm2"][n] = plate_contact(m)
    rep["cone_stress_MPa"] = {x["id"]: T.cone_stress(x) for x in LAPWINGS
                              if f"lapwing_{x['id'][3:]}_lower" in parts}
    rep["volume_cm3"] = round(sum(m.volume for m in parts.values()) / 1000.0, 2)
    rep["est_g"] = round(rep["volume_cm3"] * 1.27, 1)
    return rep


def gates(rep):
    out = [("watertight", all(rep["watertight"].values())),
           ("fits_plate", all(rep["fits_plate"].values()))]
    for k, v in rep["coplanar_mm"].items():
        out.append((f"coplanar:{k}", v is not None and v < 0.05))
    for k, v in rep["above_contact_mm"].items():
        out.append((f"below_contact:{k}", v <= 1e-6))
    for k, v in rep["occlusion"].items():
        out.append((f"occludes_nothing:{k}", v["overall"] < 1.0))
    for k, v in rep["opening"].items():
        out.append((f"opens:{k}", v is not None and v["beta"][1] - v["beta"][0] >= 20.0))
    # the whole claim of this design: every body prints as it is used
    for n, v in rep["print"].items():
        out.append((f"no_overhang:{n}", v.get("off_plate_mm2", 0.0) <= 1.0))
    for n, v in rep["plate_mm2"].items():
        out.append((f"stands_up:{n}", v > 20.0))
    for k, v in rep["cone_stress_MPa"].items():
        out.append((f"tip_stress:{k}", v < 15.0))
    return out


# --- plate and file ----------------------------------------------------
def parse_which(which):
    ids = ALL_IDS if which in ("all", "", None) else [
        w.strip() for w in which.split(",") if w.strip()]
    bad = [i for i in ids if i not in ALL_IDS]
    if bad:
        raise ValueError("no such wing: " + ", ".join(bad))
    return [i for i in ALL_IDS if i in ids]


def build(which="all"):
    out = {}
    for i in parse_which(which):
        out.update(lapwing(BY_ID[i]))
    return out


def layout(parts, gap=6.0):
    """Flat on the plate, each body the way up it is used -- except the
    pin, which lies on its head. Nothing else is flipped, and nothing
    else needs to be: that is the design."""
    out, poses = {}, {}
    x, y, row_h = 0.0, 0.0, 0.0
    for n in sorted(parts):
        m = parts[n].copy()
        F = rot(180.0, [1, 0, 0]) if "_pin" in n else np.eye(4)
        m.apply_transform(F)
        lo, hi = m.bounds
        ext = hi - lo
        if x + ext[0] > 246.0 and x > 0.0:
            x, y, row_h = 0.0, y + row_h + gap, 0.0
        shift = np.array([x - lo[0], y - lo[1], -lo[2]])
        m.apply_translation(shift)
        S = np.eye(4)
        S[:3, 3] = shift
        poses[n] = np.linalg.inv(S @ F)
        out[n] = m
        x += ext[0] + gap
        row_h = max(row_h, ext[1])
    return out, poses


def meta(parts, poses, rep):
    return {
        "design": "lap_wing",
        "joint": "half-lap bypass: the upper frame bears on the lower "
                 "frame's disc, both frames flat, cones integral",
        "arm_t": ARM_T,
        "pin": dict(r=PIN_R, head=list(PIN_HEAD), gap=HEAD_GAP,
                    press_hole_r=HOLE_PRESS_R, run_hole_r=HOLE_RUN_R),
        "wings": [dict(x, tips=tips(x), contact_z=contact_z(x),
                       dish_z=dish_z(x), disc_r=disc_r(x),
                       cone_h=[cone_h(x, True), cone_h(x, False)],
                       tip_r=T.tip_r(x), dish=round(T.dish_d(x), 3),
                       opening=rep["opening"].get(x["id"]),
                       bearing=rep["bearing"].get(x["id"]),
                       tip_back_deg=rep["tip_back_deg"].get(x["id"]))
                  for x in LAPWINGS if f"lapwing_{x['id'][3:]}_lower" in parts],
        "to_world": {n: [round(float(v), 6) for v in poses[n].ravel()]
                     for n in poses},
        "volume_cm3": {n: round(float(m.volume) / 1000.0, 2)
                       for n, m in parts.items()},
    }


def export(parts, out, rep):
    flat, poses = layout(parts)
    sc = trimesh.Scene()
    for n, m in flat.items():
        sc.add_geometry(m, geom_name=n, node_name=n)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sc.export(out)
    from embed_settings import embed
    # no body on this plate earns a brim: the frames sit on tens of
    # square centimeters and the pin lies on its Ø7 head
    embed(out, brim=False)
    with zipfile.ZipFile(out, "a", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Metadata/lap_wing.json",
                   json.dumps(meta(parts, poses, rep), separators=(",", ":")))
    from meshcheck import export_defects
    return export_defects(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wing", default="all",
                    help="all, or a comma-separated set of "
                         + ", ".join(ALL_IDS))
    ap.add_argument("--out")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    try:
        parts = build(a.wing)
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    if a.quick:
        ok = all(m.is_watertight for m in parts.values())
        print(json.dumps({"ok": ok, "bodies": len(parts)}))
        return 0 if ok else 1
    rep = measure(parts)
    failed = [n for n, ok in gates(rep) if not ok]
    ok = not failed
    if failed:
        rep["failed"] = failed
        rep["error"] = "gate failed: " + ", ".join(failed)
    if a.out and ok:
        bad = export(parts, a.out, rep)
        rep["defects"] = bad or None
        ok = not bad
        rep["file"] = os.path.basename(a.out)
    print(json.dumps({"ok": ok, **rep}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
