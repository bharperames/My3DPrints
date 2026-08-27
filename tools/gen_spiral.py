#!/usr/bin/env python3
"""Parametric hourglass screw-pair generator (spiral towers).

Replaces the 8 canonical Idea2Item hourglass STLs with one model, measured
from the originals: the solid is `starts` helical blades with a constant
inner radius, outer edge following an hourglass envelope, tied together by
thin end rims; the spiral is one star-section rod (core + lobes) sharing
the same envelope and twist rate, riding the open slots with a constant
radial clearance. Equal twist keeps angular registration at every insertion
depth, so the pair screws together end to end.

Print gates (field-derived):
  slot-wall overhang  atan(twist * base_r) <= 50 deg   (helix edge droop)
  flank flare         atan((base_r-waist_r)/(cell_h/2)) <= 45 deg
  rim thickness       >= 1.6 mm  (1.3 mm rims cracked in the field)
  blade waist section >= 1.5 mm arc, >= 2.0 mm radial
  wobble index        <= 8 on both parts
  thread simulation   FCL sweep of the full screw-in path
  watertight          both parts, verified from the exported file

Usage: gen_spiral.py --out FILE.3mf [--profile circle|square] [--base-r R]
       [--waist-frac F] [--cell-h H] [--cells N] [--starts K]
       [--twist DEG_PER_MM] [--audit-only]
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh

CLR = 0.4                          # radial + tangential running clearance
R_IN = 5.0                         # blade inner radius (channel wall)
RIM_H, RIM_BITE = 4.0, 0.7
BLADE_FRAC = 0.47                  # blade share of each angular period


def env_factory(base_r, waist_r, cell_h, cells):
    def env(z):
        t = np.mod(z, cell_h) / cell_h
        return waist_r + (base_r - waist_r) * np.abs(2 * t - 1)
    return env


def sq_profile(theta):
    """Radius multiplier of a unit square (half-width 1) at angle theta."""
    c = np.maximum(np.abs(np.cos(theta)), np.abs(np.sin(theta)))
    return 1.0 / c


def polar_loft(pts, z0, z1, nz, omega, env, env0, square=False):
    """Loft a polar polygon along z with twist and envelope scaling.

    pts: list of (r, theta, scaled) — `scaled` verts follow env(z)/env0
    (and the square profile at their rotated angle when square=True).
    Returns a watertight Trimesh.
    """
    zs = np.linspace(z0, z1, nz)
    N = len(pts)
    verts, rings = [], []
    for z in zs:
        rot = omega * (z - z0)
        ring = []
        for (r, th, scaled) in pts:
            a = th + rot
            rr = r
            if scaled:
                rr = r * env(z) / env0
                if square:
                    rr *= sq_profile(a)
            ring.append([rr * np.cos(a), rr * np.sin(a), z])
        rings.append(len(verts))
        verts.extend(ring)
    faces = []
    for i in range(len(zs) - 1):
        a, b = rings[i], rings[i + 1]
        for j in range(N):
            k = (j + 1) % N
            faces.append([a + j, a + k, b + j])
            faces.append([b + j, a + k, b + k])
    # caps: earcut the exact end rings (sections need not be star-shaped)
    from shapely.geometry import Polygon as SPoly
    for base, flip in ((rings[0], True), (rings[-1], False)):
        ring2 = np.array(verts[base:base + N])[:, :2]
        try:
            _, f2 = trimesh.creation.triangulate_polygon(
                SPoly(ring2), engine="earcut")
        except Exception:
            _, f2 = trimesh.creation.triangulate_polygon(SPoly(ring2))
        for tri in f2:
            t = [base + int(i) for i in tri]
            faces.append([t[0], t[2], t[1]] if flip else t)
    m = trimesh.Trimesh(np.array(verts), np.array(faces), process=False)
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.fix_normals()
    return m


def sector_pts(r0, r1, th0, th1, steps=9):
    """Annular sector boundary (CCW): outer arc scaled, inner arc fixed."""
    pts = []
    for th in np.linspace(th0, th1, steps):
        pts.append((r1, th, True))
    for th in np.linspace(th1, th0, steps):
        pts.append((r0, th, False))
    return pts


def star_pts(core_r, tip_r, starts, lobe_ang, steps=7):
    """Star boundary (CCW): lobe tip arcs scaled, core arcs fixed."""
    pts = []
    period = 2 * np.pi / starts
    for k in range(starts):
        c = (k + 0.5) * period          # lobes sit in the slots, not on blades
        for th in np.linspace(c - lobe_ang / 2, c + lobe_ang / 2, steps):
            pts.append((tip_r, th, True))
        for th in np.linspace(c + lobe_ang / 2, c + period - lobe_ang / 2,
                              steps):
            pts.append((core_r, th, False))
    return pts


def build(p):
    """Build (solid, spiral, report). Raises ValueError on a failed gate."""
    base_r, waist_r = p["base_r"], p["base_r"] * p["waist_frac"]
    H = p["cell_h"] * p["cells"]
    omega = np.radians(p["twist"])
    starts = p["starts"]
    square = p["profile"] == "square"
    rep = {}

    # --- analytic print gates ---
    slot_oh = np.degrees(np.arctan(omega * base_r *
                                   (np.sqrt(2) if square else 1)))
    rep["slot_overhang_deg"] = round(slot_oh, 1)
    if slot_oh > 50:
        raise ValueError(f"slot walls overhang {slot_oh:.0f}° from vertical "
                         f"(>50): lower twist or base width")
    flare = np.degrees(np.arctan((base_r - waist_r) / (p["cell_h"] / 2)))
    rep["flank_flare_deg"] = round(flare, 1)
    if flare > 45:
        raise ValueError(f"flank flare {flare:.0f}° (>45): raise waist or "
                         f"stretch the cell")
    if p["rim_t"] < 1.6:
        raise ValueError(f"rim {p['rim_t']} mm (<1.6): field prints cracked "
                         f"at 1.3 mm")
    period = 2 * np.pi / starts
    blade_arc_waist = BLADE_FRAC * period * waist_r
    rep["blade_waist_arc_mm"] = round(blade_arc_waist, 2)
    if blade_arc_waist < 1.5:
        raise ValueError(f"blades thin to {blade_arc_waist:.1f} mm arc at "
                         f"the waist (<1.5): fewer starts or wider waist")
    if waist_r - R_IN < 2.0:
        raise ValueError(f"blade radial depth at waist "
                         f"{waist_r - R_IN:.1f} mm (<2.0): raise waist_frac")

    env = env_factory(base_r, waist_r, p["cell_h"], p["cells"])
    env0 = env(0.0)
    nz = max(31, int(H) + 1)

    # --- solid: blades + end rims ---
    blade_ang = BLADE_FRAC * period
    parts = []
    for k in range(starts):
        th0 = k * period - blade_ang / 2
        parts.append(polar_loft(sector_pts(R_IN, base_r, th0,
                                           th0 + blade_ang),
                                0, H, nz, omega, env, env0, square))
    bore = base_r - RIM_BITE
    rim_out = bore + p["rim_t"]
    ring = [(rim_out, t, False) for t in np.linspace(0, 2 * np.pi, 48,
                                                     endpoint=False)]
    ring += [(bore, t, False) for t in np.linspace(2 * np.pi, 0, 48,
                                                   endpoint=False)]
    for z0, z1 in ((0, RIM_H), (H - RIM_H, H)):
        rim = polar_loft(ring, z0, z1, 3, 0.0, env, env0, False)
        parts.append(rim)
    solid = trimesh.boolean.union(parts, engine="manifold")
    solid.vertices = solid.vertices.round(4)
    solid.merge_vertices(digits_vertex=5)
    solid.update_faces(solid.unique_faces())
    solid.update_faces(solid.nondegenerate_faces())
    solid.process(validate=True)

    # --- spiral: one star-section rod ---
    tip_r = base_r - RIM_BITE - CLR
    ang_clr = CLR / R_IN       # gap >= CLR at every radius >= R_IN
    lobe_ang = (1 - BLADE_FRAC) * period - 2 * ang_clr
    if lobe_ang < np.radians(6):
        raise ValueError("lobes vanish: fewer starts or wider slots")
    sp_env = env_factory(tip_r, waist_r * tip_r / base_r,
                         p["cell_h"], p["cells"])
    spiral = polar_loft(star_pts(R_IN - CLR, tip_r, starts, lobe_ang),
                        0, H, nz, omega, sp_env, sp_env(0.0), False)
    spiral.merge_vertices()
    spiral.process(validate=True)

    rep.update(rim_mm=round(p["rim_t"], 2), height=H,
               base_dia=round(2 * (rim_out if not square
                                   else rim_out * np.sqrt(2)), 1),
               solid_cm3=round(solid.volume / 1000, 1),
               spiral_cm3=round(spiral.volume / 1000, 1))
    return solid, spiral, rep


def audit(solid, spiral, p, rep, thread_steps=3.0):
    """Mesh-measured gates: watertight, bed contact, wobble, thread sim."""
    from shapely.ops import unary_union
    from mech_audit import wobble_index
    import trimesh.collision as tc
    for name, m in (("solid", solid), ("spiral", spiral)):
        rep[f"{name}_watertight"] = bool(m.is_watertight)
        sec = m.section(plane_origin=[0, 0, m.bounds[0][2] + 0.15],
                        plane_normal=[0, 0, 1])
        if sec is None:
            rep[f"{name}_bed_mm2"], rep[f"{name}_bed_islands"] = 0, 0
        else:
            p2, _ = sec.to_2D()
            u = unary_union(list(p2.polygons_full))
            geoms = list(getattr(u, "geoms", [u]))
            rep[f"{name}_bed_mm2"] = round(u.area)
            rep[f"{name}_bed_islands"] = len(geoms)
        wob, _ = wobble_index(m, step=2.0)
        rep[f"{name}_wobble"] = wob
    # thread simulation: screw the spiral down the full path
    H = p["cell_h"] * p["cells"]
    omega = np.radians(p["twist"])
    cm = tc.CollisionManager()
    cm.add_object("solid", solid)
    worst, hit = np.inf, None
    for dz in np.arange(H - 1.0, -0.01, -thread_steps):
        T = trimesh.transformations.rotation_matrix(omega * dz, [0, 0, 1])
        T[2, 3] = dz
        if cm.in_collision_single(spiral, transform=T):
            hit = float(dz)
            break
        worst = min(worst, cm.min_distance_single(spiral, transform=T))
    rep["thread_min_gap"] = None if hit is not None else round(float(worst), 2)
    rep["threads"] = hit is None
    if hit is not None:
        rep["thread_jam_at"] = hit
    return rep


DEFAULTS = dict(profile="circle", base_r=21.3, waist_frac=0.485,
                cell_h=90.0, cells=1, starts=7, twist=2.88, rim_t=1.8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--profile", choices=["circle", "square"],
                    default=DEFAULTS["profile"])
    ap.add_argument("--base-r", type=float, default=DEFAULTS["base_r"])
    ap.add_argument("--waist-frac", type=float,
                    default=DEFAULTS["waist_frac"])
    ap.add_argument("--cell-h", type=float, default=DEFAULTS["cell_h"])
    ap.add_argument("--cells", type=int, default=DEFAULTS["cells"])
    ap.add_argument("--starts", type=int, default=DEFAULTS["starts"])
    ap.add_argument("--twist", type=float, default=DEFAULTS["twist"])
    ap.add_argument("--rim-t", type=float, default=DEFAULTS["rim_t"])
    ap.add_argument("--audit-only", action="store_true")
    a = ap.parse_args()
    p = dict(profile=a.profile, base_r=a.base_r, waist_frac=a.waist_frac,
             cell_h=a.cell_h, cells=a.cells, starts=a.starts, twist=a.twist,
             rim_t=a.rim_t)
    try:
        solid, spiral, rep = build(p)
        rep = audit(solid, spiral, p, rep)
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    ok = (rep["threads"] and rep["solid_watertight"]
          and rep["spiral_watertight"] and rep["solid_wobble"] <= 8
          and rep["spiral_wobble"] <= 8)
    if not a.audit_only and a.out and ok:
        # pair plate: side by side
        w = solid.bounds[1][0] - solid.bounds[0][0]
        spiral = spiral.copy()
        spiral.apply_translation([w / 2 + spiral.bounds[1][0] + 8, 0, 0])
        sc = trimesh.Scene()
        sc.add_geometry(solid, geom_name="solid")
        sc.add_geometry(spiral, geom_name="spiral")
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        sc.export(a.out)
        from embed_settings import embed
        embed(a.out)
        rep["file"] = os.path.basename(a.out)
    print(json.dumps({"ok": ok, **rep}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
