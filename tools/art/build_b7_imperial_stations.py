#!/usr/bin/env python3
"""Initial-only B7 Imperial station seeds; editable blend masters, never an exporter.

Blender --background --python tools/art/build_b7_imperial_stations.py -- --all
Existing selected masters are refused transactionally before Blender import.
No approval, registration, activation, runtime export or gameplay changes.
"""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')
# Each measured legacy box is independent: X/Y/Z pairs, not a shared station box.
_SPECS = (
    ('command_station', ((-62.,62.),(-8.,55.),(-62.,62.)), 'Tiered cruciform fortress with a central command keep and four armoured bastions'),
    ('shipyard', ((-43.65,43.65),(-10.,34.225),(-45.,55.507)), 'Open axial slipway between twin deep fabrication walls and a rear gantry'),
    ('research_station', ((-60.925626,60.925626),(-15.,40.305438),(-41.526279,64.)), 'Three separated laboratory drums on a triangular spoke hub with a forward instrument boom'),
    ('defense_platform', ((-44.258609,44.258609),(-13.5,21.),(-44.258609,44.258609)), 'Low octagonal fortress with four diagonal armoured twin-barrel batteries'),
    ('mining_station', ((-39.,39.),(-54.,41.),(-28.,35.507)), 'Tall ore refinery with descending extractor shaft, paired crushers and conveyor shoulders'),
    ('sensor_station', ((-37.,37.),(-23.,62.355496),(-30.387721,30.387721)), 'Narrow watchtower carrying a broad open aperture array and two side receivers'),
    ('trade_station', ((-63.53675,63.53675),(-8.605,51.5),(-63.53675,63.53675)), 'Square annular customs concourse enclosing a void with four outward docking piers'),
    ('fighter_platform', ((-33.,33.),(-11.5,53.5),(-42.,44.)), 'Stacked forward hangar shelves beneath an offset flight-control tower'),
    ('repair_dock', ((-34.5,34.5),(-20.,29.),(-42.5,42.5)), 'Open ventral service cradle with transverse ribs and unequal overhead repair arms'),
    ('energy_relay', ((-41.736688,41.736688),(-20.5,38.),(-28.,46.75)), 'Twin capacitor banks on a narrow spine feeding a tall forward induction hoop'),
)
ROWS = {'imperial:' + kind: dict(identifier='imperial_' + kind, data_id=kind,
        gameplay_entity=kind, faction='imperial', station_kind=kind, authority='blend',
        limits=limits, builder='build_' + kind, design=design)
        for kind, limits, design in _SPECS}


def fit_points(points, limits):
    """Affine fit each asymmetric side; input points are never mutated."""
    points = [tuple(p) for p in points]
    low = [min(p[i] for p in points) for i in range(3)]
    span = [max(p[i] for p in points) - low[i] for i in range(3)]
    if any(s <= 0 for s in span):
        raise ValueError('station geometry must span all three axes')
    return [tuple(a + (p[i] - low[i]) * (b - a) / span[i]
                  for i, (a, b) in enumerate(limits)) for p in points]


def dress(p, anchors):
    """Readable manufactured panels, service trenches and six explicit face roles.

    Anchors lie on structural decks; no post-hoc material classification.
    """
    for k, (x, y, z) in enumerate(anchors):
        p(f'Panel {k}', 'base', (13, 2, 14), (x,y,z))
        p(f'Trench {k}', 'dark', (9, 1, 10), (x,y+1,z))
        for side in (-1, 1):
            p(f'Raised armour {k} {side}', 'base', (3, 2, 14), (x+side*5,y+2,z))
            p(f'Edge strap {k} {side}', 'trim', (2, 1, 14), (x+side*6,y+3,z))
        for j in range(3):
            p(f'Vent slat {k} {j}', 'cool', (8, 1, 1.5), (x,y+2,z-3+j*3))
        p(f'Hazard panel {k}', 'accent', (10, 1, 2), (x,y+2,z+6))
        p(f'Window strip {k}', 'lit', (8, 1, 1.5), (x,y+2,z-6))


def build_command_station(p, c, r):
    p('Fortress east west', 'base', (108,18,32), (0,0,0))
    p('Fortress north south', 'base', (32,18,108), (0,0,0))
    for level, width in enumerate((46,34,24)):
        p(f'Command tier {level}', 'base', (width,14,width), (0,14+level*12,0))
        p(f'Tier cornice {level}', 'trim', (width+2,3,width+2), (0,21+level*12,0))
    for x,z in ((-42,0),(42,0),(0,-42),(0,42)):
        c('Bastion', 'base', (x,6,z), 18, 24, 'Y', 8)
    dress(p, [(x,19,z) for x,z in ((-42,0),(42,0),(0,-42),(0,42),(-9,0),(9,0))])


