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
    # The first B6 row, approved on the picture rather than on a word: one hull, not the batch.
    # Three rows, approved one picture at a time and recorded in one decision: both exchanges are in the
    # string, because a batch sheet and its decision have to name the same rows.
    's06-b6-imperial-ships-2026-10-18':
        'Picture approved (the corvette); picture approved. Continue (the two TIE squadrons); '
        'picture approved, continue (the two dagger capitals, the cruiser and the frigate); '
        'Pictures approved (the Imperial convoy)',
    's06-b7-imperial-stations-2026-10-18': 'approved',
    's06-b8-remaining-combat-2026-10-18': 'approved',
    's06-b9-construction-2026-10-18': 'approved',
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
    's06-b6-imperial-ships': 8,
    's06-b7-imperial-stations': 10,
    's06-b8-remaining-combat': 8,
    's06-b9-construction': 8,
}
# Exact enumerated appearance approvals, not registrations.
APPROVED_SPECIMENS = 99
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


def appearance_decisions(kind='appearance-batch-revisions'):
    return [d for d in load(APPROVALS)['decision_log'] if d.get('approval_kind') == kind]

#: `appearance-revision` decisions are outside the batch sweep (it walks
#: `appearance-batch-revisions`), so their pins were never checked by anything. One of them is
#: stale and is not a renderer change's to re-pin: the battleship entry pins an `alliance_common.py`
#: from before a later edit to that helper, and re-pinning another owner's decision would rewrite
#: what they approved. Named here so the gap is debt rather than silence.
KNOWN_STALE_REVISION_PINS = {
    's06-battleship-hull-detail-2026-10-16': {'tools/art/alliance_common.py'},
}

class RecordedApprovals(unittest.TestCase):
    def test_every_revision_decision_matches_the_files_it_pins(self):
        # The batch sweep above walks `appearance-batch-revisions` only, and the B5 re-authoring
        # was recorded as an `appearance-revision`, so for a while nothing asserted its hashes at
        # all - a hole a reviewer had to catch by hand. This walks them.
        problems = []
        for decision in appearance_decisions('appearance-revision'):
            stale = KNOWN_STALE_REVISION_PINS.get(decision['id'], set())
            groups = decision['revision']
            for group in ('source', 'exporter', 'runtime'):
                for path, want in groups.get(group, {}).items():
                    if path in stale:
                        continue
                    target = ROOT / path
                    got = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
                    if got != want:
                        problems.append((decision['id'], group, path, want[:12], (got or 'missing')[:12]))
        self.assertEqual(problems, [],
                         'a revision decision does not match the files it pins: '
                         + '; '.join(f'{d} {g} {p} want {w} got {h}' for d, g, p, w, h in problems))

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

    def test_only_authorized_s06_specimens_register_with_legacy_default(self):
        """S07 execution authority registers exact approved revisions, not pending rows."""
        from s07_registration_assertions import assert_opt_in_registration, assert_preview_boundary
        approved = assert_opt_in_registration(self, ROOT)
        assert_preview_boundary(self, ROOT, sorted(approved))

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
                    partial = batch == 's06-b9-construction'
                    self.assertEqual(sheet['status'], 'partially_appearance_approved_pending_landing'
                                     if partial else 'appearance_approved_pending_landing')
                    self.assertEqual(sheet['appearance_decision'], decision['id'])
                    identifiers = {a['identifier'] for a in sheet['assets']
                                   if not partial or a.get('appearance_decision') == decision['id']}
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


