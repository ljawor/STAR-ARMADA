#!/usr/bin/env python3
"""Actual-main notification acceptance capture (requires authorized Cocoa/GL use).

CPU-safe: --help, importing this file, and py_compile never import the game.
Run with a unique empty --out directory. Output: notification-metrics.json,
unaltered framebuffer PNGs, per-frame vector JSON, and method observation JSON.
Only _event_log and _flash_message use a paired legacy control; approved native
side panels, minimap and top bar remain enabled in BOTH images. There is no
software renderer, substitute scene, synthetic screenshot, or production edit.

The completion-event fixture is explicitly presentation setup: after pausing a
real skirmish, publish build/research/colonization/loss events on its real
production EventBus. This is NOT a claim that gameplay commands completed.
Checksums are established
AFTER fixture publication. Expiry alone resumes simulation until main.flash's
real state.time deadline, then pauses again and establishes a new baseline.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import traceback
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULES = ('_event_log', '_flash_message')
LANGUAGES = ('en', 'de', 'pl', 'ru')


def shipped_resolutions(path=None):
    """Read the production preset tuple without importing the game package."""
    source = Path(path or ROOT / 'render/display_settings.py').read_text(encoding='utf-8')
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == 'RESOLUTIONS'):
            return tuple(ast.literal_eval(node.value))
    raise RuntimeError('render/display_settings.py declares no RESOLUTIONS tuple')


def require(condition, message):
    """Do not lose acceptance gates when invoked with python -O."""
    if not condition:
        raise AssertionError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.writing')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def _owner_game_argv(argv):
    """Match executable/script positions, never mentions in docs or python -c."""
    if not argv:
        return False
    executable = Path(argv[0]).name
    if executable == 'armada_viewer':
        return True
    if not re.fullmatch(r'python(?:w)?(?:\d+(?:\.\d+)*)?', executable, re.IGNORECASE):
        return False
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg == '--':
            index += 1
            break
        if arg in ('-c', '-m') or arg.startswith(('-c', '-m')):
            return False
        if not arg.startswith('-') or arg == '-':
            break
        index += 2 if arg in ('-W', '-X', '--check-hash-based-pycs') else 1
    return index < len(argv) and Path(argv[index]).name == 'main.py'


def require_no_owner_game():
    """Fail closed on enumeration/ancestry errors; never signal any process."""
    try:
        result = subprocess.run(['ps', '-axo', 'pid=,ppid=,command='],
                                check=True, capture_output=True, text=True, timeout=10)
        processes = {}
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            pid, parent, command = line.strip().split(None, 2)
            pid, parent = int(pid), int(parent)
            if pid <= 0 or parent < 0 or pid in processes:
                raise ValueError('invalid/duplicate process PID')
            processes[pid] = (parent, command)
        excluded = set()
        pid = os.getpid()
        while pid:
            if pid in excluded or pid not in processes:
                raise ValueError('incomplete/cyclic process ancestry')
            excluded.add(pid)
            pid = processes[pid][0]
        owners = []
        for pid, (_, command) in processes.items():
            if pid not in excluded and _owner_game_argv(shlex.split(command)):
                owners.append(pid)
    except Exception as exc:
        raise RuntimeError(f'owner game preflight failed; cannot establish idle owner: {exc}') from exc
    if owners:
        raise RuntimeError(f'owner game running (PID {", ".join(map(str, sorted(owners)))}); refusing capture')


def run(args, report):
    # This function is the ONLY GPU/game entry; CLI help never enters it.
    require_no_owner_game()
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    sys.path.insert(0, str(ROOT))
    import pygame
    from OpenGL.GL import (glReadPixels, GL_RGB, GL_UNSIGNED_BYTE, glFinish,
                           glGetIntegerv, glPixelStorei, GL_PACK_ALIGNMENT)
    from PIL import Image, ImageChops, ImageStat
    from render import menus, i18n, display_settings
    from game.net.replay import state_checksum

    # The production window only honours a shipped resolution preset; any other
    # size is silently replaced by desktop-derived 'auto', so refuse it up front
    # instead of failing after a real frame has already been rendered.
    requested = f'{args.width}x{args.height}'
    require(display_settings.validate_resolution(requested) == requested,
            f'{requested} is not a shipped resolution preset; use one of '
            f'{", ".join(display_settings.RESOLUTIONS[1:])}')

    ns: dict[str, Any] = {'__name__': '__native_notification_hud_game_probe__', '__file__': str(ROOT / 'main.py')}
    pending = []
    images = {}
    traces = {}
    models = {}
    active_method = []
    observations = {}
    current_model = {}
    legacy = False
    cleanup_errors = []
    saved_log = None
    original_cwd = Path.cwd()
    real_set_mode, real_flip = pygame.display.set_mode, pygame.display.flip
    # Snapshot the real paths BEFORE redirecting any settings constants. This
    # includes packaged-user locations, not just the development saves folder.
    protected = {ROOT / 'main.py', ROOT / 'render/hud.py',
                 ROOT / 'render_bridge/vector_hud.py', ROOT / 'render_bridge/live.py',
                 ROOT / 'tools/render/capture_native_top_hud_game.py'}
    protected.update(Path(getattr(menus, name)) for name in
                     ('SETTINGS_PATH', 'CAMPAIGN_PATH', 'BALANCE_PATH'))
    protected.update(ROOT / 'saves' / (name + '.json') for name in ('settings', 'campaign', 'balance'))
    original_hashes = {str(p): digest(p) for p in sorted(protected)}
    report['protected_before'] = original_hashes
    sandbox = args.out / 'isolated-user'
    (sandbox / 'saves').mkdir(parents=True)
    settings = dict(menus.DEFAULT_SETTINGS, resolution=f'{args.width}x{args.height}',
                    fullscreen=False, music_volume=0.0, sfx_volume=0.0, autosave=False,
                    cinematics_enabled=False, tutorial_hints=False, language='en')
    write_json(sandbox / 'saves/settings.json', settings)

    def hidden_set_mode(size, flags=0, *a, **kw):
        return real_set_mode(size, (flags & ~pygame.FULLSCREEN) | pygame.HIDDEN, *a, **kw)

    def flip():
        if pending:
            name = pending.pop(0)
            glFinish()
            w, h = pygame.display.get_surface().get_size()
            require((w, h) == (args.width, args.height), 'unexpected physical framebuffer dimensions')
            alignment = glGetIntegerv(GL_PACK_ALIGNMENT)
            try:
                glPixelStorei(GL_PACK_ALIGNMENT, 1)
                raw = glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE)
            finally:
                glPixelStorei(GL_PACK_ALIGNMENT, alignment)
            image = Image.frombytes('RGB', (w, h), raw).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            require(image.getextrema() != ((0, 0), (0, 0), (0, 0)), 'black framebuffer')
            image.save(args.out / (name + '.png'))
            images[name] = image
        real_flip()

    def frame(name=None):
        observations.clear()
        current_model.clear()
        if name:
            pending.append(name)
        exec(loop_code, ns)
        require(not ns['CPP'].get('failed'), f"native renderer failed: {ns['CPP'].get('failed')}")
        require(ns['mode'] == 'game' and ns['CPP']['window'].embedded, 'not the embedded production game')
        if name:
            require(not pending and name in images, 'production flip did not provide framebuffer capture')
            require(current_model.get('active') is True, 'native vector stream was disabled')
            require(set(observations) == set(MODULES), 'production HUD did not call both notification methods')
            traces[name] = json.loads(json.dumps(observations))
            models[name] = json.loads(json.dumps(current_model))
            write_json(args.out / (name + '-methods.json'), traces[name])
            write_json(args.out / (name + '-vector.json'), models[name])
        return observations

    def key(code):
        for kind in (pygame.KEYDOWN, pygame.KEYUP):
            pygame.event.post(pygame.event.Event(kind, key=code, mod=0))
            frame()

    def method_wrapper(method_name, original):
        @functools.wraps(original)
        def observed(*a, **kw):
            nonlocal legacy
            require(hud.native_panels is True, 'shared native_panels flag must remain production-default True')
            start_blocks = len(hud.blocked_rects)
            capture = hud._native_capture()
            start_ops = len(capture.ops)
            info = {'legacy_control': legacy, 'labels': [], 'arguments': list(a)}
            active_method.append(info)
            try:
                # Toggle ONLY while executing this one original method. Never
                # disable the ring, side panels or minimap for the before image.
                if legacy:
                    hud.native_panels = False
                return original(*a, **kw)
            finally:
                hud.native_panels = True
                active_method.pop()
                info['blocks'] = [list(r) for r in hud.blocked_rects[start_blocks:]]
                info['ops'] = json.loads(json.dumps(capture.ops[start_ops:]))
                observations[method_name] = info
        return observed

    def texts(info):
        return [op['text'] for op in info['ops'] if op['kind'] == 'text']

    def only_block(info):
        require(len(info['blocks']) == 1, f"expected one notification hitbox: {info}")
        return pygame.Rect(info['blocks'][0])

    def physical(rect):
        r = pygame.Rect(rect)
        return (round(r.left * args.width / hud.width), round(r.top * args.height / hud.height),
                round(r.right * args.width / hud.width), round(r.bottom * args.height / hud.height))

    def image_delta(a, b, rect):
        delta = ImageChops.difference(images[a].crop(physical(rect)), images[b].crop(physical(rect)))
        stat = ImageStat.Stat(delta)
        return {'mean_absolute_rgb': sum(stat.mean) / 3, 'changed': delta.getbbox() is not None}

    def other_ops(name):
        # Remove the exact contiguous notification op subsequences, retaining all
        # native side-panel/minimap primitives as an independent control gate.
        ops = list(models[name]['ops'])
        for module in MODULES:
            subset = traces[name][module]['ops']
            if subset:
                indexes = [i for i in range(len(ops) - len(subset) + 1)
                           if ops[i:i + len(subset)] == subset]
                require(len(indexes) == 1, 'notification op span is not uniquely observable')
                del ops[indexes[0]:indexes[0] + len(subset)]
        return ops

    def paired(name):
        nonlocal legacy
        baseline = state_checksum(ns['state'])
        minimap = list(hud.minimap_rect)
        selection = set(ns['inputc'].selection)
        legacy = True
        try:
            frame(name + '-before')
        finally:
            legacy = False
        frame(name + '-after')
        require(state_checksum(ns['state']) == baseline, 'presentation mutated paused simulation')
        require(ns['inputc'].selection == selection, 'presentation changed selection')
        require(list(hud.minimap_rect) == minimap, 'notification control changed approved minimap')
        require(other_ops(name + '-before') == other_ops(name + '-after'),
                'paired control changed native panels/minimap primitives')
        report['checksums'][name] = {'before': baseline, 'after': state_checksum(ns['state'])}
        return traces[name + '-before'], traces[name + '-after']

    def check_geometry(before, after, name, expected_rows):
        old_incoming, incoming = only_block(before['_event_log']), only_block(after['_event_log'])
        old_flash, flash = only_block(before['_flash_message']), only_block(after['_flash_message'])
        require(old_incoming.width == 420 and old_incoming.height == 34 + 18 * len(expected_rows),
                'legacy INCOMING reference geometry changed')
        require(incoming.left == 10 and incoming.width == 240 and incoming.bottom == hud.height - 14,
                f'INCOMING must align with approved 10px/240px left panel: {incoming}')
        require(abs(incoming.height - old_incoming.height * .75) <= 1, 'INCOMING height is not 75% of legacy')
        require(any(r.x == 10 and r.y == 44 and r.width == 240 for r in hud.blocked_rects),
                'selected real station has no approved 240px left panel')
        centre = (hud.width // 2, hud.height - 60)
        require(old_flash.center == centre and all(abs(a - b) <= 1 for a, b in zip(flash.center, centre)),
                'flash centre moved beyond edge-rounding tolerance')
        require(all(abs(new - old * .75) <= 1 for new, old in zip(flash.size, old_flash.size)),
                'flash background width/height are not 75% of measured legacy')
        native_lines = texts(after['_event_log'])
        require(native_lines == [i18n.t('INCOMING'), *expected_rows],
                f'wrong latest-nine/owner/order/text in native INCOMING: {native_lines!r}')
        require(before['_event_log']['labels'] == [i18n.t('INCOMING'), *expected_rows],
                'legacy control did not draw expected event-tag generated text')
        require(not before['_event_log']['ops'] and not before['_flash_message']['ops'],
                'legacy-only notification control still emits native notification ops')
        require(ns['view_msg'] in texts(after['_flash_message']), 'native flash omitted exact main-loop message')
        flash_text = [op for op in after['_flash_message']['ops'] if op['kind'] == 'text']
        require(len(flash_text) == 1 and flash_text[0]['fit'] == 'center', 'native flash ink is not center-fitted')
        bounds = pygame.Rect(flash_text[0]['bounds'])
        require(flash.contains(bounds) and all(abs(a - b) <= 1 for a, b in zip(bounds.center, centre)),
                'native flash text box is not centered within its transformed background')
        for module, rect in (('_event_log', incoming), ('_flash_message', flash)):
            require(after[module]['ops'], 'default notification has no native vector operations')
            backgrounds = [pygame.Rect(op['rect']) for op in after[module]['ops']
                           if op['kind'] == 'rect' and op['stroke'] == 0]
            require(rect in backgrounds, 'native painted background does not match input occlusion')
            require(image_delta(name + '-before', name + '-after', rect)['changed'],
                    'native migration produced no changed notification framebuffer pixels')
        report['geometry'][name] = {'incoming_legacy': list(old_incoming), 'incoming_native': list(incoming),
                                  'flash_legacy_measured': list(old_flash), 'flash_native': list(flash),
                                  'expected_latest_9': expected_rows,
                                  'incoming_pixel_delta': image_delta(name + '-before', name + '-after', incoming),
                                  'flash_pixel_delta': image_delta(name + '-before', name + '-after', flash)}
        return incoming, flash

    def click(point, blocked):
        controller = ns['inputc']
        selection = set(controller.selection)
        pos = (round(point[0] * args.width / hud.width), round(point[1] * args.height / hud.height))
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
        frame()
        require(controller.dragging is (not blocked), f'wrong actual world-input occlusion at {point}')
        if blocked:
            require(controller.drag_start is None, 'blocked notification started a world drag')
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
        frame()
        if blocked:
            require(controller.selection == selection, 'notification click leaked into world selection')
        # The deliberate free-world click can deselect: restore the real station
        # for later screenshots and preserve visual left-edge alignment evidence.
        controller.selection = selection
        frame()

    stack = ExitStack()
    try:
        os.chdir(ROOT)
        for attr, value in {'USER_DIR': str(sandbox), 'SAVES_DIR': str(sandbox / 'saves'),
                            'SETTINGS_PATH': str(sandbox / 'saves/settings.json'),
                            'CAMPAIGN_PATH': str(sandbox / 'saves/campaign.json'),
                            'BALANCE_PATH': str(sandbox / 'saves/balance.json')}.items():
            stack.enter_context(patch.object(menus, attr, value))
        stack.enter_context(patch.object(pygame.display, 'set_mode', hidden_set_mode))
        stack.enter_context(patch.object(pygame.display, 'flip', flip))
        stack.enter_context(patch.object(sys, 'argv', [str(ROOT / 'main.py'), '--skirmish']))
        tree = ast.parse((ROOT / 'main.py').read_text(encoding='utf-8'))
        index = next(i for i, node in enumerate(tree.body) if isinstance(node, ast.While))
        loop = tree.body[index]
        require(isinstance(loop, ast.While), 'production top-level loop is not a while loop')
        if not isinstance(loop, ast.While):
            raise TypeError('expected production while loop')
        report['production_loop_ast_sha256'] = hashlib.sha256(ast.dump(loop).encode()).hexdigest()
        exec(compile(ast.Module(body=tree.body[:index], type_ignores=[]), str(ROOT / 'main.py'), 'exec'), ns)
        once = ast.For(target=ast.Name(id='_capture_frame', ctx=ast.Store()),
                       iter=ast.Tuple(elts=[ast.Constant(0)], ctx=ast.Load()), body=loop.body, orelse=[])
        require(ast.dump(ast.Module(body=once.body, type_ignores=[])) ==
                ast.dump(ast.Module(body=loop.body, type_ignores=[])), 'production loop body changed')
        loop_code = compile(ast.fix_missing_locations(ast.Module(body=[once], type_ignores=[])),
                            str(ROOT / 'main.py'), 'exec')
        frame()
        require((ns['W'], ns['H']) == (args.width, args.height), 'wrong production output resolution')
        key(pygame.K_p)
        require(ns['paused'], 'real pause key failed')
        session = ns['CPP']['session']
        hud = session.hud
        require(hud is ns['hud'], 'input and native session do not share the production HUD')
        require(hud.native_panels is True and hud.native_top_bar is True, 'production native defaults are not enabled')
        require(all(callable(getattr(hud, method, None)) for method in MODULES), 'notification extraction not installed')
        station = next(e for e in ns['state'].entities.values()
                       if e.alive and e.owner == ns['local_player'] and e.is_station)
        ns['inputc'].selection = {station.id}
        frame()
        for method in MODULES:
            stack.enter_context(patch.object(hud, method, method_wrapper(method, getattr(hud, method))))
        original_label = hud._label
        def label(x, y, text, *a, **kw):
            if active_method:
                active_method[-1]['labels'].append(i18n.t(text))
            return original_label(x, y, text, *a, **kw)
        stack.enter_context(patch.object(hud, '_label', label))
        original_publish = session._vector_hud.publish
        def publish(payload):
            current_model.clear()
            current_model.update(json.loads(payload))
            return original_publish(payload)
        stack.enter_context(patch.object(session._vector_hud, 'publish', publish))

        bus = ns['state'].events
        saved_log = list(bus.log)
        bus.log.clear()
        fixture_before = state_checksum(ns['state'])
        # Real production EventBus, paused presentation-event setup. No invented
        # entities or fabricated command completion/world mutation is claimed.
        # First three must be evicted by the latest-nine display limit. The
        # remaining nine exercise every actual notification symbol shape.
        faction = ns['state'].players[ns['local_player']].faction
        fixture = [('station_built', {'station': 'mining_station'})] * 3 + [
            ('station_built', {'station': 'sensor_station'}),
            ('station_built', {'station': 'trade_station'}),
            ('research_complete', {'tech': 'sensor_range'}),
            ('planet_colonized', {'planet': 'New Terra'}),
            ('unit_destroyed', {'unit': 'fighter', 'faction': faction}),
            ('station_built', {'station': 'trade_station'}),
            ('research_complete', {'tech': 'energy_efficiency'}),
            ('planet_colonized', {'planet': 'Frontier'}),
            ('unit_destroyed', {'unit': 'interceptor', 'faction': faction}),
        ]
        for event_type, data in fixture:
            bus.publish(event_type, entity_id=station.id, owner=ns['local_player'], **data)
        enemy = next(owner for owner in ns['state'].players if owner != ns['local_player'])
        bus.publish('station_built', entity_id=station.id, station='shipyard', owner=enemy)
        report['fixture'] = {'kind': 'real production EventBus presentation-event setup AFTER pause',
                             'not_construction_command_completion': True,
                             'before_checksum': fixture_before, 'after_checksum': state_checksum(ns['state']),
                             'events': [{'type': ev.type, 'data': dict(ev.data)} for ev in bus.log]}
        expected = [hud._event_text(ev, ns['local_player']) for ev in bus.log
                    if ev.data['owner'] == ns['local_player']][-9:]
        require(len(expected) == 9 and all('mining_station' not in text and 'shipyard' not in text for text in expected),
                'fixture does not discriminate latest-nine and enemy filtering')
        require(set(text[0] for text in expected) == set('△✦◉✕'), 'fixture omitted a native symbol shape')
        report['fixture']['symbol_shapes'] = sorted(set(text[0] for text in expected))
        ns['flash']('Constructing sensor station')
        before, after = paired('construction-en')
        incoming, flash_rect = check_geometry(before, after, 'construction-en', expected)
        first_message = ns['flash_msg']
        # Use a shipped format string, not invented translations of runtime text.
        template = '{page} · Page {n}/{total}'
        messages = {}
        for language in LANGUAGES:
            require(i18n.set_language(language) == language, 'language catalogue unavailable')
            require(template in i18n.load_pack(language), 'existing formatted catalogue entry missing')
            message = i18n.t(template, page=i18n.t('INCOMING'), n=2, total=3)
            messages[language] = message
            ns['flash'](message)
            before, after = paired('language-' + language)
            incoming, flash_rect = check_geometry(before, after, 'language-' + language, expected)
            require(first_message not in texts(after['_flash_message']), 'old flash was appended instead of replaced')
        require(len(set(messages.values())) == 4, 'language test did not exercise four actual translated strings')
        report['languages'] = messages
        report['replacement'] = True
        i18n.set_language('en')
        ns['flash']('Constructing sensor station')
        frame()
        incoming = only_block(observations['_event_log'])
        flash_rect = only_block(observations['_flash_message'])
        stable = state_checksum(ns['state'])
        click(incoming.center, True)
        click(flash_rect.center, True)
        # Previous wide INCOMING coverage must now be available to actual picking.
        freed = (min(400, hud.width // 2 - 100), incoming.centery)
        require(250 < freed[0] < 430 and not any(r.collidepoint(freed) for r in hud.blocked_rects),
                'chosen former wide INCOMING area is not free world space')
        click(freed, False)
        require(state_checksum(ns['state']) == stable, 'input occlusion probe mutated paused simulation')
        report['input'] = {'incoming_blocks_click': True, 'flash_blocks_click': True,
                           'former_wide_incoming_world_drag': list(freed), 'station_selection_restored': True}
        key(pygame.K_F1)
        require(ns['presentation'].help_visible and ns['presentation'].panel_rects, 'application help overlay failed')
        frame('application-help-over-notifications')
        overlay_selection = set(ns['inputc'].selection)
        click(ns['presentation'].panel_rects[0].center, True)
        require(ns['inputc'].selection == overlay_selection, 'application help leaked click into world')
        key(pygame.K_F1)
        require(not ns['presentation'].help_visible, 'application controls were not restored')
        report['application_overlay'] = {'help_shown_over_notifications': True, 'input_consumed': True}

        # Observe natural expiry in the real main loop; never forge time or timer.
        ns['flash']('Constructing sensor station')
        deadline = ns['flash_until']
        key(pygame.K_p)
        require(not ns['paused'], 'could not resume for real timer expiry')
        for _ in range(1800):
            if ns['state'].time >= deadline:
                break
            frame()
        require(ns['state'].time >= deadline, 'main-loop flash timer did not expire within frame budget')
        key(pygame.K_p)
        require(ns['paused'] and ns['view_flash'] == 0, 'main loop did not suppress naturally expired flash')
        before, after = paired('expired-flash')
        for info in (before['_flash_message'], after['_flash_message']):
            require(not info['ops'] and not info['blocks'], 'expired flash left native ops or input occlusion')
        delta = image_delta('expired-flash-before', 'expired-flash-after', flash_rect)
        require(delta['mean_absolute_rgb'] <= 1.5, f'expired native flash pixels differ from empty legacy control: {delta}')
        report['expiry'] = {'deadline': deadline, 'observed_state_time': ns['state'].time,
                             'view_flash': ns['view_flash'], 'clear_pixel_control': delta}
        # Clear event fixture after pausing, then compare genuine empty modules.
        bus.log.clear()
        before, after = paired('empty-notifications')
        for module in MODULES:
            require(not after[module]['ops'] and not after[module]['blocks'] and not before[module]['blocks'],
                    'empty notification left stale operations or hitboxes')
        delta = image_delta('empty-notifications-before', 'empty-notifications-after', incoming)
        require(delta['mean_absolute_rgb'] <= 1.5, f'empty native INCOMING pixels differ from empty legacy control: {delta}')
        require(image_delta('construction-en-after', 'empty-notifications-after', incoming)['changed'],
                'INCOMING empty capture is unchanged from active capture')
        report['empty_incoming'] = {'no_stale_ops_or_input_rect': True, 'clear_pixel_control': delta}
        report['drawable'] = [args.width, args.height]
        report['logical_size'] = [hud.width, hud.height]
        report['native_panels_default'] = hud.native_panels
        report['files'] = sorted(p.name for p in args.out.iterdir() if p.is_file() and p.name != 'notification-metrics.json')
        expected_images = {'construction-en-before', 'construction-en-after',
                           'application-help-over-notifications', 'expired-flash-before', 'expired-flash-after',
                           'empty-notifications-before', 'empty-notifications-after'}
        expected_images.update('language-' + lang + suffix for lang in LANGUAGES for suffix in ('-before', '-after'))
        require(set(images) == expected_images,
                f'missing/extra genuine captures: expected {sorted(expected_images)}, got {sorted(images)}')
        report['image_count'] = len(images)
        report['acceptance_complete'] = True
    finally:
        # Attempt every cleanup even if an earlier cleanup fails. passed remains
        # false until all of these AND protected-file readback have succeeded.
        def cleanup(label, operation):
            try:
                operation()
            except BaseException as exc:
                cleanup_errors.append(f'{label}: {type(exc).__name__}: {exc}')
        if saved_log is not None:
            cleanup('restore event log', lambda: ns['state'].events.log.__setitem__(slice(None), saved_log))
        if 'cpp_reset' in ns:
            cleanup('cpp_reset', ns['cpp_reset'])
        for name in ('presentation', 'menu', 'hud', 'renderer'):
            obj = ns.get(name)
            operation = getattr(obj, 'cleanup' if name == 'presentation' else 'close', None)
            if operation:
                cleanup(name, operation)
        if ns.get('audio') is not None:
            cleanup('audio', ns['audio'].cleanup)
        cleanup('pygame.quit', pygame.quit)
        cleanup('restore patches', stack.close)
        cleanup('restore cwd', lambda: os.chdir(original_cwd))
        after_hashes = {str(p): digest(p) for p in sorted(protected)}
        report['protected_after'] = after_hashes
        report['protected_files_unchanged'] = after_hashes == original_hashes
        report['cleanup_errors'] = cleanup_errors
        report['cleanup_complete'] = not cleanup_errors
        require(not cleanup_errors, f'cleanup failed: {cleanup_errors}')
        require(after_hashes == original_hashes, 'probe modified protected production/user files')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, required=True, help='unique empty artifact directory; never reuse a run')
    parser.add_argument('--width', type=int, default=2560, help='physical framebuffer width (default: 2560)')
    parser.add_argument('--height', type=int, default=1440, help='physical framebuffer height (default: 1440)')
    args = parser.parse_args(argv)
    if args.width < 640 or args.height < 480:
        parser.error('framebuffer must be at least 640x480')
    presets = shipped_resolutions()
    requested = f'{args.width}x{args.height}'
    if requested not in presets:
        # The window only honours a shipped preset; any other size silently
        # becomes desktop-derived 'auto', so say so instead of failing mid-run.
        parser.error(f'{requested} is not a shipped resolution preset '
                     f'(use one of: {", ".join(presets[1:])})')
    args.out = args.out.expanduser().resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    if any(args.out.iterdir()):
        parser.error('--out must be empty; refusing to overwrite/reuse an acceptance run')
    report = {'passed': False, 'acceptance_complete': False, 'cleanup_complete': False,
              'entrypoint': 'main.py --skirmish', 'loop': 'unchanged production AST while body, one frame at a time',
              'capture': 'real embedded Cocoa/OpenGL framebuffer before normal flip; hidden SDL window',
              'control_scope': list(MODULES), 'geometry': {}, 'checksums': {}}
    metrics = args.out / 'notification-metrics.json'
    # Exclusive creation also closes the race between two runs sharing --out.
    with metrics.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    try:
        run(args, report)
        require(report['acceptance_complete'] and report['cleanup_complete'] and
                report['protected_files_unchanged'], 'incomplete acceptance or cleanup')
        report['passed'] = True
    except BaseException as exc:
        report['passed'] = False
        report['error'] = f'{type(exc).__name__}: {exc}'
        report['traceback'] = traceback.format_exc()
    write_json(metrics, report)
    print(json.dumps({'passed': report['passed'], 'metrics': str(metrics), 'error': report.get('error')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
