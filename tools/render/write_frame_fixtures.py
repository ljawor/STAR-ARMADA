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

from render_bridge import overlay, packed

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


def build_overlay():
    """Overlay fixtures: the surface pixels are a deterministic pattern, so the native test can
    check both the rect list and the bytes without a GPU or a pygame dependency."""
    width, height = 8, 4

    def pixel(x, y):
        return bytes(((x * 16) & 0xFF, (y * 32) & 0xFF, ((x + y) * 7) & 0xFF, 255))

    surface = b''.join(pixel(x, y) for y in range(height) for x in range(width))
    full = overlay.encode(width, height, full=surface)

    rects = [(2, 1, 3, 2), (6, 0, 2, 3)]
    patches = []
    for x0, y0, w, h in rects:
        patches.append(b''.join(pixel(x, y) for y in range(y0, y0 + h) for x in range(x0, x0 + w)))
    patch_frame = overlay.encode(width, height, rects, patches)

    # Malformed variants: each must be refused by the native decoder for a different reason.
    bad_magic = b'XRMOVL01' + full[8:]
    bad_version = full[:8] + (2).to_bytes(2, 'little') + full[10:]
    bad_flags = full[:10] + (0x8).to_bytes(2, 'little') + full[12:]
    truncated = full[:-4]
    bad_crc = full[:-1] + bytes([full[-1] ^ 0xFF])
    rect_outside = overlay.encode(width, height, rects, patches)
    rect_outside = rect_outside[:28] + (7).to_bytes(2, 'little') + (0).to_bytes(2, 'little') + \
        rect_outside[32:]
    full_with_rects = (full[:16] + (1).to_bytes(2, 'little') + full[18:])
    count_too_high = patch_frame[:16] + (overlay.MAX_RECTS + 1).to_bytes(2, 'little') + patch_frame[18:]

    expected = {
        'full': {'width': width, 'height': height, 'full': True, 'rects': [],
                 'surface_crc32': __import__('zlib').crc32(surface) & 0xFFFFFFFF,
                 'frame_bytes': len(full)},
        'patch': {'width': width, 'height': height, 'full': False,
                  'rects': [list(r) for r in rects], 'frame_bytes': len(patch_frame),
                  'patch_bytes': sum(w * h * 4 for _, _, w, h in rects)},
        'sizes': {'header': overlay.HEADER_BYTES, 'rect': overlay.RECT_BYTES},
        'refusals': ['bad_magic', 'bad_version', 'bad_flags', 'truncated', 'bad_crc',
                     'rect_outside', 'full_with_rects', 'count_too_high'],
    }
    return {
        'overlay-full-v1.bin': full,
        'overlay-patch-v1.bin': patch_frame,
        'overlay-bad-magic.bin': bad_magic,
        'overlay-bad-version.bin': bad_version,
        'overlay-bad-flags.bin': bad_flags,
        'overlay-truncated.bin': truncated,
        'overlay-bad-crc.bin': bad_crc,
        'overlay-rect-outside.bin': rect_outside,
        'overlay-full-with-rects.bin': full_with_rects,
        'overlay-count-too-high.bin': count_too_high,
        'overlay-expected.json': (json.dumps(expected, indent=2, sort_keys=True) + '\n').encode(),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='fail if the committed fixtures differ from what this script writes')
    parser.add_argument('--out', type=Path, default=FIXTURES)
    args = parser.parse_args(argv)
    files = {**build(), **build_overlay()}
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
