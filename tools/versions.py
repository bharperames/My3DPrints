#!/usr/bin/env python3
"""A version for every part, and a fingerprint that keeps it honest.

A declared version is a claim, not a measurement: a generator can be fixed
and the number left alone, and then the shop shows v1.0.0 for two different
designs. So every part is fingerprinted as well as versioned, and the ledger
remembers both.

    generated / parametric  the author declares the version; the fingerprint
                            is the generator's source and its fixed
                            arguments. If the fingerprint moves and the
                            version does not, that is a fault, reported --
                            not quietly absorbed.

    library                 nobody here authored it, so nothing can declare
                            a version. One is read out of the designer's own
                            naming where they gave one ("Vortex v3" -> 3.0.0)
                            and otherwise starts at 0.1.0. When the bytes on
                            disk change, the patch moves: we cannot know
                            whether a re-download was a breaking change, and
                            a patch is the smallest claim that is still true.

The ledger lives at models/versions.json and is the record of what was seen
when. Deleting it is safe -- it rebuilds -- but the history goes with it.

Usage: versions.py [--check] [--json]
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LEDGER = os.path.join(ROOT, "models", "versions.json")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
# Bumped whenever the way a fingerprint is computed changes. Without it,
# changing the method makes every part look edited at once and the fault
# report — which deliberately holds its ground until a version moves —
# would never let the ledger re-baseline.
FP_ALGO = 3   # 3: measured off the built shape, not the source text
# "Vortex v3", "Mini Stackable V2", "thing v1.2" -- a version the designer
# put in the name. Bare numbers are not versions: "voro_sphere_2" is a file
# name, and "c-shape copy 16" is a copy count.
NAMED = re.compile(r"(?:^|[^a-z0-9])v(\d+)(?:\.(\d+))?(?:\.(\d+))?(?![0-9])",
                   re.I)


def _today():
    return datetime.date.today().isoformat()


def declared_version(part):
    """The version in the name a designer gave the file, if there is one."""
    m = NAMED.search(os.path.basename(part.get("path", "")))
    if not m:
        return None
    a, b, c = m.group(1), m.group(2) or "0", m.group(3) or "0"
    return f"{int(a)}.{int(b)}.{int(c)}"


# A 3MF is a zip, and both layers carry something that changes without the
# model changing: the zip records when it was written, and trimesh stamps a
# fresh random UUID into the model XML on every export. Hashing the raw
# bytes made a rebuild look like a new revision — the held sphere reached
# its thirtieth in four days with nobody touching it.
_UUID = re.compile(rb'\s*(?:p:)?UUID="[0-9a-fA-F-]{36}"')


def _stable(blob):
    """One zip entry, with what changes per export taken out."""
    return _UUID.sub(b"", blob)


def stamp(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return f"{st.st_size}:{int(st.st_mtime)}"


def shape_of(path):
    """What a built part IS, as two signatures: its shape and its fit.

    Neither is the file's bytes and neither is the generator's source. A
    3MF is a zip and records the time it was written, so re-exporting an
    unmoved vertex changes the bytes. Source is worse in both directions:
    a rename or a reordered loop rewrites the text without moving a
    vertex, and a number edited in an imported module moves vertices
    without touching the generator's text at all.

    SHAPE is every vertex. Coordinates are rounded to 0.1 micron, so the
    last bits of a rearranged float calculation do not count as a change,
    and both vertices and face centroids are sorted, so emitting the same
    solid in a different order is not a change either. Bodies are hashed
    separately and their hashes sorted, so the order they land in a scene
    does not count.

    FIT is what a mating part must hold: overall size, per-body size,
    volume, how many bodies and the Euler number, which moves when a hole
    opens or closes. A part can be restyled without any of these moving;
    a bore that changes diameter, a helix that changes pitch or a plate
    that changes thickness moves at least one.

    The split is the point. It is what lets the guard ask for a MAJOR bump
    when the part will no longer fit what it fitted, and only a minor one
    when it merely looks different.
    """
    import numpy as np
    import trimesh
    try:
        sc = trimesh.load(path, force="scene")
    except Exception:                                       # noqa: BLE001
        return None
    shapes, fits = [], []
    for g in sorted(sc.geometry.values(), key=lambda m: len(m.faces)):
        v = np.round(np.asarray(g.vertices, dtype=float), 4) + 0.0
        v[v == 0] = 0.0                       # -0.0 and 0.0 are one number
        f = np.asarray(g.faces)
        if not len(v) or not len(f):
            continue
        c = np.round(v[f].mean(axis=1), 4) + 0.0
        c[c == 0] = 0.0
        vi = np.lexsort((v[:, 2], v[:, 1], v[:, 0]))
        ci = np.lexsort((c[:, 2], c[:, 1], c[:, 0]))
        h = hashlib.sha256()
        h.update(v[vi].tobytes())
        h.update(c[ci].tobytes())
        shapes.append(h.hexdigest())
        # Coarser than the shape hash, and deliberately. Fit is a physical
        # question and this shop has measured where the line is: 0.05 mm
        # decided whether a carbon rod went into its socket, and a micron
        # never decided anything -- a nozzle lays 0.42 mm. So size is read
        # to 0.01 mm and volume to four figures. A finer tessellation moves
        # both by less than that and is reported as shape, not as fit; a
        # bore that opens by half a tenth is reported as fit.
        ext = np.round(v.max(axis=0) - v.min(axis=0), 2) + 0.0
        vol = float(g.volume)
        vol = round(vol, max(0, 4 - len(str(int(abs(vol)))))) if vol else 0.0
        fits.append((tuple(ext.tolist()), vol, int(g.euler_number)))
    if not shapes:
        return None
    fits.sort()
    return dict(
        shape=hashlib.sha256("".join(sorted(shapes)).encode()).hexdigest()[:16],
        fit=hashlib.sha256(repr(fits).encode()).hexdigest()[:16],
        bodies=len(shapes))


def _ver(v):
    try:
        a, b, c = (int(x) for x in str(v).split("."))
        return a, b, c
    except ValueError:
        return 0, 0, 0


def bump_needed(was_ver, now_ver, level):
    """Did the declared version advance far enough for what changed?

    A fit change asks for a major bump; a shape-only change asks for a
    minor one, and a major satisfies it. A patch never satisfies either --
    a patch says nothing moved that anyone can measure.
    """
    a0, b0, _ = _ver(was_ver)
    a1, b1, _ = _ver(now_ver)
    if level == "major":
        return a1 > a0
    return a1 > a0 or b1 > b0


def fingerprint(part, was=None):
    """What this part is made of, as a hash.

    For a generated part that is the code and the fixed arguments, so a
    change to the generator shows up whatever the version claims. For a file
    on disk it is the bytes — hashed once and then remembered against the
    file's size and mtime, because re-reading a couple of hundred downloads
    on every page load is not a thing to do.
    """
    h = hashlib.sha256()
    if part["kind"] == "library":
        p = part.get("path", "")
        st = stamp(p)
        if was and st and was.get("stamp") == st and was.get("fingerprint"):
            return was["fingerprint"], st
        try:
            if p.lower().endswith(".3mf"):
                # A 3MF is a zip and a zip records the time it was written,
                # so re-exporting geometry that has not changed by a single
                # vertex produces different bytes. Hashing those bytes made
                # every rebuild look like a new revision: the held sphere
                # was on its thirtieth in four days without anyone touching
                # it. Hash what the entries contain, not the envelope.
                with zipfile.ZipFile(p) as z:
                    for name in sorted(z.namelist()):
                        h.update(name.encode())
                        h.update(_stable(z.read(name)))
            else:
                with open(p, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 20), b""):
                        h.update(chunk)
        except (OSError, zipfile.BadZipFile, KeyError):
            return None, st
        return h.hexdigest()[:16], st
    # A generated part is not identified by its source. Hashing the code
    # was the old answer and it was wrong in both directions: a rename or a
    # reordered loop rewrote the text without moving a vertex, and a number
    # edited in an imported module moved vertices without touching the
    # text. reconcile() measures the built solid instead -- see shape_of.
    return None, None


def load():
    if not os.path.exists(LEDGER):
        return {}
    try:
        with open(LEDGER) as f:
            return json.load(f)
    except ValueError:
        return {}


def save(led):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "w") as f:
        json.dump(led, f, indent=1, sort_keys=True)


def bump_patch(v):
    try:
        a, b, c = (int(x) for x in v.split("."))
        return f"{a}.{b}.{c + 1}"
    except ValueError:
        return "0.1.1"


def canonical(part):
    """The part built at the parameters its card ships with.

    That build is what the shape signature is taken from: one agreed set
    of dials, so the question is whether the DESIGN moved rather than
    whether someone ordered a different size.
    """
    if not part.get("out") or not part.get("gen"):
        return None
    try:
        return catalog.out_path(part, catalog.defaults(part))
    except Exception:                                       # noqa: BLE001
        return None


def reconcile(parts, led=None, write=True):
    """Bring the ledger up to date with what the parts actually are.

    Returns (ledger, faults). A fault is a generated part whose source moved
    without its declared version moving -- the one thing a version ledger
    exists to catch.
    """
    led = load() if led is None else dict(led)
    faults, today = [], _today()
    changed = False
    for p in parts:
        pid = p["id"]
        was = led.get(pid)
        fp, st = fingerprint(p, was)
        if p["kind"] == "library":
            ver = (was or {}).get("version") or declared_version(p) or "0.1.0"
            if was and was.get("fingerprint") != fp:
                # the bytes changed under a name we do not control
                ver = bump_patch(ver)
        else:
            ver = p.get("version", "0.1.0")
            # What the part IS, measured off the built solid rather than
            # read out of the source that built it. Recomputed only when
            # that build has moved -- loading two dozen meshes on every
            # catalog read would make a page load cost seconds.
            sig, gst = None, None
            path = canonical(p)
            if path:
                gst = stamp(path)
                if was and gst and was.get("gstamp") == gst and was.get("shape"):
                    sig = {k: was.get(k) for k in ("shape", "fit", "bodies")}
                else:
                    sig = shape_of(path)
            if sig:
                fp = sig["shape"]
            rebased = was is not None and was.get("algo") != FP_ALGO
            moved = (sig and was and was.get("shape")
                     and was["shape"] != sig["shape"])
            if moved and not rebased and not p.get("cosmetic"):
                # A change to size, volume or topology is a change to what
                # the part will still fit, and that is a major. Anything
                # else moved vertices without moving an interface, which is
                # a minor. Neither is satisfied by a patch.
                level = "major" if was.get("fit") != sig["fit"] else "minor"
                if not bump_needed(was.get("version"), ver, level):
                    what = ("it no longer fits what it fitted"
                            if level == "major"
                            else "its shape changed")
                    faults.append(dict(
                        id=pid, name=p["name"], version=ver, level=level,
                        why=f"{pid}: {what}, so v{was.get('version')} needs "
                            f"a {level} bump -- it still declares v{ver}"))
                    # Leave the recorded signature alone. Writing the new
                    # one here would clear the fault on the next run
                    # without anyone fixing it -- the guard would fire once
                    # and then forget.
                    led[pid] = was
                    continue
        entry = dict(version=ver, fingerprint=fp, stamp=st, algo=FP_ALGO,
                     first_seen=(was or {}).get("first_seen", today),
                     revisions=(was or {}).get("revisions", 0))
        if p["kind"] != "library":
            entry.update(shape=(sig or {}).get("shape"),
                         fit=(sig or {}).get("fit"),
                         bodies=(sig or {}).get("bodies"), gstamp=gst,
                         cosmetic=bool(p.get("cosmetic")))
        if was and was.get("algo") != FP_ALGO:
            # the method changed, not the design
            entry["updated"] = was.get("updated", entry["first_seen"])
        elif was and was.get("fingerprint") != fp:
            entry["revisions"] = entry["revisions"] + 1
            entry["updated"] = today
        elif was:
            entry["updated"] = was.get("updated", entry["first_seen"])
        else:
            entry["updated"] = today
        if led.get(pid) != entry:
            changed = True
        led[pid] = entry
    if write and changed:
        save(led)
    return led, faults


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report version faults without writing the ledger")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    parts = catalog.catalog(with_library=True)["parts"]
    led, faults = reconcile(parts, write=not a.check)
    if a.json:
        print(json.dumps({"parts": len(led), "faults": faults}, indent=1))
    else:
        unver = [p for p in parts if not SEMVER.match(led[p["id"]]["version"])]
        gen = [p for p in parts if p.get("gen")]
        # Every generated part is held to its version unless it is marked
        # cosmetic, and that guard is only as good as the measurement it
        # rests on. A part with no build to measure is UNCHECKED, not
        # passing -- saying so is the difference between a guard and the
        # appearance of one.
        blind = [p["id"] for p in gen
                 if not p.get("cosmetic") and not led[p["id"]].get("shape")]
        exempt = [p["id"] for p in gen if p.get("cosmetic")]
        print(f"{len(led)} parts versioned "
              f"({sum(1 for p in parts if p['kind'] == 'library')} from disk)")
        print(f"  {len(gen) - len(blind) - len(exempt)} of {len(gen)} "
              f"generated parts checked against their built shape"
              + (f", {len(exempt)} cosmetic" if exempt else ""))
        if blind:
            print(f"  ! NOT CHECKED, no build to measure: {blind}")
            print("    run `make build` so these are guarded")
        if unver:
            print(f"  ! {len(unver)} without a valid semver: "
                  f"{[p['id'] for p in unver][:5]}")
        for f in faults:
            print(f"  ! {f['why']}")
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())
