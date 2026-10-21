"""Write the fog-mask fixtures the native decoder test reads.

The fixtures come from `render_bridge/fogmap.py` - the encoder that actually publishes the mask -
so the C++ test checks agreement with the producer rather than with a copy of the header layout.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from render_bridge import fogmap

CELLS = 6


def mask_pixels() -> bytes:
    """The three states the renderer writes, in a pattern that makes an off-by-one visible."""
    out = bytearray()
    for z in range(CELLS):
        for x in range(CELLS):
            if x == 0:                       # a visible column: alpha 0, no colour
                out += bytes((0, 0, 0, 0))
            elif (x + z) % 2 == 0:           # charted
                out += bytes((12, 22, 38, 155))
            else:                            # unexplored
                out += bytes((3, 6, 13, 255))
    return bytes(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path('render_cpp/tests/fixtures/fog'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    blob = fogmap.encode_blob(CELLS, 500.0, 3000.0, 9, mask_pixels())
    (args.out / 'skirmish.bin').write_bytes(blob)
    print(f'wrote {args.out / "skirmish.bin"} ({len(blob)} bytes)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
