#!/usr/bin/env python3
"""Read-only coverage reconciliation; never registers assets or changes approvals.

The S01 inventory is historical. Join its identities to current ship data,
revision records and registry, not its old status or sidecar canonical labels.
Shared trade-convoy rows are candidates, not proven integrated coverage.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = 'art/manifests/reviews/S06-COVERAGE-RECONCILIATION.json'
TEXTURES = {'agricultural', 'barren', 'gas_giant', 'industrial', 'military',
            'research', 'temperate', 'trade', 'star', 'nebula'}
EFFECTS = {'deep_space_sky_dome', 'jump_point'}


def build_report(root):
    inputs = {}

    def load(relative):
        raw = (root / relative).read_bytes()
        inputs[relative] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    inventory = load('art/manifests/model_inventory.json')
    approvals = load('art/manifests/approvals.json')
    policy = load('art/manifests/pipeline_policy.json')
    registry = {r['binding']: r for r in load('assets/models/registry.json')['bindings']}
    pipeline = load('art/manifests/pipeline.json')
    policy_ids = {d['id'] for d in policy['decision_log']}
    assert 's06-b5-scope-2026-10-17' in policy_ids
    errors = []
    assets = {}
    decisions = [d for d in approvals['decision_log']
                 if d.get('approval_kind') in ('appearance-batch-revisions', 'appearance-scaffold-revision')]

    def add(asset, decision_id, pending):
        binding = asset['gameplay_binding'] if pending else asset['shape_key']
        if binding in assets:
            errors.append('duplicate approved binding: ' + binding)
        meshes = {p: h for p, h in asset['runtime'].items() if p.endswith('.mesh.json')}
        if len(meshes) != 1:
            raise ValueError('expected one runtime mesh for ' + binding)
        mesh, digest = next(iter(meshes.items()))
        # Trio legacy exporter metadata is historical; only its current source and
        # runtime are checked here. The existing pipeline validator owns its tooling.
        groups = ('source', 'exporter', 'runtime') if pending else ('source', 'runtime')
        for group in groups:
            for path, expected in asset[group].items():
                file = root / path
                actual = hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None
                inputs[path] = actual
                if actual != expected:
                    errors.append(f'{decision_id}: {group} hash mismatch: {path}')
        assets[binding] = {'approval_id': decision_id, 'mesh': mesh, 'sha256': digest,
                           'pending_registration': pending}

    for asset in approvals['approved_assets']:
        add(asset, asset['approval_id'], False)
    for decision in decisions:
        for asset in decision['revision']['assets']:
            add(asset, decision['id'], True)

    pending_assets = {}
    for sheet_path in sorted((root / 'art/manifests/pending').glob('S06-BATCH-*.json')):
        sheet = load(sheet_path.relative_to(root).as_posix())
        for candidate in sheet['assets']:
            status = candidate.get('status', sheet['status'])
            if status != 'pending_owner_appearance_approval':
                continue
            binding = candidate['binding']
            if binding in assets or binding in pending_assets:
                errors.append('duplicate pending binding: ' + binding)
            mesh = candidate['mesh']
            source = f"art/blender/{candidate['identifier']}.blend"
            for path in (mesh, source):
                file = root / path
                if not file.is_file():
                    errors.append('pending asset missing: ' + path)
                inputs[path] = hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None
            pending_assets[binding] = {'approval_id': None, 'mesh': mesh,
                                       'sha256': inputs[mesh], 'pending_registration': True,
                                       'batch': sheet['batch']}

    ships = {}
    for relative in sorted((root / 'assets/data/ships').glob('*.json')):
        for data_id, data in load(relative.relative_to(root).as_posix()).get('ships', {}).items():
            identity = (data['faction'], data_id.split('_', 1)[1])
            if identity in ships:
                raise ValueError('duplicate ship identity: ' + repr(identity))
            ships[identity] = (data_id, data)

    def binding_for(row):
        canonical = row['canonical_binding']
        parts = canonical.split(':')
        if parts[0] == 'ship':
            _, faction, suffix = parts
            if suffix == 'trade_convoy':
                return faction + ':convoy', 'trade-convoy alias; real resolver/scale test still required'
            data_id, data = ships[(faction, suffix)]
            role = data['category']
            if role == 'fighter_squadron':
                role = 'bomber' if ('bomber' in data_id or data_id == 'rebel_y_squadron') else 'fighter'
            elif role == 'construction':
                role = 'colonizer' if data_id.endswith('_colonizer') else 'constructor'
            elif role == 'crew_transport' and data.get('crew_capacity', 0) > 0:
                role = 'convoy'
            return faction + ':' + role, 'current ship-data role; not the historical legacy shape'
        if parts[0] == 'station' or parts[0] == 'hardware':
            return ':'.join(parts[-2:]), 'station/hardware binding uses owner faction and kind'
        if canonical == 'construction:site:scaffold':
            return 'shared:construction_scaffold', 'shared construction scaffold'
        if canonical == 'menu:cinematic:backdrop':
            return 'menu:cinematic_backdrop', 'baked menu movie, not mesh data'
        if parts[0] == 'environment':
            return canonical, 'environment binding'
        raise ValueError('unclassified identity: ' + canonical)

    rows = []
    seen = set()
    for row in inventory['rows']:
        canonical = row['canonical_binding']
        if canonical in seen:
            raise ValueError('duplicate inventory identity: ' + canonical)
        seen.add(canonical)
        binding, mapping = binding_for(row)
        asset = assets.get(binding)
        reg = registry.get(binding)
        if asset:
            disposition = ('approved_shared_candidate' if canonical.endswith(':trade_convoy')
                           else 'approved_asset')
            scope_policy = None
        elif binding in pending_assets:
            asset = pending_assets[binding]
            disposition = 'pending_appearance'
            scope_policy = 's06-catalogue-completion-execution-2026-10-18'
        elif canonical.startswith('environment:') and canonical.split(':')[1] in TEXTURES:
            disposition = 'deferred_texture_pipeline'
            scope_policy = 's06-b5-scope-2026-10-17'
        elif (canonical.startswith('environment:') and canonical.split(':')[1] in EFFECTS
              or canonical == 'menu:cinematic:backdrop'):
            disposition = 'outside_mesh_catalogue'
            scope_policy = 's06-b5-scope-2026-10-17'
        else:
            disposition = 'missing_mesh'
            scope_policy = None
        rows.append({'canonical_binding': canonical, 'category': row['category'],
                     'faction': row['faction'], 'runtime_binding': binding,
                     'mapping_basis': mapping, 'disposition': disposition,
                     'asset': asset, 'scope_policy': scope_policy,
                     'registry_status': reg['status'] if reg else None,
                     'runtime_integration_proven': False})

    planned = []
    for item in inventory['planned_hulls']['hulls']:
        binding = item['mesh_key']
        faction, role = binding.split(':')
        present = [(key, data) for key, data in ships.values()
                   if data['faction'] == faction and
                   (data['category'] == role or role == 'bomber' and 'bomber' in key)]
        planned.append({'runtime_binding': binding, 'production_site': item['production_site'],
                        'data_ids_present': [key for key, _ in present],
                        'approved_asset': assets.get(binding),
                        'status': 'remaining_data_and_model_work' if not present else 'recheck_required',
                        'decision_id': inventory['planned_hulls']['decision_id']})
    count = Counter(r['disposition'] for r in rows)
    category_counts = {}
    for category in sorted({r['category'] for r in rows}):
        category_counts[category] = dict(sorted(Counter(r['disposition'] for r in rows
                                                       if r['category'] == category).items()))
    return {
        'schema': 's06-coverage-reconciliation/v1',
        'historical_inventory_base': inventory['base_commit'],
        'provenance': 'Content-addressed inputs, not live HEAD. Historical inventory left unchanged.',
        'limits': ['Identity/file/hash audit only; no new appearance approval, registration or activation.',
                   'Shared candidates are not final approved integration: both convoy paths need proof.',
                   'runtime_integration_proven=false means not established by this report, including the trio.',
                   'Trio source/runtime checked; historical trio exporter pins belong to pipeline validation.',
                   'Deferred textures stay on their existing pipeline; they are not authored meshes.'],
        'counts': {'inventory_rows': len(rows), 'unique_approved_assets': len(assets),
                   'appearance_batch_decisions': sum(d['approval_kind'] == 'appearance-batch-revisions' for d in decisions),
                   'appearance_batch_specimens': sum(len(d['revision']['assets']) for d in decisions
                                                     if d['approval_kind'] == 'appearance-batch-revisions'),
                   'scaffold_appearance_specimens': sum(len(d['revision']['assets']) for d in decisions
                                                        if d['approval_kind'] == 'appearance-scaffold-revision'),
                   'pipeline_assets': len(pipeline['assets']),
                   'registry_bindings': len(registry),
                   'dispositions': dict(sorted(count.items())), 'by_category': category_counts},
        's06_catalogue_complete': count['missing_mesh'] == 0 and count['pending_appearance'] == 0 and all(
            p['approved_asset'] and p['data_ids_present'] for p in planned),
        'rows': rows, 'planned_hulls_outside_inventory': planned,
        'integrity_errors': errors, 'input_sha256': dict(sorted(inputs.items()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--check', action='store_true', help='refuse report drift; write nothing')
    args = parser.parse_args()
    report = build_report(args.root)
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    destination = args.root / OUTPUT
    if report['integrity_errors']:
        print('\n'.join(report['integrity_errors']), file=sys.stderr)
        return 1
    if args.check:
        if not destination.is_file() or destination.read_text(encoding='utf-8') != rendered:
            print('STALE: ' + OUTPUT, file=sys.stderr)
            return 1
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding='utf-8', newline='\n')
    print(json.dumps(report['counts'], sort_keys=True))
    print('CHECK_OK' if args.check else 'REPORT_WRITTEN')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
