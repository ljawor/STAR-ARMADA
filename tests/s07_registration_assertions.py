"""Shared S06 authoring guards for the bounded, explicit S07 opt-in publication."""
import hashlib
import json
from unittest.mock import patch

S07_AUTHORITY = 's07-opt-in-continuation-2026-10-18'
S06_DECISIONS = frozenset({
    's06-cruiser-review-2026-10-17', 's06-b1-alliance-combat-2026-10-17',
    's06-b2-squadron-logistics-2026-10-17', 's06-b3b-stations-2026-10-17',
    's06-b3c-stations-2026-10-17', 's06-b3a-command-stations-2026-10-17',
    's06-b4-hardware-2026-10-17', 's06-b5-environment-2026-10-17',
    's06-b6-imperial-ships-2026-10-18', 's06-b7-imperial-stations-2026-10-18',
    's06-b8-remaining-combat-2026-10-18', 's06-b9-construction-2026-10-18',
})
TRIO = {'rebel:battleship', 'rebel:frigate', 'rebel:shipyard'}


def load(root, relative):
    return json.loads((root / relative).read_bytes())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_opt_in_registration(test, root, bindings=None):
    """Check real authority, exact membership, immutable pins and publication receipts.

    Appearance approval alone never grants registration. Only the twelve original
    decisions supply the 99-row increment; later scaffold approval is not inherited.
    No substring search over JSON is used for identity or decision membership.
    """
    policy = load(root, 'art/manifests/pipeline_policy.json')
    authorities = [d for d in policy['decision_log'] if d['id'] == S07_AUTHORITY]
    test.assertEqual(len(authorities), 1, 'missing/ambiguous S07 execution authority')
    test.assertEqual(authorities[0]['decision'], 'authorized-execution-not-appearance')
    approvals = load(root, 'art/manifests/approvals.json')
    decisions = [d for d in approvals['decision_log'] if d['id'] in S06_DECISIONS]
    test.assertEqual({d['id'] for d in decisions}, S06_DECISIONS)
    test.assertEqual(len(decisions), 12)
    approved = {}
    for decision in decisions:
        test.assertEqual(decision['approval_kind'], 'appearance-batch-revisions')
        test.assertEqual(decision['decision'], 'approved')
        for asset in decision['revision']['assets']:
            binding = asset['gameplay_binding']
            test.assertNotIn(binding, approved, 'duplicate original S06 approval')
            approved[binding] = (decision, asset)
    test.assertEqual(len(approved), 99)
    test.assertTrue(TRIO.isdisjoint(approved))
    test.assertEqual({a['shape_key'] for a in approvals['approved_assets']}, TRIO,
                     'registration must not rewrite the historical trio approval list')
    expected = set(approved) | TRIO
    registry = load(root, 'assets/models/registry.json')
    rows = {r['binding']: r for r in registry['bindings']}
    test.assertEqual(len(rows), len(registry['bindings']))
    test.assertEqual({b for b, r in rows.items() if r['status'] == 'core'}, expected,
                     'only the trio and exact original approved 99 may be core')
    pipeline = load(root, 'art/manifests/pipeline.json')
    entries = {a['binding']: a for a in pipeline['assets']}
    test.assertEqual(set(entries), expected)
    test.assertEqual(len(pipeline['assets']), 102)
    test.assertEqual(set(pipeline['batches']['approved-s06']), set(approved))
    test.assertEqual(len(pipeline['batches']['approved-s06']), 99)
    manifests = {p.name: load(root, str(p.relative_to(root)))
                 for p in (root / 'assets/models/manifests').glob('*.json')}
    names = {a['identifier'] + '.json' for _, a in approved.values()}
    names.update(('alliance_battleship.json', 'alliance_frigate.json', 'alliance_shipyard.json'))
    test.assertEqual(set(manifests), names)
    test.assertEqual({m['asset'] for m in manifests.values()}, {r['manifest'] for b, r in rows.items()
                                                            if b in expected})
    receipts = load(root, 'assets/models/approval-receipts.json')['receipts']
    test.assertEqual(set(receipts), {m['asset'] for m in manifests.values()})
    hashes = load(root, 'art/manifests/approved-s06-source-hashes.json')
    requested = set(approved) if bindings is None else set(bindings)
    test.assertTrue(requested <= set(approved), 'a pending or separately approved row is not S06-authorized')
    for binding in sorted(requested):
        with test.subTest(binding=binding):
            decision, asset = approved[binding]
            row, entry = rows[binding], entries[binding]
            manifest = manifests[asset['identifier'] + '.json']
            receipt = receipts[manifest['asset']]
            test.assertEqual(row['manifest'], manifest['asset'])
            test.assertEqual(entry['asset_id'], manifest['asset'])
            test.assertEqual(entry['authority'], asset['source_authority'].split('-', 1)[0])
            test.assertIn(entry['source'], asset['source'])
            test.assertIn(entry['exporter'], asset['exporter'])
            test.assertIn(entry['export_script'], asset['exporter'])
            test.assertEqual(entry['approval']['decision_id'], decision['id'])
            test.assertEqual(row['envelope_decision'], decision['id'])
            test.assertEqual(manifest['approval']['decision_id'], decision['id'])
            test.assertEqual(receipt['decision_id'], decision['id'])
            test.assertEqual(receipt['reviewed_revision'], manifest['revision'])
            canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
            test.assertEqual(receipt['manifest_sha256'], hashlib.sha256(canonical).hexdigest())
            for group in ('source', 'exporter', 'runtime'):
                for relative, digest in asset[group].items():
                    test.assertEqual(hashes[relative], digest)
                    test.assertEqual(sha256(root / relative), digest)
            mesh = manifest['files']['mesh']
            test.assertEqual(asset['runtime'][mesh['path']], mesh['sha256'])
            test.assertEqual(entry['runtime'], mesh['path'])
            test.assertEqual((root / mesh['path']).stat().st_size, mesh['bytes'])
            test.assertEqual(set(receipt['evidence_sha256']), set(manifest['approval']['reviewed_evidence']))
            test.assertTrue(receipt['evidence_sha256'], 'publication needs actual original evidence')
            for relative, digest in receipt['evidence_sha256'].items():
                test.assertEqual(sha256(root / relative), digest)
    # Negative controls cover all remaining rows, including later appearance approvals.
    scaffold = 'shared:construction_scaffold'
    test.assertEqual(rows[scaffold]['status'], 'procedural_legacy')
    test.assertNotIn(scaffold, entries)
    for binding, row in rows.items():
        if binding not in expected:
            test.assertIn(row['status'], ('procedural_legacy', 'authoring_pending',
                                         'keep_procedural_proposed', 'out_of_scope'))
            test.assertNotIn(binding, entries)
            test.assertNotIn(row['manifest'], receipts)
    for planned in load(root, 'art/manifests/model_inventory.json')['planned_hulls']['hulls']:
        test.assertNotIn(planned['mesh_key'], expected)
    return approved


def assert_preview_boundary(test, root, bindings):
    """Exercise real CPU resolver off/on/off without a selection patch or GL context."""
    from render import asset_selection as selection
    with patch.multiple(selection, _selection={'model_preview': False, 'visual_packs': []},
                        _resolver=None, _generation=0, _renderer_owners=set()):
        selection.configure({}, asset_root=root)
        for binding in bindings:
            test.assertIsNone(selection.mesh_for(binding))
        selection.configure({'model_preview': True}, asset_root=root)
        for binding in bindings:
            test.assertIsNotNone(selection.mesh_for(binding), selection.diagnostics())
        for binding in ('shared:construction_scaffold', 'syndicate:bomber', 'syndicate:battleship'):
            test.assertIsNone(selection.mesh_for(binding))
        selection.configure({})
        for binding in bindings:
            test.assertIsNone(selection.mesh_for(binding))
