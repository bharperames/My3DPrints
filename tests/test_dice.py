"""Unit tests for the dice-orb generator: numerals, seat, captivity."""
import os
import sys
import unittest

import numpy as np
import trimesh
from shapely.geometry import box as sbox

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gen_dice_cage as G  # noqa: E402

TEXTS = [str(i) for i in range(1, 21)]


class TestNumerals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cap, cls.plan = G.numeral_plan(TEXTS)

    def test_all_twenty_render(self):
        for t in TEXTS:
            shape = self.plan[t][0]
            self.assertIsNotNone(shape, f"numeral {t} failed")
            self.assertGreater(shape.area, 1.0, f"numeral {t} degenerate")

    def test_four_survives_ring_nesting(self):
        # Arial's "4" has an outer contour whose representative point falls
        # inside its own counter — a point-in-ring test cancels the glyph
        raw = G._raw_glyph("4")
        self.assertIsNotNone(raw)
        self.assertGreater(raw.area, 0.1)
        self.assertEqual(len(G._counters(raw)), 1)

    def test_one_has_no_base_serif(self):
        g = G._raw_glyph("1")
        x0, y0, x1, y1 = g.bounds
        h = y1 - y0

        def band(lo, hi):
            b = g.intersection(sbox(x0 - 1, y0 + lo * h, x1 + 1, y0 + hi * h))
            return 0.0 if b.is_empty else b.bounds[2] - b.bounds[0]

        # a serifed "1" has a foot bar several times the stem width
        self.assertLess(band(0.0, 0.08) / band(0.45, 0.55), 1.35)

    def test_strokes_and_counters_clear_the_nozzle(self):
        self.assertGreaterEqual(min(self.plan[t][1] for t in TEXTS),
                                G.MIN_STROKE)
        self.assertGreaterEqual(min(self.plan[t][2] for t in TEXTS),
                                G.MIN_COUNTER)

    def test_every_numeral_fits_its_face(self):
        for t in TEXTS:
            shape, _, _, flip = self.plan[t]
            self.assertTrue(shape.within(G.face_polygon(G.NUM_MARGIN,
                                                        bool(flip))),
                            f"numeral {t} overruns the face")

    def test_six_and_nine_are_underlined(self):
        for t in ("6", "9"):
            plain = G.render(t, G._raw_glyph(t), self.cap, 0.0)[0]
            marked = self.plan[t][0]
            self.assertGreater(marked.area, plain.area * 1.05,
                               f"{t} carries no underline")

    def test_counter_metric_is_inscribed_not_2a_over_p(self):
        # 2A/P reads the inradius on a triangle: half its inscribed diameter
        tri = G.face_polygon(0.0, False)
        self.assertAlmostEqual(G._inscribed_dia(tri),
                               2 * (2 * tri.area / tri.length), delta=0.05)

    def test_antipodal_numbering_sums_21(self):
        die = trimesh.creation.icosahedron()
        cents = die.triangles_center
        order = [None] * 20
        used, n_lo = set(), 1
        for fi in range(20):
            if fi in used:
                continue
            anti = int(np.argmin([np.dot(cents[fi], cents[j])
                                  for j in range(20)]))
            order[fi] = n_lo
            order[anti] = 21 - n_lo
            used.update((fi, anti))
            n_lo += 1
        self.assertEqual(sorted(order), list(range(1, 21)))
        for fi in range(20):
            anti = int(np.argmin([np.dot(cents[fi], cents[j])
                                  for j in range(20)]))
            self.assertEqual(order[fi] + order[anti], 21)


