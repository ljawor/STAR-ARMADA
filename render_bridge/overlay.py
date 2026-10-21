"""Overlay payload for W03: the composed HUD surface, dirty-rected, on the wire.

Design A (owner decision, `render-w03-design-a-overlay-transport-2026-10-21`) sends the surface the
Python UI already paints instead of re-implementing its text and geometry in C++. This module is the
format, and `render/overlay_upload.py` is what decides which rects to send.

Layout (little-endian):

    header, 28 bytes:
        0  8s  magic b'ARMOVL01'
        8  u16 version (1)
       10  u16 flags   bit 0 = bytes are the whole surface, not the rect list
       12  u16 width
       14  u16 height
       16  u16 rect count (0..4096)
       18  u16 reserved (0)
       20  u32 payload bytes
       24  u32 crc32 of the payload bytes

    rects, `rect count` x 8 bytes: u16 x, y, w, h (source rects, top-left origin)
    payload: the RGBA bytes of each rect in order (row major, no padding)

A full frame carries 0 rects and `width * height * 4` bytes. A patch frame's payload length must be
exactly the sum of the rect areas, so a truncated or padded patch is refused rather than half-applied.
"""
from __future__ import annotations

import struct
import zlib

MAGIC = b'ARMOVL01'
VERSION = 1
FLAG_FULL = 1
HEADER = struct.Struct('<8sHHHHHHII')
RECT = struct.Struct('<HHHH')
MAX_DIMENSION = 8192
MAX_RECTS = 4096
#: A single overlay payload may not exceed this; the ring slot has to hold one.
MAX_PAYLOAD = 8 << 20

HEADER_BYTES = HEADER.size          # 28
RECT_BYTES = RECT.size              # 8


class OverlayError(ValueError):
    """Malformed overlay payload."""


def encode(width, height, rects=(), patches=(), full=None):
    """Build an overlay payload.

    `full` is the whole-surface RGBA buffer; when given, `rects`/`patches` are ignored and the frame
    is marked full. Otherwise `rects` and `patches` must line up, and each patch is the bytes of that
    rect only.
    """
    width, height = int(width), int(height)
    if not 1 <= width <= MAX_DIMENSION or not 1 <= height <= MAX_DIMENSION:
        raise OverlayError(f'overlay size {width}x{height} is outside 1..{MAX_DIMENSION}')
    if full is not None:
        expected = width * height * 4
        if len(full) != expected:
            raise OverlayError(f'full overlay is {len(full)} bytes, expected {expected}')
        if expected > MAX_PAYLOAD:
            raise OverlayError('full overlay exceeds MAX_PAYLOAD')
        header = HEADER.pack(MAGIC, VERSION, FLAG_FULL, width, height, 0, 0,
                             expected, zlib.crc32(full) & 0xFFFFFFFF)
        return header + bytes(full)

    rects = [tuple(int(v) for v in rect) for rect in rects]
    if len(rects) != len(patches):
        raise OverlayError(f'{len(rects)} rects but {len(patches)} patches')
    if len(rects) > MAX_RECTS:
        raise OverlayError(f'{len(rects)} rects exceeds {MAX_RECTS}')
    for (x, y, w, h), patch in zip(rects, patches):
        if not (0 <= x and 0 <= y and w > 0 and h > 0 and x + w <= width and y + h <= height):
            raise OverlayError(f'rect {x},{y},{w},{h} is outside {width}x{height}')
        if len(patch) != w * h * 4:
            raise OverlayError(f'patch is {len(patch)} bytes, expected {w * h * 4} for {w}x{h}')
    payload = b''.join(bytes(patch) for patch in patches)
    if len(payload) > MAX_PAYLOAD:
        raise OverlayError('overlay payload exceeds MAX_PAYLOAD')
    header = HEADER.pack(MAGIC, VERSION, 0, width, height, len(rects), 0,
                         len(payload), zlib.crc32(payload) & 0xFFFFFFFF)
    return header + b''.join(RECT.pack(*rect) for rect in rects) + payload


