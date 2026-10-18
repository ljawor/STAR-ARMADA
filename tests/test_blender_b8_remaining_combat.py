"""Cheap B8 authoring contracts; no Blender/build/export/GL invocation."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'tools/art/build_b8_remaining_combat.py'
SHEET = ROOT / 'art/manifests/pending/S06-BATCH-B8-REMAINING-COMBAT.json'
SCOPE = ROOT / 'artifacts/s06-completion/scope.json'


class B8AuthoringTests(unittest.TestCase):
    def scope(self):
        return {r['binding']: r for r in json.loads(SCOPE.read_text())['rows']
                if r['asset_class'] == 'combat_hull'}

    def seed(self):
        self.assertTrue(SEED.is_file(), 'B8 initial-authoring seed is missing')
        spec = importlib.util.spec_from_file_location('b8_under_test', SEED)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_seed_path_and_exact_eight_row_coverage(self):
        seed = self.seed()
        self.assertEqual(set(seed.ROWS), set(self.scope()))
        self.assertEqual(len(seed.ROWS), 8)
        self.assertNotIn('bpy', seed.__dict__)
        for key, source in self.scope().items():
            with self.subTest(key=key):
                row = seed.ROWS[key]
                for field in ('identifier', 'data_id', 'faction', 'envelope'):
                    self.assertEqual(row[field], source[field])

    def test_float32_fitting_stays_inside_strict_export_bounds(self):
        import struct
        seed = self.seed()
        self.assertTrue(hasattr(seed, 'fit_coordinate'))
        for low, high in ((-129.825, 138.05575), (-52.856406, 52.856406)):
            for value in (-10., 0., 10.):
                fitted = seed.fit_coordinate(value, -10., 10., low, high)
                stored = struct.unpack('f', struct.pack('f', fitted))[0]
                self.assertGreaterEqual(stored, low)
                self.assertLessEqual(stored, high)
                if value == -10.:
                    self.assertLess(abs(stored-low), 1e-3)
                if value == 10.:
                    self.assertLess(abs(stored-high), 1e-3)

    def test_sheet_is_pending_and_preserves_scope(self):
        self.assertTrue(SHEET.is_file(), 'B8 pending review sheet is missing')
        sheet = json.loads(SHEET.read_text())
        self.assertEqual(sheet['schema'], 1)
        self.assertEqual(sheet['batch'], 's06-b8-remaining-combat')
        self.assertEqual(sheet['status'], 'appearance_approved_pending_landing')
        self.assertEqual(sheet['overview_camera'], dict(yaw=90, pitch=40, distance=4000))
        self.assertEqual(sheet['close_distance_floor'], 150)
        assets = {r['binding']: r for r in sheet['assets']}
        self.assertEqual(len(sheet['assets']), 8)
        self.assertEqual(set(assets), set(self.scope()))
        for key, source in self.scope().items():
            with self.subTest(key=key):
                row = assets[key]
                for field in ('identifier', 'data_id', 'faction', 'envelope'):
                    self.assertEqual(row[field], source[field])
                self.assertEqual(row['class'], 'combat_hull')
                self.assertEqual(row['mesh'], f"assets/models/{source['identifier']}.mesh.json")
                self.assertEqual(row['seed'], 'tools/art/build_b8_remaining_combat.py')
                self.assertEqual(row['seed_arg'], '--asset ' + key)
                self.assertEqual(row['slot'], [-4200, 0, 2200])
                self.assertAlmostEqual(row['min_length'], source['envelope'][1][2] - source['envelope'][0][2] - .2)

    def probe(self, arguments, existing=()):
        self.assertTrue(SEED.is_file(), 'cannot exercise missing B8 seed')
        with tempfile.TemporaryDirectory(prefix='b8-preflight-') as tmp:
            root = Path(tmp)
            target = root / 'tools/art' / SEED.name
            target.parent.mkdir(parents=True)
            shutil.copyfile(SEED, target)
            # A real imported poison module proves preflight precedes Blender import.
            (target.parent / 'bpy.py').write_text(
                "from pathlib import Path\nimport sys\n"
                "Path(__file__).with_suffix('.touched').write_text('imported')\n"
                "sys.exit(91)\n")
            masters = []
            for identifier in existing:
                master = root / f'art/blender/{identifier}.blend'
                master.parent.mkdir(parents=True, exist_ok=True)
                master.write_bytes(b'editable-owner-master-sentinel')
                masters.append(master)
            result = subprocess.run([sys.executable, str(target), *arguments],
                                    text=True, capture_output=True, timeout=15)
            touched = (target.parent / 'bpy.touched').exists()
            for master in masters:
                self.assertEqual(master.read_bytes(), b'editable-owner-master-sentinel')
            return result, touched

    def test_real_preflight_refuses_each_existing_master_before_blender(self):
        for key, row in self.scope().items():
            with self.subTest(key=key):
                result, touched = self.probe(['--asset', key], [row['identifier']])
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('REFUSE existing editable master', result.stderr)
                self.assertFalse(touched)

    def test_all_preflights_last_row_before_importing_blender(self):
        result, touched = self.probe(['--all'], ['syndicate_cruiser'])
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('syndicate_cruiser.blend', result.stderr)
        self.assertFalse(touched)

    def test_replace_seed_is_explicit_opt_in(self):
        result, touched = self.probe(['--asset', 'syndicate:cruiser', '--replace-seed'],
                                     ['syndicate_cruiser'])
        self.assertEqual(result.returncode, 91, result.stderr)
        self.assertTrue(touched)

    def test_blender_separator_and_no_selection(self):
        result, touched = self.probe(['--', '--asset', 'confederacy:corvette'], ['confed_corvette'])
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(touched)
        for args in ([], ['--asset', 'syndicate:supercapital'], ['--all', '--asset', 'syndicate:cruiser']):
            result, touched = self.probe(args)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse(touched)


if __name__ == '__main__':
    unittest.main()
