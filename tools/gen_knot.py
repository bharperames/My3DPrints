#!/usr/bin/env python3
"""The Knot -- three bolts woven so that none of them can turn. NOT BUILT YET.

This file is a design brief with the geometry already settled, not a working
generator. Nothing here runs. It exists so the next session starts from the
decisions rather than re-deriving them, and it sits beside the code that
will act on it because that is where this project keeps its reasoning.

WHY THE SEED CUBE IS NOT THE PUZZLE

`gen_puzzle.py` builds the primitive: one bolt, two halves. It is naive on
purpose -- it has exactly one affordance and that affordance is visible. You
can see the head, there is one thing to do to it, and doing it works. Six of
those in a row is still six obvious turns. What follows is what makes it a
puzzle instead.

THE VOCABULARY

Six primitives, each an edge in a dependency graph:

  P1  coaxial split    blocks pulling; costs a full unscrew to defeat
  P2  pinned shear     a shank crossing a sliding joint; blocks the slide
  P3  head capture     a head sunk in a NEIGHBOUR's hex pocket cannot turn
                       until that neighbour moves axially by the pocket depth
  P4  travel block     rotation is free but the shank has no corridor to
                       retreat into
  P5  captive nut      a nut trapped in a slot cannot rotate, so turning the
                       bolt drives it ALONG the shank like a screw jack --
                       turning here moves something THERE
  P6  proud head       a head standing proud blocks a neighbour's slide, so
                       it must be screwed further IN to release it

P5 and P6 are what lift it out of naive. P5 separates cause from effect in
space; P6 is a retrograde move -- the correct action is to do up the thing
you are trying to undo. Either is worth more than three extra blocks.

THE ARCHITECTURE: a cycle, not a chain

Arrange P3 in a ring. Bolt i's head sits in a pocket in the block that bolt
i+1 clamps, cyclically. Then no bolt can turn, because every bolt is blocked
by another bolt, and there is no free first move. The entry has to be a
SLIDE nobody looks for -- one block with a few millimetres of axial float
because one of its bores is plain rather than threaded. Find the slide and
the cycle unzips.

A chain would be a strictly forced sequence, which reads as tedious. Three
is the right number; past three the extra moves are all forced.

THE WEAVE, ALREADY CHECKED

Three bolt axes, cyclic under a 120 degree turn about [1,1,1]:

    A along x at (y,z) = (a, 0)
    B along y at (z,x) = (a, 0)
    C along z at (x,y) = (a, 0)

Every pair is skew and their common perpendicular is the third coordinate,
so all three pairwise distances are exactly `a` whatever a is. That equal
spacing is what lets ONE block design serve all three positions -- print
three of one part, not three different parts.

With the seed's thread (major r 8.0, ø16):

    a      shank gap    block must reach past its own axis
    18.0     2.00              26.0
    20.0     4.00              28.0
    22.0     6.00              30.0

"Must reach" is a + R: a block has to be deep enough to swallow its
neighbour's bolt, because that crossing is the P2 that stops it sliding.

THE LAW THAT CONSTRAINS THE LAYOUT

From `gen_puzzle.py`, paid for twice:

    A keyed head cannot be screwed into its own keyway.

So a block that captures a head takes a CLEARANCE bore; the thread lives
only in the block the tip reaches. Clearance hole near, thread far. In the
cycle that means: bolt i's head sits in block i (plain bore), and bolt i's
thread engages block i+1. Get this backwards and the object cannot be
assembled, and no disassembly argument will tell you.

HOW TO KNOW IT IS A GOOD PUZZLE

Do not argue it. `assembly.py` already has the machinery: `disassemble()`
sweeps every body and every pair under slide and both screw handednesses and
reports what it cannot free. Extend it to report, per state, HOW MANY moves
are legal. Then the design has numbers:

    legal first moves        want exactly 1
    shortest solve length    want 7-9
    retrograde move present  want yes (a P6 somewhere on the path)

Iterate the geometry against those instead of against a hunch. And keep a
negative control -- a variant that must fail -- because both real bugs in
this toolchain were caught by one: a left-handed sweep that had to foul, and
a mobility search that called the WORKING design welded (every path started
at the home pose, where assembled parts touch and FCL scores contact as a
collision).

OPEN DECISIONS

  * `a`, and the block section that follows from it. 18 is tight (2 mm of
    daylight between neighbouring shanks); 20-22 is comfortable and makes
    the assembly about 110-120 mm across.
  * Whether the first Knot uses P5. It is the strongest idea here and also
    the most parts. A version without it is still a genuine cycle.
  * Whether the wrench (`gen_wrench.py`) becomes a structural rib that has
    to be extracted before it can be used. Cheap, and a good joke.

MATERIAL

PETG, not PLA, and say so on the card before the settings. Silk PLA snapped
the seed cube's bolt in several places under hand torque -- the thread was
fine, the filament was not.
"""
raise SystemExit(__doc__.splitlines()[0])
