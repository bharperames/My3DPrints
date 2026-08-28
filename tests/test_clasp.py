"""Unit tests for the lobster clasp + jump ring generator."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gen_clasp as GC  # noqa: E402

D = 3.25


def inscribed(poly):
    lo, hi = 0.0, 0.5 * min(poly.bounds[2] - poly.bounds[0],
                            poly.bounds[3] - poly.bounds[1]) + 1e-6
    for _ in range(20):
        mid = (lo + hi) / 2
        if poly.buffer(-mid).is_empty:
            hi = mid
        else:
            lo = mid
    return 2 * lo


class TestClasp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clasp, cls.ring, cls.rep, cls.th = GC.build(D)

    def test_each_part_is_one_connected_piece(self):
        self.assertEqual(self.clasp.geom_type, "Polygon")
        self.assertEqual(self.ring.geom_type, "Polygon")

    def test_gate_retains_the_link_when_closed(self):
        self.assertLess(self.rep["closed_gap_mm"], D - 0.6)

    def test_gate_opens_wide_enough_to_admit_the_link(self):
        self.assertGreaterEqual(self.rep["open_gap_mm"], D + 0.4)

    def test_thumb_tab_leaves_the_mouth_passable(self):
        self.assertGreaterEqual(self.rep["passage_mm"], D + 0.6)

    def test_flexures_stay_inside_the_elastic_budget(self):
        self.assertLessEqual(self.rep["strain"], GC.STRAIN_LIMIT)
        self.assertLessEqual(self.rep["ring_strain"], GC.STRAIN_LIMIT)

    def test_gate_slot_is_printable_not_fused(self):
        self.assertGreaterEqual(self.rep["gate_slot_mm"], 0.35)

    def test_weld_root_is_measured_not_assumed(self):
        # the gate ramps off the wall, so the free beam starts later than the
        # nominal anchor; the generator must account for that taper
        self.assertGreater(self.rep["weld_root_deg"], 1.0)

    def test_ring_opens_in_plane_not_across_layers(self):
        rr_t, height = self.rep["ring_section"]
        self.assertLess(rr_t, height)

    def test_ring_threads_the_chain_link_and_the_tail(self):
        rr_t, height = self.rep["ring_section"]
        diag = np.hypot(rr_t, height)
        self.assertLess(diag, self.rep["link_bore"] - 0.4)
        self.assertLess(diag, self.rep["tail_bore"] - 0.4)

    def test_tail_bore_is_the_only_closed_hole(self):
        # the bowl is open through the mouth by design — that is how the link
        # gets in — so the tail bore is the one enclosed void
        self.assertEqual(len(self.clasp.interiors), 1)

    def test_tail_bore_admits_the_ring_section(self):
        from shapely.geometry import Polygon
        rr_t, height = self.rep["ring_section"]
        tail = Polygon(self.clasp.interiors[0])
        self.assertGreater(inscribed(tail), np.hypot(rr_t, height),
                           "neck or wall narrows the tail bore")

    def test_link_fits_the_bowl_once_captured(self):
        from shapely.geometry import Point
        # free space around the bowl centre, out to the nearest material
        self.assertGreater(2 * Point(0, 0).distance(self.clasp), D + 1.0)

    def test_flat_extrusion_has_no_overhangs(self):
        import trimesh
        m = trimesh.creation.extrude_polygon(self.clasp, self.th)
        down = m.face_normals[:, 2] < -0.05
        # every downward face is the flat underside: nothing sloped
        self.assertTrue(bool(np.all(m.face_normals[down, 2] < -0.999)))

    def test_impossible_sizes_are_refused(self):
        with self.assertRaises(ValueError):
            GC.build(0.8)


if __name__ == "__main__":
    unittest.main()
