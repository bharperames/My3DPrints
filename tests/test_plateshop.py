"""Unit tests for the plate packer and the shop catalog."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import catalog  # noqa: E402
import plateshop as PS  # noqa: E402


def items(*specs):
    """(name, w, d, [h]) -> per-copy item dicts."""
    out = []
    for i, s in enumerate(specs):
        name, w, d = s[0], s[1], s[2]
        h = s[3] if len(s) > 3 else 10.0
        out.append(dict(key=name, name=name, w=w, d=d, h=h, path="", copy=i))
    return out


class TestPacker(unittest.TestCase):
    def test_everything_lands_inside_the_usable_area(self):
        plates, over = PS.pack(items(*[("a", 40, 30)] * 12))
        self.assertFalse(over)
        uw = 256 - 2 * PS.MARGIN
        for p in plates:
            for it in p["items"]:
                self.assertLessEqual(abs(it["x"]) + it["pw"] / 2, uw / 2 + 1e-6)
                self.assertLessEqual(abs(it["y"]) + it["pd"] / 2, uw / 2 + 1e-6)

    def test_no_two_parts_overlap(self):
        plates, _ = PS.pack(items(*[("a", 61, 61)] * 9, *[("b", 35, 20)] * 7))
        for p in plates:
            box = [(i["x"] - i["pw"] / 2, i["y"] - i["pd"] / 2,
                    i["x"] + i["pw"] / 2, i["y"] + i["pd"] / 2)
                   for i in p["items"]]
            for i in range(len(box)):
                for j in range(i + 1, len(box)):
                    a, b = box[i], box[j]
                    gap_x = a[2] <= b[0] + 1e-9 or b[2] <= a[0] + 1e-9
                    gap_y = a[3] <= b[1] + 1e-9 or b[3] <= a[1] + 1e-9
                    self.assertTrue(gap_x or gap_y, f"{a} overlaps {b}")

    def test_parts_keep_a_gap_between_them(self):
        plates, _ = PS.pack(items(*[("a", 50, 50)] * 4))
        xs = sorted({round(i["x"], 3) for i in plates[0]["items"]})
        if len(xs) > 1:
            self.assertGreaterEqual(xs[1] - xs[0], 50 + PS.GAP - 1e-6)

    def test_overflow_opens_another_plate(self):
        plates, over = PS.pack(items(*[("big", 120, 120)] * 5))
        self.assertFalse(over)
        self.assertGreaterEqual(len(plates), 2)
        self.assertEqual(sum(len(p["items"]) for p in plates), 5)

    def test_oversized_is_refused_by_reason_not_dropped(self):
        plates, over = PS.pack(items(("wide", 300, 20), ("tall", 20, 20, 400),
                                     ("ok", 20, 20)))
        self.assertEqual({o["name"]: o["reason"] for o in over},
                         {"wide": "footprint", "tall": "height"})
        self.assertEqual(sum(len(p["items"]) for p in plates), 1)

    def test_rotation_rescues_a_part_that_only_fits_sideways(self):
        long_ = items(("bar", 240, 30))
        plates, over = PS.pack(long_, bed=(200.0, 260.0))
        self.assertFalse(over)
        self.assertEqual(plates[0]["items"][0]["rot"], 90)

    def test_layout_is_deterministic(self):
        spec = [("a", 40, 30)] * 5 + [("b", 25, 60)] * 4
        one = PS.pack(items(*spec))[0]
        two = PS.pack(items(*spec))[0]
        self.assertEqual(json.dumps(one, sort_keys=True, default=str),
                         json.dumps(two, sort_keys=True, default=str))

    def test_groups_do_not_share_a_plate(self):
        its = items(("a", 40, 40), ("b", 40, 40))
        its[0]["group"] = "solo"
        plates, _ = PS.pack(its)
        self.assertEqual(len(plates), 2)


class TestCatalog(unittest.TestCase):
    def test_every_kit_member_is_a_real_part(self):
        for kit in catalog.KITS:
            for m in kit["members"]:
                self.assertIn(m["part"], catalog.BY_ID, m["part"])

    def test_kit_shared_params_reach_every_member(self):
        # the chain set exists precisely so one cross-section drives all three
        kit = next(k for k in catalog.KITS if k["id"] == "chain_set")
        self.assertIn("dia", [p["key"] for p in kit["shared"]])
        self.assertGreaterEqual(len(kit["members"]), 3)

    def test_filenames_key_on_the_supplied_parameters(self):
        part = catalog.BY_ID["sphere_stand"]
        a = catalog.out_path(part, {"ball": 25.4})
        b = catalog.out_path(part, {"ball": 25.4, "wall": 3})
        self.assertNotEqual(a, b)
        self.assertTrue(a.endswith("ball25.4.3mf"), a)

    def test_literal_filenames_are_left_alone(self):
        p = catalog.out_path(catalog.BY_ID["dice_orb"])
        self.assertTrue(p.endswith("dice-cage.3mf"), p)

    def test_printer_profile_is_the_one_source_of_bed_size(self):
        self.assertEqual(catalog.PRINTERS["P2S"]["bed"], (256.0, 256.0))


if __name__ == "__main__":
    unittest.main()


class TestProvenance(unittest.TestCase):
    def test_every_part_declares_a_semver(self):
        import re
        for p in catalog.PARTS:
            self.assertRegex(p["version"], r"^\d+\.\d+\.\d+$", p["id"])
        for k in catalog.KITS:
            self.assertRegex(k["version"], r"^\d+\.\d+\.\d+$", k["id"])

    def test_dates_are_derived_not_declared(self):
        # a version is the author's claim; the date must come from the source
        for p in catalog.PARTS:
            self.assertNotIn("changed", p,
                             f"{p['id']} hard-codes a date instead of "
                             f"deriving it")

    def test_provenance_reports_version_change_and_build(self):
        pr = catalog.provenance(catalog.BY_ID["dice_orb"])
        self.assertEqual(pr["version"], catalog.BY_ID["dice_orb"]["version"])
        self.assertRegex(pr["changed"], r"^\d{4}-\d\d-\d\d$")
        self.assertIn("note", pr)

    def test_catalog_stamps_every_entry(self):
        c = catalog.catalog()
        for p in c["parts"]:
            self.assertIn("changed", p)
            self.assertIn("built", p)
        for k in c["kits"]:
            self.assertIn("changed", k)

    def test_a_kit_is_only_as_built_as_its_least_built_member(self):
        c = catalog.catalog()
        by = {p["id"]: p for p in c["parts"]}
        for k in c["kits"]:
            builts = [by[m["part"]]["built"] for m in k["members"]
                      if m["part"] in by]
            if all(builts):
                self.assertEqual(k["built"], min(builts))
            else:
                self.assertEqual(k["built"], "")


class TestUnifiedCatalog(unittest.TestCase):
    """A library file and a generated design must be the same kind of thing."""

    def test_library_entries_have_the_shape_of_a_part(self):
        lib = catalog.library(limit=5)
        if not lib:
            self.skipTest("no library files present")
        for p in lib:
            for field in ("id", "name", "family", "kind", "version",
                          "changed", "path"):
                self.assertIn(field, p, p.get("id"))
            self.assertEqual(p["kind"], "library")

    def test_find_resolves_generated_and_library_alike(self):
        self.assertEqual(catalog.find("dice_orb")["kind"], "generated")
        lib = catalog.library(limit=3)
        if lib:
            self.assertEqual(catalog.find(lib[0]["id"])["id"], lib[0]["id"])
        with self.assertRaises(KeyError):
            catalog.find("no_such_part")

    def test_a_library_part_needs_no_generation(self):
        lib = catalog.library(limit=3)
        if not lib:
            self.skipTest("no library files present")
        path, rep = catalog.ensure(lib[0])
        self.assertTrue(rep.get("library"))
        self.assertTrue(os.path.exists(path))

    def test_catalog_is_one_list_with_families(self):
        c = catalog.catalog()
        kinds = {p["kind"] for p in c["parts"]}
        self.assertIn("library", kinds)
        self.assertIn("generated", kinds)
        self.assertTrue(c["families"])
        # families are declared once, in order of first appearance
        self.assertEqual(len(c["families"]), len(set(c["families"])))

    def test_an_order_can_mix_kinds(self):
        lib = [p for p in catalog.library(limit=40)
               if p["path"].lower().endswith(".3mf")]
        if not lib:
            self.skipTest("no library 3MFs present")
        items, reports = PS.order_items(
            [{"part": "dice_orb", "qty": 1},
             {"part": lib[0]["id"], "qty": 1}])
        self.assertEqual(len(items), 2)
        self.assertEqual({i["key"] for i in items},
                         {"dice_orb", lib[0]["id"]})
        for it in items:
            self.assertGreater(it["w"], 0)


class TestEverythingSitsOnThePlate(unittest.TestCase):
    """Nothing may float. The bed is z=0 for every part, from any source."""

    def _scene(self, order):
        items, _ = PS.order_items(order)
        plates, over = PS.pack(items)
        self.assertFalse(over, [o["name"] for o in over])
        return PS.arranged_scene(plates)[0], items

    def test_generated_parts_are_authored_at_z0(self):
        for pid, params in (("dice_orb", {}), ("mont_double", {}),
                            ("wrench", {}), ("clasp", {"dia": 3.25})):
            part = catalog.find(pid)
            path, _ = catalog.ensure(part, params)
            import trimesh
            sc = trimesh.load(path, force="scene")
            self.assertAlmostEqual(float(sc.bounds[0][2]), 0.0, delta=0.01,
                                   msg=pid)

    def test_arranged_preview_puts_every_part_on_the_bed(self):
        # decimation moves vertices, so a part dropped before it is simplified
        # comes back proud — the preview must drop after
        sc, _ = self._scene([{"part": "dice_orb", "qty": 2},
                             {"part": "chain",
                              "params": {"links": 5, "len": 19, "dia": 3.25},
                              "qty": 2},
                             {"part": "wrench", "qty": 1}])
        by_part = {}
        for name, g in sc.geometry.items():
            key = name.rsplit("_", 1)[0]
            by_part[key] = min(by_part.get(key, 9e9), float(g.bounds[0][2]))
        for key, z in by_part.items():
            self.assertLess(z, 0.01, f"{key} floats {z:.3f} mm")

    def test_a_source_not_at_z0_is_still_placed_on_the_bed(self):
        lib = [p for p in catalog.library(limit=200)
               if p["path"].lower().endswith(".3mf")]
        import trimesh
        odd = next((p for p in lib
                    if abs(trimesh.load(p["path"],
                                        force="scene").bounds[0][2]) > 0.5),
                   None)
        if odd is None:
            self.skipTest("no library file sits off the bed")
        sc, _ = self._scene([{"part": odd["id"], "qty": 1}])
        for name, g in sc.geometry.items():
            self.assertLess(float(g.bounds[0][2]), 0.01, name)

    def test_the_wrench_fits_the_plate_with_margin(self):
        part = catalog.find("wrench")
        path, _ = catalog.ensure(part)
        m = catalog.measure(path)
        usable = 256 - 2 * PS.MARGIN
        self.assertLessEqual(m["w"] + PS.GAP, usable - 2.0,
                             "wrench leaves no margin on the plate")
