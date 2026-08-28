#!/usr/bin/env python3
"""Dice orb: a standard-size d20 captive inside a rib-and-ring shaker sphere.

Fixed design, no user parameters.

Cage: 14 meridian ribs + latitude rings, all Ø2.2 struts (the only
field-proven size), every unsupported arc <= 13 mm (the proven span).
Rings are lathed with a diamond section — 45 deg undersides, because round
horizontal struts hang drooped loops off their bellies (field-observed).
Both poles terminate in an open rim ring; alternate ribs stop one ring
short of the north rim so the top stays open instead of converging into a
solid cap. Three chords across the north rim form a triangular seat the
size of a die face: peer straight down through it at the die's upward
face, or invert the orb and the die settles into it.

Die: standard d20 (13.5 mm edges, 20.4 mm face-to-face), faces engraved
1-20, antipodal pairs summing 21, 6/9 underlined. Numerals are set in a
grotesque whose "1" is a bare stem — no base serif — sized per numeral to
the face's inscribed circle and dilated so every stroke clears two nozzle
widths.

Support: a triangular sleeve rises from a base disc (its own printed-in
brim) to 1.4 mm under the die's bottom face, where three tapered anchors
meet the face out at its corners — clear of the numeral, so the landing
face stays readable. The sleeve drops out through the polar window after
the die is twisted off.

Usage: gen_dice_cage.py --out FILE.3mf
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh
from trimesh.proximity import signed_distance

DIA, STRUT, RIBS = 58.0, 2.2, 14
A_D = 13.5                        # standard d20 edge length
SPAN_LIMIT = 13.0                 # proven-clean arc (13 printed, 17 stranded)
RING_HW = 1.4                     # ring diamond half-diagonal

Z_FACE = 5.4                      # die bottom-face height above the bed
TAB_H = 1.4                       # anchor height (sleeve top -> die face)
ANCHOR_L, ANCHOR_W_LO, ANCHOR_W_HI = 2.4, 1.6, 0.8
WALL_T = 1.2                      # sleeve wall
SLEEVE_OUT = 3.05                 # sleeve outer inradius (sets the window)
BASE_H, BASE_R = 0.6, 6.1         # integral brim disc under the sleeve

SEAT_LEDGE = 0.7                  # die-face overhang on the top seat bars
FONT = "Arial"                    # "1" is a bare stem: foot/stem == 1.00
NUM_MARGIN = 0.45                 # numeral clear of the face edge
NUM_DILATE = 0.18                 # max stroke fattening per side
MIN_STROKE, MIN_COUNTER = 0.75, 0.45
UL_T, UL_GAP = 0.6, 0.35          # 6/9 underline bar and its gap


def _raw_glyph(text, font=None):
    """Digit outline centered on its bbox, normalized to unit cap height."""
    from matplotlib.textpath import TextPath
    from matplotlib.font_manager import FontProperties
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from shapely import affinity
    tp = TextPath((0, 0), text, size=100,
                  prop=FontProperties(family=font or FONT, weight="bold"))
    rings = [Polygon(p) for p in tp.to_polygons() if len(p) >= 3]
    rings = [r for r in rings if r.is_valid and r.area > 1e-6]
    if not rings:
        return None
    # nesting by whole-polygon containment: a filled outer contour also
    # covers its own counter, so a representative point misclassifies it
    ringdepth = [sum(1 for o in rings if o is not r and o.contains(r))
                 for r in rings]
    solids = [r for r, d in zip(rings, ringdepth) if d % 2 == 0]
    holes = [r for r, d in zip(rings, ringdepth) if d % 2 == 1]
    shape = unary_union(solids)
    if holes:
        shape = shape.difference(unary_union(holes))
    x0, y0, x1, y1 = shape.bounds
    return affinity.scale(
        affinity.translate(shape, -(x0 + x1) / 2, -(y0 + y1) / 2),
        1 / (y1 - y0), 1 / (y1 - y0), origin=(0, 0))


def face_polygon(margin, flip):
    """The die face as a 2D triangle in the numeral's frame, inset."""
    from shapely.geometry import Polygon as SP
    cr = A_D / np.sqrt(3)
    angs = np.radians([90, 210, 330]) + (np.pi / 3 if flip else 0)
    return SP([(cr * np.cos(t), cr * np.sin(t)) for t in angs]).buffer(-margin)


