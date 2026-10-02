"""Capture real idle and constructor HUDs and verify the GL composite.

Run with PYTHONPATH=.:tests .venv/bin/python tools/diag_hud_compact.py OUTDIR.
Uses a real window/context, never SDL dummy. No files in saves are modified.
"""
from pathlib import Path
import sys

import numpy as np
import pygame
from OpenGL import GL

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game.core.manager import GameManager
from game.data.store import DataStore
from render.camera import Camera
from render.hud import HUD
from render.renderer import Renderer


def capture():
    GL.glFinish()
    raw = GL.glReadPixels(0, 0, 1280, 800, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
    return np.flipud(np.frombuffer(bytes(raw), np.uint8).reshape(800, 1280, 3)).copy()


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: diag_hud_compact.py OUTDIR')
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    pygame.init()
    try:
        pygame.display.set_mode((1280, 800), pygame.OPENGL | pygame.DOUBLEBUF)
        pygame.event.pump()
        DataStore.reset()
        ds = DataStore()
        gm = GameManager.start_skirmish(ds.maps['skirmish01'])
        st = gm.state
        constructor = next(e for e in st.entities.values()
                           if e.owner == 0 and e.is_construction)
        command = next(e for e in st.entities.values()
                       if e.owner == 0 and e.data_id == 'command_station')
        cam = Camera(1280, 800)
        cam.target = [command.pos.x, command.pos.y, command.pos.z]
        cam.distance = 3400
        cam.yaw, cam.pitch = 25, 45
        renderer = Renderer(st, cam)
        renderer.diff_render = True
        hud = HUD(1280, 800, st)
        for name, selected in [('idle', set()), ('constructor', {constructor.id})]:
            renderer.draw(0, selected)
            world = capture()
            hud.render(selected, None, 0, False)
            was_lit = bool(GL.glIsEnabled(GL.GL_LIGHTING))
            hud.draw_gl()
            assert bool(GL.glIsEnabled(GL.GL_LIGHTING)) == was_lit
            composite = capture()
            alpha = pygame.surfarray.array_alpha(hud.overlay).T
            rgb = pygame.surfarray.array3d(hud.overlay).transpose(1, 0, 2)
            a = alpha[..., None].astype(float) / 255
            expected = rgb * a + world * (1 - a)
            error = np.abs(composite.astype(float) - expected)
            print(f'{name}: compositing_max_error={error.max():.2f} lighting={GL.glIsEnabled(GL.GL_LIGHTING)}')
            assert error.max() <= 2, 'HUD colours are being altered by inherited world state'
            assert (np.abs(composite.astype(int) - world.astype(int))[alpha == 0] <= 1).all(), \
                'HUD changed world pixels outside its panels'
            assert np.any(composite[:34] != world[:34]), 'HUD was not composited'
            if not selected:
                assert np.all(alpha[200:470, 15:325] == 0)
                assert np.all(alpha[200:470, 955:1265] == 0)
            else:
                assert any(b['kind'] == 'build_station_place' for b in hud.buttons)
            assert GL.glGetError() == GL.GL_NO_ERROR
            image = pygame.image.frombuffer(composite.tobytes(), (1280, 800), 'RGB')
            path = out / f'hud_{name}.png'
            pygame.image.save(image, path)
            print(f'{name}: overlay_pixels={np.count_nonzero(alpha)} image={path}')
        print('COMPACT_HUD_DIAG_OK')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
