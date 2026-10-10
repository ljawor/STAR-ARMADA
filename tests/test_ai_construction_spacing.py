"""AI scheduling must retain legal sites and constructor intent."""
import unittest

from helpers import make_game
from game.ai.ai import AIPlayer
from game.core.vectors import Vec3


class AIConstructionSpacingTests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.ai = AIPlayer(self.st, 0)
        self.home = self.ai.home_station()
        assert self.home is not None
        self.builder = next(e for e in self.ai.my_units() if self.ai._is_builder(e))

    def test_unconsumed_station_order_reserves_constructor_against_defense(self):
        site = self.home.pos + Vec3(900, 0, 0)
        self.builder.pos = site.copy()
        self.st.players[0].credits = 10000
        self.ai._queue_build(self.builder, 'trade_station', site)
        self.ai._ensure_defense(self.home)
        commands = [c for c in self.st.command_queue if self.builder.id in c.unit_ids]
        self.assertEqual([c.type for c in commands], ['build_station'])
        self.assertNotIn(self.builder.id, self.ai._pending_site)

    def test_asteroid_search_returns_legal_site_despite_paid_obstruction(self):
        asteroid = min((e for e in self.st.entities.values() if e.data_id == 'asteroid_field'),
                       key=lambda e: e.pos.dist_sq(self.home.pos))
        # Preserve the AI RNG state so the old one-shot picker hits the occupied site.
        rng_state = self.st.rng().getstate()
        first = self.ai._find_asteroid_site(self.home)
        assert first is not None
        self.st.rng().setstate(rng_state)
        other = self.gm.factory.spawn_ship('imperial_constructor', 0, asteroid.pos.copy())
        other.build_queue.append(dict(kind='station', item='mining_station',
                                     pos=[first.x, first.y, first.z], status='paid'))
        site = self.ai._find_asteroid_site(self.home)
        self.assertIsNotNone(site)
        self.assertTrue(self.gm.construction.check_site('mining_station', site, self.builder)[0])

    def test_core_infrastructure_uses_nearby_idle_constructor(self):
        for i in range(4):
            self.gm.factory.spawn_station('mining_station', 0, Vec3(i * 1000, 0, 6000))
        self.gm.factory.spawn_station('shipyard', 0, self.home.pos + Vec3(0, 0, 900))
        self.builder.pos = Vec3(0, 0, 0)
        nearby = self.gm.factory.spawn_ship('imperial_constructor', 0,
                                          self.home.pos + Vec3(500, 0, 0))
        self.st.players[0].credits = 10000
        self.ai._ensure_economy(self.home)
        commands = [c for c in self.st.command_queue if c.type in ('build_station', 'move')]
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0].unit_ids, (nearby.id,))
