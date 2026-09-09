#!/usr/bin/env python3
"""The curated designs: what a human knows about a file that a mesh cannot say.

Designer, license-ish attribution, what the thing does, and the verdict from
the geometry review. This used to live inside the page builder, which meant
the shop and the design cards were two descriptions of the same objects that
could drift apart. It is data now, and both read it.

Keyed by the file the design ships as, so a catalog entry scanned off disk
can pick up its curation by matching the filename it already has.
"""

C = []
def add(cid, file, glb, family, designer, mat, title, blurb, v, mate=None,
        hide=False, reveals=None, reveal_label=None, pair=None, proven=None):
    """`proven` is what happened on this printer, not what the page claims.

    A design here can declare it in the catalog; a downloaded file has no
    entry there to declare it in, so it says so through its curation.
    """
    C.append(dict(cid=cid, file=file, glb=glb, family=family, designer=designer,
                  mat=mat, title=title, blurb=blurb, v=v, mate=mate, hide=hide,
                  reveals=reveals, reveal_label=reveal_label, pair=pair,
                  proven=proven))

UNK = "(unattributed export)"
add("sphere1", "sphere_stand_1.0in.3mf", "sphere_stand_1in", "Sphere Stands", UNK, "PLA",
    "Sphere Stand 1″", "Ring stand for a 25.4 mm sphere — knife-edge rim Ø19.2 mm holds it at ≈49°. Genus-1, watertight. Also seats the 27 mm passthrough ball.", ("pass", "Clean"))
add("sphere2", "sphere_stand_2.0in.3mf", "sphere_stand_2in", "Sphere Stands", UNK, "PLA",
    "Sphere Stand 2″", "Same revolved profile scaled for a 50.8 mm sphere — rim Ø36.5 mm, contact ≈46°. Also seats the 39 mm passthrough ball.", ("pass", "Clean"))
add("sphere3", "sphere_stand_3.0in.3mf", "sphere_stand_3in", "Sphere Stands", UNK, "PLA",
    "Sphere Stand 3″", "Largest of the family — rim Ø57.7 mm for a 76.2 mm sphere. All three share one 2,304-triangle topology.", ("pass", "Clean"))
add("vortex", "Vortex+v3+project.3mf", "vortex_v3", "Vortex", "Bazzlington · original", "PLA",
    "Vortex v3", "Three nested twisted sleeves (genus-1 tubes, 4-fold symmetry, 50 mm tall) that spin freely inside each other. Slicer estimate 32 g · 2 h 06 m.", ("pass", "Clean"))
add("fidget", "Mini+Fidget+Ball.3mf", "mini_fidget_ball", "Passthrough series", "RJ Design", "PLA",
    "Mini Fidget Ball", "Genus-21 helical ball threads itself through the smaller genus-7 disc. The preview shows every object in the file — the designer ships the ball at two sizes (27 + 13.5 mm, V2-series compatible); you print one. Axle = 33 mm of filament or a 2×33 brass dowel.", ("pass", "Clean"))
add("stackable", "Mini+Stackable+Supports+added+back+in.3mf", "mini_stackable", "Passthrough series", "RJ Design · V2", "PLA",
    "Mini Stackable Passthrough", "Threaded genus-17 tube sections stack into a vortex column; the preview shows all shipped objects: ball size variants (13.5/27/39 mm, V2-series compatible — print the one you need) plus assembly copies. Tree supports ship as mesh bodies — print sequentially.", ("pass", "Clean"))
add("top", "magic_spinning_top_+23+de+fight+d.3mf", "spinning_top", "Spinning Top", "AeroDesigns", "PLA",
    "Magic Spinning Top", "Floating-ring illusion: two genus-3 halves (ring + 3 spokes) plus two connector sizes — standard and +0.07 mm for slippery filaments. Never rescale.", ("pass", "Clean"))
add("skull", "Quantum+Skull.3mf", "quantum_skull", "Quantum Skull", "Gmino", "PLA",
    "Quantum Skull", "Two identical 31.5 cm³ skull halves that nest and slide as a two-hand fidget. Print each half in its own color (two plates).", ("pass", "Clean"))
