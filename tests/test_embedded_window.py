import unittest
import pygame
from render_bridge import embedded


class EmbeddedPointerTests(unittest.TestCase):
    def test_original_window_coordinates_map_to_presented_hud(self):
        event = pygame.event.Event(pygame.MOUSEMOTION, pos=(900, 450), rel=(18, 9), buttons=(0, 0, 1))
        mapped = embedded.map_pointer_event(event, (1440, 900), (1280, 800))
        self.assertEqual(mapped.pos, (800, 400))
        self.assertEqual(mapped.rel, (16, 8))
        self.assertTrue(mapped.remote)
        self.assertEqual(event.pos, (900, 450))

    def test_key_and_already_remote_event_are_not_remapped(self):
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F5)
        self.assertIs(embedded.map_pointer_event(event, (1440, 900), (1280, 800)), event)
        event = pygame.event.Event(pygame.MOUSEMOTION, pos=(400, 200), remote=True)
        self.assertIs(embedded.map_pointer_event(event, (1440, 900), (1280, 800)), event)
