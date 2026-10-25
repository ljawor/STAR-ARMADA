"""Bounded actual main.py natural-input Host / eight-human lobby captures.

No menu/simulation substitution: only isolated user paths and event injection.
Invoke under an external process-group deadline. Refuses a competing game.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    for row in subprocess.check_output(['ps', '-axo', 'pid=,args='], text=True).splitlines():
        parts = row.split()
        if any(Path(token).name in ('main.py', 'armada_viewer') for token in parts[1:]) and '-c' not in parts:
            raise SystemExit('Close the running game before this GPU diagnostic: ' + row)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    if sys.platform == 'darwin':
        os.environ['SDL_VIDEODRIVER'] = 'cocoa'
    import game.core
    from render import menus
    import pygame
    user = out / 'user'
    user.mkdir()
    settings = user / 'settings.json'
    settings.write_text(json.dumps(dict(resolution='1440x900', fullscreen=False,
        cinematics_enabled=True, reduced_motion=True, language='en', music_volume=0, sfx_volume=0)), encoding='utf-8')
    for key, path in {'USER_DIR': user, 'SAVES_DIR': user / 'saves', 'SETTINGS_PATH': settings,
                      'CAMPAIGN_PATH': user / 'campaign.json', 'BALANCE_PATH': user / 'balance.json'}.items():
        setattr(menus, key, str(path))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    real_get, real_flip = pygame.event.get, pygame.display.flip
    state = dict(ns=None, stage='navigate', captures=[])
    started = time.monotonic()
    def press(menu, action, payload=None):
        b = next(b for b in menu.buttons if b['action'] == action and (payload is None or b['payload'] == payload))
        for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            pygame.event.post(pygame.event.Event(kind, pos=b['rect'].center, button=1))
    def events(*a, **kw):
        state['ns'] = sys._getframe(1).f_globals
        assert time.monotonic() - started < 40, 'Main host capture inner deadline'
        return real_get(*a, **kw)
    def capture(menu, name):
        from OpenGL.GL import glFinish, glReadPixels, GL_RGB, GL_UNSIGNED_BYTE
        glFinish()
        size = pygame.display.get_surface().get_size()
        assert size == (1440, 900)
        frame = pygame.image.frombytes(bytes(glReadPixels(0, 0, *size, GL_RGB, GL_UNSIGNED_BYTE)), size, 'RGB')
        path = out / name
        pygame.image.save(pygame.transform.flip(frame, False, True), str(path))
        movie = menu._menu_movie
        state['captures'].append(dict(capture=name, screen=menu.screen, size=size,
            options=menu.lan_options.copy(), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            movie_sha256=hashlib.sha256(Path(movie._zip.filename).read_bytes()).hexdigest()))
    def flip():
        ns = state['ns']
        if ns and ns.get('mode') == 'menu':
            m = ns['menu']
            if state['stage'] == 'navigate':
                for screen, action in [('splash', 'goto_main'), ('main', 'goto_lan'), ('lan', 'lan_host_setup')]:
                    if m.screen == screen:
                        press(m, action)
                        break
                if m.screen == 'lan_host':
                    capture(m, 'main-host-duel.png')
                    press(m, 'lan_map', 'skirmish05')
                    state['stage'] = 'eight'
            elif state['stage'] == 'eight':
                assert m.screen == 'lan_host'
                if m.lan_options['human_count'] < 8:
                    press(m, 'lan_humans', 1)
                else:
                    assert m.lan_options['map_id'] == 'skirmish05'
                    capture(m, 'main-host-eight.png')
                    press(m, 'lan_field', 'lan_port')
                    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, mod=pygame.KMOD_CTRL, unicode='a'))
                    pygame.event.post(pygame.event.Event(pygame.TEXTINPUT, text=str(port)))
                    state['stage'] = 'create'
            elif state['stage'] == 'create':
                assert m.lan_port == str(port)
                press(m, 'lan_connect')
                state['stage'] = 'lobby'
            elif state['stage'] == 'lobby':
                assert not m.lan_notice, m.lan_notice
                if m.screen == 'lan_lobby':
                    assert m.lan_session.snapshot['options']['human_count'] == 8
                    assert not m.lan_session.snapshot['can_start']
                    assert len(m.lan_session.snapshot['players']) == 1
                    assert any('08' == text for text in m.lan_rendered_text)
                    capture(m, 'main-lobby-eight-open.png')
                    state['stage'] = 'done'
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
        real_flip()
    pygame.event.get, pygame.display.flip = events, flip
    sys.argv = [str(ROOT / 'main.py')]
    runpy.run_path(str(ROOT / 'main.py'), run_name='__main__')
    assert state['stage'] == 'done', state['stage']
    assert len(state['captures']) == 3
    (out / 'capture.json').write_text(json.dumps(dict(captures=state['captures'], count=3,
        scope='Actual main.py natural-input navigation, Host duet/eight-human setup and real TCP eight-slot lobby. No clients joined; no gameplay/performance claim.'), indent=2), encoding='utf-8')
    print('LAN_MAIN_HOST_OK', out)


if __name__ == '__main__':
    main()
