"""Bounded continuous native motion and same-entity ownership fixtures.

No simulation progression is claimed: fixture transforms/owners change explicitly;
production rendering must preserve each frame's authoritative state exactly.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.chdir(ROOT)
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--consumer-oracle', action='store_true')
    parser.add_argument('--diagnose-no-vfx', action='store_true', help='diagnostic only; suppress velocity-triggered trails/glows')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('capture_slice', ROOT / 'artifacts/alliance_blender_trio/evidence/capture_slice.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.isolate(ROOT, out)
    import game.core.manager
    import pygame
    import numpy as np
    from PIL import Image, ImageDraw
    from OpenGL import GL
    from game.core.manager import GameManager
    from game.core.entity import Entity
    from game.core.state import PlayerState
    from game.core.vectors import Vec3
    from game.benchmark import state_hash
    from render import asset_selection as selection
    from render.camera import Camera
    from render.renderer import Renderer
    from render.faction_visuals import owner_faction
    from render.ship_sizes import ship_visual_key
    oracle = None
    if args.consumer_oracle:
        from test_s07_capture_transition import assert_transition_consumers
        oracle = assert_transition_consumers
    selection.configure({'model_preview': True, 'visual_packs': []})
    pygame.display.init()
    pygame.font.init()
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
    W, H = 640, 480
    pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
    GL.glViewport(0, 0, W, H)
    assert int(GL.glGetIntegerv(GL.GL_SAMPLES)) == 4
    report = dict(status='running', renderer_sha256=sha(ROOT / 'render/renderer.py'),
                  harness_sha256=sha(__file__), rows=[], consumer_oracle=bool(oracle),
                  diagnostic_only=args.diagnose_no_vfx,
                  limits='Presentation motion with explicit fixture ownership/position edits, not paid capture commands or simulation progression. All production passes enabled, 4x MSAA; cached/uncached equality is exact, no tolerance.')
    renderer = None
    try:
        for kind, data_id in [('overlapping_ships', 'imperial_frigate'), ('ship', 'imperial_crew_transport'),
                              ('convoy', 'trade_convoy'), ('station', 'shipyard'),
                              ('satellite', 'defense_satellite'), ('installation', 'planet_extractor')]:
            gm = GameManager()
            st = gm.state
            st.players = {0: PlayerState(0, faction='imperial', team=0, is_ai=False, color=(1., .18, .12)),
                          1: PlayerState(1, faction='syndicate', team=0, is_ai=False, color=(.12, .4, 1.))}
            m = gm.ds.maps['skirmish01']
            st.map_info.bounds = m['bounds']
            st.map_info.star = dict(m['star'])
            pos = Vec3(0., 5000., 0.)
            if kind in ('station', 'satellite', 'installation'):
                e = gm.factory.spawn_station(data_id, 0, pos)
            elif kind == 'convoy':
                e = Entity(id=1, kind='ship', owner=0, data_id=data_id, is_ship=True, pos=pos, radius=32.)
                st.add_entity(e)
            else:
                e = gm.factory.spawn_ship(data_id, 0, pos)
            other = None
            if kind == 'overlapping_ships':
                other = gm.factory.spawn_ship(data_id, 0, Vec3(50., 5020., 20.))
            if kind in ('satellite', 'installation'):
                planet = Entity(id=1000, kind='planet', owner=0, data_id='temperate', is_planet=True,
                                pos=Vec3(0., 4349., 0.), radius=650.)
                st.add_entity(planet)
                e.planet_id = planet.id
                if kind == 'satellite':
                    from game.systems.satellite_orbits import orbit_position
                    e.satellite_slot = 0
                    e.pos = orbit_position(planet, e.radius, 0., 0)
                else:
                    from game.systems.planet_buildings import planet_building_site
                    e.planet_building_slot = 4
                    e.pos, _ = planet_building_site(planet, 4)
            cam = Camera(W, H)
            cam.target = list(e.pos.to_tuple())
            cam.yaw, cam.pitch, cam.distance = 48., (80. if e.is_station else 55.), 1000.
            renderer = Renderer(st, cam)
            r = renderer
            r.local_player = 0
            r.diff_render = True
            assert not r.skip and r.materials.available
            cam.bind_scene(st, lambda: r.local_player, lambda: r.time * 3. * np.pi / 180.)
            radius = r._station_visual_radius(e) if e.is_station else r._ship_size(e).radius
            cam.distance = max(200., radius * 5.)
            original = r._draw_ships
            row = dict(kind=kind, data_id=data_id, frames=[], transitions=[], exact_parity=True)
            frames = []
            for i in range(48):
                e.owner = 1 if 16 <= i < 32 else 0
                if other:
                    other.owner = e.owner
                r.local_player = e.owner
                r.time = i / 24.
                cam.yaw = 48. + i * .5
                if not e.is_station:
                    e.pos.x = i * 1.5
                    e.yaw = i * .012
                    e.vel = Vec3(36., 0., 0.)
                    if other:
                        other.pos.x = e.pos.x + 50.
                        other.pos.z = 20. - i * .5
                        other.yaw = e.yaw + .1
                        other.vel = Vec3(36., 0., -12.)
                if args.diagnose_no_vfx:
                    e.vel = Vec3(0., 0., 0.)
                    if other:
                        other.vel = Vec3(0., 0., 0.)
                st.grid.rebuild(st.entities)
                gm.visibility.update()
                faction = owner_faction(st, e.owner)
                binding = f'{faction}:{data_id}' if e.is_station else ship_visual_key(gm.ds, data_id, faction)
                resolved = selection._resolver.resolve(binding)
                assert resolved is not None, binding
                if i in (0, 16, 32):
                    item = dict(frame=i, owner=e.owner, binding=binding, revision=resolved.revision)
                    if oracle:
                        item['consumers'] = oracle(st, e, r, cam, station_angle=r.time * 3. * np.pi / 180.)
                    row['transitions'].append(item)
                before = state_hash(st)
                captures = {}
                for mode in ('cached', 'uncached'):
                    r._draw_ships = original if mode == 'cached' else lambda selected, cache: original(selected, None)
                    r._reset_frame_cache()
                    repeated = []
                    for settle in range(4):
                        pygame.event.pump()
                        r.draw(0., set())
                        GL.glFinish()
                        assert GL.glGetError() == 0 and state_hash(st) == before
                        repeated.append(np.frombuffer(GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE), np.uint8).reshape(H, W, 3)[::-1].copy())
                    assert np.array_equal(repeated[-1], repeated[-2]), (kind, i, mode, 'same-path repeat')
                    captures[mode] = repeated[-1]
                if i in (0, 16, 32):
                    saved_entities = dict(st.entities)
                    try:
                        st.entities.pop(e.id)
                        r._draw_ships = original
                        r._reset_frame_cache()
                        empty_state = state_hash(st)
                        empty_frames = []
                        for _ in range(4):
                            r.draw(0., set())
                            GL.glFinish()
                            assert GL.glGetError() == 0 and state_hash(st) == empty_state
                            empty_frames.append(np.frombuffer(GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE), np.uint8).reshape(H, W, 3)[::-1].copy())
                        assert np.array_equal(empty_frames[-1], empty_frames[-2])
                        subject_pixels = int(np.any(captures['cached'] != empty_frames[-1], axis=2).sum())
                        assert subject_pixels > 0, (kind, i, 'blank subject')
                        row['transitions'][-1]['subject_pixels'] = subject_pixels
                    finally:
                        st.entities.clear()
                        st.entities.update(saved_entities)
                        r._reset_frame_cache()
                    assert state_hash(st) == before
                changed = int(np.any(captures['cached'] != captures['uncached'], axis=2).sum())
                row['frames'].append(dict(index=i, owner=e.owner, state_sha256=before, cached_uncached_changed_pixels=changed))
                image = Image.fromarray(captures['cached'])
                image.save(out / f'{kind}-{i:03d}.png')
                row['frames'][-1]['sha256'] = sha(out / f'{kind}-{i:03d}.png')
                frames.append(image)
                if changed:
                    Image.fromarray(captures['uncached']).save(out / f'{kind}-{i:03d}-uncached.png')
                    row['exact_parity'] = False
                    report['rows'].append(row)
                    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
                    raise AssertionError((kind, i, changed))
            assert len({f['sha256'] for f in row['frames']}) > 1
            frames[0].save(out / f'{kind}.gif', save_all=True, append_images=frames[1:], duration=42, loop=0)
            sheet = Image.new('RGB', (1280, 8 * 140), (12, 17, 25))
            draw = ImageDraw.Draw(sheet)
            for i, image in enumerate(frames):
                im = image.resize((213, 120))
                x, y = (i % 6) * 213, (i // 6) * 140
                sheet.paste(im, (x, y + 20))
                draw.text((x + 4, y + 2), f'{i:02d} owner {row["frames"][i]["owner"]}', fill='white')
            sheet.save(out / f'{kind}-all-frames.jpg', quality=94)
            report['rows'].append(row)
            r.close()
            renderer = None
            (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(dict(kind=kind, frames=len(frames), exact_parity=True)), flush=True)
        report['status'] = 'passed'
    finally:
        if renderer:
            renderer.close()
        selection.configure({})
        pygame.display.quit()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
if __name__ == '__main__':
    main()
