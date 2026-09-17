#!/usr/bin/env python3
"""The specimen head system: the other answer to holding the tooth.

docs/orbital-jig-plan.html section 6 proposed a different mount from the
forest of cones in gen_tooth_stand.py. Instead of a drop-in puck with
fixed printed tips, the pedestal's platform gets a 1/4-20 brass insert --
the same part the camera receiver already uses -- and a family of heads
screws onto it, each one holding a different class of specimen a
different way:

    putty disc     a 30 mm dish with 3 mm of museum putty in it, for
                   anything under about 60 mm, sitting upright
    three-pin      three 1.5 mm stainless pins in printed collets that
    cradle         slide radially, each tipped with a 1 mm silicone
                   bead: three points, adjustable, for the big tooth
    tip cone       a 40 mm cup, 25 mm deep, with a closed-cell foam
                   liner, which takes the CROWN so the tooth hangs
                   inverted and its root underside is fully exposed
    flat chuck     two sprung jaws on a 60 mm opening, for slabs and
                   flat specimens; not teeth

This file builds all four so they can be rendered and measured beside
the cone forest rather than argued about. It is a study, not a product:
the bought parts (pins, beads, foam, the insert) are proxies, and where
the plan gave a number it is used, while everything it left open is
marked below as a choice made here.

WHAT THE COMPARISON IS ACTUALLY ABOUT

Not size or part count. The orbital jig photographs the specimen from
108 positions, all of them above the horizon, and the one thing that
decides whether a mount is visible in those frames is whether any of it
rises above the plane the specimen rests on. Nothing below that plane
can occlude the specimen from a camera above the horizon; anything above
it occludes directly. So each head is measured the same way the cone
stands are -- how far it reaches above its own contact plane -- and that
single number is the comparison.

The tip cone is the interesting case. It is the only mount here that
deliberately swallows part of the specimen, 25 mm of crown, and it does
that so the root's underside -- which no ring on this jig ever sees with
the tooth upright -- can be captured in a second pass and merged. It
trades occlusion in pass two for coverage that pass one cannot get.

Usage: gen_specimen_heads.py [--head NAME|all] [--out FILE.3mf]
"""
import argparse
import json
import os
import sys
import zipfile

import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gen_orbital_jig as J                                  # noqa: E402
from gen_orbital_jig import (rot, box, cyl, cone, rev,        # noqa: E402
                             union, cut, polar, fits_plate)

PLAT_R = J.PLAT_R           # 10.0: the platform every head screws onto

# --- the shared dock ---------------------------------------------------
# The plan's words: "a 1/4-20 brass insert in the top, the same part the
# receiver uses". So every head carries a clearance hole for a 1/4-20
# stud and a counterbore for its washer.
QTR_R = 3.3                 # 1/4-20 clearance radius
QTR_CB = (7.0, 3.0)         # counterbore radius, depth
SKIRT_R = 11.0              # a skirt just past the platform, so a head
SKIRT_H = 4.0               # cannot be knocked sideways off it

# --- putty disc --------------------------------------------------------
PD_R, PD_T = 15.0, 8.0      # the plan's 30 mm dish
PD_DISH_R, PD_DISH_D = 13.0, 3.0            # 3 mm of putty, its number

# --- three-pin cradle --------------------------------------------------
# The plan gives the pins (1.5 mm stainless), the beads (1 mm silicone)
# and "40 mm radial slides". Chosen here: the slide runs r = 8..33, which
# is 25 mm of travel on a 80 mm base -- enough for the 82 mm lobe span
# measured off BigMeherrin, and small enough to stay on the plate.
PC_R, PC_T = 40.0, 7.0
PC_SLOT = (8.0, 33.0, 3.2)  # r0, r1, half-width
PC_PHI = (90.0, 210.0, 330.0)
PC_COLLET = (10.0, 9.0, 12.0)               # length, width, height
PIN_R, PIN_L = 0.75, 25.0                   # 1.5 mm stainless
BEAD_R = 0.5                                # 1 mm silicone bead
PC_SEAT = 22.0              # where the generator parks the three collets

