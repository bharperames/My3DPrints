#!/usr/bin/env python3
"""Does the slicer actually leave this hole open?

A hole exists in the mesh, and it exists in the G-code, and the printed
part still has no hole. That happened here: Ø1.3 and Ø1.5 sockets for a
1 mm carbon rod came off the plate closed or needing force. The model
was right, the slicer's toolpath was right, and the thing nobody had
measured was how much clear air the toolpath actually leaves around a
hole that small.

This measures it. For every hole center, at several heights, it finds
the nearest extrusion path and reports

    free diameter = 2 x (distance to the nearest path - width / 2)

which is what a rod has to fit through. A hole a path runs straight
across reads zero, and that is the failure mode to look for: on the
first plate one or two sockets in six were crossed at some layer, so
the rod met a wall partway down.

Usage:
    gcode_holes.py FILE.gcode --holes x,y[,z] ... [--width 0.42]
    gcode_holes.py FILE.gcode --gazebo lp_s,...        (this repo's parts)

One part per slice. The offset between model and plate comes from the
object's own first layer, and with several parts on a bed there is no
honest way to tell which object is which when two of them are the same
size -- which the two rod bases are. A probe aimed at the wrong part
reports nonsense with total confidence, so this refuses instead.
"""
import argparse
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def paths(gcode):
    """Extrusion moves as sampled points, keyed by (object id, layer).

    Segmented by the slicer's own object markers, so each part can be
    registered where the slicer put IT. Registering the whole plate from
    one bounding box was the first try and it is only right when every
    part happens to share the plate's corner -- with four parts on a bed
    it put the probe meters away from the holes and reported nonsense.
    """
    x = y = z = 0.0
    obj = None
    by = {}
    for ln in open(gcode):
        if ln.startswith("; OBJECT_ID:"):
            obj = int(ln.split(":")[1])
            continue
        arc = ln.startswith(("G2 ", "G3 ", "G2\t", "G3\t"))
        if not (arc or ln.startswith(("G0", "G1"))):
            continue
        mz = re.search(r"\bZ([-\d.]+)", ln)
        if mz:
            z = float(mz.group(1))
        mx = re.search(r"\bX([-\d.]+)", ln)
        my = re.search(r"\bY([-\d.]+)", ln)
        me = re.search(r"\bE([-\d.]+)", ln)
        nx = float(mx.group(1)) if mx else x
        ny = float(my.group(1)) if my else y
        draws = me and float(me.group(1)) > 0 and obj is not None
        if draws and arc:
            # ARCS ARE NOT OPTIONAL. Bambu ships arc fitting on, and a
            # small round hole is the one feature that is nothing BUT
            # arc: 15,524 of them in the rod field. Reading only G1 was
            # wrong twice over -- the wall around every bore went unseen,
            # and the arc's endpoint was then joined to the stale
            # position by a straight chord drawn right across the hole.
            # That instrument called the probe's \u00d81.45 bore blocked,
            # a bore that had taken the rod in the hand.
            mi = re.search(r"\bI([-\d.]+)", ln)
            mj = re.search(r"\bJ([-\d.]+)", ln)
            if mi or mj:
                cx = x + (float(mi.group(1)) if mi else 0.0)
                cy = y + (float(mj.group(1)) if mj else 0.0)
                r = np.hypot(x - cx, y - cy)
                a0 = np.arctan2(y - cy, x - cx)
                a1 = np.arctan2(ny - cy, nx - cx)
                cw = ln.startswith("G2")
                d = a1 - a0
                # a move that ends where it started is a full turn, not a
                # zero-length one
                if cw:
                    while d >= 0:
                        d -= 2 * np.pi
                else:
                    while d <= 0:
                        d += 2 * np.pi
                n = max(4, int(abs(d) * r / 0.1))
                seg = by.setdefault((obj, round(z, 2)), [])
                for t in np.linspace(0.0, 1.0, n):
                    seg.append((cx + r * np.cos(a0 + d * t),
                                cy + r * np.sin(a0 + d * t)))
        elif draws and (mx or my):
            seg = by.setdefault((obj, round(z, 2)), [])
            n = max(2, int(np.hypot(nx - x, ny - y) / 0.1))
            for t in np.linspace(0.0, 1.0, n):
                seg.append((x + (nx - x) * t, y + (ny - y) * t))
        x, y = nx, ny
    return by


