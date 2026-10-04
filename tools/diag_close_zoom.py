"""Real SDL/GL base-camera pixels; git-show baseline stays entirely in memory.
Run: PYTHONPATH=. .venv/bin/python tools/diag_close_zoom.py --out DIR
Metrics exclude HUD; *_hud.png captures verify final compositing/minimap input.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pygame
from OpenGL import GL, GLU
from game.data.store import DataStore
from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.systems.unit_factory import UnitFactory
from render.camera import Camera
from render.renderer import Renderer
from render.input import InputController
from render.hud import HUD


def committed(path):
    source = subprocess.check_output(['git', 'show', 'HEAD:' + path], cwd=ROOT, text=True)
    module = types.ModuleType('baseline_' + Path(path).stem)
    module.__file__ = str(ROOT / path)
    sys.modules[module.__name__] = module
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


def capture(path, width, height):
    data = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
    image = pygame.image.frombuffer(data, (width, height), 'RGB')
    pygame.image.save(pygame.transform.flip(image, False, True), str(path))
    return np.frombuffer(data, np.uint8).reshape(height, width, 3)


def deliver(control, *events):
    pygame.event.clear()
    for event in events:
        pygame.event.post(event)
    for event in pygame.event.get():
        control.handle_event(event)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    pygame.display.init()
    pygame.font.init()
    W, H = 1280, 800
    pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
    GL.glViewport(0, 0, W, H)
    pygame.event.pump()
    ds = DataStore.get()
    st = GameManager.start_skirmish(ds.maps['skirmish01']).state
    st.entities.clear()
    factory = UnitFactory(st)
    base = factory.spawn_station('command_station', 0, Vec3(0, 0, 0))
    rear_ship = factory.spawn_ship('imperial_corvette', 0, Vec3(1000, 0, 1000))
    rear_ship.alive = False
    before = st.to_dict(precise=True)
    baseline_camera = committed('render/camera.py').Camera
    baseline_renderer = committed('render/renderer.py').Renderer
    baseline_input = committed('render/input.py').InputController
    baseline_sizes = committed('render/ship_sizes.py')
    def baseline_ship_size(renderer, entity):
        return baseline_sizes.readable_size(renderer.ds, entity.data_id,
            renderer._px_per_world((entity.pos.x, entity.pos.y, entity.pos.z), camera_depth=True))
    baseline_renderer._ship_size = baseline_ship_size
    results = []
    # Factory geometry only: no radius manipulation or hand-built station.
    cases = [('close', 300., 55.), ('very_close', 180., 55.),
             ('wheel_very_close', 300., 55.), ('direct_very_close', 25., 55.),
             ('minimap_low_pitch', 180., 8.), ('minimap_near1', 180., 8.),
             ('rear_ship_close', 300., 55.), ('rear_ship_very_close', 180., 55.)]
    for label, camera_cls, renderer_cls, input_cls in (
            ('baseline', baseline_camera, baseline_renderer, baseline_input),
            ('fixed', Camera, Renderer, InputController)):
        cam = camera_cls(W, H)
        hud = HUD(W, H, st)
        hud.render(set(), None, 0, False, '', 0., 60.)
        control = input_cls(st, cam, hud, types.SimpleNamespace(flash=lambda *_: None))
        renderer = renderer_cls(st, cam)
        renderer.diff_render = True
        renderer.skip = {'starfield', 'nebulas', 'star', 'jumppoints', 'planets',
                         'sites', 'shields', 'projectiles', 'effects', 'squadrons'}
        for case, distance, pitch in cases:
            rear_ship.alive = case.startswith('rear_ship')
            cam.distance, cam.pitch, cam.yaw, cam.near = distance, pitch, 45., 20.
            cam.target = [0., 0., 0.]
            if case.startswith('wheel'):
                pygame.mouse.set_pos((W//2, H//2))
                deliver(control, pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=12))
                assert cam.distance == 180., 'real wheel did not reach requested min zoom'
            if case.startswith('minimap'):
                if case.endswith('near1'):
                    cam.near = 1.
                click = (hud.minimap_rect.centerx - 1, hud.minimap_rect.centery - 1)
                deliver(control, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=click),
                        pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=click))
                assert cam.target[0] < 0. and cam.target[2] < 0., 'minimap click was not dispatched'
            # Direct camera writes must be protected by production draw/apply.
            renderer.draw(0., set())
            arr = capture(args.out / f'{label}_{case}.png', W, H)
            occupied = arr.max(axis=2) > 30
            expected = cam.world_to_screen(*cam.target)
            projected = GLU.gluProject(*cam.target)
            error = math.dist(expected, (projected[0], H - projected[1]))
            metric = dict(version=label, case=case, requested_distance=cam.distance,
                          target=list(cam.target), eye=cam.eye_position(),
                          effective_distance=math.dist(cam.target, cam.eye_position()),
                          coverage=float(occupied.mean()),
                          border_coverage=float(np.concatenate((occupied[0], occupied[-1], occupied[:,0], occupied[:,-1])).mean()),
                          projection_error_px=error, gl_error=int(GL.glGetError()))
            results.append(metric)
            print(json.dumps(metric))
            hud.render(set(), None, 0, False, '', 0., 60.)
            hud.draw_gl()
            capture(args.out / f'{label}_{case}_hud.png', W, H)
        renderer.close()
        hud.close()
    rear_ship.alive = False
    assert st.to_dict(precise=True) == before, 'camera/render mutated simulation'
    # Exercise the untouched real starting base/fleet, a crowded factory base,
    # and an isolated close corvette with the identical before/after cameras.
    from game.systems.visibility import VisibilitySystem
    for scene in ('full_start', 'crowded', 'safe_corvette', 'empty'):
        graph = GameManager.start_skirmish(DataStore.get().maps['skirmish01']).state
        subject = next(e for e in graph.entities.values() if e.owner == 0 and e.data_id == 'command_station')
        if scene != 'full_start':
            graph.entities.clear()
            f = UnitFactory(graph)
            if scene == 'crowded':
                subject = f.spawn_station('command_station', 0, Vec3())
                f.spawn_station('sensor_station', 0, Vec3(110, 160, 110))
                f.spawn_station('shipyard', 0, Vec3(320, 0, 300))
                f.spawn_planet(dict(id='near', type='temperate', pos=[500, 350, 500], radius=160))
            else:
                subject = f.spawn_ship('imperial_corvette', 0, Vec3())
                if scene == 'empty':
                    graph.entities.clear()
        VisibilitySystem(graph).update()
        frozen = graph.to_dict(precise=True)
        safe_pixels = {}
        for label, camera_cls, renderer_cls, input_cls in (
                ('baseline', baseline_camera, baseline_renderer, baseline_input),
                ('fixed', Camera, Renderer, InputController)):
            cam = camera_cls(W, H)
            hud = HUD(W, H, graph)
            hud.render(set(), None, 0, False, '', 0., 60.)
            control = input_cls(graph, cam, hud, types.SimpleNamespace(flash=lambda *_: None))
            renderer = renderer_cls(graph, cam)
            renderer.diff_render = True
            renderer.skip = {'starfield', 'nebulas', 'star', 'jumppoints', 'sites', 'shields', 'projectiles', 'effects', 'squadrons'}
            for suffix, distance, pitch in (('close', 300., 55.), ('very_close', 180., 55.), ('minimap', 180., 8.)):
                cam.target = [subject.pos.x, 0., subject.pos.z] if scene not in ('empty', 'safe_corvette') else [0., 0., 0.]
                cam.distance, cam.pitch, cam.yaw = distance, pitch, 45.
                if suffix == 'minimap':
                    r = hud.minimap_rect
                    half = graph.map_info.bounds / 2
                    click = (round(r.centerx + subject.pos.x/half*(r.width/2-4)) - 1,
                             round(r.centery + subject.pos.z/half*(r.height/2-4)) - 1)
                    deliver(control, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=click))
                renderer.draw(0., set())
                case = scene + '_' + suffix
                arr = capture(args.out / f'{label}_{case}.png', W, H)
                occupied = arr.max(axis=2) > 30
                metric = dict(version=label, case=case, requested_distance=cam.distance,
                    target=list(cam.target), eye=cam.eye_position(),
                    effective_distance=math.dist(cam.target, cam.eye_position()),
                    coverage=float(occupied.mean()),
                    projection_error_px=math.dist(cam.world_to_screen(*cam.target),
                        (GLU.gluProject(*cam.target)[0], H - GLU.gluProject(*cam.target)[1])),
                    gl_error=int(GL.glGetError()))
                results.append(metric)
                print(json.dumps(metric))
                if scene in ('safe_corvette', 'empty') and suffix != 'minimap':
                    safe_pixels[label, suffix] = arr.copy()
                if label == 'fixed':
                    from render.camera_geometry import box_interval
                    eye = cam.eye_position()
                    length = math.dist(eye, cam.target)
                    direction = tuple((eye[i]-cam.target[i])/length for i in range(3))
                    clearance = cam.near * math.sqrt(1+math.tan(math.radians(cam.fov/2))**2*(1+(W/H)**2))+2.
                    for obstacle in cam._camera_boxes:
                        interval = box_interval(cam.target, direction, obstacle, clearance)
                        assert interval is None or not interval[0] <= length <= interval[1], 'effective eye remains in hardware'
                hud.render(set(), None, 0, False, '', 0., 60.)
                hud.draw_gl()
                capture(args.out / f'{label}_{case}_hud.png', W, H)
            renderer.close()
            hud.close()
        if safe_pixels:
            for suffix in ('close', 'very_close'):
                changed = float(np.any(safe_pixels['baseline', suffix] != safe_pixels['fixed', suffix], axis=2).mean())
                assert changed < .005, (scene, suffix, 'safe scene changed', changed)
        assert graph.to_dict(precise=True) == frozen, 'diagnostic view changed precise sim state'
    (args.out / 'metrics.json').write_text(json.dumps(results, indent=2))
    lookup = {(m['version'], m['case']): m for m in results}
    red, green = lookup['baseline', 'minimap_low_pitch'], lookup['fixed', 'minimap_low_pitch']
    # Detector calibrated on the minimal hardware-only repro, not HUD pixels.
    assert red['coverage'] > .65 and red['border_coverage'] > .65, 'baseline must show interior hardware planes'
    assert green['coverage'] < .50 and green['border_coverage'] < .30, 'camera still inside/against hardware'
    assert lookup['baseline', 'minimap_near1']['coverage'] > .65, 'lower near plane unexpectedly cured the interior camera'
    assert lookup['fixed', 'very_close']['border_coverage'] < lookup['baseline', 'very_close']['border_coverage']
    assert lookup['fixed', 'direct_very_close']['effective_distance'] > 25.
    # Float32 GL matrices at the real -11000u base introduce ~.002px rounding.
    assert all(m['projection_error_px'] < .01 for m in results if m['version'] == 'fixed')
    assert lookup['baseline', 'full_start_close']['coverage'] > .90
    assert lookup['fixed', 'full_start_close']['coverage'] < .60
    assert lookup['baseline', 'rear_ship_close']['coverage'] > .90, 'behind-eye ship inflation repro is vacuous'
    assert lookup['fixed', 'rear_ship_close']['coverage'] < .60, 'behind-eye ship still fills the base view'
    assert all(m['gl_error'] == 0 for m in results)
    pygame.quit()
    print('DIAG_CLOSE_ZOOM_OK')


if __name__ == '__main__':
    main()
