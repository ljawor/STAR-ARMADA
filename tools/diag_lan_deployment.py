"""Real SDL/OpenGL host deployment input/layout/colour acceptance.

All user data is isolated; directly refuses a competing game before SDL init.
--baseline captures the old default host once, without requiring new controls.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    for row in subprocess.check_output(['ps', '-axo', 'pid=,args='], text=True).splitlines():
        parts = row.split()
        if any(Path(token).name in ('main.py', 'armada_viewer') for token in parts[1:]) and '-c' not in parts:
            raise SystemExit('Close the running game before this GPU diagnostic: ' + row)
    import numpy as np
    import pygame
    from OpenGL.GL import glViewport, glReadPixels, glGetError, glClear, glFinish, GL_RGB, GL_UNSIGNED_BYTE, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT
    from render import menus
    from game.core.skirmish import SKIRMISH_MAP_IDS, PLAYER_COLORS
    from game.net.lan import build_lan_map
    from game.core.manager import GameManager
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    pygame.init()
    try:
        with ExitStack() as scope:
            root = Path(scope.enter_context(tempfile.TemporaryDirectory()))
            for key, leaf in [('USER_DIR', ''), ('SAVES_DIR', 'saves'), ('SETTINGS_PATH', 'settings.json'), ('CAMPAIGN_PATH', 'campaign.json'), ('BALANCE_PATH', 'balance.json')]:
                scope.enter_context(patch.object(menus, key, str(root / leaf)))
            scope.enter_context(patch('pygame.mouse.get_pos', return_value=(0, 0)))
            def press(menu, action, payload=None):
                b = next(b for b in menu.buttons if b['action'] == action and (payload is None or b['payload'] == payload))
                for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                    menu.handle_event(pygame.event.Event(kind, pos=b['rect'].center, button=1))
                menu.render(0)
            cases = [(1440, 900, 'skirmish01', 'baseline')] if args.baseline else [
                (w, h, mid, mode) for w, h in ((800, 600), (1024, 768), (1440, 900))
                for mid in SKIRMISH_MAP_IDS for mode in (('humans', 'mixed') if mid == 'skirmish05' else ('humans',))]
            for width, height, mid, mode in cases:
                pygame.display.set_mode((width, height), pygame.DOUBLEBUF | pygame.OPENGL)
                glViewport(0, 0, width, height)
                menu = menus.MenuStack(width, height)
                try:
                    menu.screen = 'lan_host'
                    menu.render(0)
                    capacity = menu.skirmish_capacity(mid)
                    if not args.baseline:
                        press(menu, 'lan_map', mid)
                        action, target = ('lan_ai', capacity - 2) if mode == 'mixed' else ('lan_humans', capacity)
                        field = 'ai_count' if mode == 'mixed' else 'human_count'
                        for _ in range(8):
                            if menu.lan_options[field] == target:
                                break
                            press(menu, action, 1)
                        assert menu.lan_options[field] == target
                        press(menu, 'lan_spawn_point', capacity - 1)
                        assert menu.lan_preview_rect.w == menu.lan_preview_rect.h
                        window = pygame.Rect(0, 0, width, height)
                        for i, b in enumerate(menu.buttons):
                            assert window.contains(b['rect']), b
                            assert not any(b['rect'].colliderect(v['rect']) for v in menu.buttons[i + 1:]), b
                        bounds = [r for r in menu.lan_text_bounds if r.w]
                        for i, r in enumerate(bounds):
                            assert window.contains(r), r
                            assert not any(r.colliderect(v) for v in bounds[i + 1:]), r
                    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                    menu.draw_gl()
                    glFinish()
                    frame = np.flipud(np.frombuffer(glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE), dtype=np.uint8).reshape(height, width, 3)).copy()
                    assert glGetError() == 0
                    if not args.baseline:
                        for anchor, (x, y) in enumerate(menu.lan_preview_starts):
                            owner = menu.lan_options['spawn_slots'].index(anchor)
                            rgb = np.array([round(v * 255) for v in PLAYER_COLORS[menu.lan_options['colors'][owner]]])
                            assert np.max(np.abs(frame[y, x].astype(int) - rgb)) <= 8, (mid, anchor, frame[y, x], rgb)
                        built = build_lan_map(menu.skirmish_store, menu.lan_options)
                        assert built['players'][0]['start'] == menu.skirmish_store.maps[mid]['players'][-1]['start']
                        gm = GameManager.start_skirmish(built)
                        assert len(gm.state.players) == capacity
                        for _ in range(3):
                            gm.step(1 / 30)
                        assert not gm.state.game_over
                        with patch('pygame.font.SysFont', side_effect=AssertionError('font allocated on warmed frame')):
                            menu.render(0)
                    path = out / f'{width}x{height}_{mid}_{mode}.png'
                    pygame.image.save(pygame.image.frombuffer(frame.tobytes(), (width, height), 'RGB'), str(path))
                    rows.append(dict(map=mid, size=[width, height], mode=mode, players=menu.lan_options['human_count'] + menu.lan_options['ai_count'], sha256=hashlib.sha256(path.read_bytes()).hexdigest(), capture=path.name))
                    print('PASS', width, height, mid, mode, flush=True)
                finally:
                    menu.close()
            assert len(rows) == (1 if args.baseline else 27)
            report = dict(captures=rows, count=len(rows), scope='Real SDL/OpenGL host menu, full-capacity natural input/layout/colour pixels and map-to-manager launch. Not Windows or eight-player performance acceptance.')
            (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print('LAN_DEPLOYMENT_DIAG_OK', len(rows))
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
