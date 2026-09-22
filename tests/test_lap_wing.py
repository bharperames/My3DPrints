"""The lap X-wing: what the plier joint has to do, measured.

This design exists to answer one question the scissor X-wing answered
with a flip and four loose parts: how do two arms cross while both carry
their own cones. Every claim it makes -- nothing overhangs, nothing is
loose, the four tips are coplanar, the seat carries the upper frame --
is checked here off the built bodies, with a control for each check that
could otherwise pass on an empty measurement.
"""
import json
import os
import sys
import tempfile
import unittest
import zipfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gen_lap_wing as W  # noqa: E402
import gen_tooth_stand as T  # noqa: E402


class TestLapWing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = W.build("all")
        cls.rep = W.measure(cls.parts)

    def test_every_gate_passes(self):
        failed = [n for n, ok in W.gates(self.rep) if not ok]
        self.assertEqual(failed, [], json.dumps(self.rep, default=str)[:900])

    def test_three_bodies_per_wing_and_nothing_loose(self):
        # the point of the joint: two frames and a pin, with the cones
        # part of the frames. The scissor X-wing needs eight bodies for
        # the same four cups -- four of them loose posts on loose dowels
        self.assertEqual(len(self.parts), 3 * len(W.LAPWINGS))
        self.assertTrue(all(m.is_watertight for m in self.parts.values()))
        for n in self.parts:
            self.assertTrue(n.endswith(("_lower", "_upper", "_pin")), n)

    def test_the_four_cups_are_coplanar(self):
        for k, dz in self.rep["coplanar_mm"].items():
            self.assertIsNotNone(dz, k)
            self.assertLess(dz, 0.05, k)

    def test_the_coplanarity_probe_can_see_a_short_cone(self):
        # the control. The upper frame's cones are shortened by exactly
        # one frame thickness, so a probe that cannot see a wrong
        # shortening is not checking anything
        spec = W.BY_ID["lp_l"]
        parts = dict(W.lapwing(spec))
        up = parts["lapwing_l_upper"]
        x, y = W.tips(spec)[2]
        sunk = T.cyl(6.0, W.dish_z(spec) - 1.5, W.contact_z(spec) + 5.0,
                     x, y, sections=32)
        parts["lapwing_l_upper"] = T.cut(up, [sunk])
        dz, _ = W.tips_coplanar(spec, parts)
        self.assertIsNotNone(dz)
        self.assertGreater(dz, 1.0, "a 1.5 mm short cone must be seen")

    def test_nothing_rises_above_the_contact_plane(self):
        for k, v in self.rep["above_contact_mm"].items():
            self.assertLessEqual(v, 1e-6, f"{k} pokes {v:+.3f} mm above")

    def test_the_stand_occludes_nothing(self):
        for k, o in self.rep["occlusion"].items():
            self.assertLess(o["overall"], 1.0, k)

    # --- the claim that this design is about --------------------------
    def test_every_body_prints_as_it_is_used(self):
        # no body has a downward face off the plate: no bridge, no
        # support, and no part that has to be flipped to print
        for n, v in self.rep["print"].items():
            self.assertLessEqual(v["off_plate_mm2"], 1.0, n)
        for n, a in self.rep["plate_mm2"].items():
            self.assertGreater(a, 20.0, n)

    def test_the_overhang_probe_sees_one_that_is_there(self):
        # the control: the scissor X-wing's upper arm, printed the way
        # this design prints everything -- cones up -- is exactly the
        # part that cannot be, and the probe must say so
        spec = T.XW_BY_ID["xw_l"]
        _, upper = T.xw_arms(spec)
        v = W.print_overhang(upper)
        self.assertGreater(v["off_plate_mm2"], 100.0,
                           "the probe cannot see a pocket roof")

    def test_the_frames_are_the_same_thickness_and_stack(self):
        for x in W.LAPWINGS:
            k = x["id"][3:]
            lo = self.parts[f"lapwing_{k}_lower"]
            up = self.parts[f"lapwing_{k}_upper"]
            self.assertAlmostEqual(float(lo.bounds[0][2]), 0.0, places=6)
            # the upper frame's underside sits ON the lower frame's top:
            # face to face, no clearance to take up, which is why the
            # cups are coplanar by construction
            self.assertAlmostEqual(float(up.bounds[0][2]), W.ARM_T, places=6)
            self.assertAlmostEqual(W.cone_h(x, False),
                                   W.cone_h(x, True) - W.ARM_T, places=6)

    def test_the_seat_carries_the_upper_frame_at_every_setting(self):
        # the seat is the whole mechanism: the upper frame's two cones
        # are cantilevered on it. It must stay a full annulus through the
        # travel, not just at the pose the parts were built in
        for x in W.LAPWINGS:
            r, bore = W.disc_r(x), W.HOLE_RUN_R
            annulus = np.pi * (r ** 2 - bore ** 2)
            o = self.rep["opening"][x["id"]]
            for beta in (o["beta"][0], x["alpha"], o["beta"][1]):
                parts = W.lapwing(x, beta)
                b = W.bearing(x, parts)
                self.assertGreater(b["area_mm2"], annulus * 0.95,
                                   f"{x['id']} at beta {beta}")

    def test_it_opens_over_a_useful_range(self):
        for k, o in self.rep["opening"].items():
            self.assertIsNotNone(o, k)
            spec = W.BY_ID[k]
            self.assertLessEqual(o["beta"][0], spec["alpha"], k)
            self.assertGreaterEqual(o["beta"][1], spec["alpha"], k)
            self.assertGreaterEqual(o["beta"][1] - o["beta"][0], 20.0, k)
            # and the spans it reaches bracket the teeth it is for
            self.assertLess(o["fore"][0], 15.0, k)
            self.assertGreater(o["fore"][1], spec["cross"], k)

    def test_the_sweep_probe_can_see_a_blocked_joint(self):
        # the control: a post planted between the frames must close the
        # range down, or the range above is measuring nothing
        spec = W.BY_ID["lp_l"]
        parts = dict(W.lapwing(spec))
        blocked = T.union([parts["lapwing_l_lower"],
                           T.cyl(4.0, W.ARM_T, W.ARM_T + 4.0,
                                 x=18.0, y=18.0, sections=32)])
        parts["lapwing_l_lower"] = blocked
        o = W.opening(spec, parts)
        full = self.rep["opening"]["lp_l"]
        self.assertTrue(o is None or
                        (o["beta"][1] - o["beta"][0])
                        < (full["beta"][1] - full["beta"][0]))

    def test_the_pin_presses_into_one_frame_and_turns_in_the_other(self):
        # a pin that is a press in both locks the joint solid: that
        # happened once on the scissor X-wing and is the reason this is
        # checked rather than read off the constants
        for x in W.LAPWINGS:
            k = x["id"][3:]
            pin = self.parts[f"lapwing_{k}_pin"]
            lo = self.parts[f"lapwing_{k}_lower"]
            up = self.parts[f"lapwing_{k}_upper"]
            d_pin = T._shaft_d(pin, W.ARM_T / 2.0)
            d_press = T._bore_d(lo, W.ARM_T / 2.0)
            d_run = T._bore_d(up, W.ARM_T * 1.5)
            self.assertGreater(d_run, d_press, x["id"])
            self.assertLessEqual(d_press - d_pin, 0.16, x["id"])
            self.assertGreaterEqual(d_run - d_pin, 0.2, x["id"])
            self.assertLessEqual(d_run - d_pin, 0.32, x["id"])

    def test_the_head_seats_below_the_top_face_and_clamps(self):
        # the friction that holds a setting is the seat's, and what
        # preloads the seat is the head landing proud of its bore
        self.assertLess(W.HEAD_GAP, 0.0)
        for x in W.LAPWINGS:
            k = x["id"][3:]
            pin = self.parts[f"lapwing_{k}_pin"]
            up = self.parts[f"lapwing_{k}_upper"]
            head_low = float(pin.bounds[1][2]) - W.PIN_HEAD[1]
            self.assertLess(head_low, float(up.bounds[1][2]) - 1e-9, x["id"])
            h = self.rep["hold"][x["id"]]
            # honest about it: weight alone does not hold, the preload does
            self.assertGreater(h["preload_N"], 0.0, x["id"])

    def test_it_stands_up_to_a_tooth_leaning_back(self):
        # only the lower frame touches the table, so this is the number
        # the design trades away -- it must still beat the scissor
        # X-wing, which carries its tail under the other arm
        for x in W.LAPWINGS:
            self.assertGreater(self.rep["tip_back_deg"][x["id"]], 12.0,
                               x["id"])
        self.assertGreater(self.rep["tip_back_deg"]["lp_l"],
                           T.tip_back(T.XW_BY_ID["xw_l"]))

    def test_export_carries_the_wings_inside_the_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "wings.3mf")
            bad = W.export(self.parts, out, self.rep)
            self.assertEqual(bad, {})
            with zipfile.ZipFile(out) as z:
                names = z.namelist()
                self.assertIn("Metadata/lap_wing.json", names)
                self.assertIn("Metadata/project_settings.config", names)
                d = json.loads(z.read("Metadata/lap_wing.json"))
                ps = z.read("Metadata/project_settings.config").decode()
            self.assertIn('"brim_type": "no_brim"', ps)
            self.assertEqual(set(d["to_world"]), set(self.parts))
            import trimesh
            sc = trimesh.load(out, force="scene")
            for n, g in sc.geometry.items():
                M = np.array(d["to_world"][n]).reshape(4, 4)
                back = g.copy()
                back.apply_transform(M)
                self.assertLess(np.abs(back.bounds - self.parts[n].bounds)
                                .max(), 0.01, n)


if __name__ == "__main__":
    unittest.main()
