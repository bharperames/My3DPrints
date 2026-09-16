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


def _inside(mesh, pts, d=np.array([0.577, 0.577, 0.577])):
    """Which of `pts` are inside a CLOSED mesh. Exact, and much cheaper.

    `mesh.contains` counts parity over every crossing; this needs only the
    first one. If the first face a ray meets faces the same way the ray is
    travelling, the ray was leaving the solid, so the point began inside it.
    A ray that hits nothing began outside. Agrees with `contains` on
    6000/6000 random points in this skull's bounding box, at about three
    times the speed -- `contains` counts parity over every crossing, this
    needs only the first.
    """
    pts = np.atleast_2d(pts)
    loc, ri, tri = mesh.ray.intersects_location(
        pts, np.tile(d, (len(pts), 1)), multiple_hits=False)
    out = np.zeros(len(pts), bool)
    if len(ri):
        out[ri] = np.einsum("ij,j->i", mesh.face_normals[tri], d) > 0
    return out


def _ring_section(ring, axis):
    """The tooth outline as a 2D polygon in the plane square to `axis`.

    `tooth_frames` hands back the ring's points with np.unique applied, so
    their order -- which is the only thing that makes a loop a polygon -- is
    gone. A tooth's cross-section is a convex oval, so the 2D convex hull of
    the projected points recovers it exactly and does not care about order.
    """
    from shapely.geometry import Polygon, MultiPoint
    c = ring.mean(axis=0)
    a = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(a, axis))) > 0.9: a = np.array([0.0, 1.0, 0.0])
    u = np.cross(axis, a); u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    xy = np.column_stack([(ring - c) @ u, (ring - c) @ v])
    poly = MultiPoint([tuple(q) for q in xy]).convex_hull
    return (poly if isinstance(poly, Polygon) else None), c, u, v


def _outline_radii(poly, th):
    """The section's radius in each direction, about its own centre."""
    from shapely.geometry import LineString
    ctr = poly.centroid
    far = float(np.hypot(*(np.array(poly.bounds[2:]) - np.array(poly.bounds[:2])))) + 1.0
    out = np.zeros(len(th))
    for k, a in enumerate(th):
        d = np.array([np.cos(a), np.sin(a)])
        hit = poly.exterior.intersection(
            LineString([(ctr.x, ctr.y), (ctr.x + d[0] * far, ctr.y + d[1] * far)]))
        if hit.is_empty: continue
        g = hit.geoms[-1] if hasattr(hit, "geoms") else hit
        q = np.array(g.coords[-1] if hasattr(g, "coords") else (g.x, g.y))
        out[k] = float(np.hypot(*(q - np.array([ctr.x, ctr.y]))))
    return out, np.array([ctr.x, ctr.y])


def _loft(org, u, v, ax, zs, radii):
    """A closed solid through a stack of star-shaped rings.

    Each ring is `radii[k]` sampled around the same directions, so the side
    wall is a regular quad grid and the whole thing closes with one fan at
    each end. Built directly rather than by stacking extrusions: a stack of
    slabs has a visible step at every level and a boolean seam to go with it.
    """
    n = radii.shape[1]
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    dirs = np.cos(th)[:, None] * u + np.sin(th)[:, None] * v
    V = [org - ax * z + dirs * r[:, None] for z, r in zip(zs, radii)]
    verts = np.vstack(V + [org - ax * zs[0], org - ax * zs[-1]])
    top_c, bot_c = len(verts) - 2, len(verts) - 1
    F = []
    for k in range(len(zs) - 1):
        a, b = k * n, (k + 1) * n
        for i in range(n):
            j = (i + 1) % n
            F.append([a + i, b + i, b + j])
            F.append([a + i, b + j, a + j])
    for i in range(n):                       # caps
        j = (i + 1) % n
        F.append([top_c, j, i])
        F.append([bot_c, (len(zs) - 1) * n + i, (len(zs) - 1) * n + j])
    m = trimesh.Trimesh(vertices=verts, faces=np.array(F), process=True)
    m.fix_normals()
    return m


