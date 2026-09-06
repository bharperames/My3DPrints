#!/usr/bin/env python3
"""Serve the Fidget Shelf and open models in Bambu Studio.

Usage:  python3 serve.py   →  http://localhost:8742
The page's "Open in Bambu Studio" buttons call GET /open?f=<file in models/>,
which runs `open -a BambuStudio <file>` so the real (full-resolution) model
lands in the slicer — from there: slice, then Print to the P2S.
"""
import glob
import json
import os
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))
TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools")
MODELS = os.path.join(ROOT, "models")
# Reports from /preview, keyed on the parameterised filename. The GLB itself
# is cached on disk beside the 3MF it was made from; this only saves
# re-deriving the triangle count and extents for one already built.
_PREVIEW_CACHE = {}
# The server is threaded, so two cards (or one card typed at twice) can ask
# for the same file at once. Both would run the generator into the same
# path and the loser would read a half-written 3MF.
_PREVIEW_LOCKS = {}
_PREVIEW_GATE = threading.Lock()


def _preview_lock(key):
    with _PREVIEW_GATE:
        return _PREVIEW_LOCKS.setdefault(key, threading.Lock())
# Overridable so a second copy can be run alongside the one you have
# open, rather than restarting yours to try a change.
PORT = int(os.environ.get("PORT", 8742))
APP_CANDIDATES = ["BambuStudio", "Bambu Studio"]


def find_app():
    for name in APP_CANDIDATES:
        if os.path.isdir(f"/Applications/{name}.app"):
            return name
    return None


NOTES = os.path.join(MODELS, "notes.json")


def load_notes():
    try:
        with open(NOTES) as f:
            return json.load(f)
    except Exception:
        return {}


# Reloaded in dependency order: a module that imports another must come
# after it, so that re-executing its `import` picks up the fresh one.
_SHOP_MODULES = ("designs", "embed_settings", "meshcheck", "catalog",
                 "versions", "previews", "plateshop")
_SEEN = {}


def _sources():
    """mtime of every tool the shop's answers depend on."""
    out = {}
    for name in _SHOP_MODULES:
        f = os.path.join(TOOLS, name + ".py")
        try:
            out[name] = os.path.getmtime(f)
        except OSError:
            pass
    for f in sorted(glob.glob(os.path.join(TOOLS, "gen_*.py"))):
        try:
            out[os.path.basename(f)] = os.path.getmtime(f)
        except OSError:
            pass
    return out


def _shop_modules():
    """The shop's code, reloaded if it changed under the running server.

    A long-lived process holds whatever it imported at startup. That is how
    a generator could be fixed on disk and every order still come back with
    the old geometry: the server was running code from before the fix, and
    holding meshes cached against it. Nobody is going to remember to restart
    a server after every edit, so the server notices instead.
    """
    import importlib
    import catalog
    import plateshop
    now = _sources()
    if _SEEN and now != _SEEN:
        changed = [k for k, v in now.items() if _SEEN.get(k) != v]
        print(f"reloading: {', '.join(sorted(changed))}", flush=True)
        for name in _SHOP_MODULES:
            m = sys.modules.get(name)
            if m is not None:
                importlib.reload(m)
        catalog = sys.modules["catalog"]
        plateshop = sys.modules["plateshop"]
    _SEEN.clear()
    _SEEN.update(now)
    return catalog, plateshop


