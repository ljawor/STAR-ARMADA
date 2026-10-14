"""Player-facing replay vertical slices; full precision, not coarse checksums."""
import os
from unittest.mock import patch
import json
import tempfile
import unittest
from pathlib import Path
from game.core.commands import PlayerCommand
from game.core.manager import GameManager
from game.core.state import GameState
from game.data.store import DataStore
from game.net import replay


def precise(state):
    return json.loads(json.dumps(state.to_dict(precise=True)))


def game():
    return GameManager.start_skirmish(DataStore.get().maps['skirmish01'])


class ReplayWorkflowTests(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        # `render.menus` freezes its persistence paths at import, so a temporary USER_DIR
        # does not move SETTINGS_PATH: pin the settings file itself, or this menu draws in
        # whatever language the developer's own game last saved.
        scope = patch('render.menus.SETTINGS_PATH',
                      os.path.join(holder.name, 'settings.json'))
        scope.start()
        self.addCleanup(scope.stop)

    def test_record_consumed_commands_once_and_precise_every_tick(self):
        self.assertTrue(hasattr(replay, 'MatchRecording'), 'consumed-tick recording missing')
        gm = game()
        own = next(e.id for e in gm.state.entities.values() if e.owner == 0 and e.is_ship)
        # Initial pending command must be restored, never injected twice.
        gm.state.queue_command(PlayerCommand('move', 0, unit_ids=(own,), target_pos=(1.125, 0., 200.25)))
        rec = replay.MatchRecording(gm, mode='skirmish')
        expected = []
        for tick in range(65):
            if tick == 4:
                gm.state.queue_command(PlayerCommand('stop', 0, unit_ids=(own,)))
            if tick == 7:
                # LAN accepted frames append directly, bypassing queue_command.
                gm.state.command_queue.append(PlayerCommand('hold', 0, unit_ids=(own,)))
            gm.step(1/30)
            expected.append(precise(gm.state))
        data = rec.to_dict()
        self.assertEqual([(e['tick'], e['cmd']['type']) for e in data['commands']], [(4, 'stop'), (7, 'hold')])
        self.assertEqual(data['end_tick'], 65)
        self.assertEqual(data['version'], 2)
        self.assertTrue(data['content_digest'])
        playback = replay.PlaybackSession(data)
        for snapshot in expected:
            playback.step()
            self.assertEqual(precise(playback.gm.state), snapshot)
        self.assertTrue(playback.ended)
        playback.step()
        self.assertEqual(precise(playback.gm.state), expected[-1])


    def test_validation_bounds_compatibility_and_legacy_tail(self):
        self.assertTrue(hasattr(replay, 'validate_replay'), 'bounded replay validation missing')
        from copy import deepcopy
        gm = game()
        rec = replay.MatchRecording(gm)
        for _ in range(3):
            gm.step(1/30)
        good = rec.to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'match.json'
            rec.save(path)
            self.assertEqual(replay.load_replay(path)['end_tick'], 3)
            path.write_text('{bad')
            with self.assertRaisesRegex(ValueError, 'JSON'):
                replay.load_replay(path)
        for field, value in [('version', 999), ('end_tick', -1), ('tick_rate', 60),
                             ('content_digest', 'different'), ('game_version', 'other'),
                             ('initial_state', []), ('mods', ['../bad']), ('duration_seconds', -1)]:
            bad = deepcopy(good)
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                replay.PlaybackSession(bad)
        for cmd in [{'type': 'unknown', 'player': 0}, {'type': 'move', 'player': 0, 'target_pos': [float('nan'), 0, 0]},
                    {'type': 'stop', 'player': 99}, {'type': 'stop', 'player': 0, 'unit_ids': 'oops'}]:
            bad = deepcopy(good)
            bad['commands'] = [{'tick': 0, 'cmd': cmd}]
            with self.subTest(cmd=cmd), self.assertRaises(ValueError):
                replay.validate_replay(bad)
        legacy = replay.ReplayRecorder(gm.state).to_dict()
        migrated = replay.validate_replay(legacy)
        self.assertIn('duration', migrated['compatibility_warning'])
        self.assertEqual(migrated['end_tick'], gm.state.tick)
        self.assertTrue(replay.PlaybackSession(migrated).ended)
        bad = deepcopy(legacy)
        bad['initial_state']['command_queue'] = [{'type': 'stop', 'player': 0}]
        with self.assertRaisesRegex(ValueError, 'pending'):
            replay.validate_replay(bad)


    def test_main_playback_is_read_only_pauses_speeds_and_stops_at_end(self):
        import pygame
        from test_lan_main import factories
        from unittest.mock import Mock
        gm = game()
        rec = replay.MatchRecording(gm)
        for _ in range(12):
            gm.step(1/30)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'match.json'
            rec.save(path)
            ns = factories()
            self.assertIn('replay_path', __import__('inspect').signature(ns['start_game']).parameters,
                          'main has no playback path')
            from render.camera import Camera
            ns.update(pygame=pygame, mission_def=None, Camera=Camera)
            ns['start_game'](replay_path=str(path))
            self.assertIsNone(ns.get('recording'))
            self.assertIsNotNone(ns.get('playback'))
            before = precise(ns['state'])
            for key in (pygame.K_s, pygame.K_BACKSPACE, pygame.K_j, pygame.K_b,
                        pygame.K_F5, pygame.K_F9, pygame.K_g):
                ns['handle_game_input'](pygame.event.Event(pygame.KEYDOWN, key=key))
            for button in (1, 3):
                for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                    ns['handle_game_input'](pygame.event.Event(kind, button=button, pos=(400, 400)))
            self.assertEqual(precise(ns['state']), before)
            ns['handle_game_input'](pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p))
            ns['advance_simulation'](.2)
            self.assertEqual(precise(ns['state']), before)
            ns['handle_game_input'](pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p))
            ns['handle_game_input'](pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHTBRACKET))
            ns['advance_simulation'](.1)
            self.assertEqual(ns['state'].tick, 6)
            ns['advance_simulation'](.2)
            self.assertEqual(ns['state'].tick, 12)
            self.assertTrue(ns['playback'].ended)
            final = precise(ns['state'])
            ns['advance_simulation'](.2)
            self.assertEqual(precise(ns['state']), final)
            self.assertEqual(json.loads(path.read_text()), json.loads(json.dumps(rec.to_dict())))


    def test_menu_browse_paging_errors_and_single_activation(self):
        import pygame
        from render.menus import MenuStack, MenuResult
        from unittest.mock import patch
        self.assertTrue(hasattr(MenuResult, 'START_REPLAY'), 'replay browser missing')
        gm = game()
        rec = replay.MatchRecording(gm)
        gm.step(1/30)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'replays'
            folder.mkdir()
            for i in range(15):
                rec.save(folder / f'match-{i:02d}.json')
            (folder / 'broken.json').write_text('{oops')
            with patch('render.menus.USER_DIR', str(root)):
                menu = MenuStack(1024, 768)
                menu.open_replays()
                seen = set()
                for page in range(3):
                    menu.render(0.)
                    entries = [b for b in menu.buttons if b['action'] == 'select_replay']
                    self.assertLessEqual(len(entries), 6)
                    seen.update(Path(b['payload']).name for b in entries)
                    if page < 2:
                        nxt = next(b for b in menu.buttons if b['action'] == 'replay_page' and b['payload'] == 1)
                        menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=nxt['rect'].center))
                self.assertEqual(seen, {p.name for p in folder.iterdir()})
                menu.open_replays()
                menu.render(0.)
                broken = next(b for b in menu.buttons if Path(b.get('payload') or '').name == 'broken.json')
                menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=broken['rect'].center))
                self.assertEqual(menu.result, MenuResult.NONE)
                menu.render(0.)
                play = next(b for b in menu.buttons if b['action'] == 'play_replay')
                menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=play['rect'].center))
                self.assertIn('JSON', menu.replay_notice)
                valid = next(b for b in menu.buttons if b['action'] == 'select_replay' and b['payload'] != broken['payload'])
                menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=valid['rect'].center))
                menu.render(0.)
                play = next(b for b in menu.buttons if b['action'] == 'play_replay')
                menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=play['rect'].center))
                self.assertEqual(menu.result, MenuResult.START_REPLAY)
                self.assertEqual(menu.result_payload, valid['payload'])
                self.assertEqual(menu.buttons, [])
                menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=valid['rect'].center))
                self.assertEqual(menu.result_payload, valid['payload'])


    def test_scripted_campaign_partial_restore_replays_precisely_every_tick(self):
        from test_campaign_lifecycle import campaign
        gm = campaign([{'id': 'first', 'type': 'survive_time', 'time': .3},
                       {'id': 'second', 'type': 'survive_time', 'time': .8, 'active': False}])
        definition = dict(gm.mission.mission, triggers=[
            {'id': 'activate', 'when': {'objective': 'first'}, 'actions': [
                {'type': 'activate_objective', 'objective': 'second'}]},
            {'id': 'wave', 'when': {'tick': 15}, 'actions': [
                {'type': 'reinforcements', 'units': [
                    {'ship': 'imperial_corvette', 'owner': 0, 'pos': [-5000, 0, 3000]}]}]}])
        gm = GameManager(gm.state, mission_def=definition)
        for _ in range(4):
            gm.step(1/30)
        recorder = replay.MatchRecording(gm, mode='campaign')
        snapshots = []
        ship = next(e.id for e in gm.state.entities.values() if e.owner == 0 and e.is_ship)
        for index in range(40):
            if index == 3:
                gm.state.queue_command(PlayerCommand('hold', 0, unit_ids=(ship,)))
            gm.step(1/30)
            snapshots.append(precise(gm.state))
        player = replay.PlaybackSession(recorder.to_dict())
        for snapshot in snapshots:
            self.assertTrue(player.step())
            self.assertEqual(precise(player.gm.state), snapshot)
        self.assertTrue(player.ended)
        self.assertTrue(player.gm.mission.completed)
        self.assertEqual(player.gm.mission.to_dict()['script']['fired'], ['activate', 'wave'])

    def test_real_lan_accepted_humans_record_once_at_consumed_tick(self):
        import time
        from test_lan import SimulationTests
        from test_lan_main import factories
        host, client = SimulationTests().sessions()
        self.addCleanup(host.close)
        self.addCleanup(client.close)
        graphs = []
        for session in (host, client):
            ns = factories()
            ns.update(mission_def=None)
            ns['start_game'](lan_session=session)
            graphs.append(ns)
        for pid, ns in enumerate(graphs):
            own = next(e.id for e in ns['state'].entities.values() if e.owner == pid and e.is_ship)
            ns['state'].queue_command(PlayerCommand('hold', pid, unit_ids=(own,)))
            self.assertEqual(ns['recording'].to_dict()['commands'], [])
        snapshots = [{}, {}]
        deadline = time.monotonic() + 5
        while min(ns['state'].tick for ns in graphs) < 40 and time.monotonic() < deadline:
            for index, ns in enumerate(graphs):
                if ns['state'].tick >= 40:
                    continue
                before = ns['state'].tick
                ns['advance_simulation'](1/30)
                if ns['state'].tick > before:
                    snapshots[index][ns['state'].tick] = precise(ns['state'])
        self.assertEqual([ns['state'].tick for ns in graphs], [40, 40])
        self.assertEqual(snapshots[0], snapshots[1])
        for index, ns in enumerate(graphs):
            data = ns['recording'].to_dict()
            self.assertEqual(len(data['commands']), 2)
            self.assertEqual([e['cmd']['player'] for e in data['commands']], [0, 1])
            self.assertGreater(data['commands'][0]['tick'], 0)
            player = replay.PlaybackSession(data)
            for tick in sorted(snapshots[index]):
                player.step()
                self.assertEqual(precise(player.gm.state), snapshots[index][tick])

    def test_metadata_atomic_save_limits_and_nonfatal_failure_notice(self):
        from unittest.mock import patch
        from test_lan_main import factories
        gm = game()
        recorder = replay.MatchRecording(gm)
        gm.step(1/30)
        self.assertIn('duration_seconds', recorder.to_dict(), 'duration metadata missing')
        self.assertAlmostEqual(recorder.to_dict()['duration_seconds'], 1/30)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'match.json'
            path.write_text('original')
            with patch('game.net.replay.os.replace', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    recorder.save(path)
            self.assertEqual(path.read_text(), 'original')
            self.assertEqual([p.name for p in Path(directory).iterdir()], ['match.json'])
            ns = factories()
            ns.update(recording=recorder)
            with patch('render.menus.USER_DIR', directory), patch.object(recorder, 'save', side_effect=OSError('read only')):
                ns['finish_recording']()
            self.assertIsNone(ns['recording'])
            self.assertIn('read only', ns['replay_notice'])
            self.assertEqual(ns['menu'].replay_notice, ns['replay_notice'])
        recorder = replay.MatchRecording(gm)
        with patch('game.net.replay.MAX_REPLAY_COMMANDS', 1):
            own = next(e.id for e in gm.state.entities.values() if e.owner == 0 and e.is_ship)
            gm.state.command_queue.extend([PlayerCommand('hold', 0, unit_ids=(own,))] * 2)
            tick = gm.state.tick
            gm.step(1/30)
            self.assertEqual(gm.state.tick, tick + 1, 'recording cap must not stop the game')
            self.assertIn('limit', recorder.error)
            with self.assertRaises(ValueError):
                recorder.save('not-written.json')

    def test_actual_loop_replay_failure_returns_to_browser_with_error(self):
        import ast
        from copy import deepcopy
        from types import SimpleNamespace
        from unittest.mock import Mock
        from test_lan_main import factories, ROOT
        tree = ast.parse((ROOT / 'main.py').read_text())
        loop = next(n for n in tree.body if isinstance(n, ast.While))
        branches = [n for n in loop.body if isinstance(n, ast.If)
                    and isinstance(n.test, ast.UnaryOp) and isinstance(n.test.op, ast.Not)
                    and isinstance(n.test.operand, ast.Call)
                    and isinstance(n.test.operand.func, ast.Name)
                    and n.test.operand.func.id == 'step_game_frame']
        self.assertEqual(len(branches), 1, 'Actual loop must use the production simulation boundary')
        branch = deepcopy(branches[0])
        code = ast.For(target=ast.Name(id='_frame', ctx=ast.Store()),
                       iter=ast.Tuple(elts=[ast.Constant(0)], ctx=ast.Load()), body=[branch], orelse=[])
        ns = factories()
        # Keep advance_simulation real: its playback path raises into the real
        # helper called by the actual main loop, then leave_game updates the browser.
        playback = SimpleNamespace(advance=Mock(side_effect=ValueError('Invalid replay continuation')))
        ns.update(playback=playback, state=game().state, dt_frame=.1)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[code], type_ignores=[])), 'main.py', 'exec'), ns)
        playback.advance.assert_called_once_with(.1)
        self.assertEqual(ns['mode'], 'menu')
        self.assertEqual(ns['menu'].screen, 'replays')
        self.assertIn('continuation', ns['menu'].replay_notice)

    def test_untrusted_payloads_are_rejected_with_bounded_validation(self):
        from copy import deepcopy
        from unittest.mock import patch
        gm = game()
        recorder = replay.MatchRecording(gm)
        gm.step(1/30)
        good = recorder.to_dict()
        for cmd in [{'type': [], 'player': 0}, {'type': 'build_ship', 'player': 0, 'ship_id': {}},
                    {'type': 'stop', 'player': 0, 'name': 123}, {'type': 'stop', 'player': False}]:
            bad = deepcopy(good)
            bad['commands'] = [{'tick': 0, 'cmd': cmd}]
            with self.subTest(command=cmd), self.assertRaises(ValueError):
                replay.validate_replay(bad)
        bad = deepcopy(good)
        bad['initial_state']['players'] = {'0': ['not-a-player']}
        with self.assertRaises(ValueError):
            replay.validate_replay(bad)
        bad = deepcopy(good)
        nested = bad
        for _ in range(40):
            nested['deep'] = {}
            nested = nested['deep']
        with self.assertRaisesRegex(ValueError, 'limits'):
            replay.validate_replay(bad)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'oversized.json'
            path.write_bytes(b' ' * 100)
            with patch('game.net.replay.MAX_REPLAY_BYTES', 50), self.assertRaisesRegex(ValueError, 'size limit'):
                replay.load_replay(path)

    def test_terminal_campaign_escape_finishes_recording_in_actual_branch(self):
        from unittest.mock import Mock, patch
        from test_lan_main import factories
        from test_campaign_lifecycle import campaign
        gm = campaign([{'type': 'survive_time', 'time': 0.}])
        recorder = replay.MatchRecording(gm, mode='campaign')
        gm.step(1/30)
        ns = factories()
        ns.update(state=gm.state, gm=gm, mission_def=gm.mission.mission, recording=recorder,
                  _unlock_next_mission=Mock())
        with tempfile.TemporaryDirectory() as directory, patch('render.menus.USER_DIR', directory):
            # #69: the terminal Escape branch is the real function now, so run it
            # instead of executing a copy of the loop's inline condition.
            self.assertIn('escape_from_decided_match', ns)
            self.assertTrue(ns['escape_from_decided_match']())
            self.assertIsNone(ns['recording'], 'campaign menu return did not finalize replay')
            self.assertEqual(len(list((Path(directory) / 'replays').glob('*.json'))), 1)
            self.assertEqual(ns['mode'], 'menu')

    def test_replay_hud_does_not_advertise_disabled_fleet_controls(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from render.replay_input import configure_replay_hud
        hud = SimpleNamespace(_label=Mock(), _right_panel=Mock(), _ability_rows=Mock())
        original = hud._label
        configure_replay_hud(hud)
        hud._label(0, 0, '1-9 control groups · F fleet menu')
        self.assertEqual(original.call_args.args[2], 'READ-ONLY: camera and inspection')

    def test_replay_gl_diagnostic_is_available(self):
        self.assertTrue((Path(__file__).resolve().parents[1] / 'tools/diag_replay_workflow.py').is_file(),
                        'real SDL/GL replay workflow diagnostic missing')


if __name__ == '__main__':
    unittest.main()
