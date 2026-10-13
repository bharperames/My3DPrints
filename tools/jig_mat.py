#!/usr/bin/env python3
"""The orbital jig's parts mat: Letter pages, printed at actual size, with
a full-size line drawing of every small part in the order the assembly
fits it, its dimensions on it, and the label on the bag or box it came in.

Lay each part on its drawing before starting. A bolt five millimeters too
long, a nut of the wrong size, a step one piece short: each shows as a
part that does not cover its outline, and the mistake is found on the desk
rather than half way through the build.

The order is the assembly page's own: the steps come out of
gen_orbital_jig.assembly_steps, so a step added or reordered there moves
here too. Printed parts are drawn from their generated meshes, lying on
their broadest face as they rest on a desk, hidden lines removed by ray
casting toward the eye. Bought parts are drawn from BOUGHT below, at the
dimensions they are sold at -- not from the generator's collision
stand-ins, which are the holes the parts go into -- and labeled with what
is printed on their packaging (the source and part number Brett bought
them under; the global build-parts inventory is where those came from).
Parts too big for the page are drawn small in a dashed frame, marked with
their scale, to set out beside the mat; a part with no fixed shape (a
cable) gets a labeled chip.

    python3 tools/jig_mat.py [--out models/custom/orbital-jig-parts-mat.pdf]
"""
import argparse
import os
import re
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon as MPoly, Rectangle
from shapely.geometry import Polygon, Point, box as sbox
from shapely.ops import unary_union
from shapely import affinity
import trimesh
from trimesh.path.polygons import projected

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_orbital_jig as J  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "models", "custom", "orbital-jig-parts-mat.pdf")

PAGE = (215.9, 279.4)          # US Letter, mm
MARGIN = 12.0
GAP = 7.0                      # between drawings
BIG = 110.0                    # a part longer than this is drawn small
SMALL_TO = 55.0                # ... to fit this

INK = "#111111"
FILL = "#e6e9ee"               # light: a steel part reads against it
EDGE = "#1b2230"
DIM = "#2a3b55"
PT = 25.4 / 72                 # mm per point
FS = 6.5                       # label size, points
LINE_H = FS * PT * 1.35


class Drawing:
    """A part's view in mm, y down the page: a filled outline, the lines
    drawn on it, and its dimensions."""

    def __init__(self, outline, lines=(), hidden=(), dims=()):
        self.outline = outline
        self.lines = [np.asarray(l, float) for l in lines]
        self.hidden = [np.asarray(l, float) for l in hidden]
        self.dims = list(dims)          # (axis, a, b, at, text)

    def moved(self, dx, dy):
        d = Drawing(affinity.translate(self.outline, dx, dy),
                    [l + (dx, dy) for l in self.lines],
                    [l + (dx, dy) for l in self.hidden])
        for ax, a, b, at, t in self.dims:
            if ax == "x":
                d.dims.append((ax, a + dx, b + dx, at + dy, t))
            else:
                d.dims.append((ax, a + dy, b + dy, at + dx, t))
        return d

    def scaled(self, k):
        d = Drawing(affinity.scale(self.outline, k, k, origin=(0, 0)),
                    [l * k for l in self.lines], [l * k for l in self.hidden])
        d.dims = [(ax, a * k, b * k, at * k, t) for ax, a, b, at, t in self.dims]
        return d

    @property
    def bounds(self):
        return self.outline.bounds

    def at_origin(self):
        """Moved so nothing -- outline or dimension -- falls left of or
        above the origin."""
        x0, y0, _, _ = self.bounds
        for ax, a, b, at, t in self.dims:
            if ax == "y":
                x0 = min(x0, at - 2.5)
            else:
                y0 = min(y0, at - 3.0)
        return self.moved(-x0, -y0)


def _fmt(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _rect_lines(x0, y0, x1, y1):
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]


def _circle(cx, cy, r, n=96):
    a = np.linspace(0, 2 * np.pi, n + 1)
    return np.c_[cx + r * np.cos(a), cy + r * np.sin(a)]


