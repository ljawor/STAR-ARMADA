"""Capture the Python renderer's damage contacts as the reference the native window must match.

The four contacts of `tools/render/hit_scene.py` are drawn by the real `render.hit_effects.draw_hit`
with every other pass skipped, so the frame holds the contacts and nothing else - no hulls to
contaminate a measurement, and no starfield to brighten the background.

Run: PYTHONPATH=. .venv/bin/python tools/render/capture_python_hits.py --out DIR
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

from tools.render import hit_scene                     # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=800)
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    pygame.init()
    pygame.display.set_mode((args.width, args.height), pygame.DOUBLEBUF | pygame.OPENGL)
    for _ in range(5):
        pygame.event.pump()
        pygame.time.wait(30)

    from game.core.manager import GameManager                  # noqa: E402
    from game.data.store import DataStore                      # noqa: E402
    from PIL import Image                                      # noqa: E402
    from render.camera import Camera                           # noqa: E402
    from render.hit_effects import draw_hit                    # noqa: E402
    from render.renderer import Renderer                       # noqa: E402

    DataStore.reset()
    state = GameManager.start_skirmish(DataStore().maps['skirmish01']).state

    camera = Camera(args.width, args.height)
    camera.target = list(hit_scene.CAMERA['target'])
    camera.yaw = hit_scene.CAMERA['yaw']
    camera.pitch = hit_scene.CAMERA['pitch']
    camera.distance = hit_scene.CAMERA['distance']

    # Nothing but the background: no ships, rings, fog, starfield or effects pass. The contacts are
    # drawn below by the renderer's own draw_hit, one call each, exactly as the effects pass does.
    os.environ['STAR_ARMADA_SKIP'] = ('starfield,nebulas,star,jumppoints,planets,planet_shields,'
                                      'effects,projectiles,ships,squadrons,stations,markers,rings,'
                                      'sites,surface_slots')
    renderer = Renderer(state, camera)
    renderer.fog.draw = lambda *a, **k: None
    renderer.time = 3.0

    glViewport(0, 0, args.width, args.height)
    camera.apply(args.width, args.height)
    renderer.draw(1 / 30.0, set())
    drawn = 0
    for effect in hit_scene.effects():
        draw_hit(renderer, effect)
        drawn += 1
    glFinish()

    raw = glReadPixels(0, 0, args.width, args.height, GL_RGB, GL_UNSIGNED_BYTE)
    image = pygame.transform.flip(
        pygame.image.frombuffer(bytes(raw), (args.width, args.height), 'RGB'), False, True)
    png = os.path.join(args.out, 'python-hits.png')
    Image.frombytes('RGB', (args.width, args.height),
                    pygame.image.tobytes(image, 'RGB')).save(png)
    pixels = np.frombuffer(pygame.image.tobytes(image, 'RGB'), dtype=np.uint8)
    pixels = pixels.reshape(args.height, args.width, 3).astype(np.float32) / 255.0
    lit = pixels.max(axis=2) > 0.02
    report = {
        'screenshot': png,
        'synthetic': True,
        'contacts': hit_scene.CONTACTS,
        'camera': {'target': list(hit_scene.CAMERA['target']), 'yaw': camera.yaw,
                   'pitch': camera.pitch, 'distance': camera.distance,
                   'width': args.width, 'height': args.height},
        'drawn': drawn,
        'lit_pixels': int(lit.sum()),
        'lit_mean_rgb': [round(float(pixels[..., i][lit].mean()), 6) if lit.any() else 0.0
                         for i in range(3)],
        'note': 'Python renderer reference for the W05 contact slice; the four contacts are '
                'synthetic and placed in open space with every other pass skipped',
    }
    with open(os.path.join(args.out, 'python-hits.json'), 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    print(json.dumps({'screenshot': png, 'lit_pixels': report['lit_pixels'],
                      'lit_mean_rgb': report['lit_mean_rgb'], 'drawn': drawn}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
