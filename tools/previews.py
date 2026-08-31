#!/usr/bin/env python3
"""One preview per catalog entry, so every card shows the actual part.

The catalog carries two kinds of entry that used to look nothing alike in
the page: the handful built by the generators, which had hand-authored
cards with live 3D, and the couple of hundred files found on disk, which
were a name and a family in a list. This builds the same asset for both --
a small, decimated, coloured GLB -- so one card template can render either.

Previews are cached on the source's size and mtime: rebuilding is cheap
when nothing changed, and a file that is edited on disk gets a new preview
without anyone having to remember to ask for one.

Usage: previews.py [--only ID ...] [--budget FACES] [--force] [--jobs N]
"""
import argparse
import json
import os
import sys

import trimesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "models", "glb", "prev")
INDEX = os.path.join(ROOT, "models", "previews.json")
PALETTE = [(233, 160, 99), (90, 178, 168), (129, 146, 214), (214, 176, 88),
           (183, 122, 183), (120, 180, 108), (208, 112, 118), (110, 162, 206)]
BUDGET = 26_000          # faces per preview; a card is 320 px of canvas
GAP = 6.0


def _load(path):
    """Every body of a file, in world space, standing on z=0 as a group."""
    scene = trimesh.load(path, force="scene")
    out = []
    for node in scene.graph.nodes_geometry:
        tf, gname = scene.graph[node]
        g = scene.geometry[gname]
        if isinstance(g, trimesh.Trimesh) and len(g.faces):
            m = g.copy()
            m.apply_transform(tf)
            out.append(m)
    return out


def _tile(meshes):
    """Lay a multi-body file out in rows, so parts do not hide each other."""
    widths = [m.bounds[1][0] - m.bounds[0][0] for m in meshes]
    deps = [m.bounds[1][1] - m.bounds[0][1] for m in meshes]
    target = max(max(widths) + GAP,
                 (sum(w + GAP for w in widths)) ** 0.5 *
                 ((max(deps) + GAP) ** 0.5))
    x = y = row = 0.0
    for m in meshes:
        lo, hi = m.bounds
        w, d = hi[0] - lo[0], hi[1] - lo[1]
        if x > 0 and x + w > target:
            x, y, row = 0.0, y + row + GAP, 0.0
        m.apply_translation([x - lo[0], y - lo[1], -lo[2]])
        x += w + GAP
        row = max(row, d)


def build_one(pid, path, budget=BUDGET, tile=True):
    meshes = []
    for one in ([path] if isinstance(path, str) else path):
        meshes += _load(one)
    if not meshes:
        raise ValueError("no printable body in the file")
    full = sum(len(m.faces) for m in meshes)
    # A file that ships several loose objects is a set, not an assembly:
    # tile it. One that overlaps its own bodies is an assembly already
    # positioned, and moving the parts apart would misrepresent it.
    if tile and len(meshes) > 1 and not _overlapping(meshes):
        _tile(meshes)
    sc, kept = trimesh.Scene(), 0
    for i, m in enumerate(meshes):
        if full > budget:
            want = max(300, int(len(m.faces) * budget / full))
            if want < len(m.faces):
                try:
                    # aggression 7: the default refuses collapses that cost
                    # any accuracy, which leaves some files near their
                    # original size
                    m = m.simplify_quadric_decimation(face_count=want,
                                                      aggression=7)
                except BaseException:
                    pass
        m.visual = trimesh.visual.ColorVisuals(
            m, face_colors=(*PALETTE[i % len(PALETTE)], 255))
        kept += len(m.faces)
        sc.add_geometry(m, node_name=f"part_{i}")
    lo, hi = sc.bounds
    ctr = (lo + hi) / 2
    for g in sc.geometry.values():
        g.apply_translation([-ctr[0], -ctr[1], -lo[2]])
    os.makedirs(OUT, exist_ok=True)
    dest = os.path.join(OUT, pid + ".glb")
    sc.export(dest)
    ext = sc.bounds[1] - sc.bounds[0]
    # what the printer will make of it. A generated part is gated by its
    # generator; a downloaded one arrives however its author saved it, and
    # the first sign the orientation is wrong is spaghetti.
    try:
        import orient
        # As-saved only. The layer-by-layer check costs about half a second
        # a body, and searching ten orientations for every body of every
        # design turns a rebuild into a coffee break. `orient.py FILE` does
        # the full search when the question is actually "which way up".
        adv, worst = [], None
        for g in meshes:
            q = g.copy()
            q.apply_translation([0, 0, -q.bounds[0][2]])
            asis = dict(orient._measure(q), rot="as saved")
            best = asis
            for line in orient.verdict(best, asis):
                # one line per kind of problem, keeping the worst body's
                # number: three bodies saying the same thing three ways is
                # noise, not detail
                kind = line.split(" ")[0] + line.split("—")[0][-12:]
                if not any(k == kind for k, _ in adv):
                    adv.append((kind, line))
            if worst is None or best["overhang_mm2"] > worst["overhang_mm2"]:
                worst = best
        adv = [line for _, line in adv]
        # "prints as it stands" is the all-clear, and it is only the truth
        # when there is nothing else to say. One body's clean bill of health
        # beside another body's warning reads as a contradiction.
        real = [x for x in adv if not x.startswith("prints as it stands")]
        adv = real if real else adv
        printability = dict(advice=adv, bed_mm2=worst["bed_mm2"],
                            overhang_mm2=worst["overhang_mm2"],
                            lever=worst["lever"])
    except Exception as e:                       # noqa: BLE001
        printability = {"advice": [], "error": str(e)[:80]}

    out = dict(id=pid, glb=f"models/glb/prev/{pid}.glb", bodies=len(meshes),
               printability=printability,
               tris=kept, tris_full=full,
               dims=[round(float(v), 1) for v in ext],
               kb=round(os.path.getsize(dest) / 1024))
    if kept > budget:
        # The decimator stops well short on some meshes and there is no one
        # cause: a lattice cannot lose a handle without becoming a different
        # object, and other files simply refuse to collapse. Record what was
        # actually achieved rather than let a 2 MB card asset pass for a
        # preview that met its budget.
        out["capped"] = True
        out["capped_note"] = (f"decimator stopped at {kept:,} of a "
                              f"{budget:,} budget "
                              f"(genus {_genus(meshes)}, "
                              f"{_components(meshes)} shells)")
    return out


