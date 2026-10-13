"""Surface production and lifecycle through authoritative manager ticks."""
import json
import unittest
from helpers import make_game, run_for, run_until
from game.core.commands import PlayerCommand
from game.core.vectors import Vec3


class PlanetBuildingTests(unittest.TestCase):
    def test_ai_surface_purchase_is_serialized_reserved_and_not_duplicated(self):
        from game.ai.ai import AIPlayer
        ai = AIPlayer(self.st, 0)
        self.gm.factory.spawn_station('mining_station', 0, Vec3(-9000, 0, 8000))
        before = self.st.players[0].credits
        ai._maybe_expand(ai.home_station())
        orders = [c for c in self.st.command_queue if c.type == 'build_planet_building']
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0], PlayerCommand.from_dict(orders[0].to_dict()))
        self.assertEqual(self.st.players[0].credits, before)
        reserve = ai._infrastructure_reserve()
        self.assertTrue(all(ai._projected_budget()[k] >= reserve[k] for k in reserve))
        ai._maybe_expand(ai.home_station())
        self.assertEqual(len([c for c in self.st.command_queue if c.type == 'build_planet_building']), 1)
        self.gm.step(1 / 30)
        self.assertTrue(any(w['kind'] == 'planet_building' for w in self.planet.build_queue))
        self.st.command_queue.clear()
        self.st.players[0].credits = 5000
        ai._maybe_expand(ai.home_station())
        self.assertFalse(any(c.type == 'build_planet_building' for c in self.st.command_queue))

    def test_precise_manager_continuation_paid_income_and_capture(self):
        from game.core.manager import GameManager
        from game.core.state import GameState
        def snapshot(gm):
            return json.loads(json.dumps(gm.state.to_dict(precise=True)))
        self.build('planet_trade_hub')
        self.planet.build_queue[0]['time_left'] = 0.123456789
        restored = GameManager(GameState.from_dict(snapshot(self.gm)))
        self.assertEqual(snapshot(self.gm), snapshot(restored))
        for _ in range(12):
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(snapshot(self.gm), snapshot(restored))
        building = self.buildings()[0]
        before = self.st.players[0].credits
        self.gm.step(1 / 30)
        restored.step(1 / 30)
        self.assertGreater(self.st.players[0].credits, before)
        self.assertEqual(snapshot(self.gm), snapshot(restored))
        self.build()
        captor = self.gm.factory.spawn_ship('imperial_colonizer', 1,
            self.planet.pos + Vec3(0, 0, self.planet.radius + 300))
        self.st.queue_command(PlayerCommand('colonize', 1, unit_ids=(captor.id,), target_id=self.planet.id))
        run_for(self.gm, 14)
        self.assertEqual(self.planet.colonized_by, 0)
        restored = GameManager(GameState.from_dict(snapshot(self.gm)))
        self.assertEqual(snapshot(self.gm), snapshot(restored))
        for _ in range(65):
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(snapshot(self.gm), snapshot(restored))
        self.assertEqual(self.planet.colonized_by, 1)
        self.assertEqual(building.owner, 1)
        self.assertEqual(self.planet.build_queue, [])
        self.assertFalse(self.st.game_over)

    def test_surface_catalogue_validation_is_wired_into_store(self):
        ds = self.gm.ds
        for value in (0, 7, True, 6.5):
            ds.rules['planet_buildings'] = {'slot_cap': value}
            with self.subTest(value=value), self.assertRaises(ValueError):
                ds._validate()
        ds.rules['planet_buildings'] = {'slot_cap': 6}
        ship = ds.ships['imperial_constructor']
        ship.can_build_stations.append('planet_extractor')
        with self.assertRaises(ValueError):
            ds._validate()

    def test_hostile_command_exclusion_at_admission_and_paid_completion(self):
        from game.systems.planet_buildings import planet_building_site
        site, _ = planet_building_site(self.planet, 0)
        hostile = self.gm.factory.spawn_station('command_station', 1, site + Vec3(2999, 0, 0))
        before = self.st.players[0].credits
        self.build()
        self.assertEqual(self.planet.build_queue, [])
        self.assertGreaterEqual(self.st.players[0].credits, before)
        hostile.pos = site + Vec3(3000, 0, 0)
        self.build()
        self.assertEqual(len(self.planet.build_queue), 1)
        hostile.pos = site + Vec3(2999, 0, 0)
        run_until(self.gm, lambda: not self.planet.build_queue)
        self.assertEqual(self.buildings(), [])
        self.assertEqual(self.planet.build_queue, [])

    def test_partial_surface_shield_applies_efficiency_once_and_credits_drained_pool_xp(self):
        generator = self.build_and_wait('planet_shield_generator')
        surface = self.build_and_wait()
        attacker = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(12000, 0, 12000))
        generator.crew = generator.max_crew / 2
        before_hull = surface.hull
        before_pool = sum(generator.shields.values())
        self.st.damage_queue.append(dict(target=surface, damage=100, shield_mult=1,
            armor_mult=1, system_mult=0, attacker=attacker))
        self.gm.step(1 / 30)
        self.assertAlmostEqual(sum(generator.shields.values()), before_pool - 50)
        self.assertAlmostEqual(surface.hull, before_hull - 50)
        self.assertAlmostEqual(attacker.xp, 1)

    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.planet = next(e for e in self.st.entities.values() if e.data_id == 'temperate')
        self.planet.colonized_by = 0
        p = self.st.players[0]
        p.credits = p.materials = p.energy = p.crew = 100000

    def build(self, kind='planet_extractor'):
        self.st.queue_command(PlayerCommand('build_planet_building', 0,
            target_id=self.planet.id, station_kind=kind))
        self.gm.step(1 / 30)

    def buildings(self):
        return [e for e in self.st.entities.values()
                if e.alive and e.planet_id == self.planet.id and e.planet_building_slot is not None]

    def build_and_wait(self, kind='planet_extractor'):
        """Order surface work and tick until that building stands.

        The wait is on the delivered entity, not a fixed number of seconds: the
        surface build time is derived from the building's resource cost (#95),
        so a literal here would silently stop covering the dearer buildings.
        Returns the new building.
        """
        before = {e.id for e in self.buildings()}
        self.build(kind)
        run_until(self.gm, lambda: any(e.id not in before for e in self.buildings()))
        return next(e for e in self.buildings() if e.id not in before)

    def test_pulsar_engages_detected_ships_at_long_range_not_fighters(self):
        cannon = self.build_and_wait('planet_pulsar_cannon')
        enemy = self.gm.factory.spawn_ship('imperial_corvette', 1, cannon.pos + Vec3(3900, 0, 0))
        enemy.order_type = 'hold'
        fighter = self.gm.factory.spawn_ship('imperial_tie_squadron', 1, cannon.pos + Vec3(300, 0, 0))
        self.gm.factory.spawn_station('sensor_station', 0, enemy.pos + Vec3(0, 0, 500))
        before = enemy.hull + sum(enemy.shields.values())
        run_for(self.gm, 1)
        self.assertLess(enemy.hull + sum(enemy.shields.values()), before)
        self.assertEqual(cannon.current_target, enemy.id)
        self.assertFalse(self.gm.weapons._target_valid(cannon, fighter.id))
        cannon.systems['weapons'].hp = 0
        cannon.weapon_cooldowns.clear()
        before = enemy.hull + sum(enemy.shields.values())
        run_for(self.gm, .2)
        self.assertEqual(enemy.hull + sum(enemy.shields.values()), before)

    def test_pulsar_cannon_beats_at_its_own_gun_range(self):
        """Reported (#52): "when building a pulsar cannon we are not able to fire it".

        #81 shortened the battery's reach, so this now pins the GUARANTEE rather
        # than the number: whatever the catalogue says, the emplacement must see
        # that far and must actually fire across the whole band — and never past
        # it. A literal here would have to be edited every time the reach moves,
        # and the band it was checked at would silently stop matching it.
        """
        from game.systems import stats
        catalogued = float(self.gm.ds.weapons['planet_pulsar_beam'].range)
        self.assertAlmostEqual(catalogued, 6720.0)
        # The emplacement must also SEE that far: detection gates every launch,
        # so a beam range beyond its own sensor range would still never fire.
        station = self.gm.ds.stations['planet_pulsar_cannon']
        self.assertGreaterEqual(float(station.sensor_range), catalogued)
        cannon = self.build_and_wait('planet_pulsar_cannon')
        self.assertGreaterEqual(stats.effective_sensor_range(self.st, cannon),
                                catalogued)
        for distance in (2000.0, catalogued * 0.55, catalogued * 0.95):
            enemy = self.gm.factory.spawn_ship('imperial_cruiser', 1,
                                               cannon.pos + Vec3(distance, 0, 0))
            enemy.order_type = 'hold'
            cannon.weapon_cooldowns.clear()
            cannon.energy = cannon.max_energy
            before = enemy.total_shield() + enemy.hull
            run_for(self.gm, 1.5)
            self.assertEqual(cannon.current_target, enemy.id)
            self.assertLess(enemy.total_shield() + enemy.hull, before,
                            f'beam did not fire at {distance:.0f}u')
            enemy.alive = False
            self.st.dead_ids.append(enemy.id)
        # Beyond the gun: seen is fine, fired is not.
        out_of_range = self.gm.factory.spawn_ship(
            'imperial_cruiser', 1, cannon.pos + Vec3(catalogued * 1.2, 0, 0))
        out_of_range.order_type = 'hold'
        cannon.weapon_cooldowns.clear()
        before = out_of_range.total_shield() + out_of_range.hull
        run_for(self.gm, 2.0)
        self.assertFalse(self.st.can_see(0, out_of_range.id))
        self.assertIsNone(cannon.current_target)
        self.assertEqual(out_of_range.total_shield() + out_of_range.hull, before)

    def test_surface_shield_absorbs_only_surface_damage_and_scales_with_staffing(self):
        generator = self.build_and_wait('planet_shield_generator')
        surface = self.build_and_wait()
        satellite = self.gm.factory.spawn_station('attack_satellite', 0,
            self.planet.pos + Vec3(0, 0, self.planet.radius + 400))
        satellite.planet_id = self.planet.id
        ship = self.gm.factory.spawn_ship('imperial_corvette', 0, satellite.pos + Vec3(300, 0, 0))
        for e in (surface, satellite, ship):
            e.shields = {q: 0 for q in e.shields}
            e.last_hit_time = self.st.time
        before = {e.id: e.hull for e in (surface, satellite, ship)}
        pool = sum(generator.shields.values())
        for e in (surface, satellite, ship):
            self.st.damage_queue.append(dict(target=e, damage=100, shield_mult=1,
                armor_mult=1, system_mult=0, attacker_id=1))
        self.gm.step(1 / 30)
        self.assertEqual(surface.hull, before[surface.id])
        self.assertLess(satellite.hull, before[satellite.id])
        self.assertLess(ship.hull, before[ship.id])
        self.assertAlmostEqual(sum(generator.shields.values()), pool - 100)
        generator.crew = 0
        self.st.damage_queue.append(dict(target=surface, damage=100, shield_mult=1,
            armor_mult=1, system_mult=0, attacker_id=1))
        self.gm.step(1 / 30)
        self.assertLess(surface.hull, before[surface.id])

    def test_capture_transfers_finished_buildings_not_blockers_and_clears_queues(self):
        building = self.build_and_wait('planet_trade_hub')
        self.build()
        captor = self.gm.factory.spawn_ship('imperial_colonizer', 1,
            self.planet.pos + Vec3(0, 0, self.planet.radius + 300))
        building.current_target = captor.id
        building.order_target_id = captor.id
        building.order_type = 'attack'
        self.st.queue_command(PlayerCommand('colonize', 1, unit_ids=(captor.id,), target_id=self.planet.id))
        run_for(self.gm, 16)
        self.assertEqual(self.planet.colonized_by, 1)
        self.assertTrue(building.alive)
        self.assertEqual(building.owner, 1)
        self.assertIsNone(building.current_target)
        self.assertIsNone(building.order_target_id)
        self.assertEqual(self.planet.build_queue, [])
        self.assertEqual(len(self.buildings()), 1)
        from game.systems.planet_buildings import building_income
        self.assertEqual(building_income(self.st, self.planet)['credits'], 4)

    def test_paid_surface_slots_independent_from_satellites(self):
        from game.net.lan import _commands
        cmd = PlayerCommand('build_planet_building', 0, target_id=self.planet.id,
                            station_kind='planet_extractor')
        self.assertEqual(cmd, PlayerCommand.from_dict(cmd.to_dict()))
        _commands([cmd.to_dict()], 0)
        for _ in range(7):
            self.build()
        self.assertEqual(len(self.planet.build_queue), 6)
        self.assertEqual([w['slot'] for w in self.planet.build_queue], list(range(6)))
        self.assertTrue(self.gm.construction.start_satellite(self.planet.id, 'defense_satellite', 0))
        run_for(self.gm, 200)
        self.assertEqual(len(self.buildings()), 6)
        self.assertTrue(all(e.satellite_slot is None for e in self.buildings()))
        from game.systems.planet_buildings import building_slots, building_rules
        self.assertEqual(building_rules()['slot_cap'], 6)
        self.assertEqual(building_slots(self.st, self.planet), set(range(6)))
        self.assertFalse(self.st.game_over)
