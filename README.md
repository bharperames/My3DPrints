# My3DPrints

A local "Fidget Shelf": scans ~/Downloads for toy-print 3MF/STL files, validates their
geometry, and builds a dark-mode card index with live 3D previews, real slicer
estimates, print notes, and one-click hand-off to Bambu Studio.

**This repo holds the harness only** — model geometry (`models/`) is intentionally
untracked for now.

## Running

```
make serve   # http://localhost:8742  (make stop / make open / make log)
```

`serve.py` serves the page and provides two endpoints the page depends on:

- `GET /open?f=<file>` — opens `models/<file>` in Bambu Studio (`open -a BambuStudio`)
- `GET|POST /notes` — per-card print notes, persisted to `models/notes.json`

## Pipeline (tools/)

| Script | Role |
|---|---|
| `index_3mf.py` | scan Downloads, validate meshes with trimesh (watertight, genus, dup faces), extract embedded thumbnails |
| `make_glbs.py` | export decimated (≤180k tri) colored GLB previews + `models/manifest.json` |
| `build_designs.py` | parametric parts designed in-session (captive held-sphere, 45° print-in-place chain) with clearance/threading verification |
| `build_page.py` | curated per-design analysis data; run directly to build the shareable artifact page |
| `build_local.py` | renders `index.html` from `template_local.html` + manifest + analysis data |
| `render_pairs.py` | side-by-side render of mating hourglass pairs |

Python deps live in a venv (trimesh, numpy, scipy, shapely, rtree, manifold3d,
python-fcl, pillow, matplotlib, fast-simplification). Slicing uses the BambuStudio
CLI via the 3d-print-check skill's `bambu_slice.mjs`.

## Pages

- `index.html` — the card index (generated; committed for convenience)
- `guide.html` — P2S Field Guide: materials, geometry risk gates, settings recipes,
  PETG failure chain, 3MF portability notes
- `vendor/` — vendored three.js (page works offline)

## Not yet committed

`models/` — original 3MFs/STLs, decimated GLB previews, `manifest.json`, and
`notes.json` (print log). A future iteration will add curated models.
