"""W00/W01 offline file profile. See docs/RENDER_PROTOCOL.md."""
from dataclasses import dataclass
import json
import struct
import zlib

MAGIC = b'ARMADAS\0'
VERSION = 1
WORLD, UI = 1, 2
HEADER = struct.Struct('<8sHHIQII')
MAX_PAYLOAD = 64 * 1024 * 1024


class ProtocolError(ValueError):
    """Malformed/unsupported offline frame (native consumer exit code 3)."""


@dataclass(frozen=True)
class Frame:
    kind: int
    tick: int
    frame_index: int
    payload: dict


def _canonical(payload):
    if not isinstance(payload, dict):
        raise ProtocolError('payload must be an object')
    def keys(value):
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ProtocolError('JSON object keys must be strings')
            for item in value.values():
                keys(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                keys(item)
    try:
        keys(payload)
        return json.dumps(payload, sort_keys=True, separators=(',', ':'),
                          allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise ProtocolError(f'invalid JSON payload: {exc}') from exc


def encode(payload, *, kind=WORLD, tick=0, frame_index=0):
    if type(kind) is not int or kind not in (WORLD, UI):
        raise ProtocolError('unknown kind')
    for name, value, bits in (('tick', tick, 32), ('frame_index', frame_index, 64)):
        if type(value) is not int or not 0 <= value < 2**bits:
            raise ProtocolError(f'{name} must be uint{bits}')
    raw = _canonical(payload)
    if len(raw) > MAX_PAYLOAD:
        raise ProtocolError('payload exceeds 64 MiB')
    return HEADER.pack(MAGIC, VERSION, kind, tick, frame_index, len(raw),
                       zlib.crc32(raw)) + raw


def decode(data):
    if not isinstance(data, (bytes, bytearray, memoryview)) or len(data) < HEADER.size:
        raise ProtocolError('truncated header or non-bytes frame')
    magic, version, kind, tick, frame_index, length, crc = HEADER.unpack_from(data)
    if magic != MAGIC or version != VERSION or kind not in (WORLD, UI):
        raise ProtocolError('unknown magic, version or kind')
    if length > MAX_PAYLOAD or len(data) != HEADER.size + length:
        raise ProtocolError('invalid payload length (trailing bytes forbidden)')
    raw = bytes(data[HEADER.size:])
    if zlib.crc32(raw) != crc:
        raise ProtocolError('CRC32 mismatch')
    try:
        payload = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProtocolError(f'invalid UTF-8 JSON: {exc}') from exc
    if _canonical(payload) != raw:
        raise ProtocolError('noncanonical JSON (including duplicate keys)')
    return Frame(kind, tick, frame_index, payload)
