"""Real SDL/OpenGL skirmish UI, pixels, event batches and backend launch."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import argparse
import pygame
import numpy as np
from OpenGL.GL import (glViewport, glReadPixels, glGetError, glClear, GL_RGB, GL_UNSIGNED_BYTE,
                       GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT)
from render.menus import MenuStack, MenuResult
from game.core.skirmish import PLAYER_COLORS, build_skirmish_map
from game.core.manager import GameManager


def click(menu, action, payload=None):
    button = next(b for b in menu.buttons if b['action'] == action
                  and (payload is None or b['payload'] == payload))
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        pygame.event.post(pygame.event.Event(kind, pos=button['rect'].center, button=1))
    for event in pygame.event.get():
        menu.handle_event(event)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='saves/diag_skirmish')
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    pygame.init()
    try:
        for width, height in ((1280, 800), (1440, 900), (960, 640), (800, 600)):
            pygame.display.set_mode((width, height), pygame.DOUBLEBUF | pygame.OPENGL)
            glViewport(0, 0, width, height)
            pygame.event.pump()
            for count, map_id in ((2, 'skirmish01'), (3, 'skirmish02'), (4, 'skirmish03'), (4, 'skirmish04')):
                menu = MenuStack(width, height)
                menu.screen = 'main'
                menu.render(0)
                click(menu, 'start_skirmish')
                assert menu.result == MenuResult.NONE
                menu.render(0)
                click(menu, 'skirmish_map', map_id)
                menu.render(0)
                for _ in range(count - 2):
                    click(menu, 'skirmish_ai', 1)
                    menu.render(0)
                click(menu, 'skirmish_color', 0)
                click(menu, 'skirmish_faction', 0)
                click(menu, 'skirmish_difficulty')
                menu.render(0)
                window = pygame.Rect(0, 0, width, height)
                assert all(window.contains(b['rect']) for b in menu.buttons)
                texts = [r for r in menu.skirmish_text_bounds if r.w > 0]
                assert all(window.contains(r) for r in texts)
                for i, rect in enumerate(texts):
                    assert not any(rect.colliderect(other) for other in texts[i + 1:]), (rect, texts[i + 1:])
                for i, button in enumerate(menu.buttons):
                    assert not any(button['rect'].colliderect(other['rect']) for other in menu.buttons[i + 1:])
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                menu.draw_gl()
                pixels = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
                frame = np.flipud(np.frombuffer(pixels, dtype=np.uint8).reshape(height, width, 3))
                assert glGetError() == 0
                # Each active start must show its actual configured color, not just lit pixels.
                for slot, (x, y) in enumerate(menu.skirmish_preview_starts[:count]):
                    expected = np.array([round(v * 255) for v in PLAYER_COLORS[menu.skirmish_options['colors'][slot]]])
                    assert np.max(np.abs(frame[y, x].astype(int) - expected)) <= 8, (slot, frame[y, x], expected)
                preview = menu.skirmish_preview_rect
                area = frame[preview.y:preview.bottom, preview.x:preview.right]
                for expected in ((174, 137, 76), (100, 185, 160)):
                    assert (np.max(np.abs(area.astype(int) - expected), axis=2) <= 4).sum() > 5
                path = os.path.join(args.out, f'{width}x{height}_{map_id}_{count}players.png')
                pygame.image.save(pygame.image.frombuffer(frame.tobytes(), (width, height), 'RGB'), path)
                pygame.display.flip()
                click(menu, 'launch_skirmish')
                assert menu.result == MenuResult.START_SKIRMISH
                gm = GameManager.start_skirmish(build_skirmish_map(menu.skirmish_store, menu.result_payload))
                assert len(gm.state.players) == count
                assert gm.state.players[0].is_ai is False
                assert all(gm.state.players[i].is_ai for i in range(1, count))
                assert gm.state.players[0].faction == 'rebel'
                assert all(gm.state.players[i].ai_difficulty == 'hard' for i in range(1, count))
                for slot in range(count):
                    expected = PLAYER_COLORS[menu.result_payload['colors'][slot]]
                    assert tuple(gm.state.players[slot].color) == expected
                print(f'PASS {width}x{height} {map_id}: {count} players, pixels/layout/launch')
        print('SKIRMISH_MENU_DIAG_OK')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