def _inscribed_dia(poly):
    """Largest inscribed circle diameter (erosion bisection)."""
    x0, y0, x1, y1 = poly.bounds
    lo, hi = 0.0, 0.5 * min(x1 - x0, y1 - y0) + 1e-6   # never saturates
    for _ in range(20):
        mid = (lo + hi) / 2
        if poly.buffer(-mid).is_empty:
            hi = mid
        else:
            lo = mid
    return 2 * lo


def _counters(shape):
    """Width of each pillar left standing inside the engraved groove.

    Measured as an inscribed diameter: 2A/P reads the inradius on a
    triangular counter but the full width on a strip, so it halves the
    triangular ones.
    """
    from shapely.geometry import Polygon as SP
    return [_inscribed_dia(SP(r))
            for g in (shape.geoms if shape.geom_type == "MultiPolygon"
                      else [shape]) for r in g.interiors]


def render(text, raw, cap, dilate):
    """Final numeral outline: digits at `cap`, fattened, 6/9 underlined.

    Returns (shape, digit_stroke_mm, min_counter_mm). The stroke is measured
    on the digits alone — the underline is a fixed-width bar and would drag
    the average.
    """
    from shapely.geometry import box
    from shapely.ops import unary_union
    from shapely import affinity
    dig = affinity.scale(raw, cap, cap, origin=(0, 0))
    if dilate > 0:
        dig = dig.buffer(dilate, join_style=2)
    if dig.is_empty:
        return None, 0.0, 0.0
    stroke = 2 * dig.area / dig.length
    ct = _counters(dig)
    shape = dig
    if text in ("6", "9"):
        x0, y0, x1, y1 = dig.bounds
        w = (x1 - x0) * 0.92
        bar = box(-w / 2, y0 - UL_GAP - UL_T, w / 2, y0 - UL_GAP)
        shape = unary_union([dig, bar])
        shape = affinity.translate(shape, 0, (UL_GAP + UL_T) / 2)
    return shape, stroke, (min(ct) if ct else 9.9)


def fit_cap(text, raw, target, dilate):
    """Largest cap height whose finished numeral still sits inside target."""
    lo, hi = 0.5, 12.0
    for _ in range(20):
        mid = (lo + hi) / 2
        g, _, _ = render(text, raw, mid, dilate)
        if g is not None and g.within(target):
            lo = mid
        else:
            hi = mid
    return lo


def numeral_plan(texts, font=None):
    """One cap height for all numerals; per-numeral dilation for counters.

    A common cap keeps the set looking like a die rather than a ransom
    note; dilation is dialed back only where a counter would close.
    """
    tgt = [face_polygon(NUM_MARGIN, f) for f in (False, True)]
    raws = {t: _raw_glyph(t, font) for t in texts}
    caps = {t: [fit_cap(t, raws[t], g, NUM_DILATE) for g in tgt]
            for t in texts}
    cap = min(max(caps[t]) for t in texts)
    plan = {}
    for t in texts:
        d = NUM_DILATE
        while d > 0:
            _, st, ct = render(t, raws[t], cap, d)
            if ct >= MIN_COUNTER:
                break
            d -= 0.02
        shape, st, ct = render(t, raws[t], cap, max(d, 0.0))
        plan[t] = (shape, st, ct, int(np.argmax(caps[t])))
    return cap, plan


def numeral_mesh(shape, depth):
    geoms = list(shape.geoms) if shape.geom_type == "MultiPolygon" else [shape]
    return trimesh.util.concatenate(
        [trimesh.creation.extrude_polygon(g, depth) for g in geoms])


def rib_tube(R, sr, lat0, lat1, phi, ring=14):
    """A meridian rib as one smooth capped torus segment.

    Chaining short cylinders needs a knot sphere at every joint to close the
    union, and a sphere proud enough to weld reliably reads as a beaded
    chain on the print. A single revolve has no joints to hide.
    """
    t = np.linspace(0, 2 * np.pi, ring, endpoint=False)
    prof = np.column_stack([R + sr * np.cos(t), sr * np.sin(t)])
    prof = np.vstack([prof, prof[:1]])
    arc = lat1 - lat0
    m = trimesh.creation.revolve(prof, angle=np.radians(arc), cap=True,
                                 sections=max(24, int(round(arc / 2.5))))
    m.apply_transform(trimesh.transformations.rotation_matrix(
        np.pi / 2, [1, 0, 0]))
    m.apply_transform(trimesh.transformations.rotation_matrix(
        -np.radians(lat0), [0, 1, 0]))
    m.apply_transform(trimesh.transformations.rotation_matrix(phi, [0, 0, 1]))
    return m


