"""#89: a won campaign mission returns to the campaign screen and reads COMPLETE.

Isolation follows the menu-fixture rule: every persistence constant is patched
before a MenuStack exists, and outer sentinel bytes prove nothing leaked.
"""
import ast
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pygame

from render import menus
from render.clean_classic import BORDER, DONE
from render.menus import MenuStack, DEFAULT_SETTINGS

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ['m00_recovery_drill', 'm01_first_fleet', 'm02_supply_line']


def status_rows(menu):
    """Exact row status labels, so the footer sentence never inflates a count."""
    texts = list(menu.campaign_rendered_text)
    return {label: texts.count(label) for label in ('COMPLETE', 'AVAILABLE', 'LOCKED')}


class CampaignProgressIsolation(unittest.TestCase):
    """Temp CAMPAIGN_PATH for the persistence tests; no MenuStack involved."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.path = self.home / 'campaign.json'
        self.patch = patch.object(menus, 'CAMPAIGN_PATH', str(self.path))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def catalogue(self, ids=CATALOGUE):
        return patch.object(menus, '_campaign_ids', return_value=list(ids))


class CampaignCompletionPersistenceTests(CampaignProgressIsolation):
    def test_won_mission_is_recorded_without_touching_unlocks(self):
        with self.catalogue():
            menus.complete_campaign_mission('m01_first_fleet')
            self.assertEqual(menus.load_campaign_completed(), {'m01_first_fleet'})
            self.assertEqual(menus.load_campaign_unlocks(), {'m00_recovery_drill'})
            saved = json.loads(self.path.read_text())
            self.assertEqual(saved['schema_version'], 3)
            self.assertEqual(saved['completed_mission_ids'], ['m01_first_fleet'])

    def test_recording_a_win_is_idempotent_and_keeps_existing_progress(self):
        with self.catalogue():
            menus.save_campaign_progress(2)
            first = None
            for _ in range(2):
                menus.complete_campaign_mission('m00_recovery_drill')
                self.assertEqual(menus.load_campaign_completed(), {'m00_recovery_drill'})
                if first is not None:
                    self.assertEqual(self.path.read_text(), first)
                first = self.path.read_text()
            self.assertEqual(menus.load_campaign_unlocks(),
                             {'m00_recovery_drill', 'm01_first_fleet', 'm02_supply_line'})

    def test_unknown_or_absent_mission_id_never_writes_progress(self):
        raw = json.dumps({'schema_version': 2, 'unlocked_mission_ids': ['m01_first_fleet']})
        self.path.write_text(raw)
        for mission_id in ('future_mod', None, 3, ''):   # 3 is deliberately not a str
            with self.subTest(mission_id=mission_id):
                menus.complete_campaign_mission(mission_id)  # type: ignore[arg-type]
                self.assertEqual(self.path.read_text(), raw)
                self.assertEqual(menus.load_campaign_completed(), set())

    def test_v2_progress_reads_as_unfinished_and_is_not_rewritten(self):
        raw = json.dumps({'schema_version': 2,
                          'unlocked_mission_ids': ['m01_first_fleet', 'future_mod']})
        self.path.write_text(raw)
        self.assertEqual(menus.load_campaign_completed(), set())
        self.assertEqual(menus.load_campaign_unlocks(),
                         {'m00_recovery_drill', 'm01_first_fleet', 'future_mod'})
        self.assertEqual(self.path.read_text(), raw)

    def test_legacy_progress_migrates_once_to_v3_with_no_completed_missions(self):
        self.path.write_text(json.dumps({'mission_index': 1}))
        self.assertEqual(menus.load_campaign_completed(), set())
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved['schema_version'], 3)
        self.assertEqual(saved['completed_mission_ids'], [])
        first = self.path.read_text()
        self.assertEqual(menus.load_campaign_completed(), set())
        self.assertEqual(self.path.read_text(), first)

    def test_malformed_v3_completed_list_is_treated_as_corrupt(self):
        raw = json.dumps({'schema_version': 3, 'unlocked_mission_ids': ['m01_first_fleet'],
                          'completed_mission_ids': [0]})
        self.path.write_text(raw)
        self.assertEqual(menus.load_campaign_unlocks(), {'m00_recovery_drill'})
        self.assertEqual(menus.load_campaign_completed(), set())
        self.assertEqual(self.path.read_text(), raw)

    def test_unlock_keeps_completed_missions(self):
        with self.catalogue():
            menus.complete_campaign_mission('m00_recovery_drill')
            menus.unlock_campaign_mission('m01_first_fleet')
            self.assertEqual(menus.load_campaign_completed(), {'m00_recovery_drill'})
            self.assertIn('m01_first_fleet', menus.load_campaign_unlocks())


class CampaignCompletionScreenTests(CampaignProgressIsolation):
    """Real MenuStack render, with every persistence path inside the temp dir."""

    def setUp(self):
        super().setUp()
        self.saves = self.home / 'saves'
        self.path_patches = [
            patch.object(menus, 'USER_DIR', str(self.home)),
            patch.object(menus, 'SAVES_DIR', str(self.saves)),
            patch.object(menus, 'SETTINGS_PATH', str(self.saves / 'settings.json')),
        ]
        for item in self.path_patches:
            item.start()
            self.addCleanup(item.stop)
        pygame.font.init()
        self.stacks = []

    def menu(self):
        menu = MenuStack(1280, 800)
        self.stacks.append(menu)
        self.addCleanup(menu.close)
        menu.screen = 'campaign'
        menu.settings = dict(DEFAULT_SETTINGS)
        menu.campaign = {'campaign': 'Test Campaign',
                         'missions': [{'id': mid, 'name': mid} for mid in CATALOGUE]}
        return menu

    def test_completed_row_is_marked_complete_and_stays_selectable(self):
        with self.catalogue():
            menus.save_campaign_progress(2)
            menus.complete_campaign_mission('m00_recovery_drill')
            menu = self.menu()
            with patch('pygame.mouse.get_pos', return_value=(0, 0)):
                menu._screen_campaign()
            rows = [b for b in menu.buttons if b['action'] == 'select_mission']
            self.assertEqual([b['payload'] for b in rows], [0, 1, 2])
            self.assertEqual(status_rows(menu),
                             {'COMPLETE': 1, 'AVAILABLE': 2, 'LOCKED': 0})

    def test_completed_row_border_uses_the_finished_colour(self):
        with self.catalogue():
            menus.save_campaign_progress(2)
            menus.complete_campaign_mission('m00_recovery_drill')
            menu = self.menu()
            with patch('pygame.mouse.get_pos', return_value=(0, 0)):
                menu._screen_campaign()
            surface = menu._classic_surfaces['campaign']
            done_edge = tuple(surface.get_at((52, 164 + 25)))[:3]
            available_edge = tuple(surface.get_at((52, 164 + 60 + 25)))[:3]
            self.assertEqual(done_edge, DONE)
            self.assertEqual(available_edge, BORDER)
            self.assertNotEqual(done_edge, available_edge)

    def test_locked_rows_are_never_marked_complete(self):
        with self.catalogue():
            menu = self.menu()
            with patch('pygame.mouse.get_pos', return_value=(0, 0)):
                menu._screen_campaign()
            self.assertEqual(status_rows(menu),
                             {'COMPLETE': 0, 'AVAILABLE': 1, 'LOCKED': 2})
            self.assertEqual([b['payload'] for b in menu.buttons
                              if b['action'] == 'select_mission'], [0])


def _exec_main(names, ns):
    """Execute real main.py functions against a prepared namespace."""
    source = ROOT / 'main.py'
    tree = ast.parse(source.read_text())
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns.setdefault('mission_def', None)
    ns.setdefault('playback', None)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(source), 'exec'), ns)
    return ns


class MenuDestinationStub(SimpleNamespace):
    def __init__(self):
        super().__init__(screen='briefing', buttons=[{'action': 'stale'}],
                         lan_notice='', replay_notice='', replays_opened=False)
        self.lan_closed = 0

    def close_lan(self):
        self.lan_closed += 1

    def open_replays(self):
        self.replays_opened = True


def _leave_game_namespace(playback=None, net_session=None):
    menu = MenuDestinationStub()
    ns = {'menu': menu, 'presentation': None, 'cinematic': None, 'playback': playback,
          'net_session': net_session, 'state': SimpleNamespace(_net_session=None),
          'audio': None, 'finish_recording': lambda: None, 'mission_def': {'id': 'm01'}}
    return _exec_main(('leave_game',), ns)


class CampaignResultDestinationTests(unittest.TestCase):
    """The real leave_game()/presentation functions decide the return screen."""

    def test_campaign_result_returns_to_the_campaign_screen(self):
        ns = _leave_game_namespace()
        ns['leave_game'](screen='campaign')
        self.assertEqual(ns['menu'].screen, 'campaign')
        self.assertEqual(ns['mode'], 'menu')
        self.assertEqual(ns['menu'].lan_closed, 1)
        self.assertEqual(ns['menu'].buttons, [])

    def test_skirmish_result_keeps_the_main_menu_destination(self):
        ns = _leave_game_namespace()
        ns['leave_game']()
        self.assertEqual(ns['menu'].screen, 'main')

    def test_replay_destination_is_unchanged(self):
        ns = _leave_game_namespace(playback=object())
        ns['leave_game']()
        self.assertEqual(ns['menu'].screen, 'replays')
        self.assertTrue(ns['menu'].replays_opened)

    def test_lan_destination_is_unchanged(self):
        session = SimpleNamespace(close=lambda: None)
        ns = _leave_game_namespace(net_session=session)
        ns['leave_game']('Match finished.')
        self.assertEqual(ns['menu'].screen, 'lan_join')
        self.assertEqual(ns['menu'].lan_notice, 'Match finished.')

    def test_finished_campaign_cinematic_routes_through_the_campaign_screen(self):
        calls = []
        # The presentation ends only if the window actually showed it (#160): a dead window is a
        # fault (`test_hybrid_main` covers that), never a reason to draw a legacy frame here.
        ns = {'cinematic': SimpleNamespace(finished=True, outcome='MISSION COMPLETE',
                                           update=lambda dt: None,
                                           draw_gl=lambda w, h: None),
              'accumulator': 1.0, 'camera': SimpleNamespace(apply=lambda w, h: None),
              'pygame': pygame, 'W': 1280, 'H': 800,
              'CPP': {'failed': False}, 'CPP_HUD_SIZE': (1280, 800), 'RENDERER': 'cpp',
              'SMOKE': False, 'cpp_publish': lambda *a, **k: True,
              'cpp_drawing': lambda: True, 'cpp_fatal': lambda reason: calls.append(('fault', reason)),
              'state': object(), 'gm': SimpleNamespace(ds=object()), 'local_player': 0, 'fps': 30.,
              'mission_def': {'id': 'm01_recovery_drill'},
              'leave_game': lambda *a, **k: calls.append((a, k))}
        _exec_main(('draw_campaign_presentation',), ns)
        with patch('pygame.display.flip'):
            ns['draw_campaign_presentation'](1 / 60)
        self.assertEqual(calls, [((), {'screen': 'campaign'})])

    def test_decided_campaign_match_without_cinematics_lands_on_campaign(self):
        ns = {'state': SimpleNamespace(game_over=False), 'mission_def': {'id': 'm01'},
              'gm': SimpleNamespace(mission=SimpleNamespace(completed=True, failed=False)),
              'menu': MenuDestinationStub(), 'net_session': None,
              'campaign_outcome_seen': True, 'mode': 'game'}
        _exec_main(('escape_from_decided_match',), ns)
        self.assertTrue(ns['escape_from_decided_match']())
        self.assertEqual(ns['menu'].screen, 'campaign')

    def test_decided_skirmish_match_does_not_force_the_campaign_screen(self):
        ns = {'state': SimpleNamespace(game_over=True), 'mission_def': None,
              'gm': SimpleNamespace(mission=None), 'menu': MenuDestinationStub(),
              'net_session': None, 'campaign_outcome_seen': True, 'mode': 'game'}
        _exec_main(('escape_from_decided_match',), ns)
        self.assertTrue(ns['escape_from_decided_match']())
        self.assertEqual(ns['menu'].screen, 'briefing')
        self.assertEqual(ns['mode'], 'menu')


if __name__ == '__main__':
    unittest.main()
