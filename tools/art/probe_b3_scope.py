#!/usr/bin/env python3
"""B3 scope probe: resolve every station binding to its real mesh key, legacy envelope and
triangle count, using the live code (never a transcribed table).

    PYTHONPATH=tests .venv/bin/python tools/art/probe_b3_scope.py

Imperial stations are reported separately, and *not* because they lack a seam: `station_mesh`
consults `mesh_for(f'{faction}:{data_id}')` ahead of its imperial branch for every faction,
imperial included. They were held out of B3a/B3b/B3c because they were not in scope then; the owner
put them in scope on 2026-10-17 (`s06-imperial-migration-2026-10-17`). What imperial *ships* need is
a per-binding key minted in `render/faction_visuals.py::ship_visual_key`, which today mints one only
for the three non-imperial families and lets imperial hulls fall onto the shared 'wedge'/'box' shapes.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import game.core.manager          # noqa: F401  (import order: break the core/systems cycle)
from game.data.store import DataStore
from render.asset_selection import mesh_for
from render.faction_stations import FACTIONS, STATION_TYPES, station_mesh as faction_station_mesh
from render.fleet_geometry import _station_mesh as imperial_station_mesh

ds = DataStore.get()
rows = ds.stations if hasattr(ds, 'stations') else None
stations = json.loads((ROOT / 'assets/data/stations/stations.json').read_text())['stations']


def bounds_of(mesh):
    pts = [p for _role, tris in mesh.items() for _n, tri in tris for p in tri]
    lo = [round(min(p[i] for p in pts), 4) for i in range(3)]
    hi = [round(max(p[i] for p in pts), 4) for i in range(3)]
    tris = sum(len(v) for v in mesh.values())
    return lo, hi, tris


print('STATION_TYPES', len(STATION_TYPES), '| factions with a seam:', FACTIONS)
print('rows in assets/data/stations/stations.json:', len(stations))
print()
print(f"{'binding':30s} {'mesh_for':9s} {'radius':>6s} {'length':>8s} {'tri':>6s}  envelope")
for faction in FACTIONS:
    for kind in STATION_TYPES:
        key = f'{faction}:{kind}'
        seam = mesh_for(key)
        legacy = faction_station_mesh(faction, kind)
        lo, hi, tris = bounds_of(legacy)
        length = 2 * max(math.sqrt(sum(v * v for v in p)) for p in (lo, hi))
        print(f"{key:30s} {str(seam is None):9s} {stations[kind]['radius']:6d} {length:8.3f} {tris:6d}  "
              f"{lo} .. {hi}")
print()
print('imperial (in scope since s06-imperial-migration-2026-10-17; the seam is faction-generic):')
for kind in STATION_TYPES:
    legacy = imperial_station_mesh(kind)
    lo, hi, tris = bounds_of(legacy)
    print(f"{'imperial:' + kind:30s} {'-':9s} {stations[kind]['radius']:6d} {'-':>8s} {tris:6d}  {lo} .. {hi}")
print()
print('satellite / planet-installation rows (B4, not stations):')
for name, row in stations.items():
    if name.startswith('planet_') or 'satellite' in name:
        print(f"  {name:28s} radius={row['radius']}")
