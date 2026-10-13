"""Replay-library vertical slices using real temporary files and menu events."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pygame
from render.menus import MenuStack, MenuResult


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'replays'
        self.folder.mkdir()
        self.scope = patch('render.menus.USER_DIR', str(self.root))
        self.scope.start()
        self.addCleanup(self.scope.stop)
        # USER_DIR is frozen into SETTINGS_PATH at import, so pin that too: without it
        # this library would render in the developer's saved language.
        self.settings = patch('render.menus.SETTINGS_PATH',
                             str(self.root / 'settings.json'))
        self.settings.start()
        self.addCleanup(self.settings.stop)
        self.menu = MenuStack(1024, 768)

    def click(self, action, payload=None):
        self.menu.render(0.)
        button = next(b for b in self.menu.buttons if b['action'] == action and
                      (payload is None or b['payload'] == payload))
        self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                              button=1, pos=button['rect'].center))

    def symlink(self, link, target, **kwargs):
        try:
            link.symlink_to(target, **kwargs)
        except OSError as exc:
            if os.name == 'nt' and getattr(exc, 'winerror', None) == 1314:
                self.skipTest('Windows symlink privilege unavailable; mandatory native junction tests are separate')
            raise

    def test_empty_menu_initial_state_is_renderable_without_browse_side_effects(self):
        self.menu.screen = 'replays'
        self.menu.render(0.)
        self.assertEqual(self.menu.replay_paths, [])
        self.assertIsNone(self.menu.replay_selected)
        self.assertIsNone(self.menu.replay_confirmation)

    def test_partial_directory_scan_error_leaves_browser_renderable(self):
        path = self.folder / 'collected.json'
        path.write_text('{bad')
        real_scandir = os.scandir
        for error_type in (OSError, FileNotFoundError, PermissionError, NotADirectoryError):
            with self.subTest(error_type=error_type):
                yielded = []
                class InterruptedScan:
                    def __enter__(inner):
                        with real_scandir(self.folder) as entries:
                            entry = next(entries)
                        def interrupted_entries():
                            yielded.append(entry.path)
                            yield entry
                            raise error_type('scan interrupted')
                        return interrupted_entries()
                    def __exit__(inner, *args):
                        pass
                with patch('render.menus.os.scandir', return_value=InterruptedScan()):
                    self.menu.open_replays()
                self.assertEqual(yielded, [str(path)])
                self.menu.render(0.)
                self.assertEqual(self.menu.replay_paths, [])
                self.assertEqual(self.menu.replay_metadata, {})
                if error_type is not FileNotFoundError:
                    self.assertIn('Cannot browse replays: scan interrupted', self.menu.replay_rendered_text)
                actions = {button['action'] for button in self.menu.buttons}
                self.assertTrue({'goto_main', 'replay_refresh'} <= actions)
                self.assertTrue(path.exists())
                self.click('replay_refresh')
                self.assertEqual(self.menu.replay_paths, [str(path)])
                self.menu.render(0.)
                self.assertEqual(self.menu.replay_notice, '')

    def test_missing_directory_is_a_renderable_empty_library(self):
        self.folder.rmdir()
        self.menu.open_replays()
        self.menu.render(0.)
        self.assertEqual(self.menu.replay_paths, [])
        self.assertEqual(self.menu.replay_metadata, {})
        self.assertEqual(self.menu.replay_notice, '')
        self.assertTrue(any('No replays' in text for text in self.menu.replay_rendered_text))

    def test_metadata_works_without_posix_nofollow_flag(self):
        from render.replay_library import metadata
        path = self.folder / 'dated.json'
        path.write_text('{"created_utc":"2026-01-01T00:00:00Z"}')
        with patch.dict(os.__dict__):
            os.__dict__.pop('O_NOFOLLOW', None)
            stamp, label, info = metadata(str(path))
        self.assertIn('2026-01-01 00:00:00 UTC / recorded', label)

    @unittest.skipIf(os.name == 'nt', 'POSIX capability gate; Windows has a native handle backend')
    def test_unsupported_safe_directory_api_fails_closed_with_clear_error(self):
        from render.replay_library import delete_selected
        path = self.folder / 'keep.json'
        path.write_text('{bad')
        with patch('render.replay_library.os.supports_dir_fd', set()):
            with self.assertRaisesRegex(OSError, 'Safe replay deletion unavailable'):
                delete_selected(str(self.folder), str(path))
        self.assertTrue(path.exists())

    def test_metadata_does_not_retain_untrusted_container_headers(self):
        from render.replay_library import metadata
        path = self.folder / 'bad-header.json'
        path.write_text(json.dumps({'created_utc': ['not a date'] * 1000,
                                    'mode': {'payload': ['x'] * 1000}, 'version': 99}))
        stamp, label, info = metadata(str(path))
        self.assertEqual(info, {'version': 99})
        self.assertIn('file time', label)

    def test_browser_keeps_newest_thousand_not_first_thousand_scandir_entries(self):
        for i in range(1000):
            (self.folder / f'old-{i}.json').write_text('{"created_utc":"2020-01-01T00:00:00Z"}')
        newest = self.folder / 'newest.json'
        newest.write_text('{"created_utc":"2026-01-01T00:00:00Z"}')
        # Directory enumeration order is not a chronological contract.
        real_scandir = os.scandir
        class Ordered:
            def __enter__(inner):
                with real_scandir(self.folder) as entries:
                    return iter(sorted(entries, key=lambda entry: entry.name == 'newest.json'))
            def __exit__(inner, *args):
                pass
        with patch('render.menus.os.scandir', return_value=Ordered()):
            self.menu.open_replays()
        self.assertEqual(len(self.menu.replay_paths), 1000)
        self.assertEqual(self.menu.replay_paths[0], str(newest))
        self.assertIn('limit', self.menu.replay_notice.lower())

    def test_delete_refuses_symlinked_user_directory_parent(self):
        from render.replay_library import delete_selected
        parent = self.root / 'alias'
        self.symlink(parent, self.root, target_is_directory=True)
        path = self.folder / 'keep.json'
        path.write_text('preserve')
        with self.assertRaises(OSError):
            delete_selected(str(parent / 'replays'), str(parent / 'replays' / 'keep.json'))
        self.assertTrue(path.exists())

    def test_symlinked_replay_directory_is_not_browsed_or_deleted(self):
        self.folder.rmdir()
        outside = self.root / 'outside'
        outside.mkdir()
        file = outside / 'keep.json'
        file.write_text('{bad')
        self.symlink(self.folder, outside, target_is_directory=True)
        self.menu.open_replays()
        self.assertEqual(self.menu.replay_paths, [])
        self.assertIn('Cannot browse', self.menu.replay_notice)
        self.click('replay_delete_all')
        self.click('replay_confirm_delete')
        self.assertTrue(file.exists())
        self.assertIn('Cannot delete', self.menu.replay_notice)

    def test_selected_legacy_replay_retains_warning_and_timestamp(self):
        from test_replay_workflow import game
        from game.net.replay import MatchRecording
        data = MatchRecording(game()).to_dict()
        data['initial_state'].pop('runtime_state', None)
        path = self.folder / 'legacy.json'
        path.write_text(json.dumps(data))
        self.menu.open_replays()
        self.click('select_replay', str(path))
        self.menu.render(0.)
        self.assertIn('future-state unavailable', self.menu.replay_rows[str(path)])
        self.assertIn('UTC', self.menu.replay_rows[str(path)])
        self.assertEqual(self.menu.result, MenuResult.NONE)

    def test_delete_failure_is_visible_without_overlapping_text(self):
        path = self.folder / 'broken.json'
        path.write_text('{bad')
        self.menu.open_replays()
        self.click('select_replay', str(path))
        self.click('replay_delete')
        failure_target = ('render.replay_delete_windows._Api.dispose' if os.name == 'nt'
                          else 'render.replay_library.os.unlink')
        with patch(failure_target, side_effect=PermissionError('read only')):
            self.click('replay_confirm_delete')
        self.assertTrue(path.exists())
        self.assertIn('read only', self.menu.replay_notice)
        self.menu.render(0.)
        bounds = self.menu.replay_text_bounds
        self.assertTrue(all(not a.colliderect(b) for i, a in enumerate(bounds) for b in bounds[i+1:]))

    def test_delete_all_includes_files_beyond_browse_cap_and_keeps_other_entries(self):
        for i in range(1007):
            (self.folder / f'{i}.json').write_text('{bad')
        outside = self.root / 'outside.json'
        outside.write_text('preserve')
        self.symlink(self.folder / 'link.json', outside)
        (self.folder / 'notes.txt').write_text('preserve')
        (self.folder / 'nested.json').mkdir()
        (self.folder / 'nested.json' / 'keep.json').write_text('preserve')
        self.menu.open_replays()
        self.assertLessEqual(len(self.menu.replay_paths), 1000)
        self.click('replay_delete_all')
        self.menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertTrue((self.folder / '1006.json').exists())
        self.click('replay_delete_all')
        self.click('replay_confirm_delete')
        self.assertEqual({p.name for p in self.folder.iterdir()}, {'link.json', 'notes.txt', 'nested.json'})
        self.assertEqual(outside.read_text(), 'preserve')
        self.assertIn('1007', self.menu.replay_notice)
        self.assertEqual(self.menu.replay_paths, [])

    def test_selected_delete_refuses_replaced_symlink_and_outside_path(self):
        outside = self.root / 'outside.json'
        outside.write_text('preserve')
        path = self.folder / 'selected.json'
        path.write_text('{bad')
        self.menu.open_replays()
        self.click('select_replay', str(path))
        self.click('replay_delete')
        path.unlink()
        self.symlink(path, outside)
        self.click('replay_confirm_delete')
        self.assertTrue(path.is_symlink())
        self.assertEqual(outside.read_text(), 'preserve')
        self.assertIn('Cannot delete', self.menu.replay_notice)
        self.menu.replay_selected = str(outside)
        self.click('replay_delete')
        self.click('replay_confirm_delete')
        self.assertTrue(outside.exists())

    def test_created_timestamp_orders_renamed_invalid_files_without_reconstruction(self):
        older = self.folder / 'zzz-renamed.json'
        newer = self.folder / 'aaa-copy.json'
        older.write_text('{"created_utc":"2025-01-01T12:00:00+00:00","version":99,"initial_state":{bad')
        newer.write_text('{"created_utc":"2026-01-01T12:00:00Z","initial_state":' + ' ' * 100000 + '{bad')
        os.utime(older, (2000000000, 2000000000))
        os.utime(newer, (1, 1))
        with patch('game.net.replay.load_replay', side_effect=AssertionError('heavy browser parsing')):
            self.menu.open_replays()
            self.menu.render(0.)
        self.assertEqual(self.menu.replay_paths, [str(newer), str(older)])
        self.assertTrue(any('2026-01-01 12:00:00 UTC' in t for t in self.menu.replay_rendered_text))
        self.assertTrue(any('2025-01-01 12:00:00 UTC' in t for t in self.menu.replay_rendered_text))

    def test_corrupt_selection_is_not_playback_and_selected_delete_defaults_cancel(self):
        path = self.folder / 'broken.json'
        path.write_text('{bad')
        self.menu.open_replays()
        self.click('select_replay', str(path))
        self.assertEqual(self.menu.result, MenuResult.NONE)
        self.assertEqual(self.menu.replay_selected, str(path))
        self.click('replay_delete')
        self.assertTrue(path.exists())
        self.menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertTrue(path.exists())
        self.assertIsNone(self.menu.replay_confirmation)
        self.click('replay_delete')
        self.click('replay_confirm_delete')
        self.assertFalse(path.exists())
        self.assertIsNone(self.menu.replay_selected)
        self.menu.render(0.)
        self.assertTrue(any('No replays' in t for t in self.menu.replay_rendered_text))
        self.assertEqual(self.menu.replay_page, 0)
