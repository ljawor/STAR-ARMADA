"""Real SDL/GL Clean classic main/host pixels, geometry and timing."""
import ast
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pygame
import numpy as np
from OpenGL.GL import glClear, glReadPixels, glViewport, glGetError, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_RGB, GL_UNSIGNED_BYTE
from render.menus import MenuStack
from game.core.skirmish import PLAYER_COLORS, SKIRMISH_MAP_IDS


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ['TMPDIR']) / 'clean-classic'
    out.mkdir(parents=True, exist_ok=True)
    pygame.init()
    rows = []
    try:
        for w, h in ((800, 600), (960, 640), (1280, 800), (1440, 900)):
            pygame.display.set_mode((w, h), pygame.DOUBLEBUF | pygame.OPENGL)
            glViewport(0, 0, w, h)
            pygame.event.pump()
            for screen in ('main', 'lan_host'):
                for mid in (SKIRMISH_MAP_IDS if screen == 'lan_host' else (None,)):
                    menu = MenuStack(w, h)
                    menu.screen = screen
                    if mid:
                        menu.lan_options['map_id'] = mid
                        menu.lan_options['human_count'] = len(menu.skirmish_store.maps[mid]['players'])
                        menu.lan_options['ai_count'] = 0
                    menu.render(0)
                    window = pygame.Rect(0, 0, w, h)
                    assert all(window.contains(b['rect']) for b in menu.buttons)
                    for i, b in enumerate(menu.buttons):
                        assert not any(b['rect'].colliderect(x['rect']) for x in menu.buttons[i + 1:])
                    if mid:
                        bounds = [r for r in menu.lan_text_bounds if r.w]
                        assert all(window.contains(r) for r in bounds)
                        for i, r in enumerate(bounds):
                            assert not any(r.colliderect(x) for x in bounds[i + 1:]), r
                        assert menu.skirmish_store.maps[mid]['description'] in ' '.join(menu.lan_rendered_text)
                    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                    menu.draw_gl()
                    pixels = glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE)
                    frame = np.flipud(np.frombuffer(pixels, dtype=np.uint8).reshape(h, w, 3))
                    assert glGetError() == 0
                    if mid:
                        for slot, (x, y) in enumerate(menu.lan_preview_starts):
                            color = np.array([round(v * 255) for v in PLAYER_COLORS[menu.lan_options['colors'][slot]]])
                            assert np.max(np.abs(frame[y, x].astype(int) - color)) <= 8
                        for b in (b for b in menu.buttons if b['action'] == 'lan_color'):
                            r = b['rect']
                            color = np.array([round(v * 255) for v in PLAYER_COLORS[menu.lan_options['colors'][b['payload']]]])
                            x = r.x + round(15 * min(w / 1120, h / 700))
                            y = r.y + round(16 * min(w / 1120, h / 700))
                            assert np.max(np.abs(frame[y, x].astype(int) - color)) <= 8
                    name = f'{w}x{h}_{screen}' + (f'_{mid}' if mid else '') + '.png'
                    pygame.image.save(pygame.image.frombuffer(frame.tobytes(), (w, h), 'RGB'), out / name)
                    pygame.display.flip()
                    with patch('pygame.font.SysFont', side_effect=AssertionError('font allocated on warmed frame')):
                        for _ in range(3):
                            menu.render(0)
                    rows.append(dict(width=w, height=h, screen=screen, map=mid, capture=name))
        # Compare owned visual methods under the same backdrop/runtime.
        source = subprocess.check_output(['git', 'show', 'HEAD:render/menus.py'], cwd=ROOT, text=True)
        tree = ast.parse(source)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MenuStack')
        timings = {}
        for name, screen in (('_screen_main', 'main'), ('_screen_skirmish', 'skirmish'), ('_screen_lan', 'lan_host')):
            method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
            ns = dict(vars(sys.modules['render.menus']))
            exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), '<baseline>', 'exec'), ns)
            menu = MenuStack(1280, 800)
            menu.screen = screen
            values = {}
            for label, fn in (('before', lambda: ns[name](menu)), ('after', getattr(menu, name))):
                samples = []
                for _ in range(60):
                    menu.buttons = []
                    start = time.perf_counter()
                    fn()
                    samples.append((time.perf_counter() - start) * 1000)
                values[label + '_median_ms'] = statistics.median(samples[10:])
            timings[screen] = values
        (out / 'report.json').write_text(json.dumps(dict(captures=rows, timings=timings), indent=2))
        print(json.dumps(timings, indent=2))
        print(f'CLEAN_CLASSIC_DIAG_OK captures={len(rows)} out={out}')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
