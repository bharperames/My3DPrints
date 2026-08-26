#!/usr/bin/env python3
"""Parametric print-in-place chain generator.

Usage: gen_chain.py --links N --len L_MM --dia D_MM --out FILE.3mf
Geometry: stadium links, alternating +/-45 tilt, straight run, resting on the
bed. Link width follows the cross-section (CL_W = 2.5*D + 1.0) so the opening
always admits the neighbour's tube. Pitch starts at the tested ratio and backs
off until FCL proves every joint free and threaded. Prints a JSON result.
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh


def stadium_path(cl_l, cl_w, n_per=26):
    s, r = (cl_l - cl_w) / 2, cl_w / 2
    pts = []
    for t in np.linspace(-np.pi / 2, np.pi / 2, n_per):
        pts.append([s + r * np.cos(t), r * np.sin(t)])
    for t in np.linspace(np.pi / 2, 3 * np.pi / 2, n_per):
        pts.append([-s + r * np.cos(t), r * np.sin(t)])
    return np.array(pts)


def tube(loop2d, tr, n_sec=20):
    P = np.column_stack([loop2d, np.zeros(len(loop2d))])
    n = len(P)
    T = np.roll(P, -1, axis=0) - np.roll(P, 1, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    N = np.cross([0, 0, 1.0], T)
    N /= np.linalg.norm(N, axis=1, keepdims=True)
    B = np.cross(T, N)
    ang = np.linspace(0, 2 * np.pi, n_sec, endpoint=False)
    ring = np.stack([np.cos(ang), np.sin(ang)], axis=1) * tr
    V = (P[:, None, :] + ring[None, :, 0:1] * N[:, None, :]
         + ring[None, :, 1:2] * B[:, None, :]).reshape(-1, 3)
    F = []
    for i in range(n):
        for j in range(n_sec):
            a = i * n_sec + j
            b = i * n_sec + (j + 1) % n_sec
            c = ((i + 1) % n) * n_sec + j
            d = ((i + 1) % n) * n_sec + (j + 1) % n_sec
            F += [[a, b, c], [b, d, c]]
    m = trimesh.Trimesh(V, F)
    m.fix_normals()
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--links", type=int, required=True)
    ap.add_argument("--len", dest="length", type=float, required=True)
    ap.add_argument("--dia", type=float, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    err = None
    if not 2 <= a.links <= 40:
        err = "links must be 2-40"
    elif not 1.5 <= a.dia <= 10:
        err = "cross-section must be 1.5-10 mm"
    cl_w = 2.5 * a.dia + 1.0
    cl_l = a.length - a.dia
    if err is None and cl_l < cl_w + 2:
        err = (f"link too short for its width: length must be ≥ "
               f"{cl_w + 2 + a.dia:.1f} mm at Ø{a.dia:g}")
    if err:
        print(json.dumps({"ok": False, "error": err}))
        return 1

    link = tube(stadium_path(cl_l, cl_w), a.dia / 2)

    def placed(x, tilt):
        l = link.copy()
        l.apply_transform(trimesh.transformations.rotation_matrix(tilt, [1, 0, 0]))
        l.apply_translation([x, 0, 0])
        l.apply_translation([0, 0, -l.bounds[0][2]])
        return l

    memb0 = trimesh.creation.box((cl_l - a.dia - 0.1, cl_w - a.dia - 0.1, 0.5))
    memb0.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 4, [1, 0, 0]))
    result = None
    for s_fac in np.arange(0.30, 0.46, 0.02):
        pitch = (cl_l - cl_w) + s_fac * (cl_w + a.dia)
        l0, l1 = placed(0, np.pi / 4), placed(pitch, -np.pi / 4)
        cm = trimesh.collision.CollisionManager()
        cm.add_object("a", l0)
        if cm.in_collision_single(l1):
            continue
        d = cm.min_distance_single(l1)
        if d < max(0.4, 0.12 * a.dia):
            continue
        memb = memb0.copy()
        memb.apply_translation(l0.bounds.mean(axis=0) - memb0.bounds.mean(axis=0))
        inter = memb.intersection(l1)
        if inter.is_empty or inter.volume < 0.1:
            break                     # too far apart to thread — no larger pitch helps
        result = (pitch, d)
        break
    if result is None:
        print(json.dumps({"ok": False, "error": "no valid pitch found for these parameters"}))
        return 1
    pitch, clearance = result
    sc = trimesh.Scene()
    for i in range(a.links):
        l = placed(i * pitch, np.pi / 4 if i % 2 == 0 else -np.pi / 4)
        sc.add_geometry(l, geom_name=f"link_{i}")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sc.export(a.out)
    ext = sc.bounds[1] - sc.bounds[0]
    per = 2 * (cl_l - cl_w) + np.pi * cl_w
    vol = per * np.pi * (a.dia / 2) ** 2 * a.links / 1000.0
    print(json.dumps({"ok": True, "file": os.path.basename(a.out),
                      "links": a.links, "pitch": round(float(pitch), 2),
                      "clearance": round(float(clearance), 2),
                      "dims": [round(float(x), 1) for x in ext],
                      "volume_cm3": round(float(vol), 1),
                      "est_g": round(float(vol) * 1.24, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
