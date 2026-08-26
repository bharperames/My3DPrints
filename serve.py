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


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        url = urlparse(self.path)
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