def build_shipyard(p, c, r):
    p('Rear gantry', 'base', (86,12,15), (0,4,-38))
    for s in (-1,1):
        p('Fabrication wall', 'base', (19,32,90), (s*34,4,0))
        for z in (-28,0,28):
            p('Hangar recess', 'dark', (2,20,20), (s*24,5,z))
            p('Work bridge', 'trim', (16,5,8), (s*23,14,z))
    dress(p, [(s*34,21,z) for s in (-1,1) for z in (-28,0,28)])


def build_research_station(p, c, r):
    c('Research hub', 'base', (0,0,0), 21, 22, 'Y', 12)
    anchors = []
    for k in range(3):
        a = k*2*math.pi/3
        x,z = 40*math.sin(a),40*math.cos(a)
        beam = p('Laboratory spoke', 'trim', (12,12,43), (x/2,0,z/2))
        beam.rotation_euler[1] = a
        c('Laboratory drum', 'base', (x,6,z), 17, 30, 'Y', 16)
        c('Lab roof collar', 'trim', (x,21,z), 18, 3, 'Y', 16)
        anchors.extend(((x-5,23,z),(x+5,23,z)))
    p('Instrument boom', 'dark', (6,8,30), (0,3,60))
    dress(p, anchors)


def build_defense_platform(p, c, r):
    c('Octagonal armour raft', 'base', (0,0,0), 40, 18, 'Y', 8)
    for x in (-25,25):
        for z in (-25,25):
            c('Battery collar', 'trim', (x,8,z), 13, 7, 'Y', 12)
            p('Turret armour', 'base', (20,12,19), (x,14,z))
            for dx in (-4,4):
                c('Weapon barrel', 'dark', (x+dx,15,z+12), 2.5, 23, 'Z', 12)
    dress(p, [(x,10,z) for x,z in ((-22,0),(22,0),(0,-22),(0,22),(-8,0),(8,0))])


def build_mining_station(p, c, r):
    p('Refinery spine', 'base', (28,64,32), (0,0,0))
    c('Extractor shaft', 'dark', (0,-42,0), 12, 40, 'Y', 16)
    c('Extractor cutting collar', 'trim', (0,-59,0), 16, 7, 'Y', 16)
    for s in (-1,1):
        p('Ore conveyor', 'trim', (32,10,18), (s*22,0,0))
        p('Crusher block', 'base', (24,28,42), (s*32,8,0))
        c('Smelter tower', 'base', (s*32,31,-10), 9, 20, 'Y', 12)
    dress(p, [(x,23,z) for x in (-32,32) for z in (-12,0,12)])


def build_sensor_station(p, c, r):
    p('Watchtower pedestal', 'base', (42,16,36), (0,-13,0))
    p('Array mast', 'base', (18,63,18), (0,17,0))
    r('Open receiving aperture', 'trim', 0,43, ((-4,32,25),(4,32,25)), 32)
    p('Array crossbar', 'dark', (62,5,7), (0,43,0))
    for s in (-1,1):
        c('Side receiver', 'base', (s*27,0,0), 11, 18, 'Z', 16)
    dress(p, [(x,-4,z) for x in (-13,13) for z in (-10,0,10)])


def build_trade_station(p, c, r):
    for s in (-1,1):
        p('Concourse long side', 'base', (20,18,84), (s*36,0,0))
        p('Concourse cross side', 'base', (84,18,20), (0,0,s*36))
        p('Lateral docking pier', 'trim', (33,10,14), (s*55,-1,0))
        p('Axial docking pier', 'trim', (14,10,33), (0,-1,s*55))
    p('Customs tower', 'base', (23,44,23), (36,25,-36))
    dress(p, [(x,10,z) for x,z in ((-36,-24),(-36,0),(-36,24),(36,0),(36,24),(0,36))])


def build_fighter_platform(p, c, r):
    p('Aft hangar wall', 'base', (62,54,16), (0,15,-32))
    for y in (-9,9,27):
        p('Flight shelf', 'base', (62,6,72), (0,y,0))
        p('Hangar interior', 'dark', (52,12,4), (0,y+9,-22))
        for x in (-28,28):
            p('Shelf column', 'trim', (6,18,62), (x,y+8,0))
    p('Flight control tower', 'base', (18,21,22), (-20,44,-24))
    dress(p, [(x,31,z) for x in (-16,16) for z in (-12,6,24)])


