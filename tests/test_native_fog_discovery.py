"""Discovery→mask→live ring checks; real gameplay sensors, no GL/native window."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import game.core
from game.core.state import GameState, PlayerState
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.unit_factory import UnitFactory
from game.systems.visibility import VisibilitySystem
from render.fog import FogMask
from render_bridge import fogmap, ring


class NativeFogDiscoveryTests(unittest.TestCase):
    def setUp(self):
        import pygame
        from render import menus
        self.temp = tempfile.TemporaryDirectory(dir=Path.home() / '.hermes/cache/scratch')
        self.addCleanup(self.temp.cleanup)
        for key, name in [('USER_DIR', ''), ('SAVES_DIR', 'saves'),
                          ('SETTINGS_PATH', 'settings.json'), ('CAMPAIGN_PATH', 'campaign.json'),
                          ('BALANCE_PATH', 'balance.json')]:
            owner = patch.object(menus, key, str(Path(self.temp.name) / name))
            owner.start(); self.addCleanup(owner.stop)
        old = DataStore._instance
        self.addCleanup(setattr, DataStore, '_instance', old)
        DataStore.reset()
        pygame.font.init()
        self.state = GameState()
        self.state.map_info.bounds = 30000
        self.state.players[0] = PlayerState(0, faction='imperial')
        self.state.players[1] = PlayerState(1, faction='rebel')
        self.factory = UnitFactory(self.state)
        self.visibility = VisibilitySystem(self.state)

    def source(self, kind, owner=0):
        position = Vec3(-9000, 0, -4000)
        if kind == 'ship':
            return self.factory.spawn_ship('imperial_corvette', owner, position)
        return self.factory.spawn_station('sensor_station', owner, position)

    @staticmethod
    def alpha(mask, point):
        n, bounds = mask['cells'], mask['bounds']
        x = min(n - 1, max(0, int((point.x + bounds / 2) / bounds * n)))
        z = min(n - 1, max(0, int((point.z + bounds / 2) / bounds * n)))
        return mask['rgba'][(z * n + x) * 4 + 3]

    def test_ships_and_stations_reveal_move_and_retain_charted_ground(self):
        import pygame
        for kind in ['ship', 'station']:
            with self.subTest(kind=kind):
                self.state.entities.clear()
                self.state.explored_cells.clear()
                source = self.source(kind)
                self.visibility.update()
                fog = FogMask()
                first = fog.surface(self.state, 0)
                before = self.state.to_dict(precise=True)
                self.assertIs(fog.surface(self.state, 0), first)
                self.assertEqual(before, self.state.to_dict(precise=True))
                old_position = Vec3(*source.pos.to_tuple())
                target = Vec3(9000, 0, 5000)
                initial = dict(cells=first.get_width(), bounds=self.state.map_info.bounds,
                               rgba=pygame.image.tobytes(first, 'RGBA', False))
                self.assertEqual(self.alpha(initial, old_position), 0)
                self.assertEqual(self.alpha(initial, target), 255)
                source.pos = target
                self.visibility.update()
                moved = fog.surface(self.state, 0)
                self.assertIsNot(first, moved)
                changed = dict(cells=moved.get_width(), bounds=self.state.map_info.bounds,
                               rgba=pygame.image.tobytes(moved, 'RGBA', False))
                self.assertEqual(self.alpha(changed, target), 0)
                self.assertEqual(self.alpha(changed, old_position), 155)

    def test_live_ring_republishes_discovery_for_ship_and_new_station(self):
        from render_bridge.live import LiveSession
        source = self.source('ship')
        self.visibility.update()
        session = LiveSession(self.state, DataStore.get(), directory=Path(self.temp.name) / 'rings',
                              size=(320, 200), planet_texture=16)
        self.addCleanup(session.close)
        reader = ring.Ring.open(session.paths['fog']); self.addCleanup(reader.close)
        session.publish(self.state, visible_ids={source.id})
        first = fogmap.decode(reader.latest()[1])
        source.pos = Vec3(9000, 0, 5000)
        self.visibility.update()
        session.publish(self.state, visible_ids={source.id})
        second = fogmap.decode(reader.latest()[1])
        self.assertGreater(second['generation'], first['generation'])
        self.assertNotEqual(first['rgba'], second['rgba'])
        self.assertEqual(self.alpha(second, source.pos), 0)
        station = self.source('station')
        self.visibility.update()
        session.publish(self.state, visible_ids={source.id, station.id})
        third = fogmap.decode(reader.latest()[1])
        self.assertGreater(third['generation'], second['generation'])
        self.assertEqual(self.alpha(third, station.pos), 0)
        self.assertEqual(self.alpha(third, source.pos), 0)
        unchanged = reader.published
        session.publish(self.state, visible_ids={source.id, station.id})
        self.assertEqual(reader.published, unchanged)

    def test_enemy_sensor_does_not_reveal_our_mask(self):
        source = self.source('station', owner=1)
        self.visibility.update()
        self.assertFalse(self.state.is_position_visible(0, source.pos))
        self.assertEqual(FogMask().surface(self.state, 0).get_at((12, 22)).a, 255)


if __name__ == '__main__':
    unittest.main()
