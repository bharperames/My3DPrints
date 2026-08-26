#!/usr/bin/env python3
"""Parametric held-sphere generator: geodesic strut cage + captive ball.

Usage: gen_cage.py --dia D --subdiv {0,1,2} --strut S --ball B --out FILE.3mf
Builds the icosphere-frame cage (struts along edges, joint spheres at
vertices, face-down on a triangle base), a captive ball on a breakaway pip.
Verifies: watertight bodies, ball genuinely captive (opening vs ball) and
free (signed-distance clearance). Prints a JSON result.
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh
from trimesh.proximity import signed_distance


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dia", type=float, required=True)
    ap.add_argument("--subdiv", type=int, required=True)
    ap.add_argument("--strut", type=float, required=True)
    ap.add_argument("--ball", type=float, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    R = a.dia / 2
    sr = a.strut / 2
    br = a.ball / 2
    jr = sr * 1.35
    err = None
    if not 30 <= a.dia <= 90:
        err = "cage Ø must be 30-90 mm"
    elif a.subdiv not in (0, 1, 2):
        err = "subdiv must be 0, 1 or 2"
    elif not 1.4 <= a.strut <= 4.5:
        err = "strut Ø must be 1.4-4.5 mm"
    if err:
        print(json.dumps({"ok": False, "error": err}))
        return 1

    ico = trimesh.creation.icosphere(subdivisions=a.subdiv)
    V = ico.vertices / np.linalg.norm(ico.vertices, axis=1, keepdims=True) * R
    F = ico.faces
    n0 = np.cross(V[F[0][1]] - V[F[0][0]], V[F[0][2]] - V[F[0][0]])
    V = trimesh.transform_points(
        V, trimesh.geometry.align_vectors(n0 / np.linalg.norm(n0), [0, 0, -1]))
    edges = set()
    for f in F:
        for p, q in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            edges.add((min(p, q), max(p, q)))
    e_len = float(np.linalg.norm(V[F[0][0]] - V[F[0][1]]))
    opening = 2 * (e_len / (2 * np.sqrt(3)) - sr)
    if a.ball <= opening + 1.0:
        print(json.dumps({"ok": False, "error":
              f"ball Ø{a.ball:g} escapes: openings are Ø{opening:.1f} — "
              f"needs ≥ {opening + 1.0:.1f} mm"}))
        return 1
    if br > R - sr - 2.0:
        print(json.dumps({"ok": False, "error":
              f"ball Ø{a.ball:g} won't fit: max ≈ {2 * (R - sr - 2.0):.0f} mm "
              f"inside a Ø{a.dia:g} cage"}))
        return 1

    parts = []
    for p, q in edges:
        P, Q = V[p], V[q]
        d = Q - P
        L = np.linalg.norm(d)
        cyl = trimesh.creation.cylinder(radius=sr, height=L, sections=20)
        cyl.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], d / L))
        cyl.apply_translation((P + Q) / 2)
        parts.append(cyl)
    for v in V:
        s = trimesh.creation.icosphere(subdivisions=2, radius=jr)
        s.apply_translation(v)
        parts.append(s)
    cage = trimesh.boolean.union(parts, engine="manifold")
    zbed = cage.bounds[0][2]
    zc = zbed + br + 3.0
    ball = trimesh.creation.icosphere(subdivisions=4, radius=br)
    ball.apply_translation([0, 0, zc])
    pip = trimesh.creation.cylinder(radius=1.2, height=(zc - br + 0.4) - zbed,
                                    sections=24)
    pip.apply_translation([0, 0, (zbed + zc - br + 0.4) / 2])
    held = trimesh.boolean.union([ball, pip], engine="manifold")
    d = float((-signed_distance(cage, ball.vertices[::9])).min())
    if d < 0.5:
        print(json.dumps({"ok": False, "error":
              f"ball too tight against the cage: {d:.2f} mm (needs ≥ 0.5)"}))
        return 1
    cage.apply_translation([0, 0, -zbed])
    held.apply_translation([0, 0, -zbed])
    sc = trimesh.Scene()
    sc.add_geometry(cage, geom_name="cage")
    sc.add_geometry(held, geom_name="ball")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sc.export(a.out)
    chk = trimesh.load(a.out, force="scene")
    wt = all(g.is_watertight for g in chk.geometry.values())
    ext = chk.bounds[1] - chk.bounds[0]
    vol = (cage.volume + held.volume) / 1000.0
    print(json.dumps({"ok": True, "file": os.path.basename(a.out),
                      "struts": len(edges), "opening": round(opening, 1),
                      "clearance": round(d, 2), "watertight": wt,
                      "dims": [round(float(x), 1) for x in ext],
                      "volume_cm3": round(float(vol), 1),
                      "est_g": round(float(vol) * 1.24, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
