"""Render-only selection preferences and explicit session boundaries."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SelectionPreferencesTests(unittest.TestCase):
    def test_absent_preference_stays_legacy(self):
        from render.asset_selection import selection_preferences
        self.assertEqual(selection_preferences({}),
                         {'model_preview': False, 'visual_packs': []})
    def test_explicit_preview_and_enabled_order_survive_settings_roundtrip(self):
        import game.core
        from render import menus
        from render.asset_selection import selection_preferences
        settings = dict(menus.DEFAULT_SETTINGS, model_preview=True,
                        visual_packs=['escort-red', 'escort-blue'])
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(menus, 'SETTINGS_PATH', str(Path(tmp) / 'settings.json')):
                menus.save_settings(settings)
                loaded = menus.load_settings()
        self.assertEqual(selection_preferences(loaded),
                         {'model_preview': True,
                          'visual_packs': ['escort-red', 'escort-blue']})
        self.assertEqual(loaded['music_volume'], settings['music_volume'])
    def test_pack_preferences_reject_duplicates_and_unsafe_names(self):
        from render.asset_selection import selection_preferences
        for value in (None, 'pack', {}, ['x', 'x'], ['../x'], ['/x'],
                      ['a/b'], ['a\\b'], [False], [''], ['a'] * 33):
            with self.subTest(value=value), self.assertRaises(ValueError):
                selection_preferences({'model_preview': True, 'visual_packs': value})
    def test_menu_defaults_and_bad_pack_list_are_safe(self):
        import game.core
        from render import menus
        self.assertIs(menus.DEFAULT_SETTINGS.get('model_preview'), False)
        self.assertEqual(menus.DEFAULT_SETTINGS.get('visual_packs'), [])
        with self.assertWarnsRegex(RuntimeWarning, 'using legacy models'):
            clean = menus.validate_presentation_settings(
                {'model_preview': True, 'visual_packs': ['../escape'], 'custom': 17})
        self.assertIs(clean['model_preview'], False)
        self.assertEqual(clean['visual_packs'], [])
        self.assertEqual(clean['custom'], 17)
    def test_preview_control_is_reachable_and_persists_from_natural_input(self):
        import game.core
        import pygame
        from render import menus, i18n
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saves = root / 'saves'
            with patch.multiple(menus, USER_DIR=str(root), SAVES_DIR=str(saves),
                                SETTINGS_PATH=str(saves / 'settings.json'),
                                CAMPAIGN_PATH=str(saves / 'campaign.json'),
                                BALANCE_PATH=str(saves / 'balance.json')):
                owned_display = not pygame.display.get_init()
                if owned_display:
                    pygame.display.init()
                menu = menus.MenuStack(800, 600)
                try:
                    menu.screen = 'settings'
                    menu.settings_page = 0
                    for _ in range(3):
                        menu.buttons = []
                        menu.render(0)
                        rows = [b for b in menu.buttons
                                if b.get('payload') == {'key': 'model_preview'}]
                        if rows:
                            break
                        menu.handle_event(pygame.event.Event(pygame.KEYDOWN,
                                                            key=pygame.K_PAGEDOWN))
                    self.assertEqual(len(rows), 1, 'no reachable model preview control')
                    row = rows[0]
                    self.assertTrue(pygame.Rect(0, 0, 800, 600).contains(row['rect']))
                    menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                                        button=1, pos=row['rect'].center))
                    self.assertIs(menu.settings['model_preview'], True)
                    menu.apply_pending()
                    self.assertIs(menus.load_settings()['model_preview'], True)
                finally:
                    menu.close()
                    if owned_display:
                        pygame.display.quit()
    def test_legacy_boundary_has_visible_diagnostics_and_no_resolver_io(self):
        from render import asset_selection as selection
        before = {'model_preview': False, 'visual_packs': []}
        result = selection.configure(before)
        self.assertEqual(result['mode'], 'legacy')
        self.assertEqual(result['enabled_order'], [])
        self.assertIsNone(selection.mesh_for('rebel:frigate'))
        self.assertFalse(selection.is_authored('rebel:frigate'))
        self.assertEqual(before, {'model_preview': False, 'visual_packs': []})
    def test_selection_cannot_change_with_live_renderer_ownership(self):
        from render import asset_selection as selection
        selection.configure({})
        generation = selection.diagnostics()['generation']
        first, second = selection.attach_renderer(), selection.attach_renderer()
        try:
            with self.assertRaisesRegex(RuntimeError, 'session boundary'):
                selection.configure({})
            selection.release_renderer(first)
            with self.assertRaises(RuntimeError):
                selection.configure({})
            self.assertEqual(selection.diagnostics()['generation'], generation)
        finally:
            selection.release_renderer(first)
            selection.release_renderer(second)
        selection.configure({})
        self.assertGreater(selection.diagnostics()['generation'], generation)
    def test_session_boundary_invalidates_bounds_and_contact_helpers(self):
        import game.core
        from render import asset_selection as selection, ship_sizes, camera_geometry
        ship_sizes._bounds('needle')
        ship_sizes._ray_mesh('needle')
        camera_geometry.station_bounds('shipyard', 'rebel')
        camera_geometry.station_radius('shipyard', 'rebel')
        ship_sizes._station_ray_mesh('rebel', 'shipyard')
        caches = [ship_sizes._bounds, ship_sizes._ray_mesh,
                  ship_sizes._station_ray_mesh, camera_geometry._station_bounds,
                  camera_geometry._station_radius]
        self.assertTrue(all(f.cache_info().currsize for f in caches))
        selection.configure({})
        self.assertTrue(all(f.cache_info().currsize == 0 for f in caches))
    def test_preview_uses_generic_resolver_and_can_return_to_legacy(self):
        from render import asset_selection as selection
        from render.authored_mesh import load_frigate
        root = Path(__file__).resolve().parents[1]
        try:
            result = selection.configure({'model_preview': True}, asset_root=root)
            self.assertEqual(result['mode'], 'preview')
            self.assertEqual(selection.mesh_for('rebel:frigate'),
                             load_frigate(root / 'assets/models/alliance_frigate.mesh.json'))
            self.assertTrue(selection.is_authored('rebel:frigate'))
            self.assertFalse(selection.is_authored('rebel:corvette'))
            import json
            json.dumps(selection.diagnostics())
        finally:
            selection.configure({})
        self.assertIsNone(selection.mesh_for('rebel:frigate'))
    def test_persisted_pack_order_drives_resolver_without_touching_settings(self):
        import shutil
        from test_asset_registry import PackTests
        from render import asset_selection as selection
        root = Path(__file__).resolve().parents[1]
        first, second = PackTests.pack(self), PackTests.pack(self, 'test:second')
        with tempfile.TemporaryDirectory() as tmp:
            packs = Path(tmp)
            shutil.copytree(first.parent, packs / 'first')
            shutil.copytree(second.parent, packs / 'second')
            settings = {'model_preview': True, 'visual_packs': ['first', 'second']}
            try:
                result = selection.configure(settings, asset_root=root, pack_root=packs)
                self.assertEqual(result['enabled_order'], ['first', 'second'])
                self.assertNotEqual(selection.mesh_for('rebel:frigate'),
                                    __import__('render.authored_mesh', fromlist=['frigate_mesh']).frigate_mesh())
                self.assertEqual(result['pack_order'][-1]['pack_id'], 'test:second')
                import json
                json.dumps(result)
                self.assertEqual(settings['visual_packs'], ['first', 'second'])
            finally:
                selection.configure({})
    def test_enabled_pack_directory_symlink_cannot_escape_external_root(self):
        import shutil
        from test_asset_registry import PackTests
        from render import asset_selection as selection
        root = Path(__file__).resolve().parents[1]
        pack = PackTests.pack(self)
        with tempfile.TemporaryDirectory() as tmp:
            packs = Path(tmp)
            (packs / 'escape').symlink_to(pack.parent, target_is_directory=True)
            shutil.copytree(pack.parent, packs / 'good')
            try:
                result = selection.configure({'model_preview': True,
                                              'visual_packs': ['escape', 'good']},
                                             asset_root=root, pack_root=packs)
                self.assertFalse(result['pack_order'][0]['accepted'])
                self.assertEqual(result['pack_order'][0]['code'], 'E_SYMLINK_ESCAPE')
                self.assertTrue(result['pack_order'][1]['accepted'])
            finally:
                selection.configure({})


if __name__ == '__main__':
    unittest.main()
