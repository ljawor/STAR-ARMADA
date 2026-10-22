"""Natural ring pointer gestures must retain the local controller's semantics."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import pygame
from game.core.manager import GameManager
from game.data.store import DataStore
from render.camera import Camera
from render.hud import HUD
from render.input import InputController
from render.input_bridge import RingInput
from render_bridge import input as wire, ring


class HybridPointerTests(unittest.TestCase):
    def setUp(self):
        previous = DataStore._instance
        self.addCleanup(setattr, DataStore, '_instance', previous)
        self.gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
        self.camera = Camera(1280, 800)
        # Unprojection is analytic after apply; avoid its GL initialization in this CPU fixture.
        self.camera._view = self.camera._proj = ()
        # This test owns no display, audio or persistent user data.
        if not pygame.font.get_init():
            pygame.font.init()
        self.hud = HUD(1280, 800, self.gm.state)
        self.addCleanup(self.hud.close)
        self.controller = InputController(self.gm.state, self.camera, self.hud,
            SimpleNamespace(flash=lambda *_: None, toggle_pause=lambda: None))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'input.ring'
        self.writer = ring.Ring.create(path, slots=8, slot_bytes=4096)
        self.addCleanup(self.writer.close)
        self.bridge = RingInput(path, self.controller, (1280, 800))
        self.addCleanup(self.bridge.close)

    def send(self, *events):
        self.writer.publish(wire.encode_batch(events))
        self.bridge.poll()

    def test_right_drag_rotates_both_axes_in_hud_pixels_and_release_stops(self):
        yaw, pitch = self.camera.yaw, self.camera.pitch
        self.send(wire.Event(wire.RESIZE, extra=(2560 << 16) | 1600),
                  wire.Event(wire.BUTTON_DOWN, button=3, x=1200, y=800),
                  wire.Event(wire.MOTION, button=4, x=1280, y=840))
        self.assertAlmostEqual(self.camera.yaw, yaw - 10)
        self.assertAlmostEqual(self.camera.pitch, pitch - 3.6)
        self.send(wire.Event(wire.BUTTON_UP, button=3, x=1280, y=840))
        pose = self.camera.yaw, self.camera.pitch
        self.send(wire.Event(wire.MOTION, x=1400, y=1000))
        self.assertEqual((self.camera.yaw, self.camera.pitch), pose)

    def test_focus_loss_discards_pointer_anchor_before_a_new_motion(self):
        seen = []
        self.controller.handle_event = seen.append
        self.send(wire.Event(wire.MOTION, x=1200, y=700),
                  wire.Event(wire.FOCUS_LOST),
                  wire.Event(wire.MOTION, x=10, y=10))
        self.assertEqual(seen[-1].rel, (0, 0))

    def test_resize_discards_old_coordinate_space_before_a_new_motion(self):
        seen = []
        self.controller.handle_event = seen.append
        self.send(wire.Event(wire.MOTION, x=1200, y=700),
                  wire.Event(wire.RESIZE, extra=(2560 << 16) | 1600),
                  wire.Event(wire.MOTION, x=1200, y=700))
        self.assertEqual(seen[-1].rel, (0, 0))

    def test_tutorial_wheel_uses_event_position_without_hidden_cursor(self):
        from render.presentation import PresentationOverlay
        overlay = PresentationOverlay(1280, 800)
        self.addCleanup(overlay.cleanup)
        overlay.panel_rects = [pygame.Rect(400, 50, 400, 150)]
        event = pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1, pos=(500, 100), remote=True)
        with patch('pygame.display.get_init', return_value=True), \
             patch('pygame.mouse.get_pos', side_effect=AssertionError('hidden cursor queried')):
            self.assertTrue(overlay.handle_event(event))

    def test_local_pointer_events_restore_local_placement_authority(self):
        builder = next(e for e in self.gm.state.entities.values()
                       if e.owner == 0 and e.is_ship)
        events = [
            pygame.event.Event(pygame.MOUSEMOTION, pos=(700, 450), rel=(0, 0)),
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2, pos=(700, 450)),
            pygame.event.Event(pygame.MOUSEBUTTONUP, button=2, pos=(700, 450)),
            pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1),
        ]
        for event in events:
            with self.subTest(event=event.type):
                self.hud.placement = {'station_kind': 'mining_station', 'builder_id': builder.id}
                self.send(wire.Event(wire.MOTION, x=620, y=400))
                self.assertEqual(self.controller.remote_pointer, (620, 400))
                with patch('pygame.mouse.get_pos', return_value=(700, 450)):
                    self.controller.handle_event(event)
                    self.controller.update_placement()
                self.assertEqual((self.hud.placement['ghost']['sx'],
                                  self.hud.placement['ghost']['sy']), (700, 450))
                self.assertIsNone(self.controller.remote_pointer)

    def test_reset_clears_native_pointer_before_local_event(self):
        from test_hybrid_main import helpers
        builder = next(e for e in self.gm.state.entities.values()
                       if e.owner == 0 and e.is_ship)
        self.hud.placement = {'station_kind': 'mining_station', 'builder_id': builder.id}
        self.send(wire.Event(wire.MOTION, x=620, y=400))
        env = helpers('cpp_reset', CPP={}, inputc=self.controller)
        env['cpp_reset']()
        self.assertIsNone(self.controller.remote_pointer)
        with patch('pygame.mouse.get_pos', return_value=(700, 450)):
            self.controller.update_placement()
        self.assertEqual((self.hud.placement['ghost']['sx'],
                          self.hud.placement['ghost']['sy']), (700, 450))

    def test_placement_uses_bridged_pointer_not_hidden_window_cursor(self):
        builder = next(e for e in self.gm.state.entities.values()
                       if e.owner == 0 and e.is_ship)
        self.hud.placement = {'station_kind': 'mining_station', 'builder_id': builder.id}
        self.send(wire.Event(wire.MOTION, x=620, y=400))
        with patch('pygame.mouse.get_pos', side_effect=AssertionError('hidden cursor queried')):
            self.controller.update_placement()
        self.assertEqual((self.hud.placement['ghost']['sx'],
                          self.hud.placement['ghost']['sy']), (620, 400))


if __name__ == '__main__':
    unittest.main()
