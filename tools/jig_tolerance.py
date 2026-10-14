#!/usr/bin/env python3
"""Monte Carlo tolerance stack-up for the orbital jig, printed in PETG.

The generator grades every fit at its drawn size. A part comes off the
plate at a different one: holes close up, the big parts shrink, layers
quantize heights, and the bought parts have tolerances of their own.
Where one part locates another, those errors add up along the chain.
This samples all of them together, many times over, and asks of every
joint and every chain whether it still does its job.

What it samples, and where each number comes from:

  holes      a vertical hole prints `hole_loss(d)` small. Calibrated on
             this printer: PETG Basic took 0.45 mm off a drawn Ø1.45 bore
             (gen_gazebo.MATERIALS, read with the rod), and a Ø3 hole
             loses about 0.15-0.17. A part's holes run tight or loose
             together (PART_SIGMA): a crowded plate closed the same bore
             0.10-0.15 mm further than a strip did.
  pockets    a rectangular pocket closes RECT_LOSS, a little less than a
             round hole of its size would.
  shafts     a printed peg, key or sleeve comes out a hair over.
  shrink     every part shrinks in plan by a common amount (PETG, 0.2-0.6%)
             plus its own (DIFF_SIGMA): the ring and the base are printed
             apart, and what matters at the bearings and the Geneva is the
             difference.
  heights    printed heights scatter by Z_SIGMA, and a face that falls
             between layers lands on one of them.
  bought     each at its maker's tolerance, uniform over the band.
  assembly   the post where its play lets it sit, turned within it; the
             ring wherever three eccentrics set by hand put it; the ring
             out of round and rocked on its bearings by the arc's weight.

None of these distributions is a measurement of this printer except the
hole loss. They are stated so a fit print can replace them: change the
number, run it again.

    python3 tools/jig_tolerance.py [-n 100000] [--seed 1]
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_orbital_jig as J  # noqa: E402

# --- what printing does to a size ---------------------------------------
PART_SIGMA = 0.05       # mm on the diameter, shared by a part's holes
FEAT_SIGMA = 0.03       # mm, each hole on its own
RECT_LOSS, RECT_SIGMA = 0.10, 0.05
SHAFT_GAIN, SHAFT_SIGMA = 0.03, 0.03
SHRINK_MU, SHRINK_SIGMA = -0.0035, 0.0012   # common to the whole print
DIFF_SIGMA = 0.0007                          # each part's own, on top
Z_SIGMA = 0.05
LAYER = 0.2


def hole_loss(d):
    """What a vertical round hole of drawn diameter d loses, PETG Basic."""
    return 0.08 + 0.78 / np.asarray(d, float) ** 2


# --- the assembly, as hands do it ---------------------------------------
ECC_SET_SIGMA = 0.15    # mm: each eccentric's error when turned in by hand
RING_OOR_SIGMA = 0.10   # mm: the ring's two-lobe out-of-roundness off the plate


def U(rng, lo, hi, n):
    return rng.uniform(lo, hi, n)


def fit_rows(parts):
    """Every mating pair: the generator's fits, measured off the built
    parts, and the ones it does not list. Each row: what the hole is, how
    it prints, what goes in it and to what tolerance, and the band of
    diametral clearance (hole minus shaft) in which the joint works."""
    by = {f["name"]: f for f in J.fits(parts)}
    # kinds: vhole (round, vertical as printed), rect (a printed pocket),
    # steel (a steel bore round a printed shaft)
    # mate: (nominal, lo, hi) of what goes in -- bought, or printed ("p")
    # accept: (min, max) clearance on the diameter for the joint to work
    press = (-0.15, 0.0)
    pp_press = (-0.20, 0.02)          # printed into printed: both give
    slip = (0.0, 0.35)
    run = (0.05, 0.60)
    clear = (0.05, 9.0)
    # a press into PETG: tight in every print is the aim. PETG yields
    # past ~5% strain rather than cracking, so a tight press needs a vise,
    # not luck; the limit here is a press a bench vise still makes
    vise = (-0.40, 0.0)
    pp = (-0.40, 0.02)                # printed into printed: both yield
    spec = [
        # name in fits(),                            kind,   part,          mate,                      works if, note
        ("Geneva pin in the crank",                  "vhole", "driver",      (3.0, 0.002, 0.008),       vise,    "dowel, m6, pressed in a vise"),
        ("Geneva pin in a slot",                     "vhole", "rotor",       (3.0, 0.002, 0.008),       run,     "slot, as a hole"),
        ("Gearmotor's D-shaft in the crank, round",  "vhole", "driver",      (3.0, -0.012, 0.0),        (0.0, 0.6), "held by the set screw"),
        ("Gearmotor's D-shaft in the crank, flat",   "vhole", "driver",      (2.5, -0.05, 0.05),        (0.0, 0.6), "the set screw bears on it"),
        ("Gearmotor across its pocket",              "rect",  "drive_block", (12.0, -0.10, 0.10),       (0.0, 0.65), "the bushing locates it"),
        ("Gearmotor along its pocket",               "rect",  "drive_block", (10.0, -0.10, 0.10),       (0.0, 0.65), ""),
        ("Gearbox bushing in the block's floor",     "vhole", "drive_block", (4.0, -0.03, 0.03),        (0.0, 0.40), "locates the driver's axis"),
        ("Encoder across its pocket",                "rect",  "drive_block", (13.6, -0.15, 0.15),       (0.0, 0.75), "routed PCB"),
        ("Encoder along its pocket",                 "rect",  "drive_block", (13.0, -0.15, 0.15),       (0.0, 0.75), ""),
        ("Lid's key in the plug's channel",          "rect",  "drive_block", ("p", None),               pp,      "printed key"),
        ("Lid's peg in the access bore",             "vhole", "drive_block", ("p", None),               pp,      "printed peg"),
        ("Controller lid's peg in its boss",         "vhole", "ctrl_box",    ("p", None),               pp,      "printed peg"),
        ("Home magnet in the ring",                  "vhole", "rotor",       (3.0, -0.10, 0.10),        (0.0, 0.55), "glued; small discs run +-0.1"),
        ("Home sensor in its boss",                  "rect",  "stator",      (4.06, -0.10, 0.10),       (0.0, 0.65), "SS451A body"),
        ("Drive post in its socket",                 "rect",  "stator",      ("p", None),               run,     "printed post"),
        ("Foot bolt through the base",               "vhole", "stator",      (2.93, -0.05, 0.05),       clear,   "M3 major"),
        ("Bar bolt through the arc",                 "hhole", "arc",         (2.93, -0.05, 0.05),       (0.0, 9.0), "horizontal as printed"),
        ("Axle bolt through a sleeve",               "vhole", "sleeve_a",    (2.93, -0.05, 0.05),       clear,   "M3 major"),
        ("Sleeve in a 688's bore",                   "steel", "sleeve_a",    ("p", None),               (-0.08, 0.12), "688 bore 8 -0.008"),
        ("Carriage lips on the arc",                 "rect",  "saddle",      ("p", None),               run,     "the arc's 30 mm, printed on its side"),
        ("Receiver screws along the channel",        "vhole", "saddle",      (2.93, -0.05, 0.05),       run,     "M3 major"),
        ("1/4-20 through the receiver",              "vhole", "receiver",    (6.30, -0.10, 0.05),       clear,   "1/4-20 major"),
        ("Mount screw through the pedestal",         "vhole", "stator",      ("p", None),               clear,   "printed thread"),
        ("Arc's bar in the pad's slot",              "rect",  "rotor",       ("pz", None),              run,     "bar width is a printed height"),
    ]
    rows = []
    for name, kind, part, mate, acc, note in spec:
        f = by[name]
        if mate[1] is None:             # a printed mate: its drawn size from fits()
            mate = (mate[0], float(f["shaft"]))
        rows.append(dict(name=name, kind=kind, part=part, hole=float(f["hole"]),
                         mate=mate, accept=acc, intended=f["intended"], note=note))
    # what fits() does not measure
    t = J.TONGUE
    extra = [
        # heat-set inserts, against the hole the insert's maker asks for:
        # printed holes run a little small, and the maker's figure already
        # allows for that. One insert, M3, everywhere
        ("M3 insert bore against its maker's 4.0", "vhole", "stator", 2 * J.INS_M3[0], (4.0, 0, 0), (-0.35, 0.10), J.INSERT_M3),
        ("Hall leads down their slot", "rect", "stator", J.HALL_SLOT[0], (2.97, -0.05, 0.05), clear, "three leads at 1.27"),
        ("Motor cable down the post's bore", "vhole", "drive_block", 2 * (J.CABLE_R + 0.6), (2.6, -0.2, 0.2), clear, "six loose wires"),
    ]
    for name, kind, part, hole, mate, acc, note in extra:
        rows.append(dict(name=name, kind=kind, part=part, hole=float(hole),
                         mate=mate, accept=acc, intended="", note=note))
    return rows


def sample_fits(rows, rng, n, part_bias):
    out = {}
    for r in rows:
        d = r["hole"]
        if r["kind"] == "vhole":
            hole = d - hole_loss(d) + part_bias[r["part"]] + rng.normal(0, FEAT_SIGMA, n)
        elif r["kind"] == "hhole":
            # a horizontal hole loses as a round one, then sags at its crown
            hole = d - hole_loss(d) + part_bias[r["part"]] + rng.normal(0, FEAT_SIGMA, n) \
                - U(rng, 0.0, 0.2, n)
        elif r["kind"] == "rect":
            hole = d - RECT_LOSS + 0.5 * part_bias[r["part"]] + rng.normal(0, RECT_SIGMA, n)
        else:   # steel bore round a printed shaft
            hole = d - rng.uniform(0.0, 0.008, n)
        m = r["mate"]
        if m[0] == "p":         # a printed shaft, peg, key or post
            shaft = m[1] + SHAFT_GAIN + rng.normal(0, SHAFT_SIGMA, n)
        elif m[0] == "pz":      # a printed height
            shaft = m[1] + rng.normal(0, Z_SIGMA, n)
        else:
            shaft = m[0] + rng.uniform(m[1], m[2], n)
        if r["kind"] == "steel":
            hole, shaft = hole, shaft   # the steel bore is the hole
        c = hole - shaft
        lo, hi = r["accept"]
        out[r["name"]] = dict(c=c, tight=float(np.mean(c < lo)),
                              loose=float(np.mean(c > hi)))
    return out


# --- the Geneva's window: where the lip may be and the drive still work --
# Not assumed: the real lip and lock, moved and swept, the ring free to
# follow the pin as a real one is. Inward the lock's seat closes on the
# lock (a jam); outward nothing jams, the lock just holds less tightly, so
# the limit there is the stop's play.
STOP_PLAY_MAX = 1.0     # degrees at the ring
CACHE = os.path.join(os.path.dirname(HERE), "models", "meta", "orbital_jig_geneva_window.json")


def _fingerprint():
    keys = ("GENEVA_N", "GENEVA_C", "GENEVA_BIAS", "LIP_T", "PIN_R", "SLOT_CLR",
            "LOCK_R", "LOCK_CLR", "LOCK_RELIEF", "CRANK_T", "CRANK_R", "LIP_GAP")
    return {k: float(getattr(J, k)) for k in keys}


def _sweeper(parts):
    import trimesh.collision as tc
    o, _, _ = J._driver_frame()
    cm = tc.CollisionManager()
    cm.add_object("rotor", parts["rotor"])
    cm.add_object("driver", parts["driver"])
    cm.add_object("pin", J.pin_proxy())

    def touches(psi, th, Tsh):
        T = J.rot(psi - 180.0, [0, 0, 1], origin=[o[0], o[1], 0])
        cm.set_transform("driver", T)
        cm.set_transform("pin", T)
        cm.set_transform("rotor", Tsh @ J.rot(th, [0, 0, 1]))
        _, names = cm.in_collision_internal(return_names=True)
        return any("rotor" in p_ for p_ in names)   # the pin is pressed into the crank
    return touches


def _cell(touches, shift, psi_step=3.0, search=2.5, dth=0.05):
    Tsh = np.eye(4)
    Tsh[:2, 3] = shift
    tries = sorted(np.arange(-search, search + 1e-9, dth), key=abs)
    # the stop's play, at the stop
    free = [k for k in np.arange(-search, search + 1e-9, 0.02)
            if not touches(180.0, J.geneva_wheel(180.0) + k, Tsh)]
    if not free or max(free) - min(free) > STOP_PLAY_MAX:
        return False
    # every driver angle, the stops first: that is where a jam shows
    for psi in sorted(np.arange(180.0, 540.0 + 1e-9, psi_step),
                      key=lambda q: abs(((q - 180.0) % 360.0))):
        th0 = J.geneva_wheel(psi)
        if all(touches(psi, th0 + k, Tsh) for k in tries):
            return False
    return True


def window_grid(path=CACHE):
    """The window for the lip as drawn, as it prints, and as it prints
    tight: its seats and slots closed like holes, its lock grown a hair."""
    fp = _fingerprint()
    if os.path.exists(path):
        w = json.load(open(path))
        if w.get("fingerprint") == fp:
            return path
    seat = hole_loss(2 * (J.LOCK_R + J.LOCK_CLR)) / 2
    slot = hole_loss(2 * (J.PIN_R + J.SLOT_CLR)) / 2
    lock = SHAFT_GAIN / 2
    sig = np.hypot(PART_SIGMA, FEAT_SIGMA) / 2
    variants = {"drawn": (0, 0, 0), "printed": (seat + lock, slot, lock),
                "printed_tight": (seat + lock + 2 * sig, slot + 2 * sig, lock + sig)}
    base = J.assemble(J.SPECIMEN)
    _, u, t = J._driver_frame()
    R = np.round(np.arange(-1.6, 1.81, 0.1), 2)
    T = np.round(np.array([-1.0, -0.5, 0.0, 0.5, 1.0]), 2)
    out = {"R": R.tolist(), "T": T.tolist(), "fingerprint": fp}
    L0, S0, RL0 = J.LOCK_CLR, J.SLOT_CLR, J.LOCK_RELIEF
    try:
        for name, (dl, ds, dg) in variants.items():
            J.LOCK_RELIEF = RL0 - dg
            drv = J.driver()
            J.LOCK_RELIEF = RL0
            J.LOCK_CLR, J.SLOT_CLR = L0 - dl + dg, S0 - ds
            rot_ = J.rotor()
            J.LOCK_CLR, J.SLOT_CLR = L0, S0
            touches = _sweeper(dict(base, driver=drv, rotor=rot_))
            out[name] = [[_cell(touches, u[:2] * r + t[:2] * tt) for tt in T] for r in R]
    finally:
        J.LOCK_CLR, J.SLOT_CLR, J.LOCK_RELIEF = L0, S0, RL0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(out, open(path, "w"))
    return path


def load_window(path):
    w = json.load(open(path))
    R, T = np.array(w["R"]), np.array(w["T"])
    return R, T, {k: np.array(v, bool) for k, v in w.items() if k not in ("R", "T")}


def runs(win, dr, dt):
    """Does the Geneva run with the lip (dr, dt) off the driver? Nearest
    grid point, rounded toward the jam side: a point between a running
    and a jammed cell counts as jammed."""
    R, T, ok = win
    i0 = np.clip(np.searchsorted(R, dr) - 1, 0, len(R) - 1)
    i1 = np.clip(i0 + 1, 0, len(R) - 1)
    a = np.abs(dt)
    j1 = np.clip(np.searchsorted(T, a), 0, len(T) - 1)   # the next sideways cell out
    j1b = np.clip(np.searchsorted(T, -a, side="right") - 1, 0, len(T) - 1)
    return ok[i0, j1] & ok[i1, j1] & ok[i0, j1b] & ok[i1, j1b]


SCATTERS = ("PART_SIGMA", "FEAT_SIGMA", "RECT_SIGMA", "SHAFT_SIGMA", "DIFF_SIGMA",
            "SHRINK_SIGMA", "Z_SIGMA", "ECC_SET_SIGMA", "RING_OOR_SIGMA")


def simulate(n=100000, seed=1, window=None, scatter=1.0):
    """`scatter` multiplies every assumed spread at once: 1.0 is the
    estimate, 1.5 or 2.0 asks what fails first if the estimates are low."""
    if scatter != 1.0:
        g = globals()
        saved = {k: g[k] for k in SCATTERS}
        try:
            for k in SCATTERS:
                g[k] = saved[k] * scatter
            return simulate(n, seed, window, 1.0)
        finally:
            g.update(saved)
    rng = np.random.default_rng(seed)
    parts = J.assemble(J.SPECIMEN)
    rows = fit_rows(parts)
    names = sorted({r["part"] for r in rows} | {"stator", "rotor", "drive_block", "driver"})
    part_bias = {p: rng.normal(0, PART_SIGMA, n) for p in names}
    s_common = rng.normal(SHRINK_MU, SHRINK_SIGMA, n)
    s = {p: s_common + rng.normal(0, DIFF_SIGMA, n) for p in names}
    fits = sample_fits(rows, rng, n, part_bias)
    rep = {"n": n, "fits": {k: dict(tight=v["tight"], loose=v["loose"],
                                     p01=float(np.percentile(v["c"], 0.1)),
                                     p50=float(np.percentile(v["c"], 50)),
                                     p999=float(np.percentile(v["c"], 99.9)))
                            for k, v in fits.items()},
           "rows": [dict(name=r["name"], hole=r["hole"], mate=r["mate"],
                         accept=r["accept"], kind=r["kind"], note=r["note"])
                    for r in rows]}

    # --- chain 1: the bearings reach the race, and stand clear of it ---
    # the ring's race and outside, the base's towers, each with its own
    # shrink; the bearing steel; the sleeve's bore off its axis as printed;
    # the bearing's play on its printed sleeve, worst way
    race = J.RACE_R * (1 + s["rotor"]) + rng.normal(0, 0.03, n)
    od = J.RING_RO * (1 + s["rotor"]) + SHAFT_GAIN / 2
    tower = J.TOWER_PITCH * (1 + s["stator"]) + rng.normal(0, 0.03, n)
    brg = J.BRG_R - rng.uniform(0, 0.0045, n)
    ecc = J.ECC + rng.normal(0, 0.02, n)
    sleeve_play = np.clip(fits["Sleeve in a 688's bore"]["c"], 0, None) / 2
    oor = np.abs(rng.normal(0, RING_OOR_SIGMA, n))
    reach = (race + brg) - (tower - ecc) - sleeve_play - oor
    drop_in = (tower + ecc) - brg - od - sleeve_play - oor
    rep["bearings"] = dict(
        reach_p01=float(np.percentile(reach, 0.1)), reach_p50=float(np.median(reach)),
        fail_reach=float(np.mean(reach < 0.05)),
        drop_in_p01=float(np.percentile(drop_in, 0.1)),
        fail_drop_in=float(np.mean(drop_in < 0.0)))

    # --- chain 2: the lip where the driver expects it, in plan ----------
    o, u, t = J._driver_frame()
    arm = J.GENEVA_AT - (J.POST_R - J.GENEVA_BIAS)      # post centre to driver axis
    # the post in its socket: its play each way, and the turn it allows,
    # whose lever is the arm out to the driver
    play_x = np.clip(fits["Drive post in its socket"]["c"], 0, None)
    play_y = play_x + rng.normal(0, 0.03, n)             # the long side, same fit
    half_long = J.POST_Y / 2
    theta = rng.uniform(-1, 1, n) * (np.clip(play_y, 0, None) / 2) / half_long
    post_u = rng.uniform(-1, 1, n) * play_x / 2
    post_t = rng.uniform(-1, 1, n) * np.clip(play_y, 0, None) / 2
    bush = np.clip(fits["Gearbox bushing in the block's floor"]["c"], 0, None) / 2
    # the set screw pushes the shaft across its clearance bore, flat side
    # first: the crank sits that much off the shaft, sideways (+t)
    setscrew_t = np.clip(fits["Gearmotor's D-shaft in the crank, round"]["c"], 0, None) / 2
    ang = rng.uniform(0, 2 * np.pi, n)
    bush_u, bush_t = bush * np.cos(ang), bush * np.sin(ang)
    sock_u = rng.normal(0, 0.03, n)          # where the stator put the socket
    sock_t = rng.normal(0, 0.03, n)
    # the ring's centre: three eccentrics set by hand, and the wobble an
    # out-of-round ring makes on three bearings as it turns (worst way)
    e = rng.normal(0, ECC_SET_SIGMA, (3, n))
    phis = np.radians(np.array(J.TOWER_PHI))
    cx = -(2 / 3) * (e * np.cos(phis)[:, None]).sum(0)
    cy = -(2 / 3) * (e * np.sin(phis)[:, None]).sum(0)
    c_u, c_t = cx * u[0] + cy * u[1], cx * t[0] + cy * t[1]
    # the structural review's terms: the motor tilting in its slip pocket
    # about the bushing (+-0.1 at the lock, 15 mm below), play in the
    # gearbox's output, and the base flexing under the post and towers
    tilt_u, tilt_t = U(rng, -0.12, 0.12, n), U(rng, -0.12, 0.12, n)
    play_u, play_t = U(rng, -0.05, 0.05, n), U(rng, -0.05, 0.05, n)
    flex_u = rng.normal(0, 0.05, n)
    driver_u = (J.POST_R - J.GENEVA_BIAS) * s["stator"] + arm * s["drive_block"] \
        + sock_u + post_u + bush_u + tilt_u + play_u + flex_u
    driver_t = sock_t + post_t + arm * theta + bush_t + setscrew_t + tilt_t + play_t
    lip_u = J.GENEVA_C * s["rotor"] + c_u
    dr = lip_u - driver_u
    dt = c_t - driver_t
    rep["geneva_offsets"] = dict(
        dr_p01=float(np.percentile(dr, 0.1)), dr_p999=float(np.percentile(dr, 99.9)),
        dt_p999=float(np.percentile(np.abs(dt), 99.9)),
        oor_p999=float(np.percentile(oor, 99.9)))
    if window is None:
        window = window_grid()
    if window:
        win = load_window(window)
        R, T, ok = win
        res = {"window": {k: [float(min((r for r, row in zip(R, ok[k]) if all(row)), default=np.nan)),
                              float(max((r for r, row in zip(R, ok[k]) if all(row)), default=np.nan))]
                          for k in ("drawn", "printed", "printed_tight")}}
        # the printed lip's seats and slots close like holes; which window
        # applies follows the sampled hole loss of the rotor
        z = part_bias["rotor"] / PART_SIGMA
        pick = np.where(z < -1.0, "printed_tight", "printed")
        for wname in ("drawn", "printed", "printed_tight"):
            ww = (R, T, ok[wname])
            # an out-of-round ring swings the lip by `oor` as it turns: the
            # worst of that, toward the jam side
            res[wname] = float(np.mean(~runs(ww, dr - oor, dt) | ~runs(ww, dr + oor, dt)
                                       | ~runs(ww, dr, np.abs(dt) + oor)))
        good = np.zeros(n, bool)
        for wname in ("printed", "printed_tight"):
            m = pick == wname
            ww = (R, T, ok[wname])
            good[m] = (runs(ww, dr[m] - oor[m], dt[m]) & runs(ww, dr[m] + oor[m], dt[m])
                       & runs(ww, dr[m], np.abs(dt[m]) + oor[m]))
        res["as_printed"] = float(np.mean(~good))
        rep["geneva_jams"] = res

    # --- chain 3: heights at the drive -----------------------------------
    # crank to lip: the ring stands on its bearings, the bearings on the
    # towers; the crank hangs on the motor's shaft from the block's floor,
    # the block on its post in the base's socket
    Z = J.driver_levels(J.SPECIMEN)
    zq = lambda: rng.normal(0, Z_SIGMA, n)
    tower_top = zq()
    seat = U(rng, -0.10, 0.0, n)               # the race's flank on the bearing's chamfer
    ring_feat = zq() + U(rng, -0.1, 0.1, n)     # race to lip top, printed upright
    if hasattr(J, "RACE_PLAY"):
        # V wheels: no axial play; the ring tips only by pushing a wheel out
        # of its V against the tower's radial stiffness (~37 N/mm, the
        # structural review) under the ~2.4 N uplift: about 0.07, with scatter
        play = J.RACE_PLAY + np.abs(rng.normal(0.065, 0.02, n))
    else:
        play = (J.RACE_W - (J.BRG_W - rng.uniform(0, 0.12, n))) + zq()
    lift = np.clip(play, 0, None) * (J.GENEVA_AT + J.TOWER_PITCH / 2) \
        / (J.TOWER_PITCH * 1.5)                 # rocked by the arc's weight, at the drive
    # the base's corners flex under the bearing loads and lift the lip a
    # little more than the rocking alone (structural review: ~0.2)
    tower_flex = U(rng, 0.1, 0.2, n)
    lip_top = tower_top + seat + ring_feat + lift + tower_flex
    sock = zq()                                 # the socket's floor
    post_to_floor = zq() + 0.001 * rng.normal(0, 1, n) * (Z["floor_lo"] - Z["base_top"])
    floor_lo = sock + post_to_floor
    # the shim, pinched between crank and floor while the driver is
    # pressed on, is the gap; three layers, a first one among them
    shim = rng.normal(0, 0.03, n) + U(rng, -0.05, 0.0, n)
    crank_t = zq()
    crank_hi = floor_lo - shim
    crank_lo = crank_hi - crank_t
    g_lip = J.LIP_GAP + crank_lo - lip_top
    g_floor = J.FLOOR_GAP + shim
    # the shaft's tip must never reach the bottom of its bore
    shaft = U(rng, -0.25, 0.25, n)
    bore_sag = U(rng, 0.0, 0.15, n)
    bottom = (Z["crank_hi"] - (Z["shaft_tip"] - 0.8)) - bore_sag \
        - (Z["crank_hi"] - Z["shaft_tip"] + shaft) - shim
    rep["heights"] = dict(
        crank_to_lip_p01=float(np.percentile(g_lip, 0.1)),
        crank_to_lip_p50=float(np.median(g_lip)),
        fail_lip=float(np.mean(g_lip < 0.1)),
        # the lock's root fillet hangs that much lower, beside the lock only
        fillet_to_lip_p01=float(np.percentile(g_lip - getattr(J, "LOCK_FILLET", 0.0), 0.1)),
        fail_fillet=float(np.mean(g_lip - getattr(J, "LOCK_FILLET", 0.0) < 0.1)),
        crank_to_floor_p01=float(np.percentile(g_floor, 0.1)),
        crank_to_floor_p50=float(np.median(g_floor)),
        fail_floor=float(np.mean(g_floor < 0.1)),
        rock_at_drive_p50=float(np.median(lift)),
        shaft_to_bore_bottom_p01=float(np.percentile(bottom, 0.1)),
        fail_bottoms=float(np.mean(bottom < 0.05)))
    return rep


def table(rep):
    lines = ["%-42s %7s %-22s %-9s %7s %7s %7s %6s %6s" % (
        "joint", "drawn", "mate", "works if", "p0.1", "median", "p99.9", "tight", "loose")]
    for r in rep["rows"]:
        f = rep["fits"][r["name"]]
        m = r["mate"]
        mate = ("printed %.2f" % m[1]) if m[0] in ("p", "pz") else \
            "%.3f %+.3f/%+.3f" % (m[0], m[2], m[1])
        lo, hi = r["accept"]
        lines.append("%-42s %7.3f %-22s %4.2f..%-4.2f %7.3f %7.3f %7.3f %5.1f%% %5.1f%%" % (
            r["name"][:42], r["hole"], mate[:22], lo, min(hi, 9.99), f["p01"], f["p50"],
            f["p999"], 100 * f["tight"], 100 * f["loose"]))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=100000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--window", help="the Geneva window grid (json)")
    ap.add_argument("--scatter", type=float, default=1.0,
                    help="multiply every assumed spread (1.5, 2: pessimistic)")
    a = ap.parse_args()
    rep = simulate(a.n, a.seed, a.window, a.scatter)
    print(table(rep))
    for k in ("bearings", "geneva_offsets", "geneva_jams", "heights"):
        if k in rep:
            print(k, json.dumps({kk: (round(v, 4) if isinstance(v, float) else v)
                                 for kk, v in rep[k].items()}))


if __name__ == "__main__":
    main()