def build_repair_dock(p, c, r):
    p('Ventral service keel', 'base', (24,12,88), (0,-18,0))
    for s in (-1,1):
        p('Service rail', 'base', (14,18,90), (s*29,-3,0))
    for z in (-32,0,32):
        p('Cradle rib', 'trim', (68,7,9), (0,-10,z))
        for s in (-1,1):
            p('Repair upright', 'base', (6,30,8), (s*29,18,z))
            p('Overhead tool arm', 'trim', (19 if s<0 else 11,5,8), (s*23,32,z))
    dress(p, [(s*29,7,z) for s in (-1,1) for z in (-26,0,26)])


def build_energy_relay(p, c, r):
    p('Power distribution spine', 'base', (24,20,82), (0,0,0))
    for s in (-1,1):
        p('Capacitor bus', 'trim', (30,8,60), (s*18,0,0))
        for z in (-22,0,22):
            c('Capacitor housing', 'base', (s*27,8,z), 12, 27, 'Y', 16)
            c('Capacitor terminal', 'cool', (s*27,22,z), 8, 3, 'Y', 12)
    r('Induction hoop', 'trim', 0,22, ((35,26,19),(42,26,19)), 24)
    p('Induction support', 'dark', (12,28,12), (0,13,35))
    dress(p, [(s*27,25,z) for s in (-1,1) for z in (-22,0,22)])


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--all', action='store_true')
    choice.add_argument('--asset', choices=tuple(ROWS))
    parser.add_argument('--replace-seed', action='store_true')
    parser.add_argument('--preflight-only', action='store_true')
    return parser.parse_args(argv)


def preflight(args):
    keys = list(ROWS) if args.all else [args.asset]
    existing = [ROOT / f"art/blender/{ROWS[k]['identifier']}.blend" for k in keys
                if (ROOT / f"art/blender/{ROWS[k]['identifier']}.blend").exists()]
    if existing and not args.replace_seed:
        raise ValueError('editable master exists: ' + ', '.join(p.name for p in existing)
                         + '; --replace-seed destroys edits; export existing masters instead')
    return keys


def bake_fit_and_check(bpy, row):
    graph = bpy.context.evaluated_depsgraph_get()
    objects = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    for obj in objects:
        baked = bpy.data.meshes.new_from_object(obj.evaluated_get(graph), depsgraph=graph)
        for vertex in baked.vertices:
            vertex.co = obj.matrix_world @ vertex.co
        obj.modifiers.clear()
        obj.data = baked
        obj.matrix_world.identity()
    vertices = [v for obj in objects for v in obj.data.vertices]
    for vertex, point in zip(vertices, fit_points([v.co for v in vertices], row['limits'])):
        vertex.co = point
    roles = dict.fromkeys(ROLES, 0)
    for obj in objects:
        obj.data.update()
        obj.data.calc_loop_triangles()
        roles[obj['engine_material_role']] += len(obj.data.loop_triangles)
    measured = [[min(v.co[i] for v in vertices) for i in range(3)],
                [max(v.co[i] for v in vertices) for i in range(3)]]
    assert 1800 < sum(roles.values()) <= 11500, roles
    assert len(vertices) <= 8000, len(vertices)
    assert all(roles.values()), roles
    assert all(abs(measured[j][i]-row['limits'][i][j]) < .001 for i in range(3) for j in range(2))
    print('AUTHORING_GEOMETRY', json.dumps(dict(identifier=row['identifier'], bounds=measured,
          triangles=sum(roles.values()), vertices=len(vertices), roles=roles)))
    return measured


def main(argv=None):
    if argv is None:
        argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args = arguments(argv)
    try:
        keys = preflight(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.preflight_only:
        print(f'PREFLIGHT_OK targets={len(keys)}')
        return 0
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from alliance_common import plate, cylinder, annulus, weld_scene
    import bpy
    for key in keys:
        row = ROWS[key]
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        globals()[row['builder']](plate, cylinder, annulus)
        bpy.context.view_layer.update()
        weld_scene()
        bpy.context.view_layer.update()
        bounds = bake_fit_and_check(bpy, row)
        scene = bpy.context.scene
        scene['asset'], scene['authority'], scene['binding'] = row['identifier'], 'blend', key
        scene['design'] = row['design']
        scene['coordinates'] = 'X beam; Y up; +Z forward'
        scene['review'] = 'pending_owner_appearance_approval; no runtime registration'
        scene['features_json'] = json.dumps(dict(binding=key, faction='imperial', asset_class='station',
            authority='blend', design=row['design'], original_design=True, measured_envelope=bounds,
            material_roles=list(ROLES), seed_recipe='tools/art/build_b7_imperial_stations.py',
            approval='pending_owner_appearance_approval', provenance='Original geometry; no external assets'))
        master = ROOT / f"art/blender/{row['identifier']}.blend"
        master.parent.mkdir(parents=True, exist_ok=True)
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(master), compress=True)
        print(f'SEED_OK {key} -> {master.name}; authority=blend')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
