#!/usr/bin/env python3
"""The Print Shop catalog: everything this machine knows how to print.

Three kinds of entry, deliberately uniform so the shop UI and the plate
packer never care which is which:

  generated   a fixed design this repo builds from source (dice orb,
              coupler nut, plate board). No knobs; one canonical file.
  parametric  a design with dials and a live preview (chain, sphere
              stand, cage). Parameters key the generated file.
  library     a file found on disk — scanned out of ~/Downloads or sitting
              in models/ — indexed, measured, and printable as-is.

Every entry resolves to a 3MF on disk plus a measured footprint, which is
all the packer needs. Anything the packer cannot measure is not sellable.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODELS = os.path.join(ROOT, "models")
CUSTOM = os.path.join(MODELS, "custom")
PY = os.path.expanduser("~/.claude/skills/3d-print-check/.venv/bin/python")
if not os.path.exists(PY):
    PY = sys.executable

# printer profile — one machine for now, but the shop reads it from here
# rather than hard-coding 256 in a dozen places
PRINTERS = {
    "P2S": dict(name="Bambu Lab P2S", bed=(256.0, 256.0), height=256.0,
                nozzle=0.4, exclude=[]),
}
DEFAULT_PRINTER = "P2S"


def _zoo_animals():
    """What each code says, where the toy has actually said it.

    Empty for the rest on purpose: the mapping is not published anywhere
    and was worked out here by printing a disk and listening.
    """
    import importlib
    try:
        g = importlib.import_module("gen_binary_rings")
        return {str(k): v for k, v in getattr(g, "ANIMALS", {}).items()}
    except Exception:                                       # noqa: BLE001
        return {}


def _p(pid, name, family, kind, blurb, version="0.1.0", **kw):
    """A catalog entry. `version` is declared, not derived: only an author
    knows whether a change is a new design, a reshape, or a fix. The date
    beside it is derived from git, so it cannot drift out of step."""
    return dict(id=pid, name=name, family=family, kind=kind, blurb=blurb,
                version=version, **kw)


# --- kits: parts whose sizes must agree to interoperate ------------------
# A kit owns the parameters that decide fit. The chain's cross-section sets
# the clasp's mouth and the jump ring's section, so ordering a chain and a
# clasp at different diameters is not a choice the shop should offer.
KITS = [
    dict(id="chain_set", version="1.1.0", name="Chain Set",
         family="Designed here",
         blurb="Chain, clasp and jump rings. One cross-section drives all "
               "three: it sets the link, the clasp's mouth and the ring's "
               "section, so the parts can only be ordered as a matched set.",
         shared=[dict(key="dia", label="cross-section", unit="mm", min=2,
                      max=8, step=0.25, val=3.25)],
         members=[
             dict(part="chain", label="Chain",
                  own=[dict(key="links", label="links", min=2, max=100,
                            step=1, val=5),
                       dict(key="len", label="link length", unit="mm",
                            min=14, max=60, step=1, val=19),
                       # a round tube meets the bed on a line and the slicer
                       # lays a single bead per link; the flat gives it a pad
                       dict(key="foot", label="bed foot", unit="mm",
                            min=0.0, max=0.8, step=0.1, val=0.4,
                            derived="the printer")]),
             dict(part="clasp", label="Lobster clasp"),
             dict(part="jump_ring", label="Jump ring"),
         ]),
    dict(id="montessori", version="1.3.0",
         name="Montessori Nuts & Bolts", family="Montessori",
         blurb="Companions for the Montessori set. The thread is cast from "
               "the designer's own nut, so every piece mates with the "
               "original bolts and with each other.",
         shared=[],
         members=[
             dict(part="mont_double", label="Double nut (coupler)"),
             dict(part="mont_plate", label="Base plate 2×3"),
             dict(part="wrench", label="Nut wrench"),
         ]),
]

# The shelves a card can sit on, in the order they are shown. The names are
# what the headings say; the order is the whole point -- work that has been
# printed comes before work that has not, and files that were downloaded come
# last however many of them there are.
SHELVES = [
    dict(id="proven", label="Printed and proven",
         note="These have been through the printer and came out right."),
    dict(id="designed", label="Designed here",
         note="Built from source in this repo. Not yet printed."),
    dict(id="reference", label="Kept for reference",
         note="Here to be read, not printed \u2014 each one is the negative "
              "control for a design on a shelf above."),
    dict(id="library", label="Library",
         note="Files found on disk, indexed and measured. Printable as-is."),
    dict(id="experimental", label="Experimental",
         note="Plates kept as numbered iterations of a design still being "
              "worked out. Each one is what was actually printed, so a "
              "later revision can be compared against it rather than "
              "remembered."),
]

# --- parts: each resolves to one 3MF on disk -----------------------------
PARTS = [
    _p("wrench", "Nut Wrench", "Montessori", "generated",
       "Combination spanner for the Montessori hex: a six-point box end one "
       "side, an open jaw the other. One size drives the nuts and both bolt "
       "heads.",
       version="1.0.0", gen=["gen_wrench.py"], out="wrench-af50.3mf",
       proven="Printed perfect. Turns the nuts and both bolt heads; the "
              "0.45 mm fit and the 2.67 jaw safety hold up in the hand."),
    _p("dice_orb", "Dice Orb", "Designed here", "generated",
       "A standard d20 captive in a rib-and-ring shaker sphere.",
       version="3.2.0",
       gen=["gen_dice_cage.py"], out="dice-cage.3mf",
       proven="Green PLA, outer brim on — clean; the brim is what holds the "
              "die pedestal down.",
       # printed twice: it failed brimless and came out perfect with an
       # outer brim holding the die pedestal down
       brim="on"),
    _p("mont_double", "Double Nut (coupler)", "Montessori", "generated",
       "Joins two Montessori bolts end to end. Both bore entries run out to "
       "the thread crest at 45 degrees, so the face that prints downward "
       "has no ceiling to droop into the hole.",
       version="1.3.1",
       proven="Clean bottom face. The thin first thread is inherent and is "
              "still there; what stopped the strings was taking the "
              "unsupported ceiling under it from 557 to 15 mm2.",
       gen=["gen_montessori.py", "--part", "double-nut"],
       out="montessori-double-nut.3mf"),
    _p("mont_plate", "Base Plate 2×3", "Montessori", "generated",
       "Six threaded sockets to stand the bolts in.",
       proven="Printed well at 390 g. Shares the double nut's entry "
              "chamfer; its sockets open upward, so they were never the "
              "face at risk.",
       # shares the double nut's entry chamfer; its sockets open upward, so
       # the reshape is cosmetic here rather than a printability fix
       version="1.2.2",
       gen=["gen_montessori.py", "--part", "plate"],
       out="montessori-plate-2x3.3mf"),
    _p("clasp", "Lobster Clasp", "Designed here", "generated",
       "Flexure-gate clasp, sized to the chain it ends. Chunky against its "
       "width the way a real one is, flat on the bed and crowned above, so "
       "it has form in the hand instead of the square edges of a cut-out.",
       version="2.3.0",
       gen=["gen_clasp.py", "--part", "clasp"], out="clasp-only-D{dia:g}.3mf"),
    _p("jump_ring", "Jump Ring", "Designed here", "generated",
       "Butt C-ring that threads the link bore and the clasp's eye.",
       version="2.0.0",     # round wire, the same section as the chain
       gen=["gen_clasp.py", "--part", "ring"], out="ring-only-D{dia:g}.3mf"),
    _p("chain", "Chain", "Designed here", "parametric",
       "Print-in-place stadium links, cut flat where they meet the bed so "
       "each link lands on a pad instead of a tangent line. A chain too "
       "long to lie straight on the plate is coiled instead, at a radius "
       "the joint has been measured to bend through.",
       version="1.2.0",
       gen=["gen_chain.py"],
       proven="48 links coiled, 0.6 mm bed foot, no brim, black PLA at "
              "220/55 — clean first try. The same chain brimless on a "
              "tangent-line foot lifted links a few layers in.",
       out="chain-N{links}-L{len:g}-D{dia:g}-F{foot:g}.3mf"),
    _p("sphere_stand", "Sphere Stand", "Stands", "parametric",
       "A ring that cradles a ball on a conformal spherical seat. Set the "
       "ball; the rest follow it at a 45 degree contact.",
       keys="stand display sphere ball",
       # the three printed sizes on the shelf are this card at three ball
       # diameters, not three designs. Listing them separately gave four
       # cards for one thing and buried the configurable one among them.
       supersedes=["sphere_stand_1.0in.3mf", "sphere_stand_2.0in.3mf",
                   "sphere_stand_3.0in.3mf"],
       version="1.0.1",
       gen=["gen_sphere_stand.py"], params=[
           dict(key="ball", label="ball", unit="mm", min=8, max=120,
                step=0.5, val=25.4),
           # derived from the ball. The blurb used to say "leave the last
           # three blank", which was written for a form with text boxes —
           # a slider is never blank, it always says something.
           dict(key="wall", label="wall", unit="mm", min=1.2, max=12,
                step=0.1, val=2.5, derived="ball"),
           dict(key="chamfer", label="rim chamfer", unit="mm", min=0, max=8,
                step=0.1, val=0.8, derived="ball"),
           dict(key="seat", label="air gap", unit="mm", min=0.4, max=12,
                step=0.1, val=1.0, derived="ball")],
       out="sphere-stand"),
    _p("cage", "Geodesic Cage", "Designed here", "parametric",
       "Strut sphere, optionally with a captive ball.",
       version="1.1.0",
       gen=["gen_cage.py"], params=[
           dict(key="dia", label="cage \u00d8", unit="mm", min=30, max=90,
                step=2, val=50),
           dict(key="freq", label="frequency", min=1, max=6, step=1, val=2),
           dict(key="strut", label="strut \u00d8", unit="mm", min=1.4, max=4.5,
                step=0.2, val=2.2),
           dict(key="ball", label="ball \u00d8 (0 = none)", unit="mm", min=0,
                max=40, step=1, val=19)],
       out="cage-D{dia:g}-F{freq}-T{strut:g}-B{ball:g}.3mf",
       brim="on"),      # same thin first layer as the dice orb
    _p("puzzle_seed", "Puzzle Seed Cube", "Designed here", "parametric",
       "A cube split across the bolt rather than along it. Only the lower "
       "half is threaded, and that is not a simplification: a keyed head "
       "can never be screwed into its own keyway. It arrives at the pocket "
       "turning, so it can present the right rotation only once every sixty "
       "degrees \u2014 0.89 mm of descent on this lead \u2014 and it lands "
       "on the top face and grinds instead. So the upper half takes a plain "
       "clearance bore: the bolt drops through it by pure translation, "
       "seats its head, and only then is turned, with the upper half keyed "
       "to the head serving as the wrench that drives it home. Pull and "
       "nothing happens \u2014 the upper half is capped by the head above "
       "and floored by the lower half below. Split it the other way, along "
       "the bolt, and it would not lock at all: a plane through a round "
       "bore leaves one arc over 180 degrees and one under, and the half "
       "holding the shallow arc is a groove, which lifts straight off a "
       "cylinder. Every claim here is proved as a motion rather than a "
       "pose, because a pose cannot tell an assembly that goes together "
       "from one that does not: the insertion is swept at half the running "
       "clearance and the screw-home path over four thousand samples, and "
       "the same sweep run left-handed has to foul. The thread is the "
       "Montessori profile rebuilt rather than copied \u2014 an axial "
       "section of the toddler set\u2019s bolt is a pure cosine whose flank "
       "sits 32.5 degrees off the axis at every scale, which is why a bore "
       "of this family never needs support. The diameter is not kept, so "
       "nothing here fits that set. Ships as three parts on one plate.",
       version="1.1.0",
       proven="Printed and works: it goes together, turns, and comes apart "
              "the way the sweeps said it would. Printed in PLA Silk the "
              "bolt broke in several places while being turned in the "
              "block \u2014 the mechanism was not at fault, the filament "
              "was. Silk PLA is the most brittle thing on the shelf and a "
              "thread in torsion is the worst thing to ask of it. PETG "
              "next.",
       gen=["gen_puzzle.py"], params=[
           dict(key="side", label="block", unit="mm", min=32, max=64,
                step=1, val=40),
           dict(key="thread", label="thread \u00d8", unit="mm", min=10,
                max=26, step=1, val=16),
           dict(key="pocket", label="head pocket", unit="mm", min=3, max=12,
                step=0.5, val=5, derived="thread"),
           # the upper half carries no thread now, so moving the seam up
           # costs it nothing and buys the lower half engagement
           dict(key="split", label="seam height", min=0.35, max=0.65,
                step=0.01, val=0.5, derived="block")],
       out="puzzle-seed-S{side:g}-T{thread:g}-P{pocket:g}-X{split:g}.3mf"),
    _p("knot_bolted", "The Knot", "Designed here", "parametric",
       "Three bars, three bolts, and every bolt in tension. Each one passes "
       "right THROUGH the bar whose counterbore holds its head and threads "
       "into the next bar along, so the three are clamped in a ring and a "
       "pull on the object loads a screw thread. The burr version of this "
       "same weave stopped each head in a blind socket instead \u2014 which "
       "resists sideways and resists nothing whatever against a pull \u2014 "
       "and it came apart under fifty grams. This one does not move: swept "
       "along every direction, in every combination of two bars moving at "
       "once, and again with rotation over seven thousand random screw "
       "motions, the most any part shifts relative to another is nine "
       "tenths of a millimeter, which is the clearance it was built with. "
       "The only way in is to unscrew something, and a pull cannot turn a "
       "screw. Two of the three bolts are keyed \u2014 head sunk in a "
       "hexagonal counterbore, so the bolt can only turn if its bar turns, "
       "and no bar can. The third sits in a round counterbore and turns "
       "freely, which is both the way it was assembled and the way out: "
       "the last thread in a ring cannot be closed by turning a bar, "
       "because by then nothing is free to turn. So the puzzle is to find "
       "which one of three identical faces has the bolt that moves, and "
       "only one of them is live. That one head stands a single thread lead "
       "proud of its face so fingers can reach it \u2014 flush, its hex "
       "leaves three tenths of a millimeter inside the counterbore and "
       "nothing could grip it, and a separate key would be a part that is "
       "not the puzzle. The other two never need touching, because the bar "
       "they thread into is what turns them. Sizing comes from the "
       "counterbore alone now that nothing has to slide, which brings the "
       "cube down from 68 mm to 58. Prints with every threaded bore "
       "vertical, since a bore of this cosine family never presents more "
       "than a 32.5 degree overhang along its own axis at any scale, and "
       "the plain bores lie on their sides where droop costs nothing. "
       "PETG, not PLA \u2014 the seed cube\u2019s bolt snapped in silk PLA "
       "under hand torque, and these are longer and take real tension.",
       proven="Printed in PETG and it works — it goes together and it "
              "holds. The burr version of the same weave, which rested "
              "each head in a blind socket instead, came apart under half "
              "a newton; the bolts are what fixed that.",
       version="0.5.0",
       pages=[dict(label="Watch it go together", href="docs/knot.html")],
       # An X-ray of the assembled weave, captured from the viewer on the
       # assembly page. It shows in one still what the card's own turntable
       # cannot: three bolts in tension, each head buried in the bar it
       # passes through, and every thread engaged inside another bar.
       stills=[dict(src="assets/knot/xray.png", label="X-ray",
                    alt="X-ray view of the assembled knot: three bars in a "
                        "pinwheel with three hex bolts threaded through them")],
       gen=["gen_bolted.py"], params=[
           dict(key="thread", label="thread \u00d8", unit="mm", min=10,
                max=20, step=1, val=12)],
       out="knot-bolted-T{thread:g}.3mf"),
    _p("orbital_jig", "Orbital scanning jig", "Designed here", "parametric",
       "A photogrammetry rig that holds the specimen still and moves the "
       "camera: azimuth on a 242 mm rotor ring riding three 608 bearings, "
       "elevation on a 90-degree quadrant arc the ring carries, and the "
       "camera\u2019s entrance pupil on a 150 mm sphere about the specimen "
       "at every setting. A turntable would rotate the specimen under fixed "
       "lights, and the highlights crawling across enamel between frames "
       "read to structure-from-motion as the surface moving; here the "
       "lights, the backdrop and the tooth never move. Ten printed bodies: "
       "the stator plate with its pedestal and bearing towers, the rotor "
       "ring with 36 detent dimples every ten degrees and a slotted pad, "
       "the arc with its own leg down to that pad, a two-piece carriage "
       "clamped through the arc\u2019s 5.2 mm slot by an M5 thumbscrew, an "
       "receiver with 110 mm of fore/aft travel that takes an Arca plate or "
       "a phone clamp on its 1/4-20 \u2014 the spec\u2019s 40 mm covers one "
       "camera, and a phone\u2019s clamp foot and a full-frame body behind a "
       "90 mm macro sit 90 mm apart \u2014 a detent pawl and three "
       "bearing sleeves. The spec\u2019s numbers were kept where they agree "
       "with each other and derived where they do not: a ring guided on its "
       "perimeter puts the bearing axes 11 mm outside it, at 129, not 95, which lands "
       "them on the corners of the 250 mm triangle; the ring is 242 rather "
       "than 246 because this shop packs with a 5 mm margin and a 3 mm gap "
       "and 246 does not go into that; a 608 has an "
       "8 mm bore and the axle is M4, so each bearing rides a printed sleeve, "
       "and one sleeve\u2019s bore is a millimeter off-center for the 2.0 mm "
       "of preload travel the spec asks for. The arc sits outside the ring "
       "and 73 mm above it, and any bridge from the ring\u2019s side pushes "
       "the ring off the plate, so the bridge is the arc\u2019s: a leg and a "
       "bar that key into the pad. The arc\u2019s plane is 60 mm off the "
       "meridian because the lens and the arc want the same radial band; "
       "the carriage reaches back across so the pupil sits where the "
       "spec\u2019s equations put it, checked at 10, 45 and 80 degrees. "
       "Every clearance is swept, not assumed: the carriage with a phone in "
       "its clamp and again with a Sony \u03b11 behind each of its macros, "
       "through 10\u201380 degrees against the arc and its leg, the "
       "whole rotor side through a full turn against the base, each bearing "
       "proved to touch its race and to collide when pushed a third of a "
       "millimeter in. The pedestal\u2019s top 30 mm drafts inward at 15 "
       "degrees so that at 75 degrees of elevation the camera sees the "
       "platform and nothing under it, measured off the built mesh. PETG, "
       "four or five walls, 25\u201330% gyroid; the base and pedestal in "
       "matte black so they drop out of feature matching. One dial: how far "
       "the specimen\u2019s center sits above the platform, which moves the "
       "ring\u2019s pad and nothing else.",
       keys="jig camera scan photogrammetry turntable fossil",
       version="0.1.0",
       pages=[dict(label="Run the 108-frame capture",
                   href="docs/orbital-jig.html"),
              dict(label="Drives, mounts and the app: the study",
                   href="docs/orbital-jig-plan.html")],
       gen=["gen_orbital_jig.py"], params=[
           dict(key="specimen", label="focal height", unit="mm", min=6,
                max=70, step=1, val=12)],
       # ten flat-bottomed bodies on broad faces; a brim on the ring's
       # underside would scar the detent dimples
       brim="off",
       out="orbital-jig-S{specimen:g}.3mf"),
    _p("tooth_stand", "Fixed X-wing tooth stands", "Stands",
       "parametric",
       "A forest of cones for the orbital jig to fly around. The jig "
       "holds the specimen still and moves the camera, so whatever the "
       "tooth sits on is in all 108 frames: the mount is an optical "
       "part as much as a mechanical one. A shark tooth root is "
       "bilobate, coming down on two lobes with a notch between them, "
       "and each lobe presents a face rather than a point \u2014 so the "
       "tooth rides on FOUR cones, two per lobe, fore and aft, and "
       "never in the notch, which is exactly where the low rings want "
       "to see. Each cone is one solid of revolution: a flank at 7 "
       "degrees included blending through a 2.5 mm fillet onto a round "
       "pad on its arm, and a tip that is a cup rather than a point \u2014 "
       "\u00d82.8 mm on the M and L, smaller on the XS and S \u2014 holding the "
       "dab of museum wax that is what actually stops the tooth "
       "sliding. A sideways newton at any cup reads 9\u201313 MPa against "
       "PETG\u2019s 50, which is where the tips landed after the first "
       "printed set came out too thick in the hand. The taper is held "
       "constant by growing the base with the height, because a 3.5 mm "
       "base is a needle at 12 mm tall and a stump at 24. Four sizes, "
       "because teeth are not one size: FossilRecord measures 6,369 of "
       "them from 6.6 mm to 252, median 25.9, and the spans here come "
       "from that \u2014 root width runs about 0.76 of length across 801 "
       "shape-normalized specimens, the cross span is 0.70 of that so "
       "the tips land on the lobes inboard of the thinning edge, and "
       "the fore/aft span is 0.55 of the root's thickness. The optical "
       "claim is gated geometrically rather than cosmetically: nothing "
       "on the stand rises above the plane of the four dish rims, and "
       "the tests prove that is the right gate by showing a probe that "
       "sees 8% occlusion from a post beside the specimen and 0% from a "
       "120 mm disc beneath it \u2014 nothing under the contact plane can "
       "hide a tooth sitting on it from any camera above the horizon. "
       "Matte black PETG, solid shells, and printed as a plate of four "
       "so the fine tips get their minimum layer time from the travel "
       "between parts. The underside is one flat plane: the hub\u2019s 20 mm "
       "face sits on the pedestal\u2019s 20 mm platform and takes the "
       "tipping moment, a speck of tac holds it there, and off the jig "
       "it sits on a table the same way \u2014 so the jig itself is "
       "unchanged. Nothing keys the rotation on purpose: structure- "
       "from-motion does not care how the tooth is turned, and being "
       "able to spin the quadrilateral onto the lobes is worth more "
       "than an index. The L\u2019s own pair of pins came in from 24 mm "
       "centers to 20.3: printed at 24 they stood 18 mm apart in the "
       "clear at the feet, and a meg root tapers in faster than that, "
       "so it dropped past them instead of being held. 20.3 leaves 15 "
       "mm of clear air, and the posts flex outward a little under a "
       "root, so the working gap is the wider one. The cones here are "
       "part of the body and cannot be swapped, so the saw flank is "
       "drawn into them when --grip saw is asked for rather than "
       "printed as a loose pair \u2014 for posts you can change your mind "
       "about, see the movable X-wing. ",
       keys="stand tooth fossil shark xwing cone jig fixed",
       version="0.3.0",
       pages=[dict(label="Stand the tooth on it, both ways",
                   href="docs/tooth-stand.html")],
       gen=["gen_tooth_stand.py"], params=[
           dict(key="stand", label="sizes", type="checks", val="xs,s,m,l",
                choices=[
                    dict(value="xs", label="XS",
                         hint="teeth 10\u201328 mm \u2014 10 mm across"),
                    dict(value="s", label="S",
                         hint="teeth 25\u201355 mm \u2014 20 mm across"),
                    dict(value="m", label="M",
                         hint="teeth 50\u201395 mm \u2014 38 mm across"),
                    dict(value="l", label="L",
                         hint="teeth 90\u2013150 mm \u2014 60 mm across")])],
       out="tooth-stand-{stand}.3mf"),

    _p("movable_xwing", "Movable X-wing stands \u2014 build your own",
       "Stands", "parametric",
       "Two arms on a pin, with a cone at each end, both flat on the "
       "table so all four spires stand on the ground. Where the fixed "
       "stands settle one span and hold it, this one opens: set the "
       "scissors to the tooth in front of you and the four cups follow. "
       "The lower arm is a plain bar with a \u00d89 hub and a flat parabolic "
       "tail \u2014 a foot against tipping back, as the fixed M and L have, "
       "set square to the crook of the open scissors rather than to the "
       "bar, and short enough to pass under the upper arm at every "
       "setting. Its two spires stand on a short band so a rubber band "
       "can be run round the whole lower half. The upper arm\u2019s ends are "
       "relieved by that hub\u2019s profile and the channel the lower arm "
       "sweeps through, cut as a pocket that opens upward when the arm "
       "prints roof-down, so nothing on it is a bridge. A \u00d83 pin "
       "presses into the lower arm and turns in the upper, and a second "
       "pin goes on the plate a tenth fatter through the upper arm "
       "alone, dimpled on the head, for when the first turns too freely "
       "to hold a setting against the weight of a tooth. The cones are "
       "loose pieces standing on their own pedestals, each sliding onto "
       "a dowel pressed into the arm, with more of the dowel proud than "
       "buried so the post has something to grip. Every fit is drawn "
       "for how PETG prints and measured off the built parts, and two "
       "printed sets have moved all of them: this printer takes about "
       "0.15 mm off a small vertical hole, so \u00d83 pins now run in \u00d83.15 "
       "drawn where they press and \u00d83.25 where they turn. Nothing on "
       "the plate is brimmed: the loose posts stand on a 52 mm\u00b2 foot "
       "and the dowels on 7 mm\u00b2 of \u00d83, which is bed contact enough, and "
       "the pins lie on their \u00d87 heads. The first plate brimmed every "
       "part because brim_type is a plate-wide switch, and that cost "
       "208 mm of brim to cut off, merged the neighboring posts\u2019 brims "
       "into one raft, and took a pin\u2019s head with it. --brim turns it "
       "back on per group if anything ever lifts, and the packer then "
       "leaves air between one brim and the next. A second flank is "
       "there to try: --grip saw cuts a ratchet into the posts, one "
       "barb every 1.2 mm standing 0.35 proud, pointing DOWN, because "
       "four tapered posts squeezing a tapered root push it up and out "
       "and the face that has to do work is the one a rising root runs "
       "into. The barb\u2019s underside stands 39\u00b0 off vertical, so it "
       "prints with no support, and --both-grips puts both flanks on "
       "one plate, a smooth pair and a sawn pair, to swap on one arm "
       "without reprinting the scissors. ",
       keys="stand tooth fossil shark xwing scissor pivot pin adjustable",
       # NOT superseding movable-xwing-r5: that plate carries both grip
       # flanks, a smooth pair and a sawn pair to swap on one arm, and
       # this card builds one grip. Claiming to cover a plate you cannot
       # rebuild is how a record gets quietly dropped.
       version="0.3.0",
       pages=[dict(label="Stand the tooth on it, both ways",
                   href="docs/tooth-stand.html"),
              dict(label="Watch the scissors work",
                   href="docs/xwing.html")],
       gen=["gen_tooth_stand.py"], params=[
           dict(key="stand", label="sizes", type="checks", val="xw_m",
                choices=[
                    dict(value="xw_s", label="X-wing S",
                         hint="scissors: 12\u201330 mm between the pins"),
                    dict(value="xw_m", label="X-wing M",
                         hint="scissors: 14\u201338 mm between the pins"),
                    dict(value="xw_l", label="X-wing L",
                         hint="scissors: 15\u201361 mm between the pins")])],
       out="movable-xwing-{stand}.3mf"),

    _p("gazebo", "Tooth shaped stand with spikes",
       "Stands", "parametric",
       "PLA ONLY. The spikes are springs and they are sized as springs, "
       "in PLA: \u00d81.6 tips on a flank of a degree and four fifths, "
       "giving 0.08 mm at the tip under a root\u2019s share of a 500 g "
       "tooth and taking 10 N before they yield. PETG is half as stiff "
       "and two thirds as strong, and a set printed that way snapped in "
       "the hand; a set sized against PETG\u2019s modulus by mistake and "
       "printed in PLA came out the other way, too rigid to grip at all. "
       "The material is stated here rather than offered because the part "
       "does not work without it. "
       "Six spikes stand on a circle, not on a rectangle, and that is "
       "the whole idea. The four-cone stands put two cups under each "
       "lobe of a bilobate root and keep out of the notch between them; "
       "this one holds the notch. The underside of a root is hollow in "
       "the middle, and a ring set inside that hollow lets it sink until "
       "the cups meet the cavity wall all the way round. The wall slopes "
       "down and outward, so the root centers itself under its own "
       "weight, and turning the tooth changes nothing because a circle "
       "has no orientation. The six are spaced three, four and five "
       "twelfths of a half turn, so the ring offers three slot widths "
       "rather than one and the tooth can be turned to whichever fits: "
       "3.0, 4.4 and 5.7 mm of clear air on the S, 4.5, 6.4 and 8.1 on "
       "the M, and 6.8, 9.4 and 11.8 on the L. "
       "The pedestal is a shark tooth in plan \u2014 a real one, the "
       "silhouette of a scanned Meherrin tooth projected along its "
       "thinnest axis \u2014 and each size is scaled until a tooth at "
       "the top of its band leans at least 15\u00b0 whichever way it "
       "goes, so the shape is decoration paid for in grams and not in "
       "stability. The silhouette stands 2.5 mm proud of the pedestal as "
       "a relief, blended at both ends so it is a slope rather than a "
       "step, with the spikes rising out of it. Nothing overhangs, "
       "nothing needs support or a brim, and nothing is loose.",
       material="PLA only",
       keys="stand tooth fossil shark meg spike ring relief pla",
       supersedes=["gazebo-r21-spiked-stands-pla.3mf"],
       version="0.2.0",
       pages=[dict(label="Stand the tooth on it, both ways",
                   href="docs/tooth-stand.html")],
       gen=["gen_gazebo.py"], params=[
           dict(key="size", label="sizes", type="checks",
                val="gz_sg,gz_mg,gz_lg",
                choices=[
                    dict(value="gz_sg", label="Gazebo S",
                         hint="teeth 25\u201355 mm \u2014 \u00d812 ring, slots 3.0/4.4/5.7"),
                    dict(value="gz_mg", label="Gazebo M",
                         hint="teeth 50\u201395 mm \u2014 \u00d816 ring, slots 4.5/6.4/8.1"),
                    dict(value="gz_lg", label="Gazebo L",
                         hint="teeth 90\u2013150 mm \u2014 \u00d822 ring, slots 6.8/9.4/11.8")])],
       out="gazebo-{size}.3mf"),
    _p("gazebo_rods", "Tooth shaped base for carbon rods",
       "Stands", "parametric",
       "The large ring on its meg-shaped pedestal, with six sockets for "
       "1 mm carbon fiber rods instead of printed spikes. A rod is about "
       "five times stiffer than the spike it replaces and half the "
       "diameter at the tip, so it points where a spike gives, and "
       "nothing about the base has to flex \u2014 which is why this may "
       "be printed in either plastic while the spiked stands may not. "
       "PETG is the better choice for a base that gets handled. The "
       "sockets are 12 mm deep and the rods cut to 36.5 mm. "
       "CHOOSE THE FILAMENT, because the socket is drawn to it. A bore "
       "this small prints about half a millimeter under its drawn size, "
       "which is nothing like the tenth and a half a \u00d83 hole loses, "
       "and the loss is a property of the filament rather than of the "
       "part: read on a gauge with the rod itself, PETG Basic wants "
       "\u00d81.45, PLA Basic \u00d81.5 and PLA Silk \u00d81.7 for the "
       "same rod. One tenth either way flips the fit from refusing the "
       "rod to letting it fall out. A filament with no measurement behind "
       "it is refused rather than guessed \u2014 print the gauge and it "
       "becomes one line.",
       keys="stand tooth fossil carbon rod socket bore petg pla",
       supersedes=["gazebo-r21-rod-base-petg.3mf"],
       version="1.0.0",
       pages=[dict(label="Stand the tooth on it, both ways",
                   href="docs/tooth-stand.html")],
       gen=["gen_gazebo.py"], params=[
           dict(key="size", label="sizes", type="checks",
                val="gz_sr,gz_mr,gz_lr",
                choices=[
                    dict(value="gz_sr", label="S, carbon rods",
                         hint="teeth 25\u201355 mm \u2014 rods cut to 22.5"),
                    dict(value="gz_mr", label="M, carbon rods",
                         hint="teeth 50\u201395 mm \u2014 rods cut to 31.5"),
                    dict(value="gz_lr", label="L, carbon rods",
                         hint="teeth 90\u2013150 mm \u2014 rods cut to 36.5")]),
           dict(key="material", label="filament", type="select",
                val="petg",
                hint="Choose the filament \u2014 the socket is drawn to it. "
                     "A \u00d81 mm bore comes out about half a millimeter "
                     "under its drawn size, and how much it loses is a "
                     "property of the plastic, not of the part. One tenth "
                     "either way is the difference between refusing the "
                     "rod and letting it fall out.",
                choices=[
                    dict(value="petg", label="PETG Basic",
                         hint="sockets drawn \u00d81.45, measured"),
                    dict(value="pla_basic", label="PLA Basic",
                         hint="sockets drawn \u00d81.5, measured"),
                    dict(value="pla_silk", label="PLA Silk",
                         hint="sockets drawn \u00d81.7, measured")]),
       ],
       out="gazebo-rods-{size}-{material}.3mf"),
    _p("rod_field", "Carbon Rod Field \u2014 56 configurable holes",
       "Stands", "parametric",
       "One part, 56 holes, maximum flexibility for irregular surfaces. "
       "The holes are laid out as concentric rings whose phase turns "
       "with the radius, which offers 14 exact rectangles and five "
       "circles to nest a specimen on \u2014 plant rods where that "
       "particular root wants them and leave the rest empty. "
       "A golden-angle spiral was the first idea for the field and the "
       "scoring says it is the wrong tool: against every rectangle from "
       "10 x 5 to 51 x 26 mm it misses by 17.2 mm at worst where this "
       "pattern misses by 8.1, because a spiral is built so that nothing "
       "ever lines up and a centered rectangle is nothing but lining up. "
       "CHOOSE THE FILAMENT, because the socket is drawn to it \u2014 and "
       "on this part the number came the hard way. A bore this small "
       "prints well under its drawn size, and a crowded field takes off "
       "0.10 to 0.15 mm MORE than a sparse test strip does: 56 bores at "
       "3.58 mm centers in a \u00d859 disc simply come out smaller than 14 "
       "bores at 5 mm in a narrow bar, at the same drawn size, the same "
       "7 mm depth and a toolpath the slicer draws the same to a "
       "hundredth. A probe read \u00d81.45 for PETG; this field wants "
       "\u00d81.56 read ring by ring on a graded field \u2014 and \u00d81.60 "
       "in the end, because printed as a whole field a few bores were "
       "still stiff with no pattern to which ones, so the spread between "
       "one bore and its neighbor is wider than five rings could "
       "resolve. The toolpath is not the cause: measured off the "
       "G-code, no infill of any kind comes within 0.8 mm of a bore "
       "wall, and every one of the 56 has the same two wall loops at "
       "the same distance. The rods are glued, so the step costs "
       "nothing. Two plates drawn to the probe's number took no rod at "
       "all. The "
       "two PLAs carry the same offset over their own probe readings and "
       "are marked as inferred, not measured \u2014 print the graded "
       "field on the spool before trusting them.",
       keys="stand tooth fossil carbon rod socket bore field grid petg pla",
       version="1.1.0",
       pages=[dict(label="Stand the tooth on it, both ways",
                   href="docs/tooth-stand.html")],
       gen=["gen_gazebo.py", "--size", "gz_rf"], params=[
           dict(key="material", label="filament", type="select",
                val="petg",
                hint="Choose the filament \u2014 the socket is drawn to "
                     "it, and for this part the size was read on a "
                     "graded field rather than reasoned from a probe. "
                     "Only PETG has been graded so far.",
                choices=[
                    dict(value="petg", label="PETG Basic",
                         hint="\u00d81.60, graded then opened a step"),
                    dict(value="pla_basic", label="PLA Basic",
                         hint="\u00d81.65, inferred \u2014 not yet graded"),
                    dict(value="pla_silk", label="PLA Silk",
                         hint="\u00d81.85, inferred \u2014 not yet graded")])],
       out="gazebo-rod-field-{material}.3mf"),
    _p("rod_field_graded", "Rod field \u2014 graded, to find the size",
       "Stands", "parametric",
       "The rod field with its five rings stepped in bore, because the "
       "field is the only coupon that is honestly the field. A probe "
       "answered \u00d81.45 for PETG and the field refused a rod at that "
       "size; redrawn 25 microns larger it refused again, with a "
       "toolpath the slicer leaves wider than the probe bore that works. "
       "Same plate thickness, same 7 mm depth, same filament, same "
       "profile \u2014 so whatever closes these holes is not the drawn "
       "size on its own, and no strip of test bores 3 mm apart is going "
       "to say what it is. "
       "Five rings, \u00d81.50 at the center stepping to \u00d82.10 at "
       "the rim, each size etched beside one of its own holes. Work "
       "outward and the first ring that takes a rod is the number to "
       "draw for that filament. The span is deliberately coarse: it "
       "reaches from a whisker above the size that failed to nearly two "
       "thirds of a millimeter above it, and if even the outer ring is "
       "shut then the answer is not a size at all. "
       "Reprint it whenever the spool changes, the same way the gauge is "
       "reprinted \u2014 and the plate is not wasted afterward, since "
       "every ring that takes a rod is a working field of its own.",
       keys="gauge calibration bore socket fit rod carbon field graded "
            "test coupon petg pla",
       version="1.0.0",
       gen=["gen_gazebo.py", "--size", "gz_rfg"], params=[
           dict(key="grade", label="ladder", type="select",
                val="1.53,1.56,1.59,1.62,1.65",
                hint="Coarse first, to find out roughly where the answer "
                     "is; then fine, inside whatever the coarse one "
                     "bracketed. The fine ladder here ends on \u00d81.65 "
                     "on purpose \u2014 a size already read in the hand, "
                     "so the plate carries its own reference.",
                choices=[
                    dict(value="1.53,1.56,1.59,1.62,1.65",
                         label="fine, 1.53\u20131.65",
                         hint="PETG: \u00d81.50 refused, \u00d81.65 loose"),
                    dict(value="1.50,1.65,1.80,1.95,2.10",
                         label="coarse, 1.50\u20132.10",
                         hint="start here on a filament never read")]),
           dict(key="material", label="filament", type="select",
                val="petg",
                hint="Only the funnel and the wall follow the filament "
                     "here \u2014 the five bores are fixed, because "
                     "finding what they should be is the whole point of "
                     "the plate.",
                choices=[
                    dict(value="petg", label="PETG Basic"),
                    dict(value="pla_basic", label="PLA Basic"),
                    dict(value="pla_silk", label="PLA Silk")])],
       out="rod-field-graded-{material}-{grade}.3mf"),
    _p("rod_gauge", "Rod socket gauge",
       "Designed here", "parametric",
       "A ladder of sockets to read a number off, because two guesses "
       "cannot find a constant. Eleven bores from \u00d81.0 to \u00d82.0 "
       "in tenths, twice: one row bored up a slim boss and one straight "
       "into a solid plate, since those are the two sockets the tooth "
       "stands use and there is no reason to assume they close by the "
       "same amount, and a third row repeats the ladder with each bore "
       "flanked by two more at the rod field\u2019s own spacing. A 5 x 5 "
       "patch of \u00d81.5 bores at that spacing closes it out: the field "
       "is the case still unexplained, since its holes sit in a solid "
       "plate with material to spare and still would not take a rod in "
       "PETG where the same size up a boss would. Either that is the "
       "material or it is the crowding, and these rows separate them. "
       "Every bore is a real socket \u2014 same boss, same "
       "depth, same lead-in \u2014 so the rod itself reads the answer "
       "rather than a caliper reading a preview. Push the rod along a "
       "row from the narrow end: the first bore that takes it without "
       "force is the size to draw from then on, for that printer, that "
       "filament and that nozzle. The wedge and the etched sizes say "
       "which end is which. The ladder starts at the rod\u2019s own "
       "diameter on purpose: a bore drawn at \u00d81.0 cannot admit a "
       "1 mm rod after any shrinkage, so the first column is the control "
       "\u2014 and starting above it, which the first version did, would "
       "have reported the lowest size on the ladder as the answer "
       "without ever showing what lay beneath it. It has now been read in three "
       "filaments on a 0.4 nozzle, and they do not agree: \u00d81.45 in "
       "PETG Basic, \u00d81.5 in PLA Basic, \u00d81.7 in PLA Silk. In "
       "PLA Basic, \u00d81.4 refuses the rod and \u00d81.6 lets it drop "
       "through, so a tenth either side of the answer is the whole "
       "usable range. The bore comes out about half a millimeter "
       "under its drawn size, where a \u00d83 hole on the same printer "
       "loses only 0.15 \u2014 the error is roughly constant in "
       "millimeters, so it is ruinous at this scale and negligible at "
       "six. Below \u00d81.2 drawn a bore stops holding a round shape at "
       "all, which is the floor for any socket.",
       keys="gauge calibration bore socket fit rod carbon test coupon",
       version="1.0.0",
       gen=["gen_gazebo.py", "--size", "gz_gauge"],
       out="rod-socket-gauge.3mf"),
    _p("rod_probe", "Rod bore probe",
       "Designed here", "parametric",
       "The gauge cut down to one question, for when the filament "
       "changes and nothing else has. Fourteen bores in half-tenths from "
       "\u00d81.35 to \u00d82.0, straight into a plate at the rod "
       "field\u2019s own thickness and depth, labeled every tenth. It is "
       "75 x 16 mm and prints in a quarter of an hour, which is the "
       "point: the bore a 1 mm carbon rod wants is a property of the "
       "filament and not of the part, and two PLAs measured 0.2 mm "
       "apart. Read it with the rod, then draw sockets to what it says.",
       keys="gauge calibration bore socket fit rod carbon test coupon",
       version="1.0.0",
       gen=["gen_gazebo.py", "--size", "gz_probe"],
       out="rod-bore-probe.3mf"),
    
    _p("trex_teeth", "Skeleton T-Rex \u2014 real teeth", "Flexi Factory",
       # A FROZEN FILE, not a generator run. This card used to build on every
       # order, and the build and the bench drifted apart: the generator's
       # command-line defaults were the SKULL's numbers and went through on
       # every run, so the jaw came out cut with the skull's settings while
       # the bench showed the settled one. Two different parts from one word,
       # "default". The geometry here is the one that was measured and
       # approved; `make trex` rewrites it when the design actually changes.
       "library",
       "Flexi Factory\u2019s skeleton T-Rex with its printed teeth replaced "
       "by sockets you can set real shark teeth in and bed in black epoxy. "
       "Each socket is a cone that starts at the designer\u2019s own painted "
       "tooth outline and narrows with depth, and behind them runs one open "
       "channel that joins every socket together. A real root \u2014 even "
       "clipped \u2014 does not fit a hole sized to the crown, so the "
       "channel is where it goes and where the epoxy keys in. The lip you "
       "see from outside is left exactly as the designer drew it: the cut is "
       "bounded on the cheek side and nowhere else, so a tooth reads as "
       "inset in the jaw while the tongue side opens straight into the "
       "mouth. Which triangles were teeth is not a guess \u2014 the designer "
       "painted them and the paint ships in the 3MF, one attribute per "
       "triangle, so every tooth comes off complete down to the ring where "
       "it meets the jaw. The feet keep their talons on purpose: they are "
       "what the model stands on.",
       keys="tooth teeth fossil skeleton",
       version="5.0.0",
       path=os.path.join(os.path.dirname(HERE), "models", "custom",
                         "trex-real-teeth-v5.3mf"),
       proven="Skull and lower jaw on one plate, 2h52m and 58.5 g, no "
              "support, no brim, no slicer warning. Both watertight; the "
              "skull\u2019s genus matches the untouched model, which is the "
              "only test that catches a socket leaving through a side wall "
              "\u2014 a tunnel through a solid keeps it closed, so "
              "watertightness cannot see one. The 4.x ledge printed in PLA "
              "Black and the mounting area was right, but it held a "
              "tooth\u2019s crown and not its root; that is what this "
              "changes. Plain PLA, not silk: silk has failed twice here on "
              "thin sections and the labial lip is one.",
       settings="skull: socket 3.5, lingual 1.0, trough 3.0, lip 1.2 \u2014 "
                "jaw: socket 2.5, lingual 2.5, trough 2.75, lip 0.6 \u2014 "
                "both at socket wall 0.35, square to the jaw, no deburr"),
    _p("binary_rings", "Zoo Talker Code Disks", "Designed here", "parametric",
       "A set of coded disks for use with the Zoo Talkers Animal Sounds "
       "Zoo, which reads concentric rings as bits. "
       "The reader has five plungers, each at its own radius so the code "
       "reads at any rotation, and one of them sits on the axis \u2014 so "
       "the coding is five positions inside \u00d827.88: a \u00d84.75 disk "
       "at the center and four rings around it. That is 2^5 = 32 "
       "combinations, but the one with nothing standing gives the reader no "
       "bit to find and stays silent \u2014 so the set is 31 disks, 1 to 31. "
       "Bit 1 is the center and bit 5 the outermost "
       "ring, worth 1, 2, 4, 8 and 16, so an odd code stands its center up "
       "and an even one sinks a pocket there. The \u00d833.3 lip outside "
       "them carries no code: it "
       "is what presses the switch that starts a read, which the toy takes "
       "at any rotation. Outside the lip a flat land 2.85 wide takes the "
       "disk to \u00d839 \u2014 the face the toy meets, and the stop that "
       "keeps the plug from going in further than the switch travels. On a "
       "real accessory that flat is the body the coded disk is set into; "
       "printed on its own it has to carry its own. Every other dimension "
       "is measured off the toy and fixed here, because the plug only works "
       "in that one socket. Ask for one code or any set of them \u2014 7, "
       "or 1-31, or 1,2,4,8,16 \u2014 and a set arrives on one plate, each "
       "disk with its own number engraved underneath so they stay told "
       "apart in a drawer. Every surface is a vertical extrusion off a flat "
       "base \u2014 the land is a step down from the lip, not a brim over "
       "air \u2014 so it prints face-down with no supports. Printed, it "
       "seats and reads. It also bound on the reader going on and wanted a "
       "firm press to talk, so the cavity is built 0.10 wider across than "
       "drawn \u2014 the wall where bit 5 ends is the only surface the "
       "reader touches \u2014 and the raised features stand at the tall end "
       "of what the measurements allow.",
       # 1.1.0: rim 11.66 -> 11.55 (mean of three readings on rubber) and
       #        relief 3.46 -> 3.35, which follows it through the 8.20
       # 1.2.0: band widths became a dial -- the measurements fix their sum
       #        and one boundary, not the split, so the default is a choice
       # 2.0.0: the outermost band is the flange, not a bit. Every code
       #        addresses different geometry than it did, hence the major.
       # 2.1.0: the code is an engraved numeral underneath, replacing the
       #        row of pips -- thirty-two of these look alike in a drawer
       # 2.1.1: a width override that does not sum back to the measured
       #        inner diameter now says so instead of moving it quietly
       # 3.0.0: the code is the only dial. Heights and band widths were
       #        cast from one socket, and a slider on them offers a plug
       #        that fits nothing; the set card folded in here as 0-31.
       # 3.1.0: the generator can build the activation lip -- the second
       #        wall that presses the switch outside the bore. Minor, not
       #        major: with its numbers unmeasured the lip is not built,
       #        and every code comes out the shape it came out before.
       # 4.0.0: the lip is the switch, and the flat land around it is what
       #        the toy's face meets. Ø33.3 -> Ø39 and 6.9 -> 11.8 g: every
       #        code is a different object than it was, and the disks
       #        printed before this are the plug without its outer face.
       # 4.1.0: relief 3.35 -> 3.77. The nub and the bit rings read 7.78
       #        below the rim together, and the nub reads 3.74 off the bore
       #        floor: two readings 0.03 apart, replacing a single 8.20.
       # 5.0.0: the center is a bit, not a permanent nub. The reader has
       #        five plungers, one of them on the axis, and the animals
       #        vary there -- tiger stands a boss, seal sinks a pocket. So
       #        the field is a disk and four rings, not a nub and five
       #        rings, and every code number addresses new geometry.
       # 5.1.0: the first print talked. It needed pressing, so the rim goes
       #        to the largest reading (11.75, not the mean 11.55) and the
       #        relief follows it to 3.97 through the same 7.78 drop -- both
       #        inside what the readings bracket. And it bound going on, so
       #        the cavity is built 0.10 wider across: the disk is a hollow
       #        cylinder that goes over the reader, and the wall where bit 5
       #        ends is the only surface that touches it. The outside of the
       #        lip plays no part and did not move.
       # 5.2.0: 5.1.0 put that clearance on the outside of the lip, which
       #        the reader never touches, so it bought nothing. It moves to
       #        the cavity wall, and the number is measured across the hole
       #        rather than on the radius -- the way the hole is measured
       #        and the way the fault was reported.
       # 6.0.0, not 5.3.0: every band boundary moved. The bands were
       # regridded onto the reader's five plunger radii (midpoints between
       # them, so no boundary lands on a switch) and the outermost 1.75 mm
       # became a seat for the reader's raised rim rather than code. A disk
       # from 5.x and a disk from 6.x are not the same design, and the old
       # ones are superseded rather than merely older -- codes 16-31 built
       # under 5.x filled the rim's seat and the toy stayed silent.
       # 6.0.2: thirty of the thirty-one codes now carry the animal they
       #        say, read off a video of the whole set. The disk itself is
       #        unchanged -- this is what the card knows, not what it
       #        builds. Two names read earlier off a ten-disk plate were
       #        wrong and are corrected: 14 is kangaroo, 24 is zebra.
       version="6.0.2",
       proven="Thirty-one disks printed and heard. Ten in PLA Black first, "
              "and the toy agreed: code 16 built at three rim-seat widths, "
              "silent at 1.25 and speaking at 2.25 and at the shipped 1.75, "
              "which brackets the reader\u2019s rim and pins the seat as the "
              "thing that gates a read. Code 31 wants a firmer press \u2014 "
              "that is five plunger springs summed, not a bit standing "
              "short. Every code but 6 has since named its animal.",
       gen=["gen_binary_rings.py"], params=[
           dict(key="codes", label="codes", type="codes", val="10",
                lo=1, hi=31, animals=_zoo_animals(),
                hint="tap the codes you want \u2014 31 in the set",
                howto="docs/zoo-codes.html",
                howto_text="How the mapping was read")],
       # Brimless, flat-bottomed and vertical-walled, so 2 mm between them
       # is ample -- and it is what puts all thirty-two ø39 disks on one
       # plate instead of two. The generator lays its own set out on the
       # same 2 mm, so the file and the packed order agree.
       gap=2.0,
       out="binary-ring-{codes}.3mf"),
]
BY_ID = {p["id"]: p for p in PARTS}
_LIB_INDEX = {}


EXPERIMENTAL = os.path.join(MODELS, "experimental")


def experimental(limit=200):
    """Plates kept as numbered iterations, from models/experimental.

    A design under development throws off a plate every time something
    changes, and the question a week later is always "which one was
    that". These are named for it:

        <design>-r<n>-<what changed>.3mf

    They resolve exactly like a library file -- the shop views them and
    hands the path to the slicer -- so nothing downstream needs to know
    they are different.
    """
    import datetime
    import hashlib as _h
    out = []
    if not os.path.isdir(EXPERIMENTAL):
        return out
    skip = superseded()
    for fn in sorted(os.listdir(EXPERIMENTAL)):
        if not fn.lower().endswith((".3mf", ".stl")):
            continue
        # A plate a card can rebuild exactly is not a second design. These
        # stay on disk -- they are what went to the slicer -- but the card
        # is where you ask for them, with every size on by default and the
        # ones you do not want switched off before it goes to the plate.
        if fn.lower() in skip:
            continue
        path = os.path.join(EXPERIMENTAL, fn)
        try:
            st = os.stat(path)
        except OSError:
            continue
        stem = os.path.splitext(fn)[0]
        m = re.match(r"(.+?)-r(\d+)-(.+)$", stem)
        if m:
            design, rev, what = m.group(1), int(m.group(2)), m.group(3)
            name = (design.replace("-", " ") + " r" + str(rev) + " \u2014 "
                    + what.replace("-", " "))
            ver = "0.0." + str(rev)
        else:
            design, rev, name, ver = stem, 0, stem.replace("-", " "), "\u2014"
        day = datetime.date.fromtimestamp(st.st_mtime).isoformat()
        out.append(_p("exp_" + _h.md5(path.encode()).hexdigest()[:10],
                      name, "Experimental", "library",
                      "An iteration of " + design.replace("-", " ")
                      + ", kept as it was printed.",
                      version=ver, path=path, size=st.st_size,
                      changed=day, built=day, iteration=rev, design=design))
        if len(out) >= limit:
            break
    return out


def _lib_stamp():
    """What the library is built from: the shelf and the import list."""
    out = []
    for f in (IMPORTED,):
        try:
            st = os.stat(f)
            out.append((f, st.st_size, int(st.st_mtime)))
        except OSError:
            out.append((f, None, None))
    for d in (MODELS, EXPERIMENTAL):
        try:
            out.append((d, int(os.stat(d).st_mtime)))
        except OSError:
            pass
    return tuple(out)


def find(part_id):
    """Resolve any catalog id — generated, parametric or library.

    The library index is rebuilt when the shelf or the import list changes.
    Held for the life of the process instead, a file imported a moment ago
    is not findable until the server restarts.
    """
    if part_id in BY_ID:
        return BY_ID[part_id]
    stamp = _lib_stamp()
    if _LIB_INDEX.get("__stamp__") != stamp or part_id not in _LIB_INDEX:
        _LIB_INDEX.clear()
        _LIB_INDEX["__stamp__"] = stamp
        _LIB_INDEX.update({p["id"]: p for p in library() + experimental()})
    if part_id in _LIB_INDEX and part_id != "__stamp__":
        return _LIB_INDEX[part_id]
    raise KeyError(part_id)


def _fmt(v):
    """A parameter value as a fragment of a filename.

    A number formats itself. A string is whatever was typed into a box --
    a code spec arrives as "1,2,4,8,16" -- so it is reduced to letters,
    digits and dashes, and a long one is replaced by a short digest of
    itself rather than a filename nobody can read or a path nobody can
    open.
    """
    if isinstance(v, (int, float)):
        return f"{v:g}"
    t = re.sub(r"[^A-Za-z0-9-]+", "_", str(v)).strip("_")
    if len(t) > 32:
        t = t[:24] + "-" + hashlib.sha1(str(v).encode()).hexdigest()[:6]
    return t or "none"


_GIT = {}


def _git_last(path):
    """(iso date, subject) of the last commit to touch a file."""
    if path in _GIT:
        return _GIT[path]
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%cI\x1f%s", "--",
                            path], cwd=ROOT, capture_output=True, text=True,
                           timeout=10)
        date, _, note = r.stdout.strip().partition("\x1f")
    except Exception:
        date, note = "", ""
    if not date:
        try:
            import datetime
            date = datetime.datetime.fromtimestamp(
                os.path.getmtime(path)).isoformat()
            note = "uncommitted"
        except OSError:
            date, note = "", ""
    _GIT[path] = (date[:10], note[:90])
    return _GIT[path]


def provenance(part):
    if part["kind"] == "library":
        return dict(version=part.get("version", "—"),
                    changed=part.get("changed", ""), note="on disk",
                    built=part.get("built", ""))
    """What this design is, when it last changed, and when it was built.

    The version is the author's; the date comes from the last commit that
    touched the generator, so a design cannot claim to be current while its
    source has moved on.
    """
    src = os.path.join(HERE, part["gen"][0]) if part.get("gen") else ""
    changed, note = _git_last(src) if src else ("", "")
    built = ""
    try:
        p = out_path(part)
        if os.path.exists(p):
            import datetime
            built = datetime.datetime.fromtimestamp(
                os.path.getmtime(p)).strftime("%Y-%m-%d")
    except Exception:
        pass
    return dict(version=part.get("version", "0.1.0"), changed=changed,
                note=note, built=built)


def defaults(part):
    """Every dial a part needs to build, at its default value.

    A part in a kit gets some of its dials from the kit, so that the parts
    of a set always fit each other. Asking a part for its own params alone
    leaves those out and the generator refuses for want of a size.
    """
    vals = {}
    for k in KITS:
        if any(m["part"] == part["id"] for m in k["members"]):
            for d in k.get("shared", []):
                vals[d["key"]] = d["val"]
            for m in k["members"]:
                if m["part"] == part["id"]:
                    for d in (m.get("own") or []):
                        vals[d["key"]] = d["val"]
    for d in (part.get("params") or []):
        vals[d["key"]] = d["val"]
    return vals


def stale(part, path):
    """Was this file built before the code that builds it?

    Without this a cached 3MF is served forever: a generator can be fixed
    and every order still gets the old geometry, while the shop's own badge
    says the part rebuilds when ordered. The badge was telling the truth
    about the intent and not about the behavior.
    """
    if not os.path.exists(path):
        return True
    built = os.path.getmtime(path)
    srcs = [os.path.join(HERE, g) for g in (part.get("gen") or [])[:1]]
    srcs.append(os.path.join(HERE, "embed_settings.py"))
    # AND WHAT THE GENERATOR IMPORTS. Watching only the named script meant a
    # part could be rebuilt from a cutter that had changed underneath it and
    # nobody would know: gen_trex.py barely moved all day while channel.py
    # was rewritten around it, so every order served a cached 3MF while the
    # badge said it was made to order. One level of local imports is enough
    # to catch that, and it costs a stat per module.
    srcs += _local_imports(srcs[0]) if srcs else []
    return any(os.path.exists(f) and os.path.getmtime(f) > built
               for f in srcs)


def _local_imports(script, _cache={}):
    """Modules this script imports that live beside it."""
    if script in _cache: return _cache[script]
    out = []
    try:
        import ast
        tree = ast.parse(open(script).read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names.add(node.module.split(".")[0])
        for n in sorted(names):
            f = os.path.join(HERE, n + ".py")
            if os.path.exists(f): out.append(f)
    except Exception:                                       # noqa: BLE001
        pass
    _cache[script] = out
    return out


def out_path(part, params=None):
    """Where this part's 3MF lives, given its parameters.

    A name ending in .3mf is literal. Anything else is a stem, and the
    supplied parameters make the suffix — so a part whose defaults are
    derived (the sphere stand computes base, wall and chamfer from the ball)
    keys its file on what was actually asked for, not on a fixed template.
    """
    name, params = part["out"], params or {}
    if not name.endswith(".3mf"):
        sfx = "-".join(f"{k}{_fmt(v)}" for k, v in sorted(params.items()))
        name = f"{name}-{sfx}.3mf" if sfx else f"{name}.3mf"
    elif "{" in name:
        # Fill anything the caller left out from the part's own defaults. A
        # dial added to a design should not break every order that predates
        # it, and provenance asks for the path with no parameters at all.
        full = dict(defaults(part))
        full.update(params)
        # numbers keep their format spec ({dia:g}); anything typed is a
        # filename fragment before it reaches format()
        full = {k: (_fmt(v) if isinstance(v, str) else v)
                for k, v in full.items()}
        name = name.format(**full)
    return os.path.join(CUSTOM, name)


def ensure(part, params=None, timeout=600):
    """Generate the part's file if it is not on disk, or is out of date.

    Returns (path, report). Raises RuntimeError with the generator's own
    message when a design gate refuses the parameters.
    """
    if part["kind"] == "library":
        return part["path"], {"cached": True, "library": True}
    path = out_path(part, params)
    if not stale(part, path):
        return path, {"cached": True}
    cmd = [PY, os.path.join(HERE, part["gen"][0])] + part["gen"][1:]
    for k, v in (params or {}).items():
        cmd += [f"--{k}", str(v)]
    cmd += ["--out", path]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    try:
        rep = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        raise RuntimeError((r.stderr or "generator failed")[-300:])
    if not rep.get("ok"):
        raise RuntimeError(rep.get("error", "generation refused"))
    return path, rep


def measure(path):
    """Footprint and height of a 3MF, in mm — what the packer needs."""
    import trimesh
    sc = trimesh.load(path, force="scene")
    lo, hi = sc.bounds
    return dict(w=float(hi[0] - lo[0]), d=float(hi[1] - lo[1]),
                h=float(hi[2] - lo[2]))


IMPORTED = os.path.join(MODELS, "imported.json")
DOWNLOADS = os.path.expanduser("~/Downloads")


def imported():
    """Files the user has explicitly imported, still present on disk."""
    if not os.path.exists(IMPORTED):
        return []
    try:
        with open(IMPORTED) as f:
            paths = json.load(f)
    except ValueError:
        return []
    return [p for p in paths if os.path.isfile(p)]


def scan(dirs=None):
    """Candidates for import. Looks; does not remember."""
    return library(dirs or [DOWNLOADS], include_imported=False)


def import_from(dirs=None, paths=None):
    """Take what a scan found into the catalog, and write that down.

    The shop used to walk ~/Downloads on every read, which made anything
    that landed there a design — including the plates it had just exported.
    Importing is a thing the user does now, not a thing that happens to
    them.

    `paths` imports exactly those files instead of everything a scan finds.
    A download of one model arrives beside a year of other downloads, and
    taking the whole folder to get four files puts a hundred and forty
    cards on a shelf to gain six.
    """
    have = set(imported())
    if paths is not None:
        found = {os.path.abspath(os.path.expanduser(p)) for p in paths}
        missing = [p for p in found if not os.path.isfile(p)]
        if missing:
            raise FileNotFoundError(missing[0])
    else:
        found = {p["path"] for p in scan(dirs)}
    keep = sorted(have | found)
    os.makedirs(os.path.dirname(IMPORTED), exist_ok=True)
    with open(IMPORTED, "w") as f:
        json.dump(keep, f, indent=1)
    return dict(added=len(found - have), total=len(keep),
                already=len(found & have))


def forget_imports():
    """Drop every import. The models/ shelf is untouched."""
    if os.path.exists(IMPORTED):
        os.remove(IMPORTED)


def superseded():
    """Shelf files a parametric card already covers. They stay on disk --
    they are what was printed -- but a design is one card."""
    out = set()
    for p in PARTS:
        for f in p.get("supersedes") or []:
            out.add(f.lower())
    return out


def library(dirs=None, limit=400, include_imported=True):
    """Printable files on disk, as catalog parts.

    Same shape as a generated part, so nothing downstream — the shop rows,
    the bill of materials, the packer, the exporter — needs to know which
    kind it is holding. The only difference is that ensure() has nothing to
    generate.

    Only models/ is read automatically: that shelf is this project's own.
    Anything else is here because it was imported on purpose.
    """
    dirs = list(dirs) if dirs else [MODELS]
    files_only = []
    if include_imported and dirs == [MODELS]:
        files_only = imported()
    skip = superseded()
    seen, out = {}, []
    walks = [(d, None) for d in dirs] + [(None, f) for f in files_only]
    for d, one in walks:
        if one is not None:
            root, files = os.path.dirname(one), [os.path.basename(one)]
            trees = [(root, files)]
        elif os.path.isdir(d):
            trees = [(r, fs) for r, _, fs in os.walk(d)]
        else:
            continue
        for root, files in trees:
            if "/glb" in root or "/meta" in root or "/index_out" in root:
                continue
            if "/custom" in root:
                continue        # the generators' own output: already a part,
                                # and listing it again puts the same design
                                # in the catalog twice under two names
            if "/failed" in root:
                continue        # plates that did not work. Kept for the
                                # record, never orderable: a known-bad
                                # plate sitting in the shop next to the
                                # fixed one is how the bad one gets
                                # printed a second time
            if "/experimental" in root:
                continue        # same reason: experimental() already names
                                # these, and the walk was listing every one
                                # of them a second time under its raw file
                                # name -- one plate, two cards, one of them
                                # reading "gazebo-r21-spiked-stands-pla"
            if "print-shop-order" in root:
                continue        # a plate this shop exported, downloaded and
                                # then found again — an order is not a design
            for fn in sorted(files):
                low = fn.lower()
                if not low.endswith((".3mf", ".stl")):
                    continue
                if low.endswith(".gcode.3mf"):
                    continue        # a sliced export, not a model to print
                if re.match(r"plate_\d\d[_.]", low):
                    continue        # our own plate naming, downloaded back
                p = os.path.join(root, fn)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                # A design kept in both models/ and Downloads is one design,
                # even when the two copies differ in size because one was
                # re-saved — that pair was showing up as two catalog entries
                # for the same object. Two files that merely share a generic
                # name in unrelated project folders are not folded: "00
                # start.3mf" means something different in each of them.
                if fn.lower() in skip:
                    continue
                key = low
                prev = seen.get(key)
                same_design = prev is not None and (
                    (prev["path"].startswith(MODELS)) !=
                    (p.startswith(MODELS)))
                if same_design:
                    prev["copies"] = prev.get("copies", 1) + 1
                    prev.setdefault("also", []).append(p)
                    continue
                if prev is not None and prev["size"] == st.st_size:
                    continue                     # the very same file, twice
                import datetime
                entry = _p(
                    "lib_" + hashlib.md5(p.encode()).hexdigest()[:10],
                    os.path.splitext(fn)[0].replace("+", " ").replace("_", " "),
                    "Downloads" if "Downloads" in root else "Models",
                    "library", "",
                    version="—", path=p, size=st.st_size,
                    changed=datetime.date.fromtimestamp(
                        st.st_mtime).isoformat(),
                    built=datetime.date.fromtimestamp(
                        st.st_mtime).isoformat())
                seen.setdefault(key, entry)
                out.append(entry)
                if len(out) >= limit:
                    return out
    return out


def _tag(stamp):
    """A short, URL-safe version tag for a preview's source stamp."""
    if not stamp:
        return ""
    return hashlib.md5(str(stamp).encode()).hexdigest()[:8]


