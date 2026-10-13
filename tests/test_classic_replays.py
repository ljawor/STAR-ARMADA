"""Clean Classic replay presentation: real recordings and measured pixels."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pygame
from render.menus import MenuStack


class ClassicReplayFixtureIsolationTests(unittest.TestCase):
    def test_fixture_does_not_migrate_or_read_outer_user_files(self):
        import builtins
        from render import menus

        # The outer patch is a safety barrier, not the fixture under test:
        # a broken fixture can only migrate these disposable sentinel files.
        with tempfile.TemporaryDirectory() as protected:
            root = Path(protected)
            campaign = root / 'campaign.json'
            settings = root / 'settings.json'
            campaign_bytes = b'{"mission_index":3}\n'
            settings_bytes = b'{"music_volume":0.17,"sentinel_only":true}\n'
            campaign.write_bytes(campaign_bytes)
            settings.write_bytes(settings_bytes)
            fixture = ClassicReplayTests()
            real_open = builtins.open

            def guarded_open(file, mode='r', *args, **kwargs):
                if isinstance(file, (str, bytes, Path)) and any(c in mode for c in 'wax+'):
                    import os
                    target = Path(os.fsdecode(file)).resolve()
                    allowed = [root.resolve()]
                    if hasattr(fixture, 'root'):
                        allowed.append(fixture.root.resolve())
                    if not any(target.is_relative_to(base) for base in allowed):
                        raise AssertionError(f'write outside isolated fixture: {target}')
                return real_open(file, mode, *args, **kwargs)

            with patch.multiple(menus, USER_DIR=str(root), SAVES_DIR=str(root),
                                CAMPAIGN_PATH=str(campaign), SETTINGS_PATH=str(settings)), \
                    patch('builtins.open', side_effect=guarded_open):
                try:
                    fixture.setUp()
                    loaded_settings = dict(fixture.menu.settings)
                finally:
                    fixture.doCleanups()
                with self.subTest(file='campaign'):
                    self.assertEqual(campaign.read_bytes(), campaign_bytes)
                with self.subTest(file='settings'):
                    self.assertEqual(settings.read_bytes(), settings_bytes)
                with self.subTest(settings='defaults, not the outer sentinel'):
                    self.assertEqual(loaded_settings, menus.DEFAULT_SETTINGS)

    def test_every_menu_closes_before_paths_and_temp_directory_are_restored(self):
        from render import menus
        fixture = ClassicReplayTests()
        original_close = MenuStack.close
        closed = []

        def tracked_close(menu):
            self.assertTrue(fixture.root.is_dir())
            self.assertEqual(menus.USER_DIR, str(fixture.root))
            self.assertEqual(menus.SETTINGS_PATH, str(fixture.root / 'saves' / 'settings.json'))
            self.assertEqual(menus.CAMPAIGN_PATH, str(fixture.root / 'saves' / 'campaign.json'))
            closed.append(menu)
            original_close(menu)

        with patch.object(MenuStack, 'close', autospec=True, side_effect=tracked_close):
            try:
                fixture.setUp()
                original = fixture.menu
                fixture.test_supported_sizes_all_states_are_bounded_and_fonts_surfaces_cached()
            finally:
                fixture.doCleanups()
        self.assertEqual(len(closed), 7)  # Original plus six resolution replacements.
        self.assertEqual(len({id(menu) for menu in closed}), 7)
        self.assertIn(original, closed)
        self.assertIn(fixture.menu, closed)
        self.assertFalse(fixture.root.exists())

    def test_gl_setup_failure_still_runs_fixture_cleanups(self):
        import sys
        import test_classic_replays_gl as acceptance

        fixture = ClassicReplayTests()
        real_setup = fixture.setUp

        def fail_after_setup():
            real_setup()
            raise RuntimeError('injected setup failure')

        with tempfile.TemporaryDirectory() as output, \
                patch.object(acceptance.fixtures, 'ClassicReplayTests', return_value=fixture), \
                patch.object(fixture, 'setUp', side_effect=fail_after_setup), \
                patch.object(fixture, 'doCleanups', wraps=fixture.doCleanups) as cleanups, \
                patch.object(acceptance.pygame, 'quit') as quit_pygame, \
                patch.object(sys, 'argv', ['test_classic_replays_gl.py', output]):
            try:
                with self.assertRaisesRegex(RuntimeError, 'injected setup failure'):
                    acceptance.main()
                cleanups.assert_called_once()
                quit_pygame.assert_called_once()
                self.assertFalse(fixture.root.exists())
            finally:
                # Keep the RED regression safe even when main misses its cleanup.
                fixture.doCleanups()


class ClassicReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'replays'
        self.folder.mkdir()
        saves = self.root / 'saves'
        scope = patch.multiple('render.menus', USER_DIR=str(self.root),
                               SAVES_DIR=str(saves),
                               SETTINGS_PATH=str(saves / 'settings.json'),
                               CAMPAIGN_PATH=str(saves / 'campaign.json'))
        scope.start()
        self.addCleanup(scope.stop)
        mouse = patch('pygame.mouse.get_pos', return_value=(0, 0))
        mouse.start()
        self.addCleanup(mouse.stop)
        self.menu = self.own_menu(1120, 700)

    def own_menu(self, width, height):
        menu = MenuStack(width, height)
        # Bind this instance, not self.menu, which resolution tests replace.
        self.addCleanup(menu.close)
        return menu

    def draw(self):
        self.menu.buttons = []
        self.menu._screen_replays()

    def recording(self, name, created='2026-01-01T12:00:00Z'):
        import json
        from game.core.manager import GameManager
        from game.data.store import DataStore
        from game.net.replay import MatchRecording
        gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
        rec = MatchRecording(gm, mode='skirmish')
        gm.step(1 / 30)
        data = rec.to_dict()
        data['created_utc'] = created
        path = self.folder / name
        path.write_text(json.dumps(data))
        return str(path)

    def click(self, action, payload=None):
        self.draw()
        b = next(b for b in self.menu.buttons if b['action'] == action and
                 (payload is None or b['payload'] == payload))
        self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=b['rect'].center))

    def test_recordings_have_six_compact_dated_rows_and_right_hand_selection(self):
        paths = [self.recording('recording-' + str(i) + '-' + 'a' * 120 + '.json',
                                f'2026-01-0{i + 1}T12:00:00Z') for i in range(7)]
        self.menu.open_replays()
        with patch('builtins.open', side_effect=AssertionError('render must use cached metadata')):
            self.draw()
        rows = [b for b in self.menu.buttons if b['action'] == 'select_replay']
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]['payload'], paths[-1])
        self.assertLess(rows[0]['rect'].right, 744)
        self.assertEqual(self.menu.replay_rendered_text[3], '2026-01-07 12:00:00 UTC / recorded')
        self.assertTrue(any(t.endswith('…') for t in self.menu.replay_rendered_text))
        self.click('select_replay', paths[-1])
        self.draw()
        play = next(b for b in self.menu.buttons if b['action'] == 'play_replay')
        self.assertGreaterEqual(play['rect'].left, 744)
        self.assertEqual(play['payload'], paths[-1])
        self.assertTrue(any('skirmish / 0.0s / game' in t for t in self.menu.replay_rendered_text))
        self.assertTrue(any('P pause / [ ] speed / Esc exit.' in t for t in self.menu.replay_rendered_text))
        self.click('replay_page', 1)
        self.draw()
        self.assertEqual(len([b for b in self.menu.buttons if b['action'] == 'select_replay']), 1)
        self.assertIn('Page 2/2 / 7 files / newest first', self.menu.replay_rendered_text)
        self.assertEqual([b['payload'] for b in self.menu.buttons if b['action'] == 'replay_page'], [-1])

    def test_confirmation_is_exclusive_dark_panel_cancel_primary_delete_danger(self):
        from render.clean_classic import ACCENT
        from render.classic_replays import DANGER_FILL
        path = self.recording('selected.json')
        self.menu.open_replays()
        self.click('select_replay', path)
        self.click('replay_delete')
        self.draw()
        self.assertEqual([b['action'] for b in self.menu.buttons],
                         ['replay_cancel_delete', 'replay_confirm_delete'])
        self.assertIn('DELETE SELECTED REPLAY?', self.menu.replay_rendered_text)
        cancel, delete = [b['rect'] for b in self.menu.buttons]
        self.assertEqual(tuple(self.menu._surface.get_at((cancel.x + 3, cancel.y + 3)))[:3], ACCENT)
        self.assertEqual(tuple(self.menu._surface.get_at((delete.x + 3, delete.y + 3)))[:3], DANGER_FILL)
        self.menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertTrue(Path(path).exists())
        self.assertIsNone(self.menu.replay_confirmation)
        self.click('replay_delete_all')
        self.draw()
        self.assertTrue(any('beyond the browser limit' in t for t in self.menu.replay_rendered_text))
        self.click('replay_cancel_delete')
        self.assertTrue(Path(path).exists())

    def test_corrupt_recording_retains_existing_select_delete_and_validation_actions(self):
        path = self.folder / 'corrupt.json'
        path.write_text('{bad')
        self.menu.open_replays()
        self.click('select_replay', str(path))
        self.draw()
        self.assertEqual(self.menu.replay_selected, str(path))
        self.assertIn('play_replay', [b['action'] for b in self.menu.buttons])
        self.assertIn('replay_delete', [b['action'] for b in self.menu.buttons])
        self.assertTrue(any('Cannot play:' in t for t in self.menu.replay_rendered_text))

    def assert_geometry(self):
        window = pygame.Rect(0, 0, self.menu.width, self.menu.height)
        bounds = [r for r in self.menu.replay_text_bounds if r.w]
        self.assertTrue(all(window.contains(r) for r in bounds))
        for i, rect in enumerate(bounds):
            self.assertFalse(any(rect.colliderect(other) for other in bounds[i + 1:]), rect)
        controls = [b['rect'] for b in self.menu.buttons]
        self.assertTrue(all(window.contains(r) for r in controls))
        for i, rect in enumerate(controls):
            self.assertFalse(any(rect.colliderect(other) for other in controls[i + 1:]), rect)

    def test_supported_sizes_all_states_are_bounded_and_fonts_surfaces_cached(self):
        paths = [self.recording(f'recording-{i}.json') for i in range(7)]
        broken = self.folder / ('broken-' + 'a' * 160 + '.json')
        broken.write_text('{bad')
        for w, h in ((800, 600), (960, 640), (1120, 700), (1280, 800), (1440, 900), (2400, 1400)):
            self.menu = self.own_menu(w, h)
            self.menu.screen = 'replays'
            self.draw()
            self.assert_geometry()
            self.menu.open_replays()
            for state in ('unselected', 'selected', 'paged', 'invalid', 'confirm', 'confirm-all'):
                with self.subTest(size=(w, h), state=state):
                    self.menu.replay_page = int(state == 'paged')
                    if state == 'selected':
                        self.click('select_replay', paths[0])
                    elif state == 'invalid':
                        self.click('select_replay', str(broken))
                    self.menu.replay_confirmation = (str(broken) if state == 'confirm' else
                                                     'ALL' if state == 'confirm-all' else None)
                    self.menu.replay_notice = ('Cannot delete replay: ' + 'Permission denied ' * 15
                                               if state == 'invalid' else self.menu.replay_notice)
                    self.draw()
                    self.assert_geometry()
                    logical = self.menu._classic_surfaces['replay']
                    with patch('pygame.font.SysFont', side_effect=AssertionError('warmed font allocation')):
                        with patch('builtins.open', side_effect=AssertionError('warmed disk read')):
                            self.draw()
                    self.assertIs(logical, self.menu._classic_surfaces['replay'])
            self.assertEqual(tuple(self.menu._surface.get_at((0, 0)))[:3], (8, 15, 22))

    def test_empty_library_uses_solid_classic_canvas_and_inactive_actions(self):
        self.menu.open_replays()
        self.menu._surface.fill((199, 0, 199))
        self.draw()
        self.assertIn('STAR ARMADA', self.menu.replay_rendered_text)
        self.assertIn('Replay library', self.menu.replay_rendered_text)
        self.assertTrue(any('No replays' in t for t in self.menu.replay_rendered_text))
        self.assertEqual(tuple(self.menu._surface.get_at((0, 0)))[:3], (8, 15, 22))
        self.assertEqual({b['action'] for b in self.menu.buttons}, {'goto_main', 'replay_refresh', 'replay_delete_all'})
        self.assertEqual(self.menu._classic_surfaces['replay'].get_size(), (1120, 700))
