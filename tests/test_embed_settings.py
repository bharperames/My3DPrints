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


def make_plain_3mf(path):
    sc = trimesh.Scene()
    sc.add_geometry(trimesh.creation.box(extents=[10, 10, 10]),
                    geom_name="cube")
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

    def test_overrides_win(self):
        embed_settings.embed(self.path, {"brim_width": "8"})
        with zipfile.ZipFile(self.path) as z:
            cfg = json.loads(z.read("Metadata/project_settings.config"))
        self.assertEqual(cfg["brim_width"], "8")


if __name__ == "__main__":
    unittest.main()
