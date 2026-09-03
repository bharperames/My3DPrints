#!/usr/bin/env python3
"""Sphere stand: a ring that cradles a ball on a conformal spherical seat.

Ported from the Sphere Stand Generator (~/Code/3d_prints), which builds the
ring by hand as interleaved Three.js vertex rings. The shape is a surface of
revolution, so here it is one revolved profile instead — same geometry, a
tenth of the code, and watertight by construction.

Profile, in (radius, height), with the ball's center at z_off above the bed:

    R_in  = base - wall/2        inner lip
    R_out = base + wall/2        outer rim      (base is the MID-WALL radius)
    z_off = R_ball + seat        seat = air gap under the ball
    y(r)  = z_off - sqrt(R_ball^2 - r^2)          for r <= r_c
            y(r_c) - (r - r_c)                    for r >  r_c   (45 deg)
    r_c   = R_out - chamfer      outermost contact radius

So the ball does not balance on a knife edge: it beds into a spherical band
whose width is the contact arc.

Gates carried over from the original: the inner lip must stay inside the
ball's equator or the ball is trapped; the chamfer may not eat the wall nor
dip the rim below the bed; and the tip angle -- how far the ball must roll
before its weight passes outside the contact circle -- must clear 25 deg.
Added here: a wall thinner than three nozzle widths is refused, which the
original allowed silently down to 0.5 mm.

Usage: gen_sphere_stand.py --ball D [--base R] [--wall T] [--chamfer C]
                           [--seat H] [--out FILE.3mf]
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh

NOZZLE = 0.4
TIP_MIN, TIP_MAX = 25.0, 75.0


def auto(ball):
    """The original's Auto-Optimize: a 45 deg contact latitude."""
    return dict(base=(ball / 2) * 0.707, wall=ball * 0.10,
                chamfer=ball * 0.03, seat=1.0)


def max_base(ball, wall):
    """Inner lip must stay inside the ball's equator, or the ball is caged."""
    return ball / 2 + wall / 2 - 0.1


def max_chamfer(ball, base, wall, seat):
    """Chamfer may not eat the wall, nor drop the rim through the bed."""
    R, R_in, R_out = ball / 2, base - wall / 2, base + wall / 2
    z_off = R + seat
    geo = (R_out - max(0.0, R_in)) - 0.1
    bed = geo
    for c in np.arange(0.1, geo + 0.1, 0.1):
        rc = R_out - c
        y = z_off - np.sqrt(max(0.0, R ** 2 - min(R, rc) ** 2))
        if y - c < 0:
            bed = max(0.0, c - 0.1)
            break
    return min(geo, bed)


def profile(ball, base, wall, chamfer, seat, n=96):
    """Closed (r, z) outline of the ring, ready to revolve."""
    R, R_in, R_out = ball / 2, base - wall / 2, base + wall / 2
    R_in = max(0.05, R_in)
    z_off = R + seat
    r_c = R_out - chamfer

    def y(r):
        if r > r_c:
            return y(r_c) - (r - r_c)
        return z_off - np.sqrt(max(0.0, R ** 2 - min(R, r) ** 2))

    rs = np.linspace(R_in, r_c, n)
    pts = [(R_in, 0.0), (R_out, 0.0), (R_out, y(R_out))]
    pts += [(float(r), float(y(r))) for r in rs[::-1]]
    return np.array(pts + [pts[0]]), R, R_in, R_out, r_c, z_off


def tip_angle(ball, R_out, chamfer):
    R = ball / 2
    rc = min(R * 0.9999, max(0.0, R_out - chamfer))
    h = np.sqrt(max(0.0, R ** 2 - rc ** 2))
    return float(np.degrees(np.arctan2(rc, h))), rc


def contact_arc(ball, R_in, rc):
    R = ball / 2
    return float(R * max(0.0, np.arcsin(min(1, rc / R))
                         - np.arcsin(min(1, max(0.0, R_in) / R))))