# --- bought parts, drawn ------------------------------------------------
def socket_screw(length, d=3.0, head_d=5.5, head_h=3.0, thread=None):
    """A socket-head cap screw on its side: head, then shank, with the
    thread's minor diameter drawn thin along it."""
    r, R = d / 2, head_d / 2
    o = unary_union([sbox(0, -R, head_h, R), sbox(head_h, -r, head_h + length, r)])
    x1 = head_h + length
    tl = length if thread is None else thread
    m = r * 0.8
    lines = [[(head_h, -R), (head_h, R)],                  # the head's face
             [(0.4, -R), (0.4, R)],                         # its chamfer
             [(x1 - tl, -m), (x1, -m)], [(x1 - tl, m), (x1, m)]]
    hidden = [[(0, -head_d * 0.22), (head_h * 0.55, -head_d * 0.22)],
              [(0, head_d * 0.22), (head_h * 0.55, head_d * 0.22)]]   # the key
    return Drawing(o, lines, hidden,
                   [("x", head_h, x1, R + 3.0, _fmt(length)),
                    ("y", -r, r, x1 + 3.0, f"\u00d8{_fmt(d)}")])


def set_screw(length=8.0, d=3.0):
    r, m = d / 2, d / 2 * 0.8
    o = sbox(0, -r, length, r)
    return Drawing(o, [[(0, -m), (length, -m)], [(0, m), (length, m)]],
                   [[(0, -0.75), (2.0, -0.75)], [(0, 0.75), (2.0, 0.75)]],
                   [("x", 0, length, r + 3, _fmt(length)), ("y", -r, r, length + 3, "Ø3")])


def hex_nut(af, hole, label_t):
    rc = af / np.sqrt(3)
    pts = [(rc * np.cos(a), rc * np.sin(a)) for a in np.radians(np.arange(30, 390, 60))]
    o = Polygon(pts).difference(Point(0, 0).buffer(hole / 2 * 0.85, 64))
    return Drawing(o, [_circle(0, 0, af / 2 * 0.95), _circle(0, 0, hole / 2)],
                   dims=[("y", -af / 2, af / 2, rc + 3, f"{_fmt(af)} AF"),
                         ("x", -rc, rc, af / 2 + 3, label_t)])


def square_nut(a=8.0, hole=5.0, t=4.0):
    o = sbox(-a / 2, -a / 2, a / 2, a / 2).difference(Point(0, 0).buffer(hole / 2 * 0.85, 64))
    return Drawing(o, [_circle(0, 0, hole / 2)],
                   dims=[("x", -a / 2, a / 2, a / 2 + 3, f"{_fmt(a)} sq, {_fmt(t)} thick"),
                         ("y", -a / 2, a / 2, a / 2 + 3, _fmt(a))])


def disc(d, hole=0.0, rings=(), t=None):
    o = Point(0, 0).buffer(d / 2, 128)
    if hole:
        o = o.difference(Point(0, 0).buffer(hole / 2, 128))
    lines = [_circle(0, 0, dd / 2) for dd in rings]       # diameters
    if hole:
        lines.append(_circle(0, 0, hole / 2))
    lab = f"Ø{_fmt(d)}" + (f" x {_fmt(t)}" if t else "")
    dims = [("x", -d / 2, d / 2, d / 2 + 3, lab)]
    if hole:
        dims.append(("y", -hole / 2, hole / 2, d / 2 + 3, f"Ø{_fmt(hole)}"))
    return Drawing(o, lines, dims=dims)


def dowel(length, d):
    r, c = d / 2, 0.4
    o = Polygon([(c, -r), (length - c, -r), (length, -r + c), (length, r - c),
                 (length - c, r), (c, r), (0, r - c), (0, -r + c)])
    return Drawing(o, [[(c, -r), (c, r)], [(length - c, -r), (length - c, r)]],
                   dims=[("x", 0, length, r + 3, _fmt(length)),
                         ("y", -r, r, length + 3, f"Ø{_fmt(d)}")])


def insert(length=5.7, d=4.6):
    r = d / 2
    o = sbox(0, -r, length, r)
    lines = [[(length * 0.12, -r), (length * 0.12, r)], [(length * 0.88, -r), (length * 0.88, r)]]
    for k in range(5):                                         # the knurl
        x = length * (0.18 + 0.13 * k)
        lines.append([(x, -r), (x + length * 0.1, r)])
    return Drawing(o, lines, dims=[("x", 0, length, r + 3, _fmt(length)),
                                   ("y", -r, r, length + 3, f"Ø{_fmt(d)}")])


