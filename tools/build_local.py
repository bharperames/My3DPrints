#!/usr/bin/env python3
"""Build ~/Code/My3DPrints/index.html — one card per file, live 3D viewports."""
import json, os, re as _re
from build_page import FIXES, ALLFILES, COMPAT   # side effect: also rebuilds artifact html

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.expanduser("~/Code/My3DPrints/models")
manifest = {m["slug"]: m for m in json.load(open(os.path.join(MODELS_DIR, "manifest.json")))}

C = []
def add(cid, file, glb, family, designer, mat, title, blurb, v, mate=None, hide=False, reveals=None, reveal_label=None, pair=None):
    C.append(dict(cid=cid, file=file, glb=glb, family=family, designer=designer,
                  mat=mat, title=title, blurb=blurb, v=v, mate=mate, hide=hide,
                  reveals=reveals, reveal_label=reveal_label, pair=pair))

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
    "Quantum Skull", "Two identical 31.5 cm³ skull halves that nest and slide as a two-hand fidget. Print each half in its own colour (two plates).", ("pass", "Clean"))
add("puffer", "pufferfish.3mf", "pufferfish", "Pufferfish", "Legend Lee", "PETG",
    "Pufferfish — original", "Articulated squeeze-ball: hinged spike plates around a multi-body core, pulled by rubber bands. One leaky object of 10 — every slicer auto-repairs it.", ("warn", "1 leaky object"))
add("puffer3p", "pufferfish-p2s-threeplates.3mf", "pufferfish_threeplates", "Pufferfish", "Legend Lee", "PETG",
    "Pufferfish — 3-plate re-save", "Same 10 parts as the original (verified rotation-invariant), re-arranged across three plates for easier printing.", ("warn", "Same leaky part"))
add("puffer1c", "pufferfish-p2s-onecolor.3mf", "pufferfish_onecolor", "Pufferfish", "Legend Lee", "PETG",
    "Pufferfish — one-colour re-save", "Same parts, colour scheme flattened. A 1.3× scale is baked into mesh coords and cancelled by transforms — prints the same size.", ("warn", "Same leaky part"))
add("pikachu", "pikachu+more+resistant+one+color.3mf", "pikachu", "Pikachu Flexy", "B-Forge3D · v2", "PETG",
    "Pikachu Flexy Keychain", "Print-in-place flexy of 7 hinged bodies. This file is itself the fix — the reinforced single-colour v2 of a fragile original.", ("warn", "Minor defects"))
add("staryu", "Staryu_Starmie_Spin_Spin.3mf", "staryu_starmie", "Staryu & Starmie", "pythong · remix", "PLA",
    "Staryu & Starmie — original", "Two spinners on one bearing recipe, friction tuned by the diff_disc washer stack. Star heads carry 152 k duplicate faces — slicers discard them.", ("warn", "Dup-face defect"), reveals="staryu_dup", reveal_label="duplicate download")
add("staryu_dup", "Staryu_Starmie_Spin_Spin (1).3mf", "staryu_starmie", "Staryu & Starmie", "pythong · remix", "PLA",
    "Staryu & Starmie — copy (1)", "Byte-identical duplicate download of the original (same MD5). Safe to delete; kept here for completeness.", ("warn", "Duplicate file"), hide=True)
HG = "Idea2Item · Printables"
add("cone_pair_s", "cone-hourglass-pair-small.3mf", "cone_pair_small", "Hourglass · Cone", HG, "PETG",
    "Cone Pair Plate — 90 mm", "Built for you: solid + spiral on one plate — print this single file and the whole toy comes off the bed together. 100% infill on the solid, 15% on the spiral, brim on.", ("pass", "Built · both parts"))
add("cone_pair_d", "cone-hourglass-pair-dubbel.3mf", "cone_pair_dubbel", "Hourglass · Cone", HG, "PETG",
    "Cone Pair Plate — dubbel 180 mm", "Built for you: the double-height pair on one plate. 8.7:1 lever ratio at 180 mm — brim is mandatory.", ("pass", "Built · both parts"))
