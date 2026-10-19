#!/usr/bin/env python3
"""Actual production renderer, UNAPPROVED REVIEW-ONLY batch contact sheet.

One scene per pending specimen (S06 batch authoring): the specimen takes the 'capital'
slot and a fixed context group is placed around it, exactly as the single-specimen
Liberty harness does. Geometry is injected in-process through the existing
`render.asset_selection.mesh_for` seam; no registry, approval, production source or
gameplay data is written and the default stays unchanged.

Every capture is a before/after pair of the same camera, so the sheet is a look
comparison, not a scale comparison; the batch overview is the only scale view.

Run from the repository root:
  env -u SDL_VIDEODRIVER .venv/bin/python tools/diag_alliance_batch_review.py \
      --spec art/manifests/pending/S06-BATCH-<id>.json --out /ABSOLUTE/FRESH/DIR
Optional: --motion <binding> (one paired 5s motion clip), --skip-motion.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
W, H = 1280, 800
VIEW_NAMES = ('close', 'rear', 'tactical', 'common-scale')
FACTION_ORDER = ('rebel', 'imperial', 'confederacy', 'syndicate')
FACTION_OWNER = {name: index for index, name in enumerate(FACTION_ORDER)}
FACTION_COLOR = {'rebel': (.35, .65, 1.), 'imperial': (1., .35, .25),
                 'confederacy': (.45, .95, .55), 'syndicate': (.95, .75, .3)}


def players_for(factions):
    """One real player per faction the scene needs, keyed by `FACTION_OWNER`.

    The specimen's *owner* decides which faction's structure, so the scene has to hold a
    player of that faction (see `build_review_scene`).
    """
    from game.core.state import PlayerState
    return {FACTION_OWNER[name]: PlayerState(FACTION_OWNER[name], faction=name, team=index,
                                             is_ai=False, color=FACTION_COLOR[name])
            for index, name in enumerate(factions)}


def load_spec(path):
    spec = json.loads(Path(path).read_text(encoding='utf-8'))
    assert spec['schema'] == 1 and spec['assets'], 'batch spec needs schema 1 and assets'
    for asset in spec['assets']:
        for key in ('binding', 'identifier', 'mesh', 'envelope', 'min_length', 'data_id', 'slot'):
            assert key in asset, (asset.get('binding'), key)
    return spec


def placements_for(asset):
    """The reviewed specimen plus the same fixed context group for every row.

    Slots are spaced further apart than the widest class pair in the batch so the
    inherited non-overlap assertion holds for a 250-radius supercapital too. A station
    binding spawns a station, which the shared scene's `spawn_station` path already
    supports, and `capture_slice.geometry` measures it with `station_bounds`.
    """
    return [('capital', 'station' if asset.get('station_kind') else 'ship',
             asset['data_id'], FACTION_OWNER[asset.get('faction', 'rebel')],
             list(asset['slot']), 0.),
            ('escort', 'ship', 'rebel_frigate', 0, [-4200, 0, 2900], 0.),
            ('battleship', 'ship', 'rebel_battleship', 0, [-4200, 0, 1500], 0.),
            ('enemy_a', 'ship', 'imperial_frigate', 1, [-3500, 0, 2200], -1.5707963267948966),
            ('enemy_b', 'ship', 'imperial_frigate', 1, [-3500, 0, 2900], -1.5707963267948966)]


def station_scale(asset):
    """The game's own station scale: `assets/data/stations/stations.json` radius over the
    nominal radius-50 space the station layout is authored in.

    A station binding's union-safe camera is driven by this scaled footprint, not by the
    raw mesh extent, so a 96-unit-wide station needs its `close` view three times further
    out than a 96-unit-long ship does.
    """
    stations = json.loads((ROOT / 'assets/data/stations/stations.json')
                          .read_text(encoding='utf-8'))['stations']
    return stations[asset['station_kind']]['radius'] / 50.


def station_span(kind, faction):
    """The station's own footprint - the measure its render and contact helpers read.

    `ship_size` would resolve a station binding's class from a ship key it does not have,
    so a station is compared against the legacy *station* geometry instead: same envelope,
    same footprint, same gameplay radius.
    """
    from render.camera_geometry import station_bounds
    lo, hi = station_bounds(kind, faction)
    return tuple(hi[i] - lo[i] for i in range(3))


def views_for(asset, length, close_floor=None):
    """Camera plan for one row, framed by its own scaled footprint.

    `close_floor` is the batch's optional minimum distance for the two near views and defaults
    to None, which leaves an older batch's plan bit-for-bit unchanged. A *small* station needs
    it: the shared scene carries a context group, so a station whose footprint scales down to
    a 65-unit framing puts the near eye inside a context hull, `capture_slice.camera_check`
    resolves the eye outwards and refuses the capture ("camera not outside union"). A floor
    set for a batch that frames small stations - not a retuned multiplier, which would move
    every earlier batch's committed frames - keeps the near views clear.
    """
    x, y, z = asset['slot']
    near = max(length * 1.37, close_floor) if close_floor else length * 1.37
    return {'close': dict(target=[x, y, z], distance=near, yaw=48., pitch=35.),
            'rear': dict(target=[x, y - length * .015, z], distance=near, yaw=178., pitch=5.),
            'tactical': dict(target=[x, y, z], distance=length * 5.57, yaw=48., pitch=55.),
            'common-scale': dict(target=[-4300, 0, 2100], distance=1800., yaw=48., pitch=50.)}


def build_row_scene(helper, placements, factions=('rebel', 'imperial')):
    """One clean single-scale row: the reviewed specimens only, no context group.

    The shared helper's scene carries a fixed context group and asserts that each side
    can see it; a scale comparison must not drag those unrelated hulls into frame, so the
    minimal real setup is repeated here: same map, same players, same factory and grid.
    """
    from game.core.manager import GameManager
    from game.core.vectors import Vec3
    from game.systems.economy import EconomySystem
    gm = GameManager()
    st, ds = gm.state, gm.ds
    st.seed = 12345
    m = ds.maps['skirmish01']
    st.map_info.name = helper.VERSION
    st.map_info.victory_mode = 'elimination'
    st.map_info.bounds = m['bounds']
    st.map_info.star = dict(m['star'])
    st.map_info.nebulas = list(m.get('nebulas', []))
    st.map_info.jump_points = list(m.get('jump_points', []))
    st.players = players_for(factions)
    for _label, kind, data_id, owner, pos, yaw in placements:
        # A station row spawns a station: the shared scene's `spawn_station` path draws it
        # through `station_mesh`, which is the seam under review.
        if kind == 'ship':
            gm.factory.spawn_ship(data_id, owner, Vec3(*pos), yaw=yaw)
        else:
            gm.factory.spawn_station(data_id, owner, Vec3(*pos))
    entities = list(st.entities.values())
    for i, e in enumerate(entities):
        for other in entities[i + 1:]:
            assert e.pos.dist_sq(other.pos) > (e.radius + other.radius) ** 2, (e.id, other.id)
    EconomySystem.recompute_command_capacity(st)
    st.grid.rebuild(st.entities)
    gm.visibility.update()
    return gm, st


def build_review_scene(helper, faction='rebel'):
    """Keep the shared scene setup, but declare this orbit harness's actual intent.

    No helper.issue call is made and renderer/HUD receive empty selections; the
    inherited recipe describes the helper's separate combat harness.

    The specimen is re-owned by a player of its own faction, and the shared scene's two
    players are extended when that faction is neither of them, because the renderer
    resolves a *station's* faction from its owner (`owner_faction(state, e.owner)` in the
    renderer's station draw): a `confederacy:command_station` owned by the rebel player
    draws the Alliance design, the seam is then queried as `rebel:command_station` — which
    no candidate matches — and the row reports a 0.0-pixel change against a frame that was
    never injected. (A ship's visual key comes from its ship data row, so ship rows are
    unaffected.) Re-owning puts the specimen in the situation the binding describes: a
    station built by a player of that faction.
    """
    gm, ids, recipe = helper.build_scene()
    st = gm.state
    if faction not in ('rebel', 'imperial'):
        from game.core.state import PlayerState
        owner = FACTION_OWNER[faction]
        st.players[owner] = PlayerState(owner, faction=faction, team=2, is_ai=False,
                                        color=FACTION_COLOR[faction])
        st.entities[ids['capital']].owner = owner
        from render import asset_selection as selection
        selection.invalidate_geometry_helpers()
    return gm, ids, dict(recipe, command_schedule=[], selection=[])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--motion', default=None,
                        help='binding(s) that also get the paired 5s clip, comma separated; every '
                             'row the sheet claims a clip for must be listed, or the sheet points '
                             'at a file no run ever wrote')
    parser.add_argument('--skip-motion', action='store_true')
    args = parser.parse_args()
    spec = load_spec(args.spec)
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    motion_bindings = [b for b in (args.motion or '').split(',') if b] or (
        [] if args.skip_motion else [spec['assets'][0]['binding']])
    for binding in motion_bindings:
        assert any(a['binding'] == binding for a in spec['assets']), binding

    cap = importlib.util.spec_from_file_location(
        'capture_slice', ROOT / 'artifacts/alliance_blender_trio/evidence/capture_slice.py')
    helper = importlib.util.module_from_spec(cap); cap.loader.exec_module(helper)
    source_before = helper.manifest(ROOT)
    protected = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for folder in ('saves', 'replays', 'art/blender', 'tools/art')
                 for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    helper.isolate(ROOT, out)

    import numpy as np
    import pygame
    from OpenGL import GL
    import game.core.manager
    from game.benchmark import state_hash
    from render import asset_selection as selection
    from render.authored_mesh import _load_profile
    from render.camera import Camera
    from render.renderer import Renderer
    from render.hud import HUD
    from render.ship_sizes import ship_size
    from game.data.store import DataStore
    assert not os.environ.get('STAR_ARMADA_FIXED_MATERIALS')

    selection.configure({'model_preview': True})
    production_mesh_for = selection.mesh_for
    candidates = {}
    for asset in spec['assets']:
        assert not production_mesh_for(asset['binding']), (
            f"{asset['binding']} is already selected in production; a pending specimen must not be")
        # Envelope is [lo, hi]; the loader wants per-axis (low, high) limits.
        limits = tuple(zip(*asset['envelope']))
        assert len(limits) == 3 and all(lo < hi for lo, hi in limits), (asset['binding'], limits)
        candidates[asset['binding']] = _load_profile(
            ROOT / asset['mesh'], asset['identifier'], limits, asset['min_length'])

    active = {'enabled': False, 'mesh': None, 'binding': None}

    def review_mesh(binding):
        if not active['enabled']:
            return production_mesh_for(binding)
        if active['binding'] is None:
            # Batch overview: every reviewed specimen is served, nothing else is.
            return candidates.get(binding, production_mesh_for(binding))
        return active['mesh'] if binding == active['binding'] else production_mesh_for(binding)

    selection.mesh_for = review_mesh
    report = dict(schema=1, batch=spec['batch'], status='pending_owner_approval',
                  integration='UNAPPROVED REVIEW-ONLY harness monkeypatch of mesh_for; no production '
                              'activation or approval records',
                  warning='Offline orbit captures: production draw and real simulation ticks; not '
                          'paced FPS, battle acceptance or native Windows graphics acceptance',
                  source_sha256=source_before['sha256'], assets=spec['assets'], captures={},
                  features={}, comparison={}, overview=None, motion={}, mesh={})
    pygame.display.init(); pygame.font.init()
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
    pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
    GL.glEnable(GL.GL_DEPTH_TEST); GL.glEnable(GL.GL_MULTISAMPLE)
    samples = int(GL.glGetIntegerv(GL.GL_SAMPLES)); viewport = list(map(int, GL.glGetIntegerv(GL.GL_VIEWPORT)))
    assert samples == 4 and viewport == [0, 0, W, H]
    report['display'] = dict(samples=samples, viewport=viewport,
                             gl={k: GL.glGetString(v).decode() for k, v in
                                 [('vendor', GL.GL_VENDOR), ('renderer', GL.GL_RENDERER),
                                  ('version', GL.GL_VERSION)]})

    renderer = None; hud = None; images = {}; states = {}
    try:
        for asset in spec['assets']:
            binding = asset['binding']
            helper.PLACEMENTS = placements_for(asset)
            active['binding'] = binding; active['mesh'] = candidates[binding]
            # Class length comes from the live class ratio, not a transcribed number:
            # the candidate must not change it beyond the recorded 1% review tolerance.
            active['enabled'] = False; selection.invalidate_geometry_helpers()
            faction = asset.get('faction', 'rebel')
            station = asset.get('station_kind')
            measure = station_span(station, faction) if station else None
            length = (max(measure) * station_scale(asset) if station
                      else ship_size(DataStore.get(), asset['data_id'], faction).length)
            active['enabled'] = True; selection.invalidate_geometry_helpers()
            if station:
                candidate_measure = station_span(station, faction)
                assert all(abs(a - b) <= max(a, b) * .01 for a, b in zip(measure, candidate_measure)), \
                    (binding, measure, candidate_measure)
                candidate_length = max(candidate_measure) * station_scale(asset)
            else:
                candidate_measure = None
                candidate_length = ship_size(DataStore.get(), asset['data_id'], faction).length
                assert abs(candidate_length - length) <= length * .01, (binding, length, candidate_length)
            views = views_for(asset, length, spec['overview'].get('close_distance_floor'))
            asset_path = ROOT / asset['mesh']
            payload = json.loads(asset_path.read_text(encoding='utf-8'))
            report['mesh'][binding] = dict(
                sha256=hashlib.sha256(asset_path.read_bytes()).hexdigest(),
                triangles=payload['triangle_count'], vertices=len(payload['vertices']),
                bytes=asset_path.stat().st_size, bounds=payload['bounds'],
                blender=payload.get('authoring'), roles=sorted(payload['batches']),
                authority=payload['features'].get('authority'),
                legacy_length=length, candidate_length=candidate_length,
                legacy_footprint=measure, candidate_footprint=candidate_measure,
                station_scale=station_scale(asset) if station else None)
            gm, ids, recipe = build_review_scene(helper, faction); st = gm.state
            initial = state_hash(st)
            active['enabled'] = False; selection.invalidate_geometry_helpers()
            baseline = helper.geometry(st)
            active['enabled'] = True; selection.invalidate_geometry_helpers()
            candidate_geometry = helper.geometry(st)
            active['enabled'] = False; selection.invalidate_geometry_helpers()
            union = [baseline, candidate_geometry]
            cam = Camera(W, H); cam.bind_scene(st, lambda: 0, lambda: 0.)
            pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)

            def draw(view, save=None, with_hud=False):
                pygame.event.pump(); helper.configure(cam, view)
                check = helper.camera_check(cam, st, union, 3.)
                before = state_hash(st)
                renderer.draw(0., set())
                if with_hud:
                    hud.render(set(), None, 0, False); hud.draw_gl()
                assert state_hash(st) == before
                GL.glFinish()
                pixels = np.frombuffer(GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE),
                                       np.uint8).reshape(H, W, 3)[::-1].copy()
                assert GL.glGetError() == GL.GL_NO_ERROR
                if save:
                    pygame.image.save(pygame.image.frombuffer(pixels.tobytes(), (W, H), 'RGB'),
                                      str(out / save))
                return pixels, check

            record = dict(initial_state_sha256=initial, baseline_geometry=baseline,
                          candidate_geometry=candidate_geometry, views=views, captures={},
                          features={}, comparison={})
            for variant in ('before', 'after'):
                active['enabled'] = variant == 'after'
                selection.invalidate_geometry_helpers()
                gm, ids, _ = build_review_scene(helper, faction); st = gm.state
                assert state_hash(st) == initial
                cam = Camera(W, H); cam.bind_scene(st, lambda: 0, lambda: 0.)
                renderer = Renderer(st, cam); renderer.diff_render = True; renderer.time = 3.
                assert not renderer.skip and renderer.materials.available
                report['production_shaders'] = renderer.materials.available
                hud = HUD(W, H, st)
                for name, view in views.items():
                    for _ in range(3):
                        draw(view, with_hud=name == 'tactical')
                    pixels, check = draw(view, f'{asset["label"]}-{variant}-{name}.png',
                                         name == 'tactical')
                    repeat, _ = draw(view, with_hud=name == 'tactical')
                    delta = np.abs(pixels.astype(int) - repeat.astype(int))
                    record['captures'][f'{variant}-{name}'] = dict(
                        camera=check, state_sha256=state_hash(st),
                        repeat_changed_pixels=int(np.any(delta, axis=2).sum()),
                        repeat_max_delta=int(delta.max()))
                    images[binding, variant, name] = pixels
                if variant == 'after':
                    # Ablations prove the owner paint and the drives actually reach pixels.
                    # Each role is measured from the camera that can actually see it: a drive
                    # throat faces aft, so the front-quarter close view would report zero for
                    # a perfectly visible engine bank.
                    for role, camera in (('accent', 'close'), ('dark', 'close'), ('cool', 'rear')):
                        ablated = dict(candidates[binding]); ablated[role] = ()
                        active['mesh'] = ablated
                        renderer.close(); renderer = Renderer(st, cam)
                        renderer.diff_render = True; renderer.time = 3.
                        for _ in range(3):
                            draw(views[camera])
                        pixels, _ = draw(views[camera], f'{asset["label"]}-ablated-{role}.png')
                        full = images[binding, 'after', camera]
                        delta = np.abs(full.astype(int) - pixels.astype(int))
                        changed = np.any(delta > 3, axis=2)
                        ys, xs = np.where(changed)
                        record['features'][role] = dict(
                            camera=camera,
                            changed_pixels=int(changed.sum()),
                            bbox=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
                            if len(xs) else None)
                        active['mesh'] = candidates[binding]
                    renderer.close(); renderer = Renderer(st, cam)
                    renderer.diff_render = True; renderer.time = 3.
                    for _ in range(3):
                        draw(views['close'])
                    restored, _ = draw(views['close'], f'{asset["label"]}-close-restored.png')
                    record['restored_changed_pixels'] = int(
                        np.any(restored != images[binding, 'after', 'close'], axis=2).sum())
                hud.close(); hud = None; renderer.close(); renderer = None
            for name in views:
                a, b = images[binding, 'before', name], images[binding, 'after', name]
                diff = np.abs(a.astype(int) - b.astype(int)); changed = np.any(diff > 3, axis=2)
                ys, xs = np.where(changed)
                record['comparison'][name] = dict(
                    changed_pixels_gt3=int(changed.sum()),
                    changed_percent=round(float(changed.mean() * 100), 4),
                    bbox=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
                    if len(xs) else None)
            # Paired motion: same cameras and same ticks on both variants.
            if binding in motion_bindings:
                timeline = {}
                for variant in ('before', 'after'):
                    active['enabled'] = variant == 'after'
                    selection.invalidate_geometry_helpers()
                    gm, ids, _ = build_review_scene(helper, faction); st = gm.state
                    assert state_hash(st) == initial
                    cam = Camera(W, H); cam.bind_scene(st, lambda: 0, lambda: 0.)
                    renderer = Renderer(st, cam); renderer.diff_render = True; renderer.time = 3.
                    video = out / f'{asset["label"]}-{variant}-motion.mp4'
                    command = ['ffmpeg', '-y', '-f', 'rawvideo', '-pixel_format', 'rgb24',
                               '-video_size', f'{W}x{H}', '-framerate', '30', '-i', '-', '-an',
                               '-c:v', 'libx264', '-crf', '19', '-pix_fmt', 'yuv420p', str(video)]
                    with (out / f'{asset["label"]}-{variant}-ffmpeg.txt').open('w') as log:
                        encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=log)
                        samples_seen = []
                        try:
                            for frame in range(150):
                                gm.step(1 / 30)
                                view = dict(views['close']); view['yaw'] = 48. + frame * .6
                                # The same near-camera clearance the still views take from the
                                # sheet: a modular hardware row is short enough that 1.52 x its
                                # length puts the eye inside a context hull, and the clearance is
                                # inert for every earlier batch, whose rows are longer.
                                view['distance'] = max(length * 1.52,
                                                       spec['overview'].get('close_distance_floor')
                                                       or 0.)
                                renderer.time = 3. + frame / 30
                                pixels, _ = draw(view)
                                samples_seen.append(state_hash(st))
                                encoder.stdin.write(pixels.tobytes())
                        finally:
                            encoder.stdin.close(); assert encoder.wait() == 0
                    timeline[variant] = samples_seen
                    renderer.close(); renderer = None
                record['motion'] = dict(frames=len(timeline['before']), seconds=5, fps=30,
                                        final_state_sha256=timeline['after'][-1],
                                        paired_samples_equal=timeline['before'] == timeline['after'],
                                        before_video=f'{asset["label"]}-before-motion.mp4',
                                        after_video=f'{asset["label"]}-after-motion.mp4')
                assert record['motion']['paired_samples_equal']
            report['captures'][binding] = record
            active['enabled'] = False; selection.invalidate_geometry_helpers()

        # One batch overview at a single scale: the only scale comparison in this sheet.
        # One batch overview at a single shared scale: the only scale comparison here.
        row_factions = ['rebel', 'imperial'] + [f for f in FACTION_ORDER
                                                if any(a.get('faction') == f
                                                       for a in spec['assets'])]
        row = [(f'spec{index}', 'station' if a.get('station_kind') else 'ship',
                a['data_id'], FACTION_OWNER[a.get('faction', 'rebel')],
                [spec['overview']['first_x'], 0,
                 spec['overview']['first_z'] + index * spec['overview']['spacing']], 0.)
               for index, a in enumerate(spec['assets'])]
        overview = {'target': [spec['overview']['first_x'], 0,
                                spec['overview']['first_z']
                                + (len(spec['assets']) - 1) * spec['overview']['spacing'] / 2],
                    'distance': spec['overview']['distance'], 'yaw': spec['overview']['yaw'],
                    'pitch': spec['overview']['pitch']}
        overview_frames = {}
        for variant in ('before', 'after'):
            active['enabled'] = variant == 'after'
            active['binding'] = None
            selection.invalidate_geometry_helpers()
            gm, st = build_row_scene(helper, row, row_factions)
            cam = Camera(W, H); cam.bind_scene(st, lambda: 0, lambda: 0.)
            helper.configure(cam, overview)
            helper.camera_check(cam, st, [helper.geometry(st)], 3.)
            renderer = Renderer(st, cam); renderer.diff_render = True; renderer.time = 3.
            pygame.event.pump()
            renderer.draw(0., set()); GL.glFinish()
            pixels = np.frombuffer(GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE),
                                   np.uint8).reshape(H, W, 3)[::-1].copy()
            renderer.close(); renderer = None
            pygame.image.save(pygame.image.frombuffer(pixels.tobytes(), (W, H), 'RGB'),
                              str(out / f'overview-{variant}.png'))
            overview_frames[variant] = pixels
            images['overview', variant, 'common-scale'] = pixels
        diff = np.abs(images['overview', 'before', 'common-scale'].astype(int)
                      - images['overview', 'after', 'common-scale'].astype(int))
        report['overview'] = dict(cameras=overview, state_sha256=state_hash(st),
                                  placements=[list(entry) for entry in row],
                                  changed_pixels_gt3=int(np.any(diff > 3, axis=2).sum()))
        active['enabled'] = False

        for asset in spec['assets']:
            binding = asset['binding']
            assert production_mesh_for(binding) is None, (binding, 'must not be selected')
        selection.mesh_for = production_mesh_for
        selection.invalidate_geometry_helpers()
        report['production_candidates_unselected_after_review'] = True
        report['source_preserved'] = helper.manifest(ROOT) == source_before
        protected_after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for folder in ('saves', 'replays', 'art/blender', 'tools/art')
                           for p in (ROOT / folder).rglob('*')
                           if p.is_file() and '__pycache__' not in p.parts}
        report['protected_files_preserved'] = protected == protected_after
        assert report['source_preserved'] and report['protected_files_preserved']
        report['protected_file_hashes'] = protected

        order = [a['binding'] for a in spec['assets']]
        rows = [('overview', 'common-scale')] + [(b, n) for b in order for n in VIEW_NAMES]
        sheet = pygame.Surface((1280, len(rows) * 430 + 60)); sheet.fill((10, 16, 25))
        font = pygame.font.SysFont('Arial', 18)
        for i, (binding, name) in enumerate(rows):
            for j, variant in enumerate(('before', 'after')):
                x = j * 640; y = 60 + i * 430
                pixels = images[binding, variant, name]
                sheet.blit(pygame.transform.smoothscale(
                    pygame.image.frombuffer(pixels.tobytes(), (W, H), 'RGB'), (640, 400)), (x, y + 25))
                text = f'{variant.upper()} / {binding} / {name} / same camera, same tick'
                sheet.blit(font.render(text, True, (230, 240, 248)), (x + 10, y))
        sheet.blit(font.render('UNAPPROVED REVIEW ONLY - '
                               + ' ; '.join(a['binding'] for a in spec['assets'])
                               + ' - Blender masters - 4MSAA / production shaders / normal fog',
                               True, (200, 220, 240)), (12, 20))
        pygame.image.save(sheet, str(out / 'contact-sheet.png'))
        # `overview.png` used to be saved from the `pixels` left over by the last row's last
        # draw, so the file that reads as "the batch overview" was a duplicate of one row's
        # capture - it did not move when the overview camera moved, which is how a framing
        # check came to be run against the wrong frame. Save the frame the overview draw made.
        pygame.image.save(pygame.image.frombuffer(overview_frames['after'].tobytes(),
                                                 (W, H), 'RGB'), str(out / 'overview.png'))
        helper.dump(out / 'metrics.json', report)
        print(json.dumps({b: dict(comparison=report['captures'][b]['comparison'],
                                  features=report['captures'][b]['features'],
                                  mesh=report['mesh'][b]) for b in order}, indent=2))
    finally:
        selection.mesh_for = production_mesh_for
        if hud is not None:
            hud.close()
        if renderer is not None:
            renderer.close()
        pygame.display.quit(); pygame.font.quit()


if __name__ == '__main__':
    main()