def object_frames(by, width=0.42):
    """Each object's footprint on the plate, from a middle layer.

    Two corrections, and without them every hole is probed in the wrong
    place. A G-code bounding box is drawn through the CENTERS of the
    outer wall, so it is half an extrusion inside the real outline on
    each side -- a 75 mm part measures 74.58. And the FIRST layer is
    smaller still, because elephant-foot compensation shrinks it: the
    same part measures 74.2 down there. Registering on the first layer
    therefore put every hole center 0.4 mm off, which read as every bore
    on the probe being 1.15 mm narrower than it was drawn -- including
    the one that had just taken the rod in the hand.
    """
    out = {}
    for obj in sorted({o for o, _ in by}):
        zs = sorted(zz for oo, zz in by if oo == obj)
        P = np.array(by[(obj, zs[len(zs) // 2])])
        lo = P.min(axis=0) - width / 2.0
        hi = P.max(axis=0) + width / 2.0
        out[obj] = dict(lo=lo, hi=hi, size=hi - lo)
    return out


def free_diameters(by_z, centers, heights, width=0.42):
    out = {}
    zs = sorted(by_z)
    for want in heights:
        zz = min(zs, key=lambda v: abs(v - want))
        P = np.array(by_z[zz])
        free = []
        for c in centers:
            r = float(np.hypot(*(P - np.asarray(c)).T).min())
            free.append(max(0.0, 2.0 * (r - width / 2.0)))
        out[zz] = free
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gcode")
    ap.add_argument("--gazebo", help="comma-separated gazebo ids to check")
    ap.add_argument("--heights", default="3,6,9")
    ap.add_argument("--width", type=float, default=0.42)
    a = ap.parse_args()
    by = paths(a.gcode)
    frames = object_frames(by)
    heights = [float(v) for v in a.heights.split(",")]
    report = {}
    if a.gazebo:
        import gen_gazebo as G
        ids = [v.strip() for v in a.gazebo.split(",") if v.strip()]
        parts = G.build(",".join(ids))
        flat, _ = G.layout(parts)
        if len(ids) != 1:
            print(json.dumps(dict(error="one part per slice: registering "
                                        "several parts on one plate is not "
                                        "reliable, and a probe aimed at the "
                                        "wrong place reports nonsense "
                                        "confidently")))
            return 1
        sid = ids[0]
        name = f"gazebo_{sid[3:]}"
        spec = G.BY_ID[sid]
        m = flat[name]
        if len(frames) != 1:
            print(json.dumps(dict(error=f"{len(frames)} objects in this "
                                        "G-code; slice the one part alone")))
            return 1
        obj = next(iter(frames))
        off = frames[obj]["lo"] - m.bounds[0][:2]
        pts = (G.field_holes(spec) if spec.get("field") else G.spikes(spec))
        dx = m.bounds[0][0] - parts[name].bounds[0][0]
        dy = m.bounds[0][1] - parts[name].bounds[0][1]
        cs = np.array(pts) + [dx, dy] + off
        zs = sorted(zz for oo, zz in by if oo == obj)
        top = float(m.bounds[1][2] - m.bounds[0][2])
        per = {}
        for want_z in heights:
            if want_z > top - 0.4:
                continue
            zz = min(zs, key=lambda v: abs(v - want_z))
            P = np.array(by[(obj, zz)])
            free = [max(0.0, 2.0 * (float(np.hypot(*(P - c).T).min())
                                    - a.width / 2.0)) for c in cs]
            # a "hole" with no extrusion within millimeters is not an
            # open hole, it is a hole that does not reach this layer --
            # counting those as open made a gauge read 20 of 20 at a
            # height where half its bores had ended
            free = [v for v in free if v < 5.0]
            per[str(zz)] = dict(
                here=len(free),
                open=int(sum(1 for v in free if v > 0.6)),
                blocked=int(sum(1 for v in free if v <= 0.6)),
                free_mean=round(float(np.mean(free)), 2) if free else None,
                free_min=round(float(min(free)), 2) if free else None,
                free_max=round(float(max(free)), 2) if free else None)
        report[sid] = dict(drawn=spec.get("rods"), holes=len(cs),
                           footprint_err=round(float(np.abs(
                               frames[obj]["size"]
                               - (m.bounds[1][:2] - m.bounds[0][:2])).sum()), 2),
                           per_layer=per)
    print(json.dumps(dict(layers=len(by), report=report), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