add("cone_solid_s", "cone-solid-small.stl", "cone_solid_small", "Hourglass · Cone", HG, "PETG",
    "Cone Solid — 90 mm", "Hourglass body with 7 helical slots + a central channel (mesh genus 8). 100% infill per the designer; lands on 7 first-layer islands — brim.", ("pass", "Clean"), mate="Cone Spiral — 90 mm (pair plate: cone-hourglass-pair-small.3mf)", pair="cone_pair_s")
add("cone_spiral_s", "cone-spiral-small.stl", "cone_spiral_small", "Hourglass · Cone", HG, "PETG",
    "Cone Spiral — 90 mm", "The smooth twisted piece (genus 0) that screws through the solid's slots. 15% gyroid infill.", ("pass", "Clean"), mate="Cone Solid — 90 mm", pair="cone_pair_s")
add("cone_solid_d", "cone-solid.stl", "cone_solid", "Hourglass · Cone", HG, "PETG",
    "Cone Solid — dubbel 180 mm", "Two hourglass cells stacked at constant Ø — same 7 slots per cell (mesh genus 15). 7.4:1 lever ratio — brim mandatory.", ("pass", "Clean"), mate="Cone Spiral — dubbel 180 mm (pair plate: cone-hourglass-pair-dubbel.3mf)", pair="cone_pair_d")
add("cone_spiral_d", "cone-spiral.stl", "cone_spiral", "Hourglass · Cone", HG, "PETG",
    "Cone Spiral — dubbel 180 mm", "Double-length spiral, same Ø41 body. 8.7:1 lever ratio — brim mandatory.", ("pass", "Clean"), mate="Cone Solid — dubbel 180 mm", pair="cone_pair_d")
add("pyr_pair_s", "pyramid-hourglass-pair-small.3mf", "pyramid_pair_small", "Hourglass · Pyramid", HG, "PETG",
    "Pyramid Pair Plate — 90 mm", "Built for you: the repaired solid + spiral on one plate — the complete toy in one job. Uses the fixed body, not the broken original.", ("pass", "Built · both parts"))
add("pyr_pair_d", "pyramid-hourglass-pair-dubbel.3mf", "pyramid_pair_dubbel", "Hourglass · Pyramid", HG, "PETG",
    "Pyramid Pair Plate — dubbel 180 mm", "Built for you: double-height pyramid pair on one plate. Brim mandatory at this height.", ("pass", "Built · both parts"))
add("pyr_solid_sf", "pyramid-solid-small-fixed.stl", "pyramid_solid_small_fixed", "Hourglass · Pyramid", HG, "PETG",
    "Pyramid Solid — 90 mm (fixed)", "The repaired body: zero-thickness pinch removed (2 fewer faces, watertight) — 7 slots + channel. Print this, not the original.", ("pass", "Repaired"), mate="Pyramid Spiral — 90 mm (pair plate: pyramid-hourglass-pair-small.3mf)", reveals="pyr_solid_so", reveal_label="original (pinch)", pair="pyr_pair_s")
add("pyr_solid_so", "pyramid-solid-small.stl", "pyramid_solid_small_orig", "Hourglass · Pyramid", HG, "PETG",
    "Pyramid Solid — 90 mm (original)", "Ships with a zero-thickness pinch: one duplicated triangle on a non-manifold edge. Superseded by the -fixed file — kept for reference.", ("warn", "Pinch defect"), hide=True)
add("pyr_spiral_s", "pyramid-spiral-small.stl", "pyramid_spiral_small", "Hourglass · Pyramid", HG, "PETG",
    "Pyramid Spiral — 90 mm", "Twisted square-base piece (genus 0) with the set's shared 7-lobe thread. 15% gyroid infill.", ("pass", "Clean"), mate="Pyramid Solid — 90 mm (fixed)", pair="pyr_pair_s")
add("pyr_solid_d", "pyramid-solid.stl", "pyramid_solid", "Hourglass · Pyramid", HG, "PETG",
    "Pyramid Solid — dubbel 180 mm", "Double-height slotted body, 7 slots per cell (mesh genus 19). 100% infill and a brim.", ("pass", "Clean"), mate="Pyramid Spiral — dubbel 180 mm (pair plate: pyramid-hourglass-pair-dubbel.3mf)", pair="pyr_pair_d")
add("pyr_spiral_d", "pyramid-spiral.stl", "pyramid_spiral", "Hourglass · Pyramid", HG, "PETG",
    "Pyramid Spiral — dubbel 180 mm", "Double-length spiral. 8.7:1 lever ratio — brim mandatory.", ("pass", "Clean"), mate="Pyramid Solid — dubbel 180 mm", pair="pyr_pair_d")
