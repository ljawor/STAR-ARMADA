#!/usr/bin/env python3
"""Package the two original industrial prototypes; never rewrite accepted models."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROWS = [('shipyard', 'imperium-shipyard-prototype', 'shipyard', 'Imperial Shipyard'),
        ('mining_station', 'imperium-mining-prototype', 'mining', 'Imperial Mining Station')]


def main():
    for kind, folder, stem, name in ROWS:
        pack = ROOT / 'visual_packs' / folder
        path = pack / f'assets/models/{stem}.mesh.json'
        raw = path.read_bytes()
        payload = json.loads(raw)
        asset = 'prototype:imperial/' + kind
        assert payload['asset'] == asset
        digest = hashlib.sha256(raw).hexdigest()
        manifest = deepcopy(json.loads((ROOT / f'assets/models/manifests/imperial_{kind}.json').read_text()))
        manifest.pop('approval', None)
        manifest['export'].pop('legacy_schema_int', None)
        manifest.update(asset=asset, display_name=name + ' — visual prototype (review pending)',
                        revision=hashlib.sha256((asset + '\nmesh:' + digest).encode()).hexdigest())
        manifest['files'] = {'mesh': {'path': f'assets/models/{stem}.mesh.json', 'sha256': digest, 'bytes': len(raw)}}
        manifest['bounds'] = {'min': payload['bounds'][0], 'max': payload['bounds'][1]}
        manifest['roles'] = sorted(payload['batches'])
        manifest['budgets'] = {'triangles': payload['triangle_count'], 'draw_calls': 6, 'texture_bytes': 0}
        manifest['provenance'] = {'author': 'Lukasz Jawor / STAR ARMADA visual prototype', 'tool': 'Blender',
            'tool_version': '5.0.1', 'license': 'original', 'notes': f'Original asset: tools/art/build_{stem}_prototype.py, art/blender/imperium_{stem}_prototype.blend. Local appearance review pending; no proprietary assets or gameplay rule changes.'}
        descriptor = {'contract': 'star-armada/visual-pack', 'contract_major': 1,
            'id': 'prototype:imperium_' + stem, 'version': '0.1.0',
            'requires': {'min_engine': '0.15.1', 'contracts': ['star-armada/model-manifest/v1']},
            'content': {'replaces': [{'binding': 'imperial:' + kind, 'replace_of': 'core:imperial/' + kind,
                                   'manifest': f'assets/models/manifests/{stem}.json'}]},
            'notes': 'Local owner-requested prototype. Existing Vigil and Command Center bytes unchanged. Review before PR additions.'}
        for rel, value in [(f'assets/models/manifests/{stem}.json', manifest), ('visual-pack.json', descriptor)]:
            target = pack / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f'INDUSTRY_PACK_OK {kind} triangles={payload["triangle_count"]} mesh_sha256={digest}')


if __name__ == '__main__':
    main()