# --- tip cone ----------------------------------------------------------
TC_R, TC_H = 20.0, 30.0     # the plan's 40 mm cup
TC_BORE, TC_DEEP = 17.0, 25.0               # its 25 mm depth
TC_FOAM = 2.0               # closed-cell liner thickness
TC_FLOOR_R = 6.0            # the cup's floor is FLAT, not a point: see
                            # tip_cone() for why, and a crown should not
                            # be asked to stand on a mathematical apex

# --- flat chuck --------------------------------------------------------
FC_BASE = (45.0, 30.0, 6.0)                 # half-length, half-width, t
FC_OPEN = 60.0              # the plan's 60 mm opening
FC_JAW = (6.0, 24.0, 14.0)  # thickness, width, height
FC_LEAF = 1.5               # PETG leaf spring, as the detent pawl uses

HEADS = ["putty_disc", "pin_cradle", "tip_cone", "flat_chuck"]

# What each head does to the specimen: where its contact plane is, in the
# head's own frame (z = 0 is the face that lands on the platform), and
# whether the mount reaches above that plane on purpose.
CONTACT = {
    "putty_disc": PD_T,                      # putty sits on the dish floor
    "pin_cradle": PC_T + PC_COLLET[2] + PIN_L - BEAD_R,
    "tip_cone": TC_H - TC_DEEP,              # the crown goes IN to here
    "flat_chuck": FC_BASE[2],
}


# --- the dock, cut into every head -------------------------------------
def dock_tools(z0=0.0):
    return [cyl(QTR_R, z0 - 1.0, z0 + 60.0, sections=48),
            cyl(QTR_CB[0], z0 - 1.0, z0 + QTR_CB[1], sections=48)]


def skirt():
    """A ring that drops just past the platform's edge."""
    return rev([(PLAT_R + 0.3, 0.0), (SKIRT_R, 0.0),
                (SKIRT_R, SKIRT_H), (PLAT_R + 0.3, SKIRT_H)], sections=128)


# --- the four heads ----------------------------------------------------
def putty_disc():
    body = rev([(0.0, 0.0), (PD_R, 0.0), (PD_R, PD_T), (0.0, PD_T)],
               sections=160)
    dish = rev([(0.0, PD_T - PD_DISH_D), (PD_DISH_R, PD_T - PD_DISH_D),
                (PD_DISH_R, PD_T + 1.0), (0.0, PD_T + 1.0)], sections=160)
    m = cut(union([body, skirt()]), [dish] + dock_tools())
    return m


def collet(r_at, phi):
    """One printed collet: a block that straddles the slot, bored for a
    pin, with a pinch screw's clearance across it."""
    L, W, H = PC_COLLET
    blk = box((-L / 2.0, -W / 2.0, PC_T), (L / 2.0, W / 2.0, PC_T + H))
    bore = cyl(PIN_R + 0.15, PC_T + 2.0, PC_T + H + PIN_L, sections=32)
    # the tongue that keys into the slot, and the pinch slit
    tongue = box((-L / 2.0, -PC_SLOT[2] + 0.2, PC_T - 3.0),
                 (L / 2.0, PC_SLOT[2] - 0.2, PC_T + 0.1))
    slit = box((-L / 2.0 - 1, -0.6, PC_T + H * 0.45),
               (L / 2.0 + 1, 0.6, PC_T + H + 1))
    m = cut(union([blk, tongue]), [bore, slit])
    m.apply_transform(rot(phi, [0, 0, 1], origin=(0, 0, 0)))
    x, y, _ = polar(r_at, phi)
    m.apply_translation([x, y, 0.0])
    return m


def pin_cradle(seat=PC_SEAT):
    base = rev([(0.0, 0.0), (PC_R, 0.0), (PC_R, PC_T), (0.0, PC_T)],
               sections=180)
    slots = []
    for phi in PC_PHI:
        s = box((PC_SLOT[0], -PC_SLOT[2], -1.0),
                (PC_SLOT[1], PC_SLOT[2], PC_T + 1.0))
        s.apply_transform(rot(phi, [0, 0, 1]))
        slots.append(s)
    m = cut(union([base, skirt()]), slots + dock_tools())
    return union([m] + [collet(seat, p) for p in PC_PHI])