add("nuts", "montessori+nuts+and+bolts.3mf", "nuts_bolts", "Nuts & Bolts", "carnivalcamps", "PLA",
    "Montessori Nuts & Bolts", "Toddler counting toy: five jumbo bolts in 30 mm height steps (59–179 mm) sharing one chunky thread, plus a nut — every nut fits every bolt; print as many nuts as needed. The nut mesh leaks (slicer-repairable). Non-toxic filament, brim on the tall bolts.", ("warn", "Nut not watertight"))
add("held", "held-sphere.3mf", "held_sphere", "Designed here", "Claude · this session", "PLA",
    "Held Sphere", "A captive Ø19 ball in a geodesic strut cage: 120 Ø2.2 struts along subdivided-icosphere edges with joint spheres — fully triangulated, so it stays rigid at a third of the original shell's material (5.9 vs 16.5 cm³) while reading as a true sphere. Openings ≈Ø6 keep the ball captive (clearance 0.90 mm); it stands on a breakaway pip. Prints face-down; short struts self-support far better than the coarse version.", ("pass", "Designed · ready"))
add("held_chain", "held-sphere-chained.3mf", "held_chained", "Designed here", "Claude · this session", "PLA",
    "Held Sphere + Chain", "The pendant variant — every chain part articulates, nothing welded to the chain. A thin tag plate on the cage carries a closed hole + bed slot; link 0 pierces both perpendicular and hangs completely free (capture proven by lift test, 0.58 mm running clearance). Ten more links follow at ≥0.83 mm joints. The tag becomes the top when it hangs. Prints flat in one job.", ("pass", "Designed · ready"), mate="Held Sphere (chainless version)")
add("chain2x", "chain-test-5seg-2x.3mf", "chain_test_2x", "Designed here", "Claude · this session", "PLA",
    "Chain Test — 5 Links · 2×", "The same chain at double scale: 1.5″ links, 0.25″ (Ø6.35 mm) cross-section, 1.28 mm joint clearance, 24.4 mm² bed contact per link — comfortably brimless. A chunkier feel and a stronger test of the interlock.", ("pass", "Designed · ready"))
