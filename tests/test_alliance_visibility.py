"""Verify existing allied AI detection/view contracts without broadening control."""
import unittest
from types import SimpleNamespace

import helpers
from game.core.entity import Entity
from game.core.state import PlayerState
from game.core.vectors import Vec3
from render.fog import FogMask, known_entities
from render.hud import HUD
from render.input import InputController


class AllianceVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.gm = helpers.make_game(ai=False)
        self.st = self.gm.state
        self.st.entities.clear()
        self.st.explored_cells.clear()
        self.st.discovered_planets.clear()
        self.st.players = {0: PlayerState(0, team=1),
                           1: PlayerState(1, team=2),
                           2: PlayerState(2, team=1, is_ai=True, color=(0.2, 0.8, 0.2))}
        self.own = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3(-8000, 0, 0))
        self.ally = self.gm.factory.spawn_ship('imperial_corvette', 2, Vec3(8250, 0, 250))
        self.enemy = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(0, 0, -8000))
        self.gm.visibility.update()

    def test_faraway_ai_allies_are_known_render_contacts_even_without_sensors(self):
        self.ally.sensor_range = 0
        self.assertTrue(self.st.can_see(0, self.ally.id))
        self.assertIs(self.st.known_entity(0, self.ally.id), self.ally)
        self.assertEqual({e.id for e in known_entities(self.st, 0)}, {self.own.id, self.ally.id})
        self.assertFalse(self.st.can_see(0, self.enemy.id))
        self.assertIsNone(self.st.known_entity(0, self.enemy.id))

    def test_shared_ai_sensor_reveals_enemy_and_contact_loss_hides_it(self):
        self.enemy.pos = self.ally.pos + Vec3(100, 0, 0)
        self.assertTrue(self.st.can_see(0, self.enemy.id))
        self.assertIn(self.enemy.id, {e.id for e in known_entities(self.st, 0)})
        self.gm.visibility.update()
        self.ally.sensor_range = 0
        self.assertFalse(self.st.can_see(0, self.enemy.id))
        self.assertIsNone(self.st.known_entity(0, self.enemy.id))
        self.assertTrue(self.st.is_position_explored(0, self.enemy.pos))

    def test_ai_viewport_fog_and_minimap_share_ally_coverage(self):
        mask = FogMask().surface(self.st, 0)
        half = self.st.map_info.bounds / 2
        n = mask.get_width()
        cell_x = int((self.ally.pos.x + half) / self.st.map_info.bounds * n)
        cell_z = int((self.ally.pos.z + half) / self.st.map_info.bounds * n)
        self.assertEqual(mask.get_at((cell_x, cell_z)).a, 0)
        self.assertTrue(self.st.is_position_explored(0, self.ally.pos))
        hud = HUD(1280, 800, self.st)
        hud._minimap(set(), 0)
        mx = int(hud.minimap_rect.centerx + self.ally.pos.x / half * 101)
        my = int(hud.minimap_rect.centery + self.ally.pos.z / half * 101)
        self.assertEqual(hud.overlay.get_at((mx, my))[:3], hud._owner_rgb(2)[:3])

    def test_visible_allied_units_remain_inspectable_not_locally_controllable(self):
        hud = HUD(1280, 800, self.st)
        hud._right_panel({self.ally.id}, 0)
        self.assertFalse(any(b['kind'] in ('build_ship', 'build_station_place', 'research')
                             for b in hud.buttons))
        inp = InputController(self.st, SimpleNamespace(), hud,
                              SimpleNamespace(flash=lambda text: None))
        self.assertEqual(inp._jump_units({self.own.id, self.ally.id}), (self.own.id,))
        self.assertEqual({e.id for e in self.gm.player_entities(0)}, {self.own.id})


if __name__ == '__main__':
    unittest.main()
