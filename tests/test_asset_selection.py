"""Render-only selection preferences and explicit session boundaries."""
import os
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
        self.assertIs(menus.DEFAULT_SETTINGS.get('model_preview'), True)
        # The fourteen shipped packs cover the approved Imperium ships/stations,
        # including the seven remaining ship bindings in the fleet pack.
        self.assertEqual(menus.DEFAULT_SETTINGS.get('visual_packs'),
                         ['vigil-prototype', 'imperium-command-prototype',
                          'imperium-shipyard-prototype', 'imperium-mining-prototype',
                          'imperium-talon-prototype', 'imperium-engineer-prototype',
                          'imperium-research-prototype', 'imperium-defense-prototype',
                          'imperium-sensor-prototype', 'imperium-trade-prototype',
                          'imperium-fighter-prototype', 'imperium-repair-prototype',
                          'imperium-relay-prototype', 'imperium-fleet-prototypes'])
        with self.assertWarnsRegex(RuntimeWarning, 'using legacy models'):
            clean = menus.validate_presentation_settings(
                {'model_preview': True, 'visual_packs': ['../escape'], 'custom': 17})
        self.assertIs(clean['model_preview'], False)
        self.assertEqual(clean['visual_packs'], [])
        self.assertEqual(clean['custom'], 17)
    def test_the_approved_catalogue_is_on_and_has_no_control(self):
        """#160: the preview is no longer a switch, so nothing may offer one and the catalogue stays on."""
        import game.core
        import pygame
        from render import menus
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saves = root / 'saves'
            settings_path = saves / 'settings.json'
            with patch.multiple(menus, USER_DIR=str(root), SAVES_DIR=str(saves),
                                SETTINGS_PATH=str(settings_path),
                                CAMPAIGN_PATH=str(saves / 'campaign.json'),
                                BALANCE_PATH=str(saves / 'balance.json')):
                # A file that carries the retired opt-out must still play the approved catalogue.
                saves.mkdir(parents=True, exist_ok=True)
                settings_path.write_text('{"model_preview": false}')
                self.assertIs(menus.load_settings()['model_preview'], True)
                owned_display = not pygame.display.get_init()
                if owned_display:
                    pygame.display.init()
                menu = menus.MenuStack(800, 600)
                try:
                    menu.screen = 'settings'
                    offered = set()
                    for page in range(8):
                        menu.settings_page = page
                        menu.buttons = []
                        menu.render(0)
                        offered |= {tuple(sorted((b.get('payload') or {}).get('key', '').split()))
                                    for b in menu.buttons if isinstance(b.get('payload'), dict)}
                    self.assertNotIn(('model_preview',), offered,
                                     'the retired preview switch is still reachable')
                    self.assertIn(('high_contrast_ui',), offered,
                                  'the remaining readability controls must still be drawn')
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
            self.assertTrue(selection.is_authored('rebel:corvette'))
            self.assertTrue(selection.is_authored('shared:construction_scaffold'))
            self.assertIsNotNone(selection.mesh_for('shared:construction_scaffold'))
            self.assertFalse(selection.is_authored('syndicate:bomber'))
            import json
            json.dumps(selection.diagnostics())
        finally:
            selection.configure({})
        self.assertIsNone(selection.mesh_for('rebel:frigate'))
        self.assertIsNone(selection.mesh_for('rebel:corvette'))
        self.assertIsNone(selection.mesh_for('shared:construction_scaffold'))
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


