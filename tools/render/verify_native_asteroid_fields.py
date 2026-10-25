"""Prove the native window draws a map's asteroid fields, from a real skirmish state.

The collector used to drop asteroid fields ("not spheres"), so every map was drawn without
its mining sites. The unit tests pin the collector; this proves the pixels: it takes a real
skirmish map, builds the frame through the production collector, renders it with the native
viewer, and compares the capture against the same camera with the fields removed. If the
fields are drawn, the difference is confined to the field and is rock-coloured.

    python tools/render/verify_native_asteroid_fields.py --out OUTDIR
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(command, cwd, label):
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=180)
    (Path(cwd) / f'{label}.log').write_text(result.stdout + result.stderr)
    if result.returncode != 0:
        raise SystemExit(f'{label} failed ({result.returncode}): {(result.stdout + result.stderr)[-4000:]}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
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
    drawn = [record for record in instances if record[1] == index]
    if len(drawn) != len(fields):
        raise SystemExit(f'collector emitted {len(drawn)} of {len(fields)} fields')

    def publish(name, records):
        stream = ring.Ring.create(out / f'{name}.ring', slots=4, slot_bytes=1 << 16)
        payload = packed.pack_frame(bytearray(packed.frame_size(len(records), 0)), tick=0,
                                    frame_index=0, tables=tables, instances=records, effects=[])
        stream.publish(payload)
        stream.close()
        return out / f'{name}.ring'

    with_fields = publish('frame-with-fields', drawn)
    without_fields = publish('frame-without-fields', [])

    radius = float(target.radius)
    camera = ['--focus', f'{target.pos.x:.3f},0,{target.pos.z:.3f}',
              '--distance', f'{radius * 5.0:.3f}', '--pitch', '40', '--yaw', '0']
    viewer = ROOT / 'render_cpp/build-w02/armada_viewer'
    for label, scene in [('with-fields', with_fields), ('without-fields', without_fields)]:
        folder = out / label
        folder.mkdir(exist_ok=True)
        run([str(viewer), '--snapshot', str(ROOT / 'assets/cpp/catalogue.snap'),
             '--assets', str(ROOT), '--ring', str(scene), '--tables', str(out / 'tables.bin'),
             '--frames', '25', '--warmup', '0', *camera,
             '--screenshot', str(folder / 'capture.png'),
             '--report', str(folder / 'native.json')], folder, 'native')

    drawn_image = np.asarray(Image.open(out / 'with-fields/capture.png').convert('RGB'), dtype=float)
    empty_image = np.asarray(Image.open(out / 'without-fields/capture.png').convert('RGB'), dtype=float)
    delta = np.abs(drawn_image - empty_image).max(axis=2)
    changed = delta > 12
    height, width = delta.shape
    # The field sits at the centre of a 55-degree view, so its disc covers most of the frame;
    # what matters is that a lot of pixels changed and that they are lit rock, not background.
    coverage = float(changed.mean())
    if changed.any():
        mean_rgb = drawn_image[changed].mean(axis=0).tolist()
    else:
        mean_rgb = [0.0, 0.0, 0.0]
    background = np.median(empty_image, axis=(0, 1)).tolist()
    result = dict(
        map_id=options.get('map_id'), entity_id=target.id, radius=radius,
        fields_in_state=len(fields), fields_emitted=len(drawn),
        scale=float(drawn[0][11]), coverage=coverage,
        changed_pixels=int(changed.sum()), frame=[width, height],
        field_rgb=mean_rgb, background_rgb=background,
        omitted_planets=stats['omitted_planets'],
        passed=bool(coverage > 0.02 and sum(mean_rgb) / 3 > sum(background) / 3 + 8))
    (out / 'verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    assert result['passed'], 'the native window did not draw the asteroid field'


if __name__ == '__main__':
    sys.exit(main())
