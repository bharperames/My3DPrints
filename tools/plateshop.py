#!/usr/bin/env python3
"""Pack an order onto build plates and write one 3MF per plate.

An order is a list of (part, params, qty). Each line resolves to a 3MF on
disk; the packer measures its footprint, lays the copies out on as many
plates as it takes, and writes each plate as its own Bambu project, zipped
together.

Packing is MaxRects best-short-side-fit, ported from KlipKlopMaker's
js/plate_pack.js: largest area first, 0/90 rotation, one fresh bin per
plate with leftovers rolling onto the next. It is deterministic, so the
same order always produces the same layout.

Nothing is packed that has not been measured, and a part that cannot fit
the bed in either orientation is refused by name rather than silently
dropped off the edge.
"""
import io
import json
import os
import zipfile

import numpy as np
import trimesh

import catalog

# Packing constants and algorithm are ported from KlipKlopMaker's
# js/plate_pack.js, which is field-tested on this same printer: MaxRects with
# best-short-side-fit, largest-area-first, 0/90 rotation. Shelf packing was
# the first cut here and wastes noticeably more on mixed part sizes.
MARGIN = 5.0        # inset from every plate edge -> 246 x 246 usable
GAP = 3.0           # between parts; items are inflated by it, then deflated


class MaxRects:
    """Free-rectangle bin. Splits on place, prunes contained rects."""

    def __init__(self, w, d):
        self.free = [dict(x=0.0, y=0.0, w=w, d=d)]

    def find(self, w, d, rotate=True):
        best = None
        for f in self.free:
            for pw, pd, rot in ((w, d, 0), (d, w, 90)) if rotate else ((w, d, 0),):
                if pw > f["w"] + 1e-9 or pd > f["d"] + 1e-9:
                    continue
                short = min(f["w"] - pw, f["d"] - pd)
                long_ = max(f["w"] - pw, f["d"] - pd)
                if best is None or (short, long_) < (best["short"], best["long"]):
                    best = dict(x=f["x"], y=f["y"], w=pw, d=pd, rot=rot,
                                short=short, long=long_)
        return best

    def place(self, r):
        out = []
        for f in self.free:
            if (r["x"] >= f["x"] + f["w"] - 1e-9
                    or r["x"] + r["w"] <= f["x"] + 1e-9
                    or r["y"] >= f["y"] + f["d"] - 1e-9
                    or r["y"] + r["d"] <= f["y"] + 1e-9):
                out.append(f)
                continue
            if r["x"] > f["x"]:
                out.append(dict(f, w=r["x"] - f["x"]))
            if r["x"] + r["w"] < f["x"] + f["w"]:
                out.append(dict(f, x=r["x"] + r["w"],
                                w=f["x"] + f["w"] - (r["x"] + r["w"])))
            if r["y"] > f["y"]:
                out.append(dict(f, d=r["y"] - f["y"]))
            if r["y"] + r["d"] < f["y"] + f["d"]:
                out.append(dict(f, y=r["y"] + r["d"],
                                d=f["y"] + f["d"] - (r["y"] + r["d"])))
        # prune: without this the free list grows without bound
        keep = []
        for i, a in enumerate(out):
            if not any(i != j and a["x"] >= b["x"] - 1e-9
                       and a["y"] >= b["y"] - 1e-9
                       and a["x"] + a["w"] <= b["x"] + b["w"] + 1e-9
                       and a["y"] + a["d"] <= b["y"] + b["d"] + 1e-9
                       for j, b in enumerate(out)):
                keep.append(a)
        self.free = keep
        return r


