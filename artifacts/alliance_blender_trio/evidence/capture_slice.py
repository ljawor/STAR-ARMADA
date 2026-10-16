#!/usr/bin/env python3
"""Prepared, NOT runtime-validated. See HARNESS.md for serial future commands.

Use the repository's lexical .venv/bin/python, never its resolved python symlink.
All modes require --source (an immutable snapshot) and a fresh scratch --output.
seal-source is stdlib only; inspect-source constructs real factory state, no GL.
Capture modes require a two-source camera plan and explicitly released compute.
No imports from tools/, tests/, main.py, or the untracked showcase are used.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.abc
import importlib.machinery
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
import traceback

SCRATCH = Path('/Users/lukaszjawor/.hermes/cache/scratch/graphics-blender-trio').resolve()
LIVE = Path('/Users/lukaszjawor/Downloads/Project/STAR-ARMADA').resolve()
W, H, DT = 1280, 800, 1 / 30
VERSION = 'alliance-visual-slice-v1'
# Same world for sheet, individual detail shots and combat. Kelvin planet data
# stays exact; specimens are arranged near its surface, not moved for each view.
PLACEMENTS = [
    ('capital', 'ship', 'rebel_battleship', 0, [-4200, 0, 2200], 0.0),
    ('escort', 'ship', 'rebel_frigate', 0, [-4200, 0, 2550], 0.0),
    ('yard', 'station', 'shipyard', 0, [-4200, 0, 1600], 0.0),
    ('enemy_a', 'ship', 'imperial_frigate', 1, [-3500, 0, 2200], -math.pi / 2),
    ('enemy_b', 'ship', 'imperial_frigate', 1, [-3500, 0, 2550], -math.pi / 2),
]
# Explicit reviewable proposals. plan-cameras never silently moves an eye.
VIEWS = {
    'common-scale': dict(target=[-4300, 0, 2100], distance=1800., yaw=48., pitch=50.),
    'capital-detail': dict(target=[-4200, 0, 2200], distance=310., yaw=55., pitch=35.),
    'capital-keel': dict(target=[-4200, 0, 2200], distance=400., yaw=110., pitch=-20.),
    'capital-close': dict(target=[-4200, 0, 2200], distance=450., yaw=48., pitch=45.),
    'escort-close': dict(target=[-4200, 0, 2550], distance=155., yaw=48., pitch=35.),
    'yard-close': dict(target=[-4200, 0, 1600], distance=450., yaw=48., pitch=45.),
    'capital-engine': dict(target=[-4200, -3, 2200], distance=310., yaw=178., pitch=8.),
    'capital-rear': dict(target=[-4200, 0, 2200], distance=450., yaw=155., pitch=38.),
    'escort-rear': dict(target=[-4200, 0, 2550], distance=180., yaw=155., pitch=25.),
    'yard-rear': dict(target=[-4200, 0, 1600], distance=450., yaw=155., pitch=38.),
    'tactical': dict(target=[-4200, 0, 2100], distance=3100., yaw=48., pitch=55.),
}


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def manifest(source):
    files = {}
    for name in ('game', 'render', 'assets'):
        root = source / name
        if not root.is_dir():
            raise ValueError(f'missing source subtree: {root}')
        for p in sorted(root.rglob('*')):
            if p.is_symlink():
                raise ValueError(f'symlink forbidden in source inputs: {p}')
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
                files[str(p.relative_to(source))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return dict(schema=1, files=files, sha256=digest(files))


class PersistenceLoader(importlib.abc.Loader):
    """Execute actual menus module then patch all 5 paths before consumers see it.

    The inspected module defines constants and functions at top level, but does
    not instantiate MenuStack there. No replacement/fake menu implementation.
    """
    def __init__(self, wrapped, root):
        self.wrapped, self.root = wrapped, root

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        self.wrapped.exec_module(module)
        paths = dict(USER_DIR=self.root, SAVES_DIR=self.root / 'saves',
                     SETTINGS_PATH=self.root / 'saves/settings.json',
                     CAMPAIGN_PATH=self.root / 'saves/campaign.json',
                     BALANCE_PATH=self.root / 'saves/balance.json')
        for key, value in paths.items():
            setattr(module, key, str(value))


class PersistenceFinder(importlib.abc.MetaPathFinder):
    def __init__(self, root):
        self.root = root

    def find_spec(self, fullname, path=None, target=None):
        if fullname != 'render.menus':
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None:
            raise ImportError(fullname)
        spec.loader = PersistenceLoader(spec.loader, self.root)
        return spec


def isolate(source, output):
    # No native write sandbox is claimed. This audit guard is defense in depth
    # for Python IO; SDL/GL native caches are separately noted in HARNESS.md.
    sys.dont_write_bytecode = True
    os.chdir(output)
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    for key in ('STAR_ARMADA_SKIP', 'SDL_VIDEODRIVER', 'STAR_ARMADA_DATA'):
        if os.environ.get(key):
            raise ValueError(f'unset {key}; normal real-renderer path required')
    os.environ['TMPDIR'] = str(output / 'tmp')
    os.environ['XDG_CACHE_HOME'] = str(output / 'cache')
    for p in ('tmp', 'cache', 'user/saves'):
        (output / p).mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(source))
    sys.meta_path.insert(0, PersistenceFinder(output / 'user'))

    def writable(path):
        if isinstance(path, int):
            return
        p = Path(os.fsdecode(path)).resolve()
        if not p.is_relative_to(output):
            raise PermissionError(f'harness Python write outside output: {p}')

    def audit(event, args):
        if event == 'open':
            path, mode, flags = args
            if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            ):
                writable(path)
        elif event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod'):
            writable(args[0])
        elif event in ('os.rename', 'os.link', 'os.symlink'):
            writable(args[0]); writable(args[1])
    sys.addaudithook(audit)


def build_scene():
    from game.core.manager import GameManager
    from game.core.state import PlayerState
    from game.core.vectors import Vec3
    from game.systems.economy import EconomySystem
    gm = GameManager()
    st, ds = gm.state, gm.ds
    st.seed = 12345
    m = ds.maps['skirmish01']
    st.map_info.name = VERSION
    # Real skirmish coalition-elimination mode, as start_skirmish uses; legacy
    # command-mode would end a no-command-station specimen scene at its first check.
    st.map_info.victory_mode = 'elimination'
    st.map_info.bounds = m['bounds']
    st.map_info.star = dict(m['star'])
    st.map_info.nebulas = list(m.get('nebulas', []))
    st.map_info.jump_points = list(m.get('jump_points', []))
    st.players = {
        0: PlayerState(0, faction='rebel', team=0, is_ai=False, color=(.35, .65, 1.)),
        1: PlayerState(1, faction='imperial', team=1, is_ai=False, color=(1., .35, .25)),
    }
    pd = next(p for p in m['planets'] if p['id'] == 'planet_kel')
    assert pd['type'] == 'temperate' and pd['radius'] == 700
    planet = gm.factory.spawn_planet(dict(pd))
    ids = {'planet': planet.id}
    for label, kind, data_id, owner, pos, yaw in PLACEMENTS:
        if kind == 'ship':
            e = gm.factory.spawn_ship(data_id, owner, Vec3(*pos), yaw=yaw)
        else:
            e = gm.factory.spawn_station(data_id, owner, Vec3(*pos))
        ids[label] = e.id
    # Reject physically overlapping setup; no collision/range overrides.
    entities = list(st.entities.values())
    for i, e in enumerate(entities):
        for other in entities[i + 1:]:
            assert e.pos.dist_sq(other.pos) > (e.radius + other.radius) ** 2, (e.id, other.id)
    EconomySystem.recompute_command_capacity(st)
    st.grid.rebuild(st.entities)
    gm.visibility.update()
    for owner in (0, 1):
        targets = (ids['enemy_a'], ids['enemy_b']) if owner == 0 else (ids['capital'], ids['escort'])
        for eid in targets:
            assert st.can_see(owner, eid), ('stock sensor gate failed', owner, eid)
    recipe = dict(version=VERSION, seed=st.seed, dt=DT, placements=PLACEMENTS,
                  planet_definition=pd, map_context=dict(bounds=m['bounds'], star=m['star'],
                  nebulas=m.get('nebulas', []), jump_points=m.get('jump_points', [])),
                  entity_ids=ids, players=[dict(id=p.id, faction=p.faction, team=p.team,
                  color=p.color, ai=p.is_ai) for p in st.players.values()],
                  command_schedule='tick 1 and every 180 ticks: each side focus lowest-ID live opponent; real AttackCommand through state.command_queue',
                  selection=[ids['capital']], direct_factory_setup=True,
                  paid_construction_or_terrain_eligibility_proven=False)
    return gm, ids, recipe


def geometry(st):
    from render.camera_geometry import station_bounds
    from render.ship_sizes import ship_size, _bounds
    from render.faction_visuals import owner_faction
    result = {}
    for e in st.entities.values():
        if e.is_planet:
            result[str(e.id)] = dict(kind='sphere', radius=e.radius * 1.018)
        else:
            faction = owner_faction(st, e.owner)
            if e.is_station:
                lo, hi = station_bounds(e.data_id, faction)
                scale = e.radius / 50.
            else:
                size = ship_size(__import__('game.data.store', fromlist=['DataStore']).DataStore.get(), e.data_id, faction)
                lo, hi, _ = _bounds(size.shape)
                scale = size.scale
            result[str(e.id)] = dict(kind='station' if e.is_station else 'ship',
                                    lo=[v * scale for v in lo], hi=[v * scale for v in hi])
    return result


def boxes(st, geometries, view_time):
    result = []
    for table in geometries:
        for key, g in table.items():
            e = st.entities.get(int(key))
            if e is None or not e.alive:
                continue
            center = e.pos.to_tuple()
            if g['kind'] == 'sphere':
                result.append((center, g['radius']))
            else:
                angle = math.radians(view_time * 3.) if g['kind'] == 'station' else e.yaw
                box = (center, angle, tuple(g['lo']), tuple(g['hi']))
                result.append(box + (True,) if g['kind'] == 'ship' else box)
    return tuple(result)


def configure(cam, spec):
    cam.target = list(spec['target'])
    for key in ('distance', 'yaw', 'pitch'):
        setattr(cam, key, spec[key])
    cam.fov, cam.near, cam.far = 55., 20., 60000.


def camera_check(cam, st, geometries, view_time):
    from render.camera_geometry import safe_eye
    requested = cam._requested_eye()
    union_eye = safe_eye(cam.target, requested, boxes(st, geometries, view_time),
                         cam.near, cam.fov, cam.width / cam.height, cam.height)
    cam.refresh_scene()
    resolved = cam.eye_position()
    for eye in (union_eye, resolved):
        if any(abs(a - b) > 1e-7 for a, b in zip(requested, eye)):
            raise ValueError(f'camera not outside union; recapture BOTH with revised shared plan: requested={requested}, union={union_eye}, resolved={resolved}')
    return dict(requested_eye=requested, resolved_eye=resolved, union_eye=union_eye,
                target=cam.target, distance=cam.distance, yaw=cam.yaw, pitch=cam.pitch,
                fov=cam.fov, near=cam.near, far=cam.far)


def stats(st, ids):
    return {label: dict(id=eid, data_id=e.data_id, alive=e.alive, operational=e.operational,
                        hull=e.hull, shields=dict(e.shields), pos=e.pos.to_tuple(),
                        visible_to_local=st.can_see(0, eid))
            for label, eid in ids.items() if (e := st.entities.get(eid)) is not None}


def issue(gm, tick, log):
    from game.core.commands import AttackCommand
    st = gm.state
    if (tick - 1) % 180:
        return
    for owner in (0, 1):
        own = sorted(e.id for e in st.entities.values() if e.alive and e.owner == owner and e.is_ship and e.operational)
        enemy = sorted(e.id for e in st.entities.values() if e.alive and e.owner == 1 - owner and e.is_ship)
        if own and enemy:
            command = AttackCommand(owner, own, enemy[0])
            st.command_queue.append(command)
            log.write(json.dumps(dict(tick=tick, command=command.to_dict())) + '\n')
            log.flush()


def percentiles(values):
    s = sorted(values)
    if not s:
        return {}
    return dict(samples=len(s), median_ms=statistics.median(s),
                p95_ms=s[min(len(s) - 1, math.ceil(.95 * len(s)) - 1)], max_ms=max(s))


def run(args, seal, output):
    from game.benchmark import state_hash
    from render.camera import Camera
    gm, ids, recipe = build_scene()
    st = gm.state
    initial = state_hash(st)
    own_geometry = geometry(st)
    dump(output / 'recipe.json', recipe)
    dump(output / 'geometry.json', dict(source_sha256=seal['sha256'], recipe_sha256=digest(recipe), geometry=own_geometry))
    dump(output / 'initial-state.json', st.to_dict(precise=True))
    if args.mode == 'inspect-source':
        dump(output / 'summary.json', dict(status='source-inspected-no-GL-no-ticks', initial_state_sha256=initial,
                                         source_sha256=seal['sha256']))
        return
    peer = load(args.geometry_peer) if args.geometry_peer else None
    if peer is None or peer['recipe_sha256'] != digest(recipe):
        raise ValueError('--geometry-peer from the other inspected source with identical recipe required')
    geometries = [own_geometry, peer['geometry']]
    if args.mode == 'plan-cameras':
        cam = Camera(W, H)
        # No GL context; real scene binding and pure safety checks only.
        cam.bind_scene(st, lambda: 0, lambda: math.radians(3. * 3.))
        checked = {}
        for name, spec in VIEWS.items():
            configure(cam, spec)
            checked[name] = camera_check(cam, st, geometries, 3.)
        dump(output / 'camera-plan.json', dict(version=VERSION, recipe_sha256=digest(recipe),
             sources=sorted([seal['sha256'], peer['source_sha256']]), views=VIEWS,
             checked_initial=checked, logical_size=[W, H], frozen_view_time=3.,
             motion=dict(start_distance=1800., end_distance=1500., yaw_delta=20.,
                         view_time_start=3., view_time_dt=DT)))
        return
    plan = load(args.camera_plan) if args.camera_plan else None
    if not plan or plan['recipe_sha256'] != digest(recipe) or plan['sources'] != sorted([seal['sha256'], peer['source_sha256']]):
        raise ValueError('camera plan must bind this exact recipe and BOTH source seals')
    import pygame
    import numpy as np
    from OpenGL import GL
    from render.renderer import Renderer
    from render.hud import HUD
    if pygame.display.get_init() or pygame.font.get_init():
        raise RuntimeError('standalone process required; refusing an already-owned SDL display/font')
    renderer = hud = None
    owned_display = owned_font = False
    events = []
    st.events.subscribe('weapon_fired', lambda event: events.append(dict(tick=st.tick, data=dict(event.data))))
    report = dict(status='running', source_sha256=seal['sha256'], peer_source_sha256=peer['source_sha256'],
                  recipe_sha256=digest(recipe), camera_plan_sha256=digest(plan), mode=args.mode,
                  initial_state_sha256=initial, captures=[], ticks=args.ticks,
                  warnings=['No appearance acceptance or performance target is inferred from this harness.'])
    dump(output / 'summary.json', report)
    try:
        pygame.display.init(); owned_display = True
        pygame.font.init(); owned_font = True
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
        pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
        pygame.event.pump()
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_MULTISAMPLE)
        GL.glClearColor(.008, .012, .025, 1.)
        viewport = tuple(int(x) for x in GL.glGetIntegerv(GL.GL_VIEWPORT))
        actual = int(GL.glGetIntegerv(GL.GL_SAMPLES))
        buffers = int(GL.glGetIntegerv(GL.GL_SAMPLE_BUFFERS))
        if actual != 4 or buffers != 1 or viewport != (0, 0, W, H):
            raise RuntimeError(f'need actual 1280x800 4MSAA: viewport={viewport}, samples={actual}, buffers={buffers}')
        report['display'] = dict(logical=pygame.display.get_window_size(), viewport=viewport,
                                  drawable=viewport[2:], samples=actual, sample_buffers=buffers,
                                  sdl_requested_samples=pygame.display.gl_get_attribute(pygame.GL_MULTISAMPLESAMPLES),
                                  driver=pygame.display.get_driver(),
                                  gl={k: GL.glGetString(v).decode() for k, v in [('vendor', GL.GL_VENDOR), ('renderer', GL.GL_RENDERER), ('version', GL.GL_VERSION)]})
        cam = Camera(W, H)
        renderer = Renderer(st, cam)
        if renderer.skip:
            raise RuntimeError('renderer skip passes must be empty')
        renderer.diff_render = args.mode != 'paced-validation'
        renderer.time = 3.
        # Allocate before initialization so partial allocations can still close.
        hud = HUD.__new__(HUD)
        hud.tex = None
        HUD.__init__(hud, W, H, st)
        selection = {ids['capital']}
        report['materials_available'] = renderer.materials.available
        report['fixed_materials_requested'] = os.environ.get('STAR_ARMADA_FIXED_MATERIALS') == '1'

        def draw(spec, view_time, dt=0., with_hud=False):
            pygame.event.pump()
            if any(e.type == pygame.QUIT for e in pygame.event.get()):
                raise RuntimeError('window closed by operator')
            configure(cam, spec)
            if renderer.diff_render:
                renderer.time = view_time
            # Live mode advances r.time in draw; validate that future orientation.
            planned_time = renderer.time if renderer.diff_render else renderer.time + dt
            before = state_hash(st)
            info = camera_check(cam, st, geometries, planned_time)
            renderer.draw(dt, selection)
            if with_hud:
                hud.render(selection, None, 0, False)
                hud.draw_gl()
            after = state_hash(st)
            if before != after:
                raise AssertionError('render/HUD mutated precise simulation digest')
            info.update(state_before=before, state_after=after,
                        view_matrix=np.asarray(cam._view).tolist(), projection_matrix=np.asarray(cam._proj).tolist(),
                        subjects={label: dict(center=cam.world_to_screen(*st.entities[eid].pos.to_tuple()),
                            visible=st.can_see(0, eid)) for label, eid in ids.items() if eid in st.entities})
            if GL.glGetError() != GL.GL_NO_ERROR:
                raise RuntimeError('GL error after draw')
            return info

        def capture(name, spec, view_time, with_hud=False, repeat=False):
            for _ in range(3):
                draw(spec, view_time, with_hud=with_hud)
            info = draw(spec, view_time, with_hud=with_hud)
            GL.glFinish()  # Offline evidence only; absent from paced path.
            raw = GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
            pixels = np.frombuffer(raw, np.uint8).reshape(H, W, 3)[::-1].copy()
            if repeat:
                draw(spec, view_time, with_hud=with_hud)
                GL.glFinish()
                repeat_pixels = np.frombuffer(GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE), np.uint8).reshape(H, W, 3)[::-1].copy()
                if not np.array_equal(pixels, repeat_pixels):
                    raise AssertionError('same-source frozen repeat differs')
            path = output / (name + '.png')
            pygame.image.save(pygame.image.frombuffer(pixels.tobytes(), (W, H), 'RGB'), str(path))
            info.update(name=name, image=path.name, image_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        tick=st.tick, view_time=view_time, hud=with_hud, repeat_checked=repeat,
                        pixels_sha256=hashlib.sha256(pixels.tobytes()).hexdigest())
            report['captures'].append(json.loads(json.dumps(info)))
            return pixels

        if args.mode in ('baseline-capture', 'candidate-capture'):
            for name, spec in plan['views'].items():
                capture('initial-' + name, spec, 3., with_hud=name == 'tactical', repeat=True)
        clock = pygame.time.Clock()
        durations = []
        with (output / 'ticks.jsonl').open('w', encoding='utf-8') as ticks, (output / 'commands.jsonl').open('w', encoding='utf-8') as commands:
            ticks.write(json.dumps(dict(tick=st.tick, sha256=initial, entities=stats(st, ids))) + '\n')
            for tick in range(1, args.ticks + 1):
                elapsed = clock.tick(30) / 1000. if args.mode == 'paced-validation' else DT
                start = time.perf_counter()
                issue(gm, tick, commands)
                gm.step(DT)
                if st.tick != tick:
                    raise RuntimeError(f'simulation stopped early: expected {tick}, got {st.tick}, game_over={st.game_over}')
                row = dict(tick=tick, sha256=state_hash(st), entities=stats(st, ids),
                           projectiles=len(st.projectiles), effects=len(st.effects), weapon_events_total=len(events))
                ticks.write(json.dumps(row, allow_nan=False) + '\n'); ticks.flush()
                if args.mode == 'motion-capture':
                    fraction = tick / max(1, args.ticks)
                    spec = dict(plan['views']['common-scale'])
                    motion = plan['motion']
                    spec['yaw'] += motion['yaw_delta'] * fraction
                    spec['distance'] = motion['start_distance'] + (motion['end_distance'] - motion['start_distance']) * fraction
                    capture(f'motion-{tick:05d}', spec, motion['view_time_start'] + tick * motion['view_time_dt'], with_hud=True)
                elif args.mode == 'paced-validation':
                    draw(plan['views']['tactical'], renderer.time, dt=elapsed, with_hud=True)
                    pygame.display.flip()  # No glFinish, glReadPixels or offline encode.
                    durations.append((time.perf_counter() - start) * 1000.)
            if args.mode in ('baseline-capture', 'candidate-capture'):
                capture('final-tactical', plan['views']['tactical'], 3., with_hud=True, repeat=True)
        report['final_state_sha256'] = state_hash(st)
        report['activity'] = dict(weapon_fired=len(events), events=events, final_entities=stats(st, ids))
        dump(output / 'final-state.json', st.to_dict(precise=True))
        if not events:
            raise AssertionError('no genuine weapon_fired events; do not label as battle evidence')
        # Shield/hull may regenerate by final tick; detect changes anywhere in timeline.
        timeline = [json.loads(line) for line in (output / 'ticks.jsonl').read_text().splitlines()]
        start_entities = timeline[0]['entities']
        damage_observed = any(any(label not in row['entities'] or row['entities'][label]['hull'] < e['hull'] or
            sum(row['entities'][label]['shields'].values()) < sum(e['shields'].values())
            for label, e in start_entities.items() if label != 'planet') for row in timeline[1:])
        report['activity']['shield_or_hull_reduction_observed'] = damage_observed
        if not damage_observed:
            raise AssertionError('no genuine shield/hull reduction observed')
        report['paced_work_ms_excluding_clock_wait'] = percentiles(durations)
        report['pacing_note'] = 'SDL Clock at fixed 30Hz simulation cadence; not an agreed FPS target. Costs include digest instrumentation and ordinary swap; no GPU synchronization in paced mode.'
        if args.compare:
            other = load(Path(args.compare) / 'summary.json')
            old_ticks = [json.loads(line) for line in (Path(args.compare) / 'ticks.jsonl').read_text().splitlines()]
            if [r['sha256'] for r in old_ticks] != [r['sha256'] for r in timeline]:
                raise AssertionError('baseline/candidate per-tick digest mismatch')
            if other['camera_plan_sha256'] != report['camera_plan_sha256']:
                raise AssertionError('different camera plans')
            if other['display'] != json.loads(json.dumps(report['display'])) or other['materials_available'] != report['materials_available']:
                raise AssertionError('quality/context/material path differs')
            report['comparison'] = []
            if len(other['captures']) != len(report['captures']):
                raise AssertionError('different capture counts')
            for old, new in zip(other['captures'], report['captures']):
                for key in ('name', 'tick', 'view_time', 'requested_eye', 'resolved_eye', 'view_matrix', 'projection_matrix', 'state_before'):
                    if old[key] != new[key]:
                        raise AssertionError(f'capture contract mismatch: {new["name"]}: {key}')
                a = pygame.surfarray.array3d(pygame.image.load(str(Path(args.compare) / old['image']))).transpose(1, 0, 2)
                b = pygame.surfarray.array3d(pygame.image.load(str(output / new['image']))).transpose(1, 0, 2)
                delta = np.abs(a.astype(np.int16) - b.astype(np.int16))
                report['comparison'].append(dict(name=new['name'], changed_pixels=int(np.any(delta != 0, axis=2).sum()),
                                                 mean_absolute_channel_delta=float(delta.mean()),
                                                 note='Descriptive only: neither geometry nor appearance acceptance.'))
        report['status'] = 'captured-not-appearance-approved' if args.mode != 'paced-validation' else 'paced-run-recorded-not-performance-accepted'
    except BaseException as exc:
        report['status'] = 'failed'
        report['error'] = repr(exc)
        report['traceback'] = traceback.format_exc()
        raise
    finally:
        cleanup_errors = []
        # Every independently owned resource is attempted before context teardown.
        for resource in (hud, getattr(hud, 'fog', None), renderer):
            if resource is not None:
                try:
                    resource.close()
                except BaseException as exc:
                    cleanup_errors.append(repr(exc))
        if owned_font:
            # No MenuStack/clean_classic font cache is constructed in this process.
            pygame.font.quit()
        if owned_display:
            pygame.display.quit()
        report['cleanup_errors'] = cleanup_errors
        if cleanup_errors:
            report['status'] = 'failed-cleanup'
        dump(output / 'summary.json', report)
        if cleanup_errors and sys.exc_info()[0] is None:
            raise RuntimeError(cleanup_errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', required=True, choices=('seal-source', 'inspect-source', 'plan-cameras', 'baseline-capture', 'candidate-capture', 'motion-capture', 'paced-validation'))
    parser.add_argument('--seal', type=Path, help='prior source-manifest.json; mandatory except seal-source')
    parser.add_argument('--geometry-peer', type=Path)
    parser.add_argument('--camera-plan', type=Path)
    parser.add_argument('--compare', type=Path, help='matching baseline output directory')
    parser.add_argument('--ticks', type=int, default=180)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if source == LIVE or source.is_relative_to(LIVE) or not source.is_relative_to(SCRATCH):
        parser.error('--source must be an immutable snapshot inside dedicated scratch, NOT the live tree')
    if not output.is_relative_to(SCRATCH) or output == SCRATCH or output.is_relative_to(source) or source.is_relative_to(output):
        parser.error('output must be a dedicated disjoint scratch subdirectory')
    if output.exists():
        parser.error('output already exists; choose a fresh directory (no overwrite)')
    if args.ticks < 1:
        parser.error('--ticks must be positive')
    output.mkdir(parents=True)
    current = manifest(source)
    dump(output / 'invocation.json', dict(argv=sys.argv, executable=sys.executable, source=str(source), output=str(output), harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    dump(output / 'source-manifest.json', current)
    if args.mode == 'seal-source':
        return
    if not args.seal or current != load(args.seal):
        parser.error('source differs from --seal (or missing seal); capture is forbidden')
    isolate(source, output)
    try:
        run(args, current, output)
    finally:
        after = manifest(source)
        dump(output / 'source-manifest-after.json', after)
        if current != after:
            raise RuntimeError('immutable source CHANGED during execution; reject all evidence')


if __name__ == '__main__':
    main()
