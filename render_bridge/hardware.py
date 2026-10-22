"""An authored mesh the producer publishes because the window cannot read the asset.

The window's mesh catalogue comes from the offline snapshot, which lists the assets of the entities
that were on the map when it was taken. A planet building is created during a match - it does not
exist when the snapshot is written - so its mesh is not in that catalogue and the window has no
binding to draw. This carries the mesh instead: the same role-batched geometry the asset holds,
encoded once per binding and republished only when a binding the window has not seen appears.

Only geometry and roles cross. The role a triangle belongs to already means the same thing on both
sides - `base`, `dark`, `trim`, `accent`, `lit`, `cool` - and both palettes were the same long
before this file existed, so sending colour as well would be a second copy of a decision made
elsewhere. What the window cannot guess is the silhouette, and that is what travels.

Layout (little endian):

    0   8   magic 'ARMHWR01'
    8   2   version
    10  2   name length in bytes
    12  2   triangle count
    14  2   role block count
    16  4   crc32 of everything after the header
    20  ..  name (UTF-8, the asset binding, e.g. 'imperial:planet_extractor')
        ..  role blocks: <BH> role index, triangle count, then that many <12f> rows

A row is one triangle written flat: normal xyz then vertex xyz three times. Vertices are not
indexed or shared, for the same reason the window's own loader expands them: a triangle batch is
flat-shaded, so two triangles meeting at a corner never want the same vertex normal.
"""
from __future__ import annotations

import struct
import zlib

MAGIC = b'ARMHWR01'
VERSION = 1
HEADER = struct.Struct('<8sHHHHI')
BLOCK = struct.Struct('<BH')
ROW = struct.Struct('<12f')
MAX_TRIANGLES = 12000
MAX_NAME = 96

# The shared palette, in the order the window's loader assigns it. The index is what crosses.
ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')
_ROLE_INDEX = {name: index for index, name in enumerate(ROLES)}


class HardwareError(ValueError):
    """A blob that does not describe a mesh, or a mesh that does not fit the format."""


def encode(name: str, mesh: dict) -> bytes:
    """Pack one role-batched mesh. `mesh` is `{role: ((normal, (p0, p1, p2)), ...)}`."""
    if not isinstance(name, str) or not name:
        raise HardwareError('binding name must be a non-empty string')
    raw_name = name.encode('utf-8')
    if len(raw_name) > MAX_NAME:
        raise HardwareError(f'binding name longer than {MAX_NAME} bytes')
    blocks, total = [], 0
    for role, rows in mesh.items():
        index = _ROLE_INDEX.get(role)
        if index is None:
            raise HardwareError(f'unknown mesh role {role!r}')
        rows = list(rows)
        total += len(rows)
        if total > MAX_TRIANGLES:
            raise HardwareError(f'more than {MAX_TRIANGLES} triangles')
        out = bytearray(BLOCK.pack(index, len(rows)))
        for normal, triangle in rows:
            if len(normal) != 3 or len(triangle) != 3:
                raise HardwareError('a triangle is a normal plus three points')
            values = []
            for number in list(normal) + [axis for point in triangle for axis in point]:
                number = float(number)
                if number != number or number in (float('inf'), float('-inf')):
                    raise HardwareError('a mesh coordinate is not finite')
                values.append(number)
            out += ROW.pack(*values)
        blocks.append(bytes(out))
    body = raw_name + b''.join(blocks)
    return HEADER.pack(MAGIC, VERSION, len(raw_name), total, len(blocks),
                       zlib.crc32(body)) + body


