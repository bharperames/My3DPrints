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

def _frame(C, N, k):
    """tangent, outward axis and up axis at sample k."""
    t = C[min(k + 1, len(C) - 1)] - C[max(k - 1, 0)]
    if np.linalg.norm(t) < 1e-9: return None
    t = t / np.linalg.norm(t)
    a = np.cross(N[k], t)
    if np.linalg.norm(a) < 1e-9: return None
    return t / np.linalg.norm(t), a / np.linalg.norm(a)


def _need(h, rim, target, ramp=1.5):
    """How much wall to insist on, that far below the gum line.

    One figure for the whole face asks the anatomy for something it does not
    have. The bone at the gum line IS the alveolar margin -- the rim the
    tooth came out of -- and it is thin there because that is what a tooth
    socket is. Demanding the full wall at 0.1 mm below the gum line refused
    128 of 173 stations and left a shelf in pieces.

    So ramp it: a rim's worth at the top, the full wall by `ramp` below.
    That is the shape of the bone and it is also the shape of the need --
    the top edge is a margin, the body of the lip is what has to hold.
    """
    return rim + (target - rim) * min(1.0, max(0.0, -h) / ramp)


def _face_offsets(depth, step, nh=7, nw=3):
    """Where to probe the cut's outer face: the part of it that is in bone.

    Above the gum line there is no bone to keep -- that is where the teeth
    were -- so probing there reports "outside the mesh" and means nothing.
    Only the part at and below the gum line has a wall to preserve.
    """
    h = np.linspace(-depth + 0.1, -0.1, nh)
    w = np.linspace(-1.1 * step, 1.1 * step, nw)
    return [(hh, ww) for hh in h for ww in w]


def _measure(mesh, pos, frames, depth, step, rim, target, nh, nw):
    """Wall left at every probe on every station's cut face, in one batch.

    One query per station is 173 round trips into the ray engine and the
    proximity tree; batching every station's probes into a single call is
    the difference between ten minutes and one. It also means the solver,
    the depth trim and the verifier are all reading the same numbers -- the
    version that sampled 7x3 while the verifier sampled 9x5 solved for the
    points it was looking at and left the ones it was not.
    """
    pts, owner, hh, need = [], [], [], []
    for k, (t, a, n) in frames.items():
        for h, w in _face_offsets(depth[k], step, nh, nw):
            pts.append(pos[k] + n * h + t * w)
            owner.append(k); hh.append(h); need.append(_need(h, rim, target))
    if not pts:
        return (np.zeros((0, 3)), np.array([], int), np.array([]),
                np.array([]), np.array([]), np.array([]))
    pts = np.asarray(pts); owner = np.asarray(owner)
    hh = np.asarray(hh); need = np.asarray(need)
    dirs = np.asarray([frames[k][1] for k in owner])
    wall = np.zeros(len(pts)); slant = np.ones(len(pts))
    loc, ri, tri = mesh.ray.intersects_location(pts, dirs, multiple_hits=False)
    if len(ri):
        d = np.linalg.norm(loc - pts[ri], axis=1)
        sl = np.maximum(np.abs(np.einsum("ij,ij->i",
                                         mesh.face_normals[tri], dirs[ri])), 0.35)
        wall[ri] = d * sl; slant[ri] = sl
    # Inside/outside without a containment query. For a closed mesh, a ray
    # leaving an interior point meets its first face from behind, so that
    # face's normal points the same way the ray does; from outside, the
    # first face is an entry and its normal opposes. `mesh.contains` answers
    # the same question by casting its own rays, and it was costing more
    # than every other query in this loop put together.
    inside = np.zeros(len(pts), bool)
    if len(ri):
        inside[ri] = np.einsum("ij,ij->i", mesh.face_normals[tri], dirs[ri]) > 0
    if (~inside).any():
        lb, rb, _ = mesh.ray.intersects_location(pts[~inside], -dirs[~inside],
                                                 multiple_hits=False)
        over = np.zeros(int((~inside).sum()))
        if len(rb): over[rb] = np.linalg.norm(lb - pts[~inside][rb], axis=1)
        # A probe that has left the bone may find the far side of the skull
        # behind it. The reading only has to say "outboard, move in"; how far
        # is not information this ray carries, and taken literally it walked
        # a 115 mm gum line out to 920.
        wall[~inside] = -np.minimum(over, 2.0)
    return pts, owner, hh, need, wall, slant

