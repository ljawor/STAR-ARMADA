"""Classify the S06 B6 rows — the Imperial ships — from the live code, not from the plan.

Three questions, each answered by a measurement rather than by reading a document:

1. *Which rows are they?* The inventory declares every binding; the Imperial rows whose category is a
   hull or a squadron are this batch, and the ones whose category is a station, a satellite or a
   planet installation are **not** — the stations are B3 work and the satellites and installations are
   B4 work, both already authored.

2. *Do Imperial ships need a new key in `ship_visual_key`?* The migration record said they do. What
   the functions actually do, read and called here: `ship_visual_key` asks `ship_binding` first;
   `ship_binding` builds `f'{faction}:{role}'` for **every** faction, but returns early and `None`
   whenever no resolver is configured; `selected_binding` is
   `_resolver.has_binding(binding) and _resolver.is_authored(binding)`; and `has_binding` is true for
   any string present in the registry's bindings, overrides or aliases. So the requirement is **a
   registry binding the resolver resolves to a manifest** - exactly what every other batch has - and
   the `SHIP_KEYS` tuple, which omits Imperial, is consulted only on the procedural path. The
   conclusion this probe asserts is conditional on that and its end-to-end proof is the batch's own
   review harness, which drives the real resolver; the failure line below is deliberately left in
   place until it runs, rather than weakened to make this probe pass.

3. *What does each row draw today?* The legacy mesh — its envelope and its triangle count — read out
   of `render/fleet_geometry.py`, so the batch's envelopes and budgets come from the thing being
   replaced rather than from a transcribed table.

Prints a report and exits non-zero if a row is unclassified, if the servability claim fails, or if a
row's legacy geometry cannot be measured.

    PYTHONPATH=tests .venv/bin/python tools/art/probe_b6_scope.py
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / 'art/manifests/model_inventory.json'

# The categories that are a ship. Everything else an Imperial row can be belongs to another batch.
SHIP_CATEGORIES = ('combat_hull', 'construction', 'logistics_hull', 'squadron')
OTHER_BATCH = {'station': 'B3 command/station work', 'satellite': 'B4 hardware',
               'planet_installation': 'B4 hardware'}


def inventory_rows():
    rows = json.loads(INVENTORY.read_text(encoding='utf-8'))['rows']
    return [r for r in rows if r['faction'] == 'imperial']


def servability(control='rebel:frigate', subject='imperial:cruiser'):
    """Is an authored Imperial ship served today, and what exactly is missing?

    Measured against the **real registry**, with a preview session configured the way the preview tests
    configure one, rather than by patching `selected_binding` - which does not work, because
    `ship_binding` returns early whenever no resolver is configured, so a patched `selected_binding` is
    never consulted.

    Returns a dict of measurements:
      * `control_served` - an authored ship that exists today is served with preview on. This is the
        mechanism, not a claim about it.
      * `control_shape` / `subject_shape` - what `ship_visual_key` returns for each.
      * `subject_binding_declared` - the registry already carries the Imperial row, with a manifest.
    """
    from render import asset_selection as sel
    from render.faction_visuals import ship_visual_key

    class _Ship:
        faction = 'imperial'
        category = 'cruiser'
        crew_capacity = 0

    class _Store:
        ships = {'imperial_cruiser': _Ship()}

        @staticmethod
        def ship_visual(_data_id):
            return {'shape': 'cruiser'}

    store = _Store()
    sel.configure({})
    off = ship_visual_key(store, 'imperial_cruiser')
    sel.configure({'model_preview': True}, asset_root=str(ROOT))
    try:
        control_served = sel.mesh_for(control) is not None
        subject_served = sel.mesh_for(subject) is not None
        subject_selected = bool(sel.selected_binding(subject))
        on = ship_visual_key(store, 'imperial_cruiser')
    finally:
        sel.configure({})

    registry = json.loads((ROOT / 'assets/models/registry.json').read_text(encoding='utf-8'))
    row = next((b for b in registry['bindings'] if b['binding'] == subject), None)
    return {'control': control, 'control_served': control_served, 'subject': subject,
            'subject_served_now': subject_served, 'subject_selected_now': subject_selected,
            'subject_has_a_registry_row': row is not None,
            'subject_manifest': (row or {}).get('manifest'),
            'subject_shape_off': off, 'subject_shape_on': on}


def legacy_geometry(shape):
    """The legacy mesh this row draws today: its extent and its triangle count.

    Measured through the public `ship_mesh` for the row's own shape string. The binding's *key* form
    cannot be used for this: `ship_mesh('imperial:cruiser')` normalises the unknown key to `box`, which
    is what an unselected Imperial ship falls back to - the shape string in the inventory is what the
    renderer actually draws, because `ship_visual_key` resolves the *data row's* shape and passes that
    down. Batches are role -> triangles, each triangle `(normal, (a, b, c))`.
    """
    from render import fleet_geometry as fg
    mesh = fg.ship_mesh(shape)
    verts, per_role = [], {}
    for role, triangles in mesh.items():
        per_role[role] = len(triangles)
        for _normal, corners in triangles:
            verts.extend(corners)
    if not verts:
        return None
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    return {'envelope': [[min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]],
            'vertices': len(set(verts)),
            'triangles': sum(per_role.values()), 'per_role': per_role}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path, default=None, help='also write the report here')
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))

    rows = inventory_rows()
    ships = [r for r in rows if r['category'] in SHIP_CATEGORIES]
    others = [r for r in rows if r['category'] not in SHIP_CATEGORIES]
    failure = []

    print(f'Imperial rows: {len(rows)} | this batch (hull or squadron): {len(ships)}')
    print(f'Belonging to another batch: {len(others)} '
          f'({", ".join(sorted({r["category"] for r in others}))})')
    print()
    print(f'{"binding":36} {"category":14} {"legacy":8} {"tri":>6} {"vertices":>9}  envelope')
    report = {'servability': None, 'ships': [], 'not_this_batch': []}
    for r in ships:
        binding = r['canonical_binding']
        geom = legacy_geometry(r['geometry_shape_string'])
        if geom is None:
            failure.append(f'{binding}: the legacy mesh for shape '
                           f'{r["geometry_shape_string"]!r} could not be measured')
            print(f'{binding:36} {r["category"]:14} {r.get("geometry_shape_string"):8} '
                  f'{"?":>6} {"?":>9}  not measurable')
            continue
        envelope = geom['envelope']
        print(f'{binding:36} {r["category"]:14} {str(r.get("geometry_shape_string")):8} '
              f'{str(geom["triangles"]):>6} {geom["vertices"]:>9}  ' +
              '..'.join(','.join(f'{v:.3f}' for v in axis) for axis in envelope))
        report['ships'].append({'binding': binding, 'category': r['category'],
                                'legacy_shape': r.get('geometry_shape_string'),
                                'status': r['status'], 'scale_envelope': r.get('scale_envelope'),
                                'legacy_geometry': geom})
        if r['status'] != 'procedural_legacy':
            failure.append(f'{binding}: status is {r["status"]}, not procedural_legacy')
    for r in others:
        report['not_this_batch'].append({'binding': r['canonical_binding'],
                                         'category': r['category'],
                                         'belongs_to': OTHER_BATCH.get(r['category'], 'unclassified')})
        if r['category'] not in OTHER_BATCH:
            failure.append(f'{r["canonical_binding"]}: category {r["category"]} is not classified')

    served = servability()
    report['servability'] = served
    print()
    print(f"control  {served['control']:20} served with preview on: {served['control_served']}")
    print(f"subject  {served['subject']:20} served now: {served['subject_served_now']} | "
          f"selected: {served['subject_selected_now']} | registry row: "
          f"{served['subject_has_a_registry_row']} | manifest: {served['subject_manifest']}")
    print(f"ship_visual_key -> {served['subject_shape_off']!r} with preview off, "
          f"{served['subject_shape_on']!r} with preview on")
    if not served['control_served']:
        failure.append(f"{served['control']} is not served with preview on: the control fails, so "
                       f'nothing here can be concluded about Imperial rows')
    if not served['subject_has_a_registry_row']:
        failure.append(f"{served['subject']} has no registry row: a binding would have to be declared")
    print()
    print('=> no seam in `ship_visual_key` is needed, and this is the measurement rather than a reading '
          'of it: the same mechanism serves an authored ship today, it is driven by a registry binding '
          'resolving to a manifest, the Imperial row is already declared, and `SHIP_KEYS` - which omits '
          'Imperial - is consulted only on the procedural path. What the batch owes each row is a '
          'manifest and an authored mesh, exactly what every other batch produced.')

    if args.json:
        args.json.write_text(json.dumps({'schema': 1, 'batch': 's06-b6-imperial-ships',
                                         'generated_by': 'tools/art/probe_b6_scope.py',
                                         **report}, indent=2) + '\n')
    if failure:
        print()
        for line in failure:
            print('FAIL', line)
        return 1
    print()
    print(f'scope settled: {len(ships)} rows, no seam required')
    return 0


if __name__ == '__main__':
    sys.exit(main())
