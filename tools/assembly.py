#!/usr/bin/env python3
"""Swept-path verification: does the thing actually go together.

A fit test asks whether two parts overlap in a pose. That is not the
question. The question is whether a continuous motion exists that carries
one part from apart to assembled without ever overlapping, and a pose test
cannot see the difference — the seed cube's first build passed every pose
test and could not have been assembled at all, because its keyed head had
to arrive at its keyway while rotating and can only align once in sixty
degrees.

So motions are sampled, not poses, and the sampling rate is derived rather
than picked. Between two consecutive samples the fastest-moving point of
the mover travels

    hypot(max_r * dtheta, dz)

and if that exceeds a feature's size the feature can pass clean through
another one unseen — the mover teleports across the obstacle and the sweep
reports a clear path that does not exist. `delta` is that step, and the
default is half the running clearance: nothing thinner than the gap the
design is built around can hide between samples. `max_r` is the mover's
true bounding radius about the axis, not the radius of whatever part of it
seems relevant, because "seems relevant" is the assumption the geometry is
supposed to be testing.

Collision objects are built once and only their transforms updated. FCL
rebuilds a BVH for every mesh handed to `in_collision_single`, which costs
more than the query, and it is the reason a dense sweep looks unaffordable
until it isn't.
"""
import numpy as np
import trimesh
import trimesh.collision as tc


def helix(s0, s1, direction=(0, 0, 1), origin=(0, 0, 0), lead=None,
          theta0=0.0, max_r=1.0, delta=None, clearance=0.30):
    """Transforms sampling a screw along an arbitrary line, or a pure slide.

    The line is (origin, direction); travel and rotation share it, which is
    what a screw is. The seed cube only ever needed the z axis, but the Knot
    has three mutually skew ones, and a search that can only sweep along z
    cannot report on it at all — it would call every body welded, and that
    is exactly the failure this project has already paid for once.

    Right-handed: advancing one lead along +direction turns the mover one
    full turn counter-clockwise seen from +direction, the sense the
    generated thread is cut in. Getting this backwards produces a path that
    collides immediately and reads as a geometry failure.
    """
    d = np.asarray(direction, dtype=float)
    d = d / np.linalg.norm(d)
    o = np.asarray(origin, dtype=float)
    delta = clearance / 2.0 if delta is None else delta
    ds = float(s1 - s0)
    dth = 0.0 if lead is None else 2.0 * np.pi * ds / float(lead)
    n = int(np.ceil(np.hypot(abs(max_r * dth), abs(ds)) / delta)) + 1
    n = max(n, 2)
    out = []
    for u in np.linspace(0.0, 1.0, n):
        T = trimesh.transformations.rotation_matrix(theta0 + dth * u, d, o)
        T[:3, 3] += d * (s0 + ds * u)
        out.append(T)
    return out


def screw_path(z0, z1, lead=None, theta0=0.0, max_r=1.0, delta=None,
               clearance=0.30, axis=2):
    """`helix` down a coordinate axis, which is what the seed cube uses."""
    d = np.zeros(3)
    d[axis] = 1.0
    return helix(z0, z1, d, (0, 0, 0), lead, theta0, max_r, delta, clearance)


def extent_along(mesh, direction):
    """(min, max) of the mesh projected onto a direction.

    Vertices, not the axis-aligned bounds: a box's AABB overstates its reach
    along any direction that is not one of its own axes, and overstating
    reach means declaring a body clear of an obstacle it is still inside.
    """
    p = mesh.vertices @ (np.asarray(direction, dtype=float)
                         / np.linalg.norm(direction))
    return float(p.min()), float(p.max())


