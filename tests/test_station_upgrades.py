"""Station refits (#77): five paid levels, their ladder and their effects.

The issue asked for station levels bought with a button, raising hull and shields
on every step, and — depending on what the hull is for — firepower, resource
output or convoy traffic. These tests hold the ladder (cost and time derived from
the station's own catalogue bill), eligibility (planet-built hardware is out of
scope), every bonus category, the command seam, the cancel/refund path, the save
graph and the panel.
"""
import json
import unittest
from types import SimpleNamespace

import pygame

from helpers import make_game, run_until
from game.core.commands import COMMAND_TYPES, PlayerCommand, UpgradeStationCommand
from game.core.state import GameState
from game.core.vectors import Vec3
from game.net.replay import state_checksum
from game.systems import stats, upgrades

DT = 1 / 30

YARD_KINDS = ('command_station', 'mining_station', 'shipyard', 'research_station',
              'defense_platform', 'sensor_station', 'trade_station', 'fighter_platform',
              'repair_dock', 'energy_relay')
PLANET_KINDS = ('planet_extractor', 'planet_trade_hub', 'planet_shield_generator',
                'planet_pulsar_cannon', 'defense_satellite', 'attack_satellite')


def rich(player, amount=100000):
    player.credits = player.materials = player.energy = player.crew = amount


def resources(player):
    return (player.credits, player.materials, player.energy, player.crew)


def strip_field(graph, field):
    """Drop `field` from every tagged Entity node in a runtime graph, in place."""
    pending = [graph]
    while pending:
        node = pending.pop()
        if isinstance(node, list):
            if len(node) == 3 and node[:2] == ['object', 'Entity']:
                node[2].pop(field, None)
            pending.extend(node)
        elif isinstance(node, dict):
            pending.extend(node.values())


def graph_entity_node(graph, entity_id):
    """The tagged Entity node for `entity_id` in a runtime graph, or None."""
    pending = [graph]
    while pending:
        node = pending.pop()
        if isinstance(node, list):
            if len(node) == 3 and node[:2] == ['object', 'Entity']:
                id_field = node[2].get('id')
                if isinstance(id_field, list) and id_field[1] == entity_id:
                    return node
            pending.extend(node)
        elif isinstance(node, dict):
            pending.extend(node.values())
    return None


