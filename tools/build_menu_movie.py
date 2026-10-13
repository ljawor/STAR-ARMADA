"""Offline synthetic PRESENTATION fixture using the unchanged production renderer.

No GameManager instance, simulation systems, saves, replay or recording. The
fixture's omniscience exists only in this offline state subclass. Runtime menus
read JPEGs; they never import this module. Source animation is 16s, with its last
second crossfaded over its first second to produce a 15s/24fps baked loop.
"""
from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame
# Import ordering is significant: manager resolves the project's data cycle.
from game.core.manager import GameManager  # noqa: F401
from game.data.store import DataStore
from game.core.state import GameState, PlayerState, MapInfo
from game.core.entity import Entity
from game.core.world import Projectile
from game.core.vectors import Vec3
from render.ship_sizes import ship_size, hull_contact_offset


class PresentationState(GameState):
    """Offline-only all-visible renderer input; not a gameplay reveal-all flag."""
    def can_see(self, player_id, entity_id):
        return entity_id in self.entities

    def is_position_visible(self, player_id, pos):
        return True

    def is_position_explored(self, player_id, pos):
        return True

    def sensor_sources(self, player_id):
        return [(next(iter(self.entities.values())), 60000.)]


class PresentationFixture:
    def __init__(self):
        self.ds = DataStore.get()
        self.state = PresentationState()
        self.state.players = {
            0: PlayerState(0, faction='imperial', color=(.20, .54, 1.), team=0),
            1: PlayerState(1, faction='rebel', color=(1., .24, .19), team=1)}
        self.state.map_info = MapInfo(name='Offline cinematic fixture', bounds=6000,
                                     star={'pos': [-8000, 6000, -10000], 'size': 2800,
                                           'color': [1., .82, .62]},
                                     nebulas=[{'pos': [0, -800, -2500], 'radius': 1800,
                                               'color': [.15, .23, .40]}])
        # Real class ratios, never enlarged fake meshes. +Z bow, yaw towards enemy.
        layout = [
            ('imperial_supercapital', 0, (-230, -15, -100), math.pi/2),
            ('imperial_battleship', 0, (-220, 28, 160), math.pi/2),
            ('imperial_frigate', 0, (-45, -16, 240), math.pi/2),
            ('imperial_frigate', 0, (-80, 62, -210), math.pi/2),
            ('rebel_battleship', 1, (245, 10, -75), -math.pi/2),
            ('rebel_frigate', 1, (160, 22, 235), -math.pi/2),
            ('rebel_frigate', 1, (170, 60, -230), -math.pi/2)]
        self.bases = {}
        for i, (data_id, owner, pos, yaw) in enumerate(layout, 1):
            size = ship_size(self.ds, data_id, self.state.players[owner].faction)
            e = Entity(id=i, kind='ship', owner=owner, data_id=data_id,
                       pos=Vec3(*pos), yaw=yaw, radius=size.radius, is_ship=True,
                       sensor_range=60000., max_shield_quad=100.,
                       shields={q: 100. for q in ('front', 'rear', 'left', 'right')})
            self.state.add_entity(e)
            self.bases[i] = pos
        self.sample(0)

    def sample(self, t):
        st = self.state
        st.time = t
        st.tick = round(t * 240)
        st.effects = []
        st.projectiles = {}
        for i, e in st.entities.items():
            x, y, z = self.bases[i]
            phase = math.tau * t / 16
            e.pos = Vec3(x + 8*math.sin(phase+i), y + 3*math.sin(phase+i*.7),
                         z + 9*math.cos(phase+i*.4))
            e.vel = Vec3(5 if e.owner == 0 else -5, 0, 0)
        # Staggered bilateral broadside volleys, contact ripples, warm armor hits.
        for n, (source_id, target_id) in enumerate([(1, 5), (5, 1), (2, 6),
                                                    (6, 2), (3, 6), (7, 4), (4, 7)]):
            source, target = st.entities[source_id], st.entities[target_id]
            age = (t + .12 + n*.19) % .85
            source_size = ship_size(self.ds, source.data_id, st.players[source.owner].faction)
            start = (source.pos.x + (1 if source.owner == 0 else -1)*source_size.length*.42,
                     source.pos.y + 14, source.pos.z + (n%3-1)*8)
            delta = tuple(start[k] - (target.pos.x, target.pos.y, target.pos.z)[k] for k in range(3))
            length = math.sqrt(sum(v*v for v in delta))
            normal = tuple(v/length for v in delta)
            size = ship_size(self.ds, target.data_id, st.players[target.owner].faction)
            center = (target.pos.x, target.pos.y, target.pos.z)
            end = tuple(center[k] + normal[k] * size.radius*1.08 for k in range(3))
            color = (.25, .7, 1.) if source.owner == 0 else (1., .22, .13)
            # Analytic moving bolts, not ProjectileSystem or damage simulation.
            for j in range(3):
                flight = (t + n*.13 + j*.24) % .85
                if flight < .55:
                    u = flight/.55
                    p = tuple(start[k] + (end[k]-start[k])*u for k in range(3))
                    pid = n*3+j
                    st.projectiles[pid] = Projectile(pid, source.owner, 'laser_cannon',
                        Vec3(*p), Vec3(), target_id, 0., 1., 1., 1., .55-flight,
                        color=color, attacker_entity_id=source_id)
                    tail = tuple(p[k] - (end[k]-start[k])*.055 for k in range(3))
                    st.effects.append(dict(kind='beam', pos=tail, target_pos=p,
                                           color=color, t=.11, resolved_contact=True))
            if age < .25:
                st.effects.extend([
                    dict(kind='beam', pos=start, target_pos=end, color=color, t=age,
                         resolved_contact=True),
                    dict(kind='muzzle', pos=start, color=color, t=age)])
            if age < .55:
                st.effects.append(dict(kind='shield_hit', pos=end, center=center,
                                       radius=size.radius*1.08, size=14, normal=normal,
                                       t=age, seed=n, target_id=target_id))
            if n in (2, 4) and .30 < age < .72:
                offset = hull_contact_offset(size, normal, target.yaw,
                                             tuple(v*size.radius for v in normal))
                if offset:
                    contact = tuple(center[k]+offset[k] for k in range(3))
                    st.effects.append(dict(kind='hull_hit', pos=contact, normal=normal,
                                           size=10, t=age-.3, seed=n+20, target_id=target_id))