class Sweep:
    """One static body, one mover, many poses."""

    def __init__(self, static, mover):
        self.cm = tc.CollisionManager()
        self.cm.add_object("static", static)
        self.cm.add_object("mover", mover)
        self.mover = mover
        self.max_r = self.radius()

    def radius(self, direction=(0, 0, 1), origin=(0, 0, 0)):
        """The mover's true bounding radius about a line.

        The sampling step is derived from this, so it has to be the radius
        of the whole body and not of whatever part of it seems relevant:
        "seems relevant" is the assumption the geometry is supposed to be
        testing. About a line the mover straddles, the far corner is what
        moves fastest, and it is the far corner that skips an obstacle if
        the step is too coarse.
        """
        d = np.asarray(direction, dtype=float)
        d = d / np.linalg.norm(d)
        v = self.mover.vertices - np.asarray(origin, dtype=float)
        return float(np.linalg.norm(v - np.outer(v @ d, d), axis=1).max())

    def run(self, transforms):
        """Index of the first colliding sample, or None if the path is free."""
        for i, T in enumerate(transforms):
            self.cm.set_transform("mover", T)
            if self.cm.in_collision_internal():
                return i
        return None

    def free(self, transforms):
        return self.run(transforms) is None

    def blocked_fraction(self, transforms):
        """Where along the path it first fouls, as a fraction. None if free."""
        i = self.run(transforms)
        return None if i is None else i / (len(transforms) - 1)


def slide_in(static, mover, z0, z1, theta0=0.0, clearance=0.30, delta=None):
    """Pure translation: the insertion vector with no rotation allowed."""
    s = Sweep(static, mover)
    return s, s.run(screw_path(z0, z1, None, theta0, s.max_r, delta,
                               clearance))


def screw_in(static, mover, z0, z1, lead, theta0=0.0, clearance=0.30,
             delta=None):
    """Coupled rotation and advance, at the thread's own lead."""
    s = Sweep(static, mover)
    return s, s.run(screw_path(z0, z1, lead, theta0, s.max_r, delta,
                               clearance))


def find_phase(static, mover, z, lead, step_deg=2.0, clearance=0.30):
    """The rotation at which the mover is free at this depth, if any.

    A screw path has to start somewhere on the helix. Starting at an
    arbitrary angle collides at once and says nothing about the path.
    """
    s = Sweep(static, mover)
    free = []
    for a in np.arange(0.0, 360.0, step_deg):
        T = trimesh.transformations.rotation_matrix(np.radians(a), [0, 0, 1])
        T[2, 3] = z
        s.cm.set_transform("mover", T)
        if not s.cm.in_collision_internal():
            free.append(a)
    if not free:
        return None, 0.0
    arr = np.radians(free)
    ctr = np.degrees(np.arctan2(np.sin(arr).mean(),
                                np.cos(arr).mean())) % 360.0
    return np.radians(ctr), len(free) * step_deg


if __name__ == "__main__":
    import json
    import sys
    import time
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    from thread import Thread

    t = Thread(major_r=8.0)
    nut, bolt = t.nut(), t.bolt(shank_len=30.0)
    shank = t.shank_only(bolt)
    h = 1.717 * t.major_r
    th0, win = find_phase(nut, shank, h - 3.0, t.lead, clearance=t.clearance)
    t0 = time.time()
    s, hit = screw_in(nut, shank, h - 3.0, -6.0, t.lead, theta0=th0,
                      clearance=t.clearance)
    p = screw_path(h - 3.0, -6.0, t.lead, th0, s.max_r,
                   clearance=t.clearance)
    dt = time.time() - t0
    print(json.dumps({
        "samples": len(p), "seconds": round(dt, 2),
        "us_per_query": round(dt / len(p) * 1e6),
        "mover_max_r": round(s.max_r, 2),
        "start_window_deg": win,
        "screwed_all_the_way_through": hit is None,
        "first_foul_at": hit}, indent=2))


# --- mobility: can this thing come apart at all -------------------------
#
# The gates above each check a motion someone thought of, which cannot find
# a part that is trapped: that failure is the *absence* of a motion, and
# there is no path to sample. A pair carrying both a rotational key and a
# thread is the case that bit this project — the key forbids relative
# rotation, the thread says axial travel requires it, so the pair has zero
# degrees of freedom and is welded. Nothing about either constraint alone
# looks wrong.
#
# So instead of modelling the couplings, the geometry is asked. A candidate
# body is swept away from its home pose under every motion the assembly
# could plausibly allow — slide, right-hand screw, left-hand screw, each
# way along the axis — and if any one carries it clear without touching,
# it comes off. The couplings are never written down, so they cannot be
# written down wrong.

