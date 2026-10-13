"""Hyperspace transit phase (#92) and post-arrival shield lockdown (#78).

After charge completes a ship no longer teleports: it travels through
hyperspace for a distance-based duration, invisible on the 3D map but still
tracked (minimap blip path), untargetable and unsinkable, and it arrives with
shields locked down for a fixed window.
"""
import copy
import json
import math
import unittest

from helpers import make_game
from game.core.commands import PlayerCommand
from game.core.vectors import Vec3


class TestJumpTravel(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.rules = self.gm.ds.rules['hyperspace']
        self.ship = next(e for e in self.st.entities.values()
                         if e.owner == 0 and e.is_ship)

    def jump(self, target, ids=None):
        self.st.command_queue.append(PlayerCommand(
            'jump', 0, unit_ids=tuple(ids or [self.ship.id]), target_pos=target))
        self.gm.commands.consume()

    def charge_out(self, e):
        """Run the prep phase out; transit phase begins when this returns."""
        self.gm._update_jumps(e.jump_charge + 1 / 30)

    def snapshot(self):
        return copy.deepcopy((self.st.to_dict(precise=True), self.st.effects,
                              self.st.floating_texts))

    # ------------------------------------------------------------ #92 transit

    def test_charge_end_starts_transit_instead_of_teleport(self):
        target = Vec3(7000, 0, -6000)
        self.jump((target.x, 0.0, target.z))
        origin = self.ship.pos.copy()
        self.charge_out(self.ship)
        self.assertFalse(self.st.is_position_explored(0, target))
        self.assertNotEqual(self.ship.pos, target)
        self.assertTrue(self.ship.jump_travelling)
        self.assertEqual(self.ship.jump_origin, origin)
        self.assertEqual(self.ship.jump_target, target)
        self.assertGreater(self.ship.jump_charge, 0)
        self.assertGreater(self.ship.jump_transit_total,
                           self.ship.jump_charge - 1e-9)

    def test_transit_seconds_follow_distance_with_clamps(self):
        # short hop: clamped to the minimum
        near = self.ship.pos + Vec3(400, 0, 0)
        self.jump((near.x, self.ship.pos.y, near.z))
        self.charge_out(self.ship)
        min_total = self.rules['min_transit_seconds']
        self.assertAlmostEqual(self.ship.jump_transit_total, min_total, places=6)
        self.setUp()
        # long haul: distance / transit speed, below the maximum on this map
        far = Vec3(-11000, 0, 11000)
        self.jump((far.x, 0.0, far.z))
        self.charge_out(self.ship)
        expected = self.ship.jump_origin.dist(far) / self.rules['transit_units_per_second']
        total = self.ship.jump_transit_total
        self.assertTrue(self.rules['min_transit_seconds'] <= total
                        <= self.rules['max_transit_seconds'])
        self.assertAlmostEqual(total, max(self.rules['min_transit_seconds'],
                                          min(self.rules['max_transit_seconds'],
                                              expected)), places=6)

    def test_ship_rides_transit_path_then_exits_exactly_at_target(self):
        target = Vec3(7000, 0, -6000)
        self.jump((target.x, 0.0, target.z))
        origin = self.ship.pos.copy()
        self.charge_out(self.ship)
        total = self.ship.jump_transit_total
        dt = 1 / 30
        seen = []
        for _ in range(int(total / dt) + 2):
            self.gm._update_jumps(dt)
            seen.append((self.ship.pos.x, self.ship.pos.y, self.ship.pos.z))
        self.assertEqual(self.ship.pos, target)
        self.assertFalse(self.ship.jump_travelling)
        self.assertIsNone(self.ship.jump_origin)
        self.assertIsNone(self.ship.jump_target)
        self.assertEqual(self.ship.jump_charge, 0)
        # progress closes on the exit: distance to target never grows
        for a, b in zip(seen, seen[1:]):
            da = math.sqrt((a[0] - target.x) ** 2 + (a[2] - target.z) ** 2)
            db = math.sqrt((b[0] - target.x) ** 2 + (b[2] - target.z) ** 2)
            self.assertLessEqual(db, da + 1e-9)

    def test_travelling_ship_is_hidden_from_live_detection_but_visible_to_owner(self):
        target = Vec3(7000, 0, -6000)
        self.jump((target.x, 0.0, target.z))
        self.charge_out(self.ship)
        enemy = next(e for e in self.st.entities.values()
                     if e.owner == 1 and e.is_ship)
        self.assertTrue(self.ship.jump_travelling)
        # the owner always tracks its own transit; enemy sensors cannot see it
        self.assertTrue(self.st.can_see(0, self.ship.id))
        self.assertFalse(self.st.can_see(1, self.ship.id))
        # and the transiting hull itself senses nothing (its sensors are in FTL)
        sources = [e for e, _ in self.st.sensor_sources(1)
                   if e.id == self.ship.id]
        self.assertEqual(sources, [])
        del enemy

    def test_travelling_ship_untargetable_unhittable_unsinkable(self):
        enemy = next(e for e in self.st.entities.values()
                     if e.owner == 1 and e.is_ship)
        # sit the enemy right on the flight corridor
        self.ship.pos = Vec3(3000, 0, 0)
        corridor = Vec3(3000, 0, 100)
        self.jump((corridor.x, 0.0, corridor.z))
        hull_before = self.ship.hull
        self.charge_out(self.ship)
        self.assertTrue(self.ship.jump_travelling)
        # auto-acquisition must skip the traveller
        self.gm.weapons.find_target(enemy, 30000)
        found = self.gm.weapons.find_target(enemy, 30000)
        self.assertTrue(found is None or found.id != self.ship.id)
        # queued projectile hits must not land during transit
        self.st.damage_queue.append({
            'attacker_id': 1, 'attacker_entity': enemy, 'target': self.ship,
            'damage': 500.0, 'shield_mult': 1.0, 'armor_mult': 1.0,
            'system_mult': 1.0, 'weapon': self.gm.ds.weapons['laser_cannon']})
        self.gm.damage.update(1 / 30)
        self.assertEqual(self.ship.hull, hull_before)
        self.assertTrue(self.ship.alive)

    def test_travelling_ship_is_not_explored_by_enemy_at_corridor(self):
        self.setUp()
        target = Vec3(7000, 0, -6000)
        self.jump((target.x, 0.0, target.z))
        self.charge_out(self.ship)
        self.assertTrue(self.ship.jump_travelling)
        # the travellers' own sensors stay inert: nothing new explored at the exit
        self.assertFalse(self.st.is_position_explored(0, target))

    def test_shields_locked_after_arrival_until_lockdown_expires(self):
        self.ship.shields = {q: 0.0 for q in self.ship.shields}
        self.jump((7000, 0, -6000))
        self.charge_out(self.ship)
        total = self.ship.jump_transit_total
        self.gm._update_jumps(total)          # arrive
        self.assertEqual(self.ship.jump_charge, 0)
        lockdown = self.rules['shield_lockdown_seconds']
        self.assertGreater(self.ship.ability_cooldowns.get('shield_lockdown', 0), 0)
        # shield regeneration is paused during the lockdown
        charged = {q: 0.0 for q in self.ship.shields}
        self.ship.shields = dict(charged)
        self_ship = self.ship
        self_ship.last_hit_time = -999.0
        regen = self.gm.ds.ships[self_ship.data_id].shield_regen
        self.assertGreater(regen, 0)
        elapsed = min(4.0, lockdown / 2)
        self.gm.damage.update(elapsed)
        after_lock = sum(self_ship.shields.values())
        self.assertEqual(after_lock, 0.0)
        # once the lockdown expires, regen resumes
        self.gm.abilities.update(lockdown)
        self.assertEqual(self_ship.ability_cooldowns.get('shield_lockdown', 0), 0)
        self.gm.damage.update(elapsed + 4.0)
        self.assertGreater(sum(self_ship.shields.values()), after_lock)

    def test_emergency_shield_recharge_blocked_during_lockdown(self):
        self.ship.shields = {q: 0.0 for q in self.ship.shields}
        self.jump((7000, 0, -6000))
        self.charge_out(self.ship)
        self.gm._update_jumps(self.ship.jump_transit_total)
        lockdown = self.rules['shield_lockdown_seconds']
        self.assertGreater(self.ship.ability_cooldowns.get('shield_lockdown', 0), 0)
        if 'emergency_shield_recharge' in self.gm.ds.abilities:
            self.assertFalse(self.gm.abilities.activate(
                self.ship, 'emergency_shield_recharge'))

    def test_ships_without_shields_get_no_lockdown_key(self):
        if self.ship.max_shield_quad > 0:
            self.skipTest('fixture ship has shields')
        self.jump((7000, 0, -6000))
        self.charge_out(self.ship)
        self.gm._update_jumps(self.ship.jump_transit_total)
        self.assertNotIn('shield_lockdown', self.ship.ability_cooldowns)

    def test_arrival_publishes_single_jump_complete_per_ship(self):
        events = []
        self.st.events.subscribe('jump_complete',
                                 lambda ev: events.append(ev.data['entity_id']))
        target = Vec3(7000, 0, -6000)
        self.jump((target.x, 0.0, target.z))
        self.charge_out(self.ship)
        self.gm._update_jumps(self.ship.jump_transit_total + 1 / 30)
        self.gm._update_jumps(1 / 30)
        self.assertEqual(events.count(self.ship.id), 1)

    def test_precise_restore_mid_transit_checksums_every_tick(self):
        from game.core.manager import GameManager
        from game.core.state import GameState
        from game.net.replay import state_checksum
        target = Vec3(7000.123456789, 0, -6000.123456789)
        self.jump((target.x, 0.0, target.z))
        self.charge_out(self.ship)
        self.gm._update_jumps(self.ship.jump_transit_total * 0.5)
        self.assertTrue(self.ship.jump_travelling)
        payload = json.loads(json.dumps(self.st.to_dict(precise=True)))
        restored = GameManager(GameState.from_dict(payload))
        self.assertEqual(state_checksum(self.st), state_checksum(restored.state))
        loaded = restored.state.entity(self.ship.id)
        self.assertTrue(loaded.jump_travelling)
        self.assertEqual(loaded.jump_charge, self.ship.jump_charge)
        # identical per-tick descent to the same exit
        for _ in range(int(round((self.ship.jump_charge + 1) * 30))):
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(state_checksum(self.st), state_checksum(restored.state))
        self.assertEqual(self.ship.pos, target)
        self.assertEqual(restored.state.entity(self.ship.id).pos, target)

    def test_invalid_restored_transit_state_cannot_trick_the_sim(self):
        from game.core.manager import GameManager
        from game.core.state import GameState
        for origin, total in ((Vec3(1e9, 0, 0), 5.0),        # origin outside map
                              (Vec3(0, 0, 0), float('nan')),  # nonfinite total
                              (Vec3(0, 0, 0), 0.0)):          # zero total
            with self.subTest(origin=origin, total=total):
                self.setUp()
                self.ship.jump_charge = 1.0
                self.ship.jump_travelling = True
                self.ship.jump_transit_total = total
                self.ship.jump_origin = origin.copy()
                self.ship.jump_target = Vec3(2500, 0, 4500)
                restored = GameManager(GameState.from_dict(
                    self.st.to_dict(precise=True)))
                ship = restored.state.entity(self.ship.id)
                restored._update_jumps(1)
                self.assertEqual(ship.jump_travelling, False)
                self.assertEqual(ship.jump_charge, 0)
                self.assertIsNone(ship.jump_target)

    def test_transit_ship_cannot_board_or_be_boarded(self):
        from game.systems.boarding import boarding_reason
        enemy = next(e for e in self.st.entities.values()
                     if e.owner == 1 and e.is_ship)
        self.jump((7000, 0, -6000))
        self.charge_out(self.ship)
        self.assertTrue(self.ship.jump_travelling)
        self.assertNotEqual(boarding_reason(self.st, self.ship, enemy), '')
        # a transiting hull may not be boarded either
        self.ship.pos = enemy.pos + Vec3(100, 0, 0)
        self.assertNotEqual(boarding_reason(self.st, enemy, self.ship), '')

    def test_colonize_and_construction_gates_cover_transit(self):
        # the transit hull must not start surface work mid-flight
        from game.systems.construction import ConstructionSystem
        planet = next(e for e in self.st.entities.values() if e.is_planet)
        self.jump((7000, 0, -6000))
        self.charge_out(self.ship)
        self.assertTrue(self.ship.jump_travelling)
        cs = ConstructionSystem(self.st)
        self.assertFalse(cs.start_colonize(self.ship.id, planet.id, 0))


if __name__ == '__main__':
    unittest.main()