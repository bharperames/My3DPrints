"""The Tinker Set: its card, its nuts, and how the shop handles its pieces.

The card's dials and the generator's piece list are two copies of one
contract -- keys, defaults and brims -- and these tests are what diff them.
"""
import os
import re
import sys
import tempfile
import unittest
import zipfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import catalog  # noqa: E402
import gen_tinker as G  # noqa: E402


class TestCardMatchesGenerator(unittest.TestCase):
    def setUp(self):
        self.card = catalog.find("tinker_set")

    def test_every_piece_has_a_dial_with_its_default(self):
        dials = {d["key"]: d["val"] for d in self.card["params"]}
        gen = {key: count for _, key, _, count, _ in G.SET}
        self.assertEqual(dials, gen)

    def test_the_brimmed_pieces_are_the_generators(self):
        gen = sorted(name for name, _, _, _, brim in G.SET if brim)
        self.assertEqual(sorted(self.card["brim_bodies"]), gen)

    def test_every_count_can_go_to_zero(self):
        self.assertTrue(all(d["min"] == 0 for d in self.card["params"]))


class TestNutMouth(unittest.TestCase):
    """The strands across a nut's opening came from a flat ceiling where
    the bed-side chamfer stopped. A true cone leaves none."""

    def test_no_flat_ceiling_in_any_threaded_bore(self):
        for name, part in (("nut", G.nut()), ("coupler", G.coupler()),
                           ("wing", G.wing_nut())):
            c = part.triangles_center
            r = np.hypot(c[:, 0], c[:, 1])
            nz = part.face_normals[:, 2]
            ceiling = part.area_faces[(r < 7.5) & (nz < -0.94)].sum()
            self.assertLess(ceiling, 0.5, name)

    def test_the_bolt_still_screws_in_at_the_lead(self):
        from gen_montessori import screw_test
        lead, _ = screw_test(G.nut(), G.T.shank_only(G.bolt(1)),
                             [1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertAlmostEqual(lead, G.T.lead, places=2)


class TestShopArrangesTheSet(unittest.TestCase):
    def test_pieces_are_split_and_only_double_bolts_are_brimmed(self):
        import plateshop
        few = {k: 0 for k in catalog.defaults(self.card())}
        few.update(b2=2, nut=2, double=1)
        items, rep = plateshop.order_items(
            [dict(part="tinker_set", params=few, qty=1)])
        self.assertEqual(rep["tinker_set"]["pieces"], 5)
        plates, over = plateshop.pack(items)
        self.assertEqual((len(plates), over), (1, []))
        out = tempfile.mktemp(suffix=".3mf")
        try:
            plateshop.write_plate(plates[0], out, brim=False)
            cfg = zipfile.ZipFile(out).read(
                "Metadata/model_settings.config").decode()
        finally:
            if os.path.exists(out):
                os.remove(out)
        brimmed = [n for n, body in re.findall(
            r'<metadata key="name" value="([^"]+)"/>(.*?)</object>', cfg, re.S)
            if "brim_type" in body]
        self.assertEqual(len(brimmed), 1)
        self.assertIn("double_bolt", brimmed[0])

    def card(self):
        return catalog.find("tinker_set")


if __name__ == "__main__":
    unittest.main()