def tip_cone():
    """The profile is the cup itself: out along the base, up the outside,
    in across the rim, then down the conical interior to a FLAT floor.

    The floor is flat because of a measured defect, not a preference. Run
    to a point on the axis instead, and the body is watertight and the
    written 3MF still carries 16 non-manifold edges -- and 48 of them at
    96 sections rather than 180, which is what tells you they are
    degenerate faces at the axis rather than anything about the shape.
    Isolated: the body alone is clean, the body with its skirt is clean,
    and the body with the 1/4-20 dock bored up the axis is not, because
    the bore arrives exactly where the cone's apex already collapsed the
    revolve. A floor of radius TC_FLOOR_R keeps the two apart and the
    file comes out clean at any section count.
    """
    body = rev([(0.0, 0.0), (TC_R, 0.0), (TC_R, TC_H), (TC_BORE, TC_H),
                (TC_FLOOR_R, TC_H - TC_DEEP), (0.0, TC_H - TC_DEEP)],
               sections=180)
    return cut(union([body, skirt()]), dock_tools())


def flat_chuck():
    hl, hw, t = FC_BASE
    base = box((-hl, -hw, 0.0), (hl, hw, t))
    jt, jw, jh = FC_JAW
    parts = [base, skirt()]
    for s in (-1, 1):
        # The gripping face is at x = s * FC_OPEN/2, so the opening really
        # is FC_OPEN; the jaw's material stands outboard of it. Corners go
        # through sorted() because box() takes (lo, hi) and one sign of s
        # hands them over in the other order, which builds a box with a
        # negative extent and is not a volume.
        face = s * FC_OPEN / 2.0
        x0, x1 = sorted((face, face + s * jt))
        parts.append(box((x0, -jw / 2.0, t), (x1, jw / 2.0, t + jh)))
        # the leaf that lets the jaw give: a thin web back along the base
        l0, l1 = sorted((face + s * jt, face + s * (jt + 8.0)))
        parts.append(box((l0, -jw / 2.0, t), (l1, jw / 2.0, t + FC_LEAF)))
    return cut(union(parts), dock_tools())


BUILDERS = {"putty_disc": putty_disc, "pin_cradle": pin_cradle,
            "tip_cone": tip_cone, "flat_chuck": flat_chuck}


def proxies():
    """Bought parts, drawn so the renders are honest about what is
    printed and what is not: three stainless pins with silicone beads,
    and the tip cone's foam liner."""
    out = {}
    z0 = PC_T + PC_COLLET[2]
    for i, phi in enumerate(PC_PHI):
        x, y, _ = polar(PC_SEAT, phi)
        pin = cyl(PIN_R, z0 - 6.0, z0 + PIN_L, x, y, sections=24)
        bead = trimesh.creation.icosphere(subdivisions=2, radius=BEAD_R)
        bead.apply_translation([x, y, z0 + PIN_L])
        out[f"pin_{i}"] = union([pin, bead])
    foam = rev([(0.0, TC_H - TC_DEEP + TC_FOAM),
                (TC_BORE - TC_FOAM, TC_H),
                (TC_BORE, TC_H), (0.0, TC_H - TC_DEEP)], sections=120)
    out["foam_liner"] = foam
    return out


def parse_heads(which):
    """"all", or a comma-separated set of head names. The shop hands its
    tick-boxes over as one string, so a single name and four names arrive
    by the same route."""
    if not which or which == "all":
        return list(HEADS)
    names = [w.strip() for w in which.split(",") if w.strip()]
    bad = [n for n in names if n not in BUILDERS]
    if bad:
        raise ValueError("no such head: " + ", ".join(bad))
    return [n for n in HEADS if n in names]          # keep a stable order


def build(which="all"):
    return {n: BUILDERS[n]() for n in parse_heads(which)}


# --- layout, measurement, export ---------------------------------------
def layout(parts, gap=6.0):
    out, poses = {}, {}
    x, y, row_h = 0.0, 0.0, 0.0
    for n in sorted(parts):
        m = parts[n].copy()
        lo, hi = m.bounds
        ext = hi - lo
        if x + ext[0] > 246.0 and x > 0.0:
            x, y, row_h = 0.0, y + row_h + gap, 0.0
        shift = np.array([x - lo[0], y - lo[1], -lo[2]])
        m.apply_translation(shift)
        S = np.eye(4)
        S[:3, 3] = shift
        poses[n] = np.linalg.inv(S)
        out[n] = m
        x += ext[0] + gap
        row_h = max(row_h, ext[1])
    return out, poses


