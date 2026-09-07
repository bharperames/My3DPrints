#!/usr/bin/env python3
"""The Montessori thread as a parametric family, at any scale.

Not a copy of the toy's mesh and not compatible with it — the shape only.
An axial section of the designer's bolt was sampled every 0.5 mm and it is
a pure cosine, to three decimals:

    r(z) = R_mean + A cos(2 pi z / lead)

with ratios that come out exact on the 35 mm original, so they are almost
certainly what was drawn rather than what was measured:

    R_minor = 2/3 R_major     lead = 2/3 R_major     A = R_major / 6

Those three carry one consequence worth the whole file. The steepest flank
is dr/dz = 2 pi A / lead = pi / 2, which has no R in it: the flank sits
32.5 degrees off the axis at every scale. So a bore of this family printed
upright never presents more than a 32.5 degree overhang, and shrinking the
toy cannot walk it into a droop. That is the property being kept; the
diameter is not.

Clearance does not scale with it. The original runs 0.50 mm radial on a
35 mm thread; a proportional 0.23 mm at 16 mm is inside the slop of an
0.4 nozzle, so clearance is an absolute number here and stays where a
printer can hold it.

The solid needs no boolean. In cylindrical coordinates the surface is
r = R_mean + A cos(2 pi z / lead - theta), single valued over (theta, z) —
a height field, so it meshes as a wrapped grid that cannot self intersect
and is watertight by construction. The same function with R_mean pushed
out by the clearance is the cutter that makes the matching bore, which is
what the designer's nut is: the same cosine, 0.50 mm larger.
"""
import numpy as np
import trimesh
from shapely.geometry import Polygon

CLEARANCE = 0.30       # mm radial, absolute — an 0.4 nozzle's business
NT = 180               # samples around
NZ_PER_LEAD = 24       # samples along, per lead
HEX_AF = 2.844         # head across flats, in units of R_major (from source)
HEAD_H = 1.617         # head height, likewise
NUT_H = 1.717


