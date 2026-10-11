"""Campaign objectives own outcomes; intact derelicts are not forces."""
import json
import unittest

from game.core.commands import PlayerCommand
from game.core.manager import GameManager
from game.core.state import GameState
from game.core.vectors import Vec3


def precise(st):
    return json.loads(json.dumps(st.to_dict(precise=True)))


def campaign(objectives, *, skirmish=False):
    mission = {'id': 'lifecycle', 'objectives': objectives}
    map_def = {'id': 'lifecycle', 'bounds': 26000, 'players': [
        {'slot': 0, 'team': 0, 'start': [-9000, 0, 0],
         'start_units': {'command_station': 1, 'cruiser': 1}},
        {'slot': 1, 'team': 1, 'is_ai': True, 'start': [9000, 0, 0],
         'start_units': {'command_station': 1, 'corvette': 1}}]}
    gm = (GameManager.start_skirmish(map_def) if skirmish
          else GameManager.start_mission(map_def, mission))
    # No pool personnel: abandoned bases cannot auto-recruit during the probe.
    for player in gm.state.players.values():
        player.crew = 0
        player.credits = 0
    return gm


class TestCampaignLifecycle(unittest.TestCase):
    def test_restore_discards_snapshot_and_precise_hash_matches_live_mission(self):
        from game.net.lan import precise_checksum
        gm = GameManager(mission_def={'id': 'hash-probe', 'objectives': [
            {'type': 'survive_time', 'time': 3.}]})
        restored = GameManager(GameState.from_dict(precise(gm.state)))
        self.assertEqual(precise_checksum(restored), precise_checksum(gm))
        self.assertIsNone(restored.state.mission_state)
        for manager in (gm, restored):
            manager.step(1 / 30)
        self.assertEqual(precise_checksum(restored), precise_checksum(gm))
        self.assertEqual(precise(restored.state)['mission_state'], restored.mission.to_dict())

    def test_first_tick_escort_events_survive_restore(self):
        for outcome in ('arrival', 'raid'):
            with self.subTest(outcome=outcome):
                gm = campaign([{'type': 'escort_convoy'}])
                src, dest = [gm.factory.spawn_station('trade_station', 0, Vec3(-6000, 0, z))
                             for z in (0, 1800)]
                convoy = gm.trading._make_convoy(src, dest, 150., 250.)
                if outcome == 'arrival':
                    convoy.pos = dest.pos.copy()
                restored = GameManager(GameState.from_dict(precise(gm.state)))
                for manager in (gm, restored):
                    events = []
                    manager.state.events.subscribe('mission_complete', lambda ev: events.append('complete'))
                    manager.state.events.subscribe('mission_failed', lambda ev: events.append('failed'))
                    if outcome == 'raid':
                        target = manager.state.entity(convoy.id)
                        manager.state.damage_queue.append(dict(
                            attacker_id=1, attacker_entity=None, target=target,
                            damage=10**9, shield_mult=1., armor_mult=1.,
                            system_mult=1., weapon=None, impact_pos=target.pos.copy()))
                    manager.step(1 / 30)
                    self.assertEqual(manager.mission.completed, outcome == 'arrival')
                    self.assertEqual(manager.mission.failed, outcome == 'raid')
                    self.assertEqual(events, ['complete' if outcome == 'arrival' else 'failed'])
                self.assertEqual(precise(restored.state), precise(gm.state))

    def test_terminal_campaign_outcomes_restore_without_republishing(self):
        for outcome in ('complete', 'failed'):
            with self.subTest(outcome=outcome):
                gm = campaign([{'type': 'survive_time', 'time': 6.0}])
                gm.state.time = 6.0
                if outcome == 'failed':
                    for e in gm.state.entities.values():
                        if e.owner == 0:
                            e.crew = 0
                gm.step(1 / 30)
                snapshot = precise(gm.state)
                restored = GameManager(GameState.from_dict(snapshot))
                self.assertEqual(precise(restored.state), snapshot)
                self.assertEqual(restored.mission.completed, outcome == 'complete')
                self.assertEqual(restored.mission.failed, outcome == 'failed')
                events = []
                restored.state.events.subscribe('mission_complete', lambda ev: events.append('complete'))
                restored.state.events.subscribe('mission_failed', lambda ev: events.append('failed'))
                for _ in range(12):
                    gm.step(1 / 30)
                    restored.step(1 / 30)
                    self.assertEqual(precise(restored.state), precise(gm.state))
                self.assertEqual(events, [])

    def test_precise_restored_campaign_continues_partial_hold_without_command_center(self):
        gm = campaign([{'type': 'hold_point', 'pos': [0, 0, 0],
                       'radius': 100, 'duration': 2.123456789}])
        ship = next(e for e in gm.state.entities.values() if e.owner == 0 and e.is_ship)
        ship.pos = Vec3(.123456789, 0, .987654321)
        ship.order_type = 'hold'
        for e in gm.state.entities.values():
            if e.owner == 1 and e.is_station:
                e.crew = 0
        for _ in range(17):
            gm.step(1 / 30)
        snapshot = precise(gm.state)
        restored = GameManager(GameState.from_dict(snapshot))
        self.assertIsNotNone(restored.mission.mission)
        self.assertEqual(restored.mission.objectives, gm.mission.objectives)
        self.assertEqual(precise(restored.state), snapshot)
        for _ in range(90):
            gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(precise(restored.state), precise(gm.state))
            self.assertEqual(restored.mission.objectives, gm.mission.objectives)
            self.assertEqual(restored.mission.completed, gm.mission.completed)
            self.assertEqual(restored.mission.failed, gm.mission.failed)
        self.assertTrue(restored.mission.completed)
        self.assertFalse(restored.state.game_over)
        self.assertEqual(restored.state.tick, 107)

    def capture_command(self, gm, *, last_enemy=False):
        st = gm.state
        target = next(e for e in st.entities.values() if e.owner == 1 and e.is_station)
        source = next(e for e in st.entities.values() if e.owner == 0 and e.is_ship)
        if last_enemy:
            for e in list(st.entities.values()):
                if e.owner == 1 and e.id != target.id:
                    st.entities.pop(e.id)
        # A staffed target stays operational until capture; tiny combat attrition
        # isolates ownership transfer from the separately tested abandonment path.
        target.crew = 1
        target.shields = {q: 0.0 for q in target.shields}
        target.systems['shield_gen'].hp = 0
        target.systems['weapons'].hp = 0
        source.systems['weapons'].hp = 0
        source.pos = Vec3(target.pos.x - target.radius - source.radius - 30, 0, target.pos.z)
        gm.ds.rules['boarding']['combat_losses_per_second'] = .001
        captured = []
        st.events.subscribe('unit_captured', lambda ev: captured.append(ev.data['entity_id']))
        st.queue_command(PlayerCommand('board', 0, unit_ids=(source.id,), target_id=target.id))
        for _ in range(240):
            gm.step(1 / 30)
            if target.owner == 0:
                break
            self.assertFalse(st.game_over, 'capture must actually finish, not freeze mid-party')
        self.assertEqual(target.owner, 0)
        self.assertEqual(captured, [target.id])
        self.assertTrue(target.operational)
        return target

    def test_captured_command_with_remaining_enemy_force_does_not_end_round(self):
        for skirmish in (False, True):
            with self.subTest(skirmish=skirmish):
                gm = campaign([{'type': 'destroy_all_forces', 'team': 1}], skirmish=skirmish)
                self.capture_command(gm)
                for _ in range(60):
                    gm.step(1 / 30)
                self.assertFalse(gm.state.game_over)
                self.assertFalse(gm.mission.completed)
                self.assertFalse(gm.mission.failed)
                self.assertTrue(any(e.owner == 1 and e.operational for e in gm.state.entities.values()))

    def test_last_enemy_authoritative_capture_ends_skirmish_by_elimination(self):
        gm = campaign([], skirmish=True)
        self.capture_command(gm, last_enemy=True)
        for _ in range(31):
            gm.step(1 / 30)
        self.assertTrue(gm.state.game_over)
        self.assertEqual(gm.state.winner, 0)
        self.assertEqual(gm.state.game_over_reason, 'elimination')
        tick = gm.state.tick
        gm.step(1 / 30)
        self.assertEqual(gm.state.tick, tick)

    def test_last_enemy_authoritative_capture_completes_destroy_objective(self):
        gm = campaign([{'type': 'destroy_all_forces', 'team': 1}])
        self.capture_command(gm, last_enemy=True)
        self.assertTrue(gm.mission.completed)
        self.assertFalse(gm.mission.failed)
        self.assertFalse(gm.state.game_over)

    def test_force_loss_on_survival_deadline_is_failure_not_both_outcomes(self):
        gm = campaign([{'type': 'survive_time', 'time': 6.0}])
        gm.state.time = 5.99
        for e in gm.state.entities.values():
            if e.owner == 0:
                e.crew = 0
        outcomes = []
        gm.state.events.subscribe('mission_complete', lambda ev: outcomes.append('complete'))
        gm.state.events.subscribe('mission_failed', lambda ev: outcomes.append('failed'))
        gm.step(1 / 30)
        self.assertTrue(gm.mission.failed)
        self.assertFalse(gm.mission.completed)
        self.assertEqual(outcomes, ['failed'])

    def test_abandoned_human_force_fails_survival_after_grace(self):
        gm = campaign([{'type': 'survive_time', 'time': 30.0}])
        for e in gm.state.entities.values():
            if e.owner == 0:
                e.crew = 0
        for _ in range(180):
            gm.step(1 / 30)
        self.assertTrue(gm.mission.failed)
        self.assertFalse(gm.mission.completed)
        self.assertFalse(gm.state.game_over)
        self.assertTrue(any(e.alive and e.owner == 0
                            for e in gm.state.entities.values()))

    def test_abandoned_hull_cannot_hold_point_and_progress_drains(self):
        gm = campaign([{'type': 'hold_point', 'pos': [0, 0, 0],
                       'radius': 100, 'duration': 2.0}])
        ship = next(e for e in gm.state.entities.values()
                    if e.owner == 0 and e.is_ship)
        ship.pos = Vec3()
        ship.order_type = 'hold'
        for _ in range(15):
            gm.step(1 / 30)
        self.assertAlmostEqual(gm.mission.objectives[0]['held'], .5)
        ship.crew = 0
        for _ in range(90):
            gm.step(1 / 30)
        self.assertFalse(gm.mission.completed)
        self.assertEqual(gm.mission.objectives[0]['held'], 0)
        self.assertTrue(ship.alive)

    def test_destroy_all_forces_ignores_owned_abandoned_hulls(self):
        gm = campaign([{'type': 'destroy_all_forces', 'team': 1}])
        enemies = [e for e in gm.state.entities.values() if e.owner == 1]
        for e in enemies:
            e.crew = 0
        gm.step(1 / 30)
        self.assertTrue(gm.mission.completed)
        self.assertFalse(gm.state.game_over)
        self.assertTrue(all(e.alive and e.owner == 1 and not e.operational
                            for e in enemies))

    def test_abandoned_enemy_command_does_not_freeze_survival(self):
        gm = campaign([{'type': 'survive_time', 'time': 3.0}])
        command = next(e for e in gm.state.entities.values()
                       if e.owner == 1 and e.is_station)
        command.crew = 0
        for _ in range(120):
            gm.step(1 / 30)
        self.assertFalse(gm.state.game_over)
        self.assertEqual(gm.state.tick, 120)
        self.assertTrue(gm.mission.completed)
        self.assertFalse(gm.mission.failed)
        self.assertTrue(command.alive)
        self.assertTrue(any(e.operational and e.owner == 1 and e.is_ship
                            for e in gm.state.entities.values()))
