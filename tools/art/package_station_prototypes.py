#!/usr/bin/env python3
"""Package the Imperial station prototypes as visual packs.

Reads each generated runtime mesh, computes its content revision the same way
`render/asset_registry.py` does, and writes the manifest, pack descriptor and SOURCE
note. Core catalogue, registry and approval records are never touched.

    .venv/bin/python tools/art/package_station_prototypes.py
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ROWS = (
    dict(key='research', pack='imperium-research-prototype', pack_id='prototype:imperial_research',
         binding='imperial:research_station', asset='prototype:imperial/research_station',
         mesh='assets/models/research.mesh.json', stem='research',
         display='Galactic Imperium Research Station — visual prototype (unapproved)',
         label='Research Station',
         design='armoured keel, forward laboratory drum with observation cupola and survey spire, '
                'two outrigger science pods on spars, aft dish and radiator array'),
    dict(key='defence', pack='imperium-defense-prototype', pack_id='prototype:imperial_defense',
         binding='imperial:defense_platform', asset='prototype:imperial/defense_platform',
         mesh='assets/models/defense.mesh.json', stem='defense',
         display='Galactic Imperium Defence Platform — visual prototype (unapproved)',
         label='Defence Platform',
         design='octagonal fortress skirt, four corner bastions with elevated twin batteries, '
                'central power core with lit service bands, close-defence mounts and missile hatch banks'),
    dict(key='sensor', pack='imperium-sensor-prototype', pack_id='prototype:imperial_sensor',
         binding='imperial:sensor_station', asset='prototype:imperial/sensor_station',
         mesh='assets/models/sensor.mesh.json', stem='sensor',
         display='Galactic Imperium Sensor Station — visual prototype (unapproved)',
         label='Sensor Station',
         design='armoured base with twin sensor drums, braced lattice mast, great vertical scanner '
                'hoop with clamp ribs, and a dish-and-antenna crown'),
    dict(key='trade', pack='imperium-trade-prototype', pack_id='prototype:imperial_trade',
         binding='imperial:trade_station', asset='prototype:imperial/trade_station',
         mesh='assets/models/trade.mesh.json', stem='trade',
         display='Galactic Imperium Trade Station — visual prototype (unapproved)',
         label='Trade Station',
         design='broad market plinth with four landing pads and cargo arms, stepped exchange tower '
                'with ledges and a crown aerial cluster, raised gallery ring on braced pylons'),
    dict(key='fighter', pack='imperium-fighter-prototype', pack_id='prototype:imperial_fighter',
         binding='imperial:fighter_platform', asset='prototype:imperial/fighter_platform',
         mesh='assets/models/fighter.mesh.json', stem='fighter',
         display='Galactic Imperium Fighter Platform — visual prototype (unapproved)',
         label='Fighter Platform',
         design='hangar block with two lit launch mouths and trough rails, flanking deck platform '
                'with chevrons and an elevator, straight control tower with radar array crown'),
    dict(key='repair', pack='imperium-repair-prototype', pack_id='prototype:imperial_repair',
         binding='imperial:repair_dock', asset='prototype:imperial/repair_dock',
         mesh='assets/models/repair.mesh.json', stem='repair',
         display='Galactic Imperium Repair Station — visual prototype (unapproved)',
         label='Repair Dock',
         design='long armoured slipway floor with guide strips, two high braced side walls with '
                'lit ports and armour plates, three cradle ribs, gantry crane and a control cab'),
    dict(key='relay', pack='imperium-relay-prototype', pack_id='prototype:imperial_relay',
         binding='imperial:energy_relay', asset='prototype:imperial/energy_relay',
         mesh='assets/models/relay.mesh.json', stem='relay',
         display='Galactic Imperium Energy Relay — visual prototype (unapproved)',
         label='Energy Relay',
         design='wide armoured base with four insulator pylons, collector ring on cables, stepped '
                'emitter mast with corner fins and a crown platform carrying the feed bowl'),
)

MIN_ENGINE = '0.16.0'


def main():
    for row in ROWS:
        pack = ROOT / 'visual_packs' / row['pack']
        mesh_path = pack / row['mesh']
        raw = mesh_path.read_bytes()
        payload = json.loads(raw)
        digest = hashlib.sha256(raw).hexdigest()
        body = '\n'.join(f"{key}:{digest}" for key in ('mesh',))
        revision = hashlib.sha256(f"{row['asset']}\n{body}".encode()).hexdigest()
        manifest = {
            'contract': 'star-armada/model-manifest',
            'contract_major': 1,
            'asset': row['asset'],
            'revision': revision,
            'display_name': row['display'],
            'files': {'mesh': {'path': row['mesh'], 'sha256': digest, 'bytes': len(raw)}},
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
                'notes': f"Original Imperial {row['label'].lower()} authored by "
                         f"tools/art/build_imperial_station_prototypes.py; editable source "
                         f"art/blender/imperium_{row['key']}_prototype.blend. Appearance review "
                         "pending. No gameplay changes or proprietary models.",
            },
            'requires': {'min_engine': MIN_ENGINE, 'material_profile': 'core:fleet/standard'},
            'budgets': {'triangles': payload['triangle_count'], 'draw_calls': 6, 'texture_bytes': 0},
        }
        descriptor = {
            'contract': 'star-armada/visual-pack',
            'contract_major': 1,
            'id': row['pack_id'],
            'version': '0.1.0',
            'requires': {'min_engine': MIN_ENGINE, 'contracts': ['star-armada/model-manifest/v1']},
            'content': {'replaces': [{
                'binding': row['binding'],
                'replace_of': f"core:imperial/{row['binding'].split(':')[1]}",
                'manifest': f"assets/models/manifests/{row['stem']}.json",
            }]},
            'notes': f"Owner-requested Galactic Imperium {row['label']} prototype. Core catalogue "
                     "unchanged; the approved appearance of every other asset is untouched.",
        }
        manifests = pack / 'assets/models/manifests'
        manifests.mkdir(parents=True, exist_ok=True)
        (manifests / f"{row['stem']}.json").write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        (pack / 'visual-pack.json').write_text(json.dumps(descriptor, indent=2) + '\n', encoding='utf-8')
        (pack / 'SOURCE.md').write_text(source_note(row), encoding='utf-8')
        print('PACK', row['pack'], payload['triangle_count'], revision[:16])


def source_note(row):
    return f"""# Galactic Imperium {row['label']} — visual prototype

An original Blender-authored asset in the visible-first replacement series. Replaces only
`{row['binding']}`; every core approved asset and gameplay definition is unchanged.

## Design

{row['design']}. Homeworld-influenced silhouette language only: no proprietary geometry,
textures or purchased assets.

## Play

Run `Play Station Prototypes.command` from the repository to open the real game in a stock
Imperial skirmish with this station selected and framed. Test saves and settings stay beneath
`~/Library/Application Support/STAR ARMADA/Station Prototypes/`, separate from normal user data.
The installed application bundle is not replaced.

## Authoring

- Editable Blender source: `art/blender/imperium_{row['key']}_prototype.blend`.
- Script-authoritative builder/exporter: `tools/art/build_imperial_station_prototypes.py`, Blender 5.0.1.
- Pack metadata builder: `.venv/bin/python tools/art/package_station_prototypes.py`.
- Six existing material roles, no shader or texture-pipeline changes.
- The binding's approved envelope is preserved exactly: in-game length, collision radii, ship
  sizes and simulation hashes are untouched.

Focused integration check: `PYTHONPATH=tests .venv/bin/python -m unittest test_station_prototypes -v`.
"""


if __name__ == '__main__':
    main()
