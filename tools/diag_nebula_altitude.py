"""Real SDL/GL issue #76 proof from a precise, matching-source replay snapshot.

--snapshot is the unmodified state captured immediately before tick 109825's
recorded attack on fighter 28. No camera telemetry exists in the replay: the
fixed diagnostic view is inferred, not a recorded user view.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import types

BASE = 'f913802'
IDS = (535, 536, 537, 545)


def baseline_movement(state):
    source = subprocess.check_output(['git', 'show', f'{BASE}:game/systems/movement.py'])
    module = types.ModuleType('game.systems._nebula_baseline')
    module.__package__ = 'game.systems'
    exec(compile(source, 'immutable-baseline-movement.py', 'exec'), module.__dict__)
    return module.MovementSystem(state)


def precise(gm):
    return json.loads(json.dumps(gm.state.to_dict(precise=True)))


def restore(snapshot, baseline=False):
    from game.net.replay_validation import reconstruct
    gm = reconstruct(copy.deepcopy(snapshot))
    if baseline:
        gm.movement = baseline_movement(gm.state)
    return gm


def verify_coplanar_control():
    from game.core.manager import GameManager
    from game.core.vectors import Vec3
    from game.core.commands import AttackCommand
    from game.data.store import DataStore
    map_def = copy.deepcopy(DataStore.get().maps['skirmish01'])
    map_def['players'][1]['is_ai'] = False
    gm = GameManager.start_skirmish(map_def)
    st = gm.state
    st.entities.clear()
    target = gm.factory.spawn_station('command_station', 1, Vec3(0, 0, 800))
    ship = gm.factory.spawn_ship('imperial_corvette', 0, Vec3())
    st.queue_command(AttackCommand(0, [ship.id], target.id))
    original = restore(precise(gm), True)
    launches = []
    st.events.subscribe('weapon_fired', lambda event: launches.append(event.data)
                        if event.data.get('attacker_id') == ship.id else None)
    for tick in range(300):
        gm.step(1/30)
        original.step(1/30)
        assert precise(gm) == precise(original), f'coplanar control differs at {tick}'
    assert st.tick == 300 and launches, 'vacuous coplanar combat control'
    return {'executed_ticks': st.tick, 'pursuer_firing_events': len(launches),
            'precise_state_equal_every_tick': True}


def capture(gm, path, issue_click=False):
    import numpy as np
    import pygame
    from OpenGL import GL
    from render.camera import Camera
    from render.renderer import Renderer
    from render.hud import HUD
    from render.input import InputController
    camera = Camera(1280, 900)
    camera.target = [11463.46860285947, 900, 171.1095634896808]
    camera.yaw, camera.pitch, camera.distance = 25, 35, 7000
    renderer = Renderer(gm.state, camera)
    renderer.diff_render, renderer.time = True, 3.0
    hud = HUD(1280, 900, gm.state)
    app = types.SimpleNamespace(flash=lambda message: None)
    controller = InputController(gm.state, camera, hud, app)
    controller.selection = set(IDS)
    before = precise(gm)
    try:
        renderer.draw(0, set(IDS))
        fighter = gm.state.entity(28)
        pick = None
        point = None
        if fighter:
            screen = camera.world_to_screen(fighter.pos.x, fighter.pos.y, fighter.pos.z)
            assert screen is not None, 'fighter off diagnostic viewport'
            from OpenGL.GLU import gluProject
            gl_screen = gluProject(fighter.pos.x, fighter.pos.y, fighter.pos.z)
            gl_top_down = (gl_screen[0], 900 - gl_screen[1])
            assert max(abs(a-b) for a, b in zip(screen, gl_top_down)) < .1, (screen, gl_top_down)
            point = tuple(round(v) for v in screen)
            picked = controller._pick_target(point)
            assert picked is not None and picked.id == 28, (point, picked)
            pick = {'screen': screen, 'gl_screen': gl_top_down,
                    'picked_id': picked.id, 'detected': gm.state.can_see(0, 28)}
        assert before == precise(gm), 'render/picking modified sim state'
        GL.glFinish()
        raw = GL.glReadPixels(0, 0, 1280, 900, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
        pixels = np.flipud(np.frombuffer(raw, np.uint8).reshape(900, 1280, 3)).copy()
        assert GL.glGetError() == GL.GL_NO_ERROR
        assert int((pixels.max(2) > 45).sum()) > 1000, 'empty framebuffer'
        pygame.image.save(pygame.image.frombuffer(pixels.tobytes(), (1280, 900), 'RGB'), str(path))
        if issue_click:
            assert fighter is not None and point is not None and pick is not None
            pygame.event.clear()
            pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=point))
            pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=3, pos=point))
            for event in pygame.event.get():
                controller.handle_event(event)
            command = gm.state.command_queue[-1].to_dict()
            assert command['type'] == 'attack' and command['target_id'] == 28
            assert command['unit_ids'] == list(IDS), command
            pick['command'] = command
        return pick
    finally:
        renderer.close()
        hud.close()


def trial(snapshot, baseline, out, ticks):
    gm = restore(snapshot, baseline)
    st = gm.state
    fighter = st.entity(28)
    assert fighter is not None and fighter.alive and st.can_see(0, 28)
    picked = capture(gm, out / ('baseline-before.png' if baseline else 'fixed-before.png'), True)
    metrics = {'baseline': baseline, 'start_tick': st.tick, 'picked': picked,
               'fighter_initial': [fighter.pos.x, fighter.pos.y, fighter.pos.z],
               'pursuer_max_y': {i: st.entity(i).pos.y for i in IDS},
               'shots_at_fighter': 0, 'hits_on_fighter': 0, 'exact_restored_ticks': 0}
    def fired(event):
        metrics['shots_at_fighter'] += sum(p.target_id == 28 and p.owner == 0
                                         for p in st.projectiles.values()
                                         if p.id >= counts[0])
        counts[0] = st.next_projectile_id
    def hit(event):
        if event.data.get('target_id') == 28:
            metrics['hits_on_fighter'] += 1
    counts = [st.next_projectile_id]
    st.events.subscribe('weapon_fired', fired)
    st.events.subscribe('projectile_hit', hit)
    twin = None
    first_hit_captured = False
    capture_at = None
    for tick in range(ticks):
        if st.game_over:
            break
        gm.step(1/30)
        if twin is not None and metrics['exact_restored_ticks'] < 300:
            twin.step(1/30)
            a, b = precise(gm), precise(twin)
            if a != b:
                (out / 'restore-first-difference.json').write_text(json.dumps({'tick': st.tick, 'original': a, 'restored': b}))
                raise AssertionError(f'precise continuation differs at {st.tick}')
            metrics['exact_restored_ticks'] += 1
        if tick == 74:
            saved = precise(gm)
            (out / ('baseline-mid.json' if baseline else 'fixed-mid.json')).write_text(json.dumps(saved))
            twin = restore(saved, baseline)
            assert saved == precise(twin)
        for i in IDS:
            entity = st.entity(i)
            if entity is not None:
                metrics['pursuer_max_y'][i] = max(metrics['pursuer_max_y'][i], entity.pos.y)
        if not baseline and tick == 90:
            capture_at = capture(gm, out / 'fixed-climbing.png')
        if not baseline and metrics['hits_on_fighter'] and not first_hit_captured:
            metrics['first_hit_tick'] = st.tick
            capture(gm, out / 'fixed-first-hit.png')
            first_hit_captured = True
    metrics.update(end_tick=st.tick, fighter_hull=fighter.hull, fighter_alive=fighter.alive,
                   fighter_final=[fighter.pos.x, fighter.pos.y, fighter.pos.z],
                   climbing_pick=capture_at)
    capture(gm, out / ('baseline-after.png' if baseline else 'fixed-after.png'))
    expected_continuation = min(300, st.tick - metrics['start_tick'] - 75)
    assert expected_continuation > 0, 'match ended before the mid-flight restore'
    assert metrics['exact_restored_ticks'] == expected_continuation, metrics
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--ticks', type=int, default=1331)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    raw = args.snapshot.read_bytes()
    snapshot = json.loads(raw)
    assert snapshot['tick'] == 109825, 'requires the issue attack snapshot'
    import pygame
    from OpenGL import GL
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_mode((1280, 900), pygame.OPENGL | pygame.DOUBLEBUF)
    GL.glViewport(0, 0, 1280, 900)
    GL.glEnable(GL.GL_DEPTH_TEST)
    GL.glClearColor(.008, .012, .025, 1)
    try:
        coplanar = verify_coplanar_control()
        baseline = trial(snapshot, True, args.out, args.ticks)
        fixed = trial(snapshot, False, args.out, args.ticks)
        assert (args.out / 'baseline-before.png').read_bytes() == (args.out / 'fixed-before.png').read_bytes(), 'initial frame control differs'
        assert baseline['fighter_hull'] == 60 and baseline['shots_at_fighter'] == 0, baseline
        assert all(v == 0 for v in baseline['pursuer_max_y'].values()), baseline
        assert fixed['hits_on_fighter'] > 0 and not fixed['fighter_alive'], fixed
        assert max(fixed['pursuer_max_y'].values()) > 100, fixed
        report = {'snapshot_sha256': hashlib.sha256(raw).hexdigest(), 'baseline_source': BASE,
                  'sdl_driver': pygame.display.get_driver(),
                  'gl_renderer': GL.glGetString(GL.GL_RENDERER).decode(),
                  'camera': 'inferred diagnostic view; no replay camera telemetry',
                  'coplanar_control': coplanar, 'baseline': baseline, 'fixed': fixed}
        (args.out / 'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        print('NEBULA_ALTITUDE_DIAG_OK')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
