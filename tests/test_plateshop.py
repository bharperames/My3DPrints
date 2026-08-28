"""Unit tests for the plate packer and the shop catalogue."""
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


class TestCatalogue(unittest.TestCase):
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

    def test_catalogue_stamps_every_entry(self):
        c = catalog.catalogue()
        for p in c["parts"]:
            self.assertIn("changed", p)
            self.assertIn("built", p)
        for k in c["kits"]:
            self.assertIn("changed", k)

    def test_a_kit_is_only_as_built_as_its_least_built_member(self):
        c = catalog.catalogue()
        by = {p["id"]: p for p in c["parts"]}
        for k in c["kits"]:
            builts = [by[m["part"]]["built"] for m in k["members"]
                      if m["part"] in by]
            if all(builts):
                self.assertEqual(k["built"], min(builts))
            else:
                self.assertEqual(k["built"], "")
