#!/usr/bin/env python3
"""Tooth stands for the orbital jig: a forest of cones a fossil rests on.

The jig holds the specimen still and flies the camera around it, so
whatever the specimen sits on is in every one of the 108 frames. That
makes the mount an optical part as much as a mechanical one. It has three
jobs that pull against each other: hold the tooth to a tenth of a
millimetre through 108 settles, touch it in places small enough that the
other rings fill them in, and be matte black and featureless so feature
matching drops it.

THE SUPPORT IS A QUADRILATERAL, NOT A TRIPOD

A shark tooth root is bilobate: it comes down on two lobes with a notch
between them. Each lobe presents a face, not a point, so the tooth is
carried on FOUR cones -- two per lobe, fore and aft -- and never in the
notch, which is where nothing touches and where the low rings want to
see. Four points over-constrain a rigid body and could rock; the speck of
black tac on each tip takes that up, and four beats three for spreading a
heavy root over tips this fine.

WHERE THE SPANS COME FROM

Not from a scan. FossilRecord measures teeth as outlines lifted from
photographs -- 6,369 detected teeth with a length and a width, and 801
with normalised shape ratios -- so the durable numbers here are widths
and spans, and everything below is built from them:

    root width  ~ 0.76 x length      specimen_shapes.base_width, median
                                     of 801 (p10 0.46, p90 0.92)
    root notch  ~ 0.06 x height      specimen_shapes.cleft, median; p90
                                     0.115, max 0.212
    thickness   ~ 0.15 x length      the only caliper readings there are,
                                     16 pins over 3 specimens, 9-25 mm

    cross span   = 0.70 x root width    tips land on the lobes, inboard
                                        of the edge where it thins
    fore/aft span = 0.55 x thickness    both tips inside the footprint

Tooth lengths run from 6.6 mm to 252 mm, median 25.9, p95 110.3, so one
stand cannot do it. Four cover the range, and each one is a size band
rather than a species.

The one tooth that exists as a mesh -- models/specimen/BigMeherrin.glb,
lifted from its contour by FossilRecord's restoration pipeline, not
scanned -- is the check on the largest stand, and it passes: levelled,
its lobes touch down 82.1 mm apart and its root is 31.2 mm thick, so the
60 mm cross span and 18 mm fore/aft span put all four tips on the lobes.
Its notch is 23.4 mm deep, 18% of its height, near the top of the
measured range, and the L stand's cones are tall enough to clear it.

THE CONE

Each cone is one solid of revolution: a straight flank off the arm at
3.5 degrees from vertical, and a tip that is a shallow concave dish
rather than a point. The dish holds a speck of black tac, which is what
actually stops the tooth sliding -- the cone only has to put the tac
where it is needed and occlude as little as possible getting there.

The taper is held at about 7 degrees included for every cone, which the
spec asked for. That means the base radius has to grow with height
rather than being fixed: a 1.75 mm base would be a needle at 12 mm tall
and a 20-degree stump at 24, and only one of those prints.

    r_base = r_tip + h tan 3.5 deg

DOCKING, WITHOUT TOUCHING THE JIG

The underside is one flat plane: hub and arms end at z = 0 and nothing
reaches below it. The hub's flat 20 mm face sits on the platform's flat
20 mm face and takes the tipping moment, and a speck of the same black
tac that holds the tooth holds the stand. A first cut had a 0.9 mm boss
under the hub to drop into the platform's putty dimple; it located
nothing a speck of tac does not, and it meant the stand could not sit on
a table. The jig generator, and the 222 tests that hold it down, are
untouched by this file.

Nothing keys the rotation, deliberately. Structure-from-motion does not
care how the tooth is turned, and being able to spin the stand to line
its quadrilateral up with the root's lobes is worth more than an index.

Usage: gen_tooth_stand.py [--stand xs|s|m|l|all] [--out FILE.3mf]
"""
import argparse
import json
import os
import sys
import zipfile

import numpy as np
import trimesh
from shapely.geometry import Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# The interface this part mates with. Imported rather than copied: the
# platform diameter and the dimple are the jig's to decide, and a stand
# built against stale copies of them would fit nothing.
import gen_orbital_jig as J                                  # noqa: E402

from gen_orbital_jig import (rot, box, cyl, rev, union, cut,   # noqa: E402
                             polar, fits_plate, cone)

# --- the dock ----------------------------------------------------------
PLAT_R = J.PLAT_R           # 10.0, the pedestal's platform radius
HUB_R = 10.0                # sits exactly on the platform
HUB_T = 6.0                 # the spec's 6 mm puck

ARM_T = 5.0                 # arms this thick, flat on the plate
ARM_W = (6.0, 4.5)          # tapering from hub to the cone's pad
FILLET = 2.5                # concave blend from the flank onto the pad,
                            # scaled down with a smaller tip
PAD_MARGIN = 0.6            # the pad stands this far outside the fillet's foot

# --- the cone ----------------------------------------------------------
TIP_R = 1.875               # Ø3.75 tip: 25% thinner than the Ø5 the first
                            # print had, on Brett's call after handling it.
                            # The cup still takes a dab of museum wax
                            # in, on a spire stout enough to handle. The
                            # spec's 1.3 mm point snapped in the hand; grip
                            # comes from the wax, so the tip is sized to the
                            # wax. A stand carries its own smaller `tip`
                            # where its cones stand too close for Ø5: the
                            # XS and S pins are 6 mm apart
DISH_RATIO = 2.0 / 3.0      # cup depth over tip radius: 1.0 mm at Ø3
HALF_DEG = 3.5              # 7 degrees included, in the spec's 6-8. The
                            # first cut's cones were fragile, and the fix
                            # is at the TIP, not the base: a wider tip
                            # thickens the whole spire without widening
                            # its foot

# --- the family --------------------------------------------------------
# tooth band (mm), cross span, fore/aft span, cone height. The spans are
# the 0.70 x width and 0.55 x thickness rules above, evaluated at the top
# of each band and rounded to something a caliper can check.
STANDS = [
    # fore 6, not the 3 the 0.55 x thickness rule gives: printed at 3 the
    # cups sat 2 mm apart and there was no getting a tooth between them
    dict(id="xs", name="XS", teeth=(10.0, 28.0), cross=10.0, fore=6.0,
         cone=12.0, tip=1.125),
    # fore spans opened out from the 0.55 x thickness rule -- 6, 11, 18
    # printed with the cups nearly touching, and a root lobe wants room
    # to settle between the two pins rather than balance across them
    dict(id="s", name="S", teeth=(25.0, 55.0), cross=20.0, fore=10.0,
         cone=16.0, tip=1.5),
    # the same parabolic foot as the L, at half its size
    dict(id="m", name="M", teeth=(50.0, 95.0), cross=38.0, fore=16.0,
         cone=20.0, tail=(HUB_R / 2.0, 15.75)),
    # a tail behind the hub: the L stand's footprint is 24 mm across in
    # the fore/aft direction under a tooth that can be 150 mm tall, and
    # it tipped back. A flat parabola growing out of the hub circle
    # behind one side -- half the hub's width at its mouth, its vertex
    # 31.5 mm behind the pivot -- moves the tipping edge from 19 mm to
    # 31.5. (width at the mouth, reach behind the pivot)
    dict(id="l", name="L", teeth=(90.0, 150.0), cross=60.0, fore=24.0,
         cone=24.0, tail=(HUB_R, 31.5)),
]
BY_ID = {s["id"]: s for s in STANDS}

