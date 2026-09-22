"""The tooth stands: what the printed set has to do, measured.

Built once from its defaults; every test reads the same four bodies. The
gates here are the generator's own, re-asserted so a change that quietly
stops measuring something is caught -- plus the negative controls, which
are the only reason to believe the numbers. An occlusion probe that
reports zero is worthless until it has been shown to report something
else when something is in the way.
"""
import json
import os
import re
import sys
import tempfile
import unittest
import zipfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gen_tooth_stand as T  # noqa: E402


class TestStands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = T.build("all")
        cls.rep = T.measure(cls.parts)

    def test_every_gate_passes(self):
        failed = [n for n, ok in T.gates(self.rep) if not ok]
        self.assertEqual(failed, [], json.dumps(self.rep, default=str)[:900])

    def test_every_body_is_watertight(self):
        # four fixed stands, and two bodies per print-in-place X-wing
        # four fixed stands; per X-wing: two arms, two pins, two cones, two dowels
        self.assertEqual(len(self.parts), len(T.STANDS) + 8 * len(T.XWINGS))
        self.assertTrue(all(m.is_watertight for m in self.parts.values()))

    def test_every_body_fits_the_plate(self):
        flat, _ = T.layout(self.parts)
        for n, m in flat.items():
            e = sorted(m.extents[:2])
            self.assertLessEqual(e[1] + 3.0, 246.0 + 1e-9, n)

    def test_laid_out_bodies_do_not_overlap(self):
        # the packer decides "assembly or separate parts" by overlapping
        # bounds; the X-wing's blades print apart and bolt together
        flat, _ = T.layout(self.parts)
        names = list(flat)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                la, ha = flat[a].bounds
                lb, hb = flat[b].bounds
                self.assertFalse((la < hb).all() and (lb < ha).all(),
                                 f"{a} overlaps {b} on the plate")

    def test_plate_pose_round_trips_to_the_built_pose(self):
        flat, poses = T.layout(self.parts)
        for n in flat:
            back = flat[n].copy()
            back.apply_transform(poses[n])
            self.assertLess(np.abs(back.vertices - self.parts[n].vertices)
                            .max(), 1e-6, n)

    # --- the support quadrilateral ------------------------------------
    def test_four_tips_two_per_lobe(self):
        for s in T.STANDS:
            pts = T.tips(s)
            self.assertEqual(len(pts), 4, s["id"])
            xs = sorted({round(x, 6) for x, _ in pts})
            ys = sorted({round(y, 6) for _, y in pts})
            self.assertEqual(len(xs), 2, "two lobes")
            self.assertEqual(len(ys), 2, "fore and aft on each")
            self.assertAlmostEqual(xs[1] - xs[0], s["cross"])
            self.assertAlmostEqual(ys[1] - ys[0], s["fore"])

    def test_the_four_dishes_are_coplanar(self):
        for n, dz in self.rep["coplanar_mm"].items():
            self.assertIsNotNone(dz, n)
            self.assertLess(dz, 0.05, n)

    def test_the_coplanarity_probe_can_see_a_short_cone(self):
        # negative control: the probe reads the built mesh, so a stand
        # with one cone shortened must come back non-coplanar
        spec = T.BY_ID["m"]
        short = dict(spec)
        m = T.stand(spec)
        # 1.5 mm below the cup FLOOR, which is what the probe reads
        sunk = T.cyl(6.0, T.dish_z(spec) - 1.5, T.contact_z(spec) + 5.0,
                     *T.tips(spec)[0], sections=32)
        chopped = T.cut(m, [sunk])
        dz, _ = T.tips_coplanar(short, chopped)
        self.assertIsNotNone(dz)
        self.assertGreater(dz, 1.0, "a 1.5 mm short cone must be seen")

    def test_tip_is_the_spec_diameter(self):
        for n, d in self.rep["tip_dia_mm"].items():
            self.assertIsNotNone(d, n)
            spec = T.spec_of(n if not n.startswith("xwing") else n + "_base")
            self.assertAlmostEqual(d, 2 * T.tip_r(spec), delta=0.1, msg=n)
            self.assertGreaterEqual(d, 2.1, n)   # a cup a wax dab fits in
            self.assertLessEqual(d, 4.0, n)
            # and the cup is a real bowl, two thirds of its radius deep
            self.assertGreaterEqual(T.dish_d(spec), 0.6, n)

    def test_taper_stays_in_the_specs_six_to_eight_degrees(self):
        for s in T.STANDS:
            included = 2 * np.degrees(np.arctan(
                (T.cone_base_r(s["cone"], s) - T.tip_r(s)) / s["cone"]))
            self.assertGreaterEqual(included, 6.0, s["id"])
            self.assertLessEqual(included, 8.0, s["id"])

    # --- the optical claim --------------------------------------------
    def test_nothing_rises_above_the_contact_plane(self):
        for n, v in self.rep["above_contact_mm"].items():
            self.assertLessEqual(v, 1e-6, f"{n} pokes {v:+.3f} mm above")

    def test_the_stand_occludes_nothing_from_any_ring(self):
        for n, o in self.rep["occlusion"].items():
            self.assertLess(o["overall"], 1.0, n)

    def test_the_occlusion_probe_sees_an_obstruction_that_is_there(self):
        """The control that makes the zero above mean anything."""
        spec = T.BY_ID["l"]
        spm, _ = T.surrogate(spec)
        z = T.contact_z(spec)
        # a post beside the specimen, as tall as it is: must be seen
        post = T.cyl(8.0, z, float(spm.bounds[1][2]), x=55.0, y=0.0,
                     sections=48)
        seen = T.occlusion(post, spec)
        self.assertGreater(seen["per_ring"]["15"], 3.0)
        self.assertGreater(seen["per_ring"]["35"], 3.0)

    def test_an_obstruction_below_the_contact_plane_cannot_occlude(self):
        """Why the geometric gate is the one that carries the claim: even
        a 120 mm disc hides nothing, so staying below the plane is both
        necessary and sufficient."""
        spec = T.BY_ID["l"]
        disc = T.cyl(60.0, T.contact_z(spec) - 3.0, T.contact_z(spec) - 0.5,
                     sections=64)
        self.assertEqual(T.occlusion(disc, spec)["overall"], 0.0)

    # --- the dock ------------------------------------------------------
    def test_the_underside_is_one_flat_plane(self):
        # hub and arms end at z = 0 and nothing reaches below: the stand
        # sits on the platform or on a table the same way
        for n, m in self.parts.items():
            if "_cone" in n or "_dowel" in n:
                continue                  # the loose cones and dowels stand on the arm
            if n.endswith("_pin2"):
                continue                  # the spare pin, same as the pin
            self.assertAlmostEqual(float(m.bounds[0][2]), 0.0, places=6, msg=n)
            low = m.vertices[m.vertices[:, 2] < 1e-6]
            self.assertGreater(len(low), 3, n)

    def test_the_hub_sits_on_the_platform(self):
        for n, m in self.parts.items():
            if ('_pin' in n or n.endswith('_nut')) or '_cone' in n or '_dowel' in n:
                continue                  # the pivot's parts, not a stand
            lo, hi = m.bounds
            self.assertLessEqual(T.HUB_R * 2, max(hi[0] - lo[0],
                                                  hi[1] - lo[1]) + 1e-6, n)

    def test_the_family_covers_the_measured_size_range(self):
        bands = [s["teeth"] for s in T.STANDS]
        self.assertLessEqual(bands[0][0], 10.0)       # smallest measured
        self.assertGreaterEqual(bands[-1][1], 150.0)  # past p99
        for a, b in zip(bands, bands[1:]):            # no gap between them
            self.assertLessEqual(b[0], a[1])

    def test_xwings_open_over_a_useful_range_and_print_free(self):
        for n, o in self.rep["xwing_opening"].items():
            self.assertIsNotNone(o, n)
            spec = T.spec_of(n + "_base")
            self.assertLessEqual(o["beta"][0], spec["alpha"], n)
            self.assertGreaterEqual(o["beta"][1], spec["alpha"], n)
            # the swing is what the hub-only cut allows, measured, and
            # the default sits inside it

    def test_the_opening_sweep_sees_a_collision_that_is_there(self):
        # negative control: turned well past its measured range the upper
        # arm must collide, so the range is a measurement and not a guess
        import trimesh.collision as tc
        spec = T.XW_BY_ID["xw_l"]
        o = self.rep["xwing_opening"]["xwing_l"]
        base, top = self.parts["xwing_l_base"], self.parts["xwing_l_top"]
        cm = tc.CollisionManager()
        cm.add_object("base", base)
        cm.add_object("top", top)
        past = o["beta"][0] - 10.0
        cm.set_transform("top", T.rot(2.0 * (past - spec["alpha"]), [0, 0, 1]))
        self.assertTrue(cm.in_collision_internal())

    def test_the_upper_arm_cut_is_the_hub_profile(self):
        # the underside cut is the lower hub's negative plus the holdoff
        for x in T.XWINGS:
            r = T.xw_relief(x)
            want = np.pi * (T.XW_HUB_R + T.XW_HOLDOFF) ** 2
            self.assertAlmostEqual(r.area, want, delta=0.01 * want)

    def test_both_arms_sit_flat_on_the_table(self):
        # all four spires on the ground: each arm's pads touch z = 0
        for x in T.XWINGS:
            for part in ("base", "top"):
                m = self.parts[f"xwing_{x['id'][3:]}_{part}"]
                self.assertAlmostEqual(float(m.bounds[0][2]), 0.0, places=6, msg=part)
                low = m.vertices[m.vertices[:, 2] < 1e-6]
                self.assertGreater(float(np.ptp(low[:, 0])), x["L"], part)

    def test_the_pin_is_a_press_fit_in_both_arms(self):
        for n, f in self.rep["xwing_pin_fit"].items():
            # measured off the built bodies: a press below, a run above
            # drawn 0.1 over the pin, which PETG prints as a firm press
            self.assertGreaterEqual(f["press_clearance"], 0.05, n)
            self.assertLessEqual(f["press_clearance"], 0.15, n)
            # tightened after the first print: Ø3.4 turned too freely to
            # hold a setting
            self.assertGreaterEqual(f["run_clearance"], 0.15, n)
            self.assertLessEqual(f["run_clearance"], 0.3, n)
            self.assertGreaterEqual(f["press_engagement"], 4.0, n)
            self.assertGreaterEqual(f["run_engagement"], 4.0, n)

    def test_the_loose_cones_print_on_their_feet_and_the_dowels_fit(self):
        for n, f in self.rep["xwing_cone_fit"].items():
            self.assertGreater(f["cone_on_plate_mm2"], 25.0, n)   # a foot, not a spigot
            self.assertLess(f["cone_lever"], 5.0, n)
            roof = np.pi * T.XW_CONE_SOCKET_R ** 2
            self.assertLess(f["cone_overhang_mm2"], roof * 1.1, n)  # only the socket's roof
            # drawn sizes that PETG prints as a press and a slip
            # drawn +0.15 on both after the first print: at +0.35 a post
            # fell off its dowel, and the arm's socket ran too deep
            self.assertGreaterEqual(f["arm_clearance"], 0.1, n)
            self.assertLessEqual(f["arm_clearance"], 0.2, n)
            self.assertGreaterEqual(f["cone_clearance"], 0.1, n)
            self.assertLessEqual(f["cone_clearance"], 0.2, n)
        # a dowel reaches well into the arm and into the cone, and bottoms
        # in neither: the first print's would not seat and had to be glued
        for x in T.XWINGS:
            d = self.parts[f"xwing_{x['id'][3:]}_dowel0"]
            into_arm = T.XW_UP_T - float(d.bounds[0][2])
            proud = float(d.bounds[1][2]) - T.XW_UP_T
            # 3.5 before the arm's socket was made shallower: the first
            # print stood 3.45 of dowel proud with only 3.2 of post socket
            # to enter, so the split moved the other way
            self.assertGreaterEqual(into_arm, 3.0, x["id"])
            self.assertLessEqual(into_arm, T.XW_SOCKET[1] - 0.15, x["id"])
            # more in the post than in the arm: the first print stood its
            # dowels 3.45 proud with only 3.2 of socket to go into
            self.assertGreater(proud, into_arm, x["id"])
            self.assertLessEqual(proud, T.xw_cone_socket(x)[1] - 0.2, x["id"])

    def test_the_spare_pin_is_fatter_only_where_it_runs(self):
        # friction at the pivot holds a setting, so a second pin goes on the
        # plate: the same press into the lower arm, tighter in the upper
        for n, f in self.rep["xwing_pin_fit"].items():
            self.assertIsNotNone(f["tight_pin_d"], n)
            # tighter than the plain pin but still enterable: at Ø3.3 the
            # first spare would not go in at all
            self.assertLessEqual(f["tight_run_clearance"], 0.1, n)
            self.assertGreaterEqual(f["tight_run_clearance"], 0.0, n)
            self.assertLess(f["tight_run_clearance"], f["run_clearance"], n)
        for x in T.XWINGS:
            k = x["id"][3:]
            spare = self.parts[f"xwing_{k}_pin2"]
            plain = self.parts[f"xwing_{k}_pin"]
            # identical where it presses into the lower arm
            self.assertAlmostEqual(T._shaft_d(spare, T.ARM_T / 2),
                                   T._shaft_d(plain, T.ARM_T / 2), delta=0.01)
            # fatter overall, and dimpled on the head so the two are not
            # mixed up: a point just under the head's top is inside the
            # plain pin and inside the spare's dimple
            self.assertGreater(spare.volume, plain.volume)
            probe = [[0.0, 0.0, float(plain.bounds[1][2]) - T.XW_PIN_MARK[1] / 2]]
            self.assertTrue(bool(plain.contains(probe)[0]), x["id"])
            self.assertFalse(bool(spare.contains(probe)[0]), x["id"])

    def test_both_pins_lie_on_their_heads_and_nothing_is_brimmed(self):
        # the first plate gave back one usable head out of two: a brim at
        # zero gap around a Ø6 disc is cut off through the head. The head
        # is the pin's one flat face and carries the whole part, so the
        # pose is right and it was the brim that was wrong
        flat, _ = T.layout(self.parts)
        for n, m in flat.items():
            if not ("_pin" in n and "_pin_" not in n):
                continue
            low = m.triangles_center[:, 2] < 1e-6
            area = float(m.area_faces[low].sum())
            self.assertGreater(area, 20.0, n)          # the head, not the tip
            lever = float(m.bounds[1][2]) / np.sqrt(area / np.pi)
            self.assertLess(lever, 4.0, n)             # stands up unaided
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "plate.3mf")
            T.export(self.parts, out)
            self.assertEqual(self._brimmed(out), [])   # nothing, by default
            # and when a group is asked for, the brim lands on those bodies
            # and the PLATE stays off -- brim_type is otherwise plate-wide,
            # which is how every part came back with one
            T.BRIM_ON = [T.BRIM_GROUPS["dowels"]]
            try:
                out2 = os.path.join(tmp, "brimmed.3mf")
                T.export(self.parts, out2)
                got = self._brimmed(out2)
            finally:
                T.BRIM_ON = []
            self.assertTrue(got)
            for n in got:
                self.assertIn("_dowel", n)
            with zipfile.ZipFile(out2) as z:
                ps = z.read("Metadata/project_settings.config").decode()
            self.assertIn('"brim_type": "no_brim"', ps)

    @staticmethod
    def _brimmed(path):
        """The bodies carrying their own brim record, by name. The names
        live in a metadata key, not an attribute: reading them as an
        attribute matched nothing and the check passed on an empty list."""
        with zipfile.ZipFile(path) as z:
            ms = z.read("Metadata/model_settings.config").decode()
        out = []
        for obj in re.findall(r"<object[^>]*>.*?</object>", ms, re.S):
            name = re.search(r'key="name" value="([^"]*)"', obj)
            if name and "brim" in obj:
                out.append(name.group(1))
        return sorted(out)

    def test_a_brimmed_plate_leaves_room_between_the_brims(self):
        # at 5 mm wide and 6 mm apart the posts' brims merged into a raft
        from shapely.ops import unary_union
        T.BRIM_ON = [T.BRIM_GROUPS["posts"], T.BRIM_GROUPS["dowels"]]
        try:
            flat, _ = T.layout(self.parts)
            foot = {}
            for n, m in flat.items():
                sec = m.section(plane_origin=[0, 0, 0.2],
                                plane_normal=[0, 0, 1])
                polys, to3 = sec.to_planar()
                shape = unary_union([p for p in polys.polygons_full])
                # to_planar drops the world offset; put it back
                off = to3[:2, 3]
                from shapely import affinity
                shape = affinity.translate(shape, off[0], off[1])
                if T.takes_brim(n):
                    shape = shape.buffer(T.BRIM_W)
                foot[n] = shape
            names = list(foot)
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    self.assertFalse(foot[a].intersects(foot[b]),
                                     f"{a} and {b} touch on the plate")
            # the control, and the plate in the photo: the packer that
            # did not know about brims, with the 5 mm brim it was given
            T.BRIM_ON = []
            plain, _ = T.layout(self.parts)
            small = {n: self._foot(m, 5.0) for n, m in plain.items()
                     if any(t in n for t in ("_cone", "_dowel"))}
            ns = list(small)
            merged = [(a, b) for i, a in enumerate(ns) for b in ns[i + 1:]
                      if small[a].intersects(small[b])]
            self.assertTrue(merged, "the check cannot see a merged brim")
        finally:
            T.BRIM_ON = []

    @staticmethod
    def _foot(m, grow):
        from shapely.ops import unary_union
        from shapely import affinity
        sec = m.section(plane_origin=[0, 0, 0.2], plane_normal=[0, 0, 1])
        polys, to3 = sec.to_planar()
        sh = affinity.translate(unary_union(list(polys.polygons_full)),
                                to3[0, 3], to3[1, 3])
        return sh.buffer(grow) if grow else sh

    def test_the_saw_grip_points_its_barbs_down_and_prints_clean(self):
        # the posts squeeze a tapered root UP and out, so the face that
        # does the work is the one a rising root runs into: going up the
        # flank the radius steps OUT, then eases back in
        spec = T.BY_ID["l"]
        smooth = T.cone_profile(spec["cone"], 0.0, spec)
        T.GRIP = "saw"
        try:
            saw = T.cone_profile(spec["cone"], 0.0, spec)
            m = T.stand(spec)
        finally:
            T.GRIP = "smooth"
        self.assertTrue(m.is_watertight)
        # barbs: segments that go up and OUT, each one a step of about
        # SAW_DEPTH, and enough of them to be a grip rather than a ridge
        def out_steps(prof):
            # everything that goes up and outward; the arc that blends the
            # flank to the deck is sampled, so ignore rounding-sized ones
            return [(r1 - r0, z1 - z0) for (r0, z0), (r1, z1)
                    in zip(prof, prof[1:])
                    if r1 - r0 > 0.01 and z1 > z0 + 1e-9]
        steps = out_steps(saw)
        self.assertGreaterEqual(len(steps), 5)
        for dr, dz in steps:
            self.assertAlmostEqual(dr, T.SAW_DEPTH, delta=0.05)
            # and the underside of the barb stays inside 45 degrees, so it
            # prints with no support: the slicer is the outside check
            self.assertLess(np.degrees(np.arctan2(dr, dz)), 45.0)
        # the smooth profile has no such step at all -- the control
        self.assertEqual(out_steps(smooth), [])
        # and the cup is untouched: the grip is on the flank only
        self.assertAlmostEqual(T.tips_coplanar(spec, m)[0], 0.0, places=3)

    def test_the_upper_arm_prints_without_a_bridge(self):
        # roof-down, the only downward faces off the plate are the two
        # cone sockets' floors, each a few millimeters across
        for n, pr in self.rep["xwing_print"].items():
            sock = 2 * np.pi * T.XW_SOCKET[0] ** 2
            self.assertLessEqual(pr["overhang_mm2"], sock * 1.5, n)
            self.assertLessEqual(pr["widest_mm"], 2 * T.XW_SOCKET[0] + 1.0, n)
        # negative control: the cones-up arm this replaced, a 5 mm bar with
        # a tower in the middle, hangs off that tower when printed roof-down
        spec = T.XW_BY_ID["xw_l"]
        bar = T.xw_bar(spec["L"], T.xw_pad_r(spec), 0.0, T.ARM_T, 0.0)
        stepped = T.union([bar, T.cyl(T.XW_HUB_R, T.ARM_T - 0.5, T.XW_UP_T)])
        self.assertGreater(T.xw_print_overhang(stepped)["overhang_mm2"], 50.0)

    def test_each_arm_sits_on_the_plate(self):
        # the lower arm prints cones up; the upper arm prints roof-down, a
        # flat top XW_UP_T tall with its whole footprint on the plate
        flat, _ = T.layout(self.parts)
        for x in T.XWINGS:
            k = x['id'][3:]
            base = flat[f"xwing_{k}_base"]
            self.assertAlmostEqual(float(base.bounds[0][2]), 0.0, places=6)
            self.assertGreater(float(base.bounds[1][2]), x["cone"])
            top = flat[f"xwing_{k}_top"]
            self.assertAlmostEqual(float(top.bounds[0][2]), 0.0, places=6)
            self.assertAlmostEqual(float(top.extents[2]), T.XW_UP_T, places=6)
            on = (top.face_normals[:, 2] < -0.99) & (top.triangles_center[:, 2] < 1e-6)
            area = float(top.area_faces[on].sum())
            plan = T.xw_plan(x["L"], T.xw_pad_r(x)).area
            # less the pin bore and the two dowel sockets' mouths
            self.assertGreater(area, 0.85 * plan, k)

    def test_the_cups_are_coplanar_with_the_blade_on_its_seat(self):
        # the pose under a tooth, not a pose it floats in: the upper blade
        # is built resting on the boss, and its cups must meet the base's
        for n, v in self.rep["coplanar_mm"].items():
            if n.startswith("xwing"):
                self.assertLess(v, 0.05, n)

    def test_the_tips_are_not_the_fragile_point(self):
        for k, v in self.rep["cone_stress_MPa"].items():
            self.assertLess(v, 15.0, k)
        # the spec's point, for the record: the same push, a 1.3 mm tip
        needle = T.cone_stress(dict(cone=24.0, tip=0.65))
        self.assertGreater(needle, 30.0)

    def test_export_carries_the_stands_inside_the_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "stands.3mf")
            bad, meta = T.export(self.parts, out)
            self.assertEqual(bad, {})
            with zipfile.ZipFile(out) as z:
                names = z.namelist()
                self.assertIn("Metadata/tooth_stand.json", names)
                self.assertIn("Metadata/project_settings.config", names)
                d = json.loads(z.read("Metadata/tooth_stand.json"))
            self.assertEqual(set(d["to_world"]), set(self.parts))
            self.assertEqual([s["id"] for s in d["stands"]],
                             [s["id"] for s in T.STANDS])
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
