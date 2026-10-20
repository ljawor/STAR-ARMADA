#!/usr/bin/env python3
"""Play the original Imperial visual prototypes with separate test saves.

No application bundle, stock mesh, normal settings, saves or replays are modified.
The mining-only review scenario adds one prebuilt mine; normal game rules are unchanged.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
PROFILE = Path.home() / 'Library/Application Support/STAR ARMADA/Vigil Prototype'


PACK_NAMES = ('vigil-prototype', 'imperium-command-prototype',
              'imperium-shipyard-prototype', 'imperium-mining-prototype',
              'imperium-talon-prototype', 'imperium-engineer-prototype')
FOCUS = {
    'vigil': ('imperial_corvette', 180., 48., 28.),
    'command': ('command_station', 720., 48., 32.),
    'shipyard': ('shipyard', 600., 48., 28.),
    'mining': ('mining_station', 540., 48., 24.),
    'talon': ('imperial_tie_squadron', 110., 48., 28.),
    'engineer': ('imperial_constructor', 180., 48., 28.),
}


def review_map(map_def, focus):
    """Make a disposable review variant; never mutate the stock map or catalogue."""
    result = deepcopy(map_def)
    if focus == 'mining':
        for player in result['players']:
            if player['slot'] == 0 and player['faction'] == 'imperial':
                start = player.setdefault('start_units', {})
                start['mining_station'] = max(1, start.get('mining_station', 0))
    return result


def prepare_profile(profile, *, core=False):
    profile = Path(profile)
    (profile / 'saves').mkdir(parents=True, exist_ok=True)
    for name in PACK_NAMES:
        shutil.copytree(ROOT / 'visual_packs' / name, profile / 'visual_packs' / name, dirs_exist_ok=True)
    path = profile / 'saves/settings.json'
    settings = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    settings.update(model_preview=True, model_preview_explicit=True,
                    visual_packs=[] if core else list(PACK_NAMES), fullscreen=False)
    path.write_text(json.dumps(settings, indent=2) + '\n', encoding='utf-8')
    return settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, default=PROFILE)
    parser.add_argument('--verify-out', type=Path, help='Capture a real gameplay frame and exit after 12 frames')
    parser.add_argument('--core', action='store_true', help='Play the same launch using original core models')
    parser.add_argument('--focus', choices=list(FOCUS), default='vigil',
                        help='Select/frame a prototype; mining review includes one prebuilt mine')
    args = parser.parse_args()
    subject_data_id, distance, yaw, pitch = FOCUS[args.focus]
    profile = args.profile.resolve()
    prepare_profile(profile, core=args.core)
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    import game.core
    if args.focus == 'mining':
        from game.core.manager import GameManager
        original_start = GameManager.start_skirmish

        def mining_review_start(map_def, *a, **kw):
            return original_start(review_map(map_def, args.focus), *a, **kw)

        GameManager.start_skirmish = staticmethod(mining_review_start)
    from render import menus
    for key, value in {
        'USER_DIR': profile, 'SAVES_DIR': profile / 'saves',
        'SETTINGS_PATH': profile / 'saves/settings.json',
        'CAMPAIGN_PATH': profile / 'saves/campaign.json',
        'BALANCE_PATH': profile / 'saves/balance.json',
    }.items():
        setattr(menus, key, str(value))

    import pygame
    import render.renderer as render_module
    import render.input as input_module
    original_renderer = render_module.Renderer
    original_input = input_module.InputController

    class FramedRenderer(original_renderer):
        def __init__(self, state, camera):
            super().__init__(state, camera)
            subject = next((e for e in state.entities.values()
                            if e.owner == 0 and e.data_id == subject_data_id), None)
            if subject:
                camera.target = list(subject.pos.to_tuple())
                camera.distance, camera.yaw, camera.pitch = distance, yaw, pitch
                camera.follow_id = subject.id
            if args.verify_out:
                assert self.materials and self.materials.available, 'The production hull shader did not load'

    class SelectedInput(original_input):
        def __init__(self, state, camera, hud, app):
            super().__init__(state, camera, hud, app)
            subject = next((e for e in state.entities.values()
                            if e.owner == 0 and e.data_id == subject_data_id), None)
            if subject:
                self.selection = {subject.id}

    render_module.Renderer = FramedRenderer
    input_module.InputController = SelectedInput
    if args.verify_out:
        from OpenGL import GL
        from render.asset_selection import diagnostics
        out = args.verify_out.resolve()
        out.mkdir(parents=True, exist_ok=True)
        original_flip = pygame.display.flip
        count = 0

        def verification_flip():
            nonlocal count
            count += 1
            if count == 12:
                GL.glFinish()
                w, h = pygame.display.get_surface().get_size()
                raw = GL.glReadPixels(0, 0, w, h, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
                surface = pygame.image.frombuffer(raw, (w, h), 'RGB')
                pygame.image.save(pygame.transform.flip(surface, False, True), str(out / 'gameplay.png'))
                info = diagnostics()
                if not args.core:
                    assert {row['pack_id'] for row in info['pack_order'] if row['accepted']} == {'prototype:vigil', 'prototype:imperium_command', 'prototype:imperium_shipyard', 'prototype:imperium_mining', 'prototype:imperium_talon', 'prototype:imperium_engineer'}, info
                info['focus'] = args.focus
                info['scenario'] = 'stock skirmish + one prebuilt mining station for review' if args.focus == 'mining' else 'stock skirmish'
                info.update(frames=count, gl_samples=int(GL.glGetIntegerv(GL.GL_SAMPLES)),
                            gl_renderer=GL.glGetString(GL.GL_RENDERER).decode(), profile=str(profile))
                (out / 'gameplay.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
                print('VIGIL_GAMEPLAY_OK', out / 'gameplay.png', flush=True)
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            original_flip()

        pygame.display.flip = verification_flip
    sys.argv = [str(ROOT / 'main.py'), '--skirmish']
    runpy.run_path(str(ROOT / 'main.py'), run_name='__main__')


if __name__ == '__main__':
    main()
