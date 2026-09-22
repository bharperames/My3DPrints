#!/usr/bin/env python3
"""Orbital scanning jig: a stationary specimen and a camera that orbits it.

A turntable rotates the specimen under fixed lights, so the highlights
crawl across it between frames and photogrammetry reads the crawl as the
surface moving. This jig keeps the specimen, the backdrop and the lights
still and moves the CAMERA instead, along a spherical shell of radius
R = 150 mm about the specimen: azimuth on a bearing-guided rotor ring,
elevation on a quadrant arc the ring carries.

THE FRAME

Everything is built in the frame the spec's kinematics use: origin at the
specimen's focal point, +Z up, the rotor turning about Z. The camera's
entrance pupil sits at

    P(phi, theta) = R (cos theta cos phi, cos theta sin phi, sin theta)

and looks at the origin with its up vector along the arc's tangent. The
arc lies in a vertical plane offset Y_ARC from the meridian, and the
carriage reaches back across to hold the camera IN the meridian plane —
the lens is in the radial band the arc occupies, so they cannot share a
plane, and offsetting the arc rather than the camera is what keeps P
exactly where the spec's equations put it.

WHAT THE SPEC LEFT TO WORK OUT

A ring guided on its outer perimeter by 22 mm bearings puts the bearing
axes 11 mm outside its race, 129 mm out on this ring — not on the 95 mm
pitch circle the spec names, which does not reach a 240-odd ring from
either side. 129 is what the ring dictates, and it lands the three towers
on the corners of the 250 mm triangle, which is the strongest sign that
this is what was meant.

A 608 bearing has an 8 mm bore and the spec's axle is M4, so each bearing
rides a printed top-hat sleeve. The preload adjustment lives there: one
sleeve's bore is 1.0 mm off its axis, and turning it moves that bearing
2.0 mm radially — the spec's "2.0 mm radial travel" as an eccentric rather
than as a slotted hole, which cannot be tightened into an integral tower.

The arc's lower end (theta = 0) sits at the specimen's height, 73 mm
above the ring's mounting pad, and it sits OUTSIDE the ring: the arc's
inner radius is 140 and the ring's outer is 123. Anything that bridges
that gap from the ring's side pushes the ring's footprint past the plate,
so the bridge belongs to the arc instead. Its lower end continues straight
down as a leg and turns inward as a bar that keys into a slot in the
ring's pad and bolts down through it. The pad is as thick as the specimen
is tall, so the dial moves the ring and not the arc.

Every one of these is measured below, not assumed: the carriage is swept
through its whole elevation range against the arc and its leg, and the
rotor through a full turn against the base.

Usage: gen_orbital_jig.py [--specimen MM] [--out FILE.3mf]
"""
import argparse
import json
import os
import sys
import zipfile

import numpy as np
import trimesh
import trimesh.collision as tc
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))

# --- the numbers -------------------------------------------------------
R = 150.0               # working radius: entrance pupil to specimen
SPECIMEN = 12.0         # focal point above the platform (a small tooth's
                        # centroid); the one dial
SPECIMEN_RANGE = (6.0, 70.0)    # a 129 mm tooth's centroid is 52 up
ELEV = (10.0, 80.0)     # elevation range the carriage is asked for
PED_H = 95.0            # base top to platform top
PED_R = 11.0            # Ø22 column
PLAT_R = 10.0           # Ø20 platform
CONE_DEG = 15.0         # draft under the platform, from vertical
CONE_H = 23.0           # over which the draft runs; with the chamfer below
CHAM_H = 7.0            # it, the spec's "upper 30 mm"
BASE_SIDE = 250.0
BASE_T = 8.0
BASE_ROUND = 6.0
# The corners, turned 15 degrees: a 250 mm triangle with a side along an
# axis is 250 mm across the plate, and 241 both ways when turned.
TOWER_PHI = (75.0, 195.0, 315.0)
FOOT_PHI = (15.0, 135.0, 255.0)       # mid-edges: a three-point stance
FOOT_R, FOOT_D, FOOT_DEPTH = 60.0, 12.6, 1.0

# 242, not the spec's 246: this shop packs with a 5 mm plate margin and a
# 3 mm gap round every part, and 246 + 3 does not go into 246. The bore
# stays at 180 and the bearings follow the race outward.
RING_RO, RING_RI, RING_T = 121.0, 90.0, 18.0
RACE_R = RING_RO - 3.0  # groove floor the bearing rolls on
RACE_W = 7.4            # 7 mm bearing + 0.2 a side
RACE_FLANK = 3.0        # 45 degree flanks up to the OD: printable, and
                        # they bear on the bearing's edges for axial hold
BRG_R, BRG_W, BRG_BORE = 11.0, 7.0, 8.0
BRG_PITCH = RACE_R + BRG_R            # 131
RING_GAP = 8.0          # ring underside above the base top: pawl room
TOWER_R, BOSS_R, BOSS_H = 7.0, 5.5, 1.0
SLEEVE_R, SLEEVE_H, SLEEVE_FL_R, SLEEVE_FL_H = 3.95, 6.8, 5.75, 1.0
BOLT_R = 2.2            # M4 clearance, radius
ECC = 1.0               # eccentric sleeve offset: 2.0 mm of travel
INS_M4 = (2.65, 7.0)    # heat-set M4 x 6: bore radius, depth
INS_M3 = (2.0, 5.0)
HEAD_R, HEAD_H = 3.5, 4.0             # M4 socket head

DETENTS, DETENT_R, DETENT_MOUTH = 36, 95.0, 3.0   # 45 degree cones

Y_ARC = -60.0           # the arc's plane, off the meridian
ARC_RI, ARC_RO = 140.0, 170.0
ARC_HW = 10.0           # flange half-width (y)
WEB_HT = 4.0            # web half-thickness
FLANGE = 5.0
CHAM = 4.0              # 45 degree web roots, so the underside prints
SLOT_W = 5.2
SLOT_DEG = (4.0, 86.0)
LEG_BOTTOM = -73.0      # the arc's leg ends here, whatever the specimen
BAR_T, BAR_X0 = 20.0, 66.0            # the bar in to the ring; its inner end
                                      # stays over the annulus (r 96 at y -70)
BOLTS_X = (72.0, 86.0, 100.0)         # three M4s down through the bar
CBORE = (4.0, 8.0)      # counterbore radius and depth for their heads
FIDUCIALS = (15.0, 30.0, 45.0, 60.0, 75.0)
TICK_W, TICK_D = 1.2, 1.0

PAD_PHI, PAD_R, PAD_SLOT_D = (-58.0, -14.0), (92.0, 121.0), 4.0
BALLAST_PHI, BALLAST_R, BALLAST_D, BALLAST_DEPTH = 160.0, 107.0, 26.0, 6.0