def pack(items, bed=(256.0, 256.0), height=256.0, margin=MARGIN, gap=GAP,
         rotate=True):
    """Pack per-copy items onto plates.

    Returns (plates, oversized). Coordinates are plate-centred, which is
    what a 3MF build item wants. Oversized parts are refused by name and
    reason rather than dropped off the edge.
    """
    uw, ud = bed[0] - 2 * margin, bed[1] - 2 * margin
    queue, oversized = [], []
    for it in items:
        w, d = it["w"] + gap, it["d"] + gap
        fits = (w <= uw + 1e-9 and d <= ud + 1e-9) or (
            rotate and d <= uw + 1e-9 and w <= ud + 1e-9)
        if not fits:
            oversized.append(dict(it, reason="footprint"))
        elif it.get("h", 0) > height + 1e-9:
            oversized.append(dict(it, reason="height"))
        else:
            queue.append(dict(it, w=w, d=d))
    queue.sort(key=lambda i: (-(i["w"] * i["d"]), -max(i["w"], i["d"]),
                              str(i["key"])))
    groups, order = {}, []
    for it in queue:
        g = it.get("group", "")
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(it)
    plates = []
    for g in order:
        remaining = groups[g]
        while remaining:
            bin_ = MaxRects(uw, ud)
            placed, leftover = [], []
            for it in remaining:
                spot = bin_.find(it["w"], it["d"], rotate)
                if spot is None:
                    leftover.append(it)
                    continue
                bin_.place(spot)
                # pw/pd are the footprint AS PLACED, so they swap with a
                # 90 deg rotation. Reporting the unrotated pair (which the
                # reference implementation does) leaves x/y describing one
                # box and w/d another, and any preview drawn from them puts
                # rotated parts through their neighbours.
                placed.append(dict(
                    it, rot=spot["rot"], pw=spot["w"] - gap,
                    pd=spot["d"] - gap,
                    x=spot["x"] + spot["w"] / 2 - uw / 2,
                    y=spot["y"] + spot["d"] / 2 - ud / 2))
            if not placed:
                break
            used = sum(p["pw"] * p["pd"] for p in placed)
            plates.append(dict(index=len(plates) + 1, group=g, items=placed,
                               used=used, util=used / (uw * ud)))
            remaining = leftover
    return plates, oversized


def describe(plates, oversized):
    out = []
    for p in plates:
        n = {}
        for it in p["items"]:
            n[it["name"]] = n.get(it["name"], 0) + 1
        out.append(f"Plate {p['index']}"
                   + (f" ({p['group']} only)" if p["group"] else "")
                   + f" — {len(p['items'])} parts, {p['util']*100:.0f}% of the "
                     f"usable area")
        out += [f"    {c} x {k}" for k, c in sorted(n.items())]
    for o in oversized:
        out.append(f"  ! {o['name']} does not fit the plate ({o['reason']}) "
                   f"— print it alone")
    return "\n".join(out)


_BODIES = {}


def load_bodies(path):
    """Every body of a file, in world space, keyed by its geometry name."""
    if path not in _BODIES:
        src = trimesh.load(path, force="scene")
        out = []
        for node in src.graph.nodes_geometry:
            tf, gk = src.graph[node]
            g = src.geometry[gk].copy()
            g.apply_transform(tf)
            out.append((gk, g))
        _BODIES[path] = out
    return [(gk, g.copy()) for gk, g in _BODIES[path]]


def is_assembly(bodies):
    """Do the bodies share space? Then they were positioned on purpose.

    A dice orb's die sits inside its cage and the two must move together.
    A downloaded file's objects usually sit side by side on the designer's
    plate, and moving them together makes one 388 mm part that fits no bed.
    """
    for i, (_, a) in enumerate(bodies):
        for _, b in bodies[i + 1:]:
            if (a.bounds[0] < b.bounds[1]).all() and \
               (b.bounds[0] < a.bounds[1]).all():
                return True
    return False


def pieces(path):
    """What the packer places: whole assemblies, or one object at a time."""
    bodies = load_bodies(path)
    if len(bodies) < 2 or is_assembly(bodies):
        return [[gk for gk, _ in bodies]]
    return [[gk] for gk, _ in bodies]


def _extent(bodies, keys):
    sel = [g for gk, g in bodies if gk in keys]
    lo = np.min([g.bounds[0] for g in sel], axis=0)
    hi = np.max([g.bounds[1] for g in sel], axis=0)
    return dict(w=float(hi[0] - lo[0]), d=float(hi[1] - lo[1]),
                h=float(hi[2] - lo[2]))


