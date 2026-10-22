"""The ring that fills around a station site while it is being built.

Pixel-level, because the point of the ring is that a player can see progress without opening a panel, and
a test that only counted draw calls would pass with the ring drawn off-screen or at zero size.
"""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pygame

from game.core.state import GameState, PlayerState
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.construction import ConstructionSystem
from game.systems.unit_factory import UnitFactory
from render.hud import HUD

SITE = Vec3(0.0, 0.0, 0.0)
WIDTH, HEIGHT = 1280, 800
CENTRE = (640, 400)


class _Camera:
    """Flat projection: world x/z map linearly to pixels around screen centre, so the ring's geometry is
    predictable without a GL context. Only the projection is stubbed; everything drawn is the real HUD."""

    width, height = WIDTH, HEIGHT

    def world_to_screen(self, x, y, z):
        return (CENTRE[0] + x * 0.5, CENTRE[1] + z * 0.5)

    def basis(self):
        return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


class ConstructionProgressTests(unittest.TestCase):
    def setUp(self):
        scratch = Path.home() / '.hermes/cache/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='construct-ring-', dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        from render import menus
        for key, value in dict(USER_DIR=Path(self.tmp.name),
                SAVES_DIR=Path(self.tmp.name) / 'saves',
                SETTINGS_PATH=Path(self.tmp.name) / 'settings.json',
                CAMPAIGN_PATH=Path(self.tmp.name) / 'campaign.json',
                BALANCE_PATH=Path(self.tmp.name) / 'balance.json').items():
            owner = patch.object(menus, key, str(value))
            owner.start()
            self.addCleanup(owner.stop)
        original_store = DataStore._instance
        self.addCleanup(setattr, DataStore, '_instance', original_store)
        DataStore.reset()
        self.st = GameState()
        self.st.players[0] = PlayerState(0, faction='rebel', credits=100000,
            materials=100000, energy=100000, crew=100000, command_capacity=100)
        factory = UnitFactory(self.st)
        self.builder = factory.spawn_ship('rebel_constructor', 0, Vec3(-400.0, 0.0, -400.0))
        self.cs = ConstructionSystem(self.st)
        self.cs.factory = factory
        self.st._construction_system = self.cs
        self.pay()

    def pay(self, station='trade_station'):
        self.assertTrue(self.cs.start_station(self.builder.id, station, SITE, 0))
        self.assertTrue(self.builder.build_queue)

    def overlay(self):
        hud = HUD(WIDTH, HEIGHT, self.st)
        hud.set_camera_ref(_Camera())
        hud.compose(set(), None, 0, False)
        return hud.overlay

    def ring_pixels(self, overlay):
        """Pixel count of anything drawn inside the projection of the site."""
        raw = pygame.image.tostring(overlay, 'RGBA')
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(HEIGHT, WIDTH, 4)
        box = frame[CENTRE[1] - 90:CENTRE[1] + 90, CENTRE[0] - 90:CENTRE[0] + 90]
        return int((box[:, :, 3] > 0).sum())

    def set_progress(self, fraction):
        item = self.builder.build_queue[0]
        item['time_left'] = item['total'] * (1.0 - fraction)
        self.builder.build_queue[0] = item

    def test_a_site_with_nothing_queued_draws_no_ring(self):
        self.builder.build_queue.clear()
        self.assertEqual(self.ring_pixels(self.overlay()), 0,
                         'empty space at the site must stay empty')

    def test_the_ring_appears_while_a_station_is_being_built(self):
        self.set_progress(0.5)
        self.assertGreater(self.ring_pixels(self.overlay()), 0,
                           'a paid site must show its progress where the station will stand')

    def test_the_ring_fills_as_the_work_progresses(self):
        self.set_progress(0.08)
        early = self.ring_pixels(self.overlay())
        self.set_progress(0.92)
        late = self.ring_pixels(self.overlay())
        self.assertGreater(late, early * 1.5,
                           f'progress must be visible in the ring, not just in a side panel: {early} -> {late}')

    def test_the_ring_is_not_drawn_for_another_players_site(self):
        self.set_progress(0.5)
        self.st.players[1] = PlayerState(1, faction='imperial')
        self.builder.owner = 1
        self.assertEqual(self.ring_pixels(self.overlay()), 0,
                         'an enemy site must not advertise its progress')
        self.builder.owner = 0

    def test_a_ring_is_drawn_for_every_site_not_just_the_first(self):
        one = self.ring_pixels(self.overlay())
        # Far enough apart to clear the trade-station spacing rule, close enough to still be on screen.
        second = UnitFactory(self.st).spawn_ship('rebel_constructor', 0, Vec3(1400.0, 0.0, 0.0))
        self.assertTrue(self.cs.start_station(second.id, 'trade_station', Vec3(1600.0, 0.0, 0.0), 0))
        for builder in (self.builder, second):
            builder.build_queue[0]['time_left'] = builder.build_queue[0]['total'] * 0.4
        self.assertGreater(self.ring_pixels(self.overlay()), one,
                           'the second site must get its own ring')
    def test_the_ring_lands_on_the_site_the_camera_projects(self):
        """The ring has to be drawn where the model stands, not just somewhere on screen."""
        from render.camera import Camera

        def painted(state_progress):
            camera = Camera(WIDTH, HEIGHT)
            camera.target = [0.0, 0.0, 0.0]
            camera.distance = 900.0
            camera.pitch = 40.0
            camera.yaw = 35.0
            hud = HUD(WIDTH, HEIGHT, self.st)
            hud.set_camera_ref(camera)
            if state_progress is None:
                self.builder.build_queue.clear()
            else:
                self.set_progress(state_progress)
            hud.compose(set(), None, 0, False)
            raw = pygame.image.tostring(hud.overlay, 'RGBA')
            return camera, np.frombuffer(raw, dtype=np.uint8).reshape(HEIGHT, WIDTH, 4)

        camera, without = painted(None)
        self.pay('trade_station')          # put the order back for the "with ring" frame
        camera, with_ring = painted(0.7)
        # Panels are identical in both frames, so whatever changed is the ring.
        changed = (with_ring[:, :, 3] > 0) & (without[:, :, 3] == 0)
        ys, xs = np.nonzero(changed)
        self.assertGreater(len(xs), 200, 'the ring was not drawn at the site')
        sx, sy = camera.world_to_screen(SITE.x, SITE.y, SITE.z)
        self.assertLess(abs(xs.mean() - sx), 30.0,
                        f'ring drawn at x={xs.mean():.0f}, site projects to x={sx:.0f}')
        self.assertLess(abs(ys.mean() - sy), 30.0,
                        f'ring drawn at y={ys.mean():.0f}, site projects to y={sy:.0f}')


if __name__ == '__main__':
    unittest.main()
