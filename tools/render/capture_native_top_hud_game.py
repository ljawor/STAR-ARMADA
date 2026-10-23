#!/usr/bin/env python3
"""Capture the unchanged ordinary main.py loop, hidden, with isolated user data.

The before control uses the retained Python top bar and disables only the native
strip. The after capture is the default production path, not a special viewer.
"""
from __future__ import annotations
import argparse
import ast
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--width', type=int, default=2560)
    parser.add_argument('--height', type=int, default=1440)
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    sandbox = args.out / 'isolated-user'
    (sandbox / 'saves').mkdir(parents=True, exist_ok=True)
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    import pygame
    from OpenGL.GL import glReadPixels, GL_RGB, GL_UNSIGNED_BYTE, glFinish
    from PIL import Image
    from render import menus, i18n
    from game.net.replay import state_checksum
    protected = [ROOT / 'saves' / f'{name}.json' for name in ('settings', 'campaign', 'balance')]
    def hashes():
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in protected}
    original_hashes = hashes()
    settings = dict(menus.DEFAULT_SETTINGS, resolution=f'{args.width}x{args.height}',
                    fullscreen=False, music_volume=0.0, sfx_volume=0.0, autosave=False,
                    cinematics_enabled=False, tutorial_hints=False)
    (sandbox / 'saves/settings.json').write_text(json.dumps(settings))
    original_set_mode = pygame.display.set_mode
    original_flip = pygame.display.flip
    ns: dict[str, Any] = {'__name__': '__native_top_hud_game_probe__', '__file__': str(ROOT / 'main.py')}
    pending = []
    captured = {}
    def hidden_set_mode(size, flags=0, *a, **kw):
        return original_set_mode(size, (flags & ~pygame.FULLSCREEN) | pygame.HIDDEN, *a, **kw)
    def capture_before_flip():
        if pending:
            glFinish()
            w, h = pygame.display.get_surface().get_size()
            data = glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE)
            image = Image.frombytes('RGB', (w, h), data).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            name = pending.pop(0)
            image.save(args.out / name)
            captured[name] = image
        original_flip()
    with ExitStack() as stack:
        for attr, value in {'USER_DIR': str(sandbox), 'SAVES_DIR': str(sandbox / 'saves'),
                           'SETTINGS_PATH': str(sandbox / 'saves/settings.json'),
                           'CAMPAIGN_PATH': str(sandbox / 'saves/campaign.json'),
                           'BALANCE_PATH': str(sandbox / 'saves/balance.json')}.items():
            stack.enter_context(patch.object(menus, attr, value))
        stack.enter_context(patch.object(pygame.display, 'set_mode', hidden_set_mode))
        stack.enter_context(patch.object(pygame.display, 'flip', capture_before_flip))
        stack.enter_context(patch.object(sys, 'argv', [str(ROOT / 'main.py'), '--skirmish']))
        try:
            tree = ast.parse((ROOT / 'main.py').read_text())
            index = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.While))
            loop = tree.body[index]
            assert isinstance(loop, ast.While)
            exec(compile(ast.Module(body=tree.body[:index], type_ignores=[]), 'main.py', 'exec'), ns)
            once = ast.For(target=ast.Name(id='_capture_frame', ctx=ast.Store()),
                           iter=ast.Tuple(elts=[ast.Constant(0)], ctx=ast.Load()),
                           body=loop.body, orelse=[])
            code = compile(ast.fix_missing_locations(ast.Module(body=[once], type_ignores=[])), 'main.py', 'exec')
            def frame():
                exec(code, ns)
                assert not ns['CPP'].get('failed'), 'ordinary game reported a native renderer failure'
            def key(k):
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0))
                frame()
                pygame.event.post(pygame.event.Event(pygame.KEYUP, key=k, mod=0))
                frame()
            frame()
            assert ns['mode'] == 'game' and ns['CPP']['window'].embedded
            assert (ns['W'], ns['H']) == (args.width, args.height)
            # Native and before controls share one paused match, camera, selection and values.
            key(pygame.K_p)
            assert ns['paused']
            session = ns['CPP']['session']
            assert session.hud.native_top_bar is True, 'ordinary main did not activate native top HUD by default'
            stable = state_checksum(ns['state'])
            session.hud.native_top_bar = False
            publish_top = session._top_hud.publish
            def legacy_control(payload):
                model = json.loads(payload)
                model['active'] = False
                return publish_top(json.dumps(model, ensure_ascii=False).encode())
            with patch.object(session._top_hud, 'publish', legacy_control):
                pending.append('actual-main-before.png')
                frame()
            session.hud.native_top_bar = True
            pending.append('actual-main-after.png')
            frame()
            assert state_checksum(ns['state']) == stable
            for language in ('de', 'pl', 'ru'):
                i18n.set_language(language)
                pending.append(f'actual-main-paused-{language}.png')
                frame()
            i18n.set_language('en')
            # A click in the physical top bar must not deselect the current fleet.
            ns['inputc'].selection = {e.id for e in ns['state'].entities.values()
                                      if e.alive and e.owner == 0 and e.is_ship}
            selection = set(ns['inputc'].selection)
            assert selection, 'ordinary skirmish did not spawn an own fleet'
            for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                pygame.event.post(pygame.event.Event(kind, pos=(args.width // 2, 12), button=1))
                frame()
            assert ns['inputc'].selection == selection, 'native top strip leaked a click to world picking'
            key(pygame.K_p)
            assert not ns['paused']
            for _ in range(3):
                frame()
            assert state_checksum(ns['state']) != stable, 'game failed to resume after native pause readout'
            pending.append('actual-main-running.png')
            frame()
            header = round(34 * args.height / 800)
            board = Image.new('RGB', (args.width, (header + 24) * 2), (8, 14, 27))
            from PIL import ImageDraw
            draw = ImageDraw.Draw(board)
            for row, name in enumerate(('actual-main-before.png', 'actual-main-after.png')):
                y = row * (header + 24)
                draw.text((10, y + 4), 'BEFORE: Python bitmap scaled up' if row == 0 else
                          'AFTER: C++ glyphs at native framebuffer resolution', fill=(214, 224, 238))
                board.paste(captured[name].crop((0, 0, args.width, header)), (0, y + 24))
            board.save(args.out / 'actual-main-top-comparison.png')
            report = {'passed': True, 'drawable': [ns['W'], ns['H']], 'entrypoint': 'main.py --skirmish',
                      'loop': 'unaltered production AST loop body, real SDL input and EmbeddedWindow.present',
                      'capture': 'GL framebuffer immediately before normal flip; hidden Cocoa window',
                      'paused_same_state_before_after': True, 'top_bar_click_occlusion': True,
                      'pause_resume_gameplay': True, 'python_top_bar_disabled_by_default': session.hud.native_top_bar,
                      'top_hud_bytes': session.counts['top_hud_bytes'],
                      'files': sorted(captured)}
            (args.out / 'actual-main-metrics.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report))
        finally:
            if 'cpp_reset' in ns:
                ns['cpp_reset']()
            for name in ('menu', 'hud', 'renderer'):
                obj = ns.get(name)
                if obj is not None and hasattr(obj, 'close'):
                    obj.close()
            if ns.get('audio') is not None:
                ns['audio'].cleanup()
            pygame.quit()
            assert hashes() == original_hashes, 'probe altered real user settings/progress/balance'


if __name__ == '__main__':
    main()
