"""Isolated camera-refresh timing and live-query counts, real factory fleets.

Each size/mode runs in a fresh subprocess. The eager control differs only by
omitting the geometry broad phase; no simulation steps or safety are disabled.
Timings are uninstrumented; cold operation counts are a separate refresh.
Run: .venv/bin/python tools/diag_camera_refresh_perf.py --out SCRATCH_DIR
"""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def probe(count, mode):
    from game.core.manager import GameManager
    from game.core.vectors import Vec3
    from game.data.store import DataStore
    from game.systems.unit_factory import UnitFactory
    from game.systems.visibility import SensorQueries
    from game.systems import stats
    from render.camera import Camera
    from render.camera_geometry import scene_boxes, safe_eye
    st = GameManager.start_skirmish(DataStore.get().maps['skirmish01']).state
    st.entities.clear()
    factory = UnitFactory(st)
    for owner, x in ((0, -11000), (1, 11000)):
        for i in range(count):
            factory.spawn_ship('imperial_corvette', owner, Vec3(x, 0, i * 2))
    cam = Camera(960, 640)
    cam.target = [-11000., 0., 0.]
    cam.distance, cam.pitch, cam.yaw = 180., 55., 45.
    before = st.to_dict(precise=True)
    # Bind without an implicit warm-up query, to report cold counts separately.
    cam._scene, cam._scene_player = st, lambda: 0
    def collect_boxes(state, player_id, station_angle, ray=None):
        return scene_boxes(state, player_id, station_angle,
                           None if mode == 'eager' else ray)
    counts = dict(visibility=0, observer_checks=0, range_fingerprints=0, stat_calls=0)
    def counter(name, original):
        def wrapped(*args, **kwargs):
            counts[name] += 1
            return original(*args, **kwargs)
        return wrapped
    with patch('render.camera_geometry.scene_boxes', collect_boxes):
        with patch.object(type(st), 'can_see', counter('visibility', type(st).can_see)), \
                patch.object(SensorQueries, '_covers', counter('observer_checks', SensorQueries._covers)), \
                patch.object(SensorQueries, 'radius', counter('range_fingerprints', SensorQueries.radius)), \
                patch.object(stats, 'effective_sensor_range', counter('stat_calls', stats.effective_sensor_range)):
            cam.refresh_scene()
        cold_counts = counts.copy()
        for _ in range(3):
            cam.refresh_scene()
        samples = []
        for _ in range(21):
            start = time.perf_counter_ns()
            cam.refresh_scene()
            samples.append((time.perf_counter_ns() - start) / 1e6)
        eye = cam.eye_position()
        box_count = len(cam._camera_boxes)
    expected = safe_eye(cam.target, cam._requested_eye(), scene_boxes(st, 0, 0.),
        cam.near, cam.fov, cam.width / cam.height, cam.height)
    assert eye == expected, (eye, expected)
    assert st.to_dict(precise=True) == before, 'camera mutated precise simulation state'
    if mode == 'filtered':
        assert cold_counts['observer_checks'] == cold_counts['stat_calls'] == 0
    return dict(per_side=count, mode=mode, median_ms=statistics.median(samples),
                samples_ms=samples, cold_counts=cold_counts, box_count=box_count,
                refreshes_timed=len(samples), full_precise_state_unchanged=True,
                exhaustive_eye_equal=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path)
    ap.add_argument('--count', type=int)
    ap.add_argument('--mode', choices=('eager', 'filtered'))
    args = ap.parse_args()
    if args.count is not None:
        print('RESULT_JSON=' + json.dumps(probe(args.count, args.mode)))
        return
    if args.out is None:
        ap.error('--out is required for artifacts')
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for count in (50, 100, 250, 500):
        for mode in ('eager', 'filtered'):
            output = subprocess.check_output([sys.executable, __file__, '--count', str(count),
                                              '--mode', mode], cwd=ROOT, text=True)
            row = json.loads(next(line[12:] for line in output.splitlines()
                                  if line.startswith('RESULT_JSON=')))
            rows.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != 'samples_ms'}), flush=True)
    assert len(rows) == 8
    (args.out / 'camera_refresh_perf.json').write_text(json.dumps(rows, indent=2) + '\n')
    print('CAMERA_REFRESH_PERF_OK')


if __name__ == '__main__':
    main()
