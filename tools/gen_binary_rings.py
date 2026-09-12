#!/usr/bin/env python3
"""Coded inserts for a toy that reads concentric rings as bits.

Reference: the playset is the Fisher-Price Little People Zoo Talkers Animal
Sounds Zoo, W1710, (c) 2011 Mattel. Its instruction sheet is at
https://service.mattel.com/instruction_sheets/W1710a-0920.pdf -- assembly
only, and worth knowing what it does NOT contain: no animal list, no codes,
nothing about the reader. All it says of the mechanism is "Fit an animal
figure onto the button on the base. Each animal makes different sounds!"
The code-to-animal mapping is published nowhere; it is being worked out here
one disk at a time.

The toy is rubber. Its coded end is a swept square wave: a lip at the
outside, shorter concentric bits inside it, and the floor between them. A
band standing at bit height is a 1; floor showing through is a 0.

The reader has five plungers, each at its own radius so that the code reads
at any rotation, and one of them sits on the axis. So the coding is five bit
positions: a disc at the centre and four rings around it. The lip outside
them and the land outside that are structure -- neither ever carries a bit:

    bit 1    0      -> 2.375     Oe4.75    a disc, not a ring
    bits 2-5 2.375  -> 12.44     Oe24.88   four rings, 10.065 between them
    rim seat 12.19  -> 13.94     Oe27.88   always floor, 1.75 wide
    lip      13.94  -> 16.65     Oe33.30   always solid, 2.71 wide
    land     16.65  -> 19.50     Oe39.00   always solid, 2.85 wide

THE RIM SEAT

The outermost band is not spare field and it is not clearance. The reader's
boss carries a raised rim about 1.5 mm wide around its edge, and that band
is the socket the rim drops into. It is a locating feature, and it has to
be empty on every code.

This is what silenced codes 16-31 in the field, and it took four wrong
theories to see. The rim does not collide with a raised bit 5 -- their
heights never clash, which is what made every collision story fall apart.
It simply has nowhere to go. Fill its seat and the disc cannot descend the
rim's depth; the lip then stops short of the two side switches, and those
switches gate the read. So nothing is decoded at all, for every code with
bit 5 standing, whatever its other bits do. That is why the failure was
sixteen silences rather than one silence and fifteen wrong animals -- the
shape of the symptom was the clue, and it pointed at a gate, not a misread.

The seat is drawn 1.75 wide against a rim measured at about 1.5, because
extra width costs only bit 5's margin (which has 1.3 mm to spare) while
too little costs the whole read.

Confirmed on the toy 2026-09-06, by a plate printed to bracket it. Two
discs carried code 16 with nothing else changed but the width of this seat:
at 1.25 the disc was silent, at 2.25 it spoke, and at the shipped 1.75 it
spoke. So the rim is between 1.25 and 1.75 wide, the seat is what gates the
read, and 1.75 clears it. Every other disc on that plate read correctly,
which also puts SLACK 0.30 and the midpoint grid out of doubt: five single
bits named five different animals, 24 said whale, 14 said koala.

Code 31 wants a firmer press than the rest. That is the sum of five plunger
springs rather than a bit standing short, and it is worth being clear about
the direction: a taller RELIEF would make 31 harder, not easier. Nothing to
adjust.

The bits are numbered from the middle out, the way the toys are talked
about: bit 1 is the centre disc and bit 5 the outermost ring. In the code
they are worth 1, 2, 4, 8 and 16, so an odd code is one with its centre
standing and an even one has a pocket there.

THE CENTRE IS A BIT

It was modelled as a permanent solid nub until the animals said otherwise.
The photographed ends in assets/zootalkers/ settle it both ways round: camel
and tiger stand a boss at the centre, polar bear, turtle, koala and ostrich
sink a pocket there. It varies, so it is code, and reading it as structure
cost the field a position it does not have.

THE LIP AND THE LAND

The lip is not only what seats the plug: it is what presses the switch that
starts a read. The toy works at any rotation, so the switch is the ring
itself and not anything at one angle -- the rectangular window moulded
beside it plays no part. Nothing is read until the lip presses.

The land is the flat around the lip, 2.85 wide, and the lip stands 1.38
proud of it. On a real accessory that flat is the body the coded disc is
set into; a disc printed on its own has to carry it, or there is nothing
for the toy's face to meet and nothing to stop the plug going in further
than the switch travels.

    lip stand   1.38   the lip's top above the land
    land        2.85   wide, radially, taking the disc to Oe39.00

Read again on the toy, the lip measures Oe28 inside, Oe33.25 outside and
2.8 across. The grid here is pinned at Oe27.88 / Oe33.30 / 2.71 by earlier
readings, and 0.12 is inside what calipers on rubber disagree by, so the
grid has not been moved -- the band widths hang off Oe27.88 and would all
have to move with it. --outer and --widths take the other reading.

The same measurement put the lip's top 11.75 above the bore floor, against
the 11.55 shipped here (the mean of 11.66 / 11.70 / 11.30). The land is
placed 1.38 down from the lip's own top rather than up from the floor, so
that disagreement moves the whole outer face together and never the step
the switch actually sees.

Five positions is 2^5 = 32 combinations, but the one with nothing standing
gives the reader no bit to find: the toy needs both side switches down AND
at least one bit up, so an empty disk is silent by its own rule. There is no
code 0 disk. The set is 1 to 31. A code reads outward from the middle:

    code 10 = bits 2 and 4 = space, ring, space, ring, space
    code 14 = bits 2, 3, 4 = space, then one plateau three rings wide

Read off the toys: tiger has its centre standing and seal has a pocket
there, so tiger is odd and seal is even. Koala carries everything but bits
1 and 5, which is code 14 -- and it looks like it, a wide plateau with a
pocket in the middle and floor showing outside it.

Counted off the reader (assets/zootalkers/reader-base.jpg) the plungers come
to five, at radii of roughly 0.7, 4.0, 6.3, 8.1 and 10.9 on a Oe28 bore.
Those radii are crude -- they are scaled off a photograph -- but the count
is not, and five positions with the centre among them give the 31 speaking
codes.

WHAT THE MEASUREMENTS PIN, AND WHAT THEY DO NOT

Pinned: the centre disc (Oe4.75), the field's outer edge (Oe27.88) and the
lip (Oe33.30) are direct readings. The span from the disc's outer edge to
the inner edge of an outer ring reads 8.44, which puts a ring boundary at
r 10.8125 and so splits the field into 8.4375 inside and 3.1275 outside.

Not pinned: how the 8.4375 divides among the three rings inside it. Three
unknowns against one equation, so the default below is a choice, not a
derivation -- it divides them equally. --widths takes any other split.

    default   2.8125   2.8125   2.8125   3.1275     sums to 11.565

Superseded: a pair of 1.8 readings that used to fix two of the widths. They
were fitted to a six-position grid -- a permanent nub and five rings -- which
the reader's five plungers rule out. They may still be a real width somewhere
on the part; they no longer place a boundary on their own.

The eleven photographed ends are the way to close this properly: pooled
across them, the up and down transitions should cluster on the real
boundaries.

HEIGHTS

Measured from the floor between the rings, which is the surface the toy was
measured from -- so these are what a depth gauge reads standing on it.

    rim    11.75   floor to the top of the lip        the largest reading
    stand   1.38   the lip's top above the land       and the switch's travel
    relief  3.97   floor to the top of a bit ring     rim - 7.78
    floor   2.00   solid backing below                ours
                   ------
    total  13.75

The rubber has no single depth, and calipers compress it, so every reading
is biased short and the largest of a set is usually truest. The mean was the
conservative choice while nothing had been printed. A printed disc changed
that: it plays, but only when pressed hard, which is what a raised feature
that is slightly too short feels like. So the rim is now the largest reading
-- 11.75, against 11.66 / 11.70 / 11.30 and a later "almost 12" -- rather
than their mean, and the relief follows it up through the same 7.78 drop.

That is the whole of the licence the measurements give, and it is worth
being exact about where it ends. The readings bracket the relief between
3.74 (the centre disc, read directly off the bore floor) and 4.32 (a bit
ring, read the same way and long set aside as an outlier); 3.97 sits inside
that bracket. 4.32 is where to go next if a press is still wanted, and it
needs the rim at "almost 12" to stay arithmetically honest.

The relief is still derived rather than read, but it no longer rests on one
number. Measured down from the rim, the nub and the bit rings top out
together at 7.78 -- they are the same height, whatever the eye says -- which
puts the relief at 11.55 - 7.78 = 3.77. Read the other way, from the bore
floor, the nub stands 3.74. The two disagree by 0.03, and they sum back to
11.52 against a rim of 11.55.

That supersedes an earlier rim-to-bit gap of 8.20 and the 3.35 it implied:
0.42 of ring height, which is a tenth of the ring. The 4.32 read directly
off a bit ring remains the outlier, and remains set aside.

The flange's top edge is slightly chamfered on the toy. That is deliberately
not modelled -- a printed edge picks up about that much rounding unasked.

PRINTING

Nothing overhangs. Every surface is a vertical extrusion off a flat base --
the land is a step down from the lip, not a brim over air -- so it prints
face-down on bare bed with no supports and no bridging except over the
index pockets.

CLEARANCE, AND WHICH SURFACE IT BELONGS ON

The disc is a cup and it goes over the reader: the reader's pad stands up
inside the lip, and the plungers meet the coded floor. So the surface that
has to clear is the INSIDE of the lip -- the cavity, drawn Oe27.88 -- and
not its outside, which touches nothing. Everything was drawn nominal at
first, on the argument that the toy is rubber and stretches. A printed disc
settled it: it seats, it reads, and it binds on the reader going on.

--slack therefore opens the cavity, and it is measured ACROSS the hole --
the way a caliper reads it, and the way the fault was reported. It defaults
to 0.10: Oe27.98 built where the part is drawn Oe27.88. The outside stays
Oe33.30 and the disc stays Oe39.00; the lip's wall gives up the 0.05 of
radius and comes out 2.66 rather than 2.71.

0.10 across is about the smallest step worth asking for. The motion system
resolves far finer, but a wall comes off this printer within about +/-0.05
of nominal, so anything under a tenth is inside the scatter from one print
to the next.

The way past guessing is one caliper reading: the reader's pad across its
outside. The cavity wants that plus a slip fit, and the drawn Oe27.88 came
off an animal's coded end rather than off the reader itself.

The underside carries the code as an Arabic numeral, 1 to 31, because
thirty-one of these are otherwise indistinguishable in a drawer. It is
engraved rather than raised: the underside is the bed face, and numerals
standing proud of it would be the only thing touching the plate, so the
first layer would be the digits and the part would rock on them.
--numerals emboss raises them anyway.

The numeral is mirrored in the model so that it reads the right way round
when the part is turned over and looked at.

--codes takes a set the way a print dialog takes page numbers: "7", or
"1-31", or "1,2,4,8,16". One code is one disk; several are laid out on one
bed in reading order and written as a single 3MF.

Usage: gen_binary_rings.py --codes 7 [--out FILE.3mf]
       gen_binary_rings.py --codes 1-31 --out SET.3mf
       gen_binary_rings.py --all --outdir DIR
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh

NOZZLE = 0.4
NUB_DIA = 4.75           # measured
OUTER_DIA = 33.30        # measured -- the flange, not a bit
INNER_DIA = 27.88        # measured -- where the coding stops
BANDS = 5                # bit positions: a centre disc and four rings
# The four rings, innermost out. Bit 0 is the disc inside them, whose radius
# is NUB_DIA/2. See the note above on what the measurements fix (the sum,
# and one boundary) and what is a choice (the split inside that boundary).
# Field-reported 2026-09-05: codes 16-31 -- every code with the outermost
# ring standing -- made no sound at all. Not a wrong animal, no sound. A
# band that simply is not read would give duplicates of 0-15, so silence
# means something mechanical stops the plug seating, and the toy needs both
# side switches fully depressed before it reads anything.
#
# So the outermost slice of the field is not a bit position. It is
# clearance for the raised rim around the reader's boss, and it has to be
# floor on every disc: with bit 5 low that groove clears the rim, and with
# bit 5 high the band fills, fouls the rim, and holds the lip off its
# switch. The width is Brett's, off the part in his hand -- a photograph
# of the reader measures the dead zone at nearer 4.3, and the standing
# rule on this project is that the photograph loses.
RIM_RELIEF = 1.00
LAST_BIT_IN = 1.50       # the outermost plunger, measured in from the field
                         # edge. Brett's, off the reader in his hand.


# WHICH ANIMAL EACH CODE SAYS
#
# Not published anywhere. The toy's animal roster is (Fisher-Price Little
# People Zoo Talkers, 2011): lion, polar bear, gorilla, tiger, white tiger,
# elephant, dolphin, whale, ostrich, penguin, alligator, rhinoceros, seal,
# bear, hippo, orangutan, flamingo, giraffe, lion cub, koala, camel, turtle.
# The mapping from code to animal is not in any of that -- it was worked out
# here, one disk at a time, by printing a code and listening.
#
# So this holds only what the toy has actually said, and stays empty for the
# rest. Filling it in with plausible guesses would make a card that lies
# confidently, which is worse than one that admits it does not know.
# TO FILL IN: print a disk, put it on the peg, write down what it says.
# Brett has the toy and is working through them. Add the line here and the
# card picks it up -- the code chip gets a dot and the name in its tooltip.
# Leave a code out rather than guess at it.
ANIMALS = {
    14: "koala",     # printed 2026-09-06, said koala
    24: "whale",     # printed 2026-09-06, said whale
}

PLUNGER_R = (0.55, 3.85, 6.25, 8.15, 10.90)
# Two photographs read months apart, averaged: reader-base.jpg gave 0.7 /
# 4.0 / 6.3 / 8.1 / 10.9 and IMG_3548 gave 0.36 / 3.68 / 6.23 / 8.25 / 10.56.
# They agree within 0.35 except on p5, and there the older reading wins on
# evidence that is not a photograph at all: under the old grid the bit 4
# band ran out to r 10.8125, so if p5 were at 10.56 then a bit-4 disc would
# have driven p4 and p5 together and said "whale". No disc ever said whale.
# So p5 is outside 10.8125, and 10.90 it is.
RIM_INNER = 12.19        # where the boss's raised rim begins. The band
                         # outside this is not clearance -- see RIM SEAT.


def midpoint_edges(plungers=PLUNGER_R, nub_dia=NUB_DIA, rim_inner=RIM_INNER):
    """Band boundaries halfway between neighbouring plungers.

    Each band then owns exactly one plunger and every plunger is as far
    from an edge as the spacing allows. That is the whole job, and the grid
    this replaces failed it: its bit 4 band ran r 8.00-10.8125 and so
    covered BOTH p4 (8.20) and p5 (10.60), while its bit 5 band covered no
    plunger whatsoever and hung its outer half over the rim. Raising bit 5
    therefore pressed nothing and fouled the rim, which is why codes 16-31
    were silent rather than wrong, and why 1-15 still gave fifteen
    different animals -- bit 4 was quietly driving two switches at once.

    The innermost boundary stays the measured Oe4.75 disc rather than the
    p1/p2 midpoint: it is a direct reading of the toy's own geometry and it
    still clears p2 by 1.3 mm.
    """
    mids = [(plungers[k] + plungers[k + 1]) / 2 for k in range(len(plungers) - 1)]
    return [nub_dia / 2] + mids[1:] + [rim_inner]


def measured_widths(rim_inner=RIM_INNER):
    e = midpoint_edges(rim_inner=rim_inner)
    return tuple(e[i + 1] - e[i] for i in range(len(e) - 1))


WIDTHS = measured_widths()
RIM = 11.75              # ring floor to top of lip -- the largest reading
LAND = 2.85              # flat land around the lip, radially -- measured
LIP_STAND = 1.38         # how far the lip stands above that land -- measured
RELIEF = 3.97            # ring floor to top of a bit ring: RIM - 7.78
# The cavity, ACROSS: Oe27.88 drawn, Oe28.18 built. Diametral, not radial --
# the number is what a caliper reads across the hole, because that is how
# every other number here was read and how the fault was reported.
# 0.10 -> 0.30 on 2026-09-05: at 0.10 the second print went on and worked
# but was reported still "a tiny bit tight". This is the third value the
# number has had and each move came from a part in a hand, which is the
# only instrument that has ever been right about this fit. Field-proven
# 2026-09-06 across ten discs in PLA: seats and reads, no bind.
SLACK = 0.30
FLOOR = 2.00             # solid backing below the ring floor -- ours to pick
NUM_SIZE, NUM_DEEP = 11.0, 0.6      # cap height and cut depth of the numeral
# 2 mm between parts, not 4: the land took the disc from Oe33.3 to Oe39 and
# thirty-two of those at a 4 mm gap no longer fit the bed. They are brimless
# and never touch, and the slicer is content at 2.
PLATE_GAP, PLATE_MARGIN = 2.0, 5.0
BED = (256.0, 256.0)     # Bambu P2S


def parse_codes(spec, limit=2 ** BANDS, include_zero=False):
    """A set of codes, written the way a print dialog takes page numbers.

        7               one
        1,2,4,8,16      a list
        1-31            a range
        0-3,10,20-22    both

    Returned in reading order with each code once. What was typed sets
    which codes, not their order on the plate: the plate is laid out the
    way the numerals underneath are read, and a set is the same set
    whichever end it was typed from.

    Code 0 is dropped from a range unless it is asked for on its own or
    `include_zero` is set. Field-reported 2026-09-05: a read needs both
    side switches fully depressed *and* at least one bit standing, so a
    disc with nothing set is silent by the toy's own rule. It is still
    buildable — `--codes 0` gets it — because a silent disc is exactly
    what a probe for the switch behaviour wants. It just has no business
    taking a slot on a plate of thirty-two animals.
    """
    out = set()
    for chunk in str(spec).replace(" ", "").split(","):
        if not chunk:
            continue
        lo, dash, hi = chunk.partition("-")
        try:
            a = int(lo)
            b = int(hi) if dash else a
        except ValueError:
            raise ValueError(f"{chunk!r} is not a code or a range of them")
        if b < a:
            a, b = b, a                    # 31-0 asks for the same set
        if a < 0 or b >= limit:
            raise ValueError(f"codes run 0-{limit - 1}, so {chunk!r} is "
                             f"outside the set")
        out.update(range(a, b + 1))
    if not out:
        raise ValueError("no codes given")
    if 0 in out and len(out) > 1 and not include_zero:
        out.discard(0)
    return sorted(out)


def plate_cols(n, pitch, bed=BED, margin=PLATE_MARGIN, gap=PLATE_GAP):
    """As square a grid as the count allows, and never wider than the bed.

    Six across is what thirty-two of these need; three of them should not
    be laid out in the same six-wide grid with half a bed of air beside
    them, because the packer downstream reads the arrangement's extents.
    """
    fits = max(1, int((bed[0] - 2 * margin + gap) // pitch))
    return max(1, min(fits, int(np.ceil(np.sqrt(n)))))


def edges(widths=WIDTHS, outer_dia=OUTER_DIA, land=LAND,
          inner_dia=INNER_DIA, nub_dia=NUB_DIA):
    """Outer radius of every band: the centre disc, its four rings, the rim
    relief, the lip and the land. The first entry is bit 0's own edge, not a
    preamble to the code -- the disc is a bit like the rings are.

    When the ring widths stop short of the field edge, the gap is a real
    band and not a rounding error: it is the groove that clears the reader's
    rim, and it is floor on every code. Widths that reach the edge get no
    such band, so an explicit --widths spanning the whole field still builds
    exactly what it used to.
    """
    e = [nub_dia / 2]
    for w in widths:
        e.append(e[-1] + w)
    if inner_dia / 2 - e[-1] > 1e-6:
        e.append(inner_dia / 2)
    e += [outer_dia / 2]
    if land:
        e += [e[-1] + land]
    return e


def bands(code, floor, bit_h, rim_h, land_h=None, n_relief=0):
    """Top height of each band, walking outward from the axis.

    Every one of the five carries code, the centre disc included: the
    reader has a plunger on the axis and it reads what is under it like any
    other. The lip and the land outside them are structure -- the lip
    presses the switch that starts a read, the land is the flat the toy's
    face meets -- and neither is ever a 0.
    """
    z = [bit_h if code >> k & 1 else floor for k in range(BANDS)]
    z += [floor] * n_relief          # the rim groove: never a 1
    z += [rim_h]
    return z + [land_h] if land_h is not None else z


def profile(code, edge, floor, bit_h, rim_h, kerf, land_h=None):
    """Closed (r, z) staircase, ready to revolve.

    kerf moves each material/air boundary so a standing ring comes out at
    its drawn width rather than a nozzle fatter. It applies only where the
    height actually changes: two adjacent 1s are one wide ring with no
    boundary between them to correct.

    Clearance is the caller's: it belongs to the walls that locate the plug
    and not to the bands that carry the code, and only the caller knows
    which of these radii are which.
    """
    z = bands(code, floor, bit_h, rim_h, land_h,
              len(edge) - BANDS - (1 if land_h is None else 2))
    r_out = list(edge)
    n = len(r_out)

    pts = [(0.0, z[0])]
    for k in range(n):
        r = r_out[k]
        if k + 1 < n and z[k] != z[k + 1] and kerf:
            # the taller side is the material: pull its edge back by half
            r += kerf / 2 if z[k] < z[k + 1] else -kerf / 2
        pts.append((r, z[k]))
        if k + 1 < n:
            pts.append((r, z[k + 1]))
    pts += [(r_out[-1], 0.0), (0.0, 0.0)]
    # walked outward along the tops and back under the base, which traces the
    # section clockwise; revolve reads the winding as the surface orientation,
    # so drawn this way every normal points into the solid and the mesh comes
    # out inside-out -- watertight, and of negative volume.
    return np.array((pts + [pts[0]])[::-1]), r_out[-1]


def _glyph_outline(text, size):
    """Digits as one shapely polygon, centred on the origin.

    matplotlib hands back a flat list of contours with no nesting, so the
    counters in 0, 6, 8 and 9 arrive as ordinary rings and would fill in.
    Even-odd resolves them: a contour enclosed by an odd number of others
    is a hole.
    """
    from matplotlib.textpath import TextPath
    from matplotlib.font_manager import FontProperties
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    tp = TextPath((0, 0), text, size=size,
                  prop=FontProperties(family="DejaVu Sans", weight="bold"))
    rings = [Polygon(c).buffer(0) for c in tp.to_polygons() if len(c) >= 3]
    rings = [r for r in rings if not r.is_empty]
    if not rings:
        raise ValueError(f"no glyph outline for {text!r}")
    depth = [sum(1 for o in rings if o is not r
                 and o.area > r.area and o.contains(r.representative_point()))
             for r in rings]
    shell = unary_union([r for r, d in zip(rings, depth) if d % 2 == 0])
    holes = unary_union([r for r, d in zip(rings, depth) if d % 2 == 1])
    poly = shell.difference(holes) if not holes.is_empty else shell
    lo, up = poly.bounds[:2], poly.bounds[2:]
    from shapely import affinity
    return affinity.translate(poly, -(lo[0] + up[0]) / 2, -(lo[1] + up[1]) / 2)


def numeral(code, height, size=NUM_SIZE):
    """The code as a solid, standing on z=0, ready to cut or to add.

    Mirrored in x: this face is read from underneath, and a numeral that
    reads correctly from above is backwards the moment the part is flipped.
    """
    poly = _glyph_outline(str(code), size)
    # two digits are two disjoint polygons; extrude_polygon takes one at a
    # time, and the boolean engine is happy with the pair as separate shells
    parts = [trimesh.creation.extrude_polygon(g, height)
             for g in getattr(poly, "geoms", [poly])]
    m = trimesh.util.concatenate(parts) if len(parts) > 1 else parts[0]
    m.apply_transform(np.diag([-1.0, 1.0, 1.0, 1.0]))
    m.fix_normals()
    return m


def build(code, floor=FLOOR, relief=RELIEF, rim=RIM, kerf=0.0, slack=SLACK,
          segments=512, marks="engrave", widths=WIDTHS, outer_dia=OUTER_DIA,
          land=LAND, lip_stand=LIP_STAND, label=None,
          nub_dia=NUB_DIA):
    if not 0 <= code < 2 ** BANDS:
        raise ValueError(f"code must be 0-{2 ** BANDS - 1}")
    if len(widths) != BANDS - 1 or any(w <= 0 for w in widths):
        raise ValueError(f"need {BANDS - 1} positive ring widths (bit 0 is "
                         f"the centre disc, whose radius is its own), "
                         f"got {widths}")
    if floor < 3 * NOZZLE:
        raise ValueError(f"floor {floor:.2f} mm is under three nozzle widths "
                         f"({3 * NOZZLE:.1f}) -- nothing holds the rings on")
    if not 0 < relief <= rim:
        raise ValueError(f"relief {relief:.2f} must be positive and no taller "
                         f"than the rim ({rim:.2f}); outside that the square "
                         f"wave loses a level and codes stop differing")
    if marks == "engrave" and NUM_DEEP >= floor:
        raise ValueError(f"a numeral {NUM_DEEP} mm deep would punch through "
                         f"a {floor:.2f} mm floor")
    if land and not 0 < lip_stand < rim:
        raise ValueError(f"the lip stands {lip_stand:.2f} above the land, "
                         f"which has to be more than nothing and less than "
                         f"the {rim:.2f} it stands above the bore floor")
    if land < 0:
        raise ValueError(f"a land {land:.2f} wide is not a land")
    edge = edges(widths, outer_dia, land, INNER_DIA, nub_dia)
    # not BANDS: a rim-relief band sits between the last ring and the lip
    lip = len(edge) - (2 if land else 1)
    if edge[lip] <= edge[lip - 1]:
        raise ValueError(f"the bands reach ø{2 * edge[lip - 1]:.2f}, "
                         f"which leaves no lip inside ø{outer_dia:.2f}")
    bit_h, rim_h, height = floor + relief, floor + rim, floor + rim
    # The land is measured down from the lip's own top face, so it does not
    # move when the bore depth is read again: only the 1.38 the lip stands
    # proud has to hold, and that is the travel the switch sees.
    land_h = None if not land else rim_h - lip_stand
    # The clearance opens the cavity, because that is the surface that
    # binds: the disc goes over the reader, so the reader's pad runs against
    # the wall where bit 5 ends. The outside of the lip touches nothing and
    # does not move, so the lip gives up the wall thickness instead. Half of
    # a diametral number goes on the radius.
    #
    # It is also the one band edge that can move without saying anything
    # different: the outermost sensor sits near r 10.9, well inside it, so
    # widening the field at r 13.94 changes what the disc clears and not
    # what it reads.
    if slack:
        edge = list(edge)
        edge[lip - 1] += slack / 2

    prof, r_out = profile(code, edge, floor, bit_h, rim_h, kerf, land_h)
    m = trimesh.creation.revolve(prof, sections=int(segments))
    if marks == "engrave":
        # the cutter starts below the part so the cut opens on the bed face
        cut = numeral(code if label is None else label, NUM_DEEP * 3)
        cut.apply_translation([0, 0, NUM_DEEP - NUM_DEEP * 3])
        m = m.difference(cut, engine="manifold")
    elif marks == "emboss":
        raised = numeral(code if label is None else label, NUM_DEEP)
        raised.apply_translation([0, 0, -NUM_DEEP])
        m = m.union(raised, engine="manifold")

    z = bands(code, floor, bit_h, rim_h, land_h, lip - BANDS)
    rep = dict(
        code=int(code), bits=format(code, f"0{BANDS}b"),
        # what is actually engraved underneath. Four discs on the test plate
        # are all code 16 and are told apart only by this, so a report that
        # printed the code would name four different parts identically.
        label=str(code) if label is None else str(label),
        # the pattern is what the reader sees: five positions, then the
        # lip. The land outside it is a face, not a level, and says nothing.
        pattern="".join("#" if t > floor else "." for t in z[:lip + 1]),
        disc_dia=nub_dia, widths=[round(w, 5) for w in widths],
        # named for the coding, not for the widest thing on the part: the
        # inner diameter is where the bands stop and the outer is the
        # flange, both with or without a lip outboard of them
        inner_dia=round(2 * edge[lip - 1], 3),
        outer_dia=round(2 * edge[lip], 3),      # after any clearance
        part_dia=round(2 * r_out, 3),
        edges=[round(2 * e, 4) for e in edge],
        floor=round(floor, 2), relief=round(relief, 2), rim=round(rim, 2),
        bit_h=round(bit_h, 2), rim_h=round(rim_h, 2), height=round(height, 2),
        kerf=round(kerf, 3), slack=round(slack, 3), segments=int(segments),
        land=None if not land else dict(
            width=round(land, 3), outer_dia=round(2 * r_out, 3),
            stand=round(lip_stand, 3), height=round(land_h - floor, 3)),
        numerals=marks or "none",
        facet_err=round(float(r_out * (1 - np.cos(np.pi / segments))), 4))
    # A ring is only as narrow as its own band when it has air on both
    # sides. Runs of adjacent 1s merge into one wider ring. Bit 0 is a disc
    # rather than a ring -- alone it is a ø4.75 button, which is not a thin
    # feature. Ring 4 used to be exempt because it abutted the lip, which is
    # taller and braced it; the rim relief now puts floor on its outer side,
    # so it can stand alone, and at 1.6275 it is the narrowest ring here.
    # --widths exists to try other splits of the SAME field, so a set that
    # does not sum back to the measured inner diameter is a slip rather than
    # a choice. It is not refused -- the geometry is still coherent -- but it
    # says so, because the number that moved is the one that has to fit.
    # against the DRAWN field, not the built one: the cavity is opened by
    # `slack` on purpose, so comparing the built number here fired the
    # warning on every correct part and said the widths were wrong when the
    # only thing that had moved was the fit.
    if abs(rep["inner_dia"] - slack - INNER_DIA) > 0.01:
        rep["warn"] = (f"these widths put the drawn inner diameter at "
                       f"{rep['inner_dia'] - slack:.3f}, not the measured "
                       f"{INNER_DIA}")
    lone = [i for i in range(1, BANDS)
            if code >> i & 1
            and not code >> (i - 1) & 1
            and (i + 1 >= BANDS or not code >> (i + 1) & 1)]
    rep["thinnest_ring"] = round(min(widths[i - 1] for i in lone) - kerf,
                                 4) if lone else None
    return m, rep


PROBE_W = 1.20           # a probe ring's width: wide enough to be sure of
                         # catching a plunger, narrow enough to say where
PROBE_STEP = 1.25        # 0.05 of daylight between probes, so the sweep is
                         # effectively contiguous and nothing hides in a gap


def probe(a, b, label, **kw):
    """A disc with exactly one raised ring, between radii a and b.

    No new geometry: it is an ordinary coded disc whose band widths have
    been chosen to put the single standing band where the probe wants it.
    The ring goes in the outermost of the four ring positions and the space
    inside it is divided among the other three, all of them floor.

    The point of the shape is that the toy has told us a disc with nothing
    standing is silent. So one ring is a detector: it speaks only if it
    lands on a plunger, and two probes that speak with the SAME animal are
    on the same plunger. That reads the plunger radii, and their grouping,
    without anyone having to know which animal is which code.
    """
    outer = INNER_DIA / 2
    if not 0 < a < b or b > outer + 1e-9:
        raise ValueError(f"probe {a:.2f}-{b:.2f} is not inside Oe{INNER_DIA}")
    tail, lead = outer - b, a - NUB_DIA / 2
    # Which band carries the ring depends on where it is, because the bands
    # that are NOT the ring still have to have a width. Near the axis there
    # is no room inside the ring, so the centre disc shrinks to the probe's
    # inner radius and the ring takes the first ring position. Near the rim
    # there is no room outside it, so the ring takes the last position and
    # the space inside is divided three ways. Either way every other band is
    # floor, which is what makes the disc a detector.
    if tail >= 3 * NOZZLE:
        return build(1 << 1, nub_dia=2 * a,
                     widths=(b - a, tail / 3, tail / 3, tail / 3),
                     label=label, **kw)
    if lead < 3 * NOZZLE:
        raise ValueError(f"probe {a:.2f}-{b:.2f} has room on neither side")
    return build(1 << (BANDS - 1),
                 widths=(lead / 3, lead / 3, lead / 3, b - a),
                 label=label, **kw)


def test_plate(out, **kw):
    """One plate that answers every open question about this reader.

    P0 is the centre disc alone. P1.. sweep a single ring outward across the
    whole field, which locates all five plungers and, where they stop
    speaking, locates whatever it is out at the rim that swallows a read.
    Then three real codes: 16 is the reported failure with the new relief
    groove under it, 31 is every band standing at once, and 14 should say
    koala -- that last one is the only test here that can tell a correct
    band grid from a shifted one, because 1-15 give fifteen different
    animals either way.
    """
    discs, reps = [], []
    # One bit at a time, on the regridded bands. These are the probes: each
    # raises exactly one band, so each should press exactly one plunger and
    # name one animal. FIVE different animals means five bands that work --
    # and it is the direct test of the fault, because under the old grid
    # bit 4 drove two plungers and bit 5 drove none.
    for code in (1, 2, 4, 8, 16):
        m, r = build(code, **kw)
        discs.append(m); r["test"] = f"bit {code.bit_length()} alone"
        reps.append(r)
    # Bit 5 again at two other seat widths, and R12 is a negative control:
    # its seat is 1.25 against a reader rim measured near 1.50, so the rim
    # should not fit and the disc should stay silent. If R12 speaks the seat
    # is not what gates the read; if R12 is silent while 16 and R22 speak,
    # the mechanism is pinned and the rim's width is bracketed to 0.5 mm.
    for rel in (1.25, 2.25):
        kw2 = dict(kw, widths=measured_widths(INNER_DIA / 2 - rel))
        m, r = build(16, label=f"R{int(rel * 10):02d}", **kw2)
        discs.append(m)
        r["test"] = (f"bit 5, rim seat {rel:.2f}"
                     + (" -- NEGATIVE CONTROL, should stay silent"
                        if rel < 1.5 else " -- generous seat"))
        reps.append(r)
    for code, why in ((24, "bits 4+5 -- Brett's manual press said whale"),
                      (14, "should say koala -- tests the whole grid"),
                      (31, "every band standing at once")):
        m, r = build(code, **kw)
        discs.append(m); r["test"] = why; reps.append(r)

    pitch = 2 * (OUTER_DIA / 2 + LAND) + PLATE_GAP
    cols = plate_cols(len(discs), pitch)
    sc = trimesh.Scene()
    for i, (m, r) in enumerate(zip(discs, reps)):
        col, row = i % cols, i // cols
        g = m.copy()
        g.apply_translation([col * pitch, -row * pitch, 0])
        sc.add_geometry(g, geom_name=f"zoo_{r.get('probe') and 'probe' or 'code'}"
                                     f"_{i:02d}")
    sc.export(out)
    return reps, cols


def plate(codes=None, cols=None, gap=PLATE_GAP, bed=BED, **kw):
    """A set of codes on one bed, in reading order, as one scene.

    Row-major from the back left, so the plate is laid out the way the
    numerals underneath are read rather than in whatever order a packer
    happened to find tightest.
    """
    codes = list(range(2 ** BANDS)) if codes is None else list(codes)
    pitch = ((kw.get("outer_dia") or OUTER_DIA)
             + 2 * (LAND if kw.get("land") is None else kw["land"]) + gap)
    cols = cols or plate_cols(len(codes), pitch, bed, gap=gap)
    rows = int(np.ceil(len(codes) / cols))
    span = (cols * pitch - gap, rows * pitch - gap)
    room = (bed[0] - 2 * PLATE_MARGIN, bed[1] - 2 * PLATE_MARGIN)
    if span[0] > room[0] or span[1] > room[1]:
        raise ValueError(f"{len(codes)} parts at {pitch:.1f} mm pitch need "
                         f"{span[0]:.0f}x{span[1]:.0f} mm, and the bed gives "
                         f"{room[0]:.0f}x{room[1]:.0f}")
    sc, reps = trimesh.Scene(), []
    for n, c in enumerate(codes):
        m, rep = build(c, **kw)
        m.merge_vertices()
        m.update_faces(m.nondegenerate_faces())
        m.process(validate=True)
        if not m.is_watertight:
            raise ValueError(f"code {c} came out leaky")
        m.apply_translation([0, 0, -m.bounds[0][2]])
        i, j = n % cols, n // cols
        m.apply_translation([(i - (cols - 1) / 2) * pitch,
                             ((rows - 1) / 2 - j) * pitch, 0])
        sc.add_geometry(m, geom_name=f"ring-{c:02d}")
        reps.append(rep)
    return sc, reps, span, (cols, rows)


def emit_plate(sc, reps, span, grid, out):
    vol = sum(float(g.volume) for g in sc.geometry.values())
    rep = dict(plate=True, count=len(reps), cols=grid[0], rows=grid[1],
               codes=[r["code"] for r in reps],
               span=[round(span[0], 1), round(span[1], 1)], bed=list(BED),
               tris=int(sum(len(g.faces) for g in sc.geometry.values())),
               volume_cm3=round(vol / 1000, 2),
               est_g=round(vol / 1000 * 1.24, 1),
               height=reps[0]["height"], numerals=reps[0]["numerals"],
               watertight=all(g.is_watertight for g in sc.geometry.values()))
    if out and rep["watertight"]:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        sc.export(out)
        from embed_settings import embed
        embed(out, brim=False)
        rep["file"] = os.path.basename(out)
    return rep


def emit(m, rep, out):
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.process(validate=True)
    m.apply_translation([0, 0, -m.bounds[0][2]])
    rep["watertight"] = bool(m.is_watertight)
    rep["volume_cm3"] = round(float(m.volume) / 1000, 2)
    rep["est_g"] = round(float(m.volume) / 1000 * 1.24, 1)
    if out and rep["watertight"]:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        sc = trimesh.Scene()
        sc.add_geometry(m, geom_name=f"binary_ring_{rep['code']:02d}")
        sc.export(out)
        from embed_settings import embed
        embed(out, brim=False)
        rep["file"] = os.path.basename(out)
    return rep["watertight"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", help="which codes to make: one (7), a range "
                                    "(1-31), a list (1,2,4,8,16), or a "
                                    "mixture. Several arrive on one bed")
    ap.add_argument("--code", type=int, help=f"one code, 0-{2 ** BANDS - 1}")
    ap.add_argument("--all", action="store_true",
                    help="every code, one file each")
    ap.add_argument("--plate", action="store_true",
                    help="every code on one bed (the same as --codes 1-31)")
    ap.add_argument("--floor", type=float, default=FLOOR,
                    help="solid backing below the ring floor (mm)")
    ap.add_argument("--relief", type=float, default=RELIEF,
                    help="ring floor to the top of a bit ring (mm)")
    ap.add_argument("--rim", type=float, default=RIM,
                    help="ring floor to the top of the flange (mm)")
    ap.add_argument("--widths", type=lambda v: tuple(map(float, v.split(","))),
                    default=WIDTHS,
                    help=f"{BANDS} comma-separated band widths, innermost "
                         f"first (default {','.join(map(str, WIDTHS))})")
    ap.add_argument("--outer", type=float, default=OUTER_DIA,
                    help="flange outer diameter (mm)")
    ap.add_argument("--land", type=float, default=LAND,
                    help="flat land around the lip, radially (mm; 0 = none)")
    ap.add_argument("--lip-stand", type=float, default=LIP_STAND,
                    help="how far the lip stands above that land (mm)")
    ap.add_argument("--kerf", type=float, default=0.0,
                    help="width taken off each standing ring (mm)")
    # Measured across, not on the radius: a printed disc bound on the
    # reader, and the fault was reported the way the hole is measured.
    ap.add_argument("--slack", type=float, default=SLACK,
                    help="how much wider the cavity is built than drawn, "
                         "measured across (mm)")
    ap.add_argument("--segments", type=int, default=512)
    ap.add_argument("--numerals", choices=("engrave", "emboss", "none"),
                    default="engrave",
                    help="the code on the underside. engrave is the default "
                         "because that face meets the bed: raised digits "
                         "would be the only thing touching it")
    ap.add_argument("--out")
    ap.add_argument("--outdir")
    a = ap.parse_args()

    kw = dict(floor=a.floor, relief=a.relief, rim=a.rim, kerf=a.kerf,
              slack=a.slack, segments=a.segments,
              marks=None if a.numerals == "none" else a.numerals,
              widths=a.widths, outer_dia=a.outer,
              land=a.land, lip_stand=a.lip_stand)

    # One spelling of the question underneath: which codes are wanted.
    # --code and --plate are the ends of the same range, kept because they
    # were the interface before a set could be asked for in one go.
    spec = a.codes if a.codes is not None else (
        str(a.code) if a.code is not None else
        (f"0-{2 ** BANDS - 1}" if a.plate else None))
    if spec is None and not a.all:
        print(json.dumps({"ok": False,
                          "error": "need --codes, --code, --all or --plate"}))
        return 1
    try:
        codes = (list(range(2 ** BANDS)) if a.all and spec is None
                 else parse_codes(spec))
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1

    # A set is one plate. One code is one disc: a lone part on a plate is
    # the same file with a scene wrapped round it, and the shop packs its
    # own beds, so it would be packing a plate inside a plate.
    if len(codes) > 1 and not a.all:
        try:
            sc, reps, span, grid = plate(codes, **kw)
        except ValueError as e:
            print(json.dumps({"ok": False, "error": str(e)}))
            return 1
        out = a.out or (os.path.join(a.outdir,
                                     f"binary-ring-set-{len(codes)}.3mf")
                        if a.outdir else None)
        rep = emit_plate(sc, reps, span, grid, out)
        print(json.dumps({"ok": rep["watertight"], **rep}))
        return 0 if rep["watertight"] else 1

    reps, ok = [], True
    for c in codes:
        try:
            m, rep = build(c, **kw)
        except ValueError as e:
            print(json.dumps({"ok": False, "error": str(e)}))
            return 1
        out = a.out if a.out and len(codes) == 1 else (
            os.path.join(a.outdir, f"binary-ring-{c:02d}"
                         f"-R{a.rim:g}-B{a.relief:g}"
                         f"-F{a.floor:g}.3mf") if a.outdir else None)
        ok &= emit(m, rep, out)
        reps.append(rep)

    print(json.dumps({"ok": ok, **(reps[0] if len(reps) == 1
                                  else {"count": len(reps), "parts": reps})}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
