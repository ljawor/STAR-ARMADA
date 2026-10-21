"""Capture the Python renderer's fog overlay as the reference the native window has to match.

The fog is one quad on the ecliptic sampling one texel per visibility cell, so the honest check is
not "does fog appear" but "does the same mask land in the same place at the same framing". This
renders the same fixture and player the producer streams, with everything except the fog removed,
and records the mask's coverage: how much of the frame is charted, how much is unexplored, and where
the fog-free (visible) region ends along the screen's centre row.

Run: PYTHONPATH=. .venv/bin/python tools/render/capture_python_fog.py --out DIR
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import numpy as np                                          # noqa: E402
import pygame                                               # noqa: E402
from OpenGL.GL import (GL_RGB, GL_UNSIGNED_BYTE, glFinish,   # noqa: E402
                       glReadPixels, glViewport)

# The three states render/fog.py writes, as the picture shows them over a black background.
CHARTED = (12, 22, 38)
UNEXPLORED = (3, 6, 13)


def classify(pixels: np.ndarray) -> dict:
    """Count texels the mask darkened, separating the two opaque states by their colour."""
    dark = pixels.max(axis=2) < 0.20
    charted = dark & (pixels[..., 2] > 0.05) & (pixels[..., 0] < 0.10)
    unexplored = dark & (pixels[..., 2] <= 0.05)
    return {'dark_pixels': int(dark.sum()), 'charted_pixels': int(charted.sum()),
            'unexplored_pixels': int(unexplored.sum())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=800)
    parser.add_argument('--fixture', default='four-player-combat-v1')
    parser.add_argument('--player', type=int, default=0)
    parser.add_argument('--distance', type=float, default=11000.0)
    parser.add_argument('--pitch', type=float, default=62.0)
    parser.add_argument('--yaw', type=float, default=30.0)
    parser.add_argument('--pattern', action='store_true',
                        help='draw the fixed parity pattern instead of the simulation\'s own mask '
                             '(the frame is then synthetic and labelled as such)')
    parser.add_argument('--without-fog', action='store_true',
                        help='render the same camera with no overlay, so the comparison can measure '
                             'the mask against its own background')
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    pygame.init()
    pygame.display.set_mode((args.width, args.height), pygame.DOUBLEBUF | pygame.OPENGL)
    for _ in range(5):
        pygame.event.pump()
        pygame.time.wait(30)

    from game.data.store import DataStore                   # noqa: E402
    from game.graphics_benchmark import make_fixture         # noqa: E402
    from render.camera import Camera                        # noqa: E402
    from render.renderer import Renderer                    # noqa: E402
    from PIL import Image                                   # noqa: E402

    DataStore.reset()
    state = make_fixture(args.fixture).manager.state
    camera = Camera(args.width, args.height)
    camera.target = [0.0, 0.0, 0.0]
    camera.yaw = args.yaw
    camera.pitch = args.pitch
    camera.distance = args.distance
    # Only the fog: the mask is the subject, so ships, effects, planets and the starfield are left
    # out. Nothing about the mask itself is touched - it comes from render/fog.py's own classifier.
    os.environ['STAR_ARMADA_SKIP'] = ('starfield,nebulas,star,jumppoints,planets,planet_shields,'
                                      'effects')
    renderer = Renderer(state, camera)
    renderer.diff_render = True
    renderer.time = 3.0
    if args.pattern:
        import fog_pattern
        fixed = fog_pattern.surface()
        renderer.fog.surface = lambda *a, **k: fixed

    glViewport(0, 0, args.width, args.height)
    camera.apply(args.width, args.height)
    if not args.without_fog:
        renderer.fog.draw(state, args.player)
    glFinish()
    raw = glReadPixels(0, 0, args.width, args.height, GL_RGB, GL_UNSIGNED_BYTE)
    image = pygame.image.frombuffer(bytes(raw), (args.width, args.height), 'RGB')
    image = pygame.transform.flip(image, False, True)
    png = os.path.join(args.out, 'python-fog-off.png' if args.without_fog else 'python-fog.png')
    Image.frombytes('RGB', (args.width, args.height),
                    pygame.image.tobytes(image, 'RGB')).save(png)
    pixels = np.frombuffer(pygame.image.tobytes(image, 'RGB'), dtype=np.uint8)
    pixels = pixels.reshape(args.height, args.width, 3).astype(np.float32) / 255.0

    surface = renderer.fog.surface(state, args.player)
    mask_bytes = pygame.image.tobytes(surface, 'RGBA', False)
    alpha = np.frombuffer(mask_bytes, dtype=np.uint8).reshape(-1, 4)[:, 3]
    report = {
        'screenshot': png,
        'synthetic_mask': bool(args.pattern),
        'camera': {'target': [0.0, 0.0, 0.0], 'yaw': args.yaw, 'pitch': args.pitch,
                   'distance': camera.distance, 'width': args.width, 'height': args.height},
        'mask': {'cells': surface.get_width(),
                 'visible_texels': int((alpha == 0).sum()),
                 'charted_texels': int((alpha == 155).sum()),
                 'unexplored_texels': int((alpha == 255).sum()),
                 'total_texels': int(alpha.size)},
        'screen': classify(pixels),
        'note': 'Python reference for the W05 fog slice: the mask alone, no ships or effects, so '
                'the comparison is about the mask and its placement rather than the scene',
    }
    with open(os.path.join(args.out, 'python-fog-off.json' if args.without_fog
                           else 'python-fog.json'), 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    print(json.dumps({'screenshot': png, 'mask': report['mask'], 'screen': report['screen'],
                      'synthetic_mask': bool(args.pattern)},
                     sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
