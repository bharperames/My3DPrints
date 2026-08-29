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