# --- the X-wings -------------------------------------------------------
# Scissors. Two arms with a cone at each end, BOTH lying on the table at
# full height so all four spires stand on the ground. The lower arm is
# a plain bar. The upper arm's two ends are plain bars too, joined by a
# connector that spans ABOVE the lower bar at the crossing, resting on
# its top face; a plain printed pin is pressed down through connector
# and bar, its head on top, its tip flush with the flat bottom. Opening
# the half-angle beta between the arms moves the four pins on a circle
# of radius L:
#
#     cross = 2 L cos beta      fore/aft = 2 L sin beta
#
# so one X-wing covers a band of teeth the fixed stands need a size for
# each of. What limits the swing is the pads meeting out at the ends,
# at sin(beta) = pad / L. The upper arm's grounded ends are relieved
# only where the lower bar will lie against them at that closed angle
# -- a miter, not a disc -- and the connector spans just far enough to
# clear the lower bar there. The range reported is the built arm turned
# against the built base, and the arms alone are swept beside it.
XW_CONN_T = 3.0             # the connector, over the lower bar's top
XW_CLOSE_MARGIN = 1.0       # the relief is cut a degree past the pads' limit
# The pivot, sized to what it does: the pin only has to not shear, so it
# is Ø3; the disc round it on each arm is three pin diameters, Ø9; the
# upper arm's cut round the lower disc is Ø9.1.
XW_PIN_R = 1.5              # Ø3 pin. PETG at ~30 MPa in shear over 7 mm^2
                            # carries some 200 N; a tooth is 5
XW_HUB_R = 4.5              # Ø9 disc on the lower arm, Ø9 hub on the upper
XW_HOLDOFF = 0.05           # the upper arm's cut round the lower disc: Ø9.1
XW_SWEEP_CLR = 0.5          # clearance round the lower BAR where it sweeps
                            # past the upper arm's ends
# The pin is fixed in the LOWER arm and the UPPER arm turns on it, so the
# two holes are different fits. Small FDM holes print a tenth or two
# undersize, so the designed numbers carry that:
# Fits for PETG on the P2S. Small vertical holes print 0.1-0.2 undersize
# on the diameter and small vertical pins print a few hundredths over, so
# a hole drawn at the pin's size is a 0.15-0.2 interference -- too hard to
# press by hand into a 3 mm wall. These are the drawn sizes that print as
# the fit named:
XW_HOLE_PRESS_R = XW_PIN_R + 0.05     # lower arm: Ø3.1 drawn, a firm press
XW_HOLE_RUN_R = XW_PIN_R + 0.2        # upper arm: Ø3.4 drawn, ~0.2 running
XW_HOLE_CHAMFER = 0.3                 # lead-in at the mouth of each hole
XW_PIN_HEAD = (3.0, 1.5)    # Ø6 head, printed head-down
XW_LAND = 3.0               # the connector runs this far onto full-width end
XW_HUB_T = 5.0              # the upper hub's height: what the arm turns on
XW_BAR_W = 6.0
XWINGS = [
    # the smaller two cannot close as far as their fixed stands: the
    # upper blade's pad meets the lower cone first. Their defaults sit
    # where the sweep says they are clear, with L opened out a little
    # What stops the blades closing is the upper blade's PAD meeting the
    # lower blade's cone, out at the pins -- not anything at the hub. The
    # pad is sized to the cone's fillet foot, so a smaller fillet on the
    # X-wing cones is the one lever on the swing: 1.2 mm here against
    # 2.5 on the fixed stands, worth about three degrees of closing.
    dict(id="xw_s", name="X-wing S", teeth=(25.0, 55.0), L=16.0, cone=16.0,
         tip=1.5, alpha=45.0, xwing=True),
    dict(id="xw_m", name="X-wing M", teeth=(50.0, 95.0), L=20.0, cone=20.0,
         alpha=45.0, xwing=True),
    dict(id="xw_l", name="X-wing L", teeth=(90.0, 150.0), L=31.3, cone=24.0,
         alpha=45.0, xwing=True),
]
for _x in XWINGS:
    _b = np.radians(_x["alpha"])
    _x["cross"] = round(2 * _x["L"] * np.cos(_b), 2)
    _x["fore"] = round(2 * _x["L"] * np.sin(_b), 2)
XW_BY_ID = {x["id"]: x for x in XWINGS}
ALL_IDS = [s["id"] for s in STANDS] + [x["id"] for x in XWINGS]


def spec_of(part_name):
    """The spec a body belongs to: stand_<id> or xwing_<id>_<base|top>."""
    bits = part_name.split("_")
    if bits[0] == "xwing":
        return XW_BY_ID["xw_" + bits[1]]
    return BY_ID[bits[1]]


def mount_of(part_name):
    """The mount a body belongs to: the two X-wing bodies share one."""
    bits = part_name.split("_")
    return "xwing_" + bits[1] if bits[0] == "xwing" else part_name

PETG_G_PER_CM3 = J.PETG_G_PER_CM3


# --- helpers -----------------------------------------------------------
def tip_r(spec=None):
    return TIP_R if spec is None else float(spec.get("tip", TIP_R))


def dish_d(spec=None):
    return DISH_RATIO * tip_r(spec)


def fillet_r(spec=None):
    if spec is not None and "fillet" in spec:
        return float(spec["fillet"])
    return min(FILLET, 1.7 * tip_r(spec))


def cone_base_r(h, spec=None):
    """The flank is held at HALF_DEG, so the base grows with height."""
    return tip_r(spec) + h * np.tan(np.radians(HALF_DEG))


def fillet_geom(h, spec=None):
    """The concave fillet between the flank and the deck: its centre
    (rc, F) above the deck, its foot rc on the deck, and its tangent
    point (r_t, z_t) on the flank. The centre sits in the AIR, F from
    both surfaces, and the arc between the two tangent points is the
    short way round -- through the point nearest the corner."""
    t = np.tan(np.radians(HALF_DEG))
    r_b = cone_base_r(h, spec)
    F = fillet_r(spec)
    rc = r_b - F * t + F * np.sqrt(1.0 + t * t)
    d = F / np.sqrt(1.0 + t * t)
    return rc, F, rc - d, F + d * t


def cone_foot_r(h, spec=None):
    """Where the fillet meets the deck: the radius the pad has to cover."""
    return fillet_geom(h, spec)[0]


