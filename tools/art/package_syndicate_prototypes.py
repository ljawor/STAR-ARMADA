#!/usr/bin/env python3
"""Write the Rim Syndicate prototype pack from the built runtime meshes.

Mirrors ``package_station_prototypes.py`` exactly, because a manifest's revision
is defined as ``sha256(asset + '\\n' + 'mesh:<file sha256>')`` -- guessing that
recipe produces a pack the loader rejects with ``E_REVISION_MISMATCH``.

The pack is data-only: it replaces three bindings that currently have no core
mesh, so no approved asset's appearance moves and no gameplay rule changes.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = 'syndicate-imperium-prototypes'
PACK_ID = 'prototype:syndicate_imperium'
MIN_ENGINE = '0.16.0'

ROWS = (
    dict(stem='bomber', binding='syndicate:bomber',
         asset='prototype:syndicate/bomber',
         display='Rim Syndicate Cutthroat Strike Wing — rework prototype (unapproved)',
         label='strike wing',
         design='swept wing volumes off a welded barge fuselage with tip pods, a blunt ram prow, '
                'one offset command tower, exposed reactor drums in welded pedestals and drive '
                'emitters set inside annular throats'),
    dict(stem='battleship', binding='syndicate:battleship',
         asset='prototype:syndicate/battleship',
         display='Rim Syndicate Marauder Battleship — rework prototype (unapproved)',
         label='battleship',
         design='chamfered barge hull under a raised deckhouse, one thick port armour sponson '
                'opposed by a starboard truss ending in a counterweight drum, three centreline '
                'turrets, casemates on the sponsons and four annular drive throats'),
    dict(stem='supercapital', binding='syndicate:supercapital',
         asset='prototype:syndicate/supercapital',
         display='Rim Syndicate Leviathan Salvage Dreadnought — rework prototype (unapproved)',
         label='salvage dreadnought',
         design='the battleship language at dreadnought scale with machinery terraces, a '
                'cathedral gantry over the spine, four centreline turrets, six casemates and six '
                'annular drive throats'),
)


def main():
    replaces = []
    for row in ROWS:
        mesh_path = ROOT / 'visual_packs' / PACK / 'assets/models' / f"syndicate_{row['stem']}.mesh.json"
        raw = mesh_path.read_bytes()
        payload = json.loads(raw)
        digest = hashlib.sha256(raw).hexdigest()
        body = 'mesh:' + digest
        revision = hashlib.sha256(f"{row['asset']}\n{body}".encode()).hexdigest()
        manifest = {
            'contract': 'star-armada/model-manifest',
            'contract_major': 1,
            'asset': row['asset'],
            'revision': revision,
            'display_name': row['display'],
            'files': {'mesh': {'path': f"assets/models/syndicate_{row['stem']}.mesh.json",
                               'sha256': digest, 'bytes': len(raw)}},
            'export': {'contract': 'star-armada/mesh-export', 'contract_major': 1},
            'coordinates': 'X beam; Y up; +Z forward',
            'pivot': [0, 0, 0],
            'bounds': {'min': payload['bounds'][0], 'max': payload['bounds'][1]},
            'nominal_scale': 1.0,
            'roles': sorted(payload['batches']),
            'provenance': {
                'author': 'Lukasz Jawor / STAR ARMADA visual prototype',
                'tool': 'Blender',
                'tool_version': '5.0.1',
                'license': 'original',
                'notes': f"Original Rim Syndicate {row['label']} authored by "
                         "tools/art/build_syndicate_imperium.py; editable source "
                         f"art/blender/syndicate_{row['stem']}.blend. Appearance review pending. "
                         "No gameplay, scale or collision changes: the mesh occupies the measured "
                         "legacy procedural envelope.",
            },
            'requires': {'min_engine': MIN_ENGINE, 'material_profile': 'core:fleet/standard'},
            'budgets': {'triangles': payload['triangle_count'], 'draw_calls': 6,
                        'texture_bytes': 0},
        }
        manifests = ROOT / 'visual_packs' / PACK / 'assets/models/manifests'
        manifests.mkdir(parents=True, exist_ok=True)
        (manifests / f"{row['stem']}.json").write_text(json.dumps(manifest, indent=2) + '\n',
                                                       encoding='utf-8')
        replaces.append({'binding': row['binding'],
                         'replace_of': f"core:syndicate/{row['stem']}",
                         'manifest': f"assets/models/manifests/{row['stem']}.json"})
        print('PACK', row['stem'], payload['triangle_count'], revision[:16])
    descriptor = {
        'contract': 'star-armada/visual-pack',
        'contract_major': 1,
        'id': PACK_ID,
        'version': '0.1.0',
        'requires': {'min_engine': MIN_ENGINE,
                     'contracts': ['star-armada/model-manifest/v1']},
        'content': {'replaces': replaces},
        'notes': 'Owner-requested Rim Syndicate rework: the three hulls the faction never had. '
                 'Core catalogue unchanged; the approved appearance of every other asset is '
                 'untouched.',
    }
    (ROOT / 'visual_packs' / PACK / 'visual-pack.json').write_text(
        json.dumps(descriptor, indent=2) + '\n', encoding='utf-8')
    print('PACK_OK', len(replaces))


if __name__ == '__main__':
    main()
