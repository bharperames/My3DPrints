#!/usr/bin/env python3
"""The gazebo: eight spikes on a ring instead of four on a rectangle.

WHERE THE FOREST WENT

gen_tooth_stand.py opens by calling itself a forest of cones, and then
builds four. That was not an oversight: a shark tooth root is bilobate,
so the argument there is that the support is a QUADRILATERAL and never a
tripod -- two cones per lobe, fore and aft, and nothing in the notch
between the lobes. Four is the right answer for a root whose two lobes
come down in known places.

This stand answers a different question. The underside of a root is
hollow in the middle, and a ring of spikes set inside that hollow nests
it: the cups meet the cavity's wall all the way round, the wall slopes
down and outward, and the root centers itself on the ring under its own
weight instead of balancing on four points. Turn the tooth and nothing
changes, because a circle has no orientation.

So this is the opposite of the four-cone rule on purpose:

  - the ring is a CIRCLE, not the ellipse of the cross and fore/aft
    spans. Stretching it to those spans is what the four-cone stands do,
    and it produced a lumpy plate with the spikes bunched in two groups
    of four at the ends -- the lobes' pattern, not a ring's.
  - the ring is sized to the root's THICKNESS, not its width, because
    that is the binding dimension: a circle wider than the root's
    thickness puts half its spikes off the root entirely.
  - spikes sit ACROSS the notch rather than avoiding it. The notch is
    the hollow, and holding the hollow is the whole idea.

The deck under them is an octagon, with a spike standing on each corner
radius, and it is sized by what stops the stand tipping rather than by
what the ring needs: a tooth at the top of the band can lean 15 degrees
before its centroid passes the deck's edge.

Usage: gen_gazebo.py [--size gz_s|gz_m|all] [--out FILE.3mf]
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

import gen_tooth_stand as T                                   # noqa: E402
from gen_orbital_jig import rot, union, cut                    # noqa: E402

BASE_T = T.ARM_T            # the plate: 5 mm, flat on the table and the dock
ROUND = 1.5                 # inside corners of the plan
PHASE = 22.5                # degrees: a spike on each octagon corner
# Where the ring's WIDEST gap points, measured from +x. The deck's tip
# points along -y, so 0 puts the wide gaps out to the sides, square
# across the tooth: mounted, a root lies with its lobes across the base
# and its own tip over the base's tip, which is how a tooth is looked at.
WIDEST_AT = 0.0
DECK_SIDES = 8              # the gazebo's deck
LEAN_TARGET = 15.0          # degrees a top-of-band tooth may lean; sets the deck

# The spikes are thinner than the four-cone stands'. Two reasons, and the
# second is the one that matters: eight of them share what four carried,
# and a thinner spike finds its way between the ridges of a worn root
# instead of balancing on one. The stress below is the check that thinner
# has not become fragile -- it is a sideways newton at the tip, which is
# more than a tooth ever puts there.
# The spikes are SLENDER, and deliberately springy. A root nesting in
# the ring should sink until it is carried, spreading the spikes a
# little as it goes, so each one takes up its own share of an uneven
# surface instead of three of them carrying everything. Two numbers set
# that: a Ø1.6 tip, thinner than anything else in the family and near
# the Ø1.3 the original spec asked for, and a 1.5 degree flank instead
# of the family's 3.5, which is what actually buys the flex -- stiffness
# goes as the fourth power of the radius, so the taper matters far more
# than the tip does.
#
#   spread at 0.25 N       0.18 mm on the S, 0.27 on the M
#   worst stress at 1 N    11.3 MPa, against PETG's ~50
#
# 0.25 N is one spike's share of the outward push from a 500 g tooth
# settling on a wall sloping about 25 degrees; 1 N at the tip is the
# knock-it-with-a-finger probe the other stands are checked against, and
# it would take about 4.4 N to break one. Ø1.3 at the same taper would
# roughly double the spread and halve that margin.
# Ø2.0 tips on a 2.5 degree flank, not the Ø1.6 on 1.5 that broke.
# The first set snapped about 2 mm up and the reason was in the profile,
# not the filament: the fillet necks the spike from Ø5.1 at the deck to
# Ø2.4 in 1.4 mm and the flank barely grows after that, so the spike is
# a thin rod with a stress riser where the cove ends -- exactly where
# they broke. Measured along the real profile rather than a pure cone,
# the old spike took 4.5 N at the tip before yielding; this one takes
# 12-16. The flex went with it, and that is the trade: a printed spike
# can be thin or it can be strong. The thin, springy job now belongs to
# the carbon rods, which are half the diameter and still take 8.7 N.
# Ø1.6 on a 1.8 degree flank. The Ø2.0 on 2.5 that came before it was
# sized against PETG's modulus by mistake and printed in PLA, which is
# twice as stiff: it reads 0.026 mm of give on the M where the arithmetic
# claimed 0.054, and in the hand it is a post. This gives three times
# that and still takes 9 to 11 N at the tip in PLA, against the 8 the
# spikes that actually snapped would have taken in the same material.
TIP_R = 0.8                 # Ø1.6
HALF = 1.8                  # degrees off vertical
FILLET = 2.0                # the cove onto the deck

# Three widths, not one. An even ring offers a root exactly one gap to
# drop a ridge into; graded, it offers three and the tooth can be turned
# to whichever fits. The weights are six gaps of 3, 4 and 5 twelfths of
# a half turn -- which is the even eight with one spike and its opposite
# taken out, and the spacing then evened up -- so the ring still
# balances after half a turn.
#
#   S ring Ø12    2.99 / 4.40 / 5.71 mm of clear air
#   M ring Ø16    4.52 / 6.40 / 8.14
#
# Eight graded would have been tighter than it is useful: 2, 3, 4, 3 on
# the S ring put its narrow pair 1.5 mm apart, which is not a slot.
GRADED = [3, 4, 5, 3, 4, 5]

# The M and L carry pins a quarter taller than the family's: a bigger
# root sits deeper in its own hollow, and the lobes outside the ring
# need somewhere to hang. Height costs nothing in stress -- the worst
# section on a tapered spike sits at r_tip / (2 tan(half)), 15.3 mm up,
# and stays there however tall the spike is -- but it does cost stiffness,
# so the L gives up half a millimeter of spread and stays inside the gate.
#
# 1 mm carbon fiber rods go in the two ...r bases instead of printed
# spikes. A rod is about five times stiffer than the spike it replaces
# and half the diameter at the tip, so it is a different instrument: a
# sharp rigid point rather than a springy one. The two bases exist to
# find the hole, since nobody knows what this printer does to a hole
# this small -- it takes about 0.15 mm off a Ø3 one, and a Ø1.4 hole is
# only three extrusions wide, where that error is proportionally worse.
ROD_D = 1.0
# Measured, not guessed: a gauge of ten bores read with the rod itself,
# in Bambu PLA Basic on the 0.4 nozzle. A small vertical bore prints
# about half a millimeter under its drawn size -- not the 0.15 a Ø3 hole
# loses -- so Ø1.5 drawn is the friction fit that holds a 1 mm rod
# without glue. Ø1.4 would not take it and Ø1.6 let it drop through, and
# the boss row and the flat row read the same. Below Ø1.2 drawn a bore
# stops holding a round shape at all, which is the floor for any socket
# here.
# The filament decides this, and by more than the geometry does. Two
# PLAs are 0.2 mm apart, while a bore up a boss, the same bore in a
# solid plate and the same bore with neighbors 3.6 mm away all read
# alike. Whichever is loaded, read the gauge before drawing a socket.
# Measured with the gauge, one entry per filament actually read. A
# material that is not in here has no entry ON PURPOSE: the design
# refuses rather than interpolating, because the two PLAs sit 0.2 mm
# apart and nothing about the geometry predicts that gap.
_MAT = "pla_basic"          # which filament the module is drawing for
MATERIALS = {
    # bore: what to draw for a 1 mm rod that has to STAND in the socket
    # unglued -- a friction fit, and by definition the tightest size
    # that still admits the rod. loss: what the printer takes off a bore
    # that size, which is how the bore was arrived at.
    #
    # free: the next rung up the same ladder, where the rod slides in
    # and falls out again. That is the right size wherever the rod is
    # glued, and it is the size the FIELD wants. A friction fit has no
    # margin left in it by construction: the rod field was drawn at
    # PETG's Ø1.45 because that read as a perfect fit on the probe,
    # and not one of its 56 bores would take a rod. The toolpaths were
    # identical -- 1.43 in the field against 1.42 on the probe -- so
    # nothing was wrong with the geometry or the slicing. A bore drawn
    # at the tightest size that works on one coupon has nothing left to
    # give on a different part, and a field asks the same question 56
    # times over.
    "pla_basic": dict(bore=1.5, free=1.6, loss=0.50, label="PLA Basic"),
    # silk's upper rung is the next line of the gauge rather than a
    # reading: Ø1.7 was measured as the fit, Ø1.8 was never tried
    "pla_silk": dict(bore=1.7, free=1.8, loss=0.67, label="PLA Silk"),
    # read on the probe: Ø1.45 a perfect fit, Ø1.50 acceptable but
    # looser, Ø1.55 and the rod falls out.
    "petg": dict(bore=1.45, free=1.55, loss=0.45, label="PETG Basic"),
}

# --- the 56-bore field, and NOTHING ELSE --------------------------------
# These numbers belong to one part. They are kept out of MATERIALS on
# purpose, because everything in that table is a reading that transfers
# between parts and none of this does.
#
# A 56-bore field at 3.58 mm centers in a \u00d859 disc prints its holes
# 0.10-0.15 mm smaller than a 14-bore strip at 5.0 mm does -- same drawn
# size, same 7 mm depth, and a toolpath the slicer draws the same to a
# hundredth. The strip says \u00d81.45 for PETG and this field wants
# \u00d81.56. Why a crowded plate closes its holes further is NOT
# established; only that it does, on this part, in this filament.
#
# So: do not reach for FIELD_BORE from any other design, and do not
# extend the pattern to a new spacing, thickness or outline without
# grading that part. Two plates were printed on the belief that a number
# read on one coupon carries to another, and neither took a rod.
FIELD_BORE = {
    # read ring by ring on a graded field: \u00d81.53 very tight,
    # \u00d81.56 right, \u00d81.59 and up loose
    "petg": dict(d=1.56, read=True,
                 note="read on a graded field, PETG Basic, 0.4 nozzle"),
    # INFERRED, not measured: each carries PETG's +0.11 over its own
    # strip reading. That is the same species of guess that produced two
    # unusable plates, so it is labeled everywhere it surfaces -- in the
    # report, on the card, and in the archive. Grade the spool first.
    "pla_basic": dict(d=1.61, read=False,
                      note="inferred from PETG's offset; not graded"),
    "pla_silk": dict(d=1.81, read=False,
                     note="inferred from PETG's offset; not graded"),
}
ROD_BORES = {k: v["bore"] for k, v in MATERIALS.items()}
ROD_BORE = MATERIALS["pla_basic"]["bore"]
ROD_FREE = MATERIALS["pla_basic"]["free"]
ROD_FIELD = FIELD_BORE["pla_basic"]["d"]
ROD_LOSS = MATERIALS["pla_basic"]["loss"]
MIN_BORE = 1.2                # under this it is not a hole, it is a dimple
# foot radius, top radius, height. Widened from (2.6, 1.75): at Ø1.75
# the wall round a Ø1.9 hole is 0.8 mm, which is two extrusions with
# nothing left over, so the slicer gave the hole no perimeter of its own
# and filled the ring with gap fill -- the ragged, half-closed sockets
# that came off the first plate. At 2.4 the wall is 1.45 mm and the bore
# gets a loop.
ROD_BOSS = (3.2, 2.4, 8.0)
ROD_SEAT = 4.0                # the hole reaches this far into the deck

# --- the gauge --------------------------------------------------------
# Two sockets is a poor way to find a constant. Every drawn size here is
# a socket identical to the real one -- same boss, same depth, same
# bore -- so the rod itself reads the answer off the part: the first one
# it enters without force is the number to draw from then on, for THIS
# printer and THIS material. The bar is wedge shaped so the small end is
# obvious, and a dimple marks it.
# Two rows, because the two sockets on these parts are not the same
# hole. One is bored up a slim boss, where the wall is a millimeter and
# a half and the slicer has to fit a loop inside it; the other goes
# straight into a solid plate, which is what the rod field is. They
# print differently and there is no reason to assume they close by the
# same amount.
# From the rod's own diameter upward. Starting at Ø1.3 was a PETG
# number: there, a Ø1.3 bore in a thin-walled boss came out closed. PLA
# shrinks and oozes less and the wall is thicker now, so the tightest
# bore that still takes the rod could easily be below 1.3, and a gauge
# that starts there would report 1.3 as the answer without ever showing
# that 1.1 was the answer. Ø1.0 cannot admit a Ø1.0 rod after any
# shrinkage at all, which makes it the control: if it does, something
# is wrong with the reading rather than with the guess.
GAUGE_D = [round(1.0 + 0.1 * k, 1) for k in range(11)]
GAUGE_PITCH = 10.5
GAUGE_ROW = 15.0            # between rows
# A third row, crowded: the same ladder again, but each bore flanked by
# two more at the rod field's own spacing. The field is the case nobody
# can explain -- its bores sit in a solid plate with material to spare
# and still would not take a rod in PETG, where the same size up a boss
# would. Either it is the material or it is the crowding, and one row
# separates them.
GAUGE_CROWD = 3.58          # the field's own center-to-center spacing
# And a patch of the field itself, at the far end: 25 bores at the size
# the ladder settled on, packed the way the field packs them. A triplet
# shows whether two neighbors close a bore; a 5 x 5 shows whether
# twenty-four do, which is nearer what the field actually asks of the
# printer.
# The close-spaced row now steps in HALF-tenths across each column, so
# it augments the ladder instead of repeating it: the hole under a label
# is that size, its neighbors a twentieth either side. It still sits at
# the field's own spacing, so it answers the crowding question at the
# same time -- and so far the answer is that crowding changes nothing.
GAUGE_FINE = 0.05

# A pocket-sized gauge for one question: the bore, in a filament that
# has not been read yet. Thirteen bores in half-tenths around Ø1.5,
# in the field's own plate and depth, labeled every other one.
PROBE_D = [round(1.35 + 0.05 * k, 2) for k in range(14)]
PROBE_PITCH = 5.0
PROBE_W = 16.0
# A millimeter scale down the long edge, in the strip between the
# crowded row and the plate's edge. The coupon is already a ruler's
# shape and the strip was empty.
# Every 2 mm, not every 1. Measured against the slicer rather than
# guessed: a tick 0.8 mm wide is not cut at all -- the toolpath runs
# straight through all 70 of them -- and 1.0 mm is the narrowest the
# 0.4 nozzle will open. At 1 mm pitch a 1.0 wide tick leaves no land
# between ticks, so the scale becomes one continuous groove. 1.0 wide
# on a 2 mm pitch gives a millimeter of tick and a millimeter of plate,
# and that is the finest scale this nozzle can say.
RULE_W = 1.0
RULE_PITCH = 2.0
RULE_LEN = (1.3, 1.3, 3.4)  # minor, and every 10 mm
# No bar added for the unit. Extending the plate 11 mm to make room for
# it bought a blank slab the width of the part, which is the one thing a
# test coupon should not carry. The band between the flat row and the
# crowded row is already empty for the whole length; the unit goes
# there, at the head.
GAUGE_TEXT = 4.4            # cap height of the etched size
GAUGE_ETCH = 0.6            # how deep it is cut into the plate
E_CF = 100000.0               # MPa, pultruded carbon fiber

# --- the rod field ----------------------------------------------------
# A field of holes to put rods wherever a root wants them, rather than
# six fixed places. The pattern is MIRROR-SYMMETRIC about both axes,
# which is the whole trick: a hole at (x, y) brings (-x, y), (x, -y) and
# (-x, -y) with it, and those four are an exact rectangle, 2x across by
# 2y fore and aft -- the support quadrilateral the four-cone stands are
# built on. So every hole in a quadrant IS one available rectangle, and
# choosing the pattern is choosing which rectangles exist.
#
# A golden-angle spiral was the first idea and it is the wrong tool. Its
# defining property is that nothing ever lines up, which is exactly what
# a rectangle needs. Scored against every rectangle from 10 x 5 to
# 51 x 26 mm, at 80 holes:
#
#     pattern            worst miss    mean miss
#     golden spiral        17.2 mm       5.6 mm
#     regular grid         10.3          4.4
#     chosen here           6.3          3.0
#
# What is chosen here is a covering set: start from the four spans the
# cone stands already use, then add the hole that most reduces the
# average miss, and repeat, subject to no two holes coming closer than
# FIELD_MIN_SP. The spiral's uniformity buys nothing a centerd
# rectangle can use.
# --- the tooth-shaped deck --------------------------------------------
# The deck can be a meg tooth in plan instead of an octagon: a broad
# bilobate root at the top, a notch between the lobes, and a blade
# tapering to a tip. Half-width 1, root up, tip down; the left half is
# the mirror of this.
#
# Stability is not assumed from the shape. The support a flat plate
# gives is the CONVEX HULL of what it stands on -- the notch is bridged,
# so it costs nothing -- and the number that matters is the smallest
# distance from the pivot to that hull in any direction. The deck is
# centerd on the hull's pole of inaccessibility, which is the point that
# makes that smallest distance as large as it can be, and then scaled
# until it meets the same 15 degree lean the octagon is held to.
# The outline is a real specimen's, not a drawing: the silhouette of
# sale145_tooth_meherrin.glb projected along its thinnest axis, closed
# at 1 mm and simplified to half a millimeter, normalized to half-width
# 1 with the root up and the tip down. It is faintly asymmetric because
# the tooth is, and the centring below does not care.
TOOTH = [
    (+0.046, +0.836), (+0.320, +1.011), (+0.494, +1.169), (+0.560, +1.253),
    (+0.670, +1.337), (+0.754, +1.339), (+0.866, +1.293), (+0.940, +1.170),
    (+1.000, +0.872), (+0.993, +0.702), (+0.953, +0.579), (+0.865, +0.443),
    (+0.726, +0.123), (+0.489, -0.570), (+0.324, -0.934), (+0.074, -1.297),
    (-0.002, -1.380), (-0.088, -1.435), (-0.146, -1.420), (-0.239, -1.317),
    (-0.529, -0.798), (-0.650, -0.465), (-0.763, +0.001), (-0.999, +0.697),
    (-1.000, +0.741), (-0.976, +0.778), (-0.983, +1.035), (-0.941, +1.252),
    (-0.896, +1.379), (-0.837, +1.435), (-0.768, +1.434), (-0.687, +1.390),
    (-0.077, +0.880),
]
# Two more silhouettes, these ones drawn rather than scanned: a
# snaggletooth's hooked blade and a tiger's notched heel. They are
# stylised -- recognizable as the species, not measured from one -- and
# they go through the same centring and scaling as the meg, so a stand
# wearing either is held to the same lean.
SNAGGLE = [
    (+0.05, +0.80), (+0.35, +1.00), (+0.66, +1.10), (+0.88, +1.02),
    (+1.00, +0.82), (+0.96, +0.58), (+0.86, +0.36), (+0.70, +0.12),
    (+0.52, -0.16), (+0.36, -0.46), (+0.18, -0.78), (+0.00, -1.05),
    (-0.18, -1.22), (-0.34, -1.26), (-0.42, -1.14), (-0.38, -0.92),
    (-0.30, -0.62), (-0.34, -0.30), (-0.46, +0.02), (-0.64, +0.36),
    (-0.82, +0.62), (-0.95, +0.84), (-1.00, +1.00), (-0.88, +1.10),
    (-0.62, +1.10), (-0.30, +0.92),
]
TIGER = [
    (+0.05, +0.78), (+0.32, +0.94), (+0.60, +1.02), (+0.85, +0.96),
    (+1.00, +0.78), (+0.98, +0.54), (+0.88, +0.34), (+0.74, +0.18),
    (+0.58, +0.06), (+0.66, -0.14), (+0.56, -0.34), (+0.36, -0.22),
    (+0.22, -0.38), (+0.04, -0.60), (-0.16, -0.76), (-0.36, -0.84),
    (-0.52, -0.78), (-0.58, -0.62), (-0.62, -0.40), (-0.74, -0.10),
    (-0.90, +0.24), (-1.00, +0.56), (-0.96, +0.82), (-0.82, +0.98),
    (-0.56, +1.04), (-0.28, +0.92),
]
SHAPES = {"meg": TOOTH, "snaggletooth": SNAGGLE, "tiger": TIGER}
RELIEF_H = 2.5              # how far the tooth stands off the pedestal
RELIEF_D = 5.0              # and how far in it takes to get there
RELIEF_RIM = 2.5            # flat pedestal left showing outside the mound

FIELD_MIN_SP = 3.5            # centers, so 2 mm of wall between Ø1.5 holes
# Five rings, graded, because predicting this field has failed twice:
# drawn O1.45 took no rod, and O1.475 through a deeper funnel took no rod
# either. The probe cannot answer it -- a 14-bore strip is not a 56-bore
# disc, which is the whole lesson -- so the coupon is the field itself
# with its rings stepped.
#
# Coarse and WIDE on purpose. The step from the plate that failed to the
# plate that failed again was 0.025 mm -- 25 microns, 6% of one
# extrusion -- against a part where 56 bores out of 56 refused the rod.
# A total failure is not rescued by a change smaller than the printer's
# own precision. These five span +0.025 to +0.625 over the size that
# failed, and if the outermost ring is still shut then the answer is not
# a size at all, which is worth learning in one print rather than five.
FIELD_GRADE = [1.50, 1.65, 1.80, 1.95, 2.10]
GRADE_ETCH_SCALE = 2.6      # cap height. It cannot go up: the rings are
                            # 3 mm apart radially and a taller label
                            # touches the next ring's bores.
# Which ring a hole belongs to has to be readable at arm's length, and
# the field is far too crowded to draw a line through a ring: a polyline
# joining one ring's holes runs straight over the next ring's, at every
# width, and a groove between two rings has nowhere to go either -- the
# closest pair of rings is 3 mm apart and the mouths eat most of that.
#
# So the zones are TERRACED instead. Alternate rings sit one layer lower
# than their neighbors, which needs no clearance at all because the
# holes simply pass through the step. Each terrace holds one bore size
# and its own etched label. The bores stay exactly 7 mm deep either way:
# on a lowered terrace the hole starts a layer lower too, and it is the
# floor beneath that gives up the 0.2 mm, not the depth under test.
GRADE_BAND_EDGES = (9.5, 14.0, 18.0, 21.5)
GRADE_TERRACE = 0.2         # one layer, so the step lands on a layer line
GRADE_ETCH_BOLD = 0.10      # so the STROKES grow instead. At this cap the
                            # glyph's own strokes are 0.63 mm, thinner
                            # than the 0.82 that the gauge proved cuts;
                            # widened they reach 0.90, and the 0 keeps
                            # its counter, which a fatter pen would fill.

FIELD_T = 8.0                 # the field deck is thicker: the hole IS the guide
FIELD_R = 29.5                # the deck's corner radius

# The pattern is CONCENTRIC RINGS whose phase turns with the radius, so
# the holes read as spiral arms. Each ring is eight holes at +/-a,
# 90-a and so on, which is mirror-symmetric about both axes and so
# offers, from one ring: a circle to nest a hollow root on, two gap
# widths round that circle, and one exact rectangle. Four more mirror
# quads fill in rectangles the rings miss.
#
# Scored against every rectangle from 10 x 5 to 51 x 26 mm and every
# ring from Ø10 to Ø50, at about the same hole count:
#
#     pattern                 rect worst   rect mean   rings
#     golden-angle spiral       17.2 mm      5.6 mm    none exact
#     regular grid              10.3         4.4       none exact
#     rectangle-optimal set      6.3         3.0       none exact
#     rings + fills, here        8.1         3.7       5 exact
#
# The spiral is the wrong tool and the numbers say so: its defining
# property is that nothing lines up, and a centerd rectangle is nothing
# BUT lining up. Rings cost a millimeter or two of rectangle accuracy
# and buy the configuration this stand is actually for.
#
# (radius, phase) and the fill quads' (x, y), chosen by a greedy search
# seeded with the M and L gazebo rings and the four cone-stand spans.
FIELD_RINGS = [(8.0, 26.0), (11.0, 14.0), (20.5, 22.0), (16.0, 34.0),
               (23.5, 12.0)]
FIELD_FILLS = [(16.0, 4.5), (20.5, 11.0), (10.0, 7.0), (16.5, 11.0)]

SIZES = [
    dict(id="gz_sg", name="Gazebo S", teeth=(25.0, 55.0), ring=12.0,
         gaps=GRADED, cone=16.0, tip=TIP_R, half=HALF, fillet=FILLET,
         cross=20.0, fore=10.0, deck="relief"),
    dict(id="gz_mg", name="Gazebo M", teeth=(50.0, 95.0), ring=16.0,
         gaps=GRADED, cone=25.0, tip=TIP_R, half=HALF, fillet=FILLET,
         cross=38.0, fore=16.0, deck="relief"),
    # the L's flank is 1.8 degrees, not the family's 1.5: at 30 mm tall
    # a 1.5 degree spike gives 0.53 mm, and the spike should feel the
    # same in the hand whatever size the stand is. 1.8 puts it at 0.398
    # against the M's 0.396, for a root Ø3.49 instead of Ø3.17 -- a
    # thicker cone carrying the same give, which is the trade asked for.
    # The tip stays Ø1.6, so nothing about the point changes.
    dict(id="gz_lg", name="Gazebo L", teeth=(90.0, 150.0), ring=22.0,
         gaps=GRADED, cone=30.0, tip=TIP_R, half=1.95, fillet=FILLET,
         cross=60.0, fore=20.3, deck="relief"),
    # the pair that answers the hole question: same base as the M, one
    # drawn tight and one drawn loose, told apart by the dimples on the
    # deck -- one dot is the tighter
    # one size now, because the gauge answered it: Ø1.5
    # Three of them, the same three the spiked stands come in: a rod
    # base is its spiked size with sockets where the spikes were, so a
    # small root is no more obliged to stand on the large deck here than
    # it is over there. The rod length follows `cone` exactly as the
    # spike height did, so a size holds a tooth at the height it always
    # held it at.
    dict(id="gz_sr", name="Gazebo S, carbon rods", teeth=(25.0, 55.0),
         ring=12.0, gaps=GRADED, cone=16.0, tip=TIP_R, half=HALF,
         fillet=FILLET, cross=20.0, fore=10.0, rods=ROD_BORE,
         deck="relief"),
    dict(id="gz_mr", name="Gazebo M, carbon rods", teeth=(50.0, 95.0),
         ring=16.0, gaps=GRADED, cone=25.0, tip=TIP_R, half=HALF,
         fillet=FILLET, cross=38.0, fore=16.0, rods=ROD_BORE,
         deck="relief"),
    dict(id="gz_lr", name="Gazebo L, carbon rods", teeth=(90.0, 150.0),
         ring=22.0, gaps=GRADED, cone=30.0, tip=TIP_R, half=1.95,
         fillet=FILLET, cross=60.0, fore=20.3, rods=ROD_BORE,
         deck="relief"),
    # one base for everything: a field of holes to stand rods in
    # the other way to wear a tooth: a plain pedestal with the
    # silhouette standing 2.5 mm proud of it, spikes rising out of that
    # It carries the L's ring, Ø22 -- the pattern measured off the
    # printed octagon stand at 13.4 mm between the posts either side of
    # the wide gap, which is the one that held a meg root.
    dict(id="gz_mgs", name="Gazebo M, snaggletooth in relief",
         teeth=(50.0, 95.0), ring=16.0, gaps=GRADED, cone=25.0, tip=TIP_R,
         half=HALF, cross=38.0, fore=16.0, deck="relief",
         shape="snaggletooth"),
    dict(id="gz_mgt", name="Gazebo M, tiger in relief", teeth=(50.0, 95.0),
         ring=16.0, gaps=GRADED, cone=25.0, tip=TIP_R, half=HALF,
         cross=38.0, fore=16.0, deck="relief", shape="tiger",
         draft=True),
    dict(id="gz_probe", name="Rod bore probe", teeth=(90.0, 150.0),
         ring=22.0, gaps=GRADED, cone=30.0, tip=TIP_R, half=1.95,
         cross=60.0, fore=20.3, rods=PROBE_D[0], probe=True),
    dict(id="gz_gauge", name="Rod socket gauge", teeth=(90.0, 150.0),
         ring=22.0, gaps=GRADED, cone=30.0, tip=TIP_R, half=1.95,
         cross=60.0, fore=20.3, rods=GAUGE_D[0], gauge=True),
    dict(id="gz_rfg", name="Rod field, graded", teeth=(25.0, 150.0),
         ring=16.0, gaps=GRADED, cone=25.0, tip=TIP_R, half=HALF,
         fillet=FILLET, cross=38.0, fore=16.0, rods=FIELD_GRADE[0],
         field=True, grade=True),
    dict(id="gz_rf", name="Gazebo rod field", teeth=(25.0, 150.0), ring=16.0,
         gaps=GRADED, cone=25.0, tip=TIP_R, half=HALF, fillet=FILLET,
         cross=38.0, fore=16.0, rods=ROD_FIELD, field=True),
]
BY_ID = {s["id"]: s for s in SIZES}
ALL_IDS = [s["id"] for s in SIZES]


# --- the ring ----------------------------------------------------------
def ring_r(spec):
    return spec["ring"] / 2.0


def weights(spec):
    """The gaps round the ring, as relative weights. All ones is the
    even ring; anything else grades it."""
    return list(spec.get("gaps") or [1] * spec.get("n", 8))


def spikes(spec):
    """The hole or cup centers. On a field base that is the whole field;
    otherwise the ring, spaced by the gap weights.

    An even ring offers a root exactly one width to drop a ridge into.
    A graded one offers three: the weights run 2, 3, 4, 3 and repeat, so
    every second gap is the middle one and the narrow and wide sit
    either side of it. The pattern repeats after half a turn, so the
    ring still balances and a tooth can be spun to whichever slot fits.
    """
    if spec.get("probe"):
        n = len(PROBE_D)
        x0 = -PROBE_PITCH * (n - 1) / 2.0
        return [(round(x0 + PROBE_PITCH * k, 3), 2.5) for k in range(n)]
    if spec.get("gauge"):
        n = len(GAUGE_D)
        x0 = -GAUGE_PITCH * (n - 1) / 2.0
        return [(round(x0 + GAUGE_PITCH * k, 3), y)
                for y in (GAUGE_ROW, 0.0, -GAUGE_ROW)
                for k in range(n)]
    if spec.get("field"):
        # the graded plate spends one hole a ring on its label, and a
        # probe that rays down a hole that is not there reads the top
        # face and calls the field seven millimeters out of plane
        return field_grade_holes(spec)[0] if spec.get("grade") \
            else field_holes(spec)
    w = np.array(weights(spec), dtype=float)
    edges = np.concatenate([[0.0], np.cumsum(w)])[:-1] / w.sum() * 360.0
    span = w / w.sum() * 360.0
    # turn the ring so the widest gap's bisector lands on WIDEST_AT
    k = int(np.argmax(span))
    turn = WIDEST_AT - PHASE - (edges[k] + span[k] / 2.0)
    r = ring_r(spec)
    return [(round(float(r * np.cos(np.radians(PHASE + a + turn))), 4),
             round(float(r * np.sin(np.radians(PHASE + a + turn))), 4))
            for a in edges]


def pad_r(spec):
    return T.cone_foot_r(spec["cone"], spec) + T.PAD_MARGIN


def contact_z(spec):
    return deck_z(spec) + spec["cone"]


def dish_z(spec):
    return contact_z(spec) - T.dish_d(spec)


def tooth_norm(shape="meg"):
    """The outline at half-width 1, centerd on the pole of
    inaccessibility of its own hull, with that pole's clearance."""
    from shapely.ops import polylabel
    poly = Polygon(SHAPES[shape])
    hull = poly.convex_hull
    # center on the largest circle that fits in the MATERIAL, not in the
    # hull: centerd on the hull's, the notch came within a third of a
    # half-width of the pivot and the deck had to be scaled to twice the
    # size to get material under the outermost cone feet
    c = polylabel(poly, 0.001)
    poly = affine(poly, -c.x, -c.y)
    hull = affine(hull, -c.x, -c.y)
    # two different radii, and both matter: the HULL's is what holds the
    # stand up, because a flat plate is supported on its hull and the
    # notch is bridged. The POLYGON's is what there is material at, and
    # it is smaller -- the notch really is missing. Sizing on the hull
    # alone hung the cone feet nearest the notch out over thin air.
    return (poly, float(hull.exterior.distance(Point(0.0, 0.0))),
            float(poly.exterior.distance(Point(0.0, 0.0))))


