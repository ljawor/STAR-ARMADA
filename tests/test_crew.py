"""Crew/life-support foundation; no invented §27 contested boarding rules."""
import json
import unittest
from helpers import make_game
from game.core.vectors import Vec3
from game.core.state import GameState
from game.core.manager import GameManager


class TestCrew(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state

    def test_every_factory_has_onboard_crew_and_life_support(self):
        for sid in self.gm.ds.ships:
            e = self.gm.factory.spawn_ship(sid, 0, Vec3())
            self.assertGreater(getattr(e, 'crew', 0), 0, sid)
            self.assertEqual(e.crew, e.max_crew)
            self.assertIn('life_support', e.systems)
        for sid in self.gm.ds.stations:
            e = self.gm.factory.spawn_station(sid, 0, Vec3())
            self.assertGreater(e.crew, 0, sid)
            self.assertIn('life_support', e.systems)
        src = self.gm.factory.spawn_station('trade_station', 0, Vec3())
        dest = self.gm.factory.spawn_station('trade_station', 0, Vec3(1000, 0, 0))
        e = self.gm.trading._make_convoy(src, dest, 100, 100)
        # Convoy factory publishes rather than returns its entity.
        e = max(self.st.entities.values(), key=lambda e: e.id)
        self.assertGreater(e.crew, 0)
        self.assertIn('life_support', e.systems)

    def test_abandoned_units_cannot_fire_repair_trade_or_count_for_victory(self):
        from game.systems.crew import update_crew
        for e in self.st.entities.values():
            if not e.is_planet: e.crew = 0
        update_crew(self.st, 0)
        attacker = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3())
        enemy = self.gm.factory.spawn_ship('imperial_cruiser', 1, Vec3(100, 0, 0))
        attacker.crew = enemy.crew = 0
        update_crew(self.st, 0)
        self.st.grid.rebuild(self.st.entities)
        attacker.current_target = enemy.id
        self.gm.weapons.update(1)
        self.assertEqual(self.st.damage_queue, [])
        self.assertEqual(self.st.projectiles, {})
        self.assertEqual(self.gm.trading.markets(self.st), [])
        self.gm.economy.update(1)
        self.assertEqual(self.st.players[0].income_frame['crew'], 0)
        self.gm.victory.update(2)
        self.assertTrue(self.st.game_over)
        self.assertIsNone(self.st.winner)

    def test_destroyed_ships_reclaim_only_remaining_onboard_crew(self):
        e = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3())
        e.crew = 3
        before = self.st.players[0].crew
        self.gm.damage._kill(e, None, -1)
        fraction = self.gm.ds.rules['sim']['crew_reclaim_fraction']
        self.assertAlmostEqual(self.st.players[0].crew - before, 3 * fraction)

    def test_abandoned_assets_cannot_use_abilities_hangars_ai_or_trade(self):
        from game.ai.ai import AIPlayer
        e = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3())
        market = self.gm.factory.spawn_station('trade_station', 0, Vec3())
        carrier = self.gm.factory.spawn_ship('imperial_supercapital', 0, Vec3())
        squad = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())
        for u in (e, market, carrier): u.crew = 0
        e.energy = 1
        self.gm.abilities.update(1)
        self.assertEqual(e.energy, 1)
        self.assertFalse(self.gm.abilities.activate(e, 'emergency_shield_recharge'))
        self.assertNotIn(e, AIPlayer(self.st, 0).my_units())
        self.assertNotIn(market, self.gm.trading.markets(self.st))
        squad.hangar_id = carrier.id
        squad.hull = 1
        before = squad.hull
        # Exclude other legal hangars from this focused fixture.
        for u in self.st.entities.values():
            if u is not squad: u.crew = 0
        self.gm.squadrons._reinforce_and_repair(squad, 1)
        self.assertEqual(squad.hull, before)

    def test_abandoned_hull_never_fires_with_allied_detection_or_fleet_orders(self):
        from game.core.commands import FleetCreateCommand, MoveCommand
        from game.systems.crew import update_crew
        ship = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3())
        target = self.gm.factory.spawn_ship('imperial_cruiser', 1, Vec3(400, 0, 0))
        observer = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3(0, 0, 100))
        self.st.queue_command(FleetCreateCommand(0, [ship.id], 'Crewless'))
        self.gm.commands.consume()
        ship.crew = 0
        update_crew(self.st, 0)
        ship.current_target = target.id
        self.st.grid.rebuild(self.st.entities)
        self.gm.weapons._ship_weapons(ship, 10)
        self.assertEqual(self.st.damage_queue, [])
        self.assertEqual(self.st.projectiles, {})
        self.assertIsNone(ship.fleet_id)
        self.gm.formations.update(1)
        self.assertEqual(ship.order_type, 'idle')

    def test_crew_state_roundtrips_full_precision_and_legacy_defaults(self):
        from game.net.replay import state_checksum
        e = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3())
        e.crew = 7
        e.crew_loss_accumulator = .123456789123
        snapshot = json.loads(json.dumps(self.st.to_dict(precise=True)))
        restored = GameState.from_dict(snapshot)
        self.assertEqual(json.loads(json.dumps(restored.to_dict(precise=True))), snapshot)
        old_hash = state_checksum(self.st)
        e.crew_loss_accumulator += .000001
        self.assertNotEqual(state_checksum(self.st), old_hash)
        legacy = snapshot['entities'][str(e.id)]
        for key in ('crew', 'max_crew', 'crew_loss_accumulator'):
            legacy.pop(key)
        legacy['systems'].pop('life_support')
        restored = GameState.from_dict(snapshot).entities[e.id]
        self.assertGreater(restored.crew, 0)
        self.assertIn('life_support', restored.systems)

    def test_abandoned_assets_do_not_work_but_can_take_damage(self):
        from game.core.commands import MoveCommand, AbilityCommand
        from game.systems.crew import update_crew
        a = self.gm.factory.spawn_ship('imperial_frigate', 0, Vec3())
        yard = self.gm.factory.spawn_station('shipyard', 0, Vec3(2000, 0, 0))
        lab = self.gm.factory.spawn_station('research_station', 0, Vec3(4000, 0, 0))
        for e in (a, yard, lab):
            e.crew = 0
        update_crew(self.st, 0)
        self.st.queue_command(MoveCommand(0, [a.id], Vec3(1000, 0, 0)))
        self.gm.commands.consume()
        self.assertEqual(a.order_type, 'idle')
        self.assertFalse(self.gm.construction.start_ship(yard.id, 'imperial_corvette', 0))
        tid = self.gm.research.available_techs(0)[0]
        self.assertFalse(self.gm.research.start_research(0, lab.id, tid))
        from game.systems.visibility import SensorQueries
        self.assertFalse(SensorQueries._eligible(a, {0}))
        before = a.hull
        self.gm.damage._apply_damage(a, 10, 1, 1, 1, attacker_id=1)
        self.assertLess(a.hull, before)
        self.gm.damage.update(10)
        self.assertEqual(a.total_shield(), 0)

    def test_failing_life_support_loses_crew_before_total_failure(self):
        from game.systems.crew import update_crew
        e = self.gm.factory.spawn_ship('imperial_frigate', 0, Vec3())
        e.crew = 10
        e.systems['life_support'].hp = e.systems['life_support'].max_hp * .1
        update_crew(self.st, 2)
        self.assertLess(e.crew, 10)
        self.assertGreater(e.crew, 0)

    def test_repair_support_restores_life_support_without_resurrecting_crew(self):
        dock = self.gm.factory.spawn_station('repair_dock', 0, Vec3())
        e = self.gm.factory.spawn_ship('imperial_frigate', 0, Vec3(100, 0, 0))
        e.crew = 3
        e.systems['life_support'].hp = 0
        self.st.grid.rebuild(self.st.entities)
        self.gm.economy.update(1)
        self.assertGreater(e.systems['life_support'].hp, 0)
        self.assertEqual(e.crew, 3)
        e.crew = 0
        self.gm.economy.update(1)
        self.assertEqual(e.crew, 0)
        e.systems['life_support'].hp = 0
        helper = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3())
        self.st.grid.rebuild(self.st.entities)
        self.gm.abilities._tick_active(helper, 'repair_drones', 1)
        self.assertGreater(e.systems['life_support'].hp, 0)
        self.assertEqual(e.crew, 0)

    def test_failed_life_support_gradually_abandons_intact_hull(self):
        e = self.gm.factory.spawn_ship('imperial_frigate', 0, Vec3())
        e.crew = e.max_crew = 2
        e.systems['life_support'].hp = 0
        from game.systems.crew import update_crew
        hull, pool = e.hull, self.st.players[0].crew
        for _ in range(15):
            update_crew(self.st, 0.1)
        self.assertLess(e.crew, 2)
        self.assertGreater(e.crew, 0)
        for _ in range(30):
            update_crew(self.st, 0.1)
        self.assertEqual(e.crew, 0)
        self.assertTrue(e.alive)
        self.assertFalse(e.operational)
        self.assertEqual(e.hull, hull)
        self.assertEqual(self.st.players[0].crew, pool)
        e.systems['life_support'].hp = 100
        self.gm.step(.1)
        self.assertEqual(e.crew, 0)


if __name__ == '__main__':
    unittest.main()
