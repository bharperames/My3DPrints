# My3DPrints

A local "Fidget Shelf": scans toy-print 3MF/STLs, validates their geometry,
and serves a dark-mode card index with live 3D previews, parametric
generators, calibrated slicer estimates, print notes, and one-click hand-off
to Bambu Studio. **Harness only — `models/` (the data plane) is untracked.**

## Run

```
make serve   # http://localhost:8742   (stop / open / log)
make build   # re-run the whole pipeline (also: the page's Rebuild button)
```

## Architecture

Three layers:

**1. Pipeline (`tools/`)** — idempotent stages, each re-proving invariants:

| Stage | Role |
|---|---|
| `build_designs.py` | regenerates the in-session designs (geodesic cage, chains, chainmail pendant); FCL clearances, ray-escape captivity and threading re-asserted every run |
| `ease_spirals.py` | derives `-eased` spirals (0.05–0.15 mm lead-in) and rebuilds the hourglass pair plates |
| `extract_meta.py` | unpacks 3MF-embedded designer photos/metadata to `models/meta/<slug>/` (never overwrites — custom covers survive) |
| `make_glbs.py` | decimated ≤180k-tri GLB previews + `manifest.json` |
| `build_local.py` | renders `index.html` from `template_local.html`; also the knowledge base: card analyses, materials, calibrated slice numbers, pair/supersede links |
| `gen_chain.py` / `gen_cage.py` | on-demand parametric generators; refuse to emit until verification passes |

**2. Server (`serve.py`)** — stdlib only; static files plus:
`/open` (hand a model to Bambu Studio), `/notes` (print log →
`models/notes.json`), `/rebuild` (run the pipeline), `/generate`
(parametric chain/cage, cached by parameter key, returns verified metrics).

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
`glb/` previews, `meta/` photos, `custom/` parametric output, `notes.json`.
