"""W04: events from the window's ring reach the real controller and change real state.

These run against a live `GameManager` skirmish and the production `InputController`, not a
lookalike: the point of the package is that the migration adds no second input path, so the
evidence has to be the same controller the game already trusts (`tests/test_input_controls.py`
exercises it from native pygame events; this file exercises it from the bridge).
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pygame

from game.core.manager import GameManager
from game.data.store import DataStore
from render.camera import Camera
from render.input import InputController
from render.input_bridge import RingInput
from render_bridge import input as wire
from render_bridge import ring


def key(code, down=True, mod=0):
    return wire.Event(wire.KEY_DOWN if down else wire.KEY_UP, mod, code, 0, 0, 0)


class BridgeTest(unittest.TestCase):
    def setUp(self):
        DataStore.reset()
        self.gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
        self.state = self.gm.state
        self.camera = Camera(1280, 800)
        self.hud = SimpleNamespace(placement=None, fleet_panel=False,
                                   fleet_formation='line', fleet_commander=None,
                                   buttons=[], minimap_rect=None, scroll_rects=[])
        self.paused = False
        self.messages = []
        app = SimpleNamespace(toggle_pause=self._toggle_pause,
                              request_exit=lambda: None,
                              flash=self.messages.append)
        self.controller = InputController(self.state, self.camera, self.hud, app)
        self.ship = next(e for e in self.state.entities.values()
                         if e.owner == 0 and e.alive and e.is_ship)
        self.controller.selection = {self.ship.id}

        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'input.bin'
        self.ring = ring.Ring.create(self.path, slots=8, slot_bytes=4096)

    def _toggle_pause(self):
        self.paused = not self.paused

    def tearDown(self):
        try:
            self.ring.close()
        finally:
            self.tmp.cleanup()

    def publish(self, *events):
        self.ring.publish(wire.encode_batch(events))

    def bridge(self, **kwargs):
        return RingInput(self.path, self.controller, (1280, 800), **kwargs)

    # -- the controller is the one that acts ---------------------------------
    def test_a_space_key_from_the_window_follows_the_selection(self):
        self.assertIsNone(self.camera.follow_id)
        self.publish(key(ord(' ')))
        with self.bridge(from_oldest=True) as bridge:
            self.assertEqual(bridge.poll(), 1)
        self.assertEqual(self.camera.follow_id, self.ship.id)

    def test_the_key_is_released_when_the_window_says_so(self):
        self.publish(key(ord('q'), down=True))
        with self.bridge(from_oldest=True) as bridge:
            bridge.poll()
        before = self.camera.yaw
        self.controller.update(1 / 30)
        self.assertNotEqual(self.camera.yaw, before)
        self.publish(key(ord('q'), down=False))
        with self.bridge(from_oldest=True) as bridge:
            bridge.poll()
        stopped = self.camera.yaw
        self.controller.update(1 / 30)
        self.assertEqual(self.camera.yaw, stopped)

    def test_escape_reaches_the_registered_handler(self):
        self.publish(key(wire.KEYCODE_ESCAPE))
        with self.bridge(from_oldest=True) as bridge:
            bridge.poll()
        # Escape is the pause key in the stock controller; whatever it does, it must be the
        # controller that decided, not the bridge.
        self.assertTrue(self.paused or self.messages)

    def test_quit_event_is_not_forwarded_as_a_quit_command(self):
        self.publish(wire.Event(wire.QUIT))
        with self.bridge(from_oldest=True) as bridge:
            delivered = bridge.poll()
            self.assertTrue(bridge.quit_requested)
        self.assertEqual(delivered, 0)

    # -- coordinates ---------------------------------------------------------
    def test_pointer_pixels_scale_onto_the_hud_surface(self):
        recorded = {}
        self.controller.handle_event = lambda event: recorded.setdefault(event.type, event)
        self.publish(wire.Event(wire.RESIZE, extra=(2560 << 16) | 1600),
                     wire.Event(wire.BUTTON_DOWN, button=1, x=1280, y=800))
        with self.bridge(from_oldest=True) as bridge:
            bridge.poll()
        self.assertEqual(recorded[pygame.MOUSEBUTTONDOWN].pos, (640, 400))
        self.assertEqual(bridge.window_size, (2560, 1600))

    def test_a_same_size_window_is_not_rescaled(self):
        recorded = {}
        self.controller.handle_event = lambda event: recorded.setdefault(event.type, event)
        self.publish(wire.Event(wire.MOTION, x=321, y=654))
        with self.bridge(from_oldest=True) as bridge:
            bridge.poll()
        self.assertEqual(recorded[pygame.MOUSEMOTION].pos, (321, 654))

    # -- sampling ------------------------------------------------------------
    def test_poll_delivers_each_batch_once(self):
        self.publish(key(ord('a')))
        self.publish(key(ord('b')))
        with self.bridge(from_oldest=True) as bridge:
            self.assertEqual(bridge.poll(), 2)
            self.assertEqual(bridge.poll(), 0)
        self.assertEqual(bridge.report()['events_delivered'], 2)

    def test_a_reader_that_attaches_late_does_not_replay_old_clicks(self):
        for _ in range(3):
            self.publish(key(ord('m')))
        with self.bridge() as bridge:
            self.assertEqual(bridge.poll(), 0)

    def test_falling_a_whole_ring_behind_is_reported_not_hidden(self):
        with self.bridge() as bridge:
            for _ in range(12):
                self.publish(key(ord('a')))
            bridge.poll()
            # Eight slots, twelve batches: four batches were overwritten before anyone read
            # them, and the bridge says so instead of pretending it saw every click.
            self.assertEqual(bridge.report()['batches_skipped'], 4)

    def test_unknown_key_codes_are_counted_not_dropped_silently(self):
        self.publish(key(0x1FFF))
        with self.bridge(from_oldest=True) as bridge:
            self.assertEqual(bridge.poll(), 0)
            self.assertEqual(bridge.report()['unmapped'], 1)


if __name__ == '__main__':
    unittest.main()
