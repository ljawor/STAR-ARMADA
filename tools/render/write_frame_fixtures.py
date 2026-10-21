"""Author the committed v2 frame fixtures the native consumer test decodes.

The native decoder test must decode bytes this Python producer wrote — a C++ test that
builds its own frames proves the C++ agrees with itself. Values here are chosen to be
exactly representable in float32 so the cross-language comparison is exact rather than
tolerance-shaped, apart from the tolerance the test states explicitly.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from render_bridge import packed

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'render_cpp' / 'tests' / 'fixtures'

MATRIX_A = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 10.0, 0.0, 5.0)
MATRIX_B = (0.0, 0.0, -2.0, 0.0, 2.0, 0.0, 2.0, 0.0, 0.0, -4.5, 0.0, 12.25)


def build():
    tables = packed.Tables.build(
        ['rebel:fighter', 'imperial:cruiser', 'neutral:station'],
        ['beam', 'explosion'])
    instances = [
        packed.instance_record(entity_id=7, binding_id=tables.bindings.index('rebel:fighter'),
                              matrix=MATRIX_A, tint=(1.0, 0.5, 0.25, 1.0), flags=packed.FLAG_SELECTED,
                              hp=1.0, shield=0.75),
        packed.instance_record(entity_id=9, binding_id=tables.bindings.index('imperial:cruiser'),
                              matrix=MATRIX_B, tint=(0.25, 0.5, 1.0, 1.0),
                              flags=packed.FLAG_DAMAGED | packed.FLAG_DISABLED,
                              hp=0.5, shield=0.0),
    ]
    effects = [
        packed.effect_record(cls=packed.EFFECT_CLASS, kind_id=tables.kinds.index('beam'),
                             position=(1.5, 2.5, 3.5), end_position=(4.5, 5.5, 6.5),
                             life=0.25, size=2.0, color=(1.0, 0.0, 0.0, 1.0)),
        packed.effect_record(cls=packed.PROJECTILE_CLASS, kind_id=tables.kinds.index('explosion'),
                             is_beam=True, position=(-1.0, 0.5, 0.0),
                             velocity=(0.25, 0.5, -0.75), end_position=(-1.0, 0.5, 0.0),
                             life=3.0, size=1.5, color=(0.0, 1.0, 0.5, 1.0)),
    ]
    buffer = bytearray(packed.frame_size(len(instances), len(effects)))
    frame = bytes(packed.pack_frame(buffer, tick=4242, frame_index=99, tables=tables,
                                    instances=instances, effects=effects, flags=1))
    expected = {
        'frame': {'tick': 4242, 'frame_index': 99, 'flags': 1,
                  'instances': len(instances), 'effects': len(effects)},
        'table': {'crc32': tables.crc32, 'bindings': list(tables.bindings),
                  'kinds': list(tables.kinds)},
        'instance_records': [
            {'entity_id': 7, 'binding': 'rebel:fighter', 'flags': packed.FLAG_SELECTED,
             'tint': [255, 128, 64, 255], 'matrix': list(MATRIX_A), 'hp': 1.0, 'shield': 0.75},
            {'entity_id': 9, 'binding': 'imperial:cruiser',
             'flags': packed.FLAG_DAMAGED | packed.FLAG_DISABLED,
             'tint': [64, 128, 255, 255], 'matrix': list(MATRIX_B), 'hp': 0.5, 'shield': 0.0},
        ],
        'transient_records': [
            {'class': packed.EFFECT_CLASS, 'is_beam': False, 'kind': 'beam',
             'position': [1.5, 2.5, 3.5], 'velocity': [0.0, 0.0, 0.0],
             'end_position': [4.5, 5.5, 6.5], 'life': 0.25, 'size': 2.0,
             'colour': [255, 0, 0, 255]},
            {'class': packed.PROJECTILE_CLASS, 'is_beam': True, 'kind': 'explosion',
             'position': [-1.0, 0.5, 0.0], 'velocity': [0.25, 0.5, -0.75],
             'end_position': [-1.0, 0.5, 0.0], 'life': 3.0, 'size': 1.5,
             'colour': [0, 255, 128, 255]},
        ],
        'sizes': {'header': packed.FRAME.size, 'instance': packed.INSTANCE.size,
                  'effect': packed.EFFECT.size, 'frame': len(frame)},
    }
    files = {
        'frame-v2.bin': frame,
        'tables-v2.bin': tables.encode(),
        'expected-v2.json': (json.dumps(expected, indent=2, sort_keys=True) + '\n').encode(),
    }
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='fail if the committed fixtures differ from what this script writes')
    parser.add_argument('--out', type=Path, default=FIXTURES)
    args = parser.parse_args(argv)
    files = build()
    args.out.mkdir(parents=True, exist_ok=True)
    drift = []
    for name, payload in files.items():
        target = args.out / name
        if args.check:
            if not target.exists() or target.read_bytes() != payload:
                drift.append(name)
        else:
            target.write_bytes(payload)
    if args.check:
        if drift:
            print(f'STALE: {", ".join(drift)}', file=sys.stderr)
            return 1
        print('FIXTURES_OK')
        return 0
    for name in files:
        print(f'{name}: {(args.out / name).stat().st_size} bytes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
