"""Capture the Python renderer's shield bubbles as the reference the native window has to match.

The same four bubbles the C++ fixture carries - full, half, nearly spent, and a station - are
placed in open space above the map and rendered by the real `_draw_shields` pass with every other
pass skipped, so the frame holds the shells and nothing else. The strengths, radii and positions
come from `tools/render/write_shield_fixtures.py`, so both sides describe the same four units.

Run: PYTHONPATH=. .venv/bin/python tools/render/capture_python_shields.py --out DIR
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

# The four bubbles, as the C++ fixture encodes them: (x, radius, fraction, station)
BUBBLES = [
    (-1400.0, 60.0, 1.00, False),
    (0.0, 60.0, 0.50, False),
    (1400.0, 60.0, 0.06, False),
    (2800.0, 220.0, 0.75, True),
]
# Both sides place the four bubbles at this height, clear of the fleet.
BASE_Y = 6000.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=800)
    parser.add_argument('--distance', type=float, default=4200.0)
    parser.add_argument('--pitch', type=float, default=30.0)
    parser.add_argument('--yaw', type=float, default=15.0)
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    pygame.init()
    pygame.display.set_mode((args.width, args.height), pygame.DOUBLEBUF | pygame.OPENGL)
    for _ in range(5):
        pygame.event.pump()
        pygame.time.wait(30)

    from game.core.manager import GameManager                  # noqa: E402
    from game.core.vectors import Vec3                         # noqa: E402
    from game.data.store import DataStore                      # noqa: E402
    from render.camera import Camera                           # noqa: E402
    from render.renderer import Renderer, QUADRANTS             # noqa: E402
    from PIL import Image                                      # noqa: E402

    DataStore.reset()
    state = GameManager.start_skirmish(DataStore().maps['skirmish01']).state

    # Three ships and one station, moved to the fixture's positions in open space. Everything else
    # stays on the map plane, far below the camera.
    ships = [e for e in state.entities.values() if e.is_ship and e.alive][:3]
    stations = [e for e in state.entities.values() if e.is_station and e.alive][:1]
    picked = ships + stations
    if len(picked) != 4:
        raise SystemExit('fixture lacks three ships and one station')
    base_y = BASE_Y
    for entity, (x, radius, fraction, _station) in zip(picked, BUBBLES):
        entity.pos = Vec3(x, base_y, 0.0)
        entity.radius = radius
        # max_shield_total() is max_shield_quad * 4, so one capacity sets both sides of the fraction.
        capacity = 400.0
        entity.max_shield_quad = capacity
        entity.shields = {q: capacity * fraction for q in QUADRANTS}

    camera = Camera(args.width, args.height)
    camera.target = [700.0, base_y, 0.0]
    camera.yaw = args.yaw
    camera.pitch = args.pitch
    camera.distance = args.distance

    # Only the shells: no hulls, no rings, no fog, no starfield. The shells themselves are the
    # renderer's own `_draw_shields` at these strengths.
    os.environ['STAR_ARMADA_SKIP'] = ('starfield,nebulas,star,jumppoints,planets,planet_shields,'
                                      'effects,projectiles,ships,squadrons,stations,markers,rings,'
                                      'sites,surface_slots')
    renderer = Renderer(state, camera)
    renderer.fog.draw = lambda *a, **k: None
    renderer.time = 3.0

    glViewport(0, 0, args.width, args.height)
    camera.apply(args.width, args.height)
    renderer.draw(1 / 30.0, set())
    glFinish()
    raw = glReadPixels(0, 0, args.width, args.height, GL_RGB, GL_UNSIGNED_BYTE)
    image = pygame.transform.flip(
        pygame.image.frombuffer(bytes(raw), (args.width, args.height), 'RGB'), False, True)
    png = os.path.join(args.out, 'python-shields.png')
    Image.frombytes('RGB', (args.width, args.height),
                    pygame.image.tobytes(image, 'RGB')).save(png)
    pixels = np.frombuffer(pygame.image.tobytes(image, 'RGB'), dtype=np.uint8)
    pixels = pixels.reshape(args.height, args.width, 3).astype(np.float32) / 255.0
    lit = pixels.max(axis=2) > 0.02
    report = {
        'screenshot': png,
        'synthetic': True,
        'bubbles': [{'x': x, 'radius': r, 'fraction': f, 'station': s} for x, r, f, s in BUBBLES],
        'camera': {'target': [700.0, base_y, 0.0], 'yaw': args.yaw, 'pitch': args.pitch,
                   'distance': camera.distance, 'width': args.width, 'height': args.height},
        'lit_pixels': int(lit.sum()),
        'mean_rgb': [round(float(pixels[..., i].mean()), 6) for i in range(3)],
        'lit_mean_rgb': [round(float(pixels[..., i][lit].mean()), 6) if lit.any() else 0.0
                         for i in range(3)],
        'note': 'Python renderer reference for the W05 shield slice; the four bubbles are synthetic '
                'and placed in open space with every other pass skipped',
    }
    with open(os.path.join(args.out, 'python-shields.json'), 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    print(json.dumps({'screenshot': png, 'lit_pixels': report['lit_pixels'],
                      'lit_mean_rgb': report['lit_mean_rgb']}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
