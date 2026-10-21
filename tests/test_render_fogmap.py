"""W05 slice 4: the fog mask blob.

The mask is authoritative data - it is the picture of what a team can see, and drawing a cell as
unexplored that is in fact visible (or the reverse) is a game-state leak, not a cosmetic slip. So
these tests are mostly about refusing doubtful blobs whole.
"""
import struct
import unittest
import zlib

from render_bridge import fogmap


def _rgba(cells):
    return bytes((i * 7 + 3) & 0xFF for i in range(cells * cells * 4))


class FogMapRoundTrip(unittest.TestCase):
    def test_round_trip_keeps_every_field(self):
        blob = fogmap.encode_blob(72, 500.0, 36000.0, 4, _rgba(72))
        mask = fogmap.decode(blob)
        self.assertEqual(mask['cells'], 72)
        self.assertEqual(mask['cell'], 500.0)
        self.assertEqual(mask['bounds'], 36000.0)
        self.assertEqual(mask['generation'], 4)
        self.assertEqual(mask['rgba'], _rgba(72))

    def test_header_is_twenty_eight_bytes(self):
        blob = fogmap.encode_blob(4, 500.0, 2000.0, 1, _rgba(4))
        self.assertEqual(len(blob), 28 + 4 * 4 * 4)
        magic, version, cells = struct.unpack_from('<8sHH', blob, 0)
        self.assertEqual(magic, b'ARMFOG01')
        self.assertEqual(version, 1)
        self.assertEqual(cells, 4)

    def test_one_mask_is_small_enough_to_republish_on_change(self):
        # 72 cells at 500 m over a 36 km map is 20 KB. Republishing it whenever the classification
        # changes costs less than one frame's worth of ship instances, which is why the mask can be
        # carried as a picture instead of as sensor sources and explored cells.
        blob = fogmap.encode_blob(72, 500.0, 36000.0, 1, _rgba(72))
        self.assertLess(len(blob), 32 * 1024)


class FogMapRefuses(unittest.TestCase):
    def test_bad_magic(self):
        blob = bytearray(fogmap.encode_blob(4, 500.0, 2000.0, 1, _rgba(4)))
        blob[0] = ord('X')
        with self.assertRaises(fogmap.FogMapError):
            fogmap.decode(bytes(blob))

    def test_wrong_pixel_count(self):
        blob = fogmap.encode_blob(4, 500.0, 2000.0, 1, _rgba(4))
        with self.assertRaises(fogmap.FogMapError):
            fogmap.decode(blob[:-4])

    def test_crc_mismatch(self):
        blob = bytearray(fogmap.encode_blob(4, 500.0, 2000.0, 1, _rgba(4)))
        blob[28] ^= 0xFF
        with self.assertRaises(fogmap.FogMapError):
            fogmap.decode(bytes(blob))

    def test_short_header(self):
        with self.assertRaises(fogmap.FogMapError):
            fogmap.decode(b'ARMFOG0')

    def test_zero_cells_is_refused(self):
        header = fogmap.HEADER.pack(b'ARMFOG01', 1, 0, 500.0, 2000.0, 1, 0)
        with self.assertRaises(fogmap.FogMapError):
            fogmap.decode(header)

    def test_encode_refuses_a_short_pixel_budget(self):
        with self.assertRaises(fogmap.FogMapError):
            fogmap.encode_blob(8, 500.0, 4000.0, 1, _rgba(4))


class FogMapAgreesWithTheRenderer(unittest.TestCase):
    """The codec must not re-describe the mask: the same surface must decode to the same texels."""

    def test_pygame_surface_bytes_round_trip_unchanged(self):
        import pygame
        surface = pygame.Surface((6, 5), pygame.SRCALPHA)
        for x in range(6):
            for y in range(5):
                # visible / charted / unexplored, the three states the renderer actually writes
                states = [(0, 0, 0, 0), (12, 22, 38, 155), (3, 6, 13, 255)]
                surface.set_at((x, y), states[(x + y) % 3])
        # the mask is square by construction; use a square surface here
        square = pygame.Surface((5, 5), pygame.SRCALPHA)
        square.blit(surface, (0, 0))
        raw = pygame.image.tobytes(square, 'RGBA', False)
        mask = fogmap.decode(fogmap.encode_blob(5, 500.0, 2500.0, 1, raw))
        self.assertEqual(mask['rgba'], raw)
        self.assertEqual(zlib.crc32(mask['rgba']) & 0xFFFFFFFF,
                         zlib.crc32(raw) & 0xFFFFFFFF)


if __name__ == '__main__':
    unittest.main()
