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
# The three feet are bolts, down into three pucks glued to a heavy board.
# They stand under the corners, the base's own triangle at 79% of its
# size (Brett, 2026-10-15): at r = 60 on the mid-edges they made a
# triangle 104 mm a side, upside down to the base's, and every tower
# overhung the line between two feet by 102 mm; at r = 114 under the
# corners it is 197 mm a side and each tower stands 18 mm outboard of
# its own foot. 114 is as far out as a hex key still reaches a head past
# the V wheel above it (the wheel's tip is at 119.6): with the ring off,
# not with it on -- the ring's lip covers r 72.7 to 121. So the feet go
# in before the ring, and the jig comes off its board with the ring
# lifted out, which it rarely has to.
FOOT_PHI = TOWER_PHI
FOOT_R = 114.0
FOOT_CBORE = (3.9, 5.0)               # the socket head and its key: radius, depth
# The pucks: one under each foot, so the base touches the board at three
# points and nothing else -- a full face would screw any warp in the
# board into the base, and from there into the race. Bolted under the
# base and then glued down with it, so the base is their template: they
# land under its holes because they are bolted to them. They were one
# ring, a sole plate, whose only other job was that spacing.
PUCK_R = 9.0                          # its top, which the base stands on
PUCK_FOOT = (13.0, 2.0)               # its glued foot: radius, height
PUCK_H = 10.0                         # the base's underside above the board
# the drive's cable runs under the base, clear of its underside --
# six loose 28 AWG wires, 2.6 mm across, and the home lead beside it
CABLE_UNDER = 2.5

# 242, not the spec's 246: this shop packs with a 5 mm plate margin and a
# 3 mm gap round every part, and 246 + 3 does not go into 246. The bore
# stays at 180 and the bearings follow the race outward.
RING_RO, RING_RI, RING_T = 121.0, 90.0, 18.0
# The flanks were 3 mm, and the assembly sweep found the ring could not
# be fitted: three bearings, each overlapping the ring's lips by 3 mm, and
# only one of them able to stand back -- by 2. So the flanks come down to
# what holds the bearing's edge, and every sleeve is an eccentric. Turned
# outward, each bearing stands 0.75 mm clear of the ring's lip and the
# ring drops straight in; turned in, they close on the race with 0.85 mm
# still in hand.
#
# 0.85, not the 0.2 it was: the in-hand margin is what absorbs the ring
# and the base coming off the plate different sizes, and both are 240 mm
# across. At 0.2, a ring shrinking 0.17% more than the base left the
# bearings unable to reach the race, with no way to know before the ring
# was printed. The sleeves' offset grew from 1.0 to 1.5 mm, and the axles
# went from M4 to M3 so the sleeve keeps its 0.75 mm wall between bolt
# and bearing. With every assumed spread half as large again
# (tools/jig_tolerance.py --scatter 1.5) the bearings' reach failed first,
# so the towers came in 0.15 from where that left them, trading drop-in
# clearance, which had more to spare.
# V wheels, not 608s. A 608 on a flat race with 45 degree flanks carried
# the ring's weight on its 0.3 mm edge chamfer against PETG, about 120 MPa,
# and left the ring 0.4 mm of axial play to rock in whenever the camera's
# weight was outside the bearings, which is most of the time. A Delrin
# V wheel (the OpenBuilds Solid V: 23.9 OD, 10.23 wide, a 90 degree V
# edge) seats on both faces of a V groove in the ring's OD: the load is on
# its V faces, and the ring has no axial play at all. The wheel holds two
# 16 x 5 mm bearings; 688-2RS (8 x 16 x 5) in place of the kit's 625s gives
# it an 8 mm bore, so it rides the same printed eccentric sleeve the 608
# did. The V's tip enters the groove WHEEL_E, and the groove runs RACE_RELIEF
# deeper so the tip never bottoms: only the faces touch.
# The profile is OpenBuilds' own STEP of the Solid V (printables 459179):
# 10.2 wide, a 5.9 mm flat at the OD between 45 degree flanks that run
# down to r 9.8 at the faces. It is a trapezoid, not a sharp V -- its flat
# rides inside V-slot's 6.2 mm opening and only the flanks touch -- and
# 12.0.0 to 17.0.0 drew it with a 1 mm tip, which cut the ring a groove
# 3.8 mm wide that the real 5.9 mm flat bridged without entering.
# Brett's wheels (sold as SIMAX3D rollers, the Creality pattern) measure a
# 6.2 mm flat in 10.2 with calipers, 2026-10-13, and a 19.6 face -- the
# STEP's own: flanks 2.0 long and 2.2 deep, 47.7 degrees to the axis. The
# groove stays 45: 2.7 degrees steeper, the wheel bears at the edges of its
# flat, and the race coupon seated it with ~1 mm under the flat. Drawn to his.
# 32.0.0: the wheel is printed now, so it no longer has to be the POM
# one. Drawn at 47 degrees to the axis against the groove's 45, it touched
# the groove only at the two corners of its flat -- and the lower corner
# is the edge of the overhang it prints as, the roughest edge on the part
# (Brett's photos, 2026-10-14). Its flanks are 45 now, the groove's own,
# through the same flat: it seats where it did, on a band of flank 2 mm
# wide each side instead of an edge. The ring stays as printed.
# 38.0.0: 0.65 larger. Brett's 45 degree wheels (0.08 layers) ran smooth
# only with every eccentric turned fully in, leaving nothing to take up
# wear; the 47 degree ones were a little tight there. Drawn to reach 0.85
# past the race, the printed wheel in its printed groove reaches about
# 0.05: it seats 0.8 deeper than drawn (jig_tolerance.WHEEL_SEAT_LOSS).
# With that in the tolerance model, 0.65 more radius is what reaches the
# race in all but one build in a thousand, whatever the seed; on Brett's
# parts it reaches about 0.7 past, to be backed off to run, and that is the take-up. The
# towers stay where the 11.95 wheel put them (TOWER_PITCH): it is all reach.
WHEEL = dict(r=12.60, w=10.2, tip=3.1)     # tip: half the flat
WHEEL_R_TOWERS = 11.95                     # the wheel the printed towers were placed for
WHEEL["side_r"] = WHEEL["r"] - (WHEEL["w"] / 2 - WHEEL["tip"])   # 45 degrees
# Printed, from 22.0.0. The POM wheels came with two 625s each (5 mm bore),
# pressed in, and the printed sleeves are 7.95: the plan was to swap the
# 625s for 688s, and Brett's 625s would not come out by hand. So the
# wheel is printed to the same profile -- the race, towers and sleeves
# all stay as printed -- with a Ø16 bore the two 688s press into, one
# from each face. They stack 10.0 in its 10.2, so each sits 0.1 under its
# face.
#
# A plain bore, drawn Ø16.15 so it prints near Ø16: snug, pushed in by
# hand or in a vise. Not crush ribs -- Brett has had PETG ribs that did
# not crush and stopped a part going in at all. The fit is biased loose
# because loose has a remedy and tight does not: a bearing that turns in
# its bore gets a drop of CA or J-B Weld on its outer ring. Each mouth is
# chamfered so the bearing starts square.
# 38.0.0: Ø16.10. The 0.08-layer wheels' Ø16.15 printed loose enough
# that their 688s fell out; Brett's first wheel, at 0.2, was a perfect
# push fit. A twentieth tighter, glue still the remedy if it is loose.
WHEEL_BORE_R = 8.05
WHEEL_MOUTH = 0.5       # 45 degree chamfer at each face of the bore
WHEELS = ("wheel_a", "wheel_b", "wheel_c")
WHEEL_BRG_ITEM = "688-2RS bearing (8 x 16 x 5), two in each V wheel"
WHEEL_E = 1.4           # how far the V's tip enters the groove
RACE_FLANK = WHEEL_E    # (named for what it was: the groove's depth at the V)
RACE_R = RING_RO - WHEEL_E            # where the wheel's tip runs
RACE_PLAY = 0.0         # axial: the V seats on both faces
# Under the wheel's flat, the groove runs this much deeper than the flat
# rides. Only the flanks may touch; depth there costs nothing -- the
# flanks' contact is unchanged and the ring has 31 mm of section behind
# it -- and covers a printed floor that comes out shallow, an edge left
# soft by the molding, and a flat measured on the wide side. 0.4 until
# 19.0.0.
RACE_RELIEF = 1.0
BRG_R, BRG_W, BRG_BORE = WHEEL["r"], WHEEL["w"], 8.0
BRG_PITCH = RACE_R + BRG_R            # a wheel seated in the groove
RING_GAP = 8.0          # ring underside above the base top: the tip of
                        # the driver's pin swings through here
TOWER_R, BOSS_R, BOSS_H = 7.0, 4.8, 1.0   # the boss bears on a 688's inner race only
# Ø7.95, not 7.9: a printed shaft comes out at about its drawn size, so
# 7.9 sat in the 608's 8 mm bore with a tenth of play
# The flange is a 10 mm hex, 3 tall, held in a wrench while the axle bolt
# tightens. Round and 1.0 tall until 31.0.0, it turned with the bolt head
# -- the inner races under it turn freely -- and walked each wheel back
# off the race as it was tightened. The hex's corners are where the round

SLEEVE_R, SLEEVE_H, SLEEVE_FL_H = 3.975, WHEEL["w"] - 0.2, 3.0
SLEEVE_HEX = 10.0       # across flats
SLEEVE_FL_R = SLEEVE_HEX / np.sqrt(3.0)   # across corners, /2
# One thread through the whole jig: every bolt is an M3, into one insert,
# turned with one key. The base's feet and the arc's bar were M4; at M3
# the bar's three still hold the arc a hundred times over, and the
# order is one bag of inserts and one of screws.
BOLT_R = 1.7            # M3 clearance, radius
AXLE_R = 1.7            # the bearing axles' M3 clearance, radius
ECC = 1.5               # eccentric sleeve offset: 3.0 mm of travel
# The towers stand where an eccentric turned fully in pushed the 11.95
# wheel 0.85 past the race -- printed, so fixed. A wheel's PRELOAD is how
# far past the race fully in still reaches, as drawn: 1.50 for the 12.60.
TOWER_PITCH = RACE_R + WHEEL_R_TOWERS + ECC - 0.85   # 132.2
PRELOAD = BRG_PITCH - (TOWER_PITCH - ECC)
LOBE_REACH = 142.0      # how far the base's corner lobes reach
# Named, and drawn to its maker's hole: Ruthex's M3 x 5.7 asks for Ø4.0
# and 6.7 deep -- a millimeter past its length, so the plastic it melts
# out of the way has somewhere to go besides up round the screw.
INS_M3 = (2.0, 6.7)     # bore radius, depth
INSERT_M3 = "M3 heat-set insert, M3 x 5.7 (\u00d84.0 hole)"
INSERT_L = 5.7          # the insert's own length: all the thread there is
# Brett's idea, from pressing them: a seat at the mouth the insert's own
# size, three layers deep, so it stands in the hole square and centred
# before the iron goes on, and goes down straight. Ruthex's knurl is 4.6
# across; drawn 0.2 over, as a small printed hole prints under.
INSERT_OD = 4.6
INSERT_SEAT = (INSERT_OD + 0.2, 0.6)    # diameter, depth


def insert_seat(x, y, mouth, up=1.0):
    """The seat at an insert's mouth, `mouth` the height of the face it
    goes in from (the hole runs down from there)."""
    return cyl(INSERT_SEAT[0] / 2, mouth - INSERT_SEAT[1], mouth + up, x, y, 64)
# A bolt into a blind insert ends inside it. The melt the knurl pushes
# down fills the bore under the insert; a bolt that reaches past the
# insert's end meets that plug and stops before it clamps. Brett's
# base-to-puck M3x10, 2026-10-13: alone in a puck it went 3.6 mm in and
# stopped; with a washer an M3x8 was still long and an M3x6 pulled up
# tight. So a puck's usable thread is PUCK_THREAD, measured -- not the
# insert's 5.7 -- and the joint table uses it there.
# On the practice piece's post the same M3x10 went 4.4 mm in. Where a
# bolt stops is what limits it, not the drawn bore: INSERT_STOP for every
# blind insert, the first puck's own figure for the pucks.
ENGAGE_MIN = 2.5        # five turns of M3; the puck joint, proven, has this
PUCK_THREAD = 3.6
INSERT_STOP = 4.4
WASHER_M3 = (7.0, 0.5)  # DIN 125 M3 flat washer: OD, thickness
WASHER_ITEM = "M3 flat washer (DIN 125, 7 OD x 0.5)"
AXLE_HEAD = (2.75, 3.0)               # M3 socket head
HEAD_R, HEAD_H = AXLE_HEAD

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
# hangs under the base, which is bolted down to its pucks. 73 is the
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
# The lip and the lock are cut for a driver at GENEVA_C; the driver stands
# GENEVA_BIAS nearer the axis than that. The Geneva's tolerance is
# lopsided: with the ring free to follow the pin, the lip may sit 0.2 mm
# further in than the driver expects before the lock's seat closes on the
# lock at every stop, but well over a millimeter further out, where all
# that grows is the stop's play. Everything that moves the lip relative to
# the driver -- the post's play in its socket, the ring centred by three
# eccentrics turned by hand, the ring out of round, the ring and the base
# shrinking differently, the motor tilting in its pocket, the gearbox's
# play, the base flexing -- was sampled together (tools/jig_tolerance.py)
# and wants about +-1.0. Biased by 1.0 the window is -1.1 (a jam, with
# the lip printed as it prints) to +0.9 (a degree of play at the stop),
# and the stop's play at nominal is under half a degree, which the
# capture never sees.
GENEVA_BIAS = 1.0
GENEVA_AT = GENEVA_C - GENEVA_BIAS
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
LOCK_FILLET = 0.6       # at the lock's root, under the crank
CRANK_R = GENEVA_A + PIN_R + 2.5      # the crank disc, above the lip: 2.5
                                      # of wall beside the pin, which is pressed
CRANK_T = 8.0           # the pin is held over all of it
# The crank's underside stands 1.3 above the lip, its top 0.6 under the
# block's floor. The ring rocks on its bearings when the camera's weight
# is outside them, which it mostly is, lifting the lip up to 0.3 at the
# drive, and the base's corners flex another 0.1-0.2; the tolerance stack
# (tools/jig_tolerance.py) closed the 0.6 it had in 4% of builds. The floor gap is set with a printed 0.6 shim when
# the driver is pressed on, not by where the shaft's tip happens to end.
LIP_GAP = 1.3
FLOOR_GAP = 0.6
DRIVER_LEADIN = 0.8                   # chamfer where its bores meet the plate:
                                      # four layers, so it prints as a cone
# --- the motor that turns the driver, and what holds it -----------------
# A real part, drawn from its maker's drawing: Pololu #994, the 298:1
# Micro Metal Gearmotor HP 6V (Pololu, micro-metal-gearmotor-dimensions,
# 2024-04-03). 100 rpm and 4.0 kg.cm at 6 V, 1.6 A stalled; run from USB
# at 5 V through its 4.7 ohm it turns about 73 rpm free (firmware/sim, from
# those same numbers), so a frame's driver turn takes about 0.83 s, and
# the Geneva multiplies its torque by twelve or more at the ring -- some
# twenty times what the ring needs.
#
# The driver hangs on the gearmotor's own D-shaft. It cannot stand on a
# shaft of its own: while the pin drives, the lip sweeps straight through
# the driver's axis, so nothing may cross the lip's plane there. The
# gearbox's output bushing is the driver's bearing, and the motor sits in
# a printed block on a post from the base, where its wires never turn.
# Pololu #5173: the same 298:1 HP 6V gearbox, face and shaft as #994,
# with a 12 CPR magnetic encoder on the back and a 6-pin JST SH plug
# carrying everything -- motor +/-, encoder VCC, A, B, GND. 3,576 counts
# a driver turn, so the controller knows where the driver is at every
# moment: no phase magnet, no phase sensor, no solder at the motor.
# The side-connector version, not the back: a plug on the back stands up
# over the motor with its wires bending above it, and that height put the
# drive in four frames at the bottom of the dial. On the side, facing the
# tower, the cable leaves level and runs straight into the post's bore.
# The encoder end is bigger than the gearbox, 13.6 x 13.0 from the drawing.
MOTOR = dict(item="Pololu #5173 298:1 Micro Metal Gearmotor HP 6V, "
                  "12 CPR encoder, side connector",
             w=12.0, d=10.0, gearbox=9.0, body=15.0, enc=8.5,
             enc_w=13.6, enc_d=13.0,
             # the side header (2.7 proud) with the JST SH housing on it:
             # out from the encoder, across, tall
             plug=(5.8, 8.0, 4.0),
             shaft_d=3.0, shaft_flat=2.5, shaft_l=10.0,
             bush_d=4.0, bush_h=0.7, rpm_6v=100.0, stall_kgcm=4.0,
             # 297.92:1 exactly (Pololu), so 12 x 297.92 counts a driver
             # turn, not 3,576: counted at 3,576 it drifts a count a frame
             stall_a=1.6, counts=12 * 297.92)
SLIP = 0.30             # the shop's slip, drawn hole minus pin
PRESS = 0.10            # the shop's press
# Presses into PETG. Printed holes scatter about +-0.15, so a press
# drawn for a 0.1 interference comes out loose in a share of prints. PETG
# is ductile -- past about 5% strain it yields rather than cracks -- so the
# answer is a press drawn tight enough to be tight in every print, and a
# vise to make it. Crush ribs were tried and are wrong for PETG: nothing
# crushes, the ribs smear and creep, and how they behave was a guess.
PIN_PRESS = -0.03       # the Geneva pin's hole over the pin: prints ~0.2 under, tight always
LID_PRESS = 0.05        # the lid's peg and key over their printed bores
# The D-shaft is not pressed at all: a clearance D-bore, and an M3 set
# screw on its flat through a captured nut, the way Pololu's own hubs hold
# these shafts. Nothing about the print decides whether it holds, and no
# press goes through the gearbox.
DBORE_CLR = 0.45        # the D-bore over the shaft, round and flat: it must slide on
                        # in every print; the set screw takes up whatever is left
SETSCREW_ITEM = "M3x8 set screw, cup point"
NUT_ITEM = "M3 hex nut"
NUT_AF, NUT_T = 5.5, 2.4
# pockets for bought parts that something else locates: room for the
# maker's tolerance, so they never have to be scraped to go in
POCKET_GB, POCKET_ENC = 0.4, 0.5      # gearbox plates; a routed PCB
BUSH_FIT = 0.35         # the gearbox's bushing in the floor
HALL_FIT = 0.4
MAGNET_FIT = 0.40       # slip, and glued: small discs run +-0.05 to 0.1
FLOOR_T = 3.0           # the block's floor, under the gearmotor's faceplate
# The block's walls round the encoder: thin on the outward side, where its
# corner passes 1.5 mm inside the arc's bar, thicker inward.
WALL_OUT, WALL_IN, WALL_SIDE = 1.2, 2.0, 1.6
# Nothing is soldered at the motor. Pololu's 6-pin cable plugs into the
# encoder's side, the plug lying in an open-topped channel through the
# block's inner wall, and its loose end goes down a bore in the post and
# out through the base. A flat lid presses on over all of it: a peg in
# the screw's access bore and a key in the top of the plug's channel,
# which also keeps the plug from ever backing out. No inserts, no screws.
CAP_T = 3.0
KEY_D = 1.5             # the lid's key, down into the top of the plug's channel
# The post and tower are as wide as the block round the encoder: the
# block prints on its side, and a narrower tower stood 1.55 mm off the
# plate for its whole length, an overhang with nothing under it.
POST_X = 10.0                                             # radial
POST_Y = MOTOR["enc_w"] + POCKET_ENC + 2 * WALL_SIDE      # across
POST_R = 55.0           # its centre from the rotor axis: clear of the crank,
                        # inside the lip's mouth (72.7), and far enough in
                        # that the plug's channel never reaches the screw's
                        # access bore
SCREW_Y, CABLE_Y = -3.5, 3.5          # the post's two bores, side by side
POST_SOCKET = 0.8       # how far its foot sits down into the base
PIN_L = 16.0            # the Geneva pin: Ø3 x 16, through the 8 mm crank
MAGNET = (3.0, 2.0)     # Ø3 x 2 N52 disc, either face to its sensor
# Honeywell SS451A, an omnipolar Hall switch: it answers either pole, so
# the home magnet cannot go in the wrong way up. (The A1120 it replaces
# answered south only; a magnet pressed in north-down would have left the
# jig never finding home, with nothing to show why.) Flat TO-92 package,
# 4.06 x 3.05 x 1.57, three leads at 1.27; 3 to 24 V, and it runs from
# the XIAO's 3V3, its open-collector output pulled up to the same 3V3.
HALL_ITEM = "Honeywell SS451A omnipolar Hall switch"
HALL = (4.06, 3.05, 1.57)
HALL_LEADS = (0.22, 1.27)   # its three leads: half their 0.43 width, pitch
# Its three leads leave the package's bottom edge, in the plane of its
# face, not its underside. Lying face up -- it senses through that face,
# and the magnet passes overhead -- they point out sideways at mid-
# thickness, and are bent 90 degrees down at the body's edge. Until
# 23.0.0 they were drawn straight down out of the middle of its
# underside, into a Ø3.6 hole under the pocket's centre: the real leads
# met the pocket's wall 0.2 mm out, and the outer two the solid floor.
# So a slot along that edge of the pocket, straight down through the
# base, takes them: they run out of the pocket and down it.
HALL_SLOT = (4.0, 1.5)      # along the leads' row, and out from the body
HALL_BEND = 0.4             # how far out of the body each lead turns down
HOME = dict(r=100.0, phi=85.0, boss_r=5.5, gap=3.0)   # the ring's home sensor

Y_ARC = -60.0           # the arc's plane, off the meridian
ARC_RI, ARC_RO = 140.0, 170.0
ARC_HW = 10.0           # flange half-width (y)
WEB_HT = 4.0            # web half-thickness
FLANGE = 5.0
CHAM = 4.0              # 45 degree web roots, so the underside prints
# A closed box, not an H with a slot down its web. The carriage hangs 73 mm
# off the arc's plane, so the arc carries a twist all the way from its pad
# to the carriage, and an open section slit along its length for the
# thumbscrew twisted like two loose rails: 2.1 mm and 1.0 degree at the
# lens at 80 degrees, first mode 7 Hz. Closed, 3 mm walls, no slot: 0.65 mm,
# 0.2 degree, 11.5 Hz in the same beam model. The carriage clamps round
# the outside instead, lips riding the box's inner and outer faces.
BOX_WALL = 3.0
BOX_CHAM = 4.0          # the cavity's corners at 45 degrees: its roof prints
                        # as a 16 mm bridge held along both edges
LIP_CLR = 0.25          # each lip off its face: a running fit
LIP_T = 2.5             # a lip's radial thickness
SLOT_W = 0.0            # no slot
LEG_BOTTOM = -28.0      # the arc's leg ends here, whatever the specimen;
                        # moves with PED_H, one for one -- see PED_H above
BAR_T, BAR_X0 = 20.0, 66.0            # the bar in to the ring; its inner end
                                      # stays over the annulus (r 96 at y -70)
BOLTS_X = (72.0, 86.0, 100.0)         # three M3s down through the bar
CBORE = (4.0, 8.0)      # counterbore radius and depth for their heads
FIDUCIALS = (15.0, 30.0, 45.0, 60.0, 75.0)
TICK_W, TICK_D = 1.2, 1.0

# The pad runs in to the ring's own bore. Until 25.0.0 it stopped at r 92,
# and the inner bolt's insert (r 93.72, a 2.0 bore) broke 0.28 mm out of
# its inner face: the printed rings show the insert through the wall.
PAD_PHI, PAD_R, PAD_SLOT_D = (-58.0, -14.0), (RING_RI, 121.0), 4.0

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
# The inboard face came in from 25.8 when the phone became a 17 Pro: its
# top edge stands 33.6 toward the arc from the pupil, and at 25.8 it
# cleared the saddle by 0.6 mm, less than a hand-set clamp holds to.
PLATE_H = (10.8, 22.6)  # saddle plate band in h (inboard)
PHONE_CLEAR = 3.0       # phone to its own carriage, at least
# The thumbscrew runs from the shoe's outer face through the slot into
# the square nut in the saddle, and must come right through the nut.
# The BOM said M5x25, which stops 10 mm short of it.
THUMB_LEN = 40.0
SHOE_H = (-20.8, -10.8) # outboard shoe band
TONGUE = (147.0, 163.0, 6.2)          # r0, r1, depth stops at |h| = 6.2
NUB_R, NUB_POS = 2.0, ((142.5, -15.0), (142.5, 15.0),
                       (167.5, -15.0), (167.5, 15.0))
SCREW_R = 2.7           # M5 clearance
# the thumbscrew clamps saddle to shoe just outside the box's outer face
CLAMP_R = ARC_RO + LIP_CLR + LIP_T + 0.5 + SCREW_R
NUT = (8.4, 4.4)        # M5 square nut trap, across and thick
# The heel. With the thumbscrew the only thing joining saddle and shoe,
# outboard of everything they bear on, tightening it had nothing to
# react against: each plate rocked on the box's outer edge, closing
# over the screw and opening under the box, and Brett's carriage twisted
# as he turned it. So the shoe carries a wall across to the saddle's
# face, outboard of the screw: a fulcrum. The screw now sits between it
# and the nubs, and squeezes both -- the nubs about a quarter of its
# pull, the heel the rest -- and the plates cannot rock. It stops
# HEEL_GAP short of the saddle with the nubs touching, so they always
# bear first and the plates close the last 0.2 by a turn of 0.4 degree.
HEEL = (CLAMP_R + SCREW_R + 2.0, CLAMP_R + SCREW_R + 8.0)
HEEL_GAP = 0.2
# 34.0.0: the platform, its fore/aft channel and the sliding receiver are
# gone. They were drawn for a clamp guessed as a spring clamp gripping the
# phone's middle, its socket on a foot under it. Brett's clamp is an
# ULANZI ST-02S screw clamp, gripping the phone near its bottom, its
# socket on the END of one block -- and a phone held portrait along the
# arc puts that end face 10 mm from the saddle. So the receiver is now a
# straight bar bolted to the saddle's inboard face, running up the arc to
# a seat the clamp's end face sits on (see ST02S and MOUNT below).
CAM_Y = 0.0
# The square nut sits in a pocket open on the saddle's inboard face, a
# floor under it: pushed in from the face, it cannot hide. Until 34.0.0 it
# slid along a slot from the plate's end, and a wedge added later sealed
# that slot's mouth: Brett's printed saddle had the nut trap as a void.
NUT_FLOOR = 1.2
# The 1/4-20 that holds the clamp: a plain hex-head bolt through the seat
# from behind, turned with a 7/16 wrench or nut driver while the clamp
# stays put -- the clamp never turns to tighten, so where its thread stops
# does not decide where the phone points. The pin in the clamp's second
# hole decides that.
QTR_R = 3.4                           # 1/4"-20 clearance, radius
QTR_HEAD = (7.0 / 16 * 25.4, 4.14)    # 7/16 across flats; ASME's tallest head
QTR_HEAD_REAL = 3.97                   # McMaster 92245A537's STEP: what is drawn
QTR_LEN = 0.5 * 25.4                  # under the head
QTR_ITEM = "1/4-20 x 1/2 in hex head cap screw (holds the phone clamp)"
CLAMP_ITEM = "ULANZI ST-02S phone clamp (1/4-20 socket)"

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
# An iPhone 17 Pro, its main lens at the pupil, drawn here as if held
# landscape and turned portrait below (see _portrait). Every number is Apple's dimensional drawing for the 17 Pro
# (2025-09-09): 150.01 x 71.85 x 8.75 body, the camera plateau 2.55 off
# the back plate and the lens glass 1.88 off the plateau, 13.18 overall.
# Of the three lenses, Apple's keepout cones say which is which: 125
# degrees is the ultra wide (upper left, seen from the back), 90 the main
# (lower left), 34 the 4x telephoto (right). The main is 14.37 in from
# the side and 33.61 down from the top edge, so the phone's top edge
# stands 33.6 toward the arc from the pupil, not the 14 an iPhone 15
# class body put it.
#
# Seen from the specimen the back faces it: u is depth (lens glass at
# 150, back plate at 154.43, screen at 163.18), y runs along the phone,
# v across it. The plateau's lower edge is not dimensioned on the
# drawing; it is taken 3.8 mm below the main lens's ring, as drawn.
#
# This is the only camera. A Sony a1 on an Arca plate was carried here
# too, and it was what the carriage was sized for -- a 1.34 kg body and
# macro whose tripod socket sits 320 mm out, against a quarter kilo of
# phone and clamp. It drove the platform's length, the ballast at both
# ends, and the clearance reasoning. None of that is wanted for a phone,
# so it is gone rather than left as an option nobody takes.
#
# Fields of view are horizontal. The spec wrote one frustum, 32 degrees
# at 3:2 -- a 63 mm-equivalent lens -- which frames 86 x 57 mm at 150 mm
# and cannot hold a 129 mm tooth.
IP17 = dict(length=150.01, width=71.85, depth=8.75, plateau=2.55,
            glass=1.88, main_from_side=14.37, main_from_top=33.61,
            lens_d=16.20, plateau_below_main=8.1 + 3.8, mass_g=206.0)
