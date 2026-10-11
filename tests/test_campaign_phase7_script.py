"""Deterministic campaign scripts through the real manager pipeline."""
import json
import unittest
from game.core.manager import GameManager
from game.core.state import GameState
from game.core.commands import PlayerCommand
from game.net.replay import ReplayRecorder, ReplayPlayer
from test_campaign_lifecycle import campaign, precise


class TestCampaignScript(unittest.TestCase):
    def test_staged_objective_trigger_and_event_latch_restore(self):
        definition = {'id': 'stages', 'objectives': [
            {'id': 'first', 'type': 'survive_time', 'time': .05},
            {'id': 'second', 'type': 'survive_time', 'time': .1, 'active': False}],
            'triggers': [
                {'id': 'activate', 'when': {'objective': 'first'}, 'actions': [
                    {'type': 'activate_objective', 'objective': 'second'}]},
                {'id': 'arrival', 'when': {'event': 'jump_complete', 'match': {'owner': 0},
                                         'time': .2}, 'actions': [
                    {'type': 'reinforcements', 'units': [
                        {'ship': 'imperial_corvette', 'owner': 0, 'pos': [-5000, 0, 3000]}]}]}]}
        gm = campaign([{'type': 'survive_time', 'time': 50}])
        gm = GameManager(gm.state, mission_def=definition)
        gm.step(1 / 30)
        self.assertFalse(gm.mission.objectives[1].get('done'))
        gm.state.events.publish('jump_complete', owner=0)
        restored = GameManager(GameState.from_dict(precise(gm.state)))
        self.assertEqual(precise(gm.state), precise(restored.state))
        for _ in range(10):
            for manager in (gm, restored):
                manager.step(1 / 30)
            self.assertEqual(precise(gm.state), precise(restored.state))
        self.assertTrue(gm.mission.objectives[1]['active'])
        self.assertTrue(gm.mission.completed)
        self.assertEqual(gm.mission.to_dict()['script']['fired'], ['activate', 'arrival'])

    def test_failure_precedes_success_trigger_and_terminal_events_do_not_mutate(self):
        gm = campaign([{'id': 'wait', 'type': 'survive_time', 'time': 50}])
        definition = dict(gm.mission.mission, triggers=[
            {'id': 'success', 'when': {'tick': 1}, 'actions': [
                {'type': 'complete_objective', 'objective': 'wait'}]},
            {'id': 'loss', 'when': {'tick': 1}, 'actions': [{'type': 'fail_mission'}]}])
        gm = GameManager(gm.state, mission_def=definition)
        events = []
        gm.state.events.subscribe('mission_failed', lambda ev: events.append('failed'))
        gm.state.events.subscribe('mission_complete', lambda ev: events.append('complete'))
        gm.step(1 / 30)
        self.assertTrue(gm.mission.failed)
        self.assertFalse(gm.mission.completed)
        self.assertEqual(events, ['failed'])
        mission = gm.mission.to_dict()
        gm.state.events.publish('ship_built', owner=0, ship='imperial_corvette')
        gm.step(1 / 30)
        self.assertEqual(gm.mission.to_dict(), mission)
        self.assertEqual(events, ['failed'])

    def test_authoritative_board_and_transport_delivery_complete_tutorial_objectives(self):
        from game.core.vectors import Vec3
        gm = campaign([{'id': 'capture', 'type': 'capture_unit', 'ship': 'syndicate_corvette'},
                       {'id': 'recovery', 'type': 'recover_crew', 'ship': 'imperial_frigate', 'count': 4}])
        source = next(e for e in gm.player_entities(0) if e.is_ship)
        target = gm.factory.spawn_ship('syndicate_corvette', 1, Vec3(-7000, 0, 2000))
        target.crew = 0
        target.systems['shield_gen'].hp = 0
        target.shields = {q: 0.0 for q in target.shields}
        source.pos = Vec3(-7000, 0, 1800)
        source.systems['weapons'].hp = 0
        transport = gm.factory.spawn_ship('imperial_crew_transport', 0, Vec3(-9000, 0, 400))
        gm.state.players[0].crew = 100
        gm.state.players[0].credits = 1000
        gm.state.queue_command(PlayerCommand('crew_load', 0, unit_ids=(transport.id,)))
        gm.state.queue_command(PlayerCommand('board', 0, unit_ids=(source.id,), target_id=target.id))
        gm.visibility.update()
        for _ in range(240):
            gm.step(1 / 30)
        self.assertGreaterEqual(transport.crew_cargo, 4)
        self.assertEqual(target.owner, 0)
        self.assertTrue(gm.mission.objectives[0]['done'])
        self.assertFalse(gm.mission.objectives[1]['done'])
        recovered = gm.factory.spawn_ship('imperial_frigate', 0, Vec3(-5000, 0, 3000))
        recovered.crew = 0
        transport.pos = Vec3(-5000, 0, 3100)
        gm.state.queue_command(PlayerCommand('crew_deliver', 0, unit_ids=(transport.id,), target_id=recovered.id))
        gm.step(1 / 30)
        saved = precise(gm.state)
        restored = GameManager(GameState.from_dict(saved))
        self.assertEqual(precise(restored.state), saved)
        for _ in range(90):
            for manager in (gm, restored):
                manager.step(1 / 30)
            self.assertEqual(precise(restored.state), precise(gm.state))
        self.assertGreaterEqual(recovered.crew, 4)
        self.assertTrue(gm.mission.objectives[1]['done'])
        self.assertTrue(gm.mission.completed)

    def test_script_catalogue_rejects_unknown_units_bad_timers_and_references(self):
        gm = campaign([{'type': 'survive_time', 'time': 50}])
        from copy import deepcopy
        valid = {'id': 'validation', 'objectives': [{'id': 'wait', 'type': 'survive_time', 'time': 5}],
                 'triggers': [{'id': 'wave', 'when': {'tick': 2}, 'actions': [
                     {'type': 'reinforcements', 'units': [{'ship': 'missing', 'owner': 1, 'pos': [0, 0, 0]}]}]}]}
        gm.ds.campaign = {'missions': [valid]}
        with self.assertRaises(ValueError):
            gm.ds._validate()
        valid['triggers'][0]['actions'][0]['units'][0]['ship'] = 'syndicate_corvette'
        for field, value in [('tick', True), ('time', float('nan')), ('objective', 'missing')]:
            bad = deepcopy(valid)
            bad['triggers'][0]['when'] = {field: value}
            gm.ds.campaign = {'missions': [bad]}
            with self.assertRaises(ValueError, msg=field):
                gm.ds._validate()
        gm.ds.campaign = {'missions': [valid]}
        gm.ds._validate()

    def test_builtin_recovery_drill_runs_real_orders_and_staged_content(self):
        from game.data.store import DataStore
        from game.core.vectors import Vec3
        ds = DataStore.get()
        definition = next((m for m in ds.campaign['missions'] if m['id'] == 'm00_recovery_drill'), None)
        self.assertIsNotNone(definition, 'catalogue must expose the actual tutorial mission')
        gm = GameManager.start_mission(ds.maps['skirmish01'], definition)
        gm.step(1 / 30)
        transport = next(e for e in gm.player_entities(0) if e.data_id == 'imperial_crew_transport')
        cruiser = next(e for e in gm.player_entities(0) if e.data_id == 'imperial_cruiser')
        target = next(e for e in gm.player_entities(1) if e.data_id == 'syndicate_corvette')
        frigate = next(e for e in gm.player_entities(0) if e.data_id == 'imperial_frigate')
        self.assertEqual((frigate.crew, target.crew), (0, 0))
        # Bounded headless objective probe: isolate the real orders, not navigation/balance acceptance.
        base = next(e for e in gm.player_entities(0) if e.data_id == 'command_station')
        transport.pos = Vec3(base.pos.x, 0, base.pos.z + 400)
        cruiser.pos = Vec3(target.pos.x, 0, target.pos.z - 200)
        cruiser.systems['weapons'].hp = 0
        gm.state.queue_command(PlayerCommand('crew_load', 0, unit_ids=(transport.id,)))
        gm.state.queue_command(PlayerCommand('board', 0, unit_ids=(cruiser.id,), target_id=target.id))
        gm.visibility.update()
        capture_replay = ReplayPlayer(json.loads(json.dumps(ReplayRecorder(gm.state).to_dict())))
        replayed_capture = GameManager(GameState.from_dict(capture_replay.data['initial_state']))
        self.assertEqual(precise(replayed_capture.state), precise(gm.state))
        for _ in range(240):
            gm.step(1 / 30)
            replayed_capture.step(1 / 30)
            self.assertEqual(precise(replayed_capture.state), precise(gm.state))
        self.assertEqual(target.owner, 0)
        recovery = next(o for o in gm.mission.objectives if o['id'] == 'recover')
        self.assertTrue(recovery['active'])
        transport.pos = Vec3(frigate.pos.x, 0, frigate.pos.z + 100)
        gm.state.queue_command(PlayerCommand('crew_deliver', 0, unit_ids=(transport.id,), target_id=frigate.id))
        gm.visibility.update()
        recorder = ReplayRecorder(gm.state)
        # Pending intent is part of the precise initial snapshot.
        restored = GameManager(GameState.from_dict(json.loads(json.dumps(recorder.to_dict()['initial_state']))))
        self.assertEqual(precise(restored.state), precise(gm.state))
        for _ in range(90):
            gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(precise(restored.state), precise(gm.state))
        self.assertTrue(gm.mission.completed)
        self.assertTrue(recovery['done'])
        self.assertGreaterEqual(frigate.crew, 4)

    def test_first_and_supplyline_content_have_real_production_and_friendly_markets(self):
        from game.data.store import DataStore
        ds = DataStore.get()
        first = next(m for m in ds.campaign['missions'] if m['id'] == 'm01_first_fleet')
        self.assertEqual(first['loadout']['start_units'].get('shipyard'), 1)
        self.assertIn('two corvettes', first['briefing'])
        supply = next(m for m in ds.campaign['missions'] if m['id'] == 'm02_supply_line')
        gm = GameManager.start_mission(ds.maps[supply['map']], supply)
        own_markets = [e for e in gm.player_entities(0) if e.data_id == 'trade_station']
        self.assertEqual(len(own_markets), 1)
        self.assertIn('second trade station', supply['briefing'])

    def test_builtin_rebel_hunt_has_two_timed_waves_and_delayed_clearance(self):
        from game.data.store import DataStore
        ds = DataStore.get()
        definition = next(m for m in ds.campaign['missions'] if m['id'] == 'm06_rebel_hunt')
        self.assertEqual(len(definition.get('triggers', [])), 2)
        gm = GameManager.start_mission(ds.maps[definition['map']], definition)
        clearance = next(o for o in gm.mission.objectives if o['type'] == 'destroy_all_forces')
        self.assertFalse(clearance['active'])
        gm.state.time = 59.99
        gm.step(1 / 30)
        self.assertEqual(len(gm.mission.to_dict()['script']['spawned']['counterstrike_1']), 2)
        gm.state.time = 119.99
        gm.step(1 / 30)
        self.assertTrue(clearance['active'])
        self.assertEqual(len(gm.mission.to_dict()['script']['spawned']['counterstrike_2']), 3)

    def test_staged_escort_subscribes_before_first_active_trading_tick(self):
        gm = campaign([{'id': 'escort', 'type': 'escort_convoy', 'active': False}])
        definition = dict(gm.mission.mission, triggers=[{'id': 'enable', 'when': {'tick': 1},
            'actions': [{'type': 'activate_objective', 'objective': 'escort'}]}])
        gm = GameManager(gm.state, mission_def=definition)
        gm.step(1 / 30)
        from game.core.vectors import Vec3
        src, dest = [gm.factory.spawn_station('trade_station', 0, Vec3(-6000, 0, z)) for z in (0, 1800)]
        convoy = gm.trading._make_convoy(src, dest, 150., 250.)
        convoy.pos = dest.pos.copy()
        gm.step(1 / 30)
        self.assertTrue(gm.mission.completed)

    def test_raid_failure_cannot_be_overwritten_by_objective_completion_trigger(self):
        from game.core.vectors import Vec3
        gm = campaign([{'id': 'escort', 'type': 'escort_convoy'}])
        definition = dict(gm.mission.mission, triggers=[{'id': 'deadline', 'when': {'tick': 1},
            'actions': [{'type': 'complete_objective', 'objective': 'escort'}]}])
        gm = GameManager(gm.state, mission_def=definition)
        src, dest = [gm.factory.spawn_station('trade_station', 0, Vec3(-6000, 0, z)) for z in (0, 1800)]
        convoy = gm.trading._make_convoy(src, dest, 150., 250.)
        gm.state.damage_queue.append(dict(attacker_id=1, attacker_entity=None, target=convoy,
            damage=10**9, shield_mult=1., armor_mult=1., system_mult=1., weapon=None,
            impact_pos=convoy.pos.copy()))
        gm.step(1 / 30)
        self.assertTrue(gm.mission.failed)
        self.assertFalse(gm.mission.completed)
        self.assertEqual(gm.mission.to_dict()['script']['fired'], [])

    def test_timed_wave_restores_precisely_and_fires_once_in_replay(self):
        gm = campaign([{'id': 'wait', 'type': 'survive_time', 'time': 50}])
        definition = dict(gm.mission.mission, triggers=[{
            'id': 'wave', 'when': {'tick': 5}, 'actions': [{'type': 'reinforcements',
                'units': [{'ship': 'syndicate_corvette', 'owner': 1,
                           'pos': [7000.123456789, 0, 3000.987654321]}]}]}])
        gm = GameManager(gm.state, mission_def=definition)
        for _ in range(3):
            gm.step(1 / 30)
        recorder = ReplayRecorder(gm.state)
        restored = GameManager(GameState.from_dict(precise(gm.state)))
        replay = ReplayPlayer(json.loads(json.dumps(recorder.to_dict())))
        replayed = GameManager(GameState.from_dict(replay.data['initial_state']))
        self.assertEqual(precise(gm.state), precise(restored.state))
        before = len(gm.state.entities)
        for _ in range(10):
            cmd = PlayerCommand('hold', 0, unit_ids=tuple(e.id for e in gm.player_entities(0)))
            recorder.on_command(cmd, gm.state.tick + 1)
            for manager in (gm, restored):
                manager.state.queue_command(cmd)
            # Rebuild the command reader to include commands just recorded.
            replay = ReplayPlayer(json.loads(json.dumps(recorder.to_dict())))
            for c in replay.commands_for_tick(replayed.state.tick + 1):
                replayed.state.queue_command(c)
            for manager in (gm, restored, replayed):
                manager.step(1 / 30)
            self.assertEqual(precise(gm.state), precise(restored.state))
            self.assertEqual(precise(gm.state), precise(replayed.state))
        self.assertEqual(len(gm.state.entities), before + 1)
        self.assertIn('wave', gm.mission.to_dict()['script']['fired'])
        self.assertEqual(len(gm.mission.to_dict()['script']['spawned']['wave']), 1)
