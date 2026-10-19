"""Revision-bound approval of pictured B7/B8/B9 rows, never the unpictured scaffold."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def load(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))

class CompletionApproval(unittest.TestCase):
    def test_partial_sheet_sidecars_do_not_approve_unpictured_rows(self):
        spec = importlib.util.spec_from_file_location('approval_sidecars', ROOT / 'tools/art/write_pending_sidecars.py')
        assert spec is not None and spec.loader is not None
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        batch = copy.deepcopy(load('art/manifests/pending/S06-BATCH-B9-CONSTRUCTION.json'))
        batch['status'] = 'partially_appearance_approved_pending_landing'
        batch['appearance_decision'] = 'pictured-only-control'
        for row in batch['assets']:
            row['status'] = ('pending_owner_appearance_approval' if row['class'] == 'scaffold'
                             else 'appearance_approved_pending_landing')
            row.pop('appearance_decision', None)
            if row['class'] != 'scaffold':
                row['appearance_decision'] = 'pictured-only-control'
            sidecar = tool.sidecar_record(batch, row)
            self.assertEqual(sidecar['status'], row['status'])
            self.assertEqual(sidecar.get('appearance_decision'), row.get('appearance_decision'))
            self.assertFalse(sidecar['activation'])
            self.assertIsNone(sidecar['owner_decision'])

        scaffold_row = next(r for r in batch['assets'] if r['class'] == 'scaffold')
        scaffold_row['appearance_decision'] = 'pictured-only-control'
        with self.assertRaisesRegex(ValueError, 'status/decision mismatch'):
            tool.sidecar_record(batch, scaffold_row)
        scaffold_row.pop('appearance_decision')
        scaffold_row['status'] = 'appearance_approved_pending_landing'
        with self.assertRaisesRegex(ValueError, 'status/decision mismatch'):
            tool.sidecar_record(batch, scaffold_row)

    def test_only_the_26_pictured_exact_revisions_are_approved(self):
        decisions = [d for d in load('art/manifests/approvals.json')['decision_log']
                     if d['id'] in {'s06-b7-imperial-stations-2026-10-18',
                                    's06-b8-remaining-combat-2026-10-18',
                                    's06-b9-construction-2026-10-18'}]
        self.assertEqual(len(decisions), 3)
        review = load('artifacts/s06-completion/COMPLETION-REVIEW.json')
        pictured = {r['binding']: r for r in review['review']}
        approved = [a for d in decisions for a in d['revision']['assets']]
        self.assertEqual(len(approved), 26)
        self.assertEqual({a['gameplay_binding'] for a in approved}, set(pictured))
        self.assertNotIn('shared:construction_scaffold', pictured)
        for d in decisions:
            self.assertEqual(d['owner_words_verbatim'], 'approved')
            self.assertEqual(d['revision']['head_at_review'], 'e9d78bcf684c2128b2e76af30f3e61cd3e952083')
        for asset in approved:
            for path, digest in asset['evidence']['sha256'].items():
                self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(), digest)
            row = pictured[asset['gameplay_binding']]
            self.assertEqual(asset['runtime'][row['mesh']], row['runtime_sha256'])
            for group in ('source', 'exporter', 'runtime'):
                for path, digest in asset[group].items():
                    self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(), digest)
        scaffold = load('art/manifests/pending/S06-SHARED-CONSTRUCTION-SCAFFOLD.json')
        # A later, separately pictured S07 review approved the scaffold; the original
        # three decisions above still cover only their original 26 pictures.
        self.assertEqual(scaffold['status'], 'appearance_approved_pending_landing')
        self.assertEqual(scaffold['appearance_decision'], 's07-scaffold-appearance-2026-10-18')
