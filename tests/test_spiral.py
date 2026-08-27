"""Unit tests for the parametric spiral-tower generator."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from gen_spiral import (DEFAULTS, audit, build, env_factory,  # noqa: E402
                        sector_pts, sq_profile, star_pts)

FAST = dict(DEFAULTS, base_r=18.0, cell_h=40.0)


class TestEnvelope(unittest.TestCase):
    def test_hourglass_shape(self):
        env = env_factory(20.0, 10.0, 90.0, 1)
        self.assertAlmostEqual(env(0.0), 20.0)
        self.assertAlmostEqual(env(45.0), 10.0)
        self.assertAlmostEqual(env(90.0), 20.0)

    def test_cells_repeat(self):
        env = env_factory(20.0, 10.0, 90.0, 2)
        self.assertAlmostEqual(env(45.0), env(135.0))
        self.assertAlmostEqual(env(90.0), 20.0)

    def test_square_profile_bounds(self):
        th = np.linspace(0, 2 * np.pi, 361)
        s = sq_profile(th)
        self.assertAlmostEqual(s.min(), 1.0, places=6)
        self.assertAlmostEqual(s.max(), np.sqrt(2), places=3)


class TestSections(unittest.TestCase):
    def test_sector_flanks_are_radial(self):
        pts = sector_pts(5.0, 20.0, -0.2, 0.2)
        angles = [th for (_, th, _) in pts]
        self.assertAlmostEqual(max(angles), 0.2)
        self.assertAlmostEqual(min(angles), -0.2)

    def test_star_lobes_offset_into_slots(self):
        pts = star_pts(4.6, 20.0, 7, np.radians(20))
        period = 2 * np.pi / 7
        tips = [th for (r, th, sc) in pts if sc]
        # lobe tips cluster around half-period centers, not blade centers
        nearest = min(abs(np.angle(np.exp(1j * (t - 0.5 * period))))
                      for t in tips)
        self.assertLess(nearest, np.radians(11))

    def test_star_flanks_are_radial(self):
        pts = star_pts(4.6, 20.0, 7, np.radians(20))
        for i in range(len(pts)):
            r0, t0, _ = pts[i]
            r1, t1, _ = pts[(i + 1) % len(pts)]
            if abs(r0 - r1) > 1e-9:            # radial edge
                self.assertLess(abs(np.angle(np.exp(1j * (t1 - t0)))), 1e-9)


class TestGates(unittest.TestCase):
    def test_high_twist_rejected(self):
        with self.assertRaisesRegex(ValueError, "overhang"):
            build(dict(DEFAULTS, twist=5.0))

    def test_thin_rim_rejected(self):
        with self.assertRaisesRegex(ValueError, "rim"):
            build(dict(DEFAULTS, rim_t=1.0))

    def test_thin_blades_rejected(self):
        with self.assertRaisesRegex(ValueError, "waist"):
            build(dict(DEFAULTS, base_r=14.0, waist_frac=0.4))

    def test_square_corner_overhang_stricter(self):
        build(dict(DEFAULTS, twist=2.5))       # circle passes
        with self.assertRaisesRegex(ValueError, "overhang"):
            build(dict(DEFAULTS, twist=2.5, profile="square"))


class TestBuildAndThread(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.solid, cls.spiral, cls.rep = build(dict(FAST))
        cls.rep = audit(cls.solid, cls.spiral, dict(FAST), cls.rep,
                        thread_steps=8.0)

    def test_watertight(self):
        self.assertTrue(self.rep["solid_watertight"])
        self.assertTrue(self.rep["spiral_watertight"])

    def test_threads_with_clearance(self):
        self.assertTrue(self.rep["threads"])
        self.assertGreater(self.rep["thread_min_gap"], 0.2)

    def test_single_island_bed_contact(self):
        self.assertEqual(self.rep["solid_bed_islands"], 1)
        self.assertEqual(self.rep["spiral_bed_islands"], 1)
        self.assertGreater(self.rep["solid_bed_mm2"], 200)

    def test_wobble_low(self):
        self.assertLess(self.rep["solid_wobble"], 2.0)
        self.assertLess(self.rep["spiral_wobble"], 2.0)

    def test_solid_height_and_diameter(self):
        h = self.solid.bounds[1][2] - self.solid.bounds[0][2]
        self.assertAlmostEqual(h, FAST["cell_h"], delta=0.01)


if __name__ == "__main__":
    unittest.main()
