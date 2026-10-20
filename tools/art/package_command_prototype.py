#!/usr/bin/env python3
"""Package the original Blender Command Center export without modifying the Vigil pack."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / 'visual_packs/imperium-command-prototype'


def main():
    path = PACK / 'assets/models/command.mesh.json'
    raw = path.read_bytes()
    payload = json.loads(raw)
    asset = 'prototype:imperial/command_station'
    assert payload['asset'] == asset
    digest = hashlib.sha256(raw).hexdigest()
    manifest = deepcopy(json.loads((ROOT / 'assets/models/manifests/imperial_command_station.json').read_text()))
    manifest.pop('approval', None)
    manifest['export'].pop('legacy_schema_int', None)
    manifest.update(asset=asset, display_name='Galactic Imperium Command Center — visual prototype (unapproved)',
                    revision=hashlib.sha256((asset + '\nmesh:' + digest).encode()).hexdigest())
    manifest['files'] = {'mesh': {'path': 'assets/models/command.mesh.json', 'sha256': digest, 'bytes': len(raw)}}
    manifest['bounds'] = {'min': payload['bounds'][0], 'max': payload['bounds'][1]}
    manifest['roles'] = sorted(payload['batches'])
    manifest['budgets'] = {'triangles': payload['triangle_count'], 'draw_calls': 6, 'texture_bytes': 0}
    manifest['provenance'] = {
        'author': 'Lukasz Jawor / STAR ARMADA visual prototype', 'tool': 'Blender',
        'tool_version': '5.0.1', 'license': 'original',
        'notes': 'Original industrial command fortress authored by tools/art/build_command_center_prototype.py; editable source art/blender/imperium_command_prototype.blend. Appearance review pending. No gameplay changes or proprietary models.'}
    descriptor = {
        'contract': 'star-armada/visual-pack', 'contract_major': 1, 'id': 'prototype:imperium_command',
        'version': '0.1.0', 'requires': {'min_engine': '0.15.1', 'contracts': ['star-armada/model-manifest/v1']},
        'content': {'replaces': [{'binding': 'imperial:command_station', 'replace_of': 'core:imperial/command_station',
                                  'manifest': 'assets/models/manifests/command.json'}]},
        'notes': 'Owner-requested Galactic Imperium Command Center prototype beside unchanged approved-look Vigil. Station appearance pending; core catalogue unchanged.'}
    for rel, value in [('assets/models/manifests/command.json', manifest), ('visual-pack.json', descriptor)]:
        target = PACK / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'COMMAND_PACK_OK triangles={payload["triangle_count"]} mesh_sha256={digest} revision={manifest["revision"]}')


if __name__ == '__main__':
    main()
