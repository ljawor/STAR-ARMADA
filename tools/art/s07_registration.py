"""Deterministic registration of enumerated S06 approvals; no authoring writes.

Sidecars describe build inputs, decisions confer approval, and original capture
reports tie that approval to runtime bytes. None substitutes for either other.
"""
import hashlib
import json
from pathlib import Path
import re
import shlex

HASHES = 'art/manifests/approved-s06-source-hashes.json'


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_file(root, relative):
    if (not isinstance(relative, str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,180}', relative)
            or any(part in ('', '.', '..') for part in relative.split('/'))):
        raise ValueError('unsafe registration path: ' + str(relative))
    target = root / relative
    if not target.resolve().is_relative_to(root.resolve()) or not target.is_file():
        raise ValueError('missing/unsafe registration file: ' + relative)
    return target


def load(root, relative):
    return json.loads(safe_file(root, relative).read_bytes())


def pin(root, relative, expected):
    if digest(safe_file(root, relative).read_bytes()) != expected:
        raise ValueError('approved pin mismatch: ' + relative)


def evidence_for(root, decision, asset, sidecar, sheet):
    """Validate the original capture relationship, not arbitrary newly hashed files."""
    binding = asset['gameplay_binding']
    mesh_path, mesh_sha = next((p, h) for p, h in asset['runtime'].items() if p.endswith('.mesh.json'))
    record = asset.get('evidence') or decision['revision'].get('evidence')
    paths = set()
    if isinstance(record, dict):
        directory = record['dir']
        image = record['sheet']
        image = image if image.startswith('artifacts/') else directory + '/' + image
        paths.add(image)
        for relative, expected in record.get('sha256', {}).items():
            pin(root, relative, expected)
            paths.add(relative)
        if record.get('close'):
            paths.add(record['close'])
    else:
        image = sidecar.get('evidence')
        if sheet:
            approved_image = sheet.get('evidence', {}).get(binding, {}).get('sheet')
            if approved_image and approved_image != image:
                raise ValueError('evidence sheet relationship mismatch: ' + binding)
        if not image:
            raise ValueError('missing original evidence: ' + binding)
        if sheet is None and Path(image).name != 'review-sheet.png':
            raise ValueError('original standalone review-sheet evidence required: ' + binding)
        directory = str(Path(image).parent)
        paths.add(image)
    # All existing review families use a report or metrics sibling of the sheet.
    report_path = directory + ('/report.json' if (root / directory / 'report.json').is_file()
                               else '/metrics.json')
    report = load(root, report_path)
    paths.add(report_path)
    captured_sheet = report.get('sheet')
    if isinstance(captured_sheet, dict) and captured_sheet.get('image'):
        # Some approval prose shortened a squadron filename. The capture's own
        # pinned sheet is authoritative, within the decision's exact directory.
        captured_image = directory + '/' + captured_sheet['image']
        pin(root, captured_image, captured_sheet['sha256'])
        if captured_sheet.get('runtime_key', binding) != binding:
            raise ValueError('capture sheet binding mismatch: ' + binding)
        paths.discard(image)
        paths.add(captured_image)
    mesh = report.get('authored') or report.get('mesh', {})
    if isinstance(mesh, dict) and binding in mesh:
        mesh = mesh[binding]
    if isinstance(mesh, dict) and mesh.get('sha256'):
        if mesh['sha256'] != mesh_sha:
            raise ValueError('original evidence/runtime mismatch: ' + binding)
        if mesh.get('path', mesh_path) != mesh_path:
            raise ValueError('original evidence mesh path mismatch: ' + binding)
    elif binding == 'environment:asteroid_field':
        # B5 predates mesh-hash capture reports. Its owner decision explicitly
        # binds the v4 directory, row, exact source/export/runtime pins and deltas.
        # Do not invent a hash-bearing capture or claim a fresh export here.
        if (report.get('row') != binding or report.get('batch') != decision['revision']['batch']
                or record != decision['revision'].get('evidence')):
            raise ValueError('original B5 evidence relationship mismatch')
        measured = record['measured']
        comparison = report.get('comparison', {})
        if (comparison.get('close', {}).get('changed_percent') != measured['close_changed_percent']
                or comparison.get('wide', {}).get('changed_percent') != measured['wide_changed_percent']
                or any(v.get('repeat_changed_pixels') != measured['repeat_changed_pixels']
                       for v in comparison.values())):
            raise ValueError('original B5 evidence measurements mismatch')
    else:
        raise ValueError('original evidence lacks approved mesh hash: ' + binding)
    for relative in paths:
        safe_file(root, relative)
    return sorted(paths)


