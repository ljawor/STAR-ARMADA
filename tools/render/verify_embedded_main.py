"""Real main.py: same-window match→menu→match, local orbit and isolated quicksave."""
from pathlib import Path
import argparse
import json
import os
import runpy
import sys
import tempfile
import time
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from verify_same_window import window_identity


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'darwin': os.environ['SDL_VIDEODRIVER'] = 'cocoa'
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    import game.core
    import render.menus as menus
    from render_bridge import cpp_window
    import pygame
    original_spawn, original_get = cpp_window.spawn, pygame.event.get
    original_popen = cpp_window.subprocess.Popen

    def guarded_popen(command, *args, **kwargs):
        if command and 'armada_viewer' in str(command[0]):
            raise AssertionError('An external renderer process was launched')
        return original_popen(command, *args, **kwargs)

    cpp_window.subprocess.Popen = guarded_popen
    initial, windows, namespace = {}, [], [None]
    phase = dict(cycle=0, frame=0, menu_frames=0, finished=False)
    started = time.monotonic()

    def capture(name):
        from OpenGL.GL import glReadBuffer, glReadPixels, GL_RGB, GL_UNSIGNED_BYTE, GL_FRONT, GL_BACK
        from PIL import Image
        w, h = pygame.display.get_surface().get_size()
        glReadBuffer(GL_FRONT)
        data = glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE)
        glReadBuffer(GL_BACK)
        Image.frombytes('RGB', (w, h), data).transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(out / name)

    def spawn(*args, **kwargs):
        ns = sys._getframe(1).f_globals
        namespace[0] = ns
        result = original_spawn(*args, **kwargs)
        assert result is not None and result.embedded, 'Native renderer did not stay in-process'
        windows.append(result)
        current = window_identity()
        if not initial:
            initial.update(window=current, yaw=ns['camera'].yaw, pitch=ns['camera'].pitch)
        assert current == initial['window'], 'Match changed the native host window'
        phase.update(cycle=phase['cycle'] + 1, frame=0)
        return result

    def get(*args, **kwargs):
        events = original_get(*args, **kwargs)
        if time.monotonic() - started > 25:
            raise AssertionError('Actual-main lifecycle deadline exceeded')
        ns = namespace[0]
        if ns is None: return events
        assert window_identity() == initial['window']
        if ns['mode'] == 'menu':
            phase['menu_frames'] += 1
            if phase['menu_frames'] == 3:
                capture('menu-return.png')
                ns['start_game']()
                ns['mode'] = 'game'
            return events
        phase['frame'] += 1
        frame = phase['frame']
        if phase['cycle'] == 1:
            if frame == 6:
                events.append(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(600, 400)))
            if frame == 7:
                events.append(pygame.event.Event(pygame.MOUSEMOTION, pos=(760, 500), rel=(160, 100), buttons=(0, 0, 1)))
            if frame == 8:
                events.append(pygame.event.Event(pygame.MOUSEBUTTONUP, button=3, pos=(760, 500)))
            if frame == 10:
                events.append(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F5, mod=0))
            if frame == 18:
                assert ns['camera'].yaw != initial['yaw'] and ns['camera'].pitch != initial['pitch'], 'Local orbit failed'
                capture('match-orbit.png')
                initial.update(after_yaw=ns['camera'].yaw, after_pitch=ns['camera'].pitch)
                ns['leave_game']()
        elif phase['cycle'] == 2 and frame == 10:
            capture('second-match.png')
            phase['finished'] = True
            events.append(pygame.event.Event(pygame.QUIT))
        return events

    with tempfile.TemporaryDirectory(prefix='embedded-main-user-', dir=out) as directory:
        user = Path(directory)
        for key, value in dict(USER_DIR=user, SAVES_DIR=user / 'saves', SETTINGS_PATH=user / 'settings.json',
                CAMPAIGN_PATH=user / 'campaign.json', BALANCE_PATH=user / 'balance.json').items():
            setattr(menus, key, str(value))
        cpp_window.spawn, pygame.event.get = spawn, get
        sys.argv = [str(ROOT / 'main.py'), '--skirmish']
        try:
            runpy.run_path(str(ROOT / 'main.py'), run_name='__main__')
            assert (user / 'saves/quicksave.json').is_file(), 'Natural F5 did not save'
            initial['quicksave'] = True
        finally:
            cpp_window.spawn, pygame.event.get = original_spawn, original_get
            cpp_window.subprocess.Popen = original_popen
            for window in windows: window.terminate()
    assert phase['finished'] and len(windows) == 2 and phase['menu_frames'] >= 3, phase
    initial.update(phase=phase, embedded_sessions=len(windows), external_viewer_processes=0,
                   presentation='C++ Metal/D3D scene → CPU readback → existing GL window')
    (out / 'verification.json').write_text(json.dumps(initial, indent=2))
    print(json.dumps(initial, indent=2))


if __name__ == '__main__':
    main()
