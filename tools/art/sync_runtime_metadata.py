#!/usr/bin/env python3
"""Publish/check registration metadata; never rebuild or modify approved meshes.

The source contract examples preserve the trio. Original enumerated S06 revision
approvals, sidecars, capture reports and current ship data drive the bounded
99-row increment. Runtime assets ship without build tools or source evidence;
receipts attest the validated original evidence relationship at publication.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def binding_for(row, ships=None):
    key = row['canonical_binding']
    parts = key.split(':')
    if parts[0] == 'ship':
        faction, kind = parts[1:]
        if ships is not None and kind != 'trade_convoy':
            data_id, data = ships[(faction, kind)]
            role = data['category']
            if role == 'fighter_squadron':
                role = 'bomber' if 'bomber' in data_id or data_id == 'rebel_y_squadron' else 'fighter'
            elif role == 'construction':
                role = 'colonizer' if data_id.endswith('_colonizer') else 'constructor'
            elif role == 'crew_transport' and data.get('crew_capacity', 0) > 0:
                role = 'convoy'
            return f'{faction}:{role}'
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


def outputs(root, *, include_scaffold=False):
    def load(relative):
        return json.loads((root / relative).read_text(encoding='utf-8'))
    inventory = load('art/manifests/model_inventory.json')
    ships = {}
    for path in sorted((root / 'assets/data/ships').glob('*.json')):
        for data_id, data in json.loads(path.read_bytes()).get('ships', {}).items():
            identity = (data['faction'], data_id.split('_', 1)[-1])
            if identity in ships:
                raise ValueError('duplicate current ship identity: ' + str(identity))
            ships[identity] = (data_id, data)
    registry = load('art/schemas/examples/core-registry.json')
    rows = {row['binding']: row for row in registry['bindings']}
    mapping, legacy_shapes = {}, {}
    variants = defaultdict(list)
    for row in inventory['rows']:
        binding = binding_for(row, ships)
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
    try:
        from .s07_registration import publish, publish_scaffold
    except ImportError:
        from s07_registration import publish, publish_scaffold
    categories = {mapping[row['canonical_binding']]: row['category'] for row in inventory['rows']}
    registered, new_receipts = publish(root, rows, mapping, categories)
    # Initial opt-in is explicit; an already published separate batch must not
    # disappear when ordinary regeneration/CI invokes the historical command.
    pipeline = json.loads(registered['art/manifests/pipeline.json'])
    if 'approved-s07-scaffold' in pipeline['batches']:
        if pipeline['batches']['approved-s07-scaffold'] != ['shared:construction_scaffold']:
            raise ValueError('invalid separate scaffold registration batch')
        include_scaffold = True
    if include_scaffold:
        scaffold, scaffold_receipts = publish_scaffold(
            root, rows, mapping, categories, pipeline=pipeline)
        registered.update(scaffold)
        new_receipts.update(scaffold_receipts)
    result.update(registered)
    result['assets/models/registry.json'] = encoded(registry)
    receipts.update(new_receipts)
    result['assets/models/approval-receipts.json'] = encoded({
        'contract': 'star-armada/approval-receipts', 'contract_major': 1,
        'purpose': 'Build-time evidence attestation, not a signature or a new owner approval.',
        'receipts': receipts})
    return result


def output_destinations(root, expected):
    """Preflight the whole set, including unchanged files, before any writes.

    Reject symlink components rather than following aliases, even within root.
    The publisher assumes an exclusively owned tree (not hostile concurrent edits).
    """
    import re
    root = Path(root).resolve()
    destinations, names, inodes = {}, set(), set()
    for relative in expected:
        if (not isinstance(relative, str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,240}', relative)
                or any(part in ('', '.', '..') for part in relative.split('/'))):
            raise ValueError('unsafe metadata output path: ' + str(relative))
        name = relative.casefold()
        if name in names:
            raise ValueError('conflicting metadata output alias: ' + relative)
        names.add(name)
        target = root / relative
        for component in (*reversed(target.parents), target):
            if component == root or not component.is_relative_to(root):
                continue
            if component.is_symlink():
                raise ValueError('unsafe metadata output symlink: ' + relative)
            if component.exists() and not (component.is_file() if component == target else component.is_dir()):
                raise ValueError('unsafe metadata output type: ' + relative)
        if not target.resolve().is_relative_to(root):
            raise ValueError('unsafe metadata output escape: ' + relative)
        if target.exists():
            info = target.stat()
            inode = (info.st_dev, info.st_ino)
            if inode in inodes:
                raise ValueError('conflicting metadata output inode: ' + relative)
            inodes.add(inode)
        destinations[relative] = target
    for name in names:
        if any(parent.as_posix() in names for parent in Path(name).parents if parent != Path('.')):
            raise ValueError('conflicting metadata output parent: ' + name)
    return destinations


def publish_outputs(destinations, expected, drift):
    """Stage all bytes, then replace per file; roll back ordinary IO failures.

    This is not a crash-consistent multi-file transaction or a concurrent-writer
    sandbox. A rollback IO failure is surfaced and its backup files are retained.
    """
    import os
    import tempfile
    staged, backups, temporary, created, published = {}, {}, set(), [], []

    def stage(target, data, mode):
        fd, name = tempfile.mkstemp(prefix='.s07-metadata-', dir=target.parent)
        os.close(fd)
        path = Path(name)
        temporary.add(path)
        path.write_bytes(data)
        path.chmod(mode)
        return path

    try:
        for relative in drift:
            target = destinations[relative]
            missing = []
            parent = target.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir()
                created.append(directory)
            mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
            backups[relative] = stage(target, target.read_bytes(), mode) if target.exists() else None
            staged[relative] = stage(target, expected[relative], mode)
        for relative in drift:
            os.replace(staged[relative], destinations[relative])
            published.append(relative)
    except BaseException:
        try:
            for relative in reversed(published):
                if backups[relative] is None:
                    destinations[relative].unlink()
                else:
                    os.replace(backups[relative], destinations[relative])
        except OSError:
            temporary.difference_update(p for p in backups.values() if p is not None)
            raise
        raise
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)
        for directory in reversed(created):
            # Successful publication leaves nonempty directories in place.
            if not any(directory.iterdir()):
                directory.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    parser.add_argument('--include-scaffold', action='store_true',
                        help='Explicit separate increment for the approved S07 scaffold; not default activation')
    args = parser.parse_args()
    expected = outputs(ROOT, include_scaffold=True) if args.include_scaffold else outputs(ROOT)
    destinations = output_destinations(ROOT, expected)
    drift = [path for path, data in expected.items()
             if not destinations[path].is_file() or destinations[path].read_bytes() != data]
    if args.write:
        publish_outputs(destinations, expected, drift)
        print(f'Published {len(expected)} metadata files; {len(drift)} updated; no mesh writes')
        return 0
    if drift:
        print('Runtime metadata drift: ' + ', '.join(drift))
        return 1
    print(f'Runtime metadata satisfied: {len(expected)} files; no mesh writes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
