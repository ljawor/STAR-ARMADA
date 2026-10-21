"""ARMEMIT1: emissive primitives — weapon fire, beams, glows and jump rings.

Effects are emissive: they must not be lit, they blend additively, and they leave the depth buffer
alone. The Python renderer builds them from the state (`_draw_projectiles`, `_draw_effects`) and the
window cannot infer any of them, so the *decisions and the shapes* cross as primitives:

    header  <8sHHII   20 B   magic "ARMEMIT1", version, count (<=4096), reserved, crc32
    record  <BBH4B3f3fffHH  44 B
              kind B     RIBBON 1 | DISC 2 | RING 3 | BOLT 4 | EXPLOSION 5 | SHIELD 6
              shape B    RIBBON: 0 camera-facing | 1 flat
                         DISC/RING: 0 billboard | 1 flat (ecliptic)
                         BOLT: 0 elongated along its axis | 1 square
              flags H    bit0 depth test, bit1 additive blend
              colour 4B  rgba
              a 3f       RIBBON start | DISC/RING centre | BOLT position
              b 3f       RIBBON end   | unused            | BOLT heading (unit)
              radius f   DISC/RING world radius | BOLT half-length in pixels
              width f    RIBBON half-width in world units | RING stroke half-width | BOLT half-width
                         in pixels
              segments H DISC fan segments (0 = 24) | RING segments (0 = 32)
                         EXPLOSION seed (the blast's own deterministic hash input)
              reserved H must be 0

    A SHIELD record reuses the same fields: `a` is the shell centre, `radius` the shell's world
    radius, `width` the shield fraction (0..1, the decision the side panel also shows) and `colour`
    the tint the renderer derives from that fraction plus the fade alpha. The window builds the
    shell from the tint and its own camera; it does not re-derive how damaged a unit is.

Two units appear here on purpose. A beam is a world-sized ribbon: its width is part of how a
capital ship's fire reads at any zoom. A bolt is screen-sized: the Python renderer derives its
extents from `px_per_world` at its own camera, and in live mode the window owns the camera, so the
window converts the pixel extents at its own depth. Carrying Python's world size across would make
a bolt change size when the player zoomed.
"""
from __future__ import annotations

import struct
import zlib

MAGIC = b'ARMEMIT1'          # eight bytes: the header packs an 8s
VERSION = 1
HEADER = struct.Struct('<8sHHII')
RECORD = struct.Struct('<BBH4B3f3fffHH')
RECORD_BYTES = RECORD.size          # 44
MAX_RECORDS = 4096

RIBBON = 1
DISC = 2
RING = 3
BOLT = 4
EXPLOSION = 5                      # a blast carried as parameters, rebuilt by the window
SHIELD = 6                         # a standing shield shell: centre, radius, strength, tint

SHAPE_CAMERA = 0                   # camera-facing billboard
SHAPE_FLAT = 1                     # lying in the ecliptic
SHAPE_ELONGATED = 0                # bolt stretched along its heading
SHAPE_SQUARE = 1                   # bolt drawn as a square

FLAG_DEPTH = 0x01
FLAG_ADDITIVE = 0x02

DEFAULT_DISC_SEGMENTS = 24
DEFAULT_RING_SEGMENTS = 32


class EmissiveError(ValueError):
    """A batch that cannot be trusted."""


def _byte(value: float) -> int:
    return max(0, min(255, int(round(float(value) * 255.0))))


def _record(kind, shape, colour, a, b=(0.0, 0.0, 0.0), radius=0.0, width=0.0,
            segments=0, depth=False, additive=True) -> dict:
    alpha = float(colour[3]) if len(colour) == 4 else 1.0
    return {
        'kind': kind,
        'shape': shape,
        'flags': (FLAG_DEPTH if depth else 0) | (FLAG_ADDITIVE if additive else 0),
        'colour': (_byte(colour[0]), _byte(colour[1]), _byte(colour[2]), _byte(alpha)),
        'a': tuple(float(v) for v in a),
        'b': tuple(float(v) for v in b),
        'radius': float(radius),
        'width': float(width),
        'segments': int(segments),
    }


def ribbon(a, b, half_width, colour, *, flat=False, depth=False) -> dict:
    """A beam or tracer: a quad from `a` to `b`, half-width in world units."""
    return _record(RIBBON, SHAPE_FLAT if flat else SHAPE_CAMERA, colour, a, b,
                   width=half_width, depth=depth)


def disc(centre, radius, colour, *, segments=DEFAULT_DISC_SEGMENTS, flat=False, depth=False,
         additive=True) -> dict:
    """A glow: a fan whose centre is opaque and whose rim is transparent."""
    return _record(DISC, SHAPE_FLAT if flat else SHAPE_CAMERA, colour, centre,
                   radius=radius, segments=segments, depth=depth, additive=additive)


