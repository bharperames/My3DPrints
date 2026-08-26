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
    ap.add_argument("--freq", type=int, required=True)
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
    elif not 1 <= a.freq <= 6:
        err = "lattice frequency must be 1-6"
    elif not 1.4 <= a.strut <= 4.5:
        err = "strut Ø must be 1.4-4.5 mm"
    if err:
        print(json.dumps({"ok": False, "error": err}))
        return 1

    # class-I geodesic tessellation: 30*freq^2 struts (30/120/270/480/750/1080)
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

    nu = a.freq
    edges, F = set(), []
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
                if i + j < nu - 1:
                    d1 = grid[(i + 1, j + 1)]
                    F.append((b1, d1, c1))
    V = np.array(verts) * R
    F = np.array(F)
    n0 = np.cross(V[F[0][1]] - V[F[0][0]], V[F[0][2]] - V[F[0][0]])
    V = trimesh.transform_points(
        V, trimesh.geometry.align_vectors(n0 / np.linalg.norm(n0), [0, 0, -1]))
    e_len = float(max(np.linalg.norm(V[p] - V[q]) for p, q in edges))
    # bottom window: clear the central bottom struts so a wide, stiff pedestal
    # can rise from the bed. A O2.4 pip cannot brace a growing ball against
    # nozzle drag (field-proven, twice) — foundation stiffness scales as d^4.
    # pedestal is capped: the cage's structure is fixed — the window may only
    # claim the central bottom region, never grow with the ball
    ped_r = min(7.0, 0.34 * R - 3.5, br - 3.5, max(4.0, br * 0.45))
    if ped_r < 3.0:
        print(json.dumps({"ok": False, "error":
              f"ball Ø{a.ball:g} too small for a stable pedestal (needs ≥ 13 mm)"}))
        return 1
    win_r = ped_r + 3.5
    zlow = V[:, 2].min() + R * 0.4

    def seg_axis_dist(p, q):
        # min distance from segment pq (xy projection) to the z axis
        a, b = V[p][:2], V[q][:2]
        d = b - a
        L2 = float(d @ d)
        t = 0.0 if L2 == 0 else float(np.clip(-(a @ d) / L2, 0, 1))
        return float(np.linalg.norm(a + t * d))

    edges = {(p, q) for (p, q) in edges
             if not (max(V[p][2], V[q][2]) < zlow and seg_axis_dist(p, q) < win_r)}
    # the window is a potential escape route: ball must not fit through it
    low_d = [seg_axis_dist(p, q) for (p, q) in edges
             if max(V[p][2], V[q][2]) < zlow + 4]
    win_open = 2 * (min(low_d) - sr) if low_d else 2 * win_r
    if a.ball < win_open + 1.0:
        print(json.dumps({"ok": False, "error":
              f"ball Ø{a.ball:g} could escape through the pedestal window "
              f"(Ø{win_open:.1f}) — ball needs ≥ {win_open + 1:.0f} mm at this size"}))
        return 1
    # stability envelope, bracketed by field prints (13 mm good / 22 mm fail):
    if e_len > 16.0:
        print(json.dumps({"ok": False, "error":
              f"unstable: lattice spans {e_len:.0f} mm (shallow-strut edges droop "
              f"and strand above 16 — field-proven). Use a finer lattice or a "
              f"smaller Ø"}))
        return 1
    if e_len / a.strut > 8.0:
        print(json.dumps({"ok": False, "error":
              f"unstable: Ø{a.strut:g} struts over {e_len:.0f} mm spans flex under "
              f"nozzle drag (ratio {e_len/a.strut:.0f}, limit 8). Thicken the "
              f"struts to ≥ {e_len/8:.1f} mm"}))
        return 1
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
    used = {i for e in edges for i in e}
    for i in used:
        s = trimesh.creation.icosphere(subdivisions=2, radius=jr)
        s.apply_translation(V[i])
        parts.append(s)
    cage = trimesh.boolean.union(parts, engine="manifold")
    zbed = cage.bounds[0][2]
    # wide bed-anchored pedestal through the window + breakaway neck + teardrop
    ped_h = 4.0
    neck_h = 1.4
    z_apex = zbed + ped_h + neck_h
    zc = z_apex + br * np.sqrt(2)
    ball = trimesh.creation.icosphere(subdivisions=4, radius=br)
    ball.apply_translation([0, 0, zc])
    cone = trimesh.creation.cone(radius=br / np.sqrt(2), height=br * np.sqrt(2),
                                 sections=48)
    cone.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    cone.apply_translation([0, 0, z_apex - cone.bounds[0][2]])
    ped = trimesh.creation.cylinder(radius=ped_r, height=ped_h, sections=48)
    ped.apply_translation([0, 0, zbed + ped_h / 2])
    neck_r = max(1.9, br * 0.16)      # neck scales with ball mass
    neck = trimesh.creation.cylinder(radius=neck_r, height=neck_h + 1.0, sections=24)
    neck.apply_translation([0, 0, zbed + ped_h + (neck_h + 1.0) / 2 - 0.2])
    held = trimesh.boolean.union([ball, cone, ped, neck], engine="manifold")
    # print-time mechanics gate (field-calibrated: failed print 28, survived 8.9)
    from mech_audit import wobble_index
    wob, wz = wobble_index(held)
    if wob > 8.0:
        print(json.dumps({"ok": False, "error":
              f"unstable while printing: wobble index {wob} at z={wz:.0f} "
              f"(a survived print measured 8.9, a failed one 28) — the ball is "
              f"too heavy for its neck at this size"}))
        return 1
    d = float((-signed_distance(cage, held.vertices[::11])).min())
    if d < 0.8:
        print(json.dumps({"ok": False, "error":
              f"ball/pedestal too close to the cage: {d:.2f} mm (needs ≥ 0.8)"}))
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
                      "span_mm": round(e_len, 1), "wobble": wob,
                      "struts": len(edges), "opening": round(opening, 1),
                      "clearance": round(d, 2), "watertight": wt,
                      "dims": [round(float(x), 1) for x in ext],
                      "volume_cm3": round(float(vol), 1),
                      "est_g": round(float(vol) * 1.24, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
