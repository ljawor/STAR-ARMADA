"""Capture the Python renderer's own surface hardware as the reference for the native window.

One colony building on one planet from the combat fixture, drawn by the renderer's station pass and
by nothing else, so the frame holds a building and not a fleet. Two frames come out: the building,
and the same camera with the building taken away. The pixels that differ are the building - the
planet, the sky gradient and the starfield cancel, which is the only way to compare a 100-unit
object that stands in front of a 600-unit one.

The scene, the camera and the building come from `tools/render/hardware_scene.py`, which the live
producer also uses, so both sides describe the same building at the same place.

Run: PYTHONPATH=. .venv/bin/python tools/render/capture_python_hardware.py --out DIR
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "render"))

import hardware_scene                                    # noqa: E402

import numpy as np                                       # noqa: E402
import pygame                                            # noqa: E402
from OpenGL.GL import (GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_RGB,   # noqa: E402
                       GL_UNSIGNED_BYTE, glClear, glClearColor, glFinish,
                       glReadPixels, glViewport)


def narrow(renderer, kept: set):
    """The renderer's own frame cache, cut down to the entities this reference is about."""
    cache = renderer._ensure_frame_cache(set())
    cache['visible'] = [(e, entry) for e, entry in cache['visible'] if e.id in kept]
    return cache


def grab(renderer, camera, width, height, path, kept_ids) -> dict:
    """One frame of the renderer with every pass but stations skipped.

    `draw()` rather than `_draw_station` directly: the station pass depends on the GL state and
    material program the draw loop sets up around it, and calling the inner method on a bare
    context renders the building black.
    """
    glViewport(0, 0, width, height)
    camera.apply(width, height)
    glClearColor(0.0, 0.0, 0.0, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    renderer._setup_lighting()
    renderer._draw_ships(set(), narrow(renderer, kept_ids))
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

    from game.core.manager import GameManager              # noqa: E402
    from game.data.store import DataStore                  # noqa: E402
    from game.graphics_benchmark import make_fixture       # noqa: E402
    from render.camera import Camera                       # noqa: E402
    from render.renderer import Renderer                   # noqa: E402

    DataStore.reset()
    _ = GameManager                                        # the fixture owns the manager
    fixture = make_fixture('four-player-combat-v1')
    state = fixture.manager.state
    planet, hull = hardware_scene.plant(state, kind=hardware_scene.KIND)

    scene = hardware_scene.camera(planet)
    camera = Camera(args.width, args.height)
    camera.target = list(scene['target'])
    camera.yaw = scene['yaw']
    camera.pitch = scene['pitch']
    camera.distance = scene['distance']

    # Every world pass is skipped, but `_draw_ships` is not: it owns both the hulls and the
    # stations, so skipping it skips the building too. The frame is narrowed instead - the visible
    # list keeps the building and drops the fleet - and the pass keeps the lighting, texture and
    # material state it needs around it.
    os.environ['STAR_ARMADA_SKIP'] = ('starfield,nebulas,star,jumppoints,planets,planet_shields,'
                                      'effects,projectiles,squadrons,shields,markers,rings,'
                                      'contact,fog_quads,sites,surface_slots,minimap')
    renderer = Renderer(state, camera)
    renderer.fog.draw = lambda *a, **k: None
    renderer.marker_mode = 'off'          # markers would add their own pixels to the diff
    renderer.time = 3.0

    present = grab(renderer, camera, args.width, args.height,
                   os.path.join(args.out, 'python-hardware.png'), {hull.id})
    # Take the building away, keep the camera: the difference is the building.
    hull.is_station = False
    hull.planet_building_slot = None
    hull.planet_id = None
    absent = grab(renderer, camera, args.width, args.height,
                  os.path.join(args.out, 'python-hardware-absent.png'), set())

    report = {
        'synthetic': True,
        'binding': f'{state.players[hull.owner].faction}:{hardware_scene.KIND}',
        'kind': hardware_scene.KIND,
        'slot': hardware_scene.SLOT,
        'planet': {'id': planet.id, 'data_id': planet.data_id, 'radius': planet.radius,
                   'pos': [round(v, 3) for v in planet.pos.to_tuple()]},
        'building': {'entity_id': hull.id, 'radius': hull.radius,
                     'origin': [round(v, 3) for v in hardware_scene.target(planet)]},
        'camera': dict(scene, width=args.width, height=args.height),
        'present': present,
        'absent': absent,
        'note': 'Python reference for the W05 surface-hardware slice: one planted building, station '
                'pass only, and the same camera with the building removed so the difference is the '
                'building',
    }
    with open(os.path.join(args.out, 'python-hardware.json'), 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    print(json.dumps({'present': present['lit_pixels'], 'absent': absent['lit_pixels'],
                      'peak': present['peak']}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
