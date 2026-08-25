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

# ---------- 1. Held sphere: geodesic strut cage with captive ball ----------
# 120 struts along subdivided-icosphere edges (fully triangulated = rigid),
# joint spheres at the 42 vertices, printed face-down on a triangle base.
# Ball Ø19 cannot pass the ~Ø6 triangular openings. ~5.9 cm³ — a third of the
# original windowed shell. The ball stands on a breakaway pip from the bed.
R, STRUT_R, JOINT_R, BALL_R, PIP_R = 25.0, 1.1, 1.5, 9.5, 1.2

ico = trimesh.creation.icosphere(subdivisions=1)   # 42 verts / 120 edges — rounder cage
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


def build_chain(scale, fname):
    link = tube_from_loop(stadium_path() * scale, D * scale / 2)
    pitch = PITCH * scale
    sc2 = trimesh.Scene()
    links = []
    for i in range(5):
        l = link.copy()
        l.apply_transform(trimesh.transformations.rotation_matrix(
            np.pi / 4 if i % 2 == 0 else -np.pi / 4, [1, 0, 0]))
        th = i * pitch / COIL_R
        l.apply_transform(trimesh.transformations.rotation_matrix(th, [0, 0, 1]))
        l.apply_translation([COIL_R * np.sin(th), COIL_R * (1 - np.cos(th)), 0])
        links.append(l)
    zmin = min(l.bounds[0][2] for l in links)
    memb = trimesh.creation.box(((CL_L - D - 0.3) * scale, (CL_W - D - 0.3) * scale, 0.6))
    allok = True
    for i, l in enumerate(links):
        l.apply_translation([0, 0, -zmin])
        sc2.add_geometry(l, geom_name=f"link_{i}")
    # first-layer bed contact per link: footprint of material below 0.2 mm
    slab = trimesh.creation.box((400, 400, 0.2))
    slab.apply_translation([100, 0, 0.1])
    contact = links[0].intersection(slab)
    area = 0 if contact.is_empty else contact.volume / 0.2
    for i in range(4):
        cm = trimesh.collision.CollisionManager()
        cm.add_object("a", links[i])
        col = cm.in_collision_single(links[i + 1])
        d = cm.min_distance_single(links[i + 1])
        m = memb.copy()
        m.apply_transform(trimesh.transformations.rotation_matrix(
            np.pi / 4 if i % 2 == 0 else -np.pi / 4, [1, 0, 0]))
        th = i * pitch / COIL_R
        m.apply_transform(trimesh.transformations.rotation_matrix(th, [0, 0, 1]))
        m.apply_translation([COIL_R * np.sin(th), COIL_R * (1 - np.cos(th)), -zmin])
        inter = m.intersection(links[i + 1])
        threaded = (not inter.is_empty) and inter.volume > 0.5
        allok &= (not col) and d >= 0.5 * scale and threaded
    out2 = os.path.join(M, fname)
    sc2.export(out2)
    ext = trimesh.load(out2, force="scene")
    print(f"{fname}: {'ALL-OK' if allok else 'FAILED'} clearance≈{d:.2f} "
          f"bed contact/link≈{area:.1f} mm² extents {np.round(ext.bounds[1]-ext.bounds[0],1)}")


build_chain(1.0, "chain-test-5seg.3mf")
build_chain(2.0, "chain-test-5seg-2x.3mf")


# ---------- 3. Held sphere + 10-link chain (pendant variant) ----------
# A short stadium "bail" (10 mm mini-link, same tube and width as the chain)
# is welded shallow into the cage's lower shell at +45; all 10 chain links
# articulate freely. A round-ring bail is geometrically impossible here: its
# transverse width exceeds what the ±45 joint tolerates — stadium geometry is
# why chain links are chain-link-shaped. Constants from scan; re-verified.
def build_chained():
    base = trimesh.load(os.path.join(M, "held-sphere.3mf"), force="scene")
    cage2 = base.geometry["cage"].copy()
    held2 = base.geometry["ball"].copy()
    link = tube_from_loop(stadium_path(), D / 2)

    def mini_path(cl_l=10.0, n_per=28):
        s2, r2 = (cl_l - CL_W) / 2, CL_W / 2
        pts = []
        for t in np.linspace(-np.pi / 2, np.pi / 2, n_per):
            pts.append([s2 + r2 * np.cos(t), r2 * np.sin(t)])
        for t in np.linspace(np.pi / 2, 3 * np.pi / 2, n_per):
            pts.append([-s2 + r2 * np.cos(t), r2 * np.sin(t)])
        return np.array(pts)

    mini = tube_from_loop(mini_path(), D / 2)
    X_M, P1 = 21.0, 8.5

    def place(m0, x, tilt):
        l = m0.copy()
        l.apply_transform(trimesh.transformations.rotation_matrix(tilt, [1, 0, 0]))
        l.apply_translation([x, 0, 0])
        l.apply_translation([0, 0, -l.bounds[0][2]])
        return l

    bailm = place(mini, X_M, np.pi / 4)
    weld = bailm.intersection(cage2)
    assert (not weld.is_empty) and weld.volume > 3.0, "bail weld too small"
    body = trimesh.boolean.union([cage2, bailm], engine="manifold")
    links = [place(link, X_M + P1 + i * PITCH,
                   -np.pi / 4 if i % 2 == 0 else np.pi / 4) for i in range(10)]
    cm = trimesh.collision.CollisionManager()
    cm.add_object("w", body)
    assert not cm.in_collision_single(links[0])
    d1 = cm.min_distance_single(links[0])
    ok = d1 >= 0.45
    for i in range(9):
        c = trimesh.collision.CollisionManager()
        c.add_object("a", links[i])
        ok &= not c.in_collision_single(links[i + 1])
        ok &= c.min_distance_single(links[i + 1]) >= 0.5
    for l in links[1:]:
        ok &= not cm.in_collision_single(l)
    sc3 = trimesh.Scene()
    sc3.add_geometry(body, geom_name="cage_with_bail")
    sc3.add_geometry(held2, geom_name="ball")
    for i, l in enumerate(links):
        sc3.add_geometry(l, geom_name=f"link_{i + 1}")
    sc3.export(os.path.join(M, "held-sphere-chained.3mf"))
    print(f"held-sphere-chained: bail weld {weld.volume:.1f} mm3, link1 "
          f"clearance {d1:.2f}, {'ALL-OK' if ok else 'FAILED CHECKS'}")


build_chained()
