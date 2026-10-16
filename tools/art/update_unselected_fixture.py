#!/usr/bin/env python3
"""Recompute the pinned unselected-catalogue hashes and show exactly what moved.

`tests/fixtures/alliance_trio_unselected.sha256.json` pins 73 catalogue entries so an
authored-asset revision cannot silently change a hull it does not own. Revising one asset
is expected to move exactly the entries that route to it; anything else is a defect.

    PYTHONPATH=tests .venv/bin/python tools/art/update_unselected_fixture.py            # report only
    PYTHONPATH=tests .venv/bin/python tools/art/update_unselected_fixture.py --write    # report, then update

`--write` refuses unless every change is one of the assets named by --expect (default
`ship/rebel/battleship`), so an unintended second change cannot ride along.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
FIXTURE = ROOT / 'tests/fixtures/alliance_trio_unselected.sha256.json'


def catalogue_mesh(key):
    from render.faction_ships import ship_mesh
    from render.faction_stations import station_mesh
    from render.fleet_geometry import ship_mesh as legacy_ship_mesh, _station_mesh as legacy_station_mesh
    kind, faction, role = key.split('/')
    if kind == 'legacy_ship':
        return legacy_ship_mesh(role)
    if faction == 'imperial':
        return legacy_station_mesh(role)
    return (ship_mesh if kind == 'ship' else station_mesh)(faction, role)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='update the fixture after reporting')
    parser.add_argument('--expect', action='append', default=None,
                        help='key allowed to change (repeatable); defaults to ship/rebel/battleship')
    args = parser.parse_args()
    allowed = set(args.expect or ['ship/rebel/battleship'])

    expected = json.loads(FIXTURE.read_text(encoding='utf-8'))
    actual = {key: hashlib.sha256(repr(dict(catalogue_mesh(key))).encode()).hexdigest() for key in expected}
    changed = {key: (expected[key], actual[key]) for key in expected if expected[key] != actual[key]}
    print(f'entries={len(expected)} changed={len(changed)}')
    for key, (before, after) in changed.items():
        print(f'  {key}\n    before {before}\n    after  {after}')
    unexpected = sorted(set(changed) - allowed)
    if unexpected:
        raise SystemExit(f'unexpected catalogue changes: {unexpected} (allowed: {sorted(allowed)})')
    if args.write:
        FIXTURE.write_text(json.dumps({key: actual[key] for key in expected}, indent=2, sort_keys=True) + '\n',
                           encoding='utf-8')
        print('fixture updated:', FIXTURE)


if __name__ == '__main__':
    main()
