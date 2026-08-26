#!/usr/bin/env python3
"""Parametric dice cage: a d20 inside the geodesic sphere.

Usage: gen_dice_cage.py --dia D --freq N --strut S --out FILE.3mf
The die is auto-sized by the seat rule: its face inradius = lattice opening
inradius + strut radius + 1.2 mm, so a landed face always bridges the floor
openings and rests level on the surrounding struts (the spherical bottom
self-centers it). Faces engraved 1-20, antipodal pairs summing 21. Die
prints flat-face-down on the windowed pedestal with a breakaway neck.
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh
from trimesh.proximity import signed_distance


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
    from shapely.geometry import Polygon
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
    ap.add_argument("--dia", type=float, required=True)
    ap.add_argument("--freq", type=int, required=True)
    ap.add_argument("--strut", type=float, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    R, sr = a.dia / 2, a.strut / 2
    jr = sr * 1.42
    if not 44 <= a.dia <= 90:
        print(json.dumps({"ok": False, "error": "dice cage Ø must be 44-90 mm"}))
        return 1
    if not (1 <= a.freq <= 6 and 1.4 <= a.strut <= 4.5):
        print(json.dumps({"ok": False, "error": "freq 1-6, strut Ø 1.4-4.5"}))
        return 1

    V, F, edges = geodesic(a.freq, R)
    e_len = float(max(np.linalg.norm(V[p] - V[q]) for p, q in edges))
    if e_len > 16.0:
        print(json.dumps({"ok": False, "error":
              f"unstable: lattice spans {e_len:.0f} mm (>16, field-proven) — "
              f"finer lattice or smaller Ø"}))
        return 1
    if e_len / a.strut > 8.0:
        print(json.dumps({"ok": False, "error":
              f"struts too slender ({e_len / a.strut:.0f}, limit 8) — "
              f"thicken to ≥ {e_len / 8:.1f} mm"}))
        return 1

    # seat rule: die face bridges any floor opening and rests on its struts
    o_r = e_len / (2 * np.sqrt(3)) - sr
    face_in = o_r + sr + 1.2
    a_d = face_in * 2 * np.sqrt(3)             # d20 face edge
    die_cr = 0.9511 * a_d                      # circumradius
    if die_cr > R - sr - 3.5:
        print(json.dumps({"ok": False, "error":
              f"seat rule needs a Ø{2 * die_cr:.0f} die, too big for this cage — "
              f"use a finer lattice (smaller openings → smaller die) or a bigger Ø"}))
        return 1

    # cage with pedestal window
    ped_r = min(7.0, 0.34 * R - 3.5, face_in - 1.0)
    win_r = ped_r + 3.5
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
    die_minwidth = 2 * face_in * 2.618         # d20 in-sphere Ø (face-to-face)
    if die_minwidth < win_open + 1.0:
        print(json.dumps({"ok": False, "error":
              f"die (min width {die_minwidth:.0f}) could escape the pedestal "
              f"window (Ø{win_open:.0f})"}))
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
    dn = die.face_normals[0]
    die.apply_transform(trimesh.geometry.align_vectors(dn, [0, 0, -1]))
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
    engraved = die
    depth = 0.8
    try:
        cutters = []
        for fi in range(20):
            nm = numeral_mesh(str(order[fi]), cap_height=face_in * 0.85, depth=depth + 0.4)
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
        engraved = die.difference(trimesh.boolean.union(cutters, engine="manifold"))
        engrave_note = "numerals engraved"
    except Exception as exc:
        engraved = die
        engrave_note = f"plain faces (engraving failed: {str(exc)[:60]})"

    ped_h, neck_h = 4.0, 1.4
    die_lo = engraved.bounds[0][2]
    engraved.apply_translation([0, 0, zbed + ped_h + neck_h - die_lo])
    ped = trimesh.creation.cylinder(radius=ped_r, height=ped_h, sections=48)
    ped.apply_translation([0, 0, zbed + ped_h / 2])
    neck = trimesh.creation.cylinder(radius=2.6, height=neck_h + 1.0, sections=24)
    neck.apply_translation([0, 0, zbed + ped_h + (neck_h + 1.0) / 2 - 0.3])
    held = trimesh.boolean.union([engraved, ped, neck], engine="manifold")

    from mech_audit import wobble_index
    wob, wz = wobble_index(held)
    if wob > 8.0:
        print(json.dumps({"ok": False, "error":
              f"die too heavy for its neck while printing (wobble {wob}, limit 8)"}))
        return 1
    d = float((-signed_distance(cage, held.vertices[::11])).min())
    if d < 0.8:
        print(json.dumps({"ok": False, "error":
              f"die/pedestal too close to cage: {d:.2f} mm (needs ≥ 0.8)"}))
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
                      "span_mm": round(e_len, 1), "die_edge": round(a_d, 1),
                      "die_dia": round(2 * die_cr, 1), "face_in": round(face_in, 1),
                      "opening": round(2 * o_r, 1), "wobble": wob,
                      "clearance": round(d, 2), "watertight": wt,
                      "engraving": engrave_note,
                      "dims": [round(float(x), 1) for x in ext],
                      "volume_cm3": round(float(vol), 1),
                      "est_g": round(float(vol) * 1.24, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