def camera_pose(t):
    phase = math.tau*t/16
    return (20 + 5*math.sin(phase), 27 + 2*math.cos(phase),
            650 + 15*math.sin(phase))


def loop_frame(tail, head, alpha):
    if head is None:
        return tail
    result = tail.copy()
    overlay = head.copy()
    overlay.set_alpha(round(255 * alpha))
    result.blit(overlay, (0, 0))
    return result


def build_movie(renderer, fixture, cam, args, report):
    """Render/encode offline; runtime needs only the ZIP and pygame."""
    import json
    import subprocess
    import tempfile
    import time
    import zipfile
    import numpy as np
    from OpenGL import GL
    from render.menu_movie import MenuMovie
    scratch = Path.home() / '.hermes/cache/scratch'
    scratch.mkdir(parents=True, exist_ok=True)
    report['full_render_gl_errors'] = 0
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='menu-movie-', dir=scratch) as folder:
        folder = Path(folder)
        head = []  # Offline-only 1s transition buffer, not runtime preload.
        for i in range(384):
            pygame.event.pump()
            t = i / 24
            fixture.sample(t)
            cam.yaw, cam.pitch, cam.distance = camera_pose(t)
            renderer.time = t
            renderer.draw(1/24, set())
            GL.glFinish()
            err = int(GL.glGetError())
            if err:
                report['full_render_gl_errors'] += 1
                raise RuntimeError(f'OpenGL error {err} at source frame {i}')
            data = GL.glReadPixels(0, 0, 1280, 720, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
            frame = pygame.transform.flip(pygame.image.frombuffer(bytes(data), (1280, 720), 'RGB'), False, True)
            if i < 24:
                head.append(frame)
                continue
            if i >= 360:
                j = i - 360
                u = j / 23
                alpha = u*u*(3-2*u)
                frame = loop_frame(frame, head[j], alpha)
            index = i - 24
            pygame.image.save(frame, str(folder / f'{index:05d}.png'))
            if index in (0, 180, 359):
                name = {0: 'start', 180: 'middle', 359: 'end'}[index]
                pygame.image.save(frame, str(args.output_dir / (name+'.png')))
            if index % 60 == 0:
                print(f'Rendered {index}/360', flush=True)
        sequence = str(folder / '%05d.png')
        # Offline encoder only. JPEG q=3 preserves armor/lighting detail.
        subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
                        '-framerate', '24', '-i', sequence, '-q:v', '3',
                        '-start_number', '0', str(folder/'%05d.jpg')], check=True)
        subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
                        '-framerate', '24', '-i', sequence, '-c:v', 'libx264',
                        '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
                        '-movflags', '+faststart',
                        str(args.output_dir / 'intro-battle-preview.mp4')], check=True)
        args.asset.parent.mkdir(parents=True, exist_ok=True)
        meta = dict(version=1, width=1280, height=720, fps=24, frame_count=360,
                    duration_seconds=15, still_frame=180, loop='baked-crossfade',
                    crossfade_frames=24, renderer='render.renderer.Renderer',
                    fixture='offline synthetic presentation; no gameplay simulation',
                    msaa_samples=report['msaa_samples'],
                    models=sorted({e.data_id for e in fixture.state.entities.values()}))
        temporary = args.asset.with_suffix('.tmp')
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED) as z:
            z.writestr('metadata.json', json.dumps(meta, indent=2))
            for i in range(360):
                z.write(folder/f'{i:05d}.jpg', f'frames/{i:05d}.jpg')
        temporary.replace(args.asset)
    report['asset_bytes'] = args.asset.stat().st_size
    report['render_encode_seconds'] = time.perf_counter()-started
    # Decode + resize real asset sequentially (no cache hits), in real pygame.
    timings = []
    with MenuMovie(args.asset.parent.parent, 'menu/'+args.asset.name) as movie:
        for i in range(360):
            before = time.perf_counter()
            frame = movie.get_frame((i+.1)/24, (1440, 810))
            timings.append((time.perf_counter()-before)*1000)
            if frame is None:
                raise RuntimeError('Asset decode verification failed: '+str(movie.error))
        report['playback'] = dict(decode_scale_mean_ms=float(np.mean(timings)),
            decode_scale_p95_ms=float(np.percentile(timings, 95)),
            decode_scale_max_ms=float(max(timings)), output_size=[1440, 810],
            cache=movie.cache_info(), frames_verified=360)
        first = pygame.surfarray.array3d(movie.get_frame(0, (1280, 720))).astype(np.int16)
        last = pygame.surfarray.array3d(movie.get_frame(359/24, (1280, 720))).astype(np.int16)
        report['loop_seam_mean_abs_rgb'] = float(np.abs(first-last).mean())
        report['loop_seam_changed_fraction'] = float((np.abs(first-last).max(axis=2)>10).mean())


