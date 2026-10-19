#!/usr/bin/env python3
"""Derive data-only S08 packs without Blender or changes to approved inputs.

Run from any directory; --check verifies committed examples without writing.
Only examples/visual_packs/ and artifacts/s08/examples/source-pins.json are outputs.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROLE_MAP = {'trim': 'accent', 'accent': 'trim'}
PACKS = (
    ('core-frigate', 'example:core_frigate', 'example:alliance/frigate', 'rebel:frigate', 'frigate'),
    ('raider-addon', 'example:raider_addon', 'example:raiders/scout', 'raiders:scout', 'scout'),
)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def outputs():
    source_path = ROOT / 'assets/models/alliance_frigate.mesh.json'
    original = json.loads(source_path.read_text())
    source_manifest = json.loads((ROOT / 'assets/models/manifests/alliance_frigate.json').read_text())
    pins = {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in (
        'art/blender/alliance_frigate.blend',
        'assets/models/alliance_frigate.mesh.json',
        'assets/models/manifests/alliance_frigate.json',
        'art/manifests/provenance/rebel-frigate.json',
        'tools/art/build_alliance_frigate.py',
    )}
    result = {}
    derived = []
    for folder, pack_id, asset, binding, name in PACKS:
        base = Path('examples/visual_packs') / folder
        payload = deepcopy(original)
        payload.pop('schema')
        payload.update(contract='star-armada/mesh-export', contract_major=1, asset=asset,
                       authoring='Derived evaluated Blender mesh; Python trim/accent role swap v1')
        payload['batches'] = {ROLE_MAP.get(role, role): rows for role, rows in original['batches'].items()}
        for part in payload.get('parts', []):
            part['role'] = ROLE_MAP.get(part['role'], part['role'])
        mesh_bytes = encoded(payload)
        digest = hashlib.sha256(mesh_bytes).hexdigest()
        mesh_rel = f'assets/models/{name}.mesh.json'
        manifest_rel = f'assets/models/manifests/{name}.json'
        manifest = deepcopy(source_manifest)
        manifest.pop('approval', None)
        manifest['export'].pop('legacy_schema_int', None)
        manifest.update(asset=asset, display_name=f'S08 {name} role-remap example (unapproved)',
                        revision=hashlib.sha256((asset + '\nmesh:' + digest).encode()).hexdigest())
        manifest['files'] = {'mesh': {'path': mesh_rel, 'sha256': digest, 'bytes': len(mesh_bytes)}}
        manifest['provenance'] = {
            'author': 'Lukasz Jawor (source); S08 example derivation',
            'tool': 'Python JSON role remap', 'tool_version': '1', 'license': 'original',
            'notes': 'Derived from evaluated assets/models/alliance_frigate.mesh.json using tools/art/build_s08_examples.py. Geometry unchanged; trim/accent roles exchanged. SOURCE.md records original Blender source and hashes. No inherited or new appearance approval.',
        }
        entry = {'binding': binding, 'manifest': manifest_rel}
        requires = {'min_engine': '0.15.1', 'contracts': ['star-armada/model-manifest/v1']}
        if folder == 'raider-addon':
            entry['entity_source'] = 'gameplay:s08_raiders_fixture'
            requires['gameplay_mod'] = entry['entity_source']
            content = {'adds': [entry]}
        else:
            entry['replace_of'] = source_manifest['asset']
            content = {'replaces': [entry]}
        pack = {'contract': 'star-armada/visual-pack', 'contract_major': 1, 'id': pack_id,
                'version': '1.0.0', 'requires': requires, 'content': content,
                'notes': 'Data-only evaluated frigate derivation; role swap only. No appearance approval.'}
        result[base / mesh_rel] = mesh_bytes
        result[base / manifest_rel] = encoded(manifest)
        result[base / 'visual-pack.json'] = encoded(pack)
        source_doc = ('# S08 derived fixture provenance\n\n'
                      'Original design: Lukasz Jawor; licence declaration: original (as in source manifest).\n'
                      'Derived using `tools/art/build_s08_examples.py` v1; no Blender was run.\n'
                      'The input is the evaluated Blender 5.0.1 bevel export recorded in '
                      '`art/manifests/provenance/rebel-frigate.json`, not reconstructed geometry.\n'
                      'Only identity/contract metadata and the trim/accent material-role bijection change; '
                      'vertices, normals, indices, bounds and triangle count remain unchanged.\n'
                      'The original approval applies only to the original revision. This derived '
                      'fixture has no owner appearance approval and does not claim one.\n'
                      'The original .blend and export remain in the repository, not in this pack.\n\n'
                      '## Read-only repository inputs (SHA-256)\n\n' +
                      ''.join(f'- `{rel}`: `{sha}`\n' for rel, sha in pins.items()) +
                      f'\nDerived asset: `{asset}`; revision: `{manifest["revision"]}`.\n'
                      f'Geometry: {len(payload["vertices"])} vertices, {payload["triangle_count"]} triangles, '
                      'six roles, one LOD, no textures.\n')
        result[base / 'SOURCE.md'] = source_doc.encode()
        derived.append({'pack': pack_id, 'asset': asset, 'binding': binding,
                        'revision': manifest['revision'], 'mesh_sha256': digest,
                        'vertices': len(payload['vertices']), 'triangles': payload['triangle_count']})
    result[Path('artifacts/s08/examples/source-pins.json')] = encoded(
        {'inputs_sha256': pins, 'derivation': 'identity/contract v1; trim <-> accent; no geometry edits',
         'approval': 'none for derived fixtures', 'derived': derived})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    expected = outputs()
    stale = []
    for rel, content in expected.items():
        path = ROOT / rel
        if args.check:
            if not path.is_file() or path.read_bytes() != content:
                stale.append(str(rel))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    if stale:
        parser.exit(1, 'Missing/stale examples:\n' + '\n'.join(stale) + '\n')
    print(f'{"Verified" if args.check else "Generated"} {len(expected)} S08 example files; approved inputs read-only')


if __name__ == '__main__':
    main()