def order_items(order):
    """Resolve an order into per-copy items, generating what is missing.

    order: [{part: id, params: {...}, qty: n}]
    """
    items, reports = [], {}
    for line in order:
        part = catalog.find(line["part"])
        params = line.get("params") or {}
        path, rep = catalog.ensure(part, params)
        m = catalog.measure(path)
        bodies = load_bodies(path)
        groups = pieces(path)
        one = len(groups) == 1
        # report the piece that gets placed, not the designer's whole plate:
        # a file laid out 388 mm wide is two 81 mm halves to this shop
        shown = m if one else max(
            (_extent(bodies, set(g)) for g in groups),
            key=lambda e: e["w"] * e["d"])
        reports[part["id"]] = dict(rep, **shown, file=os.path.basename(path),
                                   pieces=len(groups))
        for i in range(int(line.get("qty", 1))):
            for j, keys in enumerate(groups):
                items.append(dict(
                    key=part["id"], path=path, copy=i, bodies=keys,
                    name=(part["name"] if one
                          else f"{part['name']} ({j + 1}/{len(groups)})"),
                    assembly=one, **_extent(bodies, set(keys))))
    return items, reports


def arranged_scene(plates, pitch=300.0, simplify=60_000):
    """Every plate, laid out side by side, as one scene.

    The same placement maths the exporter uses, so the preview is the plate —
    not a diagram of it. Meshes are decimated only if the total gets heavy,
    which keeps a 3MF full of library geometry from stalling the browser.
    """
    cols = max(1, int(np.ceil(np.sqrt(len(plates)))))
    # Load and orient everything first, decimate, and only then compute each
    # part's drop. Decimation moves vertices, so a mesh dropped to z=0 before
    # it is simplified comes back a hair proud and reads as floating.
    staged, total = [], 0
    for n, p in enumerate(plates):
        ox, oy = (n % cols) * pitch, -(n // cols) * pitch
        used = {}
        for it in p["items"]:
            keys = set(it.get("bodies") or [])
            bodies = [(gk, g) for gk, g in load_bodies(it["path"])
                      if not keys or gk in keys]
            if it["rot"]:
                R = trimesh.transformations.rotation_matrix(
                    np.radians(it["rot"]), [0, 0, 1])
                for _, g in bodies:
                    g.apply_transform(R)
            k = used.get(it["key"], 0) + 1
            used[it["key"]] = k
            total += sum(len(g.faces) for _, g in bodies)
            staged.append((p["index"], it, k, ox, oy, bodies))
    if total > simplify:
        for _, _, _, _, _, bodies in staged:
            for i, (gk, g) in enumerate(bodies):
                try:
                    bodies[i] = (gk, g.simplify_quadric_decimation(
                        face_count=max(200,
                                       int(len(g.faces) * simplify / total))))
                except Exception:
                    pass
    sc = trimesh.Scene()
    for idx, it, k, ox, oy, bodies in staged:
        lo = np.min([g.bounds[0] for _, g in bodies], axis=0)
        hi = np.max([g.bounds[1] for _, g in bodies], axis=0)
        ctr = (lo + hi) / 2
        for gk, g in bodies:
            # A generated part is one assembly: its bodies keep their relative
            # heights, since a die sits inside its cage by design. A file off
            # disk is usually a set of independent objects, and some ship with
            # them at different heights — those each get their own drop, or
            # they print in mid-air.
            dz = -lo[2] if it.get("assembly", True) else -g.bounds[0][2]
            g.apply_translation([it["x"] - ctr[0] + ox,
                                 it["y"] - ctr[1] + oy, dz])
            sc.add_geometry(g, geom_name=f"p{idx}_{it['key']}_{k}_{gk}")
    return sc, cols


def build_preview(plates, out_glb):
    sc, cols = arranged_scene(plates)
    sc.export(out_glb)
    return dict(cols=cols, plates=len(plates),
                tris=sum(len(g.faces) for g in sc.geometry.values()))


def build_zip(plates, out_zip, printer="P2S", oversized=None):
    """Write one Bambu project per plate, zipped, and return a manifest.

    Placements are plate-centred. Every part is baked at its offset with an
    identity build transform, so embed_settings' single plate-centring
    translation moves the whole plate together rather than stacking the
    parts on the origin — and its bed-drop keeps the lowest one on z=0.

    KlipKlopMaker deliberately ships geometry-only 3MFs so the slicer keeps
    the user's presets. We do the opposite on purpose: this shop targets one
    known machine, and the embedded profile is what makes the brim and
    support choices survive the trip into Studio.
    """
    from embed_settings import embed
    manifest = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in plates:
            sc = trimesh.Scene()
            used, cm3 = {}, 0.0
            for it in p["items"]:
                # A piece is placed as a unit. For an assembly that is every
                # body in the file — placing them separately would re-centre
                # each on the same spot and stand the dice orb's die on the
                # bed instead of on its sleeve inside the cage. For a file of
                # independent objects it is one object.
                keys = set(it.get("bodies") or [])
                bodies = [(gk, g) for gk, g in load_bodies(it["path"])
                          if not keys or gk in keys]
                if it["rot"]:
                    R = trimesh.transformations.rotation_matrix(
                        np.radians(it["rot"]), [0, 0, 1])
                    for _, g in bodies:
                        g.apply_transform(R)
                lo = np.min([g.bounds[0] for _, g in bodies], axis=0)
                hi = np.max([g.bounds[1] for _, g in bodies], axis=0)
                ctr = (lo + hi) / 2
                n = used.get(it["key"], 0) + 1
                used[it["key"]] = n
                for gk, g in bodies:
                    dz = -lo[2] if it.get("assembly", True) else -g.bounds[0][2]
                    g.apply_translation([it["x"] - ctr[0],
                                         it["y"] - ctr[1], dz])
                    cm3 += float(g.volume) / 1000
                    sc.add_geometry(g, geom_name=f"{it['key']}_{n}_{gk}")
            # solid volume, not print weight: sparse infill lands well
            # under this, so quoting grams here would flatter the number
            stem = (f"plate_{p['index']:02d}"
                    + (f"_{p['group']}" if p["group"] else "")
                    + f"_{len(p['items'])}parts_{round(cm3)}cm3")
            tmp = os.path.join(catalog.CUSTOM, f".{stem}.3mf")
            sc.export(tmp)
            embed(tmp, brim=False)
            with open(tmp, "rb") as f:
                z.writestr(f"{stem}.3mf", f.read())
            os.remove(tmp)
            manifest.append(dict(plate=p["index"], group=p["group"],
                                 parts=len(p["items"]),
                                 util=round(p["util"], 3),
                                 solid_cm3=round(cm3, 1),
                                 file=f"{stem}.3mf",
                                 items=[dict(key=i["key"], name=i["name"],
                                             x=round(i["x"], 1),
                                             y=round(i["y"], 1),
                                             rot=i["rot"], w=round(i["pw"], 1),
                                             d=round(i["pd"], 1),
                                             h=round(i["h"], 1))
                                        for i in p["items"]]))
        z.writestr("plates.json", json.dumps(manifest, indent=1))
        z.writestr("README.txt",
                   "My Print Shop — one 3MF per plate, Bambu P2S.\n\n"
                   + describe(plates, oversized or [])
                   + "\n\nEach file carries the P2S machine, 0.20mm Standard\n"
                     "and PLA Basic presets, supports off. Open a plate and\n"
                     "slice; the layout is already arranged.\n\n"
                     "Volumes in the filenames are solid material. A sparse\n"
                     "infill prints well under that — slice for the real\n"
                     "figure.\n")
    with open(out_zip, "wb") as f:
        f.write(buf.getvalue())
    return manifest


if __name__ == "__main__":
    import sys
    order = json.loads(sys.argv[1]) if len(sys.argv) > 1 else [
        {"part": "mont_double", "qty": 2},
        {"part": "dice_orb", "qty": 1},
    ]
    items, reports = order_items(order)
    plates, rejected = pack(items)
    out = os.path.join(catalog.CUSTOM, "shop-order.zip")
    man = build_zip(plates, out, oversized=rejected)
    print(describe(plates, rejected))
    print(json.dumps({"plates": len(plates), "zip": out,
                      "files": [m["file"] for m in man]}, indent=1))
