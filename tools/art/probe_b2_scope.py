#!/usr/bin/env python3
"""B2 scope probe: resolve every squadron/logistics binding to its real mesh key,
legacy envelope and triangle count, using the live code (never a transcribed table).

    PYTHONPATH=tests .venv/bin/python tools/art/probe_b2_scope.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import game.core.manager          # noqa: F401  (import order: break the core/systems cycle)
from game.data.store import DataStore
from render.asset_selection import mesh_for
from render.faction_ships import _ship_mesh, ship_mesh
from render.faction_visuals import FACTIONS, SHIP_KEYS, normalize_ship_key, ship_visual_key
from render.ship_sizes import ship_size

SQUADRONS = ('rebel_x_squadron', 'rebel_y_squadron', 'imperial_tie_squadron',
             'imperial_tie_bomber_squadron', 'confederacy_vulture_squadron',
             'confederacy_bomber_squadron', 'syndicate_raid_squadron')
LOGISTICS = tuple(f'{f}_crew_transport' for f in ('rebel', 'imperial', 'confederacy', 'syndicate')) \
    + ('trade_convoy',)

ds = DataStore.get()
print('FACTIONS', FACTIONS)
rows = {}
for data_id in SQUADRONS + LOGISTICS:
    data = ds.ships.get(data_id)
    faction = data.faction if data else None
    key = ship_visual_key(ds, data_id, faction)
    entry = dict(data_id=data_id, category=(data.category if data else None),
                 faction=faction, radius=(data.radius if data else None),
                 crew_capacity=(getattr(data, 'crew_capacity', None) if data else None),
                 shape=(ds.ship_visual(data_id)['shape'] if data else None),
                 mesh_key=key, in_ship_keys=key in SHIP_KEYS)
    if ':' in key and key != 'box':
        f, r = key.split(':')
        try:
            size = ship_size(ds, data_id, faction)
            entry['ratio_class'] = size.ratio
            entry['length'] = round(size.length, 3)
        except Exception as exc:                                  # noqa: BLE001
            entry['length_error'] = str(exc)
        legacy = _ship_mesh(f, r) if f in ('rebel', 'confederacy', 'syndicate') else None
        if legacy:
            pts = [p for mesh in legacy.values() for _, tri in mesh for p in tri]
            lo = [round(min(p[i] for p in pts), 3) for i in range(3)]
            hi = [round(max(p[i] for p in pts), 3) for i in range(3)]
            tris = sum(len(t) for mesh in legacy.values() for _, t in mesh)
            entry['legacy'] = dict(envelope=[lo, hi], triangles=tris, roles=sorted(legacy))
            entry['authored_now'] = mesh_for(f'{f}:{r}') is not None
    rows[data_id] = entry

print(json.dumps(rows, indent=1, sort_keys=True))
print('\ndistinct authorable mesh keys:')
seen = {}
for data_id, e in rows.items():
    key = e.get('mesh_key')
    if e.get('legacy'):
        seen.setdefault(key, []).append(data_id)
for key, users in sorted(seen.items()):
    print(f'  {key:28s} users={users} envelope={rows[users[0]]["legacy"]["envelope"]} '
          f'tris={rows[users[0]]["legacy"]["triangles"]} length={rows[users[0]].get("length")}')
