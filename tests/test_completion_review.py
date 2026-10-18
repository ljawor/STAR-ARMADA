"""Headless adapter contracts; these tests never initialize Blender or OpenGL."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def adapter():
    path = ROOT / 'tools/diag_completion_review.py'
    assert path.exists(), 'completion review adapter has not been implemented'
    spec = importlib.util.spec_from_file_location('completion_review', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CompletionReviewTests(unittest.TestCase):
    def test_station_views_centre_positive_y_hardware_with_extra_clearance(self):
        review = adapter()
        self.assertTrue(hasattr(review, 'framed_views'))
        harness = review.load_harness()
        path = next((ROOT/'art/manifests/pending').glob('S06-BATCH-B7-*.json'))
        row = next(a for a in review.derive_spec(path)['assets'] if a['station_kind']=='fighter_platform')
        length = max(hi-lo for lo, hi in zip(*row['envelope'])) * harness.station_scale(row)
        original = harness.views_for(row, length, 150.)
        result = review.framed_views(harness, row, length, 150.)
        self.assertGreater(result['close']['target'][1], original['close']['target'][1])
        self.assertGreater(result['close']['distance'], original['close']['distance'])
        self.assertEqual(result['tactical'], original['tactical'])

    def test_all_rows_station_roles_unique_labels_and_scaffold_proof(self):
        review = adapter()
        counts = []
        labels = []
        for batch, count in (('B7', 10), ('B8', 8), ('B9', 8)):
            path = next((ROOT / 'art/manifests/pending').glob(f'S06-BATCH-{batch}-*.json'))
            before = path.read_bytes()
            derived = review.derive_spec(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(derived['assets']), count)
            counts.append(len(derived['assets']))
            self.assertTrue({'first_x', 'first_z', 'spacing', 'distance', 'yaw', 'pitch',
                             'close_distance_floor'} <= derived['overview'].keys())
            self.assertEqual(derived['provenance']['source_sha256'], review.sha256(path))
            for row in derived['assets']:
                labels.append(row['label'])
                faction, role = row['binding'].split(':')
                self.assertEqual(row['faction'], faction)
                if batch == 'B7':
                    self.assertEqual(row['station_kind'], role)
                    self.assertEqual(row['data_id'], role)
                elif batch == 'B9':
                    self.assertIn(role, ('constructor', 'colonizer'))
                    self.assertEqual(row['data_id'].rsplit('_', 1)[-1], role)
            if batch == 'B9':
                excluded, = derived['excluded']
                self.assertEqual(excluded['reason'], 'requires S07 scaffold seam')
                self.assertEqual(excluded['asset']['binding'], 'shared:construction_scaffold')
                self.assertIn('assets/models/shared_construction_scaffold.mesh.json', excluded['proof'])
                self.assertIn('art/blender/shared_construction_scaffold.blend', excluded['proof'])
            from s07_registration_assertions import assert_opt_in_registration
            assert_opt_in_registration(self, ROOT, [row['binding'] for row in derived['assets']])
            # The pre-registration capture tool must refuse already-published rows.
            with self.assertRaises(AssertionError):
                review.assert_unregistered(derived)
        self.assertEqual(counts, [10, 8, 8])
        self.assertEqual(len(set(labels)), 26)

    def test_ship_roles_use_the_production_binding_function(self):
        from render import asset_selection as selection
        ships = {}
        for path in (ROOT / 'assets/data/ships').glob('*.json'):
            ships.update({key: types.SimpleNamespace(**value)
                          for key, value in json.loads(path.read_text())['ships'].items()})
        ds = types.SimpleNamespace(ships=ships)
        with patch.object(selection, '_resolver', object()), \
                patch.object(selection, 'selected_binding', return_value=True):
            for batch in ('B8', 'B9'):
                path = next((ROOT / 'art/manifests/pending').glob(f'S06-BATCH-{batch}-*.json'))
                for row in adapter().derive_spec(path)['assets']:
                    self.assertEqual(selection.ship_binding(ds, row['data_id'], row['faction']),
                                     row['binding'])

    def test_selected_seam_tracks_only_current_mesh_and_restores_on_failure(self):
        review = adapter()
        selection = types.SimpleNamespace(mesh_for=lambda key: None,
                                          selected_binding=lambda key: key == 'stock')
        original = selection.selected_binding
        with self.assertRaisesRegex(RuntimeError, 'capture failed'):
            with review.selected_seam(selection, {'imperial:constructor'}):
                self.assertFalse(selection.selected_binding('imperial:constructor'))
                selection.mesh_for = lambda key: {} if key == 'imperial:constructor' else None
                self.assertTrue(selection.selected_binding('imperial:constructor'))
                self.assertFalse(selection.selected_binding('rebel:constructor'))
                self.assertTrue(selection.selected_binding('stock'))
                raise RuntimeError('capture failed')
        self.assertIs(selection.selected_binding, original)

    def test_rejects_zero_pixel_reports(self):
        review = adapter()
        spec = {'assets': [{'binding': 'imperial:constructor'}]}
        report = {'source_preserved': True, 'protected_files_preserved': True,
                  'production_candidates_unselected_after_review': True,
                  'captures': {'imperial:constructor': {'comparison': {
                      name: {'changed_pixels_gt3': 1} for name in ('close', 'tactical')}}}}
        review.check_report(spec, report)
        for name in ('close', 'tactical'):
            bad = copy.deepcopy(report)
            bad['captures']['imperial:constructor']['comparison'][name]['changed_pixels_gt3'] = 0
            with self.assertRaises(AssertionError):
                review.check_report(spec, bad)

    def test_cli_runs_unchanged_batch_with_derived_spec_not_original(self):
        review = adapter()
        source = next((ROOT / 'art/manifests/pending').glob('S06-BATCH-B9-*.json'))
        selection = types.SimpleNamespace(mesh_for=lambda key: None, selected_binding=lambda key: False,
                                          configure=lambda settings: None)
        calls = []
        def main():
            args = sys.argv
            derived_path = Path(args[args.index('--spec') + 1])
            out = Path(args[args.index('--out') + 1])
            self.assertNotEqual(derived_path, source)
            spec = json.loads(derived_path.read_text())
            self.assertEqual(len(spec['assets']), 8)
            self.assertIn('--skip-motion', args)
            calls.append(spec)
            out.mkdir()
            report = dict(source_preserved=True, protected_files_preserved=True,
                          production_candidates_unselected_after_review=True, captures={})
            for row in spec['assets']:
                report['captures'][row['binding']] = {'comparison': {
                    name: {'changed_pixels_gt3': 1} for name in ('close', 'tactical')}}
            (out / 'metrics.json').write_text(json.dumps(report))
        real_harness = review.load_harness()
        fake_harness = types.SimpleNamespace(main=main, views_for=real_harness.views_for,
                                             station_scale=real_harness.station_scale)
        # Exercise the historical authoring CLI against explicit pending fixture
        # metadata, never by pretending the now-published stock B9 rows are pending.
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / 'pending-root'
            registry = json.loads((ROOT / 'assets/models/registry.json').read_bytes())
            pending = {row['binding'] for row in review.derive_spec(source)['assets']}
            for row in registry['bindings']:
                if row['binding'] in pending:
                    row['status'] = 'authoring_pending'
            pipeline = json.loads((ROOT / 'art/manifests/pipeline.json').read_bytes())
            pipeline['assets'] = [row for row in pipeline['assets'] if row['binding'] not in pending]
            for relative, data in [('assets/models/registry.json', json.dumps(registry).encode()),
                                   ('art/manifests/pipeline.json', json.dumps(pipeline).encode()),
                                   ('tools/diag_alliance_batch_review.py',
                                    (ROOT / 'tools/diag_alliance_batch_review.py').read_bytes())]:
                target = fixture / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            with patch.object(review, 'ROOT', fixture), \
                    patch.object(review, 'load_harness', return_value=fake_harness), \
                    patch.dict(sys.modules, {'render': types.SimpleNamespace(asset_selection=selection)}):
                self.assertEqual(review.main(['--spec', str(source), '--out', str(Path(tmp) / 'review')]), 0)
                self.assertTrue((Path(tmp) / 'review/review-spec.json').exists())
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
