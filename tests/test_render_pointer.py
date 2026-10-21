"""W07: the pointer picks what the player can see, through the same controller a native click uses.

The window publishes events, `RingInput` turns them into pygame events, `InputController` handles
them. Each of those three steps is tested on its own; this test pins the join, because a click that
travels correctly and lands on nothing looks exactly like a click that never travelled.
"""
import unittest
from types import SimpleNamespace

import pygame

from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.unit_factory import UnitFactory
from render.camera import Camera
from render.input import InputController


class PointerTests(unittest.TestCase):
    def setUp(self):
        DataStore.reset()
        self.st = GameManager.start_skirmish(DataStore.get().maps['skirmish01']).state
        self.st.entities.clear()
        self.factory = UnitFactory(self.st)
        self.station = self.factory.spawn_station('command_station', 0, Vec3(0, 0, 0))
        self.fighter = self.factory.spawn_ship('imperial_corvette', 0, Vec3(420, 0, 260))
        self.camera = Camera(1280, 800)
        self.camera.target = [0.0, 0.0, 0.0]
        self.camera.distance, self.camera.pitch, self.camera.yaw = 1600.0, 55.0, 45.0
        # The real HUD: a click has to survive the panels it is drawn under, and a stub would
        # decide that for us.
        font_owned = not pygame.font.get_init()
        if font_owned:
            from render import clean_classic
            self.addCleanup(pygame.font.quit)
            self.addCleanup(clean_classic.font.cache_clear)
        from render.hud import HUD
        self.hud = HUD(1280, 800, self.st)
        self.flashes = []
        self.ctrl = InputController(self.st, self.camera, self.hud,
                                    SimpleNamespace(flash=self.flashes.append,
                                                    local_player=0, pause=False, exit=False))

    def click(self, pos, button=1):
        for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self.ctrl.handle_event(pygame.event.Event(kind, button=button, pos=pos))

    def screen_position(self, entity):
        at = entity.pos
        found = self.camera.world_to_screen(at.x, at.y, at.z)
        self.assertIsNotNone(found, "the fixture entity is off screen; the test proves nothing")
        return found

    def test_a_click_on_a_ship_selects_that_ship(self):
        self.click(self.screen_position(self.fighter))
        self.assertEqual(self.ctrl.selection, {self.fighter.id})

    def test_a_click_on_empty_space_clears_the_selection(self):
        self.ctrl.selection = {self.fighter.id}
        self.click((40, 700))
        self.assertEqual(self.ctrl.selection, set())

    def test_a_click_on_the_minimap_is_not_a_world_click(self):
        """The minimap is drawn over the world; a click on it moves the camera, never selects."""
        # The HUD sets this rect while drawing; here the test decides where the corner sits.
        self.hud.minimap_rect = pygame.Rect(1010, 560, 250, 220)
        self.ctrl.selection = {self.fighter.id}
        before = list(self.camera.target)
        # A corner of the minimap, not its centre: the centre is the world origin, which is
        # already where the camera looks, so a pan there would pass for no pan at all.
        self.click((self.hud.minimap_rect.left + 12, self.hud.minimap_rect.top + 12))
        # A minimap click pans the camera; it must not also be read as a world click.
        self.assertEqual(self.ctrl.selection, {self.fighter.id})
        self.assertNotEqual(list(self.camera.target), before)


if __name__ == '__main__':
    unittest.main()
