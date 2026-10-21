"""W02 packed frame profile (v2). See docs/RENDER_BRIDGE_W02.md.

`protocol.py` stays the offline file profile: canonical JSON is the right shape for a
file nobody streams, and it is what the W00 approval binds. This module is the
frame-rate profile. The measured reason is in the W02 receipt: encoding the real
600-ship frame as v1 JSON costs ~8 ms of Python per frame, almost all of it decimal
text conversion for ~21,000 floats, against a 1.0 ms budget. Fixed-stride records
written with `struct.pack_into` into a buffer the caller owns cost ~0.6 ms and
allocate nothing in the steady state.

Two tables travel once per session, not per frame:

* bindings — approved mesh binding names, indexed by `u16` in every instance record;
* kinds — effect/projectile kind and weapon names, indexed by `u16`.

Both are content-hashed so a consumer can refuse frames packed against a table it
does not hold. Everything here is read-only with respect to simulation state: the
packer only reads numbers, and no function in this module touches `GameState`.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import struct
import zlib

MAGIC = b'ARMADAF2'
TABLE_MAGIC = b'ARMTBL2\0'
VERSION = 2

WORLD = 1
INSTANCE_CLASS = 1

# Effect records cover transient effects *and* projectiles: they share position,
# velocity, kind, life, size and colour, and are distinguished by `cls`.
EFFECT_CLASS = 2
PROJECTILE_CLASS = 3

FLAG_SELECTED = 1 << 0
FLAG_DAMAGED = 1 << 1
FLAG_DISABLED = 1 << 2

# <magic><version><kind><tick><frame><instances><effects><table_crc><flags><length><crc>
FRAME = struct.Struct('<8sHHIQIIIIII')
# <entity_id><binding_id><flags><tint rgba><matrix 3x4><hp><shield>
INSTANCE = struct.Struct('<IHH4B12f2f')
# <class><is_beam><kind_id><pos 3f><vel 3f><end 3f><life><size><rgba>
EFFECT = struct.Struct('<BBH3f3f3fff4B')
TABLE = struct.Struct('<8sHHI')

MAX_EFFECTS = 8_192
MAX_INSTANCES = 4_096
MAX_TABLE_BYTES = 1 << 20


@lru_cache(maxsize=16)
def table_body(bindings, kinds) -> bytes:
    """Serialized table body, cached because the per-frame path needs its CRC."""
    body = bytearray()
    for group in (bindings, kinds):
        for name in group:
            raw = name.encode('utf-8')
            if len(raw) > 0xFF:
                raise FrameError('table entry exceeds 255 bytes')
            body += bytes((len(raw),)) + raw
    if len(body) > MAX_TABLE_BYTES:
        raise FrameError('table exceeds 1 MiB')
    return bytes(body)


class FrameError(ValueError):
    """Malformed or unsupported v2 frame (native consumer exit code 3)."""


@dataclass(frozen=True)
class Tables:
    """The two string tables a consumer needs before it can decode a frame."""

    bindings: tuple[str, ...]
    kinds: tuple[str, ...]

    @staticmethod
    def build(bindings, kinds):
        bindings = tuple(sorted(set(bindings)))
        kinds = tuple(sorted(set(kinds)))
        if len(bindings) > 0xFFFF or len(kinds) > 0xFFFF:
            raise FrameError('table exceeds 65535 entries')
        for name in bindings + kinds:
            if not isinstance(name, str) or not name or '\x00' in name:
                raise FrameError('table entries must be non-empty NUL-free strings')
        return Tables(bindings, kinds)

    def encode(self) -> bytes:
        body = table_body(self.bindings, self.kinds)
        head = TABLE.pack(TABLE_MAGIC, VERSION, len(self.bindings), len(body))
        return head + body + struct.pack('<I', zlib.crc32(body))

    @property
    def crc32(self) -> int:
        # Cached: the table is constant for a session, and this is on the per-frame path.
        return zlib.crc32(table_body(self.bindings, self.kinds))

    @staticmethod
    def decode(raw) -> 'Tables':
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            raise FrameError('table must be bytes')
        if len(raw) < TABLE.size + 4:
            raise FrameError('truncated table')
        magic, version, count, length = TABLE.unpack_from(raw)
        if magic != TABLE_MAGIC or version != VERSION:
            raise FrameError('unknown table magic or version')
        if length > MAX_TABLE_BYTES or len(raw) != TABLE.size + length + 4:
            raise FrameError('invalid table length')
        body = bytes(raw[TABLE.size:TABLE.size + length])
        if struct.unpack_from('<I', raw, TABLE.size + length)[0] != zlib.crc32(body):
            raise FrameError('table CRC32 mismatch')
        names, offset = [], 0
        while offset < len(body):
            size = body[offset]
            offset += 1
            if size == 0 or offset + size > len(body):
                raise FrameError('malformed table entry')
            names.append(body[offset:offset + size].decode('utf-8'))
            offset += size
        if len(names) < count:
            raise FrameError('table shorter than its binding count')
        return Tables(tuple(names[:count]), tuple(names[count:]))


def frame_size(instances: int, effects: int) -> int:
    return FRAME.size + INSTANCE.size * instances + EFFECT.size * effects


def matrix_from_pose(position, yaw: float, scale: float) -> tuple[float, ...]:
    """3x4 column-major transform: Ry(yaw) scaled uniformly, then the translation.

    The twelve floats are the three columns

        (c, 0, -t)   (0, s, 0)   (t, 0, c)      then (px, py, pz)

    with c = cos(yaw)*scale, t = sin(yaw)*scale and s = scale. That is the W01 snapshot's
    20-float column-major instance transform with its constant 0/1 entries dropped, and it
    is the same rotation the live renderer performs with `glRotatef(yaw, 0, 1, 0)`.

    The middle column is the *vertical* axis. Writing the middle and last columns the
    other way round (which an earlier revision of this profile did) zeroes the vertical
    axis and skews every hull whose yaw is not a multiple of pi: perfectly valid bytes,
    perfectly wrong picture, and nothing in a decoder can tell.
    """
    c, s = math.cos(yaw), math.sin(yaw)
    return (c * scale, 0.0, -s * scale,
            0.0, scale, 0.0,
            s * scale, 0.0, c * scale,
            float(position[0]), float(position[1]), float(position[2]))


def channels(color) -> tuple[int, int, int, int]:
    """Clamp four 0..1 channels to bytes. Missing alpha is opaque."""
    values = tuple(color)[:4]
    if len(values) < 4:
        values += (1.0,) * (4 - len(values))
    return tuple(max(0, min(255, int(round(value * 255)))) for value in values)


def tint_bytes(color):
    """Owner tint as the four bytes an instance record carries."""
    return channels(color)


def instance_record(*, entity_id, binding_id, matrix, tint, flags=0, hp=1.0, shield=1.0):
    if not 0 <= binding_id <= 0xFFFF:
        raise FrameError('binding_id must be uint16')
    if len(matrix) != 12:
        raise FrameError('matrix must be 12 floats (3x4)')
    for value in matrix:
        if not math.isfinite(value):
            raise FrameError('non-finite matrix element')
    rgba = bytes(max(0, min(255, int(round(channel * 255)))) for channel in tint[:4])
    if len(rgba) != 4:
        raise FrameError('tint must have four channels')
    return (int(entity_id), int(binding_id), int(flags), *rgba, *matrix,
            float(hp), float(shield))


def effect_record(*, cls, kind_id, position, velocity=(0.0, 0.0, 0.0),
                  end_position=None, life=0.0, size=1.0, color=(1.0, 1.0, 1.0, 1.0),
                  is_beam=False):
    if cls not in (EFFECT_CLASS, PROJECTILE_CLASS):
        raise FrameError('unknown effect class')
    if not 0 <= kind_id <= 0xFFFF:
        raise FrameError('kind_id must be uint16')
    end = end_position if end_position is not None else position
    numbers = (*position, *velocity, *end, float(life), float(size))
    if not all(math.isfinite(value) for value in numbers):
        raise FrameError('non-finite effect element')
    rgba = bytes(max(0, min(255, int(round(channel * 255)))) for channel in color[:4])
    return (int(cls), 1 if is_beam else 0, int(kind_id),
            *position, *velocity, *end, float(life), float(size), *rgba)


def pack_frame(buffer, *, tick, frame_index, tables, instances, effects, flags=0):
    """Pack one frame into `buffer` and return the bytes that were written.

    The buffer must be at least `frame_size(len(instances), len(effects))` bytes so a
    steady state allocates nothing.
    """
    if type(tick) is not int or not 0 <= tick < 2**32:
        raise FrameError('tick must be uint32')
    if type(frame_index) is not int or not 0 <= frame_index < 2**64:
        raise FrameError('frame_index must be uint64')
    if len(instances) > MAX_INSTANCES or len(effects) > MAX_EFFECTS:
        raise FrameError('frame exceeds the instance or effect ceiling')
    size = frame_size(len(instances), len(effects))
    if len(buffer) < size:
        raise FrameError(f'buffer too small: need {size} bytes')
    view = memoryview(buffer)
    offset = FRAME.size
    for record in instances:
        INSTANCE.pack_into(buffer, offset, *record)
        offset += INSTANCE.size
    for record in effects:
        EFFECT.pack_into(buffer, offset, *record)
        offset += EFFECT.size
    payload_crc = zlib.crc32(view[FRAME.size:offset])
    FRAME.pack_into(buffer, 0, MAGIC, VERSION, WORLD, tick, frame_index,
                    len(instances), len(effects), tables.crc32, flags, offset - FRAME.size,
                    payload_crc)
    return view[:offset]


def unpack_frame(data, tables: Tables) -> dict:
    """Validate and decode a frame. Fails closed; never guesses."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise FrameError('frame must be bytes')
    if len(data) < FRAME.size:
        raise FrameError('truncated frame header')
    (magic, version, kind, tick, frame_index, n_inst, n_eff,
     table_crc, flags, length, crc) = FRAME.unpack_from(data)
    if magic != MAGIC or version != VERSION or kind != WORLD:
        raise FrameError('unknown frame magic, version or kind')
    if n_inst > MAX_INSTANCES or n_eff > MAX_EFFECTS:
        raise FrameError('frame exceeds the instance or effect ceiling')
    if table_crc != tables.crc32:
        raise FrameError('frame was packed against a different table')
    if length != INSTANCE.size * n_inst + EFFECT.size * n_eff:
        raise FrameError('payload length does not match its counts')
    if len(data) != FRAME.size + length:
        raise FrameError('trailing bytes forbidden')
    payload = memoryview(data)[FRAME.size:]
    if zlib.crc32(payload) != crc:
        raise FrameError('frame CRC32 mismatch')
    instances, effects, offset = [], [], 0
    for _ in range(n_inst):
        fields = INSTANCE.unpack_from(payload, offset)
        offset += INSTANCE.size
        if fields[1] >= len(tables.bindings):
            raise FrameError('binding_id outside the table')
        if not all(math.isfinite(value) for value in fields[4:]):
            raise FrameError('non-finite instance element')
        instances.append({
            'entity_id': fields[0], 'binding': tables.bindings[fields[1]],
            'flags': fields[2], 'tint': [channel / 255 for channel in fields[3:7]],
            'matrix': list(fields[7:19]), 'hp': fields[19], 'shield': fields[20],
        })
    for _ in range(n_eff):
        fields = EFFECT.unpack_from(payload, offset)
        offset += EFFECT.size
        if fields[2] >= len(tables.kinds):
            raise FrameError('kind_id outside the table')
        effects.append({
            'class': fields[0], 'is_beam': bool(fields[1]),
            'kind': tables.kinds[fields[2]],
            'position': list(fields[3:6]), 'velocity': list(fields[6:9]),
            'end_position': list(fields[9:12]), 'life': fields[12],
            'size': fields[13], 'color': [channel / 255 for channel in fields[14:18]],
        })
    return {'tick': tick, 'frame_index': frame_index, 'flags': flags,
            'instances': instances, 'effects': effects}
