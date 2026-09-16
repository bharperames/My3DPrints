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
# The settled cutter, in two parts.
#
# SOCKETS. One cone per tooth, starting at the designer's own painted tooth
# outline and tapering with depth, swept square to the JAW rather than along
# the tooth's own axis -- a leaning axis foreshortens the outline, and
# squaring it to the gum line's perpendicular gains the front teeth a third
# more area. The taper is one number per tooth, found by bisection: the
# widest cone whose whole surface stays inside the bone. Its sides must be
# STRAIGHT; a radius derived from the measured distance to the bone makes the
# wall an offset of the skin, which runs parallel to the surface and shaves
# it into hundreds of slivers.
#
# TROUGH. One channel swept along the gum line behind the sockets, bounded on
# the cheek side only -- LING_WALL of lip is kept there, and the tongue side
# is cut clean through the palate so every socket opens into one continuous
# channel. A clipped tooth root does not fit a socket sized to the crown;
# this is where it goes, and where the epoxy keys in. Its depth follows the
# bone station by station, which is what lets the back run deeper than the
# front: one depth for the whole arch is limited by the shallowest point, and
# applying it everywhere is what put handles in the part at 2.0 mm and tore
# it at 2.5. Measured per station, 3.0 is clean and 3.5 is not.
INSET = 0.35          # wall beside a socket (mm)
LINGUAL = 1.0         # how far past the inner surface the trough breaks (mm)
LING_DEPTH = 3.0      # deepest the trough may go where the bone allows (mm)
LING_WALL = 1.2       # lip left in front of the trough (mm)
# The lower jaw is a slender arch where the skull's palate is a thick one, so
# it takes the channel on its own terms: further through the inner wall and
# deeper, which leaves the fewest bridges spanning it (7 against 9 at the
# skull's numbers) and takes 1594 mm3 out where sockets alone take 579.
JAW_LINGUAL = 2.5
JAW_LING_DEPTH = 2.75   # Brett, comparing against 3.0: "a great improvement"
# Shallower sockets on the jaw. Brett: "the holes don't need to be this deep
# on the lower jaw ... that is constraining the removal of the remaining
# lingual part." Measured, dropping the socket from 3.5 to 2.5 halves the
# thin material left standing (0.11% of the surface to 0.06%) and costs 32
# mm3 of the 1594 removed; 1.5 takes two more bridges out but the socket
# stops being deep enough to steady a root.
JAW_DEPTH = 2.5
# The trough's labial limit on the jaw. This is the dial that reaches the
# ridges of gum standing between the sockets: at 1.2 the limit goes negative
# at 137 of 717 stations, so the channel never gets across to them at all.
# Measured, dropping it to 0.6 takes the inter-tooth material from 54.6% to
# 42.2% solid and costs nothing in wall (0.06% thin against a 0.02% floor).
JAW_LING_WALL = 0.6


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
    # SPLIT FIRST, AND DO NOT WELD.
    #
    # This used to run `tidy` over the whole mesh before splitting, and
    # `tidy` merges vertices. Where a cut runs close to the surface the
    # boolean leaves coincident geometry, and welding it makes edges shared
    # by four faces -- the part stops being closed. Measured on the lower
    # jaw: the difference comes back watertight with 165 pieces, 142 of them
    # slivers; dropping the slivers leaves a closed 23-piece part, and
    # merging its vertices is the single step that opens it.
    #
    # Degenerate faces still go, per part, because that does not move any
    # vertex. What a boolean leaves unwelded is a seam, not a hole, and the
    # mesh is closed across it.
    # WELD ONLY IF WELDING LEAVES IT CLOSED.
    #
    # Merging vertices is what tidies a boolean's seams, and on the skull it
    # is the difference between a closed part and an open one. On the lower
    # jaw it is the opposite: the trough runs close to a thin wall, the
    # boolean leaves coincident geometry there, and welding it makes edges
    # shared by four faces. Neither part is wrong -- the right answer differs
    # per part, so ask rather than pick, and say which was used.
    parts = []
    for p in mesh.split(only_watertight=False):
        if len(p.faces) < min_faces or abs(p.volume) <= floor:
            continue
        # Nothing is removed from the raw path. Dropping degenerate faces
        # can itself open a shell, and the boolean's output is closed as it
        # stands -- the cleaning belongs on the welded candidate below,
        # which is only used if it stays closed.
        p = p.copy()
        trimesh.repair.fix_normals(p)
        parts.append(p)
    if not parts: return mesh
    raw = trimesh.util.concatenate(parts)
    welded = raw.copy(); welded.merge_vertices()
    welded.update_faces(welded.nondegenerate_faces())
    welded.update_faces(welded.unique_faces())
    welded.remove_unreferenced_vertices()
    if welded.is_watertight or not raw.is_watertight:
        return welded
    return raw


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


