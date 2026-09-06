"""The depth search, on shapes small enough to reason about by hand.

The seed cube is the real calibration and it costs half a minute a run, so
it lives in `gen_puzzle.py`'s gates. What is held down here is the part that
would fail silently: the generalisation of the sweep off the z axis, and the
direction the coarse search is allowed to be wrong in.
"""
import os
import sys
import unittest

import numpy as np
import trimesh

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))
from assembly import extent_along, helix, screw_path            # noqa: E402
from mobility import Mobility                                   # noqa: E402


def box(sx, sy, sz, at=(0, 0, 0)):
    m = trimesh.creation.box((sx, sy, sz))
    m.apply_translation(at)
    return m


class TestHelix(unittest.TestCase):
    def test_z_case_is_unchanged(self):
        """The general helix has to reproduce the seed cube's z-axis path.

        `screw_path` is now a wrapper, so if these ever differ every gate in
        gen_puzzle.py is measuring something other than what it measured
        when the part was printed and found to work.
        """
        a = screw_path(0.0, 12.0, 5.33, 0.4, max_r=9.0)
        b = helix(0.0, 12.0, (0, 0, 1), (0, 0, 0), 5.33, 0.4, max_r=9.0)
        self.assertEqual(len(a), len(b))
        for u, v in zip(a, b):
            np.testing.assert_allclose(u, v, atol=1e-12)

    def test_travels_and_turns_about_the_same_line(self):
        """Off z, a screw must still advance along the line it turns about."""
        d, o = np.array([1.0, 0, 0]), np.array([0.0, 7.0, 0.0])
        p = helix(0.0, 6.0, d, o, 6.0, 0.0, max_r=5.0)
        start, end = p[0], p[-1]
        self.assertAlmostEqual(float((end[:3, 3] - start[:3, 3]) @ d), 6.0, 3)
        # one lead is one full turn, so the frame comes back to itself
        np.testing.assert_allclose(end[:3, :3], np.eye(3), atol=1e-9)
        # and the line it turns about is fixed: a point on it does not move
        pt = np.append(o + 3.0 * d, 1.0)
        np.testing.assert_allclose((end @ pt)[:3], o + 9.0 * d, atol=1e-9)

    def test_extent_uses_vertices_not_the_bounding_box(self):
        """A box's AABB overstates its reach along any diagonal."""
        m = box(10, 10, 10)
        d = np.array([1.0, 1.0, 0.0]) / np.sqrt(2)
        lo, hi = extent_along(m, d)
        self.assertAlmostEqual(hi, 5.0 * np.sqrt(2), 6)
        aabb = (m.bounds @ (d / np.linalg.norm(d)))
        self.assertLess(hi, max(aabb) + 1e-9)


class TestMobility(unittest.TestCase):
    LINES = [((1, 0, 0), (0, 0, 0)), ((0, 1, 0), (0, 0, 0)),
             ((0, 0, 1), (0, 0, 0))]

    def test_a_loose_pair_comes_apart(self):
        m = Mobility({"a": box(10, 10, 10, (0, 0, 0)),
                      "b": box(10, 10, 10, (0, 0, 10.4))},
                     self.LINES, 6.0, quantum=6.0)
        r = m.solve()
        self.assertTrue(r["comes_apart"])
        self.assertEqual(r["solve_length"], 1)

    def test_a_captured_body_does_not(self):
        """A cube inside a closed shell has no motion, so nothing to sample.

        This is the failure the whole search exists for: it is the ABSENCE
        of a path, which no gate that checks a motion someone thought of can
        ever find.
        """
        shell = box(40, 40, 40).difference(box(20, 20, 20), engine="manifold")
        m = Mobility({"shell": shell, "pea": box(19, 19, 19)},
                     self.LINES, 6.0, quantum=6.0)
        r = m.solve()
        self.assertFalse(r["comes_apart"])
        self.assertEqual(r["legal_first_moves"], 0)

    def test_an_axis_off_z_is_actually_searched(self):
        """A rod in a tube along x comes out along x and nowhere else.

        Before the sweep was generalised every body reported welded on any
        axis but z, which is the quiet failure: it under-reports mobility,
        so a working design and a welded one read the same. The negative
        half matters as much — given only the z line the rod is trapped, and
        a search that says otherwise is finding motions that do not exist.
        """
        tube = box(30, 20, 20).difference(box(31, 10, 10), engine="manifold")
        parts = {"tube": tube, "rod": box(28, 9.6, 9.6)}
        self.assertTrue(Mobility(parts, [self.LINES[0]], 6.0, quantum=6.0)
                        .solve()["comes_apart"])
        self.assertFalse(Mobility(parts, [self.LINES[2]], 6.0, quantum=6.0)
                         .solve()["comes_apart"])

    def test_a_part_already_clear_still_counts_as_free(self):
        """A lid resting on a box goes clear on the first sample.

        It is the loosest joint an assembly can have, and a search that
        insists a move travel further than its own standoff to count
        discards it and reports the whole thing stuck.
        """
        m = Mobility({"box": box(20, 20, 10), "lid": box(20, 20, 2,
                                                         (0, 0, 6.1))},
                     self.LINES, 6.0, quantum=6.0)
        self.assertTrue(m.solve()["comes_apart"])

    def test_coarse_search_only_ever_over_reports(self):
        """The coarse pass may skip a collision; it may not invent one.

        That is what makes 'search coarse, confirm fine' safe: everything it
        gets wrong is caught by the confirm pass, and nothing it gets wrong
        is a working motion declared impossible.
        """
        parts = {"a": box(10, 10, 10), "b": box(10, 10, 10, (0, 0, 10.4))}
        fine = Mobility(parts, self.LINES, 6.0, quantum=6.0, coarse=1.0)
        crude = Mobility(parts, self.LINES, 6.0, quantum=6.0, coarse=40.0)
        self.assertGreaterEqual(len(crude.moves(crude.home())),
                                len(fine.moves(fine.home())))

    def test_retrograde_is_a_move_against_the_way_out(self):
        seq = [{"parts": ["bolt"], "line": 0, "direction": -1,
                "coupling": 1, "distance": -5.0, "frees": False},
               {"parts": ["block"], "line": 1, "direction": 1,
                "coupling": None, "distance": 6.0, "frees": True},
               {"parts": ["bolt"], "line": 0, "direction": 1,
                "coupling": 1, "distance": 40.0, "frees": True}]
        r = Mobility.retrograde(seq)
        self.assertEqual([x["part"] for x in r], ["bolt"])
        self.assertEqual(r[0]["move"], 0)


if __name__ == "__main__":
    unittest.main()
