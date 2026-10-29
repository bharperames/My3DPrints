"""Wire flags for the orbital jig's controller: one small label per wire,
printed on the Brother QL's 38 mm tape (DK-22225) and folded onto the wire.

A 28 AWG wire is 0.8 mm across -- nothing wrapped round it can be read.
So each label is a flag: a slice across the tape, the same text printed on
both halves, and a blank band between them. The band wraps the wire, and
the two halves are pressed together sticky side to sticky side, so no
adhesive is left out and the flag reads from either side. Folding across a
line that runs along the wire turns the far half over and back again, so
it is printed exactly as the near one, not rotated.

The text is the net and where each end goes, set against the band: read
toward the wire on one side, away from it on the other. The wire's length
and its color, "65mm YEL", run up each half's outer edge.

    python tools/wire_labels.py            # writes the strip, prints nothing
    python tools/wire_labels.py --print    # and sends it to the printer

Printing borrows FossilRecord's label_printer (its roll table and its
send_to_printer), run by the interpreter that has brother_ql installed.
"""
import argparse
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_orbital_jig as J  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "models", "orbital-jig", "wire-labels.png")
FOSSIL = os.path.expanduser("~/Code/FossilRecord")
PRINT_PY = "/usr/bin/python3"          # the interpreter with brother_ql

# 38 mm tape: 413 dots across its printable 35 mm, at the QL's 300 dpi
WIDTH_PX = 413
PX_MM = 300 / 25.4

# across the tape: the flag's two halves and the band that wraps the wire
# (pi x 0.8 mm of insulation, and the tape's own thickness twice over)
WRAP_MM = 3.0
HALF_MM = (WIDTH_PX / PX_MM - WRAP_MM) / 2
FLAG_MM = 9.5                          # along the tape: the flag's width on the wire
PAD_MM = 0.8
NET_MM, ROW_MM = 2.4, 1.6              # cap heights: the net, the ends

BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
NARROW = "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf"


def px(mm):
    return int(round(mm * PX_MM))


def end_short(e, color):
    """Where a wire's end goes, in as few words as name it: a wire that
    comes in on a cable is named by the cable and its own color."""
    kind = e[0]
    if kind == "cable":
        return f"Motor {color}"
    if kind == "lead":
        return f"Sensor {color}"
    if kind == "xiao":
        return f"XIAO {e[1]}"
    if kind == "drv":
        return f"DRV {e[2]}"
    if kind == "under":
        return f"DRV {e[2]}"
    return f"{e[1]} joint"


SHORT_NET = {"encoder A": "Enc A", "encoder B": "Enc B"}


def flag_lines(w):
    """The flag's three lines: the net, then each end."""
    return [SHORT_NET.get(w[2], w[2]), end_short(w[3], w[1]) + "  \u2194", end_short(w[4], w[1])]


def _font(path, mm):
    """A font whose capitals stand `mm` tall."""
    size = px(mm / 0.716)               # Arial's cap height is 0.716 em
    return ImageFont.truetype(path, size)


def _fit(draw, text, path, mm, width):
    """The largest of `mm`, stepping down, at which `text` fits `width`."""
    while mm > 1.2:
        f = _font(path, mm)
        if draw.textlength(text, font=f) <= width:
            return f
        mm -= 0.1
    return _font(path, 1.2)


LEN_MM = 1.3                           # cap height of the edge columns: length, color
COL_MM = 2.0                           # each column's share of the half, gap included


COLOR_ABBR = {"red": "RED", "black": "BLK", "yellow": "YEL", "white": "WHT",
              "blue": "BLU", "green": "GRN"}


def edge_line(w):
    """Up the outer edge: the wire's length and its color, "65mm YEL"."""
    return f"{J.wire_mm(w[0]):.0f}mm {COLOR_ABBR[w[1]]}"


def edge_text(img, draw, text, x_edge, side, y0):
    """`text` turned a quarter, centered up the flag, its letters' tops
    toward the half's outer edge, which runs at x_edge."""
    # as large as LEN_MM, and clear of the cut lines at either end
    f = _fit(draw, text, NARROW, LEN_MM, px(FLAG_MM - 1.4))
    tw = int(draw.textlength(text, font=f)) + 2
    th = int(f.size) + 2
    t = Image.new("L", (tw, th), 255)
    ImageDraw.Draw(t).text((1, th - 1), text, font=f, fill=0, anchor="ld")
    t = t.rotate(90 if side < 0 else -90, expand=True)
    x = x_edge if side < 0 else x_edge - t.width
    y = y0 + (px(FLAG_MM) - t.height) // 2
    img.paste(Image.merge("RGB", [t] * 3), (x, y), Image.eval(t, lambda v: 255 - v))


