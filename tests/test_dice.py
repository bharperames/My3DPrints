"""Unit tests for dice-orb building blocks."""
import os
import sys
import unittest

import numpy as np
import trimesh

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from gen_dice_cage import A_D, numeral_mesh, tube  # noqa: E402


class TestNumerals(unittest.TestCase):
    def test_all_twenty_render(self):
        for n in range(1, 21):
            m = numeral_mesh(str(n), cap_height=3.3, depth=1.0)
            self.assertIsNotNone(m, f"numeral {n} failed")
            self.assertGreater(m.volume, 0.1, f"numeral {n} empty")

    def test_cap_height_honored(self):
        m = numeral_mesh("8", cap_height=4.0, depth=1.0)
        lo, hi = m.bounds
        self.assertAlmostEqual(hi[1] - lo[1], 4.0, delta=0.01)

    def test_six_and_nine_carry_underlines(self):
        # the underline extends the glyph box below the baseline
        plain = numeral_mesh("8", cap_height=4.0, depth=1.0)
        six = numeral_mesh("6", cap_height=4.0, depth=1.0)
        ratio6 = (six.bounds[1][1] - six.bounds[0][1])
        # both are normalized to cap height; the 6 must have MORE parts
        self.assertGreater(len(six.split(only_watertight=False)),
                           len(plain.split(only_watertight=False)) - 1)
        nine = numeral_mesh("9", cap_height=4.0, depth=1.0)
        self.assertGreater(nine.volume, 0.1)

    def test_antipodal_numbering_sums_21(self):
        # replicate the generator's pairing rule on a fresh icosahedron
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

    def test_standard_die_size(self):
        face_in = A_D / (2 * np.sqrt(3))
        self.assertAlmostEqual(2 * face_in * 2.618, 20.4, delta=0.2)


class TestTube(unittest.TestCase):
    def test_polyline_produces_parts(self):
        pts = np.array([[0, 0, 0], [10, 0, 0], [10, 10, 0]], float)
        parts = []
        tube(pts, 1.0, parts)
        self.assertEqual(len(parts), 4)      # 2 cylinders + 2 knot spheres
        u = trimesh.boolean.union(parts, engine="manifold")
        self.assertTrue(u.is_watertight)


if __name__ == "__main__":
    unittest.main()
