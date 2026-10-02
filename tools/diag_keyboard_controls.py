"""Real-window regression probe: drive the actual main loop via SDL events.

Run: PYTHONPATH=. .venv/bin/python tools/diag_keyboard_controls.py [output-dir]
No dummy SDL driver: also verifies fleet-panel pixels reach the GL framebuffer.
"""
import ast
import os
from pathlib import Path
import sys

import numpy as np
import pygame
from OpenGL.GL import glReadPixels, GL_RGB, GL_UNSIGNED_BYTE

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'saves' / 'keyboard_probe'
out.mkdir(parents=True, exist_ok=True)
sys.argv = [str(ROOT / 'main.py'), '--skirmish']
os.environ['SDL_AUDIODRIVER'] = 'dummy'

# Boot the real application, then run exactly one actual loop iteration at a
# time. Wrapping the unmodified body in a for-loop preserves break/continue.
tree = ast.parse((ROOT / 'main.py').read_text())
loop_index = next(i for i, node in enumerate(tree.body) if isinstance(node, ast.While))
ns = {'__name__': '__keyboard_probe__', '__file__': str(ROOT / 'main.py')}
exec(compile(ast.Module(body=tree.body[:loop_index], type_ignores=[]), 'main.py', 'exec'), ns)
one = ast.For(target=ast.Name(id='_probe_frame', ctx=ast.Store()),
              iter=ast.Tuple(elts=[ast.Constant(value=0)], ctx=ast.Load()),
              body=tree.body[loop_index].body, orelse=[])
frame_code = compile(ast.fix_missing_locations(ast.Module(body=[one], type_ignores=[])),
                     'main.py', 'exec')


def frame():
    exec(frame_code, ns)


def press(key):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0))
    frame()
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=key, mod=0))
    frame()


def capture(name):
    # Repaint and read BEFORE flip; reading the already-swapped buffer lies on
    # some drivers. Use precisely the same camera, world and HUD as main.py.
    camera, renderer, hud = ns['camera'], ns['renderer'], ns['hud']
    camera.apply(ns['W'], ns['H'])
    renderer.draw(0.0, ns['inputc'].selection)
    hud.render(ns['inputc'].selection, None, 0, ns['paused'])
    hud.draw_gl()
    data = glReadPixels(0, 0, ns['W'], ns['H'], GL_RGB, GL_UNSIGNED_BYTE)
    image = pygame.image.frombuffer(data, (ns['W'], ns['H']), 'RGB')
    image = pygame.transform.flip(image, False, True)
    pygame.image.save(image, str(out / name))
    return pygame.surfarray.array3d(image).transpose(1, 0, 2).copy()


try:
    frame()
    ic, camera, state = ns['inputc'], ns['camera'], ns['state']
    ships = [e for e in state.entities.values() if e.alive and e.owner == 0 and e.is_ship]
    ic.selection = {e.id for e in ships[:3]}
    press(pygame.K_SPACE)
    assert camera.follow_id == min(ic.selection) and not ns['paused']
    press(pygame.K_m)
    assert camera.follow_id is None
    press(pygame.K_m)
    assert camera.follow_id == min(ic.selection)
    before = camera.yaw
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q, mod=0))
    frame()
    frame()
    assert camera.yaw < before
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_q))
    frame()
    before = camera.yaw
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e, mod=0))
    frame()
    frame()
    assert camera.yaw > before
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_e))
    frame()
    press(pygame.K_x)
    assert camera.follow_id is None and camera.pitch == 89.0
    assert camera.distance == camera.zoom_limits[1]
    assert camera.target == [0.0, 0.0, 0.0]
    capture('overview.png')
    press(pygame.K_p)
    assert ns['paused']
    tick = state.tick
    frame()
    assert state.tick == tick
    baseline = capture('fleet_closed.png')
    press(pygame.K_f)
    assert ns['hud'].fleet_panel
    panel = capture('fleet_open.png')
    x = ns['W'] - 330
    changed = np.any(panel[44:474, x:x+320] != baseline[44:474, x:x+320], axis=2)
    assert int(changed.sum()) > 500, 'fleet panel did not reach GL framebuffer'
    for kind, value in [('fleet_formation', 'wedge'), ('fleet_commander', 'aggressive')]:
        btn = next(b for b in ns['hud'].buttons
                   if b['kind'] == kind and value in b['payload'].values())
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                           button=1, pos=btn['rect'].center))
        frame()
    btn = next(b for b in ns['hud'].buttons if b['kind'] == 'fleet_create')
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                       button=1, pos=btn['rect'].center))
    frame()
    assert not ns['hud'].fleet_panel
    assert state.command_queue[-1].type == 'fleet_create'
    press(pygame.K_p)
    assert not ns['paused']
    frame()
    fleet = next(iter(state.fleets.values()))
    assert fleet.formation == 'wedge' and fleet.commander == 'aggressive'
    assert set(fleet.member_ids) == ic.selection
    press(pygame.K_f)
    press(pygame.K_ESCAPE)
    assert not ns['hud'].fleet_panel and ns['mode'] == 'game'
    press(pygame.K_ESCAPE)
    assert ns['mode'] == 'menu'
    print(f'DIAG_KEYBOARD_OK F Space Q/E X M P Esc; fleet_panel_changed_pixels={changed.sum()}; output={out}')
finally:
    ns['audio'].cleanup()
    ns['renderer'].close()
    ns['hud'].close()
    pygame.quit()