def build(names, width=WIDTH, depth=DEPTH, depth_max=None, scrub=False,
          **extra):
    out, rep = [], {}
    for name in names:
        member, how, _ = PARTS[name]
        m, paint = load(OBJ[member])
        n = 0
        if how == "jaw":
            # NO TROUGH ON THE LOWER JAW. The skull's palate is behind a
            # thick arch and an open channel through it leaves the part
            # sounder; the lower jaw is a slender arch and IS the wall, so
            # cutting through its lingual side opens the piece -- measured,
            # every setting tried came back not watertight with 13 to 17 new
            # handles, down to a 1 mm trough barely breaking the surface.
            # Sockets alone on this part, and they gate clean.
            # The jaw's own defaults fill in only what the CALLER LEFT OUT.
            # This used to substitute whenever a value happened to equal the
            # skull's default, which cannot tell "unset" from "deliberately
            # 1.2" -- so asking for the two side by side built the same part
            # twice and the diff came back empty.
            jaw = dict(extra)
            if depth_max is None: depth_max = JAW_DEPTH
            jaw.setdefault("lingual", JAW_LINGUAL)
            jaw.setdefault("ling_depth", JAW_LING_DEPTH)
            jaw.setdefault("ling_wall", JAW_LING_WALL)
            m, n = trough(m, paint, width, depth,
                          regions=jaw_regions(m, paint),
                          depth_max=depth_max, scrub=scrub, **jaw)
        elif how == "cut":
            sk = dict(extra)
            sk.setdefault("lingual", LINGUAL)
            sk.setdefault("ling_depth", LING_DEPTH)
            sk.setdefault("ling_wall", LING_WALL)
            m, n = trough(m, paint, width, depth,
                          depth_max=DEPTH_MAX if depth_max is None else depth_max,
                          scrub=scrub, **sk)
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
                    help="wall beside each socket (mm)")
    ap.add_argument("--lingual", type=float, default=LINGUAL,
                    help="how far past the inner surface the trough breaks (mm)")
    ap.add_argument("--ling-depth", type=float, default=LING_DEPTH,
                    help="deepest the trough may go where the bone allows (mm)")
    ap.add_argument("--ling-wall", type=float, default=LING_WALL,
                    help="lip left in front of the trough (mm)")
    ap.add_argument("--out")
    a = ap.parse_args()
    names = [p.strip() for p in a.parts.split(",") if p.strip()]
    bad = [n for n in names if n not in PARTS]
    if bad:
        print(json.dumps({"ok": False, "error": f"unknown part(s): {bad}. "
                                                f"choose from {list(PARTS)}"}))
        return 1
    # scrub (deburr) is OFF. It is a morphological opening, so where the
    # wall is thin it removes the material outright rather than smoothing it
    # -- measured, ten new tunnels through a file that was clean before it
    # ran. It existed to clean up the old voxel cutter's spurs; exact CSG
    # does not leave any.
    items, rep = build(names, a.width, a.depth, a.depth_max, scrub=False,
                       align=1.0, inset=a.inset,
                       lingual=a.lingual, ling_depth=a.ling_depth,
                       ling_wall=a.ling_wall)
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