# carriage, in the arc frame: u radial, v tangential (up-arc), h = y-Y_ARC
SADDLE_DEG = 7.5        # half-span of the shoes along the arc (40 mm)
NUB_CLR = 0.15          # nubs stand this off the flange edge; the clamp
                        # closes it
PLATE_H = (10.8, 25.8)  # saddle plate band in h (inboard)
SHOE_H = (-20.8, -10.8) # outboard shoe band
TONGUE = (147.0, 163.0, 6.2)          # r0, r1, depth stops at |h| = 6.2
NUB_R, NUB_POS = 2.0, ((142.5, -15.0), (142.5, 15.0),
                       (167.5, -15.0), (167.5, 15.0))
SCREW_R = 2.7           # M5 clearance
NUT = (8.4, 4.4)        # M5 square nut trap, across and thick
# The platform is longer than the spec's 40 mm channel wanted, because
# the cameras it has to carry are not one camera: a phone's lens plane
# is 4 mm behind the pupil and its clamp's foot lands at u = 232, while a
# Sony a1 behind a 90 mm macro has its tripod socket 320 mm out. The
# channel runs 208-318 so either sits with its pupil on the sphere, and
# the ballast moves to a pocket in the platform's underside, where a body
# of any length cannot be in its way. The receiver's top is at v = -45 so
# a full-frame body's axis, 45 mm above its base, lands on v = 0.
ARM_U, ARM_V = (178.0, 200.0), (-73.0, 20.0)
PLATFORM_U, PLATFORM_V = (195.0, 350.0), (-73.0, -57.0)
CAM_Y = 0.0
PLATFORM_HW = 49.2      # platform half-width about the camera's y
CHANNEL = (208.3, 318.0, 3.4, 12.0)   # fore/aft slots: u0, u1, width, ±y
CB_POCKET = (335.0, 13.0, 8.0)        # underside ballast pocket: u, r, depth
RECV = (40.0, 50.0, 12.0)             # receiver: u, y, v
RECV_U = 232.0          # where the generator poses it; a camera moves it
ARCA = (38.5, 4.0)      # dovetail mouth and depth, 45 degree flanks
QTR_R, QTR_CB = 3.3, (7.0, 4.0)       # 1/4"-20 clearance; D-ring head

# The cameras the sweeps are checked against, and the page draws. Boxes
# are (lo, hi) in the arc frame at theta = 0: x = u radial, y across the
# meridian, z = v up-arc; the pupil is at (150, 0, 0) for every one.
#
# A phone (an iPhone 15-class body, 147.6 x 71.6 x 7.8) held landscape in
# a spring clamp with its main lens at the pupil: the clamp grips the
# phone's long edges near its middle, 60 mm out along y from the lens,
# and an L-bridge brings its 1/4-20 foot back to the receiver's socket.
#
# A Sony a1 (128.9 x 96.9 x 80.8, axis 45 above the base) on an Arca
# plate, behind whichever lens: the body starts at the lens's length
# behind the pupil and the receiver slides out under its socket.
#
# Fields of view are horizontal. The spec wrote one frustum, 32 degrees
# at 3:2 -- a 63 mm-equivalent lens -- which frames 86 x 57 mm at 150 mm
# and cannot hold a 129 mm tooth. Each camera carries the lenses it has.
CAMERAS = {
    "iphone": dict(
        name="iPhone in a spring clamp", receiver_u=232.0,
        boxes=dict(phone=[((154.2, -14.0, -57.6), (162.0, 133.6, 14.0)),
                          ((150.0, -7.0, -25.0), (154.2, 27.0, 9.0))],
                   clamp=[((152.0, 40.0, -66.0), (172.0, 80.0, -57.6)),
                          ((152.0, 40.0, 14.0), (172.0, 80.0, 22.4)),
                          ((162.0, -15.0, -70.0), (172.0, 90.0, 26.0)),
                          ((172.0, -15.0, -45.0), (247.0, 15.0, -37.0))]),
        rings=[dict(c=(150.0, 0.0, 0.0), r=6.5),
               dict(c=(150.0, 0.0, -17.0), r=6.5),
               dict(c=(150.0, 17.0, -8.5), r=6.5)],
        lenses=[dict(id="wide", name="1\u00d7 main, 24 mm eq.",
                     fov_deg=71.5, aspect=4.0 / 3.0),
                dict(id="tele", name="2\u00d7 crop, 48 mm eq.",
                     fov_deg=39.8, aspect=4.0 / 3.0)],
        default_lens="wide"),
    "a1": dict(
        name="Sony \u03b11 on an Arca plate",
        body=dict(w=128.9, h=96.9, d=80.8, axis_h=45.0, socket_back=40.0,
                  evf=(20.0, 60.0, 40.0, 12.0)),
        plate=dict(u=70.0, y=38.0, t=4.0),
        lenses=[dict(id="fe90", name="FE 90 mm f/2.8 macro", fov_deg=22.6,
                     aspect=1.5, length=130.5, dia=79.0),
                dict(id="fe50", name="FE 50 mm f/2.8 macro", fov_deg=39.6,
                     aspect=1.5, length=71.0, dia=70.8),
                dict(id="spec", name="spec macro, 32\u00b0 (63 mm eq.)",
                     fov_deg=32.0, aspect=1.5, length=90.0, dia=72.0)],
        default_lens="fe90"),
}
CAMERA_DEFAULT = "iphone"
FRUSTUM = dict(near=20.0, far=200.0)


def a1_boxes(lens):
    """The a1 behind one lens: lens barrel as a box (the sweep asks for
    touching, and a box round a cylinder errs the safe way), body, EVF
    hump, Arca plate. Also where the receiver has to be."""
    b, pl = CAMERAS["a1"]["body"], CAMERAS["a1"]["plate"]
    u0 = R + 2.0 + lens["length"]                 # mount flange
    r_ = lens["dia"] / 2.0
    base = -b["axis_h"]
    socket = u0 + b["socket_back"]
    ev = b["evf"]
    boxes = dict(
        lens=[((R, -r_, -r_), (u0, r_, r_))],
        body=[((u0, -b["w"] / 2, base), (u0 + b["d"], b["w"] / 2, base + b["h"])),
              ((u0 + ev[0], -ev[2] / 2, base + b["h"] - 0.5),
               (u0 + ev[1], ev[2] / 2, base + b["h"] + ev[3]))],
        plate=[((socket - pl["u"] / 2, -pl["y"] / 2, base - pl["t"]),
                (socket + pl["u"] / 2, pl["y"] / 2, base))])
    return boxes, socket


def camera_config(kind, lens_id=None):
    """Boxes to draw and to sweep, and the receiver's position, for one
    camera behind one lens."""
    c = CAMERAS[kind]
    lens = next(l for l in c["lenses"]
                if l["id"] == (lens_id or c["default_lens"]))
    if kind == "a1":
        boxes, socket = a1_boxes(lens)
        return dict(boxes=boxes, receiver_u=socket, lens=lens)
    return dict(boxes=c["boxes"], receiver_u=c["receiver_u"], lens=lens)


