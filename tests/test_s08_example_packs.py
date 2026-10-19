"""Shipped, GL-free S08 examples: real evaluated geometry, not token packs."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples/visual_packs'
PACKS = (
    ('core-frigate', 'example:core_frigate', 'example:alliance/frigate', 'rebel:frigate'),
    ('raider-addon', 'example:raider_addon', 'example:raiders/scout', 'raiders:scout'),
)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


class ExamplePackTests(unittest.TestCase):
    def test_installation_documentation_and_gameplay_readme_ship_with_examples(self):
        doc_path = ROOT / 'docs/VISUAL_MODEL_PACKS.md'
        self.assertTrue(doc_path.is_file(), 'S08 pack installation guide is missing')
        guide = doc_path.read_text()
        for term in ('USER_DIR/visual_packs', 'model_preview', 'visual_packs',
                     'core-frigate', 'raider-addon', 's08_raiders_fixture',
                     'diagnostics', 'hot reload', 'approval', 'DataStore'):
            self.assertIn(term, guide)
        self.assertTrue((ROOT / 'mods/s08_raiders_fixture/README.md').is_file())

    def test_gameplay_fixture_loads_through_real_datastore_and_supplies_addon_entity(self):
        fixture = ROOT / 'mods/s08_raiders_fixture/data/ships/rebel.json'
        self.assertTrue(fixture.is_file(), 'Real DataStore gameplay-mod fixture is missing')
        import game.core  # Establish the project's required import prelude.
        from game.data.store import DataStore
        from render.asset_registry import AssetResolver
        previous = DataStore._instance
        self.addCleanup(setattr, DataStore, '_instance', previous)
        baseline = DataStore(mods=[], balance={})
        loaded = DataStore(mods=['s08_raiders_fixture'], balance={})
        self.assertNotIn('s08_raiders_scout', baseline.ships)
        scout = loaded.resolve_ship('s08_raiders_scout')
        self.assertEqual((scout.faction, scout.category), ('raiders', 'scout'))
        self.assertEqual(set(loaded.ships) - set(baseline.ships), {'s08_raiders_scout'})
        for ship_id, ship in baseline.ships.items():
            self.assertEqual(loaded.ships[ship_id], ship)
        rel = 'data/ships/rebel.json'
        self.assertEqual(read(fixture), json.loads(loaded.mod_files[rel]))
        from render.asset_selection import active_gameplay_entities
        self.assertEqual(loaded.ship_mod_sources['s08_raiders_scout'], 's08_raiders_fixture')
        entities = active_gameplay_entities(loaded)
        self.assertEqual(entities, {'gameplay:s08_raiders_fixture': {'raiders:scout'}})
        paths = [EXAMPLES / folder / 'visual-pack.json' for folder, *_ in PACKS]
        resolver = AssetResolver(ROOT)
        self.assertEqual(resolver.activate_packs(paths, gameplay_entities=entities),
            ('example:core_frigate', 'example:raider_addon'))
        self.assertEqual(resolver.resolve('raiders:scout').asset, 'example:raiders/scout')
        self.assertEqual(resolver.resolve('rebel:frigate').asset, 'example:alliance/frigate')
        without_mod = AssetResolver(ROOT)
        self.assertEqual(without_mod.activate_packs(paths), ('example:core_frigate',))
        self.assertFalse(without_mod.active_order[-1]['accepted'])

    def test_external_install_uses_actual_loaded_session_seam_and_disables_cleanly(self):
        import shutil
        import tempfile
        from unittest.mock import patch
        import game.core
        from game.data.store import DataStore
        from render import menus, asset_selection
        previous = DataStore._instance
        self.addCleanup(setattr, DataStore, '_instance', previous)
        self.addCleanup(asset_selection.configure, {'model_preview': False})
        loaded = DataStore(mods=['s08_raiders_fixture'], balance={})
        with tempfile.TemporaryDirectory(prefix='s08-examples-', dir=ROOT.parent) as tmp:
            user_dir = Path(tmp)
            shutil.copytree(EXAMPLES, user_dir / 'visual_packs')
            settings = {'model_preview': True, 'visual_packs': ['core-frigate', 'raider-addon']}
            with patch.object(menus, 'USER_DIR', tmp), patch.object(menus, 'ASSET_ROOT', str(ROOT)):
                result = asset_selection.configure_from_settings(settings, data_store=loaded)
                self.assertEqual([r['accepted'] for r in result['pack_order']], [True, True])
                self.assertEqual(asset_selection.ship_binding(loaded, 's08_raiders_scout'), 'raiders:scout')
                self.assertEqual(sum(map(len, asset_selection.mesh_for('raiders:scout').values())), 7708)
                # A real altered installed file fails its pin, without mutating repository examples.
                mesh = user_dir / 'visual_packs/raider-addon/assets/models/scout.mesh.json'
                mesh.write_bytes(mesh.read_bytes() + b' ')
                result = asset_selection.configure_from_settings(settings, data_store=loaded)
                self.assertTrue(result['pack_order'][0]['accepted'])
                self.assertFalse(result['pack_order'][1]['accepted'])
                self.assertIsNone(asset_selection.ship_binding(loaded, 's08_raiders_scout'))
                result = asset_selection.configure_from_settings(
                    {'model_preview': False, 'visual_packs': settings['visual_packs']}, data_store=loaded)
                self.assertEqual(result['mode'], 'legacy')
                self.assertEqual(result['pack_order'], [])

    def test_builder_outputs_are_reproducible_and_source_pins_are_current(self):
        from tools.art.build_s08_examples import outputs
        expected = outputs()
        self.assertEqual(len(expected), 9)
        for rel, content in expected.items():
            self.assertEqual((ROOT / rel).read_bytes(), content, str(rel))
        pins = read(ROOT / 'artifacts/s08/examples/source-pins.json')
        for rel, digest in pins['inputs_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), digest)

    def test_shipped_packs_preserve_evaluated_geometry_with_role_only_remap(self):
        source = read(ROOT / 'assets/models/alliance_frigate.mesh.json')
        original = read(ROOT / 'assets/models/manifests/alliance_frigate.json')
        for folder, pack_id, asset, binding in PACKS:
            with self.subTest(folder=folder):
                path = EXAMPLES / folder / 'visual-pack.json'
                self.assertTrue(path.is_file(), 'Shippable example visual-pack.json is missing')
                pack = read(path)
                self.assertEqual(pack['id'], pack_id)
                entry = next(iter(pack['content'].values()))[0]
                self.assertEqual(entry['binding'], binding)
                manifest = read(path.parent / entry['manifest'])
                self.assertEqual(manifest['asset'], asset)
                self.assertNotIn('approval', manifest)
                self.assertNotIn('legacy_schema_int', manifest['export'])
                mesh_path = path.parent / manifest['files']['mesh']['path']
                payload = read(mesh_path)
                self.assertNotIn('schema', payload)
                self.assertEqual(payload['contract'], 'star-armada/mesh-export')
                self.assertEqual(payload['contract_major'], 1)
                self.assertEqual(payload['asset'], asset)
                for field in ('vertices', 'bounds', 'triangle_count'):
                    self.assertEqual(payload[field], source[field])
                self.assertEqual(payload['triangle_count'], 7708)
                # A bijective trim/accent swap: every triangle/normal/index survives.
                for role, rows in source['batches'].items():
                    target = {'trim': 'accent', 'accent': 'trim'}.get(role, role)
                    self.assertEqual(payload['batches'][target], rows)
                for field in ('coordinates', 'pivot', 'bounds', 'nominal_scale', 'roles', 'budgets'):
                    self.assertEqual(manifest[field], original[field])
                digest = hashlib.sha256(mesh_path.read_bytes()).hexdigest()
                self.assertEqual(manifest['files']['mesh']['sha256'], digest)
                self.assertEqual(manifest['files']['mesh']['bytes'], mesh_path.stat().st_size)
                revision = hashlib.sha256((asset + '\nmesh:' + digest).encode()).hexdigest()
                self.assertEqual(manifest['revision'], revision)
                self.assertNotEqual(revision, original['revision'])
                self.assertEqual(manifest['provenance']['tool'], 'Python JSON role remap')
                self.assertNotIn('.blend', [p.suffix for p in path.parent.rglob('*')])


if __name__ == '__main__':
    unittest.main()
