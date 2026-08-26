#!/usr/bin/env python3
"""Dice cage: a standard-size d20 captive inside a geodesic shaker sphere.

Fixed design — no user parameters. The optimizer picked Ø58 / frequency-4 /
Ø2.0 struts because the seat rule (die face inradius = opening inradius +
strut radius + 1.2 mm, so a landed face always rests level across the floor
struts) then yields a die of 20.5 mm face-to-face — a standard d20 — with
the cage 2.8x the die for shaking room, spans 9.4 mm (field envelope: <=16,
slenderness 4.7 vs limit 8).

Die support: a thin triangular sleeve rises from the bed under the die's
bottom-face perimeter, stopping 1.4 mm short of the face; three 3.0 x 0.9 mm
breakaway tabs at the edge midpoints carry the face. The numeral on the
landing face (the "1") stays untouched, and rim sag while bridging is
self-limited to 1.4 mm by the wall below. Faces engraved 1-20, antipodal
pairs summing 21; 6 and 9 carry underlines.

Usage: gen_dice_cage.py --out FILE.3mf
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh
from trimesh.proximity import signed_distance

DIA, FREQ, STRUT = 58.0, 4, 2.0
WALL_T, TAB_L, TAB_W, TAB_H = 1.5, 3.0, 0.9, 1.4
Z_FACE = 5.4                      # die bottom-face height above the bed


def geodesic(nu, R):
    ico = trimesh.creation.icosahedron()
    IV = ico.vertices / np.linalg.norm(ico.vertices, axis=1, keepdims=True)
    verts, index = [], {}

    def vid(p):
        p = p / np.linalg.norm(p)
        key = tuple(np.round(p, 6))
        if key not in index:
            index[key] = len(verts)
            verts.append(p)
        return index[key]

    edges = set()
    F = []
    for fa in ico.faces:
        A, B, C = IV[fa[0]], IV[fa[1]], IV[fa[2]]
        grid = {}
        for i in range(nu + 1):
            for j in range(nu + 1 - i):
                k = nu - i - j
                grid[(i, j)] = vid((k * A + i * B + j * C) / nu)
        for i in range(nu):
            for j in range(nu - i):
                a1, b1, c1 = grid[(i, j)], grid[(i + 1, j)], grid[(i, j + 1)]
                F.append((a1, b1, c1))
                for e in ((a1, b1), (b1, c1), (c1, a1)):
                    edges.add((min(e), max(e)))
    V = np.array(verts) * R
    F = np.array(F)
    n0 = np.cross(V[F[0][1]] - V[F[0][0]], V[F[0][2]] - V[F[0][0]])
    V = trimesh.transform_points(
        V, trimesh.geometry.align_vectors(n0 / np.linalg.norm(n0), [0, 0, -1]))
    return V, F, edges


def numeral_mesh(text, cap_height, depth):
    from matplotlib.textpath import TextPath
    from matplotlib.font_manager import FontProperties
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union
    tp = TextPath((0, 0), text, size=10,
                  prop=FontProperties(family="DejaVu Sans", weight="bold"))
    rings = [Polygon(p) for p in tp.to_polygons() if len(p) >= 3]
    rings = [r for r in rings if r.is_valid and r.area > 1e-6]
    if not rings:
        return None
    # even-odd: a ring contained in an odd number of others is a hole
    ringdepth = [sum(1 for o in rings if o is not r and
                     o.contains(r.representative_point())) for r in rings]
    solids = [r for r, d in zip(rings, ringdepth) if d % 2 == 0]
    holes = [r for r, d in zip(rings, ringdepth) if d % 2 == 1]
    shape = unary_union(solids)
    if holes:
        shape = shape.difference(unary_union(holes))
    if text in ("6", "9"):
        x0, y0, x1, y1 = shape.bounds
        h = y1 - y0
        shape = unary_union([shape, box(x0 + 0.1 * (x1 - x0), y0 - 0.30 * h,
                                        x1 - 0.1 * (x1 - x0), y0 - 0.16 * h)])
    geoms = list(shape.geoms) if shape.geom_type == "MultiPolygon" else [shape]
    m = trimesh.util.concatenate(
        [trimesh.creation.extrude_polygon(g, depth) for g in geoms])
    lo, hi = m.bounds
    s = cap_height / (hi[1] - lo[1])
    m.apply_scale([s, s, 1.0])
    lo, hi = m.bounds
    m.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, 0])
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    R, sr = DIA / 2, STRUT / 2
    jr = sr * 1.42

    V, F, edges = geodesic(FREQ, R)
    e_len = float(max(np.linalg.norm(V[p] - V[q]) for p, q in edges))
    assert e_len <= 16.0 and e_len / STRUT <= 8.0, "envelope regression"

    # seat rule: die face bridges any floor opening and rests on its struts
    o_r = e_len / (2 * np.sqrt(3)) - sr
    face_in = o_r + sr + 1.2
    a_d = face_in * 2 * np.sqrt(3)             # d20 face edge
    die_cr = 0.9511 * a_d                      # circumradius
    die_f2f = 2 * face_in * 2.618              # in-sphere (min width)
    assert die_cr <= R - sr - 3.5, "die does not fit"

    # window for the support sleeve (capped: the cage structure is inviolable)
    ci = face_in - 1.6                 # sleeve wall centerline inradius
    win_r = 2 * (ci + WALL_T / 2) + 1.8
    assert win_r <= 0.34 * R, "sleeve window over structural cap"
    zlow = V[:, 2].min() + R * 0.4

    def seg_ax(p, q):
        a2, b2 = V[p][:2], V[q][:2]
        d2 = b2 - a2
        L2 = float(d2 @ d2)
        t2 = 0.0 if L2 == 0 else float(np.clip(-(a2 @ d2) / L2, 0, 1))
        return float(np.linalg.norm(a2 + t2 * d2))

    edges = {(p, q) for (p, q) in edges
             if not (max(V[p][2], V[q][2]) < zlow and seg_ax(p, q) < win_r)}
    low_d = [seg_ax(p, q) for (p, q) in edges if max(V[p][2], V[q][2]) < zlow + 4]
    win_open = 2 * (min(low_d) - sr) if low_d else 2 * win_r
    if die_f2f < win_open + 1.0:
        print(json.dumps({"ok": False, "error":
              f"die (min width {die_f2f:.0f}) could escape the sleeve window "
              f"(Ø{win_open:.0f})"}))
        return 1

    parts = []
    for p, q in edges:
        P, Q = V[p], V[q]
        d = Q - P
        L = np.linalg.norm(d)
        cyl = trimesh.creation.cylinder(radius=sr, height=L, sections=21)
        cyl.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], d / L))
        cyl.apply_translation((P + Q) / 2)
        parts.append(cyl)
    for i in {i for e in edges for i in e}:
        sph = trimesh.creation.icosphere(subdivisions=2, radius=jr)
        sph.apply_translation(V[i])
        parts.append(sph)
    cage = trimesh.boolean.union(parts, engine="manifold")
    if not cage.is_watertight:
        cage.merge_vertices()
        cage.update_faces(cage.nondegenerate_faces())
        cage.process(validate=True)
    zbed = cage.bounds[0][2]

    # the d20, face-down, numerals engraved (antipodal faces sum to 21)
    die = trimesh.creation.icosahedron()
    die.apply_scale(die_cr / np.linalg.norm(die.vertices[0]))
    die.apply_transform(trimesh.geometry.align_vectors(
        die.face_normals[0], [0, 0, -1]))
    # bottom-face corners from the plain 12-vertex die (the engraved mesh's
    # lowest vertices are numeral-groove points — a degenerate triangle)
    pv = die.vertices
    lowv3 = pv[np.argsort(pv[:, 2])[:3]]
    cents = die.triangles_center.copy()
    normals = die.face_normals.copy()
    order = [None] * 20
    used = set()
    n_lo = 1
    for fi in range(20):
        if fi in used:
            continue
        anti = int(np.argmin([np.dot(cents[fi], cents[j]) for j in range(20)]))
        order[fi] = n_lo
        order[anti] = 21 - n_lo
        used.update((fi, anti))
        n_lo += 1
    depth = 0.6
    try:
        cutters = []
        for fi in range(20):
            nm = numeral_mesh(str(order[fi]), cap_height=face_in * 0.85,
                              depth=depth + 0.4)
            if nm is None:
                continue
            n = normals[fi]
            c = cents[fi]
            up = np.array([0, 0, 1.0]) - n * n[2]
            if np.linalg.norm(up) < 0.1:
                up = np.array([1.0, 0, 0]) - n * n[0]
            up /= np.linalg.norm(up)
            side = np.cross(up, n)
            M = np.eye(4)
            M[:3, 0], M[:3, 1], M[:3, 2] = side, up, -n
            M[:3, 3] = c + n * (depth * 0.5 - 0.05)
            nm.apply_transform(M)
            cutters.append(nm)
        engraved = die.difference(
            trimesh.boolean.union(cutters, engine="manifold"))
        engrave_note = "numerals engraved"
    except Exception as exc:
        engraved = die
        engrave_note = f"plain faces (engraving failed: {str(exc)[:60]})"

    die_lo = engraved.bounds[0][2]
    engraved.apply_translation([0, 0, zbed + Z_FACE - die_lo])
    lowv = lowv3[:, :2] + 0.0          # bottom-face corner XY (die is centered)
    cen = lowv.mean(axis=0)
    from shapely.geometry import Polygon as ShapelyPoly

    def tri_ring(t):
        outer = ShapelyPoly(cen + (lowv - cen) * ((ci + t / 2) / face_in))
        inner = ShapelyPoly(cen + (lowv - cen) * ((ci - t / 2) / face_in))
        return outer.difference(inner)

    wall = trimesh.creation.extrude_polygon(tri_ring(WALL_T), Z_FACE - TAB_H)
    wall.apply_translation([0, 0, zbed])
    corners = [cen + (lv - cen) * (ci / face_in) for lv in lowv]
    tabs = []
    for i in range(3):
        p, q = corners[i], corners[(i + 1) % 3]
        mid = (p + q) / 2
        ang = float(np.arctan2(q[1] - p[1], q[0] - p[0]))
        tab = trimesh.creation.box(extents=[TAB_L, TAB_W, TAB_H + 0.4])
        tab.apply_transform(trimesh.transformations.rotation_matrix(
            ang, [0, 0, 1]))
        tab.apply_translation([mid[0], mid[1],
                               zbed + Z_FACE - TAB_H + (TAB_H + 0.4) / 2])
        tabs.append(tab)
    held = trimesh.boolean.union([engraved, wall] + tabs, engine="manifold")

    from mech_audit import wobble_index
    wob, wz = wobble_index(held)
    if wob > 8.0:
        print(json.dumps({"ok": False, "error":
              f"die too heavy for its tabs while printing (wobble {wob})"}))
        return 1
    d = float((-signed_distance(cage, held.vertices[::7])).min())
    if d < 0.8:
        print(json.dumps({"ok": False, "error":
              f"die/sleeve too close to cage: {d:.2f} mm (needs ≥ 0.8)"}))
        return 1

    cage.apply_translation([0, 0, -zbed])
    held.apply_translation([0, 0, -zbed])
    sc = trimesh.Scene()
    sc.add_geometry(cage, geom_name="cage")
    sc.add_geometry(held, geom_name="die")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sc.export(a.out)
    chk = trimesh.load(a.out, force="scene")
    wt = all(g.is_watertight for g in chk.geometry.values())
    ext = chk.bounds[1] - chk.bounds[0]
    vol = (cage.volume + held.volume) / 1000.0
    print(json.dumps({"ok": True, "file": os.path.basename(a.out),
                      "dia": DIA, "freq": FREQ, "strut": STRUT,
                      "span_mm": round(e_len, 1), "die_edge": round(a_d, 1),
                      "die_dia": round(2 * die_cr, 1),
                      "die_f2f": round(die_f2f, 1),
                      "face_in": round(face_in, 1),
                      "opening": round(2 * o_r, 1),
                      "win_open": round(win_open, 1),
                      "tab_mm2": round(3 * TAB_L * TAB_W, 1),
                      "wobble": wob, "clearance": round(d, 2),
                      "watertight": wt, "engraving": engrave_note,
                      "dims": [round(float(x), 1) for x in ext],
                      "volume_cm3": round(float(vol), 1),
                      "est_g": round(float(vol) * 1.24, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
