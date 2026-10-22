#!/usr/bin/env python3
"""Source-only isolated Imperium review, through the unchanged real main.py.

This is a labelled factory-prebuilt review scenario, not an organic build or
release entry point. All normal commands, simulation and native drawing remain
owned by main.py. No installed app or normal user profile is touched.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_PACKS = (
    'vigil-prototype', 'imperium-command-prototype', 'imperium-shipyard-prototype',
    'imperium-mining-prototype', 'imperium-talon-prototype', 'imperium-engineer-prototype',
    'imperium-research-prototype', 'imperium-defense-prototype', 'imperium-sensor-prototype',
    'imperium-trade-prototype', 'imperium-fighter-prototype', 'imperium-repair-prototype',
    'imperium-relay-prototype',
)
REVIEW_PACKS = (*ACCEPTED_PACKS, 'imperium-fleet-prototypes')
FOCUS = {
    'hammer': ('imperial_tie_bomber_squadron', 'bomber'),
    'lancer': ('imperial_frigate', 'frigate'),
    'gladiator': ('imperial_cruiser', 'cruiser'),
    'executor': ('imperial_battleship', 'battleship'),
    'sovereign': ('imperial_supercapital', 'supercapital'),
    'colonial': ('imperial_colonizer', 'colonizer'),
    'transport': ('imperial_crew_transport', 'convoy'),
}


def prepare_subject(manager, focus):
    """Reuse stock if present; otherwise add only one actual factory specimen."""
    import math
    from game.core.vectors import Vec3
    ship_id, _ = FOCUS[focus]
    state = manager.state
    subject = next((e for e in state.entities.values()
                    if e.owner == 0 and e.alive and e.data_id == ship_id), None)
    if subject is not None:
        return subject, False
    anchor = next(e for e in state.entities.values() if e.owner == 0 and e.is_station)
    sd = manager.ds.resolve_ship(ship_id)
    # A clear lane near the home base, not a teleport or an edited combat hull.
    for distance in (2400., 3200., 4000.):
        for angle in range(0, 360, 30):
            yaw = math.radians(angle)
            pos = Vec3(anchor.pos.x + math.sin(yaw)*distance, anchor.pos.y,
                       anchor.pos.z + math.cos(yaw)*distance)
            if max(abs(pos.x), abs(pos.z)) > min(25000., state.map_info.bounds - 1000.):
                continue
            if any((pos.x-e.pos.x)**2 + (pos.z-e.pos.z)**2 < (sd.radius+e.radius+650.)**2
                   for e in state.entities.values() if e.alive):
                continue
            subject = manager.factory.spawn_ship(ship_id, 0, pos, yaw=yaw,
                name='REVIEW PREBUILT — ' + sd.display_name)
            manager.visibility.update()
            return subject, True
    raise ValueError('No safe nearby lane for review subject; refusing to overlap stock units')


def frame_subject(camera, data_store, subject):
    """Use real camera limits, hull sizes and safe-eye geometry; never override clamping."""
    import math
    from render.ship_sizes import ship_size
    size = ship_size(data_store, subject.data_id, 'imperial')
    camera.follow_id = None
    camera.target = [subject.pos.x, subject.pos.y, subject.pos.z]
    camera.yaw = (math.degrees(subject.yaw) + 35.) % 360.
    camera.pitch = 32.
    camera.distance = max(camera.zoom_limits[0], min(camera.zoom_limits[1], size.radius * 4.5))
    camera.clamp_target()
    camera._view = camera._proj = camera._safe_cache = None
    camera.refresh_scene()


def select_subject(input_controller, subject):
    """The native input controller's ordinary down/up picking path, not a forced ID set."""
    import pygame
    pos = input_controller.camera.world_to_screen(subject.pos.x, subject.pos.y, subject.pos.z)
    if pos is None:
        raise ValueError('Review subject is not projectable through the actual camera')
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        input_controller.handle_event(pygame.event.Event(kind, button=1, pos=pos, remote=True))
    if input_controller.selection != {subject.id}:
        raise ValueError('Native selection did not pick the review subject')


def profile_paths(user):
    user = Path(user)
    return {key: str(value) for key, value in {
        'USER_DIR': user, 'SAVES_DIR': user / 'saves',
        'SETTINGS_PATH': user / 'saves/settings.json',
        'CAMPAIGN_PATH': user / 'saves/campaign.json',
        'BALANCE_PATH': user / 'saves/balance.json',
    }.items()}