class Thread:
    """One thread of the family, named by its major radius."""

    def __init__(self, major_r=8.0, clearance=CLEARANCE, hex_af=None,
                 head_h=None, head_cham=None):
        """`hex_af` and `head_h` in mm override the family's proportions.

        The toy's head is 2.844 R across flats so a toddler can grip it. A
        head that is never gripped -- sunk in a pocket, turned by the block
        around it -- only has to key and to bear, and can be sized to that.
        """
        self.major_r = float(major_r)
        self._hex_af = None if hex_af is None else float(hex_af)
        self._head_h = None if head_h is None else float(head_h)
        self._head_cham = None if head_cham is None else float(head_cham)
        self.minor_r = 2.0 / 3.0 * self.major_r
        self.lead = 2.0 / 3.0 * self.major_r
        self.mean = (self.major_r + self.minor_r) / 2.0
        self.amp = self.major_r / 6.0
        self.clearance = float(clearance)

    def __repr__(self):
        return (f"Thread(major_d={2*self.major_r:.2f} minor_d="
                f"{2*self.minor_r:.2f} lead={self.lead:.2f} "
                f"clr={self.clearance:.2f})")

    def rod(self, length, z0=0.0, offset=0.0, phase=0.0, nt=NT, runout=()):
        """The screw surface as a wrapped grid. No booleans, no repair.

        `runout` is a list of (z, span): approaching that height the thread
        fades out, the mean radius opening to the major radius and the
        amplitude falling to nothing, so the bore arrives at the face as a
        plain cylinder. It is how a thread is supposed to end, and here it
        is also the only way to end one. A cone chamfer cannot do the job:
        this flank sweeps every slope from 0 to 57.5 degrees, so a cone of
        any angle below that is tangent to the thread somewhere along the
        crossing, and a tangent crossing is what a boolean turns into
        non-manifold slivers. Fading the profile keeps the whole surface a
        single-valued height field, which has no crossing to sliver.
        """
        nz = max(8, int(round(length / self.lead * NZ_PER_LEAD)))
        th = np.arange(nt) * (2 * np.pi / nt)
        z = z0 + np.linspace(0.0, length, nz + 1)
        fade = np.zeros_like(z)
        for zf, span in runout:
            fade = np.maximum(fade, np.clip(1.0 - np.abs(z - zf) / span,
                                            0.0, 1.0))
        mean = self.mean + fade * (self.major_r - self.mean)
        amp = (1.0 - fade) * self.amp
        r = (mean[None, :] + offset
             + amp[None, :] * np.cos(2 * np.pi * z[None, :] / self.lead
                                     - th[:, None] + phase))
        V = np.empty(((nt * (nz + 1)) + 2, 3))
        V[:-2, 0] = (r * np.cos(th)[:, None]).ravel()
        V[:-2, 1] = (r * np.sin(th)[:, None]).ravel()
        V[:-2, 2] = np.tile(z, nt)
        lo, hi = nt * (nz + 1), nt * (nz + 1) + 1
        V[lo] = [0, 0, z[0]]
        V[hi] = [0, 0, z[-1]]

        def vid(i, j):
            return (i % nt) * (nz + 1) + j

        F = []
        for i in range(nt):
            for j in range(nz):
                a, b = vid(i, j), vid(i + 1, j)
                c, d = vid(i + 1, j + 1), vid(i, j + 1)
                F += [[a, b, c], [a, c, d]]
            F.append([lo, vid(i + 1, 0), vid(i, 0)])
            F.append([hi, vid(i, nz), vid(i + 1, nz)])
        m = trimesh.Trimesh(V, np.array(F), process=False)
        if not m.is_watertight:
            raise ValueError("thread grid did not close — check nt/nz")
        if m.volume < 0:
            m.invert()
        return m

    def cutter(self, length, z0=0.0, phase=0.0, runout=()):
        """What to subtract from a block to leave a bore this bolt turns in.

        The designer's nut is exactly this: the same cosine, pushed out by
        the running clearance. Cutting with the bolt's own profile instead
        would give a zero-clearance fit that no printer delivers.
        """
        return self.rod(length, z0=z0, offset=self.clearance, phase=phase,
                        runout=runout)

    def mouth_chamfer(self, z_face, opens_up, size=1.0, sections=96):
        """A 45 degree ease on the lip where a bore breaks a face.

        Safe only because it is used with a run-out. Inside the run-out the
        bore is a plain cylinder of the major radius, so this cone crosses
        a cylinder in one clean circle. Cut the same cone against live
        thread and it crosses the flank tangentially and slivers.
        """
        inner = self.major_r + self.clearance - 0.3
        outer = self.major_r + self.clearance + size
        rise = outer - inner
        prof = np.array([[inner - 1.0, 0.0], [outer, 0.0], [inner, rise],
                         [inner - 1.0, rise], [inner - 1.0, 0.0]])
        if opens_up:
            # mirroring alone reverses the profile's orientation and revolves
            # into a solid of negative volume, which the boolean refuses
            prof[:, 1] = -prof[:, 1]
            prof = prof[::-1]
        c = trimesh.creation.revolve(prof, sections=sections)
        c.apply_translation([0, 0, z_face])
        return c

    @property
    def chamfer(self):
        return 0.5 * self.amp * 2.0        # ~ one thread depth of flare

    @property
    def hex_af(self):
        return HEX_AF * self.major_r if self._hex_af is None else self._hex_af

    @property
    def hex_cr(self):
        return self.hex_af / 2.0 / np.cos(np.radians(30.0))

    @property
    def head_h(self):
        return HEAD_H * self.major_r if self._head_h is None else self._head_h

    def hexagon(self, cr=None, rot=0.0):
        cr = self.hex_cr if cr is None else cr
        a = np.radians(np.arange(6) * 60.0) + rot
        return Polygon(np.column_stack([cr * np.cos(a), cr * np.sin(a)]))

    def head(self, z0=0.0, height=None, cham=None):
        """A hex head chamfered top and bottom, as the originals are."""
        h = self.head_h if height is None else height
        if cham is None:
            cham = (0.18 * self.major_r if self._head_cham is None
                    else self._head_cham)
        body = trimesh.creation.extrude_polygon(self.hexagon(), h)
        # keep the profile off the axis: a revolve through r=0 leaves
        # degenerate polar triangles that survive the boolean
        face_r = self.hex_cr - cham
        prof = np.array([(0.5, 0.0), (face_r, 0.0),
                         (self.hex_cr + 1.0, cham),
                         (self.hex_cr + 1.0, h - cham),
                         (face_r, h), (0.5, h), (0.5, 0.0)])
        barrel = trimesh.creation.revolve(prof, sections=192)
        head = body.intersection(barrel, engine="manifold")
        head.apply_translation([0, 0, z0])
        return head

    def bolt(self, shank_len, head_h=None):
        """Head at z=0, shank running up, tip eased so it starts by hand."""
        h = self.head_h if head_h is None else head_h
        rod = self.rod(shank_len + 0.01, z0=h)
        tip = h + shank_len
        # a 45 degree taper over the last thread depth: without it the final
        # crest is a full-height sliver the fingers have to find blind
        ease = self.amp * 2.0
        prof = np.array([(0.5, h - 1.0), (self.major_r + 1.0, h - 1.0),
                         (self.major_r + 1.0, tip - ease),
                         (self.minor_r - 0.5, tip),
                         (0.5, tip), (0.5, h - 1.0)])
        rod = rod.intersection(trimesh.creation.revolve(prof, sections=192),
                               engine="manifold")
        # head(height=h), not head(): the override applies to the rod's
        # start too, so building the head at the family's default height
        # leaves it floating short of its own shank — one bolt, two bodies.
        return trimesh.boolean.union([rod, self.head(height=h)],
                                     engine="manifold")

    def nut(self, height=None):
        h = NUT_H * self.major_r if height is None else height
        body = self.head(height=h)
        cuts = [self.cutter(h + 2 * self.lead, z0=-self.lead,
                            runout=[(0.0, self.lead), (h, self.lead)]),
                self.mouth_chamfer(h, True),
                self.mouth_chamfer(0.0, False)]
        return body.difference(trimesh.boolean.union(cuts, engine="manifold"),
                               engine="manifold")

    def shank_only(self, mesh):
        """The part of a generated bolt above its head, zeroed, for testing."""
        s = mesh.slice_plane([0, 0, self.head_h + 0.2], [0, 0, 1], cap=True)
        s.apply_translation([0, 0, -s.bounds[0][2]])
        return s


