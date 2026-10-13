#!/usr/bin/env python3
"""Two small prints that answer a question before the big ones are made,
cut from the orbital jig's own constants so they cannot drift from it.

race coupon      30 degrees of the rotor ring, its V groove and all, to
                 seat a real V wheel in before the 4 h ring is printed.
insert practice  the jig's heat-set insert seats, to learn the iron on:
                 three posts the size of the base's towers with an insert
                 bore in the top, and three bores flush in a flat face,
                 the way the pucks, the rotor's pad and the receiver take
                 theirs. Every bore is the jig's -- INS_M3 deep, with the
                 bolt's relief under it -- so what works here works there.

    python3 tools/jig_fit_pieces.py [--out DIR]
"""
import argparse
import os
import sys

import numpy as np
import trimesh
from shapely.geometry import Polygon

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_orbital_jig as J  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "models", "custom", "orbital-jig-fit", "pieces")

COUPON_DEG = 30.0


def race_coupon():
    """The ring's section swept through COUPON_DEG, on its underside as the
    ring prints."""
    ring = J.rev(J.ring_profile(), sections=360)
    h = J.RING_T + 2
    a = np.radians(COUPON_DEG / 2)
    R = J.RING_RO + 20
    wedge = trimesh.creation.extrude_polygon(
        Polygon([(0, 0), (R * np.cos(a), -R * np.sin(a)), (R, 0),
                 (R * np.cos(a), R * np.sin(a))]), h)
    wedge.apply_translation([0, 0, -1])
    return trimesh.boolean.intersection([ring, wedge], engine="manifold")


def insert_practice(posts=3, flush=3, post_h=12.0, plate_t=10.0, pitch=18.0):
    """Posts like the towers and flush bores like the pucks, each with the
    jig's insert bore and the bolt's relief under it."""
    ins_r, ins_d = J.INS_M3
    relief = 1.5                                   # the joint table's tip room
    n = posts + flush
    L = (n - 1) * pitch + 2 * 12.0
    W = 2 * J.TOWER_R + 12.0
    plate = trimesh.creation.box(extents=[L, W, plate_t])
    plate.apply_translation([L / 2 - 12.0, 0, plate_t / 2])
    solids, tools = [plate], []
    for i in range(n):
        x = i * pitch
        if i < posts:
            post = J.cyl(J.TOWER_R, plate_t - 0.5, plate_t + post_h, x, 0, 96)
            solids.append(post)
            top = plate_t + post_h
        else:
            top = plate_t
        tools.append(J.cyl(ins_r, top - ins_d, top + 1, x, 0, 48))
        tools.append(J.cyl(J.BOLT_R, top - ins_d - relief, top, x, 0, 48))
    return J.cut(J.union(solids), tools)


def write(m, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = m.bounds.mean(0)
    m.apply_translation([-c[0], -c[1], -m.bounds[0][2]])
    trimesh.Scene({os.path.splitext(os.path.basename(path))[0]: m}).export(path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    for name, m in (("race-coupon", race_coupon()), ("insert-practice", insert_practice())):
        assert m.is_watertight, name
        p = write(m, os.path.join(a.out, name + ".3mf"))
        print(f"{name}: {m.extents.round(1)} mm, {m.volume / 1000:.1f} cm3 -> {os.path.relpath(p)}")


if __name__ == "__main__":
    main()
