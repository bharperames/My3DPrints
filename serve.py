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
from urllib.parse import urlparse, parse_qs, unquote, quote

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


_socket_cache = {}


def _genus(m):
    """Through-holes in a closed solid, from Euler's V - E + F = 2 - 2g.

    Only meaningful when the mesh is watertight; callers check that first.
    """
    return (2 - (len(m.vertices) - len(m.edges_unique) + len(m.faces))) // 2


class Handler(SimpleHTTPRequestHandler):
    # Pages here are edited and reloaded all day, and SimpleHTTPRequestHandler
    # sends no Cache-Control at all -- so a browser falls back to heuristic
    # freshness, 10% of the file's age, and keeps an hours-old copy of a page
    # that changed a minute ago. That is not theoretical: docs/tooth-stand.html
    # went on reporting a part that had been removed from the catalog, from a
    # copy in the browser, while the file on disk and the server's own answer
    # were both correct.
    def end_headers(self):
        path = urlparse(self.path).path
        if path.endswith((".html", ".js", ".css", ".json")) or path == "/":
            self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()

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
        if url.path == "/socket":
            return self._socket(parse_qs(url.query))
        if url.path == "/diff":
            return self._diff(parse_qs(url.query))
        if url.path == "/rings":
            return self._rings(parse_qs(url.query))
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
        if url.path == "/src":
            # The real geometry, by part id. The page used to render a GLB
            # built beside every 3MF -- three hundred and fifty megabytes of
            # it, the same size as the sources it was made from, and a cache
            # that had to be kept in step with them. There is no need: the
            # browser can read the 3MF and the STL. This exists because a
            # library file may live outside the repo (imported out of
            # ~/Downloads) and so cannot be reached by a static path.
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
                src = (part["path"] if part["kind"] == "library"
                       else cat.ensure(part, params or cat.defaults(part))[0])
            except Exception as e:                          # noqa: BLE001
                return self._json(400, {"ok": False, "error": str(e)})
            if not os.path.isfile(src):
                return self._json(404, {"ok": False, "error": "no file"})
            ext = os.path.splitext(src)[1].lower()
            kind = {".3mf": "model/3mf", ".stl": "model/stl",
                    ".glb": "model/gltf-binary"}.get(ext, "application/octet-stream")
            data = open(src, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Source-Name", os.path.basename(src))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
            return

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
            with _preview_lock(slug):
                rep = _PREVIEW_CACHE.get(slug)
                if rep is None or rep.get("src_mtime") != os.path.getmtime(src):
                    try:
                        # tile=False: this file's own arrangement is the
                        # answer. A set of coded discs is laid out on the
                        # bed by the generator, and re-tiling it here would
                        # show a plate this app invented — 190 x 269 for a
                        # set that is 220 square and fits.
                        # write=False: the page reads the 3MF this just
                        # built, so a GLB beside it would be a second copy
                        # of the same geometry made for nobody. Eighty
                        # megabytes of those had accumulated, one per dial
                        # position anyone had ever tried.
                        rep = previews.build_one(slug, src, tile=False,
                                                 probe=False, write=False)
                        rep["src_mtime"] = os.path.getmtime(src)
                    except Exception as e:                  # noqa: BLE001
                        return self._json(500, {"ok": False,
                                                "error": str(e)})
                    _PREVIEW_CACHE[slug] = rep
            return self._json(200, {
                "ok": True, "dims": rep["dims"], "tris": rep["tris"],
                "bodies": rep["bodies"],
                "src": "/src?id=" + pid + "&params=" +
                       quote(json.dumps(params or cat.defaults(part))),
                "ext": os.path.splitext(src)[1].lower().lstrip("."),
                "stamp": int(os.path.getmtime(src))})
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

    def _bin(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _socket(self, q):
        """Cut the gum sockets with the dials the viewer is holding.

        The whole point is that this answers fast enough to drag a slider
        against. Two things make that possible: the source mesh is parsed
        once and kept (1.8 s on the body, every time, otherwise), and
        `deburr` is off -- it is 84% of a build and a preview does not need
        it. Anything headed for a plate is built again with it on.

        Only the jaw comes back, not the whole animal: a body is 767k faces
        and 30 MB of GLB, and the 28 mm around the gum line is both the part
        being judged and a twentieth of the size.
        """
        import io, time
        t0 = time.time()
        part = (q.get("part", ["body"])[0])
        if part not in ("skull", "body"):
            return self._json(400, {"ok": False, "error": f"unknown part {part}"})
        try:
            d = float(q.get("depth", [3.5])[0])
        except ValueError:
            return self._json(400, {"ok": False, "error": "bad number"})
        try:
            import numpy as np, trimesh
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))
            import gen_trex as G
            from channel import tooth_frames, gum_path
            from scipy.spatial import cKDTree
            cache = _socket_cache.setdefault(part, {})
            if "src" not in cache:
                member = "head" if part == "skull" else "body"
                src, paint = G.load(G.OBJ[member]); src = G.tidy(src)
                regions = (G.painted_regions(src, paint) if part == "skull"
                           else G.jaw_regions(src, paint))
                C, N, A, U = gum_path(src, tooth_frames(src, regions))
                # measure against the part with the TEETH ALREADY OFF, or
                # "removed" counts the teeth and reads ~1000 mm3 high
                hulls = [src.submesh([r], append=True).convex_hull for r in regions]
                base = trimesh.boolean.difference(
                    [src, trimesh.boolean.union(hulls, engine="manifold")],
                    engine="manifold")
                # The baseline has to go through the SAME pipeline as the
                # build it is compared against. `keep_real` drops the two
                # inverted zero-volume shells the designer's body carries,
                # and dropping them shifts the Euler count by two -- so a raw
                # baseline made every body cut look like it had punched a
                # pair of tunnels it never touched.
                cache.update(src=src, paint=paint, regions=regions,
                             tree=cKDTree(C), vol0=float(base.volume),
                             genus0=_genus(G.keep_real(
                                 base, single=(part == "skull"))))
            c = cache
            scrub = q.get("scrub", ["0"])[0] not in ("0", "", "false")
            # Each part's OWN defaults, so the bench opens on the part the
            # plate build would make rather than on the skull's numbers.
            dflt = (dict(depth=3.5, lingual=1.0, ling_depth=3.0, ling_wall=1.2)
                    if part == "skull" else
                    dict(depth=2.5, lingual=2.5, ling_depth=2.75, ling_wall=0.6))
            g = lambda k, d: float(q.get(k, [d])[0])
            kw = dict(inset=g("inset", 0.35), grow=g("grow", 0.0),
                      lean=g("lean", 0.0), align=g("align", 1.0),
                      lingual=g("lingual", dflt["lingual"]),
                      ling_depth=g("ling_depth", dflt["ling_depth"]),
                      ling_wall=g("ling_wall", dflt["ling_wall"]))
            items, rep = G.build([part if part == "skull" else "body"],
                                 depth_max=d, scrub=scrub, **kw)
            m = items[0][1]
            keep = np.where(c["tree"].query(m.triangles_center)[0] < 26.0)[0]
            crop = m.submesh([keep], append=True)
            buf = trimesh.exchange.gltf.export_glb(trimesh.Scene(crop))
            # Watertightness and genus cost ~20 ms on an 80k-face skull --
            # both read the same edge-adjacency table, which trimesh builds
            # once and caches -- against seconds for the cut itself. Genus
            # counts the solid's through-holes, so `tunnels` is how many the
            # cutter made that the designer did not, and a socket that leaves
            # through the side wall shows up here and nowhere else.
            #
            # It is reported ONLY when the mesh is watertight: Euler's
            # V-E+F = 2-2g holds for a closed surface and nothing else, so on
            # an open mesh the same arithmetic returns a number that is not a
            # tunnel count and can read clean while the part is torn.
            tight = bool(m.is_watertight)
            meta = {"removed": round(c["vol0"] - float(m.volume), 1),
                    "faces": len(crop.faces), "ms": int(1000 * (time.time() - t0)),
                    "bodies": len(m.split(only_watertight=False)),
                    "watertight": tight,
                    "tunnels": (_genus(m) - c["genus0"]) if tight else None,
                    "scrub": bool(scrub)}
            return self._bin(200, buf, "model/gltf-binary",
                             {"X-Meta": json.dumps(meta)})
        except Exception as e:                              # noqa: BLE001
            return self._json(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    def _diff(self, q):
        """What the current dials changed, against a pinned reference.

        Two cuts, two subtractions: REF minus CUR is material the reference
        still had and this one takes away; CUR minus REF is material this one
        leaves that the reference had removed. Returned as two named
        geometries so the page can colour them without guessing -- doing it
        by vertex distance in the browser would shade a surface rather than
        show the solid that changed.
        """
        import io, json as _json, time
        t0 = time.time()
        part = q.get("part", ["body"])[0]
        if part not in ("skull", "body"):
            return self._json(400, {"ok": False, "error": f"unknown part {part}"})
        try:
            a = _json.loads(unquote(q.get("ref", ["{}"])[0]) or "{}")
            b = _json.loads(unquote(q.get("cur", ["{}"])[0]) or "{}")
        except ValueError:
            return self._json(400, {"ok": False, "error": "bad params"})
        try:
            import numpy as np, trimesh
            sys.path.insert(0, os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "tools"))
            import gen_trex as G
            from channel import tooth_frames, gum_path
            from scipy.spatial import cKDTree
            cache = _socket_cache.setdefault(part, {})
            if "tree" not in cache:
                member = "head" if part == "skull" else "body"
                src, paint = G.load(G.OBJ[member]); src = G.tidy(src)
                regions = (G.painted_regions(src, paint) if part == "skull"
                           else G.jaw_regions(src, paint))
                C, N, A, U = gum_path(src, tooth_frames(src, regions))
                cache.update(tree=cKDTree(C))
            def build(kw):
                items, _ = G.build([part], scrub=False, **kw)
                return items[0][1]
            ma, mb = build(a), build(b)
            gone = trimesh.boolean.difference([ma, mb], engine="manifold")
            kept = trimesh.boolean.difference([mb, ma], engine="manifold")
            sc = trimesh.Scene()
            meta = {"ms": 0, "gone": 0.0, "kept": 0.0}
            tree = cache["tree"]
            for name, m in (("gone", gone), ("kept", kept)):
                if m is None or m.volume <= 1e-6: continue
                meta[name] = round(float(m.volume), 1)
                keep = np.where(tree.query(m.triangles_center)[0] < 26.0)[0]
                if not len(keep): continue
                sc.add_geometry(m.submesh([keep], append=True), geom_name=name)
            if not len(sc.geometry):
                return self._json(200, {"ok": True, "empty": True})
            buf = trimesh.exchange.gltf.export_glb(sc)
            meta["ms"] = int(1000 * (time.time() - t0))
            return self._bin(200, buf, "model/gltf-binary",
                             {"X-Meta": json.dumps(meta)})
        except Exception as e:                              # noqa: BLE001
            return self._json(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    def _rings(self, q):
        """The designer's own tooth boundaries, as ordered loops.

        Where a tooth-painted triangle meets a bone-painted one is the true
        socket outline -- it is what every frame, axis and radius in the
        cutter is derived from, so it is worth being able to see it against
        what the cutter actually did. `tooth_frames` keeps these points but
        runs them through np.unique, which throws the order away; a loop has
        to be walked in order to be drawn.
        """
        part = q.get("part", ["body"])[0]
        if part not in ("skull", "body"):
            return self._json(400, {"ok": False, "error": f"unknown part {part}"})
        try:
            import numpy as np
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))
            import gen_trex as G
            cache = _socket_cache.setdefault(part, {})
            if "rings" not in cache:
                member = "head" if part == "skull" else "body"
                src, paint = G.load(G.OBJ[member]); src = G.tidy(src)
                regions = (G.painted_regions(src, paint) if part == "skull"
                           else G.jaw_regions(src, paint))
                loops = []
                for faces in regions:
                    sub = src.submesh([faces], append=True); sub.merge_vertices()
                    ents = list(sub.outline().entities)
                    if not ents: continue
                    e = max(ents, key=lambda x: len(x.points))
                    pts = sub.vertices[np.asarray(e.points)]
                    loops.append([[round(float(v), 4) for v in p] for p in pts])
                cache["rings"] = loops
            return self._json(200, {"ok": True, "rings": cache["rings"]})
        except Exception as e:                              # noqa: BLE001
            return self._json(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):
        if "/open" in (args[0] if args else ""):
            sys.stderr.write(fmt % args + "\n")


if __name__ == "__main__":
    os.chdir(ROOT)
    app = find_app()
    print(f"Fidget Shelf →  http://localhost:{PORT}")
    print(f"Bambu Studio: {'found (' + app + '.app)' if app else 'NOT FOUND — print buttons will explain'}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
