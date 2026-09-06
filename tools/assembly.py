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


def screw_path(z0, z1, lead=None, theta0=0.0, max_r=1.0, delta=None,
               clearance=0.30, axis=2):
    """Transforms sampling a screw motion, or a pure slide when lead is None.

    Right-handed: advancing by one lead in +z turns the mover one full turn
    counter-clockwise seen from +z, which is the sense the generated thread
    is cut in. Getting this backwards produces a path that collides
    immediately and reads as a geometry failure.
    """
    delta = clearance / 2.0 if delta is None else delta
    dz = float(z1 - z0)
    dth = 0.0 if lead is None else 2.0 * np.pi * dz / float(lead)
    n = int(np.ceil(np.hypot(abs(max_r * dth), abs(dz)) / delta)) + 1
    n = max(n, 2)
    out = []
    for u in np.linspace(0.0, 1.0, n):
        T = trimesh.transformations.rotation_matrix(theta0 + dth * u,
                                                    [0, 0, 1])
        T[axis, 3] = z0 + dz * u
        out.append(T)
    return out


class Sweep:
    """One static body, one mover, many poses."""

    def __init__(self, static, mover):
        self.cm = tc.CollisionManager()
        self.cm.add_object("static", static)
        self.cm.add_object("mover", mover)
        self.mover = mover
        self.max_r = float(np.hypot(mover.vertices[:, 0],
                                    mover.vertices[:, 1]).max())

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

def _axial_clear(mover_z, static_z, dz, gap=0.05):
    return (mover_z[0] + dz > static_z[1] + gap or
            mover_z[1] + dz < static_z[0] - gap)


def escapes(rest, mover, lead, span=None, clearance=0.30, start_gap=None):
    """Every motion that frees `mover` from `rest`, as (direction, coupling).

    coupling None is a pure slide; +1 and -1 are the two handednesses of a
    screw at this lead. Sweeps stop the moment the two bodies are axially
    clear, so a successful escape costs only the travel it actually needs.

    Paths begin a half-clearance off home, not at home. Assembled parts are
    in contact by design — seam face on seam face, head on the floor of its
    pocket, bolt tip flush with the underside — and FCL scores contact as
    collision, so a path starting at home dies on its first sample and every
    body reports as welded. Leaving contact is not an obstruction. The first
    build of this search had no standoff and called the working design
    welded exactly as loudly as the broken one, which is the only reason it
    was caught: two designs that differ cannot both be right.
    """
    sz = (float(rest.bounds[0][2]), float(rest.bounds[1][2]))
    mz = (float(mover.bounds[0][2]), float(mover.bounds[1][2]))
    if span is None:
        span = (sz[1] - sz[0]) + (mz[1] - mz[0]) + 4.0
    gap = clearance / 2.0 if start_gap is None else start_gap
    s = Sweep(rest, mover)
    out = []
    for direction in (1, -1):
        for coupling in (None, 1, -1):
            z0, dz = direction * gap, direction * span
            lead_s = None if coupling is None else coupling * lead
            path = screw_path(z0, dz, lead_s, 0.0, s.max_r,
                              clearance=clearance)
            if lead_s is not None:
                # keep the helix phased to home, not to the standoff
                for T in path:
                    a = 2.0 * np.pi * T[2, 3] / lead_s
                    c_, s_ = np.cos(a), np.sin(a)
                    T[0, 0], T[0, 1] = c_, -s_
                    T[1, 0], T[1, 1] = s_, c_
            ok = False
            for T in path:
                s.cm.set_transform("mover", T)
                if s.cm.in_collision_internal():
                    break
                if _axial_clear(mz, sz, T[2, 3]):
                    ok = True
                    break
            if ok:
                out.append((direction, coupling))
    return out


def disassemble(parts, lead, clearance=0.30, max_group=2):
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
                found = escapes(trimesh.util.concatenate(rest), mover, lead,
                                clearance=clearance)
                if found:
                    moved = (grp, found)
                    break
            if moved:
                break
        if not moved:
            return steps, sorted(remaining)      # welded: nothing can leave
        grp, how = moved
        steps.append({"free": list(grp), "by": [
            {"direction": d, "coupling": c} for d, c in how]})
        remaining -= set(grp)
    return steps, []