if __name__ == "__main__":
    import json
    import sys
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    from gen_montessori import screw_test

    t = Thread(major_r=8.0)
    bolt = t.bolt(shank_len=45.0)
    nut = t.nut()
    shank = t.shank_only(bolt)
    rep = {"thread": repr(t), "flank_deg_off_axis":
           round(float(np.degrees(np.arctan(1.0 / (np.pi / 2)))), 2),
           "hex_af": round(t.hex_af, 2), "head_h": round(t.head_h, 2),
           "nut_h": round(NUT_H * t.major_r, 2),
           "bolt_watertight": bool(bolt.is_watertight),
           "nut_watertight": bool(nut.is_watertight)}
    depths = list(np.linspace(1.0, NUT_H * t.major_r - 3.0, 5))
    lead, windows = screw_test(nut, shank, [float(d) for d in depths])
    rep["screw_lead_mm"] = None if lead is None else round(float(lead), 3)
    rep["want_lead_mm"] = round(t.lead, 3)
    rep["free_window_deg"] = None if lead is None else [w[2] for w in windows]
    ok = (lead is not None and abs(lead - t.lead) < 0.05 * t.lead
          and bolt.is_watertight and nut.is_watertight)
    print(json.dumps({"ok": bool(ok), **rep}, indent=2))
    sys.exit(0 if ok else 1)
