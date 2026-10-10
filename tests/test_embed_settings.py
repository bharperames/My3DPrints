"""Unit tests for Bambu project-settings embedding."""
import json
import os
import sys
import tempfile
import unittest
import zipfile

import trimesh

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import embed_settings  # noqa: E402


def make_plain_3mf(path, centered=False):
    sc = trimesh.Scene()
    box = trimesh.creation.box(extents=[10, 10, 10])
    if not centered:
        box.apply_translation([0, 0, 5])
    sc.add_geometry(box, geom_name="cube")
    sc.export(path)


class TestEmbed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "t.3mf")
        make_plain_3mf(self.path)

    def test_embed_writes_configs_and_stamp(self):
        embed_settings.embed(self.path)
        with zipfile.ZipFile(self.path) as z:
            names = z.namelist()
            self.assertIn("Metadata/project_settings.config", names)
            self.assertIn("Metadata/model_settings.config", names)
            mdl = z.read("3D/3dmodel.model").decode()
            cfg = json.loads(z.read("Metadata/project_settings.config"))
        self.assertIn("BambuStudio:3mfVersion", mdl)
        self.assertIn("xmlns:BambuStudio", mdl)
        self.assertEqual(cfg["brim_type"], "outer_only")
        self.assertEqual(cfg["enable_support"], "0")
        self.assertEqual(cfg["curr_bed_type"], "Textured PEI Plate")

    def test_build_items_moved_to_plate_center(self):
        embed_settings.embed(self.path)
        with zipfile.ZipFile(self.path) as z:
            mdl = z.read("3D/3dmodel.model").decode()
        self.assertNotIn(
            'transform="1.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0"',
            mdl)

    def test_embed_is_idempotent_on_stamp(self):
        embed_settings.embed(self.path)
        embed_settings.embed(self.path)
        with zipfile.ZipFile(self.path) as z:
            mdl = z.read("3D/3dmodel.model").decode()
        self.assertEqual(mdl.count("BambuStudio:3mfVersion"), 1)

    def test_a_part_centered_on_z_is_stood_on_the_bed(self):
        # a project trusts stored placement: a mesh built around z=0 would
        # sit half under the bed and silently slice to half its height
        centered = os.path.join(self.tmp, "c.3mf")
        make_plain_3mf(centered, centered=True)
        embed_settings.embed(centered)
        sc = trimesh.load(centered, force="scene")
        self.assertAlmostEqual(float(sc.bounds[0][2]), 0.0, delta=0.01)

    def test_brim_is_optional(self):
        embed_settings.embed(self.path, brim=False)
        with zipfile.ZipFile(self.path) as z:
            cfg = json.loads(z.read("Metadata/project_settings.config"))
        self.assertEqual(cfg["brim_type"], "no_brim")

    def test_overrides_win(self):
        embed_settings.embed(self.path, {"brim_width": "8"})
        with zipfile.ZipFile(self.path) as z:
            cfg = json.loads(z.read("Metadata/project_settings.config"))
        self.assertEqual(cfg["brim_width"], "8")

    def test_a_named_filament_is_held_as_one_filament(self):
        """The GUI rejects a project whose one filament carries a value per
        nozzle variant ("Invalid configuration file", then no geometry);
        the CLI slices it anyway, so only this test stands in for the GUI.
        Every per-filament list must be one entry long, as the GUI saves."""
        name = "Bambu PETG Basic @BBL P2S 0.4 nozzle"
        if not os.path.exists(os.path.join(embed_settings.PRESETS, "filament",
                                           name + ".json")):
            self.skipTest("Bambu Studio's system presets are not installed")
        embed_settings.embed(self.path, filament=name)
        with zipfile.ZipFile(self.path) as z:
            cfg = json.loads(z.read("Metadata/project_settings.config"))
        own = embed_settings.flatten("filament", name)
        long_ = {k: cfg[k] for k in own
                 if isinstance(cfg.get(k), list) and len(cfg[k]) != 1}
        self.assertEqual(long_, {})
        self.assertEqual(cfg["filament_self_index"], ["1"])
        self.assertEqual(cfg["filament_settings_id"], [name])
        # the Standard nozzle's values, which is what the P2S ships with
        self.assertEqual(cfg["nozzle_temperature"], ["250"])
        self.assertEqual(cfg["filament_type"], ["PETG"])
        # preset bookkeeping stays out of the project
        for k in ("include", "compatible_printers", "description"):
            self.assertNotIn(k, cfg)


if __name__ == "__main__":
    unittest.main()