class TestGeometry(unittest.TestCase):
    """Design invariants, computed the same way the generator does."""

    def setUp(self):
        self.R, self.sr = G.DIA / 2, G.STRUT / 2
        self.face_in = G.A_D / (2 * np.sqrt(3))
        self.f2f = 2 * self.face_in * 2.618
        self.extract_r = max(2 * G.SLEEVE_OUT, G.BASE_R)
        self.win_r = self.extract_r + self.sr + 0.9

    def test_standard_die(self):
        self.assertAlmostEqual(self.f2f, 20.4, delta=0.2)

    def test_top_aperture_is_a_seat_not_an_exit(self):
        seat_in = self.face_in - G.SEAT_LEDGE
        self.assertLess(seat_in, self.face_in)          # the face rests on it
        top_r = 2 * seat_in
        self.assertGreater(self.f2f, 2 * (top_r - self.sr) + 1.0)

    def test_die_captive_at_every_opening(self):
        win_open = 2 * (self.win_r - self.sr)
        self.assertGreater(self.f2f, win_open + 1.0)
        ring_arc = 2 * np.pi * self.R / G.RIBS
        self.assertGreater(self.f2f, ring_arc - G.STRUT + 1.0)

    def test_die_face_catches_on_the_bottom_rim(self):
        # face corners must span wider than the polar window, or the die
        # drops into the hole and touches the table
        win_open = 2 * (self.win_r - self.sr)
        self.assertGreater(2 * (G.A_D / np.sqrt(3)), win_open + 1.0)

    def test_sleeve_drops_out_through_the_window(self):
        self.assertLess(self.extract_r, self.win_r - self.sr - 0.5)

    def test_anchors_sit_on_the_face_clear_of_the_numeral(self):
        anchor_r = 2 * (G.SLEEVE_OUT - G.WALL_T / 2)
        self.assertLess(anchor_r + G.ANCHOR_W_LO / 2, G.A_D / np.sqrt(3))
        self.assertGreater(anchor_r, self.face_in)      # outside the numeral

    def test_anchor_weld_is_lighter_than_the_proven_one(self):
        # the printed design welded 8.1 mm2 and separated cleanly
        self.assertLess(3 * G.ANCHOR_L * G.ANCHOR_W_HI, 8.1)

    def test_every_arc_within_the_proven_span(self):
        seat_in = self.face_in - G.SEAT_LEDGE
        lat_s = -np.degrees(np.arccos(self.win_r / self.R))
        lat_n = np.degrees(np.arccos(2 * seat_in / self.R))
        n = int(np.ceil(np.radians(lat_n - lat_s) * self.R / G.SPAN_LIMIT))
        rib_arc = np.radians((lat_n - lat_s) / n) * self.R
        self.assertLessEqual(rib_arc, G.SPAN_LIMIT + 0.05)
        self.assertLessEqual(2 * np.pi * self.R / G.RIBS, G.SPAN_LIMIT + 0.05)


class TestPrimitives(unittest.TestCase):
    def test_rib_is_one_smooth_capped_arc(self):
        m = G.rib_tube(29.0, 1.1, -73.8, 77.3, 0.0)
        self.assertTrue(m.is_watertight)
        v = m.vertices
        lat = np.degrees(np.arctan2(v[:, 2], np.hypot(v[:, 0], v[:, 1])))
        self.assertAlmostEqual(lat.min(), -73.8, delta=1.5)
        self.assertAlmostEqual(lat.max(), 77.3, delta=1.5)
        # every point sits on the sphere: no beads standing proud of it
        rad = np.linalg.norm(v, axis=1)
        self.assertLess(rad.max(), 29.0 + 1.1 + 0.02)

    def test_taper_narrows_upward(self):
        m = G.taper(np.array([5.0, 0.0]), np.array([1.0, 0.0]), 0.0, 2.0,
                    2.4, 1.6, 0.8)
        self.assertTrue(m.is_watertight)
        lo = m.section(plane_origin=[0, 0, 0.1], plane_normal=[0, 0, 1])
        hi = m.section(plane_origin=[0, 0, 1.9], plane_normal=[0, 0, 1])
        self.assertGreater(lo.to_2D()[0].polygons_full[0].area,
                           hi.to_2D()[0].polygons_full[0].area)

    def test_diamond_bar_has_a_45_degree_underside(self):
        bar = G.diamond_bar(np.array([-5.0, 0, 0]), np.array([5.0, 0, 0]), 1.4)
        self.assertTrue(bar.is_watertight)
        down = bar.face_normals[:, 2] < -0.1
        angs = np.degrees(np.arccos(np.clip(-bar.face_normals[down, 2], -1, 1)))
        self.assertAlmostEqual(float(np.median(angs)), 45.0, delta=2.0)


if __name__ == "__main__":
    unittest.main()
