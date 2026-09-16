#!/usr/bin/env python3
"""Flexi Factory's skeleton T-Rex, with a gum trough instead of teeth.

NOT this project's geometry. Flexi Factory's model is paid for and stays in
Brett's ~/Downloads; nothing here is copied into the repo. This reads the
file he owns and writes a derivative for his own printer, which is what the
generator exists to do -- it refuses with a clear message if the source is
not on disk.

WHAT THE PAINT GIVES US

The designer painted the teeth and the paint ships in the 3MF: one
`paint_color` attribute per triangle, '8' for teeth and claws and '4' for
bone. So which triangles are a tooth is the author's own answer, not a
detector's guess, and every tooth arrives complete down to the ring where it
meets the jaw. That is worth knowing because the obvious readings are both
wrong: the head is a single watertight body, so the teeth are not separate
objects, and a curvature detector finds 18 cones on the skull where the
author painted 14.

THE TROUGH, AND WHY IT IS NOT FIFTY SOCKETS

Brett's idea, and a better one than the sockets first tried: one channel
following the gum line, which small tooth roots can be set anywhere along
and bedded in black epoxy. It is also far more robust to build -- individual
mirrored sockets failed on 4 of 14 teeth and shattered the skull into
fragments, where the channel is a single continuous cut.

IT HAS TO BE CENTRED ON THE BONE, NOT ON THE TEETH

Measured on this skull, the teeth sit 0.88 mm outboard of the middle of the
jaw ridge, and the ridge is only 6.13 mm wide (4.99 at its narrowest). A
3.5 mm trough centred on the tooth positions breaks through the palate for
81% of its length. Centred on the ridge instead, the same 3.5 mm clears
everywhere but 2% of samples, and the finished skull's thinnest wall is
0.40 mm -- exactly what the untouched skull already had, so the trough takes
nothing away from what the designer shipped.

THE CLAWS STAY ON, AND THAT IS DELIBERATE

The same treatment was built for the foot talons and the hand claws and then
taken back out. The foot talons are what the model stands on -- cut them and
he does not stand up -- and the hand claws are small enough that swapping
them for real ones buys little. The paint marks them, so they are easy to
find again if that ever changes; the reason not to is mechanical, not
technical.
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SRC = os.path.expanduser(
    "~/Downloads/FlexiFactory/Flexi Factory Skeleton T-Rex_stls_all/"
    "Bambu Flexi Factory Skeleton T-Rex_Curved.3mf")

OBJ = {
    "bone":   "3D/Objects/Flexi Factory Skeleton T-Rex bone.stl_43.model",
    "head":   "3D/Objects/Flexi Factory Skeleton T-Rex Head without Eye.stl_46.model",
    "eyes":   "3D/Objects/Flexi Factory Skeleton T-Rex Head with Eye.stl_45.model",
    "body":   "3D/Objects/Flexi Factory Skeleton T-Rex Body_Curved.stl_47.model",
}

PARTS = {
    "testjaw":   ("head", "test", "the gum arcs alone, for trying teeth and epoxy"),
    "skull":     ("head", "cut",  "the eyeless skull, ready for real teeth"),
    "body":      ("body", "jaw",  "the body, its lower jaw ready for real teeth"),
    "skullorig": ("head", None,   "the eyeless skull as the designer drew it"),
    "eyes":      ("eyes", None,   "the skull with eyes"),
    "bodyorig":  ("body", None,   "the body exactly as the designer drew it"),
    "bone":      ("bone", None,   "the loose bone that comes with the set"),
}

TOOTH_PAINT = "8"
WIDTH, DEPTH = 3.5, 3.0
# How deep the shelf is allowed to get where the bone can carry it. At 3.0
# it is the flat depth the first skull printed with, made safe; above that
# the shelf follows the maxilla down where the maxilla is deep, which is
# where the putty and the tooth roots want the room.
DEPTH_MAX = 3.5
# The socket cutter's settled dials. A prism swept square to the jaw, its
# section the designer's own tooth outline inset by INSET: the inset is what
# protects the lip, so nothing downstream has to clip the socket back and the
# mouth stays as wide as the floor. 1.0 is the value that fits all fourteen
# teeth -- at 0.6 the bone behind the rearmost one has no room for a socket.
#
# 1.2 rather than 1.0 because 1.0 drills THROUGH the jaw at teeth 10 and 11:
# the skull's genus goes 8 -> 10, two tunnels the designer did not have. The
# part stays watertight either way -- a tunnel through a solid is still a
# closed manifold -- so nothing but a genus count catches it. At 1.2 those
# sockets narrow to 1.8 and the count comes back to 8.
INSET = 1.2


def load(member):
    from paint import read
    if not os.path.exists(SRC):
        raise SystemExit(json.dumps({
            "ok": False,
            "error": f"source model not found: {SRC}. This derives from Flexi "
                     f"Factory's paid model, which is not redistributed here."}))
    V, F, P = read(SRC, member)
    return trimesh.Trimesh(V, F, process=False), P


def tidy(mesh):
    """Weld and drop degenerate faces before judging what is a real part.

    A boolean leaves zero-area slivers, and they are not visible to a split
    until the vertices are welded -- filtering first and exporting after put
    thirty-seven two-triangle shells into the STL that were not there when
    the filter ran.
    """
    m = mesh.copy()
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.update_faces(m.unique_faces())
    m.remove_unreferenced_vertices()
    return m


def keep_real(mesh, floor=1.0, min_faces=32, single=False):
    """Drop the boolean's debris, keep every real part.

    The body is twenty-five separate pieces by design, so taking the largest
    component would throw the animal away and leave the rib cage. Judge on
    ABSOLUTE volume and on face count: a boolean leaves shells whose winding
    is inside out, and those measure a negative volume that a `> floor` test
    silently keeps while dropping a real part. Normals are fixed first so
    the survivors all read positive.
    """
    parts = []
    for p in tidy(mesh).split(only_watertight=False):
        if len(p.faces) < min_faces or abs(p.volume) <= floor:
            continue
        trimesh.repair.fix_normals(p)
        parts.append(p)
    return trimesh.util.concatenate(parts) if parts else mesh


def painted_regions(mesh, paint):
    idx = np.where(paint == TOOTH_PAINT)[0]
    lab = trimesh.graph.connected_component_labels(
        trimesh.graph.face_adjacency(mesh.faces[idx]), node_count=len(idx))
    return [idx[lab == r] for r in range(lab.max() + 1)]


def jaw_regions(mesh, paint):
    """The lower jaw's teeth, out of everything the designer painted.

    The body carries paint on far more than teeth -- vertebra caps, the
    scapula, the claws -- so the teeth have to be picked out. A tooth row is
    the tell: the jaw is the one loose piece carrying twelve small painted
    patches, where every other piece carries one big one or, on the legs and
    arms, three and one. Chosen by that rather than by a body index, which
    is an ordering and not a fact about the animal.
    """
    regions = painted_regions(mesh, paint)
    lab = trimesh.graph.connected_component_labels(
        mesh.face_adjacency, node_count=len(mesh.faces))
    by = {}
    for r in regions:
        by.setdefault(lab[r[0]], []).append(r)
    piece = max(by, key=lambda b: len(by[b]))
    return by[piece]


def deburr(mesh, wall=0.35, keep=0.15, pitch=0.2, passes=3):
    """Take off the paper-thin flaps a cut leaves, and nothing else.

    Where the channel passes close to the outside of the bone it can leave a
    sheet a couple of tenths thick: too thin to print as anything but a
    ragged fin, and the thing Brett kept seeing. Narrowing the channel does
    not fix it -- a pair of rays at mid-depth reports the ridge a healthy
    6 mm wide at every station while the sheets form above and below where
    the surface falls away.

    So the sliver is removed rather than preserved: the channel breaks out
    to the surface there, which is honest, instead of leaving a flap. Found
    by morphological opening, which is exactly the question being asked --
    what material survives no erosion by `wall`. The threshold is set from
    the designer's own skull: his largest such lump is 0.13 mm3, so only
    lumps bigger than that are ours to answer for.
    """
    from scipy import ndimage
    # One pass does not converge: taking a sliver off exposes the slightly
    # thicker material behind it, which is itself under the limit. Three
    # passes is enough here -- it stops on its own when nothing is left over
    # the threshold.
    for _ in range(passes - 1):
        out = _deburr_once(mesh, wall, keep, pitch)
        if out is mesh: return mesh
        mesh = out
    return _deburr_once(mesh, wall, keep, pitch)


def _deburr_once(mesh, wall, keep, pitch):
    from scipy import ndimage
    vox = mesh.voxelized(pitch=pitch).fill()
    G = vox.matrix
    d = ndimage.distance_transform_edt(G) * pitch
    core = d > wall
    if not core.any(): return mesh
    opened = (ndimage.distance_transform_edt(~core) * pitch) <= wall
    thin = G & ~opened
    lab, n = ndimage.label(thin)
    if n == 0: return mesh
    sz = np.array(ndimage.sum(thin, lab, range(1, n + 1))) * pitch ** 3
    big = np.where(sz > keep)[0] + 1
    if not len(big): return mesh
    # one convex hull per sliver -- a sheet is nearly flat, so its hull is
    # the sheet, and this needs no meshing library the venv does not have
    cuts = []
    for c in big:
        pts = vox.indices_to_points(np.argwhere(lab == c))
        if len(pts) < 8: continue
        lo, hi = pts.min(axis=0) - pitch, pts.max(axis=0) + pitch
        box = np.array([[x, y, z] for x in (lo[0], hi[0])
                        for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
        try:
            cuts.append(trimesh.Trimesh(np.vstack([pts, box])).convex_hull)
        except Exception:
            continue
    if not cuts: return mesh
    try:
        out = trimesh.boolean.difference(
            [mesh, trimesh.boolean.union(cuts, engine="manifold")],
            engine="manifold")
    except Exception:
        return mesh
    return out if out.volume > 0.9 * mesh.volume else mesh


def trough(mesh, paint, width=WIDTH, depth=DEPTH, regions=None,
           depth_max=DEPTH_MAX, scrub=False, **extra):
    from channel import tooth_frames, channel
    regions = painted_regions(mesh, paint) if regions is None else regions
    # a tooth is a cone, so its own convex hull is the tooth
    cuts = [mesh.submesh([r], append=True).convex_hull for r in regions]
    cuts += channel(mesh, tooth_frames(mesh, regions), regions=regions,
                    width=width, depth=depth, over=1.0, centre=True,
                    depth_max=depth_max, **extra)
    u = trimesh.boolean.union(cuts, engine="manifold")
    was = len(mesh.split(only_watertight=False))
    # `deburr` is a morphological opening over the WHOLE part, and on the body
    # it costs 418 s of a 420 s build -- 84% of it.
    #
    # It is NOT free to skip, which is what I assumed before measuring it: on
    # the skull it takes 40 mm3 off an 8084 mm3 part and drops 3100 faces, so
    # it is still finding thin material even under the drill. Off for a live
    # preview, where 0.7 s against 43 s is the difference between a slider
    # that responds and one that does not; ON for anything going to a plate.
    got = trimesh.boolean.difference([mesh, u], engine="manifold")
    if scrub: got = deburr(got)
    got = keep_real(got, single=(was == 1))
    # A cut cannot make new objects. Where a pocket's inboard sweep severs a
    # strut at the back of the mouth it frees a piece of the inner palate --
    # 117 mm3 of it, which would print as a loose lump sitting in the jaw.
    # If the part went in whole it comes out whole.
    if was == 1:
        parts = got.split(only_watertight=False)
        if len(parts) > 1:
            got = max(parts, key=lambda p: abs(p.volume))
    return got, len(regions)


def test_jaw(mesh, paint, width=WIDTH, depth=DEPTH, wall=1.5):
    """The gum arc on its own: the channel plus just enough bone to hold it.

    Printing the whole skull to find out whether a tooth root sits in the
    trough is an hour for an answer a few minutes can give. This keeps the
    bone inside a box swept along the same path -- the channel plus `wall`
    either side and underneath -- and throws the rest of the skull away, so
    what comes out is the real curve, the real width and the real depth.
    """
    from channel import tooth_frames, gum_path, band_boxes
    cut, n = trough(mesh, paint, width, depth)
    idx = np.where(paint == TOOTH_PAINT)[0]
    lab = trimesh.graph.connected_component_labels(
        trimesh.graph.face_adjacency(mesh.faces[idx]), node_count=len(idx))
    fr = tooth_frames(mesh, [idx[lab == r] for r in range(lab.max() + 1)])
    # A region to keep, not a cut: the swept box is fine for this, and the
    # offset shell would be the wrong tool -- it defines a lip, not a slab.
    C, N, A, U = gum_path(mesh, fr)
    keep = band_boxes(C, A, U, width + 2 * wall, depth + wall, wall)
    box = trimesh.boolean.union(keep, engine="manifold")
    got = trimesh.boolean.intersection([cut, box], engine="manifold")
    # The skull's tooth rows are not joined by a continuous bar of bone --
    # left and right are separate arcs and the openings break them further
    # -- so this comes out in pieces however generously the box is drawn.
    # Keep the arcs worth printing and drop the chips the cut shears off.
    pieces = sorted((p for p in tidy(got).split(only_watertight=False)
                     if len(p.faces) >= 32), key=lambda p: -abs(p.volume))
    if not pieces: return got, n
    big = [p for p in pieces if abs(p.volume) >= 0.15 * abs(pieces[0].volume)]
    for p in big: trimesh.repair.fix_normals(p)
    return trimesh.util.concatenate(big), n


def build(names, width=WIDTH, depth=DEPTH, depth_max=DEPTH_MAX, scrub=False,
          **extra):
    out, rep = [], {}
    for name in names:
        member, how, _ = PARTS[name]
        m, paint = load(OBJ[member])
        n = 0
        if how == "test":
            m, n = test_jaw(m, paint, width, depth)
        elif how == "jaw":
            m, n = trough(m, paint, width, depth,
                          regions=jaw_regions(m, paint),
                          depth_max=depth_max, scrub=scrub, **extra)
        elif how == "cut":
            m, n = trough(m, paint, width, depth, depth_max=depth_max,
                          scrub=scrub, **extra)
        out.append((name, m))
        rep[name] = dict(faces=len(m.faces), volume=round(float(m.volume), 1),
                         teeth_removed=n)
    return out, rep


def layout(items, gap=4.0):
    """Lay the chosen parts out in a row on the bed, largest first."""
    items = sorted(items, key=lambda kv: -kv[1].extents[0] * kv[1].extents[1])
    sc, x = trimesh.Scene(), 0.0
    for name, m in items:
        g = m.copy()
        g.apply_translation(-g.bounds[0])
        g.apply_translation([x, 0, 0])
        sc.add_geometry(g, geom_name=f"trex_{name}")
        x += g.extents[0] + gap
    return sc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", default="skull,body",
                    help="comma-separated: " + ", ".join(PARTS))
    ap.add_argument("--width", type=float, default=WIDTH,
                    help="gum trough width (mm)")
    ap.add_argument("--depth", type=float, default=DEPTH,
                    help="gum trough depth (mm)")
    ap.add_argument("--depth-max", type=float, default=DEPTH_MAX,
                    help="deepest the shelf may go where the bone allows (mm)")
    ap.add_argument("--inset", type=float, default=INSET,
                    help="how far inside the tooth outline the socket sits (mm)")
    ap.add_argument("--out")
    a = ap.parse_args()
    names = [p.strip() for p in a.parts.split(",") if p.strip()]
    bad = [n for n in names if n not in PARTS]
    if bad:
        print(json.dumps({"ok": False, "error": f"unknown part(s): {bad}. "
                                                f"choose from {list(PARTS)}"}))
        return 1
    items, rep = build(names, a.width, a.depth, a.depth_max,
                       scrub=True, inset=a.inset)
    sc = layout(items)
    out = a.out or os.path.join(os.path.dirname(HERE), "models", "custom",
                                "trex-" + "-".join(names) + ".3mf")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sc.export(out)
    ext = sc.extents
    print(json.dumps({"ok": True, "parts": names, "file": os.path.basename(out),
                      "span": [round(float(ext[0]), 1), round(float(ext[1]), 1)],
                      "height": round(float(ext[2]), 1),
                      "single_colour": True, "detail": rep}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