PROTOCOL = [dict(ring=1, name="Horizon", elev=15.0, step=10.0),
            dict(ring=2, name="Mid-angle", elev=35.0, step=12.0),
            dict(ring=3, name="High-angle", elev=55.0, step=15.0),
            dict(ring=4, name="Zenith", elev=75.0, step=20.0)]
# The lens the frames are drawn with. The spec wrote a 32 degree, 3:2
# frustum -- a 68 mm-equivalent macro -- and at 150 mm that frames 86 x 57
# mm, which a 129 mm tooth overfills from every angle. The camera is a
# phone now, so the default is its main camera: 24 mm equivalent on a 4:3
# sensor, 84 degrees across the diagonal, 71.5 across the width, framing
# 216 x 162 mm at R. The 2x crop and the spec's macro stay selectable.
LENSES = [dict(id="wide", name="iPhone 1\u00d7 main (24 mm eq.)",
               fov_deg=71.5, aspect=4.0 / 3.0),
          dict(id="tele", name="iPhone 2\u00d7 crop (48 mm eq.)",
               fov_deg=39.8, aspect=4.0 / 3.0),
          dict(id="macro", name="spec macro, 32\u00b0 3:2",
               fov_deg=32.0, aspect=1.5)]
FRUSTUM = dict(near=20.0, far=200.0, **{k: LENSES[0][k]
                                         for k in ("fov_deg", "aspect")})

PETG_G_PER_CM3 = 1.27

# --- helpers -----------------------------------------------------------
def rot(deg, axis, origin=(0, 0, 0)):
    return trimesh.transformations.rotation_matrix(np.radians(deg), axis,
                                                   origin)


def box(lo, hi):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    b = trimesh.creation.box(hi - lo)
    b.apply_translation((lo + hi) / 2.0)
    return b


def cyl(r, z0, z1, x=0.0, y=0.0, sections=96):
    c = trimesh.creation.cylinder(radius=r, height=z1 - z0,
                                  sections=sections)
    c.apply_translation([x, y, (z0 + z1) / 2.0])
    return c


def cone(r, z0, z1, x=0.0, y=0.0, sections=64):
    """Base of radius r at z0, apex at z1 (z1 may be below z0)."""
    c = trimesh.creation.cone(radius=r, height=abs(z1 - z0),
                              sections=sections)
    if z1 < z0:
        c.apply_transform(rot(180.0, [1, 0, 0]))
    c.apply_translation([x, y, z0])
    return c


def rev(profile, deg0=0.0, deg1=360.0, sections=None):
    """A closed (r, z) profile revolved about Z from deg0 to deg1."""
    p = np.asarray(profile, float)
    if not np.allclose(p[0], p[-1]):
        p = np.vstack([p, p[:1]])
    span = deg1 - deg0
    if sections is None:
        sections = max(8, int(np.ceil(span / 0.5)))
    full = abs(span - 360.0) < 1e-9
    m = trimesh.creation.revolve(p, angle=None if full else np.radians(span),
                                 cap=not full, sections=sections)
    if not full:
        m.apply_transform(rot(deg0, [0, 0, 1]))
    return m


def sector(r0, r1, z0, z1, deg0, deg1, sections=None):
    return rev([(r0, z0), (r1, z0), (r1, z1), (r0, z1)], deg0, deg1,
               sections)


def union(parts):
    parts = [p for p in parts if p is not None]
    return parts[0] if len(parts) == 1 else trimesh.boolean.union(
        parts, engine="manifold")


def cut(a, tools):
    tools = [t for t in tools if t is not None]
    if not tools:
        return a
    return trimesh.boolean.difference([a, union(tools)], engine="manifold")


def polar(r, deg, z=0.0):
    a = np.radians(deg)
    return np.array([r * np.cos(a), r * np.sin(a), z])


# the arc frame (X = r cos th, Y = r sin th, Z = h) into the world:
# world x = X, world y = h + Y_ARC, world z = Y. A reflection; trimesh
# turns the faces round with it.
M_ARC = np.array([[1, 0, 0, 0], [0, 0, 1, Y_ARC], [0, 1, 0, 0],
                  [0, 0, 0, 1]], float)


def elev(theta_deg):
    """Carriage placement: rotation about the world y axis carrying
    (150, 0, 0) up to (150 cos th, 0, 150 sin th)."""
    return rot(-theta_deg, [0, 1, 0])


def levels(specimen=SPECIMEN):
    zb = -(PED_H + specimen)              # base top
    ring_top = zb + RING_GAP + RING_T
    # the pad's slot floor meets the arc's bar at LEG_BOTTOM, so the pad
    # is however thick that takes: the specimen's own height
    pad_t = LEG_BOTTOM + PAD_SLOT_D - ring_top
    return dict(base_top=zb, base_bot=zb - BASE_T, plat=-specimen,
                ring_bot=zb + RING_GAP, ring_top=ring_top,
                pad_top=ring_top + pad_t, pad_t=pad_t,
                brg_z=zb + RING_GAP + RING_T / 2.0)


# --- stator: plate, towers, pedestal -----------------------------------
def base_outline():
    rc = BASE_SIDE / np.sqrt(3.0)
    tri = Polygon([polar(rc, a)[:2] for a in TOWER_PHI])
    tri = tri.buffer(-BASE_ROUND).buffer(BASE_ROUND, quad_segs=32)
    lobes = [Point(*polar(BRG_PITCH, a)[:2]).buffer(TOWER_R + 6.0,
                                                    quad_segs=48)
             for a in TOWER_PHI]
    return unary_union([tri] + lobes)


def pedestal_profile():
    z_col = PED_H - CONE_H - CHAM_H
    r_waist = PLAT_R - CONE_H * np.tan(np.radians(CONE_DEG))
    return [(0.0, 0.0), (PED_R, 0.0), (PED_R, z_col),
            (r_waist, z_col + CHAM_H), (PLAT_R, PED_H), (0.0, PED_H)]


