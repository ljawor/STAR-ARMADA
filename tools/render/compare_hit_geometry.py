"""Compare the window's contact geometry with Python's, vertex for vertex.

The pixel comparison between the two renderers is limited by the camera-framing difference that
`docs/RENDER_W05_PLANES.md` records (``bx::mtxProj`` is handed degrees where it wants radians, so the
window's effective field of view is much wider). Contacts are a few pixels wide, so that difference
swamps a pixel measurement.

The port itself can still be checked exactly: both sides build the same contact from the same record,
so the triangles must agree to floating-point error. This script decodes the fixture batch, rebuilds
every record through the real `render.hit_effects.hit_geometry` with the same `px_per_world` and
camera basis the window uses, and diffs the result against `render_cpp/build-*/dump_hit_geometry`.

Run: PYTHONPATH=. .venv/bin/python tools/render/compare_hit_geometry.py \
        --batch FIXTURE/hits.bin --dumper render_cpp/build-w02/dump_hit_geometry
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from render.hit_effects import hit_geometry                 # noqa: E402
from render_bridge import emissive as codec                 # noqa: E402

SHELL_MIN_PX = 74.0
HULL_MIN_PX = 7.0
BASIS = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))


def python_geometry(records, px_per_world):
    """Python's own triangles, from the same records the window decodes."""
    out = []
    for record in records:
        shield = record['kind'] == codec.SHIELD_HIT
        size = min(18.0, max(1.0, record['shape'] / 10.0)) if shield else None
        fx = {'kind': 'shield_hit' if shield else 'hull_hit',
              'pos': record['a'], 'normal': record['b'], 't': record['width'],
              'seed': record['segments'], 'size': size if size is not None else 5.0}
        radius = None
        visual_size = None
        if shield:
            fx['center'] = record['a']
            fx['radius'] = record['radius']
            radius = max(record['radius'], SHELL_MIN_PX * 0.5 / px_per_world)
        else:
            visual_size = max(min(18.0, float(record['radius'])), HULL_MIN_PX / px_per_world)
        if record['flags'] & codec.FLAG_VISUAL_CONTACT:
            if shield:
                radius = record['radius']
            else:
                visual_size = min(visual_size, record['radius'])
        mesh = hit_geometry(fx, radius=radius, billboard_basis=BASIS, visual_size=visual_size)
        # Python vertices are ((x, y, z), (r, g, b, a)); the dumper prints the same seven numbers.
        out.extend(('T', tuple(v[0]) + tuple(v[1])) for v in mesh['triangles'])
        out.extend(('S', tuple(v[0]) + tuple(v[1])) for v in mesh.get('smoke', []))
    return out


def native_geometry(dumper, batch, px_per_world):
    text = subprocess.run([dumper, batch, f'{px_per_world}'], check=True, capture_output=True,
                          text=True).stdout
    out = []
    for line in text.splitlines():
        tag, *numbers = line.split()
        out.append((tag, tuple(float(value) for value in numbers)))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', required=True)
    parser.add_argument('--dumper', required=True)
    parser.add_argument('--px-per-world', type=float, default=1.54)
    parser.add_argument('--out')
    args = parser.parse_args()

    with open(args.batch, 'rb') as handle:
        records = codec.decode(handle.read())
    expected = python_geometry(records, args.px_per_world)
    got = native_geometry(args.dumper, args.batch, args.px_per_world)

    report = {'batch': args.batch, 'px_per_world': args.px_per_world,
              'records': len(records),
              'triangles': {'python': sum(1 for t, _ in expected if t == 'T'),
                            'native': sum(1 for t, _ in got if t == 'T')},
              'smoke': {'python': sum(1 for t, _ in expected if t == 'S'),
                        'native': sum(1 for t, _ in got if t == 'S')},
              'counts_match': len(expected) == len(got)}
    worst = 0.0
    where = None
    mismatches = 0
    for index, ((tag_a, values_a), (tag_b, values_b)) in enumerate(zip(expected, got)):
        if tag_a != tag_b or len(values_a) != len(values_b):
            mismatches += 1
            continue
        for component, (a, b) in enumerate(zip(values_a, values_b)):
            delta = abs(a - b)
            if delta > worst:
                worst, where = delta, {'vertex': index, 'component': component,
                                       'python': a, 'native': b}
    report['max_abs_delta'] = round(worst, 12)
    report['worst_component'] = where
    report['structural_mismatches'] = mismatches
    report['identical_to'] = ('exact' if worst == 0.0 else f'{worst:.3g} absolute')
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
    return 0 if report['counts_match'] and mismatches == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
