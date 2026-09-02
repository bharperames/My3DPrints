#!/usr/bin/env python3
"""How a part wants to sit on the plate, and what it will cost either way.

The shop can generate a part that prints well because the generator gates on
it. A file somebody else designed carries no such promise: it arrives in
whatever orientation its author saved it in, and the first sign that the
orientation is wrong is spaghetti.

This measures what the printer actually cares about — how much of the part
touches the bed, and how much of it hangs over nothing — and tries the
orientations the part could rest in, so a card can say "lay it on this face"
or "this one needs supports whatever you do".

Candidate orientations come from the convex hull's faces: a rigid body can
only rest on a plane of its hull, so those are the orientations, and there
is no point searching the ones physics does not allow.

Usage: orient.py FILE [--top N]
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh

FLAT = 45.0          # degrees from vertical past which a face is overhanging
BED_EPS = 0.15       # mm; a face this close to the plate is touching it
MIN_BED = 60.0       # mm2 of contact under which a part needs a brim
BRIM_LEVER = 4.0     # height : half-width past which a brim is mandatory


LAYER = 0.4          # mm; the step the check walks in
BEAD = 0.42          # mm; how far a layer may hang past the one below


MAX_SLICES = 160     # a tall part is stepped more coarsely rather than
                     # sliced thousands of times; the measure is comparative


def _unsupported(m, layer=LAYER, bead=BEAD):
    """Area that has nothing under it, layer by layer.

    A face normal cannot answer this. The underside of a cage strut points
    straight down and has open air beneath it, yet it prints perfectly: it
    is carried by the previous layer of its own strut, which sits below and
    inward, not directly below. A vertical ray misses that entirely — it
    scored the dice orb, which prints on a brim with no supports, as 4700
    mm2 unsupported.

    So compare each layer with the one under it, the way the slicer does.
    What is not covered by the layer below, grown by one bead, is what the
    printer has to put down over air.
    """
    z0, z1 = float(m.bounds[0][2]), float(m.bounds[1][2])
    layer = max(layer, (z1 - z0) / MAX_SLICES)
    zs = np.arange(z0 + layer / 2, z1, layer)
    if len(zs) < 2:
        return 0.0
    try:
        secs = m.section_multiplane(plane_origin=[0, 0, 0],
                                    plane_normal=[0, 0, 1], heights=zs)
    except BaseException:                          # noqa: BLE001
        return float("nan")
    from shapely.geometry import MultiPolygon, Polygon
    # A gap in the part must not reset the comparison. Treating an empty
    # slice as "no previous layer" skipped the check on the layer that comes
    # after it — which is the island, the one case this exists to catch.
    EMPTY = Polygon()
    prev, ledge, island, first = None, 0.0, 0.0, True
    for s in secs:
        polys = list(s.polygons_full) if s is not None else []
        cur = (polys[0] if len(polys) == 1
               else (_union(polys) if polys else None))
        if cur is None or cur.is_empty:
            if not first:
                prev = EMPTY
            continue
        if first:                    # the bed carries the first layer
            first, prev = False, cur
            continue
        if True:
            try:
                grown = prev.buffer(bead) if not prev.is_empty else prev
                # Two different problems wear the same face. Ask it of each
                # connected piece of the layer, not of the uncovered rim:
                # the rim lies outside the layer below by construction, so
                # it never touches it. A piece that sits on material below
                # is a ledge and bridges — every articulated joint and every
                # strut has them, and they print. A piece with nothing under
                # it at all is an island and has to be held up.
                for q in (cur.geoms if isinstance(cur, MultiPolygon)
                          else [cur]):
                    if q.is_empty:
                        continue
                    free = float(q.difference(grown).area)
                    if q.intersects(prev):
                        ledge += free
                    else:
                        island += float(q.area)
            except BaseException:                  # noqa: BLE001
                pass
        prev = cur
    return round(island, 1), round(ledge, 1)


def _union(polys):
    from shapely.ops import unary_union
    try:
        u = unary_union(list(polys))
        return u if not u.is_empty else None
    except BaseException:                          # noqa: BLE001
        return None


def _measure(m):
    """Bed contact, overhang and lever for a mesh already standing on z=0."""
    n, a, c = m.face_normals, m.area_faces, m.triangles_center
    z0 = float(m.bounds[0][2])
    bed = float(a[(n[:, 2] < -0.9) & (c[:, 2] < z0 + BED_EPS)].sum())
    down = n[:, 2] < -0.05
    ang = np.degrees(np.arcsin(np.clip(-n[down, 2], 0, 1)))
    over_all = float(a[down][ang < FLAT].sum())
    island, ledge = _unsupported(m)
    over = island
    ceil = float(a[down][ang > 85.0].sum())
    ext = m.bounds[1] - m.bounds[0]
    half = max(1e-6, min(ext[0], ext[1]) / 2)
    return dict(bed_mm2=round(bed, 1), overhang_mm2=round(over, 1),
                bridged_mm2=round(ledge, 1),
                facing_down_mm2=round(over_all, 1),
                ceiling_mm2=round(ceil, 1),
                height=round(float(ext[2]), 1),
                lever=round(float(ext[2] / half), 1),
                dims=[round(float(v), 1) for v in ext])


def _rest_orientations(m, limit=24):
    """Rotations that put a hull face on the plate — the ways it can lie."""
    hull = m.convex_hull
    seen, out = [], []
    order = np.argsort(-hull.area_faces)
    for i in order:
        nrm = hull.face_normals[i]
        if any(np.dot(nrm, s) > 0.995 for s in seen):
            continue
        seen.append(nrm)
        out.append(trimesh.geometry.align_vectors(nrm, [0, 0, -1]))
        if len(out) >= limit:
            break
    return out


def evaluate(m, limit=24):
    """Every way it can rest, best first. The first entry is as-saved."""
    res = []
    base = m.copy()
    base.apply_translation([0, 0, -base.bounds[0][2]])
    res.append(dict(_measure(base), rot="as saved", matrix=None))
    for T in _rest_orientations(m, limit):
        q = m.copy()
        q.apply_transform(T)
        q.apply_translation([0, 0, -q.bounds[0][2]])
        ang = np.degrees(trimesh.transformations.euler_from_matrix(T))
        res.append(dict(_measure(q),
                        rot=" ".join(f"{x:+.0f}" for x in ang),
                        matrix=[round(float(v), 5) for v in T.flatten()]))
    # Least unsupported area wins; contact breaks the tie. As-saved is a
    # candidate like any other — leaving it out let the search "improve" a
    # part into a worse orientation than the one it arrived in.
    rest = sorted(res, key=lambda r: (r["overhang_mm2"], -r["bed_mm2"]))
    return res[0], rest


def verdict(best, asis):
    """What to actually do, in words a person can act on."""
    notes = []
    if best["overhang_mm2"] > 60:
        notes.append(f"supports: {best['overhang_mm2']:.0f} mm2 starts in "
                     f"mid-air with nothing under it to build on")
    elif asis["overhang_mm2"] > best["overhang_mm2"] * 1.5 + 50:
        notes.append(f"re-orient: as saved it overhangs "
                     f"{asis['overhang_mm2']:.0f} mm2, laid on its best face "
                     f"{best['overhang_mm2']:.0f}")
    if best["bed_mm2"] < MIN_BED:
        notes.append(f"only {best['bed_mm2']:.0f} mm2 touches the bed — "
                     f"brim, or it will come loose")
    if best["lever"] > BRIM_LEVER:
        notes.append(f"tall and narrow ({best['lever']:.1f}:1) — brim")
    if not notes:
        notes.append("prints as it stands: enough contact, nothing "
                     "significant overhanging")
    return notes


def report(path, limit=24):
    sc = trimesh.load(path, force="scene")
    out = []
    for k, g in sc.geometry.items():
        if not isinstance(g, trimesh.Trimesh) or not len(g.faces):
            continue
        asis, rest = evaluate(g, limit)
        best = rest[0] if rest else asis
        out.append(dict(body=k, as_saved=asis, best=best,
                        advice=verdict(best, asis)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--top", type=int, default=24)
    a = ap.parse_args()
    r = report(a.file, a.top)
    print(json.dumps({"file": os.path.basename(a.file), "bodies": r}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
