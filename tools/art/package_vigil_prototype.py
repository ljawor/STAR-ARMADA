#!/usr/bin/env python3
"""Package the standalone Blender Vigil export as a reversible one-binding visual pack."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / 'visual_packs/vigil-prototype'


def main():
    path = PACK / 'assets/models/vigil.mesh.json'
    raw = path.read_bytes()
    payload = json.loads(raw)
    asset = 'prototype:imperial/vigil'
    assert payload['asset'] == asset
    digest = hashlib.sha256(raw).hexdigest()
    manifest = deepcopy(json.loads((ROOT / 'assets/models/manifests/imperial_corvette.json').read_text()))
    manifest.pop('approval', None)
    manifest['export'].pop('legacy_schema_int', None)
    manifest.update(asset=asset, display_name='Vigil Corvette — visual prototype (unapproved)',
                    revision=hashlib.sha256((asset + '\nmesh:' + digest).encode()).hexdigest())
    manifest['files'] = {'mesh': {'path': 'assets/models/vigil.mesh.json', 'sha256': digest, 'bytes': len(raw)}}
    manifest['bounds'] = {'min': payload['bounds'][0], 'max': payload['bounds'][1]}
    manifest['roles'] = sorted(payload['batches'])
    manifest['budgets'] = {'triangles': payload['triangle_count'], 'draw_calls': 6, 'texture_bytes': 0}
    manifest['provenance'] = {
        'author': 'Lukasz Jawor / STAR ARMADA visual prototype', 'tool': 'Blender',
        'tool_version': '5.0.1', 'license': 'original',
        'notes': 'Original industrial Corvette authored by tools/art/build_vigil_prototype.py; editable source art/blender/vigil_prototype.blend. One-ship visual experiment, not owner appearance approved. No gameplay changes or proprietary models.'}
    descriptor = {
        'contract': 'star-armada/visual-pack', 'contract_major': 1, 'id': 'prototype:vigil',
        'version': '0.1.0', 'requires': {'min_engine': '0.15.1', 'contracts': ['star-armada/model-manifest/v1']},
        'content': {'replaces': [{'binding': 'imperial:corvette', 'replace_of': 'core:imperial/corvette',
                                  'manifest': 'assets/models/manifests/vigil.json'}]},
        'notes': 'Owner-requested Vigil-only visual prototype. Appearance review pending; original approved catalogue remains unchanged.'}
    for rel, value in [('assets/models/manifests/vigil.json', manifest), ('visual-pack.json', descriptor)]:
        target = PACK / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'VIGIL_PACK_OK triangles={payload["triangle_count"]} mesh_sha256={digest} revision={manifest["revision"]}')


if __name__ == '__main__':
    main()