def cone_profile(h, deck=0.0, spec=None):
    """One cone as an (r, z) profile to revolve: a concave fillet off the
    pad onto a straight flank, and a concave dish for the tac instead of
    a point.

    The fillet arc runs from its foot on the deck, straight below its
    centre, to its tangent point on the flank, and it has to take the
    SHORT way round: from -90 degrees down through -180, past the point
    nearest the corner. A first cut swept the angle upward instead and
    went the long way through 0 degrees -- three quarters of a circle
    bulging outward, which revolved into a torus round every pier. The
    sign of the sweep is the whole difference between a blend and a
    donut, so the profile is checked below for concavity, not eyeballed.
    """
    rc, F, r_t, z_t = fillet_geom(h, spec)
    R_T, D_D = tip_r(spec), dish_d(spec)
    pts = [(0.0, deck), (rc, deck)]
    a0 = -np.pi / 2.0
    a1 = np.arctan2(z_t - F, r_t - rc)          # second quadrant
    if a1 > a0:
        a1 -= 2.0 * np.pi                        # go down through -180
    for a in np.linspace(a0, a1, 16)[1:]:
        pts.append((rc + F * np.cos(a), deck + F + F * np.sin(a)))
    pts.append((R_T, deck + h))
    # the cup: a spherical bowl D_D deep with its rim at the tip, so the
    # rim is a sharp edge that bites the wax and the bowl holds it
    Rs = (R_T ** 2 + D_D ** 2) / (2.0 * D_D)              # sphere radius
    zc = deck + h - D_D + Rs                             # its centre, above
    a_rim = np.arcsin(R_T / Rs)
    for a in np.linspace(a_rim, 0.0, 12)[1:]:
        pts.append((Rs * np.sin(a), zc - Rs * np.cos(a)))
    return pts


def a_cone(h, x, y, deck, spec=None):
    m = rev(cone_profile(h, deck, spec), sections=72)
    m.apply_translation([x, y, 0.0])
    return m


def tips(spec):
    """The four contact points, two per lobe."""
    cx, cy = spec["cross"] / 2.0, spec["fore"] / 2.0
    return [(sx * cx, sy * cy) for sx in (-1, 1) for sy in (-1, 1)]


def arm(x, y, deck, cone_h, spec=None):
    """A tapered arm from the hub out to one cone, flat on the plate,
    ending in a round pad concentric with the cone and wider than the
    fillet's foot -- so the whole blend lands on material. A cone
    centred on the end of a 4.5 mm arm with an 8 mm foot had half of it
    in the air."""
    from shapely.geometry import Point
    from shapely.ops import unary_union
    r = float(np.hypot(x, y))
    ang = np.degrees(np.arctan2(y, x))
    w0, w1 = ARM_W
    half = [w0 / 2.0, w1 / 2.0]
    pad_r = cone_foot_r(cone_h, spec) + PAD_MARGIN
    plan = unary_union([
        Polygon([(0.0, -half[0]), (r, -half[1]), (r, half[1]), (0.0, half[0])]),
        Point(r, 0.0).buffer(pad_r, quad_segs=36)])
    p = trimesh.creation.extrude_polygon(plan, deck)
    p.apply_transform(rot(ang, [0, 0, 1]))
    return p


# --- the stand ---------------------------------------------------------
def stand(spec):
    """One stand in its own frame: the underside -- hub and arms alike
    -- is the flat plane z = 0, so it sits on the pedestal's platform or
    on a table the same way. Nothing reaches below it."""
    deck = deck_of(spec)
    parts = [cyl(HUB_R, 0.0, HUB_T, sections=128)]
    for x, y in tips(spec):
        if deck == ARM_T:
            parts.append(arm(x, y, deck, spec["cone"], spec))
        parts.append(a_cone(spec["cone"], x, y, deck, spec))
    if spec.get("tail"):
        # a filled parabola growing out of the hub circle behind the -y
        # side, as thick as the arms, flat on the table: a foot against
        # tip-back. Its mouth is the hub's own width, at the pivot; its
        # vertex is `reach` behind it
        w, reach = spec["tail"]
        hw = w / 2.0
        xs = np.linspace(-hw, hw, 49)
        para = Polygon([(x, -reach * (1.0 - (x / hw) ** 2)) for x in xs]
                       + [(hw, 0.5), (-hw, 0.5)])
        parts.append(trimesh.creation.extrude_polygon(para, ARM_T))
    return union(parts)


XW_UP_T = 10.0              # the upper arm: ONE flat-topped piece this tall,
                            # printed roof-down so nothing on it is a bridge
XW_POCKET_Z = ARM_T + 0.4   # the pocket under it clears the lower arm by two
                            # layers: PETG top surfaces crown a little
# The upper arm's cones sit on Ø3 dowels pressed into the arm. The dowel
# is its own piece because the arm prints roof-down, so a peg printed on
# it would point into the plate; and the cone gets a socket rather than
# a spigot so it prints standing on its own flat foot. Nominal fits carry
# the tenth or two that small FDM holes print undersize.
XW_DOWEL = (1.5, 7.6)       # radius and length
XW_SOCKET = (1.55, 4.0)     # in the arm: Ø3.1 drawn, a firm press
XW_CONE_SOCKET = (1.65, 4.0)  # in the cone's base: Ø3.3 drawn, a snug slip
XW_FOOT_BAND = 0.8          # a loose cone's foot is a vertical band this tall
                            # under its fillet: the fillet alone thinned to a
                            # knife edge where it met the plate
XW_HEAD_GAP = 0.3           # the pin's head stands this far off the upper arm,
                            # so a pin pressed home does not clamp the pivot
XW_NECK_HW = 1.5            # the lower bar's half-width where it meets the
                            # hub: a 3 mm neck
XW_TAPER = 8.0              # and how far out it tapers back to full width.
                            # The notches this leaves either side of the
                            # lower bar are where the upper arm's legs swing
                            # in closer to the pivot: more travel
XW_ROUND = 1.5              # inside corners of the arms' outlines, where
                            # a bar meets a pad or the disc
XW_CONN_FILLET = 2.5        # concave fillet from the connector down onto
                            # each end, in place of a square step
XW_CONN_EDGE = 0.8          # the connector's top edge at each end, rounded


def xw_plan(L, pad_r, hub_r=None):
    """An arm's outline: bar, a pad at each end, optionally the disc at
    the pivot, as ONE polygon with its inside corners rounded. One
    outline extruded once: the disc and bar as two solids met in the same
    top plane and left zero-length edges the 3MF export turned into
    non-manifold ones."""
    from shapely.geometry import Point
    from shapely.ops import unary_union
    w = XW_BAR_W / 2.0
    if hub_r:
        # the lower arm: the bar tapers in to a neck where it meets the hub
        r0, r1, h0 = hub_r - 0.5, hub_r - 0.5 + XW_TAPER, XW_NECK_HW
        bar = Polygon([(-L, -w), (-r1, -w), (-r0, -h0), (r0, -h0), (r1, -w),
                       (L, -w), (L, w), (r1, w), (r0, h0), (-r0, h0),
                       (-r1, w), (-L, w)])
    else:
        bar = Polygon([(-L, -w), (L, -w), (L, w), (-L, w)])
    parts = [bar, Point(L, 0.0).buffer(pad_r, quad_segs=36),
             Point(-L, 0.0).buffer(pad_r, quad_segs=36)]
    if hub_r:
        parts.append(Point(0.0, 0.0).buffer(hub_r, quad_segs=48))
    plan = unary_union(parts)
    return plan.buffer(XW_ROUND, quad_segs=12).buffer(-XW_ROUND, quad_segs=12)


