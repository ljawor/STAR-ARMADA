#!/usr/bin/env python3
"""B9 initial authoring ONLY; never import this recipe for export.

Eight original hull silhouettes are blend-authoritative after seeding. The repeated
modular scaffold alone is script-authoritative. Uses unchanged alliance_common.
No export, registration or appearance approval is performed here. +Z is forward.
CLI: Blender --background --python this_file.py -- --all
     Blender --background --python this_file.py -- --asset rebel:constructor
Refuse every selected existing master before Blender import unless --replace-seed.
"""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')
ROWS = {'imperial:constructor': {'identifier': 'imperial_constructor',
                          'data_id': 'imperial_constructor',
                          'gameplay_entity': 'imperial_constructor',
                          'faction': 'imperial',
                          'asset_class': 'construction',
                          'authority': 'blend',
                          'limits': [[-20.0, 20.0], [-7.0, 26.5], [-24.6975, 24.35825]],
                          'design': 'Rectilinear armoured tug; paired forward articulated grapple arms and '
                                    'recessed fabrication bays',
                          'style': 'armoured',
                          'beam': 0.45,
                          'bridge': 0.28,
                          'arms': 2,
                          'bays': 4,
                          'canisters': 0,
                          'engines': 4},
 'imperial:colonizer': {'identifier': 'imperial_colonizer',
                        'data_id': 'imperial_colonizer',
                        'gameplay_entity': 'imperial_colonizer',
                        'faction': 'imperial',
                        'asset_class': 'construction',
                        'authority': 'blend',
                        'limits': [[-20.0, 20.0], [-7.0, 26.5], [-24.6975, 24.35825]],
                        'design': 'Armoured lander core with four habitat canisters in a deployable '
                                  'rectangular landing frame',
                        'style': 'armoured',
                        'beam': 0.48,
                        'bridge': 0.24,
                        'arms': 0,
                        'bays': 2,
                        'canisters': 4,
                        'engines': 4},
 'rebel:constructor': {'identifier': 'rebel_constructor',
                       'data_id': 'rebel_constructor',
                       'gameplay_entity': 'rebel_constructor',
                       'faction': 'rebel',
                       'asset_class': 'construction',
                       'authority': 'blend',
                       'limits': [[-25.0, 25.0], [-7.0, 32.451235], [-38.455, 35.5]],
                       'design': 'Forked salvage tender with swept shoulders, twin long manipulator arms and '
                                 'broad workshop bays',
                       'style': 'swept',
                       'beam': 0.34,
                       'bridge': 0.2,
                       'arms': 2,
                       'bays': 3,
                       'canisters': 0,
                       'engines': 2},
 'rebel:colonizer': {'identifier': 'rebel_colonizer',
                     'data_id': 'rebel_colonizer',
                     'gameplay_entity': 'rebel_colonizer',
                     'faction': 'rebel',
                     'asset_class': 'construction',
                     'authority': 'blend',
                     'limits': [[-42.5, 42.5], [-13.5, 36.5], [-46.94, 48.507]],
                     'design': 'Twin habitat outriggers around a narrow survey lander core and splayed '
                               'deployable landing frame',
                     'style': 'swept',
                     'beam': 0.29,
                     'bridge': 0.18,
                     'arms': 0,
                     'bays': 2,
                     'canisters': 6,
                     'engines': 2},
 'confederacy:constructor': {'identifier': 'confed_constructor',
                             'data_id': 'confed_constructor',
                             'gameplay_entity': 'confed_constructor',
                             'faction': 'confederacy',
                             'asset_class': 'construction',
                             'authority': 'blend',
                             'limits': [[-37.794229, 37.794229], [-8.265, 33.0], [-34.6975, 34.0]],
                             'design': 'Wide industrial carrier with transverse gantry, four forward '
                                       'grapples and stacked fabrication bays',
                             'style': 'gantry',
                             'beam': 0.56,
                             'bridge': 0.25,
                             'arms': 4,
                             'bays': 5,
                             'canisters': 0,
                             'engines': 3},
 'confederacy:colonizer': {'identifier': 'confed_colonizer',
                           'data_id': 'confed_colonizer',
                           'gameplay_entity': 'confed_colonizer',
                           'faction': 'confederacy',
                           'asset_class': 'construction',
                           'authority': 'blend',
                           'limits': [[-52.856406, 52.856406], [-7.0, 43.5], [-51.6975, 55.4475]],
                           'design': 'Broad modular settlement carrier with six habitat canisters and a '
                                     'central deployable lander cradle',
                           'style': 'gantry',
                           'beam': 0.54,
                           'bridge': 0.22,
                           'arms': 0,
                           'bays': 3,
                           'canisters': 6,
                           'engines': 3},
 'syndicate:constructor': {'identifier': 'syndicate_constructor',
                           'data_id': 'syndicate_constructor',
                           'gameplay_entity': 'syndicate_constructor',
                           'faction': 'syndicate',
                           'asset_class': 'construction',
                           'authority': 'blend',
                           'limits': [[-25.714157, 29.98], [-9.0, 36.5], [-40.8725, 32.388]],
                           'design': 'Offset heavy workshop spine with unequal forward grapple arms and '
                                     'starboard industrial bays',
                           'style': 'offset',
                           'beam': 0.38,
                           'bridge': 0.32,
                           'arms': 3,
                           'bays': 4,
                           'canisters': 0,
                           'engines': 3},
 'syndicate:colonizer': {'identifier': 'syndicate_colonizer',
                         'data_id': 'syndicate_colonizer',
                         'gameplay_entity': 'syndicate_colonizer',
                         'faction': 'syndicate',
                         'asset_class': 'construction',
                         'authority': 'blend',
                         'limits': [[-35.961081, 47.4], [-11.0, 36.5], [-57.8325, 57.4475]],
                         'design': 'Offset habitat stack with five canisters, an exposed lander core and '
                                   'unequal deployable frame legs',
                         'style': 'offset',
                         'beam': 0.36,
                         'bridge': 0.3,
                         'arms': 0,
                         'bays': 2,
                         'canisters': 5,
                         'engines': 3},
 'shared:construction_scaffold': {'identifier': 'shared_construction_scaffold',
                                  'data_id': None,
                                  'gameplay_entity': 'construction:site:scaffold',
                                  'faction': 'shared',
                                  'asset_class': 'scaffold',
                                  'authority': 'script',
                                  'limits': [[-50.0, 50.0], [0.0, 50.0], [-50.0, 50.0]],
                                  'design': 'Open modular cage: four annular gantry levels, eight posts, '
                                            'diagonal braces and work collars; progress arc remains a '
                                            'renderer effect',
                                  'style': 'cage'}}


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--all', action='store_true')
    selection.add_argument('--asset', choices=tuple(ROWS))
    parser.add_argument('--replace-seed', action='store_true')
    return parser.parse_args(argv)


