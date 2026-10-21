"""Write the C++ fixture for the W05 contact port: a bare record blob and a published ring.

The records come from the real builder (`render/emissive_batch.py::hits`) fed by the shared scene in
`tools/render/hit_scene.py`, so the fixture is what the producer would actually publish, not a
hand-assembled batch. Both the blob (for `test_hit`/decoder tests) and the ring (for the viewer) are
written from one encode, so they cannot drift.

Run: PYTHONPATH=. .venv/bin/python tools/render/write_hit_fixtures.py --out DIR
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from render import emissive_batch                     # noqa: E402
from render_bridge import emissive as codec           # noqa: E402
from tools.render import hit_scene                    # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    records, skipped = emissive_batch.hits(hit_scene.effects())
    if len(records) != len(hit_scene.CONTACTS) or skipped:
        raise SystemExit(f'expected {len(hit_scene.CONTACTS)} contacts, got {len(records)} '
                         f'({skipped} skipped)')
    blob = bytes(codec.encode(records))

    blob_path = os.path.join(args.out, 'hits.bin')
    with open(blob_path, 'wb') as handle:
        handle.write(blob)

    # A published batch carries no slot framing of its own; the ring does. Slot size leaves room for
    # the trailer the shared ring reserves (see render_bridge/ring.py::SLOT_TRAILER).
    from render_bridge import ring
    ring_path = os.path.join(args.out, 'hits.ring')
    slot_bytes = max(1024, len(blob) + 64)
    handle = ring.Ring.create(ring_path, slots=4, slot_bytes=slot_bytes)
    handle.publish(blob)

    report = {
        'records': len(records),
        'bytes': len(blob),
        'kinds': [record['kind'] for record in records],
        'ages': [round(record['width'], 3) for record in records],
        'seeds': [record['segments'] for record in records],
        'blob': blob_path,
        'ring': ring_path,
        'note': 'written by render/emissive_batch.py::hits over tools/render/hit_scene.py',
    }
    with open(os.path.join(args.out, 'hits.json'), 'w', encoding='utf-8') as out:
        json.dump(report, out, indent=2, sort_keys=True)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
