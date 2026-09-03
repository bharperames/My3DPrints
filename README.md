# My3DPrints — My Print Shop

A local print shop: it generates parts to order, packs them onto build
plates, and hands back one 3MF per plate — plus a library of every printable
file on disk and a card per design carrying the measurements behind it.
One machine for now (Bambu P2S), declared in `tools/catalog.py`.
**Harness only — `models/` (the data plane) is untracked.**

Two tabs:

- **Catalog** — every design, as a card with a live 3D preview: a part
  generated to order, a part with options, and a file found in `~/Downloads`
  are the same kind of thing here and render through the same card. Search
  or filter, set a quantity, and it goes on the plate; the bill of materials
  and the plate view update as you go. Parts whose sizes must agree are sold
  as *kits* on one card: the chain's cross-section is also the clasp's mouth
  and the jump ring's section, so one dial drives all three. The plate view
  is the arranged geometry itself, exported by the same code that writes the
  3MFs.
- **About** — the vocabulary the measurements use, with a diagram each, plus
  the compatibility notes, the fixes and the file ledger.

What a human knows about a design — designer, what it does, the geometry
verdict — lives in `tools/designs.py` and is folded into the catalog entry
for the file it describes, so a card and a bill-of-materials row cannot
disagree about what a part is. Previews are built by `tools/previews.py`,
one small decimated GLB per entry, cached on the source's size and mtime.

Every entry carries a semver and a date. The version is declared; the date is
read from the last commit touching its generator. An amber badge means the
cached file predates the design and will rebuild when ordered.

## What is in `models/`

Four kinds of thing, and only two of them matter if you lose the rest.

| | what it is | rebuildable |
|---|---|---|
| `*.3mf`, `*.stl` (top level) | **the shelf** — the designs themselves, 41 of the catalog's 50 parts | no |
| `meta/` | designer photos and metadata unpacked out of the 3MFs | from the shelf |
| `custom/` | **generated parts** — what a generator built for one set of dial settings, named after them (`chain-N48-L19-D3.25-F0.6.3mf`), plus exported plates | yes, on demand |
| `glb/prev/`, `previews.json`, `versions.json` | card previews and the indexes the page reads | `make build` |

Nine of the fifty parts have a generator and no file until they are ordered:
wrench, dice orb, double nut, base plate, clasp, jump ring, chain, sphere
stand, geodesic cage. Ordering one runs its script with the dials you chose
and caches the result under a filename made from those dials — so a 48-link
chain and a 40-link chain are two files, and changing a dial makes a third.
A cached file is rebuilt when its generator is newer than it, so a fix to a
generator reaches the next order.

The other forty-one are files on the shelf. Nothing is generated for them;
they are served as they are.

`~/Downloads` is **not** read unless you press *Import from Downloads* — it
used to be scanned on every page load, which quietly turned every plate the
shop exported into a new "design" in its own catalog.

`make clean-cache` prints what the caches cost; `make clean-cache-yes`
clears them and `make build` puts them back.

## Measuring on the real thing

Nothing here trades quality away until evidence from the real target says
it must — and a simulated environment is not that evidence.

Preview geometry was capped because headless Chromium reported 11–24 fps
with two dozen cards on screen. Headless Chromium falls back to SwiftShader
and rasterizes on the CPU; read `UNMASKED_RENDERER_WEBGL` and it says so.
The same page on the GPU it actually runs on (`--use-angle=metal
--enable-gpu`) holds the display's 120 Hz with every mesh at full
resolution. The cap bought nothing and cost a small part its shape: sharing
the budget in proportion cut the wrench from 4,736 faces to 1,086, and a
prismatic part without its corners renders as a ribbon.

Previews are the real geometry now. The budgeting code is still there and
still shares max-min if a budget is ever set, because the proportional rule
was wrong independently of whether any cap was needed.

The slicing harness had the same fault from the other direction: it loaded
a system process preset that silently overrode `reduce_crossing_wall`, so
every travel figure measured settings nobody prints with. Check what the
harness is doing before believing what it reports.

And when the evidence says there is no problem, stop measuring. Having
established there was no practical cap, hunting for the theoretical one is
looking for a number to justify a decision already made.

## Before you print

A part this shop generates is gated by its generator — it will not emit a
design whose overhangs, clearances or stresses fail. A file somebody else
designed carries no such promise: it arrives in whatever orientation its
author saved it, and the first sign that it will not print is spaghetti.

So every catalog entry is measured the way a slicer would: layer against
layer, counting the area that has nothing under it, plus how much of it
touches the bed and how slender it stands. Cards say what a part needs
before it is ordered.

Face normals alone cannot answer this and the first version of the check
got it wrong: the underside of a cage strut points straight down with open
air beneath it and prints perfectly, carried by the previous layer of its
own strut. Counting normals scored the dice orb at 4,700 mm2 unsupported —
a part that prints clean on a brim. Comparing each layer with the one below
scores it at 347, which is the number that matches what came off the bed.

Calibrated against parts whose outcome is known: the wrench (printed
perfect) reads clean, the dice orb (failed bare, worked with supports and a
brim) asks for supports, and the Mini Fidget Ball asks for a brim — its
disc finished while its ball, on 12 mm2 of contact, came loose part-way up.
`orient.py FILE` searches the orientations a part can rest in when the
question is which way up.

