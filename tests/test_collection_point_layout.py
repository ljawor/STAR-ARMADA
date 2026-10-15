"""Small-window station controls, driven through production input and wheel routing."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pygame
from helpers import make_game
from game.core.vectors import Vec3
from game.net.lan import precise_checksum
from render.camera import Camera
from render.hud import HUD
from render.input import InputController


class CollectionPointLayout(unittest.TestCase):
    def setUp(self):
        owned = not pygame.font.get_init()
        if owned:
            pygame.font.init()
            def close_fonts():
                from render import clean_classic
                clean_classic.font.cache_clear()
                pygame.font.quit()
            self.addCleanup(close_fonts)
        self.gm = make_game(ai=False)
        self.yard = self.gm.factory.spawn_station('shipyard', 0, Vec3(6000, 0, 6000))
        self.hud = HUD(800, 600, self.gm.state)
        self.ctrl = InputController(self.gm.state, Camera(800, 600), self.hud,
                                    SimpleNamespace(flash=lambda *_: None))
        self.ctrl.selection = {self.yard.id}

    def draw(self):
        self.hud.buttons = []
        self.hud.scroll_rects = []
        self.hud.blocked_rects = []
        self.hud.overlay.fill((0, 0, 0, 0))
        self.hud._right_panel(self.ctrl.selection, 0)
        panel = self.hud.blocked_rects[0]
        self.assertLessEqual(panel.bottom, self.hud.height - 230, 'actions must clear the minimap')
        rects = [b['rect'] for b in self.hud.buttons]
        self.assertTrue(all(panel.contains(r) for r in rects))
        self.assertFalse(any(a.colliderect(b) for i, a in enumerate(rects) for b in rects[i + 1:]))
        for viewport, _ in self.hud.scroll_rects:
            self.assertTrue(all(viewport.contains(rect) for rect in rects
                                if viewport.colliderect(rect)), 'clipped controls must have no hitbox')

    def wheel(self, rect, direction=-1):
        with patch('pygame.mouse.get_pos', return_value=rect.center):
            self.ctrl.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=direction, x=0))
        self.draw()

    def rewind(self):
        for _ in range(30):
            self.draw()
            for rect, _ in list(self.hud.scroll_rects):
                self.wheel(rect, direction=1)

    def reachable(self, kind, predicate=lambda b: True):
        for _ in range(30):
            self.draw()
            found = [b for b in self.hud.buttons if b['kind'] == kind and predicate(b)]
            if found:
                return found[0]
            regions = list(self.hud.scroll_rects)
            for rect, _ in regions:
                self.wheel(rect)
        self.fail(f'{kind} cannot be reached with the natural wheel regions')

    def click(self, button):
        for event in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self.ctrl.handle_event(pygame.event.Event(event, button=1, pos=button['rect'].center))
        self.gm.commands.consume()

    def test_set_point_pending_refit_and_build_keep_every_ship_naturally_reachable(self):
        self.yard.collection_point = Vec3(7000, 0, 7000)
        self.yard.upgrade_level = 4
        self.yard.build_queue = [dict(kind='station_upgrade', item='shipyard', time_left=100),
                                 dict(kind='ship', item='imperial_corvette', time_left=100),
                                 dict(kind='ship', item='imperial_corvette', time_left=100)]
        p = self.gm.state.players[0]
        p.credits = p.materials = p.energy = p.crew = 100000
        expected = {d.id for d in self.hud._shipyard_items(self.yard, self.gm.ds.stations['shipyard'])
                    if self.gm.construction.station_can_build_ship(self.yard, d.id)}
        before = precise_checksum(self.gm)
        seen = set()
        for _ in range(30):
            self.draw()
            seen.update(b['payload']['ship_id'] for b in self.hud.buttons if b['kind'] == 'build_ship')
            for rect, key in list(self.hud.scroll_rects):
                if key == 'ships':
                    self.wheel(rect)
        self.assertEqual(seen, expected, 'collection/refit/queue header must not strand production')
        self.assertEqual(precise_checksum(self.gm), before, 'view and scrolling must not mutate sim')
        self.reachable('collection_clear')
        self.reachable('cancel_build', lambda b: b['payload']['index'] == 1)
        self.click(self.reachable('cancel_build', lambda b: b['payload']['index'] == 0))
        self.assertEqual(len(self.yard.build_queue), 2)
        self.assertTrue(all(q['kind'] == 'ship' for q in self.yard.build_queue))

    def test_mixed_constructor_three_queued_ships_keeps_all_controls_wheel_reachable(self):
        builder = self.gm.factory.spawn_ship('imperial_constructor', 0, Vec3(6100, 0, 6000))
        for width, height in ((800, 600), (1024, 768), (1280, 800), (1920, 1080)):
            with self.subTest(size=(width, height)):
                self.yard.collection_point = Vec3(7000, 0, 7000)
                self.yard.build_queue = [dict(kind='ship', item='imperial_corvette', time_left=100)
                                         for _ in range(3)]
                p = self.gm.state.players[0]
                p.credits = p.materials = p.energy = p.crew = 100000
                self.hud = HUD(width, height, self.gm.state)
                self.ctrl.hud = self.hud
                self.ctrl.selection = {self.yard.id, builder.id}
                expected_ships = {
                    d.id for d in self.hud._shipyard_items(self.yard, self.gm.ds.stations['shipyard'])
                    if self.gm.construction.station_can_build_ship(self.yard, d.id)}
                before = precise_checksum(self.gm)
                seen = set()
                ships = set()
                cancels = set()
                for _ in range(30):
                    self.draw()
                    seen.update(b['kind'] for b in self.hud.buttons)
                    ships.update(b['payload']['ship_id'] for b in self.hud.buttons
                                 if b['kind'] == 'build_ship')
                    cancels.update(b['payload']['index'] for b in self.hud.buttons
                                   if b['kind'] == 'cancel_build')
                    for rect, key in list(self.hud.scroll_rects):
                        if key == 'ships':
                            self.assertGreaterEqual(rect.height, 54, 'reserve a fully usable production row')
                        if key == 'station_details':
                            if (width, height) == (800, 600):
                                self.assertEqual(rect.height, 28, 'exercise the smallest viewport')
                            self.assertTrue(all(rect.contains(b['rect']) for b in self.hud.buttons
                                                if b['kind'] in ('collection_clear', 'upgrade_station')))
                        self.wheel(rect)
                self.assertIn('upgrade_station', seen, 'mixed repair header must not strand refit')
                self.assertIn('collection_clear', seen)
                self.assertIn('repair', seen)
                self.assertEqual(cancels, {0, 1, 2})
                self.assertEqual(ships, expected_ships, 'keep the usable production reserve')
                self.assertEqual(precise_checksum(self.gm), before, 'wheel input is read-only')
                # Return to the top with real wheel input, not direct scroll mutation.
                self.rewind()
                self.click(self.reachable('upgrade_station'))
                self.assertEqual(self.yard.build_queue[-1]['kind'], 'station_upgrade')
                self.rewind()
                self.click(self.reachable('cancel_build', lambda b: b['payload']['index'] == 3))
                self.assertEqual([q['kind'] for q in self.yard.build_queue], ['ship'] * 3)
                self.rewind()
                self.click(self.reachable('collection_clear'))
                self.assertIsNone(self.yard.collection_point)
                self.click(self.reachable('cancel_build', lambda b: b['payload']['index'] == 2))
                self.assertEqual([q['kind'] for q in self.yard.build_queue], ['ship'] * 2)

    def test_empty_and_set_point_can_buy_refit_build_and_clear(self):
        for point in (None, Vec3(7000, 0, 7000)):
            with self.subTest(point=point):
                self.yard.collection_point = point
                self.yard.build_queue.clear()
                self.hud.scroll.clear()
                self.click(self.reachable('upgrade_station'))
                self.assertTrue(self.yard.build_queue)
                self.click(self.reachable('build_ship'))
                self.assertTrue(any(q['kind'] == 'ship' for q in self.yard.build_queue))
                if point is not None:
                    self.click(self.reachable('collection_clear'))
                    self.assertIsNone(self.yard.collection_point)


if __name__ == '__main__':
    unittest.main()