def thumbscrew(length=J.THUMB_LEN):
    # wings flat on the desk: the wing's face, the hub, then the shank
    w = sbox(0, -13.0, 11.0, 13.0).buffer(-2.5).buffer(2.5)
    o = unary_union([w, sbox(11.0, -5.5, 13.0, 5.5), sbox(13.0, -2.5, 13.0 + length, 2.5)])
    x1 = 13.0 + length
    return Drawing(o, [[(11.0, -5.5), (11.0, 5.5)], [(13.0, -2.5), (13.0, 2.5)],
                       [(13.0, -2.0), (x1, -2.0)], [(13.0, 2.0), (x1, 2.0)]],
                   dims=[("x", 13.0, x1, 13 + 3, _fmt(length)),
                         ("y", -13.0, 13.0, -3.0, "26"),
                         ("y", -2.5, 2.5, x1 + 3, "M5")])


def hex_bolt(af, head_h, length, d):
    r = d / 2
    # on a flat: the head shows two faces, split at its centre
    o = unary_union([sbox(0, -af / 2, head_h, af / 2), sbox(head_h, -r, head_h + length, r)])
    x1 = head_h + length
    return Drawing(o, [[(0, 0), (head_h, 0)], [(head_h, -af / 2), (head_h, af / 2)],
                       [(head_h, -r * 0.8), (x1, -r * 0.8)], [(head_h, r * 0.8), (x1, r * 0.8)]],
                   dims=[("x", head_h, x1, af / 2 + 3, "1/2 in (12.7)"),
                         ("y", -af / 2, af / 2, -3.0, "7/16 AF")])


def board(l, w, extra=()):
    o = sbox(0, 0, l, w)
    lines = _rect_lines(0.8, 0.8, l - 0.8, w - 0.8) + list(extra)
    return Drawing(o, lines, dims=[("x", 0, l, w + 3, _fmt(l)), ("y", 0, w, l + 3, _fmt(w))])


def gearmotor():
    m = J.MOTOR
    s, g, b, e = m["shaft_l"], m["gearbox"], m["body"], m["enc"]
    w, ew = m["w"], m["enc_w"]
    o = unary_union([sbox(0, -1.5, s, 1.5), sbox(s, -w / 2, s + g + b, w / 2),
                     sbox(s + g + b, -ew / 2, s + g + b + e, ew / 2)])
    x1 = s + g + b + e
    return Drawing(o, [[(s + g, -w / 2), (s + g, w / 2)], [(s, 1.0), (s, 1.5)],
                       [(s + g + b, -w / 2), (s + g + b, w / 2)],
                       [(0, 1.0), (s * 0.7, 1.0)]],                      # the D flat
                   dims=[("x", s, x1, ew / 2 + 3, _fmt(g + b + e) + " + shaft " + _fmt(s)),
                         ("y", -w / 2, w / 2, x1 + 3, _fmt(w))])


def hall():
    wd, t, _ = J.HALL
    leads = [sbox(t, y - 0.22, t + 14.0, y + 0.22) for y in (-1.27, 0.0, 1.27)]
    o = unary_union([sbox(0, -wd / 2, t, wd / 2)] + leads)
    return Drawing(o, [[(t * 0.35, -wd / 2), (t * 0.35, wd / 2)]],
                   dims=[("y", -wd / 2, wd / 2, -3.0, _fmt(wd))])