def previews():
    """id -> preview record, built by previews.py. Empty is not an error."""
    f = os.path.join(MODELS, "previews.json")
    if not os.path.exists(f):
        return {}
    try:
        with open(f) as fh:
            return {e["id"]: e for e in json.load(fh)}
    except (ValueError, KeyError):
        return {}


def enrich(part, prev):
    """Give every entry the fields a card needs, whoever made it.

    A generated part knows its own story; a file scanned off disk knows
    only its name. Where a human has written about that file, its curation
    is folded in here — so one card template renders either, and the shop
    and the design write-up can no longer disagree about what a part is.
    """
    import designs
    out = dict(part)
    pv = prev.get(part["id"])
    if pv:
        # the stamp rides in the URL: a rebuilt preview is a new address, so
        # the browser cannot keep showing the geometry it cached earlier
        tag = _tag(pv.get("stamp"))
        # The measurements always come from here; a GLB only exists for the
        # composites now, since a part is read from its own 3MF or STL.
        if pv.get("glb"):
            out["preview"] = pv["glb"] + (f"?v={tag}" if tag else "")
        out.update(dims3=pv["dims"], bodies=pv["bodies"],
                   tris=pv["tris_full"])
        if pv.get("printability"):
            out["printability"] = pv["printability"]
        d = pv["dims"]
        out["dims"] = f"{d[0]} x {d[1]} x {d[2]} mm"
    cur = designs.curation(os.path.basename(part.get("path", "")))
    if cur:
        out.update(name=cur["title"], family=cur["family"],
                   designer=cur["designer"], material=cur["mat"],
                   verdict=list(cur["v"]), card=cur["cid"])
        if cur.get("proven"):
            out["proven"] = cur["proven"]
        if not out.get("blurb"):
            out["blurb"] = cur["blurb"]
        sl = designs.SLICE.get(cur["cid"])
        if sl:
            out["slice"] = sl
    m = _meta(part.get("path", ""))
    if m:
        out["meta"] = m
    return out


