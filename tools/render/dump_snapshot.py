"""Export real, read-only graphics fixtures to W01 offline snapshots; no GL."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game.benchmark import state_hash
from game.graphics_benchmark import semantic_inventory
from render import asset_selection
from render.ship_sizes import ship_size


def _manifest_map():
    registry = json.loads((ROOT / 'assets/models/registry.json').read_text())
    manifests = {m['asset']: m for path in sorted((ROOT / 'assets/models/manifests').glob('*.json'))
                 for m in [json.loads(path.read_text())]}
    return {row['binding']: manifests[row['manifest']] for row in registry['bindings']
            if row['status'] == 'core'}


def _asset(binding, manifests):
    # Use the real resolver for contract, indices, normal, envelope and hash validation.
    if asset_selection.mesh_for(binding) is None:
        raise ValueError(f'unresolved approved mesh: {binding}')
    entry = manifests[binding]['files']['mesh']
    path = (ROOT / entry['path']).resolve()
    asset_root = (ROOT / 'assets').resolve()
    if not path.is_relative_to(asset_root):
        raise ValueError(f'mesh path escapes assets root: {path}')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != entry['sha256'] or len(raw) != entry['bytes']:
        raise ValueError(f'mesh hash/length mismatch: {binding}')
    mesh = json.loads(raw)
    triangles = sum(len(rows) for rows in mesh['batches'].values())
    if triangles != mesh['triangle_count']:
        raise ValueError(f'mesh triangle count mismatch: {binding}')
    return dict(binding=binding, path=path.relative_to(asset_root).as_posix(),
                sha256=digest, vertex_count=len(mesh['vertices']), triangle_count=triangles)


def _category(e):
    if e.satellite_slot is not None:
        return 'satellites'
    if e.data_id == 'trade_convoy':
        return 'transports'
    if e.is_station:
        return 'trade_stations' if e.data_id == 'trade_station' else 'ordinary_stations'
    return 'combat_ships'


def build_snapshot(fixture, *, all_visible=False) -> dict:
    """Read a factory fixture without stepping it; only local render caches change."""
    st, ds = fixture.manager.state, fixture.manager.ds
    before = state_hash(st)
    try:
        # AssetResolver's root contains assets/, despite its asset_root parameter name.
        report = asset_selection.configure({'model_preview': True}, asset_root=ROOT)
        if not report['coverage']['ok']:
            raise ValueError('approved catalogue is incomplete')
        manifests = _manifest_map()
        instances, omitted = [], []
        detected = [e for e in sorted(st.entities.values(), key=lambda e: e.id)
                    if e.alive and (all_visible or st.can_see(0, e.id))]
        for e in detected:
            if e.is_planet:
                omitted.append(e.id)
                continue
            faction = st.players[e.owner].faction if e.owner in st.players else 'imperial'
            binding = ('imperial:' + e.data_id if e.is_station else
                       asset_selection.ship_binding(ds, e.data_id, faction))
            if binding is None or binding not in manifests:
                raise ValueError(f'alive entity has no approved mesh: {e.id} {e.data_id}')
            scale = e.radius / 50. if e.is_station else ship_size(ds, e.data_id, faction).scale
            color = st.players[e.owner].color if e.owner in st.players else (1., 1., 1.)
            instances.append(dict(entity_id=e.id, binding=binding, position=list(e.pos.to_tuple()),
                                  yaw=e.yaw, scale=scale, tint=[*color, 1.], category=_category(e)))
        assets = [_asset(binding, manifests) for binding in sorted({i['binding'] for i in instances})]
        camera = asdict(fixture.camera)
        camera['target'] = list(camera['target'])
        metadata = fixture.metadata()
        metadata.update(inventory=semantic_inventory(st), exported_inventory=semantic_inventory(
            st, entities=[st.entities[i['entity_id']] for i in instances]),
            visibility='omniscient-diagnostic' if all_visible else 'player0-detection',
            omitted_planets=omitted, omitted_features=['planets (W05)', 'fog raster', 'effects', 'UI'],
            scale_policy='Canonical ship_size.scale; differs from gameplay zoom readability inflation. Stations radius/50.',
            checksum='game.benchmark.state_hash: full precise state before and after extraction',
            profile='W00/W01 offline JSON; not W02 shared memory or a throughput claim')
        if all_visible:
            metadata['assumptions'].append('Omniscient diagnostic export; not ordinary player visibility.')
        return dict(schema=1, fixture=fixture.name, state_sha256=before, camera=camera,
                    instances=instances, assets=assets, metadata=metadata)
    finally:
        if state_hash(st) != before:
            raise RuntimeError('render extraction mutated precise simulation state')


def build_catalogue(fixture) -> dict:
    """Approved runtime closure in an artificial grid, explicitly not a battle."""
    st = fixture.manager.state
    before = state_hash(st)
    try:
        payload = build_snapshot(fixture, all_visible=True)
        manifests = _manifest_map()
        assets = [_asset(binding, manifests) for binding in sorted(manifests)]
        if len(assets) != 103 or len({a['path'] for a in assets}) != 103:
            raise ValueError('expected 103 unique approved runtime meshes')
        payload['fixture'] = 'approved-runtime-catalogue-inspection-v1'
        payload['assets'] = assets
        payload['instances'] = [dict(entity_id=index, binding=asset['binding'],
                                     position=[float(index % 11) * 700., 0., float(index // 11) * 700.],
                                     yaw=0., scale=1., tint=[.55, .7, 1., 1.], category='catalogue')
                                for index, asset in enumerate(assets)]
        payload['camera'] = dict(target=[3500., 0., 3150.], distance=11000., yaw=0., pitch=65., fov=55.)
        payload['metadata'].update(visibility='catalogue-inspection-not-gameplay',
                                   source_fixture=fixture.name, exported_inventory={'catalogue_meshes': 103},
                                   scale_policy='Inspection grid: raw authored mesh units, scale 1; not gameplay size.')
        payload['metadata']['assumptions'].append(
            'Artificial catalogue grid, synthetic IDs/transforms; checksum refers to unchanged source fixture, not this layout.')
        return payload
    finally:
        if state_hash(st) != before:
            raise RuntimeError('catalogue extraction mutated precise simulation state')


def main(argv=None):
    import argparse
    from game.graphics_benchmark import FIXTURES, make_fixture
    from render_bridge.protocol import encode, WORLD
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', choices=FIXTURES, default='four-player-combat-v1')
    parser.add_argument('--units', type=int, help='Assert fixture combat-ship count; never changes its recipe')
    parser.add_argument('--all-visible', action='store_true', help='Omniscient diagnostic; not player visibility')
    parser.add_argument('--catalogue', action='store_true', help='103 approved meshes in artificial inspection grid')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    fixture = make_fixture(args.fixture)
    count = semantic_inventory(fixture.manager.state)['total']['combat_ships']
    if args.units is not None and args.units != count:
        parser.error(f'fixture contains {count} combat ships; --units cannot alter the fixture')
    payload = (build_catalogue(fixture) if args.catalogue else
               build_snapshot(fixture, all_visible=args.all_visible))
    raw = encode(payload, kind=WORLD, tick=fixture.manager.state.tick, frame_index=0)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(raw)
    print(json.dumps(dict(out=str(args.out.resolve()), bytes=len(raw), instances=len(payload['instances']),
                          assets=len(payload['assets']), state_sha256=payload['state_sha256'],
                          visibility=payload['metadata']['visibility']), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