def build(ball, base=None, wall=None, chamfer=None, seat=None, segments=None):
    a = auto(ball)
    base = a["base"] if base is None else base
    wall = a["wall"] if wall is None else wall
    chamfer = a["chamfer"] if chamfer is None else chamfer
    seat = a["seat"] if seat is None else seat
    rep = {}
    if wall < 3 * NOZZLE:
        raise ValueError(f"wall {wall:.2f} mm is under three nozzle widths "
                         f"({3 * NOZZLE:.1f}) — it prints as a hollow shell")
    mb = max_base(ball, wall)
    if base > mb:
        raise ValueError(f"base {base:.1f} mm past the ball's equator "
                         f"(max {mb:.1f}) — the ball would be trapped")
    mc = max_chamfer(ball, base, wall, seat)
    if chamfer > mc:
        raise ValueError(f"chamfer {chamfer:.1f} mm over the limit "
                         f"({mc:.1f}) — it eats the wall or dips the rim "
                         f"below the bed")
    prof, R, R_in, R_out, r_c, z_off = profile(ball, base, wall, chamfer, seat)
    tip, rc = tip_angle(ball, R_out, chamfer)
    rep.update(ball=round(ball, 2), base=round(base, 2), wall=round(wall, 2),
               chamfer=round(chamfer, 2), seat=round(seat, 2),
               inner_dia=round(2 * R_in, 1), outer_dia=round(2 * R_out, 1),
               tip_deg=round(tip, 1), contact_arc=round(
                   contact_arc(ball, R_in, rc), 2),
               seat_latitude=round(float(np.degrees(np.arcsin(
                   min(1, rc / R)))), 1))
    if tip < TIP_MIN:
        raise ValueError(f"tip angle {tip:.0f} deg (min {TIP_MIN:.0f}) — the "
                         f"ball rolls out; widen the base or cut the chamfer")
    if tip > TIP_MAX:
        raise ValueError(f"tip angle {tip:.0f} deg (max {TIP_MAX:.0f}) — the "
                         f"ring swallows the ball; narrow the base")
    if segments is None:                     # the original's auto-density
        segments = int(np.clip(
            np.ceil(np.ceil(np.pi / np.arccos(1 - 0.025 / R_out)) / 8) * 8,
            32, 256))
    m = trimesh.creation.revolve(prof, sections=int(segments))
    rep["segments"] = int(segments)
    rep["facet_err"] = round(float(2 * np.pi * R_out / segments / 4), 3)
    rep["height"] = round(float(m.bounds[1][2] - m.bounds[0][2]), 2)
    rep["bed_mm2"] = round(float(np.pi * (R_out ** 2 - max(0, R_in) ** 2)))
    return m, rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ball", type=float, required=True,
                    help="ball diameter (mm)")
    ap.add_argument("--base", type=float, help="mid-wall radius (mm)")
    ap.add_argument("--wall", type=float, help="wall thickness (mm)")
    ap.add_argument("--chamfer", type=float, help="rim chamfer (mm)")
    ap.add_argument("--seat", type=float, help="air gap under the ball (mm)")
    ap.add_argument("--segments", type=int)
    ap.add_argument("--out")
    a = ap.parse_args()
    if not 8 <= a.ball <= 200:
        print(json.dumps({"ok": False, "error": "ball must be 8-200 mm"}))
        return 1
    try:
        m, rep = build(a.ball, a.base, a.wall, a.chamfer, a.seat, a.segments)
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.process(validate=True)
    m.apply_translation([0, 0, -m.bounds[0][2]])
    rep["watertight"] = bool(m.is_watertight)
    rep["volume_cm3"] = round(float(m.volume) / 1000, 2)
    rep["est_g"] = round(float(m.volume) / 1000 * 1.24, 1)
    ok = rep["watertight"]
    if a.out and ok:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        sc = trimesh.Scene()
        sc.add_geometry(m, geom_name="sphere_stand")
        sc.export(a.out)
        from embed_settings import embed
        embed(a.out, brim=False)
        rep["file"] = os.path.basename(a.out)
    print(json.dumps({"ok": ok, **rep}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
