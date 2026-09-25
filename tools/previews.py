#!/usr/bin/env python3
"""Measure every catalog entry, and build a GLB only for the composites.

The catalog carries two kinds of entry that used to look nothing alike in
the page: the handful built by the generators, which had hand-authored
cards with live 3D, and the couple of hundred files found on disk, which
were a name and a family in a list. One card template renders either, and
that is still the point.

It used to get there by writing a GLB beside every source. That is gone:
the browser reads 3MF and STL directly, so a copy of a part is dead weight
-- three hundred and fifty megabytes of it, the same size as the files it
was made from, and a cache that fell out of step whenever a generator
changed. What is still worth building is a COMPOSITE: a kit's card shows
every member at once and no single file on disk is that picture.

So this measures everything (extents, bodies, triangles, printability --
the numbers a card quotes) and exports only for kits. Entries are cached on
the source's size and mtime, so a file edited on disk is re-measured
without anyone having to remember to ask.

Usage: previews.py [--only ID ...] [--budget FACES] [--force] [--jobs N]
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "models", "glb", "prev")
INDEX = os.path.join(ROOT, "models", "previews.json")
PALETTE = [(233, 160, 99), (90, 178, 168), (129, 146, 214), (214, 176, 88),
           (183, 122, 183), (120, 180, 108), (208, 112, 118), (110, 162, 206)]
# No ceiling: previews are the real geometry. The machinery below still
# honours a budget if one is set, and the fair share is what it should
# always have used — but on the machine this runs on, two dozen live cards
# sit at the display's refresh rate with the full meshes, so there is
# nothing to buy by throwing detail away.
#
# The earlier ceiling was chosen from frame rates measured in headless
# Chromium, which falls back to SwiftShader and rasterizes on the CPU.
# Those numbers described a renderer nobody uses.
BUDGET = None

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


def build_one(pid, path, budget=BUDGET, tile=True, probe=True, write=True):
    """Measure a part, and write a GLB only if one is actually needed.

    A GLB used to be written beside every source -- three hundred and fifty
    megabytes of it across the shelf, the same size as the files it was made
    from, and a cache that fell out of step whenever a generator changed.
    The browser reads 3MF and STL directly now, so the copy is dead weight
    for anything with a single source file. What is still worth writing is a
    COMPOSITE: a kit's card shows all its members together and there is no
    one file on disk that is that. `write=False` measures and returns
    without exporting.
    """
    srcs = [path] if isinstance(path, str) else list(path)
    meshes = []
    for one in srcs:
        meshes += _load(one)
    # Parts that come from different files are separate objects whatever
    # their coordinates say. Each is modeled about its own origin, so an
    # hourglass body and the spiral that screws through it both sit at
    # (75, 0, 45) and the overlap test reads them as one positioned
    # assembly — the preview stacks them in the same place.
    many = len(srcs) > 1
    if not meshes:
        raise ValueError("no printable body in the file")
    full = sum(len(m.faces) for m in meshes)
    # Measure before tiling. The preview spreads a multi-body file out so
    # its parts do not hide each other, and reporting that arrangement's
    # extents describes a layout this app invented: the straight T-Rex read
    # as 176 x 176 when the file is 244 x 150, and the dragon as 203 x 393
    # when it is 508 x 195.
    _lo = np.min([m.bounds[0] for m in meshes], axis=0)
    _hi = np.max([m.bounds[1] for m in meshes], axis=0)
    src_ext = [round(float(v), 1) for v in (_hi - _lo)]
    big = max(meshes, key=lambda m: float(m.volume))
    be = big.bounds[1] - big.bounds[0]
    biggest = [round(float(v), 1) for v in be]
    # A file that ships several loose objects is a set, not an assembly:
    # tile it. One that overlaps its own bodies is an assembly already
    # positioned, and moving the parts apart would misrepresent it.
    if tile and len(meshes) > 1 and (many or not _overlapping(meshes)):
        _tile(meshes)
    # Shared max-min, not proportionally: cutting every mesh by the same
    # fraction takes three quarters of the wrench's faces to make room for
    # a base plate that will not miss them, and a prismatic part that has
    # lost its corners renders as a ribbon.
    import meshcheck
    targets = (meshcheck.budget_faces([len(m.faces) for m in meshes], budget)
               if budget else [len(m.faces) for m in meshes])
    sc, kept = trimesh.Scene(), 0
    for i, m in enumerate(meshes):
        if budget and full > budget:
            want = max(300, targets[i])
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
    dest = os.path.join(OUT, pid + ".glb")
    if write:
        os.makedirs(OUT, exist_ok=True)
        sc.export(dest)
    ext = sc.bounds[1] - sc.bounds[0]
    kb = round(os.path.getsize(dest) / 1024) if write else 0
    glb = f"models/glb/prev/{pid}.glb" if write else None
    # The printability probe below costs about a sixth of a second a body,
    # which was seven eighths of the wait on a set of thirty-two discs --
    # and a preview being redrawn while someone types is not being read
    # for printing advice. probe=False is for that caller.
    if not probe:
        return dict(id=pid, glb=glb,
                    bodies=len(meshes), printability={"advice": []},
                    tris=kept, tris_full=full, dims=src_ext,
                    tiled_dims=[round(float(v), 1) for v in ext],
                    biggest_body=biggest, kb=kb)
    # What the printer will make of it. A generated part is gated by its
    # generator; a downloaded one arrives however its author saved it, and
    # the first sign the orientation is wrong is spaghetti.
    try:
        import orient
        # As-saved only. The layer-by-layer check costs about half a second
        # a body, and searching ten orientations for every body of every
        # design turns a rebuild into a coffee break. `orient.py FILE` does
        # the full search when the question is actually "which way up".
        # Analyzed at full resolution. The decimated copy is 26k faces for
        # a 400 mm dragon, and slicing that gives jagged sections whose
        # layers stop covering each other — it reported 2584 mm2 of island
        # on a model that has none. What is bounded instead is the number
        # of slices, in orient itself.
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

    out = dict(id=pid, glb=glb, bodies=len(meshes),
               printability=printability,
               tris=kept, tris_full=full,
               dims=src_ext, tiled_dims=[round(float(v), 1) for v in ext],
               biggest_body=biggest,
               kb=kb)
    if budget and kept > budget:
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


def _builder_stamp():
    """This file's own mtime, folded into every preview's cache key.

    The stamp covered the source files and not the code that turns them
    into a preview, so fixing the layout changed nothing: every preview
    stayed cached with the arrangement the old code produced. A cache that
    does not notice its builder changed is the same bug as one that does
    not notice its source changed.
    """
    try:
        return int(os.path.getmtime(os.path.abspath(__file__)))
    except OSError:
        return 0


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
        # the toy, not every file that can supply a piece of it
        core = [m for m in k["members"] if m.get("role", "part") == "part"]
        for m in (core or k["members"]):
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
            s += f"|b{_builder_stamp()}"
        except OSError:
            continue
        old = have.get(pid)
        # glb is None for every PART -- only a kit needs a composite file,
        # a part has its own 3MF the browser reads. So a null glb is the
        # normal case, not a failure: check the file only when there is
        # one to check. Requiring it outright joined None onto a path and
        # crashed; requiring it truthy instead rebuilt every part on every
        # run, which is why a pass reported 76 built and 5 cached.
        if (old and old.get("stamp") == s
                and (not old.get("glb")
                     or os.path.exists(os.path.join(ROOT, old["glb"])))):
            out.append(old)
            kept += 1
            continue
        try:
            # Only a composite needs a file of its own. A part has a real
            # 3MF or STL the browser can read; a kit's card shows every
            # member together and nothing on disk is that.
            e = build_one(pid, path, a.budget,
                          write=pid.startswith("kit_"))
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