def publish(root, registry_rows, mapping, categories):
    """Return generated source/runtime metadata; mutate only in-memory registry rows."""
    root = Path(root)
    policy = load(root, 'art/manifests/pipeline_policy.json')
    authorities = [d for d in policy['decision_log']
                   if d['id'] == 's07-opt-in-continuation-2026-10-18'
                   and d.get('decision') == 'authorized-execution-not-appearance']
    if len(authorities) != 1:
        raise ValueError('S07 registration requires explicit opt-in execution authority')
    approvals = load(root, 'art/manifests/approvals.json')
    decisions = [d for d in approvals['decision_log']
                 if d.get('approval_kind') == 'appearance-batch-revisions']
    specimens = [(d, a) for d in decisions for a in d['revision']['assets']]
    if len(specimens) != 99 or len({a['gameplay_binding'] for _, a in specimens}) != 99:
        raise ValueError('expected exactly 99 unique S06 approved specimens')
    identifiers = {p.stem.casefold() for p in (root / 'art/schemas/examples/manifests').glob('*.json')}
    for _, asset in specimens:
        identifier = asset.get('identifier')
        if (not isinstance(identifier, str)
                or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,127}', identifier)):
            raise ValueError('unsafe asset identifier: ' + str(identifier))
        if identifier in identifiers:
            raise ValueError('conflicting manifest identifier: ' + identifier)
        identifiers.add(identifier)
    sidecars, sheets = {}, {}
    for path in sorted((root / 'art/manifests/pending').glob('S06-*.json')):
        data = json.loads(path.read_bytes())
        if 'assets' in data:
            for asset in data['assets']:
                sheets[asset['binding']] = data
        elif isinstance(data.get('runtime'), dict):
            mesh = data['runtime']['path']
            if mesh in sidecars:
                raise ValueError('duplicate sidecar: ' + mesh)
            sidecars[mesh] = data
    result, receipts, hashes, entries = {}, {}, {}, []
    for decision, asset in sorted(specimens, key=lambda pair: pair[1]['gameplay_binding']):
        binding = asset['gameplay_binding']
        if binding not in categories or decision.get('decision') != 'approved':
            raise ValueError('approved binding not in current inventory: ' + binding)
        for group in ('source', 'exporter', 'runtime'):
            for relative, expected in asset[group].items():
                pin(root, relative, expected)
                if relative in hashes and hashes[relative] != expected:
                    raise ValueError('conflicting approved pin: ' + relative)
                hashes[relative] = expected
        runtime = [p for p in asset['runtime'] if p.endswith('.mesh.json')]
        if len(runtime) != 1:
            raise ValueError('expected one mesh: ' + binding)
        runtime = runtime[0]
        sidecar = sidecars[runtime]
        if sidecar.get('appearance_decision') != decision['id']:
            raise ValueError('sidecar approval mismatch: ' + binding)
        for group, approved in [('source', 'source'), ('initial_seed', 'exporter'),
                                ('export_script', 'exporter'), ('runtime', 'runtime')]:
            record = sidecar[group]
            if asset[approved].get(record['path']) != record['sha256']:
                raise ValueError('sidecar approved pin mismatch: ' + record['path'])
        authority = asset['source_authority'].split('-', 1)[0]
        if sidecar['authority'] != authority:
            raise ValueError('sidecar authority mismatch: ' + binding)
        sheet = sheets.get(binding)
        if sheet and sheet.get('appearance_decision') != decision['id']:
            raise ValueError('batch approval mismatch: ' + binding)
        build_args = shlex.split(sidecar['initial_seed'].get('selects') or '')
        if sheet:
            specimen = next(a for a in sheet['assets'] if a['binding'] == binding)
            expected_args = shlex.split(specimen.get('seed_arg') or '')
            if build_args != expected_args or '--replace-seed' in build_args:
                raise ValueError('original seed selector mismatch: ' + binding)
        elif build_args:
            raise ValueError('unbound seed selector: ' + binding)
        evidence = evidence_for(root, decision, asset, sidecar, sheet)
        raw = safe_file(root, runtime).read_bytes()
        payload = json.loads(raw)
        faction, kind = binding.split(':')
        owner = 'alliance' if faction == 'rebel' else faction
        asset_id = f'core:{owner}/{kind}'
        sha = asset['runtime'][runtime]
        revision = digest((asset_id + '\nmesh:' + sha).encode())
        bounds = dict(zip(('min', 'max'), payload['bounds']))
        manifest = {
            'contract': 'star-armada/model-manifest', 'contract_major': 1,
            'asset': asset_id, 'revision': revision,
            'display_name': asset['identifier'].replace('_', ' ') + ' (approved)',
            'files': {'mesh': {'path': runtime, 'sha256': sha, 'bytes': len(raw)}},
            'export': {'contract': 'star-armada/mesh-export', 'contract_major': 1, 'legacy_schema_int': 1},
            'coordinates': 'X beam; Y up; +Z forward', 'pivot': [0, 0, 0],
            'bounds': bounds, 'nominal_scale': 1.0, 'roles': sorted(payload['batches']),
            'provenance': {'author': 'Lukasz Jawor', 'tool': 'Blender',
                           'tool_version': sidecar.get('authoring', 'Blender evaluated bevel mesh'),
                           'license': 'original', 'source': sidecar['source']['path'],
                           'notes': 'Registered from original S06 revision approval. No rebuild or fresh export is attested.'},
            'requires': {'min_engine': '0.15.1', 'material_profile': 'core:fleet/standard'},
            'budgets': {'triangles': payload['triangle_count'], 'draw_calls': len(payload['batches']), 'texture_bytes': 0},
            'approval': {'status': 'approved', 'decision_id': decision['id'], 'decided_by': 'owner',
                         'decided_on': decision['date'], 'reviewed_revision': revision,
                         'reviewed_evidence': evidence}}
        result[f"assets/models/manifests/{asset['identifier']}.json"] = encoded(manifest)
        receipts[asset_id] = {'manifest_sha256': digest(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()),
                              'reviewed_revision': revision, 'decision_id': decision['id'],
                              'evidence_sha256': {p: digest(safe_file(root, p).read_bytes()) for p in evidence}}
        row = registry_rows[binding]
        identity = {'faction': faction, 'class_or_kind': kind}
        if categories[binding] in ('station', 'satellite', 'planet_installation'):
            identity['station_faction'] = faction
        row.update(category=categories[binding], identity=identity,
                   manifest=asset_id, status='core', legacy_identifiers=[payload['asset']],
                   envelope=bounds, envelope_decision=decision['id'])
        row.pop('notes', None)
        entries.append({'binding': binding, 'asset_id': asset_id,
                        'gameplay_entity': sidecar.get('gameplay_entity'), 'authority': authority,
                        'source': sidecar['source']['path'], 'exporter': sidecar['initial_seed']['path'],
                        'export_script': sidecar['export_script']['path'],
                        'build_args': build_args,
                        'export_args': [], 'runtime': runtime, 'expected_hashes': HASHES,
                        'expected_triangles': payload['triangle_count'],
                        'advisory_budget_triangles': 11888, 'category': categories[binding],
                        'roles': sorted(payload['batches']), 'coordinates': 'X beam; Y up; +Z forward; nominal game model units',
                        'approval': {'decision_id': decision['id'], 'record': 'art/manifests/approvals.json'}})
    pipeline = load(root, 'art/manifests/pipeline.json')
    registered = {e['binding'] for e in entries}
    pipeline['assets'] = [e for e in pipeline['assets'] if e['binding'] not in registered] + entries
    pipeline['batches']['approved-s06'] = sorted(registered)
    result['art/manifests/pipeline.json'] = encoded(pipeline)
    result[HASHES] = encoded(dict(sorted(hashes.items())))
    return result, receipts