def merge_rects(rects, width, height, slack=1.4):
    """Clip rects to the surface and merge them into fewer, larger patches.

    Dirty rects overlap - a panel background and the bar drawn on it are separate ops - so the
    payload would otherwise carry the same pixels several times and can exceed the whole surface.
    """
    clipped = []
    for x, y, w, h in (tuple(int(v) for v in rect) for rect in rects):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(width, x + w), min(height, y + h)
        if x1 > x0 and y1 > y0:
            clipped.append((x0, y0, x1 - x0, y1 - y0))
    if not clipped:
        return []
    total = sum(w * h for _, _, w, h in clipped)
    ux0 = min(r[0] for r in clipped)
    uy0 = min(r[1] for r in clipped)
    ux1 = max(r[0] + r[2] for r in clipped)
    uy1 = max(r[1] + r[3] for r in clipped)
    if len(clipped) > 1 and (ux1 - ux0) * (uy1 - uy0) <= slack * total:
        return [(ux0, uy0, ux1 - ux0, uy1 - uy0)]
    clipped.sort(key=lambda r: (r[1], r[0]))
    merged = [list(clipped[0])]
    for x, y, w, h in clipped[1:]:
        bx, by, bw, bh = merged[-1]
        nx0, ny0 = min(bx, x), min(by, y)
        nx1, ny1 = max(bx + bw, x + w), max(by + bh, y + h)
        union_area, band_area = (nx1 - nx0) * (ny1 - ny0), bw * bh + w * h
        if union_area <= slack * band_area:
            merged[-1] = [nx0, ny0, nx1 - nx0, ny1 - ny0]
        else:
            merged.append([x, y, w, h])
    return [tuple(r) for r in merged]


def encode_surface(surface, rects):
    """Encode the given rects of a pygame surface (what the HUD recorder reported as dirty)."""
    import pygame

    width, height = surface.get_size()
    merged = merge_rects([(r.x, r.y, r.width, r.height) if isinstance(r, pygame.Rect)
                          else tuple(r) for r in rects], width, height)
    patches = [pygame.image.tobytes(surface.subsurface(pygame.Rect(r)), 'RGBA', False)
               for r in merged]
    return encode(width, height, merged, patches)


def encode_surface_full(surface):
    """Encode the whole pygame surface as a full overlay frame."""
    import pygame

    width, height = surface.get_size()
    return encode(width, height, full=pygame.image.tobytes(surface, 'RGBA', False))


def decode(buffer):
    """Parse and validate an overlay payload. Raises `OverlayError` on anything unexpected."""
    buffer = bytes(buffer)
    if len(buffer) < HEADER_BYTES:
        raise OverlayError('shorter than the header')
    magic, version, flags, width, height, count, reserved, length, crc = HEADER.unpack_from(buffer, 0)
    if magic != MAGIC:
        raise OverlayError(f'bad magic {magic!r}')
    if version != VERSION:
        raise OverlayError(f'unsupported version {version}')
    if reserved or flags & ~FLAG_FULL:
        raise OverlayError(f'unknown flags {flags:#x} / reserved {reserved}')
    if not 1 <= width <= MAX_DIMENSION or not 1 <= height <= MAX_DIMENSION:
        raise OverlayError(f'bad dimensions {width}x{height}')
    if count > MAX_RECTS:
        raise OverlayError(f'{count} rects exceeds {MAX_RECTS}')
    if length > MAX_PAYLOAD:
        raise OverlayError('payload exceeds MAX_PAYLOAD')
    expected = HEADER_BYTES + count * RECT_BYTES + length
    if len(buffer) != expected:
        raise OverlayError(f'length {len(buffer)} but header describes {expected}')
    rects = []
    area = 0
    for index in range(count):
        x, y, w, h = RECT.unpack_from(buffer, HEADER_BYTES + index * RECT_BYTES)
        if w == 0 or h == 0 or x + w > width or y + h > height:
            raise OverlayError(f'rect {x},{y},{w},{h} is outside {width}x{height}')
        rects.append((x, y, w, h))
        area += w * h
    full = bool(flags & FLAG_FULL)
    if full and count:
        raise OverlayError('a full frame must not carry rects')
    if length != (width * height * 4 if full else area * 4):
        raise OverlayError(f'payload {length} bytes does not match '
                           f'{width}x{height} {"full" if full else f"{len(rects)} rects"}')
    payload = buffer[HEADER_BYTES + count * RECT_BYTES:]
    if zlib.crc32(payload) & 0xFFFFFFFF != crc:
        raise OverlayError('payload crc mismatch')
    return {
        'width': width,
        'height': height,
        'full': full,
        'rects': rects,
        'payload': payload,
    }
