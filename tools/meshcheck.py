#!/usr/bin/env python3
"""Verify what was written, rather than repair what was built.

3MF stores coordinates to finite precision, so surfaces that meet
tangentially can come back as duplicate faces even when the solid was sound
in memory. The temptation is to quantise and drop duplicates on the way out.
Resist it: a silent repair hides the geometry that caused the slivers. Both
generators here shipped a repair for months, and behind each one sat a real
defect — a socket lip chamfered to a knife edge, and seat bars whose end
caps grazed the rim ring they were supposed to be buried in. Neither was
visible while the mesh was being cleaned up on the way out.

So: check the file, name the defect, refuse to ship. Fix the design.
"""
import trimesh


def export_defects(path):
    """Open and non-manifold edges in a written file, by body. {} is clean."""
    sc = trimesh.load(path, force="scene")
    bad = {}
    for name, g in sc.geometry.items():
        open_e = len(trimesh.grouping.group_rows(g.edges_sorted,
                                                 require_count=1))
        nm = len(trimesh.grouping.group_rows(g.edges_sorted, require_count=4))
        if open_e or nm:
            bad[name] = dict(open_edges=open_e, nonmanifold_edges=nm)
    return bad


if __name__ == "__main__":
    import json
    import sys
    for p in sys.argv[1:]:
        print(json.dumps({p: export_defects(p) or "clean"}))


def budget_faces(counts, budget):
    """Share a face budget between meshes so small parts survive it.

    Cutting every mesh by the same proportion is the obvious rule and it
    ruins the small ones: in a set with an 88,000-face base plate, the
    wrench's 4,736 faces were cut to 1,086 along with everything else, and
    a prismatic part that has lost three quarters of its faces is a ribbon.
    The big mesh loses nothing it can be seen to lose; the small one loses
    its shape.

    So the budget is shared max-min: everything under a fair share is kept
    whole, and what it does not use goes back to the meshes that are over.
    Returns a target face count per mesh, in the order given.
    """
    order = sorted(range(len(counts)), key=lambda i: counts[i])
    out = [0] * len(counts)
    left, n = float(budget), len(counts)
    for i in order:
        share = left / max(n, 1)
        if counts[i] <= share:
            out[i] = counts[i]          # small enough to keep entire
            left -= counts[i]
        else:
            out[i] = int(share)
            left -= share
        n -= 1
    return out