def labial(mesh, C, N, depth, outer_wall=1.2, step=None, only=None,
           rim=0.5, nh=9, nw=5):
    """Set the cut plane by the THINNEST point of the wall it leaves.

    Centring on the middle of the ridge spends the width evenly and leaves
    paper-thin sheets wherever the bone pinches -- on the cheek side, which
    is the side you look at. Brett's point settles it: the inside edge of
    the jaw is not visible, so it is the side that can be spent.

    The first version of this measured the wall with ONE ray, at one height,
    half the depth below the gum line, and corrected for obliquity with a
    slant factor. That guarantees the wall at exactly one plane. The cut
    face is `depth` tall, the maxilla's outer face slopes inward going down,
    and so the wall thins with depth: measured on the printed skull the
    nominal 1.2 mm came out at a median of 0.32 mm true perpendicular, under
    0.8 mm at 88% of stations, and NEGATIVE -- open to daylight -- at 21%.
    Brett photographed the result: the cutting mat showing green through the
    lip in three places.

    So probe the whole face, not a point of it, and drive the plane by the
    worst reading on it. `slant` survives only as the conversion from a
    distance measured along `a` to real wall thickness, which is what it
    always was; it is no longer asked to stand in for the readings that
    were never taken.

    Distance is measured by ray along `a`, NOT by nearest-surface: at a
    station where the maxilla is thin, the nearest surface to a point in the
    middle of it is the LINGUAL face, and solving against that walks the
    plane the wrong way and diverges.
    """
    out, axes = C.copy(), np.zeros_like(C)
    mid = mesh.centroid
    if step is None:
        step = float(np.median(np.linalg.norm(np.diff(C, axis=0), axis=1)))
    depth = np.broadcast_to(np.asarray(depth, float), (len(C),)).copy()
    home = C.copy()
    frames = {}
    for k in range(len(C)):
        if only is not None and not only[k]: continue
        f = _frame(C, N, k)
        if f is None: continue
        t, a = f
        if np.dot(a, C[k] - mid) < 0: a = -a
        n = np.cross(t, a); n = n / np.linalg.norm(n)
        if np.dot(n, N[k]) < 0: n = -n
        frames[k] = (t, a, n); axes[k] = a

    for _ in range(10):
        _, owner, _, need, wall, slant = _measure(
            mesh, out, frames, depth, step, rim, outer_wall, nh, nw)
        if not len(owner): break
        moved = False
        for k in frames:
            m = owner == k
            if not m.any(): continue
            short = need[m] - wall[m]
            q = int(np.argmax(short))
            if short[q] < 0.01: continue
            move = float(np.clip(short[q] / slant[m][q], -1.5, 1.5))
            off = float(np.dot(out[k] - frames[k][1] * move - home[k], frames[k][1]))
            out[k] = home[k] + frames[k][1] * float(np.clip(off, -1.0, 8.0))
            moved = True
        if not moved: break

    # one last read at the positions actually returned, so the depth trim and
    # the plane it trims are describing the same geometry
    _, owner, hh, need, wall, _ = _measure(
        mesh, out, frames, depth, step, rim, outer_wall, nh, nw)
    prof = [None] * len(C)
    for k in frames:
        m = owner == k
        if not m.any(): continue
        h = hh[m]; wv = wall[m]; nd = need[m]
        hs = np.unique(h)
        prof[k] = (hs, np.array([(wv[h == u] - nd[h == u]).min() for u in hs]))

    bad = np.linalg.norm(axes, axis=1) < 1e-9
    if bad.any():
        good = np.where(~bad)[0]
        if len(good):
            for k in np.where(bad)[0]:
                axes[k] = axes[good[np.argmin(abs(good - k))]]
    return out, axes, prof


def wall_by_height(mesh, C, N, A, D, step, nh=9, nw=5):
    """The wall each station leaves, probe by probe down its own cut face."""
    prof = []
    for k in range(len(C)):
        f = _frame(C, N, k)
        if f is None or D[k] <= 0: prof.append(None); continue
        t, a = f[0], A[k]
        n = np.cross(t, a); n = n / np.linalg.norm(n)
        if np.dot(n, N[k]) < 0: n = -n
        hs = np.linspace(-D[k] + 0.1, -0.1, nh)
        pts = np.array([C[k] + n * h + t * w for h in hs
                        for w in np.linspace(-1.1 * step, 1.1 * step, nw)])
        dirs = np.tile(a, (len(pts), 1))
        wall = np.zeros(len(pts))
        loc, ri, tri = mesh.ray.intersects_location(pts, dirs, multiple_hits=False)
        if len(ri):
            d = np.linalg.norm(loc - pts[ri], axis=1)
            sl = np.abs(np.einsum("ij,ij->i", mesh.face_normals[tri], dirs[ri]))
            wall[ri] = d * np.maximum(sl, 0.35)
        wall[~mesh.contains(pts)] = -1.0
        prof.append((hs, wall.reshape(nh, nw).min(axis=1)))
    return prof


