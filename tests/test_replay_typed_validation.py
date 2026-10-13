"""Untrusted replay state is rejected before browser approval or simulation."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from game.net.replay import MatchRecording, PlaybackSession, validate_replay
from test_replay_workflow import game


class TypedReplayValidationTests(unittest.TestCase):
    def test_typed_state_is_rejected_before_browser_approval(self):
        import pygame
        from render.menus import MenuStack, MenuResult
        good = json.loads(json.dumps(MatchRecording(game()).to_dict()))
        for label, mutate in [
            ('mission container', lambda st: st.update(mission_state=[])),
            ('time numeric', lambda st: st.update(time='broken')),
            ('credits numeric', lambda st: st['players']['0'].update(credits='broken')),
            ('AI boolean', lambda st: st['players']['0'].update(is_ai='false')),
            ('hull numeric', lambda st: next(iter(st['entities'].values())).update(hull='broken')),
        ]:
            with self.subTest(label=label):
                bad = deepcopy(good)
                mutate(bad['initial_state'])
                with self.assertRaises(ValueError):
                    validate_replay(bad)
                with self.assertRaises(ValueError):
                    PlaybackSession(bad)
                with tempfile.TemporaryDirectory() as directory:
                    folder = Path(directory) / 'replays'
                    folder.mkdir()
                    path = folder / 'bad.json'
                    path.write_text(json.dumps(bad))
                    with patch('render.menus.USER_DIR', directory):
                        menu = MenuStack(1024, 768)
                        menu.open_replays()
                        menu.render(0.)
                        # Browsing reads only bounded metadata; selecting never approves playback.
                        button = next(b for b in menu.buttons if b['action'] == 'select_replay')
                        menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                           pos=button['rect'].center))
                        self.assertEqual(menu.result, MenuResult.NONE)
                        menu.render(0.)
                        button = next(b for b in menu.buttons if b['action'] == 'play_replay')
                        menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                           pos=button['rect'].center))
                        self.assertEqual(menu.result, MenuResult.NONE)
                        self.assertTrue(menu.replay_notice)
                        self.assertEqual(menu.replay_selected, str(path))

    def test_mission_definition_and_progress_are_typed_before_approval(self):
        from test_campaign_lifecycle import campaign
        gm = campaign([{'id': 'wait', 'type': 'survive_time', 'time': 50}])
        good = MatchRecording(gm, mode='campaign').to_dict()
        for label, mutate in [
            ('definition container', lambda ms: ms.update(definition=[])),
            ('objective type', lambda ms: ms['definition']['objectives'][0].update(type='bad')),
            ('objective time', lambda ms: ms['definition']['objectives'][0].update(time='broken')),
            ('objective container', lambda ms: ms.update(objectives=[[]])),
            ('progress boolean', lambda ms: ms['objectives'][0].update(done='false')),
            ('progress numeric', lambda ms: ms['objectives'][0].update(count_done='broken')),
            ('terminal boolean', lambda ms: ms.update(completed='false')),
            ('unknown fired id', lambda ms: ms['script'].update(fired=['unknown'])),
            ('event boolean', lambda ms: ms['script'].update(events={'unknown': 'false'})),
            ('spawned identifiers', lambda ms: ms['script'].update(spawned={'unknown': ['bad']})),
        ]:
            with self.subTest(label=label):
                bad = deepcopy(good)
                mutate(bad['initial_state']['mission_state'])
                with self.assertRaises(ValueError):
                    validate_replay(bad)
                with self.assertRaises(ValueError):
                    PlaybackSession(bad)

    def test_mutable_nested_payloads_and_future_graph_are_validated(self):
        from game.net.reconnect import _decode, _encode
        good = json.loads(json.dumps(MatchRecording(game()).to_dict()))
        for label, mutate in [
            ('build timer', lambda st: next(iter(st['entities'].values())).update(build_queue=[
                {'kind': 'ship', 'item': 'imperial_corvette', 'total': 1., 'time_left': 'bad'}])),
            ('research timer', lambda st: st['players']['0'].update(researching={
                'tech': {'station_id': 1, 'total': 1., 'time_left': 'bad'}})),
            ('boarding timer', lambda st: next(iter(st['entities'].values())).update(boarding={
                'source': 1, 'target': 2, 'target_owner': 1, 'phase': 'transit', 'progress': 'bad'})),
            ('crew timer', lambda st: next(iter(st['entities'].values())).update(crew_mission={
                'owner': 0, 'target': None, 'phase': 'load', 'progress': 'bad'})),
            ('kill counter', lambda st: st.update(stats={'0': {'kills': 'bad', 'losses': 0}})),
        ]:
            with self.subTest(label=label):
                bad = deepcopy(good)
                mutate(bad['initial_state'])
                with self.assertRaises(ValueError):
                    validate_replay(bad)
        bad = deepcopy(good)
        state = _decode(bad['initial_state']['runtime_state']['state'])
        next(iter(state['entities'].values())).build_queue = [
            {'kind': 'ship', 'item': 'imperial_corvette', 'time_left': 'bad', 'total': 1.}]
        bad['initial_state']['runtime_state']['state'] = _encode(state)
        with self.assertRaises(ValueError):
            validate_replay(bad)

    def test_future_graph_cannot_disagree_with_replay_identity_or_pending_inputs(self):
        from game.net.reconnect import _decode, _encode
        good = json.loads(json.dumps(MatchRecording(game()).to_dict()))
        for label, mutate in [
            ('tick', lambda st: st.update(tick=st['tick'] + 1)),
            ('player AI flag', lambda st: setattr(st['players'][0], 'is_ai', True)),
            ('hidden command', lambda st: st['command_queue'].append(
                __import__('game.core.commands', fromlist=['PlayerCommand']).PlayerCommand('stop', 0))),
        ]:
            with self.subTest(label=label):
                bad = deepcopy(good)
                state = _decode(bad['initial_state']['runtime_state']['state'])
                mutate(state)
                bad['initial_state']['runtime_state']['state'] = _encode(state)
                with self.assertRaises(ValueError):
                    validate_replay(bad)

    def test_reconstruction_overflow_is_a_controlled_value_error(self):
        bad = MatchRecording(game()).to_dict()
        bad['initial_state']['players'][0]['credits'] = 10 ** 400
        with self.assertRaises(ValueError):
            validate_replay(bad)

    def test_legacy_fallback_warning_metadata_cannot_escape_as_type_error(self):
        bad = MatchRecording(game()).to_dict()
        bad['initial_state'].pop('runtime_state')
        bad['compatibility_warning'] = []
        with self.assertRaises(ValueError):
            validate_replay(bad)


if __name__ == '__main__':
    unittest.main()
