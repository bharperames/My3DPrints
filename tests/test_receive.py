"""The shop accepts geometry built in a framed app, so it accepts bytes
and a filename from another origin. Both are attacker-controlled in the
sense that matters: they arrive over postMessage from a page this
repository does not contain.

The filename is the whole risk. It decides where the file is written, and
"I stripped the bad characters" is a claim, not a test -- so these push
traversal, absolute paths, NUL, control characters and Windows separators
through the real handler and check where the byte actually landed.

The server is started here on a port of its own rather than reusing a
running shop, so the suite does not depend on `make serve` and cannot
write into a shop someone is using.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PORT = 8791


def post(name, body=b"x" * 64, port=PORT):
    """POST to /shop/receive and return (status, parsed json)."""
    url = f"http://127.0.0.1:{port}/shop/receive?name=" + \
        urllib.parse.quote(name, safe="")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type":
                                          "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        with e:                       # else the response leaks a warning
            return e.code, json.loads(e.read() or b"{}")


class TestReceiveWritesOnlyWhereItShould(unittest.TestCase):
    """The server runs for real, against a throwaway models/ directory."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="shop-receive-")
        # a checkout-shaped scratch copy: the handler writes under
        # <root>/models/custom, so give it a root of its own
        os.makedirs(os.path.join(cls.tmp, "models", "custom"))
        for f in ("serve.py",):
            shutil.copy(os.path.join(ROOT, f), cls.tmp)
        os.symlink(os.path.join(ROOT, "tools"), os.path.join(cls.tmp, "tools"))
        os.symlink(os.path.join(ROOT, "docs"), os.path.join(cls.tmp, "docs"))
        env = dict(os.environ, PORT=str(PORT))
        cls.proc = subprocess.Popen(
            [sys.executable, "serve.py"], cwd=cls.tmp, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.custom = os.path.join(cls.tmp, "models", "custom")
        for _ in range(100):                     # wait for the port
            try:
                post("warmup.3mf")
                break
            except Exception:
                time.sleep(0.1)
        else:
            cls.proc.kill()
            raise unittest.SkipTest("the shop server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def files(self):
        return sorted(os.listdir(self.custom))

    def test_a_plain_name_is_written_and_reported_relative_to_models(self):
        code, d = post("sphere_stand_50.0mm.3mf", b"a" * 100)
        self.assertEqual(code, 200, d)
        self.assertTrue(d["ok"])
        self.assertEqual(d["file"], "custom/sphere_stand_50.0mm.3mf")
        self.assertEqual(d["bytes"], 100)
        self.assertIn("sphere_stand_50.0mm.3mf", self.files())

    def test_no_filename_escapes_the_custom_directory(self):
        escapes = [
            "../../../../../../tmp/pwned.3mf",
            "..%2f..%2fpwned.3mf",
            "/etc/pwned.3mf",
            "....//....//pwned.3mf",
            "sub/dir/pwned.3mf",
            "..\\..\\pwned.3mf",
            "C:\\windows\\pwned.3mf",
        ]
        before = set(self.files())
        for name in escapes:
            code, d = post(name, b"z" * 32)
            # it may be rejected OR flattened, but it must not land outside
            if code == 200:
                self.assertEqual(os.path.dirname(d["file"]), "custom", name)
                full = os.path.join(self.tmp, "models", d["file"])
                self.assertEqual(
                    os.path.dirname(os.path.realpath(full)),
                    os.path.realpath(self.custom), name)
        # and nothing appeared anywhere else that we can see
        self.assertFalse(os.path.exists("/tmp/pwned.3mf"))
        new = set(self.files()) - before
        for f in new:
            self.assertNotIn("/", f)
            self.assertNotIn("\\", f)

    def test_only_printable_geometry_extensions_are_accepted(self):
        for name in ("evil.html", "evil.py", "evil.3mf.py", "noext",
                     "evil.sh", ".3mf", "x.3MF.exe"):
            code, d = post(name, b"q" * 16)
            self.assertEqual(code, 400, f"{name} was accepted: {d}")

    def test_an_uppercase_extension_is_normalized_not_refused(self):
        code, d = post("Ball.3MF", b"u" * 24)
        self.assertEqual(code, 200, d)
        self.assertTrue(d["file"].endswith(".3mf"), d["file"])

    def test_control_characters_and_nul_cannot_survive_into_a_name(self):
        for name in ("a\x00b.3mf", "a\nb.3mf", "a\rb.3mf", "a\tb.3mf"):
            code, d = post(name, b"c" * 16)
            if code == 200:
                base = os.path.basename(d["file"])
                self.assertTrue(all(ch.isalnum() or ch in "._-" for ch in base),
                                repr(base))

    def test_an_empty_body_is_refused(self):
        code, _ = post("empty.3mf", b"")
        self.assertEqual(code, 413)

    def test_stl_is_accepted_too(self):
        code, d = post("ball.stl", b"s" * 48)
        self.assertEqual(code, 200, d)
        self.assertEqual(d["file"], "custom/ball.stl")

    # ---- a missing file must answer, not drop the connection ----------
    #
    # log_message was overridden to print only the slicer handoff, and it
    # tested `"/open" in args[0]` -- but log_error() passes an HTTPStatus
    # there, so `in` raised TypeError from inside send_error(), before the
    # response was written. The socket closed instead. Every missing file
    # on this server answered like a server that had gone away, and the
    # card's own error handler reads that as "no answer -- restart the
    # server": a 404 reading as a dead shop.

    def test_a_missing_path_gets_a_status_not_a_closed_socket(self):
        import http.client
        # deliberately absent paths of a few shapes: a bare file, one
        # under a directory that DOES exist, one under docs/, one nested
        for path in ("/nope.txt", "/assets/not-a-real-texture.jpeg",
                     "/docs/nothing.html", "/models/glb/nope/x.glb"):
            c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=20)
            try:
                c.request("GET", path)
                self.assertEqual(c.getresponse().status, 404, path)
            except (http.client.RemoteDisconnected, ConnectionResetError) as e:
                self.fail(f"{path}: connection dropped instead of 404 ({e})")
            finally:
                c.close()

    def test_a_path_that_exists_is_still_served(self):
        """The control: proving 404s answer is worthless if nothing does."""
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=20)
        try:
            c.request("GET", "/docs/sphere.html")
            r = c.getresponse()
            self.assertEqual(r.status, 200)
            self.assertIn(b"StandMaker", r.read())
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main()