def drill_prism(mesh, regions, frames, depth=3.5, inset=0.35, reach=7.0,
                keep=0.9, over=1.5, lean=0.0, align=1.0, grow=0.0,
                report=None, **_ignored):
    """Brett's cylinder: the tooth outline, inset, swept down its own axis.

    Every socket before this one was cut oversize and then clipped back to
    keep the lip, and the clipping is what pinched the openings shut: a
    half-space fitted to rays cast at the cheek governs the whole socket,
    including the tongue side those rays never touched. Measured, the drill
    contributed nothing at all in the first 0.6 mm below the gum line while
    cutting 99% of the cavity two millimetres down -- a socket with a mouth
    smaller than its throat, which is exactly what the renders showed.

    So do not cut oversize. Take the designer's own outline, inset it by
    `inset` millimetres, and sweep THAT down the tooth's axis. The lip is
    protected by construction -- the cut never reaches it -- and because the
    section is constant, the mouth is as wide as the floor. There is nothing
    left to clip, and no guard shell to subtract.

    The axis is the tooth's first principal direction, per Brett. Where PCA
    finds the mesiodistal spread instead of the root -- a stubby tooth, or
    one whose paint runs onto the gum -- it is rejected in favour of the
    ring's own normal rather than trusted blindly.
    """
    from scipy.spatial import cKDTree
    C, N, A, U = gum_path(mesh, frames)
    tree = cKDTree(C)
    solids, short, thin = [], [], []
    for i, (faces, f) in enumerate(zip(regions, frames)):
        sub = mesh.submesh([faces], append=True)
        P = np.asarray(sub.vertices)
        ax = np.linalg.svd(P - P.mean(axis=0))[2][0]
        if float(np.dot(ax, f["n"])) < 0: ax = -ax
        # PCA can find the width of a tooth instead of its length. The ring's
        # normal is never wrong about which way is out, only about how far.
        if float(np.dot(ax, f["n"])) < 0.5: ax = f["n"]
        out = A[int(tree.query(f["c"])[1])]
        # DO NOT LET THE AXIS CARRY THE CUT OUT THROUGH THE CHEEK.
        #
        # Every tooth axis leans toward the tongue -- measured, up to 36
        # degrees on teeth 3, 5, 9 and 12 -- so a prism swept down that axis
        # drifts the other way as it goes, and at 3.5 mm depth a 36 degree
        # lean puts the socket floor 2.1 mm further out than its mouth. That
        # is through the outer wall. Brett, looking at it: "the cut ... makes
        # the cut go the wrong way ... we need to kind of ignore this
        # directions that cause the normal to poke through the outside."
        #
        # So keep the axis's fall along the jaw and take out the part of it
        # that aims at the cheek, beyond whatever `lean` allows. The socket
        # then drops straight in rather than raking across the wall, and the
        # inset is left to do the lip protection it was put there for.
        # PERPENDICULAR TO THE JAW, not to the tooth.
        #
        # Brett, looking at the front sockets: "if we keep the socket
        # basically perpendicular to the jaw itself, we might do better,
        # these front holes get pretty slender at this angle." They are
        # slender for a direct reason -- the section is the outline projected
        # SQUARE TO THE DRILL AXIS, so an axis that leans foreshortens it,
        # and the lean is worst at the front where the jaw curves hardest.
        #
        # `U` is the gum line's own perpendicular, built as tangent x outward,
        # so it is square to the jaw by construction and carries no outward
        # component at all. Blending the tooth's axis toward it un-squashes
        # the section; at align=1 the socket is simply normal to the jaw and
        # the lean clamp below has nothing left to do.
        uk = U[int(tree.query(f["c"])[1])]
        if float(np.dot(uk, ax)) < 0: uk = -uk
        ax = ax * (1.0 - align) + uk * align
        ax = ax / max(float(np.linalg.norm(ax)), 1e-9)
        lo = float(np.dot(ax, out))
        ax = ax - out * (lo - float(np.clip(lo, -lean, lean)))
        ax = ax / max(float(np.linalg.norm(ax)), 1e-9)
        sec, c, u, v = _ring_section(f["ring"], ax)
        if sec is None: continue
        ring_area = float(sec.area)          # the tooth's own footprint
        # A CONE WITH STRAIGHT SIDES, starting at the tooth contour.
        #
        # Brett: "start the cut at the tooth outline so that it is more of
        # an irregular cone that sweeps down, starting with the tooth
        # contour as the first cross section and then shrinking as needed
        # as it approaches the bottom of the hole."
        #
        # The first version took the radius in each direction from the
        # distance to the bone surface there. That is an OFFSET of the
        # skin, so the wall ran parallel to it and shaved slivers off
        # wherever it grazed -- 200-plus loose fragments and a file that
        # would not weld shut, at every wall thickness tried.
        #
        # A straight-sided cone cannot be parallel to a curved skull. So
        # keep the mouth at the designer's outline and shrink it linearly
        # with depth, and simply ask how steep the taper has to be: the
        # widest cone whose whole surface stays in the bone. One number
        # per tooth, found by bisection, and the solid is a loft through
        # rings that never chases anything.
        nth, nz = 96, 12
        th = np.linspace(0, 2 * np.pi, nth, endpoint=False)
        dirs = np.cos(th)[:, None] * u + np.sin(th)[:, None] * v
        # WIDEN ALONG THE JAW, BUT ONLY BELOW THE GUM.
        #
        # A cone cuts its own tooth's outline and nothing else, and the
        # designer's outlines come as close as 0.23 mm to one another -- so
        # the bone between a close pair survives as a blade a quarter of a
        # millimetre thick, standing in the finished channel. The trough
        # cannot take it: it sits on the CHEEK side of the gum line, where
        # the trough's labial limit is already at or past zero.
        #
        # Widening at EVERY depth does not work: between teeth the gum
        # surface dips, so a widened mouth ring stands out of the bone and
        # the containment bisection throws the tooth out -- all twelve of
        # them, measured. The mouth keeps the designer's outline and the
        # widening ramps in with depth, which is where the blade is anyway.
        rg = None
        if grow > 1e-6:
            from shapely import affinity
            from shapely.geometry import MultiPolygon
            kk = int(tree.query(f["c"])[1])
            t3 = np.cross(U[kk], A[kk])
            t3 = t3 / max(np.linalg.norm(t3), 1e-9)
            tx, ty = float(np.dot(t3, u)), float(np.dot(t3, v))
            n2 = max(np.hypot(tx, ty), 1e-9)
            tx, ty = tx / n2, ty / n2
            wide = MultiPolygon([
                affinity.translate(sec, tx * grow, ty * grow),
                affinity.translate(sec, -tx * grow, -ty * grow),
                sec]).convex_hull
            rg, _ = _outline_radii(wide, th)
        r0, ctr = _outline_radii(sec, th)
        org = c + ctr[0] * u + ctr[1] * v
        rise = float(np.max((f["ring"] - c) @ ax)) + 0.75
        zs = np.linspace(0.0, depth, nz)

        def rings(shrink):
            """Radii at each depth for a cone closing to `shrink` at the floor.

            The mouth is the designer's outline; any widening along the jaw
            ramps in with depth, so the base interpolates from r0 at the
            surface to the widened section at the floor.
            """
            t = zs / max(zs[-1], 1e-6)
            base = (r0[None, :] if rg is None
                    else r0[None, :] + (rg - r0)[None, :] * t[:, None])
            k = 1.0 - (1.0 - shrink) * t
            return np.maximum(base * k[:, None] - inset, 0.05)

        def fits(shrink):
            R = rings(shrink)
            P = np.vstack([org - ax * z + dirs * r[:, None]
                           for z, r in zip(zs, R)])
            return bool(_inside(mesh, P).all())

        lo_s, hi_s = 0.05, 1.0
        if not fits(lo_s):
            thin.append(i); continue
        if not fits(hi_s):
            for _ in range(7):
                mid = 0.5 * (lo_s + hi_s)
                if fits(mid): lo_s = mid
                else: hi_s = mid
        else:
            lo_s = hi_s
        R = rings(lo_s)
        radii = np.vstack([R[0][None, :], R])          # a lip above the gum
        zl = np.concatenate([[-rise], zs])
        h = _loft(org, u, v, ax, zl, radii)
        if h.is_volume and h.volume > 1e-6:
            solids.append(h)
            if report is not None:
                report.append(dict(tooth=i, section=round(ring_area, 2),
                                   depth=round(float(zs[-1]), 2),
                                   full=round(ring_area, 2),
                                   socket=round(ring_area, 2),
                                   used=round(lo_s, 3), inset=inset,
                                   lean=round(lo, 3), rise=round(rise, 2)))
    if short: print(f"    inset backed off on {len(short)} teeth: {short}")
    if thin: print(f"    no room for a socket in {len(thin)} teeth: {thin}")
    return trimesh.boolean.union(solids, engine="manifold")


