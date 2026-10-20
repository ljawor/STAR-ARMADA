"""S11: the shipped default catalogue, its migration, its lock and its rollback.

These tests bind the four promises the default switch makes:

1. a fresh or pre-switch install starts on the approved Blender catalogue;
2. a player who actually chose legacy keeps legacy (the choice is explicit);
3. a session drawn from a damaged catalogue says so instead of looking complete;
4. returning to legacy needs no asset change, only the selector.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / 'assets/models'


class DefaultSelectionTests(unittest.TestCase):
    def test_shipped_default_is_the_authored_catalogue(self):
        import game.core  # noqa: F401  (registers the package before menus imports it)
        from render import menus
        self.assertIs(menus.DEFAULT_SETTINGS['model_preview'], True)
        self.assertNotIn('model_preview_explicit', menus.DEFAULT_SETTINGS)
        self.assertIn('model_preview_explicit', menus.BOOKKEEPING_SETTINGS)

    def test_pre_switch_settings_file_migrates_to_the_authored_default(self):
        """`model_preview: false` in an old file was a default, not a decision."""
        import game.core  # noqa: F401
        from render import menus
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            path.write_text(json.dumps({'model_preview': False, 'music_volume': 0.4,
                                        'visual_packs': []}))
            with patch.object(menus, 'SETTINGS_PATH', str(path)):
                loaded = menus.load_settings()
        self.assertIs(loaded['model_preview'], True)
        self.assertAlmostEqual(loaded['music_volume'], 0.4)

    def test_an_explicit_legacy_choice_is_honoured_across_the_switch(self):
        import game.core  # noqa: F401
        from render import menus
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            path.write_text(json.dumps({'model_preview': False,
                                        'model_preview_explicit': True,
                                        'visual_packs': []}))
            with patch.object(menus, 'SETTINGS_PATH', str(path)):
                loaded = menus.load_settings()
        self.assertIs(loaded['model_preview'], False)

    def test_saving_records_the_choice_so_it_survives_a_restart(self):
        import game.core  # noqa: F401
        from render import menus
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(menus, 'SETTINGS_PATH', str(Path(tmp) / 'settings.json')):
                menus.save_settings(dict(menus.DEFAULT_SETTINGS, model_preview=False,
                                         model_preview_explicit=True))
                self.assertIs(menus.load_settings()['model_preview'], False)


class CompletenessReportTests(unittest.TestCase):
    def tearDown(self):
        from render import asset_selection
        asset_selection.configure({'model_preview': False, 'visual_packs': []})

    def test_authored_session_reports_a_complete_catalogue(self):
        from render import asset_selection
        report = asset_selection.configure({'model_preview': True, 'visual_packs': []})
        self.assertEqual(report['mode'], 'preview')
        self.assertIsNotNone(report['coverage'])
        self.assertIs(report['coverage']['ok'], True)
        self.assertEqual(len(report['coverage']['authored']), 103)
        self.assertEqual(report['coverage']['required_core_failures'], [])
        # The report runs at a session boundary: it must not parse the payloads.
        from render import asset_selection
        self.assertEqual(asset_selection._resolver.cache_info()[1], 0,
                         'coverage must not parse geometry during configuration')

    def test_a_damaged_catalogue_is_reported_not_hidden(self):
        """One missing manifest must surface as an incomplete catalogue, loudly."""
        from render import asset_selection
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'assets-root'
            shutil.copytree(MODELS, root / 'assets/models')
            victim = sorted((root / 'assets/models/manifests').glob('*.json'))[0]
            victim.unlink()
            with self.assertLogs('render.asset_selection', level='ERROR') as logs:
                report = asset_selection.configure({'model_preview': True,
                                                    'visual_packs': []},
                                                   asset_root=str(root))
        self.assertIs(report['coverage']['ok'], False)
        self.assertEqual(len(report['coverage']['required_core_failures']), 1)
        self.assertIn('incomplete', '\n'.join(logs.output).lower())


class RollbackRehearsalTests(unittest.TestCase):
    def tearDown(self):
        from render import asset_selection
        asset_selection.configure({'model_preview': False, 'visual_packs': []})

    def test_returning_to_legacy_needs_only_the_selector(self):
        import game.core  # noqa: F401
        from render import asset_selection
        asset_selection.configure({'model_preview': True, 'visual_packs': []})
        self.assertTrue(asset_selection.is_authored('confederacy:cruiser'))
        legacy = asset_selection.configure({'model_preview': False, 'visual_packs': []})
        self.assertEqual(legacy['mode'], 'legacy')
        self.assertIsNone(asset_selection.mesh_for('confederacy:cruiser'))
        self.assertIsNone(legacy['coverage'])
        # No save, replay or settings byte is touched by the selection itself.
        self.assertEqual(legacy['enabled_order'], [])


class ReleaseAssetLockTests(unittest.TestCase):
    def test_lock_covers_every_required_binding_with_matching_pins(self):
        lock = json.loads((ROOT / 'art/manifests/release-asset-lock.json').read_text())
        registry = json.loads((MODELS / 'registry.json').read_text())
        core = {row['binding'] for row in registry['bindings'] if row['status'] == 'core'}
        self.assertEqual({row['binding'] for row in lock['bindings']}, core)
        self.assertEqual(lock['counts']['core_bindings'], len(core))
        self.assertEqual(lock['contract'], 'star-armada/release-asset-lock')
        for row in lock['bindings']:
            for role, entry in row['files'].items():
                path = ROOT / entry['path']
                self.assertTrue(path.is_file(), f'{row["binding"]}: {role} missing')
                self.assertEqual(path.stat().st_size, entry['bytes'])

    def test_lock_check_mode_passes_on_the_committed_tree(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'build_release_asset_lock',
            ROOT / 'tools/art/build_release_asset_lock.py')
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        with patch('sys.stdout'):
            self.assertEqual(tool.main(['--check']), 0)


if __name__ == '__main__':
    unittest.main()