_U_GLASS = 150.0
_U_BACK = _U_GLASS + IP17["glass"] + IP17["plateau"]          # 154.43
_U_FRONT = _U_BACK + IP17["depth"]                             # 163.18
_Y_TOP = -IP17["main_from_top"]                                # -33.61
_Y_BOT = _Y_TOP + IP17["length"]                               # 116.40
_V_HI = IP17["main_from_side"]                                 # 14.37
_V_LO = _V_HI - IP17["width"]                                  # -57.48
_LR = IP17["lens_d"] / 2.0
def _portrait(b):
    """A landscape box turned a quarter about the view axis: the phone's
    length runs along the arc (v), its width across it (y)."""
    (u0, y0, v0), (u1, y1, v1) = b
    return ((u0, -v1, y0), (u1, -v0, y1))


# Held portrait, upside down, in an ULANZI ST-02S screw clamp -- not the
# spring clamp, gripping the phone's middle, that was drawn until 34.0.0.
# The phone's length runs along the arc with its top edge down-arc; the
# edge Camera Control is on, the main lens 14.37 in from it, faces the
# arc. So the lens sits on the meridian 16.6 mm in from the case's edge,
# and the clamp grips near the phone's bottom, up the arc, its socket end
# toward the saddle (Brett, 2026-10-14). Landscape would put the clamp
# 90 mm past the meridian at the end of a 130 mm arm; portrait puts it
# beside the saddle, the same load on a quarter less lever. Upside down,
# because right way up puts the clamp in the ring at the horizon ring.
#
# The case, measured with the phone in it: 155 x 76 (Brett, 2026-10-14).
# Over the back and the screen it is taken as 1.2.
CASE = dict(length=155.0, width=76.0, back=1.2, front=1.2)
CASE["end"] = (CASE["length"] - IP17["length"]) / 2.0          # 2.50
CASE["side"] = (CASE["width"] - IP17["width"]) / 2.0           # 2.08
_CASE_EDGE = -(IP17["main_from_side"] + CASE["side"])         # y, arc side
_CASE_TOP = -(IP17["main_from_top"] + CASE["end"])            # v, down-arc
_U_MID = (_U_BACK + _U_FRONT) / 2.0                            # the phone's mid-depth
# The clamp, from Brett's ruler photographs and calipers (2026-10-14). In
# its own frame: X along its length from the end face its socket is in,
# Y across its 27 mm jaws, Z from the crossbar's back toward the jaw tips.
# The phone's mid-depth sits where the curved pads' centres are, 25 from
# the back. The socket and a second, plain 6.2 hole (the lead screw's
# end, which stops well short of it) are on that end face, 12.05 and 5.25
# from the back: the walls between them measure 8.9 and 2.1, and
# Brett's centre readings of 11.5 and 5.3 give the same 6.8 between.
ST02S = dict(w=27.0, depth=36.1, up_t=8.6, pad_t=3.0, pad_z=(13.0, 34.0),
             pad_c=25.0, bar_long=11.5, bar_short=9.0, len_long=47.0,
             len_short=37.0, socket_z=12.05, socket_d=6.35, socket_deep=6.45,
             pin_z=5.25, pin_hole=5.0, pin_deep=10.0, rod_r=1.75, rod_y=8.0,
             screw_r=2.0, knob_r=7.75, knob_h=6.0, knob_ridges=40,
             button=(8.3, 6.1, 3.45), mass_g=50.0)
# Gripping near the phone's bottom, under Camera Control: 112 of the case
# above the clamp, the clamp's 27.5, 15 below.
CLAMP_V = _CASE_TOP + 112.0 + 27.5 / 2.0          # its centre along the phone
CLAMP_FACE_Y = _CASE_EDGE - (ST02S["up_t"] + ST02S["pad_t"])   # its socket end
CLAMP_BACK_U = _U_MID + ST02S["pad_c"]            # its crossbar's back
CLAMP_GAP = CASE["width"]                          # pad to pad
SOCKET_U = CLAMP_BACK_U - ST02S["socket_z"]
PIN_U = CLAMP_BACK_U - ST02S["pin_z"]


def _clamp_x():
    """Where each block runs along the clamp, closed on the case."""
    c = ST02S
    face = c["up_t"] + c["pad_t"]                  # the long pad's face
    s1 = face + CLAMP_GAP + c["pad_t"] + c["up_t"]  # the short block's end
    return dict(long=(0.0, c["len_long"]), short=(s1 - c["len_short"], s1),
                pad_long=(c["up_t"], face),
                pad_short=(face + CLAMP_GAP, face + CLAMP_GAP + c["pad_t"]),
                up_short=(s1 - c["up_t"], s1), end=s1)


def clamp_to_world(X, Y, Z):
    """The clamp's frame into the camera's (world at theta = 0)."""
    return (CLAMP_BACK_U - Z, CLAMP_FACE_Y + X, CLAMP_V - Y)


def _clamp_box(lo, hi):
    a = np.array(clamp_to_world(*lo)); b = np.array(clamp_to_world(*hi))
    return (tuple(np.minimum(a, b).round(4)), tuple(np.maximum(a, b).round(4)))


def _clamp_boxes():
    """The clamp as the blocks it is made of, for its mass and centre."""
    c, x, hw = ST02S, _clamp_x(), ST02S["w"] / 2.0
    return [_clamp_box((x["long"][0], -hw, 0), (x["long"][1], hw, c["bar_long"])),
            _clamp_box((0, -hw, 0), (c["up_t"], hw, c["depth"])),
            _clamp_box((x["short"][0], -hw, 0), (x["short"][1], hw, c["bar_short"])),
            _clamp_box((x["up_short"][0], -hw, 0), (x["end"], hw, c["depth"])),
            _clamp_box((x["end"], -c["knob_r"], c["pin_z"] - c["knob_r"]),
                       (x["end"] + c["knob_h"], c["knob_r"], c["pin_z"] + c["knob_r"]))]


_PHONE_BOXES = [
    # the case, round the phone; the camera plateau stands through it
    ((_U_BACK - CASE["back"], _CASE_EDGE, _CASE_TOP),
     (_U_FRONT + CASE["front"], _CASE_EDGE + CASE["width"],
      _CASE_TOP + CASE["length"])),
    _portrait(((_U_BACK, _Y_TOP, _V_LO), (_U_FRONT, _Y_BOT, _V_HI))),
    # the plateau, the full width of the back
    _portrait(((_U_BACK - IP17["plateau"], _Y_TOP, _V_LO + 1.0),
               (_U_BACK, IP17["plateau_below_main"], _V_HI - 1.0))),
    # the three lens rings, as one block
    _portrait(((_U_GLASS, -19.24 - _LR, -18.01 - _LR),
               (_U_BACK - IP17["plateau"], _LR, _LR)))]


CAMERAS = {
    "iphone": dict(
        name="iPhone 17 Pro, portrait, in an ULANZI ST-02S clamp",
        receiver_u=SOCKET_U,
        # phone, case and clamp together. It is here rather than in a test
        # because it is what decides whether the carriage needs ballast,
        # and `carriage_moment` below turns that into something the
        # suite can fail on.
        mass_g=IP17["mass_g"] + 30.0 + ST02S["mass_g"],
        boxes=dict(phone=_PHONE_BOXES, clamp=_clamp_boxes()),
        # main, ultra wide, 4x telephoto: Apple's centres, re-based on the
        # main lens and turned portrait with the phone
        rings=[dict(c=(_U_GLASS, 0.0, 0.0), r=_LR),
               dict(c=(_U_GLASS, 0.0, -19.24), r=_LR),
               dict(c=(_U_GLASS, 18.01, -9.62), r=_LR)],
        # held portrait, the frame is 3:4: across it (y) is the sensor's
        # short side, 71.5 and 39.8 degrees being across its long one
        lenses=[dict(id="wide", name="1\u00d7 main, 24 mm eq.",
                     fov_deg=56.7, aspect=3.0 / 4.0),
                dict(id="tele", name="2\u00d7 crop, 48 mm eq.",
                     fov_deg=30.4, aspect=3.0 / 4.0)],
        default_lens="wide"),
}
CAMERA_DEFAULT = "iphone"

# The receiver: a straight bar bolted flat to the saddle's inboard face,
# running up the arc to the seat the clamp's end face stands on. In the
# saddle's frame (u, v, h): h is off the arc's mid-plane, inboard
# positive, so the clamp's end face is at h = CLAMP_FACE_Y - Y_ARC.
MOUNT_H0 = PLATE_H[1]                              # on the saddle's face
MOUNT_FACE = CLAMP_FACE_Y - Y_ARC - 0.1            # the seat, 0.1 off the clamp
MOUNT_U = (157.0, 186.0)                           # round the socket and the pin
MOUNT_V = (-21.5, CLAMP_V + ST02S["w"] / 2.0)      # the saddle's span, to the clamp
# Two M3 screws into inserts in the saddle's face, clear of the nut's
# pocket at the thumbscrew. Drawn Ø3.3 to locate it, Brett's screws
# would not pass: a vertical hole that small prints under. Ø3.5 passes
# them by a hair, still close enough to locate.
MOUNT_SCREWS = ((163.0, -14.0), (163.0, 14.0))
MOUNT_SCREW_R = 1.75
# The 1/4-20 runs QTR_ENGAGE into the clamp's socket, which is 6.45 deep
# (Brett's calipers): four threads, and 1.25 short of the bottom, so a
# bolt a little long or a seat printed a little thin still lets the clamp
# pull down onto the seat rather than the bolt onto the socket's floor.
# Under its head the seat is what is left of the bolt's 1/2 in: a
# counterbore from behind takes the rest, wide enough for a 7/16 nut
# driver round the head.
QTR_ENGAGE = 5.2
MOUNT_UNDER = QTR_LEN - 0.1 - QTR_ENGAGE
MOUNT_CBORE_R = 9.5
ROOF_STEP = 0.4          # each step of a stepped roof: two 0.2 layers
# A printed pin in the clamp's plain hole sets which way the clamp, and
# so the phone, points; the bolt only holds it there. The plain hole is
# about 5.0 by Brett's calipers (2026-10-15), not the 6.2 first read,
# and his printed 5.8 would not go in; 4.9 is the most he wants in it.
# A printed shaft comes out a few hundredths over, so this is a close
# fit with nothing to spare -- what a key wants. Still 3.8 times as
# stiff as the 3.5 that a pulled, levered printed pin must at least be.
# No root fillet: the hole's edge sits at its root, 0.1 off the seat.
MOUNT_PIN = (4.9, 4.0, 0.5)                        # diameter, length, tip chamfer
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
# sensor, 84 degrees across the diagonal, 71.5 across its long side,
# framing 216 x 162 mm at R -- held portrait, 162 across and 216 up the
# arc, so the angles here are across the short side. The spec's own macro used to stay selectable beside
# them; it is gone with the body that could have carried it, because a
# frustum no camera on this jig can produce is not a choice, it is a
# drawing of somebody else's camera.
LENSES = [dict(id="wide", name="iPhone 1\u00d7 main (24 mm eq.)",
               fov_deg=56.7, aspect=3.0 / 4.0),
          dict(id="tele", name="iPhone 2\u00d7 crop (48 mm eq.)",
               fov_deg=30.4, aspect=3.0 / 4.0)]
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
    top = RING_GAP + RING_T / 2.0 - BRG_W / 2.0           # the wheel's underside
    for a in TOWER_PHI:
        x, y, _ = polar(TOWER_PITCH, a)
        parts.append(cyl(TOWER_R, -1.0, top - BOSS_H, x, y))
        parts.append(cyl(BOSS_R, top - BOSS_H - 0.5, top, x, y))
    ped = rev(pedestal_profile(), sections=120)
    parts.append(ped)
    # the ring's home sensor stands on a boss, HOME["gap"] under the ring
    hx, hy_, _ = polar(HOME["r"], HOME["phi"])
    parts.append(cyl(HOME["boss_r"], -1.0, RING_GAP - HOME["gap"], hx, hy_, 64))
    s = union(parts)
    tools = []
    for a in TOWER_PHI:
        x, y, _ = polar(TOWER_PITCH, a)
        tools.append(cyl(INS_M3[0], top - INS_M3[1], top + 1, x, y, 48))
        tools.append(insert_seat(x, y, top))
        tools.append(cyl(AXLE_R, top - INS_M3[1] - 4.0, top, x, y, 48))
    # the three foot bolts, headed from above, down into the pucks
    for a in FOOT_PHI:
        x, y, _ = polar(FOOT_R, a)
        tools.append(cyl(BOLT_R, -BASE_T - 1, 1.0, x, y, 48))
        tools.append(cyl(FOOT_CBORE[0], -FOOT_CBORE[1], 1.0, x, y, 48))
    # the drive post's foot: a square socket that keys it, an M3 insert
    # under it, and beside it the hole the drive's cable goes down
    hx, hy_ = POST_X / 2 + 0.2, POST_Y / 2 + 0.2      # the shop's running fit
    sock = box((-hx, -hy_, -POST_SOCKET), (hx, hy_, 1.0))
    ins = union([cyl(INS_M3[0], -POST_SOCKET - INS_M3[1], 0.5, 0, SCREW_Y, 48),
                 insert_seat(0, SCREW_Y, -POST_SOCKET, POST_SOCKET + 0.5)])
    relief = cyl(1.7, -BASE_T - 1, 0.5, 0, SCREW_Y, 48)
    wire = cyl(2.5, -BASE_T - 1, 1.0, 0, CABLE_Y, 48)
    for m in (sock, ins, relief, wire):
        m.apply_transform(rot(GENEVA_PHI, [0, 0, 1]))
        m.apply_translation(polar(POST_R - GENEVA_BIAS, GENEVA_PHI))
        tools.append(m)
    # the home sensor lies face up in its boss; its leads go down through
    top = RING_GAP - HOME["gap"]
    hx, hy_, _ = polar(HOME["r"], HOME["phi"])
    pk = box((-(HALL[0] + HALL_FIT) / 2, -(HALL[1] + HALL_FIT) / 2, top - HALL[2] - 0.2),
             ((HALL[0] + HALL_FIT) / 2, (HALL[1] + HALL_FIT) / 2, top + 1.0))
    pk.apply_transform(rot(HOME["phi"], [0, 0, 1]))
    pk.apply_translation([hx, hy_, 0])
    tools.append(pk)
    # the leads' slot, on the pocket's +y side, down through the base
    y0 = HALL[1] / 2 - 0.3
    slot = box((-HALL_SLOT[0] / 2, y0, -BASE_T - 1), (HALL_SLOT[0] / 2, y0 + HALL_SLOT[1], top + 1.0))
    slot.apply_transform(rot(HOME["phi"], [0, 0, 1]))
    slot.apply_translation([hx, hy_, 0])
    tools.append(slot)
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
    # a skin across the bore where the hex pocket's roof bridges it: the
    # face the screw's head pulls up against
    z0 = L["base_top"] - BASE_T + MOUNT_POCKET
    return _membrane(s, [cyl(MOUNT_BORE_R + 0.2, z0, z0 + MEMBRANE, 0, 0, 48)])


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
    return polar(GENEVA_AT, GENEVA_PHI), u, t


def driver_levels(specimen=SPECIMEN):
    """Heights up the drive, from the lip to the top of the motor."""
    L = levels(specimen)
    c0 = L["ring_bot"] + LIP_T + LIP_GAP              # crank underside
    c1 = c0 + CRANK_T
    floor_lo = c1 + FLOOR_GAP                         # the block's floor
    face = floor_lo + FLOOR_T                         # gearmotor faceplate
    top = face + MOTOR["gearbox"] + MOTOR["body"] + MOTOR["enc"]  # its plug
    return dict(lock_lo=L["ring_bot"] - 0.3, crank_lo=c0, crank_hi=c1,
                pin_lo=c1 - PIN_L, floor_lo=floor_lo, face=face,
                shaft_tip=face - MOTOR["shaft_l"], motor_top=top,
                cap_top=top + CAP_T, base_top=L["base_top"])


def _local(m):
    """Built in the driver's frame -- x out from the rotor axis, y across,
    origin on the driver's axis -- and carried into the world."""
    o, _, _ = _driver_frame()
    m.apply_transform(rot(GENEVA_PHI, [0, 0, 1]))
    m.apply_translation([o[0], o[1], 0])
    return m


def _dshaft_cut(d, flat, z0, z1):
    """A D-shaped hole: a circle of diameter d with a flat `flat` across
    from it, the flat facing +y in the driver's frame."""
    c = cyl(d / 2, z0, z1, 0, 0, 64)
    keep = box((-d, -d, z0 - 1), (d, flat - d / 2, z1 + 1))
    return trimesh.boolean.intersection([c, keep], engine="manifold")


def driver(specimen=SPECIMEN):
    """Crank and lock in one piece, pressed onto the gearmotor's D-shaft.

    Printed crank-top down: the D-bore opens on the plate and the lock
    rises off the crank's underside, so nothing overhangs. The pin goes
    through the whole 8 mm of crank."""
    Z = driver_levels(specimen)
    o, u, _ = _driver_frame()
    lock = trimesh.creation.extrude_polygon(geneva_lock_2d(),
                                            Z["crank_lo"] - Z["lock_lo"] + 0.01)
    # drawn on the axis the lip was cut for; carried to where the driver is
    shift = np.r_[(o - polar(GENEVA_C, GENEVA_PHI))[:2], 0.0]
    lock.apply_translation(shift + np.r_[0, 0, Z["lock_lo"]])
    # A fillet at the lock's root. The lock is loaded across its layers
    # whenever the ring is pushed at a stop, and a sharp printed corner is
    # where it would crack. Stepped down from the crank's underside, it
    # stays well above anything the lip reaches: the lip's top is LIP_GAP
    # below the crank, the fillet LOCK_FILLET.
    fl = []
    steps_ = 3
    for k in range(steps_):
        grow = LOCK_FILLET * (steps_ - k) / steps_
        g = geneva_lock_2d().buffer(grow, quad_segs=16)
        sl = trimesh.creation.extrude_polygon(g, LOCK_FILLET / steps_ + 0.01)
        sl.apply_translation(shift + np.r_[0, 0, Z["crank_lo"] - LOCK_FILLET * (k + 1) / steps_])
        fl.append(sl)
    lock = union([lock] + fl)
    crank = cyl(CRANK_R, Z["crank_lo"], Z["crank_hi"], o[0], o[1], 96)
    # turned half a facet, so no vertex of its rim sits on the set screw's
    # axis: one there left the screw's hole two zero-length edges
    crank.apply_transform(rot(180.0 / 96, [0, 0, 1], origin=[o[0], o[1], 0]))
    d = union([crank, lock])
    pin = o - u * GENEVA_A
    # Both bores open on the plate, where the first layer squashes out
    # and would close their mouths: a lead-in on each. Each bore and its
    # lead-in is one lofted solid -- a separate cone unioned onto a bore
    # left zero-length edges where the two met. The shaft and the pin
    # both enter from this side.
    # deep enough that the shaft's tip never bottoms: the shim sets the
    # driver's height, not the shaft's length
    z0, zj, zt = Z["shaft_tip"] - 0.8, Z["crank_hi"] - DRIVER_LEADIN, Z["crank_hi"] + 0.5
    rs = MOTOR["shaft_d"] / 2
    rc = rs + DBORE_CLR / 2
    flat = MOTOR["shaft_flat"] - rs + DBORE_CLR / 2
    ang = np.linspace(np.pi - np.arcsin(flat / rc), 2 * np.pi + np.arcsin(flat / rc), 48)
    d_pts = [(rc * np.cos(a_), rc * np.sin(a_)) for a_ in ang]
    # 45 degrees: the flare grows as far as it rises
    bore = _local(_funnel(d_pts, z0, zj, zt, (rc + zt - zj) / rc))
    rp = PIN_R + PIN_PRESS / 2
    c_pts = [(rp * np.cos(a_), rp * np.sin(a_))
             for a_ in np.linspace(0, 2 * np.pi, 48, endpoint=False)]
    pin_hole = _funnel(c_pts, Z["crank_lo"] - 1, zj, zt, (rp + zt - zj) / rp)
    pin_hole.apply_translation([pin[0], pin[1], 0])
    # the set screw: across from the round side onto the flat (+y in the
    # driver's frame), through a nut dropped into a slot from the crank's
    # top -- the block's floor stands over the slot once it is fitted
    zm = (Z["crank_lo"] + Z["crank_hi"]) / 2
    yn = flat + 1.8
    hx = NUT_AF / np.sqrt(3) + 0.15
    slot = box((-hx, yn, zm - NUT_AF / 2 - 0.2), (hx, yn + NUT_T + 0.3, Z["crank_hi"] + 1))
    screw = cyl(1.65, flat - 0.5, CRANK_R + 1, 0, 0, 32)
    screw.apply_transform(rot(-90.0, [1, 0, 0]))
    screw.apply_translation([0, 0, zm])
    nut_cut = _local(union([slot, screw]))
    return cut(d, [pin_hole, bore, nut_cut])


def _funnel(pts, z0, zj, zt, k):
    """An outline star-shaped about the origin (CCW) as a straight bore from z0
    up to zj, then flaring to k times its size at zt: one closed solid."""
    P = np.asarray(pts, float)
    n = len(P)
    rings = [np.c_[P, np.full(n, z0)], np.c_[P, np.full(n, zj)],
             np.c_[P * k, np.full(n, zt)]]
    V = np.vstack(rings + [[0, 0, z0], [0, 0, zt]])
    F = []
    for i in range(2):
        for j in range(n):
            a_, b_ = i * n + j, i * n + (j + 1) % n
            F += [[a_, b_, b_ + n], [a_, b_ + n, a_ + n]]
    cb, ct = 3 * n, 3 * n + 1
    for j in range(n):
        F.append([cb, (j + 1) % n, j])
        F.append([ct, 2 * n + j, 2 * n + (j + 1) % n])
    m = trimesh.Trimesh(V, np.array(F), process=True)
    m.fix_normals()
    return m


def _block_dims():
    """The block's extent in the driver's frame: inward x, outward x, and
    half its width across -- set by the encoder end, the widest part."""
    ed = (MOTOR["enc_d"] + POCKET_ENC) / 2
    ew = (MOTOR["enc_w"] + POCKET_ENC) / 2
    return ed + WALL_IN, ed + WALL_OUT, ew + WALL_SIDE


def _footprint():
    """The block and tower together, in plan, local frame."""
    xin, xout, by = _block_dims()
    px = POST_R - GENEVA_C
    return unary_union([Polygon([(-xin, -by), (xout, -by), (xout, by), (-xin, by)]),
                        Polygon([(px - POST_X / 2, -POST_Y / 2), (-xin + 1.0, -POST_Y / 2),
                                 (-xin + 1.0, POST_Y / 2), (px - POST_X / 2, POST_Y / 2)])])


# A hole that opens through a bridge prints its edge as loops over air,
# and that edge is the fit. So a one-layer skin closes the hole where the
# bridge is printed: the bridge lays down whole, the hole goes on above
# it, and the skin is pushed out with a drill after printing. The skins
# are in the printed file and nowhere else: the assembled jig has none,
# so the sweeps and fits never see them.
MEMBRANE = 0.2          # one layer


def _membrane(m, skins):
    """Attach skins to a part: printed, never assembled."""
    m.metadata["membranes"] = skins
    return m


def printed(name, m):
    """The part as it prints: with its skins."""
    sk = m.metadata.get("membranes")
    return union([m] + sk) if sk else m


def drive_block(specimen=SPECIMEN):
    """The gearmotor's housing on its post: a slip-fit pocket stepped out
    for the encoder, a floor the gearbox's bushing centres in, one solid
    tower down to a post keyed into the base, the cable's bore and the
    screw's down it. Printed on its side: every face square to the plate,
    the pocket a tunnel with a 13 mm bridge for its roof."""
    Z = driver_levels(specimen)
    xin, xout, by = _block_dims()
    px = POST_R - GENEVA_C
    hx, hy = POST_X / 2, POST_Y / 2
    blk = box((-xin, -by, Z["floor_lo"]), (xout, by, Z["motor_top"]))
    tower = box((px - hx, -hy, Z["floor_lo"]), (-xin + 1.0, hy, Z["motor_top"]))
    post = box((px - hx, -hy, Z["base_top"] - POST_SOCKET),
               (px + hx, hy, Z["floor_lo"] + 0.5))
    b = union([blk, tower, post])
    pw, pd = (MOTOR["w"] + POCKET_GB) / 2, (MOTOR["d"] + POCKET_GB) / 2
    ew, ed = (MOTOR["enc_w"] + POCKET_ENC) / 2, (MOTOR["enc_d"] + POCKET_ENC) / 2
    enc0 = Z["face"] + MOTOR["gearbox"] + MOTOR["body"] - 0.5
    low = Z["base_top"] - POST_SOCKET - 1
    tools = [box((-pd, -pw, Z["face"]), (pd, pw, Z["motor_top"] + 1)),
             box((-ed, -ew, enc0), (ed, ew, Z["motor_top"] + 1)),
             cyl((MOTOR["bush_d"] + BUSH_FIT) / 2, Z["floor_lo"] - 1, Z["face"] + 1,
                 0, 0, 48),
             # the post's screw: its head seats at the floor's top, reached
             # down an access bore from the top
             cyl(1.7, low, Z["face"] + 0.01, px, SCREW_Y, 32),
             cyl(3.25, Z["face"], Z["motor_top"] + 1, px, SCREW_Y, 48),
             # the cable's bore, top to bottom
             cyl(CABLE_R + 0.6, low, Z["motor_top"] + 1, px, CABLE_Y, 48)]
    # the plug's channel: out of the encoder's pocket through the inner
    # wall, open at the top so the plug drops in with the motor; it stops
    # short of the screw's access bore and a slot carries the cable on
    # into its own
    x_end, x1, pyw, pz0 = _channel(Z)
    tools.append(box((x_end, -pyw, pz0), (x1, pyw, Z["motor_top"] + 1)))
    tools.append(box((px, CABLE_Y - CABLE_R - 0.6, pz0),
                     (x_end + 0.5, CABLE_Y + CABLE_R + 0.6, Z["motor_top"] + 1)))
    # skins where the floor's first layer bridges the pocket: across the
    # bushing's hole, and across the screw's bore under its head
    skins = [cyl((MOTOR["bush_d"] + BUSH_FIT) / 2 + 0.2, Z["face"] - MEMBRANE, Z["face"],
                 0, 0, 48),
             cyl(3.4, Z["face"] - MEMBRANE, Z["face"], px, SCREW_Y, 48)]
    blk_ = _local(cut(b, tools))
    return _membrane(blk_, [_local(trimesh.boolean.intersection(
        [sk, b], engine="manifold")) for sk in skins])


def _plug_z(Z):
    """The side plug's height: the middle of the encoder end."""
    return Z["motor_top"] - MOTOR["enc"] / 2


def _channel(Z):
    """The plug's channel in the driver's frame: x from, x to, half its
    width across, and its floor."""
    ed = (MOTOR["enc_d"] + POCKET_ENC) / 2
    return (-ed - MOTOR["plug"][0] - SLIP, -ed + 0.5,
            MOTOR["plug"][1] / 2 + SLIP, _plug_z(Z) - MOTOR["plug"][2] / 2 - SLIP)


def drive_cap(specimen=SPECIMEN):
    """The lid: a flat plate over the block, the tower and the plug's
    channel, pressed on -- a peg in the screw's access bore, a key in the
    channel's top, both at the shop's press fit. The key sits on the plug
    and keeps it home. Printed upside down, peg and key up."""
    Z = driver_levels(specimen)
    px = POST_R - GENEVA_C
    lid = trimesh.creation.extrude_polygon(_footprint(), CAP_T)
    lid.apply_translation([0, 0, Z["motor_top"]])
    x0, x1, hw, _ = _channel(Z)
    # the key and the peg, each a little over its printed bore: PETG
    # yields into a light press rather than cracking. Nothing pulls on the
    # lid; the plug is held by the channel's end wall, not by the key
    k0, k1 = x0 + 0.05, -(MOTOR["enc_d"] + POCKET_ENC) / 2 - 0.2
    kz0, kz1 = Z["motor_top"] - KEY_D, Z["motor_top"] + 0.5
    key = box((k0, -hw - LID_PRESS / 2, kz0), (k1, hw + LID_PRESS / 2, kz1))
    pg = Point(0, 0).buffer((6.5 + LID_PRESS) / 2, quad_segs=24)
    peg = trimesh.creation.extrude_polygon(pg, 3.5)
    peg.apply_translation([px, SCREW_Y, Z["motor_top"] - 3.0])
    # the encoder's magnet disc spins on the back of the motor, right
    # under the lid: a recess over it rather than trusting the last half
    # millimeter of the drawing
    return _local(cut(union([lid, key, peg]),
                      [cyl(5.0, Z["motor_top"] - 1.0, Z["motor_top"] + 1.0, 0, 0, 48)]))


