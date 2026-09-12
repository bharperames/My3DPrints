"""Nothing may serve geometry older than the code that makes it.

This app has failed this in four different places: a cached 3MF returned
forever, meshes held in memory against a path, a library index frozen at
process start, and a server running code from before the fix. Each was
invisible from the outside — the shop looked like it was working. These
tests drive the whole path a change has to travel, from editing a generator
to what lands in the downloaded plate.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile

TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools")
sys.path.insert(0, TOOLS)
import catalog  # noqa: E402
import plateshop as PS  # noqa: E402


def touch(path):
    """Make a file look newer, the way an edit does."""
    t = time.time() + 1
    os.utime(path, (t, t))


class TestAChangedGeneratorReachesTheOrder(unittest.TestCase):
    def setUp(self):
        self.gen = os.path.join(TOOLS, "gen_wrench.py")
        self.backup = self.gen + ".bak"
        shutil.copy2(self.gen, self.backup)

    def tearDown(self):
        shutil.move(self.backup, self.gen)

    def test_a_cached_part_is_rebuilt_when_its_generator_moves(self):
        part = catalog.find("wrench")
        path, first = catalog.ensure(part)
        self.assertTrue(os.path.exists(path))
        # a cached file is reused while nothing has changed
        _, again = catalog.ensure(part)
        self.assertTrue(again.get("cached"))
        # and is not once the generator does
        touch(self.gen)
        self.assertTrue(catalog.stale(part, path),
                        "a newer generator did not mark the file stale")

    def test_embed_settings_counts_as_a_source(self):
        # every generator stamps its file through embed_settings, so a change
        # there changes the output too
        part = catalog.find("wrench")
        path, _ = catalog.ensure(part)
        emb = os.path.join(TOOLS, "embed_settings.py")
        b = emb + ".bak"
        shutil.copy2(emb, b)
        try:
            touch(emb)
            self.assertTrue(catalog.stale(part, path))
        finally:
            shutil.move(b, emb)


class TestNothingIsHeldAcrossAChange(unittest.TestCase):
    def test_the_mesh_cache_notices_a_rebuild(self):
        path, _ = catalog.ensure(catalog.find("mont_double"))
        PS.load_bodies(path)
        before = PS._BODIES[path][0]
        touch(path)
        PS.load_bodies(path)
        self.assertNotEqual(PS._BODIES[path][0], before)

    def test_the_library_index_notices_an_import(self):
        # a file imported a moment ago has to be findable now, not after a
        # restart
        before = catalog._lib_stamp()
        tmp = tempfile.mkdtemp()
        keep = catalog.IMPORTED
        try:
            catalog.IMPORTED = os.path.join(tmp, "imported.json")
            with open(catalog.IMPORTED, "w") as f:
                json.dump([], f)
            self.assertNotEqual(catalog._lib_stamp(), before)
        finally:
            catalog.IMPORTED = keep
            shutil.rmtree(tmp, ignore_errors=True)


class TestWhatIsDownloadedCanBeIdentified(unittest.TestCase):
    def test_a_plate_names_its_parts_and_versions(self):
        items, _ = PS.order_items([{"part": "mont_double", "qty": 1}])
        plates, _ = PS.pack(items)
        out = tempfile.mkdtemp()
        name, man = PS.build_output(plates, out)
        with zipfile.ZipFile(os.path.join(out, name)) as z:
            meta = json.loads(z.read("Metadata/print_shop.json"))
        got = meta["parts"][0]
        self.assertEqual(got["id"], "mont_double")
        self.assertEqual(got["version"], catalog.find("mont_double")["version"])
        self.assertTrue(got["fingerprint"])
        shutil.rmtree(out, ignore_errors=True)

    def test_the_fingerprint_matches_the_generator_on_disk(self):
        import versions
        part = catalog.find("mont_double")
        fp, _ = versions.fingerprint(part)
        led, _ = versions.reconcile([part], write=False)
        self.assertEqual(led["mont_double"]["fingerprint"], fp)


class TestPreviewsCannotGoStaleInTheBrowser(unittest.TestCase):
    def test_every_preview_url_is_versioned(self):
        for p in catalog.catalog()["parts"]:
            if not p.get("preview"):
                continue          # a part is read from its own file now
            self.assertIn("?v=", p["preview"], p["id"])

    def test_the_tag_changes_when_the_source_does(self):
        a = catalog._tag("100:200")
        self.assertNotEqual(a, catalog._tag("100:201"))
        self.assertEqual(a, catalog._tag("100:200"))


class TestTheServerReloadsItsOwnCode(unittest.TestCase):
    def test_the_server_watches_every_tool_it_depends_on(self):
        sys.path.insert(0, os.path.join(TOOLS, ".."))
        import serve
        srcs = serve._sources()
        for name in ("catalog", "plateshop", "embed_settings", "versions"):
            self.assertIn(name, srcs, f"{name} is not watched")
        gens = [k for k in srcs if k.startswith("gen_")]
        self.assertGreaterEqual(len(gens), 5,
                                "the generators are not watched")

    def test_a_touched_tool_shows_up_as_changed(self):
        import serve
        before = serve._sources()
        gen = os.path.join(TOOLS, "gen_chain.py")
        b = gen + ".bak"
        shutil.copy2(gen, b)
        try:
            touch(gen)
            self.assertNotEqual(serve._sources(), before)
        finally:
            shutil.move(b, gen)


if __name__ == "__main__":
    unittest.main()
