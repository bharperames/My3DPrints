# ZooTalkers — the toy the coded ring insert is cut to fit

Mattel ZooTalkers, © 2011, moulded `1186-MJ-1-NL`. Each animal is a rubber
figure whose underside carries a coded end: concentric rings inside a lip,
read by a base station when the animal is pressed onto it. `tools/gen_binary_rings.py`
reproduces that end for any code, and its module docstring is the source of
truth for every dimension. These photographs are where the dimensions came
from, and what they have to keep agreeing with.

## The sample everything was measured off

`measured-green-01.jpg` … `-06.jpg` — one green animal, unlabeled, at six
angles. Every number in the generator was read off this one:

| photo | what it shows |
|---|---|
| 01, 02 | the end in the hand, whole — the collar, the lip, the bore |
| 03, 04 | oblique, showing bore depth and the rectangular window in the moat wall |
| 05, 06 | close to top-down, the concentric rings and the nub at the centre |

What those readings pin, what they do not, and which of them contradicted
each other is written out in the generator's docstring rather than here —
one place, next to the code that acts on it.

The rectangular window visible in 03 and 04 does **nothing**: the toy reads
at any rotation, so the switch is the lip ring itself and not a feature at
one angle.

## The reader

`reader-base.jpg` — the socket in the base station. The bumps are sensor
plungers, each at its own radius, which is what makes a concentric ring code
readable at any rotation. Counted off this photograph they come to five, at
radii of roughly 0.7, 4.0, 6.3, 8.1 and 10.9 mm on a ø28 bore — the radii are
scaled off a picture and are crude, the count is not. One plunger sits on the
axis, which is why the centre of the plug is a bit and not a datum.

## Eleven coded ends

`end-*.jpg` — camel, polar bear, turtle, dolphin, cheetah, orangutan, koala,
ostrich, seal, tiger, and one unlabeled tan animal. This is the corpus that
fixes the topology, and it is what corrected it:

- **The centre is a bit.** Camel and tiger stand a boss there; polar bear,
  turtle, koala and ostrich sink a pocket. It varies, so it is code — which
  is what the reader's axis plunger is reading. The generator modelled it as
  a permanent nub until these photographs said otherwise.
- **Runs of adjacent set bits merge into one plateau.** Cheetah is a single
  wide disc; polar bear is a ring alone on a flat floor. Same geometry the
  generator makes for a run of 1s.
- **The patterns differ only in which positions stand up**, at radii that
  stay put from animal to animal — the premise of the band grid.

Bits are numbered from the middle out: bit 1 is the centre disc, bit 5 the
outermost ring, worth 1, 2, 4, 8 and 16. An odd code stands its centre up;
an even one sinks a pocket there.

| animal | reading |
|---|---|
| tiger | bit 1 set — so an odd code |
| seal | bit 1 clear — so an even code |
| koala | everything but bits 1 and 5 → **code 14** |

The rest are unread. These photographs are also the way to close the one
thing still open in the generator's docstring — how the inner field divides
among its three inner rings. Pooled across eleven samples, the up and down
transitions should cluster on the real boundaries.

**A caution the photographs earned.** A concave pocket lit from one side
photographs like a convex boss. Reading relief off these at thumbnail size
got the centre exactly backwards once. Zoom before believing, and prefer the
part in the hand.

## Naming

Filenames use the labels written on the photographs, in American spelling
(`orangutan`). The tan one arrived unlabeled.
