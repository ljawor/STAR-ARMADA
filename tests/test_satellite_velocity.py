"""#62: orbit kinematics must be visible to ballistic gunnery."""
import unittest

from helpers import make_game, run_for, queue_detected_human_attack
from game.core.commands import PlayerCommand
from game.core.vectors import Vec3

DT = 1 / 30


class SatelliteVelocityTests(unittest.TestCase):
    def fixture(self, kind):
        gm = make_game(ai=False)
        st = gm.state
        planet = next(e for e in st.entities.values() if e.data_id == 'temperate')
        planet.colonized_by = 0
        player = st.players[0]
        player.credits = player.materials = player.energy = player.crew = 100000
        self.assertTrue(gm.construction.start_satellite(planet.id, kind, 0))
        run_for(gm, 200)
        satellite = next(e for e in st.entities.values() if e.satellite_slot is not None)
        return gm, planet, satellite

    def test_orbital_velocity_matches_manager_displacement_for_both_roles(self):
        from game.systems.satellite_orbits import orbit_position
        for kind in ('defense_satellite', 'attack_satellite'):
            with self.subTest(kind=kind):
                gm, planet, satellite = self.fixture(kind)
                for _ in range(12):
                    before = satellite.pos.copy()
                    gm.step(DT)
                    self.assertGreater(satellite.pos.dist(before), 0)
                    self.assertLess((satellite.vel * DT).dist(satellite.pos - before), 1e-9)
                    expected = orbit_position(planet, satellite.radius,
                                              satellite.satellite_orbit_phase, satellite.satellite_slot)
                    self.assertEqual(satellite.pos.to_dict(True), expected.to_dict(True))

    def test_wrapped_phase_and_partially_blocked_tick_report_accepted_displacement(self):
        from game.systems.satellite_orbits import orbit_position
        from game.core import detmath as math
        gm, planet, satellite = self.fixture('defense_satellite')
        satellite.satellite_orbit_phase = 2 * math.pi - .001
        satellite.pos = orbit_position(planet, satellite.radius,
                                       satellite.satellite_orbit_phase, satellite.satellite_slot)
        before = satellite.pos.copy()
        gm.step(DT)
        self.assertLess(satellite.satellite_orbit_phase, .01)
        self.assertLess((satellite.vel * DT).dist(satellite.pos - before), 1e-9)
        obstacle = orbit_position(planet, satellite.radius,
                                 satellite.satellite_orbit_phase + .4, satellite.satellite_slot)
        gm.factory.spawn_station('mining_station', 0, obstacle)
        before, phase = satellite.pos.copy(), satellite.satellite_orbit_phase
        gm.step(10)
        self.assertGreater(satellite.pos.dist(before), 0)
        self.assertLess(satellite.satellite_orbit_phase - phase, .6)
        self.assertLess((satellite.vel * 10).dist(satellite.pos - before), 1e-9)
        before = satellite.pos.copy()
        gm.step(0)
        self.assertEqual(satellite.pos.to_dict(True), before.to_dict(True))
        self.assertEqual(satellite.vel.length(), 0)

    def test_missing_parent_clears_orbital_velocity(self):
        gm, planet, satellite = self.fixture('defense_satellite')
        gm.step(DT)
        self.assertGreater(satellite.vel.length(), 0)
        del gm.state.entities[planet.id]
        before = satellite.pos.copy()
        gm.step(DT)
        self.assertEqual(satellite.vel.length(), 0)
        self.assertEqual(satellite.pos.to_dict(True), before.to_dict(True))

    def test_frozen_engaged_blocked_and_abandoned_motion_resumes(self):
        for kind, enemy_kind in (('defense_satellite', 'imperial_tie_squadron'),
                                 ('attack_satellite', 'imperial_corvette')):
            with self.subTest(kind=kind):
                gm, planet, satellite = self.fixture(kind)
                gm.step(DT)
                self.assertGreater(satellite.vel.length(), 0)
                enemy = gm.factory.spawn_ship(enemy_kind, 1, satellite.pos + Vec3(300, 0, 0))
                enemy.order_type = 'hold'
                before, phase = satellite.pos.copy(), satellite.satellite_orbit_phase
                gm.step(DT)
                self.assertEqual(satellite.current_target, enemy.id)
                self.assertEqual(satellite.vel.length(), 0)
                self.assertEqual(satellite.pos.to_dict(True), before.to_dict(True))
                self.assertEqual(satellite.satellite_orbit_phase, phase)
                enemy.pos = planet.pos + Vec3(7000, 0, 7000)
                gm.step(DT)
                self.assertGreater(satellite.vel.length(), 0)
                crew = satellite.crew
                satellite.crew = 0
                before = satellite.pos.copy()
                gm.step(DT)
                self.assertEqual(satellite.vel.length(), 0)
                self.assertEqual(satellite.pos.to_dict(True), before.to_dict(True))
                satellite.crew = crew
                gm.step(DT)
                self.assertGreater(satellite.vel.length(), 0)
                blocker = gm.factory.spawn_station('mining_station', 0, satellite.pos.copy())
                before = satellite.pos.copy()
                gm.step(DT)
                self.assertEqual(satellite.vel.length(), 0)
                self.assertEqual(satellite.pos.to_dict(True), before.to_dict(True))
                blocker.pos = planet.pos + Vec3(7000, 0, -7000)
                gm.step(DT)
                self.assertGreater(satellite.vel.length(), 0)

    def test_precise_save_and_replay_continue_moving_satellite_under_fire(self):
        import json
        from game.core.manager import GameManager
        from game.core.state import GameState
        from game.net.replay import ReplayRecorder, ReplayPlayer, state_checksum
        gm, planet, satellite = self.fixture('defense_satellite')
        attacker = gm.factory.spawn_ship('imperial_cruiser', 1, satellite.pos + Vec3(1500, 0, 0))
        attacker.sensor_range = 20000
        gm.state.queue_command(PlayerCommand('attack', 1, unit_ids=(attacker.id,), target_id=satellite.id))
        run_for(gm, 2)
        self.assertGreater(satellite.vel.length(), 0)
        self.assertTrue(any(p.target_id == satellite.id for p in gm.state.projectiles.values()))
        def snapshot(manager):
            return json.loads(json.dumps(manager.state.to_dict(precise=True)))
        recorder = ReplayRecorder(gm.state)
        scheduled = {
            gm.state.tick + 30: PlayerCommand('stop', 1, unit_ids=(attacker.id,)),
            gm.state.tick + 60: PlayerCommand('attack', 1, unit_ids=(attacker.id,), target_id=satellite.id),
        }
        for tick, cmd in scheduled.items():
            recorder.on_command(cmd, tick)
        replay = ReplayPlayer(json.loads(json.dumps(recorder.to_dict())))
        saved = GameManager(GameState.from_dict(snapshot(gm)))
        played = GameManager(GameState.from_dict(replay.data['initial_state']))
        for other in (saved, played):
            self.assertEqual(snapshot(gm), snapshot(other))
        hits = []
        gm.state.events.subscribe('projectile_hit', lambda ev: hits.append(ev.data['target_id']))
        for _ in range(120):
            cmd = scheduled.get(gm.state.tick + 1)
            if cmd is not None:
                gm.state.queue_command(cmd)
                saved.state.queue_command(cmd)
            for cmd in replay.commands_for_tick(played.state.tick + 1):
                played.state.queue_command(cmd)
            for manager in (gm, saved, played):
                manager.step(DT)
            for other in (saved, played):
                self.assertEqual(snapshot(gm), snapshot(other))
                self.assertEqual(state_checksum(gm.state), state_checksum(other.state))
        self.assertIn(satellite.id, hits)
        self.assertFalse(gm.state.game_over)

    def test_cruiser_hits_and_kills_both_satellite_roles_without_defense_retaliation(self):
        for kind in ('defense_satellite', 'attack_satellite'):
            with self.subTest(kind=kind):
                gm, planet, satellite = self.fixture(kind)
                st = gm.state
                attacker = gm.factory.spawn_ship('imperial_cruiser', 1,
                                                satellite.pos + Vec3(1500, 0, 0))
                attacker.sensor_range = 20000
                counts = dict(shots=0, hits=0, retaliation=0)
                launched = set()
                def fired(event):
                    if event.data['attacker_id'] == attacker.id:
                        launched.update(p.id for p in st.projectiles.values()
                                        if p.attacker_entity_id == attacker.id)
                        counts['shots'] = len(launched)
                    if event.data['attacker_id'] == satellite.id:
                        counts['retaliation'] += 1
                def hit(event):
                    if event.data['target_id'] == satellite.id:
                        counts['hits'] += 1
                st.events.subscribe('weapon_fired', fired)
                st.events.subscribe('projectile_hit', hit)
                st.queue_command(PlayerCommand('attack', 1, unit_ids=(attacker.id,), target_id=satellite.id))
                start = st.tick
                reattacked = False
                for _ in range(9000):
                    gm.step(DT)
                    if not satellite.alive:
                        break
                    if not satellite.operational and not reattacked:
                        self.assertIsNone(attacker.current_target)
                        self.assertFalse(planet.satellite_locks)
                        queue_detected_human_attack(gm, 1, [attacker.id], satellite.id)
                        reattacked = True
                elapsed = (st.tick - start) * DT
                print(f'SATELLITE_COMBAT {kind} shots={counts["shots"]} hits={counts["hits"]} '
                      f'kills={st.stats.get("1", {}).get("kills", 0)} elapsed={elapsed:.3f} '
                      f'retaliation={counts["retaliation"]}', flush=True)
                self.assertFalse(st.game_over)
                if kind == 'defense_satellite':
                    self.assertEqual(counts['retaliation'], 0)
                    self.assertIsNone(satellite.current_target)
                self.assertGreater(counts['hits'], 0)
                self.assertTrue(reattacked)
                self.assertFalse(satellite.alive)
                self.assertNotIn(satellite.id, st.entities)
                self.assertEqual(st.stats['1']['kills'], 1)
                self.assertGreater(planet.satellite_locks[satellite.satellite_slot], st.time)


if __name__ == '__main__':
    unittest.main()
