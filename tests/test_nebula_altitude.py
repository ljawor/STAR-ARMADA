"""Issue #76: a replay fighter is detected, but pursuit cannot change altitude."""
import json
import unittest
from helpers import make_game
from game.core.vectors import Vec3
from game.core.commands import AttackCommand, MoveCommand
from game.net.replay_validation import reconstruct


# Exact coordinates of fighter 28 / corvette 535 at tick 109825 in the user's
# match-403f1985031d4e199ef6cdb9cf434e8e (v0.11.0, matching content).
FIGHTER_POS = (11463.46860285947, 1884.7437345410965, 171.1095634896808)
PURSUER_POS = (11104.395418883423, 0.0, -162.7707522800506)


def altitude_scene():
    gm = make_game(ai=False)
    st = gm.state
    st.entities.clear()
    fighter = gm.factory.spawn_ship('imperial_tie_squadron', 1, Vec3(*FIGHTER_POS))
    fighter.order_type = 'move'
    fighter.order_target_pos = Vec3(FIGHTER_POS[0], 0, FIGHTER_POS[2])
    pursuer = gm.factory.spawn_ship('imperial_corvette', 0, Vec3(*PURSUER_POS))
    # Remote detection is present in the actual replay. This explicit observer
    # makes the minimized fixture detected without weakening any sensor rule.
    observer = gm.factory.spawn_station('sensor_station', 0,
                                       Vec3(FIGHTER_POS[0], 0, FIGHTER_POS[2]))
    st.grid.rebuild(st.entities)
    gm.visibility.update()
    st.queue_command(AttackCommand(0, [pursuer.id], fighter.id))
    return gm, fighter, pursuer, observer


class NebulaAltitudeTests(unittest.TestCase):
    def test_detected_replay_altitude_fighter_can_be_pursued_and_damaged(self):
        gm, fighter, pursuer, _ = altitude_scene()
        self.assertTrue(gm.state.can_see(0, fighter.id))
        hits = []
        gm.state.events.subscribe('projectile_hit', lambda event: hits.append(event))
        for _ in range(1800):
            gm.step(1/30)
            if not fighter.alive:
                break
        self.assertGreater(pursuer.pos.y, 100, 'pursuit never climbed toward detected fighter')
        self.assertTrue(hits, 'no physical projectile connected')
        self.assertLess(fighter.hull, 60, 'fighter remains undamaged')

    def test_vertical_move_reaches_destination_without_flattening_position(self):
        gm = make_game(ai=False)
        st = gm.state
        st.entities.clear()
        ship = gm.factory.spawn_ship('imperial_corvette', 0, Vec3(0, -1000, 0))
        gm.factory.spawn_station('command_station', 1, Vec3(10000, 0, 10000))
        st.queue_command(MoveCommand(0, [ship.id], Vec3(0, 300, 0)))
        for _ in range(900):
            gm.step(1/30)
        self.assertAlmostEqual(ship.pos.y, 300, delta=30)
        self.assertAlmostEqual(ship.pos.x, 0, delta=1e-6)
        self.assertAlmostEqual(ship.pos.z, 0, delta=1e-6)

    def test_directly_overhead_contact_can_enter_front_weapon_arc(self):
        gm, fighter, pursuer, _ = altitude_scene()
        pursuer.pos.set(Vec3(fighter.pos.x, 0, fighter.pos.z))
        fighter.order_type = 'hold'
        fighter.order_target_pos = None
        for _ in range(3600):
            gm.step(1/30)
            if not fighter.alive:
                break
        self.assertLess(fighter.hull, 60, 'pure vertical contact never enters a front weapon arc')

    def test_hidden_high_fighter_does_not_drive_vertical_pursuit(self):
        gm, fighter, pursuer, observer = altitude_scene()
        observer.alive = False
        gm.state.grid.rebuild(gm.state.entities)
        self.assertFalse(gm.state.can_see(0, fighter.id))
        gm.step(1/30)
        self.assertIsNone(pursuer.order_target_id)
        self.assertIsNone(pursuer.current_target)
        self.assertEqual(pursuer.pos.y, 0)

    def test_elevated_pursuit_preserves_speed_and_horizontal_nose_limits(self):
        from game.core import detmath as math
        from game.systems import stats
        gm, _, ship, _ = altitude_scene()
        for _ in range(120):
            gm.step(1/30)
            self.assertLessEqual(ship.vel.length(), stats.effective_speed(gm.state, ship) + 1e-9)
            self.assertAlmostEqual(ship.vel.x * math.cos(ship.yaw)
                                   - ship.vel.z * math.sin(ship.yaw), 0, delta=1e-9)

    def test_exact_mid_climb_json_restore_continuation(self):
        gm, _, _, _ = altitude_scene()
        for _ in range(75):
            gm.step(1/30)
        saved = json.loads(json.dumps(gm.state.to_dict(precise=True)))
        restored = reconstruct(saved)
        self.assertEqual(saved, json.loads(json.dumps(restored.state.to_dict(precise=True))))
        for tick in range(300):
            gm.step(1/30)
            restored.step(1/30)
            self.assertEqual(json.loads(json.dumps(gm.state.to_dict(precise=True))),
                             json.loads(json.dumps(restored.state.to_dict(precise=True))), tick)
