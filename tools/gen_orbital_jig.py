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
axes 11 mm outside its race, 130.6 mm out on this ring — not on the 95 mm
pitch circle the spec names, which does not reach a 240-odd ring from
either side. That is what the ring dictates, and it lands the three
towers on the corners of the 250 mm triangle, which is the strongest sign
that this is what was meant.

A 608 bearing has an 8 mm bore and the spec's axle is M4, so each bearing
rides a printed top-hat sleeve, and every sleeve is eccentric: its bore
is 1.0 mm off its outside, so turning it about its axle moves its bearing
2.0 mm radially. All three, not one, because that is what lets the ring
go in at all -- see RACE_FLANK.

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
import genapi
import argparse
import json
import os
import sys
import zipfile

import numpy as np
import trimesh
import trimesh.collision as tc
from shapely.geometry import LineString, Point, Polygon
from shapely import affinity
from shapely.ops import unary_union
from thread import Thread

HERE = os.path.dirname(os.path.abspath(__file__))

# --- the numbers -------------------------------------------------------
R = 150.0               # working radius: entrance pupil to specimen
SPECIMEN = 78.0         # focal point above the platform; the one dial.
                        # 78 is the scanned Meherrin on the mount: 8 mm
                        # of plate, 13 of rod standing proud, and the
                        # tooth's own centroid 57 above its base.
# 70 was enough when the tooth stood on the platform. It does not reach
# any more: the rod field plate is 8 mm and the rods stand 15.5 to 29.5
# proud of it, so a tooth's centroid starts 23.5 to 37.5 mm up before the
# tooth itself is counted. BigMeherrin's centroid is 57 above its base,
# which lands at 80.5 on the short rods and 94.5 on the long ones -- both
# past the old stop, so the specimen this jig was built for could not
# have been brought to the focal point. 110 clears it; every gate holds
# there, and the dial is still absorbed the same way, by the pad.
# The floor is the mount, not a preference: the plate is 8 mm and a
# 20 mm rod stands 13 proud, so nothing can sit lower than 21 mm above
# the platform, and 25 leaves the pad 7 mm at that end.
SPECIMEN_RANGE = (25.0, 110.0)
ELEV = (10.0, 80.0)     # elevation range the carriage is asked for
# The pedestal was 95 mm and nothing asked for it. The height is not
# optical: the phone at the lowest ring clears the base by 113 mm, with
# the jig at a third of its original pedestal. (This read 83 mm against
# a full-frame body behind a 90 mm macro, which was the worst case while
# that camera was carried; it is not carried now.) What ties PED_H down
# is the arc's leg, through the pad that bridges them:
#
#     pad_t = LEG_BOTTOM + PAD_SLOT_D + PED_H + specimen - RING_GAP - RING_T
#
# so the pedestal and the leg trade one for one. Lower PED_H alone and
# the pad thins to nothing at 83; lower both together and every gate
# holds to a 50 mm drop. 45 is taken rather than 50 because at 54 the
# arc_concentric gate stops measuring the arc -- `arc_radii` counts every
# vertex above z = 0.05, so once the leg rises past zero the leg is
# counted too and r_min reads 66 instead of 140. Nothing collides there;
# the instrument just goes blind, and the design should not sit 4 mm from
# where its own gate stops seeing.
#
# The arc is what this buys: 243 mm tall was 7 mm under the build height.
# 32, not 50. The mount lifts the specimen before the specimen starts,
# and the rotor's pad takes up whatever is left over:
#
#     pad_t = PED_H + specimen - 50
#
# so the pedestal and the pad trade directly. With 20 mm rods the dial
# can never ask for less than 25, which leaves 7 mm of pad at the floor
# of its range, and 60 at the big tooth -- against 98 before. The camera
# still clears the base by 111.6 mm at the lowest ring, so none of this
# height was optical. 32 rather than 30 keeps a 2 mm column above the
# draft, which needs CONE_H + CHAM_H = 30 to itself.
PED_H = 32.0            # base top to platform top
PED_R = 11.0            # Ø22 column
PLAT_R = 15.0           # Ø30 platform: the mount bore needs the material,
                        # and the draft recuts itself off PLAT_R below
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
# The three feet are bolts now, down into a sole plate glued to a heavy
# board. They stay at r = 60 because that is inside the ring's bore: a
# driver reaches every head from above with the jig assembled, so the
# board needs no holes and nothing is done from underneath.
FOOT_R = 60.0
FOOT_CBORE = (3.9, 5.0)               # M4 socket head: radius, depth
# The sole plate: an annulus under the feet, with a raised pad at each so
# the base touches it at three points and nothing else -- a full face
# would screw any warp in the glued plate into the base, and from there
# into the race. Open in the middle for the mount screw's captive head.
SOLE_R = (42.0, 76.0)
SOLE_T = 5.0
SOLE_PAD = (9.0, 3.0)                 # pad radius and height above the plate

# 242, not the spec's 246: this shop packs with a 5 mm plate margin and a
# 3 mm gap round every part, and 246 + 3 does not go into 246. The bore
# stays at 180 and the bearings follow the race outward.
RING_RO, RING_RI, RING_T = 121.0, 90.0, 18.0
# The flanks were 3 mm, and the assembly sweep found the ring could not
# be fitted: three bearings, each overlapping the ring's lips by 3 mm, and
# only one of them able to stand back -- by 2. So the flanks come down to
# what holds the bearing's edge, and every sleeve is an eccentric. Turned
# outward, each bearing stands 0.4 mm clear of the ring's lip, the shop's
# face gap, and the ring drops straight in; turned in, they close on the
# race with 0.2 mm of preload still in hand.
RACE_FLANK = 1.4        # 45 degree flanks up to the OD: printable, and
                        # they bear on the bearing's edges for axial hold
RACE_R = RING_RO - RACE_FLANK         # groove floor the bearing rolls on
RACE_W = 7.4            # 7 mm bearing + 0.2 a side
BRG_R, BRG_W, BRG_BORE = 11.0, 7.0, 8.0
BRG_PITCH = RACE_R + BRG_R            # 130.6: a bearing on the race
PRELOAD = 0.2           # how much further in an eccentric can still go
RING_GAP = 8.0          # ring underside above the base top: the tip of
                        # the driver's pin swings through here
TOWER_R, BOSS_R, BOSS_H = 7.0, 5.5, 1.0
SLEEVE_R, SLEEVE_H, SLEEVE_FL_R, SLEEVE_FL_H = 3.95, 6.8, 5.75, 1.0
BOLT_R = 2.2            # M4 clearance, radius
ECC = 1.0               # eccentric sleeve offset: 2.0 mm of travel
# The towers stand where an eccentric turned fully in would push its
# bearing PRELOAD past the race; turned fully out it stands back ECC.
TOWER_PITCH = BRG_PITCH + ECC - PRELOAD   # 131.4
LOBE_REACH = 142.0      # how far the base's corner lobes reach
INS_M4 = (2.65, 7.0)    # heat-set M4 x 6: bore radius, depth
INS_M3 = (2.0, 5.0)
HEAD_R, HEAD_H = 3.5, 4.0             # M4 socket head

# --- the Geneva drive: how the ring is turned, stopped and held --------
# A driver turns continuously; once per turn its pin enters a slot in a
# lip on the ring's bore, carries the ring one slot round, and leaves.
# For the rest of the turn a lock on the driver sits in a seat cut into
# the lip, and the ring cannot move either way, powered or not. So one
# turn of the driver is one frame, the stop is set by the geometry and
# not by whoever turns it, and the ring starts and ends each step at
# rest. It replaces the 36 detent dimples and the leaf pawl, which held
# the ring lightly and had their own idea of where it should stop --
# a second decider beside any motor.
#
# The lip is on the ring's bore, flush with its underside, so the ring
# still prints as it stands. The driver is INSIDE the bore at r = 73:
# its knob is reached from above with everything assembled, and nothing
# hangs under the base, which is bolted down to a sole plate. 73 is the
# largest radius whose knob still passes inside the arc's bar, whose
# inner corner sweeps r = 82.8 three millimetres above the ring at the
# bottom of the dial.
#
# Internal, not external: the pin works from inside the slot circle, so
# the slots open toward the axis and the lip stays joined to the ring's
# wall. The pin drives for 190 degrees of each driver turn and the lock
# holds for 170.
GENEVA_N = 36                         # one slot per 10 degree stop
GENEVA_C = 73.0                       # driver axis from the rotor axis
GENEVA_PHI = 75.0                     # where the driver stands
GENEVA_A = GENEVA_C * np.sin(np.pi / GENEVA_N)    # crank: 6.36
GENEVA_MOUTH = GENEVA_C * np.cos(np.pi / GENEVA_N)  # 72.72: the pin enters
                                      # a slot moving along it, not across it
LIP_T = 5.0
PIN_R = 1.5                           # Ø3 steel dowel, pressed into the crank
PIN_HOLE_D = 2 * PIN_R + 0.10         # the shop's press: drawn hole - pin
SLOT_CLR = 0.2                        # each side of the pin
LOCK_R = 3.0                          # the lock: what is left of a Ø6 disc
LOCK_CLR = 0.2                        # in its seat, running: it turns
                                      # 170 degrees there every frame
# The lock is cut by the lip itself: everything the lip sweeps through
# while the pin drives, taken in the driver's frame and grown by this.
LOCK_RELIEF = 0.2
CRANK_R = GENEVA_A + PIN_R + 1.6      # the crank disc, above the lip
CRANK_T = 3.0
LIP_GAP = 0.6                         # crank underside above the lip
DRV_JOURNAL_R, DRV_CLR = 3.0, 0.2     # the driver's stub in the base
DRV_BOSS = (4.5, 3.5)                 # bushing boss on the base: r, height
# The stub stands on the floor of a blind bushing. No collar: the driver
# goes in from above after the ring, so everything under the crank has
# to pass down through a lock seat, and a seat is Ø6.3.
DRV_FLOOR = 1.5
KNOB_R, KNOB_H = 8.5, 11.4            # stands 2 mm above the ring's top
HEX_AF, HEX_CLR, HEX_D = 6.5, 0.15, 2.5           # knob onto the crank

Y_ARC = -60.0           # the arc's plane, off the meridian
ARC_RI, ARC_RO = 140.0, 170.0
ARC_HW = 10.0           # flange half-width (y)
WEB_HT = 4.0            # web half-thickness
FLANGE = 5.0
CHAM = 4.0              # 45 degree web roots, so the underside prints
SLOT_W = 5.4            # an M5 slides along it: the shop's running fit
SLOT_DEG = (4.0, 86.0)
LEG_BOTTOM = -28.0      # the arc's leg ends here, whatever the specimen;
                        # moves with PED_H, one for one -- see PED_H above
