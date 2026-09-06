#!/usr/bin/env python3
"""How deep the puzzle is, measured rather than argued.

`assembly.disassemble` answers one question — does this come apart — and it
answers it greedily: it takes the first move it finds and never looks back.
That is the right gate for a part that must be assemblable, and it says
nothing at all about whether the object is any good to play with. A cube
that falls open in two moves and a knot that takes nine both "come apart".

So this is the same machinery run as a search instead of a walk. A state is
where every body is sitting, not merely which bodies are left, because the
moves that make a puzzle interesting do not free anything: a head screwed
further IN so a neighbour can slide is a move, and a search that only
records removals cannot see it happen. Bodies therefore carry poses, moves
carry them between poses, and taking the thing apart is a shortest path
through that graph.

Three numbers come out, and they are the ones to iterate the geometry
against:

    legal first moves   how many things a hand can try at the start. One is
                        the target. Zero means welded; four means the
                        solver wanders into the answer.
    solve length        moves on the shortest path. Below about seven is a
                        catch, not a puzzle; far above nine is tedium,
                        because past the third dependency every move is
                        forced and forced moves are not decisions.
    retrograde          whether the shortest solution requires moving a body
                        the wrong way — screwing in to release. This is the
                        one that stops the object being solvable by pulling
                        at it, and no amount of extra blocks buys it.

An affordance is not a motion. Slide, right-hand screw and left-hand screw
along one line in one direction are three motions and one thing a hand can
see to try, so the headline count collapses them; the full breakdown is
reported underneath for when the difference matters.

WHAT IS ASSUMED

Almost nothing, deliberately, and for the reason the mobility search exists
at all: a part is trapped when a motion is ABSENT, so any motion left out of
the model is a trap the search cannot report. Every body is offered every
line, both directions, and all three couplings; nothing declares which body
is "the bolt" or which line is "its axis". A screw along a line a body is
not threaded on simply collides, and costs a sweep to find that out. That
cost is the price of not writing the couplings down, which is the same
bargain `escapes` already struck.

WHAT IS NOT

Poses compose as 4x4s, so a body may travel on one line and then another,
but every move is a helix on one of the given lines. A body that only comes
free by being tilted, or by travelling on a line nobody listed, reports as
stuck. That is the honest failure — it under-reports mobility and so can
call a working design welded, which is loud, rather than over-report it and
call a welded design working, which is silent.
"""
import heapq
import itertools

import numpy as np
import trimesh
import trimesh.collision as tc

from assembly import extent_along, helix

PARK_REST = np.array([1e5, 0.0, 0.0])     # two far corners, so that the
PARK_MOVE = np.array([-1e5, 0.0, 0.0])    # parked never meet the parked


def _park(offset):
    T = np.eye(4)
    T[:3, 3] = offset
    return T


