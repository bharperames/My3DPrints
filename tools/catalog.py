#!/usr/bin/env python3
"""The Print Shop catalog: everything this machine knows how to print.

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
import hashlib
import json
import os
import re
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


def _p(pid, name, family, kind, blurb, version="0.1.0", **kw):
    """A catalog entry. `version` is declared, not derived: only an author
    knows whether a change is a new design, a reshape, or a fix. The date
    beside it is derived from git, so it cannot drift out of step."""
    return dict(id=pid, name=name, family=family, kind=kind, blurb=blurb,
                version=version, **kw)


# --- kits: parts whose sizes must agree to interoperate ------------------
# A kit owns the parameters that decide fit. The chain's cross-section sets
# the clasp's mouth and the jump ring's section, so ordering a chain and a
# clasp at different diameters is not a choice the shop should offer.
KITS = [
    dict(id="chain_set", version="1.1.0", name="Chain Set",
         family="Designed here",
         blurb="Chain, clasp and jump rings. One cross-section drives all "
               "three: it sets the link, the clasp's mouth and the ring's "
               "section, so the parts can only be ordered as a matched set.",
         shared=[dict(key="dia", label="cross-section", unit="mm", min=2,
                      max=8, step=0.25, val=3.25)],
         members=[
             dict(part="chain", label="Chain",
                  own=[dict(key="links", label="links", min=2, max=100,
                            step=1, val=5),
                       dict(key="len", label="link length", unit="mm",
                            min=14, max=60, step=1, val=19),
                       # a round tube meets the bed on a line and the slicer
                       # lays a single bead per link; the flat gives it a pad
                       dict(key="foot", label="bed foot", unit="mm",
                            min=0.0, max=0.8, step=0.1, val=0.4)]),
             dict(part="clasp", label="Lobster clasp"),
             dict(part="jump_ring", label="Jump ring"),
         ]),
    dict(id="montessori", version="1.3.0",
         name="Montessori Nuts & Bolts", family="Montessori",
         blurb="Companions for the Montessori set. The thread is cast from "
               "the designer's own nut, so every piece mates with the "
               "original bolts and with each other.",
         shared=[],
         members=[
             dict(part="mont_double", label="Double nut (coupler)"),
             dict(part="mont_plate", label="Base plate 2×3"),
             dict(part="wrench", label="Nut wrench"),
         ]),
]

# --- parts: each resolves to one 3MF on disk -----------------------------
PARTS = [
    _p("wrench", "Nut Wrench", "Montessori", "generated",
       "Combination spanner for the Montessori hex: a six-point box end one "
       "side, an open jaw the other. One size drives the nuts and both bolt "
       "heads.",
       version="1.0.0", gen=["gen_wrench.py"], out="wrench-af50.3mf"),
    _p("dice_orb", "Dice Orb", "Designed here", "generated",
       "A standard d20 captive in a rib-and-ring shaker sphere.",
       version="3.2.0",
       gen=["gen_dice_cage.py"], out="dice-cage.3mf",
       proven="Green PLA, outer brim on — clean; the brim is what holds the "
              "die pedestal down.",
       # printed twice: it failed brimless and came out perfect with an
       # outer brim holding the die pedestal down
       brim="on"),
    _p("mont_double", "Double Nut (coupler)", "Montessori", "generated",
       "Joins two Montessori bolts end to end. Both bore entries run out to "
       "the thread crest at 45 degrees, so the face that prints downward "
       "has no ceiling to droop into the hole.",
       version="1.3.1",
       gen=["gen_montessori.py", "--part", "double-nut"],
       out="montessori-double-nut.3mf"),
    _p("mont_plate", "Base Plate 2×3", "Montessori", "generated",
       "Six threaded sockets to stand the bolts in.",
       # shares the double nut's entry chamfer; its sockets open upward, so
       # the reshape is cosmetic here rather than a printability fix
       version="1.2.2",
       gen=["gen_montessori.py", "--part", "plate"],
       out="montessori-plate-2x3.3mf"),
    _p("clasp", "Lobster Clasp", "Designed here", "generated",
       "Flexure-gate clasp, sized to the chain it ends.",
       version="2.0.0",
       gen=["gen_clasp.py", "--part", "clasp"], out="clasp-only-D{dia:g}.3mf"),
    _p("jump_ring", "Jump Ring", "Designed here", "generated",
       "Butt C-ring that threads the link bore and the clasp's eye.",
       version="1.1.0",
       gen=["gen_clasp.py", "--part", "ring"], out="ring-only-D{dia:g}.3mf"),
    _p("chain", "Chain", "Designed here", "parametric",
       "Print-in-place stadium links, cut flat where they meet the bed so "
       "each link lands on a pad instead of a tangent line. A chain too "
       "long to lie straight on the plate is coiled instead, at a radius "
       "the joint has been measured to bend through.",
       version="1.2.0",
       gen=["gen_chain.py"],
       proven="48 links coiled, 0.6 mm bed foot, no brim, black PLA at "
              "220/55 — clean first try. The same chain brimless on a "
              "tangent-line foot lifted links a few layers in.",
       out="chain-N{links}-L{len:g}-D{dia:g}-F{foot:g}.3mf"),
    _p("sphere_stand", "Sphere Stand", "Sphere Stands", "parametric",
       "A ring that cradles a ball on a conformal spherical seat. Leave the "
       "last three blank and they follow the ball at a 45 deg contact.",
       version="1.0.0",
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
       version="1.1.0",
       gen=["gen_cage.py"], params=[
           dict(key="dia", label="cage \u00d8", unit="mm", min=30, max=90,
                step=2, val=50),
           dict(key="freq", label="frequency", min=1, max=6, step=1, val=2),
           dict(key="strut", label="strut \u00d8", unit="mm", min=1.4, max=4.5,
                step=0.2, val=2.2),
           dict(key="ball", label="ball \u00d8 (0 = none)", unit="mm", min=0,
                max=40, step=1, val=19)],
       out="cage-D{dia:g}-F{freq}-T{strut:g}-B{ball:g}.3mf",
       brim="on"),      # same thin first layer as the dice orb
]
BY_ID = {p["id"]: p for p in PARTS}
_LIB_INDEX = {}


def _lib_stamp():
    """What the library is built from: the shelf and the import list."""
    out = []
    for f in (IMPORTED,):
        try:
            st = os.stat(f)
            out.append((f, st.st_size, int(st.st_mtime)))
        except OSError:
            out.append((f, None, None))
    try:
        out.append((MODELS, int(os.stat(MODELS).st_mtime)))
    except OSError:
        pass
    return tuple(out)


def find(part_id):
    """Resolve any catalog id — generated, parametric or library.

    The library index is rebuilt when the shelf or the import list changes.
    Held for the life of the process instead, a file imported a moment ago
    is not findable until the server restarts.
    """
    if part_id in BY_ID:
        return BY_ID[part_id]
    stamp = _lib_stamp()
    if _LIB_INDEX.get("__stamp__") != stamp or part_id not in _LIB_INDEX:
        _LIB_INDEX.clear()
        _LIB_INDEX["__stamp__"] = stamp
        _LIB_INDEX.update({p["id"]: p for p in library()})
    if part_id in _LIB_INDEX and part_id != "__stamp__":
        return _LIB_INDEX[part_id]
    raise KeyError(part_id)


def _fmt(v):
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


_GIT = {}


def _git_last(path):
    """(iso date, subject) of the last commit to touch a file."""
    if path in _GIT:
        return _GIT[path]
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%cI\x1f%s", "--",
                            path], cwd=ROOT, capture_output=True, text=True,
                           timeout=10)
        date, _, note = r.stdout.strip().partition("\x1f")
    except Exception:
        date, note = "", ""
    if not date:
        try:
            import datetime
            date = datetime.datetime.fromtimestamp(
                os.path.getmtime(path)).isoformat()
            note = "uncommitted"
        except OSError:
            date, note = "", ""
    _GIT[path] = (date[:10], note[:90])
    return _GIT[path]


def provenance(part):
    if part["kind"] == "library":
        return dict(version=part.get("version", "—"),
                    changed=part.get("changed", ""), note="on disk",
                    built=part.get("built", ""))
    """What this design is, when it last changed, and when it was built.

    The version is the author's; the date comes from the last commit that
    touched the generator, so a design cannot claim to be current while its
    source has moved on.
    """
    src = os.path.join(HERE, part["gen"][0]) if part.get("gen") else ""
    changed, note = _git_last(src) if src else ("", "")
    built = ""
    try:
        p = out_path(part)
        if os.path.exists(p):
            import datetime
            built = datetime.datetime.fromtimestamp(
                os.path.getmtime(p)).strftime("%Y-%m-%d")
    except Exception:
        pass
    return dict(version=part.get("version", "0.1.0"), changed=changed,
                note=note, built=built)


def defaults(part):
    """Every dial a part needs to build, at its default value.

    A part in a kit gets some of its dials from the kit, so that the parts
    of a set always fit each other. Asking a part for its own params alone
    leaves those out and the generator refuses for want of a size.
    """
    vals = {}
    for k in KITS:
        if any(m["part"] == part["id"] for m in k["members"]):
            for d in k.get("shared", []):
                vals[d["key"]] = d["val"]
            for m in k["members"]:
                if m["part"] == part["id"]:
                    for d in (m.get("own") or []):
                        vals[d["key"]] = d["val"]
    for d in (part.get("params") or []):
        vals[d["key"]] = d["val"]
    return vals


def stale(part, path):
    """Was this file built before the code that builds it?

    Without this a cached 3MF is served forever: a generator can be fixed
    and every order still gets the old geometry, while the shop's own badge
    says the part rebuilds when ordered. The badge was telling the truth
    about the intent and not about the behaviour.
    """
    if not os.path.exists(path):
        return True
    built = os.path.getmtime(path)
    srcs = [os.path.join(HERE, g) for g in (part.get("gen") or [])[:1]]
    srcs.append(os.path.join(HERE, "embed_settings.py"))
    return any(os.path.exists(f) and os.path.getmtime(f) > built
               for f in srcs)


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
        # Fill anything the caller left out from the part's own defaults. A
        # dial added to a design should not break every order that predates
        # it, and provenance asks for the path with no parameters at all.
        full = dict(defaults(part))
        full.update(params)
        name = name.format(**full)
    return os.path.join(CUSTOM, name)


def ensure(part, params=None, timeout=600):
    """Generate the part's file if it is not on disk, or is out of date.

    Returns (path, report). Raises RuntimeError with the generator's own
    message when a design gate refuses the parameters.
    """
    if part["kind"] == "library":
        return part["path"], {"cached": True, "library": True}
    path = out_path(part, params)
    if not stale(part, path):
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


IMPORTED = os.path.join(MODELS, "imported.json")
DOWNLOADS = os.path.expanduser("~/Downloads")


def imported():
    """Files the user has explicitly imported, still present on disk."""
    if not os.path.exists(IMPORTED):
        return []
    try:
        with open(IMPORTED) as f:
            paths = json.load(f)
    except ValueError:
        return []
    return [p for p in paths if os.path.isfile(p)]


def scan(dirs=None):
    """Candidates for import. Looks; does not remember."""
    return library(dirs or [DOWNLOADS], include_imported=False)


def import_from(dirs=None):
    """Take what a scan found into the catalog, and write that down.

    The shop used to walk ~/Downloads on every read, which made anything
    that landed there a design — including the plates it had just exported.
    Importing is a thing the user does now, not a thing that happens to
    them.
    """
    have = set(imported())
    found = {p["path"] for p in scan(dirs)}
    keep = sorted(have | found)
    os.makedirs(os.path.dirname(IMPORTED), exist_ok=True)
    with open(IMPORTED, "w") as f:
        json.dump(keep, f, indent=1)
    return dict(added=len(found - have), total=len(keep),
                already=len(found & have))


def forget_imports():
    """Drop every import. The models/ shelf is untouched."""
    if os.path.exists(IMPORTED):
        os.remove(IMPORTED)


def library(dirs=None, limit=400, include_imported=True):
    """Printable files on disk, as catalog parts.

    Same shape as a generated part, so nothing downstream — the shop rows,
    the bill of materials, the packer, the exporter — needs to know which
    kind it is holding. The only difference is that ensure() has nothing to
    generate.

    Only models/ is read automatically: that shelf is this project's own.
    Anything else is here because it was imported on purpose.
    """
    dirs = list(dirs) if dirs else [MODELS]
    files_only = []
    if include_imported and dirs == [MODELS]:
        files_only = imported()
    seen, out = {}, []
    walks = [(d, None) for d in dirs] + [(None, f) for f in files_only]
    for d, one in walks:
        if one is not None:
            root, files = os.path.dirname(one), [os.path.basename(one)]
            trees = [(root, files)]
        elif os.path.isdir(d):
            trees = [(r, fs) for r, _, fs in os.walk(d)]
        else:
            continue
        for root, files in trees:
            if "/glb" in root or "/meta" in root or "/index_out" in root:
                continue
            if "/custom" in root:
                continue        # the generators' own output: already a part,
                                # and listing it again puts the same design
                                # in the catalog twice under two names
            if "print-shop-order" in root:
                continue        # a plate this shop exported, downloaded and
                                # then found again — an order is not a design
            for fn in sorted(files):
                low = fn.lower()
                if not low.endswith((".3mf", ".stl")):
                    continue
                if low.endswith(".gcode.3mf"):
                    continue        # a sliced export, not a model to print
                if re.match(r"plate_\d\d[_.]", low):
                    continue        # our own plate naming, downloaded back
                p = os.path.join(root, fn)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                # A design kept in both models/ and Downloads is one design,
                # even when the two copies differ in size because one was
                # re-saved — that pair was showing up as two catalog entries
                # for the same object. Two files that merely share a generic
                # name in unrelated project folders are not folded: "00
                # start.3mf" means something different in each of them.
                key = low
                prev = seen.get(key)
                same_design = prev is not None and (
                    (prev["path"].startswith(MODELS)) !=
                    (p.startswith(MODELS)))
                if same_design:
                    prev["copies"] = prev.get("copies", 1) + 1
                    prev.setdefault("also", []).append(p)
                    continue
                if prev is not None and prev["size"] == st.st_size:
                    continue                     # the very same file, twice
                import datetime
                entry = _p(
                    "lib_" + hashlib.md5(p.encode()).hexdigest()[:10],
                    os.path.splitext(fn)[0].replace("+", " ").replace("_", " "),
                    "Downloads" if "Downloads" in root else "Models",
                    "library", "",
                    version="—", path=p, size=st.st_size,
                    changed=datetime.date.fromtimestamp(
                        st.st_mtime).isoformat(),
                    built=datetime.date.fromtimestamp(
                        st.st_mtime).isoformat())
                seen.setdefault(key, entry)
                out.append(entry)
                if len(out) >= limit:
                    return out
    return out


def _tag(stamp):
    """A short, URL-safe version tag for a preview's source stamp."""
    if not stamp:
        return ""
    return hashlib.md5(str(stamp).encode()).hexdigest()[:8]


