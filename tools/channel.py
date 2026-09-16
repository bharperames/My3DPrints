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


def _cone(c, n, r, L, seg=64):
    """Points on a cone: base ring of radius `r` at `c`, tip `L` along `n`.

    A tooth root is a cone, so the socket is one. Hulling the painted tooth's
    own vertices instead wraps it in flat planes, and where two of those meet
    the channel reads machined rather than grown.

    Two variations on this were tried and both abandoned. An ELLIPTICAL cone,
    stretched along the jaw, changed nothing measurable (1225 -> 1231 mm3) and
    nothing Brett could see. A LOFT through shrinking rings was worse on every
    count -- 1016 mm3 out against 1225, thinnest wall 0.74 against 0.84 -- and
    worse to look at. The plain cone, slid sideways to widen, is the one that
    survived contact with a person looking at it.
    """
    a = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(a, n))) > 0.9: a = np.array([0.0, 1.0, 0.0])
    u = np.cross(n, a); u /= np.linalg.norm(u)
    v = np.cross(n, u)
    th = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    ring = c + r * (np.cos(th)[:, None] * u + np.sin(th)[:, None] * v)
    return np.vstack([ring, c + n * L])


_ICO = None


def _ball(c, r):
    """Points on a sphere of radius `r` at `c`.

    The hull of a few of these is smooth: spherical caps joined by tangent
    cones, and not an edge in it. That is the whole reason for the primitive.
    """
    global _ICO
    if _ICO is None:
        _ICO = np.asarray(trimesh.creation.icosphere(subdivisions=2).vertices)
    return c + _ICO * r


def _sink(mesh, pts, axis, out, wall):
    """Push a solid in along `axis` until it clears the skin by `wall`."""
    hit, ri, _ = mesh.ray.intersects_location(
        pts, np.tile(out, (len(pts), 1)), multiple_hits=False)
    d = np.full(len(pts), -wall)                  # no hit: already outside
    if len(ri): d[ri] = np.linalg.norm(hit - pts[ri], axis=1)
    drop = float(np.max((wall - d) / max(float(np.dot(axis, out)), 0.30)))
    return pts - axis * max(drop, 0.0)