def taper(center, axis, z_lo, z_hi, length, w_lo, w_hi):
    """Convex hull of a tapered rectangular post (a breakaway anchor)."""
    a = np.array([-axis[1], axis[0]])          # long axis, tangential
    pts = []
    for z, w in ((z_lo, w_lo), (z_hi, w_hi)):
        for sl in (-1, 1):
            for sw in (-1, 1):
                p = center + a * (sl * length / 2) + axis * (sw * w / 2)
                pts.append([p[0], p[1], z])
    return trimesh.convex.convex_hull(np.array(pts))


def diamond_bar(p, q, hw):
    """Straight bar with a diamond section (45 deg underside)."""
    d = q - p
    L = np.linalg.norm(d)
    w = hw * np.sqrt(2)
    bar = trimesh.creation.box(extents=[L, w, w])
    bar.apply_transform(trimesh.transformations.rotation_matrix(
        np.pi / 4, [1, 0, 0]))
    ang = np.arctan2(d[1], d[0])
    bar.apply_transform(trimesh.transformations.rotation_matrix(
        ang, [0, 0, 1]))
    bar.apply_translation((p + q) / 2)
    return bar


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    R, sr = DIA / 2, STRUT / 2
    jr = sr * 1.42

    face_in = A_D / (2 * np.sqrt(3))            # die face inradius
    die_cr = 0.9511 * A_D                       # die circumradius
    die_f2f = 2 * face_in * 2.618               # in-sphere = min width

    # --- apertures -------------------------------------------------------
    sleeve_cr = 2 * SLEEVE_OUT                  # sleeve corner circumradius
    extract_r = max(sleeve_cr, BASE_R)
    win_r = extract_r + sr + 0.9                # south rim centerline radius
    win_open = 2 * (win_r - sr)
    seat_in = face_in - SEAT_LEDGE              # top seat triangle inradius
    top_r = 2 * seat_in                         # north rim centerline radius
    if die_f2f < win_open + 1.0:
        print(json.dumps({"ok": False, "error":
              f"die (min width {die_f2f:.1f}) escapes the polar window "
              f"(Ø{win_open:.1f})"}))
        return 1
    if die_f2f < 2 * (top_r - sr) + 1.0:
        print(json.dumps({"ok": False, "error":
              f"die escapes the top aperture (Ø{2*(top_r-sr):.1f})"}))
        return 1
    if extract_r > win_r - sr - 0.5:
        print(json.dumps({"ok": False, "error":
              "support sleeve cannot drop out through the polar window"}))
        return 1

    # --- graticule -------------------------------------------------------
    lat_s = -np.degrees(np.arccos(win_r / R))
    lat_n = np.degrees(np.arccos(top_r / R))
    n_gap = int(np.ceil(np.radians(lat_n - lat_s) * R / SPAN_LIMIT))
    ring_lats = list(np.linspace(lat_s, lat_n, n_gap + 1))
    rib_arc = np.radians(ring_lats[1] - ring_lats[0]) * R
    ring_arc = 2 * np.pi * R / RIBS
    span = max(rib_arc, ring_arc)
    if span > SPAN_LIMIT + 0.05:
        print(json.dumps({"ok": False, "error":
              f"unsupported arc {span:.1f} mm over the proven span"}))
        return 1
    slot_w = ring_arc - STRUT
    slot_h = np.radians(ring_lats[1] - ring_lats[0]) * R - STRUT
    if die_f2f < max(slot_w, slot_h) + 1.0:
        print(json.dumps({"ok": False, "error": "die escapes a window"}))
        return 1

    parts = []
    for lat in ring_lats:
        rr = R * np.cos(np.radians(lat))
        z = R * np.sin(np.radians(lat))
        if lat == ring_lats[0]:
            # flat bottom below every sphere on this latitude (crossing
            # joints reach z - jr) so the print starts on a full circle
            prof = [(rr - sr, z - jr - 0.25), (rr + sr, z - jr - 0.25),
                    (rr + sr, z + sr), (rr - sr, z + sr)]
        else:
            prof = [(rr - RING_HW, z), (rr, z - RING_HW),
                    (rr + RING_HW, z), (rr, z + RING_HW)]
        parts.append(trimesh.creation.revolve(np.array(prof + prof[:1]),
                                              sections=96))
    for k in range(RIBS):
        phi = 2 * np.pi * k / RIBS
        # alternate ribs stop one ring short: 7 meeting the north rim keeps
        # the top open, where 14 would converge into a solid collar
        top_lat = lat_n if k % 2 == 0 else ring_lats[-2]
        parts.append(rib_tube(R, sr, lat_s, top_lat, phi))
        for lat in ring_lats:                  # crossing joints
            if lat > top_lat + 1e-6:
                continue
            if lat in (ring_lats[0], ring_lats[-1]):
                # both rim rings are solid revolves: a joint sphere adds
                # nothing, crowds the sleeve below and pokes above the top
                continue
            s = trimesh.creation.icosphere(subdivisions=1, radius=jr)
            s.apply_translation([R * np.cos(np.radians(lat)) * np.cos(phi),
                                 R * np.cos(np.radians(lat)) * np.sin(phi),
                                 R * np.sin(np.radians(lat))])
            parts.append(s)

    # --- the d20, face-down, numerals engraved (antipodal faces sum 21) ---
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
    used, n_lo = set(), 1
    for fi in range(20):
        if fi in used:
            continue
        anti = int(np.argmin([np.dot(cents[fi], cents[j]) for j in range(20)]))
        order[fi] = n_lo
        order[anti] = 21 - n_lo
        used.update((fi, anti))
        n_lo += 1

    # top seat bars framed on the die's up-face orientation (antipodal faces
    # are parallel and point-reflected, so the seat is the bottom face turned
    # 60 deg)
    corner_dirs = lowv3[:, :2] / np.linalg.norm(lowv3[:, :2], axis=1,
                                                keepdims=True)
    seat_ang = np.arctan2(corner_dirs[:, 1], corner_dirs[:, 0]) + np.pi / 3
    z_n = R * np.sin(np.radians(lat_n))
    seat = [np.array([top_r * np.cos(t), top_r * np.sin(t)]) for t in seat_ang]
    for i in range(3):
        p, q = seat[i], seat[(i + 1) % 3]
        d = (q - p) / np.linalg.norm(q - p)
        # End the bars ON the rim circle, not past it. Extending them pushes
        # the end caps out to the ring's own outer surface, where cap and
        # ring graze each other and the union slivers; ending on the circle
        # buries each cap in the middle of the ring's section instead.
        parts.append(diamond_bar(np.array([*p, z_n - 0.12]),
                                 np.array([*q, z_n - 0.12]),
                                 RING_HW * 0.88))

    cage = trimesh.boolean.union(parts, engine="manifold")
    # quantize to export precision, then drop the duplicate faces that
    # coincident weld surfaces collapse into on the 3MF round-trip
    # No cleanup pass here on purpose — see meshcheck.py. The seat bars end
    # on the rim circle so their caps are buried in the ring's section, and
    # the union comes out manifold without help.
    zbed = cage.bounds[0][2]

    depth = 0.6
    cap, plan = numeral_plan([str(i) for i in range(1, 21)])
    strokes = [plan[str(i)][1] for i in range(1, 21)]
    counters = [plan[str(i)][2] for i in range(1, 21)]
    if min(strokes) < MIN_STROKE:
        print(json.dumps({"ok": False, "error":
              f"numeral strokes down to {min(strokes):.2f} mm "
              f"(<{MIN_STROKE}): larger die or heavier font"}))
        return 1
    if min(counters) < MIN_COUNTER:
        print(json.dumps({"ok": False, "error":
              f"numeral counters down to {min(counters):.2f} mm "
              f"(<{MIN_COUNTER}): less dilation"}))
        return 1
    try:
        cutters = []
        for fi in range(20):
            shape, _, _, flip = plan[str(order[fi])]
            nm = numeral_mesh(shape, depth + 0.4)
            n = normals[fi]
            c = cents[fi]
            # orient to the face's own triangle, not to world up: e1 points
            # at the face's first vertex, and `flip` turns the numeral 60 deg
            # so wide two-digit sets get the roomier of the two fits
            v0 = die.vertices[die.faces[fi][0]]
            e1 = v0 - c - n * np.dot(v0 - c, n)
            e1 /= np.linalg.norm(e1)
            e2 = np.cross(n, e1)
            ang = np.pi / 3 * flip
            up = np.cos(ang) * e1 + np.sin(ang) * e2
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
    lowv = lowv3[:, :2]
    cen = lowv.mean(axis=0)
    ci = SLEEVE_OUT - WALL_T / 2                # wall centerline inradius
    from shapely.geometry import Polygon as ShapelyPoly

    def tri_ring(t):
        outer = ShapelyPoly(cen + (lowv - cen) * ((ci + t / 2) / face_in))
        inner = ShapelyPoly(cen + (lowv - cen) * ((ci - t / 2) / face_in))
        return outer.difference(inner)

    wall = trimesh.creation.extrude_polygon(tri_ring(WALL_T), Z_FACE - TAB_H)
    wall.apply_translation([0, 0, zbed])
    base = trimesh.creation.cylinder(radius=BASE_R, height=BASE_H,
                                     sections=64)
    base.apply_translation([0, 0, zbed + BASE_H / 2])
    # anchors at the sleeve's corners — out under the die face's corners,
    # clear of the numeral, tapering to a thin parting line
    anchors, anchor_r = [], 2 * ci
    for u in corner_dirs:
        anchors.append(taper(u * anchor_r, u, zbed + Z_FACE - TAB_H,
                             zbed + Z_FACE + 0.4, ANCHOR_L,
                             ANCHOR_W_LO, ANCHOR_W_HI))
    # the landing face's numeral must survive the parting scars: measure in
    # that numeral's own frame, where the face corners (and so the anchors)
    # sit at the fitted triangle's vertex angles
    from shapely.geometry import box as SBox
    from shapely import affinity as SAff
    land, _, _, land_flip = plan[str(order[0])]
    clr = 9.9
    for deg in np.array([90.0, 210.0, 330.0]) + 60.0 * land_flip:
        u = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))])
        r = SBox(-ANCHOR_L / 2, -ANCHOR_W_HI / 2, ANCHOR_L / 2,
                 ANCHOR_W_HI / 2)
        r = SAff.rotate(r, deg + 90, origin=(0, 0))
        r = SAff.translate(r, *(u * anchor_r))
        clr = min(clr, land.distance(r))
    if clr < 0.6:
        print(json.dumps({"ok": False, "error":
              f"anchors land {clr:.2f} mm from the numeral (<0.6)"}))
        return 1
    held = trimesh.boolean.union([engraved, wall, base] + anchors,
                                 engine="manifold")

    from mech_audit import wobble_index
    wob, wz = wobble_index(held)
    if wob > 8.0:
        print(json.dumps({"ok": False, "error":
              f"die too heavy for its anchors while printing (wobble {wob})"}))
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
    from embed_settings import embed
    embed(a.out)                       # P2S presets + outer brim baked in
    from meshcheck import export_defects
    defects = export_defects(a.out)
    wt = not defects
    chk = trimesh.load(a.out, force="scene")
    ext = chk.bounds[1] - chk.bounds[0]
    vol = (cage.volume + held.volume) / 1000.0
    print(json.dumps({"ok": True, "file": os.path.basename(a.out),
                      "dia": DIA, "ribs": RIBS, "strut": STRUT,
                      "rings": len(ring_lats), "span_mm": round(span, 1),
                      "die_edge": round(A_D, 1),
                      "die_dia": round(2 * die_cr, 1),
                      "die_f2f": round(die_f2f, 1),
                      "window_mm": [round(slot_w, 1), round(slot_h, 1)],
                      "win_open": round(win_open, 1),
                      "top_seat_in": round(seat_in, 2),
                      "seat_ledge": round(SEAT_LEDGE, 2),
                      "anchor_mm2": round(3 * ANCHOR_L * ANCHOR_W_HI, 1),
                      "anchor_r": round(anchor_r, 2),
                      "numeral_clear": round(clr, 2),
                      "numeral_cap": round(cap, 2),
                      "stroke_min": round(min(strokes), 2),
                      "counter_min": round(min(counters), 2),
                      "wobble": wob, "clearance": round(d, 2),
                      "watertight": wt, "defects": defects or None, "engraving": engrave_note,
                      "dims": [round(float(x), 1) for x in ext],
                      "volume_cm3": round(float(vol), 1),
                      "est_g": round(float(vol) * 1.24, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