def main():
    import argparse
    import json
    import numpy as np
    from OpenGL import GL
    from render.camera import Camera
    from render.renderer import Renderer
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview-only', action='store_true')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--asset', type=Path, default=ROOT / 'assets/menu/battle.zip')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pygame.display.init()
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
    pygame.display.set_mode((1280, 720), pygame.OPENGL | pygame.DOUBLEBUF)
    pygame.display.set_caption('STAR ARMADA — offline cinematic render')
    GL.glEnable(GL.GL_MULTISAMPLE)
    GL.glEnable(GL.GL_DEPTH_TEST)
    GL.glClearColor(.006, .009, .018, 1.)
    GL.glViewport(0, 0, 1280, 720)
    fixture = PresentationFixture()
    cam = Camera(1280, 720)
    cam.target = [0., 15., 0.]
    renderer = Renderer(fixture.state, cam)
    renderer.marker_mode = 'off'
    renderer.diff_render = True
    if renderer.skip:
        raise RuntimeError('Do not disable production renderer passes for this build')
    report = {'msaa_samples': int(GL.glGetIntegerv(GL.GL_SAMPLES)), 'samples': []}
    try:
        for name, t in [('start', 1.), ('middle', 8.5), ('end', 15.9583333333)]:
            pygame.event.pump()
            fixture.sample(t)
            cam.yaw, cam.pitch, cam.distance = camera_pose(t)
            renderer.time = t
            renderer.draw(1/24, set())
            GL.glFinish()
            err = int(GL.glGetError())
            data = GL.glReadPixels(0, 0, 1280, 720, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
            frame = pygame.transform.flip(pygame.image.frombuffer(bytes(data), (1280, 720), 'RGB'), False, True)
            pygame.image.save(frame, str(args.output_dir / (name + '.png')))
            pixels = pygame.surfarray.array3d(frame).astype(np.int16)
            centers = [cam.world_to_screen(e.pos.x, e.pos.y, e.pos.z) for e in fixture.state.entities.values()]
            sample = {'name': name, 'time': t, 'gl_error': err,
                      'lit_pixels': int((pixels.max(axis=2) > 40).sum()),
                      'red_pixels': int(((pixels[:,:,0] > pixels[:,:,2]*1.25) & (pixels[:,:,0] > 45)).sum()),
                      'blue_pixels': int(((pixels[:,:,2] > pixels[:,:,0]*1.25) & (pixels[:,:,2] > 45)).sum()),
                      'visible_centers': sum(p is not None and 0 <= p[0] < 1280 and 0 <= p[1] < 720 for p in centers),
                      'centers': centers}
            # Real GL subtraction verifies contacts, not only starfield pixels.
            saved_fx, saved_bolts = fixture.state.effects, fixture.state.projectiles
            fixture.state.effects, fixture.state.projectiles = [], {}
            renderer.draw(0., set())
            GL.glFinish()
            base = np.frombuffer(GL.glReadPixels(0, 0, 1280, 720, GL.GL_RGB,
                GL.GL_UNSIGNED_BYTE), dtype=np.uint8).reshape(720, 1280, 3).astype(np.int16)
            fixture.state.effects = [fx for fx in saved_fx if fx['kind'] == 'shield_hit']
            renderer.draw(0., set())
            GL.glFinish()
            hit = np.frombuffer(GL.glReadPixels(0, 0, 1280, 720, GL.GL_RGB,
                GL.GL_UNSIGNED_BYTE), dtype=np.uint8).reshape(720, 1280, 3).astype(np.int16)
            actual = np.frombuffer(data, dtype=np.uint8).reshape(720, 1280, 3).astype(np.int16)
            sample['weapon_effect_pixels'] = int((np.abs(actual-base).max(axis=2)>5).sum())
            sample['shield_hit_pixels'] = int((np.abs(hit-base).max(axis=2)>2).sum())
            fixture.state.effects, fixture.state.projectiles = saved_fx, saved_bolts
            err = int(GL.glGetError()) or err
            sample['gl_error'] = err
            report['samples'].append(sample)
            if err:
                raise RuntimeError(f'OpenGL error {err}')
        if not args.preview_only:
            build_movie(renderer, fixture, cam, args, report)
        (args.output_dir / 'render-report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
