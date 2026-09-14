"""Take the teeth off and leave a trough along the gum line.

The teeth come from the designer's own paint, not from a detector: each
tooth is a `paint_color` region in the 3MF, complete down to the ring where
it meets the bone. Those rings give a centre, an axis and a width apiece,
and threading them in order gives the gum line.

The teeth come off with their own convex hulls. The ledge behind them is
cut by ONE solid, built as an offset from the cheek skin rather than swept
along the gum line -- see `shell_ledge` for why the swept version had to go.
"""
import numpy as np, trimesh

def tooth_frames(mesh, regions):
    """centre, outward axis and half-width of each painted tooth's base."""
    out = []
    for faces in regions:
        sub = mesh.submesh([faces], append=True); sub.merge_vertices()
        ents = list(sub.outline().entities)
        if not len(ents): continue
        ring = sub.vertices[np.unique(max((np.asarray(e.points) for e in ents), key=len))]
        c = ring.mean(axis=0)
        n = np.linalg.svd(ring - c)[2][2]
        tip = sub.vertices[np.argmax(np.abs((sub.vertices - c) @ n))]
        if np.dot(tip - c, n) < 0: n = -n
        out.append(dict(c=c, n=n, L=float(np.max((sub.vertices - c) @ n)),
                        r=float(np.max(np.linalg.norm(ring - c, axis=1))),
                        ring=ring))
    return out

def order_along_jaw(frames):
    """Thread the teeth into one chain: nearest neighbour from an end."""
    C = np.array([f["c"] for f in frames])
    d = np.linalg.norm(C[:, None] - C[None], axis=2)
    start = int(np.unravel_index(np.argmax(d), d.shape)[0])
    order, left = [start], set(range(len(C))) - {start}
    while left:
        nxt = min(left, key=lambda j: d[order[-1], j])
        order.append(nxt); left.discard(nxt)
    return order

def extend(C, N, run=7.0):
    """Run the path out past the first and last tooth.

    Stopping at the end tooth leaves the last box cutting a square notch,
    and the bone between that notch and the edge of the jaw survives as a
    rectangular tab -- which is what a channel that ends in mid-bone looks
    like. Carrying the path straight on past both ends until it is clear of
    the jaw lets the cut run out through the end instead of stopping in it.
    """
    d0 = C[0] - C[1]; d0 /= max(np.linalg.norm(d0), 1e-9)
    d1 = C[-1] - C[-2]; d1 /= max(np.linalg.norm(d1), 1e-9)
    C = np.vstack([C[0] + d0 * run, C, C[-1] + d1 * run])
    N = np.vstack([N[0], N, N[-1]])
    return C, N


