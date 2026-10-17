#!/usr/bin/env python3
"""Measure the evaluated bounds of editable masters and name the parts that set them.

The export wrapper asserts each mesh inside its binding's legacy envelope, but it asserts
only after a full evaluation - by which time the failing axis is one number with no clue
which primitive overran. This prints the same evaluated bounds the exporter would see and
the parts that reach furthest in each direction, so a fix is arithmetic instead of a
guessing loop. `loft`/`plate` carry a bevel modifier, so the evaluated surface stands proud
of the section values the builder declares; always size against these numbers.

    Blender --background --python-exit-code 1 --python tools/art/probe_master_bounds.py -- <identifier> ...
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AXES = 'XYZ'


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if not argv:
        raise SystemExit('usage: -- <identifier> [<identifier> ...]')
    import bpy
    for identifier in argv:
        path = ROOT / f'art/blender/{identifier}.blend'
        bpy.ops.wm.open_mainfile(filepath=str(path))
        depsgraph = bpy.context.evaluated_depsgraph_get()
        lo = [None] * 3
        hi = [None] * 3
        reach = [{} for _ in range(3)]
        for obj in bpy.context.scene.objects:
            if obj.type != 'MESH':
                continue
            mesh = obj.evaluated_get(depsgraph).to_mesh()
            for vertex in mesh.vertices:
                point = obj.matrix_world @ vertex.co
                for axis in range(3):
                    value = float(point[axis])
                    if lo[axis] is None or value < lo[axis]:
                        lo[axis] = value
                        reach[axis][-1] = obj.name
                    if hi[axis] is None or value > hi[axis]:
                        hi[axis] = value
                        reach[axis][1] = obj.name
            obj.evaluated_get(depsgraph).to_mesh_clear()
        span = hi[2] - lo[2]
        print(f'BOUNDS {identifier} lo={[round(v, 3) for v in lo]} hi={[round(v, 3) for v in hi]} z_span={span:.3f}')
        for axis in range(3):
            print(f'  {AXES[axis]} min {lo[axis]:9.3f} <- {reach[axis][-1]}')
            print(f'  {AXES[axis]} max {hi[axis]:9.3f} <- {reach[axis][1]}')
        print(f'  parts={len([o for o in bpy.context.scene.objects if o.type == "MESH"])}')


main()