def driver_shim(specimen=SPECIMEN):
    """The 0.6 mm fork slid between the crank and the block's floor while
    the driver is pressed up its shaft, then pulled out: it is what sets
    the crank's height. A tool, printed with the set and never fitted."""
    Z = driver_levels(specimen)
    g = Polygon([(-3, -5), (24, -5), (24, 5), (-3, 5)]).difference(
        Polygon([(-4, -1.7), (1.7, -1.7), (1.7, 1.7), (-4, 1.7)]))
    m = trimesh.creation.extrude_polygon(g, FLOOR_GAP)
    m.apply_translation([0, 0, Z["crank_hi"]])
    return _local(m)


def motor_prims(specimen=SPECIMEN):
    """The gearmotor as the sweeps and pages see it: gearbox and motor,
    the encoder end, the gearbox's bushing, the D-shaft."""
    Z = driver_levels(specimen)
    o, _, _ = _driver_frame()
    M = np.eye(4)
    M[:3, 3] = [o[0], o[1], 0]
    M = (M @ rot(GENEVA_PHI, [0, 0, 1])).ravel().tolist()
    w, d = MOTOR["w"] / 2, MOTOR["d"] / 2
    e0 = Z["face"] + MOTOR["gearbox"] + MOTOR["body"]
    g1 = Z["face"] + MOTOR["gearbox"]
    # the gearbox's plates are a 10 x 12 rectangle; the motor's can is
    # round, Ø12, with two flats 10 apart
    return [dict(kind="box", lo=[-d, -w, Z["face"]], hi=[d, w, g1], M=M),
            dict(kind="cyl", c=[0, 0, (g1 + e0) / 2], axis=[0, 0, 1], r=w,
                 h=e0 - g1, flats=d, M=M),
            dict(kind="box", lo=[-MOTOR["enc_d"] / 2, -MOTOR["enc_w"] / 2, e0],
                 hi=[MOTOR["enc_d"] / 2, MOTOR["enc_w"] / 2, Z["motor_top"]], M=M),
            dict(kind="cyl", c=[0, 0, Z["face"] - MOTOR["bush_h"] / 2],
                 axis=[0, 0, 1], r=MOTOR["bush_d"] / 2, h=MOTOR["bush_h"], M=M),
            dict(kind="cyl", c=[0, 0, Z["face"] - MOTOR["shaft_l"] / 2],
                 axis=[0, 0, 1], r=MOTOR["shaft_d"] / 2, h=MOTOR["shaft_l"],
                 flat=MOTOR["shaft_flat"], M=M),
            # the encoder's side connector with the cable's plug in it
            dict(kind="box", lo=[-MOTOR["enc_d"] / 2 - MOTOR["plug"][0],
                                 -MOTOR["plug"][1] / 2, _plug_z(Z) - MOTOR["plug"][2] / 2],
                 hi=[-MOTOR["enc_d"] / 2, MOTOR["plug"][1] / 2,
                     _plug_z(Z) + MOTOR["plug"][2] / 2], M=M)]


# --- the controller and its cable ---------------------------------------
# Everything that carries a wire stands still: the gearmotor and both
# sensors are on the stator, so no cable winds as the ring turns. One
# 6-pin cable (motor +/-, encoder VCC, A, B, GND) leaves the drive
# down its post, runs under the base in the gap the pucks
# leave, and out across the board to a box beside the jig. One USB-C cord
# from a 5 V wall adapter powers the controller, the H-bridge and the
# motor. The phone runs on its own battery: it rides the ring, and the
# capture turns the ring four times over.
# Seeed XIAO ESP32S3: board length, width and thickness, measured off
# Seeed's own STEP model (Seeed states only 21 x 17.8)
XIAO = (20.96, 17.78, 1.25)
# Pololu #2130 DRV8833 carrier, from Pololu's dimension drawing and STEP
DRV8833 = (12.7, 20.32, 1.57)
CTRL = dict(r=175.0, phi=15.0, l=64.0, w=40.0, h=20.0, wall=2.0, lid=2.0)
# One USB-C cord, into the XIAO, which powers everything. Its 5 V pin is
# its USB VBUS, and Seeed asks for no more than 500 mA through it. Pololu
# puts this gearbox's instantaneous torque limit at 2 kg.cm and asks for
# continuous current under a quarter of stall; unlimited, a jam at 5 V
# drives about 1.07 A and 2.6 kg.cm into it (and into the PETG slot and
# the D-flat). A 4.7 ohm resistor in series with the motor holds a stall
# to about 0.53 A and 1.15 kg.cm whatever the firmware is doing -- still
# 2.8 times the worst the ring asks -- and the motor runs at full drive
# with no PWM, so nothing switches beside the encoder's wires. Running it
# draws about 0.2 A; the whole jig, about 0.35 A, and 0.7 A in a jam.
MOTOR_R_ITEM = "4.7 ohm 2 W resistor (in series with the motor)"
MOTOR_R = 4.7
CAP_ITEM = "100 uF 16 V electrolytic capacitor"
PULLUP_ITEM = "10 kohm resistor (home sensor pull-up)"
XIAO_Y = 0.0                       # where the XIAO sits across the box
CABLE_R = 1.3                     # Pololu's cable: six loose 28 AWG wires
LEAD_R = 0.9                      # the home sensor's three-wire lead
CABLE_DY, LEAD_DY = 1.8, -2.2     # where each comes through the box's inlet
CABLE_ITEM = ("Pololu 6-pin JST SH cable, single-ended female, 75 cm "
              "(six 28 AWG)")
CTRL_INLET_Y = -12.0              # off centre: clear of the lid's boss
# The lid presses on with two pegs: bore and peg diameters, and the peg's
# length. Drawn a slip, because a hole this small prints about 0.2 under
# its size -- drawn at the drive lid's press it came out 4.6% too tight to
# push home; drawn so, it prints at that lid's own -0.19. Nothing pulls on
# this lid; it only has to stay put and come off for the wiring.
# 24.0.0: Brett's printed pegs would not go into the bosses at all, at
# 0.05 under the bore. 0.35 under now, biased loose: a lid that sits a
# little free still covers the box and lifts off for the wiring; one that
# will not go on is a reprint.
# 25.0.0: 0.5 under, because the tolerance model still gave 2.25 a 5%
# chance of a peg that will not go in -- and that model passed the 2.55.
# 27.0.0: Brett's 2.1 pegs went in and sat loose, so the two prints
# bracket it -- 2.55 would not go in, 2.1 is free -- and 2.25 is between,
# toward the end that went on (2.3 the model calls tight in 1 print in
# 125). 30% longer, 5.2, for more grip.
# 30.0.0: the 2.25 pegs held the lid on at a perfect friction fit, and one
# snapped off at its root the first time the lid came off: a thin PETG
# peg printed upright, its layers across it. A peg that is pulled and
# levered gets 3.5 at least (bending goes as d^3: 3.8x the 2.25), a fillet
# at its root and a chamfer at its tip, and the fit comes from the bore --
# the same 0.35 the 2.25 had in its 2.6. The boss grows with it, 1.3 of
# wall round the bore, and sits 0.5 deeper into its corner so the tray's
# notch round it still clears R1.
CTRL_PEG = (3.85, 3.5, 5.2)
CTRL_PEG_FILLET, CTRL_PEG_TIP = 0.6, 0.4
CTRL_BOSS_R = 3.2
_BOSS_IN = CTRL["wall"] + 1.5
CTRL_BOSSES = ((-CTRL["l"] / 2 + _BOSS_IN, CTRL["w"] / 2 - _BOSS_IN),
               (CTRL["l"] / 2 - _BOSS_IN, -CTRL["w"] / 2 + _BOSS_IN))


def _ctrl_frame(specimen=SPECIMEN):
    L = levels(specimen)
    board = L["base_bot"] - PUCK_H
    o = polar(CTRL["r"], CTRL["phi"])
    return o, board


def _ctrl_local(m, specimen=SPECIMEN):
    o, board = _ctrl_frame(specimen)
    m.apply_transform(rot(CTRL["phi"], [0, 0, 1]))
    m.apply_translation([o[0], o[1], board])
    return m


def ctrl_box(specimen=SPECIMEN):
    """On the board beside the jig, glued down with the epoxy that holds
    the pucks. The XIAO's USB-C faces outward through the wall; the
    jig's cable comes in through the inner wall past a bar it is tied
    to."""
    l, w, h, t = CTRL["l"], CTRL["w"], CTRL["h"], CTRL["wall"]
    b = box((-l / 2, -w / 2, 0), (l / 2, w / 2, h))
    # the lid's bosses run into the walls: tangent to them, the faces fold
    # into non-manifold edges on the way out to the 3MF
    bosses = [cyl(CTRL_BOSS_R, t - 0.5, h, x, y, 48) for x, y in CTRL_BOSSES]
    tools = [box((-l / 2 + t, -w / 2 + t, t), (l / 2 - t, w / 2 - t, h + 1))]
    b = cut(b, tools)
    b = union([b] + bosses)
    cut2 = []
    # The boards are held by the tray (ctrl_tray), not the box. Until
    # 25.0.0 this cut two "cradles" into the floor -- from the floor's top
    # surface up, into a box already hollow there, so they removed 0.01
    # mm and held nothing. The opening in the outer wall takes the USB-C
    # plug's overmold (12.35 x 6.5 at most, by the USB-C spec), not just
    # the receptacle: through a 2 mm wall a receptacle-sized hole stopped
    # the overmold with the plug 4.6 of its 6.6 mm in.
    uz = t + 1.0 + 3.26 / 2
    cut2.append(box((l / 2 - t - 0.5, XIAO_Y - 6.4, uz - 3.5),
                    (l / 2 + 1, XIAO_Y + 6.4, uz + 3.5)))
    # the cable's way in, low on the inner wall, and the tie bar beside it
    cut2.append(box((-l / 2 - 1, CTRL_INLET_Y - 3.5, t),
                    (-l / 2 + t + 1, CTRL_INLET_Y + 3.5,
                     t + INLET_TRAY_T + 1.4 + CABLE_R + 0.2)))
    # the lid's pegs press into the bosses, printed into printed like the
    # drive's lid
    # and a 45-degree mouth, the lead-in, which also clears the peg's fillet.
    # Its facets must not line up with the boss's and bore's 48: at 48 the
    # three meet the top face in slivers the 3MF folds non-manifold.
    mouth = CTRL_PEG[0] / 2 + CTRL_PEG_FILLET + 0.2
    for x, y in CTRL_BOSSES:
        cut2.append(cyl(CTRL_PEG[0] / 2, h - CTRL_PEG[2] - 2.0, h + 1, x, y, 48))
        cut2.append(cone(mouth + 1.0, h + 1.0, h - mouth, x, y, 64))
    return _ctrl_local(cut(b, cut2), specimen)


def ctrl_lid(specimen=SPECIMEN):
    l, w, h = CTRL["l"], CTRL["w"], CTRL["h"]
    lid = box((-l / 2, -w / 2, h), (l / 2, w / 2, h + CTRL["lid"]))
    r, f, c = CTRL_PEG[1] / 2, CTRL_PEG_FILLET, CTRL_PEG_TIP
    z0 = h - CTRL_PEG[2]
    # turned from its profile: chamfered tip, straight shank, a 45-degree
    # fillet into the lid's underside
    prof = [(0, z0), (r - c, z0), (r, z0 + c), (r, h - f), (r + f, h),
            (r + f, h + 0.5), (0, h + 0.5)]
    pegs = []
    for x, y in CTRL_BOSSES:
        p = trimesh.creation.revolve(prof, sections=48)
        p.apply_translation([x, y, 0])
        pegs.append(p)
    return _ctrl_local(union([lid] + pegs), specimen)


# --- the controller's tray and its wiring --------------------------------
# Everything here is in the box's own frame: x along it toward the wall the
# USB-C goes out through, y across, z up from the board it is glued to.
#
# The boards and the parts with legs sit in a printed tray on the box's
# floor, laid out like a circuit board: the XIAO in a window the shape of
# its board, the DRV8833 on the plate with a slot under each row of holes,
# and every part with legs in a saddle the shape of its body, its legs
# down through holes. The nets that are not on a board are made under the
# plate: each wire comes down through its own hole beside the net's name,
# runs in a groove underneath, and meets the others in the net's pocket.
# The grooves are the circuit's traces, cut into the face that prints on
# the bed, with each net's name beside its pocket, mirrored so it reads
# with the tray turned over. Every name on the top is cut in too: raised
# letters 3.6 tall printed as blobs (Brett's first and second trays).
#
# Each joint is still made off the plastic: the wires' ends twisted under
# the tray, lifted clear with tweezers, soldered, and pressed into the
# pocket when cool. Two legs end on the DRV8833 itself -- the 4.7 ohm's
# into AOUT1 and the 5 V wire into VIN -- each along a groove and up
# through the slot under that row, soldered on the board's top.
#
# The plate is 3.0, its pockets 2.0 deep under it. The 100 uF stands on
# the DRV8833, now 2 mm off it with its top 0.4 under the lid; the 5 V
# wire, which passed under it, comes into VIN from below.
TRAY_T = 3.0            # the plate, on the box's floor (2.0 until 42.0.0)
# The box's inlet and where the cables come through it were drawn for a
# 2.0 plate, and the box is printed and glued down: they stay there, and
# the plate is cut away round them.
INLET_TRAY_T = 2.0
TRAY_GAP = 0.3          # all round inside the box's walls and bosses
TRAY_FIT = 0.25         # each board's window, per side
# The tray's notches round the lid's two bosses: a snug fit, so the
# bosses, in opposite corners, wedge the tray and it stays put unglued.
# Until 30.0.0 it was 0.4 per side and the tray sat loose.
TRAY_BOSS_FIT = 0.15
# The first print (26.0.0) drew its labels in bold Arial 2.8 tall, 0.4
# proud: a smear. 30.0.0 drew raised block letters 3.6 tall in 0.8
# strokes, and those printed as blobs too: every stroke a small island
# the nozzle starts and stops on. Cut into the plate, the letters are
# holes the top layers go round, and they print as clean as the outline.
TRAY_CAP = 4.2          # a block letter's height
TRAY_LINE = 0.9         # every stroke: a letter, a symbol
TRAY_CUT = 0.6          # how deep they are cut, top and underside
# Under the plate: a groove the width of one wire or leg, and a pocket
# for each net's joint (a twist of up to four 28 AWG ends, soldered).
GROOVE = (1.4, 1.0)     # width, depth
POCKET = (4.4, 2.0)     # diameter, depth
HOLE_WIRE = 1.6         # a 28 AWG wire, 0.8 over its insulation, prints ~1.4
DRV_RIM = (1.0, 1.2)    # the wall round the DRV8833: thickness, height
DRV_SLOT = 2.0          # the slot under each of its rows of holes, through
# The boards clip in. Each hook is on an arm cut free of the plate by a
# slot, and the arm bends sideways, in the plate's own plane, to let the
# board past: along its layers, never across them as a peg standing up
# from the plate would (the lid's 2.1 pegs snapped at the root that way).
# A hook's bend is 1.5 t d / L^2 of strain on an arm t thick and L long
# moved d; every arm here stays under 2%. Each board tucks one edge under
# a fixed lip and clips down past an arm's hook. The XIAO tucks its -y
# edge under a lip beside the USB-C, in the 2 mm there before the first
# pad (a slot on that side would run through the GND name), and clips at
# its far end and its +y edge. The DRV8833 tucks its +y end and clips at
# its -y end, on the 0.75 of board its parts and pads leave there.
#
# The boards are not all the size they are drawn. Pololu's drawing gives
# the DRV8833's board edges +-0.3 (so 12.1-13.3 by 19.7-20.9) and its
# board 1.57 thick; Seeed gives the XIAO as 21 x 17.8 and nothing more,
# its STEP 20.95 x 17.78 x 1.25, and its KiCad board 1.6 thick -- taken
# here as +-0.2 on each size and up to 1.6 thick. So each board is pressed
# against one fixed wall, under its lip, and the arm across from it stands
# where a nominal board's edge is: a large board pushes the arm back and
# is held all the same, a small one has room to slide only less than the
# hooks reach. Every hook stands clear over the thickest board.
XIAO_TOL = 0.2          # on its length and width
XIAO_T_MAX = 1.6
DRV_EDGE_TOL = 0.3      # on each edge, Pololu's drawing
SEAT = 0.05             # a nominal board to the walls that hold it
LATCH_T = 1.0           # each arm, across its bend
LATCH_SLOT = 1.0        # behind the arm: room for the hook to go back
LATCH_SPLIT = 0.5       # the cut that frees the arm from the plate
HOOK = 0.75             # how far a hook reaches in from its wall
HOOK_OVER = 0.15        # its underside over the thickest board's top
HOOK_FLAT = 0.25        # the flat at its nose, below the lead-in
XIAO_END_HOOK = 0.9     # the far end's: its window is 0.25 long, and in
                        # the box the USB-C end has 0.2 to the wall
# The DRV8833 can be 1.2 shorter than the longest: more than one hook
# reaches, so its fixed lip reaches 1.4 (its parts start 2.1 in from that
# end) and its arm stands 0.2 inside a nominal board's edge.
DRV_LIP_X = (-17.5, -10.5)       # the fixed lip, at the +y end, clear of FLT's wire
DRV_LIP = 1.4
DRV_HOOK = 0.85
DRV_PRELOAD = 0.2
DRV_HOOK_X = (-13.3, -10.2)      # its hook, at the -y end: clear of the
                                 # bulk capacitor and the pads
DRV_ARM_X = (-17.6, -9.0)        # the arm the hook is on, root to tip
DRV_ARM_T = 0.8                  # thinner: the longest board puts it back 1.55
DRV_ARM_SLOT = 1.7
XIAO_END_ARM_Y = (0.4, 3.4)      # the far-end hook, along the arm's tip
XIAO_SIDE_ARM_X = (19.7, 27.8)   # the side arms' root, and where the hook starts
WIRE_R = 0.4            # Pololu's 28 AWG: JST SH takes insulation 0.8 at
                        # most, so no fatter than that (Pololu gives none)
PITCH = 2.54
# The XIAO's castellated pads, measured off Seeed's STEP: 7 to an edge,
# the first 2.92 from the USB end. Seeed's pinout, viewed from the top
# with the USB-C away from you: D0..D6 down the left edge, 5V, GND, 3V3,
# D10..D7 down the right. With the USB-C toward +x that left edge is +y.
XIAO_PAD0 = 2.92
XIAO_X1 = CTRL["l"] / 2 - CTRL["wall"] - 0.2    # its USB end, at the wall
XIAO_EDGE = {1: ("D0", "D1", "D2", "D3", "D4", "D5", "D6"),
             -1: ("5V", "GND", "3V3", "D10", "D9", "D8", "D7")}
# The DRV8833 carrier's two rows of 8, 10.16 apart, read off the
# silkscreen in Pololu's drawing; GND is the square pad at one end of
# both. With its parts up and the power row toward -x (the cable's side),
# that GND end is -y.
DRV_C = (-14.0, 0.0)
DRV_ROWS = {"power": (-1, ("GND", "VIN", "BOUT1", "BOUT2", "AOUT2", "AOUT1",
                           "AISEN", "BISEN")),
            "logic": (1, ("GND", "VMM", "BIN1", "BIN2", "AIN2", "AIN1",
                          "SLP", "FLT"))}
# Its parts, from Pololu's STEP: (x0, y0, x1, y1, height above the board)
# in the board's own frame, which the box's turns by 180 degrees
DRV_PARTS = ((4.86, 7.52, 8.86, 11.53, 1.03, "ic"),          # the DRV8833
             (7.45, 14.25, 8.85, 17.25, 1.20, "ic"),         # reverse FET
             (3.82, 15.84, 5.62, 17.19, 1.10, "ic"),
             (6.25, 17.77, 9.65, 19.57, 1.80, "ceramic"),    # bulk capacitor
             (3.19, 17.81, 4.94, 18.76, 0.65, "ceramic"),
             (7.51, 12.99, 9.26, 13.94, 0.65, "ceramic"),
             (3.21, 2.17, 4.16, 3.92, 0.65, "ceramic"),
             (2.98, 5.63, 3.88, 7.33, 0.90, "ceramic"),
             (2.85, 9.82, 3.75, 11.52, 0.90, "ceramic"),
             (3.59, 14.54, 5.30, 15.44, 0.90, "ceramic"))
# Stackpole's and Panasonic's drawings: body length, diameter, lead.
# Body colors are the usual ones for these lines, not from a datasheet.
R1_DIM = (11.0, 4.5, 0.8)        # RSMF2JT4R70, 4.7 ohm 2 W
R2_DIM = (6.0, 2.3, 0.55)        # CF14JT10K0, 10 kohm
# the longest body each drawing allows (RSMF2 11.0 +-1.5, CF14 6.0 +-0.3):
# a saddle shorter than its body would hold the body up off its seat. A
# fatter body (RSMF2 4.5 +-1.0) only sits higher in it.
R1_MAX_L, R2_MAX_L = 12.5, 6.3
C1_DIM = (5.0, 11.0, 2.0, 0.5)   # EEU-FR1C101: dia, height, lead pitch, lead
C1_STANDOFF = 2.0                # off the DRV8833's parts, under the lid
# The two resistors lie in saddles, their legs bent down at BEND past the
# body's end into holes drawn LEAD_HOLE over the leg.
BEND = 2.05
LEAD_HOLE = 0.6
R1_AT = ((-13.95, 14.55), "x", 1.5)        # its centre, its axis, saddle depth
R2_AT = ((1.0, -2.85), "y", 0.8)
INLET_X = -CTRL["l"] / 2 + 4.0             # where the cables' wires fan out
# where each cable's wires rise from it, clear of the marks beside them
RISE_X = {"cable": -27.6, "lead": -26.6}
# The nets made under the plate: where each one's pocket is, the holes its
# wires come down through (in the order WIRES numbers them), where its
# name is cut on top and how it is turned.
NETS = {
    "M1": dict(pocket=(-4.0, 14.55), holes=((-0.6, 14.55),),
               name=(10.0, 14.4, 0.0), under=(3.5, 13.5, 0.0)),
    "3V3": dict(pocket=(-3.4, -9.0), holes=((-3.8, -11.7), (-1.6, -11.7), (2.8, -11.7)),
                name=(2.4, -15.1, 0.0), under=(6.1, -7.4, 90.0)),
    "D5": dict(pocket=(-3.4, 3.6), holes=((-3.4, 8.0), (3.6, 6.0)),
               name=(1.6, 11.2, 0.0), under=(4.1, 1.4, 90.0, 3.6)),
    "GND": dict(pocket=(14.0, -14.4), holes=((9.6, -16.1), (11.6, -16.1),
                                             (16.4, -16.1), (18.4, -16.1)),
                name=(21.0, -12.0, 0.0), under=(21.4, -11.9, 0.0, 3.6)),
}
# the 5 V wire's way into VIN from below: down here, along, up the slot
VIN_HOLE = (-22.8, -12.4)
# what else is cut on top: the parts' values, the 100 uF's polarity
VALUES = (("4.7\u03a9", (-25.6, 6.5), 90.0),       # beside R1's leg, up the left side
          ("10K", (5.4, -5.1), 90.0),        # below the XIAO's far-end arm
          ("100\u00b5F", (-13.4, -15.17), 0.0, 3.6))   # short of the DRV8833's clip   # under the DRV8833, where it stands

# Every wire inside the box: its color, the net, the two ends, the step
# that solders it, the height it runs at over the tray's plate (so a
# thicker plate carries every wire up with it) and the corners of its run. The
# motor's cable keeps all six of its own wires; the 38 cm cut off its far
# end gives the home sensor's three (blue, green and white: the colors of
# the motor-cable wires on the same nets) and the rest are the jumpers
# between the boards, colored by what they carry -- red 5 V, black
# ground, blue 3V3, yellow the XIAO's signals out.
# Ends: ("cable", k) and ("lead", k) where they come in, k their place in
# the bundle; ("xiao", pad); ("drv", row, pin) from above, ("under", row,
# pin) up through the slot from its own hole; ("hole", net, k) down the
# net's k-th hole into its pocket.
WIRES = (
    ("W1", "red", "M1", ("cable", 5), ("hole", "M1", 0), "j_m1", 6.3,
     ((-27.6, 10.6), (-1.4, 10.6))),
    ("W2", "black", "M2", ("cable", 4), ("drv", "power", "AOUT2"), "motor_wires", 4.3,
     ((-27.6, 1.27),)),
    ("W3", "yellow", "encoder A", ("cable", 2), ("xiao", "D3"), "motor_wires", 7.3,
     ((-27.6, 11.5), (19.26, 11.5))),
    ("W4", "white", "encoder B", ("cable", 1), ("xiao", "D4"), "motor_wires", 8.1,
     ((-27.6, 12.3), (16.72, 12.3))),
    ("W5", "blue", "3V3", ("cable", 3), ("hole", "3V3", 0), "j_home", 4.8,
     ((-27.6, -15.85),)),
    ("W6", "green", "GND", ("cable", 0), ("hole", "GND", 0), "j_gnd", 4.0,
     ((-27.6, -17.0), (12.4, -17.0))),
    ("W7", "blue", "3V3", ("lead", 0), ("hole", "3V3", 1), "j_home", 5.7,
     ((-26.6, -15.85),)),
    ("W8", "green", "GND", ("lead", 1), ("hole", "GND", 1), "j_gnd", 4.9,
     ((-26.6, -16.2), (12.4, -16.2))),
    ("W9", "white", "home", ("lead", 2), ("hole", "D5", 0), "j_home", 6.8,
     ((-26.6, 4.6),)),
    ("W10", "red", "5V", ("xiao", "5V"), ("under", "power", "VIN"), "jumpers", 8.8,
     ((26.88, -11.6), (-15.38, -11.6))),
    ("W11", "black", "GND", ("xiao", "GND"), ("hole", "GND", 2), "j_gnd", 3.8,
     ((24.34, -14.0),)),
    ("W12", "black", "GND", ("hole", "GND", 3), ("drv", "logic", "GND"), "j_gnd", 6.6,
     ((-8.92, -14.0),)),
    ("W13", "blue", "3V3", ("hole", "3V3", 2), ("xiao", "3V3"), "j_home", 6.0,
     ((21.8, -11.55),)),
    ("W14", "white", "home", ("hole", "D5", 1), ("xiao", "D5"), "j_home", 4.8,
     ((14.18, 7.8),)),
    ("W15", "yellow", "AIN1", ("xiao", "D0"), ("drv", "logic", "AIN1"), "jumpers", 9.6,
     ((26.88, 13.2), (-8.92, 13.2))),
    ("W16", "yellow", "AIN2", ("xiao", "D1"), ("drv", "logic", "AIN2"), "jumpers", 10.5,
     ((24.34, 14.0), (-8.92, 14.0))),
    ("W17", "yellow", "nFAULT", ("xiao", "D8"), ("drv", "logic", "FLT"), "jumpers", 7.8,
     ((6.0, -10.0), (6.0, 8.89))),
)
# Pololu's cable, pin 1 to 6 (and the encoder's pins, the same order)
CABLE_COLORS = ("green", "white", "yellow", "blue", "black", "red")


def _floor():
    return CTRL["wall"]


def _plate_top():
    return CTRL["wall"] + TRAY_T


def xiao_pad(name):
    """A XIAO pad: its centre on the board's edge, and which edge."""
    for s, names in XIAO_EDGE.items():
        if name in names:
            k = names.index(name)
            return np.array([XIAO_X1 - XIAO_PAD0 - PITCH * k, s * XIAO[1] / 2]), s
    raise KeyError(name)


def drv_hole(row, name):
    side, names = DRV_ROWS[row]
    k = names.index(name)
    return np.array([DRV_C[0] + side * 5.08, DRV_C[1] - 8.89 + PITCH * k])


def _drv_top():
    return _plate_top() + 0.02 + DRV8833[2]


def _net_hole(net, k):
    return np.asarray(NETS[net]["holes"][k], float)


def _under_z():
    """A wire's or a leg's centre in a groove under the plate."""
    return _floor() + GROOVE[1] / 2


def _part_axis(at):
    (cx, cy), ax, depth = at
    a = np.array([1.0, 0.0]) if ax == "x" else np.array([0.0, 1.0])
    return np.array([cx, cy], float), a, depth


def _lead_holes(at, dim):
    """The two holes a part's legs go down: BEND past each end of its body."""
    c, a, _ = _part_axis(at)
    d = dim[0] / 2 + BEND
    return c - a * d, c + a * d


def _part_z(at, dim):
    """The centre of a lying part's body, sat in its saddle."""
    return _plate_top() + dim[1] / 2 - _part_axis(at)[2]


def _routes():
    """Every groove under the plate, as (what, points): from each net's
    holes to its pocket, the 4.7 ohm's leg to the slot under AOUT1, the
    5 V wire's to the slot under VIN."""
    out = []
    for net, d in NETS.items():
        for k, h in enumerate(d["holes"]):
            out.append((f"{net} {k}", [tuple(h), tuple(d["pocket"])]))
    # each lying part's legs into the pockets of the nets they join
    for (at, dim), nets in (((R1_AT, R1_DIM), (None, "M1")),
                            ((R2_AT, R2_DIM), ("3V3", "D5"))):
        for h, net in zip(_lead_holes(at, dim), nets):
            if net:
                out.append((f"leg to {net}", [tuple(h), tuple(NETS[net]["pocket"])]))
    w1 = _lead_holes(R1_AT, R1_DIM)[0]
    ao = drv_hole("power", "AOUT1")
    out.append(("R1 to AOUT1", [tuple(w1), (w1[0], ao[1]), (ao[0], ao[1])]))
    vin = drv_hole("power", "VIN")
    out.append(("5V to VIN", [VIN_HOLE, (vin[0], VIN_HOLE[1]), (vin[0], vin[1])]))
    return out


