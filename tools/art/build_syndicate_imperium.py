#!/usr/bin/env python3
"""Build the Rim Syndicate rework hulls; never rebuild an accepted neighbour.

    Blender --background --python-exit-code 1 --python tools/art/build_syndicate_imperium.py -- \
        [--only battleship] [--render DIR] [--replace-own] [--output-root DIR]

Writes only this batch's masters (``art/blender/syndicate_<stem>.blend``), its
runtime meshes and a data-only prototype pack. Every envelope is the legacy
procedural box measured from the live renderer (``render/fleet_geometry``), not
transcribed from a table, so in-game length, camera framing and collision
radii cannot move.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]

# binding, stem, data id, label, envelope measured from render/fleet_geometry
ROWS = (
    ('syndicate:bomber', 'bomber', 'syndicate_bomber_squadron', 'Cutthroat Strike Wing',
     ((-11.737607, 19.625), (-4.925, 12.0), (-23.618, 20.16))),
    ('syndicate:battleship', 'battleship', 'syndicate_battleship', 'Marauder Battleship',
     ((-53.481804, 84.628573), (-20.36, 82.0), (-141.68, 124.8))),
    ('syndicate:supercapital', 'supercapital', 'syndicate_supercapital',
     'Leviathan-class Salvage Dreadnought',
     ((-71.835399, 116.676), (-34.0, 82.0), (-197.33, 175.2))),
)


ROLE_STILL = {
    'base': ((.42, .44, .47, 1), 0., .62, .45),
    'dark': ((.10, .11, .13, 1), 0., .30, .70),
    'trim': ((.58, .56, .52, 1), 0., .80, .32),
    'accent': ((.76, .53, .16, 1), 0., .40, .55),
    'lit': ((1.0, .82, .52, 1), 3.2, .30, .40),
    'cool': ((.36, .84, 1.0, 1), 4.5, .20, .30),
}


def still_materials():
    """Review-still materials, keyed by the six runtime roles.

    These exist only so a still shows form and role; the shipped look of the
    asset is the runtime's role shading, not this file.
    """
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


def render_still(path, look_at=(0, 0, 0), distance=None, yaw=38., pitch=22.):
    """Y-up review still; the camera basis is built by hand, not to_track_quat."""
    import bpy
    from mathutils import Matrix, Vector
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 800
    scene.render.film_transparent = False
    world = bpy.data.worlds.new('review')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.02, .03, .05, 1)
    scene.world = world
    mats = still_materials()
    for obj in scene.objects:
        if obj.type == 'MESH':
            # Syndicate masters store 'role'; the accepted Imperium masters use
            # 'engine_material_role', and both are rendered on the same sheet.
            role = obj.get('role') or obj.get('engine_material_role')
            obj.data.materials.clear()
            obj.data.materials.append(mats[role])
    # Suns are aimed by their -Z axis; an unrotated area light points at the
    # floor and renders the whole review black.
    for name, direction, energy in (
            ('key', (.55, -1.0, -.75), 4.2),
            ('rim', (-.9, -.35, .30), 2.1),
            ('fill', (-.3, .8, -.55), 1.1)):
        light = bpy.data.lights.new(name, 'SUN')
        light.energy = energy
        light.angle = math.radians(6)
        obj = bpy.data.objects.new(name, light)
        obj.rotation_euler = Vector(direction).normalized().to_track_quat(
            '-Z', 'Y').to_euler()
        bpy.context.collection.objects.link(obj)
    camera = bpy.data.cameras.new('review')
    camera.lens = 62
    obj = bpy.data.objects.new('review', camera)
    bpy.context.collection.objects.link(obj)
    target = Vector(look_at)
    a, b = math.radians(yaw), math.radians(pitch)
    loc = target + Vector((math.sin(a) * math.cos(b), math.sin(b),
                           math.cos(a) * math.cos(b))) * (distance or 420)
    back = (loc - target).normalized()
    right = Vector((0, 1, 0)).cross(back).normalized()
    up = back.cross(right).normalized()
    obj.matrix_world = Matrix((
        (right.x, up.x, back.x, loc.x),
        (right.y, up.y, back.y, loc.y),
        (right.z, up.z, back.z, loc.z),
        (0.0, 0.0, 0.0, 1.0)))
    scene.camera = obj
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-root', type=Path, default=REPO)
    parser.add_argument('--only', choices=[r[1] for r in ROWS])
    parser.add_argument('--render', type=Path)
    parser.add_argument('--replace-own', action='store_true',
                        help='rebuild only these unapproved batch masters')
    parser.add_argument('--part-dump', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    root = args.output_root.resolve()
    rows = [r for r in ROWS if not args.only or r[1] == args.only]
    if not args.replace_own:
        for _, stem, _, _, _ in rows:
            for path in (root / f'art/blender/syndicate_{stem}.blend',
                         root / f'visual_packs/syndicate-imperium-prototypes/assets/models/'
                                f'syndicate_{stem}.mesh.json'):
                if path.exists():
                    raise FileExistsError(path)
    sys.path.insert(0, str(REPO))
    import bpy
    from tools.art import syndicate_imperium_geometry as g
    from tools.art import syndicate_imperium_designs as designs
    reports = []
    for binding, stem, data_id, label, envelope in rows:
        lo = [e[0] for e in envelope]
        hi = [e[1] for e in envelope]
        frame = {'lo': lo, 'hi': hi, 'span': [b - a for a, b in zip(lo, hi)],
                 'center': [(a + b) / 2 for a, b in zip(lo, hi)]}
        g.initialize()
        designs.build(stem, g, frame)
        if args.render:
            args.render.mkdir(parents=True, exist_ok=True)
            span = hi[2] - lo[2]
            # Framing: a 62 mm lens covers ~0.57 x distance across the frame,
            # so the whole class has to fit with its diagonal, not its length.
            for suffix, yaw, pitch, factor in (('quarter', 38., 22., 2.0),
                                               ('profile', 90., 6., 1.9),
                                               ('bow', 8., 12., 1.6)):
                render_still(args.render / f'syndicate_{stem}-{suffix}.png',
                             distance=span * factor, yaw=yaw, pitch=pitch)
        report = g.export(root, stem, stem, envelope,
                          replace_own=args.replace_own, part_dump=args.part_dump)
        report['binding'] = binding
        report['data_id'] = data_id
        report['label'] = label
        report['envelope'] = {'min': lo, 'max': hi}
        report['blender_version'] = bpy.app.version_string
        report['source_sha256'] = {
            str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__),
                         REPO / 'tools/art/syndicate_imperium_geometry.py',
                         REPO / 'tools/art/syndicate_imperium_designs.py')}
        reports.append(report)
    out = root / 'artifacts/syndicate-imperium/build'
    out.mkdir(parents=True, exist_ok=True)
    (out / (f'{args.only}.json' if args.only else 'all.json')).write_text(
        json.dumps(reports, indent=2) + '\n')
    print('SYNDICATE_BUILD_OK', len(reports), flush=True)


if __name__ == '__main__':
    main()