add("chain", "chain-test-5seg.3mf", "chain_test", "Designed here", "Claude · this session", "PLA",
    "Chain Test — 5 Links", "Print-in-place chain: five 0.75″ stadium links with 0.125″ round cross-section, alternating ±45° tilt in a gentle coil so every link self-supports. Verified: 0.74 mm clearance at every joint, threading proven by section intersection. Brim optional: each link puts a measured 9.6 mm² on the bed — enough to try brimless on textured PEI; a detached link is the failure mode if it lets go.", ("pass", "Designed · ready"))
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
 "nuts": "5 h 32 m · 228.4 g",
 "held": "43 m · 8.9 g — bridged struts; tree supports optional", "chain2x": "32 m · 10.6 g — brimless-friendly", "held_chain": "60 m · 13.3 g — cage struts bridge; tree supports optional", "chain": "9 m · 2.3 g",
}
models_js = {}
cards = []
def _mslug(f): return _re.sub(r"[^a-z0-9]+", "_", f.lower().rsplit(".", 1)[0]).strip("_")
for c in C:
    e = dict(manifest[c["glb"]])
    e["file"] = c["file"]
    ms = _mslug(c["file"])
    mj = os.path.join(MODELS_DIR, "meta", ms, "meta.json")
    md = json.load(open(mj)) if os.path.exists(mj) else {}
    base = f"models/meta/{ms}/"
    if md.get("cover"): e["cover"] = base + md["cover"]
    if md.get("photos"): e["photos"] = [base + p for p in md["photos"]]
    c["_md"], c["_base"] = md, base
    models_js[c["cid"]] = [e]
    d = e["dims"]
    spec = f'{d[0]}×{d[1]}×{d[2]} mm · {e["parts"]} part{"s" if e["parts"]>1 else ""} · {e["tris_full"]:,} tris'
    sl = SLICE.get(c["cid"])
    spec += f'<br>P2S slice: {sl}' if sl else ""
    vclass, vlabel = c["v"]
    md = c.get("_md") or {}
    metabox = ""
    if md:
        rows = "".join(
            f'<div class="mrow"><dt>{k}</dt><dd>{md[k]}</dd></div>'
            for k in ("Designer", "License", "Origin", "ProfileTitle", "Application",
                      "CreationDate", "slicer_weight_g", "slicer_time") if k in md)
        desc = f'<p class="mdesc">{md["Description"]}</p>' if md.get("Description") else ""
        gal = ""
        if md.get("photos"):
            gal = '<div class="gal">' + "".join(
                f'<img src="{c["_base"]}{p}" loading="lazy" data-cid="{c["cid"]}" alt="designer photo">'
                for p in md["photos"]) + "</div>"
        metabox = (f'<details class="metabox"><summary>3MF metadata'
                   f'{" · " + str(len(md.get("photos", []))) + " photos" if md.get("photos") else ""}</summary>'
                   f'<dl class="mrows">{rows}</dl>{desc}{gal}</details>')
    cards.append(f'''
<article class="card{' superseded' if c.get('hide') else ''}" data-cid="{c['cid']}" id="card-{c['cid']}">
  <div class="photo">
    <div class="view" data-models="{c['cid']}"></div>
    <span class="pill {vclass}">{vlabel}</span>
    <div class="chips"></div>
    <div class="dimtag"></div>
  </div>
  <div class="body">
    <p class="eyebrow">{c['family']} · {c['designer']}</p>
    <h3>{c['title']} <span class="mat">{c['mat']}</span></h3>
    <p class="principle">{c['blurb']}</p>
    {f'<p class="mate">mates with {c["mate"]}' + (f' — <a class="pairlink" href="#card-{c["pair"]}">print both together ↓</a>' if c.get('pair') else '') + '</p>' if c.get('mate') else ''}
    <p class="specline">{spec}</p>
    <div class="actions">
      <button class="print" data-card="{c['cid']}">Open in Bambu Studio</button>
      <a class="savelink" href="models/{c['file']}" download title="{c['file']}">save · {c['file']}</a>
      {f'<button class="showorig" data-target="{c["reveals"]}" data-show-label="show {c["reveal_label"]}" data-hide-label="hide {c["reveal_label"]}">show {c["reveal_label"]}</button>' if c.get('reveals') else ''}
    </div>
    <div class="notes" data-cid="{c['cid']}"></div>
    {metabox}
  </div>
</article>''')

fixes = "".join(f'<li><strong>{t}</strong><span>{d}</span></li>' for t, d in FIXES)
compat = "".join(f'<li><strong><span class="dot {c}"></span>{t}</strong><span>{d}</span></li>' for c, t, d in COMPAT)
BUILT = [
 ("cone-hourglass-pair-small.3mf", "5.6", "Hourglass · cone", "pass", "built here — both mating parts, one plate"),
 ("cone-hourglass-pair-dubbel.3mf", "6.5", "Hourglass · cone", "pass", "built here — both mating parts, one plate"),
 ("pyramid-hourglass-pair-small.3mf", "6.3", "Hourglass · pyramid", "pass", "built here — fixed solid + spiral, one plate"),
 ("pyramid-hourglass-pair-dubbel.3mf", "6.9", "Hourglass · pyramid", "pass", "built here — both mating parts, one plate"),
 ("voro_sphere_2-fixed.stl", "4.1", "One-off experiments", "pass", "repaired here — normals flipped, scaled to Ø60 mm"),
]
rows = "".join(
    f'<tr><td class="mono">{n}</td><td class="mono num">{s}</td><td>{fam}</td>'
    f'<td><span class="dot {v}"></span>{note}</td></tr>'
    for n, s, fam, v, note in list(ALLFILES) + BUILT)

tpl = open(os.path.join(HERE, "template_local.html")).read()
html = (tpl.replace("{{CARDS}}", "\n".join(cards))
        .replace("{{FIXES}}", fixes).replace("{{COMPAT}}", compat).replace("{{ROWS}}", rows)
        .replace("{{MODELS}}", json.dumps(models_js)))
out = os.path.expanduser("~/Code/My3DPrints/index.html")
open(out, "w").write(html)
print("wrote", out, len(html) // 1024, "KB,", len(cards), "cards")
