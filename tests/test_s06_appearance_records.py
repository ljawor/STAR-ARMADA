"""Cross-batch guards for the S06 appearance decisions.

Every S06 batch ends with the same two questions: is this the right direction, and may it land?
This module guards the boundary between the answers. It reads the recorded decisions and re-derives
what they claim against the tree, so a decision cannot quietly stop matching the files it names, and
an approved specimen cannot quietly become selectable without the activation decision that owns that
step.

Run:  PYTHONPATH=tests .venv/bin/python -m unittest test_s06_appearance_records
"""

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / 'art/manifests/pending'
APPROVALS = ROOT / 'art/manifests/approvals.json'
POLICY = ROOT / 'art/manifests/pipeline_policy.json'

# The owner's words that record the S06 approvals of 2026-10-17, per decision, verbatim and
# including the numbering he used. A batch answered on its own gets its own line here rather than
# being folded into another batch's sentence.
BATCH_APPROVAL_WORDS = "the Liberty Cruiser, B1 corvette + carrier, B2's eight, B3b's nine--> Approved"
OWNER_WORDS = {
    's06-cruiser-review-2026-10-17': BATCH_APPROVAL_WORDS,
    's06-b1-alliance-combat-2026-10-17': BATCH_APPROVAL_WORDS,
    's06-b2-squadron-logistics-2026-10-17': BATCH_APPROVAL_WORDS,
    's06-b3b-stations-2026-10-17': BATCH_APPROVAL_WORDS,
    's06-b3c-stations-2026-10-17': 'yes',
    's06-b3a-command-stations-2026-10-17': '1.) B3a command stations: Approved',
    's06-b4-hardware-2026-10-17': 'B4 looks good',
    # One word, recorded next to the choice it was clarified into rather than in place of it.
    's06-b5-environment-2026-10-17': 'passed',
}
EXPECTED_BATCHES = {
    's06-cruiser-review': 1,
    's06-b1-alliance-combat': 2,
    's06-b2-squadron-logistics': 8,
    's06-b3b-stations-slice-1': 9,
    's06-b3c-stations': 17,
    's06-b3a-command-stations': 3,
    's06-b4-hardware': 24,
    's06-b5-environment': 1,
}
# 37 specimens whose appearance the owner has approved, and the count the records must keep adding up
# to until another decision changes it.
APPROVED_SPECIMENS = 65
SCOPE_DECISIONS = {'s06-b4-scope-2026-10-17': '1.) B4 authorized',
                   's06-imperial-migration-2026-10-17': '4.) decision need also migration.',
                   's06-large-evidence-accepted-2026-10-17':
                       '2.) A policy flag: the B4 contact sheet is 12.7 MiB: accept bigger'}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha256(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def batch_sheets():
    """Every batch sheet by its `batch` field, so a rename cannot silently detach a decision."""
    sheets = {}
    for path in sorted(PENDING.glob('S06-BATCH-*.json')):
        sheet = load(path)
        sheets[sheet['batch']] = (path, sheet)
    return sheets


def appearance_decisions():
    return [d for d in load(APPROVALS)['decision_log']
            if d.get('approval_kind') == 'appearance-batch-revisions']


class RecordedApprovals(unittest.TestCase):
    def test_every_decision_still_names_the_revision_hashes_on_disk(self):
        """A decision is only worth reading if it can be re-derived from the tree."""
        for decision in appearance_decisions():
            for asset in decision['revision']['assets']:
                for group in ('source', 'exporter', 'runtime'):
                    for path, digest in asset[group].items():
                        with self.subTest(decision=decision['id'], binding=asset['gameplay_binding'],
                                          path=path):
                            self.assertTrue((ROOT / path).exists(), f'{path} is gone')
                            self.assertEqual(
                                digest, sha256(path),
                                f'{path} moved after {decision["id"]}: the approval no longer '
                                f'covers the bytes on disk')

    def test_approved_specimens_stay_unregistered_and_unactivated(self):
        """Appearance approval is not activation: nothing approved here may become selectable."""
        registry = load(ROOT / 'assets/models/registry.json')
        status = {b['binding']: b['status'] for b in registry['bindings']}
        pipeline = load(ROOT / 'art/manifests/pipeline.json')
        registered = {a['binding'] for a in pipeline['assets']}
        approved_assets = json.dumps([e for e in load(APPROVALS)['approved_assets']
                                      if isinstance(e, dict)])
        for decision in appearance_decisions():
            for asset in decision['revision']['assets']:
                with self.subTest(decision=decision['id'], binding=asset['gameplay_binding']):
                    # Two statuses mean "not selectable": `procedural_legacy`, which is a binding the
                    # runtime knows and serves the old mesh for, and `authoring_pending`, which is a row
                    # the inventory declares as an authoring target. Anything else - `authored`, a pack,
                    # a preview - would mean the approval had become a selection.
                    self.assertIn(status.get(asset['gameplay_binding']),
                                  ('procedural_legacy', 'authoring_pending'),
                                  'an appearance-approved specimen must still not be selectable')
                    self.assertNotIn(asset['gameplay_binding'], registered)
                    self.assertNotIn(asset['gameplay_binding'], approved_assets)
                    self.assertNotIn(asset['identifier'], approved_assets)

    def test_batch_sheets_and_sidecars_agree_with_the_decisions(self):
        """The sheet and the sidecar are what a reader sees first; they must not disagree."""
        sheets = batch_sheets()
        for decision in appearance_decisions():
            batch = decision['revision']['batch']
            with self.subTest(batch=batch):
                # The cruiser was reviewed before the batch sheets existed, so it has a sidecar
                # and no sheet: its decision names the batch it belongs to instead.
                if batch == 's06-cruiser-review':
                    self.assertNotIn(batch, sheets)
                    identifiers = {a['identifier'] for a in decision['revision']['assets']}
                else:
                    self.assertIn(batch, sheets, f'{batch} has a decision but no batch sheet')
                    path, sheet = sheets[batch]
                    self.assertEqual(sheet['status'], 'appearance_approved_pending_landing')
                    self.assertEqual(sheet['appearance_decision'], decision['id'])
                    identifiers = {a['identifier'] for a in sheet['assets']}
                    self.assertEqual(sorted(identifiers),
                                     sorted(a['identifier'] for a in decision['revision']['assets']),
                                     f'the decision and the sheet disagree about {batch}')
                for identifier in identifiers:
                    sidecar = load(PENDING / f"S06-{identifier.upper().replace('_', '-')}.json")
                    self.assertEqual(sidecar['status'], 'appearance_approved_pending_landing')
                    self.assertEqual(sidecar['appearance_decision'], decision['id'])
                    self.assertTrue(sidecar['activation'] is False)
                    self.assertTrue(sidecar['owner_decision'] is None)

    def test_the_count_the_records_claim_is_the_count_on_disk(self):
        counts = {d['revision']['batch']: len(d['revision']['assets'])
                  for d in appearance_decisions()}
        self.assertEqual(counts, EXPECTED_BATCHES,
                         'a batch gained or lost an approved specimen without a new decision')
        self.assertEqual(sum(counts.values()), APPROVED_SPECIMENS,
                         'the S06 specimens the records call approved are not the number on disk')

    def test_the_owner_words_are_verbatim_on_every_batch_decision(self):
        self.assertEqual(sorted(d['id'] for d in appearance_decisions()), sorted(OWNER_WORDS))
        for decision in appearance_decisions():
            with self.subTest(decision=decision['id']):
                self.assertEqual(decision['owner_words_verbatim'], OWNER_WORDS[decision['id']],
                                 'the record must quote what was said for this batch, not another')

    def test_every_decision_says_what_it_does_not_approve(self):
        """An approval that reads as a landing is the expensive mistake."""
        for decision in appearance_decisions():
            with self.subTest(decision=decision['id']):
                text = ' '.join(decision['not_approved_by_this_decision']).lower()
                self.assertIn('landing', text,
                              f'{decision["id"]} does not rule out landing in writing')
                self.assertIn('switch', text,
                              f'{decision["id"]} does not rule out a production switch in writing')
                self.assertIn('production', text)
                self.assertIn('packaging', text,
                              f'{decision["id"]} does not rule out packaging in writing')


class RecordedScope(unittest.TestCase):
    def test_the_scope_decisions_are_recorded_in_the_owners_wording(self):
        log = {d['id']: d for d in load(POLICY)['decision_log']}
        for decision_id, wording in SCOPE_DECISIONS.items():
            with self.subTest(decision=decision_id):
                self.assertIn(decision_id, log)
                entry = log[decision_id]
                self.assertEqual(entry['owner_wording'], wording)
                self.assertTrue(entry.get('not_authorized'),
                                'a scope decision must say what it does not authorize')
                self.assertNotIn('revision', entry,
                                 'a scope decision is not an appearance approval')

    def test_scope_decisions_do_not_masquerade_as_appearance_approvals(self):
        approvals = load(APPROVALS)
        names = json.dumps(approvals['approved_assets'])
        for decision_id in SCOPE_DECISIONS:
            self.assertNotIn(decision_id, names)
        self.assertEqual([d['id'] for d in approvals['decision_log'] if
                          d['id'] in SCOPE_DECISIONS], [])

    def test_every_sheet_is_either_approved_or_deliberately_pending(self):
        """A sheet is approved or it is waiting; what must never appear is something in between.

        A pending sheet is the point of a batch sheet - it is what the owner is asked to look at - so
        the guard names the batches that are deliberately pending rather than pretending none is. A
        new sheet, or a status that moves without a decision, therefore shows up as a diff here
        instead of sliding through.
        """
        sheets = batch_sheets()
        decided = {d['revision']['batch'] for d in appearance_decisions()}
        # The cruiser was reviewed before the batch sheets existed: it has a decision, a sidecar and
        # no sheet - named here rather than assumed.
        self.assertEqual(sorted(decided - set(sheets)), ['s06-cruiser-review'])
        pending = {batch for batch in sheets if batch not in decided}
        self.assertEqual(sorted(pending), [],
                         'every batch sheet now carries a decision: a new one, or a status that moved '
                         'without a decision, shows up here')
        for batch, (path, sheet) in sheets.items():
            with self.subTest(batch=batch):
                if batch in decided:
                    self.assertEqual(sheet['status'], 'appearance_approved_pending_landing')
                    self.assertIn('appearance_decision', sheet)
                    self.assertEqual(sheet['appearance_decision'],
                                     next(d['id'] for d in appearance_decisions()
                                          if d['revision']['batch'] == batch))
                else:
                    self.assertEqual(sheet['status'], 'pending_owner_appearance_approval')
                    self.assertNotIn('appearance_decision', sheet)


if __name__ == '__main__':
    unittest.main()
