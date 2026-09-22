"""The catalog is one list, and every entry in it can be shown and printed.

The page renders a card per entry with no branch on where the entry came
from, so these tests guard the fields that makes that possible: geometry
the page can load for everything, curation folded in where a human wrote
some, and enough default dials on a parametric part that it can actually be
built.

"Geometry the page can load" used to mean a GLB built beside every source.
It does not any more: the browser reads 3MF and STL directly, so a part
points at its own file and only a COMPOSITE -- a kit card, which shows every
member at once and matches no single file on disk -- still gets one built.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import catalog  # noqa: E402
import designs  # noqa: E402
import previews  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _built_preview(pid, src, **kw):
    """Build a preview into a scratch directory and hand back the scene.

    Parts are no longer shipped a GLB -- the page reads the 3MF itself --
    but the builder still lays parts out for the composites, and that
    behavior is what these tests are about. So build one on the spot
    rather than reaching for an artifact that is deliberately not there.
    """
    import tempfile
    import trimesh
    old = previews.OUT
    with tempfile.TemporaryDirectory() as tmp:
        previews.OUT = tmp
        try:
            previews.build_one(pid, src, write=True, **kw)
            return trimesh.load(os.path.join(tmp, pid + ".glb"), force="scene")
        finally:
            previews.OUT = old


class TestOneList(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = catalog.catalog()
        cls.parts = cls.cat["parts"]

    def test_every_entry_carries_what_a_card_needs(self):
        for p in self.parts:
            for k in ("id", "name", "family", "kind"):
                self.assertTrue(p.get(k), f"{p.get('id')} has no {k}")

    def test_every_entry_has_geometry_the_page_can_load(self):
        missing = [p["id"] for p in self.parts
                   if not (p.get("src") or p.get("preview"))]
        self.assertEqual(missing, [], f"nothing to render for {missing}")

    def test_a_part_points_at_its_own_file(self):
        for p in self.parts[:40]:
            self.assertTrue(p["src"].startswith("/src?id="), p["src"])
            self.assertIn(p["ext"], ("3mf", "stl", "glb", "obj"), p["id"])

    def test_the_source_route_hands_back_that_file(self):
        # the field is a promise the server has to keep, and for a library
        # part the file may sit outside the repo entirely
        for p in self.parts[:6]:
            src = (p.get("path") if p["kind"] == "library"
                   else catalog.out_path(p, catalog.defaults(p)))
            self.assertTrue(src and os.path.isfile(src),
                            f"{p['id']} has no file at {src}")

    def test_only_composites_still_carry_a_built_preview(self):
        # a GLB is worth writing only where nothing on disk is the picture
        withglb = [p["id"] for p in self.parts if p.get("preview")]
        self.assertEqual(withglb, [], f"parts should read their own file: {withglb}")
        kits = [k for k in self.cat["kits"] if k.get("preview")]
        self.assertTrue(kits, "a kit card shows all its members and needs one")
        for k in kits[:5]:
            f = k["preview"].split("?")[0]
            self.assertTrue(os.path.exists(os.path.join(ROOT, f)), f)
            self.assertRegex(k["preview"], r"\?v=[0-9a-f]{8}$")

    def test_a_curated_file_keeps_its_designer_and_title(self):
        ball = next(p for p in self.parts if p["name"] == "Mini Fidget Ball")
        self.assertEqual(ball["family"], "Passthrough series")
        self.assertTrue(ball["designer"])
        self.assertIn("genus", ball["blurb"].lower())
        self.assertEqual(ball["verdict"][0], "pass")

    def test_an_uncurated_file_is_still_a_complete_entry(self):
        plain = [p for p in self.parts
                 if p["kind"] == "library" and not p.get("designer")]
        self.assertTrue(plain, "expected some files nobody has written up")
        for p in plain[:5]:
            self.assertTrue(p.get("src") and p.get("dims"))

    def test_a_design_kept_in_two_places_is_one_entry(self):
        # models/ and Downloads can hold the same design at different save
        # states. Exercised directly: Downloads is not scanned unless the
        # user imports, so the catalog itself may show no folded pair.
        both = catalog.library(dirs=[catalog.MODELS, catalog.DOWNLOADS],
                               include_imported=False)
        folded = [p for p in both if p.get("copies", 1) > 1]
        if not folded:
            self.skipTest("nothing is currently kept in both places")
        for p in folded:
            self.assertTrue(p["path"].startswith(catalog.MODELS),
                            f"{p['name']} kept the uncurated copy")
            self.assertEqual(len(p["also"]), p["copies"] - 1)

    def test_the_generators_own_output_is_not_listed_twice(self):
        # custom/ holds what the generators wrote; those are already parts
        dup = [p["id"] for p in self.parts
               if "/custom/" in p.get("path", "")]
        self.assertEqual(dup, [])

    def test_an_experimental_plate_is_one_card_not_two(self):
        # the shelf under models/experimental is named by experimental(),
        # and the models/ walk was ALSO picking every plate up, so each one
        # appeared twice: once as "Tooth Stands with gazebo spikes" and
        # once as the raw "gazebo-r21-spiked-stands-pla". The control is
        # below it: the scanner must still find them at all.
        paths = [p.get("path", "") for p in self.parts]
        exp = [q for q in paths if "/experimental/" in q]
        self.assertEqual(sorted(exp), sorted(set(exp)),
                         "an experimental plate is listed twice")
        self.assertEqual(len(exp), len(catalog.experimental()),
                         "the experimental shelf is not being read")
        self.assertGreater(len(exp), 0)

    def test_unrelated_files_sharing_a_name_stay_separate(self):
        # "00 start.3mf" means something different in each project folder,
        # so folding is only for the models/ + Downloads pair
        both = catalog.library(dirs=[catalog.MODELS, catalog.DOWNLOADS],
                               include_imported=False)
        names = [p["name"] for p in both]
        dupes = len(names) - len(set(names))
        if not dupes:
            self.skipTest("no distinct files currently share a name")
        self.assertGreater(dupes, 0)

    def test_sliced_exports_are_not_offered_as_models(self):
        # a *.gcode.3mf is a slice of a print, not something to print
        bad = [p["id"] for p in self.parts
               if p.get("path", "").lower().endswith(".gcode.3mf")]
        self.assertEqual(bad, [])

    def test_families_cover_every_entry(self):
        fams = set(self.cat["families"])
        for p in self.parts:
            self.assertIn(p["family"], fams)


class TestDefaults(unittest.TestCase):
    def test_a_kit_member_inherits_the_kits_shared_dials(self):
        # the clasp's size comes from the chain set, not from the clasp
        clasp = catalog.find("clasp")
        self.assertEqual(clasp.get("params"), None)
        self.assertIn("dia", catalog.defaults(clasp))

    def test_every_parametric_part_can_build_from_its_defaults(self):
        for p in catalog.PARTS:
            if p["kind"] not in ("parametric", "generated"):
                continue
            d = catalog.defaults(p)
            try:
                catalog.out_path(p, d)
            except KeyError as e:
                self.fail(f"{p['id']} has no default for {e}")

    def test_a_parts_own_dial_wins_over_the_kits(self):
        chain = catalog.find("chain")
        d = catalog.defaults(chain)
        self.assertIn("links", d)          # its own
        self.assertIn("dia", d)            # the kit's


class TestCuration(unittest.TestCase):
    def test_curation_is_found_by_filename(self):
        self.assertIsNotNone(designs.curation("Vortex+v3+project.3mf"))
        self.assertIsNotNone(
            designs.curation("/anywhere/Vortex+v3+project.3mf"))
        self.assertIsNone(designs.curation("not-a-real-file.3mf"))

    def test_every_curated_design_names_a_file_that_exists(self):
        # curation is matched to a catalog entry by filename, so a typo
        # here silently drops a designer's write-up off the card
        names = {os.path.basename(p.get("path", ""))
                 for p in catalog.catalog()["parts"]}
        missing = [c["file"] for c in designs.C
                   if c["file"] not in names]
        self.assertEqual(missing, [], f"curated but not in the catalog: "
                                      f"{missing}")


class TestPreviewIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "models", "previews.json")) as fh:
            cls.index = json.load(fh)

    def test_every_preview_records_what_it_came_from(self):
        for e in self.index:
            self.assertTrue(e.get("stamp"), e["id"])
            self.assertGreater(e["tris"], 0)
            self.assertEqual(len(e["dims"]), 3)

    def test_a_small_part_is_not_cut_to_fit_a_big_one(self):
        # the wrench shares a set with an 88,000-face base plate; sharing
        # the budget in proportion took three quarters of its faces and it
        # rendered as a ribbon
        w = next((e for e in self.index if e["id"] == "wrench"), None)
        if w is None:
            self.skipTest("no wrench preview")
        self.assertEqual(w["tris"], w["tris_full"],
                         "the wrench was decimated")

    def test_previews_are_the_real_geometry(self):
        """No detail is thrown away without evidence that it has to be.

        A ceiling was set here from frame rates measured in headless
        Chromium, which falls back to SwiftShader and rasterizes on the
        CPU — numbers describing a renderer nobody uses. On the machine
        this runs on, two dozen live cards sit at the display's 120 Hz
        with the full meshes. The trade was paid for before anything asked
        for it.
        """
        if previews.BUDGET:
            self.skipTest("a budget is deliberately set")
        cut = [e["id"] for e in self.index if e["tris"] < e["tris_full"]]
        self.assertEqual(cut, [], f"decimated with no budget set: {cut}")

    def test_a_budget_when_set_is_shared_not_split_evenly(self):
        # the rule that ruined the wrench: an even fraction takes the same
        # share off a part that cannot spare it
        import meshcheck
        got = meshcheck.budget_faces([20484, 88062, 4736], 26000)
        self.assertEqual(got[2], 4736, "the small part was cut")
        self.assertLessEqual(sum(got), 26000)

    def test_a_changed_source_invalidates_its_preview(self):
        e = self.index[0]
        path = None
        for pid, src in previews.sources():
            if pid == e["id"]:
                path = src
                break
        if not path:
            self.skipTest("source for the first preview is gone")
        # the key is the source stamp plus the builder's, so a change to
        # either rebuilds the preview
        self.assertTrue(e["stamp"].startswith(previews.stamp(path)),
                        f"{e['stamp']} does not start with the source stamp")
        self.assertIn(f"|b{previews._builder_stamp()}", e["stamp"])

    def test_an_assembly_is_not_pulled_apart(self):
        # bodies that overlap are positioned on purpose - a captive ball
        # inside its cage must not be tiled out beside it
        import trimesh
        path = catalog.ensure(catalog.find("dice_orb"))[0]
        meshes = previews._load(path)
        self.assertGreater(len(meshes), 1)
        self.assertTrue(previews._overlapping(meshes))
        sc = _built_preview("probe_dice_orb", path)
        bounds = [g.bounds for g in sc.geometry.values()]
        self.assertTrue(any(
            (a[0] < b[1]).all() and (b[0] < a[1]).all()
            for i, a in enumerate(bounds) for b in bounds[i + 1:]),
            "the die came out beside its cage instead of inside it")


if __name__ == "__main__":
    unittest.main()


class TestEveryPartIsVersioned(unittest.TestCase):
    """A version on every part, and a fingerprint that keeps it honest."""

    @classmethod
    def setUpClass(cls):
        import versions
        cls.V = versions
        cls.cat = catalog.catalog()
        cls.parts = cls.cat["parts"]

    def test_every_part_has_a_semver(self):
        bad = [(p["id"], p.get("version")) for p in self.parts
               if not self.V.SEMVER.match(str(p.get("version", "")))]
        self.assertEqual(bad, [], f"not semver: {bad[:5]}")

    def test_library_parts_are_versioned_too(self):
        lib = [p for p in self.parts if p["kind"] == "library"]
        self.assertTrue(lib)
        for p in lib:
            self.assertTrue(self.V.SEMVER.match(p["version"]), p["name"])
            self.assertEqual(p["version_source"], "observed")

    def test_a_designers_own_version_is_used_when_they_gave_one(self):
        v3 = next((p for p in self.parts if p["name"] == "Vortex v3"), None)
        if v3 is None:
            self.skipTest("Vortex v3 not present")
        self.assertEqual(v3["version"], "3.0.0")

    def test_a_file_name_is_not_mistaken_for_a_version(self):
        # "voro_sphere_2" and "c-shape copy 16" are not v2 and v16
        for name in ("voro_sphere_2.stl", "c-shape copy 16.stl"):
            self.assertIsNone(
                self.V.declared_version({"path": name}), name)
        self.assertEqual(
            self.V.declared_version({"path": "Vortex+v3+project.3mf"}), "3.0.0")

    def test_every_part_carries_a_fingerprint(self):
        missing = [p["id"] for p in self.parts if not p.get("fingerprint")]
        self.assertEqual(missing, [])

    def test_a_generator_that_changes_without_a_bump_is_a_fault(self):
        led, _ = self.V.reconcile(self.parts, write=False)
        tampered = {k: dict(v) for k, v in led.items()}
        tampered["wrench"]["fingerprint"] = "0" * 16
        _, faults = self.V.reconcile(self.parts, led=tampered, write=False)
        self.assertTrue(faults)
        self.assertIn("wrench", faults[0]["id"])
        # bumping the declared version settles it
        tampered["wrench"]["version"] = "0.0.1"
        _, ok = self.V.reconcile(self.parts, led=tampered, write=False)
        self.assertEqual(ok, [])

    def test_a_redownloaded_file_bumps_its_patch(self):
        led, _ = self.V.reconcile(self.parts, write=False)
        lib = next(p for p in self.parts if p["kind"] == "library")
        t = {k: dict(v) for k, v in led.items()}
        before = t[lib["id"]]["version"]
        t[lib["id"]].update(fingerprint="0" * 16, stamp="stale")
        after, faults = self.V.reconcile(self.parts, led=t, write=False)
        self.assertEqual(faults, [])
        self.assertNotEqual(after[lib["id"]]["version"], before)
        self.assertEqual(after[lib["id"]]["revisions"], 1)

    def test_the_shipped_catalog_has_no_version_faults(self):
        self.assertEqual(self.cat["version_faults"], [])


class TestAVersionFaultDoesNotForgetItself(unittest.TestCase):
    """The guard has to keep firing until someone fixes it.

    Recording the new fingerprint while reporting the fault clears it on the
    next run, so the build fails once and then goes quiet with the wrong
    version still declared — which is worse than not checking.
    """

    def setUp(self):
        import versions
        self.V = versions
        self.parts = catalog.catalog()["parts"]
        self.led, _ = versions.reconcile(self.parts, write=False)

    def test_the_fault_survives_a_second_pass(self):
        t = {k: dict(v) for k, v in self.led.items()}
        t["wrench"]["fingerprint"] = "0" * 16
        first, f1 = self.V.reconcile(self.parts, led=t, write=False)
        self.assertTrue(f1)
        second, f2 = self.V.reconcile(self.parts, led=first, write=False)
        self.assertTrue(f2, "the fault cleared itself without a version bump")
        self.assertEqual(f1[0]["id"], f2[0]["id"])

    def test_a_bump_is_what_clears_it(self):
        t = {k: dict(v) for k, v in self.led.items()}
        t["wrench"]["fingerprint"] = "0" * 16
        after, _ = self.V.reconcile(self.parts, led=t, write=False)
        bumped = [dict(p, version="9.9.9") if p["id"] == "wrench" else p
                  for p in self.parts]
        _, clean = self.V.reconcile(bumped, led=after, write=False)
        self.assertEqual(clean, [])


class TestPrintabilityAdviceIsTrustworthy(unittest.TestCase):
    """Advice that cries wolf is worse than none.

    Checked against three parts whose outcome on the printer is known: the
    wrench came out perfect, the dice orb failed bare and worked with
    supports and a brim, and the fidget ball's disc finished while its ball
    came loose part-way up.
    """

    @classmethod
    def setUpClass(cls):
        import orient
        cls.O = orient
        cls.parts = {p["name"]: p for p in catalog.catalog()["parts"]}

    def _adv(self, name):
        p = self.parts.get(name)
        if p is None:
            self.skipTest(f"{name} not in the catalog")
        return (p.get("printability") or {}).get("advice", [])

    def test_a_part_that_printed_perfectly_is_not_flagged(self):
        adv = self._adv("Nut Wrench")
        self.assertTrue(adv)
        self.assertNotIn("support", " ".join(adv).lower())
        self.assertNotIn("brim", " ".join(adv).lower())

    def test_a_part_that_prints_support_free_is_not_told_to_use_supports(self):
        # every one of these came off the plate without supports; an earlier
        # version of the check asked for them on all of them
        # every one of these has now come off this printer support-free
        for name in ("Dice Orb", "Base Plate 2×3", "Nut Wrench",
                     "Flexi Imperial Dragon",
                     "Flexi Skeleton T-Rex — curved",
                     "Flexi Skeleton T-Rex — straight"):
            adv = self._adv(name)
            if not adv:
                continue
            self.assertNotIn("supports:", " ".join(adv).lower(), name)

    def test_an_island_is_told_apart_from_a_ledge(self):
        # a joint's overhang is joined to what is under it and bridges; a
        # part that starts in mid-air is not and does not
        import trimesh
        a = trimesh.creation.box(extents=[20, 20, 2])
        a.apply_translation([0, 0, 1])
        b = trimesh.creation.box(extents=[12, 12, 2])
        b.apply_translation([0, 0, 9])
        island, ledge = self.O._unsupported(
            trimesh.util.concatenate([a, b]))
        self.assertGreater(island, 100, "a floating slab is an island")
        cone = trimesh.creation.cone(radius=15, height=15, sections=64)
        self.assertEqual(self.O._unsupported(cone)[0], 0.0)
        self.assertEqual(
            self.O._unsupported(trimesh.creation.box(extents=[20, 20, 20]))[0],
            0.0)

    def test_a_gap_in_the_part_does_not_reset_the_check(self):
        # an empty slice used to mean "no previous layer", which skipped the
        # comparison on the layer after it — the island itself
        import trimesh
        a = trimesh.creation.box(extents=[20, 20, 2])
        a.apply_translation([0, 0, 1])
        b = trimesh.creation.box(extents=[12, 12, 2])
        b.apply_translation([0, 0, 20])          # a much bigger gap
        island, _ = self.O._unsupported(trimesh.util.concatenate([a, b]))
        self.assertGreater(island, 100)

    def test_the_part_whose_ball_came_loose_says_brim(self):
        self.assertIn("brim", " ".join(self._adv("Mini Fidget Ball")).lower())

    def test_facing_down_is_not_mistaken_for_unsupported(self):
        # a cage strut points straight down and is carried by its own
        # previous layer; counting normals scored the dice orb at 4700 mm2
        import trimesh
        path, _ = catalog.ensure(catalog.find("dice_orb"))
        sc = trimesh.load(path, force="scene")
        g = max(sc.geometry.values(), key=lambda m: len(m.faces))
        g = g.copy()
        g.apply_translation([0, 0, -g.bounds[0][2]])
        m = self.O._measure(g)
        self.assertGreater(m["facing_down_mm2"], 1000)
        self.assertLess(m["overhang_mm2"], m["facing_down_mm2"] / 4)

    def test_as_saved_can_win_the_orientation_search(self):
        # leaving it out let the search "improve" a part into a worse
        # orientation than the one it arrived in
        import trimesh
        p = self.parts.get("Mini Fidget Ball")
        if p is None:
            self.skipTest("not present")
        sc = trimesh.load(p["path"], force="scene")
        ball = [g for g in sc.geometry.values()
                if abs(g.bounds[1][2] - g.bounds[0][2]) > 20]
        if not ball:
            self.skipTest("no ball body")
        asis, rest = self.O.evaluate(ball[0], limit=6)
        self.assertLessEqual(rest[0]["overhang_mm2"], asis["overhang_mm2"])


class TestMultiPartToysAreOneCard(unittest.TestCase):
    """An hourglass is a body and the spiral that screws through it.

    They ship as separate files because they print separately, and the
    catalog listed them as separate designs — thirteen cards for four toys,
    with nothing saying which spiral goes through which body.
    """

    @classmethod
    def setUpClass(cls):
        cls.cat = catalog.catalog()
        cls.kits = cls.cat["kits"]
        cls.parts = cls.cat["parts"]

    def test_the_hourglass_pairs_are_sets(self):
        ids = {k["id"] for k in self.kits}
        for want in ("hourglass_cone_90", "hourglass_cone_180",
                     "hourglass_pyramid_90", "hourglass_pyramid_180"):
            self.assertIn(want, ids)

    def test_a_set_holds_a_body_and_a_spiral(self):
        s = next(k for k in self.kits if k["id"] == "hourglass_cone_90")
        labels = " ".join(m["label"] for m in s["members"]).lower()
        self.assertIn("body", labels)
        self.assertIn("spiral", labels)
        self.assertGreaterEqual(len(s["members"]), 2)

    def test_set_members_do_not_also_stand_alone(self):
        inset = {m["part"] for k in self.kits for m in k["members"]}
        solo = [p for p in self.parts if p["id"] not in inset]
        # the parts absorbed into sets are gone from the loose list
        self.assertLess(len(solo), len(self.parts))
        for p in solo:
            self.assertNotIn(p["id"], inset)

    def test_a_set_is_dropped_rather_than_shown_with_holes(self):
        # nothing resolves against an empty shelf, so nothing is offered
        self.assertEqual(catalog.sets([]), [])
        one = [{"id": "x", "path": "/tmp/cone-solid-small.stl"}]
        self.assertEqual(catalog.sets(one), [])


class TestPreviewsDoNotPileParts(unittest.TestCase):
    """Parts from different files are separate objects, whatever their
    coordinates say — each is modeled about its own origin."""

    @staticmethod
    def _world(path):
        import trimesh
        sc = trimesh.load(path, force="scene")
        out = []
        for node in sc.graph.nodes_geometry:
            tf, gk = sc.graph[node]
            g = sc.geometry[gk].copy()
            g.apply_transform(tf)
            out.append(g)
        return out

    def test_a_set_preview_lays_its_parts_out(self):
        import numpy as np
        f = os.path.join(ROOT, "models/glb/prev/kit_chain_set.glb")
        if not os.path.exists(f):
            self.skipTest("chain set preview not built")
        gs = self._world(f)
        self.assertGreater(len(gs), 1)
        c = [g.bounds.mean(axis=0) for g in gs]
        d = min(float(np.linalg.norm(c[i][:2] - c[j][:2]))
                for i in range(len(c)) for j in range(i + 1, len(c)))
        self.assertGreater(d, 2.0, "the parts are stacked on one spot")

    def test_a_captive_assembly_is_left_alone(self):
        # the die belongs inside its cage; spreading them out would be a
        # lie about what the object is
        import trimesh
        path, _ = catalog.ensure(catalog.find("dice_orb"))
        sc = _built_preview("probe_dice_orb2", path)
        ms = []
        for node in sc.graph.nodes_geometry:
            tf, gk = sc.graph[node]
            g = sc.geometry[gk].copy(); g.apply_transform(tf); ms.append(g)
        self.assertEqual(len(ms), 2)
        a, b = sorted(ms, key=lambda m: m.volume)
        self.assertTrue((a.bounds[0] >= b.bounds[0] - 1).all()
                        and (a.bounds[1] <= b.bounds[1] + 1).all(),
                        "the die is no longer inside the cage")

    def test_the_builder_is_part_of_the_cache_key(self):
        # the stamp covered the source files and not the code that turns
        # them into a preview, so fixing the layout changed nothing
        import previews
        import json as _j
        with open(os.path.join(ROOT, "models/previews.json")) as fh:
            idx = _j.load(fh)
        self.assertTrue(idx)
        for e in idx[:5]:
            self.assertIn(f"|b{previews._builder_stamp()}", e["stamp"])


class TestAVersionCountsRealChanges(unittest.TestCase):
    """A rebuild is not a revision.

    A 3MF is a zip and both layers carry something that moves on its own:
    the zip records when it was written, and trimesh stamps a fresh random
    UUID into the model XML on every export. Hashing the bytes made every
    `make build` look like a new version — the held sphere reached its
    thirtieth in four days without anyone touching it.
    """

    def setUp(self):
        import versions
        self.V = versions

    def _fp(self, path):
        return self.V.fingerprint({"kind": "library", "path": path})[0]

    def test_re_exporting_the_same_geometry_keeps_its_version(self):
        import tempfile
        import time
        import trimesh
        d = tempfile.mkdtemp()
        sc = trimesh.Scene()
        sc.add_geometry(trimesh.creation.box(extents=[10, 10, 10]), geom_name="b")
        a, b = os.path.join(d, "a.3mf"), os.path.join(d, "b.3mf")
        sc.export(a)
        time.sleep(0.05)
        sc.export(b)
        self.assertEqual(self._fp(a), self._fp(b))

    def test_a_real_change_is_still_seen(self):
        import tempfile
        import trimesh
        d = tempfile.mkdtemp()
        for name, z in (("a.3mf", 10), ("c.3mf", 11)):
            sc = trimesh.Scene()
            sc.add_geometry(trimesh.creation.box(extents=[10, 10, z]),
                            geom_name="b")
            sc.export(os.path.join(d, name))
        self.assertNotEqual(self._fp(os.path.join(d, "a.3mf")),
                            self._fp(os.path.join(d, "c.3mf")))

    def test_the_uuid_is_what_was_moving(self):
        self.assertEqual(
            self.V._stable(b'<object id="1" p:UUID="'
                           b'adfa7ff5-b4df-4f61-b563-8a7d95c6e098" x="1"/>'),
            self.V._stable(b'<object id="1" p:UUID="'
                           b'372aaf3a-61b4-4479-bdc1-5feb0e5c9a73" x="1"/>'))

    def test_the_superseded_chain_tests_are_gone(self):
        # gen_chain.py proves the same joint for any length, and the two
        # fixed test chains were left in the catalog as cards nobody would
        # choose — regenerated, and so re-versioned, on every build
        names = {p["name"] for p in catalog.catalog()["parts"]}
        self.assertNotIn("chain-test-5seg", names)
        self.assertNotIn("chain-test-5seg-2x", names)
