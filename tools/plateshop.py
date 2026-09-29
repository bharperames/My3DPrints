#!/usr/bin/env python3
"""Pack an order onto build plates and write one 3MF per plate.

An order is a list of (part, params, qty). Each line resolves to a 3MF on
disk; the packer measures its footprint, lays the copies out on as many
plates as it takes, and writes each plate as its own Bambu project, zipped
together.

Packing is by footprint, not bounding box: each piece's outline, seen
from above, is rasterized and slid to the lowest free spot on the plate,
largest first, one fresh plate at a time with leftovers rolling onto the
next. Outlines keep GAP between them, so hexes nest into a honeycomb and a
nut can sit in the notch beside a bracket. It is deterministic, so the same
order always produces the same layout.

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

# Measured off a plate Brett arranged in Bambu Studio 2.08 (22 Tinker Set
# pieces, 2026-09-29): Studio packs by OUTLINE -- hex heads sat in a
# honeycomb, flat to flat, their bounding boxes overlapping by 5 mm -- with
# 2.0 mm between outlines everywhere (hex to hex, 1x4 to 1x4, bracket to
# bracket) and about 3 mm to the bed edge. It rotated nothing, and its own
# auto-rotate packs worse (Brett). The shop's MaxRects on bounding boxes,
# ported from KlipKlopMaker, needed a card's gap cut to fit 20 of those 22.
MARGIN = 3.0        # outline to bed edge
GAP = 2.0           # outline to outline. A design that knows better says
                    # so: a part carrying its own `gap` uses that instead.
RES = 0.5           # mm per raster cell. Outlines are rasterized
                    # conservatively, so gaps come out at GAP or a little
                    # over, never under.
HULL_ABOVE = 300_000  # faces: past this the true outline costs seconds
                      # (6.5 s on an 870k-face library body), so the
                      # convex hull stands in for it
# The brim a single piece gets when its card asks for one on that piece
# alone (`brim_bodies`): a tall part in a set of short ones. Plate-wide
# brims stay the default; this rides on the plate as a per-object setting.
PIECE_BRIM = {"brim_type": "outer_only", "brim_width": "5",
              "brim_object_gap": "0"}


def _shape(it):
    """The piece's outline, centered on its bounding-box center.

    Items from an order carry their real outline; anything else -- a test,
    an older caller -- is packed as the rectangle its w and d describe.
    """
    from shapely.geometry import box
    o = it.get("outline")
    if o is None:
        return box(-it["w"] / 2, -it["d"] / 2, it["w"] / 2, it["d"] / 2)
    return o


def _raster(shape, rot, grow):
    """Cells a rotated, grown outline touches, and where its center lands.

    Conservative: a cell counts if the outline reaches any part of it, so
    two rasters that do not overlap are at least `grow` apart for real.
    """
    import shapely
    from shapely import affinity
    g = affinity.rotate(shape, rot, origin=(0, 0)) if rot else shape
    g = g.buffer(grow + RES * 0.7072, join_style=1)
    x0, y0, x1, y1 = g.bounds
    x0, y0 = np.floor(x0 / RES) * RES, np.floor(y0 / RES) * RES
    nx, ny = int(np.ceil((x1 - x0) / RES)), int(np.ceil((y1 - y0) / RES))
    X, Y = np.meshgrid(x0 + (np.arange(nx) + 0.5) * RES,
                       y0 + (np.arange(ny) + 0.5) * RES)
    mask = shapely.contains_xy(g, X, Y)
    return mask, (-x0 / RES, -y0 / RES)


def pack(items, bed=(256.0, 256.0), height=256.0, margin=MARGIN, gap=GAP,
         rotate=True):
    """Pack per-copy items onto plates.

    Returns (plates, oversized). Coordinates are plate-centered, which is
    what a 3MF build item wants, and name the center of the piece's
    bounding box. Oversized parts are refused by name and reason rather
    than dropped off the edge.

    A piece is placed as it was drawn. It is turned 90 degrees only when
    that is the only way it fits the bed at all.
    """
    from scipy.signal import fftconvolve
    bw, bd = bed
    # the raster spans the bed less the margin, plus the half-gap every
    # outline is grown by: an outline then stays `margin` from the edge
    inset = max(0.0, margin - gap / 2)
    W = int(np.floor((bw - 2 * inset) / RES))
    D = int(np.floor((bd - 2 * inset) / RES))
    queue, oversized = [], []
    for it in items:
        g = gap if it.get("gap") is None else float(it["gap"])
        shape = _shape(it)
        opts = []
        for rot in ((0, 90) if rotate else (0,)):
            mask, off = _raster(shape, rot, g / 2)
            if mask.shape[0] <= D and mask.shape[1] <= W:
                opts.append((rot, mask, off))
                break           # drawn orientation first; 90 only to rescue
        if not opts:
            oversized.append(dict(it, reason="footprint"))
        elif it.get("h", 0) > height + 1e-9:
            oversized.append(dict(it, reason="height"))
        else:
            queue.append(dict(it, gap=g, _opts=opts, _area=shape.area))
    queue.sort(key=lambda i: (-i["_area"], -max(i["w"], i["d"]),
                              str(i["key"])))
    groups, order = {}, []
    for it in queue:
        g = it.get("group", "")
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(it)
    usable = (bw - 2 * margin) * (bd - 2 * margin)
    plates = []
    for g in order:
        remaining = groups[g]
        while remaining:
            occ = np.zeros((D, W), np.float32)
            placed, leftover = [], []
            for it in remaining:
                rot, mask, (ox, oy) = it["_opts"][0]
                mh, mw = mask.shape
                if occ.any():
                    hit = fftconvolve(occ, mask[::-1, ::-1].astype(
                        np.float32), mode="valid")
                    free = np.argwhere(hit < 0.5)
                else:
                    free = np.array([[0, 0]])
                if not len(free):
                    leftover.append(it)
                    continue
                # lowest row, then leftmost: argwhere is row-major already
                r, c = (int(v) for v in free[0])
                occ[r:r + mh, c:c + mw] = np.maximum(
                    occ[r:r + mh, c:c + mw], mask)
                pw, pd = ((it["d"], it["w"]) if rot == 90
                          else (it["w"], it["d"]))
                out = {k: v for k, v in it.items() if not k.startswith("_")}
                placed.append(dict(
                    out, rot=rot, pw=pw, pd=pd,
                    x=inset + (c + ox) * RES - bw / 2,
                    y=inset + (r + oy) * RES - bd / 2))
            if not placed:
                break
            used = sum(_shape(p).area for p in placed)
            plates.append(dict(index=len(plates) + 1, group=g, items=placed,
                               used=used, util=used / usable))
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
    """Every body of a file, in world space, keyed by its geometry name.

    Keyed on the file's size and mtime, not its path alone. A generated part
    is rebuilt in place at the same path, so a cache keyed on the path holds
    the old mesh for the life of the process: the server kept handing out a
    nut whose bore entry had been fixed on disk twenty minutes earlier.
    """
    try:
        st = os.stat(path)
        key = (path, st.st_size, int(st.st_mtime))
    except OSError:
        key = (path, None, None)
    hit = _BODIES.get(path)
    if hit is None or hit[0] != key:
        src = trimesh.load(path, force="scene")
        out = []
        for node in src.graph.nodes_geometry:
            tf, gk = src.graph[node]
            g = src.geometry[gk].copy()
            g.apply_transform(tf)
            out.append((gk, g))
        _BODIES[path] = (key, out)
        hit = _BODIES[path]
    return [(gk, g.copy()) for gk, g in hit[1]]


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


_FOOT = {}


def footprint(path, keys):
    """A piece's outline from above, holes filled, in world XY.

    Holes are filled because nothing should be packed inside a plate's
    bolt hole. Cached like the bodies, on the file's size and mtime.
    """
    from shapely.geometry import MultiPoint, Polygon
    from shapely.ops import unary_union
    from trimesh.path.polygons import projected
    try:
        st = os.stat(path)
        key = (path, st.st_size, int(st.st_mtime), tuple(sorted(keys)))
    except OSError:
        key = None
    if key in _FOOT:
        return _FOOT[key]
    polys = []
    for gk, g in load_bodies(path):
        if keys and gk not in keys:
            continue
        p = None
        if len(g.faces) <= HULL_ABOVE:
            try:
                # precise: the default traces a raster, and on the double
                # bolt it lost the collar entirely -- a 40 x 34 outline
                # off-center on a 38 x 33 hex, which let a nut into its brim
                p = projected(g, normal=[0, 0, 1], precise=True)
            except Exception:                              # noqa: BLE001
                p = None
        if p is None or p.is_empty:
            p = MultiPoint(g.vertices[:, :2]).convex_hull
        polys.append(p)
    u = unary_union(polys)
    out = unary_union([Polygon(q.exterior)
                       for q in getattr(u, "geoms", [u])
                       if q.geom_type == "Polygon"])
    if key is not None:
        _FOOT[key] = out
    return out


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
        # NOT `or {}`: with no params, out_path still fills the name from
        # the catalog defaults while ensure passes the generator no flags
        # at all, so the generator's own defaults get written under the
        # card's canonical filename -- a PLA-Basic rod field served
        # forever as gazebo-rod-field-petg.3mf. Every route in serve.py
        # falls back to the card's defaults; this one did not.
        params = line.get("params") or catalog.defaults(part)
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
        # A brim is a per-part decision and plates are homogeneous: a part
        # that needs one must not share a plate with a part a brim would
        # ruin. The packer already partitions by group, so the brim choice
        # is the group.
        #
        # A design here declares its own. A file off disk cannot, so the
        # measurement speaks for it: the shop was printing "brim, or it will
        # come loose" on the card and shipping the plate with no brim. Only
        # the brim is automatic — a support inside a captive cage cannot be
        # got out again, so that stays advice.
        brim = part.get("brim")
        if brim is None:
            pr = (catalog.previews().get(part["id"], {})
                  .get("printability") or {})
            brim = ("on" if any("brim" in a for a in pr.get("advice", []))
                    else "off")
        for i in range(int(line.get("qty", 1))):
            for j, keys in enumerate(groups):
                pb = (any(k.startswith(tuple(part["brim_bodies"]))
                          for k in keys) if part.get("brim_bodies")
                      else False)
                ext = _extent(bodies, set(keys))
                from shapely import affinity
                fp = footprint(path, set(keys))
                lo = np.min([g.bounds[0] for gk, g in bodies
                             if gk in set(keys)], axis=0)
                hi = np.max([g.bounds[1] for gk, g in bodies
                             if gk in set(keys)], axis=0)
                fp = affinity.translate(fp, -(lo[0] + hi[0]) / 2,
                                        -(lo[1] + hi[1]) / 2)
                if pb:
                    # a piece's own brim is part of its footprint: packed
                    # at the bare body, a 5 mm brim runs into neighbors a
                    # 2 mm gap away
                    fp = fp.buffer(float(PIECE_BRIM["brim_width"]),
                                   join_style=1)
                items.append(dict(
                    key=part["id"], path=path, copy=i, bodies=keys,
                    name=(part["name"] if one
                          else f"{part['name']} ({j + 1}/{len(groups)})"),
                    assembly=one, brim=brim, gap=part.get("gap"),
                    # a piece that asks for its own brim, on a plate that
                    # has none: `brim_bodies` names body prefixes
                    piece_brim=pb, outline=fp,
                    group=("brim" if brim == "on" else ""),
                    **ext))
    return items, reports


def arranged_scene(plates, pitch=300.0, simplify=None):
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
    if simplify and total > simplify:
        # Shared max-min, so a small part on a plate beside a big one keeps
        # the faces that give it its shape. Cut everything by the same
        # proportion and the wrench loses three quarters of its corners to
        # make room for a base plate that will not miss them.
        import meshcheck
        flat = [(bodies, i)
                for (_, _, _, _, _, bodies) in staged
                for i in range(len(bodies))]
        want = meshcheck.budget_faces(
            [len(bodies[i][1].faces) for bodies, i in flat], simplify)
        for (bodies, i), w in zip(flat, want):
            gk, g = bodies[i]
            if w >= len(g.faces):
                continue
            try:
                bodies[i] = (gk, g.simplify_quadric_decimation(
                    face_count=max(200, w)))
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


def plate_name(p):
    stem = f"plate_{p['index']:02d}"
    if p["group"]:
        stem += f"_{p['group']}"
    return stem


def _stamp_parts(p):
    """What is on this plate, by version — so a file can be identified later.

    A downloaded plate was anonymous: nothing in it said which version of a
    design it held, so "is this the latest?" could only be answered by
    measuring the mesh. That is not a question a user should have to bring
    to someone else.
    """
    import versions as _v
    out = []
    seen = set()
    for it in p["items"]:
        if it["key"] in seen:
            continue
        seen.add(it["key"])
        try:
            part = catalog.find(it["key"])
        except KeyError:
            continue
        led, _ = _v.reconcile([dict(part, kind=part["kind"])], write=False)
        e = led.get(it["key"], {})
        out.append(dict(id=it["key"], name=part["name"],
                        version=e.get("version", part.get("version", "?")),
                        fingerprint=e.get("fingerprint", "")))
    return out


def write_plate(p, path, brim=False):
    """One plate as a Bambu project. Returns its manifest entry."""
    from embed_settings import embed
    sc = trimesh.Scene()
    used, cm3 = {}, 0.0
    per_object = {}
    for it in p["items"]:
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
            g.apply_translation([it["x"] - ctr[0], it["y"] - ctr[1], dz])
            cm3 += float(g.volume) / 1000
        # An assembly is one object on the plate. Written body by body it
        # arrives in Studio as loose parts the user can drag apart — a chain
        # whose links separate, a die lifted out of its cage.
        if it.get("assembly", True) and len(bodies) > 1:
            sc.add_geometry(trimesh.util.concatenate([g for _, g in bodies]),
                            geom_name=f"{it['key']}_{n}")
        else:
            for gk, g in bodies:
                sc.add_geometry(g, geom_name=f"{it['key']}_{n}_{gk}")
                if it.get("piece_brim") and not brim:
                    per_object[f"{it['key']}_{n}_{gk}"] = dict(PIECE_BRIM)
    sc.export(path)
    embed(path, brim=brim, per_object=per_object)
    stamp = _stamp_parts(p)
    # written into the project itself, so the answer travels with the file
    with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Metadata/print_shop.json", json.dumps(
            {"plate": p["index"], "brim": bool(brim), "parts": stamp},
            indent=1))
        z.writestr("PARTS.txt", "My Print Shop — what is on this plate\n\n"
                   + "\n".join(f"  {q['name']}  v{q['version']}  "
                                f"[{q['fingerprint']}]" for q in stamp)
                   + f"\n\n  brim: {'outer' if brim else 'none'}\n")
    return dict(plate=p["index"], group=p["group"], parts=len(p["items"]),
                versions=stamp,
                util=round(p["util"], 3), solid_cm3=round(cm3, 1),
                brim=bool(brim), file=os.path.basename(path),
                items=[dict(key=i["key"], name=i["name"],
                            x=round(i["x"], 1), y=round(i["y"], 1),
                            rot=i["rot"], w=round(i["pw"], 1),
                            d=round(i["pd"], 1), h=round(i["h"], 1))
                       for i in p["items"]])


def build_output(plates, outdir, oversized=None):
    """One plate downloads as a 3MF; several download as a zip.

    Wrapping a single plate in an archive is a step for the user to undo
    before they can open it.
    """
    made = []
    for p in plates:
        brim = p["group"] == "brim"
        stem = plate_name(p)
        cm3_path = os.path.join(outdir, f"{stem}.3mf")
        m = write_plate(p, cm3_path, brim=brim)
        vs = m.get("versions") or []
        tag = f"_{vs[0]['id']}-v{vs[0]['version']}" if len(vs) == 1 else ""
        named = os.path.join(
            outdir,
            f"{stem}{tag}_{m['parts']}parts_{round(m['solid_cm3'])}cm3.3mf")
        if named != cm3_path:
            os.replace(cm3_path, named)
            m["file"] = os.path.basename(named)
        made.append((named, m))
    if len(made) == 1:
        return made[0][1]["file"], [m for _, m in made]
    name = "print-shop-order.zip"
    with zipfile.ZipFile(os.path.join(outdir, name), "w",
                         zipfile.ZIP_DEFLATED) as z:
        for path, m in made:
            with open(path, "rb") as f:
                z.writestr(m["file"], f.read())
            os.remove(path)
        z.writestr("plates.json", json.dumps([m for _, m in made], indent=1))
        z.writestr("README.txt",
                   "My Print Shop — one 3MF per plate, Bambu P2S.\n\n"
                   + describe(plates, oversized or [])
                   + "\n\nEach file carries the P2S machine, 0.20mm Standard\n"
                     "and PLA Basic presets, supports off. Open a plate and\n"
                     "slice; the layout is already arranged.\n\n"
                     "Volumes in the filenames are solid material. A sparse\n"
                     "infill prints well under that — slice for the real\n"
                     "figure.\n")
    return name, [m for _, m in made]


if __name__ == "__main__":
    import sys
    order = json.loads(sys.argv[1]) if len(sys.argv) > 1 else [
        {"part": "mont_double", "qty": 2},
        {"part": "dice_orb", "qty": 1},
    ]
    items, reports = order_items(order)
    plates, rejected = pack(items)
    name, man = build_output(plates, catalog.CUSTOM, oversized=rejected)
    print(describe(plates, rejected))
    print(json.dumps({"plates": len(plates), "download": name,
                      "files": [m["file"] for m in man],
                      "brim": [m["file"] for m in man if m["brim"]]}, indent=1))
