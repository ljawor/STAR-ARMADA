"""Surface-level checks: idle UI must not hide the battlefield.

No GL context needed: exercise the actual panel painters, not render/upload.
"""
import unittest

import pygame

from helpers import make_game
from render.hud import HUD


class CompactHUDTests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.hud = HUD(1280, 800, self.gm.state)

    def test_idle_side_panels_leave_battlefield_uncovered(self):
        for selection in (set(), {999999}):
            with self.subTest(selection=selection):
                self.hud.overlay.fill((0, 0, 0, 0))
                self.hud._left_panel(selection, 0)
                self.hud._right_panel(selection, 0)
                for x in (20, 300, 960, 1250):
                    for y in (200, 300, 460):
                        self.assertEqual(self.hud.overlay.get_at((x, y)).a, 0,
                                         'idle cards cover empty battlefield')
                self.assertGreater(self.hud.overlay.get_at((30, 70)).a, 0)
                self.assertGreater(self.hud.overlay.get_at((970, 70)).a, 0)


    def test_short_event_log_is_bottom_anchored_and_content_sized(self):
        self.gm.state.events.log.clear()
        self.gm.state.events.publish('station_built', station='shipyard', owner=0)
        self.hud._event_log(0)
        self.assertEqual(self.hud.overlay.get_at((25, 600)).a, 0,
                         'one event reserves nine rows of screen space')
        self.assertGreater(self.hud.overlay.get_at((25, 770)).a, 0)


    def test_selected_constructor_keeps_inspector_and_build_buttons(self):
        e = next(e for e in self.gm.state.entities.values()
                 if e.owner == 0 and e.is_construction)
        self.hud._left_panel({e.id}, 0)
        self.hud._right_panel({e.id}, 0)
        self.assertGreater(self.hud.overlay.get_at((30, 460)).a, 0)
        self.assertGreater(self.hud.overlay.get_at((970, 460)).a, 0)
        self.assertTrue(any(b['kind'] == 'build_station_place'
                            for b in self.hud.buttons))

    def test_full_event_log_preserves_nine_rows(self):
        self.gm.state.events.log.clear()
        for i in range(12):
            self.gm.state.events.publish('station_built', station=f'station_{i}', owner=0)
        self.hud._event_log(0)
        self.assertGreater(self.hud.overlay.get_at((25, 600)).a, 0)
        self.assertGreater(self.hud.overlay.get_at((25, 770)).a, 0)
        self.assertEqual(self.hud.overlay.get_at((25, 580)).a, 0)

    def test_idle_cards_after_resize(self):
        self.hud.resize(1920, 1080)
        self.hud._left_panel(set(), 0)
        self.hud._right_panel(set(), 0)
        self.assertEqual(self.hud.overlay.get_at((30, 250)).a, 0)
        self.assertEqual(self.hud.overlay.get_at((1610, 250)).a, 0)
        self.assertGreater(self.hud.overlay.get_at((1610, 70)).a, 0)


if __name__ == '__main__':
    unittest.main()