def resample(C, N, per_mm=1.5):
    """Dense samples along the gum line, with the axis carried along.

    Threading straight from one tooth base to the next leaves the trough
    faceted, and where two segments meet at an angle the join sticks out of
    the bone. Sampling the path finely instead makes the steps small enough
    to disappear into the surface.
    """
    seg = np.linalg.norm(np.diff(C, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    n = max(len(C), int(s[-1] * per_mm))
    u = np.linspace(0, s[-1], n)
    Ci = np.column_stack([np.interp(u, s, C[:, k]) for k in range(3)])
    Ni = np.column_stack([np.interp(u, s, N[:, k]) for k in range(3)])
    Ni /= np.linalg.norm(Ni, axis=1)[:, None]
    return Ci, Ni

def _frame(C, N, k):
    """tangent and outward axis at sample k."""
    t = C[min(k + 1, len(C) - 1)] - C[max(k - 1, 0)]
    if np.linalg.norm(t) < 1e-9: return None
    t = t / np.linalg.norm(t)
    a = np.cross(N[k], t)
    if np.linalg.norm(a) < 1e-9: return None
    return t / np.linalg.norm(t), a / np.linalg.norm(a)


def smooth(C, N, passes=6, win=9):
    """Take the jitter out of the path before anything is built on it.

    The path is a gum line: it is smooth, and the per-tooth measurement that
    produced it is what is noisy.
    """
    C, N = C.copy(), N.copy()
    k = np.ones(win) / win
    for _ in range(passes):
        for arr in (C, N):
            pad = np.vstack([np.repeat(arr[:1], win // 2, axis=0), arr,
                             np.repeat(arr[-1:], win // 2, axis=0)])
            for c in range(3):
                arr[:, c] = np.convolve(pad[:, c], k, mode="valid")
        N /= np.linalg.norm(N, axis=1)[:, None]
    return C, N


def tooth_lip(C, A, frames):
    """Where the cut belongs: the labial edge of the painted tooth bases.

    Brett's answer, and it ends the guessing. Every offset rule tried here --
    constant wall, isotropic erosion, a share of the local thickness -- was an
    attempt to infer a line the designer had already drawn. Each tooth's paint
    goes down to the ring where it met the bone, and the OUTER edge of that
    ring is exactly where the lip's inner face should be, because that is
    where a tooth stood. Put the cut there and a real tooth sits where the
    printed one did, with the visible lip in front of it untouched.

    Returns, per station, how far outboard of the gum line the cut may reach.
    """
    lip = np.full(len(C), np.nan)
    cs = np.array([f["c"] for f in frames])
    for f in frames:
        k = int(np.argmin(np.linalg.norm(C - f["c"], axis=1)))
        lip[k] = float(np.max((f["ring"] - C[k]) @ A[k]))
    g = ~np.isnan(lip)
    if not g.any(): return np.zeros(len(C))
    # between the teeth there is no ring to read, so run the line through
    lip = np.interp(np.arange(len(C)), np.where(g)[0], lip[g])
    win = 15
    pad = np.concatenate([np.repeat(lip[:1], win // 2), lip,
                          np.repeat(lip[-1:], win // 2)])
    return np.convolve(pad, np.ones(win) / win, mode="valid")


def gum_path(mesh, frames):
    """The smoothed gum line, with an outward axis and an up axis per sample."""
    order = order_along_jaw(frames)
    C, N = extend(np.array([frames[i]["c"] for i in order]),
                  np.array([frames[i]["n"] for i in order]))
    C, N = resample(C, N)
    C, N = smooth(C, N)
    mid = mesh.centroid
    A = np.zeros_like(C); U = np.zeros_like(C); ok = np.zeros(len(C), bool)
    for k in range(len(C)):
        f = _frame(C, N, k)
        if f is None: continue
        t, a = f
        if np.dot(a, C[k] - mid) < 0: a = -a
        u = np.cross(t, a); u /= np.linalg.norm(u)
        if np.dot(u, N[k]) < 0: u = -u
        A[k], U[k], ok[k] = a, u, True
    return C[ok], N[ok], A[ok], U[ok]


def band_boxes(C, A, U, width, depth, over):
    """A generous swept volume along the gum line.

    Only for picking a REGION -- the test jaw uses it to decide how much
    bone to keep around the arc. Nothing precise is cut with it; see
    `shell_ledge` for the reason.
    """
    step = float(np.median(np.linalg.norm(np.diff(C, axis=0), axis=1)))
    out = []
    for k in range(len(C)):
        t = np.cross(A[k], U[k])
        box = trimesh.creation.box([width, 2.2 * step, depth + over])
        M = np.eye(4); M[:3, 0], M[:3, 1], M[:3, 2] = A[k], t, U[k]
        M[:3, 3] = C[k] + U[k] * (over - depth) / 2.0
        box.apply_transform(M); out.append(box)
    return out


def _sink(mesh, pts, axis, out, wall):
    """Push a solid in along `axis` until it clears the skin by `wall`."""
    hit, ri, _ = mesh.ray.intersects_location(
        pts, np.tile(out, (len(pts), 1)), multiple_hits=False)
    d = np.full(len(pts), -wall)                  # no hit: already outside
    if len(ri): d[ri] = np.linalg.norm(hit - pts[ri], axis=1)
    drop = float(np.max((wall - d) / max(float(np.dot(axis, out)), 0.30)))
    return pts - axis * max(drop, 0.0)


def drill_ledge(mesh, regions, frames, depth=6.0, wall=1.6, reach=7.0,
                keep=0.9, grow=1.0):
    """Drill each tooth out, and bridge between neighbours. Exact solids.

    Brett's construction. The designer painted each tooth down to the ring
    where it met the bone, so the tooth's own hull, swept down its own axis
    and inboard, is the pocket that tooth came out of -- a real tooth with
    its root snapped off goes back where the printed one stood.

    Fourteen pockets leave a spike of bone between each pair. An earlier
    version rounded those off with a morphological closing on a voxel grid,
    and that is what made the result stop looking like a drilled hole: a
    0.18 mm blurred iso-surface subtracted from a smooth solid leaves
    paper-thin shells and speckles wherever the cutter runs tangent to the
    skin. Brett: "it needs to push the surface, like cutting a hole in a
    solid ... it clearly has violated the idea that the skull is solid".

    So there are no voxels here. The spikes are taken by BRIDGES: the convex
    hull spanning each adjacent pair of pockets. Hulls and unions of hulls
    are exact, the boolean is exact, and what comes out has crisp walls.

    Every solid -- pockets and bridges alike -- is sunk along the tooth axis
    until it clears the cheek by `wall`. A bridge spans the chord between two
    teeth and would otherwise cut the lip where the jaw bows out between
    them, so it has to be sunk on its own account, not on its neighbours'.
    """
    order = order_along_jaw(frames)
    C, N, A, U = gum_path(mesh, frames)
    from scipy.spatial import cKDTree
    tree = cKDTree(C)

    def run(origin, d, cap):
        """How far a sweep may go before it leaves the bone.

        The FIRST crossing, not the last. Taking the farthest hit measured to
        the far side of the skull, so at the back of the jaw -- where the bone
        is thin and the ray carries on across the mouth -- the sweep ran
        straight out through the outer surface.
        """
        # Cast from every point on the tooth's base ring, not just its
        # centre. A pocket is a solid: bounding it by one ray down the middle
        # leaves its corners free, and where the frame tilts at the back of
        # the jaw those corners drove up and out through the side wall.
        origin = np.atleast_2d(origin)
        hit, ri, _ = mesh.ray.intersects_location(
            origin, np.tile(d, (len(origin), 1)), multiple_hits=False)
        if not len(ri): return 0.0
        per = np.full(len(origin), np.inf)
        for h, r in zip(hit, ri):
            per[r] = min(per[r], float(np.linalg.norm(h - origin[r])))
        per = per[np.isfinite(per)]
        if not len(per): return 0.0
        return float(min(cap, max(0.0, float(per.min()) - keep)))

    swept, axes, outs = {}, {}, {}
    for i, (faces, f) in enumerate(zip(regions, frames)):
        V = mesh.submesh([faces], append=True).vertices
        out = A[int(tree.query(f["c"])[1])]
        n = f["n"]
        c = f["ring"].mean(axis=0)
        # Bound BOTH sweeps by the bone that is actually there. A fixed 7 mm
        # inboard is what ate the palate -- 4937 mm3, more than half the
        # skull -- and it is the same mistake as reach=9 on the box cutter.
        probe = c[None, :]
        inb = run(probe, -out, reach)
        dwn = run(probe, -n, depth)
        # Widen the pocket along the jaw so neighbours overlap. Fourteen
        # separate drills leave a spike of bone standing between each pair;
        # bridging them with a convex hull spanning two pockets fills the
        # arch instead (4937 mm3, more than half the skull). Growing each
        # pocket sideways merges them where they are adjacent and nowhere
        # else, and it is still one exact hull per tooth.
        tan = np.cross(n, out)
        tan = tan / max(np.linalg.norm(tan), 1e-9)
        W = np.vstack([V + tan * grow, V - tan * grow])
        pts = np.vstack([W, W - n * dwn, W - out * inb, W - n * dwn - out * inb])
        # CLIP, do not sink. Sinking the whole pocket until it cleared the
        # cheek buried the channel: the teeth came away but the gum closed
        # over as a rounded bulge with no trough for the putty. The pocket
        # has to stay open at the gum line and simply stop where the lip
        # begins -- so cut it with a plane, which is exact on a convex hull.
        hit, ri, _ = mesh.ray.intersects_location([c], [out], multiple_hits=False)
        far = float(np.linalg.norm(hit[0] - c)) if len(ri) else wall
        swept[i] = (pts, out, c + out * (far - wall))
        axes[i], outs[i] = n, out

    solids = []
    for pts, out, org in swept.values():
        h = trimesh.convex.convex_hull(pts)
        h = trimesh.intersections.slice_mesh_plane(
            h, plane_normal=-out, plane_origin=org, cap=True)
        if h is not None and len(h.faces) >= 4 and h.volume > 1e-6:
            solids.append(h)
    return trimesh.boolean.union(solids, engine="manifold")


def channel(mesh, frames, regions=None, width=3.5, depth=3.0, over=0.6,
            centre=True, wall=1.6, min_width=1.6, reach=4.0, depth_max=3.5):
    """The solids to subtract for the ledge. One, now, not a hundred and sixty."""
    return [drill_ledge(mesh, regions, frames, depth=depth_max, wall=wall,
                        reach=reach)]