def _sweep(P, A, U, lab, lin, top, depth):
    """The channel, as a union of per-segment convex hulls.

    Built as ONE long tube this is a thin, self-touching solid a few hundred
    stations long, and that is the shape a CSG engine handles worst: the
    subtraction left material the cutter demonstrably contained -- 79 sample
    points in one cluster, 0.22% of the channel, standing as a blade in the
    finished jaw. Hulling each segment between neighbouring stations makes
    every piece convex by construction, so no piece can fold through itself,
    and the union of them is exact. Same volume to a cubic millimetre, a
    third of the leftovers, and it unions in well under a second.
    """
    quads = []
    for k in range(len(P)):
        a, u = A[k], U[k]
        quads.append(np.array([
            P[k] + a * lab[k] + u * top,
            P[k] - a * lin[k] + u * top,
            P[k] - a * lin[k] - u * depth[k],
            P[k] + a * lab[k] - u * depth[k]]))
    # OVERLAP THE HULLS BY A STATION. Hulling each ADJACENT pair covers the
    # channel exactly, and "exactly" is the problem: consecutive hulls meet
    # on a shared quad, so the seam between them is tangent and the boolean
    # can leave a knife-edge of material standing there. Spanning three
    # stations makes each hull overlap its neighbour by a whole segment, so
    # the seams are interior to a solid rather than between two.
    hulls = []
    for k in range(len(quads) - 1):
        j = min(k + 2, len(quads) - 1)
        try:
            h = trimesh.convex.convex_hull(np.vstack(quads[k:j + 1]))
        except Exception:                                   # noqa: BLE001
            continue
        if h.is_volume and h.volume > 1e-9: hulls.append(h)
    if not hulls: return None
    return trimesh.boolean.union(hulls, engine="manifold")