def fit_ledge(mesh, C, N, step, target=1.2, lo=1.5, hi=6.0, floor=1.0, rim=0.5):
    """Solve the cut plane and the cut depth together, because they trade.

    They are not independent. A deeper cut reaches further down the outer
    face of the maxilla, which slopes inward, so it forces the plane inboard
    to keep its wall; a shallower one lets the plane sit out and the shelf
    be wider. Solving them apart -- plane first at a fixed depth, depth
    afterwards -- still leaves the thin stations open, because no plane
    position rescues a cut that is simply deeper than the bone.

    So: take the bone available, solve the plane for it, then trim each
    station back to the deepest probe still carrying `target` of wall, and
    solve again. A station that cannot hold the wall even at `lo` is not cut
    at all. Its bone stays solid and the lip runs through unbroken, which is
    what a gap in the lip line is worth avoiding.
    """
    A = np.zeros_like(C)
    for k in range(len(C)):
        f = _frame(C, N, k)
        if f is None: continue
        a = f[1]
        if np.dot(a, C[k] - mesh.centroid) < 0: a = -a
        A[k] = a
    D = bone_below(mesh, C, N, A, step, floor=floor, lo=lo, hi=hi)
    # `extend` deliberately runs the path out past the last tooth so the cut
    # leaves through the end of the jaw instead of stopping in it. Those
    # stations are in fresh air, and a wall solver asked to find a wall there
    # will chase one anywhere. Gate them out first.
    D[~mesh.contains(C)] = 0.0
    out = C.copy()
    for _ in range(5):
        out, A, prof = labial(mesh, out, N, D, outer_wall=target, step=step,
                              only=D > 0, rim=rim)
        nz = np.linalg.norm(A, axis=1) > 1e-9
        A[nz] /= np.linalg.norm(A[nz], axis=1)[:, None]
        for k, pr in enumerate(prof):
            if pr is None: continue
            hs, w = pr
            # hs runs deepest first. Walk UP from the shallow end and stop at
            # the first probe that fails: the usable depth is where the wall
            # holds continuously, not the deepest probe that happens to pass.
            # A profile that fails at mid depth and passes below it is a
            # window with bone under it, and taking the lower reading keeps
            # the window.
            good = 0.0
            for h, wv in zip(hs[::-1], w[::-1]):
                if wv < 0: break         # w is already margin over the need
                good = -h
            D[k] = good
        D[(D > 0) & (D < lo)] = 0.0
    # ONCE, at the end. Inside the loop the running minimum erodes the depth
    # again on every pass, and five passes of erosion took a shelf that the
    # bone could carry to 4.9 mm down to 2.1 -- shallower than the flat cut
    # it was meant to improve on, while the plane never moved at all because
    # by then every probe passed.
    out, D = _regularise(out, C, A, D, cut=D > 0)
    return out, A, D


