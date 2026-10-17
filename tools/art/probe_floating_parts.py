#!/usr/bin/env python3
"""Which named parts of a station master are not touching anything else?

A station kit is authored as separate solids, so "attached" means *touching or overlapping*
another part. A part a hair outside its neighbour on a shared face is fine; a part that is
nowhere near anything is floating in space, and at the review camera's ~5 px per world unit a
1.4-unit gap is 7 px of daylight - and the S06 B3b legion sensor station shipped a ring 24
units clear of its body, which is 120 px of daylight in its own capture.

Reports per master, in the master's own object names, so the fix lands in the seed's part
rather than in the exported mesh.

    Blender --background --python tools/art/probe_floating_parts.py -- <master.blend> ...
    Blender --background --python tools/art/probe_floating_parts.py -- --all
    Blender --background --python tools/art/probe_floating_parts.py -- --all --tolerance 0.25

`--tolerance` is the largest daylight that still counts as fitted; the seed's weld pass uses
0.25 and the batch guards measure the exported meshes at the same number, so 0.25 is the figure
that answers "what would the weld pass touch".
"""
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
TOLERANCE = 0.5  # world units; a shared face is 0, a bevel hair is < 0.01


def master_paths(argv):
    if '--all' in argv:
        names = [p.stem for p in sorted((ROOT / 'art/blender').glob('*.blend'))]
        return [(n, ROOT / 'art/blender' / f'{n}.blend') for n in names if '_station' in n or '_relay' in n]
    return [(Path(a).stem, Path(a)) for a in argv if a.endswith('.blend')]


def boxes():
    out = {}
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        corners = [obj.matrix_world @ v.co for v in obj.data.vertices]
        out[obj.name] = (
            tuple(min(c[i] for c in corners) for i in range(3)),
            tuple(max(c[i] for c in corners) for i in range(3)),
        )
    return out


def gap(a, b):
    return max(max(a[0][i] - b[1][i], b[0][i] - a[1][i]) for i in range(3))


def main():
    global TOLERANCE
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if '--tolerance' in argv:
        TOLERANCE = float(argv[argv.index('--tolerance') + 1])
        argv = [a for a in argv if a != '--tolerance' and a != str(TOLERANCE)]
    paths = master_paths(argv)
    if not paths:
        print('FLOAT no master given')
        return
    total = 0
    for name, path in paths:
        if not path.is_file():
            print(f'FLOAT {name} MISSING {path}')
            continue
        bpy.ops.wm.open_mainfile(filepath=str(path))
        parts = boxes()
        floating = []
        for label, box in parts.items():
            nearest = min((gap(box, other) for key, other in parts.items() if key != label),
                          default=0.0)
            if nearest > TOLERANCE:
                centre = tuple(round((box[0][i] + box[1][i]) / 2, 2) for i in range(3))
                floating.append((round(nearest, 2), label, centre))
        total += len(floating)
        print(f'FLOAT {name} parts={len(parts)} floating={len(floating)}')
        for nearest, label, centre in sorted(floating, reverse=True):
            print(f'  {nearest:8.2f} from everything else: {label}  centre={list(centre)}')
    print(f'FLOAT TOTAL floating parts across {len(paths)} masters: {total}')


main()