def rise_above_contact(name, m):
    """How far the head reaches above the plane the specimen rests on --
    the one number that decides whether it shows up in the frames."""
    return round(float(m.bounds[1][2] - CONTACT[name]), 3)


def measure(parts):
    rep = {"bodies": len(parts)}
    rep["watertight"] = {n: bool(m.is_watertight) for n, m in parts.items()}
    rep["dims_mm"] = {n: [round(float(v), 2) for v in m.extents]
                      for n, m in parts.items()}
    flat, _ = layout(parts)
    rep["fits_plate"] = {n: bool(fits_plate(m)) for n, m in flat.items()}
    rep["contact_z"] = {n: CONTACT[n] for n in parts}
    rep["rise_above_contact_mm"] = {n: rise_above_contact(n, m)
                                    for n, m in parts.items()}
    vol = sum(float(m.volume) for m in parts.values()) / 1000.0
    rep["volume_cm3"] = round(vol, 2)
    rep["est_g"] = round(vol * J.PETG_G_PER_CM3, 1)
    rep["hardware"] = {"1/4-20 brass insert": 1,
                       "1.5 mm stainless pin": 3,
                       "1 mm silicone bead": 3,
                       "closed-cell foam liner": 1}
    return rep


# Two of these have to stay under the plane the specimen rests on, and
# two of them rise above it ON PURPOSE -- which is the whole comparison,
# so the gate asserts both halves rather than treating a rise as a fault.
# The cup swallows 25 mm of crown to buy the root underside that no
# upright pass on this jig can reach; a chuck grips from the sides, so
# its jaws stand beside the slab by definition. The cone stands in
# gen_tooth_stand.py make neither trade: all four of them sit flush.
STAY_BELOW = ("putty_disc", "pin_cradle")
RISE_BY_DESIGN = ("tip_cone", "flat_chuck")


def gates(rep):
    rise = rep["rise_above_contact_mm"]
    return [("watertight", all(rep["watertight"].values())),
            ("fits_plate", all(rep["fits_plate"].values())),
            ("contact_mounts_stay_below", all(
                v <= 0.01 for n, v in rise.items() if n in STAY_BELOW)),
            ("the_other_two_rise_on_purpose", all(
                v > 1.0 for n, v in rise.items() if n in RISE_BY_DESIGN))]


def heads_meta(parts, poses):
    return {"design": "specimen_heads",
            "heads": list(parts),
            "contact_z": {n: CONTACT[n] for n in parts},
            "dock": dict(qtr_r=QTR_R, cb=list(QTR_CB), skirt_r=SKIRT_R,
                         plat_r=PLAT_R),
            # the bought parts, so a page can draw what is holding the
            # specimen up: without the pins the cradle renders as a tooth
            # floating 24 mm above a base, which is not what it does
            "pins": dict(phi=list(PC_PHI), r=PC_SEAT, pin_r=PIN_R,
                         bead_r=BEAD_R, length=PIN_L,
                         z0=PC_T + PC_COLLET[2]),
            "to_world": {n: [round(float(v), 6) for v in poses[n].ravel()]
                         for n in poses},
            "volume_cm3": {n: round(float(m.volume) / 1000.0, 2)
                           for n, m in parts.items()}}


def export(parts, out):
    flat, poses = layout(parts)
    sc = trimesh.Scene()
    for n, m in flat.items():
        sc.add_geometry(m, geom_name=n, node_name=n)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sc.export(out)
    from embed_settings import embed
    embed(out, brim=True)
    meta = heads_meta(parts, poses)
    with zipfile.ZipFile(out, "a", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Metadata/specimen_heads.json",
                   json.dumps(meta, separators=(",", ":")))
    from meshcheck import export_defects
    return export_defects(out), meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--head", default="all")
    ap.add_argument("--out")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    try:
        parts = build(a.head)
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
        bad, meta = export(parts, a.out)
        rep["defects"] = bad or None
        ok = not bad
        rep["file"] = os.path.basename(a.out)
    print(json.dumps({"ok": ok, **rep}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
