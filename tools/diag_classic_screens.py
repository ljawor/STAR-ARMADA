"""Real SDL/OpenGL ancillary-screen acceptance; isolated user-data paths."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pygame
import numpy as np
from OpenGL.GL import (glClear, glReadPixels, glViewport, glGetError,
                       GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_RGB, GL_UNSIGNED_BYTE)
from render.menus import MenuStack, DEFAULT_SETTINGS
from render.clean_classic import ACCENT


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ['TMPDIR']) / 'classic-screens'
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    variants = ['lan', 'lan_join', 'lobby_host', 'lobby_client', 'lobby_error',
                'settings_0', 'settings_1', 'settings_2', 'settings_4', 'balance_gains',
                'balance_levels', 'balance_tab_back', 'campaign_0', 'campaign_1',
                'briefing_0', 'briefing_5']
    pygame.init()
    try:
        with patch('render.menus.USER_DIR', str(out / 'isolated-user')), \
             patch('render.menus.SAVES_DIR', str(out / 'isolated-user/saves')), \
             patch('render.menus.SETTINGS_PATH', str(out / 'isolated-user/saves/settings.json')), \
             patch('render.menus.CAMPAIGN_PATH', str(out / 'isolated-user/saves/campaign.json')), \
             patch('render.menus.BALANCE_PATH', str(out / 'isolated-user/saves/balance.json')), \
             patch('pygame.mouse.get_pos', return_value=(0, 0)):
            for w, h in ((800, 600), (1280, 800), (1440, 900), (2400, 1400)):
                pygame.display.set_mode((w, h), pygame.DOUBLEBUF | pygame.OPENGL)
                glViewport(0, 0, w, h)
                pygame.event.pump()
                for variant in variants:
                    menu = MenuStack(w, h)
                    try:
                        menu.settings = dict(DEFAULT_SETTINGS)
                        menu.t = 5
                        menu.screen = variant.split('_')[0] if variant not in ('lan_join', 'lobby_host', 'lobby_client', 'lobby_error') else 'lan_join' if variant == 'lan_join' else 'lan_lobby'
                        if variant.startswith('settings'):
                            menu.settings_page = int(variant[-1])
                            menu.settings_focus = 0
                        if variant.startswith('campaign'):
                            menu.campaign_page = int(variant[-1])
                        if variant.startswith('briefing'):
                            menu.selected_mission = int(variant[-1])
                        if variant.startswith('balance'):
                            # A tuned draft, so the capture shows the retuned rows and the gate
                            # rather than a screen that looks identical to an untouched one.
                            menu.balance_faction = 'imperial'
                            menu.balance_draft['station_upgrades']['shipyard'] = {
                                'hull_bonus': 0.25, 'volley_shots_per_level': 3}
                            menu.balance_draft['build_levels']['shipyard'] = {
                                'imperial_battleship': 3}
                            menu.balance_station = 'shipyard'
                            menu.balance_page = 0 if variant.endswith('gains') else 1
                            menu.balance_notice = ''
                        if variant.startswith('lobby'):
                            options = deepcopy(menu.lan_options)
                            options.update(map_id='skirmish03', human_count=4, ai_count=0)
                            snap = dict(options=options, status='Lobby', port=7777, addresses=['192.168.1.8'],
                                is_host=variant != 'lobby_client', can_start=True,
                                error='Connection lost — reconnect to the host.' if variant == 'lobby_error' else None,
                                players=[dict(slot=i, name=f'Commander {i+1}', ready=i != 1) for i in range(4)])
                            menu.lan_session = SimpleNamespace(snapshot=snap, local_player=0, close=lambda: None)
                            before = deepcopy(snap)
                        menu.render(0)
                        if variant == 'balance_tab_back':
                            # The reported defect, driven the way the player drives it: with the
                            # levels page open, the gains tab must still reach its own page —
                            # the tab was drawn, the press landed, and nothing moved because the
                            # handler stepped an absolute page index (#106).
                            assert menu.balance_page == 1, 'variant must start on the levels page'
                            tab = next(b for b in menu.buttons if b['action'] == 'balance_page'
                                       and b['payload'] == 0)
                            menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                                pos=tab['rect'].center))
                            assert menu.balance_page == 0, 'the gains tab did not reach its page'
                            menu.render(0)
                            assert any(b['action'] == 'balance_step' for b in menu.buttons), \
                                'the tab switched but the body it names did not draw'
                            assert not any(b['action'] == 'balance_gate_step'
                                           for b in menu.buttons)
                        assert menu._menu_movie is not None and menu._menu_movie.available, 'Battle movie missing from non-replay screen'
                        prefix = 'lan' if menu.screen.startswith('lan') else menu.screen
                        bounds = getattr(menu, prefix + '_text_bounds')
                        if prefix == 'settings':
                            bounds = [r for _, r in bounds]
                        bounds = [r for r in bounds if r.w]
                        window = pygame.Rect(0, 0, w, h)
                        assert all(window.contains(r) for r in bounds)
                        for i, r in enumerate(bounds):
                            assert not any(r.colliderect(x) for x in bounds[i+1:]), (variant, r)
                        assert all(window.contains(b['rect']) for b in menu.buttons)
                        for i, b in enumerate(menu.buttons):
                            assert not any(b['rect'].colliderect(x['rect']) for x in menu.buttons[i+1:])
                        if variant.startswith('lobby'):
                            assert snap == before
                        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                        menu.draw_gl()
                        pixels = glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE)
                        frame = np.flipud(np.frombuffer(pixels, dtype=np.uint8).reshape(h, w, 3))
                        assert glGetError() == 0
                        assert np.max(frame) > 150
                        primary = next((b for b in menu.buttons if b['action'] in ('lan_host_setup', 'lan_connect', 'lan_start', 'lan_reconnect', 'launch_mission', 'goto_balance')), None)
                        if primary:
                            r = primary['rect']
                            scale = min(w / 1120, h / 700)
                            color = frame[r.y + round(5 * scale), r.x + round(20 * scale)].astype(int)
                            assert np.max(np.abs(color - np.array(ACCENT))) <= 8, (variant, color)
                        name = f'{w}x{h}_{variant}.png'
                        pygame.image.save(pygame.image.frombuffer(frame.tobytes(), (w, h), 'RGB'), out / name)
                        pygame.display.flip()
                        with patch('pygame.font.SysFont', side_effect=AssertionError('font allocation on warmed frame')):
                            menu.render(0)
                        rows.append(dict(size=[w, h], screen=variant, capture=name, text_count=len(bounds),
                                         actions=[b['action'] for b in menu.buttons]))
                    finally:
                        menu.close()
    finally:
        pygame.quit()
    assert len(rows) == len(variants) * 4
    (out / 'report.json').write_text(json.dumps(rows, indent=2))
    print(f'CLASSIC_SCREENS_GL_OK captures={len(rows)} out={out}')


if __name__ == '__main__':
    main()