class Mobility:
    """Bodies, the lines they may travel, and the graph that falls out."""

    def __init__(self, parts, lines, lead, clearance=0.30, quantum=None,
                 reach=None, budget=4000, max_group=2, coarse=8.0):
        self.names = sorted(parts)
        self.parts = dict(parts)
        self.lines = [(np.asarray(d, float) / np.linalg.norm(d),
                       np.asarray(o, float)) for d, o in lines]
        self.lead = float(lead)
        self.clearance = float(clearance)
        # One lead is one full turn, which is the unit a hand actually works
        # in; a finer quantum only multiplies states that no hand can tell
        # apart.
        self.quantum = float(lead if quantum is None else quantum)
        whole = trimesh.util.concatenate(list(parts.values()))
        self.reach = float(max(whole.extents) * 1.5 if reach is None
                           else reach)
        self.budget = int(budget)
        self.max_group = int(max_group)
        # Search coarse, confirm fine. Sampling more thinly can only SKIP a
        # collision, never invent one, so a coarse sweep over-reports
        # freedom and never under-reports it — which is the safe direction
        # to be wrong in, because every move that survives into the answer
        # is re-swept at the full half-clearance step afterwards and has to
        # hold up. A search that erred the other way would quietly call a
        # working design welded and nothing would catch it.
        self.delta = clearance / 2.0
        self.coarse = self.delta * float(coarse)
        self.queries = 0

        # BVHs are built here, once, and never again: FCL rebuilds one for
        # every mesh handed to `in_collision_single`, which costs 80x the
        # query and is the whole reason a search this dense is affordable.
        self.rest_cm, self.move_cm = tc.CollisionManager(), tc.CollisionManager()
        for n, m in self.parts.items():
            self.rest_cm.add_object(n, m)
            self.move_cm.add_object(n, m)
        self.home_span = {n: [extent_along(m, d) for d, _ in self.lines]
                          for n, m in self.parts.items()}
        self.home_r = {n: [self._radius(m.vertices, d, o)
                           for d, o in self.lines]
                       for n, m in self.parts.items()}

    @staticmethod
    def _radius(v, d, o):
        w = np.asarray(v) - o
        return float(np.linalg.norm(w - np.outer(w @ d, d), axis=1).max())

    # --- states ---------------------------------------------------------
    #
    # A state is the poses of the bodies still present. Poses are keyed
    # coarsely on purpose: two configurations a printer could not tell apart
    # are the same state, and keeping them separate only inflates the graph.

    def home(self):
        return {n: np.eye(4) for n in self.names}

    def key(self, poses):
        out = []
        for n in sorted(poses):
            T = poses[n]
            t = np.round(T[:3, 3] / (self.quantum / 4.0)).astype(int)
            r = np.round(T[:3, :3] * 8.0).astype(int)
            out.append((n, tuple(t), tuple(r.ravel())))
        return tuple(out)

    def _place_rest(self, poses, group):
        """Once per sweep: nothing on the rest side moves while the mover does.

        Setting all of it per sample was most of the cost of the first
        build — a transform the geometry never asked for, paid for at every
        one of two hundred thousand queries.
        """
        for n in self.names:
            here = n in poses and n not in group
            self.rest_cm.set_transform(n, poses[n] if here
                                       else _park(PARK_REST))
            if not (n in poses and n in group):
                self.move_cm.set_transform(n, _park(PARK_MOVE))

    def _place_mover(self, poses, group, mover_T):
        for n in group:
            self.move_cm.set_transform(n, mover_T @ poses[n])

    def _hits(self):
        self.queries += 1
        return self.rest_cm.in_collision_other(self.move_cm)

    # --- one sweep ------------------------------------------------------

    def travel(self, poses, group, li, direction, coupling, delta=None):
        """How far this group gets along one line, and whether it gets out.

        Returns (stops, escaped): `stops` are the quantised distances the
        group can reach, `escaped` says the last of them carries it clear of
        everything left. One sweep yields every stop along it, so the
        partial moves cost nothing beyond the escape they are looking for.

        The helix is phased to home, not to where the body is now. A thread
        is only free to travel along the one helix it is already sitting on;
        re-zeroing the rotation at the current position asks it to jump a
        fraction of a turn it has no room for.
        """
        d, o = self.lines[li]
        rest = [n for n in poses if n not in group]
        if not rest:
            return [], False
        r_lo = min(self.home_span[n][li][0] + float(poses[n][:3, 3] @ d)
                   for n in rest)
        r_hi = max(self.home_span[n][li][1] + float(poses[n][:3, 3] @ d)
                   for n in rest)
        g_lo = min(self.home_span[n][li][0] + float(poses[n][:3, 3] @ d)
                   for n in group)
        g_hi = max(self.home_span[n][li][1] + float(poses[n][:3, 3] @ d)
                   for n in group)
        # Rotation about the line and travel along it both preserve the
        # projection onto it, so the group's extent under this motion is its
        # extent now plus the distance travelled. No per-sample transform of
        # vertices, and it is exact rather than a bound.
        max_r = max(self._radius(
            trimesh.transform_points(self.parts[n].vertices, poses[n]), d, o)
            for n in group)

        gap = self.clearance / 2.0
        s0 = direction * gap
        s1 = direction * self.reach
        lead_s = None if coupling is None else coupling * self.lead
        th0 = 0.0 if lead_s is None else 2.0 * np.pi * s0 / lead_s
        path = helix(s0, s1, d, o, lead_s, th0, max_r,
                     delta=self.coarse if delta is None else delta)
        span = s1 - s0
        free_to = 0.0
        escaped = False
        self._place_rest(poses, group)
        for i, T in enumerate(path):
            self._place_mover(poses, group, T)
            if self._hits():
                break
            s = s0 + span * i / (len(path) - 1)
            free_to = s
            if (g_lo + s > r_hi + 0.05) or (g_hi + s < r_lo - 0.05):
                escaped = True
                break
        stops = []
        k = 1
        while k * self.quantum <= abs(free_to) + 1e-9:
            stops.append(direction * k * self.quantum)
            k += 1
        if escaped:
            # The escape stop is emitted even when it is shorter than the
            # standoff. A body that is already clear along this line — a lid
            # sitting on a box, a part that simply lifts off — goes clear on
            # the first sample, and a guard that reads "it did not travel far
            # enough to count" throws exactly that case away and calls the
            # loosest joint in the assembly welded.
            stops.append(free_to)
            return stops, True
        if abs(free_to) <= gap + 1e-9:
            return [], False
        return stops, False

    # --- the move set at one state --------------------------------------

    def moves(self, poses):
        """Every legal move from here.

        Groups are only asked about when nothing single will move, which is
        what a hand does: it tries one part, and only when no part shifts
        does it try lifting two that are locked to each other.
        """
        found = self._moves_of_size(poses, 1)
        k = 2
        while not found and k <= min(self.max_group, len(poses) - 1):
            found = self._moves_of_size(poses, k)
            k += 1
        return found

    def _moves_of_size(self, poses, k):
        out = []
        for grp in itertools.combinations(sorted(poses), k):
            if len(grp) >= len(poses):
                continue
            for li in range(len(self.lines)):
                for direction in (1, -1):
                    for coupling in (None, 1, -1):
                        stops, esc = self.travel(poses, grp, li, direction,
                                                 coupling)
                        for j, s in enumerate(stops):
                            out.append({
                                "parts": list(grp), "line": li,
                                "direction": direction, "coupling": coupling,
                                "distance": round(float(s), 2),
                                "frees": bool(esc and j == len(stops) - 1)})
        return out

    def apply(self, poses, mv):
        """The state a move lands in. A freeing move drops its bodies."""
        d, o = self.lines[mv["line"]]
        s = mv["distance"]
        th = 0.0 if mv["coupling"] is None else \
            2.0 * np.pi * s / (mv["coupling"] * self.lead)
        T = trimesh.transformations.rotation_matrix(th, d, o)
        T[:3, 3] += d * s
        nxt = dict(poses)
        for n in mv["parts"]:
            if mv["frees"]:
                nxt.pop(n)
            else:
                nxt[n] = T @ poses[n]
        return nxt

    @staticmethod
    def affordances(moves):
        """Distinct things a hand can see to try, couplings collapsed."""
        return {(tuple(m["parts"]), m["line"], m["direction"]) for m in moves}

    # --- the search -----------------------------------------------------

    def solve(self):
        """Shortest disassembly, breadth first, with the metrics on the way.

        Breadth first and not greedy: the greedy walk in `disassemble` takes
        the first move it finds, which reports A solution and so cannot
        report the SHORTEST one — and the shortest one is the number a
        player experiences.
        """
        start = self.home()
        first = self.moves(start)
        report = {
            "bodies": len(self.names),
            "legal_first_moves": len(self.affordances(first)),
            "first_move_motions": len(first),
            "first_affordances": sorted(
                f"{'+' if s > 0 else '-'}{'/'.join(p)}@L{l}"
                for p, l, s in self.affordances(first))}
        if not first:
            return {**report, "comes_apart": False, "welded": True,
                    "queries": self.queries}

        seen = {self.key(start)}
        q = [(0, 0, start, [])]
        best, seq, tick = None, None, 0
        while q:
            n, _, poses, path = heapq.heappop(q)
            if len(poses) <= 1:
                best, seq = n, path
                break
            if len(seen) > self.budget:
                return {**report, "comes_apart": None,
                        "why": f"more than {self.budget} states reachable — "
                               f"the assembly is loose, not deep",
                        "queries": self.queries}
            for mv in (first if not path else self.moves(poses)):
                nxt = self.apply(poses, mv)
                kk = self.key(nxt)
                if kk in seen:
                    continue
                seen.add(kk)
                tick += 1
                heapq.heappush(q, (n + 1, tick, nxt, path + [mv]))
        if best is None:
            return {**report, "comes_apart": False,
                    "states_explored": len(seen), "queries": self.queries}
        # one representative motion per affordance, which is what was counted
        seen_aff, reps = set(), []
        for mv in first:
            a = (tuple(mv["parts"]), mv["line"], mv["direction"])
            if a not in seen_aff:
                seen_aff.add(a)
                reps.append(mv)
        bad = self.confirm(seq, reps)
        return {**report, "comes_apart": True, "solve_length": best,
                "states_explored": len(seen), "queries": self.queries,
                "retrograde": self.retrograde(seq),
                "confirmed": not bad, **({"unconfirmed": bad} if bad else {}),
                "solution": seq}

    def confirm(self, seq, first=()):
        """Re-sweep the answer at the full step. The coarse pass is a filter.

        Every move that reached the reported solution, and every affordance
        counted at the start, is walked again at half the running clearance
        — the step at which nothing thinner than the gap the design is built
        around can hide between samples. A move that only existed because
        the search stepped over an obstacle shows up here, and it shows up
        as a named failure rather than as a number quietly one too small.
        """
        bad = []
        for label, poses, mv in [("first", self.home(), m) for m in first]:
            stops, esc = self.travel(poses, mv["parts"], mv["line"],
                                     mv["direction"], mv["coupling"],
                                     delta=self.delta)
            if not stops:
                bad.append({"where": label, "step": describe(mv),
                            "free_to": 0.0})
        poses = self.home()
        for i, mv in enumerate(seq):
            stops, esc = self.travel(poses, mv["parts"], mv["line"],
                                     mv["direction"], mv["coupling"],
                                     delta=self.delta)
            far = max((abs(s) for s in stops), default=0.0)
            # A freeing move is judged on whether it still frees, not on how
            # far it ran: the escape distance is wherever the sweep happened
            # to notice the body was clear, so it moves with the step and a
            # fine pass legitimately reports a slightly shorter one. Holding
            # it to the coarse number fails every move that works.
            ok = esc if mv["frees"] else abs(mv["distance"]) <= far + 1e-6
            if not ok:
                bad.append({"where": f"move {i + 1}", "step": describe(mv),
                            "free_to": round(far, 2), "frees": esc})
            poses = self.apply(poses, mv)
        return bad

    @staticmethod
    def retrograde(seq):
        """Moves on the solution that go the wrong way.

        A body's escape direction along a line is the direction it finally
        leaves in. Any earlier move of that body, on that same line, in the
        opposite direction, is a move that undoes progress — tighten to
        release. It is the only entry in this report that cannot be bought
        with more blocks.
        """
        leaves = {}
        for mv in seq:
            if mv["frees"]:
                for n in mv["parts"]:
                    leaves[n] = (mv["line"], mv["direction"])
        out = []
        for i, mv in enumerate(seq):
            if mv["frees"]:
                continue
            for n in mv["parts"]:
                if n in leaves and leaves[n] == (mv["line"],
                                                 -mv["direction"]):
                    out.append({"move": i, "part": n,
                                "distance": mv["distance"]})
        return out


def describe(mv):
    how = {None: "slide", 1: "screw+", -1: "screw-"}[mv["coupling"]]
    return (f"{'+' if mv['direction'] > 0 else '-'}{how} "
            f"{'/'.join(mv['parts'])} {abs(mv['distance']):.1f}mm on L"
            f"{mv['line']}{' -> free' if mv['frees'] else ''}")
