"""Actual native fog pixels against authoritative ship/station discovery masks.

Time-separated masks are produced by real sensors and decoded from LiveSession's
ring. A bright diagnostic floor makes opaque/transparent cells discriminating.
This tests the native render path, not only serialization.
"""
from pathlib import Path
import argparse
import json
import math
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(Path(__file__).parent)]
from verify_star_occlusion import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    from test_native_fog_discovery import NativeFogDiscoveryTests
    from render_bridge import ring, fogmap, hardware, packed
    from render_bridge.live import LiveSession
    from game.core.vectors import Vec3
    import numpy as np
    from PIL import Image
    fixture = NativeFogDiscoveryTests(); fixture.setUp()
    try:
        state = fixture.state
        ship = fixture.source('ship'); fixture.visibility.update()
        from game.data.store import DataStore
        session = LiveSession(state, DataStore.get(), directory=out / 'source-rings',
                              size=(320, 200), planet_texture=16)
        fixture.addCleanup(session.close)
        reader = ring.Ring.open(session.paths['fog']); fixture.addCleanup(reader.close)
        cases = []
        for label in ['ship-before', 'ship-after', 'station-added']:
            if label == 'ship-after': ship.pos = Vec3(9000, 0, 5000)
            if label == 'station-added': fixture.source('station')
            fixture.visibility.update()
            session.publish(state, visible_ids=set(state.entities))
            cases.append((label, reader.latest()[1]))
        name = 'shared:fog_diagnostic_floor'
        tables = packed.Tables.build([name], [])
        (out / 'tables.bin').write_bytes(tables.encode())
        h = state.map_info.bounds / 2
        vertices = [(-h, -2, -h), (h, -2, -h), (h, -2, h), (-h, -2, h)]
        mesh = {'base': [((0, 1, 0), (vertices[0], vertices[2], vertices[1])),
                         ((0, 1, 0), (vertices[0], vertices[3], vertices[2]))]}
        stream = ring.Ring.create(out / 'mesh.ring', slots=4, slot_bytes=2048)
        stream.publish(hardware.encode(name, mesh)); stream.close()
        instance = packed.instance_record(entity_id=1, binding_id=0,
            matrix=packed.matrix_from_pose((0, 0, 0), 0, 1), tint=(1, 1, 1, 1),
            flags=packed.FLAG_DYNAMIC_MESH)
        payload = packed.pack_frame(bytearray(packed.frame_size(1, 0)), tick=0,
            frame_index=0, tables=tables, instances=[instance], effects=[])
        frames = ring.Ring.create(out / 'frame.ring', slots=4, slot_bytes=1024)
        frames.publish(payload); frames.close()
        for label, blob in [('no-fog', None)] + cases:
            folder = out / label; folder.mkdir(exist_ok=True)
            command = [str(ROOT / 'render_cpp/build-w02/armada_viewer'),
                '--snapshot', str(ROOT / 'assets/cpp/catalogue.snap'), '--assets', str(ROOT),
                '--ring', str(out / 'frame.ring'), '--tables', str(out / 'tables.bin'),
                '--mesh-ring', str(out / 'mesh.ring'), '--frames', '25', '--warmup', '0',
                '--focus', '0,0,0', '--distance', '36000', '--pitch', '89', '--yaw', '0',
                '--screenshot', str(folder / 'capture.png'), '--report', str(folder / 'native.json')]
            if blob:
                masks = ring.Ring.create(folder / 'fog.ring', slots=4, slot_bytes=len(blob) + 128)
                masks.publish(blob); masks.close()
                command += ['--fog-ring', str(folder / 'fog.ring')]
            run(command, folder, 'native')
        baseline = np.asarray(Image.open(out / 'no-fog/capture.png').convert('RGB'), dtype=float)
        height, width = baseline.shape[:2]
        focal = height / 2 / math.tan(math.radians(55) / 2)
        pitch = math.radians(89)

        def screen(x, z):
            depth = 36000 - z * math.cos(pitch)
            return round(width / 2 + focal * x / depth), round(height / 2 + focal * z * math.sin(pitch) / depth)

        samples = []
        for label, blob in cases:
            mask = fogmap.decode(blob)
            image = np.asarray(Image.open(out / label / 'capture.png').convert('RGB'), dtype=float)
            for x, z in [(-8750, -3750), (9250, 5250), (250, -10750)]:
                point = Vec3(x, 0, z)
                alpha = fixture.alpha(mask, point)
                px, py = screen(x, z)
                reference = np.median(baseline[py-2:py+3, px-2:px+3], axis=(0, 1))
                actual = np.median(image[py-2:py+3, px-2:px+3], axis=(0, 1))
                color = np.array((12, 22, 38) if alpha == 155 else (3, 6, 13))
                expected = reference * (1-alpha/255) + color * alpha/255
                error = float(np.max(np.abs(actual-expected)))
                samples.append(dict(case=label, world=[x, z], pixel=[px, py], alpha=alpha,
                    floor_rgb=reference.tolist(), actual_rgb=actual.tolist(), expected_rgb=expected.tolist(), error=error))
        # Keep one embedded renderer alive while generations change: fresh standalone
        # captures alone cannot catch a stale live texture.
        import ctypes
        library = ROOT / 'render_cpp/build-w02' / ('armada_embedded.dll' if sys.platform == 'win32' else 'libarmada_embedded.dylib')
        lib = ctypes.CDLL(str(library))
        lib.armada_open.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)]
        lib.armada_open.restype = ctypes.c_void_p
        lib.armada_frame.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        lib.armada_frame.restype = ctypes.c_int
        lib.armada_close.argtypes = [ctypes.c_void_p]; lib.armada_close.restype = None
        live_masks = ring.Ring.create(out / 'live-fog.ring', slots=4, slot_bytes=len(cases[0][1]) + 128)
        fixture.addCleanup(live_masks.close)
        argv = [str(ROOT / 'render_cpp/build-w02/armada_viewer'), '--snapshot', str(ROOT / 'assets/cpp/catalogue.snap'),
                '--assets', str(ROOT), '--ring', str(out / 'frame.ring'), '--tables', str(out / 'tables.bin'),
                '--mesh-ring', str(out / 'mesh.ring'), '--fog-ring', str(out / 'live-fog.ring'),
                '--width', '1280', '--height', '800', '--focus', '0,0,0', '--distance', '36000',
                '--pitch', '89', '--yaw', '0']
        encoded = (ctypes.c_char_p * len(argv))(*(str(p).encode() for p in argv))
        handle = lib.armada_open(len(argv), encoded)
        assert handle, 'Could not open native fog live test'
        pixels = (ctypes.c_ubyte * (1280 * 800 * 4))()
        live_images = {}
        try:
            for label, blob in [('no-fog', None)] + cases:
                if blob: live_masks.publish(blob)
                for _ in range(2):
                    assert lib.armada_frame(handle, pixels, len(pixels)) == len(pixels)
                image = Image.frombytes('RGBA', (1280, 800), bytes(pixels), 'raw', 'BGRA').convert('RGB')
                image.save(out / ('live-' + label + '.png'))
                live_images[label] = np.asarray(image, dtype=float)
        finally:
            lib.armada_close(handle)
        baseline = live_images['no-fog']
        live_samples = []
        for sample in samples:
            x, y = sample['pixel']
            actual = np.median(live_images[sample['case']][y-2:y+3, x-2:x+3], axis=(0, 1))
            base = np.median(baseline[y-2:y+3, x-2:x+3], axis=(0, 1))
            alpha = sample['alpha']
            color = np.array((12, 22, 38) if alpha == 155 else (3, 6, 13))
            expected = base * (1-alpha/255) + color * alpha/255
            live_samples.append(dict(case=sample['case'], pixel=[x,y], alpha=alpha,
                floor_rgb=base.tolist(), actual_rgb=actual.tolist(), expected_rgb=expected.tolist(),
                error=float(np.max(np.abs(actual-expected)))))
        discriminating = all(min(s['floor_rgb']) > 60 for s in samples + live_samples)
        result = dict(samples=samples, live_samples=live_samples, discriminating=discriminating,
                      passed=discriminating and all(s['error'] < 8 for s in samples + live_samples))
        (out / 'verification.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        assert all(min(s['floor_rgb']) > 60 for s in samples + live_samples), 'Missing bright floor at a measured point; fog test is not discriminating'
        assert result['passed'], 'Native fog pixels disagree with authoritative mask at world positions'
    finally:
        fixture.doCleanups()


if __name__ == '__main__':
    main()
