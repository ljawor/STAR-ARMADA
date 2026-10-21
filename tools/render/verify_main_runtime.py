"""Exercise real main.py and Metal/bgfx with isolated user files and a bounded SDL gesture.

This is a native integration smoke, not hardware input, full-match or performance acceptance.
Run with the repository's Python environment on a graphical desktop, under an outer deadline.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--orbit', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    if sys.platform == 'darwin':
        os.environ['SDL_VIDEODRIVER'] = 'cocoa'
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    import game.core
    import render.menus as menus
    import render_bridge.cpp_window as native
    import pygame

    with tempfile.TemporaryDirectory(prefix='user-', dir=out) as directory:
        user = Path(directory)
        for key, value in dict(USER_DIR=user, SAVES_DIR=user / 'saves',
                               SETTINGS_PATH=user / 'settings.json',
                               CAMPAIGN_PATH=user / 'campaign.json',
                               BALANCE_PATH=user / 'balance.json').items():
            setattr(menus, key, str(value))
        original_popen, original_spawn = native.subprocess.Popen, native.spawn
        original_get = pygame.event.get
        processes, initial, captured, namespace = [], {}, {}, {}
        clock = {'native_start': None, 'started': time.monotonic()}

        def popen(command, *a, **kw):
            if command and str(command[0]).endswith('armada_viewer'):
                command = list(command) + ['--seconds', '7', '--screenshot', str(out / 'capture.png'),
                                           '--report', str(out / 'viewer.json')]
                if args.orbit:
                    command.append('--camera-exercise')
                clock['native_start'] = time.monotonic()
            process = original_popen(command, *a, **kw)
            if command and str(command[0]).endswith('armada_viewer'):
                processes.append(process)
            return process

        def spawn(*a, **kw):
            namespace.update(sys._getframe(1).f_globals)
            # Keep the actual globals dictionary, not a frozen copy of runtime state.
            captured_globals[0] = sys._getframe(1).f_globals
            initial.update(yaw=namespace['camera'].yaw, pitch=namespace['camera'].pitch)
            return original_spawn(*a, **kw)

        captured_globals: list[dict | None] = [None]

        def get(*a, **kw):
            events = original_get(*a, **kw)
            now = time.monotonic()
            age = now - (clock['native_start'] or clock['started'])
            ns = captured_globals[0]
            if ns is not None and age > 4.5 and not captured:
                camera, cpp = ns['camera'], ns['CPP']
                session, bridge = cpp.get('session'), cpp.get('input')
                captured.update(initial=initial, camera=dict(yaw=camera.yaw, pitch=camera.pitch),
                                shared_hud=session is not None and session.hud is ns['hud'],
                                bridge=bridge.report() if bridge else None,
                                cpp_failed=cpp.get('failed'), mode=ns['mode'], tick=ns['state'].tick)
            if age > 8.0 or now - clock['started'] > 18:
                events.append(pygame.event.Event(pygame.QUIT))
            return events

        native.subprocess.Popen, native.spawn, pygame.event.get = popen, spawn, get
        sys.argv = [str(ROOT / 'main.py'), '--skirmish']
        try:
            runpy.run_path(str(ROOT / 'main.py'), run_name='__main__')
        finally:
            for process in processes:
                native.stop(process)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            native.subprocess.Popen, native.spawn, pygame.event.get = original_popen, original_spawn, original_get
            (out / 'verification.json').write_text(json.dumps(captured, indent=2), encoding='utf-8')

        assert captured.get('shared_hud'), captured
        assert not captured['cpp_failed'], captured
        delta_yaw, delta_pitch = ((40, 18) if args.orbit else (0, 0))
        assert abs(captured['camera']['yaw'] - (initial['yaw'] - delta_yaw)) < .01, captured
        assert abs(captured['camera']['pitch'] - (initial['pitch'] - delta_pitch)) < .01, captured
        if args.orbit:
            assert captured['bridge']['events_delivered'] >= 5, captured
        assert all(process.poll() is not None for process in processes)
        viewer = json.loads((out / 'viewer.json').read_text(encoding='utf-8'))
        assert viewer['live']['producer_frames_adopted'] > 0, viewer['live']
        assert viewer['hud']['full_frames'] > 0, viewer['hud']
        assert viewer['camera_ring']['decode_failures'] == 0, viewer['camera_ring']
        assert viewer['live']['decode_failures'] == 0, viewer['live']
        assert viewer['camera']['yaw'] == captured['camera']['yaw'], viewer['camera']
        assert viewer['camera']['pitch'] == captured['camera']['pitch'], viewer['camera']
        receipt = dict(captured, orbit=args.orbit, backend=viewer['backend'],
                       native_camera=viewer['camera'], camera_ring=viewer['camera_ring'],
                       hud=viewer['hud'], adopted_frames=viewer['live']['producer_frames_adopted'],
                       code_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                                    for p in ('main.py', 'render/input.py', 'render/input_bridge.py',
                                              'render_bridge/live.py', 'render_cpp/src/viewer.cpp')})
        (out / 'verification.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