# (match, name, packaging, drawing or None, note). First match wins.
# The packaging is what is printed on the bag or box: Brett's source and
# part number.
BOUGHT = [
    (r"^M3x35$", "M3 x 35 socket screw", "McMaster 91292A033 (bag of 25)",
     lambda m: socket_screw(35.0, thread=18.0), "partly threaded"),
    (r"^M3x(\d+)$", lambda m: f"M3 x {m.group(1)} socket screw",
     lambda m: f"VIGRUE M3 kit, the M3x{m.group(1)} cell",
     lambda m: socket_screw(float(m.group(1))), ""),
    (r"heat-set insert", "M3 heat-set insert", "ruthex box, M3 x 5.7 row",
     lambda m: insert(), "check the length"),
    (r"disc magnet", "Ø3 x 2 N52 magnet", "MEALOS 3 x 2 mm",
     lambda m: disc(J.MAGNET[0], t=J.MAGNET[1]), "on its face"),
    (r"steel dowel", "Ø3 x 16 dowel pin", "McMaster 91595A116",
     lambda m: dowel(J.PIN_L, 2 * J.PIN_R), ""),
    (r"set screw", "M3 x 8 set screw, cup point", "McMaster 91390A101 (black)",
     lambda m: set_screw(), ""),
    (r"^M3 hex nut$", "M3 hex nut", "VIGRUE M3 kit, the nut cell",
     lambda m: hex_nut(5.5, 3.0, "M3, 2.4 thick"), "flat"),
    (r"M5 square nut", "M5 square nut", "McMaster 90225A101",
     lambda m: square_nut(), "flat"),
    (r"thumbscrew", "M5 x 40 wing thumbscrew", "McMaster 92595A314",
     lambda m: thumbscrew(), "wings flat"),
    (r"spring clamp", "phone spring clamp", "ULANZI ST-02S", None, ""),
    (r"1/4-20", "1/4-20 x 1/2 hex bolt", "McMaster 92245A537",
     lambda m: hex_bolt(J.QTR_HEAD[0], 5 / 32 * 25.4, J.QTR_LEN, 6.35), "on a flat"),
    (r"688-2RS", "688-2RS bearing, 8 x 16 x 5", "FUSHIBEARING (blue seals)",
     lambda m: disc(16.0, 8.0, rings=(13.6,), t=5.0), "flat"),
    (r"V wheel", "V wheel, Delrin", "SIMAX3D V-slot wheels",
     lambda m: disc(2 * J.WHEEL["r"], 16.0, rings=(2 * J.WHEEL["side_r"],), t=J.WHEEL["w"]),
     "flat; 625s out, 688s in"),
    (r"SS451A", "Hall sensor SS451A", "Digi-Key 480-3587-ND",
     lambda m: hall(), "marked face down"),
    (r"XIAO", "Seeed XIAO ESP32S3", "Digi-Key 1597-113991114-ND",
     lambda m: board(J.XIAO[0], J.XIAO[1],
                     extra=_rect_lines(-1.5, J.XIAO[1] / 2 - 4.5, 1.0, J.XIAO[1] / 2 + 4.5)),
     "USB-C at the left"),
    (r"DRV8833", "Pololu #2130 DRV8833", "Digi-Key 2183-2130-ND",
     lambda m: board(J.DRV8833[0], J.DRV8833[1]), ""),
    (r"Gearmotor", "Pololu #5173 gearmotor", "Digi-Key 2183-5173-ND",
     lambda m: gearmotor(), "on its side"),
    (r"4\.7 ohm", "4.7 Ω 2 W resistor", "Digi-Key RSMF2JT4R70CT-ND", None,
     "bands yellow violet gold gold"),
    (r"10 kohm", "10 kΩ resistor", "Digi-Key CF14JT10K0CT-ND", None,
     "bands brown black orange gold"),
    (r"uF", "100 µF capacitor", "Digi-Key P14391-ND", None, "the can"),
    (r"JST SH cable", "6-pin JST SH cable, 75 cm", "Pololu #4764", None, ""),
    (r"USB-C", "USB-C cable and 5 V charger", "Anker 65 W", None, ""),
    (r"rod field plate", "rod field plate, jig mount", "printed from its own card", None, ""),
]

NAMES = {"stator": "base", "rotor": "ring", "arc": "arc", "saddle": "saddle",
         "shoe": "shoe", "receiver": "receiver", "ctrl_box": "controller box",
         "ctrl_lid": "controller lid", "drive_block": "drive block",
         "drive_cap": "drive lid", "driver": "driver (crank)",
         "driver_shim": "driver shim", "mount_screw": "mount screw",
         "mount_wing_nut": "wing nut", "mount_hex_nut": "hex nut (spare)",
         "puck": "puck", "sleeve": "eccentric sleeve"}


def bought(item):
    for pat, name, pkg, draw, note in BOUGHT:
        m = re.search(pat, item)
        if m:
            f = lambda v: v(m) if callable(v) else v
            return f(name), f(pkg), (draw(m) if draw else None), note
    return item.split("(")[0].split(",")[0].strip(), "", None, ""


