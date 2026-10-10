"""Colony AI priorities through the authoritative manager pipeline."""
import unittest

from helpers import make_game
from game.core.commands import PlayerCommand
from game.core.vectors import Vec3


class ColonyAITests(unittest.TestCase):
    def test_multiple_colonies_share_a_projected_satellite_budget(self):
        gm = make_game(ai=False)
        st = gm.state
        from game.ai.ai import AIPlayer
        ai = AIPlayer(st, 0)
        home = ai.home_station()
        assert home is not None
        gm.factory.spawn_station('mining_station', 0, home.pos + Vec3(500, 0, 500))
        for e in st.entities.values():
            if e.is_planet and e.data_id != 'gas_giant':
                e.colonized_by = 0
        p = st.players[0]
        p.credits, p.materials, p.energy = 6500, 10000, 10000
        ai._maybe_expand(home)
        buys = [c for c in st.command_queue if c.type == 'build_satellite']
        self.assertEqual(len(buys), 1, 'optional satellites must retain the economic credit reserve')
        gm.step(1 / 30)
        self.assertGreaterEqual(p.credits, 5000)
        self.assertEqual(sum(len(e.build_queue) for e in st.entities.values() if e.is_planet), 1)

    def test_satellites_account_for_earlier_unconsumed_ship_commands(self):
        gm = make_game(ai=False)
        st = gm.state
        from game.ai.ai import AIPlayer
        ai = AIPlayer(st, 0)
        home = ai.home_station()
        assert home is not None
        gm.factory.spawn_station('mining_station', 0, home.pos + Vec3(500, 0, 500))
        planet = next(e for e in st.entities.values() if e.data_id == 'temperate')
        planet.colonized_by = 0
        p = st.players[0]
        p.credits, p.materials, p.energy = 6100, 10000, 10000
        ai._queue_ship(home, 'imperial_colonizer', 1)
        ai._maybe_expand(home)
        self.assertFalse(any(c.type == 'build_satellite' for c in st.command_queue))

    def test_satellites_preserve_unpaid_research_site_energy(self):
        gm = make_game(ai=False)
        st = gm.state
        from game.ai.ai import AIPlayer
        ai = AIPlayer(st, 0)
        home = ai.home_station()
        assert home is not None
        gm.factory.spawn_station('mining_station', 0, home.pos + Vec3(500, 0, 500))
        planet = next(e for e in st.entities.values() if e.data_id == 'temperate')
        planet.colonized_by = 0
        builder = next(e for e in ai.my_units() if ai._is_builder(e))
        ai._pending_site[builder.id] = ('research_station', home.pos + Vec3(1500, 0, 0))
        p = st.players[0]
        p.credits, p.materials, p.energy = 10000, 10000, 500
        ai._maybe_expand(home)
        self.assertFalse(any(c.type == 'build_satellite' for c in st.command_queue))

    def test_syndicate_colonizer_is_selected_from_catalogue(self):
        gm = make_game(ai=False)
        st = gm.state
        from game.ai.ai import AIPlayer
        st.players[0].faction = 'syndicate'
        ai = AIPlayer(st, 0)
        home = ai.home_station()
        assert home is not None
        ai._maybe_expand(home)
        builds = [c.ship_id for c in st.command_queue if c.type == 'build_ship']
        self.assertEqual(builds, ['syndicate_colonizer'])
        gm.step(1 / 30)
        self.assertEqual(home.build_queue[0]['item'], 'syndicate_colonizer')

    def test_repeated_expansion_respects_unconsumed_colony_reservations(self):
        gm = make_game(ai=False)
        st = gm.state
        from game.ai.ai import AIPlayer
        ai = AIPlayer(st, 0)
        home = ai.home_station()
        assert home is not None
        gm.factory.spawn_station('mining_station', 0, home.pos + Vec3(500, 0, 500))
        planet = next(e for e in st.entities.values() if e.data_id == 'temperate')
        planet.colonized_by = 0
        p = st.players[0]
        p.credits, p.materials, p.energy = 20000, 20000, 10000
        ai._maybe_expand(home)
        first = list(st.command_queue)
        self.assertEqual(len([c for c in first if c.type == 'build_satellite']), 2)
        ai._maybe_expand(home)
        self.assertEqual(st.command_queue, first)
        gm.step(1 / 30)
        self.assertEqual({item['item'] for item in planet.build_queue},
                         {'defense_satellite', 'attack_satellite'})
        self.assertGreaterEqual(p.credits, 5000)
        self.assertGreaterEqual(p.materials, 2500)

    def test_satellite_clearance_survives_strategic_fleet_orders(self):
        gm = make_game(ai=False)
        st = gm.state
        for e in st.entities.values():
            if e.is_planet:
                e.alive = False
        home = next(e for e in st.entities.values() if e.owner == 0 and e.data_id == 'command_station')
        home.sensor_range = 10000
        planet = gm.factory.spawn_planet({'id': 'capture', 'type': 'temperate',
            'pos': [home.pos.x + 2000, 0, home.pos.z], 'radius': 100})
        planet.colonized_by = 1
        defender = gm.factory.spawn_station('attack_satellite', 1, planet.pos + Vec3(500, 0, 0))
        defender.planet_id = planet.id
        gm.factory.spawn_station('command_station', 1, home.pos + Vec3(6500, 0, 0))
        gm.factory.spawn_ship('imperial_colonizer', 0, home.pos + Vec3(300, 0, 0))
        fighters = [gm.factory.spawn_ship('imperial_battleship', 0,
                    home.pos + Vec3(0, 0, 500 + i * 200)) for i in range(4)]
        st.queue_command(PlayerCommand('fleet_create', 0, unit_ids=tuple(e.id for e in fighters), name='Existing strike'))
        gm.step(1 / 30)
        fleet = st.fleets[fighters[0].fleet_id]
        fleet.rally_point = [home.pos.x + 6500, 0, home.pos.z]
        st.players[0].credits = 10000
        st.players[0].is_ai = True
        st.tick = 29
        gm.step(1 / 30)  # full strategic decision, including general attack logic
        gm.step(1 / 30)  # authoritative command consumption and movement
        for fighter in fighters:
            self.assertEqual(fighter.order_type, 'attack')
            self.assertEqual(fighter.order_target_id, defender.id)
        for _ in range(90):
            gm.step(1 / 30)
        self.assertFalse(st.game_over)
        for fighter in fighters:
            self.assertEqual(fighter.order_target_id, defender.id)
        # An underway clearance is not a new purchase: losing the expansion
        # bank must not hand these ships back to the general strike fleet.
        st.players[0].credits = 0
        st.tick = 149
        gm.step(1 / 30)
        gm.step(1 / 30)
        for fighter in fighters:
            self.assertEqual(fighter.order_target_id, defender.id)


if __name__ == '__main__':
    unittest.main()
