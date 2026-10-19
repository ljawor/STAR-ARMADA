"""Actual gameplay-loader provenance, separate from cosmetic selection."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import game.core
from game.data import store as store_module
from game.data.store import DataStore
from render import asset_selection as selection

ROOT = Path(__file__).resolve().parents[1]


class GameplayDependencyTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, DataStore, '_instance', DataStore._instance)

    def test_loaded_ship_provenance_is_explicit_and_last_gameplay_writer_wins(self):
        source = json.loads((ROOT / 'assets/data/ships/rebel.json').read_text())['ships']['rebel_frigate']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('first', 'second'):
                directory = root / 'mods' / name / 'data/ships'
                directory.mkdir(parents=True)
                ship = dict(source, name='Fixture scout', faction='raiders', category='scout')
                (directory / 'rebel.json').write_text(json.dumps({'ships': {'raiders_scout': ship}}))
            with patch.object(store_module, 'ROOT', str(root)):
                stock = DataStore(assets_dir=str(ROOT / 'assets/data'))
                first = DataStore(assets_dir=str(ROOT / 'assets/data'), mods=['first'])
                both = DataStore(assets_dir=str(ROOT / 'assets/data'), mods=['first', 'second'])
        self.assertEqual(getattr(stock, 'ship_mod_sources', None), {})
        self.assertEqual(getattr(first, 'ship_mod_sources', None), {'raiders_scout': 'first'})
        self.assertEqual(getattr(both, 'ship_mod_sources', None), {'raiders_scout': 'second'})
    def test_only_effectively_loaded_ship_bindings_satisfy_visual_dependency(self):
        from types import SimpleNamespace
        ds = SimpleNamespace(ships={
            'scout': SimpleNamespace(faction='raiders', category='scout'),
            'stock': SimpleNamespace(faction='rebel', category='frigate'),
        }, ship_mod_sources={'scout': 'raiders', 'missing': 'raiders'})
        helper = getattr(selection, 'active_gameplay_entities', lambda store: {})
        self.assertEqual(helper(ds), {'gameplay:raiders': {'raiders:scout'}})
        self.assertEqual(helper(SimpleNamespace(ships=ds.ships)), {})

    def test_application_selection_uses_loaded_store_without_changing_preferences(self):
        from types import SimpleNamespace
        from render import menus
        ds = SimpleNamespace(ships={'scout': SimpleNamespace(faction='raiders', category='scout')},
                             ship_mod_sources={'scout': 'raiders'})
        self.addCleanup(selection.configure, {})
        settings = {'model_preview': True, 'visual_packs': []}
        with tempfile.TemporaryDirectory() as tmp, patch.object(menus, 'USER_DIR', tmp):
            result = selection.configure_from_settings(settings, data_store=ds)
        self.assertEqual(result['mode'], 'preview')
        self.assertEqual(selection._resolver._gameplay_entities, {'gameplay:raiders': {'raiders:scout'}})
        self.assertEqual(settings, {'model_preview': True, 'visual_packs': []})
        self.assertIn('effective_bindings', result)
        self.assertEqual(result['effective_bindings'], [])


if __name__ == '__main__':
    unittest.main()
