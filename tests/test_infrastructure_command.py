"""Issue #70: shared command accounting, paid reservations and colony capacity."""
import json
import unittest

from helpers import make_game
from game.core.vectors import Vec3
from game.data.store import DataStore


class InfrastructureCommandTests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.ds = DataStore.get()
        self.p = self.st.players[0]
        for key in ('credits', 'materials', 'energy', 'crew'):
            setattr(self.p, key, 100000)
        self.planet = next(e for e in self.st.entities.values() if e.data_id == 'temperate')

    def assert_restored_ticks(self, count, original=None):
        from game.core.manager import GameManager
        from game.core.state import GameState
        original = original or self.gm
        saved = json.loads(json.dumps(original.state.to_dict(precise=True)))
        restored = GameManager(GameState.from_dict(saved))
        self.assertEqual(saved, json.loads(json.dumps(restored.state.to_dict(precise=True))))
        for tick in range(count):
            original.step(1 / 30)
            restored.step(1 / 30)
            self.assertFalse(original.state.game_over)
            self.assertEqual(json.loads(json.dumps(original.state.to_dict(precise=True))),
                             json.loads(json.dumps(restored.state.to_dict(precise=True))), f'tick {tick}')
            for player in original.state.players:
                self.assertEqual(original.state.players[player].command_used(original.state.entities),
                                 restored.state.players[player].command_used(restored.state.entities))
        return restored

    def test_serialized_mixed_builds_restore_through_paid_completion_and_destruction(self):
        from game.core.commands import PlayerCommand
        from game.systems.economy import EconomySystem
        self.planet.colonized_by = 0
        EconomySystem.recompute_command_capacity(self.st)
        builder = next(e for e in self.st.entities.values() if e.data_id == 'imperial_constructor' and e.owner == 0)
        builder.pos = Vec3(-17000.125, 0, -5000.25)
        yard = next(e for e in self.st.entities.values() if e.data_id == 'shipyard' and e.owner == 0)
        commands = [PlayerCommand('build_station', 0, unit_ids=(builder.id,), station_kind='research_station',
                                  target_pos=(builder.pos.x, builder.pos.y, builder.pos.z)),
                    PlayerCommand('build_satellite', 0, target_id=self.planet.id, station_kind='defense_satellite'),
                    PlayerCommand('build_planet_building', 0, target_id=self.planet.id, station_kind='planet_extractor'),
                    PlayerCommand('build_ship', 0, unit_ids=(yard.id,), ship_id='imperial_corvette')]
        used = self.p.command_used(self.st.entities)
        bank = self.p.credits
        for command in commands:
            self.st.queue_command(PlayerCommand.from_dict(command.to_dict()))
        self.assertEqual(self.p.credits, bank)
        self.gm.step(1 / 30)
        self.assertEqual(sum(len(e.build_queue) for e in (builder, yard, self.planet)), 4)
        self.assertEqual(self.p.command_used(self.st.entities), used + 9)
        # Paid production remains real; accelerate only its remaining clocks.
        for e in (builder, yard, self.planet):
            for work in e.build_queue:
                work['time_left'] = .125
        self.assert_restored_ticks(45)
        self.assertEqual(self.p.command_used(self.st.entities), used + 9)
        for kind in ('research_station', 'defense_satellite', 'planet_extractor'):
            entity = next(e for e in self.st.entities.values() if e.data_id == kind and e.owner == 0)
            before = self.p.command_used(self.st.entities)
            entity.crew = 0
            self.assertEqual(self.p.command_used(self.st.entities), before)
            self.gm.damage._kill(entity, None, -1)
            self.gm.step(1 / 30)
            self.assertEqual(self.p.command_used(self.st.entities), before - self.ds.command_cost(entity))
        self.assert_restored_ticks(35)

    def test_colony_capture_transfers_capacity_hardware_and_releases_old_paid_work(self):
        from game.core.commands import PlayerCommand
        from game.systems.economy import EconomySystem
        from game.systems.planet_buildings import start_building
        self.planet.colonized_by = 1
        enemy = self.st.players[1]
        enemy.credits = enemy.materials = enemy.energy = enemy.crew = 100000
        EconomySystem.recompute_command_capacity(self.st)
        self.assertTrue(start_building(self.gm.construction, self.planet.id, 'planet_extractor', 1))
        self.planet.build_queue[0]['time_left'] = .125
        for _ in range(5):
            self.gm.step(1 / 30)
        building = next(e for e in self.st.entities.values() if e.planet_id == self.planet.id)
        self.assertTrue(start_building(self.gm.construction, self.planet.id, 'planet_trade_hub', 1))
        capacities = {p.id: p.command_capacity for p in self.st.players.values()}
        used = {p.id: p.command_used(self.st.entities) for p in self.st.players.values()}
        colonizer = self.gm.factory.spawn_ship('imperial_colonizer', 0,
                     self.planet.pos + Vec3(0, 0, self.planet.radius + 300))
        self.st.queue_command(PlayerCommand('colonize', 0, unit_ids=(colonizer.id,), target_id=self.planet.id))
        self.gm.step(1 / 30)
        colonizer.build_queue[0]['time_left'] = .125
        self.assert_restored_ticks(45)
        self.assertEqual(self.planet.colonized_by, 0)
        self.assertEqual(building.owner, 0)
        self.assertFalse(self.planet.build_queue)
        self.assertEqual(self.p.command_capacity, capacities[0] + 20)
        self.assertEqual(enemy.command_capacity, capacities[1] - 20)
        self.assertEqual(self.p.command_used(self.st.entities), used[0] + 1)
        self.assertEqual(enemy.command_used(self.st.entities), used[1] - 2)
        self.planet.alive = False
        self.assert_restored_ticks(35)
        self.assertEqual(self.p.command_capacity, capacities[0])

    def test_same_tick_orders_share_the_last_command_point(self):
        from game.core.commands import PlayerCommand
        from game.systems.economy import EconomySystem
        self.planet.colonized_by = 0
        EconomySystem.recompute_command_capacity(self.st)
        while self.p.command_used(self.st.entities) < self.p.command_capacity - 1:
            e = self.gm.factory.spawn_station('sensor_station', 0, Vec3(-23000, 0, -23000))
            e.crew = 0  # costs CMD but provides no operational capacity
        before = self.p.command_used(self.st.entities)
        self.st.queue_command(PlayerCommand('build_planet_building', 0,
                              target_id=self.planet.id, station_kind='planet_extractor'))
        self.st.queue_command(PlayerCommand('build_satellite', 0,
                              target_id=self.planet.id, station_kind='defense_satellite'))
        bank = self.p.credits
        self.gm.step(1 / 30)
        self.assertEqual(len(self.planet.build_queue), 1)
        self.assertEqual(self.planet.build_queue[0]['kind'], 'planet_building')
        self.assertEqual(self.p.command_used(self.st.entities), before + 1)
        self.assertAlmostEqual(self.p.credits, bank - self.ds.stations['planet_extractor'].cost_credits
                               + self.p.income_frame['credits'] / 30)
        self.assert_restored_ticks(5)

    def test_capacity_loss_does_not_cancel_previously_paid_work(self):
        from game.systems.planet_buildings import start_building
        from game.systems.economy import EconomySystem
        self.planet.colonized_by = 0
        self.assertTrue(start_building(self.gm.construction, self.planet.id, 'planet_extractor', 0))
        self.planet.build_queue[0]['time_left'] = .125
        self.ds.rules['sim']['command_capacity_base'] = 0
        self.ds.stations['command_station'].command_capacity = 0
        for e in self.st.entities.values():
            if e.owner == 0 and e.is_station:
                e.crew = 0
        EconomySystem.recompute_command_capacity(self.st)
        self.assertEqual(self.p.command_capacity, 0)
        self.assertFalse(self.gm.construction.command_available(0, 1))
        for _ in range(5):
            self.gm.step(1 / 30)
        self.assertFalse(self.planet.build_queue)
        self.assertTrue(any(e.data_id == 'planet_extractor' and e.owner == 0 for e in self.st.entities.values()))

    def test_station_command_cost_mod_loading_defaults_and_validation(self):
        import pathlib
        import tempfile
        from unittest.mock import patch
        import game.data.store as store
        with tempfile.TemporaryDirectory() as root:
            path = pathlib.Path(root) / 'mods' / 'cmd' / 'data' / 'stations' / 'stations.json'
            path.parent.mkdir(parents=True)
            data = json.loads((pathlib.Path(store.ROOT) / 'assets/data/stations/stations.json').read_text())
            data['stations']['research_station'].pop('command_cost', None)
            data['stations']['sensor_station']['command_cost'] = 3
            data['stations']['command_station']['command_capacity'] = 37
            path.write_text(json.dumps(data))
            with patch.object(store, 'ROOT', root):
                ds = DataStore(assets_dir=self.ds.assets_dir, mods=['cmd'])
                self.assertEqual(ds.stations['research_station'].command_cost, 5)
                self.assertEqual(ds.stations['sensor_station'].command_cost, 3)
                self.assertEqual(ds.stations['command_station'].command_capacity, 37)
                for value in (-1, True, 1.5, '2'):
                    with self.subTest(value=value):
                        data['stations']['sensor_station']['command_cost'] = value
                        path.write_text(json.dumps(data))
                        with self.assertRaisesRegex(ValueError, 'command_cost'):
                            DataStore(assets_dir=self.ds.assets_dir, mods=['cmd'])

    def test_each_eligible_colony_matches_modded_command_center_capacity(self):
        from game.systems.colonies import COLONY_TYPES
        from game.systems.economy import EconomySystem
        from game.systems.stats import player_command_capacity
        self.ds.stations['command_station'].command_capacity = 37
        tech = next(t for t in self.ds.techs.values() if t.effects.get('command_capacity_bonus'))
        self.p.researched.add(tech.id)
        EconomySystem.recompute_command_capacity(self.st)
        base = self.p.command_capacity
        for kind in sorted(COLONY_TYPES):
            with self.subTest(kind=kind):
                self.planet.data_id = kind
                self.planet.colonized_by = 0
                EconomySystem.recompute_command_capacity(self.st)
                self.assertEqual(self.p.command_capacity, base + 37)
                self.assertEqual(player_command_capacity(self.st, 0), base + 37)
                self.planet.colonized_by = 1
                EconomySystem.recompute_command_capacity(self.st)
                self.assertEqual(self.p.command_capacity, base)
        self.planet.colonized_by = 0
        self.planet.data_id = 'gas_giant'  # invalid legacy colonies remain ineligible
        EconomySystem.recompute_command_capacity(self.st)
        self.assertEqual(self.p.command_capacity, base)
        self.planet.data_id = 'temperate'
        self.planet.alive = False
        EconomySystem.recompute_command_capacity(self.st)
        self.assertEqual(self.p.command_capacity, base)

    def test_paid_infrastructure_reserves_capacity_before_any_payment(self):
        from game.systems.planet_buildings import start_building
        builder = next(e for e in self.st.entities.values() if e.data_id == 'imperial_constructor' and e.owner == 0)
        builder.pos = Vec3(-17000, 0, -5000)
        self.planet.colonized_by = 0
        used = self.p.command_used(self.st.entities)
        self.p.command_capacity = used + 7  # research 5 + surface 1 + orbital 1
        self.assertTrue(self.gm.construction.start_station(builder.id, 'research_station', builder.pos, 0))
        self.assertFalse(self.gm.construction.command_available(0, 3))
        self.assertTrue(start_building(self.gm.construction, self.planet.id, 'planet_extractor', 0))
        self.assertTrue(self.gm.construction.start_satellite(self.planet.id, 'defense_satellite', 0))
        self.assertEqual(self.p.command_used(self.st.entities), used + 7)
        bank = (self.p.credits, self.p.materials, self.p.energy, self.p.crew)
        queue = json.loads(json.dumps(self.planet.build_queue))
        self.assertFalse(start_building(self.gm.construction, self.planet.id, 'planet_trade_hub', 0))
        self.assertFalse(self.gm.construction.start_satellite(self.planet.id, 'attack_satellite', 0))
        self.assertFalse(self.gm.construction.start_station(builder.id, 'sensor_station', builder.pos + Vec3(900, 0, 0), 0))
        yard = next(e for e in self.st.entities.values() if e.data_id == 'shipyard' and e.owner == 0)
        self.assertEqual(self.gm.construction.start_ship(yard.id, 'imperial_corvette', 0), 0)
        self.assertEqual((self.p.credits, self.p.materials, self.p.energy, self.p.crew), bank)
        self.assertEqual(self.planet.build_queue, queue)
        self.assertTrue(any(t['text'] == 'Command capacity reached' for t in self.st.floating_texts))
        builder.crew = 0
        self.assertFalse(self.gm.construction.command_available(0, 1))
        builder.build_queue.clear()  # cancellation releases the reservation
        self.assertTrue(self.gm.construction.command_available(0, 5))
        builder.alive = False
        self.planet.colonized_by = 1  # old-owner paid colony work cannot reserve the new owner's pool
        self.assertEqual(self.p.command_used(self.st.entities), used - self.ds.command_cost(builder))
        self.assertEqual(self.st.players[1].command_used(self.st.entities),
                         sum(self.ds.command_cost(e) for e in self.st.entities.values() if e.alive and e.owner == 1))

    def test_every_live_station_costs_one_except_research_five(self):
        before = self.p.command_used(self.st.entities)
        for index, kind in enumerate(self.ds.stations):
            with self.subTest(kind=kind):
                entity = self.gm.factory.spawn_station(kind, 0, Vec3(18000, 0, index * 1000))
                expected = 5 if kind == 'research_station' else 1
                self.assertEqual(self.ds.command_cost(entity), expected)
                self.assertEqual(self.p.command_used(self.st.entities), before + expected)
                entity.crew = 0  # abandonment is not destruction
                self.assertEqual(self.p.command_used(self.st.entities), before + expected)
                entity.owner = 1
                self.assertEqual(self.p.command_used(self.st.entities), before)
                entity.owner = 0
                entity.alive = False
                self.assertEqual(self.p.command_used(self.st.entities), before)


if __name__ == '__main__':
    unittest.main()
