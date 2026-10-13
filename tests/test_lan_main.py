"""Execute actual main factories without importing its SDL entry loop."""
import ast
import os
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from game.core.manager import GameManager
from game.core.state import GameState
from game.data.store import DataStore

ROOT = Path(__file__).resolve().parents[1]


def factories():
    tree = ast.parse((ROOT / 'main.py').read_text())
    ns = dict(os=os, GameManager=GameManager, GameState=GameState, DataStore=DataStore,
              MODS=[], W=800, H=600, gm=None, state=None, camera=None, renderer=None,
              hud=None, audio=None, inputc=None, net_session=None, local_player=0,
              accumulator=0., last_autosave=0., menu=Mock(), mode='game', paused=False,
              TICK_DT=1/30, Audio=object, SETTINGS={})
    for name in ('Camera', 'Renderer', 'HUD', 'InputController'):
        ns[name] = Mock(side_effect=lambda *a: SimpleNamespace(close=Mock(), zoom=Mock(), set_camera_ref=Mock()))
    ns['make_audio'] = Mock(side_effect=lambda state: SimpleNamespace(cleanup=Mock(), set_camera=Mock(), state=state))
    ns['_AppGlue'] = lambda: None
    code = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)], type_ignores=[])
    exec(compile(code, str(ROOT / 'main.py'), 'exec'), ns)
    ns['make_audio'] = Mock(side_effect=lambda state: SimpleNamespace(cleanup=Mock(), set_camera=Mock(), state=state))
    return ns