def stator(specimen=SPECIMEN):
    """Built with the base top at z = 0, then dropped to its level."""
    L = levels(specimen)
    plate = trimesh.creation.extrude_polygon(base_outline(), BASE_T)
    plate.apply_translation([0, 0, -BASE_T])
    parts = [plate]
    top = RING_GAP + RING_T / 2.0 - BRG_W / 2.0 - 0.2     # bearing bottom
    for a in TOWER_PHI:
        x, y, _ = polar(BRG_PITCH, a)
        parts.append(cyl(TOWER_R, -1.0, top - BOSS_H, x, y))
        parts.append(cyl(BOSS_R, top - BOSS_H - 0.5, top, x, y))
    ped = rev(pedestal_profile(), sections=120)
    parts.append(ped)
    s = union(parts)
    tools = []
    for a in TOWER_PHI:
        x, y, _ = polar(BRG_PITCH, a)
        tools.append(cyl(INS_M4[0], top - INS_M4[1], top + 1, x, y, 48))
        tools.append(cyl(BOLT_R, top - INS_M4[1] - 4.0, top, x, y, 48))
    for a in FOOT_PHI:
        x, y, _ = polar(FOOT_R, a)
        tools.append(cyl(FOOT_D / 2.0, -BASE_T - 1, -BASE_T + FOOT_DEPTH,
                         x, y))
    # the pawl's two M3 inserts, on the pawl's own centerline
    for r_ in pawl_screws():
        x, y, _ = polar(r_, PAWL_PHI)
        tools.append(cyl(INS_M3[0], -INS_M3[1], 1.0, x, y, 48))
    # a shallow dimple in the platform for a pea of museum putty
    tools.append(cyl(5.0, PED_H - 1.0, PED_H + 1, 0, 0, 64))
    s = cut(s, tools)
    s.apply_translation([0, 0, L["base_top"]])
    return s


# --- the detent pawl ---------------------------------------------------
PAWL_PHI = 130.0        # on a detent, so the nub sits in a dimple at home
PAWL_BLOCK = (108.0, 128.0, 14.0, 7.0)     # r0, r1, width, height
PAWL_LEAF = (92.0, 1.5)                    # reaches in to r, thickness
PAWL_NUB_R = 2.5


def pawl_screws():
    return (113.0, 123.0)


def pawl(specimen=SPECIMEN):
    r0, r1, w, h = PAWL_BLOCK
    blk = box((r0, -w / 2, 0), (r1, w / 2, h))
    leaf = box((PAWL_LEAF[0], -w / 2, h - PAWL_LEAF[1]), (r0 + 0.5, w / 2, h))
    nub = trimesh.creation.icosphere(subdivisions=3, radius=PAWL_NUB_R)
    nub.apply_translation([DETENT_R, 0, h])
    p = union([blk, leaf, nub])
    p = cut(p, [cyl(1.7, -1, h + 1, r_, 0, 32) for r_ in pawl_screws()])
    p.apply_transform(rot(PAWL_PHI, [0, 0, 1]))
    p.apply_translation([0, 0, levels(specimen)["base_top"]])
    return p


# --- bearing sleeves ---------------------------------------------------
def sleeve(ecc=0.0):
    """A top hat the 608 rides on: Ø7.9 through the 8 mm bore, a flange
    the bolt head clamps onto the inner race. `ecc` offsets the bolt bore
    for the preload sleeve; two notches on its flange say which it is."""
    s = union([cyl(SLEEVE_R, 0, SLEEVE_H, 0, 0, 96),
               cyl(SLEEVE_FL_R, SLEEVE_H, SLEEVE_H + SLEEVE_FL_H, 0, 0, 96)])
    tools = [cyl(BOLT_R, -1, SLEEVE_H + SLEEVE_FL_H + 1, ecc, 0, 48)]
    if ecc:
        for sgn in (1, -1):
            tools.append(box((-0.6, sgn * 4.2 - 1.0, SLEEVE_H + 0.4),
                             (0.6, sgn * 4.2 + 1.0 + 3, SLEEVE_H + 2)))
    return cut(s, tools)


def sleeves_in_place(specimen=SPECIMEN):
    L = levels(specimen)
    z0 = L["brg_z"] - BRG_W / 2.0 - 0.1
    out = {}
    for i, a in enumerate(TOWER_PHI):
        x, y, _ = polar(BRG_PITCH, a)
        s = sleeve(ECC if i == 2 else 0.0)
        # the eccentric sleeve is turned so its offset points at the ring
        s.apply_transform(rot(a + 180.0, [0, 0, 1]))
        s.apply_translation([x, y, z0])
        out["sleeve_ecc" if i == 2 else f"sleeve_{'ab'[i]}"] = s
    return out


# --- rotor ring with its boss ------------------------------------------
def ring_profile():
    t, f = RING_T, RACE_FLANK
    lo = (t - RACE_W) / 2.0 - f
    return [(RING_RI, 0), (RING_RO, 0), (RING_RO, lo), (RACE_R, lo + f),
            (RACE_R, lo + f + RACE_W), (RING_RO, lo + 2 * f + RACE_W),
            (RING_RO, t), (RING_RI, t)]


def rotor(specimen=SPECIMEN):
    L = levels(specimen)
    zb, zt, zp = L["ring_bot"], L["ring_top"], L["pad_top"]
    ring = rev(ring_profile(), sections=360)
    ring.apply_translation([0, 0, zb])
    pad = sector(PAD_R[0], PAD_R[1], zt - 0.5, zp, PAD_PHI[0], PAD_PHI[1])
    r_ = union([ring, pad])
    tools = []
    # 36 conical dimples under the inner flange, one every ten degrees
    for i in range(DETENTS):
        x, y, _ = polar(DETENT_R, i * 360.0 / DETENTS)
        tools.append(cone(DETENT_MOUTH + 0.5, zb - 0.5, zb + DETENT_MOUTH,
                          x, y, 48))
    # the slot the arc's bar keys into, and the inserts it bolts down to
    tools.append(box((BAR_X0 - 5.0, Y_ARC - ARC_HW - 0.2, zp - PAD_SLOT_D),
                     (RING_RO + 5.0, Y_ARC + ARC_HW + 0.2, zp + 1)))
    for x in BOLTS_X:
        tools.append(cyl(INS_M4[0], zp - PAD_SLOT_D - INS_M4[1],
                         zp - PAD_SLOT_D + 0.5, x, Y_ARC, 48))
        tools.append(cyl(BOLT_R, zp - PAD_SLOT_D - INS_M4[1] - 4.0,
                         zp - PAD_SLOT_D, x, Y_ARC, 48))
    # ballast socket opposite the load: a stack of washers on an M4
    bx, by, _ = polar(BALLAST_R, BALLAST_PHI)
    tools.append(cyl(BALLAST_D / 2.0, zt - BALLAST_DEPTH, zt + 1, bx, by))
    tools.append(cyl(INS_M4[0], zt - BALLAST_DEPTH - INS_M4[1],
                     zt - BALLAST_DEPTH + 0.5, bx, by, 48))
    return cut(r_, tools)


# --- quadrant arc ------------------------------------------------------
def arc_profile():
    ri, ro, hw, wt, f, c = ARC_RI, ARC_RO, ARC_HW, WEB_HT, FLANGE, CHAM
    return [(ri, -hw), (ri + f, -hw), (ri + f, -wt - c), (ri + f + c, -wt),
            (ro - f - c, -wt), (ro - f, -wt - c), (ro - f, -hw), (ro, -hw),
            (ro, hw), (ro - f, hw), (ro - f, wt + c), (ro - f - c, wt),
            (ri + f + c, wt), (ri + f, wt + c), (ri + f, hw), (ri, hw)]


