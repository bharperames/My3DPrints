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
