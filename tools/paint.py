"""Read a Bambu 3MF object mesh together with its per-triangle paint.

The colour is not computed from the shape: the designer painted it and it
ships in the file, one `paint_color` attribute per triangle. That makes an
authored mask of which triangles are teeth and claws -- better than any
detector, because it is what the author meant rather than what the geometry
suggests.
"""
import zipfile
import numpy as np
import xml.etree.ElementTree as ET

NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"

def read(path, member):
    z = zipfile.ZipFile(path)
    V, F, P = [], [], []
    with z.open(member) as fh:
        for ev, el in ET.iterparse(fh, events=("end",)):
            if el.tag == NS + "vertex":
                V.append((float(el.get("x")), float(el.get("y")), float(el.get("z"))))
                el.clear()
            elif el.tag == NS + "triangle":
                F.append((int(el.get("v1")), int(el.get("v2")), int(el.get("v3"))))
                P.append(el.get("paint_color") or "")
                el.clear()
    return np.array(V), np.array(F), np.array(P)
