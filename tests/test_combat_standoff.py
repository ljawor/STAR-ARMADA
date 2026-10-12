"""Deterministic combat navigation, exercised through real movement/weapons."""
import math
import unittest

from helpers import make_game
from game.core.vectors import Vec3


class CombatStandoffTests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.st.entities.clear()
        self.target = self.gm.factory.spawn_station('command_station', 1, Vec3())
        self.ship = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3(0, 0, -1200))
        self.ship.sensor_range = 10000
        self.ship.order_type = 'attack'
        self.ship.order_target_id = self.target.id
        self.ship.current_target = self.target.id

    def advance(self, ticks=3600, dt=1/30):
        distances, angles, shots = [], [], 0
        for _ in range(ticks):
            self.st.tick += 1
            self.st.time += dt
            self.gm.movement.update(dt)
            self.st.grid.rebuild(self.st.entities)
            self.ship.energy = self.ship.max_energy
            self.gm.weapons._ship_weapons(self.ship, dt)
            shots += len(self.st.projectiles) + len(self.st.damage_queue)
            self.st.projectiles.clear()
            self.st.damage_queue.clear()
            offset = self.ship.pos - self.target.pos
            distances.append(offset.length())
            angles.append(math.atan2(offset.x, offset.z))
            facing = Vec3(math.sin(self.ship.yaw), 0, math.cos(self.ship.yaw))
            self.assertLess(abs(self.ship.vel.x*facing.z-self.ship.vel.z*facing.x), 1e-7)
        travel = sum(abs((b-a+math.pi)%(2*math.pi)-math.pi) for a,b in zip(angles, angles[1:]))
        return distances, travel, shots

    def test_visible_station_approach_becomes_firing_orbit(self):
        """A hull whose mounts cover every bearing keeps firing while it orbits.

        #58 made the catalogue's per-mount `arcs` authoritative, so the
        Imperial corvette's forward-only laser no longer strafes broadside;
        the all-round Confed corvette keeps the original invariant (an orbit
        inside weapon reach that keeps landing shots) at the original floor.
        """
        self.ship.alive = False
        self.ship = self.gm.factory.spawn_ship('confed_corvette', 0, Vec3(0, 0, -1200))
        self.ship.sensor_range = 10000
        self.ship.order_type = 'attack'
        self.ship.order_target_id = self.target.id
        self.ship.current_target = self.target.id
        distances, travel, shots = self.advance()
        self.assertGreaterEqual(min(distances), self.target.radius+self.ship.radius+40-1e-6)
        self.assertGreater(min(distances[-900:]), 500, 'must not slowly thrust into target center')
        self.assertLess(max(distances[-900:]), 900, 'orbit remains inside actual weapon reach')
        self.assertGreater(travel, 3, 'orbit must make meaningful angular progress')
        self.assertGreater(shots, 50)
        self.assertEqual(self.target.pos, Vec3())

    def test_fleet_combat_approach_keeps_light_screen_with_siege_ships(self):
        from game.core.commands import FleetCreateCommand, AttackMoveCommand
        cruiser = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3(0, 0, -6000))
        self.ship.pos = Vec3(250, 0, -6000)
        self.ship.current_target = self.ship.order_target_id = None
        self.gm.commands._apply(FleetCreateCommand(0, [self.ship.id, cruiser.id], 'Siege'))
        self.gm.commands._apply(AttackMoveCommand(0, [self.ship.id, cruiser.id], Vec3(0, 0, 6000)))
        for _ in range(1800):
            self.st.time += 1/30
            self.gm.movement.update(1/30)
        self.assertLess(self.ship.pos.dist(cruiser.pos), 500,
                        'light screen must not abandon slow siege ships en route')
        self.assertGreater(self.ship.pos.z, -4000)

    def test_ai_scout_replacements_do_not_spend_second_market_budget(self):
        from game.ai.ai import AIPlayer
        gm = make_game(ai=False)
        st = gm.state
        home = next(e for e in st.entities.values() if e.owner == 1 and e.data_id == 'command_station')
        gm.factory.spawn_station('trade_station', 1, home.pos + Vec3(0, 0, 900))
        st.players[1].credits = 1600
        ai = AIPlayer(st, 1)
        ai._produce_fleet(home)
        self.assertFalse(st.command_queue,
                         'replacement fighters must not consume the budget completing a trade route')
        gm.factory.spawn_station('trade_station', 1, home.pos + Vec3(900, 0, 0))
        ai._produce_fleet(home)
        self.assertTrue(st.command_queue, 'normal production resumes once both markets are accounted for')

    def test_large_dt_swept_path_cannot_tunnel_through_minimum(self):
        self.ship.pos = Vec3(0, 0, -205)
        self.ship.vel = Vec3(0, 0, 100000)
        self.gm.movement.update(.1)
        self.assertLess(self.ship.pos.z, -203.999)
        self.assertGreaterEqual(self.ship.pos.dist(self.target.pos), 204-1e-6)

    def test_overlap_and_zero_distance_resolve_outward_deterministically(self):
        for offset in (Vec3(), Vec3(0, 0, -10)):
            with self.subTest(offset=offset):
                self.ship.pos = offset.copy()
                self.ship.vel = Vec3(0, 0, 500)
                self.gm.movement.update(1/30)
                self.assertGreaterEqual(self.ship.pos.dist(self.target.pos), 204-1e-6)
                self.assertEqual(self.ship.vel, Vec3())

    def test_front_arc_capital_orbit_has_repeated_firing_windows(self):
        """A full-coverage capital keeps firing while it orbits (#58).

        It no longer needs the alternating stopped, target-facing fire windows
        that a nose-only hull uses: its batteries cover every bearing, so the
        beams must fire continuously from the tangent orbit.
        """
        self.ship.alive = False
        self.ship = self.gm.factory.spawn_ship('confed_supercapital', 0, Vec3(0, 0, -1872))
        self.ship.sensor_range = 10000
        self.ship.order_type = 'attack'
        self.ship.order_target_id = self.target.id
        self.ship.current_target = self.target.id
        self.ship.yaw = math.pi/2
        beams = 0
        angles = []
        for i in range(7200):
            self.st.tick += 1
            self.st.time += 1/30
            self.gm.movement.update(1/30)
            self.ship.energy = self.ship.max_energy
            self.gm.weapons._ship_weapons(self.ship, 1/30)
            if i > 1800:
                beams += sum(d['weapon'].id == 'beam_lance' for d in self.st.damage_queue)
            self.st.damage_queue.clear()
            self.st.projectiles.clear()
            angles.append(math.atan2(self.ship.pos.x, self.ship.pos.z))
        self.assertGreater(beams, 5, 'tangent-only nose-first orbit must not silence front weapons')
        travel = sum(abs((b-a+math.pi)%(2*math.pi)-math.pi) for a,b in zip(angles, angles[1:]))
        self.assertGreater(travel, .5)

    def test_large_but_reachable_station_does_not_choose_unreachable_orbit(self):
        self.target.radius = 800
        hard, preferred = self.gm.movement._combat_ranges(self.ship, self.target)
        self.assertEqual(hard, 874)
        self.assertGreater(preferred, hard)
        self.assertLess(preferred, 900)

    def test_target_moving_after_attacker_cannot_leave_final_overlap(self):
        self.target.alive = False
        self.target = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3())
        self.target.order_type = 'move'
        self.target.order_target_pos = Vec3(0, 0, -1000)
        self.target.yaw = math.pi
        self.target.vel = Vec3(0, 0, -75)
        self.ship.pos = Vec3(0, 0, -110)
        self.ship.order_target_id = self.ship.current_target = self.target.id
        self.gm.movement.update(.5)
        self.assertGreaterEqual(self.ship.pos.dist(self.target.pos), 108-1e-6)

    def test_multiple_units_orbit_live_moving_ship_and_station(self):
        for moving in (False, True):
            with self.subTest(moving=moving):
                self.st.entities.clear()
                if moving:
                    self.target = self.gm.factory.spawn_ship('imperial_battleship', 1, Vec3())
                    self.target.order_type = 'move'
                    self.target.order_target_pos = Vec3(7000, 0, 0)
                    self.target.yaw = math.pi/2
                else:
                    self.target = self.gm.factory.spawn_station('command_station', 1, Vec3())
                ships = []
                for i in range(3):
                    angle = i*2*math.pi/3
                    e = self.gm.factory.spawn_ship('imperial_corvette', 0,
                        Vec3(math.sin(angle)*1200, 0, math.cos(angle)*1200))
                    e.sensor_range = 10000
                    e.order_type = 'attack'
                    e.order_target_id = e.current_target = self.target.id
                    ships.append(e)
                angle_travel = {e.id: 0.0 for e in ships}
                previous = {}
                fired = {e.id: 0 for e in ships}
                for tick in range(5400):
                    self.st.tick += 1
                    self.st.time += 1/30
                    self.gm.movement.update(1/30)
                    self.st.grid.rebuild(self.st.entities)
                    self.gm.separation.update(1/30)
                    for e in ships:
                        distance = e.pos.dist(self.target.pos)
                        self.assertGreaterEqual(distance, self.target.radius+e.radius+40-1e-6)
                        if tick > 3600:
                            self.assertLess(distance, 900)
                        offset = e.pos-self.target.pos
                        angle = math.atan2(offset.x, offset.z)
                        if e.id in previous:
                            angle_travel[e.id] += abs((angle-previous[e.id]+math.pi)%(2*math.pi)-math.pi)
                        previous[e.id] = angle
                        e.energy = e.max_energy
                        self.gm.weapons._ship_weapons(e, 1/30)
                        fired[e.id] += len(self.st.projectiles)
                        self.st.projectiles.clear()
                for e in ships:
                    self.assertGreater(angle_travel[e.id], 3)
                    self.assertGreater(fired[e.id], 50)
                if moving:
                    self.assertGreater(self.target.pos.x, 4000)
                else:
                    self.assertEqual(self.target.pos, Vec3())

    def test_attack_move_acquired_contact_resumes_route_after_kill(self):
        self.ship.order_type = 'attack_move'
        self.ship.order_target_id = None
        destination = Vec3(0, 0, 5000)
        self.ship.order_target_pos = destination.copy()
        self.advance(1800)
        self.assertEqual(self.ship.order_target_pos, destination)
        self.target.alive = False
        initial = self.ship.pos.dist(destination)
        self.advance(900)
        self.assertIsNone(self.ship.current_target)
        self.assertEqual(self.ship.order_type, 'attack_move')
        self.assertLess(self.ship.pos.dist(destination), initial-500)

    def test_lost_sensor_drops_orbit_without_reading_hidden_position(self):
        self.ship.pos = Vec3(0, 0, -702)
        self.ship.sensor_range = 10
        self.target.pos = Vec3(5000, 0, 6000)
        self.ship.vel = Vec3()
        self.gm.movement.update(1/30)
        self.assertIsNone(self.ship.current_target)
        self.assertIsNone(self.ship.order_target_id)
        self.assertEqual(self.ship.order_type, 'idle')
        self.assertEqual(self.ship.pos, Vec3(0, 0, -702))
        self.assertEqual(self.ship.yaw, 0)

    def test_oversized_station_preserves_safety_without_changing_weapon_reach(self):
        self.target.radius = 1200
        self.ship.pos = Vec3(0, 0, -1600)
        hard, preferred = self.gm.movement._combat_ranges(self.ship, self.target)
        self.assertEqual(hard, 1274)
        self.assertGreater(preferred, hard)
        distances, travel, shots = self.advance(3600)
        self.assertGreaterEqual(min(distances), hard-1e-6)
        self.assertEqual(shots, 0, 'center-based weapon reach cannot penetrate oversized hulls')
        self.assertGreater(travel, 2)

    def test_noncombat_moves_hold_and_colonize_ignore_combat_lock(self):
        from game.core.state import GameState
        from game.core.manager import GameManager
        planet = self.gm.factory.spawn_planet({'id': 'approach', 'type': 'temperate',
                                              'pos': [2000, 0, 0], 'radius': 300})
        for order in ('move', 'colonize', 'hold', 'idle'):
            with self.subTest(order=order):
                self.ship.order_type = order
                self.ship.order_target_id = planet.id if order == 'colonize' else None
                self.ship.order_target_pos = Vec3(2000, 0, 2000) if order == 'move' else None
                clean = GameManager(GameState.from_dict(self.st.to_dict(precise=True)))
                clean.state.entity(self.ship.id).current_target = None
                self.gm.movement.update(1/30)
                clean.movement.update(1/30)
                other = clean.state.entity(self.ship.id)
                self.assertEqual(self.ship.pos, other.pos)
                self.assertEqual(self.ship.vel, other.vel)
                self.assertEqual(self.ship.yaw, other.yaw)

    def test_save_restore_and_recorded_replay_match_every_tick(self):
        from game.core.state import GameState
        from game.core.manager import GameManager
        from game.net.replay import ReplayRecorder, ReplayPlayer, state_checksum
        self.ship.data_id = 'imperial_cruiser'  # includes front-arc firing windows
        self.ship.hull = self.ship.max_hull = 1e9
        self.target.hull = self.target.max_hull = 1e9
        self.ship.order_type = 'idle'
        self.ship.order_target_id = self.ship.current_target = None
        recorder = ReplayRecorder(self.st)
        from game.core.commands import AttackCommand
        command = AttackCommand(0, [self.ship.id], self.target.id)
        recorder.on_command(command, self.st.tick)
        self.st.queue_command(command)
        replay = ReplayPlayer(recorder.to_dict())
        restored = GameManager(GameState.from_dict(replay.data['initial_state']))
        for i in range(1200):
            self.gm.step(1/30)
            for command in replay.commands_for_tick(restored.state.tick):
                restored.state.queue_command(command)
            restored.step(1/30)
            self.assertEqual(state_checksum(self.st), state_checksum(restored.state), i)
            for eid in (self.ship.id, self.target.id):
                a, b = self.st.entity(eid), restored.state.entity(eid)
                self.assertEqual((a.pos, a.vel, a.yaw), (b.pos, b.vel, b.yaw), i)
            if i == 600:
                restored = GameManager(GameState.from_dict(restored.state.to_dict(precise=True)))

    def test_large_dt_moving_target_cannot_tunnel_past_stopped_attacker(self):
        # #58: this cruiser's batteries now cover every bearing, so it no longer
        # freezes in a front-arc fire window during the step. It still ends the
        # step stopped (speed 0) at the swept keep-out boundary, which resolves
        # 163.9986 from the target centre against the 164 disc sum - 1.4e-3
        # deeper than the frozen trajectory's exact 164.0000. The invariant is
        # unchanged (a moving target must not pass through the attacker), so the
        # bound is stated as the disc sum instead of a hand-tuned 163.999.
        self.ship.data_id = 'imperial_cruiser'
        self.ship.radius = 90
        self.ship.pos = Vec3(0, 0, -166)
        self.target.alive = False
        self.target = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3())
        self.target.order_type = 'move'
        self.target.order_target_pos = Vec3(0, 0, -2000)
        self.target.yaw = math.pi
        self.target.vel = Vec3(0, 0, -75)
        self.ship.order_target_id = self.ship.current_target = self.target.id
        self.st.time = 41.0 - (self.ship.id * 1.618) % 41.0  # stopped front-fire phase
        self.gm.movement.update(10)
        separation = self.target.pos.z - self.ship.pos.z
        self.assertGreater(separation, self.ship.radius + self.target.radius - 0.01)

    def test_large_dt_moving_target_sweep_is_safe_when_target_integrates_first(self):
        """The same sweep with the target integrating first (see the note above)."""
        self.ship.data_id = 'imperial_cruiser'
        self.ship.radius = 90
        self.ship.pos = Vec3(0, 0, -166)
        self.target.alive = False
        self.target = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3())
        self.target.order_type = 'move'
        self.target.order_target_pos = Vec3(0, 0, -2000)
        self.target.yaw = math.pi
        self.target.vel = Vec3(0, 0, -75)
        self.ship.order_target_id = self.ship.current_target = self.target.id
        self.st.time = 41.0 - (self.ship.id * 1.618) % 41.0
        self.st.entities = {self.target.id: self.target, self.ship.id: self.ship}
        self.gm.movement.update(10)
        separation = self.target.pos.z - self.ship.pos.z
        self.assertGreater(separation, self.ship.radius + self.target.radius - 0.01)

    def test_combat_approach_keeps_planet_gravity_well_redirect(self):
        self.gm.factory.spawn_planet({'id': 'obstacle', 'type': 'temperate',
                                     'pos': [0, 0, -600], 'radius': 300})
        self.gm.movement.update(2)
        self.assertGreater(abs(self.ship.yaw), .55,
                           'orbit guidance must not overwrite planet avoidance')


if __name__ == '__main__':
    unittest.main()
