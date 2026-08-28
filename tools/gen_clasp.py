#!/usr/bin/env python3
"""Lobster-claw clasp + snap jump ring for the parametric chain.

Both parts are flat 2D profiles extruded in Z, so they print with no
overhangs, no supports and no bridges, and every flexure bends *within* its
layers instead of across them (PLA delaminates far sooner than it yields).

The gate is a flexure, not a pin-and-spring: a curved beam anchored to the
body opposite the mouth, running just inside the bowl wall and spanning the
mouth to trap the link. Pressing the thumb tab (which reaches out through
its own slot, so it never blocks the mouth) bends the beam inward and opens
a passage. A coil spring and a 0.4 mm pivot are the two parts of a real
lobster clasp that PLA does worst.

The jump ring is a C-ring with a ball-and-socket snap. It opens by in-plane
bending, where its section is deliberately floppier (radial thickness <
extrusion height), so the ends splay without twisting out of plane.

Gates: retention (closed gap << link Ø), passage (open gap > link Ø),
flexure strain from beam theory at the anchor, printable slot widths,
part clearance, watertightness, and threading of the chain's own opening.

Usage: gen_clasp.py --dia D [--out FILE.3mf]
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

STRAIN_LIMIT = 0.015          # PLA: keep repeated flexure well under yield
SEAT_CLR = 0.45               # printed gap between gate and body
MIN_FEATURE = 0.9             # nothing thinner than ~2 nozzle widths


def arc_pts(r0, r1, a0, a1, n=90):
    """Polyline sweeping angle a0->a1 while the radius ramps r0->r1."""
    t = np.linspace(0, 1, n)
    a = np.radians(a0 + (a1 - a0) * t)
    r = r0 + (r1 - r0) * t
    return np.column_stack([r * np.cos(a), r * np.sin(a)])


def wedge(a0, a1, r_in, r_out):
    """Annular sector, for cutting slots out of a ring wall."""
    a = np.radians(np.linspace(a0, a1, 40))
    outer = np.column_stack([r_out * np.cos(a), r_out * np.sin(a)])
    inner = np.column_stack([r_in * np.cos(a[::-1]), r_in * np.sin(a[::-1])])
    return Polygon(np.vstack([outer, inner]))


def build(D, T=None):
    """Return (clasp_polygon, ring_polygon, report). Raises ValueError."""
    rep = {}
    tw = max(1.9, 0.66 * D)                 # head wall: reads solid,
                                            # not a second ring
    tg = max(1.00, 0.31 * D)                # gate beam thickness
    th = T if T else max(3.4, 1.10 * D)     # extrusion height
    R1 = 2.60 * D                           # bowl outer radius
    Rin = R1 - tw                           # bowl bore
    gc = 0.62 * D                           # closed gap, gate to bore
    Rg = Rin - gc - tg / 2                  # gate centreline radius
    if Rg - tg / 2 < 0.5 * (D + 1.0):
        raise ValueError("bowl too small to hold the link once it is in")

    # One opening only: a second slot always strands the arc of head wall
    # between it and the mouth. So the mouth sits where a real clasp's does
    # — upper right, under the hooked nose — and the thumb lever rides its
    # lower edge.
    MOUTH_LO, MOUTH_HI = 12.0, 68.0
    A_TAB, TAB_HALF = 25.0, 5.0
    A_ANCH, A_TIP = 272.0, 6.0              # gate sweeps clockwise

    # --- body: one pear silhouette, head through waist to the eye --------
    R2 = 1.45 * D                           # eye outer radius
    yt = -(R1 + R2 + 2.2)                   # eye centre, on a neck
    outer = unary_union([Point(0, 0).buffer(R1, 160),
                         Point(0, yt).buffer(R2, 96)]).convex_hull
    # a hull joins the circles with dead-straight tangents; a real clasp
    # waists inward, so bite a large circle out of each flank — placed so
    # its inner edge lands exactly on the half-width we want, not deeper
    # a small carve circle has the curvature to pinch a neck; a large
    # one is too flat and eats the head before the waist narrows
    hw, wr, yw = 0.47 * R1, 0.75 * R1, -1.12 * R1
    for sx in (-1, 1):
        outer = outer.difference(Point(sx * (hw + wr), yw).buffer(wr, 200))
    # the bowl stays concentric so the verified gate geometry still holds:
    # the pear's own taper is what thickens the wall down into the waist
    body = (outer.difference(Point(0, 0).buffer(Rin, 160))
                 .difference(Point(0, yt).buffer(R2 - tw, 96))
                 .difference(wedge(MOUTH_LO, MOUTH_HI, Rin - 0.4, R1 + 5.0)))
    if body.geom_type != "Polygon":
        raise ValueError("the mouth split the head wall into loose arcs")
    # the waist carve is a big circle and will happily eat through the head
    # if placed badly: measure what wall is actually left
    wall_min = min(Point(Rin * np.cos(t), Rin * np.sin(t)).distance(
        outer.exterior) for t in np.radians(np.arange(0, 360, 2)))
    rep["wall_min_mm"] = round(float(wall_min), 2)
    if wall_min < MIN_FEATURE:
        raise ValueError(f"head wall thins to {wall_min:.2f} mm "
                         f"(<{MIN_FEATURE}) — ease the waist carve")
    passage = np.radians(MOUTH_HI - (A_TAB + TAB_HALF)) * (R1 - tw / 2)
    rep["passage_mm"] = round(passage, 2)
    if passage < D + 0.6:
        raise ValueError(f"only {passage:.1f} mm of mouth clear of the thumb "
                         f"tab — a Ø{D:g} link needs {D + 0.6:.1f}")

    # --- gate: flexure beam, ramping off the wall at the anchor ---
    path = np.vstack([
        arc_pts(R1 - tw / 2, Rg, A_ANCH, A_ANCH - 45, 40),   # blend off wall
        arc_pts(Rg, Rg, A_ANCH - 45, A_TIP, 150)])
    gate = LineString(path).buffer(tg / 2, cap_style=1, resolution=24)
    # a wing, as the real lever is: broad where it leaves the gate and
    # tapering to the point a thumb presses
    wing = arc_pts(Rg, R1 + 1.3, A_TAB + TAB_HALF * 0.8,
                   A_TAB - TAB_HALF * 1.6, 26)
    tab = unary_union([
        LineString(wing[i:i + 3]).buffer(tg * (0.85 - 0.5 * i / len(wing)),
                                         cap_style=1, resolution=12)
        for i in range(0, len(wing) - 2, 2)])
    gate = unary_union([gate, tab])
    clasp = unary_union([body, gate])
    if clasp.geom_type != "Polygon":
        raise ValueError("clasp did not close into one connected part")

    # The gate leaves the wall on a ramp, so the weld root is a taper: the
    # beam is only free where the slot has actually opened. Find that angle
    # rather than assuming the beam starts at the nominal anchor.
    ramp = arc_pts(R1 - tw / 2, Rg, A_ANCH, A_ANCH - 45, 200)
    ang = np.degrees(np.arctan2(ramp[:, 1], ramp[:, 0])) % 360
    gap = Rin - (np.hypot(ramp[:, 0], ramp[:, 1]) + tg / 2)
    free = np.where(gap >= 0.35)[0]
    if not len(free):
        raise ValueError("gate never clears the bore — steepen the ramp")
    A_EFF = float(ang[free[0]])
    rep["weld_root_deg"] = round(A_ANCH - A_EFF, 1)
    rep["gate_slot_mm"] = round(float(Rin - (Rg + tg / 2)), 2)
    if rep["gate_slot_mm"] < 0.35:
        raise ValueError(f"gate/body slot {rep['gate_slot_mm']:.2f} mm — "
                         f"they will fuse")

    # --- retention and passage ---
    open_needed = D + 0.40
    delta_mouth = open_needed - gc
    rep["closed_gap_mm"] = round(gc, 2)
    if gc > D - 0.6:
        raise ValueError(f"closed gap {gc:.1f} mm lets a Ø{D:g} link slip out")
    # beam theory: tab is the load point, the mouth deflects less than the tab
    Rb = Rg
    L = np.radians(A_EFF - A_TAB) * Rb            # free root -> tab
    x = np.radians(A_EFF - 0.5 * (MOUTH_HI + A_TAB + TAB_HALF)) * Rb
    ratio = (x ** 2 * (3 * L - x)) / (2 * L ** 3)  # cantilever shape function
    delta_tab = delta_mouth / ratio
    strain = 3 * tg * delta_tab / (2 * L ** 2)
    rep.update(open_gap_mm=round(open_needed, 2),
               tab_travel_mm=round(delta_tab, 2),
               beam_len_mm=round(L, 1), strain=round(strain, 4))
    if strain > STRAIN_LIMIT:
        raise ValueError(f"gate strain {strain*100:.1f}% over "
                         f"{STRAIN_LIMIT*100:.1f}% — longer or thinner beam")

    # --- jump ring -------------------------------------------------------
    # A butt C-ring, as a metal jump ring is. A ball-and-socket snap was the
    # first attempt and does not fit: a socket with walls either side needs
    # more radial section than the ring can spare without going stiffer than
    # PLA tolerates when sprung open. Section is radially thinner than it is
    # tall on purpose, so it opens in-plane instead of twisting out of its
    # layers.
    rr_t = max(1.30, 0.40 * D)              # radial thickness
    Rr_out = 1.90 * D
    Rr_mid = Rr_out - rr_t / 2
    if rr_t >= th:
        raise ValueError("ring must be radially thinner than it is tall, "
                         "or it opens by twisting out of its layers")
    half = np.degrees(np.arctan2(SEAT_CLR / 2, Rr_mid))
    ring = ((Point(0, 0).buffer(Rr_out, 128)
             .difference(Point(0, 0).buffer(Rr_out - rr_t, 128)))
            .difference(wedge(90 - half, 90 + half,
                              Rr_out - rr_t - 0.1, Rr_out + 0.1)))
    if ring.geom_type != "Polygon":
        raise ValueError("jump ring did not close into one part")
    rep["ring_gap_mm"] = round(SEAT_CLR, 2)

    # ring must splay wide enough to pass a link tube, without over-straining
    Lr = np.pi * Rr_mid                      # each end is half the ring
    dr = (D + 0.5 - SEAT_CLR) / 2            # how far each end must travel
    strain_r = 3 * rr_t * dr / (2 * Lr ** 2)
    rep.update(ring_open_mm=round(D + 0.5, 2), ring_strain=round(strain_r, 4))
    if strain_r > STRAIN_LIMIT:
        raise ValueError(f"jump-ring strain {strain_r*100:.1f}% over limit")

    # threading: the ring's section must pass the chain link's bore and the
    # clasp's tail bore
    sec_diag = np.hypot(rr_t, th)
    link_bore = (2.5 * D + 1.0) - D          # stadium width minus the tube
    tail_bore = 2 * (R2 - tw)
    rep.update(ring_section=[round(rr_t, 2), round(th, 2)],
               link_bore=round(link_bore, 2), tail_bore=round(tail_bore, 2))
    if sec_diag > link_bore - 0.4 or sec_diag > tail_bore - 0.4:
        raise ValueError(f"ring section {sec_diag:.1f} mm will not thread the "
                         f"link ({link_bore:.1f}) or tail ({tail_bore:.1f})")
    rep.update(wall_mm=round(tw, 2), gate_mm=round(tg, 2),
               height_mm=round(th, 2), bowl_dia=round(2 * R1, 1),
               length_mm=round(R1 - yt + R2, 1))
    return clasp, ring, rep, th


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dia", type=float, default=3.25,
                    help="chain cross-section this clasp mates with")
    ap.add_argument("--part", choices=["both", "clasp", "ring"],
                    default="both",
                    help="the ring threads the clasp's eye and the chain's "
                         "link bore, so both are sized from the same --dia")
    ap.add_argument("--out")
    a = ap.parse_args()
    if not 2.0 <= a.dia <= 8.0:
        print(json.dumps({"ok": False, "error": "dia must be 2-8 mm"}))
        return 1
    try:
        clasp, ring, rep, th = build(a.dia)
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    cm = trimesh.creation.extrude_polygon(clasp, th)
    rm = trimesh.creation.extrude_polygon(ring, th)
    rm.apply_translation([clasp.bounds[2] - ring.bounds[0] + 4.0, 0, 0])
    wanted = {"both": (("clasp", cm), ("ring", rm)),
              "clasp": (("clasp", cm),), "ring": (("ring", rm),)}[a.part]
    for name, m in (("clasp", cm), ("ring", rm)):
        rep[f"{name}_watertight"] = bool(m.is_watertight)
        rep[f"{name}_bodies"] = int(len(m.split(only_watertight=False)))
    rep["bed_mm2"] = round(clasp.area + ring.area)
    ok = (cm.is_watertight and rm.is_watertight
          and rep["clasp_bodies"] == 1 and rep["ring_bodies"] == 1)
    rep["emitted"] = [n for n, _ in wanted]
    if a.out and ok:
        sc = trimesh.Scene()
        for name, m in wanted:
            mm = m.copy()
            mm.apply_translation([-mm.bounds[0][0], -mm.bounds[0][1], 0])
            sc.add_geometry(mm, geom_name=name)
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        sc.export(a.out)
        from embed_settings import embed
        embed(a.out)
        rep["file"] = os.path.basename(a.out)
    print(json.dumps({"ok": ok, "dia": a.dia, **rep}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