def decode(blob: bytes) -> dict:
    """Unpack one blob, refusing anything that does not agree with its own header."""
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        raise HardwareError('blob must be bytes')
    raw = bytes(blob)
    if len(raw) < HEADER.size:
        raise HardwareError('blob shorter than its header')
    magic, version, name_len, triangles, blocks, crc = HEADER.unpack_from(raw, 0)
    if magic != MAGIC:
        raise HardwareError('not a hardware mesh blob')
    if version != VERSION:
        raise HardwareError(f'unsupported version {version}')
    if name_len == 0 or name_len > MAX_NAME:
        raise HardwareError('invalid name length')
    if triangles > MAX_TRIANGLES:
        raise HardwareError(f'more than {MAX_TRIANGLES} triangles')
    body = raw[HEADER.size:]
    if zlib.crc32(body) != crc:
        raise HardwareError('crc32 mismatch')
    if len(body) < name_len:
        raise HardwareError('blob ends inside its name')
    try:
        name = body[:name_len].decode('utf-8')
    except UnicodeDecodeError as error:
        raise HardwareError(f'name is not UTF-8: {error}') from error
    cursor = name_len
    roles: dict[str, list] = {}
    seen = 0
    for _ in range(blocks):
        if cursor + BLOCK.size > len(body):
            raise HardwareError('blob ends inside a role block')
        index, count = BLOCK.unpack_from(body, cursor)
        cursor += BLOCK.size
        if index >= len(ROLES):
            raise HardwareError(f'role index {index} outside the palette')
        if cursor + count * ROW.size > len(body):
            raise HardwareError('blob ends inside a role block')
        rows = []
        for _ in range(count):
            values = ROW.unpack_from(body, cursor)
            cursor += ROW.size
            rows.append((tuple(values[0:3]),
                         (tuple(values[3:6]), tuple(values[6:9]), tuple(values[9:12]))))
        seen += count
        role = ROLES[index]
        if role in roles:
            raise HardwareError(f'role {role!r} appears twice')
        roles[role] = rows
    if cursor != len(body):
        raise HardwareError('blob has trailing bytes')
    if seen != triangles:
        raise HardwareError(f'header says {triangles} triangles, blocks hold {seen}')
    return {'name': name, 'roles': roles, 'triangles': triangles}


def scaffold_mesh():
    """Selected authored scaffold, otherwise a solid version of the legacy lattice."""
    from render.asset_selection import mesh_for
    from render.fleet_geometry import _Hardware
    mesh = mesh_for('shared:construction_scaffold')
    if mesh is not None:
        return mesh
    import math
    hardware = _Hardware()
    hardware.ring('accent', 50., 48., 2., (0., 1., 0.), sides=24)
    hardware.ring('trim', 43.5, 41.5, 2., (0., 49., 0.), sides=24)
    for index in range(8):
        angle = index * math.tau / 8
        hardware.plate('base', (2., 50., 2.),
                       (42.5 * math.sin(angle), 25., 42.5 * math.cos(angle)), .3)
    return hardware.finish()


class MeshPublisher:
    """Only meshes named by visible packed instances cross; never inspect hidden entities.

    At most four blobs per frame fit in the eight-slot mesh ring without a single
    publish burst overwriting itself. Refresh active bindings periodically so a
    late/slow consumer can recover overwritten startup blobs. Geometry is encoded
    once per session, never rebuilt at frame rate.
    """
    def __init__(self, *, refresh_frames=120, max_per_frame=4):
        if refresh_frames < 1 or not 1 <= max_per_frame <= 4:
            raise ValueError('invalid mesh publication budget')
        self.refresh_frames = refresh_frames
        self.max_per_frame = max_per_frame
        self._blobs = {}
        self._sent = {}
        self.frames = 0

    def publish_frame(self, frame, tables, target):
        from . import packed
        names = set()
        count = packed.FRAME.unpack_from(frame)[5]
        for index in range(count):
            record = packed.INSTANCE.unpack_from(frame, packed.FRAME.size + index * packed.INSTANCE.size)
            if record[2] & (packed.FLAG_DYNAMIC_MESH | packed.FLAG_SURFACE_FRAME):
                names.add(tables.bindings[record[1]])
        due = [name for name in names if name not in self._sent
               or self.frames - self._sent[name] >= self.refresh_frames]
        # Unsent first, then oldest, ensuring a busy active set cannot starve a binding.
        due.sort(key=lambda name: (self._sent.get(name, -1), name))
        published = 0
        for name in due[:self.max_per_frame]:
            if name not in self._blobs:
                if name == 'shared:construction_scaffold':
                    mesh = scaffold_mesh()
                else:
                    from render.fleet_geometry import station_mesh
                    faction, kind = name.split(':', 1)
                    mesh = station_mesh(kind, faction)
                self._blobs[name] = encode(name, mesh)
            target.publish(self._blobs[name])
            self._sent[name] = self.frames
            published += 1
        self.frames += 1
        return published