BAR_T, BAR_X0 = 20.0, 66.0            # the bar in to the ring; its inner end
                                      # stays over the annulus (r 96 at y -70)
BOLTS_X = (72.0, 86.0, 100.0)         # three M4s down through the bar
CBORE = (4.0, 8.0)      # counterbore radius and depth for their heads
FIDUCIALS = (15.0, 30.0, 45.0, 60.0, 75.0)
TICK_W, TICK_D = 1.2, 1.0

PAD_PHI, PAD_R, PAD_SLOT_D = (-58.0, -14.0), (92.0, 121.0), 4.0

# There were two ballasts, both sized against a 1.34 kg Sony a1. Measured
# against 0.25 kg of phone and clamp, neither survives:
#
# The CARRIAGE pocket balanced the camera about the thumbscrew. With the
# a1 the carriage's centre of mass sat 116 mm past the clamp -- 1.76 N.m,
# which the 16 mm tongue took as a 110 N couple. With the phone, and the
# platform no longer stretched to reach an a1's tripod socket, it is
# 26.5 mm and 0.102 N.m: 6.3 N on the tongue. An M5 through two PETG
# faces does not need help with that.
#
# The ROTOR socket was never the counterweight it was called. The arc and
# everything on it put the rotor side's centre of mass 114 mm off the
# axis at the lowest ring -- 82 g.m of imbalance -- and a Ø26 x 6 pocket
# holds about 25 g of washers, 2.7 g.m, three percent of it. Balancing it
# honestly would take 770 g of steel, a pocket 183 mm deep. So the rotor
# does lift off one of its three bearings, by 1.6 N at the lowest ring,
# and what holds it is the race flanks -- which are already drawn for
# axial hold. A pocket that offsets three percent only reads as though
# the problem were solved.

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
# The platform ran to u = 350 and the channel 208-318 -- 110 mm of travel
# -- because it had to seat two cameras whose sockets are 90 mm apart: a
# phone's clamp foot at u = 232, and a Sony a1 behind a 90 mm macro with
# its tripod socket at 320. There is one camera now, and its foot is at
# 232 for both of its lenses: the phone's three lens rings differ in y
# and v, not in u, so changing lens does not move the receiver at all.
#
# So the travel is no longer a fit problem, only an adjustment: 40 mm,
# 215-255, which is 20 either side of where the clamp actually lands.
# The receiver is 40 long, so at the ends of its travel it reaches
# u = 195 and 275, and that is the platform.
#
# The receiver's top stays at v = -45. That number came from the a1's
# axis height, but the phone's L-bridge was drawn to meet it and the
# bridge is the part we do not control; moving the deck would move the
# pupil off the sphere for the sake of a few millimetres.
ARM_U, ARM_V = (178.0, 200.0), (-73.0, 20.0)
PLATFORM_U, PLATFORM_V = (195.0, 275.0), (-73.0, -57.0)
CAM_Y = 0.0
PLATFORM_HW = 49.2      # platform half-width about the camera's y
CHANNEL = (215.0, 255.0, 3.4, 12.0)   # fore/aft slots: u0, u1, width, ±y
RECV = (40.0, 50.0, 12.0)             # receiver: u, y, v
RECV_U = 232.0          # where the generator poses it; a camera moves it
RECV_RELIEF = 4.0       # past the M3 inserts, for the screw's tip
ARCA = (38.5, 4.0)      # dovetail mouth and depth, 45 degree flanks
QTR_R, QTR_CB = 3.4, (7.0, 4.0)       # 1/4"-20 clearance; D-ring head

# --- the specimen mount: a printed screw and wing nut -------------------
# The rod field plate is the specimen mount, so the only thing the jig
# owes it is a way to clamp it down. Nothing is bought: the thread is the
# Montessori cosine family in thread.py, the same one the Knot and the
# Tinker set print in PETG, taken down to Ø8.
#
# Ø8 and not the Tinker's Ø24, for two measured reasons. A nut on top of
# the plate sits where the specimen does, so its footprint is the cost:
# at Ø8 the wing nut covers none of the field's 56 sockets, at Ø12 it
# covers 8, at Ø24 it covers 44. And the bore has to pass the pedestal's
# waist, where Ø8 leaves 4.58 mm of wall against 3.58 at Ø10.
#
# It cannot occlude the tooth either way: the Ø1 carbon rods are cut
# about 40 mm and seat 7 mm, so they stand the specimen 33 mm above the
# plate, and the Ø8 wing nut is 8.0 tall.
# Ø6, the smallest this family holds up at. Its clearance is absolute --
# 0.30 mm radial at every size -- so it eats a growing share of the
# thread as the thread shrinks: 92% of the depth still engages at Ø24,
# 85% at Ø12, 77% at Ø8 and 70% at Ø6. Below that it is more clearance
# than thread. Ø6 also leaves 5.34 mm of wall where the bore crosses the
# pedestal's waist, against 4.34 at Ø8.
MOUNT_D = 6.0                         # thread major diameter
MOUNT_CLEAR = 0.50                    # plain bore, radial; as the Knot proved
MOUNT_BORE_R = MOUNT_D / 2.0 + MOUNT_CLEAR
MOUNT_AF = 2.844 * (MOUNT_D / 2.0)    # head across flats, the family's ratio
MOUNT_HEAD_CR = MOUNT_AF / np.sqrt(3.0) + 0.3     # pocket, with a little slack
# The family's own head is 1.617 R tall -- 6.47 mm here -- which will not
# sink into an 8 mm base and still leave anything above it to carry the
# clamp. The head is cut to 4.0 instead: it is only resisting rotation in
# its pocket, it is never wrenched, and at 4.0 it recesses flush with
# 3.6 mm of base left over it.
MOUNT_HEAD_H = 4.0
MOUNT_POCKET = MOUNT_HEAD_H + 0.4     # how far the head sinks into the base
# Proportions, not millimetres: the fins were drawn for Ø8 and have to
# follow the thread if the thread changes.
MOUNT_WING_SPAN = 2.675               # fin half-span, in major radii
MOUNT_WING_T = 0.60                   # fin thickness, likewise
PLATE_T = 8.0                         # the rod field plate it clamps down

