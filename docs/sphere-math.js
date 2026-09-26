// The sphere stand's geometry, in the browser.
//
// This is a second implementation of tools/gen_sphere_stand.py, and a second
// implementation is a liability unless something proves the two agree. That
// something is tests/test_sphere_parity.py, which runs this file under node
// and the generator under python over the same sweep and fails on any
// disagreement past a tenth of a micron. The PRINTED file always comes from
// the generator; this exists so a dial can move at frame rate and so a limit
// can bite while you are dragging rather than after you order.
//
// Ported from ~/Code/3d_prints (the original Sphere Stand Generator), which
// computed all of this in the browser and is the reason that app felt better
// to use than a round trip ever can.
//
// No DOM, no Three.js, no imports: node has to be able to load it bare.

// Python formats an exact half to EVEN and JavaScript formats it away from
// zero, so f"{39.25:.1f}" is 39.2 where (39.25).toFixed(1) is 39.3. The two
// agreed on the number to nine places and disagreed on the sentence, which
// is worse than disagreeing loudly: the same setting refused in the browser
// and on order for what read as different reasons. The parity test caught it.
export function fixed(v, d) {
  // Decide from the EXACT decimal expansion, never from v*10^d. Two false
  // starts here, both caught by the parity test: Math.round(v*p) turns
  // 21.149999999999998 into 21.2 because the multiply lands on exactly
  // 211.5, and testing whether 2*v*p is an integer turns 0.05 into 0.0
  // because that multiply lands on exactly 1. toPrecision(20) shows what
  // the double really is -- 21.149999999999998579, 0.050000000000000003 --
  // and only a true tie gets Python's round-half-to-even.
  if (!isFinite(v)) return String(v);
  const neg = v < 0, a = Math.abs(v);
  const s = a.toPrecision(20);
  if (s.indexOf('e') >= 0) return v.toFixed(d);        // outside our range
  const dot = s.indexOf('.');
  const ip = dot < 0 ? s : s.slice(0, dot);
  const fp = (dot < 0 ? '' : s.slice(dot + 1)).padEnd(d + 1, '0');
  const rest = fp.slice(d);
  let n = BigInt(ip + fp.slice(0, d));
  const tie = rest[0] === '5' && !/[1-9]/.test(rest.slice(1));
  if (rest[0] > '5' || (rest[0] === '5' && !tie)) n += 1n;
  else if (tie && n % 2n === 1n) n += 1n;              // half -> even
  let out = n.toString().padStart(d + 1, '0');
  const res = d ? out.slice(0, out.length - d) + '.' + out.slice(-d) : out;
  return (neg && n !== 0n ? '-' : '') + res;
}

export const NOZZLE = 0.4;
export const TIP_MIN = 25.0;
export const TIP_MAX = 75.0;
export const BALL_MIN = 8.0;
export const BALL_MAX = 200.0;

// The original's Auto-Optimize: a 45 degree contact latitude.
export function auto(ball) {
  return { base: (ball / 2) * 0.707, wall: ball * 0.10,
           chamfer: ball * 0.03, seat: 1.0 };
}

// The inner lip must stay inside the ball's equator or the ball is caged.
export function maxBase(ball, wall) {
  return ball / 2 + wall / 2 - 0.1;
}

// The chamfer may not eat the wall, nor drop the rim through the bed.
// The bed half is a scan in 0.1 steps, exactly as the generator does it --
// a closed form would be tidier and would not be the same number.
export function maxChamfer(ball, base, wall, seat) {
  const R = ball / 2, rIn = base - wall / 2, rOut = base + wall / 2;
  const zOff = R + seat;
  const geo = (rOut - Math.max(0, rIn)) - 0.1;
  let bed = geo;
  // np.arange(0.1, geo + 0.1, 0.1): the count is what numpy computes, so
  // the two loops visit the same values even when geo lands near a step
  const n = Math.max(0, Math.ceil((geo + 0.1 - 0.1) / 0.1 - 1e-12));
  for (let i = 0; i < n; i++) {
    const c = 0.1 + i * 0.1;
    const rc = rOut - c;
    const y = zOff - Math.sqrt(Math.max(0, R * R - Math.min(R, rc) ** 2));
    if (y - c < 0) { bed = Math.max(0, c - 0.1); break; }
  }
  return Math.min(geo, bed);
}