def affine(poly, dx, dy):
    from shapely import affinity
    return affinity.translate(poly, dx, dy)


def lean_r(spec):
    """How far the support has to reach, in its worst direction, for a
    tooth at the top of the band to lean LEAN_TARGET before going over."""
    h = spec["teeth"][1] * 0.44
    return float(np.tan(np.radians(LEAN_TARGET)) * (contact_z(spec) + h))


def tooth_plan(spec, need=None):
    """The silhouette, scaled so the support it gives in its WORST
    direction is `need` -- by default whatever the lean rule asks for."""
    from shapely import affinity
    poly, r_hull, r_poly = tooth_norm(spec.get("shape", "meg"))
    hold = ring_r(spec) + pad_r(spec) + 1.5       # material under every foot
    if spec.get("deck") == "relief":
        # the pedestal has to carry the mound's run and still show a rim
        hold += RELIEF_D + RELIEF_RIM
    if need is not None:
        hold = need
        k = need / r_poly
    else:
        k = max(lean_r(spec) / r_hull, hold / r_poly, (T.HUB_R + 1.0) / r_poly)
    return affinity.scale(poly, k, k, origin=(0, 0))


def gauge_etch(spec):
    """The drawn size cut into the plate between the two rows, so the
    part says what each column is without a legend. The glyph builder is
    the dice cage's -- it already handles the counter in a 0 and
    normalizes to cap height, and there is no reason for a second one.

    Sizes read 1.0 and 2.0 rather than 1 and 2, because a ladder that
    goes 1, 1.1 ... 1.9, 2 reads as two different kinds of number. The
    unit is etched once, past the last column, rather than on every
    label."""
    from shapely import affinity
    import gen_dice_cage as D
    n = len(GAUGE_D)
    x0 = -GAUGE_PITCH * (n - 1) / 2.0
    y = GAUGE_ROW / 2.0
    out = []
    labels = [(f"{d:.1f}", x0 + GAUGE_PITCH * k, y)
              for k, d in enumerate(GAUGE_D)]
    # the unit reads once, tucked into the empty band below the sizes.
    # Past the last column it sat on the 5 x 5 patch, and giving it its
    # own strip of plate wasted more material than the patch uses.
    unit = ("mm", x0 + 2.0, -GAUGE_ROW / 2.0)
    for text, x, ly in labels + [unit]:
        g = D._raw_glyph(text)
        if g is None:
            continue
        g = affinity.scale(g, GAUGE_TEXT, GAUGE_TEXT, origin=(0, 0))
        g = affinity.translate(g, x, ly)
        z = deck_z(spec)
        geoms = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
        for q in geoms:
            e = trimesh.creation.extrude_polygon(q, GAUGE_ETCH + 1.0)
            e.apply_translation([0.0, 0.0, z - GAUGE_ETCH])
            out.append(e)
    return out


