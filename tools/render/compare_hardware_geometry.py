"""Compare the vertices the window decodes with the vertices the renderer draws.

A triangle count proves nothing about a silhouette: a mesh can carry the right number of triangles
in the wrong order and still draw a building. This diffs the two rebuilds - Python's
`station_mesh()` output against the C++ decoder's output for the same published blob - vertex for
vertex, the way `compare_hit_geometry.py` diffs a damage contact.

The dump comes from `test_hardware --dump`, so the comparison runs against the same decoder the
viewer uses, not a second reader written for the test.

Run: PYTHONPATH=. .venv/bin/python tools/render/compare_hardware_geometry.py \
        --dump /tmp/hardware.dump --blob DIR/imperial_planet_extractor.bin
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

# The order the wire uses; the decoder appends blocks in this order, so the comparison does too.
ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')


def expected(name: str, blob_path: str) -> list:
    """Python's own rebuild of the same mesh, in wire order, read back out of the blob's blocks."""
    from render_bridge import hardware
    from tools.render import hardware_scene

    with open(blob_path, 'rb') as handle:
        blob = handle.read()
    decoded = hardware.decode(blob)
    # `hardware_scene.meshes()` is the mesh Python draws - the authored catalogue read through
    # `asset_selection.mesh_for`, with the asset selection configured. Calling `station_mesh`
    # without that configuration silently returns the procedural fallback (832 triangles), which
    # is how a comparison ends up measuring the wrong building.
    mesh = hardware_scene.meshes().get(name)
    if mesh is None:
        raise SystemExit(f'no Python mesh for {name!r}')
    rows = []
    for role in ROLES:
        for normal, vertices in mesh.get(role, ()):
            for vertex in vertices:
                rows.append((float(vertex[0]), float(vertex[1]), float(vertex[2]),
                             float(normal[0]), float(normal[1]), float(normal[2])))
    if decoded['name'] != name:
        raise SystemExit(f'blob names {decoded["name"]!r}, expected {name!r}')
    return rows


def read_dump(path: str) -> tuple:
    binding, triangles, rows = None, None, []
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            if line.startswith('binding '):
                binding = line.split(' ', 1)[1].strip()
            elif line.startswith('triangles '):
                triangles = int(line.split()[1])
            elif line.startswith('V '):
                rows.append(tuple(float(v) for v in line.split()[1:7]))
    return binding, triangles, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dump', required=True, help='output of test_hardware --dump')
    parser.add_argument('--blob', required=True)
    parser.add_argument('--out')
    args = parser.parse_args()

    binding, triangles, native = read_dump(args.dump)
    if binding is None:
        raise SystemExit('the dump carries no binding')
    rows = expected(binding, args.blob)

    worst, worst_at, mismatches = 0.0, -1, 0
    structural = []
    if len(rows) != len(native):
        structural.append({'kind': 'vertex_count', 'python': len(rows), 'native': len(native)})
    for index, (a, b) in enumerate(zip(rows, native)):
        delta = max(abs(a[c] - b[c]) for c in range(6))
        if delta > worst:
            worst, worst_at = delta, index
        if delta > 1e-5:
            mismatches += 1
            if len(structural) < 10:
                structural.append({'kind': 'vertex', 'index': index,
                                   'python': list(a), 'native': list(b), 'delta': delta})

    report = {
        'binding': binding,
        'triangles': triangles,
        'triangles_python': len(rows) // 3,
        'vertices': len(native),
        'vertices_python': len(rows),
        'mismatches': mismatches,
        'worst_delta': worst,
        'worst_vertex': worst_at,
        'examples': structural,
        'note': 'same decoder the viewer uses (test_hardware --dump) against the mesh the renderer '
                'draws; positions and face normals, in wire order',
    }
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
    print(json.dumps({k: report[k] for k in ('binding', 'triangles', 'vertices', 'mismatches',
                                             'worst_delta')}, sort_keys=True))
    return 0 if (not structural and mismatches == 0) else 1


if __name__ == '__main__':
    raise SystemExit(main())
