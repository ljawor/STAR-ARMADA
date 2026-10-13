"""Controlled issue #79 manager combat + real Cocoa SDL/GL/input diagnostic.

PYTHONPATH=. .venv/bin/python tools/diag_crew_damage.py --out DIR
Fixture hull/crew and queued initial hits are controlled; reattack/destruction
uses the real SDL event queue, InputController picking and production weapons.
This is not a natural human playthrough or native Windows acceptance.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pygame
from OpenGL import GL
from PIL import Image
from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.data.store import DataStore
from render.camera import Camera
from render.hud import HUD
from render.input import InputController
from render.renderer import Renderer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if os.environ.get('SDL_VIDEODRIVER') == 'dummy':
        raise RuntimeError('A real SDL/OpenGL display is required')
    pygame.display.init()
    pygame.font.init()
    report = {'scenarios': []}
    try:
        for width, height in ((1280, 800), (1024, 768)):
            pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
            pygame.event.pump()
            GL.glViewport(0, 0, width, height)
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glClearColor(.008, .012, .025, 1)
            report['sdl_driver'] = pygame.display.get_driver()
            report['gl_renderer'] = GL.glGetString(GL.GL_RENDERER).decode()
            for kind in ('ship', 'station'):
                DataStore.reset()
                map_def = json.loads(json.dumps(DataStore.get().maps['skirmish01']))
                for player in map_def['players']:
                    player['is_ai'] = False
                gm = GameManager.start_skirmish(map_def)
                st = gm.state
                st.entities.clear()
                st.discovered_planets.clear()
                st.explored_cells.clear()
                gm.factory.spawn_station('command_station', 0, Vec3(-9000, 0, 0))
                gm.factory.spawn_station('command_station', 1, Vec3(9000, 0, 0))
                source = gm.factory.spawn_ship('imperial_cruiser', 0, Vec3(0, 0, -250))
                target = (gm.factory.spawn_ship('imperial_cruiser', 1, Vec3(0, 0, 250))
                          if kind == 'ship' else
                          gm.factory.spawn_station('defense_platform', 1, Vec3(0, 0, 250)))
                target.crew = target.max_crew = 2
                target.hull = 400
                target.max_shield_quad = 0
                target.shields = dict.fromkeys(target.shields, 0.0)
                target.sensor_range = 0
                source.weapon_cooldowns = dict.fromkeys(range(10), 100.0)
                target.weapon_cooldowns = dict.fromkeys(range(10), 100.0)
                st.grid.rebuild(st.entities)
                gm.visibility.update()
                camera = Camera(width, height)
                camera.target = [0, 0, 0]
                camera.yaw, camera.pitch, camera.distance = 25, 65, 2600
                renderer = Renderer(st, camera)
                renderer.diff_render = True
                renderer.time = 3.0
                renderer.skip = {'star', 'jumppoints', 'nebulas', 'sites', 'shields'}
                hud = HUD(width, height, st)
                ctrl = InputController(st, camera, hud, SimpleNamespace(flash=lambda message: None))
                labels = []
                original_label = hud._label
                def label(x, y, text, color=None, font=None):
                    labels.append((str(text), pygame.Rect(x, y, *(font or hud.font).size(str(text)))))
                    original_label(x, y, text, color, font)
                hud._label = label
                row = {'width': width, 'kind': kind, 'captures': [], 'launches': 0}
                def fired(event):
                    if event.data.get('attacker_id') == source.id:
                        row['launches'] += 1
                st.events.subscribe('weapon_fired', fired)
                def capture(stage, entity):
                    before = json.loads(json.dumps(st.to_dict(precise=True)))
                    labels.clear()
                    renderer.draw(0, {entity.id})
                    hud.render({entity.id}, None, 0, False)
                    hud.draw_gl()
                    GL.glFinish()
                    raw = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
                    pixels = np.flipud(np.frombuffer(raw, np.uint8).reshape(height, width, 3)).copy()
                    assert GL.glGetError() == GL.GL_NO_ERROR
                    assert before == json.loads(json.dumps(st.to_dict(precise=True))), 'render mutated simulation'
                    needles = ['CREW', 'LIFE'] + (['ABANDONED'] if entity.crew == 0 else [])
                    for needle in needles:
                        matches = [(text, rect) for text, rect in labels if needle in text and rect.x < 330]
                        assert matches, f'missing {needle}: {labels}'
                        for text, rect in matches:
                            assert hud.blocked_rects[1].contains(rect), f'clipped {text}'
                            band = pixels[rect.top:rect.bottom, rect.left:rect.right]
                            assert int((band.max(2) > 80).sum()) > 10, f'invisible {text}'
                    path = args.out / f'{width}_{kind}_{stage}.png'
                    Image.fromarray(pixels).save(path)
                    row['captures'].append({'stage': stage, 'file': str(path),
                                            'crew': entity.crew, 'hull': entity.hull, 'tick': st.tick})
                    pygame.display.flip()
                    pygame.event.pump()
                def attack_input():
                    ctrl.selection = {source.id}
                    point = camera.world_to_screen(target.pos.x, target.pos.y, target.pos.z)
                    assert point is not None and ctrl._pick_target(point) is target, 'real hull pick failed'
                    point = tuple(int(v) for v in point)
                    assert not any(r.collidepoint(point) for r in hud.blocked_rects), 'target under HUD'
                    before = st.to_dict(precise=True)
                    pygame.event.clear()
                    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                        pygame.event.post(pygame.event.Event(event_type, button=3, pos=point))
                    for event in pygame.event.get():
                        ctrl.handle_event(event)
                    assert len(st.command_queue) == 1 and st.command_queue[0].type == 'attack'
                    assert st.command_queue[0].target_id == target.id
                    after = st.to_dict(precise=True)
                    # Input queues intent only, never spends crew or causes damage.
                    after['command_queue'] = before['command_queue']
                    old_queue = next(pair[1] for pair in before['runtime_state']['state'][1]
                                     if pair[0] == ['scalar', 'command_queue'])
                    for pair in after['runtime_state']['state'][1]:
                        if pair[0] == ['scalar', 'command_queue']:
                            pair[1] = old_queue
                    assert before == after, 'input mutated world outside command queue'
                try:
                    capture('staffed', target)
                    attack_input()
                    gm.commands.consume()
                    for expected in (1, 0):
                        st.damage_queue.append(dict(target=target, damage=10, shield_mult=1,
                            armor_mult=1, system_mult=0, attacker=source))
                        gm.step(1 / 30)
                        assert target.crew == expected
                        capture('crew_drop' if expected else 'abandoned', target)
                    assert target.alive and target.owner == 1
                    assert source.current_target is None and source.order_target_id is None
                    for _ in range(30):
                        gm.step(1 / 30)
                    assert row['launches'] == 0 and target.hull == 380
                    attack_input()
                    source.weapon_cooldowns.clear()
                    gm.step(1 / 30)
                    assert source.abandoned_attack_target == target.id
                    for _ in range(300):
                        if st.entity(target.id) is None:
                            break
                        gm.step(1 / 30)
                    assert st.entity(target.id) is None and row['launches'] > 0
                    capture('destroyed_after_reattack', source)
                    row['explicit_reattack_destroyed'] = True
                    report['scenarios'].append(row)
                finally:
                    hud.close()
                    renderer.close()
        (args.out / 'metrics.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        scenarios = len(report['scenarios'])
        captures = sum(len(row['captures']) for row in report['scenarios'])
        assert scenarios == 4 and captures == 16
        print(f'CREW_DAMAGE_DIAG_OK: {scenarios} scenarios; {captures} captures; '
              'real SDL reattack destroyed ships/stations')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
