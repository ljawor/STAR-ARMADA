#!/usr/bin/env python3
"""Register the three Rim Syndicate hulls into the core catalogue.

Registration, not repackaging: the meshes move from the prototype pack to
``assets/models/`` with a core manifest each, and the registry rows move from
``authoring_pending`` to ``core`` so the shipped catalogue resolves them without
any pack being active.

The revision recipe is the one the loader enforces -- ``sha256(asset + '\\n' +
'mesh:' + sha256(mesh bytes))`` -- verified against the accepted
``core:imperial/battleship`` manifest before this script existed. Guessing it
produces manifests the loader rejects with ``E_REVISION_MISMATCH``.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / 'visual_packs' / 'syndicate-imperium-prototypes'
DECISION = 'syndicate-rework-appearance-2026-10-23'
BATCH = 'approved-syndicate-rework'
HASHES = ROOT / 'art' / 'manifests' / 'approved-syndicate-rework-source-hashes.json'

ROWS = (
    dict(stem='bomber',
         display='Rim Syndicate Cutthroat Strike Wing (approved)',
         notes='Original Rim Syndicate strike wing authored for the faction rework; occupies the '
               'measured legacy envelope.'),
    dict(stem='battleship',
         display='Rim Syndicate Marauder Battleship (approved)',
         notes='Original Rim Syndicate battleship authored for the faction rework; occupies the '
               'measured legacy envelope.'),
    dict(stem='supercapital',
         display='Rim Syndicate Leviathan Salvage Dreadnought (approved)',
         notes='Original Rim Syndicate salvage dreadnought authored for the faction rework; occupies '
               'the measured legacy envelope.'),
)


def revision(asset, mesh_sha):
    return hashlib.sha256(f'{asset}\nmesh:{mesh_sha}'.encode()).hexdigest()


def rel(path):
    return path.relative_to(ROOT).as_posix()


def main():
    receipts_path = ROOT / 'assets' / 'models' / 'approval-receipts.json'
    receipts = json.loads(receipts_path.read_text(encoding='utf-8'))
    registry_path = ROOT / 'assets' / 'models' / 'registry.json'
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    by_binding = {row['binding']: row for row in registry['bindings']}
    hashes = {}
    registered = []

    for row in ROWS:
        stem = row['stem']
        target = ROOT / 'assets' / 'models' / f'syndicate_{stem}.mesh.json'
        # Idempotent: re-running after the pack was folded into core rewrites the core
        # payload from itself, keeping the asset id and every hash stable.
        source = (PACK / 'assets' / 'models' / f'syndicate_{stem}.mesh.json')
        if not source.is_file():
            source = target
        asset = f'core:syndicate/{stem}'
        payload = json.loads(source.read_bytes())
        # The loader compares a contract payload's identity with the manifest asset, so the
        # prototype id has to become the core id before the bytes are hashed.
        payload['asset'] = asset
        raw = (json.dumps(payload, indent=2) + '\n').encode()
        target.write_bytes(raw)
        mesh_sha = hashlib.sha256(raw).hexdigest()
        rev = revision(asset, mesh_sha)
        approval_evidence = [f'artifacts/syndicate-rework/stills/syndicate_{stem}-quarter.png',
                             f'artifacts/syndicate-rework/stills/syndicate_{stem}-profile.png',
                             f'artifacts/syndicate-rework/stills/syndicate_{stem}-bow.png']
        manifest = {
            'contract': 'star-armada/model-manifest',
            'contract_major': 1,
            'asset': asset,
            'revision': rev,
            'display_name': row['display'],
            'files': {'mesh': {'path': rel(target), 'sha256': mesh_sha, 'bytes': len(raw)}},
            'export': {'contract': 'star-armada/mesh-export', 'contract_major': 1,
                       'legacy_schema_int': 1},
            'coordinates': 'X beam; Y up; +Z forward',
            'pivot': [0, 0, 0],
            'bounds': {'min': payload['bounds'][0], 'max': payload['bounds'][1]},
            'nominal_scale': 1.0,
            'roles': sorted(payload['batches']),
            'provenance': {'author': 'Lukasz Jawor', 'tool': 'Blender', 'tool_version': '5.0.1',
                           'license': 'original',
                           'source': f'art/blender/syndicate_{stem}.blend',
                           'notes': row['notes']},
            'requires': {'min_engine': '0.16.0', 'material_profile': 'core:fleet/standard'},
            'budgets': {'triangles': payload['triangle_count'], 'draw_calls': 6,
                        'texture_bytes': 0},
            'approval': {'status': 'approved', 'decision_id': DECISION, 'decided_by': 'owner',
                         'decided_on': '2026-10-23', 'reviewed_revision': rev,
                         'reviewed_evidence': approval_evidence},
        }
        manifest_path = ROOT / 'assets' / 'models' / 'manifests' / f'{stem}.json'
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

        binding = f'syndicate:{stem}'
        entry = by_binding[binding]
        entry['status'] = 'core'
        entry['manifest'] = asset
        registered.append(binding)

        # The loader verifies a packaged receipt pinning the whole manifest, its revision,
        # the decision and each evidence hash; a receipt is not a second approval.
        canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
        receipts['receipts'][asset] = {
            'manifest_sha256': hashlib.sha256(canonical).hexdigest(),
            'reviewed_revision': rev,
            'decision_id': DECISION,
            'evidence_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                                for path in approval_evidence},
        }

        for path in (ROOT / 'art' / 'blender' / f'syndicate_{stem}.blend', target, manifest_path):
            hashes[rel(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        print('REGISTERED', binding, asset, payload['triangle_count'], rev[:16])

    registry_path.write_text(json.dumps(registry, indent=2) + '\n', encoding='utf-8')
    receipts['receipts'] = dict(sorted(receipts['receipts'].items()))
    receipts_path.write_text(json.dumps(receipts, indent=2) + '\n', encoding='utf-8')

    pipeline_path = ROOT / 'art' / 'manifests' / 'pipeline.json'
    pipeline = json.loads(pipeline_path.read_text(encoding='utf-8'))
    pipeline['batches'][BATCH] = sorted(registered)
    pipeline_path.write_text(json.dumps(pipeline, indent=2) + '\n', encoding='utf-8')

    for name in ('syndicate_imperium_geometry.py', 'syndicate_imperium_designs.py',
                 'build_syndicate_imperium.py', 'register_syndicate_prototypes.py'):
        path = ROOT / 'tools' / 'art' / name
        hashes[rel(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    HASHES.write_text(json.dumps(dict(sorted(hashes.items())), indent=2) + '\n', encoding='utf-8')
    print('REGISTER_OK', len(registered), 'hashes', len(hashes))


if __name__ == '__main__':
    main()