# --- printed parts, drawn from their meshes --------------------------------
def printed(mesh):
    """Hidden-line view of a part resting on its broadest face, its long
    side across the page: the outline, plus every crease and every
    silhouette line of a curved face that the eye can see."""
    obb = mesh.bounding_box_oriented
    m = mesh.copy()
    m.apply_transform(np.linalg.inv(obb.primitive.transform))
    k = int(np.argmin(m.extents))
    # the face it rests on: whichever end of that axis is flatter
    n = np.eye(3)[k]
    a = m.area_faces
    lo = a[(m.face_normals @ -n) > 0.99].sum()
    hi = a[(m.face_normals @ n) > 0.99].sum()
    eye = n if lo >= hi else -n                 # rests on the bigger flat
    # the frame projected() draws the outline in, so the lines land on it
    to_2d = trimesh.geometry.plane_transform(origin=None, normal=eye)
    outline = projected(m, normal=eye, ignore_sign=False, rpad=1e-4, tol_dot=1e-3)
    if outline is None:
        return None
    if outline.geom_type == "MultiPolygon":
        outline = max(outline.geoms, key=lambda g: g.area)
    # creases, and the silhouettes of curved faces
    ang = m.face_adjacency_angles
    fa = m.face_adjacency
    dots = m.face_normals[fa] @ eye
    keep = (ang > np.radians(25)) | (np.sign(dots[:, 0]) != np.sign(dots[:, 1]))
    keep &= ~((dots[:, 0] < -1e-3) & (dots[:, 1] < -1e-3))      # back faces only
    E = m.vertices[m.face_adjacency_edges[keep]]
    # visible where three samples along it see the eye unobstructed
    ts = (0.2, 0.5, 0.8)
    pts = np.concatenate([E[:, 0] * (1 - t) + E[:, 1] * t for t in ts])
    hit = m.ray.intersects_any(pts + eye * 0.02, np.tile(eye, (len(pts), 1)))
    vis = (~hit.reshape(len(ts), -1)).sum(0) >= 2
    segs = trimesh.transform_points(E[vis].reshape(-1, 3), to_2d)[:, :2].reshape(-1, 2, 2)
    d = Drawing(outline, [s for s in segs])
    # orient: long side along x, y down the page
    rect = d.outline.minimum_rotated_rectangle
    xy = np.asarray(rect.exterior.coords)[:3]
    e0, e1 = xy[1] - xy[0], xy[2] - xy[1]
    ev = e0 if np.linalg.norm(e0) >= np.linalg.norm(e1) else e1
    th = -np.arctan2(ev[1], ev[0])
    c, s = np.cos(th), np.sin(th)
    R = np.array([[c, -s], [s, c]])
    out = Drawing(affinity.rotate(d.outline, th, origin=(0, 0), use_radians=True),
                  [l @ R.T for l in d.lines])
    x0, y0, x1, y1 = out.bounds
    out.dims = [("x", x0, x1, y1 + 3, _fmt(x1 - x0)), ("y", y0, y1, x1 + 3, _fmt(y1 - y0))]
    return out


def body_name(n):
    base = re.sub(r"_([abc])$", "", n)
    return NAMES.get(n, NAMES.get(base, base.replace("_", " ")))


# --- what goes on the mat --------------------------------------------------
def entries():
    parts = J.assemble(J.SPECIMEN)
    steps = J.assembly_steps(parts, J.SPECIMEN)
    cache, out = {}, []
    for i, st in enumerate(steps, 1):
        groups = []
        for n in st["bodies"]:
            name = body_name(n)
            if groups and groups[-1].get("body") and groups[-1]["name"] == name:
                groups[-1]["qty"] += 1
                continue
            if name not in cache:
                cache[name] = printed(parts[n])
            d = cache[name]
            groups.append(dict(name=name, qty=1, pkg="printed", draw=d, note="",
                               body=True))
        for h in st["hardware"]:
            if not h["item"] or not h["qty"]:
                continue
            nm, pkg, d, note = bought(h["item"])
            groups.append(dict(name=nm, qty=h["qty"], pkg=pkg, draw=d, note=note))
        if groups:
            out.append(dict(n=i, title=st["title"], groups=groups))
    return out


# --- layout ------------------------------------------------------------------
def text_w(s):
    return len(s) * FS * PT * 0.56 + 1.0


