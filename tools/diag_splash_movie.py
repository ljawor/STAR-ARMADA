"""Verify the baked movie through the production SDL/OpenGL menu compositor."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import time
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pygame
from OpenGL.GL import (GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_RGB,
                       GL_UNSIGNED_BYTE, glClear, glFinish, glGetError,
                       glReadPixels, glViewport)
from render.menus import MenuStack


def run(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    pygame.init()
    results = []
    try:
        for width, height in ((800, 600), (1280, 800), (1440, 900)):
            pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
            glViewport(0, 0, width, height)
            pygame.event.pump()
            menu = MenuStack(width, height)
            try:
                menu.settings['cinematics_enabled'] = True
                menu.settings['reduced_motion'] = False
                images = {}
                for label, elapsed in (('start', 0), ('middle', 7.5), ('wrap', 15)):
                    menu.t = elapsed
                    before = time.perf_counter()
                    menu.render(0)
                    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                    menu.draw_gl()
                    glFinish()
                    milliseconds = (time.perf_counter() - before) * 1000
                    assert glGetError() == 0
                    assert menu._menu_movie.available
                    raw = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
                    pixels = np.flipud(np.frombuffer(raw, np.uint8).reshape(height, width, 3)).copy()
                    # Actual battle imagery, not only sparse stars and white title.
                    assert ((pixels[:, :, 2] > 25) & (pixels[:, :, 2] > pixels[:, :, 0] * 1.1)).sum() > 5000
                    path = output / f'{width}x{height}_{label}.png'
                    pygame.image.save(pygame.image.frombuffer(pixels.tobytes(), (width, height), 'RGB'), str(path))
                    images[label] = pixels
                    results.append(dict(size=[width, height], phase=label,
                                        render_upload_finish_ms=milliseconds, screenshot=str(path)))
                assert not np.array_equal(images['start'], images['middle'])
                # Title pulse may vary, so bound the whole composition seam.
                assert np.abs(images['start'].astype(int) - images['wrap'].astype(int)).mean() < 5
                menu.settings['reduced_motion'] = True
                menu.t = 0
                menu.render(0)
                still = pygame.image.tobytes(menu._surface, 'RGB')
                menu.t = 12
                menu.render(0)
                assert still == pygame.image.tobytes(menu._surface, 'RGB')
                assert menu.buttons[0]['action'] == 'goto_main'
                assert menu.buttons[0]['rect'] == pygame.Rect(0, 0, width, height)
                menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(10, 10)))
                assert menu.screen == 'main'
                menu.render(0)
                assert any(button['action'] == 'start_skirmish' for button in menu.buttons)
            finally:
                menu.close()
    finally:
        pygame.quit()
    (output / 'report.json').write_text(json.dumps(results, indent=2))
    print('SPLASH_MOVIE_DIAG_OK', len(results), 'real SDL/OpenGL captures')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    run(parser.parse_args().output)
