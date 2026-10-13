"""Issue #79: actual hull damage costs operating crew, through manager ticks."""
import json
import unittest
from helpers import make_game
from game.core.vectors import Vec3
from game.core.state import GameState
from game.core.manager import GameManager
from game.core.commands import AttackCommand


class TestCrewDamage(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.target = self.gm.factory.spawn_ship('imperial_cruiser', 1, Vec3(0, 0, 500))
        self.target.crew = self.target.max_crew = 20
        self.target.shields = dict.fromkeys(self.target.shields, 0.0)
        self.target.max_shield_quad = 0
        self.target.sensor_range = 0
        self.attacker = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3())
        self.attacker.order_type = 'hold'
        self.attacker.weapon_cooldowns = dict.fromkeys(range(10), 100.0)
        self.target.weapon_cooldowns = dict.fromkeys(range(10), 100.0)
        self.st.grid.rebuild(self.st.entities)

    def hit(self, amount, **kwargs):
        self.st.damage_queue.append(dict(target=self.target, damage=amount,
                                        shield_mult=1, armor_mult=1, system_mult=0,
                                        attacker=self.attacker, **kwargs))
        self.gm.step(1 / 30)

    def test_actual_unshielded_hull_damage_costs_one_crew_per_ten(self):
        control = GameManager(GameState.from_dict(json.loads(json.dumps(self.st.to_dict(precise=True)))))
        control.step(1 / 30)
        self.hit(25)
        self.assertEqual(self.target.crew, 18)
        self.assertEqual(self.st.players[1].crew, control.state.players[1].crew)
        self.assertTrue(self.target.alive)


    def test_abandonment_clears_previous_explicit_attack_immediately(self):
        self.target.crew = 1
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        self.gm.commands.consume()
        # Simulate the damaging hit arriving after weapon launch this tick.
        self.hit(10)
        self.assertEqual(self.target.crew, 0)
        self.assertTrue(self.target.alive)
        self.assertEqual(self.target.owner, 1)
        self.assertIsNone(self.attacker.current_target)
        self.assertIsNone(self.attacker.order_target_id)
        self.assertEqual(self.attacker.order_type, 'idle')
        self.assertEqual(self.target.order_type, 'idle')
        self.assertEqual(self.target.total_shield(), 0)
        self.assertIsNone(self.gm.weapons.find_target(self.attacker, 1000))


    def test_new_human_attack_can_destroy_already_abandoned_enemy(self):
        self.target.crew = 0
        self.target.hull = 12
        self.attacker.weapon_cooldowns.clear()
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        for _ in range(180):
            self.gm.step(1 / 30)
            if self.st.entity(self.target.id) is None:
                break
        self.assertIsNone(self.st.entity(self.target.id))


    def test_fractional_damage_and_explicit_permission_restore_exactly(self):
        self.hit(3.123456789123)
        self.target.crew = 0
        self.attacker.weapon_cooldowns.clear()
        hull = self.target.hull
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        self.gm.commands.consume()
        snapshot = json.loads(json.dumps(self.st.to_dict(precise=True)))
        restored = GameManager(GameState.from_dict(snapshot))
        self.assertEqual(restored.state.entity(self.target.id).crew_damage_accumulator,
                         self.target.crew_damage_accumulator)
        self.assertEqual(restored.state.entity(self.attacker.id).abandoned_attack_target,
                         self.target.id)
        self.assertEqual(json.loads(json.dumps(restored.state.to_dict(precise=True))), snapshot)
        for _ in range(40):
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(json.loads(json.dumps(restored.state.to_dict(precise=True))),
                             json.loads(json.dumps(self.st.to_dict(precise=True))))
        self.assertLess(self.target.hull, hull)  # actual in-flight combat, not an idle save fixture

    def test_projection_without_runtime_retains_damage_fraction_and_permission(self):
        self.target.crew_damage_accumulator = 9.123456789123
        self.attacker.order_type = 'attack'
        self.attacker.order_target_id = self.target.id
        self.attacker.abandoned_attack_target = self.target.id
        snapshot = json.loads(json.dumps(self.st.to_dict(precise=True)))
        snapshot.pop('runtime_state')
        restored = GameState.from_dict(snapshot)
        self.assertEqual(restored.entity(self.target.id).crew_damage_accumulator, 9.123456789123)
        self.assertEqual(restored.entity(self.attacker.id).abandoned_attack_target, self.target.id)

    def test_damage_fraction_and_permission_change_replay_checksum(self):
        from game.net.replay import state_checksum
        before = state_checksum(self.st)
        self.target.crew_damage_accumulator = .123456789
        self.assertNotEqual(state_checksum(self.st), before)
        before = state_checksum(self.st)
        self.attacker.abandoned_attack_target = self.target.id
        self.assertNotEqual(state_checksum(self.st), before)


    def test_squadron_and_ai_do_not_reacquire_abandoned_hardware(self):
        from game.ai.ai import AIPlayer
        self.target.crew = 0
        corvette = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3(0, 0, 100))
        constructor = self.gm.factory.spawn_ship('imperial_constructor', 0, Vec3(0, 0, 100))
        squad = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3(100, 0, 100))
        self.st.grid.rebuild(self.st.entities)
        self.gm.squadrons._squadron_behavior(squad)
        self.assertIsNone(squad.current_target)
        ai = AIPlayer(self.st, 0)
        self.st.tick = 3  # authoritative tactical cadence for player zero
        ai.tactical_tick(1 / 30)
        self.assertIsNone(corvette.current_target)
        self.assertIsNone(corvette.order_target_id)
        self.assertEqual(constructor.order_type, 'idle')


    def test_boarding_casualties_clear_other_attackers_before_capture(self):
        source = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3(0, 0, 400))
        self.target.crew = 1
        self.assertTrue(self.gm.boarding.launch(source, self.target))
        craft = self.st.entity(source.boarding_party_id)
        craft.pos = self.target.pos.copy()
        craft.boarding['phase'] = 'control'
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        self.gm.commands.consume()
        self.attacker.weapon_cooldowns = dict.fromkeys(range(10), 100)
        self.gm.ds.rules['boarding']['combat_losses_per_second'] = 100
        self.gm.step(1 / 30)
        self.assertEqual(self.target.crew, 0)
        self.assertEqual(self.target.owner, 1)
        self.assertIsNone(self.attacker.order_target_id)
        self.assertIsNone(self.attacker.current_target)
        self.assertEqual(craft.boarding['phase'], 'control')


    def test_old_canonical_save_migrates_missing_new_fields_only(self):
        snapshot = json.loads(json.dumps(self.st.to_dict(precise=True)))
        def strip(node):
            if isinstance(node, list):
                if len(node) == 3 and node[:2] == ['object', 'Entity']:
                    node[2].pop('crew_damage_accumulator')
                    node[2].pop('abandoned_attack_target')
                for child in node:
                    strip(child)
            elif isinstance(node, dict):
                for child in node.values():
                    strip(child)
        strip(snapshot['runtime_state'])
        restored = GameManager(GameState.from_dict(snapshot))
        self.assertEqual(restored.state.entity(self.target.id).crew_damage_accumulator, 0)
        self.assertIsNone(restored.state.entity(self.attacker.id).abandoned_attack_target)
        # Untrusted playback must not silently migrate the old typed graph.
        with self.assertRaises(ValueError):
            GameManager(GameState.from_dict(snapshot, sanitize_save=False))


    def test_excess_damage_cannot_bank_whole_casualties_for_future_recruits(self):
        self.target.crew = 1
        self.hit(25)
        self.assertEqual(self.target.crew, 0)
        self.assertEqual(self.target.crew_damage_accumulator, 5)
        self.target.crew = 10  # existing recovery may restore personnel later
        self.hit(4)
        self.assertEqual(self.target.crew, 10)


    def test_invalid_casualty_tuning_rejected_at_catalogue_load_validation(self):
        cfg = self.gm.ds.rules['combat']
        for value in (-1, True, '10', float('nan'), float('inf')):
            with self.subTest(value=value):
                cfg['hull_damage_per_crew'] = value
                with self.assertRaisesRegex(ValueError, 'hull_damage_per_crew'):
                    self.gm.ds._validate()
        cfg['hull_damage_per_crew'] = 10


    def test_ai_strategic_attack_and_threat_ignore_derelicts(self):
        from game.ai.ai import AIPlayer
        ai = AIPlayer(self.st, 0)
        home = ai.home_station()
        self.target.pos = home.pos + Vec3(500, 0, 0)
        self.target.crew = 0
        for i in range(4):
            self.gm.factory.spawn_ship('imperial_corvette', 0, home.pos + Vec3(0, 0, 100 * i))
        self.st.grid.rebuild(self.st.entities)
        self.assertFalse(ai._under_threat())
        ai._decide_attack()
        self.assertFalse(any(c.type == 'fleet_create' for c in self.st.command_queue))


    def test_station_casualties_and_abandonment_clear_incoming_orders(self):
        self.target.crew = 0
        self.target = self.gm.factory.spawn_station('defense_platform', 1, Vec3(0, 0, 500))
        self.target.crew = 1
        self.target.max_shield_quad = 0
        self.target.shields = dict.fromkeys(self.target.shields, 0.0)
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        self.gm.commands.consume()
        self.hit(10)
        self.assertEqual(self.target.crew, 0)
        self.assertEqual(self.target.owner, 1)
        self.assertTrue(self.target.alive)
        self.assertIsNone(self.attacker.current_target)
        self.assertIsNone(self.attacker.order_target_id)

    def test_shields_protect_crew_and_only_overflow_costs_personnel(self):
        self.target.max_shield_quad = 100
        self.target.shields['front'] = 25
        self.target.shields['rear'] = 100
        hull = self.target.hull
        self.hit(20)
        self.assertEqual(self.target.crew, 20)
        self.assertEqual(self.target.hull, hull)
        self.assertEqual(self.target.crew_damage_accumulator, 0)
        self.hit(20)
        self.assertEqual(self.target.crew, 19)
        self.assertEqual(self.target.hull, hull - 15)
        self.assertEqual(self.target.crew_damage_accumulator, 5)
        self.assertEqual(self.target.shields['rear'], 100)

    def test_post_armor_capped_hull_loss_not_raw_damage_costs_crew(self):
        self.st.damage_queue.append(dict(target=self.target, damage=30, shield_mult=1,
                                        armor_mult=.5, system_mult=0, attacker=self.attacker))
        self.gm.step(1 / 30)
        self.assertEqual(self.target.crew, 19)
        self.assertEqual(self.target.crew_damage_accumulator, 5)
        self.target.hull = 3
        self.hit(1000)
        self.assertEqual(self.target.crew, 19)  # only three actual HP left to lose
        self.assertFalse(self.target.alive)

    def test_many_small_hits_and_partial_casualty_restore_continue_exactly(self):
        self.target.crew_cargo = 7
        for _ in range(9):
            self.hit(1)
        self.assertEqual(self.target.crew, 20)
        snapshot = json.loads(json.dumps(self.st.to_dict(precise=True)))
        restored = GameManager(GameState.from_dict(snapshot))
        for damage in (1, .123456789123, 3.987654321987, 8.5, 7.5):
            self.st.damage_queue.append(dict(target=self.target, damage=damage, shield_mult=1,
                                            armor_mult=1, system_mult=0, attacker=self.attacker))
            restored.state.damage_queue.append(dict(target=restored.state.entity(self.target.id),
                damage=damage, shield_mult=1, armor_mult=1, system_mult=0,
                attacker=restored.state.entity(self.attacker.id)))
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(json.loads(json.dumps(restored.state.to_dict(precise=True))),
                             json.loads(json.dumps(self.st.to_dict(precise=True))))
        self.assertEqual(self.target.crew, 17)
        self.assertEqual(self.target.crew_cargo, 7)  # operating crew only, not passengers

    def test_surface_generator_absorption_protects_building_crew(self):
        planet = next(e for e in self.st.entities.values() if e.is_planet and e.data_id == 'temperate')
        planet.colonized_by = 1
        generator = self.gm.factory.spawn_station('planet_shield_generator', 1, planet.pos.copy())
        generator.planet_id, generator.planet_building_slot = planet.id, 0
        generator.shields = dict.fromkeys(generator.shields, 0.0)
        generator.shields['front'] = 25
        self.target.crew = 0
        self.target = self.gm.factory.spawn_station('planet_extractor', 1, planet.pos.copy())
        self.target.planet_id, self.target.planet_building_slot = planet.id, 1
        self.target.crew = self.target.max_crew = 20
        self.target.max_shield_quad = 0
        self.target.shields = dict.fromkeys(self.target.shields, 0.0)
        self.hit(20)
        self.assertEqual(self.target.crew, 20)
        self.hit(20)
        self.assertEqual(self.target.crew, 19)
        self.assertEqual(self.target.crew_damage_accumulator, 5)

    def test_tuning_can_change_threshold_or_disable_combat_casualties(self):
        self.gm.ds.rules['combat']['hull_damage_per_crew'] = 5
        self.hit(10)
        self.assertEqual(self.target.crew, 18)
        self.gm.ds.rules['combat']['hull_damage_per_crew'] = 0
        self.hit(100)
        self.assertEqual(self.target.crew, 18)

    def test_reattack_rejects_ai_own_allied_and_hidden_targets(self):
        self.target.crew = 0
        self.st.players[0].is_ai = True
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        self.gm.commands.consume()
        self.assertIsNone(self.attacker.abandoned_attack_target)
        self.assertIsNone(self.attacker.order_target_id)
        self.st.players[0].is_ai = False
        self.target.owner = 0
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        self.gm.commands.consume()
        self.assertIsNone(self.attacker.order_target_id)
        self.target.owner = 1
        self.st.players[1].team = self.st.players[0].team
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        self.gm.commands.consume()
        self.assertIsNone(self.attacker.order_target_id)
        self.st.players[1].team = 1
        self.target.pos = Vec3(12000, 0, 12000)
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        self.gm.commands.consume()
        self.assertIsNone(self.attacker.order_target_id)

    def test_loss_of_visibility_or_new_order_revokes_reattack_permission(self):
        from game.core.commands import StopCommand
        self.target.crew = 0
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        self.gm.commands.consume()
        self.assertEqual(self.attacker.abandoned_attack_target, self.target.id)
        self.st.queue_command(StopCommand(0, [self.attacker.id]))
        self.gm.step(1 / 30)
        self.assertIsNone(self.attacker.abandoned_attack_target)
        self.assertIsNone(self.attacker.current_target)
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        self.gm.commands.consume()
        self.target.pos = Vec3(12000, 0, 12000)
        self.gm.step(1 / 30)
        self.assertIsNone(self.attacker.abandoned_attack_target)
        self.assertIsNone(self.attacker.order_target_id)

    def test_life_support_abandonment_revokes_prior_explicit_attack(self):
        self.target.crew = 1
        self.target.systems['life_support'].hp = 0
        self.target.crew_loss_accumulator = .99
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        self.gm.commands.consume()
        self.gm.step(1 / 30)
        self.assertEqual(self.target.crew, 0)
        self.assertIsNone(self.attacker.order_target_id)
        self.assertIsNone(self.attacker.current_target)


    def test_ballistic_projectile_survives_target_abandonment(self):
        self.target.crew = 1
        weapon = self.gm.ds.resolve_weapon('turbolaser')
        self.gm.weapons._launch_projectiles(self.attacker, self.target, weapon, 1)
        self.assertEqual(len(self.st.projectiles), 1)
        self.hit(10)
        self.assertEqual(self.target.crew, 0)
        hull = self.target.hull
        for _ in range(60):
            self.gm.step(1 / 30)
        self.assertLess(self.target.hull, hull)
        self.assertEqual(self.st.projectiles, {})
        self.assertIsNone(self.attacker.current_target)

    def test_fleet_squadron_and_station_defaults_do_not_attack_derelict(self):
        from game.core.commands import FleetCreateCommand
        squad = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3(100, 0, 100))
        station = self.gm.factory.spawn_station('defense_platform', 0, Vec3(-200, 0, 0))
        self.st.queue_command(FleetCreateCommand(0, [self.attacker.id, squad.id], 'Casualty test'))
        self.st.queue_command(AttackCommand(0, [self.attacker.id, squad.id], self.target.id))
        self.gm.commands.consume()
        self.target.crew = 1
        squad.weapon_cooldowns = dict.fromkeys(range(10), 100)
        station.weapon_cooldowns = dict.fromkeys(range(10), 100)
        self.hit(10)
        for _ in range(30):
            self.gm.step(1 / 30)
        for e in (self.attacker, squad, station):
            self.assertNotEqual(e.current_target, self.target.id)
            self.assertNotEqual(e.order_target_id, self.target.id)
        self.assertEqual(self.st.projectiles, {})

    def test_human_reattack_can_destroy_abandoned_station(self):
        self.target.crew = 0
        self.target = self.gm.factory.spawn_station('defense_platform', 1, Vec3(0, 0, 500))
        self.target.crew = 0
        self.target.hull = 12
        self.attacker.weapon_cooldowns.clear()
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        for _ in range(180):
            self.gm.step(1 / 30)
            if self.st.entity(self.target.id) is None:
                break
        self.assertIsNone(self.st.entity(self.target.id))


    def test_restored_stale_ai_permit_does_not_allow_derelict_attack(self):
        self.target.crew = 0
        self.st.players[0].is_ai = True
        self.attacker.order_type = 'attack'
        self.attacker.order_target_id = self.attacker.current_target = self.target.id
        self.attacker.abandoned_attack_target = self.target.id
        self.gm.step(1 / 30)
        self.assertIsNone(self.attacker.current_target)
        self.assertIsNone(self.attacker.order_target_id)
        self.assertIsNone(self.attacker.abandoned_attack_target)


    def test_pending_beam_intent_stops_at_abandonment_but_explicit_reattack_works(self):
        beam = next(w for w in self.gm.ds.weapons.values() if w.is_beam)
        self.target.crew = 1
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        self.gm.commands.consume()
        hull = self.target.hull
        for damage, weapon in ((10, None), (20, beam)):
            self.st.damage_queue.append(dict(target=self.target, damage=damage, shield_mult=1,
                armor_mult=1, system_mult=0, attacker=self.attacker, weapon=weapon))
        self.gm.step(1 / 30)
        self.assertEqual(self.target.crew, 0)
        self.assertEqual(self.target.hull, hull - 10)
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        self.gm.commands.consume()
        self.hit(20, weapon=beam)
        self.assertEqual(self.target.hull, hull - 30)


    def test_abandoned_shooter_cannot_resolve_a_pending_beam(self):
        beam = next(w for w in self.gm.ds.weapons.values() if w.is_beam)
        self.attacker.crew = 1
        self.attacker.max_shield_quad = 0
        self.attacker.shields = dict.fromkeys(self.attacker.shields, 0.0)
        hull = self.target.hull
        self.st.damage_queue.append(dict(target=self.attacker, damage=10, shield_mult=1,
            armor_mult=1, system_mult=0, attacker_id=1))
        self.st.damage_queue.append(dict(target=self.target, damage=20, shield_mult=1,
            armor_mult=1, system_mult=0, attacker=self.attacker, weapon=beam))
        self.gm.step(1 / 30)
        self.assertEqual(self.attacker.crew, 0)
        self.assertEqual(self.target.hull, hull)


    def test_precise_restored_abandonment_then_new_reattack_continuation(self):
        self.hit(9.123456789123)
        self.target.crew = 1
        self.target.hull = 100
        self.st.queue_command(AttackCommand(0, [self.attacker.id], self.target.id))
        self.gm.commands.consume()
        restored = GameManager(GameState.from_dict(json.loads(json.dumps(self.st.to_dict(precise=True)))))
        other_target = restored.state.entity(self.target.id)
        other_attacker = restored.state.entity(self.attacker.id)
        for gm, target, source in ((self.gm, self.target, self.attacker),
                                   (restored, other_target, other_attacker)):
            gm.state.damage_queue.append(dict(target=target, damage=1, shield_mult=1,
                armor_mult=1, system_mult=0, attacker=source))
            gm.step(1 / 30)
            self.assertEqual(target.crew, 0)
            self.assertIsNone(source.order_target_id)
            gm.state.queue_command(AttackCommand(0, [source.id], target.id))
            source.weapon_cooldowns.clear()
        for _ in range(90):
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(json.loads(json.dumps(restored.state.to_dict(precise=True))),
                             json.loads(json.dumps(self.st.to_dict(precise=True))))
        self.assertIsNone(self.st.entity(self.target.id))
        self.assertIsNone(restored.state.entity(self.target.id))


if __name__ == '__main__':
    unittest.main()