# The cameras the sweeps are checked against, and the page draws. Boxes
# are (lo, hi) in the arc frame at theta = 0: x = u radial, y across the
# meridian, z = v up-arc; the pupil is at (150, 0, 0) for every one.
#
# A phone (147.6 x 71.6 x 7.8) held landscape in a spring clamp with its
# main lens at the pupil: the clamp grips the phone's long edges near its
# middle, 60 mm out along y from the lens, and an L-bridge brings its
# 1/4-20 foot back to the receiver's socket.
#
# This is the only camera. A Sony a1 on an Arca plate was carried here
# too, and it was what the carriage was sized for -- a 1.34 kg body and
# macro whose tripod socket sits 320 mm out, against 0.25 kg of phone and
# clamp at 166. It drove the platform's length, the ballast at both ends,
# and the clearance reasoning. None of that is wanted for a phone, so it
# is gone rather than left as an option nobody takes.
#
# Fields of view are horizontal. The spec wrote one frustum, 32 degrees
# at 3:2 -- a 63 mm-equivalent lens -- which frames 86 x 57 mm at 150 mm
# and cannot hold a 129 mm tooth.
CAMERAS = {
    "iphone": dict(
        name="iPhone in a spring clamp", receiver_u=232.0,
        # phone and clamp together. It is here rather than in a test
        # because it is what decides whether the carriage needs ballast,
        # and `carriage_moment` below turns that into something the
        # suite can fail on.
        mass_g=250.0,
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
}
CAMERA_DEFAULT = "iphone"
FRUSTUM = dict(near=20.0, far=200.0)


def camera_config(kind, lens_id=None):
    """Boxes to draw and to sweep, and the receiver's position, for one
    camera behind one lens."""
    c = CAMERAS[kind]
    lens = next(l for l in c["lenses"]
                if l["id"] == (lens_id or c["default_lens"]))
    return dict(boxes=c["boxes"], receiver_u=c["receiver_u"], lens=lens)


# Every step a whole number of the Geneva's 10 degrees, because those are
# the only places the ring can stop. The spec's 12 and 15 landed between
# stops; 10 and 20 keep the 108 frames, denser at 35 and coarser at 55,
# where 20 degrees spans what 11.5 does on the horizon.
PROTOCOL = [dict(ring=1, name="Horizon", elev=15.0, step=10.0),
            dict(ring=2, name="Mid-angle", elev=35.0, step=10.0),
            dict(ring=3, name="High-angle", elev=55.0, step=20.0),
            dict(ring=4, name="Zenith", elev=75.0, step=20.0)]
# The lens the frames are drawn with. The spec wrote a 32 degree, 3:2
# frustum -- a 68 mm-equivalent macro -- and at 150 mm that frames 86 x 57
# mm, which a 129 mm tooth overfills from every angle. The camera is a
# phone now, so the default is its main camera: 24 mm equivalent on a 4:3
# sensor, 84 degrees across the diagonal, 71.5 across the width, framing
# 216 x 162 mm at R. The spec's own macro used to stay selectable beside
# them; it is gone with the body that could have carried it, because a
# frustum no camera on this jig can produce is not a choice, it is a
# drawing of somebody else's camera.
LENSES = [dict(id="wide", name="iPhone 1\u00d7 main (24 mm eq.)",
               fov_deg=71.5, aspect=4.0 / 3.0),
          dict(id="tele", name="iPhone 2\u00d7 crop (48 mm eq.)",
               fov_deg=39.8, aspect=4.0 / 3.0)]
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
    # the lobes reach where they did before the towers moved out 2.4 mm
    # for the eccentrics: 142 from the axis, inside the packer's plate
    lobes = [Point(*polar(TOWER_PITCH, a)[:2]).buffer(LOBE_REACH - TOWER_PITCH,
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
        x, y, _ = polar(TOWER_PITCH, a)
        parts.append(cyl(TOWER_R, -1.0, top - BOSS_H, x, y))
        parts.append(cyl(BOSS_R, top - BOSS_H - 0.5, top, x, y))
    ped = rev(pedestal_profile(), sections=120)
    parts.append(ped)
    dx, dy, _ = polar(GENEVA_C, GENEVA_PHI)
    parts.append(cyl(DRV_BOSS[0], -1.0, DRV_BOSS[1], dx, dy, 64))
    s = union(parts)
    tools = []
    for a in TOWER_PHI:
        x, y, _ = polar(TOWER_PITCH, a)
        tools.append(cyl(INS_M4[0], top - INS_M4[1], top + 1, x, y, 48))
        tools.append(cyl(BOLT_R, top - INS_M4[1] - 4.0, top, x, y, 48))
    # the three foot bolts, headed from above, down into the sole plate
    for a in FOOT_PHI:
        x, y, _ = polar(FOOT_R, a)
        tools.append(cyl(BOLT_R, -BASE_T - 1, 1.0, x, y, 48))
        tools.append(cyl(FOOT_CBORE[0], -FOOT_CBORE[1], 1.0, x, y, 48))
    # the Geneva driver's bushing: through the base and its boss
    dx, dy, _ = polar(GENEVA_C, GENEVA_PHI)
    tools.append(cyl(DRV_JOURNAL_R + DRV_CLR, -BASE_T + DRV_FLOOR,
                     DRV_BOSS[1] + 1, dx, dy, 64))
    # The specimen mount: a plain bore straight through the pedestal and
    # the base, for the printed screw that clamps the rod field plate on
    # top. Neither the platform nor the plate is threaded -- the thread
    # lives only on the screw and the wing nut, which are the two parts
    # that can be printed standing up and replaced on their own.
    tools.append(cyl(MOUNT_BORE_R, -BASE_T - 1.0, PED_H + 1.0, 0, 0, 48))
    # and a HEX pocket in the base's underside. Hexagonal rather than
    # round because it is what keeps the screw still: the head cannot
    # turn in it, so the wing nut tightens against a captive screw and
    # nothing has to be held from underneath. Under the base it is hidden
    # from every camera on the sphere.
    tools.append(cyl(MOUNT_HEAD_CR, -BASE_T - 1.0, -BASE_T + MOUNT_POCKET,
                     0, 0, 6))
    s = cut(s, tools)
    s.apply_translation([0, 0, L["base_top"]])
    return s


# --- the Geneva drive ----------------------------------------------------
def geneva_wheel(psi):
    """The ring's angle in degrees for the driver at `psi` degrees.

    psi = 180 is home: the pin pointing at the rotor axis and the lock in
    a seat. Each turn of the driver from there moves the ring one slot,
    the same way round. Between 265 and 455 the pin is in a slot and the
    ring follows it; outside that the ring stands still, locked."""
    step = 360.0 / GENEVA_N
    k, f = divmod(psi - 180.0, 360.0)
    f += 180.0
    half = 90.0 + 180.0 / GENEVA_N        # 95: half the pin's arc in a slot
    if f < 360.0 - half:
        w = 0.0
    elif f > 360.0 + half:
        w = step
    else:
        p = np.radians(f)
        w = step / 2.0 + np.degrees(np.arctan2(
            GENEVA_A * np.sin(p), GENEVA_C + GENEVA_A * np.cos(p)))
    return k * step + w


def geneva_lip_2d():
    """The lip in plan at home: an annulus from the slots' mouth out into
    the ring's wall, less 36 slots and the 36 lock seats between them."""
    step = 360.0 / GENEVA_N
    hw = PIN_R + SLOT_CLR
    ann = Point(0, 0).buffer(RING_RI + 0.5, quad_segs=256).difference(
        Point(0, 0).buffer(GENEVA_MOUTH, quad_segs=256))
    end = GENEVA_C + GENEVA_A
    slot = unary_union([
        Polygon([(GENEVA_MOUTH - 3.0, -hw), (end, -hw), (end, hw),
                 (GENEVA_MOUTH - 3.0, hw)]),
        Point(end, 0).buffer(hw, quad_segs=32)])
    cuts = []
    for k in range(GENEVA_N):
        a = GENEVA_PHI + k * step
        cuts.append(affinity.rotate(slot, a + step / 2.0, origin=(0, 0)))
        x, y, _ = polar(GENEVA_C, a)
        cuts.append(Point(x, y).buffer(LOCK_R + LOCK_CLR, quad_segs=64))
    return ann.difference(unary_union(cuts))


def geneva_lock_2d():
    """The lock in plan at home: a Ø6 disc on the driver's axis, less
    everything the lip passes through while the pin is driving it, taken
    in the driver's own frame. Cut by the lip rather than drawn, so it
    follows any change to the slots or the seats."""
    dx, dy, _ = polar(GENEVA_C, GENEVA_PHI)
    near = geneva_lip_2d().intersection(Point(dx, dy).buffer(LOCK_R + 16.0))
    swept = []
    for psi in np.arange(265.0, 455.01, 0.5):
        g = affinity.rotate(near, geneva_wheel(psi), origin=(0, 0))
        swept.append(affinity.rotate(g, -(psi - 180.0), origin=(dx, dy)))
    keep = Point(dx, dy).buffer(LOCK_R, quad_segs=64).difference(
        unary_union(swept).buffer(LOCK_RELIEF, quad_segs=32))
    # the slivers a buffered union leaves at its seams
    return keep.buffer(-0.05, quad_segs=32).buffer(0.05, quad_segs=32)


def _driver_frame():
    """Origin on the driver's axis; u out from the rotor axis, t across."""
    u = polar(1.0, GENEVA_PHI)
    t = polar(1.0, GENEVA_PHI + 90.0)
    return polar(GENEVA_C, GENEVA_PHI), u, t


def driver_levels(specimen=SPECIMEN):
    L = levels(specimen)
    c0 = L["ring_bot"] + LIP_T + LIP_GAP              # crank underside
    return dict(lock_lo=L["ring_bot"] - 0.3, crank_lo=c0,
                crank_hi=c0 + CRANK_T, knob_hi=c0 + CRANK_T + KNOB_H,
                pin_lo=L["ring_bot"] - 1.4,
                stub_lo=L["base_bot"] + DRV_FLOOR)


def driver(specimen=SPECIMEN):
    """Crank, lock and stub in one piece, at home.

    The stub stands in a blind bushing in the base, so the driver drops
    in from above -- the lock and stub pass down through a seat in the
    lip -- and is held by nothing it can work loose from. Printed
    crank-down: the lock rises off the crank's face, and the stub's full
    round only starts above a 45 degree roof over the relief, so nothing
    overhangs.
    """
    Z = driver_levels(specimen)
    o, u, t = _driver_frame()
    lock = trimesh.creation.extrude_polygon(geneva_lock_2d(),
                                            Z["crank_lo"] - Z["lock_lo"])
    lock.apply_translation([0, 0, Z["lock_lo"]])
    crank = cyl(CRANK_R, Z["crank_lo"], Z["crank_hi"], o[0], o[1], 96)
    stub = cyl(DRV_JOURNAL_R, Z["stub_lo"], Z["lock_lo"] + 0.01, o[0], o[1], 64)
    # the roof: the relief's inner edge, walked outward at 45 degrees
    # going down until it leaves the stub
    edge = float(np.min((np.asarray(geneva_lock_2d().exterior.coords)
                         - o[:2]) @ u[:2]))
    zl = Z["lock_lo"]
    tri = Polygon([(edge + 1.0, zl + 1.0), (-DRV_JOURNAL_R - 3.0, zl + 1.0),
                   (-DRV_JOURNAL_R - 3.0,
                    zl - (edge + DRV_JOURNAL_R + 3.0))])
    roof = trimesh.creation.extrude_polygon(tri, 2 * DRV_JOURNAL_R + 4.0)
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2] = u, [0, 0, 1], -t
    M[:3, 3] = o + t * (DRV_JOURNAL_R + 2.0)
    roof.apply_transform(M)
    stub = cut(stub, [roof])
    d = union([crank, lock, stub])
    pin = o - u * GENEVA_A
    hexr = (HEX_AF + HEX_CLR) / np.sqrt(3.0)
    return cut(d, [cyl(PIN_HOLE_D / 2, Z["crank_lo"] - 1, Z["crank_hi"] + 1,
                       pin[0], pin[1], 48),
                   _hex(hexr, Z["crank_hi"] - HEX_D, Z["crank_hi"] + 1)])


def _hex(r, z0, z1):
    """A hexagonal prism on the driver's axis, flats square to u."""
    o, _, _ = _driver_frame()
    h = cyl(r, z0, z1, 0, 0, 6)
    h.apply_transform(rot(GENEVA_PHI, [0, 0, 1]))
    h.apply_translation([o[0], o[1], 0])
    return h


def driver_knob(specimen=SPECIMEN):
    """Turned by the fingers, one turn a frame; a hex plug into the
    crank's socket. Twelve shallow flutes so it can be gripped. Printed
    upside down, its top on the plate."""
    Z = driver_levels(specimen)
    o, _, _ = _driver_frame()
    k = cyl(KNOB_R, Z["crank_hi"], Z["knob_hi"], o[0], o[1], 96)
    plug = _hex((HEX_AF - HEX_CLR) / np.sqrt(3.0),
                Z["crank_hi"] - HEX_D + 0.2, Z["crank_hi"] + 0.5)
    flutes = []
    for i in range(12):
        x, y, _ = polar(KNOB_R + 0.4, i * 30.0)
        flutes.append(cyl(1.2, Z["crank_hi"] + 1.5, Z["knob_hi"] + 1,
                          o[0] + x, o[1] + y, 24))
    return cut(union([k, plug]), flutes)


def pin_proxy(specimen=SPECIMEN):
    """The Ø3 dowel. Bought, so not in the file, but it has to be in the
    sweep: it is the thing that drives."""
    Z = driver_levels(specimen)
    o, u, _ = _driver_frame()
    p = o - u * GENEVA_A
    return cyl(PIN_R, Z["pin_lo"], Z["crank_hi"], p[0], p[1], 48)


# --- the sole plate ------------------------------------------------------
def sole_plate(specimen=SPECIMEN):
    """Glued to the board; the base bolts down onto its three pads."""
    L = levels(specimen)
    pad_top = SOLE_T + SOLE_PAD[1]
    s = rev([(SOLE_R[0], 0), (SOLE_R[1], 0), (SOLE_R[1], SOLE_T),
             (SOLE_R[0], SOLE_T)], sections=240)
    pads, tools = [], []
    for a in FOOT_PHI:
        x, y, _ = polar(FOOT_R, a)
        pads.append(cyl(SOLE_PAD[0], SOLE_T - 0.5, pad_top, x, y, 96))
        tools.append(cyl(INS_M4[0], pad_top - INS_M4[1], pad_top + 1,
                         x, y, 48))
    s = cut(union([s] + pads), tools)
    s.apply_translation([0, 0, L["base_bot"] - pad_top])
    return s


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


SLEEVES = ("sleeve_a", "sleeve_b", "sleeve_c")


def bearing_centres(retracted=False):
    """Where each bearing stands: on the race (its eccentric turned in
    until the bearing meets it), or turned fully out for the ring to go
    in. The bolt is always on the tower's axis; the bearing is ECC off."""
    out = []
    for a in TOWER_PHI:
        T = polar(TOWER_PITCH, a)[:2]
        rh, th = polar(1.0, a)[:2], polar(1.0, a + 90.0)[:2]
        if retracted:
            out.append(T + rh * ECC)
            continue
        c = (TOWER_PITCH ** 2 + ECC ** 2 - BRG_PITCH ** 2) / (2 * TOWER_PITCH * ECC)
        out.append(T - rh * ECC * c + th * ECC * np.sqrt(1 - c * c))
    return out


def sleeves_in_place(specimen=SPECIMEN, retracted=False):
    L = levels(specimen)
    z0 = L["brg_z"] - BRG_W / 2.0 - 0.1
    out = {}
    for n, a, B in zip(SLEEVES, TOWER_PHI, bearing_centres(retracted)):
        T = polar(TOWER_PITCH, a)[:2]
        s = sleeve(ECC)
        # built with its outside on the origin and its bore ECC along +x:
        # turned so the bore lands on the tower's axis
        d = T - B
        s.apply_transform(rot(np.degrees(np.arctan2(d[1], d[0])), [0, 0, 1]))
        s.apply_translation([B[0], B[1], z0])
        out[n] = s
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
    # the Geneva lip on the bore, flush with the underside it prints on
    lip = trimesh.creation.extrude_polygon(geneva_lip_2d(), LIP_T)
    lip.apply_translation([0, 0, zb])
    r_ = union([ring, pad, lip])
    tools = []
    # the slot the arc's bar keys into, and the inserts it bolts down to
    tools.append(box((BAR_X0 - 5.0, Y_ARC - ARC_HW - 0.2, zp - PAD_SLOT_D),
                     (RING_RO + 5.0, Y_ARC + ARC_HW + 0.2, zp + 1)))
    for x in BOLTS_X:
        tools.append(cyl(INS_M4[0], zp - PAD_SLOT_D - INS_M4[1],
                         zp - PAD_SLOT_D + 0.5, x, Y_ARC, 48))
        tools.append(cyl(BOLT_R, zp - PAD_SLOT_D - INS_M4[1] - 4.0,
                         zp - PAD_SLOT_D, x, Y_ARC, 48))
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
    # the inserts, and relief beyond them for the screw that comes up
    # through the platform: the assembly sweep found an M3x25 bottoming
    # 4 mm short of seated in a hole that stopped at the insert
    for y in (hy - CHANNEL[3], hy + CHANNEL[3]):
        for r_h, depth in ((INS_M3[0], INS_M3[1]),
                           (1.7, INS_M3[1] + RECV_RELIEF)):
            c = trimesh.creation.cylinder(radius=r_h, height=depth + 1,
                                          sections=48)
            c.apply_transform(rot(90.0, [1, 0, 0]))
            c.apply_translation([RECV_U, v0 - 1 + (depth + 1) / 2, y])
            tools.append(c)
    r_ = cut(r_, tools)
    r_.apply_transform(M_ARC)
    return r_


# --- proxies: hardware and the camera, for the sweeps and the page -----
def bearing_proxies(specimen=SPECIMEN, retracted=False):
    L = levels(specimen)
    return [cyl(BRG_R, L["brg_z"] - BRG_W / 2, L["brg_z"] + BRG_W / 2,
                x, y, 120) for x, y in bearing_centres(retracted)]


def mount_thread():
    """The Montessori cosine thread at Ø8 -- thread.py's family, which is
    what the Knot and the Tinker set already print in PETG."""
    return Thread(major_r=MOUNT_D / 2.0)


def mount_nut_h():
    """Wing nut height: three turns of engagement."""
    return 3.0 * mount_thread().lead


def mount_shank_len():
    """Head top to tip: the base left over the pocket, the pedestal, the
    plate, and enough past it for the wing nut to run down. Derived, not
    typed, so that lowering the pedestal cannot leave a screw that no
    longer reaches."""
    # The last term is what stands proud once the nut is down, and it was
    # 4.0 -- two whole leads of thread sticking up in the middle of the
    # plate, directly under the specimen. It buys nothing: the nut is
    # started at the top of the thread and wound down, so all the tail
    # has to do is not end short of the nut's last thread. 1.0 is half a
    # lead, enough to see it start and little enough to disappear.
    return ((BASE_T - MOUNT_POCKET) + PED_H + PLATE_T
            + mount_nut_h() + 1.0)


def mount_screw():
    """Hex head, shank up. The head is captive in the base's pocket."""
    T = mount_thread()
    return T.bolt(mount_shank_len(), head_h=MOUNT_HEAD_H)


def mount_hex_nut():
    """A plain hex nut on the same thread, for a driver or the wrench.

    Printed beside the wing nut rather than instead of it: the wings are
    for fingers and are the wider thing on the plate, and a hex is what
    you reach for when the wings are in the way of a rod.
    """
    return mount_thread().nut(height=mount_nut_h())


def mount_wing_nut():
    """A threaded boss with two upright fins, turned by fingers.

    The fins are vertical and rooted on the bed, so it prints as it
    stands with no support -- the same way the Tinker set's wing nut
    does, which is where the shape comes from.
    """
    T = mount_thread()
    h = mount_nut_h()
    span = MOUNT_WING_SPAN * T.major_r
    fin_t = MOUNT_WING_T * T.major_r
    boss = cyl(T.hex_cr, 0.0, h, 0, 0, 96)
    fins = []
    for k in (0, 1):
        f = box((-span, -fin_t / 2.0, 0.0), (span, fin_t / 2.0, h))
        if k:
            f.apply_transform(rot(90.0, [0, 0, 1]))
        fins.append(f)
    body = union([boss] + fins)
    cuts = [T.cutter(h + 2 * T.lead, z0=-T.lead,
                     runout=[(0.0, T.lead), (h, T.lead)]),
            T.mouth_chamfer(h, True), T.mouth_chamfer(0.0, False)]
    return cut(body, cuts)


def camera_proxy(kind=CAMERA_DEFAULT, lens_id=None):
    """One camera behind one lens, in world coordinates at theta = 0.
    Concatenated, not unioned: the sweep only asks whether anything
    touches, and overlapping boxes answer that as well as a solid."""
    cfg = camera_config(kind, lens_id)
    return trimesh.util.concatenate(
        [box(lo, hi) for group in cfg["boxes"].values() for lo, hi in group])


CLAMP_U = 155.0         # the thumbscrew's axis, where the carriage hangs
INFILL = 0.50           # 4-5 walls at 25-30% gyroid, as a share of solid
# What the tongue can take as a couple before the joint wants help. The
# a1 asked 110 N of it, which is what the ballast was for; the phone asks
# 6. 25 N is the line: above it, the ballast comes back.
TONGUE_COUPLE_N = 25.0


def carriage_moment(parts, kind=CAMERA_DEFAULT, lens_id=None,
                    cam_g=None, cam_u=None):
    """Gravity's moment about the thumbscrew, and the couple the tongue
    carries because of it.

    This is the whole argument for having no ballast, written so it can
    be checked rather than believed. If a heavier camera is added, or the
    platform grows again, this is what notices.
    """
    tot_m = tot_mu = 0.0
    for n in CARRIAGE:
        m = parts[n]
        g = m.volume / 1000.0 * PETG_G_PER_CM3 * INFILL
        tot_m += g
        tot_mu += g * float(m.center_mass[0])
    cfg = camera_config(kind, lens_id)
    bx = [b for grp in cfg["boxes"].values() for b in grp]
    vol = [float(np.prod(np.array(hi) - np.array(lo))) for lo, hi in bx]
    # overridable so a test can ask what a different camera would do.
    # Both together: the a1's trouble was never its mass alone, it was
    # 1.34 kg sitting 110 mm further out than a phone's clamp.
    if cam_u is None:
        cam_u = float(np.average([(lo[0] + hi[0]) / 2.0 for lo, hi in bx],
                                 weights=vol))
    if cam_g is None:
        cam_g = CAMERAS[kind]["mass_g"]
    M = tot_m + cam_g
    com = (tot_mu + cam_g * cam_u) / M
    moment = M / 1000.0 * 9.81 * (com - CLAMP_U) / 1000.0
    tongue = TONGUE[1] - TONGUE[0]
    return dict(mass_g=round(M, 1), com_u=round(com, 1),
                arm_mm=round(com - CLAMP_U, 1), moment_nm=round(moment, 3),
                tongue_couple_n=round(abs(moment) / (tongue / 1000.0), 1))


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
# The mount does not turn, so it belongs on the stator side -- and
# being listed is what puts it in the azimuth sweep at all. A body
# in neither list is simply never checked against anything.
#
# The driver turns, but about its own axis and not the rotor's, so for the
# azimuth sweep it stands where it does at every stop: that sweep steps
# the ring 10 degrees at a time, and at each step the lock is in a seat.
# How it moves between stops is `geneva_sweep`'s question.
STATOR_SIDE = ("stator", "sole_plate", "driver", "driver_knob",
               "sleeve_a", "sleeve_b", "sleeve_c",
               "mount_screw", "mount_wing_nut", "mount_hex_nut")
ROTOR_SIDE = ("rotor", "arc")
CARRIAGE = ("saddle", "shoe", "receiver")


def assemble(specimen=SPECIMEN):
    """Every printed body, in the world frame, at home: phi = 0 and the
    carriage at theta = 0 (its build pose; the page and the sweeps turn
    it)."""
    parts = {"stator": stator(specimen), "sole_plate": sole_plate(specimen),
             "driver": driver(specimen), "driver_knob": driver_knob(specimen)}
    parts.update(sleeves_in_place(specimen))
    parts["rotor"] = rotor(specimen)
    parts["arc"] = arc()
    parts["saddle"] = saddle()
    parts["shoe"] = shoe()
    parts["receiver"] = receiver()
    # Placed, not just built. Everything else assemble() returns is in
    # the world frame, and these two were left in the frame they are
    # drawn in -- which put the screw standing at the focal point, up
    # through the specimen, and the wing nut in the air beside it. The
    # page draws what this returns, and the sweeps check it, so the
    # mount was being collision-checked somewhere it never sits.
    L = levels(specimen)
    screw = mount_screw()
    screw.apply_translation([0, 0, L["base_top"] - BASE_T])
    parts["mount_screw"] = screw
    nut = mount_wing_nut()
    nut.apply_translation([0, 0, L["plat"] + PLATE_T])
    parts["mount_wing_nut"] = nut
    hexn = mount_hex_nut()
    # On the axis, where the wing nut also is. Both are printed and only
    # one is ever fitted, so the assembly carries them in the same place
    # and whatever is showing the assembly picks. Drawn off to one side
    # instead, the spare nut reads as part of the jig.
    hexn.apply_translation([0, 0, L["plat"] + PLATE_T])
    parts["mount_hex_nut"] = hexn
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
    # crank-down, so the lock and stub rise off it; the knob on its top
    if name in ("driver", "driver_knob"):
        return rot(180.0, [1, 0, 0])
    return np.eye(4)


def layout(parts, gap=6.0, pitch=300.0):
    """Three virtual plates side by side: the base, the ring, the rest.
    The shop's packer places each body itself; this arrangement only has
    to keep them from overlapping so it can tell them apart."""
    plates = [["stator"], ["rotor"],
              ["arc", "saddle", "shoe", "receiver", "sole_plate",
               "driver", "driver_knob",
               "sleeve_a", "sleeve_b", "sleeve_c"]]
    # Anything assemble() makes that is not named above joins the last
    # plate rather than being dropped. These lists were written when
    # there were ten bodies; adding the mount's screw and wing nut to
    # assemble() left them passing every gate and absent from the file,
    # because layout() is also what the export and the poses are built
    # from. A body that is not laid out does not get written.
    named = {n for pl in plates for n in pl}
    plates[-1].extend(n for n in parts if n not in named)
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


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return [_jsonable(v) for v in o.tolist()]
    if isinstance(o, (np.floating,)):
        return round(float(o), 5)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, float):
        return round(o, 5)
    return o


def assembly_meta(specimen, poses, parts, rep=None):
    L = levels(specimen)
    return {
        # the order it goes together in, the path of every piece, and
        # what the generator found when it swept them; the page animates
        # exactly this
        "assembly": _jsonable(dict(
            theta=MOUNT_THETA, steps=assembly_steps(parts, specimen),
            checked=None if rep is None else rep.get("assembly"),
            fits=fits(parts, specimen) if rep is None else rep.get("fits"),
            bom=inserts(), joints=[dict(name=n, crosses=c, insert=i,
                                        relief=r, qty=q, gauge=g,
                                        length=bolt_len(c, i, r))
                                   for n, c, i, r, q, g in JOINTS],
            bands=[dict(name=n, lo=lo, hi=hi) for n, lo, hi in FIT_BANDS])),
        "design": "orbital_jig", "specimen": specimen, "R": R,
        "levels": L, "elev_range": list(ELEV),
        "y_arc": Y_ARC, "leg_bottom": LEG_BOTTOM,
        "stator_side": list(STATOR_SIDE), "rotor_side": list(ROTOR_SIDE),
        "carriage": list(CARRIAGE),
        "to_world": {n: [round(float(v), 6) for v in poses[n].ravel()]
                     for n in poses},
        "bearing": dict(r=BRG_R, w=BRG_W, bore=BRG_BORE, pitch_r=BRG_PITCH,
                        centres=[[round(float(v), 4) for v in c]
                                 for c in bearing_centres()],
                        tower_r=TOWER_PITCH, ecc=ECC,
                        phi=list(TOWER_PHI), z=L["brg_z"],
                        head_r=HEAD_R, head_h=HEAD_H),
        "geneva": dict(slots=GENEVA_N, pitch_deg=360.0 / GENEVA_N,
                       c=GENEVA_C, phi=GENEVA_PHI, crank=round(GENEVA_A, 3),
                       mouth=round(GENEVA_MOUTH, 3), lip_t=LIP_T,
                       pin_r=PIN_R, pin_lo=driver_levels(specimen)["pin_lo"],
                       pin_hi=driver_levels(specimen)["crank_hi"],
                       drive_deg=180.0 + 360.0 / GENEVA_N,
                       pin_xy=[round(float(v), 4) for v in
                               (_driver_frame()[0] - _driver_frame()[1]
                                * GENEVA_A)[:2]]),
        "fasteners": fasteners(specimen),
        "arc": dict(ri=ARC_RI, ro=ARC_RO, hw=ARC_HW, slot=SLOT_W,
                    slot_deg=list(SLOT_DEG), fiducials=list(FIDUCIALS)),
        "thumbscrew": dict(r=2.5, y0=Y_ARC + SHOE_H[0] - 6.0,
                           y1=Y_ARC + PLATE_H[0] + 7.0, knob_r=7.0,
                           knob_h=6.0, u=155.0),
        "cameras": {k: dict(c, configs={l["id"]: camera_config(k, l["id"])
                                        for l in c["lenses"]})
                    for k, c in CAMERAS.items()},
        "camera_default": CAMERA_DEFAULT, "pupil": [R, CAM_Y, 0.0],
        "receiver_u": RECV_U,
        "receiver": dict(u=RECV_U, v=PLATFORM_V[1], size=list(RECV)),
        "protocol": PROTOCOL, "frustum": FRUSTUM, "lenses": LENSES,
        "frames": sum(int(round(360.0 / p["step"])) for p in PROTOCOL),
        "volume_cm3": {n: round(float(m.volume) / 1000.0, 1)
                       for n, m in parts.items()},
    }


# --- the assembly: an order, a path for every piece, and the fits -------
# The jig is put together in a fixed order, and each step is checked the
# way the sweeps check motion: the arriving pieces travel their path, in
# small steps, against everything already in place, and nothing may touch
# until they seat. The bill of materials is the sum of the steps, so a
# part the BOM names that no step fits -- or a step that needs a part the
# BOM does not name -- fails a gate instead of failing on the bench.
#
# Hardware is described as primitives so the page draws exactly what the
# check swept: cylinders, rings and boxes in world coordinates, seated.
def _prim_mesh(p):
    if p["kind"] == "box":
        m = box(p["lo"], p["hi"])
    else:
        ax = np.asarray(p["axis"], float)
        if p["kind"] == "ring":
            m = trimesh.creation.annulus(r_min=p["ri"], r_max=p["ro"],
                                         height=p["h"], sections=96)
        else:
            m = trimesh.creation.cylinder(radius=p["r"], height=p["h"],
                                          sections=48)
        m.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], ax))
        m.apply_translation(p["c"])
    if p.get("M") is not None:
        m.apply_transform(np.asarray(p["M"], float).reshape(4, 4))
    return m


