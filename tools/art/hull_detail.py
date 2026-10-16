#!/usr/bin/env python3
"""Surface-detail helpers shared by the Alliance-authored builders.

The approved battleship carries a private copy of these helpers from
`s06-battleship-hull-detail-2026-10-16`; that revision is frozen by its recorded hash, so this module
exists for the roll-out instead of editing the approved file. New builders should import this module.

Every helper places detail **from the frame it sits on**: `surface()` interpolates the same
loft-section lists the hull is built from, so a panel line cannot float off a deck or sink into a
flank when a frame is retuned. Nothing here changes a silhouette: elements stand 0.4 to 4 world units
proud of the surface they sit on.

Detail must be large to be worth its triangles: in the shipped close camera a 12-triangle block is
about four pixels, so spend the budget on bold steps, trenches and machinery banks rather than
hairline seams.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alliance_common import mesh_object   # the builder's own mesh constructor, never a copy


def surface(sections, z):
    """Half width, deck height, keel height and chamfer of a loft frame at z."""
    if z <= sections[0][0]:
        k, t = 0, 0.
    elif z >= sections[-1][0]:
        k, t = len(sections) - 2, 1.
    else:
        k = next(i for i in range(len(sections) - 1) if sections[i][0] <= z < sections[i + 1][0])
        t = (z - sections[k][0]) / (sections[k + 1][0] - sections[k][0])
    z0, w0, t0, b0 = sections[k]
    z1, w1, t1, b1 = sections[k + 1]
    lerp = lambda a, b: a + (b - a) * t
    w, top, bottom = lerp(w0, w1), lerp(t0, t1), lerp(b0, b1)
    return w, top, bottom, min(w * .25, (top - bottom) * .28)


def panel(name, role, size, center):
    """A plain raised block: 8 shared vertices, 12 triangles, no evaluated bevel."""
    w, h, l = size
    x, y, z = center
    verts = [(x - w / 2, y - h / 2, z - l / 2), (x + w / 2, y - h / 2, z - l / 2),
             (x + w / 2, y + h / 2, z - l / 2), (x - w / 2, y + h / 2, z - l / 2),
             (x - w / 2, y - h / 2, z + l / 2), (x + w / 2, y - h / 2, z + l / 2),
             (x + w / 2, y + h / 2, z + l / 2), (x - w / 2, y + h / 2, z + l / 2)]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return mesh_object(name, role, verts, faces, 0)


def deck_seam(sections, name, z, span=1.2, role='dark', lift=.3, inset=1.0, x_offset=0):
    """A transverse panel line across the flat centre of a lofted deck."""
    w, top, _, c = surface(sections, z)
    panel(f'{name} {z} {x_offset}', role, (max(2 * (w - c) - 2 * inset, 1.), .5, span),
          (x_offset, top + lift, z))


def deck_strake(sections, name, lefts, z0, z1, steps=8, role='dark', lift=.3, inset=.9, x_offset=0):
    """A longitudinal panel line that follows the deck taper as short runs."""
    for i in range(steps):
        z = z0 + (z1 - z0) * (i + .5) / steps
        w, top, _, c = surface(sections, z)
        for left in lefts:
            panel(f'{name} {left} {round(z, 2)} {x_offset}', role, (1., .5, abs(z1 - z0) / steps * .92),
                  (x_offset + left * (w - c - inset), top + lift, z))


def deck_panel(sections, name, z0, z1, left, width, role='trim', lift=1.1, inset=1.2, x_offset=0):
    """A raised armour panel; its own edge is the highlight line the eye reads."""
    z = (z0 + z1) / 2
    w, top, _, c = surface(sections, z)
    panel(f'{name} {round(z, 2)} {x_offset}', role, (max(2 * width * (w - c - inset), 1.), lift, abs(z0 - z1) * .9),
          (x_offset + left * (w - c - inset), top + lift / 2, z))


def flank_detail(sections, name, side, spec, x_offset=0, x_limit=None):
    """spec = (z, height, length, role, out, yfrac): a block standing proud of a flank.

    `yfrac` 0 sits on the keel chamfer, 1 on the deck chamfer, so a bank cannot overhang either.
    `x_limit` is the absolute half-width the model has already declared: detail may fill that
    envelope, never widen it, so a bank is clipped to the room left and skipped if there is none.
    A model's bounding box is its in-game scale, which is not the detail pass's to change.
    """
    for z, height, length, role, out, yfrac in spec:
        w, top, bottom, c = surface(sections, z)
        if x_limit is not None:
            room = x_limit - abs(x_offset) - w + .2
            if room < .35:
                continue
            out = min(out, room)
        lo, hi = bottom + c, top - c
        y = lo + (hi - lo) * yfrac
        panel(f'{name} {side} {z}', role, (out, height, length), (x_offset + side * (w + out * .5 - .2), y, z))


def louvre_bank(sections, name, side, z, rows=5, pitch=2.0, tall=5.5, length=6.5, role='trim', x_offset=0):
    """Vent louvres: a dark recess with bright blades across it."""
    w, top, bottom, c = surface(sections, z)
    y = (top + bottom) / 2
    panel(f'{name} recess {side} {z}', 'dark', (.55, tall + .8, length + 1.2),
          (x_offset + side * (w + .2), y, z))
    for i in range(rows):
        panel(f'{name} blade {side} {z} {i}', role, (.95, 1., length),
              (x_offset + side * (w + .45), y - tall / 2 + i * pitch, z))
