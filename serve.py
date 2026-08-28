#!/usr/bin/env python3
"""Serve the Fidget Shelf and open models in Bambu Studio.

Usage:  python3 serve.py   →  http://localhost:8742
The page's "Open in Bambu Studio" buttons call GET /open?f=<file in models/>,
which runs `open -a BambuStudio <file>` so the real (full-resolution) model
lands in the slicer — from there: slice, then Print to the P2S.
"""
import json
import os
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))
MODELS = os.path.join(ROOT, "models")
PORT = 8742
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


def _shop_modules():
    """Imported lazily: they pull in trimesh, which is slow to load."""
    import catalog
    import plateshop
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
            out = {"ok": True, "reports": reports,
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
            if url.path == "/shop/build":
                name = "print-shop-order.zip"
                ps.build_zip(plates, os.path.join(MODELS, "custom", name),
                             oversized=over)
                out["file"] = "custom/" + name
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
            return self._json(200, {"ok": True, **cat.catalogue()})
        if url.path == "/shop/scan":
            cat, _ = _shop_modules()
            lib = cat.library()
            return self._json(200, {"ok": True, "count": len(lib),
                                    "items": lib})
        if url.path == "/generate":
            return self.do_POST()
        if url.path == "/notes":
            return self._json(200, load_notes())
        if url.path != "/open":
            return super().do_GET()
        q = parse_qs(url.query)
        fname = unquote(q.get("f", [""])[0])
        dry = q.get("dry", ["0"])[0] == "1"
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