def _moved(prims, M):
    """The same primitives, carried by M."""
    out = []
    for p in prims:
        q = dict(p)
        prev = np.asarray(p["M"], float).reshape(4, 4) if p.get("M") else np.eye(4)
        q["M"] = [round(float(v), 6) for v in (M @ prev).ravel()]
        out.append(q)
    return out


def _bolt_prims(seat, length, r=2.0, head_r=HEAD_R, head_h=HEAD_H,
                axis=(0, 0, 1)):
    """A socket-head bolt with its head's underside on `seat`; `axis`
    points from the shank to the head."""
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    seat = np.asarray(seat, float)
    return [dict(kind="cyl", c=(seat + a * head_h / 2).tolist(),
                 axis=a.tolist(), r=head_r, h=head_h),
            dict(kind="cyl", c=(seat - a * length / 2).tolist(),
                 axis=a.tolist(), r=r, h=length)]


def _arc_to_world(u, v, h):
    return (M_ARC @ np.array([u, v, h, 1.0]))[:3]


def _sleeve_bore(m):
    """Where a sleeve's bolt actually goes: the centre of its bore."""
    z = m.bounds[0][2] + 1.0
    sec = m.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    loops = sorted((Polygon(L[:, :2]) for L in sec.discrete),
                   key=lambda P: P.area)
    return np.array(loops[0].centroid.coords[0])


