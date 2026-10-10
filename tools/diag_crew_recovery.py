"""Real SDL/OpenGL crew controls, recovery and faction hardware acceptance.

PYTHONPATH=. .venv/bin/python tools/diag_crew_recovery.py --out DIR
Reads the real back buffer before flip. No SDL dummy and no simulated screenshots.
"""
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
from game.core.commands import AbilityCommand
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
    assert os.environ.get('SDL_VIDEODRIVER') != 'dummy', 'real display required'
    pygame.display.init()
    pygame.font.init()
    reports = []
    try:
        for width, height in ((1280, 800), (1024, 768)):
            pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
            pygame.event.pump()
            GL.glViewport(0, 0, width, height)
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glClearColor(.008, .012, .025, 1)
            DataStore.reset()
            map_def = json.loads(json.dumps(DataStore.get().maps['skirmish01']))
            for p in map_def['players']:
                p['is_ai'] = False
            game = GameManager.start_skirmish(map_def)
            st = game.state
            st.entities.clear(); st.explored_cells.clear(); st.discovered_planets.clear()
            game.factory.spawn_station('command_station', 1, Vec3(9000, 0, 9000))
            base = game.factory.spawn_station('command_station', 0, Vec3(0, 0, -850))
            transport = game.factory.spawn_ship('imperial_crew_transport', 0, Vec3(0, 0, -350))
            target = game.factory.spawn_ship('imperial_frigate', 0, Vec3(0, 0, 1100))
            target.crew = 0; target.max_crew = 10
            target.systems['life_support'].hp = 49
            game.visibility.update()
            camera = Camera(width, height)
            camera.target = [0, 0, 450]
            camera.yaw, camera.pitch, camera.distance = 20, 65, 3600
            renderer = Renderer(st, camera)
            renderer.diff_render = True; renderer.time = 3.0
            renderer.skip = {'star', 'jumppoints', 'nebulas', 'sites', 'shields'}
            hud = HUD(width, height, st)
            messages = []
            ctrl = InputController(st, camera, hud, SimpleNamespace(flash=messages.append))
            labels, bars = [], []
            orig_label, orig_bar = hud._label, hud._bar
            def label(x, y, text, color=None, font=None):
                labels.append((str(text), pygame.Rect(x, y, *(font or hud.font).size(str(text)))))
                orig_label(x, y, text, color, font)
            def bar(x, y, w, h, *values):
                bars.append(pygame.Rect(x, y, w, h)); orig_bar(x, y, w, h, *values)
            hud._label, hud._bar = label, bar
            def pixels():
                GL.glFinish()
                raw = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
                return np.flipud(np.frombuffer(raw, np.uint8).reshape(height, width, 3)).copy()
            def capture(stage, selected, needles):
                ctrl.selection = set(selected)
                before = json.loads(json.dumps(st.to_dict(precise=True)))
                labels.clear(); bars.clear()
                renderer.draw(0, ctrl.selection)
                hud.render(ctrl.selection, None, 0, False)
                hud.draw_gl()
                frame = pixels()
                assert GL.glGetError() == GL.GL_NO_ERROR
                assert before == json.loads(json.dumps(st.to_dict(precise=True))), 'renderer/HUD mutated state'
                panel = hud.blocked_rects[1]
                glyphs = {}
                for needle in needles:
                    rows = [(text, rect) for text, rect in labels if needle in text and rect.x < 330]
                    assert rows, ('missing glyph label', needle)
                    for text, rect in rows:
                        assert panel.contains(rect), ('clipped inspector', text, rect, panel)
                        assert not any(rect.colliderect(b) for b in bars), ('bar overlap', text)
                        band = frame[rect.top:rect.bottom, rect.left:rect.right]
                        count = int((band.max(2) > 80).sum())
                        assert count > 10, ('missing pixels', text)
                        glyphs[text] = count
                for button in hud.buttons:
                    if button['kind'].startswith('crew_'):
                        assert any(r.contains(button['rect']) for r in hud.blocked_rects), 'clipped control'
                path = args.out / f'{width}_{stage}.png'
                Image.fromarray(frame).save(path)
                reports.append(dict(width=width, stage=stage, file=str(path), glyph_pixels=glyphs,
                                    tick=st.tick, operating=transport.crew, cargo=transport.crew_cargo,
                                    recovered_crew=target.crew))
                pygame.display.flip(); pygame.event.pump()
                return frame
            def click_button(kind):
                b = next(b for b in hud.buttons if b['kind'] == kind)
                ctrl.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=b['rect'].center))
            def pick_target():
                point = camera.world_to_screen(target.pos.x, target.pos.y, target.pos.z)
                assert point is not None and ctrl._pick_target(point) is target, 'real owned hull pick'
                ctrl.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                    pos=(int(point[0]), int(point[1]))))
            try:
                capture('ready', {transport.id}, ['CREW', 'CARGO 0/240', 'STAFF 100%', 'LIFE'])
                pool = st.players[0].crew
                click_button('crew_load')
                assert st.command_queue[-1].type == 'crew_load'
                assert transport.crew_cargo == 0 and st.players[0].crew == pool
                for _ in range(20): game.step(1 / 30)
                capture('loading', {transport.id}, ['CREW LOAD', 'CARGO', 'LIFE'])
                for _ in range(71): game.step(1 / 30)
                assert transport.crew_cargo == 12
                click_button('crew_cancel')
                game.step(1 / 30)
                assert transport.crew_mission == {} and transport.crew_cargo == 12
                capture('support_blocked', {target.id}, ['ABANDONED', 'STAFF 0%', 'repair life support to 50%'])
                capture('loaded', {transport.id}, ['CREW', 'CARGO 12/240'])
                before = json.loads(json.dumps(st.to_dict(precise=True)))
                click_button('crew_deliver')
                assert before == json.loads(json.dumps(st.to_dict(precise=True))), 'arming mutated sim'
                pick_target()
                assert not st.command_queue and any('50%' in m for m in messages), 'unsafe target accepted'
                # Existing external engineer primitive: no passengers resurrected.
                helper = game.factory.spawn_ship('imperial_supercapital', 0, Vec3(500, 0, 1100))
                st.players[0].energy = 1000
                st.queue_command(AbilityCommand(0, (helper.id,), 'repair_drones'))
                assert target.subsystem_fraction('life_support') < .5
                game.step(1 / 30)
                assert 'repair_drones' in helper.ability_active
                assert target.subsystem_fraction('life_support') >= .5 and target.crew == 0
                pick_target()
                assert st.command_queue[-1].type == 'crew_deliver'
                assert transport.crew_cargo == 12 and target.crew == 0
                game.step(1 / 30)
                capture('transit', {transport.id}, ['CREW DELIVER', 'approaching target', 'CARGO 12/240'])
                for _ in range(900):
                    game.step(1 / 30)
                    if target.crew > 0: break
                assert 0 < target.crew < target.max_crew, 'real travel/delivery did not begin'
                capture('delivery', {transport.id}, ['CREW DELIVER', 'CARGO', 'STAFF'])
                for _ in range(90): game.step(1 / 30)
                assert target.crew == target.max_crew and transport.crew_cargo == 2
                capture('recovered', {target.id}, ['CREW 10/10', 'STAFF 100%', 'LIFE'])
                # Same-state draw-disabled controls prove solid faction hardware,
                # not selection circles or a giant unknown default mesh.
                for faction, prefix in [('imperial', 'imperial'), ('rebel', 'rebel'),
                                        ('confederacy', 'confed'), ('syndicate', 'syndicate')]:
                    hardware = game.factory.spawn_ship(prefix + '_crew_transport', 0, Vec3(4500, 0, 0))
                    camera.target = [4500, 0, 0]; camera.distance = 1300
                    camera.yaw, camera.pitch = 30, 55
                    renderer.draw(0, set()); with_hull = pixels()
                    draw_ship = renderer._draw_ship
                    renderer._draw_ship = lambda e: None if e.id == hardware.id else draw_ship(e)
                    renderer.draw(0, set()); without_hull = pixels()
                    renderer._draw_ship = draw_ship
                    mask = np.abs(with_hull.astype(int) - without_hull.astype(int)).max(2) > 8
                    count = int(mask.sum())
                    assert count > 30, ('invisible hull', faction, count)
                    shades = len(np.unique(with_hull[mask], axis=0))
                    assert shades > 8, ('unshaded hull', faction, shades)
                    capture('hardware_' + faction, {hardware.id}, ['CREW', 'CARGO', 'STAFF'])
                    reports[-1].update(hardware_difference_pixels=count, hardware_shades=shades)
                    st.entities.pop(hardware.id)
                capture('empty_compact', set(), [])
                assert hud.blocked_rects[1].height == 84
            finally:
                hud.close(); renderer.close()
        (args.out / 'metrics.json').write_text(json.dumps(reports, indent=2))
        print(json.dumps(reports, indent=2))
        print('CREW_RECOVERY_DIAG_OK', len(reports), 'framebuffer captures')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
