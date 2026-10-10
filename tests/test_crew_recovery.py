"""Recovery uses real manager commands and conserves personnel."""
import json
import unittest
from helpers import make_game
from game.core.commands import PlayerCommand
from game.core.vectors import Vec3
from game.core.state import GameState
from game.core.manager import GameManager


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.base = self.gm.factory.spawn_station('command_station', 0, Vec3())
        self.ship = self.gm.factory.spawn_ship('imperial_frigate', 0, Vec3(300, 0, 0))
        self.ship.crew = 0
        self.p = self.st.players[0]

    def test_safe_owned_abandoned_hull_recruits_over_time_charging_pool_and_credits(self):
        pool, credits = self.p.crew, self.p.credits
        self.gm.recovery.update(.25)
        self.assertEqual(self.ship.crew, 1)
        self.assertEqual(self.p.crew, pool - 1)
        self.assertEqual(self.p.credits, credits - 2)
        self.assertEqual(self.ship.owner, 0)
        self.assertTrue(self.ship.operational)

    def test_explicit_transport_load_and_deliver_charge_once_and_keep_operating_crew(self):
        self.assertIn('imperial_crew_transport', self.gm.ds.ships)
        transport = self.gm.factory.spawn_ship('imperial_crew_transport', 0, Vec3(0, 0, 300))
        operating = transport.crew
        pool, credits = self.p.crew, self.p.credits
        self.st.queue_command(PlayerCommand('crew_load', 0, unit_ids=(transport.id, transport.id)))
        self.gm.commands.consume()
        self.assertEqual(transport.crew_cargo, 0)
        self.gm.recovery.update(1)
        self.assertEqual(transport.crew_cargo, 4)
        self.assertEqual(transport.crew, operating)
        self.assertEqual(self.p.crew, pool - 8)  # four aboard target, four passengers
        self.assertEqual(self.p.credits, credits - 16)
        self.ship.pos = Vec3(2000, 0, 0)
        transport.pos = Vec3(2000, 0, 100)
        self.st.queue_command(PlayerCommand('crew_deliver', 0, unit_ids=(transport.id,), target_id=self.ship.id))
        self.gm.commands.consume()
        pool, credits, crew = self.p.crew, self.p.credits, self.ship.crew
        self.gm.recovery.update(.5)
        self.assertEqual(transport.crew_cargo, 0)
        self.assertEqual(self.ship.crew, crew + 4)
        self.assertEqual((self.p.crew, self.p.credits), (pool, credits))
        self.assertEqual(transport.crew, operating)

    def test_passenger_support_casualties_and_destruction_never_refund_cargo(self):
        from game.systems.crew import update_crew
        t = self.gm.factory.spawn_ship('imperial_crew_transport', 0, Vec3(2000, 0, 0))
        t.crew_cargo = 12
        t.systems['life_support'].hp = 0
        update_crew(self.st, 2)
        self.assertEqual(t.crew_cargo, 10)
        self.assertEqual(t.crew, t.max_crew - 2)
        pool, crew = self.p.crew, t.crew
        self.gm.damage._kill(t, None, -1)
        self.assertEqual(t.crew_cargo, 0)
        self.assertEqual(t.crew_mission, {})
        self.assertAlmostEqual(self.p.crew - pool, crew * self.gm.ds.rules['sim']['crew_reclaim_fraction'])

    def test_capture_loaded_transport_clears_mission_and_dependents_without_minting_passengers(self):
        t = self.gm.factory.spawn_ship('imperial_crew_transport', 1, Vec3(3000, 0, 0))
        t.crew_cargo = 17
        t.crew = 0
        t.shields = {q: 0 for q in t.shields}
        old_target = self.gm.factory.spawn_ship('imperial_frigate', 1, Vec3(3100, 0, 0))
        old_target.crew -= 5
        t.crew_mission = dict(phase='deliver', owner=1, target=old_target.id, progress=.12)
        t.recruitment_progress = .789
        source = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3(3000, 0, 100))
        self.gm.visibility.update()
        self.assertTrue(self.gm.boarding.launch(source, t))
        pool = self.p.crew
        for _ in range(180):
            self.gm.boarding.update(1 / 30)
        self.assertEqual(t.owner, 0)
        self.assertEqual(t.crew_mission, {})
        self.assertEqual(t.recruitment_progress, 0)
        self.assertEqual(t.crew_cargo, 17)
        self.assertEqual(self.p.crew, pool)
        self.assertLessEqual(t.crew, source.max_crew // 4)

    def test_recovery_fields_participate_in_replay_hash(self):
        from game.net.replay import state_checksum
        for field, value in [('recruitment_progress', .123456789), ('crew_cargo', 12),
                             ('cargo_loss_accumulator', .987654321),
                             ('crew_mission', dict(phase='load', owner=0, target=None, progress=.45))]:
            before = state_checksum(self.st)
            setattr(self.ship, field, value)
            self.assertNotEqual(before, state_checksum(self.st), field)

    def test_invalid_rules_and_raw_transport_capacity_are_rejected(self):
        ds = self.gm.ds
        for value in (-1, 1.5, True, float('nan')):
            ds.ships['imperial_crew_transport'].crew_capacity = value
            with self.assertRaises(ValueError):
                ds._validate()
        ds.ships['imperial_crew_transport'].crew_capacity = 240
        for key, value in [('recruitment_rate', 0), ('delivery_rate', float('nan')),
                           ('credits_per_crew', -1), ('support_threshold', 1.1),
                           ('base_types', 'command_station')]:
            ds.rules['crew_recovery'] = {key: value}
            with self.assertRaises(ValueError, msg=key):
                ds._validate()
        ds.rules.pop('crew_recovery', None)

    def test_capture_surplus_party_after_source_replenishment_cannot_overfill_source(self):
        t = self.gm.factory.spawn_ship('imperial_crew_transport', 1, Vec3(100, 0, 300))
        t.crew = 0
        t.max_crew = 1
        t.shields = {q: 0 for q in t.shields}
        source = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3(100, 0, 200))
        self.gm.visibility.update()
        self.assertTrue(self.gm.boarding.launch(source, t))
        craft = next(e for e in self.st.entities.values() if e.boarding)
        party = craft.crew
        source.crew = source.max_crew  # externally replenished while party is deployed
        pool = self.p.crew
        for _ in range(180):
            self.gm.boarding.update(1 / 30)
        self.assertEqual(source.crew, source.max_crew)
        self.assertEqual(t.crew, 1)
        self.assertEqual(self.p.crew, pool + party - 1)


if __name__ == '__main__':
    unittest.main()
