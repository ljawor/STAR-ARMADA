#!/usr/bin/env python3
"""Read-only S07 identity/CPU-route audit, never renderer acceptance or registration."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from unittest.mock import patch
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))

import game.core.manager  # Establish the application import order before DataStore.
from game.data.store import DataStore
from render import asset_selection as selection
from render.faction_visuals import ship_visual_key
from render import fleet_geometry
from render.asset_registry import AssetResolver
from render.faction_visuals import FACTIONS, convoy_key, normalize_ship_key, normalize_station_key
from tools.art.reconcile_model_coverage import EFFECTS, TEXTURES, build_report as coverage_report


def route_identity(ds, canonical) -> tuple[str, str | None, str | None]:
    """Historical ID -> live data role, never its historical visual/shape string."""
    parts = canonical.split(':')
    if len(parts) == 3 and parts[0] == 'ship' and parts[1] in FACTIONS:
        _, faction, suffix = parts
        if suffix == 'trade_convoy':
            return cast(str, convoy_key(faction)), suffix, 'render.fleet_geometry:ship_mesh'
        matches = [(key, data) for key, data in ds.ships.items()
                   if data.faction == faction and key.split('_', 1)[-1] == suffix]
        if len(matches) != 1:
            raise ValueError(f'{canonical}: expected exactly one current ship')
        data_id, data = matches[0]
        role = data.category
        if role == 'fighter_squadron':
            role = 'bomber' if 'bomber' in data_id or data_id == 'rebel_y_squadron' else 'fighter'
        elif role == 'construction':
            role = 'colonizer' if data_id.endswith('_colonizer') else 'constructor'
        elif role == 'crew_transport' and data.crew_capacity > 0:
            role = 'convoy'
        return f'{data.faction}:{role}', data_id, 'render.fleet_geometry:ship_mesh'
    if ((len(parts) == 3 and parts[0] == 'station') or
            (len(parts) == 4 and parts[:2] in (['hardware', 'satellite'], ['hardware', 'construction']))):
        faction, data_id = parts[-2:]
        if faction not in FACTIONS or data_id not in ds.stations:
            raise ValueError('unknown current station identity: ' + canonical)
        return f'{faction}:{data_id}', data_id, 'render.fleet_geometry:station_mesh'
    if canonical == 'construction:site:scaffold':
        return 'shared:construction_scaffold', None, None
    if canonical == 'menu:cinematic:backdrop':
        return 'menu:cinematic_backdrop', None, None
    if len(parts) == 2 and parts[0] == 'environment' and parts[1] in TEXTURES | EFFECTS | {'asteroid_field'}:
        return canonical, None, None
    raise ValueError('unknown historical identity: ' + canonical)


def build_report(root=ROOT):
    root = Path(root).resolve()
    coverage = coverage_report(root)
    ds = DataStore(assets_dir=str(root / 'assets/data'), mods=[], balance={})
    resolver = AssetResolver(root)
    registry = {r['binding']: r for r in json.loads(
        (root / 'assets/models/registry.json').read_text(encoding='utf-8'))['bindings']}
    manifests = {}
    for path in sorted((root / 'assets/models/manifests').glob('*.json')):
        document = json.loads(path.read_text(encoding='utf-8'))
        if document.get('contract') == 'star-armada/model-manifest':
            manifests[document['asset']] = document
    rows = []
    errors = []
    for original in sorted(coverage['rows'], key=lambda r: r['canonical_binding']):
        row = dict(original)
        parts = row['canonical_binding'].split(':')
        row.update(data_id=None, legacy_visual_key=None, dispatch_entry=None,
                   geometry_dispatch_identity=None, geometry_dispatch_proven=False,
                   cpu_dispatch_exercised=False, triangles=None, ship_binding=None,
                   preview_visual_key=None)
        binding, data_id, entry = route_identity(ds, row['canonical_binding'])
        if binding != row['runtime_binding']:
            errors.append(row['canonical_binding'] + ': coverage/live-data binding disagreement')
        row.update(runtime_binding=binding, data_id=data_id, dispatch_entry=entry)
        resolved = resolver.resolve(binding) if resolver.has_binding(binding) else None
        row['selected'] = resolved is not None
        row['registry_manifest'] = registry.get(binding, {}).get('manifest')
        row['resolved_revision'] = resolved.revision if resolved else None
        row['approval_mesh_match'] = None
        if resolved is not None:
            selected_sha = manifests.get(resolved.asset, {}).get('files', {}).get('mesh', {}).get('sha256')
            row['approval_mesh_match'] = bool(row['asset'] and row['asset']['approval_id'] and
                                              selected_sha == row['asset']['sha256'])
            if not row['approval_mesh_match']:
                errors.append(binding + ': selected mesh differs from approved revision')
            row['disposition'] = 'selected'
        elif registry.get(binding, {}).get('status') == 'core':
            row['disposition'] = 'registered_unresolved'
            errors.append(binding + ': registered core binding failed to resolve')
        elif row['asset'] and row['asset']['approval_id']:
            row['disposition'] = 'approved_not_registered'
        if parts[0] == 'ship':
            faction = parts[1]
            with patch.object(selection, '_resolver', None):
                row['legacy_visual_key'] = ship_visual_key(ds, data_id, faction)
        if row['dispatch_entry'] is not None:
            # A real resolver, scoped without changing application preferences or caches.
            with patch.object(selection, '_resolver', resolver):
                if parts[0] == 'ship':
                    row['ship_binding'] = selection.ship_binding(ds, data_id, faction)
                    key = ship_visual_key(ds, data_id, faction)
                    row['preview_visual_key'] = key
                    row['geometry_dispatch_identity'] = normalize_ship_key(key)
                    mesh = fleet_geometry.ship_mesh(key)
                else:
                    faction = parts[-2]
                    normalized = normalize_station_key(data_id, faction)
                    row['geometry_dispatch_identity'] = binding if resolved else ':'.join(normalized)
                    mesh = fleet_geometry.station_mesh(data_id, faction)
            row['cpu_dispatch_exercised'] = True
            row['triangles'] = sum(len(tris) for tris in mesh.values())
            row['geometry_dispatch_proven'] = resolved is not None and mesh is resolved.mesh
            if resolved is not None and not row['geometry_dispatch_proven']:
                errors.append(binding + ': selected metadata did not reach geometry dispatch')
        rows.append(row)
    return {'schema': 's07-binding-routes/v1', 'rows': rows, 'errors': errors,
            'counts': dict(sorted(Counter(r['disposition'] for r in rows).items())),
            'approval_integrity_errors': coverage['integrity_errors'],
            'limits': ['CPU identity audit only; no GL, renderer, scale, ownership, LOD or picking acceptance.',
                       'Production selection is unchanged; this audit writes no assets or metadata.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--summary', action='store_true')
    args = parser.parse_args(argv)
    report = build_report(args.root)
    output = report
    if args.summary:
        output = {'inventory_rows': len(report['rows']), 'counts': report['counts'],
                  'errors': report['errors'], 'approval_integrity_errors': report['approval_integrity_errors']}
    print(json.dumps(output, indent=2, sort_keys=True))
    return int(bool(report['errors'] or report['approval_integrity_errors']))


if __name__ == '__main__':
    raise SystemExit(main())