def ring(centre, radius, half_width, colour, *, segments=DEFAULT_RING_SEGMENTS, flat=True,
         depth=False) -> dict:
    """A jump-charge / arrival ring: a stroke in world units, not a filled disc."""
    return _record(RING, SHAPE_FLAT if flat else SHAPE_CAMERA, colour, centre,
                   radius=radius, width=half_width, segments=segments, depth=depth)


def bolt(position, heading, half_length_px, half_width_px, colour, *, square=False) -> dict:
    """A projectile: pixel extents, converted to world size by the window's own camera."""
    return _record(BOLT, SHAPE_SQUARE if square else SHAPE_ELONGATED, colour, position, heading,
                   radius=half_length_px, width=half_width_px)


def explosion(centre, size, age, seed, colour=(1.0, 1.0, 1.0, 1.0)) -> dict:
    """A detonation as parameters: position, size, age and seed.

    The blast is ~40 irregular shells and several thousand vertices, all derived from `age` and
    `seed` - so the parameters cross and the window rebuilds the same layers with the same
    formulas (`render/renderer.py::_draw_explosion`). Sending the geometry instead would dwarf the
    frame ring for one visual effect.
    """
    return _record(EXPLOSION, SHAPE_CAMERA, colour, centre, radius=float(size), width=float(age),
                   segments=int(seed) & 0xFFFF, depth=False, additive=False)


def shield(centre, radius, fraction, tint) -> dict:
    """A standing shield shell: where it is, how big it is, how strong it is, what colour that is.

    `fraction` and `tint` are the renderer's decisions (the strength ramp that tells the player how
    much shield is left). The shell's rim falloff is presentation and is rebuilt by the window at
    its own camera, exactly like the marker footprint in slice 2.
    """
    return _record(SHIELD, SHAPE_CAMERA, tint, centre, radius=float(radius),
                   width=float(fraction), segments=0, depth=True, additive=True)


def encode(records) -> bytes:
    records = list(records)
    if len(records) > MAX_RECORDS:
        raise EmissiveError(f'{len(records)} primitives exceeds the {MAX_RECORDS} ceiling')
    body = bytearray()
    for record in records:
        kind = int(record['kind'])
        if kind not in (RIBBON, DISC, RING, BOLT, EXPLOSION, SHIELD):
            raise EmissiveError(f'unknown emissive kind {kind}')
        body += RECORD.pack(kind, int(record['shape']), int(record['flags']),
                            *[int(v) for v in record['colour']],
                            *[float(v) for v in record['a']],
                            *[float(v) for v in record['b']],
                            float(record['radius']), float(record['width']),
                            int(record.get('segments', 0)), 0)
    return HEADER.pack(MAGIC, VERSION, len(records), 0, zlib.crc32(bytes(body)) & 0xFFFFFFFF) \
        + bytes(body)


def decode(data):
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise EmissiveError('batch must be bytes')
    if len(data) < HEADER.size:
        raise EmissiveError('batch shorter than the header')
    magic, version, count, reserved, crc = HEADER.unpack_from(data)
    if magic != MAGIC:
        raise EmissiveError('bad batch magic')
    if version != VERSION:
        raise EmissiveError(f'unsupported batch version {version}')
    if reserved:
        raise EmissiveError('reserved header field must be zero')
    if count > MAX_RECORDS:
        raise EmissiveError(f'{count} primitives exceeds the {MAX_RECORDS} ceiling')
    if len(data) != HEADER.size + count * RECORD_BYTES:
        raise EmissiveError(f'length {len(data)} does not match {count} records')
    body = bytes(data[HEADER.size:])
    if (zlib.crc32(body) & 0xFFFFFFFF) != crc:
        raise EmissiveError('batch crc mismatch')
    out = []
    for index in range(count):
        fields = RECORD.unpack_from(body, index * RECORD_BYTES)
        kind, shape, flags = fields[0], fields[1], fields[2]
        if kind not in (RIBBON, DISC, RING, BOLT, EXPLOSION, SHIELD):
            raise EmissiveError(f'record {index}: unknown kind {kind}')
        if fields[-1]:
            raise EmissiveError(f'record {index}: reserved field must be zero')
        out.append({'kind': kind, 'shape': shape, 'flags': flags,
                    'colour': tuple(fields[3:7]),
                    'a': tuple(fields[7:10]), 'b': tuple(fields[10:13]),
                    'radius': fields[13], 'width': fields[14],
                    'segments': fields[15]})
    return out
