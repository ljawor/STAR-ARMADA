"""Capture the Python renderer's planet as the reference the native window has to match.

W05's measure is "play a skirmish in the new window and not be able to tell it apart", so the
comparison is a picture, not an assertion about a shader. This frames one planet with the live
renderer, freezes the clock (`diff_render`) so the axial spin is reproducible, and writes a PNG.
Feed the same planet and the same yaw/pitch/distance to the viewer with `--focus` and compare.

Run: PYTHONPATH=. .venv/bin/python tools/render/capture_python_planet.py --out DIR
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
    parser.add_argument('--distance', type=float, default=2200.0)
    parser.add_argument('--pitch', type=float, default=8.0)
    parser.add_argument('--yaw', type=float, default=90.0)
    parser.add_argument('--time', type=float, default=3.0)
    parser.add_argument('--fixture', default='skirmish01',
                        help='skirmish01, or a graphics benchmark fixture such as '
                             'four-player-combat-v1 so both renderers draw the same world')
    parser.add_argument('--planet-id', type=int, help='which planet to frame')
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    pygame.init()
    pygame.display.set_mode((args.width, args.height), pygame.DOUBLEBUF | pygame.OPENGL)
    for _ in range(5):
        pygame.event.pump()
        pygame.time.wait(30)

    from game.core.manager import GameManager                  # noqa: E402
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
    planets = [e for e in state.entities.values() if e.is_planet and e.data_id != 'asteroid_field']
    planet = (next(e for e in planets if e.id == args.planet_id) if args.planet_id
              else next(e for e in planets if e.data_id == 'temperate'))
    star = (state.map_info.star or {}).get('pos', [0, -3000, 0])
    camera = Camera(args.width, args.height)
    camera.target = [planet.pos.x, planet.pos.y, planet.pos.z]
    camera.yaw, camera.pitch, camera.distance = args.yaw, args.pitch, args.distance
    renderer = Renderer(state, camera)
    renderer.diff_render = True      # frozen clock: the same picture twice
    renderer.time = args.time

    glViewport(0, 0, args.width, args.height)
    camera.apply(args.width, args.height)
    renderer.draw(1 / 30.0, set())
    glFinish()
    raw = glReadPixels(0, 0, args.width, args.height, GL_RGB, GL_UNSIGNED_BYTE)
    image = pygame.image.frombuffer(bytes(raw), (args.width, args.height), 'RGB')
    image = pygame.transform.flip(image, False, True)
    png = os.path.join(args.out, 'python-planet.png')
    Image.frombytes('RGB', (args.width, args.height),
                    pygame.image.tobytes(image, 'RGB')).save(png)
    pixels = np.frombuffer(pygame.image.tobytes(image, 'RGB'), dtype=np.uint8)
    pixels = pixels.reshape(args.height, args.width, 3).astype(np.float32) / 255.0
    report = {
        'screenshot': png,
        'planet': {'id': planet.id, 'data_id': planet.data_id,
                   'position': [planet.pos.x, planet.pos.y, planet.pos.z],
                   'radius': planet.radius},
        'camera': {'target': [planet.pos.x, planet.pos.y, planet.pos.z],
                   'yaw': args.yaw, 'pitch': args.pitch, 'distance': args.distance,
                   'width': args.width, 'height': args.height},
        'renderer_time': args.time,
        'star': [star[0], max(star[1], 2000.0), star[2]],
        'planets': [{'id': e.id, 'data_id': e.data_id, 'name': e.name_override,
                      'position': [e.pos.x, e.pos.y, e.pos.z], 'radius': e.radius}
                     for e in sorted(planets, key=lambda e: e.id)],
        'mean_rgb': [round(float(pixels[..., i].mean()), 6) for i in range(3)],
        'note': 'Python renderer reference for the W05 planet slice; the clock is frozen so the '
                'axial spin is reproducible',
    }
    with open(os.path.join(args.out, 'python-planet.json'), 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    print(json.dumps({'screenshot': png, 'planet': report['planet'],
                      'mean_rgb': report['mean_rgb']}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