def arc():
    """In the arc frame: the quadrant, the leg and bar down to the ring,
    the slot, the ticks, the bar's three counterbored bolt holes. Mapped
    into the world at the end. Independent of the specimen dial: the
    ring's pad absorbs that."""
    quad = rev(arc_profile(), 0.0, 90.0, sections=180)
    leg = box((ARC_RI, LEG_BOTTOM, -ARC_HW), (ARC_RO, 0.5, ARC_HW))
    bar = box((BAR_X0, LEG_BOTTOM, -ARC_HW), (ARC_RO, LEG_BOTTOM + BAR_T,
                                              ARC_HW))
    a = union([quad, leg, bar])
    tools = [sector(155.0 - SLOT_W / 2.0, 155.0 + SLOT_W / 2.0,
                    -ARC_HW - 1, ARC_HW + 1, SLOT_DEG[0], SLOT_DEG[1])]
    half = np.degrees(TICK_W / 2.0 / ARC_RO)
    for f in FIDUCIALS:
        tools.append(sector(ARC_RO - TICK_D, ARC_RO + 1, -ARC_HW - 1,
                            ARC_HW + 1, f - half, f + half, 4))
    # bolts run along the arc frame's Y (world z), down through the bar
    for x in BOLTS_X:
        for r_, y0, y1 in ((BOLT_R, LEG_BOTTOM - 1, LEG_BOTTOM + BAR_T + 1),
                           (CBORE[0], LEG_BOTTOM + BAR_T - CBORE[1],
                            LEG_BOTTOM + BAR_T + 1)):
            c = trimesh.creation.cylinder(radius=r_, height=y1 - y0,
                                          sections=48)
            c.apply_transform(rot(-90.0, [1, 0, 0]))
            c.apply_translation([x, (y0 + y1) / 2.0, 0.0])
            tools.append(c)
    a = cut(a, tools)
    a.apply_transform(M_ARC)
    return a


# --- carriage: saddle (inboard, carries the camera) and shoe -----------
def shoe_body(hband, sign):
    """Plate against the flange edges, tongue in the channel, nubs.
    `sign` is +1 inboard, -1 outboard. Built in the arc frame at th = 0,
    profile in (r, h) revolved over the saddle's span."""
    h0, h1 = sorted(hband)
    d = SADDLE_DEG
    plate = sector(ARC_RI - 2.0, ARC_RO + 7.0, h0, h1, -d, d)
    t0, t1, td = TONGUE
    tin = (sign * td, sign * (10.0 + NUB_CLR + 1.0))
    tongue = sector(t0, t1, min(tin), max(tin), -d + 0.5, d - 0.5)
    parts = [plate, tongue]
    for r_, v in NUB_POS:
        n = cyl(NUB_R, min(sign * (ARC_HW + NUB_CLR), sign * (ARC_HW + 1.5)),
                max(sign * (ARC_HW + NUB_CLR), sign * (ARC_HW + 1.5)),
                0, 0, 32)
        n.apply_translation([r_, 0, 0])
        n.apply_transform(rot(np.degrees(v / 155.0), [0, 0, 1]))
        parts.append(n)
    return union(parts)


def saddle():
    h0, h1 = PLATE_H
    s = shoe_body(PLATE_H, +1)
    # arm out past the lens, then the platform across under the camera
    arm = box((ARM_U[0], ARM_V[0], h0), (ARM_U[1], ARM_V[1], h1))
    wedge2 = Polygon([(ARC_RI - 2.0, -SADDLE_DEG * np.pi / 180 * 155.0 - 0.0),
                      (ARM_U[0] + 0.5, -SADDLE_DEG * np.pi / 180 * 155.0),
                      (ARM_U[0] + 0.5, ARM_V[0])])
    # the wedge is drawn in (u, v) and extruded across the plate's band,
    # so the plate's underside becomes a 45 degree slope down onto the arm
    wedge = trimesh.creation.extrude_polygon(wedge2, h1 - h0)
    wedge.apply_translation([0, 0, h0])
    hy = CAM_Y - Y_ARC                     # the camera's y, in h
    plat = box((PLATFORM_U[0], PLATFORM_V[0], h0),
               (PLATFORM_U[1], PLATFORM_V[1], hy + PLATFORM_HW))
    s = union([s, arm, wedge, plat])
    tools = [screw_hole(h0 - 6.0, h1 + 1.0)]
    # square nut trap, open toward down-arc so the nut slides in
    nw, nt = NUT
    tools.append(box((155.0 - nw / 2, -30.0, h0 + 3.2),
                     (155.0 + nw / 2, nw / 2, h0 + 3.2 + nt)))
    # fore/aft channel: two slots the receiver's screws ride in
    u0, u1, w, dy = CHANNEL
    for y in (hy - dy, hy + dy):
        # one stadium, not a box with two cylinders on its ends: those
        # are tangent along the box's sides, and 3MF precision folds
        # tangent faces into non-manifold edges on the way out
        stadium = LineString([(u0, y), (u1, y)]).buffer(w / 2, quad_segs=12)
        slot = trimesh.creation.extrude_polygon(
            stadium, PLATFORM_V[1] - PLATFORM_V[0] + 2)
        slot.apply_transform(np.array([[1, 0, 0, 0], [0, 0, 1, PLATFORM_V[0] - 1],
                                       [0, 1, 0, 0], [0, 0, 0, 1]], float))
        tools.append(slot)
    # ballast pocket up into the platform's underside, insert at its roof:
    # a stack of washers on an M4, hanging under the platform behind the
    # camera, which is where the counterweight wants to be anyway
    bu, br, bd = CB_POCKET
    for r_, v0, v1 in ((br, PLATFORM_V[0] - 1.0, PLATFORM_V[0] + bd),
                       (INS_M4[0], PLATFORM_V[0] + bd - 0.5,
                        PLATFORM_V[0] + bd + 6.5)):
        c = trimesh.creation.cylinder(radius=r_, height=v1 - v0, sections=64)
        c.apply_transform(rot(90.0, [1, 0, 0]))
        c.apply_translation([bu, (v0 + v1) / 2.0, hy])
        tools.append(c)
    s = cut(s, tools)
    s.apply_transform(M_ARC)
    return s


def screw_hole(h0, h1):
    c = cyl(SCREW_R, h0, h1, 0, 0, 48)
    c.apply_translation([155.0, 0, 0])
    return c


def shoe():
    s = shoe_body(SHOE_H, -1)
    s = cut(s, [screw_hole(SHOE_H[0] - 1.0, SHOE_H[1] + 7.0)])
    s.apply_transform(M_ARC)
    return s