def probe_plan(spec):
    n = len(PROBE_D)
    half = PROBE_PITCH * (n - 1) / 2.0 + 5.0
    return Polygon([(-half, -PROBE_W / 2), (half, -PROBE_W / 2),
                    (half, PROBE_W / 2), (-half, PROBE_W / 2)]
                   ).buffer(2.0, quad_segs=12).buffer(-2.0, quad_segs=12)


def probe_etch(spec):
    """Every other size, under its bore. All fourteen would not fit."""
    from shapely import affinity
    import gen_dice_cage as D
    out = []
    for (x, _), d in zip(spikes(spec), PROBE_D):
        if round(d * 100) % 10:
            continue
        g = D._raw_glyph(f"{d:.1f}")
        if g is None:
            continue
        g = affinity.translate(affinity.scale(g, 3.4, 3.4, origin=(0, 0)),
                               x, -4.0)
        for q in (list(g.geoms) if g.geom_type == "MultiPolygon" else [g]):
            e = trimesh.creation.extrude_polygon(q, GAUGE_ETCH + 1.0)
            e.apply_translation([0.0, 0.0, FIELD_T - GAUGE_ETCH])
            out.append(e)
    return out


def field_grade_holes(spec):
    """A graded field keeps ALL its holes.

    The sizes were etched beside one hole a ring, which cost five bores
    and -- worse -- distorted a neighbor in the print. The geometry said
    0.81 mm of clearance and that was measured correctly; it simply is
    not enough, because an etched pocket that close leaves a web the
    printer cannot hold. Read in the hand: "the font labelling is mostly
    responsible for distorting one of the holes."

    The terraces already say which ring is which, so the numbers do not
    need to sit in the rings at all. They go in the middle, where the
    field has nothing, and the coupon gets back to being the field.
    """
    return [tuple(v) for v in np.array(field_holes(spec))], {}


