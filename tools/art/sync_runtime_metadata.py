#!/usr/bin/env python3
"""Publish/check runtime-only metadata; never rebuild or modify approved meshes.

Source contract/examples and the S01 inventory remain authoritative. The runtime
registry deduplicates crew-transport/trade-convoy bindings sharing today's mesh;
the separate catalogue map preserves every inventory identity without claiming
that a future authored reuse has received appearance approval.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def binding_for(row):
    key = row['canonical_binding']
    parts = key.split(':')
    if parts[0] == 'ship':
        faction, kind = parts[1:]
        shape = row['geometry_shape_string']
        if ':' in shape:
            return shape
        if kind in ('crew_transport', 'trade_convoy'):
            kind = 'convoy'
        elif 'bomber' in kind:
            kind = 'bomber'
        elif 'squadron' in kind:
            kind = 'fighter'
        return f'{faction}:{kind}'
    if parts[0] == 'station':
        return ':'.join(parts[-2:])
    if parts[0] == 'hardware':
        return ':'.join(parts[-2:])
    if key == 'construction:site:scaffold':
        return 'shared:construction_scaffold'
    if key == 'menu:cinematic:backdrop':
        return 'menu:cinematic_backdrop'
    if parts[0] == 'environment':
        return key
    raise ValueError(f'Inventory identity has no explicit runtime mapping: {key}')


def outputs(root):
    def load(relative):
        return json.loads((root / relative).read_text(encoding='utf-8'))
    inventory = load('art/manifests/model_inventory.json')
    registry = load('art/schemas/examples/core-registry.json')
    rows = {row['binding']: row for row in registry['bindings']}
    mapping, legacy_shapes = {}, {}
    variants = defaultdict(list)
    for row in inventory['rows']:
        binding = binding_for(row)
        mapping[row['canonical_binding']] = binding
        variants[binding].append(row['canonical_binding'])
        faction, kind = binding.split(':')
        if row['category'] in ('combat_hull', 'squadron', 'logistics_hull', 'construction') and row.get('geometry_shape_string'):
            shape = row['geometry_shape_string']
            if binding in legacy_shapes and legacy_shapes[binding] != shape:
                raise ValueError(f'Conflicting legacy shapes for {binding}')
            legacy_shapes[binding] = shape
        if binding in rows:
            continue
        status = row['status']
        if status == 'in_scope_authoring_pending':
            status = 'authoring_pending'
        if status not in ('procedural_legacy', 'authoring_pending', 'keep_procedural_proposed', 'out_of_scope'):
            raise ValueError(f'Unexpected unapproved status for {binding}: {status}')
        identity = {'faction': faction, 'class_or_kind': kind}
        if row['category'] in ('station', 'satellite', 'planet_installation'):
            identity['station_faction'] = faction
        rows[binding] = {'binding': binding, 'category': row['category'], 'identity': identity,
                         'manifest': f'core:{faction}/{kind}', 'status': status}
    for planned in inventory['planned_hulls']['hulls']:
        binding = planned['mesh_key']
        if binding not in rows:
            faction, kind = binding.split(':')
            rows[binding] = {'binding': binding, 'category': 'squadron' if kind == 'bomber' else 'combat_hull',
                             'identity': {'faction': faction, 'class_or_kind': kind},
                             'manifest': f'core:{faction}/{kind}', 'status': 'authoring_pending',
                             'notes': 'Planned hull; no gameplay entity or appearance approval is created here.'}
    registry['bindings'] = [rows[key] for key in sorted(rows)]
    result = {'assets/models/registry.json': encoded(registry),
              'assets/models/catalogue-map.json': encoded({
                  'contract': 'star-armada/catalogue-map', 'contract_major': 1,
                  'inventory_bindings': dict(sorted(mapping.items())),
                  'legacy_ship_shapes': dict(sorted(legacy_shapes.items())),
                  'shared_runtime_bindings': {key: value for key, value in sorted(variants.items()) if len(value) > 1}})}
    receipts = {}
    for path in sorted((root / 'art/schemas').glob('*.schema.json')):
        result[f'assets/models/schemas/{path.name}'] = path.read_bytes()
    for path in sorted((root / 'art/schemas/examples/manifests').glob('*.json')):
        manifest = json.loads(path.read_text(encoding='utf-8'))
        result[f'assets/models/manifests/{path.name}'] = path.read_bytes()
        approval = manifest.get('approval', {})
        if approval.get('status') == 'approved':
            canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
            receipts[manifest['asset']] = {
                'manifest_sha256': hashlib.sha256(canonical).hexdigest(),
                'reviewed_revision': manifest['revision'], 'decision_id': approval['decision_id'],
                'evidence_sha256': {relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
                                    for relative in approval['reviewed_evidence']}}
    result['assets/models/approval-receipts.json'] = encoded({
        'contract': 'star-armada/approval-receipts', 'contract_major': 1,
        'purpose': 'Build-time evidence attestation, not a signature or a new owner approval.',
        'receipts': receipts})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    args = parser.parse_args()
    expected = outputs(ROOT)
    drift = [path for path, data in expected.items()
             if not (ROOT / path).is_file() or (ROOT / path).read_bytes() != data]
    if args.write:
        for path in drift:
            target = ROOT / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(expected[path])
        print(f'Published {len(expected)} metadata files; {len(drift)} updated; no mesh writes')
        return 0
    if drift:
        print('Runtime metadata drift: ' + ', '.join(drift))
        return 1
    print(f'Runtime metadata satisfied: {len(expected)} files; no mesh writes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
