"""Separate scaffold opt-in publication; no shared metadata or approved-art writes."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools.art import s07_registration as registration
from tools.art import sync_runtime_metadata as sync

ROOT = Path(__file__).resolve().parents[1]
BINDING = 'shared:construction_scaffold'
DECISION = 's07-scaffold-appearance-2026-10-18'
MANIFEST = 'assets/models/manifests/shared_construction_scaffold.json'
HASHES = 'art/manifests/approved-s07-scaffold-source-hashes.json'
BATCH = 'approved-s07-scaffold'


class ScaffoldRegistrationTests(unittest.TestCase):
    def test_explicit_increment_preserves_original_99_and_trio(self):
        root = self.input_copy(full=True, pre_scaffold=True)
        original = sync.outputs(root)
        # The old increment must remain usable and byte-identical by default.
        self.assertNotIn(MANIFEST, original)
        expanded = sync.outputs(root, include_scaffold=True)
        self.assertIn(MANIFEST, expanded)
        permitted = {'assets/models/registry.json', 'assets/models/approval-receipts.json',
                     'art/manifests/pipeline.json'}
        for relative, data in original.items():
            if relative not in permitted:
                self.assertEqual(expanded[relative], data, relative)
        self.assertEqual(set(expanded) - set(original), {MANIFEST, HASHES})
        old = json.loads(original['art/manifests/pipeline.json'])
        new = json.loads(expanded['art/manifests/pipeline.json'])
        self.assertEqual([a for a in new['assets'] if a['binding'] != BINDING], old['assets'])
        self.assertEqual(new['batches'][BATCH], [BINDING])
        self.assertEqual({k: v for k, v in new['batches'].items() if k != BATCH}, old['batches'])
        manifest = json.loads(expanded[MANIFEST])
        self.assertEqual(manifest['approval']['decision_id'], DECISION)
        self.assertIn('No rebuild or fresh export is attested', manifest['provenance']['notes'])
        self.assertNotIn('original S06', manifest['provenance']['notes'])
        receipts = json.loads(expanded['assets/models/approval-receipts.json'])['receipts']
        old_receipts = json.loads(original['assets/models/approval-receipts.json'])['receipts']
        self.assertEqual({k: v for k, v in receipts.items() if k != manifest['asset']}, old_receipts)
        self.assertEqual(receipts[manifest['asset']]['decision_id'], DECISION)
        self.assertFalse(any('/provenance/' in p for p in expanded))

    def input_copy(self, full=False, pre_scaffold=False):
        temporary = tempfile.TemporaryDirectory(prefix='s07-scaffold-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        approvals = json.loads((ROOT / 'art/manifests/approvals.json').read_bytes())
        decision = next(d for d in approvals['decision_log'] if d['id'] == DECISION)
        asset = decision['revision']['assets'][0]
        paths = set(asset['evidence']['sha256'])
        for group in ('source', 'exporter', 'runtime'):
            paths.update(asset[group])
        paths.update(('art/manifests/approvals.json', 'art/manifests/pipeline_policy.json',
                      'art/manifests/pipeline.json',
                      'art/manifests/pending/S06-SHARED-CONSTRUCTION-SCAFFOLD.json'))
        if full:
            generated = sync.outputs(ROOT)
            for name in ('approved-s06-source-hashes.json', 'approved-s07-scaffold-source-hashes.json'):
                paths.update(json.loads(generated['art/manifests/' + name]))
            for receipt in json.loads(generated['assets/models/approval-receipts.json'])['receipts'].values():
                paths.update(receipt['evidence_sha256'])
            paths.add('art/manifests/model_inventory.json')
            for directory in ('art/manifests/pending', 'art/schemas', 'assets/data/ships'):
                paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / directory).rglob('*') if p.is_file())
        for relative in paths:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        if pre_scaffold:
            # Only disposable pipeline metadata is rewound; approval/source/evidence
            # bytes remain the real published inputs for the separate increment.
            path = root / 'art/manifests/pipeline.json'
            pipeline = json.loads(path.read_bytes())
            pipeline['batches'].pop(BATCH)
            pipeline['assets'] = [a for a in pipeline['assets'] if a['binding'] != BINDING]
            path.write_text(json.dumps(pipeline), encoding='utf-8')
        return root

    def publish_scaffold(self, root):
        rows = {BINDING: {'binding': BINDING, 'status': 'procedural_legacy'}}
        return registration.publish_scaffold(
            root, rows, {'construction:site:scaffold': BINDING}, {BINDING: 'construction'})

    def test_manifest_evidence_is_bounded_and_receipt_matches_curated_pin_map(self):
        generated = sync.outputs(ROOT)
        manifest = json.loads(generated[MANIFEST])
        receipts = json.loads(generated['assets/models/approval-receipts.json'])['receipts']
        approvals = json.loads((ROOT / 'art/manifests/approvals.json').read_bytes())
        approved = next(d for d in approvals['decision_log'] if d['id'] == DECISION)
        pins = approved['revision']['assets'][0]['evidence']['sha256']
        evidence = manifest['approval']['reviewed_evidence']
        self.assertTrue(evidence)
        self.assertLessEqual(len(evidence), 24)
        self.assertEqual(len(evidence), len(set(evidence)))
        self.assertTrue(set(evidence).issubset(pins))
        self.assertEqual(len(pins), 29)
        self.assertEqual(receipts[manifest['asset']]['evidence_sha256'],
                         {relative: pins[relative] for relative in evidence})
        for relative, expected in pins.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), expected, relative)

    def test_publisher_validates_original_pins_omitted_from_runtime_receipt(self):
        root = self.input_copy()
        generated = sync.outputs(ROOT)
        manifest = json.loads(generated[MANIFEST])
        approvals = json.loads((root / 'art/manifests/approvals.json').read_bytes())
        asset = next(d for d in approvals['decision_log'] if d['id'] == DECISION)['revision']['assets'][0]
        omitted = set(asset['evidence']['sha256']) - set(manifest['approval']['reviewed_evidence'])
        self.assertTrue(omitted, 'negative control must target a non-runtime approval pin')
        path = root / sorted(omitted)[0]
        path.write_bytes(path.read_bytes() + b'corrupt omitted original evidence')
        with self.assertRaisesRegex(ValueError, 'approved pin mismatch'):
            self.publish_scaffold(root)

    def test_missing_separate_execution_authority_fails_closed(self):
        root = self.input_copy()
        path = root / 'art/manifests/pipeline_policy.json'
        policy = json.loads(path.read_bytes())
        policy['decision_log'] = [d for d in policy['decision_log']
                                  if d['id'] != 's07-scaffold-registration-2026-10-19']
        path.write_text(json.dumps(policy), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'separate scaffold execution authority'):
            self.publish_scaffold(root)

    def test_separate_appearance_decision_cannot_be_replaced_by_ship_batch(self):
        root = self.input_copy()
        path = root / 'art/manifests/approvals.json'
        approvals = json.loads(path.read_bytes())
        approvals['decision_log'] = [d for d in approvals['decision_log'] if d['id'] != DECISION]
        path.write_text(json.dumps(approvals), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'separate scaffold appearance approval'):
            self.publish_scaffold(root)

    def test_original_evidence_bytes_are_enforced(self):
        root = self.input_copy()
        approvals = json.loads((root / 'art/manifests/approvals.json').read_bytes())
        asset = next(d for d in approvals['decision_log'] if d['id'] == DECISION)['revision']['assets'][0]
        path = root / asset['evidence']['sheet']
        path.write_bytes(path.read_bytes() + b'corrupt')
        with self.assertRaisesRegex(ValueError, 'approved pin mismatch'):
            self.publish_scaffold(root)

    def test_captured_runtime_and_capture_code_identity_are_enforced(self):
        for field, value in [('captured_runtime_sha256', '0' * 64),
                             ('capture_code_sha256', {'render/renderer.py': '0' * 64})]:
            with self.subTest(field=field):
                root = self.input_copy()
                path = root / 'art/manifests/approvals.json'
                approvals = json.loads(path.read_bytes())
                asset = next(d for d in approvals['decision_log'] if d['id'] == DECISION)['revision']['assets'][0]
                asset['evidence'][field] = value
                path.write_text(json.dumps(approvals), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'evidence/runtime provenance mismatch'):
                    self.publish_scaffold(root)

    def test_scaffold_rejects_symlinked_approved_input_even_inside_root(self):
        root = self.input_copy()
        path = root / 'art/blender/shared_construction_scaffold.blend'
        alias = path.with_name('same-bytes.blend')
        path.rename(alias)
        path.symlink_to(alias.name)
        with self.assertRaisesRegex(ValueError, 'symlink|alias'):
            self.publish_scaffold(root)

    def test_published_separate_increment_is_preserved_without_repeating_flag(self):
        root = self.input_copy(full=True, pre_scaffold=True)
        self.assertNotIn(MANIFEST, sync.outputs(root))
        expected = sync.outputs(root, include_scaffold=True)
        destinations = sync.output_destinations(root, expected)
        drift = [p for p, data in expected.items() if not destinations[p].is_file()
                 or destinations[p].read_bytes() != data]
        sync.publish_outputs(destinations, expected, drift)
        self.assertEqual(sync.outputs(root), expected)
        self.assertEqual(sync.outputs(root, include_scaffold=True), expected)


if __name__ == '__main__':
    unittest.main()
