"""Take the teeth off and leave a trough along the gum line.

The teeth come from the designer's own paint, not from a detector: each
tooth is a `paint_color` region in the 3MF, complete down to the ring where
it meets the bone. Those rings give a centre, an axis and a width apiece,
and threading them in order gives the gum line.

One cutter does both jobs. It runs from above the tooth tips down to the
wanted depth below the bone surface, so subtracting it shears the teeth off
and digs the channel in the same operation -- no separate flush cut, and
nothing delicate to fail per tooth.
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
                        r=float(np.max(np.linalg.norm(ring - c, axis=1)))))
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

def labial(mesh, C, N, depth, outer_wall=1.2):
    """Set the channel by the OUTER wall and let the inside give.

    Centring on the middle of the ridge spends the width evenly and leaves
    paper-thin sheets wherever the bone pinches -- on the cheek side, which
    is the side you look at. Brett's point settles it: the inside edge of
    the jaw is not visible, so it is the side that can be spent. The channel
    is placed so its outer face sits exactly `outer_wall` inside the cheek,
    and whatever it does on the palate side it does out of sight.
    """
    out, axes = C.copy(), np.zeros_like(C)
    mid = mesh.centroid
    for k in range(len(C)):
        t = C[min(k + 1, len(C) - 1)] - C[max(k - 1, 0)]
        if np.linalg.norm(t) < 1e-9: continue
        t = t / np.linalg.norm(t)
        a = np.cross(N[k], t)
        if np.linalg.norm(a) < 1e-9: continue
        a = a / np.linalg.norm(a)
        # outward is away from the middle of the skull
        if np.dot(a, C[k] - mid) < 0: a = -a
        p = C[k] - N[k] * depth * 0.5
        h, _, tri = mesh.ray.intersects_location([p], [a])
        if not len(h): continue
        j = int(np.argmin(np.linalg.norm(h - p, axis=1)))
        d_out = float(np.linalg.norm(h[j] - p))
        # Step back along `a` by enough to leave `outer_wall` measured
        # PERPENDICULAR to the surface. Where the labial face is oblique to
        # the lateral axis -- which it is towards the ends of the jaw, the
        # face turning away -- a 1.2 mm step sideways leaves a fraction of
        # that in real wall. Measured, it came out at 0.2 mm: sheets one
        # voxel thick, in mirror pairs at the far left and right, which is
        # exactly the ragged flap Brett kept finding.
        nrm = mesh.face_normals[int(tri[j])]
        slant = max(abs(float(np.dot(nrm, a))), 0.35)
        out[k] = C[k] + a * (d_out - outer_wall / slant)
        axes[k] = a
    bad = np.linalg.norm(axes, axis=1) < 1e-9
    if bad.any():
        good = np.where(~bad)[0]
        for k in np.where(bad)[0]:
            axes[k] = axes[good[np.argmin(abs(good - k))]]
    return out, axes


def recentre(mesh, C, N, depth):
    """Slide each sample sideways onto the middle of the bone ridge.

    The teeth are not centred on the jaw: measured on this skull they sit
    0.88 mm outboard of the ridge midline. Cutting a trough centred on the
    teeth therefore spends the width it has on the outer side and breaks
    through the palate -- at 3.5 mm it was through for 81% of its length.
    Centred on the bone instead, the same 3.5 mm clears.
    """
    out, avail = C.copy(), np.full(len(C), np.inf)
    for k in range(len(C)):
        t = C[min(k + 1, len(C) - 1)] - C[max(k - 1, 0)]
        if np.linalg.norm(t) < 1e-9: continue
        t = t / np.linalg.norm(t)
        a = np.cross(N[k], t)
        if np.linalg.norm(a) < 1e-9: continue
        a = a / np.linalg.norm(a)
        p = C[k] - N[k] * depth * 0.5
        d = []
        for sgn in (-1, 1):
            h = mesh.ray.intersects_location([p], [a * sgn])[0]
            d.append(np.min(np.linalg.norm(h - p, axis=1)) if len(h) else np.nan)
        if not np.any(np.isnan(d)):
            out[k] = C[k] + a * (d[0] - d[1]) / 2.0
            avail[k] = d[0] + d[1]
    if np.isfinite(avail).any():
        avail[~np.isfinite(avail)] = np.nanmedian(avail[np.isfinite(avail)])
    else:
        avail[:] = 0.0
    return out, avail


def smooth(C, N, passes=6, win=9):
    """Take the jitter out of the path before anything is swept along it.

    `recentre` measures each sample on its own with a pair of rays, and the
    bone it measures against is bumpy, so the offsets it returns jump from
    one sample to the next. Sweeping a box per sample along a jittering path
    leaves each box a little to one side of its neighbours, and the thin
    wedges of bone that survive between them show up as a comb of teeth
    along the rim of the channel. The path is a gum line: it is smooth, and
    the measurement is what is noisy.
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

def channel(mesh, frames, width=3.5, depth=3.0, over=1.0, centre=True,
            wall=0.8, min_width=1.6, reach=9.0):
    """A LEDGE along the gum line: labial wall kept, everything inboard cut.

    A trough has two walls and the inner one is the trouble -- it is where
    the bone pinches, and every paper-thin flap and tab came from trying to
    hold it. Brett's answer is to stop holding it. The lip you see is the
    labial side; the lingual side is inside the mouth and no one looks at
    it. So the cut keeps a wall of `wall + 0.4` on the labial face and takes
    everything behind it for `reach`, leaving a shelf the teeth are set on
    and glued.

    With no inner wall there is nothing thin left to leave behind, which is
    the whole class of defect gone rather than patched.
    """
    order = order_along_jaw(frames)
    C, N = extend(np.array([frames[i]["c"] for i in order]),
                  np.array([frames[i]["n"] for i in order]))
    C, N = resample(C, N)
    A = None
    if centre:
        C, A = labial(mesh, C, N, depth, outer_wall=wall + 0.4)
        C, N = smooth(C, N)
        A /= np.linalg.norm(A, axis=1)[:, None]
    segs = []
    # Overlapping boxes, one per sample, not a chain of prisms end to end.
    # A prism from sample k to k+1 carries its own across-vector, and where
    # the gum line curves that vector twists between neighbours: the union
    # then has notches along it, and thin fins of bone survive between one
    # prism and the next. Seen on the skull it reads as a serrated trough;
    # seen on the test jaw, where the same sweep defines the whole part, it
    # is unusable. Boxes twice the sample spacing overlap their neighbours
    # by half, so the union is a clean tube whatever the path does.
    step = np.median(np.linalg.norm(np.diff(C, axis=0), axis=1))
    for k in range(len(C)):
        t = C[min(k + 1, len(C) - 1)] - C[max(k - 1, 0)]
        if np.linalg.norm(t) < 1e-9: continue
        t = t / np.linalg.norm(t)
        a = A[k] if A is not None else np.cross(N[k], t)
        if np.linalg.norm(a) < 1e-9: continue
        a = a / np.linalg.norm(a)
        n = np.cross(t, a); n = n / np.linalg.norm(n)
        if np.dot(n, N[k]) < 0: n = -n
        box = trimesh.creation.box([reach, 2.2 * step, depth + over])
        M = np.eye(4)
        M[:3, 0], M[:3, 1], M[:3, 2] = a, t, n
        # C is the inner face of the labial wall; the cut runs from there
        # inboard, so the box centre sits half a reach further in
        M[:3, 3] = C[k] - a * reach / 2.0 + n * (over - depth) / 2.0
        box.apply_transform(M)
        segs.append(box)
    return segs
