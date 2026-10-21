"""W05 planet texture blobs: the codec, and the binding names that point at them."""

import struct
import unittest
import zlib

from render_bridge import planets as codec


class CodecTest(unittest.TestCase):
    def test_header_is_twenty_bytes(self):
        self.assertEqual(codec.HEADER_BYTES, 20)
        self.assertEqual(codec.MAGIC, b'ARMPLN01')

    def test_round_trip_keeps_name_and_pixels(self):
        rgba = bytes(range(256))              # 8x8 RGBA (256 bytes)
        blob = codec.encode_blob('Earth', 8, 8, rgba)
        decoded = codec.decode_blob(blob)
        self.assertEqual((decoded['name'], decoded['width'], decoded['height']), ('Earth', 8, 8))
        self.assertEqual(decoded['rgba'], rgba)

    def test_binding_names_round_trip(self):
        binding = codec.binding_name('temperate', 'New Terra')
        self.assertEqual(binding, 'planet:temperate:New Terra')
        self.assertEqual(codec.parse_binding(binding), ('temperate', 'New Terra'))
        self.assertIsNone(codec.parse_binding('imperial:corvette'))
        with self.assertRaises(codec.PlanetError):
            codec.parse_binding('planet:no-name')


class RefusalTest(unittest.TestCase):
    def setUp(self):
        self.good = codec.encode_blob('Mars', 4, 4, b'\x10' * 64)

    def test_bad_magic(self):
        with self.assertRaises(codec.PlanetError):
            codec.decode_blob(b'X' + self.good[1:])

    def test_unsupported_version(self):
        with self.assertRaises(codec.PlanetError):
            codec.decode_blob(self.good[:8] + struct.pack('<H', 2) + self.good[10:])

    def test_truncated(self):
        with self.assertRaises(codec.PlanetError):
            codec.decode_blob(self.good[:-1])

    def test_pixel_count_must_match_dimensions(self):
        with self.assertRaises(codec.PlanetError):
            codec.decode_blob(codec.encode_blob('Mars', 4, 4, b'\x10' * 60))

    def test_zero_width_refused(self):
        with self.assertRaises(codec.PlanetError):
            codec.encode_blob('Mars', 0, 4, b'')

    def test_oversized_texture_refused(self):
        with self.assertRaises(codec.PlanetError):
            codec.encode_blob('Mars', codec.MAX_DIM + 1, 1, b'\x00' * 4 * (codec.MAX_DIM + 1))

    def test_name_length_limits(self):
        with self.assertRaises(codec.PlanetError):
            codec.encode_blob('', 1, 1, b'\x00' * 4)
        with self.assertRaises(codec.PlanetError):
            codec.encode_blob('x' * (codec.MAX_NAME + 1), 1, 1, b'\x00' * 4)

    def test_crc_mismatch(self):
        broken = bytearray(self.good)
        broken[-1] ^= 0xFF
        with self.assertRaises(codec.PlanetError):
            codec.decode_blob(bytes(broken))

    def test_crc_covers_the_name_too(self):
        body = bytearray(self.good[codec.HEADER_BYTES:])
        body[0] ^= 0x20                       # 'M' -> 'm', same length
        patched = self.good[:codec.HEADER_BYTES] + bytes(body)
        with self.assertRaises(codec.PlanetError):
            codec.decode_blob(patched)


class StableNameSeedTest(unittest.TestCase):
    def test_the_seed_depends_on_the_name_not_the_process(self):
        from render.planet_blobs import seed_for

        self.assertEqual(seed_for('New Terra'), seed_for('New Terra'))
        self.assertNotEqual(seed_for('New Terra'), seed_for('Mars'))
        self.assertGreaterEqual(seed_for('Mars'), 0)
        self.assertLess(seed_for('Mars'), 1000000)


if __name__ == '__main__':
    unittest.main()