def grade_legend():
    """What the center says: the innermost size, and the step out.

    Two short lines rather than five, because five will not fit in the
    clear disc and the terraces make the order plain. A ladder with an
    uneven step says its ends instead.
    """
    lo = FIELD_GRADE[0]
    steps = {round(b - a, 3) for a, b in zip(FIELD_GRADE, FIELD_GRADE[1:])}
    if len(steps) == 1:
        return [f"{lo:.2f}", f"+{steps.pop():.2f}".replace("0.", ".")]
    return [f"{lo:.2f}", f"{FIELD_GRADE[-1]:.2f}"]


def field_grade_etch(spec):
    """The legend, cut into the clear middle of the field."""
    from shapely import affinity
    import gen_dice_cage as D
    out, lines = [], grade_legend()
    pitch = GRADE_ETCH_SCALE + 1.0
    for i, txt in enumerate(lines):
        g = D._raw_glyph(txt)
        if g is None:
            continue
        g = affinity.scale(g, GRADE_ETCH_SCALE, GRADE_ETCH_SCALE,
                           origin=(0, 0)).buffer(GRADE_ETCH_BOLD,
                                                 join_style=2)
        lo_x, lo_y, hi_x, hi_y = g.bounds
        y = (len(lines) - 1) / 2.0 * pitch - i * pitch
        g = affinity.translate(g, -(lo_x + hi_x) / 2.0,
                               y - (lo_y + hi_y) / 2.0)
        for q in (list(g.geoms) if g.geom_type == "MultiPolygon" else [g]):
            e = trimesh.creation.extrude_polygon(q, GAUGE_ETCH + 1.0)
            e.apply_translation([0.0, 0.0, FIELD_T - GAUGE_ETCH])
            out.append(e)
    return out


def field_grade_terrace(spec, b):
    """How far this ring's terrace is sunk below the deck's top face."""
    return GRADE_TERRACE if b % 2 else 0.0


def field_grade_zones(spec):
    """The sunk terraces, as cutters. Alternate rings only, so the eye
    can tell one ring of bores from the next without a line drawn
    between them -- which will not fit."""
    edges = [0.0] + list(GRADE_BAND_EDGES) + [FIELD_R + 1.0]
    out = []
    for b in range(len(FIELD_GRADE)):
        d = field_grade_terrace(spec, b)
        if d <= 0.0:
            continue
        ring = (Point(0.0, 0.0).buffer(edges[b + 1], resolution=96)
                .difference(Point(0.0, 0.0).buffer(edges[b], resolution=96)))
        e = trimesh.creation.extrude_polygon(ring, d + 1.0)
        e.apply_translation([0.0, 0.0, FIELD_T - d])
        out.append(e)
    return out


def bore_depth(spec, b):
    """How deep this ring's bores go. The same on every terrace, which
    is the point: the step is cosmetic and the depth is the variable."""
    sunk = field_grade_terrace(spec, b)
    return (FIELD_T - sunk) - (1.0 - sunk)


def field_grade_zones(spec):
    """The sunk terraces, as cutters. Alternate rings only."""
    edges = [0.0] + list(GRADE_BAND_EDGES) + [FIELD_R + 1.0]
    out = []
    for b in range(len(FIELD_GRADE)):
        d = field_grade_terrace(spec, b)
        if d <= 0.0:
            continue
        ring = (Point(0.0, 0.0).buffer(edges[b + 1], resolution=96)
                .difference(Point(0.0, 0.0).buffer(edges[b], resolution=96)))
        e = trimesh.creation.extrude_polygon(ring, d + 1.0)
        e.apply_translation([0.0, 0.0, FIELD_T - d])
        out.append(e)
    return out


def field_grade_etch(spec):
    """Each ring's drawn size, cut where that ring's spare hole was."""
    from shapely import affinity
    import gen_dice_cage as D
    _, label = field_grade_holes(spec)
    out = []
    for b, (x, y) in label.items():
        g = D._raw_glyph(f"{FIELD_GRADE[b]:.2f}")
        if g is None:
            continue
        g = affinity.scale(g, GRADE_ETCH_SCALE, GRADE_ETCH_SCALE,
                           origin=(0, 0)).buffer(GRADE_ETCH_BOLD,
                                                 join_style=2)
        lo_x, lo_y, hi_x, hi_y = g.bounds
        g = affinity.translate(g, x - (lo_x + hi_x) / 2.0,
                               y - (lo_y + hi_y) / 2.0)
        sunk = field_grade_terrace(spec, b)
        for q in (list(g.geoms) if g.geom_type == "MultiPolygon" else [g]):
            e = trimesh.creation.extrude_polygon(q, GAUGE_ETCH + 1.0)
            e.apply_translation([0.0, 0.0, FIELD_T - sunk - GAUGE_ETCH])
            out.append(e)
    return out


def gauge_ruler(spec):
    """Tick marks every RULE_PITCH along the lower edge, longer every
    10 mm, zeroed on the plate's left edge.

    Each tick starts AT the edge and grows inward. Held to a straight
    baseline instead, they floated a millimeter or two off a slanted
    edge by a different amount at each end, and read as a row of dashes
    rather than a scale.
    """
    from shapely.geometry import LineString
    plan = gauge_plan(spec)
    x0 = plan.bounds[0] + 0.5
    span = plan.bounds[2] - x0 - 1.0
    out = []
    for k in range(int(span / RULE_PITCH) + 1):
        mm = k * RULE_PITCH
        x = x0 + mm
        h = RULE_LEN[2] if mm % 10 == 0 else RULE_LEN[0]
        cut = plan.intersection(LineString([(x, plan.bounds[1] - 5),
                                            (x, plan.bounds[3] + 5)]))
        if cut.is_empty:
            continue
        y_edge = cut.bounds[1]
        tick = Polygon([(x - RULE_W / 2, y_edge - 0.6),
                        (x + RULE_W / 2, y_edge - 0.6),
                        (x + RULE_W / 2, y_edge + h),
                        (x - RULE_W / 2, y_edge + h)])
        e = trimesh.creation.extrude_polygon(tick, GAUGE_ETCH + 1.0)
        e.apply_translation([0.0, 0.0, deck_z(spec) - GAUGE_ETCH])
        out.append(e)
    return out


def gauge_plan(spec):
    """A wedge: narrow at the small bore, wide at the large one, so the
    part says which end is which before any dimple does. A square pad on
    the wide end carries the 5 x 5 patch."""
    n = len(GAUGE_D)
    half = GAUGE_PITCH * (n - 1) / 2.0 + 7.0
    w0, w1 = GAUGE_ROW + 5.0, GAUGE_ROW + 8.0
    bar = Polygon([(-half, -w0), (half, -w1), (half, w1), (-half, w0)])
    return bar.buffer(2.0, quad_segs=12).buffer(-2.0, quad_segs=12)


def deck_z(spec):
    """The plane the cones stand on: the deck, or the top of the relief
    where there is one."""
    if spec.get("gauge"):
        return FIELD_T          # the flat row is the rod field's own plate
    return BASE_T + (RELIEF_H if spec.get("deck") == "relief" else 0.0)


def relief_plan(spec):
    """The raised tooth's FOOT on a relief base. Bigger than the spikes
    need by the relief's own height, because the mound rounds over on
    the way up and the flat it leaves on top is what the spikes stand
    on."""
    return tooth_plan(spec, ring_r(spec) + pad_r(spec) + 1.5 + RELIEF_D)


def relief_mound(spec, steps=16):
    """The tooth standing off the pedestal, blended at both ends.

    A single extrusion of the outline gives a vertical wall, and with
    the pedestal's own edge below it the part reads as two stacked
    steps -- which is exactly what it looked like. This walks the
    outline inward along a smoothstep, so the mound leaves the pedestal
    tangentially, rises RELIEF_H over a run of RELIEF_D, and arrives
    flat on top, where the spikes stand. A quarter circle was the first
    try and it is wrong at one end: it meets the top vertically, which
    left a shoulder a millimeter below the flat.

        u = inset / RELIEF_D        z = RELIEF_H (3u^2 - 2u^3)

    Every terrace steps INWARD going up, so there is no overhang in it,
    and the steps near both ends are thinner than a layer, which is
    where a staircase stops reading as one.
    """
    foot = relief_plan(spec).buffer(ROUND, quad_segs=12).buffer(
        -ROUND, quad_segs=12)
    out = []
    for i in range(steps):
        u = (i + 1) / steps
        z = RELIEF_H * (3 * u * u - 2 * u ** 3)
        p = foot.buffer(-RELIEF_D * u, quad_segs=16)
        if p.is_empty or p.area < 1.0:
            break
        if p.geom_type == "MultiPolygon":
            p = max(p.geoms, key=lambda q: q.area)
        out.append(trimesh.creation.extrude_polygon(p, BASE_T + z))
    return out


