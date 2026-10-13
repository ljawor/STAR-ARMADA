"""Saved-game library; all persistence confined to disposable roots."""
import ast
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class SaveLibraryTests(unittest.TestCase):
    def test_saved_games_real_gl_diagnostic_is_available(self):
        self.assertTrue((ROOT / 'tools/diag_saved_games.py').is_file(),
                        'Saved-games real main-loop/GL acceptance diagnostic missing')

    def test_namespace_is_fail_closed_even_for_corrupt_managed_files(self):
        from render import save_library as lib
        for name in ('quicksave.json', 'autosave.json', 'autosave_0.json', 'autosave_123.json'):
            self.assertTrue(lib.managed_name(name), name)
        for name in ('settings.json', 'SETTINGS.JSON', 'campaign.json', 'CAMPAIGN.json',
                     'match-123.json', 'manual.json', 'autosave_x.json', 'autosave_².json',
                     '../quicksave.json', 'QUICKSAVE.json', 'autosave_1.json.bak'):
            self.assertFalse(lib.managed_name(name), name)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('quicksave.json', 'autosave_0.json', 'settings.json'):
                (root / name).write_text('broken')
            os.utime(root / 'autosave_0.json', (100, 100))
            os.utime(root / 'quicksave.json', (200, 200))
            rows, notice = lib.browse(str(root))
            self.assertEqual([Path(p).name for p in rows], ['quicksave.json', 'autosave_0.json'])
            self.assertIn('UTC', rows[str(root / 'quicksave.json')][1])
            self.assertIn('Quick', rows[str(root / 'quicksave.json')][2])


    def test_windows_browsing_reads_metadata_only_through_safe_file_handles(self):
        import io
        from unittest.mock import Mock
        from render import save_library as lib
        native = Mock()
        native.__enter__ = Mock(return_value=native)
        native.__exit__ = Mock(return_value=False)
        native.api.entries.return_value = iter([('quicksave.json', 0), ('settings.json', 0),
                                               ('autosave_1.json', 0x400)])
        stream = io.BytesIO(b'broken')
        stream.fileno = lambda: 123
        with patch.object(lib, '_WINDOWS', True), \
                patch('render.replay_delete_windows.Folder', return_value=native), \
                patch.object(lib, 'open_selected', return_value=stream) as safe_open, \
                patch.object(lib.os, 'fstat', return_value=Mock(st_mtime=200, st_mode=0o100600)), \
                patch.object(lib.os, 'stat', side_effect=AssertionError('unpinned metadata path')):
            rows, notice = lib.browse('/isolated/saves')
        self.assertEqual(len(rows), 1)
        self.assertEqual(notice, '')
        safe_open.assert_called_once()
        self.assertIn('Corrupt JSON', next(iter(rows.values()))[2])

    def test_one_unreadable_row_does_not_hide_other_saves(self):
        from render import save_library as lib
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('quicksave.json', 'autosave.json'):
                (root / name).write_text('broken')
            original = lib.metadata
            def unreadable(fd, name):
                if name == 'quicksave.json':
                    raise PermissionError('fixture unreadable')
                return original(fd, name)
            with patch.object(lib, 'metadata', side_effect=unreadable):
                rows, notice = lib.browse(str(root))
            self.assertEqual(len(rows), 2)
            self.assertIn('unavailable', rows[str(root / 'quicksave.json')][2])
            self.assertIn('unreadable', notice)

    def test_windows_bulk_filter_uses_native_stream_and_protects_mixed_directory(self):
        from unittest.mock import Mock
        from render import save_library as lib
        native = Mock()
        native.__enter__ = Mock(return_value=native)
        native.__exit__ = Mock(return_value=False)
        native.api.entries.return_value = iter([('settings.json', 0), ('CAMPAIGN.JSON', 0),
            ('unknown.json', 0), ('match-1.json', 0), ('quicksave.json', 0),
            ('autosave.json', 0x400), ('autosave_0.json', 0x10), ('autosave_1.json', 0)])
        native.delete.side_effect = [None, OSError('fixture locked')]
        with patch.object(lib, '_WINDOWS', True), \
                patch('render.replay_delete_windows.Folder', return_value=native), \
                patch.object(lib.os, 'scandir', side_effect=AssertionError('native stream required')):
            self.assertEqual(lib.delete_all('/isolated/saves'), (1, 1, 'fixture locked'))
        self.assertEqual([call.args[0] for call in native.delete.call_args_list],
                         ['quicksave.json', 'autosave_1.json'])

    def test_browse_retains_newest_scanned_subset_and_never_constructs_managers(self):
        from render import save_library as lib
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for i in range(8):
                path = root / f'autosave_{i}.json'
                path.write_bytes(b'{bad' + b' ' * lib.HEADER_BYTES)
                os.utime(path, (i + 10, i + 10))
            with patch.object(lib, 'BROWSE_CAP', 3), \
                    patch('game.core.manager.GameManager.__init__', side_effect=AssertionError('browser simulation')):
                rows, notice = lib.browse(str(root))
            self.assertEqual([Path(p).name for p in rows], ['autosave_7.json', 'autosave_6.json', 'autosave_5.json'])
            self.assertIn('Browser limit', notice)
            with patch.object(lib, 'SCAN_CAP', 2):
                rows, notice = lib.browse(str(root))
            self.assertEqual(len(rows), 2)
            self.assertIn('Scan limit', notice)

    def test_delete_all_streams_beyond_caps_and_preserves_unmanaged_files(self):
        from render import save_library as lib
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'saves'
            folder.mkdir()
            protected = ('settings.json', 'SETTINGS.json', 'campaign.json', 'Campaign.json',
                         'manual.json', 'match-replay.json', 'screen.png', 'autosave_x.json')
            for name in protected:
                (folder / name).write_text('sentinel')
            for index in range(lib.SCAN_CAP + 2):
                (folder / f'autosave_{index}.json').write_text('corrupt')
            outside = root / 'outside.json'
            outside.write_text('outside')
            (folder / 'quicksave.json').symlink_to(outside)
            with self.assertRaises(OSError):
                lib.delete_selected(str(folder), str(folder / 'settings.json'))
            with self.assertRaises(OSError):
                lib.delete_selected(str(folder), str(outside))
            with self.assertRaises(OSError):
                lib.delete_selected(str(folder), str(folder / 'quicksave.json'))
            self.assertEqual(lib.delete_all(str(folder)), (lib.SCAN_CAP + 2, 0, ''))
            self.assertEqual(outside.read_text(), 'outside')
            for name in protected:
                self.assertEqual((folder / name).read_text(), 'sentinel')
            self.assertTrue((folder / 'quicksave.json').is_symlink())
            linked = root / 'linked'
            linked.symlink_to(folder, target_is_directory=True)
            with self.assertRaises(OSError):
                lib.delete_all(str(linked))
            self.assertIn('Cannot browse', lib.browse(str(linked))[1])


