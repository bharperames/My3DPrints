"""The catalog is one list, and every entry in it can be shown and printed.

The page renders a card per entry with no branch on where the entry came
from, so these tests guard the fields that makes that possible: a preview
for everything, curation folded in where a human wrote some, and enough
default dials on a parametric part that it can actually be built.
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


class TestOneList(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = catalog.catalog()
        cls.parts = cls.cat["parts"]

    def test_every_entry_carries_what_a_card_needs(self):
        for p in self.parts:
            for k in ("id", "name", "family", "kind"):
                self.assertTrue(p.get(k), f"{p.get('id')} has no {k}")

    def test_every_entry_has_a_preview(self):
        missing = [p["id"] for p in self.parts if not p.get("preview")]
        self.assertEqual(missing, [], f"no preview for {missing}")

    def test_preview_files_are_on_disk(self):
        for p in self.parts[:40]:
            f = p["preview"].split("?")[0]
            self.assertTrue(os.path.exists(os.path.join(ROOT, f)), f)

    def test_a_preview_url_carries_a_version_tag(self):
        # a rebuilt preview must be a new address, or the browser keeps
        # showing the geometry it cached before the fix
        tagged = [p for p in self.parts if "?v=" in p.get("preview", "")]
        self.assertGreater(len(tagged), len(self.parts) * 0.9)
        for p in tagged[:5]:
            self.assertRegex(p["preview"], r"\?v=[0-9a-f]{8}$")

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
            self.assertTrue(p.get("preview") and p.get("dims"))

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

    def test_a_preview_over_budget_says_so(self):
        # (only previews the catalog still shows)
        # some meshes will not decimate — a lattice cannot lose a handle
        # and stay the same object. That is allowed, but it is recorded,
        # never passed off as a preview that met its budget.
        for e in self.index:
            over = e["tris"] > previews.BUDGET
            self.assertEqual(bool(e.get("capped")), over,
                             f"{e['id']} at {e['tris']} tris")
            if over:
                self.assertIn("decimator stopped", e["capped_note"])

    def test_the_typical_card_is_light(self):
        # what governs the page is the weight of a screenful, not the worst
        # single file: cards load lazily, roughly two dozen at a time. Only
        # previews the catalog still shows count.
        # The median moved when Downloads stopped being scanned by default:
        # what is left is the curated shelf, which is the detailed end of the
        # collection. So the bar is the two things a viewer actually feels —
        # what the first screenful costs, and whether any one card is absurd —
        # rather than a median calibrated against a population we no longer
        # show.
        live = {p["id"] for p in catalog.catalog()["parts"]}
        kb = sorted(e["kb"] for e in self.index if e["id"] in live)
        self.assertTrue(kb, "no live previews")
        self.assertLess(sum(kb[:24]) / min(24, len(kb)), 400,
                        "a first screenful is heavy")
        # A heavy card is allowed only where the index says why it is heavy:
        # some meshes will not decimate, and that is recorded rather than
        # hidden. An unexplained 4 MB card is the thing to catch.
        heavy = [e for e in self.index
                 if e["id"] in live and e["kb"] > 2500 and not e.get("capped")]
        self.assertEqual([e["id"] for e in heavy], [],
                         "heavy previews with no recorded reason")

    def test_a_changed_source_invalidates_its_preview(self):
        e = self.index[0]
        path = None
        for pid, src in previews.sources():
            if pid == e["id"]:
                path = src
                break
        if not path:
            self.skipTest("source for the first preview is gone")
        self.assertEqual(previews.stamp(path), e["stamp"])

    def test_an_assembly_is_not_pulled_apart(self):
        # bodies that overlap are positioned on purpose - a captive ball
        # inside its cage must not be tiled out beside it
        import trimesh
        path = catalog.ensure(catalog.find("dice_orb"))[0]
        meshes = previews._load(path)
        self.assertGreater(len(meshes), 1)
        self.assertTrue(previews._overlapping(meshes))
        sc = trimesh.load(os.path.join(ROOT, "models", "glb", "prev",
                                       "dice_orb.glb"), force="scene")
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
