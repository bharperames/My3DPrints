"""The specimen head system: the screw-on alternative, measured.

This family is a study rather than a product, so what the tests hold down
is the comparison it exists to make -- which heads keep clear of the
plane the specimen rests on and which do not -- rather than fit and
clearance it will never be printed to.
"""
import json
import os
import sys
import tempfile
import unittest
import zipfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gen_specimen_heads as H  # noqa: E402


class TestHeads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = H.build("all")
        cls.rep = H.measure(cls.parts)

    def test_every_gate_passes(self):
        failed = [n for n, ok in H.gates(self.rep) if not ok]
        self.assertEqual(failed, [], json.dumps(self.rep, default=str)[:900])

    def test_four_heads_all_watertight(self):
        self.assertEqual(len(self.parts), 4)
        self.assertEqual(set(self.parts), set(H.HEADS))
        self.assertTrue(all(m.is_watertight for m in self.parts.values()))

    def test_every_head_fits_the_plate(self):
        flat, _ = H.layout(self.parts)
        for n, m in flat.items():
            e = sorted(m.extents[:2])
            self.assertLessEqual(e[1] + 3.0, 246.0 + 1e-9, n)

    def test_laid_out_heads_do_not_overlap(self):
        flat, _ = H.layout(self.parts)
        names = list(flat)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                la, ha = flat[a].bounds
                lb, hb = flat[b].bounds
                self.assertFalse((la < hb).all() and (lb < ha).all(),
                                 f"{a} overlaps {b}")

    # --- the comparison this family exists to make ---------------------
    def test_the_contact_mounts_keep_clear_of_the_specimen(self):
        for n in H.STAY_BELOW:
            self.assertLessEqual(self.rep["rise_above_contact_mm"][n], 0.01,
                                 f"{n} must not rise above its contact plane")

    def test_the_other_two_rise_and_that_is_the_trade(self):
        rise = self.rep["rise_above_contact_mm"]
        # the cup swallows the crown; the chuck's jaws stand beside a slab
        self.assertGreater(rise["tip_cone"], 20.0)
        self.assertGreater(rise["flat_chuck"], 10.0)

    def test_the_cup_swallows_the_depth_the_plan_asked_for(self):
        self.assertAlmostEqual(
            self.rep["rise_above_contact_mm"]["tip_cone"], H.TC_DEEP, delta=0.5)

    def test_the_chuck_really_opens_sixty(self):
        m = self.parts["flat_chuck"]
        t = H.FC_BASE[2]
        # slice through the jaws and read the gap between them
        sec = m.section(plane_origin=[0, 0, t + H.FC_JAW[2] / 2.0],
                        plane_normal=[0, 0, 1])
        self.assertIsNotNone(sec)
        p, _ = sec.to_planar()
        xs = sorted(poly.centroid.x for poly in p.polygons_full)
        inner = [poly for poly in p.polygons_full
                 if abs(poly.centroid.x) > H.FC_OPEN / 2.0 - 1.0]
        self.assertEqual(len(inner), 2, "two jaws")
        faces = sorted(min(abs(v) for v in
                           np.array(poly.bounds).reshape(2, 2)[:, 0])
                       for poly in inner)
        self.assertAlmostEqual(faces[0] + faces[1], H.FC_OPEN, delta=0.5)

    def test_every_head_carries_the_quarter_twenty_dock(self):
        for n, m in self.parts.items():
            # a bore of that radius must pass right through the base
            sec = m.section(plane_origin=[0, 0, 1.0],
                            plane_normal=[0, 0, 1])
            self.assertIsNotNone(sec, n)
            p, _ = sec.to_planar()
            holes = [len(poly.interiors) for poly in p.polygons_full]
            self.assertGreaterEqual(max(holes), 1, f"{n} has no dock bore")

    def test_bought_parts_are_proxies_not_printed(self):
        px = H.proxies()
        self.assertEqual(set(px), {"pin_0", "pin_1", "pin_2", "foam_liner"})
        for n, m in px.items():
            self.assertTrue(m.is_watertight, n)
            self.assertNotIn(n, self.parts, "a proxy must not be printed")

    def test_the_cone_stands_make_neither_trade(self):
        """The point of the comparison, asserted across both files."""
        import gen_tooth_stand as T
        stands = T.build("all")
        for n, m in stands.items():
            spec = T.BY_ID[n.split("_")[1]]
            self.assertLessEqual(float(m.bounds[1][2]) - T.contact_z(spec),
                                 1e-6, n)

    def test_export_carries_the_heads_inside_the_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "heads.3mf")
            bad, meta = H.export(self.parts, out)
            self.assertEqual(bad, {})
            with zipfile.ZipFile(out) as z:
                self.assertIn("Metadata/specimen_heads.json", z.namelist())
                d = json.loads(z.read("Metadata/specimen_heads.json"))
            self.assertEqual(set(d["to_world"]), set(self.parts))
            self.assertEqual(set(d["contact_z"]), set(self.parts))
            import trimesh
            sc = trimesh.load(out, force="scene")
            self.assertEqual(set(sc.geometry), set(self.parts))
            for n, g in sc.geometry.items():
                M = np.array(d["to_world"][n]).reshape(4, 4)
                back = g.copy()
                back.apply_transform(M)
                self.assertLess(np.abs(back.bounds - self.parts[n].bounds)
                                .max(), 0.01, n)


if __name__ == "__main__":
    unittest.main()
