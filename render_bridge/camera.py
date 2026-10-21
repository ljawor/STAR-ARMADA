"""The game's camera, published so the window can look at what the player is looking at.

Until this ring existed the window had its own camera, and a click leaving the window would have been
resolved in Python against a different view - which is why the input ring stayed unread. The pose
crosses as an *answer* like everything else: the simulation's camera object is read here and copied,
never nudged.

Wire format (`ARMCAM01`): a 20-byte header, then six float32 in this order -

    target.x, target.y, target.z, distance, yaw, pitch

`yaw` and `pitch` are degrees, matching `render.camera.Camera` and the window's own `Camera`. The
window applies the pose and keeps its own field of view, which is the one thing that is native.
"""
from __future__ import annotations

import struct
import zlib

MAGIC = b'ARMCAM01'
VERSION = 1
HEADER = struct.Struct('<8sHHII')     # magic, version, reserved, length, crc32
POSE = struct.Struct('<6f')
HEADER_BYTES = HEADER.size
PAYLOAD_BYTES = POSE.size


class CameraError(ValueError):
    """A camera payload that cannot be trusted."""


def encode(camera) -> bytes:
    """Serialize a `render.camera.Camera` (or anything with the same six numbers)."""
    target = list(camera.target)
    body = POSE.pack(float(target[0]), float(target[1]), float(target[2]),
                     float(camera.distance), float(camera.yaw), float(camera.pitch))
    crc = zlib.crc32(body) & 0xFFFFFFFF
    return HEADER.pack(MAGIC, VERSION, 0, len(body), crc) + body


def decode(buffer) -> dict:
    """Parse and validate a camera payload. Refuses anything it cannot read exactly."""
    buffer = bytes(buffer)
    if len(buffer) < HEADER_BYTES:
        raise CameraError('shorter than the header')
    magic, version, reserved, length, crc = HEADER.unpack_from(buffer, 0)
    if magic != MAGIC:
        raise CameraError(f'bad magic {magic!r}')
    if version != VERSION:
        raise CameraError(f'unsupported version {version}')
    if reserved:
        raise CameraError(f'reserved field is {reserved}')
    if length != PAYLOAD_BYTES:
        raise CameraError(f'payload is {length} bytes, expected {PAYLOAD_BYTES}')
    if len(buffer) != HEADER_BYTES + length:
        raise CameraError(f'length {len(buffer)} but header describes {HEADER_BYTES + length}')
    body = buffer[HEADER_BYTES:]
    if zlib.crc32(body) & 0xFFFFFFFF != crc:
        raise CameraError('payload crc mismatch')
    x, y, z, distance, yaw, pitch = POSE.unpack(body)
    return {'target': (x, y, z), 'distance': distance, 'yaw': yaw, 'pitch': pitch}