def xw_bar(L, pad_r, z0, z1, ang_deg, hub_r=None):
    """A straight bar through the pivot, pads at both ends, lying z0..z1,
    optionally with the pivot disc in the same outline."""
    b = trimesh.creation.extrude_polygon(xw_plan(L, pad_r, hub_r), z1 - z0)
    b.apply_translation([0, 0, z0])
    b.apply_transform(rot(ang_deg, [0, 0, 1]))
    return b


def xw_bore(r, z0, top, bottom_mouth=None):
    """A hole of radius r up to `top` with a 45 degree lead-in at its
    mouth, as ONE revolved cutter. A cylinder and a separate chamfer cone
    met exactly on the hole's wall and exported non-manifold. With
    `bottom_mouth`, a lead-in at that height too: a hole that opens onto
    the plate has its first layer squashed narrower than the rest."""
    c = XW_HOLE_CHAMFER
    if bottom_mouth is None:
        prof = [(0.0, z0), (r, z0)]
    else:
        prof = [(0.0, z0), (r + c + 1.0, z0), (r + c + 1.0, bottom_mouth - 1.0),
                (r, bottom_mouth + c)]
    prof += [(r, top - c), (r + c + 1.0, top + 1.0), (0.0, top + 1.0)]
    return rev(prof, sections=64)


def xw_connector(Rc, z0, z1):
    """The connector in the upper arm's frame (bar along x): a straight
    bridge of bar width from -Rc to Rc, its top edges rounded, and a
    concave fillet at each end carrying it down onto the arm, drawn in
    side view and extruded across the bar's width."""
    F, E, w = XW_CONN_FILLET, XW_CONN_EDGE, XW_BAR_W / 2.0
    pts = [(-Rc - F, z0), (Rc + F, z0)]
    # right end: concave fillet up from the arm's top, centre in the air
    for t in np.linspace(-np.pi / 2, -np.pi, 12)[1:]:
        pts.append((Rc + F + F * np.cos(t), z0 + F + F * np.sin(t)))
    # up the end face, round the top edge, across, round, down
    for t in np.linspace(0.0, np.pi / 2, 8):
        pts.append((Rc - E + E * np.cos(t), z1 - E + E * np.sin(t)))
    for t in np.linspace(np.pi / 2, np.pi, 8):
        pts.append((-Rc + E + E * np.cos(t), z1 - E + E * np.sin(t)))
    for t in np.linspace(0.0, -np.pi / 2, 12)[1:]:
        pts.append((-Rc - F + F * np.cos(t), z0 + F + F * np.sin(t)))
    side = Polygon(pts)
    c = trimesh.creation.extrude_polygon(side, 2.0 * w)
    # profile drawn in (x, z), extruded along y
    c.apply_transform(np.array([[1, 0, 0, 0], [0, 0, 1, -w], [0, 1, 0, 0],
                                [0, 0, 0, 1]], float))
    return c


def xw_pins(spec, beta=None):
    """Lower pins at -beta, upper pins at +beta, on the circle of radius L."""
    b = np.radians(spec["alpha"] if beta is None else beta)
    L = spec["L"]
    lower = [(sgn * L * np.cos(b), -sgn * L * np.sin(b)) for sgn in (1, -1)]
    upper = [(sgn * L * np.cos(b), sgn * L * np.sin(b)) for sgn in (1, -1)]
    return lower, upper


def xw_pad_r(spec):
    return cone_foot_r(spec["cone"], spec) + PAD_MARGIN


def xw_close(spec):
    """The half-angle the pads let the arms close to, less a margin: the
    tightest angle the relief is cut for."""
    return float(np.degrees(np.arcsin(xw_pad_r(spec) / spec["L"]))) \
        - XW_CLOSE_MARGIN


def xw_open(spec):
    """The half-angle the pads let the arms open to -- the other pair
    meets on the cross side -- plus the same margin."""
    return float(np.degrees(np.arccos(xw_pad_r(spec) / spec["L"]))) \
        + XW_CLOSE_MARGIN


def xw_disc_r(spec):
    return XW_HUB_R


def xw_relief(spec):
    """What is cut from the upper arm's ends, in the upper arm's own frame:
    the negative of the lower arm's hub, XW_HOLDOFF clear of it, and
    nothing else. The arms turn as far as that allows, which is measured
    off the built parts rather than designed in. An earlier cut also
    cleared the lower bar's whole sweep, which made the connector bridge
    34 mm on the L to buy a swing the stand does not need."""
    from shapely.geometry import Point
    return Point(0, 0).buffer(XW_HUB_R + XW_HOLDOFF, quad_segs=48)


def xw_span(spec):
    """The connector runs to where the upper end is its full width again,
    plus XW_LAND: the farthest the relief reaches along the bar."""
    w = XW_BAR_W / 2.0
    band = Polygon([(-200, -w), (200, -w), (200, w), (-200, w)])
    cut_ = xw_relief(spec).intersection(band)
    xs = np.array(cut_.bounds)
    return float(max(abs(xs[0]), abs(xs[2]))) + XW_LAND


def xw_levels(spec):
    return dict(bar=ARM_T, upper=XW_UP_T, pocket=XW_POCKET_Z,
                contact=ARM_T + spec["cone"])


def xw_pins(spec, beta=None):
    """Lower pins at -beta, upper pins at +beta, on the circle of radius L."""
    b = np.radians(spec["alpha"] if beta is None else beta)
    L = spec["L"]
    lower = [(sgn * L * np.cos(b), -sgn * L * np.sin(b)) for sgn in (1, -1)]
    upper = [(sgn * L * np.cos(b), sgn * L * np.sin(b)) for sgn in (1, -1)]
    return lower, upper


def xw_pocket(spec):
    """The upper arm's underside pocket, in the upper arm's own frame:
    the lower hub's profile plus holdoff, and the channel the lower bar
    sweeps through between the pads' limits, half a millimetre clear. It
    opens downward in use and upward on the plate, so it needs no bridge."""
    from shapely import affinity
    from shapely.geometry import Point
    from shapely.ops import unary_union
    L, pad = spec["L"], xw_pad_r(spec)
    hw = XW_BAR_W / 2.0 + XW_SWEEP_CLR
    reach = L - pad - 0.5              # stop short of the upper arm's pads
    strip = Polygon([(-reach, -hw), (reach, -hw), (reach, hw), (-reach, hw)])
    strips = [affinity.rotate(strip, -2.0 * b, origin=(0, 0))
              for b in np.linspace(xw_close(spec), xw_open(spec), 72)]
    shape = unary_union(strips + [Point(0, 0).buffer(
        XW_HUB_R + XW_HOLDOFF, quad_segs=48)]).simplify(0.02)
    return shape.buffer(XW_ROUND, quad_segs=12).buffer(-XW_ROUND, quad_segs=12)


