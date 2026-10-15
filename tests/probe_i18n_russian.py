import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

import numpy as np
import pygame
from OpenGL import GL
from render import clean_classic, i18n, menus


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path.home() / '.hermes/cache/scratch/russian108')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if os.environ.get('SDL_VIDEODRIVER') == 'dummy':
        raise RuntimeError('This probe requires a real SDL OpenGL driver')
    font_owned = not pygame.font.get_init()
    display_owned = not pygame.display.get_init()
    previous_language = i18n.language()
    menu = None
    report = {'captures': [], 'glyphs': []}
    try:
        pygame.display.init()
        pygame.display.set_mode((1280, 800), pygame.OPENGL | pygame.DOUBLEBUF)
        report['driver'] = pygame.display.get_driver()
        report['gl_renderer'] = GL.glGetString(GL.GL_RENDERER).decode()
        with tempfile.TemporaryDirectory(dir=args.out) as directory:
            root = Path(directory)
            saves = root / 'saves'
            saves.mkdir()
            with patch.multiple(menus, USER_DIR=str(root), SAVES_DIR=str(saves),
                                SETTINGS_PATH=str(saves / 'settings.json'),
                                CAMPAIGN_PATH=str(saves / 'campaign.json'),
                                BALANCE_PATH=str(saves / 'balance.json')):
                try:
                    menu = menus.MenuStack(1280, 800)
                    menu.render(0)
                    start = next(b for b in menu.buttons if b['action'] == 'goto_main')
                    click(menu, start)
                    menu.render(0)
                    settings = next(b for b in menu.buttons if b['action'] == 'goto_settings')
                    click(menu, settings)
                    for _ in range(3):
                        menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEDOWN))
                    for expected in ('de', 'pl', 'ru'):
                        menu.render(0)
                        row = next(b for b in menu.buttons if b['action'] == 'cycle_language')
                        click(menu, row)
                        menu.apply_pending()
                        assert i18n.language() == expected
                    assert json.loads((saves / 'settings.json').read_text(encoding='utf-8'))['language'] == 'ru'
                    menu.render(0)
                    assert 'Русский ›' in menu.settings_rendered_text
                    assert 'Язык · Страница 4/5' in menu.settings_rendered_text
                    report['settings_text'] = menu.settings_rendered_text
                    report['captures'].append(capture(menu, args.out / 'settings_ru_gl.png'))
                    menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
                    menu.render(0)
                    assert 'Настройки' in menu.main_rendered_text
                    assert 'Кампания' in menu.main_rendered_text
                    report['menu_text'] = menu.main_rendered_text
                    report['captures'].append(capture(menu, args.out / 'main_ru_gl.png'))
                    font = clean_classic.font(24)
                    pack = json.loads((ROOT / 'assets/data/lang/ru.json').read_text(encoding='utf-8'))
                    letters = sorted(set(re.findall('[А-Яа-яЁё]', json.dumps(pack, ensure_ascii=False))))
                    missing = pygame.image.tobytes(font.render('\U0010ffff', True, 'white'), 'RGBA')
                    bitmaps = set()
                    for letter in letters:
                        surface = font.render(letter, True, 'white')
                        pixels = pygame.image.tobytes(surface, 'RGBA')
                        alpha = pygame.surfarray.array_alpha(surface)
                        metrics = font.metrics(letter)[0]
                        assert pixels != missing and metrics is not None and metrics[1] > metrics[0]
                        assert int(alpha.sum()) > 0
                        bitmaps.add(pixels)
                        report['glyphs'].append({'letter': letter, 'ink_pixels': int((alpha > 0).sum()),
                                                'alpha_sum': int(alpha.sum()), 'metrics': metrics})
                    assert len(bitmaps) == len(letters)
                    report['distinct_non_tofu_glyphs'] = len(bitmaps)
                    report['persisted_language'] = 'ru'
                finally:
                    if menu is not None:
                        menu.close()
                        menu = None
        (args.out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        if menu is not None:
            menu.close()
        i18n.set_language(previous_language)
        if display_owned:
            pygame.display.quit()
        if font_owned and pygame.font.get_init():
            clean_classic.font.cache_clear()
            pygame.font.quit()


def click(menu, button):
    menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                        pos=button['rect'].center))


def capture(menu, path):
    GL.glViewport(0, 0, menu.width, menu.height)
    GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
    menu.draw_gl()
    GL.glFinish()
    data = GL.glReadPixels(0, 0, menu.width, menu.height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
    pixels = np.frombuffer(data, dtype=np.uint8).reshape(menu.height, menu.width, 3)[::-1].copy()
    expected = pygame.surfarray.array3d(menu._surface).transpose(1, 0, 2)
    error = np.abs(pixels.astype(int) - expected.astype(int))
    assert int(error.max()) <= 1, int(error.max())
    pygame.image.save(pygame.image.frombuffer(pixels.tobytes(), (menu.width, menu.height), 'RGB'), str(path))
    pygame.display.flip()
    return {'path': str(path), 'max_gl_surface_error': int(error.max()),
            'nonzero_components': int((pixels > 0).sum())}


if __name__ == '__main__':
    main()
