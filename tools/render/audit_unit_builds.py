#!/usr/bin/env python3
"""Exhaustive CPU paid construction audit. No window, GL, save or user settings IO.

Run from repository root:
 SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m tools.render.audit_unit_builds

Manifest identity is (kind,id), NOT render binding (several hulls may share one).
Station cases cover every faction. Rich fixtures deliberately do not prove campaign
or AI progression: they prove real authoritative paid queue and completion paths.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path
import signal
import tempfile
import traceback
from unittest.mock import patch

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

# Import core first: systems -> core -> manager otherwise has an existing cycle.
from game.core.state import GameState, PlayerState
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.construction import ConstructionSystem, buildable_ship_ids, required_level, _body_clearance
from game.systems.unit_factory import UnitFactory
from game.systems.planet_buildings import BUILDING_TYPES, start_building
from render import asset_selection
from render_bridge.collect import station_binding

SCRATCH = Path.home() / '.hermes/cache/scratch'
DEFAULT_OUTPUT = SCRATCH / 'sa-all-unit-audit'
SATELLITES = ('defense_satellite', 'attack_satellite')
RESOURCES = ('credits', 'materials', 'energy', 'crew')


@contextmanager
def isolated_catalogue():
    """Own DataStore, render selection and EVERY settings/save path temporarily."""
    from render import menus
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sa-unit-fixture-', dir=SCRATCH) as tmp, ExitStack() as stack:
        for key, value in dict(USER_DIR=tmp, SAVES_DIR=tmp + '/saves',
                SETTINGS_PATH=tmp + '/settings.json', CAMPAIGN_PATH=tmp + '/campaign.json',
                BALANCE_PATH=tmp + '/balance.json').items():
            stack.enter_context(patch.object(menus, key, value))
        stack.enter_context(patch.object(DataStore, '_instance', None))
        for key in ('_selection', '_resolver', '_generation', '_coverage_report', '_coverage_generation'):
            stack.enter_context(patch.object(asset_selection, key, getattr(asset_selection, key)))
        ds = DataStore(balance={})  # never adopt the user's active balance/settings
        asset_selection.configure({'model_preview': True, 'visual_packs': []},
                                  asset_root=menus.ASSET_ROOT)
        yield ds


def inventory(ds):
    """Discover the exact shipped inventory and all declared authoritative routes."""
    rows = []
    for kind, catalogue in (('ship', ds.ships), ('station', ds.stations)):
        for unit_id, data in sorted(catalogue.items()):
            faction = data.faction if kind == 'ship' else 'imperial'
            if kind == 'ship':
                routes = [{'api': 'start_ship', 'builder': station,
                           'required_level': required_level(ds, station, unit_id)}
                          for station in sorted(ds.stations)
                          if unit_id in buildable_ship_ids(ds, station, faction)]
                binding = asset_selection._ship_binding(ds, unit_id, faction)
            else:
                if unit_id in BUILDING_TYPES:
                    routes = [{'api': 'start_building', 'builder': 'owned_colony'}]
                elif unit_id in SATELLITES:
                    routes = [{'api': 'start_satellite', 'builder': 'owned_colony'}]
                else:
                    routes = [{'api': 'start_station', 'builder': ship.id, 'faction': ship.faction}
                              for ship in sorted(ds.ships.values(), key=lambda x: x.id)
                              if ship.is_construction and not ship.can_colonize
                              and unit_id in ship.can_build_stations]
                binding = station_binding(unit_id, faction)
            rows.append(dict(kind=kind, id=unit_id, name=data.display_name,
                faction=faction if kind == 'ship' else 'shared', binding=binding,
                category=data.category if kind == 'ship' else 'station',
                can_colonize=bool(getattr(data, 'can_colonize', False)),
                is_construction=bool(getattr(data, 'is_construction', False)),
                classification='buildable' if routes else 'nonbuildable', routes=routes,
                test_scope='paid queue and completion' if routes else 'factory-only visual candidate'))
            variants = []
            for variant_faction in ([faction] if kind == 'ship' else sorted(ds.factions)):
                legal = [r for r in routes if r.get('faction', variant_faction) == variant_faction]
                variants.append(dict(faction=variant_faction,
                    classification='buildable' if legal else 'nonbuildable',
                    binding=binding if kind == 'ship' else station_binding(unit_id, variant_faction),
                    routes=legal, test_scope='paid queue and completion' if legal else 'factory-only visual candidate'))
            rows[-1]['variants'] = variants
    keys = [(r['kind'], r['id']) for r in rows]
    expected = {('ship', sid) for sid in ds.ships} | {('station', sid) for sid in ds.stations}
    assert len(keys) == len(set(keys)) and set(keys) == expected
    return rows


def fixture(ds, faction):
    st = GameState(seed=1827)
    st.players[0] = PlayerState(0, faction=faction, credits=1e8, materials=1e8,
        energy=1e8, crew=1e8, command_capacity=100000, researched=set(ds.techs))
    factory = UnitFactory(st)
    construction = ConstructionSystem(st)
    construction.factory = factory
    return st, factory, construction


def build_case(ds, row, faction):
    """Use actual paid APIs, observe exact debits, step update, inspect new entity."""
    st, factory, cs = fixture(ds, faction)
    unit_id = row['id']
    kind = row['kind']
    routes = [r for r in row['routes'] if r.get('faction', faction) == faction]
    if not routes:
        # Never counterfeit a paid build by using a foreign constructor. Keep the
        # visual candidate measurable while explicitly excluding it from paid totals.
        entity = (factory.spawn_station(unit_id, 0, Vec3()) if kind == 'station'
                  else factory.spawn_ship(unit_id, 0, Vec3()))
        binding = station_binding(unit_id, faction) if kind == 'station' else asset_selection.ship_binding(ds, unit_id, faction)
        mesh = asset_selection.mesh_for(binding)
        triangles = sum(len(faces) for faces in mesh.values()) if mesh is not None else 0
        return dict(faction=faction, classification='nonbuildable',
                    test_scope='factory-only visual candidate', passed=triangles > 0,
                    paid=False, queued=False, completed=False, binding=binding,
                    mesh_triangles=triangles, entity=dict(data_id=entity.data_id,
                    name=ds.unit_name(entity), kind=entity.kind, owner=entity.owner),
                    note='No legitimate builder/buildlist route for this faction')
    route = routes[0]
    result: dict = dict(faction=faction, route=route, classification='buildable',
                  test_scope='paid queue and completion', paid=False, queued=False,
                  completed=False, passed=False)
    try:
        if kind == 'ship':
            builder = factory.spawn_station(route['builder'], 0, Vec3())
            builder.upgrade_level = max(1, route['required_level'])
            cost = factory.ship_build_cost(unit_id)
            invoke = lambda: cs.start_ship(builder.id, unit_id, 0) == 1
        elif route['api'] in ('start_building', 'start_satellite'):
            builder = factory.spawn_planet(dict(id='audit-colony', type='temperate',
                                                pos=[0, 0, 0], radius=600))
            builder.colonized_by = 0
            cost = factory.station_build_cost(unit_id)
            invoke = (lambda: start_building(cs, builder.id, unit_id, 0)) if unit_id in BUILDING_TYPES else (
                lambda: cs.start_satellite(builder.id, unit_id, 0))
        else:
            builder = factory.spawn_ship(route['builder'], 0, Vec3())
            data = ds.stations[unit_id]
            for body_id, radius_range in data.requires_range.items():
                radius = 2200 if body_id == 'gas_giant' else 600
                body = factory.spawn_planet(dict(id='audit-' + body_id, type=body_id,
                                                 pos=[0, 0, 0], radius=radius))
                clear = _body_clearance(body, data.radius) if body_id != 'asteroid_field' else 0
                body.pos = Vec3(-clear - radius_range / 2, 0, 0)
            result['site_validation'] = list(cs.check_site(unit_id, Vec3(), builder))
            cost = factory.station_build_cost(unit_id)
            invoke = lambda: cs.start_station(builder.id, unit_id, Vec3(), 0)
        result['fixture'] = dict(resources='100000000 each', all_techs=True,
            builder_id=builder.data_id, yard_level=builder.upgrade_level,
            command_capacity=st.players[0].command_capacity)
        before_ids = set(st.entities)
        before = {r: getattr(st.players[0], r) for r in RESOURCES}
        accepted = invoke()
        after = {r: getattr(st.players[0], r) for r in RESOURCES}
        result['cost'] = cost
        result['resource_debits'] = {r: before[r] - after[r] for r in RESOURCES}
        result['paid'] = accepted and all(abs(result['resource_debits'][r] - cost.get(r, 0)) < 1e-7 for r in RESOURCES)
        result['queued'] = bool(accepted and len(builder.build_queue) == 1 and
            builder.build_queue[0]['item'] == unit_id and builder.build_queue[0]['status'] == 'paid')
        assert result['paid'], 'API rejected or resource debit mismatched'
        assert result['queued'], 'No matching real paid queue entry'
        result['queued_item'] = dict(builder.build_queue[0])
        total = builder.build_queue[0]['total']
        # No queue injection, direct _complete call or factory spawn of the target.
        # Oversized bounded dt exercises the ordinary authoritative completion dispatcher.
        cs.update(total * 100 + 1)
        born = [e for eid, e in st.entities.items() if eid not in before_ids]
        matching = [e for e in born if e.data_id == unit_id and e.owner == 0 and e.operational
                    and (e.is_station if kind == 'station' else e.is_ship or e.is_squadron)]
        result['completed'] = len(matching) == 1 and len(born) == 1 and not builder.build_queue
        assert result['completed'], 'Paid completion missing/wrong entity'
        entity = matching[0]
        result['entity'] = dict(id=entity.id, data_id=entity.data_id, kind=entity.kind,
            owner=entity.owner, name=ds.unit_name(entity), pos=list(entity.pos.to_tuple()),
            planet_id=entity.planet_id, satellite_slot=entity.satellite_slot,
            planet_building_slot=entity.planet_building_slot)
        binding = (station_binding(entity.data_id, faction) if kind == 'station'
                   else asset_selection.ship_binding(ds, entity.data_id, faction))
        result['binding'] = binding
        mesh = asset_selection.mesh_for(binding)
        result['mesh_triangles'] = sum(len(faces) for faces in mesh.values()) if mesh is not None else 0
        assert binding and result['mesh_triangles'] > 0, 'Missing authored CPU mesh binding'
        result['passed'] = True
    except Exception as exc:
        result['failure'] = f'{type(exc).__name__}: {exc}'
        result['traceback'] = traceback.format_exc()
    return result


def audit_catalogue(output=DEFAULT_OUTPUT):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with isolated_catalogue() as ds:
        rows = inventory(ds)
        expected = Counter(kind for kind, _ in [('ship', k) for k in ds.ships] + [('station', k) for k in ds.stations])
        (output / 'manifest.json').write_text(json.dumps(dict(
            expected_counts=dict(expected), inventory_count=len(rows), rows=rows), indent=2) + '\n')
        failures = []
        for row in rows:
            factions = [row['faction']] if row['kind'] == 'ship' else sorted(ds.factions)
            row['cases'] = []
            for faction in factions:
                case = build_case(ds, row, faction)
                row['cases'].append(case)
                if not case['passed']:
                    failures.append(dict(kind=row['kind'], id=row['id'], faction=faction,
                                         failure=case.get('failure')))
            assert {c['faction'] for c in row['cases']} == {v['faction'] for v in row['variants']}
            assert len(row['cases']) == len(row['variants'])
            # Checkpoint after every catalogue row; partial progress survives a deadline.
            (output / 'rows.partial.json').write_text(json.dumps(rows, indent=2) + '\n')
        keys = {(r['kind'], r['id']) for r in rows}
        assert len(keys) == len(rows) == len(ds.ships) + len(ds.stations)
        report = dict(scope='CPU only: paid construction and authored mesh resolution; NOT native visibility',
            inventory_count=len(rows), result_count=len(keys), expected_counts=dict(expected),
            classification_counts=dict(Counter(r['classification'] for r in rows)),
            variant_count=sum(len(r['cases']) for r in rows),
            paid_cases=sum(c['classification'] == 'buildable' for r in rows for c in r['cases']),
            passed_paid_cases=sum(c['classification'] == 'buildable' and c['passed'] for r in rows for c in r['cases']),
            factory_only_visual_cases=sum(c['classification'] != 'buildable' for r in rows for c in r['cases']),
            passed_cases=sum(c['passed'] for r in rows for c in r['cases']),
            buildlist_gaps=[dict(kind=r['kind'], id=r['id'], faction=c['faction'],
                                classification=c['classification'], test_scope=c['test_scope'])
                            for r in rows for c in r['cases'] if c['classification'] != 'buildable'],
            failures=failures, rows=rows,
            supplemental_non_catalogue=[dict(kind='ship', id='trade_convoy',
                classification='auto-spawned', test_scope='factory-only visual candidate',
                note='TradingSystem mints this dataless entity; deliberately outside DataStore census')])
        (output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--deadline', type=int, default=180)
    args = parser.parse_args()
    def deadline(signum, frame):
        raise TimeoutError('CPU audit deadline exceeded; inspect rows.partial.json')
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(args.deadline)
    try:
        report = audit_catalogue(args.output)
        print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, indent=2))
        print('Manifest:', args.output / 'manifest.json')
        print('Results:', args.output / 'results.json')
        return int(bool(report['failures']))
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    raise SystemExit(main())