def xw_arms(spec, lift=0.0):
    """The two arms without their cones. The lower arm: a bar tapering to
    a neck at a Ø9 hub, 5 tall. The upper arm: one flat-topped block
    XW_UP_T tall with the pocket cut up into it from underneath."""
    L, a = spec["L"], spec["alpha"]
    pad = xw_pad_r(spec)
    lower = xw_bar(L, pad, 0.0, ARM_T, -a, hub_r=XW_HUB_R)
    block = xw_bar(L, pad, lift, XW_UP_T, a)
    pocket = trimesh.creation.extrude_polygon(xw_pocket(spec), XW_POCKET_Z + 1.0)
    pocket.apply_translation([0, 0, -1.0])
    pocket.apply_transform(rot(a, [0, 0, 1]))
    return lower, cut(block, [pocket])


def xw_cone_part(spec, x, y):
    """One of the upper arm's cones as its own piece: the cone standing
    on the arm's top at XW_UP_T, reaching the same contact plane as the
    lower arm's cones, with a socket up into its base for the dowel. It
    prints on that flat foot."""
    band = XW_FOOT_BAND
    h = xw_levels(spec)["contact"] - XW_UP_T - band
    c = union([a_cone(h, x, y, XW_UP_T + band, spec),
               cyl(cone_foot_r(h, spec), XW_UP_T, XW_UP_T + band + 0.01,
                   x, y, sections=72)])
    r, d = XW_CONE_SOCKET
    # the socket opens at the cone's foot with a 0.3 mm lead-in
    sock = rev([(0.0, XW_UP_T - 1.0), (r + 1.3, XW_UP_T - 1.0),
                (r, XW_UP_T + 0.3), (r, XW_UP_T + d), (0.0, XW_UP_T + d)],
               sections=48)
    sock.apply_translation([x, y, 0.0])
    return cut(c, [sock])


def xw_dowel(x, y):
    """A plain Ø3 dowel, chamfered both ends, standing where it sits: half
    in the arm, half in the cone."""
    r, L = XW_DOWEL
    z0 = XW_UP_T - XW_SOCKET[1] + 0.2
    d = rev([(0.0, z0), (r - 0.3, z0), (r, z0 + 0.3), (r, z0 + L - 0.3),
             (r - 0.3, z0 + L), (0.0, z0 + L)], sections=48)
    d.apply_translation([x, y, 0.0])
    return d


def xwing(spec):
    """Base, upper arm and pin in the assembled frame at the default
    opening, the strip resting on the disc: the pose it is in under a
    tooth, and the pose the cups are checked coplanar in."""
    Z = xw_levels(spec)
    h = spec["cone"]
    lo_pins, hi_pins = xw_pins(spec)
    lower, upper = xw_arms(spec)
    base = [lower] + [a_cone(h, x, y, ARM_T, spec) for x, y in lo_pins]
    base = cut(union(base), [xw_bore(XW_HOLE_PRESS_R, -2.0, ARM_T,
                                     bottom_mouth=0.0)])
    z1 = XW_UP_T
    sockets = []
    for x, y in hi_pins:
        sk = xw_bore(XW_SOCKET[0], XW_UP_T - XW_SOCKET[1], XW_UP_T)
        sk.apply_translation([x, y, 0.0])
        sockets.append(sk)
    top = cut(upper, [xw_bore(XW_HOLE_RUN_R, -1.0, z1)] + sockets)
    kk = spec['id'][3:]
    cones = {f"xwing_{kk}_cone{i}": xw_cone_part(spec, x, y)
             for i, (x, y) in enumerate(hi_pins)}
    cones.update({f"xwing_{kk}_dowel{i}": xw_dowel(x, y)
                  for i, (x, y) in enumerate(hi_pins)})
    # the pin: pressed down from above, head on the connector, tip flush
    # with the flat bottom, chamfered so it starts in the hole
    hr, hh = XW_PIN_HEAD
    g = XW_HEAD_GAP
    pin = union([cyl(hr, z1 + g, z1 + g + hh, sections=64),
                 rev([(0.0, 0.0), (XW_PIN_R - 0.4, 0.0), (XW_PIN_R, 0.4),
                      (XW_PIN_R, z1 + g + 0.5), (0.0, z1 + g + 0.5)],
                     sections=64)])
    k = spec['id'][3:]
    return {f"xwing_{k}_base": base, f"xwing_{k}_top": top,
            f"xwing_{k}_pin": pin, **cones}


def xw_hub_range(spec, step=1.0):
    """Where the ARMS alone would meet: both built without cones, the
    upper turned against the lower until they touch. Set beside the
    range the cones allow, so it is known which one limits the swing."""
    import trimesh.collision as tc
    a = spec["alpha"]
    lo, hi = xw_arms(spec, lift=0.1)
    cm = tc.CollisionManager()
    cm.add_object("lo", lo)
    cm.add_object("hi", hi)
    def clear(beta):
        cm.set_transform("hi", rot(2.0 * (beta - a), [0, 0, 1]))
        return not cm.in_collision_internal()
    if not clear(a):
        return None
    b0 = a
    while b0 - step > 0.0 and clear(b0 - step):
        b0 -= step
    b1 = a
    while b1 + step < 90.0 and clear(b1 + step):
        b1 += step
    return [b0, b1]


def xw_print_overhang(top):
    """The upper arm as it prints, roof-down on the plate: the area of
    downward-facing surface that is not on the plate, and the widest such
    patch. Nothing but the two cone sockets' floors should show."""
    m = top.copy()
    m.apply_transform(rot(180.0, [1, 0, 0]))
    m.apply_translation([0, 0, -m.bounds[0][2]])
    n, c = m.face_normals, m.triangles_center
    # steeper than 45 degrees: a 45 degree lead-in chamfer prints unaided
    down = (n[:, 2] < -0.8) & (c[:, 2] > 0.05)
    area = float(m.area_faces[down].sum())
    widest = 0.0
    if down.any():
        sub = m.submesh([np.where(down)[0]], append=True)
        for piece in sub.split(only_watertight=False):
            widest = max(widest, float(max(piece.extents[:2])))
    return dict(overhang_mm2=round(area, 1), widest_mm=round(widest, 1))


def _bore_d(mesh, z):
    """Diameter of the hole on the pivot axis, sectioned at height z: the
    interior ring of the section that encloses the origin."""
    from shapely.geometry import Point
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if sec is None:
        return None
    polys, to3 = sec.to_planar()
    origin = trimesh.transform_points([[0, 0, z]], np.linalg.inv(to3))[0][:2]
    for poly in polys.polygons_full:
        for ring in poly.interiors:
            from shapely.geometry import Polygon as SPoly
            hole = SPoly(ring)
            if hole.contains(Point(origin)):
                return float(2.0 * np.sqrt(hole.area / np.pi))
    return None


def _shaft_d(mesh, z):
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if sec is None:
        return None
    polys, _ = sec.to_planar()
    return float(2.0 * np.sqrt(max(p.area for p in polys.polygons_full) / np.pi))


