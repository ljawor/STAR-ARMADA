"""The S07 scaffold picture approval is separate from the earlier eight B9 ships."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DECISION = 's07-scaffold-appearance-2026-10-18'
BINDING = 'shared:construction_scaffold'

def load(path):
    return json.loads((ROOT / path).read_text())

class ScaffoldAppearanceApproval(unittest.TestCase):
    def test_owner_approval_is_revision_bound_and_preserves_earlier_picture_scope(self):
        approvals = load('art/manifests/approvals.json')
        decisions = {d['id']: d for d in approvals['decision_log']}
        self.assertIn(DECISION, decisions, 'The latest scaffold picture approval has not been recorded')
        decision = decisions[DECISION]
        self.assertEqual(decision['owner_words_verbatim'], 'Pictures approved')
        self.assertEqual(decision['approval_kind'], 'appearance-scaffold-revision')
        self.assertFalse(decision['activation'])
        self.assertFalse(decision['runtime_acceptance'])
        self.assertEqual(len(decision['revision']['assets']), 1)
        asset = decision['revision']['assets'][0]
        self.assertEqual(asset['gameplay_binding'], BINDING)
        for group in ('source', 'exporter', 'runtime'):
            for path, expected in asset[group].items():
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected)
        for path, expected in asset['evidence']['sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected)
        metrics = load(asset['evidence']['metrics'])
        mesh = 'assets/models/shared_construction_scaffold.mesh.json'
        self.assertEqual(metrics['runtime_sha256'], asset['runtime'][mesh])
        self.assertEqual(metrics['grid']['sha256'], asset['evidence']['sha256'][asset['evidence']['grid']])
        self.assertTrue(metrics['protected_files_preserved'])
        self.assertTrue(metrics['production_scaffold_unselected_after_review'])
        self.assertEqual(set(metrics['captures']), {'imperial-0.1','imperial-0.5','imperial-0.9',
                                                   'rebel-0.5','confederacy-0.5','syndicate-0.5'})
        original = decisions['s06-b9-construction-2026-10-18']
        self.assertEqual(len(original['revision']['assets']), 8)
        self.assertEqual(original['owner_words_verbatim'], 'approved')
        self.assertNotIn(BINDING, {a['gameplay_binding'] for a in original['revision']['assets']})
        sidecar = load('art/manifests/pending/S06-SHARED-CONSTRUCTION-SCAFFOLD.json')
        self.assertEqual(sidecar['appearance_decision'], DECISION)
        self.assertEqual(sidecar['status'], 'appearance_approved_pending_landing')
        self.assertFalse(sidecar['activation'])
        spec = importlib.util.spec_from_file_location('scaffold_coverage', ROOT / 'tools/art/reconcile_model_coverage.py')
        assert spec is not None and spec.loader is not None
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        report = tool.build_report(ROOT)
        row = next(r for r in report['rows'] if r['canonical_binding'] == 'construction:site:scaffold')
        self.assertEqual(row['disposition'], 'approved_asset')
        self.assertEqual(row['asset']['approval_id'], DECISION)
        self.assertFalse(row['runtime_integration_proven'])
        self.assertEqual(report['integrity_errors'], [])

if __name__ == '__main__': unittest.main()
