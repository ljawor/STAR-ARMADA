"""Capture the Python renderer's colony shield dome as the reference for the native window.

One planet from the skirmish map, moved to `dome_scene.PLANET` and given a colony plus a surface
shield generator big enough to raise a field. Every pass except `planet_shields` is skipped, so the
frame holds the dome and nothing else. Two frames:

* `python-dome-full.png`  - a full field, the renderer's single additive shell;
* `python-dome-pulse.png` - the frame after the pool drops, when the renderer re-adds the shell
  until the flash decays.

Both the position and the radius come from `tools/render/dome_scene.py`, which the native fixture
also reads, so the two sides describe the same dome.

Run: PYTHONPATH=. .venv/bin/python tools/render/capture_python_dome.py --out DIR
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "render"))

import dome_scene                                          # noqa: E402

import numpy as np                                         # noqa: E402
import pygame                                              # noqa: E402
from OpenGL.GL import (GL_BLEND, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,   # noqa: E402
                       GL_DEPTH_TEST, GL_LIGHTING, GL_ONE, GL_RGB, GL_SRC_ALPHA,
                       GL_TEXTURE_2D, GL_UNSIGNED_BYTE, glBlendFunc, glClear,
                       glClearColor, glDisable, glEnable, glFinish, glReadPixels,
                       glViewport)

CAPACITY = 400.0


def grab(renderer, camera, planet, generator, radius, strength, dt, width, height, path) -> dict:
    """One frame of the renderer's own dome pass and nothing else.

    `_draw_planet_shields` gates each field on `state.can_see` for the generator, which belongs to
    the detection model rather than to the dome; calling the dome itself keeps the reference about
    the shell's geometry and brightness. The GL state around it is the pass's own.
    """
    glViewport(0, 0, width, height)
    camera.apply(width, height)
    glClearColor(0.0, 0.0, 0.0, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE)
    renderer._planet_shield_dome(planet, generator, radius, strength, dt)
    glFinish()
    raw = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
    image = pygame.transform.flip(
        pygame.image.frombuffer(bytes(raw), (width, height), 'RGB'), False, True)
    from PIL import Image
    Image.frombytes('RGB', (width, height), pygame.image.tobytes(image, 'RGB')).save(path)
    pixels = np.frombuffer(pygame.image.tobytes(image, 'RGB'), dtype=np.uint8)
    pixels = pixels.reshape(height, width, 3).astype(np.float32) / 255.0
    lit = pixels.max(axis=2) > 0.02
    return {
        'screenshot': path,
        'lit_pixels': int(lit.sum()),
        'lit_mean_rgb': [round(float(pixels[..., i][lit].mean()), 6) if lit.any() else 0.0
                         for i in range(3)],
        'peak': [round(float(pixels[..., i].max()), 6) for i in range(3)],
    }


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
    from game.core.vectors import Vec3                         # noqa: E402
    from game.data.store import DataStore                      # noqa: E402
    from render.camera import Camera                           # noqa: E402
    from render.renderer import Renderer                       # noqa: E402

    DataStore.reset()
    state = GameManager.start_skirmish(DataStore().maps['skirmish01']).state

    planet = next(e for e in state.entities.values() if e.is_planet)
    planet.pos = Vec3(*dome_scene.PLANET)
    planet.radius = dome_scene.RADIUS
    planet.colonized_by = planet.owner

    # The generator is a real entity - the camera walks every one of them for its attachment pass,
    # and a stub would have to reimplement half of Entity. Take an escort, park it on the planet and
    # relabel it as surface hardware; the dome pass only asks what Entity already answers.
    generator = next(e for e in state.entities.values() if e.is_ship and e.alive)
    generator.data_id = 'planet_shield_generator'
    generator.planet_id = planet.id
    generator.planet_building_slot = 0
    generator.owner = planet.colonized_by
    generator.pos = Vec3(*dome_scene.PLANET)
    if hasattr(generator, 'vel'):
        generator.vel = Vec3(0.0, 0.0, 0.0)
    generator.max_shield_quad = CAPACITY / 4.0
    generator.shields = {q: CAPACITY / 4.0 for q in ('front', 'rear', 'left', 'right')}

    camera = Camera(args.width, args.height)
    camera.target = list(dome_scene.CAMERA['target'])
    camera.yaw = dome_scene.CAMERA['yaw']
    camera.pitch = dome_scene.CAMERA['pitch']
    camera.distance = dome_scene.CAMERA['distance']

    # Everything but the dome: no planet sphere, no starfield, no fleet.
    os.environ['STAR_ARMADA_SKIP'] = ('starfield,nebulas,star,jumppoints,planets,planet_shields,'
                                      'effects,projectiles,ships,squadrons,stations,markers,rings,'
                                      'sites,surface_slots')
    renderer = Renderer(state, camera)
    renderer.fog.draw = lambda *a, **k: None
    renderer.time = 3.0

    dome = dict(planet=planet, generator=generator, radius=dome_scene.DOME_RADIUS,
                dt=1.0 / 30.0, width=args.width, height=args.height)
    full = grab(renderer, camera, strength=dome_scene.STRENGTH,
                path=os.path.join(args.out, 'python-dome-full.png'), **dome)
    # The hit: the pool drops, so the pass pulses on the very next frame.
    for quadrant in generator.shields:
        generator.shields[quadrant] = CAPACITY * dome_scene.HIT_STRENGTH / 4.0
    pulse = grab(renderer, camera, strength=dome_scene.HIT_STRENGTH,
                 path=os.path.join(args.out, 'python-dome-pulse.png'), **dome)

    report = {
        'synthetic': True,
        'planet': list(dome_scene.PLANET),
        'planet_radius': dome_scene.RADIUS,
        'dome_radius': dome_scene.DOME_RADIUS,
        'camera': dict(dome_scene.CAMERA, width=args.width, height=args.height),
        'full': full,
        'pulse': pulse,
        'note': 'Python reference for the W05 colony-dome slice: one planet, a synthetic generator, '
                'every pass but planet_shields skipped',
    }
    with open(os.path.join(args.out, 'python-dome.json'), 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    print(json.dumps({'full': full['lit_pixels'], 'pulse': pulse['lit_pixels'],
                      'peak': pulse['peak']}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
