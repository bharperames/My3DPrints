#!/usr/bin/env python3
"""The Print Shop catalogue: everything this machine knows how to print.

Three kinds of entry, deliberately uniform so the shop UI and the plate
packer never care which is which:

  generated   a fixed design this repo builds from source (dice orb,
              coupler nut, plate board). No knobs; one canonical file.
  parametric  a design with dials and a live preview (chain, sphere
              stand, cage). Parameters key the generated file.
  library     a file found on disk — scanned out of ~/Downloads or sitting
              in models/ — indexed, measured, and printable as-is.

Every entry resolves to a 3MF on disk plus a measured footprint, which is
all the packer needs. Anything the packer cannot measure is not sellable.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODELS = os.path.join(ROOT, "models")
CUSTOM = os.path.join(MODELS, "custom")
PY = os.path.expanduser("~/.claude/skills/3d-print-check/.venv/bin/python")
if not os.path.exists(PY):
    PY = sys.executable

# printer profile — one machine for now, but the shop reads it from here
# rather than hard-coding 256 in a dozen places
PRINTERS = {
    "P2S": dict(name="Bambu Lab P2S", bed=(256.0, 256.0), height=256.0,
                nozzle=0.4, exclude=[]),
}
DEFAULT_PRINTER = "P2S"


def _p(pid, name, family, kind, blurb, **kw):
    return dict(id=pid, name=name, family=family, kind=kind, blurb=blurb, **kw)


# --- kits: parts whose sizes must agree to interoperate ------------------
# A kit owns the parameters that decide fit. The chain's cross-section sets
# the clasp's mouth and the jump ring's section, so ordering a chain and a
# clasp at different diameters is not a choice the shop should offer.
KITS = [
    dict(id="chain_set", name="Chain Set", family="Designed here",
         blurb="Chain, clasp and jump rings. One cross-section drives all "
               "three: it sets the link, the clasp's mouth and the ring's "
               "section, so the parts can only be ordered as a matched set.",
         shared=[dict(key="dia", label="cross-section", unit="mm", min=2,
                      max=8, step=0.25, val=3.25)],
         members=[
             dict(part="chain", label="Chain",
                  own=[dict(key="links", label="links", min=2, max=25,
                            step=1, val=5),
                       dict(key="len", label="link length", unit="mm",
                            min=14, max=60, step=1, val=19)]),
             dict(part="clasp", label="Lobster clasp"),
             dict(part="jump_ring", label="Jump ring"),
         ]),
    dict(id="montessori", name="Montessori Nuts & Bolts", family="Montessori",
         blurb="Companions for the Montessori set. The thread is cast from "
               "the designer's own nut, so every piece mates with the "
               "original bolts and with each other.",
         shared=[],
         members=[
             dict(part="mont_double", label="Double nut (coupler)"),
             dict(part="mont_plate", label="Base plate 2×3"),
         ]),
]

# --- parts: each resolves to one 3MF on disk -----------------------------
PARTS = [
    _p("dice_orb", "Dice Orb", "Designed here", "generated",
       "A standard d20 captive in a rib-and-ring shaker sphere.",
       gen=["gen_dice_cage.py"], out="dice-cage.3mf", proven=True),
    _p("mont_double", "Double Nut (coupler)", "Montessori", "generated",
       "Joins two Montessori bolts end to end.",
       gen=["gen_montessori.py", "--part", "double-nut"],
       out="montessori-double-nut.3mf"),
    _p("mont_plate", "Base Plate 2×3", "Montessori", "generated",
       "Six threaded sockets to stand the bolts in.",
       gen=["gen_montessori.py", "--part", "plate"],
       out="montessori-plate-2x3.3mf"),
    _p("clasp", "Lobster Clasp", "Designed here", "generated",
       "Flexure-gate clasp, sized to the chain it ends.",
       gen=["gen_clasp.py", "--part", "clasp"], out="clasp-only-D{dia:g}.3mf"),
    _p("jump_ring", "Jump Ring", "Designed here", "generated",
       "Butt C-ring that threads the link bore and the clasp's eye.",
       gen=["gen_clasp.py", "--part", "ring"], out="ring-only-D{dia:g}.3mf"),
    _p("chain", "Chain", "Designed here", "parametric",
       "Print-in-place stadium links, any length.",
       gen=["gen_chain.py"],
       out="chain-N{links}-L{len:g}-D{dia:g}.3mf"),
    _p("sphere_stand", "Sphere Stand", "Sphere Stands", "parametric",
       "A ring that cradles a ball on a conformal spherical seat. Leave the "
       "last three blank and they follow the ball at a 45 deg contact.",
       gen=["gen_sphere_stand.py"], params=[
           dict(key="ball", label="ball", unit="mm", min=8, max=120,
                step=0.5, val=25.4),
           dict(key="wall", label="wall", unit="mm", min=1.2, max=12,
                step=0.1, val=2.5),
           dict(key="chamfer", label="rim chamfer", unit="mm", min=0, max=8,
                step=0.1, val=0.8),
           dict(key="seat", label="air gap", unit="mm", min=0.4, max=12,
                step=0.1, val=1.0)],
       out="sphere-stand"),
    _p("cage", "Geodesic Cage", "Designed here", "parametric",
       "Strut sphere, optionally with a captive ball.",
       gen=["gen_cage.py"], params=[
           dict(key="dia", label="cage O", unit="mm", min=30, max=90,
                step=2, val=50),
           dict(key="freq", label="frequency", min=1, max=6, step=1, val=2),
           dict(key="strut", label="strut O", unit="mm", min=1.4, max=4.5,
                step=0.2, val=2.2),
           dict(key="ball", label="ball O (0 = none)", unit="mm", min=0,
                max=40, step=1, val=19)],
       out="cage-D{dia:g}-F{freq}-T{strut:g}-B{ball:g}.3mf"),
]
BY_ID = {p["id"]: p for p in PARTS}


def _fmt(v):
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


def out_path(part, params=None):
    """Where this part's 3MF lives, given its parameters.

    A name ending in .3mf is literal. Anything else is a stem, and the
    supplied parameters make the suffix — so a part whose defaults are
    derived (the sphere stand computes base, wall and chamfer from the ball)
    keys its file on what was actually asked for, not on a fixed template.
    """
    name, params = part["out"], params or {}
    if not name.endswith(".3mf"):
        sfx = "-".join(f"{k}{_fmt(v)}" for k, v in sorted(params.items()))
        name = f"{name}-{sfx}.3mf" if sfx else f"{name}.3mf"
    elif "{" in name:
        name = name.format(**params)
    return os.path.join(CUSTOM, name)


def ensure(part, params=None, timeout=600):
    """Generate the part's file if it is not already on disk.

    Returns (path, report). Raises RuntimeError with the generator's own
    message when a design gate refuses the parameters.
    """
    path = out_path(part, params)
    if os.path.exists(path):
        return path, {"cached": True}
    cmd = [PY, os.path.join(HERE, part["gen"][0])] + part["gen"][1:]
    for k, v in (params or {}).items():
        cmd += [f"--{k}", str(v)]
    cmd += ["--out", path]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    try:
        rep = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        raise RuntimeError((r.stderr or "generator failed")[-300:])
    if not rep.get("ok"):
        raise RuntimeError(rep.get("error", "generation refused"))
    return path, rep


def measure(path):
    """Footprint and height of a 3MF, in mm — what the packer needs."""
    import trimesh
    sc = trimesh.load(path, force="scene")
    lo, hi = sc.bounds
    return dict(w=float(hi[0] - lo[0]), d=float(hi[1] - lo[1]),
                h=float(hi[2] - lo[2]))


def library(dirs=None, limit=400):
    """Index printable files sitting on disk (the ad-hoc shelf)."""
    dirs = dirs or [os.path.expanduser("~/Downloads"), MODELS]
    seen, out = set(), []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            if "/glb" in root or "/meta" in root or "/index_out" in root:
                continue
            for fn in sorted(files):
                if not fn.lower().endswith((".3mf", ".stl")):
                    continue
                p = os.path.join(root, fn)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                key = (fn.lower(), st.st_size)
                if key in seen:
                    continue
                seen.add(key)
                out.append(_p(
                    "lib_" + str(abs(hash(p)) % (10 ** 10)),
                    os.path.splitext(fn)[0].replace("+", " "),
                    "Library", "library", "",
                    path=p, size=st.st_size, mtime=st.st_mtime,
                    where="Downloads" if "Downloads" in root else "models"))
                if len(out) >= limit:
                    return out
    return out


def catalogue():
    return {"printers": PRINTERS, "printer": DEFAULT_PRINTER,
            "kits": KITS, "parts": PARTS}


if __name__ == "__main__":
    c = catalogue()
    print(json.dumps({"kits": [(k["id"], [m["part"] for m in k["members"]])
                               for k in c["kits"]],
                      "parts": [p["id"] for p in c["parts"]],
                      "library_found": len(library())}, indent=1))
