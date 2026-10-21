"""Round trip and refusal tests for the hardware mesh blob."""
from __future__ import annotations

import struct
import sys
import types
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from render_bridge import hardware


def mesh(roles=('base', 'trim'), rows=2):
    """A small role-batched mesh: `rows` triangles per role, each in its own plane."""
    out = {}
    for index, role in enumerate(roles):
        batch = []
        for step in range(rows):
            normal = (0.0, 1.0, 0.0) if index % 2 == 0 else (0.0, 0.0, 1.0)
            base = float(index * 10 + step)
            batch.append((normal, ((base, 0.0, 0.0), (base + 1.0, 0.0, 0.0),
                                   (base, 0.0, 1.0))))
        out[role] = tuple(batch)
    return out


class RoundTripTests(unittest.TestCase):
    def test_a_mesh_survives_the_round_trip(self):
        source = mesh()
        decoded = hardware.decode(hardware.encode('imperial:planet_extractor', source))
        self.assertEqual(decoded['name'], 'imperial:planet_extractor')
        self.assertEqual(decoded['triangles'], 4)
        self.assertEqual(set(decoded['roles']), {'base', 'trim'})
        for role, rows in source.items():
            for got, want in zip(decoded['roles'][role], rows):
                self.assertEqual(got[0], want[0])
                self.assertEqual(got[1], want[1])

    def test_the_blob_is_twenty_bytes_of_header_plus_the_payload(self):
        blob = hardware.encode('x', {'base': mesh(('base',), 1)['base']})
        name_len = len('x')
        self.assertEqual(len(blob), hardware.HEADER.size + name_len
                         + hardware.BLOCK.size + hardware.ROW.size)

    def test_every_role_index_round_trips(self):
        for role in hardware.ROLES:
            decoded = hardware.decode(hardware.encode('r', {role: mesh((role,), 1)[role]}))
            self.assertEqual(set(decoded['roles']), {role})

    def test_the_crc_covers_the_payload_not_the_header(self):
        blob = bytearray(hardware.encode('name', mesh()))
        body = blob[hardware.HEADER.size:]
        self.assertEqual(struct.unpack_from('<I', blob, 16)[0], zlib.crc32(body))

    def test_an_empty_mesh_is_a_valid_blob(self):
        decoded = hardware.decode(hardware.encode('empty', {}))
        self.assertEqual(decoded['triangles'], 0)
        self.assertEqual(decoded['roles'], {})


class RefusalTests(unittest.TestCase):
    def test_a_short_blob_is_refused(self):
        with self.assertRaises(hardware.HardwareError):
            hardware.decode(b'ARMHWR01')

    def test_a_foreign_magic_is_refused(self):
        blob = hardware.encode('x', mesh())
        with self.assertRaises(hardware.HardwareError):
            hardware.decode(b'ARMEMIT1' + blob[8:])

    def test_a_flipped_payload_byte_is_refused_by_the_crc(self):
        blob = bytearray(hardware.encode('x', mesh()))
        blob[-1] ^= 0xFF
        with self.assertRaises(hardware.HardwareError):
            hardware.decode(bytes(blob))

    def test_a_truncated_payload_is_refused(self):
        blob = hardware.encode('x', mesh())
        with self.assertRaises(hardware.HardwareError):
            hardware.decode(blob[:-8])

    def test_an_unknown_role_index_is_refused(self):
        body = b'x' + hardware.BLOCK.pack(len(hardware.ROLES), 0)
        blob = bytearray(hardware.HEADER.pack(hardware.MAGIC, hardware.VERSION, 1, 0, 1,
                                              zlib.crc32(body)) + body)
        with self.assertRaises(hardware.HardwareError):
            hardware.decode(bytes(blob))

    def test_a_role_that_appears_twice_is_refused(self):
        rows = mesh(('base',), 1)['base']
        block = hardware.BLOCK.pack(0, 1) + hardware.ROW.pack(0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
        body = b'x' + block + block
        blob = hardware.HEADER.pack(hardware.MAGIC, hardware.VERSION, 1, 2, 2,
                                    zlib.crc32(body)) + body
        with self.assertRaises(hardware.HardwareError):
            hardware.decode(blob)
        self.assertEqual(len(rows), 1)

    def test_a_triangle_count_that_disagrees_with_the_header_is_refused(self):
        blob = bytearray(hardware.encode('x', mesh()))
        struct.pack_into('<H', blob, 12, 9)
        struct.pack_into('<I', blob, 16, zlib.crc32(bytes(blob[hardware.HEADER.size:])))
        with self.assertRaises(hardware.HardwareError):
            hardware.decode(bytes(blob))

    def test_trailing_bytes_are_refused(self):
        blob = hardware.encode('x', mesh()) + b'\x00'
        with self.assertRaises(hardware.HardwareError):
            hardware.decode(blob)

    def test_an_unknown_role_name_is_refused_when_encoding(self):
        with self.assertRaises(hardware.HardwareError):
            hardware.encode('x', {'glow': mesh(('base',), 1)['base']})

    def test_a_non_finite_coordinate_is_refused_when_encoding(self):
        bad = {'base': (((0.0, 1.0, 0.0), ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                                          (float('nan'), 0.0, 1.0))),)}
        with self.assertRaises(hardware.HardwareError):
            hardware.encode('x', bad)

    def test_a_triangle_that_is_not_three_points_is_refused(self):
        bad = {'base': (((0.0, 1.0, 0.0), ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))),)}
        with self.assertRaises(hardware.HardwareError):
            hardware.encode('x', bad)

    def test_a_name_that_is_too_long_is_refused(self):
        with self.assertRaises(hardware.HardwareError):
            hardware.encode('x' * (hardware.MAX_NAME + 1), mesh())


if __name__ == '__main__':
    unittest.main()
