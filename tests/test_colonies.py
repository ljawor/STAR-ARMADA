"""Planetary colony lifecycle through real manager ticks."""
import json
import unittest
from helpers import make_game, run_for
from game.core.commands import PlayerCommand
from game.core.vectors import Vec3


class ColonyTests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.planet = next(e for e in self.st.entities.values() if e.data_id == 'temperate')
        self.ship = self.gm.factory.spawn_ship('imperial_colonizer', 0,
            self.planet.pos + Vec3(0, 0, self.planet.radius + 300))

    def order(self):
        self.st.queue_command(PlayerCommand('colonize', 0, unit_ids=(self.ship.id,), target_id=self.planet.id))
        self.gm.step(1 / 30)

    def test_ai_satellites_do_not_starve_opening_mining(self):
        from game.ai.ai import AIPlayer
        self.planet.colonized_by = 0
        ai = AIPlayer(self.st, 0)
        ai._maybe_expand(ai.home_station())
        self.assertFalse(any(c.type == 'build_satellite' for c in self.st.command_queue))

    def test_all_eligible_planet_types_produce_crew_and_type_resources(self):
        from game.systems.colonies import COLONY_TYPES
        from game.data.store import DataStore
        ds = DataStore.get()
        for kind in sorted(COLONY_TYPES):
            with self.subTest(kind=kind):
                self.planet.data_id = kind
                self.planet.colonized_by = 0
                # Isolate declared colony output from base recruitment.
                for e in self.st.entities.values():
                    if e.is_station:
                        e.crew = 0
                self.gm.step(1 / 30)
                p = self.st.players[0]
                self.assertGreater(p.income_frame['crew'], 0)
                self.assertGreater(sum(p.income_frame[r] for r in ('credits', 'materials', 'energy')), 0)
                self.assertEqual(p.income_frame['credits'], ds.rules['economy']['planet_income'][kind].get('credits', 0))

    def test_satellite_intent_is_registered_for_lan_and_replay(self):
        from game.core.commands import COMMAND_TYPES
        from game.net.lan import _commands
        command = PlayerCommand('build_satellite', 0, target_id=self.planet.id, station_kind='defense_satellite')
        self.assertIn(command.type, COMMAND_TYPES)
        restored = PlayerCommand.from_dict(command.to_dict())
        self.assertEqual(command, restored)
        _commands([restored.to_dict()], 0)

    def test_capture_clears_old_owner_paid_queues_and_incoming_references(self):
        self.planet.colonized_by = 1
        dependent = self.gm.factory.spawn_ship('imperial_colonizer', 1, self.planet.pos + Vec3(2000, 0, 0))
        dependent.order_type = 'follow'
        dependent.order_target_id = self.planet.id
        self.planet.build_queue = [dict(kind='satellite', item='attack_satellite', time_left=1000., total=1000.,
            source_owner=1, slot=0, pos=[0, 0, 0], status='paid')]
        self.order()
        run_for(self.gm, 16)
        self.assertEqual(self.planet.colonized_by, 0)
        self.assertEqual(self.planet.build_queue, [])
        self.assertIsNone(dependent.order_target_id)
        self.assertIsNone(dependent.current_target)
        self.assertEqual(dependent.order_type, 'idle')
        self.assert_roundtrip_ticks(10)

    def test_source_nonoperational_ownership_and_target_transfer_abort_without_consumption(self):
        for mutation in ('crew', 'owner', 'target', 'type'):
            with self.subTest(mutation=mutation):
                self.setUp()
                self.order()
                run_for(self.gm, 6)
                if mutation == 'crew':
                    self.ship.crew = 0
                elif mutation == 'owner':
                    self.ship.owner = 1
                elif mutation == 'target':
                    self.planet.colonized_by = 1
                else:
                    self.planet.data_id = 'gas_giant'
                self.gm.step(1 / 30)
                self.assertEqual(self.ship.build_queue, [])
                self.assertTrue(self.ship.alive)
                run_for(self.gm, 16)
                self.assertNotEqual(self.planet.colonized_by, 0)

    def test_rejected_colony_replacement_cancels_existing_control(self):
        for rejected in ('gas', 'allied', 'protected'):
            for traveling in (False, True):
                for direct in (False, True):
                    with self.subTest(rejected=rejected, traveling=traveling, direct=direct):
                        self.setUp()
                        if traveling:
                            self.ship.pos = self.planet.pos + Vec3(0, 0, self.planet.radius + 2000)
                        self.order()
                        self.assertEqual(len(self.ship.build_queue), 1)
                        if rejected == 'gas':
                            target = next(e for e in self.st.entities.values() if e.data_id == 'gas_giant')
                        else:
                            target = next(e for e in self.st.entities.values()
                                          if e.is_planet and e.data_id == 'barren')
                            target.colonized_by = 1
                            if rejected == 'allied':
                                for player in self.st.players.values():
                                    player.team = 0
                            else:
                                satellite = self.gm.factory.spawn_station('defense_satellite', 1,
                                    target.pos + Vec3(target.radius + 500, 0, 0))
                                satellite.planet_id = target.id
                                satellite.crew = 0
                        if direct:
                            self.assertFalse(self.gm.construction.start_colonize(self.ship.id, target.id, 0))
                        else:
                            self.st.queue_command(PlayerCommand('colonize', 0,
                                unit_ids=(self.ship.id,), target_id=target.id))
                            self.gm.step(1 / 30)
                        self.assertEqual(self.ship.build_queue, [])
                        self.assertEqual(self.ship.order_type, 'idle')
                        self.assertIsNone(self.ship.order_target_pos)
                        self.assertIsNone(self.ship.order_target_id)
                        run_for(self.gm, 16)
                        self.assertIsNone(self.planet.colonized_by)
                        self.assertTrue(self.ship.alive)

    def test_foreign_replacement_cannot_cancel_existing_colony_mission(self):
        self.order()
        snapshot = lambda: json.loads(json.dumps(self.st.to_dict(precise=True)))
        before = snapshot()
        gas = next(e for e in self.st.entities.values() if e.data_id == 'gas_giant')
        self.assertFalse(self.gm.construction.start_colonize(self.ship.id, gas.id, 1))
        self.assertEqual(snapshot(), before)
        from game.systems.commands_handler import CommandHandler
        handler = CommandHandler(self.st, self.gm.construction, self.gm.research,
                                 self.gm.formations, self.gm.abilities)
        handler._apply(PlayerCommand('colonize', 1, unit_ids=(self.ship.id,), target_id=gas.id))
        self.assertEqual(snapshot(), before)
        handler._apply(PlayerCommand('stop', 1, unit_ids=(self.ship.id,)))
        self.assertEqual(snapshot(), before)
        run_for(self.gm, 16)
        self.assertEqual(self.planet.colonized_by, 0)
        self.assertFalse(self.ship.alive)

    def test_colony_order_detaches_fleet_clears_jump_and_replaces_mission(self):
        self.st.queue_command(PlayerCommand('fleet_create', 0, unit_ids=(self.ship.id,), name='Settlers'))
        self.gm.step(1 / 30)
        self.assertIsNotNone(self.ship.fleet_id)
        self.ship.jump_target = self.ship.pos.copy()
        self.ship.jump_charge = 2
        # jumping ships cannot start a colony mission
        self.assertFalse(self.gm.construction.start_colonize(self.ship.id, self.planet.id, 0))
        self.ship.jump_target = None
        self.ship.jump_charge = 0
        self.order()
        self.assertIsNone(self.ship.fleet_id)
        self.order()
        self.assertEqual(len(self.ship.build_queue), 1)
        self.st.queue_command(PlayerCommand('jump', 0, unit_ids=(self.ship.id,), target_pos=(0, 0, 0)))
        self.gm.step(1 / 30)
        self.assertEqual(self.ship.build_queue, [])

    def test_colony_tuning_controls_time_range_and_slot_cap(self):
        from game.data.store import DataStore
        DataStore.get().rules['colonies'] = dict(control_seconds=2.0, approach_range=1200.0, satellite_cap=2, orbit_clearance=500)
        self.ship.pos = self.planet.pos + Vec3(0, 0, self.planet.radius + 1000)
        self.order()
        run_for(self.gm, 3)
        self.assertEqual(self.planet.colonized_by, 0)
        for _ in range(3):
            self.st.queue_command(PlayerCommand('build_satellite', 0, target_id=self.planet.id, station_kind='defense_satellite'))
        self.gm.step(1 / 30)
        self.assertEqual(len(self.planet.build_queue), 2)

    def test_catalogue_rejects_invalid_colony_rules_and_bypass_entries(self):
        from game.data.store import DataStore
        ds = DataStore.get()
        for value in (True, 0, -1, 6.5, float('nan')):
            ds.rules['colonies'] = {'satellite_cap': value}
            with self.assertRaisesRegex(ValueError, 'satellite_cap'):
                ds._validate()
        ds.rules['colonies'] = {}
        ds._validate()  # omitted mod block has defaults
        ds.stations['shipyard'].builds_ships = ['imperial_colonizer']
        with self.assertRaisesRegex(ValueError, 'command'):
            ds._validate()

    def test_ai_eligible_capture_targets_use_observed_owner_and_attack_defenders(self):
        from game.ai.ai import AIPlayer
        ai = AIPlayer(self.st, 0)
        home = ai.home_station()
        # Public static geometry, last observed ownership: hidden mutation cannot affect choice.
        home.pos = self.planet.pos.copy()
        self.planet.colonized_by = 1
        self.gm.visibility.update()
        picked = ai._pick_colony_target(home)
        self.assertIs(picked, self.planet)
        satellite = self.gm.factory.spawn_station('defense_satellite', 1, self.planet.pos + Vec3(1100, 0, 0))
        satellite.planet_id = self.planet.id
        warship = self.gm.factory.spawn_ship('imperial_frigate', 0, satellite.pos + Vec3(300, 0, 0))
        self.gm.visibility.update()
        ai._maybe_expand(home)
        self.assertTrue(any(c.type == 'attack' and c.target_id == satellite.id for c in self.st.command_queue))
        self.assertFalse(any(c.type == 'colonize' for c in self.st.command_queue))
        self.assertNotIn('gas_giant', [ai._pick_colony_target(home).data_id])

    def test_ai_builds_colonizer_at_command_and_satellites_from_owned_planet(self):
        from game.ai.ai import AIPlayer
        ai = AIPlayer(self.st, 0)
        home = ai.home_station()
        self.ship.alive = False
        ai._maybe_expand(home)
        commands = self.st.command_queue
        self.assertTrue(commands)
        self.assertEqual(self.st.entity(commands[-1].unit_ids[0]).data_id, 'command_station')
        self.st.command_queue.clear()
        self.planet.colonized_by = 0
        self.gm.factory.spawn_station('mining_station', 0, Vec3(-9000, 0, 3000))
        self.gm.visibility.update()
        ai._maybe_expand(home)
        satellite_orders = [c for c in self.st.command_queue if c.type == 'build_satellite']
        self.assertEqual({c.station_kind for c in satellite_orders}, {'defense_satellite', 'attack_satellite'})
        self.assertTrue(all(c.target_id == self.planet.id for c in satellite_orders))

    def test_satellite_roles_and_missile_interception(self):
        defense = self.gm.factory.spawn_station('defense_satellite', 0, Vec3(0, 0, 3000))
        attack = self.gm.factory.spawn_station('attack_satellite', 0, Vec3(0, 0, 4000))
        enemy = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(100, 0, 3100))
        fighter = self.gm.factory.spawn_ship('imperial_tie_squadron', 1, Vec3(200, 0, 3100))
        self.gm.step(1 / 30)
        self.assertFalse(self.gm.weapons._target_valid(defense, enemy.id))
        self.assertTrue(self.gm.weapons._target_valid(defense, fighter.id))
        self.assertTrue(self.gm.weapons._target_valid(attack, enemy.id))
        self.assertFalse(self.gm.weapons._target_valid(attack, fighter.id))
        wd = self.gm.weapons.ds.weapons['missile_battery']
        self.gm.weapons._launch_projectiles(enemy, defense, wd, 1)
        missile = max(self.st.projectiles.values(), key=lambda p: p.id)
        missile.pos = defense.pos + Vec3(250, 0, 0)
        self.gm.step(1 / 30)
        self.assertNotIn(missile.id, self.st.projectiles)
        self.assertTrue(any(ev.type == 'missile_intercepted' for ev in self.st.events.log))

    def test_interception_reload_scales_with_staffing_and_weapon_health(self):
        defense = self.gm.factory.spawn_station('defense_satellite', 0, Vec3(0, 0, 3000))
        enemy = self.gm.factory.spawn_ship('imperial_corvette', 1, defense.pos + Vec3(250, 0, 0))
        defense.max_crew = 160
        defense.crew = 40
        defense.systems['weapons'].hp = defense.systems['weapons'].max_hp / 2
        defense.xp = 1000000  # stations must not acquire ship rank bonuses
        defense.energy = 0  # interception has no additional energy fee
        self.gm.visibility.update()
        wd = self.gm.weapons.ds.weapons['missile_battery']
        self.gm.weapons._launch_projectiles(enemy, defense, wd, 1)
        missile = max(self.st.projectiles.values(), key=lambda p: p.id)
        missile.pos = defense.pos + Vec3(250, 0, 0)
        self.gm.projectiles.update(1 / 30)
        self.assertNotIn(missile.id, self.st.projectiles)
        self.assertAlmostEqual(defense.ability_cooldowns['_intercept'],
            self.gm.weapons.ds.weapons['point_defense'].reload * 8)
        self.assertEqual(defense.energy, 0)

    def test_precise_satellite_combat_restore_with_partial_crew_and_inflight_missiles(self):
        defense = self.gm.factory.spawn_station('defense_satellite', 0, Vec3(0, 0, 3000))
        attack = self.gm.factory.spawn_station('attack_satellite', 0, Vec3(0, 0, 4000))
        enemy = self.gm.factory.spawn_ship('imperial_corvette', 1, attack.pos + Vec3(200, 0, 0))
        fighter = self.gm.factory.spawn_ship('imperial_tie_squadron', 1, defense.pos + Vec3(200, 0, 0))
        for satellite in (defense, attack):
            satellite.crew = satellite.max_crew // 2
            satellite.systems['weapons'].hp *= .57
            satellite.weapon_cooldowns[0] = .213579
            satellite.retarget_cooldown = .127593
        defense.ability_cooldowns['_intercept'] = .137591
        self.gm.visibility.update()
        self.gm.weapons._launch_projectiles(enemy, defense,
            self.gm.weapons.ds.weapons['missile_battery'], 2)
        missiles = sorted(self.st.projectiles)
        self.assertEqual(len(missiles), 2)
        for missile in self.st.projectiles.values():
            missile.pos = defense.pos + Vec3(250, 0, 0)
            missile.vel = Vec3()
            missile.life = 30
        health = lambda e: e.hull + sum(e.shields.values())
        before = (health(enemy), health(fighter))
        observed_health = []
        defense_shots = []
        def observe():
            observed_health.append((health(enemy), health(fighter)))
            defense_shots.extend(p.id for p in self.st.projectiles.values()
                                 if p.attacker_entity_id == defense.id and p.target_id == fighter.id)
        self.assert_roundtrip_ticks(90, observe=observe)
        self.assertTrue(all(pid not in self.st.projectiles for pid in missiles))
        self.assertTrue(any(ev.type == 'missile_intercepted' for ev in self.st.events.log))
        self.assertLess(min(h[0] for h in observed_health), before[0])
        self.assertTrue(defense_shots, 'restored defense role must fire at fighters')
        self.assertIn(0, attack.weapon_cooldowns)
        self.assertIn(0, defense.weapon_cooldowns)

    def test_disabled_weapon_subsystem_cannot_intercept(self):
        defense = self.gm.factory.spawn_station('defense_satellite', 0, Vec3(0, 0, 3000))
        enemy = self.gm.factory.spawn_ship('imperial_corvette', 1, defense.pos + Vec3(250, 0, 0))
        defense.systems['weapons'].hp = 0
        self.gm.visibility.update()
        self.gm.weapons._launch_projectiles(enemy, defense,
            self.gm.weapons.ds.weapons['missile_battery'], 1)
        missile = max(self.st.projectiles.values(), key=lambda p: p.id)
        missile.pos = defense.pos + Vec3(250, 0, 0)
        missile.vel = Vec3()
        self.gm.projectiles.update(1 / 30)
        self.assertIn(missile.id, self.st.projectiles)
        self.assertNotIn('_intercept', defense.ability_cooldowns)

    def test_gas_legacy_ownership_is_preserved_but_inert_and_no_colony_income(self):
        gas = next(e for e in self.st.entities.values() if e.data_id == 'gas_giant')
        before = self.st.players[0].energy
        gas.colonized_by = 0  # preserve legacy save history; no income or construction
        run_for(self.gm, 1)
        self.assertEqual(self.st.players[0].energy, before)
        self.assertEqual(gas.colonized_by, 0)
        self.assert_roundtrip_ticks(3)

    def test_precise_capture_and_satellite_restore_continuation(self):
        self.planet.colonized_by = 1
        self.order()
        run_for(self.gm, 5.3)
        self.assert_roundtrip_ticks(340)
        self.assertEqual(self.planet.colonized_by, 0)
        self.st.queue_command(PlayerCommand('build_satellite', 0, target_id=self.planet.id, station_kind='attack_satellite'))
        run_for(self.gm, 3.1)
        self.assert_roundtrip_ticks(700)
        self.assertTrue(any(e.planet_id == self.planet.id for e in self.st.entities.values()))
        self.assert_roundtrip_ticks(10)

    def assert_roundtrip_ticks(self, count, observe=None):
        from game.core.state import GameState
        from game.core.manager import GameManager
        snapshot = lambda st: json.loads(json.dumps(st.to_dict(precise=True)))
        data = snapshot(self.st)
        restored = GameManager(state=GameState.from_dict(data))
        self.assertEqual(data, snapshot(restored.state))
        self.assertEqual([(e.id, e.planet_id, e.satellite_slot) for e in self.st.entities.values()],
                         [(e.id, e.planet_id, e.satellite_slot) for e in restored.state.entities.values()])
        for _ in range(count):
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(snapshot(self.st), snapshot(restored.state))
            if observe is not None:
                observe()
        self.assertFalse(self.st.game_over)

    def test_capture_waits_for_all_live_satellites_and_resets_on_new_defender(self):
        self.planet.colonized_by = 1
        satellite = self.gm.factory.spawn_station('defense_satellite', 1, self.planet.pos + Vec3(1100, 0, 0))
        satellite.planet_id = self.planet.id
        satellite.crew = 0  # derelict still blocks
        self.assertFalse(self.gm.construction.start_colonize(self.ship.id, self.planet.id, 0))
        satellite.alive = False
        self.order()
        run_for(self.gm, 8)
        new = self.gm.factory.spawn_station('defense_satellite', 1, satellite.pos)
        new.planet_id = self.planet.id
        new.crew = 0
        self.gm.step(1 / 30)
        self.assertEqual(self.ship.build_queue[0]['time_left'], 15)
        run_for(self.gm, 10)
        self.assertEqual(self.planet.colonized_by, 1)
        new.alive = False
        run_for(self.gm, 10)
        self.assertEqual(self.planet.colonized_by, 1)
        run_for(self.gm, 6)
        self.assertEqual(self.planet.colonized_by, 0)

    def test_satellites_cannot_be_built_by_constructor_or_boarded(self):
        from game.data.store import DataStore
        from game.systems.boarding import boarding_reason
        ds = DataStore.get()
        constructor = next(e for e in self.st.entities.values() if e.owner == 0 and e.data_id == 'imperial_constructor')
        ds.ships[constructor.data_id].can_build_stations.append('defense_satellite')
        constructor.pos = Vec3(0, 0, 4000)
        self.assertFalse(self.gm.construction.start_station(constructor.id, 'defense_satellite', constructor.pos, 0))
        satellite = self.gm.factory.spawn_station('defense_satellite', 1, self.ship.pos + Vec3(100, 0, 0))
        satellite.planet_id = self.planet.id
        satellite.crew = 0
        satellite.shields = {q: 0 for q in satellite.shields}
        attacker = self.gm.factory.spawn_ship('imperial_frigate', 0, satellite.pos + Vec3(100, 0, 0))
        self.gm.step(1 / 30)
        self.assertIn('satellite', boarding_reason(self.st, attacker, satellite))

    def test_satellite_search_skips_blocked_first_slot(self):
        for obstruction in ('station', 'pending_station', 'pending_satellite'):
            with self.subTest(obstruction=obstruction):
                self.setUp()
                self.planet.colonized_by = 0
                slot0 = self.gm.construction.satellite_site(self.planet, 'defense_satellite', 0)
                slot1 = self.gm.construction.satellite_site(self.planet, 'defense_satellite', 1)
                if obstruction == 'station':
                    self.gm.factory.spawn_station('sensor_station', 0, slot0)
                else:
                    constructor = next(e for e in self.st.entities.values()
                                       if e.owner == 0 and e.data_id == 'imperial_constructor')
                    constructor.build_queue.append(dict(
                        kind='station' if obstruction == 'pending_station' else 'satellite',
                        item='sensor_station' if obstruction == 'pending_station' else 'attack_satellite',
                        time_left=1000., total=1000., status='paid', pos=slot0.to_dict(precise=True)))
                before = self.st.players[0].credits
                self.st.queue_command(PlayerCommand('build_satellite', 0,
                    target_id=self.planet.id, station_kind='defense_satellite'))
                self.gm.step(1 / 30)
                self.assertEqual(len(self.planet.build_queue), 1)
                work = self.planet.build_queue[0]
                self.assertEqual(work['slot'], 1)
                self.assertEqual(work['pos'], slot1.to_dict(precise=True))
                self.assertAlmostEqual(self.st.players[0].credits,
                    before - self.gm.factory.station_build_cost('defense_satellite')['credits']
                    + self.st.players[0].income_frame['credits'] / 30)
                # The next intent reserves the next legal slot, not the paid site.
                self.assertTrue(self.gm.construction.start_satellite(self.planet.id, 'attack_satellite', 0))
                self.assertEqual([w['slot'] for w in self.planet.build_queue], [1, 2])

    def test_owned_planet_builds_paid_satellites_with_shared_reserved_cap(self):
        self.planet.colonized_by = 0
        p = self.st.players[0]
        p.credits = p.materials = p.energy = p.crew = 100000
        before = p.credits
        for i in range(7):
            self.st.queue_command(PlayerCommand('build_satellite', 0, target_id=self.planet.id,
                station_kind='defense_satellite' if i % 2 == 0 else 'attack_satellite'))
        self.gm.step(1 / 30)
        self.assertEqual(len(self.planet.build_queue), 6)
        self.assertLess(p.credits, before - 5000)
        run_for(self.gm, 140)
        satellites = [e for e in self.st.entities.values() if e.alive and getattr(e, 'planet_id', None) == self.planet.id]
        self.assertEqual(len(satellites), 6)
        self.assertEqual({e.data_id for e in satellites}, {'defense_satellite', 'attack_satellite'})
        self.assertTrue(all(e.owner == 0 and e.is_station for e in satellites))
        for a in satellites:
            self.assertGreater(a.pos.dist(self.planet.pos), self.planet.radius + a.radius + 100)
            for b in satellites:
                if a is not b:
                    self.assertGreater(a.pos.dist(b.pos), (a.radius + b.radius) * 1.6)

    def test_colony_ship_only_command_and_never_station_constructor(self):
        from game.data.store import DataStore
        ds = DataStore.get()
        yard = next(e for e in self.st.entities.values() if e.owner == 0 and e.data_id == 'shipyard')
        ds.stations['shipyard'].builds_ships = ['imperial_colonizer']
        ds.ships['imperial_colonizer'].can_build_stations = ['sensor_station']
        self.assertEqual(self.gm.construction.start_ship(yard.id, self.ship.data_id, 0), 0)
        self.assertFalse(self.gm.construction.start_station(self.ship.id, 'sensor_station', self.ship.pos.copy(), 0))
        command = next(e for e in self.st.entities.values() if e.owner == 0 and e.data_id == 'command_station')
        self.assertEqual(self.gm.construction.start_ship(command.id, self.ship.data_id, 0), 1)

    def test_timer_resets_after_leaving_range_not_damage(self):
        self.order()
        run_for(self.gm, 6)
        left = self.ship.build_queue[0]['time_left']
        self.ship.hull -= 20
        self.gm.step(1 / 30)
        self.assertLess(self.ship.build_queue[0]['time_left'], left)
        self.ship.pos = self.planet.pos + Vec3(0, 0, self.planet.radius + 1000)
        self.gm.step(1 / 30)
        self.assertEqual(self.ship.build_queue[0]['time_left'], 15)
        self.ship.pos = self.planet.pos + Vec3(0, 0, self.planet.radius + 300)
        run_for(self.gm, 10)
        self.assertIsNone(self.planet.colonized_by)
        run_for(self.gm, 6)
        self.assertEqual(self.planet.colonized_by, 0)

    def test_capture_revalidates_owner_and_competing_ship_survives(self):
        self.planet.colonized_by = 1
        other = self.gm.factory.spawn_ship('imperial_colonizer', 0, self.ship.pos + Vec3(150, 0, 0))
        self.st.queue_command(PlayerCommand('colonize', 0, unit_ids=(self.ship.id, other.id), target_id=self.planet.id))
        run_for(self.gm, 16)
        self.assertEqual(self.planet.colonized_by, 0)
        self.assertFalse(self.ship.alive)
        self.assertTrue(other.alive)
        self.assertEqual(other.build_queue, [])

    def test_gas_and_terrain_are_ineligible(self):
        for planet in self.st.entities.values():
            if planet.is_planet and planet.data_id in ('gas_giant', 'asteroid_field'):
                self.assertFalse(self.gm.construction.start_colonize(self.ship.id, planet.id, 0), planet.data_id)
        self.assertEqual(self.ship.build_queue, [])

    def test_travel_has_no_fee_and_new_order_interrupts_timer(self):
        self.ship.pos = self.planet.pos + Vec3(0, 0, self.planet.radius + 900)
        self.st.players[0].credits = self.st.players[0].materials = self.st.players[0].energy = self.st.players[0].crew = 0
        self.order()
        run_for(self.gm, 11)  # includes the colony hull's 180-degree approach turn
        self.assertEqual(self.ship.build_queue[0]['status'], 'paid')
        self.assertLess(self.ship.build_queue[0]['time_left'], 15)
        self.st.queue_command(PlayerCommand('stop', 0, unit_ids=(self.ship.id,)))
        self.gm.step(1 / 30)
        self.assertEqual(self.ship.build_queue, [])
        run_for(self.gm, 17)
        self.assertIsNone(self.planet.colonized_by)
        self.assertTrue(self.ship.alive)

    def test_colonization_has_no_additional_fee_and_consumes_only_on_success(self):
        self.st.players[0].credits = self.st.players[0].materials = self.st.players[0].energy = self.st.players[0].crew = 0
        self.order()
        self.assertEqual(len(self.ship.build_queue), 1)
        self.assertTrue(self.ship.alive)
        run_for(self.gm, 14)
        self.assertIsNone(self.planet.colonized_by)
        run_for(self.gm, 2)
        self.assertEqual(self.planet.colonized_by, 0)
        self.assertFalse(self.ship.alive)
        self.assertFalse(self.st.game_over)


if __name__ == '__main__':
    unittest.main()
