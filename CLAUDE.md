# Working in this repo

## Changing geometry means answering to the version check

Almost every part here mates with something: carbon rods in their sockets,
the Ø12 thread, the 16.6 mm hex the wrench drives, the specimen tooth on
its platform, the ZooTalkers disc seating into a Mattel toy's rim. A part
that quietly stops fitting what it fitted, under the same version number,
is the failure this repo most needs to avoid — the mating surface is not
ours to move.

So after any change that could move geometry — a generator, a module it
imports, a constant, a profile, a cutter — run the check:

    make build            # rebuilds, then reconciles the ledger
    python3 tools/versions.py --check    # reconcile without writing

It reports `N of M generated parts checked against their built shape`. A
part it could not measure is listed as **NOT CHECKED**, which is not the
same as passing.

### What it measures, and what it asks for

It measures the **built solid** at the parameters the card ships with —
not the source text. Source hashing was tried and is wrong in both
directions: a rename rewrites the text without moving a vertex, and a
number edited in an imported module moves vertices without touching the
text.

| what moved | what it asks for |
| --- | --- |
| size, volume, body count or topology — **it may no longer fit** | **major** |
| vertices moved, fit held — it only looks different | **minor** |
| nothing measurable moved (a refactor) | nothing |

A **patch never satisfies either**: a patch says nothing measurable moved.
Tolerances are physical, not numerical — size to 0.01 mm and volume to
four figures, because 0.05 mm decided whether a rod entered its socket and
the nozzle lays 0.42 mm, so a micron has never decided anything.

### When it faults

Bump the declared `version=` on that card in `tools/catalog.py`, to the
level it asked for. The fault will not clear itself — recording the new
shape while reporting the fault would fire once and then go quiet with the
wrong version still declared.

Do not bump a version to silence the check without understanding what
moved. And do not bump a part another session is working on: say so
instead.

`cosmetic=True` on a card exempts it. Reviewing all 22 generated parts,
none qualified — so reach for it only when a part genuinely fits nothing.

## Collision sweeps: add the mover once

`CollisionManager.in_collision_single(mesh, transform=T)` and
`min_distance_single` build a BVH for the mesh they are handed, **on every
call**. In a loop that costs far more than the query it is preparing for.
Add the mover to the manager once and move it instead:

    cm.add_object("static", part)
    cm.add_object("mover", bolt)          # once
    for T in poses:
        cm.set_transform("mover", T)      # not in_collision_single(bolt, T)
        if cm.in_collision_internal():
            ...

With two objects in the manager the internal check asks exactly the same
question. `assembly.Sweep` already does this; use it where it fits.

The trap scales with the mesh and is easy to dismiss from a small test:
worth 1.3x at 1k faces, 85x at 4k, 189x at 16k, 273x at 64k. Real parts
here are 13k-64k. It has now been found three times -- assembly.py and
mobility.py both carry comments about it, and gen_montessori and
gen_wrench were still paying it, 18.4x and 8.7x respectively.

## The ledger is local

`models/versions.json` is gitignored, like everything under `models/`. It
is a working record, not a shipped artifact, and it re-baselines when the
measurement method changes.

## Other standing rules

- Commit only what nothing here can rebuild. `models/` is gitignored with
  one exception: `models/specimen/meherrin-textured.glb` came off a
  scanner and no generator will ever make it.
- Pages render the printed 3MF itself. Pose data goes inside the archive,
  never a GLB beside it.
- Hand over a file path for slicing. Never launch Bambu Studio.