def block(g):
    """A group's footprint: drawings (one per piece), dims, two lines of
    label. Returns (w, h, spec)."""
    qty = g["qty"]
    head = (f"{qty} × " if qty > 1 else "") + g["name"]
    lab = [head, g["pkg"] + (f" — {g['note']}" if g["note"] else "")]
    tw = max(text_w(s) for s in lab)
    d = g["draw"]
    if d is None:
        return tw + 4, 2 * LINE_H + 3, ("chip", lab)
    d = d.at_origin()
    scale = 1.0
    x0, y0, x1, y1 = d.bounds
    if max(x1, y1) > BIG:
        scale = SMALL_TO / max(x1, y1)
        d = d.scaled(scale)
        d.dims = []
        lab[1] = f"printed — drawn at 1:{1 / scale:.0f}, set it beside the mat"
        qty_draw = 1
    else:
        qty_draw = qty
    _, _, w, h = d.bounds
    stack = w > 45 and qty_draw > 1
    pad_r = 7.0 if d.dims else 0
    pad_b = 6.0 if d.dims else 0
    sp = 3.0 + (pad_r if not stack else 0)
    pw = w if stack else qty_draw * w + (qty_draw - 1) * sp
    ph = qty_draw * (h + (pad_b if stack else 0)) + (qty_draw - 1) * 3 if stack else h
    bw = max(pw + pad_r, tw)
    bh = ph + pad_b + 1 + 2 * LINE_H
    return bw, bh, ("draw", d, qty_draw, stack, sp, pad_b, lab, scale != 1.0)


def layout(es):
    W = PAGE[0] - 2 * MARGIN
    pages, ops, y = [], [], MARGIN + 8
    bottom = PAGE[1] - MARGIN - 9
    for e in es:
        rows, row, x, rh = [], [], 0.0, 0.0
        for g in e["groups"]:
            w, h, spec = block(g)
            if row and x + w > W:
                rows.append((row, rh))
                row, x, rh = [], 0.0, 0.0
            row.append((x, spec))
            x += w + GAP
            rh = max(rh, h)
        if row:
            rows.append((row, rh))
        need = 7 + sum(r[1] + 4 for r in rows)
        if y + need > bottom and ops:
            pages.append(ops)
            ops, y = [], MARGIN + 8
        ops.append(("head", y, e["n"], e["title"]))
        y += 7
        for row, rh in rows:
            for x, spec in row:
                ops.append(("item", MARGIN + x, y, spec))
            y += rh + 4
        ops.append(("rule", y - 2))
        y += 2
    pages.append(ops)
    return pages


# --- drawing ------------------------------------------------------------------
def arrow(ax, p, q):
    ax.annotate("", xy=q, xytext=p, arrowprops=dict(arrowstyle="<|-|>", lw=0.35,
                color=DIM, mutation_scale=4, shrinkA=0, shrinkB=0))


def draw(ax, d, x, y, dims=True, small=False):
    d = d.moved(x, y)
    geoms = [d.outline] if d.outline.geom_type == "Polygon" else list(d.outline.geoms)
    for p in geoms:
        ax.add_patch(MPoly(np.asarray(p.exterior.coords), closed=True, facecolor=FILL,
                           edgecolor=EDGE, lw=0.6, joinstyle="round"))
        for hole in p.interiors:
            ax.add_patch(MPoly(np.asarray(hole.coords), closed=True, facecolor="white",
                               edgecolor=EDGE, lw=0.6))
    if d.lines:
        ax.add_collection(LineCollection(d.lines, colors=EDGE, linewidths=0.3,
                                         capstyle="round"))
    if d.hidden:
        ax.add_collection(LineCollection(d.hidden, colors=EDGE, linewidths=0.25,
                                         linestyles=(0, (1.2, 0.8))))
    if not dims:
        return
    for axis, a, b, at, t in d.dims:
        if axis == "x":
            x0, x1 = a, b
            ext_from = max(0, min(at - 3.5, at))
            ax.plot([x0, x0], [at - 2.2, at + 0.8], color=DIM, lw=0.25)
            ax.plot([x1, x1], [at - 2.2, at + 0.8], color=DIM, lw=0.25)
            arrow(ax, (x0, at), (x1, at))
            ax.text((x0 + x1) / 2, at - 0.5, t, fontsize=5.5, color=DIM, ha="center",
                    va="bottom", bbox=dict(facecolor="white", edgecolor="none", pad=0.3))
        else:
            ax.plot([at - 2.2, at + 0.8], [a, a], color=DIM, lw=0.25)
            ax.plot([at - 2.2, at + 0.8], [b, b], color=DIM, lw=0.25)
            arrow(ax, (at, a), (at, b))
            ax.text(at + 0.6, (a + b) / 2, t, fontsize=5.5, color=DIM, ha="left",
                    va="center", rotation=0,
                    bbox=dict(facecolor="white", edgecolor="none", pad=0.3))


