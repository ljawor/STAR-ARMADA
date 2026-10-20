#!/usr/bin/env python3
"""Small real-driver before/after capture for the single Vigil visual prototype."""
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
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('capture_slice', ROOT / 'artifacts/alliance_blender_trio/evidence/capture_slice.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.isolate(ROOT, out)
    helper.PLACEMENTS = [
        ('capital', 'ship', 'imperial_corvette', 0, [-4200, 0, 2200], 0.),
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
              'views': VIEWS, 'variants': {}, 'changed_pixels': {}}
    frames = {}
    cameras = {name: Camera(W, H) for name in VIEWS}
    try:
        for label, packs in [('before', []), ('after', ['vigil-prototype'])]:
            info = asset_selection.configure({'model_preview': True, 'visual_packs': packs},
                                             asset_root=ROOT, pack_root=ROOT / 'visual_packs')
            if packs:
                assert info['pack_order'][0]['accepted'], info
            gm, ids, _ = helper.build_scene()
            st = gm.state
            st.players[0].faction = 'imperial'
            st.players[0].color = (0.85, 0.23, 0.12)
            assert st.can_see(0, ids['capital'])
            initial = state_hash(st)
            size = ship_size(gm.ds, 'imperial_corvette', 'imperial')
            variant = report['variants'][label] = {'state_sha256': initial,
                'size': {'length': size.length, 'scale': size.scale, 'shape': size.shape},
                'pack_order': info['pack_order'], 'captures': {}}
            for name, cam in cameras.items():
                helper.configure(cam, VIEWS[name])
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
        for name in VIEWS:
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
