#!/usr/bin/env python3
"""Parts designed in-session: geodesic held-sphere cage and a 5-link chain.

Both are verified after building: watertightness through 3MF round-trip,
captivity/threading, and mating clearances. Requires manifold3d + python-fcl.
"""
import os
import numpy as np
import trimesh
from trimesh.proximity import signed_distance

M = os.path.expanduser("~/Code/My3DPrints/models")

# ---------- 1. Held sphere: icosahedron strut cage with captive ball ----------
# 30 struts along the edges of an icosahedron (fully triangulated = rigid),
# joint spheres at the 12 vertices, printed face-down on a triangle base.
# Ball Ø19 cannot pass the ~Ø12 triangular openings. 5.8 cm³ vs 16.5 for the
# earlier windowed shell. The ball stands on a breakaway pip from the bed.
R, STRUT_R, JOINT_R, BALL_R, PIP_R = 25.0, 1.6, 2.1, 9.5, 1.2

ico = trimesh.creation.icosahedron()
V = ico.vertices / np.linalg.norm(ico.vertices, axis=1, keepdims=True) * R
F = ico.faces
n0 = np.cross(V[F[0][1]] - V[F[0][0]], V[F[0][2]] - V[F[0][0]])
V = trimesh.transform_points(
    V, trimesh.geometry.align_vectors(n0 / np.linalg.norm(n0), [0, 0, -1]))

edges = set()
for f in F:
    for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
        edges.add((min(a, b), max(a, b)))
parts = []
for a, b in edges:
    p, q = V[a], V[b]
    d = q - p
    L = np.linalg.norm(d)
    cyl = trimesh.creation.cylinder(radius=STRUT_R, height=L, sections=24)
    cyl.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], d / L))
    cyl.apply_translation((p + q) / 2)
    parts.append(cyl)
for v in V:
    s = trimesh.creation.icosphere(subdivisions=2, radius=JOINT_R)
    s.apply_translation(v)
    parts.append(s)
# one batch union — folding pairwise leaves hairline cracks
cage = trimesh.boolean.union(parts, engine="manifold")

zbed = cage.bounds[0][2]
zc = zbed + BALL_R + 3.0                       # 3 mm pip under the ball
ball = trimesh.creation.icosphere(subdivisions=4, radius=BALL_R)
ball.apply_translation([0, 0, zc])
pip = trimesh.creation.cylinder(radius=PIP_R, height=(zc - BALL_R + 0.4) - zbed,
                                sections=24)
pip.apply_translation([0, 0, (zbed + zc - BALL_R + 0.4) / 2])
held = trimesh.boolean.union([ball, pip], engine="manifold")
clearance = float((-signed_distance(cage, ball.vertices[::7])).min())

cage.apply_translation([0, 0, -zbed])
held.apply_translation([0, 0, -zbed])
sc = trimesh.Scene()
sc.add_geometry(cage, geom_name="cage")
sc.add_geometry(held, geom_name="ball")
out1 = os.path.join(M, "held-sphere.3mf")
sc.export(out1)
chk = trimesh.load(out1, force="scene")
edge_len = float(np.linalg.norm(V[F[0][0]] - V[F[0][1]]))
opening = 2 * (edge_len / (2 * np.sqrt(3)) - STRUT_R)
print(f"held-sphere: {[(len(g.faces), g.is_watertight) for g in chk.geometry.values()]}"
      f" vol {cage.volume/1000:.1f}+{held.volume/1000:.1f} cm3"
      f" opening Ø{opening:.1f} vs ball Ø{2*BALL_R} "
      f"({'CAPTIVE' if opening < 2*BALL_R else 'ESCAPES'}) clearance {clearance:.2f} mm")

# ---------- 2. Chain: five stadium links at alternating ±45° tilt ----------
# 0.75" links, 0.125" round cross-section. ±45° tilt lets every link
# self-support; pitch 11.0 gives 0.74 mm clearance with threading verified.
D, L_OUT, CL_W = 3.175, 19.05, 8.0
CL_L = L_OUT - D
PITCH, COIL_R = 11.0, 200.0


