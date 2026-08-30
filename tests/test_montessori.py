"""Unit tests for the Montessori companion parts.

The thread is cast from the designer's nut, so these tests need the source
model; models/ is untracked, so they skip cleanly without it.
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gen_montessori as GM  # noqa: E402

HAVE_SRC = os.path.exists(GM.SRC)


class TestBedPlacement(unittest.TestCase):
    @unittest.skipUnless(
        os.path.exists(os.path.expanduser(
            "~/Code/My3DPrints/models/custom/montessori-double-nut.3mf")),
        "generated file not present")
    def test_generated_parts_stand_on_the_bed(self):
        import trimesh
        base = os.path.expanduser("~/Code/My3DPrints/models/custom")
        for fn in ("montessori-double-nut.3mf", "montessori-plate-2x3.3mf"):
            p = os.path.join(base, fn)
            if not os.path.exists(p):
                continue
            sc = trimesh.load(p, force="scene")
            self.assertAlmostEqual(float(sc.bounds[0][2]), 0.0, delta=0.01,
                                   msg=f"{fn} does not sit on the bed")


class TestExportedFilesAreCleanByConstruction(unittest.TestCase):
    """No quantise-and-dedupe pass: the geometry has to come out manifold.

    Both generators used to repair the mesh on the way out, and both repairs
    were hiding a real defect — a socket lip chamfered past a knife edge,
    and seat bar caps grazing the ring they should sit inside. The repair is
    gone; these guard the design instead.
    """

    BASE = os.path.expanduser("~/Code/My3DPrints/models/custom")

    def _check(self, fn):
        import meshcheck
        p = os.path.join(self.BASE, fn)
        if not os.path.exists(p):
            self.skipTest(f"{fn} not generated")
        self.assertEqual(meshcheck.export_defects(p), {})

    def test_plate_file_is_clean(self):
        self._check("montessori-plate-2x3.3mf")

    def test_double_nut_file_is_clean(self):
        self._check("montessori-double-nut.3mf")

    def test_dice_orb_file_is_clean(self):
        self._check("dice-cage.3mf")

    def test_socket_lip_keeps_a_flat_land(self):
        # the two chamfers approach the top face from opposite sides; if they
        # meet, the rim is a knife edge and the mesh slivers along it
        land = (GM.BOSS_R - GM.BOSS_CHAM) - (GM.BORE_ROOT + GM.CHAMFER)
        self.assertGreaterEqual(land, GM.LAND_MIN)

    def test_a_knife_edged_lip_is_refused(self):
        if not HAVE_SRC:
            self.skipTest("source model not present")
        nut, _ = GM.source_parts()
        old = GM.BOSS_CHAM
        try:
            GM.BOSS_CHAM = 5.0          # chamfers now cross
            with self.assertRaisesRegex(ValueError, "knife"):
                GM.build_plate(nut)
        finally:
            GM.BOSS_CHAM = old


class TestHex(unittest.TestCase):
    def test_hexagon_circumradius(self):
        h = GM.hexagon(10.0)
        xy = np.array(h.exterior.coords)[:-1]
        self.assertEqual(len(xy), 6)
        self.assertTrue(np.allclose(np.hypot(xy[:, 0], xy[:, 1]), 10.0))


@unittest.skipUnless(HAVE_SRC, "source Montessori model not present")
class TestThread(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nut, cls.shank = GM.source_parts()

    def test_source_nut_repairs_to_watertight(self):
        self.assertTrue(self.nut.is_watertight)

    def test_plug_is_a_solid_cast_of_the_bore(self):
        plug = GM.thread_plug(self.nut, 20.0)
        self.assertTrue(plug.is_watertight)
        self.assertAlmostEqual(plug.bounds[1][2] - plug.bounds[0][2],
                               20.0, delta=0.2)
        r = np.hypot(plug.vertices[:, 0], plug.vertices[:, 1])
        # the cast reaches the female thread's root, not past it
        self.assertLess(r.max(), GM.BORE_ROOT + 0.2)

    def test_one_lead_is_the_axial_period(self):
        # translating the cast by one lead must map it onto itself: compare
        # the shifted copy's overlap with the original in the shared band
        plug = GM.thread_plug(self.nut, 24.0)
        band = plug.slice_plane([0, 0, -12 + GM.LEAD], [0, 0, 1], cap=True)
        shifted = plug.copy()
        shifted.apply_translation([0, 0, GM.LEAD])
        inter = band.intersection(shifted, engine="manifold")
        self.assertGreater(inter.volume / band.volume, 0.97)

    def test_a_wrong_lead_does_not_map_onto_itself(self):
        plug = GM.thread_plug(self.nut, 24.0)
        band = plug.slice_plane([0, 0, -12 + GM.LEAD], [0, 0, 1], cap=True)
        shifted = plug.copy()
        shifted.apply_translation([0, 0, GM.LEAD * 0.5])
        inter = band.intersection(shifted, engine="manifold")
        self.assertLess(inter.volume / band.volume, 0.90)


@unittest.skipUnless(HAVE_SRC, "source Montessori model not present")
class TestScrewVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nut, cls.shank = GM.source_parts()
        cls.good = GM.build_double_nut(cls.nut, 20.0)

    def test_real_bolt_screws_into_the_generated_thread(self):
        lead, windows = GM.screw_test(self.good, self.shank, [-3.0, 0.0, 3.0])
        self.assertIsNotNone(lead, "the designer's bolt does not fit")
        self.assertAlmostEqual(lead, GM.LEAD, delta=0.6)
        for _, _, width in windows:
            self.assertGreater(width, 6)      # a real clearance window

    def test_the_check_rejects_a_mis_stacked_thread(self):
        bad = GM.build_double_nut(self.nut, 20.0, lead=GM.LEAD * 1.18)
        lead, _ = GM.screw_test(bad, self.shank, [-3.0, 0.0, 3.0])
        if lead is not None:
            self.assertGreater(abs(lead - GM.LEAD), 0.6,
                               "a wrong lead passed the screw test")

    def test_double_nut_is_one_watertight_body(self):
        # watertight as built, with no repair pass: an unconditional
        # merge_vertices welds the end chamfer's near-coincident vertices
        # at the hex corners and breaks a solid that was already sound
        self.assertTrue(self.good.is_watertight)
        self.assertEqual(len(self.good.split(only_watertight=False)), 1)

    def test_hex_ends_are_chamfered_like_the_original(self):
        import numpy as np
        v = self.good.vertices
        r = np.hypot(v[:, 0], v[:, 1])
        z0 = v[:, 2].min()
        face = (np.abs(v[:, 2] - z0) < 0.05) & (r > 21)
        self.assertAlmostEqual(float(r[face].max()), GM.FACE_R, delta=0.1)
        corners = v[r > GM.HEX_CR - 0.25]
        self.assertAlmostEqual(float(corners[:, 2].min() - z0), GM.CHAM_H,
                               delta=0.15)


if __name__ == "__main__":
    unittest.main()


class TestWrench(unittest.TestCase):
    """The wrench is sized off the same hex the nut and bolt heads share."""

    @classmethod
    def setUpClass(cls):
        import gen_wrench
        cls.W = gen_wrench
        cls.prof, cls.rep, cls.geo = gen_wrench.build()

    def test_one_size_drives_the_whole_set(self):
        # nut 49.68, bolt heads 49.78 — the wrench takes the larger
        self.assertGreaterEqual(self.W.AF, 49.78 - 1e-6)

    def test_profile_is_one_piece_with_one_bore(self):
        self.assertEqual(self.prof.geom_type, "Polygon")
        self.assertEqual(len(self.prof.interiors), 1)

    def test_thinner_than_the_hex_flat_band(self):
        # the heads chamfer above and below, leaving ~18 mm of true flat
        self.assertLess(self.rep["thick_mm"], 17.5)

    def test_jaw_arms_carry_a_childs_torque(self):
        self.assertLess(self.rep["jaw_stress_MPa"], self.W.PLA_YIELD / 2)
        self.assertGreater(self.rep["safety"], 2.0)

    def test_thin_arms_are_refused(self):
        # either gate may catch it first — the tapered arm can fall under
        # the wall minimum before the bending number goes bad — and both
        # are a refusal to emit a wrench that would snap
        with self.assertRaisesRegex(ValueError, "stress|thin"):
            self.W.build(jaw_arm=8.0)

    def test_head_keeps_material_behind_the_throat(self):
        self.assertGreaterEqual(self.rep["behind_throat_mm"], self.W.MIN_WALL)

    def test_jaw_grips_past_the_nuts_centre(self):
        self.assertGreater(self.rep["grip_past_nut_mm"], 8.0)

    def test_it_fits_the_bed(self):
        self.assertLess(self.rep["length_mm"], 246.0)

    @unittest.skipUnless(HAVE_SRC, "source Montessori model not present")
    def test_the_designer_s_nut_seats_in_both_ends(self):
        import trimesh
        m = trimesh.creation.extrude_polygon(self.prof, self.rep["thick_mm"])
        nut, _ = GM.source_parts()
        nut = nut.copy()
        nut.apply_translation([0, 0, -nut.bounds[0][2]])
        for tag, at in (("box", (0.0, 0.0)), ("jaw", self.geo["seat"])):
            fit = self.W.fit_test(m, nut, at, self.rep["thick_mm"], sweep=2.0)
            self.assertIsNotNone(fit, f"nut will not enter the {tag} end")
            gap, _, free = fit
            self.assertGreaterEqual(gap, self.W.FIT_MIN, tag)
            self.assertLessEqual(gap, self.W.FIT_MAX, tag)
            self.assertGreater(free, 0, tag)


class TestBoreEntryIsPrintable(unittest.TestCase):
    """The face that prints downward may not be a ceiling.

    The bore entry was cut with `cone(radius=BORE_ROOT + CHAMFER,
    height=CHAMFER)` — 20 mm of radius over 2 mm of height, a flank 9 across
    for every 1 up. It reads like a 2.2 mm chamfer and is an 84 degree
    overhang: a shelf built inward over open air at roughly 1.8 mm of
    unsupported step per layer, which drooped into the hole and came off the
    printer as loose strands across the opening.
    """

    @classmethod
    def setUpClass(cls):
        import trimesh
        import catalog
        cls.trimesh = trimesh
        path, _ = catalog.ensure(catalog.find("mont_double"))
        cls.m = trimesh.util.concatenate(
            list(trimesh.load(path, force="scene").geometry.values()))

    def _downward(self, zmax=9.0, rmax=20.5):
        import numpy as np
        m = self.m
        z0 = m.bounds[0][2]
        c, n, a = m.triangles_center, m.face_normals, m.area_faces
        sel = ((c[:, 2] - z0 < zmax) & (c[:, 2] - z0 > 0.05)
               & (np.hypot(c[:, 0], c[:, 1]) < rmax) & (n[:, 2] < -0.05))
        ang = np.degrees(np.arcsin(np.clip(-n[sel, 2], 0, 1)))
        return ang, a[sel]

    def test_the_entry_has_no_unsupported_ceiling(self):
        import numpy as np
        ang, area = self._downward()
        severe = float(area[ang >= 60].sum())
        self.assertLess(severe, 60.0,
                        f"{severe:.0f} mm2 of the bore entry overhangs past "
                        f"60 deg; it was 557 mm2 when it strung")

    def test_most_of_the_entry_is_comfortably_printable(self):
        ang, area = self._downward()
        ok = float(area[ang < 45].sum())
        self.assertGreater(ok / max(float(area.sum()), 1e-9), 0.7)

    def test_the_chamfer_reaches_the_thread_crest(self):
        # relieving only the root leaves the crest to appear in one slice,
        # which is a 3 mm shelf however good the chamfer above it is
        import gen_montessori as GM
        nut, _ = GM.source_parts()
        # measured on the plug that cuts the bore, not on the donor nut:
        # the nut's own bore sits half a millimetre wide of the surface the
        # part ends up with, and a lead-in aimed there leaves that much
        # thread behind
        crest = GM.crest_radius(GM.thread_plug(nut, 48.0))
        self.assertLess(crest, GM.BORE_ROOT)
        c = GM.entry_chamfer(0.0, False, to_r=crest)
        rise = float(c.bounds[1][2] - c.bounds[0][2])
        flare = (GM.BORE_ROOT + GM.CHAMFER) - crest
        self.assertAlmostEqual(rise, flare, delta=0.15,
                               msg="the lead-in is not at 45 degrees")

    def test_a_chamfer_solid_is_a_volume_either_way_up(self):
        # mirroring the profile reverses its winding; the boolean refuses a
        # solid of negative volume
        import gen_montessori as GM
        for up in (True, False):
            c = GM.entry_chamfer(21.0 if up else -21.0, up)
            self.assertTrue(c.is_volume, f"opens_up={up}")
            self.assertGreater(c.volume, 0)
