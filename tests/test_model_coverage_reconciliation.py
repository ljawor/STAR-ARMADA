"""Behavioural checks for the read-only inventory reconciliation report."""
import importlib.util
import json
from pathlib import Path
import unittest
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/art/reconcile_model_coverage.py'


class CoverageReconciliation(unittest.TestCase):
    def test_every_inventory_row_is_accounted_for_without_inventing_approval(self):
        self.assertTrue(TOOL.is_file(), 'the reproducible coverage reconciler is missing')
        spec = importlib.util.spec_from_file_location('coverage_reconciliation', TOOL)
        assert spec is not None and spec.loader is not None
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        report = tool.build_report(ROOT)
        rows = {r['canonical_binding']: r for r in report['rows']}
        inventory = json.loads((ROOT / 'art/manifests/model_inventory.json').read_text())
        self.assertEqual(set(rows), {r['canonical_binding'] for r in inventory['rows']})
        self.assertEqual(report['counts']['inventory_rows'], 120)
        self.assertEqual(report['counts']['unique_approved_assets'], 76)
        self.assertEqual(report['counts']['appearance_batch_decisions'], 9)
        self.assertEqual(report['counts']['appearance_batch_specimens'], 73)
        self.assertEqual(report['counts']['dispositions'], {
            'approved_asset': 76, 'approved_shared_candidate': 4,
            'pending_appearance': 27, 'deferred_texture_pipeline': 10,
            'outside_mesh_catalogue': 3})
        for faction in ('imperial', 'rebel', 'confederacy', 'syndicate'):
            crew = rows[f'ship:{faction}:crew_transport']
            trade = rows[f'ship:{faction}:trade_convoy']
            self.assertEqual(crew['runtime_binding'], faction + ':convoy')
            self.assertEqual(trade['runtime_binding'], faction + ':convoy')
            self.assertEqual(trade['disposition'], 'approved_shared_candidate')
            self.assertFalse(trade['runtime_integration_proven'])
        self.assertEqual(rows['ship:imperial:constructor']['disposition'], 'pending_appearance')
        self.assertEqual(rows['station:imperial:shipyard']['disposition'], 'pending_appearance')
        for row in rows.values():
            if row['disposition'] == 'pending_appearance':
                self.assertIsNone(row['asset'].get('approval_id'))
                self.assertFalse(row['runtime_integration_proven'])
        self.assertEqual(len(report['planned_hulls_outside_inventory']), 3)
        self.assertFalse(report['s06_catalogue_complete'])
        self.assertEqual(report['integrity_errors'], [])

    def test_cli_rejects_stale_report_and_approval_corruption_without_writing(self):
        """Exercise real --check on a disposable copy, never mutate approved inputs."""
        relative = 'art/manifests/reviews/S06-COVERAGE-RECONCILIATION.json'
        report = json.loads((ROOT / relative).read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory(prefix='coverage-control-') as directory:
            root = Path(directory)
            for path in list(report['input_sha256']) + [relative]:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / path, target)

            def check():
                return subprocess.run([sys.executable, str(TOOL), '--root', str(root), '--check'],
                                      text=True, capture_output=True, check=False)

            good = check()
            self.assertEqual(good.returncode, 0, good.stderr)
            output = root / relative
            original = output.read_bytes()
            output.write_text('{}\n', encoding='utf-8')
            stale = check()
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn('STALE:', stale.stderr)
            self.assertEqual(output.read_text(encoding='utf-8'), '{}\n')
            output.write_bytes(original)
            approval = root / 'art/manifests/approvals.json'
            data = json.loads(approval.read_text(encoding='utf-8'))
            batch = next(d for d in data['decision_log']
                         if d.get('approval_kind') == 'appearance-batch-revisions')
            mesh = next(p for p in batch['revision']['assets'][0]['runtime']
                        if p.endswith('.mesh.json'))
            batch['revision']['assets'][0]['runtime'][mesh] = '0' * 64
            approval.write_text(json.dumps(data), encoding='utf-8')
            corrupted = check()
            self.assertNotEqual(corrupted.returncode, 0)
            self.assertIn('hash mismatch: ' + mesh, corrupted.stderr)
            self.assertEqual(output.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
