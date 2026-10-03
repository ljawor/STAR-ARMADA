"""Real-window impact probe, unchanged-scene subtraction + old-code control.

Run: PYTHONPATH=. .venv/bin/python tools/diag_hit_effects.py [output_dir]
No renderer edits needed: call draw_hit directly after the frozen baseline.
The old renderer is loaded from git HEAD into a temporary module, never reverted.
"""
from __future__ import annotations
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pygame
from OpenGL import GL
from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.data.store import DataStore
from render.camera import Camera
from render.renderer import Renderer
from render.hit_effects import draw_hit

W, H = 960, 640


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT/'saves'/'diag_hit_effects'
    out.mkdir(parents=True, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
    for _ in range(5):
        pygame.event.pump()
        pygame.time.wait(30)
    DataStore.reset()
    ds = DataStore()
    gm = GameManager.start_skirmish(ds.maps['skirmish01'])
    st = gm.state
    station = next(e for e in st.entities.values() if e.is_station and e.owner == 0)
    ship = next(e for e in st.entities.values() if e.is_ship and not e.is_construction and e.owner == 0)
    camera = Camera(W, H)
    camera.target = [0., 0., 0.]
    camera.yaw, camera.pitch = 35., 30.
    r = Renderer(st, camera)
    r.diff_render = True
    report = dict(frames=[], perf=[], old={})
    failures = []

    def grab():
        GL.glFinish()
        data = GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
        return np.flipud(np.frombuffer(data, np.uint8).reshape(H, W, 3)).copy()

    def save(arr, name):
        pygame.image.save(pygame.image.frombuffer(arr.tobytes(), (W, H), 'RGB'), str(out/name))

    def render_scene(fxs=()):
        st.effects = list(fxs)
        # Initialize identical entry state for each scene subtraction.
        GL.glDisable(GL.GL_BLEND)
        GL.glEnable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_TEXTURE_2D)
        GL.glDepthMask(True)
        GL.glClearColor(.018, .025, .04, 1.)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        r.draw(0., set())
        return grab()

    def base():
        return render_scene()

    def prepare(entity, distance):
        entity.pos = Vec3()
        entity.vel = Vec3()
        st.entities = {entity.id: entity}
        camera.distance = distance
        # Prime standing shield values; don't count state-diff glows as contacts.
        r._prev_shields.clear()
        r._shield_flash.clear()
        base()
        return base()

    def frame(fxs):
        baseline = base()
        GL.glDisable(GL.GL_LIGHTING)
        # Match the effects pass before hulls: no opaque depth is populated.
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_BLEND)
        GL.glDepthMask(False)
        for fx in fxs:
            draw_hit(r, fx)
        GL.glDepthMask(True)
        return baseline, grab()

    def stats(baseline, image):
        delta = np.abs(image.astype(int)-baseline.astype(int))
        mask = delta.max(axis=2) > 3
        n = int(mask.sum())
        saturated = mask & (image.min(axis=2) >= 240)
        # Interior constant-colour plateau (all four neighbors exactly equal).
        flat = mask.copy()
        for dy, dx in ((0,1), (0,-1), (1,0), (-1,0)):
            flat &= (image == np.roll(image, (dy,dx), axis=(0,1))).all(axis=2)
        return dict(pixels=n, energy=int(delta.sum()),
                    saturated=float(saturated.sum()/max(1,n)),
                    flat=float(flat.sum()/max(1,n)))

    for label, entity, distance in (('station_tactical', station, 6000.),
                                     ('station_near', station, 1500.),
                                     ('ship_tactical', ship, 2200.),
                                     ('ship_near', ship, 650.)):
        prepare(entity, distance)
        # Contact on near shell, offset toward screen right, not at its center.
        yaw, pitch = math.radians(camera.yaw), math.radians(camera.pitch)
        n = Vec3(math.sin(yaw)*math.cos(pitch), math.sin(pitch),
                 math.cos(yaw)*math.cos(pitch))
        incoming = n * -1
        for kind in ('shield_hit', 'hull_hit'):
            st.effects.clear()
            gm.damage._spawn_hit(kind, entity, entity.pos+n*entity.radius,
                                 None, 12., incoming, 734)
            fx = dict(st.effects[-1])
            energies = []
            for age in (0., .08, .18, .34, .50, .65):
                control, image = frame([dict(fx, t=age)])
                m = stats(control, image)
                m.update(subject=label, kind=kind, age=age)
                report['frames'].append(m)
                energies.append(m['energy'])
                save(image, f'{label}_{kind}_{age:.2f}.png')
                if m['saturated'] > .015 or m['flat'] > .10:
                    failures.append(f'flat/saturated contact: {m}')
            if max(energies[:3]) < 30:
                failures.append(f'invisible effect {label}/{kind}: {energies}')
            if energies[-1] != 0:
                failures.append(f'not expired {label}/{kind}: {energies}')
            if energies[4] > max(energies[:3]) * .15:
                failures.append(f'poor fade {label}/{kind}: {energies}')

    # Use a temporary old module so concurrent working-tree renderer edits are
    # never touched. The actual old effect methods render against the SAME scene.
    old_source = subprocess.check_output(['git', 'show', '8de573e'], cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix='hit-control-', dir=os.environ.get('TMPDIR')) as temp:
        path = Path(temp)/'old_renderer.py'
        path.write_bytes(old_source)
        spec = importlib.util.spec_from_file_location('hit_control_renderer', path)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        prepare(station, 6000.)
        control = base()
        # Cluster reproduces simultaneous projectile generic+damage contact glows.
        st.effects = [dict(kind=kind, pos=[0., 0., 0.], t=0., color=[.8,.9,1.])
                      for _ in range(16) for kind in ('impact', 'hull_hit')]
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_TEXTURE_2D)
        old.Renderer._draw_effects(r)
        bad = grab()
        old_metrics = stats(control, bad)
        report['old'] = old_metrics
        save(bad, 'old_duplicate_disc.png')
        # Generic glints are small; the actual broad white veil is caused
        # by radius-scaled quadrant billboards, measured separately below.
        control = base()
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_BLEND)
        GL.glDisable(GL.GL_TEXTURE_2D)
        for q in ('front', 'rear', 'left', 'right'):
            old.Renderer._shield_quadrant_glow(r, station, .85, q, 1.)
        quadrant = grab()
        report['old_quadrants'] = stats(control, quadrant)
        save(quadrant, 'old_quadrant_billboards.png')

    prepare(station, 6000.)
    st.effects.clear()
    gm.damage._spawn_hit('shield_hit', station, Vec3(0,0,station.radius), None, 12)
    shield_fx = dict(st.effects[-1], t=.08)
    gm.damage._spawn_hit('hull_hit', station, Vec3(0,0,station.radius), None, 12)
    hull_fx = dict(st.effects[-1], t=.08)
    control, image = frame([shield_fx, hull_fx]*16)
    m = stats(control, image)
    report['stacked'] = m
    if report['old_quadrants']['pixels'] <= m['pixels'] * 10:
        failures.append('old quadrant control did not expose the broad veil')
    save(image, 'new_stacked_contacts.png')
    if m['saturated'] > .015 or m['flat'] > .10:
        failures.append(f'new contact stack makes disc: {m}')

    # Verify the real draw path, not just the standalone contact helper.
    control = base()
    integrated = render_scene([shield_fx, hull_fx])
    im = stats(control, integrated)
    report['integrated'] = im
    save(integrated, 'integrated_contacts.png')
    if im['pixels'] < 3 or im['saturated'] > .015 or im['flat'] > .10:
        failures.append(f'integrated contact rendering failed: {im}')

    # GL state preservation is verified in a real context (including blend,
    # current colour, line width, texture/cull/lighting and depth write).
    GL.glEnable(GL.GL_CULL_FACE)
    GL.glEnable(GL.GL_LIGHTING)
    GL.glDisable(GL.GL_BLEND)
    GL.glLineWidth(2.)
    GL.glColor4f(.3,.4,.5,.6)
    GL.glDepthMask(True)
    def state():
        return (tuple(GL.glGetFloatv(GL.GL_CURRENT_COLOR)),
                float(GL.glGetFloatv(GL.GL_LINE_WIDTH)),
                bool(GL.glGetBooleanv(GL.GL_DEPTH_WRITEMASK)),
                tuple(bool(GL.glIsEnabled(x)) for x in (GL.GL_BLEND, GL.GL_LIGHTING,
                                                       GL.GL_CULL_FACE, GL.GL_TEXTURE_2D)),
                int(GL.glGetIntegerv(GL.GL_BLEND_SRC)), int(GL.glGetIntegerv(GL.GL_BLEND_DST)))
    before = state()
    draw_hit(r, shield_fx)
    draw_hit(r, hull_fx)
    if state() != before:
        failures.append('GL state leak')
    report['state_restored'] = state() == before

    # Warmed-up absolute and no-effect delta; scene cost excluded equally.
    def bench(n, frames=15):
        GL.glDisable(GL.GL_LIGHTING)
        for _ in range(3):
            for i in range(n):
                draw_hit(r, dict(shield_fx if i%2 else hull_fx, seed=i))
        GL.glFinish()
        start = time.perf_counter()
        for _ in range(frames):
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            for i in range(n):
                draw_hit(r, dict(shield_fx if i%2 else hull_fx, seed=i))
        GL.glFinish()
        return (time.perf_counter()-start)*1000/frames
    zero = bench(0)
    for count in (20, 60, 150):
        ms = bench(count)
        report['perf'].append(dict(count=count, ms=ms, delta_ms=ms-zero))
        if count == 150 and ms-zero > 25.:
            failures.append(f'150 contacts exceed 25ms render budget: {ms-zero:.2f}ms')
    error = int(GL.glGetError())
    report['gl_error'] = error
    if error:
        failures.append(f'GL error {error}')
    report['failures'] = failures
    (out/'metrics.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    pygame.quit()
    print('DIAG_FAIL' if failures else 'DIAG_OK', out)
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
