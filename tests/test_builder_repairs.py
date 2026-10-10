"""Paid equipment-only field service through serialized manager commands."""
import json
import unittest
from helpers import make_game
from game.core.commands import PlayerCommand
from game.core.vectors import Vec3
from game.core.manager import GameManager
from game.core.state import GameState


def precise(st):
    return json.loads(json.dumps(st.to_dict(precise=True)))


class TestBuilderRepairs(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.builder = self.gm.factory.spawn_ship('imperial_constructor', 0, Vec3())
        self.target = self.gm.factory.spawn_station('shipyard', 0, Vec3(500, 0, 0))
        self.target.crew = 0
        self.target.systems['life_support'].hp = 0
        self.target.hull -= 100
        # Isolate service accounting from station income and crew auto-recruitment.
        self.gm.ds.rules['economy']['planet_income'] = {}
        for sd in self.gm.ds.stations.values():
            sd.income = {}

    def order(self, player=0, target=None):
        cmd = PlayerCommand('repair', player, unit_ids=(self.builder.id,),
                            target_id=self.target.id if target is None else target)
        self.st.queue_command(PlayerCommand.from_dict(json.loads(json.dumps(cmd.to_dict()))))

    def test_docks_service_own_ships_not_stations_or_auxiliary_craft(self):
        dock = self.gm.factory.spawn_station('repair_dock', 0, Vec3(500, 0, 0))
        ship = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3(600, 0, 0))
        ship.crew = 0
        ship.hull -= 100
        self.target.systems['life_support'].hp = 10
        self.st.grid.rebuild(self.st.entities)
        hull = self.target.hull
        self.gm.economy.update(1)
        self.assertEqual(self.target.hull, hull)
        self.assertEqual(self.target.systems['life_support'].hp, 10)
        self.assertGreater(ship.hull, ship.max_hull - 100)
        self.assertFalse(self.gm.recovery.repairs_support(dock, self.target))

    def test_repair_explore_commands_have_catalogue_and_lan_validation(self):
        from game.core.commands import COMMAND_TYPES
        from game.net.lan import _commands
        for kind in ('repair', 'explore'):
            self.assertIn(kind, COMMAND_TYPES)
            data = PlayerCommand(kind, 0, unit_ids=(self.builder.id,),
                                 target_id=self.target.id if kind == 'repair' else None).to_dict()
            self.assertEqual(_commands([data], 0), [data])
        for bad in (None, True, '1', [], 0):
            data = {'type': 'repair', 'player': 0, 'unit_ids': [self.builder.id]}
            if bad is not None:
                data['target_id'] = bad
            with self.assertRaises(ValueError):
                _commands([data], 0)
            self.st.queue_command(PlayerCommand('repair', 0, unit_ids=(self.builder.id,), target_id=bad))
            self.gm.commands.consume()

    def test_authorized_orders_cancel_but_spoofs_and_malformed_ids_do_not(self):
        self.order()
        self.gm.commands.consume()
        for ids in ((True,), ('1',), ([],)):
            self.st.queue_command(PlayerCommand('stop', 0, unit_ids=ids))
            self.gm.commands.consume()
            self.assertEqual(self.builder.order_type, 'repair')
        self.st.queue_command(PlayerCommand('stop', 1, unit_ids=(self.builder.id,)))
        self.gm.commands.consume()
        self.assertEqual(self.builder.order_type, 'repair')
        self.st.queue_command(PlayerCommand('repair', 0, unit_ids=(self.builder.id,), target_id=None))
        self.gm.commands.consume()
        self.assertEqual(self.builder.order_type, 'idle')

    def test_repair_and_spacing_rules_are_validated(self):
        for block, keys in [('exploration', ['threat_margin', 'arrival_radius']),
                            ('engineer_repairs', ['hp_per_second', 'credits_per_hp', 'materials_per_hp', 'range']),
                            ('economy', ['trade_station_min_distance', 'enemy_command_build_min_distance'])]:
            for key in keys:
                for bad in (0, -1, True, 'fast', float('nan'), float('inf')):
                    with self.subTest(block=block, key=key, bad=bad):
                        cfg = self.gm.ds.rules.setdefault(block, {})
                        previous = cfg.get(key)
                        cfg[key] = bad
                        with self.assertRaises(ValueError):
                            self.gm.ds._validate()
                        if previous is None:
                            cfg.pop(key)
                        else:
                            cfg[key] = previous

    def test_explore_manager_dispatch_and_owned_replacement(self):
        fighter = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())
        self.st.queue_command(PlayerCommand('explore', 0, unit_ids=(fighter.id,)))
        self.gm.step(1 / 30)
        self.assertEqual(fighter.order_type, 'explore')
        self.assertIs(self.st._exploration_system, self.gm.exploration)
        self.st.queue_command(PlayerCommand('repair', 1, unit_ids=(fighter.id,), target_id=self.target.id))
        self.gm.commands.consume()
        self.assertEqual(fighter.order_type, 'explore')
        self.st.queue_command(PlayerCommand('repair', 0, unit_ids=(fighter.id,), target_id=self.target.id))
        self.gm.commands.consume()
        self.assertEqual(fighter.order_type, 'idle')

    def test_helper_and_start_reject_foreign_nonlive_or_colonizer_builders(self):
        from game.systems.repairs import builder_capable, repair_reason
        self.assertTrue(builder_capable(self.st, self.builder))
        colonizer = self.gm.factory.spawn_ship('imperial_colonizer', 0, Vec3())
        self.assertFalse(builder_capable(self.st, colonizer))
        before = precise(self.st)
        self.assertFalse(self.gm.repairs.start(self.builder, self.target, False))
        self.assertEqual(precise(self.st), before)
        self.assertFalse(self.gm.repairs.start(self.builder, self.target, 1))
        self.assertEqual(precise(self.st), before)
        self.target.owner = 1
        self.assertTrue(repair_reason(self.st, self.builder, self.target))
        self.target.owner = 0
        self.st.entities.pop(self.target.id)
        self.assertTrue(repair_reason(self.st, self.builder, self.target))
        self.assertFalse(self.gm.repairs.start(self.builder, self.target, 0))

    def test_budget_caps_actual_damage_and_pauses_without_charge(self):
        p = self.st.players[0]
        p.credits, p.materials = 100, .15
        self.order()
        self.gm.step(.5)
        self.assertAlmostEqual(self.target.systems['life_support'].hp, 1.5)
        self.assertAlmostEqual(p.credits, 99.7)
        self.assertAlmostEqual(p.materials, 0)
        self.gm.step(.5)
        self.assertAlmostEqual(p.credits, 99.7)
        for s in self.target.systems.values():
            s.hp = s.max_hp
        self.target.hull = self.target.max_hull - .125
        p.materials = 100
        credits = p.credits
        self.gm.step(.5)
        self.assertEqual(self.target.hull, self.target.max_hull)
        self.assertAlmostEqual(p.credits, credits - .025)
        self.assertEqual(self.builder.order_type, 'idle')
        banks = (p.credits, p.materials)
        self.order()
        self.gm.step(.5)
        self.assertEqual((p.credits, p.materials), banks)

    def test_half_staffing_scales_shared_budget_once_and_repairs_all_subsystems(self):
        self.builder.crew = self.builder.max_crew // 2
        self.order()
        self.gm.step(1)
        self.assertAlmostEqual(self.target.systems['life_support'].hp, 10)
        for s in self.target.systems.values():
            s.hp = s.max_hp
        self.target.hull = self.target.max_hull
        for name in ('sensors', 'weapons'):
            self.target.systems[name].hp -= 4
        credits = self.st.players[0].credits
        self.gm.step(1)
        for s in self.target.systems.values():
            self.assertEqual(s.hp, s.max_hp)
        self.assertAlmostEqual(self.st.players[0].credits, credits - 1.6)
        self.assertEqual(self.target.crew, 0)

    def test_remote_work_travels_stops_and_invalidates_before_movement(self):
        self.target.pos = Vec3(0, 0, 2200)
        credits = self.st.players[0].credits
        self.order()
        self.gm.step(.1)
        self.assertEqual(self.builder.order_type, 'repair')
        self.assertGreater(self.builder.pos.z, 0)
        self.assertEqual(self.target.systems['life_support'].hp, 0)
        self.assertEqual(self.st.players[0].credits, credits)
        for _ in range(1200):
            self.gm.step(1 / 30)
            if self.target.systems['life_support'].hp > 0:
                break
        self.assertGreater(self.target.systems['life_support'].hp, 0)
        position = self.builder.pos.copy()
        for _ in range(5):
            self.gm.step(1 / 30)
        self.assertEqual(self.builder.pos, position)
        self.target.owner = 1
        self.builder.vel = Vec3(0, 0, 100)
        credits = self.st.players[0].credits
        self.gm.step(.1)
        self.assertEqual(self.builder.order_type, 'idle')
        self.assertEqual(self.builder.pos, position)
        self.assertEqual(self.st.players[0].credits, credits)

    def test_exact_mid_travel_and_mid_repair_restored_continuation(self):
        self.target.pos = Vec3(0.123456789, 0, 2100.987654321)
        self.order()
        self.gm.step(.1)
        self.gm.visibility.update()
        for phase in ('travel', 'repair'):
            if phase == 'repair':
                self.builder.pos = Vec3(0, 0, 1700)
                self.gm.step(.123456789)
            snapshot = precise(self.st)
            restored = GameManager(GameState.from_dict(snapshot))
            restored.ds.rules['economy']['planet_income'] = {}
            for sd in restored.ds.stations.values():
                sd.income = {}
            self.assertEqual(precise(restored.state), snapshot)
            for _ in range(15):
                self.gm.step(1 / 30)
                restored.step(1 / 30)
                self.assertEqual(precise(restored.state), precise(self.st))

    def test_paid_service_prioritizes_support_and_never_creates_crew(self):
        p = self.st.players[0]
        credits, materials, crew = p.credits, p.materials, p.crew
        self.order()
        self.gm.step(.5)
        self.assertEqual(self.builder.order_type, 'repair')
        self.assertAlmostEqual(self.target.systems['life_support'].hp, 10)
        self.assertAlmostEqual(self.target.hull, self.target.max_hull - 100)
        self.assertAlmostEqual(p.credits, credits - 2)
        self.assertAlmostEqual(p.materials, materials - 1)
        self.assertEqual(self.target.crew, 0)
        self.assertEqual(p.crew, crew)
