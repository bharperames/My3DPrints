"""Unit tests for the Montessori companion parts.

The thread is cast from the designer's nut, so these tests need the source
model; models/ is untracked, so they skip cleanly without it.
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gen_montessori as GM  # noqa: E402

HAVE_SRC = os.path.exists(GM.SRC)


class TestHex(unittest.TestCase):
    def test_hexagon_circumradius(self):
        h = GM.hexagon(10.0)
        xy = np.array(h.exterior.coords)[:-1]
        self.assertEqual(len(xy), 6)
        self.assertTrue(np.allclose(np.hypot(xy[:, 0], xy[:, 1]), 10.0))


@unittest.skipUnless(HAVE_SRC, "source Montessori model not present")
class TestThread(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nut, cls.shank = GM.source_parts()

    def test_source_nut_repairs_to_watertight(self):
        self.assertTrue(self.nut.is_watertight)

    def test_plug_is_a_solid_cast_of_the_bore(self):
        plug = GM.thread_plug(self.nut, 20.0)
        self.assertTrue(plug.is_watertight)
        self.assertAlmostEqual(plug.bounds[1][2] - plug.bounds[0][2],
                               20.0, delta=0.2)
        r = np.hypot(plug.vertices[:, 0], plug.vertices[:, 1])
        # the cast reaches the female thread's root, not past it
        self.assertLess(r.max(), GM.BORE_ROOT + 0.2)

    def test_one_lead_is_the_axial_period(self):
        # translating the cast by one lead must map it onto itself: compare
        # the shifted copy's overlap with the original in the shared band
        plug = GM.thread_plug(self.nut, 24.0)
        band = plug.slice_plane([0, 0, -12 + GM.LEAD], [0, 0, 1], cap=True)
        shifted = plug.copy()
        shifted.apply_translation([0, 0, GM.LEAD])
        inter = band.intersection(shifted, engine="manifold")
        self.assertGreater(inter.volume / band.volume, 0.97)

    def test_a_wrong_lead_does_not_map_onto_itself(self):
        plug = GM.thread_plug(self.nut, 24.0)
        band = plug.slice_plane([0, 0, -12 + GM.LEAD], [0, 0, 1], cap=True)
        shifted = plug.copy()
        shifted.apply_translation([0, 0, GM.LEAD * 0.5])
        inter = band.intersection(shifted, engine="manifold")
        self.assertLess(inter.volume / band.volume, 0.90)


@unittest.skipUnless(HAVE_SRC, "source Montessori model not present")
class TestScrewVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nut, cls.shank = GM.source_parts()
        cls.good = GM.build_double_nut(cls.nut, 20.0)

    def test_real_bolt_screws_into_the_generated_thread(self):
        lead, windows = GM.screw_test(self.good, self.shank, [-3.0, 0.0, 3.0])
        self.assertIsNotNone(lead, "the designer's bolt does not fit")
        self.assertAlmostEqual(lead, GM.LEAD, delta=0.6)
        for _, _, width in windows:
            self.assertGreater(width, 6)      # a real clearance window

    def test_the_check_rejects_a_mis_stacked_thread(self):
        bad = GM.build_double_nut(self.nut, 20.0, lead=GM.LEAD * 1.18)
        lead, _ = GM.screw_test(bad, self.shank, [-3.0, 0.0, 3.0])
        if lead is not None:
            self.assertGreater(abs(lead - GM.LEAD), 0.6,
                               "a wrong lead passed the screw test")

    def test_double_nut_is_one_watertight_body(self):
        m = self.good.copy()
        m.merge_vertices()
        m.update_faces(m.nondegenerate_faces())
        m.process(validate=True)
        self.assertTrue(m.is_watertight)
        self.assertEqual(len(m.split(only_watertight=False)), 1)


if __name__ == "__main__":
    unittest.main()
