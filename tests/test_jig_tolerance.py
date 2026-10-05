"""The orbital jig's tolerance stack-up: every joint and every chain,
sampled over PETG's real scatter, keeps working."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import jig_tolerance as T  # noqa: E402


class TestHoleModel(unittest.TestCase):
    def test_it_reads_what_this_printer_did(self):
        """PETG Basic took 0.45 off a drawn Ø1.45 bore (read with the rod,
        gen_gazebo.MATERIALS), and about 0.15-0.17 off a Ø3."""
        self.assertAlmostEqual(float(T.hole_loss(1.45)), 0.45, delta=0.02)
        self.assertTrue(0.14 <= float(T.hole_loss(3.0)) <= 0.19)


class TestStack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # the Geneva's window takes minutes to map; use it when it is there
        w = T.CACHE if os.path.exists(T.CACHE) else False
        cls.rep = T.simulate(n=20000, seed=7, window=w)

    def test_every_joint_works_in_nearly_every_build(self):
        bad = {k: (v["tight"], v["loose"]) for k, v in self.rep["fits"].items()
               if v["tight"] > 0.005 or v["loose"] > 0.005}
        self.assertEqual(bad, {})

    def test_the_bearings_reach_the_race_and_clear_the_ring(self):
        b = self.rep["bearings"]
        self.assertLess(b["fail_reach"], 0.001)
        self.assertEqual(b["fail_drop_in"], 0.0)

    def test_the_crank_never_rubs_the_lip_or_the_floor(self):
        h = self.rep["heights"]
        self.assertEqual(h["fail_lip"], 0.0)
        self.assertEqual(h["fail_floor"], 0.0)
        self.assertEqual(h["fail_bottoms"], 0.0)

    def test_the_geneva_runs_as_printed(self):
        if "geneva_jams" not in self.rep:
            self.skipTest("the Geneva's window has not been mapped here")
        self.assertLess(self.rep["geneva_jams"]["as_printed"], 0.001)
        self.assertLess(self.rep["geneva_jams"]["printed_tight"], 0.005)

    def test_a_plain_press_would_have_failed(self):
        """Negative control: the Ø3.1 press the pin had, under the same
        scatter, misses its window in a fifth of builds."""
        rng = np.random.default_rng(3)
        n = 20000
        hole = 3.1 - T.hole_loss(3.1) + rng.normal(0, T.PART_SIGMA, n) \
            + rng.normal(0, T.FEAT_SIGMA, n)
        c = hole - (3.0 + rng.uniform(0.002, 0.008, n))
        self.assertGreater(np.mean((c < -0.15) | (c > 0.0)), 0.10)


if __name__ == "__main__":
    unittest.main()
