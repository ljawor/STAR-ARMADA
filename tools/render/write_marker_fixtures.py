"""Fixtures for the C++ side of the W05 slice-2 cue batch.

The bytes are written by the Python encoder, so `test_markers.cpp` is checking cross-language
agreement rather than a restatement of the format. The damaged variants exist because a cue batch
that half-decodes would paint a ring around a unit that is not selected.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from render_bridge import markers as codec


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    records = [
        codec.circle((100.0, -20.0, 30.0), 135.0, (0.2, 0.8, 0.3), width=2.0, segments=28,
                     alpha=0.9, depth=False),
        codec.circle((-400.0, 0.0, 900.0), 720.0, (0.9, 0.2, 0.2), width=3.0, segments=40,
                     alpha=1.0, depth=True),
        codec.marker((12.0, 5.0, -7.0), 40.0, (1.0, 0.34, 0.12), hostile=True),
    ]
    good = codec.encode(records)
    (args.out / 'cues.bin').write_bytes(good)

    flipped = bytearray(good)
    flipped[-1] ^= 0xFF
    (args.out / 'bad-crc.bin').write_bytes(bytes(flipped))
    (args.out / 'bad-magic.bin').write_bytes(b'ARMARK99' + good[8:])
    (args.out / 'truncated.bin').write_bytes(good[:-5])
    count = bytearray(good)
    count[10:12] = (len(records) + 1).to_bytes(2, 'little')
    (args.out / 'bad-count.bin').write_bytes(bytes(count))
    reserved = bytearray(good)
    reserved[codec.HEADER.size + 30] = 1
    (args.out / 'reserved.bin').write_bytes(bytes(reserved))
    print(f'wrote {len(records)} primitives ({len(good)} bytes) and 5 damaged variants to {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
