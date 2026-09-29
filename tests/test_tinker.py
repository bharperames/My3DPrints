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


class TestWrench(unittest.TestCase):
    """Fit is measured against the set's own nut, in both ends, with the
    Montessori wrench's own band: loose enough to go on, tight enough not
    to round the corners it turns."""

    def test_both_ends_fit_the_nut(self):
        import gen_wrench as W
        m = G.wrench()
        self.assertTrue(m.is_watertight)
        self.assertEqual(len(m.split(only_watertight=False)), 1)
        nut = G.nut()
        nut.apply_translation([0, 0, -nut.bounds[0][2]])
        _, _, geo = W.build(G.HEX_AF, G.WRENCH_THICK, **G.WRENCH)
        for at in ((0.0, 0.0), tuple(geo["seat"])):
            fit = W.fit_test(m, nut, at, G.WRENCH_THICK, nut_mid=G.U / 2)
            self.assertIsNotNone(fit, f"the nut does not go in at {at}")
            self.assertTrue(W.FIT_MIN <= fit[0] <= W.FIT_MAX, fit[0])

    def test_it_is_thinner_than_the_heads_flat_band(self):
        self.assertLess(G.WRENCH_THICK, G.U - 2 * G.HEAD_CHAM)


class TestNoSmallParts(unittest.TestCase):
    """16 CFR 1501: a part that fits wholly in a 31.7 mm cylinder is a
    small part. Conservatively, a piece passes only if no view of it -- its
    shadow along any direction -- fits a 31.7 mm circle. Views are sampled,
    which can only miss the narrowest one, so the bar carries a millimeter
    of margin on top."""

    MARGIN = 1.0

    @staticmethod
    def narrowest_view(mesh, n=3000):
        import shapely
        from shapely.geometry import MultiPoint
        i = np.arange(n) + 0.5
        ph, th = np.arccos(1 - 2 * i / n), np.pi * (1 + 5 ** 0.5) * i
        dirs = np.column_stack([np.cos(th) * np.sin(ph),
                                np.sin(th) * np.sin(ph), np.cos(ph)])
        dirs = np.vstack([dirs[dirs[:, 2] >= 0], np.eye(3)])
        v = mesh.convex_hull.vertices
        best = np.inf
        for d in dirs:
            a = np.cross(d, [1, 0, 0] if abs(d[0]) < .9 else [0, 1, 0])
            a /= np.linalg.norm(a)
            b = np.cross(d, a)
            pts = MultiPoint(np.column_stack([v @ a, v @ b]))
            best = min(best, 2 * shapely.minimum_bounding_radius(pts))
        return best

    def test_the_instrument_catches_a_small_part(self):
        # the set as first drawn, at half this size, was all small parts
        nut = G.nut()
        nut.apply_scale(0.5)
        self.assertLess(self.narrowest_view(nut), G.SMALL_PART_D)

    def test_no_piece_fits_the_cylinder(self):
        for name, _, fn, _, _ in G.SET:
            with self.subTest(name):
                self.assertGreater(self.narrowest_view(fn()),
                                   G.SMALL_PART_D + self.MARGIN)


class TestDoubleBolt(unittest.TestCase):
    def test_nothing_on_it_is_a_flat_ceiling(self):
        m = G.double_bolt()
        c, nz = m.triangles_center, m.face_normals[:, 2]
        self.assertLess(m.area_faces[(nz < -0.94) & (c[:, 2] > 0.5)].sum(),
                        0.5)


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

    @staticmethod
    def written_outlines(plates):
        """Each body's outline from above, on the plate the shop writes:
        the packer's own shapes are what is under test, so they cannot be
        the ruler."""
        import plateshop
        import shapely
        import trimesh
        from trimesh.path.polygons import projected
        out = tempfile.mktemp(suffix=".3mf")
        try:
            plateshop.write_plate(plates[0], out, brim=False)
            sc = trimesh.load(out, force="scene")
            polys = {}
            for node in sc.graph.nodes_geometry:
                tf, gk = sc.graph[node]
                g = sc.geometry[gk].copy()
                g.apply_transform(tf)
                p = projected(g, normal=[0, 0, 1])
                polys[gk] = shapely.unary_union(
                    [shapely.Polygon(q.exterior)
                     for q in getattr(p, "geoms", [p])])
        finally:
            if os.path.exists(out):
                os.remove(out)
        return polys

    def test_a_brimmed_piece_keeps_its_brim_clear_of_neighbors(self):
        import plateshop
        few = {k: 0 for k in catalog.defaults(self.card())}
        few.update(double=1, nut=6, b1=2)
        items, _ = plateshop.order_items(
            [dict(part="tinker_set", params=few, qty=1)])
        plates, _ = plateshop.pack(items)
        polys = self.written_outlines(plates)
        brim = float(plateshop.PIECE_BRIM["brim_width"])
        db = [k for k in polys if "double_bolt" in k]
        self.assertEqual(len(db), 1)
        for k, p in polys.items():
            if k != db[0]:
                self.assertGreaterEqual(p.distance(polys[db[0]]), brim, k)

    def test_the_plate_brett_arranged_in_studio_packs_onto_one_bed(self):
        """Bambu Studio fit these 22 on one plate by nesting outlines
        (2026-09-29). The shop's bounding-box packer could not."""
        import plateshop
        brett = {k: 0 for k in catalog.defaults(self.card())}
        brett.update(p1x4=2, p1x2=2, bracket=2, b1=1, b2=6, b3=1, b4=1,
                     coupler=1, wing=1, nut=5)
        items, _ = plateshop.order_items(
            [dict(part="tinker_set", params=brett, qty=1)])
        plates, over = plateshop.pack(items)
        self.assertEqual((len(plates), over), (1, []))
        polys = self.written_outlines(plates)
        ks = list(polys)
        closest = min(polys[a].distance(polys[b])
                      for i, a in enumerate(ks) for b in ks[i + 1:])
        self.assertGreaterEqual(closest, plateshop.GAP - 1e-6)

    def test_the_default_set_is_one_plate(self):
        import plateshop
        items, _ = plateshop.order_items(
            [dict(part="tinker_set", params=None, qty=1)])
        plates, over = plateshop.pack(items)
        self.assertEqual((len(plates), over), (1, []))

    def card(self):
        return catalog.find("tinker_set")


if __name__ == "__main__":
    unittest.main()
