"""Real Cocoa SDL/GL replay workflow; never a cross-platform acceptance claim.
Run: PYTHONPATH=. .venv/bin/python tools/diag_replay_workflow.py --out DIR
"""
import argparse
import ast
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=True)
if os.environ.get('SDL_VIDEODRIVER') == 'dummy':
    raise RuntimeError('This diagnostic requires a real GL window server.')
os.environ['SDL_AUDIODRIVER'] = 'dummy'
import pygame
import numpy as np
from OpenGL.GL import glReadPixels, glGetError, glViewport, GL_RGB, GL_UNSIGNED_BYTE
import render.menus as menus
menus.USER_DIR = str(out / 'user')
menus.SAVES_DIR = str(out / 'user/saves')
menus.SETTINGS_PATH = str(out / 'user/saves/settings.json')
menus.CAMPAIGN_PATH = str(out / 'user/saves/campaign.json')
sys.argv = [str(ROOT / 'main.py')]
tree = ast.parse((ROOT / 'main.py').read_text())
loop_index = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.While))
ns = {'__name__': '__replay_probe__', '__file__': str(ROOT / 'main.py')}
exec(compile(ast.Module(body=tree.body[:loop_index], type_ignores=[]), 'main.py', 'exec'), ns)
one = ast.For(target=ast.Name(id='_probe_frame', ctx=ast.Store()),
              iter=ast.Tuple(elts=[ast.Constant(value=0)], ctx=ast.Load()),
              body=tree.body[loop_index].body, orelse=[])
code = compile(ast.fix_missing_locations(ast.Module(body=[one], type_ignores=[])), 'main.py', 'exec')
class Clock:
    def tick(self, rate):
        return 34
ns['clock'] = Clock()
capture_name = None
real_flip = pygame.display.flip
captures = []
def flip():
    global capture_name
    if capture_name:
        w, h = ns['W'], ns['H']
        raw = glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE)
        image = pygame.transform.flip(pygame.image.frombuffer(raw, (w, h), 'RGB'), False, True)
        path = out / capture_name
        pygame.image.save(image, str(path))
        pixels = pygame.surfarray.array3d(image)
        assert np.count_nonzero(pixels.max(axis=2) > 40) > 2000, 'blank framebuffer'
        assert glGetError() == 0, 'GL error'
        captures.append(str(path))
        capture_name = None
    real_flip()
pygame.display.flip = flip

def frame(name=None):
    global capture_name
    capture_name = name
    exec(code, ns)

def click(action, payload=None):
    b = next(b for b in ns['menu'].buttons if b['action'] == action and
             (payload is None or b['payload'] == payload))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=b['rect'].center))
    frame()
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=b['rect'].center))
    frame()

def press(key):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0))
    frame()
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=key, mod=0))
    frame()

def precise():
    return json.loads(json.dumps(ns['state'].to_dict(precise=True)))

try:
    pygame.event.clear()
    ns['menu'].screen = 'main'
    frame()
    click('start_skirmish')
    click('launch_skirmish')
    assert ns['mode'] == 'game' and ns['recording'] is not None
    own = next(e.id for e in ns['state'].entities.values() if e.owner == 0 and e.is_ship)
    ns['inputc'].selection = {own}
    press(pygame.K_s)
    for _ in range(30):
        frame()
    press(pygame.K_ESCAPE)
    assert ns['mode'] == 'menu'
    files = sorted((out / 'user/replays').glob('*.json'))
    assert len(files) == 1, 'automatic match recording did not persist exactly once'
    original = files[0].read_bytes()
    data = json.loads(original)
    assert len(data['commands']) == 1 and data['commands'][0]['cmd']['type'] == 'stop'
    assert data['end_tick'] > data['commands'][0]['tick'] + 20
    for i in range(14):
        (files[0].parent / f'fixture-{i:02d}.json').write_bytes(original)
    broken = files[0].parent / 'broken.json'
    broken.write_text('{bad')
    for width, height in ((1024, 768), (1280, 800)):
        pygame.display.set_mode((width, height), pygame.DOUBLEBUF | pygame.OPENGL)
        glViewport(0, 0, width, height)
        ns['W'], ns['H'] = width, height
        ns['menu'].close()
        ns['menu'] = menus.MenuStack(width, height)
        ns['menu'].open_replays()
        seen = set()
        for page in range(3):
            frame(f'browser-{width}-{page}.png')
            menu = ns['menu']
            seen.update(b['payload'] for b in menu.buttons if b['action'] == 'play_replay')
            assert all(pygame.Rect(0, 0, width, height).contains(r) for r in menu.replay_text_bounds)
            assert all(not a.colliderect(b) for i, a in enumerate(menu.replay_text_bounds)
                       for b in menu.replay_text_bounds[i + 1:]), 'overlapping replay text'
            if page < 2:
                click('replay_page', 1)
        assert len(seen) == 16, 'paging did not expose every fixture'
        menu.open_replays()
        frame()
        click('play_replay', str(broken))
        assert 'JSON' in menu.replay_notice and ns['mode'] == 'menu'
        frame(f'error-{width}.png')
        click('play_replay', str(files[0].parent / 'fixture-00.json'))
        assert ns['mode'] == 'game' and ns['playback'] is not None, 'main menu did not launch playback'
        press(pygame.K_p)
        assert ns['playback'].paused
        before = precise()
        ns['inputc'].selection = {own}
        for key in (pygame.K_s, pygame.K_j, pygame.K_b, pygame.K_g, pygame.K_F5, pygame.K_F9):
            press(key)
        for button in (1, 3):
            for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                pygame.event.post(pygame.event.Event(kind, button=button, pos=(width - 100, 200)))
                frame()
        assert precise() == before, 'playback input mutated the simulation'
        press(pygame.K_RIGHTBRACKET)
        assert ns['playback'].speed == 2.
        frame(f'paused-{width}.png')
        assert not ns['hud'].buttons, 'replay HUD still advertises gameplay actions'
        press(pygame.K_p)
        for _ in range(100):
            frame()
            if ns['playback'].ended:
                break
        assert ns['state'].tick == data['end_tick'], 'duration/end handling failed'
        final = precise()
        frame(f'ended-{width}.png')
        assert precise() == final
        press(pygame.K_ESCAPE)
        assert ns['mode'] == 'menu' and files[0].read_bytes() == original
    report = dict(result='DIAG_REPLAY_OK', driver=pygame.display.get_driver(),
                  captures=captures, resolutions=[[1024, 768], [1280, 800]],
                  commands=len(data['commands']), end_tick=data['end_tick'],
                  limitation='Local macOS SDL/GL automation only; not cross-platform interactive acceptance.')
    (out / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
finally:
    pygame.display.flip = real_flip
    ns['menu'].close()
    for key, method in [('audio', 'cleanup'), ('renderer', 'close'), ('hud', 'close')]:
        if ns.get(key) is not None:
            getattr(ns[key], method)()
    pygame.quit()
