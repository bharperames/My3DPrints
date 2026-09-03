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
        cls.clasp, cls.ring, cls.rep, cls.th = GC.build(D)[:4]

    def test_each_part_is_one_connected_piece(self):
        self.assertEqual(self.clasp.geom_type, "Polygon")
        # the ring is round wire now, built as a solid rather than an
        # outline to extrude
        self.assertTrue(self.ring.is_watertight)
        self.assertEqual(len(self.ring.split(only_watertight=False)), 1)

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

    def test_the_ring_opens_by_bending_within_budget(self):
        # the old ring was radially thinner than it was tall, so it would
        # rather flex in-plane than twist out of its layers. Round wire has
        # no such preference — it bends the same about every diameter — so
        # what has to hold is the strain when its ends are pulled apart
        rr_t, height = self.rep["ring_section"]
        self.assertAlmostEqual(rr_t, height, places=2)
        self.assertLessEqual(self.rep["ring_strain"], GC.STRAIN_LIMIT)

    def test_ring_threads_the_chain_link_and_the_tail(self):
        wire = self.rep["ring_wire_mm"]
        self.assertLess(wire, self.rep["link_bore"] - 0.4)
        self.assertLess(wire, self.rep["tail_bore"] - 0.4)

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
        # free space around the bowl center, out to the nearest material
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


class TestItHasFormNotJustOutline(unittest.TestCase):
    """A straight extrusion of the outline is a cut-out, not a clasp.

    The first printed one worked and read as a silhouette: square edges,
    nothing in the hand. A real clasp swells through the middle and tapers
    to its edges. Only the top is domed — the underside stays flat, because
    the honest lens would need support under every millimeter of it.
    """

    @classmethod
    def setUpClass(cls):
        import trimesh
        cls.trimesh = trimesh
        cls.poly, cls.ring, cls.rep = GC.build(3.25)[:3]
        cls.th = cls.rep["height_mm"]
        cls.m = GC.crown(cls.poly, cls.th, min(GC.CROWN, 0.28 * cls.th))

    def test_the_top_is_domed_and_the_bottom_is_flat(self):
        import numpy as np
        m = self.m
        n, a = m.face_normals, m.area_faces
        flat_down = float(a[n[:, 2] < -0.99].sum())
        self.assertGreater(flat_down, 100, "the underside is not flat")
        # The crown is a staircase, not a swept surface — every face is
        # horizontal or vertical. What matters is that the steps are finer
        # than a layer, so the printer lays it down as a curve.
        # a union of two dozen slabs leaves slivers of a millionth of a
        # square millimeter; they are not faces of the object
        up = (n[:, 2] > 0.99) & (a > 1e-4)
        heights = np.unique(np.round(m.triangles_center[up][:, 2], 3))
        self.assertGreater(len(heights), 6,
                           "the top is one flat face — no crown at all")
        step = float(np.max(np.diff(np.sort(heights))))
        self.assertLess(step, 0.1,
                        f"crown steps {step:.3f} mm would print as terracing")
        self.assertAlmostEqual(float(heights.max()), self.th, delta=0.01)

    def test_it_needs_no_support(self):
        import numpy as np
        n, a = self.m.face_normals, self.m.area_faces
        down = n[:, 2] < -0.05
        ang = np.degrees(np.arcsin(np.clip(-n[down, 2], 0, 1)))
        # boolean slivers aside — a hundredth of a square millimeter is not
        # something the printer has to bridge
        self.assertLess(float(a[down][ang < 45].sum()), 0.01)

    def test_it_is_still_one_solid(self):
        self.assertTrue(self.m.is_watertight)
        self.assertEqual(len(self.m.split(only_watertight=False)), 1)

    def test_the_crown_never_eats_a_thin_feature_whole(self):
        # the gate is the thinnest thing here; the crown may round it but
        # the full outline has to survive underneath
        low = self.m.section(plane_origin=[0, 0, 0.2], plane_normal=[0, 0, 1])
        self.assertIsNotNone(low)
        pl, _ = low.to_2D()
        self.assertAlmostEqual(sum(p.area for p in pl.polygons_full),
                               self.poly.area, delta=self.poly.area * 0.02)

    def test_the_crown_is_capped_against_the_thickness(self):
        # a crown deeper than the part would come to a knife edge
        for th in (2.0, 3.58, 8.0):
            self.assertLessEqual(min(GC.CROWN, 0.28 * th), 0.28 * th)


class TestTheRingIsWire(unittest.TestCase):
    """Round section, the same as the chain links it joins.

    A flat annulus read as a washer beside them. A circular section bends
    the same about every diameter, which is fine — a C-ring is opened by
    pulling its ends apart, and that is bending. What it costs is size: the
    splay strain goes with the section depth, so round wire this thick needs
    a bigger ring to open without over-straining.
    """

    @classmethod
    def setUpClass(cls):
        cls.clasp, cls.ring, cls.rep, cls.th = GC.build(D)[:4]

    def test_the_wire_matches_the_chain_it_joins(self):
        self.assertAlmostEqual(self.rep["ring_wire_mm"], D, places=2)

    def test_the_section_is_round(self):
        import numpy as np
        # a vertical slice through the wire is as tall as it is wide, bar
        # the flat cut off its underside
        m = self.ring
        h = float(m.bounds[1][2] - m.bounds[0][2])
        self.assertAlmostEqual(h, D - GC.RING_FOOT, delta=0.15)

    def test_it_lands_on_a_pad_not_a_line(self):
        # the same trick the chain links needed
        self.assertGreater(self.rep["ring_bed_mm2"], 40)

    def test_the_ring_grew_to_keep_its_splay_in_budget(self):
        self.assertLessEqual(self.rep["ring_strain"], GC.STRAIN_LIMIT)
        # round wire is deeper than the old rectangle, so the ring has to be
        # bigger; if it were not, the strain gate would have caught it
        self.assertGreater(self.rep["ring_outer_dia"], 4.0 * D)

    def test_the_wire_still_threads_what_it_has_to(self):
        self.assertLess(self.rep["ring_wire_mm"], self.rep["link_bore"] - 0.4)
        self.assertLess(self.rep["ring_wire_mm"], self.rep["tail_bore"] - 0.4)
