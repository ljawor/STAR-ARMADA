"""Publish the surface-hardware meshes the window cannot find in its own catalogue.

A planet building is created during a match; the offline snapshot only names assets of entities
already on the map, so the window has no binding for it. Each kind for each faction the session can
field is published into a ring the viewer drains with `--mesh-ring`, one blob per binding, exactly
as a live producer sends them.

The geometry is the authored catalogue's, read through `render.asset_selection.mesh_for` - the same
call `fleet_geometry.station_mesh` makes - so the window draws the mesh Python draws rather than a
second copy of the same design. `tools/render/hardware_scene.py` owns the catalogue walk and the
encode; this tool is the command line over it, so a fixture can be regenerated without a match.

Run: PYTHONPATH=. .venv/bin/python tools/render/write_hardware_fixtures.py --out DIR
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from tools.render import hardware_scene                      # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--ring', default='hardware.ring')
    parser.add_argument('--only', action='append', metavar='FACTION:KIND',
                        help='publish only these bindings (the test fixture keeps the ring small)')
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    report = hardware_scene.publish(os.path.join(args.out, args.ring), only=args.only)

    # The C++ test reads bare blobs; the viewer reads the ring. Both come from the same encode.
    from render_bridge import hardware                       # noqa: E402
    available = hardware_scene.meshes()
    for name in sorted(args.only or report['bindings']):
        mesh = available.get(name)
        if mesh is None:
            continue
        with open(os.path.join(args.out, name.replace(':', '_') + '.bin'), 'wb') as handle:
            handle.write(hardware.encode(name, mesh))

    report.update({
        'synthetic': False,
        'source': 'approved asset catalogue (render.asset_selection.mesh_for)',
        'ring': os.path.join(args.out, args.ring),
        'note': 'one blob per binding: the window cannot read the asset catalogue for a mesh that '
                'only exists after a match starts',
    })
    with open(os.path.join(args.out, 'hardware.json'), 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    print(json.dumps({'bindings': len(report['bindings']),
                      'largest_blob_bytes': report['largest_blob_bytes']}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
