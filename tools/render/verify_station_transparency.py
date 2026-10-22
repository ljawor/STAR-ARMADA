"""Native alpha negative control: exact same station mesh, pose and light at three opacities."""
from pathlib import Path
import argparse
import json
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(Path(__file__).parent)]
from verify_star_occlusion import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--faction', choices=('imperial', 'rebel'), default='imperial')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    import numpy as np
    from PIL import Image
    from test_native_station_lifecycle import StationLifecycleTests
    from render_bridge import packed, hardware, ring
    from render import asset_selection
    from tools.render.dump_snapshot import _default_selection
    asset_selection.configure(_default_selection(), asset_root=ROOT, pack_root=ROOT / 'visual_packs')
    fixture = StationLifecycleTests('test_paid_station_created_after_tables_is_present_in_live_frame')
    fixture.faction = args.faction
    fixture.setUp()
    images, reports = {}, {}
    try:
        binding = fixture.tables.bindings.index(args.faction + ':trade_station')
        scale = fixture.ds.stations['trade_station'].radius / 50.

        for label, opacity in [('empty', 0.), ('early', .2), ('late', .55), ('solid', 1.)]:
            folder = out / label
            folder.mkdir(exist_ok=True)
            instances = [] if not opacity else [packed.instance_record(entity_id=0xC0000001,
                binding_id=binding, matrix=packed.matrix_from_pose((0.,0.,0.),0.,scale),
                tint=(*fixture.st.players[0].color[:3], opacity), flags=packed.FLAG_DYNAMIC_MESH)]
            payload = packed.pack_frame(bytearray(packed.frame_size(4,0)), tick=0, frame_index=0,
                tables=fixture.tables, instances=instances, effects=[])
            (folder / 'tables.bin').write_bytes(fixture.tables.encode())
            frames = ring.Ring.create(folder / 'frame.ring', slots=4, slot_bytes=16384)
            frames.publish(bytes(payload)); frames.close()
            meshes = ring.Ring.create(folder / 'mesh.ring', slots=8, slot_bytes=4 << 20)
            # Each standalone consumer needs its own initial geometry, not another session's cache.
            hardware.MeshPublisher().publish_frame(payload, fixture.tables, meshes)
            meshes.close()
            run([str(ROOT / 'render_cpp/build-w02/armada_viewer'), '--snapshot',
                 str(ROOT / 'assets/cpp/catalogue.snap'), '--assets', str(ROOT),
                 '--ring', str(folder / 'frame.ring'), '--tables', str(folder / 'tables.bin'),
                 '--mesh-ring', str(folder / 'mesh.ring'), '--frames', '24', '--warmup', '0',
                 '--focus', '0,0,0', '--distance', '350', '--pitch', '35', '--yaw', '25',
                 '--screenshot', str(folder / 'capture.png'), '--report', str(folder / 'viewer.json')],
                 folder, 'native')
            reports[label] = json.loads((folder / 'viewer.json').read_text())['hardware']
            images[label] = np.asarray(Image.open(folder / 'capture.png').convert('RGB'), dtype=float)
    finally:
        fixture.doCleanups()
    empty, solid = images['empty'], images['solid']
    contrast = np.max(np.abs(solid-empty), axis=2)
    mask = contrast > 40
    count = int(mask.sum())
    results: dict[str, Any] = dict(contrasting_station_pixels=count, hardware=reports)
    assert count > 300, 'No discriminating opaque station in native reference'
    for name in ('early', 'late'):
        results[name] = dict(background_distance=float(np.mean(np.abs(images[name]-empty)[mask])),
                             solid_distance=float(np.mean(np.abs(images[name]-solid)[mask])))
    results['solid_background_distance'] = float(np.mean(np.abs(solid-empty)[mask]))
    # Intersecting authored layers can expose bright interior details through glass;
    # late ghost brightness need not stay below the opaque outer shell's brightness.
    # It must instead converge towards the opaque image while remaining distinct.
    results['passed'] = (results['early']['solid_distance'] > results['late']['solid_distance'] > 2 and
                         results['early']['background_distance'] > 2 and
                         results['early']['background_distance'] < results['late']['background_distance'])
    (out / 'verification.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    assert results['passed'], 'Station alpha ignored, invisible or not progressively more solid'


if __name__ == '__main__':
    main()