add("puffer", "pufferfish.3mf", "pufferfish", "Pufferfish", "Legend Lee", "PETG",
    "Pufferfish — original", "Articulated squeeze-ball: hinged spike plates around a multi-body core, pulled by rubber bands. One leaky object of 10 — every slicer auto-repairs it.", ("warn", "1 leaky object"))
add("puffer3p", "pufferfish-p2s-threeplates.3mf", "pufferfish_threeplates", "Pufferfish", "Legend Lee", "PETG",
    "Pufferfish — 3-plate re-save", "Same 10 parts as the original (verified rotation-invariant), re-arranged across three plates for easier printing.", ("warn", "Same leaky part"))
add("puffer1c", "pufferfish-p2s-onecolor.3mf", "pufferfish_onecolor", "Pufferfish", "Legend Lee", "PETG",
    "Pufferfish — one-color re-save", "Same parts, color scheme flattened. A 1.3× scale is baked into mesh coords and canceled by transforms — prints the same size.", ("warn", "Same leaky part"))
add("pikachu", "pikachu+more+resistant+one+color.3mf", "pikachu", "Pikachu Flexy", "B-Forge3D · v2", "PETG",
    "Pikachu Flexy Keychain", "Print-in-place flexy of 7 hinged bodies. This file is itself the fix — the reinforced single-color v2 of a fragile original.", ("warn", "Minor defects"))
add("staryu", "Staryu_Starmie_Spin_Spin.3mf", "staryu_starmie", "Staryu & Starmie", "pythong · remix", "PLA",
    "Staryu & Starmie — original", "Two spinners on one bearing recipe, friction tuned by the diff_disc washer stack. Star heads carry 152 k duplicate faces — slicers discard them.", ("warn", "Dup-face defect"), reveals="staryu_dup", reveal_label="duplicate download")
add("staryu_dup", "Staryu_Starmie_Spin_Spin (1).3mf", "staryu_starmie", "Staryu & Starmie", "pythong · remix", "PLA",
    "Staryu & Starmie — copy (1)", "Byte-identical duplicate download of the original (same MD5). Safe to delete; kept here for completeness.", ("warn", "Duplicate file"), hide=True)
# --- chainmail and scale sheets, downloaded 2026-09-09 -------------------
# Two unrelated designs that arrive looking alike. Both are sheets of many
# small closed bodies printed touching, so both slice with no support and
# both stand or fall on first-layer squish rather than on any setting a
# profile carries.
FAB = "Bambu Lab \u00b7 MakerWorld"
add("fab_test", "TEST-OBJECT+(63mm+x+63mm)+-+BAMBULAB.3mf", "fabric_test",
    "Fabric Chainmail", FAB, "PLA",
    "Fabric Mat \u2014 63 mm test", "The rehearsal, and the piece to print "
    "first. 415 links against the 200 mm mat\u2019s 4,094, and 92 of its 93 "
    "distinct link shapes are shapes the big mat also uses \u2014 so it is a "
    "cut-out of the same tiling at a tenth of the cost, sliced on the same "
    "settings. 1 h 23 m and 13.8 g here, against 13 h 27 m and 131 g. What it "
    "tests is whether the links come out free on this printer, which is a "
    "question about first-layer squish and flow, not about a profile.",
    ("pass", "Clean \u00b7 415 links"))
add("fab_103", "FABRIC+MAT+(103mm+x+103mm)+-+BAMBULAB.3mf", "fabric_103",
    "Fabric Chainmail", FAB, "PLA",
    "Fabric Mat \u2014 103 mm", "1,050 links, 103 \u00d7 95 \u00d7 6 mm. "
    "Smallest of the four full mats.", ("pass", "Clean"))
add("fab_119", "FABRIC+MAT+(119mm+x+119mm)+-+BAMBULAB.3mf", "fabric_119",
    "Fabric Chainmail", FAB, "PLA",
    "Fabric Mat \u2014 119 mm", "1,422 links, 119 \u00d7 111 \u00d7 6 mm.",
    ("pass", "Clean"))
