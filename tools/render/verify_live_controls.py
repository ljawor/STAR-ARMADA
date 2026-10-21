"""Actual-driver smoke for native input ownership and right-drag transport.

Run from the repository with its Python environment. This launches the real bgfx viewer;
SDL test events are injected through its normal event pump, not directly into Python.
It is not a hardware/OS-input test or a performance benchmark.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    viewer = ROOT / 'render_cpp/build-w02/armada_viewer'
    report = out / 'viewer.json'
    input_path = out / 'input.ring'
    cmd = [str(viewer), '--assets', str(ROOT), '--snapshot', str(ROOT / 'assets/cpp/catalogue.snap'),
           '--input-ring', str(input_path), '--input-slots', '64', '--exercise-controls',
           '--camera-exercise', '--frames', '140', '--warmup', '0', '--report', str(report)]
    process = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        output = process.communicate(timeout=30)[0]
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise RuntimeError('native input probe exceeded 30 seconds')
    (out / 'viewer-output.txt').write_bytes(output)
    if process.returncode:
        raise RuntimeError(output.decode(errors='replace'))
    data = json.loads(report.read_text())
    states = data['control_exercise']
    assert len(states) == 4, states
    initial = states[0]
    for pose in states[1:]:
        assert all(pose[key] == initial[key] for key in ('target', 'distance', 'yaw', 'pitch')), pose
    # The native viewer records, but must not execute, the live game's gestures and Escape.
    from render_bridge import input as wire
    reader = wire.InputReader(input_path, from_oldest=True)
    try:
        events = [event for batch in reader.read() for event in batch]
    finally:
        reader.close()
    assert any(e.kind == wire.BUTTON_DOWN and e.button == 3 for e in events), events
    assert any(e.kind == wire.KEY_DOWN and e.code == wire.KEYCODE_ESCAPE for e in events), events
    assert data['wall_frame']['samples'] == 140, 'Escape terminated the native viewer'
    import pygame
    from types import SimpleNamespace
    from game.core.manager import GameManager
    from game.data.store import DataStore
    from render.camera import Camera
    from render.hud import HUD
    from render.input import InputController
    from render.input_bridge import RingInput
    pygame.font.init()
    manager = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
    camera = Camera(1280, 800)
    camera._view = camera._proj = ()  # analytic unprojection; no Python GL context
    hud = HUD(1280, 800, manager.state)
    exits = []
    app = SimpleNamespace(flash=lambda *_: None, request_exit=lambda: exits.append(True))
    controller = InputController(manager.state, camera, hud, app)
    try:
        with RingInput(input_path, controller, (1280, 800), from_oldest=True) as bridge:
            bridge.poll()
            receipt = bridge.report()
        assert abs(camera.yaw - 5.) < 0.001, camera.yaw
        assert abs(camera.pitch - 37.) < 0.001, camera.pitch
        assert not exits, 'first Escape must cancel/arm, not leave the game'
        assert receipt['unmapped'] == 0, receipt
        assert receipt['batches_skipped'] == 0, receipt
        receipt.update(camera_yaw=camera.yaw, camera_pitch=camera.pitch,
                       native_frames=data['wall_frame']['samples'], backend=data['backend'])
        (out / 'verification.json').write_text(json.dumps(receipt, indent=2))
        print(json.dumps(receipt, indent=2))
    finally:
        hud.close()


if __name__ == '__main__':
    main()
