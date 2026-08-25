#!/usr/bin/env python3
"""Build The Fidget Shelf — visual index of downloaded toy 3MFs."""
import base64, io, os
from PIL import Image, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
THUMBS = os.path.join(HERE, "index_out", "thumbs")

def thumb_uri(slug, crop_43=True):
    im = Image.open(os.path.join(THUMBS, slug + ".png"))
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (245, 244, 240))
        bg.paste(im, mask=im.split()[3])
        im = bg
    else:
        im = im.convert("RGB")
    # trim near-uniform border
    corner = im.getpixel((2, 2))
    diff = ImageChops.difference(im, Image.new("RGB", im.size, corner))
    bbox = diff.point(lambda p: 255 if p > 24 else 0).getbbox()
    if bbox:
        pad = 20
        l, t, r, b = bbox
        l = max(0, l - pad); t = max(0, t - pad)
        r = min(im.width, r + pad); b = min(im.height, b + pad)
        im = im.crop((l, t, r, b))
    # letterbox to 4:3
    if crop_43:
        tw, th = 4, 3
        w, h = im.size
        if w / h > tw / th:
            nh = int(w * th / tw)
            canvas = Image.new("RGB", (w, nh), im.getpixel((2, 2)))
            canvas.paste(im, (0, (nh - h) // 2)); im = canvas
        else:
            nw = int(h * tw / th)
            canvas = Image.new("RGB", (nw, h), im.getpixel((2, 2)))
            canvas.paste(im, ((nw - w) // 2, 0)); im = canvas
    im.thumbnail((480, 360), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=76)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()

FAMILIES = [
 dict(slug="sphere_stand_2_0in", material=("PLA", "PLA — decorative, zero mechanical stress; best surface finish"), name="Sphere Stand", designer="(unattributed export)",
      files=["sphere_stand_1.0in.3mf", "sphere_stand_2.0in.3mf", "sphere_stand_3.0in.3mf"],
      verdict=("pass", "Clean ×3"),
      principle="A single revolved ring profile (genus-1 torus-like solid) whose knife-edge rim is the contact circle a sphere rests on. All three sizes share the identical 2,304-triangle topology — one profile, re-scaled.",
      drivers=["sphere Ø (the sole input)", "rim Ø ≈ 0.75 × sphere Ø", "contact angle ≈ 46–49°", "height ≈ 0.18–0.20 × sphere Ø (sub-linear)"],
      specs=[("Sizes", "1&Prime; / 2&Prime; / 3&Prime; spheres"), ("Footprint Ø", "20.5 / 41.3 / 61.5 mm"),
             ("Height", "5.1 / 9.3 / 13.4 mm"), ("Solid PLA", "0.8 / 5.5 / 18.6 g"),
             ("Topology", "genus 1, watertight"), ("Mesh", "2,304 tris each")],
      note="Not uniform scaling: a 2&Prime; stand is 2.01× wider but only 1.82× taller than the 1&Prime; — the cross-section fattens slower than the rim grows, keeping the stand squat."),
 dict(slug="vortex_v3_project", material=("PLA", "PLA — clean helical overhangs, no stringing between nested sleeves"), name="Vortex v3", designer="Bazzlington · original",
      files=["Vortex+v3+project.3mf"], verdict=("pass", "Clean"),
      principle="Three nested coaxial twisted sleeves, each a genus-1 tube with 4-fold rotational symmetry, all exactly 50 mm tall. The helical vanes let each sleeve spin freely inside the next — a telescoping vortex.",
      drivers=["sleeve count = 3", "outer Ø 38.0 → 32.7 → 28.1 mm (≈2.7 mm radial nesting gap)", "common height 50 mm", "4-fold twist symmetry"],
      specs=[("Assembled", "Ø38 × 50 mm"), ("Volume", "27.3 cm³"), ("Slicer est.", "32.2 g · 2 h 06 m"),
             ("Profile", "0.2 mm, 3 walls, 25%"), ("Topology", "2× genus 1 + 1 core, all watertight"), ("Mesh", "378,652 tris")],
      note=None),
 dict(slug="mini_fidget_ball", material=("PLA", "PLA — hard, slick surface keeps the thread passthrough smooth"), name="Mini Fidget Ball", designer="RJ Design · original",
      files=["Mini+Fidget+Ball.3mf"], verdict=("pass", "Clean"),
      principle="An “impossible passthrough”: a helically-grooved ball (genus 21) threads itself through a disc (genus 7) whose opening is smaller than the ball. The thread converts push into rotation — a screw in disguise.",
      drivers=["ball Ø as a pure 3MF scale transform — one mesh instanced at 1× (27 mm) and 0.5× (13.5 mm)", "disc Ø 34.9 × 8 mm", "helix pitch sets pass-through force"],
      specs=[("Ball", "Ø27 mm (+13.5 mm copy)"), ("Disc", "Ø34.9 × 8 mm"), ("Slicer est.", "11.3 g · 52 m"),
             ("Profile", "0.2 mm, 2 walls, 30% gyroid"), ("Topology", "genus 21 + 7, watertight"), ("Mesh", "845,530 tris")],
      note="Assembles with a 33 mm length of 1.75 mm filament or a 2×33 mm brass dowel as the axle pin."),
 dict(slug="mini_stackable_supports_added_back_in", material=("PLA", "PLA — tree supports release cleanly; PETG welds to its supports"), name="Mini Stackable Passthrough", designer="RJ Design · V2 series",
      files=["Mini+Stackable+Supports+added+back+in.3mf"], verdict=("pass", "Clean"),
      principle="The passthrough principle stretched into a tube: threaded genus-17 tube sections (male thread passes through the slightly larger female) stack into an arbitrarily long vortex column a ball twists down.",
      drivers=["ball Ø via scale transforms: one mesh at 0.5× / 1× / 1.44× → 13.5 / 27 / 39 mm", "tube Ø35.4 × 62.2 mm per section", "section count = column length", "caps Ø35.4 × 3.8 mm close the ends"],
      specs=[("Tube section", "Ø35.4 × 62.2 mm"), ("Volume", "71.4 cm³ total"), ("Solid PLA", "≈88 g"),
             ("Profile", "0.2 mm, 2 walls, 30%"), ("Topology", "genus 17–20, watertight"), ("Mesh", "3.73 M tris — 23 MB file")],
      note="“Supports added back in”: each ball object carries an extra mesh body (3 vs 2 in the Fidget Ball) — the ball floats above the plate and ships with its tree-support geometry restored. Print sequentially, 30° tree supports."),
 dict(slug="hourglass_cone", material=("PETG", "PETG — designer printed PETG; PLA works with the same 100%-infill rule"), name="Impossible Hourglass — Cone", designer="Idea2Item · Printables · CC BY-NC-SA",
      files=["cone-solid-small.stl", "cone-spiral-small.stl", "cone-solid.stl", "cone-spiral.stl"],
      verdict=("pass", "Clean ×4"),
      principle="An impossible-spiral pair per size: the smooth twisted “spiral” piece (genus 0) screws through helical slots cut clear through the wider “solid” hourglass (genus 8–15) — it looks impossible because the solid’s waist is narrower than the piece passing it. Their waist profiles match exactly (both dip to the same radius at the same heights).",
      drivers=["base profile: circle", "cell count: 1 hourglass (90 mm) or 2 stacked (“dubbel”, 180 mm) at constant Ø", "7 helical slots + a central channel (mesh genus 8 small, 15 dubbel)", "waist Ø ≈ 21–23 mm vs body Ø ≈ 41–48 mm"],
      specs=[("Small pair", "Ø44.7 / 41.3 × 90 mm"), ("Dubbel pair", "Ø48.4 / 41.2 × 180 mm"),
             ("Volumes", "33.4–87.3 cm³"), ("Lever ratio", "4.0:1 small → 8.7:1 dubbel"),
             ("Designer settings", "PETG · 0.2 mm · 3 walls · brim"), ("Infill", "100% solid body / 15% gyroid spiral")],
      note="The 180 mm versions run 7.4–8.7:1 lever ratios and cone-solid-small lands on 7 separate first-layer islands (smallest 0.7 cm²) — the designer’s brim advice is mandatory, not optional."),
 dict(slug="hourglass_pyramid", material=("PETG", "PETG — designer printed PETG; PLA works with the same 100%-infill rule"), name="Impossible Hourglass — Pyramid", designer="Idea2Item · Printables · CC BY-NC-SA",
      files=["pyramid-solid-small.stl", "pyramid-solid-small-fixed.stl", "pyramid-spiral-small.stl", "pyramid-solid.stl", "pyramid-spiral.stl"],
      verdict=("warn", "Original had pinch"),
      principle="The same passthrough principle on a square base: genus-10 / genus-19 slotted hourglass bodies with matching genus-0 twisted pyramids that thread through them. Square corners make the twist read more dramatically than the cone version.",
      drivers=["base profile: square", "cell count: 1 (90 mm) or 2 (“dubbel”, 180 mm)", "the same 7 helical slots + channel (mesh genus 10 small, 19 dubbel)", "waist Ø 28 mm vs body 46.6–47.5 mm"],
      specs=[("Small pair", "46.6 / 41.4 × 90 mm"), ("Dubbel pair", "47.5 / 41.2 × 180 mm"),
             ("Volumes", "47.1–113.2 cm³"), ("Lever ratio", "3.9:1 small → 8.7:1 dubbel"),
             ("Designer settings", "PETG · 0.2 mm · 3 walls · brim"), ("Infill", "100% solid body / 15% gyroid spiral")],
      note="pyramid-solid-small.stl ships with a zero-thickness pinch — one duplicated triangle riding a non-manifold edge. Your <code>-fixed</code> re-export (Aug 20) removes both copies: 2 fewer faces, 1 fewer vertex, watertight again. Print the fixed file; the other four are clean as-shipped."),
 dict(slug="magic_spinning_top_23_de_fight_d", material=("PLA", "PLA — use the “PLA” connector for silk/slippery filaments; PETG tip survives drops better"), name="Magic Spinning Top", designer="AeroDesigns · “floating” illusion",
      files=["magic_spinning_top_+23+de+fight+d.3mf"], verdict=("pass", "Clean"),
      principle="A floating-ring illusion top: upper and lower halves are each genus-3 solids — an outer ring joined to the hub by 3 spokes — so the spinning ring appears detached from the centre spike. Mass at the rim gives the long spin.",
      drivers=["rotor Ø 73.1 mm", "assembled height 41.3 mm", "3-fold spoke symmetry (the genus count)", "connector interference: two variants 0.06–0.07 mm apart"],
      specs=[("Rotor", "Ø73.1 × 41.3 mm"), ("Volume", "11.1 cm³"), ("Solid PLA", "13.8 g"),
             ("Connector", "7.58×6.56 vs 7.65×6.62 mm"), ("Topology", "2× genus 3, watertight"), ("Mesh", "5,292 tris")],
      note="Ships two connectors: standard and a “PLA” variant +0.07 mm larger for slippery filaments (silk PLA). Warning from the designer: rescaling breaks the connector fit — clearance doesn’t scale."),
 dict(slug="quantum_skull", material=("PLA", "PLA — harder, slicker faces glide better for the sliding fidget"), name="Quantum Skull", designer="Gmino · original",
      files=["Quantum+Skull.3mf"], verdict=("pass", "Clean"),
      principle="Two identical genus-0 skull halves (STEP-born solids, 31.53 cm³ each — byte-equal volumes) that nest and slide against each other as a two-hand fidget. The whole design is one shell duplicated.",
      drivers=["half size 81 × 103 × 37 mm", "print each half in a different colour (two plates)", "mating clearance between the shells"],
      specs=[("Each half", "81 × 103 × 37 mm"), ("Volume", "63.1 cm³ pair"), ("Solid PLA", "78 g pair"),
             ("Profile", "0.24 mm, 3 walls, 15%"), ("Topology", "2× genus 0, watertight"), ("Mesh", "30,692 tris")],
      note=None),
 dict(slug="pufferfish", material=("PETG", "PETG — rubber-band loads on hinged plates favor ductility; PLA can snap"), name="Pufferfish (捏捏河豚)", designer="Legend Lee · squeeze toy",
      files=["pufferfish.3mf", "pufferfish-p2s-threeplates.3mf", "pufferfish-p2s-onecolor.3mf"], verdict=("warn", "1 leaky object"),
      principle="An articulated squeeze-ball: spiked shell plates hinge around a multi-body core (objects of 6–15 bodies each), pulled back by rubber bands so the fish puffs and relaxes. Eyes are two perfect Ø9.36 mm spheres (radial deviation 0.0).",
      drivers=["body ≈ 88 × 95 × 33 mm closed", "spike-plate count (12- and 15-body rings)", "rubber-band tension = squeeze force", "eye Ø 9.36 mm"],
      specs=[("Body", "≈88 × 95 × 33 mm"), ("Parts", "10 objects, up to 15 bodies each"), ("Volume", "52+ cm³ (one part unmeasurable)"),
             ("Profile", "0.16 mm, 2 walls, 15%"), ("Validation", "9/10 watertight; the 147k-tri 12-body spike ring leaks"), ("Mesh", "385,412 tris")],
      note="Dedup verified with rotation-invariant signatures (volume, area, inertia): all three files carry the same 10 parts. threeplates only re-plates them; onecolor bakes a 1.3× scale into the mesh coordinates and cancels it in the placement transform — same physical size. The leaky ring is a shared upstream defect every slicer auto-repairs. Needs rubber bands, lubricant and glue to assemble."),
 dict(slug="pikachu_more_resistant_one_color", material=("PETG", "PETG — keychain abuse bends thin links; brittle PLA is the failure the v2 rework addressed"), name="Pikachu Flexy Keychain", designer="B-Forge3D · v2 “more resistant”",
      files=["pikachu+more+resistant+one+color.3mf"], verdict=("warn", "Minor defects"),
      principle="A print-in-place articulated flexy: one object containing 7 interlocked bodies (head, tail and body segments) that hinge without assembly. This file is itself the fix — the reinforced single-colour v2 replacing the fragile multi-colour original.",
      drivers=["7 linked segments", "hinge clearance (print-in-place)", "overall 32.5 × 76.1 × 14.1 mm"],
      specs=[("Size", "32.5 × 76.1 × 14.1 mm"), ("Bodies", "7, print-in-place"), ("Validation", "not watertight; 5 degenerate faces — cosmetic, slicer-repairable"),
             ("Profile", "“new version — more resistant single color”"), ("Mesh", "34,818 tris"), ("License", "MakerWorld Exclusive")],
      note=None),
 dict(slug="staryu_starmie_spin_spin", material=("PLA", "PLA — slick printed bearing spins best; switch the thin pins to PETG if they snap"), name="Staryu & Starmie Spinners", designer="pythong · remix of Nova7171",
      files=["Staryu_Starmie_Spin_Spin.3mf", "Staryu_Starmie_Spin_Spin (1).3mf"], verdict=("warn", "Dup-face defect"),
      principle="Two fidget spinners built on one bearing recipe: a printed pin + screw hub spins a star-shaped rotor, with friction tuned by a stack of “diff_disc” washers. Starmie Ø74.7; Staryu is the same design at 94% scale with a thicker ring.",
      drivers=["global scale: Staryu = 0.94 × Starmie (parts not interchangeable)", "washer stack: 5× Ø11×1.0 mm + Ø10.3×0.94 + Ø10.3×2.35 mm shims", "star heads: 8-fold (Staryu) vs 10-fold (Starmie) symmetry", "half the thickness of the original model"],
      specs=[("Starmie", "Ø74.7 × 5.5 mm"), ("Staryu", "Ø70.1 × 7.9 mm"), ("Volume", "≈39 cm³ (watertight parts)"),
             ("Validation", "4 objects carry mass duplicate faces — heads have 152,511 dup tris (45%)"), ("Mesh", "921,452 tris"), ("License", "BY-NC-SA · no AMS needed")],
      note="The head part is literally named Startmie_head_final_fixed.stl — a repaired replacement — yet still carries the coincident-duplicate-surface defect. Harmless in practice: slicers discard duplicates. The second file is a byte-identical duplicate download (same MD5) — safe to delete."),
 dict(slug="oneoff_stls", material=("PLA", "PLA — experiment prints; the Voronoi shell needs ≥20× scale and clean thin walls"), name="One-off Experiments", designer="(local exports, unattributed)",
      files=["c-shape copy 16.stl", "remesh_averaged_model_thresh0.900.stl", "voro_sphere_2.stl"],
      verdict=("warn", "1 inverted mesh"),
      principle="Three unrelated one-offs found loose in ~/Downloads. Two are arch studies: a C-shaped arch built from fused spherical lobes (121 × 146 × 42 mm, genus 0) and a smoothed low-poly arch of the same silhouette (2,146 faces — an averaging-pipeline output, per its thresh 0.900 filename). The third is a Voronoi lattice sphere: a genus-56 openwork shell.",
      drivers=["arch: lobe count and arch sweep", "remesh: averaging threshold 0.900 sets smoothness", "voro sphere: cell count = genus 56, shell thickness", "voro sphere modelled at unit scale — Ø2 mm as saved"],
      specs=[("C-shape", "121 × 146 × 42 mm · 286 cm³"), ("Remesh", "103 × 116 × 17 mm · 96 cm³"),
             ("Voro sphere", "Ø2 mm · genus 56"), ("Validation", "arches clean & watertight"),
             ("Defect", "voro sphere normals inverted (negative volume)"), ("Mesh", "9,770 / 2,146 / 84,480 tris")],
      note="voro_sphere_2.stl needs two fixes before printing: flip the normals (the whole surface points inward) and scale up ≥20× — at the saved Ø2 mm the struts are thinner than a nozzle."),
 dict(slug="montessori_nuts_and_bolts", material=("PLA", "PLA — stiff chunky threads screw smoothly; use quality non-toxic filament for a toddler toy"), name="Montessori Nuts & Bolts", designer="carnivalcamps · Standard License",
      files=["montessori+nuts+and+bolts.3mf"],
      verdict=("warn", "Nut not watertight"),
      principle="A toddler counting toy: five jumbo bolts in exact 30 mm height steps (59 → 179 mm) share one hex head profile (50 × 57 mm) and one chunky rounded thread, so every nut fits every bolt — the length sequence is the counting ladder. Print as many nuts as the game needs.",
      drivers=["bolt length: 30 mm per counting step (≈2–6 nut-heights)", "one shared thread profile across all six parts", "hex head = nut profile, 50.3 × 57.1 mm", "nut height 30 mm sets the step size"],
      specs=[("Bolts", "5, heights 59–179 mm"), ("Nut", "50.3 × 57.1 × 30 mm"),
             ("Solid volume", "≈638 cm³ total"), ("Profile", "0.2 mm, 2 walls, 15%"),
             ("Validation", "5 bolts watertight (genus 1); nut leaks — slicer-repairable"), ("Mesh", "217,774 tris")],
      note="Designer's safety note: use high-quality, non-toxic filament and supervise play. The tallest bolt is 179 mm — print upright with a brim."),
]

COMPAT = [
 ("pass", "V2 passthrough series (designer-stated, measured)",
  "Mini Fidget Ball and Mini Stackable share the same canonical ball mesh at 13.5 / 27 / 39 mm — the 27 mm ball threads both the fidget disc (Ø34.9) and the stackable tube (Ø35.4). Stackable sections thread into each other indefinitely: male passes female by design."),
 ("pass", "Passthrough balls on the sphere stands",
  "A ball sits on a stand when its Ø exceeds the rim Ø. The 27 mm ball rests on the 1″ stand (rim 19.2 mm, contact ≈45°) and the 39 mm ball on the 2″ stand (rim 36.5 mm — deep seat, ≈69°). The 13.5 mm ball falls through every stand."),
 ("warn", "Staryu vs Starmie — same design, no shared parts",
  "Staryu is the same spinner at 94% scale: pins, spacers and heads do not interchange between the two (designer-confirmed, and the pin Øs differ). The diff_disc washer stack is the shared tuning hardware within each spinner."),
 ("pass", "Hourglass cone & pyramid share one 7-lobe thread (measured)",
  "Cross-sections show every hourglass part rides the same 7-lobe inner mechanism — cone and pyramid differ only in outer skin (round vs square). Clearance measured 0.38 mm for all four solid×spiral combinations at the mid-connection, so same-size cone and pyramid parts likely interchange. Size classes do not mix: small and dubbel waist profiles differ."),
 ("warn", "Spinning top connector is fit-critical",
  "The two connectors differ by 0.06–0.07 mm for different filaments; the designer warns any rescale of the top breaks the fit, since clearance does not scale with the part."),
]

FIXES = [
 ("Pyramid hourglass", "Mesh repaired locally: <code>pyramid-solid-small.stl</code> has a zero-thickness pinch (one duplicated triangle on a non-manifold edge). <code>pyramid-solid-small-fixed.stl</code> (Aug 20) deletes both copies of the triangle — 2 fewer faces, watertight again."),
 ("Staryu / Starmie", "Head replaced upstream: <code>Startmie_head_final_fixed.stl</code>. The whole model is a remix that redesigned the body edges, pin and back wall at half the original thickness, removing the need for supports and glue."),
 ("Magic Spinning Top", "Connector part shipped in two sizes — standard and <code>connector PLA.stl</code>, +0.06–0.07&nbsp;mm — swap the part instead of rescaling to fix a loose fit."),
 ("Pikachu", "Entire file is the replacement: v2 “more resistant” rebuild of a fragile original, in single-colour form."),
 ("Mini Stackable", "“Supports added back in” — the floating ball’s tree-support geometry was restored as an extra mesh body inside each ball object after an earlier upload shipped without it."),
 ("Pufferfish", "Your two <code>-p2s-</code> files are re-saves of the original — verified with rotation-invariant part signatures. threeplates re-plates the same parts; onecolor bakes a 1.3× scale into mesh coordinates and cancels it in the placement transform (same printed size)."),
 ("Staryu duplicate", "<code>Staryu_Starmie_Spin_Spin (1).3mf</code> is byte-identical (MD5 <code>9eb99177…</code>) to the original — a double download, not a revision."),
]

ALLFILES = [
 ("sphere_stand_1.0in.3mf", "0.02", "Sphere Stand", "pass", "watertight · genus 1"),
 ("sphere_stand_2.0in.3mf", "0.02", "Sphere Stand", "pass", "watertight · genus 1"),
 ("sphere_stand_3.0in.3mf", "0.02", "Sphere Stand", "pass", "watertight · genus 1"),
 ("Vortex+v3+project.3mf", "6.03", "Vortex v3", "pass", "3 objects, all watertight"),
 ("Mini+Fidget+Ball.3mf", "6.07", "Mini Fidget Ball", "pass", "watertight · genus 21+7"),
 ("Mini+Stackable+Supports+added+back+in.3mf", "23.4", "Mini Stackable", "pass", "watertight · 3.73 M tris"),
 ("magic_spinning_top_+23+de+fight+d.3mf", "0.70", "Magic Spinning Top", "pass", "watertight · 2 connector variants"),
 ("Quantum+Skull.3mf", "1.38", "Quantum Skull", "pass", "watertight · mirror pair"),
 ("pufferfish.3mf", "7.01", "Pufferfish", "warn", "1 of 10 objects leaks"),
 ("pufferfish-p2s-threeplates.3mf", "7.01", "Pufferfish", "warn", "same geometry, replated"),
 ("pufferfish-p2s-onecolor.3mf", "5.63", "Pufferfish", "warn", "same geometry, one colour"),
 ("pikachu+more+resistant+one+color.3mf", "1.43", "Pikachu Flexy", "warn", "not watertight · 5 degen faces"),
 ("Staryu_Starmie_Spin_Spin.3mf", "15.7", "Staryu & Starmie", "warn", "152 k duplicate faces"),
 ("Staryu_Starmie_Spin_Spin (1).3mf", "15.7", "Staryu & Starmie", "warn", "exact duplicate file"),
 ("cone-solid-small.stl", "8.8", "Hourglass · cone", "pass", "watertight · genus 8"),
 ("cone-solid.stl", "10.0", "Hourglass · cone", "pass", "watertight · genus 15"),
 ("cone-spiral-small.stl", "8.5", "Hourglass · cone", "pass", "watertight · genus 0"),
 ("cone-spiral.stl", "9.7", "Hourglass · cone", "pass", "watertight · genus 0"),
 ("pyramid-solid-small.stl", "9.6", "Hourglass · pyramid", "warn", "pinch defect — superseded by -fixed"),
 ("pyramid-solid-small-fixed.stl", "9.6", "Hourglass · pyramid", "pass", "repaired · watertight · genus 10"),
 ("pyramid-solid.stl", "11.0", "Hourglass · pyramid", "pass", "watertight · genus 19"),
 ("pyramid-spiral-small.stl", "9.6", "Hourglass · pyramid", "pass", "watertight · genus 0"),
 ("pyramid-spiral.stl", "10.0", "Hourglass · pyramid", "pass", "watertight · genus 0"),
 ("c-shape copy 16.stl", "0.5", "One-off experiments", "pass", "watertight · genus 0"),
 ("remesh_averaged_model_thresh0.900.stl", "0.1", "One-off experiments", "pass", "watertight · low-poly"),
 ("voro_sphere_2.stl", "4.1", "One-off experiments", "warn", "inverted normals · unit scale Ø2 mm"),
 ("montessori+nuts+and+bolts.3mf", "2.9", "Montessori Nuts & Bolts", "warn", "5 bolts clean · nut leaks (repairable)"),
]

def esc(s): return s

if __name__ == "__main__":
    cards = []
    for f in FAMILIES:
        uri = thumb_uri(f["slug"])
        chips = "".join(f'<li>{d}</li>' for d in f["drivers"])
        mat_badge, mat_why = f["material"]
        all_specs = [("Material", mat_why)] + f["specs"]
        specs = "".join(f'<div class="spec"><dt>{k}</dt><dd>{v}</dd></div>' for k, v in all_specs)
        note = f'<p class="note">{f["note"]}</p>' if f["note"] else ""
        nfiles = len(f["files"])
        filelist = " · ".join(f["files"]) if nfiles > 1 else f["files"][0]
        vclass, vlabel = f["verdict"]
        cards.append(f'''
    <article class="card">
      <div class="photo"><img src="{uri}" alt="{f['name']}" loading="lazy">
        <span class="pill {vclass}">{vlabel}</span></div>
      <div class="body">
        <header><h3>{f['name']} <span class="mat">{mat_badge}</span></h3><p class="designer">{f['designer']}</p></header>
        <p class="principle">{f['principle']}</p>
        <h4>Shape drivers</h4>
        <ul class="drivers">{chips}</ul>
        <dl class="specs">{specs}</dl>
        {note}
        <p class="files" title="{filelist}">{nfiles} file{'s' if nfiles>1 else ''}: {filelist}</p>
      </div>
    </article>''')

    fixes = "".join(f'<li><strong>{t}</strong><span>{d}</span></li>' for t, d in FIXES)
    compat = "".join(f'<li><strong><span class="dot {c}"></span>{t}</strong><span>{d}</span></li>' for c, t, d in COMPAT)
    rows = "".join(
        f'<tr><td class="mono">{n}</td><td class="mono num">{s}</td><td>{fam}</td>'
        f'<td><span class="dot {v}"></span>{note}</td></tr>'
        for n, s, fam, v, note in ALLFILES)

    TEMPLATE = open(os.path.join(HERE, "page_template.html")).read()
    html = (TEMPLATE.replace("{{CARDS}}", "\n".join(cards))
            .replace("{{FIXES}}", fixes).replace("{{COMPAT}}", compat).replace("{{ROWS}}", rows))
    out = os.path.join(HERE, "fidget_shelf.html")
    open(out, "w").write(html)
    print("wrote", out, len(html) // 1024, "KB")
