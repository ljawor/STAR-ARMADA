"""W05: planet textures travelling to the native window.

A planet in the Python renderer is a textured sphere: the texture is procedural
(`render/textures.py::planet_texture`, one per planet *type*, seeded from the planet's name so a
reload cannot change the world) and the sphere is a few hundred triangles. Only the texture is
worth carrying, and only once per distinct planet: it is static for the life of a match.

Layout (little-endian):

    blob header, 20 bytes:
        0  8s  magic b'ARMPLN01'
        8  u16 version (1)
       10  u16 width   (1..2048)
       12  u16 height  (1..2048)
       14  u16 name length (1..128)
       16  u32 crc32 over name + pixels
      then the name (utf-8), then width*height*4 bytes of RGBA, top row first.

A blob that fails any check is refused whole: a half-decoded texture would paint a planet with a
corrupt surface and the window would look broken in a way nobody could attribute.
"""
from __future__ import annotations

import struct
import zlib

MAGIC = b'ARMPLN01'
VERSION = 1
HEADER = struct.Struct('<8sHHHHI')
HEADER_BYTES = HEADER.size      # 20
MAX_DIM = 2048
MAX_NAME = 128

#: Prefix that marks a frame binding as a planet rather than an asset mesh.
BINDING_PREFIX = 'planet:'


class PlanetError(ValueError):
    """Malformed planet texture blob."""


def binding_name(data_id: str, name: str) -> str:
    """The binding string a planet instance carries: `planet:<data_id>:<name>`."""
    return f'{BINDING_PREFIX}{data_id}:{name}'


def parse_binding(binding: str):
    """(data_id, name) from a planet binding, or None for an ordinary asset binding."""
    if not binding.startswith(BINDING_PREFIX):
        return None
    rest = binding[len(BINDING_PREFIX):]
    data_id, _, name = rest.partition(':')
    if not data_id or not name:
        raise PlanetError(f'malformed planet binding: {binding!r}')
    return data_id, name


def encode_blob(name: str, width: int, height: int, rgba: bytes) -> bytes:
    width, height = int(width), int(height)
    if not 1 <= width <= MAX_DIM or not 1 <= height <= MAX_DIM:
        raise PlanetError(f'texture {width}x{height} outside 1..{MAX_DIM}')
    encoded = name.encode('utf-8')
    if not 1 <= len(encoded) <= MAX_NAME:
        raise PlanetError(f'name must be 1..{MAX_NAME} bytes')
    if len(rgba) != width * height * 4:
        raise PlanetError(f'{len(rgba)} bytes for a {width}x{height} RGBA surface')
    body = encoded + bytes(rgba)
    crc = zlib.crc32(body) & 0xFFFFFFFF
    return bytes(HEADER.pack(MAGIC, VERSION, width, height, len(encoded), crc)) + body


def decode_blob(buffer) -> dict:
    buffer = bytes(buffer)
    if len(buffer) < HEADER_BYTES:
        raise PlanetError('shorter than the blob header')
    magic, version, width, height, name_len, crc = HEADER.unpack_from(buffer, 0)
    if magic != MAGIC:
        raise PlanetError(f'bad magic {magic!r}')
    if version != VERSION:
        raise PlanetError(f'unsupported version {version}')
    if not 1 <= width <= MAX_DIM or not 1 <= height <= MAX_DIM:
        raise PlanetError(f'texture {width}x{height} outside 1..{MAX_DIM}')
    if not 1 <= name_len <= MAX_NAME:
        raise PlanetError(f'name length {name_len} outside 1..{MAX_NAME}')
    expected = HEADER_BYTES + name_len + width * height * 4
    if len(buffer) != expected:
        raise PlanetError(f'length {len(buffer)} but the header describes {expected}')
    body = buffer[HEADER_BYTES:]
    if zlib.crc32(body) & 0xFFFFFFFF != crc:
        raise PlanetError('blob crc mismatch')
    try:
        name = body[:name_len].decode('utf-8')
    except UnicodeDecodeError as error:
        raise PlanetError('name is not utf-8') from error
    return {'name': name, 'width': width, 'height': height,
            'rgba': body[name_len:]}


def surface_blob(surface, name: str) -> bytes:
    """Encode a pygame surface as a blob, converting a 24-bit surface to RGBA on the way."""
    import pygame

    width, height = surface.get_size()
    if surface.get_bitsize() != 32:
        surface = surface.convert(32)
    rgba = pygame.image.tostring(surface, 'RGBA')
    return encode_blob(name, width, height, rgba)