# A block letter as strokes in a unit cell, x 0..1 across, y 0..1 up
# (the descender of a mu below 0). Three rows -- foot, middle, top -- so
# the gaps between strokes stay a full stroke wide or more at TRAY_CAP.
_BLOCK = {
    "0": [[(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]],
    "1": [[(0.2, 0.8), (0.55, 1), (0.55, 0)]],
    "3": [[(0, 1), (1, 1), (1, 0), (0, 0)], [(0.25, 0.5), (1, 0.5)]],
    "4": [[(0, 1), (0, 0.45), (1, 0.45)], [(0.75, 1), (0.75, 0)]],
    "5": [[(1, 1), (0, 1), (0, 0.5), (1, 0.5), (1, 0), (0, 0)]],
    "7": [[(0, 1), (1, 1), (0.45, 0)]],
    "D": [[(0, 0), (0, 1), (0.6, 1), (1, 0.65), (1, 0.35), (0.6, 0), (0, 0)]],
    "G": [[(1, 1), (0, 1), (0, 0), (1, 0), (1, 0.5), (0.45, 0.5)]],
    "N": [[(0, 0), (0, 1), (1, 0), (1, 1)]],
    "V": [[(0, 1), (0.5, 0), (1, 1)]],
    "M": [[(0, 0), (0, 1), (0.5, 0.45), (1, 1), (1, 0)]],
    "K": [[(0, 0), (0, 1)], [(1, 1), (0, 0.4)], [(0.35, 0.6), (1, 0)]],
    "F": [[(1, 1), (0, 1), (0, 0)], [(0, 0.5), (0.75, 0.5)]],
    "\u00b5": [[(0, -0.3), (0, 0.7)], [(0, 0), (1, 0), (1, 0.7)]],
    "\u03a9": [[(0, 0), (0.3, 0), (0.3, 0.25), (0, 0.5), (0, 1), (1, 1),
                 (1, 0.5), (0.7, 0.25), (0.7, 0), (1, 0)]],
    "+": [[(0, 0.5), (1, 0.5)], [(0.5, 0.05), (0.5, 0.95)]],
}
_BLOCK_W = {".": 0.25, "\u03a9": 0.85, "1": 0.45}


def _glyph(text, cap, at, angle=0.0, w=TRAY_LINE):
    """A label in block letters, `cap` tall, centred on `at`."""
    h = cap - w                       # stroke centres, so the ink is `cap`
    out, x = [], 0.0
    for ch in text:
        cw = _BLOCK_W.get(ch, 0.62) * cap
        if ch == ".":
            out.append(Polygon([(x, 0), (x + w, 0), (x + w, w), (x, w)]))
        else:
            sx = cw - w
            strokes = unary_union(
                [LineString([(x + w / 2 + u * sx, w / 2 + v * h) for u, v in line])
                 .buffer(w / 2, cap_style=3, join_style=2, mitre_limit=1.5)
                 for line in _BLOCK[ch]])
            # trimmed to its own cell: a square end on a diagonal pokes out
            lo = -0.3 * h if ch == "\u00b5" else 0.0
            out.append(strokes.intersection(
                Polygon([(x, lo), (x + cw, lo), (x + cw, cap), (x, cap)])))
        x += cw + 0.22 * cap
    g = unary_union(out)
    x0, y0, x1, y1 = g.bounds
    g = affinity.translate(g, -(x0 + x1) / 2, -(y0 + y1) / 2)
    g = affinity.rotate(g, angle, origin=(0, 0))
    return affinity.translate(g, at[0], at[1])


def tray_layout():
    """The tray in plan, in the box's frame: its plate, the walls on it,
    and what is cut into it -- through, from the top, from underneath --
    each a shapely region, and what each cut is."""
    l, w, t = CTRL["l"], CTRL["w"], CTRL["wall"]
    xi, yi = l / 2 - t - TRAY_GAP, w / 2 - t - TRAY_GAP
    plate = Polygon([(-xi, -yi), (xi, -yi), (xi, yi), (-xi, yi)])
    for x, y in CTRL_BOSSES:
        plate = plate.difference(Point(x, y).buffer(CTRL_BOSS_R + TRAY_BOSS_FIT, 64))
    # the XIAO's window, open to the wall it butts against: its -y wall
    # the one it is held to, its +y wide enough for the widest board but
    # for the arm beside the USB-C, which stands at a nominal one's edge
    x0 = XIAO_X1 - XIAO[0] - TRAY_FIT
    ym, yp = _xiao_walls()
    plate = plate.difference(_rect(x0, ym, xi + 1, yp).difference(
        _rect(XIAO_SIDE_ARM_X[0], XIAO[1] / 2 + SEAT, xi + 1, yp + 0.01)))
    # where the cables come in, at the height the box's inlet was drawn
    # for: the plate is cut away round them
    plate = plate.difference(Polygon([(-xi - 1, CTRL_INLET_Y - 4.6),
                                      (INLET_X + 2.4, CTRL_INLET_Y - 4.6),
                                      (INLET_X + 2.4, CTRL_INLET_Y + 4.0),
                                      (-xi - 1, CTRL_INLET_Y + 4.0)]))
    through = []
    # under the DRV8833's rows: room for what comes through its holes, and
    # the way up into them from underneath
    for row in DRV_ROWS:
        x = drv_hole(row, "GND")[0]
        through.append(Polygon(
            [(x - DRV_SLOT / 2, -8.89 - 1.0), (x + DRV_SLOT / 2, -8.89 - 1.0),
             (x + DRV_SLOT / 2, 8.89 + 1.0), (x - DRV_SLOT / 2, 8.89 + 1.0)]))
    for net, d in NETS.items():
        for h in d["holes"]:
            through.append(Point(*h).buffer(HOLE_WIRE / 2, 32))
    for at, dim in ((R1_AT, R1_DIM), (R2_AT, R2_DIM)):
        for h in _lead_holes(at, dim):
            through.append(Point(*h).buffer(dim[2] / 2 + LEAD_HOLE / 2, 32))
    through.append(Point(*VIN_HOLE).buffer(HOLE_WIRE / 2, 32))
    dl, (dm, dp) = _drv_frame()
    slots, raised, hooks = _latches(x0, xi)
    through += slots
    # held at +y, room at -y for the longest board but where the arm is
    inner = _rect(DRV_C[0] - dl, dm, DRV_C[0] + dl, dp)
    rim = inner.buffer(DRV_RIM[0], join_style=2).difference(inner)
    # cut into the top: the names and values
    top = []
    for net, d in NETS.items():
        x, y, a = d["name"]
        top.append((f"name {net}", _glyph(net, TRAY_CAP, (x, y), a)))
    for text, at, a, *cap in VALUES:
        top.append((f"value {text}", _glyph(text, cap[0] if cap else TRAY_CAP, at, a)))
    # cut into the underside: the grooves, the pockets, each net's name
    under = []
    for what, pts in _routes():
        under.append((f"groove {what}",
                      LineString(pts).buffer(GROOVE[0] / 2, cap_style=1, join_style=1)))
    for net, d in NETS.items():
        under.append((f"pocket {net}", Point(*d["pocket"]).buffer(POCKET[0] / 2, 48)))
    labels = []
    for net, d in NETS.items():
        x, y, a, *cap = d["under"]
        # mirrored, so it reads with the tray turned over
        g = affinity.scale(_glyph(net, cap[0] if cap else TRAY_CAP, (0, 0), a), -1, 1,
                           origin=(0, 0))
        labels.append((f"under {net}", affinity.translate(g, x, y)))
    return dict(plate=plate, rim=rim, through=unary_union(through),
                top=top, under=under, labels=labels, raised=raised, hooks=hooks)


def _rect(x0, y0, x1, y1):
    return Polygon([(min(x0, x1), min(y0, y1)), (max(x0, x1), min(y0, y1)),
                    (max(x0, x1), max(y0, y1)), (min(x0, x1), max(y0, y1))])


def _xiao_walls():
    """The XIAO's window across: the -y wall it is held to, and the +y
    wall that clears the widest board pressed against it."""
    ym = -XIAO[1] / 2 - SEAT
    return ym, ym + XIAO[1] + XIAO_TOL + 0.1


def _drv_frame():
    """The DRV8833's frame: its half-width, and its -y and +y walls. Held
    at +y; at -y room for the longest board but where the arm is."""
    dl = DRV8833[0] / 2 + DRV_EDGE_TOL + 0.1
    dp = DRV8833[1] / 2 + SEAT
    return dl, (dp - DRV8833[1] - 2 * DRV_EDGE_TOL - 0.15, dp)


def _arm_strain(t, d, length):
    """The bend in an arm t thick and `length` long, its tip moved d."""
    return 1.5 * t * d / length ** 2


def _latches(x0, xi):
    """The clips that hold the boards: the slots that free each arm, the
    walls standing on the plate (the DRV8833's lip and arm, up past its
    board), and the hooks, each (what, wall from, wall to, inward, z under
    it, z over it, lead-in, reach)."""
    T, S, P = LATCH_T, LATCH_SLOT, LATCH_SPLIT
    ym, yp = _xiao_walls()
    ya = XIAO[1] / 2 + SEAT                    # the side arm's face
    xb = _floor() + XIAO_T_MAX + HOOK_OVER     # the XIAO lies on the box's floor
    db = _drv_top() + DRV8833[2] * 0.1 + HOOK_OVER   # FR4's own +-10%
    slots, raised, hooks = [], [], []
    # the XIAO's far end: an arm down the window's end wall, root at its corner
    y0 = XIAO_END_ARM_Y[0]
    slots.append(_rect(x0 - T - S, y0 - P, x0 - T, yp))
    slots.append(_rect(x0 - T - S, y0 - P, x0 + 0.01, y0))
    hooks.append(("XIAO end", (x0, y0), (x0, XIAO_END_ARM_Y[1]), (1.0, 0.0),
                  xb, None, True, XIAO_END_HOOK))
    # its long edges beside the USB-C: an arm along +y, its tip at the
    # tray's end; a lip in the plate's own wall at -y
    slots.append(_rect(XIAO_SIDE_ARM_X[0], ya + T, xi + 1, ya + T + S))
    hooks.append(("XIAO side", (XIAO_SIDE_ARM_X[1], ya), (xi, ya), (0.0, -1.0),
                  xb, None, True, HOOK))
    hooks.append(("XIAO lip", (XIAO_SIDE_ARM_X[1], ym), (xi, ym), (0.0, 1.0),
                  xb, _plate_top(), False, HOOK))
    # the DRV8833: a fixed lip at +y, an arm with its hook at -y, both
    # standing a hook's height over its board
    _, (dm, dp) = _drv_frame()
    zt = db + HOOK_FLAT + DRV_HOOK            # the clip's lead-in, to its top
    raised.append((_rect(DRV_LIP_X[0], dp, DRV_LIP_X[1], dp + DRV_RIM[0]), zt))
    hooks.append(("DRV8833 lip", (DRV_LIP_X[0], dp), (DRV_LIP_X[1], dp), (0.0, -1.0),
                  db, zt, False, DRV_LIP))
    a0, a1 = DRV_ARM_X
    T, S = DRV_ARM_T, DRV_ARM_SLOT
    fa = -dp + DRV_PRELOAD                     # its face, just inside a nominal board's edge
    raised.append((_rect(a0, fa - T, a1, fa), zt))
    # freed by a split a nozzle can leave open, run into the slots under
    # its rows and into the groove from VIN
    sp = max(fa + P, -8.89 - 1.0 + 0.04)
    slots.append(_rect(-18.4, fa, a1, sp))
    slots.append(_rect(a0, fa - T - S, a1 + P, fa - T))
    slots.append(_rect(a1, fa - T - S, a1 + P, sp))
    hooks.append(("DRV8833 clip", (DRV_HOOK_X[0], fa), (DRV_HOOK_X[1], fa), (0.0, 1.0),
                  db, zt, True, DRV_HOOK))
    return slots, raised, hooks


def _hook_mesh(a, b, inward, zb, zt, lead, reach=HOOK):
    """A hook along the wall from a to b, reaching in along `inward`:
    flat underneath, and with `lead` a 45-degree lead-in over its nose
    that a board pressed down onto it pushes back."""
    if lead:
        prof = [(-0.05, zb), (reach, zb), (reach, zb + HOOK_FLAT),
                (0.0, zb + HOOK_FLAT + reach), (-0.05, zb + HOOK_FLAT + reach)]
    else:
        prof = [(-0.05, zb), (reach, zb), (reach, zt), (-0.05, zt)]
    a, b = np.asarray(a, float), np.asarray(b, float)
    e = b - a
    n = float(np.linalg.norm(e))
    m = trimesh.creation.extrude_polygon(Polygon(prof), n)
    T = np.eye(4)
    T[:3, 0] = [inward[0], inward[1], 0.0]
    T[:3, 1] = [0.0, 0.0, 1.0]
    T[:3, 2] = [e[0] / n, e[1] / n, 0.0]
    T[:3, 3] = [a[0], a[1], 0.0]
    m.apply_transform(T)          # a mirroring transform rewinds the faces itself
    return m


def ctrl_tray(specimen=SPECIMEN):
    """The controller's tray: dropped into the box, it holds both boards
    and every part, carries every joint off a board underneath, and says
    where each goes."""
    L = tray_layout()
    z0 = _floor()
    pt = _plate_top()

    def prism(poly, za, zb):
        geoms = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
        out = []
        for g in geoms:
            if g.is_empty or g.area < 1e-6:
                continue
            m = trimesh.creation.extrude_polygon(g, zb - za)
            m.apply_translation([0, 0, za])
            out.append(m)
        return out
    plate = L["plate"].difference(L["through"])
    solid = union(prism(plate, z0, pt)
                  + prism(L["rim"].intersection(plate), pt - 0.01, pt + DRV_RIM[1])
                  + [m for poly, zt in L["raised"]
                     for m in prism(poly.intersection(plate), pt - 0.01, zt)]
                  + [_hook_mesh(a, b, n, zb, zt, lead, reach)
                     for _, a, b, n, zb, zt, lead, reach in L["hooks"]])
    tools = []
    tools += prism(unary_union([g for _, g in L["top"]]), pt - TRAY_CUT, pt + 1)
    tools += prism(unary_union([g for _, g in L["under"]
                                if not _.startswith("pocket")]), z0 - 1, z0 + GROOVE[1])
    tools += prism(unary_union([g for _, g in L["under"]
                                if _.startswith("pocket")]), z0 - 1, z0 + POCKET[1])
    tools += prism(unary_union([g for _, g in L["labels"]]), z0 - 1, z0 + TRAY_CUT)
    # the saddles: each body's own cylinder, sunk to its depth
    for at, dim, lmax in ((R1_AT, R1_DIM, R1_MAX_L), (R2_AT, R2_DIM, R2_MAX_L)):
        c, a, _ = _part_axis(at)
        zc = _part_z(at, dim)
        sad = trimesh.creation.cylinder(radius=dim[1] / 2 + 0.2, height=lmax + 0.4,
                                        sections=48)
        sad.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], [a[0], a[1], 0]))
        sad.apply_translation([c[0], c[1], zc])
        tools.append(sad)
    return _ctrl_local(cut(solid, tools), specimen)


# --- the bought parts in the box, drawn as they are ------------------------
def _p(kind, mat, **kw):
    return dict(kind=kind, mat=mat, **kw)


def _boxp(lo, hi, mat):
    return _p("box", mat, lo=[float(v) for v in lo], hi=[float(v) for v in hi])


def _cylp(c, axis, r, h, mat, **kw):
    return _p("cyl", mat, c=[float(v) for v in c], axis=[float(v) for v in axis],
              r=float(r), h=float(h), **kw)


def _wire(pts, mat, r=WIRE_R):
    """A wire through `pts`: a cylinder a segment, each run on by most of
    its radius so a bend closes square."""
    pts = [np.asarray(q, float) for q in pts]
    out = []
    for a, b in zip(pts[:-1], pts[1:]):
        d = b - a
        n = float(np.linalg.norm(d))
        if n < 1e-6:
            continue
        out.append(_cylp((a + b) / 2, d / n, r, n + 1.6 * r, mat, sides=16))
    return out


def xiao_prims():
    """Seeed's XIAO ESP32S3, from its STEP: black board, gold half-hole
    pads, the RF shield, the USB-C overhanging its end, the two buttons
    and the antenna's U.FL."""
    x1, z = XIAO_X1, _floor() + 0.02
    zt = z + XIAO[2]
    w = XIAO[1] / 2
    out = [_boxp((x1 - XIAO[0], -w, z), (x1, w, zt), "pcb_black")]
    for s, names in XIAO_EDGE.items():
        for k in range(len(names)):
            x = x1 - XIAO_PAD0 - PITCH * k
            ya, yb = sorted((s * w, s * (w - 1.6)))
            out.append(_boxp((x - 0.55, ya, zt), (x + 0.55, yb, zt + 0.04), "gold"))
    out.append(_boxp((x1 - 17.31, -6.3, zt), (x1 - 6.71, 6.3, zt + 2.0), "shield"))
    out.append(_boxp((x1 - 5.77, -4.47, zt), (x1 + 1.53, 4.47, zt + 3.21), "steel"))
    for ya, yb in ((5.12, 6.72), (-6.72, -5.12)):       # Reset and Boot
        out.append(_boxp((x1 - 2.87, ya, zt), (x1 - 0.29, yb, zt + 0.73), "plastic"))
    out.append(_boxp((x1 - 20.09, 3.87, zt), (x1 - 18.37, 5.58, zt + 1.25), "steel"))
    return out


def drv_prims():
    """Pololu's DRV8833 carrier, from its STEP: green board, its 16 holes'
    pads, and the parts on it."""
    z = _plate_top() + 0.02
    zt = z + DRV8833[2]
    l, w = DRV8833[0] / 2, DRV8833[1] / 2
    out = [_boxp((DRV_C[0] - l, -w, z), (DRV_C[0] + l, w, zt), "pcb_green")]
    for row, (_, names) in DRV_ROWS.items():
        for n in names:
            c = drv_hole(row, n)
            out.append(_p("ring", "gold", c=[float(c[0]), float(c[1]), zt + 0.02],
                          axis=[0.0, 0.0, 1.0], ro=0.8, ri=0.51, h=0.04))
    # the board's frame turned half round into the box's
    for x0, y0, x1, y1, hh, mat in DRV_PARTS:
        X0, X1 = DRV_C[0] + l - x1, DRV_C[0] + l - x0
        Y0, Y1 = w - y1, w - y0
        out.append(_boxp((X0, Y0, zt), (X1, Y1, zt + hh),
                         "plastic" if mat == "ic" else "ceramic"))
    return out


def _bands(c, axis, r, length, colors):
    """A resistor's color bands, from the end nearest -axis."""
    a = np.asarray(axis, float)
    out = []
    for k, col in enumerate(colors):
        t = -length / 2 + length * (0.18 + 0.15 * k) if k < 3 else length / 2 - length * 0.16
        out.append(_cylp(np.asarray(c) + a * t, a, r + 0.04, length * 0.08, "band_" + col))
    return out


def _lying(at, dim, body, bands):
    """A resistor in its saddle, its legs bent down through their holes
    to the underside. Returns its prims and the bottoms of its two legs."""
    L_, D, lead = dim
    c, a, _ = _part_axis(at)
    zc = _part_z(at, dim)
    c3 = np.array([c[0], c[1], zc])
    a3 = np.array([a[0], a[1], 0.0])
    out = [_cylp(c3, a3, D / 2, L_, body)]
    out += _bands(c3, a3, D / 2, L_, bands)
    ends = []
    for s, h in zip((-1, 1), _lead_holes(at, dim)):
        e = c3 + a3 * s * L_ / 2
        bot = np.array([h[0], h[1], _under_z()])
        out += _wire([e, (h[0], h[1], zc), bot], "steel", lead / 2)
        ends.append(bot)
    return out, ends


def r1_prims():
    """The motor's 4.7 ohm in its saddle beside the DRV8833: the leg
    toward it along a groove under the plate and up through the slot into
    AOUT1, soldered on top; the other into the M1 pocket."""
    out, (w, e) = _lying(R1_AT, R1_DIM, "r_body_blue", ("yellow", "violet", "gold", "gold"))
    h = drv_hole("power", "AOUT1")
    pts = [w] + [np.array([x, y, _under_z()]) for x, y in _routes_by("R1 to AOUT1")[1:]]
    pts.append(np.array([h[0], h[1], _drv_top() + 0.1]))
    out += _wire(pts, "steel", R1_DIM[2] / 2)
    out.append(_solder_hole(h))
    out += _to_pocket(e, "M1", R1_DIM[2] / 2)
    return out


def r2_prims():
    """The 10 kohm pull-up in its saddle, a leg into each of the 3V3 and
    D5 pockets."""
    out, (a, b) = _lying(R2_AT, R2_DIM, "r_body_tan", ("brown", "black", "orange", "gold"))
    out += _to_pocket(a, "3V3", R2_DIM[2] / 2) + _to_pocket(b, "D5", R2_DIM[2] / 2)
    return out


def _to_pocket(bot, net, r):
    """From the bottom of a hole along the floor into the net's pocket."""
    p = NETS[net]["pocket"]
    q = np.array([p[0], p[1], _under_z()])
    return _wire([bot, q], "steel", r) if np.linalg.norm(q - bot) > 1e-6 else []


def _routes_by(what):
    return dict(_routes())[what]


def c1_prims():
    """The 100 uF stood on the DRV8833, its legs in VIN (+) and GND (-),
    2 mm up off the board's parts."""
    D, H, pitch, lead = C1_DIM
    vin, gnd = drv_hole("power", "VIN"), drv_hole("power", "GND")
    c = (vin + gnd) / 2
    z0 = _drv_top() + C1_STANDOFF
    out = [_cylp((c[0], c[1], z0 + H / 2), (0, 0, 1), D / 2, H, "cap_sleeve"),
           _cylp((c[0], c[1], z0 + H + 0.1), (0, 0, 1), D / 2 - 0.4, 0.2, "steel"),
           # the - stripe, on the side over GND
           _boxp((c[0] - 1.0, c[1] - D / 2 - 0.05, z0 + 0.3),
                 (c[0] + 1.0, c[1] - D / 2 + 0.6, z0 + H - 0.3), "cap_stripe")]
    for h, s in ((vin, 1), (gnd, -1)):
        top = np.array([c[0], c[1] + s * pitch / 2, z0])
        out += _wire([top, (top[0], top[1], z0 - 0.6), (h[0], h[1], z0 - 1.2),
                      (h[0], h[1], _drv_top() + 0.1)], "steel", lead / 2)
        out.append(_solder_hole(h))
    return out


def _solder_hole(h):
    return _cylp((h[0], h[1], _drv_top() + 0.3), (0, 0, 1), 0.85, 0.6, "solder", sides=24)


def _end(spec, lane=None):
    """A wire's end: its points from the joint itself out to where it
    rises to its lane, and the solder that holds it."""
    kind = spec[0]
    if kind in ("cable", "lead"):
        k = spec[1]
        z = CTRL["wall"] + INLET_TRAY_T + 1.4    # as _to_box has it
        y0 = CTRL_INLET_Y + (CABLE_DY if kind == "cable" else LEAD_DY)
        n = 6 if kind == "cable" else 3
        a = 2 * np.pi * k / n
        rr = 0.82 if kind == "cable" else 0.5
        p = np.array([INLET_X, y0 + rr * np.cos(a), z + rr * np.sin(a)])
        return [p, np.array([RISE_X[kind], p[1], p[2]])], []
    if kind == "xiao":
        c, s = xiao_pad(spec[1])
        zt = _floor() + 0.02 + XIAO[2]
        p = np.array([c[0], s * (XIAO[1] / 2 - 0.8), zt + 0.04 + WIRE_R])
        # the board lies in its window on the box's floor, below the
        # tray's top: up off its pad, then out over the window's edge
        up = np.array([c[0], p[1], max(p[2], _plate_top() + WIRE_R + 0.3)])
        return ([p, up, np.array([c[0], s * 10.0, up[2]])],
                [_cylp((c[0], s * (XIAO[1] / 2 - 0.7), zt + 0.3), (0, 0, 1), 0.7, 0.6,
                       "solder", sides=24)])
    if kind == "drv":
        h = drv_hole(spec[1], spec[2])
        return [np.array([h[0], h[1], _drv_top() + 0.1])], [_solder_hole(h)]
    if kind == "under":
        # into a DRV8833 hole from below: up the slot from a groove that
        # starts at its own hole in the plate
        h = drv_hole(spec[1], spec[2])
        route = _routes_by("5V to VIN")
        pts = [np.array([h[0], h[1], _drv_top() + 0.1])]
        pts += [np.array([x, y, _under_z()]) for x, y in route[::-1]]
        pts.append(np.array([route[0][0], route[0][1], _plate_top() + WIRE_R + 0.3]))
        return pts, [_solder_hole(h)]
    if kind == "hole":
        # down through its hole beside the net's name, into the pocket
        net, k = spec[1], spec[2]
        h = _net_hole(net, k)
        p = NETS[net]["pocket"]
        return [np.array([p[0], p[1], _under_z()]), np.array([h[0], h[1], _under_z()]),
                np.array([h[0], h[1], _plate_top() + WIRE_R + 0.3])], []
    raise ValueError(spec)


def wire_path(wid):
    w = {x[0]: x for x in WIRES}[wid]
    _, col, net, a, b, step, lane, via = w
    pa, _ = _end(a)
    pb, _ = _end(b)
    ra, rb = pa[-1], pb[-1]
    lane += _plate_top()        # the table gives it over the tray's plate
    mid = [np.array([ra[0], ra[1], lane])]
    mid += [np.array([x, y, lane]) for x, y in via]
    mid += [np.array([rb[0], rb[1], lane])]
    return pa + mid + pb[::-1]


def wire_prims(wid):
    w = {x[0]: x for x in WIRES}[wid]
    out = _wire(wire_path(wid), "wire_" + w[1])
    for spec in (w[3], w[4]):
        out += _end(spec)[1]
    return out


def joint_prims(net):
    """The joint itself, in its pocket under the plate: the wires' ends
    twisted and soldered, cold before it goes in."""
    p = NETS[net]["pocket"]
    return [_cylp((p[0], p[1], _floor() + 0.95), (0, 0, 1), 1.3, 1.6, "solder", sides=24)]


def wiring_table():
    """Every wire, for the page: what it is and where each end goes."""
    def name(e):
        if e[0] in ("cable", "lead"):
            return ("motor cable" if e[0] == "cable" else "home lead")
        if e[0] == "xiao":
            return f"XIAO {e[1]}"
        if e[0] in ("drv", "under"):
            return f"DRV8833 {e[2]}" + (", from below" if e[0] == "under" else "")
        return f"{e[1]} hole {e[2] + 1}"
    return [dict(id=w[0], color=w[1], net=w[2], a=name(w[3]), b=name(w[4]),
                 step=w[5]) for w in WIRES]


def _to_box(specimen, dy):
    """The way into the controller box, offset dy along its inlet."""
    co, board = _ctrl_frame(specimen)
    inlet = (co + polar(-(CTRL["l"] / 2 + 6.0), CTRL["phi"])
             + polar(CTRL_INLET_Y + dy, CTRL["phi"] + 90.0))
    # just inside the wall: from there its wires fan out over the tray
    inside = (co + polar(-(CTRL["l"] / 2 - 4.0), CTRL["phi"])
              + polar(CTRL_INLET_Y + dy, CTRL["phi"] + 90.0))
    z = board + CTRL["wall"] + INLET_TRAY_T + 1.4
    return inlet, inside, z


def _approach(specimen, dy):
    """20 mm out from the inlet, square to the wall, so a cable never
    crosses the box's screw ear on its way in."""
    co, board = _ctrl_frame(specimen)
    return (co + polar(-(CTRL["l"] / 2 + 20.0), CTRL["phi"])
            + polar(CTRL_INLET_Y + dy, CTRL["phi"] + 90.0))


def cable_upper(specimen=SPECIMEN):
    """The motor's cable inside the drive: level out of the encoder's side
    plug along its channel, and down the post's bore to its foot. It goes
    in with the drive."""
    Z = driver_levels(specimen)
    L = levels(specimen)
    o, u, t = _driver_frame()
    px = POST_R - GENEVA_C
    zc = _plug_z(Z)
    end = o + u * (-MOTOR["enc_d"] / 2 - MOTOR["plug"][0])     # the plug's back
    turn = o + u * (-(MOTOR["enc_d"] + POCKET_ENC) / 2 - MOTOR["plug"][0]) + t * CABLE_Y
    bore = o + u * px + t * CABLE_Y
    return [[end[0], end[1], zc], [turn[0], turn[1], zc], [bore[0], bore[1], zc],
            [bore[0], bore[1], L["base_top"] - POST_SOCKET]]


