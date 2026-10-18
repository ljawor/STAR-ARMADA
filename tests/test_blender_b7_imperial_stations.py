"""Cheap B7 contracts; Blender builds/exports belong to the parent acceptance pass."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'tools/art/build_b7_imperial_stations.py'
SHEET = ROOT / 'art/manifests/pending/S06-BATCH-B7-IMPERIAL-STATIONS.json'
SCOPE = ROOT / 'artifacts/s06-completion/scope.json'


def load_seed():
    spec = importlib.util.spec_from_file_location('b7_seed_contract', SEED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ImperialStationAuthoringTests(unittest.TestCase):
    def test_seed_and_sheet_exist(self):
        self.assertTrue(SEED.is_file(), 'B7 initial-only seed is missing')
        self.assertTrue(SHEET.is_file(), 'B7 pending sheet is missing')

    def test_ten_station_rows_match_measured_scope(self):
        self.assertTrue(SHEET.is_file(), 'B7 pending sheet is missing')
        sheet = json.loads(SHEET.read_text())
        scope = [r for r in json.loads(SCOPE.read_text())['rows'] if r['asset_class'] == 'station']
        self.assertEqual(len(scope), 10)
        self.assertEqual(len(sheet['assets']), 10)
        self.assertEqual(sheet['schema'], 1)
        self.assertEqual(sheet['batch'], 's06-b7-imperial-stations')
        self.assertEqual(sheet['status'], 'appearance_approved_pending_landing')
        self.assertFalse(sheet['activation'])
        self.assertIsNone(sheet['owner_decision'])
        by_binding = {r['binding']: r for r in sheet['assets']}
        self.assertEqual(set(by_binding), {r['binding'] for r in scope})
        seed = load_seed()
        self.assertEqual(set(seed.ROWS), set(by_binding))
        for measured in scope:
            row = by_binding[measured['binding']]
            for field in ('identifier', 'envelope', 'data_id', 'gameplay_entity', 'faction', 'station_kind'):
                self.assertEqual(row[field], measured[field])
            self.assertEqual(row['class'], 'station')
            self.assertEqual(row['seed'], str(SEED.relative_to(ROOT)))
            self.assertEqual(row['seed_arg'], '--asset ' + row['binding'])
            self.assertEqual(row['mesh'], 'assets/models/' + row['identifier'] + '.mesh.json')
            self.assertEqual(row['slot'], [-4200, 0, 2200])
            self.assertAlmostEqual(row['min_length'], row['envelope'][1][2] - row['envelope'][0][2] - .2)
            self.assertEqual(seed.ROWS[row['binding']]['limits'], tuple(zip(*row['envelope'])))
        self.assertEqual([sheet['overview'][k] for k in ('yaw','pitch','distance','close_distance_floor')], [90,40,2800,150])

    def run_isolated(self, args, existing=()):
        self.assertTrue(SEED.is_file(), 'B7 initial-only seed is missing')
        with tempfile.TemporaryDirectory(prefix='b7-preflight-') as directory:
            root = Path(directory)
            dest = root / 'tools/art' / SEED.name
            dest.parent.mkdir(parents=True)
            shutil.copyfile(SEED, dest)
            for identifier in existing:
                master = root / 'art/blender' / (identifier + '.blend')
                master.parent.mkdir(parents=True, exist_ok=True)
                master.write_bytes(b'editable-master-sentinel')
            result = subprocess.run([sys.executable, str(dest), *args], capture_output=True, text=True)
            for identifier in existing:
                self.assertEqual((root / 'art/blender' / (identifier + '.blend')).read_bytes(), b'editable-master-sentinel')
            self.assertFalse((root / 'assets').exists())
            self.assertEqual(len(list(root.rglob('*.blend'))), len(existing))
            return result

    def test_all_refuses_last_existing_master_before_blender_import(self):
        result = self.run_isolated(['--all'], ['imperial_energy_relay'])
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('imperial_energy_relay.blend', result.stderr)
        self.assertIn('--replace-seed', result.stderr)
        self.assertNotIn('bpy', result.stderr)

    def test_single_target_refuses_existing_master(self):
        result = self.run_isolated(['--', '--asset', 'imperial:command_station'], ['imperial_command_station'])
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('editable master', result.stderr)
        self.assertNotIn('bpy', result.stderr)

    def test_explicit_replacement_preflight_is_allowed_without_blender(self):
        result = self.run_isolated(['--all','--replace-seed','--preflight-only'], ['imperial_energy_relay'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('targets=10', result.stdout)

    def test_selected_target_ignores_unselected_existing_master(self):
        result = self.run_isolated(['--asset','imperial:shipyard','--preflight-only'], ['imperial_energy_relay'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('targets=1', result.stdout)

    def test_unknown_or_missing_selection_refused_without_import(self):
        for args in ([], ['--asset','imperial:not_a_kind'], ['--asset'], ['--all','--asset','imperial:shipyard']):
            with self.subTest(args=args):
                result = self.run_isolated(args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn('bpy', result.stderr)

    def test_affine_fit_reaches_every_asymmetric_side(self):
        self.assertTrue(SEED.is_file(), 'B7 initial-only seed is missing')
        seed = load_seed()
        for row in seed.ROWS.values():
            points = [(-10,-20,-30), (15,37,63), (1,2,3)]
            fitted = seed.fit_points(points, row['limits'])
            for axis, (lo, hi) in enumerate(row['limits']):
                self.assertAlmostEqual(min(p[axis] for p in fitted), lo)
                self.assertAlmostEqual(max(p[axis] for p in fitted), hi)
            self.assertTrue(all(lo <= fitted[2][i] <= hi for i,(lo,hi) in enumerate(row['limits'])))

    def test_unique_functional_builders_and_no_export_dependency(self):
        self.assertTrue(SEED.is_file(), 'B7 initial-only seed is missing')
        seed = load_seed()
        self.assertEqual(len({row['builder'] for row in seed.ROWS.values()}), 10)
        self.assertEqual(seed.ROLES, ('base','dark','trim','accent','lit','cool'))
        self.assertNotIn('bpy', seed.__dict__)
        self.assertNotIn('alliance_common', sys.modules)
        for row in seed.ROWS.values():
            self.assertTrue(callable(getattr(seed, row['builder'])))
            self.assertTrue(row['design'])


if __name__ == '__main__':
    unittest.main()
