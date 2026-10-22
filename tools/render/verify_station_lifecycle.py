"""Render the real paid station queue at early/half/completed construction stages."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from verify_star_occlusion import run  # shared bounded native runner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    import game.core
    from test_native_station_lifecycle import StationLifecycleTests
    from render_bridge import packed, hardware, ring
    from render import asset_selection
    from tools.render.dump_snapshot import _default_selection
    asset_selection.configure(_default_selection(), asset_root=ROOT, pack_root=ROOT / 'visual_packs')
    fixture = StationLifecycleTests('test_paid_site_grows_and_is_replaced_by_completed_hull')
    reports = {}
    fixture.setUp()
    try:
        fixture.pay()
        duration = fixture.builder.build_queue[0]['total']
        for label, advance in [('early', 0.), ('half', duration / 2), ('complete', duration)]:
            if advance:
                fixture.cs.update(advance)
            folder = out / label
            folder.mkdir(exist_ok=True)
            payload, _ = fixture.collector.collect_into(fixture.st,
                bytearray(packed.frame_size(64, 64)), tick=fixture.st.tick, frame_index=0)
            (folder / 'tables.bin').write_bytes(fixture.tables.encode())
            frames = ring.Ring.create(folder / 'frame.ring', slots=4, slot_bytes=16384)
            frames.publish(bytes(payload))
            frames.close()
            meshes = ring.Ring.create(folder / 'hardware.ring', slots=8, slot_bytes=4 << 20)
            publisher = hardware.MeshPublisher()
            publisher.publish_frame(payload, fixture.tables, meshes)
            meshes.close()
            snapshot = json_state = fixture.st.to_dict(precise=True)
            (folder / 'state.json').write_text(json.dumps(json_state, indent=2))
            run([str(ROOT / 'render_cpp/build-w02/armada_viewer'),
                '--snapshot', str(ROOT / 'assets/cpp/catalogue.snap'), '--assets', str(ROOT),
                '--ring', str(folder / 'frame.ring'), '--tables', str(folder / 'tables.bin'),
                '--mesh-ring', str(folder / 'hardware.ring'), '--frames', '35', '--warmup', '0',
                '--focus', '0,0,0', '--distance', '350', '--pitch', '35', '--yaw', '25',
                '--screenshot', str(folder / 'capture.png'), '--report', str(folder / 'viewer.json')],
                folder, 'native')
            report = json.loads((folder / 'viewer.json').read_text())
            reports[label] = report['hardware']
            assert fixture.st.to_dict(precise=True) == snapshot, 'Rendering changed game state'
    finally:
        fixture.doCleanups()
    (out / 'verification.json').write_text(json.dumps(reports, indent=2))
    print(json.dumps(reports, indent=2))
    for label, report in reports.items():
        assert report['decode_failures'] == 0, (label, report)
        assert report['instances_drawn'] > 0, (label, 'paid station/site invisible', report)
        assert report['unmeshed'] == 0 and report['dropped_instances'] == 0, (label, report)


if __name__ == '__main__':
    main()