// Closed (r, z) outline of the ring, ready to revolve.
export function profile(ball, base, wall, chamfer, seat, n = 96) {
  const R = ball / 2;
  let rIn = base - wall / 2;
  const rOut = base + wall / 2;
  rIn = Math.max(0.05, rIn);
  const zOff = R + seat;
  const rC = rOut - chamfer;
  const y = (r) => (r > rC)
    ? y(rC) - (r - rC)
    : zOff - Math.sqrt(Math.max(0, R * R - Math.min(R, r) ** 2));
  const pts = [[rIn, 0], [rOut, 0], [rOut, y(rOut)]];
  // linspace(rIn, rC, n) walked backwards
  for (let i = n - 1; i >= 0; i--) {
    const r = n === 1 ? rIn : rIn + (rC - rIn) * (i / (n - 1));
    pts.push([r, y(r)]);
  }
  pts.push(pts[0].slice());
  return { pts, R, rIn, rOut, rC, zOff };
}

export function tipAngle(ball, rOut, chamfer) {
  const R = ball / 2;
  const rc = Math.min(R * 0.9999, Math.max(0, rOut - chamfer));
  const h = Math.sqrt(Math.max(0, R * R - rc * rc));
  return { deg: Math.atan2(rc, h) * 180 / Math.PI, rc };
}

export function contactArc(ball, rIn, rc) {
  const R = ball / 2;
  return R * Math.max(0, Math.asin(Math.min(1, rc / R))
                       - Math.asin(Math.min(1, Math.max(0, rIn) / R)));
}

// The original's auto-density, clamped 32..256 and rounded to a multiple of 8.
export function segmentsFor(rOut) {
  const raw = Math.ceil(Math.ceil(Math.PI / Math.acos(1 - 0.025 / rOut)) / 8) * 8;
  return Math.min(256, Math.max(32, raw));
}

// What the CHAMFER dial may be. maxChamfer is where the gate sits; a dial
// that stops exactly there hands the generator a value it refuses, because
// the two languages agree on that limit to nine places and not to the last
// bit. Same inset as baseRange, same reason.
export function chamferMax(ball, base, wall, seat) {
  return Math.max(0, maxChamfer(ball, base, wall, seat) - 1e-6);
}

// What the BASE dial may actually be, once every gate is accounted for.
//
// maxBase alone is not the answer: it only keeps the lip inside the ball's
// equator. The tip-angle gate binds too, and at a small ball it binds first
// -- at O12 the equator allows 7.15 and the ring swallows the ball at
// anything over 5.35. A dial that stopped at 7.15 would hand you a setting
// the generator refuses, which is the whole thing this page is for.
//
// tip = atan2(rc, h), rc = base + wall/2 - chamfer, so the gate inverts:
//   TIP_MIN <= tip <= TIP_MAX  ->  R sin(TIP_MIN) <= rc <= R sin(TIP_MAX)
export function baseRange(ball, wall, chamfer) {
  const R = ball / 2;
  const off = wall / 2 - chamfer;
  // inset by a hair: the gate refuses tip > TIP_MAX, and a base sitting
  // exactly on R*sin(TIP_MAX) lands at 75.0000000001 as often as not, so an
  // un-inset ceiling clamps the dial onto a value the generator rejects.
  // The range is the buildable one, not its closure.
  const EPS = 1e-6;
  return {
    lo: R * Math.sin(TIP_MIN * Math.PI / 180) - off + EPS,
    hi: Math.min(maxBase(ball, wall),
                 R * Math.sin(TIP_MAX * Math.PI / 180) - off) - EPS,
  };
}

