"""Deterministic S06 registration; generated metadata is staged only in temp roots."""
import json
import hashlib
from collections import Counter
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.art.sync_runtime_metadata import outputs

ROOT = Path(__file__).resolve().parents[1]


class RegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generated = outputs(ROOT)

    def input_copy(self):
        temporary = tempfile.TemporaryDirectory(prefix='s07-registration-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        paths = set()
        for name in ('approved-s06-source-hashes.json', 'approved-s07-scaffold-source-hashes.json'):
            paths.update(json.loads(self.generated['art/manifests/' + name]))
        for receipt in json.loads(self.generated['assets/models/approval-receipts.json'])['receipts'].values():
            paths.update(receipt['evidence_sha256'])
        approvals = json.loads((ROOT / 'art/manifests/approvals.json').read_bytes())
        scaffold = next(d for d in approvals['decision_log']
                        if d['id'] == 's07-scaffold-appearance-2026-10-18')
        paths.update(scaffold['revision']['assets'][0]['evidence']['sha256'])
        paths.update(['art/manifests/approvals.json', 'art/manifests/pipeline.json',
                      'art/manifests/pipeline_policy.json', 'art/manifests/model_inventory.json'])
        for directory in ['art/manifests/pending', 'art/schemas', 'assets/data/ships']:
            paths.update(str(p.relative_to(ROOT)) for p in (ROOT / directory).rglob('*') if p.is_file())
        for relative in paths:
            source, target = ROOT / relative, root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return root

    def test_rejects_unsafe_asset_identifiers_before_manifest_generation(self):
        root = self.input_copy()
        path = root / 'art/manifests/approvals.json'
        original = json.loads(path.read_bytes())
        for identifier in ('../escape', '/absolute', 'nested/name', r'nested\name',
                           '.', '..', '', 'UPPER', 'trailing.', 'white space'):
            with self.subTest(identifier=identifier):
                data = json.loads(json.dumps(original))
                decision = next(d for d in data['decision_log']
                                if d.get('approval_kind') == 'appearance-batch-revisions')
                decision['revision']['assets'][0]['identifier'] = identifier
                path.write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'unsafe asset identifier'):
                    outputs(root)

    def test_rejects_manifest_identifiers_aliasing_other_specimens_or_trio(self):
        root = self.input_copy()
        path = root / 'art/manifests/approvals.json'
        original = json.loads(path.read_bytes())
        trio_identifier = next((root / 'art/schemas/examples/manifests').glob('*.json')).stem
        for collision in ('specimen', 'trio'):
            with self.subTest(collision=collision):
                data = json.loads(json.dumps(original))
                assets = [a for d in data['decision_log']
                          if d.get('approval_kind') == 'appearance-batch-revisions'
                          for a in d['revision']['assets']]
                assets[0]['identifier'] = assets[1]['identifier'] if collision == 'specimen' else trio_identifier
                path.write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'conflicting manifest'):
                    outputs(root)

    def test_publication_preflights_every_destination_without_partial_writes(self):
        from tools.art import sync_runtime_metadata as sync
        for kind in ('absolute', 'traversal', 'dot', 'empty-part', 'backslash',
                     'symlink-parent', 'symlink-file', 'case-alias', 'hardlink-alias',
                     'file-parent', 'directory-target'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                root = base / 'root'
                root.mkdir()
                outside = base / 'outside'
                outside.mkdir()
                sentinel = outside / 'sentinel.json'
                sentinel.write_bytes(b'external sentinel')
                good = root / 'first.json'
                good.write_bytes(b'original')
                expected = {'first.json': b'updated'}
                bad = {'absolute': str(sentinel), 'traversal': '../outside/sentinel.json',
                       'dot': './other.json', 'empty-part': 'nested//other.json',
                       'backslash': r'nested\other.json', 'symlink-parent': 'link/sentinel.json',
                       'symlink-file': 'link.json', 'case-alias': 'FIRST.json',
                       'hardlink-alias': 'alias.json', 'file-parent': 'first.json/child.json',
                       'directory-target': 'directory.json'}[kind]
                if kind == 'symlink-parent':
                    (root / 'link').symlink_to(outside, target_is_directory=True)
                elif kind == 'symlink-file':
                    (root / 'link.json').symlink_to(sentinel)
                elif kind == 'hardlink-alias':
                    (root / 'alias.json').hardlink_to(good)
                elif kind == 'directory-target':
                    (root / bad).mkdir()
                # Even an unchanged escape must be preflighted, not just drift.
                expected[bad] = b'external sentinel' if kind.startswith('symlink') else b'bad'
                before = sorted(p.relative_to(root).as_posix() for p in root.rglob('*'))
                with patch.object(sync, 'ROOT', root), patch.object(sync, 'outputs', return_value=expected), \
                        patch.object(sys, 'argv', ['sync_runtime_metadata', '--write']):
                    with self.assertRaisesRegex(ValueError, 'unsafe|conflicting'):
                        sync.main()
                self.assertEqual(good.read_bytes(), b'original')
                self.assertEqual(sentinel.read_bytes(), b'external sentinel')
                self.assertEqual(sorted(p.relative_to(root).as_posix() for p in root.rglob('*')), before)

    def test_publication_failure_restores_entire_output_set(self):
        from tools.art import sync_runtime_metadata as sync
        import os
        for failure, fail_at in (('stage', 2), ('stage', 3), ('replace', 2), ('replace', 3)):
            with self.subTest(failure=failure, fail_at=fail_at), tempfile.TemporaryDirectory() as temporary:
                # Publication canonicalizes root; fault injection must name that same
                # destination on macOS (/var and /private/var alias one directory).
                root = Path(temporary).resolve()
                (root / 'old.json').write_bytes(b'original')
                expected = {'new/sub/file.json': b'new', 'old.json': b'updated', 'last.json': b'last'}
                original_write = Path.write_bytes
                original_replace = os.replace
                calls = 0

                def fail_write(path, data):
                    nonlocal calls
                    calls += 1
                    if calls == fail_at:
                        raise OSError('injected staging failure')
                    return original_write(path, data)

                def fail_replace(source, destination):
                    nonlocal calls
                    if Path(destination) in (root / p for p in expected):
                        calls += 1
                        if calls == fail_at:
                            raise OSError('injected replacement failure')
                    return original_replace(source, destination)

                injection = (patch.object(Path, 'write_bytes', fail_write) if failure == 'stage'
                             else patch.object(os, 'replace', fail_replace))
                with patch.object(sync, 'ROOT', root), patch.object(sync, 'outputs', return_value=expected), \
                        patch.object(sys, 'argv', ['sync_runtime_metadata', '--write']), injection:
                    with self.assertRaisesRegex(OSError, 'injected'):
                        sync.main()
                self.assertEqual((root / 'old.json').read_bytes(), b'original')
                self.assertEqual(sorted(p.relative_to(root).as_posix() for p in root.rglob('*')), ['old.json'])

    def test_refuses_registration_without_explicit_execution_authority(self):
        root = self.input_copy()
        path = root / 'art/manifests/pipeline_policy.json'
        policy = json.loads(path.read_bytes())
        policy['decision_log'] = [d for d in policy['decision_log']
                                  if d['id'] != 's07-opt-in-continuation-2026-10-18']
        path.write_text(json.dumps(policy), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'execution authority'):
            outputs(root)

    def test_regeneration_after_publication_is_idempotent_and_preserves_inputs(self):
        root = self.input_copy()
        before = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in root.rglob('*') if p.is_file()}
        generated = outputs(root)
        from tools.art import sync_runtime_metadata as sync
        with patch.object(sync, 'ROOT', root), \
                patch.object(sys, 'argv', ['sync_runtime_metadata', '--write']):
            self.assertEqual(sync.main(), 0)
            self.assertEqual(sync.main(), 0)
        for relative, data in generated.items():
            self.assertEqual((root / relative).read_bytes(), data)
        self.assertFalse(any(p.name.startswith('.s07-metadata-') for p in root.rglob('*')))
        self.assertEqual(outputs(root), generated)
        for relative, expected in before.items():
            if relative not in generated:
                self.assertEqual(hashlib.sha256((root / relative).read_bytes()).hexdigest(), expected)

    def test_regenerates_stale_corvette_registry_facts_without_dropping_row(self):
        root = self.input_copy()
        registry = json.loads(self.generated['assets/models/registry.json'])
        expected = next(row for row in registry['bindings'] if row['binding'] == 'rebel:corvette')
        stale = dict(expected, category='station',
                     identity={'faction': 'imperial', 'class_or_kind': 'frigate'},
                     manifest='core:alliance/frigate', legacy_identifiers=['wrong_corvette_alias'],
                     envelope={'min': [-100, -100, -100], 'max': [100, 100, 100]})
        path = root / 'art/schemas/examples/core-registry.json'
        source = json.loads(path.read_bytes())
        source['bindings'] = [row for row in source['bindings'] if row['binding'] != 'rebel:corvette'] + [stale]
        path.write_text(json.dumps(source), encoding='utf-8')
        regenerated = json.loads(outputs(root)['assets/models/registry.json'])
        self.assertEqual(next(row for row in regenerated['bindings'] if row['binding'] == 'rebel:corvette'), expected)

    def test_rejects_wrong_real_script_selector(self):
        root = self.input_copy()
        path = root / 'art/manifests/pending/S06-IMPERIAL-CORVETTE.json'
        data = json.loads(path.read_bytes())
        data['initial_seed']['selects'] = '--asset ship:imperial:frigate'
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'selector'):
            outputs(root)

    def test_pipeline_authorities_and_existing_trio_are_preserved(self):
        generated = self.generated
        original = json.loads((ROOT / 'art/manifests/pipeline.json').read_bytes())
        pipeline = json.loads(generated['art/manifests/pipeline.json'])
        trio = original['batches']['approved-trio']
        self.assertEqual([a for a in pipeline['assets'] if a['binding'] in trio],
                         [a for a in original['assets'] if a['binding'] in trio])
        original99 = set(pipeline['batches']['approved-s06'])
        decisions = json.loads((ROOT / 'art/manifests/approvals.json').read_bytes())
        approved99 = {a['gameplay_binding'] for d in decisions['decision_log']
                      if d.get('approval_kind') == 'appearance-batch-revisions'
                      for a in d['revision']['assets']}
        self.assertEqual(original99, approved99)
        self.assertEqual(len(original99), 99)
        self.assertNotIn('shared:construction_scaffold', original99)
        new = [a for a in pipeline['assets'] if a['binding'] in original99]
        self.assertEqual({a['binding'] for a in new}, original99)
        self.assertEqual(pipeline['batches']['approved-s07-scaffold'], ['shared:construction_scaffold'])
        scaffold = [a for a in pipeline['assets'] if a['binding'] == 'shared:construction_scaffold']
        self.assertEqual(Counter(a['authority'] for a in scaffold), {'script': 1})
        self.assertEqual(len(pipeline['assets']), 103)
        self.assertEqual(Counter(a['authority'] for a in new), {'blend': 66, 'script': 33})
        by_binding = {a['binding']: a for a in new}
        self.assertEqual(by_binding['imperial:corvette']['build_args'], ['--asset', 'ship:imperial:corvette'])
        self.assertEqual(by_binding['rebel:defense_satellite']['build_args'], ['--asset', 'rebel:defense_satellite'])
        for entry in new:
            self.assertEqual(entry['export_args'], [])
            self.assertNotIn('--replace-seed', entry['build_args'])
        hashes = json.loads(generated['art/manifests/approved-s06-source-hashes.json'])
        for relative, expected in hashes.items():
            self.assertIsInstance(expected, str)
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), expected)
        receipts = json.loads(generated['assets/models/approval-receipts.json'])['receipts']
        original_receipts = json.loads((ROOT / 'assets/models/approval-receipts.json').read_bytes())['receipts']
        for path in (ROOT / 'art/schemas/examples/manifests').glob('*.json'):
            self.assertEqual(generated['assets/models/manifests/' + path.name], path.read_bytes())
            asset = json.loads(path.read_bytes())['asset']
            self.assertEqual(receipts[asset], original_receipts[asset])
        self.assertFalse(any('/provenance/' in p for p in generated))

    def test_resolver_loads_original_102_plus_separate_scaffold_in_assets_only_frozen_root(self):
        from render.asset_registry import AssetResolver
        from render import asset_selection as selection
        temporary = tempfile.TemporaryDirectory(prefix='s07-frozen-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        generated = self.generated
        for relative, data in generated.items():
            if relative.startswith('assets/'):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        manifests = [json.loads(v) for k, v in generated.items()
                     if k.startswith('assets/models/manifests/')]
        for manifest in manifests:
            relative = manifest['files']['mesh']['path']
            shutil.copy2(ROOT / relative, root / relative)
        self.assertEqual({p.name for p in root.iterdir()}, {'assets'})
        registry = json.loads(generated['assets/models/registry.json'])
        with patch.object(sys, '_MEIPASS', str(root), create=True):
            resolver = AssetResolver()
        loaded = 0
        for row in registry['bindings']:
            if row['status'] != 'core':
                continue
            with self.subTest(binding=row['binding']):
                resolved = resolver.resolve(row['binding'])
                self.assertIsNotNone(resolved, resolver.diagnostics)
                self.assertEqual(resolved.asset, row['manifest'])
                for alias in row.get('legacy_identifiers', []):
                    self.assertEqual(resolver.resolve(alias).revision, resolved.revision)
                loaded += 1
        self.assertEqual(loaded, 103)
        pipeline = json.loads(generated['art/manifests/pipeline.json'])
        original102 = set(pipeline['batches']['approved-s06']) | set(pipeline['batches']['approved-trio'])
        self.assertEqual(len(original102), 102)
        self.assertNotIn('shared:construction_scaffold', original102)
        self.assertEqual({r['binding'] for r in registry['bindings'] if r['status'] == 'core'},
                         original102 | {'shared:construction_scaffold'})
        self.assertIsNotNone(resolver.resolve('shared:construction_scaffold'))
        self.assertIsNone(resolver.resolve('syndicate:bomber'))
        inventory = json.loads((ROOT / 'art/manifests/model_inventory.json').read_bytes())
        for planned in inventory['planned_hulls']['hulls']:
            self.assertIsNone(resolver.resolve(planned['mesh_key']))
        mapping = json.loads(generated['assets/models/catalogue-map.json'])
        for faction in ('rebel', 'imperial', 'syndicate', 'confederacy'):
            crew = mapping['inventory_bindings'][f'ship:{faction}:crew_transport']
            trade = mapping['inventory_bindings'][f'ship:{faction}:trade_convoy']
            self.assertEqual(crew, trade)
            self.assertEqual(crew, f'{faction}:convoy')
            self.assertIsNotNone(resolver.resolve(crew))
        self.assertEqual(mapping['inventory_bindings']['ship:rebel:corvette'], 'rebel:corvette')
        self.assertIn('rebel:corvette', mapping['legacy_ship_shapes'])
        # Metadata registration is not a production-default switch.
        with patch.multiple(selection, _selection={'model_preview': False, 'visual_packs': []},
                            _resolver=None, _generation=0, _renderer_owners=set()):
            selection.configure({}, asset_root=root)
            for row in registry['bindings']:
                self.assertIsNone(selection.mesh_for(row['binding']))
            selection.configure({'model_preview': True}, asset_root=root)
            self.assertIsNotNone(selection.mesh_for('rebel:corvette'))
            self.assertIsNotNone(selection.mesh_for('imperial:command_station'))
            self.assertIsNotNone(selection.mesh_for('shared:construction_scaffold'))
            selection.configure({'model_preview': False}, asset_root=root)
            self.assertIsNone(selection.mesh_for('rebel:corvette'))

    def test_rejects_rehashed_evidence_from_a_different_runtime(self):
        root = self.input_copy()
        path = root / 'artifacts/s06_alliance_batch_review/b1-alliance-combat/metrics.json'
        data = json.loads(path.read_bytes())
        data['mesh']['rebel:corvette']['sha256'] = '0' * 64
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'evidence/runtime mismatch'):
            outputs(root)

    def test_rejects_corrupt_approved_pin(self):
        root = self.input_copy()
        path = root / 'tools/art/build_b4_hardware.py'
        path.write_bytes(path.read_bytes() + b'\n# corrupt pin\n')
        with self.assertRaisesRegex(ValueError, 'approved pin mismatch'):
            outputs(root)

    def test_rejects_corrupt_pinned_evidence(self):
        root = self.input_copy()
        path = root / 'artifacts/s06-completion/review-b7-attempt2/render/contact-sheet.png'
        path.write_bytes(b'not the approved sheet')
        with self.assertRaisesRegex(ValueError, 'approved pin mismatch'):
            outputs(root)

    def test_rejects_noncanonical_safe_evidence_paths_without_normalizing(self):
        from tools.art.s07_registration import safe_file
        for relative in ('./art/manifests/approvals.json', 'art//manifests/approvals.json'):
            with self.subTest(relative=relative):
                with self.assertRaisesRegex(ValueError, 'unsafe registration path'):
                    safe_file(ROOT, relative)

    def test_rejects_missing_evidence(self):
        root = self.input_copy()
        (root / 'artifacts/s06_alliance_batch_review/b1-alliance-combat/contact-sheet.png').unlink()
        with self.assertRaisesRegex(ValueError, 'missing/unsafe registration file'):
            outputs(root)

    def test_rejects_arbitrary_cruiser_evidence_beside_real_report(self):
        root = self.input_copy()
        path = root / 'art/manifests/pending/S06-ALLIANCE-CRUISER.json'
        data = json.loads(path.read_bytes())
        arbitrary = 'artifacts/s06_alliance_cruiser_review/fixed-review/capture/arbitrary.png'
        (root / arbitrary).write_bytes(b'unrelated image, real metrics next door')
        data['evidence'] = arbitrary
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'evidence'):
            outputs(root)

    def test_exact_approved_set_and_deterministic_outputs(self):
        generated = outputs(ROOT)
        registry = json.loads(generated['assets/models/registry.json'])
        approved = {r['binding'] for r in registry['bindings'] if r['status'] == 'core'}
        decisions = json.loads((ROOT / 'art/manifests/approvals.json').read_bytes())
        expected = {a['shape_key'] for a in decisions['approved_assets']}
        expected.update(a['gameplay_binding'] for d in decisions['decision_log']
                        if d.get('approval_kind') == 'appearance-batch-revisions'
                        for a in d['revision']['assets'])
        self.assertEqual(len(expected), 102)
        self.assertNotIn('shared:construction_scaffold', expected)
        self.assertEqual(approved, expected | {'shared:construction_scaffold'})
        self.assertNotIn('syndicate:bomber', approved)
        self.assertNotIn('confederacy:supercarrier', approved)
        self.assertEqual(generated, outputs(ROOT))
        manifests = [json.loads(v) for k, v in generated.items()
                     if k.startswith('assets/models/manifests/')]
        self.assertEqual(len(manifests), 103)
        self.assertEqual(len(json.loads(generated['assets/models/approval-receipts.json'])['receipts']), 103)


if __name__ == '__main__':
    unittest.main()