def receiver():
    """Arca dovetail slot on top, a 1/4-20 D-ring through the middle, two
    M3 inserts underneath for the fore/aft channel."""
    lu, ly, lv = RECV
    hy = CAM_Y - Y_ARC
    v0 = PLATFORM_V[1]
    r_ = box((RECV_U - lu / 2, v0, hy - ly / 2), (RECV_U + lu / 2, v0 + lv,
                                                  hy + ly / 2))
    mouth, depth = ARCA
    dv = Polygon([(hy - mouth / 2, v0 + lv + 0.5), (hy + mouth / 2, v0 + lv + 0.5),
                  (hy + mouth / 2 + depth, v0 + lv - depth),
                  (hy - mouth / 2 - depth, v0 + lv - depth)])
    dove = trimesh.creation.extrude_polygon(dv, lu + 2)
    # profile in (y, v): map polygon x -> h, y -> v, extrusion -> u
    dove.apply_transform(np.array([[0, 0, 1, RECV_U - lu / 2 - 1],
                                   [0, 1, 0, 0], [1, 0, 0, 0],
                                   [0, 0, 0, 1]], float))
    tools = [dove]
    for r_h, v_lo, v_hi in ((QTR_R, v0 - 1, v0 + lv + 1),
                            (QTR_CB[0] / 2 + 0.3, v0 - 1, v0 + QTR_CB[1])):
        c = trimesh.creation.cylinder(radius=r_h, height=v_hi - v_lo,
                                      sections=48)
        c.apply_transform(rot(90.0, [1, 0, 0]))
        c.apply_translation([RECV_U, (v_lo + v_hi) / 2, hy])
        tools.append(c)
    for y in (hy - CHANNEL[3], hy + CHANNEL[3]):
        c = trimesh.creation.cylinder(radius=INS_M3[0], height=INS_M3[1] + 1,
                                      sections=48)
        c.apply_transform(rot(90.0, [1, 0, 0]))
        c.apply_translation([RECV_U, v0 - 1 + (INS_M3[1] + 1) / 2, y])
        tools.append(c)
    r_ = cut(r_, tools)
    r_.apply_transform(M_ARC)
    return r_


# --- proxies: hardware and the camera, for the sweeps and the page -----
def bearing_proxies(specimen=SPECIMEN):
    L = levels(specimen)
    out = []
    for a in TOWER_PHI:
        x, y, _ = polar(BRG_PITCH, a)
        out.append(cyl(BRG_R, L["brg_z"] - BRG_W / 2, L["brg_z"] + BRG_W / 2,
                       x, y, 120))
    return out


def camera_proxy(kind=CAMERA_DEFAULT, lens_id=None):
    """One camera behind one lens, in world coordinates at theta = 0.
    Concatenated, not unioned: the sweep only asks whether anything
    touches, and overlapping boxes answer that as well as a solid."""
    cfg = camera_config(kind, lens_id)
    return trimesh.util.concatenate(
        [box(lo, hi) for group in cfg["boxes"].values() for lo, hi in group])


def camera_cases():
    """Every camera behind every lens it has: what the sweeps run over."""
    return [(k, l["id"]) for k, c in CAMERAS.items() for l in c["lenses"]]


def receiver_for(parts, kind, lens_id=None):
    """The receiver slid along the channel to under this camera's socket."""
    m = parts["receiver"].copy()
    m.apply_translation([camera_config(kind, lens_id)["receiver_u"] - RECV_U,
                         0, 0])
    return m


# --- assembly and layout -----------------------------------------------
STATOR_SIDE = ("stator", "pawl", "sleeve_a", "sleeve_b", "sleeve_ecc")
ROTOR_SIDE = ("rotor", "arc")
CARRIAGE = ("saddle", "shoe", "receiver")


def assemble(specimen=SPECIMEN):
    """Every printed body, in the world frame, at home: phi = 0 and the
    carriage at theta = 0 (its build pose; the page and the sweeps turn
    it)."""
    parts = {"stator": stator(specimen), "pawl": pawl(specimen)}
    parts.update(sleeves_in_place(specimen))
    parts["rotor"] = rotor(specimen)
    parts["arc"] = arc()
    parts["saddle"] = saddle()
    parts["shoe"] = shoe()
    parts["receiver"] = receiver()
    return parts


def plate_pose(name, mesh):
    """World -> plate rotation for each body, chosen so it prints flat
    without support: the arc and the shoe lie on their outboard faces,
    the sleeves on their flanges, everything else as it stands."""
    if name == "arc":
        return rot(90.0, [1, 0, 0])
    if name == "shoe":
        return rot(90.0, [1, 0, 0])
    if name.startswith("sleeve"):
        return rot(180.0, [1, 0, 0])
    return np.eye(4)


def layout(parts, gap=6.0, pitch=300.0):
    """Three virtual plates side by side: the base, the ring, the rest.
    The shop's packer places each body itself; this arrangement only has
    to keep them from overlapping so it can tell them apart."""
    plates = [["stator"], ["rotor"],
              ["arc", "saddle", "shoe", "receiver", "pawl",
               "sleeve_a", "sleeve_b", "sleeve_ecc"]]
    out, poses = {}, {}
    for pi, names in enumerate(plates):
        x, y, row_h = pi * pitch, 0.0, 0.0
        for n in names:
            m = parts[n].copy()
            T = plate_pose(n, m)
            m.apply_transform(T)
            lo, hi = m.bounds
            ext = hi - lo
            if x + ext[0] > pi * pitch + 246.0 and x > pi * pitch:
                x, y, row_h = pi * pitch, y + row_h + gap, 0.0
            shift = np.array([x - lo[0], y - lo[1], -lo[2]])
            m.apply_translation(shift)
            S = np.eye(4)
            S[:3, 3] = shift
            poses[n] = np.linalg.inv(S @ T)     # plate -> world
            out[n] = m
            x += ext[0] + gap
            row_h = max(row_h, ext[1])
    return out, poses


