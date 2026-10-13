"""Explicit real-window GL acceptance. Run directly, not in headless pytest.

.venv/bin/python tests/test_classic_replays_gl.py <capture-directory>
"""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pygame
import numpy as np
from OpenGL import GL as gl
from render.menus import MenuStack
import test_classic_replays as fixtures


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / '.hermes' / 'cache' / 'scratch' / 'classic-replays-gl'
    output.mkdir(parents=True, exist_ok=True)
    fixture = fixtures.ClassicReplayTests()
    results = []
    try:
        fixture.setUp()
        pygame.init()
        for w, h in ((800, 600), (1440, 900)):
            # Release textures while their original GL context is still current.
            fixture.menu.close()
            pygame.display.set_mode((w, h), pygame.OPENGL | pygame.DOUBLEBUF)
            gl.glViewport(0, 0, w, h)
            pygame.event.pump()
            fixture.menu = fixture.own_menu(w, h)
            fixture.menu.screen = 'replays'
            paths = []
            for state in ('empty', 'unselected', 'selected', 'paged', 'invalid', 'confirm', 'confirm-all'):
                menu = fixture.menu
                if state == 'unselected':
                    paths = [fixture.recording(f'gl-recording-{i}-' + 'a' * 100 + '.json',
                                               f'2026-01-0{i + 1}T12:00:00Z') for i in range(7)]
                    broken = fixture.folder / ('invalid-' + 'b' * 110 + '.json')
                    broken.write_text('{bad')
                    menu.open_replays()
                elif state == 'selected':
                    fixture.click('select_replay', paths[-1])
                elif state == 'paged':
                    fixture.click('replay_page', 1)
                elif state == 'invalid':
                    fixture.click('replay_page', -1)
                    fixture.click('select_replay', str(broken))
                elif state == 'confirm':
                    fixture.click('replay_delete')
                elif state == 'confirm-all':
                    fixture.click('replay_cancel_delete')
                    fixture.click('replay_delete_all')
                with patch.object(menu, '_draw_splash_movie', side_effect=AssertionError('movie on replay screen')):
                    menu.render(0)
                fixture.assert_geometry()
                gl.glClearColor(1, 0, 1, 1)
                gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
                menu.draw_gl()
                raw = gl.glReadPixels(0, 0, w, h, gl.GL_RGB, gl.GL_UNSIGNED_BYTE)
                frame = np.flipud(np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3))
                assert gl.glGetError() == gl.GL_NO_ERROR
                expected = pygame.surfarray.array3d(menu._surface).transpose(1, 0, 2)
                delta = np.abs(frame.astype(int) - expected.astype(int))
                assert delta.max() <= 1, (state, delta.max())
                assert tuple(frame[0, 0]) == (8, 15, 22)
                name = f'{w}x{h}_replay_{state}.png'
                pygame.image.save(pygame.image.frombuffer(frame.tobytes(), (w, h), 'RGB'), output / name)
                pygame.display.flip()
                results.append(dict(size=[w, h], state=state, capture=name,
                                    gl_error=0, max_pixel_difference=int(delta.max()),
                                    buttons=len(menu.buttons), text_bounds=len(menu.replay_text_bounds)))
            for path in fixture.folder.iterdir():
                path.unlink()
        (output / 'report.json').write_text(json.dumps(results, indent=2))
        print(f'CLASSIC_REPLAYS_GL_OK captures={len(results)} output={output}')
    finally:
        try:
            fixture.doCleanups()
        finally:
            pygame.quit()


if __name__ == '__main__':
    main()
