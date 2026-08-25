#!/usr/bin/env python3
"""Index toy-print 3MF files: validate geometry, fit primitives, extract thumbnails."""
import hashlib, io, json, math, os, re, sys, zipfile
import xml.etree.ElementTree as ET
import numpy as np
import trimesh

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index_out")
THUMBS = os.path.join(OUT, "thumbs")
os.makedirs(THUMBS, exist_ok=True)

FILES = [
    "sphere_stand_1.0in.3mf",
    "sphere_stand_2.0in.3mf",
    "sphere_stand_3.0in.3mf",
    "Vortex+v3+project.3mf",
    "pufferfish.3mf",
    "pufferfish-p2s-threeplates.3mf",
    "pufferfish-p2s-onecolor.3mf",
    "magic_spinning_top_+23+de+fight+d.3mf",
    "pikachu+more+resistant+one+color.3mf",
    "Quantum+Skull.3mf",
    "Mini+Fidget+Ball.3mf",
    "Mini+Stackable+Supports+added+back+in.3mf",
    "Staryu_Starmie_Spin_Spin.3mf",
    "Staryu_Starmie_Spin_Spin (1).3mf",
]
DL = os.path.expanduser("~/Downloads")

def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def extract_thumb(path, slug):
    """Pull best embedded thumbnail; return relative filename or None."""
    prefs = ["Auxiliaries/.thumbnails/thumbnail_middle.png",
             "Auxiliaries/.thumbnails/thumbnail_3mf.png",
             "Metadata/plate_1.png", "Metadata/top_1.png"]
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            for p in prefs:
                if p in names:
                    data = z.read(p)
                    fn = f"{slug}.png"
                    with open(os.path.join(THUMBS, fn), "wb") as f:
                        f.write(data)
                    return fn
    except Exception:
        pass
    return None

def read_metadata(path):
    """3MF core metadata + Bambu slice_info."""
    meta = {}
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            try:
                root = ET.fromstring(z.read("3D/3dmodel.model")[:200000] if False else z.read("3D/3dmodel.model"))
            except Exception:
                root = None
            if root is not None:
                ns = {"m": root.tag.split("}")[0].strip("{")}
                for md in root.findall("m:metadata", ns):
                    n, v = md.get("name", ""), (md.text or "").strip()
                    if v and n:
                        meta[n.split(":")[-1]] = v[:200]
            if "Metadata/slice_info.config" in names:
                txt = z.read("Metadata/slice_info.config").decode("utf8", "ignore")
                w = re.findall(r'key="weight"\s+value="([\d.]+)"', txt)
                t = re.findall(r'key="prediction"\s+value="(\d+)"', txt)
                if w: meta["slicer_weight_g"] = sum(float(x) for x in w)
                if t: meta["slicer_time_s"] = sum(int(x) for x in t)
    except Exception as e:
        meta["meta_error"] = str(e)[:100]
    return meta

def principal_axis_stats(m):
    """Fit primitives: return dict of scores + fitted params (mm)."""
    v = m.vertices
    c = v.mean(axis=0)
    d = v - c
    ext = m.bounding_box.primitive.extents
    bbox_vol = float(np.prod(ext))
    V = float(abs(m.volume)) if m.is_volume else float(abs(m.volume)) if m.is_watertight else None
    A = float(m.area)
    out = {}
    # sphere fit: radial distance spread from centroid
    r = np.linalg.norm(d, axis=1)
    out["sphere_r_mean"] = float(r.mean())
    out["sphere_r_cv"] = float(r.std() / r.mean()) if r.mean() > 0 else 1.0
    # sphericity (needs volume)
    if V and V > 0:
        out["sphericity"] = float(np.pi ** (1/3) * (6 * V) ** (2/3) / A)
        out["box_fill"] = float(V / bbox_vol) if bbox_vol > 0 else None
    # cylinder fit about z axis (models are usually z-up)
    rz = np.linalg.norm(d[:, :2], axis=1)
    if rz.mean() > 0:
        out["cyl_r_mean"] = float(rz.mean())
        out["cyl_r_cv"] = float(rz.std() / rz.mean())
    # rotational symmetry order via angular FFT of xy vertex angles
    ang = np.arctan2(d[:, 1], d[:, 0])
    hist, _ = np.histogram(ang, bins=360, weights=rz)
    if hist.sum() > 0:
        F = np.abs(np.fft.rfft(hist - hist.mean()))
        if len(F) > 13:
            k = int(np.argmax(F[1:13]) + 1)
            out["sym_order"] = k
            out["sym_strength"] = float(F[k] / (np.abs(F[1:13]).sum() + 1e-9))
    # aspect: tall/flat/cubic
    e = sorted(ext)
    out["aspect_ratio"] = float(e[2] / e[0]) if e[0] > 0 else None
    return out

def classify(stats, genus, ext):
    """Human-readable primitive guess."""
    s = stats
    if s.get("sphere_r_cv", 1) < 0.08:
        return "sphere"
    if s.get("cyl_r_cv", 1) < 0.10 and s.get("aspect_ratio", 0) and s["aspect_ratio"] < 20:
        return "cylinder/ring" if genus and genus >= 1 else "cylinder"
    if s.get("box_fill") and s["box_fill"] > 0.85:
        return "box"
    if genus and genus >= 1:
        return f"toroidal (genus {genus})"
    if s.get("sym_order") and s.get("sym_strength", 0) > 0.5:
        return f"{s['sym_order']}-fold rotational form"
    return "freeform"