add("fab_151", "FABRIC+MAT+(151mm+x+151mm)+-+BAMBULAB.3mf", "fabric_151",
    "Fabric Chainmail", FAB, "PLA",
    "Fabric Mat \u2014 151 mm", "2,292 links, 151 \u00d7 143 \u00d7 6 mm.",
    ("pass", "Clean"))
add("fab_200", "FABRIC+MAT+(200mm+x+200mm)+-+BAMBULAB.3mf", "fabric_200",
    "Fabric Chainmail", FAB, "PLA",
    "Fabric Mat \u2014 200 mm", "4,094 links, 199 \u00d7 191 \u00d7 6 mm, "
    "and 13 h 27 m of them at 131 g. Print the 63 mm test first.",
    ("pass", "Clean"), mate="Fabric Mat \u2014 63 mm test", pair="fab_test")
add("dragon_skin", "Dragon+Skin+225+pz.3mf", "dragon_skin",
    "Dragon Skin", "SKFactory \u00b7 profile by a MakerWorld uploader", "PLA",
    "Dragon Skin \u2014 225 scales", "225 interlocking scales in a 175 mm "
    "sheet, 170 separate closed bodies, no support. The uploader\u2019s "
    "contribution is the profile and it is in the file: a variable layer "
    "height from 0.08 to 0.28 mm over the 9.8 mm height, Arachne walls and a "
    "Hilbert-curve bottom surface. It is not only prettier \u2014 their own "
    "slice recorded 90.6 g against the 99.2 g a flat 0.2 mm gives here. "
    "Original by @SKFactory on Printables, shared under a licence that allows "
    "it with attribution.", ("pass", "Clean \u00b7 no defects"))

HG = "Idea2Item · Printables"
add("cone_pair_s", "cone-hourglass-pair-small.3mf", "cone_pair_small", "Hourglass · Cone", HG, "PLA",
    "Cone Pair Plate — 90 mm", "Solid + eased spiral (0.05–0.15 mm entry lead-in) on one plate. Known failure: the solid’s wall thins to 1–2 mm where the slots taper at the rim, on a 35–39° flare — cracks in PETG as the top closes (spiral is innocent). Print PLA, 100% infill + ≥4 walls on the solid, 100% fan up top, brim. Full measurements in the print notes.", ("pass", "Built · both parts"))
add("cone_pair_d", "cone-hourglass-pair-dubbel.3mf", "cone_pair_dubbel", "Hourglass · Cone", HG, "PLA",
    "Cone Pair Plate — dubbel 180 mm", "The double-height pair on one plate, with the eased spiral (0.05–0.15 mm entry lead-in). 8.7:1 lever at 180 mm — brim mandatory; same thin-rim caution as the 90 mm plate.", ("pass", "Built · both parts"))
add("cone_solid_s", "cone-solid-small.stl", "cone_solid_small", "Hourglass · Cone", HG, "PLA",
    "Cone Solid — 90 mm", "Hourglass body with 7 helical slots + a central channel (mesh genus 8). 100% infill per the designer; lands on 7 first-layer islands — brim.", ("pass", "Clean"), mate="Cone Spiral — 90 mm (pair plate: cone-hourglass-pair-small.3mf)", pair="cone_pair_s")
add("cone_spiral_s", "cone-spiral-small.stl", "cone_spiral_small", "Hourglass · Cone", HG, "PLA",
    "Cone Spiral — 90 mm", "The smooth twisted piece (genus 0) that screws through the solid's slots. 15% gyroid infill.", ("pass", "Clean"), mate="Cone Solid — 90 mm", pair="cone_pair_s")
add("cone_solid_d", "cone-solid.stl", "cone_solid", "Hourglass · Cone", HG, "PLA",
    "Cone Solid — dubbel 180 mm", "Two hourglass cells stacked at constant Ø — same 7 slots per cell (mesh genus 15). 7.4:1 lever ratio — brim mandatory.", ("pass", "Clean"), mate="Cone Spiral — dubbel 180 mm (pair plate: cone-hourglass-pair-dubbel.3mf)", pair="cone_pair_d")
