"""Unit tests for the print-time mechanics audit."""
import os
import sys
import unittest

import trimesh

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from mech_audit import PLA_G_PER_MM3, wobble_index  # noqa: E402


class TestWobbleIndex(unittest.TestCase):
    def test_uniform_cylinder_matches_analytic(self):
        # index at z = rho * (H - z); worst near the bottom sample
        H = 50.0
        cyl = trimesh.creation.cylinder(radius=8.0, height=H, sections=48)
        cyl.apply_translation([0, 0, H / 2])
        w, wz = wobble_index(cyl, step=2.0)
        expect = PLA_G_PER_MM3 * (H - 2.0)
        self.assertAlmostEqual(w, expect, delta=expect * 0.25)
        self.assertLess(wz, 6.0)

    def test_top_heavy_ball_on_neck_scores_high(self):
        ball = trimesh.creation.icosphere(subdivisions=3, radius=10.0)
        ball.apply_translation([0, 0, 20 + 10])
        neck = trimesh.creation.cylinder(radius=1.5, height=22, sections=24)
        neck.apply_translation([0, 0, 11])
        m = trimesh.boolean.union([ball, neck], engine="manifold")
        w_heavy, _ = wobble_index(m, step=2.0)
        self.assertGreater(w_heavy, 0.4)
        # and it must dwarf the uniform-cylinder baseline
        cyl = trimesh.creation.cylinder(radius=10.0, height=40, sections=48)
        cyl.apply_translation([0, 0, 20])
        w_cyl, _ = wobble_index(cyl, step=2.0)
        self.assertGreater(w_heavy, 5 * w_cyl)


if __name__ == "__main__":
    unittest.main()
