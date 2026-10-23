"""Render an accepted .blend with the same review camera as the Syndicate batch.

Read-only: opens the file, assigns the review-still materials by role, renders
three views. Used only to put a candidate still beside an accepted Imperium
still on one sheet, so the comparison is like for like.

    Blender --background --python tools/art/render_review_still.py -- \
        art/blender/imperial_battleship.blend out/dir name
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from tools.art.build_syndicate_imperium import render_still  # noqa: E402


def bounds():
    pts = []
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
            for corner in obj.bound_box:
                pts.append(obj.matrix_world @ Vector(corner))
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return lo, hi


def main():
    argv = sys.argv[sys.argv.index('--') + 1:]
    blend, out_dir, name = Path(argv[0]), Path(argv[1]), argv[2]
    bpy.ops.wm.open_mainfile(filepath=str(blend.resolve()))
    lo, hi = bounds()
    out_dir.mkdir(parents=True, exist_ok=True)
    span = hi[2] - lo[2]
    # The object sits where its author placed it; frame about its own middle.
    centre = [(a + b) / 2 for a, b in zip(lo, hi)]
    for suffix, yaw, pitch, factor in (('quarter', 38., 22., 2.0),
                                       ('profile', 90., 6., 1.9),
                                       ('bow', 8., 12., 1.6)):
        render_still(out_dir / f'{name}-{suffix}.png', look_at=centre,
                     distance=span * factor, yaw=yaw, pitch=pitch)
    print('REVIEW_STILL_OK', name, [round(v, 2) for v in lo],
          [round(v, 2) for v in hi], flush=True)


if __name__ == '__main__':
    main()