def _run(x, win, op):
    pad = np.concatenate([np.repeat(x[:1], win // 2), x, np.repeat(x[-1:], win // 2)])
    return np.array([op(pad[i:i + win]) for i in range(len(x))])


def _regularise(out, home, A, D, cut, win=7):
    """Smooth the solve without giving back what it bought.

    Solving each station on its own leaves the plane jittering from one to
    the next, and a jittering plane is exactly the serrated lip `smooth`
    exists to prevent -- measured, it stretched the path from 115 mm to 173.
    But averaging the answer undoes it: the mean of two plane positions does
    not clear the bone between them, which is why the solve cannot simply be
    followed by a smoothing pass.

    So smooth in the direction that can only be safe. The offset inboard
    takes a running MAXIMUM before it is averaged, so no station ends up
    shallower into the bone than its own reading demanded; the depth takes a
    running MINIMUM, so none ends up deeper than its own reading allowed.
    Both come out smooth, and neither can spend the wall.
    """
    o = np.array([float(np.dot(out[k] - home[k], A[k])) for k in range(len(out))])
    om = _run(o, win, np.max)
    o2 = np.maximum(_run(om, win, np.mean), o)
    dm = np.where(cut, D, np.nan)
    if np.isfinite(dm).any():
        filled = np.where(cut, D, np.nanmax(dm))
        dn = _run(filled, win, np.min)
        d2 = np.minimum(_run(dn, win, np.mean), D)
    else:
        d2 = D
    return np.array([home[k] + A[k] * o2[k] for k in range(len(out))]), \
           np.where(cut, np.maximum(d2, 0.0), 0.0)


def bone_below(mesh, C, N, A, step, floor=1.0, lo=1.5, hi=6.0):
    """How deep the shelf can go at each station before it breaks out.

    One depth for the whole arch is wrong in both directions at once. Below
    the gum line this skull carries a median of 3.7 mm of bone, but 36% of
    the arch has 8 mm or more and a quarter has 0.7 mm or less. A flat 3.0
    cuts straight out of the bottom at the thin quarter -- the other half of
    what Brett photographed -- and throws away most of a deep shelf through
    the middle of the tooth row, which is exactly where the putty and the
    tooth roots want the room.
    """
    d = np.full(len(C), lo)
    for k in range(len(C)):
        f = _frame(C, N, k)
        if f is None: continue
        t, a = f[0], A[k]
        n = np.cross(t, a); n = n / np.linalg.norm(n)
        if np.dot(n, N[k]) < 0: n = -n
        runs = []
        for w in (-1.1 * step, 0.0, 1.1 * step):
            p = C[k] + t * w + n * 0.2
            h = mesh.ray.intersects_location([p], [-n])[0]
            runs.append(np.min(np.linalg.norm(h - p, axis=1)) if len(h) else 0.0)
        d[k] = min(runs) - floor
    d = np.clip(d, lo, hi)
    # The floor of the shelf is a surface someone looks into: let it fall
    # and rise smoothly rather than step from station to station.
    win = 9
    pad = np.concatenate([np.repeat(d[:1], win // 2), d, np.repeat(d[-1:], win // 2)])
    return np.convolve(pad, np.ones(win) / win, mode="valid")


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
            wall=0.8, min_width=1.6, reach=9.0, depth_max=6.0):
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
    step = float(np.median(np.linalg.norm(np.diff(C, axis=0), axis=1)))
    D = np.full(len(C), depth)
    if centre:
        # Smooth the path FIRST and solve the plane on the smoothed path.
        # Solving and then smoothing undoes the solve: the average of two
        # neighbouring plane positions is not a plane position that clears
        # the bone between them, and on a convex stretch it lands outboard
        # of both -- which is a wall the solver believed it had left.
        C, N = smooth(C, N)
        C, A, D = fit_ledge(mesh, C, N, step, target=wall + 0.4,
                            lo=1.5, hi=depth_max)
    segs = []
    # Overlapping boxes, one per sample, not a chain of prisms end to end.
    # A prism from sample k to k+1 carries its own across-vector, and where
    # the gum line curves that vector twists between neighbours: the union
    # then has notches along it, and thin fins of bone survive between one
    # prism and the next. Seen on the skull it reads as a serrated trough;
    # seen on the test jaw, where the same sweep defines the whole part, it
    # is unusable. Boxes twice the sample spacing overlap their neighbours
    # by half, so the union is a clean tube whatever the path does.
    step = float(np.median(np.linalg.norm(np.diff(C, axis=0), axis=1)))
    for k in range(len(C)):
        t = C[min(k + 1, len(C) - 1)] - C[max(k - 1, 0)]
        if np.linalg.norm(t) < 1e-9: continue
        t = t / np.linalg.norm(t)
        a = A[k] if A is not None else np.cross(N[k], t)
        if np.linalg.norm(a) < 1e-9: continue
        a = a / np.linalg.norm(a)
        n = np.cross(t, a); n = n / np.linalg.norm(n)
        if np.dot(n, N[k]) < 0: n = -n
        dk = float(D[k])
        if dk <= 0: continue        # no wall to be had here: leave it solid
        box = trimesh.creation.box([reach, 2.2 * step, dk + over])
        M = np.eye(4)
        M[:3, 0], M[:3, 1], M[:3, 2] = a, t, n
        # C is the inner face of the labial wall; the cut runs from there
        # inboard, so the box centre sits half a reach further in
        M[:3, 3] = C[k] - a * reach / 2.0 + n * (over - dk) / 2.0
        box.apply_transform(M)
        segs.append(box)
    return segs
