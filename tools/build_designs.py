#!/usr/bin/env python3
"""Design two new parts: captive held-sphere and a 5-link print-in-place chain."""
import numpy as np
import trimesh
import os

M = os.path.expanduser("~/Code/My3DPrints/models")

# ---------- 1. Held sphere: openwork shell with captive ball ----------
R_OUT, R_IN = 25.0, 21.5          # shell outer/inner radius (3.5 mm wall)
WIN_R = 8.0                       # window radius -> opening Ø16
BALL_R = 9.5                      # ball Ø19 > opening Ø16 -> captive
BALL_Z = -10.0                    # ball center; bottom at -19.5
PIP_R, FLAT_Z = 1.2, -24.0        # breakaway pip Ø2.4; bed flat cut

shell = trimesh.creation.icosphere(subdivisions=4, radius=R_OUT)
shell = shell.difference(trimesh.creation.icosphere(subdivisions=4, radius=R_IN))

# windows along icosahedron vertex directions (12), skipping the bottom-most
ico = trimesh.creation.icosahedron()
dirs = ico.vertices / np.linalg.norm(ico.vertices, axis=1, keepdims=True)
cutters = []
for d in dirs:
    if d[2] < -0.8:               # keep bottom solid-ish for the bed flat
        continue
    cyl = trimesh.creation.cylinder(radius=WIN_R, height=2 * R_OUT + 10, sections=48)
    T = trimesh.geometry.align_vectors([0, 0, 1], d)
    cyl.apply_transform(T)
    cyl.apply_translation(d * R_OUT)     # centered through the shell wall
    cutters.append(cyl)
shell = shell.difference(trimesh.util.concatenate(cutters))

# flat bottom for bed contact
box = trimesh.creation.box((2 * R_OUT + 4,) * 3)
box.apply_translation([0, 0, FLAT_Z - (R_OUT + 2)])
shell = shell.difference(box)

ball = trimesh.creation.icosphere(subdivisions=4, radius=BALL_R)
ball.apply_translation([0, 0, BALL_Z])
# breakaway pip from shell inner bottom up to ball bottom
pip_bot, pip_top = -R_IN, BALL_Z - BALL_R + 0.4   # embed 0.4 into ball
pip = trimesh.creation.cylinder(radius=PIP_R, height=(pip_top - pip_bot), sections=24)
pip.apply_translation([0, 0, (pip_top + pip_bot) / 2])
held = ball.union(pip)

sc = trimesh.Scene()
zoff = -FLAT_Z                     # floor at z=0
shell.apply_translation([0, 0, zoff])
held.apply_translation([0, 0, zoff])
sc.add_geometry(shell, geom_name="cage")
sc.add_geometry(held, geom_name="ball")
out1 = os.path.join(M, "held-sphere.3mf")
sc.export(out1)

chk = trimesh.load(out1, force="scene")
geoms = list(chk.geometry.values())
print("held-sphere:", [(len(g.faces), g.is_watertight, round(g.volume/1000, 1)) for g in geoms],
      "extents", np.round(chk.bounds[1] - chk.bounds[0], 1))
# captive proof: ball Ø vs window opening
print(f"  captive: ball Ø{2*BALL_R} vs window Ø{2*WIN_R} -> {'CAPTIVE' if 2*BALL_R > 2*WIN_R else 'ESCAPES'}")
# clearance ball<->shell (excluding pip)
from trimesh.proximity import signed_distance
samp = ball.sample(600) if hasattr(ball, 'sample') else ball.vertices[:600]
d = -signed_distance(shell, samp + [0, 0, 0])
print(f"  min ball->cage distance: {d.min():.2f} mm")

# ---------- 2. Chain: five stadium links, alternating flat/vertical ----------
D = 3.175                          # 0.125" cross-section
L_OUT = 19.05                      # 0.75" outer length
CL_L = L_OUT - D                   # centerline length of stadium
CL_W = 8.0                         # centerline width -> opening 4.8mm wide

def stadium_path(n_per=24):
    """Closed centerline: two straights + two semicircle ends, in XY."""
    s, r = (CL_L - CL_W) / 2, CL_W / 2
    pts = []
    for t in np.linspace(-np.pi/2, np.pi/2, n_per):        # right cap
        pts.append([s + r*np.cos(t), r*np.sin(t)])
    for t in np.linspace(np.pi/2, 3*np.pi/2, n_per):       # left cap
        pts.append([-s + r*np.cos(t), r*np.sin(t)])
    return np.array(pts)

def tube_from_loop(loop2d, tube_r, n_sec=20):
    """Watertight tube swept along closed planar loop (torus topology)."""
    P = np.column_stack([loop2d, np.zeros(len(loop2d))])
    n = len(P)
    T = np.roll(P, -1, axis=0) - np.roll(P, 1, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    up = np.array([0, 0, 1.0])
    N = np.cross(up, T); N /= np.linalg.norm(N, axis=1, keepdims=True)
    B = np.cross(T, N)
    ang = np.linspace(0, 2*np.pi, n_sec, endpoint=False)
    ring = np.stack([np.cos(ang), np.sin(ang)], axis=1) * tube_r
    V = (P[:, None, :] + ring[None, :, 0:1] * N[:, None, :]
         + ring[None, :, 1:2] * B[:, None, :]).reshape(-1, 3)
    F = []
    for i in range(n):
        for j in range(n_sec):
            a = i*n_sec + j
            b = i*n_sec + (j+1) % n_sec
            c = ((i+1) % n)*n_sec + j
            dd = ((i+1) % n)*n_sec + (j+1) % n_sec
            F += [[a, b, c], [b, dd, c]]
    m = trimesh.Trimesh(vertices=V, faces=F)
    m.fix_normals()
    return m

link = tube_from_loop(stadium_path(), D/2)
print("chain link:", len(link.faces), "tris, wt", link.is_watertight,
      "ext", np.round(link.extents, 2))

PITCH = 13.6                       # center spacing along chain
COIL_R = 60.0                      # gentle arc "coil" on the plate
chain = trimesh.Scene()
links = []
for i in range(5):
    l = link.copy()
    if i % 2 == 1:                 # vertical links stand through flat neighbours
        l.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, [1, 0, 0]))
    # position along an arc
    theta = (i * PITCH) / COIL_R
    x, y = COIL_R * np.sin(theta), COIL_R * (1 - np.cos(theta))
    rot = trimesh.transformations.rotation_matrix(theta, [0, 0, 1])
    l.apply_transform(rot)
    l.apply_translation([x, y, 0])
    l.apply_translation([0, 0, -l.bounds[0][2]])   # rest on bed
    links.append(l)
    chain.add_geometry(l, geom_name=f"link_{i}")

# verify: no intersections, real clearances between neighbours
mgr = trimesh.collision.CollisionManager()
ok = True
for i, l in enumerate(links):
    mgr.add_object(f"l{i}", l)
col, names = mgr.in_collision_internal(return_names=True)
print("chain collisions:", col, names if col else "")
for i in range(4):
    m1 = trimesh.collision.CollisionManager(); m1.add_object("a", links[i])
    dist = m1.min_distance_single(links[i+1])
    print(f"  link{i}-link{i+1} clearance: {dist:.2f} mm")
out2 = os.path.join(M, "chain-test-5seg.3mf")
chain.export(out2)
chk2 = trimesh.load(out2, force="scene")
print("chain-test:", len(chk2.geometry), "links, extents", np.round(chk2.bounds[1]-chk2.bounds[0], 1))
EOF_MARKER = None