def analyze(path):
    name = os.path.basename(path)
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower().replace(".3mf", "")).strip("_")
    rec = {"file": name, "slug": slug, "size_mb": round(os.path.getsize(path) / 1e6, 2),
           "md5": md5(path)}
    rec["thumb"] = extract_thumb(path, slug)
    rec["meta"] = read_metadata(path)
    try:
        scene = trimesh.load(path, force="scene")
        geoms = list(scene.geometry.items())
    except Exception as e:
        rec["load_error"] = str(e)[:200]
        return rec
    objs = []
    tot_tri = tot_vert = 0
    all_meshes = []
    for gname, g in geoms:
        if not isinstance(g, trimesh.Trimesh) or len(g.faces) == 0:
            continue
        # apply scene transform so extents are placed correctly
        tf = None
        for node in scene.graph.nodes_geometry:
            t, gn = scene.graph[node]
            if gn == gname:
                tf = t; break
        gm = g.copy()
        if tf is not None:
            gm.apply_transform(tf)
        all_meshes.append(gm)
        tot_tri += len(gm.faces); tot_vert += len(gm.vertices)
        wt = bool(gm.is_watertight)
        euler = int(gm.euler_number)
        genus = (2 - euler) // 2 if wt else None
        nm_edges = int((trimesh.grouping.group_rows(gm.edges_sorted, require_count=None) is not None) and 0)
        # duplicate / degenerate faces
        dup = len(gm.faces) - len(trimesh.grouping.unique_rows(np.sort(gm.faces, axis=1))[0])
        areas = gm.area_faces
        degen = int((areas < 1e-10).sum())
        ext = gm.bounding_box.primitive.extents
        vol_cm3 = abs(gm.volume) / 1000.0 if wt else None
        st = principal_axis_stats(gm)
        objs.append({
            "name": gname[:60], "vertices": len(gm.vertices), "triangles": len(gm.faces),
            "watertight": wt, "euler": euler, "genus": genus,
            "dup_faces": int(dup), "degen_faces": degen,
            "bodies": int(gm.body_count),
            "extents_mm": [round(float(x), 2) for x in ext],
            "volume_cm3": round(vol_cm3, 2) if vol_cm3 is not None else None,
            "weight_g_pla_solid": round(vol_cm3 * 1.24, 1) if vol_cm3 is not None else None,
            "stats": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in st.items()},
            "classify": classify(st, genus, ext),
        })
    rec["objects"] = objs
    rec["n_objects"] = len(objs)
    rec["total_triangles"] = tot_tri
    if all_meshes:
        comb = trimesh.util.concatenate(all_meshes)
        ext = comb.bounding_box.primitive.extents
        rec["overall_extents_mm"] = [round(float(x), 2) for x in ext]
        wt_all = all(o["watertight"] for o in objs)
        rec["all_watertight"] = wt_all
        if wt_all:
            v = sum(o["volume_cm3"] for o in objs)
            rec["total_volume_cm3"] = round(v, 2)
            rec["weight_g_pla_solid"] = round(v * 1.24, 1)
        rec["_render_mesh"] = comb  # consumed by renderer, stripped before json
    return rec

def render_thumb(rec):
    """Matplotlib fallback render for files with no embedded thumbnail."""
    m = rec.get("_render_mesh")
    if m is None or rec.get("thumb"):
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    mm = m
    if len(mm.faces) > 60000:
        idx = np.random.default_rng(0).choice(len(mm.faces), 60000, replace=False)
        tris = mm.vertices[mm.faces[idx]]
    else:
        tris = mm.vertices[mm.faces]
    fig = plt.figure(figsize=(4, 4), dpi=80)
    ax = fig.add_subplot(111, projection="3d")
    # simple lambert-ish shading by face normal z
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    nn = n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)
    light = np.array([0.4, 0.3, 0.85]); light /= np.linalg.norm(light)
    lum = 0.35 + 0.65 * np.clip(nn @ light, 0, 1)
    colors = np.stack([lum * 0.95, lum * 0.75, lum * 0.4, np.ones_like(lum)], axis=1)
    pc = Poly3DCollection(tris, facecolors=colors, edgecolors="none")
    ax.add_collection3d(pc)
    lo, hi = mm.bounds
    ctr, span = (lo + hi) / 2, (hi - lo).max() / 2
    ax.set_xlim(ctr[0]-span, ctr[0]+span); ax.set_ylim(ctr[1]-span, ctr[1]+span)
    ax.set_zlim(ctr[2]-span, ctr[2]+span)
    ax.set_axis_off(); ax.view_init(elev=28, azim=-55)
    fn = f"{rec['slug']}.png"
    fig.savefig(os.path.join(THUMBS, fn), bbox_inches="tight", pad_inches=0, transparent=True)
    plt.close(fig)
    rec["thumb"] = fn

def main():
    results = []
    for f in FILES:
        p = os.path.join(DL, f)
        if not os.path.exists(p):
            results.append({"file": f, "error": "missing"}); continue
        print(f"--- {f}", flush=True)
        rec = analyze(p)
        try:
            render_thumb(rec)
        except Exception as e:
            print("  render failed:", e)
        rec.pop("_render_mesh", None)
        results.append(rec)
        print(f"    objs={rec.get('n_objects')} tris={rec.get('total_triangles')} "
              f"wt={rec.get('all_watertight')} thumb={rec.get('thumb')}", flush=True)
    with open(os.path.join(OUT, "index.json"), "w") as f:
        json.dump(results, f, indent=1)
    print("WROTE", os.path.join(OUT, "index.json"))

if __name__ == "__main__":
    main()