def cable_lower(specimen=SPECIMEN):
    """Its loose end, threaded on down through the base and out under it
    to the controller."""
    L = levels(specimen)
    o, u, t = _driver_frame()
    bore = o + u * (POST_R - GENEVA_C) + t * CABLE_Y
    under = L["base_bot"] - CABLE_UNDER
    edge = polar(118.0, (GENEVA_PHI + CTRL["phi"]) / 2)
    inlet, inside, z = _to_box(specimen, CABLE_DY)
    a = _approach(specimen, CABLE_DY)
    return [[bore[0], bore[1], L["base_top"] - POST_SOCKET], [bore[0], bore[1], under],
            [edge[0], edge[1], under], [edge[0], edge[1], z], [a[0], a[1], z],
            [inlet[0], inlet[1], z], [inside[0], inside[1], z]]


def home_lead(specimen=SPECIMEN):
    """The home sensor's leads go down through the base; its own short lead
    runs under it to the box. It goes round the inner end of the post
    rather than across the motor's cable, lower in the gap and clear of
    the sensor's pins, then alongside the motor's cable, 4 mm off it, all
    the way into the box."""
    L = levels(specimen)
    h = polar(HOME["r"], HOME["phi"])
    z = L["base_bot"] - 4.0
    b = polar(46.0, GENEVA_PHI + 9.0)
    c = polar(46.0, GENEVA_PHI - 14.0)
    # the corner where the motor's cable turns for the box, offset to its
    # inside by the same 4 mm from both of the runs that meet there
    lo = cable_lower(specimen)
    bore2, e = np.asarray(lo[1][:2]), np.asarray(lo[2][:2])
    inlet, inside, zb = _to_box(specimen, LEAD_DY)
    a = _approach(specimen, CABLE_DY)[:2]
    a1 = (e - bore2) / np.linalg.norm(e - bore2)
    a2 = (a - e) / np.linalg.norm(a - e)
    n1, n2 = np.array([a1[1], -a1[0]]), np.array([a2[1], -a2[0]])
    m = (n1 + n2) / np.linalg.norm(n1 + n2)
    d = e + m * (CABLE_DY - LEAD_DY) / float(m @ n1)
    # and again where it squares up to the box's wall
    il = np.asarray(_to_box(specimen, CABLE_DY)[0][:2])
    a3 = (il - a) / np.linalg.norm(il - a)
    n3 = np.array([a3[1], -a3[0]])
    m2 = (n2 + n3) / np.linalg.norm(n2 + n3)
    a2 = a + m2 * (CABLE_DY - LEAD_DY) / float(m2 @ n2)
    return [[h[0], h[1], L["base_bot"] - 3.2], [h[0], h[1], z], [b[0], b[1], z],
            [c[0], c[1], z], [d[0], d[1], z], [d[0], d[1], zb], [a2[0], a2[1], zb],
            [inlet[0], inlet[1], zb], [inside[0], inside[1], zb]]


def cable_path(specimen=SPECIMEN):
    return cable_upper(specimen) + cable_lower(specimen)[1:]


def _tubes(pts, r):
    pts = [np.asarray(q, float) for q in pts]
    return [dict(kind="cyl", c=list((a_ + b_) / 2), axis=list(b_ - a_), r=r,
                 h=float(np.linalg.norm(b_ - a_)))
            for a_, b_ in zip(pts[:-1], pts[1:]) if np.linalg.norm(b_ - a_) > 1e-6]


def cable_proxy(specimen=SPECIMEN):
    """The cables as thin tubes, so the sweeps can prove nothing that
    moves ever reaches them."""
    return trimesh.util.concatenate(
        [_prim_mesh(q) for q in _tubes(cable_path(specimen), CABLE_R)
         + _tubes(home_lead(specimen), LEAD_R)])


def pin_proxy(specimen=SPECIMEN):
    """The Ø3 dowel. Bought, so not in the file, but it has to be in the
    sweep: it is the thing that drives."""
    Z = driver_levels(specimen)
    o, u, _ = _driver_frame()
    p = o - u * GENEVA_A
    return cyl(PIN_R, Z["pin_lo"], Z["crank_hi"] - 0.05, p[0], p[1], 48)


# --- the pucks -----------------------------------------------------------
# Nothing stands under the base's corners. The plate model gave each
# tower 0.11 mm per newton downward, cantilevered 100 mm past the line
# between two feet, and 12.0.0 glued a foot under each; but the printed
# base proved rigid in the hand, and the tolerance stack with the corners'
# 0.1-0.2 mm of flex put back still clears the lock in all but 2 builds in
# 10,000. Six supports would also have let the board, not the three
# pucks, decide where the base sits.
PUCKS = ("puck_a", "puck_b", "puck_c")


def pucks(specimen=SPECIMEN):
    """One under each foot: bolted to the base, glued to the board. A
    wider foot for the glue, printed as it stands."""
    L = levels(specimen)
    board = L["base_bot"] - PUCK_H
    out = {}
    for n, a in zip(PUCKS, FOOT_PHI):
        x, y, _ = polar(FOOT_R, a)
        p = rev([(0, 0), (PUCK_FOOT[0], 0), (PUCK_FOOT[0], PUCK_FOOT[1]),
                 (PUCK_R, PUCK_FOOT[1] + PUCK_FOOT[0] - PUCK_R),
                 (PUCK_R, PUCK_H), (0, PUCK_H)], sections=96)
        tools = [cyl(INS_M3[0], PUCK_H - INS_M3[1], PUCK_H + 1, 0, 0, 48),
                 insert_seat(0, 0, PUCK_H),
                 # the joint table's millimeter under the insert, for the
                 # bolt's tip
                 cyl(BOLT_R, PUCK_H - INS_M3[1] - 1.5, PUCK_H, 0, 0, 48)]
        p = cut(p, tools)
        p.apply_translation([x, y, board])
        out[n] = p
    return out


# --- bearing sleeves ---------------------------------------------------
def sleeve(ecc=0.0):
    """A top hat the 608 rides on: Ø7.9 through the 8 mm bore, a flange
    the bolt head clamps onto the inner race. `ecc` offsets the bolt bore
    for the preload sleeve; two notches on its flange say which it is."""
    # a corner points the way the bore is off; turned to face out from the
    # ring's center, its wheel is furthest in
    top = SLEEVE_H + SLEEVE_FL_H
    s = union([cyl(SLEEVE_R, 0, SLEEVE_H, 0, 0, 96),
               cyl(SLEEVE_FL_R, SLEEVE_H, top, 0, 0, 6)])
    tools = [cyl(AXLE_R, -1, top + 1, ecc, 0, 48)]
    if ecc:
        for sgn in (1, -1):
            tools.append(box((-0.6, sgn * 3.6 - 1.0, top - 0.6),
                             (0.6, sgn * 3.6 + 1.0 + 3, top + 1)))
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
    z0 = L["brg_z"] - BRG_W / 2.0
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
    """The ring in section, with a 90 degree V groove on its OD whose
    faces are the wheel's V faces seated, and RACE_RELIEF under its flat."""
    t, e, tip = RING_T, WHEEL_E, WHEEL["tip"]
    zc = t / 2.0
    d = RACE_RELIEF
    root = RING_RO - e - d
    return [(RING_RI, 0), (RING_RO, 0), (RING_RO, zc - tip - e),
            (root, zc - tip + d), (root, zc + tip - d),
            (RING_RO, zc + tip + e), (RING_RO, t), (RING_RI, t)]


def wheel_profile():
    """The V wheel in section about its own axis, mid-plane at z = 0."""
    r, hw, tip, sr = WHEEL["r"], WHEEL["w"] / 2.0, WHEEL["tip"], WHEEL["side_r"]
    return [(0, -hw), (sr, -hw), (r, -tip), (r, tip), (sr, hw), (0, hw)]


def wheel():
    """A printed V wheel: the profile the ring's groove was cut for, a
    plain bore two 688s press into, one from each face, and a chamfer at
    each mouth -- all one revolved section. Prints flat on a face; the
    lower flank is a 45 degree overhang."""
    r, hw, tip, sr = WHEEL["r"], WHEEL["w"] / 2.0, WHEEL["tip"], WHEEL["side_r"]
    rb, m = WHEEL_BORE_R, WHEEL_MOUTH
    return rev([(rb + m, -hw), (sr, -hw), (r, -tip), (r, tip), (sr, hw),
                (rb + m, hw), (rb, hw - m), (rb, -hw + m)], sections=360)


def wheels_in_place(specimen=SPECIMEN, retracted=False):
    """The wheels where their sleeves put them: on the race, or turned out."""
    L = levels(specimen)
    out = {}
    for n, (x, y) in zip(WHEELS, bearing_centres(retracted)):
        w = wheel()
        w.apply_translation([x, y, L["brg_z"]])
        out[n] = w
    return out


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
    # the home magnet, pressed up into the underside over its sensor
    mx, my, _ = polar(HOME["r"], HOME["phi"])
    tools = [cyl((MAGNET[0] + MAGNET_FIT) / 2, zb - 1, zb + MAGNET[1] + 0.1,
                 mx, my, 48)]
    # the slot the arc's bar keys into, and the inserts it bolts down to
    tools.append(box((BAR_X0 - 5.0, Y_ARC - ARC_HW - 0.2, zp - PAD_SLOT_D),
                     (RING_RO + 5.0, Y_ARC + ARC_HW + 0.2, zp + 1)))
    for x in BOLTS_X:
        tools.append(cyl(INS_M3[0], zp - PAD_SLOT_D - INS_M3[1],
                         zp - PAD_SLOT_D + 0.5, x, Y_ARC, 48))
        tools.append(insert_seat(x, Y_ARC, zp - PAD_SLOT_D, 0.5))
        tools.append(cyl(BOLT_R, zp - PAD_SLOT_D - INS_M3[1] - 4.0,
                         zp - PAD_SLOT_D, x, Y_ARC, 48))
    return cut(r_, tools)


# --- quadrant arc ------------------------------------------------------
def arc_profile():
    """The box's outside, in (r, h)."""
    ri, ro, hw = ARC_RI, ARC_RO, ARC_HW
    return [(ri, -hw), (ro, -hw), (ro, hw), (ri, hw)]


def arc_cavity():
    """The box's inside, its corners chamfered at 45 degrees."""
    w, c = BOX_WALL, BOX_CHAM
    a, b, h = ARC_RI + w, ARC_RO - w, ARC_HW - w
    return [(a + c, -h), (b - c, -h), (b, -h + c), (b, h - c), (b - c, h),
            (a + c, h), (a, h - c), (a, -h + c)]


def arc():
    """In the arc frame: the quadrant, the leg and bar down to the ring,
    the slot, the ticks, the bar's three counterbored bolt holes. Mapped
    into the world at the end. Independent of the specimen dial: the
    ring's pad absorbs that."""
    quad = rev(arc_profile(), 0.0, 90.0, sections=180)
    # hollow from a little above the leg to a little short of the top, so
    # both ends are closed
    cav = rev(arc_cavity(), 2.0, 88.0, sections=172)
    leg = box((ARC_RI, LEG_BOTTOM, -ARC_HW), (ARC_RO, 0.5, ARC_HW))
    bar = box((BAR_X0, LEG_BOTTOM, -ARC_HW), (ARC_RO, LEG_BOTTOM + BAR_T,
                                              ARC_HW))
    a = union([quad, leg, bar])
    tools = [cav]
    half = np.degrees(TICK_W / 2.0 / ARC_RO)
    for f in FIDUCIALS:
        tools.append(sector(ARC_RO - TICK_D, ARC_RO + 1, -ARC_HW - 1,
                            ARC_HW + 1, f - half, f + half, 4))
    # bolts run along the arc frame's Y (world z), down through the bar
    for x in BOLTS_X:
        # horizontal as the arc prints, so its crown sags: 0.1 more room
        for r_, y0, y1 in ((BOLT_R + 0.1, LEG_BOTTOM - 1, LEG_BOTTOM + BAR_T + 1),
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
    r_in = ARC_RI - LIP_CLR - LIP_T
    plate = sector(r_in, HEEL[1], h0, h1, -d, d)
    # lips over the box's inner and outer faces, half its depth each side
    lh = (sign * 1.0, sign * (ARC_HW + NUB_CLR + 1.0))
    # the plate's whole span, so the lips' ends are flush with its ends
    # and nothing hangs off them as the part prints
    lips = [sector(r_in, ARC_RI - LIP_CLR, min(lh), max(lh), -d, d),
            sector(ARC_RO + LIP_CLR, ARC_RO + LIP_CLR + LIP_T, min(lh), max(lh), -d, d)]
    parts = [plate] + lips
    for r_, v in NUB_POS:
        n = cyl(NUB_R, min(sign * (ARC_HW + NUB_CLR), sign * (ARC_HW + 1.5)),
                max(sign * (ARC_HW + NUB_CLR), sign * (ARC_HW + 1.5)),
                0, 0, 32)
        n.apply_translation([r_, 0, 0])
        n.apply_transform(rot(np.degrees(v / 155.0), [0, 0, 1]))
        parts.append(n)
    return union(parts)


def saddle():
    """The inboard half of the carriage's clamp on the arc. The receiver
    bolts flat to its inboard face."""
    h0, h1 = PLATE_H
    s = shoe_body(PLATE_H, +1)
    tools = [screw_hole(h0 - 6.0, h1 + 1.0)]
    # the square nut's pocket, open on the inboard face: the nut drops in
    # from the face onto a floor, square to the thumbscrew, and once the
    # receiver is on it cannot fall out
    nw = NUT[0]
    tools.append(box((CLAMP_R - nw / 2, -nw / 2, h0 + NUT_FLOOR),
                     (CLAMP_R + nw / 2, nw / 2, h1 + 1.0)))
    # the receiver's inserts
    for u, v in MOUNT_SCREWS:
        tools.append(cyl(INS_M3[0], h1 - INS_M3[1], h1 + 1.0, u, v, 48))
        tools.append(insert_seat(u, v, h1))
    s = cut(s, tools)
    s.apply_transform(M_ARC)
    return s


def screw_hole(h0, h1):
    c = cyl(SCREW_R, h0, h1, 0, 0, 48)
    c.apply_translation([CLAMP_R, 0, 0])
    return c


def shoe():
    s = shoe_body(SHOE_H, -1)
    # the heel, to HEEL_GAP short of the saddle's face once both plates'
    # nubs are on the box (each plate closes NUB_CLR)
    reach = PLATE_H[0] - 2 * NUB_CLR - HEEL_GAP
    s = union([s, sector(HEEL[0], HEEL[1], SHOE_H[1] - 0.5, reach,
                         -SADDLE_DEG, SADDLE_DEG)])
    s = cut(s, [screw_hole(SHOE_H[0] - 1.0, SHOE_H[1] + 7.0)])
    s.apply_transform(M_ARC)
    return s


def receiver():
    """The phone's mount: a bar from the saddle's inboard face up the arc
    to the seat the clamp's end face stands on, the pin that keys the
    clamp, and the hole the 1/4-20 comes through from behind into the
    clamp's socket. Prints on its back, the pin standing up."""
    (u0, u1), (v0, v1) = MOUNT_U, MOUNT_V
    h0, h1 = MOUNT_H0, MOUNT_FACE
    b = box((u0, v0, h0), (u1, v1, h1))
    d, L, ch = MOUNT_PIN
    r = d / 2.0
    prof = [(0, h1 - 0.5), (r, h1 - 0.5), (r, h1 + L - ch), (r - ch, h1 + L),
            (0, h1 + L)]
    pin = trimesh.creation.revolve(prof, sections=48)
    pin.apply_translation([PIN_U, CLAMP_V, 0])
    b = union([b, pin])
    hs = h1 - MOUNT_UNDER                       # the head's seat
    tools = [cyl(QTR_R, h0 - 1, h1 + 1, SOCKET_U, CLAMP_V, 48),
             cyl(MOUNT_CBORE_R, h0 - 1, hs, SOCKET_U, CLAMP_V, 64)]
    # The seat is the counterbore's roof, printed over air, and the bolt's
    # hole through it left every bridge line ending on nothing: Brett's
    # print was a nest of strands. So the roof steps: first two bridges
    # either side of a slot the hole's width, each landed on the
    # counterbore's wall at both ends; then two across the slot, landed
    # on those, leaving a square; then the round hole on solid ground.
    # Nothing is drilled out, and the head still seats on the first layer.
    slot = Polygon([(-QTR_R, -MOUNT_CBORE_R - 1), (QTR_R, -MOUNT_CBORE_R - 1),
                    (QTR_R, MOUNT_CBORE_R + 1), (-QTR_R, MOUNT_CBORE_R + 1)]
                   ).intersection(Point(0, 0).buffer(MOUNT_CBORE_R, quad_segs=32))
    for k, poly in enumerate((slot, Polygon([(-QTR_R, -QTR_R), (QTR_R, -QTR_R),
                                             (QTR_R, QTR_R), (-QTR_R, QTR_R)]))):
        st = trimesh.creation.extrude_polygon(poly, ROOF_STEP + 0.01)
        st.apply_translation([SOCKET_U, CLAMP_V, hs - 0.01 + k * ROOF_STEP])
        tools.append(st)
    for u, v in MOUNT_SCREWS:
        tools.append(cyl(MOUNT_SCREW_R, h0 - 1, h1 + 1, u, v, 32))
    b = cut(b, tools)
    b.apply_transform(M_ARC)
    return b


# The turner: a camera mount is screwed on by turning the camera, and
# this one is the other way round -- the clamp is keyed by its pin and
# the 1/4-20 turns behind it, where fingers get only its 2 mm of head.
# So a small knurled knob carries the head in a hex socket: the bolt goes
# into the clamp by the fingers, and the turner can stay on it. Its stem
# fills the counterbore, so the socket holds all of the head, and it
# prints back down, the socket open to the nozzle. It began as a V
# wheel; the V's flanks gave the fingers nothing, so it is straight, its
# grooves running up the print so every layer is the same outline.
TURNER = dict(r=11.0, w=8.0, edge=0.6, grooves=24, groove_r=0.9, groove_at=11.2)
TURNER_FIT = 0.2         # the hex socket over the head's flats: snug
TURNER_STEM = 1.5        # into the 1.86 counterbore
TURNER_GAP = 0.4         # the knob's face off the receiver's: two layers


def qtr_turner_local():
    """Built back down at z = 0, the stem and the socket's mouth up."""
    T = TURNER
    r, w, e = T["r"], T["w"], T["edge"]
    face = w - (TURNER_GAP - 0.1)   # the knob's face, the stem standing off it
    knurl = Point(0, 0).buffer(r, quad_segs=48)
    for k in range(T["grooves"]):
        a = 2 * np.pi * k / T["grooves"]
        knurl = knurl.difference(
            Point(T["groove_at"] * np.cos(a), T["groove_at"] * np.sin(a))
            .buffer(T["groove_r"], quad_segs=8))
    knob = trimesh.creation.extrude_polygon(knurl, face)
    # both edges broken: the plate's against its first layer's squeeze,
    # the receiver's for the fingers
    edges = rev([(0, 0), (r - e, 0), (r, e), (r, face - e), (r - e, face), (0, face)],
                sections=180)
    knob = trimesh.boolean.intersection([knob, edges], engine="manifold")
    rs = MOUNT_CBORE_R - 0.4
    body = union([knob, cyl(rs, face - 0.01, w + TURNER_STEM, sections=180)])
    af = QTR_HEAD[0] + TURNER_FIT
    top = w + TURNER_STEM
    sock = trimesh.creation.cylinder(radius=af / np.sqrt(3.0),
                                     height=QTR_HEAD[1] + 0.6, sections=6)
    sock.apply_translation([0, 0, top - (QTR_HEAD[1] + 0.6) / 2.0 + 0.01])
    return cut(body, [sock])


def qtr_turner():
    """On the 1/4-20's head, its stem in the receiver's counterbore."""
    t = qtr_turner_local()
    # its back face 0.1 off the receiver's, the stem in the counterbore
    t.apply_translation([SOCKET_U, CLAMP_V,
                         MOUNT_H0 - TURNER["w"] - 0.1])
    t.apply_transform(M_ARC)
    return t


# --- proxies: hardware and the camera, for the sweeps and the page -----
def bearing_proxies(specimen=SPECIMEN, retracted=False):
    """The V wheels as they are: their true profile, revolved."""
    L = levels(specimen)
    out = []
    for x, y in bearing_centres(retracted):
        w = rev(wheel_profile(), sections=120)
        w.apply_translation([x, y, L["brg_z"]])
        out.append(w)
    return out


def _wheel_688s(c, z):
    """The two 688s in a wheel's Ø16 bore, one from each face. They sit
    on the tower's boss, where the sleeve's foot does, and stack to the
    sleeve's 10.0 under its flange: 0.1 below the wheel's middle."""
    z0 = z - BRG_W / 2.0
    return [dict(kind="ring", c=[float(c[0]), float(c[1]), z0 + dz], axis=[0, 0, 1],
                 ro=8.0, ri=BRG_BORE / 2.0, h=5.0) for dz in (2.5, 7.5)]


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
        [box(lo, hi) for lo, hi in cfg["boxes"]["phone"]] + [clamp_mesh()])


CLAMP_U = CLAMP_R       # the thumbscrew's axis, where the carriage hangs
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
    tongue = (ARC_RO - ARC_RI) + 2 * LIP_CLR + LIP_T   # the lips' couple arm
    return dict(mass_g=round(M, 1), com_u=round(com, 1),
                arm_mm=round(com - CLAMP_U, 1), moment_nm=round(moment, 3),
                tongue_couple_n=round(abs(moment) / (tongue / 1000.0), 1))


def phone_clearance(parts, kind=CAMERA_DEFAULT):
    """The phone against its own carriage. The sweeps move the two
    together, so they never ask this; a 17 Pro's top edge put it 0.6 mm
    off the saddle before anyone looked."""
    ph = trimesh.util.concatenate([box(lo, hi) for lo, hi in
                                   CAMERAS[kind]["boxes"]["phone"]])
    cm = tc.CollisionManager()
    for n in ("saddle", "shoe", "receiver"):
        cm.add_object(n, parts[n])
    return round(float(cm.min_distance_single(ph)), 3)


def thumbscrew_reach():
    """From the shoe's outer face, does the thumbscrew come through the
    square nut, and stay inside the saddle's screw hole?"""
    tip = SHOE_H[0] + THUMB_LEN
    nut_top = PLATE_H[0] + NUT_FLOOR + NUT[1]
    # 2 mm past the nut: every thread of it engaged, with the screw's
    # chamfered end beyond; and short of the receiver over the pocket
    return dict(tip_h=round(tip, 3), nut_top_h=round(nut_top, 3),
                past_nut_mm=round(tip - nut_top, 3), face_h=PLATE_H[1],
                through=bool(nut_top + 2.0 <= tip < PLATE_H[1]))


def camera_cases():
    """Every camera behind every lens it has: what the sweeps run over."""
    return [(k, l["id"]) for k, c in CAMERAS.items() for l in c["lenses"]]


def receiver_for(parts, kind, lens_id=None):
    """The receiver, which no longer slides: every lens of the one
    camera is behind the same socket."""
    return parts["receiver"].copy()


_CLAMP_M = np.array([[0, 0, -1, CLAMP_BACK_U], [1, 0, 0, CLAMP_FACE_Y],
                     [0, -1, 0, CLAMP_V], [0, 0, 0, 1]], float)


def _xcyl(r, x0, x1, y, z, sections=48):
    """A cylinder along the clamp's X."""
    c = cyl(r, x0, x1, 0, 0, sections)
    # cyl runs along z: send z to x (and x to -z)
    c.apply_transform(np.array([[0, 0, 1, 0], [0, 1, 0, y], [-1, 0, 0, z],
                                [0, 0, 0, 1]], float))
    return c


def clamp_meshes():
    """The ST-02S as it is made, by material, in the world at theta = 0:
    the two anodized blocks (socket and plain hole in the long one's end
    face, a button on each of its sides), the black pads on the jaws,
    the two steel guide rods and the lead screw between the blocks, and
    the knurled knob on the short block's end."""
    c, x, hw = ST02S, _clamp_x(), ST02S["w"] / 2.0
    zc = c["pin_z"]                                   # the screw's axis
    long_ = union([box((x["long"][0], -hw, 0), (x["long"][1], hw, c["bar_long"])),
                   box((0, -hw, 0), (c["up_t"], hw, c["depth"]))])
    long_ = cut(long_, [_xcyl(c["socket_d"] / 2 + 0.08, -1, c["socket_deep"], 0,
                              c["socket_z"]),
                        _xcyl(c["pin_hole"] / 2, -1, c["pin_deep"], 0, zc)])
    bx, bz, br = c["button"]
    buttons = []
    for sgn in (1, -1):
        bt = cyl(br, 0, 0.3, 0, 0, 32)
        bt.apply_transform(rot(-90 * sgn, [1, 0, 0]))
        bt.apply_translation([x["long"][1] - bx, sgn * hw, bz])
        buttons.append(bt)
    short = union([box((x["short"][0], -hw, 0), (x["short"][1], hw, c["bar_short"])),
                   box((x["up_short"][0], -hw, 0), (x["end"], hw, c["depth"]))])
    pads = []
    for (p0, p1), inward in ((x["pad_long"], 1), (x["pad_short"], -1)):
        pd = box((p0, -hw + 0.8, c["pad_z"][0]), (p1, hw - 0.8, c["pad_z"][1]))
        # dished to the case's rounded edge: 1.2 deep at the middle
        face = p1 if inward > 0 else p0
        rc = 12.0
        dish = cyl(rc, -hw - 1, hw + 1, 0, 0, 96)
        dish.apply_transform(rot(90, [1, 0, 0]))
        dish.apply_translation([face + inward * (rc - 1.2), 0, c["pad_c"]])
        pads.append(cut(pd, [dish]))
    x0, x1 = x["long"][1] - 6.0, x["short"][0] + 6.0
    steel = [_xcyl(c["rod_r"], x0, x1, sgn * c["rod_y"], zc) for sgn in (1, -1)]
    steel.append(_xcyl(c["screw_r"], x0, x["end"] + 1.0, 0, zc))
    kr = c["knob_r"]
    knob = [_xcyl(kr - 0.35, x["end"], x["end"] + c["knob_h"], 0, zc, 64)]
    for k in range(c["knob_ridges"]):
        a = 2 * np.pi * k / c["knob_ridges"]
        knob.append(_xcyl(0.45, x["end"] + 0.3, x["end"] + c["knob_h"] - 0.3,
                          (kr - 0.45) * np.cos(a), zc + (kr - 0.45) * np.sin(a), 8))
    out = {"anodized": union([long_, short] + buttons),
           "rubber": trimesh.util.concatenate(pads),
           "steel": trimesh.util.concatenate(steel),
           "dark": trimesh.util.concatenate(knob)}
    for m in out.values():
        m.apply_transform(_CLAMP_M)
    return out


def clamp_mesh():
    """The clamp as one mesh, for the sweeps."""
    return trimesh.util.concatenate(list(clamp_meshes().values()))


def clamp_prims():
    """The clamp for the pages: one mesh primitive per material."""
    return [dict(kind="mesh", mat=k,
                 v=[round(float(t), 3) for t in m.vertices.ravel()],
                 f=[int(t) for t in m.faces.ravel()])
            for k, m in clamp_meshes().items()]


# --- assembly and layout -----------------------------------------------
# The mount does not turn, so it belongs on the stator side -- and
# being listed is what puts it in the azimuth sweep at all. A body
# in neither list is simply never checked against anything.
#
# The driver turns, but about its own axis and not the rotor's, so for the
# azimuth sweep it stands where it does at every stop: that sweep steps
# the ring 10 degrees at a time, and at each step the lock is in a seat.
# How it moves between stops is `geneva_sweep`'s question.
STATOR_SIDE = ("stator", "puck_a", "puck_b", "puck_c", "driver", "drive_block", "drive_cap",
               "ctrl_box", "ctrl_tray", "ctrl_lid", "sleeve_a", "sleeve_b", "sleeve_c",
               "mount_screw", "mount_wing_nut", "mount_hex_nut")
ROTOR_SIDE = ("rotor", "arc")
CARRIAGE = ("saddle", "shoe", "receiver", "qtr_turner")


