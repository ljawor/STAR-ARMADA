"""End-to-end fleet facade selection, independent of model-specific dispatch."""
import unittest
from pathlib import Path

import game.core
from render import asset_selection as selection
from render.fleet_geometry import ship_mesh, station_mesh
from render.authored_mesh import load_frigate, load_shipyard, load_battleship

ROOT = Path(__file__).resolve().parents[1]


class GenericPreviewIntegrationTests(unittest.TestCase):
    def setUp(self):
        from game.data.store import DataStore
        self.addCleanup(setattr, DataStore, '_instance', DataStore._instance)

    def tearDown(self):
        selection.configure({})

    def test_application_start_applies_selection_after_old_renderer_closes(self):
        import ast
        source = (ROOT / 'main.py').read_text()
        start = next(n for n in ast.parse(source).body
                     if isinstance(n, ast.FunctionDef) and n.name == 'start_game')
        text = ast.unparse(start)
        self.assertIn('configure_from_settings(SETTINGS)', text)
        self.assertLess(text.index('renderer.close()'), text.index('configure_from_settings(SETTINGS)'))
        self.assertLess(text.index('configure_from_settings(SETTINGS)'), text.index('renderer = Renderer('))
        # Execute the same boundary helper against disposable menu preferences.
        from render.asset_selection import configure_from_settings
        from render import menus
        from unittest.mock import patch
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(menus, 'USER_DIR', tmp):
                result = configure_from_settings({'model_preview': True})
        self.assertEqual(result['mode'], 'preview')
        self.assertIsNotNone(selection.mesh_for('rebel:frigate'))

    def test_additive_gameplay_fixture_reaches_ship_size_and_fleet_mesh(self):
        from dataclasses import replace
        from game.data.store import DataStore
        from render.ship_sizes import ship_size
        from render.faction_visuals import ship_visual_key
        from test_asset_registry import PackTests
        from render.asset_registry import AssetResolver
        from unittest.mock import patch
        path = PackTests.pack(self, 'test:addon', 'raiders:scout', adds=True)
        resolver = AssetResolver(ROOT, gameplay_entities={'gameplay:raiders': {'raiders:scout'}})
        resolver.activate_packs([path])
        store = DataStore()
        # The gameplay entity already exists before a visual pack is enabled.
        store.ships['raiders_scout'] = replace(store.ships['rebel_frigate'],
                                              faction='raiders', category='scout')
        with patch.object(selection, '_resolver', resolver):
            self.assertEqual(ship_visual_key(store, 'raiders_scout'), 'raiders:scout')
            size = ship_size(store, 'raiders_scout')
            self.assertEqual(size.shape, 'raiders:scout')
            self.assertEqual(ship_mesh(size.shape), resolver.resolve('raiders:scout').mesh)

    def test_unknown_optional_bindings_keep_legacy_canonical_fallbacks_in_preview(self):
        from render.asset_registry import AssetResolver, AssetError
        controls = [('mod:unknown', lambda: ship_mesh('mod:unknown')),
                    ('imperial:mod_station', lambda: station_mesh('mod_station', 'imperial'))]
        selection.configure({})
        legacy = [draw() for _, draw in controls]
        selection.configure({'model_preview': True}, asset_root=ROOT)
        resolver = AssetResolver(ROOT)
        for (binding, draw), expected in zip(controls, legacy):
            with self.subTest(binding=binding):
                self.assertIsNone(selection.mesh_for(binding))
                self.assertIs(draw(), expected)
                with self.assertRaises(AssetError) as caught:
                    resolver.resolve(binding)
                self.assertEqual(caught.exception.code, 'E_UNKNOWN_BINDING')

    def test_stock_is_procedural_and_preview_is_approved_trio(self):
        selection.configure({})
        controls = [('rebel:frigate', load_frigate, lambda: ship_mesh('rebel:frigate')),
                    ('rebel:battleship', load_battleship, lambda: ship_mesh('rebel:battleship')),
                    ('rebel:shipyard', load_shipyard, lambda: station_mesh('shipyard', 'rebel'))]
        legacy = [draw() for _, _, draw in controls]
        approved = [loader(ROOT / f'assets/models/alliance_{key.split(":")[1]}.mesh.json')
                    for key, loader, _ in controls]
        for key, old, authored in zip((c[0] for c in controls), legacy, approved):
            with self.subTest(binding=key):
                self.assertNotEqual(old, authored, 'stock silently activates approved preview')
        selection.configure({'model_preview': True}, asset_root=ROOT)
        for (_, _, draw), authored in zip(controls, approved):
            self.assertEqual(draw(), authored)
        selection.configure({})
        for (_, _, draw), old in zip(controls, legacy):
            self.assertEqual(draw(), old)