class SavedMenuTests(unittest.TestCase):
    def setUp(self):
        import pygame
        from render import menus
        pygame.display.init()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'saves'
        self.folder.mkdir()
        scope = patch.multiple(menus, USER_DIR=str(self.root), SAVES_DIR=str(self.folder),
                               SETTINGS_PATH=str(self.folder / 'settings.json'),
                               CAMPAIGN_PATH=str(self.folder / 'campaign.json'))
        scope.start()
        self.addCleanup(scope.stop)
        self.menu = menus.MenuStack(800, 600)
        self.addCleanup(self.menu.close)
        self.menu.settings['cinematics_enabled'] = False
        self.pygame = pygame

    def click(self, action, payload=None):
        self.menu.render(0)
        b = next(b for b in self.menu.buttons if b['action'] == action and
                 (payload is None or b['payload'] == payload))
        self.menu.handle_event(self.pygame.event.Event(self.pygame.MOUSEBUTTONDOWN,
                                                     button=1, pos=b['rect'].center))

    def test_deletion_modal_is_exclusive_cancel_default_and_refreshes(self):
        for index in range(9):
            (self.folder / f'autosave_{index}.json').write_text('broken')
        protected = self.folder / 'settings.json'
        protected.write_text('sentinel')
        self.menu.open_saved_games()
        self.click('save_page', 1)
        self.assertEqual(self.menu.save_page, 1)
        self.click('select_save')
        selected = Path(self.menu.save_selected)
        self.click('save_delete')
        self.menu.render(0)
        self.assertEqual({b['action'] for b in self.menu.buttons},
                         {'save_cancel_delete', 'save_confirm_delete'})
        for key in (self.pygame.K_RETURN, self.pygame.K_ESCAPE, self.pygame.K_KP_ENTER):
            self.menu.handle_event(self.pygame.event.Event(self.pygame.KEYDOWN, key=key))
            self.assertIsNone(self.menu.save_confirmation)
            self.assertTrue(selected.exists())
            self.click('save_delete')
        self.click('save_confirm_delete')
        self.assertFalse(selected.exists())
        self.assertEqual(self.menu.save_page, 1)
        self.click('save_delete_all')
        self.click('save_confirm_delete')
        self.assertEqual(self.menu.save_paths, [])
        self.assertEqual(protected.read_text(), 'sentinel')
        self.assertIn('Deleted 8', self.menu.save_notice)
        self.menu.render(0)
        self.assertNotIn('load_save', [b['action'] for b in self.menu.buttons])
        self.click('goto_main')
        self.assertEqual(self.menu.screen, 'main')

    def factories(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from game.core.manager import GameManager
        from game.core.state import GameState
        from game.data.store import DataStore
        tree = ast.parse((ROOT / 'main.py').read_text())
        ns = dict(GameManager=GameManager, GameState=GameState, DataStore=DataStore,
                  MODS=[], W=800, H=600, gm=None, state=None, camera=None, renderer=None,
                  hud=None, audio=None, inputc=None, net_session=None, local_player=0,
                  accumulator=0., last_autosave=0., menu=self.menu, mode='menu', paused=False,
                  TICK_DT=1/30, Audio=object, SETTINGS={}, json=json, os=os, SAVES_DIR=str(self.folder),
                  recording=None, playback=None, mission_def=None, presentation=None)
        for name in ('Camera', 'Renderer', 'HUD', 'InputController'):
            ns[name] = Mock(side_effect=lambda *a: SimpleNamespace(close=Mock(), zoom=Mock(), set_camera_ref=Mock()))
        ns['_AppGlue'] = lambda: None
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)],
                               type_ignores=[]), 'main.py', 'exec'), ns)
        ns['make_audio'] = Mock(side_effect=lambda state: SimpleNamespace(cleanup=Mock(), set_camera=Mock()))
        return ns

    def test_explicit_load_uses_production_factory_and_continues_campaign_canonically(self):
        from game.core.manager import GameManager
        from game.data.store import DataStore
        from render.menus import MenuResult
        ds = DataStore.get()
        definition = self.menu.campaign['missions'][0]
        source = GameManager.start_mission(ds.maps[definition['map']], definition)
        for _ in range(45):
            source.step(1/30)
        path = self.folder / 'quicksave.json'
        writer = self.factories()
        writer['state'] = source.state
        writer['write_save'](str(path))
        self.menu.open_saved_games()
        self.click('select_save', str(path))
        self.click('load_save')
        ns = self.factories()
        self.assertIn('load_saved_game', ns, 'main saved-game result handler missing')
        self.assertTrue(ns['load_saved_game'](self.menu.result_payload))
        self.assertEqual(ns['mode'], 'game')
        loaded = ns['gm']
        normalize = lambda manager: json.loads(json.dumps(manager.state.to_dict(precise=True)))
        self.assertEqual(normalize(loaded), normalize(source))
        self.assertEqual(ns['mission_def'], source.mission.mission)
        for tick in range(120):
            source.step(1/30)
            loaded.step(1/30)
            self.assertEqual(normalize(loaded), normalize(source), f'continuation tick {tick}')
        self.assertIsNone(ns.get('cinematic'))
        self.assertEqual(self.menu.result, MenuResult.LOAD_GAME)

    def test_reconstruction_errors_leave_live_graph_and_menu_usable(self):
        from unittest.mock import Mock
        from game.core.manager import GameManager
        from game.data.store import DataStore
        for defect in ('zero_visibility', 'empty_position'):
            with self.subTest(defect=defect):
                ns = self.factories()
                previous = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
                prior_ds = DataStore.get()
                resources = {key: Mock() for key in
                             ('renderer', 'hud', 'audio', 'presentation', 'net_session')}
                recording = Mock(user_dir=str(self.root))
                ns.update(gm=previous, state=previous.state, recording=recording, **resources)
                data = previous.state.to_dict()
                data.pop('runtime_state')
                if defect == 'zero_visibility':
                    data['visibility_cell_size'] = 0
                else:
                    next(iter(data['entities'].values()))['pos'] = []
                path = self.folder / 'quicksave.json'
                path.write_text(json.dumps(data))
                self.assertFalse(ns['load_saved_game'](str(path)))
                self.assertIs(ns['gm'], previous)
                self.assertIs(ns['state'], previous.state)
                self.assertIs(ns['recording'], recording)
                self.assertEqual(recording.mock_calls, [])
                for key, resource in resources.items():
                    self.assertIs(ns[key], resource)
                    self.assertEqual(resource.mock_calls, [])
                self.assertIs(DataStore.get(), prior_ds)
                self.assertEqual(ns['mode'], 'menu')
                self.assertEqual(self.menu.screen, 'saved_games')
                self.assertIn('Cannot load', self.menu.save_notice)
                self.menu.render(0)
                self.assertIn('save_refresh', [b['action'] for b in self.menu.buttons])

    def test_invalid_mission_definition_or_progress_is_inert(self):
        from unittest.mock import Mock
        from game.core.manager import GameManager
        from game.data.store import DataStore
        for field in ('definition', 'progress'):
            with self.subTest(field=field):
                ns = self.factories()
                previous = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
                prior_ds = DataStore.get()
                resources = {key: Mock() for key in
                             ('renderer', 'hud', 'audio', 'presentation', 'net_session')}
                recording = Mock(user_dir=str(self.root))
                ns.update(gm=previous, state=previous.state, recording=recording, **resources)
                data = previous.state.to_dict()
                data.pop('runtime_state')
                definition = dict(type='survive_time', time=10)
                progress = dict(definition, done=False)
                if field == 'definition':
                    definition['time'] = 'bad'
                else:
                    progress['time'] = 'bad'
                data['mission_state'] = dict(definition=dict(objectives=[definition]),
                                             objectives=[progress])
                path = self.folder / 'quicksave.json'
                path.write_text(json.dumps(data))
                self.assertFalse(ns['load_saved_game'](str(path)))
                self.assertIs(ns['gm'], previous)
                self.assertIs(ns['state'], previous.state)
                self.assertIs(ns['recording'], recording)
                self.assertEqual(recording.mock_calls, [])
                for key, resource in resources.items():
                    self.assertIs(ns[key], resource)
                    self.assertEqual(resource.mock_calls, [])
                self.assertIs(DataStore.get(), prior_ds)
                self.assertEqual(ns['mode'], 'menu')
                self.menu.render(0)
                self.assertIn('save_refresh', [b['action'] for b in self.menu.buttons])

    def test_future_save_format_is_rejected_before_reconstruction(self):
        from game.core.manager import GameManager
        from game.data.store import DataStore
        ns = self.factories()
        previous = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
        ns.update(gm=previous, state=previous.state)
        data = previous.state.to_dict()
        data['format'] = 999
        path = self.folder / 'quicksave.json'
        path.write_text(json.dumps(data))
        self.assertFalse(ns['load_saved_game'](str(path)))
        self.assertIs(ns['gm'], previous)
        self.assertIn('format', self.menu.save_notice)

    def test_supported_legacy_save_uses_existing_fallback_and_loads(self):
        from game.core.manager import GameManager
        from game.data.store import DataStore
        ns = self.factories()
        source = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
        data = source.state.to_dict()
        data.pop('runtime_state')
        path = self.folder / 'quicksave.json'
        path.write_text(json.dumps(data))
        self.assertTrue(ns['load_saved_game'](str(path)))
        self.assertEqual(ns['mode'], 'game')
        self.assertEqual(ns['state'].tick, source.state.tick)
        self.assertEqual(set(ns['state'].entities), set(source.state.entities))

    def test_legacy_campaign_restores_progress_and_continues_120_ticks_without_intro(self):
        from unittest.mock import Mock
        from game.core.manager import GameManager
        from game.core.state import GameState
        from game.data.store import DataStore
        definition = self.menu.campaign['missions'][0]
        source = GameManager.start_mission(DataStore.get().maps[definition['map']], definition)
        for _ in range(45):
            source.step(1/30)
        data = json.loads(json.dumps(source.state.to_dict(precise=True)))
        data.pop('runtime_state')
        # Historical saves cannot recover AI/timers that were never persisted;
        # compare continuation with the supported ordinary legacy decoder.
        baseline = GameManager(state=GameState.from_dict(data))
        path = self.folder / 'quicksave.json'
        path.write_text(json.dumps(data))
        ns = self.factories()
        intro = Mock()
        ns['start_campaign_presentation'] = intro
        self.assertTrue(ns['load_saved_game'](str(path)))
        loaded = ns['gm']
        normalize = lambda manager: json.loads(json.dumps(manager.state.to_dict(precise=True)))
        self.assertEqual(loaded.mission.to_dict(), source.mission.to_dict())
        self.assertEqual(normalize(loaded), normalize(baseline))
        for tick in range(120):
            baseline.step(1/30)
            loaded.step(1/30)
            self.assertEqual(normalize(loaded), normalize(baseline), f'legacy continuation tick {tick}')
        intro.assert_not_called()
        self.assertIsNone(ns.get('cinematic'))

    def test_malformed_legacy_candidate_is_validated_before_ownership_changes(self):
        from unittest.mock import Mock
        from game.core.manager import GameManager
        from game.data.store import DataStore
        ns = self.factories()
        previous = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
        recording = Mock()
        recording.user_dir = str(self.root)
        renderer = Mock()
        ns.update(gm=previous, state=previous.state, recording=recording, renderer=renderer)
        data = previous.state.to_dict()
        data.pop('runtime_state')
        data['time'] = 'invalid legacy time'
        path = self.folder / 'quicksave.json'
        path.write_text(json.dumps(data))
        self.assertFalse(ns['load_saved_game'](str(path)))
        self.assertIs(ns['gm'], previous)
        self.assertIs(ns['recording'], recording)
        recording.close.assert_not_called()
        renderer.close.assert_not_called()
        self.assertIn('Cannot load', self.menu.save_notice)

    def test_incompatible_canonical_save_and_symlink_never_replace_live_state(self):
        from game.core.manager import GameManager
        from game.data.store import DataStore
        ns = self.factories()
        previous = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
        ns.update(gm=previous, state=previous.state)
        data = previous.state.to_dict()
        data['runtime_state']['version'] = 999
        path = self.folder / 'quicksave.json'
        path.write_text(json.dumps(data))
        self.assertFalse(ns['load_saved_game'](str(path)))
        self.assertIn('future-state', self.menu.save_notice)
        self.assertIs(ns['gm'], previous)
        path.unlink()
        outside = self.root / 'outside.json'
        outside.write_text(json.dumps(previous.state.to_dict()))
        original = outside.read_bytes()
        path.symlink_to(outside)
        self.assertFalse(ns['load_saved_game'](str(path)))
        self.assertIs(ns['gm'], previous)
        self.assertEqual(outside.read_bytes(), original)

    def test_oversized_save_rejects_before_json_decode_and_resource_teardown(self):
        from render import save_library as lib
        ns = self.factories()
        path = self.folder / 'quicksave.json'
        path.write_bytes(b' ' * 128)
        with patch.object(lib, 'MAX_SAVE_BYTES', 64, create=True):
            self.assertFalse(ns['load_saved_game'](str(path)))
        self.assertIn('size limit', self.menu.save_notice)
        self.assertIsNone(ns['gm'])

    def test_bad_load_keeps_previous_graph_recording_resources_and_menu_usable(self):
        from unittest.mock import Mock
        ns = self.factories()
        self.assertIn('load_saved_game', ns)
        previous = object()
        renderer = Mock()
        recording = Mock()
        ns.update(gm=previous, renderer=renderer, recording=recording)
        path = self.folder / 'quicksave.json'
        for payload in ('{broken', '[]', '{}', '{"runtime_state":{"version":999}}'):
            path.write_text(payload)
            self.assertFalse(ns['load_saved_game'](str(path)))
            self.assertIs(ns['gm'], previous)
            self.assertIs(ns['recording'], recording)
            renderer.close.assert_not_called()
            recording.close.assert_not_called()
            self.assertEqual(ns['mode'], 'menu')
            self.assertEqual(self.menu.screen, 'saved_games')
            self.assertIn('Cannot load', self.menu.save_notice)
            self.menu.render(0)
            self.assertIn('save_refresh', [b['action'] for b in self.menu.buttons])
        path.unlink()
        self.assertFalse(ns['load_saved_game'](str(path)))
        protected = self.folder / 'settings.json'
        protected.write_text('{}')
        self.assertFalse(ns['load_saved_game'](str(protected)))
        self.assertEqual(protected.read_text(), '{}')

    def test_main_entry_selection_is_passive_load_is_explicit(self):
        from render.menus import MenuResult
        self.menu.screen = 'main'
        self.menu.render(0)
        self.assertEqual([b['action'] for b in self.menu.buttons],
                         ['start_skirmish', 'goto_lan', 'goto_campaign', 'goto_saved_games',
                          'goto_replays', 'goto_settings', 'exit'])
        path = self.folder / 'quicksave.json'
        path.write_text('corrupt')
        self.click('goto_saved_games')
        self.assertEqual(self.menu.screen, 'saved_games')
        self.click('select_save', str(path))
        self.assertEqual(self.menu.result, MenuResult.NONE)
        self.assertEqual(self.menu.save_selected, str(path))
        self.click('load_save')
        self.assertEqual(self.menu.result, MenuResult.LOAD_GAME)
        self.assertEqual(self.menu.result_payload, str(path))
        self.assertTrue(path.exists())


if __name__ == '__main__':
    unittest.main()
