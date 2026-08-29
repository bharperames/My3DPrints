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
            self.assertTrue(os.path.exists(os.path.join(ROOT, p["preview"])),
                            p["preview"])

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
        # the curated copy in models/ and the download it came from are the
        # same design; listing both put it in the catalog twice
        folded = [p for p in self.parts if p.get("copies", 1) > 1]
        self.assertTrue(folded, "expected some designs kept in both places")
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
        # "00 start.3mf" means something different in each project folder
        names = [p["name"] for p in self.parts]
        self.assertGreater(len(names) - len(set(names)), 0,
                           "expected distinct files that share a name")

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
        # single file: cards load lazily, roughly two dozen at a time
        kb = sorted(e["kb"] for e in self.index)
        median = kb[len(kb) // 2]
        self.assertLess(median, 450, f"median preview {median} KB")
        self.assertLess(sum(kb[:24]) / 24, 400, "a first screenful is heavy")

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
