"""Cheap authoring-half guards: no Blender builds, exports or rendered-proof claims."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SEED = Path('tools/art/build_b9_construction.py')
SHEET = Path('art/manifests/pending/S06-BATCH-B9-CONSTRUCTION.json')
ROLES = ['base', 'dark', 'trim', 'accent', 'lit', 'cool']


def scope_rows():
    return {r['binding']: r for r in json.loads((ROOT / 'artifacts/s06-completion/scope.json').read_text())['rows']
            if r['asset_class'] in ('construction', 'scaffold')}


def seed_module():
    spec = importlib.util.spec_from_file_location('b9_authoring', ROOT / SEED)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConstructionAuthoringTests(unittest.TestCase):
    def test_scope_coverage_and_paths(self):
        self.assertTrue((ROOT / SEED).is_file(), 'B9 seed missing')
        self.assertTrue((ROOT / SHEET).is_file(), 'B9 pending sheet missing')
        module = seed_module()
        sheet = json.loads((ROOT / SHEET).read_text())
        expected = scope_rows()
        self.assertEqual(len(expected), 9)
        self.assertEqual(set(module.ROWS), set(expected))
        self.assertEqual(sheet['schema'], 1)
        self.assertEqual(sheet['batch'], 's06-b9-construction')
        self.assertEqual(sheet['status'], 'partially_appearance_approved_pending_landing')
        self.assertEqual(len(sheet['assets']), 9)
        self.assertEqual({r['binding'] for r in sheet['assets']}, set(expected))
        for row in sheet['assets']:
            with self.subTest(binding=row['binding']):
                source = expected[row['binding']]
                for key in ('identifier', 'data_id', 'gameplay_entity', 'faction', 'envelope'):
                    self.assertEqual(row[key], source[key])
                self.assertEqual(row['class'], source['asset_class'])
                self.assertEqual(row['mesh'], f"assets/models/{row['identifier']}.mesh.json")
                self.assertEqual(row['seed'], SEED.as_posix())
                self.assertEqual(row['seed_arg'], '--asset ' + row['binding'])
                self.assertEqual(row['slot'], [-4200, 0, 2200])
                self.assertAlmostEqual(row['min_length'], row['envelope'][1][2] - row['envelope'][0][2] - .2)
                self.assertEqual(row['material_roles'], ROLES)
                seed = module.ROWS[row['binding']]
                self.assertEqual(seed['limits'], list(map(list, zip(*row['envelope']))))
                authority = 'script' if row['class'] == 'scaffold' else 'blend'
                self.assertEqual(seed['authority'], authority)
                self.assertEqual(row['authority'], authority)
        scaffold = next(r for r in sheet['assets'] if r['class'] == 'scaffold')
        self.assertIsNone(scaffold['data_id'])
        self.assertTrue(scaffold['review_requires_scaffold_seam'])
        self.assertEqual(sheet['motion'], [])

    def run_seed(self, args, existing=None):
        self.assertTrue((ROOT / SEED).is_file(), 'B9 seed missing')
        with tempfile.TemporaryDirectory(prefix='b9-preflight-') as directory:
            root = Path(directory)
            target = root / SEED
            target.parent.mkdir(parents=True)
            shutil.copy2(ROOT / SEED, target)
            (target.parent / 'alliance_common.py').write_text("raise RuntimeError('BLENDER_IMPORT_REACHED')\n")
            master = root / f'art/blender/{existing}.blend' if existing else None
            if master:
                master.parent.mkdir(parents=True)
                master.write_bytes(b'editable-owner-master')
            result = subprocess.run([sys.executable, str(target), '--', *args], capture_output=True, text=True)
            if master:
                self.assertEqual(master.read_bytes(), b'editable-owner-master')
            self.assertFalse(list(root.glob('assets/models/*')))
            return result

    def test_real_single_target_refuses_before_blender_import(self):
        result = self.run_seed(['--asset', 'rebel:constructor'], 'rebel_constructor')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('editable master', result.stderr)
        self.assertNotIn('BLENDER_IMPORT_REACHED', result.stderr)

    def test_real_all_preflights_last_target_before_any_import(self):
        result = self.run_seed(['--all'], 'shared_construction_scaffold')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('editable master', result.stderr)
        self.assertNotIn('BLENDER_IMPORT_REACHED', result.stderr)

    def test_replace_seed_explicitly_reaches_blender_import(self):
        result = self.run_seed(['--asset', 'rebel:constructor', '--replace-seed'], 'rebel_constructor')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('BLENDER_IMPORT_REACHED', result.stderr)
        self.assertNotIn('editable master', result.stderr)

    def test_unknown_binding_rejected_without_import(self):
        result = self.run_seed(['--asset', 'not:a-model'])
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn('BLENDER_IMPORT_REACHED', result.stderr)


if __name__ == '__main__':
    unittest.main()