## Staying current

Two kinds of part live here — files on the shelf, and parts a generator
builds to order — and every place one is cached is a place it can go stale.
It has, four times: a built 3MF returned forever, meshes held in memory
against a path, a library index frozen at process start, and a server
running code from before a fix. Each was invisible from outside; the shop
looked like it was working.

The rule is that **nothing serves geometry older than the code that makes
it**, and every cache states what invalidates it:

| what is held | invalidated by |
|---|---|
| `custom/*.3mf`, a part built to order | its generator's mtime, and `embed_settings.py` |
| meshes held in memory while packing | the file's size and mtime |
| the library index | the shelf and `imported.json` |
| the shop's code inside a running server | any `tools/*.py` it depends on, reloaded in place |
| a preview in the browser's cache | the URL carries a tag derived from the source |
| previews and the version ledger | the source file's size and mtime |

So editing a generator is enough: the next order rebuilds the part, reloads
the code, and re-reads the mesh, with no restart and nothing to remember.
`tests/test_freshness.py` drives that whole path.

What a plate *is* travels with it. Every exported 3MF carries `PARTS.txt`
and `Metadata/print_shop.json` naming each design with its version and
fingerprint, and a single-design plate puts the version in its filename —
so "is this the latest?" is answered by reading the file rather than by
measuring its mesh.

## Run

```
make serve   # http://localhost:8742   (stop / open / log)
make build   # re-run the whole pipeline (also: the page's Rebuild button)
make test    # unit tests (tests/: generators, gates, audits, embedding)
```

## Architecture

Three layers:

**1. Pipeline (`tools/`)** — idempotent stages, each re-proving invariants:

| Stage | Role |
|---|---|
| `build_designs.py` | regenerates the in-session designs (geodesic cage, chains, chainmail pendant); FCL clearances, ray-escape captivity and threading re-asserted every run |
| `ease_spirals.py` | derives `-eased` spirals (0.05–0.15 mm lead-in) and rebuilds the hourglass pair plates |
| `extract_meta.py` | unpacks 3MF-embedded designer photos/metadata to `models/meta/<slug>/` (never overwrites — custom covers survive) |
| `previews.py` | one decimated GLB per catalog entry, cached on the source's size and mtime; a preview the decimator cannot bring under budget is recorded as such rather than passed off as one that met it |
| `designs.py` | the curated designs: designer, what it does, the geometry verdict — matched to a catalog entry by filename |
| `catalog.py` | the one list of what can be printed: kits, parts, printers, and each design's semver — the version is declared, the date is read from git so it cannot drift |
| `plateshop.py` | MaxRects plate packing (ported from KlipKlopMaker's `js/plate_pack.js`) and the multi-plate 3MF zip |
| `gen_sphere_stand.py` | sphere stand, ported from the Sphere Stand Generator as one revolved profile |
| `build_local.py` | renders `index.html` from `template_local.html` with the review material (compatibility, fixes, file ledger); the catalog itself is fetched live from `/shop/catalog` |
| `gen_chain.py` / `gen_cage.py` / `gen_dice_cage.py` / `gen_spiral.py` / `gen_clasp.py` / `gen_montessori.py` | on-demand generators; refuse to emit until verification passes (gen_spiral simulates the full screw-in path with FCL; gen_clasp checks flexure strain against PLA's elastic budget; gen_montessori casts its thread from the designer's own nut and proves it by screwing the real bolt in) |
| `embed_settings.py` | stamps generated 3MFs as Bambu projects with the P2S presets + outer brim baked in |

**2. Server (`serve.py`)** — stdlib only; static files plus:
`/open` (hand a model to Bambu Studio), `/notes` (print log →
`models/notes.json`), `/rebuild` (run the pipeline), `/generate`
(one part, cached by parameter key), `/shop/catalog`, `/shop/layout`
(pack an order, returns the plate placements the exporter will use),
`/shop/build` (write the zip) and `/shop/scan` (index the library).

**3. Frontend (`index.html`, generated)** — no framework. One shared WebGL
canvas scissor-renders every card viewport (scroll-synced); GLBs lazy-load;
parametric cards mirror the generator math in JS for instant slider feedback
(live captivity warnings) while downloads always come from the server
generator. Per card: designer-photo overlay, 3MF metadata + gallery, print
notes, "show original" toggles for superseded files, pair-plate links, a
true-scale US quarter, graph-paper axis mode (inch rulings), and a
fullscreen lightbox.

## Principle

Nothing on a card is decorative: verdicts come from mesh measurement
(watertightness, genus, clearances), slice numbers from real BambuStudio CLI
runs calibrated against the actual printer (mass ±6%; time reads low by
8–25%, growing with print length), material badges from measured geometry
over designer defaults, and every generated or repaired file re-proves its
invariants before it reaches the user.

## Not committed

`models/` — source 3MF/STLs, `-fixed`/`-eased` derivatives, pair plates,
`glb/prev/` card previews, `previews.json` their index, `meta/` photos, `custom/` parametric output, `notes.json`.