def assemble(specimen=SPECIMEN):
    """Every printed body, in the world frame, at home: phi = 0 and the
    carriage at theta = 0 (its build pose; the page and the sweeps turn
    it)."""
    parts = {"stator": stator(specimen), **pucks(specimen),
             "driver": driver(specimen), "drive_block": drive_block(specimen),
             "drive_cap": drive_cap(specimen), "ctrl_box": ctrl_box(specimen),
             "ctrl_tray": ctrl_tray(specimen), "ctrl_lid": ctrl_lid(specimen)}
    parts.update(sleeves_in_place(specimen))
    parts.update(wheels_in_place(specimen))
    parts["driver_shim"] = driver_shim(specimen)
    parts["rotor"] = rotor(specimen)
    parts["arc"] = arc()
    parts["saddle"] = saddle()
    parts["shoe"] = shoe()
    parts["receiver"] = receiver()
    parts["qtr_turner"] = qtr_turner()
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
    # on its inboard face, lips up: the nut's pocket and the receiver's
    # insert holes open onto the plate. It stood on the platform's
    # underside until 34.0.0, and without the platform it would stand on
    # the curved end of its plate.
    if name == "saddle":
        return rot(-90.0, [1, 0, 0])
    # on its back, the pin standing up, the 1/4-20's counterbore open
    # onto the plate
    if name == "receiver":
        return rot(90.0, [1, 0, 0])
    # on its back, the socket open to the nozzle. As it stands it is a
    # wheel on its edge, on the V's 1.5 mm tip, and plate 20 spaghettied
    if name == "qtr_turner":
        return rot(90.0, [1, 0, 0])
    if name.startswith("sleeve"):
        return rot(180.0, [1, 0, 0])
    # crank-top down, so the bore opens on the plate and the lock rises
    if name == "driver":
        return rot(180.0, [1, 0, 0])
    # Lid face down. On its side, the plug channel's wall was a tab held
    # by one edge -- the cable's slot one side of it, the encoder's pocket
    # the other, the end open -- printed on air, and it is the face the
    # lid's key presses against. Upside down the pockets and the channel
    # are shafts open to the plate, every fit is a vertical wall, and the
    # only roofs are the floor over the pocket and the channel's end, each
    # landed all round.
    if name == "drive_block":
        return rot(180.0, [1, 0, 0])
    # its wiring bay up, open to the nozzle; the controller's lid, pegs up
    if name in ("drive_cap", "ctrl_lid"):
        return rot(180.0, [1, 0, 0])
    return np.eye(4)


def layout(parts, gap=6.0, pitch=300.0):
    """Three virtual plates side by side: the base, the ring, the rest.
    The shop's packer places each body itself; this arrangement only has
    to keep them from overlapping so it can tell them apart."""
    plates = [["stator"], ["rotor"],
              ["arc", "saddle", "shoe", "receiver", *PUCKS,
               "driver", "drive_block", "drive_cap", "ctrl_box", "ctrl_tray",
               "ctrl_lid", "sleeve_a", "sleeve_b", "sleeve_c", *WHEELS]]
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
            m = printed(n, parts[n]).copy()
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


def carriage_hardware(parts, specimen=SPECIMEN):
    """The bought hardware that rides the carriage, in its frame (the
    world at theta = 0): taken from the assembly's steps, which pose it
    at MOUNT_THETA, and carried back down."""
    steps = {s_["id"]: s_ for s_ in assembly_steps(parts, specimen)}
    back = np.linalg.inv(elev(MOUNT_THETA))
    out = []
    for i, name in (("thumbscrew", "thumbscrew"), ("receiver_screws", "screw"),
                    ("camera_bolt", "camera bolt")):
        for h in steps[i]["hardware"]:
            for k, q in enumerate(h["prims"]):
                M = back @ np.asarray(q["M"], float).reshape(4, 4)
                # the thumbscrew's head is what the page's close-up calls its knob
                nm = "knob" if (i == "thumbscrew" and k == 0) else name
                out.append(dict(q, M=[round(float(v), 6) for v in M.ravel()],
                                mat=q.get("mat") or "steel", name=nm))
    return out


def page_hardware(parts, specimen=SPECIMEN):
    """The bought hardware of the drive, where it sits once fitted, for
    the capture page to draw: what stands still, what turns with the
    driver, what turns with the ring. Taken from the assembly's own steps,
    so the page draws what was swept."""
    steps = {s_["id"]: s_ for s_ in assembly_steps(parts, specimen)}
    mats = {"motor": ["steel", "dark", "brass", "steel"],
            "home_hall": ["dark"], "post_screw": ["dark", "steel"],
            "cable": ["cable"], "cable_run": ["cable"], "home_lead": ["cable"],
            "pin": ["steel"], "ring_magnet": ["magnet"]}

    def take(*ids):
        out = []
        for i in ids:
            prims = [q for h in steps[i]["hardware"] for q in h["prims"]]
            m = mats.get(i, ["steel"])
            # the controller's parts say what they are made of themselves
            out += [q if q.get("mat") else dict(q, mat=m[k] if k < len(m) else m[-1])
                    for k, q in enumerate(prims)]
        return out
    return dict(static=take("motor", "home_hall", "post_screw", "cable",
                            "cable_run", "home_lead", "boards", "c1", "jumpers",
                            "r1", "motor_wires", "j_m1", "j_home", "j_gnd"),
                driver=take("pin"), rotor=take("ring_magnet"))


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
                        head_r=AXLE_HEAD[0], head_h=AXLE_HEAD[1]),
        "geneva": dict(slots=GENEVA_N, pitch_deg=360.0 / GENEVA_N,
                       c=GENEVA_C, at=GENEVA_AT, phi=GENEVA_PHI,
                       crank=round(GENEVA_A, 3),
                       mouth=round(GENEVA_MOUTH, 3), lip_t=LIP_T,
                       pin_r=PIN_R, pin_lo=driver_levels(specimen)["pin_lo"],
                       pin_hi=driver_levels(specimen)["crank_hi"],
                       drive_deg=180.0 + 360.0 / GENEVA_N,
                       pin_xy=[round(float(v), 4) for v in
                               (_driver_frame()[0] - _driver_frame()[1]
                                * GENEVA_A)[:2]]),
        "fasteners": fasteners(specimen),
        "hardware": _jsonable(page_hardware(parts, specimen)),
        "motor": _jsonable(MOTOR),
        "arc": dict(ri=ARC_RI, ro=ARC_RO, hw=ARC_HW, slot=SLOT_W,
                    slot_deg=[], box_wall=BOX_WALL, fiducials=list(FIDUCIALS)),
        # the carriage's own hardware, at theta = 0: the wing thumbscrew,
        # the receiver's two screws and the clamp's 1/4-20
        "carriage_hw": carriage_hardware(parts, specimen),
        "cameras": {k: dict(c, configs={l["id"]: camera_config(k, l["id"])
                                        for l in c["lenses"]})
                    for k, c in CAMERAS.items()},
        "camera_default": CAMERA_DEFAULT, "pupil": [R, CAM_Y, 0.0],
        "clamp": clamp_prims(),
        "receiver_u": SOCKET_U,
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
# The rod field plate is the specimen mount and its own design, printed
# from its own card; the assembly fits it, so it is built here from that
# card's generator for the sweep, and the page fetches that card's file.
PLATE_CARD = "rod_field_jig"
PLATE_ITEM = "Carbon rod field plate, jig mount (printed: its own card)"


def rod_plate(specimen=SPECIMEN):
    """The plate as its own generator builds it, on the platform."""
    import gen_gazebo as G
    m = G.stand(G.BY_ID["gz_rfj"])
    lo, hi = m.bounds
    m.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2,
                         levels(specimen)["plat"] - lo[2]])
    return m


def _prim_mesh(p):
    if p["kind"] == "external":
        m = rod_plate(p["specimen"])
        if p.get("M") is not None:
            m.apply_transform(np.asarray(p["M"], float).reshape(4, 4))
        return m
    if p["kind"] == "vendor":
        m = vendor_mesh(p["id"])
        if m is None:
            m = trimesh.creation.cylinder(radius=p["r"], height=p["h"], sections=48)
            m.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], p["axis"]))
            m.apply_translation(p["c"])
        else:
            m = m.copy()
            m.apply_transform(np.asarray(p["V"], float).reshape(4, 4))
    elif p["kind"] == "mesh":
        m = trimesh.Trimesh(np.reshape(p["v"], (-1, 3)), np.reshape(p["f"], (-1, 3)),
                            process=False)
    elif p["kind"] == "box":
        m = box(p["lo"], p["hi"])
        if p.get("hole"):
            # a nut: its thread is where the screw's goes, so the stand-in
            # is open to the screw's major diameter
            h = p["hole"]
            c = trimesh.creation.cylinder(radius=h["r"], height=h["h"],
                                          sections=48)
            c.apply_transform(trimesh.geometry.align_vectors(
                [0, 0, 1], np.asarray(h["axis"], float)))
            c.apply_translation(h["c"])
            m = cut(m, [c])
    else:
        ax = np.asarray(p["axis"], float)
        if p["kind"] == "ring":
            m = trimesh.creation.annulus(r_min=p["ri"], r_max=p["ro"],
                                         height=p["h"], sections=96)
        else:
            m = trimesh.creation.cylinder(radius=p["r"], height=p["h"],
                                          sections=p.get("sides", 48))
        if p.get("flat"):
            # a D-shaft: the flat faces +y before the primitive is placed
            keep = box((-p["r"] - 1, -p["r"] - 1, -p["h"]),
                       (p["r"] + 1, p["flat"] - p["r"], p["h"]))
            m = trimesh.boolean.intersection([m, keep], engine="manifold")
        if p.get("flats"):
            # a motor can: two flats, `flats` either side of the axis on x
            keep = box((-p["flats"], -p["r"] - 1, -p["h"]),
                       (p["flats"], p["r"] + 1, p["h"]))
            m = trimesh.boolean.intersection([m, keep], engine="manifold")
        if p.get("corner") is not None:
            # a hex head: a corner, which trimesh puts on +x, turned to
            # `corner` so the flats line up with the pocket's
            z = ax / np.linalg.norm(ax)
            x = np.asarray(p["corner"], float)
            x = x - z * (x @ z); x /= np.linalg.norm(x)
            R = np.eye(4); R[:3, :3] = np.c_[x, np.cross(z, x), z]
            m.apply_transform(R)
        else:
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


def _bolt_prims(seat, length, r=1.5, head_r=HEAD_R, head_h=HEAD_H,
                axis=(0, 0, 1)):
    """A socket-head bolt with its head's underside on `seat`; `axis`
    points from the shank to the head."""
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    seat = np.asarray(seat, float)
    return [dict(kind="cyl", c=(seat + a * head_h / 2).tolist(),
                 axis=a.tolist(), r=head_r, h=head_h),
            dict(kind="cyl", c=(seat - a * length / 2).tolist(),
                 axis=a.tolist(), r=r, h=length)]


# --- bought hardware, as its maker drew it ----------------------------
# McMaster-Carr's STEP files, tessellated with OpenCascade at full
# quality, kept local in models/hardware/mcmaster/<part>.glb and never
# committed. Each is placed by where its head seats and which way it
# runs, read off the mesh: `seat` is the point on the axis under the head
# (or the part's centre), `axis` the way from the shank to the head, and
# `ref` a direction square to it -- a hex head's corner, a wing's span.
VENDOR_DIR = os.path.join(HERE, "..", "models", "hardware", "mcmaster")
VENDOR = {
    "92245A537": dict(name="1/4-20 x 1/2 hex head screw", seat=(-4.366, 0, 0),
                      axis=(-1, 0, 0), ref=(0, 1, 0), r=3.175, h=12.7),
    "92595A314": dict(name="M5 x 40 wing-head thumb screw", seat=(20.0, 0, 0),
                      axis=(1, 0, 0), ref=(0, 1, 0), r=2.5, h=40.0),
    "90225A101": dict(name="M5 square nut", seat=(0, 0, 0), axis=(0, 0, 1),
                      ref=(1, 0, 0), r=4.0, h=4.0),
    "91292A033": dict(name="M3 x 35 socket head screw", seat=(0, 0, 16.0),
                      axis=(0, 0, 1), ref=(1, 0, 0), r=1.5, h=35.0),
    "91390A101": dict(name="M3 x 8 cup-point set screw", seat=(0, 0, 0),
                      axis=(0, 0, 1), ref=(1, 0, 0), r=1.5, h=8.0),
    "91595A116": dict(name="3 x 16 dowel pin", seat=(0, 0, 0), axis=(0, 0, 1),
                      ref=(1, 0, 0), r=1.5, h=16.0),
}
_VENDOR_CACHE = {}
# Pairs whose real threads meet: drawn as McMaster models them, a screw
# slid straight into its nut meets the nut's thread with its own -- it
# goes in by turning. The sweep lets them through each other; the
# thumbscrew's reach past the nut is `thumbscrew_reach`'s question.
THREAD_MATES = {frozenset(("M5 square nut", f"M5x{THUMB_LEN:g} thumbscrew"))}


def vendor_path(pid):
    return os.path.join(VENDOR_DIR, pid + ".glb")


def vendor_mesh(pid):
    """The part as McMaster drew it, in its own frame; None if its mesh is
    not on this machine."""
    if pid not in _VENDOR_CACHE:
        f = vendor_path(pid)
        _VENDOR_CACHE[pid] = (trimesh.load(f, force="scene").to_geometry()
                              if os.path.exists(f) else None)
    return _VENDOR_CACHE[pid]


def _frame(axis, ref):
    z = np.asarray(axis, float); z /= np.linalg.norm(z)
    x = np.asarray(ref, float); x = x - z * (x @ z); x /= np.linalg.norm(x)
    return np.c_[x, np.cross(z, x), z]


def vendor_prim(pid, seat, axis, ref=None, mat="steel"):
    """A bought part placed with its seat on `seat`, running `axis` (shank
    to head) and, if given, its `ref` direction turned to `ref`."""
    v = VENDOR[pid]
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    if ref is None:
        ref = np.cross(a, [0, 0, 1.0]) if abs(a[2]) < 0.9 else np.array([1.0, 0, 0])
    R = _frame(a, ref) @ _frame(v["axis"], v["ref"]).T
    M = np.eye(4); M[:3, :3] = R
    M[:3, 3] = np.asarray(seat, float) - R @ np.asarray(v["seat"], float)
    # where its shank runs, for a page or sweep without the mesh
    c = np.asarray(seat, float) - a * v["h"] / 2
    return dict(kind="vendor", id=pid, mat=mat, r=v["r"], h=v["h"],
                c=c.tolist(), axis=a.tolist(),
                V=[round(float(t), 6) for t in M.ravel()])


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
          check=None, spin=None, carry=(), at=None, alt=None, turn=None,
          presses=(), solder=False):
    """`hw` is [(bom_item, qty, [prims])]; `path` is (direction, travel),
    the way the pieces arrive. `against`, when given, makes it a bench
    step checked against those bodies only; what it builds rides along
    with the later step that names it in `carry`. `at` poses the step's
    bodies (the carriage at MOUNT_THETA); `alt` stands bodies somewhere
    other than their final pose (an eccentric turned out) until `turn`
    puts them back. `solder` is wiring: its pieces overlap the pads and
    wires they are soldered to by design, so they are checked against
    the printed parts only."""
    return dict(id=id_, title=title, note=note, bodies=list(bodies),
                hardware=[dict(item=i, qty=q, prims=pr) for i, q, pr in hw],
                path=None if path is None else
                dict(dir=list(map(float, path[0])), travel=float(path[1]),
                     spin=spin),
                against=None if against is None else list(against),
                check=check, carry=list(carry),
                at=None if at is None else [round(float(v), 6)
                                            for v in np.ravel(at)],
                alt=alt, turn=turn, presses=[list(p) for p in presses],
                solder=solder)


