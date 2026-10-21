"""W04 input batches: the window's events must arrive as the events the game already handles."""

import struct
import unittest
import zlib

from render_bridge import input as inp


def batch(*events):
    return inp.encode_batch([inp.Event(*fields) for fields in events])


class FormatTest(unittest.TestCase):
    def test_record_and_header_sizes_are_fixed(self):
        self.assertEqual(inp.RECORD_BYTES, 16)
        self.assertEqual(inp.HEADER_BYTES, 20)
        self.assertEqual(inp.MAGIC, b'ARMINP01')

    def test_empty_batch_round_trips(self):
        self.assertEqual(inp.decode_batch(inp.encode_batch([])), [])

    def test_round_trip_preserves_every_field(self):
        events = [inp.Event(inp.MOTION, button=1, x=-5, y=12),
                  inp.Event(inp.BUTTON_DOWN, button=1, x=100, y=200),
                  inp.Event(inp.WHEEL, button=1),
                  inp.Event(inp.KEY_DOWN, button=inp.MOD_SHIFT, code=ord('a')),
                  inp.Event(inp.RESIZE, extra=(1280 << 16) | 800)]
        self.assertEqual(inp.decode_batch(inp.encode_batch(events)), events)

    def test_refuses_an_unknown_kind(self):
        with self.assertRaises(inp.InputError):
            inp.Event(99)


class RefusalTest(unittest.TestCase):
    def setUp(self):
        self.good = batch((inp.KEY_DOWN, 0, ord('a'), 0, 0, 0))

    def test_bad_magic(self):
        with self.assertRaises(inp.InputError):
            inp.decode_batch(b'X' + self.good[1:])

    def test_unsupported_version(self):
        with self.assertRaises(inp.InputError):
            inp.decode_batch(self.good[:8] + struct.pack('<H', 2) + self.good[10:])

    def test_truncated(self):
        with self.assertRaises(inp.InputError):
            inp.decode_batch(self.good[:-4])

    def test_trailing_bytes(self):
        with self.assertRaises(inp.InputError):
            inp.decode_batch(self.good + b'\0')

    def test_crc_mismatch(self):
        broken = bytearray(self.good)
        broken[-1] ^= 0xFF
        with self.assertRaises(inp.InputError):
            inp.decode_batch(bytes(broken))

    def test_record_ceiling(self):
        frame = inp.encode_batch([])[:10] + struct.pack('<H', inp.MAX_RECORDS + 1) + \
            inp.encode_batch([])[12:]
        with self.assertRaises(inp.InputError):
            inp.decode_batch(frame)

    def test_non_zero_reserved_field(self):
        frame = inp.encode_batch([])[:12] + struct.pack('<H', 7) + inp.encode_batch([])[14:]
        with self.assertRaises(inp.InputError):
            inp.decode_batch(frame)

    def test_too_many_events_to_encode(self):
        with self.assertRaises(inp.InputError):
            inp.encode_batch([inp.Event(inp.MOTION)] * (inp.MAX_RECORDS + 1))


