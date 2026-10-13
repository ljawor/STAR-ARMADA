"""Independent-review regressions through production browser/manager paths."""
import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from game.core.commands import PlayerCommand
from game.core.manager import GameManager
from game.net.replay import MatchRecording, load_replay
from test_replay_workflow import game


class ReviewReplayTests(unittest.TestCase):
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

    def test_malformed_player_with_human_stop_is_rejected_by_browser(self):
        import pygame
        from render.menus import MenuStack, MenuResult

        gm = game()
        recording = MatchRecording(gm)
        gm.state.queue_command(PlayerCommand('stop', 0))
        gm.step(1 / 30)
        data = recording.to_dict()
        data['initial_state']['players']['0'] = ['not-a-player']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'replays'
            folder.mkdir()
            path = folder / 'malformed.json'
            path.write_text(json.dumps(data))
            with patch('render.menus.USER_DIR', directory):
                menu = MenuStack(1024, 768)
                menu.open_replays()
                menu.render(0.)
                button = next(b for b in menu.buttons if b['action'] == 'select_replay')
                menu.handle_event(pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN, button=1, pos=button['rect'].center))
                menu.render(0.)
                self.assertIn('Cannot play:', menu.replay_rows[str(path)])
                button = next(b for b in menu.buttons if b['action'] == 'play_replay')
                menu.handle_event(pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN, button=1, pos=button['rect'].center))
                self.assertEqual(menu.result, MenuResult.NONE)
                self.assertIn('initial state', menu.replay_notice)
            with self.assertRaisesRegex(ValueError, 'initial state'):
                load_replay(path)

    def test_old_v2_browser_warns_future_state_not_unknown_duration(self):
        import pygame
        from render.menus import MenuStack
        data = MatchRecording(game()).to_dict()
        data['initial_state'].pop('runtime_state', None)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'replays'
            folder.mkdir()
            path = folder / 'old-v2.json'
            path.write_text(json.dumps(data))
            with patch('render.menus.USER_DIR', directory):
                menu = MenuStack(1024, 768)
                menu.open_replays()
                menu.render(0.)
                button = next(b for b in menu.buttons if b['action'] == 'select_replay')
                menu.handle_event(pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN, button=1, pos=button['rect'].center))
                menu.render(0.)
                row = menu.replay_rows[str(path)]
                self.assertIn('future-state unavailable', row)
                self.assertNotIn('duration unknown', row)

    def test_oversized_duration_is_controlled_browser_error(self):
        from game.net.replay import validate_replay, PlaybackSession
        from render.menus import MenuStack, MenuResult
        import pygame
        data = MatchRecording(game()).to_dict()
        data['duration_seconds'] = 10 ** 400
        with self.assertRaises(ValueError):
            validate_replay(data)
        with self.assertRaises(ValueError):
            PlaybackSession(data)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'replays'
            folder.mkdir()
            path = folder / 'oversized-duration.json'
            path.write_text(json.dumps(data))
            with patch('render.menus.USER_DIR', directory):
                menu = MenuStack(1024, 768)
                menu.open_replays()
                menu.render(0.)
                button = next(b for b in menu.buttons if b['action'] == 'select_replay')
                menu.handle_event(pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN, button=1, pos=button['rect'].center))
                menu.render(0.)
                self.assertIn('Cannot play:', menu.replay_rows[str(path)])
                button = next(b for b in menu.buttons if b['action'] == 'play_replay')
                menu.handle_event(pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN, button=1, pos=button['rect'].center))
                self.assertEqual(menu.result, MenuResult.NONE)
                self.assertIn('duration', menu.replay_notice)

    def test_invalid_initial_state_containers_raise_value_error(self):
        from copy import deepcopy
        from game.net.replay import validate_replay

        data = MatchRecording(game()).to_dict()
        for field, value in [('entities', None), ('command_queue', None)]:
            bad = deepcopy(data)
            bad['initial_state'][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'initial state'):
                validate_replay(bad)


class ReviewCampaignTests(unittest.TestCase):
    def test_failure_stops_remaining_actions_in_same_trigger_at_manager_tick(self):
        from test_campaign_lifecycle import campaign

        gm = campaign([{'id': 'wait', 'type': 'survive_time', 'time': 50}])
        wave = {'type': 'reinforcements', 'units': [
            {'ship': 'imperial_corvette', 'owner': 0, 'pos': [-5000, 0, 3000]}]}
        definition = dict(gm.mission.mission, triggers=[
            {'id': 'loss', 'when': {'tick': 1}, 'actions': [
                {'type': 'fail_mission'}, wave,
                {'type': 'complete_objective', 'objective': 'wait'}]},
            {'id': 'later', 'when': {'tick': 1}, 'actions': [wave]}])
        gm = GameManager(gm.state, mission_def=definition)
        before = set(gm.state.entities)
        events = []
        gm.state.events.subscribe('mission_failed', lambda ev: events.append(ev.type))
        gm.step(1 / 30)
        self.assertTrue(gm.mission.failed)
        self.assertFalse(gm.mission.completed)
        self.assertEqual(set(gm.state.entities), before, 'post-failure reinforcements spawned')
        self.assertFalse(gm.mission.objectives[0]['done'])
        self.assertEqual(gm.mission.script.to_dict()['fired'], ['loss'])
        self.assertEqual(gm.mission.script.to_dict()['spawned'], {})
        gm.step(1 / 30)
        self.assertEqual(set(gm.state.entities), before)
        self.assertEqual(events, ['mission_failed'])


if __name__ == '__main__':
    unittest.main()
