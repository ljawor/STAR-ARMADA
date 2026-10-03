"""Combat must use current team sensor contact, never exploration history."""
import unittest

from helpers import make_game
from game.core.commands import AttackCommand
from game.core.vectors import Vec3


class SensorCombatTests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.st.entities.clear()
        self.ship = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3())
        self.enemy = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(0, 0, 500))
        self.st.grid.rebuild(self.st.entities)

    def test_contact_loss_immediately_prevents_firing(self):
        self.ship.sensor_range = 100
        self.ship.current_target = self.enemy.id
        self.gm.weapons.update(1 / 30)
        self.assertIsNone(self.ship.current_target)
        self.assertFalse([p for p in self.st.projectiles.values() if p.owner == 0])
        self.assertFalse([d for d in self.st.damage_queue if d['attacker'].owner == 0])

    def test_forged_hidden_attack_is_rejected(self):
        self.ship.sensor_range = 100
        self.gm.commands._apply(AttackCommand(0, [self.ship.id], self.enemy.id))
        self.assertEqual(self.ship.order_type, 'idle')
        self.assertIsNone(self.ship.current_target)
        self.assertIsNone(self.ship.order_target_id)

    def test_hidden_target_does_not_leak_live_chase_position(self):
        self.ship.sensor_range = 100
        self.ship.order_type = 'attack'
        self.ship.order_target_id = self.enemy.id
        self.ship.current_target = self.enemy.id
        self.ship.order_target_pos = self.enemy.pos.copy()
        self.enemy.pos = Vec3(900, 0, 500)
        self.gm.movement.update(1 / 30)
        self.assertIsNone(self.ship.current_target)
        self.assertIsNone(self.ship.order_target_id)
        self.assertIsNone(self.ship.order_target_pos)
        self.assertEqual(self.ship.order_type, 'idle')
        self.assertEqual(self.ship.yaw, 0)

    def test_squadron_does_not_acquire_hidden_enemy(self):
        sq = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())
        sq.sensor_range = 1000
        sq.ability_active['sensor_jammed'] = 10
        self.ship.sensor_range = 100
        self.st.grid.rebuild(self.st.entities)
        self.gm.squadrons.update(.2)
        self.assertIsNone(sq.current_target)
        self.assertIsNone(sq.order_target_id)

    def test_squadron_clears_lost_lock_between_tactical_ticks(self):
        sq = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())
        sq.sensor_range = 100
        self.ship.sensor_range = 100
        sq.order_type = 'attack'
        sq.order_target_id = self.enemy.id
        sq.current_target = self.enemy.id
        self.gm.squadrons.update(.01)
        self.assertIsNone(sq.current_target)
        self.assertIsNone(sq.order_target_id)
        self.assertEqual(sq.order_type, 'idle')

    def test_targeted_ability_rejects_hidden_enemy_without_cost(self):
        self.ship.sensor_range = 100
        energy = self.ship.energy
        result = self.gm.abilities.activate(self.ship, 'tractor_beam', self.enemy.id)
        self.assertFalse(result)
        self.assertEqual(self.ship.energy, energy)
        self.assertNotIn('tractor_slowed', self.enemy.ability_active)
        self.assertNotIn('tractor_beam', self.ship.ability_cooldowns)

    def test_ai_tactical_does_not_choose_hidden_live_enemy(self):
        from game.ai.ai import AIPlayer
        self.ship.sensor_range = 1000
        self.ship.ability_active['sensor_jammed'] = 10
        self.st.tick = 3
        AIPlayer(self.st, 0).tactical_tick(.2)
        self.assertIsNone(self.ship.current_target)
        self.assertIsNone(self.ship.order_target_id)

    def test_ai_strategic_scouting_ignores_hidden_enemy_position(self):
        from game.ai.ai import AIPlayer
        from game.core.world import Fleet
        home = self.gm.factory.spawn_station('command_station', 0, Vec3(-11000, 0, 800))
        home.sensor_range = 100
        self.ship.sensor_range = 100
        combat = [self.ship] + [self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3()) for _ in range(3)]
        for e in combat:
            e.sensor_range = 100
        fleet = Fleet(1, 0, 'Strike Fleet')
        fleet.member_ids = {e.id for e in combat}
        self.st.fleets[1] = fleet
        ai = AIPlayer(self.st, 0)
        ai.attack_fleet_id = 1
        ai._decide_attack()
        first = [(c.type, c.target_id, c.target_pos) for c in self.st.command_queue]
        self.assertTrue(first, 'AI must still scout when no contacts exist')
        self.st.command_queue.clear()
        self.enemy.pos = Vec3(10000, 0, -2000)
        ai._decide_attack()
        second = [(c.type, c.target_id, c.target_pos) for c in self.st.command_queue]
        self.assertEqual(first, second)
        self.assertTrue(all(c[0] == 'attack_move' and c[1] is None for c in first))

    def test_ai_hidden_enemy_does_not_trigger_defense(self):
        from game.ai.ai import AIPlayer
        home = self.gm.factory.spawn_station('command_station', 0, Vec3())
        home.sensor_range = self.ship.sensor_range = 100
        ai = AIPlayer(self.st, 0)
        self.assertFalse(ai._under_threat())

    def test_ai_hidden_enemy_does_not_prompt_defense_build(self):
        from game.ai.ai import AIPlayer
        home = self.gm.factory.spawn_station('command_station', 0, Vec3())
        home.sensor_range = self.ship.sensor_range = 100
        self.gm.factory.spawn_ship('imperial_colonizer', 0, Vec3()).sensor_range = 100
        self.st.players[0].credits = 1000
        AIPlayer(self.st, 0)._ensure_defense(home)
        self.assertFalse(self.st.command_queue)

    def test_ai_colony_selection_does_not_read_hidden_station_position(self):
        from game.ai.ai import AIPlayer
        home = self.gm.factory.spawn_station('command_station', 0, Vec3())
        home.sensor_range = self.ship.sensor_range = 100
        planet = self.gm.factory.spawn_planet({'id': 'colony', 'type': 'temperate', 'pos': [2000, 0, 0], 'radius': 100})
        self.gm.factory.spawn_station('command_station', 1, Vec3(2100, 0, 0))
        self.assertIs(AIPlayer(self.st, 0)._pick_colony_target(home), planet)

    def test_ai_colony_selection_ignores_undetected_planet_ownership(self):
        from game.ai.ai import AIPlayer
        home = self.gm.factory.spawn_station('command_station', 0, Vec3())
        home.sensor_range = self.ship.sensor_range = 100
        near = self.gm.factory.spawn_planet({'id': 'near', 'type': 'temperate', 'pos': [2000, 0, 0], 'radius': 100})
        far = self.gm.factory.spawn_planet({'id': 'far', 'type': 'temperate', 'pos': [6000, 0, 0], 'radius': 100})
        colonizer = self.gm.factory.spawn_ship('imperial_colonizer', 0, Vec3())
        colonizer.sensor_range = 100
        self.st.players[0].credits = 10000
        ai = AIPlayer(self.st, 0)
        for owner, colonized_by in ((-1, None), (1, 1), (0, 0), (1, None)):
            with self.subTest(owner=owner, colonized_by=colonized_by):
                near.owner, near.colonized_by = owner, colonized_by
                self.assertFalse(self.st.can_see(0, near.id))
                self.assertFalse(self.st.can_see(0, far.id))
                self.assertIsNone(self.st.known_entity(0, near.id))
                self.assertIs(ai._pick_colony_target(home), near)
                self.st.command_queue.clear()
                ai._maybe_expand(home)
                self.assertEqual([(c.type, c.target_id) for c in self.st.command_queue],
                                 [('colonize', near.id)])

    def test_ai_colony_selection_uses_stale_ownership_until_reacquisition(self):
        from game.ai.ai import AIPlayer
        home = self.gm.factory.spawn_station('command_station', 0, Vec3())
        self.ship.sensor_range = 100
        near = self.gm.factory.spawn_planet({'id': 'near', 'type': 'temperate', 'pos': [2000, 0, 0], 'radius': 100})
        far = self.gm.factory.spawn_planet({'id': 'far', 'type': 'temperate', 'pos': [6000, 0, 0], 'radius': 100})
        ai = AIPlayer(self.st, 0)
        for observed, hidden in ((None, 1), (1, None)):
            with self.subTest(observed=observed, hidden=hidden):
                near.owner = -1 if observed is None else observed
                near.colonized_by = observed
                home.sensor_range = 2500
                self.gm.visibility.update()
                before = ai._pick_colony_target(home)
                self.assertIs(before, near if observed is None else far)
                home.sensor_range = 100
                near.owner = -1 if hidden is None else hidden
                near.colonized_by = hidden
                self.gm.visibility.update()
                self.assertFalse(self.st.can_see(0, near.id))
                remembered = self.st.known_entity(0, near.id)
                self.assertIsNotNone(remembered)
                assert remembered is not None
                self.assertEqual(remembered.colonized_by, observed)
                self.assertIs(ai._pick_colony_target(home), before)
                home.sensor_range = 2500
                self.assertTrue(self.st.can_see(0, near.id))
                self.assertIs(ai._pick_colony_target(home), near if hidden is None else far)
                self.gm.visibility.update()
                home.sensor_range = 100
                self.assertIs(ai._pick_colony_target(home), near if hidden is None else far)

    def test_ai_colony_selection_respects_visible_ownership(self):
        from game.ai.ai import AIPlayer
        home = self.gm.factory.spawn_station('command_station', 0, Vec3())
        home.sensor_range = 2500
        near = self.gm.factory.spawn_planet({'id': 'near', 'type': 'temperate', 'pos': [2000, 0, 0], 'radius': 100})
        far = self.gm.factory.spawn_planet({'id': 'far', 'type': 'temperate', 'pos': [6000, 0, 0], 'radius': 100})
        ai = AIPlayer(self.st, 0)
        for owner in (1, 0, -1):
            with self.subTest(owner=owner):
                near.owner = owner
                near.colonized_by = None if owner == -1 else owner
                self.assertTrue(self.st.can_see(0, near.id))
                self.assertIs(self.st.known_entity(0, near.id), near)
                self.assertIs(ai._pick_colony_target(home), near if owner == -1 else far)

    def test_ai_expansion_enemy_station_proximity_is_sensor_gated(self):
        from game.ai.ai import AIPlayer
        home = self.gm.factory.spawn_station('command_station', 0, Vec3())
        home.sensor_range = self.ship.sensor_range = 100
        near = self.gm.factory.spawn_planet({'id': 'near', 'type': 'temperate', 'pos': [2000, 0, 0], 'radius': 100})
        far = self.gm.factory.spawn_planet({'id': 'far', 'type': 'temperate', 'pos': [7000, 0, 0], 'radius': 100})
        station = self.gm.factory.spawn_station('command_station', 1, Vec3(2100, 0, 0))
        colonizer = self.gm.factory.spawn_ship('imperial_colonizer', 0, Vec3())
        colonizer.sensor_range = 100
        self.st.players[0].credits = 10000
        ai = AIPlayer(self.st, 0)
        for sensor_range, station_pos, expected in (
                (100, Vec3(2100, 0, 0), near),
                (100, Vec3(9000, 0, 0), near),
                (2500, Vec3(2100, 0, 0), far),
                (100, Vec3(2100, 0, 0), near)):
            with self.subTest(sensor_range=sensor_range, station_pos=station_pos):
                home.sensor_range = sensor_range
                station.pos = station_pos
                self.gm.visibility.update()
                self.assertEqual(self.st.can_see(0, station.id), sensor_range == 2500)
                self.assertIs(ai._pick_colony_target(home), expected)
                self.st.command_queue.clear()
                ai._maybe_expand(home)
                self.assertEqual([(c.type, c.target_id) for c in self.st.command_queue],
                                 [('colonize', expected.id)])

    def test_ai_constructor_does_not_flee_hidden_enemy(self):
        from game.ai.ai import AIPlayer
        home = self.gm.factory.spawn_station('command_station', 0, Vec3(-2000, 0, 0))
        home.sensor_range = self.ship.sensor_range = 100
        builder = self.gm.factory.spawn_ship('imperial_constructor', 0, Vec3())
        builder.sensor_range = 100
        self.st.grid.rebuild(self.st.entities)
        self.st.tick = 3
        AIPlayer(self.st, 0).tactical_tick(.2)
        self.assertEqual(builder.order_type, 'idle')
        self.assertIsNone(builder.order_target_pos)

    def test_direct_launch_rejects_hidden_enemy(self):
        self.ship.sensor_range = 100
        weapon = self.gm.ds.resolve_weapon('laser_cannon')
        self.gm.weapons._launch_projectiles(self.ship, self.enemy, weapon, 1)
        self.assertFalse(self.st.projectiles)

    def test_enemy_just_inside_effective_sensor_range_fires(self):
        self.ship.sensor_range = 501
        self.assertTrue(self.st.can_see(0, self.enemy.id))
        self.gm.weapons._ship_weapons(self.ship, .01)
        self.assertEqual(self.ship.current_target, self.enemy.id)
        self.assertTrue(self.st.projectiles)

    def test_remote_allied_station_detection_permits_fire(self):
        from game.core.state import PlayerState
        self.st.players[2] = PlayerState(id=2, faction='imperial', team=0)
        self.ship.sensor_range = 100
        station = self.gm.factory.spawn_station('sensor_station', 2, Vec3(0, 0, 900))
        station.sensor_range = 450
        self.assertTrue(self.st.can_see(0, self.enemy.id))
        self.gm.weapons._ship_weapons(self.ship, .01)
        self.assertTrue(self.st.projectiles)
        station.alive = False
        self.ship.weapon_cooldowns.clear()
        self.st.projectiles.clear()
        self.gm.weapons._ship_weapons(self.ship, .01)
        self.assertIsNone(self.ship.current_target)
        self.assertFalse(self.st.projectiles)

    def test_jam_loss_immediately_stops_firing(self):
        self.ship.sensor_range = 1000
        self.ship.current_target = self.enemy.id
        self.ship.ability_active['sensor_jammed'] = 10
        self.gm.weapons._ship_weapons(self.ship, .01)
        self.assertIsNone(self.ship.current_target)
        self.assertFalse(self.st.projectiles)

    def test_station_loop_rejects_hidden_contact(self):
        station = self.gm.factory.spawn_station('defense_platform', 0, Vec3())
        station.sensor_range = self.ship.sensor_range = 100
        station.current_target = self.enemy.id
        station.order_type = 'attack'
        station.order_target_id = self.enemy.id
        self.gm.weapons.update(.01)
        self.assertIsNone(station.current_target)
        self.assertIsNone(station.order_target_id)
        self.assertFalse([p for p in self.st.projectiles.values() if p.owner == 0])
        self.assertFalse([d for d in self.st.damage_queue if d['attacker'].owner == 0])

    def test_beam_cannot_fire_at_hidden_enemy(self):
        cruiser = self.gm.factory.spawn_ship('confed_supercapital', 0, Vec3())
        cruiser.sensor_range = self.ship.sensor_range = 100
        cruiser.current_target = self.enemy.id
        self.gm.weapons._ship_weapons(cruiser, .01)
        self.assertFalse(self.st.damage_queue)
        self.assertFalse(self.st.projectiles)
        self.assertIsNone(cruiser.current_target)

    def test_sensor_jam_area_can_hit_hidden_enemy(self):
        self.ship.sensor_range = 100
        self.assertFalse(self.st.can_see(0, self.enemy.id))
        self.assertTrue(self.gm.abilities.activate(self.ship, 'sensor_jam'))
        self.assertGreater(self.enemy.ability_active.get('sensor_jammed', 0), 0)

    def test_missile_remains_ballistic_after_contact_loss(self):
        self.ship.sensor_range = 1000
        weapon = self.gm.ds.resolve_weapon('missile_battery')
        self.gm.weapons._launch_projectiles(self.ship, self.enemy, weapon, 1)
        projectile = next(iter(self.st.projectiles.values()))
        velocity = projectile.vel.copy()
        position = projectile.pos.copy()
        self.ship.sensor_range = 100
        self.enemy.pos = Vec3(500, 0, 500)
        self.st.grid.rebuild(self.st.entities)
        self.gm.projectiles.update(.1)
        self.assertIn(projectile.id, self.st.projectiles)
        self.assertEqual(projectile.vel, velocity)
        self.assertEqual(projectile.pos, position + velocity * .1)

    def test_fired_unguided_projectile_can_hit_hidden_enemy(self):
        from game.core.world import Projectile
        self.ship.sensor_range = 100
        p = Projectile(1, 0, 'laser_cannon', self.enemy.pos - Vec3(0, 0, 10),
                       Vec3(0, 0, 100), self.enemy.id, 14, 1, 1, 1, 2)
        self.st.projectiles[1] = p
        self.gm.projectiles.update(.1)
        self.assertEqual(self.st.damage_queue[0]['target'], self.enemy)
        self.assertNotIn(1, self.st.projectiles)

    def test_detected_squadron_target_is_acquired(self):
        sq = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())
        self.st.grid.rebuild(self.st.entities)
        self.gm.squadrons.update(.2)
        self.assertEqual(sq.current_target, self.enemy.id)
        self.assertEqual(sq.order_target_id, self.enemy.id)

    def test_detected_beam_launches_damage(self):
        capital = self.gm.factory.spawn_ship('confed_supercapital', 0, Vec3())
        self.gm.weapons._ship_weapons(capital, .01)
        self.assertTrue(any(d['weapon'].is_beam for d in self.st.damage_queue))

    def test_forged_ability_command_rejects_hidden_lock(self):
        from game.core.commands import PlayerCommand
        self.ship.sensor_range = 100
        energy = self.ship.energy
        self.gm.commands._apply(PlayerCommand('ability', 0, unit_ids=(self.ship.id,),
                                              target_id=self.enemy.id, ability_id='tractor_beam'))
        self.assertEqual(self.ship.energy, energy)
        self.assertNotIn('tractor_slowed', self.enemy.ability_active)

    def test_lost_lock_clears_target_bearing_attack_destination(self):
        self.ship.sensor_range = 100
        self.ship.order_type = 'attack'
        self.ship.current_target = self.enemy.id
        self.ship.order_target_pos = self.enemy.pos.copy()
        self.gm.weapons._ship_weapons(self.ship, .01)
        self.assertEqual(self.ship.order_type, 'idle')
        self.assertIsNone(self.ship.order_target_pos)

    def test_commercial_convoy_route_to_hidden_market_is_not_attack_chase(self):
        market = self.gm.factory.spawn_station('trade_station', 1, Vec3(0, 0, 8000))
        # Commercial routes intentionally connect opposing markets; stopping an
        # existing convoy is not a combat-contact loss and breaks escort missions.
        from game.core.entity import Entity
        convoy = Entity(id=999, kind='ship', owner=0, data_id='trade_convoy', pos=Vec3())
        convoy.is_ship = True
        convoy.order_type = 'move'
        convoy.order_target_id = market.id
        self.st.entities[convoy.id] = convoy
        self.gm.movement.update(.01)
        self.assertEqual(convoy.order_target_id, market.id)
        self.assertEqual(convoy.order_type, 'move')

    def test_ai_keeps_one_active_exploration_scout(self):
        from game.ai.ai import AIPlayer
        home = self.gm.factory.spawn_station('command_station', 0, Vec3(-11000, 0, 800))
        home.sensor_range = self.ship.sensor_range = 100
        scout = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())
        scout.sensor_range = 100
        ai = AIPlayer(self.st, 0)
        ai._decide_attack()
        self.gm.commands.consume()
        self.st.command_queue.clear()
        ai._decide_attack()
        self.assertFalse(self.st.command_queue, 'scouting must not drain every idle defender')


if __name__ == '__main__':
    unittest.main()