def xw_pin_fit(parts, k):
    """The pin against both holes, all three measured off the built
    bodies at mid-depth of each hole: a press in the lower arm, a running
    fit in the upper. Diameters from area, so a 64-gon reads as the
    circle it stands for."""
    pin = parts[f"xwing_{k}_pin"]
    base, top = parts[f"xwing_{k}_base"], parts[f"xwing_{k}_top"]
    z_low = ARM_T / 2.0
    z_top = (XW_POCKET_Z + XW_UP_T) / 2.0
    pin_d = _shaft_d(pin, z_low)
    press = _bore_d(base, z_low)
    run = _bore_d(top, z_top)
    out = dict(pin_d=round(pin_d, 3), press_hole_d=round(press, 3),
               run_hole_d=round(run, 3),
               press_clearance=round(press - pin_d, 3),
               run_clearance=round(run - pin_d, 3),
               press_engagement=round(ARM_T - XW_HOLE_CHAMFER, 2),
               run_engagement=round(XW_UP_T - XW_POCKET_Z - XW_HOLE_CHAMFER, 2))
    return out


def cone_stress(spec, side_N=1.0):
    """Bending stress at a cone's narrowest section, the tip, from a
    sideways push at the cup -- a tooth nudged while it is set down. The
    section grows down the flank, so the tip is where it breaks. PETG
    yields near 50 MPa; the spec's 1.3 mm point read 37 MPa under this
    load, which is why it snapped in the hand."""
    r = tip_r(spec)
    h = spec["cone"]
    I = np.pi * r ** 4 / 4.0                     # second moment, circle
    return round(float(side_N * h * r / I), 2)   # M c / I, MPa


def xw_cone_fit(parts, k, spec):
    """The dowel against the arm's socket and the cone's socket, and the
    cone as it prints on its foot: all measured off the built bodies."""
    lo, up = xw_pins(spec)
    x, y = up[0]
    shift = np.eye(4)
    shift[:3, 3] = [-x, -y, 0.0]
    dow = parts[f"xwing_{k}_dowel0"].copy().apply_transform(shift)
    top = parts[f"xwing_{k}_top"].copy().apply_transform(shift)
    cone = parts[f"xwing_{k}_cone0"].copy().apply_transform(shift)
    z_arm = XW_UP_T - XW_SOCKET[1] / 2.0
    z_cone = XW_UP_T + XW_CONE_SOCKET[1] / 2.0
    d = _shaft_d(dow, z_arm)
    arm_hole, cone_hole = _bore_d(top, z_arm), _bore_d(cone, z_cone)
    c = cone.copy()
    c.apply_translation([0, 0, -c.bounds[0][2]])
    n, ctr = c.face_normals, c.triangles_center
    on = float(c.area_faces[(n[:, 2] < -0.99) & (ctr[:, 2] < 1e-6)].sum())
    over = float(c.area_faces[(n[:, 2] < -0.8) & (ctr[:, 2] > 0.05)].sum())
    return dict(dowel_d=round(d, 3), arm_hole_d=round(arm_hole, 3),
                cone_hole_d=round(cone_hole, 3),
                arm_clearance=round(arm_hole - d, 3),
                cone_clearance=round(cone_hole - d, 3),
                cone_on_plate_mm2=round(on, 1), cone_overhang_mm2=round(over, 1),
                cone_lever=round(float(c.extents[2] / (np.sqrt(on / np.pi))), 2))


def xw_hold(spec, tooth_g=500.0, offset_mm=None):
    """Whether the upper arm stays put with a tooth sitting off-centre.
    Both arms stand on the table on their own pads, so a tooth on one cup
    loads that arm's pad, not the pivot; what is left is the strip
    lifting off the disc, which the pressed pin resists. A Ø6 PETG pin
    pressed a tenth tight is taken to hold 60 N; an estimate, reported
    and not gated."""
    off = spec["L"] if offset_mm is None else offset_mm
    tip = tooth_g / 1000.0 * 9.81 * off / 1000.0
    hold = (60.0 + tooth_g / 1000.0 * 9.81) * xw_span(spec) / 1000.0
    return dict(tipping_Nm=round(tip, 3), holding_Nm=round(hold, 3),
                margin=round(hold / tip, 1))


def xw_opening(spec, base, top, step=1.0):
    """How far the blade can turn before it meets the base: the clear
    range of the half-angle beta containing the default, found by turning
    the BUILT blade against the BUILT base, lifted a tenth off its seat."""
    import trimesh.collision as tc
    cm = tc.CollisionManager()
    cm.add_object("base", base)
    t = top.copy()
    t.apply_translation([0, 0, 0.1])      # off its seat, or the seat is a hit
    cm.add_object("top", t)
    a = spec["alpha"]
    def clear(beta):
        cm.set_transform("top", rot(2.0 * (beta - a), [0, 0, 1]))
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


def parse_which(which):
    """"all", or a comma-separated set of stand ids. The shop offers this
    as tick-boxes because the spec asks for the variants to be printed
    together: the fine tips get their minimum layer time from the travel
    between parts, so a plate of four is easier to print than one."""
    if not which or which == "all":
        return list(ALL_IDS)
    ids = [w.strip().lower() for w in which.split(",") if w.strip()]
    bad = [i for i in ids if i not in ALL_IDS]
    if bad:
        raise ValueError("no such stand: " + ", ".join(bad))
    return [i for i in ALL_IDS if i in ids]                # keep size order


def build(which="all"):
    out = {}
    for i in parse_which(which):
        if i in XW_BY_ID:
            out.update(xwing(XW_BY_ID[i]))
        else:
            out[f"stand_{i}"] = stand(BY_ID[i])
    return out


# --- layout and export -------------------------------------------------
def layout(parts, gap=6.0):
    """All four on one plate: they are small, and the spec wants them
    printed together so the fine tips get their minimum layer time from
    the travel between parts rather than from a slowdown."""
    out, poses = {}, {}
    x, y, row_h = 0.0, 0.0, 0.0
    for n in sorted(parts):
        m = parts[n].copy()
        # the X-wing's pin prints head-down: standing on its tip, the head
        # is a 2 mm overhang all round
        # the X-wing's upper arm prints upside down too, on Brett's call
        F = (rot(180.0, [1, 0, 0]) if n.endswith(("_pin", "_top"))
             else np.eye(4))
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