add("cone_spiral_d", "cone-spiral.stl", "cone_spiral", "Hourglass · Cone", HG, "PLA",
    "Cone Spiral — dubbel 180 mm", "Double-length spiral, same Ø41 body. 8.7:1 lever ratio — brim mandatory.", ("pass", "Clean"), mate="Cone Solid — dubbel 180 mm", pair="cone_pair_d")
add("pyr_pair_s", "pyramid-hourglass-pair-small.3mf", "pyramid_pair_small", "Hourglass · Pyramid", HG, "PLA",
    "Pyramid Pair Plate — 90 mm", "The repaired solid + eased spiral on one plate. Same thin-rim + 35–39° flare failure anatomy as the cone set — print PLA, 100% infill + ≥4 walls on the solid, 100% fan up top, brim. Details in the print notes.", ("pass", "Built · both parts"))
add("pyr_pair_d", "pyramid-hourglass-pair-dubbel.3mf", "pyramid_pair_dubbel", "Hourglass · Pyramid", HG, "PLA",
    "Pyramid Pair Plate — dubbel 180 mm", "Both parts on one plate. Same failure anatomy as the 90 mm set (thin rim ribbons on a 35–39° flare — field-confirmed at both scales), amplified here by the 8.7:1 lever and doubled travels. Prefer the individual cards on separate plates; PLA, max fan + slow outer wall up top, brim. Details in the print notes.", ("pass", "Built · both parts"))
add("pyr_solid_sf", "pyramid-solid-small-fixed.stl", "pyramid_solid_small_fixed", "Hourglass · Pyramid", HG, "PLA",
    "Pyramid Solid — 90 mm (fixed)", "The repaired body: zero-thickness pinch removed (2 fewer faces, watertight) — 7 slots + channel. Print this, not the original.", ("pass", "Repaired"), mate="Pyramid Spiral — 90 mm (pair plate: pyramid-hourglass-pair-small.3mf)", reveals="pyr_solid_so", reveal_label="original (pinch)", pair="pyr_pair_s")
add("pyr_solid_so", "pyramid-solid-small.stl", "pyramid_solid_small_orig", "Hourglass · Pyramid", HG, "PLA",
    "Pyramid Solid — 90 mm (original)", "Ships with a zero-thickness pinch: one duplicated triangle on a non-manifold edge. Superseded by the -fixed file — kept for reference.", ("warn", "Pinch defect"), hide=True)
add("pyr_spiral_s", "pyramid-spiral-small.stl", "pyramid_spiral_small", "Hourglass · Pyramid", HG, "PLA",
    "Pyramid Spiral — 90 mm", "Twisted square-base piece (genus 0) with the set's shared 7-lobe thread. 15% gyroid infill.", ("pass", "Clean"), mate="Pyramid Solid — 90 mm (fixed)", pair="pyr_pair_s")
add("pyr_solid_d", "pyramid-solid.stl", "pyramid_solid", "Hourglass · Pyramid", HG, "PLA",
    "Pyramid Solid — dubbel 180 mm", "Double-height slotted body, 7 slots per cell (mesh genus 19). 100% infill and a brim.", ("pass", "Clean"), mate="Pyramid Spiral — dubbel 180 mm (pair plate: pyramid-hourglass-pair-dubbel.3mf)", pair="pyr_pair_d")
add("pyr_spiral_d", "pyramid-spiral.stl", "pyramid_spiral", "Hourglass · Pyramid", HG, "PLA",
    "Pyramid Spiral — dubbel 180 mm", "Double-length spiral. 8.7:1 lever ratio — brim mandatory.", ("pass", "Clean"), mate="Pyramid Solid — dubbel 180 mm", pair="pyr_pair_d")
add("nuts", "montessori+nuts+and+bolts-fixed.3mf", "nuts_bolts", "Nuts & Bolts", "carnivalcamps", "PLA",
    "Montessori Nuts & Bolts", "Toddler counting toy: five jumbo bolts in 30 mm height steps (59–179 mm) sharing one chunky thread, plus a nut — every nut fits every bolt; print as many nuts as needed. The nut mesh shipped leaky (4 non-manifold edges from 5 zero-area slivers); repaired here — volume unchanged to 0.01 cm³, all six objects watertight. Non-toxic filament, brim on the tall bolts.", ("pass", "Repaired"), reveals="nuts_orig", reveal_label="original (leaky nut)")