class LanMainTests(unittest.TestCase):
    def test_lan_respects_fixed_rate_at_faster_render_rate(self):
        ns = factories()
        ns['state'] = SimpleNamespace(game_over=False)
        ns['gm'] = Mock()
        ns['net_session'] = SimpleNamespace(advance=Mock(return_value=True))
        for _ in range(4):
            ns['advance_simulation'](1/120)
        self.assertEqual(ns['net_session'].advance.call_count, 1)
        ns['gm'].step.assert_not_called()

    def test_successful_lan_ticks_preserve_quantized_frame_remainder(self):
        ns = factories()
        ns['state'] = SimpleNamespace(game_over=False)
        ns['gm'] = Mock()
        ns['net_session'] = SimpleNamespace(advance=Mock(return_value=True))
        for _ in range(300):
            for milliseconds in (33, 33, 34):
                before = ns['net_session'].advance.call_count
                ns['advance_simulation'](milliseconds / 1000)
                self.assertLessEqual(ns['net_session'].advance.call_count - before, 1)
        self.assertGreaterEqual(ns['net_session'].advance.call_count, 899)
        self.assertLessEqual(ns['net_session'].advance.call_count, 900)
        self.assertGreaterEqual(ns['accumulator'], 0.)
        # One-step-per-frame pacing can defer one tick across a 34ms frame.
        self.assertLessEqual(ns['accumulator'], ns['TICK_DT'] + 1e-12)

    def test_success_keeps_fraction_but_network_wait_resets_it(self):
        ns = factories()
        ns['state'] = SimpleNamespace(game_over=False)
        ns['gm'] = Mock()
        ns['net_session'] = SimpleNamespace(advance=Mock(return_value=True))
        ns['advance_simulation'](.034)
        self.assertAlmostEqual(ns['accumulator'], .034 - ns['TICK_DT'])
        ns['net_session'].advance.return_value = False
        ns['advance_simulation'](.034)
        self.assertEqual(ns['accumulator'], 0.)
        ns['net_session'].advance.return_value = True
        ns['advance_simulation'](.001)
        self.assertEqual(ns['net_session'].advance.call_count, 2)

    def test_high_fps_sustained_success_is_thirty_hz(self):
        ns = factories()
        ns['state'] = SimpleNamespace(game_over=False)
        ns['gm'] = Mock()
        ns['net_session'] = SimpleNamespace(advance=Mock(return_value=True))
        for _ in range(3600):
            before = ns['net_session'].advance.call_count
            ns['advance_simulation'](1/120)
            self.assertLessEqual(ns['net_session'].advance.call_count - before, 1)
        self.assertEqual(ns['net_session'].advance.call_count, 900)
        ns['gm'].step.assert_not_called()

    def test_real_tcp_gl_menu_main_diagnostic_exists(self):
        self.assertTrue((ROOT / 'tools/diag_lan_menu.py').is_file(), 'LAN real-window diagnostic missing')

    def test_audio_victory_uses_client_slot_and_alliance_not_player_zero(self):
        from render.audio import Audio
        tree = ast.parse((ROOT / 'main.py').read_text())
        classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == '_ViewpointAudio']
        self.assertTrue(classes, 'Local audio viewpoint adapter missing')
        ns = {'Audio': Audio}
        exec(compile(ast.Module(body=classes, type_ignores=[]), 'main.py', 'exec'), ns)
        audio = ns['_ViewpointAudio'].__new__(ns['_ViewpointAudio'])
        audio.local_player = 1
        audio.state = SimpleNamespace(winner=1, allied_player_ids=lambda pid: {1})
        audio._allowed = Mock(return_value=True)
        audio.play = Mock()
        audio._ev_game_over(SimpleNamespace(data={'winner': 1}))
        audio.play.assert_called_once_with('mission_complete', .9)
        audio.play.reset_mock()
        audio._ev_game_over(SimpleNamespace(data={'winner': 0}))
        audio.play.assert_called_once_with('mission_failed', .9)
        audio.play.reset_mock()
        audio.state.allied_player_ids = lambda pid: {0, 1}
        audio._ev_game_over(SimpleNamespace(data={'winner': 0}))
        audio.play.assert_called_once_with('mission_complete', .9)

    def test_restart_releases_previous_audio_before_replacing_graph(self):
        ns = factories()
        old_audio = SimpleNamespace(cleanup=Mock())
        ns['audio'] = old_audio
        ns['start_game']()
        old_audio.cleanup.assert_called_once()
        self.assertIsNot(ns['audio'], old_audio)

    def test_network_input_failure_returns_to_menu_instead_of_crashing(self):
        ns = factories()
        ns['net_session'] = SimpleNamespace(close=Mock())
        ns['state'] = SimpleNamespace(_net_session=ns['net_session'])
        ns['inputc'] = SimpleNamespace(handle_event=Mock(side_effect=ValueError('Command limit exceeded')))
        self.assertIn('handle_game_input', ns, 'Network input exception boundary missing')
        ns['handle_game_input'](object())
        self.assertEqual(ns['mode'], 'menu')
        self.assertIn('Command limit exceeded', ns['menu'].lan_notice)
        self.assertIsNone(ns['net_session'])

    def test_network_controls_leave_cleanup_and_error_recovery(self):
        ns = factories()
        import pygame
        ns['pygame'] = pygame
        session = SimpleNamespace(close=Mock(), poll=Mock(), snapshot={'error': 'Peer disconnected'})
        ns['net_session'] = session
        ns['state'] = SimpleNamespace(_net_session=session, time=0.)
        ns['audio'] = SimpleNamespace(cleanup=Mock())
        self.assertIn('handle_network_event', ns)
        for key in (pygame.K_p, pygame.K_F5, pygame.K_F9):
            self.assertTrue(ns['handle_network_event'](pygame.event.Event(pygame.KEYDOWN, key=key)))
            self.assertEqual(ns['mode'], 'game')
        ns['poll_network']()
        self.assertEqual(ns['mode'], 'menu')
        session.close.assert_called_once()
        self.assertIsNone(ns['net_session'])
        self.assertIsNone(ns['state']._net_session)
        self.assertEqual(ns['menu'].screen, 'lan_join')
        self.assertIn('Peer disconnected', ns['menu'].lan_notice)
        ns['net_session'] = SimpleNamespace(close=Mock())
        ns['mode'] = 'game'
        # #69: the LAN hook no longer steals Escape — the in-match abort rule
        # owns it, so a pending operation is cancelled before any exit.
        self.assertFalse(ns['handle_network_event'](
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)))
        self.assertIsNotNone(ns['net_session'])
        self.assertEqual(ns['mode'], 'game')

    def test_decided_lan_match_releases_its_session_on_escape(self):
        """#69: a finished LAN match must still close its socket on Escape."""
        ns = factories()
        ns['mission_def'] = None
        ns['state'] = SimpleNamespace(game_over=True)
        ns['gm'] = Mock()
        ns['net_session'] = SimpleNamespace(close=Mock())
        ns['audio'] = SimpleNamespace(cleanup=Mock())
        self.assertIn('escape_from_decided_match', ns)
        self.assertTrue(ns['escape_from_decided_match']())
        self.assertEqual(ns['mode'], 'menu')
        self.assertIsNone(ns['net_session'])
        self.assertEqual(ns['menu'].screen, 'lan_join')

    def test_running_match_escape_never_leaves_on_its_own(self):
        """#69: the decided-result shortcut must not fire during play."""
        ns = factories()
        ns['mission_def'] = None
        ns['state'] = SimpleNamespace(game_over=False)
        ns['gm'] = Mock(mission=SimpleNamespace(completed=False, failed=False))
        ns['net_session'] = SimpleNamespace(close=Mock())
        self.assertFalse(ns['escape_from_decided_match']())
        self.assertEqual(ns['mode'], 'game')
        self.assertIsNotNone(ns['net_session'])

    def test_network_step_waits_without_catchup_and_never_double_steps(self):
        ns = factories()
        ns['state'] = SimpleNamespace(game_over=False)
        ns['gm'] = Mock()
        ns['net_session'] = SimpleNamespace(advance=Mock(return_value=False))
        self.assertIn('advance_simulation', ns)
        ns['accumulator'] = 5.
        ns['advance_simulation'](.2)
        self.assertEqual(ns['accumulator'], 0.)
        ns['gm'].step.assert_not_called()
        ns['net_session'].advance.assert_called_once()
        ns['net_session'].advance.return_value = True
        ns['advance_simulation'](.2)
        self.assertEqual(ns['net_session'].advance.call_count, 2)
        ns['gm'].step.assert_not_called()
        ns['net_session'] = None
        ns['advance_simulation'](1/30)
        ns['gm'].step.assert_called_once_with(1/30)

    def test_canonical_launch_builds_client_view_and_human_hook(self):
        ns = factories()
        from copy import deepcopy
        map_def = deepcopy(DataStore.get().maps['skirmish02'])
        map_def['players'][0]['ai'] = False
        map_def['players'][1]['ai'] = False
        session = SimpleNamespace(launch=dict(map_def=map_def, local_player=1), close=Mock())
        self.assertIn('lan_session', __import__('inspect').signature(ns['start_game']).parameters)
        ns['start_game'](lan_session=session)
        st = ns['state']
        self.assertIs(ns['net_session'], session)
        self.assertIs(st._net_session, session)
        for obj in ('inputc', 'renderer', 'hud', 'audio'):
            self.assertEqual(ns[obj].local_player, 1)
        own = next(e for e in st.entities.values() if e.owner == 1 and e.is_station)
        self.assertEqual(ns['camera'].target, [own.pos.x, 0., own.pos.z])
        self.assertEqual(ns['local_player'], 1)