# The carriage goes onto the arc half way up it: at the arc's foot the
# leg is solid and there is no channel for its tongue to enter.
MOUNT_THETA = 45.0


def _step(id_, title, note, bodies=(), hw=(), path=None, against=None,
          check=None, spin=None, carry=(), at=None, alt=None, turn=None):
    """`hw` is [(bom_item, qty, [prims])]; `path` is (direction, travel),
    the way the pieces arrive. `against`, when given, makes it a bench
    step checked against those bodies only; what it builds rides along
    with the later step that names it in `carry`. `at` poses the step's
    bodies (the carriage at MOUNT_THETA); `alt` stands bodies somewhere
    other than their final pose (an eccentric turned out) until `turn`
    puts them back."""
    return dict(id=id_, title=title, note=note, bodies=list(bodies),
                hardware=[dict(item=i, qty=q, prims=pr) for i, q, pr in hw],
                path=None if path is None else
                dict(dir=list(map(float, path[0])), travel=float(path[1]),
                     spin=spin),
                against=None if against is None else list(against),
                check=check, carry=list(carry),
                at=None if at is None else [round(float(v), 6)
                                            for v in np.ravel(at)],
                alt=alt, turn=turn)


def assembly_steps(parts, specimen=SPECIMEN):
    L = levels(specimen)
    Z = driver_levels(specimen)
    length = {n: bolt_len(c, i, r) for n, c, i, r, _, _ in JOINTS}
    down, up = (0, 0, -1), (0, 0, 1)
    feet = [polar(FOOT_R, a, L["base_top"] - FOOT_CBORE[1]) for a in FOOT_PHI]
    towers = [polar(TOWER_PITCH, a)[:2] for a in TOWER_PHI]
    top_of = {n: parts[n].bounds[1][2] for n in SLEEVES}
    axles = [[T[0], T[1], top_of[n]] for n, T in zip(SLEEVES, towers)]
    bars = [[x, Y_ARC, LEG_BOTTOM + BAR_T - CBORE[1]] for x in BOLTS_X]

    def bearings(retracted):
        return [dict(kind="ring", c=[float(x), float(y), L["brg_z"]],
                     axis=[0, 0, 1], ro=BRG_R, ri=BRG_BORE / 2.0, h=BRG_W)
                for x, y in bearing_centres(retracted)]
    # how far each eccentric turns between standing out and standing in
    turn = []
    for n, T, Bo, Bi in zip(SLEEVES, towers, bearing_centres(True),
                            bearing_centres(False)):
        a0 = np.arctan2(*(Bo - T)[::-1])
        a1 = np.arctan2(*(Bi - T)[::-1])
        turn.append(dict(body=n, axis=[float(T[0]), float(T[1])],
                         deg=round(float(np.degrees(wrapdeg(a1 - a0))), 4),
                         bearing=n))
    o, u, _ = _driver_frame()
    pin_xy = o - u * GENEVA_A
    pin = [dict(kind="cyl", c=[pin_xy[0], pin_xy[1],
                               (Z["pin_lo"] + Z["crank_hi"]) / 2],
                axis=[0, 0, 1], r=PIN_R, h=Z["crank_hi"] - Z["pin_lo"])]
    E = elev(MOUNT_THETA)
    hy = CAM_Y - Y_ARC
    # a real M5 square nut, 8 x 4, centred in its 8.4 x 4.4 trap
    zn = PLATE_H[0] + 3.2 + NUT[1] / 2
    nut = _moved([dict(kind="box", lo=[151.0, -4.0, zn - 2.0],
                       hi=[159.0, 4.0, zn + 2.0], M=M_ARC.ravel().tolist())], E)
    thumb = _moved(_bolt_prims(_arc_to_world(155.0, 0.0, SHOE_H[0]), 25.0,
                               r=2.5, head_r=7.0, head_h=6.0,
                               axis=(0, -1, 0)), E)
    v0 = PLATFORM_V[0]
    recv_screws = _moved([p for y in (hy - CHANNEL[3], hy + CHANNEL[3])
                          for p in _bolt_prims(_arc_to_world(RECV_U, v0, y),
                                               length["receiver to platform"],
                                               r=1.5, head_r=2.75, head_h=3.0,
                                               axis=(0, 0, -1))], E)
    # its shank stops at the receiver's top here: it really runs on into
    # the clamp's socket, which the clamp's box stand-in does not have
    dring = _moved(_bolt_prims(
        _arc_to_world(RECV_U, PLATFORM_V[1] + QTR_CB[1], hy),
        RECV[2] - QTR_CB[1] - 0.1, r=3.175, head_r=QTR_CB[0] / 2.0,
        head_h=QTR_CB[1] - 0.2, axis=(0, 0, -1)), E)
    cfg = camera_config(CAMERA_DEFAULT)
    cam = _moved([dict(kind="box", lo=list(lo), hi=list(hi))
                  for grp in cfg["boxes"].values() for lo, hi in grp], E)
    up_arc = (E @ np.array([0, 0, 1.0, 0]))[:3]   # +v at MOUNT_THETA
    inboard, outboard = (0, -1, 0), (0, 1, 0)
    return [
        _step("sole", "Sole plate onto the board",
              "Melt the three M4 inserts into the pads, then glue the plate "
              "to a heavy board, pads up. Board and glue are not on the BOM.",
              ["sole_plate"], [("M4 heat-set insert", 3, [])], (down, 30.0)),
        _step("stator_inserts", "Inserts into the bearing towers",
              "Three M4 inserts, one in the top of each tower.",
              hw=[("M4 heat-set insert", 3, [])]),
        _step("mount_screw", "Mount screw up through the pedestal",
              "On the bench, from underneath: the hex head drops into its "
              "pocket and cannot turn. The last time the underside is "
              "reachable.", ["mount_screw"], path=(up, 60.0),
              against=["stator"]),
        _step("stator", "Base down onto the sole plate",
              "The three counterbored holes over the three pads; the mount "
              "screw rides in it.", ["stator"], path=(down, 30.0),
              carry=["mount_screw"]),
        _step("feet", "Three bolts down into the sole plate",
              "From above, through the bore.",
              hw=[("M4x" + str(length["stator to sole plate"]), 3,
                   [p for f in feet for p in
                    _bolt_prims(f, length["stator to sole plate"])])],
              path=(down, 20.0)),
        _step("bearings", "Sleeves and bearings onto the towers",
              "A 608 pressed on each sleeve. All three sleeves are "
              "eccentric: turn each so its bearing stands back from where "
              "the ring will be.", list(SLEEVES),
              [("608-2RS", 3, bearings(True))], (down, 25.0),
              alt="retracted"),
        _step("axles", "Axle bolts, finger tight",
              "Down through each sleeve into its tower's insert.",
              hw=[("M4x" + str(length["bearing axle to tower"]), 3,
                   [p for a in axles for p in
                    _bolt_prims(a, length["bearing axle to tower"])])],
              path=(down, 20.0)),
        _step("rotor_inserts", "Inserts into the rotor's pad",
              "Three M4 inserts in the floor of the pad's slot.",
              hw=[("M4 heat-set insert", 3, [])]),
        _step("rotor", "Ring down past the bearings",
              "Lip down, held at the race while the eccentrics come in.",
              ["rotor"], path=(down, 40.0)),
        _step("preload", "Turn the eccentrics in and tighten",
              "Each until its bearing meets the race and the ring turns "
              "without play; then the three axles.",
              check="race", turn=turn),
        _step("pin", "Pin into the crank",
              "On the bench: the Ø3 dowel pressed down through the crank.",
              hw=[("Ø3 x 10 steel dowel (the Geneva pin)", 1, pin)],
              path=(down, 14.0), against=["driver"]),
        _step("driver", "Driver down into its bushing",
              "Through the lock seat under it, stub into the base.",
              ["driver"], path=(down, 40.0), carry=["pin"]),
        _step("knob", "Knob onto the driver",
              "Hex down into the crank's socket.",
              ["driver_knob"], path=(down, 20.0)),
        _step("arc", "Arc down onto the pad",
              "The bar keys into the pad's slot.",
              ["arc"], path=(down, 40.0)),
        _step("arc_bolts", "Three bolts down through the bar",
              "Into the pad's inserts.",
              hw=[("M4x" + str(length["arc bar to rotor pad"]), 3,
                   [p for b in bars for p in
                    _bolt_prims(b, length["arc bar to rotor pad"])])],
              path=(down, 25.0)),
        _step("nut", "Square nut into the saddle",
              "On the bench: slid up into its trap.",
              hw=[("M5 square nut", 1, nut)], path=(up_arc, 20.0),
              against=["saddle"], at=E),
        _step("saddle", "Saddle onto the arc, inboard",
              "Half way up the arc, its tongue into the inboard channel.",
              ["saddle"], path=(inboard, 30.0), carry=["nut"], at=E),
        _step("shoe", "Shoe onto the arc, outboard", "",
              ["shoe"], path=(outboard, 30.0), at=E),
        _step("thumbscrew", "Thumbscrew through shoe, slot and saddle",
              "Into the square nut.",
              hw=[("M5x25 thumbscrew", 1, thumb)], path=(outboard, 40.0)),
        _step("receiver_prep", "Receiver: inserts and the 1/4-20",
              "On the bench: two M3 inserts underneath, the D-ring screw "
              "up through it.",
              hw=[("M3 heat-set insert", 2, []), ("1/4-20 D-ring", 1, dring)],
              path=(up_arc, 20.0), against=["receiver"], at=E),
        _step("receiver", "Receiver onto the platform", "",
              ["receiver"], path=(-up_arc, 20.0), carry=["receiver_prep"],
              at=E),
        _step("receiver_screws", "Two screws up through the channel",
              "Into the receiver's inserts; loose enough to slide it.",
              hw=[("M3x" + str(length["receiver to platform"]), 2,
                   recv_screws)], path=(up_arc, 30.0)),
        _step("camera", "Phone clamp onto the 1/4-20", "",
              hw=[("phone spring clamp, 1/4-20 socket", 1, cam)],
              path=(-up_arc, 30.0)),
        _step("mount", "Wing nut down the mount screw",
              "Over the rod field plate, which is its own design.",
              ["mount_wing_nut"], path=(down, 30.0),
              spin=dict(xy=[0.0, 0.0], lead=mount_thread().lead)),
        _step("spare", "The hex nut: for when a rod is in the wings' way",
              "Printed with the set, fitted instead of the wing nut.",
              ["mount_hex_nut"]),
    ]


