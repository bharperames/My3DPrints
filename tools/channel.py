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

def recentre(mesh, C, N, depth):
    """Slide each sample sideways onto the middle of the bone ridge.

    The teeth are not centred on the jaw: measured on this skull they sit
    0.88 mm outboard of the ridge midline. Cutting a trough centred on the
    teeth therefore spends the width it has on the outer side and breaks
    through the palate -- at 3.5 mm it was through for 81% of its length.
    Centred on the bone instead, the same 3.5 mm clears.
    """
    out = C.copy()
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
    return out

def channel(mesh, frames, width=3.5, depth=3.0, over=1.0, centre=True):
    """A trough of `width` and `depth` threaded through the tooth bases."""
    order = order_along_jaw(frames)
    C, N = resample(np.array([frames[i]["c"] for i in order]),
                    np.array([frames[i]["n"] for i in order]))
    if centre: C = recentre(mesh, C, N, depth)
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
        a = np.cross(N[k], t)
        if np.linalg.norm(a) < 1e-9: continue
        a = a / np.linalg.norm(a)
        n = np.cross(t, a); n = n / np.linalg.norm(n)
        if np.dot(n, N[k]) < 0: n = -n
        box = trimesh.creation.box([width, 2.2 * step, depth + over])
        M = np.eye(4)
        M[:3, 0], M[:3, 1], M[:3, 2] = a, t, n
        M[:3, 3] = C[k] + n * (over - depth) / 2.0
        box.apply_transform(M)
        segs.append(box)
    return segs
