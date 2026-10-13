"""Isolated real SDL/GL saved-game workflow. No real user data is accessed.
Run: PYTHONPATH=. .venv/bin/python tools/diag_saved_games.py --out NEW_SCRATCH_DIR
"""
import argparse
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if os.environ.get('SDL_VIDEODRIVER') == 'dummy':
        raise RuntimeError('Requires real SDL/GL, not dummy video')
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    import pygame
    from OpenGL.GL import glReadPixels, glGetError, glViewport, GL_RGB, GL_UNSIGNED_BYTE
    from render import menus
    captures = []
    loaded_modes = []
    loaded_missions = []
    window_modes = []
    ns = None
    with tempfile.TemporaryDirectory(prefix='saved-games-', dir=out) as isolated:
        user = Path(isolated)
        saves = user / 'saves'
        saves.mkdir()
        with patch.multiple(menus, USER_DIR=str(user), SAVES_DIR=str(saves),
                            SETTINGS_PATH=str(saves / 'settings.json'),
                            CAMPAIGN_PATH=str(saves / 'campaign.json')), \
                patch.object(sys, 'argv', [str(ROOT / 'main.py')]):
            try:
                tree = ast.parse((ROOT / 'main.py').read_text())
                index = next(i for i, node in enumerate(tree.body) if isinstance(node, ast.While))
                ns = {'__name__': '__saved_games_probe__', '__file__': str(ROOT / 'main.py')}
                exec(compile(ast.Module(body=tree.body[:index], type_ignores=[]), 'main.py', 'exec'), ns)
                frame_node = ast.For(target=ast.Name(id='_probe_frame', ctx=ast.Store()),
                    iter=ast.Tuple(elts=[ast.Constant(0)], ctx=ast.Load()), body=tree.body[index].body, orelse=[])
                frame_code = compile(ast.fix_missing_locations(ast.Module(body=[frame_node], type_ignores=[])),
                                     'main.py', 'exec')
                class Clock:
                    def tick(self, rate):
                        return 0
                ns['clock'] = Clock()
                pygame.event.clear()

                def frame():
                    exec(frame_code, ns)

                def capture(name):
                    menu = ns['menu']
                    menu.render(0)
                    menu.draw_gl()
                    w, h = ns['W'], ns['H']
                    raw = glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE)
                    image = pygame.transform.flip(pygame.image.frombuffer(raw, (w, h), 'RGB'), False, True)
                    path = out / name
                    pygame.image.save(image, str(path))
                    assert pygame.surfarray.array3d(image).max() > 100
                    assert glGetError() == 0
                    assert all(pygame.Rect(0, 0, w, h).contains(b['rect']) for b in menu.buttons)
                    bounds = getattr(menu, 'save_text_bounds', [])
                    assert all(pygame.Rect(0, 0, w, h).contains(b) for b in bounds)
                    assert not any(a.colliderect(b) for i, a in enumerate(bounds) for b in bounds[i + 1:] if a.w and b.w)
                    captures.append(name)
                    pygame.display.flip()

                def click(action, payload=None):
                    menu = ns['menu']
                    menu.render(0)
                    button = next(b for b in menu.buttons if b['action'] == action and
                                  (payload is None or b['payload'] == payload))
                    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button['rect'].center))
                    frame()

                from game.core.manager import GameManager
                from game.data.store import DataStore
                definition = ns['menu'].campaign['missions'][0]
                source = GameManager.start_mission(DataStore.get().maps[definition['map']], definition)
                for _ in range(45):
                    source.step(1/30)
                ns['state'] = source.state
                ns['write_save'](str(saves / 'quicksave.json'))  # production F5 writer
                original = (saves / 'quicksave.json').read_bytes()
                (saves / 'quicksave.json').unlink()
                (saves / 'settings.json').write_text('{"sentinel":true}')
                (saves / 'campaign.json').write_text('{"schema_version":2,"unlocked_mission_ids":[]}')
                sentinels = {p.name: p.read_bytes() for p in saves.iterdir()}

                for w, h in ((800, 600), (1440, 900)):
                    ns['menu'].close()  # all resources freed before GL context replacement
                    for name in ('renderer', 'hud'):
                        if ns.get(name) is not None:
                            ns[name].close()
                            ns[name] = None
                    if ns.get('presentation') is not None:
                        ns['presentation'].cleanup()
                        ns['presentation'] = None
                    pygame.display.quit()
                    pygame.display.init()
                    flags = pygame.DOUBLEBUF | pygame.OPENGL
                    if w == 1440:
                        flags |= pygame.FULLSCREEN
                    surface = pygame.display.set_mode((w, h), flags)
                    assert surface.get_size() == (w, h), (w, h, surface.get_size(), flags)
                    window_modes.append('fullscreen' if flags & pygame.FULLSCREEN else 'windowed')
                    glViewport(0, 0, w, h)
                    ns['W'], ns['H'] = w, h
                    ns['menu'] = menus.MenuStack(w, h)
                    menu = ns['menu']
                    menu.screen = 'main'
                    ns['mode'] = 'menu'
                    capture(f'main-{w}.png')
                    click('goto_saved_games')
                    capture(f'empty-{w}.png')
                    for i in range(9):
                        (saves / f'autosave_{i}.json').write_bytes(original)
                        os.utime(saves / f'autosave_{i}.json', (100 + i, 100 + i))
                    quick = saves / 'quicksave.json'
                    quick.write_bytes(original)
                    os.utime(quick, (200, 200))
                    corrupt = saves / 'autosave.json'
                    corrupt.write_text('{bad')
                    os.utime(corrupt, (300, 300))
                    click('save_refresh')
                    capture(f'normal-{w}.png')
                    before = ns['gm']
                    click('select_save', str(quick))
                    assert ns['gm'] is before and ns['mode'] == 'menu'
                    capture(f'selected-{w}.png')
                    click('save_page', 1)
                    capture(f'paged-{w}.png')
                    click('save_page', -1)
                    click('select_save', str(corrupt))
                    click('load_save')
                    assert ns['mode'] == 'menu' and ns['gm'] is before
                    assert 'Cannot load' in menu.save_notice
                    capture(f'corrupt-{w}.png')
                    click('save_delete')
                    capture(f'confirmation-{w}.png')
                    assert {b['action'] for b in menu.buttons} == {'save_cancel_delete', 'save_confirm_delete'}
                    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0))
                    frame()
                    assert corrupt.exists() and menu.save_confirmation is None
                    click('select_save', str(quick))
                    click('load_save')  # actual main result dispatcher -> existing start_game
                    assert ns['mode'] == 'game' and ns['playback'] is None
                    loaded_modes.append(ns['state'].game_type)
                    loaded_missions.append(ns['gm'].mission.mission['id'])
                    precise = lambda manager: json.loads(json.dumps(manager.state.to_dict(precise=True)))
                    assert precise(ns['gm']) == precise(source)
                    assert ns['mission_def'] == source.mission.mission
                    ns['paused'] = True
                    frame()  # full renderer/HUD/gameplay loop after transition
                    assert glGetError() == 0
                    for tick in range(120):
                        ns['gm'].step(1/30)
                        source.step(1/30)
                        assert precise(ns['gm']) == precise(source), tick
                    # Re-create the original source for the second resolution.
                    from game.core.state import GameState
                    source = GameManager(GameState.from_dict(json.loads(original)))
                    ns['leave_game']()
                    menu.open_saved_games()
                    click('save_delete_all')
                    click('save_confirm_delete')
                    assert menu.save_paths == []
                    for name, data in sentinels.items():
                        assert (saves / name).read_bytes() == data
                report = dict(captures=captures, loaded_modes=loaded_modes,
                              loaded_missions=loaded_missions, window_modes=window_modes,
                              continued_ticks_per_load=120, production_writer=True,
                              actual_main_dispatch=True, protected_files_preserved=True,
                              isolated_user_removed=True,
                              limitations=['Native Windows gate not run on macOS; not a natural human playthrough.'])
            finally:
                if ns is not None:
                    if ns.get('menu') is not None:
                        ns['menu'].close()
                    for name in ('renderer', 'hud'):
                        if ns.get(name) is not None:
                            ns[name].close()
                    if ns.get('audio') is not None:
                        ns['audio'].cleanup()
                    if ns.get('presentation') is not None:
                        ns['presentation'].cleanup()
                pygame.quit()
    (out / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
