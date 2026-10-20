#!/usr/bin/env python3
"""Small real-driver before/after capture for a named playtest asset."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
W, H = 1280, 800
VIEWS = {
    'close': dict(target=[-4200, 5, 2200], distance=120., yaw=48., pitch=32.),
    'rear': dict(target=[-4200, 5, 2200], distance=120., yaw=155., pitch=23.),
    'tactical': dict(target=[-4200, 0, 2200], distance=500., yaw=48., pitch=55.),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--subject', choices=['vigil', 'command', 'shipyard', 'mining'], default='vigil')
    args = parser.parse_args()
    station = args.subject != 'vigil'
    station_kind = {'command': 'command_station', 'shipyard': 'shipyard', 'mining': 'mining_station'}.get(args.subject)
    framing = {'command': (45, 640., 1600.), 'shipyard': (20, 440., 1200.), 'mining': (-5, 310., 900.)}
    if station:
        assert station_kind is not None
        target_y, close, tactical = framing[args.subject]
        views = {
            'close': dict(target=[-4200, target_y, 2200], distance=close, yaw=48., pitch=32.),
            'rear': dict(target=[-4200, target_y, 2200], distance=close, yaw=155., pitch=25.),
            'tactical': dict(target=[-4200, 0, 2200], distance=tactical, yaw=48., pitch=55.),
        }
    else:
        views = VIEWS
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('capture_slice', ROOT / 'artifacts/alliance_blender_trio/evidence/capture_slice.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.isolate(ROOT, out)
    helper.PLACEMENTS = [
        ('capital', 'station' if station else 'ship', station_kind if station else 'imperial_corvette', 0, [-4200, 0, 2200], 0.),
        ('escort', 'ship', 'imperial_frigate', 0, [-4200, 0, 2900], 0.),
        ('enemy_a', 'ship', 'imperial_corvette', 1, [-3500, 0, 2200], 0.),
        ('enemy_b', 'ship', 'imperial_corvette', 1, [-3500, 0, 2900], 0.),
    ]
    import numpy as np
    import pygame
    from OpenGL import GL
    import game.core.manager
    from game.benchmark import state_hash
    from render import asset_selection
    from render.camera import Camera
    from render.renderer import Renderer
    from render.ship_sizes import ship_size

    pygame.init()
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
    pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
    for _ in range(5):
        pygame.event.pump()
    samples = int(GL.glGetIntegerv(GL.GL_SAMPLES))
    assert samples == 4, samples
    report = {'quality': {'samples': samples, 'viewport': [W, H],
                         'gl': GL.glGetString(GL.GL_RENDERER).decode()},
              'subject': args.subject, 'views': views, 'variants': {}, 'changed_pixels': {}}
    frames = {}
    cameras = {name: Camera(W, H) for name in views}
    try:
        if args.subject in ('shipyard', 'mining'):
            accepted = ['vigil-prototype', 'imperium-command-prototype']
            candidate = {'shipyard': 'imperium-shipyard-prototype', 'mining': 'imperium-mining-prototype'}[args.subject]
            variants = [('before', accepted), ('after', accepted + [candidate])]
        elif station:
            variants = [('before', ['vigil-prototype']), ('after', ['vigil-prototype', 'imperium-command-prototype'])]
        else:
            variants = [('before', []), ('after', ['vigil-prototype'])]
        for label, packs in variants:
            info = asset_selection.configure({'model_preview': True, 'visual_packs': packs},
                                             asset_root=ROOT, pack_root=ROOT / 'visual_packs')
            if packs:
                assert all(row['accepted'] for row in info['pack_order']), info
            gm, ids, _ = helper.build_scene()
            st = gm.state
            st.players[0].faction = 'imperial'
            st.players[0].color = (0.85, 0.23, 0.12)
            assert st.can_see(0, ids['capital'])
            initial = state_hash(st)
            if station:
                from render.camera_geometry import station_bounds
                lo, hi = station_bounds(station_kind, 'imperial')
                scale = st.entities[ids['capital']].radius / 50.
                size_info = {'length': (hi[2] - lo[2]) * scale, 'scale': scale, 'shape': 'imperial:' + station_kind}
            else:
                size = ship_size(gm.ds, 'imperial_corvette', 'imperial')
                size_info = {'length': size.length, 'scale': size.scale, 'shape': size.shape}
            variant = report['variants'][label] = {'state_sha256': initial,
                'size': size_info,
                'pack_order': info['pack_order'], 'captures': {}}
            for name, cam in cameras.items():
                helper.configure(cam, views[name])
                r = Renderer(st, cam)
                try:
                    assert r.materials.available, r.materials.error
                    r.local_player = 0
                    r.diff_render = True
                    r.time = 3.
                    eyes = []
                    for i in range(4):
                        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
                        r.draw(0., set())
                        GL.glFinish()
                        pygame.event.pump()
                    image = np.frombuffer(GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE),
                                          dtype=np.uint8).reshape(H, W, 3)[::-1].copy()
                    eyes = list(cam.eye_position())
                    assert state_hash(st) == initial, 'Rendering changed simulation'
                    filename = f'{label}-{name}.png'
                    pygame.image.save(pygame.image.frombuffer(image.tobytes(), (W, H), 'RGB'), str(out / filename))
                    frames[label, name] = image
                    variant['captures'][name] = {'file': filename, 'eye': eyes,
                        'sha256': hashlib.sha256((out / filename).read_bytes()).hexdigest()}
                    assert GL.glGetError() == GL.GL_NO_ERROR
                finally:
                    r.close()
        assert report['variants']['before']['state_sha256'] == report['variants']['after']['state_sha256']
        assert abs(report['variants']['before']['size']['length'] - report['variants']['after']['size']['length']) < .15
        for name in views:
            assert report['variants']['before']['captures'][name]['eye'] == report['variants']['after']['captures'][name]['eye']
            changed = int(np.any(frames['before', name] != frames['after', name], axis=2).sum())
            assert changed > 0, f'No visible change: {name}'
            report['changed_pixels'][name] = changed
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print('VIGIL_CAPTURE_OK', json.dumps(report['changed_pixels']))
    finally:
        asset_selection.configure({'model_preview': False})
        pygame.quit()


if __name__ == '__main__':
    main()