add("nuts_orig", "montessori+nuts+and+bolts.3mf", "nuts_bolts", "Nuts & Bolts", "carnivalcamps", "PLA",
    "Montessori Nuts & Bolts — original", "As downloaded: the nut object carries 5 degenerate faces creating 4 non-manifold edges. Superseded by the repaired file — kept for reference.", ("warn", "Nut not watertight"), hide=True)
add("held_chain", "held-sphere-chained.3mf", "held_chained", "Designed here", "Claude · this session", "PLA",
    "Held Sphere + Chain", "Chainmail onto the untouched lattice: the hook is simply a longer, wider chain link — 20×12 mm with a thin Ø2.4 tube, standard 45° tilt — threaded through one stock lattice opening and wrapped around a low strut. No cage modifications, nothing welded, no extra hardware; capture proven by ray-escape test, 0.52 mm running clearance, chain joints ≥0.48 mm. Prints flat in one job.", ("pass", "Designed · ready"), mate="Held Sphere (chainless version)")
LOCAL = "(local export)"
add("cshape", "c-shape copy 16.stl", "c_shape", "One-off Experiments", LOCAL, "PLA",
    "C-Shape (copy 16)", "Arch of fused spherical lobes — 286 cm³ solid, clean and watertight.", ("pass", "Clean"))
add("remesh", "remesh_averaged_model_thresh0.900.stl", "remesh_avg", "One-off Experiments", LOCAL, "PLA",
    "Averaged Remesh", "Smoothed low-poly arch (2,146 faces) — an averaging-pipeline output at threshold 0.900.", ("pass", "Clean"))
add("voro", "voro_sphere_2.stl", "voro_sphere", "One-off Experiments", LOCAL, "PLA",
    "Voronoi Sphere — original", "Openwork lattice shell (genus 56, “Voronoi” per the filename) as downloaded: inverted normals and saved at Ø2 mm. Superseded by the fixed version — kept for reference.", ("warn", "Superseded"), hide=True)
add("voro_f", "voro_sphere_2-fixed.stl", "voro_fixed", "One-off Experiments", LOCAL, "PLA",
    "Voronoi Sphere — fixed Ø60", "Repaired here: normals flipped (volume now positive, 28.8 cm³) and scaled 30× to Ø60 mm — mean strut ≈2.9 mm, comfortably printable. Watertight, genus 56. Slicer flags floating regions where lattice arcs start mid-air: enable tree supports or accept some rough undersides.", ("pass", "Repaired · ready"), reveals="voro", reveal_label="original (Ø2 mm)")

SLICE = {
 "sphere1": "2 m · 0.8 g", "sphere2": "7 m · 3.4 g", "sphere3": "14 m · 8.8 g",
 "vortex": "1 h 24 m · 27.9 g (via STL re-slice — the project file mis-slices in the CLI)",
 "fidget": "44 m · 8.0 g", "stackable": "5 h 32 m · 48.6 g",
 "top": "28 m · 11.4 g", "skull": "1 h 02 m · 36.7 g",
 "puffer": "2 h 09 m · 63.1 g — plate 1 of 4",
 "puffer3p": "2 h 09 m · 63.1 g — plate 1 of 4",
 "puffer1c": "4 h 07 m · 81.8 g — single plate",
 "pikachu": "18 m · 5.3 g",
 "staryu": "10 m · 4.3 g — plate 1 of 4", "staryu_dup": "10 m · 4.3 g — plate 1 of 4",
 "cone_pair_s": "2 h 19 m · 60.5 g", "cone_pair_d": "4 h 54 m · 133.2 g",
 "cone_solid_s": "1 h 17 m · 30.6 g", "cone_spiral_s": "1 h 03 m · 30.1 g",
 "cone_solid_d": "2 h 42 m · 71.0 g", "cone_spiral_d": "2 h 12 m · 62.4 g",
 "pyr_pair_s": "2 h 37 m · 75.5 g", "pyr_pair_d": "5 h 11 m · 147.6 g",
 "pyr_solid_sf": "1 h 32 m · 42.7 g", "pyr_solid_so": "1 h 31 m · 42.7 g",
 "pyr_spiral_s": "1 h 06 m · 32.9 g", "pyr_solid_d": "2 h 58 m · 83.7 g",
 "pyr_spiral_d": "2 h 14 m · 64.0 g",
 "cshape": "2 h 54 m · 93.1 g", "remesh": "1 h 26 m · 37.4 g",
 "voro": "unsliceable at Ø2 mm — print the fixed version",
 "voro_f": "1 h 22 m · 24.8 g",
 "nuts": "5 h 32 m · 228.4 g (Studio on the P2S: 6 h 56 m · 225.05 g)", "nuts_orig": "5 h 32 m · 228.4 g",
 "held": "43 m · 8.9 g — bridged struts; tree supports optional", "chain2x": "32 m · 10.6 g — brimless-friendly", "held_chain": "1 h 01 m · 13.5 g (Studio on the P2S: 1 h 06 m · 12.72 g)", "chain": "9 m · 2.3 g",
}

