#!/usr/bin/env python3
"""Build the remaining 23 Rim Syndicate meshes; never rebuild an accepted neighbour.

    blender -b --python tools/art/build_syndicate_fleet.py -- \
        [--only cruiser] [--family station,satellite] [--render DIR] [--replace-own]

Envelopes come from ``assets/models/registry.json`` -- the containment box each
binding was already approved at -- so in-game length, camera framing, collision
radius and every simulation field stay exactly where they are.

Outputs land beside the accepted batch, never over it: masters in
``art/blender/syndicate_fleet/`` and runtime meshes in the
``syndicate-fleet-prototypes`` pack. The older ``art/blender/syndicate_<stem>.blend``
masters of the same stems are the accepted s06 batch and stay untouched.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]

ROWS = (
    ('corvette', 'Syndicate Corvette', 'hull', 1800),
    ('frigate', 'Syndicate Frigate', 'hull', 1800),
    ('cruiser', 'Syndicate Cruiser', 'hull', 1800),
    ('convoy', 'Syndicate Convoy', 'hull', 1800),
    ('colonizer', 'Syndicate Colonizer', 'hull', 1800),
    ('constructor', 'Syndicate Constructor', 'hull', 1800),
    ('fighter', 'Syndicate Fighter', 'fighter', 700),
    ('command_station', 'Syndicate Command Station', 'station', 1800),
    ('defense_platform', 'Syndicate Defense Platform', 'station', 1800),
    ('energy_relay', 'Syndicate Energy Relay', 'station', 1800),
    ('fighter_platform', 'Syndicate Fighter Platform', 'station', 1800),
    ('mining_station', 'Syndicate Mining Station', 'station', 1800),
    ('repair_dock', 'Syndicate Repair Dock', 'station', 1800),
    ('research_station', 'Syndicate Research Station', 'station', 1800),
    ('sensor_station', 'Syndicate Sensor Station', 'station', 1800),
    ('shipyard', 'Syndicate Shipyard', 'station', 1800),
    ('trade_station', 'Syndicate Trade Station', 'station', 1800),
    ('attack_satellite', 'Syndicate Attack Satellite', 'satellite', 900),
    ('defense_satellite', 'Syndicate Defense Satellite', 'satellite', 900),
    ('planet_extractor', 'Syndicate Planet Extractor', 'installation', 1500),
    ('planet_pulsar_cannon', 'Syndicate Planet Pulsar Cannon', 'installation', 1500),
    ('planet_shield_generator', 'Syndicate Planet Shield Generator', 'installation', 1500),
    ('planet_trade_hub', 'Syndicate Planet Trade Hub', 'installation', 1500),
)

ROLE_STILL = {
    'base': ((.42, .44, .47, 1), 0., .62, .45),
    'dark': ((.10, .11, .13, 1), 0., .30, .70),
    'trim': ((.58, .56, .52, 1), 0., .80, .32),
    'accent': ((.76, .53, .16, 1), 0., .40, .55),
    'lit': ((1.0, .82, .52, 1), 3.2, .30, .40),
    'cool': ((.36, .84, 1.0, 1), 4.5, .20, .30),
}
MASTERS = 'art/blender/syndicate_fleet'
PACK = 'art/blender/syndicate_fleet/runtime'


def registry_envelopes():
    data = json.loads((REPO / 'assets/models/registry.json').read_text(encoding='utf-8'))
    boxes = {}
    for row in data['bindings']:
        if row['binding'].startswith('syndicate:') and row.get('envelope'):
            boxes[row['binding'].split(':', 1)[1]] = row['envelope']
    return boxes


def still_materials():
    import bpy
    made = {}
    for role, (rgba, emit, metallic, rough) in ROLE_STILL.items():
        mat = bpy.data.materials.new('still_' + role)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes['Principled BSDF']
        bsdf.inputs['Base Color'].default_value = rgba
        bsdf.inputs['Metallic'].default_value = metallic
        bsdf.inputs['Roughness'].default_value = rough
        if emit:
            bsdf.inputs['Emission Color'].default_value = rgba
            bsdf.inputs['Emission Strength'].default_value = emit
        made[role] = mat
    return made


def normalize_to_envelope(frame, clamp=1.35):
    """Fill the approved box per axis, or say which asset underfills it.

    The design fractions already aim at the box, so these factors land near 1. A
    factor above ``clamp`` means the class silhouette is wrong for its envelope;
    that is reported and left for ``export`` to refuse rather than quietly
    stretched into shape.
    """
    import bpy
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    lo, hi = [1e9] * 3, [-1e9] * 3
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        ev = obj.evaluated_get(dg)
        data = ev.to_mesh()
        try:
            for v in data.vertices:
                p = ev.matrix_world @ v.co
                for i in range(3):
                    lo[i] = min(lo[i], p[i])
                    hi[i] = max(hi[i], p[i])
        finally:
            ev.to_mesh_clear()
    centre = [(a + b) / 2 for a, b in zip(frame['lo'], frame['hi'])]
    factors = []
    for i in range(3):
        span = hi[i] - lo[i]
        want = frame['hi'][i] - frame['lo'][i]
        factors.append(want / span if span else 1.)
    print('NORMALISE ' + json.dumps({'span': [round(hi[i] - lo[i], 3) for i in range(3)],
                                     'factors': [round(f, 4) for f in factors]}), flush=True)
    if any(f > clamp for f in factors):
        print('NORMALISE_GAP refusing to stretch beyond', clamp, flush=True)
        return factors
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        obj.scale = factors
        obj.location = [centre[i] * (1 - factors[i]) for i in range(3)]
    bpy.context.view_layer.update()
    return factors


def render_still(path, distance, yaw=38., pitch=22., offset=(0., 0., 0.)):
    import math
    from mathutils import Matrix, Vector
    import bpy
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 760
    scene.render.film_transparent = False
    world = bpy.data.worlds.new('review')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.02, .03, .05, 1)
    scene.world = world
    mats = still_materials()
    for obj in scene.objects:
        if obj.type == 'MESH':
            role = obj.get('role') or obj.get('engine_material_role')
            obj.data.materials.clear()
            obj.data.materials.append(mats[role])
    for name, direction, energy in (('key', (.55, -1.0, -.75), 4.2),
                                    ('rim', (-.9, -.35, .30), 2.1),
                                    ('fill', (-.3, .8, -.55), 1.1)):
        light = bpy.data.lights.new(name, 'SUN')
        light.energy = energy
        light.angle = math.radians(6)
        obj = bpy.data.objects.new(name, light)
        obj.rotation_euler = Vector(direction).normalized().to_track_quat('-Z', 'Y').to_euler()
        bpy.context.collection.objects.link(obj)
    dg = bpy.context.evaluated_depsgraph_get()
    lo, hi = [1e9] * 3, [-1e9] * 3
    for meshobj in scene.objects:
        if meshobj.type != 'MESH':
            continue
        ev = meshobj.evaluated_get(dg)
        data = ev.to_mesh()
        try:
            for v in data.vertices:
                p = ev.matrix_world @ v.co
                for i in range(3):
                    lo[i] = min(lo[i], p[i])
                    hi[i] = max(hi[i], p[i])
        finally:
            ev.to_mesh_clear()
    camera = bpy.data.cameras.new('review')
    camera.lens = 62
    obj = bpy.data.objects.new('review', camera)
    bpy.context.collection.objects.link(obj)
    target = Vector([(lo[i] + hi[i]) / 2 for i in range(3)])
    a, b = math.radians(yaw), math.radians(pitch)
    loc = target + Vector((math.sin(a) * math.cos(b), math.sin(b),
                           math.cos(a) * math.cos(b))) * distance
    back = (loc - target).normalized()
    right = Vector((0, 1, 0)).cross(back).normalized()
    up = back.cross(right).normalized()
    obj.matrix_world = Matrix(((right.x, up.x, back.x, loc.x),
                               (right.y, up.y, back.y, loc.y),
                               (right.z, up.z, back.z, loc.z),
                               (0., 0., 0., 1.)))
    scene.camera = obj
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-root', type=Path, default=REPO)
    parser.add_argument('--only', help='comma-separated stems')
    parser.add_argument('--family', help='comma-separated families: hull,fighter,station,satellite,installation')
    parser.add_argument('--render', type=Path)
    parser.add_argument('--replace-own', action='store_true')
    parser.add_argument('--part-dump', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    root = args.output_root.resolve()
    envelopes = registry_envelopes()
    rows = list(ROWS)
    if args.only:
        wanted = {s.strip() for s in args.only.split(',')}
        rows = [r for r in rows if r[0] in wanted]
    if args.family:
        wanted = {s.strip() for s in args.family.split(',')}
        rows = [r for r in rows if r[2] in wanted]
    if not rows:
        raise SystemExit('no rows selected')
    if not args.replace_own:
        for stem, _, _, _ in rows:
            for path in (root / MASTERS / f'{stem}.blend',
                         root / PACK / 'assets/models' / f'syndicate_{stem}.mesh.json'):
                if path.exists():
                    raise FileExistsError(path)
    sys.path.insert(0, str(REPO))
    import bpy
    from tools.art import syndicate_imperium_geometry as g
    from tools.art import syndicate_fleet_designs as designs
    reports = []
    for stem, label, family, floor in rows:
        if stem not in envelopes:
            raise KeyError('no approved envelope for ' + stem)
        box = envelopes[stem]
        lo, hi = list(box['min']), list(box['max'])
        frame = {'lo': lo, 'hi': hi,
                 'span': [b - a for a, b in zip(lo, hi)],
                 'center': [(a + b) / 2 for a, b in zip(lo, hi)]}
        g.initialize()
        designs.build(stem, g, frame)
        factors = [1., 1., 1.]  # containment only: never inflate into a padded box
        if args.render:
            args.render.mkdir(parents=True, exist_ok=True)
            span = hi[2] - lo[2]
            for suffix, yaw, pitch, factor in (('quarter', 38., 22., 2.0),
                                               ('profile', 90., 6., 1.9),
                                               ('bow', 8., 12., 1.7)):
                render_still(args.render / f'{stem}-{suffix}.png',
                             distance=max(span, hi[0] - lo[0]) * factor, yaw=yaw, pitch=pitch,
                             offset=((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2,
                                     (lo[2] + hi[2]) / 2))
        report = g.export(root, stem, stem, tuple((lo[i], hi[i]) for i in range(3)),
                          replace_own=args.replace_own, part_dump=args.part_dump,
                          master_path=root / MASTERS / f'{stem}.blend',
                          target_path=(root / PACK / 'assets/models'
                                       / f'syndicate_{stem}.mesh.json'),
                          asset_id=f'prototype:syndicate/{stem}',
                          authority=('tools/art/build_syndicate_fleet.py and '
                                     'syndicate_fleet_designs.py'),
                          min_triangles=floor, contain_only=True)
        report.update(binding='syndicate:' + stem, label=label, family=family,
                      envelope=box, normalise=factors,
                      blender_version=bpy.app.version_string,
                      source_sha256={
                          str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in (Path(__file__),
                                       REPO / 'tools/art/syndicate_fleet_designs.py',
                                       REPO / 'tools/art/syndicate_imperium_geometry.py')})
        reports.append(report)
    out = root / 'artifacts/syndicate-fleet/build'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'all.json').write_text(json.dumps(reports, indent=2) + '\n', encoding='utf-8')
    print('SYNDICATE_FLEET_BUILD_OK', len(reports), flush=True)


if __name__ == '__main__':
    main()