def frame(ax, page, pages):
    ax.text(MARGIN, MARGIN - 3, "Orbital scanning jig — parts mat",
            fontsize=11, weight="bold", color=INK, va="baseline")
    ax.text(MARGIN, MARGIN + 2, "Every part at full size, in the order it goes in. "
            "Lay each one on its drawing; one that does not cover it is the wrong part.",
            fontsize=7, color=INK, va="baseline")
    ax.text(PAGE[0] - MARGIN, MARGIN - 3, f"page {page} of {pages}",
            fontsize=8, color=INK, ha="right", va="baseline")
    y = PAGE[1] - MARGIN + 2
    ax.add_patch(Rectangle((MARGIN, y), 100, 1.6, facecolor=INK, lw=0))
    for k in range(11):
        ax.plot([MARGIN + 10 * k] * 2, [y, y - 2.2], color=INK, lw=0.5)
    ax.text(MARGIN + 103, y + 1.5,
            "100 mm. Measure it: if it is not, reprint at Actual size (100%).",
            fontsize=7, color=INK, va="baseline")


def render(pages, out):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with PdfPages(out) as pdf:
        for k, ops in enumerate(pages, 1):
            fig = plt.figure(figsize=(PAGE[0] / 25.4, PAGE[1] / 25.4))
            ax = fig.add_axes([0, 0, 1, 1])
            ax.set_xlim(0, PAGE[0])
            ax.set_ylim(PAGE[1], 0)
            ax.set_aspect("equal")
            ax.axis("off")
            frame(ax, k, len(pages))
            for op in ops:
                if op[0] == "head":
                    _, y, n, title = op
                    ax.text(MARGIN, y + 3.5, f"Step {n}", fontsize=9, weight="bold",
                            color=INK, va="baseline")
                    ax.text(MARGIN + 16, y + 3.5, title, fontsize=9, color=INK,
                            va="baseline")
                elif op[0] == "rule":
                    ax.plot([MARGIN, PAGE[0] - MARGIN], [op[1]] * 2, color="#7d8796", lw=0.3)
                else:
                    _, x, y, spec = op
                    if spec[0] == "chip":
                        lab = spec[1]
                        w = max(text_w(s) for s in lab) + 4
                        ax.add_patch(Rectangle((x, y), w, 2 * LINE_H + 2, facecolor="white",
                                               edgecolor=EDGE, lw=0.4, linestyle=(0, (2, 1))))
                        for i, s in enumerate(lab):
                            ax.text(x + 2, y + 1 + (i + 0.8) * LINE_H, s, fontsize=FS,
                                    color=INK, va="baseline", weight="bold" if i == 0 else "normal")
                        continue
                    _, d, n, stack, sp, pad_b, lab, small = spec
                    _, _, w, h = d.bounds
                    for i in range(n):
                        dx, dy = (0, i * (h + pad_b + 3)) if stack else (i * (w + sp), 0)
                        draw(ax, d, x + dx, y + dy, dims=(i == 0))
                    if small:
                        ax.add_patch(Rectangle((x - 1.5, y - 1.5), w + 3, h + 3, fill=False,
                                               edgecolor=EDGE, lw=0.4, linestyle=(0, (3, 2))))
                    ph = n * (h + pad_b + 3) - 3 - pad_b if stack else h
                    ty = y + ph + pad_b + 1
                    for i, s in enumerate(lab):
                        ax.text(x, ty + (i + 0.8) * LINE_H, s, fontsize=FS, color=INK,
                                va="baseline", weight="bold" if i == 0 else "normal")
            pdf.savefig(fig)
            plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    es = entries()
    pages = layout(es)
    render(pages, a.out)
    print(f"wrote {os.path.relpath(a.out)}: {len(es)} steps on {len(pages)} pages")


if __name__ == "__main__":
    main()
