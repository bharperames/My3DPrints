#!/usr/bin/env python3
"""Parametric print-in-place chain generator.

Usage: gen_chain.py --links N --len L_MM --dia D_MM [--layout auto|straight|coil]
                    [--bed MM] --out FILE.3mf
Geometry: stadium links, alternating +/-45 tilt, resting on the bed. Link
width follows the cross-section (CL_W = 2.5*D + 1.0) so the opening always
admits the neighbour's tube. Pitch starts at the tested ratio and backs off
until FCL proves every joint free and threaded.

A long chain laid out straight runs off the end of the plate. Past that it is
coiled instead, on an Archimedean spiral whose turn per link is no sharper
than the joint has been measured to tolerate: the same collision and
threading tests that pass the straight joint are run on a curved pair, and
the tightest radius that passes sets the coil. Every pair of links in the
finished layout is then checked, neighbours and rings alike, so a coil that
laps back onto itself is refused rather than shipped.
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
    ap.add_argument("--layout", choices=("auto", "straight", "coil"),
                    default="auto")
    ap.add_argument("--bed", type=float, default=246.0,
                    help="usable plate edge (mm); the coil must fit inside it")
    a = ap.parse_args()
    err = None
    if not 2 <= a.links <= 120:
        err = "links must be 2-120"
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
    min_gap = max(0.4, 0.12 * a.dia)

    def place(x, y, psi, tilt):
        """A link at (x, y), lying along a path heading psi, tilted on it."""
        l = link.copy()
        l.apply_transform(
            trimesh.transformations.rotation_matrix(tilt, [1, 0, 0]))
        l.apply_transform(
            trimesh.transformations.rotation_matrix(psi, [0, 0, 1]))
        l.apply_translation([x, y, 0])
        l.apply_translation([0, 0, -l.bounds[0][2]])
        return l

    def threaded(a_lnk, b_lnk, tilt_a, psi_a):
        """Does b pass through a's opening? A membrane across a, cut by b."""
        memb = memb0.copy()
        if tilt_a < 0:
            memb.apply_transform(
                trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
        memb.apply_transform(
            trimesh.transformations.rotation_matrix(psi_a, [0, 0, 1]))
        memb.apply_translation(a_lnk.bounds.mean(axis=0)
                               - memb.bounds.mean(axis=0))
        inter = memb.intersection(b_lnk)
        return (not inter.is_empty) and inter.volume >= 0.1

    def joint_ok(a_lnk, b_lnk, tilt_a, psi_a):
        """The two tests the straight joint passes: free, and threaded."""
        cm = trimesh.collision.CollisionManager()
        cm.add_object("a", a_lnk)
        if cm.in_collision_single(b_lnk):
            return False
        if cm.min_distance_single(b_lnk) < min_gap:
            return False
        return threaded(a_lnk, b_lnk, tilt_a, psi_a)

    def turn_ok(r):
        """Does the joint still work when the chain bends at radius r?"""
        dpsi = pitch / r
        for k in (0, 1):                       # both tilt orders
            t0 = np.pi / 4 if k == 0 else -np.pi / 4
            t1 = -t0
            p0 = place(0.0, 0.0, 0.0, t0)
            p1 = place(r * np.sin(dpsi), r * (1 - np.cos(dpsi)), dpsi, t1)
            if not joint_ok(p0, p1, t0, 0.0):
                return False
        return True

    def coil_at(r0):
        """Lay the chain on an Archimedean spiral starting at radius r0."""
        ring = cl_w + a.dia + max(1.5, 0.5 * a.dia)   # clear of the next ring
        b = ring / (2 * np.pi)
        pos, th = [(r0, 0.0, np.pi / 2)], 0.0
        step = np.radians(0.2)
        while len(pos) < a.links:
            th += step
            r = r0 + b * th
            if r > usable / 2:
                return None, None
            x, y = r * np.cos(th), r * np.sin(th)
            if np.hypot(x - pos[-1][0], y - pos[-1][1]) >= pitch:
                pos.append((x, y, np.arctan2(b * np.sin(th) + r * np.cos(th),
                                             b * np.cos(th) - r * np.sin(th))))
        return ([place(x, y, psi, np.pi / 4 if i % 2 == 0 else -np.pi / 4)
                 for i, (x, y, psi) in enumerate(pos)],
                [((x, y), psi) for x, y, psi in pos])

    def check(links_, poses):
        """Prove the finished layout, not the pair model it was built from.

        Every pair for collision — a coil laps back on itself, and a
        neighbour-only check never sees ring touching ring — and every
        neighbour for threading, because links that merely pass close to
        each other make a row of rings, not a chain.
        """
        worst_ = None
        # Two links cannot touch if their centres are further apart than the
        # sum of their reaches, so most of the n^2 pairs need no collision
        # test at all. Without this a long coil spends minutes proving that
        # opposite sides of the spiral are not in contact.
        reach = cl_l + a.dia
        mid = np.array([np.array(pz[0]) for pz in poses])
        for i in range(len(links_)):
            near = [j for j in range(i + 1, len(links_))
                    if j == i + 1
                    or np.hypot(*(mid[j] - mid[i])) <= reach]
            if not near:
                continue
            one = trimesh.collision.CollisionManager()
            one.add_object("a", links_[i])
            for j in near:
                if one.in_collision_single(links_[j]):
                    return None, f"links {i} and {j} touch"
                if j == i + 1:
                    d = one.min_distance_single(links_[j])
                    worst_ = d if worst_ is None else min(worst_, d)
        if worst_ is not None and worst_ < min_gap:
            return None, (f"tightest joint {worst_:.2f} mm, under the "
                          f"{min_gap:.2f} mm the printer needs")
        for i in range(len(links_) - 1):
            _, psi = poses[i]
            tilt = np.pi / 4 if i % 2 == 0 else -np.pi / 4
            if not threaded(links_[i], links_[i + 1], tilt, psi):
                return None, f"links {i} and {i + 1} are not threaded"
        return worst_, None

    straight_len = (a.links - 1) * pitch + cl_l
    usable = a.bed
    want_coil = (a.layout == "coil"
                 or (a.layout == "auto" and straight_len > usable))
    layout, coil_r, why = "straight", None, None
    if want_coil:
        # The pair test says which bends the joint tolerates in isolation;
        # the built coil is what actually has to pass, and it did not at the
        # first radius the pair test allowed. So open the coil out until the
        # whole layout passes, rather than trusting the local answer.
        seed = None
        for r in np.arange(pitch * 0.8, pitch * 12.0, pitch * 0.2):
            if turn_ok(float(r)):
                seed = float(r)
                break
        if seed is None:
            print(json.dumps({"ok": False, "error":
                  "the joint will not bend: no coil radius passes the "
                  "clearance and threading tests"}))
            return 1
        placed_links = None
        r0 = seed
        for _ in range(14):
            cand, poses = coil_at(r0)
            if cand is not None:
                worst, why = check(cand, poses)
                if why is None:
                    placed_links, coil_r, layout = cand, round(r0, 1), "coil"
                    break
            r0 *= 1.12
        if placed_links is None:
            print(json.dumps({"ok": False, "error":
                  f"no coil fits a {usable:g} mm plate for {a.links} links"
                  + (f" — {why}" if why else "")}))
            return 1
    else:
        placed_links = [place(i * pitch, 0.0, 0.0,
                              np.pi / 4 if i % 2 == 0 else -np.pi / 4)
                        for i in range(a.links)]
        worst, why = check(placed_links,
                           [((i * pitch, 0.0), 0.0) for i in range(a.links)])
        if why is not None:
            print(json.dumps({"ok": False, "error": why}))
            return 1

    sc = trimesh.Scene()
    for i, l in enumerate(placed_links):
        sc.add_geometry(l, geom_name=f"link_{i}")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sc.export(a.out)
    from embed_settings import embed
    # no brim: a 5 mm skirt would bridge the gaps between print-in-place links
    embed(a.out, brim=False)
    ext = sc.bounds[1] - sc.bounds[0]
    per = 2 * (cl_l - cl_w) + np.pi * cl_w
    vol = per * np.pi * (a.dia / 2) ** 2 * a.links / 1000.0
    print(json.dumps({"ok": True, "file": os.path.basename(a.out),
                      "links": a.links, "pitch": round(float(pitch), 2),
                      "layout": layout, "coil_radius": coil_r,
                      "straight_len": round(float(straight_len), 1),
                      "clearance": round(float(worst if worst is not None
                                               else clearance), 2),
                      "dims": [round(float(x), 1) for x in ext],
                      "volume_cm3": round(float(vol), 1),
                      "est_g": round(float(vol) * 1.24, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