def deck_r(spec):
    """The deck's corner radius. Whichever is larger: what the ring and
    its pads need, the jig's own hub, or what keeps a tooth at the top of
    the band from leaning off the edge."""
    if spec.get("field"):
        return FIELD_R
    h = spec["teeth"][1] * 0.44
    lean = np.tan(np.radians(LEAN_TARGET)) * (contact_z(spec) + h)
    # the deck is an octagon, so its worst direction is across a flat,
    # not out to a corner: the corner radius has to be bigger by
    # 1/cos(22.5) for the target to hold whichever way the tooth leans.
    # This stand has no good direction and no bad one, which the tailed
    # stands cannot say -- the fixed L leans 18.3 degrees over its tail
    # and 9.5 across its arms
    lean /= np.cos(np.pi / DECK_SIDES)
    return round(float(max(ring_r(spec) + pad_r(spec), T.HUB_R, lean)), 2)


def base_plan(spec):
    """The deck, with the jig's Ø20 hub inside it. One polygon, extruded
    once: separate solids meeting in one plane export non-manifold."""
    if spec.get("probe"):
        return probe_plan(spec)
    if spec.get("gauge"):
        return gauge_plan(spec)
    if spec.get("deck") in ("tooth", "relief"):
        plan = tooth_plan(spec)
        hub = Point(0.0, 0.0).buffer(T.HUB_R, quad_segs=64)
        # union the hub only if the outline does not already hold it:
        # a circle lying a hair inside the outline unions to a tangency
        # the triangulator turns into inverted slivers on the top face
        if not plan.contains(hub):
            plan = unary_union([plan, hub])
        plan = plan.buffer(ROUND, quad_segs=12).buffer(-ROUND, quad_segs=12)
        return plan.simplify(0.01).buffer(0)
    R = deck_r(spec)
    th = np.radians(PHASE + 360.0 / DECK_SIDES * np.arange(DECK_SIDES))
    deck = Polygon([(R * np.cos(t), R * np.sin(t)) for t in th])
    plan = unary_union([deck, Point(0.0, 0.0).buffer(T.HUB_R, quad_segs=64)])
    return plan.buffer(ROUND, quad_segs=12).buffer(-ROUND, quad_segs=12)


def field_holes(spec=None):
    """Every hole in the field: each ring's eight, and each fill quad's
    four. Mirror-symmetric about both axes by construction, which is
    what makes a rectangle out of any hole and its three mirrors."""
    out = []
    for R, a in FIELD_RINGS:
        for t in (a, 90 - a, 90 + a, 180 - a, 180 + a, 270 - a, 270 + a,
                  360 - a):
            out.append((round(R * np.cos(np.radians(t)), 3),
                        round(R * np.sin(np.radians(t)), 3)))
    for x, y in FIELD_FILLS:
        for sx in (1.0, -1.0):
            for sy in (1.0, -1.0):
                out.append((round(sx * x, 3), round(sy * y, 3)))
    return sorted(set(out))


def field_rects(spec=None):
    """The rectangles the field offers: cross by fore, widest first."""
    S = {(round(x, 2), round(y, 2)) for x, y in field_holes()}
    out = {(round(2 * x, 1), round(2 * y, 1)) for x, y in S
           if x > 0 and y > 0
           and all((sx * x, sy * y) in S for sx in (1, -1) for sy in (1, -1))}
    return sorted(out, reverse=True)


def field_rings(spec=None):
    """The circles it offers, and the two gap widths round each."""
    out = []
    for R, a in FIELD_RINGS:
        g = sorted([2 * R * np.sin(np.radians(a)),
                    2 * R * np.sin(np.radians(45 - a))])
        out.append(dict(d=round(2 * R, 1),
                        gaps=[round(float(v - ROD_D), 2) for v in g]))
    return sorted(out, key=lambda r: r["d"])


def field_spacing(spec=None):
    p = np.array(field_holes())
    d = np.hypot(*(p[:, None, :] - p[None, :, :]).T)
    np.fill_diagonal(d, 9e9)
    return round(float(d.min()), 2)


BOSS_AIR = 0.8              # clear air between two towers at their tops:
                            # two extrusions, so the slicer draws two walls
                            # and not one merged blob
BOSS_WALL = 0.9             # the least plastic around the bore. The gauge
                            # read the same bore up a slim boss as straight
                            # into a plate, so thinning the tower does not
                            # move the fit -- it only has to hold together


def rod_boss_r(spec):
    """How fat a socket tower can be on THIS ring.

    Ø6.4 at the foot is fine on the L, where the posts stand 8.4 mm
    apart, and it is nonsense on the S, where they stand 4.6 apart: six
    towers that size fuse into a solid wall with six holes in it, which
    is not a forest and cannot be gauged. The tower is only there to
    give the rod 13 mm of hole to stand in, so its width is free --
    narrow it until the tops clear each other, and stop at the wall.
    """
    rf, rt, h = ROD_BOSS
    P = np.array(spikes(spec))
    d = np.hypot(*(P[:, None, :] - P[None, :, :]).T).T
    np.fill_diagonal(d, np.inf)
    room = (float(d.min()) - BOSS_AIR) / 2.0
    top = min(rt, room)
    if top < spec["rods"] / 2.0 + BOSS_WALL:
        raise SystemExit(json.dumps(dict(
            ok=False, error=f"{spec['id']}: the posts stand "
                            f"{float(d.min()):.2f} mm apart, which leaves "
                            f"no room for a socket tower with "
                            f"{BOSS_WALL} mm of wall round a "
                            f"\u00d8{spec['rods']} bore")))
    return top + (rf - rt), top, h


def rod_boss(spec, x, y):
    """One socket tower: a stubby taper off the deck with the rod's hole
    down its axis. The tower is there for depth -- a 1 mm rod standing in
    5 mm of deck would lean by whatever the hole's clearance allows, and
    13 mm of hole cuts that lean by two thirds."""
    rf, rt, h = rod_boss_r(spec)
    d = deck_z(spec)              # the mound's top, where there is one
    c = T.rev([(0.0, d - 0.5), (rf, d - 0.5), (rt, d + h),
               (0.0, d + h)], sections=48)
    c.apply_translation([x, y, 0.0])
    return c


ROD_CHAMFER = 0.8             # the lead-in at a rod socket's mouth
# The field cannot have that much. Its bores sit FIELD_MIN_SP apart, and
# a mouth is bore + 2 x chamfer wide: at 0.8 the mouths would leave half
# a millimeter of top face between them. 0.4 leaves 1.3 mm.
FIELD_WALL = 1.2              # top face left between two mouths


def _field_spacing(_c={}):
    """The closest two holes in the field actually come, in mm."""
    if "v" not in _c:
        P = np.array(field_holes(BY_ID["gz_rf"]))
        d = np.hypot(*(P[:, None, :] - P[None, :, :]).T).T
        np.fill_diagonal(d, np.inf)
        _c["v"] = float(d.min())
    return _c["v"]


# The field's lead-in, as (depth, radial width) instead of a 45 degree
# chamfer. The probe's bores get 0.8 mm of 45 degree cone -- four layers,
# opening the mouth to Ø3.05 -- and they take a rod. The field could
# only afford 0.4 of the same cone, two layers, because a wide mouth eats
# the wall between holes 3.58 mm apart; and 0.3 was already known to
# print as nothing at all. Depth is free and width is what is scarce, so
# this funnel is six layers tall and NARROWER at the mouth than the cone
# it replaces: more wall left, and three times the guide.
FIELD_LEAD = (1.2, 0.35)




def field_bands(spec):
    """Each hole's ring, grouped so the rings are far enough apart to
    tell by eye. Nine distinct radii collapse to five: 11.0 and 12.2 are
    one ring in the hand, and so are 16.0/16.6, 19.8/20.5, 23.3/23.5."""
    P = np.array(field_holes(spec))
    r = np.hypot(*P.T)
    return np.searchsorted(GRADE_BAND_EDGES, r)


def field_grade_d(spec, i):
    """The drawn bore for hole i of a graded field."""
    return FIELD_GRADE[int(field_bands(spec)[i])]


def field_grade_d_at(spec, x, y):
    """The drawn bore for the hole at this point, by which ring it is on."""
    r = float(np.hypot(x, y))
    return FIELD_GRADE[int(np.searchsorted(GRADE_BAND_EDGES, r))]


def field_lead(bore=None):
    """The funnel, narrowed if this filament's bore leaves less room.

    Silk wants Ø1.75 where PETG wants Ø1.475, and the wall between
    two mouths is what pays for it. Depth never changes: it costs
    nothing but layers, and it is the half that makes the funnel print.
    """
    dep, wid = FIELD_LEAD
    b = ROD_FIELD if bore is None else bore
    room = (_field_spacing() - b - FIELD_WALL) / 2.0
    # floored, not rounded: rounding the width UP spends a wall that is
    # not there, and the gate then reads 1.196 against a 1.2 floor
    return dep, np.floor(min(wid, room) * 1000.0) / 1000.0


def rod_hole_at(r, z0, top, x, y, chamfer=None, lead=None):
    """A blind bore with a cone at its mouth, as ONE revolved cutter.

    The lead-in was 0.3 mm, borrowed from the tooth stand's Ø3 holes,
    and at a Ø1.5 bore that is one extrusion width and a layer and a
    half. It measured as a chamfer and printed as nothing: the first
    layer of the bore is already full width, so a rod tip has no cone to
    find and the mouth just reads as mess. 0.8 leaves something the rod
    can follow, and something still visibly open if the bore itself
    closes a little.
    """
    if lead is not None:
        dep, wid = lead
        prof = [(0.0, z0), (r, z0), (r, top - dep), (r + wid, top),
                (r + wid + 1.0, top + 1.0), (0.0, top + 1.0)]
        b = T.rev(prof, sections=64)
        b.apply_translation([x, y, 0.0])
        return b
    c = ROD_CHAMFER if chamfer is None else chamfer
    prof = [(0.0, z0), (r, z0), (r, top - c), (r + c, top),
            (r + c + 1.0, top + 1.0), (0.0, top + 1.0)]
    b = T.rev(prof, sections=64)
    b.apply_translation([x, y, 0.0])
    return b


def field_bore(d, x, y, top=None, z0=1.0):
    """ONE definition of "a hole in the rod field", at any diameter.

    The probe exists to tell the field what size to draw, and it was
    built with its own call to rod_hole_at: the same bore, the same
    depth, and a 0.8 mm 45 degree chamfer where the field had 0.4. So
    the coupon was not measuring the field's hole, it was measuring a
    different hole that happened to share a diameter -- and it reported
    \u00d81.45 as a perfect fit for a part where \u00d81.45 took no rod at
    all. Matching thickness and depth by hand is what made that feel
    careful; the chamfer was simply never on the list.

    A coupon has to instantiate the SAME FEATURE as the part, not a
    checklist of the dimensions somebody thought mattered. So there is
    one function, and the only thing a coupon varies is the diameter.
    """
    return rod_hole_at(d / 2.0, z0, FIELD_T if top is None else top,
                       x, y, lead=field_lead(d))


def rod_hole(spec, x, y):
    d = deck_z(spec)
    return rod_hole_at(spec["rods"] / 2.0, d - ROD_SEAT,
                       d + ROD_BOSS[2], x, y)