def stand_meta(parts, poses):
    return {
        "design": "tooth_stand",
        "dock": dict(flat_bottom=True, plat_r=PLAT_R),
        "hub": dict(r=HUB_R, t=HUB_T),
        "cone": dict(tip_r=TIP_R, half_deg=HALF_DEG, dish_ratio=DISH_RATIO),
        # contact_z travels with each stand so a page can draw the plane
        # the tooth rests on without re-deriving the deck rule in JS
        "stands": [dict(s, tips=tips(s), deck=deck_of(s),
                        tip_back_deg=tip_back(s),
                        contact_z=contact_z(s), dish_z=dish_z(s),
                        base_r=round(float(cone_base_r(s["cone"], s)), 3),
                        foot_r=round(float(cone_foot_r(s["cone"], s)), 3),
                        tip_r=tip_r(s), dish=round(dish_d(s), 3),
                        fillet=round(fillet_r(s), 3))
                   for s in STANDS],
        "xwings": [dict(x, tips=tips(x), contact_z=contact_z(x),
                        dish_z=dish_z(x), levels=xw_levels(x),
                        pivot=f"plain \u00d8{2 * XW_PIN_R:g} printed pin: pressed into the lower arm, turning in the upper",
                        upper_t=XW_UP_T,
                        dowel=dict(r=XW_DOWEL[0], length=XW_DOWEL[1],
                                   proud=round(XW_DOWEL[1] - XW_SOCKET[1] + 0.2, 2)),
                        disc_r=round(float(xw_disc_r(x)), 2), holdoff=XW_HOLDOFF,
                        span=round(float(xw_span(x)), 2),
                        conn_t=XW_CONN_T, hub_r=XW_HUB_R, bar_t=ARM_T,
                        pin=dict(r=XW_PIN_R, head=list(XW_PIN_HEAD)),
                        print=(xw_print_overhang(parts[f"xwing_{x['id'][3:]}_top"])
                               if f"xwing_{x['id'][3:]}_top" in parts else None),
                        hold=xw_hold(x),
                        base_r=round(float(cone_base_r(x["cone"], x)), 3),
                        tip_r=tip_r(x), dish=round(dish_d(x), 3),
                        opening=(xw_opening(x, parts[f"xwing_{x['id'][3:]}_base"],
                                            parts[f"xwing_{x['id'][3:]}_top"])
                                 if f"xwing_{x['id'][3:]}_top" in parts else None))
                   for x in XWINGS],
        "to_world": {n: [round(float(v), 6) for v in poses[n].ravel()]
                     for n in poses},
        "volume_cm3": {n: round(float(m.volume) / 1000.0, 2)
                       for n, m in parts.items()},
    }


def export(parts, out):
    flat, poses = layout(parts)
    sc = trimesh.Scene()
    for n, m in flat.items():
        sc.add_geometry(m, geom_name=n, node_name=n)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sc.export(out)
    from embed_settings import embed
    # a brim earns its keep here: four small footprints, and the tallest
    # is a 24 mm cone on a 20 mm hub
    embed(out, brim=True)
    meta = stand_meta(parts, poses)
    with zipfile.ZipFile(out, "a", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Metadata/tooth_stand.json",
                   json.dumps(meta, separators=(",", ":")))
    from meshcheck import export_defects
    return export_defects(out), meta


# --- measurement -------------------------------------------------------
def tip_back(spec, tooth_mm=None):
    """How far a tooth can lean back before the stand goes with it: the
    angle at which its centroid passes the support edge behind the
    pivot. The centroid is taken at 44% of the tooth's height, as the
    Meherrin tooth's is, on top of the contact plane; the tooth is the
    top of the stand's band unless given."""
    h = (spec["teeth"][1] if tooth_mm is None else tooth_mm) * 0.44
    edge = spec["fore"] / 2.0 + cone_foot_r(spec["cone"], spec) + PAD_MARGIN
    if spec.get("tail"):
        edge = max(edge, spec["tail"][1])
    return round(float(np.degrees(np.arctan2(edge, contact_z(spec) + h))), 1)


def deck_of(spec):
    """The height the cones stand on: the arm tops when the tips reach
    past the hub, the hub top when they do not. One deck for all four, so
    the four cones are identical and the contact plane is flat by
    construction rather than by arithmetic."""
    reach = max(np.hypot(x, y) for x, y in tips(spec))
    return ARM_T if reach + cone_foot_r(spec["cone"], spec) + PAD_MARGIN > HUB_R else HUB_T


def contact_z(spec):
    """The plane the tooth actually rests on: the RIM of each dish, which
    is the highest thing on the stand. The dish bottom is DISH_D below it
    and holds the tac; the rim is what carries the load and what the
    'nothing above this plane' gate is measured against."""
    if spec.get("xwing"):
        return xw_levels(spec)["contact"]
    return deck_of(spec) + spec["cone"]


def dish_z(spec):
    return contact_z(spec) - dish_d(spec)


def contact_points(spec):
    return [(x, y, contact_z(spec)) for x, y in tips(spec)]


def tip_points(spec):
    """The floor of each dish, where the speck of tac sits."""
    return [(x, y, dish_z(spec)) for x, y in tips(spec)]


def tips_coplanar(spec, m, tol=0.05):
    """The four dishes must lie in one plane, or the tooth rocks. Read
    off the built mesh, not off the intent: ray down the axis of each
    cone and take the first surface."""
    pts = tip_points(spec)
    origins = np.array([[x, y, 200.0] for x, y, _ in pts])
    dirs = np.tile([0.0, 0.0, -1.0], (4, 1))
    loc, idx_r, _ = m.ray.intersects_location(origins, dirs,
                                              multiple_hits=False)
    if len(loc) != 4:
        return None, None
    zs = np.array([loc[list(idx_r).index(i)][2] for i in range(4)])
    return float(np.ptp(zs)), [round(float(z), 3) for z in zs]


def tip_diameter(m, spec):
    """The tip as built, measured by slicing the cone just under its rim
    -- a slicer that cannot resolve the flank would show up here."""
    pts = tip_points(spec)
    x, y, z = pts[0]
    # just under the rim of the dish, which is where the tip's diameter
    # actually is; the flank is already widening 0.06 mm per mm below it
    sec = m.section(plane_origin=[0, 0, z + dish_d(spec) - 0.05],
                    plane_normal=[0, 0, 1])
    if sec is None:
        return None
    p, _ = sec.to_planar()
    best = None
    for poly in p.polygons_full:
        cx, cy = poly.centroid.x, poly.centroid.y
        if np.hypot(cx - x, cy - y) < 3.0:
            lo, hi = np.array(poly.bounds).reshape(2, 2)
            best = float(np.mean(hi - lo))
    return best


SPECIMEN_GLB = os.path.join(HERE, "..", "models", "specimen",
                            "BigMeherrin.glb")


def surrogate(spec):
    """A specimen for the stand to cast its shadow on, sitting on the
    four tips.

    The one tooth that exists as a mesh, scaled to the middle of this
    stand's band; or, when that file is absent -- models/ is not in the
    repository -- a lenticular blob of the same measured proportions.
    Which one was used travels with the number, because a shadow cast on
    a blob is a weaker claim than one cast on a tooth.
    """
    L = float(np.mean(spec["teeth"]))
    what, m = "BigMeherrin scaled to %.0f mm" % L, None
    if os.path.isfile(SPECIMEN_GLB):
        try:
            sc = trimesh.load(SPECIMEN_GLB, force="scene")
            m = trimesh.util.concatenate(list(sc.geometry.values()))
            m.apply_transform(rot(90.0, [1, 0, 0]))       # y up -> z up
            m.apply_scale(L / 129.0)
        except Exception:                                 # noqa: BLE001
            m = None
    if m is None:
        what = "lenticular surrogate, %.0f mm" % L
        m = trimesh.creation.icosphere(subdivisions=3)
        m.apply_scale([0.76 * L / 2.0, 0.15 * L / 2.0, L / 2.0])
    z = contact_z(spec)
    m.apply_translation([-m.centroid[0], -m.centroid[1], z - m.bounds[0][2]])
    return m, what


