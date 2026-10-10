"""Real SDL/OpenGL boarding acceptance: gameplay, picking and framebuffer evidence.

PYTHONPATH=. .venv/bin/python tools/diag_boarding.py --out DIR
No dummy video driver; captures occur BEFORE flip and are vertically corrected.
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
        raise RuntimeError('Real SDL/OpenGL display required')
    pygame.display.init()
    pygame.font.init()
    report = []
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
            # Real factory hulls in a clean scene, plus live bases so manager ticks
            # cannot silently become no-ops through annihilation victory.
            st.entities.clear()
            st.explored_cells.clear()
            st.discovered_planets.clear()
            game.factory.spawn_station('command_station', 0, Vec3(-9000, 0, 0))
            game.factory.spawn_station('command_station', 1, Vec3(9000, 0, 0))
            source = game.factory.spawn_ship('imperial_cruiser', 0, Vec3(0, 0, -220))
            target = game.factory.spawn_ship('imperial_frigate', 1, Vec3(0, 0, 220))
            target.crew = 0
            target.systems['life_support'].hp = 0
            target.shields = {q: 0.0 for q in target.shields}
            game.visibility.update()
            camera = Camera(width, height)
            camera.target = [0, 0, 0]
            camera.yaw, camera.pitch, camera.distance = 25, 65, 2600
            renderer = Renderer(st, camera)
            renderer.diff_render = True
            renderer.time = 3.0
            renderer.skip = {'star', 'jumppoints', 'nebulas', 'sites', 'shields'}
            view = HUD(width, height, st)
            messages = []
            ctrl = InputController(st, camera, view, SimpleNamespace(flash=messages.append))
            ctrl.selection = {source.id}
            labels, bars = [], []
            original_label, original_bar = view._label, view._bar
            def label(x, y, text, color=None, font=None):
                labels.append((str(text), pygame.Rect(x, y, *(font or view.font).size(str(text)))))
                original_label(x, y, text, color, font)
            def bar(x, y, w, h, *values):
                bars.append(pygame.Rect(x, y, w, h))
                original_bar(x, y, w, h, *values)
            view._label, view._bar = label, bar
            def pixels():
                GL.glFinish()
                raw = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
                return np.flipud(np.frombuffer(raw, np.uint8).reshape(height, width, 3)).copy()
            def capture(stage, entity, expected):
                before = st.to_dict(precise=True)
                labels.clear(); bars.clear()
                renderer.draw(0, {entity.id})
                view.render({entity.id}, None, 0, False)
                view.draw_gl()
                frame = pixels()
                assert GL.glGetError() == GL.GL_NO_ERROR
                assert before == st.to_dict(precise=True), 'render mutated simulation'
                panel = view.blocked_rects[1]
                glyphs = {}
                for needle in expected:
                    rows = [(text, rect) for text, rect in labels if needle in text and rect.x < 330]
                    assert rows, f'missing {needle}'
                    for text, rect in rows:
                        assert panel.contains(rect), f'clipped {text}: {rect} panel={panel}'
                        assert not any(rect.colliderect(b) for b in bars), f'bar covers {text}'
                        band = frame[rect.top:rect.bottom, rect.left:rect.right]
                        n = int((band.max(axis=2) > 80).sum())
                        assert n > 10, f'invisible glyphs {text}'
                        glyphs[text] = n
                for button in view.buttons:
                    if button['kind'] == 'board':
                        assert any(r.contains(button['rect']) for r in view.blocked_rects), 'board hitbox clipped'
                path = args.out / f'{width}_{stage}.png'
                Image.fromarray(frame).save(path)
                report.append({'width': width, 'stage': stage, 'file': str(path), 'glyph_pixels': glyphs})
                pygame.display.flip(); pygame.event.pump()
                return frame
            try:
                capture('ready', source, ['CREW', 'LIFE'])
                button = next(b for b in view.buttons if b['kind'] == 'board')
                before = st.to_dict(precise=True)
                ctrl.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button['rect'].center))
                assert ctrl._pending_ability is not None
                assert before == st.to_dict(precise=True), 'arming mutated sim'
                point = camera.world_to_screen(target.pos.x, target.pos.y, target.pos.z)
                assert point is not None
                assert ctrl._pick_target(point) is target, 'real hull pick failed'
                ctrl.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(int(point[0]), int(point[1]))))
                assert st.command_queue and st.command_queue[-1].type == 'board'
                assert source.crew == source.max_crew, 'input spent crew outside tick'
                game.step(1 / 30)
                craft = next(e for e in st.entities.values() if e.boarding)
                for _ in range(30):
                    game.step(1 / 30)
                assert craft.boarding['phase'] == 'transit'
                capture('transit', source, ['CREW', 'LIFE', 'BOARDING TRANSIT'])
                # A same-state, frozen-animation control proves real craft geometry.
                draw_ship = renderer._draw_ship
                renderer._draw_ship = lambda e: None if e.id == craft.id else draw_ship(e)
                renderer.draw(0, set())
                without = pixels()
                renderer._draw_ship = draw_ship
                renderer.draw(0, set())
                with_craft = pixels()
                visible = int((np.abs(with_craft.astype(int)-without.astype(int)).max(2) > 8).sum())
                assert visible > 10, f'craft draws no hardware ({visible} px)'
                report[-1]['craft_difference_pixels'] = visible
                for _ in range(120):
                    if craft.boarding['phase'] == 'control':
                        break
                    game.step(1 / 30)
                assert craft.boarding['phase'] == 'control'
                capture('control', target, ['CREW', 'LIFE', 'ABANDONED', 'BOARDING CONTROL'])
                for _ in range(180):
                    if target.owner == 0:
                        break
                    game.step(1 / 30)
                assert target.owner == 0 and target.crew > 0
                assert not any(e.boarding for e in st.entities.values())
                capture('captured', target, ['CREW', 'LIFE', 'ORDER'])
            finally:
                view.close()
                renderer.close()
        (args.out / 'metrics.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        print('BOARDING_DIAG_OK', len(report), 'framebuffer captures')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