def stadium_path(n_per=28):
    s, r = (CL_L - CL_W) / 2, CL_W / 2
    pts = []
    for t in np.linspace(-np.pi / 2, np.pi / 2, n_per):
        pts.append([s + r * np.cos(t), r * np.sin(t)])
    for t in np.linspace(np.pi / 2, 3 * np.pi / 2, n_per):
        pts.append([-s + r * np.cos(t), r * np.sin(t)])
    return np.array(pts)


def tube_from_loop(loop2d, tube_r, n_sec=22):
    """Watertight tube swept along a closed planar loop (torus topology)."""
    P = np.column_stack([loop2d, np.zeros(len(loop2d))])
    n = len(P)
    T = np.roll(P, -1, axis=0) - np.roll(P, 1, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    N = np.cross([0, 0, 1.0], T)
    N /= np.linalg.norm(N, axis=1, keepdims=True)
    B = np.cross(T, N)
    ang = np.linspace(0, 2 * np.pi, n_sec, endpoint=False)
    ring = np.stack([np.cos(ang), np.sin(ang)], axis=1) * tube_r
    Vv = (P[:, None, :] + ring[None, :, 0:1] * N[:, None, :]
          + ring[None, :, 1:2] * B[:, None, :]).reshape(-1, 3)
    Ff = []
    for i in range(n):
        for j in range(n_sec):
            a = i * n_sec + j
            b = i * n_sec + (j + 1) % n_sec
            c = ((i + 1) % n) * n_sec + j
            dd = ((i + 1) % n) * n_sec + (j + 1) % n_sec
            Ff += [[a, b, c], [b, dd, c]]
    m = trimesh.Trimesh(vertices=Vv, faces=Ff)
    m.fix_normals()
    return m


link = tube_from_loop(stadium_path(), D / 2)
sc2 = trimesh.Scene()
links = []
for i in range(5):
    l = link.copy()
    l.apply_transform(trimesh.transformations.rotation_matrix(
        np.pi / 4 if i % 2 == 0 else -np.pi / 4, [1, 0, 0]))
    th = i * PITCH / COIL_R
    l.apply_transform(trimesh.transformations.rotation_matrix(th, [0, 0, 1]))
    l.apply_translation([COIL_R * np.sin(th), COIL_R * (1 - np.cos(th)), 0])
    links.append(l)
zmin = min(l.bounds[0][2] for l in links)
memb = trimesh.creation.box((CL_L - D - 0.3, CL_W - D - 0.3, 0.6))
allok = True
for i, l in enumerate(links):
    l.apply_translation([0, 0, -zmin])
    sc2.add_geometry(l, geom_name=f"link_{i}")
for i in range(4):
    cm = trimesh.collision.CollisionManager()
    cm.add_object("a", links[i])
    col = cm.in_collision_single(links[i + 1])
    d = cm.min_distance_single(links[i + 1])
    m = memb.copy()
    m.apply_transform(trimesh.transformations.rotation_matrix(
        np.pi / 4 if i % 2 == 0 else -np.pi / 4, [1, 0, 0]))
    th = i * PITCH / COIL_R
    m.apply_transform(trimesh.transformations.rotation_matrix(th, [0, 0, 1]))
    m.apply_translation([COIL_R * np.sin(th), COIL_R * (1 - np.cos(th)), -zmin])
    inter = m.intersection(links[i + 1])
    threaded = (not inter.is_empty) and inter.volume > 0.5
    print(f"  link{i}-{i+1}: collision={col} clearance={d:.2f} threaded={threaded}")
    allok &= (not col) and d >= 0.5 and threaded
out2 = os.path.join(M, "chain-test-5seg.3mf")
sc2.export(out2)
print("chain-test:", "ALL-OK" if allok else "FAILED CHECKS",
      np.round(trimesh.load(out2, force='scene').bounds[1], 1))
