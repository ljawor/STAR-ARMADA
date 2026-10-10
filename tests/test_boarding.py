"""End-to-end serialized boarding, conservation, authoritative gates and restore."""
import json
import unittest
from helpers import make_game
from game.core.commands import PlayerCommand
from game.core.vectors import Vec3
from game.core.state import GameState
from game.core.manager import GameManager
from game.net.replay import state_checksum


def normalized(st):
    return json.loads(json.dumps(st.to_dict(precise=True)))


class TestBoarding(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.source = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3())
        self.target = self.gm.factory.spawn_ship('imperial_frigate', 1, Vec3(500, 0, 0))
        self.source.order_type = 'hold'
        self.target.crew = 0
        self.target.shields = {q: 0.0 for q in self.target.shields}

    def launch(self):
        cmd = PlayerCommand('board', 0, unit_ids=(self.source.id,), target_id=self.target.id)
        self.st.queue_command(PlayerCommand.from_dict(json.loads(json.dumps(cmd.to_dict()))))
        self.gm.commands.consume()
        return [e for e in self.st.entities.values() if e.data_id == 'boarding_craft']

    def test_authoritative_launch_rejects_illegal_targets_and_sources(self):
        cases = ['own', 'allied', 'hidden', 'range', 'shield', 'staffed', 'incapable', 'crew', 'jump', 'planet']
        for case in cases:
            with self.subTest(case=case):
                self.setUp()
                if case == 'own': self.target.owner = 0
                if case == 'allied': self.st.players[1].team = self.st.players[0].team
                if case == 'hidden':
                    self.target.pos = Vec3(8000, 8000, 8000)
                    self.source.pos = self.target.pos.copy()
                    self.source.sensor_range = 0
                if case == 'range': self.target.pos.x = 5000
                if case == 'shield': self.target.shields['front'] = 1
                if case == 'staffed': self.target.crew = 10
                if case == 'incapable': self.source.data_id = 'imperial_corvette'
                if case == 'crew': self.source.crew = 1
                if case == 'jump': self.source.jump_charge = 1
                if case == 'planet': self.target.is_planet = True
                before = self.source.crew
                self.assertEqual(self.launch(), [])
                self.assertEqual(self.source.crew, before)

    def test_staffed_disabled_targets_resist_and_can_defeat_party(self):
        self.target.crew = 1000
        self.target.max_crew = 1000
        self.target.systems['engines'].hp = 0
        craft = self.launch()[0]
        craft.pos = self.target.pos.copy()
        party = craft.crew
        self.gm.boarding.update(1.0)
        self.assertLess(craft.crew, party)
        self.assertLess(craft.boarding['progress'], .2)
        for _ in range(200): self.gm.boarding.update(.1)
        self.assertEqual(self.target.owner, 1)
        self.assertFalse(any(e.boarding for e in self.st.entities.values()))

    def test_disabled_staffed_hull_can_be_captured_through_real_ticks(self):
        self.target.crew = 5
        for name in ('engines', 'weapons', 'shield_gen'):
            self.target.systems[name].hp = 0
        self.target.systems['life_support'].hp = 100
        self.launch()
        for _ in range(450):
            self.gm.step(1 / 30)
            if self.target.owner == 0:
                break
        self.assertEqual(self.target.owner, 0)
        self.assertGreater(self.target.crew, 0)
        self.assertIsNone(self.source.boarding_party_id)

    def test_capture_cleans_previous_owner_runtime_and_preserves_banks(self):
        from game.core.commands import FleetCreateCommand
        self.st.queue_command(FleetCreateCommand(1, [self.target.id], 'Defenders'))
        self.target.crew = 1
        self.gm.commands.consume()
        self.target.crew = 0
        fleet_id = self.target.fleet_id
        self.target.build_queue = [{'kind': 'ship', 'item': 'imperial_corvette', 'time_left': .1}]
        self.st.players[1].researching['test'] = {'station_id': self.target.id, 'time_left': .1}
        self.target.order_target_id = self.source.id
        self.target.jump_charge = 20
        self.target.ability_active['repair'] = 10
        banks = [(p.credits, p.materials, p.energy, p.crew) for p in self.st.players.values()]
        craft = self.launch()[0]
        craft.pos = self.target.pos.copy()
        self.gm.boarding.update(6)
        self.assertEqual(self.target.owner, 0)
        self.assertEqual(self.target.build_queue, [])
        self.assertEqual(self.target.order_type, 'idle')
        self.assertIsNone(self.target.order_target_id)
        self.assertIsNone(self.target.fleet_id)
        self.assertNotIn(fleet_id, self.st.fleets)
        self.assertEqual(self.target.jump_charge, 0)
        self.assertEqual(self.target.ability_active, {})
        self.assertNotIn('test', self.st.players[1].researching)
        self.assertEqual(banks, [(p.credits, p.materials, p.energy, p.crew) for p in self.st.players.values()])

    def test_interruptions_return_survivors_and_never_capture_invalid_target(self):
        for case in ('hidden', 'dead', 'transferred', 'range', 'shields', 'repaired', 'stop', 'source_dead'):
            with self.subTest(case=case):
                self.setUp()
                before = self.source.crew
                craft = self.launch()[0]
                if case == 'hidden':
                    self.target.pos = Vec3(8000, 8000, 8000)
                    self.source.pos = self.target.pos.copy()
                    self.source.sensor_range = 0
                if case == 'dead': self.target.alive = False
                if case == 'transferred': self.target.owner = 0
                if case == 'range': self.source.pos.x = -8000
                if case == 'shields': self.target.shields['front'] = 1
                if case == 'repaired': self.target.crew = 10
                if case == 'stop':
                    self.st.queue_command(PlayerCommand('stop', 0, unit_ids=(self.source.id,)))
                    self.gm.commands.consume()
                if case == 'source_dead': self.source.alive = False
                for _ in range(100): self.gm.boarding.update(1)
                self.assertFalse(any(e.boarding for e in self.st.entities.values()))
                if case != 'transferred': self.assertEqual(self.target.owner, 1)
                if case != 'source_dead': self.assertEqual(self.source.crew, before)

    def test_boarding_source_holds_position_and_ceases_fire_at_its_target(self):
        self.source.order_type = 'attack'
        self.source.order_target_id = self.target.id
        self.source.current_target = self.target.id
        self.source.yaw = 1.5707963267948966
        self.launch()
        self.assertEqual(self.source.order_type, 'hold')
        self.assertIsNone(self.source.order_target_id)
        self.gm.weapons._ship_weapons(self.source, 1)
        self.assertFalse(any(hit['target'] is self.target for hit in self.st.damage_queue))
        self.assertFalse(any(p.target_id == self.target.id for p in self.st.projectiles.values()))

    def test_station_capture_and_competing_parties_conserve_survivors(self):
        self.target = self.gm.factory.spawn_station('shipyard', 1, Vec3(500, 0, 0))
        self.target.crew = 0
        self.target.shields = {q: 0 for q in self.target.shields}
        second = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3(100, 0, 0))
        total = self.source.crew + second.crew
        first = self.launch()[0]
        self.st.queue_command(PlayerCommand('board', 0, unit_ids=(second.id,), target_id=self.target.id))
        self.gm.commands.consume()
        parties = [e for e in self.st.entities.values() if e.boarding]
        self.assertEqual(len(parties), 2)
        for craft in parties: craft.pos = self.target.pos.copy()
        self.gm.boarding.update(6)
        for _ in range(30): self.gm.boarding.update(1)
        self.assertEqual(self.target.owner, 0)
        self.assertTrue(self.target.operational)
        self.assertEqual(self.source.crew + second.crew + self.target.crew, total)
        self.assertFalse(any(e.boarding for e in self.st.entities.values()))

    def test_only_one_active_party_per_source(self):
        first = self.launch()[0]
        before = self.source.crew
        self.assertEqual(self.launch(), [first])
        self.assertEqual(self.source.crew, before)

    def test_every_tick_json_restore_and_replay_hash_through_capture(self):
        self.launch()
        self.gm.visibility.update()
        for tick in range(300):
            snapshot = normalized(self.st)
            other = GameManager(GameState.from_dict(snapshot))
            self.assertEqual(normalized(other.state), snapshot, tick)
            self.gm.step(1 / 30)
            other.step(1 / 30)
            self.assertEqual(normalized(other.state), normalized(self.st), tick)
            self.assertEqual(state_checksum(other.state), state_checksum(self.st), tick)
        self.assertEqual(self.target.owner, 0)
        self.assertTrue(self.target.alive)

    def test_boarding_rules_validate_numbers_and_legacy_mod_defaults(self):
        from game.systems.boarding import boarding_rules
        self.gm.ds.rules.pop('boarding', None)
        self.assertGreater(boarding_rules()['craft_speed'], 0)
        self.gm.ds._validate()
        for bad in (0, -1, float('nan'), float('inf'), True, 'fast'):
            with self.subTest(bad=bad):
                self.gm.ds.rules['boarding'] = {'craft_speed': bad}
                with self.assertRaises(ValueError): self.gm.ds._validate()
        self.gm.ds.rules['boarding'] = {'party_fraction': 2}
        with self.assertRaises(ValueError): self.gm.ds._validate()

    def test_launch_transit_and_capture_derelict_without_minting_crew(self):
        total = self.source.crew + self.target.crew
        pool = self.st.players[0].crew
        crafts = self.launch()
        self.assertEqual(len(crafts), 1)
        craft = crafts[0]
        self.assertGreater(craft.crew, 0)
        self.assertEqual(self.source.crew + craft.crew, total)
        self.assertEqual(craft.pos.to_dict(), self.source.pos.to_dict())
        self.gm.boarding.update(.5)
        self.assertGreater(craft.pos.x, 0)
        self.assertLess(craft.pos.x, self.target.pos.x)
        self.assertEqual(self.target.owner, 1)
        for _ in range(200):
            self.gm.boarding.update(.1)
        self.assertEqual(self.target.owner, 0)
        self.assertTrue(self.target.alive)
        self.assertEqual(self.source.crew + self.target.crew, total)
        self.assertEqual(self.st.players[0].crew, pool)
        self.assertFalse(any(e.data_id == 'boarding_craft' for e in self.st.entities.values()))


if __name__ == '__main__':
    unittest.main()