class PygameMappingTest(unittest.TestCase):
    """The whole point: what comes off the wire is what `InputController.handle_event` expects."""

    def test_letters_and_digits_keep_their_ascii_code(self):
        import pygame

        for char in 'abcdefghijklmnopqrstuvwxyz0123456789':
            event = inp.Event(inp.KEY_DOWN, code=ord(char))
            self.assertEqual(event.pygame_key(), getattr(pygame, f'K_{char}'))

    def test_special_keys_map_to_pygame_constants(self):
        import pygame

        expected = {inp.KEYCODE_ESCAPE: pygame.K_ESCAPE, inp.KEYCODE_RETURN: pygame.K_RETURN,
                    inp.KEYCODE_SPACE: pygame.K_SPACE, inp.KEYCODE_LEFT: pygame.K_LEFT,
                    inp.KEYCODE_RIGHT: pygame.K_RIGHT, inp.KEYCODE_UP: pygame.K_UP,
                    inp.KEYCODE_DOWN: pygame.K_DOWN, inp.KEYCODE_TAB: pygame.K_TAB,
                    inp.KEYCODE_F1: pygame.K_F1, inp.KEYCODE_F12: pygame.K_F12,
                    inp.KEYCODE_HOME: pygame.K_HOME, inp.KEYCODE_END: pygame.K_END,
                    inp.KEYCODE_PAGEUP: pygame.K_PAGEUP, inp.KEYCODE_PAGEDOWN: pygame.K_PAGEDOWN}
        for code, constant in expected.items():
            self.assertEqual(inp.Event(inp.KEY_DOWN, code=code).pygame_key(), constant)

    def test_modifiers(self):
        import pygame

        event = inp.Event(inp.KEY_DOWN, button=inp.MOD_SHIFT | inp.MOD_CTRL, code=ord('s'))
        self.assertEqual(event.pygame_mod(), pygame.KMOD_SHIFT | pygame.KMOD_CTRL)

    def test_mouse_events_carry_the_window_position(self):
        import pygame

        down = inp.to_pygame(inp.Event(inp.BUTTON_DOWN, button=3, x=640, y=400))
        self.assertEqual(down.type, pygame.MOUSEBUTTONDOWN)
        self.assertEqual(down.pos, (640, 400))
        self.assertEqual(down.button, 3)
        motion = inp.to_pygame(inp.Event(inp.MOTION, x=10, y=20))
        self.assertEqual(motion.type, pygame.MOUSEMOTION)
        self.assertEqual(motion.pos, (10, 20))

    def test_wheel_direction(self):
        import pygame

        up = inp.to_pygame(inp.Event(inp.WHEEL, button=1))
        down = inp.to_pygame(inp.Event(inp.WHEEL, button=0))
        self.assertEqual((up.type, up.y), (pygame.MOUSEWHEEL, 1))
        self.assertEqual((down.type, down.y), (pygame.MOUSEWHEEL, -1))

    def test_resize_focus_and_quit(self):
        import pygame

        resize = inp.to_pygame(inp.Event(inp.RESIZE, extra=(1600 << 16) | 900))
        self.assertEqual((resize.type, resize.width, resize.height),
                         (pygame.WINDOWRESIZED, 1600, 900))
        self.assertEqual(inp.to_pygame(inp.Event(inp.FOCUS_LOST)).type, pygame.WINDOWFOCUSLOST)
        self.assertEqual(inp.to_pygame(inp.Event(inp.QUIT)).type, pygame.QUIT)

    def test_a_batch_becomes_an_event_list(self):
        events = inp.decode_batch(batch((inp.KEY_DOWN, 0, ord('a'), 0, 0, 0),
                                        (inp.BUTTON_UP, 1, 0, 5, 6, 0)))
        converted = inp.to_pygame_batch(events)
        self.assertEqual(len(converted), 2)
        self.assertEqual(converted[1].pos, (5, 6))


class RingTransportTest(unittest.TestCase):
    """Input rides the same ring as frames; the reader must not replay or lose ordering."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from render_bridge import ring

        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'input.bin'
        self.ring = ring.Ring.create(self.path, slots=4, slot_bytes=4096)

    def tearDown(self):
        try:
            self.ring.close()
        finally:
            self.tmp.cleanup()

    def test_reader_sees_each_batch_once_in_order(self):
        reader = inp.InputReader(self.path)
        self.ring.publish(batch((inp.KEY_DOWN, 0, ord('a'), 0, 0, 0)))
        self.ring.publish(batch((inp.KEY_UP, 0, ord('a'), 0, 0, 0)))
        first = reader.read()
        self.assertEqual(len(first), 2)
        self.assertEqual([e[0].kind for e in first], [inp.KEY_DOWN, inp.KEY_UP])
        self.assertEqual(reader.read(), [])

    def test_reader_skips_batches_that_were_overwritten(self):
        reader = inp.InputReader(self.path)
        for _ in range(10):
            self.ring.publish(batch((inp.MOTION, 0, 0, 1, 1, 0)))
        batches = reader.read()
        self.assertEqual(len(batches), 4)          # the ring only holds four
        self.assertEqual(reader.dropped, 0)

    def test_reader_close_is_final(self):
        reader = inp.InputReader(self.path)
        reader.close()
        with self.assertRaises(Exception):
            reader.read()


if __name__ == '__main__':
    unittest.main()