def wrapdeg(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def _path_pose(path, t, phase=0.0):
    """Where a step's pieces are at distance t short of seated: back
    along the path, and for a nut, unwound about its screw at the lead."""
    T = np.eye(4)
    T[:3, 3] = -np.asarray(path["dir"], float) * t
    sp = path.get("spin")
    if sp:
        ang = 360.0 * t / sp["lead"] + phase
        T = T @ rot(ang, [0, 0, 1], origin=[sp["xy"][0], sp["xy"][1], 0])
    return T


def assembly_sweep(parts, specimen=SPECIMEN, step=0.5):
    """Every step's pieces along their path against what is in place --
    printed bodies and the hardware fitted before them. Returns per-step
    fouls, and whether the steps install every printed body exactly once
    and add up to the BOM."""
    steps = assembly_steps(parts, specimen)
    alts = {"retracted": sleeves_in_place(specimen, retracted=True)}
    installed, bench, out = {}, {}, []
    for st in steps:
        at = None if st["at"] is None else np.asarray(st["at"]).reshape(4, 4)
        movers = {}
        for n in st["bodies"]:
            m = (alts[st["alt"]][n] if st["alt"] else parts[n]).copy()
            if at is not None:
                m.apply_transform(at)
            movers[n] = m
        for h in st["hardware"]:
            for i, p in enumerate(h["prims"]):
                movers[f"{h['item']}#{i}"] = _prim_mesh(p)
        for c in st["carry"]:
            movers.update(bench.pop(c))
        fouls, phase = [], 0.0
        if st["path"] and movers:
            stat = installed
            if st["against"] is not None:
                # a bench step: the part it builds onto, posed as the step is
                stat = {}
                for n in st["against"]:
                    m = parts[n].copy()
                    if at is not None:
                        m.apply_transform(at)
                    stat[n] = m
            cm = tc.CollisionManager()
            for n, m in stat.items():
                cm.add_object("S:" + n, m)
            for n, m in movers.items():
                cm.add_object("M:" + n, m)

            def hits(T):
                for n in movers:
                    cm.set_transform("M:" + n, T)
                _, names = cm.in_collision_internal(return_names=True)
                return sorted({"|".join(sorted((a[2:], b[2:])))
                               for a, b in names
                               if (a[:2] == "M:") != (b[:2] == "M:")})

            if st["path"].get("spin"):
                # a nut ends wherever its thread lets it: find that phase
                for ph in np.arange(0.0, 360.0, 5.0):
                    if not hits(_path_pose(st["path"], 0.05, ph)):
                        phase = float(ph)
                        break
            for t in list(np.arange(st["path"]["travel"], 0.05, -step)) + [0.05]:
                hit = hits(_path_pose(st["path"], float(t), phase))
                if hit:
                    fouls.append((round(float(t), 2), hit))
                    break
        if st["turn"]:
            # the eccentrics come in: sleeves and bearings to where they run
            for n in SLEEVES:
                installed[n] = parts[n]
            for k in [k for k in installed if k.startswith("608-2RS#")]:
                del installed[k]
            for i, b in enumerate(bearing_proxies(specimen)):
                installed[f"608-2RS#{i}"] = b
        if st["check"] == "race":
            r = race_contact(parts["rotor"], specimen)
            if not all(x["gap"] < 0.05 and x["pressed_collides"] for x in r):
                fouls.append((0.0, ["bearings do not seat on the race"]))
        if st["against"] is not None:
            bench[st["id"]] = movers
        else:
            installed.update(movers)
        out.append(dict(id=st["id"], fouls=fouls))
    counts = {}
    for st in steps:
        for b in st["bodies"]:
            counts[b] = counts.get(b, 0) + 1
    bom = {}
    for st in steps:
        for h in st["hardware"]:
            bom[h["item"]] = bom.get(h["item"], 0) + h["qty"]
    want = inserts()
    return dict(steps=out, left_on_bench=sorted(bench),
                bodies_once=sorted(counts) == sorted(parts)
                and all(v == 1 for v in counts.values()),
                missing_bodies=sorted(set(parts) - set(counts)),
                bom=bom, bom_matches=bom == want,
                bom_diff={k: (bom.get(k, 0), want.get(k, 0))
                          for k in set(bom) | set(want)
                          if bom.get(k, 0) != want.get(k, 0)})


# --- fits: every PETG mating surface, measured off the built parts -------
# Graded on the shop's own table for PETG on the P2S with a 0.4 nozzle
# (drawn hole minus pin, on the diameter): press +0.10, slip +0.30,
# running +0.40. A printed hole comes out small, so a hole drawn at the
# pin's size is an interference. A printed shaft in a steel bore is the
# other way round, and has its own row.
FIT_BANDS = (("interference", -9.0, 0.0), ("press", 0.0, 0.2),
             ("slip", 0.2, 0.35), ("running", 0.35, 0.6),
             ("clearance", 0.6, 9.0))


def fit_class(allow, kind="printed hole"):
    if kind == "printed shaft in steel bore":
        return "press" if -0.2 < allow <= 0.15 else (
            "interference" if allow <= -0.2 else "slip")
    for name, lo, hi in FIT_BANDS:
        if lo <= allow < hi:
            return name
    return "clearance"


def _loop_at(mesh, xy, z, want):
    """The closed section loop centred near `xy` at height z whose size is
    nearest `want` (a radius): its inscribed and circumscribed radii,
    each about the loop's own centre."""
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if sec is None:
        return None
    best = None
    for Lp in sec.discrete:
        # the area centroid, not the vertices' mean: a cut leaves a loop
        # sampled densely on one side, and the mean walks toward it
        c = np.array(Polygon(Lp[:, :2]).centroid.coords[0])
        if np.linalg.norm(c - np.asarray(xy)[:2]) > 1.5:
            continue
        P = Lp[:, :2] - c
        a, b = P, np.roll(P, -1, axis=0)
        ab = b - a
        t = np.clip(-(a * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12),
                    0, 1)
        near = np.linalg.norm(a + ab * t[:, None], axis=1).min()
        far = np.linalg.norm(P, axis=1).max()
        score = abs((near + far) / 2 - want)
        if best is None or score < best[0]:
            best = (score, near, far)
    return None if best is None else (best[1], best[2])


def _ray_hit(mesh, origin, direction):
    d = np.asarray(direction, float) / np.linalg.norm(direction)
    loc, _, _ = mesh.ray.intersects_location([origin], [d],
                                             multiple_hits=False)
    return None if not len(loc) else float(np.linalg.norm(loc[0] - origin))


def _ray_gap(mesh, origin, direction):
    d = np.asarray(direction, float) / np.linalg.norm(direction)
    total = 0.0
    for s in (1, -1):
        loc, _, _ = mesh.ray.intersects_location([origin], [d * s],
                                                 multiple_hits=False)
        if not len(loc):
            return None
        total += float(np.linalg.norm(loc[0] - origin))
    return total


def fits(parts, specimen=SPECIMEN):
    L = levels(specimen)
    Z = driver_levels(specimen)
    o, u, t = _driver_frame()
    pin_xy = o - u * GENEVA_A
    rows = []

    def row(name, hole, shaft, intended, kind="printed hole", note=""):
        if hole is None or shaft is None:
            rows.append(dict(name=name, hole=hole, shaft=shaft,
                             allow=None, got="not measured",
                             intended=intended, ok=False, note=note))
            return
        a = round(hole - shaft, 3)
        got = fit_class(a, kind)
        ok = got == intended or (intended == "clearance"
                                 and got in ("running", "clearance"))
        rows.append(dict(name=name, hole=round(hole, 3), shaft=round(shaft, 3),
                         allow=a, got=got, intended=intended, kind=kind,
                         ok=ok, note=note))

    def hole_d(m, xy, z, r):
        lp = _loop_at(m, xy, z, r)
        return None if lp is None else 2 * lp[0]

    def shaft_d(m, xy, z, r):
        lp = _loop_at(m, xy, z, r)
        return None if lp is None else 2 * lp[1]

    zc = (Z["crank_lo"] + Z["crank_hi"]) / 2
    row("Geneva pin in the crank", hole_d(parts["driver"], pin_xy, zc, PIN_R),
        2 * PIN_R, "press", note="steel dowel, pressed")
    zl = L["ring_bot"] + LIP_T / 2
    a_s = np.radians(GENEVA_PHI + 180.0 / GENEVA_N)
    rs = (GENEVA_MOUTH + GENEVA_C + GENEVA_A) / 2
    org = np.array([rs * np.cos(a_s), rs * np.sin(a_s), zl])
    row("Geneva pin in a slot", _ray_gap(parts["rotor"], org,
                                         [-np.sin(a_s), np.cos(a_s), 0]),
        2 * PIN_R, "running", note="it slides the slot's length every frame")
    zb = L["base_top"] + 1.0
    row("Driver stub in its bushing",
        hole_d(parts["stator"], o, zb, DRV_JOURNAL_R + DRV_CLR),
        shaft_d(parts["driver"], o, zb, DRV_JOURNAL_R), "running",
        note="printed in printed; turns once a frame")
    # the seat opens into the bore, so no closed loop: measured along u,
    # out from the driver's axis to the seat's wall and in to the lock's
    po = np.array([o[0], o[1], zl])
    seat = _ray_hit(parts["rotor"], po, u)
    lk = _ray_hit(parts["driver"], po + u * 10.0, -u)
    row("Lock in its seat", None if seat is None else 2 * seat,
        None if lk is None else 2 * (10.0 - lk), "running",
        note="it turns 170 degrees in the seat each frame")
    zh = Z["crank_hi"] - HEX_D / 2
    sock = _loop_at(parts["driver"], o, zh, HEX_AF / 2)
    plug = _loop_at(parts["driver_knob"], o, zh, HEX_AF / 2)
    row("Knob's hex in the crank", None if sock is None else 2 * sock[0],
        None if plug is None else 2 * plug[0], "slip",
        note="across the flats")
    for a in FOOT_PHI[:1]:
        f = polar(FOOT_R, a)
        row("Foot bolt through the base",
            hole_d(parts["stator"], f, L["base_top"] - FOOT_CBORE[1] - 1.5,
                   BOLT_R), 4.0, "clearance")
    row("Bar bolt through the arc",
        hole_d(parts["arc"], (BOLTS_X[0], Y_ARC), LEG_BOTTOM + 3.0, BOLT_R),
        4.0, "clearance")
    sl = parts["sleeve_a"]
    bx, by = _sleeve_bore(sl)
    zs = sl.bounds[0][2] + 1.0
    row("Axle bolt through a sleeve", hole_d(sl, (bx, by), zs, BOLT_R), 4.0,
        "clearance")
    oc = sl.centroid[:2]
    row("Sleeve in a 608's bore", 8.0, shaft_d(sl, oc, zs, SLEEVE_R),
        "press", kind="printed shaft in steel bore",
        note="the bearing pressed onto its sleeve")
    th = np.radians(45.0)
    sc = np.array([155.0 * np.cos(th), Y_ARC, 155.0 * np.sin(th)])
    row("Thumbscrew along the arc's slot",
        _ray_gap(parts["arc"], sc, [np.cos(th), 0, np.sin(th)]), 5.0,
        "running", note="it slides the slot's length with every ring")
    hy = CAM_Y - Y_ARC
    ch = _arc_to_world((CHANNEL[0] + CHANNEL[1]) / 2,
                       (PLATFORM_V[0] + PLATFORM_V[1]) / 2, hy + CHANNEL[3])
    row("Receiver screws along the channel",
        _ray_gap(parts["saddle"], ch, [1, 0, 0]) and
        _ray_gap(parts["saddle"], ch, [0, 1, 0]), 3.0, "running",
        note="they slide the channel to set the phone's distance")
    # between the D-ring's counterbore and the dovetail cut over it
    rc = _arc_to_world(RECV_U, PLATFORM_V[1] + QTR_CB[1] + 2.0, hy)
    row("1/4-20 through the receiver",
        hole_d(parts["receiver"], rc, rc[2], QTR_R), 6.35, "clearance")
    row("Mount screw through the pedestal",
        hole_d(parts["stator"], (0, 0), L["base_top"] + PED_H / 2,
               MOUNT_BORE_R), MOUNT_D, "clearance",
        note="a printed thread in a plain bore")
    bar = np.array([(BOLTS_X[0] + BOLTS_X[1]) / 2, Y_ARC,
                    L["pad_top"] - PAD_SLOT_D / 2])
    row("Arc's bar in the pad's slot", _ray_gap(parts["rotor"], bar, [0, 1, 0]),
        2 * ARC_HW, "running",
        note="it locates the arc; bar_seats proves it holds")
    return rows


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


def count_slots(r_, specimen):
    """Probe the lip at mid-thickness: in every slot there is nothing, and
    past the end of every lock seat, between two slots, there is lip.
    Returns the slots seen, or -1 if lip is missing where a slot isn't."""
    z = levels(specimen)["ring_bot"] + LIP_T / 2.0
    step = 360.0 / GENEVA_N
    r_slot = (GENEVA_MOUTH + GENEVA_C + GENEVA_A) / 2.0
    r_land = GENEVA_C + LOCK_R + LOCK_CLR + 1.0
    slots = [polar(r_slot, GENEVA_PHI + step * (k + 0.5), z)
             for k in range(GENEVA_N)]
    lands = [polar(r_land, GENEVA_PHI + step * k, z) for k in range(GENEVA_N)]
    empty = ~r_.contains(np.array(slots))
    solid = r_.contains(np.array(lands))
    if not solid.all():
        return -1
    return int(empty.sum())


def geneva_sweep(parts, specimen, step=1.0):
    """One whole turn of the driver, the ring following the Geneva law,
    against the rotor: nothing may touch. Then the two things a Geneva is
    for, each proven by a collision. Locked: at a stop, the ring nudged
    0.4 degrees either way runs into the lock. Driven: with the pin
    mid-slot, the same nudge runs into the pin. Without those a ring
    that slipped past the driver would sweep clean too."""
    o, _, _ = _driver_frame()
    cm = tc.CollisionManager()
    cm.add_object("rotor", parts["rotor"])
    movers = {"driver": parts["driver"], "pin": pin_proxy(specimen)}
    for n, m in movers.items():
        cm.add_object(n, m)

    def pose(psi, nudge=0.0):
        cm.set_transform("rotor", rot(geneva_wheel(psi) + nudge, [0, 0, 1]))
        T = rot(psi - 180.0, [0, 0, 1], origin=[o[0], o[1], 0])
        for n in movers:
            cm.set_transform(n, T)
        _, names = cm.in_collision_internal(return_names=True)
        return sorted("|".join(sorted(p)) for p in names if "rotor" in p)

    fouls = [(float(psi), f) for psi in np.arange(180.0, 540.0 + 1e-9, step)
             for f in [pose(psi)] if f]
    nudge = 0.4
    locked = all(pose(180.0, d) for d in (-nudge, nudge))
    driven = all(pose(360.0, d) for d in (-nudge, nudge))
    advance = geneva_wheel(540.0) - geneva_wheel(180.0)
    return dict(fouls=fouls, locked=locked, driven=driven,
                advance_deg=round(float(advance), 6))


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
    turn against the stator side. Ten degrees a step, because those are
    the only places the ring stops: at each the driver's lock is in a
    seat. Between stops the driver moves too, and `geneva_sweep` follows
    both."""
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


# Every threaded joint, as a stack: how much printed part the bolt has to
# cross before it reaches the insert, how deep the insert is, and how much
# relief is bored under it. The length follows from those three, so it
# cannot drift away from the geometry the way a typed list did.
#
# It had. The BOM said M4x16 for all eight M4 bolts, and at the arc bar
# that crosses 12 mm of bar and leaves 4 mm in a 7 mm insert -- four
# threads, on the joint that carries the arc and the whole carriage
# through a 90 degree sweep. The pawl, since gone, was the same story in M3. Measured
# on the built rotor: 11.00 mm of hole on each bolt axis, 0.00 beside it.
JOINTS = (
    # name, crosses, insert depth, relief, count
    ("arc bar to rotor pad", BAR_T - CBORE[1], INS_M4[1], 4.0, 3, "M4"),
    ("bearing axle to tower", SLEEVE_H + SLEEVE_FL_H, INS_M4[1], 4.0, 3, "M4"),
    # the head sits in a 5 mm counterbore; under the insert, 1 mm of pad
    ("stator to sole plate", BASE_T - FOOT_CBORE[1], INS_M4[1], 1.0, 3, "M4"),
    # up through the platform into the receiver, so it slides the channel
    ("receiver to platform", PLATFORM_V[1] - PLATFORM_V[0], INS_M3[1],
     RECV_RELIEF, 2, "M3"),
)
_STOCK = (6, 8, 10, 12, 16, 20, 25, 30, 35)


def fasteners(specimen=SPECIMEN):
    """The bolts the page draws, where they sit: head down on its seat,
    shank the length the joint table gives it. Bought, so not in the
    file -- but drawn from the same numbers the BOM is."""
    L = levels(specimen)
    length = {n: bolt_len(c, i, r) for n, c, i, r, _, _ in JOINTS}
    return [
        dict(joint="stator to sole plate", side="stator", r=2.0,
             head_r=HEAD_R, head_h=HEAD_H, len=length["stator to sole plate"],
             at=[[round(float(v), 4) for v in
                  polar(FOOT_R, a, L["base_top"] - FOOT_CBORE[1])]
                 for a in FOOT_PHI]),
        dict(joint="arc bar to rotor pad", side="rotor", r=2.0,
             head_r=HEAD_R, head_h=HEAD_H, len=length["arc bar to rotor pad"],
             at=[[x, Y_ARC, LEG_BOTTOM + BAR_T - CBORE[1]] for x in BOLTS_X]),
    ]


def bolt_len(crosses, insert, relief):
    """Shortest stock length that fills the insert without bottoming."""
    lo, hi = crosses + insert, crosses + insert + relief
    for L in _STOCK:
        if lo <= L <= hi:
            return L
    return None


def inserts():
    out = {"M4 heat-set insert": 3 + 3 + 3, "M3 heat-set insert": 2,
           "608-2RS": 3, "M5x25 thumbscrew": 1, "M5 square nut": 1,
           "1/4-20 D-ring": 1,
           "\u00d83 x 10 steel dowel (the Geneva pin)": 1,
           "phone spring clamp, 1/4-20 socket": 1}
    for _, crosses, ins, relief, n, gauge in JOINTS:
        key = f"{gauge}x{bolt_len(crosses, ins, relief)}"
        out[key] = out.get(key, 0) + n
    return out


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
    rep["slots"] = count_slots(parts["rotor"], specimen)
    rep["assembly"] = assembly_sweep(parts, specimen)
    rep["fits"] = fits(parts, specimen)
    rep["geneva"] = geneva_sweep(parts, specimen)
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
    rep["carriage_balance"] = carriage_moment(parts)
    rep["bearing_pitch_r"] = BRG_PITCH
    rep["preload_travel_mm"] = 2 * ECC
    rep["retracted_clear_mm"] = round(float(min(
        np.linalg.norm(c) for c in bearing_centres(True)) - BRG_R - RING_RO), 3)
    return rep


def gates(rep):
    return [("watertight", all(rep["watertight"].values())),
            ("fits_plate", all(rep["fits_plate"].values())),
            ("pedestal_hidden_at_75", rep["pedestal_hidden_at_75"]),
            ("arc_concentric", ARC_RI - 0.05 <= rep["arc_radii"][0]
             and rep["arc_radii"][1] <= ARC_RO + 0.05),
            ("slot_width", rep["slot_mm"] is not None
             and abs(rep["slot_mm"] - SLOT_W) < 0.15),
            ("36_slots", rep["slots"] == GENEVA_N),
            ("geneva_turns_clear", not rep["geneva"]["fouls"]),
            ("geneva_locks_and_drives", rep["geneva"]["locked"]
             and rep["geneva"]["driven"]
             and abs(rep["geneva"]["advance_deg"] - 360.0 / GENEVA_N) < 1e-6),
            # it goes together in the order given, and the BOM is the sum
            ("assembles_in_order", not any(s["fouls"]
                                           for s in rep["assembly"]["steps"])
             and not rep["assembly"]["left_on_bench"]),
            ("bom_is_the_steps", rep["assembly"]["bom_matches"]
             and rep["assembly"]["bodies_once"]),
            ("fits_as_intended", all(f["ok"] for f in rep["fits"])),
            # every protocol step is a whole number of Geneva stops
            ("protocol_on_stops", all(abs(p["step"] / (360.0 / GENEVA_N)
                                          - round(p["step"] / (360.0 / GENEVA_N)))
                                      < 1e-9 for p in PROTOCOL)),
            ("bearings_on_race", all(r["gap"] < 0.05 and r["pressed_collides"]
                                     for r in rep["race"])),
            ("pupil_at_R", all(abs(p - R) < 0.01 for p in rep["pupil_radius"])
             and all(abs(y) < 0.01 for y in rep["pupil_y"])),
            ("bar_seats_in_slot", rep["bar_seats"]["overlap_mm3"] < 1.0
             and rep["bar_seats"]["pressed_collides"]
             and rep["bar_seats"]["shoved_collides"]),
            ("elevation_clear", not rep["elevation_fouls"]),
            ("azimuth_clear", not rep["azimuth_fouls"]),
            # no ballast, and this is why: see carriage_moment
            ("carriage_balanced_enough",
             rep["carriage_balance"]["tongue_couple_n"] <= TONGUE_COUPLE_N)]


# --- export ------------------------------------------------------------
def export(parts, specimen, out, rep=None):
    flat, poses = layout(parts)
    sc = trimesh.Scene()
    for n, m in flat.items():
        sc.add_geometry(m, geom_name=n, node_name=n)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sc.export(out)
    from embed_settings import embed
    # no brim: three of these are 250 mm plates and the rest stand on
    # broad flat faces; a brim on the ring's underside would ring the
    # Geneva lip and close its slots' mouths
    embed(out, brim=False)
    meta = assembly_meta(specimen, poses, parts, rep)
    with zipfile.ZipFile(out, "a", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Metadata/orbital_jig.json",
                   json.dumps(meta, separators=(",", ":")))
    from meshcheck import export_defects
    return export_defects(out), meta


def _parser():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specimen", type=float, default=SPECIMEN,
                    help="focal point above the platform, mm")
    ap.add_argument("--out")
    ap.add_argument("--quick", action="store_true",
                    help="skip the sweeps (geometry only)")
    return ap


def generate(out=None, **kw):
    """Build the part and, given `out`, write it. Returns the report.

    This is the generator. `main` below is a command line around it
    and nothing else -- the shop imports this and calls it.
    """
    a = genapi.namespace(_parser(), out=out, **kw)
    if not SPECIMEN_RANGE[0] <= a.specimen <= SPECIMEN_RANGE[1]:
        return {"ok": False, "error": "specimen height must be "
                          f"{SPECIMEN_RANGE[0]:g}-{SPECIMEN_RANGE[1]:g} mm"}
    parts = assemble(a.specimen)
    if a.quick:
        rep = {"watertight": {n: bool(m.is_watertight)
                              for n, m in parts.items()}}
        rep["ok"] = all(rep["watertight"].values())
        return rep
    rep = measure(parts, a.specimen)
    failed = [n for n, ok in gates(rep) if not ok]
    ok = not failed
    if failed:
        rep["failed"] = failed
        rep["error"] = "gate failed: " + ", ".join(failed)
    if a.out and ok:
        bad, meta = export(parts, a.specimen, a.out, rep)
        rep["defects"] = bad or None
        rep["frames"] = meta["frames"]
        ok = not bad
        rep["file"] = os.path.basename(a.out)
    rep["bodies"] = len(parts)
    return {"ok": ok, **rep}
    return 0 if ok else 1


def main():
    return genapi.cli(_parser(), generate)



if __name__ == "__main__":
    sys.exit(main())
