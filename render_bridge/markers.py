"""ARMARK01: the ownership cues and selection rings, carried as primitives.

The Python renderer draws three cheap things on top of the world that the window cannot infer:

  * the **selection ring** — a circle at the selected unit's own footprint radius, coloured by owner
    or by hull severity, tucked inside the shield bubble when there is one;
  * the **ownership marker** — a screen-clamped chevron (own/ally) or diamond (hostile) that keeps a
    constant pixel size at any zoom;
  * the **planet owner ring** — a circle at `radius + 120` in the colonist's colour.

All three are *decisions* (who is selected, who owns what, which relation, which severity), and the
rule from W02-W04 is that decisions stay in Python. What crosses is a batch of primitives:

    header  <8sHHII   20 B   magic, version, count (<=1024), reserved (must be 0), crc32(records)
    record  <BBH4B3ffHH   32 B
              kind B     CIRCLE 1 | MARKER 2
              shape B    circle: XZ 0 (horizontal) | XY 1 (vertical, stations/planets)
                         marker: CHEVRON 0 | DIAMOND 1
              flags H    bit0 depth test, bit1 alpha blend
              colour 4B  rgba
              centre 3f  world position
              size f     circle: world radius; marker: the hull's world radius, from which the
                         window derives the icon's pixel footprint with its own camera
              width f    line width in pixels (markers: 0)
              segments H circle: line segments (0 -> default 28)
              reserved H must be 0

A marker's hull radius crosses, not its pixel size: in live mode the window owns the camera, so it
applies `markers.marker_px` to its own apparent size. A footprint computed from Python's camera
would stop being screen-clamped the moment the player zoomed the window.
"""
from __future__ import annotations

import struct

MAGIC = b'ARMARK01'
VERSION = 1
HEADER = struct.Struct('<8sHHII')
RECORD = struct.Struct('<BBH4B3fffHH')
RECORD_BYTES = RECORD.size          # 32
MAX_RECORDS = 1024

CIRCLE = 1
MARKER = 2

SHAPE_XZ = 0                        # circle lying flat in the ecliptic
SHAPE_XY = 1                        # circle standing up (stations, planet markers)
SHAPE_CHEVRON = 0
SHAPE_DIAMOND = 1

FLAG_DEPTH = 0x01                   # depth test on (planet rings); cues are on top
FLAG_BLEND = 0x02                   # alpha blend

DEFAULT_SEGMENTS = 28


class MarkerError(ValueError):
    """A batch that cannot be trusted."""


def _byte(value: float) -> int:
    return max(0, min(255, int(round(float(value) * 255.0))))


def circle(centre, radius, colour, *, vertical=False, width=2.0, segments=DEFAULT_SEGMENTS,
           alpha=0.9, depth=False):
    """One selection or ownership ring."""
    c = list(colour) + [alpha] if len(colour) == 3 else list(colour)
    return {
        'kind': CIRCLE,
        'shape': SHAPE_XY if vertical else SHAPE_XZ,
        'flags': (FLAG_DEPTH if depth else 0) | (FLAG_BLEND if c[3] < 1.0 else 0),
        'colour': (_byte(c[0]), _byte(c[1]), _byte(c[2]), _byte(c[3])),
        'centre': (float(centre[0]), float(centre[1]), float(centre[2])),
        'size': float(radius),
        'width': float(width),
        'segments': int(segments),
    }


def marker(centre, px, colour, *, hostile=False, alpha=0.95):
    """One ownership marker: a chevron for own/ally/neutral, a diamond for hostiles."""
    c = list(colour) + [alpha] if len(colour) == 3 else list(colour)
    return {
        'kind': MARKER,
        'shape': SHAPE_DIAMOND if hostile else SHAPE_CHEVRON,
        'flags': FLAG_BLEND if c[3] < 1.0 else 0,
        'colour': (_byte(c[0]), _byte(c[1]), _byte(c[2]), _byte(c[3])),
        'centre': (float(centre[0]), float(centre[1]), float(centre[2])),
        'size': float(px),
        'width': 0.0,
        'segments': 0,
    }


def encode(records):
    """Pack primitives into one batch. A batch that cannot be trusted is refused whole."""
    records = list(records)
    if len(records) > MAX_RECORDS:
        raise MarkerError(f'{len(records)} primitives exceeds the {MAX_RECORDS} ceiling')
    body = bytearray()
    for record in records:
        kind = int(record['kind'])
        if kind not in (CIRCLE, MARKER):
            raise MarkerError(f'unknown primitive kind {kind}')
        body += RECORD.pack(kind, int(record['shape']), int(record['flags']),
                            *[int(v) for v in record['colour']],
                            *[float(v) for v in record['centre']],
                            float(record['size']), float(record['width']),
                            int(record.get('segments', 0)), 0)
    return HEADER.pack(MAGIC, VERSION, len(records), 0, _crc32(bytes(body))) + bytes(body)


def decode(data):
    """Validate and unpack one batch. Fails closed; never guesses."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise MarkerError('batch must be bytes')
    if len(data) < HEADER.size:
        raise MarkerError('batch shorter than the header')
    magic, version, count, reserved, crc = HEADER.unpack_from(data)
    if magic != MAGIC:
        raise MarkerError('bad batch magic')
    if version != VERSION:
        raise MarkerError(f'unsupported batch version {version}')
    if reserved:
        raise MarkerError('reserved header field must be zero')
    if count > MAX_RECORDS:
        raise MarkerError(f'{count} primitives exceeds the {MAX_RECORDS} ceiling')
    expected = HEADER.size + count * RECORD_BYTES
    if len(data) != expected:
        raise MarkerError(f'length {len(data)} does not match {count} records')
    body = bytes(data[HEADER.size:])
    if _crc32(body) != crc:
        raise MarkerError('batch crc mismatch')
    out = []
    for index in range(count):
        kind, shape, flags, r, g, b, a, x, y, z, size, width, segments, pad = \
            RECORD.unpack_from(body, index * RECORD_BYTES)
        if kind not in (CIRCLE, MARKER):
            raise MarkerError(f'record {index}: unknown kind {kind}')
        if pad:
            raise MarkerError(f'record {index}: reserved field must be zero')
        out.append({'kind': kind, 'shape': shape, 'flags': flags,
                    'colour': (r, g, b, a), 'centre': (x, y, z),
                    'size': size, 'width': width, 'segments': segments})
    return out


def _crc32(data: bytes) -> int:
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF
