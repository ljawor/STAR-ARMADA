"""Real-context deterministic graphics acceptance and benchmark (no HUD).

PYTHONPATH=.:tests .venv/bin/python tools/diag_modern_fleet.py --label before --out DIR
Repeat with --label after --compare DIR/before_metrics.json after changes.
Captures glReadPixels BEFORE flip and vertically corrects readback. Never simulates.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time

import numpy as np
import pygame
from OpenGL import GL
from game.data.store import DataStore
from game.core.manager import GameManager
from game.core.entity import Entity
from game.core.vectors import Vec3
from render.camera import Camera
from render.renderer import Renderer

W, H = 1280, 800


def ship(ds, idx, did, pos, owner=0):
    sd = ds.ships[did]
    e = Entity(id=1000 + idx, kind="ship", owner=owner, data_id=did,
               pos=Vec3(*pos), radius=sd.radius)
    e.is_ship, e.is_station, e.is_squadron = True, False, False
    e.yaw = 2.45
    return e


def checksum(st):
    return hashlib.sha256(json.dumps(st.to_dict(precise=True), sort_keys=True).encode()).hexdigest()


def capture():
    GL.glFinish()
    raw = GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
    return np.flipud(np.frombuffer(raw, np.uint8).reshape(H, W, 3)).copy()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--label', default='after')
    ap.add_argument('--compare', type=Path)
    ap.add_argument('--require-modern', action='store_true')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    pygame.init()
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
    pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
    pygame.event.pump()
    GL.glEnable(GL.GL_DEPTH_TEST)
    GL.glEnable(GL.GL_MULTISAMPLE)
    GL.glClearColor(.008, .012, .025, 1)
    caps = {name: GL.glGetString(enum).decode() for name, enum in
            [('vendor', GL.GL_VENDOR), ('renderer', GL.GL_RENDERER),
             ('version', GL.GL_VERSION), ('glsl', GL.GL_SHADING_LANGUAGE_VERSION)]}
    print('CAPABILITIES', caps)
    ds = DataStore.get()
    gm = GameManager.start_skirmish(ds.maps['skirmish01'])
    st = gm.state
    st.entities.clear()
    cam = Camera(W, H)
    r = Renderer(st, cam)
    r.diff_render = True
    r.time = 3.0
    r.skip = {'star', 'jumppoints', 'nebulas', 'rings', 'sites', 'shields'}
    metrics = {'capabilities': caps, 'scenes': {}, 'bench_ms': {}}
    frames = {}
    for scene in ('hull', 'fleet', 'planet'):
        st.entities.clear()
        cam.target = [0, 0, 0]
        cam.yaw, cam.pitch = 0, 30
        cam.distance = 2100 if scene == 'hull' else 5200
        if scene == 'hull':
            e = ship(ds, 0, 'imperial_battleship', (0, 0, 0))
            st.entities[e.id] = e
            r.skip.add('starfield')
        elif scene == 'fleet':
            r.skip.discard('starfield')
            for i, (did, pos, owner) in enumerate([
                ('imperial_battleship', (-650, 0, 0), 0),
                ('imperial_cruiser', (400, 80, -250), 0),
                ('imperial_cruiser', (-600, -50, 1150), 0),
                ('imperial_corvette', (350, 0, 850), 0),
                ('imperial_battleship', (1150, 100, -1500), 1),
                ('imperial_cruiser', (-100, 50, -1500), 1)]):
                e = ship(ds, i, did, pos, owner)
                e.vel = Vec3(90, 0, -110)
                st.entities[e.id] = e
            p = Entity(id=2000, kind='planet', owner=-1, data_id='temperate',
                       pos=Vec3(-1800, -450, -2700), radius=950)
            p.is_planet = True
            st.entities[p.id] = p
        else:
            cam.distance = 3100
            r.skip.discard('starfield')
            p = Entity(id=2000, kind='planet', owner=-1, data_id='temperate',
                       pos=Vec3(0, 0, 0), radius=900)
            p.is_planet = True
            st.entities[p.id] = p
        initial = checksum(st)
        for _ in range(3):
            r.draw(0, set())
        a = capture()
        r.draw(0, set())
        assert np.array_equal(a, capture()), 'frozen frame is not stable'
        assert checksum(st) == initial, 'renderer mutated simulation'
        assert GL.glGetError() == GL.GL_NO_ERROR
        assert int(GL.glGetIntegerv(GL.GL_CURRENT_PROGRAM)) == 0, 'world shader leaked into HUD/effects'
        if os.environ.get('STAR_ARMADA_FIXED_MATERIALS') == '1':
            assert not r.materials.available, 'forced fixed-material fallback ignored'
        path = args.out / f'{args.label}_{scene}.png'
        pygame.image.save(pygame.image.frombuffer(a.tobytes(), (W, H), 'RGB'), path)
        frames[scene] = a
        metrics['scenes'][scene] = {
            'lit_pixels': int((a.max(2) > 45).sum()),
            'unique_colors': len(np.unique(a.reshape(-1, 3), axis=0)),
            'checksum': initial, 'image': str(path)}
        assert metrics['scenes'][scene]['lit_pixels'] > 2000, scene
        print('SCENE', scene, metrics['scenes'][scene])
    # Warmed render-only benchmark, explicit GL synchronization, no flip/vsync.
    r.skip = {'starfield', 'star', 'planets', 'jumppoints', 'nebulas', 'rings', 'sites', 'shields'}
    cam.distance = 14000
    for n in (20, 60, 150):
        st.entities.clear()
        for i in range(n):
            e = ship(ds, i, 'imperial_cruiser', ((i % 15 - 7) * 650, 0, (i // 15 - 5) * 700), i % 2)
            st.entities[e.id] = e
        for _ in range(5):
            r.draw(0, set())
        samples = []
        for _ in range(20):
            GL.glFinish()
            start = time.perf_counter()
            r.draw(0, set())
            GL.glFinish()
            samples.append((time.perf_counter() - start) * 1000)
        metrics['bench_ms'][str(n)] = {'median': float(np.median(samples)), 'p95': float(np.percentile(samples, 95))}
        print('BENCH', n, metrics['bench_ms'][str(n)])
    if args.require_modern:
        assert getattr(r, 'materials', None) and r.materials.available, 'GLSL material path unavailable'
        assert metrics['scenes']['hull']['unique_colors'] > 3000, 'hull lacks per-fragment detail'
    if args.compare:
        before = json.loads(args.compare.read_text())
        metrics['comparison'] = {}
        for scene, a in frames.items():
            old = pygame.surfarray.array3d(pygame.image.load(before['scenes'][scene]['image'])).transpose(1, 0, 2)
            delta = np.abs(a.astype(float) - old)
            changed = int((delta.max(2) > 8).sum())
            metrics['comparison'][scene] = {'changed_pixels': changed, 'mean_delta': float(delta.mean())}
            assert before['scenes'][scene]['checksum'] == metrics['scenes'][scene]['checksum'], 'comparison scene changed'
            assert changed > 5000, f'{scene}: upgrade not visibly substantial'
        print('COMPARISON', metrics['comparison'])
    path = args.out / f'{args.label}_metrics.json'
    path.write_text(json.dumps(metrics, indent=2))
    pygame.quit()
    print('MODERN_FLEET_DIAG_OK', path)


if __name__ == '__main__':
    main()
