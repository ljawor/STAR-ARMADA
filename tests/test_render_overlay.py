"""Wire format for the W03 overlay: encode, decode, and refuse anything malformed.

The decoder on the other side is C++ (`render_cpp/include/overlay.hpp`, tested by
`render_cpp/tests/test_overlay.cpp` against fixtures this suite's sibling writer produces). These
tests pin the producer half: a payload the native decoder accepts must carry exactly the pixels of
the rects it names, and a payload that is wrong must never be produced.
"""

import struct
import unittest
import zlib

from render_bridge import overlay


def pattern(width, height):
    """Deterministic RGBA surface, so a mismatch names the offending pixel."""
    out = bytearray()
    for y in range(height):
        for x in range(width):
            out += bytes(((x * 16) & 0xFF, (y * 32) & 0xFF, ((x + y) * 7) & 0xFF, 255))
    return bytes(out)


def pygame_surface(width, height):
    import pygame

    surface = pygame.Surface((width, height), pygame.SRCALPHA, 32)
    surface.blit(pygame.image.frombuffer(pattern(width, height), (width, height), 'RGBA'), (0, 0))
    return surface


def pixels(surface, width, x0, y0, w, h):
    return b''.join(surface[((y0 + row) * width + x0) * 4:((y0 + row) * width + x0 + w) * 4]
                    for row in range(h))


class HeaderTest(unittest.TestCase):
    def test_sizes_are_what_the_native_decoder_expects(self):
        self.assertEqual(overlay.HEADER_BYTES, 28)
        self.assertEqual(overlay.RECT_BYTES, 8)
        self.assertEqual(overlay.HEADER.size, 28)
        self.assertEqual(overlay.HEADER.format, '<8sHHHHHHII')
        self.assertEqual(overlay.MAGIC, b'ARMOVL01')


class EncodeTest(unittest.TestCase):
    def test_full_frame_is_the_whole_surface_and_carries_no_rects(self):
        surface = pattern(8, 4)
        frame = overlay.decode(overlay.encode(8, 4, full=surface))
        self.assertTrue(frame['full'])
        self.assertEqual(frame['rects'], [])
        self.assertEqual(frame['payload'], surface)

    def test_patch_frame_carries_exactly_the_bytes_of_each_rect(self):
        surface = pattern(8, 4)
        rects = [(2, 1, 3, 2), (6, 0, 2, 3)]
        patches = [pixels(surface, 8, *r) for r in rects]
        frame = overlay.decode(overlay.encode(8, 4, rects, patches))
        self.assertFalse(frame['full'])
        self.assertEqual(frame['rects'], rects)
        expected = b''.join(patches)
        self.assertEqual(frame['payload'], expected)
        self.assertEqual(len(frame['payload']), sum(w * h * 4 for _, _, w, h in rects))

    def test_refuses_patch_bytes_that_do_not_match_the_rect_area(self):
        with self.assertRaises(overlay.OverlayError):
            overlay.encode(8, 4, [(2, 1, 3, 2)], [b'\0' * 4])

    def test_refuses_a_rect_outside_the_surface(self):
        with self.assertRaises(overlay.OverlayError):
            overlay.encode(8, 4, [(7, 3, 2, 2)], [b'\0' * 16])

    def test_refuses_a_full_buffer_of_the_wrong_length(self):
        with self.assertRaises(overlay.OverlayError):
            overlay.encode(8, 4, full=b'\0' * 100)

    def test_refuses_more_rects_than_the_ceiling(self):
        rects = [(0, 0, 1, 1)] * (overlay.MAX_RECTS + 1)
        with self.assertRaises(overlay.OverlayError):
            overlay.encode(64, 64, rects, [b'\0' * 4] * len(rects))

    def test_refuses_odd_dimensions(self):
        for width, height in ((0, 4), (8, 0), (overlay.MAX_DIMENSION + 1, 4)):
            with self.assertRaises(overlay.OverlayError):
                overlay.encode(width, height, full=b'\0' * 4)