class RegistrationGuardControls(unittest.TestCase):
    """Prove the migrated shared assertions still reject unauthorized publication."""

    def reject_document_change(self, relative, mutate):
        from unittest.mock import patch
        import s07_registration_assertions as guards
        original_load = guards.load
        changed = original_load(ROOT, relative)
        mutate(changed)

        def controlled_load(root, path):
            return changed if path == relative else original_load(root, path)

        # A fresh TestCase has no running subTest outcome to absorb the assertion.
        with patch.object(guards, 'load', side_effect=controlled_load):
            with self.assertRaises(AssertionError):
                guards.assert_opt_in_registration(unittest.TestCase(), ROOT, ['rebel:corvette'])

    def test_guard_rejects_missing_execution_authority(self):
        def remove(doc):
            doc['decision_log'] = [d for d in doc['decision_log']
                                   if d['id'] != 's07-opt-in-continuation-2026-10-18']
        self.reject_document_change('art/manifests/pipeline_policy.json', remove)

    def test_guard_rejects_substring_only_authority(self):
        def rename(doc):
            for decision in doc['decision_log']:
                if decision['id'] == 's07-opt-in-continuation-2026-10-18':
                    decision['id'] += '-not-authorized'
        self.reject_document_change('art/manifests/pipeline_policy.json', rename)

    def test_guard_rejects_substring_only_appearance_decision(self):
        def rename(doc):
            for decision in doc['decision_log']:
                if decision['id'] == 's06-b1-alliance-combat-2026-10-17':
                    decision['id'] += '-unapproved'
        self.reject_document_change('art/manifests/approvals.json', rename)

    def test_guard_rejects_scaffold_registration_without_its_execution_authority(self):
        def withdraw(doc):
            doc['decision_log'] = [d for d in doc['decision_log']
                                   if d['id'] != 's07-scaffold-registration-2026-10-19']
        self.reject_document_change('art/manifests/pipeline_policy.json', withdraw)

    def test_guard_rejects_scaffold_registration_under_a_renamed_appearance_decision(self):
        def rename(doc):
            for decision in doc['decision_log']:
                if decision['id'] == 's07-scaffold-appearance-2026-10-18':
                    decision['id'] += '-unapproved'
        self.reject_document_change('art/manifests/approvals.json', rename)

    def test_guard_rejects_planned_unapproved_syndicate_hull_registration(self):
        def activate(doc):
            next(r for r in doc['bindings'] if r['binding'] == 'syndicate:bomber')['status'] = 'core'
        self.reject_document_change('assets/models/registry.json', activate)

    def test_guard_rejects_missing_original_approval_receipt(self):
        self.reject_document_change('assets/models/approval-receipts.json',
                                    lambda doc: doc['receipts'].pop('core:alliance/corvette'))

    def test_guard_rejects_receipt_from_a_different_revision(self):
        def corrupt(doc):
            doc['receipts']['core:alliance/corvette']['reviewed_revision'] = '0' * 64
        self.reject_document_change('assets/models/approval-receipts.json', corrupt)

    def test_guard_rejects_corrupt_approved_source_pin(self):
        def corrupt(doc):
            doc['tools/art/build_alliance_corvette.py'] = '0' * 64
        self.reject_document_change('art/manifests/approved-s06-source-hashes.json', corrupt)

    def test_guard_rejects_corrupt_original_evidence_receipt(self):
        def corrupt(doc):
            evidence = doc['receipts']['core:alliance/corvette']['evidence_sha256']
            evidence[next(iter(evidence))] = '0' * 64
        self.reject_document_change('assets/models/approval-receipts.json', corrupt)

    def test_guard_rejects_silent_production_default_activation(self):
        from unittest.mock import patch
        from render import asset_selection as selection
        from s07_registration_assertions import assert_preview_boundary
        configure = selection.configure

        def force_preview(settings, **kwargs):
            return configure(dict(settings, model_preview=True), **kwargs)

        with patch.object(selection, 'configure', side_effect=force_preview):
            with self.assertRaises(AssertionError):
                assert_preview_boundary(unittest.TestCase(), ROOT, ['rebel:corvette'])


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
        self.assertEqual(sorted(pending), [], 'all batch sheets now have appearance decisions; B9 is partial')
        for batch, (path, sheet) in sheets.items():
            with self.subTest(batch=batch):
                if batch in decided:
                    expected = ('partially_appearance_approved_pending_landing' if batch ==
                                's06-b9-construction' else 'appearance_approved_pending_landing')
                    self.assertEqual(sheet['status'], expected)
                    self.assertIn('appearance_decision', sheet)
                    self.assertEqual(sheet['appearance_decision'],
                                     next(d['id'] for d in appearance_decisions()
                                          if d['revision']['batch'] == batch))
                else:
                    self.assertEqual(sheet['status'], 'pending_owner_appearance_approval')
                    self.assertNotIn('appearance_decision', sheet)


if __name__ == '__main__':
    unittest.main()