class SelectionLanguageTests(unittest.TestCase):
    LABELS = ('Changes apply at the next session, never during a battle.',)
    # #160 removed the renderer, preview and pack-order rows. Their labels must leave the catalogue
    # with them, or the language pipeline keeps translating controls the game no longer draws.
    RETIRED = (
        'Renderer (next session)',
        'Blender model preview (next session)',
        'Enabled visual packs (saved order)',
        '{count} enabled · settings.json',
        'Preview is opt-in; OFF keeps stock legacy models.',
        'Pack order: visual_packs in settings.json; later entries win.',
    )

    def test_retired_rows_left_the_language_catalogue(self):
        from tools import lang_coverage as coverage
        for key in self.RETIRED:
            with self.subTest(key=key):
                self.assertNotIn(key, coverage.catalogue())

    def test_preview_labels_have_authored_translations_in_every_registered_pack(self):
        import json
        from render import i18n
        from tools import build_lang_packs as builder, lang_coverage as coverage
        root = Path(__file__).resolve().parents[1]
        self.assertNotIn('Invalid visual pack preferences; using legacy models',
                         coverage.catalogue())
        for code, _ in i18n.LANGUAGES:
            pack = json.loads((root / f'assets/data/lang/{code}.json').read_text(
                encoding='utf-8'))
            source = builder.load_source(code)[0] if code != 'en' else pack
            for key in self.LABELS:
                with self.subTest(code=code, key=key):
                    self.assertIn(key, coverage.catalogue())
                    self.assertIn(key, pack)
                    self.assertEqual(pack[key], source[key])
                    self.assertTrue(pack[key].strip())
                    if code != 'en':
                        self.assertNotEqual(pack[key], key)

    def test_no_settings_page_offers_a_retired_control(self):
        """#160: walking every page must not find a row the owner retired."""
        import game.core
        import pygame
        from render import menus, clean_classic
        owned_font = not pygame.font.get_init()
        owned_display = not pygame.display.get_init()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saves = root / 'saves'
            with patch.multiple(menus, USER_DIR=str(root), SAVES_DIR=str(saves),
                                SETTINGS_PATH=str(saves / 'settings.json'),
                                CAMPAIGN_PATH=str(saves / 'campaign.json'),
                                BALANCE_PATH=str(saves / 'balance.json')):
                if owned_display:
                    pygame.display.init()
                menu = None
                try:
                    menu = menus.MenuStack(800, 600)
                    menu.screen = 'settings'
                    seen_actions, seen_keys, pages = set(), set(), 0
                    for page in range(8):
                        menu.settings_page = page
                        menu.buttons = []
                        menu.render(0)
                        if menu.settings_page != page:
                            break
                        pages += 1
                        for button in menu.buttons:
                            seen_actions.add(button.get('action'))
                            payload = button.get('payload')
                            if isinstance(payload, dict) and 'key' in payload:
                                seen_keys.add(payload['key'])
                            elif isinstance(payload, str):
                                seen_keys.add(payload)
                    self.assertGreaterEqual(pages, 4, 'the settings walk did not reach every page')
                    self.assertFalse(seen_actions & {'cycle_renderer', 'pack_order'},
                                     f'retired actions are still offered: {seen_actions}')
                    self.assertFalse(seen_keys & {'renderer', 'model_preview', 'visual_packs'},
                                     f'retired rows are still drawn: {seen_keys}')
                    for label in SelectionLanguageTests.RETIRED:
                        self.assertNotIn(label, menu.settings_rendered_text)
                finally:
                    if menu is not None:
                        menu.close()
                    if owned_font:
                        clean_classic.font.cache_clear()
                        pygame.font.quit()
                    if owned_display:
                        pygame.display.quit()

    def test_only_language_catalogues_force_lf_checkout(self):
        import os
        import shutil
        import subprocess
        from render import i18n
        if shutil.which('git') is None:
            self.skipTest('git is required to inspect checkout attributes')
        root = Path(__file__).resolve().parents[1]
        catalogues = [f'assets/data/lang/{code}.json' for code, _ in i18n.LANGUAGES]
        runtime = ['assets/models/alliance_frigate.mesh.json',
                   'assets/models/registry.json',
                   'assets/models/manifests/alliance_frigate.json',
                   'art/manifests/pipeline.json',
                   'art/schemas/model-manifest.schema.json',
                   'artifacts/alliance_visual_slice/probe.json',
                   'tools/art/alliance_common.py']
        controls = ['unrelated/probe.blend', 'assets/data/ships/ships.json']
        result = subprocess.run(
            ['git', '-c', f'core.attributesFile={os.devnull}', 'check-attr',
             'text', 'eol', '--', *catalogues, *runtime, *controls],
            cwd=root, env=dict(os.environ, GIT_ATTR_NOSYSTEM='1'),
            check=True, capture_output=True, encoding='utf-8')
        attributes = {}
        for line in result.stdout.splitlines():
            path, attribute, value = line.split(': ', 2)
            attributes.setdefault(path, {})[attribute] = value
        for path in catalogues:
            with self.subTest(path=path):
                self.assertEqual(attributes[path], {'text': 'set', 'eol': 'lf'})
        for path in runtime:
            with self.subTest(path=path):
                self.assertEqual(attributes[path], {'text': 'unset', 'eol': 'unspecified'})
        for path in controls:
            with self.subTest(path=path):
                self.assertEqual(attributes[path],
                                 {'text': 'unspecified', 'eol': 'unspecified'})

    def test_preview_catalogue_pipeline_is_utf8_lf_even_with_windows_defaults(self):
        import builtins
        import contextlib
        import io
        from render import i18n
        from tools import build_lang_packs as builder, lang_coverage as coverage
        root = Path(__file__).resolve().parents[1]
        real_open = builtins.open

        def windows_open(file, mode='r', *args, **kwargs):
            if 'w' in mode and 'b' not in mode:
                kwargs.setdefault('newline', '\r\n')
            return real_open(file, mode, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(coverage, 'LANG_DIR', directory), \
                    patch.object(builder, 'LANG_DIR', directory), \
                    patch('builtins.open', windows_open), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(coverage.write_catalogue(), 0)
                with self.subTest(writer='catalogue'):
                    english = (Path(directory) / 'en.json').read_bytes()
                    self.assertNotIn(b'\r', english)
                    self.assertEqual(english, (root / 'assets/data/lang/en.json').read_bytes())
                # Use the shipped catalogue to exercise pack writing independently.
                (Path(directory) / 'en.json').write_bytes(
                    (root / 'assets/data/lang/en.json').read_bytes())
                self.assertEqual(builder.main(), 0)
            for code, _ in i18n.LANGUAGES:
                actual = (Path(directory) / f'{code}.json').read_bytes()
                self.assertNotIn(b'\r', actual)
                self.assertEqual(actual, (root / f'assets/data/lang/{code}.json').read_bytes())


class ShippedPrototypeDefaultTests(unittest.TestCase):
    """The committed default is only real if it resolves the approved meshes.

    `DEFAULT_SETTINGS['visual_packs']` names thirteen external packs, and a name is not a
    model: a typo, a moved directory or a dropped mesh would leave the shipped
    selection pointing at nothing while every settings test still passed. Drive the
    real application seam from a clean install (no saved settings file) and check the
    loaded geometry against the owner's approved triangle counts.
    """

    REVIEWS = ('artifacts/imperial-flight-prototypes/OWNER_REVIEW.json',
               'artifacts/imperial-stations-review/OWNER_REVIEW.json',
               'artifacts/imperial-dockyard-review/OWNER_REVIEW.json',
               'artifacts/imperium-fleet/OWNER_REVIEW.json')

    def test_shipped_default_loads_the_approved_prototype_meshes(self):
        import json
        import game.core
        from render import menus
        from render import asset_selection as selection
        root = Path(__file__).resolve().parents[1]
        approved = [item for name in self.REVIEWS
                    for item in json.loads((root / name).read_text(encoding='utf-8'))['assets']]
        replacements=[item for pack in menus.DEFAULT_SETTINGS['visual_packs']
                      for item in json.loads((root/'visual_packs'/pack/'visual-pack.json').read_text())['content']['replaces']]
        self.assertEqual(len(approved),len(replacements),
                         'every shipped replacement carries an owner-approved mesh')
        self.assertEqual({item['binding'] for item in approved},
                         {item['binding'] for item in replacements})
        # A clean install: no settings file, so `load_settings` returns the shipped
        # defaults. In a source run USER_DIR is the checkout, which is where the
        # committed packs live.
        self.assertEqual(os.path.realpath(menus.USER_DIR), os.path.realpath(root))
        with patch.object(menus, 'SETTINGS_PATH', str(root / 'saves' / 'absent-settings.json')):
            settings = menus.load_settings()
        self.assertEqual(settings['visual_packs'], menus.DEFAULT_SETTINGS['visual_packs'])
        with patch.multiple(selection,
                            _selection={'model_preview': False, 'visual_packs': []},
                            _resolver=None, _generation=0, _coverage_report=None,
                            _coverage_generation=-1):
            report = selection.configure_from_settings(settings)
            self.assertEqual(report['mode'], 'preview')
            self.assertEqual([row['accepted'] for row in report['pack_order']],
                             [True] * len(menus.DEFAULT_SETTINGS['visual_packs']), report['pack_order'])
            self.assertEqual(report['enabled_order'], menus.DEFAULT_SETTINGS['visual_packs'])
            self.assertTrue(report['coverage']['ok'], report['coverage'])
            for item in approved:
                binding = item['binding']
                with self.subTest(binding=binding):
                    self.assertTrue(selection.selected_binding(binding), binding)
                    mesh = selection.mesh_for(binding)
                    assert mesh is not None, binding
                    self.assertEqual(sum(len(faces) for faces in mesh.values()),
                                     item['triangle_count'], 'shipped default is not the reviewed mesh')
                    self.assertEqual(selection.gpu_cache_key(binding, 'base', 'legacy')[0], 'authored')


if __name__ == '__main__':
    unittest.main()
