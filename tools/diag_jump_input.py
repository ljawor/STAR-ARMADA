"""Real SDL/GL destination-picking probe; no dummy video driver.

PYTHONPATH=. .venv/bin/python tools/diag_jump_input.py [output-dir]
Boots the real application's object graph and dispatches posted SDL events to
its real InputController, then reads final composited GL pixels before flip.
"""
import ast
import os
from pathlib import Path
import sys
from typing import Any
import numpy as np
import pygame
from OpenGL.GL import glReadPixels, GL_RGB, GL_UNSIGNED_BYTE


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game.core.vectors import Vec3
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'saves' / 'jump_probe'
out.mkdir(parents=True, exist_ok=True)
sys.argv = [str(ROOT / 'main.py'), '--skirmish']
os.environ['SDL_AUDIODRIVER'] = 'dummy'
tree = ast.parse((ROOT / 'main.py').read_text())
stop = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.While))
ns: dict[str, Any] = {'__name__': '__jump_probe__', '__file__': str(ROOT / 'main.py')}
exec(compile(ast.Module(body=tree.body[:stop], type_ignores=[]), 'main.py', 'exec'), ns)
ic, st, camera, hud = (ns[k] for k in ('inputc', 'state', 'camera', 'hud'))


def dispatch(*events):
    for event in events:
        pygame.event.post(event)
    for event in pygame.event.get():
        ic.handle_event(event)


def press(key):
    dispatch(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0),
             pygame.event.Event(pygame.KEYUP, key=key))


def click(pos, button=1):
    dispatch(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button),
             pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button))


def capture(name, flash=False):
    camera.apply(ns['W'], ns['H'])
    ns['renderer'].draw(0, ic.selection)
    hud.render(ic.selection, None, 0, False,
               ns['flash_msg'] if flash else '', 2.5 if flash else 0)
    hud.draw_gl()
    raw = glReadPixels(0, 0, ns['W'], ns['H'], GL_RGB, GL_UNSIGNED_BYTE)
    image = pygame.transform.flip(pygame.image.frombuffer(raw, (ns['W'], ns['H']), 'RGB'), False, True)
    pygame.image.save(image, str(out / name))
    return pygame.surfarray.array3d(image).transpose(1, 0, 2).copy()


try:
    pygame.event.clear()
    ship = next(e for e in st.entities.values() if e.owner == 0 and e.is_ship)
    ic.selection = {ship.id}
    camera.target = [0, 0, 0]
    camera.pitch = 89
    camera.distance = camera.zoom_limits[1]
    baseline = capture('idle.png')
    press(pygame.K_j)
    assert not st.command_queue and ic._pending_jump == (ship.id,)
    armed = capture('armed.png')  # deliberately no transient flash
    changed = np.any(armed != baseline, axis=2)
    assert changed.sum() > 100, 'persistent jump prompt missing from GL pixels'
    assert any(r.collidepoint((20, 100)) for r in hud.blocked_rects)
    click((20, 100))
    assert not st.command_queue and ic._pending_jump is not None
    assert 'HUD' in ns['flash_msg']
    # Actual ground-plane unprojection; no stubbed camera coordinates.
    screen = camera.world_to_screen(6000, 0, 5000)
    assert screen is not None
    pos = tuple(int(v) for v in screen[:2])
    world = camera.screen_to_world(*pos)
    destination = Vec3(world[0], 0, world[2])
    st.explored_cells.setdefault(0, set()).add(st.visibility_cell(destination))
    assert st.is_position_explored(0, destination)
    assert not st.is_position_visible(0, destination)
    before = list(camera.target)
    click(pos)
    cmd = st.command_queue[-1]
    assert cmd.type == 'jump' and cmd.unit_ids == (ship.id,)
    assert np.allclose(cmd.target_pos, (world[0], 0, world[2]))
    assert camera.target == before and not ic.dragging
    assert ic.selection == {ship.id}
    st.command_queue.clear()
    press(pygame.K_j)
    r = hud.minimap_rect
    scale = (st.map_info.bounds / 2) / (r.width / 2 - 4)
    assert not st.is_position_explored(0, Vec3(50 * scale, 0, -50 * scale))
    click((r.centerx + 50, r.centery - 50))
    assert np.allclose(st.command_queue[-1].target_pos, (50 * scale, 0, -50 * scale))
    assert camera.target == before
    st.command_queue.clear()
    press(pygame.K_j)
    # Explored minimap position at the own ship, derived from HUD's mapping.
    own = (int(r.centerx + ship.pos.x / scale), int(r.centery + ship.pos.z / scale))
    destination = Vec3((own[0] - r.centerx) * scale, 0,
                       (own[1] - r.centery) * scale)
    assert st.is_position_explored(0, destination)
    assert st.is_position_visible(0, destination)
    click(own)
    assert len(st.command_queue) == 1 and ic._pending_jump is None
    assert np.allclose(st.command_queue[-1].target_pos,
                       (destination.x, destination.y, destination.z))
    # Preserve the actual command's precise division/multiplication result.
    destination = Vec3(*st.command_queue[-1].target_pos)
    assert ns['flash_msg'] == 'hyperspace jump ordered'
    ns['gm'].commands.consume()
    assert ship.jump_charge > 0 and ship.jump_target == destination
    acceptance = capture('explored_accepted.png', flash=True)
    assert np.any(acceptance != armed), 'acceptance feedback not visible'
    ns['gm']._update_jumps(ship.jump_charge)
    assert ship.pos == destination and ship.jump_target is None
    ship.ability_cooldowns['_jump_cd'] = 0
    press(pygame.K_j)
    click((640, 300), 3)
    assert not st.command_queue and ic._pending_jump is None
    press(pygame.K_j)
    dispatch(pygame.event.Event(pygame.WINDOWFOCUSLOST))
    assert ic._pending_jump is None
    print(f'DIAG_JUMP_INPUT_OK explored-world/unexplored-minimap/sensed-minimap/sim-completion/HUD/right/focus; video={pygame.display.get_driver()}; prompt_pixels={changed.sum()}; output={out}')
finally:
    ns['audio'].cleanup()
    ns['renderer'].close()
    hud.close()
    pygame.quit()
