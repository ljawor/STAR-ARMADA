"""Measurable deterministic orbit probe with optional actual-renderer GL trails.

PYTHONPATH=. .venv/bin/python tools/diag_combat_standoff.py --out /path/to/output
Use --no-render only where a real window server is unavailable.
Damage is intentionally not applied: measure sustained navigation and actual
weapon launches against a persistent anchor, without a kill ending the probe.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.data.store import DataStore


def probe(moving=False, ticks=5400):
    gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
    st = gm.state
    st.entities.clear()
    if moving:
        target = gm.factory.spawn_ship('imperial_battleship', 1, Vec3())
        target.order_type = 'move'
        target.order_target_pos = Vec3(7000, 0, 0)
        target.yaw = math.pi/2
    else:
        target = gm.factory.spawn_station('command_station', 1, Vec3())
    ships = []
    kinds = ('imperial_corvette', 'imperial_corvette', 'imperial_corvette',
             'imperial_corvette' if moving else 'confed_supercapital')
    for i, kind in enumerate(kinds):
        angle = i * math.pi/2
        radius = 1872 if kind == 'confed_supercapital' else 1200
        ship = gm.factory.spawn_ship(kind, 0, Vec3(math.sin(angle)*radius, 0,
                                                 math.cos(angle)*radius))
        ship.order_type = 'attack'
        ship.order_target_id = ship.current_target = target.id
        ship.sensor_range = 12000
        ships.append(ship)
    trails = {e.id: [] for e in ships}
    metrics = {e.id: {'unit': e.data_id, 'min_distance': float('inf'),
                     'tail_max_distance': 0, 'angular_travel': 0,
                     'launches': 0, 'front_launches': 0,
                     'hard_radius': gm.movement._combat_ranges(e, target)[0],
                     'preferred_radius': gm.movement._combat_ranges(e, target)[1]}
               for e in ships}
    previous = {}
    for tick in range(ticks):
        st.tick += 1
        st.time += 1/30
        gm.movement.update(1/30)
        st.grid.rebuild(st.entities)
        gm.separation.update(1/30)
        for e in ships:
            offset = e.pos-target.pos
            distance = offset.length()
            angle = math.atan2(offset.x, offset.z)
            row = metrics[e.id]
            row['min_distance'] = min(row['min_distance'], distance)
            if tick >= ticks*2//3:
                row['tail_max_distance'] = max(row['tail_max_distance'], distance)
            if e.id in previous:
                row['angular_travel'] += abs((angle-previous[e.id]+math.pi)%(2*math.pi)-math.pi)
            previous[e.id] = angle
            assert distance >= row['hard_radius']-1e-6, row
            facing = Vec3(math.sin(e.yaw), 0, math.cos(e.yaw))
            assert abs(e.vel.x*facing.z-e.vel.z*facing.x) < 1e-7, 'lateral crabbing'
            if tick % 10 == 0:
                trails[e.id].append(e.pos.to_dict())
            e.energy = e.max_energy
            gm.weapons._ship_weapons(e, 1/30)
            row['launches'] += len(st.projectiles)+len(st.damage_queue)
            row['front_launches'] += sum(d['weapon'].hardpoint == 'front' for d in st.damage_queue)
            row['front_launches'] += sum(gm.ds.resolve_weapon(p.weapon_id).hardpoint == 'front'
                                         for p in st.projectiles.values())
            st.projectiles.clear()
            st.damage_queue.clear()
        st.effects.clear()
    for row in metrics.values():
        assert row['angular_travel'] > .5, row
        assert row['launches'] > 10, row
        if row['unit'] == 'confed_supercapital':
            assert row['front_launches'] > 5, row
    if not moving:
        assert target.pos == Vec3(), 'station anchor moved'
    return gm, target, trails, list(metrics.values())


def render_probe(gm, target, trails, path):
    import numpy as np
    import pygame
    from OpenGL import GL
    from render.camera import Camera
    from render.renderer import Renderer

    width, height = 1280, 900
    pygame.init()
    try:
        pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
        pygame.event.pump()
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glClearColor(.008, .012, .025, 1)
        camera = Camera(width, height)
        camera.target = [target.pos.x, 0, target.pos.z]
        camera.yaw, camera.pitch, camera.distance = 0, 70, 6500
        renderer = Renderer(gm.state, camera)
        renderer.diff_render = True
        renderer.skip = {'star', 'jumppoints', 'nebulas', 'sites', 'shields'}
        renderer.time = 3.0
        gm.visibility.update()
        for _ in range(3):
            renderer.draw(0, set(trails))
        GL.glPushAttrib(GL.GL_ENABLE_BIT | GL.GL_CURRENT_BIT | GL.GL_LINE_BIT)
        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glLineWidth(1.5)
        colors = ((.25, .8, 1), (.3, 1, .65), (1, .8, .25), (.9, .4, 1))
        for color, points in zip(colors, trails.values()):
            GL.glColor3f(*color)
            GL.glBegin(GL.GL_LINE_STRIP)
            for point in points:
                GL.glVertex3f(*point)
            GL.glEnd()
        for radius, color in ((target.radius, (1, .2, .15)),
                               (target.radius+34+40, (1, .5, .2)),
                               (702, (.3, .55, .9))):
            GL.glColor3f(*color)
            GL.glBegin(GL.GL_LINE_LOOP)
            for i in range(180):
                angle = i*math.tau/180
                GL.glVertex3f(target.pos.x+math.sin(angle)*radius, 0,
                              target.pos.z+math.cos(angle)*radius)
            GL.glEnd()
        GL.glPopAttrib()
        GL.glFinish()
        raw = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
        pixels = np.flipud(np.frombuffer(raw, np.uint8).reshape(height, width, 3)).copy()
        assert GL.glGetError() == GL.GL_NO_ERROR
        assert int((pixels.max(2) > 45).sum()) > 1000, 'empty capture'
        pygame.image.save(pygame.image.frombuffer(pixels.tobytes(), (width, height), 'RGB'), str(path))
        return {'image': str(path), 'gl_renderer': GL.glGetString(GL.GL_RENDERER).decode()}
    finally:
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--no-render', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {}
    for moving in (False, True):
        name = 'moving_ship' if moving else 'station'
        gm, target, trails, metrics = probe(moving)
        report[name] = {'ticks': 5400, 'units': metrics}
        if not args.no_render:
            report[name]['render'] = render_probe(gm, target, trails, args.out/f'{name}_trails.png')
    (args.out/'metrics.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print('COMBAT_STANDOFF_DIAG_OK', args.out)


if __name__ == '__main__':
    main()