def assembly_meta(specimen, poses, parts):
    L = levels(specimen)
    return {
        "design": "orbital_jig", "specimen": specimen, "R": R,
        "levels": L, "elev_range": list(ELEV),
        "y_arc": Y_ARC, "leg_bottom": LEG_BOTTOM,
        "stator_side": list(STATOR_SIDE), "rotor_side": list(ROTOR_SIDE),
        "carriage": list(CARRIAGE),
        "to_world": {n: [round(float(v), 6) for v in poses[n].ravel()]
                     for n in poses},
        "bearing": dict(r=BRG_R, w=BRG_W, bore=BRG_BORE, pitch_r=BRG_PITCH,
                        phi=list(TOWER_PHI), z=L["brg_z"],
                        head_r=HEAD_R, head_h=HEAD_H),
        "detent": dict(count=DETENTS, r=DETENT_R, pitch_deg=360.0 / DETENTS),
        "arc": dict(ri=ARC_RI, ro=ARC_RO, hw=ARC_HW, slot=SLOT_W,
                    slot_deg=list(SLOT_DEG), fiducials=list(FIDUCIALS)),
        "thumbscrew": dict(r=2.5, y0=Y_ARC + SHOE_H[0] - 6.0,
                           y1=Y_ARC + PLATE_H[0] + 7.0, knob_r=7.0,
                           knob_h=6.0, u=155.0),
        "cameras": {k: dict(c, configs={l["id"]: camera_config(k, l["id"])
                                        for l in c["lenses"]})
                    for k, c in CAMERAS.items()},
        "camera_default": CAMERA_DEFAULT, "pupil": [R, CAM_Y, 0.0],
        "ballast": dict(phi=BALLAST_PHI, r=BALLAST_R, d=BALLAST_D,
                        z_floor=L["ring_top"] - BALLAST_DEPTH),
        "cb_pocket": dict(u=CB_POCKET[0], r=CB_POCKET[1],
                          v_roof=PLATFORM_V[0] + CB_POCKET[2],
                          v_mouth=PLATFORM_V[0]),
        "receiver_u": RECV_U,
        "receiver": dict(u=RECV_U, v=PLATFORM_V[1], size=list(RECV)),
        "protocol": PROTOCOL, "frustum": FRUSTUM, "lenses": LENSES,
        "frames": sum(int(round(360.0 / p["step"])) for p in PROTOCOL),
        "volume_cm3": {n: round(float(m.volume) / 1000.0, 1)
                       for n, m in parts.items()},
    }


# --- measurement -------------------------------------------------------
def pedestal_hidden(st, specimen):
    """Below the platform, does the pedestal stay inside the shadow the
    platform casts along a 75 degree line of sight? The rule is r(d) <=
    10 - d tan 15 for every depth d in the drafted section: measured off
    the built mesh, not the profile it was built from."""
    zp = -specimen
    worst = -1e9
    for d in np.linspace(0.5, CONE_H - 0.5, 10):
        sec = st.section(plane_origin=[0, 0, zp - d], plane_normal=[0, 0, 1])
        if sec is None:
            return False, None
        pts = sec.vertices[:, :2]
        near = pts[np.linalg.norm(pts, axis=1) < 30.0]
        r_ = float(np.linalg.norm(near, axis=1).max())
        allow = PLAT_R - d * np.tan(np.radians(CONE_DEG))
        worst = max(worst, r_ - allow)
    return bool(worst <= 0.1), round(float(worst), 3)


def arc_radii(a):
    v = a.vertices
    above = v[v[:, 2] > 0.05]
    rr = np.hypot(above[:, 0], above[:, 2])
    return round(float(rr.min()), 3), round(float(rr.max()), 3)


def slot_width(a):
    """Probe across the web at 45 degrees; the first r not inside the
    mesh from each side is the slot's edge."""
    rs = np.arange(150.0, 160.01, 0.05)
    th = np.radians(45.0)
    pts = np.column_stack([rs * np.cos(th), np.full_like(rs, Y_ARC),
                           rs * np.sin(th)])
    inside = a.contains(pts)
    if inside.all() or not inside.any():
        return None
    gap = rs[~inside]
    return round(float(gap.max() - gap.min() + 0.05), 2)


def count_detents(r_, specimen):
    """Ray up into the underside at the detent radius: a dimple reads
    deeper than the flat between two dimples."""
    zb = levels(specimen)["ring_bot"]
    hits = 0
    for i in range(DETENTS * 2):
        a = i * 180.0 / DETENTS
        x, y, _ = polar(DETENT_R, a)
        loc, _, _ = r_.ray.intersects_location([[x, y, zb - 5.0]],
                                               [[0, 0, 1.0]],
                                               multiple_hits=False)
        if not len(loc):
            continue
        depth = float(loc[0][2] - zb)
        if (i % 2 == 0) and depth > 2.5:
            hits += 1
        if (i % 2 == 1) and depth > 0.1:
            return -1                         # something between detents
    return hits


def race_contact(rot_, specimen):
    """Each bearing touches the groove floor and nothing else. Pushed
    0.3 mm into the ring it must collide, or the check sees nothing."""
    cm = tc.CollisionManager()
    cm.add_object("ring", rot_)
    out = []
    for b, a in zip(bearing_proxies(specimen), TOWER_PHI):
        d = cm.min_distance_single(b)
        inward = polar(-0.3, a)
        b2 = b.copy()
        b2.apply_translation(inward)
        out.append(dict(gap=round(float(d), 3),
                        pressed_collides=bool(cm.in_collision_single(b2))))
    return out


def elevation_sweep(parts, step=2.5, cases=None):
    """The carriage and each camera through every elevation against the
    arc, its leg and the base. Returns (camera, lens, angle, pairs) for
    every pose that fouls."""
    fouled = []
    for kind, lens_id in (cases or camera_cases()):
        cm = tc.CollisionManager()
        for n in ("arc", "rotor", "stator"):
            cm.add_object(n, parts[n])
        movers = {n: parts[n] for n in CARRIAGE if n != "receiver"}
        movers["receiver"] = receiver_for(parts, kind, lens_id)
        movers["camera"] = camera_proxy(kind, lens_id)
        for n, m in movers.items():
            cm.add_object(n, m)
        for th in np.arange(ELEV[0], ELEV[1] + 1e-9, step):
            T = elev(th)
            for n in movers:
                cm.set_transform(n, T)
            hit, names = cm.in_collision_internal(return_names=True)
            # a pair with one mover in it. Two statics touching -- the
            # arc's bar seated on its slot floor -- is contact by design,
            # and FCL scores contact as collision; `bar_seats` measures it
            pairs = [p for p in names if len(set(p) & set(movers)) == 1]
            if pairs:
                fouled.append((kind, lens_id, float(th),
                               sorted("|".join(sorted(p)) for p in pairs)))
    return fouled


def bar_seats(parts):
    """The arc's bar in the ring's slot: no overlap at home, and a
    collision when the arc is pushed 0.3 mm down -- so the floor is there
    and the check can see it."""
    a, r_ = parts["arc"], parts["rotor"]
    overlap = float(a.intersection(r_, engine="manifold").volume)
    cm = tc.CollisionManager()
    cm.add_object("rotor", r_)
    down = a.copy()
    down.apply_translation([0, 0, -0.3])
    side = a.copy()
    side.apply_translation([0, 0.5, 0])
    return dict(overlap_mm3=round(overlap, 3),
                pressed_collides=bool(cm.in_collision_single(down)),
                shoved_collides=bool(cm.in_collision_single(side)))