class RefitBase(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.ds = self.gm.ds
        self.player = self.st.players[0]
        rich(self.player)
        self.observer = next(e for e in self.st.entities.values()
                             if e.owner == 0 and e.is_ship)

    def spawn(self, kind, away=400):
        return self.gm.factory.spawn_station(kind, 0, self.observer.pos + Vec3(0, 0, away))

    def assertBilled(self, before, cost, fraction=1.0, tol=0.5):
        """Compare a resource bill with a tolerance: passive income accrues per tick."""
        for key, index in (('credits', 0), ('materials', 1), ('energy', 2)):
            self.assertAlmostEqual(getattr(self.player, key),
                                   before[index] - cost.get(key, 0) * fraction, delta=tol)

    def refit(self, station, ticks=1):
        self.st.queue_command(UpgradeStationCommand(0, station.id))
        for _ in range(ticks):
            self.gm.step(DT)
        return station

    def complete(self, station):
        """Order a refit and run until the level actually lands."""
        target = upgrades.station_level(station) + 1
        self.refit(station)
        run_until(self.gm, lambda: upgrades.station_level(station) >= target,
                  limit_seconds=300)
        return station


class RefitRuleTests(RefitBase):
    """The tuning is validated at catalogue load and honoured at once."""
    def test_the_shipped_rules_give_five_levels_and_a_step_per_level(self):
        rules = upgrades.upgrade_rules(self.ds)
        self.assertEqual(upgrades.max_level(rules), 5)
        self.assertEqual(len(rules['cost_mult']), 4)
        self.assertEqual(len(rules['time_mult']), 4)

    def test_every_step_cost_and_time_entry_is_positive(self):
        for key in ('cost_mult', 'time_mult'):
            for value in upgrades.upgrade_rules(self.ds)[key]:
                self.assertGreater(value, 0)

    def test_the_store_refuses_a_level_cap_below_two(self):
        cfg = self.ds.rules['station_upgrades']
        for value in (1, 0, -3):
            with self.subTest(value=value):
                cfg['max_level'] = value
                with self.assertRaisesRegex(ValueError, 'max_level'):
                    self.ds._validate()
        cfg['max_level'] = 5

    def test_the_store_refuses_a_step_table_that_is_too_short(self):
        cfg = self.ds.rules['station_upgrades']
        cfg['cost_mult'] = [0.75, 1.1]
        with self.assertRaisesRegex(ValueError, 'cost_mult'):
            self.ds._validate()
        cfg['cost_mult'] = [0.75, 1.1, 1.5, 2.0]

    def test_the_store_refuses_an_unusable_step_multiplier(self):
        cfg = self.ds.rules['station_upgrades']
        for value in (0, -1, '1.5', float('nan'), float('inf')):
            with self.subTest(value=value):
                cfg['time_mult'] = [value, 0.85, 1.1, 1.4]
                with self.assertRaisesRegex(ValueError, 'time_mult'):
                    self.ds._validate()
        cfg['time_mult'] = [0.6, 0.85, 1.1, 1.4]

    def test_the_store_refuses_a_negative_bonus(self):
        cfg = self.ds.rules['station_upgrades']
        cfg['hull_bonus'] = -0.1
        with self.assertRaisesRegex(ValueError, 'hull_bonus'):
            self.ds._validate()
        cfg['hull_bonus'] = 0.1

    def test_retuned_bonuses_take_effect_at_once(self):
        """The per-shot callers are memoized; a replaced table must not go stale."""
        station = self.spawn('shipyard')
        station.upgrade_level = 2
        self.assertAlmostEqual(upgrades.hull_multiplier(station), 1.10)
        cfg = self.ds.rules['station_upgrades']
        cfg['hull_bonus'] = 0.5
        self.assertAlmostEqual(upgrades.hull_multiplier(station), 1.5)
        cfg['hull_bonus'] = 0.1

    def test_the_exclusion_list_covers_every_planet_built_type(self):
        from game.systems.planet_buildings import BUILDING_TYPES
        self.assertTrue(set(BUILDING_TYPES) <= set(upgrades.EXCLUDED))


class RefitLadderTests(RefitBase):
    """Cost and time are the station's own bill and build time, step by step."""
    def test_the_cost_is_the_stations_own_bill_times_the_step(self):
        station = self.spawn('shipyard')
        data = self.ds.stations['shipyard']
        cost = upgrades.upgrade_cost(station)
        self.assertEqual(cost, {'credits': int(round(data.cost_credits * 0.75)),
                                'materials': int(round(data.cost_materials * 0.75)),
                                'energy': int(round(data.cost_energy * 0.75))})
        self.assertEqual(cost, {'credits': 1050, 'materials': 1200, 'energy': 225})

    def test_a_refit_never_charges_crew(self):
        """A refit works on a hull that already has its complement."""
        cost = upgrades.upgrade_cost(self.spawn('shipyard'))
        self.assertNotIn('crew', cost)
        self.assertEqual(set(cost), {'credits', 'materials', 'energy'})

    def test_each_step_costs_and_takes_longer_than_the_last(self):
        station = self.spawn('shipyard')
        costs, times = [], []
        for level in (1, 2, 3, 4):
            station.upgrade_level = level
            costs.append(upgrades.upgrade_cost(station)['credits'])
            times.append(upgrades.upgrade_time(station))
        self.assertEqual(costs, sorted(costs))
        self.assertLess(costs[0], costs[-1])
        self.assertEqual(times, sorted(times))
        self.assertLess(times[0], times[-1])

    def test_a_bigger_hull_costs_more_to_refit(self):
        cheap = upgrades.upgrade_cost(self.spawn('sensor_station', 400))
        dear = upgrades.upgrade_cost(self.spawn('command_station', 1200))
        self.assertGreater(dear['credits'], cheap['credits'])
        self.assertGreater(dear['materials'], cheap['materials'])

    def test_the_time_is_the_stations_build_time_times_the_step(self):
        station = self.spawn('shipyard')
        self.assertAlmostEqual(upgrades.upgrade_time(station),
                               self.ds.stations['shipyard'].build_time * 0.60)
        self.assertAlmostEqual(upgrades.upgrade_time(station), 21.0)
        trade = self.spawn('trade_station', 900)
        self.assertAlmostEqual(upgrades.upgrade_time(trade),
                               self.ds.stations['trade_station'].build_time * 0.60)
        self.assertAlmostEqual(upgrades.upgrade_time(trade), 10.8)

    def test_the_full_ladder_costs_more_than_the_hull_itself(self):
        station = self.spawn('defense_platform')
        data = self.ds.stations['defense_platform']
        total = upgrades.upgrade_cost(station)['credits']
        for level in (2, 3, 4):
            station.upgrade_level = level
            total += upgrades.upgrade_cost(station)['credits']
        self.assertGreater(total, data.cost_credits)


class RefitEligibilityTests(RefitBase):
    """Yard stations only — the issue excludes everything built on a planet."""
    def test_every_yard_station_is_eligible(self):
        for kind in YARD_KINDS:
            with self.subTest(kind=kind):
                station = self.spawn(kind, 400)
                self.assertTrue(upgrades.eligible(station, self.ds))
                self.assertIsNotNone(upgrades.upgrade_cost(station))
                self.assertIsNotNone(upgrades.upgrade_time(station))

    def test_planet_built_hardware_is_not_eligible(self):
        from game.systems.planet_buildings import start_building
        planet = next(e for e in self.st.entities.values() if e.data_id == 'temperate')
        planet.colonized_by = 0
        for kind in PLANET_KINDS[:4]:
            with self.subTest(kind=kind):
                start_building(self.gm.construction, planet.id, kind, 0)
                run_until(self.gm, lambda k=kind: any(
                    e.data_id == k for e in self.st.entities.values()), limit_seconds=300)
                built = next(e for e in self.st.entities.values() if e.data_id == kind)
                self.assertFalse(upgrades.eligible(built, self.ds))
                self.assertIsNone(upgrades.upgrade_cost(built))
                self.assertIsNone(upgrades.upgrade_time(built))
                self.assertFalse(self.gm.construction.start_upgrade(built.id, 0))
                self.assertEqual(built.build_queue, [])

    def test_satellites_are_not_eligible(self):
        planet = next(e for e in self.st.entities.values() if e.data_id == 'temperate')
        planet.colonized_by = 0
        self.assertTrue(self.gm.construction.start_satellite(
            planet.id, 'defense_satellite', 0))
        run_until(self.gm, lambda: any(e.data_id == 'defense_satellite'
                                       for e in self.st.entities.values()),
                  limit_seconds=300)
        satellite = next(e for e in self.st.entities.values()
                         if e.data_id == 'defense_satellite')
        self.assertFalse(upgrades.eligible(satellite, self.ds))
        self.assertIsNone(upgrades.upgrade_cost(satellite))
        self.assertFalse(self.gm.construction.start_upgrade(satellite.id, 0))

    def test_a_planet_and_a_ship_are_not_eligible(self):
        planet = next(e for e in self.st.entities.values() if e.data_id == 'temperate')
        self.assertFalse(upgrades.eligible(planet, self.ds))
        self.assertEqual(upgrades.station_level(planet), 1)
        self.assertIsNone(upgrades.upgrade_cost(planet))
        constructor = next(e for e in self.st.entities.values() if e.is_construction)
        self.assertFalse(upgrades.eligible(constructor, self.ds))
        self.assertFalse(self.gm.construction.start_upgrade(constructor.id, 0))

    def test_an_unknown_station_id_is_not_eligible(self):
        station = self.spawn('shipyard')
        station.data_id = 'no_such_station'
        self.assertFalse(upgrades.eligible(station, self.ds))
        self.assertIsNone(upgrades.upgrade_cost(station))

    def test_only_a_hull_that_can_fire_is_armed(self):
        self.assertTrue(upgrades.is_armed(self.spawn('defense_platform'), self.ds))
        self.assertTrue(upgrades.is_armed(self.spawn('shipyard', 700), self.ds))
        self.assertFalse(upgrades.is_armed(self.spawn('mining_station', 1000), self.ds))
        self.assertFalse(upgrades.is_armed(self.spawn('trade_station', 1300), self.ds))

    def test_only_a_hull_with_an_income_table_produces(self):
        self.assertTrue(upgrades.produces(self.spawn('mining_station'), self.ds))
        self.assertTrue(upgrades.produces(self.spawn('trade_station', 700), self.ds))
        self.assertFalse(upgrades.produces(self.spawn('sensor_station', 1000), self.ds))


class RefitSimTests(RefitBase):
    """The command seam, the capacity it buys and every bonus category."""
    def test_the_command_seam_pays_queues_and_completes_the_level(self):
        station = self.spawn('shipyard')
        before = resources(self.player)
        cost = upgrades.upgrade_cost(station)
        self.assertIn('upgrade_station', COMMAND_TYPES)
        command = UpgradeStationCommand(0, station.id)
        self.assertEqual(command, PlayerCommand.from_dict(command.to_dict()))
        self.refit(station)
        self.assertEqual(len(station.build_queue), 1)
        item = station.build_queue[0]
        self.assertEqual(item['kind'], 'station_upgrade')
        self.assertEqual(item['level'], 2)
        self.assertEqual(item['cost'], cost)
        # a tick of passive income accrues while the command is delivered
        self.assertBilled(before, cost)
        self.assertAlmostEqual(self.player.crew, before[3], delta=0.5)
        run_until(self.gm, lambda: upgrades.station_level(station) == 2, limit_seconds=300)
        self.assertEqual(station.build_queue, [])
        rules = upgrades.upgrade_rules(self.ds)
        self.assertAlmostEqual(station.max_hull,
                               self.ds.stations['shipyard'].hull * (1 + rules['hull_bonus']))
        self.assertAlmostEqual(station.max_shield_quad,
                               self.ds.stations['shipyard'].shield_quad * (1 + rules['shield_bonus']))
        self.assertAlmostEqual(station.shield_regen,
                               self.ds.stations['shipyard'].shield_regen * (1 + rules['shield_regen_bonus']))

    def test_the_refit_ladder_compounds_over_all_four_steps(self):
        station = self.spawn('sensor_station')
        base_hull, base_quad = station.max_hull, station.max_shield_quad
        for expected in (2, 3, 4, 5):
            self.complete(station)
            self.assertEqual(upgrades.station_level(station), expected)
        rules = upgrades.upgrade_rules(self.ds)
        self.assertAlmostEqual(station.max_hull, base_hull * (1 + 4 * rules['hull_bonus']))
        self.assertAlmostEqual(station.max_shield_quad,
                               base_quad * (1 + 4 * rules['shield_bonus']))
        self.assertIsNone(upgrades.upgrade_cost(station))
        self.assertFalse(self.gm.construction.start_upgrade(station.id, 0))

    def test_a_damaged_station_stays_exactly_as_damaged(self):
        """A refit must never be usable as a paid repair."""
        station = self.spawn('shipyard')
        station.hull = station.max_hull * 0.25
        fraction = station.hull_fraction()
        self.complete(station)
        self.assertAlmostEqual(station.hull_fraction(), fraction, places=9)

    def test_shield_quads_are_scaled_not_topped_up(self):
        """A half-empty quad stays half empty and an empty one stays empty.

        Applied directly rather than through the timer: regeneration refills quads
        every tick, so a ticked assertion would be measuring regen, not the refit.
        """
        station = self.spawn('shipyard')
        station.shields['front'] = station.max_shield_quad * 0.5
        station.shields['rear'] = 0.0
        self.assertTrue(upgrades.apply_level(self.st, station, {'level': 2}))
        self.assertAlmostEqual(station.shields['front'], station.max_shield_quad * 0.5)
        self.assertEqual(station.shields['rear'], 0.0)
        station.shields['front'] = station.max_shield_quad
        self.assertTrue(upgrades.apply_level(self.st, station, {'level': 3}))
        self.assertAlmostEqual(station.shields['front'], station.max_shield_quad)

    def test_the_refit_adds_firepower_to_an_armed_station(self):
        station = self.spawn('defense_platform')
        base = stats.effective_weapon_damage(self.st, station, 10.0)
        station.upgrade_level = 3
        self.assertAlmostEqual(stats.effective_weapon_damage(self.st, station, 10.0),
                               base * 1.24)

    def test_the_ladder_is_level_driven_and_the_data_decides_who_uses_it(self):
        """An unarmed hull still has a level; it simply owns no weapon to scale.

        The bonus helpers are level-driven on purpose, so the category comes from
        the catalogue (empty `weapons` here) rather than from a hard-coded list of
        station names — the same rule lets a mod arm a mining station.
        """
        mine = self.spawn('mining_station')
        self.assertFalse(upgrades.is_armed(mine, self.ds))
        self.assertEqual(self.ds.stations['mining_station'].weapons, [])
        mine.upgrade_level = 5
        self.assertAlmostEqual(upgrades.damage_multiplier(mine), 1.48)

    def test_the_refit_adds_output_for_a_collecting_station(self):
        mine = self.spawn('mining_station')
        base = stats.effective_production_rate(self.st, mine, 100.0)
        self.assertAlmostEqual(base, 100.0)
        mine.upgrade_level = 3
        self.assertAlmostEqual(stats.effective_production_rate(self.st, mine, 100.0),
                               base * 1.30)

    def test_ships_and_planets_keep_the_baseline_bonuses(self):
        planet = next(e for e in self.st.entities.values() if e.data_id == 'temperate')
        planet.upgrade_level = 5            # a corrupt/legacy value must stay inert
        self.assertEqual(upgrades.damage_multiplier(planet), 1.0)
        self.assertEqual(upgrades.production_multiplier(planet), 1.0)
        self.assertEqual(upgrades.extra_shots(planet), 0)
        ship = next(e for e in self.st.entities.values() if e.owner == 0 and e.is_ship)
        ship.upgrade_level = 5
        self.assertEqual(upgrades.damage_multiplier(ship), 1.0)
        self.assertEqual(upgrades.extra_shots(ship), 0)

    def test_every_weapon_mount_fires_more_shots_per_volley(self):
        platform = self.spawn('defense_platform')
        target = self.gm.factory.spawn_ship(
            'imperial_corvette', 1, platform.pos + Vec3(180, 0, 0))
        volleys = {}
        for level in (1, 2):
            platform.upgrade_level = level
            platform.energy = 1e6
            platform.weapon_cooldowns.clear()
            platform.current_target = target.id
            before = len(self.st.projectiles)
            self.gm.weapons._ship_weapons(platform, DT, is_static=True)
            volleys[level] = len(self.st.projectiles) - before
        self.assertGreater(volleys[1], 0)
        self.assertGreater(volleys[2], volleys[1])

    def test_a_refitted_market_releases_more_and_richer_convoys(self):
        first = self.spawn('trade_station')
        second = self.spawn('trade_station', 900)
        first.upgrade_level = 3             # two steps: +30% cargo, one extra convoy
        base_cargo = float(self.gm.trading.cfg.get('cargo_credits', 150.0))
        self.gm.trading._spawn_convoys()
        convoys = [e for e in self.st.entities.values() if e.data_id == 'trade_convoy']
        self.assertEqual(len(convoys), 3)
        self.assertEqual({c.cargo_credits for c in convoys if c.convoy_source == first.id},
                         {base_cargo * 1.3})
        self.assertEqual({c.cargo_credits for c in convoys if c.convoy_source == second.id},
                         {base_cargo})

    def test_a_refit_is_refused_when_the_player_cannot_pay(self):
        station = self.spawn('shipyard')
        self.player.credits = self.player.materials = self.player.energy = 0
        before = resources(self.player)
        self.assertFalse(self.gm.construction.start_upgrade(station.id, 0))
        self.assertEqual(station.build_queue, [])
        self.assertEqual(resources(self.player), before)
        self.assertEqual(upgrades.station_level(station), 1)

    def test_another_players_station_is_refused(self):
        station = self.spawn('shipyard')
        before = resources(self.player)
        self.assertFalse(self.gm.construction.start_upgrade(station.id, 1))
        self.assertEqual(station.build_queue, [])
        self.assertEqual(resources(self.player), before)

    def test_an_uncrewed_station_cannot_be_refitted(self):
        station = self.spawn('shipyard')
        station.crew = 0
        before = resources(self.player)
        self.assertFalse(self.gm.construction.start_upgrade(station.id, 0))
        self.assertEqual(station.build_queue, [])
        self.assertEqual(resources(self.player), before)

    def test_a_second_refit_is_refused_while_one_is_pending(self):
        station = self.spawn('shipyard')
        self.refit(station)
        after_pay = resources(self.player)
        self.assertFalse(self.gm.construction.start_upgrade(station.id, 0))
        self.assertEqual(resources(self.player), after_pay)
        self.assertEqual(len(station.build_queue), 1)

    def test_a_refit_never_supersedes_the_units_it_names(self):
        """Only a new order supersedes old work — a refit is a queue edit."""
        planet = next(e for e in self.st.entities.values() if e.data_id == 'temperate')
        colonizer = self.gm.factory.spawn_ship(
            'imperial_colonizer', 0, planet.pos + Vec3(0, 0, planet.radius + 300))
        self.assertTrue(self.gm.construction.start_colonize(colonizer.id, planet.id, 0))
        station = self.spawn('shipyard')
        self.st.queue_command(PlayerCommand('upgrade_station', 0,
                                            target_id=station.id,
                                            unit_ids=[colonizer.id]))
        self.gm.step(DT)
        self.assertEqual([w['kind'] for w in colonizer.build_queue], ['colonize'])
        self.assertEqual([w['kind'] for w in station.build_queue], ['station_upgrade'])

    def test_a_refit_reserves_no_command_capacity(self):
        """Command usage is the hull, not the work inside it (#70 accounting)."""
        station = self.spawn('shipyard')
        before = self.player.command_used(self.st.entities)
        self.refit(station)
        self.assertEqual(self.player.command_used(self.st.entities), before)

    def test_the_bonus_table_matches_the_documented_ladder(self):
        station = self.spawn('trade_station')
        station.upgrade_level = 5
        table = upgrades.bonus_table(station, self.ds)
        rules = upgrades.upgrade_rules(self.ds)
        self.assertEqual(table['level'], 5)
        self.assertEqual(table['max_level'], 5)
        self.assertAlmostEqual(table['hull_bonus'], 4 * rules['hull_bonus'])
        self.assertAlmostEqual(table['shield_bonus'], 4 * rules['shield_bonus'])
        self.assertAlmostEqual(table['shield_regen_bonus'], 4 * rules['shield_regen_bonus'])
        self.assertAlmostEqual(table['damage_bonus'], 4 * rules['damage_bonus'])
        self.assertEqual(table['extra_shots'], 4)
        self.assertAlmostEqual(table['production_bonus'], 4 * rules['production_bonus'])
        self.assertAlmostEqual(table['convoy_cargo_bonus'], 4 * rules['convoy_cargo_bonus'])
        self.assertEqual(table['extra_convoys'], 2)

    def test_a_legacy_or_corrupt_level_is_clamped(self):
        station = self.spawn('shipyard')
        station.upgrade_level = 0
        self.assertEqual(upgrades.station_level(station), 1)
        station.upgrade_level = 99
        self.assertEqual(upgrades.station_level(station), 5)


class RefitCancelTests(RefitBase):
    """The refit is queued paid work, so #94's cancel covers it too."""
    def test_cancelling_a_pending_refit_refunds_half_of_the_refit_bill(self):
        station = self.spawn('shipyard')
        cost = upgrades.upgrade_cost(station)
        self.refit(station)
        after_pay = resources(self.player)
        self.assertTrue(self.gm.construction.cancel_build(station.id, 0, 0))
        self.assertEqual(station.build_queue, [])
        self.assertAlmostEqual(self.player.credits, after_pay[0] + cost['credits'] * 0.5)
        self.assertAlmostEqual(self.player.materials, after_pay[1] + cost['materials'] * 0.5)
        self.assertAlmostEqual(self.player.energy, after_pay[2] + cost['energy'] * 0.5)

    def test_a_cancelled_refit_leaves_the_level_and_capacity_untouched(self):
        station = self.spawn('shipyard')
        hull, quad = station.max_hull, station.max_shield_quad
        self.refit(station)
        self.gm.construction.cancel_build(station.id, 0, 0)
        self.assertEqual(upgrades.station_level(station), 1)
        self.assertEqual(station.max_hull, hull)
        self.assertEqual(station.max_shield_quad, quad)

    def test_the_refund_comes_from_the_step_that_was_paid_not_the_head(self):
        station = self.spawn('shipyard')
        self.gm.construction.start_ship(station.id, 'imperial_corvette', 0, 1)
        station.build_queue.append({'kind': 'station_upgrade', 'item': 'shipyard',
                                    'level': 2, 'time_left': 5.0, 'total': 5.0,
                                    'status': 'paid', 'source_owner': 0,
                                    'cost': {'credits': 40, 'materials': 20, 'energy': 4}})
        before = resources(self.player)
        self.assertTrue(self.gm.construction.cancel_build(station.id, 0, 1))
        self.assertAlmostEqual(self.player.credits, before[0] + 20)
        self.assertAlmostEqual(self.player.materials, before[1] + 10)
        self.assertAlmostEqual(self.player.energy, before[2] + 2)


class RefitPersistenceTests(RefitBase):
    """Level is hull state: it rides the save graph and the desync digest."""
    def test_the_level_and_its_capacity_survive_a_snapshot_restore(self):
        station = self.spawn('shipyard')
        self.complete(station)
        payload = json.loads(json.dumps(self.st.to_dict(precise=True)))
        restored = GameState.from_dict(payload)
        copy = restored.entity(station.id)
        self.assertEqual(copy.upgrade_level, 2)
        self.assertAlmostEqual(copy.max_hull, station.max_hull)
        self.assertAlmostEqual(copy.max_shield_quad, station.max_shield_quad)
        self.assertAlmostEqual(copy.shield_regen, station.shield_regen)

    def test_a_pending_refit_survives_a_snapshot_restore(self):
        station = self.spawn('shipyard')
        self.refit(station)
        payload = json.loads(json.dumps(self.st.to_dict(precise=True)))
        restored = GameState.from_dict(payload)
        item = restored.entity(station.id).build_queue[0]
        self.assertEqual(item['kind'], 'station_upgrade')
        self.assertEqual(item['level'], 2)
        self.assertEqual(item['cost'], upgrades.upgrade_cost(station))

    def test_an_old_save_without_the_field_loads_at_level_one(self):
        """A save that predates #77 has the field nowhere: neither graph nor projection.

        Both defaults must hold — `migrate_saved_runtime` for the typed graph the LAN
        reconnect and replay use, `_entity_from_dict` for the ordinary projection — and
        the migration stays additive: it never recomputes capacity from the level.
        """
        station = self.spawn('shipyard')
        self.complete(station)
        payload = json.loads(json.dumps(self.st.to_dict(precise=True)))
        strip_field(payload['runtime_state'], 'upgrade_level')
        for entity in payload['entities'].values():
            entity.pop('upgrade_level', None)
        restored = GameState.from_dict(payload)
        self.assertEqual(restored.entity(station.id).upgrade_level, 1)
        self.assertAlmostEqual(restored.entity(station.id).max_hull, station.max_hull)

    def test_the_graph_decoder_is_exact_and_the_migration_is_what_saves_it(self):
        """The typed graph decoder demands the whole field set, so an old graph is
        refused until `migrate_saved_runtime` supplies the level — and the migrated
        node then decodes at level 1."""
        from game.core.runtime_snapshot import migrate_saved_runtime
        from game.net import reconnect
        station = self.spawn('shipyard')
        self.complete(station)
        graph = json.loads(json.dumps(self.st.to_dict(precise=True)))['runtime_state']
        node = graph_entity_node(graph, station.id)
        self.assertIsNotNone(node)
        strip_field(graph, 'upgrade_level')
        with self.assertRaises(ValueError):
            reconnect._decode(node)
        migrated = migrate_saved_runtime(graph)
        self.assertEqual(reconnect._decode(graph_entity_node(migrated, station.id)).upgrade_level, 1)

    def test_an_older_projection_still_validates_for_replay(self):
        """Additive fields must not break untrusted playback: a projection that
        predates #77 validates and replays at level 1."""
        from game.net.replay_validation import validate_state
        station = self.spawn('shipyard')
        payload = json.loads(json.dumps(self.st.to_dict(precise=True)))
        for entity in payload['entities'].values():
            entity.pop('upgrade_level', None)
        validate_state(payload)
        self.assertEqual(GameState.from_dict(payload, sanitize_save=False)
                         .entity(station.id).upgrade_level, 1)

    def test_a_save_that_precedes_only_the_projection_field_still_decodes(self):
        """The graph migration is what keeps a typed graph decodable, nothing more."""
        station = self.spawn('shipyard')
        self.complete(station)
        payload = json.loads(json.dumps(self.st.to_dict(precise=True)))
        strip_field(payload['runtime_state'], 'upgrade_level')
        restored = GameState.from_dict(payload)
        # The projection is authoritative for an ordinary save, so the level it
        # carries survives; the migration only stopped the graph from failing.
        self.assertEqual(restored.entity(station.id).upgrade_level, 2)

    def test_the_digest_separates_two_refit_levels(self):
        station = self.spawn('shipyard')
        baseline = state_checksum(self.st)
        station.upgrade_level = 2
        self.assertNotEqual(state_checksum(self.st), baseline)
        station.upgrade_level = 1
        self.assertEqual(state_checksum(self.st), baseline)


class RefitNetworkTests(RefitBase):
    """The refit command and the level must survive the wire, not just a save."""
    def test_the_lan_gate_accepts_the_refit_and_demands_the_station_id(self):
        from game.net import lan
        self.assertIn('upgrade_station', lan.COMMAND_TYPES)
        good = {'type': 'upgrade_station', 'player': 0, 'target_id': 12}
        self.assertEqual(len(lan._commands([good], 0)), 1)
        with self.assertRaises(ValueError):
            lan._commands([{'type': 'upgrade_station', 'player': 0}], 0)
        with self.assertRaises(ValueError):
            lan._commands([{**good, 'target_id': '12'}], 0)

    def test_the_level_survives_a_lan_reconnect_round_trip(self):
        """The typed graph — not only the save projection — must carry the level."""
        from game.net.lan import precise_checksum
        from game.net.reconnect import capture_snapshot, restore_snapshot
        station = self.spawn('shipyard')
        self.complete(station)
        before = precise_checksum(self.gm)
        restored = restore_snapshot(capture_snapshot(self.gm))
        copy = restored.state.entities[station.id]
        self.assertEqual(copy.upgrade_level, 2)
        self.assertAlmostEqual(copy.max_hull, station.max_hull)
        self.assertEqual(precise_checksum(restored), before)


class RefitUITests(RefitBase):
    """The panel offers the button the issue asked for, and only when it can act."""
    def setUp(self):
        super().setUp()
        from render.camera import Camera
        from render.hud import HUD
        from render.input import InputController
        self.station = self.spawn('shipyard')
        self.hud = HUD(1280, 800, self.st)
        self.ctrl = InputController(self.st, Camera(1280, 800), self.hud,
                                    SimpleNamespace(flash=lambda *_: None))

    def draw(self, selection):
        self.ctrl.selection = set(selection)
        self.hud.buttons.clear()
        self.hud.blocked_rects.clear()
        self.hud.scroll_rects.clear()
        self.hud._right_panel(self.ctrl.selection, 0)

    def click(self, point):
        for event in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self.ctrl.handle_event(pygame.event.Event(event, button=1, pos=point))

    def buttons(self, kind):
        return [b for b in self.hud.buttons if b['kind'] == kind]

    def test_the_panel_offers_the_refit_button_and_clicking_it_buys_the_step(self):
        self.draw({self.station.id})
        rows = self.buttons('upgrade_station')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['payload']['target_id'], self.station.id)
        before = resources(self.player)
        self.click(rows[0]['rect'].center)
        self.assertEqual(self.st.command_queue,
                         [UpgradeStationCommand(0, self.station.id)])
        self.gm.step(DT)
        cost = upgrades.upgrade_cost(self.station)
        self.assertBilled(before, cost)
        self.assertEqual(len(self.station.build_queue), 1)

    def test_a_pending_refit_shows_its_timer_and_a_cancel_row(self):
        self.refit(self.station)
        self.draw({self.station.id})
        self.assertEqual(self.buttons('upgrade_station'), [])
        cancels = [b for b in self.buttons('cancel_build')
                   if b['payload']['target_id'] == self.station.id]
        self.assertEqual(len(cancels), 1)
        self.assertEqual(cancels[0]['payload']['index'], 0)
        self.click(cancels[0]['rect'].center)
        self.gm.step(DT)
        self.assertEqual(self.station.build_queue, [])

    def test_a_maxed_station_offers_no_refit_button(self):
        self.station.upgrade_level = 5
        self.draw({self.station.id})
        self.assertEqual(self.buttons('upgrade_station'), [])

    def test_planet_built_hardware_gets_no_refit_block(self):
        planet = next(e for e in self.st.entities.values() if e.data_id == 'temperate')
        planet.colonized_by = 0
        from game.systems.planet_buildings import start_building
        start_building(self.gm.construction, planet.id, 'planet_extractor', 0)
        run_until(self.gm, lambda: any(e.data_id == 'planet_extractor'
                                       for e in self.st.entities.values()),
                  limit_seconds=300)
        extractor = next(e for e in self.st.entities.values()
                         if e.data_id == 'planet_extractor')
        self.draw({extractor.id})
        self.assertEqual(self.buttons('upgrade_station'), [])
        self.assertEqual([b for b in self.buttons('cancel_build')
                          if b['payload']['target_id'] == extractor.id], [])

    def test_a_stale_row_from_another_selection_cannot_buy_a_refit(self):
        self.draw({self.station.id})
        row = self.buttons('upgrade_station')[0]
        # The row is still in this frame's button list; the selection moved on
        # without a redraw, so the input-side check is all that stands between a
        # stale row and the player's resources.
        self.ctrl.selection = {self.observer.id}
        self.click(row['rect'].center)
        self.assertEqual(self.st.command_queue, [])
        self.ctrl.selection = {self.station.id}
        self.click(row['rect'].center)
        self.assertEqual(self.st.command_queue,
                         [UpgradeStationCommand(0, self.station.id)])

    def test_a_row_for_another_players_station_cannot_buy_a_refit(self):
        # The panel offers this player nothing for a hull it does not own: the action
        # panel drops every entity whose owner is not the local player, which is what
        # keeps an enemy station's refit out of reach here and everywhere else.
        enemy = self.gm.factory.spawn_station('defense_platform', 1,
                                              self.observer.pos + Vec3(0, 0, 1600))
        self.draw({enemy.id})
        self.assertEqual(self.buttons('upgrade_station'), [])
        self.assertEqual(self.st.command_queue, [])

    def test_a_row_left_over_from_a_capture_cannot_buy_a_refit(self):
        station = self.spawn('defense_platform')
        self.draw({station.id})
        row = self.buttons('upgrade_station')[0]
        station.owner = 1  # the station fell to the enemy after the frame was drawn
        self.click(row['rect'].center)
        self.assertEqual(self.st.command_queue, [])
        self.assertEqual(station.build_queue, [])


if __name__ == '__main__':
    unittest.main()
