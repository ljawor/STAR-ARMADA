"""Bounded real-main resolution probe; all user data lives under --out.

Run each mode in its own process under an external process-group deadline. Navigates actual
menu hitboxes to Settings and Skirmish, then records native target/readback and host sizes.
This is macOS source integration evidence, not Windows/Retina/package acceptance.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import runpy
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--resolution', required=True)
    parser.add_argument('--fullscreen', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    if sys.platform == 'darwin':
        os.environ['SDL_VIDEODRIVER'] = 'cocoa'
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    import game.core
    from render import menus
    from render_bridge import cpp_window
    import pygame
    user = out / 'user'
    user.mkdir(exist_ok=True)
    settings_path = user / 'settings.json'
    settings_path.write_text(json.dumps({'resolution': args.resolution,
        'fullscreen': args.fullscreen, 'cinematics_enabled': False,
        'reduced_motion': True, 'language': 'en', 'music_volume': 0.0, 'sfx_volume': 0.0}),
        encoding='utf-8')
    for key, path in {'USER_DIR': user, 'SAVES_DIR': user / 'saves',
                      'SETTINGS_PATH': settings_path, 'CAMPAIGN_PATH': user / 'campaign.json',
                      'BALANCE_PATH': user / 'balance.json'}.items():
        setattr(menus, key, str(path))
    original_get, original_flip = pygame.event.get, pygame.display.flip
    original_spawn = cpp_window.spawn
    namespace = [None]
    phase = {'settings_seen': False, 'back': False, 'native_frames': 0, 'done': False}
    result = {'requested_resolution': args.resolution, 'requested_fullscreen': args.fullscreen}
    started = time.monotonic()

    def click(menu, action):
        button = next((b for b in menu.buttons if b['action'] == action), None)
        if button is None:
            return []
        return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button['rect'].center)]

    def get(*a, **kw):
        namespace[0] = ns = sys._getframe(1).f_globals
        events = original_get(*a, **kw)
        if time.monotonic() - started > 45:
            raise AssertionError('Resolution application probe exceeded its inner deadline')
        if ns.get('mode') != 'menu':
            if phase['done']:
                return events + [pygame.event.Event(pygame.QUIT)]
            return events
        menu = ns['menu']
        if menu.screen == 'splash':
            return events + [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)]
        if menu.screen == 'main':
            return events + click(menu, 'start_skirmish' if phase['back'] else 'goto_settings')
        if menu.screen == 'settings' and phase['settings_seen']:
            phase['back'] = True
            return events + click(menu, 'goto_main')
        if menu.screen == 'skirmish':
            return events + click(menu, 'launch_skirmish')
        return events

    def capture(name):
        from OpenGL.GL import glReadPixels, glFinish, GL_RGB, GL_UNSIGNED_BYTE, GL_VIEWPORT, glGetIntegerv
        glFinish()
        size = pygame.display.get_surface().get_size()
        viewport = tuple(int(n) for n in glGetIntegerv(GL_VIEWPORT))
        assert viewport[2:] == size, (viewport, size)
        data = glReadPixels(0, 0, *size, GL_RGB, GL_UNSIGNED_BYTE)
        surface = pygame.image.frombytes(bytes(data), size, 'RGB')
        surface = pygame.transform.flip(surface, False, True)
        pygame.image.save(surface, str(out / name))
        result[name] = {'size': size, 'viewport': viewport,
                        'sha256': hashlib.sha256((out / name).read_bytes()).hexdigest()}

    def flip():
        ns = namespace[0]
        if ns is not None and ns.get('mode') == 'menu' and ns['menu'].screen == 'settings':
            if not phase['settings_seen']:
                surface = pygame.display.get_surface()
                size = surface.get_size()
                fullscreen = bool(surface.get_flags() & pygame.FULLSCREEN)
                label = f'Current resolution: {size[0]} × {size[1]} · ' + ('Fullscreen' if fullscreen else 'Windowed')
                assert label in ns['menu'].settings_rendered_text
                assert ns['menu'].settings['resolution'] == args.resolution
                result.update(actual_size=size, actual_fullscreen=fullscreen,
                              settings_text=ns['menu'].settings_rendered_text)
                capture('settings.png')
                phase['settings_seen'] = True
        elif ns is not None and ns.get('mode') == 'game':
            phase['native_frames'] += 1
            if phase['native_frames'] == 8:
                window = ns['CPP']['window']
                assert window is not None and window.embedded
                assert not ns['CPP']['failed']
                size = pygame.display.get_surface().get_size()
                assert tuple(window.size) == size
                assert len(window._pixels) == size[0] * size[1] * 4
                assert (ns['hud'].width, ns['hud'].height) == ns['CPP_HUD_SIZE']
                assert abs(ns['camera'].aspect - size[0] / size[1]) < 1e-9
                # Native readback must carry a real composed scene, not merely a sized allocation.
                import numpy as np
                rgb = np.frombuffer(window._pixels, dtype=np.uint8).reshape(size[1], size[0], 4)[:, :, :3]
                assert int((rgb.max(axis=2) > 25).sum()) > 1000
                result.update(native_target=window.size, native_frames=phase['native_frames'],
                              native_readback_bytes=len(window._pixels),
                              hud_size=ns['CPP_HUD_SIZE'], camera_aspect=ns['camera'].aspect,
                              nonblack_pixels=int((rgb.max(axis=2) > 25).sum()))
                capture('match.png')
                phase['done'] = True
        original_flip()

    def spawn(*a, **kw):
        namespace[0] = sys._getframe(1).f_globals
        return original_spawn(*a, **kw)

    pygame.event.get, pygame.display.flip, cpp_window.spawn = get, flip, spawn
    sys.argv = [str(ROOT / 'main.py')]
    try:
        runpy.run_path(str(ROOT / 'main.py'), run_name='__main__')
    finally:
        pygame.event.get, pygame.display.flip, cpp_window.spawn = original_get, original_flip, original_spawn
        result.update(phase=phase, elapsed_seconds=time.monotonic() - started)
        (out / 'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    assert phase['done'] and phase['settings_seen'], phase
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
