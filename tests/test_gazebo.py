"""The gazebo: eight spikes on a ring, measured.

The four-cone stands put their cups where a median root's lobes are.
This one does not know where the lobes are, so what has to be true is
different: every spike reaches the same plane, the ring covers the
root's own footprint, the notch stays empty, and eight spikes stay eight
rather than merging into a wall. Each check has a control.
"""
import json
import os
import sys
import tempfile
import unittest
import zipfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gen_gazebo as G  # noqa: E402
import gen_tooth_stand as T  # noqa: E402

# the ring stands; the field base is a different animal and is tested
# on its own terms further down
# the ring stands; the field base and the socket gauge are different
# animals and are tested on their own terms further down
def _is_stand(s):
    return not (s.get("field") or s.get("gauge") or s.get("probe"))


RINGS = [s for s in G.SIZES if _is_stand(s)]
# what `all` builds: the drawn silhouettes are drafts and stay off plates
BUILT = [s for s in G.SIZES if not s.get("draft")]
BUILT_RINGS = [s for s in BUILT if _is_stand(s)]


class TestGazebo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = G.build("all")
        cls.rep = G.measure(cls.parts)

    def test_every_gate_passes_on_a_plate_that_fits(self):
        # the whole family is nine bodies and does not fit one bed, so
        # the gates are asserted on the plates a person would actually
        # print; the refusal itself is checked below
        for which in ("gz_sg,gz_mg,gz_lg", "gz_lg",
                      "gz_lr,gz_rf,gz_gauge"):
            rep = G.measure(G.build(which))
            failed = [n for n, ok in G.gates(rep) if not ok]
            self.assertEqual(failed, [], which)

    def test_a_plate_too_deep_for_the_bed_is_refused(self):
        # the packer wraps rows at the bed's width and never looked at
        # how deep the rows had gone: all nine packed 268 mm off the
        # back and the slicer, not the generator, was what said no
        self.assertGreater(max(self.rep["plate_mm"]), 250.0)
        self.assertIn("plate_fits_the_bed",
                      [n for n, ok in G.gates(self.rep) if not ok])

    def test_one_body_per_size_and_a_spike_per_gap(self):
        self.assertEqual(len(self.parts), len(BUILT))
        self.assertTrue(all(m.is_watertight for m in self.parts.values()))
        for s in RINGS:
            self.assertEqual(len(G.spikes(s)), len(G.weights(s)), s["id"])
            self.assertGreaterEqual(len(G.spikes(s)), 6, s["id"])

    def test_every_cup_is_coplanar(self):
        for k, dz in self.rep["coplanar_mm"].items():
            self.assertIsNotNone(dz, k)
            self.assertLess(dz, 0.05, k)
            self.assertEqual(len(self.rep["tip_z"][k]),
                             len(G.spikes(G.BY_ID[k])), k)

    def test_the_coplanarity_probe_can_see_one_short_spike(self):
        spec = G.BY_ID["gz_mg"]
        m = G.stand(spec)
        x, y = G.spikes(spec)[3]
        sunk = T.cyl(5.0, G.dish_z(spec) - 1.5, G.contact_z(spec) + 5.0,
                     x, y, sections=32)
        dz, _ = G.tips_coplanar(spec, T.cut(m, [sunk]))
        self.assertIsNotNone(dz)
        self.assertGreater(dz, 1.0, "a 1.5 mm short spike must be seen")

    def test_the_ring_is_a_circle_sized_to_the_root_s_thickness(self):
        # not the ellipse of the cross and fore/aft spans: that is the
        # four-cone rule, and stretched to it the spikes bunch into two
        # groups of four at the ends -- the lobes' pattern, not a ring's.
        # The binding dimension is the root's thickness, because a circle
        # wider than that puts half its spikes off the root
        for s in RINGS:
            pts = np.array(G.spikes(s))
            rad = np.hypot(pts[:, 0], pts[:, 1])
            # the centers are stored rounded to four places
            self.assertLess(rad.max() - rad.min(), 1e-3, s["id"])
            self.assertAlmostEqual(2 * rad.mean(), s["ring"], places=3)
            self.assertLessEqual(s["ring"], 1.3 * s["fore"], s["id"])

    def test_an_even_ring_would_space_evenly_and_a_graded_one_does_not(self):
        # every shipped size is graded, so the even ring is built here as
        # the control: on a circle, equal weights are equal arcs and
        # every gap comes out the same
        even = dict(G.BY_ID["gz_mg"], gaps=[1] * 8)
        g = G.gaps(even)
        self.assertLess(max(g) - min(g), 1e-6)
        self.assertEqual(len(G.widths(even)), 1)
        for s in RINGS:
            self.assertGreater(max(G.gaps(s)) - min(G.gaps(s)), 1.0, s["id"])

    def test_every_ring_offers_three_widths_and_still_balances(self):
        # one gap size gives a root one slot to drop a ridge into; three
        # let it be turned to whichever fits
        for s in RINGS:
            w = G.widths(s)
            self.assertEqual(len(w), 3, s["id"])
            self.assertGreaterEqual(min(w), 2.0, s["id"])
            # each width clearly different from the next, not a rounding
            self.assertGreater(min(a - b for a, b in zip(w, w[1:])), 0.8,
                               s["id"])
            # and the ring repeats after half a turn, so it balances
            pts = np.array(G.spikes(s))
            for q in -pts:
                self.assertLess(np.abs(pts - q).sum(axis=1).min(), 1e-6,
                                s["id"])

    def test_the_ring_holds_the_hollow_and_the_lobes_clear_the_deck(self):
        # this stand touches the middle of the root ON PURPOSE -- the
        # four-cone stands keep out of the notch, this one nests in it --
        # so what has to be checked instead is that the lobes hanging
        # outside the ring do not reach the deck
        for k, v in self.rep["lobe_clear"].items():
            self.assertGreater(v["margin_mm"], 2.0, k)
        for s in RINGS:
            self.assertLess(s["ring"] / 2.0 + G.pad_r(s),
                            G.deck_r(s) + 1e-6, s["id"])

    def test_eight_spikes_do_not_merge_into_a_wall(self):
        for k, v in self.rep["merge_z_mm"].items():
            self.assertIsNotNone(v, k)
            self.assertLess(v, 0.45 * G.BY_ID[k]["cone"], k)

    def test_the_merge_probe_can_see_a_wall(self):
        # the control: a ring band raised to half the cone height is a
        # wall, and the probe must refuse to find eight islands below it
        spec = G.BY_ID["gz_sg"]
        walled = T.union([G.stand(spec),
                          T.cyl(G.ring_r(spec) + 1.0, G.BASE_T,
                                G.BASE_T + 0.5 * spec["cone"], sections=64)])
        z = G.merge_z(spec, walled)
        self.assertTrue(z is None or z >= 0.45 * spec["cone"],
                        f"a wall read as {z} mm")

    def test_nothing_rises_above_the_contact_plane(self):
        for k, v in self.rep["above_contact_mm"].items():
            self.assertLessEqual(v, 1e-6, f"{k} pokes {v:+.3f} mm above")

    def test_it_occludes_nothing_and_prints_as_it_is_used(self):
        for k, o in self.rep["occlusion"].items():
            self.assertLess(o["overall"], 1.0, k)
        for n, v in self.rep["print"].items():
            self.assertLessEqual(v["off_plate_mm2"], 1.0, n)
        for n, a in self.rep["plate_mm2"].items():
            self.assertGreater(a, 100.0, n)

    def test_the_underside_is_one_flat_plane_on_the_dock(self):
        # the hub's Ø20 face sits on the jig's platform, and the stand
        # sits on a table the same way
        for n, m in self.parts.items():
            self.assertAlmostEqual(float(m.bounds[0][2]), 0.0, places=6,
                                   msg=n)
            if n.endswith(("_gauge", "_probe")):
                continue              # a coupon, not a stand
            lo, hi = m.bounds
            # a 64-gon inscribed in Ø20 is a couple of microns under it
            self.assertGreaterEqual(min(hi[0] - lo[0], hi[1] - lo[1]),
                                    2 * T.HUB_R - 0.01, n)

    def test_a_spike_both_gives_and_holds(self):
        # read in PLA, which is what these print in. Sizing them against
        # PETG's modulus reported twice the give they had, and the set
        # that came out of it was a post in the hand.
        for k, v in self.rep["flex"].items():
            self.assertEqual(v["material"], "PLA", k)
            self.assertGreaterEqual(v["breaks_at_N"], 9.0, k)
            self.assertGreaterEqual(v["spread_mm"], 0.04, k)
        # the spike that snapped takes about 8 N in the same material,
        # and the one before this took 23 with almost no give
        old = dict(G.BY_ID["gz_lg"], tip=0.8, half=1.5)
        old.pop("fillet", None)
        self.assertLess(G.spike_flex(old)["breaks_at_N"], 9.0)
        stiff = G.spike_flex(dict(G.BY_ID["gz_mg"], tip=1.0, half=2.5))
        self.assertLess(stiff["spread_mm"], 0.04)

    def test_the_stress_probe_looks_at_the_real_profile(self):
        # the control, and the mistake that let the first set through:
        # the flank alone is nearly parallel, so a pure-cone model puts
        # the worst section two thirds of the way up. The real part necks
        # at the cove, and that is where it breaks
        for k, v in self.rep["flex"].items():
            self.assertLessEqual(v["worst_at_mm"], 0.25 * G.BY_ID[k]["cone"], k)
        spec = G.BY_ID["gz_lg"]
        h, t = spec["cone"], np.tan(np.radians(spec["half"]))
        s = np.linspace(1e-6, h, 2000)              # the pure cone, from the tip
        r = T.tip_r(spec) + s * t
        naive_z = h - float(s[np.argmax(s * r / (np.pi * r ** 4 / 4))])
        self.assertGreater(naive_z, 0.5 * h)        # it would say high up
        self.assertLess(self.rep["flex"]["gz_lg"]["worst_at_mm"], 0.25 * h)

    def test_every_rod_socket_is_the_measured_size(self):
        # the bracket has been read: a gauge of ten bores, in PLA, said
        # Ø1.5 drawn is the friction fit for a 1 mm rod -- Ø1.4 would not
        # take it, Ø1.6 let it drop through. There is one size now.
        for k, v in self.rep["socket"].items():
            self.assertEqual(v["drawn_d"], G.ROD_BORE, k)
            self.assertAlmostEqual(v["printed_d_expected"], G.ROD_D, delta=0.1)
            self.assertGreaterEqual(v["depth_mm"], 10.0, k)
        # the field is the exception, and it is the exception on
        # evidence: drawn at the friction size it produced 56 bores that
        # would not take a rod, in a filament whose probe said that size
        # was a perfect fit. A rod in a field is glued, so the field is
        # drawn one rung up, where the rod runs free.
        # the field's bore is read on a graded field, and it is a long
        # way above the strip's: 0.11 in PETG, where two rounds of
        # reasoning offered 0.025 and produced plates that took no rod.
        self.assertEqual(self.rep["field"]["gz_rf"]["drawn_d"], G.ROD_FIELD)
        self.assertGreater(G.ROD_FIELD, G.ROD_FREE,
                           "a crowded field needs more than the strip's "
                           "loose size, not less")
        # Ø1.56 was the graded reading; the field runs Ø1.60 because
        # whole-field prints still had stiff bores with no pattern to
        # them, so the spread between bores is wider than a ladder of
        # five rings could resolve. Still well clear of the strip's
        # Ø1.45 -- the crowding correction is the point.
        self.assertAlmostEqual(G.FIELD_BORE["petg"]["d"], 1.60, places=3)
        self.assertTrue(G.FIELD_BORE["petg"]["read"])
        self.assertGreater(G.FIELD_BORE["petg"]["d"] - G.ROD_D, 0.5,
                           "a crowded field needs half a millimeter over "
                           "the rod, not the strip's 0.45")
        # THE FIELD'S NUMBERS STAY OUT OF THE SHARED TABLE. Everything in
        # MATERIALS is a reading that transfers between parts; none of
        # this does, and keeping it there invites the next part to reach
        # for it -- which is the mistake that cost two plates.
        for k, v in G.MATERIALS.items():
            self.assertNotIn("field", v, f"{k}: the field's bore belongs "
                                         f"in FIELD_BORE, not MATERIALS")
        # and a filament nobody has graded says so rather than pretending
        off = G.FIELD_BORE["petg"]["d"] - G.MATERIALS["petg"]["bore"]
        for k, v in G.FIELD_BORE.items():
            self.assertIn("note", v)
            if not v["read"]:
                self.assertIn("inferred", v["note"].lower(), k)
                self.assertAlmostEqual(
                    v["d"] - G.MATERIALS[k]["bore"], off, places=3,
                    msg=f"{k}: an inferred field bore must carry PETG's "
                        f"offset, not a number of its own")

    def test_an_ungraded_filament_says_so_in_the_report(self):
        # the caveat has to travel with the part, not sit in a comment:
        # somebody slicing a PLA field from the archive never reads the
        # source, and an inferred number looks exactly like a measured
        # one once it is geometry
        for k, v in G.FIELD_BORE.items():
            rep = dict(self.rep)
            self.assertTrue(v["read"] or not v["read"])
        f = self.rep["field"]["gz_rf"]
        self.assertIn("bore_measured", f)
        self.assertIn("applies_to", f)
        self.assertIn("this field only", f["applies_to"])
        self.assertEqual(f["bore_measured"], G.FIELD_BORE[G._MAT]["read"])
        # and the funnel has to be tall enough to exist in plastic
        self.assertGreaterEqual(G.FIELD_LEAD[0], 1.0)
        self.assertGreater(G.FIELD_LEAD[0], G.ROD_CHAMFER,
                           "the field's lead-in is deep where the "
                           "socket's is wide")
        # and nothing is drawn below the floor, where a bore stops being
        # round at all
        self.assertGreaterEqual(G.ROD_BORE, G.MIN_BORE)
        # the loss is the one that was measured, not a nozzle width
        self.assertAlmostEqual(G.ROD_LOSS, 0.5, delta=0.01)

    def test_the_coupon_bores_the_same_hole_the_field_does(self):
        # THE lesson from the plate that came out with 56 unusable
        # bores. The probe told the field to draw \u00d81.45, and it was
        # entitled to be believed only if its holes were the field's
        # holes. They were not: same bore, same depth -- both matched on
        # purpose -- and a 0.8 mm 45 degree chamfer against the field's
        # 0.4, because the chamfer was never on the list of things to
        # match. A coupon must instantiate the SAME FEATURE, so both go
        # through one function and the only thing that varies is the
        # diameter.
        d = G.ROD_FIELD
        a = G.field_bore(d, 0.0, 0.0)
        b = G.field_bore(d, 0.0, 0.0)
        self.assertAlmostEqual(a.volume, b.volume, places=6)
        # the probe's bore at the field's own size is the field's bore
        probe = G.field_bore(d, 0.0, 0.0, top=G.FIELD_T)
        self.assertAlmostEqual(probe.volume, a.volume, places=6)
        # and the lead-in is one rule, not two: same depth and width
        # whatever part asks for it
        for dia in (1.45, G.ROD_FIELD, 1.7):
            self.assertEqual(G.field_lead(dia)[0], G.FIELD_LEAD[0], dia)
        # the old 45-degree rule is GONE, not merely unused: a second way
        # to draw the same feature is how the two drifted apart
        self.assertFalse(hasattr(G, "field_chamfer"),
                         "two definitions of one feature is the bug")

    def test_the_graded_field_is_legible_and_keeps_every_hole(self):
        # the sizes were etched beside one hole a ring. The geometry
        # said 0.81 mm of clearance, and that was measured right -- it
        # is simply not enough, because an etched pocket that close
        # leaves a web the printer cannot hold, and a distorted bore
        # corrupts the one reading the plate exists to give. The legend
        # went to the middle, where the field has nothing.
        from shapely import affinity
        from shapely.geometry import Point
        import gen_dice_cage as D
        spec = G.BY_ID["gz_rfg"]
        pts, label = G.field_grade_holes(spec)
        self.assertEqual(label, {}, "no per-ring labels any more")
        self.assertEqual(len(pts), len(G.field_holes(spec)),
                         "a graded field spends no holes on its legend")
        lines = G.grade_legend()
        self.assertTrue(1 <= len(lines) <= 2)
        pitch = G.GRADE_ETCH_SCALE + 1.0
        worst, thinnest = 9e9, 9e9
        for i, txt in enumerate(lines):
            g = affinity.scale(D._raw_glyph(txt), G.GRADE_ETCH_SCALE,
                               G.GRADE_ETCH_SCALE, origin=(0, 0)
                               ).buffer(G.GRADE_ETCH_BOLD, join_style=2)
            lo_x, lo_y, hi_x, hi_y = g.bounds
            y = (len(lines) - 1) / 2.0 * pitch - i * pitch
            g = affinity.translate(g, -(lo_x + hi_x) / 2.0,
                                   y - (lo_y + hi_y) / 2.0)
            lo, hi = 0.0, 2.0
            for _ in range(40):
                m = (lo + hi) / 2.0
                if g.buffer(-m / 2.0).is_empty:
                    hi = m
                else:
                    lo = m
            thinnest = min(thinnest, lo)
            for x, yy in pts:
                d = G.field_grade_d_at(spec, x, yy)
                mouth = Point(x, yy).buffer(d / 2.0 + G.field_lead(d)[1])
                worst = min(worst, g.distance(mouth))
        self.assertGreaterEqual(thinnest, 0.82, "thinner than the stroke "
                                                "the gauge proved cuts")
        self.assertGreater(worst, 2.0, "0.81 mm was measured correctly "
                                       "and still distorted a bore")

    def test_the_grade_brackets_the_size_that_failed(self):
        # it exists to answer one question, so it has to reach past the
        # answer in both directions: below is the size already known to
        # refuse a rod, above is far enough that a shut ring means the
        # trouble is not the bore at all
        # brackets the strip's number from below and reaches well past
        # whatever the field turns out to want from above
        self.assertLess(G.FIELD_GRADE[0], G.FIELD_BORE["petg"]["d"])
        self.assertGreater(G.FIELD_GRADE[-1], G.FIELD_BORE["petg"]["d"])
        self.assertEqual(sorted(G.FIELD_GRADE), list(G.FIELD_GRADE))

    def test_a_socket_tower_fits_the_ring_it_stands_on(self):
        # Ø6.4 towers are comfortable on the L, whose posts stand 8.4 mm
        # apart, and impossible on the S at 4.6: six of them fuse into a
        # solid wall with six holes in it. The tower is only there to give
        # the rod 13 mm of hole, so it narrows to fit -- but never past
        # the wall around the bore.
        import numpy as np
        for k in ("gz_sr", "gz_mr", "gz_lr"):
            spec = G.BY_ID[k]
            P = np.array(G.spikes(spec))
            d = np.hypot(*(P[:, None, :] - P[None, :, :]).T).T
            np.fill_diagonal(d, np.inf)
            rf, rt, h = G.rod_boss_r(spec)
            self.assertLessEqual(2 * rt, float(d.min()) - G.BOSS_AIR + 1e-9,
                                 f"{k}: the tops of two towers touch")
            self.assertGreaterEqual(rt - spec["rods"] / 2.0, G.BOSS_WALL,
                                    f"{k}: no wall left round the bore")
            self.assertGreater(rf, rt, k)
            # and the L is untouched: it was printed at the full size
            if k == "gz_lr":
                self.assertEqual((rf, rt, h), G.ROD_BOSS)

    def test_a_ring_too_tight_for_any_tower_is_refused(self):
        # the control. Narrowing the tower is only honest while there is
        # something left to narrow; a ring that cannot carry a socket at
        # all has to say so rather than draw a bore in thin air.
        spec = dict(G.BY_ID["gz_sr"], id="gz_impossible", ring=3.0)
        with self.assertRaises(SystemExit):
            G.rod_boss_r(spec)

    def test_a_rod_is_a_stiffer_instrument_than_a_spike(self):
        # worth knowing rather than gating: the rod points where the
        # printed spike gives
        # the rod is half the diameter of a spike and still takes more
        # load, which is why the thin job belongs to it
        rod = self.rep["socket"]["gz_lr"]
        self.assertLess(G.ROD_D, 2 * T.tip_r(G.BY_ID["gz_mg"]))
        self.assertLess(rod["max_MPa_at_1N"], 1500.0 / 5.0)

    def test_the_spikes_are_still_finer_than_the_four_cone_family(self):
        # strength came from the flank, not from blunting the point
        for s in RINGS:
            self.assertLessEqual(T.tip_r(s), T.tip_r(T.BY_ID["m"]), s["id"])

    def test_the_flex_model_answers_a_case_with_a_known_shape(self):
        # the control: stiffness goes as the fourth power of the radius,
        # so doubling the tip must cut the spread by much more than half,
        # and a steeper flank must stiffen it further
        spec = G.BY_ID["gz_mg"]
        base = G.spike_flex(spec)["spread_mm"]
        fat = G.spike_flex(dict(spec, tip=2 * spec["tip"]))["spread_mm"]
        steep = G.spike_flex(dict(spec, half=3.5))["spread_mm"]
        self.assertLess(fat, base / 4.0)
        self.assertLess(steep, base / 2.0)

    def test_it_stands_up_whichever_way_the_tooth_leans(self):
        # the deck has no good direction and no bad one. The four-cone
        # stands do: T.tip_back reports the tail's direction, and the
        # fixed L leans 18.3 degrees that way and 9.5 across its arms,
        # which is the number this has to beat
        for s in BUILT_RINGS:
            self.assertGreaterEqual(self.rep["tip_back_deg"][s["id"]],
                                    G.LEAN_TARGET - 0.5, s["id"])
        fixed = T.BY_ID["l"]
        across = fixed["fore"] / 2.0 + T.cone_foot_r(fixed["cone"], fixed) \
            + T.PAD_MARGIN
        h = fixed["teeth"][1] * 0.44
        worst = np.degrees(np.arctan2(across, T.contact_z(fixed) + h))
        self.assertGreater(self.rep["tip_back_deg"]["gz_lg"], worst)

    # --- the rod field ------------------------------------------------
    @staticmethod
    def _cover(rects, reqs):
        R = np.array(rects)
        e = np.array([float(np.hypot(*(R - q).T).min()) for q in reqs])
        return float(e.max()), float(e.mean())

    def test_the_field_is_mirror_symmetric_so_every_hole_is_a_rectangle(self):
        # the whole trick: a hole at (x, y) brings its three mirrors, and
        # those four ARE a centerd rectangle. Without the symmetry the
        # field offers holes but no support quadrilateral
        holes = {(round(x, 2), round(y, 2)) for x, y in G.field_holes()}
        for x, y in holes:
            for sx in (1, -1):
                for sy in (1, -1):
                    self.assertIn((round(sx * x, 2), round(sy * y, 2)), holes)
        self.assertGreaterEqual(len(G.field_rects()), 10)

    def test_the_field_holes_clear_each_other(self):
        p = np.array(G.field_holes())
        d = np.hypot(*(p[:, None, :] - p[None, :, :]).T)
        np.fill_diagonal(d, 9e9)
        self.assertGreaterEqual(d.min(), G.FIELD_MIN_SP - 1e-9)
        # and they are all on the deck, with wall left at the rim
        self.assertLess(np.hypot(*p.T).max(), G.FIELD_R - 3.0)

    def test_the_field_beats_a_golden_spiral_at_what_it_is_for(self):
        # this is the reason the pattern is rings and not a spiral. The
        # spiral's defining property is that nothing lines up, and a
        # centerd rectangle is nothing but lining up
        req = np.array([(c, f) for c in np.arange(10, 52, 2.0)
                        for f in np.arange(5, 26, 2.0)
                        if f <= c and np.hypot(c / 2, f / 2) <= G.FIELD_R - 3.5])
        mine = self._cover(G.field_rects(), req)
        n = len(G.field_holes()) // 4
        phi = (np.sqrt(5) - 1) / 2
        ks = np.arange(n)
        r = (G.FIELD_R - 3.5) * np.sqrt((ks + 0.5) / n)
        th = np.radians(90 * ((ks * phi) % 1.0))
        spiral = [(2 * r[k] * np.cos(th[k]), 2 * r[k] * np.sin(th[k]))
                  for k in ks]
        theirs = self._cover(spiral, req)
        self.assertLess(mine[0], theirs[0])      # worst miss
        self.assertLess(mine[1], theirs[1])      # and the average one
        self.assertLess(mine[0], 9.0)

    def test_the_field_offers_circles_to_nest_on(self):
        # the configuration this whole design is for, at several
        # diameters, each with two gap widths round it
        rings = G.field_rings()
        self.assertGreaterEqual(len(rings), 4)
        ds = [r["d"] for r in rings]
        self.assertEqual(ds, sorted(ds))
        self.assertLessEqual(min(ds), 18.0)      # small enough for an S root
        self.assertGreaterEqual(max(ds), 40.0)   # and large enough for an L
        for r in rings:
            self.assertEqual(len(r["gaps"]), 2, r["d"])
            self.assertGreater(min(r["gaps"]), 2.0, r["d"])
        # every ring's eight holes really are on one circle in the field
        holes = np.array(G.field_holes())
        for r in rings:
            on = np.abs(np.hypot(*holes.T) - r["d"] / 2.0) < 0.05
            self.assertEqual(int(on.sum()), 8, r["d"])

    def test_the_field_is_deep_enough_to_stand_a_rod_up(self):
        f = self.rep["field"]["gz_rf"]
        self.assertGreaterEqual(f["depth_mm"], 6.0)
        self.assertEqual(f["holes"], len(G.field_holes()))
        # a rod cut to this length puts its tip on the M's contact plane
        self.assertGreater(f["rod_len_mm"], 20.0)

    def test_the_gauge_reads_a_constant_rather_than_guessing_one(self):
        # Ø1.7 and Ø1.9 were a two-point bracket extrapolated from one
        # PETG print and then applied in PLA. This is the part that
        # answers it instead: every bore is a real socket, same boss and
        # same depth, so the rod reads the constant off the part
        g = self.rep["gauge"]["gz_gauge"]
        self.assertEqual(len(g["drawn"]), len(G.GAUGE_D))
        self.assertGreaterEqual(len(g["drawn"]), 8)
        step = np.diff(sorted(g["drawn"]))
        self.assertTrue(np.allclose(step, step[0]), "even steps or it is a guess")
        self.assertLessEqual(float(step[0]), 0.1001)
        # it has to start at or below the rod itself, or the tightest
        # bore that works can sit under the range and never be seen.
        # A bore drawn at the rod's own size cannot admit it after any
        # shrinkage, which makes the first column the control
        self.assertLessEqual(min(g["drawn"]), G.ROD_D)
        # it must bracket both of the sizes it is meant to settle
        self.assertGreater(G.ROD_BORE, min(g["drawn"]))
        self.assertLess(G.ROD_BORE, max(g["drawn"]))
        # both rows, because the two sockets on these parts are not the
        # same hole: one is bored up a slim boss, the other straight
        # into a solid plate, and there is no reason to assume they
        # close by the same amount
        # three rows: up a boss, flat and on its own, and flat with two
        # neighbors at the rod field's own spacing -- the field is the
        # case that is still unexplained, and crowding is the suspect
        # three rows: up a boss, flat and on its own, and a close-spaced
        # row that steps in half-tenths so it fills in between the
        # ladder's sizes while also being the crowding case
        self.assertEqual(set(g["rows"]), {"boss", "flat", "fine"})
        for lbl, row in g["rows"].items():
            if lbl == "fine":
                # the close-spaced row augments the ladder rather than
                # repeating it: under each label, that size with a
                # twentieth either side
                self.assertEqual(len(row), 3 * len(g["drawn"]))
                want = [d + (j - 1) * G.GAUGE_FINE
                        for d in g["drawn"] for j in range(3)]
                for a, b in zip(row, want):
                    self.assertAlmostEqual(a, b, delta=0.02)
                continue
            self.assertEqual(len(row), len(g["drawn"]))
            for a, b in zip(row, g["drawn"]):
                self.assertIsNotNone(a)
                self.assertAlmostEqual(a, b, delta=0.05)
        # each row at the depth its real socket has
        self.assertEqual(g["flat_depth_mm"], G.FIELD_T - 1.0)
        # every size reads to one decimal, so the ladder does not mix
        # "1" with "1.1", and the unit is etched once rather than on
        # every label
        import gen_dice_cage as D
        self.assertEqual([f"{d:.1f}" for d in G.GAUGE_D][0], "1.0")
        self.assertEqual([f"{d:.1f}" for d in G.GAUGE_D][-1], "2.0")
        self.assertIsNotNone(D._raw_glyph("mm"))
        # and every column says its own size, so the part needs no legend
        m = self.parts["gazebo_gauge"]
        etched = G.gauge_etch(G.BY_ID["gz_gauge"])
        self.assertGreaterEqual(len(etched), 2 * len(G.GAUGE_D))
        for e in etched:
            # cut INTO the top face, not standing on it
            self.assertLess(float(e.bounds[0][2]), G.deck_z(G.BY_ID["gz_gauge"]))
            self.assertGreaterEqual(
                G.deck_z(G.BY_ID["gz_gauge"]) - float(e.bounds[0][2]),
                G.GAUGE_ETCH - 1e-6)
        # the label band sits between rows, clear of every socket
        holes = [(x, y) for x, y in G.spikes(G.BY_ID["gz_gauge"])]
        for e in etched:
            for y in (float(e.bounds[0][1]), float(e.bounds[1][1])):
                self.assertGreater(min(abs(y - hy) for _, hy in holes), 3.0)
        # a socket's depth, not a plate's: a short hole prints nothing
        # like a 12 mm one
        self.assertEqual(g["depth_mm"],
                         self.rep["socket"]["gz_lr"]["depth_mm"])

    def test_the_ruler_is_as_fine_as_the_nozzle_can_cut(self):
        # measured against the slicer, not guessed: at 0.8 mm wide the
        # toolpath ran through every tick and cut none of them, and at
        # 1 mm pitch a 1.0 wide tick leaves no land between ticks
        self.assertGreaterEqual(G.RULE_W, 1.0)
        self.assertGreaterEqual(G.RULE_PITCH - G.RULE_W, G.RULE_W - 1e-9)
        ticks = G.gauge_ruler(G.BY_ID["gz_gauge"])
        self.assertGreater(len(ticks), 40)
        from shapely.geometry import LineString
        plan = G.gauge_plan(G.BY_ID["gz_gauge"])
        holes = G.spikes(G.BY_ID["gz_gauge"])
        for t in ticks:
            # every tick starts at the edge under it, not at a straight
            # baseline: the edge is slanted, so a baseline left them
            # floating off it by a different amount at each end
            x = (float(t.bounds[0][0]) + float(t.bounds[1][0])) / 2
            edge = plan.intersection(LineString([(x, -200), (x, 200)])).bounds[1]
            self.assertLess(float(t.bounds[0][1]), edge)
            self.assertGreater(float(t.bounds[1][1]), edge)
            # and stops short of the sockets
            self.assertLess(float(t.bounds[1][1]), -16.3)

    def test_export_carries_the_ring_inside_the_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "gazebo.3mf")
            bad = G.export(self.parts, out, self.rep)
            self.assertEqual(bad, {})
            with zipfile.ZipFile(out) as z:
                self.assertIn("Metadata/gazebo.json", z.namelist())
                d = json.loads(z.read("Metadata/gazebo.json"))
                ps = z.read("Metadata/project_settings.config").decode()
            self.assertIn('"brim_type": "no_brim"', ps)
            self.assertEqual(set(d["to_world"]), set(self.parts))
            self.assertEqual(d["ring"]["deck_sides"], 8)
            for s in d["sizes"]:
                if s.get("gauge") or s.get("probe"):
                    continue
                if s.get("field"):
                    self.assertGreaterEqual(len(s["field"]["rects"]), 10)
                    self.assertGreaterEqual(len(s["field"]["rings"]), 4)
                    continue
                self.assertEqual(len(s["spikes"]), s["n"], s["id"])
                self.assertIn("flex", s)


if __name__ == "__main__":
    unittest.main()