def _sweep_tube(P, A, U, lab, lin, top, depth):
    """A continuous tube along the path, not a row of boxes.

    One box per station is a row of rectangular prisms, and where the arch
    curves each box's corners stand proud of its neighbour's -- the union's
    outer boundary is the envelope of those corners, which reads as a
    staircase on the finished surface. Brett saw it immediately: "large
    blocky artifacts."

    Connecting each station's four corners to the next one's instead gives a
    ruled surface with nothing to step on. Same section, same path; the
    difference is that the sides are now continuous rather than sampled.
    """
    ring = []
    for k in range(len(P)):
        a, u = A[k], U[k]
        ring.append(np.array([
            P[k] + a * lab[k] + u * top,
            P[k] - a * lin[k] + u * top,
            P[k] - a * lin[k] - u * depth[k],
            P[k] + a * lab[k] - u * depth[k]]))
    V = np.vstack(ring)
    F = []
    for k in range(len(ring) - 1):
        b0, b1 = 4 * k, 4 * (k + 1)
        for i in range(4):
            j = (i + 1) % 4
            F.append([b0 + i, b1 + i, b1 + j])
            F.append([b0 + i, b1 + j, b0 + j])
    n = len(ring) - 1
    F += [[0, 2, 1], [0, 3, 2]]                       # near cap
    F += [[4 * n + 0, 4 * n + 1, 4 * n + 2], [4 * n + 0, 4 * n + 2, 4 * n + 3]]
    m = trimesh.Trimesh(vertices=V, faces=np.array(F), process=True)
    m.fix_normals()
    return m


