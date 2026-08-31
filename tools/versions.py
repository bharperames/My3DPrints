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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LEDGER = os.path.join(ROOT, "models", "versions.json")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
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


def stamp(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return f"{st.st_size}:{int(st.st_mtime)}"


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
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        except OSError:
            return None, st
        return h.hexdigest()[:16], st
    gen = part.get("gen") or []
    if not gen:
        return None, None
    src = os.path.join(HERE, gen[0])
    try:
        with open(src, "rb") as f:
            h.update(f.read())
    except OSError:
        return None, None
    h.update("\x00".join(gen[1:]).encode())
    return h.hexdigest()[:16], stamp(src)


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
            if (was and was.get("fingerprint") != fp
                    and was.get("version") == ver):
                faults.append(dict(
                    id=pid, name=p["name"], version=ver,
                    why=f"{os.path.basename((p.get('gen') or ['?'])[0])} "
                        f"changed but {pid} still declares v{ver}"))
                # Leave the recorded fingerprint alone. Writing the new one
                # here would clear the fault on the next run without anyone
                # fixing it — the guard would fire once and then forget.
                led[pid] = was
                continue
        entry = dict(version=ver, fingerprint=fp, stamp=st,
                     first_seen=(was or {}).get("first_seen", today),
                     revisions=(was or {}).get("revisions", 0))
        if was and was.get("fingerprint") != fp:
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
        print(f"{len(led)} parts versioned "
              f"({sum(1 for p in parts if p['kind'] == 'library')} from disk)")
        if unver:
            print(f"  ! {len(unver)} without a valid semver: "
                  f"{[p['id'] for p in unver][:5]}")
        for f in faults:
            print(f"  ! {f['why']}")
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())