def assembly_steps(parts, specimen=SPECIMEN):
    L = levels(specimen)
    Z = driver_levels(specimen)
    length = {n: bolt_len(c, i, r) for n, c, i, r, _, _ in JOINTS}
    down, up = (0, 0, -1), (0, 0, 1)
    feet = [polar(FOOT_R, a, L["base_top"] - FOOT_CBORE[1] + WASHER_M3[1])
            for a in FOOT_PHI]
    washers = [dict(kind="ring", c=list(map(float, f - [0, 0, WASHER_M3[1] / 2])),
                    axis=[0, 0, 1], ro=WASHER_M3[0] / 2, ri=1.6, h=WASHER_M3[1])
               for f in map(np.asarray, feet)]
    towers = [polar(TOWER_PITCH, a)[:2] for a in TOWER_PHI]
    top_of = {n: parts[n].bounds[1][2] for n in SLEEVES}
    axles = [[T[0], T[1], top_of[n]] for n, T in zip(SLEEVES, towers)]
    # each head on a washer in its counterbore, as at the feet: the Ø8
    # counterbore takes the 7 mm washer, and a head on bare PETG creeps
    bars = [[x, Y_ARC, LEG_BOTTOM + BAR_T - CBORE[1] + WASHER_M3[1]] for x in BOLTS_X]
    bar_washers = [dict(kind="ring", c=[float(x), float(Y_ARC),
                                        LEG_BOTTOM + BAR_T - CBORE[1] + WASHER_M3[1] / 2],
                        axis=[0, 0, 1], ro=WASHER_M3[0] / 2, ri=1.6, h=WASHER_M3[1])
                   for x in BOLTS_X]

    def bearings(retracted, rings):
        # each ring says which wheel it is: the page turns a wheel's
        # rings together, about that wheel's own eccentric
        return [dict(q, unit=k) for k, c in enumerate(bearing_centres(retracted))
                for q in rings(c, L["brg_z"])]
    # how far each eccentric turns between standing out and standing in
    turn = []
    for n, T, Bo, Bi in zip(SLEEVES, towers, bearing_centres(True),
                            bearing_centres(False)):
        a0 = np.arctan2(*(Bo - T)[::-1])
        a1 = np.arctan2(*(Bi - T)[::-1])
        turn.append(dict(body=n, axis=[float(T[0]), float(T[1])],
                         deg=round(float(np.degrees(wrapdeg(a1 - a0))), 4),
                         bearing=n))
    # the wheels turn with their sleeves, after them so a 688's `unit`
    # still finds its own sleeve's turn
    turn += [dict(t, body=w) for t, w in zip(turn, WHEELS)]
    o, u, _ = _driver_frame()
    pin_xy = o - u * GENEVA_A
    pin = [vendor_prim("91595A116", [pin_xy[0], pin_xy[1],
                                     (Z["pin_lo"] + Z["crank_hi"]) / 2], [0, 0, 1])]
    Zd = driver_levels(specimen)
    motor = motor_prims(specimen)
    DR = np.eye(4)
    DR[:3, 3] = [o[0], o[1], 0]
    DR = (DR @ rot(GENEVA_PHI, [0, 0, 1])).ravel().tolist()
    # the set screw on the shaft's flat, through the nut in its slot: in
    # the driver's frame, the flat facing +y
    zm = (Zd["crank_lo"] + Zd["crank_hi"]) / 2
    yf = MOTOR["shaft_flat"] - MOTOR["shaft_d"] / 2
    yn = yf + DBORE_CLR / 2 + 1.8
    # its cup on the flat, its hex socket outward
    setscrew = [dict(vendor_prim("91390A101", [0.0, yf + 0.05 + 4.0, zm], [0, 1, 0]),
                     M=DR)]
    crank_nut = [dict(kind="cyl", c=[0.0, yn + 0.15 + NUT_T / 2, zm], axis=[0, 1, 0],
                      r=NUT_AF / np.sqrt(3), h=NUT_T, sides=6, corner=[1.0, 0, 0],
                      M=DR)]
    lr, lp = HALL_LEADS
    post_screw = ([dict(vendor_prim("91292A033", [POST_R - GENEVA_C, SCREW_Y, Zd["face"]],
                                    [0, 0, 1]), M=DR)]
                  if length["drive post to base"] == 35 else
                  [dict(q, M=DR) for q in _bolt_prims(
                      [POST_R - GENEVA_C, SCREW_Y, Zd["face"]],
                      length["drive post to base"], r=1.5, head_r=2.75, head_h=3.0)])
    cable_in = _tubes(cable_upper(specimen), CABLE_R)
    cable_out = _tubes(cable_lower(specimen), CABLE_R)
    lead = _tubes(home_lead(specimen), LEAD_R)
    co, board = _ctrl_frame(specimen)
    CR = np.eye(4)
    CR[:3, 3] = [co[0], co[1], board]
    CR = (CR @ rot(CTRL["phi"], [0, 0, 1])).ravel().tolist()
    t_ = CTRL["wall"]

    def inbox(prims):
        return [dict(q, M=CR) for q in prims]
    xiao, drv = inbox(xiao_prims()), inbox(drv_prims())
    wires = {st: inbox([q for w in WIRES if w[5] == st for q in wire_prims(w[0])])
             for st in {w[5] for w in WIRES}}
    hm = polar(HOME["r"], HOME["phi"])
    HM = np.eye(4)
    HM[:3, 3] = [hm[0], hm[1], 0]
    HM = (HM @ rot(HOME["phi"], [0, 0, 1])).ravel().tolist()
    htop = L["base_top"] + RING_GAP - HOME["gap"]
    # face up in its boss; its leads out of its +y edge at mid-thickness,
    # bent down at HALL_BEND and on down the slot through the base
    home_hall = [dict(kind="box", lo=[-HALL[0] / 2, -HALL[1] / 2, htop - HALL[2]],
                      hi=[HALL[0] / 2, HALL[1] / 2, htop], M=HM)]
    lr_, zl = HALL_LEADS[0], htop - HALL[2] / 2
    yb = HALL[1] / 2 + HALL_BEND
    hz0 = L["base_bot"] - 3.0
    for x in (-HALL_LEADS[1], 0.0, HALL_LEADS[1]):
        home_hall += [dict(kind="box", lo=[x - lr_, HALL[1] / 2, zl - lr_],
                           hi=[x + lr_, yb + lr_, zl + lr_], M=HM),
                      dict(kind="box", lo=[x - lr_, yb - lr_, hz0],
                           hi=[x + lr_, yb + lr_, zl - lr_], M=HM)]
    # its real 2.0, pushed up into its 2.1 pocket short of the top
    ring_mag = [dict(kind="cyl", c=[hm[0], hm[1], L["ring_bot"] + 0.05 + MAGNET[1] / 2],
                     axis=[0, 0, 1], r=MAGNET[0] / 2, h=MAGNET[1])]
    # heat-set inserts, drawn a hair inside their bores so the sweep sees
    # them seat; in life they melt in a little proud of that
    def insert(c, ins, axis=(0, 0, 1), M=None):
        # a threaded tube: its bolt goes through it, so the stand-in is
        # open to the bolt's major diameter
        bolt_r = {INS_M3: 1.5}[ins]
        q = dict(kind="ring", c=list(map(float, c)), axis=list(axis),
                 ro=ins[0] - 0.05, ri=bolt_r + 0.05, h=ins[1] - 1.0,
                 mouth=1)      # its open end faces +axis
        if M is not None:
            q["M"] = M
        return q
    ins3 = INS_M3
    sole_ins = [insert(polar(FOOT_R, a, L["base_bot"] - (ins3[1] - 1.0) / 2),
                       ins3) for a in FOOT_PHI]
    ttop = L["base_top"] + RING_GAP + RING_T / 2.0 - BRG_W / 2.0
    tower_ins = [insert(polar(TOWER_PITCH, a, ttop - (ins3[1] - 1.0) / 2), ins3)
                 for a in TOWER_PHI]
    post_ins = [insert([POST_R - GENEVA_C, SCREW_Y, L["base_top"] - POST_SOCKET
                        - (ins3[1] - 1.0) / 2], ins3, M=DR)]
    floor_ = L["pad_top"] - PAD_SLOT_D
    pad_ins = [insert([x, Y_ARC, floor_ - (ins3[1] - 1.0) / 2], ins3) for x in BOLTS_X]

    # the USB-C plug in the XIAO's port, its cord running off the board
    # the receptacle's centre: on top of the XIAO, 3.21 tall (Seeed's STEP)
    pz = t_ + 0.02 + XIAO[2] + 3.21 / 2
    # what shows is the overmold, 12 x 6.4 and 20 long, from the
    # receptacle's mouth out through the wall; its metal shell is inside
    um = XIAO_X1 + 1.53
    usb = [dict(kind="box", lo=[um, XIAO_Y - 6.0, pz - 3.2],
                hi=[um + 20.0, XIAO_Y + 6.0, pz + 3.2], M=CR, mat="plastic"),
           dict(kind="cyl", c=[um + 50.0, XIAO_Y, pz], axis=[1, 0, 0],
                r=2.0, h=60.0, M=CR, mat="cable")]
    usb_dir = (np.asarray(CR).reshape(4, 4)[:3, :3] @ np.array([-1.0, 0, 0])).tolist()
    # the receiver's inserts, in the saddle's inboard face
    saddle_ins = _moved([dict(kind="ring", axis=[0, -1, 0], ro=ins3[0] - 0.05,
                              ri=1.55, h=ins3[1] - 1.0, mouth=-1,
                              c=list(_arc_to_world(u, v, PLATE_H[1]
                                                   - (ins3[1] - 1.0) / 2)))
                         for u, v in MOUNT_SCREWS], elev(MOUNT_THETA))
    E = elev(MOUNT_THETA)
    # a real M5 square nut, 8 x 4, on the floor of its 8.4 pocket
    zn = PLATE_H[0] + NUT_FLOOR + NUT[1] / 2
    nut = _moved([dict(vendor_prim("90225A101", [CLAMP_R, 0.0, zn], [0, 0, 1],
                                   ref=(1, 0, 0)), M=M_ARC.ravel().tolist())], E)
    # McMaster 92595A314 as it is drawn: the wing head, the M5 thread
    seat = _arc_to_world(CLAMP_R, 0.0, SHOE_H[0])
    thumb = [vendor_prim("92595A314", seat, (0, -1, 0), ref=(0, 0, 1))]
    thumb = _moved(thumb, E)
    recv_screws = _moved([p for u, v in MOUNT_SCREWS
                          for p in _bolt_prims(_arc_to_world(u, v, MOUNT_FACE),
                                               length["receiver to saddle"],
                                               r=1.5, head_r=2.75, head_h=3.0,
                                               axis=(0, 1, 0))], E)
    # from behind the seat, through it, QTR_ENGAGE into the clamp's socket;
    # its head a hexagon for the 7/16 wrench
    # McMaster 92245A537 as it is drawn, its threads and all
    qseat = _arc_to_world(SOCKET_U, CLAMP_V, MOUNT_FACE - MOUNT_UNDER)
    qtr = [vendor_prim("92245A537", qseat, (0, -1, 0), ref=(1, 0, 0))]
    qtr = _moved(qtr, E)
    cfg = camera_config(CAMERA_DEFAULT)
    cam = _moved([dict(kind="box", lo=list(lo), hi=list(hi), mat="phone")
                  for lo, hi in cfg["boxes"]["phone"]] + clamp_prims(), E)
    up_arc = (E @ np.array([0, 0, 1.0, 0]))[:3]   # +v at MOUNT_THETA
    inboard, outboard = (0, -1, 0), (0, 1, 0)
    return [
        _step("puck_inserts", "Inserts into the pucks",
              "On the bench: one M3 insert melted into the top of each.",
              hw=[(INSERT_M3, 3, sole_ins)], path=(down, 15.0),
              against=list(PUCKS)),
        _step("stator_inserts", "Inserts into the base",
              "Four M3 inserts: one in the top of each tower, one under "
              "the drive post's socket. Its bolt runs right through, so "
              "once it is cool clear the melt pushed under it: a 2.5 mm "
              "drill down through the insert, by hand.",
              hw=[(INSERT_M3, 4, tower_ins + post_ins)],
              path=(down, 15.0), against=["stator"]),
        _step("pucks", "Pucks up under the base",
              "On the bench: an insert-side-up puck under each of the three "
              "counterbored holes at the base's corners.",
              list(PUCKS), path=(up, 20.0), against=["stator"],
              carry=["puck_inserts"]),
        _step("feet", "Three bolts down into the pucks",
              "From above, a washer under each head, down the counterbores; "
              "snug. The base now stands on its own three feet.",
              hw=[(WASHER_ITEM, 3, washers),
                  ("M3x" + str(length["base to puck"]), 3,
                   [p for f in feet for p in
                    _bolt_prims(f, length["base to puck"])])],
              path=(down, 20.0), against=["stator", "pucks"]),
        _step("mount_screw", "Mount screw up through the pedestal",
              "On the bench, from underneath: push a 7 mm drill through the "
              "thin skin over the hex pocket first; the hex head drops into its "
              "pocket and cannot turn. The last time the underside is "
              "reachable.", ["mount_screw"], path=(up, 60.0),
              against=["stator"]),
        _step("home_hall", "Home sensor into its boss",
              "On the bench: bend its three leads 90 degrees down, as "
              "close to the body as they will go, away from the printed "
              "face. Set it in the pocket printed face up, the leads down "
              "the slot beside it and out under the base. "
              "Its wiring is the motor cable's spare: cut the cable 37 cm from "
              "its plug and take three of the six wires off the loose 38 cm. "
              "Splice them onto the sensor's leads underneath now and sleeve "
              "each joint -- the splice ends up in the gap under the base, "
              "where nothing can be soldered once the base is down.",
              hw=[(HALL_ITEM, 1, home_hall)],
              path=(down, 15.0), against=["stator"]),
        _step("stator", "Base onto the board",
              "Scuff the pucks' undersides, put glue under each and set the "
              "base down on the board: the base holds the pucks where they "
              "belong while it cures. The home lead trails out. Board and "
              "glue are not on the BOM.",
              ["stator"], path=(down, 30.0),
              carry=["stator_inserts", "pucks", "feet", "mount_screw",
                     "home_hall"]),
        _step("bearings", "Two 688s into each printed wheel, onto the towers",
              "On the bench, in a vise or under a flat block: a 688 pressed "
              "into each face of a wheel, pushing on the bearing's outer "
              "ring only, until it sits just under the face. The bore is "
              "drawn a touch loose: a bearing that slides in by hand gets a "
              "drop of CA or J-B Weld round its outer ring. Then sit each "
              "wheel on a tower.",
              list(WHEELS),
              [(WHEEL_BRG_ITEM, 6, bearings(True, _wheel_688s))],
              (down, 25.0), alt="retracted"),
        _step("sleeves", "Sleeves down through the wheels",
              "Each printed sleeve down through its wheel's two 688s, flange "
              "on top. The bolt hole is off center in all three: turn each "
              "sleeve until its wheel sits as far out as it goes, so the "
              "ring can drop in between them. The flange is a 10 mm hex: "
              "that is what turns it.", list(SLEEVES),
              path=(down, 25.0), alt="retracted"),
        _step("axles", "Axle bolts, finger tight",
              "Down through each sleeve into its tower's insert.",
              hw=[("M3x" + str(length["bearing axle to tower"]), 3,
                   [p for a in axles for p in
                    _bolt_prims(a, length["bearing axle to tower"], r=1.5,
                                head_r=AXLE_HEAD[0], head_h=AXLE_HEAD[1])])],
              path=(down, 20.0)),
        _step("rotor_inserts", "Inserts into the rotor's pad",
              "Three M3 inserts in the floor of the pad's slot.",
              hw=[(INSERT_M3, 3, pad_ins)],
              path=(down, 15.0), against=["rotor"]),
        _step("ring_magnet", "Home magnet into the ring",
              "On the bench: a drop of CA in its pocket, then the magnet, "
              "either way up.",
              hw=[("\u00d83 x 2 N52 disc magnet", 1, ring_mag)],
              path=(up, 10.0), against=["rotor"]),
        _step("rotor", "Ring down past the bearings",
              "Lip down, held at the race while the eccentrics come in.",
              ["rotor"], path=(down, 40.0),
              carry=["rotor_inserts", "ring_magnet"]),
        _step("preload", "Turn the eccentrics in and tighten",
              "With a 10 mm wrench on each sleeve's hex, in turn, a little "
              "each time, so the ring stays centered, until every bearing "
              "meets the race and the ring turns without play -- fully in "
              "is a little tight, so stop just short of it. Then tighten "
              "each axle bolt with the wrench still holding its sleeve: "
              "left free, the sleeve turns with the bolt's head and walks "
              "its wheel back off the race.",
              check="race", turn=turn),
        _step("pin", "Pin into the crank",
              "On the bench, in a vise: the \u00d83 x 16 dowel pressed down "
              "through the whole 8 mm of crank, flush with its top. The hole "
              "is drawn at the pin's size so it is tight in every print.",
              hw=[(f"\u00d83 x {PIN_L:g} steel dowel (the Geneva pin)", 1, pin)],
              path=(down, 20.0), against=["driver"],
              presses=[("\u00d83 x 16 steel dowel", "driver")]),
        _step("motor", "Gearmotor into the drive block",
              "On the bench: first push a 4 mm drill through the two thin "
              "skins on the block's floor, the bushing's hole and the screw's; "
              "then the motor shaft down, its bushing into the floor's hole, "
              "the flat of its D-shaft facing across the block. Nothing to "
              "solder: everything is on its plug.",
              hw=[(MOTOR["item"], 1, motor)], path=(down, 30.0),
              against=["drive_block"]),
        _step("cable", "Plug the cable on and thread it down",
              "On the bench: Pololu's 6-pin cable into the encoder's side "
              "connector, the plug lying in its channel, its loose end down "
              "the post's bore until it comes out of the foot.",
              hw=[(CABLE_ITEM, 1, cable_in)], against=["drive_block"]),
        _step("shim", "The driver's shim",
              "Printed with the set, fitted never: the 0.6 mm fork that sets "
              "the crank's height in the next step.",
              ["driver_shim"], check="spare"),
        _step("driver", "Driver up onto the gearmotor's shaft",
              "On the bench: the M3 nut into its slot in the crank's top; "
              "the shim against the block's floor, round the shaft; the "
              "D-bore slid onto the D-shaft, flat to flat, up until the "
              "crank meets the shim. Tighten the set screw onto the flat "
              "through the crank's side, and pull the shim out. The pin "
              "goes with it.",
              ["driver"], path=(up, 15.0), against=["drive_block", "motor"],
              carry=["pin"], hw=[(SETSCREW_ITEM, 1, setscrew), (NUT_ITEM, 1, crank_nut)]),
        _step("drive", "The drive down onto the base",
              "As one unit: the cable's loose end through the base's hole, "
              "the lock and pin down through a seat in the lip, the post's "
              "foot into its socket. The gearbox will not turn by hand, so "
              "turn the ring instead until a seat comes under the lock and "
              "the drive drops.",
              ["drive_block"], path=(down, 45.0),
              carry=["motor", "cable", "driver"]),
        _step("post_screw", "One screw down through the tower and post",
              "Down the access bore into the base's insert.",
              hw=[(f"M3x{length['drive post to base']}", 1, post_screw)],
              path=(down, 30.0)),
        _step("cap", "Lid pressed on",
              "Its two pegs into the screw's access bore and their own "
              "hole, over the motor, the plug and the cable's channel.",
              ["drive_cap"], path=(down, 15.0),
              presses=[("drive_cap", "drive_block")]),
        _step("ctrl", "Controller box onto the board",
              "Glued to the board like the pucks, its USB-C opening facing "
              "out, its cable inlet toward the jig.",
              ["ctrl_box"], path=(down, 25.0)),
        _step("tray", "The tray into the box",
              "Printed, it drops in flat, its notches round the lid's two "
              "bosses. It is wired like a circuit board: each part in a "
              "saddle its own shape, its legs down through holes; each wire "
              "down through the hole beside its net's name. Turned over, "
              "the grooves underneath are the circuit, and every net that is "
              "not on a board meets the others in its pocket there. It comes "
              "out again for the wiring, and goes back in when it is done.",
              ["ctrl_tray"], path=(down, 15.0)),
        _step("cable_run", "The motor's cable under the base to the box",
              "Its loose end from under the base, across the board, in "
              "through the box's inlet. Pull 10 cm through: the wiring is "
              "done with the ends up out of the box.", hw=[("", 0, cable_out)]),
        _step("home_lead", "The home sensor's lead to the box",
              "Spliced on before the base went down; laid under it now, "
              "alongside the motor's cable, and in through the box's inlet.",
              hw=[("", 0, lead)]),
        _step("boards", "The XIAO and the DRV8833 into the tray",
              "Both clip in, on the bench with the tray out. The XIAO "
              "parts up, its USB-C toward the tray's open end: tuck the "
              "edge away from the M1 name under the small lip beside the "
              "USB-C, then press the board down until the hooks at its far "
              "end and its other edge click over it. The DRV8833 parts up, "
              "its GND end toward you (the end with the square pad, on the "
              "underside): tuck the far end under the lip in its frame, "
              "then press the near end down past the hook. To free either, "
              "push a hook's arm back with a fingernail and lift. The tray "
              "goes back into the box USB-C end first, tilted, the port "
              "into the wall's opening, then laid down over the bosses; "
              "everything from here is soldered on the bench, and the tray "
              "shows where it ends up.",
              hw=[("Seeed Studio XIAO ESP32S3", 1, xiao),
                  ("Pololu #2130 DRV8833 dual motor driver carrier", 1, drv)],
              # its clip's arm stands DRV_PRELOAD inside the board's end
              presses=[("Pololu #2130 DRV8833", "ctrl_tray")], solder=True),
        _step("c1", "The 100 uF onto the DRV8833",
              "Its long leg (+) into VIN, the striped leg (-) into the GND "
              "beside it, on the power row; standing 2 mm off the board's "
              "parts, its top under the lid. Solder underneath and trim "
              "flush: the tray's slot takes what is left.",
              hw=[(CAP_ITEM, 1, inbox(c1_prims()))], solder=True),
        _step("jumpers", "Board to board: power and the three signals",
              "Red from the XIAO's 5V down through the hole beside the "
              "100 uF's value, along its groove under the tray and up the "
              "slot into VIN from below, beside the capacitor's leg; "
              "soldered on the board's top. Yellow from D0 to AIN1, D1 to "
              "AIN2 and D8 to FLT (nFAULT). On the XIAO each lies flat along "
              "its pad, tinned first; on the DRV8833 each goes through its "
              "hole, soldered underneath and trimmed.",
              hw=[("", 0, wires["jumpers"])], solder=True),
        _step("r1", "The motor's 4.7 ohm",
              "Into its saddle above the DRV8833, a leg bent down into the "
              "hole at each end. Under the tray, the leg nearer the left "
              "wall runs down its groove and up the slot into AOUT1, "
              "soldered on the board's top; the other runs to the M1 "
              "pocket.",
              hw=[(MOTOR_R_ITEM, 1, inbox(r1_prims()))], solder=True),
        _step("motor_wires", "Three of the motor cable's wires straight on",
              "Black (the motor's M2) into AOUT2. Yellow (encoder A) to "
              "the XIAO's D3, white (encoder B) to D4.",
              hw=[("", 0, wires["motor_wires"])], solder=True),
        _step("j_m1", "Red to the 4.7 ohm: the M1 channel",
              "The cable's red (the motor's M1) down the hole beside M1, "
              "and under the tray along its groove to the pocket, where it "
              "twists onto the resistor's leg. Lift the twist clear of the "
              "plastic with tweezers, solder it, and press it into the "
              "pocket once it is cool.",
              hw=[("", 0, wires["j_m1"] + inbox(joint_prims("M1")))], solder=True),
        _step("j_home", "The pull-up, 3V3 and the home signal",
              "The 10 kohm into its saddle beside its value, a leg down "
              "each end: under the tray they run to the 3V3 and D5 pockets. "
              "3V3, down its three holes: the motor cable's blue (the "
              "encoder's supply), the home lead's blue (the sensor's) and a "
              "blue on to the XIAO's 3V3. D5, down its two: the home lead's "
              "white (the sensor's output) and a white on to the XIAO's D5. "
              "In each pocket the ends twist together, soldered lifted "
              "clear, pressed in cool.",
              hw=[(PULLUP_ITEM, 1, inbox(r2_prims())),
                  ("", 0, wires["j_home"] + inbox(joint_prims("3V3"))
                   + inbox(joint_prims("D5")))], solder=True),
        _step("j_gnd", "Every ground together: the GND channel",
              "Down the four holes beside GND: both greens (the encoder's "
              "and the sensor's ground) and two blacks, one to the XIAO's "
              "GND, one to the DRV8833's GND on its logic row. One joint, "
              "in the GND pocket.",
              hw=[("", 0, wires["j_gnd"] + inbox(joint_prims("GND")))], solder=True),
        _step("ctrl_lid", "Lid on the controller",
              "Its two pegs pressed into the bosses.",
              ["ctrl_lid"], path=(down, 15.0),
              presses=[("ctrl_lid", "ctrl_box")]),
        _step("power", "The one power cord",
              "USB-C from a 5 V, 2 A wall charger (not a laptop port) into "
              "the XIAO. It powers the controller, the H-bridge and the "
              "gearmotor; the motor's resistor keeps the draw near what the "
              "XIAO's port is built for. The phone runs on its battery: it "
              "rides the ring.",
              hw=[("USB-C cable and 5 V 2 A USB power adapter", 1, usb)],
              path=(usb_dir, 25.0)),
        _step("arc", "Arc down onto the pad",
              "The bar keys into the pad's slot.",
              ["arc"], path=(down, 40.0)),
        _step("arc_bolts", "Three bolts down through the bar",
              "A washer under each head, down the counterbores into the "
              "pad's inserts.",
              hw=[(WASHER_ITEM, 3, bar_washers),
                  ("M3x" + str(length["arc bar to rotor pad"]), 3,
                   [p for b in bars for p in
                    _bolt_prims(b, length["arc bar to rotor pad"])])],
              path=(down, 25.0)),
        _step("saddle_inserts", "Inserts into the saddle",
              "On the bench: two M3 inserts into the saddle's inboard face, "
              "for the receiver.",
              hw=[(INSERT_M3, 2, saddle_ins)], path=(inboard, 15.0),
              against=["saddle"], at=E),
        _step("nut", "Square nut into the saddle",
              "On the bench: flat, down into the square pocket in the "
              "saddle's inboard face until it sits on the pocket's floor, "
              "over the screw hole. The receiver covers it later.",
              hw=[("M5 square nut", 1, nut)], path=(inboard, 20.0),
              against=["saddle"], at=E),
        _step("saddle", "Saddle onto the arc, inboard",
              "Half way up the arc, its lips over the arc's inner and outer faces.",
              ["saddle"], path=(inboard, 30.0), carry=["saddle_inserts", "nut"],
              at=E),
        _step("shoe", "Shoe onto the arc, outboard", "",
              ["shoe"], path=(outboard, 30.0), at=E),
        _step("thumbscrew", "Thumbscrew through shoe, slot and saddle",
              "Into the square nut.",
              hw=[(f"M5x{THUMB_LEN:g} thumbscrew", 1, thumb)],
              path=(outboard, 50.0)),
        _step("receiver", "Receiver onto the saddle",
              "Flat on the saddle's inboard face, its seat up the arc, "
              "the pin facing away from the arc.",
              ["receiver"], path=(inboard, 20.0), at=E),
        _step("receiver_screws", "Two screws into the saddle",
              "Through the receiver's bar into the saddle's inserts.",
              hw=[("M3x" + str(length["receiver to saddle"]), 2,
                   recv_screws)], path=(inboard, 25.0)),
        _step("camera", "Phone, in its clamp, onto the seat",
              "The phone in the clamp first: portrait, upside down, the "
              "clamp near its bottom under Camera Control, the long block "
              "on the camera's edge. Then the long block's end face onto "
              "the seat, the pin in its plain hole: the clamp goes on only "
              "one way.",
              hw=[(CLAMP_ITEM, 1, cam)], path=(inboard, 30.0)),
        _step("camera_bolt", "The 1/4-20 from behind, in its turner",
              "The bolt's head into the turner's hex socket, then through "
              "the seat into the clamp's socket, turned by the turner's "
              "rim, finger tight. The clamp does not turn, so the pin says "
              "where the phone points, not the thread. The turner stays on.",
              ["qtr_turner"], hw=[(QTR_ITEM, 1, qtr)], path=(outboard, 25.0),
              at=E),
        _step("rod_plate", "Rod field plate onto the platform",
              "Printed from its own card. Its plain hole drops over the "
              "mount screw; the carbon rods go in later, cut to the "
              "specimen.",
              hw=[(PLATE_ITEM, 1, [dict(kind="external", id=PLATE_CARD,
                                         params=dict(material="petg"),
                                         specimen=specimen,
                                         c=[0.0, 0.0, L["plat"]])])],
              path=(down, 30.0)),
        _step("mount", "Wing nut down the mount screw",
              "Turned down onto the plate by the fingers.",
              ["mount_wing_nut"], path=(down, 30.0),
              spin=dict(xy=[0.0, 0.0], lead=mount_thread().lead,
                        engage=float(parts["mount_screw"].bounds[1][2]
                                     - (L["plat"] + PLATE_T)))),
        _step("spare", "The hex nut: for when a rod is in the wings' way",
              "Printed with the set, fitted instead of the wing nut.",
              ["mount_hex_nut"], check="spare"),
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
        # above the screw's tip the nut is only dropped; it turns, at the
        # thread's lead, for the distance it is actually on the thread
        ang = 360.0 * min(t, sp.get("engage", t)) / sp["lead"] + phase
        T = T @ rot(ang, [0, 0, 1], origin=[sp["xy"][0], sp["xy"][1], 0])
    return T


# A press overlaps its partner by design. The sweep lets a
# declared pair touch, but only by about a press's worth: a part that
# really did not fit would overlap far more.
PRESS_VOL_MAX = 4.0     # mm3


def _presses(pair, st, movers, stat, T):
    """Is this contact a declared press, overlapping by no more than a
    press does?"""
    for a_, b_ in st.get("presses") or ():
        for x, y in (pair, pair[::-1]):
            if x.startswith(a_) and y.startswith(b_):
                mv = movers[x] if x in movers else movers[y]
                st_ = stat[y] if y in stat else stat[x]
                m = mv.copy()
                m.apply_transform(T)
                try:
                    v = trimesh.boolean.intersection([m, st_], engine="manifold").volume
                except Exception:
                    return False
                return v <= PRESS_VOL_MAX
    return False


RUN_IN_REACH = 60.0      # clear run a hand needs to hold a piece and place it


def _run_in(path, movers, stat):
    """How far back along its path a step's pieces must go to stand
    clear of the box round everything they are fitted against: the
    path's own travel says where it starts, not that it can get there."""
    if not stat or not movers:
        return 0.0
    lo = np.min([m.bounds[0] for m in stat.values()], axis=0)
    hi = np.max([m.bounds[1] for m in stat.values()], axis=0)
    d = np.asarray(path["dir"], float)
    mlo = np.min([m.bounds[0] for m in movers.values()], axis=0)
    mhi = np.max([m.bounds[1] for m in movers.values()], axis=0)
    # moved by -d t, the boxes part on axis i once t passes this; parting
    # on any one axis is enough
    ts = [(mhi[i] - lo[i]) / d[i] if d[i] > 0 else (hi[i] - mlo[i]) / -d[i]
          for i in range(3) if abs(d[i]) > 1e-9]
    return max(0.0, min(ts))


def assembly_sweep(parts, specimen=SPECIMEN, step=0.5):
    """Every step's pieces along their path against what is in place --
    printed bodies and the hardware fitted before them. Returns per-step
    fouls, and whether the steps install every printed body exactly once
    and add up to the BOM."""
    steps = assembly_steps(parts, specimen)
    alts = {"retracted": {**sleeves_in_place(specimen, retracted=True),
                          **wheels_in_place(specimen, retracted=True)}}
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
                    if n in bench:                 # what a bench step built
                        stat.update(bench[n])
                        continue
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
                out_ = set()
                for a, b in names:
                    if (a[:2] == "M:") == (b[:2] == "M:"):
                        continue
                    pair = (a[2:], b[2:])
                    if _presses(pair, st, movers, stat, T):
                        continue
                    if frozenset(x.split("#")[0] for x in pair) in THREAD_MATES:
                        continue
                    out_.add("|".join(sorted(pair)))
                return sorted(out_)

            if st["path"].get("spin"):
                # a nut ends wherever its thread lets it: find that phase
                for ph in np.arange(0.0, 360.0, 5.0):
                    if not hits(_path_pose(st["path"], 0.05, ph)):
                        phase = float(ph)
                        break
            # where it comes from: a piece that starts sealed inside what it
            # goes into -- a nut in a trap with no mouth -- can slide its
            # whole path without touching anything. Run the path back on
            # until it is clear of everything it is fitted against.
            if not st["path"].get("spin"):
                # ...or for a hand's reach: the arc's bolts go in under the
                # arc itself, 108 mm overhead, and that is room enough
                far = min(_run_in(st["path"], movers, stat),
                          st["path"]["travel"] + RUN_IN_REACH)
                for t in np.arange(st["path"]["travel"] + step, far + step, step):
                    hit = hits(_path_pose(st["path"], float(t), phase))
                    if hit:
                        fouls.append((round(float(t), 2), ["cannot be brought in: "] + hit))
                        break
            for t in list(np.arange(st["path"]["travel"], 0.05, -step)) + [0.05]:
                hit = hits(_path_pose(st["path"], float(t), phase))
                if hit:
                    fouls.append((round(float(t), 2), hit))
                    break
        if (not st["path"] and movers and st["against"] is None
                and st["check"] != "spare"):
            # nothing moves it into place (the cable is laid, not pushed):
            # it must not overlap anything where it sits
            cm = tc.CollisionManager()
            for n, m in installed.items():
                if st.get("solder") and n not in parts:
                    continue
                cm.add_object("S:" + n, m)
            for n, m in movers.items():
                cm.add_object("M:" + n, m)
            _, names = cm.in_collision_internal(return_names=True)
            hit = sorted({"|".join(sorted((a[2:], b[2:]))) for a, b in names
                          if (a[:2] == "M:") != (b[:2] == "M:")
                          and not _presses((a[2:], b[2:]), st, movers, installed,
                                           np.eye(4))})
            if hit:
                fouls.append((0.0, hit))
        if st["turn"]:
            # the eccentrics come in: sleeves and bearings to where they run
            # the 688s go with their wheels: inside them, never a fit's
            # question for what comes after
            for n in SLEEVES + WHEELS:
                installed[n] = parts[n]
            for k in [k for k in installed if k.startswith(WHEEL_BRG_ITEM + "#")]:
                del installed[k]
        if st["check"] == "race":
            r = race_contact(parts["rotor"], specimen)
            if not all(x["gap"] < 0.05 and x["pressed_collides"] for x in r):
                fouls.append((0.0, ["bearings do not seat on the race"]))
        if st["against"] is not None:
            bench[st["id"]] = movers
        elif st["check"] != "spare":           # the spare is never fitted
            installed.update(movers)
        out.append(dict(id=st["id"], fouls=fouls))
    counts = {}
    for st in steps:
        for b in st["bodies"]:
            counts[b] = counts.get(b, 0) + 1
    bom = {}
    for st in steps:
        for h in st["hardware"]:
            if h["item"]:                  # "" is hardware carried on, not bought
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
    if kind == "steel in a vise":
        # drawn under the pin on purpose: PETG yields, and a vise does it
        return "press" if -0.10 <= allow <= 0.2 else (
            "interference" if allow < -0.10 else "slip")
    if kind == "printed in printed":
        # both sides yield: a light press is drawn a little over
        return "press" if -0.15 <= allow <= 0.02 else (
            "interference" if allow < -0.15 else "slip")
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


def _socket_width(mesh, centre, direction):
    """Across a socket open at the top: from just inside one wall to the
    other, along `direction`."""
    d = np.asarray(direction, float) / np.linalg.norm(direction)
    hits = []
    for sgn in (1, -1):
        loc, _, _ = mesh.ray.intersects_location([centre], [d * sgn],
                                                 multiple_hits=False)
        if not len(loc):
            return None
        hits.append(float(np.linalg.norm(loc[0] - centre)))
    return sum(hits)


def _key_width(mesh, centre, direction):
    """Across a solid key, from outside it inward on both sides."""
    d = np.asarray(direction, float) / np.linalg.norm(direction)
    total = 0.0
    for sgn in (1, -1):
        start = centre + d * sgn * 20.0
        loc, _, _ = mesh.ray.intersects_location([start], [-d * sgn],
                                                 multiple_hits=False)
        if not len(loc):
            return None
        total += 20.0 - float(np.linalg.norm(loc[0] - start))
    return total


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
        2 * PIN_R, "press", kind="steel in a vise", note="steel dowel, pressed with a vise")
    zl = L["ring_bot"] + LIP_T / 2
    a_s = np.radians(GENEVA_PHI + 180.0 / GENEVA_N)
    rs = (GENEVA_MOUTH + GENEVA_C + GENEVA_A) / 2
    org = np.array([rs * np.cos(a_s), rs * np.sin(a_s), zl])
    row("Geneva pin in a slot", _ray_gap(parts["rotor"], org,
                                         [-np.sin(a_s), np.cos(a_s), 0]),
        2 * PIN_R, "running", note="it slides the slot's length every frame")
    # the gearmotor's D-shaft in the crank: across the round, and across
    # the flat, both the shop's press
    # measured from the driver's own axis -- a D's area centroid is pulled
    # toward its round side -- out to the round wall and to the flat
    t_ = np.array([-u[1], u[0], 0.0])
    od = np.array([o[0], o[1], Z["crank_hi"] - 2.0])
    rnd, flt = _ray_hit(parts["driver"], od, -t_), _ray_hit(parts["driver"], od, t_)
    row("Gearmotor's D-shaft in the crank, round",
        None if rnd is None else 2 * rnd, MOTOR["shaft_d"], "running",
        note="it slides on; the set screw on its flat holds it")
    row("Gearmotor's D-shaft in the crank, flat",
        None if rnd is None or flt is None else rnd + flt, MOTOR["shaft_flat"],
        "running")
    zp = Z["face"] + 8.0
    pc = np.array([o[0], o[1], zp])
    row("Gearmotor across its pocket",
        _ray_gap(parts["drive_block"], pc, [-u[1], u[0], 0]), MOTOR["w"], "running",
        note="the bushing locates it; the pocket only has to take it")
    row("Gearmotor along its pocket",
        _ray_gap(parts["drive_block"], pc, u), MOTOR["d"], "running")
    row("Gearbox bushing in the block's floor",
        hole_d(parts["drive_block"], o, Z["floor_lo"] + FLOOR_T / 2,
               MOTOR["bush_d"] / 2), MOTOR["bush_d"], "slip",
        note="this is what centres the driver on its axis")
    ze = Z["motor_top"] - MOTOR["enc"] / 2
    pe = np.array([o[0], o[1], ze])
    row("Encoder across its pocket",
        _ray_gap(parts["drive_block"], pe, [-u[1], u[0], 0]), MOTOR["enc_w"], "running",
        note="a routed PCB, +-0.15")
    # out to the outward wall and doubled: inward, the plug's channel opens
    ow = _ray_hit(parts["drive_block"], pe, u)
    row("Encoder along its pocket", None if ow is None else 2 * ow,
        MOTOR["enc_d"], "running")
    x0, x1, hw_, _ = _channel(Z)
    kc = o + u * ((x0 + x1) / 2 - 1.0) + np.array([0, 0, Z["motor_top"] - KEY_D / 2])
    tt = np.array([-u[1], u[0], 0])
    kh = _ray_gap(parts["drive_block"], kc, tt)
    row("Lid's key in the plug's channel", kh,
        None if kh is None else _key_width(parts["drive_cap"], kc, tt), "press",
        kind="printed in printed",
        note="it holds the lid, and holds the plug in its socket")
    ab = o + u * (POST_R - GENEVA_C) + np.array([-u[1], u[0], 0]) * SCREW_Y
    row("Lid's peg in the access bore",
        hole_d(parts["drive_block"], ab, Z["motor_top"] - 1.5, 3.25),
        shaft_d(parts["drive_cap"], ab, Z["motor_top"] - 1.5, 3.2), "press",
        kind="printed in printed")
    co, cb = _ctrl_frame(specimen)
    cp = rot(CTRL["phi"], [0, 0, 1])[:3, :3] @ np.array([*CTRL_BOSSES[0], 0.0])
    cp = cp + np.array([co[0], co[1], cb + CTRL["h"] - 1.5])
    row("Controller lid's peg in its boss",
        hole_d(parts["ctrl_box"], cp[:2], cp[2], CTRL_PEG[0] / 2),
        shaft_d(parts["ctrl_lid"], cp[:2], cp[2], CTRL_PEG[1] / 2), "slip",
        kind="printed in printed",
        note="drawn loose; the bore prints 0.2 small, so it closes to a snug slip")
    hm = polar(HOME["r"], HOME["phi"])
    row("Home magnet in the ring",
        hole_d(parts["rotor"], hm, L["ring_bot"] + 1.0, MAGNET[0] / 2),
        MAGNET[0], "running", note="loose on purpose, and glued")
    hc = np.array([hm[0], hm[1], L["base_top"] + RING_GAP - HOME["gap"] - 0.8])
    row("Home sensor in its boss",
        _ray_gap(parts["stator"], hc, polar(1.0, HOME["phi"])), HALL[0],
        "running")
    pp = polar(POST_R - GENEVA_BIAS, GENEVA_PHI, L["base_top"] - POST_SOCKET / 2)
    row("Drive post in its socket", _socket_width(parts["stator"], pp, u),
        POST_X, "running",
        note="it keys the drive's angle; the screw holds it down")
    for a in FOOT_PHI[:1]:
        f = polar(FOOT_R, a)
        row("Foot bolt through the base",
            hole_d(parts["stator"], f, L["base_top"] - FOOT_CBORE[1] - 1.5,
                   BOLT_R), 3.0, "clearance")
    row("Bar bolt through the arc",
        hole_d(parts["arc"], (BOLTS_X[0], Y_ARC), LEG_BOTTOM + 3.0, BOLT_R + 0.1),
        3.0, "clearance")
    sl = parts["sleeve_a"]
    bx, by = _sleeve_bore(sl)
    zs = sl.bounds[0][2] + 1.0
    row("Axle bolt through a sleeve", hole_d(sl, (bx, by), zs, AXLE_R), 3.0,
        "clearance")
    oc = sl.centroid[:2]
    row("Sleeve in a 688's bore", 8.0, shaft_d(sl, oc, zs, SLEEVE_R),
        "press", kind="printed shaft in steel bore",
        note="the bearing pressed onto its sleeve")
    ar = arc_radii(parts["arc"])
    row("Carriage lips on the arc", (ARC_RO + LIP_CLR) - (ARC_RI - LIP_CLR),
        ar[1] - ar[0], "running", note="they slide the arc's length with every ring")
    # the receiver's holes run across the arc (world y): measured as the
    # gap along the two axes square to them
    def y_hole(m, c):
        gx, gz = _ray_gap(m, c, [1, 0, 0]), _ray_gap(m, c, [0, 0, 1])
        return None if gx is None or gz is None else min(gx, gz)

    rq = _arc_to_world(SOCKET_U, CLAMP_V, MOUNT_FACE - 2.0)
    row("1/4-20 through the receiver", y_hole(parts["receiver"], rq), 6.35,
        "clearance")
    rs = _arc_to_world(*MOUNT_SCREWS[0], MOUNT_FACE - 2.0)
    row("Receiver screw through its bar", y_hole(parts["receiver"], rs), 3.0,
        "clearance", note="drawn 3.3 to locate it, the screws would not pass")
    # the pin, sectioned square to its axis half way along it
    sec = parts["receiver"].section(
        plane_origin=_arc_to_world(PIN_U, CLAMP_V, MOUNT_FACE + MOUNT_PIN[1] / 2),
        plane_normal=[0, 1, 0])
    pin_d = None
    if sec is not None:
        for Lp in sec.discrete:
            P = Polygon(Lp[:, [0, 2]])
            if P.contains(Point(PIN_U, CLAMP_V)):
                pin_d = 2 * np.sqrt(P.area / np.pi)
    row("Receiver's pin in the clamp's plain hole", ST02S["pin_hole"], pin_d,
        "press", kind="printed shaft in steel bore",
        note="it keys the clamp; the 1/4-20 holds it")
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
    """The box's walls, probed at mid-wall all along the quadrant: the
    share of points inside. 1.0 is a closed box with no slot."""
    pts = []
    for th in np.radians(np.arange(5.0, 85.1, 2.5)):
        for r_, h in ((ARC_RI + BOX_WALL / 2, 0.0), (ARC_RO - BOX_WALL / 2, 0.0),
                      (155.0, ARC_HW - BOX_WALL / 2), (155.0, -ARC_HW + BOX_WALL / 2)):
            pts.append([r_ * np.cos(th), Y_ARC + h, r_ * np.sin(th)])
    return round(float(np.mean(a.contains(np.array(pts)))), 4)


