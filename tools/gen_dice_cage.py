#!/usr/bin/env python3
"""Dice orb: a standard-size d20 captive inside a rib-and-ring shaker sphere.

Fixed design, no user parameters. The triangle-lattice version proved both
too dense to read the die and unprintable without supports at see-through
strut sizes (field: Ø1.6 struts stranded; Ø2.2 lattice is opaque). This
topology solves both: 14 meridian ribs + latitude rings every 25°, all at
the only field-proven strut Ø (2.2), with every unsupported arc <= 13 mm —
the span the Ø50 cage printed clean at. Openings are ~11 x 10 mm windows
(die min width 20.5 mm: captive), and the cage stands on a full bed-contact
ring instead of lattice fingertips.

Die: standard d20 (13.5 mm edges, 20.4 mm face-to-face), faces engraved
1-20, antipodal pairs summing 21, 6/9 underlined. It prints face-down on a
thin triangular sleeve under the face perimeter; three 3.0 x 0.9 mm tabs at
the edge midpoints break away with a twist, and rim sag while bridging is
self-limited by the wall 1.4 mm below. The sleeve exits through the polar
window after snap-off.

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
WALL_T, TAB_L, TAB_W, TAB_H = 1.5, 3.0, 0.9, 1.4
Z_FACE = 5.4                      # die bottom-face height above the bed
SPAN_LIMIT = 13.5                 # proven-clean arc (13 mm printed, 17 failed)


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


def tube(points, sr, parts):
    """Polyline of cylinders welded by knot spheres."""
    for i in range(len(points) - 1):
        P, Q = points[i], points[i + 1]
        d = Q - P
        L = np.linalg.norm(d)
        if L < 1e-6:
            continue
        c = trimesh.creation.cylinder(radius=sr, height=L, sections=13)
        c.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], d / L))
        c.apply_translation((P + Q) / 2)
        parts.append(c)
        # slightly proud of the cylinder wall: an exact-radius sphere is
        # tangent along near-collinear segments and welds nonmanifold
        s = trimesh.creation.icosphere(subdivisions=1, radius=sr * 1.06)
        s.apply_translation(P)
        parts.append(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    R, sr = DIA / 2, STRUT / 2
    jr = sr * 1.42

    # standard die, fixed directly (no lattice to nest in any more)
    face_in = A_D / (2 * np.sqrt(3))
    die_cr = 0.9511 * A_D
    die_f2f = 2 * face_in * 2.618

    # polar window sized to pass the snapped-off sleeve with FCL margin
    ci = face_in - 1.6
    tube_outer_cr = 2 * (ci + WALL_T / 2)
    win_r = tube_outer_cr + sr + 0.9           # rim-ring centerline radius
    win_open = 2 * (win_r - sr)
    if not win_open + 1.0 <= die_f2f:
        print(json.dumps({"ok": False, "error":
              f"die (min width {die_f2f:.1f}) could escape the polar window "
              f"(Ø{win_open:.1f})"}))
        return 1

    # graticule: rim ring at the window, rings every 25°, ribs to a pole cap
    lat_s = -np.degrees(np.arccos(win_r / R))  # south rim latitude
    ring_lats = [lat_s, -50, -25, 0, 25, 50, 75]
    arcs = {"rib max": np.radians(max(np.diff(ring_lats + [90]))) * R,
            "ring max": 2 * np.pi * R / RIBS}
    span = max(arcs.values())
    if span > SPAN_LIMIT:
        print(json.dumps({"ok": False, "error":
              f"unsupported arc {span:.1f} mm over the proven span "
              f"{SPAN_LIMIT} (field: 13 printed clean, 17 stranded)"}))
        return 1
    # captivity: worst window is the equator slot between ribs
    slot_w = 2 * np.pi * R / RIBS - STRUT
    slot_h = np.radians(25) * R - STRUT
    if not max(slot_w, slot_h) + 1.0 <= die_f2f:
        print(json.dumps({"ok": False, "error": "die could escape a window"}))
        return 1

    parts = []
    # rings are lathed: diamond section (45° underside — round horizontal
    # struts loop strands off their bellies, field-observed), except the rim
    # ring which needs a flat bottom on the bed
    hw = 1.4                                   # diamond half-diagonal
    for lat in ring_lats:
        rr = R * np.cos(np.radians(lat))
        z = R * np.sin(np.radians(lat))
        if lat == lat_s:
            # flat bottom below every sphere on this latitude (crossing
            # joints reach z - jr) so the print starts on a full circle,
            # not 14 floating dots
            prof = [(rr - sr, z - jr - 0.25), (rr + sr, z - jr - 0.25),
                    (rr + sr, z + sr), (rr - sr, z + sr)]
        else:
            prof = [(rr - hw, z), (rr, z - hw), (rr + hw, z), (rr, z + hw)]
        ring = trimesh.creation.revolve(np.array(prof + prof[:1]),
                                        sections=96)
        parts.append(ring)
    for k in range(RIBS):
        phi = 2 * np.pi * k / RIBS
        lats = np.radians(np.arange(lat_s, 88.0, 4.0))
        pts = np.column_stack([R * np.cos(lats) * np.cos(phi),
                               R * np.cos(lats) * np.sin(phi),
                               R * np.sin(lats)])
        tube(pts, sr, parts)
        for lat in ring_lats:                  # crossing joints
            s = trimesh.creation.icosphere(subdivisions=1, radius=jr)
            s.apply_translation([R * np.cos(np.radians(lat)) * np.cos(phi),
                                 R * np.cos(np.radians(lat)) * np.sin(phi),
                                 R * np.sin(np.radians(lat))])
            parts.append(s)
    cap = trimesh.creation.icosphere(subdivisions=2, radius=jr * 1.6)
    cap.apply_translation([0, 0, R])
    parts.append(cap)
    cage = trimesh.boolean.union(parts, engine="manifold")
    # quantize to export precision, then drop the duplicate faces that
    # coincident weld surfaces collapse into on the 3MF round-trip
    cage.vertices = cage.vertices.round(4)
    cage.merge_vertices(digits_vertex=5)
    cage.update_faces(cage.unique_faces())
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
                      "dia": DIA, "ribs": RIBS, "strut": STRUT,
                      "span_mm": round(span, 1), "die_edge": round(A_D, 1),
                      "die_dia": round(2 * die_cr, 1),
                      "die_f2f": round(die_f2f, 1),
                      "window_mm": [round(slot_w, 1), round(slot_h, 1)],
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
