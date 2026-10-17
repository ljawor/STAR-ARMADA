#!/usr/bin/env python3
"""B3 scope probe: resolve every station binding to its real mesh key, legacy envelope and
triangle count, using the live code (never a transcribed table).

    PYTHONPATH=tests .venv/bin/python tools/art/probe_b3_scope.py

Imperial stations are reported separately: `render/fleet_geometry.station_mesh` dispatches
them straight to `_station_mesh(did)` with no `mesh_for` seam, so an authored imperial
station needs a renderer change and is therefore an owner/renderer decision, not an asset
in this batch - the same shape as the shared imperial ship shapes.
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
print('imperial (no seam - renderer change required):')
for kind in STATION_TYPES:
    legacy = imperial_station_mesh(kind)
    lo, hi, tris = bounds_of(legacy)
    print(f"{'imperial:' + kind:30s} {'-':9s} {stations[kind]['radius']:6d} {'-':>8s} {tris:6d}  {lo} .. {hi}")
print()
print('satellite / planet-installation rows (B4, not stations):')
for name, row in stations.items():
    if name.startswith('planet_') or 'satellite' in name:
        print(f"  {name:28s} radius={row['radius']}")
