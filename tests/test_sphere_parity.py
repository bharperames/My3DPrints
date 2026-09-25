"""The browser's sphere-stand math must equal the generator's.

docs/sphere-math.js exists so a dial can move at frame rate and a limit can
bite while you drag. That is worth having and it is a second implementation
of geometry that is already written once, which is the arrangement this shop
has been bitten by all session: two descriptions of one object, drifting.

So they are not allowed to drift. This runs the JS under node and the Python
in process over the same sweep and fails on any disagreement -- in the
measurements, in WHERE a limit falls, and in the sentence a refusal gives.

If node is not on the machine the suite says so and skips, rather than
passing quietly on a comparison it never made.
"""
import json
import os
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gen_sphere_stand as G  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(HERE, "..", "docs", "sphere-math.js")

# the corners and the middle: the auto values, the dial's own stops, and
# settings chosen to land on each gate in turn
CASES = []
for ball in (8.0, 12.0, 25.4, 40.0, 60.0, 76.2, 120.0, 200.0):
    a = G.auto(ball)
    CASES.append((ball, a["base"], a["wall"], a["chamfer"], a["seat"]))
    CASES.append((ball, a["base"], 2.5, 0.8, 1.0))
    CASES.append((ball, a["base"], 1.2, 0.0, 0.4))
    CASES.append((ball, G.max_base(ball, 2.5), 2.5, 0.8, 1.0))
    CASES.append((ball, a["base"], 2.5, 12.0, 1.0))      # chamfer way over
    CASES.append((ball, a["base"] * 1.5, 2.5, 0.8, 1.0))  # base way over


def node():
    return shutil.which("node")


def run_js(cases):
    src = """
import { measure, refuse, maxBase, maxChamfer, segmentsFor }
  from %s;
const cases = %s;
const out = cases.map(([ball, base, wall, chamfer, seat]) => ({
  refuse: refuse(ball, base, wall, chamfer, seat),
  maxBase: maxBase(ball, wall),
  maxChamfer: maxChamfer(ball, base, wall, seat),
  measure: measure(ball, base, wall, chamfer, seat),
}));
console.log(JSON.stringify(out));
""" % (json.dumps(os.path.abspath(JS)), json.dumps(cases))
    p = subprocess.run([node(), "--input-type=module", "-e", src],
                       capture_output=True, text=True, timeout=120)
    if p.returncode:
        raise AssertionError("node failed: " + (p.stderr or "")[-600:])
    return json.loads(p.stdout)


def py_one(ball, base, wall, chamfer, seat):
    """What the generator says, in the shape the JS returns."""
    out = dict(maxBase=G.max_base(ball, wall),
               maxChamfer=G.max_chamfer(ball, base, wall, seat))
    if not 8 <= ball <= 200:
        return dict(out, refuse="ball must be 8-200 mm", measure=None)
    try:
        _, rep = G.build(ball, base, wall, chamfer, seat)
    except ValueError as e:
        return dict(out, refuse=str(e), measure=None)
    return dict(out, refuse=None, measure=rep)


@unittest.skipUnless(node(), "node is not installed; the JS half cannot run")
class TestSphereParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = run_js(CASES)
        cls.py = [py_one(*c) for c in CASES]

    def test_the_two_agree_on_where_every_limit_falls(self):
        for c, j, p in zip(CASES, self.js, self.py):
            self.assertAlmostEqual(j["maxBase"], p["maxBase"], places=9, msg=str(c))
            self.assertAlmostEqual(j["maxChamfer"], p["maxChamfer"],
                                   places=9, msg=str(c))

    def test_the_two_refuse_the_same_settings_for_the_same_reason(self):
        for c, j, p in zip(CASES, self.js, self.py):
            self.assertEqual(j["refuse"] is None, p["refuse"] is None,
                             f"{c}: js={j['refuse']!r} py={p['refuse']!r}")
            if p["refuse"]:
                self.assertEqual(j["refuse"], p["refuse"], str(c))

    def test_the_two_measure_the_same_ring(self):
        checked = 0
        for c, j, p in zip(CASES, self.js, self.py):
            if p["measure"] is None:
                continue
            for k in ("inner_dia", "outer_dia", "tip_deg", "contact_arc",
                      "seat_latitude", "segments", "facet_err", "bed_mm2"):
                self.assertAlmostEqual(j["measure"][k], p["measure"][k],
                                       places=6, msg=f"{c}: {k}")
            checked += 1
        # a parity test that compared nothing would pass
        self.assertGreater(checked, len(CASES) // 3,
                           "too few cases actually built to prove anything")

    def test_the_advertised_base_range_is_one_the_generator_accepts(self):
        """baseRange is what the page's dial stops at, so every value in it
        must build. maxBase alone is not enough -- the tip-angle gate binds
        first on a small ball -- and the range must be the open interval:
        a base sitting exactly on R sin(TIP_MAX) lands at 75.0000000001."""
        src = """
import { baseRange, chamferMax } from %s;
const out = [];
for (let ball = 8; ball <= 200; ball += 3.1)
  for (const wall of [1.2, 2.5, 6])
    for (const chW of [0, 0.8, 2])
      for (const seat of [0.4, 1, 4]) {
        // start from the bottom, the top and the middle of the base range
        // and settle each the way the page does. The emitted pair is the
        // SETTLED one: varying base after settling the chamfer leaves the
        // two inconsistent, which is a flaw in the question, not the page.
        const r0 = baseRange(ball, wall, 0);
        if (r0.hi <= r0.lo) continue;
        for (const start of [r0.lo, r0.hi, (r0.lo + r0.hi) / 2]) {
          let base = start, ch = chW, dead = false;
          for (let i = 0; i < 8; i++) {          // the page's fixed point
            ch = Math.min(ch, chamferMax(ball, base, wall, seat));
            const r = baseRange(ball, wall, ch);
            if (r.hi <= r.lo) { dead = true; break; }
            base = Math.min(Math.max(base, r.lo), r.hi);
          }
          if (!dead) out.push([ball, base, wall, ch, seat]);
        }
      }
console.log(JSON.stringify(out));
""" % json.dumps(os.path.abspath(JS))
        p = subprocess.run([node(), "--input-type=module", "-e", src],
                           capture_output=True, text=True, timeout=180)
        self.assertFalse(p.returncode, (p.stderr or "")[-500:])
        cases = json.loads(p.stdout)
        self.assertGreater(len(cases), 2000, "the sweep covered too little")
        bad = []
        for ball, base, wall, ch, seat in cases:
            try:
                G.build(ball, base, wall, ch, seat)
            except ValueError as e:
                bad.append((round(ball, 1), round(base, 3), wall,
                            round(ch, 3), seat, str(e)))
        self.assertEqual(bad[:4], [],
                         f"{len(bad)} of {len(cases)} settings the dial "
                         f"offers are refused by the generator")

    def test_the_sweep_exercises_every_refusal(self):
        seen = {p["refuse"].split(" ")[0] for p in self.py if p["refuse"]}
        for word in ("wall", "base", "chamfer", "tip"):
            self.assertIn(word, seen, f"nothing in the sweep trips {word}")


if __name__ == "__main__":
    unittest.main()