def mark_spot(spec):
    """Somewhere flat on the pedestal for the dimples: out along the
    root, past the mound's foot but inside the deck. On a relief base
    the rim is only RELIEF_RIM wide, which is not room for a Ø2.5 dot,
    but the tooth's lobes are wide and the mound is not."""
    deck = base_plan(spec)
    mound = (relief_plan(spec) if spec.get("deck") == "relief"
             else deck.buffer(-1e6))
    from shapely.geometry import Point
    for r in np.arange(4.0, 60.0, 0.5):
        p = Point(0.0, r)
        if deck.contains(p.buffer(2.6)) and not mound.intersects(p.buffer(2.2)):
            return float(r)
    return float(min(deck_r(spec), support_edge(spec)) - 3.5)


def marks(spec):
    """Dimples on the pedestal: one dot for the tighter hole, two for
    the looser. Two bases the same size with a fifth of a millimeter
    between their holes are otherwise impossible to tell apart."""
    n = spec.get("mark", 0)
    r = mark_spot(spec)
    return [T.cyl(1.25, BASE_T - 0.6, BASE_T + 1.0,
                  x=-3.0 + 3.0 * k, y=r, sections=24) for k in range(n)]


def plugged_cone(spec, x, y, deck):
    """A cone, plus a short plug reaching BELOW the deck it stands on.

    The cone's own base lands exactly on the deck's top face, and two
    solids meeting in one plane leave zero-length edges and inverted
    slivers. The plug makes them overlap instead of touch. It is buried
    and changes nothing about the printed part."""
    foot = T.cone_foot_r(spec["cone"], spec) + 0.4   # never the same radius
    return union([T.a_cone(spec["cone"], x, y, deck, spec),
                  T.cyl(foot, deck - 0.6, deck + 0.05, x=x, y=y, sections=96)])


def stand(spec):
    """One gazebo: the deck, the relief if it wears one, and then either
    a cone on each ring position or a socket tower for a rod. Flat
    underside, nothing facing down, so it prints as it is used.

    The relief used to be checked first and returned, which quietly gave
    the rod bases cones instead of sockets the moment they were asked to
    wear one. The two choices are independent and are treated that way.
    """
    if spec.get("field"):
        slab = trimesh.creation.extrude_polygon(base_plan(spec), FIELD_T)
        if spec.get("grade"):
            pts, _ = field_grade_holes(spec)
            holes = []
            for x, y in pts:
                b = int(np.searchsorted(GRADE_BAND_EDGES, np.hypot(x, y)))
                sunk = field_grade_terrace(spec, b)
                # same 7 mm of hole on a terrace as off one: the mouth
                # drops with the surface and the floor underneath pays
                holes.append(field_bore(FIELD_GRADE[b], x, y,
                                        top=FIELD_T - sunk,
                                        z0=1.0 - sunk))
            return cut(slab, holes + field_grade_zones(spec)
                       + field_grade_etch(spec))
        return cut(slab, [field_bore(spec["rods"], x, y)
                          for x, y in field_holes(spec)])
    if spec.get("probe"):
        slab = trimesh.creation.extrude_polygon(probe_plan(spec), FIELD_T)
        # the probe IS the field, at fourteen diameters
        holes = [field_bore(PROBE_D[k], x, y)
                 for k, (x, y) in enumerate(spikes(spec))]
        return cut(slab, holes + probe_etch(spec))
    if spec.get("gauge"):
        d = deck_z(spec)
        pts = spikes(spec)
        n = len(GAUGE_D)
        boss, flat, crowd = pts[:n], pts[n:2 * n], pts[2 * n:]
        body = [trimesh.creation.extrude_polygon(base_plan(spec), d)]
        body += [rod_boss(spec, x, y) for x, y in boss]
        holes = [rod_hole_at(GAUGE_D[k] / 2.0, d - ROD_SEAT,
                             d + ROD_BOSS[2], x, y)
                 for k, (x, y) in enumerate(boss)]
        # the flat row is the field's hole on its own; the crowded row is
        # the same hole with two neighbors at the field's own spacing
        for k, (x, y) in enumerate(flat):
            holes.append(field_bore(GAUGE_D[k], x, y, top=d))
        for k, (x, y) in enumerate(crowd):
            for j, dx in enumerate((-GAUGE_CROWD, 0.0, GAUGE_CROWD)):
                fine = GAUGE_D[k] + (j - 1) * GAUGE_FINE
                holes.append(field_bore(fine, x + dx, y, top=d))
        return cut(union(body), holes + gauge_etch(spec)
                   + gauge_ruler(spec))
    body = [trimesh.creation.extrude_polygon(base_plan(spec), BASE_T)]
    if spec.get("deck") == "relief":
        body += relief_mound(spec)
    if spec.get("rods"):
        body += [rod_boss(spec, x, y) for x, y in spikes(spec)]
        return cut(union(body),
                   [rod_hole(spec, x, y) for x, y in spikes(spec)]
                   + marks(spec))
    body += [plugged_cone(spec, x, y, deck_z(spec)) for x, y in spikes(spec)]
    return union(body)


# --- measurement -------------------------------------------------------
def tips_coplanar(spec, m):
    """Read all eight cup floors off the built mesh by raying down each
    spike's axis. Eight points on one plane is the whole claim: a root
    that lands on any three of them must find the rest at the same
    height."""
    pts = spikes(spec)
    origins = np.array([[x, y, 500.0] for x, y in pts])
    dirs = np.tile([0.0, 0.0, -1.0], (len(pts), 1))
    loc, idx_r, _ = m.ray.intersects_location(origins, dirs,
                                              multiple_hits=False)
    if len(loc) != len(pts):
        return None, None
    zs = np.zeros(len(pts))
    zs[idx_r] = loc[:, 2]
    return float(zs.max() - zs.min()), [round(float(z), 3) for z in zs]


def gaps(spec):
    """Clear air between neighboring cups, at the rim. A root lobe has
    to settle BETWEEN spikes rather than balance across them: the four
    cone stands were printed once with 2 mm here and there was no getting
    a tooth in."""
    pts = spikes(spec)
    r = T.tip_r(spec)
    out = []
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        out.append(round(float(np.hypot(x1 - x0, y1 - y0) - 2 * r), 2))
    return out


def widths(spec):
    """The distinct gaps this ring offers, widest first, measured as
    clear air between the cups. One number means an even ring."""
    seen = sorted({round(g, 1) for g in gaps(spec)}, reverse=True)
    return seen


def lobe_clear(spec):
    """Headroom under the ring. The root nests on the circle, so its
    lobes hang down OUTSIDE it and must not reach the deck. A root's
    cleft runs about 0.06 of the tooth's height (FossilRecord's median of
    801; p90 is 0.115), so this is the cone's height against the deepest
    lobe in the band, taken at p90."""
    drop = 0.115 * spec["teeth"][1]
    return dict(cone_mm=spec["cone"], lobe_drop_mm=round(drop, 1),
                margin_mm=round(spec["cone"] - drop, 1))


# The stands are printed in PLA, so PLA is what the spike is read in.
# Sizing them against PETG's modulus was a straight mistake: PLA is
# twice as stiff, so every spread reported was double the truth and the
# spikes came out rigid in the hand.
E_PETG, Y_PETG = 1700.0, 50.0       # MPa
E_PLA, Y_PLA = 3500.0, 85.0


def spike_flex(spec, side_N=0.25, probe_N=1.0, E=None, Y=None):
    """How far one spike's tip moves, and where it is worked hardest.

    Integrated along the spike's REAL profile -- fillet and all -- not
    along the pure cone it looks like from its constants. That
    distinction is the whole reason the first set snapped. Taking the
    flank alone, the worst section came out two thirds of the way UP a
    spike that is nearly parallel; on the real part the cove at the deck
    necks it from Ø5.1 to Ø2.4 in 1.4 mm and the worst section is just
    above the cove, 2 mm up. That is where they broke.

    `breaks_at_N` is the side load at the tip that takes the worst
    section to PETG's yield, near 50 MPa. It is a static number and says
    nothing about a layer that did not fuse.
    """
    h = spec["cone"]
    prof = np.array(T.cone_profile(h, 0.0, spec), dtype=float)[1:]
    z, r = prof[:, 1], prof[:, 0]
    top = h - T.dish_d(spec)
    ok = (z <= top + 1e-9) & (r > 0.05)
    z, r = z[ok], r[ok]
    o = np.argsort(z)
    # the flank is one long segment in the profile: sample it, or the
    # integral sees two points and the deflection comes out a tenth of
    # what it is
    zz = np.linspace(float(z[o].min()), top, 2000)
    rr = np.interp(zz, z[o], r[o])
    I = np.pi * rr ** 4 / 4.0
    sig = probe_N * (h - zz) * rr / I
    k = int(np.argmax(sig))
    E = E_PLA if E is None else E
    Y = Y_PLA if Y is None else Y
    spread = float(np.trapezoid((h - zz) ** 2 / (E * I), zz)) * side_N
    return dict(spread_mm=round(spread, 3),
                spread_at_N=side_N,
                material="PLA" if E == E_PLA else "PETG",
                max_MPa_at_1N=round(float(sig[k]), 1),
                worst_at_mm=round(float(zz[k]), 1),
                breaks_at_N=round(float(Y / sig[k]), 1),
                petg_spread_mm=round(spread * E / E_PETG, 3),
                root_d=round(float(rr.max()), 2) * 2)


def rods_in(spec):
    """The rods themselves, for measuring the assembly rather than the
    printed part: Ø1 from the seat up to the contact plane."""
    z0 = BASE_T - ROD_SEAT
    return [T.cyl(ROD_D / 2.0, z0, contact_z(spec), x=x, y=y, sections=24)
            for x, y in spikes(spec)]


def rod_flex(spec, side_N=0.25, probe_N=1.0):
    """The rod is a different instrument from the spike it replaces: a
    parallel Ø1 cantilever in carbon fiber, held in 13 mm of socket. It
    is some five times stiffer than the printed spike and half the
    diameter at the tip, so it points rather than gives."""
    free = contact_z(spec) - (BASE_T + ROD_BOSS[2])
    I = np.pi * (ROD_D / 2.0) ** 4 / 4.0
    return dict(free_mm=round(free, 1),
                spread_mm=round(side_N * free ** 3 / (3 * E_CF * I), 3),
                spread_at_N=side_N,
                max_MPa_at_1N=round(probe_N * free * (ROD_D / 2.0) / I, 0),
                rod_len_mm=round(contact_z(spec) - (BASE_T - ROD_SEAT), 1))


def socket_d(spec, m):
    """The socket bores, read off the built mesh at mid-depth -- the
    drawn size, which is not the printed size. This printer takes about
    0.15 mm off a \u00d83 hole, and about half a millimeter off one
    three extrusions wide, which is what the gauge was for.

    Read ring by ring rather than island by island. The first version
    looked for one closed island per socket and so could only see a
    forest that had already separated; on the S the six towers are still
    one shape at this height, and it reported two sockets out of six on a
    part that has six good ones.
    """
    return [round(v, 3) for v in
            _bores_at(spec, m, spikes(spec),
                      deck_z(spec) + ROD_BOSS[2] / 2.0)]


def _bores_at(spec, m, centers, z):
    """Bore diameters read at one height, by matching each hole's own
    interior ring to the center it belongs to."""
    from shapely import affinity
    from shapely.geometry import Polygon as _P
    sec = m.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    polys, to3 = sec.to_planar()
    out = []
    for x, y in centers:
        d = 0.0
        for q in polys.polygons_full:
            qq = affinity.translate(q, to3[0, 3], to3[1, 3])
            for ring in qq.interiors:
                c = np.array(_P(ring).centroid.coords)[0]
                if np.hypot(c[0] - x, c[1] - y) < 1.0:
                    d = 2 * float(np.sqrt(abs(_P(ring).area) / np.pi))
        out.append(d)
    return out