def _genus(meshes):
    """Handles in the surface, from Euler's formula."""
    g = 0
    for m in meshes:
        try:
            chi = len(m.vertices) - len(m.edges_unique) + len(m.faces)
            g += max(0, int(round((2 - chi) / 2)))
        except BaseException:                        # noqa: BLE001
            pass
    return g


def _components(meshes):
    """Disconnected shells: each one has its own decimation floor."""
    n = 0
    for m in meshes:
        try:
            n += len(m.split(only_watertight=False))
        except BaseException:                        # noqa: BLE001
            n += 1
    return n


def _overlapping(meshes):
    """Do any two bodies share space? Then the file is an arranged assembly."""
    for i, a in enumerate(meshes):
        for b in meshes[i + 1:]:
            if (a.bounds[0] < b.bounds[1]).all() and \
               (b.bounds[0] < a.bounds[1]).all():
                return True
    return False


def stamp(path):
    st = os.stat(path)
    return f"{st.st_size}:{int(st.st_mtime)}"


def _source_of(pid):
    part = catalog.find(pid)
    if part["kind"] == "library":
        return part["path"]
    return catalog.ensure(part, catalog.defaults(part))[0]


def sources():
    """(id, source) for everything the catalog can show on a card.

    A kit gets a preview of its own, built from every member: the card is
    for the set, and showing only the first part of it answers the wrong
    question about what you are about to order.
    """
    cat = catalog.catalog()
    for p in cat["parts"]:
        try:
            yield p["id"], _source_of(p["id"])
        except Exception as e:                       # noqa: BLE001
            print(f"  ! {p['id']}: {e}", file=sys.stderr)
    for k in cat["kits"]:
        paths = []
        for m in k["members"]:
            try:
                paths.append(_source_of(m["part"]))
            except Exception as e:                   # noqa: BLE001
                print(f"  ! {k['id']}/{m['part']}: {e}", file=sys.stderr)
        if paths:
            yield "kit_" + k["id"], paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--budget", type=int, default=BUDGET)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    have = {}
    if os.path.exists(INDEX) and not a.force:
        with open(INDEX) as fh:
            have = {e["id"]: e for e in json.load(fh)}
    out, built, kept = [], 0, 0
    for pid, path in sources():
        if a.only and pid not in a.only:
            if pid in have:
                out.append(have[pid])
            continue
        try:
            s = "|".join(stamp(x)
                         for x in ([path] if isinstance(path, str) else path))
        except OSError:
            continue
        old = have.get(pid)
        if (old and old.get("stamp") == s
                and os.path.exists(os.path.join(ROOT, old["glb"]))):
            out.append(old)
            kept += 1
            continue
        try:
            e = build_one(pid, path, a.budget)
        except Exception as ex:                      # noqa: BLE001
            print(f"  ! {pid}: {ex}", file=sys.stderr)
            continue
        e["stamp"] = s
        out.append(e)
        built += 1
        print(f"{pid:22s} {e['tris_full']:>9,d} -> {e['tris']:>7,d} tris  "
              f"{e['kb']:>5d} KB"
              + (f"  ! {e['capped_note']}" if e.get("capped") else ""),
              flush=True)
    with open(INDEX, "w") as f:
        json.dump(out, f, indent=1)
    print(f"previews: {built} built, {kept} cached, {len(out)} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
