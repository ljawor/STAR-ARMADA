"""W05 slice 4: the fog mask travelling to the native window.

In the Python renderer the fog is *not* a per-pixel effect: `render/fog.py::FogMask` classifies one
small texture over the map (a cell is visible, charted or unexplored) and draws it as a single quad
lying on the ecliptic. The classification is authoritative state - sensor sources, effective radii,
explored cells - and it stays in Python. What crosses is the finished mask, and only when it
changes, exactly like the HUD surface in W03 and the planet textures in W05 slice 1.

Carrying the inputs instead would be worse in every direction: the explored-cell set alone is
thousands of cells, and re-deriving the radii natively would be a second opinion about what the
player can see.

Layout (little-endian):

    header, 28 bytes:
        0  8s  magic b'ARMFOG01'
        8  u16 version (1)
       10  u16 cells   (1..2048)      - the mask is square, cells x cells
       12  f32 cell    (metres per cell)
       16  f32 bounds  (map extent the quad covers)
       20  u32 generation             - bumps whenever the classification changed
       24  u32 crc32 over the pixels
      then cells*cells*4 bytes of RGBA, row 0 = -z edge (the same order the Python surface uses).

A blob that fails any check is refused whole: a half-decoded mask would blank half the map or
reveal ground the player has never seen.
"""
from __future__ import annotations

import struct
import zlib

MAGIC = b'ARMFOG01'
VERSION = 1
HEADER = struct.Struct('<8sHHffII')
HEADER_BYTES = HEADER.size      # 28
MAX_CELLS = 2048


class FogMapError(ValueError):
    """Malformed fog mask blob."""


def encode_blob(cells: int, cell: float, bounds: float, generation: int, rgba: bytes) -> bytes:
    cells = int(cells)
    if not 1 <= cells <= MAX_CELLS:
        raise FogMapError(f'cells out of range: {cells}')
    expected = cells * cells * 4
    if len(rgba) != expected:
        raise FogMapError(f'expected {expected} bytes of RGBA, got {len(rgba)}')
    header = HEADER.pack(MAGIC, VERSION, cells, float(cell), float(bounds),
                         int(generation) & 0xFFFFFFFF, 0)
    crc = zlib.crc32(rgba) & 0xFFFFFFFF
    header = HEADER.pack(MAGIC, VERSION, cells, float(cell), float(bounds),
                         int(generation) & 0xFFFFFFFF, crc)
    return header + bytes(rgba)


def decode(blob: bytes) -> dict:
    if len(blob) < HEADER_BYTES:
        raise FogMapError('short header')
    magic, version, cells, cell, bounds, generation, crc = HEADER.unpack_from(blob, 0)
    if magic != MAGIC:
        raise FogMapError(f'bad magic: {magic!r}')
    if version != VERSION:
        raise FogMapError(f'unsupported version: {version}')
    if not 1 <= cells <= MAX_CELLS:
        raise FogMapError(f'cells out of range: {cells}')
    expected = cells * cells * 4
    pixels = blob[HEADER_BYTES:]
    if len(pixels) != expected:
        raise FogMapError(f'expected {expected} bytes of RGBA, got {len(pixels)}')
    if zlib.crc32(pixels) & 0xFFFFFFFF != crc:
        raise FogMapError('crc mismatch')
    return {'cells': cells, 'cell': cell, 'bounds': bounds, 'generation': generation,
            'rgba': pixels}