// Every refusal the generator makes, in the order it makes them, as text.
// Returning the same sentence the server would is the point: a limit that
// bites in the browser and a limit that bites on order must not disagree
// about why.
export function refuse(ball, base, wall, chamfer, seat) {
  if (!(ball >= BALL_MIN && ball <= BALL_MAX))
    return `ball must be ${BALL_MIN}-${BALL_MAX} mm`;
  if (wall < 3 * NOZZLE - 1e-9)
    return `wall ${fixed(wall, 2)} mm is under three nozzle widths `
         + `(${fixed(3 * NOZZLE, 1)}) — it prints as a hollow shell`;
  const mb = maxBase(ball, wall);
  if (base > mb)
    return `base ${fixed(base, 1)} mm past the ball's equator `
         + `(max ${fixed(mb, 1)}) — the ball would be trapped`;
  const mc = maxChamfer(ball, base, wall, seat);
  if (chamfer > mc)
    return `chamfer ${fixed(chamfer, 1)} mm over the limit `
         + `(${fixed(mc, 1)}) — it eats the wall or dips the rim below the bed`;
  const { rOut } = profile(ball, base, wall, chamfer, seat);
  const { deg } = tipAngle(ball, rOut, chamfer);
  if (deg < TIP_MIN)
    return `tip angle ${fixed(deg, 0)} deg (min ${fixed(TIP_MIN, 0)}) — the `
         + `ball rolls out; widen the base or cut the chamfer`;
  if (deg > TIP_MAX)
    return `tip angle ${fixed(deg, 0)} deg (max ${fixed(TIP_MAX, 0)}) — the `
         + `ring swallows the ball; narrow the base`;
  return null;
}

// What the card quotes, computed here rather than fetched.
export function measure(ball, base, wall, chamfer, seat, segments) {
  const { R, rIn, rOut, rC, zOff } = profile(ball, base, wall, chamfer, seat);
  const { deg, rc } = tipAngle(ball, rOut, chamfer);
  const seg = segments || segmentsFor(rOut);
  return {
    ball: r2(ball), base: r2(base), wall: r2(wall),
    chamfer: r2(chamfer), seat: r2(seat),
    inner_dia: r1(2 * rIn), outer_dia: r1(2 * rOut),
    tip_deg: r1(deg),
    contact_arc: r2(contactArc(ball, rIn, rc)),
    seat_latitude: r1(Math.asin(Math.min(1, rc / R)) * 180 / Math.PI),
    segments: seg,
    facet_err: r3(2 * Math.PI * rOut / seg / 4),
    bed_mm2: Math.round(Math.PI * (rOut * rOut - Math.max(0, rIn) ** 2)),
  };
}

// What the original called Stability: how far the ball must roll before
// its weight passes outside the contact circle, read as a verdict rather
// than a number. The bands are the generator's own gates.
export function stability(tipDeg) {
  if (tipDeg < TIP_MIN) return { text: 'rolls out', tone: 'no' };
  if (tipDeg > TIP_MAX) return { text: 'swallowed', tone: 'no' };
  if (tipDeg < 35) return { text: 'shallow', tone: 'warn' };
  if (tipDeg > 65) return { text: 'deep', tone: 'warn' };
  return { text: 'stable', tone: 'ok' };
}

// The share of the revolved wall that overhangs past 45 degrees. The
// profile is a surface of revolution, so this is a property of the
// (r, z) outline alone -- no mesh needed.
export function overhangPercent(ball, base, wall, chamfer, seat) {
  const { pts } = profile(ball, base, wall, chamfer, seat);
  let total = 0, over = 0;
  for (let i = 1; i < pts.length; i++) {
    const dr = pts[i][0] - pts[i - 1][0], dz = pts[i][1] - pts[i - 1][1];
    const len = Math.hypot(dr, dz);
    if (len < 1e-9) continue;
    total += len;
    // angle of the surface away from vertical; a wall leaning out past 45
    // is what a nozzle cannot bridge onto
    if (Math.abs(dz) < 1e-12 || Math.abs(dr / dz) > 1) over += len;
  }
  return total ? (over / total) * 100 : 0;
}

// Volume of the revolved ring, by Pappus on the closed outline: the
// signed area of the (r, z) polygon times the path its centroid travels.
export function volumeMm3(ball, base, wall, chamfer, seat) {
  const { pts } = profile(ball, base, wall, chamfer, seat);
  let a2 = 0, cr = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const [r0, z0] = pts[i], [r1_, z1] = pts[i + 1];
    const cross = r0 * z1 - r1_ * z0;
    a2 += cross;
    cr += (r0 + r1_) * cross;
  }
  const area = a2 / 2;
  if (Math.abs(area) < 1e-12) return 0;
  const rBar = cr / (3 * a2);
  return Math.abs(2 * Math.PI * rBar * area);
}

const r1 = (v) => Math.round(v * 10) / 10;
const r2 = (v) => Math.round(v * 100) / 100;
const r3 = (v) => Math.round(v * 1000) / 1000;