def gauge_bores(spec, m):
    """Both rows read off the built mesh, each at its own height: the
    boss row up the towers, the flat row inside the plate."""
    from shapely import affinity
    from shapely.geometry import Polygon as _P
    n = len(GAUGE_D)
    pts = spikes(spec)
    out = {}
    # two rows read at their own heights; the third, the close-spaced
    # one, is read hole by hole below because its sizes vary within it
    for lbl, sel, z in (("boss", pts[:n], deck_z(spec) + ROD_BOSS[2] / 2.0),
                        ("flat", pts[n:2 * n], deck_z(spec) / 2.0)):
        sec = m.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        polys, to3 = sec.to_planar()
        got = []
        for x, y in sel:
            d = None
            for q in polys.polygons_full:
                qq = affinity.translate(q, to3[0, 3], to3[1, 3])
                for ring in qq.interiors:
                    c = np.array(_P(ring).centroid.coords)[0]
                    if np.hypot(c[0] - x, c[1] - y) < 1.0:
                        d = round(2 * float(np.sqrt(abs(_P(ring).area) / np.pi)), 3)
            got.append(d)
        out[lbl] = got
    return out


def merge_z(spec, m):
    """Where the forest becomes a wall. Adjacent cones on a ring this
    tight run into each other near the deck; that is harmless -- a root
    sits on the cups, 16 to 20 mm above -- but it has to happen LOW, or
    the eight spikes stop being eight. Read off the built mesh: the
    lowest height at which the section is eight separate islands."""
    for z in np.arange(BASE_T + 0.5, BASE_T + spec["cone"], 0.25):
        sec = m.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        if sec is None:
            continue
        polys, _ = sec.to_planar()
        if len(polys.polygons_full) >= len(weights(spec)):
            return round(float(z - BASE_T), 2)
    return None


def support_edge(spec):
    """The smallest distance from the pivot to the support hull, over
    every direction. The plate is flat, so what holds it up is the hull
    of its outline -- a notch or a scallop is bridged and costs nothing,
    and a long thin lobe helps only in its own direction. This reads the
    built plan, so it is right for an octagon and for a tooth alike."""
    hull = base_plan(spec).convex_hull
    xy = np.array(hull.exterior.coords)
    th = np.radians(np.arange(0, 360, 1.0))
    u = np.c_[np.cos(th), np.sin(th)]
    return round(float((xy @ u.T).max(axis=0).min()), 2)


def tip_back(spec, tooth_mm=None):
    h = (spec["teeth"][1] if tooth_mm is None else tooth_mm) * 0.44
    return round(float(np.degrees(np.arctan2(support_edge(spec),
                                             contact_z(spec) + h))), 1)


def print_overhang(mesh):
    """Downward-facing area with AIR under it, in the print pose.

    Pointing down is not enough. Where two cones' fillets run into each
    other at the deck, and wherever a boolean leaves a face on an
    internal plane, the mesh carries downward faces that have solid
    immediately beneath them -- 1.7 mm2 of them on the M, which sent me
    hunting a geometry fault that was not there. So each candidate face
    is asked whether the point just below it is inside the solid, and
    only the ones over air are counted.
    """
    n = mesh.face_normals[:, 2]
    bad = n < -0.8
    if not bad.any():
        return dict(overhang_mm2=0.0, off_plate_mm2=0.0)
    c = mesh.triangles_center[bad]
    a = mesh.area_faces[bad]
    off = c[:, 2] > 1e-6
    if not off.any():
        return dict(overhang_mm2=round(float(a.sum()), 2), off_plate_mm2=0.0)
    probe = c[off] - [0.0, 0.0, 0.05]
    solid = mesh.contains(probe)
    return dict(overhang_mm2=round(float(a.sum()), 2),
                off_plate_mm2=round(float(a[off][~solid].sum()), 2))


def plate_contact(mesh):
    low = mesh.triangles_center[:, 2] < 1e-6
    down = mesh.face_normals[:, 2] < -0.5
    return round(float(mesh.area_faces[low & down].sum()), 1)


def measure(parts):
    rep = dict(bodies=len(parts),
               watertight={n: bool(m.is_watertight) for n, m in parts.items()},
               dims_mm={n: [round(float(v), 2) for v in m.extents]
                        for n, m in parts.items()},
               fits_plate={n: bool(T.fits_plate(m)) for n, m in parts.items()})
    flat, _ = layout(parts)
    lo = np.min([m.bounds[0] for m in flat.values()], axis=0)
    hi = np.max([m.bounds[1] for m in flat.values()], axis=0)
    # the packed plate, not just each body: the packer wraps rows at the
    # bed's width and never looked at how deep the rows had gone, so a
    # nine-body set packed straight off the back of the bed and the
    # slicer refused it
    rep["plate_mm"] = [round(float(hi[0] - lo[0]), 1),
                       round(float(hi[1] - lo[1]), 1)]
    for key in ("grade", "coplanar_mm", "tip_z", "gaps_mm", "min_gap_mm",
                "merge_z_mm", "lobe_clear", "ring_mm", "flex", "widths_mm",
                "socket", "gauge",
                "occlusion", "field",
                "above_contact_mm", "plate_mm2", "print", "tip_dia_mm"):
        rep[key] = {}
    for s in SIZES:
        n = f"gazebo_{s['id'][3:]}"
        if n not in parts:
            continue
        m = parts[n]
        if s.get("probe"):
            rep["gauge"][s["id"]] = dict(
                drawn=list(PROBE_D),
                measured=[round(v, 3) for v in
                          _bores_at(s, m, spikes(s), FIELD_T / 2.0)],
                rows={}, depth_mm=round(FIELD_T - 1.0, 1),
                flat_depth_mm=round(FIELD_T - 1.0, 1),
                pitch_mm=PROBE_PITCH, row_gap_mm=0.0)
            rep["plate_mm2"][n] = plate_contact(m)
            rep["print"][n] = print_overhang(m)
            continue
        if s.get("gauge"):
            # a gauge is not a stand: no ring, no cups, no lean. What it
            # has to be is ten sockets that are each the size they say
            rows = gauge_bores(s, m)
            rows["fine"] = [round(v, 3) for v in _bores_at(
                s, m, [(x + dx, y) for x, y in spikes(s)[2 * len(GAUGE_D):]
                       for dx in (-GAUGE_CROWD, 0.0, GAUGE_CROWD)],
                deck_z(s) / 2.0)]
            rep["gauge"][s["id"]] = dict(
                drawn=list(GAUGE_D), measured=rows["boss"], rows=rows,
                depth_mm=round(ROD_BOSS[2] + ROD_SEAT, 1),
                flat_depth_mm=round(deck_z(s) - 1.0, 1),
                pitch_mm=GAUGE_PITCH, row_gap_mm=GAUGE_ROW)
            rep["plate_mm2"][n] = plate_contact(m)
            rep["print"][n] = print_overhang(m)
            continue
        dz, zs = tips_coplanar(s, m)
        rep["coplanar_mm"][s["id"]] = dz
        rep["tip_z"][s["id"]] = zs
        if s.get("rods") and not s.get("field"):
            # what the ray finds on a rod base is the SEAT, not a cup
            rep["socket"][s["id"]] = dict(
                drawn_d=s["rods"], measured_d=socket_d(s, m),
                printed_d_expected=round(s["rods"] - ROD_LOSS, 2),
                clearance_expected=round(s["rods"] - ROD_LOSS - ROD_D, 2),
                seat_z=zs[0] if zs else None,
                depth_mm=round(ROD_BOSS[2] + ROD_SEAT, 1),
                **rod_flex(s))
        if s.get("field"):
            # a field has no ring to measure: what it has is what it
            # OFFERS -- the rectangles, the circles and the room between
            rep["field"][s["id"]] = dict(
                holes=len(spikes(s)), min_spacing=field_spacing(s),
                deck_d=round(2 * FIELD_R, 1), thickness=FIELD_T,
                depth_mm=round(FIELD_T - 1.0, 1),
                chamfer=field_lead(s["rods"])[1],
                lead_depth=FIELD_LEAD[0],
                drawn_d=s["rods"],
                fit=("snug, read on a graded field"
                     if FIELD_BORE[_MAT]["read"]
                     else "inferred from PETG's offset, not yet graded"),
                # a field loses MORE than the strip the loss came from,
                # so predicting its holes with the strip's number said
                # \u00d81.11 for a bore read in the hand as just right on a
                # \u00d81 rod. The field's own loss is what the graded
                # plate measured: drawn minus the rod it holds.
                bore_source=FIELD_BORE[_MAT]["note"],
                bore_measured=FIELD_BORE[_MAT]["read"],
                applies_to="this field only: 56 bores, 3.58 mm centers, "
                           "8 mm deck. Not transferable to another "
                           "spacing, thickness or outline.",
                loss_mm=round(FIELD_BORE[_MAT]["d"] - ROD_D, 2),
                strip_loss_mm=ROD_LOSS,
                printed_d_expected=round(
                    s["rods"] - (FIELD_BORE[_MAT]["d"] - ROD_D), 2),
                rects=[[float(a), float(b)] for a, b in field_rects(s)],
                rings=field_rings(s),
                rod_len_mm=round(contact_z(s) - 1.0, 1))
            if s.get("grade"):
                # an instrument, not a stand: the terraces are a layer
                # apart ON PURPOSE, so coplanarity is not a claim this
                # plate makes. What IS checked is that terracing never
                # touched the depth under test. It is still reported as
                # the field it is -- reporting it as something else left
                # the export with no field block and the archive
                # describing 51 spikes on a six-spike ring.
                rep["grade"][s["id"]] = dict(
                    sizes=list(FIELD_GRADE), terrace_mm=GRADE_TERRACE,
                    depths=sorted({round(bore_depth(s, b), 2)
                                   for b in range(len(FIELD_GRADE))}))
                # and it withdraws the coplanarity reading rather than
                # publishing one it does not mean: every other plate
                # here claims a tooth can rest on it, and this one
                # claims only to be read.
                rep["coplanar_mm"].pop(s["id"], None)
                rep["tip_z"].pop(s["id"], None)
            rep["plate_mm2"][n] = plate_contact(m)
            rep["print"][n] = print_overhang(m)
            continue
        rep["gaps_mm"][s["id"]] = gaps(s)
        rep["min_gap_mm"][s["id"]] = min(gaps(s))
        rep["merge_z_mm"][s["id"]] = merge_z(s, m)
        rep["lobe_clear"][s["id"]] = lobe_clear(s)
        if not s.get("rods"):
            rep["flex"][s["id"]] = spike_flex(s)
        rep["widths_mm"][s["id"]] = widths(s)
        rep["ring_mm"][s["id"]] = dict(ring_d=s["ring"], n=len(weights(s)),
                                       deck_d=round(2 * deck_r(s), 2))
        whole = union([m] + rods_in(s)) if s.get("rods") else m
        rep["occlusion"][s["id"]] = T.occlusion(whole, s)
        rep["above_contact_mm"][s["id"]] = round(
            float(whole.bounds[1][2]) - contact_z(s), 4)
        rep["plate_mm2"][n] = plate_contact(m)
        rep["print"][n] = print_overhang(m)
        rep["tip_dia_mm"][s["id"]] = 2 * T.tip_r(s)
    rep["tip_back_deg"] = {s["id"]: tip_back(s) for s in SIZES
                           if f"gazebo_{s['id'][3:]}" in parts
                           and not s.get("field")}
    rep["g_each"] = {n: round(float(m.volume) / 1000.0 * 1.27, 1)
                     for n, m in parts.items()}
    rep["volume_cm3"] = round(sum(m.volume for m in parts.values()) / 1000.0, 2)
    rep["est_g"] = round(rep["volume_cm3"] * 1.27, 1)
    if rep.get("field") and not FIELD_BORE[_MAT]["read"]:
        rep.setdefault("caveats", []).append(
            f"the field's bore for {MATERIALS[_MAT]['label']} is "
            f"inferred from PETG's offset, not read on a graded field. "
            f"Print the graded field on this spool before trusting it.")
    return rep


