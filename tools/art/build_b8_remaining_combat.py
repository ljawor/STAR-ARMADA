#!/usr/bin/env python3
"""B8 initial seeds: original twin-prong industrial and asymmetric salvage hulls.

After seeding, editable .blend masters are authoritative. No export, registration,
approval or activation. Existing masters are refused before Blender import.
Use Blender --background --python this_file.py -- --all (or --asset binding).
X beam; Y up; +Z forward. Shared alliance_common helpers are unchanged.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')
ROWS = {'confederacy:corvette': {'identifier': 'confed_corvette',
                          'data_id': 'confed_corvette',
                          'faction': 'confederacy',
                          'envelope': [[-31.713844, -7.0, -38.49], [31.713844, 15.1, 48.06775]],
                          'gameplay_entity': 'confed_corvette',
                          'rank': 0,
                          'width': 14,
                          'spread': 19,
                          'bow': 30,
                          'engines': 2,
                          'design': 'Compact twin-prong patrol hammer with a transverse stern '
                                    'drive block',
                          'authority': 'blend',
                          'asset_class': 'combat_hull'},
 'confederacy:frigate': {'identifier': 'confed_frigate',
                         'data_id': 'confed_frigate',
                         'faction': 'confederacy',
                         'envelope': [[-48.070766, -8.5, -60.475], [48.070766, 15.1, 72.56775]],
                         'gameplay_entity': 'confed_frigate',
                         'rank': 1,
                         'width': 11,
                         'spread': 22,
                         'bow': 38,
                         'engines': 3,
                         'design': 'Long split-rail escort with narrow parallel forward gun prongs',
                         'authority': 'blend',
                         'asset_class': 'combat_hull'},
 'confederacy:cruiser': {'identifier': 'confed_cruiser',
                         'data_id': 'confed_cruiser',
                         'faction': 'confederacy',
                         'envelope': [[-75.392305, -10.0, -80.31], [75.392305, 15.655, 94.61775]],
                         'gameplay_entity': 'confed_cruiser',
                         'rank': 2,
                         'width': 17,
                         'spread': 29,
                         'bow': 30,
                         'engines': 4,
                         'design': 'Broad shouldered twin-prong cruiser with armoured wing '
                                   'batteries',
                         'authority': 'blend',
                         'asset_class': 'combat_hull'},
 'confederacy:battleship': {'identifier': 'confed_battleship',
                            'data_id': 'confed_battleship',
                            'faction': 'confederacy',
                            'envelope': [[-109.856406, -14.0, -129.825],
                                         [109.856406, 49.5, 138.05575]],
                            'gameplay_entity': 'confed_battleship',
                            'rank': 3,
                            'width': 20,
                            'spread': 27,
                            'bow': 42,
                            'engines': 5,
                            'design': 'Double-deck industrial battleship with deep fork and four '
                                      'broadside casemates',
                            'authority': 'blend',
                            'asset_class': 'combat_hull'},
 'confederacy:supercapital': {'identifier': 'confed_supercapital',
                              'data_id': 'confed_supercapital',
                              'faction': 'confederacy',
                              'envelope': [[-147.0, -29.605, -178.825], [147.0, 49.5, 187.05575]],
                              'gameplay_entity': 'confed_supercapital',
                              'rank': 4,
                              'width': 23,
                              'spread': 34,
                              'bow': 48,
                              'engines': 6,
                              'design': 'Fortress carrier with twin heavy prongs, stepped command '
                                        'citadel and outboard hangars',
                              'authority': 'blend',
                              'asset_class': 'combat_hull'},
 'syndicate:corvette': {'identifier': 'syndicate_corvette',
                        'data_id': 'syndicate_corvette',
                        'faction': 'syndicate',
                        'envelope': [[-22.36926, -9.0, -44.025], [30.672491, 44.0, 38.4]],
                        'gameplay_entity': 'syndicate_corvette',
                        'rank': 0,
                        'width': 12,
                        'spread': 19,
                        'bow': 28,
                        'engines': 2,
                        'design': 'Offset salvage cutter with one long gun spine and short port '
                                  'engine pod',
                        'authority': 'blend',
                        'asset_class': 'combat_hull'},
 'syndicate:frigate': {'identifier': 'syndicate_frigate',
                       'data_id': 'syndicate_frigate',
                       'faction': 'syndicate',
                       'envelope': [[-31.829605, -9.0, -70.51], [43.872131, 44.0, 62.4]],
                       'gameplay_entity': 'syndicate_frigate',
                       'rank': 1,
                       'width': 13,
                       'spread': 22,
                       'bow': 40,
                       'engines': 3,
                       'design': 'Asymmetric raider with high salvage tower and starboard freight '
                                 'sponson',
                       'authority': 'blend',
                       'asset_class': 'combat_hull'},
 'syndicate:cruiser': {'identifier': 'syndicate_cruiser',
                       'data_id': 'syndicate_cruiser',
                       'faction': 'syndicate',
                       'envelope': [[-42.463847, -11.02, -94.395], [58.551844, 44.0, 84.0]],
                       'gameplay_entity': 'syndicate_cruiser',
                       'rank': 2,
                       'width': 18,
                       'spread': 29,
                       'bow': 36,
                       'engines': 4,
                       'design': 'Salvage arsenal cruiser with unequal broadside stacks and '
                                 'exposed dorsal machinery',
                       'authority': 'blend',
                       'asset_class': 'combat_hull'}}


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--all', action='store_true')
    selection.add_argument('--asset', choices=tuple(ROWS))
    parser.add_argument('--replace-seed', action='store_true')
    return parser.parse_args(argv)


def preflight(args):
    keys = list(ROWS) if args.all else [args.asset]
    existing = [ROOT / f"art/blender/{ROWS[k]['identifier']}.blend" for k in keys
                if (ROOT / f"art/blender/{ROWS[k]['identifier']}.blend").exists()]
    if existing and not args.replace_seed:
        raise ValueError('REFUSE existing editable master: ' + ', '.join(map(str, existing))
                         + '; export existing .blend; --replace-seed destroys edits')
    return keys


def ship_parts(row, plate, cylinder, loft):
    """Class-specific structural assemblies; large readable parts, not surface noise."""
    rank, w, spread, bow = (row[k] for k in ('rank', 'width', 'spread', 'bow'))
    confed = row['faction'] == 'confederacy'
    offset = 0 if confed else 7
    loft('01 Pressure hull', 'base', ((-42,w*.8,8,-8),(-27,w,10,-10),
         (2,w,10,-9),(18,w*.6,7,-6)), 0, (offset,0,0))
    plate('02 Stern crossmember', 'dark', (spread*2+18,16,16), (offset,0,-31))
    plate('03 Ventral keel', 'dark', (w,5,58), (offset,-10,-12))
    for side in (-1,1):
        for k in range(3):
            plate(f'04 Spine service armour {side} {k}', 'base', (7,2,5),
                  (offset+side*6,11,-24+k*7))
    # Confederacy: genuine negative-space fork, joined only abaft the throat.
    # Syndicate: unequal sidecar hulls, one elongated gun spine and one stub pod.
    for side in (-1,1):
        reach = bow if confed else (bow if side == 1 else 10+rank*3)
        x = offset + side*spread
        pw = (7+rank*1.8) if confed else (8+rank*2 if side==1 else 11)
        loft(f'10 Armoured prong {side}', 'base',
             ((-33,pw,8,-7),(-15,pw,10,-8),(reach-8,pw*.85,7,-6),
              (reach,pw*.48,5,-4)), 0, (x,0,0))
        plate(f'11 Prong root {side}', 'trim', (spread,6,14),
              (offset+side*spread*.5,2,-19))
        for k in range(4+rank):
            z = -24 + k*(reach+15)/(3+rank)
            plate(f'12 Prong armour {side} {k}', 'base', (pw*1.8,3,6), (x,10,z))
            plate(f'13 Hazard band {side} {k}', 'accent', (pw*1.5,1.5,2), (x,12,z))
            plate(f'14 Inset vent {side} {k}', 'dark', (2,7,5), (x+side*pw,1,z))
        cylinder(f'15 Forward battery {side}', 'dark', (x,1,reach), pw*.5,8,'Z',12)
        cylinder(f'16 Battery collar {side}', 'trim', (x,1,reach+2),pw*.56,2,'Z',12)
    # Command superstructure is seated on the central aft deck.
    tower_x = offset if confed else offset-6
    levels = 1 + (rank//2 if confed else rank+1)
    for k in range(levels):
        plate(f'20 Citadel tier {k}', 'base', (w*1.2-k*2,8,18-k*2),
              (tower_x,13+k*7,-14))
        plate(f'21 Command visor {k}', 'lit', (w-k*2,2,2),
              (tower_x,15+k*7,-5+k))
    for side in (-1,1):
        for k in range(4):
            plate(f'22 Heat bank {side} {k}', 'cool', (w*.45,2,4),
                  (offset+side*w*.6,11,-26+k*7))
    for k in range(row['engines']):
        x = offset+(k-(row['engines']-1)/2)*9
        cylinder(f'30 Drive housing {k}', 'dark', (x,0,-40),5,14,'Z',12)
        cylinder(f'31 Drive collar {k}', 'trim', (x,0,-45),5.4,3,'Z',12)
        cylinder(f'32 Drive aperture {k}', 'lit', (x,0,-47),4,1,'Z',12)
    if confed and rank>=2:
        # Cruiser wing batteries; battleship stacked casemates; supercapital hangars.
        for side in (-1,1):
            for k in range(rank-1):
                x = side*(spread+9)
                z = -24+k*13
                plate(f'40 Broadside shoulder {side} {k}', 'base', (18,13,15),(x,0,z))
                plate(f'41 Broadside recess {side} {k}', 'dark', (2,8,10),(x+side*9,0,z))
                plate(f'42 Broadside lintel {side} {k}', 'trim', (4,3,12),(x+side*8,5,z))
                if rank==4:
                    plate(f'43 Hangar light {side} {k}', 'lit', (2,2,9),(x+side*10,3,z))
        if rank>=3:
            plate('44 Raised industrial deck', 'base', (w*1.6,8,30),(0,13,-5))
            plate('45 Deck axial trench', 'dark', (6,2,28),(0,18,-5))
    if not confed:
        # Salvaged machinery on one side only; class changes module count and height.
        for k in range(2+rank):
            x,z = offset+spread+5,-20+k*12
            plate(f'50 Salvage rack {k}', 'trim', (18,6,11),(x,11,z))
            cylinder(f'51 Exposed reactor drum {k}', 'dark',(x,17,z),6,10,'Z',12)
            plate(f'52 Salvaged cover {k}', 'accent',(10,2,7),(x,23,z))
        plate('53 Unequal port radiator', 'cool',(3,18+rank*8,20),
              (offset-spread-7,12,-12))
        plate('54 Radiator support', 'trim',(12,5,20),(offset-spread-3,6,-12))
        if rank==2:
            loft('55 Arsenal outrigger', 'base', ((-22,10,5,-6),(0,10,7,-6),
                 (20,5,5,-4)),0,(offset-spread-8,-4,0))
            plate('56 Arsenal saddle', 'trim',(24,5,22),(offset-spread,-1,-5))


def fit_coordinate(value, source_low, source_high, low, high):
    """Round into Blender float32 storage without crossing either target bound."""
    import struct
    def f32(number):
        return struct.unpack('f', struct.pack('f', number))[0]
    fitted = f32(low + (value-source_low) * (high-low) / (source_high-source_low))
    if fitted < low:
        fitted = f32(low + max(abs(low), 1.) * 2**-23)
    if fitted > high:
        fitted = f32(high - max(abs(high), 1.) * 2**-23)
    assert low <= fitted <= high
    return fitted


def bake_fit_and_check(bpy, row):
    """Fit EVALUATED assembled geometry independently on every axis and both sides.

    Bake bevels/transforms before measuring; never infer extents from part centres.
    This is authoring-space fit, not a gameplay size/radius change. No exporter used.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    objects = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        baked = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
        matrix = obj.matrix_world.copy()
        for vertex in baked.vertices:
            vertex.co = matrix @ vertex.co
        obj.modifiers.clear()
        obj.data = baked
        obj.matrix_world.identity()
    points = [v.co for obj in objects for v in obj.data.vertices]
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    for p in points:
        for i, (low, high) in enumerate(zip(*row['envelope'])):
            assert hi[i] > lo[i]
            p[i] = fit_coordinate(p[i], lo[i], hi[i], low, high)
    triangles = {role: 0 for role in ROLES}
    unique = set()
    for obj in objects:
        obj.data.update()
        obj.data.calc_loop_triangles()
        triangles[obj['engine_material_role']] += len(obj.data.loop_triangles)
        unique.update(tuple(round(float(c), 6) for c in v.co) for v in obj.data.vertices)
    measured = [[min(p[i] for p in unique) for i in range(3)],
                [max(p[i] for p in unique) for i in range(3)]]
    for i, (low, high) in enumerate(zip(*row['envelope'])):
        assert abs(measured[0][i] - low) < 1e-3, (i, measured)
        assert abs(measured[1][i] - high) < 1e-3, (i, measured)
    total = sum(triangles.values())
    assert 1800 < total < 11888, total
    assert len(unique) < 9450, len(unique)
    assert all(triangles.values()), triangles
    print('AUTHORING_GEOMETRY', json.dumps(dict(identifier=row['identifier'],
          bounds=measured, triangles=total, vertices=len(unique), roles=triangles)))
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
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import bpy
    from alliance_common import plate, cylinder, loft, weld_scene
    for key in keys:
        row = ROWS[key]
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        ship_parts(row, plate, cylinder, loft)
        bpy.context.view_layer.update()
        weld_scene(tolerance=.12, grow_max=.8, min_half=.2, max_half=.7,
                   overlap=.04, max_brace=5, max_members=90)
        bpy.context.view_layer.update()
        measured = bake_fit_and_check(bpy, row)
        scene = bpy.context.scene
        scene['asset'] = row['identifier']
        scene['authority'] = 'blend'
        scene['binding'] = key
        scene['design'] = row['design']
        scene['coordinates'] = 'X beam; Y up; +Z forward'
        scene['review'] = 'pending_owner_appearance_approval; no runtime registration'
        scene['features_json'] = json.dumps(dict(binding=key, authority='blend',
            data_id=row['data_id'], faction=row['faction'], asset_class='combat_hull',
            original_design=True, design=row['design'], measured_envelope=measured,
            seed_recipe='tools/art/build_b8_remaining_combat.py', material_roles=list(ROLES),
            approval='pending_owner_appearance_approval',
            provenance='Original geometry; no external mesh or texture dependencies'), sort_keys=True)
        master = ROOT / f"art/blender/{row['identifier']}.blend"
        master.parent.mkdir(parents=True, exist_ok=True)
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(master), compress=True)
        print(f'SEED_OK {key} -> {master.name}; authority=blend')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