def _old_slot_width(a):
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


def geneva_follows(parts, shift=(0.0, 0.0), psi_step=3.0, search=1.5,
                   dth=0.05):
    """Can the ring, displaced by `shift` in plan, follow one whole turn
    of the driver? Unlike geneva_sweep, the ring is not held to the law:
    it is free to turn within its play, as a real one is, and at each
    driver angle any ring angle near the law that touches nothing will
    do. Returns the driver angles at which there is none -- a jam."""
    o, _, _ = _driver_frame()
    cm = tc.CollisionManager()
    cm.add_object("rotor", parts["rotor"])
    movers = {"driver": parts["driver"], "pin": pin_proxy()}
    for n, m in movers.items():
        cm.add_object(n, m)
    Tsh = np.eye(4)
    Tsh[:2, 3] = shift
    tries = sorted(np.arange(-search, search + 1e-9, dth), key=abs)
    jams = []
    for psi in np.arange(180.0, 540.0 + 1e-9, psi_step):
        T = rot(psi - 180.0, [0, 0, 1], origin=[o[0], o[1], 0])
        for n in movers:
            cm.set_transform(n, T)
        th0 = geneva_wheel(psi)
        for k in tries:
            cm.set_transform("rotor", Tsh @ rot(th0 + k, [0, 0, 1]))
            _, names = cm.in_collision_internal(return_names=True)
            # the pin is pressed into the crank's ribs: only the rotor counts
            if not any("rotor" in p_ for p_ in names):
                break
        else:
            jams.append(float(psi))
    return jams


# How far the lip may be off where the driver expects it, all causes
# together: the post's play in its running-fit socket (0.2), the ring
# centred by eccentrics turned in by hand, and the ring and the base
# shrinking differently (0.1-0.2 at r 73).
GENEVA_STACK = 0.6


def geneva_window(parts):
    """The ring off by GENEVA_STACK each way along the drive's line and
    across it must run; off by 1.6 mm toward the axis it must jam, or the
    check sees nothing."""
    _, u, t = _driver_frame()
    out = {}
    for name, v in (("in", -u), ("out", u), ("across", t), ("across_back", -t)):
        out[name] = len(geneva_follows(parts, v[:2] * GENEVA_STACK))
    out["control_jams"] = len(geneva_follows(parts, -u[:2] * 1.6)) > 0
    return out


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


def bought_statics(specimen=SPECIMEN):
    """What stands still and is not printed, but can be hit: the gearmotor
    and the cable. Everything that carries a wire is here."""
    return {"gearmotor": trimesh.util.concatenate(
                [_prim_mesh(q) for q in motor_prims(specimen)]),
            "cable": cable_proxy(specimen)}


def azimuth_sweep(parts, thetas=(ELEV[0], ELEV[1]), step=10.0,
                  specimen=SPECIMEN):
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
            for n, m in bought_statics(specimen).items():
                cm.add_object(n, m)
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


def sightlines(parts, specimen=SPECIMEN):
    """From the pupil at every frame of the protocol to points over the
    specimen's likely envelope -- from the rod tips to 40 mm above the
    focal point, on the axis and 20 mm off it -- do the drive, its cable
    or its controller ever stand in the way?"""
    obs = trimesh.util.concatenate(
        [parts[n] for n in ("driver", "drive_block", "drive_cap",
                            "ctrl_box", "ctrl_tray", "ctrl_lid")]
        + list(bought_statics(specimen).values()))
    z_lo = -specimen + PLATE_T + 13.0
    targets = [[0, 0, z] for z in (z_lo, 0.0, 40.0)]
    targets += [[20 * np.cos(a), 20 * np.sin(a), z]
                for a in np.radians(np.arange(0, 360, 45)) for z in (z_lo, 0.0)]
    targets = np.asarray(targets, float)
    origins, dirs, lens = [], [], []
    for p in PROTOCOL:
        th = np.radians(p["elev"])
        for phi in np.radians(np.arange(0.0, 360.0, p["step"])):
            P = R * np.array([np.cos(th) * np.cos(phi), np.cos(th) * np.sin(phi),
                              np.sin(th)])
            for t in targets:
                d = t - P
                origins.append(P)
                lens.append(float(np.linalg.norm(d)))
                dirs.append(d / lens[-1])
    loc, idx, _ = obs.ray.intersects_location(np.asarray(origins),
                                              np.asarray(dirs),
                                              multiple_hits=False)
    blocked = 0
    for x, i in zip(loc, idx):
        if np.linalg.norm(x - origins[i]) < lens[i]:
            blocked += 1
    return dict(rays=len(origins), blocked=int(blocked))


# The phone's lenses, as the camera app frames them: the 1x and 2x both
# off the main sensor, and the ultra wide, 120 degrees on its diagonal
# (13 mm equivalent). Across y and up the arc, held portrait.
def _fov_pair(diag_or_long, aspect_long=4.0 / 3.0, diag=False):
    t = np.tan(np.radians(diag_or_long / 2.0))
    if diag:
        t_long = t * aspect_long / np.hypot(aspect_long, 1.0)
    else:
        t_long = t
    return t_long / aspect_long, t_long          # tan of half: across, along


VIEW_LENSES = (dict(id="wide", ring=0, tan=_fov_pair(71.5)),
               dict(id="tele", ring=0, tan=_fov_pair(39.8)),
               dict(id="ultra", ring=1, tan=_fov_pair(120.0, diag=True)))
# Nearer than this to the lens, a body is in front of everything the
# specimen can be: in the foreground of the frame, not behind the tooth.
VIEW_FOREGROUND = R - 75.0


def view_targets(specimen=SPECIMEN):
    """The specimen's likely envelope, as `sightlines` takes it."""
    z_lo = -specimen + PLATE_T + 13.0
    t = [[0, 0, z] for z in (z_lo, 0.0, 40.0)]
    t += [[20 * np.cos(a), 20 * np.sin(a), z]
          for a in np.radians(np.arange(0, 360, 45)) for z in (z_lo, 0.0)]
    return np.asarray(t, float)


def phone_view(parts, specimen=SPECIMEN, kind=CAMERA_DEFAULT, extra=None,
               grid=(9, 12)):
    """From each of the phone's lenses at every frame of the protocol:

    - its rays to the specimen's envelope, against every body in the jig,
      the clamp, its own carriage and the rod field plate -- `blocked`
      must be 0;
    - a grid of rays across each lens's frame, and what the nearest thing
      each one meets is: a body nearer than VIEW_FOREGROUND is something
      standing in front of the specimen, and `foreground` counts them.

    The rotor side turns with the frame's azimuth, so the rays are cast
    into the rotor's frame for it and into the world for the rest.
    `extra` is a mesh added to the stator side: the negative control."""
    rot_names = set(ROTOR_SIDE) | set(CARRIAGE)
    stat = [m for n, m in parts.items() if n not in rot_names]
    stat += list(bought_statics(specimen).values())
    stat.append(rod_plate(specimen))
    if extra is not None:
        stat.append(extra)
    stat = trimesh.util.concatenate(stat)
    rotor_fixed = trimesh.util.concatenate([parts[n] for n in ROTOR_SIDE])
    cam = CAMERAS[kind]
    targets = view_targets(specimen)
    out = dict(rays=0, blocked=0, blocked_at=[], lenses={})
    gy, gv = grid
    for L in VIEW_LENSES:
        out["lenses"][L["id"]] = dict(rays=0, foreground=0, worst=None)
    for p in PROTOCOL:
        th = p["elev"]
        E = elev(th)
        moving = [rotor_fixed]
        for n in CARRIAGE:
            m = parts[n].copy(); m.apply_transform(E); moving.append(m)
        cl = clamp_mesh(); cl.apply_transform(E); moving.append(cl)
        moving = trimesh.util.concatenate(moving)
        for phi in np.arange(0.0, 360.0, p["step"]):
            Rz = rot(phi, [0, 0, 1])
            T = Rz @ E
            for L in VIEW_LENSES:
                c = np.asarray(cam["rings"][L["ring"]]["c"], float)
                o = (T @ np.r_[c, 1.0])[:3]
                fwd = (T[:3, :3] @ [-1.0, 0, 0])
                ax_y = T[:3, :3] @ [0, 1.0, 0]
                ax_v = T[:3, :3] @ [0, 0, 1.0]
                ta, tl = L["tan"]
                g = [fwd + a * ta * ax_y + b * tl * ax_v
                     for a in np.linspace(-1, 1, gy) for b in np.linspace(-1, 1, gv)]
                g = [d / np.linalg.norm(d) for d in g]
                to_t = [(t - o) for t in targets]
                dists = [float(np.linalg.norm(d)) for d in to_t]
                dirs = [d / n for d, n in zip(to_t, dists)] + g
                lim = dists + [VIEW_FOREGROUND] * len(g)
                O = np.repeat(o[None], len(dirs), 0)
                D = np.asarray(dirs)
                near = np.full(len(dirs), np.inf)
                Ri = np.linalg.inv(Rz)
                for mesh, M in ((stat, np.eye(4)), (moving, Ri)):
                    Oo = (M[:3, :3] @ O.T).T + M[:3, 3]
                    Dd = (M[:3, :3] @ D.T).T
                    loc, idx, _ = mesh.ray.intersects_location(Oo, Dd,
                                                               multiple_hits=False)
                    for x_, i in zip(loc, idx):
                        near[i] = min(near[i], float(np.linalg.norm(x_ - Oo[i])))
                nt = len(targets)
                hit_t = int(np.sum(near[:nt] < np.asarray(lim[:nt]) - 0.5))
                hit_g = int(np.sum(near[nt:] < VIEW_FOREGROUND))
                if L["id"] != "tele":           # the 2x is the 1x's middle
                    out["rays"] += nt
                    out["blocked"] += hit_t
                    if hit_t:
                        out["blocked_at"].append((L["id"], th, float(phi), hit_t))
                lv = out["lenses"][L["id"]]
                lv["rays"] += len(g)
                lv["foreground"] += hit_g
                if hit_g and (lv["worst"] is None or hit_g > lv["worst"][2]):
                    lv["worst"] = (th, float(phi), hit_g)
    return out


# The working volume: where a specimen can be and still be photographed.
# A point is seen from a frame if it is inside the 1x lens's frame and
# nearer the lens than whatever the lens's ray toward it meets first --
# the plate, the wing nut, the pedestal, the ring. Each frame's "what the
# lens meets first" is a depth image traced against every body, so the
# shadows are the real parts' shadows. A point seen from at least
# WORK_SHARE of the 108 frames is inside the working volume.
WORK_SHARE = 0.80
WORK_GRID = 2.0                       # mm between the points tested
WORK_BOX = ((-90.0, 90.0), (-90.0, 90.0), (-72.0, 110.0))
WORK_PIX = (90, 120)                  # depth image: across, up the arc
_WORK_MESH = {}                       # its surface, by specimen, for export


def specimen_mesh():
    """The scanned tooth, posed as the page poses it: glTF y-up turned
    z-up, centred over the axis, its base on the rods' tips."""
    path = os.path.join(HERE, "..", "models", "specimen", "meherrin-textured.glb")
    if not os.path.exists(path):
        return None
    m = trimesh.load(path, force="scene").to_geometry()
    m.apply_transform(rot(90.0, [1, 0, 0]))
    lo, hi = m.bounds
    plate_top = levels()["plat"] + PLATE_T
    m.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2,
                         plate_top + 13.0 - lo[2]])
    return m


def working_volume(parts, specimen=SPECIMEN, kind=CAMERA_DEFAULT, extra=None):
    """How many of the protocol's frames see each point of a grid round
    the focal point, through the 1x lens, with the jig's shadows."""
    rot_names = set(ROTOR_SIDE) | set(CARRIAGE)
    stat = [m for n, m in parts.items() if n not in rot_names]
    stat += list(bought_statics(specimen).values())
    stat.append(rod_plate(specimen))
    if extra is not None:
        stat.append(extra)
    stat = trimesh.util.concatenate(stat)
    rotor_fixed = trimesh.util.concatenate([parts[n] for n in ROTOR_SIDE])
    axes = [np.arange(a, b + 1e-9, WORK_GRID) for a, b in WORK_BOX]
    X, Y, Z = np.meshgrid(*axes, indexing="ij")
    P = np.c_[X.ravel(), Y.ravel(), Z.ravel()]
    count = np.zeros(len(P), np.int16)
    L = VIEW_LENSES[0]
    ta, tl = L["tan"]
    c = np.asarray(CAMERAS[kind]["rings"][L["ring"]]["c"], float)
    na, nb = WORK_PIX
    ga, gb = np.meshgrid(np.linspace(-1, 1, na), np.linspace(-1, 1, nb), indexing="ij")
    frames = 0
    for p in PROTOCOL:
        E = elev(p["elev"])
        moving = [rotor_fixed]
        for n in CARRIAGE:
            m = parts[n].copy(); m.apply_transform(E); moving.append(m)
        cl = clamp_mesh(); cl.apply_transform(E); moving.append(cl)
        moving = trimesh.util.concatenate(moving)
        for phi in np.arange(0.0, 360.0, p["step"]):
            frames += 1
            Rz = rot(phi, [0, 0, 1])
            T = Rz @ E
            o = (T @ np.r_[c, 1.0])[:3]
            f, ay, av = (T[:3, :3] @ np.eye(3)[:, k] for k in range(3))
            f = -f
            D = (f[None] + ga.reshape(-1, 1) * ta * ay[None]
                 + gb.reshape(-1, 1) * tl * av[None])
            D /= np.linalg.norm(D, axis=1)[:, None]
            depth = np.full(len(D), np.inf)
            Ri = np.linalg.inv(Rz)
            for mesh, M in ((stat, np.eye(4)), (moving, Ri)):
                Oo = np.repeat(((M @ np.r_[o, 1.0])[:3])[None], len(D), 0)
                Dd = (M[:3, :3] @ D.T).T
                loc, idx, _ = mesh.ray.intersects_location(Oo, Dd, multiple_hits=False)
                if len(idx):
                    d = np.linalg.norm(loc - Oo[idx], axis=1)
                    np.minimum.at(depth, idx, d)
            depth = depth.reshape(na, nb)
            # each grid point into this frame: inside it, and nearer than
            # what the lens meets along that line
            v = P - o
            x = v @ f
            a = (v @ ay) / (x * ta)
            b = (v @ av) / (x * tl)
            inside = (x > 1.0) & (np.abs(a) <= 1) & (np.abs(b) <= 1)
            ia = np.clip(np.rint((a + 1) / 2 * (na - 1)).astype(int), 0, na - 1)
            ib = np.clip(np.rint((b + 1) / 2 * (nb - 1)).astype(int), 0, nb - 1)
            dist = np.linalg.norm(v, axis=1)
            seen = inside & (dist < depth[ia, ib] - 1.0)
            count += seen
    shape = X.shape
    return dict(axes=axes, count=count.reshape(shape), frames=frames)


def work_report(wv, need=WORK_SHARE, specimen=None):
    """The working volume's size, at a share of the frames, and how much
    of a specimen lies outside it."""
    k = int(np.ceil(need * wv["frames"]))
    mask = wv["count"] >= k
    g = WORK_GRID
    out = dict(frames_needed=k, volume_cm3=round(float(mask.sum()) * g ** 3 / 1000.0, 1))
    if mask.any():
        idx = np.argwhere(mask)
        lo = [wv["axes"][i][idx[:, i].min()] for i in range(3)]
        hi = [wv["axes"][i][idx[:, i].max()] for i in range(3)]
        out["box"] = [[round(float(v), 1) for v in lo], [round(float(v), 1) for v in hi]]
        # across at the focal height, and how tall on the axis
        zi = int(np.argmin(np.abs(wv["axes"][2])))
        sl = mask[:, :, zi]
        xs = wv["axes"][0][sl.any(axis=1)]
        out["across_at_focus_mm"] = round(float(xs.max() - xs.min()), 1) if len(xs) else 0.0
        ci = int(np.argmin(np.abs(wv["axes"][0]))), int(np.argmin(np.abs(wv["axes"][1])))
        zs = wv["axes"][2][mask[ci[0], ci[1], :]]
        out["tall_on_axis_mm"] = round(float(zs.max() - zs.min()), 1) if len(zs) else 0.0
    if specimen is not None:
        V = specimen.vertices
        ii = [np.clip(np.rint((V[:, i] - wv["axes"][i][0]) / g).astype(int), 0,
                      len(wv["axes"][i]) - 1) for i in range(3)]
        ok = mask[ii[0], ii[1], ii[2]]
        out["specimen_outside_pct"] = round(100.0 * (1 - float(ok.mean())), 2)
        out["specimen_min_frames"] = int(wv["count"][ii[0], ii[1], ii[2]].min())
    return out


def work_mesh(wv, need=WORK_SHARE):
    """The working volume's surface, for the page."""
    from skimage import measure
    k = np.ceil(need * wv["frames"])
    f = np.pad(wv["count"].astype(float), 1, constant_values=0)
    verts, faces, _, _ = measure.marching_cubes(f, level=k - 0.5, spacing=(WORK_GRID,) * 3)
    verts += np.array([a[0] for a in wv["axes"]]) - WORK_GRID
    return trimesh.Trimesh(verts, faces[:, ::-1], process=True)


def pupil(theta):
    p = np.array([R, 0.0, CAM_Y - Y_ARC, 1.0])
    w = elev(theta) @ M_ARC @ p
    return w[:3]


def fits_plate(m, bed=246.0, height=250.0):
    e = m.extents
    return (e[2] <= height) and ((e[0] <= bed and e[1] <= bed))


# Every threaded joint, as a stack: how much the bolt has to cross before
# it reaches the insert (printed part, and a washer where there is one),
# how much thread the insert holds, and -- only where the bolt runs out
# through it into open air -- the relief under it. relief None is a blind
# joint: the bolt ends inside the insert (ENGAGE_MIN). The length follows from those three, so it
# cannot drift away from the geometry the way a typed list did.
#
# It had. The BOM said M4x16 for all eight M4 bolts, and at the arc bar
# that crosses 12 mm of bar and leaves 4 mm in a 7 mm insert -- four
# threads, on the joint that carries the arc and the whole carriage
# through a 90 degree sweep. The pawl, since gone, was the same story in M3. Measured
# on the built rotor: 11.00 mm of hole on each bolt axis, 0.00 beside it.
JOINTS = (
    # name, crosses, insert depth, relief, count
    ("arc bar to rotor pad", BAR_T - CBORE[1] + WASHER_M3[1], INSERT_STOP, None, 3,
     "M3"),
    ("bearing axle to tower", SLEEVE_H + SLEEVE_FL_H, INSERT_STOP, None, 3, "M3"),
    # the head sits on a washer in a 5 mm counterbore
    ("base to puck", BASE_T - FOOT_CBORE[1] + WASHER_M3[1], PUCK_THREAD,
     None, 3, "M3"),
    # down through the drive's arm and post into the base, its tip out
    # into the gap the pucks leave under the base
    ("drive post to base", driver_levels()["face"] - (levels()["base_top"]
                                                       - POST_SOCKET),
     INS_M3[1], BASE_T - POST_SOCKET - INS_M3[1] + CABLE_UNDER + 2.0, 1, "M3"),
    # through the receiver's bar into the saddle's face
    ("receiver to saddle", MOUNT_FACE - MOUNT_H0, INSERT_STOP, None, 2, "M3"),
)
_STOCK = (6, 8, 10, 12, 14, 16, 18, 20, 25, 30, 35)   # the VIGRUE kit, and McMaster's 35


def fasteners(specimen=SPECIMEN):
    """The bolts the page draws, where they sit: head down on its seat,
    shank the length the joint table gives it. Bought, so not in the
    file -- but drawn from the same numbers the BOM is."""
    L = levels(specimen)
    length = {n: bolt_len(c, i, r) for n, c, i, r, _, _ in JOINTS}
    return [
        dict(joint="base to puck", side="stator", r=1.5,
             head_r=HEAD_R, head_h=HEAD_H, len=length["base to puck"],
             at=[[round(float(v), 4) for v in
                  polar(FOOT_R, a, L["base_top"] - FOOT_CBORE[1] + WASHER_M3[1])]
                 for a in FOOT_PHI]),
        dict(joint="arc bar to rotor pad", side="rotor", r=1.5,
             head_r=HEAD_R, head_h=HEAD_H, len=length["arc bar to rotor pad"],
             at=[[x, Y_ARC, LEG_BOTTOM + BAR_T - CBORE[1]] for x in BOLTS_X]),
    ]


def bolt_len(crosses, insert, relief):
    """Blind (relief None): the longest stock length that ends inside the
    insert with ENGAGE_MIN of thread. Through: the shortest that fills the
    insert and stays inside the relief."""
    if relief is None:
        for L in sorted(_STOCK, reverse=True):
            if crosses + ENGAGE_MIN <= L <= crosses + insert:
                return L
        return None
    lo, hi = crosses + insert, crosses + insert + relief
    for L in _STOCK:
        if lo <= L <= hi:
            return L
    return None


def inserts():
    out = {INSERT_M3: 3 + 3 + 2 + 1 + 3,
           MOTOR["item"]: 1,
           HALL_ITEM: 1,
           "\u00d83 x 2 N52 disc magnet": 1,
           CABLE_ITEM: 1,
           "Seeed Studio XIAO ESP32S3": 1, MOTOR_R_ITEM: 1, CAP_ITEM: 1,
           PULLUP_ITEM: 1,
           SETSCREW_ITEM: 1, NUT_ITEM: 1, WASHER_ITEM: 6,
           "Pololu #2130 DRV8833 dual motor driver carrier": 1,
           "USB-C cable and 5 V 2 A USB power adapter": 1,
           WHEEL_BRG_ITEM: 6, f"M5x{THUMB_LEN:g} thumbscrew": 1, "M5 square nut": 1,
           QTR_ITEM: 1,
           f"\u00d83 x {PIN_L:g} steel dowel (the Geneva pin)": 1,
           CLAMP_ITEM: 1, PLATE_ITEM: 1}
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
    rep["geneva_window"] = geneva_window(parts)
    rep["race"] = race_contact(parts["rotor"], specimen)
    rep["pupil_radius"] = [round(float(np.linalg.norm(pupil(t))), 3)
                           for t in (ELEV[0], 45.0, ELEV[1])]
    rep["pupil_y"] = [round(float(pupil(t)[1]), 3) for t in (ELEV[0], ELEV[1])]
    rep["bar_seats"] = bar_seats(parts)
    rep["cameras_swept"] = camera_cases()
    rep["elevation_fouls"] = elevation_sweep(parts)
    rep["azimuth_fouls"] = azimuth_sweep(parts, specimen=specimen)
    rep["sightlines"] = sightlines(parts, specimen)
    pv = phone_view(parts, specimen)
    wv = working_volume(parts, specimen)
    sp = specimen_mesh() if specimen == SPECIMEN else None
    rep["working_volume"] = dict(share=WORK_SHARE, frames=wv["frames"],
                                 at_share=work_report(wv, WORK_SHARE, sp),
                                 every_frame=work_report(wv, 1.0, sp))
    _WORK_MESH[specimen] = work_mesh(wv)
    rep["phone_view"] = dict(rays=pv["rays"], blocked=pv["blocked"],
                             blocked_at=pv["blocked_at"][:10],
                             foreground={k: v["foreground"]
                                         for k, v in pv["lenses"].items()},
                             worst={k: v["worst"] for k, v in pv["lenses"].items()})
    vol = sum(float(m.volume) for m in parts.values()) / 1000.0
    rep["volume_cm3"] = round(vol, 1)
    rep["est_g"] = round(vol * PETG_G_PER_CM3, 0)
    rep["hardware"] = inserts()
    rep["carriage_balance"] = carriage_moment(parts)
    rep["phone_clear_mm"] = phone_clearance(parts)
    rep["thumbscrew"] = thumbscrew_reach()
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
            ("arc_box_closed", rep["slot_mm"] == 1.0),
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
            # the drive stands inside the camera's world: it may not stand
            # between the phone and the specimen in any frame
            ("drive_out_of_every_frame", rep["sightlines"]["blocked"] == 0),
            # every lens sees the whole specimen from every frame, and
            # nothing stands in front of it in the 1x's frame (or the 2x's,
            # its middle). The ultra wide sees the arc and the ring's pad
            # at its frame's lower corner on the horizon ring: reported,
            # not gated -- it is beside and below the specimen.
            ("phone_sees_the_specimen", rep["phone_view"]["blocked"] == 0),
            ("nothing_in_front_of_the_1x",
             rep["phone_view"]["foreground"]["wide"] == 0),
            # the specimen the jig is built for lies inside the volume seen
            # from WORK_SHARE of the frames
            ("specimen_in_the_working_volume",
             rep["working_volume"]["at_share"].get("specimen_outside_pct", 0.0) == 0.0),
            # what the drive can be off by in life, and it still runs
            ("geneva_runs_off_centre",
             rep["geneva_window"]["control_jams"]
             and not any(rep["geneva_window"][k]
                         for k in ("in", "out", "across", "across_back"))),
            ("phone_clear_of_carriage", rep["phone_clear_mm"] >= PHONE_CLEAR),
            ("thumbscrew_through_its_nut", rep["thumbscrew"]["through"]),
            # no ballast, and this is why: see carriage_moment
            ("carriage_balanced_enough",
             rep["carriage_balance"]["tongue_couple_n"] <= TONGUE_COUPLE_N)]


# --- export ------------------------------------------------------------
BRIM = {"brim_type": "outer_only", "brim_width": "5", "brim_object_gap": "0"}
BRIMMED = ("mount_screw", "mount_hex_nut", "mount_wing_nut", "drive_block")
FILAMENT = "Bambu PETG Basic @BBL P2S 0.4 nozzle"
PRINT_SETTINGS = {"wall_loops": "4", "sparse_infill_density": "25%",
                  "sparse_infill_pattern": "gyroid"}
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
    # Geneva lip and close its slots' mouths. Except the printed mount
    # hardware: the screw stands 55 mm tall on its head, an 11:1 lever,
    # and the hex nut's chamfers leave it 7 mm2 of first layer. The
    # Tinker set's nuts and bolts print with a brim each for the same
    # reasons, and print.
    # The card says PETG, four or five walls, 25-30% gyroid, and every fit
    # here is drawn to the shop's PETG table; the file says so too, rather
    # than opening on the template's PLA Basic and two walls.
    embed(out, brim=False, per_object={n: dict(BRIM) for n in BRIMMED},
          filament=FILAMENT, overrides=PRINT_SETTINGS)
    meta = assembly_meta(specimen, poses, parts, rep)
    if rep and "working_volume" in rep:
        meta["working_volume"] = rep["working_volume"]
    with zipfile.ZipFile(out, "a", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Metadata/orbital_jig.json",
                   json.dumps(meta, separators=(",", ":")))
        # the working volume's surface, for the capture page to show
        if specimen in _WORK_MESH:
            z.writestr("Metadata/working_volume.glb",
                       _WORK_MESH[specimen].export(file_type="glb"))
        # the bought parts McMaster drew, for the pages to draw as drawn
        for pid in VENDOR:
            if os.path.exists(vendor_path(pid)):
                z.write(vendor_path(pid), f"Metadata/hardware/{pid}.glb")
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