def previews():
    """id -> preview record, built by previews.py. Empty is not an error."""
    f = os.path.join(MODELS, "previews.json")
    if not os.path.exists(f):
        return {}
    try:
        with open(f) as fh:
            return {e["id"]: e for e in json.load(fh)}
    except (ValueError, KeyError):
        return {}


def enrich(part, prev):
    """Give every entry the fields a card needs, whoever made it.

    A generated part knows its own story; a file scanned off disk knows
    only its name. Where a human has written about that file, its curation
    is folded in here — so one card template renders either, and the shop
    and the design write-up can no longer disagree about what a part is.
    """
    import designs
    out = dict(part)
    pv = prev.get(part["id"])
    if pv:
        # the stamp rides in the URL: a rebuilt preview is a new address, so
        # the browser cannot keep showing the geometry it cached earlier
        tag = _tag(pv.get("stamp"))
        out.update(preview=pv["glb"] + (f"?v={tag}" if tag else ""),
                   dims3=pv["dims"], bodies=pv["bodies"],
                   tris=pv["tris_full"])
        d = pv["dims"]
        out["dims"] = f"{d[0]} x {d[1]} x {d[2]} mm"
    cur = designs.curation(os.path.basename(part.get("path", "")))
    if cur:
        out.update(name=cur["title"], family=cur["family"],
                   designer=cur["designer"], material=cur["mat"],
                   verdict=list(cur["v"]), card=cur["cid"])
        if not out.get("blurb"):
            out["blurb"] = cur["blurb"]
        sl = designs.SLICE.get(cur["cid"])
        if sl:
            out["slice"] = sl
    m = _meta(part.get("path", ""))
    if m:
        out["meta"] = m
    return out


