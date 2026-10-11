"""Real SDL/GL surface hardware proof from paid manager construction.

Controlled owned planet and funded players; not a natural campaign playthrough.
PYTHONPATH=. .venv/bin/python tools/diag_planet_buildings.py --out DIR
"""
import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pygame
from OpenGL import GL
from PIL import Image
from game.core.commands import PlayerCommand
from game.core.entity import Entity
from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.planet_buildings import BUILDING_TYPES
from render.camera import Camera
from render.renderer import Renderer
from render.planet_building_geometry import station_world_mesh


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    pygame.display.init()
    pygame.font.init()
    report = []
    try:
        for width, height in ((1280, 800), (1024, 768)):
            pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
            GL.glViewport(0, 0, width, height)
            pygame.event.pump()
            DataStore.reset()
            definition = json.loads(json.dumps(DataStore.get().maps['skirmish01']))
            for player in definition['players']:
                player['is_ai'] = False
            gm = GameManager.start_skirmish(definition)
            st = gm.state
            st.entities.clear()
            st.discovered_planets.clear()
            st.explored_cells.clear()
            gm.factory.spawn_station('command_station', 0, Vec3(-9000, 0, 0))
            gm.factory.spawn_station('command_station', 1, Vec3(9000, 0, 0))
            planet = Entity(st.next_entity_id, 'planet', -1, 'temperate',
                pos=Vec3(), radius=650, hull=1e9, max_hull=1e9,
                is_planet=True, colonized_by=0, name_override='Surface acceptance')
            st.next_entity_id += 1
            st.add_entity(planet)
            player = st.players[0]
            player.credits = player.materials = player.energy = player.crew = 100000
            for kind in BUILDING_TYPES:
                st.queue_command(PlayerCommand('build_planet_building', 0,
                    target_id=planet.id, station_kind=kind))
            for _ in range(3000):
                gm.step(1 / 30)
            hardware = sorted((e for e in st.entities.values()
                if e.planet_id == planet.id and e.planet_building_slot is not None),
                key=lambda e: e.planet_building_slot)
            assert {e.data_id for e in hardware} == set(BUILDING_TYPES)
            assert st.tick == 3000 and not st.game_over
            gm.visibility.update()
            camera = Camera(width, height)
            renderer = Renderer(st, camera)
            renderer.diff_render = True
            renderer.marker_mode = 'off'
            renderer.skip = {'star', 'jumppoints', 'nebulas', 'shields', 'markers'}

            def pixels():
                GL.glFinish()
                return np.flipud(np.frombuffer(GL.glReadPixels(0, 0, width,
                    height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE), np.uint8)
                    .reshape(height, width, 3)).copy()

            try:
                for building in hardware:
                    slot = building.planet_building_slot
                    camera.target = list(building.pos.to_tuple())
                    camera.yaw = (90, 0, -90, 180)[slot]
                    camera.pitch = 30
                    camera.distance = 1600
                    before = json.loads(json.dumps(st.to_dict(precise=True)))
                    renderer.draw(0, set())
                    with_hardware = pixels()
                    original = renderer._draw_station
                    renderer._draw_station = lambda e: None if e.id == building.id else original(e)
                    try:
                        renderer.draw(0, set())
                        without_hardware = pixels()
                    finally:
                        renderer._draw_station = original
                    assert GL.glGetError() == GL.GL_NO_ERROR
                    assert before == json.loads(json.dumps(st.to_dict(precise=True)))
                    mask = np.abs(with_hardware.astype(int) - without_hardware.astype(int)).max(2) > 8
                    count = int(mask.sum())
                    assert count > 40, (building.data_id, count, camera.eye_position())
                    points = [p for role in station_world_mesh(st, building).values()
                              for _, tri in role for p in tri]
                    assert min(math.dist(p, planet.pos.to_tuple()) for p in points) >= planet.radius
                    path = out / f'{width}_{building.data_id}.png'
                    Image.fromarray(with_hardware).save(path)
                    Image.fromarray(without_hardware).save(out / f'{width}_{building.data_id}_disabled.png')
                    report.append(dict(width=width, height=height,
                        kind=building.data_id, slot=slot, hardware_pixels=count,
                        screenshot=str(path), paid_manager_ticks=st.tick,
                        gl_renderer=GL.glGetString(GL.GL_RENDERER).decode()))
                    pygame.display.flip()
                    pygame.event.pump()
                camera.target = [0, 0, 0]
                camera.yaw, camera.pitch, camera.distance = 45, 55, 2800
                before = st.to_dict(precise=True)
                renderer.draw(0, {planet.id})
                slots_frame = pixels()
                renderer.skip.add('surface_slots')
                renderer.draw(0, {planet.id})
                no_slots = pixels()
                assert st.to_dict(precise=True) == before
                changed = int((np.abs(slots_frame.astype(int) - no_slots.astype(int)).max(2) > 8).sum())
                assert changed > 40, ('no surface pads', changed)
                Image.fromarray(slots_frame).save(out / f'{width}_surface_slots.png')
                report.append(dict(width=width, stage='surface_slots', difference_pixels=changed))
            finally:
                renderer.close()
        (out / 'metrics.json').write_text(json.dumps(report, indent=2))
        print(f'PLANET_BUILDINGS_DIAG_OK: {len(report)} verified hardware/slot captures; {out}')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