def _meta(path):
    """The designer's own metadata, extracted from the 3MF alongside it."""
    if not path:
        return None
    slug = re.sub(r"[^a-z0-9]+", "_",
                  os.path.basename(path).lower().rsplit(".", 1)[0]).strip("_")
    f = os.path.join(MODELS, "meta", slug, "meta.json")
    if not os.path.exists(f):
        return None
    try:
        with open(f) as fh:
            md = json.load(fh)
    except ValueError:
        return None
    keep = {k: md[k] for k in ("Designer", "License", "Origin", "Application",
                               "CreationDate", "Description") if md.get(k)}
    if md.get("photos"):
        keep["photos"] = [f"models/meta/{slug}/{x}" for x in md["photos"]]
    if md.get("cover"):
        keep["cover"] = f"models/meta/{slug}/{md['cover']}"
    return keep or None


# --- sets: parts from separate files that are one toy ---------------------
# An hourglass is a body and the spiral that screws through it. They ship as
# separate files because they print separately, and the catalog showed them
# as separate designs — thirteen cards for four toys, with nothing saying
# which spiral goes through which body. Declared by filename so the grouping
# survives re-indexing, since a library id is derived from a path.
SETS = [
    dict(id="hourglass_cone_90", version="1.0.0",
         name="Hourglass — cone, 90 mm", family="Hourglass · Cone",
         blurb="A cone body and the spiral that threads through it. The "
               "spiral screws down under its own weight; the eased cut has "
               "a 0.05-0.15 mm lead-in so it starts without being forced.",
         files=[("cone-solid-small.stl", "Body", "part"),
                ("cone-spiral-small.stl", "Spiral", "part"),
                ("cone-spiral-small-eased.stl", "Spiral — eased lead-in", "alt"),
                ("cone-hourglass-pair-small.3mf", "Both, on one plate", "alt")]),
    dict(id="hourglass_cone_180", version="1.0.0",
         name="Hourglass — cone, dubbel 180 mm", family="Hourglass · Cone",
         blurb="The same pair at double height. Twice the lever on the same "
               "footprint, so it wants a brim and a slow outer wall.",
         files=[("cone-solid.stl", "Body", "part"),
                ("cone-spiral.stl", "Spiral", "part"),
                ("cone-spiral-eased.stl", "Spiral — eased lead-in", "alt"),
                ("cone-hourglass-pair-dubbel.3mf", "Both, on one plate", "alt")]),
    dict(id="hourglass_pyramid_90", version="1.0.0",
         name="Hourglass — pyramid, 90 mm", family="Hourglass · Pyramid",
         blurb="The pyramid cut of the same mechanism. The original body "
               "carries the duplicate-face defect; the fixed one is the "
               "copy to print.",
         files=[("pyramid-solid-small-fixed.stl", "Body — fixed", "part"),
                ("pyramid-spiral-small.stl", "Spiral", "part"),
                ("pyramid-solid-small.stl",
                 "Body — original, has the defect", "alt"),
                ("pyramid-spiral-small-eased.stl",
                 "Spiral — eased lead-in", "alt"),
                ("pyramid-hourglass-pair-small.3mf",
                 "Both, on one plate", "alt")]),
    dict(id="hourglass_pyramid_180", version="1.0.0",
         name="Hourglass — pyramid, dubbel 180 mm",
         family="Hourglass · Pyramid",
         blurb="The pyramid pair at double height.",
         files=[("pyramid-solid.stl", "Body", "part"),
                ("pyramid-spiral.stl", "Spiral", "part"),
                ("pyramid-spiral-eased.stl", "Spiral — eased lead-in", "alt"),
                ("pyramid-hourglass-pair-dubbel.3mf",
                 "Both, on one plate", "alt")]),
]


