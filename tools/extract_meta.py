#!/usr/bin/env python3
"""Extract embedded photos + metadata from 3MF files into models/meta/<slug>/.

Never overwrites existing files, so hand-replaced covers/photos survive re-runs.
Writes meta.json (designer, license, description, profile, dates, slicer est.)
plus cover.png and photo_N.<ext> pulled from the archive.
"""
import html
import json
import os
import re
import zipfile

MODELS = os.path.expanduser("~/Code/My3DPrints/models")
META = os.path.join(MODELS, "meta")

COVER_PREF = [
    "Auxiliaries/.thumbnails/thumbnail_middle.png",
    "Auxiliaries/.thumbnails/thumbnail_3mf.png",
    "Metadata/plate_1.png",
    "Metadata/top_1.png",
]
META_KEYS = ["Designer", "License", "ProfileTitle", "CreationDate",
             "ModificationDate", "Application", "Origin", "DesignModelId"]


def slugify(fname):
    return re.sub(r"[^a-z0-9]+", "_", fname.lower().rsplit(".", 1)[0]).strip("_")


def strip_html(s, limit=700):
    s = html.unescape(html.unescape(s))
    s = re.sub(r"<img[^>]*>", " ", s)
    s = re.sub(r"</?(p|li|ol|ul|h\d|br)[^>]*>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", s)).strip()
    return (s[:limit] + "…") if len(s) > limit else s


def extract(path):
    slug = slugify(os.path.basename(path))
    outdir = os.path.join(META, slug)
    os.makedirs(outdir, exist_ok=True)
    meta = {"source_file": os.path.basename(path), "slug": slug}
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:
        meta["error"] = str(e)[:120]
        return slug, meta
    names = z.namelist()

    try:
        model = z.read("3D/3dmodel.model").decode("utf8", "ignore")
        for key in META_KEYS:
            m = re.search(f'<metadata name="(?:[^"]*:)?{key}">([^<]*)</metadata>', model)
            if m and m.group(1).strip():
                meta[key] = html.unescape(m.group(1).strip())[:200]
        m = re.search(r'<metadata name="Description">(.*?)</metadata>', model, re.S)
        if m:
            meta["Description"] = strip_html(m.group(1))
    except KeyError:
        pass

    if "Metadata/slice_info.config" in names:
        txt = z.read("Metadata/slice_info.config").decode("utf8", "ignore")
        w = re.findall(r'key="weight" value="([\d.]+)"', txt)
        t = re.findall(r'key="prediction" value="(\d+)"', txt)
        if w:
            meta["slicer_weight_g"] = round(sum(map(float, w)), 1)
        if t:
            s = sum(map(int, t))
            meta["slicer_time"] = f"{s // 3600}h {s % 3600 // 60:02d}m"

    cover = os.path.join(outdir, "cover.png")
    if not os.path.exists(cover):
        for p in COVER_PREF:
            if p in names:
                with open(cover, "wb") as f:
                    f.write(z.read(p))
                meta["cover_from"] = p
                break
    if os.path.exists(cover):
        meta["cover"] = "cover.png"

    photos = []
    pics = sorted(n for n in names
                  if n.startswith("Auxiliaries/Model Pictures/")
                  and n.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
    for i, p in enumerate(pics[:8], 1):
        ext = p.rsplit(".", 1)[-1].lower()
        dst = os.path.join(outdir, f"photo_{i}.{ext}")
        if not os.path.exists(dst):
            with open(dst, "wb") as f:
                f.write(z.read(p))
        photos.append(os.path.basename(dst))
    if photos:
        meta["photos"] = photos

    mj = os.path.join(outdir, "meta.json")
    with open(mj, "w") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    return slug, meta


if __name__ == "__main__":
    done = []
    for fname in sorted(os.listdir(MODELS)):
        if not fname.lower().endswith(".3mf"):
            continue
        slug, meta = extract(os.path.join(MODELS, fname))
        done.append(slug)
        tag = []
        if "cover" in meta: tag.append("cover")
        if "photos" in meta: tag.append(f"{len(meta['photos'])} photos")
        if "Designer" in meta: tag.append(meta["Designer"])
        print(f"{slug:44s} {' · '.join(tag) or '(no embedded media)'}")
    print(len(done), "files processed ->", META)
