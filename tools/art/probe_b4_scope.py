#!/usr/bin/env python3
"""B4 scope probe: resolve every satellite and planet-installation binding to its real mesh key,
legacy envelope, radius and triangle count, using the live code (never a transcribed table).

    PYTHONPATH=tests .venv/bin/python tools/art/probe_b4_scope.py

The rows come from `assets/data/stations/stations.json` minus the station kinds, because that file
holds both and enumerating by hand is how a row gets missed. `render/fleet_geometry.station_mesh`
consults the authored-model seam ahead of any fallback for *every* faction, imperial included, so
these rows are ordinary asset work now that the owner has put them in scope - the imperial ships are
the ones that need a per-binding key minted in render/faction_visuals.py::ship_visual_key.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import game.core.manager          # noqa: F401  (import order: break the core/systems cycle)
from game.data.store import DataStore
from game.systems.planet_buildings import BUILDING_TYPES
from render.asset_selection import mesh_for
from render.faction_stations import FACTIONS
from render.fleet_geometry import _satellite_mesh, station_mesh

FACTIONS_ALL = tuple(FACTIONS) + (('imperial',) if 'imperial' not in FACTIONS else ())
SATELLITE_KINDS = ('defense_satellite', 'attack_satellite')

ds = DataStore.get()
stations = json.loads((ROOT / 'assets/data/stations/stations.json').read_text())['stations']
KINDS = [k for k in stations if k not in BUILDING_TYPES and 'satellite' not in k]
HARDWARE = [k for k in stations if k in BUILDING_TYPES or k in SATELLITE_KINDS]


def bounds_of(mesh):
    pts = [p for _role, tris in mesh.items() for _n, tri in tris for p in tri]
    lo = [round(min(p[i] for p in pts), 4) for i in range(3)]
    hi = [round(max(p[i] for p in pts), 4) for i in range(3)]
    tris = sum(len(v) for v in mesh.values())
    return lo, hi, tris


def legacy(kind, faction):
    """The mesh the game draws today for this row: the same entry the renderer uses."""
    return station_mesh(kind, faction)


print('factions:', FACTIONS_ALL)
print('station kinds (B3):', sorted(KINDS))
print('satellite / installation kinds (B4):', sorted(HARDWARE))
print()
print(f"{'binding':34s} {'radius':>6s} {'tri':>6s} {'min_length':>10s}  envelope (lo .. hi)")
rows = []
for faction in FACTIONS_ALL:
    for kind in sorted(HARDWARE):
        key = f'{faction}:{kind}'
        mesh = legacy(kind, faction)
        lo, hi, tris = bounds_of(mesh)
        span = [round(hi[i] - lo[i], 4) for i in range(3)]
        radius = stations[kind]['radius']
        rows.append({'binding': key, 'kind': kind, 'faction': faction, 'radius': radius,
                     'envelope_lo': lo, 'envelope_hi': hi, 'span': span, 'triangles': tris,
                     'min_length': round(max(span), 4), 'seam_resolves': mesh_for(key) is not None})
        print(f"{key:34s} {radius:6d} {tris:6d} {max(span):10.3f}  {lo} .. {hi}")

print()
print('every row still procedural until its binding is registered:',
      all(not r['seam_resolves'] for r in rows), '| rows:', len(rows))
# No artifact is written: the batch sheet is the record, and this probe regenerates its table.
# Kept as evidence that the envelopes in that sheet came from the live code, not from a transcription.
_ = rows
