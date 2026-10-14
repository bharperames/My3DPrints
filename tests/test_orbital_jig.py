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
from unittest import mock
import zipfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gen_orbital_jig as J  # noqa: E402

# Ø1 carbon rod stock, as cut for the field; one place, not three
ROD_NOMINAL = 20.0


class TestJig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = J.assemble(J.SPECIMEN)
        cls.rep = J.measure(cls.parts, J.SPECIMEN)

    def test_every_gate_passes(self):
        failed = [n for n, ok in J.gates(self.rep) if not ok]
        self.assertEqual(failed, [], json.dumps(self.rep, default=str)[:800])

    def test_twenty_four_bodies_all_watertight(self):
        self.assertEqual(len(self.parts), 24)
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
            # laid out is as printed: with its skins over holes in bridges
            want = J.printed(n, self.parts[n])
            self.assertLess(np.abs(back.vertices - want.vertices).max(), 1e-6, n)

    def test_skins_are_printed_and_never_assembled(self):
        """A hole opening through a bridge gets a one-layer skin in the
        printed file; the assembled part, which the sweeps see, has none."""
        for n in ("drive_block", "stator"):
            sk = self.parts[n].metadata.get("membranes")
            self.assertTrue(sk, n)
            added = J.printed(n, self.parts[n]).volume - self.parts[n].volume
            self.assertTrue(1.0 < added < 20.0, (n, added))

    def test_pupil_sits_on_the_working_sphere_in_the_meridian(self):
        for th in (10.0, 15.0, 35.0, 55.0, 75.0, 80.0):
            p = J.pupil(th)
            self.assertAlmostEqual(float(np.linalg.norm(p)), J.R, places=6)
            self.assertAlmostEqual(float(p[1]), 0.0, places=6)
            self.assertAlmostEqual(float(p[2]), J.R * np.sin(np.radians(th)),
                                   places=6)

    def test_the_protocol_keeps_108_frames_on_the_genevas_stops(self):
        frames = [int(round(360.0 / p["step"])) for p in J.PROTOCOL]
        self.assertEqual(frames, [36, 36, 18, 18])
        pitch = 360.0 / J.GENEVA_N
        for p in J.PROTOCOL:
            self.assertAlmostEqual(p["step"] / pitch,
                                   round(p["step"] / pitch), places=9)
        self.assertEqual(sum(frames), 108)
        self.assertEqual([p["elev"] for p in J.PROTOCOL], [15, 35, 55, 75])

    def test_slots_are_seen_and_a_missing_one_would_be(self):
        self.assertEqual(self.rep["slots"], 36)
        # negative control: probe a ring with one slot filled in
        z = J.levels(J.SPECIMEN)["ring_bot"]
        x, y, _ = J.polar((J.GENEVA_MOUTH + J.GENEVA_C + J.GENEVA_A) / 2.0,
                          J.GENEVA_PHI + 5.0)
        plug = J.cyl(J.PIN_R + J.SLOT_CLR + 0.3, z, z + J.LIP_T, x, y)
        filled = J.union([self.parts["rotor"], plug])
        self.assertEqual(J.count_slots(filled, J.SPECIMEN), 35)


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

    def test_arc_is_concentric_and_a_closed_box(self):
        """No slot down its length: the thumbscrew clamps outside it, so
        the box's four walls run unbroken from the leg to the top."""
        lo, hi = self.rep["arc_radii"]
        self.assertGreaterEqual(lo, J.ARC_RI - 0.05)
        self.assertLessEqual(hi, J.ARC_RO + 0.05)
        self.assertEqual(self.rep["slot_mm"], 1.0)

    def test_a_slotted_arc_would_be_caught(self):
        """Negative control: a slot cut down the outboard wall."""
        a = self.parts["arc"].copy()
        a.apply_transform(np.linalg.inv(J.M_ARC))
        cut_ = J.sector(J.ARC_RI - 1, J.ARC_RO + 1, -J.ARC_HW - 1, -J.ARC_HW + 2, 20, 70)
        a = J.cut(a, [cut_])
        a.apply_transform(J.M_ARC)
        self.assertLess(J.slot_width(a), 1.0)

    def test_the_clamp_stands_clear_of_the_box(self):
        self.assertGreater(J.CLAMP_R - J.SCREW_R, J.ARC_RO + J.LIP_CLR + J.LIP_T)

    def test_the_dial_moves_the_pad_and_not_the_arc(self):
        """Stated as a rate, not an identity.

        This asserted pad_t == specimen, which was only ever true because
        PED_H happened to be 50. Shortening the pedestal to 32 broke the
        test without breaking anything it was there to protect: what
        matters is that a millimetre of dial is a millimetre of pad and
        nothing else moves, whatever the pedestal is.
        """
        self.assertLess(np.abs(self.parts["arc"].vertices
                               - J.arc().vertices).max(), 1e-9)
        lo, hi = J.SPECIMEN_RANGE
        a, b = lo + 5.0, lo + 25.0
        self.assertAlmostEqual(J.levels(b)["pad_t"] - J.levels(a)["pad_t"],
                               b - a)
        # and the arc's bar still lands on the pad's slot floor at any dial
        for sp in (a, b, hi):
            self.assertAlmostEqual(J.levels(sp)["pad_top"] - J.PAD_SLOT_D,
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


class TestVWheels(unittest.TestCase):
    """The ring rides V wheels: seated on both faces of its groove, with no
    axial play to rock in, and the load on the V's faces."""

    @classmethod
    def setUpClass(cls):
        cls.parts = J.assemble(J.SPECIMEN)

    def test_every_wheel_seats_on_the_groove(self):
        for c in J.race_contact(self.parts["rotor"], J.SPECIMEN):
            self.assertLess(c["gap"], 0.05)
            self.assertTrue(c["pressed_collides"])

    def test_the_ring_has_no_axial_play(self):
        """Lifted 0.1 mm, the ring runs into every wheel's V: nothing lets
        it rock but the towers' own give."""
        import trimesh.collision as tc
        ring = self.parts["rotor"].copy()
        ring.apply_translation([0, 0, 0.1])
        cm = tc.CollisionManager()
        cm.add_object("ring", ring)
        for w in J.bearing_proxies(J.SPECIMEN):
            self.assertTrue(cm.in_collision_single(w))

    def test_the_tip_never_bottoms(self):
        """The groove runs deeper than the V's tip enters: only the faces
        carry load."""
        prof = np.array(J.ring_profile())
        root = prof[:, 0][prof[:, 0] < J.RING_RO - 0.01].min()
        self.assertLess(root, J.RACE_R - 0.3)

    def test_the_wheel_takes_688s_on_the_same_sleeve(self):
        bom = J.inserts()
        self.assertEqual(bom[J.WHEEL_BRG_ITEM], 6)
        self.assertEqual(J.BRG_BORE, 8.0)

    def test_the_printed_wheel_bore_is_drawn_for_a_snug_688(self):
        """Measured off the built wheel, at mid-depth of each bearing: a
        plain bore a little over the 688's Ø16, to print near it."""
        w = J.wheel()
        for z in (-2.6, 2.6):
            sec = w.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
            loops = [np.asarray(L)[:, :2] for L in sec.discrete]
            inner = min(loops, key=lambda L: np.abs(L).max())
            r = np.hypot(inner[:, 0], inner[:, 1])
            self.assertGreater(r.min(), 8.0)
            self.assertLess(r.max(), 8.1)
        # the profile the race was cut for is unchanged
        self.assertAlmostEqual(w.bounds[1][0], J.WHEEL["r"], delta=0.01)
        self.assertAlmostEqual(w.extents[2], J.WHEEL["w"], delta=0.01)


class TestCornerFeet(unittest.TestCase):
    """Each tower stands on a foot glued to the board, not on 100 mm of
    8 mm plate cantilevered past the line between two bolts."""

    @classmethod
    def setUpClass(cls):
        cls.parts = J.assemble(J.SPECIMEN)

    def test_the_card_and_the_generator_name_the_same_settings(self):
        import catalog
        card = catalog.find("orbital_jig")
        self.assertEqual(card["print"]["filament"], J.FILAMENT)
        self.assertEqual(card["print"]["settings"], J.PRINT_SETTINGS)
        self.assertEqual(set(card["brim_bodies"]), set(J.BRIMMED))

    def test_the_filament_preset_exists_for_this_printer(self):
        from embed_settings import flatten
        f = flatten("filament", J.FILAMENT)
        self.assertEqual(f["filament_type"], ["PETG"])


class TestGeneva(unittest.TestCase):
    """The ring is turned, stopped and held by a Geneva drive.

    A sweep that finds nothing proves nothing on its own: a driver that
    never reached the lip would sweep clean. So each claim is paired with
    the part made wrong in the one way that claim is about, and the
    instrument has to notice.
    """

    @classmethod
    def setUpClass(cls):
        cls.parts = J.assemble(J.SPECIMEN)
        cls.g = J.geneva_sweep(cls.parts, J.SPECIMEN)

    def test_a_whole_driver_turn_is_clear_and_moves_the_ring_one_stop(self):
        self.assertEqual(self.g["fouls"], [])
        self.assertAlmostEqual(self.g["advance_deg"], 10.0, places=9)

    def test_at_a_stop_the_ring_is_locked_and_mid_slot_it_is_driven(self):
        self.assertTrue(self.g["locked"])
        self.assertTrue(self.g["driven"])

    def test_it_runs_with_the_ring_off_where_the_driver_expects_it(self):
        """The post's play in its socket, the ring centred by hand and the
        two big parts shrinking differently put the lip a few tenths off
        the driver either way. It must run 0.4 mm off in every direction,
        with the ring free to follow the pin as a real one is."""
        w = J.geneva_window(self.parts)
        for k in ("in", "out", "across", "across_back"):
            self.assertEqual(w[k], 0, k)
        self.assertTrue(w["control_jams"])

    def test_without_the_bias_the_lip_closes_on_the_lock(self):
        """Negative control: the driver where the lip was cut for, and the
        ring 0.4 mm toward the axis, jams at the stops."""
        with mock.patch.object(J, "GENEVA_AT", J.GENEVA_C):
            parts = dict(self.parts, driver=J.driver())
            _, u, _ = J._driver_frame()
            self.assertTrue(J.geneva_follows(parts, -u[:2] * J.GENEVA_STACK))

    def test_the_law_starts_and_ends_each_step_at_rest(self):
        w = J.geneva_wheel
        half = 90.0 + 180.0 / J.GENEVA_N
        for edge in (360.0 - half, 360.0 + half):
            for side in (-1, 1):
                d = abs(w(edge + side * 0.01) - w(edge)) / 0.01
                self.assertLess(d, 0.01, f"ring moving at {edge}+{side}")
        self.assertGreater((w(361.0) - w(359.0)) / 2.0, 0.05)

    def test_an_unrelieved_lock_would_jam(self):
        """Negative control for the sweep: the lock as a whole Ø6 disc."""
        Z = J.driver_levels(J.SPECIMEN)
        o, _, _ = J._driver_frame()
        parts = dict(self.parts)
        parts["driver"] = J.union([self.parts["driver"],
                                   J.cyl(J.LOCK_R, Z["lock_lo"], Z["crank_lo"],
                                         o[0], o[1])])
        self.assertTrue(J.geneva_sweep(parts, J.SPECIMEN, step=5.0)["fouls"])

    def test_without_its_lock_the_ring_would_not_be_held(self):
        """Negative control for `locked`: the lock cut off the driver."""
        Z = J.driver_levels(J.SPECIMEN)
        o, _, _ = J._driver_frame()
        parts = dict(self.parts)
        parts["driver"] = J.cut(self.parts["driver"],
                                [J.cyl(J.LOCK_R + 0.5, Z["lock_lo"] - 1.0,
                                       Z["crank_lo"] - 0.01, o[0], o[1])])
        self.assertFalse(J.geneva_sweep(parts, J.SPECIMEN, step=90.0)["locked"])

    def test_the_driver_drops_in_through_a_seat(self):
        """It is fitted from above after the ring: everything below the
        crank must pass down through the lock seat it stands in."""
        Z = J.driver_levels(J.SPECIMEN)
        d = self.parts["driver"]
        o, _, _ = J._driver_frame()
        below = d.vertices[d.vertices[:, 2] < Z["crank_lo"] - 0.01]
        lip_z = J.levels(J.SPECIMEN)["ring_bot"]
        # the lip's own thickness: what passes down through the seat. Above
        # the lip's top the driver never enters it, and the lock's root
        # fillet lives there, under the crank
        for z in np.linspace(lip_z, lip_z + J.LIP_T, 5):
            sec = d.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
            v = sec.vertices
            r = np.hypot(v[:, 0] - o[0], v[:, 1] - o[1])
            self.assertLessEqual(r.max(), J.LOCK_R + 1e-6, z)
        self.assertGreater(Z["crank_lo"] - J.LOCK_FILLET, lip_z + J.LIP_T)
        # nothing hangs below the lock but the pin, which points at the
        # rotor axis at a stop, where the bore is open
        self.assertGreaterEqual(below[:, 2].min(), Z["lock_lo"] - 1e-4)

    def test_every_screw_is_reached_from_above(self):
        """The foot bolts, the drive post's screw and the cap's screws:
        nothing over their heads, so the jig comes off its pucks, and
        the drive out of it, without lifting anything."""
        import trimesh
        others = trimesh.util.concatenate(
            [m for n, m in self.parts.items()
             if n not in ("stator", *J.PUCKS, "drive_block", "drive_cap",
                          "driver")])
        L = J.levels(J.SPECIMEN)
        Z = J.driver_levels(J.SPECIMEN)
        o, u, t = J._driver_frame()
        rays, floor = [], []
        for a in J.FOOT_PHI:
            for dr in (-J.FOOT_CBORE[0], 0.0, J.FOOT_CBORE[0]):
                rays.append(J.polar(J.FOOT_R + dr, a, 400.0))
                floor.append(L["base_top"])
        # the post's screw, down its access bore (lid off)
        post = o + u * (J.POST_R - J.GENEVA_C) + t * J.SCREW_Y + np.array([0, 0, 400.0])
        rays.append(post)
        floor.append(Z["face"] + 3.0)
        locs, idx, _ = others.ray.intersects_location(
            np.array(rays), np.tile([0, 0, -1.0], (len(rays), 1)),
            multiple_hits=False)
        for h, i in zip(locs, idx):
            self.assertLess(h[2], floor[i], f"something above ray {i}: {h}")


class TestRealDrive(unittest.TestCase):
    """The drive is real parts at their makers' sizes, and works.

    The gearmotor is Pololu #5173 from Pololu's dimension drawing; the
    home sensor is a Honeywell SS451A. What matters about each is
    tested where the design depends on it."""

    @classmethod
    def setUpClass(cls):
        cls.parts = J.assemble(J.SPECIMEN)

    def test_the_gearmotor_is_the_drawing(self):
        m = J.MOTOR
        self.assertEqual((m["w"], m["d"], m["gearbox"], m["body"]),
                         (12.0, 10.0, 9.0, 15.0))
        self.assertEqual((m["shaft_d"], m["shaft_flat"], m["shaft_l"]),
                         (3.0, 2.5, 10.0))

    def test_the_motor_has_torque_to_spare(self):
        """At 5 V the stall torque scales to about 0.33 N.m; the driver
        needs the ring's torque divided by the Geneva's leverage, which is
        least mid-step at a / (C + a)."""
        stall = J.MOTOR["stall_kgcm"] * 0.0980665 * 5.0 / 6.0
        lever = J.GENEVA_A / (J.GENEVA_C + J.GENEVA_A)
        ring_needs = 0.2                     # N.m: generous for three 608s
        self.assertGreater(stall / (ring_needs * lever), 10.0)

    def test_the_driver_hangs_on_the_motor_shaft(self):
        Z = J.driver_levels(J.SPECIMEN)
        # the shaft's tip sits in the crank, with crank left under it
        self.assertGreater(Z["shaft_tip"], Z["crank_lo"] + 1.0)
        self.assertLess(Z["shaft_tip"], Z["crank_hi"] - 5.0)

    def test_the_pin_is_held_over_the_whole_crank(self):
        self.assertEqual(J.CRANK_T, 8.0)
        Z = J.driver_levels(J.SPECIMEN)
        lip = J.levels(J.SPECIMEN)["ring_bot"]
        self.assertLess(Z["pin_lo"], lip)                  # through the lip

    def test_the_home_sensor_sees_its_magnet_closely(self):
        self.assertLessEqual(J.HOME["gap"], 3.0)

    def test_the_encoder_knows_the_driver_finely(self):
        """3,576 counts a driver turn: the controller can stop it anywhere
        in the lock's 170 degrees with three orders of margin."""
        self.assertAlmostEqual(J.MOTOR["counts"], 12 * 297.92)   # Pololu's exact ratio
        lock = 180.0 - 360.0 / J.GENEVA_N
        self.assertGreater(J.MOTOR["counts"] * lock / 360.0, 1000)

    def test_nothing_at_the_motor_is_soldered(self):
        """One plug carries motor and encoder; the BOM has no phase
        sensor, no second magnet, no inserts or screws for the lid."""
        bom = J.inserts()
        self.assertIn("side connector", J.MOTOR["item"])
        self.assertEqual(bom[J.HALL_ITEM], 1)
        self.assertIn("omnipolar", J.HALL_ITEM)
        self.assertNotIn("M2 heat-set insert", bom)
        self.assertFalse(any(k.startswith("M2x8") for k in bom))
        self.assertIn(J.CABLE_ITEM, bom)

    def test_nothing_that_turns_carries_a_wire(self):
        rotating = set(J.ROTOR_SIDE) | set(J.CARRIAGE)
        self.assertFalse(rotating & {"drive_block", "drive_cap", "ctrl_box"})
        self.assertIn("drive_block", J.STATOR_SIDE)

    def test_the_clamps_stud_stands_proud_and_cannot_turn(self):
        """The phone's clamp threads onto the 1/4-20: it needs thread
        above the receiver's top, but no more than a clamp's socket is
        deep, and the bolt's head held in a hex it cannot turn in."""
        proud = J.QTR_LEN - (J.RECV[2] - J.QTR_HEX[1])
        self.assertGreater(proud, 4.0)      # three threads and more
        self.assertLess(proud, 6.0)         # a shallow socket still seats
        r = self.parts["receiver"]
        # the pocket's flats: a round head would turn, a tight one jams
        self.assertGreater(J.QTR_HEX[0] - J.QTR_HEAD[0], 0.3)
        self.assertLess(J.QTR_HEX[0] - J.QTR_HEAD[0], 0.6)
        self.assertTrue(r.is_watertight)

    def test_the_cable_fits_under_the_base(self):
        self.assertGreater(J.CABLE_UNDER, J.CABLE_R + 0.5)
        self.assertGreater(J.PUCK_H - J.CABLE_UNDER, J.CABLE_R + 0.5)

    def test_the_base_stands_on_its_three_pucks_and_nothing_else(self):
        """Each puck under its foot bolt, its top at the base's underside
        and its foot on the board."""
        L = J.levels(J.SPECIMEN)
        for n, a in zip(J.PUCKS, J.FOOT_PHI):
            m = self.parts[n]
            self.assertTrue(m.is_watertight, n)
            x, y, _ = J.polar(J.FOOT_R, a)
            c = m.bounds.mean(0)
            self.assertAlmostEqual(c[0], x, delta=0.01)
            self.assertAlmostEqual(c[1], y, delta=0.01)
            self.assertAlmostEqual(m.bounds[1][2], L["base_bot"], delta=0.01)
            self.assertAlmostEqual(m.bounds[0][2], L["base_bot"] - J.PUCK_H,
                                   delta=0.01)
            # the bolt's hole is open down the axis to the insert and past
            hits = m.ray.intersects_location([[x, y, L["base_bot"] + 1]],
                                             [[0, 0, -1.0]], multiple_hits=True)[0]
            floor = max(v[2] for v in hits)
            self.assertAlmostEqual(L["base_bot"] - floor, J.INS_M3[1] + 1.5,
                                   delta=0.05)

    def test_the_cable_runs_inside_the_drive(self):
        """Along the plug's channel and down a bore in the post, not hung
        in the air: every point of its path above the base is inside the
        drive's footprint, under its lid."""
        from shapely.geometry import Point
        o, u, t = J._driver_frame()
        L = J.levels(J.SPECIMEN)
        Z = J.driver_levels(J.SPECIMEN)
        fp = J._footprint()
        for x, y, z in J.cable_path(J.SPECIMEN):
            if z <= L["base_top"]:
                continue
            d = np.array([x, y]) - o[:2]
            self.assertTrue(fp.contains(Point(d @ u[:2], d @ t[:2])), (x, y, z))
            self.assertLess(z, Z["motor_top"])

    def test_the_lid_key_holds_the_plug_down(self):
        """The key reaches down into the channel to just over the plug."""
        Z = J.driver_levels(J.SPECIMEN)
        plug_top = J._plug_z(Z) + J.MOTOR["plug"][2] / 2
        key_bottom = Z["motor_top"] - J.KEY_D
        self.assertGreater(key_bottom, plug_top)
        self.assertLess(key_bottom - plug_top, 1.0)

    def test_sightlines_see_a_blocker_when_there_is_one(self):
        """Negative control: a post standing between the phone and the
        specimen must block frames."""
        parts = dict(self.parts)
        parts["drive_cap"] = J.box((60.0, -5.0, -60.0), (70.0, 5.0, 30.0))
        self.assertGreater(J.sightlines(parts, J.SPECIMEN)["blocked"], 0)
        self.assertEqual(J.sightlines(self.parts, J.SPECIMEN)["blocked"], 0)

    def test_the_thumbscrew_comes_through_its_nut(self):
        self.assertTrue(J.thumbscrew_reach()["through"])
        from unittest import mock
        with mock.patch.object(J, "THUMB_LEN", 25.0):
            self.assertFalse(J.thumbscrew_reach()["through"])

    def test_the_phone_stands_clear_of_its_carriage(self):
        self.assertGreaterEqual(J.phone_clearance(self.parts), J.PHONE_CLEAR)


class TestAssembly(unittest.TestCase):
    """It goes together, in the order given, and the BOM is what it takes.

    Each claim is paired with the jig made wrong in the one way that
    claim is about, because a sweep that finds nothing has only proved
    something if it would have found the fault.
    """

    @classmethod
    def setUpClass(cls):
        cls.parts = J.assemble(J.SPECIMEN)
        cls.a = J.assembly_sweep(cls.parts)

    def test_every_step_reaches_its_seat(self):
        self.assertEqual([s["id"] for s in self.a["steps"] if s["fouls"]], [])
        self.assertEqual(self.a["left_on_bench"], [])

    def test_the_rod_field_plate_is_fitted_from_its_own_card(self):
        steps = {s["id"]: s for s in J.assembly_steps(self.parts)}
        self.assertIn("rod_plate", steps)
        ids = [s["id"] for s in J.assembly_steps(self.parts)]
        self.assertLess(ids.index("rod_plate"), ids.index("mount"))
        self.assertEqual(J.inserts()[J.PLATE_ITEM], 1)
        import catalog
        self.assertIn(J.PLATE_CARD, {p["id"] for p in catalog.PARTS})

    def test_the_bom_is_the_sum_of_the_steps(self):
        self.assertTrue(self.a["bom_matches"], self.a["bom_diff"])
        self.assertTrue(self.a["bodies_once"], self.a["missing_bodies"])

    def test_a_bom_line_no_step_uses_would_be_caught(self):
        from unittest import mock
        extra = dict(J.inserts(), **{"M3x8": 2})
        with mock.patch.object(J, "inserts", lambda: extra):
            a = J.assembly_sweep(self.parts, step=50.0)
        self.assertFalse(a["bom_matches"])
        self.assertEqual(a["bom_diff"], {"M3x8": (0, 2)})

    def test_bearings_left_in_would_block_the_ring(self):
        """Negative control: the eccentrics not turned out. This is the
        fault the sweep first found, with the old 3 mm flanks and one
        eccentric: the ring had no way past the bearings."""
        from unittest import mock
        real = J.bearing_centres
        inner = J.sleeves_in_place(J.SPECIMEN)
        with mock.patch.object(J, "bearing_centres",
                               lambda retracted=False: real(False)), \
             mock.patch.object(J, "sleeves_in_place",
                               lambda specimen=J.SPECIMEN, retracted=False: inner):
            a = J.assembly_sweep(self.parts, step=2.0)
        bad = {s["id"] for s in a["steps"] if s["fouls"]}
        self.assertIn("rotor", bad)

    def test_a_nut_trap_with_no_mouth_would_be_caught(self):
        """Negative control: the 20.0.0 saddle. Its trap opened into the
        arm's wedge, which sealed it; the nut slid its 20 mm inside the
        34 mm void and the sweep, asking only what it hit, passed it.
        Brett found it on the printed part."""
        h0, (nw, nt) = J.PLATE_H[0], J.NUT
        s = J.saddle()
        s.apply_transform(np.linalg.inv(J.M_ARC))
        void = J.box((J.CLAMP_R - nw / 2, -30.0, h0 + 3.2),
                     (J.CLAMP_R + nw / 2, nw / 2, h0 + 3.2 + nt))
        mouth = J.box((J.CLAMP_R - nw / 2, -nw / 2, h0 + 3.2),
                      (J.CLAMP_R + nw / 2, 40.0, h0 + 3.2 + nt))
        sealed = J.cut(J.union([s, J.cut(mouth, [void])]), [void])
        sealed.apply_transform(J.M_ARC)
        a = J.assembly_sweep(dict(self.parts, saddle=sealed), step=2.0)
        bad = {s["id"] for s in a["steps"] if s["fouls"]}
        self.assertIn("nut", bad)

    def test_turned_out_each_bearing_clears_the_ring_by_the_face_gap(self):
        clear = min(np.linalg.norm(c) for c in J.bearing_centres(True)) \
            - J.BRG_R - J.RING_RO
        self.assertGreaterEqual(clear, 0.4)

    def test_the_eccentrics_absorb_the_big_parts_shrinking_differently(self):
        """Turned fully in, each bearing can still go PRELOAD past the
        race. The ring and the base are both 240 mm across; this margin is
        what lets the ring come out up to 0.5% smaller than the base and
        the bearings still reach it."""
        s_ring, s_base = 0.005, 0.0
        reach = (J.RACE_R * (1 - s_ring) + J.BRG_R) \
            - (J.TOWER_PITCH * (1 - s_base) - J.ECC)
        self.assertGreater(reach, 0.0)
        # the sleeve keeps a real wall between its bolt and its bearing
        self.assertGreaterEqual(J.SLEEVE_R - J.ECC - J.AXLE_R, 0.7)

    def test_every_axle_is_on_its_towers_insert(self):
        """The eccentric's bore was 1 mm off its tower's insert, so its
        axle could not reach the thread. The bore is the tower's axis."""
        for n, a in zip(J.SLEEVES, J.TOWER_PHI):
            bx, by = J._sleeve_bore(self.parts[n])
            T = J.polar(J.TOWER_PITCH, a)[:2]
            self.assertLess(np.hypot(bx - T[0], by - T[1]), 0.05, n)

    def test_every_fit_is_measured_and_as_intended(self):
        rows = J.fits(self.parts)
        self.assertTrue(all(r["hole"] is not None and r["shaft"] is not None
                            for r in rows), [r["name"] for r in rows
                                             if r["hole"] is None
                                             or r["shaft"] is None])
        self.assertEqual([r["name"] for r in rows if not r["ok"]], [])

    def test_the_grading_is_the_shops_table(self):
        self.assertEqual(J.fit_class(-0.1), "interference")
        self.assertEqual(J.fit_class(0.10), "press")
        self.assertEqual(J.fit_class(0.30), "slip")
        self.assertEqual(J.fit_class(0.40), "running")
        self.assertEqual(J.fit_class(0.1, "printed shaft in steel bore"),
                         "press")

    def test_a_pin_hole_drawn_loose_would_be_caught(self):
        """Negative control: the pin's hole drawn 0.3 over the pin grades
        as a slip, which would let the pin fall out of the crank."""
        with mock.patch.object(J, "PIN_PRESS", 0.30):
            d = J.driver(J.SPECIMEN)
        parts = dict(self.parts, driver=d)
        row = next(r for r in J.fits(parts) if r["name"] == "Geneva pin in the crank")
        self.assertNotEqual(row["got"], "press")
        self.assertFalse(row["ok"])

    def test_nothing_depends_on_a_press_into_the_print_being_exact(self):
        """The D-shaft slides into a clearance bore and a set screw holds
        it; the pin's hole is drawn under the pin so it is tight in every
        print. PETG yields rather than cracks, and the crank has 2.5 mm of
        wall beside the pin."""
        rows = {r["name"]: r for r in J.fits(self.parts)}
        for n in ("Gearmotor's D-shaft in the crank, round",
                  "Gearmotor's D-shaft in the crank, flat"):
            self.assertGreaterEqual(rows[n]["allow"], 0.4, n)
        self.assertLess(rows["Geneva pin in the crank"]["allow"], 0.0)
        self.assertGreaterEqual(J.CRANK_R - J.GENEVA_A - J.PIN_R, 2.5)
        bom = J.inserts()
        self.assertEqual(bom[J.SETSCREW_ITEM], 1)
        self.assertEqual(bom[J.NUT_ITEM], 1)

    def test_a_jam_stays_under_the_gearbox_limit(self):
        """Pololu: 2 kg.cm instantaneous for the 298:1. The series resistor
        holds a stall under it, whatever the firmware does."""
        r_total = 6.0 / 1.6 + J.MOTOR_R + 0.36 + 0.32 + 0.15
        i = 5.0 / r_total
        torque_kgcm = 4.0 * (i - 0.1) / 1.5
        self.assertLess(torque_kgcm, 1.5)
        self.assertLess(i, 1.0)            # the JST SH contacts' rating


class TestFasteners(unittest.TestCase):
    """Every bolt the BOM names must fill its insert and not bottom out.

    The list used to be typed. It said M4x16 for all eight M4 bolts, and
    at the arc bar -- which crosses 12 mm before it reaches a 7 mm insert
    -- that is four threads holding the arc and the whole carriage
    through a 90 degree sweep.
    """

    def test_every_joint_gets_a_length_that_fills_its_insert(self):
        for name, crosses, ins, relief, n, gauge in J.JOINTS:
            L = J.bolt_len(crosses, ins, relief)
            self.assertIsNotNone(L, f"{name}: no stock length fits")
            if relief is None:
                # blind: ends inside the insert, clear of the melt under it
                self.assertGreaterEqual(L - crosses, J.ENGAGE_MIN,
                                        f"{name}: {gauge}x{L} too little thread")
                self.assertLessEqual(L - crosses, ins,
                                     f"{name}: {gauge}x{L} reaches past the insert")
                continue
            self.assertGreaterEqual(L - crosses, ins,
                                    f"{name}: {gauge}x{L} leaves threads unused")
            self.assertLessEqual(L - crosses, ins + relief,
                                 f"{name}: {gauge}x{L} bottoms out")

    def test_the_rotor_really_has_the_relief_the_table_claims(self):
        """The table is only right if the part agrees with it."""
        r = J.rotor(J.SPECIMEN)
        floor = J.levels(J.SPECIMEN)["pad_top"] - J.PAD_SLOT_D
        claimed = J.INS_M3[1] + 4.0
        for x in J.BOLTS_X:
            on = r.ray.intersects_location([[x, J.Y_ARC, floor + 0.5]],
                                           [[0, 0, -1.0]], multiple_hits=True)[0]
            self.assertTrue(len(on), f"no hole at x={x}")
            self.assertAlmostEqual(floor - max(v[2] for v in on), claimed,
                                   delta=0.2, msg=f"hole depth at x={x}")
        # beside the axis there must be solid pad, or the probe proves nothing
        beside = r.ray.intersects_location(
            [[J.BOLTS_X[0] + 3.5, J.Y_ARC, floor + 0.5]],
            [[0, 0, -1.0]], multiple_hits=True)[0]
        self.assertAlmostEqual(floor - max(v[2] for v in beside), 0.0, delta=0.2)


class TestOneCameraNoBallast(unittest.TestCase):
    """The jig carries a phone and nothing else, and has no ballast.

    Those two facts are the same fact. The ballast at both ends was sized
    against a 1.34 kg Sony a1 whose tripod socket sat 320 mm out; with
    0.25 kg of phone at 167 it offsets a moment the tongue barely feels.
    If a heavy camera is ever added back, the balance test below is what
    should fail first -- not a printed part.
    """

    @classmethod
    def setUpClass(cls):
        cls.parts = J.assemble(J.SPECIMEN)

    def test_the_phone_is_the_only_camera(self):
        self.assertEqual(list(J.CAMERAS), ["iphone"])
        self.assertEqual([k for k, _ in J.camera_cases()], ["iphone"] * 2)

    def test_no_lens_is_offered_that_no_camera_has(self):
        have = {l["id"] for c in J.CAMERAS.values() for l in c["lenses"]}
        self.assertEqual({l["id"] for l in J.LENSES}, have)

    def test_nothing_is_left_of_the_ballast(self):
        for gone in ("BALLAST_PHI", "BALLAST_R", "BALLAST_D",
                     "BALLAST_DEPTH", "CB_POCKET"):
            self.assertFalse(hasattr(J, gone), f"{gone} is still here")
        self.assertNotIn("ballast", json.dumps(J.inserts()).lower())

    def test_nothing_is_left_of_the_detents_or_the_pawl(self):
        for gone in ("DETENTS", "DETENT_R", "PAWL_PHI", "PAWL_BLOCK", "pawl",
                     "count_detents"):
            self.assertFalse(hasattr(J, gone), f"{gone} is still here")
        self.assertNotIn("silicone", json.dumps(J.inserts()).lower())

    def test_the_carriage_balances_well_enough_to_need_none(self):
        b = J.carriage_moment(self.parts)
        self.assertLessEqual(b["tongue_couple_n"], J.TONGUE_COUPLE_N)

    def test_and_a_heavy_camera_would_say_so(self):
        """Negative control: the gate has to be able to ask for ballast.

        Without this the test above passes on a jig that could not hold a
        camera at all, and the reasoning for removing the ballast would
        be recorded as a number nothing could ever contradict.
        """
        # the a1 as it actually sat: 1.34 kg with its mass at u = 276,
        # not the phone's 250 g at 167. Mass alone is not the test --
        # 1.34 kg at the phone's position is only 14 N on the tongue,
        # which is how the first version of this control passed while
        # proving nothing.
        heavy = J.carriage_moment(self.parts, cam_g=1340.0, cam_u=275.7)
        self.assertGreater(heavy["tongue_couple_n"], J.TONGUE_COUPLE_N)
        near = J.carriage_moment(self.parts, cam_g=1340.0, cam_u=166.5)
        self.assertLess(near["tongue_couple_n"], J.TONGUE_COUPLE_N)

    def test_the_platform_is_only_as_long_as_the_phone_needs(self):
        """The receiver, at either end of its travel, must sit on deck."""
        lo, hi = J.CHANNEL[0], J.CHANNEL[1]
        half = J.RECV[0] / 2.0
        self.assertGreaterEqual(lo - half, J.PLATFORM_U[0] - 1e-6)
        self.assertLessEqual(hi + half, J.PLATFORM_U[1] + 1e-6)
        # and no longer: deck past the receiver's reach is carried for nothing
        self.assertLess(J.PLATFORM_U[1] - (hi + half), 2.0)


class TestSpecimenMount(unittest.TestCase):
    """The rod field plate on the platform, held by a printed screw and
    a wing nut. The specimen stands on rods in that plate, so what these
    hold down is that it goes together, that it stays together, and that
    none of it can reach into a frame.
    """

    @classmethod
    def setUpClass(cls):
        import gen_gazebo as G
        cls.G = G
        cls.L = J.levels(J.SPECIMEN)
        cls.stator = J.stator(J.SPECIMEN)
        cls.screw = J.mount_screw()
        cls.nut = J.mount_wing_nut()
        cls.plate = G.build("gz_rfj")["gazebo_rfj"]

    def _seated(self):
        """The three parts put where they sit in use."""
        screw = self.screw.copy()
        screw.apply_translation([0, 0, self.L["base_top"] - J.BASE_T])
        plate = self.plate.copy()
        plate.apply_translation([0, 0, self.L["plat"]])
        nut = self.nut.copy()
        nut.apply_translation([0, 0, self.L["plat"] + self.G.FIELD_T])
        return screw, plate, nut

    def test_screw_and_nut_are_printable_solids(self):
        for n, m in (("screw", self.screw), ("wing nut", self.nut)):
            self.assertTrue(m.is_watertight, n)
            self.assertGreater(m.volume, 0.0, n)

    def test_the_screw_is_long_enough_to_catch_the_nut(self):
        screw, _, nut = self._seated()
        self.assertGreater(screw.bounds[1][2], nut.bounds[1][2],
                           "screw tip must stand past the top of the nut")

    def test_the_screw_passes_the_pedestal_without_touching(self):
        screw, _, _ = self._seated()
        self.assertEqual(
            float(self.stator.intersection(screw, engine="manifold").volume),
            0.0)

    def test_a_fatter_screw_would_not_pass(self):
        """Negative control: the bore is a fit, not a hole in open air."""
        fat = self.screw.copy()
        fat.apply_scale([1.3, 1.3, 1.0])
        fat.apply_translation([0, 0, self.L["base_top"] - J.BASE_T])
        self.assertGreater(
            float(self.stator.intersection(fat, engine="manifold").volume),
            1.0)

    def test_the_plate_rests_on_the_platform_and_does_not_sink_into_it(self):
        _, plate, _ = self._seated()
        self.assertLess(
            float(self.stator.intersection(plate, engine="manifold").volume),
            1.0)

    def test_the_probe_can_see_the_plate_pressed_in(self):
        """Negative control for the test above."""
        _, plate, _ = self._seated()
        plate.apply_translation([0, 0, -0.3])
        self.assertGreater(
            float(self.stator.intersection(plate, engine="manifold").volume),
            50.0)

    def test_the_head_cannot_turn_in_its_pocket(self):
        """A hex head in a hex pocket is what makes the screw captive, so
        the wing nut can be tightened without holding anything below.

        Asked as a behaviour rather than by counting the head's corners:
        seated it is free, and turned half a flat it jams. Counting
        vertices would pass just as well on a head that fitted a round
        hole, which is the thing this has to rule out.
        """
        screw, _, _ = self._seated()
        self.assertEqual(
            float(self.stator.intersection(screw, engine="manifold").volume),
            0.0, "seated, it should turn freely enough to drop in")
        turned = self.screw.copy()
        turned.apply_transform(J.rot(30.0, [0, 0, 1]))     # half a hex flat
        turned.apply_translation([0, 0, self.L["base_top"] - J.BASE_T])
        self.assertGreater(
            float(self.stator.intersection(turned, engine="manifold").volume),
            1.0, "turned 30 degrees the head must foul its pocket")

    def test_the_mount_hole_is_the_jigs_number_not_a_copy(self):
        self.assertEqual(self.G.J.MOUNT_BORE_R, J.MOUNT_BORE_R)

    def test_every_one_of_the_56_sockets_survives_the_mount_hole(self):
        P = np.array(self.G.field_holes(self.G.BY_ID["gz_rfj"]))
        self.assertEqual(len(P), 56)
        r = np.hypot(P[:, 0], P[:, 1])
        reach = J.MOUNT_BORE_R + self.G.JIG_BORE_CHAMFER
        self.assertGreater(r.min() - self.G.ROD_FIELD / 2.0 - reach, 1.0)

    def test_the_nut_cannot_reach_into_a_frame(self):
        """Nothing may rise above the plane the specimen rests on. The
        rods lift the tooth; the nut has to stay under the shortest of
        them, or it occludes the specimen from every camera above it."""
        rod_proud = ROD_NOMINAL - 7.0            # Ø1 carbon, cut and seated
        self.assertLess(self.nut.extents[2], rod_proud)

    def _nut_overlap(self, z, extra_deg=0.0):
        T = J.mount_thread()
        n = self.nut.copy()
        n.apply_transform(J.rot(360.0 * z / T.lead + extra_deg, [0, 0, 1]))
        n.apply_translation([0, 0, z])
        return float(self.screw.intersection(n, engine="manifold").volume)

    def test_the_wing_nut_runs_the_length_of_the_shank(self):
        """Turned with the helix it must not jam anywhere."""
        for z in np.arange(10.0, 60.0, 4.0):
            self.assertLess(self._nut_overlap(z), 1.0, f"jams at z={z}")

    def test_a_nut_out_of_phase_jams(self):
        """Negative control, and it has to be a real error to be one.

        30 degrees off is 0.22 mm of axial error against 0.30 mm of
        radial clearance, so it still fits -- that is the thread working,
        not the probe failing. 60 degrees is 0.44 mm and does jam, which
        is what makes the test above mean anything.
        """
        near = self._nut_overlap(30.0, 30.0)
        off = self._nut_overlap(30.0, 60.0)
        far = self._nut_overlap(30.0, 180.0)
        self.assertLess(near, 1.0)
        self.assertGreater(off, 1.0)
        # half a lead out must be far worse than a sixth of one. Stated as
        # a ratio, not a millimetre figure: the absolute overlap scales
        # with the thread, and a fixed threshold quietly became a test of
        # the thread's diameter when it went from Ø8 to Ø6.
        self.assertGreater(far, 3.0 * off)

    def test_the_dial_still_reaches_the_tooth_this_jig_was_built_for(self):
        """The mount lifts the specimen before the specimen starts, so
        the focal-height dial has to cover the lift as well as the tooth.
        BigMeherrin's centroid is 57 mm above its own base; on the long
        rods that is 94.5 mm above the platform. At the old 70 mm stop
        the one tooth this jig exists for could not be brought to the
        focal point, and nothing said so.
        """
        lift = self.G.FIELD_T + (ROD_NOMINAL - 7.0)   # plate + rods proud
        self.assertLessEqual(lift + 57.0, J.SPECIMEN_RANGE[1])

    def test_every_height_the_dial_offers_actually_builds(self):
        """A dial is a promise that every value of it works."""
        for sp in (J.SPECIMEN_RANGE[0], J.SPECIMEN_RANGE[1]):
            parts = J.assemble(sp)
            self.assertTrue(all(m.is_watertight for m in parts.values()), sp)
            self.assertGreater(J.levels(sp)["pad_t"], 0.0, sp)

    def test_the_nut_covers_no_socket(self):
        _, _, nut = self._seated()
        P = np.array(self.G.field_holes(self.G.BY_ID["gz_rfj"]))
        z = self.L["plat"] + self.G.FIELD_T + self.nut.extents[2] / 2.0
        pts = np.column_stack([P, np.full(len(P), z)])
        self.assertEqual(int(nut.contains(pts).sum()), 0)


if __name__ == "__main__":
    unittest.main()
