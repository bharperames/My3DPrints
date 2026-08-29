#!/usr/bin/env python3
"""Assemble ~/Code/My3DPrints/index.html.

The page used to carry a hand-written card per design alongside a separate
shop list, which meant two descriptions of the same objects that could drift
apart. There is one catalog now, rendered in the browser from /shop/catalog,
and what a human knows about a design lives in designs.py where the catalog
reads it. What is left to build here is the review material: the fixes, the
compatibility notes and the file ledger.
"""
import json, os
from build_page import FIXES, ALLFILES, COMPAT   # side effect: also rebuilds artifact html

HERE = os.path.dirname(os.path.abspath(__file__))

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
html = (tpl.replace("{{FIXES}}", fixes).replace("{{COMPAT}}", compat)
        .replace("{{ROWS}}", rows).replace("{{MODELS}}", json.dumps({})))
out = os.path.expanduser("~/Code/My3DPrints/index.html")
open(out, "w").write(html)
print("wrote", out, len(html) // 1024, "KB")
