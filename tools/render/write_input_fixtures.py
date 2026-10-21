"""Write the input-batch fixtures both sides of the bridge are tested against.

The C++ window and the Python game each have their own encoder for `ARMINP01` batches. Two
encoders that merely "work" can still disagree, and the disagreement would only show up as a
dropped click in a live match, so the fixtures pin the bytes: the native test decodes these exact
files and re-encodes them, and the result has to match byte for byte.

    .venv/bin/python tools/render/write_input_fixtures.py --out /tmp/input-fixtures
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from render_bridge import input as wire   # noqa: E402

#: Deliberately mixed: a resize, a drag with a held button, a click, both wheel directions, a
#: letter with a modifier, an arrow, escape, a function key, focus loss and quit.
EVENTS = [
    wire.Event(wire.RESIZE, extra=(2560 << 16) | 1600),
    wire.Event(wire.MOTION, button=1, x=640, y=400),
    wire.Event(wire.MOTION, button=1, x=700, y=440),
    wire.Event(wire.BUTTON_DOWN, button=1, x=700, y=440),
    wire.Event(wire.BUTTON_UP, button=1, x=700, y=440),
    wire.Event(wire.WHEEL, button=1, x=512, y=300),
    wire.Event(wire.WHEEL, button=0, x=512, y=300),
    wire.Event(wire.KEY_DOWN, button=wire.MOD_SHIFT, code=ord('q')),
    wire.Event(wire.KEY_UP, button=wire.MOD_SHIFT, code=ord('q')),
    wire.Event(wire.KEY_DOWN, button=0, code=wire.KEYCODE_LEFT),
    wire.Event(wire.KEY_UP, button=0, code=wire.KEYCODE_LEFT),
    wire.Event(wire.KEY_DOWN, button=wire.MOD_CTRL, code=wire.KEYCODE_F1 + 4),
    wire.Event(wire.FOCUS_LOST),
    wire.Event(wire.QUIT),
]

MALFORMED = {
    'bad-magic.bin': lambda b: b'X' + b[1:],
    'bad-version.bin': lambda b: b[:8] + struct.pack('<H', 99) + b[10:],
    'reserved.bin': lambda b: b[:12] + struct.pack('<I', 1) + b[16:],
    'truncated.bin': lambda b: b[:-4],
    'trailing.bin': lambda b: b + b'\x00',
    'bad-crc.bin': lambda b: b[:-1] + bytes([b[-1] ^ 0xFF]),
    'unknown-kind.bin': lambda b: b[:20] + bytes([250]) + b[21:],
    'over-ceiling.bin': lambda b: b[:10] + struct.pack('<H', wire.MAX_RECORDS + 1) + b[12:],
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = wire.encode_batch(EVENTS)
    (out / 'input-batch.bin').write_bytes(payload)
    (out / 'input-expected.json').write_text(json.dumps({
        'magic': wire.MAGIC.decode(),
        'version': wire.VERSION,
        'header_bytes': wire.HEADER_BYTES,
        'record_bytes': wire.RECORD_BYTES,
        'bytes': len(payload),
        'crc32': struct.unpack_from('<I', payload, 16)[0],
        'events': [dict(zip(('kind', 'button', 'code', 'x', 'y', 'extra'), event.as_tuple()))
                   for event in EVENTS],
    }, indent=2) + '\n')
    for name, corrupt in MALFORMED.items():
        (out / name).write_bytes(corrupt(payload))

    # The control that makes the fixtures meaningful: decoding the good file gives back exactly
    # the events that were written.
    assert wire.decode_batch(payload) == EVENTS
    for name in MALFORMED:
        try:
            wire.decode_batch((out / name).read_bytes())
        except wire.InputError:
            continue
        raise SystemExit(f'{name} was accepted by the Python decoder')
    print(json.dumps({'out': str(out), 'bytes': len(payload), 'events': len(EVENTS),
                      'malformed': sorted(MALFORMED)}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