def validate_selection(report):
    """Production permits damaged-pack fallback; this review explicitly does not."""
    if report.get('enabled_order') != list(REVIEW_PACKS):
        raise ValueError('Required review packs missing or reordered')
    order = report.get('pack_order', [])
    if len(order) != len(REVIEW_PACKS) or any(not p.get('accepted') for p in order):
        raise ValueError('Required review pack rejected or missing: ' + json.dumps(order))
    if not report.get('coverage', {}).get('ok'):
        raise ValueError('Required authored catalogue coverage failed')
    bindings = {row['binding']: row for row in report.get('effective_bindings', [])}
    for _, role in FOCUS.values():
        row = bindings.get('imperial:' + role, {})
        if (row.get('pack_id') != 'prototype:imperium_fleet'
                or row.get('asset') != 'prototype:imperial/' + role):
            raise ValueError('Missing review replacement (core fallback forbidden): imperial:' + role)
    return report


def parse_args(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--focus', choices=tuple(FOCUS), default='sovereign')
    parser.add_argument('--frames', type=int, help='Exit after this many actual native presents')
    parser.add_argument('--capture', type=Path, help='PNG of the actual presented native frame; defaults to 90 frames')
    args = parser.parse_args(argv)
    if args.frames is not None and args.frames < 1:
        parser.error('--frames must be positive')
    if args.capture and args.capture.suffix.lower() != '.png':
        parser.error('--capture must name a PNG file')
    if args.capture and args.frames is None:
        args.frames = 90
    return args


@contextmanager
def isolated_profile(root, defaults):
    """Copy data-only packs; never symlink a writable profile back to the source."""
    with tempfile.TemporaryDirectory(prefix='imperium-fleet-review-') as directory:
        user = Path(directory)
        (user / 'saves').mkdir()
        (user / 'replays').mkdir()
        settings = deepcopy(defaults)
        settings.update(model_preview=True, renderer='cpp', visual_packs=list(REVIEW_PACKS),
                        fullscreen=False, tutorial_hints=False)
        for pack in REVIEW_PACKS:
            source = Path(root) / 'visual_packs' / pack
            if not (source / 'visual-pack.json').is_file():
                raise ValueError(f'Required review pack missing: {pack}')
            shutil.copytree(source, user / 'visual_packs' / pack)
        (user / 'saves/settings.json').write_text(json.dumps(settings, indent=2), encoding='utf-8')
        yield user


def build_review_catalogue(settings, target):
    """Export an explicit review catalogue, bypassing shipped/default snapshot reuse (CPU)."""
    from unittest.mock import patch
    from game.graphics_benchmark import make_fixture
    from render import asset_selection
    from render_bridge.protocol import encode, WORLD
    from tools.render import dump_snapshot
    fixture = make_fixture('four-player-combat-v1')
    with patch.object(dump_snapshot, '_default_selection', lambda: deepcopy(settings)):
        payload = dump_snapshot.build_catalogue(fixture)
    report = validate_selection(asset_selection.diagnostics())
    Path(target).write_bytes(encode(payload, kind=WORLD, tick=fixture.manager.state.tick, frame_index=0))
    return report


class ReviewHooks:
    """Small process-local seams around main's existing factory, input and presentation."""

    def __init__(self, args):
        self.args = args
        self.subject = None
        self.spawned = False
        self.namespace = None
        self.framed_controller = None
        self.presented = 0
        self.capture_done = False

    def start_game(self, original, *args, **kwargs):
        manager = original(*args, **kwargs)
        # Before main begins recording: the prebuilt unit is in the initial replay state.
        self.subject, self.spawned = prepare_subject(manager, self.args.focus)
        return manager

    def before_events(self, namespace):
        import pygame
        self.namespace = namespace
        if namespace['CPP'].get('failed'):
            raise RuntimeError('Review native renderer failed: ' + str(namespace['CPP']['failed']))
        controller = namespace.get('inputc')
        if namespace.get('mode') != 'game':
            if self.framed_controller is not None:
                raise RuntimeError('Review left the match before completion')
            return
        if controller is None or controller is self.framed_controller:
            return
        subject = namespace['state'].entities.get(getattr(self.subject, 'id', None))
        if subject is None or subject.data_id != FOCUS[self.args.focus][0]:
            raise ValueError('Review focus absent after session change')
        frame_subject(namespace['camera'], namespace['gm'].ds, subject)
        select_subject(controller, subject)
        namespace['replay_notice'] = ('IMPERIUM FLEET REVIEW — '
            + ('FACTORY PREBUILT' if self.spawned else 'STOCK SUBJECT')
            + ' — ' + self.args.focus + ' | normal commands enabled; isolated profile')
        pygame.display.set_caption('STAR ARMADA — ' + namespace['replay_notice'])
        self.framed_controller = controller

    def after_present(self):
        self.presented += 1
        if self.args.frames is not None and self.presented >= self.args.frames:
            if self.args.capture:
                capture_presented(self.args.capture)
                self.capture_done = True
            self.namespace['running'] = False


def capture_presented(path):
    """Read the original window's presented front buffer, not a hidden legacy scene."""
    import pygame
    from OpenGL.GL import glReadBuffer, glReadPixels, GL_FRONT, GL_BACK, GL_RGB, GL_UNSIGNED_BYTE
    path = Path(path).resolve()
    if path.exists():
        raise ValueError('Refusing to overwrite capture: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = pygame.display.get_surface().get_size()
    glReadBuffer(GL_FRONT)
    try:
        data = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
    finally:
        glReadBuffer(GL_BACK)
    image = pygame.image.frombuffer(data, (width, height), 'RGB')
    pygame.image.save(pygame.transform.flip(image, False, True), str(path))


def main(argv=None):
    import os
    import runpy
    import sys
    from unittest.mock import patch
    args = parse_args(argv)
    if getattr(sys, 'frozen', False) or getattr(sys, '_MEIPASS', None) is not None:
        raise ValueError('Source-run review only; frozen/installed release entry is forbidden')
    if args.capture:
        args.capture = args.capture.resolve()
        if args.capture.exists() or args.capture.with_suffix('.json').exists():
            raise ValueError('Refusing to overwrite review evidence')
        if args.capture.is_relative_to(ROOT / 'saves') or args.capture.is_relative_to(ROOT / 'visual_packs'):
            raise ValueError('Capture must not overwrite normal saves or packs')
    sys.path.insert(0, str(ROOT))
    import game.core  # establish the simulation import order before menus
    import pygame
    from render import menus, asset_selection
    from render_bridge.embedded import EmbeddedWindow
    from game.core.manager import GameManager
    hooks = ReviewHooks(args)
    old_cwd = Path.cwd()
    with isolated_profile(ROOT, menus.DEFAULT_SETTINGS) as user:
        settings = json.loads((user / 'saves/settings.json').read_text(encoding='utf-8'))
        snapshot = user / 'review-catalogue.snap'
        source_report = build_review_catalogue(settings, snapshot)
        with patch.multiple(menus, **profile_paths(user)):
            isolated_report = validate_selection(asset_selection.configure_from_settings(settings))
            source_revisions = [p['revision'] for p in source_report['pack_order']]
            if source_revisions != [p['revision'] for p in isolated_report['pack_order']]:
                raise ValueError('Pack files changed while copying isolated review profile')
            original_start = GameManager.start_skirmish
            original_events = pygame.event.get
            original_present = EmbeddedWindow.present

            def start(*a, **kw):
                return hooks.start_game(original_start, *a, **kw)

            def events(*a, **kw):
                ns = sys._getframe(1).f_globals
                if ns.get('__file__') == str(ROOT / 'main.py'):
                    validate_selection(asset_selection.diagnostics())
                    hooks.before_events(ns)
                return original_events(*a, **kw)

            def present(window):
                result = original_present(window)
                hooks.after_present()
                return result

            # Force this run's validated catalogue and original embedded owner. Never reuse
            # an environment-selected stock snapshot or launch a second renderer window.
            env = {'STAR_ARMADA_CPP_SNAPSHOT': str(snapshot), 'STAR_ARMADA_CPP_EXTERNAL': '0'}
            try:
                os.chdir(ROOT)
                print('IMPERIUM FLEET REVIEW: isolated factory-prebuilt scenario; NOT organic build/release', flush=True)
                with patch.dict(os.environ, env), patch.object(sys, 'argv', [str(ROOT / 'main.py'), '--skirmish']), \
                     patch.object(GameManager, 'start_skirmish', staticmethod(start)), \
                     patch.object(pygame.event, 'get', events), patch.object(EmbeddedWindow, 'present', present):
                    runpy.run_path(str(ROOT / 'main.py'), run_name='__main__')
            finally:
                os.chdir(old_cwd)
                # runpy exceptions bypass main's normal tail. Always release the native
                # owner before deleting its ring directory and isolated profile.
                if hooks.namespace is not None:
                    hooks.namespace['cpp_reset']()
                pygame.quit()
            if not hooks.presented or (args.frames is not None and hooks.presented < args.frames):
                raise RuntimeError(f'Review ended before requested native frames ({hooks.presented})')
            if args.capture and not hooks.capture_done:
                raise RuntimeError('Requested capture was not made')
            receipt = {'scenario': 'isolated-factory-prebuilt-review-not-organic-build',
                       'focus': args.focus, 'subject_id': hooks.subject.id,
                       'spawned': hooks.spawned, 'native_presented_frames': hooks.presented,
                       'enabled_packs': list(REVIEW_PACKS), 'pack_revisions': source_revisions,
                       'camera': {key: getattr(hooks.namespace['camera'], key)
                                  for key in ('target', 'distance', 'yaw', 'pitch')},
                       'actual_eye': hooks.namespace['camera'].eye_position()}
            if args.capture:
                args.capture.with_suffix('.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
            print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