def preflight(args):
    """Validate the entire transaction before importing the scene-resetting helper."""
    keys = list(ROWS) if args.all else [args.asset]
    existing = [ROOT / f"art/blender/{ROWS[key]['identifier']}.blend" for key in keys
                if (ROOT / f"art/blender/{ROWS[key]['identifier']}.blend").exists()]
    if existing and not args.replace_seed:
        raise ValueError('editable master exists: ' + ', '.join(p.name for p in existing)
                         + '; export the existing .blend instead; --replace-seed destroys edits')
    return keys


def ship_parts(row, plate, cylinder, loft):
    """Broad connected structure in a local design frame, fitted only after evaluation.

    Faction style changes topology: armoured rectangular spine; swept tapered fork;
    gantry carrier with transverse trusses; offset spine and unequal module banks.
    Constructor grapples and colonizer lander frames are different assemblies.
    """
    width = row['beam'] * 100
    offset = 7 if row['style'] == 'offset' else 0
    sections = ((-40, width * .70, 10, -9), (-28, width, 12, -11),
                (5, width, 12, -11), (22, width * .72, 9, -8))
    if row['style'] == 'swept':
        sections = ((-40, width * .45, 8, -8), (-24, width, 11, -9),
                    (0, width * .75, 10, -9), (25, width * .20, 7, -5))
    loft('01 Industrial pressure spine', 'base', sections, .6, (offset, 0, 0))
    plate('02 Command pedestal', 'base', (width * .8, 15, 24), (offset, 15, -22))
    plate('03 Command tier', 'trim', (width * .65, 5, 20), (offset, 23, -22))
    plate('04 Bridge visor', 'lit', (width * .58, 2.5, 2), (offset, 24, -12))
    plate('05 Radiator mast', 'cool', (3, row['bridge'] * 100, 12),
          (offset, 24 + row['bridge'] * 40, -22))
    plate('06 Ventral service keel', 'dark', (width, 4, 42), (offset, -10, -7))
    # Wide work bays sit on the spine's parallel middle section, never on an imagined taper.
    for side in (-1, 1):
        reach = width + (9 if row['style'] == 'offset' and side > 0 else 0)
        plate(f'10 Bay carrier {side}', 'base', (18, 18, 39), (offset + side * reach, 1, -10))
        for k in range(row['bays']):
            z = -25 + k * 30 / max(1, row['bays'] - 1)
            plate(f'11 Workshop recess {side} {k}', 'dark', (3, 11, 6),
                  (offset + side * (reach + 8), 2, z))
            plate(f'12 Workshop lintel {side} {k}', 'trim', (5, 3, 7),
                  (offset + side * (reach + 7), 8, z))
            plate(f'13 Workshop light {side} {k}', 'lit', (3, 2, 5),
                  (offset + side * (reach + 8), 5.5, z))
            plate(f'14 Hazard shoulder {side} {k}', 'accent', (12, 2, 4),
                  (offset + side * reach, 10, z))
        plate(f'15 Service radiator {side}', 'cool', (3, 10, 20),
              (offset + side * (width * .72), 14, -10))
        for k in range(4):
            plate(f'16 Raised deck armour {side} {k}', 'base', (width * .60, 3, 6),
                  (offset + side * width * .40, 12, -25 + k * 9))
            plate(f'17 Deck strap {side} {k}', 'trim', (width * .62, 2, 2),
                  (offset + side * width * .40, 14, -25 + k * 9))
    if row['style'] == 'gantry':
        for z in (-22, 0):
            plate(f'18 Transverse gantry {z}', 'base', (width * 2.4, 6, 7), (0, 18, z))
            for side in (-1, 1):
                plate(f'19 Gantry leg {z} {side}', 'trim', (5, 20, 7),
                      (side * width, 10, z))
    for k in range(row['engines']):
        x = offset + (k - (row['engines'] - 1) / 2) * 11
        cylinder(f'20 Drive shroud {k}', 'dark', (x, 0, -38), 7, 12, 'Z', 16)
        cylinder(f'21 Drive collar {k}', 'trim', (x, 0, -42), 7.3, 3, 'Z', 16)
        cylinder(f'22 Drive aperture {k}', 'lit', (x, 0, -44), 5.5, 1.2, 'Z', 16)
    if row['arms']:
        for k in range(row['arms']):
            x = offset + (k - (row['arms'] - 1) / 2) * 22
            end = 44 - (k * 5 if row['style'] == 'offset' else 0)
            plate(f'30 Arm root {k}', 'base', (12, 12, 18), (x, 0, 17))
            cylinder(f'31 Shoulder pivot {k}', 'trim', (x, 0, 22), 7, 13, 'Y', 16)
            plate(f'32 Forward manipulator {k}', 'base', (7, 7, end - 18), (x, 0, (18 + end) / 2))
            plate(f'33 Hydraulic ram {k}', 'dark', (3, 3, end - 20), (x, 3.5, (20 + end) / 2))
            cylinder(f'34 Wrist pivot {k}', 'accent', (x, 0, end), 5, 8, 'Y', 12)
            for side in (-1, 1):
                plate(f'35 Grapple jaw {k} {side}', 'trim', (3, 7, 10), (x + side * 4, 0, end + 3))
                plate(f'36 Grapple hook {k} {side}', 'dark', (5, 7, 3), (x + side * 3, 0, end + 7))
    else:
        # Separate round habitat canisters, positively seated into spine/outer carrier.
        for k in range(row['canisters']):
            side = -1 if k % 2 == 0 else 1
            x = offset + side * width * .68
            z = -22 + (k // 2) * 15
            cylinder(f'40 Habitat canister {k}', 'base', (x, 19, z), 10, 17, 'Z', 16)
            for dz in (-6, 6):
                cylinder(f'41 Habitat collar {k} {dz}', 'trim', (x, 19, z + dz), 10.5, 2.5, 'Z', 16)
            plate(f'42 Habitat window band {k}', 'lit', (11, 3, 13), (x, 28, z))
            plate(f'43 Habitat ID {k}', 'accent', (12, 2, 4), (x, 29, z))
        cylinder('44 Survey lander core', 'base', (offset, 0, 24), 16, 25, 'Y', 16)
        cylinder('45 Lander deployment collar', 'accent', (offset, -9, 24), 18, 4, 'Y', 16)
        for side in (-1, 1):
            for z in (5, 36):
                plate(f'46 Deployable crossmember {side} {z}', 'trim', (width + 15, 5, 5),
                      (offset + side * width / 2, -9, z))
                plate(f'47 Landing frame leg {side} {z}', 'base', (5, 17, 7),
                      (offset + side * width, -15, z))
                plate(f'48 Landing foot {side} {z}', 'dark', (13, 4, 12),
                      (offset + side * width, -23, z))


def scaffold_parts(plate, annulus):
    """No cap or solid hull: annular walkways, posts and open diagonal trusses."""
    from mathutils import Vector
    for k, y in enumerate((2, 17, 32, 48)):
        ring = annulus(f'01 Open gantry ring {k}', 'base', 0, 0,
                       ((-1.5, 50, 45), (1.5, 50, 45)), 48)
        ring.rotation_euler[0] = math.pi / 2
        ring.location.y = y
    for k in range(8):
        a = 2 * math.pi * k / 8
        x, z = 47.5 * math.cos(a), 47.5 * math.sin(a)
        plate(f'10 Structural post {k}', 'trim', (4, 50, 4), (x, 25, z))
        for j, role in enumerate(('dark', 'accent', 'lit', 'cool')):
            plate(f'11 Post work collar {k} {j}', role, (6, 4, 6), (x, 8 + j * 11, z))
        b = 2 * math.pi * (k + 1) / 8
        for lower in (2, 25):
            start = Vector((x, lower, z))
            stop = Vector((47.5 * math.cos(b), lower + 23, 47.5 * math.sin(b)))
            beam = plate(f'12 Diagonal gantry brace {k} {lower}', 'dark',
                         (2.5, 2.5, (stop - start).length), (0, 0, 0))
            beam.rotation_euler = (stop - start).to_track_quat('Z', 'Y').to_euler()
            beam.location = (start + stop) / 2


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
        for i, (low, high) in enumerate(row['limits']):
            assert hi[i] > lo[i]
            p[i] = low + (p[i] - lo[i]) * (high - low) / (hi[i] - lo[i])
    triangles = {role: 0 for role in ROLES}
    unique = set()
    for obj in objects:
        obj.data.update()
        obj.data.calc_loop_triangles()
        triangles[obj['engine_material_role']] += len(obj.data.loop_triangles)
        unique.update(tuple(round(float(c), 6) for c in v.co) for v in obj.data.vertices)
    measured = [[min(p[i] for p in unique) for i in range(3)],
                [max(p[i] for p in unique) for i in range(3)]]
    for i, (low, high) in enumerate(row['limits']):
        assert abs(measured[0][i] - low) < 1e-3, (i, measured)
        assert abs(measured[1][i] - high) < 1e-3, (i, measured)
    total = sum(triangles.values())
    assert 1800 < total <= 8000, total
    assert len(unique) <= 6000, len(unique)
    assert all(triangles.values()), triangles
    print('AUTHORING_GEOMETRY', json.dumps(dict(identifier=row['identifier'],
          bounds=measured, triangles=total, vertices=len(unique), roles=triangles)))
    return measured


def main(argv=None):
    argv = (sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]) if argv is None else argv
    args = arguments(argv)
    try:
        keys = preflight(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from alliance_common import plate, cylinder, loft, annulus, weld_scene
    import bpy
    for key in keys:
        row = ROWS[key]
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        if row['asset_class'] == 'scaffold':
            scaffold_parts(plate, annulus)
        else:
            ship_parts(row, plate, cylinder, loft)
        bpy.context.view_layer.update()
        # Hull-specific fitting constants, not the shared helper's station-size defaults.
        weld_scene(tolerance=.12, grow_max=.8, min_half=.2, max_half=.7,
                   overlap=.04, max_brace=5, max_members=90)
        bpy.context.view_layer.update()
        measured = bake_fit_and_check(bpy, row)
        scene = bpy.context.scene
        features = dict(authority=row['authority'], binding=key, data_id=row['data_id'],
                        original_design=True, design=row['design'], faction=row['faction'],
                        asset_class=row['asset_class'], measured_envelope=measured,
                        approval='pending_owner_appearance_approval',
                        seed_recipe='tools/art/build_b9_construction.py',
                        material_roles=list(ROLES), review_requires_scaffold_seam=row['asset_class'] == 'scaffold',
                        provenance='Original geometry; no external mesh or texture dependencies')
        scene['asset'] = row['identifier']
        scene['authority'] = row['authority']
        scene['binding'] = key
        scene['features_json'] = json.dumps(features, sort_keys=True)
        scene['design'] = row['design']
        scene['coordinates'] = 'X beam; Y up; +Z forward'
        scene['review'] = 'pending_owner_appearance_approval; no runtime registration'
        master = ROOT / f"art/blender/{row['identifier']}.blend"
        master.parent.mkdir(parents=True, exist_ok=True)
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(master), compress=True)
        print(f'SEED_OK {key} -> {master.name}; authority={row["authority"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

