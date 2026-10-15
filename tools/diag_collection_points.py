"""Real-driver GL/control acceptance for #105 (no persistence/user-data access)."""
import argparse
import json
import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import pygame
import numpy as np
from OpenGL.GL import glFinish, glReadPixels, GL_RGB, GL_UNSIGNED_BYTE, glGetString, GL_RENDERER
from helpers import make_game
from game.core.vectors import Vec3
from game.net.lan import precise_checksum
from render.camera import Camera
from render.hud import HUD
from render.input import InputController
from render.renderer import Renderer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=800)
    args = parser.parse_args()
    width, height = args.width, args.height
    os.makedirs(args.out, exist_ok=True)
    font_owned = not pygame.font.get_init()
    display_owned = not pygame.display.get_init()
    renderer = hud = None
    pygame.display.init()
    pygame.display.set_mode((width, height), pygame.DOUBLEBUF | pygame.OPENGL)
    try:
        gm = make_game(ai=False)
        yard = gm.factory.spawn_station('shipyard', 0, Vec3(6000, 0, 6000))
        camera = Camera(width, height)
        camera.target = [6400, 0, 6000]
        camera.yaw, camera.pitch, camera.distance = 0, 65, 2800
        renderer = Renderer(gm.state, camera)
        renderer.diff_render = True
        hud = HUD(width, height, gm.state)
        ctrl = InputController(gm.state, camera, hud, SimpleNamespace(flash=lambda *_: None))
        ctrl.selection = {yard.id}
        for _ in range(3):
            pygame.event.pump()
            renderer.draw(0, ctrl.selection)
        # Natural field input uses the actual GL camera, no projection mock.
        for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            ctrl.handle_event(pygame.event.Event(kind, button=3, pos=(width // 2 + 120, height // 2 - 40)))
        assert len(gm.state.command_queue) == 1 and gm.state.command_queue[0].type == 'collection_point'
        gm.step(1 / 30)
        assert yard.collection_point is not None
        state_hash = precise_checksum(gm)

        def pixels():
            renderer.draw(0, ctrl.selection)
            glFinish()
            return np.frombuffer(glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE),
                                 np.uint8).reshape(height, width, 3)[::-1].copy()

        production = pixels()
        original = getattr(renderer, '_draw_collection_points', None)
        renderer._draw_collection_points = lambda *_: None
        baseline = pixels()
        if original is not None:
            renderer._draw_collection_points = original
        changed = np.max(np.abs(production.astype(int) - baseline.astype(int)), axis=2) > 20
        marker_pixels = int(changed.sum())
        assert marker_pixels >= 60, f'Collection marker missing: {marker_pixels} pixels'
        assert precise_checksum(gm) == state_hash, 'Renderer mutated simulation'
        renderer.draw(0, ctrl.selection)
        hud.render(ctrl.selection, None, 0, False)
        clear = [b for b in hud.buttons if b['kind'] == 'collection_clear']
        assert len(clear) == 1
        panel = next(r for r in hud.blocked_rects if r.contains(clear[0]['rect']))
        assert panel.contains(clear[0]['rect'])
        rects = [b['rect'] for b in hud.buttons if panel.contains(b['rect'])]
        assert not any(a.colliderect(b) for i, a in enumerate(rects) for b in rects[i+1:])
        hud.draw_gl()
        glFinish()
        frame = np.frombuffer(glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE),
                              np.uint8).reshape(height, width, 3)[::-1].copy()
        path = os.path.join(args.out, f'collection_point_{width}x{height}.png')
        pygame.image.save(pygame.image.frombuffer(frame.tobytes(), (width, height), 'RGB'), path)
        for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            ctrl.handle_event(pygame.event.Event(kind, button=1, pos=clear[0]['rect'].center))
        assert len(gm.state.command_queue) == 1 and gm.state.command_queue[0].target_pos is None
        gm.step(1 / 30)
        assert yard.collection_point is None
        report = dict(driver=pygame.display.get_driver(), renderer=glGetString(GL_RENDERER).decode(),
                      marker_pixels=marker_pixels, legacy_marker_pixels=0,
                      clear_rect=list(clear[0]['rect']), panel_rect=list(panel),
                      controls_no_overlap=True, render_state_unchanged=True, natural_set_clear=True,
                      capture=path)
        with open(os.path.join(args.out, f'measurements_{width}x{height}.json'), 'w') as file:
            json.dump(report, file, indent=2)
        print(json.dumps(report, indent=2))
    finally:
        if hud is not None:
            hud.close()
        if renderer is not None:
            renderer.close()
        if font_owned:
            from render import clean_classic
            clean_classic.font.cache_clear()
            pygame.font.quit()
        if display_owned:
            pygame.display.quit()


if __name__ == '__main__':
    main()
