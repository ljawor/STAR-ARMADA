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
    parser.add_argument('--side-panels', action='store_true',
                        help='compare compact native side panels/minimap against the retained legacy control')
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
            if args.side_panels:
                # Select a real spawned command station; no simulation fixture is invented.
                stations = [e for e in ns['state'].entities.values()
                            if e.alive and e.owner == 0 and e.is_station]
                assert stations, 'ordinary skirmish did not spawn an own station'
                command = next((e for e in stations if 'command' in e.data_id), stations[0])
                ns['inputc'].selection = {command.id}
                frame()
            # Native and before controls share one paused match, camera, selection and values.
            key(pygame.K_p)
            assert ns['paused']
            session = ns['CPP']['session']
            assert session.hud.native_top_bar is True, 'ordinary main did not activate native top HUD by default'
            if args.side_panels:
                assert session.hud.native_panels is True, 'ordinary main did not activate native side HUD by default'
            stable = state_checksum(ns['state'])
            mode_attribute = 'native_panels' if args.side_panels else 'native_top_bar'
            stream = session._vector_hud if args.side_panels else session._top_hud
            setattr(session.hud, mode_attribute, False)
            publish_top = stream.publish
            def legacy_control(payload):
                model = json.loads(payload)
                model['active'] = False
                return publish_top(json.dumps(model, ensure_ascii=False).encode())
            with patch.object(stream, 'publish', legacy_control):
                pending.append('actual-main-before.png')
                frame()
            before_minimap = tuple(session.hud.minimap_rect)
            before_blocks = [tuple(r) for r in session.hud.blocked_rects]
            setattr(session.hud, mode_attribute, True)
            pending.append('actual-main-after.png')
            frame()
            assert state_checksum(ns['state']) == stable
            after_blocks = [tuple(r) for r in session.hud.blocked_rects]
            if args.side_panels:
                assert tuple(session.hud.minimap_rect) == before_minimap == (1058, 578, 210, 210)
                for x in (10, 1030):
                    assert any(r[0] == x and r[1] == 44 and r[2] == 240 for r in after_blocks), 'compact panel is not 240 logical pixels wide'
            for language in ('de', 'pl', 'ru'):
                i18n.set_language(language)
                pending.append(f'actual-main-paused-{language}.png')
                frame()
            i18n.set_language('en')
            if args.side_panels:
                # Real SDL clicks must hit the compact control geometry, not old bitmap bounds.
                for panel in ('left', 'right'):
                    for minimized in (True, False):
                        button = next(b for b in session.hud.buttons if b['kind'] == 'hud_panel'
                                      and b['payload']['panel'] == panel
                                      and b['payload']['minimized'] is minimized)
                        rect = button['rect']
                        pos = (round(rect.centerx * args.width / 1280),
                               round(rect.centery * args.height / 800))
                        for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                            pygame.event.post(pygame.event.Event(kind, pos=pos, button=1))
                            frame()
                        assert session.hud.minimized[panel] is minimized
                assert state_checksum(ns['state']) == stable
                constructor = next(e for e in ns['state'].entities.values()
                                   if e.alive and e.owner == 0 and e.is_construction)
                ns['inputc'].selection = {constructor.id}
                frame()
                region, scroll_key = next((r, k) for r, k in session.hud.scroll_rects if k == 'stations')
                initial_scroll = session.hud.scroll[scroll_key]
                distance = ns['inputc'].camera.distance
                wheel_pos = (round(region.centerx * args.width / 1280),
                             round(region.centery * args.height / 800))
                pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, y=-1, x=0, pos=wheel_pos))
                frame()
                assert session.hud.scroll[scroll_key] > initial_scroll
                assert ns['inputc'].camera.distance == distance, 'panel wheel leaked into world zoom'
                pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, y=1, x=0, pos=wheel_pos))
                frame()
                assert session.hud.scroll[scroll_key] == initial_scroll
                # Space formerly covered by the left panel is now world input.
                freed = (round(280 * args.width / 1280), round(200 * args.height / 800))
                pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=freed, button=1))
                frame()
                assert ns['inputc'].dragging and ns['inputc'].drag_start is not None
                pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=freed, button=1))
                frame()
                # Minimap stays at its old bounds and drives the real camera mapping.
                camera = ns['inputc'].camera
                old_target, old_follow = list(camera.target), camera.follow_id
                mini = session.hud.minimap_rect
                pos = (round(mini.centerx * args.width / 1280),
                       round(mini.centery * args.height / 800))
                for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                    pygame.event.post(pygame.event.Event(kind, pos=pos, button=1))
                    frame()
                tolerance = ns['state'].map_info.bounds / (mini.width - 8)
                assert abs(camera.target[0]) < tolerance and abs(camera.target[2]) < tolerance
                assert camera.follow_id is None
                camera.target[:] = old_target
                camera.follow_id = old_follow
                assert state_checksum(ns['state']) == stable
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
            font_metrics = {}
            if args.side_panels:
                import numpy as np
                def heading_ink_height(image, logical_box):
                    x, y, w, h = logical_box
                    box = (round(x * args.width / 1280), round(y * args.height / 800),
                           round((x+w) * args.width / 1280), round((y+h) * args.height / 800))
                    rgb = np.asarray(image.crop(box).convert('RGB')).astype(int)
                    ink = (rgb.min(axis=2) > 160) & (rgb.max(axis=2)-rgb.min(axis=2) < 55)
                    rows = np.where(ink.sum(axis=1) > 2)[0]
                    assert len(rows), 'selected station heading produced no legible ink'
                    return int(rows[-1]-rows[0]+1)
                old_ink = heading_ink_height(captured['actual-main-before.png'], (22,80,296,26))
                new_ink = heading_ink_height(captured['actual-main-after.png'], (19,71,222,20))
                heading_ratio = new_ink / old_ink
                assert .65 <= heading_ratio <= .90, ('compact native heading is not near 75% of legacy ink height', old_ink, new_ink)
                font_metrics = dict(heading_ink_height_before=old_ink, heading_ink_height_after=new_ink,
                                    heading_ink_ratio=heading_ratio)
            region_height = args.height if args.side_panels else header
            board = Image.new('RGB', (args.width, (region_height + 24) * 2), (8, 14, 27))
            from PIL import ImageDraw
            draw = ImageDraw.Draw(board)
            for row, name in enumerate(('actual-main-before.png', 'actual-main-after.png')):
                y = row * (region_height + 24)
                draw.text((10, y + 4), 'BEFORE: Python bitmap scaled up' if row == 0 else
                          ('AFTER: native side panels at 75% width/height; minimap unchanged' if args.side_panels else
                           'AFTER: C++ glyphs at native framebuffer resolution'), fill=(214, 224, 238))
                board.paste(captured[name].crop((0, 0, args.width, region_height)), (0, y + 24))
            board.save(args.out / ('actual-main-side-comparison.png' if args.side_panels else
                                   'actual-main-top-comparison.png'))
            report = {'passed': True, 'drawable': [ns['W'], ns['H']], 'entrypoint': 'main.py --skirmish',
                      'loop': 'unaltered production AST loop body, real SDL input and EmbeddedWindow.present',
                      'capture': 'GL framebuffer immediately before normal flip; hidden Cocoa window',
                      'paused_same_state_before_after': True, 'top_bar_click_occlusion': True,
                      'pause_resume_gameplay': True, 'python_top_bar_disabled_by_default': session.hud.native_top_bar,
                      'top_hud_bytes': session.counts['top_hud_bytes'],
                      'files': sorted(captured)}
            if args.side_panels:
                report.update(native_side_panels_default=True, side_scale=0.75,
                              minimap_unchanged=list(before_minimap), compact_collapse_restore_clicks=True,
                              freed_world_input=True, minimap_camera_click=True,
                              panel_wheel_down_up=True,
                              **font_metrics,
                              vector_hud_bytes=session.counts['vector_hud_bytes'],
                              before_blocks=before_blocks, after_blocks=after_blocks)
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