# --- flexi print-in-place models, downloaded 2026-09-02 -------------------
# Flexi Factory ships each design cut for several bed shapes and for two
# slicers. Only the Bambu variants are here, and of the dragon only the
# square-bed cut: its file spans 508 mm because the two halves are laid
# side by side, but each half is 203 x 193 and fits the P2S on its own.
add("flexi_dragon", "Flexi Factory Dragon Square Bed.3mf", "flexi_dragon",
    "Flexi Factory", "Flexi Factory", "PLA",
    "Flexi Imperial Dragon", "Print-in-place articulated dragon, cut in two "
    "halves for a square bed. Each half is 203 x 193 mm and prints on its "
    "own plate; the designer's file lays both side by side at 508 mm, which "
    "no P2S plate takes. Wide-bed and Printmill cuts of the same dragon are "
    "in the download and are not here — they are for other bed shapes.",
    ("pass", "Clean"),
    proven="PLA, no supports — both halves clean. The check reads it as 0 "
           "island and 1678 mm2 of bridged ledge, which is what a "
           "print-in-place model should look like.")
add("flexi_trex_curved", "Bambu Flexi Factory Skeleton T-Rex_Curved.3mf",
    "flexi_trex_curved", "Flexi Factory", "Flexi Factory", "PLA",
    "Flexi Skeleton T-Rex — curved", "Print-in-place articulated skeleton, "
    "four bodies on one 179 x 152 mm plate, laid out in the curved pose. "
    "The Prusa cut of the same model is in the download and is not here.",
    ("pass", "Clean"),
    proven="PLA, no supports. Which of the two poses went on the plate was "
           "not recorded, and they are the same four bodies laid out "
           "differently, so it stands for both rather than for a guess at "
           "one.")
add("flexi_trex_straight", "Bambu Flexi Factory Skeleton T-Rex_Straight.3mf",
    "flexi_trex_straight", "Flexi Factory", "Flexi Factory", "PLA",
    "Flexi Skeleton T-Rex — straight", "The same skeleton laid out straight "
    "rather than curved: four bodies on a 176 x 176 mm plate. One pose or "
    "the other, not both.", ("pass", "Clean"),
    mate="Flexi Skeleton T-Rex — curved",
    proven="PLA, no supports. Which of the two poses went on the plate was "
           "not recorded, and they are the same four bodies laid out "
           "differently, so it stands for both rather than for a guess at "
           "one.")
add("flexi_trex_stand", "Bambu Flexi Factory Skeleton T-Rex Stand.3mf",
    "flexi_trex_stand", "Flexi Factory", "Flexi Factory", "PLA",
    "Flexi Skeleton T-Rex stand", "Display stand for the skeleton, 114 x 126 "
    "mm.", ("pass", "Clean"), mate="Flexi Skeleton T-Rex")

BY_FILE = {}
for _c in C:
    BY_FILE.setdefault(_c["file"].rsplit("/", 1)[-1], _c)


def curation(filename):
    """What we know about a file by name, or None if it is just a file."""
    return BY_FILE.get(filename.rsplit("/", 1)[-1])