def azimuth_sweep(parts, thetas=(ELEV[0], ELEV[1]), step=10.0):
    """The whole rotor side, carriage at its extremes, through a full
    turn against the stator side. The pawl is checked at detent angles,
    where its nub sits in a dimple; between them it is pressed flat and
    the model does not bend."""
    fouled = []
    for kind, lens_id in camera_cases():
        for th in thetas:
            cm = tc.CollisionManager()
            for n in STATOR_SIDE:
                cm.add_object(n, parts[n])
            movers = {n: parts[n] for n in ROTOR_SIDE}
            E = elev(th)
            for n in CARRIAGE:
                m = (receiver_for(parts, kind, lens_id) if n == "receiver"
                     else parts[n].copy())
                m.apply_transform(E)
                movers[n] = m
            cam = camera_proxy(kind, lens_id)
            cam.apply_transform(E)
            movers["camera"] = cam
            for n, m in movers.items():
                cm.add_object(n, m)
            for phi in np.arange(0.0, 360.0, step):
                T = rot(phi, [0, 0, 1])
                for n in movers:
                    cm.set_transform(n, T)
                hit, names = cm.in_collision_internal(return_names=True)
                pairs = [p for p in names if len(set(p) & set(movers)) == 1]
                if pairs:
                    fouled.append((kind, lens_id, float(th), float(phi),
                                   sorted("|".join(sorted(p)) for p in pairs)))
    return fouled


def pupil(theta):
    p = np.array([R, 0.0, CAM_Y - Y_ARC, 1.0])
    w = elev(theta) @ M_ARC @ p
    return w[:3]


def fits_plate(m, bed=246.0, height=250.0):
    e = m.extents
    return (e[2] <= height) and ((e[0] <= bed and e[1] <= bed))


def inserts():
    return {"M4": 3 + 3 + 1 + 1, "M3": 2 + 2,
            "M4x16": 3 + 3 + 2, "M3x10": 2 + 2, "608-2RS": 3,
            "M5x25 thumbscrew + square nut": 1, "1/4-20 D-ring": 1,
            "silicone feet": 3}


def measure(parts, specimen):
    rep = {"specimen_mm": specimen, "R": R}
    rep["watertight"] = {n: bool(m.is_watertight) for n, m in parts.items()}
    rep["dims_mm"] = {n: [round(float(x), 1) for x in m.extents]
                      for n, m in parts.items()}
    flat, _ = layout(parts)
    rep["fits_plate"] = {n: bool(fits_plate(m)) for n, m in flat.items()}
    hidden, worst = pedestal_hidden(parts["stator"], specimen)
    rep["pedestal_hidden_at_75"] = hidden
    rep["pedestal_worst_mm"] = worst
    rep["arc_radii"] = arc_radii(parts["arc"])
    rep["slot_mm"] = slot_width(parts["arc"])
    rep["detents"] = count_detents(parts["rotor"], specimen)
    rep["race"] = race_contact(parts["rotor"], specimen)
    rep["pupil_radius"] = [round(float(np.linalg.norm(pupil(t))), 3)
                           for t in (ELEV[0], 45.0, ELEV[1])]
    rep["pupil_y"] = [round(float(pupil(t)[1]), 3) for t in (ELEV[0], ELEV[1])]
    rep["bar_seats"] = bar_seats(parts)
    rep["cameras_swept"] = camera_cases()
    rep["elevation_fouls"] = elevation_sweep(parts)
    rep["azimuth_fouls"] = azimuth_sweep(parts)
    vol = sum(float(m.volume) for m in parts.values()) / 1000.0
    rep["volume_cm3"] = round(vol, 1)
    rep["est_g"] = round(vol * PETG_G_PER_CM3, 0)
    rep["hardware"] = inserts()
    rep["bearing_pitch_r"] = BRG_PITCH
    rep["preload_travel_mm"] = 2 * ECC
    return rep


def gates(rep):
    return [("watertight", all(rep["watertight"].values())),
            ("fits_plate", all(rep["fits_plate"].values())),
            ("pedestal_hidden_at_75", rep["pedestal_hidden_at_75"]),
            ("arc_concentric", ARC_RI - 0.05 <= rep["arc_radii"][0]
             and rep["arc_radii"][1] <= ARC_RO + 0.05),
            ("slot_5.2", rep["slot_mm"] is not None
             and abs(rep["slot_mm"] - SLOT_W) < 0.15),
            ("36_detents", rep["detents"] == DETENTS),
            ("bearings_on_race", all(r["gap"] < 0.05 and r["pressed_collides"]
                                     for r in rep["race"])),
            ("pupil_at_R", all(abs(p - R) < 0.01 for p in rep["pupil_radius"])
             and all(abs(y) < 0.01 for y in rep["pupil_y"])),
            ("bar_seats_in_slot", rep["bar_seats"]["overlap_mm3"] < 1.0
             and rep["bar_seats"]["pressed_collides"]
             and rep["bar_seats"]["shoved_collides"]),
            ("elevation_clear", not rep["elevation_fouls"]),
            ("azimuth_clear", not rep["azimuth_fouls"])]


# --- export ------------------------------------------------------------
def export(parts, specimen, out):
    flat, poses = layout(parts)
    sc = trimesh.Scene()
    for n, m in flat.items():
        sc.add_geometry(m, geom_name=n, node_name=n)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sc.export(out)
    from embed_settings import embed
    # no brim: three of these are 250 mm plates and the rest stand on
    # broad flat faces; a brim on the ring's underside would scar the
    # detent dimples
    embed(out, brim=False)
    meta = assembly_meta(specimen, poses, parts)
    with zipfile.ZipFile(out, "a", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Metadata/orbital_jig.json",
                   json.dumps(meta, separators=(",", ":")))
    from meshcheck import export_defects
    return export_defects(out), meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specimen", type=float, default=SPECIMEN,
                    help="focal point above the platform, mm")
    ap.add_argument("--out")
    ap.add_argument("--quick", action="store_true",
                    help="skip the sweeps (geometry only)")
    a = ap.parse_args()
    if not SPECIMEN_RANGE[0] <= a.specimen <= SPECIMEN_RANGE[1]:
        print(json.dumps({"ok": False, "error": "specimen height must be "
                          f"{SPECIMEN_RANGE[0]:g}-{SPECIMEN_RANGE[1]:g} mm"}))
        return 1
    parts = assemble(a.specimen)
    if a.quick:
        rep = {"watertight": {n: bool(m.is_watertight)
                              for n, m in parts.items()}}
        rep["ok"] = all(rep["watertight"].values())
        print(json.dumps(rep))
        return 0 if rep["ok"] else 1
    rep = measure(parts, a.specimen)
    failed = [n for n, ok in gates(rep) if not ok]
    ok = not failed
    if failed:
        rep["failed"] = failed
        rep["error"] = "gate failed: " + ", ".join(failed)
    if a.out and ok:
        bad, meta = export(parts, a.specimen, a.out)
        rep["defects"] = bad or None
        rep["frames"] = meta["frames"]
        ok = not bad
        rep["file"] = os.path.basename(a.out)
    rep["bodies"] = len(parts)
    print(json.dumps({"ok": ok, **rep}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
