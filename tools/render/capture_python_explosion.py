"""Capture the Python renderer's detonation as the reference the native window has to match.

A blast is ~40 irregular shells whose shape, colour and timing all derive from `age` and `seed`, so
the only honest comparison is the same age and seed in both renderers. This spawns one synthetic
detonation in open space (documented as synthetic - nothing in the fixture is being killed), freezes
the clock, and writes the frame plus the mean RGB of the whole picture.

Run: PYTHONPATH=. .venv/bin/python tools/render/capture_python_explosion.py --out DIR
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import numpy as np                                     # noqa: E402
import pygame                                          # noqa: E402
from OpenGL.GL import (GL_RGB, GL_UNSIGNED_BYTE, glFinish,   # noqa: E402
                       glReadPixels, glViewport)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=800)
    parser.add_argument('--age', type=float, default=0.35, help='seconds into a 1.5 s blast')
    parser.add_argument('--size', type=float, default=120.0)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--distance', type=float, default=0.0,
                        help='camera distance; 0 = 5.5x the blast size')
    parser.add_argument('--pitch', type=float, default=0.0)
    parser.add_argument('--yaw', type=float, default=0.0)
    parser.add_argument('--fixture', default='skirmish01')
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    pygame.init()
    pygame.display.set_mode((args.width, args.height), pygame.DOUBLEBUF | pygame.OPENGL)
    for _ in range(5):
        pygame.event.pump()
        pygame.time.wait(30)

    from game.core.manager import GameManager                  # noqa: E402
    from game.core.vectors import Vec3                             # noqa: E402
    from game.data.store import DataStore                      # noqa: E402
    from render.camera import Camera                           # noqa: E402
    from render.renderer import Renderer                       # noqa: E402
    from PIL import Image                                      # noqa: E402

    DataStore.reset()
    if args.fixture == 'skirmish01':
        state = GameManager.start_skirmish(DataStore().maps['skirmish01']).state
    else:
        from game.graphics_benchmark import make_fixture
        state = make_fixture(args.fixture).manager.state

    # Open space, far above the map, so the frame holds the blast and nothing else.
    origin = Vec3(0.0, 3000.0, 0.0)
    state.effects.clear()
    state.spawn_effect('explosion', origin, size=args.size, seed=args.seed)
    state.effects[-1]['t'] = args.age
    camera = Camera(args.width, args.height)
    camera.target = [origin.x, origin.y, origin.z]
    camera.yaw = args.yaw
    camera.pitch = args.pitch
    camera.distance = args.distance or args.size * 5.5
    # Isolate the blast: no fog test (it would hide anything off the sensor coverage), no fog
    # overlay, no starfield/star/planets. Nothing about the blast itself is changed - it is the
    # renderer's own `_draw_explosion` at this age and seed.
    import render.renderer as renderer_module
    renderer_module.effect_visible = lambda *a, **k: True
    os.environ['STAR_ARMADA_SKIP'] = 'starfield,nebulas,star,jumppoints,planets,planet_shields'
    renderer = Renderer(state, camera)
    renderer.fog.draw = lambda *a, **k: None
    renderer.diff_render = True
    renderer.time = 3.0

    glViewport(0, 0, args.width, args.height)
    camera.apply(args.width, args.height)
    renderer.draw(1 / 30.0, set())
    glFinish()
    raw = glReadPixels(0, 0, args.width, args.height, GL_RGB, GL_UNSIGNED_BYTE)
    image = pygame.image.frombuffer(bytes(raw), (args.width, args.height), 'RGB')
    image = pygame.transform.flip(image, False, True)
    png = os.path.join(args.out, 'python-explosion.png')
    Image.frombytes('RGB', (args.width, args.height),
                    pygame.image.tobytes(image, 'RGB')).save(png)
    pixels = np.frombuffer(pygame.image.tobytes(image, 'RGB'), dtype=np.uint8)
    pixels = pixels.reshape(args.height, args.width, 3).astype(np.float32) / 255.0
    lit = pixels.max(axis=2) > 0.02
    report = {
        'screenshot': png,
        'synthetic': True,
        'blast': {'position': [origin.x, origin.y, origin.z], 'size': args.size,
                  'age': args.age, 'seed': args.seed, 'life': 1.5},
        'camera': {'target': [origin.x, origin.y, origin.z], 'yaw': args.yaw, 'pitch': args.pitch,
                   'distance': camera.distance, 'width': args.width, 'height': args.height},
        'mean_rgb': [round(float(pixels[..., i].mean()), 6) for i in range(3)],
        'lit_pixels': int(lit.sum()),
        'lit_mean_rgb': [round(float(pixels[..., i][lit].mean()), 6) if lit.any() else 0.0
                         for i in range(3)],
        'note': 'Python renderer reference for the W05 explosion slice; the blob is synthetic and '
                'placed in open space so nothing else is in frame',
    }
    with open(os.path.join(args.out, 'python-explosion.json'), 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    print(json.dumps({'screenshot': png, 'mean_rgb': report['mean_rgb'],
                      'lit_pixels': report['lit_pixels']}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