def draw_half(img, draw, y0, lines, cols, edge, side):
    """One half of a flag, its text against the band: `edge` is the band's
    side of the half, and `side` -1 when the text runs up to it (the near
    half, read toward the wire), +1 when it runs away from it. `cols` run
    up the half's outer edge, the first outermost; the lines shrink,
    together, only where they would run into them."""
    room = px(HALF_MM - 2 * PAD_MM - COL_MM * len(cols) - 0.6)
    row = min((_fit(draw, r, NARROW, ROW_MM, room) for r in lines[1:]), key=lambda f: f.size)
    wide = max(draw.textlength(r, font=row) for r in lines[1:])
    big = _fit(draw, lines[0], BOLD, NET_MM, wide)
    anchor = "r" if side < 0 else "l"
    x = edge + side * px(PAD_MM)
    base = y0 + px(PAD_MM + NET_MM)
    draw.text((x, base), lines[0], font=big, fill="black", anchor=anchor + "s")
    for r in lines[1:]:
        base += px(ROW_MM + 0.75)
        draw.text((x, base), r, font=row, fill="black", anchor=anchor + "s")
    outer = edge + side * px(HALF_MM)
    for i, c in enumerate(cols):
        edge_text(img, draw, c, outer - side * px(0.4 + COL_MM * i), side, y0)


def dashed(draw, y, x0, x1, dash=px(1.0), gap=px(1.0)):
    x = x0
    while x < x1:
        draw.line([(x, y), (min(x + dash, x1), y)], fill="black", width=1)
        x += dash + gap



def strip(wires):
    """The whole strip: a heading, then a flag per wire with cut lines
    between them and ticks at the edges of the band that wraps the wire."""
    head = px(10.5)
    h = px(FLAG_MM)
    img = Image.new("RGB", (WIDTH_PX, head + h * len(wires) + px(2)), "white")
    d = ImageDraw.Draw(img)
    full = WIDTH_PX - 2 * px(PAD_MM)
    d.text((px(PAD_MM), px(1.0)), "Orbital jig: wire flags", font=_font(BOLD, 2.0),
           fill="black", anchor="lt")
    note = ("Cut on the dashed lines. Wrap the band",
            "between the ticks round the wire, then press",
            "the halves together, sticky side to sticky side.")
    sf = min((_fit(d, t, NARROW, 1.5, full) for t in note), key=lambda f: f.size)
    for i, t in enumerate(note):
        d.text((px(PAD_MM), px(4.2 + 1.9 * i)), t, font=sf, fill="black", anchor="lt")
    a0, a1 = px(HALF_MM), px(HALF_MM + WRAP_MM)
    for k, w in enumerate(wires):
        y0 = head + k * h
        dashed(d, y0, 0, WIDTH_PX)
        L = flag_lines(w)
        cols = [edge_line(w)]
        draw_half(img, d, y0, L, cols, a0, -1)
        draw_half(img, d, y0, L, cols, a1, +1)
        # the band's edges, top and bottom, where the wire lies between
        for x in (a0, a1):
            d.line([(x, y0 + 2), (x, y0 + px(1.6))], fill="black", width=2)
            d.line([(x, y0 + h - px(1.6)), (x, y0 + h - 2)], fill="black", width=2)
    dashed(d, head + h * len(wires), 0, WIDTH_PX)
    return img


def send(path):
    """To the printer, through FossilRecord's own sender and its 38 mm roll."""
    code = ("import sys; sys.path.insert(0, %r)\n"
            "import label_printer as L\n"
            "from PIL import Image\n"
            "L.send_to_printer([Image.open(%r).convert('RGB')], L.LABEL_ROLLS['38'])\n"
            % (FOSSIL, path))
    subprocess.run([PRINT_PY, "-c", code], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--print", action="store_true", help="send the strip to the label printer")
    ap.add_argument("--only", nargs="*", help="wire ids, e.g. W15 W16 (default: every wire)")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    wires = [w for w in J.WIRES if not args.only or w[0] in args.only]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    img = strip(wires)
    img.save(args.out, dpi=(300, 300))
    print(f"{len(wires)} flags, {img.height / PX_MM:.0f} mm of tape: {args.out}")
    if args.print:
        send(args.out)
        print("sent to the printer")


if __name__ == "__main__":
    main()