def occlusion(stand_mesh, spec, n_pts=250, n_az=12):
    """What fraction of the specimen the stand hides, per ring.

    For every camera pose in the capture protocol, each sampled point on
    the specimen that FACES that camera casts one ray to it; the ray is
    blocked or it is not, and the fraction blocked is what the mount
    costs the reconstruction. Points facing away are the tooth hiding
    itself, which the opposite side of the ring covers, so they are not
    counted against the stand.
    """
    spm, what = surrogate(spec)
    pts, fid = trimesh.sample.sample_surface(spm, n_pts)
    nrm = spm.face_normals[fid]
    centre = np.array(contact_points(spec)).mean(axis=0)
    per, tot_seen, tot_blocked = {}, 0, 0
    for p in J.PROTOCOL:
        th = p["elev"]
        seen = blocked = 0
        for i in range(n_az):
            phi = 360.0 * i / n_az
            cam = centre + J.R * np.array([
                np.cos(np.radians(th)) * np.cos(np.radians(phi)),
                np.cos(np.radians(th)) * np.sin(np.radians(phi)),
                np.sin(np.radians(th))])
            d = cam - pts
            d = d / np.linalg.norm(d, axis=1)[:, None]
            face = (nrm * d).sum(axis=1) > 0.0
            if not face.any():
                continue
            hit = stand_mesh.ray.intersects_any(
                pts[face] + d[face] * 0.05, d[face])
            seen += int(face.sum())
            blocked += int(np.count_nonzero(hit))
        per[str(int(th))] = round(100.0 * blocked / max(seen, 1), 1)
        tot_seen += seen
        tot_blocked += blocked
    return dict(per_ring=per, specimen=what,
                overall=round(100.0 * tot_blocked / max(tot_seen, 1), 1))


def measure(parts):
    rep = {"bodies": len(parts)}
    rep["watertight"] = {n: bool(m.is_watertight) for n, m in parts.items()}
    rep["dims_mm"] = {n: [round(float(x), 2) for x in m.extents]
                      for n, m in parts.items()}
    flat, _ = layout(parts)
    rep["fits_plate"] = {n: bool(fits_plate(m)) for n, m in flat.items()}
    rep["coplanar_mm"], rep["tip_z"] = {}, {}
    rep["tip_dia_mm"], rep["occlusion"] = {}, {}
    rep["above_contact_mm"], rep["xwing_opening"] = {}, {}
    # an X-wing is measured assembled: its two bodies as one mount
    mounts = {}
    for n, m in parts.items():
        mounts.setdefault(mount_of(n), []).append(m)
    for n, ms in mounts.items():
        spec = spec_of(n if not n.startswith("xwing") else n + "_base")
        m = ms[0] if len(ms) == 1 else trimesh.util.concatenate(ms)
        dz, zs = tips_coplanar(spec, m)
        rep["coplanar_mm"][n] = dz
        rep["tip_z"][n] = zs
        rep["tip_dia_mm"][n] = tip_diameter(m, spec)
        rep["occlusion"][n] = occlusion(m, spec)
        rep["above_contact_mm"][n] = round(
            float(m.bounds[1][2] - contact_z(spec)), 4)
        if spec.get("xwing"):
            rep["xwing_opening"][n] = xw_opening(
                spec, parts[n + "_base"], parts[n + "_top"])
            rep.setdefault("xwing_hold", {})[n] = xw_hold(spec)
            rep.setdefault("xwing_hub_range", {})[n] = xw_hub_range(spec)
            rep.setdefault("xwing_pin_fit", {})[n] = xw_pin_fit(parts, n[6:])
            rep.setdefault("xwing_print", {})[n] = xw_print_overhang(parts[n + "_top"])
            rep.setdefault("xwing_cone_fit", {})[n] = xw_cone_fit(parts, n[6:], spec)
    rep["cone_stress_MPa"] = {s["id"]: cone_stress(s) for s in STANDS + XWINGS}
    rep["spans"] = {s["id"]: dict(cross=s["cross"], fore=s["fore"],
                                  cone=s["cone"], teeth=list(s["teeth"]))
                    for s in STANDS + XWINGS}
    vol = sum(float(m.volume) for m in parts.values()) / 1000.0
    rep["volume_cm3"] = round(vol, 2)
    rep["est_g"] = round(vol * PETG_G_PER_CM3, 1)
    return rep


def gates(rep):
    return [
        ("watertight", all(rep["watertight"].values())),
        ("fits_plate", all(rep["fits_plate"].values())),
        ("tips_coplanar", all(v is not None and v < 0.05
                              for v in rep["coplanar_mm"].values())),
        ("tip_is_its_size", all(
            v is not None and abs(v - 2 * tip_r(spec_of(
                n if not n.startswith("xwing") else n + "_base"))) < 0.25
            for n, v in rep["tip_dia_mm"].items())),
        # an X-wing has to turn at all: clear at its default setting
        ("xwing_turns", all(o is not None
                            for o in rep["xwing_opening"].values())),
        # a sideways newton at the cup must stay well inside PETG's yield
        # a newton sideways at the cup, against PETG's ~50 MPa yield: the
        # thinnest tip here reads 11, a margin of four and a half
        ("cones_not_fragile", all(v < 15.0
                                  for v in rep["cone_stress_MPa"].values())),
        # the loose cones stand on their own feet on the plate, and the
        # dowel presses into the arm and slips into the cone
        ("xwing_cones_print_on_their_feet", all(
            f["cone_on_plate_mm2"] > 40.0 and f["cone_overhang_mm2"] < 12.0
            for f in rep.get("xwing_cone_fit", {}).values())),
        ("xwing_dowel_fits", all(
            0.05 <= f["arm_clearance"] <= 0.15 and 0.2 <= f["cone_clearance"] <= 0.4
            for f in rep.get("xwing_cone_fit", {}).values())),
        # the pin presses into the lower arm and turns in the upper, as
        # designed: nominal clearances that print as a press and a run
        ("xwing_pin_fits", all(
            0.05 <= f["press_clearance"] <= 0.15
            and 0.3 <= f["run_clearance"] <= 0.5
            for f in rep.get("xwing_pin_fit", {}).values())),
        # The gate that carries the optical claim. Nothing below the
        # contact plane can occlude a specimen resting on it from any
        # camera above the horizon -- proved by the negative controls in
        # the tests -- so "the mount is invisible" reduces to this.
        ("nothing_above_contact_plane", all(
            v <= 1e-6 for v in rep["above_contact_mm"].values())),
        ("mount_invisible", all(o["overall"] < 1.0
                                for o in rep["occlusion"].values())),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stand", default="all",
                    help="all, or a comma-separated set of "
                         + ", ".join(ALL_IDS))
    ap.add_argument("--out")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    try:
        parts = build(a.stand)
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