def drill_ledge(mesh, regions, frames, depth=6.0, wall=1.6, reach=7.0,
                keep=0.9, grow=0.45, rscale=0.94, lip=0.6):
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

    # How sharply the jaw turns at each tooth. Where it turns hard the
    # neighbouring pockets diverge on the cheek side and leave a wedge of
    # bone standing between them -- the thin corners at the front of the
    # lower jaw. Widen more there, and only there.
    pos = {i: f["c"] for i, f in enumerate(frames)}
    turn = {i: 0.0 for i in pos}
    for a_, b_, c_ in zip(order, order[1:], order[2:]):
        u = pos[b_] - pos[a_]; v = pos[c_] - pos[b_]
        nu, nv = np.linalg.norm(u), np.linalg.norm(v)
        if nu < 1e-9 or nv < 1e-9: continue
        turn[b_] = float(np.arccos(np.clip(np.dot(u / nu, v / nv), -1, 1)))

    swept, axes, outs, skin = {}, {}, {}, []
    for i, (faces, f) in enumerate(zip(regions, frames)):
        out = A[int(tree.query(f["c"])[1])]
        n = f["n"]
        # A CONE, not the tooth's convex hull.
        #
        # Hulling the painted tooth's vertices wraps it in flat planes, and
        # where two pockets meet those planes leave a ridge -- the channel
        # reads machined rather than grown. A tooth root is a cone, so the
        # socket should be one: round sides, and the union of overlapping
        # cones scallops the way an alveolar channel does. It also fits a
        # real tooth better than a cast of the printed one's silhouette.
        V = _cone(f["c"], n, f["r"] * rscale, f["L"])
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
        # Shrink the outline where it faces the LIP, and only there.
        #
        # The ring is a floor the clip may not cross, which is what finally
        # opened all fourteen sockets. But on the labial side that outline
        # runs right up to the outer surface, so honouring it exactly leaves
        # no lip at all -- Brett: "based on how close the tooth edge is to the
        # lip, we might need to shrink the tooth area along the outer edge."
        #
        # Pull those points inboard, weighted by how far outboard they sit, so
        # the socket stops short of the lip on the cheek side and still
        # reaches the designer's outline everywhere else. Nothing is at stake
        # on the tongue side, so nothing is given up there.
        raw = f["ring"]
        d_out = (raw - c) @ out
        span = float(np.max(d_out)) if float(np.max(d_out)) > 1e-6 else 1.0
        w = np.clip(d_out / span, 0.0, 1.0)[:, None]
        ring = raw - out * (lip * w)
        # A HULL OF SPHERES, which has no edges anywhere.
        #
        # The cone was the right idea and the wrong solid. A cone swept along
        # a straight line and hulled is a PRISM: flat sides, and a silhouette
        # against the gum that is a rectangle with 90-degree corners. Two
        # straight sweeps -- down the axis and inboard -- gave it two sets of
        # them. Brett, looking at three of those openings: "I don't understand
        # how changing socket radius still produces these hard 90 deg corners
        # up against the lip ... this corner shape up against the curved gum
        # is what causes the problems." It never could: the radius scales the
        # rounded ends and leaves the swept sides exactly as they were.
        #
        # The convex hull of a set of spheres is bounded by spherical caps and
        # the cones tangent between them. There is no edge in it to land on
        # the gum, so the opening it cuts is a smooth closed curve whatever
        # angle the bone meets it at.
        tan = np.cross(n, out)
        tan = tan / max(np.linalg.norm(tan), 1e-9)
        g = grow * (1.0 + 0.5 * turn[i])
        rad = f["r"] * rscale
        balls = []
        for t_ in np.linspace(0.0, 1.0, 5):
            c_t = f["c"] - n * dwn * t_ - out * inb * t_
            r_t = rad * (1.0 - 0.30 * t_ * t_)
            for off in (-g, g) if g > 1e-6 else (0.0,):
                balls.append(_ball(c_t + tan * off, r_t))
        # and the crown, so the socket opens flush at the gum line
        balls.append(_ball(f["c"] + n * (f["L"] * 0.25), rad * 0.72))
        # THE OUTLINE ITSELF belongs in the hull. A ball is a circle where it
        # meets the gum and the outline is an ellipse, so a socket sized by
        # the ring's LARGEST radius still misses its ends, and one sized to
        # span them is far too wide in the middle. Measured, the tongue side
        # of the outline stayed 64% solid for exactly this reason. Feeding
        # the (lip-inset) ring points straight in makes the socket span the
        # designer's outline by construction rather than by a radius that
        # happens to fit.
        pts = np.vstack(balls + [ring])
        # CLIP AGAINST THE SURFACE, not against one plane through its middle.
        #
        # This used to cast a single ray from the tooth's CENTRE, measure how
        # far the cheek was, and clip the whole socket with one flat plane set
        # back by `wall`. Against a curved gum that is right in the middle and
        # wrong everywhere else: toward the edges of the socket the bone has
        # curved away, the plane sits too far inboard, and what it leaves is
        # a long flat facet ending in a crescent cusp on the lingual side.
        # Brett named it exactly -- "computed using the center of each drill
        # area instead of being computed for each boundary edge ... the hold
        # back is too naive".
        #
        # So take a plane per boundary point instead, each tangent to the
        # labial face where that ray actually lands and set back along that
        # face's own normal. Their intersection is the offset surface,
        # piecewise, and it follows the curve. Both the socket and every
        # half-space are convex, so the result stays convex and exact.
        step_r = max(1, len(ring) // 14)
        planes = []
        for q in raw[::step_r]:
            hh, rr, tt = mesh.ray.intersects_location(
                [q], [out], multiple_hits=False)
            if not len(rr): continue
            nn = mesh.face_normals[int(tt[0])]
            if float(np.dot(nn, out)) < 0.2: continue   # grazing: tells us nothing
            planes.append((nn, hh[0] - nn * wall, hh[0]))
        # THE RING IS A FLOOR, NOT A SUGGESTION.
        #
        # Brett: "almost by definition any triangle that touches the tooth
        # boundary line needs to be cut." The ring is where the tooth met the
        # bone, so every one of those planes must leave the whole ring inside
        # the socket. Clipping is an INTERSECTION of half-spaces, so the
        # tightest reading anywhere around the loop was governing everywhere
        # -- measured, that left a median 93% of each outline still solid and
        # six of fourteen sockets that did not open at all. Push any plane
        # that would bite into the ring back out until it does not.
        # ...but the WALL is the hard limit, and the ring floor works beneath
        # it. Pushed without a limit, the floor deletes the lip: on the cheek
        # side the outline lies ON the outer surface, so a plane moved out to
        # include it has no material left in front of it and the socket comes
        # straight through. The clamp lets the ring open the socket as far as
        # it can WITHOUT thinning the lip past `wall`, and where the two
        # disagree the wall wins -- which is Brett's "shrink the tooth area
        # along the outer edge", arrived at by measurement rather than a dial.
        planes = [(nn, org + nn * max(0.0, float(np.max((ring - org) @ nn)) + 1e-4))
                  for nn, org, _ in planes]
        if not planes:
            hit, ri, _ = mesh.ray.intersects_location([c], [out], multiple_hits=False)
            far = float(np.linalg.norm(hit[0] - c)) if len(ri) else wall
            planes = [(out, c + out * (far - wall))]
        swept[i] = (pts, planes)
        axes[i], outs[i] = n, out
        for q in raw:
            hh, rr, tt = mesh.ray.intersects_location([q], [out], multiple_hits=False)
            if len(rr): skin.append(hh[0])

    solids = []
    for pts, planes in swept.values():
        h = trimesh.convex.convex_hull(pts)
        for nn, org in planes:
            # A slice can come back open, empty, or not a volume -- a plane
            # pushed clear of the hull, or one that grazes it, both do it.
            # Keep the last good solid rather than handing the boolean
            # something it will refuse.
            try:
                cut = trimesh.intersections.slice_mesh_plane(
                    h, plane_normal=-nn, plane_origin=org, cap=True)
            except Exception:                              # noqa: BLE001
                continue
            if cut is None or len(cut.faces) < 4: continue
            cut = trimesh.convex.convex_hull(cut.vertices)  # convex by construction
            if cut.is_volume and cut.volume > 1e-6:
                h = cut
        if h is not None and h.is_volume and h.volume > 1e-6:
            solids.append(h)
    cut = trimesh.boolean.union(solids, engine="manifold")

    # PROTECT THE LIP LOCALLY, not with a plane.
    #
    # The ring says the socket must reach the tooth outline; the wall says it
    # must stay `wall` inside the cheek. On the labial side those disagree,
    # because the outline lies on the outer surface. Clipping cannot settle
    # it: a half-space is global, so whichever rule is applied last governs
    # the whole socket -- honour the ring and the lip vanishes (holes clean
    # through), clamp to the wall and the socket never opens (93% of every
    # outline still solid). Both were measured; neither is a compromise.
    #
    # A ball of radius `wall` sitting on the skin protects that spot and
    # nowhere else. Their union is the lip, and taking it back out of the
    # socket lets the ring win everywhere it does not cost anything.
    if skin:
        # A real union, not a pile of overlapping shells: concatenating the
        # spheres gives a mesh that is not a volume and the boolean refuses
        # it. Every other point off the ring is dense enough -- the samples
        # sit well under `wall` apart, so the union has no gaps in it.
        balls = [trimesh.creation.icosphere(subdivisions=1, radius=wall)
                 .apply_translation(p) for p in skin[::2]]
        try:
            guard = trimesh.boolean.union(balls, engine="manifold")
            cut = trimesh.boolean.difference([cut, guard], engine="manifold")
        except Exception:                                   # noqa: BLE001
            pass
    return cut


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


def _grid(poly, n):
    """Points inside a 2D polygon, on a grid sized to hold about `n` of them."""
    from shapely.geometry import Point
    x0, y0, x1, y1 = poly.bounds
    k = max(3, int(np.ceil(np.sqrt(n * (x1 - x0) * (y1 - y0) / max(poly.area, 1e-6)))))
    gx, gy = np.meshgrid(np.linspace(x0, x1, k), np.linspace(y0, y1, k))
    xy = np.column_stack([gx.ravel(), gy.ravel()])
    keep = np.array([poly.contains(Point(a, b)) for a, b in xy])
    xy = xy[keep] if keep.any() else np.array([[poly.centroid.x, poly.centroid.y]])
    return xy[:, 0], xy[:, 1]


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


def _clip_radial(poly, th, reach):
    """The section, cut back to `reach[k]` in each direction `th[k]`.

    Written in polar form about the section's own centre so the result cannot
    tie itself in a knot: pulling individual boundary points inward can make
    an outline self-intersect, but a radius per direction is star-shaped by
    construction whatever the radii are.
    """
    from shapely.geometry import Polygon, Point, LineString
    c = poly.centroid
    far = float(np.hypot(*(np.array(poly.bounds[2:]) - np.array(poly.bounds[:2])))) + 1.0
    pts = []
    for a, lim in zip(th, reach):
        d = np.array([np.cos(a), np.sin(a)])
        hit = poly.exterior.intersection(
            LineString([(c.x, c.y), (c.x + d[0] * far, c.y + d[1] * far)]))
        if hit.is_empty: continue
        g = hit.geoms[0] if hasattr(hit, "geoms") else hit
        q = np.array(g.coords[-1] if hasattr(g, "coords") else (g.x, g.y))
        r_out = float(np.hypot(*(q - np.array([c.x, c.y]))))
        r = min(r_out, float(lim))
        if r <= 0.05: continue
        pts.append((c.x + d[0] * r, c.y + d[1] * r))
    if len(pts) < 8: return None
    out = Polygon(pts)
    if not out.is_valid: out = out.buffer(0)
    return out if (isinstance(out, Polygon) and out.area > 0.5) else None


def _inset(poly, inset):
    """Shrink the section, backing off until something survives.

    A 1 mm inset is most of a narrow front tooth. Rather than dropping those
    teeth -- which is what an unchecked buffer does, silently -- take as much
    of the inset as the section can stand and report the shortfall.
    """
    from shapely.geometry import Polygon
    for f in (1.0, 0.75, 0.5, 0.35, 0.25):
        q = poly.buffer(-inset * f, join_style=1)
        if isinstance(q, Polygon) and not q.is_empty and q.area > 0.5:
            return q, inset * f
    return None, 0.0


def drill_prism(mesh, regions, frames, depth=3.5, inset=1.2, reach=7.0,
                keep=0.9, over=1.5, lean=0.0, align=1.0, radial=False,
                cone=True, report=None, **_ignored):
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
        if cone:
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
            r0, ctr = _outline_radii(sec, th)
            org = c + ctr[0] * u + ctr[1] * v
            rise = float(np.max((f["ring"] - c) @ ax)) + 0.75
            zs = np.linspace(0.0, depth, nz)

            def rings(shrink):
                """Radii at each depth for a cone closing to `shrink` at the floor."""
                k = 1.0 - (1.0 - shrink) * (zs / max(zs[-1], 1e-6))
                return np.maximum(r0[None, :] * k[:, None] - inset, 0.05)

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
            continue
        # HOW FAR MAY THE SOCKET REACH, DIRECTION BY DIRECTION.
        #
        # A uniform inset is the wrong shape of answer. It exists to keep the
        # socket off the cheek, where the outline runs right up against the
        # outer surface -- and then spends the same margin on the tongue side,
        # which has five to nine millimetres of bone behind it and nothing to
        # protect. Measured, that left the sockets holding 25% of the painted
        # tooth area, and two of them 11%. Brett, looking at the sliced file:
        # "the actual socket seems smaller than the available removed tooth
        # area."
        #
        # So ask the bone instead of a dial. From the socket's own axis, fire
        # rays outward across a fan of directions at a spread of depths; the
        # nearest surface any of them meets is how far the socket may go that
        # way, less `inset` of wall. Clipping the outline to that limit leaves
        # it at full size wherever the jaw is thick and backs it off only
        # where it is thin -- which is what the inset was always for.
        # NOT ON BY DEFAULT. Measured against the uniform inset it doubles
        # the socket area -- 25% of the tooth footprint to 50-56% -- and it
        # also drills a tunnel back through the jaw (genus 8 -> 9), comes
        # back not watertight at inset 1.0, and leaves teeth 0 and 1 with no
        # socket at all, because 1.1 mm of bone minus a 1.0 mm wall is
        # nothing. The idea is right and this implementation is not finished.
        if not radial:
            sec, got = _inset(sec, inset)
            if sec is None: continue
            if got < inset - 1e-6: short.append((i, round(got, 2)))
            return_early = False
        else:
            return_early = True
        if return_early:
         th = np.linspace(0, 2 * np.pi, 96, endpoint=False)
         dirs = np.cos(th)[:, None] * u + np.sin(th)[:, None] * v
         reach_r = np.full(len(th), np.inf)
         for z in np.linspace(0.05, max(depth, 0.3), 8):
            org = np.tile(c - ax * z, (len(th), 1))
            hh, rr, _ = mesh.ray.intersects_location(org, dirs,
                                                     multiple_hits=False)
            per = np.full(len(th), np.inf)
            for h_, r_ in zip(hh, rr):
                per[r_] = min(per[r_], float(np.linalg.norm(h_ - org[r_])))
            reach_r = np.minimum(reach_r, per - inset)
         sec = _clip_radial(sec, th, reach_r)
         got = inset
        if sec is None: continue
        # Stop before the far wall, the same rule the hull drill used: the
        # FIRST crossing going in, not the last, or a thin patch at the back
        # of the jaw lets the sweep out through the other side.
        # HOW THICK IS THE BONE IN THIS SOCKET'S OWN COLUMNS.
        #
        # Twice now the depth has been bounded by a distance measured from
        # one origin, and twice the worst point on the designer's RING has
        # governed the whole socket. The ring's labial edge lies against the
        # outer skin, so a probe there leaves the cheek in a millimetre --
        # measured, thirteen of fourteen sockets clamped to the 0.8 mm floor
        # while the one that did not read 0.3% blocked. Brett named this
        # shape of error on the hull cutter: "the hold back is too naive".
        #
        # So probe the INSET section, which is `inset` clear of the lip by
        # construction, and probe it the way the question is actually posed:
        # fire each column from outside, take the first solid span it crosses
        # -- skin in, cavity out -- and that span is the bone available to
        # this socket at that column. A constant section can only go as deep
        # as its thinnest column, less `keep`.
        rise = float(np.max((f["ring"] - c) @ ax))

        def bone(poly):
            """Thinnest bone among this section's own columns.

            Sampled densely: at 60 points the grid is re-laid for every
            polygon, so a different inset lands the samples somewhere else
            and the minimum jumps around -- tooth 1 read 1.99 mm at one
            inset and 0.72 mm at another on the SAME bone. That is the
            measurement moving, not the jaw, and a depth chosen from it is
            a coin toss.
            """
            gx, gy = _grid(poly, 400)
            Q = c + gx[:, None] * u + gy[:, None] * v + ax * (rise + 6.0)
            hits, ri, _ = mesh.ray.intersects_location(
                Q, np.tile(-ax, (len(Q), 1)), multiple_hits=True)
            span = {}
            for h, r in zip(hits, ri):
                span.setdefault(int(r), []).append(float(np.linalg.norm(h - Q[r])))
            thick = []
            for v_ in span.values():
                t = sorted(v_)             # skin in, then the cavity behind
                if len(t) > 1: thick.append(t[1] - t[0])
            return min(thick) if thick else float("inf")

        # NEVER CUT DEEPER THAN THE BONE IS THICK.
        #
        # This used to floor the depth at 0.8 mm, which is not a safety net
        # but a guarantee of the opposite: where the jaw is thinner than that
        # -- 0.72 mm at the back of tooth 1 -- the floor drove the cutter
        # straight through the wall. Brett found the hole it left and dialled
        # the inset to hide it, which worked only because the coarse probe
        # grid happened to miss the thin column at the other setting.
        #
        # So there is no floor. If the section cannot host a socket, shrink
        # the section until it can: a narrower drill standing in thicker bone
        # beats a wide one that comes out the side. Only if nothing fits is
        # the tooth left alone, and it is named rather than silently skipped.
        def escapes(poly, dd):
            """Does this prism's SIDE WALL leave the bone on its way down?

            `bone` looks straight down each column, so it catches a socket
            that would come out of the floor and is blind to one that leaves
            through the side. Teeth 10 and 11 did exactly that: squaring the
            section to the jaw grew them 83% -- far more than any other tooth
            -- until their side walls stood outside the bone, and the part
            came back with two tunnels through it that every other instrument
            here called clean.

            So walk the section's own boundary at several depths and require
            every one of those points to be inside the solid.
            """
            xy = np.asarray(poly.exterior.coords)[:-1]
            xy = xy[::max(1, len(xy) // 120)]
            # from the gum line down to the floor. Above it the prism stands
            # proud of the surface on purpose, so points up there are outside
            # by construction and would report an escape on every tooth.
            zs = np.linspace(0.05, max(dd, 0.3), 24)
            P = np.vstack([c + xy[:, :1] * u + xy[:, 1:] * v - ax * z
                           for z in zs])
            return not bool(_inside(mesh, P).all())

        # Take the WIDEST section that stays in the bone, not the deepest.
        # Ascending, first clean one wins: a socket is only worth having if
        # a tooth can sit in it, and a wider shallow one beats a narrow deep
        # one that a tooth cannot enter.
        base, choice = sec, None
        for extra in (0.0, 0.3, 0.6, 1.0, 1.4):
            # always from the ORIGINAL section, never from the last one --
            # insetting an already-inset polygon compounds, so the socket
            # ends up smaller than the number reported beside it
            poly = base if extra <= 1e-9 else _inset(base, extra)[0]
            if poly is None: break
            dd = float(min(depth, bone(poly) - keep))
            if dd < 0.3 or escapes(poly, dd): continue
            choice = (poly, dd, got + extra); break
        if choice is None:
            thin.append(i)
            continue
        sec, d, tried = choice
        # Start the sweep above the HIGHEST point of the outline, not a fixed
        # distance above its centroid. The ring follows the curve of the gum,
        # so on a tooth near the bow of the jaw its ends stand well proud of
        # the middle -- and a prism that starts level with the centroid would
        # leave those ends uncut, which is the same crescent of gum the hull
        # cutter was leaving for a different reason.
        rise = float(np.max((f["ring"] - c) @ ax))
        top = max(over, rise + 0.75)
        h = trimesh.creation.extrude_polygon(sec, d + top)
        M = np.eye(4)
        M[:3, 0], M[:3, 1], M[:3, 2] = u, v, ax
        M[:3, 3] = c - ax * d
        h.apply_transform(M)
        if report is not None:
            # Hand the caller what the cutter actually did, rather than
            # leaving an instrument to recompute it and drift.
            report.append(dict(tooth=i, section=round(float(sec.area), 2),
                               inset=round(got, 2), depth=round(d, 2),
                               rise=round(rise, 2), lean=round(lo, 3),
                               used=round(tried, 2),
                               # the footprint and what the socket kept of
                               # it -- recorded from DIFFERENT polygons, or
                               # the ratio is 100% on every tooth by
                               # construction and says nothing
                               full=round(ring_area, 2),
                               socket=round(float(sec.area), 2)))
        if h.is_volume and h.volume > 1e-6: solids.append(h)
    if short: print(f"    inset backed off on {len(short)} teeth: {short}")
    if thin: print(f"    no room for a socket in {len(thin)} teeth: {thin}")
    return trimesh.boolean.union(solids, engine="manifold")


def channel(mesh, frames, regions=None, width=3.5, depth=3.0, over=0.6,
            centre=True, wall=1.6, min_width=1.6, reach=4.0, depth_max=3.5,
            mode="prism", **extra):
    """The solids to subtract for the ledge. One, now, not a hundred and sixty."""
    if mode == "prism":
        for k in ("grow", "rscale", "lip"): extra.pop(k, None)
        return [drill_prism(mesh, regions, frames, depth=depth_max,
                            reach=reach, **extra)]
    for k in ("inset", "lean", "align", "radial", "cone"):
        extra.pop(k, None)
    return [drill_ledge(mesh, regions, frames, depth=depth_max, wall=wall,
                        reach=reach, **extra)]
