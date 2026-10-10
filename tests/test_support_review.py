"""Independent review regressions; no production fixes in this module."""
import math
import unittest

from game.core.state import GameState, PlayerState
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.construction import ConstructionSystem
from game.systems.exploration import ExplorationSystem
from game.systems.unit_factory import UnitFactory


class SupportReviewTests(unittest.TestCase):
    def setUp(self):
        DataStore.reset()
        self.st = GameState()
        self.st.players = {
            0: PlayerState(0, team=0, credits=100000, materials=100000,
                           energy=100000, crew=100000, command_capacity=100),
            1: PlayerState(1, team=1),
        }
        self.factory = UnitFactory(self.st)

    def test_legal_fractional_trade_boundary_survives_completion(self):
        cs = ConstructionSystem(self.st)
        cs.factory = self.factory
        self.factory.spawn_station('trade_station', 0, Vec3())
        distance = 1500.000001
        pos = Vec3(distance * math.sin(math.radians(1)), 0,
                   distance * math.cos(math.radians(1)))
        builder = self.factory.spawn_ship('imperial_constructor', 0, pos.copy())
        self.assertGreater(math.dist(pos.to_dict(precise=True), [0, 0, 0]), 1500)
        self.assertTrue(cs.check_site('trade_station', pos, builder)[0])
        self.assertTrue(cs.start_station(builder.id, 'trade_station', pos, 0))
        paid_bank = self.st.players[0].credits
        builder.build_queue[0]['time_left'] = .001
        # Nothing changes ownership or occupies the approved site.
        cs.update(.1)
        self.assertEqual(self.st.players[0].credits, paid_bank)
        markets = [e for e in self.st.entities.values() if e.data_id == 'trade_station']
        self.assertEqual(len(markets), 2,
                         'coordinate rounding must not cancel paid legal work')

    def test_fully_explored_map_still_evades_detected_enemy(self):
        self.st.map_info.bounds = 6000
        fighter = self.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())
        fighter.sensor_range = 2500
        home = self.factory.spawn_ship('imperial_corvette', 0, Vec3(-2000, 0, 0))
        enemy = self.factory.spawn_ship('imperial_corvette', 1, Vec3(300, 0, 0))
        self.st.explored_cells[0] = {(x, z) for x in range(-6, 6) for z in range(-6, 6)}
        self.assertTrue(self.st.can_see(0, enemy.id))
        system = ExplorationSystem(self.st)
        obstacles = list(system._obstacles(fighter))
        self.assertTrue(system._route_safe(fighter.pos, home.pos, obstacles))
        self.assertTrue(system.start(fighter, 0))
        self.assertEqual(fighter.order_type, 'explore')
        self.assertIsNotNone(fighter.order_target_pos,
                             'persistent survey must evade detected threats even without unknown cells')


if __name__ == '__main__':
    unittest.main()