class Handler(SimpleHTTPRequestHandler):
    def _read_json(self, limit=200_000):
        n = int(self.headers.get("Content-Length", 0))
        if n > limit:
            raise ValueError("payload too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        url = urlparse(self.path)
        if url.path in ("/shop/layout", "/shop/build"):
            cat, ps = _shop_modules()
            try:
                body = self._read_json()
                order = [ln for ln in body.get("order", [])
                         if int(ln.get("qty", 0)) > 0]
                if not order:
                    return self._json(400, {"ok": False,
                                            "error": "nothing selected"})
                items, reports = ps.order_items(order)
                bed = cat.PRINTERS[body.get("printer", cat.DEFAULT_PRINTER)]
                plates, over = ps.pack(items, bed=bed["bed"],
                                       height=bed["height"])
            except KeyError as e:
                return self._json(400, {"ok": False,
                                        "error": f"unknown part {e}"})
            except Exception as e:
                return self._json(422, {"ok": False, "error": str(e)[:300]})
            preview = None
            if body.get("preview") and url.path == "/shop/layout":
                name = "shop-preview.glb"
                try:
                    info = ps.build_preview(
                        plates, os.path.join(MODELS, "custom", name))
                    preview = dict(info, file="custom/" + name)
                except Exception as e:
                    preview = {"error": str(e)[:120]}
            out = {"ok": True, "reports": reports, "preview": preview,
                   "oversized": [dict(name=o["name"], reason=o["reason"])
                                 for o in over],
                   "plates": [dict(index=p["index"], util=round(p["util"], 3),
                                   items=[dict(key=i["key"], name=i["name"],
                                               x=round(i["x"], 2),
                                               y=round(i["y"], 2),
                                               w=round(i["pw"], 2),
                                               d=round(i["pd"], 2),
                                               h=round(i["h"], 2),
                                               rot=i["rot"])
                                          for i in p["items"]])
                              for p in plates],
                   "bed": bed["bed"], "margin": ps.MARGIN}
            if url.path == "/shop/import":
                cat, _ = _shop_modules()
                return self._json(200, {"ok": True, **cat.import_from()})
            if url.path == "/shop/build":
                name, man = ps.build_output(
                    plates, os.path.join(MODELS, "custom"), oversized=over)
                out["file"] = "custom/" + name
                out["single"] = name.lower().endswith(".3mf")
                out["brim"] = [m["file"] for m in man if m["brim"]]
            return self._json(200, out)
        if url.path == "/generate":
            q = parse_qs(url.query)
            kind = q.get("type", ["chain"])[0]
            try:
                if kind == "chain":
                    links = int(q["links"][0]); ln = float(q["len"][0]); dia = float(q["dia"][0])
                    fname = f"chain-N{links}-L{ln:g}-D{dia:g}.3mf"
                    args = ["gen_chain.py", "--links", str(links),
                            "--len", str(ln), "--dia", str(dia)]
                elif kind == "cage":
                    cd = float(q["dia"][0]); fr = int(q["freq"][0])
                    st = float(q["strut"][0]); ball = float(q["ball"][0])
                    fname = f"cage-D{cd:g}-F{fr}-T{st:g}-B{ball:g}.3mf"
                    args = ["gen_cage.py", "--dia", str(cd), "--freq", str(fr),
                            "--strut", str(st), "--ball", str(ball)]
                elif kind == "montessori":
                    part = q.get("part", ["double-nut"])[0]
                    if part not in ("double-nut", "plate"):
                        return self._json(400, {"ok": False, "error": "bad part"})
                    fname = ("montessori-double-nut.3mf" if part == "double-nut"
                             else "montessori-plate-2x3.3mf")
                    args = ["gen_montessori.py", "--part", part]
                elif kind == "clasp":
                    cd = float(q.get("dia", ["3.25"])[0])
                    fname = f"clasp-D{cd:g}.3mf"
                    args = ["gen_clasp.py", "--dia", str(cd)]
                elif kind == "dice":
                    # fixed design: the generator owns the geometry
                    fname = "dice-cage.3mf"
                    args = ["gen_dice_cage.py"]
                else:
                    return self._json(400, {"ok": False, "error": "unknown type"})
            except Exception:
                return self._json(400, {"ok": False, "error": "bad params"})
            out = os.path.join(MODELS, "custom", fname)
            if os.path.exists(out):
                return self._json(200, {"ok": True, "file": "custom/" + fname, "cached": True})
            py = os.path.expanduser("~/.claude/skills/3d-print-check/.venv/bin/python")
            if not os.path.exists(py):
                py = "python3"
            r = subprocess.run([py, os.path.join(ROOT, "tools", args[0])]
                               + args[1:] + ["--out", out],
                               capture_output=True, text=True, timeout=300)
            try:
                j = json.loads(r.stdout.strip().splitlines()[-1])
            except Exception:
                return self._json(500, {"ok": False, "error": (r.stderr or "generator failed")[-300:]})
            if j.get("ok"):
                j["file"] = "custom/" + fname
            return self._json(200 if j.get("ok") else 422, j)
        if url.path == "/rebuild":
            r = subprocess.run(["make", "build"], cwd=ROOT, capture_output=True,
                               text=True, timeout=900)
            tail = (r.stdout + r.stderr)[-1200:]
            return self._json(200 if r.returncode == 0 else 500,
                              {"ok": r.returncode == 0, "log": tail})
        if url.path != "/notes":
            return self._json(404, {"ok": False})
        n = int(self.headers.get("Content-Length", 0))
        if n > 100_000:
            return self._json(413, {"ok": False, "error": "too large"})
        try:
            body = json.loads(self.rfile.read(n))
            cid, text = str(body["cid"])[:64], str(body["text"])[:2000].strip()
            assert text
        except Exception:
            return self._json(400, {"ok": False, "error": "bad request"})
        import datetime
        notes = load_notes()
        notes.setdefault(cid, []).append(
            {"date": datetime.date.today().isoformat(), "text": text})
        with open(NOTES, "w") as f:
            json.dump(notes, f, indent=1)
        self._json(200, {"ok": True, "notes": notes[cid]})

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/shop/catalog":
            cat, _ = _shop_modules()
            return self._json(200, {"ok": True, **cat.catalog()})
        if url.path == "/shop/scan":
            cat, _ = _shop_modules()
            found = cat.scan()
            have = set(cat.imported())
            return self._json(200, {
                "ok": True, "count": len(found),
                "new": sum(1 for p in found if p["path"] not in have),
                "imported": len(have),
                "items": [p["name"] for p in found[:40]]})
        if url.path == "/generate":
            return self.do_POST()
        if url.path == "/notes":
            return self._json(200, load_notes())
        if url.path == "/preview":
            # A dial that moves the geometry has to move the picture too.
            # The card's own GLB is built once from the defaults, so before
            # this a part could be ordered at one code and previewed at
            # another. The 3MF is already keyed on its parameters, so the
            # GLB beside it is keyed the same way and both survive a reload.
            q = parse_qs(url.query)
            pid = unquote(q.get("id", [""])[0])
            try:
                params = json.loads(unquote(q.get("params", ["{}"])[0]) or "{}")
            except ValueError:
                params = {}
            cat, _ = _shop_modules()
            try:
                part = cat.find(pid)
            except KeyError:
                return self._json(404, {"ok": False, "error": "unknown part"})
            try:
                src = cat.ensure(part, params or cat.defaults(part))[0]
            except Exception as e:                          # noqa: BLE001
                return self._json(400, {"ok": False, "error": str(e)})
            import previews
            slug = "live-" + os.path.splitext(os.path.basename(src))[0]
            dest = os.path.join(MODELS, "glb", "prev", slug + ".glb")
            with _preview_lock(slug):
                rep = _PREVIEW_CACHE.get(slug)
                if (rep is None or not os.path.exists(dest)
                        or os.path.getmtime(dest) < os.path.getmtime(src)):
                    try:
                        # tile=False: this file's own arrangement is the
                        # answer. A set of coded discs is laid out on the
                        # bed by the generator, and re-tiling it here would
                        # show a plate this app invented — 190 x 269 for a
                        # set that is 220 square and fits.
                        rep = previews.build_one(slug, src, tile=False,
                                                 probe=False)
                    except Exception as e:                  # noqa: BLE001
                        return self._json(500, {"ok": False,
                                                "error": str(e)})
                    _PREVIEW_CACHE[slug] = rep
            return self._json(200, {
                "ok": True, "glb": rep["glb"], "dims": rep["dims"],
                "tris": rep["tris"], "bodies": rep["bodies"],
                "stamp": int(os.path.getmtime(dest))})
        if url.path != "/open":
            return super().do_GET()
        q = parse_qs(url.query)
        fname = unquote(q.get("f", [""])[0])
        pid = unquote(q.get("id", [""])[0])
        dry = q.get("dry", ["0"])[0] == "1"
        if pid:
            # A catalog part, opened by id: the shop can hand any entry to
            # the slicer, including a generated one that has to be built
            # first and a file that lives outside models/.
            cat, _ = _shop_modules()
            try:
                part = cat.find(pid)
            except KeyError:
                return self._json(404, {"ok": False, "error": "unknown part"})
            try:
                params = json.loads(unquote(q.get("params", ["{}"])[0]) or "{}")
            except ValueError:
                params = {}
            try:
                path = os.path.realpath(cat.ensure(
                    part, params or cat.defaults(part))[0])
            except Exception as e:                          # noqa: BLE001
                return self._json(500, {"ok": False, "error": str(e)})
            ok = os.path.isfile(path)
        else:
            path = os.path.realpath(os.path.join(MODELS, fname))
            ok = (path.startswith(os.path.realpath(MODELS) + os.sep)
                  and os.path.isfile(path)
                  and path.lower().endswith((".3mf", ".stl")))
        app = find_app()
        if not ok:
            return self._json(400, {"ok": False, "error": "unknown file"})
        if app is None:
            return self._json(501, {"ok": False, "error": "Bambu Studio not found in /Applications"})
        if not dry:
            subprocess.Popen(["open", "-a", app, path])
        self._json(200, {"ok": True, "app": app, "file": os.path.basename(path), "dry": dry})

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if "/open" in (args[0] if args else ""):
            sys.stderr.write(fmt % args + "\n")


if __name__ == "__main__":
    os.chdir(ROOT)
    app = find_app()
    print(f"Fidget Shelf →  http://localhost:{PORT}")
    print(f"Bambu Studio: {'found (' + app + '.app)' if app else 'NOT FOUND — print buttons will explain'}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