def gates(rep):
    out = [("watertight", all(rep["watertight"].values())),
           ("fits_plate", all(rep["fits_plate"].values())),
           ("plate_fits_the_bed", max(rep["plate_mm"]) <= 250.0)]
    for k, v in rep.get("grade", {}).items():
        out.append((f"terracing_left_the_depth_alone:{k}",
                    len(v["depths"]) == 1))
        out.append((f"grade_is_a_ladder:{k}",
                    v["sizes"] == sorted(v["sizes"])))
    for k, v in rep["coplanar_mm"].items():
        out.append((f"coplanar:{k}", v is not None and v < 0.05))
    for k, v in rep["above_contact_mm"].items():
        out.append((f"below_contact:{k}", v <= 1e-6))
    for k, v in rep["occlusion"].items():
        out.append((f"occludes_nothing:{k}", v["overall"] < 1.0))
    for k, v in rep["widths_mm"].items():
        want = 3 if BY_ID[k].get("gaps") else 1
        out.append((f"offers_{want}_widths:{k}", len(v) == want))
    for k, v in rep["min_gap_mm"].items():
        # NOT the four-cone stands' rule. There, the two cups on a lobe
        # have to take the root BETWEEN them, so 2 mm was hopeless. Here
        # the root comes down ON the ring and closer spikes are a finer
        # bed of nails, not a worse one. All this has to catch is cups
        # running into each other, which would make two spikes one.
        out.append((f"cups_are_separate:{k}", v >= 2.0))
    for k, v in rep["merge_z_mm"].items():
        # the cones run together near the deck; it must be near the deck
        spec = BY_ID[k]
        out.append((f"spikes_are_not_a_wall:{k}",
                    v is not None and v < 0.45 * spec["cone"]))
    for k, v in rep["lobe_clear"].items():
        # the lobes hang outside the ring; they must not reach the deck
        out.append((f"lobes_clear_the_deck:{k}", v["margin_mm"] > 2.0))
    for k, v in rep["gauge"].items():
        for lbl, got in v["rows"].items():
            if lbl == "fine":
                want = [d + (j - 1) * GAUGE_FINE
                        for d in v["drawn"] for j in range(3)]
            else:
                want = v["drawn"]
            out.append((f"gauge_{lbl}_bores_are_drawn_true:{k}",
                        len(got) == len(want)
                        and all(a is not None and abs(a - b) < 0.05
                                for a, b in zip(got, want))))
        # a boss socket is 12 deep, a plate one 7: each gauge is as deep
        # as the socket it stands in for
        out.append((f"gauge_is_as_deep_as_a_socket:{k}",
                    v["depth_mm"] >= (10.0 if v["rows"] else 6.0)))
    for k, v in rep["field"].items():
        # the field takes the FREE size, not the friction one. This gate
        # used to insist on the friction size and it was wrong: that is
        # what put Ø1.45 in a PETG field and made 56 bores that would
        # not take a rod.

        out.append((f"field_holes_clear_each_other:{k}",
                    v["min_spacing"] >= FIELD_MIN_SP - 1e-9))
        # the mouths, not just the bores: a lead-in widens the hole where
        # it meets the top face, and that is where they crowd
        # against the TRUE spacing, not the rounded one the report
        # prints: 3.585 rounds to 3.58, and gating on the rounded number
        # failed a wall that is actually there
        out.append((f"field_mouths_leave_a_wall:{k}",
                    _field_spacing()
                    - (v["drawn_d"] + 2 * field_lead(v["drawn_d"])[1])
                    >= FIELD_WALL - 1e-9))
        # the lead-in has to be tall enough to PRINT. 0.3 mm of it came
        # out as nothing; this one is six layers
        out.append((f"field_lead_in_is_printable:{k}",
                    v["lead_depth"] >= 1.0))
        # the field's bore is READ on a graded field, not derived from
        # the strip. The gate this replaces allowed at most a half step
        # over the strip reading, which is the rule that produced two
        # plates that took no rod at all: the real gap is 0.11.
        out.append((f"field_bore_is_the_read_one:{k}",
                    abs(v["drawn_d"] - ROD_FIELD) < 1e-9))
        out.append((f"field_bore_is_bigger_than_the_strip:{k}",
                    v["drawn_d"] > ROD_BORE))
        out.append((f"field_offers_rectangles:{k}", len(v["rects"]) >= 10))
        out.append((f"field_offers_rings:{k}", len(v["rings"]) >= 4))
        out.append((f"field_is_deep_enough:{k}", v["depth_mm"] >= 6.0))
    for k, v in rep["socket"].items():
        # drawn, not printed: the two bases are the experiment that finds
        # the printed one. Both must at least admit the rod after the
        # printer takes its cut
        # against the measured rule rather than a toolpath guess: the
        # bore prints ROD_LOSS under its drawn size, and the fit wanted
        # is friction -- the rod stays without glue and still goes in
        printed = v["drawn_d"] - ROD_LOSS
        out.append((f"socket_is_a_friction_fit:{k}",
                    -0.02 <= printed - ROD_D <= 0.1))
        out.append((f"socket_is_above_the_floor:{k}",
                    v["drawn_d"] >= MIN_BORE))
        out.append((f"socket_is_drawn_true:{k}",
                    all(abs(d - v["drawn_d"]) < 0.05 for d in v["measured_d"])
                    and len(v["measured_d"]) == len(BY_ID[k]["gaps"])))
        out.append((f"socket_is_deep_enough:{k}", v["depth_mm"] >= 10.0))
    for k, v in rep["flex"].items():
        # strength first, after a set printed at Ø1.6 on a 1.5 degree
        # flank snapped in the hand. A spike has to take a firm push at
        # the tip, and what flex is left is a bonus rather than the
        # point -- the thin springy job belongs to the carbon rods now.
        # in PLA, which is what these print in. The spikes that snapped
        # would take about 8 N in the same material, so 9 is the floor
        out.append((f"spike_takes_a_push:{k}", v["breaks_at_N"] >= 9.0))
        out.append((f"spike_has_give:{k}", v["spread_mm"] >= 0.04))
        out.append((f"spike_worst_section_is_low:{k}",
                    v["worst_at_mm"] <= 0.25 * BY_ID[k]["cone"]))
    for n, v in rep["print"].items():
        out.append((f"no_overhang:{n}", v["off_plate_mm2"] <= 1.0))
    for n, v in rep["plate_mm2"].items():
        out.append((f"stands_up:{n}", v > 100.0))
    return out


# --- plate and file ----------------------------------------------------
def parse_which(which):
    # `all` means everything settled: the drawn silhouettes are not, and
    # a draft that nobody asked for has no business on a plate
    if which in ("all", "", None):
        ids = [i for i in ALL_IDS if not BY_ID[i].get("draft")]
    else:
        ids = [w.strip() for w in which.split(",") if w.strip()]
    bad = [i for i in ids if i not in ALL_IDS]
    if bad:
        raise ValueError("no such size: " + ", ".join(bad))
    return [i for i in ALL_IDS if i in ids]


def build(which="all"):
    return {f"gazebo_{i[3:]}": stand(BY_ID[i]) for i in parse_which(which)}


def layout(parts, gap=6.0):
    """Flat on the plate, the way up they are used. Nothing is flipped:
    there is nothing on a gazebo that faces down."""
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


def meta(parts, poses, rep):
    return {
        "design": "gazebo",
        "shapes": sorted(SHAPES),
        "ring": dict(phase_deg=PHASE, deck_sides=DECK_SIDES,
                     lean_target_deg=LEAN_TARGET),
        "dock": dict(flat_bottom=True, plat_r=T.PLAT_R),
        "sizes": [dict(s, spikes=spikes(s), contact_z=contact_z(s),
                       dish_z=dish_z(s), tip_r=T.tip_r(s),
                       dish=round(T.dish_d(s), 3), base_t=BASE_T,
                       gaps=rep["gaps_mm"].get(s["id"]),
                       ring_d=s["ring"], n=len(weights(s)),
                       widths=rep["widths_mm"].get(s["id"]),
                       deck_d=round(2 * deck_r(s), 2),
                       flex=rep["flex"].get(s["id"]),
                       socket=rep["socket"].get(s["id"]),
                       field=rep["field"].get(s["id"]),
                       tip_back_deg=rep["tip_back_deg"].get(s["id"]))
                  for s in SIZES if f"gazebo_{s['id'][3:]}" in parts],
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
    embed(out, brim=False)          # hundreds of mm2 on the plate already
    with zipfile.ZipFile(out, "a", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Metadata/gazebo.json",
                   json.dumps(meta(parts, poses, rep), separators=(",", ":")))
    from meshcheck import export_defects
    return export_defects(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="all",
                    help="all, or a comma-separated set of "
                         + ", ".join(ALL_IDS))
    ap.add_argument("--grade", default="",
                    help="five bore sizes for the graded field, smallest "
                         "first, e.g. 1.53,1.56,1.59,1.62,1.65. The "
                         "coarse default brackets; a second pass narrows "
                         "inside whatever the first one bracketed.")
    ap.add_argument("--material", default="pla_basic",
                    help="the filament the rod sockets are drawn for: "
                         + ", ".join(sorted(MATERIALS))
                         + ". Anything else is refused rather than "
                           "guessed: print the gauge and add it.")
    ap.add_argument("--out")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    global ROD_BORE, ROD_FREE, ROD_FIELD, ROD_LOSS, _MAT
    if a.material not in MATERIALS:
        print(json.dumps({"ok": False, "error":
                          "no bore measured for " + a.material
                          + "; the gauge reads one. Known: "
                          + ", ".join(sorted(MATERIALS))}))
        return 1
    ROD_BORE = MATERIALS[a.material]["bore"]
    ROD_FREE = MATERIALS[a.material]["free"]
    ROD_FIELD = FIELD_BORE[a.material]["d"]
    _MAT = a.material
    if a.grade:
        vals = [float(v) for v in a.grade.split(",") if v.strip()]
        if len(vals) != len(FIELD_GRADE) or sorted(vals) != vals:
            print(json.dumps(dict(ok=False, error=(
                f"--grade wants {len(FIELD_GRADE)} sizes in increasing "
                f"order; got {vals}"))))
            return 1
        FIELD_GRADE[:] = vals
    ROD_LOSS = MATERIALS[a.material]["loss"]
    for _s in SIZES:
        if _s.get("rods") and not _s.get("gauge") and not _s.get("probe"):
            # the field is glued and gets the free size; a socket on a
            # tower holds its rod up while you place it, and keeps the
            # friction fit
            _s["rods"] = ROD_FIELD if _s.get("field") else ROD_BORE
    try:
        parts = build(a.size)
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    if a.quick:
        ok = all(m.is_watertight for m in parts.values())
        print(json.dumps({"ok": ok, "bodies": len(parts)}))
        return 0 if ok else 1
    rep = measure(parts)
    rep["material"] = a.material
    rep["rod_bore"] = ROD_BORE
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