def _meta(path):
    """The designer's own metadata, extracted from the 3MF alongside it."""
    if not path:
        return None
    slug = re.sub(r"[^a-z0-9]+", "_",
                  os.path.basename(path).lower().rsplit(".", 1)[0]).strip("_")
    f = os.path.join(MODELS, "meta", slug, "meta.json")
    if not os.path.exists(f):
        return None
    try:
        with open(f) as fh:
            md = json.load(fh)
    except ValueError:
        return None
    keep = {k: md[k] for k in ("Designer", "License", "Origin", "Application",
                               "CreationDate", "Description") if md.get(k)}
    if md.get("photos"):
        keep["photos"] = [f"models/meta/{slug}/{x}" for x in md["photos"]]
    if md.get("cover"):
        keep["cover"] = f"models/meta/{slug}/{md['cover']}"
    return keep or None


def catalog(with_library=True):
    """One list. A part is a part; some of them have options."""
    entries = list(PARTS) + (library() if with_library else [])
    prev = previews()
    parts = [enrich(dict(p, **provenance(p)), prev) for p in entries]
    # Every part carries a semver, including the ones nobody here authored.
    # Reconciled in memory so a read has no side effects; the pipeline
    # (versions.py) is what writes the ledger.
    import versions as _v
    led, faults = _v.reconcile(parts, write=False)
    for p in parts:
        e = led.get(p["id"], {})
        if e.get("version"):
            p["version"] = e["version"]
        p["fingerprint"] = e.get("fingerprint")
        p["revisions"] = e.get("revisions", 0)
        p["first_seen"] = e.get("first_seen", "")
        p["version_source"] = ("declared" if p["kind"] != "library"
                               else "observed")
    by = {p["id"]: p for p in parts}
    kits = []
    for k in KITS:
        mem = [by[m["part"]] for m in k["members"] if m["part"] in by]
        dates = [p["changed"] for p in mem if p["changed"]]
        builts = [p["built"] for p in mem if p["built"]]
        # a kit is only as built as its least-built member
        kit = dict(k, changed=max(dates) if dates else "",
                   built=min(builts) if len(builts) == len(mem) else "")
        pv = prev.get("kit_" + k["id"])
        if pv:
            # the card is for the set, so its preview shows the whole set
            tag = _tag(pv.get("stamp"))
            kit.update(preview=pv["glb"] + (f"?v={tag}" if tag else ""),
                       dims3=pv["dims"], tris=pv["tris_full"],
                       bodies=pv["bodies"])
        kits.append(kit)
    fams = []
    for p in parts:
        if p["family"] not in fams:
            fams.append(p["family"])
    return {"printers": PRINTERS, "printer": DEFAULT_PRINTER,
            "kits": kits, "parts": parts, "families": fams,
            "version_faults": faults}


if __name__ == "__main__":
    c = catalog()
    print(json.dumps({"kits": [(k["id"], [m["part"] for m in k["members"]])
                               for k in c["kits"]],
                      "parts": [p["id"] for p in c["parts"]],
                      "library_found": len(library())}, indent=1))
