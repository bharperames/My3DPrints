"""Replay the page's own step definitions against the real meshes and look
for interference at every sample. This checks the ANIMATION, not merely
that some path exists: it uses the same from/to offsets, the same screw
rule, and the same rest poses the page computes."""
import os, sys, json, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, trimesh, trimesh.collision as tc
import gen_bolted as B

t = B.thread_for(12.0); a = float(np.ceil(B.min_spacing(t)))
P = B.assemble(t, a, entry="free")
D = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models', 'knot_bolted_assembly.json')))
STEPS = D["steps"]
AX = [(np.asarray(x["dir"], float), np.asarray(x["origin"], float)) for x in D["axes"]]
HOME = {n: np.asarray(m.centroid, float) for n, m in P.items()}
PARTS = sorted(P)

def parts_of(st):  return st.get("parts", [])
def shown_of(st):  return parts_of(st) + st.get("show", [])

def line_of(part):
    for st in STEPS:
        if st.get("screw") and part in parts_of(st):
            return st.get("line")
    return None

ENGAGE = {}
for _st in STEPS:
    if _st.get("screw") and _st.get("line") is not None:
        for _p in parts_of(_st):
            ENGAGE[_p] = max(ENGAGE.get(_p, 0.0), float(_st.get("engage", 1e9)))

def pose(part, off):
    """Same rule the page uses: translate by `off`, then rotate about the
    part's own threaded line by 2*pi*(off along that line)/lead -- with the
    offset clamped to the engagement, because past that the part is off the
    end of the thread and is being carried, not turned. Engagement is a
    whole number of leads, so the clamped angle is zero and the rule stays
    continuous where the thread bites."""
    M = np.eye(4); M[:3, 3] = off
    li = line_of(part)
    if li is None:
        return M
    d, o = AX[li]
    e = ENGAGE[part]
    ax = float(np.clip(np.dot(off, d), -e, e))
    ang = 2 * np.pi * ax / D["lead"]
    R = trimesh.transformations.rotation_matrix(ang, d, o)
    return R @ M

def offsets(i, u):
    """Every part's offset at fraction u through step i."""
    off = {n: None for n in PARTS}
    for s in range(0, i + 1):
        st = STEPS[s]
        for p in parts_of(st):
            f = np.asarray(st["from"], float); tt = np.asarray(st["to"], float)
            off[p] = f + (tt - f) * u if s == i else tt
    seen = set()
    for s in range(0, i + 1): seen |= set(shown_of(STEPS[s]))
    for s in range(i + 1, len(STEPS)):
        for p in parts_of(STEPS[s]):
            if p not in seen and off[p] is None:
                off[p] = np.asarray(STEPS[s]["from"], float)
    return {k: (v if v is not None else np.zeros(3)) for k, v in off.items()}

def visible(i):
    v = set()
    for s in range(0, i + 1): v |= set(shown_of(STEPS[s]))
    return v

PARK_OFF = "--nopark" in sys.argv
if PARK_OFF:
    # negative control: bring the red bar home before the green bar sweeps,
    # which the geometry says jams at 3 mm
    for st in STEPS:
        if st.get("line") == 0 and any(x != 0 for x in st["to"]):
            st["to"] = [0.0, 0.0, 0.0]
        if st.get("line") == 0 and any(x != 0 for x in st["from"]) and st["from"][0] < 5:
            st["from"] = [0.0, 0.0, 0.0]
N = 160
print(f"Replaying {len(STEPS)} steps at {N} samples each, all 15 part pairs.\n")
worst_overall = 0.0
for i, st in enumerate(STEPS):
    vis = visible(i)
    if len(vis) < 2:
        print(f"  step {i+1}: only one part on the bench"); continue
    cm = tc.CollisionManager()
    for n in vis: cm.add_object(n, P[n])
    worst = 0.0; worst_at = None; hits = 0
    for k in range(N + 1):
        u = k / N
        off = offsets(i, u)
        for n in vis: cm.set_transform(n, pose(n, off[n]))
        hit, names = cm.in_collision_internal(return_names=True)
        if hit:
            hits += 1
            for x, y in names:
                gx = P[x].copy(); gx.apply_transform(pose(x, off[x]))
                gy = P[y].copy(); gy.apply_transform(pose(y, off[y]))
                v = float(trimesh.boolean.intersection([gx, gy],
                                                       engine="manifold").volume)
                if v > worst: worst, worst_at = v, (u, x, y)
    worst_overall = max(worst_overall, worst)
    tag = "clean" if worst < 0.01 else f"INTERFERES {worst:.3f} mm3"
    extra = "" if worst_at is None else f" at u={worst_at[0]:.2f} {worst_at[1]}|{worst_at[2]}"
    print(f"  step {i+1} {st['title'][:38]:40s} contacts:{hits:4d}/{N+1}  {tag}{extra}")
print(f"\n  WORST INTERFERENCE ANYWHERE IN THE ANIMATION: {worst_overall:.4f} mm3")
