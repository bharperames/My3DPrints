"""The orbital scanning jig: what the printed set has to do, measured.

Built once from its defaults; every test reads the same bodies. The gates
here are the generator's own, re-asserted so a change to the generator
that quietly stops measuring something is caught by a test that still
does -- and a few that only a test can afford, like the negative controls
that prove each instrument sees the thing it is meant to see.
"""
import json
import os
import sys
import tempfile
import unittest
import zipfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gen_orbital_jig as J  # noqa: E402


class TestJig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = J.assemble(J.SPECIMEN)
        cls.rep = J.measure(cls.parts, J.SPECIMEN)

    def test_every_gate_passes(self):
        failed = [n for n, ok in J.gates(self.rep) if not ok]
        self.assertEqual(failed, [], json.dumps(self.rep, default=str)[:800])

    def test_ten_bodies_all_watertight(self):
        self.assertEqual(len(self.parts), 10)
        self.assertTrue(all(m.is_watertight for m in self.parts.values()))

    def test_every_body_fits_the_plate_with_the_packers_gap(self):
        flat, _ = J.layout(self.parts)
        for n, m in flat.items():
            e = sorted(m.extents[:2])
            self.assertLessEqual(e[1] + 3.0, 246.0 + 1e-9, n)

    def test_laid_out_bodies_do_not_overlap(self):
        # the packer decides "assembly or separate parts" by overlapping
        # bounds; one overlap and all ten travel as a 800 mm block
        flat, _ = J.layout(self.parts)
        names = list(flat)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                la, ha = flat[a].bounds
                lb, hb = flat[b].bounds
                self.assertFalse((la < hb).all() and (lb < ha).all(),
                                 f"{a} overlaps {b} on the plate")

    def test_plate_pose_round_trips_to_the_assembled_pose(self):
        flat, poses = J.layout(self.parts)
        for n in flat:
            back = flat[n].copy()
            back.apply_transform(poses[n])
            self.assertLess(np.abs(back.vertices - self.parts[n].vertices)
                            .max(), 1e-6, n)

    def test_pupil_sits_on_the_working_sphere_in_the_meridian(self):
        for th in (10.0, 15.0, 35.0, 55.0, 75.0, 80.0):
            p = J.pupil(th)
            self.assertAlmostEqual(float(np.linalg.norm(p)), J.R, places=6)
            self.assertAlmostEqual(float(p[1]), 0.0, places=6)
            self.assertAlmostEqual(float(p[2]), J.R * np.sin(np.radians(th)),
                                   places=6)

    def test_the_protocol_is_the_specs_108_frames(self):
        frames = [int(round(360.0 / p["step"])) for p in J.PROTOCOL]
        self.assertEqual(frames, [36, 30, 24, 18])
        self.assertEqual(sum(frames), 108)
        self.assertEqual([p["elev"] for p in J.PROTOCOL], [15, 35, 55, 75])

    def test_detents_are_seen_and_a_missing_one_would_be(self):
        self.assertEqual(self.rep["detents"], 36)
        # negative control: probe a ring built with one dimple filled in
        r_ = self.parts["rotor"].copy()
        zb = J.levels(J.SPECIMEN)["ring_bot"]
        x, y, _ = J.polar(J.DETENT_R, 0.0)
        plug = J.cone(J.DETENT_MOUTH + 0.6, zb - 0.6, zb + J.DETENT_MOUTH + 0.1,
                      x, y)
        filled = J.union([r_, plug])
        self.assertEqual(J.count_detents(filled, J.SPECIMEN), 35)

    def test_bearings_touch_the_race_and_the_check_can_tell(self):
        for r in self.rep["race"]:
            self.assertLess(abs(r["gap"]), 0.05)
            self.assertTrue(r["pressed_collides"])

    def test_pedestal_hides_under_the_platform_at_75_degrees(self):
        self.assertTrue(self.rep["pedestal_hidden_at_75"])
        # negative control: a straight column would not
        col = J.cyl(J.PLAT_R, -J.SPECIMEN - 30, -J.SPECIMEN)
        ok, worst = J.pedestal_hidden(col, J.SPECIMEN)
        self.assertFalse(ok)
        self.assertGreater(worst, 5.0)

    def test_carriage_clears_everything_through_its_range(self):
        self.assertEqual(self.rep["elevation_fouls"], [])

    def test_rotor_side_clears_the_base_through_a_full_turn(self):
        self.assertEqual(self.rep["azimuth_fouls"], [])

    def test_sweep_sees_a_collision_when_there_is_one(self):
        # negative control: a carriage swung past the arc's foot
        parts = dict(self.parts)
        low = J.elevation_sweep(parts, step=90.0)     # 10 and 80 only
        self.assertEqual(low, [])
        parts["arc"] = self.parts["arc"].copy()
        parts["arc"].apply_translation([0, 12.0, 0])   # into the saddle
        self.assertTrue(J.elevation_sweep(parts, step=90.0))

    def test_arc_is_concentric_and_slotted(self):
        lo, hi = self.rep["arc_radii"]
        self.assertGreaterEqual(lo, J.ARC_RI - 0.05)
        self.assertLessEqual(hi, J.ARC_RO + 0.05)
        self.assertAlmostEqual(self.rep["slot_mm"], J.SLOT_W, delta=0.15)

    def test_the_dial_moves_the_pad_and_not_the_arc(self):
        a12 = self.parts["arc"]
        a20 = J.arc()
        self.assertLess(np.abs(a12.vertices - a20.vertices).max(), 1e-9)
        self.assertAlmostEqual(J.levels(20.0)["pad_t"], 20.0)
        self.assertAlmostEqual(J.levels(20.0)["pad_top"] - J.PAD_SLOT_D,
                               J.LEG_BOTTOM)

    def test_export_carries_the_assembly_inside_the_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "jig.3mf")
            bad, meta = J.export(self.parts, J.SPECIMEN, out)
            self.assertEqual(bad, {})
            with zipfile.ZipFile(out) as z:
                names = z.namelist()
                self.assertIn("Metadata/orbital_jig.json", names)
                self.assertIn("Metadata/project_settings.config", names)
                d = json.loads(z.read("Metadata/orbital_jig.json"))
            self.assertEqual(set(d["to_world"]), set(self.parts))
            self.assertEqual(d["frames"], 108)
            self.assertEqual(d["R"], J.R)
            import trimesh
            sc = trimesh.load(out, force="scene")
            self.assertEqual(set(sc.geometry), set(self.parts))
            # the geometry in the file, taken back through to_world, is
            # the assembled body: what the page renders is what prints
            for n, g in sc.geometry.items():
                M = np.array(d["to_world"][n]).reshape(4, 4)
                back = g.copy()
                back.apply_transform(M)
                self.assertLess(np.abs(back.bounds - self.parts[n].bounds)
                                .max(), 0.01, n)


if __name__ == "__main__":
    unittest.main()