def lingual_trough(mesh, frames, depth=3.5, wall=0.8, over=2.0, past=1.0,
                   floor=1.2, per_mm=8.0, reach_cap=4.0, bloat=0.08,
                   report=None):
    """One open channel behind the sockets, bounded only on the cheek side.

    Brett's ask, and the first cut here that is deliberately allowed OUT of
    the bone: "allow the removal to not be constrained by the lingual side
    and basically connect all those openings together, but leaving the labial
    side shape that is still missing tooth contoured alone." A real tooth's
    root -- even clipped -- does not fit a socket sized to the crown, and a
    trough open to the tongue gives it somewhere to go and somewhere for the
    epoxy to key into.

    So at each station along the gum line, take a section that runs from just
    PAST the inner surface all the way out to the inner face of the lip, and
    sweep it. One constraint survives, the one that matters: the labial limit
    is where the cheek is, less `wall`, so the tooth-contoured outer wall the
    cones cut is never touched.

    The lingual side is bounded only so the cut does not cross the mouth and
    eat the opposite tooth row -- the first surface going inward, plus
    `past`. That is through the palate, which is what "open to the inside of
    the mouth" means on an upper jaw.
    """
    C, N, A, U = gum_path(mesh, frames)
    # FINER STATIONS THAN THE SOCKETS NEED.
    #
    # The gum path is sampled for placing pockets, about 1.5 a millimetre.
    # Swept, that spacing is visible: the sides are ruled between stations,
    # so each segment reads as a facet and the run of them as blocks. Brett:
    # "perhaps with a finer discretization the effect would not be
    # noticeable." Re-sample the path alone -- the measurements below are
    # taken at the finer spacing too, so the wall follows the bone as closely
    # as it is drawn.
    seg = np.linalg.norm(np.diff(C, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    fine = np.linspace(0.0, arc[-1], max(len(C), int(arc[-1] * per_mm)))
    lerp = lambda M: np.column_stack(
        [np.interp(fine, arc, M[:, i]) for i in range(3)])
    unit = lambda M: M / np.maximum(np.linalg.norm(M, axis=1), 1e-9)[:, None]
    C, A, U = lerp(C), unit(lerp(A)), unit(lerp(U))
    lab = np.zeros(len(C)); lin = np.zeros(len(C)); ok = np.zeros(len(C), bool)
    dep = np.full(len(C), depth)
    for k in range(len(C)):
        a = A[k]

        def reach(o, d):
            hit, ri, _ = mesh.ray.intersects_location(
                [o], [d], multiple_hits=False)
            return float(np.linalg.norm(hit[0] - o)) if len(ri) else None

        d_out = reach(C[k] + a * 0.05, a)          # to the cheek
        d_in = reach(C[k] - a * 0.05, -a)          # to the tongue side
        if d_out is None or d_in is None: continue
        # CAP THE LINGUAL REACH. `d_in` is the distance to the first surface
        # going toward the tongue, and on a U-shaped arch that ray can miss
        # the near wall and hit the FAR SIDE of the jaw -- measured, up to
        # 21.7 mm. The section then balloons past the midline, the swept tube
        # overlaps the opposite side of the arch, and a self-intersecting
        # cutter does not subtract properly: 118 of 717 stations ended up
        # with their own rectangle centre outside the solid they built, and
        # the material they were supposed to remove stayed put.
        lin[k], ok[k] = min(d_in, reach_cap) + past, True
        lab[k] = d_out - wall
        # LET THE DEPTH FOLLOW THE BONE. One depth for the whole arch is
        # limited by the shallowest station, so the back -- where there is
        # most material -- is cut no deeper than the front, and Brett wants
        # it deeper there. Measure how far down the jaw goes at each station
        # and take what is available, less `floor`.
        # MEASURE BONE, NOT AIR. The gum line runs through tooth CENTRES and
        # is smoothed, so between teeth it sits a little above the scalloped
        # surface -- and a ray fired down from there reports the distance to
        # the bone's TOP face, not the thickness beneath it. Measured, that
        # read 0.34 mm between teeth against 5.38 mm at one, so the trough
        # went 0.4 mm deep in exactly the gaps, and the lingual wall below
        # survived as the slivers Brett could see. Take the first solid SPAN
        # the column crosses instead, which is the same correction the socket
        # depth needed for the same reason.
        o = C[k] + U[k] * 6.0
        hh, rr, _ = mesh.ray.intersects_location([o], [-U[k]], multiple_hits=True)
        ts = sorted(float(np.linalg.norm(h - o)) for h in hh)
        span = (ts[1] - ts[0]) if len(ts) > 1 else None
        dep[k] = depth if span is None else min(depth, max(0.4, span - floor))
    if ok.sum() < 4: return None
    # carry the measurement across any station whose rays missed, and smooth
    # it -- a limit that jumps from one station to the next puts a step in
    # the swept wall just as surely as the boxes did
    idx = np.arange(len(C))
    lab = np.interp(idx, idx[ok], lab[ok])
    lin = np.interp(idx, idx[ok], lin[ok])
    dep = np.interp(idx, idx[ok], dep[ok])
    win = 9
    ker = np.ones(win) / win
    pad = lambda v: np.concatenate([np.repeat(v[:1], win // 2), v,
                                    np.repeat(v[-1:], win // 2)])
    lab = np.convolve(pad(lab), ker, mode="valid")
    lin = np.convolve(pad(lin), ker, mode="valid")
    dep = np.convolve(pad(dep), ker, mode="valid")
    if report is not None:
        # Hand back the stations the cut was actually built from, at the
        # spacing it actually used. Recomputing them outside tests a claim
        # the cutter never made.
        report.update(C=C.copy(), A=A.copy(), U=U.copy(),
                      lab=lab.copy(), lin=lin.copy(), dep=dep.copy())
    tube = _sweep(C, A, U, lab, lin, over, dep)
    # PUSH THE CUTTER OUT A HAIR. Its wall lands exactly on the bone's own
    # surface in places, and a boolean between coincident surfaces is where
    # CSG is least reliable -- the subtraction left blades standing that the
    # cutter demonstrably contained, and intersecting to find them came back
    # empty because manifold's own arithmetic disagreed with the geometry.
    # Inflating by `bloat` breaks the coincidence: measured, 55 leftover
    # sample points to zero at 0.02 mm, and the two bridges across the
    # channel go at 0.10. A tenth of a millimetre is a quarter of the
    # nozzle -- below anything the printer resolves.
    if tube is not None and bloat > 1e-9:
        tube.vertices = tube.vertices + tube.vertex_normals * bloat
    if tube.is_volume and tube.volume > 1e-6:
        return tube
    # a tube can fold where the arch turns hardest; fall back to the boxes
    step = float(np.median(np.linalg.norm(np.diff(C, axis=0), axis=1)))
    out = []
    for k in range(len(C)):
        a, u = A[k], U[k]
        t = np.cross(a, u); nt = np.linalg.norm(t)
        if nt < 1e-9 or lab[k] + lin[k] <= 0.2: continue
        t = t / nt
        box = trimesh.creation.box([lab[k] + lin[k], 2.2 * step, dep[k] + over])
        M = np.eye(4)
        M[:3, 0], M[:3, 1], M[:3, 2] = a, t, u
        M[:3, 3] = C[k] + a * (lab[k] - lin[k]) / 2.0 + u * (over - dep[k]) / 2.0
        box.apply_transform(M); out.append(box)
    if not out: return None
    return trimesh.boolean.union(out, engine="manifold")


def channel(mesh, frames, regions=None, depth_max=3.5, reach=4.0, **extra):
    """The solids to subtract: one cone per tooth, and the trough behind them.

    There used to be a `mode` here, selecting between this and a cutter that
    grew each socket from the tooth's convex hull and clipped it back to keep
    the lip. That one is gone -- it is in git at 932a1f8 if it is ever wanted.
    Clipping is what pinched the socket mouths shut: a half-space fitted to
    rays cast at the cheek governs the whole socket, including the tongue
    side those rays never touched, and measured it left the openings at 23%
    of the designer's outline with 4.5% of the surface under 0.8 mm against
    the printed part's 1.0%.
    """
    # The trough is SHALLOWER than the sockets by default and its lip is its
    # own number: a socket's margin and the thickness of cheek in front of an
    # open channel are different questions, and reusing `inset` for both left
    # a 0.35 mm wall -- thinner than one 0.4 mm extrusion.
    ling = float(extra.pop("lingual", 0.0))
    ldepth = float(extra.pop("ling_depth", 0.0) or depth_max)
    lwall = float(extra.pop("ling_wall", 0.0) or 1.2)
    # How much bone stays UNDER the channel. On the skull this is never the
    # binding constraint; on the lower jaw it is -- reserving 1.2 mm where
    # there is only 1.6 leaves a 0.4 mm cut, which is why a fifth of that
    # arch was barely touched and why the depth terraced between stations
    # that could cut and stations that could not.
    lfloor = float(extra.pop("ling_floor", 0.0) or 1.2)
    lcap = float(extra.pop("ling_cap", 0.0) or 4.0)
    for k in ("rscale", "lip", "width", "depth", "over", "centre",
              "wall", "min_width", "mode", "cone", "radial", "scrub"):
        extra.pop(k, None)
    cuts = [drill_prism(mesh, regions, frames, depth=depth_max,
                        reach=reach, **extra)]
    if ling:
        tr = lingual_trough(mesh, frames, depth=ldepth, wall=lwall, past=ling)
        if tr is not None: cuts.append(tr)
    return cuts