class DecodeRefusalTest(unittest.TestCase):
    def setUp(self):
        self.surface = pattern(8, 4)
        self.full = overlay.encode(8, 4, full=self.surface)

    def test_bad_magic(self):
        with self.assertRaises(overlay.OverlayError):
            overlay.decode(b'X' + self.full[1:])

    def test_unsupported_version(self):
        with self.assertRaises(overlay.OverlayError):
            overlay.decode(self.full[:8] + struct.pack('<H', 2) + self.full[10:])

    def test_unknown_flags(self):
        with self.assertRaises(overlay.OverlayError):
            overlay.decode(self.full[:10] + struct.pack('<H', 0x8) + self.full[12:])

    def test_truncated_payload(self):
        with self.assertRaises(overlay.OverlayError):
            overlay.decode(self.full[:-8])

    def test_crc_mismatch(self):
        with self.assertRaises(overlay.OverlayError):
            overlay.decode(self.full[:-1] + bytes([self.full[-1] ^ 0xFF]))

    def test_trailing_byte(self):
        with self.assertRaises(overlay.OverlayError):
            overlay.decode(self.full + b'\0')

    def test_empty(self):
        with self.assertRaises(overlay.OverlayError):
            overlay.decode(b'')

    def test_full_frame_with_rects(self):
        with self.assertRaises(overlay.OverlayError):
            overlay.decode(self.full[:16] + struct.pack('<H', 1) + self.full[18:])

    def test_rect_outside(self):
        frame = overlay.encode(8, 4, [(2, 1, 3, 2)], [pixels(self.surface, 8, 2, 1, 3, 2)])
        broken = frame[:28] + struct.pack('<HHHH', 7, 0, 2, 1) + frame[36:]
        with self.assertRaises(overlay.OverlayError):
            overlay.decode(broken)

    def test_crc_is_over_the_payload_not_the_header(self):
        payload = pixels(self.surface, 8, 2, 1, 3, 2)
        frame = overlay.encode(8, 4, [(2, 1, 3, 2)], [payload])
        header = overlay.HEADER.unpack_from(frame, 0)
        self.assertEqual(header[8], zlib.crc32(payload) & 0xFFFFFFFF)


class SurfaceTest(unittest.TestCase):
    def test_encode_surface_reads_the_named_rects(self):
        raw = pattern(8, 4)
        frame = overlay.decode(overlay.encode_surface(pygame_surface(8, 4), [(1, 0, 2, 2)]))
        self.assertEqual(frame['rects'], [(1, 0, 2, 2)])
        self.assertEqual(frame['payload'], pixels(raw, 8, 1, 0, 2, 2))

    def test_encode_surface_merges_dirty_rects_instead_of_sending_overlap(self):
        raw = pattern(8, 4)
        frame = overlay.decode(overlay.encode_surface(pygame_surface(8, 4), [(0, 0, 8, 4),
                                                                            (0, 0, 8, 4)]))
        # Two identical dirty rects must not put the surface on the wire twice.
        self.assertEqual(len(frame['payload']), 8 * 4 * 4)
        self.assertEqual(frame['payload'], raw)

    def test_encode_surface_full(self):
        raw = pattern(8, 4)
        frame = overlay.decode(overlay.encode_surface_full(pygame_surface(8, 4)))
        self.assertTrue(frame['full'])
        self.assertEqual(frame['payload'], raw)


class MergeTest(unittest.TestCase):
    def test_merge_never_selects_more_pixels_than_the_slack_allows(self):
        rects = [(0, 0, 10, 10), (2, 2, 10, 10), (5, 5, 10, 10)]
        merged = overlay.merge_rects(rects, 64, 64, slack=1.4)
        area = sum(w * h for _, _, w, h in merged)
        painted = set()
        for x, y, w, h in rects:
            painted.update((x + i, y + j) for i in range(w) for j in range(h))
        self.assertGreaterEqual(area, len(painted))
        self.assertLessEqual(area, len(painted) * 1.4 + 4)
        for x, y, w, h in merged:
            self.assertTrue(0 <= x and x + w <= 64 and 0 <= y and y + h <= 64)

    def test_merge_covers_every_rect_it_is_given(self):
        rects = [(3, 4, 5, 6), (20, 1, 4, 4), (21, 2, 4, 4)]
        merged = overlay.merge_rects(rects, 64, 64)
        for x, y, w, h in rects:
            self.assertTrue(
                any(mx <= x and x + w <= mx + mw and my <= y and y + h <= my + mh
                    for mx, my, mw, mh in merged),
                f'rect {(x, y, w, h)} is not covered by {merged}')

    def test_merge_of_nothing_is_nothing(self):
        self.assertEqual(overlay.merge_rects([], 64, 64), [])


class ReplayTest(unittest.TestCase):
    """The property the window relies on: keyframe + patches == the surface it published."""

    def replay(self, frames, width, height):
        surface = bytearray(width * height * 4)
        for frame in frames:
            if frame['full']:
                surface[:] = frame['payload']
                continue
            offset = 0
            for x, y, w, h in frame['rects']:
                for row in range(h):
                    start = ((y + row) * width + x) * 4
                    surface[start:start + w * 4] = frame['payload'][offset:offset + w * 4]
                    offset += w * 4
        return bytes(surface)

    def test_patch_stream_reproduces_the_last_surface(self):
        width, height = 8, 4
        first = pattern(width, height)
        second = bytearray(first)
        second[(1 * width + 3) * 4:(1 * width + 4) * 4] = b'\x01\x02\x03\xff'
        second = bytes(second)
        frames = [overlay.decode(overlay.encode(width, height, full=first)),
                  overlay.decode(overlay.encode(width, height, [(3, 1, 1, 1)],
                                                [pixels(second, width, 3, 1, 1, 1)]))]
        self.assertEqual(self.replay(frames, width, height), second)


if __name__ == '__main__':
    unittest.main()
