"""Prove the native window draws a map's asteroid fields in a real skirmish frame.

The frame is the whole scene the collector produces - ships, planets, stations, fields - not a
fields-only fixture. Two renders of it differ by a few hundred sparse pixels (silhouette and
starfield flicker); `dense_mask` drops those and keeps the rock patches, which is what makes the
footprint measurement reproducible rather than a coin flip.


The collector used to drop asteroid fields ("not spheres"), so every map was drawn without
its mining sites. The unit tests pin the collector; this proves the pixels: it takes a real
skirmish map, builds the whole frame through the production collector (ships, planets,
stations, effects), renders it with the native viewer, and compares it against the *same
frame with only the asteroid records removed*. Everything else - camera, ships, planets,
HUD-free scene - is identical, so the difference is the fields and nothing else.

The check is not "some pixels changed": it measures the changed footprint against the
field's own projection (world radius, camera distance, the viewer's reported fov) and
against the frame centre, so a field drawn at the wrong scale or in the wrong place fails.

    python tools/render/verify_native_asteroid_fields.py --out OUTDIR
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# A pixel counts as field when it moves more than this in any channel. The scene around the
# field is identical in both frames, so anything above antialiasing noise is field.
PIXEL_THRESHOLD = 12


def run(command, cwd, label):
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=180)
    (Path(cwd) / f'{label}.log').write_text(result.stdout + result.stderr)
    if result.returncode != 0:
        raise SystemExit(f'{label} failed ({result.returncode}): {(result.stdout + result.stderr)[-4000:]}')
    return result


def dense_mask(mask, window=4, minimum=6):
    """Keep changed pixels that sit in a crowd; drop the sparse ones.

    The two renders of a real frame are not pixel-identical: a planet's silhouette and the
    starfield behind it flicker by a pixel or two, anywhere in the frame - 262 such pixels in a
    measured pair, some 30-40 per channel. A bounding box over the raw difference therefore
    jumped to the whole viewport on roughly one run in four. Rocks, unlike that noise, are
    patches: every rock pixel has neighbours. A box this size counts as a crowd, a lone
    flickering pixel does not.
    """
    import numpy as np
    integral = np.pad(mask.astype(np.int32), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    height, width = mask.shape
    top, left = np.clip(np.arange(height) - window, 0, None), np.clip(np.arange(width) - window, 0, None)
    bottom = np.clip(np.arange(height) + window + 1, None, height)
    right = np.clip(np.arange(width) + window + 1, None, width)
    counts = (integral[np.ix_(bottom, right)] - integral[np.ix_(top, right)]
              - integral[np.ix_(bottom, left)] + integral[np.ix_(top, left)])
    return mask & (counts >= minimum)


def projected_radius_px(world_radius, distance, fov_deg, image_height):
    """Half-width of a world-space disc of `world_radius` seen `distance` away, in pixels."""
    return (world_radius / (distance * math.tan(math.radians(fov_deg) * 0.5))) * (image_height * 0.5)


CONTROLS = ('scale3', 'shift', 'boulder')


def apply_control(name):
    """Draw the field wrong on purpose, so the checks can be shown to notice.

    These are the sabotage controls the report cites. They live here as a flag rather than as
    prose in a table: anyone can re-run them and read the numbers instead of believing them. A
    control run is not evidence about the game - it is evidence about the measurement.
    """
    if not name:
        return
    from render_bridge import collect
    if name == 'scale3':
        collect.ASTEROID_EXTENT = collect.ASTEROID_EXTENT / 3.0     # every rock 3x too large
        return
    original = collect.asteroid_rocks
    if name == 'shift':
        def asteroid_rocks(entity):
            reach = float(entity.radius) * 0.8                       # the belt, moved off its mark
            return tuple(((x + reach, y, z), yaw, scale, shade)
                         for (x, y, z), yaw, scale, shade in original(entity))
    elif name == 'boulder':
        def asteroid_rocks(entity):                                  # one rock filling the field
            size = float(entity.radius) * 0.95
            return (((float(entity.pos.x), 0.0, float(entity.pos.z)), 0.0,
                     size / collect.ASTEROID_EXTENT, 0.5),)
    else:
        raise SystemExit(f'unknown control {name!r}')
    collect.asteroid_rocks = asteroid_rocks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--control', choices=CONTROLS, default=None,
                        help='draw the field wrong on purpose to prove the checks notice')
    args = parser.parse_args()
    apply_control(args.control)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    import numpy as np
    from PIL import Image

    from game.core.manager import GameManager
    from game.core.skirmish import build_skirmish_map, default_skirmish_options
    from game.data.store import DataStore
    from render.asset_selection import ship_binding
    from render.ship_sizes import ship_size
    from render_bridge import collect, packed, ring

    ds = DataStore()
    options = default_skirmish_options(ds)
    manager = GameManager.start_skirmish(build_skirmish_map(ds, options))
    state = manager.state
    fields = sorted((e for e in state.entities.values()
                     if e.is_planet and e.data_id == 'asteroid_field'),
                    key=lambda e: (-e.radius, e.id))
    if not fields:
        raise SystemExit('the fixture map has no asteroid fields')
    target = fields[0]

    bindings, weapons = collect.required_names(
        state, ds, ship_size=ship_size, ship_binding=ship_binding, all_visible=True)
    tables = packed.Tables.build(bindings, list(weapons))
    (out / 'tables.bin').write_bytes(tables.encode())
    collector = collect.FrameCollector(ds, tables, asset_selection=None, ship_size=ship_size,
                                       ship_binding=ship_binding, all_visible=True)
    instances, effects, stats = collector.collect(state)
    index = {name: i for i, name in enumerate(tables.bindings)}[collect.ASTEROID_BINDING]
    rocks = [record for record in instances if record[1] == index]
    scene_without = [record for record in instances if record[1] != index]
    rock_fields = {collect.rock_field_id(record[0]) for record in rocks}
    if rock_fields != {(e.id & 0xFFFF) for e in fields}:
        raise SystemExit(f'collector covered fields {sorted(rock_fields)} of {sorted(e.id for e in fields)}')
    if not scene_without:
        raise SystemExit('the fixture frame has no non-asteroid geometry: the comparison would be empty')

    def publish(name, records):
        stream = ring.Ring.create(out / f'{name}.ring', slots=4, slot_bytes=1 << 16)
        payload = packed.pack_frame(bytearray(packed.frame_size(len(records), 0)), tick=0,
                                    frame_index=0, tables=tables, instances=records, effects=[])
        stream.publish(payload)
        stream.close()
        return out / f'{name}.ring'

    def without_target(records):
        """The real frame with only the aimed-at field's rocks removed.

        Several fields can share one 55-degree view (this fixture has five, three of them in
        frame), so a single bounding box over "all changed pixels" would describe the belt, not
        the field the camera is aimed at. Differencing against this frame isolates the target's
        own pixels without moving the camera, so the footprint can be compared to its projection.
        """
        field = target.id & 0xFFFF
        return [record for record in records
                if record[1] != index or collect.rock_field_id(record[0]) != field]

    with_fields = publish('frame-with-fields', instances)
    without_fields = publish('frame-without-fields', scene_without)
    without_target_frame = publish('frame-without-target', without_target(instances))

    radius = float(target.radius)
    distance = radius * 5.0
    pitch = 40.0
    camera = ['--focus', f'{target.pos.x:.3f},0,{target.pos.z:.3f}',
              '--distance', f'{distance:.3f}', '--pitch', f'{pitch:g}', '--yaw', '0']
    viewer = ROOT / 'render_cpp/build-w02/armada_viewer'
    for label, scene in [('with-fields', with_fields), ('without-fields', without_fields),
                         ('without-target', without_target_frame)]:
        folder = out / label
        folder.mkdir(exist_ok=True)
        run([str(viewer), '--snapshot', str(ROOT / 'assets/cpp/catalogue.snap'),
             '--assets', str(ROOT), '--ring', str(scene), '--tables', str(out / 'tables.bin'),
             '--frames', '25', '--warmup', '0', *camera,
             '--screenshot', str(folder / 'capture.png'),
             '--report', str(folder / 'native.json')], folder, 'native')

    def load(name):
        return np.asarray(Image.open(out / name / 'capture.png').convert('RGB'), dtype=float)

    drawn = load('with-fields')
    bare = load('without-fields')
    target_frame = load('without-target')
    changed = np.abs(drawn - bare).max(axis=2) > PIXEL_THRESHOLD      # every field in the frame
    # This field only, with the sparse flicker of silhouettes and starfield removed first.
    target_changed = dense_mask(np.abs(drawn - target_frame).max(axis=2) > PIXEL_THRESHOLD)
    height, width = drawn.shape[:2]
    coverage = float(changed.mean())
    mean_rgb = drawn[changed].mean(axis=0).tolist() if changed.any() else [0.0, 0.0, 0.0]
    background = np.median(bare, axis=(0, 1)).tolist()

    # Footprint against the field's own projection: the camera looks straight at the field
    # centre, so the changed pixels must straddle the frame centre and span the projected disc.
    report = json.loads((out / 'with-fields/native.json').read_text(encoding='utf-8'))
    fov_deg = float(report['projection']['fov_deg'])
    half_width_px = projected_radius_px(radius, distance, fov_deg, height)
    half_height_px = half_width_px * math.cos(math.radians(pitch))
    if target_changed.any():
        rows = np.where(target_changed.any(axis=1))[0]
        cols = np.where(target_changed.any(axis=0))[0]
        box = [int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])]
        centre = [float((box[0] + box[2]) / 2.0), float((box[1] + box[3]) / 2.0)]
        span = [float(box[2] - box[0] + 1), float(box[3] - box[1] + 1)]
    else:
        box, centre, span = [0, 0, 0, 0], [width / 2.0, height / 2.0], [0.0, 0.0]
    centre_error = [abs(centre[0] - width / 2.0) / width, abs(centre[1] - height / 2.0) / height]
    size_ratio = [span[0] / (2.0 * half_width_px), span[1] / (2.0 * half_height_px)]
    # How much of the field's own disc is rock. A scatter of small bodies leaves most of it
    # empty; one boulder scaled up to fill the radius - the bug this replaced - fills most of
    # it. Neither the bbox nor the pixel count separates those two, the fill fraction does.
    disc_area = math.pi * half_width_px * half_height_px
    disc_fill = float(target_changed.sum()) / disc_area if disc_area else 0.0

    # A field that runs past the frame cannot be measured by its bounding box, and it is too
    # big for its radius: the span check below would read a clipped box as correctly sized.
    touches_edge = bool(target_changed[0, :].any() or target_changed[-1, :].any()
                        or target_changed[:, 0].any() or target_changed[:, -1].any())
    checks = {
        'coverage': bool(coverage > 0.01),
        'lit_rock': bool(sum(mean_rgb) / 3 > sum(background) / 3 + 8),
        'target_drawn': bool(int(target_changed.sum()) > 200),
        'inside_the_frame': not touches_edge,
        'centred': bool(max(centre_error) < 0.10),
        'size_matches_projection': bool(0.55 <= size_ratio[0] <= 1.9 and 0.55 <= size_ratio[1] <= 1.9),
        'is_a_scatter_not_a_boulder': bool(0.03 <= disc_fill <= 0.50),
    }
    # Self-describing evidence: an earlier copy of this file in the evidence bundle had been
    # produced by a different revision of the tool, so its numbers described a file that no
    # longer existed. The hash below is of the tool that actually wrote the JSON.
    import hashlib
    tool_path = Path(__file__).resolve()
    result = dict(
        control=args.control,
        expectation='fail' if args.control else 'pass',
        tool=dict(path=str(tool_path.relative_to(ROOT)),
                  sha256=hashlib.sha256(tool_path.read_bytes()).hexdigest(),
                  pixel_threshold=PIXEL_THRESHOLD),
        map_id=options.get('map_id'), entity_id=target.id, radius=radius,
        distance=distance, fov_deg=fov_deg,
        fields_in_state=len(fields), fields_drawn=len(rock_fields), rock_instances=len(rocks),
        instances_with_fields=len(instances), instances_without_fields=len(scene_without),
        coverage=coverage, changed_pixels=int(changed.sum()), frame=[width, height],
        target_pixels=int(target_changed.sum()),
        footprint_box=box, footprint_centre=centre, footprint_span=span,
        dense_mask_window=4, dense_mask_minimum=6,
        projected_span=[2.0 * half_width_px, 2.0 * half_height_px],
        centre_error=centre_error, size_ratio=size_ratio, disc_fill=disc_fill,
        field_rgb=mean_rgb, background_rgb=background,
        touches_frame_edge=touches_edge,
        omitted_planets=stats['omitted_planets'], checks=checks,
        passed=bool(all(checks.values())))
    (out / 'verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if args.control:
        # A control is expected to be rejected: that is the whole point of running it. Exit 0 so
        # the output can be recorded alongside the passing run; the verdict is in the JSON.
        failed = [name for name, ok in checks.items() if not ok]
        if not failed:
            raise SystemExit(f'control {args.control!r} was NOT caught by any check')
        print(f'control {args.control!r} rejected by: {", ".join(failed)}')
        return 0
    assert result['passed'], 'the native window did not draw the asteroid field in the real frame'


if __name__ == '__main__':
    sys.exit(main())
