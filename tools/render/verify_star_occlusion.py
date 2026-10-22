"""Native pixel regression: a black opaque planet must occlude sky stars.

Runs the actual renderer with a static packed-frame fixture, not the simulation.
Each child has a process-group deadline. Output is real Metal/D3D evidence only.
"""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def run(command, out, label):
    start = time.monotonic()
    with (out / (label + '.log')).open('w') as log:
        environment = dict(os.environ)
        if sys.platform == 'darwin':
            environment['SDL_VIDEODRIVER'] = 'cocoa'
        child = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True, env=environment)
        expired = False
        try:
            code = child.wait(timeout=35)
        except subprocess.TimeoutExpired:
            expired = True
            os.killpg(child.pid, signal.SIGKILL)
            code = child.wait()
    receipt = dict(command=list(map(str, command)), returncode=code, timeout=expired,
                   seconds=time.monotonic() - start)
    (out / (label + '-process.json')).write_text(json.dumps(receipt, indent=2))
    assert code == 0 and not expired, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--binary', type=Path, default=ROOT / 'render_cpp/build-w02/armada_viewer')
    parser.add_argument('--shaders', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    from render_bridge import packed, planets, ring
    import numpy as np
    from PIL import Image
    tables = packed.Tables.build(['planet:barren:Occluder'], [])
    (out / 'tables.bin').write_bytes(tables.encode())
    texture = planets.encode_blob('Occluder', 4, 4, b'\0\0\0\xff' * 16)
    textures = ring.Ring.create(out / 'planets.ring', slots=4, slot_bytes=1024)
    textures.publish(texture)
    textures.close()
    for label, body in [('sky', False), ('occluder', True)]:
        rows = [packed.instance_record(entity_id=1, binding_id=0,
                    matrix=packed.matrix_from_pose((0., 0., 0.), 0., 1000.),
                    tint=(1., 1., 1., 1.))] if body else []
        payload = packed.pack_frame(bytearray(packed.frame_size(len(rows), 0)),
                    tick=0, frame_index=0, tables=tables, instances=rows, effects=[])
        frames = ring.Ring.create(out / (label + '.ring'), slots=4, slot_bytes=1024)
        frames.publish(bytes(payload))
        frames.close()
        command = [str(args.binary.resolve()), '--snapshot', str(ROOT / 'assets/cpp/catalogue.snap'),
                   '--assets', str(ROOT), '--ring', str(out / (label + '.ring')),
                   '--tables', str(out / 'tables.bin'), '--planet-ring', str(out / 'planets.ring'),
                   '--frames', '30', '--warmup', '0', '--focus', '0,0,0', '--distance', '4000',
                   '--pitch', '0', '--yaw', '90', '--screenshot', str(out / (label + '.png')),
                   '--report', str(out / (label + '.json'))]
        if args.shaders:
            command += ['--shaders', str(args.shaders.resolve())]
        run(command, out, label)
    sky = np.asarray(Image.open(out / 'sky.png').convert('RGB')).astype(int)
    image = np.asarray(Image.open(out / 'occluder.png').convert('RGB')).astype(int)
    h, w = image.shape[:2]
    yy, xx = np.ogrid[:h, :w]
    # Analytic projected sphere radius, then erode 25% to exclude silhouette/MSAA.
    focal = h / 2 / math.tan(math.radians(55) / 2)
    radius = focal * 1000 / math.sqrt(4000 ** 2 - 1000 ** 2)
    interior = (xx - w / 2) ** 2 + (yy - h / 2) ** 2 < (radius * .75) ** 2
    foreground_stars = int(np.count_nonzero((image.max(axis=2) > 3) & interior))
    sky_candidates = int(np.count_nonzero((sky.max(axis=2) > 40) & interior))
    report = dict(foreground_star_pixels=foreground_stars,
                  sky_candidate_pixels_behind_planet=sky_candidates,
                  planet_interior_pixels=int(interior.sum()), projected_radius=radius)
    report['viewer'] = json.loads((out / 'occluder.json').read_text())
    (out / 'verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'viewer'}, indent=2))
    assert sky_candidates > 5, 'Non-discriminating fixture: no stars behind the occluder'
    assert foreground_stars == 0, f'Stars paint over an opaque black planet: {foreground_stars} pixels'


if __name__ == '__main__':
    main()
