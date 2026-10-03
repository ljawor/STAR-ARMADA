"""Authoritative hyperspace orders and deterministic reserved exits."""
import copy
import unittest

from helpers import make_game
from game.core.commands import PlayerCommand, JumpCommand
from game.core.vectors import Vec3


class TestJumpSim(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.ship = next(e for e in self.st.entities.values()
                         if e.owner == 0 and e.is_ship)

    def jump(self, target, ids=None):
        self.st.command_queue.append(PlayerCommand(
            'jump', 0, unit_ids=tuple(ids or [self.ship.id]), target_pos=target))
        self.gm.commands.consume()

    def snapshot(self):
        return copy.deepcopy((self.st.to_dict(precise=True), self.st.effects,
                              self.st.floating_texts))

    def moving_fleet(self):
        ships = sorted((e for e in self.st.entities.values()
                        if e.owner == 0 and e.is_ship), key=lambda e: e.id)
        self.st.queue_command(PlayerCommand(
            'fleet_create', 0, unit_ids=tuple(e.id for e in ships)))
        self.gm.commands.consume()
        fleet = self.st.fleets[ships[0].fleet_id]
        self.gm.formations.apply_fleet_move(fleet, Vec3(-7000, 0, 2000))
        return fleet, ships

    def test_nonflagship_jump_not_reclaimed_by_old_formation_after_real_ticks(self):
        fleet, ships = self.moving_fleet()
        jumper = self.st.entities[18]
        self.assertIn(jumper.id, fleet.member_ids)
        self.assertNotEqual(jumper.id, fleet.flagship_id)
        others = [e for e in ships if e.id != jumper.id]
        before = {e.id: copy.deepcopy(e) for e in others}
        target = Vec3(2500, 0, 4500)
        self.jump(target.to_dict(), [jumper.id])
        # Jump acceptance must not disturb any nonselected entity.
        self.assertEqual(before, {e.id: e for e in others})
        for _ in range(140):
            self.gm.step(1 / 30)
        self.assertEqual(self.st.tick, 140)
        self.assertEqual(jumper.pos, target)
        self.assertEqual(jumper.order_type, 'idle')
        self.assertIsNone(jumper.order_target_pos)
        self.assertIsNone(jumper.fleet_id)
        self.assertEqual(fleet.member_ids, {e.id for e in others})
        self.assertIn(fleet.flagship_id, fleet.member_ids)
        self.assertEqual(fleet.rally_point, [-7000, 0, 2000])
        for e in others:
            self.assertEqual(e.fleet_id, fleet.id)
            self.assertEqual(e.order_type, before[e.id].order_type)
            self.assertEqual(e.order_target_pos, before[e.id].order_target_pos)
            self.assertNotEqual(e.pos, before[e.id].pos)

    def test_flagship_subset_jump_elects_remaining_leader_without_reordering(self):
        fleet, ships = self.moving_fleet()
        jumpers = [self.st.entities[fleet.flagship_id], self.st.entities[18]]
        others = [e for e in ships if e not in jumpers]
        # Exercise the deterministic lowest-id tie breaker.
        for e in others:
            e.max_hull = 1000
        before = {e.id: copy.deepcopy(e) for e in others}
        self.jump((2500, 0, 4500), [e.id for e in reversed(jumpers)])
        exits = {e.id: e.jump_target.copy() for e in jumpers}
        self.assertEqual(before, {e.id: e for e in others})
        self.assertEqual(fleet.flagship_id, min(e.id for e in others))
        self.assertEqual(fleet.member_ids, set(before))
        self.assertEqual(fleet.rally_point, [-7000, 0, 2000])
        for _ in range(180):
            self.gm.step(1 / 30)
        self.assertEqual(self.st.tick, 180)
        for e in jumpers:
            self.assertEqual(e.pos, exits[e.id])
            self.assertEqual(e.order_type, 'idle')
            self.assertIsNone(e.order_target_pos)
            self.assertIsNone(e.fleet_id)
        for e in others:
            self.assertEqual(e.fleet_id, fleet.id)
            self.assertEqual(e.order_target_pos, before[e.id].order_target_pos)
            self.assertNotEqual(e.pos, before[e.id].pos)

    def test_entire_fleet_jump_removes_empty_formation_and_stays_at_exits(self):
        fleet, ships = self.moving_fleet()
        self.jump((2500, 0, 4500), [e.id for e in ships])
        exits = {e.id: e.jump_target.copy() for e in ships}
        self.assertNotIn(fleet.id, self.st.fleets)
        for _ in range(180):
            self.gm.step(1 / 30)
        self.assertEqual(self.st.tick, 180)
        for e in ships:
            self.assertEqual(e.pos, exits[e.id])
            self.assertIsNone(e.fleet_id)
            self.assertEqual(e.order_type, 'idle')
            self.assertIsNone(e.order_target_pos)
            self.assertIsNone(e.jump_target)
            self.assertEqual(e.jump_charge, 0)

    def test_rejected_fleet_jump_preserves_membership_orders_and_effects(self):
        for rejection in ('destination', 'no_room', 'cooldown'):
            with self.subTest(rejection=rejection):
                self.setUp()
                fleet, ships = self.moving_fleet()
                target = (2500, 0, 4500)
                if rejection == 'destination':
                    target = (self.st.map_info.bounds, 0, 0)
                elif rejection == 'no_room':
                    ships[-1].radius = self.st.map_info.bounds
                else:
                    for e in ships:
                        e.ability_cooldowns['_jump_cd'] = 1
                before = self.snapshot()
                fleet_before = copy.deepcopy(fleet)
                self.jump(target, [e.id for e in ships])
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.st.fleets[fleet.id], fleet_before)

    def test_detached_fleet_jump_precise_json_restore_matches_every_tick(self):
        import json
        from game.core.state import GameState
        from game.core.manager import GameManager
        fleet, ships = self.moving_fleet()
        jumper = self.st.entities[fleet.flagship_id]
        self.jump((2500.123456789, -20.123456789, 4500.123456789), [jumper.id])
        for _ in range(37):
            self.gm.step(1 / 30)
        self.assertGreater(jumper.jump_charge, 0)
        payload = json.loads(json.dumps(self.st.to_dict(precise=True)))
        restored = GameManager(GameState.from_dict(payload))

        def precise(gm):
            return json.loads(json.dumps(gm.state.to_dict(precise=True)))

        self.assertEqual(precise(restored), payload)
        loaded = restored.state.entities[jumper.id]
        self.assertIsNone(loaded.fleet_id)
        self.assertNotIn(jumper.id, restored.state.fleets[fleet.id].member_ids)
        for _ in range(180):
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            # Full precise state includes charge/cooldown omitted by checksums.
            self.assertEqual(precise(self.gm), precise(restored))
        self.assertEqual(self.st.tick, 217)
        self.assertEqual(jumper.pos, Vec3(2500.123456789, -20.123456789, 4500.123456789))
        self.assertEqual(jumper.order_type, 'idle')
        self.assertIsNone(jumper.order_target_pos)

    def test_invalid_destination_has_no_effects(self):
        half = self.st.map_info.bounds / 2
        for target in (None, (), (1, 2), (1, 2, 3, 4), 'abc',
                       ('1', 0, 0), (True, 0, 0),
                       (float('nan'), 0, 0), (0, float('inf'), 0),
                       (0, 0, -float('inf')), (half + 1, 0, 0),
                       (0, 0, -half - 1), (0, half + 1, 0)):
            with self.subTest(target=target):
                self.setUp()
                before = self.snapshot()
                self.jump(target)
                self.assertEqual(before, self.snapshot())

    def test_explored_and_unexplored_destinations_accepted(self):
        target = Vec3(2500, 0, 4500)
        for explored in (False, True):
            with self.subTest(explored=explored):
                self.setUp()
                self.st.explored_cells = {0: set()}
                if explored:
                    self.st.explored_cells[0].add(self.st.visibility_cell(target))
                self.assertEqual(self.st.is_position_explored(0, target), explored)
                self.jump((target.x, target.y, target.z))
                self.assertGreater(self.ship.jump_charge, 0)
                self.assertEqual(self.ship.jump_target, target)
                rules = self.gm.commands.ds.rules['hyperspace']
                sd = self.gm.commands.ds.ships[self.ship.data_id]
                self.assertEqual(self.ship.jump_charge, max(rules['min_prep_seconds'],
                                 sd.command_cost * rules['prep_seconds_per_command_point']))

    def test_only_owned_live_ships_are_eligible(self):
        from game.core.entity import Entity
        excluded = [e for e in self.st.entities.values()
                    if e.owner != 0 or not e.is_ship]
        dead = copy.deepcopy(self.ship)
        dead.id = self.st.next_entity_id
        self.st.next_entity_id += 1
        dead.alive = False
        self.st.add_entity(dead)
        impostor = Entity(self.st.next_entity_id, 'cargo', 0, self.ship.data_id)
        self.st.next_entity_id += 1
        self.st.add_entity(impostor)
        excluded += [dead, impostor]
        before = [copy.deepcopy(e) for e in excluded]
        self.jump((2500, 0, 4500), [e.id for e in excluded] + [self.ship.id, self.ship.id])
        self.assertGreater(self.ship.jump_charge, 0)
        self.assertEqual(excluded, before)
        self.assertEqual(len(self.st.effects), 1)

    def test_charge_cannot_be_replaced_even_after_cooldown_expires(self):
        self.jump((2500, 0, 4500))
        self.ship.ability_cooldowns['_jump_cd'] = 0
        self.ship.jump_charge = 0.123
        before = self.snapshot()
        self.jump((5500, 0, 4500))
        self.assertEqual(before, self.snapshot())

    def test_cooldown_reuse_has_no_effects(self):
        self.ship.ability_cooldowns['_jump_cd'] = 1
        before = self.snapshot()
        self.jump((2500, 0, 4500))
        self.assertEqual(before, self.snapshot())

    def test_jump_stops_old_orders_before_charge_and_on_exit(self):
        self.ship.order_type = 'attack'
        self.ship.order_target_id = 999
        self.ship.current_target = 999
        self.ship.order_target_pos = Vec3(6000, 0, 6000)
        self.ship.patrol_a = Vec3(5000, 0, 5000)
        self.ship.patrol_b = Vec3(6000, 0, 6000)
        self.ship.vel = Vec3(20, 10, 30)
        self.jump((2500, 0, 4500))
        self.assertEqual(self.ship.order_type, 'idle')
        self.assertIsNone(self.ship.order_target_id)
        self.assertIsNone(self.ship.current_target)
        self.assertIsNone(self.ship.order_target_pos)
        self.assertIsNone(self.ship.patrol_a)
        self.assertIsNone(self.ship.patrol_b)
        self.assertEqual(self.ship.vel, Vec3())
        # Orders received during charge must not create a phantom chase on exit.
        self.ship.order_type = 'attack'
        self.ship.current_target = 999
        self.ship.order_target_id = 999
        self.gm._update_jumps(self.ship.jump_charge)
        self.assertEqual(self.ship.pos, Vec3(2500, 0, 4500))
        self.assertEqual(self.ship.order_type, 'idle')
        self.assertIsNone(self.ship.current_target)
        self.assertIsNone(self.ship.order_target_id)
        self.assertEqual(self.ship.jump_charge, 0)

    def test_group_reserves_deterministic_hull_clearance_exits(self):
        self.gm.factory.spawn_ship('imperial_frigate', 0, Vec3(-11000, 0, -1500))
        ships = [e for e in self.st.entities.values() if e.owner == 0 and e.is_ship]
        target = Vec3(2500, 0, 4500)
        self.jump((target.x, target.y, target.z), [e.id for e in reversed(ships)])
        self.assertTrue(all(e.jump_charge > 0 for e in ships))
        ordered = sorted(ships, key=lambda e: e.id)
        self.assertEqual(ordered[0].jump_target, target)
        for i, e in enumerate(ordered):
            self.assertLess((e.jump_target - target).length(), 1500)
            self.assertFalse(self.st.is_position_explored(0, e.jump_target))
            for other in ordered[:i]:
                self.assertGreaterEqual((e.jump_target - other.jump_target).length(),
                                        1.15 * (e.radius + other.radius))
        reserved = {e.id: e.jump_target.copy() for e in ships}
        # Earliest arrival explores the area; this must not invalidate its peers.
        first = min(ships, key=lambda e: (e.jump_charge, e.id))
        self.gm._update_jumps(first.jump_charge)
        self.gm.visibility.update()
        self.assertTrue(self.st.is_position_explored(0, first.pos))
        self.assertTrue(any(e.jump_charge > 0 for e in ships))
        self.gm._update_jumps(max(e.jump_charge for e in ships) + 1)
        self.assertTrue(all(e.jump_charge == 0 and e.jump_target is None for e in ships))
        self.assertEqual({e.id: e.pos for e in ships}, reserved)

    def test_single_hull_footprint_must_fit_bounds(self):
        half = self.st.map_info.bounds / 2
        for target in ((half - self.ship.radius / 2, 0, 4500),
                       (2500, half - self.ship.radius / 2, 4500),
                       (2500, 0, half - self.ship.radius / 2)):
            with self.subTest(target=target):
                self.setUp()
                self.st.explored_cells = {0: set()}
                self.assertFalse(self.st.is_position_explored(0, Vec3(*target)))
                before = self.snapshot()
                self.jump(target)
                self.assertEqual(before, self.snapshot())

    def test_hull_can_cross_own_or_allied_exploration_boundary(self):
        target = Vec3(2499, 0, 4499)
        for owner in (0, 1):
            with self.subTest(exploration_owner=owner):
                self.setUp()
                self.st.players[0].team = self.st.players[1].team = 7
                self.st.explored_cells = {0: set(), 1: set()}
                self.st.explored_cells[owner].add((5, 9))
                self.assertFalse(self.st.is_position_explored(0, target))
                self.assertTrue(self.st.is_position_explored(0, target + Vec3(2, 0, 2)))
                self.assertGreater(self.ship.radius, 3)
                self.jump((target.x, target.y, target.z))
                self.assertEqual(self.ship.jump_target, target)
                self.gm._update_jumps(self.ship.jump_charge)
                self.assertEqual(self.ship.pos, target)

    def test_allied_explored_destination_accepted(self):
        target = Vec3(2500, 0, 4500)
        self.st.players[0].team = self.st.players[1].team = 7
        self.st.explored_cells = {0: set(), 1: {self.st.visibility_cell(target)}}
        self.assertTrue(self.st.is_position_explored(0, target))
        self.assertFalse(self.st.is_position_visible(0, target))
        self.jump((target.x, target.y, target.z))
        self.assertEqual(self.ship.jump_target, target)
        self.gm._update_jumps(self.ship.jump_charge)
        self.assertEqual(self.ship.pos, target)

    def test_currently_sensed_destination_accepted(self):
        target = self.ship.pos + Vec3(500, 0, 0)
        self.assertTrue(self.st.is_position_explored(0, target))
        self.assertTrue(self.st.is_position_visible(0, target))
        self.jump((target.x, target.y, target.z))
        self.assertEqual(self.ship.jump_target, target)
        self.gm._update_jumps(self.ship.jump_charge)
        self.assertEqual(self.ship.pos, target)

    def test_group_exits_independent_of_exploration_and_selection_order(self):
        ids = [e.id for e in self.st.entities.values() if e.owner == 0 and e.is_ship]
        target = (2500, 0, 4500)
        self.st.explored_cells = {0: set()}
        self.jump(target, ids)
        exits = {}
        for uid in ids:
            exit_pos = self.st.entities[uid].jump_target
            self.assertIsNotNone(exit_pos)
            assert exit_pos is not None
            exits[uid] = exit_pos.copy()
        self.setUp()
        self.st.explored_cells = {0: {(x, z) for x in range(0, 20)
                                     for z in range(0, 20)}}
        self.jump(target, list(reversed(ids)))
        self.assertEqual(exits, {uid: self.st.entities[uid].jump_target for uid in ids})
        self.assertTrue(all(self.st.is_position_explored(0, p) for p in exits.values()))
        self.gm._update_jumps(max(self.st.entities[uid].jump_charge for uid in ids) + 1)
        self.assertEqual(exits, {uid: self.st.entities[uid].pos for uid in ids})

    def test_restored_invalid_charge_cannot_teleport_outside_map(self):
        from game.core.state import GameState
        from game.core.manager import GameManager
        for target in (Vec3(float('nan'), 0, 0), Vec3(15000, 0, 0)):
            with self.subTest(target=target):
                self.setUp()
                self.ship.jump_charge = 0.1
                self.ship.jump_target = target
                restored = GameManager(GameState.from_dict(self.st.to_dict(precise=True)))
                ship = restored.state.entity(self.ship.id)
                original = ship.pos.copy()
                restored._update_jumps(1)
                self.assertEqual(ship.pos, original)
                self.assertEqual(ship.jump_charge, 0)
                self.assertIsNone(ship.jump_target)
                self.assertEqual(restored.state.effects, [])

    def test_boundary_group_is_spaced_inward_and_command_order_invariant(self):
        ships = sorted((e for e in self.st.entities.values()
                        if e.owner == 0 and e.is_ship), key=lambda e: e.id)
        self.st.explored_cells = {0: set()}
        target = (self.st.map_info.bounds / 2 - 1, 0, 4500)
        self.jump(target, [e.id for e in ships])
        exits = [e.jump_target.copy() for e in ships]
        half = self.st.map_info.bounds / 2
        for e in ships:
            self.assertLessEqual(abs(e.jump_target.x) + e.radius, half)
            self.assertLessEqual(abs(e.jump_target.z) + e.radius, half)
        self.setUp()
        self.st.explored_cells = {0: set()}
        self.jump(target, [e.id for e in reversed(ships)])
        self.assertEqual(exits, [self.st.entity(e.id).jump_target for e in ships])

    def test_no_room_for_entire_group_rejects_atomically(self):
        ships = [e for e in self.st.entities.values() if e.owner == 0 and e.is_ship]
        ships[-1].radius = self.st.map_info.bounds
        before = self.snapshot()
        self.jump((2500, 0, 4500), [e.id for e in ships])
        self.assertEqual(before, self.snapshot())

    def test_hidden_enemy_geometry_does_not_change_reserved_exits(self):
        from game.core.entity import Entity
        ids = [e.id for e in self.st.entities.values() if e.owner == 0 and e.is_ship]
        self.jump((2500, 0, 4500), ids)
        exits = [self.st.entity(uid).jump_target.copy() for uid in ids]
        self.setUp()
        hidden = Entity(self.st.next_entity_id, 'station', 1, 'hidden',
                        pos=Vec3(2500, 0, 4500), radius=5000, is_station=True)
        self.st.add_entity(hidden)
        self.assertFalse(self.st.can_see(0, hidden.id))
        self.jump((2500, 0, 4500), ids)
        self.assertEqual(exits, [self.st.entity(uid).jump_target for uid in ids])

    def test_single_exact_click_serialized_command_completes_and_discovers(self):
        target = Vec3(2500.123456789, -20.123456789, 4500.123456789)
        cmd = JumpCommand(0, [self.ship.id], target)
        self.st.queue_command(PlayerCommand.from_dict(cmd.to_dict()))
        for _ in range(140):
            self.gm.step(1 / 30)
        self.assertEqual(self.st.tick, 140)
        self.assertEqual(self.ship.pos, target)
        self.assertEqual(self.ship.jump_charge, 0)
        self.assertTrue(self.st.is_position_explored(0, self.ship.pos))
        self.assertIsNone(self.ship.order_target_pos)

    def test_group_reserved_exits_survive_actual_tick_separation(self):
        ships = [e for e in self.st.entities.values() if e.owner == 0 and e.is_ship]
        self.jump((2500, 0, 4500), [e.id for e in ships])
        reserved = {e.id: e.jump_target.copy() for e in ships}
        for _ in range(140):
            self.gm.step(1 / 30)
        self.assertEqual(self.st.tick, 140)
        self.assertEqual({e.id: e.pos for e in ships}, reserved)
        self.assertTrue(all(e.jump_target is None for e in ships))

    def test_ship_definition_must_be_a_real_ship(self):
        squadron = next(e for e in self.st.entities.values() if e.is_squadron)
        for data_id in ('missing_ship', squadron.data_id):
            with self.subTest(data_id=data_id):
                self.ship.data_id = data_id
                before = self.snapshot()
                self.jump((2500, 0, 4500))
                self.assertEqual(before, self.snapshot())

    def test_precise_restore_preserves_charges_exits_and_tick_checksums(self):
        import json
        from game.core.state import GameState
        from game.core.manager import GameManager
        from game.net.replay import state_checksum
        self.gm.factory.spawn_ship('imperial_frigate', 0, Vec3(-11000, 0, -1500))
        ships = [e for e in self.st.entities.values() if e.owner == 0 and e.is_ship]
        ids = [e.id for e in ships]
        self.jump((2500.123456789, -20.123456789, 4500.123456789), ids)
        for _ in range(37):
            self.gm.step(1 / 30)
        restored = GameManager(GameState.from_dict(json.loads(json.dumps(
            self.st.to_dict(precise=True)))))
        for e in ships:
            loaded = restored.state.entity(e.id)
            self.assertEqual(loaded.jump_charge, e.jump_charge)
            self.assertEqual(loaded.jump_target, e.jump_target)
            self.assertEqual(loaded.ability_cooldowns, e.ability_cooldowns)
        self.assertEqual(state_checksum(self.st), state_checksum(restored.state))
        for _ in range(150):
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(state_checksum(self.st), state_checksum(restored.state))
        self.assertTrue(all(e.jump_charge == 0 for e in ships))
        self.assertEqual(self.st.tick, 187)


if __name__ == '__main__':
    unittest.main()