def _clear_along(mover_span, static_span, s, direction, gap=0.05):
    """Has the mover travelled far enough along the axis to be past it.

    Past it on the side it is travelling toward. A body that starts beyond
    the static one and moves back at it is apart at its first sample and
    is not escaping.
    """
    if direction > 0:
        return mover_span[0] + s > static_span[1] + gap
    return mover_span[1] + s < static_span[0] - gap


Z_AXIS = ((0.0, 0.0, 1.0), (0.0, 0.0, 0.0))


def escapes(rest, mover, lead, axes=(Z_AXIS,), span=None, clearance=0.30):
    """Every motion that frees `mover` from `rest`.

    Each result is (axis index, direction, coupling): coupling None is a
    pure slide, +1 and -1 the two handednesses of a screw at this lead.
    `axes` is a sequence of (direction, origin) lines — the seed cube has
    one, the Knot has three, and a body is only asked about the lines it
    could actually travel on. Sweeps stop the moment the two bodies are
    clear along the axis, so a successful escape costs only the travel it
    actually needs.

    The home sample itself is never tested. Assembled parts are in contact
    by design — seam face on seam face, head on the floor of its pocket —
    and FCL scores contact as collision, so a search that tested home would
    call every body welded. The first build of this search did exactly
    that, and called the working design welded as loudly as the broken one,
    which is the only reason it was caught: two designs that differ cannot
    both be right. Every sample after home is tested, and none of the
    motion between home and the first sample is skipped.
    """
    s = Sweep(rest, mover)
    out = []
    for ai, (d, o) in enumerate(axes):
        ms = extent_along(mover, d)
        rs = extent_along(rest, d)
        reach = (rs[1] - rs[0]) + (ms[1] - ms[0]) + 4.0 if span is None \
            else span
        max_r = s.radius(d, o)
        for direction in (1, -1):
            for coupling in (None, 1, -1):
                s0, s1 = 0.0, direction * reach
                lead_s = None if coupling is None else coupling * lead
                path = helix(s0, s1, d, o, lead_s, 0.0, max_r,
                             clearance=clearance)
                ok = False
                for i, T in enumerate(path):
                    # Home is not tested, and nothing between home and the
                    # first sample is skipped. The old standoff started a
                    # half-clearance out along the axis, which on a screw
                    # phased to home is a rotation taken before the first
                    # sample -- 10 degrees on this lead -- and a body
                    # turning about a line far from its features moves them
                    # millimetres in that jump.
                    if i == 0:
                        continue
                    s.cm.set_transform("mover", T)
                    if s.cm.in_collision_internal():
                        break
                    if _clear_along(ms, rs, s0 + (s1 - s0) * i
                                    / (len(path) - 1), direction):
                        ok = True
                        break
                if ok:
                    out.append((ai, direction, coupling))
    return out


def disassemble(parts, lead, axes=(Z_AXIS,), clearance=0.30, max_group=2):
    """Take the assembly apart, or report what stays stuck.

    Bodies are tried alone and in groups, because the seed cube only comes
    apart if the bolt and the upper half leave together — no single part is
    free at the start. A group is moved as one rigid body, which is what a
    hand does when it lifts two parts that are locked to each other.
    """
    import itertools
    names = list(parts)
    steps, remaining = [], set(names)
    while len(remaining) > 1:
        moved = None
        for k in range(1, min(max_group, len(remaining) - 1) + 1):
            for grp in itertools.combinations(sorted(remaining), k):
                rest = [parts[n] for n in sorted(remaining) if n not in grp]
                if not rest:
                    continue
                mover = trimesh.util.concatenate([parts[n] for n in grp])
                found = escapes(trimesh.util.concatenate(rest), mover,
                                lead, axes=axes, clearance=clearance)
                if found:
                    moved = (grp, found)
                    break
            if moved:
                break
        if not moved:
            return steps, sorted(remaining)      # welded: nothing can leave
        grp, how = moved
        steps.append({"free": list(grp), "by": [
            {"axis": a, "direction": d, "coupling": c} for a, d, c in how]})
        remaining -= set(grp)
    return steps, []
