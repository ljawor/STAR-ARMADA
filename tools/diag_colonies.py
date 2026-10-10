"""Real SDL/GL colony acceptance: input -> serialized command -> manager.
Run PYTHONPATH=. .venv/bin/python tools/diag_colonies.py --out <scratch-dir>.
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
from game.core.entity import Entity
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
    assert os.environ.get('SDL_VIDEODRIVER') != 'dummy'
    pygame.display.init(); pygame.font.init()
    report = []
    try:
        for width, height in ((1280, 800), (1024, 768)):
            pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
            assert pygame.display.get_driver() != 'dummy'
            gl_renderer = GL.glGetString(GL.GL_RENDERER).decode()
            pygame.event.pump()
            GL.glViewport(0, 0, width, height)
            DataStore.reset()
            m = json.loads(json.dumps(DataStore.get().maps['skirmish01']))
            for player in m['players']:
                player['is_ai'] = False
            gm = GameManager.start_skirmish(m)
            st = gm.state
            st.entities.clear(); st.discovered_planets.clear(); st.explored_cells.clear()
            gm.factory.spawn_station('command_station', 0, Vec3(-9000, 0, 0))
            gm.factory.spawn_station('command_station', 1, Vec3(9000, 0, 0))
            planet = Entity(st.next_entity_id, 'planet', -1, 'temperate', pos=Vec3(),
                            radius=300, hull=1e9, max_hull=1e9, is_planet=True,
                            name_override='New Horizon')
            st.next_entity_id += 1; st.add_entity(planet)
            colony = gm.factory.spawn_ship('imperial_colonizer', 0, Vec3(-650, 0, 0))
            gm.visibility.update()
            camera = Camera(width, height)
            camera.target = [0, 0, 0]
            camera.yaw, camera.pitch, camera.distance = 0, 65, 4400
            renderer = Renderer(st, camera)
            renderer.diff_render = True; renderer.time = 3
            renderer.skip = {'star', 'jumppoints', 'nebulas', 'sites', 'shields'}
            hud = HUD(width, height, st)
            ctrl = InputController(st, camera, hud, SimpleNamespace(flash=lambda message: None))
            labels, bars = [], []
            label0, bar0 = hud._label, hud._bar
            def label(x, y, text, color=None, font=None):
                labels.append((str(text), pygame.Rect(x, y, *(font or hud.font).size(str(text)))))
                label0(x, y, text, color, font)
            def bar(x, y, w, h, *args):
                bars.append(pygame.Rect(x, y, w, h)); bar0(x, y, w, h, *args)
            hud._label, hud._bar = label, bar
            def snapshot():
                return json.loads(json.dumps(st.to_dict(precise=True)))
            def pixels():
                GL.glFinish()
                raw = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
                return np.flipud(np.frombuffer(raw, np.uint8).reshape(height, width, 3)).copy()
            def capture(stage, expected):
                before = snapshot(); labels.clear(); bars.clear()
                renderer.draw(0, ctrl.selection)
                hud.render(ctrl.selection, None, 0, False); hud.draw_gl()
                frame = pixels()
                assert GL.glGetError() == GL.GL_NO_ERROR, stage
                assert before == snapshot(), 'render mutated state'
                metrics = {}
                for text, rect in labels:
                    assert any(panel.contains(rect) for panel in hud.blocked_rects), f'clipped {text}: {rect}'
                    assert not any(rect.colliderect(b) for b in bars), f'bar covers {text}'
                for needle in expected:
                    rows = [(text, rect) for text, rect in labels if needle in text]
                    assert rows, f'missing {needle}'
                    for text, rect in rows:
                        assert any(panel.contains(rect) for panel in hud.blocked_rects), f'clipped {text}: {rect}'
                        assert not any(rect.colliderect(b) for b in bars), f'bar covers {text}'
                        band = frame[rect.top:rect.bottom, rect.left:rect.right]
                        n = int((band.max(2) > 80).sum())
                        assert n > 10, f'invisible label {text}'
                        metrics[text] = n
                for button in hud.buttons:
                    assert any(panel.contains(button['rect']) for panel in hud.blocked_rects), 'clipped button'
                path = args.out / f'{width}_{stage}.png'
                Image.fromarray(frame).save(path)
                report.append(dict(width=width, height=height, stage=stage, screenshot=str(path), glyph_pixels=metrics,
                                   checked_labels=len(labels), sdl_driver=pygame.display.get_driver(), gl_renderer=gl_renderer))
                pygame.display.flip(); pygame.event.pump()
                return frame
            def click(entity, button=1):
                point = camera.world_to_screen(*entity.pos.to_dict())
                assert point is not None
                pos = tuple(int(v) for v in point)
                ctrl.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=pos))
                ctrl.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=button, pos=pos))
            def advance(seconds):
                tick = st.tick
                ticks = int(seconds * 30)
                for _ in range(ticks):
                    gm.step(1 / 30)
                assert st.tick == tick + ticks and not st.game_over
            try:
                capture('ready', [])
                click(colony)
                assert ctrl.selection == {colony.id}, 'colony physical pick'
                before = snapshot()
                click(planet, 3)
                assert st.command_queue[-1].type == 'colonize'
                assert not colony.build_queue and not planet.colonized_by
                assert st.players[0].crew == before['players']['0']['crew']
                advance(7)
                capture('colonizing', ['COLONIZING', 'COLONY SHIP'])
                advance(10)
                assert planet.colonized_by == 0 and not colony.alive
                click(planet)
                assert ctrl.selection == {planet.id}, 'owned planet physical pick'
                capture('owned', ['COLONY OWNER: Player', 'PLANETARY SATELLITES', 'SLOTS 0/6'])
                buttons = [b for b in hud.buttons if b['kind'] == 'build_satellite']
                assert len(buttons) == 2
                balance = st.players[0].credits
                for button in buttons:
                    ctrl.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button['rect'].center))
                assert [c.type for c in st.command_queue] == ['build_satellite', 'build_satellite']
                assert st.players[0].credits == balance and not planet.build_queue
                advance(1)
                assert len(planet.build_queue) == 2 and st.players[0].credits < balance
                capture('production', ['BUILDING DEFENSE SATELLITE', 'SLOTS 2/6'])
                advance(45)
                satellites = [e for e in st.entities.values() if e.planet_id == planet.id]
                assert len(satellites) == 2
                capture('satellites', ['SLOTS 2/6', 'COLONY OWNER: Player'])
                # Frozen draw-disabled control: prove shaded hardware, not markers or rings.
                renderer.marker_mode = 'off'
                before_hardware = snapshot()
                renderer.draw(0, set()); with_hw = pixels()
                original = renderer._draw_station
                renderer._draw_station = lambda e: None if e.planet_id == planet.id else original(e)
                renderer.draw(0, set()); without_hw = pixels()
                renderer._draw_station = original
                assert before_hardware == snapshot(), 'hardware control mutated state'
                assert GL.glGetError() == GL.GL_NO_ERROR, 'hardware control GL error'
                Image.fromarray(with_hw).save(args.out / f'{width}_hardware.png')
                Image.fromarray(without_hw).save(args.out / f'{width}_hardware_disabled.png')
                hardware = int((np.abs(with_hw.astype(int) - without_hw.astype(int)).max(2) > 8).sum())
                assert hardware > 40, f'no solid satellite meshes ({hardware})'
                report[-1]['hardware_difference_pixels'] = hardware
                # Capture uses the exact same input path; defenders are destroyed, never boarded.
                for satellite in satellites:
                    st.damage_queue.append(dict(target=satellite, damage=1e9, shield_mult=1., armor_mult=1., system_mult=0., attacker_id=1))
                advance(1)
                assert not any(e.alive and e.planet_id == planet.id for e in st.entities.values())
                planet.colonized_by = 1
                captor = gm.factory.spawn_ship('imperial_colonizer', 0, Vec3(-650, 0, 0))
                gm.visibility.update()
                click(captor); click(planet, 3)
                assert st.command_queue[-1].type == 'colonize'
                advance(7)
                capture('capturing', ['CAPTURING', 'COLONY SHIP'])
                advance(10)
                assert planet.colonized_by == 0 and not captor.alive
                click(planet)
                capture('captured', ['COLONY OWNER: Player'])
                planet.colonized_by = 1
                planet.build_queue = [dict(item='attack_satellite', time_left=13.25, total=22)]
                scout = gm.factory.spawn_ship('imperial_corvette', 0, Vec3(-650, 0, 0))
                gm.visibility.update()
                assert st.can_see(0, planet.id)
                capture('enemy_observed', ['COLONY OWNER:', 'Requires your non-gas colony'])
                assert not any('BUILDING' in text for text, rect in labels)
                assert not any(b['kind'] == 'build_satellite' for b in hud.buttons)
                scout.pos = Vec3(-9000, 0, 0)
                gm.visibility.update()
                assert not st.can_see(0, planet.id)
                assert st.known_entity(0, planet.id).build_queue == []
                capture('enemy_hidden', ['NO SELECTION'])
                assert not any('BUILDING' in text for text, rect in labels)
                assert GL.glGetError() == GL.GL_NO_ERROR
            finally:
                hud.close(); renderer.close()
        (args.out / 'metrics.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        print('COLONIES_DIAG_OK', len(report), 'captures; real SDL/GL, input, hardware, immutable state')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
