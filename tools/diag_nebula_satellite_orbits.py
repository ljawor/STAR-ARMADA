"""#75 real Cocoa SDL/OpenGL: replay-derived blocked satellite and complete orbit.
PYTHONPATH=.:tests python tools/diag_nebula_satellite_orbits.py --out DIR
"""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
import numpy as np
import pygame
from OpenGL import GL
from PIL import Image
from test_nebula_satellite_orbits import NebulaSatelliteOrbitTests
from render.camera import Camera
from render.renderer import Renderer
from game.systems.satellite_orbits import orbit_geometry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    assert os.environ.get('SDL_VIDEODRIVER') != 'dummy'
    pygame.display.init()
    width, height = 1280, 800
    pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
    GL.glViewport(0, 0, width, height)
    assert pygame.display.get_driver() != 'dummy'
    gm, planet, satellite = NebulaSatelliteOrbitTests().fixture()
    st = gm.state
    camera = Camera(width, height)
    camera.target = planet.pos.to_dict(True)
    camera.yaw, camera.pitch, camera.distance = 30, 65, 6000
    renderer = Renderer(st, camera)
    renderer.diff_render = True; renderer.time = 3
    report = dict(sdl_driver=pygame.display.get_driver(),
        gl_renderer=GL.glGetString(GL.GL_RENDERER).decode(), stages=[],
        ring=orbit_geometry(st, planet, satellite.radius, satellite.satellite_slot),
        fixture='exact replay tick25401 position/phase/role; unrelated combat omitted')
    def snapshot():
        return json.loads(json.dumps(st.to_dict(precise=True)))
    def pixels():
        GL.glFinish()
        return np.flipud(np.frombuffer(GL.glReadPixels(0, 0, width, height,
            GL.GL_RGB, GL.GL_UNSIGNED_BYTE), np.uint8).reshape(height, width, 3)).copy()
    original_draw = renderer._draw_station
    def capture(label):
        before = snapshot()
        # A polar orbit can pass behind the opaque planet. Seek an unobstructed
        # real camera bearing rather than weakening the hardware-pixel gate.
        for yaw in (30, 120, 210, 300):
            for pitch in (65, 20):
                camera.yaw, camera.pitch = yaw, pitch
                renderer.draw(0, {satellite.id}); frame = pixels()
                assert GL.glGetError() == GL.GL_NO_ERROR
                renderer._draw_station = lambda e: None if e.id == satellite.id else original_draw(e)
                renderer.draw(0, {satellite.id}); control = pixels()
                renderer._draw_station = original_draw
                changed = int(np.any(frame != control, axis=2).sum())
                if changed > 0:
                    break
            if changed > 0:
                break
        assert changed > 0, 'satellite hardware invisible at all camera bearings'
        assert before == snapshot(), 'render changed simulation'
        path = args.out / f'{label}.png'; Image.fromarray(frame).save(path)
        report['stages'].append(dict(stage=label, image=str(path), position=satellite.pos.to_dict(True),
                                    phase=satellite.satellite_orbit_phase, hardware_pixels=changed))
        pygame.display.flip(); pygame.event.pump()
    capture('blocked_legacy_plane')
    travel = 0.; last = satellite.satellite_orbit_phase
    previous = satellite.pos.copy(); min_clearance = 1e9; max_step = 0.
    for tick in range(4800):
        gm.satellite_orbits.update(1 / 30)
        step = (satellite.satellite_orbit_phase - last) % (2 * np.pi)
        if step < .1: travel += step
        last = satellite.satellite_orbit_phase
        max_step = max(max_step, satellite.pos.dist(previous)); previous = satellite.pos.copy()
        for body in st.entities.values():
            if body.alive and body.is_planet and body is not planet and body.data_id != 'asteroid_field':
                min_clearance = min(min_clearance, satellite.pos.dist(body.pos) - (satellite.radius + body.radius) * 1.6)
        if tick + 1 in (900, 2400, 4800): capture(f'accepted_tick_{tick + 1}')
    assert travel > 2 * np.pi and min_clearance >= -1e-8 and max_step < 5
    report.update(angular_travel=travel, minimum_keepout_margin=min_clearance, maximum_tick_displacement=max_step)
    (args.out / 'report.json').write_text(json.dumps(report, indent=2))
    pygame.quit()
    print('NEBULA_ORBIT_GL_OK', json.dumps(report))


if __name__ == '__main__':
    main()