def sets(parts):
    """SETS resolved against what is actually on the shelf.

    A set whose files are missing is dropped rather than shown with holes.
    """
    by_file = {}
    for p in parts:
        f = os.path.basename(p.get("path", ""))
        if f:
            by_file.setdefault(f, p["id"])
    out = []
    for spec in SETS:
        # `role` separates the toy from its alternatives: an hourglass is a
        # body and a spiral, and the eased spiral and the both-on-one-plate
        # file are other ways to get the same two parts. Counting them as
        # members showed five bodies in the preview of a two-part toy.
        mem = [dict(part=by_file[f], label=lab, role=role)
               for f, lab, role in spec["files"] if f in by_file]
        if len(mem) < 2:
            continue
        out.append(dict(id=spec["id"], version=spec["version"],
                        name=spec["name"], family=spec["family"],
                        blurb=spec["blurb"], shared=[], members=mem,
                        parts_n=sum(1 for m in mem if m["role"] == "part")))
    return out


def catalog(with_library=True):
    """One list. A part is a part; some of them have options."""
    entries = (list(PARTS) + experimental()
               + (library() if with_library else []))
    prev = previews()
    parts = [enrich(dict(p, **provenance(p)), prev) for p in entries]
    # Every part carries a semver, including the ones nobody here authored.
    # Reconciled in memory so a read has no side effects; the pipeline
    # (versions.py) is what writes the ledger.
    import versions as _v
    led, faults = _v.reconcile(parts, write=False)
    for p in parts:
        e = led.get(p["id"], {})
        if e.get("version"):
            p["version"] = e["version"]
        p["fingerprint"] = e.get("fingerprint")
        p["revisions"] = e.get("revisions", 0)
        p["first_seen"] = e.get("first_seen", "")
        p["version_source"] = ("declared" if p["kind"] != "library"
                               else "observed")
        # an experimental plate's version IS its iteration number, and the
        # ledger has no business guessing one for it. The SOURCE stays
        # "observed": the number is read off the file's name, which is
        # exactly what observed means for a library entry.
        if p.get("iteration") is not None:
            p["version"] = "0.0." + str(p["iteration"])
    # WHAT ORDERING IT ACTUALLY DOES. The three kinds behave differently
    # and the card never said so: a library file is handed over as its
    # author saved it, a design with no dials is one canonical file that
    # sits on disk between orders, and a design with dials is generated to
    # whatever the dials say. Only the last of those should be running a
    # generator while you wait, so the card is explicit about which it is.
    # Where the REAL geometry is, so the page can read it instead of a GLB
    # built beside it. A library file may sit outside the repo, so this is a
    # route rather than a path.
    for p in parts:
        src = (p.get("path") if p["kind"] == "library"
               else out_path(p, defaults(p)))
        p["src"] = "/src?id=" + p["id"]
        p["ext"] = os.path.splitext(src or "")[1].lower().lstrip(".") or "3mf"

    kit_driven = {m["part"] for k in KITS if k.get("shared")
                  for m in k["members"]}
    for p in parts:
        if p["kind"] == "library":
            p["delivery"] = "file"
        elif p.get("params") or p["id"] in kit_driven:
            p["delivery"] = "dials"
        else:
            f = out_path(p, defaults(p))
            p["delivery"] = ("ready" if os.path.exists(f) and not stale(p, f)
                             else "build")

    # WHICH SHELF a card belongs on, and therefore where it appears. The
    # order used to be whatever the list here happened to be plus whatever
    # order the library scan returned, which put four hourglass plates ahead
    # of every design that has actually been printed. Derived, so a new part
    # lands somewhere sensible without being told; `shelf=` on an entry
    # overrides it.
    for p in parts:
        p["shelf"] = p.get("shelf") or (
            "library" if p["kind"] == "library"
            else "proven" if p.get("proven") else "designed")
    by = {p["id"]: p for p in parts}
    kits = []
    for k in list(KITS) + sets(parts):
        mem = [by[m["part"]] for m in k["members"] if m["part"] in by]
        dates = [p["changed"] for p in mem if p["changed"]]
        builts = [p["built"] for p in mem if p["built"]]
        # a kit is only as built as its least-built member
        kit = dict(k, changed=max(dates) if dates else "",
                   built=min(builts) if len(builts) == len(mem) else "",
                   # a kit sits with the work, on the strength of any member
                   # that has been printed
                   # a kit is dial-driven if it shares any, otherwise it is
                   # as ready as its least-ready member
                   delivery=("dials" if k.get("shared")
                             else "file" if all(m["kind"] == "library" for m in mem)
                             else ("build" if any(m.get("delivery") == "build"
                                                  for m in mem) else "ready")),
                   shelf=k.get("shelf") or
                         ("proven" if any(m.get("proven") for m in mem)
                          else "designed" if any(m["kind"] != "library"
                                                 for m in mem)
                          else "library"))
        pv = prev.get("kit_" + k["id"])
        if pv:
            # the card is for the set, so its preview shows the whole set
            tag = _tag(pv.get("stamp"))
            kit.update(preview=pv["glb"] + (f"?v={tag}" if tag else ""),
                       dims3=pv["dims"], tris=pv["tris_full"],
                       bodies=pv["bodies"])
        kits.append(kit)
    fams = []
    for p in parts:
        if p["family"] not in fams:
            fams.append(p["family"])
    return {"printers": PRINTERS, "printer": DEFAULT_PRINTER,
            "kits": kits, "parts": parts, "families": fams,
            "shelves": SHELVES, "version_faults": faults}


if __name__ == "__main__":
    c = catalog()
    print(json.dumps({"kits": [(k["id"], [m["part"] for m in k["members"]])
                               for k in c["kits"]],
                      "parts": [p["id"] for p in c["parts"]],
                      "library_found": len(library())}, indent=1))
