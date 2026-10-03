"""Placement feedback must not act as a detector for hidden obstructions."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from game.core.state import GameState, PlayerState
from game.core.vectors import Vec3
from game.systems.construction import ConstructionSystem
from game.systems.unit_factory import UnitFactory
from render.input import InputController


class PlacementFogTests(unittest.TestCase):
    def setUp(self):
        self.st = GameState()
        self.st.players[0] = PlayerState(0)
        self.st.players[1] = PlayerState(1)
        self.factory = UnitFactory(self.st)
        self.builder = self.factory.spawn_ship('imperial_constructor', 0, Vec3())
        self.cs = ConstructionSystem(self.st)
        self.cs.factory = self.factory
        self.st._construction_system = self.cs
        self.site = (9000, 0, 0)
        self.enemy = self.factory.spawn_station('defense_platform', 1, Vec3(*self.site))
        self.flashes = []
        self.hud = SimpleNamespace(placement=None)
        self.input = InputController(self.st,
            SimpleNamespace(screen_to_world=lambda *args: self.site), self.hud,
            SimpleNamespace(flash=self.flashes.append))

    def ghost_verdict(self):
        self.hud.placement = {'builder_id': self.builder.id, 'station_kind': 'shipyard'}
        with patch('render.input.pygame.mouse.get_pos', return_value=(10, 20)):
            self.input.update_placement()
        ghost = self.hud.placement['ghost']
        return ghost['valid'], ghost['reason']

    def test_far_hidden_station_does_not_change_ghost_verdict(self):
        self.assertFalse(self.st.can_see(0, self.enemy.id))
        obstructed = self.ghost_verdict()
        del self.st.entities[self.enemy.id]
        self.assertEqual(obstructed, self.ghost_verdict())
        self.assertFalse(obstructed[0])
        self.assertIn('out of range', obstructed[1])

    def test_unsensed_near_station_does_not_change_ghost_verdict(self):
        self.site = (600, 0, 0)
        self.enemy.pos = Vec3(*self.site)
        self.builder.sensor_range = 0
        self.assertFalse(self.st.can_see(0, self.enemy.id))
        obstructed = self.ghost_verdict()
        del self.st.entities[self.enemy.id]
        self.assertEqual(obstructed, self.ghost_verdict())
        self.assertEqual(obstructed, (True, ''))

    def test_hidden_obstruction_confirmation_does_not_flash_its_type(self):
        self.site = (600, 0, 0)
        self.enemy.pos = Vec3(*self.site)
        self.builder.sensor_range = 0
        self.ghost_verdict()
        self.assertTrue(self.input._confirm_placement((10, 20)))
        self.assertEqual(len(self.st.command_queue), 1)
        self.assertFalse(any('defense platform' in text for text in self.flashes))

    def test_actual_build_rejects_hidden_spacing_with_generic_feedback(self):
        self.site = (600, 0, 0)
        self.enemy.pos = Vec3(*self.site)
        self.builder.sensor_range = 0
        self.assertFalse(self.cs.check_site('shipyard', self.site, self.builder)[0])
        self.assertFalse(self.cs.start_station(self.builder.id, 'shipyard',
                                               Vec3(*self.site), 0))
        self.assertFalse(self.builder.build_queue)
        self.assertEqual(self.st.floating_texts[-1]['text'], 'Cannot build: site unavailable')

    def test_current_visible_station_reports_legitimate_spacing(self):
        self.site = (600, 0, 0)
        self.enemy.pos = Vec3(*self.site)
        self.assertTrue(self.st.can_see(0, self.enemy.id))
        self.assertEqual(self.ghost_verdict(), (False, 'too close to defense platform'))
        self.assertFalse(self.cs.start_station(self.builder.id, 'shipyard',
                                               Vec3(*self.site), 0))
        self.assertIn('too close to defense platform', self.st.floating_texts[-1]['text'])

    def test_allied_current_detection_is_used_not_builder_sensors(self):
        self.site = (600, 0, 0)
        self.enemy.pos = Vec3(*self.site)
        self.builder.sensor_range = 0
        self.st.players[0].team = 2
        self.st.players[2] = PlayerState(2, team=2)
        detector = self.factory.spawn_ship('imperial_corvette', 2, Vec3(*self.site))
        self.assertTrue(self.st.can_see(0, self.enemy.id))
        self.assertEqual(self.ghost_verdict(), (False, 'too close to defense platform'))
        detector.alive = False
        self.assertEqual(self.ghost_verdict(), (True, ''))

    def test_far_preview_short_circuits_detection_without_weakening_default(self):
        with patch.object(GameState, 'can_see', side_effect=AssertionError('expensive detection')):
            ok, reason = self.cs.check_site('shipyard', self.site, self.builder, viewer=0)
        self.assertFalse(ok)
        self.assertIn('out of range', reason)
        self.assertEqual(self.cs.check_site('shipyard', self.site, self.builder),
                         (False, 'too close to defense platform'))
        del self.st.entities[self.enemy.id]
        self.assertEqual(self.cs.check_site('shipyard', self.site, self.builder), (True, ''))


if __name__ == '__main__':
    unittest.main()
